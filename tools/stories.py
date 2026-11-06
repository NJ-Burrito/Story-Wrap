# /// script
# requires-python = ">=3.10"
# dependencies = ["playwright"]
# ///
"""Instagram and Facebook Page stories for Story-Wrap, through the official APIs only (owner, 2026-10-25: "manage highlights and stories").

    uv run tools/stories.py announce <ep> [--go] [--force]     after the Reel is live: ONE story per platform, «الحلقة N الآن على الصفحة» over the cover or a teaser clip
    uv run tools/stories.py vote     <ep> [--go] [--force]     the next morning: ONE story per platform with the result of <ep>'s vote (from decision.json)
    uv run tools/stories.py vote-due [--go]                    every decided episode whose result story is not posted yet (the Harvest task calls this)
    uv run tools/stories.py status                             what is on record, per episode
Dry run without --go: no network, no credentials, nothing rendered (the text and the plan are printed).

The APIs take image or video only: no stickers, polls or links (CLAUDE.md "Stories and highlights"). Highlights have no API and are never touched here.
Every story is rendered as a short VIDEO (1080x1920, H.264/AAC, 3 to 60 s, NVENC), so Instagram's resumable upload (rupload, the path ig.py uses for Reels)
needs no public URL and the Facebook Page uses its video_stories phases (start, upload to rupload.facebook.com, finish with is_ai_generated).
  Instagram: POST /{ig-user}/media  media_type=STORIES upload_type=resumable -> rupload -> status_code FINISHED -> POST /{ig-user}/media_publish
             (https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/content-publishing, read 2026-10-25)
  Facebook:  POST /{page}/video_stories upload_phase=start -> upload_url (rupload.facebook.com) -> upload_phase=finish [is_ai_generated]  (https://developers.facebook.com/docs/page-stories-api/)
Rules: the same gates as the Reel (`ig.publish_gates`), a story only after that platform's Reel is on record and live, wording rules (`ig.caption_problems`, no tashkeel),
one record `work/episodes/<ep>/stories.json` with a PENDING state written before the call that makes the story public (no double story), one platform failing never
blocks or undoes the other, tokens redacted. Standard library only apart from playwright (card rendering, imported when a card is drawn).
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fb   # noqa: E402
import ig   # noqa: E402
from ig import fail, need, now, read_json, redact, wdir, write_json   # noqa: E402
from arabic_display import display_text, has_tashkeel   # noqa: E402

REPO = ig.REPO
PLATFORMS = ("instagram", "facebook")
W, H, FPS = 1080, 1920, 30
CARD_S = 6                    # seconds a still card stays up
TEASER_S = 25                 # seconds cut from the episode for the announce story (<= 60: both platforms' story limit)
STORY_MAX_S = 60
VOTE_WINDOW_H = 30            # a result story is posted within this many hours of the decision ("the next morning"); an older decision is left alone
ANNOUNCE_WITHIN_H = 3         # an "announce" story is skipped when the Reel went live longer ago than this
CLAIMING = "claiming"
PENDING = "publishing"
POLL_MAX = 10
FONTS = Path(os.environ.get("SW_FONTS") or REPO / "assets" / "fonts")


# ---------------------------------------------------------------- the text people see
def announce_line(ep: str) -> str:
    return display_text(f"الحلقة {ig.episode_number_ar(ep)} الآن على الصفحة")


def result_choice(dec: dict) -> tuple:
    """(choice dict, how) for the vote result: the audience winner, else the showrunner's pick. (None, None) when nothing is decided yet."""
    ch = {c.get("id"): c for c in dec.get("choices") or []}
    if dec.get("winner") in ch:
        return ch[dec["winner"]], "audience"
    pick = dec.get("showrunner_pick") or {}
    if pick.get("id") in ch:
        return ch[pick["id"]], "showrunner"
    return None, None


def vote_lines(ep: str, dec: dict) -> list:
    """The result card text: «نتيجة الحلقة N», the winning choice as a short phrase, and the count (audience) or the writer's reason (tie or near-empty vote)."""
    c, how = result_choice(dec)
    if c is None:
        return []
    lines = [f"نتيجة الحلقة {ig.episode_number_ar(ep)}", ig.typed_phrase(c["text_ar"])]
    if how == "audience":
        n = (dec.get("counts") or {}).get(c["id"])
        lines.append(f"اخترتم هذا الطريق ({n} صوت)" if isinstance(n, int) else "اخترتم هذا الطريق")
    else:
        reason = ((dec.get("showrunner_pick") or {}).get("reason_ar") or "").strip()
        lines.append(reason or "الحلقة القادمة تتبع هذا الطريق")
    return [display_text(x) for x in lines]


def text_problems(lines: list) -> list:
    t = "\n".join(lines)
    bad = ig.caption_problems(t, "instagram")
    if has_tashkeel(t):
        bad.append("tashkeel or tatweel")
    if "#" in t:
        bad.append("a hashtag on a story card")
    return bad


# ---------------------------------------------------------------- the record
def rec_path(ep: str, repo: Path = REPO) -> Path:
    return wdir(ep, repo) / "stories.json"


def load_record(ep: str, repo: Path = REPO) -> dict:
    p = rec_path(ep, repo)
    if not p.is_file():
        return {"episode": ep, "items": {}}
    try:
        r = json.loads(p.read_text(encoding="utf-8"))
        return r if isinstance(r, dict) and isinstance(r.get("items"), dict) else {"episode": ep, "items": {}, "corrupt": True}
    except (ValueError, OSError):
        return {"episode": ep, "items": {}, "corrupt": True}


def item_key(kind: str, platform: str) -> str:
    return f"{kind}:{platform}"


def save_item(ep: str, key: str, item: dict, repo: Path = REPO) -> None:
    rec = load_record(ep, repo)
    rec["items"][key] = item
    rec["episode"] = ep
    write_json(rec_path(ep, repo), rec)


def lock_path(ep: str, key: str, repo: Path = REPO) -> Path:
    return story_dir(ep, repo) / ("claim-" + key.replace(":", "-") + ".lock")


def on_record(ep: str, key: str, repo: Path = REPO) -> bool:
    """Any entry counts, a claimed, pending or failed one included: a retry of a story that may be live needs --force."""
    rec = load_record(ep, repo)
    return bool(rec.get("corrupt")) or key in rec["items"] or lock_path(ep, key, repo).exists()


def claim(ep: str, kind: str, platform: str, repo: Path = REPO, force: bool = False) -> bool:
    """Take the story BEFORE anything is rendered or sent. The lock file is created with O_EXCL, so of two overlapping runs only one gets it; the other reports
    'already'. The claim is also written to stories.json as state "claiming". A crash leaves both in place: the next run needs --force. A failure that is known to
    have happened before anything became public calls release()."""
    key = item_key(kind, platform)
    lp = lock_path(ep, key, repo)
    lp.parent.mkdir(parents=True, exist_ok=True)
    if force:
        lp.unlink(missing_ok=True)
    try:
        fd = os.open(str(lp), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(now().isoformat(timespec="seconds") + "\n")
    save_item(ep, key, {"kind": kind, "platform": platform, "state": CLAIMING, "at": now().isoformat(timespec="seconds")}, repo)
    return True


def release(ep: str, kind: str, platform: str, repo: Path = REPO) -> None:
    """Give a claim back after a failure that happened before the story could be public (nothing was sent that publishes it)."""
    key = item_key(kind, platform)
    rec = load_record(ep, repo)
    if (rec["items"].get(key) or {}).get("state") == CLAIMING:
        rec["items"].pop(key)
        write_json(rec_path(ep, repo), rec)
    lock_path(ep, key, repo).unlink(missing_ok=True)


# ---------------------------------------------------------------- is the Reel live on that platform?
def reel_live(ep: str, platform: str, repo: Path = REPO, at: datetime | None = None) -> tuple:
    """(ok, why). Instagram: post.json with a media id. Facebook: facebook.json with a video id whose go-live time (scheduled or posted) has passed."""
    w, cur = wdir(ep, repo), at or now()
    if platform == "instagram":
        p = read_json(w / "post.json")
        return (True, "") if isinstance(p, dict) and p.get("media_id") else (False, "the Reel is not on Instagram yet")
    r = fb.load_record(ep, repo)
    if not r or r.get("corrupt") or not r.get("video_id"):
        return False, "the Reel is not on the Facebook Page yet"
    t = fb.go_live_at(r)
    if t is None:
        return False, "the Facebook record has no usable time"
    if t.tzinfo is None:
        t = t.astimezone()
    if t > cur:
        return False, f"the Facebook Reel is scheduled for {t.isoformat(timespec='minutes')}"
    if str(r.get("state", "")).startswith(("not-ready", "finish-refused")):
        return False, f"the Facebook Reel is {r.get('state')!r}"
    return True, ""


def live_since(ep: str, platform: str, repo: Path = REPO):
    """When the Reel went (or goes) live on that platform, or None."""
    w = wdir(ep, repo)
    try:
        if platform == "instagram":
            p = read_json(w / "post.json")
            return datetime.fromisoformat(p["posted_at"]) if isinstance(p, dict) and p.get("posted_at") else None
        return fb.go_live_at(fb.load_record(ep, repo))
    except (ValueError, TypeError, KeyError):
        return None


def too_late(ep: str, platform: str, repo: Path, cur: datetime):
    """For an 'announce' story: a message when the Reel went live more than ANNOUNCE_WITHIN_H hours ago (a story that says «الآن» a day late is wrong), else None."""
    t = live_since(ep, platform, repo)
    if t is None:
        return None
    t = t if t.tzinfo else t.astimezone()
    age = (cur - t).total_seconds() / 3600
    return f"skipped: the Reel went live {age:.1f} h ago (an announce story is only posted within {ANNOUNCE_WITHIN_H} h)" if age > ANNOUNCE_WITHIN_H else None


# ---------------------------------------------------------------- cards and video (replaced in tests)
def card_html(kind: str, lines: list) -> str:
    fam = []
    for f, wt, n in (("thmanyahsans", 900, "Black"), ("thmanyahsans", 700, "Bold"), ("thmanyahserifdisplay", 900, "Black")):
        fam.append(f'@font-face{{font-family:"{f}";src:url("{(FONTS / f"{f}-{n}.woff2").as_uri()}") format("woff2");font-weight:{wt}}}')
    esc = lambda t: t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")   # noqa: E731
    if kind == "announce":      # transparent overlay: one plate low in the frame, over the cover or the teaser
        body = f'<div id="p">{esc(lines[0])}</div>'
        css = ("html,body{margin:0;background:transparent}#p{position:absolute;left:90px;right:90px;bottom:300px;padding:44px 36px;text-align:center;color:#fff;"
               "background:rgba(10,10,10,.78);font:900 84px/1.35 thmanyahsans;border-radius:12px}")
    else:                       # vote result: an opaque ink-on-paper card
        body = f'<div id="a">{esc(lines[0])}</div><div id="b">{esc(lines[1])}</div><div id="c">{esc(lines[2])}</div>'
        css = ("html,body{margin:0;width:1080px;height:1920px;background:#f2ede3;color:#111}body{display:flex;flex-direction:column;justify-content:center;align-items:center;gap:56px;"
               "text-align:center;padding:0 90px;box-sizing:border-box}#a{font:700 64px/1.3 thmanyahsans}#b{font:900 112px/1.3 thmanyahserifdisplay}#c{font:700 52px/1.4 thmanyahsans;opacity:.75}")
    return f'<!doctype html><html lang="ar" dir="rtl"><meta charset="utf-8"><style>{"".join(fam)}{css}</style><body>{body}</body></html>'


def _render(kind: str, lines: list, out_png: Path) -> Path:
    """Draw the card with Chromium (Thmanyah, real Arabic shaping). announce = transparent PNG overlay; vote = opaque 1080x1920 PNG."""
    from playwright.sync_api import sync_playwright
    for f in ("thmanyahsans-Black.woff2", "thmanyahsans-Bold.woff2", "thmanyahserifdisplay-Black.woff2"):
        if not (FONTS / f).is_file():
            fail("ST-FONTS", f"Thmanyah font {f} missing in {FONTS}: a story card is never drawn with a fallback face")
    out_png.parent.mkdir(parents=True, exist_ok=True)
    page = out_png.with_suffix(".html")
    page.write_text(card_html(kind, lines), encoding="utf-8")
    with sync_playwright() as pw:
        b = pw.chromium.launch(args=["--enable-gpu-rasterization", "--ignore-gpu-blocklist", "--allow-file-access-from-files"])
        try:
            pg = b.new_page(viewport={"width": W, "height": H})
            pg.goto(page.as_uri())
            pg.evaluate("Promise.all(['900 40px thmanyahsans','700 40px thmanyahsans','900 40px thmanyahserifdisplay'].map(s => document.fonts.load(s, 'هدى'))).then(() => 1)")
            if not pg.evaluate("document.fonts.check('900 40px thmanyahsans') && document.fonts.check('700 40px thmanyahsans')"):
                fail("ST-FONTS", "Thmanyah did not load in the card page")
            pg.screenshot(path=str(out_png), omit_background=(kind == "announce"))
        finally:
            b.close()
    return out_png


def _ffmpeg(args: list) -> None:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-y", "-threads", "2", *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
    if r.returncode != 0:
        tail = (r.stderr or "").strip().splitlines()
        fail("ST-FFMPEG", "ffmpeg failed: " + (tail[-1][:200] if tail else f"exit {r.returncode}"))


def _venc() -> list:
    if os.environ.get("NJ_COMPOSE_CPU"):
        return ["-c:v", "libx264", "-preset", "medium", "-crf", "20"]
    return ["-c:v", "h264_nvenc", "-preset", "p5", "-tune", "hq", "-rc", "vbr", "-cq", "21", "-b:v", "0", "-maxrate", "8M"]


def _aenc() -> list:
    return ["-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "128k"]


OUT_FLAGS = ["-r", str(FPS), "-pix_fmt", "yuv420p", "-g", str(FPS * 2), "-movflags", "+faststart"]


def story_dir(ep: str, repo: Path = REPO) -> Path:
    return wdir(ep, repo) / "story"


def build_announce(ep: str, repo: Path = REPO) -> Path:
    """announce.mp4: the line over work/episodes/<ep>/cover.png (CARD_S seconds, silent) when a cover exists, else over the first TEASER_S seconds of the episode (with its sound)."""
    d = story_dir(ep, repo)
    d.mkdir(parents=True, exist_ok=True)
    overlay = _render("announce", [announce_line(ep)], d / "announce-line.png")
    out, cover, video = d / "announce.mp4", wdir(ep, repo) / "cover.png", wdir(ep, repo) / "episode.mp4"
    fit = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1"
    if cover.is_file():
        _ffmpeg(["-loop", "1", "-t", str(CARD_S), "-i", str(cover), "-i", str(overlay), "-f", "lavfi", "-t", str(CARD_S), "-i", "anullsrc=r=48000:cl=stereo",
                 "-filter_complex", f"[0:v]{fit}[b];[b][1:v]overlay=0:0:format=auto,format=yuv420p[v]", "-map", "[v]", "-map", "2:a", "-shortest", *_venc(), *_aenc(), *OUT_FLAGS, str(out)])
    else:
        _ffmpeg(["-t", str(TEASER_S), "-i", str(video), "-i", str(overlay), "-filter_complex", f"[0:v]{fit}[b];[b][1:v]overlay=0:0:format=auto,format=yuv420p[v]",
                 "-map", "[v]", "-map", "0:a?", "-t", str(TEASER_S), *_venc(), *_aenc(), *OUT_FLAGS, str(out)])
    return out


def build_vote(ep: str, lines: list, repo: Path = REPO) -> Path:
    d = story_dir(ep, repo)
    d.mkdir(parents=True, exist_ok=True)
    card = _render("vote", lines, d / "vote.png")
    out = d / "vote.mp4"
    _ffmpeg(["-loop", "1", "-t", str(CARD_S), "-i", str(card), "-f", "lavfi", "-t", str(CARD_S), "-i", "anullsrc=r=48000:cl=stereo", "-map", "0:v", "-map", "1:a", "-shortest",
             "-vf", f"scale={W}:{H},format=yuv420p", *_venc(), *_aenc(), *OUT_FLAGS, str(out)])
    return out


def check_video(p: Path) -> None:
    if not p.is_file() or p.stat().st_size == 0:
        fail("ST-VIDEO", f"{p.name} was not written")


# ---------------------------------------------------------------- per-platform publish
def post_instagram(env: dict, video: Path, sleep=time.sleep) -> dict:
    env = ig.publish_env(env)
    need(env, "IG_USER_ID", "IG_ACCESS_TOKEN")
    route, video_url, cleanup = ig.video_source(video, "story-" + video.parent.name)
    try:
        cid = ig.create_container(env, "STORIES", route, video_url, video)
        status = None
        for _ in range(ig.POLL_MAX):
            status = ig.api(env, "GET", cid, {"fields": "status_code"}).get("status_code")
            if status in ("FINISHED", "ERROR", "EXPIRED"):
                break
            sleep(ig.POLL_EVERY_S)
    finally:
        cleanup()
    if status != "FINISHED":
        fail("ST-IG-PROCESS", f"story container {cid} ended as {status!r}; nothing was published")
    return {"container_id": cid, "upload": route}


def publish_instagram(env: dict, cid: str) -> str:
    env = ig.publish_env(env)
    return ig.api(env, "POST", f"{env['IG_USER_ID']}/media_publish", {"creation_id": cid}).get("id") or fail("ST-IG-PUBLISH", "no story id returned")


def post_facebook_start(env: dict, video: Path) -> dict:
    need(env, "FB_PAGE_ID", "FB_PAGE_TOKEN")
    pid = env["FB_PAGE_ID"]
    s = fb.api(env, "POST", f"{pid}/video_stories", {"upload_phase": "start"})
    vid, url = s.get("video_id"), s.get("upload_url")
    if not vid or not url:
        fail("ST-FB-START", "no video_id / upload_url returned by the start phase; nothing was published")
    if not fb.upload_host_ok(url):
        fail("ST-FB-START", "upload_url is not an https *.facebook.com address; the Page token was not sent")
    fb.api(env, "POST", "", url=url, headers={"Authorization": f"OAuth {env['FB_PAGE_TOKEN']}", "offset": "0", "file_size": str(video.stat().st_size)}, data=video.read_bytes())
    return {"video_id": vid}


def finish_facebook(env: dict, vid: str, sleep=time.sleep) -> dict:
    r = fb.api(env, "POST", f"{env['FB_PAGE_ID']}/video_stories", {"upload_phase": "finish", "video_id": vid, "is_ai_generated": "true"})
    if r.get("success") is False:
        fail("ST-FB-FINISH", f"video {vid}: the finish phase did not succeed")
    return {"post_id": r.get("post_id")}


def story_one(ep: str, kind: str, platform: str, video: Path, go: bool, force: bool, repo: Path, env: dict, sleep) -> dict:
    """One story on one platform. Writes the PENDING record before the call that makes it public."""
    key = item_key(kind, platform)
    base = {"kind": kind, "platform": platform, "video": video.name, "bytes": video.stat().st_size}
    if platform == "instagram":
        part = post_instagram(env, video, sleep)
        save_item(ep, key, {**base, **part, "state": PENDING, "at": now().isoformat(timespec="seconds")}, repo)      # BEFORE media_publish
        try:
            sid = publish_instagram(env, part["container_id"])
        except SystemExit as e:
            fail("ST-IG-PUBLISH-UNKNOWN", f"{e}; recorded as {PENDING!r}, the story may be live: check the account before any --force")
        item = {**base, **part, "story_id": sid, "state": "published", "at": now().isoformat(timespec="seconds")}
    else:
        part = post_facebook_start(env, video)
        save_item(ep, key, {**base, **part, "state": PENDING, "at": now().isoformat(timespec="seconds")}, repo)      # BEFORE the finish phase
        try:
            fin = finish_facebook(env, part["video_id"], sleep)
        except SystemExit as e:
            fail("ST-FB-FINISH-UNKNOWN", f"{e}; recorded as {PENDING!r}, the story may be live: check the Page before any --force")
        item = {**base, **part, **fin, "state": "published", "at": now().isoformat(timespec="seconds")}
    save_item(ep, key, item, repo)
    return item


def run_kind(ep: str, kind: str, lines: list, build, go: bool = False, force: bool = False, repo: Path = REPO, env: dict | None = None, sleep=time.sleep,
             platforms=PLATFORMS, at: datetime | None = None) -> dict:
    """Both platforms, independently. Returns {platform: 'posted' | 'already' | 'waits: why' | 'dry' | 'error: msg' | 'no credentials'}. Never raises for one platform."""
    bad = text_problems(lines)
    if bad:
        fail("ST-TEXT", f"the {kind} story text breaks the wording rules (pipelines/AUDIENCE.md): " + "; ".join(bad) + "; nothing was posted")
    res, todo = {}, []
    for p in platforms:
        ok, why = reel_live(ep, p, repo, at)
        if on_record(ep, item_key(kind, p), repo) and not force:
            res[p] = "already"
        elif not ok:
            res[p] = "waits: " + why
        elif kind == "announce" and too_late(ep, p, repo, at or now()):
            res[p] = too_late(ep, p, repo, at or now())
        else:
            todo.append(p)
    if not go:
        for p in todo:
            res[p] = "dry"
        print(f"DRY RUN (add --go). {kind} story for {ep}, text: " + " / ".join(lines) + "\n" + "\n".join(f"  {p}: {r}" for p, r in res.items()))
        return res
    if not todo:
        return res
    env = env if env is not None else ig.load_env()
    have = {"instagram": bool(env.get("IG_USER_ID") and env.get("IG_ACCESS_TOKEN")), "facebook": fb.has_creds(env)}
    for p in [p for p in todo if not have[p]]:
        res[p] = "no credentials"
    todo = [p for p in todo if have[p]]
    if not todo:
        return res
    why = ig.publish_gates(ep, repo) if kind == "announce" else []
    if why:
        fail("ST-GATE", "refusing to post a story for " + ep + ": " + "; ".join(why))
    mine = [p for p in todo if claim(ep, kind, p, repo, force)]          # BEFORE build(): two overlapping runs cannot both publish
    for p in todo:
        if p not in mine:
            res[p] = "already"
    try:
        video = build() if mine else None
        if video is not None:
            check_video(video)
    except SystemExit:
        for p in mine:
            release(ep, kind, p, repo)
        raise
    for p in mine:
        try:
            story_one(ep, kind, p, video, go, force, repo, env, sleep)
            res[p] = "posted"
        except SystemExit as e:
            res[p] = "error: " + redact(str(e), env)[:300]
            if (load_record(ep, repo)["items"].get(item_key(kind, p)) or {}).get("state") == CLAIMING:
                release(ep, kind, p, repo)           # failed before the story could be public: the next run retries
    blob = json.dumps(load_record(ep, repo), ensure_ascii=False)
    for k in ig.SECRET_KEYS:
        if env.get(k) and env[k] in blob:
            fail("ST-LEAK", "a credential value appeared in stories.json")
    for p, r in res.items():
        print(f"{ep} {kind} story {p}: {r}")
    return res


# ---------------------------------------------------------------- commands
def cmd_announce(ep: str, go: bool = False, force: bool = False, repo: Path = REPO, env: dict | None = None, sleep=time.sleep, at: datetime | None = None) -> dict:
    why = ig.publish_gates(ep, repo)
    if why:
        fail("ST-GATE", "refusing to post a story for " + ep + ": " + "; ".join(why))
    return run_kind(ep, "announce", [announce_line(ep)], lambda: build_announce(ep, repo), go, force, repo, env, sleep, at=at)


def cmd_vote(ep: str, go: bool = False, force: bool = False, repo: Path = REPO, env: dict | None = None, sleep=time.sleep, at: datetime | None = None) -> dict:
    dec = read_json(wdir(ep, repo) / "decision.json")
    if not isinstance(dec, dict):
        fail("ST-NODECISION", f"{ep} has no decision.json: the result story follows a counted vote")
    lines = vote_lines(ep, dec)
    if not lines:
        fail("ST-UNDECIDED", f"{ep}: the vote has no winner and no showrunner pick yet; no result story")
    return run_kind(ep, "vote", lines, lambda: build_vote(ep, lines, repo), go, force, repo, env, sleep, at=at)


def vote_due(repo: Path = REPO, go: bool = False, env: dict | None = None, at: datetime | None = None, sleep=time.sleep) -> dict:
    """Every episode with a fresh decision (written within VOTE_WINDOW_H) and a result that exists, whose result story is not on record. Errors are reported, not raised."""
    cur = at or now()
    out = {}
    wd = repo / "work" / "episodes"
    for d in sorted(wd.glob("*")) if wd.is_dir() else []:
        dp = d / "decision.json"
        if not dp.is_file() or all(on_record(d.name, item_key("vote", p), repo) for p in PLATFORMS):
            continue
        age = (cur.timestamp() - dp.stat().st_mtime) / 3600
        if age > VOTE_WINDOW_H:
            out[d.name] = f"skipped: the decision is {age:.0f} h old (window {VOTE_WINDOW_H} h)"
            continue
        try:
            out[d.name] = cmd_vote(d.name, go=go, repo=repo, env=env, sleep=sleep, at=cur)
        except SystemExit as e:
            out[d.name] = "error: " + str(e)[:200]
    return out


def cmd_status(repo: Path = REPO) -> str:
    out = []
    wd = repo / "work" / "episodes"
    for d in sorted(wd.glob("*")) if wd.is_dir() else []:
        items = load_record(d.name, repo)["items"]
        out.append(f"{d.name}: " + (", ".join(f"{k} {v.get('state')}" for k, v in sorted(items.items())) or "no stories"))
    s = "\n".join(out) or "no episodes"
    print(s)
    return s


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Instagram and Facebook Page stories for Story-Wrap")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for n in ("announce", "vote"):
        p = sub.add_parser(n); p.add_argument("ep"); p.add_argument("--go", action="store_true"); p.add_argument("--force", action="store_true")
    p = sub.add_parser("vote-due"); p.add_argument("--go", action="store_true")
    sub.add_parser("status")
    a = ap.parse_args(argv)
    if a.cmd == "announce":
        res = cmd_announce(a.ep, a.go, a.force)
    elif a.cmd == "vote":
        res = cmd_vote(a.ep, a.go, a.force)
    elif a.cmd == "vote-due":
        res = vote_due(go=a.go)
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return 0
    else:
        cmd_status()
        return 0
    return 1 if any(str(v).startswith("error") for v in res.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
