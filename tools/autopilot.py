# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""The Story-Wrap AUTOPILOT (owner, 2026-10-27): harvest at 14:00 the day after a post, then build the next episode at once, without asking.

    uv run tools/daily.py autopilot [--dry] [--lead]     the entry the StoryWrap-Autopilot task runs (tools/autopilot.ps1 -> tools/register-autopilot.ps1)
    uv run tools/autopilot.py decide                      print what the next run would do (changes nothing)
    uv run tools/autopilot.py plan                        print the launcher commands as JSON (the pure function the launcher and a test share)

One run decides ONE thing from the files on disk (decide), does it, writes one status line to work/daily/autopilot.log and the state to work/daily/autopilot.json
(the board's Today tab shows both, with the to-do items the owner needs to see). It is idempotent: a run that finds nothing to do says so, a run that is cut short is resumed
by the next tick (the task fires every 15 min around the clock since 2026-10-30, R-505; the 14:00 harvest rule is decided here, not by the trigger), and work/daily/autopilot.lock keeps two runs from overlapping.
A failed episode is never parked until tomorrow: it is retried at once when tools/ or its inputs changed, else backed off (parked(): 2 h, 3 extra a day), and a stop nobody can heal writes
work/daily/<ep>/FIX-REQUEST.md; every tick and stage boundary rewrites the board's Build panel (tools/build_status.py).

  (a) an episode is built but not complete (gates, critic >= 9, retro): finish it (`daily.py run --ep E`: critic, heal within pipelines/heal.json, retro). No harvest.
  (b) otherwise, once it is 14:00 on the day after the latest post and that post is not harvested: harvest (comments, replies, DMs, metrics, Instagram vote tally, the
      learning review, the next brief), then `daily.py run` for the next episode (votes, script through critic and retro).
  (c) the latest post is harvested and nothing is started: build the next episode.
    (d) a complete unposted episode whose slot has passed: post it now (R-507).
  nothing else: idle (waiting for 14:00, complete and waiting for its 19:00 slot, or backed off).

It posts only through the Post task's own path and only after the slot (R-507): StoryWrap-Post posts at 19:00 (window to 20:25); a COMPLETE episode (gates PASS, critic >= 9, retro) whose slot has passed and that is still unposted
is posted at once by the next tick, however late and across midnight (loop_gate.late_post_due, post_extra.py tick --late-ep, one post run at a time through post.lock; a failed post is PUBLISH-FAILED in red
and retried at the next tick, POST_TRIES_PER_DAY a day). It never loosens a gate. A stop that no specific heal can cure and the Lead repair gave up on gets ONE bounded headless fixer session (try_fixer, R-506). The loop gate holds: N+1 starts
only after N was posted and harvested. A failed run is retried by the next tick up to MAX_ATTEMPTS times when the cause looks transient; a deterministic stop (heal rounds spent,
a gate, the render cap) is not retried: the run ends with exit code 6, and the launcher starts ONE headless Lead session (`--lead`, tools/templates/autopilot-lead.md) that
reads handoff.md and the log, writes work/daily/autopilot-lead-<date>.md plus a one-action decision file, and the autopilot executes that one action through the same daily.py stages
(rerun, rerun-stage, refit-line = `daily.py refit`, give-up).

A take longer than its slot (PLAN-DURATION) is not a deterministic stop any more (the owner 2026-10-30, R-502): `daily.py run` rewords that line under a new id and voices only it (tools/line_refit.py), and
the autopilot keeps such an episode out of `stuck` while that cure has rounds left (refit_pending).
A plate up too briefly (CAP-READING-SPEED / CAP-READ-TIME at the animatic) is healed the same way (the owner 2026-10-30, R-503): tools/read_heal.py feeds the measured shortfall to the plan, and
heal_pending keeps the episode out of `stuck` while it has rounds left. The Lead repair runs once per (episode, stop code) per day.
A shot that fails only a depth gate (SHOT-GATE parallax_corr / depth_bands) is healed the same way (the owner 2026-10-30, R-504): tools/depth_heal.py re-layers that shot's camera and gates it again.

Exit codes as daily.py: 0 done, waiting, idle or another run holds the lock; 1 a stage failed; 3 the day's token budget is spent; 4 the 4 h machine cap; 5 a paid service was asked
for; 6 NEEDS-LEAD (this file). The daily token budget of autopilot runs is SW_LLM_DAILY_TOKENS=5000000 (the owner 2026-10-28, replaces 1.2 M of 2026-10-27; one episode used about 1 M).

Standard library only here; the children (daily.py, inbox.py) are started with `uv run`. Every external step is an injectable callable so the tests run no process and no network.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import loop_gate  # noqa: E402

ROOT = Path(os.environ.get("STORYWRAP_ROOT") or TOOLS.parent)

DAILY_TOKENS = 5_000_000             # SW_LLM_DAILY_TOKENS of autopilot runs (the owner 2026-10-28: 5 M a day, replaces 1.2 M)
MACHINE_CAP_H = 4                    # the 4 h render cap per episode stays (daily.CAP_S)
MAX_ATTEMPTS = 3                     # failed runs of one episode on one day before it is called stuck (transient causes only)
LOCK_STALE_H = 6                     # a lock older than this is stolen even if its pid looks alive (the task limit is 5 h)
CHILD_TIMEOUT_H = 4.75               # one daily.py child (the task limit is 5 h)
POST_TIMEOUT_H = 1.5                 # one late post run (Instagram and Facebook processing, YouTube upload, stories)
NEEDS_LEAD_RC = 6
TRANSIENT = {"CHILD", "TIMEOUT", "LLM-CRITIC", "LLM-WRITER", "CRITIC-FORMAT", "CRITIC-INCOMPLETE"}     # worth another run; any other stop code is deterministic
BACKOFF_H = 2                        # R-505: after MAX_ATTEMPTS a deterministic stop is retried every 2 h (never parked "until tomorrow") ...
BACKOFF_MAX_PER_DAY = 3              # ... at most this many extra runs a day for one episode (the 4 h machine cap and the token budget still bind: daily.py exits 4 / 3)
FIX_REQUEST = "FIX-REQUEST.md"
LEAD_MAX_PER_EP_DAY = 3               # Lead repairs for one episode in one day (one per stop code, R-503)
NO_RETRY_RC = {3, 4, 5}              # budget spent, render cap, paid service: another run today cannot change it
LEAD_FORCE_STAGES = ("plan", "animatic", "shots", "compose", "gates", "critic", "retro")      # script and voice are frozen once voiced (one take per line)
LOG_NAME, STATE_NAME, LOCK_NAME = "autopilot.log", "autopilot.json", "autopilot.lock"
FIXER_MAX_PER_EP_DAY = 3             # R-506: general fixer sessions for one episode in one day (and one per stop code)
FIXER_MIN_TOKENS = 150_000           # no fixer session when the day's budget has less than this left
DOING = {"post": "posting (late, R-507)", "harvest-next": "harvesting, then building", "finish": "finishing the build", "build-next": "building the next episode"}
FIXER_NAME = "fixer.json"            # work/daily/<ep>/fixer.json: every fixer pass of the episode (the board's Build panel lists it)
POST_TRIES_PER_DAY = 8               # R-507: failed late-post attempts for one episode in one day (one per tick, so about two hours of retries); PUBLISH-FAILED stays red after that
LAUNCH_ENV = {"PYTHONUTF8": "1", "SW_LLM_DAILY_TOKENS": str(DAILY_TOKENS)}


# ------------------------------------------------------------------ files
def ddir(root: Path) -> Path:
    return Path(root) / "work" / "daily"


def read_json(p: Path, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:       # noqa: BLE001
        return default


def load_state(root: Path) -> dict:
    s = read_json(ddir(root) / STATE_NAME, {}) or {}
    s.setdefault("attempts", {})
    s.setdefault("lead", {})
    s.setdefault("fixer", {})
    s.setdefault("todo", [])
    return s


def save_state(root: Path, state: dict) -> None:
    loop_gate.write_json(ddir(root) / STATE_NAME, state)


def todo_set(state: dict, key: str, text: str, at: dt.datetime) -> None:
    state["todo"] = [t for t in state["todo"] if t.get("key") != key] + [{"key": key, "text": text[:400], "since": at.isoformat(timespec="minutes")}]


def todo_clear(state: dict, prefix: str) -> None:
    state["todo"] = [t for t in state["todo"] if not str(t.get("key", "")).startswith(prefix)]


# ------------------------------------------------------------------ the lock
def pid_alive(pid: int) -> bool:
    """Is a process with this id running? ctypes OpenProcess on Windows (os.kill(pid, 0) is not a probe there), os.kill elsewhere."""
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, pid)          # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        try:
            code = ctypes.c_ulong()
            return bool(k.GetExitCodeProcess(h, ctypes.byref(code))) and code.value == 259     # STILL_ACTIVE
        finally:
            k.CloseHandle(h)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def lock_acquire(root: Path, at: dt.datetime, pid: int | None = None, alive=pid_alive) -> bool:
    """Take work/daily/autopilot.lock (created exclusively). A lock whose process is gone, or that is older than LOCK_STALE_H, is stolen. False = another run holds it."""
    p = ddir(root) / LOCK_NAME
    p.parent.mkdir(parents=True, exist_ok=True)
    me = {"pid": pid or os.getpid(), "started": at.isoformat(timespec="seconds")}
    for _ in range(2):
        try:
            fd = os.open(str(p), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            held = read_json(p, {}) or {}
            try:
                age_h = (at - dt.datetime.fromisoformat(held["started"])).total_seconds() / 3600
            except (KeyError, ValueError, TypeError):
                age_h = 1e9                              # unreadable lock: stale
            if alive(int(held.get("pid") or 0)) and age_h < LOCK_STALE_H:
                return False
            try:
                p.unlink()
            except OSError:
                return False
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(me))
        return True
    return False


def lock_release(root: Path, pid: int | None = None) -> None:
    p = ddir(root) / LOCK_NAME
    held = read_json(p, {}) or {}
    if held.get("pid") in (None, pid or os.getpid()):       # only the lock this process took
        try:
            p.unlink()
        except OSError:
            pass


# ------------------------------------------------------------------ what is the state of the loop
def retro_done(root: Path, ep: str) -> bool:
    st = (read_json(ddir(root) / ep / "STATE.json", {}) or {}).get("stages", {}).get("retro") or {}
    return st.get("status") in ("ok", "skipped")


def build_complete(root: Path, ep: str) -> bool:
    """Gates PASS, critic 9 or more, the video exists (loop_gate.is_finished) and the retro stage ended: nothing left for a build run to do."""
    return loop_gate.is_finished(root, ep) and retro_done(root, ep)


def latest_posted(root: Path) -> str | None:
    best = None
    w = Path(root) / "work" / "episodes"
    for d in sorted(w.iterdir()) if w.is_dir() else []:
        t = loop_gate.posted_at(root, d.name) if loop_gate.EP_ID.match(d.name) else None
        if t and (best is None or t > best[0]):
            best = (t, d.name)
    return best[1] if best else None


def stop_code(root: Path, ep: str) -> str | None:
    """The code of the last stop of an episode (work/daily/<ep>/STOPPED.md: 'FAIL [CRITIC-LOW] ...')."""
    p = ddir(root) / ep / "STOPPED.md"
    if ":" in ep:
        return None
    try:
        codes = re.findall(r"FAIL \[([A-Z0-9-]+)\]", p.read_text(encoding="utf-8"))
    except OSError:
        return None
    if not codes:
        return None
    if codes[0] == "CHILD" and len(codes) > 1:     # R-506: a stop written before daily.uv unwrapped the child's own code ('FAIL [CHILD] calm_compose.py captions E05: FAIL [CAP-FACE-CLEAR] ...')
        return codes[1]
    return codes[0]


def post_tries_today(state: dict, ep: str, at: dt.datetime) -> int:
    a = state["attempts"].get("post:" + ep) or {}
    return int(a.get("n", 0)) if a.get("date") == at.date().isoformat() else 0


def attempts_today(state: dict, ep: str, at: dt.datetime) -> int:
    a = state["attempts"].get(ep) or {}
    return int(a.get("n", 0)) if a.get("date") == at.date().isoformat() else 0


def read_heal_pending(root: Path, ep: str) -> bool:
    """R-503: an episode whose last stop is a reading-time one (CAP-READING-SPEED / CAP-READ-TIME) is not stuck while tools/read_heal.py can still feed the animatic's measurement
    back to the plan (`daily.py run` does it by itself). Stuck only once its rounds are spent or a pass found nothing the plan can cure (work/daily/<ep>/read-heal.json)."""
    try:
        import read_heal
        return stop_code(root, ep) in read_heal.READ_IDS and read_heal.heal_possible(root, ep)
    except Exception:     # noqa: BLE001
        return False


def depth_heal_pending(root: Path, ep: str) -> bool:
    """R-504: an episode whose last stop is SHOT-GATE on a depth gate (parallax_corr / depth_bands) is not stuck while tools/depth_heal.py has a rung the record has not used for it:
    `daily.py run` re-layers the failing shot's camera by itself and gates only that shot. Stuck only once every rung is spent (work/daily/<ep>/depth-heal.json `exhausted`)."""
    if stop_code(root, ep) != "SHOT-GATE":
        return False
    try:
        import depth_heal
        txt = (ddir(root) / ep / "STOPPED.md").read_text(encoding="utf-8")
        return any(i in txt for i in depth_heal.DEPTH_IDS) and depth_heal.heal_possible(root, ep)
    except Exception:     # noqa: BLE001
        return False


def cap_heal_pending(root: Path, ep: str) -> bool:
    """R-506: an episode whose last stop is a plate that has no place on screen (CAP-FACE-CLEAR, CAP-SAFE, CALM-PLATE-SAFE) is not stuck while tools/cap_heal.py can still cut the plate
    or reword its line (`daily.py run` does it by itself). Stuck only once both are spent (work/daily/<ep>/cap-heal.json `exhausted`)."""
    try:
        import cap_heal
        return stop_code(root, ep) in cap_heal.IDS and cap_heal.heal_possible(root, ep)
    except Exception:     # noqa: BLE001
        return False


def heal_pending(root: Path, ep: str, at: dt.datetime) -> bool:
    """A stop that an automatic heal still has rounds for is not terminal and not stuck: the refit (PLAN-DURATION, R-502), the reading-time feedback (R-503), the depth re-layering (R-504)
    and the plate cut (CAP-FACE-CLEAR and friends, R-506)."""
    return refit_pending(root, ep, at) or read_heal_pending(root, ep) or depth_heal_pending(root, ep) or cap_heal_pending(root, ep)


def lead_key(ep: str, code: str | None) -> str:
    return f"{ep}|{code or '?'}"


def lead_done(state: dict, ep: str, code: str | None, at: dt.datetime) -> bool:
    """R-503: the Lead repair runs once per (episode, stop code) per day, and at most LEAD_MAX_PER_EP_DAY times for one episode in a day (a runaway guard). The old key (the bare
    episode id, one repair per episode per day) is no longer read."""
    today = at.date().isoformat()
    mine = [k for k, v in state["lead"].items() if k.startswith(ep + "|") and v == today]
    return state["lead"].get(lead_key(ep, code)) == today or len(mine) >= LEAD_MAX_PER_EP_DAY


def refit_pending(root: Path, ep: str, at: dt.datetime) -> bool:
    """R-502: an episode whose last stop is PLAN-DURATION (a take too long for its slot) is not stuck while tools/line_refit.py can still reword the line: the run is tried again
    (`daily.py run` refits by itself). Stuck only once the refit's own bounds are spent (work/daily/<ep>/refit.json `exhausted`)."""
    if stop_code(root, ep) != "PLAN-DURATION":
        return False
    try:
        import line_refit
        return line_refit.refit_possible(root, ep, at.date().isoformat())
    except Exception:     # noqa: BLE001
        return False


def code_fingerprint(root: Path) -> str:
    """R-505: a hash of the code a retry would run: tools/**/*.py (not the tests), tools/templates/** and pipelines/heal.json. A failure records it; when it differs at a later tick the
    code was fixed or merged since, so the episode is retried at once instead of waiting for a backoff. Pure file reads; no git call."""
    import hashlib
    root = Path(root)
    h = hashlib.sha1()
    files = [p for p in sorted((root / "tools").rglob("*.py")) if "tests" not in p.parts and "__pycache__" not in p.parts]
    files += sorted(p for p in (root / "tools" / "templates").rglob("*") if p.is_file()) if (root / "tools" / "templates").is_dir() else []
    files += [root / "pipelines" / "heal.json"] if (root / "pipelines" / "heal.json").is_file() else []
    for p in files:
        try:
            h.update(p.relative_to(root).as_posix().encode() + b"\0" + p.read_bytes() + b"\0")
        except OSError:
            continue
    return h.hexdigest()[:16]


def tokens_spent(root: Path, at: dt.datetime) -> bool:
    b = read_json(ddir(root) / f"budget-{at.date().isoformat()}.json", {}) or {}
    return int(b.get("tokens") or 0) >= int(b.get("limit") or os.environ.get("SW_LLM_DAILY_TOKENS", DAILY_TOKENS))


def machine_cap_spent(root: Path, ep: str) -> bool:
    d = read_json(ddir(root) / ep / "deadline.json", {}) or {}
    return bool(d) and float(d.get("machine_s", 0)) >= float(d.get("cap_s", MACHINE_CAP_H * 3600))


def parked(root: Path, state: dict, key: str, at: dt.datetime, ep: str | None = None) -> dict | None:
    """R-505: None = this key may run now. Otherwise {why, due}: it failed MAX_ATTEMPTS times today and no heal has rounds left, so it is backed off, never parked silently. It runs again
    when its code or inputs changed (forget_fixed_failures), else BACKOFF_H after the last failure, at most BACKOFF_MAX_PER_DAY extra times a day, and never past the 4 h machine cap or the
    day's token budget. `due` is None when only a change or a new day can free it. The next day starts with a fresh count."""
    ep = ep or key
    harvest = key.startswith("harvest:")
    a = state["attempts"].get(key) or {}
    if a.get("date") != at.date().isoformat() or int(a.get("n", 0)) < MAX_ATTEMPTS:
        return None
    if not harvest and heal_pending(root, ep, at):
        return None
    code = None if harvest else stop_code(root, ep)
    base = (f"the harvest of {ep}" if harvest else ep) + f" failed {MAX_ATTEMPTS} times today" + (f" ({code})" if code else "")
    if not harvest and machine_cap_spent(root, ep):
        return {"why": f"{base}: the 4 h machine cap of {ep} is spent, only the owner can extend it", "due": None}
    if tokens_spent(root, at):
        return {"why": f"{base}: today's token budget is spent, it resumes tomorrow", "due": None}
    if int(a.get("backoff_n", 0)) >= BACKOFF_MAX_PER_DAY:
        return {"why": f"{base} and {BACKOFF_MAX_PER_DAY} backoff retries: it waits for a code or plan change (the next tick sees it) or for tomorrow", "due": None}
    try:
        due = dt.datetime.fromisoformat(a["at"]) + dt.timedelta(hours=BACKOFF_H)
    except (KeyError, ValueError, TypeError):
        return None
    if at >= due:
        return None                                  # the backoff retry is due: run it
    return {"why": f"{base}: nothing changed since; next retry {due:%H:%M} (every {BACKOFF_H} h, or at once when tools/ or the plan change)", "due": due.isoformat(timespec="minutes")}


def write_fix_request(root: Path, ep: str, code: str | None, reason: str, at: dt.datetime, overwrite: bool = False) -> Path:
    """R-505: work/daily/<ep>/FIX-REQUEST.md, a precise request for the next human or Lead session: the stop code, the files it names, the numbers it measured and the heals that already ran.
    A Lead session may have written a better one (autopilot-lead.md asks for it): that one is kept unless `overwrite`. The board shows it in red until the episode builds."""
    p = ddir(root) / ep / FIX_REQUEST
    if p.is_file() and not overwrite:
        return p
    try:
        stopped = (ddir(root) / ep / "STOPPED.md").read_text(encoding="utf-8")
    except OSError:
        stopped = ""
    files = list(dict.fromkeys(re.findall(r"[A-Za-z0-9_./\\:-]+\.(?:py|json|md|txt|mp4|png)\b", stopped)))[:8]
    nums = list(dict.fromkeys(re.findall(r"\b\d+(?:\.\d+)?\s?(?:s|h|%|chars?|cps|ms)\b|[a-z_]+=\d+(?:\.\d+)?", stopped)))[:12]
    heals = [f.name for f in sorted((ddir(root) / ep).glob("*.json")) if "heal" in f.name or "refit" in f.name]
    body = (f"# FIX-REQUEST {ep}\n\nwritten {at:%Y-%m-%d %H:%M} by the autopilot\n\n- stop code: `{code or 'none recorded'}`\n- why the autopilot cannot go on: {reason}\n"
            f"- files named by the stop: {', '.join(files) or 'none (see STOPPED.md)'}\n- measured numbers in the stop note: {', '.join(nums) or 'none'}\n"
            f"- heals that already ran: {', '.join(heals) or 'none'} (work/daily/{ep}/)\n"
            f"- suggested change: fix the cause the stop names in tools/ or in the plan/script input, never a gate, a threshold, the critic bar, the 4 h cap or the token budget; the next tick then retries at once (the code fingerprint changes).\n\n"
            f"## stop note\n\n{stopped[:1800] or 'work/daily/' + ep + '/STOPPED.md is missing'}\n")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def resolve_fix_request(root: Path, ep: str) -> None:
    p = ddir(root) / ep / FIX_REQUEST
    if p.is_file():
        try:
            os.replace(p, p.with_name("FIX-REQUEST.resolved.md"))
        except OSError:
            pass


def forget_fixed_failures(root: Path, state: dict) -> None:
    """A failed episode whose script, plan or any other input file changed AFTER its last failure, or whose code (tools/, templates, heal.json: code_fingerprint) is not the code that failed,
    was fixed (by the Lead, the owner or a merge): its count goes, so the next tick tries it again at once (R-505; before, only script.json and calm-plan.json counted and a merged fix
    left the episode parked). Root cause (2026-10-29): one deterministic stop parked E04 for the day although the plan had been fixed minutes later."""
    fp = None
    for key, a in list(state.get("attempts", {}).items()):
        if not a.get("at"):
            continue
        if a.get("code_fp"):
            fp = fp or code_fingerprint(root)
            if a["code_fp"] != fp:
                state["attempts"].pop(key, None)
                continue
        if key.startswith("harvest:"):
            continue
        try:
            failed_at = dt.datetime.fromisoformat(a["at"]).timestamp()
        except ValueError:
            continue
        files = [p for p in Path(root).glob(f"bible/series/*/episodes/{key}/*") if p.is_file()]
        if any(p.stat().st_mtime > failed_at for p in files):
            state["attempts"].pop(key, None)


def decide(root: Path, at: dt.datetime, next_episode, state: dict | None = None) -> dict:
    """The one thing this run should do. {action, ep, why, due}. action: finish | harvest-next | build-next | stuck | idle.
    `next_episode(root)` is daily.next_episode. Pure given the files under root and the clock `at`."""
    root = Path(root)
    state = state if state is not None else load_state(root)
    forget_fixed_failures(root, state)
    unposted = loop_gate.started_unposted(root)
    for e in [x for x in unposted if build_complete(root, x)] + [x for x in [latest_posted(root)] if x]:       # R-507: a complete episode whose slot has passed is posted at once, however late
        pd = loop_gate.late_post_due(e, at, root)
        if pd["due"]:
            n = post_tries_today(state, e, at)
            if n >= POST_TRIES_PER_DAY:
                return {"action": "idle", "ep": e, "why": f"the post of {e} failed {n} times today (PUBLISH-FAILED stays red on the board); the next tries are tomorrow", "due": None}
            return {"action": "post", "ep": e, "why": pd["why"], "code": pd["code"], "due": None}
    open_eps = [e for e in unposted if not build_complete(root, e)]
    if open_eps:                                                                            # (a) finish the episode that is built but not complete
        ep = open_eps[-1]
        gate = loop_gate.check(ep, root, at=at)
        if not gate["allowed"]:                                                              # the loop gate holds: N+1 waits for N to be posted and harvested
            pre, due = gate.get("waiting_for"), (loop_gate.harvest_due_at(root, gate["waiting_for"]) if gate.get("waiting_for") else None)
            if gate["code"] == "WAIT-HARVEST" and due and at >= due:
                pk = parked(root, state, "harvest:" + pre, at, pre)
                if pk:
                    return {"action": "stuck", "ep": pre, **pk}
                return {"action": "harvest-next", "ep": pre, "next": ep, "why": f"{pre} is due for harvest ({due:%Y-%m-%d %H:%M}); then {ep} is finished", "due": due.isoformat(timespec="minutes")}
            return {"action": "idle", "ep": ep, "why": gate["why"], "due": due.isoformat(timespec="minutes") if due else None}
        pk = parked(root, state, ep, at)
        if pk:
            return {"action": "stuck", "ep": ep, **pk}
        return {"action": "finish", "ep": ep, "why": f"{ep} is built but not complete (critic, heal, retro): finishing it", "due": None}
    p = latest_posted(root)
    if p is None:
        return {"action": "idle", "ep": None, "why": "nothing has been posted yet: the first post is made by hand", "due": None}
    due = loop_gate.harvest_due_at(root, p)
    if not loop_gate.is_harvested(root, p):
        if due and at < due:
            return {"action": "idle", "ep": p, "why": f"{p} was posted; its harvest is due {due:%Y-%m-%d %H:%M}", "due": due.isoformat(timespec="minutes")}
        nxt = loop_gate.pick_episode(root, next_episode)
        pk = parked(root, state, "harvest:" + p, at, p)
        if pk:
            return {"action": "stuck", "ep": p, **pk}
        return {"action": "harvest-next", "ep": p, "next": nxt, "why": f"{p} is due for harvest ({due:%Y-%m-%d %H:%M}); then {nxt} is built", "due": due.isoformat(timespec="minutes")}
    nxt = loop_gate.pick_episode(root, next_episode)
    if loop_gate.is_posted(root, nxt):
        return {"action": "idle", "ep": nxt, "why": f"{nxt} is already posted", "due": None}
    pk = parked(root, state, nxt, at)
    if pk:
        return {"action": "stuck", "ep": nxt, **pk}
    if any(build_complete(root, e) for e in unposted):
        return {"action": "idle", "ep": unposted[-1], "why": f"{unposted[-1]} is complete and waits for the 19:00 post", "due": None}
    return {"action": "build-next", "ep": nxt, "why": f"{p} is harvested and {nxt} is not built: building it now", "due": None}


# ------------------------------------------------------------------ the launcher (pure; tools/autopilot.ps1 builds the same thing, a test keeps them equal)
def code_exe(code_on_path: str | None, localappdata: str | None) -> str | None:
    """Where VS Code starts from: `code` on PATH, else %LOCALAPPDATA%\\Programs\\Microsoft VS Code\\Code.exe."""
    if code_on_path:
        return code_on_path
    if localappdata:
        return str(Path(localappdata) / "Programs" / "Microsoft VS Code" / "Code.exe")
    return None


def launch_plan(root, uv: str, code_running: bool, code_on_path: str | None = None, localappdata: str | None = None) -> dict:
    """The commands of one launcher run: {vscode: argv | None, autopilot: argv, lead: argv, env: {...}}. vscode is None when Code.exe is already running."""
    exe = code_exe(code_on_path, localappdata)
    return {"vscode": None if code_running or not exe else [exe, str(root)],
            "autopilot": [uv, "run", "tools/daily.py", "autopilot"],
            "lead": [uv, "run", "tools/daily.py", "autopilot", "--lead"],
            "env": dict(LAUNCH_ENV)}


# ------------------------------------------------------------------ real steps (each injectable)
def run_child(cmd: list[str], timeout_s: float, cwd: Path, env: dict | None = None) -> tuple[int, str]:
    """Run one child to the end, in the foreground. On a timeout the whole tree is killed by the pid recorded here (taskkill /T), never by image name."""
    e = dict(os.environ)
    e.update({"PYTHONUTF8": "1", "SW_LLM_DAILY_TOKENS": os.environ.get("SW_LLM_DAILY_TOKENS", str(DAILY_TOKENS))})
    e.update(env or {})
    p = subprocess.Popen(cmd, cwd=str(cwd), env=e, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        out, _ = p.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            p.kill()
        out, _ = p.communicate()
        return 124, (out or "")[-4000:] + f"\nTIMEOUT after {timeout_s:.0f} s"
    return p.returncode, (out or "")[-4000:]


def real_harvest(root: Path, ep: str) -> dict:
    """The 14:00 harvest of one posted episode on every platform. {rc, status, notes[]}: comments, replies, the Instagram vote tally, the next brief, metrics, the learning
    review (ig_board.harvest_cycle), then the inbox (DMs and comments on every account, read only) and the live numbers. Only the decision (rc, decision.json) can stop the loop."""
    import ig_board
    notes = []
    rc = ig_board.harvest_cycle(root, go=True)
    try:
        r, out = run_child(["uv", "run", str(TOOLS / "inbox.py"), "harvest"], 1800, root)
        notes.append(f"inbox rc={r}")
    except Exception as e:     # noqa: BLE001  the inbox never stops the loop
        notes.append(f"inbox failed: {str(e)[:100]}")
    try:
        import live_numbers
        notes.append("live: " + live_numbers.summary_line(live_numbers.refresh_all(root)))
    except BaseException as e:     # noqa: BLE001
        notes.append(f"live numbers failed: {str(e)[:100]}")
    return {"rc": rc, "notes": notes}


def real_preview(root: Path, ep: str) -> str:
    """Give a finished episode its own tab in previews/index.html and open Edge at it (the owner 2026-10-28, R-496). Never raises, never blocks the build or the post."""
    try:
        if not (Path(root) / "work" / "episodes" / ep / "episode.mp4").is_file() or not (Path(root) / "previews" / "index.html").is_file():
            return "no episode video or preview page: tab skipped"
        import preview_tab
        return preview_tab.safe_add(Path(root), ep, open_=True)
    except BaseException as e:     # noqa: BLE001  a preview failure is logged, nothing else
        return f"preview tab failed: {str(e)[:120]}"


def real_build(root: Path, ep: str, force: str | None = None) -> tuple[int, str]:
    cmd = ["uv", "run", str(TOOLS / "daily.py"), "run", "--ep", ep, "--cap-hours", str(MACHINE_CAP_H)] + (["--force", force] if force else [])
    return run_child(cmd, CHILD_TIMEOUT_H * 3600, root)


def real_post(root: Path, ep: str) -> tuple[int, str]:
    """R-507: the Post task's own path for a complete episode whose slot has passed: `post_extra.py tick --late-ep E` = `daily.py post E --late --go` (Instagram, the Facebook Reel, the
    covers, YouTube, the stories, the first comment, the after-post steps; every publish gate), then the extras of every episode posted in the last 36 h. One post run at a time (post.lock)."""
    return run_child(["uv", "run", str(TOOLS / "post_extra.py"), "tick", "--late-ep", ep], POST_TIMEOUT_H * 3600, root)


def real_refit(root: Path, ep: str, line: str = "", shorter: bool = False) -> tuple[int, str]:
    """`daily.py refit --ep E [--line ID]`: reword the voiced lines whose take is over its slot (new ids), voice only those once, then run the stages again. Never touches a settled take."""
    cmd = ["uv", "run", str(TOOLS / "daily.py"), "refit", "--ep", ep, "--cap-hours", str(MACHINE_CAP_H)] + (["--line", line] if line else []) + (["--shorter"] if shorter else [])
    return run_child(cmd, CHILD_TIMEOUT_H * 3600, root)


# ------------------------------------------------------------------ one run
def status_line(at: dt.datetime, action: str, ep, rc: int, why: str) -> str:
    return f"{at:%Y-%m-%d %H:%M:%S} {action.upper()} {ep or '-'} rc={rc} {why}".replace("\n", " ")[:400]


def append_log(root: Path, line: str) -> None:
    """One line per tick. The task ticks every 15 min (R-505), so a run of identical IDLE / STUCK / LOCKED lines would bury the last real action: a line equal to the previous one except
    for its time replaces it (the log keeps the latest time) instead of being appended."""
    p = ddir(root) / LOG_NAME
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.is_file() and any(f" {w} " in line[:32] for w in ("IDLE", "STUCK", "LOCKED", "POST-WAIT")):
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except OSError:
            lines = []
        if lines and lines[-1][19:] == line[19:]:
            lines[-1] = line
            p.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return
    with open(p, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def record_failure(root: Path, state: dict, key: str, rc: int, at: dt.datetime) -> bool:
    """Count a failed run. Returns True when the cause is deterministic (no retry helps): the Lead is called instead."""
    code = stop_code(root, key)
    a = state["attempts"].get(key) if (state["attempts"].get(key) or {}).get("date") == at.date().isoformat() else {"date": at.date().isoformat(), "n": 0}
    was_parked = int(a.get("n", 0)) >= MAX_ATTEMPTS         # this run was a backoff retry (R-505)
    a["n"] = int(a.get("n", 0)) + 1
    if was_parked:
        a["backoff_n"] = int(a.get("backoff_n", 0)) + 1
    a["code_fp"] = code_fingerprint(root)
    healable = heal_pending(root, key, at)      # R-502 / R-503: an automatic heal cures it, so the stop is not terminal while the cure has rounds left
    terminal = rc in NO_RETRY_RC or (code is not None and code not in TRANSIENT and not healable)
    if healable and not terminal:
        a["n"] = min(a["n"], MAX_ATTEMPTS - 1)      # a heal in progress is progress, not a failure to count against the day
        a.update({"last_rc": rc, "last_code": code, "at": at.isoformat(timespec="seconds")})
        state["attempts"][key] = a
        return False
    if terminal:
        a["n"] = max(a["n"], MAX_ATTEMPTS)
    a.update({"last_rc": rc, "last_code": code, "at": at.isoformat(timespec="seconds")})
    state["attempts"][key] = a
    return terminal or a["n"] >= MAX_ATTEMPTS


def run_once(root: Path = ROOT, at: dt.datetime | None = None, *, next_episode, harvest=None, build=None, dry: bool = False, alive=pid_alive, pid: int | None = None,
             write_board=None, preview=None, poster=None, fixer_llm=None, daily_mod=None) -> tuple[int, str]:
    """One autopilot run: lock, decide, do it, log one line. Returns (exit code, the status line). Never posts."""
    root = Path(root)
    at = at or dt.datetime.now()
    harvest = harvest or (lambda ep: real_harvest(root, ep))
    build = build or (lambda ep: real_build(root, ep))
    preview = preview or (lambda ep: real_preview(root, ep))
    poster = poster or (lambda ep: real_post(root, ep))
    if dry:
        d = decide(root, at, next_episode)
        return 0, status_line(at, "dry-" + d["action"], d.get("ep"), 0, d["why"])
    if not lock_acquire(root, at, pid, alive):
        line = status_line(at, "locked", None, 0, "another autopilot run is in progress")
        append_log(root, line)
        return 0, line
    try:
        state = load_state(root)
        d = decide(root, at, next_episode, state)
        act, ep, rc, why = d["action"], d.get("ep"), 0, d["why"]
        task_status = "IDLE"
        state["parked"] = {}
        state["doing"] = None if act in ("idle", "stuck") else {"what": DOING.get(act, act), "ep": ep, "since": at.isoformat(timespec="minutes")}      # R-506: the Build panel says what is working right now
        save_state(root, state)
        publish_build(root, at)                                      # R-505: the board's Build panel shows "this tick started" before a long child runs
        if act == "idle":
            task_status = "WAIT" if d.get("due") else "IDLE"
        elif act == "stuck":
            task_status = "FAIL"
            todo_set(state, f"stuck:{ep}", f"{ep} is backed off ({why}). See {ep}'s FIX-REQUEST.md, work/daily/autopilot.log and work/daily/autopilot-lead-*.md.", at)
            state["parked"][ep] = {"why": why, "due": d.get("due"), "since": at.isoformat(timespec="minutes")}
            if not str(ep).startswith("harvest:") and (ddir(root) / ep).is_dir():
                write_fix_request(root, ep, stop_code(root, ep), why, at)       # never parked silently: a precise request waits for the next human or Lead session
                fx = try_fixer(root, state, ep, stop_code(root, ep), at, why, llm=fixer_llm, build=build, daily_mod=daily_mod)      # R-506: no heal left -> ONE bounded content fix, then the build runs again
                if fx:
                    rc, note = fx
                    why = f"{why}; {note}"
                    task_status = "OK" if rc == 0 else "FAIL"
                    if rc == 0:
                        state["parked"].pop(ep, None)
                        state["attempts"].pop(ep, None)
                        todo_clear(state, f"stuck:{ep}")
                        resolve_fix_request(root, ep)
        elif act == "post":              # R-507: a complete episode whose slot has passed goes out at once (never to the next day)
            prc, pout = poster(ep)
            rc = prc
            a = state["attempts"].get("post:" + ep) if (state["attempts"].get("post:" + ep) or {}).get("date") == at.date().isoformat() else {"date": at.date().isoformat(), "n": 0}
            a["n"] = int(a.get("n", 0)) + 1
            a["at"] = at.isoformat(timespec="seconds")
            on_ig = loop_gate.is_posted(root, ep)
            fb_open = bool(on_ig and loop_gate.has_fb_token() and loop_gate.fb_pending(root, ep, at))
            if prc == 0 and not on_ig:        # nothing was posted and nothing failed: no token, the gap since the last post, another post run holds the lock (the child said which)
                act, task_status, why = "post-wait", "WAIT", f"{ep} was due but not posted: {last_line(pout)}"
            elif prc == 0 and on_ig and not fb_open:
                task_status, why = "OK", f"posted {ep} ({d.get('code')}): {last_line(pout)}"
                state["attempts"].pop("post:" + ep, None)
                todo_clear(state, f"post:{ep}")
                why += f"; {preview(ep)}"                              # its preview tab is refreshed once the post is on record
            else:
                task_status = "FAIL"
                state["attempts"]["post:" + ep] = a
                why = f"{ep} late post {'partial' if on_ig else 'failed'} (rc {prc}, try {a['n']}/{POST_TRIES_PER_DAY}): {last_line(pout)}"
                todo_set(state, f"post:{ep}", f"PUBLISH-FAILED {ep}: {last_line(pout)} (try {a['n']}/{POST_TRIES_PER_DAY} today; the next tick tries again)", at)
                rc = rc or 1
        else:
            target = ep
            if act == "harvest-next":
                h = harvest(ep)
                decided = loop_gate.is_harvested(root, ep)
                if h.get("rc") == 1 or not decided:
                    terminal = record_failure(root, state, "harvest:" + ep, 1, at)
                    why = f"harvest of {ep} did not finish ({'decision.json missing' if not decided else 'FAIL'}); " + "; ".join(h.get("notes", []))
                    rc, act, task_status = (NEEDS_LEAD_RC if terminal and not lead_done(state, ep, "HARVEST", at) else 1), "harvest-failed", "FAIL"
                    todo_set(state, f"harvest:{ep}", f"The harvest of {ep} failed: {why[:200]}", at)
                    state["needs_lead"] = {"ep": ep, "code": "HARVEST", "since": at.isoformat(timespec="minutes")} if rc == NEEDS_LEAD_RC else state.get("needs_lead")
                    target = None
                else:
                    todo_clear(state, f"harvest:{ep}")
                    state["attempts"].pop("harvest:" + ep, None)
                    why = f"harvested {ep} ({'; '.join(h.get('notes', [])) or 'ok'})"
                    nxt = d.get("next")
                    if nxt and loop_gate.is_posted(root, nxt):
                        nxt = None
                    target = nxt
                    if nxt is not None and build_complete(root, nxt):
                        target, why = None, why + f"; {nxt} is already complete"
            if target:
                brc, out = build(target)
                rc = brc
                if brc == 0:
                    task_status, why = "OK", (why + "; " if act == "harvest-next" else "") + f"{target} run finished: {last_line(out)}"
                    state["attempts"].pop(target, None)
                    todo_clear(state, f"stuck:{target}")
                    resolve_fix_request(root, target)
                    try:
                        if build_complete(root, target):       # the episode passed every gate and the critic: its own preview tab, Edge opens at it (R-496)
                            why += f"; {preview(target)}"
                    except BaseException as e:     # noqa: BLE001  never blocks the build or the post
                        why += f"; preview failed: {str(e)[:80]}"
                else:
                    task_status = "FAIL"
                    terminal = record_failure(root, state, target, brc, at)
                    code = stop_code(root, target)
                    why = (why + "; " if act == "harvest-next" else "") + f"{target} stopped (rc {brc}{', ' + code if code else ''}): {last_line(out)}"
                    todo_set(state, f"stuck:{target}", f"{target} stopped at rc {brc} ({code or 'no stop code'}). The autopilot " + ("calls the Lead repair." if terminal else "retries at the next tick."), at)
                    if terminal and not lead_done(state, target, code or f"rc{brc}", at) and brc not in (3,):
                        rc = NEEDS_LEAD_RC
                        state["needs_lead"] = {"ep": target, "code": code or f"rc{brc}", "since": at.isoformat(timespec="minutes")}
                    elif terminal:
                        write_fix_request(root, target, code, f"rc {brc}; the Lead repair already ran for this stop code today: {last_line(out)}", at)
                        fx = try_fixer(root, state, target, code, at, why, llm=fixer_llm, build=build, daily_mod=daily_mod)      # R-506: no heal and no Lead action left -> ONE bounded content fix
                        if fx:
                            rc, note = fx
                            why += f"; {note}"
                            if rc == 0:
                                task_status = "OK"
                                state["attempts"].pop(target, None)
                                todo_clear(state, f"stuck:{target}")
                                resolve_fix_request(root, target)
                if act == "harvest-next":
                    act = "harvest+build"
        line = status_line(at, act, ep, rc, why)
        append_log(root, line)
        state["doing"] = None
        state["last"] = {"at": at.isoformat(timespec="seconds"), "action": act, "ep": ep, "rc": rc, "status": task_status, "line": line}
        save_state(root, state)
        loop_gate.write_task_status(root, "StoryWrap-Autopilot", task_status, why, at)
        publish_build(root, at)
        if write_board is None:
            try:
                import ig_board
                ig_board.write_all(root)
            except BaseException as e:     # noqa: BLE001  the board is a courtesy: a failure to refresh it never changes the run
                print(f"board not refreshed: {str(e)[:120]}", file=sys.stderr)
        else:
            write_board(root)
        return rc, line
    finally:
        lock_release(root, pid)


def publish_build(root: Path, at: dt.datetime | None = None) -> None:
    """Write board/data/build.json and build.js (tools/build_status.py): the Build panel at the top of the board. Cheap, files only, never raises."""
    try:
        import build_status
        build_status.write(root, at)
    except BaseException as e:     # noqa: BLE001  the board is a courtesy
        print(f"build status not written: {str(e)[:120]}", file=sys.stderr)


def last_line(out: str) -> str:
    lines = [l.strip() for l in (out or "").splitlines() if l.strip()]
    return (lines[-1] if lines else "no output")[:200]


# ------------------------------------------------------------------ the Lead repair (one headless Sonnet session, one bounded action)
LEAD_ACTIONS = ("rerun", "rerun-stage", "refit-line", "give-up")


def parse_lead_decision(text: str) -> dict:
    """{action, stage, reason} from the Lead's decision file, or give-up when it is missing, unreadable, unknown or asks for a stage that must not be forced."""
    try:
        j = json.loads(text)
    except (ValueError, TypeError):
        return {"action": "give-up", "stage": None, "reason": "decision file unreadable"}
    act = j.get("action") if isinstance(j, dict) else None
    if act not in LEAD_ACTIONS:
        return {"action": "give-up", "stage": None, "reason": f"unknown action {act!r}"}
    stage = j.get("stage")
    if act == "refit-line":         # R-502: reword the voiced line(s) over their slot under a new id and voice only those (daily.py refit); `stage` carries an optional line id
        line = str(j.get("line") or stage or "").strip()
        return {"action": act, "stage": None, "line": line if re.fullmatch(r"[A-Za-z0-9]{1,12}", line) else "", "reason": str(j.get("reason") or "")[:300]}
    if act == "rerun-stage" and stage not in LEAD_FORCE_STAGES:
        return {"action": "give-up", "stage": None, "reason": f"stage {stage!r} may not be forced (allowed: {', '.join(LEAD_FORCE_STAGES)})"}
    return {"action": act, "stage": stage if act == "rerun-stage" else None, "line": "", "reason": str(j.get("reason") or "")[:300]}


def lead_prompt(root: Path, ep: str, code: str, at: dt.datetime, out_md: Path, out_json: Path) -> str:
    tpl = (TOOLS / "templates" / "autopilot-lead.md").read_text(encoding="utf-8")
    return tpl.format(ep=ep, code=code, date=at.date().isoformat(), out_md=out_md.as_posix(), out_json=out_json.as_posix(), fix_request=(ddir(root) / ep / FIX_REQUEST).as_posix(), log=(ddir(root) / LOG_NAME).as_posix(),
                      stopped=(ddir(root) / ep / "STOPPED.md").as_posix(), state=(ddir(root) / STATE_NAME).as_posix())


def lead_once(root: Path = ROOT, at: dt.datetime | None = None, *, daily_mod=None, llm=None, build=None, refit=None, fixer_llm=None) -> tuple[int, str]:
    """The Lead repair, at most once per episode per day: one headless Sonnet session (daily.run_claude: the flags of daily.build_cmd, NJ_ROLE=job, permission-mode dontAsk,
    capped turns and budget, no shell, no Agent) reads handoff.md and the log and writes work/daily/autopilot-lead-<date>.md and .json; the autopilot then executes the ONE action
    in the decision file (rerun, rerun-stage with a stage in LEAD_FORCE_STAGES, refit-line, or give-up) through daily.py. It never commits, posts or loosens a gate."""
    root = Path(root)
    at = at or dt.datetime.now()
    if not lock_acquire(root, at):
        return 0, status_line(at, "lead-locked", None, 0, "another autopilot run is in progress")
    try:
        state = load_state(root)
        need = state.get("needs_lead") or {}
        ep = need.get("ep")
        if not ep or lead_done(state, ep, need.get("code"), at):
            line = status_line(at, "lead-skip", ep, 0, "no Lead repair is pending (or it already ran for this episode and stop code today)")
            append_log(root, line)
            return 0, line
        state["lead"][lead_key(ep, need.get("code"))] = at.date().isoformat()                       # recorded BEFORE the session: a crash never repeats it
        fr_path = ddir(root) / ep / FIX_REQUEST
        fr_before = fr_path.stat().st_mtime if fr_path.is_file() else 0.0
        save_state(root, state)
        out_md = ddir(root) / f"autopilot-lead-{at.date().isoformat()}.md"
        out_json = out_md.with_suffix(".json")
        for p in (out_md, out_json):
            if p.exists():
                p.unlink()
        if llm is None:
            dm = daily_mod or __import__("daily")
            llm = lambda prompt, name: dm.run_claude(prompt, name=name, tools="Read,Glob,Grep,Write,Edit", root=root, expect=(out_md, out_json), timeout=1800,       # noqa: E731
                                                     effort="medium", write_allow="work/daily/**", budget=dm.Budget(root, limit=int(os.environ.get("SW_LLM_DAILY_TOKENS", DAILY_TOKENS))))
        r = llm(lead_prompt(root, ep, need.get("code", "?"), at, out_md, out_json), f"autopilot-lead-{ep}")
        dec = parse_lead_decision(out_json.read_text(encoding="utf-8")) if (r.get("rc") == 0 and out_json.is_file()) else {"action": "give-up", "stage": None, "reason": f"the Lead session ended rc {r.get('rc')}"}
        rc, done = 0, f"gave up: {dec['reason']}"
        if dec["action"] == "refit-line":
            refit = refit or (lambda e, line="": real_refit(root, e, line))
            rc, out = refit(ep, dec.get("line", ""))
            done = f"refit-line{' ' + dec['line'] if dec.get('line') else ''} -> rc {rc}: {last_line(out)}"
            if rc == 0:
                state["attempts"].pop(ep, None)
                todo_clear(state, f"stuck:{ep}")
                resolve_fix_request(root, ep)
        elif dec["action"] in ("rerun", "rerun-stage"):
            build = build or (lambda e, force=None: real_build(root, e, force))
            rc, out = build(ep, dec["stage"])
            done = f"{dec['action']}{' ' + dec['stage'] if dec['stage'] else ''} -> rc {rc}: {last_line(out)}"
            if rc == 0:
                state["attempts"].pop(ep, None)
                todo_clear(state, f"stuck:{ep}")
                resolve_fix_request(root, ep)
        else:
            todo_set(state, f"stuck:{ep}", f"The Lead repair of {ep} gave up ({dec['reason']}); see {out_md.name} and {ep}'s FIX-REQUEST.md.", at)
            if not (fr_path.is_file() and fr_path.stat().st_mtime > fr_before):       # the Lead session wrote none: the autopilot writes the precise request itself (R-505)
                write_fix_request(root, ep, need.get("code"), f"the Lead repair gave up: {dec['reason']}", at, overwrite=True)
            fx = try_fixer(root, state, ep, need.get("code"), at, dec["reason"], llm=fixer_llm, build=build, daily_mod=daily_mod)      # R-506: the Lead has no action left -> ONE bounded content fix
            if fx:
                rc, note = fx
                done += f"; {note}"
                if rc == 0:
                    state["attempts"].pop(ep, None)
                    todo_clear(state, f"stuck:{ep}")
                    resolve_fix_request(root, ep)
        with open(out_md, "a", encoding="utf-8") as fh:
            fh.write(f"\n\n## executed by the autopilot ({at:%H:%M:%S})\n\n{done}\n")
        state["needs_lead"] = None
        line = status_line(at, "lead", ep, rc, done)
        append_log(root, line)
        state["last"] = {"at": at.isoformat(timespec="seconds"), "action": "lead", "ep": ep, "rc": rc, "status": "OK" if rc == 0 else "FAIL", "line": line}
        save_state(root, state)
        loop_gate.write_task_status(root, "StoryWrap-Autopilot", "OK" if rc == 0 else "FAIL", done, at)
        publish_build(root, at)
        return rc, line
    finally:
        lock_release(root)


# ------------------------------------------------------------------ the general fixer (R-506): a stop with no specific heal left gets ONE bounded headless content fix, then the build runs again
FIXER_READ_ONLY = ("narration-manifest.json",)      # files the fixer must leave byte for byte as they were (the voice record)


def fixer_key(ep: str, code: str | None) -> str:
    return f"{ep}|{code or '?'}"


def fixer_done(state: dict, ep: str, code: str | None, at: dt.datetime) -> bool:
    """Once per (episode, stop code) per day, and at most FIXER_MAX_PER_EP_DAY sessions for one episode in a day (a runaway guard)."""
    today = at.date().isoformat()
    mine = [k for k, v in state["fixer"].items() if k.startswith(ep + "|") and v == today]
    return state["fixer"].get(fixer_key(ep, code)) == today or len(mine) >= FIXER_MAX_PER_EP_DAY


def tokens_left(root: Path, at: dt.datetime) -> int:
    b = read_json(ddir(root) / f"budget-{at.date().isoformat()}.json", {}) or {}
    return int(b.get("limit") or os.environ.get("SW_LLM_DAILY_TOKENS", DAILY_TOKENS)) - int(b.get("tokens") or 0)


def episode_files(root: Path, ep: str) -> Path | None:
    hits = sorted(Path(root).glob(f"bible/series/*/episodes/{ep}"))
    return hits[0] if hits else None


def snapshot_episode(edir: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(Path(edir).glob("*")) if p.is_file() and p.suffix in (".json", ".txt", ".md")}


def fixer_problems(before: dict[str, bytes], after: dict[str, bytes]) -> list[str]:
    """What the fixer did that it may not: a line's id, text, tts_text or speaker changed, a line added or removed, the voice record touched. [] = its edits stay inside the limits."""
    out = []
    for n in FIXER_READ_ONLY:
        if before.get(n) != after.get(n):
            out.append(f"{n} was changed")
    try:
        a, b = json.loads(before["script.json"].decode("utf-8")), json.loads(after["script.json"].decode("utf-8"))
        la, lb = {l["id"]: l for l in a["lines"]}, {l["id"]: l for l in b["lines"]}
        if list(la) != list(lb):
            out.append("script.json: a line was added, removed or reordered")
        for i, l in la.items():
            m = lb.get(i)
            if m and any(l.get(k) != m.get(k) for k in ("text", "tts_text", "speaker")):
                out.append(f"script.json: line {i} was reworded (a voiced line is never changed; a shorter one goes through refit_lines)")
    except (KeyError, ValueError, TypeError, UnicodeDecodeError) as e:
        out.append(f"script.json unreadable after the fix: {e}")
    return out


def rel(root: Path, p: Path) -> str:
    try:
        return Path(p).relative_to(root).as_posix()
    except ValueError:
        return Path(p).as_posix()


def fixer_prompt(root: Path, ep: str, code: str, at: dt.datetime, out_md: Path, out_json: Path, edir: Path) -> str:
    tpl = (TOOLS / "templates" / "autopilot-fixer.md").read_text(encoding="utf-8")
    return tpl.format(ep=ep, code=code, date=at.date().isoformat(), out_md=out_md.as_posix(), out_json=out_json.as_posix(), stopped=(ddir(root) / ep / "STOPPED.md").as_posix(),
                      fix_request=(ddir(root) / ep / FIX_REQUEST).as_posix(), ep_dir=rel(root, edir), plan=(edir / "calm-plan.json").as_posix(), script=(edir / "script.json").as_posix())


def parse_fixer_decision(text: str, line_ids: set[str]) -> dict:
    try:
        j = json.loads(text)
    except (ValueError, TypeError):
        return {"fixed": False, "changes": [], "refit_lines": [], "reason": "decision file unreadable"}
    if not isinstance(j, dict):
        return {"fixed": False, "changes": [], "refit_lines": [], "reason": "decision file is not an object"}
    lines = [str(x) for x in (j.get("refit_lines") or []) if str(x) in line_ids][:2]
    return {"fixed": bool(j.get("fixed")), "changes": [str(c)[:200] for c in (j.get("changes") or [])][:8], "refit_lines": lines, "reason": str(j.get("reason") or "")[:300]}


def record_fixer(root: Path, ep: str, event: dict) -> None:
    """work/daily/<ep>/fixer.json (the board's Build panel lists it) and one lessons-ledger entry."""
    p = ddir(root) / ep / FIXER_NAME
    rec = read_json(p, {}) or {}
    rec.setdefault("events", []).append(event)
    rec["rounds"] = len(rec["events"])
    rec["exhausted"] = None
    loop_gate.write_json(p, rec)
    try:
        import learn
        learn.add_lessons(root, ep, [{"summary": f"{ep} stopped at {event['code']}; the fixer {('changed ' + '; '.join(event['changes'])) if event.get('changes') else 'changed nothing'} -> {event['result']}",
                                      "fault": event["code"], "class": "PROCESS",
                                      "root_cause": "a new kind of stop had no specific heal, so the episode would have waited for a human",
                                      "fix": "autopilot.try_fixer: one bounded headless content fix (plan, caption cuts, a shorter line through line_refit), then daily.py run again", "check": event["code"]}],
                          "fixer", event["at"][:10])
    except Exception as e:     # noqa: BLE001  the ledger is a record; it never blocks a run
        print(f"fixer ledger entry failed: {str(e)[:100]}", file=sys.stderr)


def try_fixer(root: Path, state: dict, ep: str, code: str | None, at: dt.datetime, why: str, *, llm=None, build=None, refit=None, daily_mod=None, validate=None) -> tuple[int, str] | None:
    """R-506. None = the fixer does not run (a specific heal still has rounds, it already ran for this stop code today or 3 times for this episode, the day's token budget has under
    FIXER_MIN_TOKENS left, the 4 h machine cap is spent, no stop code or no episode). Otherwise one headless Sonnet session (daily.run_claude: NJ_ROLE=job, dontAsk, capped turns and budget,
    no shell, no Agent) that may write only under the episode's data folder and work/daily/<ep>/ reads STOPPED.md and FIX-REQUEST.md and makes one content fix; the autopilot then rolls back
    anything outside the limits (fixer_problems), validates the plan, has the listed lines refitted (daily.py refit --shorter) and runs `daily.py run` again. Returns (rc of that run, note)."""
    root = Path(root)
    edir = episode_files(root, ep)
    if not code or edir is None or ":" in ep or heal_pending(root, ep, at) or fixer_done(state, ep, code, at):
        return None
    if tokens_left(root, at) < FIXER_MIN_TOKENS or machine_cap_spent(root, ep):
        return None
    state["fixer"][fixer_key(ep, code)] = at.date().isoformat()                       # recorded BEFORE the session: a crash never repeats it
    state["doing"] = {"what": f"the fixer is fixing {code}", "ep": ep, "since": at.isoformat(timespec="minutes")}
    save_state(root, state)
    publish_build(root, at)
    n = sum(1 for v in state["fixer"].values() if v == at.date().isoformat())
    out_md = ddir(root) / ep / f"fixer-{at.date().isoformat()}-{n}.md"
    out_json = out_md.with_suffix(".json")
    for q in (out_md, out_json):
        if q.exists():
            q.unlink()
    before = snapshot_episode(edir)
    dm = daily_mod or __import__("daily")
    if llm is None:
        wallow = f"{rel(root, edir)}/**,work/daily/{ep}/**"
        llm = lambda prompt, name: dm.run_claude(prompt, name=name, tools="Read,Glob,Grep,Write,Edit", root=root, expect=(out_md, out_json), timeout=1800, effort="medium",      # noqa: E731
                                                 write_allow=wallow, budget=dm.Budget(root, limit=int(os.environ.get("SW_LLM_DAILY_TOKENS", DAILY_TOKENS))))
    event = {"at": at.isoformat(timespec="seconds"), "code": code, "changes": [], "refit_lines": [], "result": "", "reason": ""}
    try:
        r = llm(fixer_prompt(root, ep, code, at, out_md, out_json, edir), f"autopilot-fixer-{ep}")
    except Exception as e:     # noqa: BLE001  a budget or claude failure ends the pass, not the autopilot
        r = {"rc": 1, "err": str(e)[:200]}
    ids = set()
    try:
        ids = {l["id"] for l in json.loads(before["script.json"].decode("utf-8"))["lines"]}
    except (KeyError, ValueError, TypeError):
        pass
    if r.get("rc") == 0 and out_json.is_file():
        dec = parse_fixer_decision(out_json.read_text(encoding="utf-8"), ids)
    else:
        dec = {"fixed": False, "changes": [], "refit_lines": [], "reason": f"the fixer session ended rc {r.get('rc')}"}
    after = snapshot_episode(edir)
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    bad = fixer_problems(before, after) if changed else []
    if not bad and changed:
        try:
            if validate is None:
                ctx = dm.Ctx(ep, root=root)
                bad = [b for b in dm.validate_episode_files(ctx) if not b.startswith("PLAN-DURATION")]
                if not bad:
                    dm.restamp(ctx, "script")              # a verified edit of the script stage's outputs, not a hand edit (the healer's way)
            else:
                bad = validate(ep)
        except Exception as e:     # noqa: BLE001
            bad = [f"validation failed: {str(e)[:150]}"]
    if bad:
        for k in changed:      # rolled back byte for byte: the files in the episode's data folder as they were
            if k in before:
                (edir / k).write_bytes(before[k])
            elif (edir / k).exists():
                (edir / k).unlink()
        event.update({"changes": [], "result": "rolled back: " + "; ".join(bad[:3])[:300], "reason": dec["reason"]})
        record_fixer(root, ep, event)
        return 1, f"the fixer's edits were rolled back ({'; '.join(bad[:2])[:200]})"
    cap_cuts = (ddir(root) / ep / "cap-heal.json")
    wrote_heal = cap_cuts.is_file() and cap_cuts.stat().st_mtime >= at.timestamp() - 2
    event.update({"changes": dec["changes"] or [f"{k} changed" for k in changed] + (["cap-heal.json written"] if wrote_heal else []), "refit_lines": dec["refit_lines"], "reason": dec["reason"]})
    if not (changed or dec["refit_lines"] or wrote_heal or dec["fixed"]):
        event.update({"result": f"nothing to fix inside its limits: {dec['reason']}", "changes": []})
        record_fixer(root, ep, event)
        return 1, f"the fixer changed nothing ({dec['reason'] or 'no reason given'})"
    refit = refit or (lambda e, line: real_refit(root, e, line, shorter=True))
    for ln in dec["refit_lines"]:
        rrc, rout = refit(ep, ln)
        event.setdefault("refit_results", []).append(f"{ln}: rc {rrc}")
        if rrc != 0:
            event.update({"result": f"refit of {ln} failed (rc {rrc}): {last_line(rout)}"})
            record_fixer(root, ep, event)
            return rrc, event["result"]
    build = build or (lambda e: real_build(root, e))
    state["doing"] = {"what": f"building {ep} again after the fixer", "ep": ep, "since": at.isoformat(timespec="minutes")}
    save_state(root, state)
    publish_build(root, at)
    brc, bout = build(ep)
    event["result"] = f"daily.py run -> rc {brc}: {last_line(bout)}"
    record_fixer(root, ep, event)
    return brc, f"fixer ({'; '.join(event['changes'])[:160] or 'refit'}) then {event['result']}"


# ------------------------------------------------------------------ entry
def main(argv=None, daily_mod=None) -> int:
    ap = argparse.ArgumentParser(prog="autopilot.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("cmd", nargs="?", default="run", choices=["run", "decide", "plan"])
    ap.add_argument("--dry", action="store_true", help="say what would be done; change nothing, take no lock")
    ap.add_argument("--lead", action="store_true", help="run the pending Lead repair (the launcher starts this after exit code 6)")
    ap.add_argument("--code-running", action="store_true")
    ap.add_argument("--code-path")
    a = ap.parse_args(argv)
    dm = daily_mod or __import__("daily")
    if a.cmd == "plan":
        print(json.dumps(launch_plan(ROOT, "uv", a.code_running, a.code_path, os.environ.get("LOCALAPPDATA")), indent=1))
        return 0
    if a.cmd == "decide" or a.dry:
        rc, line = run_once(ROOT, next_episode=dm.next_episode, dry=True)
        print(line)
        return 0
    os.environ.setdefault("SW_LLM_DAILY_TOKENS", str(DAILY_TOKENS))
    rc, line = lead_once(ROOT, daily_mod=dm) if a.lead else run_once(ROOT, next_episode=dm.next_episode, daily_mod=dm)
    print(line)
    return rc


if __name__ == "__main__":
    sys.exit(main())
