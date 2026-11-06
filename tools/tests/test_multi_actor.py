"""Several characters in one shot: the two-actor pass fixture passes every check, and one mutation per new check id makes exactly that id fail.
New ids: ACTOR-DECLARED, ACTOR-ORDER, ACTOR-EMOTION, ACTOR-INTERACTION, SHADOW-ACTOR (spec); ACTOR-TRACE, ACTOR-OCCLUSION, ACTOR-CONTACT, HANDOVER (trace).
Also: per-actor emotion, the per-actor hand / rig checks, the registry (node harness, no browser), and the multi-actor engine plumbing."""
import copy, json, shutil, subprocess

import pytest

import qg_checks as qc
import quality_gate as qg
from conftest import REPO, TOOLS
from multi_actor_fixture import HANDOFF, two_spec, two_trace
import sw_fixtures

SPEC_IDS = {"ACTOR-DECLARED", "ACTOR-ORDER", "ACTOR-EMOTION", "ACTOR-INTERACTION", "SHADOW-ACTOR"}
TRACE_IDS = {"ACTOR-TRACE", "ACTOR-OCCLUSION", "ACTOR-CONTACT", "HANDOVER"}


@pytest.fixture
def spec():
    return two_spec()


@pytest.fixture
def trace():
    return two_trace()


def ids(f): return qc.ids_of(f)
def IA(sp, name): return next(x for x in sp["actor_interactions"] if x["id"] == name)
def SF(tr, i): return tr["scene"]["frames"][i]
def PROP(tr, i): return SF(tr, i)["props"][0]


# ---------------------------------------------------------------- fixtures on disk stay in step with the builder
def test_stored_fixtures_equal_the_builder():
    d = REPO / "kb/quality/fixtures"
    assert json.loads((d / "two-actor.shot-spec.json").read_text(encoding="utf-8")) == json.loads(json.dumps(two_spec()))
    assert json.loads((d / "two-actor.rig-trace.json").read_text(encoding="utf-8")) == json.loads(json.dumps(two_trace()))


# ---------------------------------------------------------------- pass cases
@sw_fixtures.needs_project("your characters' rig modules (tools/render/characters/<id>.js)", "tools/render/characters/hero.js")
def test_two_actor_spec_passes_every_spec_check(spec):
    assert qg.check_spec(spec, REPO, False) == []


def test_two_actor_trace_passes_every_rig_check(spec, trace):
    assert qc.check_rig(trace, spec, REPO) == []


def test_one_character_spec_and_trace_are_untouched():
    sp = json.loads((REPO / "kb/quality/shot-spec.example.json").read_text(encoding="utf-8"))
    assert qc.check_actors(sp) == []                      # no actors[]: the multi-actor rules do not apply
    from test_rig_checks import make_trace
    assert qc.rig_actors(make_trace(), sp) == []          # no scene block, one character: skipped


def test_single_actor_scene_trace_passes(spec, trace):
    sp = copy.deepcopy(spec); tr = copy.deepcopy(trace)
    del tr["characters"]["partner"]
    for fr in tr["scene"]["frames"]:
        fr["present"] = ["hero"]; fr["draw_order"] = ["hero:body", "hero:arms"]; fr["depth"] = {"hero": 2.4}; fr["props"] = []
    tr["scene"]["actors"] = tr["scene"]["actors"][:1]
    sp["actors"] = sp["actors"][:1]; sp["characters"] = sp["characters"][:1]; sp["actor_interactions"] = []
    for b in sp["beats"]:
        b.pop("draw_order"); b.pop("actor_emotions"); b["poses"] = b["poses"][:1]; b["cast_shadows"] = [s for s in b["cast_shadows"] if s.get("caster") != "partner"]
    assert qc.rig_actors(tr, sp) == []
    assert qc.check_actors(sp) == []


# ---------------------------------------------------------------- spec side: one mutation, one id
def _drop(d, k): d.pop(k)
def _actor_module(sp): sp["actors"][1].pop("module")
def _dup(sp): sp["actors"][1]["id"] = "hero"
def _no_rig(sp): sp["characters"] = sp["characters"][:1]
def _no_pose(sp): sp["beats"][0]["poses"] = sp["beats"][0]["poses"][:1]
def _bad_ref(sp): sp["actors"][1]["catalogue_refs"] = ["hero/model@1.0"]
def _invert(sp): sp["beats"][0]["draw_order"] = [{"order": ["hero", "partner"]}]    # the farther actor (partner) drawn last, over the nearer
def _missing_actor(sp): sp["beats"][0]["draw_order"] = [{"order": ["hero"]}]
def _split_no_why(sp): sp["beats"][0]["draw_order"] = [{"order": ["partner:body", "hero:body", "partner:arms", "hero:arms"]}]
def _gap(sp): sp["beats"][0]["draw_order"] = [{"t0": 0.0, "t1": 2.0, "order": ["partner", "hero"]}]       # beat b1 is 0..3 s
def _change_no_why(sp): sp["beats"][0]["draw_order"] = [{"t0": 0.0, "t1": 1.5, "order": ["partner", "hero"]}, {"t0": 1.5, "t1": 3.0, "order": ["partner:body", "hero", "partner:arms"]}]
def _no_interactions(sp): sp["actor_interactions"] = [x for x in sp["actor_interactions"] if x["beat"] != "b1"]
def _late_handoff(sp): IA(sp, "pass-cup")["handoff_frame"] = 200
def _one_both_frame(sp): IA(sp, "pass-cup")["both_hands_frames"] = 1
def _no_held_by(sp): IA(sp, "touch-cup")["b"].pop("held_by")
def _wide_tol(sp): IA(sp, "shake")["tol_px"] = 40
def _self_touch(sp): IA(sp, "shake")["b"]["actor"] = "hero"
def _same_giver(sp): IA(sp, "pass-cup")["receiver"]["actor"] = "hero"
def _no_shadow(sp): sp["beats"][1]["cast_shadows"] = [s for s in sp["beats"][1]["cast_shadows"] if s.get("caster") != "partner"]
def _no_actor_emotion(sp): sp["beats"][1]["actor_emotions"].pop("partner")
def _prop_missing(sp): IA(sp, "pass-cup")["prop"] = "nothing"

SPEC_MUT = [
    ("ACTOR-DECLARED", _actor_module), ("ACTOR-DECLARED", _dup), ("ACTOR-DECLARED", _no_rig), ("ACTOR-DECLARED", _no_pose), ("ACTOR-DECLARED", _bad_ref),
    ("ACTOR-ORDER", _invert), ("ACTOR-ORDER", _missing_actor), ("ACTOR-ORDER", _split_no_why), ("ACTOR-ORDER", _gap), ("ACTOR-ORDER", _change_no_why),
    ("ACTOR-ORDER", lambda sp: _drop(sp["beats"][0], "draw_order")),
    ("ACTOR-INTERACTION", _no_interactions), ("ACTOR-INTERACTION", _late_handoff), ("ACTOR-INTERACTION", _one_both_frame), ("ACTOR-INTERACTION", _no_held_by),
    ("ACTOR-INTERACTION", _wide_tol), ("ACTOR-INTERACTION", _self_touch), ("ACTOR-INTERACTION", _same_giver), ("ACTOR-INTERACTION", _prop_missing),
    ("SHADOW-ACTOR", _no_shadow), ("ACTOR-EMOTION", _no_actor_emotion),
]


@pytest.mark.parametrize("cid,mut", SPEC_MUT, ids=[f"{c}-{m.__name__ if hasattr(m, '__name__') else 'x'}" for c, m in SPEC_MUT])
def test_spec_mutation_fails_its_id(spec, cid, mut):
    sp = copy.deepcopy(spec); mut(sp)
    got = ids(qg.check_spec(sp, REPO, False))
    assert cid in got, got
    assert got <= SPEC_IDS, got                                                      # no unrelated check fires


def test_each_actor_is_checked_on_its_own_emotion(spec):
    sp = copy.deepcopy(spec)
    sp["beats"][0]["actor_emotions"]["partner"]["emotion_track"]["voice"] = None      # drop channels for the partner only
    sp["beats"][0]["actor_emotions"]["partner"]["emotion_track"]["sfx"] = None
    sp["beats"][0]["actor_emotions"]["partner"]["emotion_track"]["environment"] = None
    f = qg.check_spec(sp, REPO, False)
    assert "EMO-CHANNELS" in ids(f)
    assert all("actor partner" in x for x in f if "EMO-CHANNELS" in x), f           # named for the actor that fails, the hero is clean
    sp2 = copy.deepcopy(spec); sp2["beats"][0]["actor_emotions"]["hero"]["emotion"]["primary"] = "not-an-emotion"
    f2 = qg.check_spec(sp2, REPO, False)
    assert any("actor hero" in x and "EMO-DECLARED" in x for x in f2)


def test_light_may_serve_either_actors_feeling(spec):
    sp = copy.deepcopy(spec)
    b = sp["beats"][0]; b["actor_emotions"]["partner"]["emotion"]["primary"] = "sadness"; b["actor_emotions"]["partner"]["emotion"]["intensity"] = 0.4
    b["actor_emotions"]["partner"]["emotion_track"]["eyes"]["blink_per_min"] = [6, 10]
    assert "EMO-LIGHT" not in ids(qg.check_spec(sp, REPO, False))        # the light serves the hero's feeling; the partner's differs


# ---------------------------------------------------------------- trace side
def _tr_no_scene(tr): tr.pop("scene")
def _tr_no_partner(tr): tr["characters"].pop("partner")
def _tr_frames_off(tr): tr["characters"]["partner"]["frames"].pop()
def _oc_inverted(tr): SF(tr, 10)["draw_order"] = ["hero:body", "hero:arms", "partner:body", "partner:arms"]
def _oc_interleave(tr): SF(tr, 10)["draw_order"] = ["partner:body", "hero:body", "partner:arms", "hero:arms"]
def _oc_missing(tr): SF(tr, 10)["draw_order"] = ["partner:body", "partner:arms", "hero:body"]
def _oc_ghost(tr): SF(tr, 10)["draw_order"] = ["ghost:body", "ghost:arms", "partner:body", "partner:arms", "hero:body", "hero:arms"]
def _oc_depth_swap(tr): SF(tr, 10)["depth"] = {"hero": 3.0, "partner": 2.8}                     # hero is now the farther one but is still drawn last
def _oc_nodepth(tr): SF(tr, 10)["depth"] = {"hero": 2.4}
def _oc_empty(tr): SF(tr, 10)["draw_order"] = []
def _ct_far(tr): tr["characters"]["partner"]["frames"][30]["contact_points"]["hand_L"] = [640.0, 520.0]
def _ct_nodata(tr): tr["characters"]["partner"]["frames"][30]["contact_points"].pop("hand_L")
def _ct_parent(tr): PROP(tr, 80)["parent"] = {"actor": "partner", "hand": "L"}
def _ct_cup_far(tr): tr["characters"]["partner"]["frames"][75]["contact_points"]["hand_L"] = [PROP(tr, 75)["pos"][0] + 30, PROP(tr, 75)["pos"][1]]
def _ho_early(tr):
    for i in range(HANDOFF - 2, HANDOFF): PROP(tr, i)["parent"] = {"actor": "partner", "hand": "L"}
def _ho_late(tr):
    for i in range(HANDOFF, HANDOFF + 3): PROP(tr, i)["parent"] = {"actor": "hero", "hand": "R"}
def _ho_never(tr):
    for i in range(72, 108): PROP(tr, i)["parent"] = {"actor": "hero", "hand": "R"}
def _ho_one_hand(tr): PROP(tr, HANDOFF - 2)["hands"] = [{"actor": "hero", "hand": "R", "gap_px": 2.0}]
def _ho_far(tr): PROP(tr, HANDOFF - 1)["hands"][1]["gap_px"] = 25.0
def _ho_teleport(tr):
    for i in range(HANDOFF, 144): PROP(tr, i)["pos"] = [PROP(tr, i)["pos"][0] + 60.0, PROP(tr, i)["pos"][1]]
def _ho_noprop(tr): SF(tr, 80)["props"] = []

TRACE_MUT = [
    ("ACTOR-TRACE", _tr_no_scene), ("ACTOR-TRACE", _tr_no_partner), ("ACTOR-TRACE", _tr_frames_off),
    ("ACTOR-OCCLUSION", _oc_inverted), ("ACTOR-OCCLUSION", _oc_interleave), ("ACTOR-OCCLUSION", _oc_missing), ("ACTOR-OCCLUSION", _oc_ghost),
    ("ACTOR-OCCLUSION", _oc_depth_swap), ("ACTOR-OCCLUSION", _oc_nodepth), ("ACTOR-OCCLUSION", _oc_empty),
    ("ACTOR-CONTACT", _ct_far), ("ACTOR-CONTACT", _ct_nodata), ("ACTOR-CONTACT", _ct_parent), ("ACTOR-CONTACT", _ct_cup_far),
    ("HANDOVER", _ho_early), ("HANDOVER", _ho_late), ("HANDOVER", _ho_never), ("HANDOVER", _ho_one_hand), ("HANDOVER", _ho_far), ("HANDOVER", _ho_teleport), ("HANDOVER", _ho_noprop),
]


@pytest.mark.parametrize("cid,mut", TRACE_MUT, ids=[f"{c}-{m.__name__}" for c, m in TRACE_MUT])
def test_trace_mutation_fails_its_id(spec, trace, cid, mut):
    tr = copy.deepcopy(trace); mut(tr)
    got = ids(qc.check_rig(tr, spec, REPO))
    assert cid in got, got
    assert got <= TRACE_IDS, got                                                       # nothing else in the rig checks moves


@sw_fixtures.needs_project("your characters' rig modules (tools/render/characters/<id>.js)", "tools/render/characters/hero.js")
def test_draw_order_may_interleave_when_the_spec_declares_it(spec, trace):
    sp = copy.deepcopy(spec); tr = copy.deepcopy(trace)
    split = ["partner:body", "hero:body", "partner:arms", "hero:arms"]
    for b in sp["beats"]: b["draw_order"] = [{"order": split, "why": "his arm reaches over her shoulder: arms in front of both bodies"}]
    for fr in tr["scene"]["frames"]: fr["draw_order"] = list(split)
    assert qg.check_spec(sp, REPO, False) == []
    assert qc.check_rig(tr, sp, REPO) == []


@sw_fixtures.needs_project("your characters' rig modules (tools/render/characters/<id>.js)", "tools/render/characters/hero.js")
def test_declared_order_change_is_followed_frame_exact(spec, trace):
    sp = copy.deepcopy(spec); tr = copy.deepcopy(trace)
    sp["beats"][1]["draw_order"] = [{"t0": 3.0, "t1": 4.0, "order": ["partner", "hero"]}, {"t0": 4.0, "t1": 6.0, "order": ["hero", "partner"], "why": "the hero steps back behind the partner as the cup changes hands"}]
    sp["beats"][1]["depth_z"] = {"hero": 2.4, "partner": 2.8}
    assert any(x for x in qg.check_spec(sp, REPO, False) if "ACTOR-ORDER" in x)       # hero over partner is wrong while hero is nearer
    sp["beats"][1]["depth_z"] = {"hero": 2.4, "partner": 2.8}
    sp["beats"][1]["draw_order"][1]["order"] = ["partner", "hero"]
    sp["beats"][1]["draw_order"][1]["why"] = "same order, a second window (declared so the change point is explicit)"
    assert qg.check_spec(sp, REPO, False) == []
    for fr in tr["scene"]["frames"]:
        if fr["f"] == 100: fr["draw_order"] = ["hero:body", "hero:arms", "partner:body", "partner:arms"]
    assert "ACTOR-OCCLUSION" in ids(qc.check_rig(tr, sp, REPO))


def test_per_actor_hand_and_rig_checks_name_the_actor(spec, trace):
    tr = copy.deepcopy(trace)
    tr["characters"]["partner"]["frames"][5]["joints"]["elbow_flex_L"] = 400.0
    f = qc.check_rig(tr, spec, REPO)
    assert any("RIG-LIMITS" in x and "partner frame 5" in x for x in f), f
    assert not any("hero frame 5" in x for x in f)
    tr = copy.deepcopy(trace)
    for i in range(10, 14):
        tr["characters"]["hero"]["frames"][i]["hand_pose"] = {"R": {"id": "hero/hand/x-L", "topo": {"fingers": 4, "order": qc.HANDW["finger_order"]}, "fingers": {}}}
    f = qc.check_rig(tr, spec, REPO)
    assert any("HAND-SIDE" in x and "hero" in x for x in f), f


def test_scene_frame_shapes_are_documented_in_the_schema():
    sch = json.loads((REPO / "kb/quality/rig-trace.schema.json").read_text(encoding="utf-8"))
    assert "scene" in sch["properties"] and "draw_order" in json.dumps(sch["properties"]["scene"])
    sp = json.loads((REPO / "kb/quality/shot-spec.schema.json").read_text(encoding="utf-8"))
    txt = json.dumps(sp)
    for k in ("actors", "actor_interactions", "actor_emotions", "draw_order", "handoff_frame"):
        assert k in txt, k


# ---------------------------------------------------------------- engine plumbing
def test_catalogue_stage_reads_every_actor(tmp_path):
    from shotlib import catalogue
    shot = json.loads((REPO / "work/shots/smoke-partner/shot.json").read_text(encoding="utf-8")) if (REPO / "work/shots/smoke-partner/shot.json").is_file() else None
    if shot is None:
        pytest.skip("smoke-partner shot not present")
    two = copy.deepcopy(shot); two["actors"].append({**copy.deepcopy(shot["actors"][0]), "id": "inti2"})
    rep, fails = catalogue.check(two, REPO)
    assert fails == [] and rep["actors"] == ["partner", "inti2"]
    two["actors"][1]["catalogue"]["grips"].append("no-such-grip")
    rep, fails = catalogue.check(two, REPO)
    assert any("no-such-grip" in x for x in fails)


def test_one_character_shot_json_still_reads_as_one_actor():
    from shotlib import catalogue
    shot = json.loads((REPO / "tools/templates/shot/shot.json").read_text(encoding="utf-8"))
    a = catalogue.actor_list(shot)
    assert len(a) == 1 and a[0]["id"] == shot["character"] and a[0]["module"] == shot["character"]


def test_page_config_carries_actors_and_lists_module_scripts(tmp_path):
    from shotlib import page
    shot = {"id": "t", "fps": 24, "duration_s": 1, "canvas": [10, 10], "world": "world-a", "cuts": [], "smears": [], "fonts": [], "scene_files": ["scene/main.js"],
            "library": ["core.js", "@scene"], "actors": [{"id": "a", "module": "partner"}], "draw_order": [{"f0": 0, "f1": 24, "order": ["a"]}], "rel": "work/shots/t"}
    cfg = page.config_for(shot, "work/shots/t")
    assert cfg["actors"][0]["id"] == "a" and cfg["draw_order"][0]["order"] == ["a"] and "character" not in cfg
    with pytest.raises(KeyError):
        page.config_for({k: v for k, v in shot.items() if k != "actors"}, "work/shots/t")   # a one-character shot still needs its character / catalogue


def test_recorder_keeps_masks_per_actor(tmp_path):
    import urllib.request
    from record import server
    srv = server.start(REPO, tmp_path, 24)
    try:
        for url in (f"http://127.0.0.1:{srv.port}/mask?kind=shadow&actor=partner&i=6", f"http://127.0.0.1:{srv.port}/mask?kind=line&i=6"):
            urllib.request.urlopen(urllib.request.Request(url, data=b"x", method="POST")).read()
        bad = urllib.request.Request(f"http://127.0.0.1:{srv.port}/mask?kind=shadow&actor=../x&i=6", data=b"x", method="POST")
        with pytest.raises(Exception):
            urllib.request.urlopen(bad).read()
    finally:
        srv.stop()
    assert (tmp_path / "masks/shadow/partner/0006.png").is_file() and (tmp_path / "masks/line/0006.png").is_file()


def test_extras_gate_reads_nested_shadow_masks():
    src = (TOOLS / "quality_gate.py").read_text(encoding="utf-8")
    assert "rglob(\"*.png\")" in src


# ---------------------------------------------------------------- registry (node, no browser)
@pytest.fixture(scope="module")
def reg():
    if not shutil.which("node"):
        pytest.skip("node not installed")
    r = subprocess.run(["node", str(TOOLS / "tests" / "actors_harness.js")], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_registry_gives_each_actor_its_own_module_and_data(reg):
    assert reg["ids"] == ["far", "near", "near2"] and reg["same_module_two_instances"]
    assert (reg["far_fd"], reg["near_fd"], reg["near_hm3"], reg["near_grip"]) == ("face2", "face1", "hand1", ["a"])
    assert reg["far_solve_sees_fd"] == "face2" and reg["near_solve_sees_fd"] == "face1"      # the module's `let FD` was cut: it reads the swapped slot
    assert reg["far_char"] == "mod2" and abs(reg["far_hum"] - 0.22) < 1e-9


def test_with_actor_restores_the_active_one(reg):
    assert reg["with_restores"] == ["mod2", "mod1", "near"]


def test_draw_order_default_declared_and_tokens(reg):
    assert reg["order_default"] == ["far", "near", "near2"]                  # farther first, then layer
    assert reg["order_window"] == ["near", "far:body", "far:arms", "near2"] and reg["order_after"] == ["far", "near", "near2"]
    assert reg["expand"] == ["far:body", "far:arms", "near:arms"]
    assert "unknown actor" in reg["bad_actor"] and "bad draw-order token" in reg["bad_token"]
    assert reg["calls"] == ["far:body", "far:arms", "near:body", "near2:body", "near2:arms", "near:arms"]
    assert reg["log"] == ["body2", "arms2", "body1", "body1", "arms1", "arms1"]


def test_layer_lists_are_per_actor_instance(reg):
    assert reg["layer_far"] == ["body-2", "arms-2"] and reg["layer_near"] == ["body-1", "arms-1"] and reg["layer_near2"] == ["body-1", "arms-1"]
    assert reg["layer_after_reset"] == [] and reg["duplicate"] == "duplicate actor id far" and reg["solve"] == 2


# ---------------------------------------------------------------- no-touch ('apart', the owner 2026-10-23): ACTOR-CONTACT proves a minimum gap between two actors' drawn hands
def _apart_case(spec, trace, gap):
    sp = copy.deepcopy(spec); tr = copy.deepcopy(trace)
    sp["actor_interactions"] = [x for x in sp["actor_interactions"] if x["id"] != "shake"] + [
        {"id": "no-touch", "kind": "apart", "beat": "b1", "t0": 1.0, "t1": 2.0, "why": "an object stays between their hands, they never touch",
         "a": {"actor": "hero", "hands": ["L", "R"]}, "b": {"actor": "partner", "hands": ["L", "R"]}, "min_gap_px": 12}]
    sq = lambda x, y: [[x, y], [x + 40, y], [x + 40, y + 40], [x, y + 40]]
    for cid, x0 in (("hero", 100), ("partner", 140 + gap)):
        for fr in tr["characters"][cid]["frames"]:
            fr["hand_outline_px"] = {"L": sq(x0, 500), "R": sq(x0, 700)}
    return sp, tr


def test_apart_passes_with_a_clear_gap(spec, trace):
    sp, tr = _apart_case(spec, trace, 30)
    assert "ACTOR-INTERACTION" not in ids(qg.check_spec(sp, REPO, False))
    assert "ACTOR-CONTACT" not in ids(qc.check_rig(tr, sp, REPO))


def test_apart_fails_when_hands_come_too_close(spec, trace):
    sp, tr = _apart_case(spec, trace, 4)
    got = ids(qc.check_rig(tr, sp, REPO)); assert "ACTOR-CONTACT" in got and got <= TRACE_IDS, got


def test_apart_without_outlines_fails(spec, trace):
    sp, tr = _apart_case(spec, trace, 30)
    for fr in tr["characters"]["partner"]["frames"]:
        fr.pop("hand_outline_px", None)
    assert "ACTOR-CONTACT" in ids(qc.check_rig(tr, sp, REPO))


@pytest.mark.parametrize("bad", [{"min_gap_px": 0}, {"why": "no"}, {"b": {"actor": "hero", "hands": ["L"]}}, {"a": {"actor": "hero", "hands": []}}])
def test_apart_spec_needs_two_actors_hands_gap_and_why(spec, trace, bad):
    sp, _ = _apart_case(spec, trace, 30); IA(sp, "no-touch").update(bad)
    got = ids(qg.check_spec(sp, REPO, False)); assert "ACTOR-INTERACTION" in got and got <= SPEC_IDS, got
