"""yt_perf tests: no network (fake Data and Analytics services), no real credentials."""
import csv
import json
from datetime import datetime, timezone

import pytest

import ig_board
import learn
import yt
import yt_perf

T0 = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)
SECRET = {"token": "ya29.ACCESSsecret123456", "refresh_token": "1//REFRESHsecret987654", "client_id": "cid", "client_secret": "GOCSPX-clientsecret55"}


class Req:
    def __init__(self, fn):
        self.fn = fn

    def execute(self):
        return self.fn()


class Data:
    def __init__(self, vids):
        self.vids, self.calls = vids, []

    def channels(self):
        return type("C", (), {"list": lambda s, **kw: Req(lambda: {"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UU1"}}}]})})()

    def playlistItems(self):
        d = self

        class P:
            def list(s, **kw):
                d.calls.append(kw)
                ids = [v["id"] for v in d.vids]
                if kw.get("pageToken"):
                    return Req(lambda: {"items": [{"contentDetails": {"videoId": i}} for i in ids[1:]]})
                return Req(lambda: {"items": [{"contentDetails": {"videoId": ids[0]}}], "nextPageToken": "p2"})
        return P()

    def videos(self):
        d = self
        return type("V", (), {"list": lambda s, part, id: Req(lambda: {"items": [v for v in d.vids if v["id"] in id.split(",")]})})()


class Analytics:
    def __init__(self, reject_engaged=False, fail_dim=None):
        self.queries, self.reject_engaged, self.fail_dim = [], reject_engaged, fail_dim

    def reports(self):
        a = self

        class R:
            def query(s, **kw):
                a.queries.append(kw)
                return Req(lambda: a.answer(kw))
        return R()

    def answer(self, kw):
        dim, metrics = kw.get("dimensions"), kw["metrics"]
        if self.fail_dim and dim == self.fail_dim:
            raise RuntimeError("Bad Request access_token=ya29.ACCESSsecret123456")
        if self.reject_engaged and "engagedViews" in metrics and "," in metrics:
            raise RuntimeError("The query is not supported")
        if dim == "day":
            return {"columnHeaders": [{"name": "day"}, {"name": "views"}], "rows": [["2026-10-24", 5]]}
        if dim == "elapsedVideoTimeRatio":
            return {"columnHeaders": [{"name": dim}, {"name": "audienceWatchRatio"}], "rows": [[0.01, 1.0], [0.5, 0.4]]}
        if dim == "insightTrafficSourceType":
            return {"columnHeaders": [{"name": dim}, {"name": "views"}, {"name": "estimatedMinutesWatched"}], "rows": [["SHORTS", 7, 3.5], ["EXT_URL", 1, 0.2]]}
        if dim == "country":
            return {"columnHeaders": [{"name": dim}, {"name": "views"}, {"name": "estimatedMinutesWatched"}], "rows": [["SA", 4, 2.0], ["EG", 3, 1.0]]}
        if dim == "creatorContentType":
            return {"columnHeaders": [{"name": dim}, {"name": "views"}, {"name": "estimatedMinutesWatched"}], "rows": [["SHORTS", 8, 3.7]]}
        names = metrics.split(",")
        vals = {"views": 8, "engagedViews": 6, "estimatedMinutesWatched": 3.7, "averageViewDuration": 28.0, "averageViewPercentage": 61.5, "likes": 2, "dislikes": 0,
                "comments": 1, "shares": 0, "subscribersGained": 1, "subscribersLost": 0}
        if "VIDNONE" in kw["filters"]:
            return {"columnHeaders": [{"name": n} for n in names], "rows": []}
        return {"columnHeaders": [{"name": n} for n in names], "rows": [[vals[n] for n in names]]}


def video(i, published, secs="PT45S", privacy="public"):
    return {"id": i, "snippet": {"title": f"عنوان {i}", "publishedAt": published}, "statistics": {"viewCount": "9", "likeCount": "2", "commentCount": "1"},
            "contentDetails": {"duration": secs}, "status": {"privacyStatus": privacy}}


@pytest.fixture
def repo(tmp_path):
    w = tmp_path / "work" / "episodes" / "E01C"
    w.mkdir(parents=True)
    (w / "youtube.json").write_text(json.dumps({"video_id": "VIDA", "state": "uploaded"}), encoding="utf-8")
    return tmp_path


def run(repo, an=None, vids=None):
    vids = vids or [video("VIDB", "2026-10-01T00:00:00Z", "PT5M"), video("VIDA", "2026-10-25T10:00:00Z")]
    return yt_perf.cmd_fetch(30, repo, Data(vids), an or Analytics(), T0)


def test_fetch_outputs(repo):
    run(repo)
    od = yt_perf.out_dir(repo)
    raw = (od / "videos.csv").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    rows = list(csv.DictReader(raw.decode("utf-8-sig").splitlines()))
    assert [r["video_id"] for r in rows] == ["VIDA", "VIDB"]            # newest first
    a = rows[0]
    assert a["episode"] == "E01C" and a["views"] == "8" and a["is_short"] == "True" and rows[1]["is_short"] == "False"
    assert a["top_country"] == "SA" and a["top_traffic_source"] == "SHORTS" and a["data_viewCount"] == "9" and a["as_of"] == "2026-10-24"
    d = json.loads((od / "VIDA.json").read_text(encoding="utf-8"))
    assert d["retention"][1] == {"elapsedVideoTimeRatio": 0.5, "audienceWatchRatio": 0.4} and len(d["countries"]) == 2
    sm = json.loads((od / "summary.json").read_text(encoding="utf-8"))
    assert sm["videos"] == 2 and sm["episodes_mapped"] == 1 and sm["sums"]["views"] == 16 and sm["as_of"] == "2026-10-24" and sm["fetched_at"].startswith("2026-10-26")


def test_all_pages_listed():
    d = Data([video("V1", "2026-10-01T00:00:00Z"), video("V2", "2026-10-02T00:00:00Z"), video("V3", "2026-10-03T00:00:00Z")])
    assert [v["id"] for v in yt_perf.list_videos(d)] == ["V1", "V2", "V3"]


def test_unsupported_metric_degrades_to_single_queries(repo):
    run(repo, Analytics(reject_engaged=True))
    d = json.loads((yt_perf.out_dir(repo) / "VIDA.json").read_text(encoding="utf-8"))
    assert d["totals"]["views"] == 8 and d["totals"]["engagedViews"] == 6 and "whole_list_error" in d["totals"]


def test_failed_breakdown_is_not_available_and_redacted(repo, monkeypatch):
    monkeypatch.setattr(yt, "TOKEN_FILE", repo / "tok.json")
    (repo / "tok.json").write_text(json.dumps(SECRET), encoding="utf-8")
    run(repo, Analytics(fail_dim="country"))
    d = json.loads((yt_perf.out_dir(repo) / "VIDA.json").read_text(encoding="utf-8"))
    assert d["countries"]["status"] == "not available" and d["totals"]["views"] == 8
    blob = "".join(p.read_text(encoding="utf-8-sig") for p in yt_perf.out_dir(repo).iterdir())
    assert "ACCESSsecret" not in blob


def test_api_not_enabled_gives_one_clear_reason(repo):
    class Off(Analytics):
        def answer(self, kw):
            err = RuntimeError("403")
            err.resp = type("R", (), {"status": 403})()
            err.content = json.dumps({"error": {"message": "YouTube Analytics API has not been used in project 1 before or it is disabled."}}).encode()
            raise err
    off = Off()
    sm = run(repo, off)
    assert len(off.queries) == 1 and "has not been used" in sm["analytics_problem"]
    d = json.loads((yt_perf.out_dir(repo) / "VIDA.json").read_text(encoding="utf-8"))
    assert d["data_api"]["viewCount"] == 9 and d["totals"]["views"]["status"] == "not available"


def test_http_error_other_than_400_is_not_retried_per_metric(repo):
    class Denied(Analytics):
        def answer(self, kw):
            if kw.get("dimensions") == "day":
                return super().answer(kw)
            err = RuntimeError("quota")
            err.resp = type("R", (), {"status": 429})()
            raise err
    a = Denied()
    run(repo, a, [video("VIDA", "2026-10-25T10:00:00Z")])
    assert len(a.queries) <= 7           # preflight + totals + 4 breakdowns, no per-metric storm


def test_no_rows_means_zero(repo):
    run(repo, vids=[video("VIDNONE", "2026-10-25T10:00:00Z")])
    d = json.loads((yt_perf.out_dir(repo) / "VIDNONE.json").read_text(encoding="utf-8"))
    assert d["totals"]["views"] == 0 and "note" in d["totals"]


def test_leak_refuses(repo, monkeypatch):
    monkeypatch.setattr(yt, "load_token", lambda path=None: {"token": "STRANGEWORD"})
    with pytest.raises(SystemExit):
        yt_perf.cmd_fetch(30, repo, Data([video("VIDA", "2026-10-25T10:00:00Z", privacy="STRANGEWORD")]), Analytics(), T0)


def test_iso_seconds():
    assert yt_perf.iso_seconds("PT1M5S") == 65 and yt_perf.iso_seconds("PT45S") == 45 and yt_perf.iso_seconds("PT1H") == 3600 and yt_perf.iso_seconds("x") is None


def test_status_and_scopes(repo, monkeypatch):
    monkeypatch.setattr(yt, "TOKEN_FILE", repo / "tok.json")
    (repo / "tok.json").write_text(json.dumps({**SECRET, "scopes": [yt_perf.SCOPE_READ]}), encoding="utf-8")
    run(repo)
    s = yt_perf.cmd_status(repo)
    assert "yt-analytics.readonly: MISSING" in s and "youtube.readonly: yes" in s and "2 videos" in s and "ACCESSsecret" not in s


def test_feeds_learn_and_board(repo):
    w = repo / "work" / "episodes" / "E01C"
    assert yt_perf.learn_stats("E01C", repo) is None and "perf" not in ig_board.youtube_row(w)
    run(repo)
    ls = yt_perf.learn_stats("E01C", repo)
    assert ls["views"] == {"value": 8} and ls["viewCount"] == {"value": 9} and ls["as_of"] == "2026-10-24"
    assert learn._yt_stats("E01C", repo) == ls                         # learn.py uses it before the private-upload gate
    assert yt_perf.country_counts("E01C", repo) == {"SA": 4, "EG": 3}
    assert ig_board.youtube_row(w)["perf"]["views"] == 8
