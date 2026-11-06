"""The Haiku engagement role (R-474 to R-479): decisions, likes and reactions, no-API likes, DMs, ice breakers, comment-to-DM. No network, no model call, no credentials."""
import json
import subprocess
from datetime import datetime, timedelta, timezone

from pathlib import Path

import pytest

import daily
import dm_auto
import engage
import sw_fixtures
import fb
import ig
import inbox

START = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)      # 15:00 Amman
SECRET = "EAAsecrettoken123456789"


def t(h):
    return START + timedelta(hours=h)


def stamp(d):
    return d.strftime("%Y-%m-%dT%H:%M:%S+0000")


@pytest.fixture(autouse=True)
def neutral_engage_data(monkeypatch):
    """Where a root has no data/engage/*.json the tools fall back to the user's own files; the tests use the neutral fixtures instead."""
    lex, cfg = engage.lexicon_path, dm_auto.config_path
    monkeypatch.setattr(engage, "lexicon_path", lambda root: lex(root) if (Path(root) / "data" / "engage" / "lexicon.json").is_file() else sw_fixtures.PROJECT / "data" / "engage" / "lexicon.json")
    monkeypatch.setattr(dm_auto, "config_path", lambda root=None: cfg(root) if (Path(root or ig.REPO) / "data" / "engage" / "dm_auto.json").is_file() else sw_fixtures.PROJECT / "data" / "engage" / "dm_auto.json")


@pytest.fixture
def repo(tmp_path):
    w = tmp_path / "work" / "episodes" / "E01"
    w.mkdir(parents=True)
    (w / "post.json").write_text(json.dumps({"episode": "E01", "media_id": "M1", "posted_at": START.isoformat()}), encoding="utf-8")
    (w / "facebook.json").write_text(json.dumps({"episode": "E01", "video_id": "V1", "state": "scheduled", "posted_at": START.isoformat(), "publish_at": START.isoformat()}), encoding="utf-8")
    (w / "youtube.json").write_text(json.dumps({"episode": "E01", "video_id": "Y1", "state": "uploaded", "upload_status": "uploaded", "posted_at": START.isoformat()}), encoding="utf-8")
    (tmp_path / "board" / "data").mkdir(parents=True)
    return tmp_path


def comment(platform, mid, text, when_h, sender=None, own=False, sid=None):
    thread = {"instagram": "M1", "facebook": "555_V1", "youtube": "Y1"}[platform]
    return inbox.row("comment", platform, "StoryPage", thread, "", mid, "", sender or f"user{mid}", sid or sender or f"u{mid}", own, stamp(t(when_h)), text)


def dm(platform, mid, text, when_h, sender="u9"):
    return inbox.row("dm", platform, "StoryPage", "conv-" + sender, "", mid, "", sender, sender, False, stamp(t(when_h)), text)


class Rec:
    """Records sends, likes and private replies; any can be told to fail."""
    def __init__(self):
        self.sent, self.liked, self.pm = [], [], []

    def sender(self, item, text, gif, env):
        self.sent.append((item["platform"], item["id"], text))
        return f"r{len(self.sent)}"

    def liker(self, pf):
        def f(item, env):
            if engage.no_api_like(item, pf):
                raise engage.NoApi("no API")
            self.liked.append((pf, item["id"], item["kind_raw"]))
            return "react" if item["kind_raw"] == "dm" else "like"
        return f

    def pmsender(self, pf):
        def f(item, text, env):
            self.pm.append((pf, item["id"], text))
            return "pm1"
        return f


def tick(repo, rows, now, rec=None, go=True, llm=None, env=None, **kw):
    rec = rec or Rec()
    res = engage.run(go=go, root=repo, now=now, harvest=lambda s: 0, senders={p: rec.sender for p in engage.PLATFORMS}, likers={p: rec.liker(p) for p in engage.PLATFORMS},
                     pm_senders={p: rec.pmsender(p) for p in engage.PM_PLATFORMS}, env=env or {"IG_ACCESS_TOKEN": SECRET}, use_llm=llm is not None, llm=llm, do_lexicon=False,
                     rows=rows, sleep=lambda x: None, **kw)
    return res, rec


def state(repo):
    return json.loads((repo / "work" / "engage" / "state.json").read_text(encoding="utf-8"))["items"]


def jl(repo, name):
    p = repo / "work" / "engage" / name
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


def model(out):
    def llm(prompt, name, tools, effort):
        assert tools == "NONE" and "untrusted" in prompt and "FACTS" in prompt
        return {"rc": 0, "text": json.dumps(out, ensure_ascii=False)}
    return llm


# ------------------------------------------------------------------ the numbers and the model call
def test_new_numbers_are_the_documented_ones():
    assert (engage.RUN_CAP, engage.DAY_CAP["instagram"], engage.DAY_CAP["facebook"], engage.DAY_CAP["youtube"], engage.DAY_CAP["dm_instagram"]) == (5, 20, 20, 20, 15)
    assert engage.DELAY_MIN["question"] == (2, 8) and engage.DM_DELAY == (1, 4) and engage.QUIET[0].hour == 0 and engage.QUIET[1].minute == 30
    assert engage.HAIKU_MODEL == "haiku"


def test_haiku_runner_swaps_the_model_and_drops_effort(monkeypatch, tmp_path):
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = list(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"result": "{}", "usage": {"input_tokens": 3, "output_tokens": 2}}), stderr="")
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(daily, "claude_exe", lambda: "claude.exe")
    r = engage.haiku_llm(tmp_path)("hi", name="engage-haiku", tools="NONE", effort="low")
    cmd = seen["cmd"]
    assert r["rc"] == 0 and cmd[cmd.index("--model") + 1] == "haiku" and "--effort" not in cmd and "--allowedTools" not in cmd and cmd[cmd.index("--tools") + 1] == ""
    assert not any("gemini" in c.lower() for c in cmd)


def test_parse_decisions_accepts_objects_and_plain_strings_and_drops_junk():
    out = engage.parse_decisions('x {"a": {"action": "like", "why": "short thanks"}, "b": "شكرا لك 🌟", "c": {"action": "dance"}, "d": 5} y')
    assert out["a"]["action"] == "like" and out["b"] == {"action": "reply", "text": "شكرا لك 🌟", "reaction": "love", "why": ""} and "c" not in out and "d" not in out


def test_facts_digest_has_the_premise_and_characters():
    f = engage.story_facts(sw_fixtures.PROJECT)
    assert "Premise" in f and "hero" in f.lower() and len(f) < engage.FACTS_MAX + 200


# ------------------------------------------------------------------ decisions
def test_model_decides_reply_like_react_and_skip(repo):
    rows = [comment("facebook", "f1", "متى الحلقة؟", 2, sender="fan1"), comment("facebook", "f2", "❤️", 2, sender="fan2"), comment("instagram", "i1", "🔥🔥", 2, sender="fan3"),
            dm("instagram", "d1", "حلو", 2, sender="u1"), comment("youtube", "y1", "اممم", 2, sender="fan4"), comment("youtube", "y2", "واو", 2, sender="fan5")]
    llm = model({"facebook:f1": {"action": "reply", "text": "قريبا جدا 🔑", "why": "asked when"}, "facebook:f2": {"action": "like", "why": "just a heart"},
                 "instagram:i1": {"action": "like", "why": "fire emoji"}, "instagram:d1": {"action": "react", "why": "thanks"}, "youtube:y1": {"action": "skip", "why": "unclear"},
                 "youtube:y2": {"action": "reply", "text": "واو منك 🙌", "why": "wow"}})
    res, rec = tick(repo, rows, t(3), llm=llm)
    st = state(repo)
    assert res["llm"] and st["facebook:f1"]["how"] == "llm"
    assert ("facebook", "f1", "قريبا جدا 🔑") in rec.sent and ("youtube", "y2", "واو منك 🙌") in rec.sent
    assert ("facebook", "f2", "comment") in rec.liked and ("facebook", "f1", "comment") in rec.liked        # the answered comment is liked too; the heart is only liked
    assert ("instagram", "d1", "dm") in rec.liked                                              # the DM gets a reaction
    assert st["facebook:f2"]["status"] == "liked" and st["instagram:d1"]["status"] == "liked"
    assert st["youtube:y1"]["status"] == "skip" and st["youtube:y1"]["reason"].startswith("model: ")
    assert st["instagram:i1"]["status"] == "noapi_like"                                       # Instagram comment like: no API
    todo = jl(repo, "likes_todo.jsonl")
    assert {(x["platform"], x["comment_id"]) for x in todo} == {("instagram", "i1"), ("youtube", "y2")} and all("no API" in x["reason"] for x in todo)


def test_the_hard_gate_runs_before_the_model_sees_anything(repo):
    seen = {}

    def llm(prompt, name, tools, effort):
        seen["p"] = prompt
        return {"rc": 0, "text": "{}"}
    rows = [comment("instagram", "c1", "ممل جدا", 2), comment("instagram", "c2", "تابعني https://a.com", 2), comment("instagram", "c3", "ما رأيكم بالانتخابات", 2),
            comment("instagram", "c4", "عمري 12 سنة", 2), comment("instagram", "c5", "رائع جدا", 2, sender="story_account"), comment("instagram", "c6", "شكرا لكم", 2, sender="owner_account")]
    tick(repo, rows, t(3), llm=llm)
    items = json.loads(seen["p"].split("<<<VIEWER_DATA" + chr(10), 1)[1].split(chr(10) + "VIEWER_DATA>>>", 1)[0])
    assert [i["key"] for i in items] == ["instagram:c6"]                                      # only the owner's account: he is answered like any viewer


def test_a_model_text_that_breaks_the_gates_falls_back_to_the_template(repo):
    rows = [comment("instagram", "c1", "متى الحلقة القادمة؟", 2), comment("instagram", "c2", "متى الحلقة القادمة يا ترى؟", 2), comment("instagram", "c3", "متى الحلقة؟", 2)]
    llm = model({"instagram:c1": "ممتاز https://x.com", "instagram:c2": "سنجيب 🌟🌟🌟🌟", "instagram:c3": "تابعونا وشاركوا"})
    tick(repo, rows, t(3), llm=llm, go=False)
    st = state(repo)
    assert all(st[f"instagram:c{i}"]["how"] == "template" and st[f"instagram:c{i}"]["status"] == "drafted" for i in (1, 2, 3))


def test_the_model_may_answer_in_the_commenters_dialect_or_language(repo):
    rows = [comment("instagram", "c1", "when is the next episode?", 2), comment("instagram", "c2", "شو القصة يا جماعة؟", 2)]
    llm = model({"instagram:c1": "Soon! the key is still looking for its lock 🔑", "instagram:c2": "القصة بتبلّش مع حقيبة هدى 🎒"})
    tick(repo, rows, t(3), llm=llm, go=False)
    st = state(repo)
    assert st["instagram:c1"]["how"] == "llm" and st["instagram:c2"]["how"] == "llm"
    assert engage.reply_problems("Soon! the key 🔑") and engage.reply_problems("Soon! the key 🔑", relaxed=True) == []        # the strict gate is still the template gate
    assert any("tashkeel" in w for w in engage.reply_problems("مَرحبا", relaxed=True))


def test_model_failure_falls_back_and_the_tick_goes_on(repo):
    rows = [comment("instagram", "c1", "متى الحلقة القادمة؟", 2)]
    res, rec = tick(repo, rows, t(3), llm=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert not res["llm"] and state(repo)["instagram:c1"]["how"] == "template" and len(rec.sent) == 1


def test_without_a_model_the_template_bank_varies_replies_and_likes_the_rest(repo):
    rows = [comment("facebook", f"f{i}", "ما شاء الله رائع", 2, sender=f"fan{i}") for i in range(20)]
    res, rec = tick(repo, rows, t(3))
    st = state(repo)
    kinds = {v["status"] for v in st.values()}
    assert "liked" in kinds and kinds <= {"sent", "liked", "drafted"}


# ------------------------------------------------------------------ speed
def test_old_items_go_on_the_same_tick_new_ones_after_two_to_eight_minutes(repo):
    old = comment("instagram", "c1", "متى الحلقة القادمة؟", 2)
    new = comment("instagram", "c2", "متى الحلقة القادمة يا ترى؟", 2.99)
    res, rec = tick(repo, [old, new], t(3))
    assert [x[1] for x in rec.sent] == ["c1"]
    nb = datetime.fromisoformat(state(repo)["instagram:c2"]["not_before"])
    assert t(2.99) + timedelta(minutes=2) <= nb <= t(2.99) + timedelta(minutes=8)
    res, rec = tick(repo, [old, new], t(3.2))
    assert [x[1] for x in rec.sent] == ["c2"]


def test_quiet_hours_still_hold_back_everything(repo):
    night = datetime(2026, 10, 26, 22, 30, tzinfo=timezone.utc)                 # 01:30 Amman
    rows = [comment("facebook", "f1", "متى الحلقة؟", 9.9, sender="a"), comment("facebook", "f2", "❤️", 9.9, sender="b")]
    res, rec = tick(repo, rows, night)
    assert rec.sent == [] and rec.liked == []


# ------------------------------------------------------------------ likes and reactions
def test_facebook_comment_like_uses_the_page_token_endpoint(monkeypatch):
    calls = []

    def fake_http(method, url, headers=None, data=None):
        calls.append((method, url, dict(headers or {}), data))
        return {"success": True}
    monkeypatch.setattr(ig, "_http", fake_http)
    assert fb.like_comment({"FB_PAGE_TOKEN": SECRET}, "555_999") is True
    m, url, h, data = calls[0]
    assert m == "POST" and url.endswith("/555_999/likes") and h["Authorization"] == f"Bearer {SECRET}" and SECRET not in url
    with pytest.raises(SystemExit):
        fb.like_comment({"FB_PAGE_TOKEN": SECRET}, "bad/id")


def test_reactions_use_the_sender_action_react_with_love(monkeypatch):
    calls = []
    monkeypatch.setattr(ig, "api", lambda env, method, path, params=None, **kw: calls.append((method, path, params)) or {})
    monkeypatch.setattr(ig, "publish_env", lambda env: env)
    dm_auto.react_instagram_dm({"FB_PAGE_ID": "P1", "IG_ACCESS_TOKEN": SECRET}, "U1", "mid.1")
    m, path, params = calls[0]
    assert m == "POST" and path == "P1/messages" and params["sender_action"] == "react" and json.loads(params["recipient"]) == {"id": "U1"}
    assert json.loads(params["payload"]) == {"message_id": "mid.1", "reaction": "love"}
    calls.clear()
    monkeypatch.setattr(fb, "api", lambda env, method, path, params=None, **kw: calls.append((method, path, params)) or {})
    dm_auto.react_messenger_dm({"FB_PAGE_ID": "P1", "FB_PAGE_TOKEN": SECRET}, "U2", "mid.2")
    assert calls[0][2]["sender_action"] == "react" and json.loads(calls[0][2]["payload"])["reaction"] == "love"


def test_instagram_and_youtube_comment_likes_are_recorded_not_faked(repo):
    rows = [comment("instagram", "i1", "❤️", 2, sender="a"), comment("youtube", "y1", "❤️", 2, sender="b")]
    llm = model({"instagram:i1": {"action": "like", "why": "heart"}, "youtube:y1": {"action": "like", "why": "heart"}})
    res, rec = tick(repo, rows, t(3), llm=llm)
    assert rec.liked == [] and set(res["noapi_likes"]) == {"instagram:i1", "youtube:y1"}
    assert {s["status"] for s in state(repo).values()} == {"noapi_like"}
    assert {x["platform"] for x in jl(repo, "likes_todo.jsonl")} == {"instagram", "youtube"}


def test_dry_run_lists_likes_and_writes_no_todo(repo):
    rows = [comment("facebook", "f1", "❤️", 2, sender="a"), comment("instagram", "i1", "❤️", 2, sender="b")]
    llm = model({"facebook:f1": {"action": "like", "why": "x"}, "instagram:i1": {"action": "like", "why": "x"}})
    res, rec = tick(repo, rows, t(3), llm=llm, go=False)
    assert res["would_like"] == ["facebook:f1"] and res["noapi_likes"] == ["instagram:i1"] and rec.liked == [] and not (repo / "work" / "engage" / "likes_todo.jsonl").exists()


def test_a_failing_like_never_fails_the_reply(repo):
    rec = Rec()
    rec.liker = lambda pf: (lambda item, env: (_ for _ in ()).throw(SystemExit(f"FAIL [FB-HTTP] token {SECRET} rejected")))
    res, rec = tick(repo, [comment("facebook", "f1", "متى الحلقة؟", 2, sender="a")], t(3), rec=rec)
    st = state(repo)["facebook:f1"]
    assert st["status"] == "sent" and SECRET not in st.get("like_error", "")
    assert SECRET not in (repo / "work" / "engage" / "state.json").read_text(encoding="utf-8")


def test_like_day_cap(repo):
    for i in range(engage.LIKE_DAY_CAP):
        engage.append_jsonl(repo / "work" / "engage" / "likes.jsonl", {"at": t(2).isoformat(), "platform": "facebook", "ok": True, "episode": "E01"})
    llm = model({"facebook:f1": {"action": "like", "why": "x"}})
    res, rec = tick(repo, [comment("facebook", "f1", "❤️", 2, sender="a")], t(3), llm=llm)
    assert rec.liked == [] and state(repo)["facebook:f1"]["status"] == "drafted"


# ------------------------------------------------------------------ our own accounts, per platform
@pytest.mark.parametrize("pf,kw,env", [
    ("instagram", {"sender": "story_account"}, {}),
    ("instagram", {"sender": "unknown", "sid": "17841"}, {"IG_USER_ID": "17841"}),
    ("facebook", {"sender": "StoryPage", "sid": "PAGE1"}, {"FB_PAGE_ID": "PAGE1"}),
    ("youtube", {"sender": "NJ Story", "sid": "UCown"}, {"YT_CHANNEL_ID": "UCown"}),
    ("youtube", {"sender": "NJ Story", "sid": "UCx", "own": True}, {}),
])
def test_never_reply_to_like_or_react_to_our_own_comments(repo, pf, kw, env):
    rows = [comment(pf, "o1", "متى الحلقة القادمة؟", 2, **kw)]
    llm = model({f"{pf}:o1": {"action": "like", "why": "x"}})
    res, rec = tick(repo, rows, t(3), llm=llm, env={"IG_ACCESS_TOKEN": SECRET, **env})
    assert rec.sent == [] and rec.liked == [] and rec.pm == [] and jl(repo, "likes_todo.jsonl") == []
    assert not state(repo) or state(repo)[f"{pf}:o1"]["status"] == "skip"


# ------------------------------------------------------------------ DMs
def test_owner_dms_are_answered_on_the_next_tick_inside_24h(repo):
    rows = [dm("instagram", "m1", "واو شو حلو", -3, sender="owner"), dm("instagram", "m2", "🔥", -2, sender="owner")]
    res, rec = tick(repo, rows, t(1))
    st = state(repo)
    assert st["instagram:m1"]["kind"] == "praise" and st["instagram:m2"]["kind"] == "praise"
    assert st["instagram:m1"]["status"] in ("sent", "liked") and st["instagram:m2"]["status"] in ("sent", "liked") and (rec.sent or rec.liked)
    assert all(it["dm"] for it in st.values())


def test_a_dm_older_than_24h_is_not_answered(repo):
    res, rec = tick(repo, [dm("instagram", "m1", "واو شو حلو", -30, sender="owner")], t(1))
    assert rec.sent == [] and state(repo)["instagram:m1"]["reason"] == "outside the 24 h messaging window"


def test_dms_on_facebook_get_a_reaction_and_youtube_has_no_dms(repo):
    llm = model({"facebook:m1": {"action": "reply", "text": "أهلا بك 🙌", "why": "greeting"}})
    res, rec = tick(repo, [dm("facebook", "m1", "مرحبا كيف حالكم؟", 2, sender="u5")], t(3), llm=llm)
    assert ("facebook", "m1", "أهلا بك 🙌") in rec.sent and ("facebook", "m1", "dm") in rec.liked
    assert engage.SOURCES_FOR["youtube"] == ("youtube_comments",)                              # YouTube has no DM API: no DM source


def test_ice_breaker_tap_gets_its_canned_answer_without_the_model(repo):
    cfg = dm_auto.load_config(repo)
    q = cfg["ice_breakers"][0]["question"]
    called = []
    res, rec = tick(repo, [dm("instagram", "m1", q, 2, sender="u5")], t(3), llm=lambda *a, **k: called.append(1) or {"rc": 0, "text": "{}"})
    assert called == [] and rec.sent[0][2] == cfg["ice_breakers"][0]["answer"]
    assert state(repo)["instagram:m1"]["how"] == "ice"


def test_welcome_goes_to_a_first_short_dm_only_once(repo):
    cfg = dm_auto.load_config(repo)
    res, rec = tick(repo, [dm("instagram", "m1", "اهلا", 2, sender="u5")], t(3))
    assert rec.sent[0][2] == cfg["welcome"]["text"] and state(repo)["instagram:m1"]["how"] == "welcome"
    res, rec = tick(repo, [dm("instagram", "m1", "اهلا", 2, sender="u5"), dm("instagram", "m2", "ممكن", 3.5, sender="u5")], t(4))
    assert state(repo)["instagram:m2"]["how"] != "welcome"


# ------------------------------------------------------------------ comment-to-DM
def test_keyword_comment_gets_one_private_reply_per_person_per_post(repo):
    cfg = dm_auto.load_config(repo)
    rows = [comment("instagram", "k1", "وين الحلقة الكاملة", 2, sender="ana", sid="S1"), comment("instagram", "k2", "ابغى الحلقة", 2.1, sender="ana", sid="S1"),
            comment("instagram", "k3", "القصة تجنن", 2, sender="bob", sid="S2"), comment("facebook", "k4", "الحلقة حلوة", 2, sender="ana", sid="S1")]
    res, rec = tick(repo, rows, t(3))
    assert sorted((p, i) for p, i, _ in rec.pm) == [("facebook", "k4"), ("instagram", "k1"), ("instagram", "k3")]        # ana once on Instagram; the same person on Facebook is another post
    assert all(txt == cfg["comment_to_dm"]["text"] for _, _, txt in rec.pm)
    assert len(jl(repo, "pm.jsonl")) == 3
    res, rec = tick(repo, rows, t(4))
    assert rec.pm == []                                                                          # never twice


def test_private_reply_needs_a_clean_comment(repo):
    rows = [comment("instagram", "k1", "الحلقة ممل", 2, sender="a"), comment("instagram", "k2", "الحلقة واتصل بي 0799123456", 2, sender="b"),
            comment("instagram", "k3", "الحلقة https://x.com", 2, sender="c"), comment("instagram", "k4", "رابط الحلقة", 2, sender="d"), comment("instagram", "k5", "الحلقة والانتخابات", 2, sender="e")]
    res, rec = tick(repo, rows, t(3))
    assert [i for _, i, _ in rec.pm] == ["k4"]                                                    # «رابط» alone is a request here, not spam


def test_private_reply_dry_and_window_and_failure(repo):
    rows = [comment("instagram", "k1", "الحلقة", 2, sender="a", sid="S1")]
    res, rec = tick(repo, rows, t(3), go=False)
    assert res["pm_would_send"] == ["instagram:k1"] and rec.pm == []
    bad = Rec()
    bad.pmsender = lambda pf: (lambda item, text, env: (_ for _ in ()).throw(SystemExit("FAIL (#10) no permission")))
    res, rec = tick(repo, rows, t(3.1), rec=bad)
    assert state(repo)["instagram:k1"]["pm_error"] and "pm_instagram" in json.loads((repo / "work" / "engage" / "state.json").read_text(encoding="utf-8"))["halt"]
    res, rec = tick(repo, rows, t(3.2))
    assert rec.pm == []                                                                          # paused for 6 h, replies of the comments themselves unaffected


def test_private_reply_never_goes_to_our_own_comment(repo):
    res, rec = tick(repo, [comment("instagram", "k1", "الحلقة", 2, sender="story_account")], t(3))
    assert rec.pm == []


# ------------------------------------------------------------------ dm_auto: ice breakers
def test_config_texts_pass_the_gates_and_meta_limits():
    cfg = dm_auto.load_config(sw_fixtures.PROJECT)
    assert dm_auto.problems(cfg) == [] and 1 <= len(cfg["ice_breakers"]) <= 4 and all(len(b["question"]) <= 80 for b in cfg["ice_breakers"])
    for k in (cfg["welcome"]["text"], cfg["comment_to_dm"]["text"], *[b["answer"] for b in cfg["ice_breakers"]]):
        assert "http" not in k and not engage.has_tashkeel(k)


def test_apply_is_dry_by_default_and_go_posts_the_ice_breakers(tmp_path):
    calls = []
    api = lambda env, method, path, params=None, **kw: calls.append((method, path, params)) or {"result": "success"}
    dry = dm_auto.apply(go=False, root=tmp_path, api=api)
    assert dry["mode"] == "DRY" and not dry["set"] and calls == [] and len(dry["ice_breakers"]) == 4
    go = dm_auto.apply(go=True, root=tmp_path, env={"FB_PAGE_ID": "P1", "IG_ACCESS_TOKEN": SECRET}, api=api)
    m, path, params = calls[0]
    assert go["set"] and m == "POST" and path == "P1/messenger_profile" and params["platform"] == "instagram"
    ib = json.loads(params["ice_breakers"])
    assert ib[0]["locale"] == "default" and len(ib[0]["call_to_actions"]) == 4 and all(set(c) == {"question", "payload"} for c in ib[0]["call_to_actions"])
    assert SECRET not in json.dumps(go)


def test_apply_refuses_a_bad_config(tmp_path):
    (tmp_path / "data" / "engage").mkdir(parents=True)
    (tmp_path / "data" / "engage" / "dm_auto.json").write_text(json.dumps({"ice_breakers": [{"question": "س" * 90, "answer": "تابعونا https://a.com"}]}), encoding="utf-8")
    r = dm_auto.apply(go=True, root=tmp_path, env={"FB_PAGE_ID": "P1", "IG_ACCESS_TOKEN": SECRET}, api=lambda *a, **k: pytest.fail("must not be called"))
    assert r["status"].startswith("REFUSED") and r["problems"]


def test_status_reads_but_never_writes(tmp_path):
    calls = []
    api = lambda env, method, path, params=None, **kw: calls.append(method) or {"data": [{"ice_breakers": []}]}
    out = dm_auto.status(root=tmp_path, env={"FB_PAGE_ID": "P1", "IG_ACCESS_TOKEN": SECRET}, api=api)
    assert calls == ["GET"] and out["live_ice_breakers"] and len(out["ice_breakers"]) == 4
    assert dm_auto.status(root=tmp_path, live=False)["problems"] == []


def test_engagement_stops_calling_the_model_at_its_share_of_the_day(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: calls.append(1) or subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"result": "{}", "usage": {"input_tokens": engage.ENGAGE_DAY_TOKENS}}), stderr=""))
    monkeypatch.setattr(daily, "claude_exe", lambda: "claude.exe")
    call = engage.haiku_llm(tmp_path)
    assert call("a", name="engage-haiku")["rc"] == 0
    with pytest.raises(daily.StageFail):
        call("b", name="engage-haiku")
    assert len(calls) == 1 and engage.draft_with_llm(tmp_path, [{"key": "k", "kind": "chat", "kind_raw": "comment", "platform": "instagram", "text": "x"}], {}, [], llm=lambda *a, **k: (_ for _ in ()).throw(RuntimeError())) == {}


# ------------------------------------------------------------------ media-only items (R-480)
def media_row(platform, mid, when_h, kind="comment", att=(), sender=None):
    if kind == "dm":
        return inbox.row("dm", platform, "StoryPage", "conv-" + (sender or "u9"), "", mid, "", sender or "u9", sender or "u9", False, stamp(t(when_h)), "", att)
    return comment(platform, mid, "", when_h, sender=sender)


def test_media_classification():
    assert engage.classify("", media=True)[0] == "media" and engage.classify("")[0] == "other"
    assert engage.classify("ممل", media=True)[0] == "hostile" and engage.classify("❤️", media=True)[0] == "praise"        # a word or emoji still wins
    assert engage.is_media("", "comment") and engage.is_media("", "dm", "image/jpeg") and not engage.is_media("", "dm") and not engage.is_media("hi", "comment")


def test_an_empty_text_gif_comment_gets_a_playful_line_from_the_model(repo):
    seen = {}

    def llm(prompt, name, tools, effort):
        seen["p"] = prompt
        return {"rc": 0, "text": json.dumps({"instagram:g1": {"action": "reply", "text": "هذا الجيف لخص الحلقة كلها 😂", "why": "gif vibe"}})}
    res, rec = tick(repo, [media_row("instagram", "g1", 2)], t(3), llm=llm)
    st = state(repo)["instagram:g1"]
    assert st["kind"] == "media" and st["status"] == "sent" and rec.sent == [("instagram", "g1", "هذا الجيف لخص الحلقة كلها 😂")]
    assert '"kind": "media"' in seen["p"] and "GIF, sticker or image" in seen["p"]


def test_an_image_dm_is_answered_and_reacted_to_and_without_the_model_generically(repo):
    row = media_row("instagram", "m1", 2, kind="dm", att=["image/jpeg"])
    res, rec = tick(repo, [row], t(3))                                   # no model at all: the template bank answers warmly
    st = state(repo)["instagram:m1"]
    assert st["kind"] == "media" and st["dm"] and st["status"] in ("sent", "liked") and (rec.sent or rec.liked)
    res, rec = tick(repo, [media_row("facebook", "m2", 2, kind="dm", att=["image"], sender="u2")], t(3.1), llm=model({"facebook:m2": {"action": "react", "why": "photo"}}))
    assert ("facebook", "m2", "dm") in rec.liked and rec.sent == []        # an emoji reaction where the API has one


def test_a_dm_with_no_text_and_no_attachment_is_still_nothing_to_answer(repo):
    res, rec = tick(repo, [media_row("instagram", "m1", 2, kind="dm")], t(3))
    assert rec.sent == [] and state(repo)["instagram:m1"]["reason"] == "nothing to answer"


# ------------------------------------------------------------------ YouTube parity
def test_youtube_comment_is_answered_through_the_comments_api_and_liked_as_no_api(repo, monkeypatch):
    import sys
    import types
    inserted = []

    class Svc:
        def comments(self):
            return self

        def insert(self, part, body):
            inserted.append((part, body))
            return types.SimpleNamespace(execute=lambda: {"id": "yr1"})
    fake = types.SimpleNamespace(load_token=lambda: {}, service=lambda: Svc(), call=lambda fn, what, tok=None: fn())
    monkeypatch.setitem(sys.modules, "yt", fake)
    rows = [comment("youtube", "y1", "متى تنزل الحلقة القادمة؟", 2, sender="v1"), comment("youtube", "y2", "❤️", 2, sender="v2")]
    llm = model({"youtube:y1": {"action": "reply", "text": "قريبا جدا 🔑", "why": "asked when"}, "youtube:y2": {"action": "like", "why": "heart"}})
    res = engage.run(go=True, root=repo, now=t(3), harvest=lambda s: 0, senders={"youtube": engage.send_youtube}, likers={"youtube": engage.like_youtube}, env={}, use_llm=True, llm=llm,
                     do_lexicon=False, rows=rows, sleep=lambda x: None)
    assert inserted == [("snippet", {"snippet": {"parentId": "y1", "textOriginal": "قريبا جدا 🔑"}})]
    st = state(repo)
    assert st["youtube:y1"]["status"] == "sent" and st["youtube:y2"]["status"] == "noapi_like"
    assert {(x["platform"], x["comment_id"]) for x in jl(repo, "likes_todo.jsonl")} == {("youtube", "y1"), ("youtube", "y2")}       # the reply's like and the heart: both "no API"
    assert engage.send_youtube is engage.SENDERS["youtube"] and "youtube_dm" not in engage.SOURCES_FOR["youtube"]


def test_youtube_replies_pass_the_same_gates(repo):
    llm = model({"youtube:y1": "تابعونا https://x.com"})
    res, rec = tick(repo, [comment("youtube", "y1", "متى الحلقة؟", 2, sender="v1")], t(3), llm=llm, go=False)
    assert state(repo)["youtube:y1"]["how"] == "template"


# ------------------------------------------------------------------ the board feed
def test_board_engage_log_has_who_what_reply_action_why_time_and_the_no_api_list(repo):
    import monitor_board
    rows = [comment("instagram", "i1", "❤️", 2, sender="fan1"), comment("instagram", "i2", "متى الحلقة؟", 2, sender="fan2")]
    llm = model({"instagram:i1": {"action": "like", "why": "just a heart"}, "instagram:i2": {"action": "reply", "text": "قريبا 🔑", "why": "asked when"}})
    tick(repo, rows, t(3), llm=llm)
    items = engage.load_state(repo)["items"]
    e = monitor_board.engage_log("instagram", items, rows, engage.sent_rows(repo), repo)
    by = {x["key"]: x for x in e["log"]}
    assert by["instagram:i2"]["reply"] == "قريبا 🔑" and by["instagram:i2"]["action"] == "reply" and by["instagram:i2"]["why"] == "asked when" and by["instagram:i2"]["who"] == "fan2"
    assert by["instagram:i1"]["action"] == "like: no API" and len(by["instagram:i1"]["when"]["hms"]) == 8
    assert {x["comment_id"] for x in e["likes_todo"]} == {"i1", "i2"} and e["no_dm_api"] is False
    assert monitor_board.engage_log("youtube", items, rows, [], repo)["no_dm_api"] is True and monitor_board.engage_log("youtube", items, rows, [], repo)["log"] == []
