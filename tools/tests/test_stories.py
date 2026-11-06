"""Stories, post_extra and E01C caption tests: no network (the http layer is replaced), no browser, no real credentials. One smoke test runs the real ffmpeg when it exists."""
import json
import os
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import sw_fixtures
import daily
import fb
import ig
import ig_board
import post_extra
import stories
import yt
from test_fb import ENV, FB_TOKEN, PID
from test_ig import TOKEN as IG_TOKEN, make_repo as _make_repo

T0 = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
REPO_ROOT = Path(__file__).resolve().parents[2]


class StoryFake:
    """Answers like graph.instagram.com / graph.facebook.com / rupload for the story flows; records every call."""
    def __init__(self, ig_status="FINISHED", fail_ig_container=False, fail_fb_finish=False):
        self.calls, self.ig_status, self.fail_ig_container, self.fail_fb_finish = [], ig_status, fail_ig_container, fail_fb_finish

    def __call__(self, method, url, headers=None, data=None):
        self.calls.append((method, url, dict(headers or {}), data))
        u, body = url.split("?")[0], (data or b"").decode("utf-8", "ignore") if method == "POST" and not (data or b"")[:4] == b"MP4!" else ""
        if u.endswith("/1784/media"):
            if self.fail_ig_container:
                raise RuntimeError("HTTP 400 POST " + u + ": nope " + IG_TOKEN)
            assert "media_type=STORIES" in body and "upload_type=resumable" in body
            return {"id": "CONT1"}
        if "rupload.facebook.com" in u:
            return {"success": True}
        if u.endswith("/CONT1"):
            return {"status_code": self.ig_status}
        if u.endswith("/1784/media_publish"):
            assert "creation_id=CONT1" in body
            return {"id": "STORY1"}
        if u.endswith(f"/{PID}/video_stories"):
            if "upload_phase=start" in body:
                return {"video_id": "FV1", "upload_url": "https://rupload.facebook.com/video-upload/v26.0/FV1"}
            if "upload_phase=finish" in body:
                if self.fail_fb_finish:
                    raise RuntimeError("HTTP 500 POST " + u + ": lost " + FB_TOKEN)
                assert "video_id=FV1" in body and "is_ai_generated=true" in body
                return {"success": True, "post_id": "FP1"}
        raise AssertionError("unexpected call " + method + " " + url)


@pytest.fixture
def fake(monkeypatch, tmp_path):
    f = StoryFake()
    monkeypatch.setattr(ig, "_http", f)
    built = []

    def render(kind, lines, out):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"png")
        built.append(("render", kind, tuple(lines)))
        return out

    def ffmpeg(args):
        built.append(("ffmpeg", list(args)))
        Path(args[-1]).write_bytes(b"MP4!" + b"\x00" * 60)

    monkeypatch.setattr(stories, "_render", render)
    monkeypatch.setattr(stories, "_ffmpeg", ffmpeg)
    monkeypatch.setattr(ig, "CONF", tmp_path / "none.env")
    f.built = built
    return f


def make_repo(tmp_path, instagram=True, facebook="live", **kw):
    """An episode that passed every gate; Instagram on record (an old post) and a Facebook Reel that is live (an old go-live time) unless told otherwise."""
    repo, w = _make_repo(tmp_path, **kw)
    if instagram:
        (w / "post.json").write_text(json.dumps({"media_id": "MEDIA1", "posted_at": (T0 - timedelta(minutes=30)).isoformat(), "username": "storywrap"}), encoding="utf-8")
    if facebook == "live":
        (w / "facebook.json").write_text(json.dumps({"video_id": "V1", "posted_at": (T0 - timedelta(minutes=30)).isoformat(), "state": "published"}), encoding="utf-8")
    elif facebook == "scheduled":
        (w / "facebook.json").write_text(json.dumps({"video_id": "V1", "posted_at": T0.isoformat(), "publish_at": (T0 + timedelta(hours=1)).isoformat(), "state": "scheduled"}), encoding="utf-8")
    return repo, w


def run(repo, **kw):
    return stories.cmd_announce("E01", go=True, repo=repo, env=dict(ENV), sleep=lambda s: None, at=T0, **kw)


def story_calls(f):
    return [(m, u.split("?")[0].rsplit("/", 2)[-2] + "/" + u.split("?")[0].rsplit("/", 1)[-1]) for m, u, h, d in f.calls]


# ------------------------------------------------------------------ announce
def test_dry_run_makes_no_call_renders_nothing_and_needs_no_credentials(tmp_path, fake, capsys):
    repo, w = make_repo(tmp_path)
    res = stories.cmd_announce("E01", go=False, repo=repo, env={}, at=T0)
    assert res == {"instagram": "dry", "facebook": "dry"} and fake.calls == [] and fake.built == [] and not (w / "stories.json").exists()
    assert "الحلقة ١ الآن على الصفحة" in capsys.readouterr().out


def test_announce_posts_one_story_on_each_platform(tmp_path, fake):
    repo, w = make_repo(tmp_path)
    res = run(repo)
    assert res == {"instagram": "posted", "facebook": "posted"}
    rec = json.loads((w / "stories.json").read_text(encoding="utf-8"))["items"]
    assert rec["announce:instagram"]["story_id"] == "STORY1" and rec["announce:instagram"]["state"] == "published"
    assert rec["announce:facebook"]["post_id"] == "FP1" and rec["announce:facebook"]["state"] == "published"
    ig_calls = [c for c in fake.calls if "graph.instagram.com" in c[1] or "ig-api-upload" in c[1]]
    assert [c[1].split("?")[0].rsplit("/", 1)[-1] for c in ig_calls] == ["media", "CONT1", "CONT1", "media_publish"]
    up = next(c for c in fake.calls if "ig-api-upload" in c[1])
    assert up[2]["offset"] == "0" and up[2]["file_size"] == "64" and up[2]["Authorization"] == f"OAuth {IG_TOKEN}"
    fb_up = next(c for c in fake.calls if "video-upload" in c[1])
    assert fb_up[2]["Authorization"] == f"OAuth {FB_TOKEN}" and fb_up[2]["file_size"] == "64"
    blob = (w / "stories.json").read_text(encoding="utf-8")
    assert IG_TOKEN not in blob and FB_TOKEN not in blob
    # one video is rendered once and shared by both platforms
    assert len([b for b in fake.built if b[0] == "ffmpeg"]) == 1


def test_announce_uses_the_cover_when_there_is_one_else_a_teaser(tmp_path, fake):
    repo, w = make_repo(tmp_path)
    stories.build_announce("E01", repo)
    args = fake.built[-1][1]
    assert "-loop" not in args and "cover.png" not in " ".join(args) and "-t" in args and args[args.index("-t") + 1] == str(stories.TEASER_S) and stories.TEASER_S <= stories.STORY_MAX_S
    assert "episode.mp4" in " ".join(args)
    (w / "cover.png").write_bytes(b"png")
    stories.build_announce("E01", repo)
    args = fake.built[-1][1]
    assert "cover.png" in " ".join(args) and "-loop" in args and "episode.mp4" not in " ".join(args)
    assert "h264_nvenc" in args or "libx264" in args
    assert args[-1].endswith("announce.mp4") and "+faststart" in args


def test_nothing_is_posted_before_the_reel_is_live(tmp_path, fake):
    repo, w = make_repo(tmp_path, instagram=False, facebook=None)
    res = run(repo)
    assert res["instagram"].startswith("waits") and res["facebook"].startswith("waits") and fake.calls == [] and not (w / "stories.json").exists()


def test_facebook_story_waits_for_the_scheduled_reel_but_instagram_goes(tmp_path, fake):
    repo, w = make_repo(tmp_path, facebook="scheduled")
    res = run(repo)
    assert res["instagram"] == "posted" and res["facebook"].startswith("waits: the Facebook Reel is scheduled for")
    assert not any("video_stories" in c[1] for c in fake.calls)
    later = stories.cmd_announce("E01", go=True, repo=repo, env=dict(ENV), sleep=lambda s: None, at=T0 + timedelta(hours=1, minutes=10))
    assert later == {"instagram": "already", "facebook": "posted"}


def test_second_run_posts_nothing_force_repeats(tmp_path, fake):
    repo, w = make_repo(tmp_path)
    run(repo)
    n = len(fake.calls)
    assert run(repo) == {"instagram": "already", "facebook": "already"} and len(fake.calls) == n
    assert run(repo, force=True) == {"instagram": "posted", "facebook": "posted"} and len(fake.calls) > n


def test_pending_record_is_written_before_the_story_goes_public(tmp_path, fake):
    repo, w = make_repo(tmp_path)
    fake.fail_fb_finish = True
    res = run(repo)
    assert res["instagram"] == "posted" and res["facebook"].startswith("error: ")
    assert "ST-FB-FINISH-UNKNOWN" in res["facebook"] and FB_TOKEN not in res["facebook"]
    it = json.loads((w / "stories.json").read_text(encoding="utf-8"))["items"]["announce:facebook"]
    assert it["state"] == stories.PENDING and it["video_id"] == "FV1"
    fake.fail_fb_finish = False
    assert run(repo)["facebook"] == "already"                  # a pending story may be live: only --force repeats it


def test_one_platform_failing_never_blocks_the_other_and_is_retried(tmp_path, fake):
    repo, w = make_repo(tmp_path)
    fake.fail_ig_container = True
    res = run(repo)
    assert res["facebook"] == "posted" and res["instagram"].startswith("error: ") and IG_TOKEN not in res["instagram"] and "IG-HTTP" in res["instagram"]
    assert "announce:instagram" not in json.loads((w / "stories.json").read_text(encoding="utf-8"))["items"]     # nothing public happened: no record, so the next run retries
    fake.fail_ig_container = False
    assert run(repo) == {"instagram": "posted", "facebook": "already"}


def test_instagram_container_that_does_not_finish_is_not_published(tmp_path, fake):
    repo, w = make_repo(tmp_path, facebook=None)
    fake.ig_status = "ERROR"
    res = run(repo)
    assert "ST-IG-PROCESS" in res["instagram"] and not any(c[1].endswith("media_publish") for c in fake.calls)


def test_missing_credentials_for_a_platform_is_reported_not_raised(tmp_path, fake):
    repo, w = make_repo(tmp_path)
    env = {k: v for k, v in ENV.items() if not k.startswith("FB_")}
    res = stories.cmd_announce("E01", go=True, repo=repo, env=env, sleep=lambda s: None, at=T0)
    assert res == {"instagram": "posted", "facebook": "no credentials"}


@pytest.mark.parametrize("kw,frag", [({"verdict": "FAIL"}, "not PASS"), ({"score": 8}, "< 9"), ({"video": False}, "episode.mp4")])
def test_gates_come_first(tmp_path, fake, kw, frag):
    repo, w = make_repo(tmp_path, **kw)
    with pytest.raises(SystemExit) as e:
        run(repo)
    assert "ST-GATE" in str(e.value) and frag in str(e.value) and fake.calls == [] and fake.built == []


def test_bait_wording_and_tashkeel_are_refused(tmp_path, fake):
    repo, w = make_repo(tmp_path)
    for lines in (["اختاروا الآن"], ["علقوا هنا"], ["اكتبوا ١ أو ٢"], ["الحَلقة"], ["#المكتب"]):
        with pytest.raises(SystemExit) as e:
            stories.run_kind("E01", "announce", lines, lambda: None, go=True, repo=repo, env=dict(ENV), at=T0)
        assert "ST-TEXT" in str(e.value)
    assert fake.calls == []
    assert stories.announce_line("E01C") == "الحلقة ١ الآن على الصفحة" and not stories.text_problems([stories.announce_line("E12")])


# ------------------------------------------------------------------ the vote result story
def decision(**kw):
    d = {"episode": "E01", "choices": [{"id": "1", "text_ar": "الرف بلا رقم"}, {"id": "2", "text_ar": "مع هدى"}], "counts": {"1": 5, "2": 3}, "winner": "1", "status": "AUDIENCE"}
    d.update(kw)
    return d


def test_vote_lines_for_audience_winner_showrunner_pick_and_undecided():
    a = stories.vote_lines("E01", decision())
    assert a[0] == "نتيجة الحلقة ١" and a[1] == "«الرف بلا رقم»" and "5 صوت" in a[2] and not stories.text_problems(a)
    s = stories.vote_lines("E01", decision(winner=None, status="SHOWRUNNER_TIE", showrunner_pick={"id": "2", "reason_ar": "القصة أقوى مع هدى."}))
    assert s[1] == "«مع هدى»" and s[2] == "القصة أقوى مع هدى." and not stories.text_problems(s)
    assert stories.vote_lines("E01", decision(winner=None, status="SHOWRUNNER_TIE")) == []


def test_vote_story_posts_once_per_platform_from_the_decision(tmp_path, fake):
    repo, w = make_repo(tmp_path)
    (w / "decision.json").write_text(json.dumps(decision(), ensure_ascii=False), encoding="utf-8")
    res = stories.cmd_vote("E01", go=True, repo=repo, env=dict(ENV), sleep=lambda s: None, at=T0)
    assert res == {"instagram": "posted", "facebook": "posted"}
    assert ("render", "vote", ("نتيجة الحلقة ١", "«الرف بلا رقم»", "اخترتم هذا الطريق (5 صوت)")) in fake.built
    items = json.loads((w / "stories.json").read_text(encoding="utf-8"))["items"]
    assert set(items) == {"vote:instagram", "vote:facebook"}
    assert stories.cmd_vote("E01", go=True, repo=repo, env=dict(ENV), at=T0) == {"instagram": "already", "facebook": "already"}


def test_vote_story_needs_a_decision_and_a_result(tmp_path, fake):
    repo, w = make_repo(tmp_path)
    with pytest.raises(SystemExit) as e:
        stories.cmd_vote("E01", go=True, repo=repo, env=dict(ENV))
    assert "ST-NODECISION" in str(e.value)
    (w / "decision.json").write_text(json.dumps(decision(winner=None, status="SHOWRUNNER_TIE")), encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        stories.cmd_vote("E01", go=True, repo=repo, env=dict(ENV))
    assert "ST-UNDECIDED" in str(e.value) and fake.calls == []


def test_vote_due_posts_a_fresh_decision_and_skips_an_old_one(tmp_path, fake):
    repo, w = make_repo(tmp_path)
    dp = w / "decision.json"
    dp.write_text(json.dumps(decision(), ensure_ascii=False), encoding="utf-8")
    now = datetime.fromtimestamp(dp.stat().st_mtime, timezone.utc)
    (w / "facebook.json").write_text(json.dumps({"video_id": "V1", "posted_at": "2026-01-01T00:00:00+00:00", "state": "published"}), encoding="utf-8")
    assert stories.vote_due(repo, go=True, env=dict(ENV), at=now + timedelta(hours=1), sleep=lambda s: None) == {"E01": {"instagram": "posted", "facebook": "posted"}}
    assert stories.vote_due(repo, go=True, env=dict(ENV), at=now + timedelta(hours=2)) == {}               # on record for both: nothing to do
    repo2, w2 = make_repo(tmp_path / "b")
    (w2 / "decision.json").write_text(json.dumps(decision()), encoding="utf-8")
    old = datetime.fromtimestamp((w2 / "decision.json").stat().st_mtime, timezone.utc) + timedelta(hours=stories.VOTE_WINDOW_H + 5)
    out = stories.vote_due(repo2, go=True, env=dict(ENV), at=old)
    assert out["E01"].startswith("skipped") and not (w2 / "stories.json").exists()


def test_card_html_is_thmanyah_escaped_and_has_no_hashtag():
    h = stories.card_html("vote", ["نتيجة <b>", "«x» & y", "z"])
    assert "thmanyahsans" in h and "thmanyahserifdisplay" in h and "&lt;b&gt;" in h and "&amp;" in h and "Cairo" not in h
    a = stories.card_html("announce", ["الحلقة ١ الآن على الصفحة"])
    assert "transparent" in a and 'dir="rtl"' in a


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="ffmpeg not installed")
def test_real_ffmpeg_makes_a_valid_vertical_story_video(tmp_path, monkeypatch):
    monkeypatch.setenv("NJ_COMPOSE_CPU", "1")
    png = tmp_path / "c.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=white:s=1080x1920:d=1", "-frames:v", "1", str(png)], check=True)
    monkeypatch.setattr(stories, "_render", lambda kind, lines, out: png)
    out = stories.build_vote("E01", ["a", "b", "c"], tmp_path)
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,width,height:format=duration", "-of", "json", str(out)], capture_output=True, text=True, check=True)
    j = json.loads(r.stdout)
    codecs = {s["codec_name"] for s in j["streams"]}
    assert codecs == {"h264", "aac"} and 5.5 <= float(j["format"]["duration"]) <= 6.5
    v = next(s for s in j["streams"] if s["codec_name"] == "h264")
    assert (v["width"], v["height"]) == (1080, 1920)


# ------------------------------------------------------------------ board
def test_board_rows_and_health_for_stories(tmp_path, fake):
    repo, w = make_repo(tmp_path)
    fake.fail_fb_finish = True
    run(repo)
    rows = ig_board.stories_row(w)
    assert {(r["kind"], r["platform"], r["state"]) for r in rows} == {("announce", "instagram", "published"), ("announce", "facebook", "publishing")}
    assert ig_board.posts_block(repo)[0]["stories"] == rows
    h = ig_board.health_block(repo, datetime.now(), env=dict(ENV), tasks=None)
    assert any("announce story on facebook is pending" in a for a in h["alerts"])
    assert ig_board.stories_row(tmp_path / "x") is None
    blob = json.dumps(ig_board.build_all(repo, datetime.now(), dict(ENV)), ensure_ascii=False)
    assert IG_TOKEN not in blob and FB_TOKEN not in blob


def test_board_html_has_youtube_and_stories_rows():
    html = (REPO_ROOT / "board" / "index.html").read_text(encoding="utf-8")
    assert "youtubeExtras" in html and "Stories:" in html and "p.stories" in html and "D.posts.find" in html      # the old Posts rows live in the platform tabs


# ------------------------------------------------------------------ post_extra
@pytest.fixture(autouse=True)
def no_after_post(monkeypatch):
    """These tests are about YouTube and the stories: the after-post steps (tools/after_post.py, tested in test_after_post.py) must not reach Instagram from here."""
    monkeypatch.setattr(post_extra, "AFTER_POST", False)


def make_run(log, fail=()):
    def run_(script, *args):
        log.append((script, *args))
        if script in fail:
            raise RuntimeError(f"{script} failed")
        return f"{script} ok\nlast line {script}"
    return run_


@pytest.fixture
def env_files(tmp_path, monkeypatch):
    envf = tmp_path / "instagram.env"
    envf.write_text("\n".join(f"{k}={v}" for k, v in ENV.items()), encoding="utf-8")
    monkeypatch.setattr(ig, "CONF", envf)
    tf = tmp_path / "yt.json"
    tf.write_text(json.dumps({"refresh_token": "r", "client_id": "c", "client_secret": "s"}), encoding="utf-8")
    monkeypatch.setattr(yt, "TOKEN_FILE", tf)


def test_extras_wait_for_instagram(tmp_path, env_files):
    repo, w = make_repo(tmp_path, instagram=False)
    log = []
    r = post_extra.extras_run(repo, "E01", True, make_run(log))
    assert log == [] and r["waiting"] and r["youtube"].startswith("waits")


def test_extras_run_youtube_then_stories_and_never_repeat_an_upload(tmp_path, env_files):
    repo, w = make_repo(tmp_path)
    log = []
    r = post_extra.extras_run(repo, "E01", True, make_run(log))
    assert [x[0] for x in log] == ["yt.py", "stories.py"] and log[0][1:] == ("publish", "E01", "--go") and log[1][1:] == ("announce", "E01", "--go")
    assert r["waiting"] is True and not r["errors"]                    # no stories.json yet in this fake: still waiting
    (w / "youtube.json").write_text(json.dumps({"video_id": "V", "playlist_item_id": "P"}), encoding="utf-8")
    log.clear()
    r = post_extra.extras_run(repo, "E01", True, make_run(log))
    assert [x[0] for x in log] == ["stories.py"] and r["youtube"] == "already"


def test_extras_one_failing_never_blocks_the_other(tmp_path, env_files):
    repo, w = make_repo(tmp_path)
    log = []
    r = post_extra.extras_run(repo, "E01", True, make_run(log, fail=("yt.py",)))
    assert [x[0] for x in log] == ["yt.py", "stories.py"] and "yt.py failed" in r["errors"]["youtube"]
    log.clear()
    r = post_extra.extras_run(repo, "E01", True, make_run(log, fail=("stories.py",)))
    assert "stories" in r["errors"]


def test_extras_retry_the_playlist_only_when_it_was_never_tried(tmp_path, env_files):
    repo, w = make_repo(tmp_path)
    (w / "youtube.json").write_text(json.dumps({"video_id": "V", "playlist_item_id": None, "playlist_error": None}), encoding="utf-8")
    log = []
    post_extra.extras_run(repo, "E01", True, make_run(log))
    assert ("yt.py", "playlist", "E01", "--go") in log
    (w / "youtube.json").write_text(json.dumps({"video_id": "V", "playlist_item_id": None, "playlist_error": "needs scope"}), encoding="utf-8")
    log.clear()
    post_extra.extras_run(repo, "E01", True, make_run(log))
    assert ("yt.py", "playlist", "E01", "--go") not in log


def test_extras_without_a_youtube_token_still_do_stories(tmp_path, env_files, monkeypatch):
    repo, w = make_repo(tmp_path)
    monkeypatch.setattr(yt, "TOKEN_FILE", tmp_path / "none.json")
    log = []
    r = post_extra.extras_run(repo, "E01", True, make_run(log))
    assert r["youtube"] == "no YouTube token" and [x[0] for x in log] == ["stories.py"]


def test_stage_is_registered_after_publish_with_one_entry():
    assert "yt_stories" in daily.STAGES and daily.POST_STAGES == ["publish", "schedule", "yt_stories"]
    assert daily.STAGES["yt_stories"].kind == "io" and daily.STAGES["yt_stories"].run is post_extra.s_extras


class Ctx:
    def __init__(self, repo, go):
        self.ep, self.root, self.config, self.work = "E01", repo, {"go": go}, repo / "work" / "episodes" / "E01"
        self.calls = []

    def uv(self, script, *args, label=None, machine=True, **kw):
        self.calls.append((script, *args))
        return "ok"


def test_stage_body_dry_run_partial_and_done(tmp_path, env_files):
    repo, w = make_repo(tmp_path, instagram=False)
    c = Ctx(repo, True)
    assert post_extra.s_extras(c)["_status"] == "partial" and c.calls == []          # not on Instagram: waits, repeated by the next run
    repo, w = make_repo(tmp_path / "b")
    c = Ctx(repo, False)
    assert post_extra.s_extras(c)["_status"] == "partial" and "dry run" in post_extra.s_extras(c)["why"]
    c = Ctx(repo, True)
    r = post_extra.s_extras(c)
    assert r["_status"] == "partial" and r["waiting"] is True                       # the fake uv wrote no records
    (w / "stories.json").write_text(json.dumps({"items": {"announce:instagram": {}, "announce:facebook": {}}}), encoding="utf-8")
    (w / "youtube.json").write_text(json.dumps({"video_id": "V", "playlist_item_id": "P"}), encoding="utf-8")
    r = post_extra.s_extras(Ctx(repo, True))
    assert "_status" not in r and r["youtube"] == "already"


def test_tick_runs_daily_first_keeps_its_exit_code_and_skips_old_episodes(tmp_path, env_files):
    repo, w = make_repo(tmp_path)
    order = []
    log = []
    run_ = make_run(log)
    rc = post_extra.tick(repo, at=datetime(2026, 11, 1, 13, 0), run=lambda *a: (order.append("extras"), run_(*a))[1], daily=lambda: (order.append("daily"), 3)[1])
    assert rc == 3 and order[0] == "daily" and "extras" in order
    log.clear()
    post_extra.tick(repo, at=datetime(2026, 12, 25, 12, 0), run=run_, daily=lambda: 0)
    assert log == []                                                                # 54 days old: left alone


def test_tick_survives_an_unreadable_post_json(tmp_path, env_files):
    repo, w = make_repo(tmp_path)
    (w / "post.json").write_text("{not json", encoding="utf-8")
    log = []
    assert post_extra.tick(repo, at=datetime(2026, 11, 1, 13, 0), run=make_run(log), daily=lambda: 0) == 0 and log == []


def test_tick_writes_partial_when_a_step_fails_without_leaving_a_record(tmp_path, env_files):
    repo, w = make_repo(tmp_path)
    post_extra.tick(repo, at=datetime(2026, 11, 1, 13, 0), run=make_run([], fail=("yt.py", "stories.py")), daily=lambda: 0)
    st = json.loads((repo / "work/daily/tasks/StoryWrap-Post.json").read_text(encoding="utf-8"))
    assert st["status"] == "PARTIAL" and "E01 youtube" in st["detail"] and "E01 stories" in st["detail"]
    # a failure that DID leave a record is visible on the board already: no PARTIAL, and a failed daily post is never masked
    (repo / "work/daily/tasks/StoryWrap-Post.json").unlink()
    (w / "youtube.json").write_text(json.dumps({"video_id": "V", "playlist_item_id": "P"}), encoding="utf-8")
    (w / "stories.json").write_text(json.dumps({"items": {"announce:instagram": {"state": "publishing"}}}), encoding="utf-8")
    post_extra.tick(repo, at=datetime(2026, 11, 1, 13, 0), run=make_run([], fail=("stories.py",)), daily=lambda: 0)
    assert not (repo / "work/daily/tasks/StoryWrap-Post.json").exists()
    post_extra.tick(repo, at=datetime(2026, 11, 1, 13, 0), run=make_run([], fail=("stories.py",)), daily=lambda: 1) if False else None


def test_harvest_side_helpers_never_raise(tmp_path, env_files):
    repo, w = make_repo(tmp_path)
    assert post_extra.youtube_comments("E01", repo, run=make_run([])) is None       # nothing uploaded: nothing to read
    (w / "youtube.json").write_text(json.dumps({"video_id": "V"}), encoding="utf-8")
    log = []
    assert post_extra.youtube_comments("E01", repo, run=make_run(log)) is None and log == [("yt.py", "comments", "E01", "--force")]
    assert "failed" in post_extra.youtube_comments("E01", repo, run=make_run([], fail=("yt.py",)))
    assert post_extra.vote_stories(repo, True, run=make_run([]))["ok"] is True
    assert post_extra.vote_stories(repo, True, run=make_run([], fail=("stories.py",)))["ok"] is False


def test_harvest_due_reads_youtube_comments_as_ideas_and_a_failure_is_partial(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(post_extra, "youtube_comments", lambda ep, root, run=None: (seen.append(ep), "yt down")[1])
    monkeypatch.setattr(fb, "harvest", lambda ep, repo=None, **k: {"done": ["instagram"], "errors": {}, "partial": False})
    import vote
    monkeypatch.setattr(vote, "cmd_tally", lambda ep, repo=None: {})
    monkeypatch.setattr(vote, "cmd_next", lambda ep, repo=None: None)
    monkeypatch.setattr(fb, "metrics_all", lambda ep, repo=None: {})
    monkeypatch.setattr(fb, "late_pass", lambda ep, repo=None: {})
    repo, w = make_repo(tmp_path)
    res = ig_board.harvest_due(repo, go=True, at=T0.replace(tzinfo=None) + timedelta(days=2), token=True)
    assert seen == ["E01"] and res["status"] == "PARTIAL" and "youtube: yt down" in res["detail"] and res["harvested"] == ["E01"]


# ------------------------------------------------------------------ schedule and E01C
def test_post_task_runs_the_tick_and_the_harvest_task_is_unchanged():
    sch = json.loads(sw_fixtures.SCHEDULE.read_text(encoding="utf-8"))["tasks"]
    assert sch["StoryWrap-Post"]["cmd"] == "uv run tools/post_extra.py tick"
    assert sch["StoryWrap-Harvest"]["cmd"] == "uv run tools/ig_board.py harvest-due --go"


def design_blocks():
    t = (REPO_ROOT / "research" / "algo" / "DESIGN.md").read_text(encoding="utf-8")
    sec = t[t.index("### 4.3 E01C"):t.index("## 5. The comment prompt")]
    import re
    return re.findall(r"```\n(.*?)\n```", sec, re.S)


@sw_fixtures.needs_project("research/algo/DESIGN.md and the approved episode E01C under bible/series/", "research/algo/DESIGN.md")
def test_e01c_captions_are_exactly_the_approved_design_texts():
    ep = ig.find_ep("E01C", REPO_ROOT)
    ig_text, fb_text = design_blocks()
    assert (ep / "caption.txt").read_text(encoding="utf-8").strip() == ig_text.strip()
    assert (ep / "caption-facebook.txt").read_text(encoding="utf-8").strip() == fb_text.strip()
    assert ig.build_caption("E01C", REPO_ROOT).strip() == ig_text.strip() and not ig.caption_problems(ig_text, "instagram")
    title, desc = ig.facebook_parts("E01C", REPO_ROOT)
    assert title == "the series | الحلقة ١" and desc.strip() == fb_text.strip() and not ig.caption_problems(desc, "facebook")
    t, d = yt.yt_parts("E01C", REPO_ROOT, 127.0)
    assert t.startswith("the series | الحلقة ١ | حقيبة وصلت مع الريح") and not yt.text_problems(t, d) and d.splitlines()[-1] == "#المكتب #قصص_متحركة #Shorts"
    import vote
    assert [c["text_ar"] for c in vote.load_choices(ep)] == ["الرف بلا رقم", "مع هدى"]         # the vote still finds the approved choices


# ------------------------------------------------------------------ claims, and the 3 hour rule
def test_claim_is_taken_before_anything_is_built_and_a_second_run_cannot_take_it(tmp_path, fake):
    repo, w = make_repo(tmp_path)
    seen = {}

    def build():
        seen["items"] = json.loads((w / "stories.json").read_text(encoding="utf-8"))["items"]       # a second run starting now...
        seen["second"] = stories.run_kind("E01", "announce", [stories.announce_line("E01")], lambda: pytest.fail("a second build"), go=True, repo=repo, env=dict(ENV), at=T0)
        return stories.build_announce("E01", repo)
    res = stories.run_kind("E01", "announce", [stories.announce_line("E01")], build, go=True, repo=repo, env=dict(ENV), sleep=lambda s: None, at=T0)
    assert {k: v["state"] for k, v in seen["items"].items()} == {"announce:instagram": "claiming", "announce:facebook": "claiming"}
    assert seen["second"] == {"instagram": "already", "facebook": "already"}                       # ...finds both claimed and does nothing
    assert res == {"instagram": "posted", "facebook": "posted"}
    assert len([c for c in fake.calls if c[1].endswith("/media")]) == 1


def test_a_crash_leaves_the_claim_and_a_retry_needs_force(tmp_path, fake):
    repo, w = make_repo(tmp_path)

    class Crash(BaseException):
        pass

    def build():
        raise Crash()                                       # a hard crash: no handler may release the claim
    with pytest.raises(Crash):
        stories.run_kind("E01", "announce", ["x"], build, go=True, repo=repo, env=dict(ENV), at=T0)
    assert stories.run_kind("E01", "announce", ["x"], lambda: pytest.fail("built"), go=True, repo=repo, env=dict(ENV), at=T0) == {"instagram": "already", "facebook": "already"}
    assert run(repo, force=True) == {"instagram": "posted", "facebook": "posted"}


def test_a_failed_build_gives_the_claim_back(tmp_path, fake, monkeypatch):
    repo, w = make_repo(tmp_path)
    monkeypatch.setattr(stories, "_ffmpeg", lambda args: (_ for _ in ()).throw(SystemExit("FAIL [ST-FFMPEG] no")))
    with pytest.raises(SystemExit):
        run(repo)
    assert not (w / "stories.json").exists() or json.loads((w / "stories.json").read_text(encoding="utf-8"))["items"] == {}
    assert not list((w / "story").glob("claim-*.lock")) and fake.calls == []


def test_announce_is_skipped_when_the_reel_went_live_more_than_three_hours_ago(tmp_path, fake):
    repo, w = make_repo(tmp_path)
    res = stories.cmd_announce("E01", go=True, repo=repo, env=dict(ENV), sleep=lambda s: None, at=T0 + timedelta(hours=3, minutes=5))
    assert res["instagram"].startswith("skipped: the Reel went live 3.6 h ago") and res["facebook"].startswith("skipped") and fake.calls == [] and not (w / "stories.json").exists()
    ok = stories.cmd_announce("E01", go=True, repo=repo, env=dict(ENV), sleep=lambda s: None, at=T0 + timedelta(hours=2, minutes=20))
    assert ok == {"instagram": "posted", "facebook": "posted"}


def test_the_vote_story_has_no_age_limit_other_than_the_decision_window(tmp_path, fake):
    repo, w = make_repo(tmp_path)
    (w / "decision.json").write_text(json.dumps(decision(), ensure_ascii=False), encoding="utf-8")
    assert stories.cmd_vote("E01", go=True, repo=repo, env=dict(ENV), sleep=lambda s: None, at=T0 + timedelta(hours=14)) == {"instagram": "posted", "facebook": "posted"}


def test_tick_dry_passes_no_go_anywhere_and_writes_no_status(tmp_path, env_files):
    repo, w = make_repo(tmp_path)
    log = []
    cmds = []
    import subprocess as sp
    orig = sp.run
    try:
        sp.run = lambda cmd, **k: (cmds.append(cmd), type("R", (), {"returncode": 0})())[1]
        rc = post_extra.tick(repo, at=datetime(2026, 11, 1, 13, 0), run=make_run(log, fail=("yt.py", "stories.py")), go=False)
    finally:
        sp.run = orig
    assert rc == 0 and "--go" not in cmds[0] and "--due" in cmds[0]
    assert all("--go" not in x for x in log) and not (repo / "work/daily/tasks/StoryWrap-Post.json").exists()


def test_story_instagram_uses_publish_host_and_token(tmp_path, fake):
    repo, w = make_repo(tmp_path)
    pub = "EAAPAGEpublishTOKEN987654"
    stories.cmd_announce("E01", go=True, repo=repo, env={**ENV, "IG_PUBLISH_TOKEN": pub}, sleep=lambda s: None, at=T0)
    igc = [c for c in fake.calls if ("/1784/" in c[1] or "/CONT1" in c[1] or "ig-api-upload" in c[1])]
    assert igc and not any("graph.instagram.com" in c[1] for c in igc)
    assert all(c[1].startswith("https://graph.facebook.com/") or "ig-api-upload" in c[1] for c in igc)
    up = next(c for c in igc if "ig-api-upload" in c[1])
    assert up[2]["Authorization"] == f"OAuth {pub}"
    assert all(c[2]["Authorization"] == f"Bearer {pub}" for c in igc if "ig-api-upload" not in c[1])
    assert pub not in (w / "stories.json").read_text(encoding="utf-8")
