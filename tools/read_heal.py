"""tools/read_heal.py - the animatic's reading-time findings fed back into the plan (R-503, the owner 2026-10-30: "fix the stopping issue, never stop again").

The plan estimates how long a caption plate stays up (calm_compose.read_hold_s: the LAST sentence of a line, from the text alone). The animatic then measures the REAL
plates (real Thmanyah widths, real word timing, sentence merging). When a plate is up for less than a reader needs (CAP-READING-SPEED / CAP-READ-TIME) the
fix text has always said "the plan adds a pause or the writer shortens the line"; this module does the plan's half by itself, from the measurement:

  the plate that is short is the LAST sentence of its line   -> `hold`: the scene is held that much longer AFTER the line (the next voice moves later; the shot holds its last frame)
  it is the FIRST sentence of a line with more sentences     -> `lead`: that much silence BEFORE the voice (the first plate may start inside it; calm_compose.caption_states)
  it is a sentence in the middle of the line                  -> not curable by the plan: the voice runs through it. The stop stays (the script needs the writer).

The shortfall plus MARGIN_S is written to work/daily/<ep>/read-heal.json, which is an input of the plan stage; `daily.py run` then reruns plan and animatic (bounded:
HEAL_CALLS per run, MAX_ROUNDS per episode). Nothing is loosened: the threshold stays max(1.5 s, chars / 12 cps) and the same check judges the result. Every heal is
written to the lessons ledger (kb/lessons/ledger.jsonl) so the plan's own estimate can be improved from the evidence.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

READ_IDS = ("CAP-READING-SPEED", "CAP-READ-TIME")
HEAL_CALLS = 2            # heal passes inside one `daily.py run`
MAX_ROUNDS = 4            # heal passes per episode in total (read-heal.json `rounds`); after that the stop is the Lead's
MARGIN_S = 0.1            # the measured shortfall is raised by this much (the pause is also snapped up to a whole frame)
MAX_EXTRA_S = 3.0         # one scene never gets more than this much extra in total (PLAN-DURATION still guards the scene)

_NUM = re.compile(r"(\S+) unit (\d+): .*?is on screen ([\d.]+) s.*?(?:the least is .*?= |a reader needs )([\d.]+) s", re.S)


def record_path(root, ep: str) -> Path:
    return Path(root) / "work" / "daily" / ep / "read-heal.json"


def load(root, ep: str) -> dict:
    try:
        r = json.loads(record_path(root, ep).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        r = {}
    r.setdefault("lines", {})        # line id -> {"lead": s, "hold": s}
    r.setdefault("rounds", 0)
    r.setdefault("events", [])
    r.setdefault("exhausted", None)     # {"reason", "date"} once a pass found nothing the plan can cure (the autopilot then treats the stop as terminal)
    return r


def save(root, ep: str, rec: dict) -> None:
    p = record_path(root, ep)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def heal_possible(root, ep: str) -> bool:
    """For the autopilot (a pure file read): may a reading-time stop of this episode still be healed by the plan feedback?"""
    r = load(root, ep)
    return r["rounds"] < MAX_ROUNDS and not r["exhausted"]


def parse(finding: dict) -> dict | None:
    """{'id', 'line', 'unit', 'shown', 'need'} from a CAP-READING-SPEED / CAP-READ-TIME finding (cap_sentence.check_plates messages). None when it is another check."""
    if finding.get("id") not in READ_IDS or finding.get("sev", "fail") != "fail":
        return None
    m = _NUM.search(finding.get("msg") or "")
    if not m:
        return None
    return {"id": finding["id"], "line": m.group(1), "unit": int(m.group(2)), "shown": float(m.group(3)), "need": float(m.group(4))}


def curable_ids(findings: list[dict]) -> list[dict]:
    return [p for p in (parse(f) for f in findings) if p]


def _units_of(ctx, line: str) -> int | None:
    """How many sentence units the animatic made of a line (work/episodes/<ep>/animatic/report.json `plates`: [line, unit, state, start, end])."""
    try:
        rep = json.loads((ctx.root / "work" / "episodes" / ctx.ep / "animatic" / "report.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    us = {p[1] for p in rep.get("plates", []) if p and p[0] == line}
    return len(us) or None


def plan_feedback(ctx, findings: list[dict], rec: dict) -> list[dict]:
    """Apply the measured shortfalls to rec['lines'] and return what was done (one dict per finding: line, unit, where, add_s, or why not)."""
    done = []
    for p in curable_ids(findings):
        n_units = _units_of(ctx, p["line"])
        short = max(0.0, p["need"] - p["shown"]) + MARGIN_S
        if n_units is None or p["unit"] == n_units - 1:
            where = "hold"
        elif p["unit"] == 0:
            where = "lead"
        else:
            done.append({**p, "where": None, "why": "a sentence in the middle of the line: the voice runs through it, only the script can change it"})
            continue
        row = rec["lines"].setdefault(p["line"], {"lead": 0.0, "hold": 0.0})
        if row["lead"] + row["hold"] + short > MAX_EXTRA_S + 1e-9:
            done.append({**p, "where": where, "why": f"would add more than {MAX_EXTRA_S} s to one scene"})
            continue
        row[where] = round(row[where] + short, 3)
        done.append({**p, "where": where, "add_s": round(short, 3)})
    return done


def ledger(ctx, done: list[dict]) -> None:
    """One lessons-ledger entry per healed plate (kb/lessons/ledger.jsonl). Never raises."""
    try:
        import learn
        items = []
        for d in done:
            if not d.get("where"):
                continue
            items.append({"summary": f"{ctx.ep} {d['line']} unit {d['unit']}: plate up {d['shown']:.2f} s, needs {d['need']:.2f} s; the plan now adds {d['add_s']:.2f} s of {d['where']} (read-heal)",
                          "fault": d["id"], "class": "PROCESS",
                          "root_cause": "the plan's reading-time estimate sees only the line's last clause from the text; the animatic measures the real plates (widths, merging, word timing)",
                          "fix": "tools/read_heal.py feeds the measured shortfall back to the plan (lead / hold) and reruns plan and animatic", "check": d["id"]})
        if items:
            learn.add_lessons(ctx.root, ctx.ep, items, "read-heal", dt.date.today().isoformat())
    except Exception as e:     # noqa: BLE001  the ledger is a record; it never blocks a build
        ctx.log(f"[read-heal] ledger entry failed: {e}")


def cure(ctx, error) -> bool:
    """Called by daily.run_list when the animatic's verify failed. True = the plan was fed back and plan has run again (the caller runs the animatic again);
    False = nothing the plan can cure, or the rounds are spent. Raises StageFail only from the plan stage it reruns."""
    import daily
    findings = getattr(error, "findings", None) or []
    fails = [f for f in findings if f.get("sev", "fail") == "fail"]
    if not curable_ids(fails):
        return False
    rec = load(ctx.root, ctx.ep)
    if rec["rounds"] >= MAX_ROUNDS:
        ctx.log(f"[read-heal] {rec['rounds']} heal rounds already used for {ctx.ep}: the stop stays")
        return False
    done = plan_feedback(ctx, fails, rec)
    applied = [d for d in done if d.get("where") and d.get("add_s")]
    rec["events"].append({"at": dt.datetime.now().isoformat(timespec="seconds"), "round": rec["rounds"] + 1, "done": done})
    if not applied:
        rec["exhausted"] = {"reason": "uncurable", "date": dt.date.today().isoformat()}
        save(ctx.root, ctx.ep, rec)
        ctx.log("[read-heal] no finding can be cured by the plan: " + "; ".join(f"{d['line']} unit {d['unit']}: {d.get('why')}" for d in done)[:300])
        return False
    before = load(ctx.root, ctx.ep)      # the record as it was on disk, to put back if the plan refuses the longer scene
    rec["rounds"] += 1
    rec["exhausted"] = None
    save(ctx.root, ctx.ep, rec)
    ledger(ctx, done)
    ctx.log("[read-heal] " + ", ".join(f"{d['line']} unit {d['unit']} +{d['add_s']} s {d['where']}" for d in applied) + f"; plan and animatic run again (round {rec['rounds']}/{MAX_ROUNDS})")
    try:
        daily.run_stage(ctx, daily.STAGES["plan"])      # its inputs now include read-heal.json, so it reruns; a StageFail here is the caller's stop
    except daily.StageFail:
        before["exhausted"] = {"reason": "plan-refused", "date": dt.date.today().isoformat()}
        before["events"] = rec["events"]
        save(ctx.root, ctx.ep, before)
        raise
    return True
