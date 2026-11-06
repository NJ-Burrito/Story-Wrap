"""YouTube tool tests: no network (the service object is a fake), no real credentials."""
import json
from datetime import datetime, timedelta, timezone

import pytest

import fb
import ig
import ig_board
import vote
import yt
from test_ig import make_repo as _make_repo

SECRET = {"token": "ya29.ACCESSsecret123456", "refresh_token": "1//REFRESHsecret987654", "client_id": "cid.apps.googleusercontent.com", "client_secret": "GOCSPX-clientsecret55",
          "scopes": ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"], "expiry": "2026-11-01T12:30:00Z"}
T0 = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


class HttpErr(Exception):
    def __init__(self, status, msg="boom"):
        super().__init__(msg)
        self.resp = type("R", (), {"status": status})()


class Req:
    def __init__(self, fn):
        self.fn = fn

    def execute(self):
        return self.fn()

    def next_chunk(self, num_retries=0):
        self.chunks = getattr(self, "chunks", 0) + 1
        if self.chunks < 3:
            return {"progress": self.chunks}, None
        return None, self.fn()


class Fake:
    """Answers like the YouTube Data API for the calls yt.py makes; records them."""
    def __init__(self, privacy="public", playlists=None, playlist_status=None, comments=None, comments_error=None, upload_error=None):
        self.calls, self.privacy, self.pl_items = [], privacy, playlists or []
        self.playlist_status, self.comments, self.comments_error, self.upload_error = playlist_status, comments or [], comments_error, upload_error

    def _rec(self, name, **kw):
        self.calls.append((name, kw))

    def videos(self):
        f = self

        class V:
            def insert(s, part, body, media_body):
                f._rec("videos.insert", part=part, body=body, media=media_body)
                def done():
                    if f.upload_error:
                        raise f.upload_error
                    return {"id": "VID1"}
                return Req(done)

            def list(s, part, id):
                f._rec("videos.list", part=part, id=id)
                return Req(lambda: {"items": [{"status": {"privacyStatus": f.privacy, "uploadStatus": "uploaded", "madeForKids": False}}]})
        return V()

    def playlists(self):
        f = self

        class P:
            def list(s, **kw):
                f._rec("playlists.list", **kw)
                return Req(lambda: {"items": f.pl_items})

            def insert(s, part, body):
                f._rec("playlists.insert", part=part, body=body)
                if f.playlist_status:
                    return Req(lambda: (_ for _ in ()).throw(HttpErr(f.playlist_status, "insufficientPermissions")))
                return Req(lambda: {"id": "PL1"})
        return P()

    def playlistItems(self):
        f = self

        class PI:
            def insert(s, part, body):
                f._rec("playlistItems.insert", part=part, body=body)
                return Req(lambda: {"id": "PLI1"})
        return PI()

    def commentThreads(self):
        f = self

        class C:
            def list(s, **kw):
                f._rec("commentThreads.list", **kw)
                if f.comments_error:
                    return Req(lambda: (_ for _ in ()).throw(f.comments_error))
                return Req(lambda: {"items": f.comments})
        return C()

    def channels(self):
        f = self

        class Ch:
            def list(s, **kw):
                f._rec("channels.list", **kw)
                return Req(lambda: {"items": [{"id": yt.CHANNEL_ID, "snippet": {"title": "StoryPage"}}]})
        return Ch()


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    tf = tmp_path / "youtube-token.json"
    tf.write_text(json.dumps(SECRET), encoding="utf-8")
    monkeypatch.setattr(yt, "TOKEN_FILE", tf)
    monkeypatch.setattr(yt, "_media", lambda p: f"media:{p.name}")
    monkeypatch.setattr(yt, "video_seconds", lambda p: 127.0)
    monkeypatch.setattr(ig, "CONF", tmp_path / "none.env")


def make_repo(tmp_path, instagram=True, **kw):
    repo, w = _make_repo(tmp_path, **kw)
    if instagram:
        (w / "post.json").write_text(json.dumps({"media_id": "MEDIA1", "posted_at": (T0 - timedelta(days=40)).isoformat(), "username": "storywrap"}), encoding="utf-8")
    return repo, w


def test_dry_run_makes_no_call_and_needs_no_credentials(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(yt, "TOKEN_FILE", tmp_path / "missing.json")
    repo, w = make_repo(tmp_path)
    plan = yt.cmd_publish("E01", go=False, repo=repo, svc=None)
    out = capsys.readouterr().out
    assert plan["mode"] == "DRY RUN" and not (w / "youtube.json").exists()
    assert "the series | الحلقة ١" in out and "#Shorts" in out and out.count("#") == 3 and not ig.caption_problems(out, "youtube")
    r = plan["resource"]
    assert r["snippet"]["categoryId"] == "1" and r["snippet"]["defaultLanguage"] == "ar"
    assert r["status"] == {"privacyStatus": "private", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True, "embeddable": True, "publicStatsViewable": True, "license": "youtube"}
    assert r["snippet"]["tags"][0] == "the series" and "gaming" not in " ".join(r["snippet"]["tags"]).lower()


def test_title_has_hook_and_stays_inside_100_characters():
    t = yt.make_title("E01C", "كلمة " * 40)
    assert t.startswith("the series | الحلقة ١ | ") and len(t) <= 100 and t.endswith("…")
    assert yt.make_title("E02", "") == "the series | الحلقة ٢"


def test_no_shorts_tag_for_a_long_video(tmp_path):
    repo, _ = make_repo(tmp_path)
    _, d = yt.yt_parts("E01", repo, seconds=400.0)
    assert "#Shorts" not in d and "#حكايات" in d
    _, d = yt.yt_parts("E01", repo, seconds=60.0)
    assert d.splitlines()[-1].endswith("#Shorts") and d.count("#") == 3


def test_caption_youtube_file_wins_and_is_checked(tmp_path):
    repo, w = make_repo(tmp_path)
    ep = ig.find_ep("E01", repo)
    (ep / "caption-youtube.txt").write_text("نص خاص\nاكتبوا اختياركم\n#a", encoding="utf-8")
    t, d = yt.yt_parts("E01", repo, 100.0)
    assert d.startswith("نص خاص") and yt.text_problems(t, d)
    with pytest.raises(SystemExit) as e:
        yt.cmd_publish("E01", go=True, repo=repo, svc=Fake())
    assert "YT-CAPTION-BAIT" in str(e.value)


@pytest.mark.parametrize("kw,frag", [({"verdict": "FAIL"}, "not PASS"), ({"complete": False}, "INCOMPLETE"), ({"score": 8}, "< 9"), ({"video": False}, "episode.mp4")])
def test_publish_refuses_without_gates(tmp_path, kw, frag):
    repo, w = make_repo(tmp_path, **kw)
    f = Fake()
    with pytest.raises(SystemExit) as e:
        yt.cmd_publish("E01", go=True, repo=repo, svc=f)
    assert "YT-GATE" in str(e.value) and frag in str(e.value) and f.calls == [] and not (w / "youtube.json").exists()


def test_never_before_instagram(tmp_path):
    repo, w = make_repo(tmp_path, instagram=False)
    f = Fake()
    with pytest.raises(SystemExit) as e:
        yt.cmd_publish("E01", go=True, repo=repo, svc=f)
    assert "YT-WAIT-INSTAGRAM" in str(e.value) and f.calls == [] and not (w / "youtube.json").exists()


def test_upload_records_status_and_playlist(tmp_path):
    repo, w = make_repo(tmp_path)
    f = Fake()
    rec = yt.cmd_publish("E01", go=True, repo=repo, svc=f)
    names = [c[0] for c in f.calls]
    assert names[0] == "videos.insert" and "playlists.insert" in names and names.count("playlistItems.insert") == 1
    ins = f.calls[0][1]
    assert ins["part"] == "snippet,status" and ins["media"] == "media:episode.mp4" and ins["body"]["status"]["containsSyntheticMedia"] is True
    assert rec["video_id"] == "VID1" and rec["state"] == "uploaded" and rec["privacy_actual"] == "public" and rec["locked_private"] is False
    assert rec["url"] == "https://www.youtube.com/shorts/VID1" and rec["playlist_item_id"] == "PLI1"
    assert json.loads((w / "youtube.json").read_text(encoding="utf-8"))["video_id"] == "VID1"
    assert json.loads((repo / "work/state/youtube.json").read_text(encoding="utf-8"))["playlist_id"] == "PL1"


def audit_passed(repo):
    yt.audit_flag(repo).parent.mkdir(parents=True, exist_ok=True)
    yt.audit_flag(repo).write_text("passed", encoding="utf-8")


def test_locked_private_is_recorded_not_hidden(tmp_path, capsys):
    repo, w = make_repo(tmp_path)
    audit_passed(repo)
    rec = yt.cmd_publish("E01", go=True, repo=repo, svc=Fake(privacy="private"))
    assert rec["privacy_actual"] == "private" and rec["locked_private"] is True and "locked private" in capsys.readouterr().out


def test_pending_record_is_written_before_the_first_byte(tmp_path):
    repo, w = make_repo(tmp_path)
    seen = {}

    class Spy(Fake):
        def videos(self):
            seen.setdefault("rec", json.loads((w / "youtube.json").read_text(encoding="utf-8")))      # when videos().insert is built, the record must exist
            return super().videos()
    yt.cmd_publish("E01", go=True, repo=repo, svc=Spy())
    assert seen["rec"]["state"] == yt.PENDING


def test_second_upload_is_refused_without_force(tmp_path):
    repo, w = make_repo(tmp_path)
    yt.cmd_publish("E01", go=True, repo=repo, svc=Fake())
    f = Fake()
    with pytest.raises(SystemExit) as e:
        yt.cmd_publish("E01", go=True, repo=repo, svc=f)
    assert "YT-ALREADY" in str(e.value) and f.calls == []


def test_a_pending_or_corrupt_record_blocks_a_retry(tmp_path):
    repo, w = make_repo(tmp_path)
    (w / "youtube.json").write_text("{not json", encoding="utf-8")
    assert yt.load_record("E01", repo) == {"corrupt": True} and yt.is_posted("E01", repo)
    with pytest.raises(SystemExit) as e:
        yt.cmd_publish("E01", go=True, repo=repo, svc=Fake())
    assert "YT-ALREADY" in str(e.value)


def test_failed_upload_stays_on_record_and_is_redacted(tmp_path):
    repo, w = make_repo(tmp_path)
    err = HttpErr(500, f"server said no to {SECRET['token']} and refresh_token={SECRET['refresh_token']}")
    with pytest.raises(SystemExit) as e:
        yt.cmd_publish("E01", go=True, repo=repo, svc=Fake(upload_error=err))
    msg = str(e.value)
    assert "YT-UPLOAD" in msg and SECRET["token"] not in msg and SECRET["refresh_token"] not in msg
    rec = json.loads((w / "youtube.json").read_text(encoding="utf-8"))
    assert rec["state"] == "upload-failed" and SECRET["token"] not in json.dumps(rec)
    with pytest.raises(SystemExit):                        # recorded: a retry needs --force
        yt.cmd_publish("E01", go=True, repo=repo, svc=Fake())


def test_missing_playlist_scope_does_not_fail_the_upload(tmp_path, capsys):
    repo, w = make_repo(tmp_path)
    rec = yt.cmd_publish("E01", go=True, repo=repo, svc=Fake(playlist_status=403))
    assert rec["video_id"] == "VID1" and rec["playlist_item_id"] is None and "youtube` scope" in rec["playlist_error"]
    assert "playlist:" in capsys.readouterr().out


def test_existing_playlist_is_reused_and_stored_once(tmp_path):
    repo, w = make_repo(tmp_path)
    f = Fake(playlists=[{"id": "PLX", "snippet": {"title": "the series"}}])
    rec = yt.cmd_publish("E01", go=True, repo=repo, svc=f)
    assert rec["playlist_id"] == "PLX" and "playlists.insert" not in [c[0] for c in f.calls]
    f2 = Fake()
    yt.ensure_playlist(f2, repo)
    assert f2.calls == []                                   # the stored id is used, no call


def test_playlist_command_retries_only_when_missing(tmp_path, capsys):
    repo, w = make_repo(tmp_path)
    yt.cmd_publish("E01", go=True, repo=repo, svc=Fake(playlist_status=403))
    yt.cmd_playlist("E01", go=False, repo=repo)
    assert "DRY RUN" in capsys.readouterr().out
    f = Fake()
    rec = yt.cmd_playlist("E01", go=True, repo=repo, svc=f)
    assert rec["playlist_item_id"] == "PLI1" and rec["playlist_error"] is None
    f2 = Fake()
    yt.cmd_playlist("E01", go=True, repo=repo, svc=f2)
    assert f2.calls == []


def test_credentials_missing_is_a_clean_failure(tmp_path, monkeypatch):
    repo, w = make_repo(tmp_path)
    monkeypatch.setattr(yt, "TOKEN_FILE", tmp_path / "gone.json")
    with pytest.raises(SystemExit) as e:
        yt.cmd_publish("E01", go=True, repo=repo)
    assert "YT-CREDS" in str(e.value) and not (w / "youtube.json").exists()


def test_auth_error_is_redacted(tmp_path, monkeypatch):
    def boom(path):
        raise RuntimeError(f"refresh failed for {SECRET['refresh_token']} client_secret={SECRET['client_secret']}")
    monkeypatch.setattr(yt, "_build", boom)
    with pytest.raises(SystemExit) as e:
        yt.service()
    assert "YT-AUTH" in str(e.value) and SECRET["refresh_token"] not in str(e.value) and SECRET["client_secret"] not in str(e.value)


def test_redact_covers_tokens_params_and_bearer():
    s = yt.redact(f"x {SECRET['token']} y access_token=abc123 Authorization: Bearer ya29.zzzzzzzzzzzz key=AIza123", dict(SECRET))
    assert SECRET["token"] not in s and "abc123" not in s and "ya29.zzzz" not in s and "AIza123" not in s and s.count("[REDACTED]") == 4


def test_status_never_prints_the_token_and_live_reads_the_channel(tmp_path, capsys):
    repo, w = make_repo(tmp_path)
    s = yt.cmd_status(live=True, repo=repo, svc=Fake())
    for v in (SECRET["token"], SECRET["refresh_token"], SECRET["client_secret"]):
        assert v not in s
    assert "StoryPage" in s and yt.CHANNEL_ID in s and "NO playlist scope" in s and "NOT FOUND" not in s


def test_token_state_without_file_or_refresh_token():
    assert "no token file" in yt.token_state({})
    assert "no refresh token" in yt.token_state({"token": "x"})


# ------------------------------------------------------------------ comments: ideas only
def thread(i, text, user="ali", ch="UCother", replies=None):
    t = {"id": f"T{i}", "snippet": {"topLevelComment": {"id": f"C{i}", "snippet": {"textDisplay": text, "authorDisplayName": user, "authorChannelId": {"value": ch}, "publishedAt": "2026-11-01T13:00:00Z"}}}}
    if replies:
        t["replies"] = {"comments": replies}
    return t


def test_comments_merge_as_youtube_ideas_and_never_vote(tmp_path):
    repo, w = make_repo(tmp_path)
    yt.cmd_publish("E01", go=True, repo=repo, svc=Fake())
    ig_row = {"id": "I1", "platform": "instagram", "text": "على الرف", "username": "u1", "timestamp": "2026-11-01T13:00:00+0000"}
    (w / "comments.json").write_text(json.dumps({"episode": "E01", "comments": [ig_row], "own_usernames": ["storywrap"]}), encoding="utf-8")
    reply = {"id": "R1", "snippet": {"textDisplay": "ولماذا؟", "authorDisplayName": "nj", "authorChannelId": {"value": yt.CHANNEL_ID}, "publishedAt": "x"}}
    f = Fake(comments=[thread(1, "الرف بلا رقم طبعا", replies=[reply]), thread(2, "مع هدى", user="sara")])
    res = yt.cmd_comments("E01", force=True, repo=repo, svc=f)
    rows = {(c["platform"], c["id"]): c for c in res["comments"]}
    assert ("instagram", "I1") in rows and rows[("youtube", "C1")]["parent_id"] is None and rows[("youtube", "R1")]["parent_id"] == "C1" and rows[("youtube", "R1")]["own"] is True
    assert res["platforms"] == ["instagram", "youtube"] and f.calls[0][1]["videoId"] == "VID1"
    again = yt.cmd_comments("E01", force=True, repo=repo, svc=Fake(comments=[thread(1, "الرف بلا رقم طبعا")]))
    assert [c["id"] for c in again["comments"] if c["platform"] == "youtube"] == ["C1"]          # replaced, not duplicated; Instagram kept
    choices = vote.load_choices(ig.find_ep("E01", repo))
    t = vote.tally_comments(res["comments"], choices, {"storywrap"})
    assert t["counts"] == {"1": 1, "2": 0} and t["other_platform_comments"] == 2 and t["excluded_own"] == 1 and all(i["platform"] == "youtube" for i in t["ideas"] if i["id"] != "I1")


def test_comments_too_early_comments_off_and_no_record(tmp_path):
    repo, w = make_repo(tmp_path)
    with pytest.raises(SystemExit) as e:
        yt.cmd_comments("E01", repo=repo, svc=Fake())
    assert "YT-NOPOST" in str(e.value)
    yt.cmd_publish("E01", go=True, repo=repo, svc=Fake())
    r = yt.load_record("E01", repo)
    r["posted_at"] = datetime.now(timezone.utc).isoformat()
    (w / "youtube.json").write_text(json.dumps(r), encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        yt.cmd_comments("E01", repo=repo, svc=Fake())
    assert "YT-TOO-EARLY" in str(e.value)
    with pytest.raises(SystemExit) as e:
        yt.cmd_comments("E01", force=True, repo=repo, svc=Fake(comments_error=HttpErr(403, "commentsDisabled")))
    assert "YT-COMMENTS-OFF" in str(e.value)


# ------------------------------------------------------------------ board
def test_board_rows_carry_youtube_and_no_credentials(tmp_path):
    repo, w = make_repo(tmp_path)
    audit_passed(repo)
    yt.cmd_publish("E01", go=True, repo=repo, svc=Fake(privacy="private"))
    row = ig_board.youtube_row(w)
    assert row["state"] == "uploaded" and row["privacy"] == "private" and row["locked_private"] is True and row["playlist"] is True
    blob = json.dumps(row)
    assert not any(v in blob for v in (SECRET["token"], SECRET["refresh_token"], SECRET["client_secret"]))
    assert ig_board.youtube_row(tmp_path / "nowhere") is None
    posts = ig_board.posts_block(repo)
    assert posts[0]["youtube"]["url"].endswith("VID1") and posts[0]["stories"] is None


# ------------------------------------------------------------------ privacy until the audit, O_EXCL, playlist step, retention
def test_private_until_the_audit_flag_exists_then_public(tmp_path, capsys):
    repo, w = make_repo(tmp_path)
    f = Fake(privacy="private")
    rec = yt.cmd_publish("E01", go=True, repo=repo, svc=f)
    assert f.calls[0][1]["body"]["status"]["privacyStatus"] == "private" and rec["privacy_requested"] == "private" and rec["locked_private"] is False
    assert yt.privacy_for(repo) == "private"
    repo2, w2 = make_repo(tmp_path / "b")
    audit_passed(repo2)
    f2 = Fake()
    rec2 = yt.cmd_publish("E01", go=True, repo=repo2, svc=f2)
    assert f2.calls[0][1]["body"]["status"]["privacyStatus"] == "public" and rec2["privacy_requested"] == "public" and yt.privacy_for(repo2) == "public"


def test_the_dry_run_says_which_privacy_and_why(tmp_path, capsys):
    repo, w = make_repo(tmp_path)
    yt.cmd_publish("E01", go=False, repo=repo)
    assert "privacy private (private until the API audit passes: create work/state/yt_audit_passed" in capsys.readouterr().out


def test_two_overlapping_uploads_cannot_both_start(tmp_path):
    repo, w = make_repo(tmp_path)
    seen = {}

    class Racer(Fake):
        def videos(self):
            if "second" not in seen:
                seen["second"] = "tried"
                try:
                    yt.cmd_publish("E01", go=True, repo=repo, svc=Fake())       # a second run that passed its is_posted check earlier
                except SystemExit as e:
                    seen["error"] = str(e)
            return super().videos()
    yt.cmd_publish("E01", go=True, repo=repo, svc=Racer())
    assert "YT-ALREADY" in seen["error"]
    with pytest.raises(SystemExit):
        yt.create_record("E01", {"x": 1}, repo)                               # O_EXCL: an existing record is never overwritten
    yt.create_record("E01", {"x": 1}, repo, force=True)
    assert json.loads((w / "youtube.json").read_text(encoding="utf-8")) == {"x": 1}


def test_the_playlist_step_is_recorded_before_the_insert_and_a_crash_never_adds_twice(tmp_path):
    repo, w = make_repo(tmp_path)

    class Crash(Fake):
        def playlistItems(self):
            rec = json.loads((w / "youtube.json").read_text(encoding="utf-8"))
            assert rec["playlist_state"] == "adding"                               # written BEFORE the call
            raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        yt.cmd_publish("E01", go=True, repo=repo, svc=Crash())
    rec = yt.load_record("E01", repo)
    assert rec["playlist_state"] == "adding" and not rec.get("playlist_item_id")
    f = Fake()
    out = yt.cmd_playlist("E01", go=True, repo=repo, svc=f)
    assert "may already be in the playlist" in out["playlist_error"] and "playlistItems.insert" not in [c[0] for c in f.calls]
    out = yt.cmd_playlist("E01", go=True, repo=repo, svc=f, force=True)
    assert out["playlist_item_id"] == "PLI1" and out["playlist_state"] == "added"


def test_a_refused_insert_allows_a_retry(tmp_path):
    repo, w = make_repo(tmp_path)
    rec = yt.cmd_publish("E01", go=True, repo=repo, svc=Fake(playlist_status=403))
    assert rec["playlist_state"] == "failed"
    assert yt.cmd_playlist("E01", go=True, repo=repo, svc=Fake())["playlist_item_id"] == "PLI1"


def seed_comments(w, rows, ideas_in_decision=True):
    (w / "comments.json").write_text(json.dumps({"episode": "E01", "fetched_at": "2026-11-01T00:00:00+00:00", "comments": rows, "platforms": sorted({r["platform"] for r in rows}),
                                                 "youtube_video_id": "VID1"}, ensure_ascii=False), encoding="utf-8")


def yrow(i, fetched, text="فكرة طويلة جدا عن الحقيبة"):
    return {"id": f"Y{i}", "platform": "youtube", "text": text + str(i), "username": "u", "fetched_at": fetched}


def test_prune_deletes_old_youtube_rows_and_their_idea_copies_only(tmp_path):
    repo, w = make_repo(tmp_path)
    now = datetime(2026, 12, 1, tzinfo=timezone.utc)
    old, fresh = (now - timedelta(days=31)).isoformat(), (now - timedelta(days=5)).isoformat()
    igrow = {"id": "I1", "platform": "instagram", "text": "على الرف", "username": "a", "timestamp": "2020-01-01T00:00:00+0000"}
    seed_comments(w, [igrow, yrow(1, old), yrow(2, fresh)])
    (w / "decision.json").write_text(json.dumps({"ideas": [{"id": "Y1", "platform": "youtube", "text": "t1"}, {"id": "Y2", "platform": "youtube", "text": "t2"},
                                                            {"id": "I1", "platform": "instagram", "text": "t3"}], "idea_count": 3}), encoding="utf-8")
    (w / "late-ideas.json").write_text(json.dumps({"ideas": [{"id": "Y1", "platform": "youtube", "text": "t1"}], "count": 1}), encoding="utf-8")
    (w / "next-brief.md").write_text("# brief\n- 1. " + yrow(1, old)["text"] + "\n- 2. " + yrow(2, old)["text"] + "\n- 3. على الرف تماما\n", encoding="utf-8")
    res = yt.prune_comments(repo, at=now)
    assert res["rows_deleted"] == 1 and res["idea_copies_deleted"] == 3
    cm = json.loads((w / "comments.json").read_text(encoding="utf-8"))
    assert [c["id"] for c in cm["comments"]] == ["I1", "Y2"] and cm["count"] == 2
    assert [i["id"] for i in json.loads((w / "decision.json").read_text(encoding="utf-8"))["ideas"]] == ["Y2", "I1"]
    assert json.loads((w / "late-ideas.json").read_text(encoding="utf-8"))["ideas"] == []
    brief = (w / "next-brief.md").read_text(encoding="utf-8")
    assert yrow(1, old)["text"] not in brief and yrow(2, old)["text"] in brief and "على الرف تماما" in brief
    assert yt.prune_comments(repo, at=now) == {"rows_deleted": 0, "idea_copies_deleted": 0, "files": 0}


def test_a_refetch_refreshes_the_retention_clock(tmp_path):
    repo, w = make_repo(tmp_path)
    yt.cmd_publish("E01", go=True, repo=repo, svc=Fake())
    yt.cmd_comments("E01", force=True, repo=repo, svc=Fake(comments=[thread(1, "فكرة")]))
    row = next(c for c in json.loads((w / "comments.json").read_text(encoding="utf-8"))["comments"] if c["platform"] == "youtube")
    assert row["fetched_at"]
    later = datetime.now(timezone.utc) + timedelta(days=29)
    assert yt.prune_comments(repo, at=later)["rows_deleted"] == 0
    assert yt.prune_comments(repo, at=datetime.now(timezone.utc) + timedelta(days=31))["rows_deleted"] == 1


def test_forget_deletes_all_stored_youtube_data_at_once(tmp_path, capsys):
    repo, w = make_repo(tmp_path)
    yt.cmd_publish("E01", go=True, repo=repo, svc=Fake())
    igrow = {"id": "I1", "platform": "instagram", "text": "على الرف", "username": "a"}
    seed_comments(w, [igrow, yrow(1, datetime.now(timezone.utc).isoformat()), yrow(2, datetime.now(timezone.utc).isoformat())])
    rec = yt.load_record("E01", repo)
    rec.update(comments_count=2, comments_fetched_at="x")
    (w / "youtube.json").write_text(json.dumps(rec), encoding="utf-8")
    assert yt.cmd_forget(go=False, repo=repo)["rows"] == 2 and "DRY RUN" in capsys.readouterr().out
    assert len(json.loads((w / "comments.json").read_text(encoding="utf-8"))["comments"]) == 3
    res = yt.cmd_forget(go=True, repo=repo)
    assert res["rows_deleted"] == 2
    cm = json.loads((w / "comments.json").read_text(encoding="utf-8"))
    assert [c["platform"] for c in cm["comments"]] == ["instagram"] and "youtube_video_id" not in cm
    r = yt.load_record("E01", repo)
    assert "comments_count" not in r and r["video_id"] == "VID1"                       # the upload record stays: it stops a second upload
    yt.cmd_forget(go=True, repo=repo, records=True)
    assert not (w / "youtube.json").exists() and not yt.state_path(repo).exists()


def test_the_harvest_task_runs_the_prune(tmp_path, monkeypatch, capsys):
    repo, w = make_repo(tmp_path)
    called = []
    monkeypatch.setattr(yt, "prune_comments", lambda root, **k: (called.append(root), {"rows_deleted": 0})[1])
    monkeypatch.setattr(ig_board, "ROOT", repo)
    monkeypatch.setattr(ig_board, "harvest_due", lambda root, go=False: {"status": "IDLE", "detail": "x"})
    monkeypatch.setattr(ig_board.loop_gate, "has_token", lambda *a: False)
    assert ig_board.main(["harvest-due", "--go"]) == 0 and called == [repo] and "youtube retention" in capsys.readouterr().out


# ------------------------------------------------------------------ board info, and the Windows file-lock retry
def test_a_private_youtube_video_is_info_not_an_alert(tmp_path):
    repo, w = make_repo(tmp_path)
    yt.cmd_publish("E01", go=True, repo=repo, svc=Fake(privacy="private"))
    h = ig_board.health_block(repo, datetime.now(), env={}, tasks=None)
    assert not any("YouTube" in a and "private" in a for a in h["alerts"])
    assert any("E01 is private on YouTube" in i and "requested private" in i for i in h["info"])


def test_replace_retry_survives_a_short_lock_and_gives_up_after_the_last_try(tmp_path, monkeypatch):
    import loop_gate
    calls = {"n": 0}
    real = loop_gate.os.replace

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError(5, "Access is denied")
        return real(src, dst)
    monkeypatch.setattr(loop_gate.os, "replace", flaky)
    monkeypatch.setattr("time.sleep", lambda s: None)
    (tmp_path / "a.tmp").write_text("x", encoding="utf-8")
    loop_gate.replace_retry(tmp_path / "a.tmp", tmp_path / "a.json")
    assert (tmp_path / "a.json").read_text(encoding="utf-8") == "x" and calls["n"] == 3
    monkeypatch.setattr(loop_gate.os, "replace", lambda s, d: (_ for _ in ()).throw(PermissionError(5, "denied")))
    with pytest.raises(PermissionError):
        loop_gate.replace_retry(tmp_path / "a.tmp", tmp_path / "b.json", tries=3)
