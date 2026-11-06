# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""ART-PROPORTION reference values (owner, 2026-10-25: the art book is the reference, every time).

Writes catalogue/characters/<id>/artbook-proportions.json from the data the APPROVED art-book sheets are drawn from: the character module's `data.hand_model` and
`data.face` (tools/render/characters/<id>.js, exactly what tools/sheets.py draws on sheets 04 turnaround, 06 hands and 07 face) and the approved sheets folder's
sheets.json (module_sha and the SVG hashes are recorded as provenance). Everything is stored per head height, so a body part cannot grow unnoticed:

    hand length  = wrist to the tip of the straight middle finger     hand width = knuckle span, index to little
    finger radius = first finger segment                              nose / lips / eyes = the face file's own sizes

The film's rig trace (render/hands.js artMeasure) reports the same quantities as DRAWN; qg_checks.rig_art_proportion compares them (tolerance 8 %).

    uv run tools/artbook_proportions.py            # all three
    uv run tools/artbook_proportions.py hero
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APPROVED = {"hero": "v6", "guide": "v2", "lead": "v2", "partner": "v2"}
# the hand model the approved sheets were drawn from, where the module has moved on since: Lead's v2 sheets carry hand 0.85 HU = the v1.0 model; hand-model v3 is a 1.1176x sketch-stage draft
HAND_OVERRIDE = {"lead": "v1/hands/hand-model.json"}   # approved art-book sheet version per character (owner, 2026-10-25)
TOLERANCE_PCT = 8.0


def _data_files(cid: str) -> dict:
    src = (ROOT / "tools" / "render" / "characters" / f"{cid}.js").read_text(encoding="utf-8")
    m = re.search(r'data:\s*\{[^}]*?hand_model:\s*"([^"]+)"', src, re.S)
    f = re.search(r'data:\s*\{[^}]*?face:\s*"([^"]+)"', src, re.S)
    if not (m and f):
        raise SystemExit(f"{cid}: data.face / data.hand_model not found in the module")
    return {"hand_model": m.group(1), "face": f.group(1)}


def measure(cid: str) -> dict:
    files = _data_files(cid)
    files["hand_model"] = HAND_OVERRIDE.get(cid, files["hand_model"])
    cdir = ROOT / "catalogue" / "characters" / cid
    hm = json.loads((cdir / files["hand_model"]).read_text(encoding="utf-8"))
    fc = json.loads((cdir / files["face"]).read_text(encoding="utf-8"))
    ch = json.loads((cdir / "character.json").read_text(encoding="utf-8"))
    head = float(ch["proportions_hu"]["head_h"])
    k = 1.0   # the model's numbers are already in head units (a model with scale_vs_v1 has it inside them)
    kn, lp = hm["knuckles_ur"], hm["phalanges_hu"]["middle"]
    length = (kn["middle"][0] + sum(lp)) * k
    width = abs(kn["index"][1] - kn["little"][1]) * k
    nose, lips, eyes = fc["nose"], fc["lips"], fc["eyes"]
    hu = {
        "hand_len_hu": length, "hand_w_hu": width, "finger_r_hu": hm["radii_hu"]["finger"][0],
        "nose_w_hu": 2 * nose["wing_x"], "nose_len_hu": nose["tip_y"] - nose["bridge_top_y"],
        "lips_w_hu": 2 * lips["half_w"], "lips_t_hu": lips["upper_t"] + lips["lower_t"],
        "eye_w_hu": eyes["w"], "eye_h_hu": eyes["h"],
    }
    sj = cdir / APPROVED[cid] / "sheets" / "sheets.json"
    sheets = json.loads(sj.read_text(encoding="utf-8"))
    shas = {s["id"]: s["svg_sha"] for s in sheets["sheets"] if s["id"] in ("04-turnaround", "06-hands-grips", "07-face")}
    return {
        "character": cid, "approved_sheet_version": APPROVED[cid], "sheets_module_sha": sheets.get("module_sha"), "sheets_svg_sha": shas,
        "derived_from": {"hand_model": files["hand_model"], "face": files["face"], "character": "character.json"},
        "head_h_hu": head, "catalogue_hand_hu": ch["proportions_hu"]["hand"], "hand_model_scale": k,
        "values_hu": {a: round(b, 4) for a, b in hu.items()},
        "per_head": {a: round(b / head, 4) for a, b in hu.items()},
        "tolerance_pct": TOLERANCE_PCT,
        "rule": "CLAUDE.md: the art book is the reference, every time. Close-ups read through the camera, never through scale.",
    }


def main(argv: list[str]) -> int:
    for cid in (argv or list(APPROVED)):
        out = measure(cid)
        p = ROOT / "catalogue" / "characters" / cid / "artbook-proportions.json"
        p.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(cid, p.relative_to(ROOT), json.dumps(out["per_head"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
