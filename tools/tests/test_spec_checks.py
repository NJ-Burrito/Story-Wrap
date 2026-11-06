"""Spec checks: for every check id, the passing example has no failure of that id and a one-line mutation of it does."""
import json, subprocess, sys
import pytest
import qg_checks as qc
import quality_gate as qg
from conftest import REPO, TOOLS


def B(sp, i): return sp["beats"][i]
def CH(sp): return sp["characters"][0]
def drop_parts(sp, names): CH(sp)["parts"] = [p for p in CH(sp)["parts"] if p["name"] not in names]
def setp(d, k, v): d[k] = v
def _hair(sp):
    for p in CH(sp)["parts"]:
        if p["name"] == "hair": p["under_garment"] = False
def _nocontacts(sp):
    for b in sp["beats"]:
        for ps in b["poses"]: ps.pop("contacts", None)
def _sh_contacts(sp):
    for s in B(sp, 0)["cast_shadows"]: s.pop("contacts", None)
def _selfsh(sp):
    for b in sp["beats"]:
        for s in b["cast_shadows"]: s.pop("self_shadow", None)
def _env(sp):
    for b in sp["beats"]:
        for i in b["interactions"]: i["carries_emotion"] = False
def _tr(sp, **kw): sp["transitions"][0].update(kw)
def _rc(sp): sp["transitions"][0]["type"] = "whip-smear"; sp["transitions"][0]["rate_change"][0]["ramp"] = "none"

MUT = {
    "BIO-PROFILE": lambda sp: setp(CH(sp), "physics_profile", "no-such-profile"),
    "BIO-PROPORTIONS": lambda sp: CH(sp)["rest_proportions"].update(shoulder_w=30),
    "BIO-EXEMPT": lambda sp: B(sp, 0)["poses"][0].update(stretch_events=[{"segment": "forearm", "t0": 0, "t1": 1, "max_scale": 2.0}]),
    "BIO-CONTACTS": _nocontacts,
    "POSE-CATALOGUE": lambda sp: B(sp, 0)["poses"][0].pop("catalogue"),
    "ATT-MODEL": lambda sp: CH(sp).pop("model_ref"),
    "ATT-ANCHORS": lambda sp: CH(sp)["anchors"].pop("neck_base"),
    "ATT-DECLARED": lambda sp: setp(CH(sp), "attachments", []),
    "ATT-LAYERS": lambda sp: CH(sp)["attachments"][0]["layer_order"].update(front=["palm-R"]),
    "ATT-FINGERS": lambda sp: drop_parts(sp, {"thumb-R", "finger-index-R"}),
    "ATT-HAIR": _hair,
    "SHADOW-MASS": lambda sp: B(sp, 1)["cast_shadows"][0].pop("source"),
    "SHADOW-CONTACT": _sh_contacts,
    "SHADOW-SELF": _selfsh,
    "SHADOW-SOFT": lambda sp: B(sp, 0)["light"]["key"].pop("size"),
    "TRANS-COUNT": lambda sp: setp(sp, "transitions", []),
    "TRANS-FIELDS": lambda sp: sp["transitions"][0].pop("cause"),
    "TRANS-STYLE": lambda sp: _tr(sp, style_entry="none-same-style"),
    "TRANS-CAUSE": lambda sp: _tr(sp, cause="bang"),
    "TRANS-CARRIER": lambda sp: _tr(sp, type="contour-wipe"),
    "TRANS-RATE": _rc,
    "TRANS-AUDIO": lambda sp: _tr(sp, audio_lead_frames=1),
    "CAM-PLAN": lambda sp: sp.pop("camera_plan"),
    "CAM-WHY": lambda sp: sp["camera_plan"][2].update(why="x"),
    "CAM-DUR": lambda sp: sp["camera_plan"][0].update(dur_s=0.5),
    "CAM-VARY": lambda sp: sp["camera_plan"][1].update(size="MWS", angle="eye", why="same again please"),
    "CAM-SAFE": lambda sp: sp["camera_plan"][2]["safe_boxes"][0].update(x=1000),
    "CAM-EMOTION": lambda sp: sp["camera_plan"][2].update(serves_emotion="calm"),
    "TEXT-SPEC": lambda sp: B(sp, 0).pop("texts"),
    "TEXT-LAYER": lambda sp: B(sp, 1)["texts"][0].update(layer="mid"),
    "TEXT-SIZE": lambda sp: B(sp, 1)["texts"][0].update(height_px=20),
    "TEXT-CONTRAST": lambda sp: B(sp, 1)["texts"][0].update(min_contrast=3.0),
    "TEXT-DWELL": lambda sp: B(sp, 1)["texts"][0].update(t1=4.5),
    "TEXT-SAFE": lambda sp: B(sp, 1)["texts"][0]["box"].update(y=100),
    "TEXT-TRANSITION": lambda sp: B(sp, 1)["texts"][0].update(t0=2.9, t1=4.3),
    "EMO-DECLARED": lambda sp: B(sp, 0)["emotion"].update(primary="grumpy"),
    "EMO-CHANNELS": lambda sp: [B(sp, 0)["emotion_track"].pop(k) for k in ("voice", "sfx", "environment")],
    "EMO-ORDER": lambda sp: B(sp, 0)["emotion_track"]["eyes"].update(onset_s=1.0),
    "EMO-GAZE": lambda sp: B(sp, 0)["emotion_track"]["eyes"].update(gaze_target=""),
    "EMO-BLINK": lambda sp: B(sp, 0)["emotion_track"]["eyes"].update(blink_per_min=[30, 40]),
    "EMO-HIDDEN": lambda sp: B(sp, 0)["emotion"].update(shown="hidden"),
    "EMO-COLOUR": lambda sp: B(sp, 1)["emotion_track"].update(colour=dict(B(sp, 0)["emotion_track"]["colour"])),
    "EMO-CHANGE": lambda sp: (B(sp, 1).pop("emotion_change"), B(sp, 1)["emotion"].update(cause="the bag slams the counter")),
    "EMO-SFXVFX": lambda sp: B(sp, 1)["emotion_track"].update(sfx=[]),
    "EMO-LIGHT": lambda sp: B(sp, 0)["light"].update(serves_emotion="joy"),
    "EMO-ENV": _env,
    "EMO-PROFILE": lambda sp: CH(sp).pop("emotion_profile"),
}


def test_example_passes_everything(example):
    assert qc.check_spec_v2(example) == []
    assert qg.check_spec(example) == []


@pytest.mark.parametrize("cid", sorted(MUT))
def test_check_fails_on_mutation_and_passes_on_example(cid, example, clone):
    assert cid not in qc.ids_of(qc.check_spec_v2(example)), "passing fixture must not trip " + cid
    bad = clone(example)
    MUT[cid](bad)
    assert cid in qc.ids_of(qc.check_spec_v2(bad)), "mutation must trip " + cid


def test_cam_files_pass_and_fail(example, clone, tmp_path):
    ok = clone(example)
    (tmp_path / "t.png").write_bytes(b"x")
    ok["camera_plan"][0]["thumbnail"] = "t.png"
    assert "CAM-FILES" not in qc.ids_of(qc.check_camera(ok, tmp_path, files=True))
    ok["camera_plan"][0]["thumbnail"] = "missing.png"
    assert "CAM-FILES" in qc.ids_of(qc.check_camera(ok, tmp_path, files=True))


def test_profile_resolution_inline_extends_and_stretch(example, clone):
    sp = clone(example)
    sp["physics_profiles"] = {"rubber": {"extends": "_human-default", "overrides": {"stretch": {"max_scale": 3.0, "segments": {"forearm": 3.0}}}}}
    CH(sp)["physics_profile"] = "rubber"
    B(sp, 0)["poses"][0]["stretch_events"] = [{"segment": "forearm", "t0": 0, "t1": 1, "max_scale": 2.5}]
    assert "BIO-EXEMPT" not in qc.ids_of(qc.check_bio(sp))
    B(sp, 0)["poses"][0]["stretch_events"][0]["max_scale"] = 4.0
    assert "BIO-EXEMPT" in qc.ids_of(qc.check_bio(sp))


def test_mix_v2_spec_fails_the_new_checks(mix_v2):
    ids = qc.ids_of(qg.check_spec(mix_v2))
    expected = {"BIO-PROFILE", "BIO-PROPORTIONS", "POSE-CATALOGUE", "ATT-MODEL", "ATT-ANCHORS", "ATT-DECLARED",
                "SHADOW-MASS", "SHADOW-CONTACT", "SHADOW-SELF", "SHADOW-SOFT", "TRANS-COUNT", "CAM-PLAN",
                "TEXT-SPEC", "EMO-DECLARED", "EMO-PROFILE"}
    assert expected <= ids, expected - ids


def test_schema_accepts_example_and_rejects_mix_v2(example, mix_v2):
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((REPO / "kb/quality/shot-spec.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    v = jsonschema.Draft202012Validator(schema)
    assert list(v.iter_errors(example)) == []
    assert len(list(v.iter_errors(mix_v2))) > 0


def test_cli_spec_exit_codes():
    ex = subprocess.run([sys.executable, str(TOOLS / "quality_gate.py"), "spec", str(REPO / "kb/quality/shot-spec.example.json")], capture_output=True, text=True)
    mx = subprocess.run([sys.executable, str(TOOLS / "quality_gate.py"), "spec", str(REPO / "kb/quality/fixtures/mix-v2.shot-spec.json")], capture_output=True, text=True)
    assert ex.returncode == 0 and ex.stdout.strip().endswith("PASS")
    assert mx.returncode == 1 and "FAIL [TRANS-COUNT]" in mx.stdout
