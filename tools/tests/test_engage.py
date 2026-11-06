"""Engagement window tests: no network, no real credentials, no model call. Senders, the harvest and the model are replaced."""
import json
import os
import time
from datetime import datetime, timedelta, timezone

from pathlib import Path

import pytest

import engage
import ig
import inbox
import learn
import sw_fixtures

START = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)      # 15:00 Amman
SECRET = "EAAsecrettoken123456789"


def t(h):
    return START + timedelta(hours=h)


def stamp(dtm):
    return dtm.strftime("%Y-%m-%dT%H:%M:%S+0000")


@pytest.fixture(autouse=True)
def neutral_lexicon(monkeypatch):
    """Where a root has no data/engage/lexicon.json the tool falls back to the user's own; the tests use the neutral fixture instead."""
    orig = engage.lexicon_path
    monkeypatch.setattr(engage, "lexicon_path", lambda root: orig(root) if (Path(root) / "data" / "engage" / "lexicon.json").is_file() else sw_fixtures.PROJECT / "data" / "engage" / "lexicon.json")


@pytest.fixture
def repo(tmp_path):
    w = tmp_path / "work" / "episodes" / "E01"
    w.mkdir(parents=True)
    (w / "post.json").write_text(json.dumps({"episode": "E01", "media_id": "M1", "posted_at": START.isoformat(), "permalink": "https://i/x"}), encoding="utf-8")
    (w / "facebook.json").write_text(json.dumps({"episode": "E01", "video_id": "V1", "state": "scheduled", "posted_at": START.isoformat(), "publish_at": (START + timedelta(hours=1)).isoformat()}), encoding="utf-8")
    (w / "youtube.json").write_text(json.dumps({"episode": "E01", "video_id": "Y1", "state": "uploaded", "upload_status": "uploaded", "posted_at": START.isoformat()}), encoding="utf-8")
    (tmp_path / "board" / "data").mkdir(parents=True)
    return tmp_path


def comment(platform, mid, text, when_h, thread=None, parent="", sender=None, own=False, kind=None):
    thread = thread or {"instagram": "M1", "facebook": "555_V1", "youtube": "Y1"}[platform]
    return inbox.row(kind or ("reply" if parent else "comment"), platform, "StoryPage", thread, "", mid, parent, sender or f"user{mid}", sender or f"u{mid}", own, stamp(t(when_h)), text)


def dm(platform, mid, text, when_h, sender="u9", own=False):
    return inbox.row("dm", platform, "StoryPage", "conv1", "", mid, "", sender, sender, own, stamp(t(when_h)), text)


class Sender:
    def __init__(self, fail=None):
        self.calls, self.fail = [], fail

    def __call__(self, item, text, gif, env):
        if self.fail:
            raise SystemExit(self.fail)
        self.calls.append((item["target"], text, gif))
        return f"r{len(self.calls)}"


def tick(repo, rows, now, go=False, sender=None, env=None, **kw):
    s = sender or Sender()
    res = engage.run(go=go, root=repo, now=now, harvest=lambda src: 0, senders={p: s for p in engage.PLATFORMS}, env=env or {"IG_ACCESS_TOKEN": SECRET}, use_llm=kw.pop("use_llm", False),
                     do_lexicon=False, rows=rows, sleep=lambda x: None, **kw)
    return res, s


# ------------------------------------------------------------------ windows
def test_windows_are_72h_from_each_platform(repo):
    w = engage.episode_windows(repo)["E01"]
    assert w["instagram"]["start"] == START and w["instagram"]["end"] == START + timedelta(hours=72)
    assert w["facebook"]["start"] == START + timedelta(hours=1)          # a scheduled Reel counts from its go-live time
    assert w["youtube"]["ids"] == ["Y1"]


def test_rows_match_their_episode_and_window(repo):
    w = engage.episode_windows(repo)
    assert engage.match_episode(comment("instagram", "c1", "x", 2), w) == "E01"
    assert engage.match_episode(comment("facebook", "c2", "x", 2), w) == "E01"        # Page post id 555_V1
    assert engage.match_episode(comment("youtube", "c3", "x", 2), w) == "E01"
    assert engage.match_episode(comment("instagram", "c4", "x", 2, thread="OTHER"), w) is None
    assert engage.match_episode(comment("instagram", "c5", "x", 73), w) is None       # after the window
    assert engage.match_episode(dm("instagram", "d1", "x", 5), w) == "E01"
    assert engage.match_episode(dm("instagram", "d2", "x", 80), w) == "E01"        # R-474: a DM belongs to the latest live post; the 24 h window (decide_item) limits the answer
    assert engage.match_episode(dm("instagram", "d3", "x", -5), w) == "E01"       # before the post: the first post after it


# ------------------------------------------------------------------ classification
@pytest.mark.parametrize("text,kind", [
    ("هههه حقيبة هدى ضحكتني", "joke"), ("متى تنزل الحلقة القادمة؟", "question"), ("ما شاء الله قصة جميلة جدا", "praise"), ("❤️", "praise"),
    ("أتمنى أن تفتح هدى الرف الذي بلا رقم وترى ما فيه", "idea"), ("ممل جدا", "hostile"), ("this is stupid", "hostile"), ("تابعني https://x.com/y", "spam"),
    ("عمري 12 سنة", "minor"), ("i'm 15 and love it", "minor"), ("ما رأيكم بالانتخابات", "sensitive"), ("ما رأيك بالدين", "sensitive"),
    ("مدينة جميلة", "praise"), ("الشخصية الرئيسية رائعة", "praise"), ("", "other"), ("عنوان الحلقة حلو", "praise"),
])
def test_classify(text, kind):
    assert engage.classify(text)[0] == kind


def test_sensitive_beats_friendly_and_vote_cue_does_not_beat_sensitive():
    assert engage.classify("رائع جدا لكن الحرب")[0] == "sensitive"
    assert engage.classify("الخيار الأول", vote_kind="vote")[0] == "vote"
    assert engage.classify("شيعي ", vote_kind="vote")[0] == "sensitive"


# ------------------------------------------------------------------ gates
@pytest.mark.parametrize("text,frag", [
    ("", "short"), ("مَرحبا بكم", "tashkeel"), ("x" * 5 + "ا" * 230, "characters"), ("شكرا https://a.com", "link"), ("شكرا #وسم", "link"), ("شكرا @فلان", "link"),
    ("علقوا برأيكم", "bait"), ("تابعونا وشاركوا", "follow"), ("شو هذا الحلو 🌟", "dialect"), ("🌟🌟🌟🌟 شكرا لك", "emoji"), ("أنا أحبكم", "person"), ("thanks a lot my friend", "Arabic"),
    ("الحرب مؤلمة", "sensitive"),
])
def test_reply_problems(text, frag):
    why = " | ".join(engage.reply_problems(text))
    assert frag.lower() in why.lower(), why


def test_clean_reply_and_duplicates():
    assert engage.reply_problems("شكرا لك 🌟 تعليقك أسعدنا") == []
    assert any("same text" in w for w in engage.reply_problems("شكرا لك 🌟 تعليقك أسعدنا", [engage.norm_ar("شكرا لك 🌟 تعليقك أسعدنا")]))


def test_every_template_passes_its_own_gates():
    lex = engage.load_lexicon(sw_fixtures.PROJECT)
    for kind in lex["openers"]:
        for i in range(60):
            text, _ = engage.compose(kind, lex, f"k{i}", i, "الرف")
            assert engage.reply_problems(text) == [], (kind, text)


def test_compose_rotates_and_avoids_the_last_opener():
    lex = engage.load_lexicon(sw_fixtures.PROJECT)
    texts = {engage.compose("praise", lex, "k", a)[0] for a in range(40)}
    assert len(texts) > 10
    ops = {engage.compose("praise", lex, f"k{i}", 0, "", last_opener="شكرا لك")[1] for i in range(40)}
    assert "شكرا لك" not in ops


# ------------------------------------------------------------------ the tick: dry, delays, send, caps
def test_dry_run_drafts_but_never_sends(repo):
    rows = [comment("instagram", "c1", "متى الحلقة القادمة؟", 2), comment("instagram", "c2", "ممل", 2), comment("instagram", "c3", "تابعني https://a.com", 2)]
    res, s = tick(repo, rows, t(3))
    assert res["mode"] == "DRY" and res["kinds"] == {"question": 1, "hostile": 1, "spam": 1} and res["drafted"] == 1
    assert s.calls == [] and not (repo / "work" / "engage" / "sent.jsonl").exists()
    d = [json.loads(x) for x in (repo / "work" / "engage" / "drafts.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(d) == 1 and d[0]["text"] and d[0]["status"] == "drafted"
    st = json.loads((repo / "work" / "engage" / "state.json").read_text(encoding="utf-8"))
    assert st["items"]["instagram:c2"]["status"] == "skip" and "hostile" in st["items"]["instagram:c2"]["reason"]


def test_reply_waits_for_its_delay_then_sends_once(repo):
    rows = [comment("instagram", "c1", "متى الحلقة القادمة؟", 2.99)]                       # written about one minute before the tick
    r1, s = tick(repo, rows, t(3), go=True)
    assert s.calls == [] and r1["sent_n"] == 0                       # the short human delay (2 to 8 min after the comment, R-474) has not passed
    st = json.loads((repo / "work" / "engage" / "state.json").read_text(encoding="utf-8"))
    nb = datetime.fromisoformat(st["items"]["instagram:c1"]["not_before"])
    assert t(2.99) + timedelta(minutes=2) <= nb <= t(2.99) + timedelta(minutes=8)
    r2, s2 = tick(repo, rows, t(3.2), go=True)
    assert len(s2.calls) == 1 and s2.calls[0][0] == "c1"
    sent = [json.loads(x) for x in (repo / "work" / "engage" / "sent.jsonl").read_text(encoding="utf-8").splitlines()]
    assert sent[0]["platform"] == "instagram" and sent[0]["item_id"] == "c1" and sent[0]["reply_id"] == "r1" and sent[0]["text"]
    r3, s3 = tick(repo, rows, t(5), go=True)
    assert s3.calls == [] and r3["sent_n"] == 0                      # idempotent: never a second reply to the same comment


def test_replies_go_under_the_top_level_comment_and_one_per_thread(repo):
    rows = [comment("instagram", "top", "قصة جميلة جدا", 2), comment("instagram", "r1", "متى الحلقة القادمة؟", 3, parent="top")]
    tick(repo, rows, t(4), go=True)
    r, s = tick(repo, rows, t(8), go=True)
    # 'top' is praise (may be varied away); r1 is a question: its target is the top-level comment
    assert all(c[0] == "top" for c in s.calls)
    r, s = tick(repo, rows, t(9), go=True)
    assert s.calls == []


def test_thread_answered_by_us_is_not_answered_again(repo):
    rows = [comment("instagram", "c1", "متى الحلقة؟", 2), comment("instagram", "o1", "سنخبركم قريبا", 2.2, parent="c1", own=True, sender="nj")]
    inbox.mark_replied(rows)
    res, s = tick(repo, rows, t(3))
    assert res["skipped"] == {"already answered (a reply of ours is newer)": 1} or "already answered" in " ".join(res["skipped"])


def test_new_question_in_an_answered_thread_gets_one_more_reply(repo):
    own = comment("instagram", "o1", "سنخبركم", 2.2, parent="c1", own=True, sender="nj")
    rows = [comment("instagram", "c1", "شكرا لكم", 2), own, comment("instagram", "q2", "ومتى تنزل الحلقة الجديدة؟", 3, parent="c1")]
    inbox.mark_replied(rows)
    res, _ = tick(repo, rows, t(4))
    st = json.loads((repo / "work" / "engage" / "state.json").read_text(encoding="utf-8"))["items"]
    assert st["instagram:q2"]["status"] == "drafted"
    rows.append(comment("instagram", "q3", "وهل هناك جزء ثان؟", 3.5, parent="c1", sender="userq2"))
    rows.append(comment("instagram", "o2", "نعم", 3.6, parent="c1", own=True, sender="nj"))
    inbox.mark_replied(rows)
    tick(repo, rows, t(5))
    st = json.loads((repo / "work" / "engage" / "state.json").read_text(encoding="utf-8"))["items"]
    assert st["instagram:q3"]["status"] == "skip"


def test_run_cap_per_platform(repo):
    rows = [comment("instagram", f"c{i}", "متى تنزل الحلقة القادمة؟", 2) for i in range(7)]
    r, s = tick(repo, rows, t(3), go=True)                           # older than the delay: sent on the same tick, up to the per-tick cap
    assert len(s.calls) == engage.RUN_CAP and r["sent_n"] == engage.RUN_CAP
    r, s = tick(repo, rows, t(3.5), go=True)
    assert len(s.calls) == 2


def test_day_cap_counts_what_was_sent_today(repo):
    rows = [comment("youtube", f"c{i}", "متى تنزل الحلقة القادمة؟", 2) for i in range(4)]
    for i in range(engage.DAY_CAP["youtube"]):
        engage.append_jsonl(repo / "work" / "engage" / "sent.jsonl", {"at": t(6).isoformat(), "platform": "youtube", "channel": "youtube", "episode": "E01", "thread": f"o{i}", "text": f"x{i}"})
    tick(repo, rows, t(7), go=True)
    r, s = tick(repo, rows, t(8), go=True)
    assert s.calls == []


def test_quiet_hours_push_the_reply_to_the_morning(repo):
    rows = [comment("instagram", "c1", "متى تنزل الحلقة القادمة؟", 9.9)]            # seen at 22:00Z = 01:00 Amman
    tick(repo, rows, t(10.0), go=True)
    st = json.loads((repo / "work" / "engage" / "state.json").read_text(encoding="utf-8"))["items"]["instagram:c1"]
    nb = datetime.fromisoformat(st["not_before"]).astimezone(engage.AMMAN)
    assert nb.time() >= engage.QUIET[1]
    r, s = tick(repo, rows, t(10.5), go=True)
    assert s.calls == []
    r, s = tick(repo, rows, t(19), go=True)                                       # 10:00 Amman next day, still inside the 72 h window
    assert len(s.calls) == 1


def test_window_over_expires_pending_replies(repo):
    rows = [comment("instagram", "c1", "متى تنزل الحلقة القادمة؟", 70)]
    tick(repo, rows, t(71))                                          # dry: drafted, nothing sent
    r, s = tick(repo, rows, t(73), go=True)
    assert s.calls == []
    assert json.loads((repo / "work" / "engage" / "state.json").read_text(encoding="utf-8"))["items"]["instagram:c1"]["status"] == "expired"


def test_direct_messages_only_questions_and_thanks_inside_24h(repo):
    rows = [dm("instagram", "d1", "متى تنزل الحلقة القادمة؟", 2), dm("instagram", "d2", "ممل", 2, sender="u8"), dm("instagram", "d3", "ما رأيكم بالانتخابات", 2, sender="u7")]
    res, _ = tick(repo, rows, t(3))
    st = json.loads((repo / "work" / "engage" / "state.json").read_text(encoding="utf-8"))["items"]
    assert st["instagram:d1"]["status"] == "drafted" and st["instagram:d1"]["dm"] is True
    assert st["instagram:d2"]["status"] == "skip" and "sensitive" in st["instagram:d3"]["reason"]
    old = [dm("instagram", "d4", "متى الحلقة؟", 2)]
    res, _ = tick(repo, old, t(30))
    assert json.loads((repo / "work" / "engage" / "state.json").read_text(encoding="utf-8"))["items"]["instagram:d4"]["reason"] == "outside the 24 h messaging window"


def test_board_flow_comments_are_not_answered_twice(repo):
    (repo / "board" / "data" / "replies.json").write_text(json.dumps({"replies": [{"id": "c1", "status": "approved"}]}), encoding="utf-8")
    res, _ = tick(repo, [comment("instagram", "c1", "متى الحلقة؟", 2)], t(3))
    assert "the board flow handles it" in res["skipped"]


def test_a_failed_send_halts_the_platform_and_hard_codes_for_a_day(repo):
    rows = [comment("instagram", f"c{i}", "متى تنزل الحلقة القادمة؟", 2) for i in range(2)]
    tick(repo, rows, t(3))
    r, s = tick(repo, rows, t(8), go=True, sender=Sender(fail="FAIL [IG-HTTP] HTTP 400 ... (#368) temporarily blocked"))
    assert r["failed"] and "instagram" in r["halted"] and len(r["failed"]) == 1          # the second item is not tried once halted
    halt = json.loads((repo / "work" / "engage" / "state.json").read_text(encoding="utf-8"))["halt"]["instagram"]
    assert datetime.fromisoformat(halt) == t(8) + timedelta(hours=engage.HALT_HARD_H)
    r, s = tick(repo, rows, t(9), go=True)
    assert s.calls == [] and "instagram" in r["halted"]


def test_other_platforms_keep_working_when_one_is_halted(repo):
    rows = [comment("instagram", "c1", "متى تنزل الحلقة القادمة؟", 2), comment("youtube", "y1", "متى تنزل الحلقة القادمة؟", 2)]
    tick(repo, rows, t(3))
    state = json.loads((repo / "work" / "engage" / "state.json").read_text(encoding="utf-8"))
    state["halt"]["instagram"] = (t(40)).isoformat()
    (repo / "work" / "engage" / "state.json").write_text(json.dumps(state), encoding="utf-8")
    r, s = tick(repo, rows, t(8), go=True)
    assert [c[0] for c in s.calls] == ["y1"]


def test_summary_files_for_learn_and_board(repo):
    tick(repo, [comment("instagram", "c1", "متى الحلقة؟", 2), comment("instagram", "c2", "ممل", 2)], t(3))
    s = json.loads((repo / "work" / "engage" / "summary-E01.json").read_text(encoding="utf-8"))
    assert s["status"] == "open" and s["items_by_kind"] == {"question": 1, "hostile": 1} and s["replies_sent"] == 0
    assert learn.engagement_for(repo, "E01")["items_by_kind"] == {"question": 1, "hostile": 1}
    assert learn.engagement_for(repo, "E99")["status"] == "not available"
    b = json.loads((repo / "board" / "data" / "engage.json").read_text(encoding="utf-8"))
    assert b["episodes"][0]["episode"] == "E01" and len(b["drafts"]) == 1
    closed, _ = tick(repo, [], t(80))
    assert json.loads((repo / "work" / "engage" / "summary-E01.json").read_text(encoding="utf-8"))["status"] == "closed"


def test_credentials_never_reach_the_files(repo):
    s = Sender(fail=f"FAIL [IG-HTTP] token {SECRET} rejected")
    tick(repo, [comment("instagram", "c1", "متى الحلقة القادمة؟", 2)], t(3), go=True)
    tick(repo, [comment("instagram", "c1", "متى الحلقة القادمة؟", 2)], t(8), go=True, sender=s)
    for p in (repo / "work" / "engage").glob("*"):
        assert SECRET not in p.read_text(encoding="utf-8")


def test_youtube_viewer_text_is_not_stored(repo):
    tick(repo, [comment("youtube", "y1", "متى تنزل الحلقة القادمة؟", 2), comment("instagram", "c1", "متى تنزل الحلقة القادمة؟", 2)], t(3))
    st = json.loads((repo / "work" / "engage" / "state.json").read_text(encoding="utf-8"))["items"]
    assert "excerpt" not in st["youtube:y1"] and st["instagram:c1"]["excerpt"].startswith("متى")


# ------------------------------------------------------------------ drafting with the model
def test_model_drafts_are_used_when_clean_and_gated(repo):
    def llm(prompt, name, tools, effort):
        assert tools == "NONE" and "untrusted" in prompt
        return {"rc": 0, "text": json.dumps({"instagram:c1": "سؤال حلو 🧳 الجواب في الحلقة القادمة", "instagram:c2": "شكرا لك https://spam.com"})}
    rows = [comment("instagram", "c1", "متى الحلقة القادمة؟", 2), comment("instagram", "c2", "متى الحلقة القادمة يا ترى؟", 2)]
    res, _ = tick(repo, rows, t(3), use_llm=True, llm=llm)
    st = json.loads((repo / "work" / "engage" / "state.json").read_text(encoding="utf-8"))["items"]
    assert res["llm"] and st["instagram:c1"]["how"] == "llm" and st["instagram:c1"]["reply"].startswith("سؤال حلو")
    assert st["instagram:c2"]["how"] == "template"                 # the model's text had a link: the gate refused it, the bank took over


def test_model_failure_falls_back_to_templates(repo):
    res, _ = tick(repo, [comment("instagram", "c1", "متى الحلقة القادمة؟", 2)], t(3), use_llm=True, llm=lambda *a, **k: {"rc": 1, "text": ""})
    st = json.loads((repo / "work" / "engage" / "state.json").read_text(encoding="utf-8"))["items"]["instagram:c1"]
    assert not res["llm"] and st["how"] == "template" and st["status"] == "drafted"


# ------------------------------------------------------------------ gifs and lexicon
def test_gif_only_from_our_own_list_and_only_on_facebook(repo):
    item = {"key": "facebook:c1"}
    assert engage.own_gif(repo, "joke", "facebook", item) is None
    (repo / "data" / "engage").mkdir(parents=True)
    (repo / "data" / "engage" / "gifs.json").write_text(json.dumps({"gifs": [{"url": "https://ours/x.gif", "moods": ["joke"], "licence": "own art"}, {"url": "https://t/y.gif", "moods": ["joke"]}]}), encoding="utf-8")
    assert engage.own_gif(repo, "joke", "facebook", item) == "https://ours/x.gif"      # the entry without a licence row is never used
    assert engage.own_gif(repo, "joke", "instagram", item) is None and engage.own_gif(repo, "praise", "facebook", item) is None


def test_lexicon_refresh_promotes_only_safe_shared_emoji_and_words(repo):
    rows = []
    for i in range(6):
        rows.append(comment("instagram", f"a{i}", "قصة 😂 رهيبة", 2 + i * 20 % 40, sender=f"s{i}"))
        rows.append(comment("instagram", f"b{i}", "كده 🖕 حلو", 2, sender=f"s{i}"))
    rows += [comment("instagram", "z", "رهيبة 😂", 30, sender="s0")]
    res = engage.refresh_lexicon(repo, t(48), rows=rows)
    lex = json.loads((repo / "data" / "engage" / "lexicon.json").read_text(encoding="utf-8"))
    texts = {(a["type"], a["text"]) for a in lex["auto"]}
    assert ("emoji", "😂") in texts and ("emoji", "🖕") not in texts
    assert not any(a["text"] == "كده" for a in lex["auto"])                      # dialect word: never promoted
    assert res["written"] is True


def test_lexicon_auto_entries_expire_and_trends_are_never_used_in_drafts(repo):
    lex = engage.load_lexicon(repo)
    lex = json.loads(json.dumps(lex))
    lex["auto"] = [{"type": "emoji", "text": "🎉", "senders": 9, "last": "2026-01-01", "first": "2026-01-01"}]
    (repo / "data" / "engage").mkdir(parents=True)
    (repo / "data" / "engage" / "lexicon.json").write_text(json.dumps(lex), encoding="utf-8")
    engage.refresh_lexicon(repo, t(48), rows=[], trends=lambda r: [f"عنوان {r}", "الانتخابات الجديدة"], use_trends=True)
    out = json.loads((repo / "data" / "engage" / "lexicon.json").read_text(encoding="utf-8"))
    assert out["auto"] == [] and all("الانتخابات" not in x["title"] for x in out["trending"]) and out["trending"]
    lex2 = engage.load_lexicon(repo)
    for i in range(50):
        assert all(tr["title"] not in engage.compose("praise", lex2, f"k{i}", 0)[0] for tr in lex2["trending"])


def test_ig_board_does_not_draft_a_comment_engage_already_answered(repo):
    import ig_board
    engage.append_jsonl(repo / "work" / "engage" / "sent.jsonl", {"at": t(1).isoformat(), "platform": "instagram", "channel": "instagram", "item_id": "c1", "thread": "c1", "text": "x"})
    assert "c1" in ig_board.engage_sent_ids(repo)
    engage.append_jsonl(repo / "work" / "engage" / "sent.jsonl", {"at": t(1).isoformat(), "platform": "instagram", "channel": "dm_instagram", "item_id": "d1", "thread": "conv", "text": "y"})
    assert "d1" not in ig_board.engage_sent_ids(repo)


def test_demo_runs_offline():
    out = engage.demo()
    assert {d["kind"] for d in out} >= {"joke", "question", "praise", "idea", "hostile", "spam", "minor", "sensitive"}
    assert all(d["reply"] is None or d["problems"] == [] for d in out)


# ------------------------------------------------------------------ decisions log, Instagram permission (2026-10-26 live finding)
def decisions(repo):
    p = repo / "work" / "engage" / "decisions.jsonl"
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


def test_every_verdict_is_logged_with_a_reason_and_no_viewer_text(repo):
    rows = [comment("instagram", "c1", "متى الحلقة القادمة؟", 2), comment("instagram", "c2", "ممل جدا", 2),
            dm("instagram", "d_early", "مرحبا كيف الحال؟", -5),                                  # five hours before the post: R-474 still answers it (24 h window)
            comment("instagram", "c_other", "رائع", 2, thread="OTHERMEDIA")]
    tick(repo, rows, t(3))
    dec = {d["key"]: d for d in decisions(repo)}
    assert dec["instagram:c2"]["status"] == "skip" and "hostile" in dec["instagram:c2"]["reason"]
    assert dec["instagram:d_early"]["status"] in ("drafted", "due", "waiting")        # R-474: matched to the first post after it and answered inside its own 24 h window
    assert dec["instagram:c_other"]["status"] == "out_of_window" and "no episode window" in dec["instagram:c_other"]["reason"]
    assert dec["instagram:c1"]["status"] in ("drafted", "due", "waiting")
    blob = (repo / "work" / "engage" / "decisions.jsonl").read_text(encoding="utf-8")
    assert "متى الحلقة" not in blob and "ممل" not in blob
    n = len(decisions(repo))
    tick(repo, rows, t(3))
    assert len(decisions(repo)) == n or all(d["key"] != "instagram:c2" for d in decisions(repo)[n:])     # an unchanged verdict is not logged twice
    board = json.loads((repo / "board" / "data" / "engage.json").read_text(encoding="utf-8"))
    assert board["decisions"] and board["decision_counts"]


def test_waiting_reasons_are_logged_once(repo):
    rows = [comment("instagram", "c1", "متى الحلقة القادمة؟", 2.99)]
    tick(repo, rows, t(3), go=True)
    tick(repo, rows, t(3) + timedelta(seconds=30), go=True)
    w = [d for d in decisions(repo) if d["key"] == "instagram:c1" and d["status"] == "waiting"]
    assert len(w) == 1 and "delay" in w[0]["reason"]


def test_quiet_hours_reason(repo):
    rows = [comment("instagram", "c1", "متى الحلقة القادمة؟", 2)]
    tick(repo, rows, t(3))
    quiet_now = datetime(2026, 10, 26, 22, 30, tzinfo=timezone.utc)          # 01:30 Amman
    tick(repo, rows, quiet_now, go=True)
    assert any("quiet hours" in d["reason"] for d in decisions(repo))


PERM = 'FAIL [IG-HTTP] HTTP 400 POST https://graph.facebook.com/v26.0/c1/replies: {"error":{"message":"(#200) Requires instagram_manage_comments permission","type":"OAuthException","code":200}}'


def test_instagram_comment_reply_without_permission_is_recorded_once_and_the_draft_is_kept(repo):
    rows = [comment("instagram", "c1", "متى تنزل الحلقة القادمة؟", 2), comment("instagram", "c9", "متى تنزل الحلقة الثانية؟", 2),
            comment("youtube", "y1", "متى تنزل الحلقة القادمة؟", 2), dm("instagram", "d1", "هل الحلقة القادمة غدا؟", 2.5, sender="u77")]
    tick(repo, rows, t(3))
    ok = Sender()
    attempts = []

    class Perm(Sender):
        def __call__(self, item, text, gif, env):
            attempts.append(item["key"])
            if not item["dm"]:
                raise SystemExit(PERM)
            return super().__call__(item, text, gif, env)
    bad = Perm()

    def go(now, ig_sender):
        return engage.run(go=True, root=repo, now=now, harvest=lambda s: 0, senders={"instagram": ig_sender, "facebook": ok, "youtube": ok}, env={"IG_ACCESS_TOKEN": SECRET},
                          use_llm=False, do_lexicon=False, rows=rows, sleep=lambda x: None)
    r = go(t(5), bad)
    st = json.loads((repo / "work" / "engage" / "state.json").read_text(encoding="utf-8"))
    assert r["needs_permission"] == engage.NEEDS_NOTE and not r["failed"] and "instagram" not in r["halted"]
    assert st["failures"].get("instagram", 0) == 0 and "instagram" not in st["halt"]
    assert st["needs"]["instagram"]["note"] == engage.NEEDS_NOTE
    assert [a for a in attempts if not a.startswith("instagram:d")] and len([a for a in attempts if a.startswith("instagram:c")]) == 1      # one probe, not one per draft
    assert {v["status"] for k, v in st["items"].items() if k.startswith("instagram:c")} == {"drafted"}       # drafts stay on the board
    assert any(c[0] == "y1" for c in ok.calls)                                  # YouTube unaffected
    assert st["items"]["instagram:d1"]["status"] == "sent"                      # the Instagram DM channel is unaffected
    drafts = [json.loads(x) for x in (repo / "work" / "engage" / "drafts.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(d["blocked_by"] == engage.NEEDS_NOTE for d in drafts)
    # within 6 h: no new attempt, no new note
    probes = []

    class Probe(Sender):
        def __call__(self, item, text, gif, env):
            probes.append(item["key"])
            return super().__call__(item, text, gif, env)
    go(t(6), Probe())
    assert probes == [k for k in probes if k.startswith("instagram:d")] and len([d for d in decisions(repo) if d["status"] == "needs_permission"]) == 1
    # after 6 h: exactly one probe; it succeeds -> the permission note clears
    probes.clear()
    go(t(24), Probe())
    assert len([p for p in probes if p.startswith("instagram:c")]) >= 1      # the first probe worked, so the rest of the drafts follow in the same tick
    st = json.loads((repo / "work" / "engage" / "state.json").read_text(encoding="utf-8"))
    assert "instagram" not in st["needs"] and any(d["status"] == "permission_ok" for d in decisions(repo))


def test_instagram_dm_is_not_blocked_by_the_comment_permission(repo):
    rows = [comment("instagram", "c1", "متى تنزل الحلقة القادمة؟", 2), dm("instagram", "d1", "هل الحلقة القادمة غدا؟", 2.5, sender="u77")]
    tick(repo, rows, t(3))
    calls = []

    def ig_sender(item, text, gif, env):
        calls.append(item["key"])
        if not item["dm"]:
            raise SystemExit(PERM)
        return "m1"
    engage.run(go=True, root=repo, now=t(5), harvest=lambda s: 0, senders={"instagram": ig_sender, "facebook": Sender(), "youtube": Sender()}, env={"IG_ACCESS_TOKEN": SECRET},
               use_llm=False, do_lexicon=False, rows=rows, sleep=lambda x: None)
    assert "instagram:d1" in calls                                        # the DM still goes out, whichever order they were tried in
    st = json.loads((repo / "work" / "engage" / "state.json").read_text(encoding="utf-8"))
    assert st["items"]["instagram:d1"]["status"] == "sent" and st["items"]["instagram:c1"]["status"] == "drafted"


def test_our_own_sent_reply_with_a_hidden_author_is_not_answered(repo):
    rows = [comment("instagram", "top", "متى تنزل الحلقة القادمة؟", 2)]
    tick(repo, rows, t(3), go=True)
    tick(repo, rows, t(5), go=True)
    sent = [json.loads(x) for x in (repo / "work" / "engage" / "sent.jsonl").read_text(encoding="utf-8").splitlines()]
    mine = sent[0]["reply_id"]
    rows2 = rows + [comment("instagram", mine, "شكرا لك 🙏", 4.5, parent="top", sender="unknown")]       # harvested back with no author
    r, s = tick(repo, rows2, t(6), go=True)
    assert s.calls == [] and f"instagram:{mine}" not in json.loads((repo / "work" / "engage" / "state.json").read_text(encoding="utf-8"))["items"]


# ------------------------------------------------------------------ owner and own accounts (R-473)
def test_owner_comment_is_skipped_never_drafted_or_sent(repo):
    rows = [comment("instagram", "o3", "متى تنزل الحلقة القادمة؟", 2, sender="story_account"), comment("instagram", "o4", "great", 2, sender="@story_account")]
    r, s = tick(repo, rows, t(30), go=True)
    st = json.loads((repo / "work" / "engage" / "state.json").read_text(encoding="utf-8"))
    assert s.calls == [] and r["drafted"] == 0
    for k in ("instagram:o3", "instagram:o4"):
        assert st["items"][k]["status"] == "skip" and st["items"][k]["reason"] == engage.OWNER_REASON and "reply" not in st["items"][k]


def test_owner_item_already_drafted_in_state_is_not_sent(repo):
    rows = [comment("instagram", "c1", "متى تنزل الحلقة القادمة؟", 2, sender="someone")]
    tick(repo, rows, t(3))                                       # drafted under a name that was hidden then
    p = repo / "work" / "engage" / "state.json"
    st = json.loads(p.read_text(encoding="utf-8"))
    assert st["items"]["instagram:c1"]["status"] == "drafted"
    rows2 = [comment("instagram", "c1", "متى تنزل الحلقة القادمة؟", 2, sender="story_account")]      # the API now shows the author: our own account
    r, s = tick(repo, rows2, t(30), go=True)
    st = json.loads(p.read_text(encoding="utf-8"))
    assert s.calls == [] and st["items"]["instagram:c1"]["status"] == "skip" and "reply" not in st["items"]["instagram:c1"]
    assert not any(d["key"] == "instagram:c1" and d["status"] in ("sent", "due") for d in decisions(repo)[-1:])


def test_owner_by_from_id_of_our_account_is_skipped(repo):
    rows = [comment("instagram", "c1", "hello", 2, sender="unknown")]
    rows[0]["sender_id"] = "17841"
    r, s = tick(repo, rows, t(30), go=True, env={"IG_ACCESS_TOKEN": SECRET, "IG_USER_ID": "17841"})
    assert s.calls == []


def test_owner_personal_account_gets_replies_like_any_viewer(repo):
    rows = [comment("instagram", "c1", "متى تنزل الحلقة القادمة؟", 2, sender="owner_account")]
    r, s = tick(repo, rows, t(3))
    assert r["drafted"] == 1
    r, s = tick(repo, rows, t(30), go=True)
    assert len(s.calls) == 1


def test_normal_user_is_still_drafted_and_sent(repo):
    rows = [comment("instagram", "c1", "متى تنزل الحلقة القادمة؟", 2, sender="some_viewer")]
    r, s = tick(repo, rows, t(3))
    assert r["drafted"] == 1
    r, s = tick(repo, rows, t(30), go=True)
    assert len(s.calls) == 1


def test_nationality_question_is_not_sensitive():
    # «جنسياتها» (their nationalities) once matched the «جنسي» (sexual) pattern: a real viewer question went unanswered (2026-10-27)
    n = engage.norm_ar("ياخي احكيلنا الشخصيات هاي شو جنسياتها") if hasattr(engage, "norm_ar") else "ياخي احكيلنا الشخصيات هاي شو جنسياتها"
    assert not engage.SENSITIVE_A.search(n)
    assert engage.SENSITIVE_A.search("محتوى جنسي")


def test_run_lock_keeps_two_go_runs_apart(tmp_path):
    # the hourly task and the watcher's tick both run `engage.py run --go`: the second one must wait (R-481)
    first = engage.run_lock(tmp_path)
    assert first is not None and first.exists()
    assert engage.run_lock(tmp_path) is None
    first.unlink()
    again = engage.run_lock(tmp_path)
    assert again is not None
    old = time.time() - engage.RUN_LOCK_STALE_S - 5
    os.utime(again, (old, old))
    assert engage.run_lock(tmp_path) is not None            # a dead run's lock is cleared
