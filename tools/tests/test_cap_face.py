# -*- coding: utf-8 -*-
"""Captions never cover a face (owner, 2026-10-25, F-001) and the reading pause (C12): tools/cap_face.py, calm_compose.place_clear_of_faces, read_hold_s.
No browser, no model, no network."""
import json
from pathlib import Path

import calm_compose as cc
import cap_face as CF

REPO = Path(__file__).resolve().parents[2]
SAFE = (54, 270, 1026, 1250)


def _shot(tmp_path, faces, cam0=None, cam1=None, z=2.0, name="S"):
    """A shot folder with the three files cap_face reads: faces = {frame: [x, y]} for one character 'c'."""
    sd = tmp_path / name
    (sd / "out").mkdir(parents=True)
    cam0 = cam0 or {"x": 0, "y": 0, "z": -3.0, "F": 3000.0}
    (sd / "calm.json").write_text(json.dumps({"camera": {"cam0": cam0, "cam1": cam1 or cam0}}), encoding="utf-8")
    (sd / "shot.json").write_text(json.dumps({"actors": [{"id": "c", "z": z}]}), encoding="utf-8")
    frames = [{"f": f, "anchors": {"face_center": xy}} for f, xy in sorted(faces.items())]
    (sd / "out" / "rig-trace.json").write_text(json.dumps({"characters": {"c": {"frames": frames}}}), encoding="utf-8")
    return sd


def test_the_face_box_is_centred_on_the_trace_and_sized_by_the_cameras_scale(tmp_path):
    sd = _shot(tmp_path, {0: [540, 800]})
    (b,) = CF.shot_face_boxes(sd)
    s = 3000.0 / (2.0 + 3.0)                                                   # 600 px a metre
    assert abs(b["w"] - (CF.FACE_W_M * s + 2 * CF.FACE_PAD_PX)) <= 1 and abs(b["h"] - (CF.FACE_H_M * s + 2 * CF.FACE_PAD_PX)) <= 1
    assert abs((b["x"] + b["w"] / 2) - 540) <= 1 and abs((b["y"] + b["h"] / 2) - 800) <= 1


def test_the_box_is_the_union_over_every_frame_and_the_camera_push_grows_it(tmp_path):
    sd = _shot(tmp_path, {0: [500, 800], 10: [580, 820]}, cam0={"x": 0, "y": 0, "z": -3.0, "F": 3000.0}, cam1={"x": 0, "y": 0, "z": -2.0, "F": 3000.0})
    (b,) = CF.shot_face_boxes(sd)
    assert b["x"] < 500 - 60 and b["x"] + b["w"] > 580 + 60 and b["y"] < 800 and b["y"] + b["h"] > 820     # both ends of the move are inside


def test_a_face_off_the_canvas_gives_no_box_and_a_missing_trace_is_an_error(tmp_path):
    assert CF.shot_face_boxes(_shot(tmp_path, {0: [-900, 800]}, name="off")) == []
    try:
        CF.shot_face_boxes(tmp_path / "nothing")
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("a shot with no trace cannot prove a plate is clear")


def test_the_camera_plans_wide_framing_box_is_not_the_box_a_plate_must_clear():
    wide = 0.50 * 1119                                                           # the plan's 0.5 m face framing box in the s02 close-up
    mine = CF.FACE_H_M * 1119 + 2 * CF.FACE_PAD_PX
    assert mine < wide * 0.7


def test_place_plate_keeps_a_clear_default_and_moves_a_covered_one_the_least():
    face = {"x": 380, "y": 596, "w": 306, "h": 330, "char": "hero"}
    x, y = CF.place_plate(738, 292, (171, 870), [face], y_max=1350)
    assert y >= face["y"] + face["h"] and y + 292 <= 1350 and x == 171            # moved straight down, not sideways
    tall = {**face, "h": 420}
    x, y = CF.place_plate(738, 292, (171, 870), [tall], y_max=1250)
    assert y + 292 <= tall["y"]                                                   # no room below inside the safe area: it goes above
    assert CF.place_plate(738, 400, (171, 870), [{**face, "y": 400, "h": 700}], y_max=1250) is None      # nothing fits: None, never a plate on a face


def test_a_default_that_is_already_clear_is_kept():
    face = {"x": 380, "y": 596, "w": 306, "h": 330, "char": "hero"}
    assert CF.place_plate(738, 152, (171, 1010), [face], y_max=1350) == (171, 1010)


def test_place_plate_prefers_a_spot_clear_of_the_hud():
    hud = {"x": 52, "y": 268, "w": 380, "h": 230}
    face = {"x": 380, "y": 700, "w": 300, "h": 300}
    x, y = CF.place_plate(738, 152, (171, 500), [face], [hud], SAFE, 1350)
    assert not CF.intersects({"x": x, "y": y, "w": 738, "h": 152}, hud)


def test_a_join_under_the_grace_does_not_ask_a_plate_to_clear_the_next_shot():
    items = [{"id": "a", "t0": 0, "t1": 5}, {"id": "b", "t0": 4.75, "t1": 9}]
    boxes = {"a": [{"x": 0, "y": 0, "w": 10, "h": 10}], "b": [{"x": 50, "y": 50, "w": 10, "h": 10}]}
    assert [b["item"] for b in CF.window_face_boxes(items, boxes, 3.0, 4.8)] == ["a"]       # 0.05 s of b: ignored
    assert [b["item"] for b in CF.window_face_boxes(items, boxes, 3.0, 5.0)] == ["a", "b"]  # 0.25 s of b: it counts


def test_check_plates_names_the_plate_the_face_and_the_shot():
    face = {"x": 100, "y": 100, "w": 200, "h": 200, "char": "hero", "item": "s02"}
    ok = {"x": 0, "y": 400, "w": 300, "h": 100, "start": 1.0, "end": 2.0, "line": "L02", "text": "ا"}
    bad = {**ok, "y": 250}
    assert CF.check_plates([ok], lambda p: [face]) == []
    (msg,) = CF.check_plates([bad], lambda p: [face])
    assert msg.startswith("CAP-FACE-CLEAR") and "hero" in msg and "s02" in msg and "L02" in msg


def test_the_choice_sequence_maps_a_clips_face_through_its_crop_window():
    it = {"id": "choice", "split": {"top": [{"id": "A", "shot": "s16", "crop": {"x": 0, "y": 40, "w": 500, "dx": 0, "dy": 40}}]}}
    boxes = {"s16": [{"x": 400, "y": 300, "w": 200, "h": 200, "char": "hero"}]}
    (b,) = CF.choice_face_boxes(it, boxes, {"A": "s16"}, 948)
    assert b["x"] == (400 - 0) * (1080 / 500) and abs(b["x"] + b["w"] - 1080) < 1e-6      # clipped at the picture's right edge
    far = {"s16": [{"x": 700, "y": 300, "w": 100, "h": 100, "char": "hero"}]}
    assert CF.choice_face_boxes(it, far, {"A": "s16"}, 948) == []                          # a face outside the crop is not in the picture


# ---------------------------------------------------------------------------------------------- the stage: plates move, sentences keep one place
def _caps(n=3, y=870, h=292):
    return [{"line": "L02", "unit": 0, "text": "جملة", "start": 10.0 + i * 0.5, "end": 10.5 + i * 0.5, "x": 171, "y": y, "w": 738, "h": h, "style": None} for i in range(n)]


class _Ep:
    root = Path(".")


def test_place_clear_of_faces_moves_a_covered_sentence_as_one_and_leaves_a_clear_one(monkeypatch):
    tl = {"items": [{"id": "s02", "kind": "scene", "t0": 9.0, "t1": 14.0}]}
    face = {"x": 380, "y": 596, "w": 306, "h": 330, "char": "hero"}
    monkeypatch.setattr(cc, "face_boxes_by_item", lambda ep, tl_: {"s02": [face]})
    caps = _caps()
    info = cc.place_clear_of_faces(_Ep(), tl, caps, [])
    assert info["plates_moved"] == 3 and len({(c["x"], c["y"]) for c in caps}) == 1          # all three states of the sentence share one place
    assert not any(CF.intersects(c, face) for c in caps) and all(c["moved_for_face"] for c in caps)
    clear = _caps(y=1000, h=152)
    assert cc.place_clear_of_faces(_Ep(), tl, clear, [])["plates_moved"] == 0 and clear[0]["y"] == 1000


def test_a_sentence_over_a_join_with_no_single_place_is_placed_state_by_state(monkeypatch):
    tl = {"items": [{"id": "a", "kind": "scene", "t0": 0.0, "t1": 10.5}, {"id": "b", "kind": "scene", "t0": 10.25, "t1": 20.0}]}
    fa, fb = {"x": 380, "y": 300, "w": 300, "h": 330, "char": "x"}, {"x": 380, "y": 640, "w": 300, "h": 560, "char": "y"}
    monkeypatch.setattr(cc, "face_boxes_by_item", lambda ep, tl_: {"a": [fa], "b": [fb]})
    caps = [{"line": "L", "unit": 0, "text": "ا", "start": 9.0, "end": 10.2, "x": 171, "y": 870, "w": 738, "h": 292, "style": None},
            {"line": "L", "unit": 0, "text": "ا", "start": 10.6, "end": 11.5, "x": 171, "y": 870, "w": 738, "h": 292, "style": None}]
    info = cc.place_clear_of_faces(_Ep(), tl, caps, [])
    assert info["sentences_placed_per_state"] == 1
    assert not CF.intersects(caps[0], fa) and not CF.intersects(caps[1], fb)       # each state clears only the faces on screen during it


def test_no_room_for_a_plate_is_a_hard_stop_with_the_plate_named(monkeypatch):
    tl = {"items": [{"id": "s02", "kind": "scene", "t0": 9.0, "t1": 14.0}]}
    monkeypatch.setattr(cc, "face_boxes_by_item", lambda ep, tl_: {"s02": [{"x": 380, "y": 300, "w": 300, "h": 1000, "char": "hero"}]})
    try:
        cc.place_clear_of_faces(_Ep(), tl, _caps(), [])
    except cc.Fail as e:
        assert e.cid == "CAP-FACE-CLEAR" and "L02" in e.msg
    else:
        raise AssertionError("a plate that cannot clear the face must stop the stage")


# ---------------------------------------------------------------------------------------------- C12: the plan's reading pause
LINES = [{"id": "L1", "speaker": "narrator", "text": "أنتم أمام النافذة العالية، والريح تفتحها."},
         {"id": "L2", "speaker": "narrator", "text": "نعم."}]


def test_a_line_whose_last_clause_is_gone_before_it_can_be_read_gets_a_pause():
    # 'والريح تفتحها.' is a short share of a 4.0 s take; 14 characters need the 1.5 s floor; the room after the line is 0.3 s
    assert cc.read_hold_s(LINES, "L1", 2.5, 0.3, []) > 0.0
    assert cc.read_hold_s(LINES, "L1", 4.0, 3.0, []) == 0.0                         # a long gap needs none
    long_ = [{"id": "L3", "speaker": "narrator", "text": "كل شيء هنا له بطاقة باسمه إلا هذه عليها اسمي أنا"}]
    assert cc.read_hold_s(long_, "L3", 6.0, 0.3, []) == 0.0                          # one long clause is spoken slower than it is read
    assert cc.read_hold_s(LINES, "NOPE", 4.0, 0.3, []) == 0.0


def test_the_pause_is_exactly_what_the_last_plate_is_short_of():
    gap = 0.3
    need = cc.read_hold_s(LINES, "L2", 0.5, gap, [])                                 # 'نعم.': 4 characters, a 1.5 s floor, 0.5 s of voice, 0.28 s of room
    assert abs(need - (1.5 - 0.5 - (gap - 0.02) + cc.READ_HOLD_MARGIN_S)) < 1e-9


def test_the_pause_counts_a_glossed_meaning_the_viewer_must_also_read():
    ent = [{"word": "شيكامو", "language": "Swahili", "meaning_ar": "تحية احترام للكبار", "character": "hero"}]
    ln = [{"id": "L1", "speaker": "hero", "text": "شيكامو، يا عم."}]
    plain = cc.read_hold_s([{**ln[0], "text": "هلا، يا عم."}], "L1", 1.6, 0.3, ent)
    glossed = cc.read_hold_s(ln, "L1", 1.6, 0.3, ent)
    assert glossed >= plain


def test_e01c_timeline_keeps_the_shot_length_and_adds_the_pause_after_it():
    p = REPO / "work" / "episodes" / "E01C" / "timeline.json"
    if not p.is_file():
        return
    for it in json.loads(p.read_text(encoding="utf-8"))["items"]:
        if "read_hold" in it:
            assert abs(it["dur"] - it["dur_shot"] - it["read_hold"]) < 2e-3 and it["read_hold"] >= 0


def test_an_engraved_plate_stays_on_its_brass_plate_and_ends_when_the_next_shot_begins(monkeypatch):
    """E01C, 2026-10-25: the engraving ran 0.11 s into the page turn onto the next shot, over the 0.1 s grace, so the sentence was thrown 206 px down and crossed the plate's border."""
    tl = {"items": [{"id": "day", "kind": "card", "t0": 6.75, "t1": 11.75}, {"id": "s02", "kind": "scene", "t0": 11.5, "t1": 17.0}]}
    monkeypatch.setattr(cc, "face_boxes_by_item", lambda ep, tl_: {"s02": [{"x": 380, "y": 596, "w": 306, "h": 700, "char": "hero"}]})
    caps = [{"line": "W01", "unit": 0, "text": "ا", "start": s, "end": e, "x": 103, "y": 760, "w": 873, "h": 292, "style": "object"} for s, e in ((10.0, 10.6), (10.6, 11.61))]
    info = cc.place_clear_of_faces(_Ep(), tl, caps, [])
    assert info["plates_moved"] == 0 and all(c["y"] == 760 and not c.get("moved_for_face") for c in caps)
    assert caps[-1]["end"] == 11.5 and caps[0]["end"] == 10.6


def test_a_calm_stage_leaves_a_state_record_the_heal_guard_can_read(tmp_path):
    """E01C, 2026-10-25: no STATE.json meant heal.py guard refused every honest re-run of the gate as 'edited by hand'."""
    class _W:
        work = tmp_path / "E99"
    _W.work.mkdir()
    cc.record_stage(_W, "captions")
    cc.record_stage(_W, "gate")
    st = __import__("json").loads((_W.work / "STATE.json").read_text(encoding="utf-8"))
    assert set(st["stages"]) == {"captions", "gate"} and st["stages"]["gate"]["at"] and st["stages"]["gate"]["status"] == "ok"


def test_a_plate_moved_off_a_face_also_keeps_clear_of_the_nj_mark():
    # E03 2026-10-28: plates lifted above a face landed at y 384, 6 px under the mark, and WATERMARK-CLEAR failed the episode.
    import watermark as WM
    mark = cc.mark_avoid_box()
    face = {"x": 100, "y": 676, "w": 880, "h": 400}
    pos = CF.place_plate(847, 292, (117, 966), [face, mark], None, (54, 270, 1026, 1250), 1250)
    assert pos is not None
    plate = {"x": pos[0], "y": pos[1], "w": 847, "h": 292}
    assert not WM.clear_problems(None, [plate], [], [], [])


def test_an_event_shot_gets_the_action_ceilings_and_other_shots_keep_the_calm_ones():
    # format v2 (the owner 2026-10-28): the lid sliding shut and the mug falling, with a character speaking over them
    import qg_checks as qc
    m = {"motion_coverage": 0.40, "motion_clusters": 9.0}
    assert {x.split()[0] for x in qc.check_calm_shot(m)} >= {"FAIL"} and len(qc.check_calm_shot(m)) == 2
    assert qc.check_calm_shot(m, event=True) == []
    assert len(qc.check_calm_shot({"motion_coverage": 0.50, "motion_clusters": 11.0}, event=True)) == 2
