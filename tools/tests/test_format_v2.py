"""Format v2 (the owner 2026-10-28): DIALOGUE-LINES, EVENTS, NARRATOR-SHARE / CALM-VOICE-COVERAGE, intros once per series, scene length, writer prompt and critic questions."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import calm_compose as cc   # noqa: E402
import calm_intro as ci   # noqa: E402
import daily   # noqa: E402
import qg_checks as qc   # noqa: E402
import sw_fixtures


def L(i, speaker="narrator"):
    return {"id": f"L{i:02d}", "speaker": speaker, "text": "كلام بلا تشكيل", "tts_text": "كَلَامٌ", "style": "story"}


def script(chars=("hero", "partner") * 6):
    """2 narrator lines (hook, recap) then the characters' lines, two more narrator lines at the end."""
    lines = [L(1), L(2)] + [L(3 + i, c) for i, c in enumerate(chars)]
    n = len(lines)
    return {"lines": lines + [L(n + 1), L(n + 2)]}


def plan(**kw):
    scenes = [{"id": f"s{i:02d}", "line": f"L{i + 2:02d}", "block": "consequence" if i < 3 else "story", "template": "push_in", "params": {"character": "partner"}} for i in range(1, 9)]
    scenes[1].update(event="Partner closes the drain with the iron cover")       # night 1
    scenes[5].update(event="Hero opens the locked box on the counter")        # night 2
    p = {"series": "no-such-series", "episode": "E03", "day": 3, "scenes": scenes}
    p.update(kw)
    return p


def ids(fs):
    return {f.split(" ", 1)[0] for f in fs}


# ---- DIALOGUE-LINES
def test_dialogue_count_speakers_and_exchange():
    assert cc.dialogue_problems(script()) == []                                    # 12 character lines, two speakers
    assert ids(cc.dialogue_problems(script(("hero", "partner") * 3))) == {"DIALOGUE-LINES"}          # 6 lines: too few
    assert ids(cc.dialogue_problems(script(("hero", "partner") * 9))) == {"DIALOGUE-LINES"}          # 18: too many
    assert cc.dialogue_problems(script(("hero", "partner") * 5)) == []                # the limits 10 and 15 are inside
    assert cc.dialogue_problems(script(("hero", "partner") * 7 + ("hero",))) == []
    one = cc.dialogue_problems(script(("hero",) * 12))
    assert any("fewer than 2" in x for x in one)                                    # one speaker only
    apart = script(("hero",) * 6 + ("partner",) * 6)                                  # two speakers who answer each other once at the seam
    assert cc.dialogue_problems(apart) == []
    sep = {"lines": []}
    for i, c in enumerate(("hero", "partner") * 6):        # a narrator link between every two character lines: nobody answers anybody
        sep["lines"] += [L(i * 2 + 1, c), L(i * 2 + 2)]
    assert any("no exchange" in x for x in cc.dialogue_problems(sep))


def test_v2_applies_from_e03_only():
    assert cc.format_v2({"episode": "E03"}) and cc.format_v2({"episode": "E12"}) and cc.format_v2({"series": "x"})
    assert not cc.format_v2({"episode": "E02"}) and not cc.format_v2({"episode": "E01C"}) and not cc.format_v2({"episode": "E01"})
    full = plan(hook={"pattern": 1, "line": "L01"}, recap={"line": "x", "word": "y"}, choice={"question": "q", "choice1": "a", "choice2": "b"})
    got = cc.validate_plan(full, script(("hero",) * 3))
    assert {"DIALOGUE-LINES", "NARRATOR-SHARE"} <= ids(got)
    old = cc.validate_plan({**full, "episode": "E02"}, script(("hero",) * 3))
    assert not ids(old) & {"DIALOGUE-LINES", "EVENTS", "NARRATOR-SHARE"}      # E02 is published under the old format


# ---- EVENTS
def test_events_count_template_and_every_night():
    assert cc.event_problems(plan()) == []
    p = plan()
    p["scenes"][1].pop("event")
    got = cc.event_problems(p)
    assert any("1 event scenes" in x for x in got) and any("night n1 has no event" in x for x in got)
    p = plan()
    for s in p["scenes"][:5]:
        s["event"] = "A thing happens in the room"
    assert any("event scenes" in x and "5" not in x.split("event scenes")[0][-2:] for x in cc.event_problems(p)) or ids(cc.event_problems(p)) == {"EVENTS"}      # 6 events: too many
    p = plan()
    p["scenes"][1]["template"] = "reaction_closeup"
    assert any("reaction_closeup" in x for x in cc.event_problems(p))               # a reaction alone is not an event
    p = plan()
    p["scenes"][5]["template"] = "hold_breathe"
    assert any("hold_breathe" in x for x in cc.event_problems(p))
    p = plan()
    p["scenes"][1]["event"] = "looks"
    assert any("not a sentence" in x for x in cc.event_problems(p))


def test_an_empty_night_is_refused_even_with_enough_events():
    p = plan()
    for s in p["scenes"]:
        s.pop("event", None)
    for i in (3, 4, 5):
        p["scenes"][i]["event"] = "Hero finds the key under the tag"            # all events in the second night
    got = cc.event_problems(p)
    assert any("night n1 has no event" in x for x in got) and not any("night n2" in x for x in got)
    p = plan()
    for s in p["scenes"]:
        s["night"] = "only"                                                       # an explicit single night is satisfied by any event
    assert cc.event_problems(p) == []


def test_needs_art_shape():
    assert cc.event_problems(plan(needs_art=[{"what": "iron drain cover, closed", "for_scene": "s02"}])) == []
    assert any("needs_art" in x for x in cc.event_problems(plan(needs_art="a drain cover")))
    assert any("needs_art" in x for x in cc.event_problems(plan(needs_art=[{"for_scene": "s02"}])))


# ---- narrator roles and share
def test_narrator_only_in_recap_link_and_vote_question():
    p = plan(hook={"pattern": 1, "line": "L01"}, choice={"question": "q", "choice1": "a", "choice2": "b", "lines": {"question": "L99"}})
    s = script()
    s["lines"][-1]["id"] = "L99"
    p["scenes"][0]["line"] = "L02"                                                # the first scene is the recap
    s["lines"][-2]["id"] = "L98"
    got = cc.narrator_role_problems(p, s)
    assert len(got) == 1 and "L98" in got[0]                                       # a narrator line nobody gave a role
    p["scenes"][7]["line"] = "L98"
    p["scenes"][7]["role"] = "link"
    assert cc.narrator_role_problems(p, s) == []
    s["lines"][-2]["text"] = "كلمة " * 15
    assert any("at most 14" in x for x in cc.narrator_role_problems(p, s))


def test_narrator_share_is_a_share_of_voice_time():
    assert cc.narrator_share([("narrator", 5.0), ("hero", 15.0)]) == pytest.approx(0.25)
    assert cc.narrator_share([("hero", 4.0)]) == 0.0 and cc.narrator_share([]) == 0.0
    assert cc.NARRATOR_SHARE_MAX == 0.25
    assert not hasattr(cc, "narrator_carries") and not hasattr(cc, "NARRATOR_SHARE_MIN")      # the old rule is gone


def test_voice_coverage_counts_any_speaker():
    pl = {"lines": [{"start": 0.0, "dur": 9.0}, {"start": 9.0, "dur": 0.6}]}      # 9.6 s of voice in 10 s from several speakers; nothing about who spoke
    assert not any("CALM-VOICE-COVERAGE" in x for x in qc.check_calm_declared(pl, {"captions": []}, {}, {}, 10.0))
    thin = qc.check_calm_declared({"lines": [{"start": 0.0, "dur": 5.0}]}, {"captions": []}, {}, {}, 10.0)
    assert any("[CALM-VOICE-COVERAGE]" in x for x in thin) and not any("[CALM-NARRATOR]" in x for x in thin)
    assert qc.CALM["voice_share_min"] == 0.85                                       # the threshold did not move


# ---- intros once per series
def series_tree(tmp_path, per_episode):
    for ep, chars in per_episode.items():
        d = tmp_path / "bible" / "series" / "s1" / "episodes" / ep
        d.mkdir(parents=True)
        (d / "calm-plan.json").write_text(json.dumps({"series": "s1", "episode": ep[:3], "intros": [{"id": f"intro-{c}", "character": c, "after": "s01"} for c in chars]}), encoding="utf-8")
    return tmp_path


def test_introduced_before_reads_the_earlier_episodes(tmp_path):
    root = series_tree(tmp_path, {"E01C": ["hero", "guide"], "E02": ["hero", "partner"], "E03": ["han"]})
    assert ci.introduced_before({"series": "s1", "episode": "E03"}, root) == {"hero", "guide", "partner"}
    assert ci.introduced_before({"series": "s1", "episode": "E04"}, root) == {"hero", "guide", "partner", "han"}
    assert ci.introduced_before({"series": "s1", "episode": "E02"}, root) == set()           # published under the old format
    assert ci.introduced_before({"series": "other", "episode": "E03"}, root) == set()
    assert ci.FORMAT_V2_FROM_EPISODE == cc.FORMAT_V2_FROM_EPISODE


def intro_plan(chars_on_screen, intros):
    scenes = [{"id": f"s{i}", "line": f"L{i}", "block": "story", "template": "push_in", "params": {"character": c}} for i, c in enumerate(chars_on_screen, 1)]
    return {"series": "s1", "episode": "E03", "scenes": scenes,
            "intros": [{"id": f"intro-{c}", "character": c, "after": f"s{chars_on_screen.index(c) + 1}", "name": "اسم", "tag": "وصف قصير"} for c in intros]}


def test_plan_intro_rejects_a_reintroduction_and_asks_only_for_new_characters(tmp_path):
    root = series_tree(tmp_path, {"E01C": ["hero", "guide"], "E02": ["partner"]})
    got = ci.plan_problems(intro_plan(["hero", "partner", "han"], ["hero", "han"]), None, root)
    assert any("PLAN-INTRO hero was introduced in an earlier episode" in x for x in got)          # re-intro refused
    assert not any("han" in x for x in got)                                                          # a new character is still introduced
    ok = ci.plan_problems(intro_plan(["hero", "partner", "han"], ["han"]), None, root)
    assert ok == []                                                                                   # no intro for the known cast, one for the new face
    missing = ci.plan_problems(intro_plan(["hero", "partner", "han"], []), None, root)
    assert any("han first appears" in x for x in missing) and not any("hero" in x or "partner" in x for x in missing)
    assert ci.plan_problems({**intro_plan(["hero"], ["hero"]), "episode": "E02"}, None, root) == []        # E02 keeps its own intros


# ---- the real series files
@sw_fixtures.needs_project("your early episodes under bible/series/<series>/episodes", "bible/series/series/episodes/E01")
def test_the_real_early_episodes_give_the_known_cast():
    known = ci.introduced_before({"series": "series", "episode": "E03"}, Path(__file__).resolve().parents[2])
    assert {"hero", "guide", "lead", "partner"} <= known


# ---- pacing, prompt, critic
def test_dialogue_scenes_may_reach_ten_seconds():
    assert cc.MAX_SCENE_S == 10.0
    assert cc.scene_seconds(9.0, None) == cc.snap(9.0 + cc.VOICE_LEAD_S + cc.PAD_S)
    with pytest.raises(cc.Fail):
        cc.scene_seconds(9.6, None)
    assert qc.CALM["shot_len_s"] == (1.8, 6.0)                                      # the average band is untouched


def test_writer_prompt_states_the_new_rules_and_formats():
    pr = daily.WRITER_PROMPT
    for must in ("10 to 15 spoken character lines", '"role": "link"', "`event`", "needs_art", "EVERY night", "INTROS ONCE PER SERIES", "never"):
        assert must in pr
    assert "lines for ONE narrator" not in pr
    out = pr.format(series="s", brief="b", ep="E03", day=3, epdir="d", learned="", fit="")
    assert "E03" in out


def test_critic_checks_dialogue_events_intros_and_nights():
    q13 = daily.CRITIC_QUESTIONS[-1]
    assert q13.startswith("Q13") and all(w in q13 for w in ("spoken character lines", "events", "no empty night", "introduced again"))
    assert "characters carry the story" in daily.CRITIC_QUESTIONS[4]


def test_the_old_narrator_check_ids_are_gone_from_the_tools():
    root = Path(__file__).resolve().parents[1]
    for name in ("qg_checks.py", "calm_compose.py", "animatic.py", "stagegate.py", "compose.py"):
        txt = (root / name).read_text(encoding="utf-8")
        assert '"CALM-NARRATOR"' not in txt, name
