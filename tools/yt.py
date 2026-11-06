# /// script
# requires-python = ">=3.10"
# dependencies = ["google-api-python-client", "google-auth"]
# ///
"""YouTube uploader and comment reader for Story-Wrap (official YouTube Data API v3, our own Google Cloud project `story-publisher`).

    uv run tools/yt.py publish  <ep> [--go] [--force]   resumable upload of the episode; dry run without --go (no network, no credentials)
    uv run tools/yt.py playlist <ep> [--go]             add the uploaded video to the playlist «the series» (publish does this too; this retries it)
    uv run tools/yt.py comments <ep> [--force]          commentThreads -> merged into work/episodes/<ep>/comments.json as platform=youtube (IDEAS ONLY, never votes)
    uv run tools/yt.py status   [--live]                token state, per-episode state; --live also asks channels.list(mine)
    uv run tools/yt.py prune    [--go]                  delete YouTube comment rows (and their idea copies) older than 30 days (the Harvest task does this)
    uv run tools/yt.py forget   [--go] [--records]      delete ALL stored YouTube data at once (a deletion request); --records also the upload records

Same shape and same gates as ig.py and fb.py (`ig.publish_gates`, `ig.caption_problems`, tashkeel check). Rules (CLAUDE.md "Platforms", DESIGN 4.1):
  * YouTube never goes live before Instagram: no `post.json`, no upload (--go).
  * A pending record (`youtube.json`, state "uploading") is written BEFORE the first byte leaves; any later run needs --force (YouTube treats a deleted and
    re-posted Short as a spam risk, research/algo/tiktok-youtube-top5.md B.2).
  * Votes are read from Instagram only; YouTube comments are ideas, tagged platform=youtube.
Credentials: ~/.config/story-wrap/youtube-token.json (authorized-user JSON with a refresh token; override SW_YT_TOKEN). Refreshed when needed and saved back.
Nothing from that file is ever printed, logged, written to a record, the repo or the board (`redact`).

Scopes on the token today: youtube.upload + youtube.readonly. Uploading and reading comments work with those. Creating a playlist and adding to it
(playlists.insert, playlistItems.insert) need the broader `https://www.googleapis.com/auth/youtube` scope: without it the upload still succeeds, the
playlist step is recorded as `playlist_error` and `status` says what to authorise once.

The google libraries are imported only when a call is made (dry runs, tests and the gates need none).
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ig   # noqa: E402
from ig import fail, now, read_json, write_json, wdir   # noqa: E402
from arabic_display import display_text, has_tashkeel   # noqa: E402
import seo   # noqa: E402

REPO = ig.REPO
TOKEN_FILE = Path(os.environ.get("SW_YT_TOKEN") or Path.home() / ".config" / "story-wrap" / "youtube-token.json")
CHANNEL_ID = os.environ.get("SW_YT_CHANNEL_ID") or "YOUR_CHANNEL_ID"      # see config/story-wrap.example.env
PLAYLIST_TITLE = os.environ.get("SW_YT_PLAYLIST_TITLE") or "Story-Wrap series"
SERIES = os.environ.get("SW_SERIES_NAME") or "Story-Wrap series"
CATEGORY_ID = "1"              # Film & Animation
LANGUAGE = "ar"
TITLE_MAX = 100                # YouTube: up to 100 characters
DESC_MAX = 5000
SHORTS_MAX_S = 180             # a vertical video up to 3 minutes is a Short (OFFICIAL, support.google.com/youtube/answer/15424877)
CHUNK = 8 * 1024 * 1024
RETRIES = 5
SECRET_FIELDS = ("token", "refresh_token", "client_secret", "id_token")
SCOPE_PLAYLIST = "https://www.googleapis.com/auth/youtube"
PENDING = "uploading"
AUDIT_FLAG = "yt_audit_passed"
HASHTAGS = tuple(seo.hashtag_list("youtube"))        # data/seo/keywords.json; YouTube shows up to three; a Short gets #Shorts as the third instead of #حكايات


class YtError(SystemExit):
    pass


# ---------------------------------------------------------------- credentials (never printed)
def load_token(path: Path | None = None) -> dict:
    p = Path(path or TOKEN_FILE)
    try:
        d = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    except (ValueError, OSError):
        d = {}
    return d if isinstance(d, dict) else {}


def secrets_of(tok: dict) -> list:
    return [str(tok[k]) for k in SECRET_FIELDS if tok.get(k)]


def redact(text, tok: dict | None = None) -> str:
    """Remove every credential value (and any access_token/refresh_token/client_secret parameter) from a string before it can be shown or stored."""
    s = str(text)
    for v in secrets_of(tok if tok is not None else load_token()):
        s = s.replace(v, "[REDACTED]")
    s = re.sub(r"((?:access_token|refresh_token|client_secret|key)=)[^&\s\"']+", r"\1[REDACTED]", s)
    return re.sub(r"(Bearer\s+)[A-Za-z0-9._~+/=-]{8,}", r"\1[REDACTED]", s)


def has_token(path: Path | None = None) -> bool:
    t = load_token(path)
    return bool(t.get("refresh_token") and t.get("client_id") and t.get("client_secret"))


def token_state(tok: dict, at: datetime | None = None) -> str:
    if not tok:
        return f"no token file ({TOKEN_FILE})"
    if not tok.get("refresh_token"):
        return "token file has no refresh token: authorise again"
    scopes = tok.get("scopes") or []
    if isinstance(scopes, str):
        scopes = scopes.split()
    short = ", ".join(s.rsplit("/", 1)[-1] for s in scopes) or "scopes unknown"
    exp = tok.get("expiry")
    left = ""
    try:
        if exp:
            e = datetime.fromisoformat(exp.replace("Z", "+00:00"))
            e = e if e.tzinfo else e.replace(tzinfo=timezone.utc)
            m = (e - (at or now())).total_seconds() / 60
            left = f"; access token {'valid ' + str(int(m)) + ' min' if m > 0 else 'expired, refreshed on the next call'}"
    except ValueError:
        pass
    need_pl = "" if SCOPE_PLAYLIST in scopes else "; NO playlist scope (playlists need https://www.googleapis.com/auth/youtube: authorise once more)"
    return f"token present with a refresh token ({short}){left}{need_pl}"


# ---------------------------------------------------------------- the API (replaced in tests)
def _build(path: Path):
    """The authorised service object. Refreshes the access token when it is missing or expired and saves the file back (atomic)."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    creds = Credentials.from_authorized_user_file(str(path))
    if not creds.valid:
        creds.refresh(Request())
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(creds.to_json(), encoding="utf-8")
        os.replace(tmp, path)
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def service(path: Path | None = None):
    p = Path(path or TOKEN_FILE)
    tok = load_token(p)
    if not has_token(p):
        fail("YT-CREDS", f"missing or incomplete token file {p} (refresh_token, client_id, client_secret)")
    try:
        return _build(p)
    except Exception as e:     # noqa: BLE001  any library error: redacted, never raw
        fail("YT-AUTH", redact(f"{type(e).__name__}: {e}", tok))


def _media(path: Path):
    from googleapiclient.http import MediaFileUpload
    return MediaFileUpload(str(path), mimetype="video/mp4", chunksize=CHUNK, resumable=True)


def _image(path: Path):
    from googleapiclient.http import MediaFileUpload
    return MediaFileUpload(str(path), mimetype="image/jpeg")


def call(fn, what: str, tok: dict | None = None):
    """Run one API call; any failure becomes one redacted YtError carrying the HTTP status when there is one."""
    try:
        return fn()
    except SystemExit:
        raise
    except Exception as e:     # noqa: BLE001
        code = getattr(getattr(e, "resp", None), "status", None)
        err = YtError(f"FAIL [YT-HTTP] {what}: " + redact(f"{type(e).__name__}{' ' + str(code) if code else ''}: {e}", tok))
        err.http_status = code
        raise err


# ---------------------------------------------------------------- the record and the playlist state
def rec_path(ep: str, repo: Path = REPO) -> Path:
    return wdir(ep, repo) / "youtube.json"


def load_record(ep: str, repo: Path = REPO) -> dict | None:
    """None = no file; the record; or {"corrupt": True} for an unreadable file (it still counts as posted: never upload over a record we cannot read)."""
    p = rec_path(ep, repo)
    if not p.is_file():
        return None
    try:
        r = json.loads(p.read_text(encoding="utf-8"))
        return r if isinstance(r, dict) else {"corrupt": True}
    except (ValueError, OSError):
        return {"corrupt": True}


def is_posted(ep: str, repo: Path = REPO) -> bool:
    return rec_path(ep, repo).is_file()


def state_path(repo: Path = REPO) -> Path:
    return repo / "work" / "state" / "youtube.json"


def audit_flag(repo: Path = REPO) -> Path:
    return repo / "work" / "state" / AUDIT_FLAG


def privacy_for(repo: Path = REPO) -> str:
    """"private" until the YouTube API compliance audit has passed, then "public". The Lead (or the owner) creates the flag file work/state/yt_audit_passed after Google's
    approval email; nothing else ever does. Until then every upload is requested private on purpose: YouTube locks an unaudited project's uploads to private anyway,
    and asking for public would only publish the title and description of a video nobody can see (and a video flipped public by hand later keeps its own record)."""
    return "public" if audit_flag(repo).exists() else "private"


def create_record(ep: str, rec: dict, repo: Path = REPO, force: bool = False) -> None:
    """The pending record, created with O_EXCL right after the is_posted check: of two overlapping runs only one can write it, the other fails YT-ALREADY.
    (--force replaces an existing record.)"""
    p = rec_path(ep, repo)
    p.parent.mkdir(parents=True, exist_ok=True)
    if force:
        write_json(p, rec)
        return
    try:
        fd = os.open(str(p), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        fail("YT-ALREADY", f"{ep}: another run created youtube.json first; check the channel, then --force")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False, indent=2) + "\n")


def load_state(repo: Path = REPO) -> dict:
    return read_json(state_path(repo)) or {}


# ---------------------------------------------------------------- the text
def episode_hook(ep: str, repo: Path = REPO) -> str:
    """The hook sentence of the Instagram caption's first line («الحلقة N | the series 🧳 hook»), without the emoji. Empty when the line does not have that shape."""
    first = (ig.build_caption(ep, repo, "instagram").splitlines() or [""])[0]
    m = re.match(rf"^\s*الحلقة\s+(\S+)\s*[|｜]\s*(.+?)\s*(?={ig._EMOJI})", first)
    return first[m.end() + 1:].strip() if m else ""


def make_title(ep: str, hook: str) -> str:
    base = f"{SERIES} | الحلقة {ig.episode_number_ar(ep)}"
    t = f"{base} | {hook}" if hook else base
    if len(t) > TITLE_MAX:
        cut = t[:TITLE_MAX - 1].rsplit(" ", 1)[0].rstrip(" |،,")
        t = cut + "…"
    return display_text(t)


def video_seconds(video: Path) -> float | None:
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)], capture_output=True, text=True, timeout=30)
        return float(r.stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def yt_parts(ep: str, repo: Path = REPO, seconds: float | None = None) -> tuple:
    """(title, description). caption-youtube.txt / title-youtube.txt in the episode folder win. Otherwise: title «the series | الحلقة N | hook»; the description is
    the Instagram text with the series prefix moved out of the first line (it is in the title), the same open question, the closing line gaining «الحلقة N من ...», and
    three hashtags (#Shorts as the third when the video is a Short, at most 3 minutes)."""
    ep_dir = ig.find_ep(ep, repo)
    tf, df = ep_dir / "title-youtube.txt", ep_dir / "caption-youtube.txt"
    hook = episode_hook(ep, repo)
    title = display_text(tf.read_text(encoding="utf-8")).strip().splitlines()[0] if tf.is_file() and tf.read_text(encoding="utf-8").strip() else make_title(ep, hook)
    if df.is_file() and df.read_text(encoding="utf-8").strip():
        return title, display_text(df.read_text(encoding="utf-8"))
    ig_text = ig.build_caption(ep, repo, "instagram")
    lines = ig_text.splitlines()
    first = lines[0] if lines else ""
    m = re.match(rf"^\s*الحلقة\s+(\S+)\s*[|｜]\s*(.+?)\s*(?={ig._EMOJI})", first)
    if m:
        lines[0] = f"{first[m.end() + 1:].strip()} {first[m.end()]}".strip()      # the hook alone, its emoji at the end (the series and number are in the title)
    short = seconds is not None and seconds <= SHORTS_MAX_S
    tags = " ".join((*HASHTAGS[:2], "#Shorts") if short else HASHTAGS)
    n_ar = ig.episode_number_ar(ep)
    out = []
    for ln in lines:
        if ln.strip() == ig.CLOSING:
            ln = f"الحلقة {n_ar} من {SERIES}. {ig.CLOSING}"
        elif ln.strip().startswith("#"):
            ln = tags
        out.append(ln)
    out.insert(1, seo.keyword_line())      # the first ~150 characters are what search shows: the hook, then the series keywords in plain words
    if not any(l.strip().startswith("#") for l in out):
        out += ["", tags]
    return title, display_text("\n".join(out))


def text_problems(title: str, desc: str) -> list:
    bad = ig.caption_problems(desc, "youtube") + [f"title: {b}" for b in ig.caption_problems(title, "youtube")]
    if has_tashkeel(title) or has_tashkeel(desc):
        bad.append("tashkeel or tatweel")
    if "<" in title + desc or ">" in title + desc:
        bad.append("'<' or '>' (YouTube refuses them in titles and descriptions)")
    if len(title) > TITLE_MAX:
        bad.append(f"title is {len(title)} characters (limit {TITLE_MAX})")
    if len(desc.encode("utf-8")) > DESC_MAX:
        bad.append("description is over 5000 bytes")
    return bad


def video_resource(title: str, desc: str, privacy: str = "private") -> dict:
    return {"snippet": {"title": title, "description": desc, "categoryId": CATEGORY_ID, "defaultLanguage": LANGUAGE, "defaultAudioLanguage": LANGUAGE,
                        "tags": seo.youtube_tags()},
            "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True, "embeddable": True, "publicStatsViewable": True,
                       "license": seo.load()["youtube_license"]}}


# ---------------------------------------------------------------- playlist
def ensure_playlist(svc, repo: Path = REPO, tok: dict | None = None) -> str:
    """The id of the playlist «the series», created once and stored in work/state/youtube.json. A playlist with that title already on the channel is reused
    (a crash between create and save must never make a second one)."""
    st = load_state(repo)
    if st.get("playlist_id"):
        return st["playlist_id"]
    page = None
    while True:
        r = call(lambda: svc.playlists().list(part="snippet", mine=True, maxResults=50, **({"pageToken": page} if page else {})).execute(), "playlists.list", tok)
        for it in r.get("items", []):
            if (it.get("snippet") or {}).get("title") == PLAYLIST_TITLE:
                st.update(playlist_id=it["id"], channel_id=CHANNEL_ID)
                write_json(state_path(repo), st)
                return it["id"]
        page = r.get("nextPageToken")
        if not page:
            break
    body = {"snippet": {"title": PLAYLIST_TITLE, "description": f"{SERIES}: episodes in order", "defaultLanguage": LANGUAGE}, "status": {"privacyStatus": "public"}}
    r = call(lambda: svc.playlists().insert(part="snippet,status", body=body).execute(), "playlists.insert", tok)
    pid = r.get("id") or fail("YT-PLAYLIST", "no playlist id returned")
    st.update(playlist_id=pid, channel_id=CHANNEL_ID, created_at=now().isoformat(timespec="seconds"))
    write_json(state_path(repo), st)
    return pid


def add_to_playlist(ep: str, svc, repo: Path = REPO, tok: dict | None = None, force: bool = False) -> dict:
    """Put the uploaded video into the playlist. Never fatal for the upload: a failure (typically the missing `youtube` scope) is recorded as playlist_error.
    The step is recorded as playlist_state "adding" BEFORE the insert call: a crash or a lost answer leaves "adding", and then nothing adds the video again
    (it may already be in the playlist) until `yt.py playlist <ep> --go --force` after a look at the playlist."""
    rec = load_record(ep, repo)
    if not rec or not rec.get("video_id"):
        fail("YT-NOPOST", f"{ep} has no readable youtube.json with a video id")
    if rec.get("playlist_item_id"):
        return rec
    if rec.get("playlist_state") == "adding" and not force:
        rec["playlist_error"] = "a previous playlist insert did not report back; the video may already be in the playlist: check it, then `yt.py playlist --go --force`"
        write_json(rec_path(ep, repo), rec)
        return rec
    try:
        pid = ensure_playlist(svc, repo, tok)
        body = {"snippet": {"playlistId": pid, "resourceId": {"kind": "youtube#video", "videoId": rec["video_id"]}}}
        rec.update(playlist_id=pid, playlist_state="adding", playlist_error=None)
        write_json(rec_path(ep, repo), rec)                    # BEFORE the insert
        r = call(lambda: svc.playlistItems().insert(part="snippet", body=body).execute(), "playlistItems.insert", tok)
        rec.update(playlist_item_id=r.get("id"), playlist_state="added", playlist_error=None)
    except SystemExit as e:
        hint = " (the token lacks the `youtube` scope: authorise https://www.googleapis.com/auth/youtube once)" if getattr(e, "http_status", None) in (401, 403) else ""
        rec["playlist_error"] = (str(e)[:300] + hint)
        if getattr(e, "http_status", None) in (400, 401, 403, 404):   # the API refused the insert: nothing was added, a retry is safe
            rec["playlist_state"] = "failed"
    write_json(rec_path(ep, repo), rec)
    return rec


# ---------------------------------------------------------------- publish
def cmd_publish(ep: str, go: bool = False, force: bool = False, repo: Path = REPO, svc=None, sleep=time.sleep) -> dict:
    why = ig.publish_gates(ep, repo)
    if why:
        fail("YT-GATE", "refusing to upload " + ep + ": " + "; ".join(why))
    w = wdir(ep, repo)
    if is_posted(ep, repo) and not force:
        r = load_record(ep, repo) or {}
        fail("YT-ALREADY", f"{ep} is already on record for YouTube (work/episodes/{ep}/youtube.json, state {r.get('state', 'unreadable')!r}); check the channel, then --force to upload again")
    video = w / "episode.mp4"
    secs = video_seconds(video)
    title, desc = yt_parts(ep, repo, secs)
    bad = text_problems(title, desc)
    if bad:
        fail("YT-CAPTION-BAIT", "the YouTube text breaks the wording rules (pipelines/AUDIENCE.md): " + "; ".join(bad) + "; nothing was uploaded")
    plan = {"episode": ep, "video": video.as_posix(), "bytes": video.stat().st_size, "seconds": secs, "title": title, "description": desc, "mode": "DRY RUN",
            "resource": video_resource(title, desc, privacy_for(repo))}
    if not go:
        print("DRY RUN (add --go to upload to YouTube). Gates clear. Title: " + title + "\nDescription:\n" + desc
              + f"\nVideo: {plan['video']} ({plan['bytes']} bytes{'' if secs is None else f', {secs:.0f} s'}), resumable upload, category {CATEGORY_ID}, language {LANGUAGE}, "
              f"not made for kids, containsSyntheticMedia=true, privacy {plan['resource']['status']['privacyStatus']} "
              + ("(the audit flag exists)." if audit_flag(repo).exists() else f"(private until the API audit passes: create work/state/{AUDIT_FLAG} then; the answer YouTube gives is recorded)."))
        return plan
    if not (w / "post.json").is_file():
        fail("YT-WAIT-INSTAGRAM", f"{ep} is not on Instagram yet: YouTube never goes live before Instagram, so it waits; nothing was uploaded")
    tok = load_token()
    svc = svc if svc is not None else service()
    rec = {"episode": ep, "video_id": None, "url": None, "state": PENDING, "title": title, "description": desc, "privacy_requested": plan["resource"]["status"]["privacyStatus"], "privacy_actual": None,
           "upload_status": None, "posted_at": now().isoformat(timespec="seconds"), "playlist_id": None, "playlist_item_id": None, "playlist_error": None}
    create_record(ep, rec, repo, force)        # O_EXCL, BEFORE the first byte: from now on any retry needs --force
    req = call(lambda: svc.videos().insert(part="snippet,status", body=plan["resource"], media_body=_media(video)), "videos.insert", tok)
    resp, tries = None, 0
    while resp is None:
        try:
            _, resp = call(lambda: req.next_chunk(num_retries=RETRIES), "videos.insert chunk", tok)
        except SystemExit as e:
            rec["state"] = "upload-failed"
            rec["error"] = str(e)[:300]
            write_json(rec_path(ep, repo), rec)
            fail("YT-UPLOAD", f"{e}; recorded as 'upload-failed': check the channel in Studio before any --force")
        tries += 1
        if tries > 100000:
            fail("YT-UPLOAD", "too many chunks")
    vid = (resp or {}).get("id")
    if not vid:
        rec["state"] = "upload-no-id"
        write_json(rec_path(ep, repo), rec)
        fail("YT-UPLOAD", "the upload finished but no video id came back; recorded, check the channel before any --force")
    rec.update(video_id=vid, url=f"https://www.youtube.com/shorts/{vid}" if (secs is not None and secs <= SHORTS_MAX_S) else f"https://www.youtube.com/watch?v={vid}", state="uploaded")
    write_json(rec_path(ep, repo), rec)
    try:                                       # what YouTube really did with it (it may lock an unaudited project's upload to private)
        r = call(lambda: svc.videos().list(part="status", id=vid).execute(), "videos.list", tok)
        st = ((r.get("items") or [{}])[0].get("status")) or {}
        rec.update(privacy_actual=st.get("privacyStatus"), upload_status=st.get("uploadStatus"), made_for_kids=st.get("madeForKids"), rejection=st.get("rejectionReason"),
                   locked_private=rec.get("privacy_requested") == "public" and st.get("privacyStatus") not in (None, "public"))
    except SystemExit as e:
        rec["status_error"] = str(e)[:200]
    write_json(rec_path(ep, repo), rec)
    set_thumbnail(ep, svc, repo, tok)         # R-501: the grid poster is the thumbnail; a refusal is recorded and never stops the playlist step
    rec = add_to_playlist(ep, svc, repo, tok)
    blob = json.dumps(rec, ensure_ascii=False)
    for v in secrets_of(tok):
        if v in blob:
            fail("YT-LEAK", "a credential value appeared in the YouTube record")
    print(f"UPLOADED {ep} to YouTube: {rec['url']} (privacy {rec.get('privacy_actual')!r}{', locked private by YouTube until the API audit passes' if rec.get('locked_private') else (', private until the audit flag exists' if rec.get('privacy_requested') == 'private' else '')})"
          + (f"; playlist: {rec['playlist_error']}" if rec.get("playlist_error") else ""))
    return rec


def set_thumbnail(ep: str, svc, repo: Path = REPO, tok: dict | None = None, cover: Path | None = None) -> dict:
    """R-501: the video's thumbnail is the grid poster (thumbnails.set). A channel that cannot use custom thumbnails (not verified: 403) is recorded and skipped, never fatal.
    Returns {"state": "set"|"skipped"|"failed", "error": ...} and writes it to the record as `thumbnail`."""
    from ig import cover_file
    rec = load_record(ep, repo) or {}
    f = Path(cover) if cover else cover_file(wdir(ep, repo))
    if f is None or not f.is_file() or not rec.get("video_id"):
        return {"state": "skipped", "error": "no cover.jpg" if f is None else "no video id"}
    try:
        call(lambda: svc.thumbnails().set(videoId=rec["video_id"], media_body=_image(f)).execute(), "thumbnails.set", tok)
        res = {"state": "set", "error": None}
    except SystemExit as e:
        res = {"state": "skipped" if getattr(e, "http_status", None) in (400, 403) else "failed", "error": str(e)[:200]}
        print(f"WARNING YouTube thumbnail not set for {ep}: {res['error']} (a channel needs phone verification for custom thumbnails)")
    except Exception as e:     # noqa: BLE001  a missing client library or file: logged, never fatal
        res = {"state": "failed", "error": redact(f"{type(e).__name__}: {e}", tok)[:200]}
        print(f"WARNING YouTube thumbnail not set for {ep}: {res['error']}")
    rec["thumbnail"] = res
    write_json(rec_path(ep, repo), rec)
    return res


def cmd_thumbnail(ep: str, go: bool = False, repo: Path = REPO, svc=None, cover: Path | None = None) -> dict:
    rec = load_record(ep, repo)
    if not rec or not rec.get("video_id"):
        fail("YT-NOPOST", f"{ep} has no readable youtube.json with a video id")
    if not go:
        print(f"DRY RUN (add --go). Would set the grid poster as the thumbnail of YouTube video {rec['video_id']}.")
        return rec
    res = set_thumbnail(ep, svc if svc is not None else service(), repo, load_token(), cover)
    print(f"YouTube thumbnail of {ep}: {res['state']}" + (f" ({res['error']})" if res.get("error") else ""))
    return load_record(ep, repo) or rec


def cmd_playlist(ep: str, go: bool = False, repo: Path = REPO, svc=None, force: bool = False) -> dict:
    rec = load_record(ep, repo)
    if not rec or not rec.get("video_id"):
        fail("YT-NOPOST", f"{ep} has no readable youtube.json with a video id")
    if rec.get("playlist_item_id"):
        print(f"{ep} is already in the playlist {rec.get('playlist_id')}")
        return rec
    if not go:
        print(f"DRY RUN (add --go). Would add {rec['video_id']} to the playlist «{PLAYLIST_TITLE}».")
        return rec
    rec = add_to_playlist(ep, svc if svc is not None else service(), repo, load_token(), force)
    print(f"playlist: {rec.get('playlist_item_id') or rec.get('playlist_error')}")
    return rec


# ---------------------------------------------------------------- comments (ideas only)
def yt_comment(sn: dict, cid: str, parent: str | None) -> dict:
    ch = (sn.get("authorChannelId") or {}).get("value")
    return {"id": cid, "platform": "youtube", "parent_id": parent, "text": sn.get("textDisplay") or sn.get("textOriginal") or "", "username": sn.get("authorDisplayName"),
            "user_id": ch, "timestamp": sn.get("publishedAt"), "own": bool(ch and ch == CHANNEL_ID)}


def cmd_comments(ep: str, force: bool = False, repo: Path = REPO, svc=None, at: datetime | None = None) -> dict:
    """commentThreads.list -> comments.json rows tagged platform=youtube. vote.tally_comments counts only Instagram rows, so these are ideas, never votes."""
    import fb
    w = wdir(ep, repo)
    rec = load_record(ep, repo)
    if not rec or not rec.get("video_id"):
        fail("YT-NOPOST", f"{ep} has no readable youtube.json with a video id: nothing known to be uploaded")
    try:
        due = datetime.fromisoformat(rec["posted_at"]) + timedelta(hours=ig.HOURS_BEFORE_COMMENTS)
    except (KeyError, ValueError, TypeError):
        fail("YT-RECORD", f"{ep}: youtube.json has no usable time")
    cur = at or now()
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    if cur < due and not force:
        fail("YT-TOO-EARLY", f"{(due - cur).total_seconds() / 3600:.1f} h until the {ig.HOURS_BEFORE_COMMENTS} h mark; --force to read now")
    tok = load_token()
    svc = svc if svc is not None else service()
    mine, page = [], None
    while True:
        kw = {"part": "snippet,replies", "videoId": rec["video_id"], "maxResults": 100, "order": "time", "textFormat": "plainText"}
        if page:
            kw["pageToken"] = page
        try:
            r = call(lambda: svc.commentThreads().list(**kw).execute(), "commentThreads.list", tok)
        except SystemExit as e:
            if "commentsDisabled" in str(e):
                fail("YT-COMMENTS-OFF", f"{ep}: comments are disabled on the video")
            raise
        for th in r.get("items", []):
            top = ((th.get("snippet") or {}).get("topLevelComment")) or {}
            mine.append(yt_comment(top.get("snippet") or {}, top.get("id") or th.get("id"), None))
            for rp in ((th.get("replies") or {}).get("comments")) or []:
                mine.append(yt_comment(rp.get("snippet") or {}, rp.get("id"), top.get("id")))
        page = r.get("nextPageToken")
        if not page:
            break
    for c in mine:
        c["fetched_at"] = cur.isoformat(timespec="seconds")      # the retention clock of the privacy page: a row older than 30 days is pruned unless a fetch refreshed it
    cm = read_json(w / "comments.json") or {}
    merged = fb.merge_comments(cm.get("comments", []), mine, "youtube")
    res = {**cm, "episode": ep, "fetched_at": cur.isoformat(timespec="seconds"), "count": len(merged), "comments": merged, "youtube_video_id": rec["video_id"],
           "platforms": sorted({c["platform"] for c in merged}), "own_usernames": cm.get("own_usernames") or []}
    blob = json.dumps(res, ensure_ascii=False)
    for v in secrets_of(tok):
        if v in blob:
            fail("YT-LEAK", "a credential value appeared in the comments output; not written")
    write_json(w / "comments.json", res)
    rec["comments_fetched_at"] = cur.isoformat(timespec="seconds")
    rec["comments_count"] = len(mine)
    write_json(rec_path(ep, repo), rec)
    print(f"{ep}: {len(mine)} YouTube comments and replies merged as ideas -> work/episodes/{ep}/comments.json ({len(merged)} in all)")
    return res


# ---------------------------------------------------------------- retention (the public privacy page: comments refreshed or deleted within 30 days, all of it on request)
RETENTION_DAYS = 30


def _row_time(c: dict, fallback):
    for t in (c.get("fetched_at"), c.get("timestamp"), fallback):
        try:
            if t:
                d = datetime.fromisoformat(str(t).replace("Z", "+00:00"))
                return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _scrub_derived(w: Path, ids: set, texts: list) -> int:
    """Remove the YouTube-sourced copies of deleted comments from the idea stores built from them: decision.json `ideas`, late-ideas.json, next-brief.md lines."""
    n = 0
    for name, count_key in (("decision.json", "idea_count"), ("late-ideas.json", "count")):
        p = w / name
        try:
            d = read_json(p)
        except ValueError:
            continue
        if isinstance(d, dict) and isinstance(d.get("ideas"), list):
            keep = [i for i in d["ideas"] if not (i.get("platform") == "youtube" and i.get("id") in ids)]
            if len(keep) != len(d["ideas"]):
                n += len(d["ideas"]) - len(keep)
                d["ideas"], d[count_key] = keep, len(keep)
                write_json(p, d)
    bp = w / "next-brief.md"
    if bp.is_file() and texts:
        lines = bp.read_text(encoding="utf-8").split("\n")
        keep = [l for l in lines if not any(t and len(t) >= 6 and t in l for t in texts)]
        if len(keep) != len(lines):
            n += len(lines) - len(keep)
            bp.write_text("\n".join(keep), encoding="utf-8")
    return n


def prune_comments(repo: Path = REPO, at: datetime | None = None, days: int = RETENTION_DAYS, everything: bool = False) -> dict:
    """Delete YouTube-sourced comment rows older than `days` (everything=True: all of them) from every comments.json, and their copies in decision.json, late-ideas.json and
    next-brief.md. Instagram and Facebook rows are never touched. Run by the Harvest task; `yt.py forget` calls it with everything=True."""
    cur = at or now()
    old = datetime.min.replace(tzinfo=timezone.utc)
    rows = copies = files = 0
    wd = repo / "work" / "episodes"
    for w in sorted(wd.glob("*")) if wd.is_dir() else []:
        cp = w / "comments.json"
        try:
            cm = read_json(cp)
        except ValueError:
            continue
        if not isinstance(cm, dict) or not isinstance(cm.get("comments"), list):
            continue
        gone = [c for c in cm["comments"] if c.get("platform") == "youtube" and (everything or (_row_time(c, cm.get("fetched_at")) or old) < cur - timedelta(days=days))]
        if not gone:
            continue
        ids = {c.get("id") for c in gone}
        cm["comments"] = [c for c in cm["comments"] if not (c.get("platform") == "youtube" and c.get("id") in ids)]
        cm["count"] = len(cm["comments"])
        cm["platforms"] = sorted({c.get("platform") or "instagram" for c in cm["comments"]})
        if not any(c.get("platform") == "youtube" for c in cm["comments"]):
            cm.pop("youtube_video_id", None)
        write_json(cp, cm)
        copies += _scrub_derived(w, ids, [c.get("text") or "" for c in gone])
        rows += len(gone)
        files += 1
    return {"rows_deleted": rows, "idea_copies_deleted": copies, "files": files}


def cmd_forget(go: bool = False, repo: Path = REPO, records: bool = False) -> dict:
    """Delete ALL stored YouTube-sourced data at once (a deletion request): every YouTube comment row and every idea copy, the comment counters in youtube.json.
    records=True also deletes the upload records youtube.json and the playlist state (then the episode could be uploaded again: only on purpose). The OAuth token is
    ours, not user data: revoke it in the Google account to remove it. Dry run without --go."""
    wd = repo / "work" / "episodes"
    eps = sorted(wd.glob("*")) if wd.is_dir() else []
    n = 0
    for w in eps:
        try:
            n += sum(1 for c in (read_json(w / "comments.json") or {}).get("comments", []) if c.get("platform") == "youtube")
        except ValueError:
            pass
    if not go:
        print(f"DRY RUN (add --go). Would delete {n} stored YouTube comment rows, their idea copies" + (", the upload records and the playlist state" if records else "") + ".")
        return {"rows": n, "mode": "DRY RUN"}
    res = prune_comments(repo, everything=True)
    for w in eps:
        rp = w / "youtube.json"
        if not rp.is_file():
            continue
        if records:
            rp.unlink()
            continue
        try:
            r = read_json(rp)
        except ValueError:
            continue
        if isinstance(r, dict):
            for k in ("comments_fetched_at", "comments_count"):
                r.pop(k, None)
            write_json(rp, r)
    if records:
        state_path(repo).unlink(missing_ok=True)
    print(f"FORGOTTEN: {res['rows_deleted']} YouTube comment rows and {res['idea_copies_deleted']} idea copies deleted" + (" (upload records and playlist state too)" if records else ""))
    return {**res, "records": records}


# ---------------------------------------------------------------- status
def cmd_status(live: bool = False, repo: Path = REPO, svc=None) -> str:
    tok = load_token()
    out = [f"token file: {'found' if TOKEN_FILE.is_file() else 'MISSING'} ({TOKEN_FILE})", token_state(tok)]
    st = load_state(repo)
    out.append(f"playlist «{PLAYLIST_TITLE}»: {st.get('playlist_id') or 'not created yet'}")
    wd = repo / "work" / "episodes"
    for d in sorted(wd.glob("*")) if wd.is_dir() else []:
        rec = load_record(d.name, repo)
        out.append(f"{d.name}: " + (f"on record for YouTube {rec.get('posted_at')} ({rec.get('state', 'unreadable file')}, privacy {rec.get('privacy_actual')}) {rec.get('url') or ''}".rstrip()
                                    if rec else "not uploaded to YouTube"))
    if live:
        svc = svc if svc is not None else service()
        r = call(lambda: svc.channels().list(part="snippet", mine=True).execute(), "channels.list", tok)
        items = r.get("items", [])
        ids = [i.get("id") for i in items]
        out.append("live check: channel " + (", ".join(f"{(i.get('snippet') or {}).get('title')!r} ({i.get('id')})" for i in items) or "none returned")
                   + ("" if CHANNEL_ID in ids else f"; EXPECTED {CHANNEL_ID} NOT FOUND"))
    s = redact("\n".join(out), tok)
    print(s)
    return s


READBACK_TRIES, READBACK_WAIT = 8, 10      # the API answers reads from a replica that lags a write by seconds to minutes (measured 2026-10-27: a playlist update read back stale at once, right 20 s later)


def poll_readback(read, ok, sleep=time.sleep, tries: int = READBACK_TRIES, wait: float = READBACK_WAIT):
    """(last read, ok) — re-reads until `ok(read)` holds or the tries run out. A read right after a write may still show the old value."""
    last = None
    for i in range(tries):
        last = read()
        if ok(last):
            return last, True
        if i < tries - 1:
            sleep(wait)
    return last, False


def _same(key: str, have, want) -> bool:
    """Tags come back from the API re-ordered (sorted), so they are compared as sets; every other field must match exactly."""
    if key == "tags":
        return {t.strip() for t in have or []} == {t.strip() for t in want or []}
    return have == want


def cmd_seo_fix(target: str, go: bool = False, repo: Path = REPO, svc=None, sleep=time.sleep) -> dict:
    """Correct the search metadata of a video that is already up (Studio uploads inherit the channel's old upload defaults: gaming tags, category Gaming, English,
    Creative Commons licence). Reads the video, keeps its title, description and every other status field, and sets the series tags, category, language and the
    standard YouTube licence. Dry run by default (it reads the video, writes nothing); --go calls videos.update (needs the `youtube` scope, which the token has since the playlist step)."""
    vid = target
    if re.fullmatch(r"E\d{2,3}[A-Za-z]?", target):      # an episode id (E01C); a video id is 11 characters and may start with E (E5_Amg97q7k)
        rec = load_record(target, repo) or {}
        vid = rec.get("video_id") or fail("YT-SEO", f"no YouTube record for {target}")
    tok = load_token()
    svc = svc if svc is not None else service()      # the dry run only READS the video
    r = call(lambda: svc.videos().list(part="snippet,status", id=vid).execute(), "videos.list", tok)
    items = r.get("items") or []
    if not items:
        fail("YT-SEO", f"video {vid} not found on the channel")
    sn, st = dict(items[0]["snippet"]), dict(items[0]["status"])
    want = {"tags": seo.youtube_tags(), "categoryId": CATEGORY_ID, "defaultLanguage": LANGUAGE, "defaultAudioLanguage": LANGUAGE}
    st_keep = {k: st[k] for k in ("privacyStatus", "embeddable", "publicStatsViewable", "selfDeclaredMadeForKids", "containsSyntheticMedia") if k in st}
    st_new = {**st_keep, "license": seo.load()["youtube_license"]}
    body = {"id": vid, "snippet": {"title": sn["title"], "description": sn.get("description", ""), **want}, "status": st_new}
    diff = {k: {"from": sn.get(k), "to": v} for k, v in want.items() if not _same(k, sn.get(k), v)}
    if st.get("license") != st_new["license"]:
        diff["license"] = {"from": st.get("license"), "to": st_new["license"]}
    out = {"video": vid, "changes": diff, "mode": "WRITE" if go else "DRY RUN"}
    if go and diff:
        resp = call(lambda: svc.videos().update(part="snippet,status", body=body).execute(), "videos.update", tok) or {}
        out["update_response_tags"] = (resp.get("snippet") or {}).get("tags")
        def read():
            return (call(lambda: svc.videos().list(part="snippet,status", id=vid).execute(), "videos.list", tok).get("items") or [{}])[0].get("snippet", {})
        bs, ok = poll_readback(read, lambda b: all(_same(k, b.get(k), v) for k, v in want.items()), sleep)
        out["readback"] = {k: bs.get(k) for k in want}
        out["readback_ok"] = ok
    return out


def cmd_channel_seo(go: bool = False, repo: Path = REPO, svc=None, sleep=time.sleep) -> dict:
    """Channel description, channel keywords and language (channels.update, brandingSettings), the series playlist description and the privacy of the off-topic
    playlists named in data/seo/keywords.json (`playlists_private`). The whole brandingSettings block is read, changed in the three fields and sent back, because
    channels.update replaces the part. Dry run by default; --go writes, then reads everything back."""
    tok = load_token()
    svc = svc if svc is not None else service()
    d = seo.load()
    ch = (call(lambda: svc.channels().list(part="snippet,brandingSettings", mine=True).execute(), "channels.list", tok).get("items") or [None])[0]
    if not ch or ch.get("id") != CHANNEL_ID:
        fail("YT-SEO", f"the token's channel is not {CHANNEL_ID}")
    br = json.loads(json.dumps(ch.get("brandingSettings") or {}))
    cb = br.setdefault("channel", {})
    want = {"description": d["channel_description"], "keywords": d["channel_keywords"], "defaultLanguage": d["channel_language"]}
    changes = {"channel": {k: {"from": cb.get(k), "to": v} for k, v in want.items() if cb.get(k) != v}}
    cb.update(want)
    pls = call(lambda: svc.playlists().list(part="snippet,status", mine=True, maxResults=50).execute(), "playlists.list", tok).get("items") or []
    todo = []
    for pl in pls:
        sn, stt = pl["snippet"], pl["status"]
        new_sn, new_st = dict(sn), dict(stt)
        if sn.get("title") == PLAYLIST_TITLE and sn.get("description") != d["playlist_description"]:
            new_sn["description"] = d["playlist_description"]
        if sn.get("title") in d.get("playlists_private", []) and stt.get("privacyStatus") != "private":
            new_st["privacyStatus"] = "private"
        if new_sn != sn or new_st != stt:
            changes["playlist " + sn["title"]] = {"description": {"from": sn.get("description"), "to": new_sn.get("description")} if new_sn != sn else "unchanged",
                                                  "privacy": {"from": stt.get("privacyStatus"), "to": new_st.get("privacyStatus")} if new_st != stt else "unchanged"}
            todo.append((pl["id"], new_sn, new_st))
    out = {"changes": changes, "mode": "WRITE" if go else "DRY RUN"}
    if go:
        if changes["channel"]:
            call(lambda: svc.channels().update(part="brandingSettings", body={"id": CHANNEL_ID, "brandingSettings": br}).execute(), "channels.update", tok)
        for pid, sn, stt in todo:
            body = {"id": pid, "snippet": {"title": sn["title"], "description": sn.get("description", ""), **({"defaultLanguage": sn["defaultLanguage"]} if sn.get("defaultLanguage") else {})},
                    "status": {"privacyStatus": stt["privacyStatus"]}}
            call(lambda: svc.playlists().update(part="snippet,status", body=body).execute(), "playlists.update", tok)
        def kw(x):      # the API drops the quotes around a one-word keyword
            return " ".join(x.replace('"', "").split()) if x else x

        def read():
            br_ = (call(lambda: svc.channels().list(part="brandingSettings", mine=True).execute(), "channels.list", tok).get("items") or [{}])[0].get("brandingSettings", {}).get("channel", {})
            pb_ = {p["id"]: p for p in call(lambda: svc.playlists().list(part="snippet,status", mine=True, maxResults=50).execute(), "playlists.list", tok).get("items") or []}
            return br_, pb_

        def ok(r):
            back, pb = r
            return all((kw(back.get(k)) == kw(v)) for k, v in want.items()) and all(
                pb.get(pid, {}).get("snippet", {}).get("description", "") == (sn.get("description") or "") and pb.get(pid, {}).get("status", {}).get("privacyStatus") == stt["privacyStatus"]
                for pid, sn, stt in todo)
        (back, pb), good = poll_readback(read, ok, sleep)
        out["readback"] = {"channel": {k: back.get(k) for k in want},
                           "playlists": {pid: {"description": pb[pid]["snippet"].get("description"), "privacy": pb[pid]["status"].get("privacyStatus")} for pid, _, _ in todo if pid in pb}}
        out["readback_ok"] = good
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="YouTube Data API v3 for Story-Wrap")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("publish"); p.add_argument("ep"); p.add_argument("--go", action="store_true"); p.add_argument("--force", action="store_true")
    p = sub.add_parser("playlist"); p.add_argument("ep"); p.add_argument("--go", action="store_true"); p.add_argument("--force", action="store_true")
    p = sub.add_parser("thumbnail"); p.add_argument("ep"); p.add_argument("--go", action="store_true"); p.add_argument("--cover", help="a jpg to use instead of the episode folder's cover.jpg")
    p = sub.add_parser("comments"); p.add_argument("ep"); p.add_argument("--force", action="store_true")
    p = sub.add_parser("status"); p.add_argument("--live", action="store_true")
    p = sub.add_parser("forget"); p.add_argument("--go", action="store_true"); p.add_argument("--records", action="store_true")
    p = sub.add_parser("prune"); p.add_argument("--go", action="store_true")
    p = sub.add_parser("seo-fix"); p.add_argument("target", help="an episode id (E01C) or a YouTube video id"); p.add_argument("--go", action="store_true")
    p = sub.add_parser("channel-seo"); p.add_argument("--go", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "channel-seo":
        print(json.dumps(cmd_channel_seo(a.go), ensure_ascii=False, indent=1))
    elif a.cmd == "publish":
        cmd_publish(a.ep, a.go, a.force)
    elif a.cmd == "playlist":
        cmd_playlist(a.ep, a.go, force=a.force)
    elif a.cmd == "thumbnail":
        cmd_thumbnail(a.ep, a.go, cover=Path(a.cover) if a.cover else None)
    elif a.cmd == "comments":
        cmd_comments(a.ep, a.force)
    elif a.cmd == "forget":
        cmd_forget(a.go, records=a.records)
    elif a.cmd == "seo-fix":
        print(json.dumps(cmd_seo_fix(a.target, a.go), ensure_ascii=False, indent=1))
    elif a.cmd == "prune":
        print(prune_comments() if a.go else f"DRY RUN (add --go): YouTube comment rows older than {RETENTION_DAYS} days would be deleted")
    else:
        cmd_status(a.live)
    return 0


if __name__ == "__main__":
    sys.exit(main())
