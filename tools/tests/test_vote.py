"""Audience vote tests: deterministic, fixtures only, no network."""
import json

import pytest

import vote

CHOICES = [{"id": "1", "text_ar": "١  على الرّفِّ الذي بلا رقم"}, {"id": "2", "text_ar": "٢  في يدِ هُدى، لا تُفارقُها"}]


def cm(i, text, user="u"):
    return {"id": str(i), "text": text, "username": user}


def tally(texts, own=("storywrap",), min_votes=5):
    return vote.tally_comments([cm(i, t, f"u{i}") if not isinstance(t, tuple) else cm(i, *t) for i, t in enumerate(texts)], CHOICES, set(own), min_votes)


@pytest.mark.parametrize("text,want", [
    ("1", {"1"}), ("2", {"2"}), ("١", {"1"}), ("٢", {"2"}), ("۱", {"1"}), ("۲", {"2"}),
    ("1️⃣", {"1"}), ("اخترت 2 طبعا", {"2"}), ("#١", {"1"}),
    ("على الرف", {"1"}), ("الرَّفّ اللي بلا رقم", {"1"}), ("رقم", {"1"}),
    ("في يد هدى", {"2"}), ("تفارقها", {"2"}), ("تفارقه", {"2"}),
    ("هُدَى", {"2"}), ("الهدى", {"2"}), ("الرفّ", {"1"}), ("الرفف", {"1"}),
    ("الأول", {"1"}), ("الثاني", {"2"}), ("اثنين", {"2"}), ("one", {"1"}), ("two", {"2"}),
    ("1 و 2", {"1", "2"}), ("١ أو ٢", {"1", "2"}), ("على الرف وفي يد هدى", {"1", "2"}),
    ("حلقة جميلة", set()), ("", set()), ("12", set()), ("🔥🔥🔥", set()), ("on the shelf", set()),
])
def test_classify(text, want):
    assert vote.classify(text, CHOICES) == want


def test_shared_words_are_not_votes():
    ch = [{"id": "1", "text_ar": "١ تفتح الباب الكبير"}, {"id": "2", "text_ar": "٢ تفتح النافذة الصغيرة"}]
    assert vote.classify("تفتح", ch) == set()
    assert vote.classify("النافذة", ch) == {"2"}


def test_arabic_and_western_digits_tally_together():
    r = tally(["1", "١", "2", "٢", "٢", "حلقة حلوة"])
    assert r["counts"] == {"1": 2, "2": 3} and r["neither"] == 1 and r["counted"] == 5
    assert r["winner"] == "2" and r["margin"] == 1 and r["status"] == "AUDIENCE" and not r["needs_showrunner"]


def test_both_and_neither_do_not_count():
    r = tally(["1 و 2", "٢ أو ١", "ما فهمت", "رائع", "1", "1", "1", "1", "1"])
    assert r["both"] == 2 and r["neither"] == 2 and r["counts"] == {"1": 5, "2": 0}


def test_own_comments_excluded_case_insensitive_and_at():
    r = tally([("1", "StoryWrap"), ("2", "@storywrap"), ("2", "fan")], own=("storywrap",), min_votes=1)
    assert r["excluded_own"] == 2 and r["counts"] == {"1": 0, "2": 1}


def test_every_comment_counts_including_replies_but_one_vote_per_account():
    r = vote.tally_comments([{"id": "a", "text": "1", "username": "x"}, {"id": "b", "text": "1", "username": "y", "parent_id": "a"}], CHOICES, set(), 1)
    assert r["counts"]["1"] == 2
    r = vote.tally_comments([{"id": "a", "text": "1", "username": "x"}, {"id": "b", "text": "1", "username": "x", "parent_id": "a"}], CHOICES, set(), 1)
    assert r["counts"]["1"] == 1 and r["duplicates_collapsed"] == 1


def test_tie_goes_to_showrunner():
    r = tally(["1", "1", "1", "2", "2", "2"])
    assert r["tie"] and r["winner"] is None and r["status"] == "SHOWRUNNER_TIE" and r["needs_showrunner"]


def test_near_empty_goes_to_showrunner():
    r = tally(["1", "1", "2"])
    assert r["near_empty"] and r["winner"] is None and r["status"] == "SHOWRUNNER_LOW_VOTES" and r["leader"] == "1"
    z = tally([])
    assert z["counted"] == 0 and z["leader"] is None and z["tie"]


def test_sample_is_capped_and_short():
    r = tally(["1 " + "x" * 400] * 9)
    assert len(r["sample"]["1"]) == vote.SAMPLE_PER_CHOICE and len(r["sample"]["1"][0]["text"]) <= 140


def make_repo(tmp_path, comments, outline=True):
    ep = tmp_path / "bible/series/s/episodes/E01"
    ep.mkdir(parents=True)
    (ep / "shotlist.json").write_text(json.dumps({"end_card": {"choices": CHOICES}}, ensure_ascii=False), encoding="utf-8")
    if outline:
        (ep / "outline.md").write_text("\n".join(["| Option | Gloss | Where it leads |", "|---|---|---|", "| ١ على الرّفِّ | shelf | E08 paid shelf |", "| ٢ في يدِ هُدى | hand | E05 the watch |"]) + "\n", encoding="utf-8")
    w = tmp_path / "work/episodes/E01"
    w.mkdir(parents=True)
    (w / "comments.json").write_text(json.dumps({"comments": comments, "own_usernames": ["storywrap"]}), encoding="utf-8")
    (tmp_path / "catalogue/characters/hero").mkdir(parents=True)
    (tmp_path / "reference/mix-v5").mkdir(parents=True)
    return tmp_path, w


def test_tally_and_next_write_files(tmp_path):
    repo, w = make_repo(tmp_path, [cm(i, "٢", f"u{i}") for i in range(6)] + [cm(9, "1", "u9"), cm(10, "2", "storywrap")])
    d = vote.cmd_tally("E01", repo)
    assert d["winner"] == "2" and d["counts"] == {"1": 1, "2": 6} and (w / "decision.json").is_file()
    txt = vote.cmd_next("E01", repo).read_text(encoding="utf-8")
    assert "Winning branch: choice 2" in txt and "E05 the watch" in txt and "PARKED" in txt
    assert "hero" in txt and "mix-v5" in txt and "Reuse first" in txt and "E02" in txt
    parked = repo / "bible/ideas/parked-E01-choice-1.md"
    assert parked.is_file() and "E08 paid shelf" in parked.read_text(encoding="utf-8")


def test_next_on_tie_demands_a_pick_then_uses_it(tmp_path):
    repo, w = make_repo(tmp_path, [cm(i, "1") for i in range(3)] + [cm(i + 10, "2") for i in range(3)])
    vote.cmd_tally("E01", repo)
    txt = vote.cmd_next("E01", repo).read_text(encoding="utf-8")
    assert "DECISION NEEDED FIRST" in txt and not (repo / "bible/ideas/parked-E01-choice-1.md").exists()
    d = json.loads((w / "decision.json").read_text(encoding="utf-8"))
    d["showrunner_pick"] = {"id": "1", "reason_ar": "الأقوى حكايةً"}
    (w / "decision.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    vote.cmd_tally("E01", repo)
    txt = vote.cmd_next("E01", repo).read_text(encoding="utf-8")
    assert "Winning branch: choice 1" in txt and "الأقوى حكايةً" in txt and (repo / "bible/ideas/parked-E01-choice-2.md").is_file()


def test_tally_needs_comments(tmp_path):
    repo, w = make_repo(tmp_path, [])
    (w / "comments.json").unlink()
    with pytest.raises(SystemExit):
        vote.cmd_tally("E01", repo)


def test_next_id():
    assert vote.next_id("E01") == "E02" and vote.next_id("E09") == "E10"



# ---------------------------------------------------------------- C13 (2026-10-25): the choice is a phrase people write in their own words
PHRASES = [{"id": "1", "text_ar": "الرف بلا رقم", "variants": ["على الرف", "الرف الفارغ"]},
           {"id": "2", "text_ar": "مع هدى", "variants": ["عند هدى", "تبقى معها"]}]


def tally_p(texts, min_votes=1):
    return vote.tally_comments([cm(i, t, f"u{i}") for i, t in enumerate(texts)], PHRASES, {"storywrap"}, min_votes)


@pytest.mark.parametrize("text,want,via", [
    ("الرف بلا رقم", {"1"}, "phrase"), ("«الرف بلا رقم»", {"1"}, "phrase"), ("على الرف", {"1"}, "phrase"), ("بالرف الفارغ", {"1"}, "phrase"),
    ("الرف", {"1"}, "words"), ("مع هدى", {"2"}, "phrase"), ("عند هدى", {"2"}, "phrase"), ("تبقى معها", {"2"}, "phrase"), ("هدى", {"2"}, "words"),
    ("1", {"1"}, "digit"), ("٢", {"2"}, "digit"),
    ("حلقة جميلة", set(), None), ("الرف وهدى", {"1", "2"}, None),
])
def test_votes_are_counted_from_the_wording(text, want, via):
    hv = vote.classify_via(text, PHRASES)
    assert set(hv) == want
    if via:
        assert hv[next(iter(want))] == via


def test_tally_reports_how_each_vote_was_recognised():
    r = tally_p(["الرف بلا رقم", "على الرف", "الرف", "مع هدى", "1", "هدى"])
    assert r["counts"] == {"1": 4, "2": 2} and r["via"]["1"] == {"phrase": 2, "words": 1, "digit": 1} and r["via"]["2"] == {"phrase": 1, "words": 1, "digit": 0}


def test_ideas_are_collected_for_the_next_writer_brief():
    r = tally_p(["الرف", "مع هدى", "أتمنى أن نرى جدتها تفتح الصندوق في الحلقة القادمة", "مع هدى وأريد أن أعرف سر المفتاح القديم", "أتمنى أن نرى جدتها تفتح الصندوق في الحلقة القادمة", "رائع"])
    texts = [i["text"] for i in r["ideas"]]
    assert r["idea_count"] == 2 and len(set(texts)) == 2                      # the repeat counts once; a bare choice or "رائع" is a vote or nothing, not an idea
    assert r["ideas"][1]["names"] == ["2"] and r["ideas"][0]["names"] == []
    assert r["counts"]["2"] == 2                                              # the idea that also names the choice still votes


def test_load_choices_reads_the_calm_plan_and_its_variants(tmp_path):
    (tmp_path / "calm-plan.json").write_text(json.dumps({"choice": {"choice1": "الرف بلا رقم", "choice2": "مع هدى", "variants": {"1": ["على الرف"], "2": ["عند هدى"]}}}, ensure_ascii=False), encoding="utf-8")
    ch = vote.load_choices(tmp_path)
    assert [c["text_ar"] for c in ch] == ["الرف بلا رقم", "مع هدى"] and ch[0]["variants"] == ["على الرف"]


def test_brief_carries_the_ideas_and_the_new_comment_rule(tmp_path):
    ep = tmp_path / "bible/series/s/episodes/E01"
    ep.mkdir(parents=True)
    (ep / "calm-plan.json").write_text(json.dumps({"choice": {"choice1": "الرف بلا رقم", "choice2": "مع هدى", "variants": {"1": ["على الرف"], "2": ["عند هدى"]}}}, ensure_ascii=False), encoding="utf-8")
    (ep / "outline.md").write_text("| Option | Gloss | Where it leads |\n|---|---|---|\n| الرف بلا رقم | shelf | E08 |\n| مع هدى | hand | E05 |\n", encoding="utf-8")
    w = tmp_path / "work/episodes/E01"
    w.mkdir(parents=True)
    (w / "comments.json").write_text(json.dumps({"comments": [cm(i, "على الرف", f"u{i}") for i in range(6)] + [cm(9, "أتمنى أن نرى جدتها تفتح الصندوق قريبا", "z")], "own_usernames": []}, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "catalogue/characters/hero").mkdir(parents=True)
    (tmp_path / "reference/mix-v5").mkdir(parents=True)
    d = vote.cmd_tally("E01", tmp_path)
    assert d["winner"] == "1" and d["idea_count"] == 1
    txt = vote.cmd_next("E01", tmp_path).read_text(encoding="utf-8")
    assert "Ideas from the audience" in txt and "جدتها تفتح الصندوق" in txt and "Recognised by" in txt and "Never \"comment 1 or 2\"" in txt
