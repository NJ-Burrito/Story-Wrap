# /// script
# requires-python = ">=3.11"
# dependencies = ["google-api-python-client", "google-auth"]
# ///
"""Story-Wrap engagement watcher (the owner 2026-10-27, R-481): "monitor the notification centre of each platform and when a notification arrives, investigate".

Meta webhooks need a public HTTPS endpoint and YouTube has no comment push, and this machine has no public server. So this is a notification poll that costs no
model tokens: every ~60 s (YouTube ~150 s, jittered) it asks each platform's official API for ONE light change signal, and only when a signal changed does it run a
full engagement tick (`tools/engage.py run --go`: harvest, rules gate, Haiku decides, send). The hourly StoryWrap-Engage task stays as the safety net.

Signals (only the reels inside their 72 h window):
  instagram  comments_count of each open reel + the newest updated_time of the Page's Instagram conversations
  facebook   comments summary total_count (replies included) of each open reel + the newest updated_time of the Page's Messenger conversations
  youtube    commentThreads list per open video (order=time, 5 newest: id + reply count); 1 quota unit a call, ~1 700 of 10 000 units a day at 150 s
A first look at a platform only records a baseline (no tick). A tick re-baselines the platforms it was asked about, so our own replies never trigger the next tick.
Ticks never overlap (lock file), keep at least 60 s apart, are deferred through the quiet hours (00:30-08:30 Amman, engage's own span) and, after a tick, a follow-up
tick is planned for the earliest reply that engage has scheduled (its 2-8 min human delay). API errors back off exponentially to 15 min and never crash the loop.

  uv run tools/watch.py              run until stopped (the StoryWrap-Watch task)
  uv run tools/watch.py --once       one poll round, a tick when something changed, then exit
  uv run tools/watch.py status       print the health file
Files: work/engage/watch-state.json (signatures + health), work/engage/watch.log (one line per event, HH:MM:SS Amman), board/data/watch.json|js (health for the board).
Nothing here sends, likes or follows: a tick is the existing engage run and its caps. Tokens are never printed (inbox.scrub on every error text).
"""
from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

AMMAN = timezone(timedelta(hours=3))
PLATFORMS = ("instagram", "facebook", "youtube")
INTERVAL_S = {"instagram": 60, "facebook": 60, "youtube": 150}     # YouTube: 1 quota unit per open video per call; 150 s keeps it far under 10 000 a day
JITTER_S = 15
MIN_TICK_GAP_S = 60
BACKOFF_MAX_S = 900
LOCK_STALE_S = 1800                                                 # a tick that has run 30 min is dead
TICK_TIMEOUT_S = 1500
FOLLOW_UP_GRACE_S = 5
SPAN_QUIET = ((0, 30), (8, 30))                                     # engage.QUIET, Amman; engage.in_quiet is used when it can be imported


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(t) -> str | None:
    return t.astimezone(timezone.utc).isoformat(timespec="seconds") if t else None


def parse(s):
    try:
        t = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def write_json(p: Path, data) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    for i in range(5):
        try:
            os.replace(tmp, p)
            return
        except PermissionError:                  # the board server may be reading it
            time.sleep(0.2 * (i + 1))
    os.replace(tmp, p)


def read_json(p: Path, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def in_quiet_default(t: datetime) -> bool:
    try:
        import engage
        return engage.in_quiet(t)
    except Exception:     # noqa: BLE001
        a = t.astimezone(AMMAN)
        return SPAN_QUIET[0] <= (a.hour, a.minute) < SPAN_QUIET[1]


# ------------------------------------------------------------------ change detection
def changed(old: dict | None, new: dict) -> bool:
    """True when `new` differs from `old` on a key both know, or carries a key `old` lacks with a non-empty value. `old` None = first look: never changed (a baseline)."""
    if old is None:
        return False
    for k, v in new.items():
        if k in old:
            if old[k] != v:
                return True
        elif v not in (0, None, "", [], {}):
            return True
    return False


# ------------------------------------------------------------------ signal fetchers (official APIs, light). Each: fn(ctx) -> dict, raising only when it learned nothing.
def _open_ids(ctx: dict, pf: str) -> list[str]:
    now, out = ctx["now"], []
    for w in ctx["windows"].values():
        v = w.get(pf)
        if v and v["start"] <= now <= v["end"]:
            out += [str(i) for i in v["ids"]]
    return sorted(set(out))


def _parts(ctx: dict, jobs: dict) -> dict:
    """Run named sub-signals; a failed one is left out (the old value is kept by the caller). Raises when none worked."""
    out, errs = {}, []
    for name, fn in jobs.items():
        try:
            out.update(fn())
        except (SystemExit, Exception) as e:     # noqa: BLE001
            errs.append(f"{name}: {e}")
    if jobs and not out:
        raise RuntimeError("; ".join(errs)[:300])
    return out


def fetch_instagram(ctx: dict) -> dict:
    import ig
    env = ctx["env"]
    ids = set(_open_ids(ctx, "instagram"))

    def comments():
        ig.need(env, "IG_ACCESS_TOKEN")
        if not ids:
            return {}
        rows = ig.read_pages(env, f"{env.get('IG_USER_ID') or 'me'}/media", {"fields": "id,comments_count", "limit": "50"})
        return {f"c:{r['id']}": r.get("comments_count", 0) for r in rows if str(r.get("id")) in ids}

    def dms():
        denv = ig.publish_env(env)
        ig.need(denv, "FB_PAGE_ID", "IG_ACCESS_TOKEN")
        r = ig.api(denv, "GET", f"{denv['FB_PAGE_ID']}/conversations", {"platform": "instagram", "fields": "updated_time", "limit": "5"})
        return {"dm": sorted(c.get("updated_time") or "" for c in r.get("data", []))[-1:]}

    return _parts(ctx, {"comments": comments, "dm": dms})


def fetch_facebook(ctx: dict) -> dict:
    import fb
    env = ctx["env"]
    ids = _open_ids(ctx, "facebook")

    def comments():
        fb.need(env, "FB_PAGE_ID", "FB_PAGE_TOKEN")
        out = {}
        for vid in ids:
            r = fb.api(env, "GET", f"{vid}/comments", {"summary": "true", "filter": "stream", "limit": "0"})
            out[f"c:{vid}"] = (r.get("summary") or {}).get("total_count", 0)
        return out

    def dms():
        fb.need(env, "FB_PAGE_ID", "FB_PAGE_TOKEN")
        r = fb.api(env, "GET", f"{env['FB_PAGE_ID']}/conversations", {"platform": "messenger", "fields": "updated_time", "limit": "5"})
        return {"dm": sorted(c.get("updated_time") or "" for c in r.get("data", []))[-1:]}

    return _parts(ctx, {"comments": comments, "dm": dms})


def fetch_youtube(ctx: dict) -> dict:
    ids = _open_ids(ctx, "youtube")
    if not ids:
        return {}
    import yt
    tok = yt.load_token()
    svc = ctx["cache"].get("yt") or ctx["cache"].setdefault("yt", yt.service())
    out = {}
    for vid in ids:
        r = yt.call(lambda: svc.commentThreads().list(part="snippet", videoId=vid, order="time", maxResults=5, textFormat="plainText").execute(), "commentThreads.list", tok)
        out[f"v:{vid}"] = [[t.get("id"), (t.get("snippet") or {}).get("totalReplyCount", 0)] for t in r.get("items", [])]
    return out


FETCHERS = {"instagram": fetch_instagram, "facebook": fetch_facebook, "youtube": fetch_youtube}


# ------------------------------------------------------------------ the tick: one engage run in a child process (fresh code every time, killable)
def run_tick(root: Path, timeout: int = TICK_TIMEOUT_S) -> dict:
    env = {**os.environ, "PYTHONUTF8": "1"}
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    p = subprocess.run([sys.executable, str(TOOLS / "engage.py"), "run", "--go"], cwd=str(root), env=env, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout, creationflags=flags)
    out = p.stdout or ""
    res: dict = {}
    try:
        res = json.loads(out[out.index("{"):out.rindex("}") + 1]) if "{" in out else {}
    except ValueError:
        res = {}
    return {"rc": p.returncode, "sent": len(res.get("sent") or []), "pm_sent": len(res.get("pm_sent") or []), "liked": len(res.get("liked") or []),
            "drafted": res.get("drafted", 0), "new_items": res.get("new_items", 0), "err": (p.stderr or "")[-200:] if p.returncode else ""}


def next_due(root: Path, after: datetime) -> datetime | None:
    """The earliest reply (or private reply) engage has scheduled after `after`: the follow-up tick that actually sends it."""
    try:
        import engage
        state = engage.load_state(root)
    except Exception:     # noqa: BLE001
        return None
    best = None
    for st in (state.get("items") or {}).values():
        if st.get("status") not in ("pending", "drafted", "held"):
            continue
        for f in ("not_before", "pm_not_before"):
            t = parse(st.get(f))
            if t and t > after and (best is None or t < best):
                best = t
    return best


# ------------------------------------------------------------------ the watcher
class Watcher:
    def __init__(self, root: Path, fetchers: dict | None = None, tick=None, now_fn=now_utc, sleep=time.sleep, env: dict | None = None, rng: random.Random | None = None,
                 windows_fn=None, quiet_fn=None, due_fn=None, intervals: dict | None = None):
        self.root = Path(root)
        self.fetchers = fetchers if fetchers is not None else FETCHERS
        self.tick = tick or (lambda: run_tick(self.root))
        self.now_fn, self.sleep = now_fn, sleep
        self.env = env
        self.rng = rng or random.Random()
        self.windows_fn = windows_fn
        self.quiet_fn = quiet_fn or in_quiet_default
        self.due_fn = due_fn or (lambda after: next_due(self.root, after))
        self.intervals = {**INTERVAL_S, **(intervals or {})}
        self.dir = self.root / "work" / "engage"
        self.state_p, self.log_p, self.lock_p = self.dir / "watch-state.json", self.dir / "watch.log", self.dir / "watch.lock"
        self.state = read_json(self.state_p, {}) or {}
        self.state.setdefault("sigs", {})
        self.state.setdefault("health", {})
        self.pending: set[str] = set(self.state.get("pending") or [])
        self.next_at: dict[str, datetime] = {}
        self.fails: dict[str, int] = {}
        self.last_tick: datetime | None = parse(self.state.get("last_tick"))
        self.follow_up: datetime | None = None
        self.cache: dict = {}

    # -- log + health
    def log(self, msg: str) -> None:
        t = self.now_fn().astimezone(AMMAN).strftime("%H:%M:%S")
        self.dir.mkdir(parents=True, exist_ok=True)
        with open(self.log_p, "a", encoding="utf-8") as f:
            f.write(f"{t} {msg}\n")

    def save(self) -> None:
        self.state["pending"] = sorted(self.pending)
        self.state["last_tick"] = iso(self.last_tick)
        write_json(self.state_p, self.state)
        board = self.root / "board" / "data"
        if board.is_dir():
            data = {"generated_at": iso(self.now_fn()), "watching": True, "pid": os.getpid(), "last_tick": iso(self.last_tick), "platforms": self.state["health"]}
            write_json(board / "watch.json", data)
            tmp = board / "watch.js.tmp"
            tmp.write_text("window.__WATCH__ = " + json.dumps(data, ensure_ascii=False) + ";\n", encoding="utf-8")
            os.replace(tmp, board / "watch.js")

    def scrub(self, e) -> str:
        try:
            import inbox
            return inbox.scrub(e, self.env or {})[:160]
        except Exception:     # noqa: BLE001
            return type(e).__name__

    # -- lock: ticks never overlap
    def lock(self) -> bool:
        self.dir.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(self.lock_p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, json.dumps({"pid": os.getpid(), "at": iso(self.now_fn())}).encode())
                os.close(fd)
                return True
            except FileExistsError:
                held = read_json(self.lock_p, {}) or {}
                at = parse(held.get("at"))
                if at and (self.now_fn() - at).total_seconds() > LOCK_STALE_S:
                    self.log(f"lock: stale lock of pid {held.get('pid')} removed")
                    self.unlock()
                    continue
                return False
        return False

    def unlock(self) -> None:
        try:
            self.lock_p.unlink()
        except OSError:
            pass

    # -- context
    def ctx(self, now: datetime) -> dict:
        if self.windows_fn:
            windows = self.windows_fn(now)
        else:
            import engage
            windows = engage.episode_windows(self.root)
        env = self.env
        if env is None:
            import ig
            env = ig.load_env()
        self.env = env
        return {"env": env, "now": now, "windows": windows, "cache": self.cache}

    # -- one poll of one platform; True when it changed
    def poll(self, pf: str, now: datetime) -> bool:
        h = self.state["health"].setdefault(pf, {})
        try:
            sig = self.fetchers[pf](self.ctx(now))
        except (SystemExit, Exception) as e:     # noqa: BLE001  never crash: back off
            n = self.fails[pf] = self.fails.get(pf, 0) + 1
            wait = min(BACKOFF_MAX_S, self.intervals[pf] * 2 ** n)
            self.next_at[pf] = now + timedelta(seconds=wait * (1 + self.rng.uniform(0, 0.1)))
            msg = self.scrub(e)
            h.update(status="error", error=msg, fails=n, last_check=iso(now), retry_at=iso(self.next_at[pf]))
            self.log(f"{pf}: ERROR #{n} {msg} (retry in {int(wait)} s)")
            return False
        self.fails[pf] = 0
        self.next_at[pf] = now + timedelta(seconds=self.intervals[pf] + self.rng.uniform(-JITTER_S, JITTER_S))
        old = self.state["sigs"].get(pf)
        ch = changed(old, sig)
        self.state["sigs"][pf] = {**(old or {}), **sig}
        h.update(status="ok", error="", fails=0, last_check=iso(now), retry_at=None, watching=sorted(sig))
        if old is None:
            self.log(f"{pf}: baseline recorded ({len(sig)} signals)")
        elif ch:
            keys = [k for k, v in sig.items() if old.get(k) != v]
            self.log(f"{pf}: CHANGE {','.join(keys)[:80]}")
        return ch

    # -- tick gate
    def run_tick_if_due(self, now: datetime) -> bool:
        want = bool(self.pending) or (self.follow_up is not None and now >= self.follow_up)
        if not want:
            return False
        if self.quiet_fn(now):
            return False                           # engage sends nothing in the quiet span: the tick waits, the pending flag stays
        if self.last_tick and (now - self.last_tick).total_seconds() < MIN_TICK_GAP_S:
            return False
        if not self.lock():
            self.log("tick: deferred, another tick holds the lock")
            return False
        why = ",".join(sorted(self.pending)) or "follow-up"
        asked = set(self.pending)
        self.pending.clear()
        self.follow_up = None
        self.last_tick = now
        self.log(f"tick: start ({why})")
        try:
            r = self.tick()
            self.log(f"tick: done rc={r.get('rc')} new={r.get('new_items')} drafted={r.get('drafted')} sent={r.get('sent')} pm={r.get('pm_sent')} liked={r.get('liked')}" +
                     (f" err={self.scrub(r['err'])}" if r.get("err") else ""))
            self.state["health"]["tick"] = {"at": iso(now), "rc": r.get("rc"), "sent": r.get("sent")}
            if r.get("rc"):
                self.pending |= asked                       # a failed tick is asked for again (after the minimum gap)
        except (SystemExit, Exception) as e:     # noqa: BLE001
            self.pending |= asked
            self.log(f"tick: FAILED {self.scrub(e)}")
            self.state["health"]["tick"] = {"at": iso(now), "rc": "exception"}
        finally:
            self.unlock()
        end = self.now_fn()
        self.last_tick = end
        for pf in asked:                                    # re-baseline: our own replies must not look like a notification
            try:
                self.state["sigs"][pf] = {**self.state["sigs"].get(pf, {}), **self.fetchers[pf](self.ctx(end))}
            except (SystemExit, Exception):     # noqa: BLE001
                self.state["sigs"].pop(pf, None)           # unknown: the next good poll is a baseline again
        try:
            due = self.due_fn(end)
        except Exception:     # noqa: BLE001
            due = None
        if due:
            self.follow_up = due + timedelta(seconds=FOLLOW_UP_GRACE_S)
            self.log(f"tick: follow-up planned for {self.follow_up.astimezone(AMMAN).strftime('%H:%M:%S')}")
        return True

    # -- one round: poll what is due, then maybe tick
    def step(self, now: datetime | None = None) -> dict:
        now = now or self.now_fn()
        out = {"polled": [], "changed": [], "ticked": False, "quiet": False}
        if self.quiet_fn(now):
            out["quiet"] = True
            for pf in PLATFORMS:
                self.state["health"].setdefault(pf, {})["status"] = "quiet"
        else:
            for pf in PLATFORMS:
                if pf not in self.fetchers or now < self.next_at.get(pf, now):
                    continue
                out["polled"].append(pf)
                if self.poll(pf, now):
                    out["changed"].append(pf)
                    self.pending.add(pf)
        out["ticked"] = self.run_tick_if_due(now)
        self.save()
        return out

    def forever(self, stop=lambda: False) -> None:
        self.log(f"watcher: started pid {os.getpid()}")
        while not stop():
            try:
                self.step()
            except Exception as e:     # noqa: BLE001  the loop itself never dies
                self.log(f"loop: {self.scrub(e)}")
            self.sleep(5)
        self.log("watcher: stopped")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Story-Wrap engagement watcher")
    ap.add_argument("cmd", nargs="?", default="run", choices=("run", "status"))
    ap.add_argument("--once", action="store_true", help="one poll round (a tick if something changed), then exit")
    ap.add_argument("--root", default=None)
    a = ap.parse_args(argv)
    import ig
    root = Path(a.root or ig.REPO)
    if a.cmd == "status":
        print(json.dumps(read_json(root / "work" / "engage" / "watch-state.json", {}), ensure_ascii=False, indent=1))
        return 0
    w = Watcher(root)
    if a.once:
        print(json.dumps(w.step(), ensure_ascii=False))
        return 0
    w.forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
