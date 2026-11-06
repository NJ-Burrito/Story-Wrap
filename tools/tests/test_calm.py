"""Calm shot templates (tools/calm.py, calm_kit.py, calm_cards.py, shot.py card/format hooks): data in, a gated shot folder out. No browser, no GPU, no network."""
import json
import re
import sys
from pathlib import Path

import pytest

import calm
import calm_cards
import calm_kit
import sw_fixtures

TOOLS = Path(__file__).resolve().parents[1]
REPO = TOOLS.parent

ACTOR = {"push_in": {"character": "partner", "pose": "offer", "expression": "giving-relief"},
         "parallax_pan": {"character": "guide", "expression": "calm"},
         "hold_breathe": {"character": "partner", "expression": "calm-ceiling"},
         "insert": {"character": "partner", "target": "prop:bread_grip", "pose": "bread-low"},
         "insert_depth": {"character": "hero", "target": "prop:tag", "expression": "fear"},
         "reaction_closeup": {"character": "guide", "expression": "calm", "expression_to": "surprise"},
         "two_shot": {"characters": "partner,guide", "expressions": "calm-ceiling,calm", "gazes": "right,left"}}
CARDS = {"title_card": {"title": "the series", "line": "اليوم السابع"},
         "day_card": {"series": "the series", "day": "7", "clock": "9:04 م", "place": "الرف بلا رقم"},
         "recap_card": {"line": "اخترتم:", "word": "الرف"},
         "choice_card": {"question": "أين تنام الحقيبة الليلة؟", "choice1": "على الرف", "choice2": "في يد هدى"},
         "follow_card": {"line": "تابع لتعرف ماذا حدث", "handle": "@storywrap"},
         "choice_split": {"question": "أين تنام الحقيبة الليلة؟", "choice1": "على الرف", "choice2": "في يد هدى"},
         "object_card": {"heading": "the series"},
         "intro_freeze": {"character": "hero", "name": "هدى", "tag": "تضع بطاقة على كل شيء", "source": "work/shots/E01C-s02"}}


def test_every_template_of_the_brief_exists():
    want = {"push_in", "parallax_pan", "hold_breathe", "insert", "insert_depth", "reaction_closeup", "two_shot", "title_card", "day_card", "recap_card", "choice_card", "follow_card", "choice_split", "object_card", "intro_freeze"}
    assert want == set(calm.ACTOR_TEMPLATES) | set(calm.CARD_TEMPLATES)
    assert set(ACTOR) == set(calm.ACTOR_TEMPLATES) and set(CARDS) == set(calm.CARD_TEMPLATES)


@sw_fixtures.needs_project("calm kits (tools/templates/calm/kits/<char>.json and .js, built from your characters' smoke shots) and the character catalogue", "tools/templates/calm/kits/hero.json")
@pytest.mark.parametrize("name", list(ACTOR))
def test_actor_template_resolves_validates_and_writes_a_shot_folder(name, tmp_path):
    c = calm.resolve(name, {**ACTOR[name], "duration": "3.75", "id": f"t-{name}"})
    assert calm.validate_calm(c) == []
    assert c["format"] == "calm" and c["duration_s"] == 3.75
    sd = tmp_path / f"t-{name}"
    calm.write_shot(c, sd)
    shot = json.loads((sd / "shot.json").read_text(encoding="utf-8"))
    assert shot["format"] == "calm" and shot["id"] == sd.name and shot["fps"] == 24
    assert shot["scene_files"][0] == "scene/calm-scene.js"          # the scene defines registerKit before a kit hook calls it
    assert all((sd / f).is_file() for f in shot["scene_files"] + ["plan/camera.py", "plan/spec.py", "calm.json"])
    assert [a["id"] for a in shot["actors"]] == [a["id"] for a in c["actors"]]


@sw_fixtures.needs_project("calm kits (tools/templates/calm/kits/<char>.json and .js, built from your characters' smoke shots) and the character catalogue", "tools/templates/calm/kits/hero.json")
@pytest.mark.parametrize("name", list(ACTOR))
def test_camera_plan_and_spec_build_and_pass_the_spec_gate(name, tmp_path):
    """The generated plan/camera.py and plan/spec.py run through shot.py's own camera and spec code and the calm spec gate (quality_gate.py spec --format calm)."""
    import importlib.util
    import quality_gate as qg
    from shotlib import camera
    c = calm.resolve(name, {**ACTOR[name], "duration": "3.75", "id": f"t-{name}"})
    sd = REPO / "work" / "tests-calm" / f"t-{name}"
    sd.mkdir(parents=True, exist_ok=True)
    try:
        calm.write_shot(c, sd)
        shot = json.loads((sd / "shot.json").read_text(encoding="utf-8"))
        shot["rel"] = sd.relative_to(REPO).as_posix()
        def load(p, n):
            spec = importlib.util.spec_from_file_location(n, p)
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            return m
        plan = camera.build_plan(sd, shot, load(sd / "plan" / "camera.py", f"cam_{name}"))
        assert camera.validate_plan(plan, shot, REPO) == []
        spec = load(sd / "plan" / "spec.py", f"spec_{name}").build(plan, shot, None)
        assert spec["format"] == "calm" and spec["beats"][0]["emotion"]["peak_s"] > 0
        fails = qg.check_spec(spec, REPO, True, "calm")
        assert fails == [], fails
    finally:
        import shutil
        shutil.rmtree(sd.parent, ignore_errors=True)


def test_premium_thresholds_are_untouched_and_calm_is_a_separate_profile():
    import quality_gate as qg
    assert qg.SPEC_GATES["max_hold_s"] == 0.8 and qg.SPEC_GATES["max_hold_share"] == 0.10 and qg.SPEC_GATES["min_camera_move_pct"] == 4
    assert dict((k, (op, t)) for k, op, t, _ in qg.RENDER_GATES)["motion_coverage"] == (">=", 0.50)
    calm_gates = dict((k, (op, t)) for k, op, t, _ in qg.render_gates("calm"))
    assert calm_gates["motion_coverage"][0] == ">=" and calm_gates["motion_coverage"][1] < 0.5
    for art in ("luma_range", "local_contrast"):   # the art checks keep their premium thresholds
        assert calm_gates[art] == dict((k, (op, t)) for k, op, t, _ in qg.RENDER_GATES)[art]
    assert qg.spec_gates("premium") is qg.SPEC_GATES


@sw_fixtures.needs_project("calm kits (tools/templates/calm/kits/<char>.json and .js, built from your characters' smoke shots) and the character catalogue", "tools/templates/calm/kits/hero.json")
def test_durations_snap_to_the_frame_grid_and_are_bounded():
    c = calm.resolve("hold_breathe", {"character": "partner", "duration": "3.77"})
    assert abs(c["duration_s"] * 24 - round(c["duration_s"] * 24)) < 1e-9
    for bad in ("1.0", "12"):
        with pytest.raises(calm.CalmError) as e:
            calm.resolve("hold_breathe", {"character": "partner", "duration": bad})
        assert e.value.code == "CALM-PARAM"


@sw_fixtures.needs_project("calm kits (tools/templates/calm/kits/<char>.json and .js, built from your characters' smoke shots) and the character catalogue", "tools/templates/calm/kits/hero.json")
def test_missing_or_unknown_inputs_are_refused_not_guessed():
    with pytest.raises(calm.CalmError) as e:
        calm.resolve("push_in", {})
    assert e.value.code == "CALM-PARAM"
    with pytest.raises(calm.CalmError) as e:
        calm.resolve("push_in", {"character": "extra"})          # a character without a kit cannot be shot in the calm format yet
    assert e.value.code == "CALM-KIT"
    with pytest.raises(calm.CalmError) as e:
        calm.resolve("push_in", {"character": "partner", "expression": "no-such"})
    assert e.value.code == "CALM-EXPRESSION"
    with pytest.raises(calm.CalmError) as e:
        calm.resolve("push_in", {"character": "partner", "pose": "no-such"})
    assert e.value.code == "CALM-POSE"
    with pytest.raises(calm.CalmError) as e:
        calm.resolve("nope", {})
    assert e.value.code == "CALM-TEMPLATE"
    with pytest.raises(calm.CalmError) as e:
        calm.resolve("push_in", {"character": "partner", "set": "moon"})
    assert e.value.code == "CALM-SET"


@sw_fixtures.needs_project("calm kits (tools/templates/calm/kits/<char>.json and .js, built from your characters' smoke shots) and the character catalogue", "tools/templates/calm/kits/hero.json")
def test_the_expression_arrives_on_a_neutral_face_and_the_peak_is_the_arrival():
    c = calm.resolve("push_in", {"character": "partner", "expression": "giving-relief", "duration": "3.75"})
    a = c["actors"][0]
    assert a["expr_from"]["aus"] == {} and a["expr_to"]["aus"]
    assert a["peak_s"] == round((a["change_f"] + a["change_frames"] / 2) / 24, 4)   # RIG-PEAK: the biggest face change is the declared peak
    assert 6 <= a["change_frames"] <= 24
    assert a["darts"] and max(b[0] for b in a["darts"]) < 3.75
    gaps = [b[0] - a_[0] for a_, b in zip(a["darts"], a["darts"][1:])]
    assert all(g < 1.0 for g in gaps)                        # an eye dart in every second (RIG-EYE-DART)


@sw_fixtures.needs_project("calm kits (tools/templates/calm/kits/<char>.json and .js, built from your characters' smoke shots) and the character catalogue", "tools/templates/calm/kits/hero.json")
def test_reaction_turns_one_expression_into_another():
    c = calm.resolve("reaction_closeup", {**ACTOR["reaction_closeup"], "duration": "3.75"})
    a = c["actors"][0]
    assert a["expr_from"]["aus"] != a["expr_to"]["aus"] and 0.15 * 90 <= a["change_f"] <= 0.85 * 90


@sw_fixtures.needs_project("calm kits (tools/templates/calm/kits/<char>.json and .js, built from your characters' smoke shots) and the character catalogue", "tools/templates/calm/kits/hero.json")
def test_one_subject_per_frame_except_the_two_shot_and_no_touch_distance():
    one = calm.resolve("push_in", {**ACTOR["push_in"]})
    assert len(one["actors"]) == 1
    two = calm.resolve("two_shot", {**ACTOR["two_shot"]})
    assert len(two["actors"]) == 2 and calm.validate_calm(two) == []
    xs = [(calm_kit.load_kit(a["kit"]).get("root") or {}).get("X", 0) + a["root_dx"] for a in two["actors"]]
    assert abs(xs[0] - xs[1]) >= calm.HAND_REACH_M * 1.2
    bad = dict(two)
    bad["actors"] = [dict(a) for a in two["actors"]]
    bad["actors"][1]["root_dx"] = bad["actors"][0]["root_dx"] + (calm_kit.load_kit("partner")["root"]["X"] - calm_kit.load_kit("guide")["root"]["X"])   # both roots at the same X
    assert any(f.startswith("CALM-NO-TOUCH") for f in calm.validate_calm(bad))
    with pytest.raises(calm.CalmError):
        calm.resolve("two_shot", {"characters": "partner,partner"})


@sw_fixtures.needs_project("calm kits (tools/templates/calm/kits/<char>.json and .js, built from your characters' smoke shots) and the character catalogue", "tools/templates/calm/kits/hero.json")
def test_two_shot_spec_declares_the_no_touch_proof():
    c = calm.resolve("two_shot", {**ACTOR["two_shot"], "duration": "3.75"})
    spec = calm.build_spec(c, {"shots": [{"shot": "s1", "beat": "b1", "size": "MS", "angle": "eye", "lens_mm": 35, "move": "push", "start_frame_desc": "a", "end_frame_desc": "b", "dur_s": 3.75,
                                          "why": "a two-shot exchange", "serves_emotion": "calm", "safe_boxes": [], "thumbnail": "x"}]}, {"id": "t", "rel": "work/shots/t"})
    ap = [x for x in spec["actor_interactions"] if x["kind"] == "apart"]
    assert ap and ap[0]["min_gap_px"] >= 12 and {ap[0]["a"]["actor"], ap[0]["b"]["actor"]} == {"partner", "guide"}
    assert set(spec["beats"][0]["actor_emotions"]) == {"partner", "guide"}


@sw_fixtures.needs_project("calm kits (tools/templates/calm/kits/<char>.json and .js, built from your characters' smoke shots) and the character catalogue", "tools/templates/calm/kits/hero.json")
def test_a_passed_shot_is_not_rewritten_by_a_template(tmp_path):
    c = calm.resolve("hold_breathe", {"character": "partner", "id": "p"})
    sd = tmp_path / "p"
    calm.write_shot(c, sd)
    (sd / "gate").mkdir()
    (sd / "gate" / "report.json").write_text(json.dumps({"verdict": "PASS"}), encoding="utf-8")
    with pytest.raises(calm.CalmError) as e:
        calm.write_shot(c, sd)
    assert e.value.code == "CALM-EXISTS"


@sw_fixtures.needs_project("calm kits (tools/templates/calm/kits/<char>.json and .js, built from your characters' smoke shots) and the character catalogue", "tools/templates/calm/kits/hero.json")
def test_kits_are_complete_and_name_real_catalogue_files():
    assert set(calm_kit.list_kits()) >= {"partner", "guide"}
    for k in calm_kit.list_kits():
        kit = calm_kit.load_kit(k)
        assert kit["schema"] == "calm-kit/1" and kit["root"]["z"] == kit["actor"]["z"] and not kit.get("todo")
        assert (TOOLS / "templates" / "calm" / "kits" / f"{k}.js").is_file()
        for name, ex in kit["expressions"].items():
            assert (REPO / "catalogue" / "characters" / k / ex["dir"].strip("/") / f"{name}.json").is_file()
        for pname, p in kit["poses"].items():
            for sd, h in p["hands"].items():
                assert h["grip"] in kit["actor"]["catalogue"]["grips"], (k, pname, h["grip"])
        assert kit["default_pose"] in kit["poses"] and kit["default_expression"] in kit["expressions"]


@sw_fixtures.needs_project("calm kits (tools/templates/calm/kits/<char>.json and .js, built from your characters' smoke shots) and the character catalogue", "tools/templates/calm/kits/hero.json")
def test_kit_status_names_the_characters_that_cannot_be_shot_yet():
    st = calm_kit.status()
    assert "partner       KIT" in st and "hero       KIT" in st and "extra    no kit" in st


@sw_fixtures.needs_project("calm kits (tools/templates/calm/kits/<char>.json and .js, built from your characters' smoke shots) and the character catalogue", "tools/templates/calm/kits/hero.json")
def test_generic_scene_names_no_character():
    src = (TOOLS / "templates" / "calm" / "scene" / "calm-scene.js").read_text(encoding="utf-8")
    for name in ("partner", "guide", "hero", "lead", "extra", "rival", "han"):
        assert not re.search(rf"\b{name}\b", src, re.I), name


def test_scene_and_kit_scripts_pass_node_check():
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    for f in [TOOLS / "templates" / "calm" / "scene" / "calm-scene.js", *(TOOLS / "templates" / "calm" / "kits").glob("*.js")]:
        r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True)
        assert r.returncode == 0, (f, r.stderr)


# ------------------------------------------------------------------ cards
@pytest.mark.parametrize("name", list(CARDS))
def test_card_templates_resolve_and_write_a_shot_folder(name, tmp_path):
    c = calm.resolve(name, {**CARDS[name], "id": f"c-{name}"})
    assert c["kind"] == "card" and c["format"] == "calm" and calm.validate_calm(c) == []
    sd = tmp_path / f"c-{name}"
    calm.write_shot(c, sd)
    shot = json.loads((sd / "shot.json").read_text(encoding="utf-8"))
    assert shot["kind"] == "card" and shot["format"] == "calm"
    import calm_intro
    stages = (calm_intro if name == "intro_freeze" else calm_cards).stages(sd)
    from shotlib.engine import STAGE_ORDER
    assert [s.name for s in stages] == STAGE_ORDER                       # shot.py runs it like any other shot


def test_cards_refuse_tashkeel_and_missing_text():
    with pytest.raises(calm.CalmError) as e:
        calm.resolve("recap_card", {"line": "اخترتم:", "word": "الرَّفّ"})
    assert e.value.code == "CALM-TASHKEEL"
    with pytest.raises(calm.CalmError) as e:
        calm.resolve("choice_card", {"question": "q", "choice1": "a"})
    assert e.value.code == "CALM-PARAM"
    with pytest.raises(calm.CalmError):
        calm.resolve("follow_card", {"line": "x", "colour": "red"})


def test_day_card_writes_arabic_digits_and_the_choice_card_names_two_options():
    d = calm.resolve("day_card", {**CARDS["day_card"]})
    assert d["card"]["text"]["day_label"] == "اليوم ٧" and d["card"]["text"]["clock"] == "٩:٠٤ م"
    ch = calm.resolve("choice_card", {**CARDS["choice_card"]})
    html = calm_cards.card_html({**ch["card"], "backdrop_png": None})
    assert html.count('class="pill"') == 2 and "اكتبوا اختياركم بكلماتكم" in html and "١ أو ٢" not in html and "«على الرف»" in html and "thmanyahserifdisplay" in html and "Cairo" not in html


def test_choice_cards_refuse_digits_and_long_phrases():
    """C13 (2026-10-25): a choice is a short phrase a viewer can type, never 1 or 2."""
    with pytest.raises(calm.CalmError) as e:
        calm.resolve("choice_split", {"question": "q", "choice1": "١ على الرف", "choice2": "مع هدى"})
    assert e.value.code == "CALM-CHOICE"
    with pytest.raises(calm.CalmError) as e:
        calm.resolve("choice_card", {"question": "q", "choice1": "ضعوها على الرف بلا رقم أبدا", "choice2": "مع هدى"})
    assert e.value.code == "CALM-CHOICE"
    c = calm.resolve("choice_split", {"question": "q", "choice1": "الرف بلا رقم", "choice2": "مع هدى"})
    assert "tag1" not in c["card"]["text"]


def test_card_check_flags_a_fallback_font_unsafe_text_and_low_contrast():
    c = calm.resolve("recap_card", {**CARDS["recap_card"]})["card"]
    good = {"fonts_ok": True, "boxes": [{"text": "اخترتم:", "x0": 100, "y0": 400, "x1": 900, "y1": 600, "font_px": 78, "family": '"thmanyahsans"', "color": "rgb(243, 237, 228)"},
                                         {"text": "الرف", "x0": 100, "y0": 640, "x1": 900, "y1": 900, "font_px": 176, "family": '"thmanyahserifdisplay"', "color": "rgb(255, 77, 77)"}]}
    assert calm_cards.check_card(c, good) == []
    assert any(f.startswith("CARD-FONT") for f in calm_cards.check_card(c, {**good, "fonts_ok": False}))
    arial = {**good, "boxes": [{**good["boxes"][0], "family": "Arial"}, good["boxes"][1]]}
    assert any(f.startswith("CARD-FONT") for f in calm_cards.check_card(c, arial))
    out = {**good, "boxes": [{**good["boxes"][0], "x1": 1070}, good["boxes"][1]]}
    assert any(f.startswith("CARD-SAFE") for f in calm_cards.check_card(c, out))
    dim = {**good, "boxes": [{**good["boxes"][0], "color": "rgb(40, 38, 35)"}, good["boxes"][1]]}
    assert any(f.startswith("CARD-CONTRAST") for f in calm_cards.check_card(c, dim))
    assert any(f.startswith("CARD-ONE-IDEA") for f in calm_cards.check_card(c, {**good, "boxes": good["boxes"] * 2}))


def test_card_push_is_followed_by_a_hold_no_longer_than_three_seconds():
    for dur in (2.0, 2.5, 3.0, 5.0):
        pf = calm_cards.push_frames(dur)
        hold = dur - pf / 24 - 0.35
        assert 0 < hold <= 3.0 + 1e-9, (dur, hold)


# ---- kits for hero and lead, plan vocabulary, quiet faces (E01 calm, 2026-10-24)
@sw_fixtures.needs_project("calm kits (tools/templates/calm/kits/<char>.json and .js, built from your characters' smoke shots) and the character catalogue", "tools/templates/calm/kits/hero.json")
def test_every_kit_has_its_drawing_hook_and_the_plans_plain_feelings_resolve():
    for ch in ("partner", "guide", "hero", "lead"):
        assert calm_kit.kit_path(ch).is_file() and (calm_kit.KITS_DIR / f"{ch}.js").is_file()
    for ch in ("hero", "lead"):
        kit = calm_kit.load_kit(ch)
        assert kit["film"] and kit["expression_aliases"]
        for plain, real in kit["expression_aliases"].items():
            assert real in kit["expressions"], (ch, plain, real)
            calm.expression_of(kit, plain)    # the plan says "calm" or "fear"; the kit maps it to a catalogue file the character has
    c = calm.resolve("push_in", {"character": "hero", "expression": "fear", "duration": "4"})
    assert c["actors"][0]["expression"] == "dread-tag-read"


@sw_fixtures.needs_project("calm kits (tools/templates/calm/kits/<char>.json and .js, built from your characters' smoke shots) and the character catalogue", "tools/templates/calm/kits/hero.json")
def test_scene_parameters_for_the_kit_hook_travel_in_shot_json():
    c = calm.resolve("insert", {"character": "hero", "target": "prop:bag", "x_fall": "1", "x_near": "0", "duration": "4"})
    assert c["xp"] == {"fall": "1", "near": "0"}
    assert calm.shot_json(c)["calm"]["xp"] == {"fall": "1", "near": "0"}


@sw_fixtures.needs_project("calm kits (tools/templates/calm/kits/<char>.json and .js, built from your characters' smoke shots) and the character catalogue", "tools/templates/calm/kits/hero.json")
def test_a_quiet_face_puts_the_declared_peak_on_the_blink():
    c = calm.resolve("push_in", {"character": "lead", "expression": "calm", "duration": "4"})   # calm-courtesy barely moves the face: the blink is the biggest change (R-374)
    a = c["actors"][0]
    assert abs(a["peak_s"] - (a["blinks"][0] + 1) / 24) * 24 <= 3
    d = calm.resolve("push_in", {"character": "lead", "expression": "calm", "arrive_at": "0.2", "duration": "4"})   # an explicit arrival wins
    assert d["actors"][0]["change_f"] == max(3, round(0.2 * 96))


@sw_fixtures.needs_project("calm kits (tools/templates/calm/kits/<char>.json and .js, built from your characters' smoke shots) and the character catalogue", "tools/templates/calm/kits/hero.json")
def test_a_locked_camera_needs_and_keeps_its_reason():
    c = calm.resolve("insert", {"character": "hero", "target": "prop:tag", "locked": "the tag is the subject", "duration": "4"})
    assert c["camera"]["locked_because"] == "the tag is the subject" and c["camera"]["move_pct"] == 0
    assert calm.validate_calm(c) == []


def test_choice_split_may_run_past_the_9_s_shot_cap():
    """The 12.75 s choice sequence of E01C was refused by validate_calm (9 s cap for every shot) after the card builder had accepted it (2026-10-25)."""
    import calm
    c = calm.resolve("choice_split", {"id": "x-choice", "question": "q", "choice1": "a", "choice2": "b", "duration": 12.75})
    assert calm.validate_calm(c) == []
    c["template"], c["kind"] = "day_card", "card"
    assert any("CALM-DURATION" in x for x in calm.validate_calm(c))


@sw_fixtures.needs_project("calm kits (tools/templates/calm/kits/<char>.json and .js, built from your characters' smoke shots) and the character catalogue", "tools/templates/calm/kits/hero.json")
def test_a_changed_camera_changes_shot_json():
    """shot.py skips a stage whose input hashes did not change: the framing must be inside shot.json (E01C reused a stale video after size=medium, 2026-10-25)."""
    import calm
    a = calm.shot_json(calm.resolve("push_in", {"id": "t-a", "character": "hero", "size": "mwide"}))
    b = calm.shot_json(calm.resolve("push_in", {"id": "t-a", "character": "hero", "size": "medium"}))
    assert a != b


# ---------------------------------------------------------------- insert_depth (2026-10-25): a prop close-up built as separate planes
@sw_fixtures.needs_project("calm kits (tools/templates/calm/kits/<char>.json and .js, built from your characters' smoke shots) and the character catalogue", "tools/templates/calm/kits/hero.json")
@pytest.mark.parametrize("prop", ["tag", "key", "cards"])
def test_insert_depth_builds_real_planes_and_a_calm_dolly(prop):
    c = calm.resolve("insert_depth", {"character": "hero", "target": f"prop:{prop}", "expression": "fear", "duration": "5"})
    assert calm.validate_calm(c) == []
    d, cam = c["depth"], c["camera"]
    zh = d["hero_z"]
    # four separated planes, far to near: far set, counter surface, the hero prop, the occluder; the lens is closer than the plain insert's 5 m
    assert d["planes"]["far"] > d["planes"]["counter"][1] > zh - 0.2 and zh > d["occ"]["z"] > cam["cam0"]["z"] + 0.3
    assert zh - cam["cam0"]["z"] < 2.5
    # the camera is a dolly: same focal, z moves; a real push at the hero plane, inside the calm band (qg: recipe push 1.00 to 1.08, validate_calm < 40 %)
    assert cam["cam0"]["F"] == cam["cam1"]["F"] and cam["cam1"]["z"] > cam["cam0"]["z"]
    assert 3.0 <= cam["move_pct"] <= 12.5
    # nearer planes move faster for the same dolly: the rate each plane scales at
    rate = lambda z: (z - cam["cam0"]["z"]) / (z - cam["cam1"]["z"])
    assert rate(d["occ"]["z"]) > rate(zh) > rate(d["planes"]["far"]) > 1.0
    assert c["life"]["dust"] is False and "near" not in c["xp"]


@sw_fixtures.needs_project("calm kits (tools/templates/calm/kits/<char>.json and .js, built from your characters' smoke shots) and the character catalogue", "tools/templates/calm/kits/hero.json")
def test_insert_depth_refuses_a_prop_without_a_hero_drawing_and_an_occluder_inside_the_lens():
    with pytest.raises(calm.CalmError) as e:
        calm.resolve("insert_depth", {"character": "hero", "target": "prop:bag", "duration": "4"})
    assert "CALM-HERO" in str(e.value)
    with pytest.raises(calm.CalmError) as e:
        calm.resolve("insert_depth", {"character": "hero", "target": "prop:key", "dist": "0.9", "occ_z": "0.7", "duration": "4"})
    assert "CALM-DEPTH" in str(e.value)
    with pytest.raises(calm.CalmError):
        calm.resolve("insert_depth", {"character": "hero", "target": "hand_R"})   # an insert_depth is always on a prop


@sw_fixtures.needs_project("calm kits (tools/templates/calm/kits/<char>.json and .js, built from your characters' smoke shots) and the character catalogue", "tools/templates/calm/kits/hero.json")
def test_insert_depth_data_reaches_the_scene_through_shot_json_and_the_scene_draws_it():
    c = calm.resolve("insert_depth", {"id": "t-depth", "character": "hero", "target": "prop:key", "duration": "4"})
    j = calm.shot_json(c)
    assert j["calm"]["depth"]["hero"] == "key"                    # shot.py hashes shot.json: a changed depth plan reruns the build
    a = calm.shot_json(calm.resolve("insert_depth", {"id": "t-depth", "character": "hero", "target": "prop:key", "duration": "4", "push": "9"}))
    assert a != j
    scene = (calm.TPL_DIR / "scene" / "calm-scene.js").read_text(encoding="utf-8")
    kit = (calm.TPL_DIR / "kits" / "hero.js").read_text(encoding="utf-8")
    assert "const DEPTH = CALM.depth" in scene and "drawOccluder" in scene and "farDim" in scene
    assert "filter" not in scene.split("INSERT_DEPTH", 1)[1].split("const ease01", 1)[0]   # no blur: 2D flat tones only
    for hero in ("tag", "key", "cards"):
        assert f"  {hero}(t, Z)" in kit
    assert set(calm.kit_of("hero")["hero"]) == {"tag", "key", "cards"}
