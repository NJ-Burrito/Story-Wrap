"""SEO keyword data (data/seo/keywords.json), the YouTube tags and the seo-fix command. No network."""
import json

import pytest

import ig
import seo
import yt
from arabic_display import has_tashkeel
from test_yt import Fake, make_repo   # noqa: F401  (the fixture `env` in test_yt is autouse only there)


def test_hashtag_counts_and_form_match_the_design():
    for plat, n in (("instagram", 3), ("facebook", 2), ("youtube", 3)):
        h = seo.hashtag_list(plat)
        assert len(h) == n and all(t.startswith("#") and " " not in t for t in h)
    assert ig.HASHTAGS["instagram"] == seo.hashtags("instagram") and yt.HASHTAGS == tuple(seo.hashtag_list("youtube"))
    assert not ig.caption_problems(seo.hashtags("instagram"), "instagram") and not ig.caption_problems(seo.hashtags("facebook"), "facebook")


def test_no_tashkeel_and_no_rejected_words_anywhere_in_the_keyword_file():
    text = json.dumps(seo.load(), ensure_ascii=False)
    assert not has_tashkeel(text)
    assert not any(w in text.lower() for w in ("gemini", "رعب", "fortnite", "minecraft", "covid"))


def test_youtube_tags_fit_the_budget_dedupe_and_keep_the_series_first():
    tags = seo.youtube_tags(extra=["هدى", "the series", "x" * 600])
    assert tags[0] == "the series" and tags.count("the series") == 1 and "هدى" in tags and ("x" * 600) not in tags
    cost = sum(len(t) + (2 if " " in t else 0) for t in tags) + len(tags) - 1
    assert cost <= seo.TAGS_LIMIT


def test_a_tiny_budget_drops_tags_not_the_first(tmp_path):
    p = tmp_path / "k.json"
    d = seo.load(); d["youtube_tags_max_chars"] = 30
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    t = seo.youtube_tags(path=p)
    assert t[0] == "the series" and len(t) < len(seo.load()["youtube_tags"])


def test_description_carries_the_keyword_line_right_after_the_hook(tmp_path):
    repo, _ = make_repo(tmp_path)
    _, d = yt.yt_parts("E01", repo, seconds=60.0)
    lines = d.splitlines()
    assert lines[1] == seo.keyword_line() and not yt.text_problems("the series | الحلقة ١", d)


def test_seo_fix_dry_run_writes_nothing_and_go_updates_once(tmp_path):
    class V(Fake):
        def videos(self):
            f = self

            class VV:
                def list(s, part, id):
                    f._rec("videos.list", part=part, id=id)
                    return type("R", (), {"execute": lambda self_: {"items": [{"snippet": {"title": "t", "description": "d", "tags": ["fortnite"], "categoryId": "20", "defaultLanguage": "en-US"},
                                                                              "status": {"privacyStatus": "public", "license": "creativeCommon", "embeddable": True, "uploadStatus": "processed"}}]}})()

                def update(s, part, body):
                    f._rec("videos.update", part=part, body=body)
                    return type("R", (), {"execute": lambda self_: {}})()
            return VV()
    repo, _ = make_repo(tmp_path)
    f = V()
    out = yt.cmd_seo_fix("VID9", go=False, repo=repo, svc=f)
    assert out["mode"] == "DRY RUN" and out["changes"]["categoryId"] == {"from": "20", "to": "1"} and out["changes"]["license"]["to"] == "youtube"
    assert not [c for c in f.calls if c[0] == "videos.update"]
    f = V()
    yt.cmd_seo_fix("VID9", go=True, repo=repo, svc=f, sleep=lambda s: None)
    upd = [c for c in f.calls if c[0] == "videos.update"]
    assert len(upd) == 1
    b = upd[0][1]["body"]
    assert b["snippet"]["title"] == "t" and b["snippet"]["tags"][0] == "the series" and "uploadStatus" not in b["status"] and b["status"]["privacyStatus"] == "public"


class LagVideos:
    """A videos.list that serves the OLD snippet for `lag` reads after an update (the replica lag measured on 2026-10-27), tags re-ordered (sorted) like the API."""
    def __init__(self, lag=2):
        self.lag, self.calls, self.sn = lag, [], {"title": "t", "description": "d", "tags": ["fortnite"], "categoryId": "20", "defaultLanguage": "en-US"}
        self.new = None

    def videos(self):
        f = self

        class VV:
            def list(s, part, id):
                f.calls.append("list")
                def run():
                    if f.new is not None and f.lag <= 0:
                        sn = dict(f.new); sn["tags"] = sorted(sn["tags"])
                        return {"items": [{"snippet": sn, "status": {"privacyStatus": "public", "license": "youtube"}}]}
                    if f.new is not None:
                        f.lag -= 1
                    return {"items": [{"snippet": f.sn, "status": {"privacyStatus": "public", "license": "creativeCommon"}}]}
                return type("R", (), {"execute": lambda self_: run()})()

            def update(s, part, body):
                f.calls.append("update")
                f.new = dict(body["snippet"])
                return type("R", (), {"execute": lambda self_: {"id": "VID9", "snippet": {"tags": body["snippet"]["tags"]}}})()
        return VV()


def test_seo_fix_waits_out_a_lagging_read_and_proves_the_new_tags(tmp_path):
    repo, _ = make_repo(tmp_path)
    f = LagVideos(lag=2)
    naps = []
    out = yt.cmd_seo_fix("VID9", go=True, repo=repo, svc=f, sleep=naps.append)
    assert out["readback_ok"] is True and sorted(out["readback"]["tags"]) == sorted(seo.youtube_tags()) and len(naps) == 2
    assert f.calls.count("update") == 1


def test_seo_fix_reports_a_failed_readback_instead_of_claiming_success(tmp_path):
    repo, _ = make_repo(tmp_path)
    out = yt.cmd_seo_fix("VID9", go=True, repo=repo, svc=LagVideos(lag=99), sleep=lambda s: None)
    assert out["readback_ok"] is False and out["readback"]["tags"] == ["fortnite"]


def test_tag_order_alone_is_not_a_change():
    assert yt._same("tags", sorted(seo.youtube_tags()), seo.youtube_tags()) and not yt._same("tags", ["a"], ["b"])


def test_a_video_id_starting_with_E_is_not_taken_for_an_episode(tmp_path):
    repo, _ = make_repo(tmp_path)
    out = yt.cmd_seo_fix("E5_Amg97q7k", go=False, repo=repo, svc=LagVideos(lag=0))
    assert out["video"] == "E5_Amg97q7k"


class ChannelFake:
    def __init__(self):
        self.ch = {"id": yt.CHANNEL_ID, "brandingSettings": {"channel": {"title": "StoryPage", "description": "old", "country": "JO"}, "image": {"bannerExternalUrl": "u"}}}
        self.pl = [{"id": "A", "snippet": {"title": yt.PLAYLIST_TITLE, "description": "old"}, "status": {"privacyStatus": "public"}},
                   {"id": "B", "snippet": {"title": "Music", "description": ""}, "status": {"privacyStatus": "public"}},
                   {"id": "C", "snippet": {"title": "Atomicrops", "description": ""}, "status": {"privacyStatus": "unlisted"}}]
        self.updates = []

    def channels(self):
        f = self

        class C:
            def list(s, **kw):
                return type("R", (), {"execute": lambda self_: {"items": [json.loads(json.dumps(f.ch))]}})()

            def update(s, part, body):
                f.updates.append(("channels", part, body))
                f.ch["brandingSettings"] = body["brandingSettings"]
                return type("R", (), {"execute": lambda self_: {}})()
        return C()

    def playlists(self):
        f = self

        class P:
            def list(s, **kw):
                return type("R", (), {"execute": lambda self_: {"items": json.loads(json.dumps(f.pl))}})()

            def update(s, part, body):
                f.updates.append(("playlists", part, body))
                for p in f.pl:
                    if p["id"] == body["id"]:
                        p["snippet"]["description"] = body["snippet"]["description"]; p["status"]["privacyStatus"] = body["status"]["privacyStatus"]
                return type("R", (), {"execute": lambda self_: {}})()
        return P()


def test_channel_seo_dry_run_writes_nothing_and_go_changes_only_the_named_things(tmp_path):
    f = ChannelFake()
    out = yt.cmd_channel_seo(go=False, svc=f)
    assert out["mode"] == "DRY RUN" and not f.updates and "playlist Music" in out["changes"] and "playlist Atomicrops" not in out["changes"]
    out = yt.cmd_channel_seo(go=True, svc=f, sleep=lambda s: None)
    assert out["readback_ok"] is True
    ch = [u for u in f.updates if u[0] == "channels"]
    assert len(ch) == 1 and ch[0][2]["brandingSettings"]["channel"]["country"] == "JO" and ch[0][2]["brandingSettings"]["image"] == {"bannerExternalUrl": "u"}
    assert ch[0][2]["brandingSettings"]["channel"]["defaultLanguage"] == "ar" and "the series" in ch[0][2]["brandingSettings"]["channel"]["keywords"]
    assert {u[2]["id"]: u[2]["status"]["privacyStatus"] for u in f.updates if u[0] == "playlists"} == {"A": "public", "B": "private"}
    assert not has_tashkeel(seo.load()["channel_description"])
