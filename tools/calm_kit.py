"""Calm kits: the per-character data a calm shot template needs (owner, 2026-10-24, CLAUDE.md "Calm format").

A kit is `tools/templates/calm/kits/<char>.json`. It is DATA taken from a character's finished, gated film shot (a "smoke" shot under
work/shots/): the actor entry of shot.json, the rig, physics and props of shot-spec.json, the root position, and where the head, torso and hands sit
in the world (measured from the shot's rig trace and camera, not guessed). Templates (tools/calm.py) read a kit; nothing in a template names a character.

  uv run tools/calm_kit.py extract <smoke-shot-dir> [--out tools/templates/calm/kits/<char>.json]
      first draft of a kit from a smoke shot; poses, acting ranges and the JS hook (kits/<char>.js) are then written by hand
  uv run tools/calm_kit.py status            which characters have a kit, which only have a catalogue (and so cannot be shot yet)

Adding a kit is the only way a new character enters the calm format; it is checked by tools/tests/test_calm.py.
"""
from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("STORYWRAP_ROOT") or TOOLS.parent)
KITS_DIR = TOOLS / "templates" / "calm" / "kits"
W, H = 1080, 1920


def read_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def kit_path(char: str) -> Path:
    return KITS_DIR / f"{char}.json"


def load_kit(char: str) -> dict:
    p = kit_path(char)
    if not p.is_file():
        have = sorted(x.stem for x in KITS_DIR.glob("*.json")) if KITS_DIR.is_dir() else []
        raise KeyError(f"no calm kit for '{char}' (kits: {', '.join(have) or 'none'}); add one with `calm_kit.py extract <smoke-shot-dir>`")
    return read_json(p)


def list_kits() -> list[str]:
    return sorted(x.stem for x in KITS_DIR.glob("*.json")) if KITS_DIR.is_dir() else []


def screen_to_world(px, py, cam: dict, zs: float):
    """Invert the flat camera (core.js P): world X, Y of a screen point on the plane at depth zs."""
    s = cam["F"] / max(0.05, zs - cam["z"])
    return [round(cam["x"] + (px - W / 2) / s, 4), round(cam["y"] + (py - H / 2) / s, 4)]


def extract(shot_dir: Path) -> dict:
    """Draft a kit from a gated single-actor smoke shot."""
    sd = Path(shot_dir)
    shot = read_json(sd / "shot.json")
    spec = read_json(sd / "shot-spec.json")
    plan = read_json(sd / "camera-plan.json")
    trace = read_json(sd / "out" / "rig-trace.json")
    if len(shot.get("actors", [])) != 1:
        raise ValueError("a kit is taken from a single-actor shot")
    actor = copy.deepcopy(shot["actors"][0])
    cid = actor["id"]
    cam = plan["shots"][0]["cam0"]
    zs = float(actor["z"])
    fr = trace["characters"][cid]["frames"][0]
    anc, cp = fr.get("anchors", {}), fr.get("contact_points", {})
    world = {}
    for name, key in (("face", "face_center"), ("torso", "torso_center")):
        p = anc.get(key)
        if p and abs(p[0]) > 5:   # torso_center is body-space (0, -174) in some traces: not a screen point
            world[name] = screen_to_world(p[0], p[1], cam, zs)
    for name, key in (("hand_L", "hand_L"), ("hand_R", "hand_R")):
        if key in cp:
            world[name] = screen_to_world(cp[key][0], cp[key][1], cam, zs)
    props = {k: screen_to_world(v[0], v[1], cam, zs) for k, v in cp.items() if k not in ("hand_L", "hand_R")}
    beat0 = copy.deepcopy(spec["beats"][0])
    return {
        "schema": "calm-kit/1", "id": cid, "module": actor["module"], "source_shot": sd.name,
        "actor": actor, "world": shot.get("world", "world-a"), "film": None,
        "root": {"X": None, "Y": None, "z": zs},
        "camera_medium": {k: cam[k] for k in ("x", "y", "z", "F")},
        "where": {"face": world.get("face"), "torso": world.get("torso"), "hand_L": world.get("hand_L"), "hand_R": world.get("hand_R"), "props": props},
        "spec": {
            "character": copy.deepcopy(spec["characters"][0]), "physics_profiles": copy.deepcopy(spec["physics_profiles"]),
            "props": copy.deepcopy(spec.get("props", [])), "actor_entry": copy.deepcopy(spec["actors"][0]),
            "beat_base": beat0,
        },
        "poses": {}, "acting": {}, "trace": {},
        "todo": ["root X, Y (the smoke scene's pelvis position)", "poses: grips and hand local targets from the smoke scene", "acting ranges (neck clamps, breath)", "kits/<char>.js hook (extras, traceExtra)"],
    }


def status() -> str:
    cat = sorted(p.name for p in (ROOT / "catalogue" / "characters").iterdir() if p.is_dir())
    kits = list_kits()
    lines = [f"{c:10s} {'KIT' if c in kits else 'no kit (cannot be shot in the calm format yet)'}" for c in cat]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("extract", "status"):
        print(__doc__)
        return 2
    if argv[0] == "status":
        print(status())
        return 0
    if len(argv) < 2:
        print(__doc__)
        return 2
    kit = extract(Path(argv[1]))
    out = Path(argv[argv.index("--out") + 1]) if "--out" in argv else kit_path(kit["id"])
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        print(f"FAIL [KIT-EXISTS] {out} exists: kits are edited by hand once written; delete it first if you want a fresh draft")
        return 1
    out.write_text(json.dumps(kit, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"OK kit draft {out} ({len(json.dumps(kit))} bytes); fill: {', '.join(kit['todo'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
