"""The Monitor feed of the Story-Wrap board (owner, 2026-10-26: "combine the monitoring of the posts into the board, link all platforms, each one in a tab").

    uv run tools/monitor_board.py refresh [--root DIR]   rewrite board/data/monitor.json + monitor.js (ig_board.py refresh calls this too)
    uv run tools/monitor_board.py show                   one line per platform and post (no comment text)
    uv run tools/monitor_board.py notes [--pending]      the notes the owner typed on the board (work/board/notes.jsonl); `pick <id>` marks one as picked up

One tab per platform (instagram, facebook, youtube). Per post, newest first: the live link, the post time in Amman (HH:MM:SS), the 72 h engagement window
(open or closed, time left), the live numbers, the comment threads with our sent replies, the drafts waiting, the stories, and a trend from our own history.
Account totals and a link to the account sit at the top of each tab. DMs and stories are folded into the platform tab they belong to.

READ ONLY and FILES ONLY: every number comes from a file an existing writer already made (post.json, facebook.json, youtube.json, metrics*.json,
learn/metrics.json, work/perf/youtube/*, work/inbox/inbox.jsonl, work/engage/*). This module makes no network call, sends nothing, and never touches a
send or post path. A number no writer has produced yet is {"na": reason}, never 0. Credentials are never read except the public FB page id, and the blob is
checked for secret values before it is written. DM text is private: board/data/monitor.* is git-ignored.

The trend keeps its own small history in work/monitor/history.jsonl (git-ignored): one row per refresh (every 15 min); the same refresh never writes a key twice.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

AMMAN = timezone(timedelta(hours=3))        # Jordan: permanent UTC+3 since Oct 2022
WINDOW_H = 72                                # engage.WINDOW_H (the owner 2026-10-26)
DM_WINDOW_H = 24                             # engage.DM_WINDOW_H (Meta standard messaging window)
PLATFORMS = ("instagram", "facebook", "youtube")
HISTORY_KEEP, HISTORY_TRIM = 5000, 3000
HISTORY_EVERY_MIN = 10          # one row per refresh (the board task runs every 15 min) even when a number did not move, so the sparkline has a point per refresh
STALE_MIN = 30                  # a number read longer ago than this carries a stale badge
SERIES_POINTS = 30
COMMENTS_PER_POST = 40
TEXT_MAX = 300
CAPTION_MAX = 280
DM_TEXT_MAX = 140
INSTAGRAM_URL = os.environ.get("SW_INSTAGRAM_URL") or "https://www.instagram.com/story_account/"
YOUTUBE_URL = os.environ.get("SW_YOUTUBE_URL") or "https://www.youtube.com/channel/YOUR_CHANNEL_ID"
SHOW_ON_SCREEN = {"instagram": "📸 Instagram", "facebook": "📘 Facebook", "youtube": "▶️ YouTube"}
DRAFT_STATES = ("drafted", "held")
METRIC_DEFS = (("views", "👁", "views / plays"), ("reach", "🎯", "reach"), ("likes", "❤️", "likes / reactions"), ("comments", "💬", "comments"), ("shares", "🔁", "shares"),
               ("saves", "🔖", "saves"), ("watch", "⏱", "watch time"), ("retention", "📉", "avg view %"), ("follows", "➕", "follows gained"))
NUMERIC_KEYS = tuple(k for k, _e, _l in METRIC_DEFS)
SUMMABLE = ("views", "reach", "likes", "comments", "shares", "saves", "follows")      # added up per platform; the All level drops reach (unique reach does not add)
ALL_KEYS = ("views", "likes", "comments", "shares", "saves", "follows")
NOTE_MAX = 2000
THUMB_W = 360


# ------------------------------------------------------------------ small helpers
def read_json(p: Path, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def read_jsonl(p: Path) -> list[dict]:
    out = []
    try:
        for ln in Path(p).read_text(encoding="utf-8").splitlines():
            if ln.strip():
                try:
                    r = json.loads(ln)
                except ValueError:
                    continue
                if isinstance(r, dict):
                    out.append(r)
    except OSError:
        pass
    return out


def ts(s) -> datetime | None:
    """Graph (…+0000), YouTube (…Z) and ISO times -> aware UTC. A naive time is taken as UTC. Unreadable -> None."""
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).strip().replace("Z", "+00:00"))
    except ValueError:
        try:
            d = datetime.strptime(str(s).strip(), "%Y-%m-%dT%H:%M:%S%z")
        except ValueError:
            return None
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def iso(t: datetime | None) -> str | None:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if t else None


def when(t: datetime | None) -> dict | None:
    """{utc, date, hms} for a moment: hms is HH:MM:SS Amman time."""
    if not t:
        return None
    a = t.astimezone(AMMAN)
    return {"utc": iso(t), "date": a.strftime("%Y-%m-%d"), "hms": a.strftime("%H:%M:%S")}


_TASHKEEL = re.compile("[ً-ٰٟـ]")


def plain(s, n: int = CAPTION_MAX) -> str:
    """Text for the screen: no tashkeel (the owner 2026-10-24), no em or en dashes, one line, clipped."""
    return clip(_TASHKEEL.sub("", str(s or "")).replace("—", "-").replace("–", "-"), n)


def full_rows(rows: list, absent: dict) -> list:
    """Every post shows the same nine metrics in the same order: a metric the writer did not give is 'not available yet' with the reason in `absent`."""
    have = {r[0]: r for r in rows}
    out = []
    for k, e, l in METRIC_DEFS:
        out.append(have.get(k) or (k, e, l, na(absent.get(k) or "no writer reads it yet")))
    return out


def val(v) -> dict:
    return {"value": v}


def na(reason: str) -> dict:
    return {"na": reason}


def clip(s, n: int) -> str:
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def secret_values(env: dict) -> list[str]:
    import re
    return [str(v) for k, v in (env or {}).items() if v and len(str(v)) >= 8 and re.search(r"TOKEN|SECRET|KEY", k, re.I)]


def load_env_safe() -> dict:
    try:
        import ig
        return ig.load_env()
    except Exception:     # noqa: BLE001  an unreadable credentials file only means no page link
        return {}


# ------------------------------------------------------------------ the metric rows
def learn_value(block, name: str, scale: float = 1.0, why: str = ""):
    """One metric from work/episodes/<ep>/learn/metrics.json (the 14 h audience review): {"value": n} or {"status": "not available", "reason": ...}."""
    if not isinstance(block, dict):
        return na(why or "the 14 h audience review has not fetched it yet")
    x = block.get(name)
    if isinstance(x, dict) and "value" in x and isinstance(x["value"], (int, float)):
        return val(round(x["value"] * scale, 2) if scale != 1.0 else x["value"])
    if isinstance(x, dict) and x.get("status"):
        return na(clip(x.get("reason") or x["status"], 120))
    return na(why or "the platform returned no value")


def first_value(*vals) -> dict:
    for v in vals:
        if "value" in v:
            return v
    return vals[-1]


def at_of(m: dict, at) -> dict:
    """A value carries the time it was read ("at"); a n/a is left alone."""
    return {**m, "at": at} if "value" in m and at and not m.get("at") else m


def live_value(block, name: str, scale: float = 1.0):
    """One metric from a live file (work/episodes/<ep>/insights-*.json written every 15 min by tools/live_numbers.py):
    {"value", "at"} or {"na": exact reason} or None when the file has nothing about it."""
    x = ((block or {}).get("metrics") or {}).get(name) if isinstance(block, dict) else None
    if not isinstance(x, dict):
        return None
    if isinstance(x.get("value"), (int, float)):
        v = {"value": round(x["value"] * scale, 2) if scale != 1.0 else x["value"], "at": x.get("at") or block.get("fetched_at")}
        if x.get("error"):
            v["note"] = "last good value; the newest fetch failed: " + clip(x["error"], 100)
        return v
    return na(clip(x.get("reason") or x.get("status") or "not available", 140))


def best(live, learn_v: dict, generic: dict, learn_at=None) -> dict:
    """live number > the 14 h review's number > the live file's exact reason > the generic wait text."""
    if live and "value" in live:
        return live
    if "value" in learn_v:
        return at_of(learn_v, learn_at)
    return live or learn_v or generic


def number(m: dict):
    return m.get("value") if isinstance(m.get("value"), (int, float)) else None


def ig_metrics(w: Path, fetched) -> tuple[list, dict]:
    met = read_json(w / "metrics.json") or {}
    live = read_json(w / "insights-instagram.json")
    learn_blk = read_json(w / "learn" / "metrics.json") or {}
    learn, learn_at = learn_blk.get("instagram"), learn_blk.get("fetched_at")
    wait = "not fetched yet (insights are read every 15 min once the Page token has instagram_manage_insights)"

    def pick(name, *learn_names, scale=1.0):
        lv = live_value(live, name, scale)
        lr = first_value(*[learn_value(learn, n, scale, why=wait) for n in learn_names])
        return best(lv, lr, na(wait), learn_at)

    lk = at_of(val(met["likes"]), met.get("fetched_at")) if isinstance(met.get("likes"), (int, float)) else na("no metrics fetch yet (ig_board.py refresh --metrics)")
    com = at_of(val(met["comments"]), met.get("fetched_at")) if isinstance(met.get("comments"), (int, float)) else na("no metrics fetch yet (ig_board.py refresh --metrics)")
    views_live = live_value(live, "views")
    if not (views_live and "value" in views_live):
        views_live = live_value(live, "plays") or views_live
    rows = [("views", "👁", "views", best(views_live, first_value(learn_value(learn, "views", why=wait), learn_value(learn, "plays", why=wait)), na(wait), learn_at)),
            ("reach", "🎯", "reach", pick("reach", "reach")),
            ("likes", "❤️", "likes", lk),
            ("comments", "💬", "comments", com),
            ("shares", "🔁", "shares", pick("shares", "shares")),
            ("saves", "🔖", "saves", pick("saved", "saved")),
            ("watch", "⏱", "avg watch (s)", pick("ig_reels_avg_watch_time", "ig_reels_avg_watch_time", scale=0.001))]
    fetched.append(met.get("fetched_at"))
    return full_rows(rows, {"retention": "Instagram gives average watch time, not an average viewed percent", "follows": "no writer reads follows gained per Reel yet"}), {}


def fb_metrics(w: Path, fetched) -> tuple[list, dict]:
    met = read_json(w / "metrics-facebook.json") or {}
    live = read_json(w / "insights-facebook.json")
    learn_blk = read_json(w / "learn" / "metrics.json") or {}
    learn, learn_at = learn_blk.get("facebook"), learn_blk.get("fetched_at")
    wait = "not fetched yet (video insights are read every 15 min once the Page token has read_insights)"

    def pick(name, learn_name=None, scale=1.0):
        return best(live_value(live, name, scale), learn_value(learn, learn_name or name, scale, why=wait), na(wait), learn_at)

    likes = at_of(val(met["likes"]), met.get("fetched_at")) if isinstance(met.get("likes"), (int, float)) else na("no metrics fetch yet")
    com = at_of(val(met["comments"]), met.get("fetched_at")) if isinstance(met.get("comments"), (int, float)) else na("no metrics fetch yet")
    fb_reach = learn_value(learn, "total_video_impressions_unique", why=wait)
    rows = [("views", "👁", "views", pick("blue_reels_play_count", "total_video_views")),
            ("reach", "🎯", "reach", at_of(fb_reach, learn_at) if "value" in fb_reach else na("Facebook gives no unique reach for a Reel")),
            ("likes", "❤️", "reactions", likes),
            ("comments", "💬", "comments", com),
            ("shares", "🔁", "shares", na("no writer reads Facebook shares yet")),
            ("complete", "✅", "full views", pick("total_video_complete_views")),
            ("watch", "⏱", "avg watch (s)", pick("post_video_avg_time_watched", "total_video_avg_time_watched", 0.001))]
    fetched.append(met.get("fetched_at"))
    return full_rows(rows, {"saves": "Facebook has no saves metric", "retention": "no writer turns the Facebook retention graph into a number yet", "follows": "no writer reads follows gained per Reel yet"}), {}


def yt_live_override(rows: list, live: dict | None) -> list:
    """views / likes / comments from work/episodes/<ep>/metrics-youtube.json (videos.list statistics, every 15 min) replace the daily Analytics numbers when they are newer."""
    if not isinstance(live, dict):
        return rows
    out = []
    for k, e, l, m in rows:
        x = live.get({"views": "views", "likes": "likes", "comments": "comments"}.get(k, ""))
        if isinstance(x, (int, float)) and live.get("fetched_at"):
            cur = ts(m.get("at"))
            if not ("value" in m and cur and cur > (ts(live["fetched_at"]) or cur)):
                m = {"value": x, "at": live["fetched_at"], "note": "YouTube Data API count, every 15 min" + (f" (newest fetch failed: {clip(live['error'], 80)})" if live.get("error") and (ts(live.get("error_at")) or cur) > ts(live["fetched_at"]) else "")}
        out.append((k, e, l, m))
    return out


def yt_metrics(ep: str, root: Path, fetched) -> tuple[list, dict]:
    live = read_json(root / "work" / "episodes" / ep / "metrics-youtube.json")
    rows, extra = _yt_metrics_perf(ep, root, fetched)
    rows = yt_live_override(rows, live)
    if isinstance(live, dict) and live.get("fetched_at"):
        fetched.append(live["fetched_at"])
    elif isinstance(live, dict) and live.get("error"):
        rows = [(k, e, l, ({"na": "YouTube statistics fetch failed: " + clip(live["error"], 120)} if "na" in m and k in ("views", "likes", "comments") else m)) for k, e, l, m in rows]
    return rows, extra


def _yt_metrics_perf(ep: str, root: Path, fetched) -> tuple[list, dict]:
    d = None
    try:
        import yt_perf
        d = yt_perf.detail_of(ep, root)
    except Exception:     # noqa: BLE001  yt_perf needs the google libraries only for fetching; reading the file never does, but never break the board
        pass
    if not d:
        why = "no YouTube performance fetch yet (tools/yt_perf.py fetch)"
        return [(k, e, l, na(why)) for k, e, l in METRIC_DEFS], {}
    t, api = d.get("totals") or {}, d.get("data_api") or {}
    lag = f"Analytics lags 1-2 days (data until {d.get('as_of') or 'none yet'})"

    def total(name):
        x = t.get(name)
        if isinstance(x, dict) and x.get("status"):
            return na(clip(x.get("reason") or x["status"], 120))
        return val(x) if isinstance(x, (int, float)) else na(lag)

    views = total("views")
    dv = api.get("viewCount")
    lagging = number(views) in (None, 0) and (d.get("as_of") is None or (isinstance(dv, (int, float)) and dv > 0))   # Analytics is 1-2 days behind the Data API: its zeros are not real zeros
    if isinstance(dv, (int, float)) and number(views) in (None, 0) and dv > 0:
        views = {"value": dv, "note": "Data API count; Analytics catches up in 1-2 days"}

    def live(key, data_key):
        if isinstance(api.get(data_key), (int, float)):
            return {"value": api[data_key], "note": "Data API count"}
        return na(lag) if lagging else total(key)

    likes, com = live("likes", "likeCount"), live("comments", "commentCount")
    shares = na(lag) if lagging else total("shares")
    watch = na(lag) if lagging else total("estimatedMinutesWatched")
    avg = na(lag) if lagging else total("averageViewPercentage")
    retention = d.get("retention")
    curve = None
    if isinstance(retention, list) and retention:
        curve = [round(float(r.get("audienceWatchRatio", 0)), 3) for r in retention if isinstance(r, dict)][:60]
    follows = na(lag) if lagging else total("subscribersGained")
    rows = [("views", "👁", "views", views), ("likes", "❤️", "likes", likes), ("comments", "💬", "comments", com), ("shares", "🔁", "shares", shares),
            ("watch", "⏱", "watch (min)", watch), ("retention", "📉", "avg viewed %", avg), ("follows", "➕", "subscribers gained", follows)]
    fetched.append(d.get("fetched_at"))
    rows = [(k, e, l, at_of(m, d.get("fetched_at"))) for k, e, l, m in rows]
    return full_rows(rows, {"reach": "YouTube has no reach metric; views are its reach", "saves": "YouTube has no saves metric"}), ({"retention_curve": curve} if curve else {"retention_curve_na": lag if not isinstance(retention, dict) else clip(retention.get("reason") or lag, 120)})


# ------------------------------------------------------------------ comments, drafts, DMs
def matches(row: dict, ids: list) -> bool:
    thread = str(row.get("thread_or_post_id") or "")
    return any(i and (thread == i or thread.endswith("_" + i) or i in thread) for i in ids)


def comment_threads(pf: str, ep: str, ids: list, rows: list, state_items: dict, sent: list, w: Path) -> tuple[list, int]:
    """Top-level comments of one post, newest first, each with its replies, our sent replies and the engage verdict. Returns (threads, total top-level count)."""
    mine = [r for r in rows if r.get("platform") == pf and r.get("kind") in ("comment", "reply") and matches(r, ids)]
    seen = {r["message_id"] for r in mine}
    if pf == "instagram":      # the vote harvest (12 h) keeps comments in comments.json; used when the inbox has not read them yet
        for c in (read_json(w / "comments.json") or {}).get("comments", []):
            if c.get("id") and str(c["id"]) not in seen and c.get("platform", "instagram") == "instagram":
                t = ts(c.get("timestamp"))
                mine.append({"message_id": str(c["id"]), "parent_id": str(c.get("parent_id") or ""), "sender_name": c.get("username") or "", "is_own": bool(c.get("own")),
                             "text": c.get("text") or "", "created_at_utc": iso(t) or "", "kind": "reply" if c.get("parent_id") else "comment", "replied_by_us": False})
    by_parent: dict = {}
    for r in mine:
        if r.get("parent_id"):
            by_parent.setdefault(str(r["parent_id"]), []).append(r)
    reply_ids = {r["message_id"] for r in mine}
    my_sent = [s for s in sent if s.get("platform") == pf and s.get("episode") == ep and s.get("channel", pf) == pf]
    tops = sorted((r for r in mine if not r.get("parent_id")), key=lambda r: r.get("created_at_utc") or "", reverse=True)
    out = []
    for r in tops[:COMMENTS_PER_POST]:
        cid = str(r["message_id"])
        st = state_items.get(f"{pf}:{cid}") or {}
        reps = sorted(by_parent.get(cid, []), key=lambda x: x.get("created_at_utc") or "")
        sent_here = [{"text": clip(s.get("text"), TEXT_MAX), "when": when(ts(s.get("at")))} for s in my_sent
                     if (str(s.get("item_id")) == cid or str(s.get("thread")) == cid) and str(s.get("reply_id")) not in reply_ids]
        t = ts(r.get("created_at_utc"))
        out.append({"id": cid, "who": clip(r.get("sender_name") or r.get("sender_id") or "?", 40), "own": bool(r.get("is_own")), "text": clip(r.get("text"), TEXT_MAX), "when": when(t),
                    "kind": st.get("kind"), "status": st.get("status") or ("replied" if r.get("replied_by_us") else "new"), "reason": clip(st.get("reason") or "", 80) or None,
                    "replies": [{"who": clip(x.get("sender_name") or "?", 40), "own": bool(x.get("is_own")), "text": clip(x.get("text"), TEXT_MAX), "when": when(ts(x.get("created_at_utc")))} for x in reps],
                    "sent": sent_here})
    return out, len(tops)


def drafts_for(pf: str, ep: str, state_items: dict, rows: list) -> list:
    text_of = {f"{r['platform']}:{r['message_id']}": r.get("text") for r in rows if r.get("message_id")}
    out = []
    for key, v in state_items.items():
        if v.get("platform") != pf or v.get("episode") != ep or v.get("dm") or v.get("status") not in DRAFT_STATES:
            continue
        out.append({"key": key, "status": v["status"], "kind": v.get("kind"), "to": clip(v.get("excerpt") or text_of.get(key) or "", 120), "text": clip(v.get("reply"), 260),
                    "not_before": when(ts(v.get("not_before"))), "reason": clip(v.get("reason") or "", 80) or None})
    return sorted(out, key=lambda d: (d["not_before"] or {}).get("utc") or "")


ENGAGE_LOG_MAX = 40


def engage_log(pf: str, items: dict, rows: list, sent: list, root: Path) -> dict:
    """The Haiku engagement log of one platform (R-474): every comment and DM the tick has seen, newest first: who, what they wrote, our reply, the action
    (reply / like / react / skip / liked / no API) and Haiku's why, times in Amman; plus the "like: no API, do in session" list (work/engage/likes_todo.jsonl)."""
    by_key = {f"{r['platform']}:{r['message_id']}": r for r in rows if r.get("message_id")}
    sent_by = {(s.get("platform"), str(s.get("item_id"))): s for s in sent}
    log = []
    for key, v in items.items():
        if v.get("platform") != pf:
            continue
        r = by_key.get(key) or {}
        s_ = sent_by.get((pf, key.split(":", 1)[1]))
        reply = (s_ or {}).get("text") or v.get("reply")
        action = v.get("action") or ("reply" if reply else None)
        if v.get("status") == "noapi_like":
            action = "like: no API"
        elif v.get("status") == "skip":
            action = "skip"
        log.append({"key": key, "dm": bool(v.get("dm")), "who": clip(r.get("sender_name") or "?", 40), "text": clip(r.get("text") or v.get("excerpt") or "", 160), "when": when(ts(v.get("created"))),
                    "kind": v.get("kind"), "status": v.get("status"), "action": action, "why": clip(v.get("why") or v.get("reason") or "", 100) or None, "how": v.get("how"),
                    "reply": clip(reply, TEXT_MAX) if reply else None, "done": when(ts(v.get("sent_at") or (s_ or {}).get("at")))})
    log.sort(key=lambda x: (x["when"] or {}).get("utc") or "", reverse=True)
    todo, seen = [], set()
    for x in reversed(read_jsonl(root / "work" / "engage" / "likes_todo.jsonl")):
        if x.get("platform") == pf and x.get("comment_id") not in seen:
            seen.add(x.get("comment_id"))
            todo.append({"comment_id": x.get("comment_id"), "episode": x.get("episode"), "when": when(ts(x.get("at"))), "text": clip((by_key.get(f"{pf}:{x.get('comment_id')}") or {}).get("text"), 100),
                         "reason": x.get("reason") or "like: no API, do in session"})
    return {"log": log[:ENGAGE_LOG_MAX], "likes_todo": todo[:ENGAGE_LOG_MAX], "no_dm_api": pf == "youtube"}


def dm_block(pf: str, rows: list, inbox_state: dict, now: datetime, sent: list | None = None, items: dict | None = None) -> dict:
    src = (inbox_state.get("sources") or {}).get(f"{pf}_dm") or {}
    if pf == "youtube":
        return {"note": "YouTube has no direct messages", "threads": [], "unanswered": 0, "source": None, "sent": [], "drafts": []}
    status = src.get("status")
    source = ({"status": status, "last_ok": when(ts(src.get("last_ok"))), "error": clip(src.get("error") or "", 140) or None} if src else {"status": "not read yet", "last_ok": None, "error": None})
    convs: dict = {}
    for r in rows:
        if r.get("platform") == pf and r.get("kind") == "dm":
            convs.setdefault(str(r.get("thread_or_post_id")), []).append(r)
    threads = []
    for tid, rs in convs.items():
        rs.sort(key=lambda r: r.get("created_at_utc") or "")
        incoming = [r for r in rs if not r.get("is_own")]
        last = rs[-1]
        last_in = ts(incoming[-1]["created_at_utc"]) if incoming else None
        unanswered = bool(incoming) and bool(last_in) and not last.get("is_own") and not incoming[-1].get("replied_by_us")
        threads.append({"who": clip((incoming[-1] if incoming else last).get("sender_name") or "?", 40), "count": len(rs), "last": clip(last.get("text"), DM_TEXT_MAX), "last_own": bool(last.get("is_own")),
                        "when": when(ts(last.get("created_at_utc"))), "unanswered": unanswered,
                        "reply_open_until": when(last_in + timedelta(hours=DM_WINDOW_H)) if unanswered and last_in and now <= last_in + timedelta(hours=DM_WINDOW_H) else None})
    threads.sort(key=lambda t: (t["when"] or {}).get("utc") or "", reverse=True)
    dm_sent = [{"text": clip(x.get("text"), TEXT_MAX), "when": when(ts(x.get("at"))), "episode": x.get("episode")} for x in (sent or []) if x.get("channel") == f"dm_{pf}"]
    dm_sent.sort(key=lambda x: (x["when"] or {}).get("utc") or "", reverse=True)
    dm_drafts = [{"status": v["status"], "text": clip(v.get("reply"), 260), "not_before": when(ts(v.get("not_before"))), "to": clip(v.get("excerpt") or "", 100)}
                 for v in (items or {}).values() if v.get("platform") == pf and v.get("dm") and v.get("status") in DRAFT_STATES]
    return {"note": None, "threads": threads[:15], "unanswered": sum(t["unanswered"] for t in threads), "source": source, "sent": dm_sent[:20], "drafts": dm_drafts}


def stories_for(pf: str, w: Path) -> list:
    r = read_json(w / "stories.json")
    out = []
    for k, v in sorted(((r or {}).get("items") or {}).items()):
        if isinstance(v, dict) and k.split(":")[-1] == pf:
            out.append({"kind": k.split(":")[0], "state": v.get("state"), "when": when(ts(v.get("at")))})
    return out


# ------------------------------------------------------------------ thumbnails and post details
THUMB_URL_KEYS = ("thumbnail_url", "picture", "thumbnail", "thumbnail_maxres")        # a platform thumbnail kept by a writer; none of today's writers stores one


def make_thumb(root: Path, ep: str) -> None:
    """A still from work/episodes/<ep>/episode.mp4 into board/data/thumbs/<ep>.jpg (and the length in <ep>.json), only when missing or older than the video. Local ffmpeg, no network."""
    mp4 = Path(root) / "work" / "episodes" / ep / "episode.mp4"
    out = Path(root) / "board" / "data" / "thumbs" / f"{ep}.jpg"
    ff, fp = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not (mp4.is_file() and ff) or (out.is_file() and out.stat().st_mtime >= mp4.stat().st_mtime):
        return
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.stem + ".tmp.jpg")
    try:
        subprocess.run([ff, "-y", "-v", "error", "-ss", "1.5", "-i", str(mp4), "-frames:v", "1", "-vf", f"scale={THUMB_W}:-2", "-q:v", "3", str(tmp)], timeout=90, check=True, creationflags=flags)
        os.replace(tmp, out)
        if fp:
            r = subprocess.run([fp, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(mp4)], capture_output=True, text=True, timeout=30, creationflags=flags)
            out.with_suffix(".json").write_text(json.dumps({"duration_s": round(float(r.stdout.strip()), 1)}), encoding="utf-8")
    except (OSError, subprocess.SubprocessError, ValueError):
        tmp.unlink(missing_ok=True)


def post_details(root: Path, pf: str, ep: str, rec: dict) -> dict:
    """Thumbnail, title, caption and length of one post. Titles and captions are shown without tashkeel."""
    local = Path(root) / "board" / "data" / "thumbs" / f"{ep}.jpg"
    loc = f"data/thumbs/{ep}.jpg" if local.is_file() else None
    url = next((rec[k] for k in THUMB_URL_KEYS if isinstance(rec.get(k), str) and rec[k].startswith("https://")), None)
    dur = (read_json(local.with_suffix(".json"), {}) or {}).get("duration_s")
    post = read_json(Path(root) / "work" / "episodes" / ep / "post.json") or {}
    if pf == "instagram":
        title, caption = None, post.get("caption")
    elif pf == "facebook":
        title, caption = rec.get("title"), rec.get("caption")
    else:
        title, caption = rec.get("title"), rec.get("description")
    return {"thumb": {"src": url or loc, "local": loc, "source": "platform" if url else ("frame of episode.mp4" if loc else None)},
            "title": plain(title, 140) or None, "caption": plain(caption) or None, "duration_s": dur}


# ------------------------------------------------------------------ notes for Claude (written by the board server, read by the Lead)
_SECRETISH = re.compile(r"(?:EAA|IGAA|ya29\.|AIza|sk-|ghp_|xox[bp]-)[A-Za-z0-9_\-.]{12,}|[A-Za-z0-9_\-]{40,}")


def notes_path(root: Path) -> Path:
    return Path(root) / "work" / "board" / "notes.jsonl"


def add_note(root: Path, platform: str, post: str, text: str, now: datetime | None = None, env: dict | None = None) -> dict:
    """Append one note: {id, ts, platform, post, text, picked_up: false}. Refuses an empty note, an unknown platform or post id, and anything that looks like a secret."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    platform, post = str(platform or ""), str(post or "general")
    text = "".join(ch for ch in str(text or "") if ch == "\n" or ch >= " ").strip()
    if platform not in PLATFORMS + ("all",):
        raise ValueError("unknown platform")
    if post != "general" and not re.fullmatch(r"[A-Za-z0-9_.\-]{1,40}", post):
        raise ValueError("bad post id")
    if not text:
        raise ValueError("the note is empty")
    if len(text) > NOTE_MAX:
        raise ValueError(f"the note is longer than {NOTE_MAX} characters")
    if _SECRETISH.search(text) or any(v in text for v in secret_values(env or {})):
        raise ValueError("the note looks like it holds a token or key; not saved")
    rec = {"id": "n" + now.strftime("%y%m%d%H%M%S") + hashlib.sha1((iso(now) + text).encode("utf-8")).hexdigest()[:4], "ts": iso(now), "platform": platform, "post": post,
           "text": text, "picked_up": False}
    p = notes_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def mark_picked(root: Path, note_id: str, now: datetime | None = None) -> dict:
    """The Lead marks a note as picked up (an event row; the note itself is never rewritten)."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if not any(n["id"] == note_id for n in read_notes(root)):
        raise ValueError(f"no note {note_id}")
    rec = {"id": note_id, "picked_up": True, "picked_at": iso(now)}
    with notes_path(root).open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def read_notes(root: Path) -> list:
    """Notes newest first, each with its picked-up state merged in."""
    notes: dict = {}
    for r in read_jsonl(notes_path(root)):
        if "text" in r and r.get("id"):
            notes[r["id"]] = {**r, "picked_up": False, "picked_at": None}
        elif r.get("id") in notes and r.get("picked_up"):
            notes[r["id"]]["picked_up"], notes[r["id"]]["picked_at"] = True, r.get("picked_at")
    out = sorted(notes.values(), key=lambda n: n["ts"], reverse=True)
    return [{**n, "when": when(ts(n["ts"])), "picked_when": when(ts(n["picked_at"])) if n["picked_at"] else None} for n in out]


# ------------------------------------------------------------------ history and trend
def series(key: str, numbers: dict, hist: list, now: datetime) -> dict:
    """Per metric: the sparkline points, the change since about 24 h ago (or since the first reading), and when that reading was taken."""
    rows = sorted((h for h in hist if h.get("key") == key and isinstance(h.get("n"), dict)), key=lambda h: h.get("at") or "")
    day_ago = iso(now - timedelta(hours=24))
    out = {}
    for k in NUMERIC_KEYS:
        pts = [(h["at"], h["n"][k]) for h in rows if isinstance(h["n"].get(k), (int, float))]
        cur = numbers.get(k)
        if isinstance(cur, (int, float)):
            pts.append((iso(now), cur))
        pts = pts[-SERIES_POINTS:]
        ref = None
        for at, v in pts[:-1]:
            if at <= day_ago:
                ref = (at, v)
        if ref is None and len(pts) > 1:
            ref = pts[0]
        out[k] = {"points": [v for _a, v in pts], "delta": round(cur - ref[1], 2) if ref and isinstance(cur, (int, float)) else None, "since": when(ts(ref[0])) if ref else None}
    return out


def decorate(cards: list, ser: dict) -> list:
    for c in cards:
        c.update(ser.get(c["key"]) or {})
    return cards


def append_history(root: Path, data: dict, now: datetime) -> int:
    """One row per post, per platform and for all platforms when its numbers changed since the last row, or the last row is an hour old. Returns the rows written."""
    hp = Path(root) / "work" / "monitor" / "history.jsonl"
    hist = read_jsonl(hp)
    last: dict = {}
    for h in hist:
        last[h.get("key")] = h
    todo = [("all:*", data["all"]["numbers"])]
    for pf in PLATFORMS:
        todo.append((f"{pf}:*", data["platforms"][pf]["numbers"]))
        todo += [(f"{pf}:{p['episode']}", p["numbers"]) for p in data["platforms"][pf]["posts"]]
    new = []
    for key, nums in todo:
        prev = last.get(key)
        old = ts(prev.get("at")) if prev else None
        if prev is not None and old and old >= now:        # the same refresh (or an older clock) never writes a key twice
            continue
        if prev is None or prev.get("n") != nums or (old and now - old >= timedelta(minutes=HISTORY_EVERY_MIN)):
            new.append({"at": iso(now), "key": key, "n": nums})
    if new:
        hp.parent.mkdir(parents=True, exist_ok=True)
        rows = hist + new
        if len(rows) > HISTORY_KEEP:
            rows = rows[-HISTORY_TRIM:]
            tmp = hp.with_name(hp.name + ".tmp")
            tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
            os.replace(tmp, hp)
        else:
            with hp.open("a", encoding="utf-8") as f:
                f.write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in new))
    return len(new)


# ------------------------------------------------------------------ the whole feed
def window_info(win: dict | None, now: datetime) -> dict:
    if not win:
        return {"state": "none", "open": False, "left_min": None, "start": None, "end": None}
    start, end = win["start"], win["end"]
    if now < start:
        return {"state": "not live yet", "open": False, "left_min": int((end - now).total_seconds() // 60), "starts_in_min": int((start - now).total_seconds() // 60),
                "start": when(start), "end": when(end)}
    if now <= end:
        return {"state": "open", "open": True, "left_min": int((end - now).total_seconds() // 60), "start": when(start), "end": when(end)}
    return {"state": "closed", "open": False, "left_min": 0, "start": when(start), "end": when(end)}


def level_cards(posts: list, keys: tuple, pf: str | None = None) -> tuple[list, dict]:
    """The metric cards of a platform (its posts added up; averages for the watch and percent metrics) and the plain numbers behind them."""
    cards, nums = [], {}
    for k, e, l in METRIC_DEFS:
        if k not in keys:
            continue
        have = [p["numbers"][k] for p in posts if k in p["numbers"]]
        label = next((m["label"] for p in posts for m in p["metrics"] if m["key"] == k), l)
        if have:
            mean = k == "retention" or (k == "watch" and pf != "youtube")
            v = round(sum(have) / len(have), 1) if mean else sum(have)
            nums[k] = v
            ats = [c["at"] for p in posts for c in p["metrics"] if c["key"] == k and c.get("at") and "na" not in c]
            cards.append({"key": k, "emoji": e, "label": label, "value": v, **({"at": min(ats)} if ats else {}), **({"note": f"average of {len(have)} post(s)"} if mean and len(have) > 1 else {})})
        else:
            why = next((m["na"] for p in posts for m in p["metrics"] if m["key"] == k and "na" in m), "no post is on this platform yet")
            cards.append({"key": k, "emoji": e, "label": label, "na": why})
    return cards, nums


def stamp_cards(cards: list, now: datetime) -> None:
    """Each number card says when it was read ("as_of", HH:MM:SS Amman) and is stale when that was more than STALE_MIN minutes ago (or unknown)."""
    for c in cards:
        if "value" not in c:
            continue
        t = ts(c.get("at"))
        c["as_of"] = when(t)
        c["stale"] = t is None or now - t > timedelta(minutes=STALE_MIN)


def stamp_all(out: dict, now: datetime) -> None:
    for pf in PLATFORMS:
        stamp_cards(out["platforms"][pf]["metrics"], now)
        for p in out["platforms"][pf]["posts"]:
            stamp_cards(p["metrics"], now)
    stamp_cards(out["all"]["metrics"], now)
    out["stale_min"] = STALE_MIN


def build(root: Path, now: datetime | None = None, env: dict | None = None, hist: list | None = None) -> dict:
    import engage
    root = Path(root)
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    env = env if env is not None else load_env_safe()
    hist = hist if hist is not None else read_jsonl(root / "work" / "monitor" / "history.jsonl")
    windows = engage.episode_windows(root)
    rows = read_jsonl(root / "work" / "inbox" / "inbox.jsonl")
    inbox_state = read_json(root / "work" / "inbox" / "state.json", {}) or {}
    estate = engage.load_state(root)
    items = estate.get("items") or {}
    sent = engage.sent_rows(root)
    page = env.get("FB_PAGE_ID")
    links = {"instagram": INSTAGRAM_URL, "facebook": f"https://www.facebook.com/{page}" if page else None, "youtube": YOUTUBE_URL}
    out = {"generated_at": iso(now), "generated": when(now), "window_h": WINDOW_H, "platforms": {}, "summary": {}}
    for pf in PLATFORMS:
        posts = []
        for ep in sorted(windows):
            win = windows[ep].get(pf)
            if not win:
                continue
            w = root / "work" / "episodes" / ep
            fetched: list = []
            if pf == "instagram":
                mrows, extra = ig_metrics(w, fetched)
                rec = read_json(w / "post.json") or {}
                posted = ts(rec.get("posted_at"))
            elif pf == "facebook":
                mrows, extra = fb_metrics(w, fetched)
                rec = read_json(w / "facebook.json") or ((read_json(w / "post.json") or {}).get("facebook")) or {}
                posted = win["start"]
            else:
                mrows, extra = yt_metrics(ep, root, fetched)
                rec = read_json(w / "youtube.json") or {}
                posted = ts(rec.get("posted_at"))
            numbers = {k: number(m) for k, _e, _l, m in mrows if number(m) is not None}
            cards = decorate([{"key": k, "emoji": e, "label": l, **m} for k, e, l, m in mrows], series(f"{pf}:{ep}", numbers, hist, now))
            threads, total_top = comment_threads(pf, ep, win["ids"], rows, items, sent, w)
            sent_p = [s for s in sent if s.get("platform") == pf and s.get("episode") == ep and s.get("channel", pf) == pf]
            det = post_details(root, pf, ep, rec)
            if pf == "youtube" and not det["duration_s"]:
                try:
                    import yt_perf
                    det["duration_s"] = ((yt_perf.detail_of(ep, root) or {}).get("duration_s"))
                except Exception:     # noqa: BLE001
                    pass
            posts.append({"episode": ep, "id": (win["ids"] or [None])[0], "url": win.get("url") or rec.get("permalink") or rec.get("url"), "state": rec.get("state"),
                          "posted": when(posted), "scheduled_note": (f"went live {when(win['start'])['hms']}" if pf == "facebook" and rec.get("state") == "scheduled" and now >= win["start"] else None),
                          "window": window_info(win, now), "metrics": cards, "metrics_at": when(ts(next((f for f in fetched if f), None))), "numbers": numbers, **det, **extra,
                          "comments": threads, "comments_total": total_top, "comments_reported": numbers.get("comments"),
                          "sent": [{"text": clip(s.get("text"), TEXT_MAX), "kind": s.get("kind"), "when": when(ts(s.get("at")))} for s in sent_p],
                          "drafts": drafts_for(pf, ep, items, rows), "stories": stories_for(pf, w) if pf != "youtube" else []})
        posts.sort(key=lambda p: (p["posted"] or {}).get("utc") or "", reverse=True)
        dms = dm_block(pf, rows, inbox_state, now, sent, items)
        cards, nums = level_cards(posts, SUMMABLE + ("watch", "retention"), pf)
        halt = ts((estate.get("halt") or {}).get(pf))
        out["platforms"][pf] = {
            "name": SHOW_ON_SCREEN[pf], "link": links[pf], "link_note": None if links[pf] else "the Facebook page id is not set (FB_PAGE_ID)",
            "metrics": decorate(cards, series(f"{pf}:*", nums, hist, now)), "numbers": nums,
            "totals": {"posts": len(posts), "windows_open": sum(p["window"]["open"] for p in posts), "replies_sent": sum(len(p["sent"]) for p in posts), "drafts": sum(len(p["drafts"]) for p in posts),
                       "dms_unanswered": dms["unanswered"], "followers": na("no writer reads follower counts yet"), "halted_until": when(halt) if halt and halt > now else None},
            "dms": dms, "engage": engage_log(pf, items, rows, sent, root), "posts": posts, "stories_note": "YouTube has no stories (removed 2023)" if pf == "youtube" else None}
    # all platforms together: the platform sums are added up (a platform with no number for a metric adds nothing)
    def plat_cards(pf):
        have = {c["key"]: c for c in out["platforms"][pf]["metrics"]}
        return [({"key": k, "label": l, "at": have[k]["at"]} if k in have and have[k].get("at") and "value" in have[k] else {"key": k, "label": l, "na": "no platform has this number yet"})
                for k, _e, l in METRIC_DEFS]
    plat = [{"numbers": out["platforms"][pf]["numbers"], "metrics": plat_cards(pf)} for pf in PLATFORMS]
    cards, nums = level_cards(plat, ALL_KEYS)
    out["all"] = {"metrics": decorate(cards, series("all:*", nums, hist, now)), "numbers": nums, "posts": sum(len(out["platforms"][pf]["posts"]) for pf in PLATFORMS)}
    stamp_all(out, now)
    out["notes"] = read_notes(root)[:100]
    out["summary"] = {"windows_open": sum(out["platforms"][p]["totals"]["windows_open"] for p in PLATFORMS), "drafts": sum(out["platforms"][p]["totals"]["drafts"] for p in PLATFORMS),
                      "dms_unanswered": sum(out["platforms"][p]["totals"]["dms_unanswered"] for p in PLATFORMS), "replies_sent": sum(out["platforms"][p]["totals"]["replies_sent"] for p in PLATFORMS),
                      "notes_waiting": sum(1 for n in out["notes"] if not n["picked_up"])}
    return out


def write(root: Path, now: datetime | None = None, env: dict | None = None) -> dict:
    """Make the thumbnails, build the feed and write board/data/monitor.json + monitor.js; append the trend history. Refuses (writes nothing) if a credential value is in the blob."""
    root = Path(root)
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    env = env if env is not None else load_env_safe()
    dp = root / "board" / "data"
    if dp.is_dir():
        import engage
        for ep in engage.episode_windows(root):
            make_thumb(root, ep)
    data = build(root, now, env)
    blob = json.dumps(data, ensure_ascii=False)
    for v in secret_values(env):
        if v in blob:
            raise SystemExit("MONITOR-LEAK a credential value appeared in the monitor data; nothing was written")
    if not dp.is_dir():
        return data
    import loop_gate
    for name, text in (("monitor.json", blob + "\n"), ("monitor.js", "window.__MONITOR__ = " + blob + ";\n")):
        tmp = dp / (name + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        loop_gate.replace_retry(tmp, dp / name)
    append_history(root, data, now)
    return data


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="monitor_board.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", default=os.environ.get("SW_REPO") or str(TOOLS.parent))
    sub = ap.add_subparsers(dest="cmd", required=True)
    for n in ("refresh", "show"):
        sub.add_parser(n)
    nl = sub.add_parser("notes", help="list the notes the owner typed on the board (the Lead's inbox)")
    nl.add_argument("--pending", action="store_true", help="only notes not yet picked up")
    pk = sub.add_parser("pick", help="mark a note as picked up")
    pk.add_argument("id")
    a = ap.parse_args(argv)
    root = Path(a.root)
    if a.cmd == "notes":
        for n in read_notes(root):
            if a.pending and n["picked_up"]:
                continue
            print(f"{n['id']}  {n['when']['date']} {n['when']['hms']}  {n['platform']}/{n['post']}  {'picked up' if n['picked_up'] else 'WAITING'}\n    {n['text']}")
        return 0
    if a.cmd == "pick":
        try:
            mark_picked(root, a.id)
        except ValueError as e:
            print(f"FAIL {e}")
            return 1
        write(root)
        print("ok")
        return 0
    data = write(root) if a.cmd == "refresh" else build(root)
    for pf in PLATFORMS:
        P = data["platforms"][pf]
        for p in P["posts"]:
            w = p["window"]
            print(f"{P['name']} {p['episode']} {p['url']} posted {(p['posted'] or {}).get('hms')} window {w['state']} {w.get('left_min')} min left; comments {p['comments_total']}, sent {len(p['sent'])}, drafts {len(p['drafts'])}")
    print(f"monitor {'written' if a.cmd == 'refresh' else 'built (not written)'}: {data['summary']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
