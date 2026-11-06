"""Hands, props and writing checks (R-383..R-392): a clean synthetic trace passes; one mutation per check id fails that id."""
import copy
import json
import subprocess
import sys
import qg_checks as qc
from conftest import TOOLS

N = 60
FING = ["index", "middle", "ring", "little"]
TOPO = {"fingers": 4, "order": ["thumb", "index", "middle", "ring", "little"]}


def make_trace():
    frames = []
    for i in range(N):
        writing = 6 <= i < 46
        k = max(0, i - 6)
        x = 700.0 - 5.0 * k                         # nib moves leftwards (Arabic, RTL)
        nib = [x, 500.0]
        fr = {
            "f": i, "t": i / 24,
            "hand_pose": {
                "L": {"id": "tripod-pen-L", "contact_kind": "pen-tip", "pinch": False, "topo": TOPO, "orient_deg": 20.0,
                      "wrist_px": [760.0 - k, 560.0], "holding": "pen",
                      "fingers": {n: [30.0, 40.0, 20.0] for n in FING},
                      "grip_contacts": {"thumb": 3.0, "index": 2.0, "middle": 4.0},
                      "grip_layers": {"front": ["paper", "hand-L", "pen", "finger-index-L"]}},
                "R": {"id": "pinch-tag-R", "contact_kind": "pinch", "pinch": True, "topo": TOPO, "orient_deg": 5.0,
                      "wrist_px": [500.0, 600.0], "fingers": {n: [20.0, 20.0, 10.0] for n in FING}},
            },
            "layer_order": {"angle": "front", "order": ["paper", "hand-L", "pen", "finger-index-L", "thumb-R"]},
            "props": [{"id": "tag", "faces": {"front": {"print": []}, "back": {"print": []}}, "facing": "front",
                       "marks": [{"id": "ink1", "face": "front", "kind": "ink", "drawn": writing or i >= 46}]}],
            "writing": {"prop": "tag", "active": writing, "direction": "rtl", "nib_face": "front", "nib_px": nib,
                        "paper_px": [nib[0], nib[1] + 1.0], "nib_gap_px": 1.0, "on_paper": True,
                        "drawn_to_px": list(nib) if writing else [700.0 - 5.0 * 39, 500.0],
                        "ink_len_px": float(min(k, 39) * 5.0) if i >= 6 else 0.0},
        }
        frames.append(fr)
    # R hand: a proper blend into an open hand at frame 40..44, then the new grip
    for i in range(36, 40):
        frames[i]["hand_pose"]["R"]["blend"] = {"to_id": "startle-open-R", "to_kind": "palm", "k": (i - 35) / 4}
    for i in range(40, N):
        hp = frames[i]["hand_pose"]["R"]
        hp.update({"id": "startle-open-R", "contact_kind": "palm", "pinch": False})
    return {"fps": 24, "characters": {"hero": {"frames": frames}}}


def ids(tr):
    return qc.ids_of(qc.check_hands_writing(tr))


def fr(tr, i):
    return tr["characters"]["hero"]["frames"][i]


def test_clean_passes():
    assert qc.check_hands_writing(make_trace()) == []
    assert not {"HAND-TOPO", "HAND-SIDE", "HAND-SWAP", "PROP-FACE", "WRITE-REVEAL", "NIB-CONTACT", "LAYER-GRIP"} & qc.ids_of(qc.check_rig(make_trace()))


def test_hand_topo_finger_count():
    tr = make_trace(); fr(tr, 10)["hand_pose"]["L"]["topo"] = {"fingers": 5, "order": TOPO["order"]}
    assert "HAND-TOPO" in ids(tr)


def test_hand_topo_single_frame_jump():
    tr = make_trace()
    for i in range(20, N):
        fr(tr, i)["hand_pose"]["L"]["fingers"]["index"] = [90.0, 40.0, 20.0]   # 60 deg in one frame
    assert "HAND-TOPO" in ids(tr)


def test_hand_topo_jump_waived_by_smear_or_cut():
    tr = make_trace()
    for i in range(20, N):
        fr(tr, i)["hand_pose"]["L"]["fingers"]["index"] = [90.0, 40.0, 20.0]
    fr(tr, 20)["smear"] = True
    assert "HAND-TOPO" not in ids(tr)


def test_hand_topo_axis_and_wrist_jump():
    tr = make_trace()
    for i in range(30, N):
        fr(tr, i)["hand_pose"]["R"]["orient_deg"] = 60.0                        # 55 deg
    assert "HAND-TOPO" in ids(tr)
    tr = make_trace()
    for i in range(30, N):
        fr(tr, i)["hand_pose"]["R"]["wrist_px"] = [500.0, 800.0]                 # 200 px
    assert "HAND-TOPO" in ids(tr)


def test_hand_side():
    tr = make_trace()
    for i in range(N):
        fr(tr, i)["hand_pose"]["R"]["id"] = "flat-support-L" if i >= 40 else fr(tr, i)["hand_pose"]["R"]["id"]
    assert "HAND-SIDE" in ids(tr)
    for i in range(40, N):
        fr(tr, i)["hand_pose"]["R"]["mirrored"] = True
    assert "HAND-SIDE" not in ids(tr)


def test_hand_swap_without_blend():
    tr = make_trace()
    for i in range(36, 40):
        del fr(tr, i)["hand_pose"]["R"]["blend"]
    assert "HAND-SWAP" in ids(tr)


def test_hand_swap_contact_kind_only():
    tr = make_trace()
    for i in range(30, N):
        fr(tr, i)["hand_pose"]["L"]["contact_kind"] = "heel"                      # the Mix v4 heel -> pinch snap
    assert "HAND-SWAP" in ids(tr)


def test_prop_face_hidden_face():
    tr = make_trace()
    for i in range(N):
        fr(tr, i)["props"][0]["facing"] = "back"                                   # camera sees the back, ink on the front
    assert "PROP-FACE" in ids(tr)


def test_prop_face_nib_on_other_face():
    tr = make_trace()
    for i in range(6, 46):
        fr(tr, i)["writing"]["nib_face"] = "back"                                  # writer is behind the card
    assert "PROP-FACE" in ids(tr)


def test_write_reveal_ink_not_at_nib():
    tr = make_trace()
    fr(tr, 20)["writing"]["drawn_to_px"] = [900.0, 500.0]
    assert "WRITE-REVEAL" in ids(tr)


def test_write_reveal_wrong_direction():
    tr = make_trace()
    for i in range(6, 46):
        w = fr(tr, i)["writing"]; w["nib_px"] = [300.0 + 5.0 * (i - 6), 500.0]; w["drawn_to_px"] = list(w["nib_px"])
        w["paper_px"] = [w["nib_px"][0], 501.0]
    assert "WRITE-REVEAL" in ids(tr)


def test_write_reveal_ink_without_nib():
    tr = make_trace()
    fr(tr, 50)["writing"]["ink_len_px"] = 400.0
    assert "WRITE-REVEAL" in ids(tr)


def test_nib_contact():
    tr = make_trace()
    fr(tr, 15)["writing"]["nib_gap_px"] = 25.0
    assert "NIB-CONTACT" in ids(tr)


def test_layer_grip_order():
    tr = make_trace()
    fr(tr, 12)["layer_order"]["order"] = ["hand-L", "pen", "finger-index-L", "paper"]   # paper drawn above the writing hand
    assert "LAYER-GRIP" in ids(tr)


def test_layer_grip_not_held_and_undeclared():
    tr = make_trace()
    fr(tr, 12)["hand_pose"]["L"]["grip_contacts"]["thumb"] = 40.0
    assert "LAYER-GRIP" in ids(tr)
    tr = make_trace()
    del fr(tr, 12)["hand_pose"]["L"]["grip_layers"]
    assert "LAYER-GRIP" in ids(tr)


def test_cli_hands(tmp_path):
    good, bad = make_trace(), make_trace()
    fr(bad, 15)["writing"]["nib_gap_px"] = 25.0
    pg, pb = tmp_path / "g.json", tmp_path / "b.json"
    pg.write_text(json.dumps(good)); pb.write_text(json.dumps(bad))
    ok = subprocess.run([sys.executable, str(TOOLS / "quality_gate.py"), "hands", str(pg)], capture_output=True, text=True)
    ko = subprocess.run([sys.executable, str(TOOLS / "quality_gate.py"), "hands", str(pb)], capture_output=True, text=True)
    assert ok.returncode == 0 and "PASS" in ok.stdout, ok.stdout + ok.stderr
    assert ko.returncode == 1 and "NIB-CONTACT" in ko.stdout
