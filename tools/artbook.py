# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow", "numpy"]
# ///
"""Art book builder and checks (sketch stage; pipelines/ARTBOOK.md).

  uv run tools/artbook.py build [--series DIR] [--html previews/index.html]   assemble the "Art Book" tab (#artbook)
  uv run tools/artbook.py check [--series DIR] [--html ...] [--built-only]    run the four checks below

Checks (exit 1 on any FAIL, 2 on a tool error):
  ARTBOOK-SHEETS  every character of the series has sheets 01-08 and every world its set w1-w4 (rendered by tools/sheets.py)
  ARTBOOK-INK     rendered sheets carry no colour: PNG chroma <= INK_CHROMA_MAX, SVG colours are only black, white and greys
  ARTBOOK-MATCH   drawn proportions match the module, the catalogue character.json and the bible (height in heads, shoulder width,
                  physics/rig profile), and the sheets on disk are the ones the measures were taken from (sha256)
  ARTBOOK-TEXT    every caption in the book traces to a bible line (file + line number, text found in that line)
--built-only checks only the characters/worlds that have a module (the rest are reported PENDING, not failed)."""
from __future__ import annotations
import argparse, hashlib, html as htmllib, json, re, sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
DEFAULT_SERIES = ROOT / "bible" / "series" / "series"
DEFAULT_HTML = ROOT / "previews" / "index.html"
CHAR_SHEETS = ["01-shapes", "02-mannequin", "03-sketch", "04-turnaround", "05-expressions", "06-hands-grips", "07-face", "08-props"]
WORLD_SHEETS = ["w1-establishing", "w2-locations", "w3-props", "w4-materials"]
CORE_EMOTIONS = ["calm", "joy", "sadness", "fear", "anger", "surprise", "disgust", "shame"]
INK_CHROMA_MAX = 8            # of 255: max(R,G,B) - min(R,G,B) over every pixel of a rendered sheet
MATCH_TOL = 0.02              # R-344: drawn lengths within 2 % of the recorded ones
CAP_MAX = 120                 # characters in a caption before it is cut at a word boundary


def F(cid: str, msg: str) -> str:
    return f"FAIL [{cid}] {msg}"


# ------------------------------------------------------------------ bible reading (the only source of caption text)
COMMENT = re.compile(r"<!--.*?-->")
FIELD_RE = re.compile(r"^\s*-\s+([a-z][a-z0-9_]*):\s*(.*)$")


def clean(s: str) -> str:
    s = COMMENT.sub("", s)
    s = s.replace("**", "").replace("`", "")
    s = re.sub(r"^\s*(#+|-|\d+\.)\s+", "", s)
    return re.sub(r"\s+", " ", s).strip()


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", clean(s).rstrip("…").strip())


def read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def bible_fields(path: Path) -> dict:
    """{'fields': {key: (line_no, cleaned value)}, 'emotions': {name: {key: (line_no, value)}}, 'bullets': {parent_key: [(line_no, text)]}}"""
    out = {"fields": {}, "emotions": {}, "bullets": {}}
    cur_emotion = None
    parent = None
    for i, raw in enumerate(read_lines(path), 1):
        m = re.match(r"^###\s+emotion:\s*([A-Za-z-]+)\s*$", raw)
        if m:
            cur_emotion = out["emotions"].setdefault(m.group(1).lower(), {})
            parent = None
            continue
        if raw.startswith("#"):
            cur_emotion = None
            parent = None
            continue
        fm = FIELD_RE.match(raw)
        if fm and not raw.startswith("  "):
            key, val = fm.group(1), clean(fm.group(2))
            if cur_emotion is not None:
                cur_emotion[key] = (i, val)
            else:
                out["fields"][key] = (i, val)
                parent = key
            continue
        if parent and raw.startswith("  - "):
            out["bullets"].setdefault(parent, []).append((i, clean(raw)))
    return out


def first_sentence(text: str, limit: int = CAP_MAX) -> str:
    t = text.strip()
    m = re.search(r"[.!؟?](?:\s|$)", t)
    if m:
        t = t[:m.end()].strip()
    if len(t) > limit:
        cut = t[:limit].rsplit(" ", 1)[0].rstrip(",;:- ")
        t = cut + "…"
    return t


def cap(file: Path, line: int, text: str, root: Path) -> dict:
    try:
        rel = file.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        rel = file.as_posix()
    return {"text": text, "source": {"file": rel, "line": line}}


# ------------------------------------------------------------------ what exists
def series_chars(series: Path) -> list[str]:
    d = series / "characters"
    return sorted(p.name for p in d.iterdir() if (p / "bible.md").is_file()) if d.is_dir() else []


def series_worlds(series: Path) -> list[str]:
    d = series / "worlds"
    return sorted(p.stem for p in d.glob("*.md")) if d.is_dir() else []


def version_key(p: Path) -> int:
    m = re.match(r"v(\d+)$", p.parent.parent.name)
    return int(m.group(1)) if m else -1


def find_char_sheets(root: Path, cid: str) -> Path | None:
    c = sorted((root / "catalogue" / "characters" / cid).glob("v*/sheets/sheets.json"), key=version_key)
    return c[-1] if c else None


def find_world_sheets(root: Path, world: str) -> Path | None:
    c = []
    for p in sorted((root / "catalogue" / "environments").glob("*/v*/sheets/sheets.json"), key=version_key):
        try:
            if json.loads(p.read_text(encoding="utf-8")).get("module_summary", {}).get("bible_world") == world:
                c.append(p)
        except (OSError, ValueError):
            continue
    return c[-1] if c else None


def has_module(root: Path, kind: str, mid: str) -> bool:
    return (root / "tools" / "render" / ("characters" if kind == "character" else "worlds") / f"{mid}.js").is_file()


def world_modules(root: Path) -> dict[str, str]:
    """bible_world -> module id, read from the module sources (no browser needed)."""
    out = {}
    d = root / "tools" / "render" / "worlds"
    for p in d.glob("*.js") if d.is_dir() else []:
        m = re.search(r"bible_world:\s*\"([a-z0-9-]+)\"", p.read_text(encoding="utf-8"))
        if m:
            out[m.group(1)] = p.stem
    return out


def load_meta(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ checks
def check_sheets(root: Path, series: Path, built_only: bool = False) -> tuple[list[str], list[str]]:
    fails, pending = [], []
    for cid in series_chars(series):
        meta = find_char_sheets(root, cid)
        if meta is None:
            if built_only and not has_module(root, "character", cid):
                pending.append(f"PENDING {cid}: no character module yet")
            elif has_module(root, "character", cid):
                fails.append(F("ARTBOOK-SHEETS", f"character '{cid}' has a module but no rendered sheets: run tools/sheets.py character {cid}"))
            else:
                fails.append(F("ARTBOOK-SHEETS", f"character '{cid}' has no module and no sheets: an Opus artist builds tools/render/characters/{cid}.js"))
            continue
        m = load_meta(meta)
        have = {s["id"]: s for s in m.get("sheets", [])}
        for sid in CHAR_SHEETS:
            s = have.get(sid)
            if not s:
                fails.append(F("ARTBOOK-SHEETS", f"character '{cid}' lacks sheet {sid}"))
                continue
            for k in ("svg", "png"):
                if not s.get(k) or not (meta.parent / s[k]).is_file():
                    fails.append(F("ARTBOOK-SHEETS", f"character '{cid}' sheet {sid}: {k} file missing ({s.get(k)})"))
    wm = world_modules(root)
    for w in series_worlds(series):
        meta = find_world_sheets(root, w)
        if meta is None:
            if built_only and w not in wm:
                pending.append(f"PENDING {w}: no world module yet")
            else:
                fails.append(F("ARTBOOK-SHEETS", f"world '{w}' has no rendered sheet set ({'run tools/sheets.py world ' + wm[w] if w in wm else 'an Opus artist builds a tools/render/worlds/<id>.js with bible_world: ' + w})"))
            continue
        m = load_meta(meta)
        have = {s["id"]: s for s in m.get("sheets", [])}
        for sid in WORLD_SHEETS:
            s = have.get(sid)
            if not s:
                fails.append(F("ARTBOOK-SHEETS", f"world '{w}' lacks sheet {sid}"))
                continue
            for k in ("svg", "png"):
                if not s.get(k) or not (meta.parent / s[k]).is_file():
                    fails.append(F("ARTBOOK-SHEETS", f"world '{w}' sheet {sid}: {k} file missing ({s.get(k)})"))
    return fails, pending


_COL_ATTR = re.compile(r"""(?:fill|stroke|stop-color|flood-color|color)\s*[=:]\s*["']?\s*(#[0-9a-fA-F]{3,8}|rgba?\([^)]*\)|hsla?\([^)]*\)|[a-zA-Z]+)""")
_NEUTRAL_NAMES = {"none", "white", "black", "transparent", "currentcolor", "inherit", "evenodd", "nonzero", "round", "butt", "square", "middle", "start", "end", "bold", "normal", "miter"}


def colour_is_grey(tok: str) -> bool:
    t = tok.strip().lower()
    if t in _NEUTRAL_NAMES or t.startswith("url("):
        return True
    if t.startswith("#"):
        h = t[1:]
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h)
        if len(h) in (6, 8):
            r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
            return max(r, g, b) - min(r, g, b) <= INK_CHROMA_MAX
        return False
    m = re.match(r"rgba?\(\s*([\d.]+)[ ,]+([\d.]+)[ ,]+([\d.]+)", t)
    if m:
        v = [float(x) for x in m.groups()]
        return max(v) - min(v) <= INK_CHROMA_MAX
    if t.startswith("hsl"):
        m = re.match(r"hsla?\(\s*[\d.]+[ ,]+([\d.]+)%", t)
        return bool(m) and float(m.group(1)) <= 3
    return False   # an unknown colour name (red, teal, ...) is colour


def svg_colour_fails(svg: str) -> list[str]:
    bad = set()
    for m in _COL_ATTR.finditer(svg):
        tok = m.group(1)
        if tok.lower() in ("fill", "stroke") or not tok:
            continue
        if not colour_is_grey(tok):
            # names such as font-family values are matched only after fill=/stroke=/color=, so a non-grey here is a real colour
            bad.add(tok)
    return sorted(bad)


def png_chroma_max(path: Path) -> int:
    from PIL import Image
    import numpy as np
    im = Image.open(path)
    if im.mode in ("L", "LA", "1", "I;16", "I"):
        return 0
    a = np.asarray(im.convert("RGB"), dtype=np.int16)
    return int((a.max(axis=2) - a.min(axis=2)).max())


def sheet_dirs(root: Path, series: Path, built_only: bool) -> list[tuple[str, Path]]:
    out = []
    for cid in series_chars(series):
        p = find_char_sheets(root, cid)
        if p:
            out.append((f"character '{cid}'", p))
    for w in series_worlds(series):
        p = find_world_sheets(root, w)
        if p:
            out.append((f"world '{w}'", p))
    return out


def check_ink(root: Path, series: Path, built_only: bool = False) -> list[str]:
    fails = []
    for label, meta in sheet_dirs(root, series, built_only):
        m = load_meta(meta)
        for s in m.get("sheets", []):
            if s.get("svg") and (meta.parent / s["svg"]).is_file():
                bad = svg_colour_fails((meta.parent / s["svg"]).read_text(encoding="utf-8"))
                if bad:
                    fails.append(F("ARTBOOK-INK", f"{label} sheet {s['id']}: SVG has colour {', '.join(bad[:5])} (ink is black, white and greys only)"))
            if s.get("png") and (meta.parent / s["png"]).is_file():
                c = png_chroma_max(meta.parent / s["png"])
                if c > INK_CHROMA_MAX:
                    fails.append(F("ARTBOOK-INK", f"{label} sheet {s['id']}: PNG chroma {c} > {INK_CHROMA_MAX}"))
    return fails


def _num(s: str | None) -> float | None:
    m = re.search(r"\d+(?:\.\d+)?", s or "")
    return float(m.group(0)) if m else None


def _close(a: float, b: float, tol: float = MATCH_TOL) -> bool:
    return abs(a - b) <= tol * max(abs(b), 1e-9)


def check_match(root: Path, series: Path, built_only: bool = False) -> list[str]:
    fails = []
    for cid in series_chars(series):
        meta = find_char_sheets(root, cid)
        if not meta:
            continue
        m = load_meta(meta)
        mod = m.get("module_summary", {})
        prop = mod.get("proportions_hu", {})
        meas = m.get("measures", {})
        lab = f"character '{cid}'"
        # 1 the sheets on disk are the ones that were measured
        for s in m.get("sheets", []):
            f = meta.parent / s.get("svg", "")
            if f.is_file() and "svg_sha" in s and "sha256:" + hashlib.sha256(f.read_bytes()).hexdigest()[:16] != s["svg_sha"]:
                fails.append(F("ARTBOOK-MATCH", f"{lab} sheet {s['id']}: the SVG changed since it was measured; re-run tools/sheets.py character {cid}"))
        # 2 drawn == module
        for k, v in meas.items():
            if k in prop and isinstance(v, (int, float)) and not _close(v, prop[k]):
                fails.append(F("ARTBOOK-MATCH", f"{lab}: drawn {k} = {v} HU but the module says {prop[k]} (> {MATCH_TOL:.0%})"))
        if not any(k in meas for k in ("height", "shoulder_w")):
            fails.append(F("ARTBOOK-MATCH", f"{lab}: sheets.json carries no drawn height or shoulder width"))
        # 3 module == catalogue character.json
        cj = root / "catalogue" / "characters" / cid / "character.json"
        if cj.is_file():
            ch = json.loads(cj.read_text(encoding="utf-8")).get("proportions_hu", {})
            for k, v in ch.items():
                if k in prop and not _close(prop[k], v):
                    fails.append(F("ARTBOOK-MATCH", f"{lab}: module {k} = {prop[k]} but catalogue character.json says {v}"))
        else:
            fails.append(F("ARTBOOK-MATCH", f"{lab}: catalogue/characters/{cid}/character.json missing"))
        # 4 module == bible
        bp = series / "characters" / cid / "bible.md"
        if bp.is_file():
            b = bible_fields(bp)
            h = _num(b["fields"].get("height_head_units", (0, ""))[1])
            if h is None:
                fails.append(F("ARTBOOK-MATCH", f"{lab}: bible has no height_head_units"))
            else:
                for src, v in (("module", prop.get("height")), ("drawn", meas.get("height"))):
                    if v is not None and not _close(v, h):
                        fails.append(F("ARTBOOK-MATCH", f"{lab}: {src} height {v} heads but the bible says {h}"))
            txt = bp.read_text(encoding="utf-8")
            sm = re.search(r"([\d.]+) head units wide", txt)
            if sm and prop.get("shoulder_w") is not None and not _close(prop["shoulder_w"], float(sm.group(1))):
                fails.append(F("ARTBOOK-MATCH", f"{lab}: module shoulder_w {prop['shoulder_w']} but the bible says {sm.group(1)} head units wide"))
            prof = mod.get("physics_profile")
            if prof and prof not in txt:
                fails.append(F("ARTBOOK-MATCH", f"{lab}: rig profile '{prof}' is not named in the bible"))
            pj = root / "catalogue" / "characters" / cid / "physics.json"
            if prof and pj.is_file() and json.loads(pj.read_text(encoding="utf-8")).get("id") != prof:
                fails.append(F("ARTBOOK-MATCH", f"{lab}: module physics_profile '{prof}' != catalogue physics.json id"))
    return fails


DATA_RE = re.compile(r'<script type="application/json" id="artbook-data">(.*?)</script>', re.S)
CAPEL_RE = re.compile(r"<(\w+)([^>]*)>(.*?)</\1>", re.S)


def check_text(root: Path, html_path: Path) -> list[str]:
    fails = []
    if not html_path.is_file():
        return [F("ARTBOOK-TEXT", f"{html_path} not found")]
    page = html_path.read_text(encoding="utf-8")
    m = DATA_RE.search(page)
    if not m:
        return [F("ARTBOOK-TEXT", "no artbook-data block: run tools/artbook.py build")]
    data = json.loads(m.group(1))
    caps = data.get("captions", {})
    cache: dict[str, list[str]] = {}
    for cid, c in caps.items():
        src = c.get("source") or {}
        f, ln = src.get("file"), src.get("line")
        if not f or not isinstance(ln, int):
            fails.append(F("ARTBOOK-TEXT", f"caption {cid}: no source file and line"))
            continue
        p = root / f
        if not p.is_file():
            fails.append(F("ARTBOOK-TEXT", f"caption {cid}: source {f} does not exist"))
            continue
        lines = cache.setdefault(f, read_lines(p))
        if ln < 1 or ln > len(lines):
            fails.append(F("ARTBOOK-TEXT", f"caption {cid}: {f}:{ln} is out of range"))
            continue
        if norm(c.get("text", "")) not in norm(lines[ln - 1]) or not norm(c.get("text", "")):
            fails.append(F("ARTBOOK-TEXT", f"caption {cid} does not trace to {f}:{ln}: '{c.get('text', '')[:60]}'"))
    # every captioned element in the panel is data-driven
    panel = page[page.find('id="panel-artbook"'):] if 'id="panel-artbook"' in page else ""
    end = panel.find("<!--ARTBOOK_PANEL_END-->")
    panel = panel[:end] if end > 0 else panel
    shown = set()
    for em in re.finditer(r"<(\w+)([^>]*(?:data-cap|ab-cap)[^>]*)>(.*?)</\1>", panel, re.S):
        attrs, inner = em.group(2), em.group(3)
        has_cls = re.search(r'class="[^"]*\bab-cap\b', attrs)
        dm = re.search(r'data-cap="([^"]+)"', attrs)
        if dm:
            shown.add(dm.group(1))
            if dm.group(1) not in caps:
                fails.append(F("ARTBOOK-TEXT", f"element data-cap={dm.group(1)} has no entry in artbook-data"))
            elif htmllib.unescape(re.sub(r"<[^>]+>", "", inner)).strip() != caps[dm.group(1)]["text"]:
                fails.append(F("ARTBOOK-TEXT", f"element data-cap={dm.group(1)} shows text that differs from its caption"))
        elif has_cls:
            fails.append(F("ARTBOOK-TEXT", f"a caption element has no data-cap (text '{re.sub('<[^>]+>', '', inner)[:40]}'): it traces to no bible line"))
    return fails


def run_checks(root: Path, series: Path, html_path: Path, built_only: bool, log=print) -> int:
    fs, pending = check_sheets(root, series, built_only)
    allf = fs + check_ink(root, series, built_only) + check_match(root, series, built_only) + check_text(root, html_path)
    for p in pending:
        log(p)
    for f in allf:
        log(f)
    ids = ["ARTBOOK-SHEETS", "ARTBOOK-INK", "ARTBOOK-MATCH", "ARTBOOK-TEXT"]
    for i in ids:
        n = sum(1 for f in allf if f"[{i}]" in f)
        log(f"{'FAIL' if n else 'PASS'} {i}" + (f" ({n})" if n else ""))
    return 1 if allf else 0


# ------------------------------------------------------------------ build
def crop_css(url: str, page: tuple[int, int], r: list[float]) -> str:
    W, H = page
    x, y, w, h = r
    bw = W / w * 100
    px = 0 if W == w else x / (W - w) * 100
    py = 0 if H == h else y / (H - h) * 100
    return f'style="--ar:{w:.0f}/{h:.0f};background-image:url(\'{url}\');background-size:{bw:.2f}% auto;background-position:{px:.2f}% {py:.2f}%"'


def esc(s: str) -> str:
    return htmllib.escape(s, quote=True)


class Book:
    def __init__(self, root: Path):
        self.root, self.caps, self.n = root, {}, 0

    def cap(self, file: Path, line: int, text: str, kind: str = "ab-cap", tag: str = "p") -> str:
        self.n += 1
        cid = f"c{self.n:03d}"
        self.caps[cid] = cap(file, line, text, self.root)
        return f'<{tag} class="{kind}" data-cap="{cid}">{esc(text)}</{tag}>'


def rel_url(root: Path, p: Path) -> str:
    return "../" + p.resolve().relative_to(root.resolve()).as_posix()


def char_spread(bk: Book, root: Path, series: Path, cid: str, meta_p: Path) -> str:
    m = load_meta(meta_p)
    sh = {s["id"]: s for s in m["sheets"]}
    page = (m["page"]["w"], m["page"]["h"])
    bp = series / "characters" / cid / "bible.md"
    b = bible_fields(bp)
    fl = b["fields"]
    mod = m.get("module_summary", {})

    def png(sid):
        return rel_url(root, meta_p.parent / sh[sid]["png"])

    def region(sid, key):
        return sh[sid].get("regions", {}).get(key)

    def crop(sid, key, label, cls=""):
        r = region(sid, key)
        if not r:
            return f'<figure class="ab-panel"><img src="{png(sid)}" alt="{esc(label)}" loading="lazy"></figure>'
        return f'<figure class="ab-panel {cls}"><div class="ab-crop" role="img" aria-label="{esc(label)}" {crop_css(png(sid), page, r)}></div></figure>'

    name_line, name_val = fl.get("name", (0, ""))
    title_ar = m.get("module_summary", {}).get("name_ar") or name_val.split("/")[0].strip()
    trait = fl.get("extreme_trait", (0, ""))
    out = [f'<article class="ab-spread" id="ab-{cid}">',
           f'<header class="ab-head"><p class="ab-kick">🧑‍🎨 Character</p><h2 class="ab-title ar" dir="rtl" lang="ar">{esc(title_ar)}</h2>']
    if name_line:
        out.append(bk.cap(bp, name_line, first_sentence(name_val), "ab-cap ab-sub"))
    out.append("</header><div class=\"ab-pages\"><div class=\"ab-page ab-left\">")
    out.append('<span class="ab-tag">A · Hero</span>' + crop("04-turnaround", "front", f"{cid} hero plate, front view", "ab-hero"))
    out.append('<div class="ab-block"><span class="ab-tag">E · Who</span>')
    for key, emoji in (("age", "🎂"), ("origin", "🌍"), ("extreme_trait", "⚡")):
        if key in fl:
            out.append(f'<div class="ab-line"><span class="ab-emo">{emoji}</span>' + bk.cap(bp, fl[key][0], first_sentence(fl[key][1]), "ab-cap", "span") + "</div>")
    out.append("</div>")
    out.append('<span class="ab-tag">F · Shape notes</span>' + crop("01-shapes", "figure", f"{cid} shape notes"))
    if "silhouette_note" in fl:
        out.append(bk.cap(bp, fl["silhouette_note"][0], first_sentence(fl["silhouette_note"][1])))
    out.append('</div><div class="ab-page ab-right">')
    out.append('<span class="ab-tag">B · Turnaround</span>' + f'<figure class="ab-panel"><img src="{png("04-turnaround")}" alt="{esc(cid)} turnaround: front, three-quarter, side, back" loading="lazy"></figure>')
    out.append('<span class="ab-tag">C · Head study</span><div class="ab-heads">')
    for emo in mod.get("head_study", ["calm", "shame", "surprise"]):
        e = b["emotions"].get(emo, {})
        out.append('<div class="ab-head1">' + crop("05-expressions", emo, f"{cid} expression: {emo}") + f'<b class="ab-emo-name">{esc(emo)}</b>')
        if "leak" in e:
            out.append(bk.cap(bp, e["leak"][0], first_sentence(e["leak"][1], 90)))
        out.append("</div>")
    out.append("</div>")
    out.append('<span class="ab-tag">D · Props</span>' + f'<figure class="ab-panel"><img src="{png("08-props")}" alt="{esc(cid)} props and signature objects" loading="lazy"></figure>')
    out.append("<ul class=\"ab-props\">")
    for ln, txt in b["bullets"].get("props_carried", [])[:3]:
        label = re.split(r"[(.]", txt, maxsplit=1)[0].strip()
        out.append("<li>" + bk.cap(bp, ln, label, "ab-cap", "span") + "</li>")
    out.append("</ul></div></div>")
    out.append('<details class="ab-all"><summary>📚 All 8 sheets, full size</summary><div class="ab-sheets">')
    for sid in CHAR_SHEETS:
        out.append(f'<figure class="ab-panel"><img src="{png(sid)}" alt="{esc(cid)} sheet {sid}" loading="lazy"><figcaption class="ab-fig">{sid}</figcaption></figure>')
    out.append("</div></details></article>")
    return "".join(out)


def world_spread(bk: Book, root: Path, series: Path, wid: str, meta_p: Path) -> str:
    m = load_meta(meta_p)
    sh = {s["id"]: s for s in m["sheets"]}
    bp = series / "worlds" / f"{wid}.md"
    lines = read_lines(bp)

    def png(sid):
        return rel_url(root, meta_p.parent / sh[sid]["png"])

    def find(pat: str):
        for i, l in enumerate(lines, 1):
            if re.search(pat, l):
                return i, clean(l)
        return 0, ""

    out = [f'<article class="ab-spread ab-world" id="ab-{wid}"><header class="ab-head"><p class="ab-kick">🗺️ World</p>']
    ti, tt = find(r"^# ")
    if ti:
        out.append(bk.cap(bp, ti, tt, "ab-cap ab-title ar", "h2"))
    out.append('</header><div class="ab-pages"><div class="ab-page ab-left">')
    out.append('<span class="ab-tag">A · Establishing</span>' + f'<figure class="ab-panel"><img src="{png("w1-establishing")}" alt="{esc(wid)} establishing view" loading="lazy"></figure>')
    out.append('<div class="ab-block"><span class="ab-tag">E · Place</span>')
    for pat, emoji in ((r"^- \*\*Location and neighbours", "📍"), (r"^- \*\*Story function", "🎯"), (r"^- \*\*The one feature", "🧵")):
        i, t = find(pat)
        if i:
            body = re.sub(r"^[^.]*\.\s*", "", t) if "Location" in t[:30] or "one feature" in t[:40] else re.sub(r"^Story function:\s*", "", t)
            out.append(f'<div class="ab-line"><span class="ab-emo">{emoji}</span>' + bk.cap(bp, i, first_sentence(body), "ab-cap", "span") + "</div>")
    out.append("</div></div><div class=\"ab-page ab-right\">")
    out.append('<span class="ab-tag">B · Key places</span>' + f'<figure class="ab-panel"><img src="{png("w2-locations")}" alt="{esc(wid)} key locations" loading="lazy"></figure>')
    out.append('<span class="ab-tag">C · Materials</span>' + f'<figure class="ab-panel"><img src="{png("w4-materials")}" alt="{esc(wid)} materials" loading="lazy"></figure>')
    out.append('<span class="ab-tag">D · Culture cues</span>' + f'<figure class="ab-panel"><img src="{png("w3-props")}" alt="{esc(wid)} props" loading="lazy"></figure>')
    out.append("</div></div></article>")
    return "".join(out)


def pending_card(kind: str, mid: str, root: Path) -> str:
    need = ("module + 8 sheets (shapes, mannequin, sketch, turnaround, 8 emotions, hands, face, props)" if kind == "character"
            else "module + 4 sheets (establishing, key places, props, materials)")
    return (f'<article class="ab-spread ab-pending" id="ab-{esc(mid)}"><header class="ab-head"><p class="ab-kick">{"🧑‍🎨" if kind == "character" else "🗺️"} {kind.title()}</p>'
            f'<h2 class="ab-title">{esc(mid)}</h2></header><p class="ab-wait">⏳ Not drawn yet. Needs an Opus artist: {need}. See pipelines/ARTBOOK.md.</p></article>')


CSS = """/*ARTBOOK_CSS_BEGIN*/
.ab-wrap{--paper:#fffefb;--ink:#111;max-width:1280px;margin:0 auto;padding:24px 16px 64px}
.ab-spread{margin:0 0 56px;padding:18px;background:var(--paper);color:var(--ink);border:4px solid var(--ink);border-radius:6px;box-shadow:8px 8px 0 var(--ink)}
.ab-head{display:flex;flex-wrap:wrap;gap:6px 18px;align-items:baseline;border-bottom:4px solid var(--ink);margin:0 0 16px;padding:0 0 10px}
.ab-kick{margin:0;font-weight:900;letter-spacing:.06em;text-transform:uppercase;font-size:14px}
.ab-title{margin:0;font-family:"thmanyahserifdisplay",serif;font-weight:900;font-size:clamp(40px,7vw,84px);line-height:1.15}
.ab-sub{margin:0;font-size:18px}
.ab-pages{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,520px),1fr));gap:18px}
.ab-page{display:flex;flex-direction:column;gap:12px;min-width:0}
.ab-tag{align-self:flex-start;background:var(--ink);color:var(--paper);font-weight:700;font-size:13px;padding:2px 10px;border-radius:2px}
.ab-panel{margin:0;border:3px solid var(--ink);background:#fff;overflow:hidden}
.ab-panel img{display:block;width:100%;height:auto}
.ab-hero{max-width:340px;align-self:center}.ab-crop{width:100%;aspect-ratio:var(--ar);background-repeat:no-repeat}
.ab-block{border:3px solid var(--ink);padding:10px 14px;display:flex;flex-direction:column;gap:6px}
.ab-line{display:flex;gap:10px;align-items:baseline;font-size:18px}
.ab-emo{font-size:22px}
.ab-cap{margin:0;font-size:16px;line-height:1.5}
.ab-heads{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.ab-head1{display:flex;flex-direction:column;gap:4px;min-width:0}
.ab-emo-name{font-family:"thmanyahserifdisplay",serif;font-size:20px;text-transform:capitalize}
.ab-props{list-style:none;margin:0;padding:0;display:flex;flex-wrap:wrap;gap:8px}
.ab-props li{border:2px solid var(--ink);padding:2px 10px;border-radius:999px}
.ab-all{margin-top:18px}.ab-all summary{cursor:pointer;font-weight:700;font-size:18px;min-height:44px;display:flex;align-items:center}
.ab-sheets{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,520px),1fr));gap:14px;margin-top:10px}
.ab-fig{font-size:13px;padding:4px 8px;border-top:3px solid var(--ink)}
.ab-pending{border-style:dashed;box-shadow:none;padding:10px 18px}.ab-pending .ab-title{font-size:32px}.ab-pending .ab-head{border:0;margin:0}.ab-wait{margin:0;font-size:18px}
@media (prefers-color-scheme:dark){.ab-spread{box-shadow:8px 8px 0 #000}}
/*ARTBOOK_CSS_END*/"""


def build(root: Path, series: Path, html_path: Path, log=print) -> int:
    bk = Book(root)
    spreads = []
    for cid in series_chars(series):
        mp = find_char_sheets(root, cid)
        spreads.append(char_spread(bk, root, series, cid, mp) if mp else pending_card("character", cid, root))
    for wid in series_worlds(series):
        mp = find_world_sheets(root, wid)
        spreads.append(world_spread(bk, root, series, wid, mp) if mp else pending_card("world", wid, root))
    spreads.sort(key=lambda s: "ab-pending" in s)   # drawn spreads first
    n_done = sum(1 for s in spreads if "ab-pending" not in s)
    data = json.dumps({"series": series.name, "captions": bk.caps}, ensure_ascii=False)
    panel = ('<!--ARTBOOK_PANEL_BEGIN-->\n<section class="panel" id="panel-artbook" data-tab="artbook" hidden>\n<main class="ab-wrap">\n'
             '<p class="hook">🖋️ The Art Book</p>\n<p class="sub">✒️ Black ink only. Built from the character and world modules, captions straight from the bibles.</p>\n'
             f'<p class="sub">📖 {n_done} of {len(spreads)} spreads drawn. Grey dashed cards are still waiting for an artist.</p>\n'
             + "\n".join(spreads) + f'\n<script type="application/json" id="artbook-data">{data}</script>\n</main>\n</section>\n<!--ARTBOOK_PANEL_END-->')
    page = html_path.read_text(encoding="utf-8")
    page = re.sub(r"<!--ARTBOOK_PANEL_BEGIN-->.*?<!--ARTBOOK_PANEL_END-->\n?", "", page, flags=re.S)
    anchor = '<section class="panel" id="panel-cast"'
    if anchor not in page:
        log("FAIL [ARTBOOK-BUILD] previews page has no cast panel anchor"); return 2
    page = page.replace(anchor, panel + "\n" + anchor, 1)
    page = re.sub(r"/\*ARTBOOK_CSS_BEGIN\*/.*?/\*ARTBOOK_CSS_END\*/\n?", "", page, flags=re.S)
    page = page.replace("</style>", CSS + "\n</style>", 1)
    if 'id: "artbook"' not in page:
        page = page.replace('  {id: "hero",', '  {id: "artbook", emoji: "🖋️", label: "Art Book"},\n  {id: "hero",', 1)
    html_path.write_text(page, encoding="utf-8")
    log(f"OK art book: {n_done}/{len(spreads)} spreads, {len(bk.caps)} captions -> {html_path.relative_to(root).as_posix() if html_path.is_relative_to(root) else html_path}#artbook")
    return 0


def heal_stage(root: Path, series: Path, html_path: Path, built_only: bool) -> int:
    """OPTIONAL heal stage (pipelines/HEAL.md): run the checks, keep their output in work/artbook/gate/artbook.out, then let
    tools/heal.py classify the faults and write the critic and fix briefs. Exit 0 only when ready to show the owner."""
    import heal
    lines: list[str] = []
    run_checks(root, series, html_path, built_only, log=lambda m: (lines.append(str(m)), print(m)))
    out = root / "work" / "artbook" / "gate"
    out.mkdir(parents=True, exist_ok=True)
    (out / "artbook.out").write_text("\n".join(lines) + "\n", encoding="utf-8")
    res = heal.prepare(root / "work" / "artbook", "artbook", root)
    return 0 if res is None or res["ready_for_owner"] else 1


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=["build", "check", "heal"])
    ap.add_argument("--series", type=Path, default=DEFAULT_SERIES)
    ap.add_argument("--html", type=Path, default=DEFAULT_HTML)
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--built-only", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "build":
        return build(a.root, a.series, a.html)
    if a.cmd == "heal":
        return heal_stage(a.root, a.series, a.html, a.built_only)
    return run_checks(a.root, a.series, a.html, a.built_only)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
