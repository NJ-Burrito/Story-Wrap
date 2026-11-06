"""Shared drawing code (tools/render: geom2d.js, svgctx.js Ink, face.js hooks and range, sheets.js): node harness without a browser,
plus browser tests that skip cleanly where playwright is not installed."""
import json
import re
import shutil
import subprocess
import sys

import pytest

from conftest import REPO, TOOLS


@pytest.fixture(scope="module")
def h():
    if not shutil.which("node"):
        pytest.skip("node not installed")
    r = subprocess.run(["node", str(TOOLS / "tests" / "face_hooks_harness.js")], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_geom2d_exports_helpers_and_fd_slot(h):
    assert h["helpers"] and h["fd_slot"]
    assert abs(h["ik_len"] - 1) < 1e-6


def test_expression_range_widens_sheet_not_film(h):
    assert h["open_range15"] > h["open_range1"] and h["open_color"] == h["open_range1"]


def test_face_hooks_run_in_layer_order(h):
    # "behind" and "skin" belong to the head drawer (sheets.js); the face drawer runs the rest in FACE_LAYERS order
    assert h["order"] == [l for l in h["layers"] if l not in ("behind", "skin")]
    assert h["layers"].index("beard") < h["layers"].index("mouth") < h["layers"].index("moustache") < h["layers"].index("spectacles") < h["layers"].index("hair") < h["layers"].index("headwear")


def test_small_detail_drawn_only_with_open_mouth(h):
    assert h["detail_open"] > h["detail_closed"]


def test_ink_helpers(h):
    assert h["ink"]["brush"] and h["ink"]["hatch"] and h["ink"]["cross"] == 2 and h["ink"]["spotted"]


def test_generic_files_have_no_workaround_globals():
    for name in ("sheets.js", "face.js"):
        src = (REPO / "tools/render" / name).read_text(encoding="utf-8")
        assert "hijab" not in src.replace("hijab_layer_order", "")
    assert "geom2d.js" in (TOOLS / "sheets.py").read_text(encoding="utf-8")
    assert "geom2d.js" in (REPO / "tools/templates/shot/shot.json").read_text(encoding="utf-8")


def test_world_sheet_wording_comes_from_module():
    src = (REPO / "tools/render/sheets.js").read_text(encoding="utf-8")
    assert not re.search(r"shelves|stone, wood, carving, brass", src)
    assert "sheet.labels" in src




def _run_sheets(kind, mid, tmp_path):
    pytest.importorskip("playwright")
    r = subprocess.run([sys.executable, str(TOOLS / "sheets.py"), kind, mid, "--no-png", "--out", str(tmp_path)], capture_output=True, text=True, encoding="utf-8")
    return r


@pytest.mark.parametrize("mid", ["hero", "rival"])
def test_character_sheets_render(mid, tmp_path):
    r = _run_sheets("character", mid, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    meta = json.loads((tmp_path / "sheets.json").read_text(encoding="utf-8"))
    ids = [s["id"] for s in meta["sheets"]]
    assert ids[:5] == ["01-shapes", "02-mannequin", "03-sketch", "04-turnaround", "05-expressions"] and "07-face" in ids and "08-props" in ids
    assert "angle_files" in meta["module_summary"]


def test_world_sheets_render_with_neutral_labels(tmp_path):
    r = _run_sheets("world", "world-a", tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    ids = [s["id"] for s in json.loads((tmp_path / "sheets.json").read_text(encoding="utf-8"))["sheets"]]
    assert ids == ["w1-establishing", "w2-locations", "w3-props", "w4-materials"]
