# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Instagram Graph API poster and comment reader for Story-Wrap (our own free Meta app; research/instagram-api.md).

    uv run tools/ig.py publish  <ep> [--go] [--force]   post the Reel; dry run without --go (no network, no credentials)
    uv run tools/ig.py comments <ep> [--force]          all comments and replies -> work/episodes/<ep>/comments.json
    uv run tools/ig.py status   [--live]                token, per-episode state; --live also asks the publish quota
    uv run tools/ig.py refresh                          refresh the long-lived token (60 days) and save it
    uv run tools/ig.py plan     <ep>                    print the Task Scheduler command for 12 h after the post (never registers)
    uv run tools/ig.py metrics  <ep>                    likes and comment count of the posted Reel -> work/episodes/<ep>/metrics.json
    uv run tools/ig.py reply    <comment_id> <text> [--go]   one reply under a comment (dry run without --go; the board and its daily limit call this)

Secrets live only in ~/.config/story-wrap/instagram.env and are never printed, logged or written to an output file.
Keys: IG_USER_ID, IG_ACCESS_TOKEN, IG_USERNAME (our own account), optional IG_API_HOST (default graph.instagram.com),
IG_API_VERSION (default v26.0), IG_TOKEN_ISSUED (ISO time, written by `refresh`).
Standard library only. No scraping, no other service.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from datetime import time as dtime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from arabic_display import display_text, has_tashkeel   # noqa: E402
import media_host   # noqa: E402
import secret_gate   # noqa: E402
import seo   # noqa: E402

REPO = Path(os.environ.get("SW_REPO") or Path(__file__).resolve().parents[1])
CONF = Path(os.environ.get("SW_IG_ENV") or Path.home() / ".config" / "story-wrap" / "instagram.env")

MIN_CRITIC = 9              # heal.json critic.min_score
HOURS_BEFORE_COMMENTS = 12  # the earliest a comment read is allowed (a floor guard); the scheduled harvest is 14:00 the next day (loop_gate.HARVEST_AT)
URL_ABOVE_BYTES = 18 * 1024 * 1024   # above this the resumable upload is refused by Meta (about 20 MB, measured 2026-10-26): host the original file and use video_url
POLL_EVERY_S, POLL_MAX = 60, 10   # Meta: check once a minute; 10 min so a large video_url fetch (~120 MB) has time (2026-10-26)
SECRET_KEYS = ("IG_ACCESS_TOKEN", "IG_APP_SECRET", "FB_PAGE_TOKEN", "IG_PUBLISH_TOKEN")   # FB_PAGE_TOKEN: tools/fb.py shares this redaction


class IgError(SystemExit):
    pass


def fail(code: str, msg: str):
    raise IgError(f"FAIL [{code}] {msg}")


# ---------------------------------------------------------------- credentials (never printed)
def load_env(path: Path | None = None) -> dict:
    p = Path(path or CONF)
    vals = {}
    if p.is_file():
        for line in p.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                vals[k.strip()] = v.strip().strip('"').strip("'")
    return vals


def need(env: dict, *keys):
    miss = [k for k in keys if not env.get(k)]
    if miss:
        fail("IG-CREDS", f"missing {', '.join(miss)} in {CONF} (setup steps: research/instagram-api.md section 7)")


def redact(text, env: dict) -> str:
    """Remove every secret value (and any access_token=... query) from a string before it can be shown or stored."""
    s = str(text)
    for k in SECRET_KEYS:
        v = env.get(k)
        if v:
            s = s.replace(v, "[REDACTED]")
    return re.sub(r"(access_token=)[^&\s\"']+", r"\1[REDACTED]", s)


def publish_env(env: dict) -> dict:
    """Publishing (container, rupload, status, media_publish, the read of the new media) needs the Page token on graph.facebook.com:
    graph.instagram.com refuses upload_type=resumable for REELS/STORIES (measured 2026-10-26). Without IG_PUBLISH_TOKEN the env is unchanged."""
    if env.get("IG_PUBLISH_TOKEN"):
        return {**env, "IG_API_HOST": env.get("IG_PUBLISH_HOST") or "graph.facebook.com", "IG_ACCESS_TOKEN": env["IG_PUBLISH_TOKEN"]}
    return env


def read_pages(env: dict, path: str, params: dict, extra_fields: str = "") -> list:
    """READ an Instagram edge (media, comments, replies). Media published through the Facebook-login route (every Reel since 2026-10-26) is readable only with the
    Page token on graph.facebook.com: the Instagram-login token gets 0 rows, not an error (measured 2026-10-26). So: the Page token first when IG_PUBLISH_TOKEN is set
    (extra_fields, e.g. `from`, only ride on that route), the Instagram-login token when it is not set or the Page read fails."""
    if env.get("IG_PUBLISH_TOKEN"):
        p = dict(params)
        if extra_fields:
            p["fields"] = f"{p['fields']},{extra_fields}"
        try:
            return pages(publish_env(env), path, p)
        except IgError:
            pass
    return pages(env, path, params)


def base(env: dict) -> str:
    return f"https://{env.get('IG_API_HOST') or 'graph.instagram.com'}/{env.get('IG_API_VERSION') or 'v26.0'}"


# ---------------------------------------------------------------- http (replaced in tests)
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A Graph call is never redirected: urllib would carry the Authorization header to the new host. A redirect surfaces as an HTTP 3xx error instead."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def _http(method: str, url: str, headers: dict | None = None, data: bytes | None = None) -> dict:
    req = urllib.request.Request(url, data=data, method=method, headers={"User-Agent": "story-wrap-ig/1.0", **(headers or {})})
    try:
        with _OPENER.open(req, timeout=180) as r:
            txt = r.read().decode("utf-8") or "{}"
            return json.loads(txt)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} {method} {url.split('?')[0]}: {e.read().decode('utf-8', 'replace')[:600]}")


def api(env: dict, method: str, path: str, params: dict | None = None, headers: dict | None = None, data: bytes | None = None, url: str | None = None) -> dict:
    """One Graph call. The token travels as a Bearer header, never in a URL we build; errors are redacted."""
    u = url or f"{base(env)}/{path.lstrip('/')}"
    h = {"Authorization": f"Bearer {env['IG_ACCESS_TOKEN']}", **(headers or {})}
    if params and not url:
        if method == "POST":            # form body: long Arabic captions stay out of the URL
            data = urllib.parse.urlencode(params).encode("utf-8")
            h["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            u += "?" + urllib.parse.urlencode(params)
    try:
        return _http(method, u, h, data)
    except RuntimeError as e:
        fail("IG-HTTP", redact(e, env))


def pages(env: dict, path: str, params: dict) -> list:
    """Follow paging.next until it disappears (an empty page may still carry `next`)."""
    out, url = [], None
    host = f"https://{env.get('IG_API_HOST') or 'graph.instagram.com'}/"
    while True:
        r = api(env, "GET", path, params if url is None else None, url=url)
        out += r.get("data", [])
        url = (r.get("paging") or {}).get("next")
        if not url:
            return out
        if not url.startswith(host):
            fail("IG-PAGING", "paging.next points to another host; stopped")


# ---------------------------------------------------------------- episode files
def find_ep(ep: str, repo: Path = REPO) -> Path:
    for c in sorted((repo / "bible" / "series").glob(f"*/episodes/{ep}")):
        if c.is_dir():
            return c
    fail("IG-EP", f"episode {ep!r} not found under bible/series/*/episodes/")


def wdir(ep: str, repo: Path = REPO) -> Path:
    return repo / "work" / "episodes" / ep


def read_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


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
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    replace_retry(tmp, p)


def now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- gates before posting
def publish_gates(ep: str, repo: Path = REPO) -> list:
    """Reasons NOT to post (empty list = clear). Compose gate PASS and complete, critic >= 9, the video exists."""
    w, why = wdir(ep, repo), []
    rep = read_json(w / "gate" / "report.json")
    if rep is None:
        why.append("compose gate report missing (work/episodes/%s/gate/report.json): run `compose.py gate`" % ep)
    else:
        if rep.get("verdict") != "PASS":
            why.append(f"compose gate verdict is {rep.get('verdict')!r}, not PASS")
        if rep.get("complete") is False:
            why.append("compose gate is INCOMPLETE (render gate skipped)")
        bad = [c.get("id") for c in rep.get("checks", []) if c.get("status") == "fail"]
        if bad:
            why.append("failing checks: " + ", ".join(map(str, bad[:5])))
    cr = read_json(w / "heal" / "critic.json")
    if cr is None:
        why.append("critic record missing (work/episodes/%s/heal/critic.json): run the heal loop" % ep)
    else:
        sc = cr.get("score")
        if not isinstance(sc, int) or isinstance(sc, bool) or sc < MIN_CRITIC:
            # Owner override (owner, 2026-10-27, E02 at 8): heal/owner-approval.json naming this exact critic score and video lets the post through; the gates above still apply
            ok = read_json(w / "heal" / "owner-approval.json") or {}
            if not (ok.get("by") == "the owner" and ok.get("score") == sc and ok.get("video_sha") and ok.get("video_sha") == cr.get("video_sha")):
                why.append(f"critic score {sc!r} < {MIN_CRITIC}")
    if not (w / "episode.mp4").is_file():
        why.append("episode.mp4 missing")
    return why


def episode_title(ep_dir: Path) -> str:
    o = ep_dir / "outline.md"
    if o.is_file():
        m = re.match(r"#\s*(\S+)\s+(.+?)\s*/", o.read_text(encoding="utf-8").splitlines()[0] + " /")
        if m:
            return m.group(2).strip()
    return ""


def typed_phrase(text_ar: str) -> str:
    """A choice as the caption shows it: the short phrase in quotes, without a leading number (C13: viewers write the choice in words)."""
    return "«" + re.sub(r"^[0-9٠-٩۰-۹]+\s*", "", text_ar).strip() + "»"


HASHTAGS = {"instagram": seo.hashtags("instagram"), "facebook": seo.hashtags("facebook")}   # DESIGN 4.2: 3 on Instagram, 2 on Facebook; the words live in data/seo/keywords.json
HASHTAG_MAX = {"instagram": 3, "facebook": 2}
CLOSING = "الحلقة القادمة تتبع ما تكتبونه."      # DESIGN 4.1: a statement of how the story works, not a request
BAIT = ("اكتبوا اختياركم", "علقوا", "صوتوا", "اختاروا", "شاركوا", "اذكروا", "اضغطوا", "تابعوا لتعرفوا")   # DESIGN 4.1 "Never" and 5.2 "Words banned"
_BAIT_DIGITS = re.compile(r"(?:\b[1-9١-٩]\s*(?:أو|او|or)\s*[1-9١-٩]\b|(?:comment|علق\w*|اكتب\w*)\s*[1-9١-٩]\b)", re.I)
_EMOJI = "[\U0001F000-\U0001FFFF\u2600-\u27BF]"


def caption_problems(text: str, platform: str = "instagram") -> list:
    """Reasons a caption may not go out (DESIGN 4.1 and 5.2): engagement-bait wording, a digit to type, too many hashtags."""
    t = display_text(text)
    why = [f"engagement-bait wording {w!r}" for w in BAIT if w in t]
    if _BAIT_DIGITS.search(t):
        why.append("a digit to type (\"comment 1 or 2\")")
    why += secret_gate.secret_problems(text)    # a credential never goes out (security 2026-10-27, #1/#2)
    n = len(re.findall(r"#\w+", t))
    if n > HASHTAG_MAX.get(platform, 3):
        why.append(f"{n} hashtags (at most {HASHTAG_MAX.get(platform, 3)} on {platform})")
    return why


def episode_number_ar(ep: str) -> str:
    num = re.sub(r"\D", "", ep) or ep
    return num.lstrip("0").translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")) or "٠"


def build_caption(ep: str, repo: Path = REPO, platform: str = "instagram") -> str:
    """The post text. Instagram: caption.txt in the episode folder wins (the writer's text, DESIGN 4.3), otherwise a template caption: number and title,
    the question with the two options named as story facts, the reason ask, the closing statement and 3 hashtags. Facebook: caption-facebook.txt wins,
    otherwise the Instagram text rewritten by facebook_parts. Never a digit to type and never \"comment 1 or 2\" (caption_problems checks both)."""
    if platform == "facebook":
        return facebook_parts(ep, repo)[1]
    ep_dir = find_ep(ep, repo)
    f = ep_dir / "caption.txt"
    if f.is_file() and f.read_text(encoding="utf-8").strip():
        return display_text(f.read_text(encoding="utf-8"))
    sl = read_json(ep_dir / "shotlist.json") or {}
    card = sl.get("end_card") or {}
    ch = card.get("choices") or []
    if len(ch) != 2:
        fail("IG-CAPTION", "the end card needs exactly 2 choices to make a caption")
    head = f"الحلقة {episode_number_ar(ep)}" + (f" · {episode_title(ep_dir)}" if episode_title(ep_dir) else "")
    lines = [head + " 🎬", ""]
    prev = re.sub(r"\d+$", lambda m: str(int(m.group()) - 1).zfill(len(m.group())), ep)
    pd = read_json(wdir(prev, repo) / "decision.json") if prev != ep else None
    if pd and pd.get("showrunner_pick", {}) and pd["showrunner_pick"].get("reason_ar"):
        lines += [f"🗳️ {pd['showrunner_pick']['reason_ar']}", ""]
    elif pd and pd.get("winner"):
        w = next((c["text_ar"] for c in pd["choices"] if c["id"] == pd["winner"]), "")
        lines += [f"🗳️ اخترتم: {w} ({pd['counts'][pd['winner']]} صوت)", ""]
    q = card.get("question_ar") or ""
    lines += [f"❓ {q}".rstrip(), "↔️ " + " أم ".join(typed_phrase(c["text_ar"]) for c in ch) + "؟",
              "💬 قولوا لنا لماذا، وماذا تتوقعون أن يحدث بعد ذلك.", "", CLOSING, "", HASHTAGS["instagram"]]
    return display_text("\n".join(lines))


def facebook_parts(ep: str, repo: Path = REPO) -> tuple:
    """(title, description) for the Facebook Reel. caption-facebook.txt (and title-facebook.txt) in the episode folder win. Otherwise the Instagram text is
    rewritten the way DESIGN 4.1 says: the series and number move to the `title` («the series | الحلقة N»), the first line keeps only the hook with
    its emoji, the closing line gains «الحلقة N من ...», and the hashtags drop to 2."""
    ep_dir = find_ep(ep, repo)
    ig_text = build_caption(ep, repo, "instagram")
    n_ar = episode_number_ar(ep)
    series, hook = None, None
    first = ig_text.splitlines()[0] if ig_text.strip() else ""
    m = re.match(rf"^\s*الحلقة\s+(\S+)\s*[|｜]\s*(.+?)\s*(?={_EMOJI})", first)
    if m:
        series = m.group(2).strip()
        em = first[m.end()]
        hook = f"{first[m.end() + 1:].strip()} {em}".strip()
    tf, df = ep_dir / "title-facebook.txt", ep_dir / "caption-facebook.txt"
    title = display_text(tf.read_text(encoding="utf-8")).strip().splitlines()[0] if tf.is_file() and tf.read_text(encoding="utf-8").strip() else \
        (f"{series} | الحلقة {n_ar}" if series else f"الحلقة {n_ar}")
    if df.is_file() and df.read_text(encoding="utf-8").strip():
        return title, display_text(df.read_text(encoding="utf-8"))
    lines = ig_text.splitlines()
    if hook:
        lines[0] = hook
    out = []
    for ln in lines:
        if ln.strip() == CLOSING and series:
            ln = f"الحلقة {n_ar} من {series}. {CLOSING}"
        elif ln.strip().startswith("#"):
            ln = HASHTAGS["facebook"]
        out.append(ln)
    return title, display_text("\n".join(out))


def reply_text(s: str) -> str:
    """Any reply or comment we post goes through here: no tashkeel (CLAUDE.md)."""
    return display_text(s)


# ---------------------------------------------------------------- upload route
_ROUTE_TEXT = {"resumable": "resumable upload, no public URL needed",
               "video_url-github": "video_url via a temporary GitHub release on OWNER/OWNER.github.io (file above 18 MB; original quality, release deleted after the container is FINISHED)",
               "video_url-env": "video_url from IG_VIDEO_URL (set by hand)"}


def upload_route(nbytes: int, environ=None) -> str:
    """Which way a video of this size goes up: "video_url-env" (IG_VIDEO_URL set by hand), "video_url-github" (temporary release, automatic above
    URL_ABOVE_BYTES) or "resumable". The original file is always the one uploaded; nothing is re-encoded to fit."""
    if (environ if environ is not None else os.environ).get("IG_VIDEO_URL"):
        return "video_url-env"
    return "video_url-github" if nbytes > URL_ABOVE_BYTES else "resumable"


def video_source(video: Path, name: str, environ=None) -> tuple:
    """(route, video_url or None, cleanup). cleanup() is always callable and never raises: a failed delete prints a WARNING (the sweep removes it later)."""
    route = upload_route(video.stat().st_size, environ)
    if route == "video_url-env":
        return route, (environ if environ is not None else os.environ)["IG_VIDEO_URL"], (lambda: None)
    if route == "resumable":
        return route, None, (lambda: None)
    try:
        media_host.sweep()      # stale ig-tmp-* releases of an earlier crashed run
    except SystemExit as e:
        print(f"WARNING stale-release sweep skipped: {e}")
    url, clean = media_host.host(video, name=name)

    def cleanup() -> None:
        try:
            clean()
        except SystemExit as e:
            print(f"WARNING temporary release not removed ({e}); `uv run tools/media_host.py sweep` removes it")
    return route, url, cleanup


def cover_file(w: Path) -> Path | None:
    """The grid poster of an episode as a JPEG (cover.jpg next to episode.mp4; made from cover.png when only the png exists), or None for an episode with no poster (R-501)."""
    jpg, png = w / "cover.jpg", w / "cover.png"
    if jpg.is_file() and (not png.is_file() or jpg.stat().st_mtime >= png.stat().st_mtime):
        return jpg
    if png.is_file():
        from PIL import Image
        Image.open(png).convert("RGB").save(jpg, quality=95)
        return jpg
    return None


def cover_source(w: Path, name: str, environ=None) -> tuple:
    """(cover_url or None, cleanup): the Reel's cover (R-501, the owner 2026-10-28: the profile grid must show the poster, not a black tile) is hosted the same way a large video is
    (a temporary GitHub release, deleted once the container is FINISHED); IG_COVER_URL set by hand wins. A cover that cannot be hosted is a WARNING, never a reason not to post: the
    episode's frame 0 IS the poster, so Instagram's default cover is the same picture. cleanup() never raises."""
    env = environ if environ is not None else os.environ
    if env.get("IG_COVER_URL"):
        return env["IG_COVER_URL"], (lambda: None)
    f = cover_file(w)
    if f is None:
        return None, (lambda: None)
    try:
        url, clean = media_host.host(f, name=f"{name}-cover")
    except SystemExit as e:
        print(f"WARNING cover not hosted ({e}); the Reel goes out with the frame-0 default cover, which is the same poster")
        return None, (lambda: None)

    def cleanup() -> None:
        try:
            clean()
        except SystemExit as e:
            print(f"WARNING temporary cover release not removed ({e}); `uv run tools/media_host.py sweep` removes it")
    return url, cleanup


def create_container(env: dict, media_type: str, route: str, url: str | None, video: Path, extra: dict | None = None) -> str:
    """Make the media container for a Reel or Story: by video_url, or by the resumable upload. Returns the container id."""
    uid = env["IG_USER_ID"]
    if url:
        c = api(env, "POST", f"{uid}/media", {"media_type": media_type, "video_url": url, **(extra or {})})
        return c.get("id") or fail("IG-CONTAINER", "no container id returned")
    c = api(env, "POST", f"{uid}/media", {"media_type": media_type, "upload_type": "resumable", **(extra or {})})
    cid = c.get("id") or fail("IG-CONTAINER", "no container id returned")
    up = f"https://rupload.facebook.com/ig-api-upload/{env.get('IG_API_VERSION') or 'v26.0'}/{cid}"
    api(env, "POST", "", url=up, headers={"Authorization": f"OAuth {env['IG_ACCESS_TOKEN']}", "offset": "0", "file_size": str(video.stat().st_size)}, data=video.read_bytes())
    return cid


# ---------------------------------------------------------------- publish
def cmd_publish(ep: str, go: bool = False, force: bool = False, repo: Path = REPO, env: dict | None = None, sleep=time.sleep) -> dict:
    why = publish_gates(ep, repo)
    if why:
        fail("IG-GATE", "refusing to post " + ep + ": " + "; ".join(why))
    w = wdir(ep, repo)
    if (w / "post.json").is_file() and not force:
        fail("IG-ALREADY", f"{ep} was already posted (work/episodes/{ep}/post.json); --force to post again")
    caption, video = build_caption(ep, repo), w / "episode.mp4"
    if has_tashkeel(caption):
        fail("IG-NO-TASHKEEL", "the post caption still carries tashkeel or tatweel; nothing was posted")
    bad = caption_problems(caption, "instagram")
    if bad:
        fail("IG-CAPTION-BAIT", "the Instagram caption breaks the wording rules (pipelines/AUDIENCE.md): " + "; ".join(bad) + "; nothing was posted")
    plan = {"episode": ep, "video": video.as_posix(), "bytes": video.stat().st_size, "caption": caption, "mode": "DRY RUN"}
    if not go:
        print("DRY RUN (add --go to post). Gates clear. Caption:\n" + caption + f"\nVideo: {plan['video']} ({plan['bytes']} bytes), upload route: {_ROUTE_TEXT[upload_route(plan['bytes'])]}. Cover: {cover_file(w) or 'none (no grid poster in the episode folder)'}.")
        return plan
    env = publish_env(env if env is not None else load_env())
    need(env, "IG_USER_ID", "IG_ACCESS_TOKEN")
    uid = env["IG_USER_ID"]
    quota = api(env, "GET", f"{uid}/content_publishing_limit", {"fields": "quota_usage,config"})
    q = (quota.get("data") or [{}])[0]
    used, total = q.get("quota_usage"), (q.get("config") or {}).get("quota_total")
    if isinstance(used, int) and isinstance(total, int) and used >= total:
        fail("IG-LIMIT", f"publish quota used up ({used}/{total} in 24 h)")
    # Measured 2026-10-26: the resumable upload is refused above about 20 MB, so a large episode goes up by video_url (IG_VIDEO_URL by hand, or
    # automatically a temporary GitHub release). The release is deleted as soon as Meta has the file (container FINISHED) or on any failure.
    route, video_url, cleanup = video_source(video, ep)
    cover_url, cover_cleanup = cover_source(w, ep)
    try:
        cid = create_container(env, "REELS", route, video_url, video, {"caption": caption, **({"cover_url": cover_url} if cover_url else {})})
        status = None
        for _ in range(POLL_MAX):
            status = api(env, "GET", cid, {"fields": "status_code"}).get("status_code")
            if status in ("FINISHED", "ERROR", "EXPIRED"):
                break
            sleep(POLL_EVERY_S)
    finally:
        cleanup()
        cover_cleanup()
    if status != "FINISHED":
        fail("IG-PROCESS", f"container {cid} ended as {status!r}; nothing was published")
    mid = api(env, "POST", f"{uid}/media_publish", {"creation_id": cid}).get("id") or fail("IG-PUBLISH", "no media id returned")
    rec = {"episode": ep, "media_id": mid, "container_id": cid, "permalink": None, "username": env.get("IG_USERNAME"),
           "posted_at": now().isoformat(timespec="seconds"), "instagram_timestamp": None, "caption": caption, "upload": route, "cover": bool(cover_url)}
    try:
        fbr = read_json(w / "facebook.json")
    except ValueError:
        fbr = None
    # Facebook posted first (Instagram failed earlier): keep its copy in this record
    if fbr and fbr.get("video_id"):
        rec["facebook"] = {k: fbr.get(k) for k in ("video_id", "permalink", "posted_at", "state")}
    write_json(w / "post.json", rec)            # the stub is written BEFORE the permalink GET: a failed GET can never lead to a second post
    try:
        try:
            info = api(env, "GET", mid, {"fields": "permalink,timestamp,username,media_product_type"})
        except SystemExit:      # the Facebook-Login host may reject a field it does not know: the permalink alone is enough
            info = api(env, "GET", mid, {"fields": "permalink,timestamp"})
        rec.update(permalink=info.get("permalink"), instagram_timestamp=info.get("timestamp"), username=info.get("username") or rec["username"])
        write_json(w / "post.json", rec)
    except SystemExit as e:
        print(f"WARNING {ep} is published (media {mid}); the permalink could not be read yet ({e}); `ig.py metrics {ep}` fills it in")
    print(f"POSTED {ep}: {rec['permalink']} at {rec['posted_at']}")
    return rec


# ---------------------------------------------------------------- comments
def cmd_comments(ep: str, force: bool = False, repo: Path = REPO, env: dict | None = None, at: datetime | None = None) -> dict:
    w = wdir(ep, repo)
    post = read_json(w / "post.json")
    if post is None:
        fail("IG-NOPOST", f"{ep} has no post.json: nothing posted yet")
    t = datetime.fromisoformat(post["posted_at"])
    due = t + timedelta(hours=HOURS_BEFORE_COMMENTS)
    cur = at or now()
    if cur < due and not force:
        left = (due - cur).total_seconds() / 3600
        fail("IG-TOO-EARLY", f"{left:.1f} h until the {HOURS_BEFORE_COMMENTS} h mark ({due.isoformat(timespec='minutes')}); --force to read now")
    env = env if env is not None else load_env()
    need(env, "IG_ACCESS_TOKEN")
    me = str(env.get("IG_USER_ID") or "")
    top = read_pages(env, f"{post['media_id']}/comments", {"fields": "id,text,timestamp,username,like_count", "limit": "50"}, "from")

    def entry(c, parent):      # the Page token returns username null (no instagram_manage_comments): `from.id` still tells our own account
        d = {"id": c.get("id"), "platform": "instagram", "parent_id": parent, "text": c.get("text", ""), "username": c.get("username"), "timestamp": c.get("timestamp")}
        if me and str((c.get("from") or {}).get("id") or "") == me:
            d["own"] = True
        return d
    out = []
    for c in top:
        out.append(entry(c, None))
        for r in read_pages(env, f"{c['id']}/replies", {"fields": "id,text,timestamp,username", "limit": "50"}, "from"):
            out.append(entry(r, c.get("id")))
    old = read_json(w / "comments.json") or {}      # a Facebook harvest may already be in the file: keep it (platform + id dedupe)
    other = [c for c in old.get("comments", []) if (c.get("platform") or "instagram") != "instagram"]
    seen, merged = set(), []
    for c in out + other:
        key = (c.get("platform"), c.get("id"))
        if c.get("id") is not None and key in seen:
            continue
        seen.add(key)
        merged.append(c)
    own = {u for u in {post.get("username"), env.get("IG_USERNAME")} if u} | (set(old.get("own_usernames") or []) if other else set())
    res = {**({k: v for k, v in old.items() if k.startswith("facebook")} if other else {}),
           "episode": ep, "media_id": post["media_id"], "fetched_at": cur.isoformat(timespec="seconds"), "count": len(merged),
           "own_usernames": sorted(own), "comments": merged}
    blob = json.dumps(res, ensure_ascii=False)
    for k in SECRET_KEYS:
        if env.get(k) and env[k] in blob:
            fail("IG-LEAK", "a credential value appeared in the comments output; not written")
    write_json(w / "comments.json", res)
    print(f"{ep}: {len(out)} Instagram comments and replies -> work/episodes/{ep}/comments.json")
    return res


# ---------------------------------------------------------------- board support: metrics and replies (official API, own account only)
MAX_REPLY_CHARS = 2200   # Instagram comment limit


def cmd_metrics(ep: str, repo: Path = REPO, env: dict | None = None, at: datetime | None = None) -> dict:
    """Like and comment counts of the posted Reel for the board. Needs the token; writes only counts, never credentials."""
    w = wdir(ep, repo)
    post = read_json(w / "post.json")
    if post is None:
        fail("IG-NOPOST", f"{ep} has no post.json: nothing posted yet")
    env = env if env is not None else load_env()
    need(env, "IG_ACCESS_TOKEN")
    r = api(env, "GET", post["media_id"], {"fields": "like_count,comments_count,permalink,timestamp"})
    res = {"episode": ep, "fetched_at": (at or now()).isoformat(timespec="seconds"), "likes": r.get("like_count"), "comments": r.get("comments_count"),
           "permalink": r.get("permalink") or post.get("permalink")}
    if res["permalink"] and not post.get("permalink"):          # a post.json stub from a failed permalink read gets its link here
        post.update(permalink=res["permalink"], instagram_timestamp=post.get("instagram_timestamp") or r.get("timestamp"))
        write_json(w / "post.json", post)
    blob = json.dumps(res, ensure_ascii=False)
    for k in SECRET_KEYS:
        if env.get(k) and env[k] in blob:
            fail("IG-LEAK", "a credential value appeared in the metrics output; not written")
    write_json(w / "metrics.json", res)
    print(f"{ep}: {res['likes']} likes, {res['comments']} comments -> work/episodes/{ep}/metrics.json")
    return res


def cmd_reply(comment_id: str, text: str, go: bool = False, env: dict | None = None) -> dict:
    """Post ONE reply under a comment (POST /{comment-id}/replies). Dry run unless go. No tashkeel (CLAUDE.md); the caller owns the daily limit."""
    text = reply_text(text).strip()
    if not text:
        fail("IG-REPLY-EMPTY", "empty reply")
    if len(text) > MAX_REPLY_CHARS:
        fail("IG-REPLY-LONG", f"reply is {len(text)} characters; the limit is {MAX_REPLY_CHARS}")
    if has_tashkeel(text):
        fail("IG-NO-TASHKEEL", "the reply still carries tashkeel or tatweel; nothing was posted")
    if not re.fullmatch(r"[0-9A-Za-z_]+", comment_id or ""):
        fail("IG-REPLY-ID", "the comment id is not a plain id")
    if not go:
        print(f"DRY RUN (add --go to post). Reply under {comment_id}:\n{text}")
        return {"comment_id": comment_id, "text": text, "mode": "DRY RUN"}
    env = env if env is not None else load_env()
    need(env, "IG_ACCESS_TOKEN")
    env = publish_env(env)      # comment ids read with the Page token (media of the Facebook-login route) are answered on the same host and token
    r = api(env, "POST", f"{comment_id}/replies", {"message": text})
    rid = r.get("id") or fail("IG-REPLY", "no reply id returned")
    print(f"REPLIED under {comment_id}: {rid}")
    return {"comment_id": comment_id, "reply_id": rid, "text": text, "mode": "POSTED"}


# ---------------------------------------------------------------- token
def cmd_refresh(env: dict | None = None, path: Path | None = None, at: datetime | None = None) -> dict:
    p = Path(path or CONF)
    env = env if env is not None else load_env(p)
    need(env, "IG_ACCESS_TOKEN")
    issued = env.get("IG_TOKEN_ISSUED")
    cur = at or now()
    if issued and cur - datetime.fromisoformat(issued) < timedelta(hours=24):
        fail("IG-REFRESH-EARLY", "the token is under 24 h old; Meta refuses to refresh it yet")
    host = env.get("IG_API_HOST") or "graph.instagram.com"
    r = api(env, "GET", "", url=f"https://{host}/refresh_access_token?" + urllib.parse.urlencode({"grant_type": "ig_refresh_token", "access_token": env["IG_ACCESS_TOKEN"]}))
    new = r.get("access_token")
    if not new:
        fail("IG-REFRESH", "no access_token in the refresh answer")
    lines = [l for l in (p.read_text(encoding="utf-8").splitlines() if p.is_file() else []) if not l.startswith(("IG_ACCESS_TOKEN=", "IG_TOKEN_ISSUED="))]
    lines += [f"IG_ACCESS_TOKEN={new}", f"IG_TOKEN_ISSUED={cur.isoformat(timespec='seconds')}"]
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, p)
    days = round(int(r.get("expires_in", 0)) / 86400, 1)
    print(f"token refreshed, valid about {days} days")
    return {"expires_in_days": days}


def token_state(env: dict, at: datetime | None = None) -> str:
    if not env.get("IG_ACCESS_TOKEN"):
        return "no token"
    iss = env.get("IG_TOKEN_ISSUED")
    if not iss:
        return "token present (issue date unknown: run `refresh` once to start the 60-day clock)"
    left = 60 - ((at or now()) - datetime.fromisoformat(iss)).total_seconds() / 86400
    return f"token present, about {left:.0f} days left" + ("; REFRESH NOW" if left < 10 else "")


# ---------------------------------------------------------------- status / plan
def cmd_status(live: bool = False, repo: Path = REPO, env: dict | None = None) -> str:
    env = env if env is not None else load_env()
    out = [f"credentials file: {'found' if CONF.is_file() else 'MISSING'} ({CONF})", f"IG_USER_ID: {'set' if env.get('IG_USER_ID') else 'missing'}",
           token_state(env)]
    wd = repo / "work" / "episodes"
    for d in sorted(wd.glob("*")) if wd.is_dir() else []:
        post = read_json(d / "post.json")
        if post:
            due = datetime.fromisoformat(post["posted_at"]) + timedelta(hours=HOURS_BEFORE_COMMENTS)
            out.append(f"{d.name}: posted {post['posted_at']}, comments due {due.isoformat(timespec='minutes')}, "
                       f"comments.json {'yes' if (d / 'comments.json').is_file() else 'no'}, decision.json {'yes' if (d / 'decision.json').is_file() else 'no'}")
        else:
            why = publish_gates(d.name, repo) if (d / "gate").exists() or (d / "episode.mp4").exists() else ["not composed yet"]
            out.append(f"{d.name}: not posted; " + ("ready to post" if not why else "blocked: " + "; ".join(why)))
    if live:
        need(env, "IG_USER_ID", "IG_ACCESS_TOKEN")
        q = (api(env, "GET", f"{env['IG_USER_ID']}/content_publishing_limit", {"fields": "quota_usage,config"}).get("data") or [{}])[0]
        out.append(f"publish quota: {q.get('quota_usage')} of {(q.get('config') or {}).get('quota_total')} in 24 h")
    s = "\n".join(out)
    print(s)
    return s


def cmd_plan(ep: str, repo: Path = REPO) -> str:
    post = read_json(wdir(ep, repo) / "post.json")
    if not post:
        fail("IG-NOPOST", f"{ep} not posted yet: the plan needs the post time")
    posted = datetime.fromisoformat(post["posted_at"]).astimezone()
    due = datetime.combine(posted.date() + timedelta(days=1), dtime(14, 0))      # the owner 2026-10-27: harvest at 14:00 Amman the day after the post (loop_gate.harvest_due_at)
    cmd = (f'schtasks /Create /TN "StoryWrap-Votes-{ep}" /SC ONCE /SD {due:%d/%m/%Y} /ST {due:%H:%M} /F '
           f'/TR "cmd /c cd /d {repo} && set PYTHONUTF8=1 && uv run tools/fb.py harvest {ep} & if errorlevel 4 exit /b 1 & if not errorlevel 3 if errorlevel 1 exit /b 1 & uv run tools/vote.py tally {ep} && uv run tools/vote.py next {ep}"')   # exit 3 = only the Facebook half failed: the Instagram vote still counts
    print("NOT REGISTERED. Register only after the owner's token works (pipelines/AUDIENCE.md, Scheduling plan):\n" + cmd)
    return cmd


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Instagram Graph API for Story-Wrap")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("publish"); p.add_argument("ep"); p.add_argument("--go", action="store_true"); p.add_argument("--force", action="store_true")
    p = sub.add_parser("comments"); p.add_argument("ep"); p.add_argument("--force", action="store_true")
    p = sub.add_parser("status"); p.add_argument("--live", action="store_true")
    sub.add_parser("refresh")
    p = sub.add_parser("plan"); p.add_argument("ep")
    p = sub.add_parser("metrics"); p.add_argument("ep")
    p = sub.add_parser("reply"); p.add_argument("comment_id"); p.add_argument("text"); p.add_argument("--go", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "publish":
        cmd_publish(a.ep, a.go, a.force)
    elif a.cmd == "comments":
        cmd_comments(a.ep, a.force)
    elif a.cmd == "status":
        cmd_status(a.live)
    elif a.cmd == "refresh":
        cmd_refresh()
    elif a.cmd == "metrics":
        cmd_metrics(a.ep)
    elif a.cmd == "reply":
        cmd_reply(a.comment_id, a.text, a.go)
    else:
        cmd_plan(a.ep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
