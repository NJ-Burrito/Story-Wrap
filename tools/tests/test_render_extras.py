"""Render extras on tiny synthetic frames: text-box contrast and texture, per-beat colour script."""
import numpy as np
import qg_checks as qc

SCALE = 0.5
BOX = {"x": 300, "y": 900, "w": 400, "h": 120}      # 1080x1920 px -> (150,450,200,60) at half size


def frame(bg=(255, 255, 255), glyph=(0, 0, 0), halftone=0, seed=0):
    f = np.zeros((960, 540, 3), np.uint8); f[:] = bg
    rng = np.random.default_rng(seed)
    if halftone:
        yy, xx = np.mgrid[:960, :540]
        chk = ((xx // 3 + yy // 3) % 2).astype(float) * 2 - 1
        f = np.clip(f.astype(float) + chk[..., None] * halftone, 0, 255).astype(np.uint8)
    mask = np.zeros((960, 540), bool)
    for k in range(6):
        mask[470 + k * 8: 475 + k * 8, 160:340] = True       # glyph bars inside the box
    f[mask] = glyph
    return f, mask


def run(f, mask=None, h=60):
    c, tx, sh, used = qc.text_box_metrics(f, BOX, h, SCALE, mask)
    return qc.check_text_render([{"contrast": c, "texture": tx, "share": sh, "mask": used}] * 5, h, "t")


def test_text_contrast_pass_and_fail_with_mask():
    f, m = frame(); assert run(f, m) == []
    f, m = frame(glyph=(215, 215, 215)); assert "REND-TEXT-CONTRAST" in qc.ids_of(run(f, m))


def test_text_contrast_pass_and_fail_fallback_two_mode():
    f, _ = frame(); assert "REND-TEXT-CONTRAST" not in qc.ids_of(run(f))
    f, _ = frame(glyph=(215, 215, 215)); assert "REND-TEXT-CONTRAST" in qc.ids_of(run(f))


def test_text_texture_pass_and_fail_with_mask():
    f, m = frame(); assert "REND-TEXT-TEXTURE" not in qc.ids_of(run(f, m))
    f, m = frame(bg=(200, 200, 200), halftone=40); assert "REND-TEXT-TEXTURE" in qc.ids_of(run(f, m))


def test_text_texture_fallback():
    f, _ = frame(bg=(230, 230, 230), glyph=(10, 10, 10)); assert "REND-TEXT-TEXTURE" not in qc.ids_of(run(f))
    f, _ = frame(bg=(200, 200, 200), glyph=(0, 0, 0), halftone=40); assert "REND-TEXT-TEXTURE" in qc.ids_of(run(f))


def test_large_text_uses_the_3_to_1_floor():
    f, m = frame(glyph=(120, 120, 120))                   # about 4:1 on white
    assert "REND-TEXT-CONTRAST" in qc.ids_of(run(f, m, h=40))
    assert "REND-TEXT-CONTRAST" not in qc.ids_of(run(f, m, h=60))


def test_colour_stats_hue():
    red = np.zeros((8, 8, 3), np.uint8); red[..., 0] = 200
    blue = np.zeros((8, 8, 3), np.uint8); blue[..., 2] = 200
    assert qc._hdiff(qc.colour_stats([red])["hue"], 0) < 5
    assert abs(qc.colour_stats([blue])["hue"] - 240) < 5


SPEC = {"beats": [{"id": "b1", "emotion": {"primary": "calm"}}, {"id": "b2", "emotion": {"primary": "fear"}}]}


def test_colour_script_moves_between_emotions_passes():
    st = [{"hue": 30, "sat": 0.5, "val": 0.6, "luma": 0.4}, {"hue": 200, "sat": 0.3, "val": 0.4, "luma": 0.2}]
    assert qc.check_colour_script(st, SPEC) == []


def test_colour_script_flat_fails():
    st = [{"hue": 140, "sat": 0.20, "val": 0.6, "luma": 0.30}, {"hue": 138, "sat": 0.21, "val": 0.6, "luma": 0.31}]
    assert "REND-COLOUR" in qc.ids_of(qc.check_colour_script(st, SPEC))      # the Mix v2 case: hue 138..140


def test_colour_script_declared_target():
    sp = {"beats": [{"id": "b1", "emotion": {"primary": "calm"}, "emotion_track": {"colour": {"target": {"hue_deg": 30, "sat": 0.5}}}}]}
    assert qc.check_colour_script([{"hue": 40, "sat": 0.45, "val": 0.5, "luma": 0.3}], sp) == []
    assert "REND-COLOUR" in qc.ids_of(qc.check_colour_script([{"hue": 200, "sat": 0.45, "val": 0.5, "luma": 0.3}], sp))
