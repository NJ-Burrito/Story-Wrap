"""The Monitor feed (tools/monitor_board.py): one tab per platform. No network, no real credentials, no model call; every input is a fake file in a temp repo."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import engage
import ig_board
import inbox
import monitor_board as mb

START = datetime(2026, 10, 26, 17, 9, 25, tzinfo=timezone.utc)       # 20:09:25 Amman
NOW = START + timedelta(hours=2)
SECRET = "EAAsecrettoken123456789"
PAGE = "9988776655"


def wj(p, d):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def stamp(t):
    return t.strftime("%Y-%m-%dT%H:%M:%S+0000")


def jl(p, rows):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


@pytest.fixture
def repo(tmp_path):
    w = tmp_path / "work" / "episodes" / "E01"
    wj(w / "post.json", {"episode": "E01", "media_id": "M1", "permalink": "https://www.instagram.com/reel/AbC/", "posted_at": START.isoformat(), "username": "story_account"})
    wj(w / "facebook.json", {"episode": "E01", "video_id": "V1", "permalink": "https://www.facebook.com/reel/V1/", "state": "scheduled", "posted_at": START.isoformat(),
                             "publish_at": (START + timedelta(hours=1)).isoformat()})
    wj(w / "youtube.json", {"episode": "E01", "video_id": "Y1", "url": "https://www.youtube.com/shorts/Y1", "state": "uploaded", "upload_status": "uploaded", "posted_at": START.isoformat()})
    wj(w / "metrics.json", {"episode": "E01", "fetched_at": "2026-10-26T18:19:16+00:00", "likes": 5, "comments": 5})
    wj(w / "metrics-facebook.json", {"episode": "E01", "fetched_at": "2026-10-26T18:19:16+00:00", "likes": 0, "comments": 0})
    wj(w / "stories.json", {"episode": "E01", "items": {"announce:instagram": {"kind": "announce", "platform": "instagram", "state": "published", "at": "2026-10-26T17:11:08+00:00"},
                                                       "announce:facebook": {"kind": "announce", "platform": "facebook", "state": "published", "at": "2026-10-26T18:13:50+00:00"}}})
    (tmp_path / "board" / "data").mkdir(parents=True)
    return tmp_path


def c(pf, mid, text, h, thread, parent="", name=None, own=False):
    return inbox.row("reply" if parent else "comment", pf, "StoryPage", thread, "", mid, parent, name or f"user{mid}", f"u{mid}", own, stamp(START + timedelta(hours=h)), text)


def build(repo, now=NOW, **kw):
    return mb.build(repo, now, env=kw.pop("env", {"FB_PAGE_ID": PAGE}), **kw)


# ------------------------------------------------------------------ links, times, window
def test_each_platform_has_a_tab_with_the_live_link_and_amman_time(repo):
    d = build(repo)
    assert list(d["platforms"]) == ["instagram", "facebook", "youtube"]
    ig, fb, yt = (d["platforms"][k]["posts"][0] for k in ("instagram", "facebook", "youtube"))
    assert ig["url"] == "https://www.instagram.com/reel/AbC/" and fb["url"] == "https://www.facebook.com/reel/V1/" and yt["url"] == "https://www.youtube.com/shorts/Y1"
    assert ig["posted"]["hms"] == "20:09:25" and ig["posted"]["date"] == "2026-10-26"
    assert fb["posted"]["hms"] == "21:09:25"                     # the Facebook Reel goes live an hour later
    assert d["platforms"]["instagram"]["link"] == "https://www.instagram.com/story_account/"
    assert d["platforms"]["facebook"]["link"] == f"https://www.facebook.com/{PAGE}"
    assert d["platforms"]["youtube"]["link"].endswith("YOUR_CHANNEL_ID")


def test_window_open_with_time_left_then_closed_and_not_live_yet(repo):
    ig = build(repo)["platforms"]["instagram"]["posts"][0]["window"]
    assert ig["open"] and ig["state"] == "open" and ig["left_min"] == 70 * 60 and ig["end"]["hms"] == "20:09:25"
    late = build(repo, now=START + timedelta(hours=73))["platforms"]["instagram"]["posts"][0]["window"]
    assert not late["open"] and late["state"] == "closed" and late["left_min"] == 0
    early = build(repo, now=START + timedelta(minutes=20))["platforms"]["facebook"]["posts"][0]["window"]
    assert early["state"] == "not live yet" and early["starts_in_min"] == 40 and not early["open"]


def test_without_a_page_id_facebook_has_no_link_and_says_why(repo):
    d = build(repo, env={})["platforms"]["facebook"]
    assert d["link"] is None and "FB_PAGE_ID" in d["link_note"]


def test_newest_post_first(repo):
    w = repo / "work" / "episodes" / "E02"
    wj(w / "post.json", {"episode": "E02", "media_id": "M2", "permalink": "https://www.instagram.com/reel/Two/", "posted_at": (START + timedelta(days=1)).isoformat()})
    eps = [p["episode"] for p in build(repo, now=START + timedelta(days=1, hours=1))["platforms"]["instagram"]["posts"]]
    assert eps == ["E02", "E01"]


# ------------------------------------------------------------------ numbers: real, or not available with a reason, never a made-up 0
def by_key(post):
    return {m["key"]: m for m in post["metrics"]}


def test_missing_numbers_say_not_available_with_the_reason(repo):
    ig = by_key(build(repo)["platforms"]["instagram"]["posts"][0])
    assert ig["likes"]["value"] == 5 and ig["comments"]["value"] == 5
    for k in ("views", "reach", "shares", "saves", "watch"):
        assert "value" not in ig[k] and "not fetched yet" in ig[k]["na"]
    fb = by_key(build(repo)["platforms"]["facebook"]["posts"][0])
    assert fb["likes"]["value"] == 0                              # a measured zero stays a zero
    assert "value" not in fb["shares"] and "shares" in fb["shares"]["na"]


def test_audience_review_numbers_fill_in_and_unavailable_ones_keep_their_reason(repo):
    wj(repo / "work" / "episodes" / "E01" / "learn" / "metrics.json", {
        "instagram": {"views": {"value": 1200}, "reach": {"value": 900}, "shares": {"value": 7}, "saved": {"value": 11},
                      "ig_reels_avg_watch_time": {"value": 8500}, "plays": {"status": "not available", "reason": "metric plays is deprecated"}},
        "facebook": {"total_video_views": {"value": 300}, "total_video_avg_time_watched": {"status": "not available", "reason": "needs read_insights"}}})
    d = build(repo)["platforms"]
    ig, fb = by_key(d["instagram"]["posts"][0]), by_key(d["facebook"]["posts"][0])
    assert ig["views"]["value"] == 1200 and ig["shares"]["value"] == 7 and ig["saves"]["value"] == 11 and ig["watch"]["value"] == 8.5
    assert fb["views"]["value"] == 300 and fb["watch"]["na"] == "needs read_insights"
    assert by_key({"metrics": d["instagram"]["metrics"]})["views"]["value"] == 1200


def yt_detail(root, **over):
    d = {"video_id": "Y1", "episode": "E01", "as_of": None, "fetched_at": "2026-10-26T17:37:35+00:00", "data_api": {"viewCount": 2, "likeCount": 1, "commentCount": 0},
         "totals": {"views": 0, "estimatedMinutesWatched": 0, "averageViewPercentage": 0, "likes": 0, "comments": 0, "shares": 0}, "retention": []}
    d.update(over)
    wj(root / "work" / "perf" / "youtube" / "Y1.json", d)


def test_youtube_analytics_lag_is_not_shown_as_zero(repo):
    yt_detail(repo)
    m = by_key(build(repo)["platforms"]["youtube"]["posts"][0])
    assert m["views"]["value"] == 2 and "Data API" in m["views"]["note"]
    assert m["likes"]["value"] == 1
    for k in ("shares", "watch", "retention"):
        assert "value" not in m[k] and "lags 1-2 days" in m[k]["na"]
    assert "lags" in build(repo)["platforms"]["youtube"]["posts"][0]["retention_curve_na"]


def test_youtube_real_analytics_and_retention_curve(repo):
    yt_detail(repo, as_of="2026-10-27", totals={"views": 40, "estimatedMinutesWatched": 12.5, "averageViewPercentage": 61.2, "likes": 3, "comments": 1, "shares": 2},
              data_api={"viewCount": 41}, retention=[{"elapsedVideoTimeRatio": 0.1, "audienceWatchRatio": 0.9}, {"elapsedVideoTimeRatio": 0.2, "audienceWatchRatio": 0.7}])
    p = build(repo)["platforms"]["youtube"]["posts"][0]
    m = by_key(p)
    assert m["views"]["value"] == 40 and m["watch"]["value"] == 12.5 and m["retention"]["value"] == 61.2 and m["shares"]["value"] == 2
    assert p["retention_curve"] == [0.9, 0.7]


def test_youtube_without_any_fetch_says_so(repo):
    m = by_key(build(repo)["platforms"]["youtube"]["posts"][0])
    assert all("value" not in x and "yt_perf.py fetch" in x["na"] for x in m.values())


# ------------------------------------------------------------------ comments, replies, drafts, stories
def seed_threads(repo):
    rows = [c("instagram", "c1", "متى الحلقة القادمة؟", 1, "M1", name="sara"),
            c("instagram", "c2", "هههه حقيبة هدى", 2, "M1", name="omar"),
            c("instagram", "r1", "قريبا", 3, "M1", parent="c1", name="story_account", own=True),
            c("facebook", "f1", "قصة جميلة", 2, "555_V1", name="lina"),
            c("youtube", "y1", "ممتاز", 2, "Y1", name="yuser"),
            c("instagram", "other", "not ours", 1, "M999", name="x")]
    jl(repo / "work" / "inbox" / "inbox.jsonl", rows)
    items = {"instagram:c2": {"platform": "instagram", "episode": "E01", "kind": "joke", "status": "drafted", "reply": "ههه صح 😂", "not_before": stamp(NOW + timedelta(minutes=30)), "excerpt": "هههه حقيبة هدى", "dm": False},
             "instagram:c1": {"platform": "instagram", "episode": "E01", "kind": "question", "status": "sent", "dm": False},
             "facebook:f1": {"platform": "facebook", "episode": "E01", "kind": "praise", "status": "skip", "reason": "random: not every compliment", "dm": False}}
    wj(repo / "work" / "engage" / "state.json", {"items": items, "halt": {"youtube": stamp(NOW + timedelta(hours=5))}, "failures": {}, "metrics_at": {}})
    jl(repo / "work" / "engage" / "sent.jsonl", [{"at": stamp(NOW), "platform": "instagram", "channel": "instagram", "episode": "E01", "kind": "question", "item_id": "c1", "thread": "c1",
                                                  "reply_id": "rX", "text": "قريبا جدا ⏳"}])


def test_comment_threads_replies_and_our_sent_reply(repo):
    seed_threads(repo)
    p = build(repo)["platforms"]["instagram"]["posts"][0]
    assert p["comments_total"] == 2 and [x["id"] for x in p["comments"]] == ["c2", "c1"]       # newest first, the other post's comment is not here
    c1 = p["comments"][1]
    assert c1["status"] == "sent" and c1["kind"] == "question"
    assert c1["replies"][0]["own"] and c1["replies"][0]["text"] == "قريبا"
    assert c1["sent"][0]["text"] == "قريبا جدا ⏳"                                              # engage's own record, shown with the thread
    assert len(p["sent"]) == 1 and p["sent"][0]["when"]["hms"] == "22:09:25"


def test_drafts_waiting_and_other_platforms_stay_apart(repo):
    seed_threads(repo)
    d = build(repo)["platforms"]
    dr = d["instagram"]["posts"][0]["drafts"]
    assert len(dr) == 1 and dr[0]["text"] == "ههه صح 😂" and dr[0]["not_before"]["hms"] == "22:39:25" and dr[0]["to"] == "هههه حقيبة هدى"
    assert d["facebook"]["posts"][0]["drafts"] == [] and d["facebook"]["posts"][0]["comments"][0]["status"] == "skip"
    assert d["youtube"]["posts"][0]["comments"][0]["text"] == "ممتاز"
    assert d["youtube"]["totals"]["halted_until"]["hms"]
    assert d["instagram"]["totals"]["drafts"] == 1 and d["instagram"]["totals"]["replies_sent"] == 1


def test_instagram_falls_back_to_the_vote_harvest_comments(repo):
    wj(repo / "work" / "episodes" / "E01" / "comments.json", {"comments": [{"id": "h1", "username": "ali", "text": "نفتح الحقيبة", "timestamp": "2026-10-26T18:00:00+0000"}]})
    p = build(repo)["platforms"]["instagram"]["posts"][0]
    assert p["comments_total"] == 1 and p["comments"][0]["who"] == "ali" and p["comments_reported"] == 5


def test_stories_belong_to_their_platform(repo):
    d = build(repo)["platforms"]
    assert d["instagram"]["posts"][0]["stories"][0]["when"]["hms"] == "20:11:08"
    assert d["facebook"]["posts"][0]["stories"][0]["when"]["hms"] == "21:13:50"
    assert d["youtube"]["posts"][0]["stories"] == [] and "no stories" in d["youtube"]["stories_note"]


# ------------------------------------------------------------------ DMs
def test_dms_grouped_with_waiting_flag_and_reply_window(repo):
    dm = lambda mid, h, text, own=False: inbox.row("dm", "instagram", "StoryPage", "conv1", "", mid, "", "fan" if not own else "StoryPage", "u1", own, stamp(START + timedelta(hours=h)), text)   # noqa: E731
    jl(repo / "work" / "inbox" / "inbox.jsonl", [dm("d1", 1, "واو شو حلو"), dm("d2", 1.5, "شكرا", own=True), dm("d3", 2, "متى الحلقة؟")])
    wj(repo / "work" / "inbox" / "state.json", {"sources": {"instagram_dm": {"status": "ok", "last_ok": stamp(NOW)}, "facebook_dm": {"status": "FAIL", "error": "permission pages_messaging missing"}}})
    d = build(repo)["platforms"]
    t = d["instagram"]["dms"]["threads"][0]
    assert t["count"] == 3 and t["unanswered"] and t["last"] == "متى الحلقة؟" and t["reply_open_until"]["hms"] == "22:09:25"
    assert d["instagram"]["totals"]["dms_unanswered"] == 1
    assert d["facebook"]["dms"]["source"]["status"] == "FAIL" and "pages_messaging" in d["facebook"]["dms"]["source"]["error"]
    assert d["youtube"]["dms"]["note"] == "YouTube has no direct messages"
    assert build(repo, now=START + timedelta(hours=30))["platforms"]["instagram"]["dms"]["threads"][0]["reply_open_until"] is None      # past Meta's 24 h


# ------------------------------------------------------------------ trend history
def test_per_metric_delta_and_sparkline_since_the_last_reading(repo):
    d1 = mb.write(repo, NOW, env={})
    m1 = by_key(d1["platforms"]["instagram"]["posts"][0])["likes"]
    assert m1["delta"] is None and m1["points"] == [5]
    wj(repo / "work" / "episodes" / "E01" / "metrics.json", {"fetched_at": stamp(NOW), "likes": 9, "comments": 6})
    d2 = mb.write(repo, NOW + timedelta(minutes=15), env={})
    ig = by_key(d2["platforms"]["instagram"]["posts"][0])
    assert ig["likes"]["delta"] == 4 and ig["comments"]["delta"] == 1 and ig["likes"]["points"] == [5, 9]
    assert ig["likes"]["since"]["hms"] == NOW.astimezone(mb.AMMAN).strftime("%H:%M:%S")
    assert ig["views"]["delta"] is None and "na" in ig["views"]          # a metric with no number has no trend and keeps its reason
    plat = by_key({"metrics": d2["platforms"]["instagram"]["metrics"]})
    assert plat["likes"]["value"] == 9 and plat["likes"]["delta"] == 4                              # the platform level has its own history
    assert by_key({"metrics": d2["all"]["metrics"]})["likes"]["value"] == 9


def test_all_platforms_level_adds_the_platforms_and_skips_unique_reach(repo):
    yt_detail(repo, as_of="2026-10-27", totals={"views": 40, "estimatedMinutesWatched": 1, "averageViewPercentage": 50, "likes": 3, "comments": 1, "shares": 2, "subscribersGained": 4},
              data_api={"viewCount": 41})
    d = build(repo)
    a = by_key({"metrics": d["all"]["metrics"]})
    assert a["likes"]["value"] == 5 + 0 + 3 and a["comments"]["value"] == 5 + 0 + 1 and a["views"]["value"] == 40 and a["follows"]["value"] == 4
    assert "reach" not in a and "watch" not in a
    assert by_key(d["platforms"]["youtube"]["posts"][0])["follows"]["value"] == 4
    assert set(by_key(d["platforms"]["instagram"]["posts"][0])) == set(mb.NUMERIC_KEYS)             # every post shows the same nine metrics


def test_the_trend_gets_one_point_per_refresh_and_never_a_duplicate(repo):
    hp = repo / "work" / "monitor" / "history.jsonl"
    count = lambda: len(hp.read_text(encoding="utf-8").splitlines())      # noqa: E731
    mb.write(repo, NOW, env={})
    n = count()
    mb.write(repo, NOW, env={})                                  # the same refresh again: nothing new
    assert count() == n
    mb.write(repo, NOW + timedelta(minutes=3), env={})           # too soon and nothing moved
    assert count() == n
    mb.write(repo, NOW + timedelta(minutes=15), env={})          # the next 15 min refresh: one point per key
    assert count() == n * 2


# ------------------------------------------------------------------ thumbnails and post details
def test_details_show_caption_without_tashkeel_and_dashes(repo):
    wj(repo / "work" / "episodes" / "E01" / "post.json", {"episode": "E01", "media_id": "M1", "permalink": "https://i/x", "posted_at": START.isoformat(), "caption": "الـمَكْتَبُ — الحلقة"})
    p = build(repo)["platforms"]["instagram"]["posts"][0]
    assert p["caption"] == "المكتب - الحلقة" and p["title"] is None
    assert build(repo)["platforms"]["youtube"]["posts"][0]["thumb"]["src"] is None                  # no still yet: the page shows a placeholder


def test_thumbnail_uses_a_platform_url_when_a_writer_kept_one_else_the_local_frame(repo):
    (repo / "board" / "data" / "thumbs").mkdir()
    (repo / "board" / "data" / "thumbs" / "E01.jpg").write_bytes(b"\xff\xd8x")
    wj(repo / "board" / "data" / "thumbs" / "E01.json", {"duration_s": 127.5})
    p = build(repo)["platforms"]["instagram"]["posts"][0]
    assert p["thumb"] == {"src": "data/thumbs/E01.jpg", "local": "data/thumbs/E01.jpg", "source": "frame of episode.mp4"} and p["duration_s"] == 127.5
    wj(repo / "work" / "episodes" / "E01" / "youtube.json", {"episode": "E01", "video_id": "Y1", "state": "uploaded", "upload_status": "uploaded", "posted_at": START.isoformat(),
                                                           "thumbnail_url": "https://i.ytimg.com/vi/Y1/maxresdefault.jpg"})
    t = build(repo)["platforms"]["youtube"]["posts"][0]["thumb"]
    assert t["src"].startswith("https://i.ytimg.com") and t["local"] == "data/thumbs/E01.jpg" and t["source"] == "platform"


def test_a_frame_is_grabbed_from_episode_mp4_with_ffmpeg(repo, monkeypatch):
    (repo / "work" / "episodes" / "E01" / "episode.mp4").write_bytes(b"x")
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd[0])
        if "-frames:v" in cmd:
            Path(cmd[-1]).write_bytes(b"\xff\xd8jpg")

        class R:
            stdout = "42.5\n"
        return R()
    monkeypatch.setattr(mb.shutil, "which", lambda n: n)
    monkeypatch.setattr(mb.subprocess, "run", fake_run)
    mb.make_thumb(repo, "E01")
    assert (repo / "board" / "data" / "thumbs" / "E01.jpg").read_bytes().startswith(b"\xff\xd8")
    assert json.loads((repo / "board" / "data" / "thumbs" / "E01.json").read_text(encoding="utf-8"))["duration_s"] == 42.5
    n = len(calls)
    mb.make_thumb(repo, "E01")                                                                       # up to date: ffmpeg is not run again
    assert len(calls) == n


# ------------------------------------------------------------------ notes
def test_notes_are_saved_listed_and_marked_picked_up(repo):
    n1 = mb.add_note(repo, "instagram", "E01", "الغلاف غامق جدا <b>x</b>", NOW)
    n2 = mb.add_note(repo, "all", "general", "note two", NOW + timedelta(minutes=1))
    d = build(repo)
    assert [n["id"] for n in d["notes"]] == [n2["id"], n1["id"]] and d["summary"]["notes_waiting"] == 2
    assert d["notes"][1]["text"] == "الغلاف غامق جدا <b>x</b>"                                       # stored as typed; the page escapes it
    mb.mark_picked(repo, n1["id"], NOW + timedelta(hours=1))
    d = build(repo)
    assert [n["picked_up"] for n in d["notes"]] == [False, True] and d["notes"][1]["picked_when"]["hms"] == "23:09:25" and d["summary"]["notes_waiting"] == 1
    with pytest.raises(ValueError):
        mb.mark_picked(repo, "nope")
    assert len((repo / "work" / "board" / "notes.jsonl").read_text(encoding="utf-8").splitlines()) == 3


@pytest.mark.parametrize("args,frag", [(("tiktok", "E01", "hi"), "platform"), (("instagram", "../x", "hi"), "post id"), (("instagram", "E01", "   "), "empty"),
                                      (("instagram", "E01", "x" * 2001), "longer"), (("instagram", "E01", "my key EAAB" + "a" * 30), "token"),
                                      (("instagram", "E01", "use " + SECRET), "token")])
def test_bad_notes_are_refused(repo, args, frag):
    with pytest.raises(ValueError, match=frag):
        mb.add_note(repo, *args, env={"IG_ACCESS_TOKEN": SECRET})
    assert not mb.notes_path(repo).exists()


def test_notes_cli_lists_pending_and_picks(repo, capsys):
    n = mb.add_note(repo, "facebook", "general", "hello", NOW)
    assert mb.main(["--root", str(repo), "notes", "--pending"]) == 0 and "WAITING" in capsys.readouterr().out
    assert mb.main(["--root", str(repo), "pick", n["id"]]) == 0
    mb.main(["--root", str(repo), "notes", "--pending"])
    assert "hello" not in capsys.readouterr().out


def test_board_server_note_endpoint_is_token_guarded_and_writes_the_file(repo, monkeypatch):
    import http.client
    import threading
    from http.server import ThreadingHTTPServer
    import importlib.util
    spec = importlib.util.spec_from_file_location("sw_board_serve", Path(mb.__file__).parents[1] / "board" / "serve.py")
    serve = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(serve)
    monkeypatch.setattr(serve, "ROOT", repo)
    monkeypatch.setattr(mb, "load_env_safe", lambda: {})
    srv = ThreadingHTTPServer(("127.0.0.1", 0), serve.H)
    port = srv.server_address[1]
    monkeypatch.setattr(serve, "PORT", port)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        def post(token, body):
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            h = {"Content-Type": "application/json", **({"X-Board-Token": token} if token else {})}
            c.request("POST", "/api/note", json.dumps(body), h)
            r = c.getresponse()
            return r.status, json.loads(r.read())
        assert post(None, {"platform": "instagram", "post": "E01", "text": "hi"})[0] == 403
        assert not mb.notes_path(repo).exists()
        st, j = post(serve.TOKEN, {"platform": "instagram", "post": "E01", "text": "ملاحظة"})
        assert st == 200 and j["ok"]
        assert mb.read_notes(repo)[0]["text"] == "ملاحظة"
        st, j = post(serve.TOKEN, {"platform": "instagram", "post": "E01", "text": ""})
        assert st == 400 and not j["ok"]
    finally:
        srv.shutdown()
        srv.server_close()


# ------------------------------------------------------------------ files, secrets, read only
def test_write_makes_json_and_js_and_never_a_token(repo):
    mb.write(repo, NOW, env={"FB_PAGE_ID": PAGE, "IG_ACCESS_TOKEN": SECRET})
    js = (repo / "board" / "data" / "monitor.js").read_text(encoding="utf-8")
    assert js.startswith("window.__MONITOR__ = ") and json.loads((repo / "board" / "data" / "monitor.json").read_text(encoding="utf-8"))["platforms"]
    assert SECRET not in js


def test_a_credential_in_the_data_refuses_the_write(repo):
    wj(repo / "work" / "episodes" / "E01" / "post.json", {"episode": "E01", "media_id": "M1", "permalink": "https://x/" + SECRET, "posted_at": START.isoformat()})
    with pytest.raises(SystemExit, match="MONITOR-LEAK"):
        mb.write(repo, NOW, env={"IG_ACCESS_TOKEN": SECRET})
    assert not (repo / "board" / "data" / "monitor.json").exists()


def test_ig_board_refresh_writes_the_monitor_and_a_monitor_fault_never_stops_it(repo, monkeypatch):
    (repo / "work" / "daily").mkdir(parents=True, exist_ok=True)
    ig_board.write_all(repo, dt_now(), env={"IG_USER_ID": "1", "IG_ACCESS_TOKEN": SECRET})
    assert (repo / "board" / "data" / "monitor.json").is_file() and (repo / "board" / "data" / "board.json").is_file()
    monkeypatch.setattr(mb, "write", lambda *a, **k: (_ for _ in ()).throw(SystemExit("MONITOR-LEAK")))
    ig_board.write_all(repo, dt_now(), env={"IG_USER_ID": "1", "IG_ACCESS_TOKEN": SECRET})          # no exception


def dt_now():
    from datetime import datetime as D
    return D(2026, 10, 26, 23, 0)


def test_the_module_has_no_send_or_post_path():
    src = (Path(mb.__file__)).read_text(encoding="utf-8")
    code = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
    for banned in ("cmd_reply", "cmd_publish", "send_instagram", "send_facebook", "send_youtube", "urllib", "requests", "SENDERS", "append_jsonl", "comments.insert"):
        assert banned not in code, banned


# ------------------------------------------------------------------ the page
def test_page_has_a_tab_per_platform_notes_and_no_cairo():
    html = (Path(mb.__file__).parents[1] / "board" / "index.html").read_text(encoding="utf-8")
    assert '["all", "📊 All platforms"]' in html and '["instagram", "📸 Instagram"]' in html and '["posts", "Posts"]' not in html and '["engage", "Engage"]' not in html
    assert "function platformPage" in html and "function engageCards" in html and "comments()}" in html      # Posts, Comments and Engage live inside the platform tabs
    assert "/api/note" in html and "esc(n.text)" in html
    assert all(k in html for k in ("instagram", "facebook", "youtube", "data/monitor"))
    assert "Cairo" not in html and "—" not in html                                   # Thmanyah only; no em dashes
