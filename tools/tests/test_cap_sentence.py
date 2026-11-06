# -*- coding: utf-8 -*-
"""Full-sentence captions with the spoken word highlighted (the owner 2026-10-25, C7) and the own-language word tags (C8).
No browser, no model, no network: widths come from a fake per-letter measure."""
import json
import math
import wave
from pathlib import Path

import calm_compose as cc
import cap_sentence as CS
import gloss as G
import sw_fixtures

REPO = Path(__file__).resolve().parents[2]
SERIES = sw_fixtures.SERIES
ENTRIES = json.loads((SERIES / "glossary.json").read_text(encoding="utf-8"))["entries"]

MAX_W = 900
width = lambda ws: sum(len(w) * 52 + 46 for w in ws)      # 52 px a letter, 46 px of margin a word: close to Thmanyah Black at 104 px


def test_a_very_short_sentence_takes_the_next_one_along_when_both_fit():
    ws = "أنا؟ ما ضيعتها بعد".split()
    assert [u["idx"] for u in CS.split_units(ws, width, MAX_W)] == [[0, 1, 2, 3]]          # «أنا؟» alone would flash by
    ws = "ثقيل. لا... ثقيلة.".split()
    assert [u["idx"] for u in CS.split_units(ws, width, MAX_W)] == [[0, 1, 2]]
    ws = "كلمة كلمة كلمة. كلمة كلمة كلمة.".split()                                          # two 3-word sentences: each stays its own unit
    assert [u["idx"] for u in CS.split_units(ws, width, MAX_W)] == [[0, 1, 2], [3, 4, 5]]
    ws = "كلمة؟ كلمةطويلةجدا كلمةطويلةجدا كلمةطويلةجدا كلمةطويلةجدا".split()                  # the next sentence is too wide to share: no merge
    assert [u["idx"] for u in CS.split_units(ws, width, MAX_W)][0] == [0]


def test_a_glossed_sentence_also_takes_company():
    ws = "أري! سبع ليالي رف حتى تضيع.".split()
    assert [u["idx"] for u in CS.split_units(ws, width, MAX_W, glossed={0})] == [[0, 1, 2, 3, 4, 5]]


def test_a_long_sentence_breaks_at_the_comma_and_every_unit_fits_two_lines():
    ws = "أنتم أمام النافذة العالية، والريح تفتحها. وحقيبة تسقط على المنضدة.".split()
    us = CS.split_units(ws, width, MAX_W)
    assert [i for u in us for i in u["idx"]] == list(range(len(ws)))           # every word once, in order
    for u in us:
        assert len(u["lines"]) <= 2 and len(u["idx"]) <= CS.UNIT_WORDS_MAX
        assert width([ws[i] for i in u["lines"][0]]) <= MAX_W
        first, last = ws[u["idx"][0] - 1] if u["idx"][0] else ".", ws[u["idx"][-1]]
        assert CS.ends_clause(first) and CS.ends_clause(last)                   # starts after a clause end, ends on one
    assert not any(u["split"] for u in us)


def test_a_clause_too_long_for_two_lines_is_cut_in_balanced_parts_and_flagged():
    ws = ["كلمةطويلةجدا"] * 7                                                   # 7 x (12 letters) cannot fit two 900 px lines
    us = CS.split_units(ws, width, MAX_W)
    assert len(us) > 1 and all(u["split"] and u["clause_words"] == 7 for u in us)
    assert [i for u in us for i in u["idx"]] == list(range(7))


def test_a_glued_phrase_is_never_cut():
    ws = ["كلمةطويلة"] * 5 + ["بور", "لو", "دوسييه"]
    us = CS.split_units(ws, width, MAX_W, glued={5, 6})
    assert any({5, 6, 7} <= set(u["idx"]) for u in us)


def test_wrap_balances_two_lines_and_refuses_what_cannot_fit():
    ws = ["كلمة"] * 4                                          # 4 x 254 px is over one 900 px line
    ls = CS.wrap_lines(ws, width, MAX_W)
    assert ls is not None and len(ls) == 2 and len(ls[0]) == len(ls[1]) == 2
    assert CS.wrap_lines(["كلمةطويلةجدا"] * 9, width, MAX_W) is None


def test_syllable_weights_follow_the_vowel_marks_and_fall_back_to_letters():
    w, how = CS.syllable_weights("أنتم أمام", "أَنْتُمْ أَمَامَ")
    assert how == "syllable" and w[1] > w[0]                                  # two vowels against three
    w, how = CS.syllable_weights("أنتم أمام", "أنتم")                           # the vowelled copy does not line up: letters
    assert how == "letter" and len(w) == 2
    w, how = CS.syllable_weights("أنتم", None)
    assert how == "letter"


def _windows():
    ws = "أنتم أمام النافذة العالية، والريح تفتحها.".split()
    us = [{"idx": [0, 1, 2, 3], "lines": [[0, 1], [2, 3]], "clause_words": 4, "split": False}, {"idx": [4, 5], "lines": [[4, 5]], "clause_words": 2, "split": False}]
    t = [(1.0 + 0.5 * i, 1.0 + 0.5 * i + 0.4) for i in range(6)]
    return ws, us, t


def test_the_highlight_walks_the_words_and_the_sentence_holds_until_the_next_one():
    ws, us, t = _windows()
    st = CS.unit_windows(us, t, t[-1][1], None)
    assert [s["word"] for s in st] == list(range(6))
    assert all(s["start"] == t[s["word"]][0] for s in st)
    assert st[3]["end"] == t[4][0]                                           # unit 1 stays up until unit 2 begins
    assert st[5]["end"] == round(t[5][1] + CS.TAIL_S, 3)                      # the last sentence keeps its tail
    st2 = CS.unit_windows(us, t, t[-1][1], 3.7)
    assert st2[5]["end"] == 3.68                                              # but never runs into the next line's plate


def _plates(ws, us, t, lid="L01"):
    out = []
    for s in CS.unit_windows(us, t, t[-1][1], None):
        u = us[s["unit"]]
        text = " ".join(ws[i] for i in u["idx"])
        out.append({"line": lid, "unit": s["unit"], "text": text, "active_index": s["k"], "word_i": s["word"], "n_lines": len(u["lines"]), "clause_words": u["clause_words"],
                    "split": u["split"], "start": s["start"], "end": s["end"], "word_start": s["word_start"]})
    return out


def test_check_plates_passes_a_clean_sentence_set_and_names_each_fault():
    ws, us, t = _windows()
    t = [(round(a * 1.4, 3), round(b * 1.4, 3)) for a, b in t]          # a take slow enough for max(1.5 s, chars / 12 cps) (C12)
    line = {"L01": {"id": "L01", "text": " ".join(ws)}}
    pl = _plates(ws, us, t)
    assert CS.check_plates(pl, line, {"L01": t}) == []
    # a half sentence: the first unit stops in the middle of a clause
    half = [{"idx": [0, 1], "lines": [[0, 1]], "clause_words": 4, "split": False}, {"idx": [2, 3, 4, 5], "lines": [[2, 3], [4, 5]], "clause_words": 4, "split": False}]
    assert any("middle of a sentence" in x for x in CS.check_plates(_plates(ws, half, t), line, None))
    # the same cut with an honest excuse (the clause was too long) passes
    excuse = [{**h, "split": True, "clause_words": 9} for h in half]
    assert not any("middle of a sentence" in x for x in CS.check_plates(_plates(ws, excuse, t), line, None))
    # a word skipped by the highlight
    bad = [p for p in pl if p["active_index"] != 1]
    assert any("visit each" in x for x in CS.check_plates(bad, line, None))
    # a word dropped from the line
    assert any("units show" in x for x in CS.check_plates([p for p in pl if p["unit"] == 0], line, None))
    # a highlight that drifted from the voice
    drift = [{**p, "word_start": p["word_start"] + 0.5} if p["word_i"] == 2 else p for p in pl]
    assert any("tolerance" in x for x in CS.check_plates(drift, line, {"L01": t}))
    # three lines
    assert any("lines (max" in x for x in CS.check_plates([{**p, "n_lines": 3} for p in pl], line, None))
    # a sentence flashed up for less than a reader needs
    quick = [{**p, "end": p["start"] + 0.05} for p in pl]
    assert any(x.startswith("CAP-READ-TIME") for x in CS.check_plates(quick, line, None))


def test_a_sentence_is_on_screen_long_enough_to_read():
    ws, us, t = _windows()
    pl = _plates(ws, us, t)
    for u in (0, 1):
        g = [p for p in pl if p["unit"] == u]
        assert g[-1]["end"] - g[0]["start"] >= CS.read_budget_s(len(us[u]["idx"]))


def _wav(path, spans, secs=3.0, sr=16000):
    frames = bytearray()
    for i in range(int(sr * secs)):
        t = i / sr
        on = any(a <= t < b for a, b in spans)
        v = int(32767 * (0.5 if on else 0.0) * math.sin(2 * math.pi * 220 * t))
        frames += v.to_bytes(2, "little", signed=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(sr)
        w.writeframes(bytes(frames))


def test_a_pause_in_the_take_is_never_spent_on_a_word(tmp_path):
    p = tmp_path / "take.wav"
    _wav(p, [(0.2, 1.0), (1.8, 2.6)])                       # a 0.8 s pause in the middle of the line
    ws = "كلمة اخرى ثالثة رابعة".split()
    tm = cc.word_timing(p, ws, [2.0, 2.0, 2.0, 2.0])
    assert tm[0][0] >= 0.15 and tm[-1][1] <= 2.65
    assert all(not (a0 < 1.0 - 0.05 and a1 > 1.8 + 0.05) for a0, a1 in tm)    # no word straddles the pause
    assert tm[2][0] >= 1.75                                                    # the third word waits for the voice after the pause
    assert all(b[0] >= a[1] - 1e-6 and b[1] > b[0] for a, b in zip(tm, tm[1:]))


def test_heavier_words_get_more_time(tmp_path):
    p = tmp_path / "take.wav"
    _wav(p, [(0.2, 2.2)])
    tm = cc.word_timing(p, ["أ", "ب"], [1.0, 3.0])
    assert (tm[1][1] - tm[1][0]) > 2 * (tm[0][1] - tm[0][0])


def test_plate_html_draws_a_two_line_sentence_with_one_highlight():
    st = [{"words": ["أنتم", "أمام", "النافذة", "العالية،"], "lines": [[0, 1], [2, 3]], "active": 2, "gloss": [], "style": None}]
    h = cc.plate_html(st, [], with_ref=True)
    assert h.count('class="ln"') == 4                      # two lines in the plate and in its twin
    assert h.count('class="on"') == 2 and '<span data-t="النافذة" class="on">النافذة</span>' in h


# ---- C8: the manager's «أري»
def test_glossed_word_is_in_the_glossary_with_the_bibles_meaning():
    e = [x for x in ENTRIES if x["character"] == "guide" and G.norm(x["word"]) == G.norm("أري")]
    assert len(e) == 1 and e[0]["language"] == "Gujarati" and e[0]["meaning_ar"] == "يا للعجب"
    bible = (SERIES / "characters" / "guide" / "bible.md").read_text(encoding="utf-8")
    assert "arre, hey, oh: surprise" in bible              # the English gloss the Arabic meaning translates


def test_every_own_language_word_in_a_bible_voice_section_is_in_the_glossary_or_confirmed_arabic():
    data = json.loads((SERIES / "glossary.json").read_text(encoding="utf-8"))
    assert G.audit_coverage(data["entries"], SERIES, data["arabic_words"]) == []
    cand = G.bible_candidates(SERIES)
    assert "آيغو" in cand["han"] and "أرّي" in cand["guide"]          # exclamations from the bible and the voice table are seen
    # a bible word nobody put in the glossary is caught
    assert any("أرّي" in x for x in G.audit_coverage([e for e in data["entries"] if G.norm(e["word"]) != G.norm("أري")], SERIES, data["arabic_words"]))


def test_a_speakers_own_word_must_be_tagged_by_the_writer():
    line = {"id": "L06", "speaker": "guide", "text": "أري! سبع ليال."}
    f = G.check_script_tags([line], ENTRIES)
    assert len(f) == 1 and "does not tag it" in f[0]
    assert G.check_script_tags([{**line, "foreign": [{"word": "أري", "language": "Gujarati", "meaning_ar": "يا للعجب"}]}], ENTRIES) == []
    assert any("not in the line" in x for x in G.check_script_tags([{**line, "foreign": [{"word": "تشالو", "language": "Gujarati", "meaning_ar": "هيا بنا"}]}], ENTRIES))
    assert any("glossary says" in x for x in G.check_script_tags([{**line, "foreign": [{"word": "أري", "language": "Gujarati", "meaning_ar": "هيه"}]}], ENTRIES))
    assert any("required" in x for x in G.check_script_tags([{**line, "foreign": [{"word": "أري", "language": "", "meaning_ar": "يا للعجب"}]}], ENTRIES))


def test_a_tagged_word_outside_the_glossary_still_needs_its_gloss_on_screen():
    line = {"id": "L9", "speaker": "guide", "text": "هيه يا عم", "foreign": [{"word": "هيه", "language": "Gujarati", "meaning_ar": "انتبه"}]}
    plate = {"line": "L9", "text": "هيه يا عم"}
    bad = G.check_captions([plate], {"L9": line}, ENTRIES)
    assert len(bad) == 1 and "هيه" in bad[0] and "انتبه" in bad[0]
    assert G.check_captions([{**plate, "text": "هيه (انتبه) يا عم"}], {"L9": line}, ENTRIES) == []


def test_a_caption_word_the_series_never_used_is_flagged_for_a_human():
    corpus = G.series_corpus(SERIES)
    known = sorted(corpus, key=len)[-3:]
    assert G.unrecognised_words(known + ["وكلمةغريبةتماما"], corpus, ENTRIES) == ["وكلمةغريبةتماما"]
    assert G.unrecognised_words(["والريح"], {"ريح"}, []) == []                  # a glued prefix (و + ال) does not make a known word unknown
    assert G.unrecognised_words(["أري!"], corpus, ENTRIES) == []             # a glossary word is known


def test_e01c_script_tags_the_manager_and_the_greeting():
    p = REPO / "work" / "rehearsal" / "E01C" / "script.json"
    if not p.is_file():
        return                                                               # the rehearsal folder is git-ignored
    lines = json.loads(p.read_text(encoding="utf-8"))["lines"]
    assert G.check_script_tags(lines, ENTRIES) == []
    l06 = next(l for l in lines if l["id"] == "L06")
    assert l06["foreign"][0]["word"] == "أري" and l06["foreign"][0]["meaning_ar"] == "يا للعجب"


def test_plan_validation_names_an_untagged_own_language_word(monkeypatch):
    monkeypatch.setattr(cc, "ROOT", sw_fixtures.PROJECT)       # the neutral fixture project, not a user's own series
    plan = {"series": "series", "episode": "E09", "day": 2, "place": "x", "recap": {"line": "اخترتم:", "word": "الباب"},
            "scenes": [{"id": f"s{i}", "template": "push_in"} for i in range(1, 6)], "choice": {"question": "q؟", "choice1": "a", "choice2": "b"}}
    line = {"id": "L06", "speaker": "guide", "text": "أري! سبع ليال."}
    assert any(x.startswith("PLAN-FOREIGN") and "أري" in x for x in cc.validate_plan(plan, {"series": "series", "lines": [line]}))
    tagged = {**line, "foreign": [{"word": "أري", "language": "Gujarati", "meaning_ar": "يا للعجب"}]}
    assert not any(x.startswith("PLAN-FOREIGN") for x in cc.validate_plan(plan, {"series": "series", "lines": [tagged]}))


def test_the_writer_is_told_to_tag_own_language_words():
    import daily
    assert '"foreign"' in daily.WRITER_PROMPT and "أري" in daily.WRITER_PROMPT


def test_a_glossed_sentence_that_is_up_too_briefly_hands_its_meaning_to_the_next_plates():
    ws = "شيكامو، يا عم. ساعتك لم تعرف بعد.".split()
    us = [{"idx": [0, 1, 2], "lines": [[0, 1, 2]], "clause_words": 3, "split": False}, {"idx": [3, 4, 5, 6], "lines": [[3, 4], [5, 6]], "clause_words": 4, "split": False}]
    t = [(0.0, 0.5), (0.5, 0.7), (0.7, 1.0), (1.0, 1.5), (1.5, 1.8), (1.8, 2.1), (2.1, 2.6)]
    st = CS.unit_windows(us, t, t[-1][1], None)
    CS.carry_glosses(st, {0: [("شيكامو", "تحية احترام للكبار")]}, {0: 3, 1: 4})
    assert not any(s.get("carry") for s in st if s["unit"] == 0)
    assert all(s["carry"][0]["meaning"] == "تحية احترام للكبار" for s in st if s["unit"] == 1)      # the whole next sentence carries it: the text never jumps
    line = {"L1": {"id": "L1", "text": " ".join(ws)}}
    pl = _plates(ws, us, t, "L1")
    for p, s in zip(pl, st):
        p["carry"] = s.get("carry", [])
        p["text"] = p["text"].replace("شيكامو،", "شيكامو، (تحية احترام للكبار)")
    assert CS.check_plates(pl, line, None) == []
    for p in pl:                                                                    # without the hand-over the same plates are too brief
        p["carry"] = []
    assert any("CAP-READ-TIME" in x and "gloss words" in x for x in CS.check_plates(pl, line, None))


# ---------------------------------------------------------------------------------------------- C12: CAP-READING-SPEED (owner, 2026-10-25)
def test_the_least_a_plate_stays_up_is_the_greater_of_one_and_a_half_seconds_and_chars_over_twelve():
    assert CS.read_speed_need_s(5) == CS.READ_MIN_S == 1.5                      # a short sentence still gets 1.5 s
    assert CS.read_speed_need_s(24) == 2.0 and CS.read_speed_need_s(36) == 3.0   # 12 characters a second above that
    assert CS.visible_chars("ويش؟ (ماذا) هذا") == len("ويش؟ ماذا هذا")             # the brackets are not read, the meaning is


def test_a_plate_up_for_less_than_its_reading_time_fails_reading_speed_and_names_the_numbers():
    ws = "أنتم أمام النافذة العالية،".split()          # 26 characters: 2.17 s
    us = [{"idx": [0, 1, 2, 3], "lines": [[0, 1], [2, 3]], "clause_words": 4, "split": False}]
    t = [(0.0, 0.4), (0.4, 0.8), (0.8, 1.2), (1.2, 1.6)]
    line = {"L01": {"id": "L01", "text": " ".join(ws)}}
    pl = []
    for s_ in CS.unit_windows(us, t, 1.6, None, 0.2):                      # a 0.2 s tail: up 1.8 s in all
        pl.append({"line": "L01", "unit": 0, "text": " ".join(ws), "active_index": s_["k"], "word_i": s_["word"], "n_lines": 2, "clause_words": 4, "split": False,
                   "start": s_["start"], "end": s_["end"], "word_start": s_["word_start"]})
    bad = [x for x in CS.check_plates(pl, line, None) if x.startswith("CAP-READING-SPEED")]
    assert len(bad) == 1 and "1.80 s" in bad[0] and "2.17 s" in bad[0] and "26 characters" in bad[0]
    long_tail = [{**p, "end": p["end"] + 0.5} if p["active_index"] == 3 else p for p in pl]     # 0.5 s more on the last state: 2.30 s
    assert not [x for x in CS.check_plates(long_tail, line, None) if x.startswith("CAP-READING-SPEED")]


def test_a_brief_unit_takes_a_neighbour_when_the_voice_leaves_it_up_too_short():
    ws = "هو يرى ذاك. هي تقف هنا. نحن نرى كل".split()
    brief = lambda idx, last: len(idx) < 4                                 # stand-in for "up for less than a reader needs"
    units = CS.split_units(ws, width, MAX_W, None, None, brief)
    never = CS.split_units(ws, width, MAX_W, None, None, lambda idx, last: False)
    assert sorted(i for u in units for i in u["idx"]) == list(range(len(ws)))        # nothing lost or reordered
    assert len(units) < len(never)                                                   # the brief units were merged


def test_a_brief_last_unit_joins_the_one_before_it():
    ws = "الريح تفتح النافذة. وتسقط".split()
    asked = []

    def brief(idx, last):
        asked.append((tuple(idx), last))
        return last and len(idx) < 2
    units = CS.split_units(ws, width, MAX_W, None, None, brief)
    assert [u["idx"] for u in units] == [[0, 1, 2, 3]] and any(last for _, last in asked)


def test_a_unit_short_of_its_need_by_a_hair_starts_early_and_the_unit_before_pays():
    st = [{"unit": 0, "start": 0.0, "end": 2.5, "word_start": 0.0}, {"unit": 1, "start": 2.5, "end": 3.96, "word_start": 2.5}]
    CS.borrow_lead(st, {0: 2.17, 1: 1.5})
    assert st[1]["start"] == 2.455 and st[0]["end"] == 2.455 and st[1]["word_start"] == 2.5       # the voice's word time never moves
    far = [{"unit": 0, "start": 0.0, "end": 2.5, "word_start": 0.0}, {"unit": 1, "start": 2.5, "end": 3.2, "word_start": 2.5}]
    CS.borrow_lead(far, {0: 2.17, 1: 1.5})
    assert far[1]["start"] == 2.5                                              # 0.8 s short: a lead-in cannot fix it, the gate reports it
    tight = [{"unit": 0, "start": 0.0, "end": 2.17, "word_start": 0.0}, {"unit": 1, "start": 2.17, "end": 3.66, "word_start": 2.17}]
    CS.borrow_lead(tight, {0: 2.17, 1: 1.5})
    assert tight[0]["end"] == 2.17                                             # the unit before has nothing to spare


def test_the_first_unit_short_of_its_need_by_a_hair_starts_before_its_first_word():
    st = [{"unit": 0, "start": 1.0, "end": 2.59, "word_start": 1.0}, {"unit": 1, "start": 2.59, "end": 5.0, "word_start": 2.59}]
    CS.borrow_lead(st, {0: 1.6, 1: 1.5})
    assert st[0]["start"] == 0.985 and st[0]["word_start"] == 1.0 and st[1]["start"] == 2.59      # nothing before it pays; the voice's word time never moves
    far = [{"unit": 0, "start": 1.0, "end": 2.2, "word_start": 1.0}, {"unit": 1, "start": 2.2, "end": 5.0, "word_start": 2.2}]
    CS.borrow_lead(far, {0: 1.6, 1: 1.5})
    assert far[0]["start"] == 1.0                                              # 0.4 s short: a lead-in cannot fix it, the gate reports it
