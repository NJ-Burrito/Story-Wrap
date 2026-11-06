"""Instagram tool tests: no network (the http layer is replaced), no real credentials."""
import json
from datetime import datetime, timedelta, timezone

import pytest

import ig

TOKEN = "IGAAsecretTOKEN123456789"
ENV = {"IG_USER_ID": "1784", "IG_ACCESS_TOKEN": TOKEN, "IG_USERNAME": "storywrap"}
T0 = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


def make_repo(tmp_path, verdict="PASS", score=9, complete=True, video=True):
    ep = tmp_path / "bible/series/s/episodes/E01"
    ep.mkdir(parents=True)
    card = {"question_ar": "أينَ تنامُ الحقيبةُ الليلة؟", "comment_prompt_ar": "TODO",
            "choices": [{"id": "1", "text_ar": "١ على الرّفِّ"}, {"id": "2", "text_ar": "٢ في يدِ هُدى"}]}
    (ep / "shotlist.json").write_text(json.dumps({"end_card": card}, ensure_ascii=False), encoding="utf-8")
    (ep / "outline.md").write_text("# E01 «الحقيبة» / The Bag: outline\n", encoding="utf-8")
    w = tmp_path / "work/episodes/E01"
    (w / "gate").mkdir(parents=True)
    (w / "heal").mkdir()
    (w / "gate/report.json").write_text(json.dumps({"verdict": verdict, "complete": complete, "checks": []}), encoding="utf-8")
    (w / "heal/critic.json").write_text(json.dumps({"score": score}), encoding="utf-8")
    if video:
        (w / "episode.mp4").write_bytes(b"\x00" * 64)
    return tmp_path, w


class Fake:
    """Records calls; answers like the Graph API."""
    def __init__(self, comments=None, replies=None, status="FINISHED"):
        self.calls, self.status = [], status
        self.comments, self.replies = comments or [], replies or {}

    def __call__(self, method, url, headers=None, data=None):
        self.calls.append((method, url, dict(headers or {}), data))
        u = url.split("?")[0]
        if u.endswith("/content_publishing_limit"):
            return {"data": [{"quota_usage": 1, "config": {"quota_total": 100}}]}
        if u.endswith("/1784/media"):
            return {"id": "CONT1"}
        if "rupload.facebook.com" in u:
            return {"success": True}
        if u.endswith("/CONT1"):
            return {"status_code": self.status}
        if u.endswith("/media_publish"):
            return {"id": "MEDIA1"}
        if u.endswith("/MEDIA1"):
            return {"permalink": "https://www.instagram.com/reel/abc/", "timestamp": "2026-11-01T12:00:00+0000", "username": "storywrap"}
        if u.endswith("/MEDIA1/comments"):
            if "after=X" in url:
                return {"data": self.comments[2:]}
            return {"data": self.comments[:2], "paging": {"next": "https://graph.instagram.com/v26.0/MEDIA1/comments?after=X&access_token=" + TOKEN}}
        if u.endswith("/replies"):
            return {"data": self.replies.get(u.split("/")[-2], [])}
        raise AssertionError("unexpected call " + url)


@pytest.fixture
def fake(monkeypatch):
    f = Fake()
    monkeypatch.setattr(ig, "_http", f)
    return f


@pytest.mark.parametrize("kw,frag", [
    ({"verdict": "FAIL"}, "not PASS"), ({"complete": False}, "INCOMPLETE"), ({"score": 8}, "< 9"), ({"video": False}, "episode.mp4"),
])
def test_publish_refuses_without_gates(tmp_path, fake, kw, frag):
    repo, w = make_repo(tmp_path, **kw)
    with pytest.raises(SystemExit) as e:
        ig.cmd_publish("E01", go=True, repo=repo, env=dict(ENV))
    assert "IG-GATE" in str(e.value) and frag in str(e.value)
    assert fake.calls == [] and not (w / "post.json").exists()


def test_publish_refuses_missing_reports(tmp_path, fake):
    repo, w = make_repo(tmp_path)
    (w / "gate/report.json").unlink()
    (w / "heal/critic.json").unlink()
    with pytest.raises(SystemExit) as e:
        ig.cmd_publish("E01", go=True, repo=repo, env=dict(ENV))
    assert "report missing" in str(e.value) and "critic record missing" in str(e.value)


def test_dry_run_makes_no_call_and_needs_no_credentials(tmp_path, fake, capsys):
    repo, w = make_repo(tmp_path)
    plan = ig.cmd_publish("E01", go=False, repo=repo, env={})
    assert fake.calls == [] and plan["mode"] == "DRY RUN" and not (w / "post.json").exists()
    out = capsys.readouterr().out
    assert "الحلقة ١" in out and "«على الرف»" in out and "«في يد هدى»" in out and "قولوا لنا لماذا" in out and "الحلقة القادمة تتبع ما تكتبونه." in out
    assert "اكتبوا اختياركم" not in out and "١ أو ٢" not in out and out.count("#") == 3 and not ig.caption_problems(out)


def test_publish_go_flow_and_post_json(tmp_path, fake):
    repo, w = make_repo(tmp_path)
    ig.cmd_publish("E01", go=True, repo=repo, env=dict(ENV), sleep=lambda s: None)
    post = json.loads((w / "post.json").read_text(encoding="utf-8"))
    assert post["media_id"] == "MEDIA1" and post["permalink"].endswith("/abc/") and post["posted_at"]
    urls = [c[1].split("?")[0] for c in fake.calls]
    i_media = next(i for i, u in enumerate(urls) if u.endswith("/1784/media"))
    i_pub = next(i for i, u in enumerate(urls) if u.endswith("/media_publish"))
    assert i_media < i_pub
    media = fake.calls[i_media]
    body = media[3].decode()
    assert "media_type=REELS" in body and "upload_type=resumable" in body and "caption=" in body
    assert TOKEN not in json.dumps(post) and TOKEN not in media[1]


def test_publish_stops_if_container_not_finished(tmp_path, monkeypatch):
    monkeypatch.setattr(ig, "_http", Fake(status="ERROR"))
    repo, w = make_repo(tmp_path)
    with pytest.raises(SystemExit) as e:
        ig.cmd_publish("E01", go=True, repo=repo, env=dict(ENV), sleep=lambda s: None)
    assert "IG-PROCESS" in str(e.value) and not (w / "post.json").exists()


def test_publish_refuses_double_post(tmp_path, fake):
    repo, w = make_repo(tmp_path)
    (w / "post.json").write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        ig.cmd_publish("E01", go=True, repo=repo, env=dict(ENV))
    assert "IG-ALREADY" in str(e.value) and fake.calls == []


def test_missing_credentials_message_names_keys_not_values(tmp_path, fake):
    repo, w = make_repo(tmp_path)
    with pytest.raises(SystemExit) as e:
        ig.cmd_publish("E01", go=True, repo=repo, env={})
    assert "IG_USER_ID" in str(e.value) and "IG-CREDS" in str(e.value)


def posted(w):
    (w / "post.json").write_text(json.dumps({"media_id": "MEDIA1", "posted_at": T0.isoformat(), "username": "storywrap"}), encoding="utf-8")


def test_comments_refused_before_12h(tmp_path, fake):
    repo, w = make_repo(tmp_path)
    posted(w)
    with pytest.raises(SystemExit) as e:
        ig.cmd_comments("E01", repo=repo, env=dict(ENV), at=T0 + timedelta(hours=11, minutes=59))
    assert "IG-TOO-EARLY" in str(e.value) and fake.calls == [] and not (w / "comments.json").exists()


def test_comments_after_12h_paginate_with_replies_and_force(tmp_path, monkeypatch):
    f = Fake(comments=[{"id": f"c{i}", "text": str(i), "username": "u"} for i in range(1, 4)], replies={"c1": [{"id": "r1", "text": "٢", "username": "v"}]})
    monkeypatch.setattr(ig, "_http", f)
    repo, w = make_repo(tmp_path)
    posted(w)
    res = ig.cmd_comments("E01", repo=repo, env=dict(ENV), at=T0 + timedelta(hours=12))
    assert [c["id"] for c in res["comments"]] == ["c1", "r1", "c2", "c3"] and res["comments"][1]["parent_id"] == "c1"
    f2 = Fake(comments=[])
    monkeypatch.setattr(ig, "_http", f2)
    ig.cmd_comments("E01", force=True, repo=repo, env=dict(ENV), at=T0 + timedelta(hours=1))
    assert f2.calls


def test_no_credential_in_any_output_file_or_stdout(tmp_path, monkeypatch, capsys):
    f = Fake(comments=[{"id": "c1", "text": "1", "username": "u"}])
    monkeypatch.setattr(ig, "_http", f)
    repo, w = make_repo(tmp_path)
    ig.cmd_publish("E01", go=True, repo=repo, env=dict(ENV), sleep=lambda s: None)
    ig.cmd_comments("E01", repo=repo, env=dict(ENV), at=datetime.now(timezone.utc) + timedelta(hours=13))
    ig.cmd_status(repo=repo, env=dict(ENV))
    blob = capsys.readouterr().out
    for p in tmp_path.rglob("*"):
        if p.is_file():
            blob += p.read_text(encoding="utf-8", errors="ignore")
    assert TOKEN not in blob


def test_http_error_is_redacted(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError(f"HTTP 400 GET https://x/y?access_token={TOKEN}&a=1 body {TOKEN}")
    monkeypatch.setattr(ig, "_http", boom)
    with pytest.raises(SystemExit) as e:
        ig.api(dict(ENV), "GET", "me")
    assert TOKEN not in str(e.value) and "REDACTED" in str(e.value)


def test_paging_to_foreign_host_is_refused(monkeypatch):
    monkeypatch.setattr(ig, "_http", lambda *a, **k: {"data": [], "paging": {"next": "https://evil.example/x?access_token=1"}})
    with pytest.raises(SystemExit) as e:
        ig.pages(dict(ENV), "M/comments", {})
    assert "IG-PAGING" in str(e.value)


def test_refresh_saves_new_token_and_respects_24h(tmp_path, monkeypatch, capsys):
    envf = tmp_path / "instagram.env"
    envf.write_text(f"IG_USER_ID=1784\nIG_ACCESS_TOKEN={TOKEN}\n", encoding="utf-8")
    monkeypatch.setattr(ig, "_http", lambda *a, **k: {"access_token": "NEWTOKENabcdef", "expires_in": 5183944})
    ig.cmd_refresh(path=envf, at=T0)
    saved = envf.read_text(encoding="utf-8")
    assert "IG_ACCESS_TOKEN=NEWTOKENabcdef" in saved and TOKEN not in saved and "IG_TOKEN_ISSUED=" in saved and "IG_USER_ID=1784" in saved
    out = capsys.readouterr().out
    assert "NEWTOKEN" not in out and TOKEN not in out
    with pytest.raises(SystemExit) as e:
        ig.cmd_refresh(path=envf, at=T0 + timedelta(hours=2))
    assert "IG-REFRESH-EARLY" in str(e.value)


def test_status_offline_lists_state(tmp_path, capsys):
    repo, w = make_repo(tmp_path)
    s = ig.cmd_status(repo=repo, env=dict(ENV))
    assert "E01: not posted; ready to post" in s and "IG_USER_ID: set" in s
    (w / "heal/critic.json").write_text(json.dumps({"score": 7}), encoding="utf-8")
    assert "blocked" in ig.cmd_status(repo=repo, env=dict(ENV))


def test_plan_prints_command_and_registers_nothing(tmp_path, monkeypatch):
    import subprocess
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not run")))
    repo, w = make_repo(tmp_path)
    posted(w)
    c = ig.cmd_plan("E01", repo)
    assert "schtasks /Create" in c and "fb.py harvest E01" in c and "vote.py tally E01" in c and "vote.py next E01" in c


def test_caption_and_reply_have_no_tashkeel(tmp_path):
    from arabic_display import has_tashkeel
    repo, w = make_repo(tmp_path)
    assert not has_tashkeel(ig.build_caption("E01", repo))
    assert ig.reply_text("أهلًا هُدى") == "أهلا هدى"


def test_publish_refuses_vowelled_caption(tmp_path, fake, monkeypatch):
    repo, w = make_repo(tmp_path)
    monkeypatch.setattr(ig, "build_caption", lambda ep, repo=None: "هُدى")
    with pytest.raises(SystemExit) as e:
        ig.cmd_publish("E01", go=True, repo=repo, env=dict(ENV))
    assert "IG-NO-TASHKEEL" in str(e.value) and fake.calls == []


# ---------------------------------------------------------------- publish host/token (graph.facebook.com + Page token)
PUB = "EAAPAGEpublishTOKEN987654"


def test_publish_env_swaps_host_and_token_only_when_set():
    e = ig.publish_env({**ENV, "IG_PUBLISH_TOKEN": PUB})
    assert e["IG_API_HOST"] == "graph.facebook.com" and e["IG_ACCESS_TOKEN"] == PUB
    e2 = ig.publish_env({**ENV, "IG_PUBLISH_TOKEN": PUB, "IG_PUBLISH_HOST": "graph.example.test"})
    assert e2["IG_API_HOST"] == "graph.example.test"
    assert ig.publish_env(dict(ENV)) == ENV and ig.base(ig.publish_env(dict(ENV))).startswith("https://graph.instagram.com/")


def test_publish_flow_uses_publish_host_and_token(tmp_path, fake):
    repo, w = make_repo(tmp_path)
    ig.cmd_publish("E01", go=True, repo=repo, env={**ENV, "IG_PUBLISH_TOKEN": PUB}, sleep=lambda s: None)
    assert len(fake.calls) == 6
    for method, url, headers, data in fake.calls:
        if "rupload.facebook.com" in url:
            assert headers["Authorization"] == f"OAuth {PUB}"
        else:
            assert url.startswith("https://graph.facebook.com/v26.0/") and headers["Authorization"] == f"Bearer {PUB}"
    assert TOKEN not in (w / "post.json").read_text(encoding="utf-8") and PUB not in (w / "post.json").read_text(encoding="utf-8")


def test_publish_falls_back_to_login_token_without_publish_token(tmp_path, fake):
    repo, w = make_repo(tmp_path)
    ig.cmd_publish("E01", go=True, repo=repo, env=dict(ENV), sleep=lambda s: None)
    assert all(c[1].startswith("https://graph.instagram.com/") for c in fake.calls if "rupload" not in c[1])


def test_non_publish_calls_keep_login_host(fake):
    env = {**ENV, "IG_PUBLISH_TOKEN": PUB}
    fake.comments = []
    ig.api(env, "GET", "MEDIA1/comments", {"fields": "id"})
    assert fake.calls[-1][1].startswith("https://graph.instagram.com/") and fake.calls[-1][2]["Authorization"] == f"Bearer {TOKEN}"


def test_publish_token_is_redacted():
    env = {**ENV, "IG_PUBLISH_TOKEN": PUB}
    assert PUB not in ig.redact(f"oops {PUB} again", env)
