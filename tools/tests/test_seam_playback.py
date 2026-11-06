"""SEAM (R-381) and PLAYBACK (R-382): one passing and one failing synthetic fixture each."""
import numpy as np
import pytest
from PIL import Image
import qg_checks as qc

W, H = 200, 300
HU = 100.0


def mask_png(path, draw):
    a = np.zeros((H, W), np.uint8)
    draw(a)
    Image.fromarray(a).save(path)
    return path.name


def limb_outlines(a):              # two vertical outline strokes of a continuous arm: run ALONG the bone
    a[60:240, 80:83] = 255
    a[60:240, 120:123] = 255


def with_cross(a):                 # plus a horizontal stroke closing the upper arm at the elbow: a seam line
    limb_outlines(a)
    a[150:153, 80:123] = 255


def trace_for(tmp_path, draw, seams, overlaps=None, name="m.png"):
    f = {"f": 0, "t": 0.0, "line_mask": mask_png(tmp_path / name, draw), "seams": seams}
    if overlaps is not None:
        f["overlaps"] = overlaps
    return {"fps": 24, "canvas": {"w": W, "h": H}, "characters": {"hero": {"head_unit_px": HU, "frames": [f]}}}


ELBOW = {"id": "elbow_L", "parts": ["upper_arm_L", "forearm_L"], "at": [101, 150], "from": [101, 60], "to": [101, 240]}
NECK = {"id": "head_neck", "parts": ["head", "torso"], "at": [101, 150], "axis": [0, 1], "kind": "head-neck", "via": "neck"}


def ids(tr, tmp_path):
    return qc.ids_of(qc.rig_seams(tr, tmp_path))


def test_seam_pass_limb_outline_only(tmp_path):
    assert ids(trace_for(tmp_path, limb_outlines, [ELBOW]), tmp_path) == set()


def test_seam_fail_stroke_across_joint(tmp_path):
    assert ids(trace_for(tmp_path, with_cross, [ELBOW]), tmp_path) == {"SEAM-CROSS"}


def test_seam_declared_overlap_waives(tmp_path):
    tr = trace_for(tmp_path, with_cross, [ELBOW], overlaps=["elbow_L"])
    assert ids(tr, tmp_path) == set()
    tr = trace_for(tmp_path, with_cross, [ELBOW], overlaps=["forearm_L|upper_arm_L"], name="m2.png")
    assert ids(tr, tmp_path) == set()


def test_seam_mask_scale_is_honoured(tmp_path):
    def small(a):
        a[75:76, 40:62] = 255      # same cross stroke at half resolution
    tr = trace_for(tmp_path, small, [ELBOW])
    Image.fromarray(np.where(np.arange(H)[:, None] == 75, 255, 0).astype(np.uint8)[:, :1].repeat(W, 1)[::2, ::2]).save(tmp_path / "m.png")
    arr = np.zeros((H // 2, W // 2), np.uint8); arr[75:77, 40:62] = 255
    Image.fromarray(arr).save(tmp_path / "m.png")
    assert ids(tr, tmp_path) == {"SEAM-CROSS"}


def test_headneck_pass_when_joined_through_neck(tmp_path):
    assert ids(trace_for(tmp_path, limb_outlines, [NECK]), tmp_path) == set()


def test_headneck_fail_outline_between_head_and_body(tmp_path):
    tr = trace_for(tmp_path, with_cross, [NECK], overlaps=["head|torso"])   # overlaps cannot waive the head join
    assert ids(tr, tmp_path) == {"SEAM-HEADNECK"}


def test_headneck_fail_without_neck_shape(tmp_path):
    n = {k: v for k, v in NECK.items() if k != "via"}
    assert ids(trace_for(tmp_path, limb_outlines, [n]), tmp_path) == {"SEAM-HEADNECK"}


def test_seam_nodata_when_mask_missing(tmp_path):
    tr = trace_for(tmp_path, limb_outlines, [ELBOW])
    (tmp_path / "m.png").unlink()
    assert ids(tr, tmp_path) == {"SEAM-NODATA"}


def test_seam_skipped_without_seams(tmp_path):
    tr = trace_for(tmp_path, with_cross, [])
    assert qc.rig_seams(tr, tmp_path) == []


def test_seam_runs_inside_check_rig(tmp_path):
    assert "SEAM-CROSS" in qc.ids_of(qc.check_rig(trace_for(tmp_path, with_cross, [ELBOW]), None, None, tmp_path))


# ------------------------------------------------------------------ PLAYBACK
GOOD = """<body><section class="panel" data-tab="mix"><video src="mix.mp4" controls loop muted></video>
<details><summary>Live editor</summary><canvas id="liveCanvas"></canvas></details></section>
<section class="panel" data-tab="notes"><p>text only</p></section>
<script>const c=document.getElementById('liveCanvas');function loop(){requestAnimationFrame(loop)}</script></body>"""

BAD_LIVE = """<body><section class="panel" data-tab="mix"><video src="mix.mp4" controls></video>
<canvas id="mixCanvas" width="1080" height="1920"></canvas></section>
<script>const c=document.getElementById('mixCanvas');function tick(){renderAt(t);requestAnimationFrame(tick)}tick()</script></body>"""

BAD_NOVIDEO = """<body><section class="panel" data-tab="mix3"><canvas id="c3" hidden></canvas><p>no video</p></section></body>"""


def test_playback_static_pass():
    assert qc.check_preview_static(GOOD) == []


def test_playback_static_fail_live_painter_default():
    assert qc.ids_of(qc.check_preview_static(BAD_LIVE)) == {"PLAYBACK-AUTOPLAY"}


def test_playback_static_fail_no_video():
    assert qc.ids_of(qc.check_preview_static(BAD_NOVIDEO)) == {"PLAYBACK-VIDEO"}


def test_playback_static_scans_each_tab_separately():
    html = GOOD.replace("</body>", BAD_LIVE.replace("<body>", "").replace("data-tab=\"mix\"", "data-tab=\"mix9\"").replace("mixCanvas", "m9") + "</body>")
    fails = qc.check_preview_static(html)
    assert len(fails) == 1 and "mix9" in fails[0]


def test_playback_dynamic_thresholds():
    assert qc.dynamic_issues([16.6] * 200, [20], []) == []
    assert qc.ids_of(qc.dynamic_issues([16.6] * 90 + [280] * 10, [150], ["TypeError x"])) == {
        "PLAYBACK-FRAMETIME", "PLAYBACK-LONGTASK", "PLAYBACK-ERROR"}


def test_preview_max_tabs():
    def page(n):
        tabs = ",".join('{id: "t%d", label: "T%d"}' % (i, i) for i in range(n))
        return "<body>" + "".join('<section class="panel" data-tab="t%d"><p>x</p></section>' % i for i in range(n)) + "<script>const TABS = [" + tabs + "];</script></body>"
    assert qc.check_preview_static(page(4)) == []
    assert qc.ids_of(qc.check_preview_static(page(5))) == {"PREVIEW-MAX-TABS"}
