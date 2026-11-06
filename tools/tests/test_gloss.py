# -*- coding: utf-8 -*-
"""Foreign-word glossary (owner, 2026-10-25, CLAUDE.md "Gloss foreign words"): tools/gloss.py, the series glossary file, the caption plates and CAP-FOREIGN-GLOSS.
No browser, no model, no network."""
import json
from pathlib import Path

import calm_compose as cc
import gloss as G
import sw_fixtures
import qg_checks as qc

REPO = Path(__file__).resolve().parents[2]
SERIES = sw_fixtures.SERIES
ENTRIES = json.loads((SERIES / "glossary.json").read_text(encoding="utf-8"))["entries"]


def test_the_series_glossary_is_valid_and_comes_from_the_bibles():
    assert G.check_glossary(ENTRIES, SERIES) == []
    for ch in sorted(p.name for p in (SERIES / "characters").iterdir() if p.is_dir()):
        assert any(e["character"] == ch for e in ENTRIES), f"{ch} has no glossary word"          # every character bible's signature words are in


def test_glossary_file_faults_are_each_caught():
    base = {"word": "شيكامو", "language": "Swahili", "meaning_ar": "تحية احترام للكبار", "character": "hero"}
    assert G.check_glossary([base], SERIES) == []
    assert any("tashkeel" in x for x in G.check_glossary([{**base, "meaning_ar": "تَحِيَّة"}]))
    assert any("Latin" in x for x in G.check_glossary([{**base, "meaning_ar": "greeting"}]))
    assert any("over 3 words" in x for x in G.check_glossary([{**base, "meaning_ar": "تحية احترام كبيرة للكبار جدا"}]))
    assert any("listed twice" in x for x in G.check_glossary([base, base]))
    assert any("not found in hero's bible" in x for x in G.check_glossary([{**base, "word": "ماكاروني"}], SERIES))
    assert any("empty" in x for x in G.check_glossary([{**base, "language": ""}]))


def test_matching_ignores_punctuation_hamza_and_scopes_by_speaker():
    words = "شيكامو، يا عم. ساعتك لم تعرف بعد.".split()
    gm = G.gloss_map(words, "hero", ENTRIES)
    assert list(gm) == [0] and gm[0]["meaning_ar"] == "تحية احترام للكبار"
    assert G.gloss_map(words, "narrator", ENTRIES).keys() == {0}          # the narrator may quote it
    assert G.gloss_map(words, "lead", ENTRIES) == {}                     # another character's word is not his
    assert G.gloss_map("اري يا صديقي".split(), "guide", ENTRIES).keys() == {0}      # أري written without hamza still matches
    assert G.gloss_map("بولي بولي".split(), "lead", ENTRIES).keys() == {1}          # the two-word phrase wins over Hero's single «بولي»
    assert G.gloss_map("بولي".split(), "lead", ENTRIES) == {}


def test_a_phrase_is_glossed_once_after_its_last_word():
    out = G.with_gloss("قال بور لو دوسييه ثم صمت".split(), "extra", ENTRIES)
    assert out == ["قال", "بور", "لو", "دوسييه", "(من أجل الملف)", "ثم", "صمت"]


def test_no_glossary_word_no_change():
    w = "الريح تفتح النافذة العالية".split()
    assert G.with_gloss(w, "narrator", ENTRIES) == w and G.with_gloss(w, "narrator", []) == w


def test_cap_foreign_gloss_fails_a_plate_without_the_meaning():
    lines = {"L1": {"speaker": "hero"}}
    f = G.check_captions([{"line": "L1", "text": "شيكامو يا عم"}], lines, ENTRIES)
    assert len(f) == 1 and f[0].startswith("CAP-FOREIGN-GLOSS") and "شيكامو" in f[0]
    assert G.check_captions([{"line": "L1", "text": "شيكامو (تحية احترام للكبار) يا عم"}], lines, ENTRIES) == []
    assert "glossary says" in G.check_captions([{"line": "L1", "text": "شيكامو (وداعا) يا عم"}], lines, ENTRIES)[0]
    assert G.check_captions([{"line": "L1", "text": "يا عم ساعتك"}], lines, ENTRIES) == []


def test_on_screen_strings_are_checked_too():
    assert G.check_text("اخترتم: شيكامو", None, ENTRIES, where="recap.line ")[0].startswith("CAP-FOREIGN-GLOSS recap.line")
    assert G.check_text("اخترتم: شيكامو (تحية احترام للكبار)", None, ENTRIES) == []


def test_gloss_is_not_a_caption_word():
    assert G.strip_gloss("شيكامو (تحية احترام للكبار) يا") == "شيكامو يا"
    c = {"captions": [{"line": "L1", "text": "شيكامو (تحية احترام للكبار)", "font_px_1080": 104, "start": 0.0, "end": 1.0}]}
    assert not any("more than" in x for x in qc.check_calm_declared({"lines": []}, c, {"choices": ["a", "b"]}, {}, 10.0))


def test_plate_html_puts_the_meaning_under_the_words_in_plate_and_reference():
    st = [{"line": "L1", "words": ["شيكامو،", "يا", "عم"], "active": 0, "gloss": ["تحية احترام للكبار"], "style": None},
          {"line": "L1", "words": ["ساعتك", "لم"], "active": 1, "gloss": [], "style": None}]
    h = cc.plate_html(st, [], with_ref=True)
    assert h.count('class="gl"') == 2 and "(تحية احترام للكبار)" in h              # plate c0 and its twin r0; none on the plate without a glossary word


def test_plan_validation_names_an_unglossed_word_on_screen(monkeypatch):
    monkeypatch.setattr(cc, "ROOT", sw_fixtures.PROJECT)       # the neutral fixture project, not a user's own series
    plan = {"series": "series", "episode": "E09", "day": 2, "place": "مكتب", "recap": {"line": "اخترتم:", "word": "شيكامو"},
            "scenes": [{"id": f"s{i}", "template": "push_in"} for i in range(1, 6)], "choice": {"question": "ماذا؟", "choice1": "ا", "choice2": "ب"}}
    script = {"series": "series", "lines": []}
    assert any(x.startswith("PLAN-GLOSS recap.word") for x in cc.validate_plan(plan, script))
    plan["recap"]["word"] = "شيكامو (تحية احترام للكبار)"
    assert not any(x.startswith("PLAN-GLOSS") for x in cc.validate_plan(plan, script))


# ---------------------------------------------------------------------------------------------- C11: every cultural word (owner, 2026-10-25)
GDATA = json.loads((SERIES / "glossary.json").read_text(encoding="utf-8"))


def test_the_dialect_and_spanish_and_surname_words_the_audit_found_are_glossary_entries():
    for w, ch in (("ويش", "hero"), ("واجد", "hero"), ("زين", "hero"), ("موانا حبيبي", "hero"), ("كاكا", "guide"), ("ديوب", "extra"), ("نو", "partner"), ("فويرا", "partner")):
        assert any(G.norm(e["word"]) == G.norm(w) and e["character"] == ch for e in ENTRIES), f"{w} ({ch}) is not in the glossary"
    assert "ديوب" not in GDATA["arabic_words"]          # a Wolof surname used as a greeting was hidden in the confirmed-Arabic list; it is glossed now
    assert G.check_glossary(ENTRIES, SERIES) == [] and G.audit_coverage(ENTRIES, SERIES, GDATA["arabic_words"]) == []


def test_a_dialect_word_of_a_speaker_gets_its_meaning_in_a_caption():
    words = "ويش؟ هذا خطي أنا.".split()
    assert list(G.gloss_map(words, "hero", ENTRIES)) == [0]
    assert G.check_text("ويش؟ هذا خطي أنا.", "hero", ENTRIES) and not G.check_text("ويش؟ (ماذا) هذا خطي أنا.", "hero", ENTRIES)


def test_plainly_foreign_letters_and_loanwords_fail_even_with_no_glossary_entry():
    lex = G.lexicon(sw_fixtures.PROJECT, "series")
    f = G.check_foreign("سمعت ok من هنا", None, lex["entries"], lex["foreign_keys"], "x ", lex["loanwords"])
    assert any("«ok»" in x for x in f)                                                        # Latin letters
    assert G.check_foreign("ڤيديو جديد", None, [], {}, "", {})                                  # a Persian/Urdu letter
    h = G.check_foreign("#المكتب #قصة #انيميشن", None, lex["entries"], lex["foreign_keys"], "post ", lex["loanwords"])
    assert len(h) == 1 and "انيميشن" in h[0] and "رسوم متحركة" in h[0]                       # the loanword is named with its Arabic replacement
    assert G.check_foreign("#المكتب #قصة #رسوم_متحركة", None, lex["entries"], lex["foreign_keys"], "post ", lex["loanwords"]) == []
    assert G.check_foreign("انيميشن (رسوم متحركة)", None, lex["entries"], lex["foreign_keys"], "", lex["loanwords"]) == []   # a bracket right after it counts as glossed


def test_a_bible_own_language_word_with_no_glossary_entry_is_named(tmp_path):
    sd = tmp_path / "series"
    (sd / "characters" / "x").mkdir(parents=True)
    (sd / "characters" / "x" / "bible.md").write_text("- voice_signature_words: «مابو» (mabo, hello: his greeting); «بس» (bas, enough)\n- next: y\n", encoding="utf-8")
    keys = G.bible_foreign_keys(sd, [], ["بس"])
    assert keys == {"مابو": ("x", "مابو")}                                                    # «بس» is confirmed Arabic, «مابو» is not
    f = G.check_foreign("قال مابو للجميع", None, [], keys, "line ")
    assert len(f) == 1 and "no glossary entry" in f[0] and "مابو" in f[0]
    assert G.check_foreign("قال مابو (مرحبا) للجميع", None, [], keys, "line ") == []
    assert G.bible_foreign_keys(sd, [{"word": "مابو", "character": "x"}], ["بس"]) == {}            # once it is a glossary word the other check owns it


def test_the_lexicon_leaves_the_episode_scripts_out_so_a_script_cannot_vouch_for_its_own_word(tmp_path):
    sd = tmp_path / "series"
    (sd / "episodes" / "E01").mkdir(parents=True)
    (sd / "worlds").mkdir()
    (sd / "episodes" / "E01" / "script.json").write_text(json.dumps({"lines": [{"text": "كلمةغريبة"}]}, ensure_ascii=False), encoding="utf-8")
    (sd / "worlds" / "w.md").write_text("ريح ومرفأ", encoding="utf-8")
    assert G.norm("كلمةغريبة") in G.series_corpus(sd)
    corpus = G.series_corpus(sd, skip_episodes=True)
    assert G.norm("كلمةغريبة") not in corpus and "ريح" in corpus
    assert G.review_words(["كلمةغريبة", "والريح"], corpus, [], [], []) == ["كلمةغريبة"]
    assert G.review_words(["كلمةغريبة"], corpus, [], ["كلمةغريبة"], []) == []                  # a reader confirmed it
    assert G.review_words(["أنطوان،"], corpus, [], [], ["أنطوان"]) == []                       # a listed name


def test_e01c_every_caption_and_post_caption_word_is_glossed_arabic_or_a_listed_name():
    import re
    s, pl = REPO / "work" / "rehearsal" / "E01C" / "script.json", REPO / "work" / "rehearsal" / "E01C" / "calm-plan.json"
    if not s.is_file() or not pl.is_file():
        return          # the rehearsal episode is git-ignored: nothing to audit on a fresh clone
    lex = G.lexicon(sw_fixtures.PROJECT, "series")
    script = json.loads(s.read_text(encoding="utf-8"))
    for l in script["lines"]:
        assert G.check_foreign(l["text"], l.get("speaker"), G.line_entries(l, lex["entries"]), lex["foreign_keys"], l["id"] + " ", lex["loanwords"]) == []
    plan = json.loads(pl.read_text(encoding="utf-8"))
    assert G.check_foreign(plan["post_caption"], None, lex["entries"], lex["foreign_keys"], "post ", lex["loanwords"]) == []
    words = [w for l in script["lines"] for w in l["text"].split()] + [w for w in re.split(r"[\s#_]+", plan["post_caption"]) if re.search("[ء-ي]", w)]
    audited = {"أنتم", "أمام", "النافذة", "التاريخ", "المنضدة", "ضيعتها", "مفتاحا", "تسمعون", "ترفعون", "تابعوا"}        # the E01C words read and confirmed on 2026-10-25
    assert not audited & set(G.review_words(words, lex["corpus"], lex["entries"], lex["arabic_ok"], lex["names"]))      # a later script revision may bring new words: they go to the review list, not here
