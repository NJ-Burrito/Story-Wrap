"""E02 critic fixes (2026-10-27): the per-shot grade (Q10), the recap's story picture (Q01), the heal guard against edits that break a passing shot, a card shot's video length in its
record hash, the gloss measure faces and the NJ mark clear of card text. No model, no GPU, no browser."""
import json
from pathlib import Path

import pytest

import calm
import calm_cards as cc
import calm_compose as cx
import daily
from shotlib.engine import hash_inputs
import sw_fixtures

REPO = Path(__file__).resolve().parents[2]


# ------------------------------------------------------------------ Q10: grade
def push_in(**kw):
    return calm.resolve("push_in", {"character": "hero", "pose": "write", "expression": "calm", "id": "t-s", "duration": 4.0, **kw})


@sw_fixtures.needs_project("calm kits (tools/templates/calm/kits/<char>.json and .js, built from your characters' smoke shots)", "tools/templates/calm/kits/hero.json")
def test_grade_defaults_to_nothing_so_no_cached_shot_changes():
    c = push_in()
    assert "grade" not in c
    assert "grade" not in calm.shot_json(c)["calm"]


@sw_fixtures.needs_project("calm kits (tools/templates/calm/kits/<char>.json and .js, built from your characters' smoke shots)", "tools/templates/calm/kits/hero.json")
def test_grade_reaches_calm_json_and_shot_json_and_is_bounded():
    c = push_in(grade="0.12", grade_actor="0.06")
    assert c["grade"] == {"set": 0.12, "actor": 0.06}
    assert calm.shot_json(c)["calm"]["grade"] == {"set": 0.12, "actor": 0.06}            # shot.json is hashed by shot.py: a changed grade re-records the shot
    assert push_in(grade="0.12")["grade"] == {"set": 0.12, "actor": 0.0}
    with pytest.raises(calm.CalmError):
        push_in(grade="0.4")                                                                  # past the measured ceiling: the gate would refuse the shot (luma_range 0.809 < 0.85)
    with pytest.raises(calm.CalmError):
        push_in(grade="0.06", grade_actor="0.1")                                           # the figure is never darker than the room


def test_the_scene_template_dims_in_flat_steps_only():
    js = (REPO / "tools" / "templates" / "calm" / "scene" / "calm-scene.js").read_text(encoding="utf-8")
    assert "function flatDim" in js and "gradeSet();" in js and "gradeActor();" in js
    body = js.split("function flatDim", 1)[1].split("function farDim", 1)[0]
    assert "createLinearGradient" not in body and "createRadialGradient" not in body and "fillRect" in body      # LOOK2D: flat steps, no gradient


# ------------------------------------------------------------------ Q01: the recap's story picture
PLAN = {"series": "series", "episode": "E02", "day": 2, "scenes": [{"id": "s01"}], "recap": {"line": "اخترتم:", "word": "هدى"}}


def test_recap_params_carry_a_backdrop_only_when_given():
    assert "backdrop" not in cx.recap_card_params(PLAN)
    assert cx.recap_card_params(PLAN, "/x/frame.png")["backdrop"] == "/x/frame.png"


def test_recap_backdrop_plan_checks():
    ok = {**PLAN, "recap": {**PLAN["recap"], "backdrop_from": "first_shot"}}
    assert cx.recap_backdrop_problems(ok) == []
    assert cx.recap_backdrop_problems({**PLAN, "recap": {**PLAN["recap"], "backdrop_from": "episode:E01C@12.5"}}) == []
    assert cx.recap_backdrop_problems({**PLAN, "recap": {**PLAN["recap"], "backdrop_from": "somewhere"}})[0].startswith("PLAN-RECAP-BACKDROP")
    assert cx.recap_backdrop_problems({**PLAN, "recap": {**PLAN["recap"], "backdrop": "no/such.png"}})[0].startswith("PLAN-RECAP-BACKDROP")
    both = {**PLAN, "recap": {**PLAN["recap"], "backdrop": "a.png", "backdrop_from": "first_shot"}}
    assert any("both" in x for x in cx.recap_backdrop_problems(both))
    assert not any(k.startswith("recap.backdrop") for k, _ in cx._visible_strings(ok))      # a picture source is not text people read


def test_recap_backdrop_source_first_shot_and_missing_video(tmp_path):
    plan = {**PLAN, "recap": {**PLAN["recap"], "backdrop_from": "first_shot"}}
    vid, t = cx.recap_backdrop_source(plan, tmp_path, "E02")
    assert vid == tmp_path / "work" / "shots" / "E02-s01" / "out" / "E02-s01.mp4" and t == 1.0
    with pytest.raises(cx.Fail) as e:
        cx.recap_backdrop_png(plan, tmp_path, "E02", tmp_path / "o.png")
    assert e.value.cid == "PLAN-RECAP-BACKDROP"
    assert cx.recap_backdrop_png(PLAN, tmp_path, "E02", tmp_path / "o.png") is None            # no picture asked: type on black as before
    img = tmp_path / "k.png"
    img.write_bytes(b"png")
    assert cx.recap_backdrop_png({**PLAN, "recap": {**PLAN["recap"], "backdrop": str(img)}}, tmp_path, "E02", tmp_path / "o.png").read_bytes() == b"png"


def test_recap_card_description_changes_when_the_picture_changes(tmp_path):
    a = tmp_path / "a.png"
    a.write_bytes(b"one")
    p = {"line": "اخترتم:", "word": "هدى"}
    ca = cc.resolve("recap_card", {**p, "backdrop": str(a)})
    assert ca == cc.resolve("recap_card", {**p, "backdrop": str(a)}) and ca["card"]["backdrop_sha256"]
    a.write_bytes(b"three")
    assert cc.resolve("recap_card", {**p, "backdrop": str(a)}) != ca                            # daily.s_shots compares descriptions: a re-cut story frame rebuilds the card


# ------------------------------------------------------------------ the heal guard
def plan_with(**p10):
    return {"scenes": [{"id": "s09", "template": "push_in", "params": {"size": "medium", "grade": "0.2"}},
                       {"id": "s10", "template": "push_in", "params": {"size": "mwide", "push": "3", **p10}}]}


def test_edit_detection_and_the_two_revert_levels():
    before = plan_with()
    after = plan_with(size="medium", grade="0.5")
    assert daily.edited_scene_ids(before, after) == {"s10"}
    fr = daily.revert_scene_edits(before, after, {"s10"}, "framing")
    assert fr["scenes"][1]["params"] == {"size": "mwide", "push": "3", "grade": "0.5"}          # framing goes back, the darker grade stays
    full = daily.revert_scene_edits(before, after, {"s10"}, "scene")
    assert full["scenes"][1] == before["scenes"][1] and full["scenes"][0] == before["scenes"][0]
    assert after["scenes"][1]["params"]["size"] == "medium"                                      # the inputs are not mutated


def shot_report(root, sid, verdict):
    d = root / "work" / "shots" / f"E02-{sid}" / "gate"
    d.mkdir(parents=True, exist_ok=True)
    (d / "report.json").write_text(json.dumps({"verdict": verdict}), encoding="utf-8")


def test_passing_and_regressed_scenes(tmp_path):
    plan = plan_with()
    shot_report(tmp_path, "s09", "PASS")
    shot_report(tmp_path, "s10", "PASS")
    assert daily.passing_scene_shots(tmp_path, "E02", plan) == {"s09", "s10"}
    shot_report(tmp_path, "s10", "FAIL")
    assert daily.regressed_scene_ids(tmp_path, "E02", plan, {"s10"}) == {"s10"}
    assert daily.regressed_scene_ids(tmp_path, "E02", plan, {"s09"}) == set()


def heal_ctx(tmp_path, monkeypatch, fails_when):
    """A context whose `shots` stage fails (SHOT-GATE, report FAIL) while the plan on disk satisfies fails_when(plan)."""
    root = tmp_path / "repo"
    ed = root / "bible" / "series" / "series" / "episodes" / "E02"
    ed.mkdir(parents=True)
    (root / "work" / "episodes" / "E02" / "heal").mkdir(parents=True)
    before = plan_with()
    (ed / "calm-plan.json").write_text(json.dumps(plan_with(size="medium", grade="0.5")), encoding="utf-8")
    ctx = daily.Ctx("E02", root=root, config={}, budget=daily.Budget(root, limit=1000, today="2026-10-25"), log=lambda *a: None)
    monkeypatch.setattr(daily, "validate_episode_files", lambda c: [])
    monkeypatch.setattr(daily, "restamp", lambda c, n: None)
    ran = []

    def shots(c):
        plan = json.loads((ed / "calm-plan.json").read_text(encoding="utf-8"))
        bad = fails_when(plan)
        shot_report(root, "s10", "FAIL" if bad else "PASS")
        ran.append("shots")
        if bad:
            raise daily.StageFail("SHOT-GATE", "1 shot(s) failed their gates: E02-s10: depth_bands")
        return {}
    for nm in daily.HEAL_STAGES:
        monkeypatch.setitem(daily.STAGES, nm, daily.Stage(nm, shots if nm == "shots" else (lambda c: {}), lambda c: [], "machine"))
    return ctx, ed, before, ran


def test_a_healer_edit_that_breaks_a_passing_shot_is_taken_back_framing_first(tmp_path, monkeypatch):
    ctx, ed, before, ran = heal_ctx(tmp_path, monkeypatch, lambda p: p["scenes"][1]["params"]["size"] == "medium")
    refused = daily.heal_run_stages(ctx, before, {"s10"})
    now = json.loads((ed / "calm-plan.json").read_text(encoding="utf-8"))
    assert now["scenes"][1]["params"]["size"] == "mwide" and now["scenes"][1]["params"]["grade"] == "0.5"      # only the framing went back
    assert len(refused) == 1 and "framing" in refused[0] and "s10" in refused[0] and ran == ["shots", "shots"]
    assert (ctx.work / "heal" / "refused-edits.jsonl").is_file()


def test_the_whole_scene_goes_back_when_the_framing_alone_does_not_fix_it(tmp_path, monkeypatch):
    ctx, ed, before, ran = heal_ctx(tmp_path, monkeypatch, lambda p: p["scenes"][1]["params"].get("grade") == "0.5")
    refused = daily.heal_run_stages(ctx, before, {"s10"})
    assert json.loads((ed / "calm-plan.json").read_text(encoding="utf-8"))["scenes"][1] == before["scenes"][1]
    assert len(refused) == 2 and "framing" in refused[0] and "scene" in refused[1]


def test_a_failure_that_is_not_a_regression_is_not_hidden(tmp_path, monkeypatch):
    ctx, ed, before, ran = heal_ctx(tmp_path, monkeypatch, lambda p: True)
    with pytest.raises(daily.StageFail):
        daily.heal_run_stages(ctx, before, set())            # the edited scene did not pass before: nothing to take back, the failure stands
    assert ran == ["shots"]


# ------------------------------------------------------------------ (b) a card's video length is in its record hash
def test_card_record_stage_hashes_the_duration(tmp_path):
    sd = tmp_path / "E02-day"
    cc.write_shot(cc.resolve("day_card", {"series": "the series", "day": 2, "duration": 2.0, "id": "E02-day"}), sd)
    (sd / "out").mkdir()
    (sd / "out" / "card.png").write_bytes(b"png")
    rec = next(s for s in cc.stages(sd) if s.name == "record")
    h1 = hash_inputs(rec.inputs(sd), REPO)
    cc.write_shot(cc.resolve("day_card", {"series": "the series", "day": 2, "duration": 2.5, "id": "E02-day"}), sd)      # only the duration changed; card.png is the same
    assert hash_inputs(rec.inputs(sd), REPO) != h1


def test_card_trace_stage_hashes_the_backdrop_picture(tmp_path):
    sd = tmp_path / "E02-recap"
    img = tmp_path / "bd.png"
    img.write_bytes(b"one")
    cc.write_shot(cc.resolve("recap_card", {"line": "اخترتم:", "word": "هدى", "backdrop": str(img), "id": "E02-recap"}), sd)
    tr = next(s for s in cc.stages(sd) if s.name == "trace")
    h1 = hash_inputs(tr.inputs(sd), REPO)
    img.write_bytes(b"two")
    assert hash_inputs(tr.inputs(sd), REPO) != h1


# ------------------------------------------------------------------ (c) gloss measure faces
def test_the_gloss_is_measured_in_the_faces_it_is_drawn_in():
    faces = cx.measure_faces()
    assert f"900 {cx.CAP_FONT_PX}px thmanyahsans" in faces and f"700 {cx.GLOSS_FONT_PX}px thmanyahsans" in faces
    src = (REPO / "tools" / "calm_compose.py").read_text(encoding="utf-8")
    assert "faces.map(f => document.fonts.load(f" in src and "measure_faces()])" in src


# ------------------------------------------------------------------ (d) the NJ mark and card text
def box(x0, y0, x1, y1, text="x"):
    return {"x0": x0, "y0": y0, "x1": x1, "y1": y1, "text": text}


def test_card_text_may_not_touch_the_mark():
    r = cc.WM.rect()
    assert cc.mark_problems([box(54, 330, 1026, 548, "question")])[0].startswith("CARD-MARK")      # a full-width first block reaches under the mark
    assert cc.mark_problems([box(54, 330, 896, 548)]) == []                                          # the layout's margin ends left of the mark's column
    assert cc.mark_problems([box(54, r["y"] + r["h"] + cc.WM.PAD_PX, 1026, 700)]) == []             # below the mark is free
    assert 1026 - cc.MARK_CLEAR_INLINE_PX <= r["x"] - cc.WM.PAD_PX


def test_check_card_runs_the_mark_check_but_not_for_the_cover():
    c = cc.resolve("choice_card", {"question": "ماذا نفعل؟", "choice1": "نغلق الباب", "choice2": "نفتح الباب", "id": "t"})["card"]
    meas = {"fonts_ok": True, "boxes": [{**box(54, 330, 1026, 548, "q"), "font_px": 78, "family": "thmanyahsans", "color": "rgb(243,237,228)"}]}
    assert any(x.startswith("CARD-MARK") for x in cc.check_card(c, meas))
    cover = cc.resolve("cover_card", {"series": "the series", "day": 2, "id": "t"})["card"]
    assert not any(x.startswith("CARD-MARK") for x in cc.check_card(cover, {"fonts_ok": True, "boxes": [{**box(100, 500, 1026, 700, "n"), "font_px": 300, "family": "thmanyahserifdisplay", "color": "rgb(19,17,14)"}]}))


# ------------------------------------------------------------------ the hero lamp with its red thread (x_lamp_thread)
@sw_fixtures.needs_project("calm kits (tools/templates/calm/kits/<char>.json and .js, built from your characters' smoke shots)", "tools/templates/calm/kits/hero.json")
def test_hero_lamp_thread_is_a_scene_param_drawn_after_the_key_lamp_and_absent_by_default():
    assert "lamp_thread" not in calm.shot_json(push_in())["calm"]["xp"]
    c = calm.shot_json(push_in(x_lamp_thread="cut", x_lamp_x="-0.22", x_lamp_z="2.3"))["calm"]["xp"]
    assert c["lamp_thread"] == "cut" and c["lamp_x"] == "-0.22"
    src = (REPO / "tools/templates/calm/scene/calm-scene.js").read_text(encoding="utf-8")
    i = src.index("drawLamp(tw);")
    assert src.index("drawLampThread(0, 0, st", i) > i and 'st === "tied" || st === "cut"' in src[i:]
