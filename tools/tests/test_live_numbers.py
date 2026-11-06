"""tools/live_numbers.py and its use on the board: YouTube statistics, Instagram media insights, Facebook video insights. Fakes only: no network, no real credential."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import ig
import live_numbers as ln
import monitor_board as mb

START = datetime(2026, 10, 27, 5, 0, 0, tzinfo=timezone.utc)
NOW = START + timedelta(hours=2)
SECRET = "EAAsecretpagetoken987654321"
YT_SECRET = "yt-refresh-secret-123456"


def wj(p, d):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d), encoding="utf-8")


def rj(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


@pytest.fixture
def repo(tmp_path):
    w = tmp_path / "work" / "episodes" / "E01"
    wj(w / "post.json", {"episode": "E01", "media_id": "M1", "permalink": "https://www.instagram.com/reel/A/", "posted_at": START.isoformat()})
    wj(w / "facebook.json", {"episode": "E01", "video_id": "V1", "permalink": "https://www.facebook.com/reel/V1/", "state": "published", "posted_at": START.isoformat()})
    wj(w / "youtube.json", {"episode": "E01", "video_id": "Y1", "url": "https://youtu.be/Y1", "state": "uploaded", "posted_at": START.isoformat()})
    wj(w / "metrics.json", {"episode": "E01", "fetched_at": NOW.isoformat(), "likes": 8, "comments": 10})
    wj(w / "metrics-facebook.json", {"episode": "E01", "fetched_at": NOW.isoformat(), "likes": 1, "comments": 2})
    (tmp_path / "board" / "data").mkdir(parents=True)
    return tmp_path


ENV = {"IG_ACCESS_TOKEN": "IGLOGINTOKEN00000", "IG_PUBLISH_TOKEN": SECRET, "FB_PAGE_ID": "99", "FB_PAGE_TOKEN": SECRET}
IG_VALUES = {"views": 362, "reach": 320, "shares": 33, "saved": 0, "total_interactions": 51, "ig_reels_avg_watch_time": 4200, "ig_reels_video_view_total_time": 90000}
FB_VALUES = {"blue_reels_play_count": 40, "fb_reels_replay_count": 3, "post_video_avg_time_watched": 13174, "post_video_view_time": 26349}


def graph_ok(values):
    def _http(method, url, headers=None, data=None):
        assert SECRET not in url and "access_token=" not in url          # the token travels as a header only
        name = url.split("metric=")[1].split("&")[0]
        return {"data": [{"name": name, "total_value": {"value": values[name]}}]}
    return _http


def graph_denied(code, text):
    def _http(method, url, headers=None, data=None):
        raise RuntimeError(f"HTTP 400 GET {url.split('?')[0]}: " + json.dumps({"error": {"message": text, "type": "OAuthException", "code": code}}))
    return _http


# ------------------------------------------------------------------ Instagram
def test_instagram_insights_are_fetched_and_written(repo, monkeypatch):
    monkeypatch.setattr(ig, "_http", graph_ok(IG_VALUES))
    r = ln.fetch_instagram(repo, "E01", ENV, NOW)
    assert r["status"] == "ok" and r["values"] == 7
    f = rj(repo / "work/episodes/E01/insights-instagram.json")
    assert f["metrics"]["views"]["value"] == 362 and f["metrics"]["saved"]["value"] == 0 and f["metrics"]["views"]["at"].startswith("2026-10-27T07:00:00")
    assert SECRET not in json.dumps(f)


def test_instagram_permission_error_keeps_the_exact_reason_and_stops_calling(repo, monkeypatch):
    calls = []
    inner = graph_denied(10, "(#10) Application does not have permission for this action")
    monkeypatch.setattr(ig, "_http", lambda *a, **k: (calls.append(1), inner(*a, **k))[1])
    r = ln.fetch_instagram(repo, "E01", ENV, NOW)
    assert r["status"] == "no-insights" and r["reason"] == "needs instagram_manage_insights" and len(calls) == 1
    f = rj(repo / "work/episodes/E01/insights-instagram.json")
    assert all(x["reason"] == "needs instagram_manage_insights" and "value" not in x for x in f["metrics"].values())


def test_a_failed_metric_keeps_its_last_good_value_with_the_old_time(repo, monkeypatch):
    monkeypatch.setattr(ig, "_http", graph_ok(IG_VALUES))
    ln.fetch_instagram(repo, "E01", ENV, NOW)
    monkeypatch.setattr(ig, "_http", graph_denied(100, "Unsupported get request"))
    ln.fetch_instagram(repo, "E01", ENV, NOW + timedelta(minutes=15))
    x = rj(repo / "work/episodes/E01/insights-instagram.json")["metrics"]["views"]
    assert x["value"] == 362 and x["at"].startswith("2026-10-27T07:00:00") and x["error"]


def test_instagram_without_a_post_or_token_is_skipped(repo):
    assert ln.fetch_instagram(repo, "E02", ENV, NOW)["status"] == "skipped"
    assert ln.fetch_instagram(repo, "E01", {}, NOW)["status"] == "skipped"


# ------------------------------------------------------------------ Facebook
def test_facebook_video_insights_are_fetched(repo, monkeypatch):
    monkeypatch.setattr(ig, "_http", graph_ok(FB_VALUES))
    r = ln.fetch_facebook(repo, "E01", ENV, NOW)
    assert r["status"] == "ok" and r["values"] == 4
    assert rj(repo / "work/episodes/E01/insights-facebook.json")["metrics"]["blue_reels_play_count"]["value"] == 40


def test_facebook_permission_error_says_read_insights(repo, monkeypatch):
    monkeypatch.setattr(ig, "_http", graph_denied(200, "(#200) requires read_insights permission"))
    r = ln.fetch_facebook(repo, "E01", ENV, NOW)
    assert r["reason"] == "needs read_insights"
    assert set(x["reason"] for x in rj(repo / "work/episodes/E01/insights-facebook.json")["metrics"].values()) == {"needs read_insights"}


# ------------------------------------------------------------------ YouTube
def yt_http(stats=None, fail=None):
    def _http(method, url, headers=None, data=None):
        if "oauth2" in url:
            if fail == "oauth":
                raise RuntimeError("HTTP 400 POST oauth: invalid_grant " + YT_SECRET)
            return {"access_token": "ya29.fake-access"}
        assert headers["Authorization"] == "Bearer ya29.fake-access" and "part=statistics" in url and "Y1" in url
        return {"items": [{"id": "Y1", "statistics": stats}]}
    return _http


@pytest.fixture
def yt_token(tmp_path):
    p = tmp_path / "yt-token.json"
    wj(p, {"client_id": "cid-1234567890", "client_secret": "csecret-123456", "refresh_token": YT_SECRET})
    return p


def test_youtube_statistics_are_written_per_episode(repo, yt_token):
    r = ln.fetch_youtube(repo, token_file=yt_token, http=yt_http({"viewCount": "36", "likeCount": "3", "commentCount": "1"}), at=NOW)
    f = rj(repo / "work/episodes/E01/metrics-youtube.json")
    assert r["status"] == "ok" and (f["views"], f["likes"], f["comments"]) == (36, 3, 1) and f["fetched_at"].startswith("2026-10-27T07:00:00")


def test_youtube_hidden_likes_are_none_not_zero(repo, yt_token):
    ln.fetch_youtube(repo, token_file=yt_token, http=yt_http({"viewCount": "36", "commentCount": "0"}), at=NOW)
    f = rj(repo / "work/episodes/E01/metrics-youtube.json")
    assert f["likes"] is None and f["comments"] == 0


def test_youtube_failure_is_recorded_redacted_and_keeps_old_numbers(repo, yt_token):
    ln.fetch_youtube(repo, token_file=yt_token, http=yt_http({"viewCount": "36", "likeCount": "3", "commentCount": "1"}), at=NOW)
    r = ln.fetch_youtube(repo, token_file=yt_token, http=yt_http(fail="oauth"), at=NOW + timedelta(minutes=15))
    f = rj(repo / "work/episodes/E01/metrics-youtube.json")
    assert r["status"] == "error" and f["views"] == 36 and f["fetched_at"].startswith("2026-10-27T07:00:00") and f["error"]
    assert YT_SECRET not in json.dumps(f) and YT_SECRET not in r["reason"]


def test_youtube_without_a_token_is_skipped(repo, tmp_path):
    assert ln.fetch_youtube(repo, token_file=tmp_path / "none.json", http=yt_http({}))["status"] == "skipped"


# ------------------------------------------------------------------ the board
def test_board_cards_show_fresh_numbers_as_of_and_stale_badge(repo, yt_token, monkeypatch):
    monkeypatch.setattr(ig, "_http", graph_ok({**IG_VALUES, **FB_VALUES}))
    ln.fetch_instagram(repo, "E01", ENV, NOW)
    ln.fetch_facebook(repo, "E01", ENV, NOW)
    ln.fetch_youtube(repo, token_file=yt_token, http=yt_http({"viewCount": "50", "likeCount": "4", "commentCount": "2"}), at=NOW - timedelta(minutes=45))
    data = mb.build(repo, NOW + timedelta(minutes=1), env={})
    by = lambda pf: {m["key"]: m for m in data["platforms"][pf]["posts"][0]["metrics"]}      # noqa: E731
    assert by("instagram")["views"]["value"] == 362 and by("instagram")["views"]["stale"] is False and by("instagram")["views"]["as_of"]["hms"] == "10:00:00"
    assert by("facebook")["views"]["value"] == 40
    yt = by("youtube")
    assert yt["views"]["value"] == 50 and yt["views"]["stale"] is True            # read 46 min ago: stale
    allv = {m["key"]: m for m in data["all"]["metrics"]}
    assert allv["views"]["value"] == 362 + 40 + 50 and allv["views"]["stale"] is True and allv["views"]["as_of"]            # the oldest contributor decides
    assert data["stale_min"] == 30


def test_a_permission_reason_reaches_the_board_instead_of_a_zero(repo, monkeypatch):
    monkeypatch.setattr(ig, "_http", graph_denied(10, "(#10) permission"))
    ln.fetch_instagram(repo, "E01", ENV, NOW)
    m = {x["key"]: x for x in mb.build(repo, NOW, env={})["platforms"]["instagram"]["posts"][0]["metrics"]}
    assert m["views"]["na"] == "needs instagram_manage_insights" and "value" not in m["views"]
    assert m["likes"]["value"] == 8                                          # likes and comments still come from metrics.json


def test_refresh_all_never_raises_and_reports_each_platform(repo, yt_token, monkeypatch):
    monkeypatch.setattr(ig, "_http", graph_denied(10, "(#10) permission"))
    res = ln.refresh_all(repo, env=ENV, at=NOW, http=yt_http({"viewCount": "1"}), token_file=yt_token)
    assert res["youtube"]["status"] == "ok" and res["instagram"]["E01"]["reason"] == "needs instagram_manage_insights" and res["facebook"]["E01"]["reason"] == "needs read_insights"
    assert "needs read_insights" in ln.summary_line(res)


def test_ig_board_refresh_runs_the_live_fetch_then_rebuilds_the_monitor(repo, monkeypatch):
    import ig_board
    import loop_gate
    called = []
    monkeypatch.setattr(ig_board, "ROOT", repo)
    monkeypatch.setattr(loop_gate, "has_token", lambda *a, **k: False)
    monkeypatch.setattr(ln, "refresh_all", lambda root: (called.append(root), {"youtube": {"status": "ok"}})[1])
    assert ig_board.main(["refresh", "--metrics"]) == 0
    assert called and (repo / "board" / "data" / "monitor.json").is_file()
