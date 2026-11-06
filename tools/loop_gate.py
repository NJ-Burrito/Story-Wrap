# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""The audience LOOP GATE and the post-time rules (owner, 2026-10-25: schedule the Instagram loop).

    uv run tools/loop_gate.py check <ep>      may episode <ep> be produced now? (exit 0 either way; the answer is printed and written)
    uv run tools/loop_gate.py slot  <ep>      today's post time for <ep>
    uv run tools/loop_gate.py status          what each scheduled task last said (work/daily/tasks/*.json)

LOOP GATE: production of episode N+1 waits until episode N was POSTED (work/episodes/N/post.json) and HARVESTED
(work/episodes/N/decision.json, written by the harvest at 14:00 Amman the day after the post). The first episode has no predecessor and is free.
Without an Instagram token nothing can be posted, so production stops after ONE finished episode (it never runs ahead
by more than one): E02 waits for E01 to be posted. A wait is a clean answer (exit 0), not a failure.

POST SLOT (owner, 2026-10-27, replaces 19:30 / 20:30): 19:00 Amman on every platform. Instagram, the Facebook Reel and YouTube go out in the same Post run.
A post happens only when the episode was READY (gates PASS, critic 9+) by the slot and the tick is inside the retry window after it (POST_GRACE_MIN); an episode
that is not ready at 19:00 waits for the next 19:00, it never posts off-slot. Never less than 20 h after the last post.
HARVEST (owner, 2026-10-27): 14:00 Amman the day after the later post (harvest_due_at); the 24 h pass feeds ideas only.

Standard library only. No network, no git, nothing left running.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(os.environ.get("STORYWRAP_ROOT") or Path(__file__).resolve().parents[1])
CONF = Path(os.environ.get("SW_IG_ENV") or Path.home() / ".config" / "story-wrap" / "instagram.env")

HARVEST_AT = dt.time(14, 0)          # the owner 2026-10-27: the harvest is due at 14:00 Amman the day after the LATER post (was: 12 h after it)
HARVEST_DAY_OFFSET = 1
LATE_IDEAS_AFTER_H = 24              # DESIGN 6.4: a second pass feeds ideas only
SLOT_START_MIN = 19 * 60             # 19:00 Amman on every platform (the owner 2026-10-27; was Instagram 19:30, Facebook 20:30)
POST_GRACE_MIN = 90                  # the Post task ticks every 5 min from the slot to 20:25: a failed attempt is retried inside this window, never after it
POST_CUTOFF = dt.time(20, 30)        # = slot + POST_GRACE_MIN (a test keeps them equal): after this the day's slot is missed, WAIT-LATE until tomorrow's 19:00
FB_SLOT_OFFSET_MIN = 0               # the Facebook Reel goes live in the same Post run, at once after Instagram (the owner 2026-10-27: one time for every platform)
MIN_GAP_H = 20.0                     # never two posts closer than this
MIDNIGHT_CROSS_END = dt.time(6, 0)   # R-507: a post made before this on the calendar day after its slot day still counts as that slot day's post
HARVEST_MIN_AFTER_H = 12.0           # R-507: the harvest is never due sooner than this after the post
TASK_NAMES = ("StoryWrap-Autopilot", "StoryWrap-Post", "StoryWrap-Harvest", "StoryWrap-Board", "StoryWrap-Health")


# ------------------------------------------------------------------ small helpers
def read_json(p: Path):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return None


def replace_retry(src, dst, tries: int = 8) -> None:
    """os.replace that survives a moment of Windows file locking (WinError 5/32 while an antivirus scan or a reader holds the target): a few short retries, then the
    original error. The temp file is written completely before this runs, so a retry never publishes half a file."""
    import time
    for i in range(tries):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == tries - 1:
                raise
            time.sleep(0.05 * (i + 1))


def write_json(p: Path, d) -> None:
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    replace_retry(tmp, p)


def local(t: dt.datetime) -> dt.datetime:
    """Any datetime as naive local time (post.json stores an aware UTC time)."""
    return t.astimezone().replace(tzinfo=None) if t.tzinfo else t


def parse_time(s: str) -> dt.datetime:
    return local(dt.datetime.fromisoformat(s))


EP_ID = re.compile(r"^([A-Za-z]+)(\d+)([A-Z]?)$")      # E02, and a suffixed cut such as E01C (the calm cut of E01)


def prev_ep(ep: str) -> str | None:
    """The arithmetic predecessor: E02 -> E01, E02C -> E01, E01 and E01C -> None."""
    m = EP_ID.match(ep)
    if not m or int(m.group(2)) <= 1:
        return None
    return f"{m.group(1)}{int(m.group(2)) - 1:0{len(m.group(2))}d}"


def predecessor(root: Path, ep: str) -> str | None:
    """The episode <ep> must wait for: the latest POSTED or ADOPTED episode with a lower number (E01C when E01 was never posted), else the arithmetic one.
    Not hard-coded to any id: whichever episode the pipeline last posted or adopted is the one the audience loop continues from."""
    m = EP_ID.match(ep)
    wd = Path(root) / "work" / "episodes"
    if not m or not wd.is_dir():
        return prev_ep(ep)
    best = None
    for d in wd.iterdir():
        k = EP_ID.match(d.name)
        if not k or k.group(1) != m.group(1) or int(k.group(2)) >= int(m.group(2)):
            continue
        if (d / "post.json").is_file() or (d / "adopted.json").is_file():
            key = (int(k.group(2)), k.group(3))
            if best is None or key > best[0]:
                best = (key, d.name)
    return best[1] if best else prev_ep(ep)


def has_token(env_path: Path | None = None) -> bool:
    """True when the credentials file holds both keys. The values are never read out or printed."""
    p = Path(env_path or CONF)
    if not p.is_file():
        return False
    keys = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            keys[k.strip()] = v.strip().strip('"').strip("'")
    return bool(keys.get("IG_ACCESS_TOKEN") and keys.get("IG_USER_ID"))


def has_fb_token(env_path: Path | None = None) -> bool:
    """True when the credentials file holds FB_PAGE_ID and FB_PAGE_TOKEN (the Facebook Page). The values are never read out or printed."""
    p = Path(env_path or CONF)
    if not p.is_file():
        return False
    keys = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            keys[k.strip()] = v.strip().strip('"').strip("'")
    return bool(keys.get("FB_PAGE_ID") and keys.get("FB_PAGE_TOKEN"))


FB_RETRY_WITHIN_H = 36      # an episode older than this on Instagram is never back-filled to Facebook by the scheduled Post task


def fb_recorded(root: Path, ep: str) -> bool:
    """Any facebook.json counts, a pending ("finishing") or unreadable one included: Facebook is never posted over a record."""
    return (ep_work(root, ep) / "facebook.json").is_file()


def fb_pending(root: Path, ep: str, at: dt.datetime | None = None) -> bool:
    """Instagram posted within the last FB_RETRY_WITHIN_H hours but Facebook not yet: the Facebook half is retried (episodes from before Facebook was wired in are left alone)."""
    t = posted_at(root, ep)
    if not t or ((at or dt.datetime.now()) - t).total_seconds() > FB_RETRY_WITHIN_H * 3600:
        return False
    return not fb_recorded(root, ep)


# ------------------------------------------------------------------ episode state
def ep_work(root: Path, ep: str) -> Path:
    return Path(root) / "work" / "episodes" / ep


def posted_at(root: Path, ep: str) -> dt.datetime | None:
    post = read_json(ep_work(root, ep) / "post.json")
    return parse_time(post["posted_at"]) if post and post.get("posted_at") else None


def later_post_at(root: Path, ep: str) -> dt.datetime | None:
    """The later of the Instagram post time and the Facebook go-live time (its scheduled time, else its post time). None while Instagram is not posted:
    the vote source is Instagram, so nothing is harvested without it."""
    t = posted_at(root, ep)
    if not t:
        return None
    fbr = read_json(ep_work(root, ep) / "facebook.json")
    try:
        f = parse_time((fbr or {}).get("publish_at") or (fbr or {}).get("posted_at") or "")
    except ValueError:
        f = None
    return max(t, f) if f else t


def slot_day(t: dt.datetime) -> dt.date:
    """The day a post was FOR: a post made after midnight but before MIDNIGHT_CROSS_END is a late post of the day before (R-507: a build that finished past 00:00 posts at once)."""
    return t.date() - dt.timedelta(days=1) if t.time() < MIDNIGHT_CROSS_END else t.date()


def harvest_due_at(root: Path, ep: str) -> dt.datetime | None:
    """14:00 Amman on the day after the later post (the owner 2026-10-27); R-507: counted from the day the post was FOR (a post at 01:00 belongs to the evening before, so its harvest is
    14:00 the same calendar day), and never less than HARVEST_MIN_AFTER_H after the post itself (a post at 05:00 is harvested at 17:00, not at 14:00)."""
    t = later_post_at(root, ep)
    if not t:
        return None
    return max(dt.datetime.combine(slot_day(t) + dt.timedelta(days=HARVEST_DAY_OFFSET), HARVEST_AT), t + dt.timedelta(hours=HARVEST_MIN_AFTER_H))


def is_posted(root: Path, ep: str) -> bool:
    return (ep_work(root, ep) / "post.json").is_file()


def is_harvested(root: Path, ep: str) -> bool:
    return (ep_work(root, ep) / "decision.json").is_file()


def ready_at(root: Path, ep: str) -> dt.datetime | None:
    """When the episode became postable: the newest of the gate report, the critic verdict and the video. None when any is missing (not ready at all)."""
    w = ep_work(root, ep)
    files = [w / "gate" / "report.json", w / "heal" / "critic.json", w / "episode.mp4"]
    if not all(f.is_file() for f in files):
        return None
    return max(dt.datetime.fromtimestamp(f.stat().st_mtime) for f in files)


def is_finished(root: Path, ep: str) -> bool:
    """Gates passed and critic >= 9 (the same facts ig.publish_gates checks), without importing it."""
    w = ep_work(root, ep)
    rep, cr = read_json(w / "gate" / "report.json"), read_json(w / "heal" / "critic.json")
    return bool(rep and rep.get("verdict") == "PASS" and rep.get("complete") is not False and cr and isinstance(cr.get("score"), int)
                and (cr["score"] >= 9 or owner_approved(w, cr)) and (w / "episode.mp4").is_file())


def owner_approved(w: Path, cr: dict | None) -> bool:
    """Owner override (owner, 2026-10-27 E02 and 2026-10-28 E03, both at critic 8): heal/owner-approval.json naming this exact critic score and the video the critic judged lets
    the episode post below 9. The same rule as ig.publish_gates; every gate still applies."""
    ok = read_json(w / "heal" / "owner-approval.json") or {}
    return bool(cr and ok.get("by") == "the owner" and isinstance(cr.get("score"), int) and ok.get("score") == cr["score"] and ok.get("video_sha")
                and ok["video_sha"] == cr.get("video_sha"))


# ------------------------------------------------------------------ the loop gate
def check(ep: str, root: Path = ROOT, token: bool | None = None, at: dt.datetime | None = None, prev: str | None = None) -> dict:
    """May episode <ep> be produced? {allowed, code, why, waiting_for, due}. code: OPEN | WAIT-POST | WAIT-HARVEST."""
    root = Path(root)
    token = has_token() if token is None else token
    at = at or dt.datetime.now()
    p = prev or predecessor(root, ep)       # `prev` names the predecessor when the ids do not count (E01C is the calm cut of E01)
    if p is None:
        return {"episode": ep, "allowed": True, "code": "OPEN", "why": "first episode: no predecessor", "waiting_for": None, "due": None}
    if not is_posted(root, p):
        extra = "" if token else " No Instagram token yet, so nothing can be posted: production stays at one finished episode."
        ready = " It is finished and ready to post." if is_finished(root, p) else " It is not finished yet."
        return {"episode": ep, "allowed": False, "code": "WAIT-POST", "waiting_for": p, "due": None,
                "why": f"{ep} waits: {p} has not been posted.{ready}{extra}"}
    if not is_harvested(root, p):
        due = harvest_due_at(root, p)
        late = " The harvest is overdue (the Harvest task or the token needs a look)." if due and at >= due else ""
        return {"episode": ep, "allowed": False, "code": "WAIT-HARVEST", "waiting_for": p, "due": due.isoformat(timespec="minutes") if due else None,
                "why": f"{ep} waits: {p} was posted but its comments are not harvested yet (due {due:%Y-%m-%d %H:%M}).{late}" if due else f"{ep} waits for the harvest of {p}."}
    return {"episode": ep, "allowed": True, "code": "OPEN", "why": f"{p} was posted and harvested", "waiting_for": None, "due": None}


def started_unposted(root: Path) -> list[str]:
    """Episodes this pipeline started (work/daily/<ep>/STATE.json) and has not posted, in id order; an adopted episode is finished building and never listed."""
    root = Path(root)
    out = []
    for p in sorted((root / "work" / "daily").glob("E*/STATE.json")) if (root / "work" / "daily").is_dir() else []:
        ep = p.parent.name
        if EP_ID.match(ep) and not is_posted(root, ep) and not (ep_work(root, ep) / "adopted.json").is_file():
            out.append(ep)
    return out


def pick_episode(root: Path, next_episode) -> str:
    """Resume an episode this pipeline started and never posted; otherwise the next one. `next_episode(root)` is daily.next_episode."""
    started = started_unposted(root)
    return started[-1] if started else next_episode(Path(root))


# ------------------------------------------------------------------ the post slot
def post_slot(ep: str, day: dt.date) -> dt.datetime:
    """The post time on every platform: 19:00 local (Amman) every day (the owner 2026-10-27). fb_slot is the same moment (offset 0)."""
    return dt.datetime.combine(day, dt.time(SLOT_START_MIN // 60, SLOT_START_MIN % 60))


def fb_slot(ep: str, day: dt.date) -> dt.datetime:
    return post_slot(ep, day) + dt.timedelta(minutes=FB_SLOT_OFFSET_MIN)


def last_post_time(root: Path) -> dt.datetime | None:
    times = [posted_at(root, p.parent.name) for p in (Path(root) / "work" / "episodes").glob("*/post.json")]
    times = [t for t in times if t]
    return max(times) if times else None


def post_due(ep: str, at: dt.datetime | None = None, root: Path = ROOT) -> dict:
    """Is it time to post <ep>? {due, code, why, slot}. code: DUE | ALREADY | WAIT-LATE | WAIT-SLOT | WAIT-GAP | WAIT-NOTREADY.
    19:00 on every platform. An episode that became ready only after today's slot (its gate report, critic or video is newer than the slot) is NOT posted
    off-slot: it waits for the next 19:00. Files that do not exist at all (a bare tree in a test) skip that one check; the publish gates still refuse an unfinished episode."""
    at = at or dt.datetime.now()
    slot = post_slot(ep, at.date())
    sl = slot.isoformat(timespec="minutes")
    if is_posted(root, ep):
        return {"due": False, "code": "ALREADY", "why": f"{ep} is already posted", "slot": sl}
    if at.time() >= POST_CUTOFF and at.date() == slot.date():
        return {"due": False, "code": "WAIT-LATE", "why": f"it is past {POST_CUTOFF:%H:%M}: {ep} waits for tomorrow's {slot:%H:%M} slot of the Post task (R-507: the autopilot posts a complete episode at once, late_post_due)", "slot": sl}
    if at < slot:
        return {"due": False, "code": "WAIT-SLOT", "why": f"today's slot for {ep} is {slot:%H:%M}", "slot": sl}
    rdy = ready_at(root, ep)
    if rdy and rdy > slot:
        return {"due": False, "code": "WAIT-NOTREADY", "why": f"{ep} was ready only at {rdy:%H:%M}, after the {slot:%H:%M} slot: the Post task posts it at tomorrow's {slot:%H:%M}, never off-slot (R-507: the autopilot posts it at once, late_post_due)", "slot": sl}
    last = last_post_time(root)
    if last and (at - last).total_seconds() < MIN_GAP_H * 3600:
        return {"due": False, "code": "WAIT-GAP", "why": f"the last post was {last:%Y-%m-%d %H:%M}; at least {MIN_GAP_H:g} h apart", "slot": sl}
    return {"due": True, "code": "DUE", "why": f"slot {slot:%H:%M} reached", "slot": sl}


def build_started_at(root: Path, ep: str) -> dt.datetime | None:
    """When the episode's first build run began (work/daily/<ep>/STATE.json `started`)."""
    j = read_json(Path(root) / "work" / "daily" / ep / "STATE.json") or {}
    try:
        return parse_time(j["started"])
    except (KeyError, ValueError, TypeError):
        return None


def first_slot_after(ep: str, t: dt.datetime) -> dt.datetime:
    s = post_slot(ep, t.date())
    return s if s >= t else post_slot(ep, t.date() + dt.timedelta(days=1))


def late_post_due(ep: str, at: dt.datetime | None = None, root: Path = ROOT) -> dict:
    """R-507 (the owner 2026-10-30: NEVER postpone a post to the next day). Is <ep> to be posted NOW by the autopilot? {due, code, why, slot}. code: DUE | DUE-LATE | FB-RETRY | ALREADY |
    WAIT-SLOT | WAIT-GAP | WAIT-NOTREADY.

    The episode's slot is the first 19:00 after its build began (a build that began at 14:30 is for today's 19:00). Before that slot nothing is posted (WAIT-SLOT: the Post task does it
    at 19:00, or the autopilot at its first tick after). From the slot on, a complete episode (gates PASS, critic 9+, video) is posted at once however late it is, past 20:30 and past
    midnight included (DUE-LATE). The 20 h gap since the last post still binds (WAIT-GAP, until the gap is over the same day). An episode posted to Instagram whose Facebook half is missing
    is retried while it is within FB_RETRY_WITHIN_H (FB-RETRY). Every publish gate still runs inside the post (daily.py post --go --late)."""
    at = at or dt.datetime.now()
    if is_posted(root, ep):
        if has_fb_token() and fb_pending(root, ep, at):
            return {"due": True, "code": "FB-RETRY", "why": f"{ep} is on Instagram but not on Facebook: retrying the Facebook half", "slot": None}
        return {"due": False, "code": "ALREADY", "why": f"{ep} is already posted", "slot": None}
    rdy = ready_at(root, ep)
    if rdy is None:
        return {"due": False, "code": "WAIT-NOTREADY", "why": f"{ep} has no gate report, critic verdict or video yet", "slot": None}
    started = build_started_at(root, ep) or rdy
    slot = first_slot_after(ep, min(started, rdy))
    sl = slot.isoformat(timespec="minutes")
    if at < slot:
        return {"due": False, "code": "WAIT-SLOT", "why": f"{ep}'s slot is {slot:%Y-%m-%d %H:%M}", "slot": sl}
    last = last_post_time(root)
    if last and (at - last).total_seconds() < MIN_GAP_H * 3600:
        return {"due": False, "code": "WAIT-GAP", "why": f"the last post was {last:%Y-%m-%d %H:%M}; at least {MIN_GAP_H:g} h apart (posts at {last + dt.timedelta(hours=MIN_GAP_H):%H:%M})", "slot": sl}
    late = rdy > slot or at.time() >= POST_CUTOFF or at.date() != slot.date()
    return {"due": True, "code": "DUE-LATE" if late else "DUE", "why": f"slot {slot:%Y-%m-%d %H:%M} reached" + (" (a late post: the episode was ready after the slot; it is not postponed to tomorrow)" if late else ""), "slot": sl}


@contextlib.contextmanager
def post_lock(root: Path, stale_h: float = 2.0):
    """R-507: one post run at a time between the Post task (19:00 to 20:25) and the autopilot's late post. Yields True when this process holds work/daily/post.lock, False when another live
    post run does. A lock older than stale_h is stolen. Always released."""
    p = Path(root) / "work" / "daily" / "post.lock"
    p.parent.mkdir(parents=True, exist_ok=True)
    got = False
    for _ in range(2):
        try:
            fd = os.open(str(p), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, json.dumps({"pid": os.getpid(), "at": dt.datetime.now().isoformat(timespec="seconds")}).encode())
            os.close(fd)
            got = True
            break
        except FileExistsError:
            try:
                if (dt.datetime.now().timestamp() - p.stat().st_mtime) > stale_h * 3600:
                    p.unlink()
                    continue
            except OSError:
                pass
            break
    try:
        yield got
    finally:
        if got:
            try:
                p.unlink()
            except OSError:
                pass


def next_post_slot(ep: str, at: dt.datetime | None = None, root: Path = ROOT) -> dt.datetime:
    """The next time the Post task will act on <ep>: today's slot if still ahead (and the gap allows), else tomorrow's."""
    at = at or dt.datetime.now()
    day = at.date()
    last = last_post_time(root)
    for _ in range(3):
        slot = post_slot(ep, day)
        rdy = ready_at(root, ep)
        if slot > at and not (last and (slot - last).total_seconds() < MIN_GAP_H * 3600) and not (rdy and rdy > slot):
            return slot
        day += dt.timedelta(days=1)
    return post_slot(ep, day)


# ------------------------------------------------------------------ what each task last said (the board's Health tab reads these)
def write_task_status(root: Path, task: str, status: str, detail: str = "", at: dt.datetime | None = None) -> dict:
    """status: OK | WAIT | NO-TOKEN | FAIL | IDLE. Never put a secret in `detail`."""
    rec = {"task": task, "status": status, "detail": detail[:400], "at": (at or dt.datetime.now()).isoformat(timespec="seconds")}
    write_json(Path(root) / "work" / "daily" / "tasks" / f"{task}.json", rec)
    return rec


def task_interval_min(task: dict) -> int:
    """How often a scheduled task says something, from board/schedule.json: a daily or windowed task once a day, a repeating one every `every_min`."""
    if task.get("kind") == "repeat" and not task.get("for_h"):
        return int(task.get("every_min") or 1440)
    return 1440


def status_age_min(status: dict, at: dt.datetime) -> float | None:
    try:
        return (at - parse_time(status["at"])).total_seconds() / 60
    except (KeyError, ValueError, TypeError):
        return None


def read_task_statuses(root: Path) -> dict:
    out = {}
    for t in TASK_NAMES:
        r = read_json(Path(root) / "work" / "daily" / "tasks" / f"{t}.json")
        if r:
            out[t] = r
    return out


def main(argv=None) -> int:
    a = list(sys.argv[1:] if argv is None else argv)
    if not a:
        print(__doc__)
        return 2
    if a[0] == "check" and len(a) > 1:
        r = check(a[1])
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return 0
    if a[0] == "slot" and len(a) > 1:
        print(post_slot(a[1], dt.date.today()).isoformat(timespec="minutes"))
        return 0
    if a[0] == "status":
        print(json.dumps(read_task_statuses(ROOT), ensure_ascii=False, indent=1))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
