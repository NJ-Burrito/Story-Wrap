# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Facebook Page Reels poster and comment reader for Story-Wrap (Page «StoryPage», our own Meta app, official Graph API only).

    uv run tools/fb.py publish  <ep> [--go] [--force]   post the Reel to the Page; dry run without --go (no network, no credentials)
    uv run tools/fb.py comments <ep> [--force]          Facebook comments -> merged into work/episodes/<ep>/comments.json (platform + id deduped; ideas only, never votes)
    uv run tools/fb.py harvest  <ep> [--force]          Instagram comments (the vote source, required) then Facebook comments (ideas only); exit 3 = Facebook half failed
    uv run tools/fb.py late     <ep>                    the 24 h pass: new comments -> late-ideas.json (ideas only, decision.json untouched)
    uv run tools/fb.py status   [--live]                token state, per-episode state; --live also reads the Page name
    uv run tools/fb.py metrics  <ep>                    likes and comment count of the posted Reel -> work/episodes/<ep>/metrics-facebook.json

Same shape as ig.py and the same gates (`ig.publish_gates`), the same caption. Secrets live only in ~/.config/story-wrap/instagram.env:
FB_PAGE_ID, FB_PAGE_TOKEN (a Page token that does not expire); host graph.facebook.com (FB_API_HOST), version IG_API_VERSION (default v26.0).
Nothing is ever printed, logged or written to an output file with a credential in it.

The record of a Facebook post is work/episodes/<ep>/facebook.json, mirrored under the `facebook` key of post.json when that file exists
(Instagram's record; readers that do not know the key ignore it). Each platform is recorded separately: one failing never blocks or undoes the other.
Standard library only.
"""
import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ig   # noqa: E402
import seo   # noqa: E402
from ig import fail, need, now, read_json, redact, write_json, wdir   # noqa: E402

REPO = ig.REPO
POLL_MAX = 10          # status checks, one a minute (Reels processing is slower than a Page photo)
PAGE_EDGE_LIMIT = "50"


# ---------------------------------------------------------------- host, token, http
def host(env: dict) -> str:
    return env.get("FB_API_HOST") or "graph.facebook.com"


def base(env: dict) -> str:
    return f"https://{host(env)}/{env.get('IG_API_VERSION') or 'v26.0'}"


def has_creds(env: dict) -> bool:
    return bool(env.get("FB_PAGE_ID") and env.get("FB_PAGE_TOKEN"))


def api(env: dict, method: str, path: str, params: dict | None = None, headers: dict | None = None, data: bytes | None = None, url: str | None = None) -> dict:
    """One Graph call. The Page token travels as a header, never in a URL we build. Every failure (an HTTP error, a dead connection, a timeout, an answer that is
    not JSON) becomes one redacted FB-HTTP failure: the caller never sees a raw exception that could carry the token."""
    u = url or f"{base(env)}/{path.lstrip('/')}"
    h = {"Authorization": f"Bearer {env['FB_PAGE_TOKEN']}", **(headers or {})}
    if params and not url:
        if method == "POST":
            data = urllib.parse.urlencode(params).encode("utf-8")
            h["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            u += "?" + urllib.parse.urlencode(params)
    try:
        return ig._http(method, u, h, data)      # looked up at call time: tests replace ig._http
    except (RuntimeError, urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
        fail("FB-HTTP", redact(f"{type(e).__name__}: {e}", env))


def like_comment(env: dict, comment_id: str) -> bool:
    """Like one comment on our Page as the Page (POST /{comment-id}/likes with the Page token; pages_manage_engagement). Engagement on our own posts only (R-474)."""
    import re
    need(env, "FB_PAGE_TOKEN")
    if not re.fullmatch(r"[0-9A-Za-z_]+", str(comment_id or "")):
        fail("FB-LIKE-ID", "the comment id is not a plain id")
    r = api(env, "POST", f"{comment_id}/likes", None, {"Content-Type": "application/x-www-form-urlencoded"}, b"")
    return bool(r.get("success", True))


def pages(env: dict, path: str, params: dict) -> list:
    out, url = [], None
    while True:
        r = api(env, "GET", path, params if url is None else None, url=url)
        out += r.get("data", [])
        url = (r.get("paging") or {}).get("next")
        if not url:
            return out
        if not url.startswith(f"https://{host(env)}/"):
            fail("FB-PAGING", "paging.next points to another host; stopped")


def upload_host_ok(url: str) -> bool:
    """The binary upload carries the Page token in an OAuth header, so it only goes to https://*.facebook.com (rupload.facebook.com)."""
    u = urllib.parse.urlparse(url or "")
    h = (u.hostname or "").lower()
    return u.scheme == "https" and (h == "facebook.com" or h.endswith(".facebook.com"))


# ---------------------------------------------------------------- the record
PENDING = "finishing"      # written BEFORE the finish call: from then on the episode counts as posted for every retry
MIN_SCHEDULE_AHEAD_MIN = 11   # the Pages API takes a scheduled time 10 minutes to 29 days ahead
FB_AFTER_IG_MIN = 0           # the owner 2026-10-27: 19:00 on every platform, so the Facebook Reel goes live at once after the Instagram one (was +60 min: 19:30 / 20:30)


def rec_path(ep: str, repo: Path = REPO) -> Path:
    return wdir(ep, repo) / "facebook.json"


def load_record(ep: str, repo: Path = REPO) -> dict | None:
    """None = no file; the record; or {"corrupt": True} for a file that is not valid JSON (it still counts as posted: never post over a record we cannot read)."""
    p = rec_path(ep, repo)
    if not p.is_file():
        return None
    try:
        r = json.loads(p.read_text(encoding="utf-8"))
        return r if isinstance(r, dict) else {"corrupt": True}
    except (ValueError, OSError):
        return {"corrupt": True}


def is_posted(ep: str, repo: Path = REPO) -> bool:
    """Any facebook.json counts, pending ("finishing") and unreadable ones included: a retry needs --force."""
    return rec_path(ep, repo).is_file()


def go_live_at(r: dict | None) -> datetime | None:
    """When the Facebook Reel is (or was) live: its scheduled time, else the time we posted it."""
    try:
        t = (r or {}).get("publish_at") or (r or {}).get("posted_at")
        return datetime.fromisoformat(t) if t else None
    except (ValueError, TypeError):
        return None


def save_record(ep: str, rec: dict, repo: Path = REPO) -> None:
    """facebook.json is the truth; post.json (Instagram's record) carries a copy under `facebook` when it exists."""
    write_json(rec_path(ep, repo), rec)
    pj = wdir(ep, repo) / "post.json"
    try:
        post = read_json(pj)
    except ValueError:
        post = None
    if isinstance(post, dict):
        post["facebook"] = {k: rec.get(k) for k in ("video_id", "permalink", "posted_at", "publish_at", "state")}
        write_json(pj, post)


def plan_go_live(ep: str, repo: Path, at: datetime) -> datetime | None:
    """The scheduled time (Instagram's post time + FB_AFTER_IG_MIN; 0 since 2026-10-27, so normally None = publish now) when Instagram is on record and that is still 11+ minutes ahead; None = publish now."""
    try:
        post = read_json(wdir(ep, repo) / "post.json")
        t = datetime.fromisoformat(post["posted_at"]) + timedelta(minutes=FB_AFTER_IG_MIN) if isinstance(post, dict) and post.get("posted_at") else None
    except (ValueError, TypeError, KeyError):
        t = None
    return t if t and t >= at + timedelta(minutes=MIN_SCHEDULE_AHEAD_MIN) else None


# ---------------------------------------------------------------- publish
def multipart(fields: dict, file_field: str, file_name: str, file_bytes: bytes, mime: str = "image/jpeg") -> tuple:
    """(body, content_type) of a multipart/form-data upload, standard library only."""
    bnd = "swcover" + hashlib.sha1(file_bytes[:4096]).hexdigest()[:16]
    parts = [f'--{bnd}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode("utf-8") for k, v in fields.items()]
    parts.append(f'--{bnd}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{file_name}"\r\nContent-Type: {mime}\r\n\r\n'.encode("utf-8") + file_bytes + b"\r\n")
    parts.append(f"--{bnd}--\r\n".encode("utf-8"))
    return b"".join(parts), f"multipart/form-data; boundary={bnd}"


def set_thumbnail(env: dict, vid: str, jpg: Path) -> dict:
    """R-501: the Reel's thumbnail is the grid poster. Graph API `POST /{video-id}/thumbnails` (source=<file>, is_preferred=true). Never fatal: returns {"state": "set"} or {"state": "failed", "error": ...}.
    NOT verified live for Reels (the endpoint is documented for Page videos; a Reel may refuse it): a refusal is recorded and the owner sets the cover in the app (Edit cover)."""
    try:
        body, ctype = multipart({"is_preferred": "true"}, "source", "cover.jpg", Path(jpg).read_bytes())
        r = api(env, "POST", f"{vid}/thumbnails", headers={"Content-Type": ctype}, data=body)
        return {"state": "set" if r.get("success", True) else "failed", "error": None if r.get("success", True) else "success=false"}
    except SystemExit as e:
        return {"state": "failed", "error": str(e)[:200]}


def cmd_thumbnail(ep: str, go: bool = False, repo: Path = REPO, env: dict | None = None, cover: Path | None = None) -> dict:
    """`post_extra.py covers <ep> --go`: set the grid poster as the thumbnail of an already posted Facebook Reel. Dry run without --go."""
    rec = load_record(ep, repo)
    if not rec or not rec.get("video_id"):
        fail("FB-NOPOST", f"{ep} has no readable facebook.json with a video id")
    f = Path(cover) if cover else ig.cover_file(wdir(ep, repo))
    if f is None or not f.is_file():
        fail("FB-NOCOVER", f"{ep} has no cover.png / cover.jpg in its folder")
    if not go:
        print(f"DRY RUN (add --go). Would set {f.name} as the thumbnail of Facebook video {rec['video_id']}.")
        return rec
    env = env if env is not None else ig.load_env()
    need(env, "FB_PAGE_ID", "FB_PAGE_TOKEN")
    rec["thumbnail"] = set_thumbnail(env, rec["video_id"], f)
    save_record(ep, rec, repo)
    print(f"Facebook thumbnail of {ep}: {rec['thumbnail']['state']}" + (f" ({rec['thumbnail']['error']})" if rec["thumbnail"].get("error") else ""))
    return rec


def cmd_publish(ep: str, go: bool = False, force: bool = False, repo: Path = REPO, env: dict | None = None, sleep=time.sleep) -> dict:
    why = ig.publish_gates(ep, repo)
    if why:
        fail("FB-GATE", "refusing to post " + ep + ": " + "; ".join(why))
    w = wdir(ep, repo)
    if is_posted(ep, repo) and not force:
        r = load_record(ep, repo) or {}
        fail("FB-ALREADY", f"{ep} is already on record for Facebook (work/episodes/{ep}/facebook.json, state {r.get('state', 'unreadable')!r}); check the Page, then --force to post again")
    title, caption = ig.facebook_parts(ep, repo)
    video = w / "episode.mp4"
    if ig.has_tashkeel(caption) or ig.has_tashkeel(title):
        fail("FB-NO-TASHKEEL", "the post text still carries tashkeel or tatweel; nothing was posted")
    bad = ig.caption_problems(caption, "facebook") + [f"title: {b}" for b in ig.caption_problems(title, "facebook")]
    if bad:
        fail("FB-CAPTION-BAIT", "the Facebook text breaks the wording rules (pipelines/AUDIENCE.md): " + "; ".join(bad) + "; nothing was posted")
    plan = {"episode": ep, "video": video.as_posix(), "bytes": video.stat().st_size, "title": title, "caption": caption, "mode": "DRY RUN"}
    if not go:
        when = plan_go_live(ep, repo, now())
        print("DRY RUN (add --go to post to the Facebook Page). Gates clear. Title: " + title + "\nDescription:\n" + caption
              + f"\nVideo: {plan['video']} ({plan['bytes']} bytes), Reels upload, is_ai_generated=true, " + (f"scheduled for {when.isoformat(timespec='minutes')}." if when else "published at once."))
        return plan
    if not (w / "post.json").is_file():
        fail("FB-WAIT-INSTAGRAM", f"{ep} is not on Instagram yet: Facebook never goes live before Instagram, so it waits for the Instagram post; nothing was uploaded")
    env = env if env is not None else ig.load_env()
    need(env, "FB_PAGE_ID", "FB_PAGE_TOKEN")
    pid = env["FB_PAGE_ID"]
    start = api(env, "POST", f"{pid}/video_reels", {"upload_phase": "start"})
    vid, upload_url = start.get("video_id"), start.get("upload_url")
    if not vid or not upload_url:
        fail("FB-START", "no video_id / upload_url returned by the start phase; nothing was published")
    if not upload_host_ok(upload_url):
        fail("FB-START", "upload_url is not an https *.facebook.com address; the Page token was not sent")
    api(env, "POST", "", url=upload_url, headers={"Authorization": f"OAuth {env['FB_PAGE_TOKEN']}", "offset": "0", "file_size": str(plan["bytes"])}, data=video.read_bytes())
    at = now()
    live = plan_go_live(ep, repo, at)
    rec = {"episode": ep, "video_id": vid, "permalink": None, "posted_at": at.isoformat(timespec="seconds"), "publish_at": (live or at).isoformat(timespec="seconds"),
           "state": PENDING, "title": title, "caption": caption}
    save_record(ep, rec, repo)          # BEFORE the finish call: if its answer is lost the Reel may be live, and any retry now needs --force
    params = {"upload_phase": "finish", "video_id": vid, "title": title, "description": caption, "is_ai_generated": "true"}
    params.update({"video_state": "SCHEDULED", "scheduled_publish_time": str(int(live.timestamp()))} if live else {"video_state": "PUBLISHED"})
    try:
        fin = api(env, "POST", f"{pid}/video_reels", params)
    except SystemExit as e:
        fail("FB-FINISH-UNKNOWN", f"video {vid}: the finish call did not answer ({e}); recorded as {PENDING!r}, the Reel may be live: check the Page before any --force")
    if fin.get("success") is False:
        rec["state"] = "finish-refused"
        save_record(ep, rec, repo)
        fail("FB-FINISH", f"video {vid}: the finish phase did not succeed; nothing was trimmed or retried")
    rec["state"] = "processing"
    save_record(ep, rec, repo)
    status, st = None, {}
    for _ in range(POLL_MAX):
        st = (api(env, "GET", vid, {"fields": "status"}).get("status") or {})
        status = st.get("video_status")
        if status in ("ready", "error", "expired", "processing_failed"):
            break
        sleep(ig.POLL_EVERY_S)
    if status != "ready":
        rec["state"] = f"not-ready:{status}"
        save_record(ep, rec, repo)
        detail = json.dumps({k: v for k, v in st.items() if k != "video_status"}, ensure_ascii=False)[:300]
        fail("FB-PROCESS", f"video {vid} ended as {status!r} ({detail}); the video was NOT trimmed or re-encoded; recorded in facebook.json, tell the owner before any --force")
    link = None
    try:
        link = api(env, "GET", vid, {"fields": "permalink_url"}).get("permalink_url")
    except SystemExit:
        if not live:
            raise
    rec.update(permalink=("https://www.facebook.com" + link) if link and link.startswith("/") else link, state="scheduled" if live else "published")
    cf = ig.cover_file(w)
    if cf is not None:      # R-501: the thumbnail is the grid poster; a refusal is recorded, never fatal
        rec["thumbnail"] = set_thumbnail(env, vid, cf)
    save_record(ep, rec, repo)
    print(f"{'SCHEDULED' if live else 'POSTED'} {ep} to Facebook: {rec['permalink']} at {rec['publish_at']}")
    return rec


# ---------------------------------------------------------------- comments
def fb_comment(c: dict, page_id: str, parent: str | None) -> dict:
    frm = c.get("from") or {}
    return {"id": c.get("id"), "platform": "facebook", "parent_id": parent, "text": c.get("message", ""), "username": frm.get("name"),
            "user_id": frm.get("id"), "timestamp": c.get("created_time"), "own": bool(frm.get("id") and str(frm["id"]) == str(page_id))}


def merge_comments(old: list, new: list, platform: str) -> list:
    """Keep the other platforms' comments, replace this platform's, dedupe by (platform, id). A comment without `platform` is Instagram's."""
    seen, out = set(), []
    for c in [x for x in old if (x.get("platform") or "instagram") != platform] + new:
        c = {**c, "platform": c.get("platform") or "instagram"}
        key = (c["platform"], c.get("id"))
        if c.get("id") is not None and key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def cmd_comments(ep: str, force: bool = False, repo: Path = REPO, env: dict | None = None, at: datetime | None = None) -> dict:
    w = wdir(ep, repo)
    rec = load_record(ep, repo)
    if not rec or not rec.get("video_id"):
        fail("FB-NOPOST", f"{ep} has no readable facebook.json: nothing known to be posted to Facebook")
    live_at = go_live_at(rec)
    if live_at is None:
        fail("FB-RECORD", f"{ep}: facebook.json has no usable time")
    due = live_at + timedelta(hours=ig.HOURS_BEFORE_COMMENTS)
    cur = at or now()
    if cur < due and not force:
        fail("FB-TOO-EARLY", f"{(due - cur).total_seconds() / 3600:.1f} h until the {ig.HOURS_BEFORE_COMMENTS} h mark; --force to read now")
    env = env if env is not None else ig.load_env()
    need(env, "FB_PAGE_ID", "FB_PAGE_TOKEN")
    pid, vid = env["FB_PAGE_ID"], rec["video_id"]
    fields = {"fields": "id,message,created_time,from{id,name}", "limit": PAGE_EDGE_LIMIT, "order": "chronological"}
    mine = []
    for c in pages(env, f"{vid}/comments", fields):
        mine.append(fb_comment(c, pid, None))
        for r in pages(env, f"{c['id']}/comments", fields):
            mine.append(fb_comment(r, pid, c.get("id")))
    cm = read_json(w / "comments.json") or {}
    merged = merge_comments(cm.get("comments", []), mine, "facebook")
    own = sorted({*(cm.get("own_usernames") or []), *(c["username"] for c in mine if c["own"] and c.get("username"))})
    res = {**cm, "episode": ep, "fetched_at": cur.isoformat(timespec="seconds"), "count": len(merged), "own_usernames": own, "comments": merged,
           "facebook_video_id": vid, "platforms": sorted({c["platform"] for c in merged})}
    blob = json.dumps(res, ensure_ascii=False)
    for k in ig.SECRET_KEYS:
        if env.get(k) and env[k] in blob:
            fail("FB-LEAK", "a credential value appeared in the comments output; not written")
    write_json(w / "comments.json", res)
    print(f"{ep}: {len(mine)} Facebook comments and replies merged -> work/episodes/{ep}/comments.json ({len(merged)} in all)")
    return res


def harvest(ep: str, force: bool = False, repo: Path = REPO, env: dict | None = None, at: datetime | None = None) -> dict:
    """Comments into one comments.json. OWNER RULE (owner, 2026-10-25): the vote is read from INSTAGRAM ONLY, so Instagram is the required half and runs first:
    if it is not posted or cannot be read, this FAILS and nothing is finalised (the Facebook rows alone must never become a decision). Facebook is read after
    it for the idea pool only; a Facebook failure (too early, token, network) is returned under `errors`, marks the harvest `partial` and never touches
    Instagram's rows or its decision."""
    if not (wdir(ep, repo) / "post.json").is_file():
        fail("FB-HARVEST", f"{ep} is not on Instagram, the only vote source: nothing was harvested")
    ig.cmd_comments(ep, force=force, repo=repo, env=env, at=at)         # fatal on failure: no decision from a failed Instagram read
    done, errors = ["instagram"], {}
    if is_posted(ep, repo):
        try:
            cmd_comments(ep, force=force, repo=repo, env=env, at=at)
            done.append("facebook")
        except SystemExit as e:
            errors["facebook"] = str(e)
    return {"done": done, "errors": errors, "partial": bool(errors)}


def late_pass(ep: str, repo: Path = REPO, env: dict | None = None, at: datetime | None = None) -> dict:
    """The 24 h pass (DESIGN 6.4): read the comments again and file the NEW ones as ideas for the writer in late-ideas.json. decision.json is never changed."""
    import vote
    w = wdir(ep, repo)
    dec = read_json(w / "decision.json")
    if dec is None:
        fail("FB-LATE", f"{ep} has no decision.json: the late pass only follows a counted vote")
    res = harvest(ep, force=True, repo=repo, env=env, at=at)
    cm = read_json(w / "comments.json") or {}
    seen = set(dec.get("seen_ids") or [])
    own = {o.strip().lstrip("@").lower() for o in cm.get("own_usernames") or []}
    choices = vote.load_choices(vote.find_ep(ep, repo))
    ideas = []
    for c in cm.get("comments", []):
        plat = c.get("platform") or "instagram"
        if f"{plat}:{c.get('id')}" in seen or c.get("own") or (c.get("username") or "").strip().lstrip("@").lower() in own:
            continue
        t = vote.idea_text(c.get("text", ""), choices)
        if t:
            ideas.append({"id": c.get("id"), "platform": plat, "username": c.get("username"), "text": t})
    out = {"episode": ep, "fetched_at": (at or now()).isoformat(timespec="seconds"), "note": "ideas only: the decision was made at the 14:00 harvest and is never changed",
           "count": len(ideas), "ideas": ideas[:vote.IDEAS_MAX], "errors": res["errors"]}
    write_json(w / "late-ideas.json", out)
    nb = w / "next-brief.md"
    if nb.is_file() and ideas:
        nb.write_text(nb.read_text(encoding="utf-8").rstrip("\n") + "\n\n## Late ideas (24 h)\n\n" + "\n".join(f"- ({i['platform']}) {i['text']}" for i in out["ideas"][:12]) + "\n", encoding="utf-8")
    print(f"{ep}: {len(ideas)} late ideas -> work/episodes/{ep}/late-ideas.json")
    return out


# ---------------------------------------------------------------- metrics
def cmd_metrics(ep: str, repo: Path = REPO, env: dict | None = None, at: datetime | None = None) -> dict:
    rec = load_record(ep, repo)
    if not rec or not rec.get("video_id"):
        fail("FB-NOPOST", f"{ep} has no readable facebook.json: nothing known to be posted to Facebook")
    env = env if env is not None else ig.load_env()
    need(env, "FB_PAGE_TOKEN")
    r = api(env, "GET", rec["video_id"], {"fields": "likes.summary(true).limit(0),comments.summary(true).limit(0),permalink_url"})
    tot = lambda k: ((r.get(k) or {}).get("summary") or {}).get("total_count")   # noqa: E731
    res = {"episode": ep, "platform": "facebook", "fetched_at": (at or now()).isoformat(timespec="seconds"), "likes": tot("likes"), "comments": tot("comments"),
           "permalink": rec.get("permalink")}
    blob = json.dumps(res, ensure_ascii=False)
    for k in ig.SECRET_KEYS:
        if env.get(k) and env[k] in blob:
            fail("FB-LEAK", "a credential value appeared in the metrics output; not written")
    write_json(wdir(ep, repo) / "metrics-facebook.json", res)
    print(f"{ep}: {res['likes']} likes, {res['comments']} comments on Facebook -> work/episodes/{ep}/metrics-facebook.json")
    return res


def metrics_all(ep: str, repo: Path = REPO) -> dict:
    """Likes and comment counts from every platform the episode is posted on; one failing is recorded, the other still runs."""
    done, errors = [], {}
    for name, fn, posted in (("instagram", ig.cmd_metrics, (wdir(ep, repo) / "post.json").is_file()), ("facebook", cmd_metrics, is_posted(ep, repo))):
        if not posted:
            continue
        try:
            fn(ep, repo=repo)
            done.append(name)
        except SystemExit as e:
            errors[name] = str(e)
    if errors and not done:
        fail("FB-METRICS", "; ".join(f"{k}: {v}" for k, v in errors.items()))
    return {"done": done, "errors": errors}


# ---------------------------------------------------------------- status
def token_state(env: dict) -> str:
    if not env.get("FB_PAGE_TOKEN"):
        return "no Facebook Page token"
    return "Page token present (does not expire)" + ("" if env.get("FB_PAGE_ID") else "; FB_PAGE_ID MISSING")


def cmd_status(live: bool = False, repo: Path = REPO, env: dict | None = None) -> str:
    env = env if env is not None else ig.load_env()
    out = [f"credentials file: {'found' if ig.CONF.is_file() else 'MISSING'} ({ig.CONF})", f"FB_PAGE_ID: {'set' if env.get('FB_PAGE_ID') else 'missing'}", token_state(env)]
    wd = repo / "work" / "episodes"
    for d in sorted(wd.glob("*")) if wd.is_dir() else []:
        rec = load_record(d.name, repo)
        out.append(f"{d.name}: " + (f"on record for Facebook {rec.get('posted_at')} ({rec.get('state', 'unreadable file')}) {rec.get('permalink') or ''}".rstrip() if rec else "not posted to Facebook"))
    if live:
        need(env, "FB_PAGE_ID", "FB_PAGE_TOKEN")
        r = api(env, "GET", env["FB_PAGE_ID"], {"fields": "name"})
        out.append(f"live check: Page name {r.get('name')!r}")
    s = redact("\n".join(out), env)
    print(s)
    return s


PAGE_SEO_FIELDS = "name,about,description,category,username,fan_count"


def cmd_page_seo(go: bool = False, env: dict | None = None) -> dict:
    """Set the Page's short description («about») from data/seo/keywords.json with the Page token. Dry run by default (reads the Page, writes nothing).
    Only `about` is written: the Graph API has no way to set the username (Page settings only), the name needs Meta review, and the category is not guessed.
    A refused write (missing pages_manage_metadata, or any Graph error) is reported as-is with its error code; nothing is retried or worked around."""
    env = env if env is not None else ig.load_env()
    need(env, "FB_PAGE_ID", "FB_PAGE_TOKEN")
    before = api(env, "GET", env["FB_PAGE_ID"], {"fields": PAGE_SEO_FIELDS})
    want = seo.load()["facebook_about"]
    out = {"mode": "WRITE" if go else "DRY RUN", "before": before, "about_to": want, "changes": before.get("about") != want}
    if go and out["changes"]:
        try:
            out["write"] = api(env, "POST", env["FB_PAGE_ID"], {"about": want})
        except ig.IgError as e:       # api() turns a Graph refusal into one redacted FB-HTTP failure
            out["write"] = f"REFUSED: {redact(str(e), env)}"
        out["after"] = api(env, "GET", env["FB_PAGE_ID"], {"fields": PAGE_SEO_FIELDS})
        out["readback_ok"] = out["after"].get("about") == want
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Facebook Page Reels for Story-Wrap")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("publish"); p.add_argument("ep"); p.add_argument("--go", action="store_true"); p.add_argument("--force", action="store_true")
    for n in ("comments", "harvest"):
        p = sub.add_parser(n); p.add_argument("ep"); p.add_argument("--force", action="store_true")
    p = sub.add_parser("late"); p.add_argument("ep")
    p = sub.add_parser("thumbnail"); p.add_argument("ep"); p.add_argument("--go", action="store_true"); p.add_argument("--cover", help="a jpg to use instead of the episode folder's cover.jpg")
    p = sub.add_parser("status"); p.add_argument("--live", action="store_true")
    p = sub.add_parser("metrics"); p.add_argument("ep")
    p = sub.add_parser("page-seo"); p.add_argument("--go", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "page-seo":
        print(json.dumps(cmd_page_seo(a.go), ensure_ascii=False, indent=1))
    elif a.cmd == "publish":
        cmd_publish(a.ep, a.go, a.force)
    elif a.cmd == "comments":
        cmd_comments(a.ep, a.force)
    elif a.cmd == "harvest":
        r = harvest(a.ep, a.force)
        if r["partial"]:
            print("PARTIAL " + "; ".join(f"{k}: {v}" for k, v in r["errors"].items()) + " (Instagram was read; its decision is not affected)")
            return 3
    elif a.cmd == "thumbnail":
        cmd_thumbnail(a.ep, a.go, cover=Path(a.cover) if a.cover else None)
    elif a.cmd == "late":
        late_pass(a.ep)
    elif a.cmd == "status":
        cmd_status(a.live)
    else:
        cmd_metrics(a.ep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
