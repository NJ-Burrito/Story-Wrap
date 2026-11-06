# /// script
# requires-python = ">=3.10"
# dependencies = ["google-api-python-client", "google-auth"]
# ///
"""YouTube performance for Story-Wrap: every video on our channel, from the OFFICIAL YouTube Analytics API v2 and Data API v3 (no Studio scraping).

    uv run tools/yt_perf.py fetch [--days N]   every video on the channel (uploads playlist) -> work/perf/youtube/ (git-ignored)
    uv run tools/yt_perf.py status             token scopes, last fetch time, row count (no network)

Output (repo = SW_REPO or this checkout):
    work/perf/youtube/videos.csv        one row per video, newest first, UTF-8 with BOM (opens in Excel with Arabic intact)
    work/perf/youtube/<video_id>.json   full detail: totals, retention curve (audienceWatchRatio by elapsedVideoTimeRatio), traffic sources, top 10 countries, Shorts split
    work/perf/youtube/summary.json      counts, sums, as_of, fetched_at, per-video one-liners

Analytics data lags about 1-2 days: `as_of` is the last day the Analytics API returned data for the channel (measured), `fetched_at` is when we asked. A metric or breakdown the
API refuses is recorded as {"status": "not available", "reason": ...} and never blocks the others. Credentials are never printed or written (`yt.redact`).

Feeds the existing loops without changing them: `learn_stats(ep, root)` returns the perf file of an episode in learn.py's metric shape ({name: {"value": n}}) and
`board_row(ep, root)` a small dict for ig_board's YouTube row; both return None when no fetch has happened.
Needs the token scopes yt-analytics.readonly + youtube.readonly (token ~/.config/story-wrap/youtube-token.json, override SW_YT_TOKEN).
"""
import argparse
import csv
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import yt   # noqa: E402
from ig import REPO, fail, now, read_json, write_json   # noqa: E402

OUT_SUB = ("work", "perf", "youtube")
SCOPE_ANALYTICS = "https://www.googleapis.com/auth/yt-analytics.readonly"
SCOPE_READ = "https://www.googleapis.com/auth/youtube.readonly"
TOTAL_METRICS = ("views", "engagedViews", "estimatedMinutesWatched", "averageViewDuration", "averageViewPercentage", "likes", "dislikes", "comments", "shares",
                 "subscribersGained", "subscribersLost")
CSV_COLUMNS = ("video_id", "episode", "title", "published_at", "privacy", "duration_s", "is_short", "url", "window_start", "window_end", *TOTAL_METRICS,
               "data_viewCount", "data_likeCount", "data_commentCount", "top_traffic_source", "top_country", "as_of", "fetched_at")
SHORTS_MAX_S = yt.SHORTS_MAX_S


def out_dir(root: Path = REPO) -> Path:
    return Path(root).joinpath(*OUT_SUB)


# ---------------------------------------------------------------- services (replaced in tests)
def _build(path: Path):
    """(Data API service, Analytics API service) on one credential; refreshes the access token when needed and saves the file back (atomic)."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    creds = Credentials.from_authorized_user_file(str(path))
    if not creds.valid:
        creds.refresh(Request())
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(creds.to_json(), encoding="utf-8")
        os.replace(tmp, path)
    return (build("youtube", "v3", credentials=creds, cache_discovery=False),
            build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False))


def services(path: Path | None = None):
    p = Path(path or yt.TOKEN_FILE)
    tok = yt.load_token(p)
    if not yt.has_token(p):
        fail("YT-CREDS", f"missing or incomplete token file {p} (refresh_token, client_id, client_secret)")
    try:
        return _build(p)
    except Exception as e:     # noqa: BLE001
        fail("YT-AUTH", yt.redact(f"{type(e).__name__}: {e}", tok))


def _na(err, tok=None) -> dict:
    return {"status": "not available", "reason": yt.redact(re.sub(r"\s+", " ", str(err)), tok)[:200]}


# ---------------------------------------------------------------- the channel's videos (Data API)
def iso_seconds(d: str | None) -> int | None:
    m = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", d or "")
    if not m:
        return None
    dd, h, mi, s = (int(x or 0) for x in m.groups())
    return dd * 86400 + h * 3600 + mi * 60 + s


def episode_map(root: Path = REPO) -> dict:
    """{video_id: episode id} from work/episodes/*/youtube.json."""
    out = {}
    wd = Path(root) / "work" / "episodes"
    for d in sorted(wd.glob("*")) if wd.is_dir() else []:
        try:
            r = read_json(d / "youtube.json")
        except ValueError:
            continue
        if isinstance(r, dict) and r.get("video_id"):
            out[r["video_id"]] = d.name
    return out


def list_videos(data, tok=None) -> list:
    """Every video of the channel: uploads playlist (all pages), then videos.list in batches of 50 for snippet, statistics, contentDetails, status."""
    ch = yt.call(lambda: data.channels().list(part="contentDetails", mine=True).execute(), "channels.list", tok)
    items = ch.get("items") or []
    if not items:
        fail("YT-NOCHANNEL", "channels.list(mine) returned no channel")
    uploads = ((items[0].get("contentDetails") or {}).get("relatedPlaylists") or {}).get("uploads")
    if not uploads:
        fail("YT-NOCHANNEL", "the channel has no uploads playlist")
    ids, page = [], None
    while True:
        kw = {"part": "contentDetails", "playlistId": uploads, "maxResults": 50}
        if page:
            kw["pageToken"] = page
        r = yt.call(lambda: data.playlistItems().list(**kw).execute(), "playlistItems.list", tok)
        ids += [(i.get("contentDetails") or {}).get("videoId") for i in r.get("items", [])]
        page = r.get("nextPageToken")
        if not page:
            break
    ids = [i for i in dict.fromkeys(ids) if i]
    vids = []
    for k in range(0, len(ids), 50):
        batch = ids[k:k + 50]
        r = yt.call(lambda: data.videos().list(part="snippet,statistics,contentDetails,status", id=",".join(batch)).execute(), "videos.list", tok)
        vids += r.get("items", [])
    return vids


# ---------------------------------------------------------------- Analytics queries
def _query(an, tok, **kw) -> dict:
    kw.setdefault("ids", "channel==MINE")
    r = yt.call(lambda: an.reports().query(**kw).execute(), "reports.query", tok)
    heads = [h.get("name") for h in r.get("columnHeaders", [])]
    return {"headers": heads, "rows": r.get("rows") or []}


def _num(x):
    return round(x, 6) if isinstance(x, float) else x


def totals(an, tok, vid, start, end) -> dict:
    """The per-video totals. If the whole list is refused, each metric is asked alone so one unsupported metric (engagedViews) does not blank the rest."""
    base = dict(filters=f"video=={vid}", startDate=start, endDate=end)
    try:
        q = _query(an, tok, metrics=",".join(TOTAL_METRICS), **base)
        if q["rows"]:
            return {h: _num(v) for h, v in zip(q["headers"], q["rows"][0])}
        return {m: 0 for m in TOTAL_METRICS} | {"note": "no rows: no activity in the window"}
    except SystemExit as first:
        out = {"whole_list_error": _na(first, tok)["reason"]}
        if getattr(first, "http_status", None) not in (400, None):
            return out | {m: _na(first, tok) for m in TOTAL_METRICS}      # 401/403/429/5xx: asking each metric alone would fail the same way
        for m in TOTAL_METRICS:
            try:
                q = _query(an, tok, metrics=m, **base)
                out[m] = _num(q["rows"][0][0]) if q["rows"] else 0
            except SystemExit as e:
                out[m] = _na(e, tok)
        return out


def breakdown(an, tok, vid, start, end, dimension, metrics, **extra):
    """[{dimension value, metrics...}] or a not-available dict."""
    try:
        q = _query(an, tok, dimensions=dimension, metrics=metrics, filters=f"video=={vid}", startDate=start, endDate=end, **extra)
        return [{h: _num(v) for h, v in zip(q["headers"], row)} for row in q["rows"]]
    except SystemExit as e:
        return _na(e, tok)


def preflight(an, tok, start, end):
    """(as_of, problem). as_of = the newest `day` with channel data (measured), or None. problem = the API's own readable message when the query is refused (typically 403
    accessNotConfigured: the YouTube Analytics API is not enabled in the Google Cloud project), else None. Called raw (not through yt.call) to keep the error message."""
    try:
        r = an.reports().query(ids="channel==MINE", dimensions="day", metrics="views", startDate=start, endDate=end, sort="-day", maxResults=1).execute()
        rows = r.get("rows") or []
        return (rows[0][0] if rows else None), None
    except Exception as e:     # noqa: BLE001
        msg = ""
        try:
            msg = (json.loads(getattr(e, "content", b"") or b"{}").get("error") or {}).get("message") or ""
        except (ValueError, AttributeError):
            pass
        code = getattr(getattr(e, "resp", None), "status", None)
        return None, yt.redact(f"HTTP {code}: {msg or type(e).__name__}", tok)[:400]


def video_detail(an, tok, v: dict, start: str, end: str, episode: str | None, problem: str | None = None) -> dict:
    vid = v["id"]
    sn, st, cd, status = (v.get(k) or {} for k in ("snippet", "statistics", "contentDetails", "status"))
    secs = iso_seconds(cd.get("duration"))
    detail = {
        "video_id": vid, "episode": episode, "title": sn.get("title"), "published_at": sn.get("publishedAt"), "privacy": status.get("privacyStatus"),
        "duration_s": secs, "is_short": (secs is not None and secs <= SHORTS_MAX_S), "url": f"https://www.youtube.com/{'shorts/' if secs is not None and secs <= SHORTS_MAX_S else 'watch?v='}{vid}",
        "window": {"start": start, "end": end},
        "data_api": {k: int(st[k]) for k in ("viewCount", "likeCount", "commentCount") if str(st.get(k, "")).isdigit()},
    }
    if problem:        # the Analytics API refused the preflight: one clear reason instead of dozens of identical failures; the Data API numbers above still stand
        na = {"status": "not available", "reason": problem}
        detail.update(totals={m: dict(na) for m in TOTAL_METRICS}, retention=na, traffic_sources=na, countries=na, content_type=na)
        return detail
    detail.update(totals=totals(an, tok, vid, start, end),
                  retention=breakdown(an, tok, vid, start, end, "elapsedVideoTimeRatio", "audienceWatchRatio"),
                  traffic_sources=breakdown(an, tok, vid, start, end, "insightTrafficSourceType", "views,estimatedMinutesWatched", sort="-views"),
                  countries=breakdown(an, tok, vid, start, end, "country", "views,estimatedMinutesWatched", sort="-views", maxResults=10),
                  content_type=breakdown(an, tok, vid, start, end, "creatorContentType", "views,estimatedMinutesWatched"))
    return detail


# ---------------------------------------------------------------- fetch
def _first(x, key):
    return x[0].get(key) if isinstance(x, list) and x else None


def csv_row(d: dict, as_of, fetched_at) -> dict:
    t, da = d["totals"], d["data_api"]
    r = {"video_id": d["video_id"], "episode": d["episode"], "title": d["title"], "published_at": d["published_at"], "privacy": d["privacy"], "duration_s": d["duration_s"],
         "is_short": d["is_short"], "url": d["url"], "window_start": d["window"]["start"], "window_end": d["window"]["end"],
         "data_viewCount": da.get("viewCount"), "data_likeCount": da.get("likeCount"), "data_commentCount": da.get("commentCount"),
         "top_traffic_source": _first(d["traffic_sources"], "insightTrafficSourceType"), "top_country": _first(d["countries"], "country"), "as_of": as_of, "fetched_at": fetched_at}
    for m in TOTAL_METRICS:
        x = t.get(m)
        r[m] = "n/a" if isinstance(x, dict) or x is None else x
    return r


def cmd_fetch(days: int = 90, root: Path = REPO, data=None, an=None, at: datetime | None = None) -> dict:
    tok = yt.load_token()
    if data is None or an is None:
        data, an = services()
    cur = at or now()
    end = cur.date()
    start = end - timedelta(days=max(1, days))
    s, e = start.isoformat(), end.isoformat()
    vids = list_videos(data, tok)
    emap = episode_map(root)
    as_of, problem = preflight(an, tok, s, e)
    fetched_at = cur.isoformat(timespec="seconds")
    od = out_dir(root)
    od.mkdir(parents=True, exist_ok=True)
    details = []
    for v in vids:
        d = video_detail(an, tok, v, s, e, emap.get(v["id"]), problem)
        d.update(as_of=as_of, fetched_at=fetched_at)
        details.append(d)
    details.sort(key=lambda d: d.get("published_at") or "", reverse=True)
    rows = [csv_row(d, as_of, fetched_at) for d in details]
    blob = json.dumps({"rows": rows, "details": details}, ensure_ascii=False)
    for sec in yt.secrets_of(tok):
        if sec in blob:
            fail("YT-LEAK", "a credential value appeared in the performance output; nothing written")
    for d in details:
        write_json(od / f"{d['video_id']}.json", d)
    tmp = od / "videos.csv.tmp"
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, od / "videos.csv")
    nums = lambda k: sum(r[k] for r in rows if isinstance(r[k], (int, float)))   # noqa: E731
    summary = {"fetched_at": fetched_at, "as_of": as_of, "as_of_basis": "newest day with channel data in the Analytics API (data lags about 1-2 days)", "window": {"start": s, "end": e, "days": days},
               "analytics_problem": problem, "videos": len(rows), "episodes_mapped": sum(1 for r in rows if r["episode"]), "sums": {m: nums(m) for m in ("views", "estimatedMinutesWatched", "likes", "comments", "shares", "subscribersGained", "subscribersLost")},
               "per_video": [{k: r[k] for k in ("video_id", "episode", "title", "published_at", "privacy", "views", "averageViewPercentage", "likes", "comments", "data_viewCount")} for r in rows]}
    write_json(od / "summary.json", summary)
    if problem:
        print(f"WARNING: YouTube Analytics API refused the channel query ({problem}); only Data API statistics were stored")
    print(f"fetched {len(rows)} videos -> {od} (as_of {as_of}, fetched_at {fetched_at}, window {s}..{e})")
    return summary


# ---------------------------------------------------------------- feeds for learn.py and ig_board.py
def detail_of(ep: str, root: Path = REPO) -> dict | None:
    rec = yt.load_record(ep, root)
    vid = rec.get("video_id") if isinstance(rec, dict) else None
    if not vid:
        return None
    try:
        d = read_json(out_dir(root) / f"{vid}.json")
    except ValueError:
        return None
    return d if isinstance(d, dict) else None


def learn_stats(ep: str, root: Path = REPO) -> dict | None:
    """learn.py's metric shape for the episode's YouTube section: {name: {"value": n}} / {"status": "not available", ...}, plus fetched_at and as_of. None = no fetch yet."""
    d = detail_of(ep, root)
    if not d:
        return None
    out = {}
    for m, x in (d.get("totals") or {}).items():
        if m in TOTAL_METRICS:
            out[m] = x if isinstance(x, dict) and x.get("status") else {"value": x}
    for k, v in (d.get("data_api") or {}).items():
        out[k] = {"value": v}
    out["fetched_at"], out["as_of"] = d.get("fetched_at"), d.get("as_of")
    return out


def country_counts(ep: str, root: Path = REPO) -> dict | None:
    """{country code: views} for learn.py's countries block, or None."""
    d = detail_of(ep, root)
    c = (d or {}).get("countries")
    if not isinstance(c, list) or not c:
        return None
    return {str(r["country"]).upper(): r["views"] for r in c if r.get("country") and isinstance(r.get("views"), (int, float))} or None


def board_row(ep: str, root: Path = REPO) -> dict | None:
    d = detail_of(ep, root)
    if not d:
        return None
    t = d.get("totals") or {}
    pick = lambda k: t.get(k) if not isinstance(t.get(k), dict) else None   # noqa: E731
    return {"views": pick("views"), "averageViewPercentage": pick("averageViewPercentage"), "likes": pick("likes"), "comments": pick("comments"), "shares": pick("shares"),
            "as_of": d.get("as_of"), "fetched_at": d.get("fetched_at")}


# ---------------------------------------------------------------- status
def cmd_status(root: Path = REPO) -> str:
    tok = yt.load_token()
    out = [yt.token_state(tok)]
    scopes = tok.get("scopes") or []
    scopes = scopes.split() if isinstance(scopes, str) else scopes
    for sc in (SCOPE_ANALYTICS, SCOPE_READ):
        out.append(f"scope {sc.rsplit('/', 1)[-1]}: {'yes' if sc in scopes else 'MISSING (authorise once more)'}")
    try:
        sm = read_json(out_dir(root) / "summary.json")
    except ValueError:
        sm = None
    out.append(f"last fetch: {sm['fetched_at']} (as_of {sm.get('as_of')}, {sm.get('videos')} videos)" if isinstance(sm, dict) else f"no fetch yet ({out_dir(root)})")
    s = yt.redact("\n".join(out), tok)
    print(s)
    return s


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="YouTube performance (official Analytics + Data APIs) for Story-Wrap")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("fetch"); p.add_argument("--days", type=int, default=90)
    sub.add_parser("status")
    a = ap.parse_args(argv)
    if a.cmd == "fetch":
        cmd_fetch(a.days)
    else:
        cmd_status()
    return 0


if __name__ == "__main__":
    sys.exit(main())
