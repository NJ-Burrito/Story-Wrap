# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""LINE-FIT: does a voiced line fit the slot the plan puts it in? (owner, 2026-10-30: "fix the stopping issue, never stop again", rule R-502)

A scene, the spoken recap, an intro and the choice sequence each have a hard length cap in tools/calm_compose.py (RECAP_MAX_S, MAX_SCENE_S, calm_intro.MAX_S, MAX_CHOICE_S). The cap
is checked by the plan stage, AFTER the voice stage, when the take already exists and a line is voiced once. E04 (2026-10-29) and E05 (2026-10-30) stopped there: the recap
line H01 took 3.88 s against the 3.0 s card. This module is the one place that knows those limits in seconds of SPEECH (the cap minus the lead and the pad the plan adds), and it
serves two jobs:

  PREVENTION (script stage, before any voice is made)   `script_problems(plan, script)` estimates every line's spoken length from its Arabic letters and a straight line (seconds = a + b x letters) fitted
                                                         from the real takes (tools/line_fit_rates.json; `calibrate` rebuilds it), with a safety margin. A line over its slot goes back to
                                                         the writer with its target length. `brief_block()` is the same limits as text for the writer's brief.
  CURE (after voicing, tools/line_refit.py)             `overruns(plan, secs)` finds the lines whose REAL take is over the slot, and `rewrite_target` gives the shorter length the writer
                                                         must hit under a new line id.

    uv run tools/line_fit.py check <episode-dir>          estimate every line of an episode's script against its slot (changes nothing)
    uv run tools/line_fit.py limits                       print the per-slot limits (what the writer's brief carries)
    uv run tools/line_fit.py calibrate [--root DIR] [--write]   measure seconds per letter from the narration manifests under DIR (default: this repo) and write line_fit_rates.json

Standard library only; calm_compose is imported lazily (the numbers live there once). No model, no network, no voice.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

RATES_P = TOOLS / "line_fit_rates.json"
AR_LETTER = re.compile("[ء-غف-يٱ]")
FIT_AIM = 0.90          # a rewrite aims at this share of the slot, so a take that comes out a little slower than the estimate still fits
MIN_LINE_S = 1.2        # a refit never asks for a line shorter than this (a single short phrase)
DEFAULT_RATES = {"margin": 1.0, "model": {"narrator": {"a": 0.54, "b": 0.131}, "dialogue": {"a": 1.53, "b": 0.122}}}     # used only when line_fit_rates.json is missing; the file is the measurement


def letters(tts_text: str) -> int:
    """Arabic letters of the voiced text (tashkeel excluded), the same count voice.letters_of makes."""
    return len(AR_LETTER.findall(tts_text or "")) or len(tts_text or "")


def load_rates(path: Path | None = None) -> dict:
    p = Path(path or RATES_P)
    try:
        j = json.loads(p.read_text(encoding="utf-8"))
        if j.get("model") and j.get("margin"):
            return j
    except (OSError, ValueError):
        pass
    return DEFAULT_RATES


def model_for(speaker: str | None, rates: dict | None = None) -> tuple[float, float, float]:
    """(a, b, margin) of seconds = (a + b * letters) * margin for the narrator or a character. a already carries the slow side (the p90 residual) of the measurements."""
    r = rates or load_rates()
    m = r["model"]["narrator" if speaker == "narrator" else "dialogue"]
    return float(m["a"]), float(m["b"]), float(r["margin"])


def estimate_s(line: dict, rates: dict | None = None) -> float:
    a, b, mg = model_for(line.get("speaker"), rates)
    return round((a + b * letters(line.get("tts_text") or line.get("text", ""))) * mg, 2)


def letters_for(seconds: float, speaker: str | None, rates: dict | None = None) -> int:
    """The most Arabic letters that are estimated to fit `seconds` of speech."""
    a, b, mg = model_for(speaker, rates)
    return max(4, int((seconds / mg - a) / b))


def max_letters(max_s: float, speaker: str | None, rates: dict | None = None) -> int:
    """The letter budget a rewrite is given for a slot of max_s: FIT_AIM of the slot, so a take a little slower than the estimate still fits."""
    return letters_for(max_s * FIT_AIM, speaker, rates)


# ------------------------------------------------------------------ the limits (seconds of speech)
def slot_caps(plan: dict) -> dict:
    """{line id: {slot, ref, max_s}} - the longest take, in seconds, the plan stage accepts for each line. Mirrors calm_compose.stage_plan: a scene lasts
    its line + VOICE_LEAD_S + PAD_S (at least MIN_SCENE_S) and may not pass MAX_SCENE_S; the recap card MAX = RECAP_MAX_S; an intro's line passes calm_intro.MAX_S.
    The four choice lines share one budget (see choice_budget), so each carries that budget as `group_s`."""
    import calm_compose as cc
    import calm_intro
    lead = cc.VOICE_LEAD_S + cc.PAD_S
    caps: dict = {}
    hk = (plan.get("hook") or {}).get("line")
    if hk and cc.recap_expected(plan) and cc.algo_on(plan):
        caps[hk] = {"slot": "recap", "ref": "recap", "max_s": round(cc.RECAP_MAX_S - lead, 2)}
    for s in plan.get("scenes", []):
        if s.get("line"):
            caps[s["line"]] = {"slot": "scene", "ref": s.get("id"), "max_s": round(cc.MAX_SCENE_S - lead, 2)}
    for ix in plan.get("intros", []) or []:
        if ix.get("line"):
            caps[ix["line"]] = {"slot": "intro", "ref": ix.get("id"), "max_s": round(calm_intro.MAX_S - lead, 2)}
    ch = plan.get("choice") or {}
    if ch.get("lines"):
        for role in ("question", "choice1", "choice2", "hook"):
            if ch["lines"].get(role):
                caps[ch["lines"][role]] = {"slot": "choice", "ref": role, "max_s": None, "group_s": choice_budget()}
    return caps


def choice_budget() -> float:
    """The most speech the choice sequence takes: MAX_CHOICE_S minus the lead-in, three gaps and the tail (calm_compose.stage_plan: cdur = JOIN_S + 0.3 + sum + 3 gaps + CHOICE_TAIL_S)."""
    import calm_compose as cc
    return round(cc.MAX_CHOICE_S - (cc.JOIN_S + 0.3) - 3 * cc.CHOICE_GAP_S - cc.CHOICE_TAIL_S, 2)


def choice_ids(plan: dict) -> list[str]:
    ch = (plan.get("choice") or {}).get("lines") or {}
    return [ch[k] for k in ("question", "choice1", "choice2", "hook") if ch.get(k)]


def limits_text(plan: dict | None = None) -> str:
    """The same limits as plain text (for `limits` and for the writer's brief). Rates come from line_fit_rates.json."""
    import calm_compose as cc
    import calm_intro
    lead = cc.VOICE_LEAD_S + cc.PAD_S
    rows = [("the spoken recap (first line, the hook; the narrator's)", cc.RECAP_MAX_S - lead, False), ("a scene line (character or narrator)", cc.MAX_SCENE_S - lead, True),
            ("an intro's narrator line", calm_intro.MAX_S - lead, False)]
    out = [f"{name}: at most {s:.2f} s aloud = about {max_letters(s, 'narrator')} Arabic letters of tts_text" + (f" for the narrator ({max_letters(s, 'hero')} for a character)" if chars else "") for name, s, chars in rows]
    a, b, mg = model_for("narrator")
    total = int((choice_budget() / mg - 4 * a) / b * FIT_AIM)
    out.append(f"the four choice lines TOGETHER (question, both choices, hook): at most {choice_budget():.1f} s aloud = about {total} Arabic letters in all")
    return "\n".join(out)


def brief_block() -> str:
    """The text block the writer's brief carries (daily.WRITER_PROMPT {fit}): the per-slot limits, in seconds and in letters."""
    return ("SLOT LIMITS (R-502; the plan stage refuses a take longer than its slot, and a line is voiced ONCE, so a line that is too long can only be reworded under a new id):\n"
            + limits_text()
            + "\nCount the Arabic letters of tts_text without the vowel marks. The narrator voice speaks about 7 letters a second, characters about 8 (plus a short breath before the first word); the check uses the slow side of the measured takes."
              " A line over its slot is sent back to you before any voice is made.")


# ------------------------------------------------------------------ prevention
def script_problems(plan: dict, script: dict, rates: dict | None = None) -> list[str]:
    """'SCRIPT-FIT ...' findings, one per line that the estimate puts over its slot (a choice line is judged on the whole choice sequence). Empty = every line fits."""
    rates = rates or load_rates()
    caps = slot_caps(plan)
    by_id = {l["id"]: l for l in (script or {}).get("lines", [])}
    out: list[str] = []
    for lid, cap in caps.items():
        ln = by_id.get(lid)
        if ln is None or cap["slot"] == "choice":
            continue
        est = estimate_s(ln, rates)
        if est > cap["max_s"] + 1e-9:
            n, tgt = letters(ln.get("tts_text", "")), max_letters(cap["max_s"], ln.get("speaker"), rates)
            out.append(f"SCRIPT-FIT line {lid} ({cap['slot']} {cap['ref']}): about {est:.1f} s aloud ({n} letters), the slot takes {cap['max_s']:.2f} s: rewrite it in at most {tgt} Arabic letters of tts_text "
                       f"(about {max(2, tgt // 4)} words), same idea, same speaker")
    ids = [i for i in choice_ids(plan) if i in by_id]
    if ids:
        tot = sum(estimate_s(by_id[i], rates) for i in ids)
        budget = choice_budget()
        if tot > budget + 1e-9:
            worst = max(ids, key=lambda i: estimate_s(by_id[i], rates))
            share = max(MIN_LINE_S, estimate_s(by_id[worst], rates) - (tot - budget) - 0.3)
            out.append(f"SCRIPT-FIT choice sequence ({', '.join(ids)}): about {tot:.1f} s aloud in all, the card takes {budget:.1f} s: shorten line {worst} to about {share:.1f} s "
                       f"(at most {letters_for(share, by_id[worst].get('speaker'), rates)} letters) or the others")
    return out


# ------------------------------------------------------------------ cure
def overruns(plan: dict, secs: dict, message: str = "") -> list[dict]:
    """The lines whose REAL take (secs = {line id: seconds of the trimmed take}) is over the slot, by the plan stage's own arithmetic.
    [{line, slot, ref, seconds, max_s, target_s}] longest overrun first. `message` is the PLAN-DURATION text: a scene that only fails with its reading pause
    (calm_compose: MAX_SCENE_S + 1.5) is named there, not computable here, so its id is taken from the text."""
    import calm_compose as cc
    import calm_intro
    caps = slot_caps(plan)
    found: dict = {}
    for lid, cap in caps.items():
        s = secs.get(lid)
        if s is None:
            continue
        if cap["slot"] == "recap":
            over = cc.snap(max(2.5, s + cc.VOICE_LEAD_S + cc.PAD_S)) > cc.RECAP_MAX_S + 1e-9
        elif cap["slot"] == "scene":
            over = cc.snap(max(cc.MIN_SCENE_S, s + cc.VOICE_LEAD_S + cc.PAD_S)) > cc.MAX_SCENE_S + 1e-9
        elif cap["slot"] == "intro":
            over = cc.snap(max(cc.MIN_SCENE_S, s + cc.VOICE_LEAD_S + cc.PAD_S)) > calm_intro.MAX_S + 1e-9
        else:
            continue
        if over:
            found[lid] = {"line": lid, "slot": cap["slot"], "ref": cap["ref"], "seconds": round(s, 2), "max_s": cap["max_s"], "target_s": round(max(MIN_LINE_S, cap["max_s"] * FIT_AIM), 2)}
    m = re.search(r"scene (\S+) would last .* reading pause", message or "")
    if m:
        sc = next((x for x in plan.get("scenes", []) if x.get("id") == m.group(1) and x.get("line")), None)
        if sc and sc["line"] in secs and sc["line"] not in found:
            s = secs[sc["line"]]
            found[sc["line"]] = {"line": sc["line"], "slot": "scene", "ref": sc["id"], "seconds": round(s, 2), "max_s": caps[sc["line"]]["max_s"],
                                 "target_s": round(max(MIN_LINE_S, s - 1.5), 2), "why": "its reading pause pushes the scene past the cap"}
    ids = [i for i in choice_ids(plan) if i in secs]
    if ids:
        tot, budget = sum(secs[i] for i in ids), choice_budget()
        if tot > budget + 1e-9:
            need, rest = tot - budget + 0.3, tot - budget + 0.3
            for i in sorted(ids, key=lambda i: -secs[i]):
                if rest <= 1e-9:
                    break
                take = min(rest, max(0.0, secs[i] - MIN_LINE_S))
                if take > 0:
                    found[i] = {"line": i, "slot": "choice", "ref": caps[i]["ref"], "seconds": round(secs[i], 2), "max_s": round(secs[i] - take, 2),
                                "target_s": round(max(MIN_LINE_S, secs[i] - take), 2), "why": f"the choice sequence is {need - 0.3:.2f} s over its card"}
                    rest -= take
    return sorted(found.values(), key=lambda d: d["seconds"] - d["max_s"], reverse=True)


def rewrite_target(item: dict, speaker: str | None, rates: dict | None = None) -> dict:
    """What the writer is told for one overrun: the seconds and the letter budget of the new line."""
    tgt_s = min(item["target_s"], item["max_s"] * FIT_AIM) if item["slot"] != "choice" else item["target_s"]
    return {"target_s": round(tgt_s, 2), "max_letters": letters_for(tgt_s, speaker, rates)}


def new_line_ok(line: dict, item: dict, rates: dict | None = None) -> str | None:
    """None when the rewritten line is estimated to fit its slot, else the reason (the refit asks again, at most twice per line)."""
    est = estimate_s(line, rates)
    lim = item["max_s"]
    if est > lim + 1e-9:
        return f"about {est:.1f} s aloud, the slot takes {lim:.2f} s"
    return None


# ------------------------------------------------------------------ calibration
def calibrate(root: Path, margin: float = 1.0) -> dict:
    """Seconds as a straight line of Arabic letters, fitted to the real finished takes: the narration manifests under root/bible/series/*/episodes/*/ carry the measured `seconds`
    of each trimmed take and its tts_text. Per group (narrator, characters): least squares seconds = a + b * letters, then `a` is raised by the 90th percentile of the residuals,
    so the line is the slow side of the takes (a per-letter rate over-states long lines: the fixed breath before the first word is spread over more letters)."""
    rows: dict = {"narrator": [], "dialogue": []}
    eps = 0
    for p in sorted(Path(root).glob("bible/series/*/episodes/*/narration-manifest.json")):
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        eps += 1
        for l in m.get("lines", []):
            if l.get("seconds") and l.get("tts_text"):
                rows["narrator" if l.get("speaker") == "narrator" else "dialogue"].append((letters(l["tts_text"]), float(l["seconds"])))
    out = {"version": 2, "margin": margin, "model": {}, "samples": {}, "episodes": eps, "measured": dt.date.today().isoformat(),
           "source": "narration manifests (trimmed take seconds vs Arabic letters of tts_text): seconds = a + b * letters, a raised by the p90 residual; rebuilt by `uv run tools/line_fit.py calibrate --write`"}
    for k, v in rows.items():
        out["samples"][k] = len(v)
        if len(v) < 3 or len({n for n, _ in v}) < 2:
            out["model"][k] = dict(DEFAULT_RATES["model"][k])
            continue
        mx, my = sum(n for n, _ in v) / len(v), sum(t for _, t in v) / len(v)
        b = sum((n - mx) * (t - my) for n, t in v) / sum((n - mx) ** 2 for n, _ in v)
        a = my - b * mx
        res = sorted(t - (a + b * n) for n, t in v)
        shift = res[max(0, min(len(res) - 1, int(len(res) * 0.9) - 1))]
        out["model"][k] = {"a": round(a + max(0.0, shift), 3), "b": round(b, 4)}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="line_fit.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("cmd", choices=["check", "limits", "calibrate"])
    ap.add_argument("episode", nargs="?")
    ap.add_argument("--root", default=str(TOOLS.parent))
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    if a.cmd == "limits":
        print(limits_text())
        return 0
    if a.cmd == "calibrate":
        r = calibrate(Path(a.root))
        print(json.dumps(r, ensure_ascii=False, indent=1))
        if a.write:
            RATES_P.write_text(json.dumps(r, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            print(f"wrote {RATES_P}")
        return 0
    if not a.episode:
        print("episode directory required", file=sys.stderr)
        return 2
    d = Path(a.episode)
    plan, script = json.loads((d / "calm-plan.json").read_text(encoding="utf-8")), json.loads((d / "script.json").read_text(encoding="utf-8"))
    bad = script_problems(plan, script)
    for b in bad:
        print(b)
    print("OK every line fits its slot" if not bad else f"{len(bad)} line(s) over their slot")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
