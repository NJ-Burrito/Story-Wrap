# -*- coding: utf-8 -*-
"""Captions never cover a face (owner, 2026-10-25, finding F-001 on E01 calm). Pure geometry; no browser, no model.

The plate of a sentence is placed OUTSIDE the face boxes of every shot that is on screen while the plate is up, and CAP-FACE-CLEAR checks it again at the gate.

  shot_face_boxes(shot_dir)                      the shot's face boxes in 1080x1920 screen px: one per character, the UNION over every frame of the rig trace
  window_face_boxes(items, shot_boxes, t0, t1)   the face boxes of every timeline item that overlaps the window (a plate that crosses a join clears both shots)
  choice_face_boxes(item, shots_root, ep_id)     the face boxes inside the choice sequence's top half (crop windows mapped onto the 1080 x TOP_H picture)
  place_plate(w, h, default, avoid, soft, safe)  the nearest legal position to the default; None when nothing fits
  check_plates(plates, boxes_for)                CAP-FACE-CLEAR problems: any plate that intersects a face box while it is on screen

Where the box comes from. Centre: `anchors.face_center` of every trace frame (screen px of the frame, written by tools/render/trace-multi.js, already inside the camera
move). Size: FACE_W_M x FACE_H_M metres of the world at that frame's camera scale s = F / (z_actor - z_camera) (the same scale tools/calm.py screen_box uses for the camera
plan's own face box), plus FACE_PAD_PX on every side. The camera plan's `safe_boxes` face box (0.42 x 0.50 m) is a framing box, wide enough to hold shoulders, so it is NOT the
box a caption must clear: in a close-up it spans y 522 to 1082 of a 1920 px frame whose safe area ends at 1250, which leaves no legal place for any plate.
The box is the FACE: skin, brows and eyes, mouth, chin, with the hairline or cap band; not the covering around it (the hijab drape, the top of a turban). Measured on the
E01C frames at 14 s (Hero, s02, 1119 px/m), 36 s (Guide, s06, about 845 px/m) and 70 s (Lead, s14): the face is 0.12, 0.22 and 0.13 m wide and 0.165, 0.20 and 0.215 m tall
(Guide's with the spectacles and brow). FACE_H_M rounds the tallest up to 0.24 m, FACE_W_M the widest up to 0.24 m; the 24 px pad is the margin for the plate's own dark outline."""
from __future__ import annotations

import json
from pathlib import Path

FACE_W_M = 0.24            # face width, metres of world (measured on three characters, see the module docstring)
FACE_H_M = 0.24            # face height
FACE_PAD_PX = 24           # clear space kept around the head
HUD_PAD_PX = 12
CANVAS = (1080, 1920)
X_STEP, Y_STEP = 18, 6


def _read(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def _lerp(a, b, u):
    return a + (b - a) * u


def box_union(boxes: list[dict]) -> dict | None:
    if not boxes:
        return None
    x0, y0 = min(b["x"] for b in boxes), min(b["y"] for b in boxes)
    x1, y1 = max(b["x"] + b["w"] for b in boxes), max(b["y"] + b["h"] for b in boxes)
    return {"x": round(x0), "y": round(y0), "w": round(x1 - x0), "h": round(y1 - y0)}


def shot_face_boxes(shot_dir) -> list[dict]:
    """[{char, x, y, w, h}] in screen px, the union over every frame. A character whose face is never inside the canvas gives no box. No trace means no boxes (the caller
    reports it: a shot without a trace cannot prove a plate is clear)."""
    sd = Path(shot_dir)
    trace_p, calm_p, shot_p = sd / "out" / "rig-trace.json", sd / "calm.json", sd / "shot.json"
    if not (trace_p.is_file() and calm_p.is_file() and shot_p.is_file()):
        raise FileNotFoundError(f"{sd}: rig-trace.json, calm.json and shot.json are needed for the face boxes")
    tr, calm, shot = _read(trace_p), _read(calm_p), _read(shot_p)
    cam0, cam1 = calm["camera"]["cam0"], calm["camera"]["cam1"]
    zs_of = {a["id"]: float(a["z"]) for a in shot.get("actors", [])}
    out = []
    for ch, cv in tr["characters"].items():
        frames = [f for f in cv["frames"] if (f.get("anchors") or {}).get("face_center")]
        if not frames:
            continue
        zs = zs_of.get(ch)
        if zs is None:
            raise KeyError(f"{sd.name}: no actor z for {ch} in shot.json")
        n = max(1, len(cv["frames"]) - 1)
        boxes = []
        for f in frames:
            u = f["f"] / n
            z = _lerp(cam0["z"], cam1["z"], u)
            F = _lerp(cam0["F"], cam1["F"], u)
            s = F / max(0.05, zs - z)
            cx, cy = f["anchors"]["face_center"]
            w, h = FACE_W_M * s + 2 * FACE_PAD_PX, FACE_H_M * s + 2 * FACE_PAD_PX
            boxes.append({"x": cx - w / 2, "y": cy - h / 2, "w": w, "h": h})
        u = box_union(boxes)
        x0, y0 = max(0, u["x"]), max(0, u["y"])
        x1, y1 = min(CANVAS[0], u["x"] + u["w"]), min(CANVAS[1], u["y"] + u["h"])
        if x1 > x0 and y1 > y0:
            out.append({"char": ch, "x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0})
    return out


def window_face_boxes(items: list[dict], shot_boxes: dict[str, list[dict]], t0: float, t1: float, grace: float = 0.1) -> list[dict]:
    """Face boxes of every timeline item (a dict with t0, t1, id) overlapping [t0, t1] by at least `grace` seconds (a join dissolves two shots; a plate that touches a shot
    only for the last frames of its dissolve is not asked to clear that shot's face). `shot_boxes` maps item id to its boxes (items with no entry are cards: no face)."""
    out = []
    for it in items:
        if min(it["t1"], t1) - max(it["t0"], t0) >= grace - 1e-9:
            out += [{**b, "item": it["id"]} for b in shot_boxes.get(it["id"], [])]
    return out


def choice_face_boxes(it: dict, shot_boxes: dict[str, list[dict]], by_shot: dict[str, str], top_h: int, w: int = 1080) -> list[dict]:
    """Faces visible in the choice sequence's top half: each clip's crop rect (x, y, cw, ch) over its shot, at its start and its drift end, maps linearly onto the
    w x top_h picture. `by_shot` maps a top clip id to its shot id. Union over the clip's whole use (the picture drifts, the plate must not)."""
    out = []
    sp = it.get("split") or {}
    for c in sp.get("top", []):
        cr = c["crop"]
        cw = int(cr["w"]) // 2 * 2
        ch = int(round(cw * top_h / w)) // 2 * 2
        sc = w / cw
        for b in shot_boxes.get(by_shot.get(c["id"], ""), []):
            mapped = []
            for dx, dy in ((0, 0), (cr.get("dx", 0), cr.get("dy", 0))):
                rx, ry = cr["x"] + dx, cr["y"] + dy
                x0, y0 = (b["x"] - rx) * sc, (b["y"] - ry) * sc
                x1, y1 = x0 + b["w"] * sc, y0 + b["h"] * sc
                x0, y0, x1, y1 = max(0, x0), max(0, y0), min(w, x1), min(top_h, y1)
                if x1 > x0 and y1 > y0:
                    mapped.append({"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0})
            u = box_union(mapped)
            if u:
                out.append({**u, "char": b.get("char"), "clip": c["id"], "item": it["id"]})
    return out


def intersects(a: dict, b: dict, pad: int = 0) -> bool:
    return a["x"] < b["x"] + b["w"] + pad and b["x"] < a["x"] + a["w"] + pad and a["y"] < b["y"] + b["h"] + pad and b["y"] < a["y"] + a["h"] + pad


def place_plate(w: int, h: int, default: tuple[int, int], avoid: list[dict], soft: list[dict] | None = None,
                safe: tuple[int, int, int, int] = (54, 270, 1026, 1250), y_max: int | None = None) -> tuple[int, int] | None:
    """The legal (x, y) nearest the default for a w x h plate: inside `safe`, clear of every `avoid` box (faces), and, when possible, clear of the `soft` boxes (the HUD).
    A move up or down costs 1 per px, a sideways move 0.5 per px, touching a soft box 10000. None when no position clears the faces. y_max caps the plate's bottom edge."""
    x0, y0 = default
    bottom = y_max if y_max is not None else safe[3]
    best = None
    xs = sorted({x0} | set(range(safe[0], safe[2] - w + 1, X_STEP)), key=lambda x: abs(x - x0))
    ys = list(range(safe[1], bottom - h + 1, Y_STEP))
    if not ys or not xs:
        return None
    for y in sorted({y0} | set(ys), key=lambda y: abs(y - y0)):
        if y < safe[1] or y + h > bottom:
            continue
        for x in xs:
            if x < safe[0] or x + w > safe[2]:
                continue
            r = {"x": x, "y": y, "w": w, "h": h}
            if any(intersects(r, b) for b in avoid):
                continue
            cost = abs(y - y0) + 0.5 * abs(x - x0) + (10000 if any(intersects(r, b) for b in (soft or [])) else 0)
            if best is None or cost < best[0]:
                best = (cost, x, y)
        if best is not None and best[0] < abs(y - y0):    # every later row is farther away than the best cost found
            break
    return (best[1], best[2]) if best else None


def check_plates(plates: list[dict], boxes_for) -> list[str]:
    """CAP-FACE-CLEAR: `boxes_for(plate)` gives the face boxes on screen while the plate is up. A plate overlapping one fails (any overlap of its rectangle)."""
    f = []
    for p in plates:
        r = {"x": p["x"], "y": p["y"], "w": p["w"], "h": p["h"]}
        for b in boxes_for(p):
            if intersects(r, b):
                f.append(f"CAP-FACE-CLEAR plate «{p.get('text', '')[:30]}» ({p.get('line')}, {p['start']:.2f}-{p['end']:.2f} s) at x{p['x']} y{p['y']} {p['w']}x{p['h']} covers the {b.get('char', 'face')} face box x{round(b['x'])} y{round(b['y'])} {round(b['w'])}x{round(b['h'])} of {b.get('item', '?')}")
                break
    return f
