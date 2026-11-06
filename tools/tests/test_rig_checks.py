"""Rig-trace checks: a clean synthetic trace passes every check; one mutation per check id makes that id fail."""
import copy, json, math, subprocess, sys
import numpy as np
import pytest
import qg_checks as qc
from conftest import REPO, TOOLS

FPS, N = 24, 144           # 6 s, matches the two 3 s beats of the example spec
HU = 120.0


def g(t):                  # head yaw in degrees, period 2 s
    return 20.0 * math.sin(2 * math.pi * t / 2.0)


def make_trace():
    frames = []
    for i in range(N):
        t = i / FPS
        blink = 1.0 if any(s <= i < s + 3 for s in (12, 40, 90, 130)) else 0.0
        el = 35 + 95 * i / (N - 1)
        step = sum(0.2 for k in range(12, N, 12) if i >= k) % 1.0     # eye_y darts every 12 frames
        jump = 0.2 * (i >= 36) + 0.2 * (i >= 82)
        ctrl = {a: jump for a in ("AU1", "AU2", "AU4", "AU5", "AU12")}
        frames.append({
            "f": i, "t": t,
            "joints": {"elbow_flex_L": 40 + 20 * math.sin(t), "elbow_flex_R": 30.0, "knee_flex_L": 20.0, "shoulder_flex_L": 60.0},
            "bend_side": {"elbow_L": 1, "elbow_R": 1},
            "segments_px": {"upper_arm_L": 52.0, "forearm_L": 40.0},
            "anchors": {"shoulder_L": [480.0, 300.0 - 0.2 * (el - 30)], "shoulder_R": [600.0, 300.0], "torso_center": [540.0, 400.0], "palm_grip": [700.0, 500.0]},
            "torso_half_width_px": 60.0, "clavicle_y": 300.0 - 0.1 * (el - 30), "neck_length_px": 36.0,
            "arm_elevation_deg": {"L": el, "R": 10.0}, "shoulder_lift_px": {"L": 0.2 * (el - 30), "R": 0.0},
            "contact_points": {"pen_grip": [700.0, 500.0]},
            "contacts": [{"id": "pen-grip", "point": [700.0, 500.0], "target": [700.0, 500.0], "shoulder": [600.0, 300.0], "limb_len_px": 240.0}],
            "layer_order": {"angle": "front", "order": ["palm-R", "pen", "finger-index-R", "thumb-R"]},
            "com": [540.0, 900.0], "support_x": [480.0, 600.0],
            "face": {"eye_x": 0.01 * g(t + 3.0 / FPS * 0) + 0.0, "eye_y": step, "head_yaw": g(t), "blink": blink, "controls": ctrl},
        })
    # eye_x: leads the head by 3 frames, plus a slow independent drift so it is not a pure head-follow
    for i, fr in enumerate(frames):
        fr["face"]["eye_x"] = 0.01 * g((i + 3) / FPS) + 0.3 * math.sin(2 * math.pi * (i / FPS) / 12.0)
    return {"fps": FPS, "characters": {"hero": {"head_unit_px": HU, "rest_lengths_px": {"upper_arm_L": 52.0, "forearm_L": 40.0}, "frames": frames}}}


@pytest.fixture
def trace():
    return make_trace()


def fr(tr, i): return tr["characters"]["hero"]["frames"][i]
def ids(tr, spec): return qc.ids_of(qc.check_rig(tr, spec))


def _lag0(tr):
    for i, f in enumerate(tr["characters"]["hero"]["frames"]):
        f["face"]["eye_x"] = 0.01 * g(i / FPS) + 0.3 * math.sin(2 * math.pi * (i / FPS) / 12.0)


def _indep(tr):
    for f in tr["characters"]["hero"]["frames"]:
        f["face"]["eye_x"] = 0.01 * f["face"]["head_yaw"]


def _still_eyes(tr):
    for f in tr["characters"]["hero"]["frames"]:
        f["face"]["eye_x"] = 0.0; f["face"]["eye_y"] = 0.0
        f["face"]["head_yaw"] = 0.0


def _blink_long(tr):
    for i in range(60, 70): fr(tr, i)["face"]["blink"] = 1.0


def _flip(tr):
    for i in range(50, 144): fr(tr, i)["bend_side"]["elbow_R"] = -1
    fr(tr, 50)["joints"]["elbow_flex_R"] = 50.0
    fr(tr, 49)["joints"]["elbow_flex_R"] = 50.0


def _nofacemove(tr):
    for f in tr["characters"]["hero"]["frames"]: f["face"]["controls"] = {a: 0.0 for a in f["face"]["controls"]}


def _peak(tr):
    for i, f in enumerate(tr["characters"]["hero"]["frames"]):
        j = 0.2 * (i >= 36) + 0.2 * (i >= 130)
        f["face"]["controls"] = {a: j for a in f["face"]["controls"]}


def _noride(tr):
    for f in tr["characters"]["hero"]["frames"]: f["shoulder_lift_px"]["L"] = 0.0


def _attach(tr):
    for i in range(20, 24): fr(tr, i)["contact_points"]["pen_grip"] = [712.0, 500.0]


def _layers(tr):
    for f in tr["characters"]["hero"]["frames"]: f["layer_order"]["order"] = ["pen", "palm-R", "thumb-R", "finger-index-R"]


MUT = {
    "RIG-LIMITS": lambda tr: fr(tr, 10)["joints"].update(elbow_flex_R=175.0),
    "RIG-HINGE": _flip,
    "RIG-SEGLEN": lambda tr: fr(tr, 7)["segments_px"].update(upper_arm_L=60.0),
    "RIG-CONTACT-GAP": lambda tr: fr(tr, 5)["contacts"][0].update(point=[712.0, 500.0]),
    "RIG-REACH": lambda tr: fr(tr, 5)["contacts"][0].update(shoulder=[698.0, 500.0]),
    "RIG-ATTACH": _attach,
    "RIG-LAYERS": _layers,
    "RIG-SHOULDER": lambda tr: fr(tr, 3)["anchors"].update(shoulder_L=[520.0, 300.0]),
    "RIG-SHOULDER-RIDES": _noride,
    "RIG-BALANCE": lambda tr: fr(tr, 30).update(com=[760.0, 900.0]),
    "RIG-BLINK": _blink_long,
    "RIG-EYE-DART": _still_eyes,
    "RIG-EYE-INDEP": _indep,
    "RIG-EYE-LEAD": _lag0,
    "RIG-FACE": _nofacemove,
    "RIG-PEAK": _peak,
}


def test_clean_trace_passes_all(trace, example):
    assert qc.check_rig(trace, example) == []


@pytest.mark.parametrize("cid", sorted(MUT))
def test_rig_check_fails_on_mutation(cid, trace, example):
    assert cid not in ids(trace, example)
    bad = copy.deepcopy(trace)
    MUT[cid](bad)
    assert cid in ids(bad, example), qc.check_rig(bad, example)[:3]


def _all(tr, fn):
    for f in tr["characters"]["hero"]["frames"]: fn(f)


def test_raised_arm_with_elevated_shoulder_passes(trace, example):
    # the fixture lifts arm L from 35 to 130 deg with the shoulder rising 0.2 px per degree (0.1 head per 60 deg)
    assert max(f["arm_elevation_deg"]["L"] for f in trace["characters"]["hero"]["frames"]) > 125
    assert "RIG-SHOULDER" not in ids(trace, example)


def test_one_armed_gesture_passes_and_shrug_is_allowed(trace, example):
    for f in trace["characters"]["hero"]["frames"]:   # arm L at 150 deg, shoulder on the model line; the other arm rests
        f["arm_elevation_deg"]["L"] = 150.0; f["anchors"]["shoulder_L"][1] = 300.0 - 24.0
    assert "RIG-SHOULDER" not in ids(trace, example)
    for i in range(60, 80):   # a 0.1 head shrug of both shoulders for a moment
        for k in ("shoulder_L", "shoulder_R"): fr(trace, i)["anchors"][k][1] -= 12.0
    assert "RIG-SHOULDER" not in ids(trace, example)


def test_shoulder_that_stays_down_with_arm_raised_fails(trace, example):
    _all(trace, lambda f: f["anchors"]["shoulder_L"].__setitem__(1, 300.0))
    assert "RIG-SHOULDER" in ids(trace, example)


def test_shoulder_anchored_in_mid_chest_fails(trace, example):
    _all(trace, lambda f: f["anchors"]["shoulder_R"].__setitem__(0, 540.0 + 30.0))      # 30 px of a 60 px half width
    assert "RIG-SHOULDER" in ids(trace, example)


def test_mix_v2_fault_fails(trace, example):
    # Mix v2: shoulder x at 0.6..0.75 of the torso half width, with the arm raised and the shoulder risen
    _all(trace, lambda f: f["anchors"]["shoulder_L"].__setitem__(0, 540.0 - 0.7 * 60.0))
    assert "RIG-SHOULDER" in ids(trace, example)


def test_arc_inward_shift_is_small_and_model_is_zero_below_onset():
    assert qc.shoulder_lift_model(30.0, 120.0) == 0.0
    assert qc.shoulder_lift_model(90.0, 120.0) == pytest.approx(12.0)
    assert 0.0 < qc._arc_inward(24.0, 60.0) < 6.0


def test_exceed_window_excuses_a_soft_limit_but_not_a_hard_one(trace, example):
    t = fr(trace, 86)["t"]                       # inside the example's 3.5..3.62 s exceed window for shoulder_flex
    fr(trace, 86)["joints"]["shoulder_flex_L"] = 175.0
    assert "RIG-LIMITS" not in ids(trace, example)
    fr(trace, 86)["joints"]["shoulder_flex_L"] = 190.0
    assert "RIG-LIMITS" in ids(trace, example)


def _disc(n=60, r=20):
    y, x = np.ogrid[:n, :n]
    return (x - n // 2) ** 2 + (y - n // 2) ** 2 <= r * r


def test_shadow_mask_solid_passes():
    assert qc.shadow_mask_issues(_disc(), "ok") == []


def test_shadow_mask_hole_and_split_fail():
    m = _disc(); m[28:34, 28:34] = False                  # hollow circle
    assert "RIG-SHADOW-HOLES" in qc.ids_of(qc.shadow_mask_issues(m, "hole"))
    m2 = _disc(); m2[:, 28:32] = False                    # cut in two (a clipped neck)
    assert "RIG-SHADOW-HOLES" in qc.ids_of(qc.shadow_mask_issues(m2, "split"))


def test_rig_shadow_files(tmp_path, trace):
    from PIL import Image
    good = _disc(100, 30); Image.fromarray((good * 255).astype(np.uint8)).save(tmp_path / "ok.png")
    bad = good.copy(); bad[48:56, 48:56] = False; Image.fromarray((bad * 255).astype(np.uint8)).save(tmp_path / "bad.png")
    fr(trace, 0)["shadow_mask"] = "ok.png"
    assert qc.rig_shadow(trace, tmp_path) == []
    fr(trace, 6)["shadow_mask"] = "bad.png"
    assert "RIG-SHADOW-HOLES" in qc.ids_of(qc.rig_shadow(trace, tmp_path))


def test_trace_matches_schema(trace):
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((REPO / "kb/quality/rig-trace.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    assert list(jsonschema.Draft202012Validator(schema).iter_errors(trace)) == []


def test_cli_rig_exit_codes(tmp_path, trace):
    p = tmp_path / "t.json"; p.write_text(json.dumps(trace), encoding="utf-8")
    spec = str(REPO / "kb/quality/shot-spec.example.json")
    ok = subprocess.run([sys.executable, str(TOOLS / "quality_gate.py"), "rig", str(p), spec], capture_output=True, text=True)
    assert ok.returncode == 0, ok.stdout
    fr(trace, 10)["joints"]["elbow_flex_R"] = 175.0
    p.write_text(json.dumps(trace), encoding="utf-8")
    bad = subprocess.run([sys.executable, str(TOOLS / "quality_gate.py"), "rig", str(p), spec], capture_output=True, text=True)
    assert bad.returncode == 1 and "RIG-LIMITS" in bad.stdout
