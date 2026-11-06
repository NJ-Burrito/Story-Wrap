"""Camera plan writer and validator (stage camera). The shot supplies plan/camera.py (BEATS, SHOTS, CUTS, EXTRA);
this module writes camera-plan.json + one thumbnail SVG per shot and validates the result (R-328..R-333).
Failure ids: CAMERA-BEATS, CAMERA-SHOTS, CAMERA-FRAMES, CAMERA-CUTS, CAMERA-THUMB."""
from __future__ import annotations
import json
from pathlib import Path

REQUIRED_SHOT = ("shot", "beat", "t0", "t1", "size", "angle", "lens_mm", "move", "start_frame_desc", "end_frame_desc", "why", "serves_emotion", "safe_boxes", "catalogue_camera")


def thumb(s, mod=None):
    W, H = 270, 480
    ink = 'fill="none" stroke="#000" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"'
    grey = 'fill="#ddd" stroke="#000" stroke-width="1.6"'
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="thmanyahsans, sans-serif">',
         '<rect width="100%" height="100%" fill="#fff"/>', f'<rect x="1" y="1" width="{W-2}" height="{H-2}" fill="none" stroke="#000" stroke-width="2"/>',
         f'<rect x="0" y="{250/4:.0f}" width="{960/4:.0f}" height="{(1580-250)/4:.0f}" fill="none" stroke="#999" stroke-dasharray="4 3"/>']
    sid = s["shot"]
    def figure(cx, cy, k):  # one merged silhouette: hijab, coat, arms (no seams)
        return [f'<path d="M{cx-42*k} {cy+40*k} Q{cx-46*k} {cy-30*k} {cx} {cy-38*k} Q{cx+46*k} {cy-30*k} {cx+42*k} {cy+40*k} L{cx+62*k} {cy+60*k} L{cx+70*k} {cy+190*k} L{cx-70*k} {cy+190*k} L{cx-62*k} {cy+60*k} Z" {grey}/>',
                f'<ellipse cx="{cx}" cy="{cy}" rx="{20*k}" ry="{26*k}" fill="#fff" stroke="#000" stroke-width="1.2"/>']
    art = getattr(mod, "thumb_art", None) if mod is not None else None
    if art:
        p += art(s, ink, grey, figure)
    p += [f'<rect x="0" y="0" width="{W}" height="22" fill="#000"/>', f'<text x="6" y="16" fill="#fff" font-size="13">{sid} {s["size"]} {s["angle"]} {s["lens_mm"]}mm, {s["move"]}</text>',
          f'<text x="6" y="{H-8}" font-size="12">{s["t0"]:.3f}-{s["t1"]:.3f} s, {s["beat"]}</text>', '</svg>']
    return "\n".join(p)



def build_plan(shot_dir: Path, shot: dict, mod) -> dict:
    """Write camera-plan.json and camera/s*.svg from the shot's plan/camera.py module. Returns the plan."""
    shots = [dict(s) for s in mod.SHOTS]
    cam_dir = Path(shot_dir) / "camera"
    cam_dir.mkdir(parents=True, exist_ok=True)
    for s in shots:
        s["dur_s"] = round(s["t1"] - s["t0"], 4)
        s["thumbnail"] = f"{shot['rel']}/camera/{s['shot']}.svg"
        (cam_dir / f"{s['shot']}.svg").write_text(thumb(s, mod), encoding="utf-8")
    plan = {"episode": shot["id"], "fps": shot["fps"], "made_before_animation": True,
            "order_of_work": "camera plan -> shot spec (gate) -> build -> trace -> record -> gate -> review"}
    plan.update(getattr(mod, "EXTRA", {}))
    plan.update({"beats": mod.BEATS, "shots": shots, "cuts": mod.CUTS})
    (Path(shot_dir) / "camera-plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    return plan


def validate_plan(plan: dict, shot: dict, root: Path) -> list[str]:
    """Return failures as 'CHECK-ID message' strings (empty = valid)."""
    fails: list[str] = []
    fps, dur = shot["fps"], shot["duration_s"]
    on_grid = lambda t: abs(t * fps - round(t * fps)) < 1e-6
    beats, shots = plan.get("beats", []), plan.get("shots", [])
    if not beats:
        return ["CAMERA-BEATS no beats"]
    t = 0.0
    for b in beats:
        if abs(b["start"] - t) > 1e-6:
            fails.append(f"CAMERA-BEATS beat {b['id']} starts at {b['start']} s, expected {t} s (beats must be contiguous from 0)")
        t = b["end"]
    if abs(t - dur) > 1e-6:
        fails.append(f"CAMERA-BEATS beats end at {t} s but the shot lasts {dur} s")
    for b in beats:
        for k in ("start", "end"):
            if not on_grid(b[k]):
                fails.append(f"CAMERA-FRAMES beat {b['id']} {k} {b[k]} s is not on the {fps} fps frame grid")
    t = 0.0
    for s in shots:
        miss = [k for k in REQUIRED_SHOT if k not in s or s[k] in (None, "", [])]
        if miss:
            fails.append(f"CAMERA-SHOTS shot {s.get('shot')} lacks {miss}")
            continue
        if abs(s["t0"] - t) > 1e-6:
            fails.append(f"CAMERA-SHOTS shot {s['shot']} starts at {s['t0']} s, expected {t} s (shots must be contiguous)")
        t = s["t1"]
        for k in ("t0", "t1"):
            if not on_grid(s[k]):
                fails.append(f"CAMERA-FRAMES shot {s['shot']} {k} {s[k]} s is not on the {fps} fps frame grid")
        if not (("cam0" in s and "cam1" in s) or "insert" in s):
            fails.append(f"CAMERA-SHOTS shot {s['shot']} has neither cam0/cam1 nor an insert block")
        beat = next((b for b in beats if b["id"] == s["beat"]), None)
        if beat is None or s["t0"] < beat["start"] - 1e-6 or s["t1"] > beat["end"] + 1e-6:
            fails.append(f"CAMERA-SHOTS shot {s['shot']} lies outside its beat {s['beat']}")
        th = root / s.get("thumbnail", "")
        if not s.get("thumbnail") or not th.is_file() or th.stat().st_size < 100:
            fails.append(f"CAMERA-THUMB shot {s['shot']} thumbnail {s.get('thumbnail')} missing")
    if shots and abs(t - dur) > 1e-6:
        fails.append(f"CAMERA-SHOTS shots end at {t} s but the shot lasts {dur} s")
    for b in beats:
        tot = sum(s["t1"] - s["t0"] for s in shots if s.get("beat") == b["id"])
        if abs(tot - (b["end"] - b["start"])) > 0.05:
            fails.append(f"CAMERA-SHOTS shots of beat {b['id']} sum to {tot:.3f} s, the beat is {b['end'] - b['start']:.3f} s")
    cuts = plan.get("cuts", {})
    want = {f"{a['shot']}->{b['shot']}" for a, b in zip(shots, shots[1:])}
    if set(cuts) != want:
        fails.append(f"CAMERA-CUTS cuts {sorted(set(cuts) ^ want)} do not match the shot pairs (need {len(want)} cuts)")
    return fails
