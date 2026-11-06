"""R-380 2D look: flat cel + ink line passes; smooth lit-volume ramps and no line fail."""
import numpy as np
import qg_checks as qc

H, W = 960, 540


def cel(ink=True):
    f = np.full((H, W), 0.55, np.float32)
    for k in range(20):                      # flat shapes with hard edges, 2 tone steps
        for j in range(5):
            y0, x0 = 20 + k * 46, 20 + j * 104
            f[y0:y0 + 40, x0:x0 + 96] = 0.25 + 0.2 * ((k + j) % 2)
            if ink:                          # 3 px dark outline around every shape
                f[y0:y0 + 3, x0:x0 + 96] = 0.02; f[y0 + 37:y0 + 40, x0:x0 + 96] = 0.02
                f[y0:y0 + 40, x0:x0 + 3] = 0.02; f[y0:y0 + 40, x0 + 93:x0 + 96] = 0.02
    return f


def volume():
    x = np.linspace(0, 1, W, dtype=np.float32)[None, :]
    y = np.linspace(0, 1, H, dtype=np.float32)[:, None]
    return (0.5 + 0.4 * np.sin(2 * np.pi * (3 * x + 2 * y))).astype(np.float32)   # smooth lit ramps, no edges


def run(frames):
    return qc.check_look2d(qc.look2d_metrics(frames))


def test_cel_with_ink_passes():
    assert run([cel()] * 3) == []


def test_smooth_volume_fails_ramp_and_line():
    ids = qc.ids_of(run([volume()] * 3))
    assert {"LOOK2D-RAMP", "LOOK2D-LINE"} <= ids


def test_cel_without_ink_loses_line_share():
    m = qc.look2d_metrics([cel(ink=False)] * 2)
    assert m["hard_edge"] < qc.look2d_metrics([cel()] * 2)["hard_edge"]


def test_soft_shadow_spec_fails_flat_check(example, clone):
    sp = clone(example)
    assert "SHADOW-FLAT" not in qc.ids_of(qc.check_shadow_flat(sp))
    sp["beats"][0]["cast_shadows"][0]["edge"] = "soft"
    assert "SHADOW-FLAT" in qc.ids_of(qc.check_shadow_flat(sp))
    sp["beats"][0]["cast_shadows"][0].update(edge="hard", blur_px=12)
    assert "SHADOW-FLAT" in qc.ids_of(qc.check_shadow_flat(sp))
