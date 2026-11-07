"""C10 (2026-10-25): intro_freeze, the character introduction. Pure logic and small synthetic pictures: no browser, no GPU, no video."""
import copy
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import calm
import calm_intro as ci
import calm_sfx

SCENES = [
    {"id": "s01", "template": "insert", "params": {"character": "hero", "target": "prop:bag"}},
    {"id": "s02", "template": "push_in", "params": {"character": "hero"}},
    {"id": "s03", "template": "insert_depth", "params": {"character": "hero", "target": "prop:tag"}},
    {"id": "s05", "template": "parallax_pan", "params": {"character": "guide"}},
    {"id": "s09", "template": "insert", "params": {"character": "guide", "target": "hand_R"}},
    {"id": "s13", "template": "two_shot", "params": {"characters": "hero,lead"}},
]


def plan(intros=None):
    return {"scenes": copy.deepcopy(SCENES), "intros": intros if intros is not None else [
        {"id": "intro-hero", "character": "hero", "after": "s02", "name": "هدى", "tag": "تضع بطاقة على كل شيء"},
        {"id": "intro-guide", "character": "guide", "after": "s05", "name": "أنطوان", "tag": "يضع سعرا لكل شيء"},
        {"id": "intro-lead", "character": "lead", "after": "s13", "name": "إدريس", "tag": "لا يتأخر ثانية"}]}


def test_first_appearance_skips_prop_and_hand_close_ups():
    f = ci.first_appearances(SCENES)
    assert f == {"hero": "s02", "guide": "s05", "lead": "s13"}      # s01 is a bag, s09 a bare hand: neither introduces a person


def test_plan_with_every_intro_passes_and_a_missing_one_fails():
    assert ci.plan_problems(plan()) == []
    p = plan()
    p["intros"] = p["intros"][:2]
    assert any("lead first appears in scene s13 and has no intro_freeze" in x for x in ci.plan_problems(p))


def test_intro_must_follow_the_first_appearance_and_only_once():
    p = plan()
    p["intros"][0]["after"] = "s03"
    assert any("first appearance is scene s02" in x for x in ci.plan_problems(p))
    p = plan()
    p["intros"].append({"id": "intro-hero-2", "character": "hero", "after": "s03", "name": "هدى", "tag": "تكتب"})
    assert any("introduced twice" in x for x in ci.plan_problems(p))


def test_intro_text_is_short_and_has_no_tashkeel():
    p = plan()
    p["intros"][0]["tag"] = "تَضَعُ بطاقة"
    assert any("tashkeel" in x for x in ci.plan_problems(p))
    p = plan()
    p["intros"][0]["tag"] = "تضع بطاقة على كل شيء في هذا المكتب كله اليوم"
    assert any("graffiti is short" in x for x in ci.plan_problems(p))


def test_the_narrator_reads_the_intro():
    script = {"lines": [{"id": "I01", "speaker": "hero"}]}
    p = plan()
    p["intros"][0]["line"] = "I01"
    assert any("read by the narrator" in x for x in ci.plan_problems(p, script))
    assert any("not in script.json" in x for x in ci.plan_problems(p, {"lines": []}))


def test_a_recorded_deferral_exempts_only_a_valid_one():
    """A plan may defer an intro to a later episode if it records it; the gate itself is not weaker for anyone else."""
    p = plan()
    p["episode"] = "E01"
    p["intros"] = p["intros"][:2]                                                       # `lead` has no intro
    assert any("lead first appears" in x for x in ci.plan_problems(p))                  # unrecorded: still refused
    p["intros_deferred"] = [{"character": "lead", "to_episode": "E02", "reason": "he speaks first in E02"}]
    assert ci.plan_problems(p) == []                                                    # recorded: allowed
    p["intros_deferred"][0]["to_episode"] = "E01"
    assert any("not a later episode" in x for x in ci.plan_problems(p))                 # not later: refused
    p["intros_deferred"] = [{"character": "lead", "to_episode": "E02", "reason": " "}]
    assert any("needs a character and a reason" in x for x in ci.plan_problems(p))
    p["intros_deferred"] = [{"character": "hero", "to_episode": "E02", "reason": "x"}]
    assert any("both introduced and deferred" in x for x in ci.plan_problems(p))
    # the built timeline: a deferred character needs no intro item
    pl = {"episode": "E01", "scenes": [SCENES[5]], "intros": [], "intros_deferred": [{"character": "hero", "to_episode": "E02", "reason": "r"}, {"character": "lead", "to_episode": "E02", "reason": "r"}]}
    assert ci.episode_problems(pl, {"items": [{"id": "s13", "kind": "scene"}]}, {}) == []
    del pl["intros_deferred"]
    assert any("no intro_freeze follows" in x for x in ci.episode_problems(pl, {"items": [{"id": "s13", "kind": "scene"}]}, {}))


def tl(freeze_in="freeze", back="page", with_intro=True):
    items = [{"id": "s02", "kind": "scene", "t0": 0, "dur": 5}]
    if with_intro:
        items.append({"id": "intro-hero", "kind": "intro", "character": "hero", "after": "s02", "t0": 4.75, "dur": 6, "join_in": {"cut": freeze_in}})
    items.append({"id": "s03", "kind": "scene", "t0": 10.5, "dur": 5, "join_in": {"cut": back}})
    return {"items": items}


ONE = {"scenes": [SCENES[1], SCENES[2]]}
GOOD = {"intro-hero": {"ok": True, "fails": []}}


def test_episode_gate_passes_an_introduced_character():
    assert ci.episode_problems(ONE, tl(), GOOD) == []


def test_episode_gate_catches_a_missing_intro_a_wrong_cut_and_an_unbuilt_shot():
    assert any("no intro_freeze follows" in x for x in ci.episode_problems(ONE, tl(with_intro=False), {}))
    assert any("dramatic transition is the cut 'freeze'" in x for x in ci.episode_problems(ONE, tl(freeze_in="whoosh"), GOOD))
    assert any("nothing carries the picture back" in x for x in ci.episode_problems(ONE, tl(back="freeze"), GOOD))
    assert any("no intro-measure.json" in x for x in ci.episode_problems(ONE, tl(), {"intro-hero": None}))
    assert any("failed its own gate" in x for x in ci.episode_problems(ONE, tl(), {"intro-hero": {"ok": False, "fails": ["INTRO-READ x"]}}))


def test_resolve_enforces_reading_time_and_text_rules():
    c = ci.resolve({"character": "hero", "name": "هدى", "tag": "تضع بطاقة على كل شيء", "source": "work/shots/E01C-s02", "id": "E01C-intro-hero"})
    assert c["kind"] == "card" and c["template"] == "intro_freeze" and c["card"]["accent"] and c["intro"]["words"] == 6
    assert c["duration_s"] >= ci.TEXT_DONE_S + ci.read_budget(5) + ci.OUT_S - 1e-9
    with pytest.raises(calm.CalmError) as e:
        ci.resolve({"character": "hero", "name": "هدى", "tag": "تضع بطاقة على كل شيء", "source": "x", "duration": 3.0})
    assert e.value.code == "CALM-DURATION"
    with pytest.raises(calm.CalmError) as e:
        ci.resolve({"character": "hero", "name": "هُدى", "tag": "تضع", "source": "x"})
    assert e.value.code == "CALM-TASHKEEL"
    with pytest.raises(calm.CalmError):
        ci.resolve({"character": "hero", "name": "هدى", "tag": "تضع", "source": "x", "colour": "red"})
    assert calm.resolve("intro_freeze", {"character": "hero", "name": "هدى", "tag": "تضع بطاقة", "source": "x"})["template"] == "intro_freeze"


def test_min_duration_grows_with_the_words_and_sits_on_the_grid():
    assert ci.min_duration(8) > ci.min_duration(3)
    d = ci.min_duration(5)
    assert abs(d * ci.FPS - round(d * ci.FPS)) < 1e-9


def ring_mask(h=96, w=54):
    m = np.zeros((h, w), np.uint8)
    m[20:80, 12:40] = 255
    m[22:78, 14:38] = 0                  # a closed outline, 2 px thick
    m[50:52, 0:3] = 255                  # a stray speck
    return m


def test_silhouette_fills_the_outline_and_drops_specks():
    s = ci.silhouette(ring_mask())
    assert s[50, 26] == 1.0 and s[30, 20] == 1.0     # inside the outline: filled
    assert s[51, 1] == 0.0                           # the speck is gone
    assert s[5, 5] == 0.0


def test_silhouette_closes_a_figure_cut_by_the_frame_edge():
    m = np.zeros((96, 54), np.uint8)
    m[30:96, 12:14] = 255                # an open U: two vertical lines running off the bottom and a top line
    m[30:32, 12:40] = 255
    m[30:96, 38:40] = 255
    s = ci.silhouette(m)
    assert s[70, 26] == 1.0                          # the body inside, down to the frame edge


def test_glow_is_a_rim_outside_and_nothing_inside():
    sil = np.zeros((200, 120), np.float32)
    sil[60:140, 40:80] = 1.0
    rim, halo = ci.glow_fields(sil)
    assert rim[100, 60] == 0 and halo[100, 60] == 0           # inside
    assert rim[100, 34] > 0.9 or rim[100, 35] > 0.9           # a few pixels outside the edge
    assert halo[100, 30] > halo[100, 5] > 0                   # falls off with distance


def test_dimmed_loses_colour_and_light_and_dim_amount_comes_back():
    rgb = np.zeros((60, 40, 3), np.float32)
    rgb[..., 0] = 220
    rgb[..., 1] = 80
    d = ci.dimmed(rgb)
    sat = lambda x: float((x.max(axis=2) - x.min(axis=2)).mean())
    assert sat(d) < 0.3 * sat(rgb) and d.mean() < 0.5 * rgb.mean()
    dur = 5.0
    assert ci.dim_amount(0.0, dur) == 0 and ci.dim_amount(1.5, dur) == 1.0 and ci.dim_amount(dur, dur) == 0


def test_reveal_sweeps_from_the_right_and_finishes():
    sm = ci.reveal_map(40, 120, 3)
    a_half = ci.reveal_alpha(sm, 0.5)
    assert a_half[:, 100:].mean() > a_half[:, :20].mean()      # the marker started at the right (Arabic)
    assert ci.reveal_alpha(sm, 0.0).max() == 0 and ci.reveal_alpha(sm, 1.0).min() == 1.0


def test_layout_prefers_the_place_the_character_hides_least():
    sil = np.zeros((480, 270), np.float32)               # canvas / 4
    sil[120:480, 80:190] = 1.0                           # a tall character in the middle
    block = np.ones((25, 60), np.float32)                # 100 x 240 px of text at 1/4 scale
    left, top, vis = ci.pick_layout(sil, block, 4, (54, 700), (280, 700), step=20)
    assert vis > 0.99                                    # it found a clear place (above the head, or to the side)
    assert top <= 480 or left >= 190 * 4 - 8 or left + 240 <= 80 * 4 + 8


def test_measure_problems_cover_text_read_and_isolation():
    good = {"fonts_ok": True, "text_boxes": [{"text": "هدى", "family": '"thmanyahserifdisplay"'}], "texts": {"name": "هدى"}, "placed_boxes": [{"layer": "name", "inside_safe": True}],
            "visible_share": 0.9, "silhouette_share": 0.2, "full_read_window_s": 2.5, "read_budget_s": 1.9, "words": 5, "duration_s": 6.0}
    assert ci.measure_problems(good) == []
    for patch, tag in (({"fonts_ok": False}, "INTRO-TEXT"), ({"text_boxes": [{"text": "x", "family": "Arial"}]}, "INTRO-TEXT"), ({"visible_share": 0.4}, "INTRO-TEXT"),
                       ({"texts": {"name": "هُدى"}}, "INTRO-TEXT"), ({"placed_boxes": [{"layer": "tag", "x0": 0, "y0": 0, "x1": 9, "y1": 9, "inside_safe": False}]}, "INTRO-TEXT"),
                       ({"silhouette_share": 0.01}, "INTRO-ISOLATE"), ({"full_read_window_s": 1.0}, "INTRO-READ"), ({"duration_s": 2.0}, "INTRO-LEN")):
        bad = ci.measure_problems({**good, **patch})
        assert any(x.startswith(tag) for x in bad), (patch, bad)


def test_video_problems_isolated_and_frozen_pass_and_a_bright_background_or_motion_fails():
    h, w = 400, 240
    sil = np.zeros((h, w), np.float32)
    sil[120:360, 70:170] = 1.0
    frame = np.full((h, w, 3), 30.0, np.float32)
    frame[sil > 0] = (200.0, 120.0, 60.0)
    d = np.zeros((h, w))
    yy, xx = np.mgrid[0:h, 0:w]
    inside = sil > 0.9
    from scipy import ndimage as ndi
    dist = ndi.distance_transform_edt(~inside)
    frame[(dist >= 2) & (dist <= 8)] = (200, 200, 200)       # the grey rim
    f, m = ci.video_problems(frame, frame.copy(), sil)
    assert f == [], (f, m)
    bright = frame.copy()
    bright[sil == 0] = (190.0, 120.0, 60.0)
    assert any("ISOLATE" in x for x in ci.video_problems(bright, bright.copy(), sil)[0])
    moved = frame.copy()
    moved[sil > 0] = (40.0, 180.0, 220.0)
    assert any("FROZEN" in x for x in ci.video_problems(frame, moved, sil)[0])


def test_the_freeze_cut_has_a_visual_and_the_impact_sound():
    vfx, xf, snd, *_ = calm_sfx.CUTS["freeze"]
    assert vfx and xf and snd == "impact" and snd in calm_sfx.LIB
    assert calm_sfx.default_cut({"kind": "intro", "id": "intro-hero"}) == "freeze"


def test_sfx_for_an_intro_needs_the_hit_and_the_marker():
    t = {"items": [{"id": "s02", "kind": "scene", "t0": 0.0, "dur": 5.0, "template": "push_in"},
                   {"id": "intro-hero", "kind": "intro", "t0": 4.75, "dur": 6.0, "character": "hero"},
                   {"id": "s03", "kind": "scene", "t0": 10.5, "dur": 5.0, "template": "insert"}]}
    pl = {"scenes": [{"id": "s02"}, {"id": "s03"}], "transitions": [{"from": "s02", "to": "intro-hero", "cut": "freeze"}, {"from": "intro-hero", "to": "s03", "cut": "page"}]}
    sfx = calm_sfx.build("EX", pl, t)
    assert any(c["sound"] == "impact" and c["kind"] == "transition" and c["shot"] == "intro-hero" for c in sfx["cues"])
    assert sum(1 for c in sfx["cues"] if c["sound"] == "pen" and c["shot"] == "intro-hero") >= 2
    assert not [b for b in calm_sfx.check(sfx, pl, t) if b.startswith("CALM-INTRO-SFX")]
    sfx["cues"] = [c for c in sfx["cues"] if c["sound"] != "impact"]
    assert any(b.startswith("CALM-INTRO-SFX") and "no impact cue" in b for b in calm_sfx.check(sfx, pl, t))


def test_layout_parts_keeps_the_worst_part_readable():
    sil = np.zeros((480, 270), np.float32)
    sil[160:480, 80:190] = 1.0                      # a character from y 640 down, x 320..760
    name = (np.ones((30, 60), np.float32), 0, 0)
    line = (np.ones((16, 60), np.float32), 0, 34)
    left, top, vis = ci.pick_layout_parts(sil, [name, line], 60, 52, 4, (54, 700), (274, 700), step=12)
    assert vis > 0.99 and top + 52 * 4 <= 640 + 8 or left + 240 <= 320 + 8 or left >= 760 - 8


def test_the_music_holds_its_breath_during_an_intro():
    import calm_mix
    n = int(12 * calm_mix.SR)
    env = calm_mix.intro_dip({"items": [{"kind": "scene", "t0": 0, "t1": 4}, {"kind": "intro", "t0": 3.75, "t1": 9.0}]}, n)
    at = lambda t: float(env[int(t * calm_mix.SR)])
    assert at(1.0) == 1.0 and at(11.0) == 1.0
    assert abs(at(6.0) - 10 ** (-calm_mix.INTRO_DIP_DB / 20)) < 1e-3
    assert calm_mix.intro_dip({"items": []}, 100).min() == 1.0
