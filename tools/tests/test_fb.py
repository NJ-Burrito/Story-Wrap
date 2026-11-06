"""Facebook Page tool tests: no network (the http layer is replaced), no real credentials."""
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

import pytest

import sw_fixtures
import daily
import fb
import ig
import ig_board
import vote
from test_ig import ENV as IG_ENV, Fake as IgFake, TOKEN as IG_TOKEN, make_repo as _make_repo

FB_TOKEN = "EAAFBpageTOKEN987654321"
ENV = {**IG_ENV, "FB_PAGE_ID": "1000000000000001", "FB_PAGE_TOKEN": FB_TOKEN}
T0 = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
PID = "1000000000000001"


def make_repo(tmp_path, instagram=True, **kw):
    """An episode that passed every gate. By default Instagram is already on record (an old post), because Facebook never goes live before Instagram."""
    repo, w = _make_repo(tmp_path, **kw)
    if instagram:
        (w / "post.json").write_text(json.dumps({"media_id": "MEDIA1", "posted_at": (T0 - timedelta(days=40)).isoformat(), "username": "storywrap"}), encoding="utf-8")
    return repo, w


class FbFake:
    """Answers like graph.facebook.com for the Reels flow; records every call."""
    def __init__(self, video_status="ready", comments=None, replies=None, fail_start=False):
        self.calls, self.video_status = [], video_status
        self.comments, self.replies, self.fail_start = comments or [], replies or {}, fail_start

    def __call__(self, method, url, headers=None, data=None):
        self.calls.append((method, url, dict(headers or {}), data))
        u = url.split("?")[0]
        if u.endswith(f"/{PID}/video_reels"):
            body = (data or b"").decode()
            if self.fail_start:
                raise RuntimeError("HTTP 400 POST " + u + ": nope " + FB_TOKEN)
            if "upload_phase=start" in body:
                return {"video_id": "VID1", "upload_url": "https://rupload.facebook.com/video-upload/v26.0/VID1"}
            if "upload_phase=finish" in body:
                return {"success": True}
        if "rupload.facebook.com" in u:
            return {"success": True}
        if u.endswith(f"/{PID}"):
            return {"name": "StoryPage", "id": PID}
        if u.endswith("/VID1/comments"):
            return {"data": self.comments}
        if u.endswith("/comments") and "/VID1/" not in u:
            return {"data": self.replies.get(u.split("/")[-2], [])}
        if u.endswith("/VID1"):
            if "fields=status" in url:
                return {"status": {"video_status": self.video_status}}
            if "permalink_url" in url and "likes" not in url:
                return {"permalink_url": "/reel/VID1/"}
            return {"likes": {"summary": {"total_count": 7}}, "comments": {"summary": {"total_count": 3}}, "permalink_url": "/reel/VID1/"}
        raise AssertionError("unexpected call " + url)


def two_hosts(fbf, igf):
    """One fake http layer that routes by host: graph.facebook.com / rupload.facebook.com to FB, graph.instagram.com and ig-api-upload to IG."""
    def h(method, url, headers=None, data=None):
        if "graph.instagram.com" in url or "ig-api-upload" in url:
            return igf(method, url, headers, data)
        return fbf(method, url, headers, data)
    return h


@pytest.fixture
def fbf(monkeypatch):
    f = FbFake()
    monkeypatch.setattr(ig, "_http", f)
    return f


def record(w):
    return json.loads((w / "facebook.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- publish sequence
def test_publish_runs_start_upload_finish_then_polls_and_records(tmp_path, fbf):
    repo, w = make_repo(tmp_path)
    rec = fb.cmd_publish("E01", go=True, repo=repo, env=dict(ENV), sleep=lambda s: None)
    kinds = []
    for m, u, h, d in fbf.calls:
        if "rupload" in u:
            kinds.append("upload")
        elif u.split("?")[0].endswith("/video_reels"):
            kinds.append("start" if b"upload_phase=start" in d else "finish")
        else:
            kinds.append("get")
    assert kinds[:3] == ["start", "upload", "finish"] and kinds[3:] == ["get", "get"]       # status poll, then the permalink
    up = next(c for c in fbf.calls if "rupload" in c[1])
    assert up[2]["Authorization"] == f"OAuth {FB_TOKEN}" and up[2]["offset"] == "0" and up[2]["file_size"] == "64" and up[3] == b"\x00" * 64
    fin = next(c for c in fbf.calls if c[3] and b"upload_phase=finish" in c[3])[3].decode()
    assert "video_state=PUBLISHED" in fin and "video_id=VID1" in fin and "description=" in fin
    assert all(c[1].startswith("https://graph.facebook.com/v26.0/") for c in fbf.calls if "rupload" not in c[1])
    assert rec["video_id"] == "VID1" and rec["permalink"] == "https://www.facebook.com/reel/VID1/" and rec["state"] == "published"
    assert record(w)["video_id"] == "VID1" and FB_TOKEN not in json.dumps(record(w))


def test_publish_mirrors_into_post_json_under_facebook_key_and_keeps_old_keys(tmp_path, fbf):
    repo, w = make_repo(tmp_path)
    (w / "post.json").write_text(json.dumps({"media_id": "MEDIA1", "posted_at": T0.isoformat(), "username": "storywrap"}), encoding="utf-8")
    fb.cmd_publish("E01", go=True, repo=repo, env=dict(ENV), sleep=lambda s: None)
    post = json.loads((w / "post.json").read_text(encoding="utf-8"))
    assert post["media_id"] == "MEDIA1" and post["username"] == "storywrap"               # the old readers' keys are untouched
    assert post["facebook"]["video_id"] == "VID1" and post["facebook"]["permalink"].endswith("/reel/VID1/")


def test_publish_refuses_without_gates_and_dry_run_makes_no_call(tmp_path, fbf, capsys):
    repo, w = make_repo(tmp_path, verdict="FAIL")
    with pytest.raises(SystemExit) as e:
        fb.cmd_publish("E01", go=True, repo=repo, env=dict(ENV))
    assert "FB-GATE" in str(e.value) and fbf.calls == [] and not (w / "facebook.json").exists()
    repo, w = make_repo(tmp_path / "ok")
    plan = fb.cmd_publish("E01", go=False, repo=repo, env={})
    assert plan["mode"] == "DRY RUN" and fbf.calls == [] and not (w / "facebook.json").exists()
    assert "الحلقة ١" in capsys.readouterr().out


def test_publish_is_idempotent_an_episode_is_never_posted_twice(tmp_path, fbf):
    repo, w = make_repo(tmp_path)
    fb.cmd_publish("E01", go=True, repo=repo, env=dict(ENV), sleep=lambda s: None)
    n = len(fbf.calls)
    with pytest.raises(SystemExit) as e:
        fb.cmd_publish("E01", go=True, repo=repo, env=dict(ENV), sleep=lambda s: None)
    assert "FB-ALREADY" in str(e.value) and len(fbf.calls) == n


def test_a_stuck_video_is_recorded_so_it_cannot_be_posted_again(tmp_path, monkeypatch):
    monkeypatch.setattr(ig, "_http", FbFake(video_status="error"))
    repo, w = make_repo(tmp_path)
    with pytest.raises(SystemExit) as e:
        fb.cmd_publish("E01", go=True, repo=repo, env=dict(ENV), sleep=lambda s: None)
    assert "FB-PROCESS" in str(e.value) and record(w)["state"] == "not-ready:error"
    assert fb.is_posted("E01", repo)


def test_missing_credentials_name_keys_not_values(tmp_path, fbf):
    repo, w = make_repo(tmp_path)
    with pytest.raises(SystemExit) as e:
        fb.cmd_publish("E01", go=True, repo=repo, env={"IG_USER_ID": "1"})
    assert "FB_PAGE_ID" in str(e.value) and "FB_PAGE_TOKEN" in str(e.value) and fbf.calls == []


# ---------------------------------------------------------------- redaction
def test_token_redaction_in_errors_status_and_output_files(tmp_path, monkeypatch, capsys):
    assert FB_TOKEN not in ig.redact(f"boom {FB_TOKEN} access_token={FB_TOKEN}", ENV)
    assert "FB_PAGE_TOKEN" in ig.SECRET_KEYS
    monkeypatch.setattr(ig, "_http", FbFake(fail_start=True))
    repo, w = make_repo(tmp_path)
    with pytest.raises(SystemExit) as e:
        fb.cmd_publish("E01", go=True, repo=repo, env=dict(ENV))
    assert "FB-HTTP" in str(e.value) and FB_TOKEN not in str(e.value)
    fb.cmd_status(repo=repo, env=dict(ENV))
    assert FB_TOKEN not in capsys.readouterr().out


def test_comments_output_refuses_to_carry_a_token(tmp_path, monkeypatch):
    leaked = [{"id": "VID1_c1", "message": f"look {FB_TOKEN}", "created_time": "t", "from": {"id": "9", "name": "Sara"}}]
    monkeypatch.setattr(ig, "_http", FbFake(comments=leaked))
    repo, w = make_repo(tmp_path)
    (w / "facebook.json").write_text(json.dumps({"video_id": "VID1", "posted_at": T0.isoformat()}), encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        fb.cmd_comments("E01", repo=repo, env=dict(ENV), at=T0 + timedelta(hours=13))
    assert "FB-LEAK" in str(e.value) and not (w / "comments.json").exists()


# ---------------------------------------------------------------- one platform failing, the other succeeding
def test_facebook_never_goes_live_before_instagram_and_follows_once_instagram_is_on_record(tmp_path, monkeypatch):
    igf, fbf_ = IgFake(status="ERROR"), FbFake()                  # the Instagram container never finishes
    monkeypatch.setattr(ig, "_http", two_hosts(fbf_, igf))
    repo, w = make_repo(tmp_path, instagram=False)
    with pytest.raises(SystemExit):
        ig.cmd_publish("E01", go=True, repo=repo, env=dict(ENV), sleep=lambda s: None)
    with pytest.raises(SystemExit) as e:                          # Instagram is not on record: Facebook waits, nothing is uploaded
        fb.cmd_publish("E01", go=True, repo=repo, env=dict(ENV), sleep=lambda s: None)
    assert "FB-WAIT-INSTAGRAM" in str(e.value) and fbf_.calls == [] and not (w / "facebook.json").exists() and not (w / "post.json").exists()
    monkeypatch.setattr(ig, "_http", two_hosts(FbFake(), IgFake()))
    ig.cmd_publish("E01", go=True, repo=repo, env=dict(ENV), sleep=lambda s: None)
    rec = fb.cmd_publish("E01", go=True, repo=repo, env=dict(ENV), sleep=lambda s: None)
    post = json.loads((w / "post.json").read_text(encoding="utf-8"))
    assert post["media_id"] == "MEDIA1" and post["facebook"]["video_id"] == "VID1" and rec["state"] == "published"      # 19:00 on every platform: no schedule ahead


def test_facebook_failing_does_not_undo_instagram(tmp_path, monkeypatch):
    monkeypatch.setattr(ig, "_http", two_hosts(FbFake(fail_start=True), IgFake()))
    repo, w = make_repo(tmp_path, instagram=False)
    ig.cmd_publish("E01", go=True, repo=repo, env=dict(ENV), sleep=lambda s: None)
    with pytest.raises(SystemExit):
        fb.cmd_publish("E01", go=True, repo=repo, env=dict(ENV), sleep=lambda s: None)
    post = json.loads((w / "post.json").read_text(encoding="utf-8"))
    assert post["media_id"] == "MEDIA1" and "facebook" not in post and not (w / "facebook.json").exists()


def posted_ig(w):
    (w / "post.json").write_text(json.dumps({"media_id": "MEDIA1", "posted_at": T0.isoformat(), "username": "storywrap"}), encoding="utf-8")


def test_daily_publish_stage_does_not_attempt_facebook_when_instagram_fails(tmp_path, monkeypatch):
    root, w = make_repo(tmp_path, instagram=False)
    ctx = daily.Ctx("E01", root=root, config={"go": True}, budget=daily.Budget(root, limit=1000, today="2026-10-25"), log=lambda *a: None)
    ran = []

    def uv(script, *a, **k):
        ran.append((script, a))
        if script == "ig.py":
            raise daily.StageFail("CHILD", "ig.py publish E01: FAIL [IG-PROCESS] boom")
        return "POSTED E01 to Facebook\n"
    monkeypatch.setattr(ctx, "uv", uv, raising=False)
    monkeypatch.setattr(daily, "token_exists", lambda r: True)
    monkeypatch.setattr(daily, "fb_token_exists", lambda r: True)
    with pytest.raises(daily.StageFail) as e:
        daily.s_publish(ctx)
    assert [r[0] for r in ran] == ["ig.py"] and e.value.code == "PUBLISH-FAILED" and "instagram" in e.value.msg       # Facebook never goes live before Instagram


def test_daily_publish_stage_posts_both_in_order_and_skips_without_any_token(tmp_path, monkeypatch):
    root, w = make_repo(tmp_path, instagram=False)
    ctx = daily.Ctx("E01", root=root, config={"go": True}, budget=daily.Budget(root, limit=1000, today="2026-10-25"), log=lambda *a: None)
    ran = []

    def uv(script, *a, **k):
        ran.append(script)
        if script == "ig.py":
            (w / "post.json").write_text(json.dumps({"media_id": "M", "posted_at": T0.isoformat()}), encoding="utf-8")
        return "POSTED\n"
    monkeypatch.setattr(ctx, "uv", uv, raising=False)
    monkeypatch.setattr(daily, "token_exists", lambda r: True)
    monkeypatch.setattr(daily, "fb_token_exists", lambda r: True)
    assert daily.s_publish(ctx)["posted"] is True and ran == ["ig.py", "fb.py"]
    monkeypatch.setattr(daily, "token_exists", lambda r: False)
    monkeypatch.setattr(daily, "fb_token_exists", lambda r: False)
    assert daily.s_publish(ctx)["_status"] == "skipped"


# ---------------------------------------------------------------- comments, merge, own exclusion, vote
FB_COMMENTS = [
    {"id": "VID1_c1", "message": "على الرف", "created_time": "2026-11-02T01:00:00+0000", "from": {"id": "11", "name": "Sara"}},
    {"id": "VID1_c2", "message": "في يد هدى", "created_time": "2026-11-02T02:00:00+0000", "from": {"id": "12", "name": "Omar"}},
    {"id": "VID1_c3", "message": "على الرف", "created_time": "2026-11-02T03:00:00+0000", "from": {"id": PID, "name": "StoryPage"}},   # the Page itself
]


def ig_comments_file(w):
    (w / "comments.json").write_text(json.dumps({"episode": "E01", "own_usernames": ["storywrap"], "comments": [
        {"id": "i1", "parent_id": None, "text": "على الرف", "username": "ali"},
        {"id": "i2", "parent_id": None, "text": "على الرف", "username": "storywrap"},
        {"id": "VID1_c1", "parent_id": None, "text": "على الرف", "username": "ali2"},   # same raw id as a Facebook one but another platform: kept
    ]}, ensure_ascii=False), encoding="utf-8")


def test_facebook_comments_merge_by_platform_and_id_and_the_page_is_flagged_own(tmp_path, monkeypatch):
    monkeypatch.setattr(ig, "_http", FbFake(comments=FB_COMMENTS + [FB_COMMENTS[0]], replies={"VID1_c1": [{"id": "VID1_r1", "message": "2", "created_time": "t", "from": {"id": "13", "name": "Lina"}}]}))
    repo, w = make_repo(tmp_path)
    (w / "facebook.json").write_text(json.dumps({"video_id": "VID1", "posted_at": T0.isoformat()}), encoding="utf-8")
    ig_comments_file(w)
    res = fb.cmd_comments("E01", repo=repo, env=dict(ENV), at=T0 + timedelta(hours=13))
    keys = [(c["platform"], c["id"]) for c in res["comments"]]
    assert len(keys) == len(set(keys))                                         # the duplicate Facebook c1 was dropped
    assert ("instagram", "VID1_c1") in keys and ("facebook", "VID1_c1") in keys
    assert res["platforms"] == ["facebook", "instagram"] and res["count"] == len(res["comments"]) == 3 + 4
    page = next(c for c in res["comments"] if c["id"] == "VID1_c3")
    assert page["own"] is True and next(c for c in res["comments"] if c["id"] == "VID1_c1" and c["platform"] == "facebook")["own"] is False
    assert next(c for c in res["comments"] if c["id"] == "VID1_r1")["parent_id"] == "VID1_c1"
    again = fb.cmd_comments("E01", repo=repo, env=dict(ENV), at=T0 + timedelta(hours=14))   # a re-harvest replaces Facebook's rows, never doubles them
    assert again["count"] == res["count"]


def test_instagram_harvest_keeps_the_facebook_rows_already_in_the_file(tmp_path, monkeypatch):
    repo, w = make_repo(tmp_path)
    posted_ig(w)
    (w / "comments.json").write_text(json.dumps({"own_usernames": ["StoryPage"], "facebook_video_id": "VID1", "comments": [
        {"id": "VID1_c1", "platform": "facebook", "text": "x", "username": "Sara", "own": False}]}), encoding="utf-8")
    monkeypatch.setattr(ig, "_http", IgFake(comments=[{"id": "C1", "text": "1", "username": "ali", "timestamp": "t"}] * 3))
    res = ig.cmd_comments("E01", repo=repo, env=dict(ENV), at=T0 + timedelta(hours=13))
    assert {c["platform"] for c in res["comments"]} == {"instagram", "facebook"} and "StoryPage" in res["own_usernames"] and "storywrap" in res["own_usernames"]
    assert sum(c["platform"] == "instagram" for c in res["comments"]) == 1      # IG duplicates by id collapse too


def test_vote_is_instagram_only_facebook_rows_feed_ideas_never_the_decision(tmp_path, monkeypatch):
    """Owner rule, the owner 2026-10-25: votes are read from Instagram only; Facebook comments may feed the idea pool, never the decision."""
    monkeypatch.setattr(ig, "_http", FbFake(comments=FB_COMMENTS))
    repo, w = make_repo(tmp_path)
    (w / "facebook.json").write_text(json.dumps({"video_id": "VID1", "posted_at": T0.isoformat()}), encoding="utf-8")
    ig_comments_file(w)
    fb.cmd_comments("E01", repo=repo, env=dict(ENV), at=T0 + timedelta(hours=13))
    ch = [{"id": "1", "text_ar": "١ على الرف"}, {"id": "2", "text_ar": "٢ في يد هدى"}]
    cm = json.loads((w / "comments.json").read_text(encoding="utf-8"))
    res = vote.tally_comments(cm["comments"], ch, set(cm["own_usernames"]))
    # Instagram: ali (1), ali2 (1), storywrap excluded. Facebook: Sara, Omar and the Page's own comment are NOT votes.
    assert res["counts"] == {"1": 2, "2": 0} and res["vote_source"] == "instagram" and res["other_platform_comments"] == 2 and res["excluded_own"] == 2
    only_ig = vote.tally_comments([c for c in cm["comments"] if c["platform"] == "instagram"], ch, set(cm["own_usernames"]))
    assert {k: res[k] for k in ("counts", "winner", "status", "margin")} == {k: only_ig[k] for k in ("counts", "winner", "status", "margin")}
    assert "facebook:VID1_c1" in res["seen_ids"] and "instagram:i1" in res["seen_ids"]


def test_a_facebook_idea_is_kept_with_its_platform_but_is_not_a_vote():
    ch = [{"id": "1", "text_ar": "١ على الرف"}, {"id": "2", "text_ar": "٢ في يد هدى"}]
    fbc = {"id": "f1", "platform": "facebook", "text": "اريد ان اشاهد هدى تكتشف سر المفتاح القديم", "username": "Sara", "own": False}
    res = vote.tally_comments([fbc], ch, set())
    assert res["counted"] == 0 and res["ideas"][0]["platform"] == "facebook" and res["ideas"][0]["names"] == []


def test_harvest_requires_instagram_and_a_facebook_failure_is_partial_not_fatal(tmp_path, monkeypatch):
    repo, w = make_repo(tmp_path, instagram=False)
    (w / "facebook.json").write_text(json.dumps({"video_id": "VID1", "posted_at": T0.isoformat()}), encoding="utf-8")
    monkeypatch.setattr(fb, "cmd_comments", lambda ep, **k: (_ for _ in ()).throw(SystemExit("FAIL [FB-HTTP] down")))
    with pytest.raises(SystemExit) as e:                       # Facebook alone must never become a decision
        fb.harvest("E01", repo=repo, env=dict(ENV))
    assert "FB-HARVEST" in str(e.value) and "Instagram" in str(e.value)
    posted_ig(w)
    seen = []
    monkeypatch.setattr(ig, "cmd_comments", lambda ep, **k: seen.append("ig") or {})
    r = fb.harvest("E01", repo=repo, env=dict(ENV))
    assert seen == ["ig"] and r["done"] == ["instagram"] and r["partial"] is True and "FB-HTTP" in r["errors"]["facebook"]
    monkeypatch.setattr(ig, "cmd_comments", lambda ep, **k: (_ for _ in ()).throw(SystemExit("FAIL [IG-HTTP] down")))
    with pytest.raises(SystemExit) as e:                       # Instagram failing is fatal: nothing is finalised from a Facebook-only read
        fb.harvest("E01", repo=repo, env=dict(ENV))
    assert "IG-HTTP" in str(e.value)


def test_facebook_too_early_never_blocks_or_alters_the_instagram_decision(tmp_path, monkeypatch, capsys):
    """Real callers: fb.harvest (the CLI exit code) -> ig.cmd_comments -> fb.cmd_comments (FB-TOO-EARLY) -> vote.cmd_tally."""
    igf = IgFake(comments=[{"id": "C1", "text": "على الرف", "username": "ali", "timestamp": "t1"}, {"id": "C2", "text": "في يد هدى", "username": "omar", "timestamp": "t2"}])
    monkeypatch.setattr(ig, "_http", two_hosts(FbFake(comments=FB_COMMENTS), igf))
    repo, w = make_repo(tmp_path)
    posted_ig(w)                                                                   # Instagram at T0
    (w / "facebook.json").write_text(json.dumps({"video_id": "VID1", "posted_at": T0.isoformat(), "publish_at": (T0 + timedelta(hours=1)).isoformat()}), encoding="utf-8")
    monkeypatch.setattr(ig, "now", lambda: T0 + timedelta(hours=12, minutes=30))     # Instagram's 12 h are over; Facebook's go-live was +60 min, so its are not
    monkeypatch.setattr(fb, "now", lambda: T0 + timedelta(hours=12, minutes=30))
    monkeypatch.setattr(ig, "load_env", lambda path=None: dict(ENV))
    real = fb.harvest
    monkeypatch.setattr(fb, "harvest", lambda ep, force=False: real(ep, force, repo=repo))       # the CLI entry point on the temp repo
    rc = fb.main(["harvest", "E01"])
    out = capsys.readouterr().out
    assert rc == 3 and "PARTIAL" in out and "FB-TOO-EARLY" in out
    cm = json.loads((w / "comments.json").read_text(encoding="utf-8"))
    assert {c["platform"] for c in cm["comments"]} == {"instagram"}                # no Facebook row got in
    dec = vote.cmd_tally("E01", repo)
    assert dec["vote_source"] == "instagram" and dec["counts"] == {"1": 1, "2": 1} and dec["total_comments"] == 2


def test_harvest_due_reports_partial_but_still_decides(tmp_path):
    repo, w = make_repo(tmp_path)
    (repo / "board").mkdir()
    (repo / "board" / "schedule.json").write_text(sw_fixtures.SCHEDULE.read_text(encoding="utf-8"), encoding="utf-8")
    (repo / "work" / "daily").mkdir(parents=True, exist_ok=True)
    when = datetime.now(timezone.utc) - timedelta(days=2)          # the harvest is due 14:00 the day after the post
    (w / "post.json").write_text(json.dumps({"media_id": "M", "posted_at": when.isoformat()}), encoding="utf-8")
    calls = []
    res = ig_board.harvest_due(repo, go=True, at=datetime.now(), token=True,
                               do_comments=lambda ep: {"done": ["instagram"], "errors": {"facebook": "FAIL [FB-TOO-EARLY] 1.0 h"}, "partial": True},
                               do_tally=lambda ep: calls.append("tally"), do_next=lambda ep: calls.append("next"), do_metrics=None)
    assert calls == ["tally", "next"] and res["harvested"] == ["E01"] and res["status"] == "PARTIAL" and "FB-TOO-EARLY" in res["detail"]


def test_harvest_is_due_at_14_00_the_day_after_the_later_of_the_two_posts(tmp_path):
    import loop_gate
    repo, w = make_repo(tmp_path)
    t = datetime(2026, 10, 30, 16, 0, tzinfo=timezone.utc)      # a fixed 19:00 Amman post: datetime.now() put the +1 h post past midnight late at night, where R-507's late-post harvest rule applies instead
    (w / "post.json").write_text(json.dumps({"media_id": "M", "posted_at": t.isoformat()}), encoding="utf-8")
    nextday = lambda x: datetime.combine(x.date() + timedelta(days=1), datetime.min.time()).replace(hour=14)      # noqa: E731
    assert loop_gate.harvest_due_at(repo, "E01") == nextday(loop_gate.parse_time(t.isoformat()))
    (w / "facebook.json").write_text(json.dumps({"video_id": "V", "posted_at": t.isoformat(), "publish_at": (t + timedelta(hours=1)).isoformat()}), encoding="utf-8")
    assert loop_gate.harvest_due_at(repo, "E01") == nextday(loop_gate.parse_time(t.isoformat()) + timedelta(hours=1))
    assert loop_gate.later_post_at(repo, "E01") == loop_gate.parse_time(t.isoformat()) + timedelta(hours=1)


def test_late_pass_files_new_comments_as_ideas_and_never_touches_the_decision(tmp_path, monkeypatch):
    repo, w = make_repo(tmp_path)
    posted_ig(w)
    (w / "facebook.json").write_text(json.dumps({"video_id": "VID1", "posted_at": T0.isoformat(), "publish_at": (T0 + timedelta(hours=1)).isoformat()}), encoding="utf-8")
    dec = {"episode": "E01", "counts": {"1": 1, "2": 0}, "winner": None, "seen_ids": ["instagram:C1"]}
    (w / "decision.json").write_text(json.dumps(dec), encoding="utf-8")
    before = (w / "decision.json").read_text(encoding="utf-8")
    igf = IgFake(comments=[{"id": "C1", "text": "على الرف", "username": "ali", "timestamp": "t1"},
                           {"id": "C9", "text": "اريد ان اشاهد هدى تكتشف سر المفتاح القديم", "username": "late", "timestamp": "t9"}])
    fbc = [{"id": "VID1_L1", "message": "قصة جميلة جدا اتمنى ان ارى المزيد من الاسرار", "created_time": "t", "from": {"id": "77", "name": "Nour"}}]
    monkeypatch.setattr(ig, "_http", two_hosts(FbFake(comments=fbc), igf))
    out = fb.late_pass("E01", repo=repo, env=dict(ENV), at=T0 + timedelta(hours=25))
    ideas = json.loads((w / "late-ideas.json").read_text(encoding="utf-8"))
    assert {i["platform"] for i in ideas["ideas"]} == {"instagram", "facebook"} and all(i["id"] != "C1" for i in ideas["ideas"]) and out["count"] == 2
    assert (w / "decision.json").read_text(encoding="utf-8") == before


# ---------------------------------------------------------------- BLOCKER 1: the lost finish response
def uv_in_process(root, env, calls=None):
    """ctx.uv replacement that runs ig.py / fb.py in this process, the way the real child would, and turns a SystemExit into the StageFail ctx.uv raises."""
    def uv(script, *a, **k):
        try:
            mod = ig if script == "ig.py" else fb
            if a[0] == "publish":
                kw = dict(go="--go" in a, repo=root, env=env, sleep=lambda s: None)
                mod.cmd_publish(a[1], **kw)
            return "POSTED\n"
        except SystemExit as e:
            raise daily.StageFail("CHILD", f"{script} {a[0]} {a[1]}: {e}")
    return uv


class LostFinish(FbFake):
    """The finish call goes through on Facebook's side but its answer is lost (a dead connection after the request)."""
    def __init__(self):
        super().__init__()
        self.finish_calls = 0

    def __call__(self, method, url, headers=None, data=None):
        if data and b"upload_phase=finish" in data:
            self.finish_calls += 1
            self.calls.append((method, url, dict(headers or {}), data))
            import urllib.error
            raise urllib.error.URLError(f"connection lost near {FB_TOKEN}")
        return super().__call__(method, url, headers, data)


def test_a_lost_finish_response_leaves_a_pending_record_and_a_retry_needs_force(tmp_path, monkeypatch):
    lost = LostFinish()
    monkeypatch.setattr(ig, "_http", lost)
    repo, w = make_repo(tmp_path)
    with pytest.raises(SystemExit) as e:
        fb.cmd_publish("E01", go=True, repo=repo, env=dict(ENV), sleep=lambda s: None)
    assert "FB-FINISH-UNKNOWN" in str(e.value) and FB_TOKEN not in str(e.value)
    rec = record(w)
    assert rec["state"] == "finishing" and rec["video_id"] == "VID1" and fb.is_posted("E01", repo)
    with pytest.raises(SystemExit) as e:                                               # a plain retry is refused
        fb.cmd_publish("E01", go=True, repo=repo, env=dict(ENV), sleep=lambda s: None)
    assert "FB-ALREADY" in str(e.value) and lost.finish_calls == 1


def test_a_lost_finish_response_through_the_daily_stage_never_posts_twice(tmp_path, monkeypatch):
    lost = LostFinish()
    monkeypatch.setattr(ig, "_http", two_hosts(lost, IgFake()))
    root, w = make_repo(tmp_path)
    ctx = daily.Ctx("E01", root=root, config={"go": True}, budget=daily.Budget(root, limit=1000, today="2026-10-25"), log=lambda *a: None)
    monkeypatch.setattr(ctx, "uv", uv_in_process(root, dict(ENV)), raising=False)
    monkeypatch.setattr(daily, "token_exists", lambda r: True)
    monkeypatch.setattr(daily, "fb_token_exists", lambda r: True)
    r = daily.s_publish(ctx)                                                           # Instagram posted, Facebook's answer lost
    assert r["_status"] == "partial" and "FB-FINISH-UNKNOWN" in r["facebook_error"] and (w / "post.json").is_file()
    r2 = daily.s_publish(ctx)                                                          # the retry sees the pending record: Facebook is NOT attempted again
    assert lost.finish_calls == 1 and r2.get("_status") != "partial" and r2["posted"] is True


# ---------------------------------------------------------------- fix 4: PARTIAL does not stop the schedule stage
def test_partial_publish_still_lets_the_schedule_stage_run_and_is_retried(tmp_path, monkeypatch):
    root, w = make_repo(tmp_path)
    ctx = daily.Ctx("E01", root=root, config={"go": True}, budget=daily.Budget(root, limit=1000, today="2026-10-25"), log=lambda *a: None)
    monkeypatch.setattr(daily, "token_exists", lambda r: True)
    monkeypatch.setattr(daily, "fb_token_exists", lambda r: True)
    posted_ig(w)

    def uv(script, *a, **k):
        if script == "fb.py":
            raise daily.StageFail("CHILD", "fb.py publish E01: FAIL [FB-HTTP] down")
        return "x\n"
    monkeypatch.setattr(ctx, "uv", uv, raising=False)
    assert daily.run_stage(ctx, daily.STAGES["publish"]) == "partial"
    assert daily.stage_state(ctx, daily.STAGES["publish"])[0] == "stale"                # so the next run retries Facebook; Instagram is skipped as done
    for n in daily.RUN_STAGES:                                                          # production stages fresh: only the publish gap matters here
        monkeypatch.setitem(ctx.state["stages"], n, {"status": "ok"})
    monkeypatch.setattr(daily, "stage_state", lambda c, st: ("fresh", "") if st.name in daily.RUN_STAGES else ("stale", "last status partial"))
    daily.require_upstream(ctx, daily.RUN_STAGES + ["publish"])                          # does not raise UPSTREAM-NOT-VERIFIED
    # Instagram failing: Facebook is not attempted and the stage fails
    (w / "post.json").unlink()

    def uv2(script, *a, **k):
        if script == "ig.py":
            raise daily.StageFail("CHILD", "ig.py publish E01: FAIL [IG-HTTP] down")
        return "x\n"
    monkeypatch.setattr(ctx, "uv", uv2, raising=False)
    with pytest.raises(daily.StageFail) as e:
        daily.s_publish(ctx)
    assert e.value.code == "PUBLISH-FAILED"


# ---------------------------------------------------------------- fix 3: Facebook-only row and alert
def test_facebook_only_post_shows_a_row_and_a_health_alert(tmp_path):
    repo, w = make_repo(tmp_path, instagram=False)
    (w / "facebook.json").write_text(json.dumps({"video_id": "VID1", "posted_at": T0.isoformat(), "state": "published", "permalink": "https://www.facebook.com/reel/VID1/"}), encoding="utf-8")
    rows = ig_board.posts_block(repo)
    assert len(rows) == 1 and rows[0]["instagram"] is False and "NOT on Instagram" in rows[0]["alert"] and rows[0]["facebook"]["permalink"].endswith("/reel/VID1/")
    h = ig_board.health_block(repo, datetime(2026, 11, 2), env=dict(ENV))
    assert any("on Facebook but NOT on Instagram" in a for a in h["alerts"])
    import loop_gate
    assert loop_gate.check("E02", repo, token=True, prev="E01")["code"] == "WAIT-POST"        # the loop still waits for Instagram, the vote source


# ---------------------------------------------------------------- fix 5: upload host, redirects, unreadable record
def test_the_page_token_is_sent_only_to_facebook_com_hosts(tmp_path, monkeypatch):
    assert fb.upload_host_ok("https://rupload.facebook.com/video-upload/v26.0/1") and fb.upload_host_ok("https://facebook.com/x")
    for bad in ("https://evil.example/facebook.com", "https://facebook.com.evil.example/x", "http://rupload.facebook.com/x", "https://notfacebook.com/x", ""):
        assert not fb.upload_host_ok(bad)

    class Evil(FbFake):
        def __call__(self, method, url, headers=None, data=None):
            if data and b"upload_phase=start" in data:
                self.calls.append((method, url, dict(headers or {}), data))
                return {"video_id": "VID1", "upload_url": "https://attacker.example/up"}
            return super().__call__(method, url, headers, data)
    ev = Evil()
    monkeypatch.setattr(ig, "_http", ev)
    repo, w = make_repo(tmp_path)
    with pytest.raises(SystemExit) as e:
        fb.cmd_publish("E01", go=True, repo=repo, env=dict(ENV), sleep=lambda s: None)
    assert "FB-START" in str(e.value) and not any("attacker" in c[1] for c in ev.calls) and not (w / "facebook.json").exists()


def test_http_never_follows_a_redirect_so_the_oauth_header_cannot_leave():
    import urllib.request
    h = ig._NoRedirect()
    req = urllib.request.Request("https://rupload.facebook.com/x", headers={"Authorization": "OAuth secret"})
    assert h.redirect_request(req, None, 302, "Found", {}, "https://attacker.example/y") is None
    assert any(isinstance(x, ig._NoRedirect) for x in ig._OPENER.handlers)


def test_an_unreadable_facebook_json_counts_as_posted_and_does_not_crash(tmp_path, fbf):
    repo, w = make_repo(tmp_path)
    (w / "facebook.json").write_text("{not json", encoding="utf-8")
    assert fb.is_posted("E01", repo) and fb.load_record("E01", repo) == {"corrupt": True}
    with pytest.raises(SystemExit) as e:
        fb.cmd_publish("E01", go=True, repo=repo, env=dict(ENV))
    assert "FB-ALREADY" in str(e.value) and fbf.calls == []
    (w / "post.json").write_text(json.dumps({"media_id": "M", "posted_at": T0.isoformat()}), encoding="utf-8")
    import loop_gate
    assert loop_gate.fb_recorded(repo, "E01") and not loop_gate.fb_pending(repo, "E01")
    assert fb.cmd_status(repo=repo, env=dict(ENV))                                    # status survives it
    ctx = daily.Ctx("E01", root=repo, config={"go": True}, budget=daily.Budget(repo, limit=1000, today="2026-10-25"), log=lambda *a: None)
    ran = []
    ctx.uv = lambda script, *a, **k: ran.append(script) or "x\n"
    import unittest.mock as m
    with m.patch.object(daily, "token_exists", lambda r: False), m.patch.object(daily, "fb_token_exists", lambda r: True):
        daily.s_publish(ctx)
    assert ran == []                                                                   # the daily stage does not touch Facebook over an unreadable record


def test_network_errors_are_wrapped_and_redacted(tmp_path, monkeypatch):
    import socket
    import urllib.error

    def boom(method, url, headers=None, data=None):
        raise urllib.error.URLError(socket.timeout(f"timed out talking to {FB_TOKEN}"))
    monkeypatch.setattr(ig, "_http", boom)
    with pytest.raises(SystemExit) as e:
        fb.api(dict(ENV), "GET", PID, {"fields": "name"})
    assert "FB-HTTP" in str(e.value) and FB_TOKEN not in str(e.value)
    monkeypatch.setattr(ig, "_http", lambda *a, **k: (_ for _ in ()).throw(ValueError("bad json " + FB_TOKEN)))
    with pytest.raises(SystemExit) as e:
        fb.api(dict(ENV), "GET", PID)
    assert "FB-HTTP" in str(e.value) and FB_TOKEN not in str(e.value)


# ---------------------------------------------------------------- DESIGN section 4/6: captions, title, AI label, scheduled go-live
E01C_IG = """الحلقة ١ | the series 🧳 حقيبة وصلت مع الريح، وعليها اسم هدى وتاريخ الخميس القادم

🕯️ هدى موظفة جديدة، وكل شيء هنا له بطاقة.
🔑 وفي الحقيبة مفتاح قديم لا يناسب أي قفل.
👀 وفي المكتب رف واحد بلا رقم.

❓ أين تضعون الحقيبة الليلة: على الرف الذي بلا رقم، أم في يد هدى؟
💬 قولوا لنا لماذا، وماذا تتوقعون أن يحدث بعد ذلك.

الحلقة القادمة تتبع ما تكتبونه.

#المكتب #قصص_متحركة #حكايات
"""


def put_caption(repo, text, name="caption.txt"):
    (repo / "bible/series/s/episodes/E01" / name).write_text(text, encoding="utf-8")


def test_facebook_gets_its_own_title_hook_first_line_and_two_hashtags(tmp_path):
    repo, w = make_repo(tmp_path)
    put_caption(repo, E01C_IG)
    assert ig.build_caption("E01", repo) == ig.display_text(E01C_IG).rstrip("\n") or ig.build_caption("E01", repo).strip() == E01C_IG.strip()
    title, desc = ig.facebook_parts("E01", repo)
    assert title == "the series | الحلقة ١"
    assert desc.splitlines()[0] == "حقيبة وصلت مع الريح، وعليها اسم هدى وتاريخ الخميس القادم 🧳"
    assert "الحلقة ١ من the series. الحلقة القادمة تتبع ما تكتبونه." in desc and desc.strip().endswith("#المكتب #قصص_متحركة") and desc.count("#") == 2
    assert not ig.caption_problems(E01C_IG, "instagram") and not ig.caption_problems(desc, "facebook")
    assert E01C_IG.count("#") == 3
    put_caption(repo, "حقيبة 🧳\n\n❓ سؤال؟\n\nالحلقة ١ من the series.\n\n#a #b", "caption-facebook.txt")        # the writer's own Facebook text wins
    assert ig.facebook_parts("E01", repo)[1].startswith("حقيبة")


def test_bait_wording_is_refused_on_both_platforms(tmp_path, fbf):
    for bad in ("اكتبوا اختياركم بكلماتكم", "علقوا برقم", "صوتوا الآن", "اختاروا واحدا", "شاركوا الفيديو", "اضغطوا اعجاب", "تابعوا لتعرفوا", "علقوا 1 أو 2", "comment 1 or 2"):
        assert ig.caption_problems("الحلقة ١ 🧳\n" + bad, "instagram"), bad
    assert ig.caption_problems("x #a #b #c #d") and ig.caption_problems("x #a #b #c", "facebook")
    repo, w = make_repo(tmp_path, instagram=False)
    put_caption(repo, "الحلقة ١ | the series 🧳 خطاف\n\nاكتبوا اختياركم بكلماتكم\n\n#أ")
    with pytest.raises(SystemExit) as e:
        ig.cmd_publish("E01", go=True, repo=repo, env=dict(ENV))
    assert "IG-CAPTION-BAIT" in str(e.value)
    (w / "post.json").write_text(json.dumps({"media_id": "M", "posted_at": T0.isoformat()}), encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        fb.cmd_publish("E01", go=True, repo=repo, env=dict(ENV))
    assert "FB-CAPTION-BAIT" in str(e.value) and fbf.calls == []


def test_finish_carries_title_ai_label_and_the_description(tmp_path, fbf):
    repo, w = make_repo(tmp_path)
    put_caption(repo, E01C_IG)
    fb.cmd_publish("E01", go=True, repo=repo, env=dict(ENV), sleep=lambda s: None)
    body = urllib_parse(next(c for c in fbf.calls if c[3] and b"upload_phase=finish" in c[3])[3].decode())
    assert body["is_ai_generated"] == "true" and body["title"] == "the series | الحلقة ١" and body["description"].startswith("حقيبة وصلت مع الريح")
    assert body["video_state"] == "PUBLISHED" and "scheduled_publish_time" not in body        # Instagram not posted: nothing to follow


def urllib_parse(qs):
    import urllib.parse
    return {k: v[0] for k, v in urllib.parse.parse_qs(qs).items()}


def test_facebook_is_scheduled_when_a_delay_is_configured(tmp_path, fbf, monkeypatch):
    """Since 2026-10-27 FB_AFTER_IG_MIN is 0 (19:00 everywhere, test_autopilot.py); the scheduling mechanism stays, here with a 60 min delay."""
    monkeypatch.setattr(fb, "FB_AFTER_IG_MIN", 60)
    repo, w = make_repo(tmp_path)
    ig_at = datetime.now(timezone.utc).replace(microsecond=0)
    (w / "post.json").write_text(json.dumps({"media_id": "M", "posted_at": ig_at.isoformat(), "username": "storywrap"}), encoding="utf-8")
    rec = fb.cmd_publish("E01", go=True, repo=repo, env=dict(ENV), sleep=lambda s: None)
    body = urllib_parse(next(c for c in fbf.calls if c[3] and b"upload_phase=finish" in c[3])[3].decode())
    assert body["video_state"] == "SCHEDULED" and int(body["scheduled_publish_time"]) == int((ig_at + timedelta(minutes=60)).timestamp())
    assert rec["state"] == "scheduled" and rec["publish_at"] == (ig_at + timedelta(minutes=60)).isoformat()
    # an Instagram post older than 49 minutes cannot be followed by a 60-minute-later schedule: the Reel goes out at once
    assert fb.plan_go_live("E01", repo, ig_at + timedelta(minutes=50)) is None and fb.plan_go_live("E01", repo, ig_at + timedelta(minutes=49)) is not None


def test_a_refused_video_is_reported_not_trimmed(tmp_path, monkeypatch):
    class Refuse(FbFake):
        def __call__(self, method, url, headers=None, data=None):
            if url.split("?")[0].endswith("/VID1") and "fields=status" in url:
                return {"status": {"video_status": "error", "processing_phase": {"status": "error", "errors": [{"message": "video too long"}]}}}
            return super().__call__(method, url, headers, data)
    monkeypatch.setattr(ig, "_http", Refuse())
    repo, w = make_repo(tmp_path)
    with pytest.raises(SystemExit) as e:
        fb.cmd_publish("E01", go=True, repo=repo, env=dict(ENV), sleep=lambda s: None)
    assert "FB-PROCESS" in str(e.value) and "video too long" in str(e.value) and "NOT trimmed" in str(e.value) and record(w)["state"] == "not-ready:error"
    assert (w / "episode.mp4").read_bytes() == b"\x00" * 64


# ---------------------------------------------------------------- DESIGN 5.4: the vote reads free answers
CH2 = [{"id": "1", "text_ar": "على الرف الذي بلا رقم", "variants": ["أتركها على الرف", "خلوها على الرف", "أحطها على الرف"]},
       {"id": "2", "text_ar": "في يد هدى", "variants": ["تبقى معها", "تحملها هدى", "خليها مع هدى", "تبقى في يدها"]}]


def votes(*rows, min_votes=1):
    cms = [{"id": str(i), "text": t, "username": u, "timestamp": f"2026-11-02T0{i}:00:00"} for i, (u, t) in enumerate(rows)]
    return vote.tally_comments(cms, CH2, set(), min_votes)


def test_a_reason_naming_the_other_side_does_not_cancel_the_vote():
    r = votes(("a", "أتركها على الرف لأن في يد هدى الحقيبة قديمة وتحتاج مكانا هادئا"))
    assert r["counts"] == {"1": 1, "2": 0} and r["strong"] == {"1": 1, "2": 0}
    assert r["ideas"] and "في يد هدى" in r["ideas"][0]["text"]                     # the reason is kept as an idea


def test_negation_flips_a_two_option_answer_and_marks_it_weak():
    r = votes(("a", "لا أتركها على الرف"))
    assert r["counts"] == {"1": 0, "2": 1} and r["via"]["2"].get("flip") == 1 and r["weak"]["2"] == 1 and r["strong"]["2"] == 0
    r = votes(("a", "لا على الرف ولا في يد هدى"))
    assert r["counted"] == 0 and len(r["ambiguous"]) == 1                          # unclear: nobody's vote, listed for the writer


def test_a_choices_own_negator_is_not_a_negation():
    ch = [{"id": "1", "text_ar": "على الرف"}, {"id": "2", "text_ar": "في يد هدى لا تفارقها"}]
    r = vote.tally_comments([{"id": "1", "text": "لا تفارقها", "username": "a"}], ch, set(), 1)
    assert r["counts"] == {"1": 0, "2": 1}


def test_gulf_dialect_answers_count_as_strong_votes_through_listed_variants():
    r = votes(("a", "خلوها على الرف"), ("b", "خليها مع هدى عشان تحميها"), ("c", "أحطها على الرف"))
    assert r["counts"] == {"1": 2, "2": 1} and r["strong"] == {"1": 2, "2": 1}


def test_digit_only_answers_count_but_only_as_weak_votes():
    r = votes(("a", "1"), ("b", "٢"))
    assert r["counts"] == {"1": 1, "2": 1} and r["weak"] == {"1": 1, "2": 1} and r["strong"] == {"1": 0, "2": 0}


def test_strong_votes_decide_first_and_weak_ones_only_break_a_strong_tie():
    rows = [(f"s{i}", "أتركها على الرف") for i in range(5)] + [(f"w{i}", "٢") for i in range(8)]
    r = votes(*rows, min_votes=5)
    assert r["winner"] == "1" and r["basis"] == "strong" and r["counts"] == {"1": 5, "2": 8}
    rows = [(f"s{i}", "أتركها على الرف") for i in range(3)] + [(f"t{i}", "تبقى معها") for i in range(3)] + [(f"w{i}", "٢") for i in range(2)]
    r = votes(*rows, min_votes=5)
    assert r["winner"] == "2" and r["basis"] == "all"                              # strong 3-3 ties, the weak votes decide


def test_one_vote_per_account_the_latest_counted_comment():
    r = votes(("same", "أتركها على الرف"), ("other", "تبقى معها"), ("same", "تبقى معها"))
    assert r["counts"] == {"1": 0, "2": 2} and r["duplicates_collapsed"] == 1
    r = vote.tally_comments([{"id": "1", "text": "تبقى معها", "username": "x", "user_id": "9"}, {"id": "2", "text": "تبقى معها", "username": "x2", "user_id": "9"}], CH2, set(), 1)
    assert r["counts"]["2"] == 1


def test_e01c_replay_on_a_made_up_comment_set():
    rows = [("u1", "أتركها على الرف لأنها بلا رقم"), ("u2", "تبقى مع هدى"), ("u3", "في يد هدى طبعا"), ("u4", "على الرف الذي بلا رقم"), ("u5", "خلوها على الرف"),
            ("u6", "لا أتركها على الرف"), ("u7", "حلقة جميلة جدا وأتمنى أن أرى المزيد من الأسرار"), ("u1", "تبقى معها")]
    r = votes(*rows, min_votes=5)
    assert r["counts"] == {"1": 2, "2": 4} and r["duplicates_collapsed"] == 1 and r["idea_count"] >= 1
    assert r["winner"] == "2" and r["status"] == "AUDIENCE" and r["weak"]["2"] == 2     # u2 (words) and u6 (a negation flip) are weak


def test_comments_wait_12_hours_and_need_a_facebook_post(tmp_path, fbf):
    repo, w = make_repo(tmp_path)
    with pytest.raises(SystemExit) as e:
        fb.cmd_comments("E01", repo=repo, env=dict(ENV))
    assert "FB-NOPOST" in str(e.value)
    (w / "facebook.json").write_text(json.dumps({"video_id": "VID1", "posted_at": T0.isoformat()}), encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        fb.cmd_comments("E01", repo=repo, env=dict(ENV), at=T0 + timedelta(hours=2))
    assert "FB-TOO-EARLY" in str(e.value) and fbf.calls == []


# ---------------------------------------------------------------- status, metrics, board
def test_status_reports_token_state_and_makes_a_live_page_check(tmp_path, fbf, capsys):
    repo, w = make_repo(tmp_path)
    s = fb.cmd_status(live=True, repo=repo, env=dict(ENV))
    assert "Page token present" in s and "'StoryPage'" in s and fbf.calls[0][1].endswith(f"/{PID}?fields=name") and fbf.calls[0][0] == "GET"
    assert "no Facebook Page token" in fb.token_state({})


def test_metrics_reads_counts_into_its_own_file(tmp_path, fbf):
    repo, w = make_repo(tmp_path)
    (w / "facebook.json").write_text(json.dumps({"video_id": "VID1", "posted_at": T0.isoformat(), "permalink": "https://www.facebook.com/reel/VID1/"}), encoding="utf-8")
    res = fb.cmd_metrics("E01", repo=repo, env=dict(ENV))
    assert res["likes"] == 7 and res["comments"] == 3 and (w / "metrics-facebook.json").is_file() and not (w / "metrics.json").exists()


def test_board_shows_the_facebook_status_and_link_next_to_instagram(tmp_path):
    repo, w = make_repo(tmp_path)
    posted_ig(w)
    (w / "facebook.json").write_text(json.dumps({"video_id": "VID1", "posted_at": T0.isoformat(), "state": "published", "permalink": "https://www.facebook.com/reel/VID1/"}), encoding="utf-8")
    row = ig_board.posts_block(repo)[0]
    assert row["facebook"]["permalink"].endswith("/reel/VID1/") and row["facebook"]["state"] == "published" and "permalink" in row
    h = ig_board.health_block(repo, datetime(2026, 11, 2), env=dict(ENV))
    assert h["facebook_token"]["present"] is True and FB_TOKEN not in json.dumps(h)


def test_board_comment_rows_carry_the_platform_and_facebook_comments_get_no_ig_reply_draft(tmp_path):
    repo, w = make_repo(tmp_path)
    posted_ig(w)
    (w / "comments.json").write_text(json.dumps({"own_usernames": ["storywrap"], "comments": [
        {"id": "i1", "platform": "instagram", "text": "على الرف", "username": "ali"},
        {"id": "f1", "platform": "facebook", "text": "على الرف", "username": "Sara", "own": False},
        {"id": "f2", "platform": "facebook", "text": "x", "username": "StoryPage", "own": True}]}, ensure_ascii=False), encoding="utf-8")
    cb = ig_board.comments_block(repo)
    by = {r["id"]: r for r in cb["comments"]}
    assert by["f1"]["platform"] == "facebook" and by["f2"]["own"] is True
    assert [r["id"] for r in cb["replies"]] == ["i1"]                      # replies go through ig.py only


def test_loop_gate_retries_only_a_recent_instagram_post_on_facebook(tmp_path):
    import loop_gate
    repo, w = make_repo(tmp_path)
    now = datetime.now()
    (w / "post.json").write_text(json.dumps({"media_id": "M", "posted_at": datetime.now(timezone.utc).isoformat()}), encoding="utf-8")
    assert loop_gate.fb_pending(repo, "E01") is True
    (w / "facebook.json").write_text(json.dumps({"video_id": "VID1"}), encoding="utf-8")
    assert loop_gate.fb_pending(repo, "E01") is False
    (w / "facebook.json").unlink()
    assert loop_gate.fb_pending(repo, "E01", at=now + timedelta(hours=40)) is False       # an old episode is never back-filled


# ---------------------------------------------------------------- review round 2
def test_the_question_word_ma_is_not_a_negation():
    r = votes(("a", "ما رأيكم بالرف؟"))
    assert r["counts"] == {"1": 1, "2": 0} and r["via"]["1"].get("flip") is None
    r = votes(("a", "ما رأيكم بالباب الأزرق؟"))
    assert r["counted"] == 0
    r = votes(("a", "ليس على الرف"))                                                  # the real negators still flip
    assert r["counts"] == {"1": 0, "2": 1}


def test_post_due_has_a_latest_cutoff_after_the_retry_window(tmp_path):
    import loop_gate as lg
    root = tmp_path
    day = datetime(2026, 11, 3).date()
    at = lambda h, m: datetime.combine(day, datetime.min.time()).replace(hour=h, minute=m)      # noqa: E731
    assert lg.post_due("E02", at(18, 59), root)["code"] == "WAIT-SLOT"
    assert lg.post_due("E02", at(19, 0), root)["due"] is True and lg.post_due("E02", at(20, 20), root)["due"] is True
    late = lg.post_due("E02", at(22, 0), root)                                           # a PC waking at 22:00 with -StartWhenAvailable
    assert late["due"] is False and late["code"] == "WAIT-LATE" and "tomorrow" in late["why"]
    assert lg.post_due("E02", at(19, 0) + timedelta(days=1), root)["due"] is True        # the next day's slot is open again


def test_a_failed_permalink_read_still_leaves_post_json_so_instagram_is_never_posted_twice(tmp_path, monkeypatch):
    class NoPermalink(IgFake):
        def __call__(self, method, url, headers=None, data=None):
            if url.split("?")[0].endswith("/MEDIA1"):
                raise RuntimeError("HTTP 500 GET " + url.split("?")[0] + ": boom")
            return super().__call__(method, url, headers, data)
    monkeypatch.setattr(ig, "_http", NoPermalink())
    repo, w = make_repo(tmp_path, instagram=False)
    rec = ig.cmd_publish("E01", go=True, repo=repo, env=dict(ENV), sleep=lambda s: None)
    post = json.loads((w / "post.json").read_text(encoding="utf-8"))
    assert post["media_id"] == "MEDIA1" and post["permalink"] is None and rec["media_id"] == "MEDIA1"
    with pytest.raises(SystemExit) as e:
        ig.cmd_publish("E01", go=True, repo=repo, env=dict(ENV), sleep=lambda s: None)
    assert "IG-ALREADY" in str(e.value)

    class Metrics(IgFake):
        def __call__(self, method, url, headers=None, data=None):
            if url.split("?")[0].endswith("/MEDIA1"):
                return {"like_count": 2, "comments_count": 1, "permalink": "https://www.instagram.com/reel/zzz/", "timestamp": "t"}
            return super().__call__(method, url, headers, data)
    monkeypatch.setattr(ig, "_http", Metrics())
    ig.cmd_metrics("E01", repo=repo, env=dict(ENV))
    assert json.loads((w / "post.json").read_text(encoding="utf-8"))["permalink"].endswith("/reel/zzz/")       # filled in later


def test_the_scheduled_harvest_plan_tolerates_exit_3_but_stops_on_a_real_failure(tmp_path):
    repo, w = make_repo(tmp_path)
    cmd = ig.cmd_plan("E01", repo)
    assert "fb.py harvest E01 & if errorlevel 4 exit /b 1 & if not errorlevel 3 if errorlevel 1 exit /b 1 & uv run tools/vote.py tally E01" in cmd


def test_the_late_pass_gives_up_after_three_tries_and_says_so(tmp_path):
    repo, w = make_repo(tmp_path)
    (repo / "board").mkdir()
    (repo / "board" / "schedule.json").write_text(sw_fixtures.SCHEDULE.read_text(encoding="utf-8"), encoding="utf-8")
    (repo / "work" / "daily").mkdir(parents=True, exist_ok=True)
    when = datetime.now(timezone.utc) - timedelta(hours=30)
    (w / "post.json").write_text(json.dumps({"media_id": "M", "posted_at": when.isoformat()}), encoding="utf-8")
    (w / "decision.json").write_text(json.dumps({"episode": "E01", "counts": {"1": 1, "2": 0}, "choices": []}), encoding="utf-8")
    calls = []

    def boom(ep):
        calls.append(ep)
        raise SystemExit("FAIL [IG-HTTP] down")
    for _ in range(5):
        ig_board.harvest_due(repo, go=True, at=datetime.now(), token=True, do_comments=lambda e: None, do_tally=lambda e: None, do_next=lambda e: None, do_metrics=None, do_late=boom)
    assert len(calls) == 3
    done = json.loads((w / "late-ideas.json").read_text(encoding="utf-8"))
    assert done["status"] == "late-pass-gave-up" and done["ideas"] == []


def test_the_bait_check_covers_the_facebook_title_too(tmp_path, fbf):
    repo, w = make_repo(tmp_path)
    put_caption(repo, "x 🧳 خطاف\n\nسؤال؟\n\n#أ", "caption-facebook.txt")
    (repo / "bible/series/s/episodes/E01" / "title-facebook.txt").write_text("صوتوا الآن | الحلقة ١", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        fb.cmd_publish("E01", go=True, repo=repo, env=dict(ENV))
    assert "FB-CAPTION-BAIT" in str(e.value) and "title:" in str(e.value) and fbf.calls == []


def test_page_seo_dry_run_reads_only_and_a_refused_write_is_reported_not_worked_around(monkeypatch):
    calls = []

    def http(method, url, headers=None, data=None):
        calls.append(method)
        if method == "POST":
            raise RuntimeError('HTTP 400 POST x: {"error":{"message":"(#283) Requires pages_manage_metadata permission","code":283}}')
        return {"id": PID, "name": "StoryPage", "about": "old", "category": "Digital creator"}
    monkeypatch.setattr(ig, "_http", http)
    out = fb.cmd_page_seo(go=False, env=ENV)
    assert out["mode"] == "DRY RUN" and out["changes"] and calls == ["GET"]
    out = fb.cmd_page_seo(go=True, env=ENV)
    assert out["write"].startswith("REFUSED") and "283" in out["write"] and out["readback_ok"] is False
    assert calls.count("POST") == 1 and FB_TOKEN not in json.dumps(out)
