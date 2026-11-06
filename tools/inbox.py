# /// script
# requires-python = ">=3.11"
# dependencies = ["google-api-python-client", "google-auth"]
# ///
"""The Story-Wrap inbox harvest (owner, 2026-10-26): every DM and comment our accounts received, with sender and timing, in one sorted CSV.

    uv run tools/inbox.py harvest [--since DAYS] [--dry]   read all sources, merge new rows into work/inbox/inbox.csv + inbox.jsonl (dry: count only, write nothing)
    uv run tools/inbox.py status                            row counts by platform and kind, unanswered count, last run per source (never prints a message)

Sources (official APIs, READ ONLY: this file never sends, replies, likes or deletes anything):
  instagram_dm        GET /{FB_PAGE_ID}/conversations?platform=instagram   Page token IG_PUBLISH_TOKEN on graph.facebook.com
  facebook_dm         GET /{FB_PAGE_ID}/conversations?platform=messenger   same token
  instagram_comments  media of the account + comments + replies            Page token (IG_PUBLISH_TOKEN) first, Instagram-login token as the fallback (tools/ig.py read_pages)
  facebook_comments   Page posts and reels + comments + replies            Page token (tools/fb.py)
  youtube_comments    commentThreads of the channel                         youtube.readonly OAuth token (tools/yt.py)
  linkedin            the LinkedIn repo's harvested files only (engage/replies-<slug>.md and published/comments.jsonl); no LinkedIn API call, LinkedIn DMs are never read

Files (work/ is git-ignored; DMs are private: no data is committed, no message text is ever printed, logs carry counts only):
  work/inbox/inbox.csv    UTF-8 with BOM (Excel shows Arabic), sorted by created_at desc
  work/inbox/inbox.jsonl  the same rows, one JSON object per line (the merge base)
  work/inbox/state.json   last run and last success per source (the next run reads only what is newer, with 2 days of overlap)

Each source fails alone with a FAIL line; the others still run. Exit 2 only when every source failed. Tokens are redacted from every error.
Standard library only (the YouTube source uses what tools/yt.py declares).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fb   # noqa: E402
import ig   # noqa: E402

AMMAN = timezone(timedelta(hours=3))        # Jordan moved to permanent UTC+3 in Oct 2022: no DST to apply
OVERLAP = timedelta(days=2)                 # an incremental run re-reads the last 2 days so a late write is never missed
LINKEDIN_ROOT = Path(os.environ.get("INBOX_LINKEDIN_ROOT") or "linkedin-repo")
SOURCES = ("instagram_dm", "facebook_dm", "instagram_comments", "facebook_comments", "youtube_comments", "linkedin")
COLUMNS = ("kind", "platform", "account", "thread_or_post_id", "post_url", "message_id", "parent_id", "sender_name", "sender_id", "is_own",
           "created_at_utc", "created_at_amman", "text", "attachments", "language", "replied_by_us", "harvested_at")
CONV_LIMIT, MSG_LIMIT = "25", "50"


# ------------------------------------------------------------------ small helpers
def out_dir(repo: Path) -> Path:
    return Path(repo) / "work" / "inbox"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_ts(s) -> datetime | None:
    """Graph (2026-10-26T10:00:00+0000), YouTube (...Z) and ISO-with-offset times -> aware datetime; a naive time is taken as UTC. Unreadable -> None."""
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def lang_guess(text: str) -> str:
    """Script-based: ar when Arabic letters are at least as many as Latin ones, en when Latin letters win, other when there are letters of neither, '' for no letters."""
    ar = len(re.findall(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]", text or ""))
    la = len(re.findall(r"[A-Za-z]", text or ""))
    if ar and ar >= la:
        return "ar"
    if la:
        return "en"
    return "other" if re.search(r"[^\W\d_]", text or "") else ""


def row(kind, platform, account, thread, post_url, mid, parent, name, sid, own, when, text, attachments=(), at=None) -> dict | None:
    """One normalised row, or None when the message has no id or no readable time (it cannot be deduplicated or sorted)."""
    t = parse_ts(when)
    if not mid or t is None:
        return None
    t = t.astimezone(timezone.utc)
    text = text or ""
    return {"kind": kind, "platform": platform, "account": account or "", "thread_or_post_id": str(thread or ""), "post_url": post_url or "", "message_id": str(mid),
            "parent_id": str(parent or ""), "sender_name": name or "", "sender_id": str(sid or ""), "is_own": bool(own),
            "created_at_utc": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "created_at_amman": t.astimezone(AMMAN).isoformat(timespec="seconds"),
            "text": text, "attachments": " | ".join(a for a in attachments if a), "language": lang_guess(text), "replied_by_us": False,
            "harvested_at": (at or utcnow()).strftime("%Y-%m-%dT%H:%M:%SZ")}


def secret_values(env: dict) -> list[str]:
    return [v for k, v in env.items() if v and len(str(v)) >= 8 and re.search(r"TOKEN|SECRET|KEY", k, re.I)]


def scrub(text, env: dict | None = None) -> str:
    """Every credential value and token-looking parameter removed from a string before it is shown or stored (500 characters at most)."""
    s = str(text)
    for v in secret_values(env or {}):
        s = s.replace(str(v), "[REDACTED]")
    s = ig.redact(s, env or {})
    s = re.sub(r"((?:access_token|refresh_token|client_secret|key)=)[^&\s\"']+", r"\1[REDACTED]", s)
    s = re.sub(r"(Bearer\s+)[A-Za-z0-9._~+/=-]{8,}", r"\1[REDACTED]", s)
    return s[:500]


def attach_names(att) -> list[str]:
    """['image/jpeg:name', 'share', ...] from a Messaging 'attachments' or 'shares' edge, or a Page comment 'attachment'. No URLs (CDN links are signed and private)."""
    out = []
    items = att.get("data", []) if isinstance(att, dict) and "data" in att else ([att] if isinstance(att, dict) and att else [])
    for a in items:
        kind = a.get("mime_type") or a.get("type") or ("image" if a.get("image_data") else "video" if a.get("video_data") else "file")
        out.append(f"{kind}:{a['name']}" if a.get("name") else str(kind))
    return out


def walk(env: dict, path: str, params: dict, stop=None, host_ok=None) -> list:
    """Follow paging.next through ig.api (one redacted failure type). stop(page_items) -> True ends the walk after that page (newest-first edges)."""
    out, url = [], None
    pref = f"https://{ig.base(env).split('/')[2]}/"
    while True:
        r = ig.api(env, "GET", path, params if url is None else None, url=url)
        page = r.get("data", [])
        out += page
        url = (r.get("paging") or {}).get("next")
        if not url or (stop and stop(page)):
            return out
        if not url.startswith(pref):
            ig.fail("IG-PAGING", "paging.next points to another host; stopped")


# ------------------------------------------------------------------ direct messages
def dm_rows(ctx: dict, platform: str) -> list[dict]:
    env = ig.publish_env(ctx["env"])
    if platform == "messenger" and not env.get("IG_PUBLISH_TOKEN") and ctx["env"].get("FB_PAGE_TOKEN"):
        env = {**ctx["env"], "IG_API_HOST": "graph.facebook.com", "IG_ACCESS_TOKEN": ctx["env"]["FB_PAGE_TOKEN"]}
    ig.need(env, "FB_PAGE_ID", "IG_ACCESS_TOKEN")
    pid, since = env["FB_PAGE_ID"], ctx.get("since")
    is_ig = platform == "instagram"
    own_ids = {str(pid)} | ({str(env["IG_USER_ID"])} if is_ig and env.get("IG_USER_ID") else set())
    own_user = (env.get("IG_USERNAME") or "").lower() if is_ig else ""
    account = (env.get("IG_USERNAME") or "story_account") if is_ig else "StoryPage"
    plat = "instagram" if is_ig else "facebook"
    msg_fields = "id,from,to,message,created_time,attachments,shares"
    fields = f"id,participants,updated_time,messages.limit({MSG_LIMIT}){{{msg_fields}}}"

    def old(items):
        return bool(since) and bool(items) and all((parse_ts(c.get("updated_time")) or since) < since for c in items)

    out = []
    for conv in walk(env, f"{pid}/conversations", {"platform": platform, "fields": fields, "limit": CONV_LIMIT}, stop=old):
        cid, upd = conv.get("id"), parse_ts(conv.get("updated_time"))
        if since and upd and upd < since:
            continue
        box = conv.get("messages") or {}
        msgs, nxt = list(box.get("data", [])), (box.get("paging") or {}).get("next")
        while nxt and not (since and msgs and (parse_ts(msgs[-1].get("created_time")) or since) < since):
            if not nxt.startswith(f"https://{ig.base(env).split('/')[2]}/"):
                ig.fail("IG-PAGING", "paging.next points to another host; stopped")
            r = ig.api(env, "GET", "", url=nxt)
            msgs += r.get("data", [])
            nxt = (r.get("paging") or {}).get("next")
        for m in msgs:
            frm = m.get("from") or {}
            own = str(frm.get("id")) in own_ids or bool(own_user and (frm.get("username") or "").lower() == own_user)
            att = attach_names(m.get("attachments")) + (["share"] if m.get("shares") else [])
            r_ = row("dm", plat, account, cid, "", m.get("id"), "", frm.get("name") or frm.get("username"), frm.get("id"), own,
                     m.get("created_time"), m.get("message"), att, ctx.get("now"))
            if r_:
                out.append(r_)
    return out


def src_instagram_dm(ctx):
    return dm_rows(ctx, "instagram")


def src_facebook_dm(ctx):
    return dm_rows(ctx, "messenger")


# ------------------------------------------------------------------ comments: Instagram, Facebook, YouTube
def src_instagram_comments(ctx):
    """Media, comments and replies of the account, read with the Page token when IG_PUBLISH_TOKEN is set (media of the Facebook-login route is invisible to the
    Instagram-login token: 0 rows, no error), else with the Instagram-login token. The Page token has no instagram_manage_comments, so `username` is null: the sender
    is then the `from.id` when Meta sends it, else 'unknown', and our own rows are recognised by that id (IG_USER_ID / FB_PAGE_ID) or by the username."""
    env = ctx["env"]
    ig.need(env, "IG_ACCESS_TOKEN")
    me = env.get("IG_USER_ID") or "me"
    account = env.get("IG_USERNAME") or "story_account"
    own = account.lower()
    own_ids = {str(env[k]) for k in ("IG_USER_ID", "FB_PAGE_ID") if env.get(k)}
    out = []
    for m in ig.read_pages(env, f"{me}/media", {"fields": "id,permalink,timestamp", "limit": "50"}):
        def mk(c, parent):
            u = c.get("username") or ""
            sid = str((c.get("from") or {}).get("id") or "")
            name = u or (c.get("from") or {}).get("username") or "unknown"
            is_own = (u.lower() == own) or bool(sid and sid in own_ids)
            return row("reply" if parent else "comment", "instagram", account, m["id"], m.get("permalink"), c.get("id"), parent, name, sid, is_own,
                       c.get("timestamp"), c.get("text"), (), ctx.get("now"))
        for c in ig.read_pages(env, f"{m['id']}/comments", {"fields": "id,text,timestamp,username", "limit": "50"}, "from"):
            out.append(mk(c, ""))
            for r in ig.read_pages(env, f"{c['id']}/replies", {"fields": "id,text,timestamp,username", "limit": "50"}, "from"):
                out.append(mk(r, c.get("id")))
    return [r for r in out if r]


def src_facebook_comments(ctx):
    env = ctx["env"]
    fb.need(env, "FB_PAGE_ID", "FB_PAGE_TOKEN")
    pid = env["FB_PAGE_ID"]
    posts, errs = {}, []
    for edge in ("posts", "video_reels"):
        try:
            for p in fb.pages(env, f"{pid}/{edge}", {"fields": "id,permalink_url,created_time", "limit": fb.PAGE_EDGE_LIMIT}):
                posts.setdefault(p["id"], p)
        except SystemExit as e:
            errs.append(f"{edge}: {e}")
    if errs and len(errs) == 2:
        ig.fail("FB-EDGES", "; ".join(errs))
    if errs:
        print(f"WARN facebook_comments: edge failed ({scrub(errs[0], env)})")
    fields = {"fields": "id,message,created_time,from{id,name},attachment", "limit": fb.PAGE_EDGE_LIMIT, "order": "chronological"}
    out = []
    for p in posts.values():
        def mk(c, parent):
            frm = c.get("from") or {}
            return row("reply" if parent else "comment", "facebook", "StoryPage", p["id"], p.get("permalink_url"), c.get("id"), parent, frm.get("name"), frm.get("id"),
                       bool(frm.get("id") and str(frm["id"]) == str(pid)), c.get("created_time"), c.get("message"), attach_names(c.get("attachment")), ctx.get("now"))
        for c in fb.pages(env, f"{p['id']}/comments", fields):
            out.append(mk(c, ""))
            for r in fb.pages(env, f"{c['id']}/comments", fields):
                out.append(mk(r, c.get("id")))
    return [r for r in out if r]


def src_youtube_comments(ctx):
    import yt
    tok = yt.load_token()
    svc = ctx.get("yt_service") or yt.service()
    out, page = [], None

    def mk(sn, cid, parent):
        ch = (sn.get("authorChannelId") or {}).get("value")
        vid = sn.get("videoId") or ""
        return row("reply" if parent else "comment", "youtube", "StoryPage", vid, f"https://www.youtube.com/watch?v={vid}&lc={cid}" if vid else "", cid, parent,
                   sn.get("authorDisplayName"), ch, bool(ch and ch == yt.CHANNEL_ID), sn.get("publishedAt"), sn.get("textOriginal") or sn.get("textDisplay"), (), ctx.get("now"))

    while True:
        kw = {"part": "snippet,replies", "allThreadsRelatedToChannelId": yt.CHANNEL_ID, "maxResults": 100, "order": "time", "textFormat": "plainText"}
        if page:
            kw["pageToken"] = page
        r = yt.call(lambda: svc.commentThreads().list(**kw).execute(), "commentThreads.list", tok)
        for th in r.get("items", []):
            top = (th.get("snippet") or {}).get("topLevelComment") or {}
            tid = top.get("id") or th.get("id")
            out.append(mk(top.get("snippet") or {}, tid, ""))
            inline = (th.get("replies") or {}).get("comments") or []
            replies, total = list(inline), (th.get("snippet") or {}).get("totalReplyCount") or 0
            if total > len(inline):             # commentThreads carries at most 5 replies: ask for the rest of this thread
                replies, rp = [], None
                while True:
                    k2 = {"part": "snippet", "parentId": tid, "maxResults": 100, "textFormat": "plainText"}
                    if rp:
                        k2["pageToken"] = rp
                    r2 = yt.call(lambda: svc.comments().list(**k2).execute(), "comments.list", tok)
                    replies += r2.get("items", [])
                    rp = r2.get("nextPageToken")
                    if not rp:
                        break
            for c in replies:
                out.append(mk(c.get("snippet") or {}, c.get("id"), tid))
        page = r.get("nextPageToken")
        if not page:
            break
    return [r for r in out if r]


# ------------------------------------------------------------------ LinkedIn: files the LinkedIn repo already wrote (no API call, no DMs)
def _h(*parts) -> str:
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]


def src_linkedin(ctx):
    root = Path(ctx.get("linkedin_root") or LINKEDIN_ROOT)
    if not root.is_dir():
        ig.fail("LI-NOREPO", f"LinkedIn repo not found at {root}")
    me = ctx.get("linkedin_name") or "the owner"
    out, now = [], ctx.get("now")
    urls = {}
    led = root / "published" / "ledger.jsonl"
    if led.is_file():
        for line in led.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
                urls[e["slug"]] = (e.get("url") or "", e.get("urn") or "")
            except (ValueError, KeyError):
                continue
    # Comments on the owner's posts + our replies: engage/replies-<slug>.md written by comments_watch.py ("## YYYY-MM-DD HH:MM" Amman time, "- **who**: text", "  - replied: text")
    for f in sorted((root / "engage").glob("replies-*.md")):
        slug = f.stem[len("replies-"):]
        url, urn = urls.get(slug, ("", ""))
        when, cur = None, None
        for line in f.read_text(encoding="utf-8").splitlines():
            h = re.match(r"## (\d{4}-\d\d-\d\d) (\d\d:\d\d)\s*$", line)
            if h:
                when, cur = f"{h.group(1)}T{h.group(2)}:00+03:00", None
                continue
            m = re.match(r"- \*\*(.+?)\*\*: (.*)$", line)
            if m and when:
                cur = _h(slug, m.group(1), m.group(2))
                r = row("comment", "linkedin", "owner", urn or slug, url, cur, "", m.group(1), "", False, when, m.group(2), (), now)
                if r:
                    out.append(r)
                continue
            m = re.match(r"\s+- replied: (.*)$", line)
            if m and when and cur:
                r = row("reply", "linkedin", "owner", urn or slug, url, _h(cur, "reply", m.group(1)), cur, me, "", True, when, m.group(1), (), now)
                if r:
                    out.append(r)
    # the owner's own comments on other people's posts: published/comments.jsonl (li.COMMENT_LOG)
    log = root / "published" / "comments.jsonl"
    if log.is_file():
        for line in log.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            mid = e.get("comment_urn") or _h(str(e.get("post")), str(e.get("at")), str(e.get("text")))
            r = row("reply" if e.get("reply_to") else "comment", "linkedin", "owner", e.get("post"), e.get("url"), mid, "", me, "", True, e.get("at"), e.get("text"), (), now)
            if r:
                out.append(r)
    return out


FETCHERS = {"instagram_dm": src_instagram_dm, "facebook_dm": src_facebook_dm, "instagram_comments": src_instagram_comments,
            "facebook_comments": src_facebook_comments, "youtube_comments": src_youtube_comments, "linkedin": src_linkedin}


# ------------------------------------------------------------------ merge, replied_by_us, files
def mark_replied(rows: list[dict]) -> None:
    """replied_by_us: some row of ours, in the same thread (a comment's thread is its root comment), is newer than this one. Our own rows stay False."""
    def key(r):
        return (r["platform"], r["thread_or_post_id"] if r["kind"] == "dm" else (r["parent_id"] or r["message_id"]))
    own_last: dict = {}
    answered = {(r["platform"], r["parent_id"]) for r in rows if r["is_own"] and r["parent_id"]}     # an own reply that names its parent counts at any time stamp
    for r in rows:
        if r["is_own"]:
            own_last[key(r)] = max(own_last.get(key(r), ""), r["created_at_utc"])
    for r in rows:
        r["replied_by_us"] = (not r["is_own"]) and ((r["platform"], r["message_id"]) in answered or own_last.get(key(r), "") > r["created_at_utc"])


def sort_rows(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=lambda r: (r["created_at_utc"], r["message_id"]), reverse=True)


def merge(old: list[dict], new: list[dict]) -> tuple[list[dict], int]:
    """Dedup by (platform, message_id): a fresh copy replaces the stored one but keeps the first harvested_at. Returns (all rows sorted, number of rows never seen before)."""
    by = {(r["platform"], r["message_id"]): r for r in old}
    added = 0
    for r in new:
        k = (r["platform"], r["message_id"])
        if k in by:
            r = {**r, "harvested_at": by[k].get("harvested_at") or r["harvested_at"]}
        else:
            added += 1
        by[k] = r
    rows = list(by.values())
    mark_replied(rows)
    return sort_rows(rows), added


def _csv_safe(v):
    """A cell that starts with = + - @ would run as a formula in Excel: prefix it with an apostrophe (CSV only; the JSONL keeps the raw text)."""
    s = v if isinstance(v, str) else str(v).lower() if isinstance(v, bool) else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@") else s


def write_files(d: Path, rows: list[dict]) -> None:
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / "inbox.jsonl.tmp"
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    ig.replace_retry(tmp, d / "inbox.jsonl")
    tmp = d / "inbox.csv.tmp"
    with tmp.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        for r in rows:
            w.writerow([_csv_safe(r.get(c, "")) for c in COLUMNS])
    ig.replace_retry(tmp, d / "inbox.csv")


def load_rows(d: Path) -> list[dict]:
    p = Path(d) / "inbox.jsonl"
    out = []
    if p.is_file():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


# ------------------------------------------------------------------ commands
def cmd_harvest(since_days: float | None = None, dry: bool = False, repo: Path | None = None, env: dict | None = None, only=None, **ctx_extra) -> int:
    repo = Path(repo or ig.REPO)
    d = out_dir(repo)
    env = env if env is not None else ig.load_env()
    at = utcnow()
    state = ig.read_json(d / "state.json") or {}
    src_state = state.get("sources") or {}
    old = load_rows(d)
    new_all, ok, lines = [], 0, []
    names = [s for s in SOURCES if not only or s in only]
    for name in names:
        if since_days is not None:
            since = at - timedelta(days=since_days)
        else:
            last = parse_ts((src_state.get(name) or {}).get("last_ok"))
            since = (last - OVERLAP) if last else None
        ctx = {"env": env, "now": at, "since": since, **ctx_extra}
        try:
            got = FETCHERS[name](ctx)
            if since:
                got = [r for r in got if (parse_ts(r["created_at_utc"]) or at) >= since]
            before = {(r["platform"], r["message_id"]) for r in old}
            fresh = sum(1 for r in got if (r["platform"], r["message_id"]) not in before)
            new_all += got
            ok += 1
            src_state[name] = {**src_state.get(name, {}), "last_run": at.isoformat(timespec="seconds"), "last_ok": at.isoformat(timespec="seconds"), "status": "ok", "rows": len(got), "new": fresh, "error": ""}
            lines.append(f"OK {name}: {len(got)} rows read, {fresh} new")
        except (SystemExit, Exception) as e:    # noqa: BLE001  one source never stops the others; the error is redacted
            msg = scrub(e, env)
            src_state[name] = {**src_state.get(name, {}), "last_run": at.isoformat(timespec="seconds"), "status": "FAIL", "error": msg}
            lines.append(f"FAIL {name}: {msg[5:].strip() if msg.startswith('FAIL ') else msg}")
    for ln in lines:
        print(ln)
    rows, added = merge(old, new_all)
    if dry:
        print(f"DRY: {len(new_all)} rows read, {added} would be new, {len(rows)} in all; nothing written")
    else:
        write_files(d, rows)
        ig.write_json(d / "state.json", {"last_harvest": at.isoformat(timespec="seconds"), "sources": src_state})
        print(f"inbox: {len(rows)} rows ({added} new) -> {d / 'inbox.csv'}")
    return 0 if ok else 2


def cmd_status(repo: Path | None = None) -> str:
    d = out_dir(Path(repo or ig.REPO))
    rows = load_rows(d)
    st = ig.read_json(d / "state.json") or {}
    out = [f"inbox: {len(rows)} rows in {d / 'inbox.csv'}" if rows else f"inbox: no rows yet ({d})"]
    by: dict = {}
    for r in rows:
        k = (r["platform"], r["kind"])
        by[k] = by.get(k, 0) + 1
    for (p, k), n in sorted(by.items()):
        out.append(f"  {p:10} {k:8} {n}")
    todo = sum(1 for r in rows if not r["is_own"] and not r["replied_by_us"])
    out.append(f"unanswered (not ours, no later reply of ours): {todo}")
    if rows:
        out.append(f"newest {rows[0]['created_at_amman']}   oldest {rows[-1]['created_at_amman']}")
    for n in SOURCES:
        s = (st.get("sources") or {}).get(n)
        out.append(f"  {n:19} " + (f"{s.get('status')} last_run {s.get('last_run')} rows {s.get('rows', '-')}" + (f" error: {s['error'][:120]}" if s.get("error") else "") if s else "never run"))
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Story-Wrap inbox: DMs and comments to one CSV (read only)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("harvest")
    p.add_argument("--since", type=float, default=None, help="only the last DAYS days (default: since the last good run of each source, minus 2 days)")
    p.add_argument("--dry", action="store_true")
    sub.add_parser("status")
    a = ap.parse_args(argv)
    if a.cmd == "status":
        print(cmd_status())
        return 0
    return cmd_harvest(a.since, a.dry)


if __name__ == "__main__":
    sys.exit(main())
