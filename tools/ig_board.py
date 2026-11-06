# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""The Story-Wrap Instagram board feed (owner, 2026-10-25: a monitor plus the schedule).

    uv run tools/ig_board.py refresh [--metrics]    rebuild board/data/*.json and board/data/board.js (no network unless --metrics and a token)
    uv run tools/ig_board.py harvest-due [--go]     for every posted episode whose harvest time (14:00 Amman the day after the later post) has come and has no decision.json: comments -> tally -> next brief,
                                                    then draft replies. No token: exits 0 with the status NO-TOKEN. Dry unless --go.
    uv run tools/ig_board.py health                 rebuild the Health tab (asks Task Scheduler about the five StoryWrap tasks) and print alerts
    uv run tools/ig_board.py replies [--post] [--go]   list the reply drafts; --post sends the approved ones (daily limit, dry unless --go)
    uv run tools/ig_board.py decide <comment_id> approve|reject [--text "..."]   the same buttons the page has

The page (board/index.html) only READS board/data/board.js (works from file:// too). Buttons need the local server: `python board/serve.py`.

Feeds: work/daily/<ep>/ (STATE.json, deadline.json, STOPPED.md, budget-<date>.json), work/episodes/<ep>/ (post.json, comments.json, decision.json,
metrics.json, gate/report.json, heal/critic.json), work/daily/tasks/*.json (what each scheduled task last said), tools/ig.py, tools/vote.py, tools/loop_gate.py.

Rules (CLAUDE.md "Audience loop", "No tashkeel", Research rules; pipelines/AUDIENCE.md):
- The token is never read out, printed or written: only "present", "missing" and the days left. Every output blob is checked against the secret values.
- Reply drafts are deterministic templates in the page's voice (warm, short, Arabic, NO tashkeel, one question to keep the chat going). A draft becomes a reply
  only when the owner approves it on the board, or, with `auto_reply: true` in board/config.json, when its kind is in `auto_kinds` (default: counted votes
  only) and the daily limit (`max_replies_per_day`, default 10) and the per-run limit (3) allow it. Official API only, our own account's comments only.
- Nothing here posts an episode, edits a gate, writes the next episode, or calls a paid service.
Standard library only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("STORYWRAP_ROOT") or TOOLS.parent)
sys.path.insert(0, str(TOOLS))
import loop_gate  # noqa: E402
from arabic_display import display_text, has_tashkeel  # noqa: E402

NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
SECRET_KEYS = ("IG_ACCESS_TOKEN", "IG_APP_SECRET", "FB_PAGE_TOKEN")
DEFAULT_CFG = {"auto_reply": False, "auto_kinds": ["vote"], "max_replies_per_day": 10, "max_replies_per_run": 3}
LATE_PASS_TRIES = 3                  # the 24 h ideas pass is tried this often, then recorded as "late-pass-gave-up"
METRICS_EVERY_H = 3                  # ask Instagram for likes at most this often per post
STOPPED_SHOW = 3                     # newest STOPPED.md files shown in Health
REPLY_STATUSES = ("draft", "approved", "rejected", "posted", "failed")

# Reply voice: the StoryPage page talks like the narrator of the series: warm, short, "we", one invitation to keep talking. No tashkeel.
REPLY_TEMPLATES = {
    "vote": ["وصل صوتك ✅ سجلنا اختيارك: {choice}. تابع الحلقة الجاية لترى ماذا حدث 👀",
             "شكرا لصوتك 🗳️ اخترت: {choice}. الحلقة الجاية تُبنى على قرارك أنت وبقية المتابعين",
             "تم احتساب صوتك ✅ ({choice}). قل لنا: ماذا تتوقع أن يحدث بعد ذلك؟"],
    "idea": ["فكرة جميلة 💡 حفظناها ليقرأها كاتب الحلقة الجاية",
             "أعجبتنا فكرتك 🙌 وصلت إلى كاتب الحلقة الجاية، وربما ترى أثرها قريبا",
             "شكرا على فكرتك 💡 هذا النوع من الأفكار هو سبب أن القصة بيدكم"],
    "chat": ["شكرا لك 🙏 قل لنا: أي اختيار تفضل في آخر حلقة، وماذا تريد أن ترى بعدها؟",
             "نورت الصفحة 🌟 اكتب لنا اختيارك بكلماتك وما تتمنى أن يحدث في الحلقة الجاية",
             "شكرا لمتابعتك 🙏 رأيك يهمنا: ما الذي أعجبك، وماذا تريد أن ترى بعد ذلك؟"],
}


# ------------------------------------------------------------------ small helpers
def read_json(p: Path, default=None):
    r = loop_gate.read_json(p)
    return default if r is None else r


write_json = loop_gate.write_json


def iso(t: dt.datetime | None) -> str | None:
    return t.isoformat(timespec="minutes") if t else None


def loc(s) -> str | None:
    """A stored timestamp (ig.py and fb.py store aware UTC) as Amman local time, minute precision, for the board. Unreadable text is passed through unchanged."""
    if not s:
        return None
    try:
        return iso(loop_gate.parse_time(str(s)))
    except (ValueError, TypeError):
        return s


def paths(root: Path):
    root = Path(root)
    return root / "board" / "data", root / "board" / "config.json", root / "board" / "schedule.json"


def load_cfg(root: Path) -> dict:
    _, cfg_p, _ = paths(root)
    return {**DEFAULT_CFG, **(read_json(cfg_p, {}) or {})}


def load_schedule(root: Path) -> dict:
    _, _, sp = paths(root)
    return read_json(sp, {"tasks": {}}) or {"tasks": {}}


def episode_ids(root: Path) -> list[str]:
    w = Path(root) / "work" / "episodes"
    return sorted(p.name for p in w.glob("*") if p.is_dir() and re.fullmatch(r"E\d+[A-Z]?", p.name)) if w.is_dir() else []


def env_values(path: Path | None = None) -> dict:
    p = Path(path or loop_gate.CONF)
    vals = {}
    if p.is_file():
        for line in p.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                vals[k.strip()] = v.strip().strip('"').strip("'")
    return vals


def redact_log(text: str) -> str:
    return re.sub(r"(access_token=|Bearer\s+|OAuth\s+)[^&\s\"']+", r"\1[REDACTED]", text)


# ------------------------------------------------------------------ Today
def active_episode(root: Path) -> str | None:
    cands = [(p.stat().st_mtime, p.parent.name) for p in (Path(root) / "work" / "daily").glob("E*/STATE.json")]
    return max(cands)[1] if cands else None


def adoption(root: Path, ep: str | None) -> dict | None:
    """The valid adoption record of <ep> (tools/adopt.py), else None."""
    if not ep:
        return None
    try:
        import adopt
        return read_json(adopt.rec_path(ep, Path(root))) if adopt.valid(ep, Path(root)) else None
    except Exception:   # noqa: BLE001  an unreadable adoption is simply "not adopted"
        return None


def episode_closed(root: Path, ep: str | None) -> bool:
    """Posted, finished (gate PASS + critic >= 9 + episode.mp4) or validly adopted: its building is over, so a render-cap hit or an old stop no longer matters."""
    return bool(ep) and (loop_gate.is_posted(root, ep) or loop_gate.is_finished(root, ep) or adoption(root, ep) is not None)


def today_block(root: Path, at: dt.datetime, token: bool) -> dict:
    root = Path(root)
    ep = active_episode(root)
    out = {"episode": None, "stages": [], "machine_s": 0, "cap_s": 4 * 3600, "gate": None, "critic": None, "stopped": None, "next_episode": None, "loop": None, "state": None, "adopted": None}
    nxt = None
    if ep:
        st = read_json(root / "work" / "daily" / ep / "STATE.json", {}) or {}
        dl = read_json(root / "work" / "daily" / ep / "deadline.json", {}) or {}
        rows = []
        for name in ("votes", "script", "voice", "shots", "compose", "gates", "critic", "publish", "schedule"):
            e = (st.get("stages") or {}).get(name)
            rows.append({"stage": name, "status": (e or {}).get("status", "pending"), "seconds": (e or {}).get("seconds"),
                         "check": (e or {}).get("check"), "message": ((e or {}).get("message") or (e or {}).get("info", {}).get("why") or "")[:200]})
        rep = read_json(root / "work" / "episodes" / ep / "gate" / "report.json")
        cr = read_json(root / "work" / "episodes" / ep / "heal" / "critic.json")
        out.update({"episode": ep, "stages": rows, "machine_s": dl.get("machine_s", 0), "cap_s": dl.get("cap_s", 4 * 3600), "started": st.get("started"),
                    "gate": ({"verdict": rep.get("verdict"), "complete": rep.get("complete"), "checks": len(rep.get("checks", [])),
                              "fails": [str(f)[:120] for f in (rep.get("fails") or [])][:6], "warnings": len(rep.get("warnings") or [])} if rep else None),
                    "critic": ({"score": cr.get("score"), "verdict": cr.get("verdict"), "round": cr.get("round"), "at": cr.get("at")} if cr else None)})
        adp = adoption(root, ep)
        posted, finished = loop_gate.is_posted(root, ep), loop_gate.is_finished(root, ep)
        if adp:     # adopted by hand: the run stages were not built by the pipeline, so the old voice/critic failures are not shown
            who = f"adopted by {adp.get('approved_by')} {str(adp.get('adopted_at') or '')[:10]}".strip()
            for r in rows:
                if r["stage"] in ("votes", "script", "voice", "shots", "compose", "gates", "critic"):
                    r.update({"status": "ok", "seconds": None, "check": None, "message": who})
            out["adopted"] = {"by": adp.get("approved_by"), "at": adp.get("adopted_at"), "text": who}
        out["state"] = "posted" if posted else "adopted" if adp else "ready" if finished else None
        sp = root / "work" / "daily" / ep / "STOPPED.md"
        if sp.is_file() and not (posted or finished or adp):
            out["stopped"] = redact_log(sp.read_text(encoding="utf-8")[:600])
            out["state"] = "stopped"
        out["state"] = out["state"] or "production"
        m = re.fullmatch(r"([A-Za-z]+)(\d+)([A-Z]?)", ep)
        nxt = f"{m.group(1)}{int(m.group(2)) + 1:0{len(m.group(2))}d}" if m else None
    if nxt:
        out["next_episode"] = nxt
        out["loop"] = loop_gate.check(nxt, root, token=token, at=at, prev=ep)
    out["task_status"] = loop_gate.read_task_statuses(root)
    ap = read_json(root / "work" / "daily" / "autopilot.json", {}) or {}
    log_p = root / "work" / "daily" / "autopilot.log"
    try:
        tail = log_p.read_text(encoding="utf-8").splitlines()[-5:] if log_p.is_file() else []
    except OSError:
        tail = []
    out["autopilot"] = {"last": (ap.get("last") or {}).get("line"), "status": (ap.get("last") or {}).get("status"), "todo": ap.get("todo") or [], "log_tail": [redact_log(l)[:300] for l in tail]}     # what the owner needs to see
    return out


# ------------------------------------------------------------------ Posts
def youtube_row(w: Path):
    """The YouTube record of an episode for the board (no credentials in it): state, the privacy YouTube really applied, the link, the playlist problem if any."""
    r = read_json(w / "youtube.json")
    if not isinstance(r, dict):
        return None
    row = {"video_id": r.get("video_id"), "url": r.get("url"), "state": r.get("state"), "privacy": r.get("privacy_actual"), "locked_private": r.get("locked_private"),
           "posted_at": loc(r.get("posted_at")), "playlist": bool(r.get("playlist_item_id")), "playlist_error": r.get("playlist_error"), "comments": r.get("comments_count")}
    try:
        import yt_perf
        perf = yt_perf.board_row(w.name, w.parents[2])      # numbers from tools/yt_perf.py fetch; the key exists only after a fetch
        if perf:
            row["perf"] = perf
    except Exception:     # noqa: BLE001  an optional extra never breaks the board
        pass
    return row


def stories_row(w: Path):
    """stories.json for the board: one entry per story kind and platform (announce/vote x instagram/facebook) with its state."""
    r = read_json(w / "stories.json")
    if not isinstance(r, dict) or not isinstance(r.get("items"), dict):
        return None
    return [{"kind": k.split(":")[0], "platform": k.split(":")[-1], "state": v.get("state"), "at": loc(v.get("at"))} for k, v in sorted(r["items"].items()) if isinstance(v, dict)]


def posts_block(root: Path) -> list:
    root, rows = Path(root), []
    for ep in episode_ids(root):
        w = root / "work" / "episodes" / ep
        post = read_json(w / "post.json")
        if not post and (w / "facebook.json").is_file():       # Instagram failed but Facebook posted: shown, flagged, and the loop keeps waiting for Instagram
            fbo = read_json(w / "facebook.json") or {}
            rows.append({"episode": ep, "instagram": False, "alert": "On Facebook but NOT on Instagram: the vote source is missing; the loop waits for Instagram",
                         "permalink": None, "posted_at": loc(fbo.get("posted_at")), "harvest_due": None, "likes": None, "comments": None, "metrics_at": None,
                         "harvested": False, "vote": None, "brief": False,
                         "facebook": {"video_id": fbo.get("video_id"), "permalink": fbo.get("permalink"), "state": fbo.get("state"), "posted_at": loc(fbo.get("posted_at")), "likes": None, "comments": None}})
            continue
        if not post:
            continue
        met, dec, cm = read_json(w / "metrics.json", {}), read_json(w / "decision.json"), read_json(w / "comments.json")
        due = loop_gate.harvest_due_at(root, ep)
        fb = read_json(w / "facebook.json") or post.get("facebook") or {}
        fbm = read_json(w / "metrics-facebook.json", {})
        rows.append({"episode": ep, "youtube": youtube_row(w), "stories": stories_row(w), "facebook": ({"video_id": fb.get("video_id"), "permalink": fb.get("permalink"), "state": fb.get("state"), "posted_at": loc(fb.get("posted_at")),
                                                  "likes": fbm.get("likes"), "comments": fbm.get("comments")} if fb.get("video_id") else None),
                     "permalink": post.get("permalink"), "posted_at": loc(post.get("posted_at")), "harvest_due": iso(due),
                     "likes": met.get("likes"), "comments": met.get("comments", (cm or {}).get("count")), "metrics_at": loc(met.get("fetched_at")),
                     "harvested": bool(dec), "vote": ({"counts": dec.get("counts"), "counted": dec.get("counted"), "winner": dec.get("winner"), "status": dec.get("status"),
                                                       "choices": dec.get("choices"), "ideas": dec.get("idea_count")} if dec else None),
                     "brief": (w / "next-brief.md").is_file()})
    return rows


# ------------------------------------------------------------------ Comments and reply drafts
def choice_text(dec: dict | None, cid) -> str:
    for c in (dec or {}).get("choices") or []:
        if str(c.get("id")) == str(cid):
            return display_text(c.get("text_ar", ""))
    return ""


def comment_kind(cm: dict, choices: list, vote_mod) -> tuple[str, str | None]:
    """('vote' | 'idea' | 'chat', choice id). A counted vote is a comment naming exactly one choice; a wording beyond it is also an idea."""
    hit = set(vote_mod.classify_via(cm.get("text", ""), choices)) if choices else set()
    idea = vote_mod.idea_text(cm.get("text", ""), choices) if choices else (cm.get("text") if len((cm.get("text") or "").split()) >= 3 else None)
    if len(hit) == 1:
        return "vote", next(iter(hit))
    if idea:
        return "idea", None
    return "chat", None


def draft_text(kind: str, comment_id: str, choice: str) -> str:
    opts = REPLY_TEMPLATES[kind]
    i = int(hashlib.sha1(str(comment_id).encode()).hexdigest(), 16) % len(opts)
    return display_text(opts[i].format(choice=f"«{choice}»" if choice else "اختيارك"))


def engage_sent_ids(root: Path) -> set:
    """Instagram comment ids tools/engage.py has answered (its sent.jsonl keeps the thread's top-level comment id as `thread` and the comment as `item_id`)."""
    out = set()
    try:
        for ln in (Path(root) / "work" / "engage" / "sent.jsonl").read_text(encoding="utf-8").splitlines():
            r = json.loads(ln)
            if r.get("platform") == "instagram" and r.get("channel") == "instagram":
                out |= {r.get("item_id"), r.get("thread")}
    except (OSError, ValueError):
        pass
    return out


def comments_block(root: Path) -> dict:
    """Every comment of every posted episode, classified, plus the ideas, the tally and the reply drafts (merged with the decisions already made)."""
    import vote as vote_mod
    root = Path(root)
    dp, _, _ = paths(root)
    old = {r["id"]: r for r in (read_json(dp / "replies.json", {"replies": []}) or {}).get("replies", [])}
    replies, rows, tallies = [], [], []
    for ep in episode_ids(root):
        w = root / "work" / "episodes" / ep
        cm = read_json(w / "comments.json")
        if not cm:
            continue
        dec = read_json(w / "decision.json")
        try:
            choices = vote_mod.load_choices(vote_mod.find_ep(ep, root))
        except SystemExit:
            choices = [{"id": str(c["id"]), "text_ar": c.get("text_ar", ""), "badge": None, "variants": c.get("variants", [])} for c in (dec or {}).get("choices", [])]
        own = {o.lower().lstrip("@") for o in cm.get("own_usernames") or []}
        try:
            import after_post
            of_ = after_post.own_first(root, ep)
            own_first, own_texts = of_["ids"], of_["texts"]
        except Exception as e_:     # noqa: BLE001  fail closed (R-484): the first-comment record cannot be read, so nothing of this episode is drafted for
            print(f"ig_board: {ep} skipped, the first-comment record could not be read ({str(e_)[:80]})", file=sys.stderr)
            continue
        answered = {c.get("parent_id") for c in cm["comments"] if c.get("own") or (c.get("username") or "").lower().lstrip("@") in own}
        answered |= engage_sent_ids(root)                    # tools/engage.py already replied to these (work/engage/sent.jsonl): the board never drafts a second reply
        if dec:
            tallies.append({"episode": ep, "counts": dec.get("counts"), "counted": dec.get("counted"), "winner": dec.get("winner"), "status": dec.get("status"),
                            "margin": dec.get("margin"), "choices": dec.get("choices"), "ideas": dec.get("ideas") or [], "own_excluded": dec.get("excluded_own")})
        for c in cm["comments"]:
            mine = bool(c.get("own")) or (c.get("username") or "").lower().lstrip("@") in own or ("instagram", str(c.get("id"))) in own_first or (not c.get("parent_id") and ("instagram", after_post.norm_text(c.get("text"))) in own_texts)      # our first comment (R-484), by id or by text
            kind, cid = comment_kind(c, choices, vote_mod) if not mine else ("own", None)
            rows.append({"id": c.get("id"), "episode": ep, "username": c.get("username"), "text": (c.get("text") or "")[:300], "timestamp": c.get("timestamp"),
                         "parent_id": c.get("parent_id"), "platform": c.get("platform") or "instagram", "kind": kind, "choice": cid, "own": mine, "answered": c.get("id") in answered})
            if mine or c.get("id") in answered or not c.get("id") or (c.get("platform") or "instagram") != "instagram":   # replies go out through ig.py only; Facebook comments are read, counted and shown, not answered
                continue
            prev = old.get(c["id"])
            r = prev or {"id": c["id"], "episode": ep, "username": c.get("username"), "comment": (c.get("text") or "")[:300], "kind": kind,
                         "text": draft_text(kind, c["id"], choice_text(dec, cid)), "status": "draft", "created": dt.datetime.now().isoformat(timespec="seconds")}
            replies.append(r)
    # decisions already made on comments that vanished from the files stay in the record
    keep = {r["id"] for r in replies}
    replies += [r for i, r in old.items() if i not in keep and r.get("status") in ("posted", "failed")]
    return {"comments": rows, "tallies": tallies, "replies": replies}


def reply_counts(replies: list, day: dt.date) -> dict:
    return {"drafts": sum(r["status"] == "draft" for r in replies), "approved": sum(r["status"] == "approved" for r in replies),
            "posted_today": sum(r["status"] == "posted" and (r.get("posted_at") or "")[:10] == day.isoformat() for r in replies)}


def decide(root: Path, comment_id: str, action: str, text: str | None = None, at: dt.datetime | None = None) -> dict:
    """Approve or reject one reply draft (the board's buttons). Optionally with edited text (no tashkeel is enforced here too)."""
    if action not in ("approve", "reject"):
        raise ValueError("action must be approve or reject")
    dp, _, _ = paths(root)
    doc = read_json(dp / "replies.json", {"replies": []}) or {"replies": []}
    for r in doc["replies"]:
        if r["id"] == comment_id:
            if r["status"] == "posted":
                raise ValueError("already posted")
            if text is not None:
                t = display_text(text).strip()
                if not t or has_tashkeel(t) or len(t) > 2200:
                    raise ValueError("reply text is empty, too long or carries tashkeel")
                r["text"] = t
            r["status"] = "approved" if action == "approve" else "rejected"
            r["decided_at"] = (at or dt.datetime.now()).isoformat(timespec="seconds")
            write_json(dp / "replies.json", doc)
            return r
    raise KeyError(comment_id)


def post_replies(root: Path, go: bool = False, at: dt.datetime | None = None, do_reply=None, token: bool | None = None) -> dict:
    """Send approved drafts (and, only with auto_reply, drafts whose kind is in auto_kinds) within the limits. Dry unless go."""
    root = Path(root)
    at = at or dt.datetime.now()
    cfg = load_cfg(root)
    dp, _, _ = paths(root)
    doc = read_json(dp / "replies.json", {"replies": []}) or {"replies": []}
    token = loop_gate.has_token() if token is None else token
    if not token:
        loop_gate.write_task_status(root, "StoryWrap-Harvest", "NO-TOKEN", "reply drafts wait for the Instagram token")
        return {"status": "NO-TOKEN", "sent": 0, "dry": []}
    posted_today = sum(r["status"] == "posted" and (r.get("posted_at") or "")[:10] == at.date().isoformat() for r in doc["replies"])
    budget = max(0, min(cfg["max_replies_per_day"] - posted_today, cfg["max_replies_per_run"]))
    todo = [r for r in doc["replies"] if r["status"] == "approved" or (cfg["auto_reply"] and r["status"] == "draft" and r["kind"] in cfg["auto_kinds"])][:budget]
    if do_reply is None:
        import ig
        do_reply = lambda cid, text, go_: ig.cmd_reply(cid, text, go_)   # noqa: E731
    sent, dry = 0, []
    for r in todo:
        try:
            res = do_reply(r["id"], r["text"], go)
        except SystemExit as e:
            r["status"], r["error"] = "failed", str(e)[:200]
            continue
        if not go:
            dry.append(r["id"])
            continue
        r.update({"status": "posted", "posted_at": at.isoformat(timespec="seconds"), "reply_id": (res or {}).get("reply_id")})
        sent += 1
    if go:
        write_json(dp / "replies.json", doc)
    return {"status": "OK", "sent": sent, "dry": dry, "limit_left": budget - sent, "posted_today": posted_today + sent}


# ------------------------------------------------------------------ Schedule
def hhmm(s: str) -> dt.time:
    h, m = s.split(":")
    return dt.time(int(h), int(m))


def ticks_of(task: dict, day: dt.date) -> list[dt.datetime]:
    """Every start time of a task on one day, from board/schedule.json."""
    if task.get("kind") == "daily":
        return [dt.datetime.combine(day, hhmm(t)) for t in [task["at"], *task.get("extra_at", [])]]
    start = dt.datetime.combine(day, hhmm(task.get("from", "00:00")))
    step = dt.timedelta(minutes=int(task["every_min"]))
    end = start + dt.timedelta(hours=float(task.get("for_h", 24))) - dt.timedelta(seconds=1) if task.get("for_h") else dt.datetime.combine(day, dt.time(23, 59, 59))
    out, t = [], start
    while t <= end:
        out.append(t)
        t += step
    return out


def next_tick(task: dict, at: dt.datetime) -> dt.datetime | None:
    for d in range(0, 3):
        for t in ticks_of(task, at.date() + dt.timedelta(days=d)):
            if t >= at:
                return t
    return None


def schedule_block(root: Path, at: dt.datetime, token: bool) -> dict:
    root = Path(root)
    sch = load_schedule(root)
    rows = []
    for name, t in sch.get("tasks", {}).items():
        n = next_tick(t, at)
        rows.append({"task": name, "what": t.get("what", ""), "rule": t.get("rule", ""), "next": iso(n), "command": t.get("cmd", "")})
    ready = [e for e in episode_ids(root) if loop_gate.is_finished(root, e) and not loop_gate.is_posted(root, e)]
    post = {"episode": None, "slot": None, "blocked": None}
    if ready:
        ep = ready[-1]
        post.update({"episode": ep, "slot": iso(loop_gate.next_post_slot(ep, at, root)), "blocked": None if token else "no Instagram token: it will not post"})
    pending = [(loop_gate.harvest_due_at(root, e), e) for e in episode_ids(root) if loop_gate.is_posted(root, e) and not loop_gate.is_harvested(root, e)]
    harvest = {"episode": None, "due": None, "next_run": None}
    if pending:
        due, ep = min(pending)
        ht = sch.get("tasks", {}).get("StoryWrap-Harvest")
        harvest.update({"episode": ep, "due": iso(due), "next_run": iso(next_tick(ht, max(due, at))) if ht else None})
    return {"now": iso(at), "tasks": rows, "next_post": post, "next_harvest": harvest}


# ------------------------------------------------------------------ Health
def token_info(env: dict, at: dt.datetime) -> dict:
    if not env.get("IG_ACCESS_TOKEN"):
        return {"state": "missing", "present": False, "days_left": None, "note": "no token: Post and Harvest exit cleanly and the board says so"}
    iss = env.get("IG_TOKEN_ISSUED")
    if not iss:
        return {"state": "unknown-age", "present": True, "days_left": None, "note": "present; run `ig.py refresh` once to start the 60-day clock"}
    left = 60 - (at - loop_gate.parse_time(iss)).total_seconds() / 86400
    return {"state": "refresh-now" if left < 10 else "ok", "present": True, "days_left": round(left), "note": "present"}


def query_tasks(names=loop_gate.TASK_NAMES) -> dict:
    """Last run, last result and next run of each StoryWrap task from Task Scheduler (English Windows output). Absent tasks are reported as not registered."""
    out = {}
    for n in names:
        try:
            r = subprocess.run(["schtasks", "/Query", "/TN", n, "/FO", "LIST", "/V"], capture_output=True, text=True, timeout=20, creationflags=NOWIN, errors="replace")
        except Exception as e:                      # noqa: BLE001
            out[n] = {"registered": None, "error": str(e)[:80]}
            continue
        if r.returncode != 0:
            out[n] = {"registered": False}
            continue
        f = {k.strip(): v.strip() for k, _, v in (l.partition(":") for l in r.stdout.splitlines()) if _}
        res = f.get("Last Result", "")
        out[n] = {"registered": True, "last_run": f.get("Last Run Time"), "last_result": res, "next_run": f.get("Next Run Time"), "status": f.get("Status"),
                  "ok": res in ("0", "267011", "267009", "267010", "267008")}   # 0 ok; 0x41303 never run; 0x41301 running ...
    return out


HEALTH_TASK = "StoryWrap-Health"


AMMAN = dt.timezone(dt.timedelta(hours=3))      # Amman has been UTC+3 all year since 2022; the clock needs no tz database


def amman_naive(at: dt.datetime) -> dt.datetime:
    return at.astimezone(AMMAN).replace(tzinfo=None) if at.tzinfo else at


def amman_date(at: dt.datetime) -> dt.date:
    """The calendar day in Amman: a naive `at` is already local (Amman) time, an aware one is converted. The daily token budget resets at its midnight."""
    return amman_naive(at).date()


STOP_SHOW_H = 48                    # a STOPPED.md older than this is history, not news
DATA_STALE_X = 3                    # a Board or Harvest status older than this many of its own intervals is an alert
WATCHED = ("StoryWrap-Board", "StoryWrap-Harvest")


def sweep_media(sweep=None) -> str:
    """Security 2026-10-27 #7: delete stale temporary public ig-tmp-* releases (older than 2 h) every time Health runs. Never raises: a gh problem is a printed line."""
    try:
        if sweep is None:
            import media_host
            sweep = media_host.sweep
        gone = sweep()
        return f"media sweep: {len(gone)} stale release(s) removed" + (f": {', '.join(gone)}" if gone else "")
    except (Exception, SystemExit) as e:     # noqa: BLE001  MediaHostError is a SystemExit; no gh/login must not fail the Health task
        return f"media sweep skipped: {str(e)[:200]}"


def health_block(root: Path, at: dt.datetime, env: dict | None = None, tasks: dict | None = None, tasks_at: str | None = None) -> dict:
    root = Path(root)
    at = amman_naive(at)        # the rest of the board runs on naive local (Amman) time
    env = env if env is not None else env_values()
    tok = token_info(env, at)
    ep = active_episode(root)
    dl = read_json(root / "work" / "daily" / ep / "deadline.json", {}) if ep else {}
    bud = read_json(root / "work" / "daily" / f"budget-{amman_date(at).isoformat()}.json", {"tokens": 0, "calls": []})
    limit = int(bud.get("limit") or os.environ.get("SW_LLM_DAILY_TOKENS", "5000000"))
    cutoff = (at - dt.timedelta(hours=STOP_SHOW_H)).timestamp()
    stopped = [p for p in sorted((root / "work" / "daily").glob("*/STOPPED.md"), key=lambda p: p.stat().st_mtime, reverse=True)
               if p.stat().st_mtime >= cutoff and not episode_closed(root, p.parent.name)][:STOPPED_SHOW] if (root / "work" / "daily").is_dir() else []
    fails = [{"episode": p.parent.name, "text": redact_log(p.read_text(encoding="utf-8"))[:400], "at": dt.datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="minutes")} for p in stopped]
    sched = (read_json(paths(root)[2], {}) or {}).get("tasks", {})
    statuses = {}
    for n, st in loop_gate.read_task_statuses(root).items():
        age = loop_gate.status_age_min(st, at)
        interval = loop_gate.task_interval_min(sched.get(n, {}))
        statuses[n] = {**st, "age_min": None if age is None else round(age), "interval_min": interval, "stale": age is not None and age > interval}
    alerts = []
    if tok["state"] == "refresh-now":
        alerts.append(f"Instagram token has {tok['days_left']} days left: run `uv run tools/ig.py refresh`")
    for n in WATCHED:       # the board is only as good as its feeds: a Board or Harvest status that stopped refreshing is an alert in itself
        s = statuses.get(n)
        if s and s["age_min"] is not None and s["age_min"] > DATA_STALE_X * s["interval_min"]:
            alerts.append(f"{n} said nothing for {s['age_min']} min (it runs every {s['interval_min']} min): the board data is older than {DATA_STALE_X * s['interval_min']} min")
    for n, s in statuses.items():
        if n == HEALTH_TASK or s["stale"]:      # Health never reports its own previous status (it nested every old alert into the next one); a stale status is dimmed on the board, never red
            continue
        if s["status"] == "FAIL":
            alerts.append(f"{n} failed at {s['at']}: {s['detail']}")
        elif s["status"] == "PARTIAL":
            alerts.append(f"{n} partly failed at {s['at']} (the post itself is fine): {s['detail']}")
    for e in episode_ids(root):
        w = root / "work" / "episodes" / e
        fbr = loop_gate.read_json(w / "facebook.json")
        if (w / "facebook.json").is_file() and not (w / "post.json").is_file():
            alerts.append(f"{e} is on Facebook but NOT on Instagram: the vote source is missing, so the loop waits; look at the Post task")
        elif env.get("FB_PAGE_TOKEN") and (w / "post.json").is_file() and loop_gate.fb_pending(root, e, at):
            alerts.append(f"{e} is on Instagram but not on Facebook yet: the Post task retries")
        if isinstance(fbr, dict) and str(fbr.get("state", "")).startswith(("not-ready", "finish-refused", "finishing")):
            alerts.append(f"{e} Facebook state is {fbr.get('state')!r}: check the Page before any --force (no video was trimmed)")
    info = []        # facts that need no action (shown, never an alert)
    for e in episode_ids(root):
        w = root / "work" / "episodes" / e
        yr, sr = youtube_row(w), stories_row(w)
        if yr and str(yr.get("state") or "").startswith(("uploading", "upload-")):
            alerts.append(f"{e} YouTube state is {yr['state']!r}: check the channel in Studio before any --force (no video is re-uploaded automatically)")
        if yr and yr.get("privacy") not in (None, "public"):
            info.append(f"{e} is {yr.get('privacy')} on YouTube" + (" (YouTube locked it until the API audit passes)" if yr.get("locked_private") else " (requested private until work/state/yt_audit_passed exists)"))
        if yr and yr.get("playlist_error"):
            alerts.append(f"{e} is not in the YouTube playlist: {str(yr['playlist_error'])[:160]}")
        for it in sr or []:
            if it.get("state") == "publishing":
                alerts.append(f"{e} {it['kind']} story on {it['platform']} is pending: check the account before any --force")
    if not (env.get("FB_PAGE_ID") and env.get("FB_PAGE_TOKEN")):
        alerts.append("Facebook token or Page id is missing from instagram.env: episodes upload to Instagram only")
    if dl and dl.get("machine_s", 0) >= dl.get("cap_s", 14400) and not episode_closed(root, ep):
        alerts.append(f"{ep} used the whole 4 h render cap")
    if bud["tokens"] >= limit:
        alerts.append(f"today's {limit} token budget is spent: no more agent calls today")
    if tasks:
        for n, t in tasks.items():
            if t.get("registered") is False:
                alerts.append(f"{n} is not registered in Task Scheduler")
            elif t.get("registered") and t.get("ok") is False:
                alerts.append(f"{n} last result {t.get('last_result')}")
    fbt = {"present": bool(env.get("FB_PAGE_TOKEN") and env.get("FB_PAGE_ID")), "note": "Page token, does not expire"}
    return {"checked_at": iso(at), "token": tok, "facebook_token": fbt, "episode": ep, "cap": {"used_s": dl.get("machine_s", 0), "cap_s": dl.get("cap_s", 14400)},
            "tokens_today": {"used": bud["tokens"], "limit": limit, "calls": len(bud.get("calls", []))}, "failures": fails, "task_status": statuses,
            "scheduler": tasks, "scheduler_at": tasks_at if tasks else None, "alerts": alerts, "info": info}


# ------------------------------------------------------------------ build and write
def build_all(root: Path = ROOT, at: dt.datetime | None = None, env: dict | None = None, tasks: dict | None = None) -> dict:
    root = Path(root)
    at = at or dt.datetime.now()
    env = env if env is not None else env_values()
    token = bool(env.get("IG_ACCESS_TOKEN") and env.get("IG_USER_ID"))
    cb = comments_block(root)
    dp, _, _ = paths(root)
    prev = read_json(dp / "health.json", {}) or {}
    sched_prev = prev.get("scheduler") if tasks is None else tasks
    sched_at = (prev.get("scheduler_at") or prev.get("checked_at")) if tasks is None else iso(at)      # the age of the Task Scheduler column: reused from the last Health run unless this call asked
    health = health_block(root, at, env, tasks=sched_prev, tasks_at=sched_at)
    return {"generated_at": iso(at), "profile": {"name": os.environ.get("SW_PAGE_NAME") or "Story-Wrap page", "handle": env.get("IG_USERNAME") or "story_account", "url": "https://www.instagram.com/%s/" % (env.get("IG_USERNAME") or "story_account")},
            "token": token, "today": today_block(root, at, token), "posts": posts_block(root), "comments": cb["comments"], "tallies": cb["tallies"],
            "replies": {"items": cb["replies"], "counts": reply_counts(cb["replies"], at.date()), "config": load_cfg(root)},
            "schedule": schedule_block(root, at, token), "health": health}


def write_all(root: Path = ROOT, at: dt.datetime | None = None, env: dict | None = None, tasks: dict | None = None) -> dict:
    root = Path(root)
    env = env if env is not None else env_values()
    data = build_all(root, at, env, tasks)
    blob = json.dumps(data, ensure_ascii=False)
    for k in SECRET_KEYS:
        if env.get(k) and env[k] in blob:
            raise SystemExit("IGB-LEAK a credential value appeared in the board data; nothing was written")
    dp, _, _ = paths(root)
    for name, key in (("today", "today"), ("posts", "posts"), ("comments", "comments"), ("schedule", "schedule"), ("health", "health")):
        write_json(dp / f"{name}.json", data[key])
    write_json(dp / "replies.json", {"replies": data["replies"]["items"]})
    write_json(dp / "board.json", data)
    tmp = dp / "board.js.tmp"
    tmp.write_text("window.__BOARD__ = " + blob + ";\n", encoding="utf-8")
    loop_gate.replace_retry(tmp, dp / "board.js")
    try:
        import learn
        learn.write_board(root, at)       # board/data/learning.json: the Learning tab (tools/learn.py); never stops the board
    except Exception:                     # noqa: BLE001
        pass
    try:
        import monitor_board
        monitor_board.write(root, env=env)    # board/data/monitor.json: the Monitor tab, one sub-tab per platform (tools/monitor_board.py); files only, never stops the board
    except (Exception, SystemExit) as e:       # noqa: BLE001  a leak refusal inside the monitor writes nothing and leaves the other tabs fresh
        print(f"monitor.json NOT refreshed: {type(e).__name__}: {str(e)[:200]}", file=sys.stderr)       # visible in the task log, never silent
    return data


# ------------------------------------------------------------------ harvest (the StoryWrap-Harvest task)
def harvest_due(root: Path = ROOT, go: bool = False, at: dt.datetime | None = None, token: bool | None = None,
                do_comments=None, do_tally=None, do_next=None, do_metrics=None, do_late=None) -> dict:
    """For each posted episode whose harvest time (14:00 Amman the day after the LATER of the two posts, loop_gate.harvest_due_at) has come and has no decision.json: comments -> tally -> next brief. The vote is read
    from Instagram only; a Facebook read that fails is reported under `partial` (status PARTIAL, exit 3) and never blocks or changes the decision. Then the 24 h
    pass: new comments of an already decided episode become ideas (late-ideas.json), never a changed decision. The steps are injectable for tests."""
    root = Path(root)
    at = at or dt.datetime.now()
    token = loop_gate.has_token() if token is None else token
    due = [e for e in episode_ids(root) if loop_gate.is_posted(root, e) and not loop_gate.is_harvested(root, e)]
    due = [e for e in due if (loop_gate.harvest_due_at(root, e) or at) <= at]
    if not token:
        waiting = [e for e in episode_ids(root) if loop_gate.is_posted(root, e) and not loop_gate.is_harvested(root, e)]
        detail = f"no Instagram token (~/.config/story-wrap/instagram.env): nothing to harvest" + (f"; {', '.join(waiting)} waiting" if waiting else "; nothing posted yet")
        loop_gate.write_task_status(root, "StoryWrap-Harvest", "NO-TOKEN", detail, at)
        return {"status": "NO-TOKEN", "detail": detail, "harvested": []}
    if do_comments is None:
        import ig
        import vote
        import fb
        import post_extra
        def do_comments(ep):                                          # Instagram and Facebook comments into one comments.json; one failing does not stop the other
            res = fb.harvest(ep, repo=root)
            err = post_extra.youtube_comments(ep, root)               # YouTube comments join as ideas (platform=youtube), never as votes
            if err:
                res = {**res, "errors": {**res.get("errors", {}), "youtube": err}, "partial": True}
            return res
        do_tally = lambda ep: vote.cmd_tally(ep, repo=root)           # noqa: E731
        do_next = lambda ep: vote.cmd_next(ep, repo=root)             # noqa: E731
        do_metrics = lambda ep: fb.metrics_all(ep, repo=root)         # noqa: E731
        def do_late(ep):
            post_extra.youtube_comments(ep, root)                     # a failed YouTube read never stops the 24 h pass
            return fb.late_pass(ep, repo=root)
    done, failed, partial, late = [], [], [], []
    for ep in due:
        if not go:
            done.append(ep + " (dry)")
            continue
        try:
            res = do_comments(ep)
            if isinstance(res, dict) and res.get("errors"):
                partial.append(f"{ep}: " + "; ".join(f"{k}: {str(v)[:120]}" for k, v in res["errors"].items()))
            do_tally(ep)
            do_next(ep)
            done.append(ep)
        except SystemExit as e:
            failed.append(f"{ep}: {str(e)[:160]}")
    if go and do_metrics:
        for ep in [e for e in episode_ids(root) if loop_gate.is_posted(root, e)]:   # likes and comment counts, at most every METRICS_EVERY_H h
            m = read_json(root / "work" / "episodes" / ep / "metrics.json", {}) or {}
            last = loop_gate.parse_time(m["fetched_at"]) if m.get("fetched_at") else None
            if not last or (at - last).total_seconds() >= METRICS_EVERY_H * 3600:
                try:
                    do_metrics(ep)
                except SystemExit as e:
                    failed.append(f"{ep} metrics: {str(e)[:120]}")
    for ep in [e for e in episode_ids(root) if do_late is not None and loop_gate.is_harvested(root, e) and not (root / "work" / "episodes" / e / "late-ideas.json").is_file()]:
        t = loop_gate.later_post_at(root, ep)
        if not t or at < t + dt.timedelta(hours=loop_gate.LATE_IDEAS_AFTER_H):
            continue
        if not go:
            late.append(ep + " (dry)")
            continue
        tries_p = root / "work" / "episodes" / ep / "late-attempts.json"
        tries = (read_json(tries_p, {}) or {}).get("attempts", 0)
        try:
            do_late(ep)
            late.append(ep)
        except SystemExit as e:
            tries += 1
            write_json(tries_p, {"attempts": tries, "last_error": str(e)[:200]})
            partial.append(f"{ep} late ideas (try {tries} of {LATE_PASS_TRIES}): {str(e)[:120]}")
            if tries >= LATE_PASS_TRIES:       # stop retrying every hour: record it once, the decision is untouched
                write_json(root / "work" / "episodes" / ep / "late-ideas.json", {"episode": ep, "status": "late-pass-gave-up", "count": 0, "ideas": [], "error": str(e)[:200]})
    write_all(root, at)
    status = "FAIL" if failed else ("PARTIAL" if partial else ("OK" if done or late else "IDLE"))
    detail = "; ".join(failed + partial) if (failed or partial) else (f"harvested {', '.join(done)}" if done else (f"late ideas {', '.join(late)}" if late else "no episode is due"))
    loop_gate.write_task_status(root, "StoryWrap-Harvest", status, detail, at)
    return {"status": status, "detail": detail, "harvested": done, "failed": failed, "partial": partial, "late_ideas": late}


def harvest_cycle(root: Path = ROOT, go: bool = False, at: dt.datetime | None = None) -> int:
    """What the StoryWrap-Harvest task and the autopilot's harvest step both run: harvest_due, then replies, the vote stories, the learning review and the YouTube comment
    retention. Prints one line per part; returns the task's exit code (0 ok, 1 FAIL, 3 PARTIAL)."""
    res = harvest_due(root, go=go, **({'at': at} if at else {}))
    print(f"{res['status']} {res['detail']}")
    if go and res["status"] != "NO-TOKEN":
        pr = post_replies(root, go=True)
        write_all(root)
        print(f"replies: {pr}")
        import post_extra
        print(f"vote stories: {post_extra.vote_stories(root, go=True)}")        # the next-morning result story; its failure never changes the exit code
    if go:        # the audience review, due with the harvest (tools/learn.py); printed, never changes the exit code
        import learn
        try:
            lr = learn.review_due(root, go=True, **({'at': at} if at else {}))
            print(f"learning: {lr['status']} {lr['detail']}")
        except Exception as e:     # noqa: BLE001
            print(f"learning FAILED: {e}")
    if go:        # retention (public privacy page): YouTube-sourced comment rows older than 30 days are deleted, whatever the token says
        import yt
        try:
            print(f"youtube retention: {yt.prune_comments(root)}")
        except Exception as e:     # noqa: BLE001  a prune problem is printed, it never changes the harvest result
            print(f"youtube retention FAILED: {e}")
    return 1 if res["status"] == "FAIL" else (3 if res["status"] == "PARTIAL" else 0)


# ------------------------------------------------------------------ CLI
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ig_board.py", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("refresh"); r.add_argument("--metrics", action="store_true")
    h = sub.add_parser("harvest-due"); h.add_argument("--go", action="store_true")
    sub.add_parser("health")
    p = sub.add_parser("replies"); p.add_argument("--post", action="store_true"); p.add_argument("--go", action="store_true")
    d = sub.add_parser("decide"); d.add_argument("comment_id"); d.add_argument("action", choices=["approve", "reject"]); d.add_argument("--text")
    a = ap.parse_args(argv)
    if a.cmd == "refresh":
        live = ""
        if a.metrics:
            if loop_gate.has_token():
                import ig
                for ep in [e for e in episode_ids(ROOT) if loop_gate.is_posted(ROOT, e)]:
                    import fb
                    try:
                        fb.metrics_all(ep, repo=ROOT)         # Instagram and Facebook likes and comments -> metrics.json, metrics-facebook.json
                    except SystemExit as e:
                        print(e)
            try:       # YouTube statistics, Instagram media insights, Facebook video insights (each platform on its own credentials; one failing never stops the rest)
                import live_numbers
                live = live_numbers.summary_line(live_numbers.refresh_all(ROOT))
                print("live numbers:", live)
            except BaseException as e:     # noqa: BLE001
                live = f"live numbers FAILED: {str(e)[:120]}"
                print(live)
        data = write_all(ROOT)      # also rebuilds board/data/monitor.json (tools/monitor_board.py): the same 15-minute task, no second task needed
        loop_gate.write_task_status(ROOT, "StoryWrap-Board", "OK", f"{len(data['posts'])} posts, {len(data['comments'])} comments; {live}"[:390])
        print(f"board data written: {len(data['posts'])} posts, {len(data['comments'])} comments, {data['replies']['counts']['drafts']} reply drafts")
        return 0
    if a.cmd == "harvest-due":
        return harvest_cycle(ROOT, go=a.go)
    if a.cmd == "health":
        print(sweep_media())
        tasks = query_tasks()
        data = write_all(ROOT, tasks=tasks)
        al = data["health"]["alerts"]
        # Health ran fine whatever it found: the alerts live on the board and in the log. FAIL here would be quoted back next time and never clear.
        loop_gate.write_task_status(ROOT, HEALTH_TASK, "OK", f"{len(al)} alert(s)" if al else "all clear")
        print("ALERTS:\n  " + "\n  ".join(al) if al else "health: all clear")
        return 0
    if a.cmd == "replies":
        if a.post:
            print(post_replies(ROOT, go=a.go))
        else:
            for x in (read_json(paths(ROOT)[0] / "replies.json", {"replies": []}) or {"replies": []})["replies"]:
                print(f"{x['status']:9s} {x['kind']:5s} {x['id']}  {x['text']}")
        return 0
    if a.cmd == "decide":
        try:
            decide(ROOT, a.comment_id, a.action, a.text)
        except (KeyError, ValueError) as e:
            print(f"FAIL {e}")
            return 1
        write_all(ROOT)
        print("ok")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
