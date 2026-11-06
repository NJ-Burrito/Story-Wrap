"""C3 + C4 + C5 (2026-10-25): transitions have a sound and a visual, foley is derived from the shot specs, the choice sequence pops with the narrator."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import calm_sfx as cs


def tl(split=True):
    items = [{"id": "s01", "kind": "scene", "t0": 0.0, "dur": 5.0}, {"id": "s02", "kind": "scene", "t0": 4.75, "dur": 5.0}]
    if split:
        items[1]["split"] = {"cuts": [{"t": 1.0, "clip": "B", "vfx": "flash"}], "lit": [{"state": "question", "t0": 0.5, "t1": 1.5}]}
    return {"items": items}


def plan(cut="page"):
    return {"scenes": [{"id": "s01"}, {"id": "s02"}], "transitions": [{"from": "s01", "to": "s02", "cut": cut}]}


def test_every_cut_type_has_visual_and_sound():
    for k, (vfx, xf, snd, *_rest) in cs.CUTS.items():
        assert vfx and xf and snd in cs.LIB, k


def test_join_gets_a_cue_and_passes():
    t = tl(); sfx = cs.build("EX", plan(), t)
    assert any(c["kind"] == "transition" and c["shot"] == "s02" for c in sfx["cues"])
    assert not [b for b in cs.check(sfx, plan(), t) if b.startswith("CALM-TRANSITION-SFX")]


def test_join_without_known_cut_fails():
    t = tl(); sfx = cs.build("EX", plan("nonsense"), t)
    assert any(b.startswith("CALM-TRANSITION-SFX") for b in cs.check(sfx, plan("nonsense"), t))


def test_choice_without_pops_fails():
    t = tl(); sfx = cs.build("EX", plan(), t)
    sfx["cues"] = [c for c in sfx["cues"] if c["kind"] != "choice"]
    assert any(b.startswith("CALM-CHOICE-SFX") for b in cs.check(sfx, plan(), t))


def test_unlicensed_file_fails():
    t = tl(); sfx = cs.build("EX", plan(), t)
    sfx["cues"][0]["licence_id"] = "sfx-nope"
    assert any(b.startswith("CALM-FOLEY") for b in cs.check(sfx, plan(), t))


def test_spec_words_map_props_and_actions():
    ev = cs.spec_foley({"beats": [{"emotion_track": {"sfx": [{"at_s": 1, "what": "pencil on paper"}, {"at_s": 0, "what": "office room tone"}, {"at_s": 2, "what": "bell's last strokes"}]}}]})
    assert [e["sound"] for e in ev] == ["pen", "bell"]


def test_default_cut_by_template():
    assert cs.default_cut({"template": "insert"}) == "page" and cs.default_cut({"id": "follow"}) == "whoosh"
