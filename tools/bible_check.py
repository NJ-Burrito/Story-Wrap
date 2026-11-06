# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Writing-stage machine check for a series bible.

    uv run tools/bible_check.py bible/series/<series> [--min-diff 8] [--json]

Prints one line per finding: `FAIL [CHECK-ID] <path>: message`. Exit 0 = pass, 1 = findings, 2 = usage error.
Required character fields come from kb/templates/character-bible.md (single source of truth).
Layout and rules: pipelines/WRITING.md. A check with no data fails; it never passes (R-398).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TEMPLATE = REPO / "kb/templates/character-bible.md"

CORE_EMOTIONS = ["calm", "joy", "sadness", "fear", "anger", "surprise", "disgust", "shame"]
CHANNELS = ["eyes", "face", "body", "voice", "action", "environment", "colour", "sfx", "vfx"]
MIN_SHOW_CHANNELS = 4
HANDS = {"left", "right", "ambidextrous"}
ARCS = {"positive", "flat", "negative"}
CULTURE_STATUS = {"closed", "pending", "open"}
AXES = 10
EMPTY_WORDS = {"", "tbd", "todo", "...", "-", "n/a"}  # bare "n/a" is not enough: "n/a because ..."

FIELD_RE = re.compile(r"^- ([a-z][a-z0-9_]*):[ \t]*(.*)$")
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)


@dataclass
class Finding:
    check: str
    path: str
    msg: str

    def line(self) -> str:
        return f"FAIL [{self.check}] {self.path}: {self.msg}"


# ---------------------------------------------------------------- parsing

def strip_comments(text: str) -> str:
    return COMMENT_RE.sub("", text)


def is_placeholder(v: str) -> bool:
    v = v.strip()
    if v.lower().strip(".") in EMPTY_WORDS or v.lower() in EMPTY_WORDS:
        return True
    return v.startswith("<") and v.endswith(">")


def parse_fields(text: str) -> dict[str, dict]:
    """Return {key: {"value": inline text, "nested": [lines]}} for top-level `- key: value` lines.

    Nested lines are indented lines that follow. Fields inside `### emotion:` blocks are parsed
    separately by parse_emotions and are skipped here (keys shows/hides/leak)."""
    out: dict[str, dict] = {}
    cur = None
    in_emotion = False
    for raw in strip_comments(text).splitlines():
        if raw.startswith("#"):
            in_emotion = bool(re.match(r"^###\s+emotion:", raw))
            cur = None
            continue
        if in_emotion:
            continue
        m = FIELD_RE.match(raw)
        if m:
            cur = {"value": m.group(2).strip(), "nested": []}
            out[m.group(1)] = cur
        elif cur is not None and raw.startswith((" ", "\t")) and raw.strip():
            cur["nested"].append(raw.strip())
        elif not raw.strip():
            continue
        else:
            cur = None
    return out


def field_filled(f: dict | None) -> bool:
    if not f:
        return False
    if f["value"] and not is_placeholder(f["value"]):
        return True
    for n in f["nested"]:
        body = re.sub(r"^[-*]\s+", "", n)
        if n.startswith("|"):
            cells = [c.strip() for c in n.strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells):
                continue
            if cells and any(c and not is_placeholder(c) for c in cells[1:] or cells):
                return True
            continue
        if body and not is_placeholder(body):
            return True
    return False


def parse_emotions(text: str) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    cur = None
    for raw in strip_comments(text).splitlines():
        m = re.match(r"^###\s+emotion:\s*([A-Za-z-]+)\s*$", raw)
        if m:
            cur = out.setdefault(m.group(1).lower(), {})
            continue
        if raw.startswith("#"):
            cur = None
            continue
        fm = FIELD_RE.match(raw)
        if cur is not None and fm:
            cur[fm.group(1)] = fm.group(2).strip()
    return out


def required_keys() -> list[str]:
    """Every top-level field key of the template, outside emotion blocks."""
    if not TEMPLATE.exists():
        raise SystemExit(f"template missing: {TEMPLATE}")
    return list(parse_fields(TEMPLATE.read_text(encoding="utf-8")).keys())


def tokens(s: str) -> set[str]:
    return {w.lower() for w in re.findall(r"[\w؀-ۿ]{4,}", s)}


def split_csv(s: str) -> list[str]:
    return [p.strip() for p in re.split(r"[;,؛،]", s) if p.strip() and not is_placeholder(p)]


# ---------------------------------------------------------------- character checks

def check_character(cdir: Path, series: Path, req: list[str]) -> list[Finding]:
    F: list[Finding] = []
    rel = lambda p: p.relative_to(series.parent).as_posix() if series.parent in p.parents else p.as_posix()  # noqa: E731
    bible = cdir / "bible.md"
    if not bible.exists():
        return [Finding("BIBLE-FIELDS", rel(cdir), "bible.md missing")]
    text = bible.read_text(encoding="utf-8")
    fields = parse_fields(text)
    P = rel(bible)

    missing = [k for k in req if not field_filled(fields.get(k))]
    if missing:
        F.append(Finding("BIBLE-FIELDS", P, f"{len(missing)} empty or missing fields: {', '.join(missing)}"))
    ident = fields.get("id", {}).get("value", "")
    if ident and ident != cdir.name:
        F.append(Finding("BIBLE-FIELDS", P, f"id {ident!r} does not match folder {cdir.name!r}"))
    arc = fields.get("arc_type", {}).get("value", "").strip().lower()
    if arc and arc not in ARCS:
        F.append(Finding("BIBLE-FIELDS", P, f"arc_type {arc!r} is not one of positive, flat, negative"))

    # BIBLE-CULTURE
    cb = fields.get("culture_brief", {}).get("value", "").strip()
    status = fields.get("culture_status", {}).get("value", "").strip().lower()
    if not cb or is_placeholder(cb):
        F.append(Finding("BIBLE-CULTURE", P, "culture_brief not set"))
    else:
        cpath = (cdir / cb).resolve()
        if not cpath.is_file():
            F.append(Finding("BIBLE-CULTURE", P, f"culture brief not found: {cb}"))
        else:
            ct = strip_comments(cpath.read_text(encoding="utf-8"))
            ok = False
            for m in re.finditer(r"^##+\s+.*decisions?.*$", ct, re.I | re.M):
                body = ct[m.end():].split("\n## ", 1)[0]
                if re.search(r"^\s*(?:[-*]|\d+[.)])\s+\S", body, re.M):
                    ok = True
            if not ok:
                F.append(Finding("BIBLE-CULTURE", rel(cpath),
                                 "no 'Decisions' section with at least one recorded or open decision"))
    if status and status not in CULTURE_STATUS:
        F.append(Finding("BIBLE-CULTURE", P, f"culture_status {status!r} is not closed, pending or open"))

    # BIBLE-ACCENT
    src = fields.get("accent_source", {}).get("value", "")
    feats = fields.get("accent_features", {})
    flist = split_csv(feats.get("value", "")) + [re.sub(r"^[-*]\s+", "", n) for n in feats.get("nested", [])
                                                  if not is_placeholder(re.sub(r"^[-*]\s+", "", n))]
    origin = fields.get("origin", {}).get("value", "") + " " + " ".join(fields.get("origin", {}).get("nested", []))
    if not src or is_placeholder(src):
        F.append(Finding("BIBLE-ACCENT", P, "accent_source empty: name the origin the accent comes from"))
    elif not (tokens(src) & tokens(origin)):
        F.append(Finding("BIBLE-ACCENT", P, "accent_source shares no word with origin: the accent must follow the origin"))
    if len(flist) < 2:
        F.append(Finding("BIBLE-ACCENT", P, f"accent_features lists {len(flist)} feature(s); need at least 2"))

    # BIBLE-EMOTION
    emo = parse_emotions(text)
    for e in CORE_EMOTIONS:
        blk = emo.get(e)
        if blk is None:
            F.append(Finding("BIBLE-EMOTION", P, f"emotion block missing: {e}"))
            continue
        shows = blk.get("shows", "")
        got = sorted({c for c in CHANNELS if re.search(rf"\b{c}\s*:", shows, re.I)})
        if is_placeholder(shows) or len(got) < MIN_SHOW_CHANNELS:
            F.append(Finding("BIBLE-EMOTION", P,
                             f"{e}: shows names {len(got)} channel(s) ({', '.join(got) or 'none'}); need >= {MIN_SHOW_CHANNELS}"))
        for k in ("hides", "leak"):
            if is_placeholder(blk.get(k, "")):
                F.append(Finding("BIBLE-EMOTION", P, f"{e}: {k} empty"))

    # BIBLE-HAND
    h = fields.get("handedness", {}).get("value", "").strip().lower()
    if not h or is_placeholder(h):
        F.append(Finding("BIBLE-HAND", P, "handedness not set (left, right or ambidextrous)"))
    elif h.split()[0].strip(",.;:") not in HANDS:
        F.append(Finding("BIBLE-HAND", P, f"handedness {h!r} must start with left, right or ambidextrous"))

    # WORLD-LINK
    wl = fields.get("world", {}).get("value", "")
    worlds = split_csv(wl) if not is_placeholder(wl) else []
    if not worlds:
        F.append(Finding("WORLD-LINK", P, "world not set: every character lives in at least one world"))
    for w in worlds:
        if not (series / "worlds" / f"{w}.md").is_file():
            F.append(Finding("WORLD-LINK", P, f"world {w!r} has no file worlds/{w}.md"))
    return F


# ---------------------------------------------------------------- ensemble

def parse_matrix(text: str) -> tuple[list[str], list[list[str]]] | None:
    lines = strip_comments(text).splitlines()
    for i, ln in enumerate(lines):
        if re.match(r"^\|\s*Character\b", ln, re.I):
            head = [c.strip() for c in ln.strip().strip("|").split("|")]
            rows = []
            for r in lines[i + 1:]:
                if not r.strip().startswith("|"):
                    break
                cells = [c.strip() for c in r.strip().strip("|").split("|")]
                if all(set(c) <= set("-: ") for c in cells):
                    continue
                rows.append(cells)
            return head, rows
    return None


def norm_cell(c: str) -> str:
    m = re.search(r"\[([^\]]+)\]\s*$", c)
    return (m.group(1) if m else c).strip().lower()


def check_ensemble(series: Path, n_chars: int, min_diff: int) -> list[Finding]:
    P = (series / "ensemble-matrix.md").as_posix()
    mp = series / "ensemble-matrix.md"
    if not mp.is_file():
        return [Finding("ENSEMBLE-CONTRAST", P, "ensemble-matrix.md missing")]
    parsed = parse_matrix(mp.read_text(encoding="utf-8"))
    if not parsed:
        return [Finding("ENSEMBLE-CONTRAST", P, "no table with a 'Character' header")]
    head, rows = parsed
    F: list[Finding] = []
    if len(head) < AXES + 2:
        return [Finding("ENSEMBLE-CONTRAST", P, f"table has {len(head)} columns; need Character + {AXES} axes + Tell")]
    rows = [r for r in rows if len(r) >= AXES + 2]
    if len(rows) < 2:
        return [Finding("ENSEMBLE-CONTRAST", P, f"{len(rows)} character row(s); a pair needs at least 2")]
    if n_chars and len(rows) < n_chars:
        F.append(Finding("ENSEMBLE-CONTRAST", P, f"{len(rows)} matrix rows for {n_chars} character folders"))
    empty = [(r[0], head[i]) for r in rows for i in range(1, AXES + 2) if is_placeholder(r[i]) or not r[i]]
    if empty:
        F.append(Finding("ENSEMBLE-CONTRAST", P, "empty cells: " + "; ".join(f"{a}/{b}" for a, b in empty[:8])))
    for a, b in combinations(rows, 2):
        same = [i for i in range(1, AXES + 1) if a[i] and norm_cell(a[i]) == norm_cell(b[i])]
        diff = AXES - len(same)
        if diff < min_diff:
            F.append(Finding("ENSEMBLE-CONTRAST", P,
                             f"{a[0]} / {b[0]} differ on {diff} of {AXES} axes (need >= {min_diff}); same on axes "
                             + ", ".join(map(str, same))))
    for col, name in ((AXES, "extreme trait"), (AXES + 1, "tell")):
        seen: dict[str, str] = {}
        for r in rows:
            k = norm_cell(r[col])
            if k in seen:
                F.append(Finding("ENSEMBLE-CONTRAST", P, f"{seen[k]} and {r[0]} share the same {name}"))
            seen[k] = r[0]
    return F


# ---------------------------------------------------------------- series

def run(series: Path, min_diff: int = 8, only: str | None = None) -> list[Finding]:
    F: list[Finding] = []
    if not series.is_dir():
        return [Finding("BIBLE-LAYOUT", series.as_posix(), "series folder not found")]
    if not (series / "series.md").is_file():
        F.append(Finding("BIBLE-LAYOUT", series.as_posix(), "series.md missing"))
    cdirs = sorted(p for p in (series / "characters").glob("*") if p.is_dir()) if (series / "characters").is_dir() else []
    if only:
        cdirs = [c for c in cdirs if c.name == only]
    if not cdirs:
        F.append(Finding("BIBLE-LAYOUT", series.as_posix(), "no characters/<id>/ folders"))
    req = required_keys()
    for c in cdirs:
        F += check_character(c, series, req)
    if not only:
        F += check_ensemble(series, len(cdirs), min_diff)
    return F


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("series", help="bible/series/<series> folder")
    ap.add_argument("--character", help="check one character id only (skips the ensemble check)")
    ap.add_argument("--min-diff", type=int, default=8, help="axes a pair must differ on (default 8 of 10)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        F = run(Path(a.series).resolve(), a.min_diff, a.character)
    except SystemExit as e:
        print(e, file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps([f.__dict__ for f in F], ensure_ascii=False, indent=1))
    else:
        for f in F:
            print(f.line())
        print("OK" if not F else f"{len(F)} finding(s): " + ", ".join(sorted({f.check for f in F})))
    return 1 if F else 0


if __name__ == "__main__":
    sys.exit(main())
