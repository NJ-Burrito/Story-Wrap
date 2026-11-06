# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Live numbers for the Story-Wrap board, every 15 minutes (owner, 2026-10-27: "I don't see the numbers get updated on all platforms").

    uv run tools/live_numbers.py [--root DIR]     fetch YouTube, Instagram and Facebook numbers of every posted episode, then print one line per platform

`ig_board.py refresh --metrics` (task StoryWrap-Board, every 15 min) calls `refresh_all()`; it then rebuilds board/data/ and monitor.json from these files:

    work/episodes/<ep>/metrics-youtube.json     {fetched_at, video_id, views, likes, comments}                 YouTube Data API videos.list part=statistics (1 quota unit for all videos)
    work/episodes/<ep>/insights-instagram.json  {fetched_at, metrics: {name: {value, at} | {status, reason}}}  media insights (Page token, graph.facebook.com)
    work/episodes/<ep>/insights-facebook.json   the same for video_insights                                     (needs read_insights)

Instagram/Facebook likes and comments still come from `ig.cmd_metrics` / `fb.cmd_metrics` (metrics.json, metrics-facebook.json).

Rules: read-only calls; one metric per call so a metric the API refuses never blocks the others; a permission error is recorded with its exact reason
("needs instagram_manage_insights" / "needs read_insights"), never as a zero; a failed fetch keeps the last good value with its OLD time, so the board shows it as stale.
No credential is ever written (checked before every file is made) or printed. Standard library only (the YouTube call refreshes the OAuth access token over plain HTTP
and does not write the token file back).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.parse
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import ig  # noqa: E402

ROOT = Path(os.environ.get("STORYWRAP_ROOT") or os.environ.get("SW_REPO") or TOOLS.parent)
YT_TOKEN_FILE = Path(os.environ.get("SW_YT_TOKEN") or Path.home() / ".config" / "story-wrap" / "youtube-token.json")
YT_TOKEN_URI = "https://oauth2.googleapis.com/token"
YT_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
STALE_MIN = 30                      # the board marks a number older than this

# Reels insights on Graph API v26 (names verified against the API's own error text; a name it refuses is recorded with that text, never as zero)
IG_METRICS = ("views", "reach", "shares", "saved", "total_interactions", "ig_reels_avg_watch_time", "ig_reels_video_view_total_time")
IG_TOTAL_VALUE = ("views", "reach", "shares", "saved", "total_interactions")        # these need metric_type=total_value
IG_VIEWS_FALLBACK = "plays"
# Facebook REELS answer these on video_insights (measured 2026-10-27); the older total_video_* names return empty data or "not a valid insights metric" for a Reel
FB_METRICS = ("blue_reels_play_count", "fb_reels_replay_count", "post_video_avg_time_watched", "post_video_view_time")
IG_PERMISSION = "needs instagram_manage_insights"
FB_PERMISSION = "needs read_insights"
YT_SECRET_FIELDS = ("token", "refresh_token", "client_secret", "id_token", "client_id")


# ------------------------------------------------------------------ small io
def now_iso(at: dt.datetime | None = None) -> str:
    return (at or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc).isoformat(timespec="seconds")


def read_json(p: Path, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def wdir(root: Path, ep: str) -> Path:
    return Path(root) / "work" / "episodes" / ep


def episodes(root: Path) -> list[str]:
    d = Path(root) / "work" / "episodes"
    return sorted(p.name for p in d.iterdir() if p.is_dir()) if d.is_dir() else []


def write_checked(p: Path, data: dict, secrets: list[str]) -> None:
    """Atomic write; refuses (writes nothing) when a credential value is in the blob."""
    blob = json.dumps(data, ensure_ascii=False, indent=1)
    for s in secrets:
        if s and len(s) >= 8 and s in blob:
            raise SystemExit("LIVE-LEAK a credential value appeared in the live numbers; nothing was written")
    ig.write_json(Path(p), data)


def env_secrets(env: dict) -> list[str]:
    return [str(env[k]) for k in ig.SECRET_KEYS if env.get(k)]


# ------------------------------------------------------------------ error text
def classify(err, env: dict, permission: str) -> tuple[str, bool]:
    """(reason, is_permission_error) from a failed Graph call. Credentials are removed first."""
    s = re.sub(r"\s+", " ", ig.redact(str(err), env))
    low = s.lower()
    code = re.search(r'"code"\s*:\s*(\d+)', s)
    c = int(code.group(1)) if code else None
    if c in (10, 200, 3) or "permission" in low or "instagram_manage_insights" in low or "read_insights" in low or "(#10)" in low or "(#200)" in low:
        return permission, True
    if c == 190 or "access token" in low and ("expired" in low or "invalid" in low):
        return "token expired or invalid (code 190): the Page token must be renewed", False
    msg = re.search(r'"message"\s*:\s*"([^"]+)"', s)
    return (msg.group(1) if msg else s)[:200], False


def graph_value(resp: dict):
    d = (resp or {}).get("data") or []
    if not d:
        return None
    e = d[0]
    if isinstance(e.get("total_value"), dict):
        return e["total_value"].get("value")
    vals = e.get("values") or []
    return vals[0].get("value") if vals else None


def merge_metrics(old: dict, fresh: dict, at: str) -> dict:
    """A fresh value replaces the old; a failed metric keeps its last good value with its old time (the board then shows it as stale)."""
    out = {}
    for name, x in fresh.items():
        if "value" in x:
            out[name] = {"value": x["value"], "at": at}
        else:
            prev = (old or {}).get(name)
            out[name] = ({**prev, "error": x.get("reason")} if isinstance(prev, dict) and "value" in prev else x)
    return out


# ------------------------------------------------------------------ Instagram and Facebook insights
def _insights(call, path_of, names, env: dict, permission: str, total_value: tuple = (), fallback: dict | None = None):
    """One call per metric. After a permission error the rest would fail the same way: they get the same reason without more calls."""
    res: dict = {}
    denied = None
    for name in names:
        if denied:
            res[name] = {"status": "not available", "reason": denied}
            continue
        for attempt in (name, (fallback or {}).get(name)):
            if not attempt:
                break
            p = {"metric": attempt}
            if attempt in total_value:
                p["metric_type"] = "total_value"
            try:
                v = graph_value(call(path_of, p))
                res[name] = {"value": v} if v is not None else {"status": "not available", "reason": "the API returned no value"}
                break
            except SystemExit as e:
                reason, perm = classify(e, env, permission)
                res[name] = {"status": "not available", "reason": reason}
                if perm:
                    denied = reason
                    break
    return res


def fetch_instagram(root: Path, ep: str, env: dict, at: dt.datetime | None = None) -> dict:
    w = wdir(root, ep)
    post = read_json(w / "post.json")
    if not post or not post.get("media_id"):
        return {"status": "skipped", "reason": "not posted on Instagram"}
    route = ig.publish_env(env)                 # the Page token on graph.facebook.com when IG_PUBLISH_TOKEN is set (the route Reels were published on)
    if not route.get("IG_ACCESS_TOKEN"):
        return {"status": "skipped", "reason": "no Instagram token"}
    stamp = now_iso(at)
    fresh = _insights(lambda path, p: ig.api(route, "GET", path, p), f"{post['media_id']}/insights", IG_METRICS, env, IG_PERMISSION,
                      IG_TOTAL_VALUE, {"views": IG_VIEWS_FALLBACK})
    old = (read_json(w / "insights-instagram.json") or {}).get("metrics") or {}
    out = {"episode": ep, "platform": "instagram", "fetched_at": stamp, "metrics": merge_metrics(old, fresh, stamp)}
    write_checked(w / "insights-instagram.json", out, env_secrets(env))
    got = sum("value" in x for x in fresh.values())
    first_bad = next((x["reason"] for x in fresh.values() if "reason" in x), None)
    return {"status": "ok" if got else "no-insights", "values": got, "reason": first_bad}


def fetch_facebook(root: Path, ep: str, env: dict, at: dt.datetime | None = None) -> dict:
    w = wdir(root, ep)
    rec = read_json(w / "facebook.json") or (read_json(w / "post.json") or {}).get("facebook") or {}
    if not rec.get("video_id"):
        return {"status": "skipped", "reason": "not posted on Facebook"}
    if not env.get("FB_PAGE_TOKEN"):
        return {"status": "skipped", "reason": "no Facebook Page token"}
    import fb
    stamp = now_iso(at)
    fresh = _insights(lambda path, p: fb.api(env, "GET", path, p), f"{rec['video_id']}/video_insights", FB_METRICS, env, FB_PERMISSION)
    old = (read_json(w / "insights-facebook.json") or {}).get("metrics") or {}
    out = {"episode": ep, "platform": "facebook", "fetched_at": stamp, "metrics": merge_metrics(old, fresh, stamp)}
    write_checked(w / "insights-facebook.json", out, env_secrets(env))
    got = sum("value" in x for x in fresh.values())
    first_bad = next((x["reason"] for x in fresh.values() if "reason" in x), None)
    return {"status": "ok" if got else "no-insights", "values": got, "reason": first_bad}


# ------------------------------------------------------------------ YouTube
def yt_secrets(tok: dict) -> list[str]:
    return [str(tok[k]) for k in YT_SECRET_FIELDS if tok.get(k)]


def yt_redact(text, tok: dict) -> str:
    s = str(text)
    for v in yt_secrets(tok):
        s = s.replace(v, "[REDACTED]")
    return re.sub(r"((?:access_token|refresh_token|client_secret|key)=)[^&\s\"']+", r"\1[REDACTED]", s)


def yt_access_token(tok: dict, http) -> str:
    body = urllib.parse.urlencode({"client_id": tok["client_id"], "client_secret": tok["client_secret"], "refresh_token": tok["refresh_token"], "grant_type": "refresh_token"}).encode()
    r = http("POST", tok.get("token_uri") or YT_TOKEN_URI, {"Content-Type": "application/x-www-form-urlencoded"}, body)
    if not r.get("access_token"):
        raise RuntimeError("the OAuth refresh answered without an access token")
    return r["access_token"]


def fetch_youtube(root: Path, eps: list[str] | None = None, token_file: Path | None = None, http=None, at: dt.datetime | None = None) -> dict:
    """One videos.list call (part=statistics) for every episode with a youtube.json video id. Writes metrics-youtube.json per episode."""
    http = http or ig._http
    tf = Path(token_file or YT_TOKEN_FILE)
    tok = read_json(tf, {}) or {}
    ids: dict[str, str] = {}
    for ep in (eps if eps is not None else episodes(root)):
        r = read_json(wdir(root, ep) / "youtube.json")
        if isinstance(r, dict) and r.get("video_id"):
            ids[ep] = r["video_id"]
    if not ids:
        return {"status": "skipped", "reason": "no episode is on YouTube"}
    if not (tok.get("refresh_token") and tok.get("client_id") and tok.get("client_secret")):
        return {"status": "skipped", "reason": "no YouTube token file (SW_YT_TOKEN)"}
    stamp = now_iso(at)
    try:
        access = yt_access_token(tok, http)
        resp = http("GET", f"{YT_VIDEOS_URL}?" + urllib.parse.urlencode({"part": "statistics", "id": ",".join(sorted(set(ids.values()))), "maxResults": 50}),
                    {"Authorization": f"Bearer {access}"}, None)
    except Exception as e:     # noqa: BLE001  any failure: redacted, recorded, the old numbers stay with their old time
        reason = yt_redact(re.sub(r"\s+", " ", f"{type(e).__name__}: {e}"), tok)[:240]
        for ep in ids:
            p = wdir(root, ep) / "metrics-youtube.json"
            old = read_json(p) or {}
            write_checked(p, {**old, "episode": ep, "video_id": ids[ep], "error": reason, "error_at": stamp}, yt_secrets(tok))
        return {"status": "error", "reason": reason}
    stats = {it.get("id"): it.get("statistics") or {} for it in (resp.get("items") or [])}
    done = 0
    for ep, vid in ids.items():
        p = wdir(root, ep) / "metrics-youtube.json"
        st = stats.get(vid)
        if st is None:
            old = read_json(p) or {}
            write_checked(p, {**old, "episode": ep, "video_id": vid, "error": "videos.list returned no item for this video id", "error_at": stamp}, yt_secrets(tok))
            continue
        num = lambda k: int(st[k]) if str(st.get(k, "")).isdigit() else None      # noqa: E731  hidden like counts come back absent: None, never 0
        write_checked(p, {"episode": ep, "video_id": vid, "fetched_at": stamp, "views": num("viewCount"), "likes": num("likeCount"), "comments": num("commentCount")}, yt_secrets(tok))
        done += 1
    return {"status": "ok" if done else "error", "videos": done}


# ------------------------------------------------------------------ everything
def refresh_all(root: Path = ROOT, env: dict | None = None, at: dt.datetime | None = None, http=None, token_file: Path | None = None) -> dict:
    """Never raises: each platform and each episode is independent. Returns {platform: result}."""
    root = Path(root)
    try:
        env = env if env is not None else ig.load_env()
    except Exception:     # noqa: BLE001
        env = {}
    out: dict = {}
    try:
        out["youtube"] = fetch_youtube(root, token_file=token_file, http=http, at=at)
    except BaseException as e:     # noqa: BLE001
        out["youtube"] = {"status": "error", "reason": str(e)[:200]}
    for name, fn in (("instagram", fetch_instagram), ("facebook", fetch_facebook)):
        res: dict = {}
        for ep in episodes(root):
            try:
                r = fn(root, ep, env, at)
            except BaseException as e:     # noqa: BLE001
                r = {"status": "error", "reason": ig.redact(str(e), env)[:200]}
            if r.get("status") != "skipped":
                res[ep] = r
        out[name] = res or {"status": "skipped", "reason": "nothing posted"}
    return out


def summary_line(res: dict) -> str:
    parts = []
    for pf, r in res.items():
        if "status" in r and not isinstance(next(iter(r.values()), None), dict):
            parts.append(f"{pf}: {r['status']}" + (f" ({r['reason']})" if r.get("reason") else ""))
        else:
            bits = [f"{ep} {x['status']}" + (f" ({x['reason']})" if x.get("reason") else "") for ep, x in r.items()]
            parts.append(f"{pf}: " + "; ".join(bits))
    return " | ".join(parts)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="live_numbers.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", default=str(ROOT))
    a = ap.parse_args(argv)
    res = refresh_all(Path(a.root))
    print(summary_line(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
