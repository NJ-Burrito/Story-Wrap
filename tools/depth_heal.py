"""tools/depth_heal.py - a calm shot that fails a depth gate is re-layered, not parked (R-504, the owner 2026-10-30: "fix the stopping issue, never stop again").

E05-s01 (Hero at the back wall, the lamp with the cut thread on the counter) failed `parallax_corr` = 0.063 (gate >= 0.10) while the other fifteen shots of the same episode
measured 0.107 to 0.461: with one flat figure plane and a 3 % dolly the depth model sees a layered set but the motion does not follow the layers. The cure that already worked
once by hand (E01C insert_depth, calm.py) is a real-depth camera: a longer dolly with a slight sideways drift, so every plane moves at its own rate (nearer = faster) while the total
move stays inside the calm band (CALM-MOTION <= 0.35, CALM-CAMERA < 40 %).

This module is that cure as a pipeline step. `daily.py` s_shots calls it when `shot.py all` fails and the ONLY failing gates are depth gates (quality_gate.DEPTH_GATES):

  rung 1: push >= 5 %, span 1 %   (the camera drifts sideways a little while it pushes in: parallax from two axes). Measured on E05-s01 (2026-10-30, local render + gate, unchanged gates):
          parallax_corr 0.063 -> 0.112, depth_bands 4.9 -> 5.0, motion_coverage 0.238 -> 0.331 (ceiling 0.35), every other gate PASS
  rung 2: push >= 6 %, span 1 %, near tags on   (for a shot with calm headroom left; on E05-s01 it reached 0.126 but motion_coverage 0.363 > 0.35, so CALM-MOTION failed it: rung 1 is the one that fits there)
  Measured on the way (same shot): push 4 + span 1 % = 0.099 (just under); push 7 alone = 0.097 and coverage 0.380; push 5 + span 1 % with the lamp and world at 0 = 0.092 and coverage 0.402
  (a flat lamp makes the set's motion all camera motion and busts the ceiling): so the rungs touch nothing but the camera.

The overlay is written to work/daily/<ep>/depth-heal.json, an input of the shots stage, and applied to the shot's plan parameters on every later run (a healed shot stays healed; the
cache compares the description a template writes now). Only the failing shot is re-rendered. Bounds: ROUNDS_PER_RUN rounds inside one `daily.py run`, one rung per round, len(RUNGS)
rungs per shot in total, then the stop is the Lead's (`exhausted`). Nothing is loosened: the same gates judge every rung, CALM-MOTION and the rest included; a rung that breaks
another gate fails and the next rung is tried. Every heal is one lessons-ledger entry (kb/lessons/ledger.jsonl, source `depth-heal`).
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

DEPTH_IDS = ("parallax_corr", "depth_bands")      # quality_gate.DEPTH_GATES keys (a test pins this to the gate list)
ROUNDS_PER_RUN = 2          # heal rounds inside one `daily.py run`
RUNGS = (
    {"push": 5.0, "span": 0.010},
    {"push": 6.0, "span": 0.010, "x_near": "1"},
)
CURABLE_TEMPLATES = ("push_in", "reaction_closeup", "hold_breathe", "parallax_pan", "insert")     # camera = a dolly the overlay may lengthen; insert_depth already is the depth cure


def record_path(root, ep: str) -> Path:
    return Path(root) / "work" / "daily" / ep / "depth-heal.json"


def load(root, ep: str) -> dict:
    try:
        r = json.loads(record_path(root, ep).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        r = {}
    r.setdefault("shots", {})       # shot id -> {"rung": n applied, "history": [...], "exhausted": bool}
    r.setdefault("exhausted", None)
    return r


def save(root, ep: str, rec: dict) -> None:
    p = record_path(root, ep)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def heal_possible(root, ep: str) -> bool:
    """For the autopilot (a pure file read): may a depth stop of this episode still be cured by a rung the record has not used?"""
    r = load(root, ep)
    if r["exhausted"]:
        return False
    return all(not s.get("exhausted") and s.get("rung", 0) < len(RUNGS) for s in r["shots"].values()) if r["shots"] else True


def overlay(rec: dict, shot_id: str, tpl: str, prm: dict) -> dict:
    """The plan parameters with the shot's recorded rung applied (a copy). Never lowers a push or span the plan already asks for."""
    n = (rec["shots"].get(shot_id) or {}).get("rung", 0)
    if not n or tpl not in CURABLE_TEMPLATES or prm.get("locked"):
        return prm
    out = dict(prm)
    for k, v in RUNGS[min(n, len(RUNGS)) - 1].items():
        try:
            if isinstance(v, (int, float)) and float(out.get(k, 0)) >= v:
                continue
        except (TypeError, ValueError):
            pass
        out[k] = str(v) if not isinstance(v, str) else v
    return out


def failing(sd) -> tuple[list[str], list[str]]:
    """(depth gate ids that failed, other gate ids that failed) from <shot>/gate/report.json. ([], []) when there is no report."""
    try:
        rep = json.loads((Path(sd) / "gate" / "report.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [], []
    depth, other = [], []
    for gname, g in (rep.get("gates") or {}).items():
        for i in g.get("fail_ids") or []:
            (depth if (gname == "render" and i in DEPTH_IDS) else other).append(i)
    return depth, other


def curable(sd, tpl: str, prm: dict, rec: dict, shot_id: str) -> bool:
    depth, other = failing(sd)
    st = rec["shots"].get(shot_id) or {}
    return bool(depth) and not other and tpl in CURABLE_TEMPLATES and not prm.get("locked") and st.get("rung", 0) < len(RUNGS) and not st.get("exhausted")


def metrics(sd) -> dict:
    try:
        m = json.loads((Path(sd) / "gate" / "render.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: m.get(k) for k in ("parallax_corr", "depth_bands", "motion_coverage") if k in m}


def ledger(ctx, shot_id: str, rung: int, before: dict, after: dict, ok: bool, depth: list[str]) -> None:
    """One lessons-ledger entry per heal round. Never raises."""
    try:
        import learn
        res = "passes" if ok else "still fails"
        learn.add_lessons(ctx.root, ctx.ep, [{
            "summary": f"{shot_id}: {', '.join(depth)} {before}; rung {rung} {RUNGS[rung - 1]} {res} {after} (depth-heal)",
            "fault": depth[0], "class": "PROCESS",
            "root_cause": "a flat figure plane under a 3 % dolly: the depth model sees the layers of the set but the camera moves them at nearly one rate (correlation of depth with motion under 0.10)",
            "fix": "tools/depth_heal.py lengthens the dolly and adds a slight sideways drift (and the near tags) for that shot and re-renders only it; the gate is unchanged", "check": depth[0]}],
            "depth-heal", dt.date.today().isoformat())
    except Exception as e:     # noqa: BLE001  the ledger is a record; it never blocks a build
        ctx.log(f"[depth-heal] ledger entry failed: {e}")


def cure(ctx, shot_id: str, tpl: str, prm: dict, sd, attempt) -> bool:
    """Called by daily.s_shots when a shot's gates failed. `attempt(new_prm)` re-resolves, writes and gates the shot and returns True when `shot.py all` passed.
    True = the shot now passes. False = nothing a rung can cure (another gate failed, no rung left), or the rounds of this run are spent: the original stop stands."""
    rec = load(ctx.root, ctx.ep)
    st = rec["shots"].setdefault(shot_id, {"rung": 0, "history": []})
    for _ in range(ROUNDS_PER_RUN):
        if not curable(sd, tpl, prm, rec, shot_id):
            break
        depth, _other = failing(sd)
        before = metrics(sd)
        st["rung"] += 1
        new = overlay(rec, shot_id, tpl, prm)
        ctx.log(f"[depth-heal] {shot_id}: {', '.join(depth)} {before}; rung {st['rung']}/{len(RUNGS)} {RUNGS[st['rung'] - 1]}")
        ok = bool(attempt(new))
        after = metrics(sd)
        st["history"].append({"at": dt.datetime.now().isoformat(timespec="seconds"), "rung": st["rung"], "before": before, "after": after, "ok": ok})
        save(ctx.root, ctx.ep, rec)
        ledger(ctx, shot_id, st["rung"], before, after, ok, depth)
        if ok:
            return True
    if not curable(sd, tpl, prm, rec, shot_id):      # no rung left, or the failure is not a depth one: the stop is the Lead's and the autopilot must not wait for a heal
        st["exhausted"] = True
        ctx.log(f"[depth-heal] {shot_id}: nothing left to try ({st['rung']}/{len(RUNGS)} rungs used): the stop stands")
    save(ctx.root, ctx.ep, rec)
    return False
