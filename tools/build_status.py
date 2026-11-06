# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""The board's live BUILD panel (owner, 2026-10-30, R-505): what the pipeline is doing right now and, in red, anything that stopped.

    uv run tools/build_status.py            write board/data/build.json and build.js now, print the headline
    uv run tools/build_status.py --json     print the whole block

Written by every autopilot tick (autopilot.publish_build) and at every stage boundary of `daily.py run` (daily.publish_build_status), so the panel is never older than the last thing
that happened; board/index.html reads it every 60 s and shows it above every tab. Files only: no network, no model, no process, standard library only. It never raises into a caller.

The block: {generated_at, episode, stages[{stage,state,seconds,note}], heals[{file,kind,rounds,last}], machine{used_s,cap_s}, tokens{used,limit}, autopilot{last,last_at,next_tick,ticking},
alerts[{kind,ep,text,since}]}. Stage state is ok | running | failed | waiting. An alert is a STOPPED.md nobody resolved, a stuck/backed-off episode, a FIX-REQUEST.md, a PUBLISH-* stop, a
failed harvest, or an autopilot that stopped ticking.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("STORYWRAP_ROOT") or TOOLS.parent)
STAGE_ORDER = ["votes", "script", "voice", "plan", "animatic", "shots", "compose", "gates", "critic", "retro", "publish", "schedule"]
STOP_SHOW_H = 72                     # an unresolved STOPPED.md older than this is history
RUNNING_FRESH_MIN = 20               # a "running" stage with no live autopilot lock and a STATE.json older than this was cut short
TICK_STALE_X = 3                     # an autopilot silent for this many of its own ticks is an alert (the 2026-10-30 root cause: nothing ran after 18:30)
DEFAULT_TOKENS = 5_000_000
POST_STAGE_NAMES = ("publish", "schedule", "yt_stories")


def rj(p: Path, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:       # noqa: BLE001
        return default


def iso(t: dt.datetime | None) -> str | None:
    return t.isoformat(timespec="minutes") if t else None


def ddir(root: Path) -> Path:
    return Path(root) / "work" / "daily"


def active_episode(root: Path) -> str | None:
    """The episode whose STATE.json changed last (the one being built)."""
    c = [(p.stat().st_mtime, p.parent.name) for p in ddir(root).glob("E*/STATE.json")]
    return max(c)[1] if c else None


def lock_alive(root: Path) -> bool:
    held = rj(ddir(root) / "autopilot.lock", {}) or {}
    try:
        import autopilot
        return autopilot.pid_alive(int(held.get("pid") or 0))
    except Exception:       # noqa: BLE001
        return False


def schedule_task(root: Path) -> dict:
    return ((rj(Path(root) / "board" / "schedule.json", {}) or {}).get("tasks") or {}).get("StoryWrap-Autopilot") or {}


def next_tick(task: dict, at: dt.datetime) -> dt.datetime | None:
    """The next start of the autopilot task after `at` (board/schedule.json: from + k * every_min, all day when there is no for_h)."""
    try:
        h, m = (task.get("from") or "00:00").split(":")
        step = dt.timedelta(minutes=int(task["every_min"]))
    except (KeyError, ValueError):
        return None
    for d in range(0, 3):
        day = at.date() + dt.timedelta(days=d)
        t = dt.datetime.combine(day, dt.time(int(h), int(m)))
        end = t + dt.timedelta(hours=float(task["for_h"])) if task.get("for_h") else dt.datetime.combine(day, dt.time(23, 59, 59))
        while t <= end:
            if t > at:
                return t
            t += step
    return None


def stage_rows(root: Path, ep: str, at: dt.datetime) -> list[dict]:
    st = rj(ddir(root) / ep / "STATE.json", {}) or {}
    stages = st.get("stages") or {}
    try:
        fresh = (at.timestamp() - (ddir(root) / ep / "STATE.json").stat().st_mtime) < RUNNING_FRESH_MIN * 60
    except OSError:
        fresh = False
    live = lock_alive(root) or fresh
    names = STAGE_ORDER + [k for k in stages if k not in STAGE_ORDER]
    rows = []
    for n in names:
        e = stages.get(n)
        if e is None:
            if n in ("publish", "schedule") or n not in STAGE_ORDER:
                continue
            rows.append({"stage": n, "state": "waiting", "seconds": None, "note": ""})
            continue
        s = e.get("status")
        state = "ok" if s in ("ok", "skipped") else "failed" if s == "failed" else "running" if s == "running" else "waiting"
        note = ((e.get("check") + ": ") if e.get("check") else "") + str(e.get("message") or (e.get("info") or {}).get("why") or "")
        if state == "running" and not live:
            state, note = "failed", "interrupted: no live run found for it"
        rows.append({"stage": n, "state": state, "seconds": e.get("seconds"), "note": note[:200]})
    return rows


HEAL_KINDS = {"refit.json": "line refit (R-502)", "read-heal.json": "reading time (R-503)", "depth-heal.json": "depth re-layering (R-504)", "cap-heal.json": "plate cut (R-506)",
              "fixer.json": "general fixer (R-506)"}
ACTIVE_MIN = 10                      # a heal record touched within this many minutes of a live run is "running now"


def heals(root: Path, ep: str, at: dt.datetime | None = None) -> list[dict]:
    """Every heal record beside STATE.json: refit.json, read-heal.json, cap-heal.json, fixer.json and any other *heal* file (the depth heal of the shots stage writes one too).
    Each row says WHICH heal it is (`kind`), what it did last (`what`) and whether it is working right now (`active`), so the board shows a pipeline that is working, not waiting."""
    out = []
    at = at or dt.datetime.now()
    live = lock_alive(root)
    for p in sorted((ddir(root) / ep).glob("*.json")):
        if not ("heal" in p.name or "refit" in p.name or p.name == "fixer.json"):
            continue
        j = rj(p, None)
        if not isinstance(j, dict):
            continue
        ev = j.get("events") if isinstance(j.get("events"), list) else []
        rounds = j.get("rounds")
        if rounds is None and isinstance(j.get("lines"), dict):
            rounds = sum(int((v or {}).get("rounds", 0)) for v in j["lines"].values() if isinstance(v, dict))
        last = (ev[-1] or {}).get("at") if ev and isinstance(ev[-1], dict) else None
        e = ev[-1] if ev and isinstance(ev[-1], dict) else {}
        what = str(e.get("result") or e.get("event") or e.get("plate") or "")[:160]
        if e.get("event") == "cut":
            what = f"cut {e.get('line')} «{str(e.get('plate'))[:30]}» after word {e.get('after_word')}"
        age_min = (at.timestamp() - p.stat().st_mtime) / 60
        out.append({"file": p.name, "kind": HEAL_KINDS.get(p.name, "heal"), "rounds": rounds if rounds is not None else len(ev), "events": len(ev),
                    "last": last or dt.datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="minutes"), "what": what, "active": bool(live and age_min < ACTIVE_MIN),
                    "exhausted": bool(j.get("exhausted"))})
    return out


def stop_info(root: Path, ep: str):
    p = ddir(root) / ep / "STOPPED.md"
    try:
        t = p.read_text(encoding="utf-8")
        m = re.search(r"FAIL \[([A-Z0-9-]+)\]\s*(.*)", t)
        m2 = re.search(r"FAIL \[([A-Z0-9-]+)\]\s*(.*)", m.group(2)) if m and m.group(1) == "CHILD" else None      # R-506: a stop written before the child's own code was unwrapped
        m = m2 or m
        st = re.search(r"stage (\w+),", t)
        return (m.group(1) if m else "STOPPED"), (m.group(2) if m else t[:200]).strip("` \n")[:300], dt.datetime.fromtimestamp(p.stat().st_mtime), (st.group(1) if st else "")
    except OSError:
        return None


def closed(root: Path, ep: str) -> bool:
    try:
        import loop_gate
        return loop_gate.is_posted(root, ep) or loop_gate.is_finished(root, ep)
    except Exception:       # noqa: BLE001
        return False


def alerts(root: Path, at: dt.datetime, ap: dict, tick_stale: str | None) -> list[dict]:
    out = []
    for d in sorted(ddir(root).glob("E*")):
        if not d.is_dir() or ":" in d.name:
            continue
        si = stop_info(root, d.name)
        fr = d / "FIX-REQUEST.md"
        if si:
            code, msg, when, stage = si
            publish = code.startswith("PUBLISH") or stage in POST_STAGE_NAMES        # R-507: a stop in a post stage is a failed publish, whatever its check id
            fresh = (at - when).total_seconds() < STOP_SHOW_H * 3600
            if fresh and (not closed(root, d.name) or publish):
                out.append({"kind": "PUBLISH-FAILED" if publish else "STOPPED", "ep": d.name, "text": f"{d.name} stopped at [{code}]: {msg}", "since": iso(when)})
        if fr.is_file():
            head = [l.strip("- ").strip() for l in fr.read_text(encoding="utf-8").splitlines() if l.startswith("- stop code") or l.startswith("- why")]
            out.append({"kind": "FIX-REQUEST", "ep": d.name, "text": f"{d.name} needs a fix: {' | '.join(head)[:300]} (work/daily/{d.name}/FIX-REQUEST.md)",
                        "since": iso(dt.datetime.fromtimestamp(fr.stat().st_mtime))})
    for ep, pk in (ap.get("parked") or {}).items():
        out.append({"kind": "STUCK", "ep": ep, "text": f"{ep} is backed off: {pk.get('why')}" + (f" (next retry {str(pk['due']).replace('T', ' ')})" if pk.get("due") else " (no retry until something changes)"), "since": pk.get("since")})
    for t in ap.get("todo") or []:
        if str(t.get("key", "")).startswith("post:"):          # R-507: the autopilot's late post failed; it tries again at the next tick
            out.append({"kind": "PUBLISH-FAILED", "ep": str(t["key"]).split(":", 1)[1], "text": t.get("text", ""), "since": t.get("since")})
        if str(t.get("key", "")).startswith("harvest:"):
            hep = str(t["key"]).split(":", 1)[1]
            try:
                import loop_gate
                if loop_gate.is_harvested(root, hep):          # a stale to-do of an episode that was harvested later is history
                    continue
            except Exception:       # noqa: BLE001
                pass
            out.append({"kind": "HARVEST-FAILED", "ep": hep, "text": t.get("text", ""), "since": t.get("since")})
    post = rj(ddir(root) / "tasks" / "StoryWrap-Post.json", {}) or {}
    if post.get("status") == "FAIL":
        out.append({"kind": "PUBLISH-FAILED", "ep": None, "text": f"StoryWrap-Post failed: {str(post.get('detail'))[:250]}", "since": post.get("at")})
    if tick_stale:
        out.append({"kind": "AUTOPILOT-SILENT", "ep": None, "text": tick_stale, "since": None})
    seen, uniq = set(), []
    for a in out:
        k = (a["kind"], a["ep"], a["text"])
        if k not in seen:
            seen.add(k)
            uniq.append(a)
    return uniq


def build(root: Path = ROOT, at: dt.datetime | None = None) -> dict:
    root = Path(root)
    at = at or dt.datetime.now()
    ep = active_episode(root)
    ap = rj(ddir(root) / "autopilot.json", {}) or {}
    last = ap.get("last") or {}
    task = schedule_task(root)
    nt = next_tick(task, at) if task else None
    tick_stale = None
    try:
        gap = at - dt.datetime.fromisoformat(last["at"])
        every = int(task.get("every_min") or 30)
        if task and gap > dt.timedelta(minutes=TICK_STALE_X * every) and not lock_alive(root):
            tick_stale = f"the autopilot said nothing for {int(gap.total_seconds() // 60)} min (it ticks every {every} min): the Task Scheduler task StoryWrap-Autopilot is not running; run tools\\register-autopilot.ps1"
    except (KeyError, ValueError, TypeError):
        if task:
            tick_stale = "the autopilot has never written a tick: register it with tools\\register-autopilot.ps1"
    dl = (rj(ddir(root) / ep / "deadline.json", {}) or {}) if ep else {}
    bud = rj(ddir(root) / f"budget-{at.date().isoformat()}.json", {}) or {}
    rows = stage_rows(root, ep, at) if ep else []
    running = next((r["stage"] for r in rows if r["state"] == "running"), None)
    failed = next((r["stage"] for r in rows if r["state"] == "failed"), None)
    al = alerts(root, at, ap, tick_stale)
    doing = ap.get("doing") if lock_alive(root) else None          # R-506/R-507: what the running autopilot tick is doing right now (a heal, the fixer, a post, a harvest)
    hl = heals(root, ep, at) if ep else []
    busy = (f"{doing.get('what')} {doing.get('ep') or ''}".strip() if doing else None) or next((f"{h['kind']} running" for h in hl if h.get("active")), None)
    return {"generated_at": iso(at), "episode": ep, "now": busy or running or ("stopped at " + failed if failed else ("idle" if all(r["state"] in ("ok", "waiting") for r in rows) else "")),
            "doing": doing, "stages": rows, "heals": hl,
            "machine": {"used_s": dl.get("machine_s", 0), "cap_s": dl.get("cap_s", 4 * 3600)},
            "tokens": {"used": int(bud.get("tokens") or 0), "limit": int(bud.get("limit") or os.environ.get("SW_LLM_DAILY_TOKENS", DEFAULT_TOKENS))},
            "autopilot": {"last": last.get("line"), "last_at": last.get("at"), "status": last.get("status"), "next_tick": iso(nt), "every_min": task.get("every_min"),
                          "running": lock_alive(root)},
            "alerts": al}


def write(root: Path = ROOT, at: dt.datetime | None = None) -> dict | None:
    """board/data/build.json (served board) and build.js (board opened from disk). Atomic. Returns the block, or None if anything failed (never raises)."""
    try:
        root = Path(root)
        data = build(root, at)
        out = root / "board" / "data"
        out.mkdir(parents=True, exist_ok=True)
        blob = json.dumps(data, ensure_ascii=False)
        for name, text in (("build.json", json.dumps(data, ensure_ascii=False, indent=1)), ("build.js", "window.__BUILD__ = " + blob + ";\n")):
            tmp = out / (name + ".tmp")
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, out / name)
        return data
    except BaseException as e:     # noqa: BLE001  the board is a courtesy: a failure here never changes a run
        print(f"build status not written: {str(e)[:120]}", file=sys.stderr)
        return None


def main(argv=None) -> int:
    a = list(sys.argv[1:] if argv is None else argv)
    sys.path.insert(0, str(TOOLS))
    d = write(ROOT)
    if d is None:
        return 1
    if "--json" in a:
        print(json.dumps(d, ensure_ascii=False, indent=1))
    else:
        print(f"{d['episode']}: {d['now']}; {len(d['alerts'])} alert(s); next tick {d['autopilot']['next_tick']}")
        for x in d["alerts"]:
            print(f"  RED {x['kind']}: {x['text']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
