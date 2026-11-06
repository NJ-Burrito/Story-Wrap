"""tools/cap_heal.py - a caption plate with no place on screen is cut in two, not parked (R-506, the owner 2026-10-30: "never stop, never need him to ask").

The E05 case: L13 «يد؟ أري! (يا للعجب) يد تدخل مكتبي بلا أجرة!» (7 words: three sentences that cap_sentence.split_units merged because the first two are brief and one carries a gloss) was
drawn as ONE plate of 891 x 380 px. While it was up (77.50 to 77.91 s) Guide's close-up filled the picture and cap_face.place_plate found no position outside his face in the safe area
(CAP-FACE-CLEAR); the stop said "shorten the sentence or split it" and nothing did either. The positions are already exhausted by the placement (it scans the whole safe area), so the cure
is a smaller plate:

  rung 1  CUT   the failing unit is cut at one more sentence end (else clause end, else the middle of the sentence) inside it: work/daily/<ep>/cap-heal.json {"lines": {line: {"cuts": [i]}}} (a boundary after display word i;
                calm_compose.caption_states passes it to cap_sentence.split_units as `forced`, so neither the merge of brief sentences nor the gloss merge undoes it). The gloss of a foreign
                word stays with the sentence that has the word, so «(يا للعجب)» ends up on its own, smaller plate. The cut is an INPUT of the animatic and compose stages, so both run again;
                the animatic judges the new plates (CAP-READING-SPEED / CAP-READ-TIME, and read_heal gives a brief first or last plate its lead / hold) before compose draws them.
  rung 2  REFIT no cut is left in the unit (a single word) or the cut rounds are spent: the line is reworded SHORTER under a new id and voiced once (tools/line_refit.py,
                R-502, forced item), the plan runs again.
  then    the stop stays (`exhausted` in cap-heal.json) and the autopilot's fixer takes it (R-506).

Handled codes: CAP-FACE-CLEAR and CAP-SAFE (compose), CALM-PLATE-SAFE (animatic): a plate that is too big for where it must go. The timing codes (CALM-ONE-PLATE, ANI-CAP-WINDOW) are the plan's
and are not cut here: the fixer takes them.

Bounds: HEAL_CALLS cut passes inside one `daily.py run`, MAX_ROUNDS cuts per episode, MAX_REFITS rewrites per episode (line_refit adds its own per-line bound). Nothing is loosened: the same
checks judge every new plate. Every heal is one lessons-ledger entry (kb/lessons/ledger.jsonl, source `cap-heal`).
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

IDS = ("CAP-FACE-CLEAR", "CAP-SAFE", "CALM-PLATE-SAFE")
HEAL_CALLS = 3            # cut passes inside one `daily.py run`
MAX_ROUNDS = 5            # cuts per episode in total (cap-heal.json `rounds`)
MAX_REFITS = 2            # line rewrites this heal asks for per episode (line_refit bounds the rounds of one line again)
ESTIMATE_MARGIN_S = 0.35  # the share-of-the-take estimate of a plate's time is optimistic (E05 L13: 1.68 s estimated, 1.36 s measured); a part must clear its need by this much
REFIT_SHARE = 0.65        # the rewrite aims at this share of the voiced take's length

_QUOTED = re.compile(r"«([^»]*)»|'([^']*)'")
_LINE_UNIT = re.compile(r"\((\w+) unit (\d+),")
_GLOSS = re.compile(r"\([^)]*\)?")


def record_path(root, ep: str) -> Path:
    return Path(root) / "work" / "daily" / ep / "cap-heal.json"


def load(root, ep: str) -> dict:
    try:
        r = json.loads(record_path(root, ep).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        r = {}
    if not isinstance(r, dict):
        r = {}
    r.setdefault("lines", {})          # line id -> {"cuts": [display word index, ...]}
    r.setdefault("rounds", 0)
    r.setdefault("refits", 0)
    r.setdefault("events", [])
    r.setdefault("exhausted", None)    # {"reason", "date"} once nothing is left to try (the autopilot then hands the stop to the fixer)
    return r


def save(root, ep: str, rec: dict) -> None:
    p = record_path(root, ep)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def heal_possible(root, ep: str) -> bool:
    """For the autopilot (a pure file read): may a plate-size stop of this episode still be healed (a cut or a rewrite left)?"""
    r = load(root, ep)
    return not r["exhausted"] and (r["rounds"] < MAX_ROUNDS or r["refits"] < MAX_REFITS)


# ------------------------------------------------------------------ reading the failure
def parse(code: str, msg: str) -> dict | None:
    """{'code', 'text', 'line'} from a plate-size failure message. `text` is the plate's text without its bracketed meaning; 'line' is the script line id when the message names it."""
    if code not in IDS:
        return None
    m = _QUOTED.search(msg or "")
    if not m:
        return None
    text = _GLOSS.sub("", m.group(1) or m.group(2) or "").strip()
    if not text:
        return None
    lu = _LINE_UNIT.search(msg)
    return {"code": code, "text": text, "line": lu.group(1) if lu else None, "unit": int(lu.group(2)) if lu else None}


def locate(lines: list[dict], text: str, hint: str | None = None) -> tuple[str, int, list[str]] | None:
    """(line id, index of the plate's first word, the line's display words) where the plate's words sit in the script. A text cut short by the message (CALM-PLATE-SAFE shows 22 characters)
    matches on its whole words plus a prefix of the last one."""
    from arabic_display import display_text
    want = text.split()
    if not want:
        return None
    order = sorted(lines, key=lambda l: l["id"] != hint)
    for ln in order:
        lw = display_text(ln["text"]).split()
        for s in range(0, len(lw) - len(want) + 1):
            seg = lw[s:s + len(want)]
            if seg[:-1] == want[:-1] and seg[-1].startswith(want[-1]):
                return ln["id"], s, lw
        if hint and ln["id"] == hint:
            break
    return None


def _need_s(words: list[str]) -> float:
    """The least a plate of these words must stay up: the larger of CAP-READING-SPEED and CAP-READ-TIME (cap_sentence), the two checks the animatic puts on it."""
    import cap_sentence as CS
    return max(CS.read_speed_need_s(CS.visible_chars(" ".join(words))), CS.read_budget_s(len(words)))


def candidates(lw: list[str], start: int, n: int, taken: set[int], glued: set[int], *, weights: list[float] | None = None, secs: float | None = None) -> list[int]:
    """Where the plate of words start..start+n-1 may be cut (a cut after display word i), never inside a glued glossary phrase and never twice. Best first.
    With the line's syllable `weights` and its take length `secs`, a cut whose parts would each be up long enough to be read comes first: a part in the MIDDLE of a line cannot be
    cured later (read_heal only gives the first plate a lead and the last a hold), so a middle part shorter than its need makes the cut non-viable and it goes last. Then a
    sentence end, then a clause end, then the middle of a sentence (cap_sentence flags that `split`; CAP-FULL-SENTENCE already allows it), then the most even cut in letters."""
    import cap_sentence as CS
    first_unit, last_unit = start == 0, start + n == len(lw)
    tot = sum(weights) if weights else 0.0

    def dur(i0, i1):      # seconds the voice spends on words i0..i1-1 (the last plate of a line also holds a tail)
        return secs * sum(weights[i0:i1]) / tot if (weights and secs and tot) else None
    out = []
    for i in range(start, start + n - 1):
        if i in taken or i in glued:
            continue
        short = 0.0
        for (a0, a1, curable) in ((start, i + 1, first_unit), (i + 1, start + n, last_unit)):
            d = dur(a0, a1)
            if d is not None and not curable:
                short = max(short, _need_s(lw[a0:a1]) - (d - ESTIMATE_MARGIN_S))
        a, b = sum(len(w) for w in lw[start:i + 1]), sum(len(w) for w in lw[i + 1:start + n])
        tier = 0 if CS.ends_sentence(lw[i]) else 1 if CS.ends_clause(lw[i]) else 2
        out.append((1 if short > 0.05 else 0, round(short, 1) if short > 0.05 else 0, tier, abs(a - b), i))
    return [o[-1] for o in sorted(out)]


def CS_weights(line: dict, lw: list[str]) -> list[float] | None:
    import cap_sentence as CS
    w, _m = CS.syllable_weights(" ".join(lw), line.get("tts_text"))
    return w if len(w) == len(lw) else None


def _glued(ctx, line: dict, lw: list[str], script: dict) -> set[int]:
    try:
        import gloss as G
        gl = G.load(ctx.root, script.get("series"))
        gm = G.gloss_map(lw, line.get("speaker"), G.line_entries(line, gl))
        return {i for idx, e in gm.items() for i in range(idx - len(G._key(e)) + 1, idx)}
    except Exception:     # noqa: BLE001  no glossary data: nothing is glued, the cut is still only at a sentence or clause end
        return set()


def failures(error) -> list[dict]:
    """The plate-size failures of a stop: the findings of a verify failure (animatic) or the one message of a stage failure (compose)."""
    out = []
    for f in getattr(error, "findings", None) or []:
        if f.get("sev", "fail") == "fail" and f.get("id") in IDS:
            p = parse(f["id"], f.get("msg") or "")
            if p:
                out.append(p)
    if not out:
        p = parse(getattr(error, "code", ""), getattr(error, "msg", "") or "")
        if p:
            out.append(p)
    return out


def curable(error) -> bool:
    return bool(failures(error))


# ------------------------------------------------------------------ the ledger
def ledger(ctx, summary: str, fault: str) -> None:
    """One lessons-ledger entry per heal (kb/lessons/ledger.jsonl). Never raises."""
    try:
        import learn
        learn.add_lessons(ctx.root, ctx.ep, [{"summary": summary, "fault": fault, "class": "PROCESS",
                                              "root_cause": "caption units are built from the text alone, before any face is located; a merged run of brief sentences can make a plate with no legal place beside a close-up",
                                              "fix": "tools/cap_heal.py cuts the plate at a sentence end (cap-heal.json), or rewrites the line shorter (line_refit), and the stages run again", "check": fault}],
                          "cap-heal", dt.date.today().isoformat())
    except Exception as e:     # noqa: BLE001  the ledger is a record; it never blocks a build
        ctx.log(f"[cap-heal] ledger entry failed: {e}")


# ------------------------------------------------------------------ the cure
def rerun_stages(ctx, names: list[str]) -> None:
    """Run the stages again in order (each skips itself when fresh). A reading-time stop of the animatic goes to read_heal, as `daily.py run` does. A StageFail is the caller's stop."""
    import daily
    import read_heal
    for n in names:
        for k in range(daily.READ_HEAL_CALLS + 1):
            try:
                daily.run_stage(ctx, daily.STAGES[n])
                break
            except daily.VerifyFail as e:
                if n == "animatic" and k < daily.READ_HEAL_CALLS and read_heal.cure(ctx, e):
                    continue
                raise


def refit_item(ctx, plan: dict, script: dict, lid: str, text: str) -> dict | None:
    import line_refit
    secs = line_refit.measured_seconds(ctx, script).get(lid)
    if not secs:
        return None
    scene = next((s.get("id") for s in plan.get("scenes", []) if s.get("line") == lid), lid)
    return {"line": lid, "slot": "scene", "ref": scene, "seconds": round(secs, 2), "max_s": round(secs * REFIT_SHARE * 1.1, 2), "target_s": round(max(1.2, secs * REFIT_SHARE), 2),
            "why": f"its caption «{text[:60]}» has no place on screen outside the faces (or is wider than the safe area): the sentence must be clearly shorter, about {int(REFIT_SHARE * 100)} % of its length"}


def cure(ctx, error, *, from_stage: str = "compose") -> bool:
    """Called by `daily.run_list` when compose (CAP-FACE-CLEAR, CAP-SAFE) or the animatic (CALM-PLATE-SAFE) fails on a plate that is too big for its place.
    True = the unit was cut (or its line rewritten) and the stages before `from_stage` have run again; the caller runs `from_stage` again. False = nothing left to try
    (recorded in cap-heal.json `exhausted`; the original stop stays). A StageFail from a stage it reruns is the caller's stop."""
    import daily
    fs = failures(error)
    if not fs:
        return False
    rec = load(ctx.root, ctx.ep)
    if rec["exhausted"]:
        ctx.log("[cap-heal] already exhausted for this episode: the stop stays")
        return False
    try:
        script = json.loads((ctx.ep_dir / "script.json").read_text(encoding="utf-8"))
        plan = json.loads((ctx.ep_dir / "calm-plan.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        ctx.log(f"[cap-heal] cannot read the episode files: {e}")
        return False
    f = fs[0]
    loc = locate(script["lines"], f["text"], f["line"])
    if loc is None:
        rec["exhausted"] = {"reason": f"unlocated: «{f['text'][:40]}» is not in the script", "date": dt.date.today().isoformat()}
        save(ctx.root, ctx.ep, rec)
        ctx.log("[cap-heal] " + rec["exhausted"]["reason"])
        return False
    lid, start, lw = loc
    n = len(f["text"].split())
    line = next(l for l in script["lines"] if l["id"] == lid)
    row = rec["lines"].setdefault(lid, {"cuts": []})
    weights, secs = None, None
    try:
        import line_refit
        weights = CS_weights(line, lw)
        secs = line_refit.measured_seconds(ctx, {"lines": [line]}).get(lid)
    except Exception:     # noqa: BLE001  no take to measure: the cut is chosen without the reading estimate
        pass
    cands = candidates(lw, start, n, set(row["cuts"]), _glued(ctx, line, lw, script), weights=weights, secs=secs)
    now = dt.datetime.now().isoformat(timespec="seconds")
    upstream = {"compose": ["animatic", "shots"], "animatic": []}.get(from_stage, [])
    if cands and rec["rounds"] < MAX_ROUNDS:
        cut = cands[0]
        row["cuts"] = sorted(row["cuts"] + [cut])
        rec["rounds"] += 1
        rec["events"].append({"at": now, "round": rec["rounds"], "event": "cut", "code": f["code"], "line": lid, "after_word": cut, "plate": f["text"][:80]})
        save(ctx.root, ctx.ep, rec)
        ledger(ctx, f"{ctx.ep} {lid}: the plate «{f['text'][:50]}» had no place on screen ({f['code']}); it is cut after «{lw[cut]}» (cap-heal)", f["code"])
        ctx.log(f"[cap-heal] {f['code']}: {lid} plate «{f['text'][:50]}» cut after word {cut} «{lw[cut]}» (round {rec['rounds']}/{MAX_ROUNDS}); {', '.join(upstream) or from_stage} run again")
        rerun_stages(ctx, upstream)
        return True
    if rec["refits"] < MAX_REFITS:
        import line_refit
        item = refit_item(ctx, plan, script, lid, f["text"])
        if item is None:
            rec["exhausted"] = {"reason": f"{lid} has no voiced take to measure for a rewrite", "date": dt.date.today().isoformat()}
            save(ctx.root, ctx.ep, rec)
            return False
        rec["refits"] += 1
        rec["events"].append({"at": now, "event": "refit", "code": f["code"], "line": lid, "plate": f["text"][:80], "why": "no cut left in the unit" if not cands else "cut rounds spent"})
        save(ctx.root, ctx.ep, rec)
        ledger(ctx, f"{ctx.ep} {lid}: the plate «{f['text'][:50]}» has no place on screen and no cut is left ({f['code']}); the line is reworded shorter under a new id (cap-heal)", f["code"])
        ctx.log(f"[cap-heal] {f['code']}: {lid} cannot be cut further; rewording it shorter (line_refit, once voiced)")
        if line_refit.cure(ctx, error, only=lid, items=[item]):
            rerun_stages(ctx, ["plan", "animatic", "shots"])
            return True
    rec["exhausted"] = {"reason": "no cut and no rewrite left", "date": dt.date.today().isoformat()}
    save(ctx.root, ctx.ep, rec)
    ctx.log("[cap-heal] nothing left to try for " + lid)
    return False
