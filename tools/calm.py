# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Calm shot templates (owner, 2026-10-24, CLAUDE.md "Calm format": HIS PACING, OUR ART).

A template is DATA, not code: a name plus parameters (character, pose, expression, set, duration, camera move). `calm.py make` turns it into a
normal `tools/shot.py` shot folder (shot.json with "format": "calm", plan/camera.py, plan/spec.py, scene/*.js, calm.json) that the existing
pipeline records and gates; shot.py runs the calm profile for it (quality_gate.py --format calm: pacing checks move, the art checks do not).

  uv run tools/calm.py list                                   templates, kits, sets, and what each template needs
  uv run tools/calm.py make <template> <shot-dir> [key=value ...] [--params file.json] [--run]
  uv run tools/calm.py validate <shot-dir>                    re-check calm.json of an existing calm shot (no browser)

Actor templates (a character in the world-a set, 2D ink, the engine of tools/render):
  push_in            slow push-in on one subject                      character pose expression [gaze] [target=face|torso] [size=mwide push=3]
  parallax_pan       slow parallax pan across the set to the subject  character pose expression [pan=left|right span=0.01 (share of the frame width)]
  hold_breathe       a deliberate hold: breathing, a blink, tiny drift character pose expression [gaze]
  insert             insert on a prop or a hand                       character pose target=hand_L|hand_R|prop:<name> [expression] [size=mwide at_y=0.62 push=2.5 gain=1.25]
  insert_depth       calm insert with real depth: 3-4 separated planes + a slow dolly   character target=prop:<tag|key|cards> [expression] [dist=1.6 win=<per prop> push=7 span=0.008 dim=0.2 occ=left|right|off]
  reaction_closeup   reaction close-up: one expression turns into another  character pose expression expression_to [change_at=0.45]
  two_shot           two-shot exchange, hands always apart (no touch) characters=a,b poses=p,q expressions=e,f [gap]
Card templates (typographic cards in Thmanyah, tools/calm_cards.py):
  title_card day_card recap_card choice_card follow_card choice_split object_card
Beat template (tools/calm_intro.py):
  intro_freeze   C10: a character's first appearance freezes, a grey glow isolates them, graffiti names them   character name tag source=work/shots/<scene> [hold]

Common keys: id, duration (seconds, snapped to the 24 fps grid), set (world-a), intensity (0..1), cause (why the feeling), seed,
  grade (0..0.12, darkness of the set behind the actor, two flat steps), grade_actor (0..0.12, the actor too; never above grade). See pipelines/CALM.md "Grade".
Exit 0 ok, 1 a template or parameter was refused (`FAIL [CALM-*] message`), 2 usage.
"""
from __future__ import annotations

import copy
import json
import os
import re
import shutil
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("STORYWRAP_ROOT") or TOOLS.parent)
sys.path.insert(0, str(TOOLS))
import calm_kit as ck   # noqa: E402

FPS = 24
CANVAS = [1080, 1920]
TPL_DIR = TOOLS / "templates" / "calm"
MIN_S, MAX_S = 1.5, 9.0          # recipe: a calm shot is about 3.7 s, never under 1.5 s (research/stickman-replication.md 5); 9 s is the longest hold we allow
MAX_CHOICE_S = 16.0         # (C13: was 14.0) the choice_split card (C4) alone may run longer: tools/calm_cards.py and calm_compose.MAX_CHOICE_S state the same number
SIZES = {"wide": (0.62, "WS", 24), "mwide": (0.82, "MWS", 28), "medium": (1.0, "MS", 35), "mclose": (1.3, "MCU", 42), "close": (1.8, "CU", 50), "ecu": (3.0, "ECU", 85)}   # x the kit's medium scale
GAZES = {"camera": [0, 4], "down": [0, 20], "up": [0, -12], "left": [-14, 3], "right": [14, 3], "away": [-12, 6]}   # yaw, pitch in degrees (kit may override)
BLINK_BANDS = {"calm": (10, 17), "joy": (12, 18), "sadness": (6, 10), "fear": (3, 30), "anger": (3, 6), "surprise": (0, 20), "suspicion": (6, 10), "relief": (6, 10), "bitter-joy": (6, 10)}
EMOTIONS = ["calm", "joy", "sadness", "fear", "anger", "surprise", "disgust", "contempt", "shame", "longing", "relief", "suspicion", "dread", "bitter-joy", "wonder"]
FONTS = ["700 40px thmanyahseriftext", "700 20px thmanyahsans", "500 16px thmanyahsans"]
LIBRARY = ["core.js", "geom2d.js", "worlds/world-a.js", "face.js", "hands.js", "actors.js", "@scene", "trace-multi.js", "bootstrap-multi.js"]
LIFE = {"lamp": 0.1, "flicker": 0.2, "dust": False, "world": 0.15}   # how much the set itself moves: calm shots keep it low (motion coverage <= 0.35, clusters <= 8: qg_checks.CALM)
HAND_REACH_M = 0.9               # a character's hand reaches about this far from its root (arm 3 head units x the module's hu_m, rounded up)


class CalmError(Exception):
    def __init__(self, code: str, msg: str):
        super().__init__(f"FAIL [{code}] {msg}")
        self.code, self.msg = code, msg


# ------------------------------------------------------------------ sets
SETS = {
    "world-a": {
        "world": "world-a", "library": "worlds/world-a.js",
        "label": "the harbour office under the quay (the only set with a film drawing so far)",
        "pan_span": 0.01,   # a slow pan crosses about 1.5 % of the frame width: motion coverage (calm ceiling 0.35) measured 0.82 at 0.22, 0.70 at 0.08, 0.47 at 0.03, 0.35 at 0.015
    },
}


# ------------------------------------------------------------------ helpers
def snap(dur: float) -> float:
    return round(float(dur) * FPS) / FPS


def num(p: dict, key: str, default, lo=None, hi=None):
    try:
        v = float(p.get(key, default))
    except (TypeError, ValueError):
        raise CalmError("CALM-PARAM", f"{key}={p.get(key)!r} is not a number")
    if (lo is not None and v < lo) or (hi is not None and v > hi):
        raise CalmError("CALM-PARAM", f"{key}={v} outside {lo}..{hi}")
    return v


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def seeded(seed: str):
    h = 2166136261
    for ch in seed:
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    def nxt():
        nonlocal h
        h = (1664525 * h + 1013904223) & 0xFFFFFFFF
        return h / 0xFFFFFFFF
    return nxt


def catalogue_for(char: str):
    from shotlib.catalogue import Catalogue
    return Catalogue(ROOT, char)


def kit_of(char: str) -> dict:
    try:
        return ck.load_kit(char)
    except KeyError as e:
        raise CalmError("CALM-KIT", str(e).strip("'\""))


def expression_of(kit: dict, name: str) -> dict:
    """The expression's AUs and eye offsets, read from the character's catalogue (the file the engine loads), plus its catalogue ref."""
    ex = (kit.get("expressions") or {})
    name = (kit.get("expression_aliases") or {}).get(name, name)   # the plan speaks in plain feelings (calm, fear, ...); a kit maps each to the catalogue file that character really has
    if name not in ex:
        raise CalmError("CALM-EXPRESSION", f"{kit['id']} has no expression '{name}' in its calm kit (kit expressions: {', '.join(sorted(ex)) or 'none'})")
    meta = ex[name]
    f = ROOT / "catalogue" / "characters" / kit["id"] / meta["dir"].strip("/") / f"{name}.json"
    if not f.is_file():
        raise CalmError("CALM-EXPRESSION", f"expression file {f} is missing")
    j = json.loads(f.read_text(encoding="utf-8"))
    cat = catalogue_for(kit["id"])
    ver = cat.latest(j["id"])
    return {"id": name, "ref": f"{j['id']}@{ver}" if ver else None, "aus": {str(k): float(v) for k, v in j.get("aus", {}).items()},
            "eye": {k: float(v) for k, v in (j.get("eye") or {}).items() if k in ("eyeX", "eyeY")},
            "emotion": meta.get("emotion") or j.get("emotion") or "calm", "dir": meta["dir"]}


def pose_of(kit: dict, name: str) -> dict:
    if name not in kit.get("poses", {}):
        raise CalmError("CALM-POSE", f"{kit['id']} has no pose '{name}' in its calm kit (poses: {', '.join(sorted(kit.get('poses', {}))) or 'none'})")
    return kit["poses"][name]


# ------------------------------------------------------------------ camera
def scale_medium(kit: dict) -> float:
    c = kit["camera_medium"]
    return c["F"] / (float(kit["actor"]["z"]) - c["z"])


def where_of(kit: dict, pose: dict, dx: float = 0.0) -> dict:
    w = copy.deepcopy(pose.get("where") or kit["where"])
    root = kit.get("root") or {}
    if root.get("X") is not None and root.get("Y") is not None:
        w["root"] = [root["X"], root["Y"]]
    for k, v in list(w.items()):
        if k in ("face", "hand_L", "hand_R", "root") and v:
            w[k] = [v[0] + dx, v[1]]
    if w.get("props"):
        w["props"] = {k: [v[0] + dx, v[1]] for k, v in w["props"].items()}
    if w.get("face") and w.get("root"):
        w["torso"] = [(w["face"][0] + w["root"][0]) / 2, (w["face"][1] + w["root"][1]) / 2]
    return w


def target_point(w: dict, target: str):
    if target.startswith("prop:"):
        name = target[5:]
        pt = (w.get("props") or {}).get(name)
        if not pt:
            raise CalmError("CALM-TARGET", f"no prop '{name}' (props: {', '.join((w.get('props') or {}).keys()) or 'none'})")
        return pt
    pt = w.get(target)
    if not pt:
        raise CalmError("CALM-TARGET", f"no target '{target}' (face, torso, hand_L, hand_R, prop:<name>)")
    return pt


def camera_at(kit: dict, point, size: str, at=(0.5, 0.42)) -> dict:
    if size not in SIZES:
        raise CalmError("CALM-SIZE", f"size '{size}' is not one of {', '.join(SIZES)}")
    sc = scale_medium(kit) * SIZES[size][0]
    c = kit["camera_medium"]
    return {"x": round(point[0] - (at[0] - 0.5) * CANVAS[0] / sc, 4), "y": round(point[1] - (at[1] - 0.5) * CANVAS[1] / sc, 4), "z": c["z"], "F": round(sc * (float(kit["actor"]["z"]) - c["z"]), 1)}


def screen_box(cam: dict, zs: float, point, w_m: float, h_m: float, box_id: str) -> dict:
    s = cam["F"] / max(0.05, zs - cam["z"])
    cx, cy = CANVAS[0] / 2 + (point[0] - cam["x"]) * s, CANVAS[1] / 2 + (point[1] - cam["y"]) * s
    x0, y0, x1, y1 = max(0, cx - w_m * s / 2), max(250, cy - h_m * s / 2), min(960, cx + w_m * s / 2), min(1580, cy + h_m * s / 2)
    return {"id": box_id, "x": round(x0), "y": round(y0), "w": max(40, round(x1 - x0)), "h": max(40, round(y1 - y0))}


# ------------------------------------------------------------------ actors
def acting(kit: dict, p: dict, dur: float, role: str = "") -> dict:
    """Resolve one actor's acting data for the scene (everything the generic scene needs, nothing it must invent)."""
    pose_name = p.get("pose") or kit.get("default_pose")
    pose = pose_of(kit, pose_name)
    e0 = expression_of(kit, p.get("expression") or kit.get("default_expression"))
    n = round(dur * FPS)
    change_frames = int(num(p, "change_frames", 12, 6, 24))   # qg_checks: an emotion change takes 6..24 frames
    if p.get("expression_to"):   # a reaction: the face starts in expression_to's predecessor and turns into expression_to at change_at
        e1 = expression_of(kit, p["expression_to"])
        e_from, e_to = e0, e1
        change_f = int(round(num(p, "change_at", 0.45, 0.15, 0.85) * n))
    else:   # the expression arrives on a neutral face at arrive_at (a rest face has nothing to read): the biggest face change is that arrival
        e1 = e0
        e_from, e_to = {"aus": {}, "eye": {}}, e0
        change_f = max(3, int(round(num(p, "arrive_at", 0.2, 0.0, 0.7) * n)))
    br_cycles = max(1, round(dur * float(kit.get("acting", {}).get("breath_hz", 0.26))))
    g_from = p.get("gaze") or kit.get("default_gaze") or "camera"
    g_to = p.get("gaze_to") or g_from
    gz = {**GAZES, **(kit.get("acting", {}).get("gaze") or {})}
    for g in (g_from, g_to):
        if g not in gz:
            raise CalmError("CALM-GAZE", f"gaze '{g}' is not one of {', '.join(gz)}")
    rnd = seeded(f"{kit['id']}-{p.get('seed', '')}-{round(dur * FPS)}")
    emo = e0["emotion"] if e0["emotion"] in BLINK_BANDS else "calm"
    lo, hi = BLINK_BANDS.get(emo, (0, 30))
    rate = (lo + hi) / 2 if hi < 30 else 12
    nb = int(round(rate * dur / 60))
    blinks = [int(round((i + 0.55) * n / max(1, nb))) for i in range(nb)]
    intensity = num(p, "intensity", 0.8, 0.1, 1.0)
    if not p.get("expression_to") and "arrive_at" not in p and blinks and sum(abs(v) for v in e0["aus"].values()) * intensity / change_frames < 0.05:
        # a quiet face (its arrival moves the face by under 0.05 a frame): the blink is the biggest face change of the shot (qg_checks rig_face, R-374), so the declared peak
        # sits on the blink instead of on an arrival nobody can see. A blink peaks one frame after it starts.
        change_f = max(3, blinks[0] + 1 - change_frames // 2)
    peak_s = round((change_f + change_frames / 2) / FPS, 4)
    darts, t = [], 0.35 + rnd() * 0.25
    while t < dur - 0.25:   # the eyes move on their own at least once in every second (qg_checks RIG-EYE-DART, R-363)
        sg = lambda: 1 if rnd() < 0.5 else -1   # a dart is never a near-zero nudge: 2.5 to 5.5 degrees across, 1 to 2.5 up or down
        darts.append([round(t, 3), round(sg() * (2.5 + rnd() * 3), 1), round(sg() * (1.0 + rnd() * 1.5), 1), 3])
        t += 0.62 + rnd() * 0.2
    return {
        "id": kit["id"], "kit": kit["id"], "role": role, "root_dx": float(p.get("root_dx", 0.0)),
        "pose_name": pose_name, "pose": {k: pose[k] for k in ("flex", "tilt", "neckFlex", "neckTilt", "shrug", "hands")},
        "breath": {"cycles": br_cycles, "flex_amp": num(p, "breath_amp", 1.4, 0.2, 4), "tilt_amp": 0.8, "sway_cycles": max(1, round(dur * 0.1)), "shrug_amp": 0.012, "hand_amp": [0.02, 0.03]},
        "expr_from": {"aus": e_from["aus"], "eye": e_from["eye"]}, "expr_to": {"aus": e_to["aus"], "eye": e_to["eye"]}, "peak_s": peak_s,
        "expression": e0["id"], "expression_to": e1["id"], "emotion": emo, "emotion_to": e1["emotion"] if e1["emotion"] in EMOTIONS else emo,
        "intensity": num(p, "intensity", 0.8, 0.1, 1.0),
        "change_f": change_f, "change_frames": change_frames,
        "head_tilt": float(p.get("head_tilt", 2.0 if e1 is not e0 else 0.0)),
        "gaze_from": gz[g_from], "gaze_to": gz[g_to], "gaze_from_label": g_from, "gaze_to_label": g_to,
        "gaze_change_f": int(round(float(p.get("gaze_change_at", 0.5)) * n)) if g_to != g_from else n + 1, "gaze_change_frames": 10,
        "blinks": blinks, "blink_per_min": [lo, hi], "darts": darts, "darts_per_s": round(len(darts) / dur, 2) if dur else 0,
        "expr_refs": [r for r in (e0["ref"], e1["ref"]) if r], "expr_files": sorted({e0["id"], e1["id"]}), "expr_dir": e0["dir"],
    }


# ------------------------------------------------------------------ templates (data -> calm dict)
def _base(template: str, p: dict, kind: str = "actor") -> dict:
    dur = snap(num(p, "duration", 3.75, MIN_S, MAX_S))
    sid = slug(str(p.get("id") or f"calm-{template}"))
    sset = p.get("set", "world-a")
    if sset not in SETS:
        raise CalmError("CALM-SET", f"set '{sset}' has no film drawing (sets: {', '.join(SETS)})")
    return {"schema": "calm-shot/1", "format": "calm", "kind": kind, "template": template, "id": sid, "fps": FPS, "duration_s": dur, "canvas": CANVAS, "set": sset}


def _single(template: str, p: dict, *, size: str, push_pct: float, target: str, move: str, why: str, locked_because: str | None = None,
            pan: float = 0.0) -> dict:
    c = _base(template, {**p, "template": template})
    char = p.get("character")
    if not char:
        raise CalmError("CALM-PARAM", f"{template} needs character=<id> (kits: {', '.join(ck.list_kits())})")
    kit = kit_of(char)
    dur = c["duration_s"]
    a = acting(kit, {**p, "template": template}, dur)
    pose = pose_of(kit, a["pose_name"])
    w = where_of(kit, pose, a["root_dx"])
    size = p.get("size", size)
    push_pct = num(p, "push", push_pct, 0.0, 15.0)   # the recipe's push is scale 1.00 to 1.08 over a scene
    pan = pan or (1.0 if "span" in p else 0.0)   # span=<share of the frame width> adds a sideways drift to any template (inserts use it for their parallax)
    if p.get("locked"):   # a locked-off camera, with its reason (R-330): the subject is an object, the lamp, the near tags and the breath move, the frame does not
        locked_because, push_pct, pan = str(p["locked"]), 0.0, 0.0
    target = p.get("target", target)
    pt = target_point(w, target)
    at = (0.5, 0.42) if target == "face" else (0.5, 0.5)
    if "at_y" in p or (template == "insert"):   # where the target sits in the frame (0 top .. 1 bottom): a hand held low keeps the figure above it in the picture
        at = (0.5, num(p, "at_y", 0.55, 0.25, 0.75))
    cam0 = camera_at(kit, pt, size, at)
    zs = float(kit["actor"]["z"])
    cam1 = {**cam0, "z": round(zs - (zs - cam0["z"]) / (1 + push_pct / 100), 4)}   # a dolly (camera z), not a zoom: near layers then move faster than far ones (the parallax the depth gate wants)
    if pan:
        frac = num(p, "span", SETS[c["set"]]["pan_span"], 0.01, 0.4)   # the pan's length as a share of the frame width
        sign = -1 if p.get("pan", "right") == "left" else 1
        span_m = frac * CANVAS[0] / (cam0["F"] / (float(kit["actor"]["z"]) - cam0["z"]))
        cam0 = {**cam0, "x": round(cam0["x"] - sign * span_m / 2, 4)}
        cam1 = {**cam1, "x": round(cam1["x"] + sign * span_m / 2, 4)}
    s0 = cam0["F"] / (zs - cam0["z"])
    s1 = cam1["F"] / (zs - cam1["z"])
    move_pct = round(max(abs(s1 / s0 - 1) * 100, abs(cam1["x"] - cam0["x"]) * s0 / CANVAS[0] * 100, abs(cam1["y"] - cam0["y"]) * s0 / CANVAS[1] * 100), 2)
    if move_pct < 2.0 and not locked_because:
        cam1 = {**cam1, "z": round(zs - (zs - cam1["z"]) / 1.025, 4)}   # a calm hold still drifts about 2.5 %: motion coverage and the camera_move check both want a trace of it
        move_pct = 2.5
    face_box = screen_box(cam1, zs, w.get("face") or pt, 0.42, 0.5, "face")
    c.update({
        "character": char, "actors": [a], "camera": {"move": move, "size0": size, "size1": size, "target": target, "cam0": cam0, "cam1": cam1, "move_pct": move_pct,
                                                       "why": why, "locked_because": locked_because, "safe_boxes": [face_box]},
        "cause": p.get("cause") or kit.get("default_cause") or "a quiet moment in the office",
        "xp": {k[2:]: v for k, v in p.items() if k.startswith("x_")},   # scene parameters only the kit's drawing hook reads (which prop lies on the counter, ...)
        "life": {**LIFE, **({"gain": num(p, "gain", 1.0, 0.8, 1.6)} if "gain" in p else {}), **({"lamp": num(p, "lamp", LIFE["lamp"], 0, 1)} if "lamp" in p else {}), **({"world": num(p, "world", LIFE["world"], 0, 1)} if "world" in p else {}), **({"dust": p["dust"] in ("1", "true", "yes")} if "dust" in p else {})},
    })
    return c


def t_push_in(p):
    return _single("push_in", p, size="mwide", push_pct=3.0, target="face", move="push",
                   why="a slow push says 'look closer at this one person' and keeps one subject in the frame")


def t_parallax_pan(p):
    return _single("parallax_pan", p, size="mwide", push_pct=0.0, target="torso", move="drift", pan=1.0,
                   why="a slow sideways drift across the set shows the layers sliding at different speeds, then rests on the subject")


def t_hold_breathe(p):
    return _single("hold_breathe", p, size="mwide", push_pct=2.5, target="torso", move="drift",
                   why="a deliberate hold: the figure breathes and blinks while the frame barely drifts, the pause before the next line")


def t_insert(p):
    if not p.get("target"):
        raise CalmError("CALM-PARAM", "insert needs target=hand_L|hand_R|prop:<name>")
    return _single("insert", {"gain": "1.25", "at_y": "0.62", **p}, size="mwide", push_pct=2.5, target="hand_R", move="push",
                   why="an insert on one hand or prop: the story object the narrator is naming, held in a close frame")


def t_insert_depth(p):
    """A calm INSERT with real depth (E01C: the prop close-ups failed parallax_corr because the prop sat on one flat plane and a wider pan broke CALM-MOTION).

    Planes, back to front (CALM.depth in calm-scene.js, the kit's `hero` hook in kits/<char>.js):
      1. the far set, dimmed in two flat steps (dim=)             Z 3.6..8, the lens is 5+ m away from it
      2. the counter surface, the bag and the character's side     Z 2.2..2.6
      3. the hero prop on its own plane (kit.hero[name].Z) with a flat 2D cast shadow on the counter top and its own small action
      4. a dark soft-edged occluder with two hanging tags on the lens side (occ=left|right, occ=off removes it)   nearest to the lens
    One slow dolly (push= % at the hero plane) plus a slight drift (span=). The lens sits dist= metres from the hero plane, close enough that each plane moves at its own rate
    (nearer = faster: real parallax), while the total move stays inside the calm band. The world's own near strings, the pole and the dust are off (they would sit at a hand's width
    from the lens); the scene's life stays at the calm values."""
    tgt = p.get("target") or ""
    if not tgt.startswith("prop:"):
        raise CalmError("CALM-PARAM", "insert_depth needs target=prop:<name> (a prop with a hero drawing in the kit: tag, key, cards)")
    name = tgt[5:]
    kit = kit_of(p.get("character") or "")
    hero = (kit.get("hero") or {}).get(name)
    if not hero:
        raise CalmError("CALM-HERO", f"{kit['id']}'s kit has no hero prop '{name}' (hero props: {', '.join((kit.get('hero') or {}).keys()) or 'none'}); use the plain insert template")
    q = {"gain": "1.25", "at_y": str(hero.get("at_y", 0.62)), "win": str(hero.get("win", 0.7)), "dist": "1.6", "dust": "0", "dim": "0.2", **p}
    c = _single("insert_depth", {k: v for k, v in q.items() if k not in ("span", "pan", "push")}, size="mwide", push_pct=2.5, target=tgt, move="push", pan=0.0,
                why=f"an insert on the {name} built as separate planes (far set, counter, prop with its shadow, a dark occluder) with a slow dolly: each plane moves at its own rate, so the depth is real and the motion stays calm")
    D = num(q, "dist", 1.6, 0.9, 2.4)             # lens to the hero plane, metres
    win = num(q, "win", 0.7, 0.35, 1.0)           # width of the frame at the hero plane, metres
    push = num(q, "push", 7.0, 3.0, 12.0)         # % scale change at the hero plane over the shot (the recipe's push is 1.00 to 1.08)
    span = num(q, "span", 0.008, 0.0, 0.03)       # sideways drift, share of the frame width at the hero plane
    sc = CANVAS[0] / win                          # px per metre at the hero plane
    at_y = num(q, "at_y", 0.62, 0.35, 0.75)
    zh, X, Y = float(hero["Z"]), float(hero["X"]), float(hero["Y"])
    sign = -1 if q.get("pan", "right") == "left" else 1
    sm = span * CANVAS[0] / sc
    y = round(Y - (at_y - 0.5) * CANVAS[1] / sc, 4)
    cam0 = {"x": round(X - sign * sm / 2, 4), "y": y, "z": round(zh - D, 4), "F": round(sc * D, 1)}
    cam1 = {"x": round(X + sign * sm / 2, 4), "y": y, "z": round(zh - D / (1 + push / 100), 4), "F": cam0["F"]}
    occ_side = q.get("occ", "left")
    occ = {"on": occ_side != "off", "side": "right" if occ_side == "right" else "left", "z": round(zh - num(q, "occ_z", 0.45, 0.2, 0.7) * D, 4),
           "frac": num(q, "occ_frac", 0.11, 0.05, 0.2), "bleed": 0.15}
    for cam in (cam0, cam1):
        if occ["on"] and occ["z"] - cam["z"] < 0.3:
            raise CalmError("CALM-DEPTH", f"the occluder plane Z {occ['z']} is within 0.3 m of the lens (Z {cam['z']}): raise occ_z or dist")
    s_h0, s_h1 = cam0["F"] / (zh - cam0["z"]), cam1["F"] / (zh - cam1["z"])
    move_pct = round(max(abs(s_h1 / s_h0 - 1) * 100, abs(cam1["x"] - cam0["x"]) * s_h0 / CANVAS[0] * 100), 2)
    cam = c["camera"]
    cam.update({"cam0": cam0, "cam1": cam1, "move_pct": move_pct, "size0": "mclose", "size1": "mclose", "target": tgt,
                "safe_boxes": [screen_box(cam1, zh, [X, Y], 0.3, 0.3, name)]})
    c["xp"] = {k: v for k, v in c["xp"].items() if k not in ("near",)}
    c["depth"] = {"hero": name, "hero_z": zh, "dist_m": D, "win_m": win, "push_pct": push, "span": span, "dim_far": num(q, "dim", 0.2, 0.0, 0.7), "occ": occ,
                  "planes": {"far": 3.6, "counter": [2.22, 2.6], "hero": zh, "occluder": occ["z"] if occ["on"] else None}}
    c["life"] = {**c["life"], "dust": False, "world": num(q, "world", 0.1, 0.0, 1.0)}
    return c


def t_reaction_closeup(p):
    p = {"intensity": "0.7", "change_frames": "14", **p, "expression_to": p.get("expression_to") or None}   # a gentler, slower turn: facial features are many small clusters (qg_checks.CALM motion_clusters <= 8)
    if not p.get("expression_to"):
        raise CalmError("CALM-PARAM", "reaction_closeup needs expression=<first> and expression_to=<reaction>")
    return _single("reaction_closeup", p, size="medium", push_pct=3.0, target="face", move="push",
                   why="a reaction close-up: the face turns from one feeling to the next while the frame moves in slightly")


def t_two_shot(p):
    chars = [x.strip() for x in str(p.get("characters", "")).split(",") if x.strip()]
    if len(chars) != 2 or chars[0] == chars[1]:
        raise CalmError("CALM-PARAM", "two_shot needs characters=a,b (two different characters)")
    poses = [x.strip() for x in str(p.get("poses", "")).split(",") if x.strip()] or [None, None]
    exprs = [x.strip() for x in str(p.get("expressions", "")).split(",") if x.strip()] or [None, None]
    gaze = [x.strip() for x in str(p.get("gazes", "")).split(",") if x.strip()] or ["right", "left"]
    c = _base("two_shot", {**p, "template": "two_shot"})
    kits = [kit_of(x) for x in chars]
    dur = c["duration_s"]
    gap = num(p, "gap", 1.15, 0.9, 3.0)   # metres between the two roots: more than two arm reaches apart, so the hands cannot meet
    offs = [-gap / 2, gap / 2]
    acts, whs = [], []
    for i, kit in enumerate(kits):
        # keep each character at its own kit root (depth and counter occlusion), shifted sideways to the pair gap
        base_x = (kit.get("root") or {}).get("X") or 0.0
        dx = offs[i] - base_x
        a = acting(kit, {"pose": poses[i] if i < len(poses) else None, "expression": exprs[i] if i < len(exprs) else None, "gaze": gaze[i] if i < len(gaze) else None,
                         "intensity": p.get("intensity", 0.7), "seed": f"{p.get('seed', '')}{i}", "template": "two_shot", "root_dx": dx}, dur, role="speaker" if i == int(p.get("speaker", 0)) else "listener")
        acts.append(a)
        whs.append(where_of(kit, pose_of(kit, a["pose_name"]), a["root_dx"]))
    k0 = kits[0]
    mid = [(whs[0]["face"][0] + whs[1]["face"][0]) / 2, (whs[0]["face"][1] + whs[1]["face"][1]) / 2 + 0.25]
    sc = min(CANVAS[0] * 0.80 / (gap + 1.5), scale_medium(k0) * 1.1)
    c0 = k0["camera_medium"]
    zs0 = float(k0["actor"]["z"])
    def cam_s(scale):
        return {"x": round(mid[0], 4), "y": round(mid[1], 4), "z": c0["z"], "F": round(scale * (zs0 - c0["z"]), 1)}
    cam0 = cam_s(sc)
    cam1 = {**cam0, "z": round(zs0 - (zs0 - c0["z"]) / 1.03, 4)}   # a 3 % dolly, like every calm push (parallax, not zoom)
    boxes = [screen_box(cam1, float(kits[i]["actor"]["z"]), whs[i]["face"], 0.42, 0.5, f"face-{chars[i]}") for i in range(2)]
    c.update({"character": chars[0], "characters": chars, "actors": acts, "gap_m": gap,
              "camera": {"move": "push", "size0": "medium", "size1": "medium", "target": "pair", "cam0": cam0, "cam1": cam1, "move_pct": 3.0,
                         "why": "a two-shot exchange: both people in one frame, a slow push, hands kept apart (no touch)", "locked_because": None, "safe_boxes": boxes},
              "cause": p.get("cause") or "two people at the counter, one speaking and one listening"})
    return c


ACTOR_TEMPLATES = {
    "push_in": (t_push_in, "slow push-in on one subject", ["character"]),
    "parallax_pan": (t_parallax_pan, "slow parallax pan across the set", ["character"]),
    "hold_breathe": (t_hold_breathe, "hold with a small breathing / blink loop", ["character"]),
    "insert": (t_insert, "insert on a prop or a hand", ["character", "target"]),
    "insert_depth": (t_insert_depth, "insert on a prop built as separate planes with a slow dolly (real parallax, calm motion)", ["character", "target"]),
    "reaction_closeup": (t_reaction_closeup, "reaction close-up (one expression turns into another)", ["character", "expression", "expression_to"]),
    "two_shot": (t_two_shot, "two-shot exchange, no touch", ["characters"]),
}
CARD_TEMPLATES = ("title_card", "day_card", "recap_card", "choice_card", "follow_card", "choice_split", "object_card", "intro_freeze")


GRADE_SET_MAX, GRADE_ACTOR_MAX = 0.12, 0.12    # alpha caps of the two flat value steps, MEASURED not chosen (2026-10-27, push_in hero medium, 3 s, shot.py all): luma_range (>= 0.85) was 0.91 at grade 0, 0.882 at 0.12 (pass), 0.842 at 0.18, 0.820 at 0.24, 0.809 at 0.4 and 0.6 (fail); 0.4 with grade_actor 0.1 gave 0.776 and LOOK2D-LINE 0.079. A bigger value would only produce a shot the gate refuses. More darkness than this needs a Lead-merged R-212 proposal (gate-spec.md H: a declared dark beat), never a larger number here.


def apply_grade(c: dict, p: dict) -> dict:
    """Q10 (E02 critic, 2026-10-27): a per-shot DARKNESS setting. `grade=<0..0.12>` dims the set behind the actor (backdrop, chute, counter) and `grade_actor=<0..0.12>` is laid over the whole frame after the actor, so it dims the actor and the props she handles (and the set a second time), each as TWO FLAT value steps of one dark ink (the same two steps `farDim` uses): a flat 2D value shift, no gradient, no 3D, nothing the LOOK2D gate reads as
    smooth shading. Both default to 0, in which case calm.json and shot.json are byte-for-byte what they were (no cached shot is invalidated by the parameter alone). Not a lamp setting:
    `lamp` and `world` only change how much the lamp and the set MOVE (motion coverage), never how bright the frame is. The plan's way to say "darker towards the end"."""
    g_set = num(p, "grade", 0.0, 0.0, GRADE_SET_MAX)
    g_act = num(p, "grade_actor", 0.0, 0.0, GRADE_ACTOR_MAX)
    if g_act > g_set + 1e-9:
        raise CalmError("CALM-PARAM", f"grade_actor={g_act} is above grade={g_set}: the figure may never be darker than the room behind it (the eye goes to the lit figure)")
    if g_set > 0 or g_act > 0:
        c = {**c, "grade": {"set": round(g_set, 3), "actor": round(g_act, 3)}}
    return c


def resolve(template: str, params: dict) -> dict:
    """Template name + parameters -> the calm description of one shot. Raises CalmError (never guesses a missing parameter)."""
    if template in ACTOR_TEMPLATES:
        fn, _, need = ACTOR_TEMPLATES[template]
        miss = [k for k in need if not params.get(k)]
        if miss:
            raise CalmError("CALM-PARAM", f"{template} needs {', '.join(miss)}")
        c = fn(params)
        c = apply_grade(c, params)
        for a in c["actors"]:
            if a["id"] not in ck.list_kits():
                raise CalmError("CALM-KIT", f"no kit for {a['id']}")
        return c
    if template == "intro_freeze":      # C10: a character's first appearance freezes (tools/calm_intro.py)
        import calm_intro
        return calm_intro.resolve(params)
    if template in CARD_TEMPLATES:
        import calm_cards
        return calm_cards.resolve(template, params)
    raise CalmError("CALM-TEMPLATE", f"unknown template '{template}' (templates: {', '.join(list(ACTOR_TEMPLATES) + list(CARD_TEMPLATES))})")


# ------------------------------------------------------------------ lip sync (owner, 2026-10-25, C6: "the mouths do not move with the words")
# A character's mouth follows ITS OWN viseme track (work/voice/<ep>/visemes/<line>.json, written by `voice.py visemes` from the take that is mixed),
# placed on the shot clock at start_s = the line's voice start minus the shot's start. The narrator has no mouth: its lines never reach a character.
# c["lipsync"] is the list of those placements (empty for a shot with no on-screen speaker); its presence marks a voice-aware shot, so the rig
# checks LIPSYNC-ACTIVE / LIPSYNC-SILENT (qg_checks.rig_lipsync) hold the trace to it.
def _sha(path) -> str:
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def lipsync_entry(root, episode: str, script: dict, line_id: str, start_s: float, actor_ids: list):
    """The placement of one line on a shot, or None when its speaker is not drawn in the shot (the narrator, or a character off screen)."""
    line = next((l for l in script.get("lines", []) if l.get("id") == line_id), None)
    if line is None:
        raise CalmError("LIPSYNC-LINE", f"line {line_id} is not in the script")
    spk = line.get("speaker")
    if spk not in actor_ids:
        return None
    vdir = Path(root) / "work" / "voice" / episode
    vp = vdir / "visemes" / f"{line_id}.json"
    if not vp.is_file():
        raise CalmError("LIPSYNC-NO-TRACK", f"{spk} speaks {line_id} on screen but {vp} does not exist: run `uv run tools/voice.py visemes <episode-dir>` after the voice stage")
    tr = json.loads(vp.read_text(encoding="utf-8"))
    take = next((vdir / n for n in (f"{line_id}.trimmed.wav", f"{line_id}.wav") if (vdir / n).is_file()), None)
    if take is not None and tr.get("source", {}).get("audio_sha256") != _sha(take):
        raise CalmError("LIPSYNC-STALE-TRACK", f"{vp.name} was measured on other audio than {take.name} (a re-voiced or re-trimmed take): run `voice.py visemes` again")
    return {"actor": spk, "line": line_id, "start_s": round(float(start_s), 4), "ramp_s": tr.get("ramp_s", 0.04), "track_sha256": tr["source"]["audio_sha256"][:16],
            "keys": [{"t": float(k["t"]), "id": k["id"]} for k in tr["keys"]]}


def set_lipsync(c: dict, entries: list) -> dict:
    """Mark the calm description voice-aware: entries = lipsync_entry results (None dropped). Returns c."""
    c["lipsync"] = [e for e in entries if e]
    return c


# ------------------------------------------------------------------ calm dict -> shot folder
_FIND = """import json, sys
from pathlib import Path
_here = Path(__file__).resolve()
_tools = next(p / 'tools' for p in _here.parents if (p / 'tools' / 'calm.py').is_file())
sys.path.insert(0, str(_tools))
import calm
C = json.loads((_here.parent.parent / 'calm.json').read_text(encoding='utf-8'))
"""


def camera_py(c: dict) -> str:
    return ('"""Camera data of a calm shot: read from calm.json (written by tools/calm.py; edit the template parameters, not this file)."""\n'
            + _FIND + "BEATS, SHOTS, CUTS, EXTRA = calm.camera_data(C)\n")


def spec_py(c: dict) -> str:
    return ('"""Shot-spec of a calm shot: built from calm.json by tools/calm.py (build_spec)."""\n'
            + _FIND + "def build(plan, shot, lib):\n    return calm.build_spec(C, plan, shot)\n")



def camera_data(c: dict):
    cam = c["camera"]
    em = c["actors"][0]["emotion"]
    dur = c["duration_s"]
    beats = [{"id": "b1", "start": 0.0, "end": dur, "treatment": "A", "emotion": em}]
    shots = [{"shot": "s1", "beat": "b1", "t0": 0.0, "t1": dur, "size": SIZES[cam["size1"]][1], "angle": "eye", "lens_mm": SIZES[cam["size1"]][2], "move": cam["move"],
              "cam0": cam["cam0"], "cam1": cam["cam1"],
              "start_frame_desc": f"{c['template'].replace('_', ' ')}: {', '.join(a['id'] for a in c['actors'])} at the start of the move ({cam['size0']}, target {cam['target']})",
              "end_frame_desc": f"the end of the move ({cam['size1']}), expression {c['actors'][0]['expression_to']}",
              "why": cam["why"], "serves_emotion": em, "safe_boxes": cam["safe_boxes"], "catalogue_camera": f"calm-{c['template']}"}]
    extra = {"lens_rule": "2D flat camera: x, y, z and focal only (F9).", "line_180": "one shot, no cut", "screen_direction": "the kit's own handedness; nobody crosses the line",
             "format": "calm"}
    return beats, shots, {}, extra


def _planes(kit: dict, cam0: dict, beat_base: dict) -> list:
    return beat_base["depth_planes"]   # the camera keeps the kit's z, so the layer parallax factors are the ones the gated smoke shot declared


def build_spec(c: dict, plan: dict, shot: dict) -> dict:
    """The shot-spec dict (stage spec) for a calm shot, from the kit's gated spec data and the template's acting."""
    dur = c["duration_s"]
    first = c["actors"][0]
    kit = kit_of(first["kit"])
    base = copy.deepcopy(kit["spec"]["beat_base"])
    em_name = first["emotion"] if first["emotion"] in EMOTIONS else "calm"
    lo, hi = BLINK_BANDS.get(em_name, (0, 30))
    beat = base
    beat.update({"id": "b1", "start": 0.0, "end": dur, "title": c["template"].replace("_", " "),
                 "treatment": "A", "treatment_reason": f"calm format ({c['template'].replace('_', ' ')}): clear line, depth and a slow camera carry one subject; no extra frame-rate effect",
                 "camera_move_pct": c["camera"]["move_pct"], "poses": [], "texts": [], "holds": []})
    beat.pop("title", None)
    beat["depth_planes"] = _planes(kit, c["camera"]["cam0"], base)
    beat["light"]["serves_emotion"] = em_name
    beat["elements"] = [{"id": "back-wall", "static_s": 0.0}, {"id": "drawers", "static_s": round(min(dur, 4.0), 2)}]
    if c["camera"].get("locked_because"):
        beat["locked_camera_because"] = c["camera"]["locked_because"]
    beat["emotion"] = {"primary": em_name, "intensity": first["intensity"], "shown": "visible", "peak_s": first["peak_s"], "cause": c["cause"], "character": first["id"]}
    et = beat["emotion_track"]
    et["eyes"].update({"gaze_target": first["gaze_to_label"], "darts_per_s": first["darts_per_s"], "blink_per_min": [lo, hi]})
    et["face"]["aus"] = {k: v for k, v in first["expr_to"]["aus"].items() if v}
    for ch in ("sfx",):
        if ch in et:
            et[ch] = [{**s, "at_s": min(float(s.get("at_s", 0.0)), round(dur - 0.1, 2))} for s in et[ch]]
    pdef = pose_of(kit, first["pose_name"])
    sp = copy.deepcopy(pdef.get("spec_pose") or {"character": first["id"], "pose_id": first["pose_name"], "angle": "front", "contacts": []})
    for ct in sp.get("contacts", []):
        ct["t0"], ct["t1"] = 0.0, dur
    beat["poses"] = [sp]
    beat["actions"] = [{"part": "eyes", "anticipation_frames": 3, "what": "dart between the look-at points"}] + [a for a in beat.get("actions", []) if a.get("part") != "eyes"][:1]
    beat["interactions"] = beat.get("interactions", [])[:2]
    if dur >= 6:   # one interaction per 3 s (SPEC need = dur // 3)
        beat["interactions"] += [{"cause": "the lamp swings on its chain", "effect": "the light slides across the face and the shelves behind", "kind": "light"}] * int(dur // 3 - len(beat["interactions"]) + 1)
    spec = {
        "episode": f"{shot['id']} (calm {c['template']}, {dur:g} s)", "format": "calm", "fps": FPS, "canvas": "1080x1920", "duration_s": dur,
        "camera_plan_file": f"{shot['rel']}/camera-plan.json",
        "actors": [kit["spec"]["actor_entry"]], "characters": [copy.deepcopy(kit["spec"]["character"])],
        "physics_profiles": copy.deepcopy(kit["spec"]["physics_profiles"]), "props": copy.deepcopy(kit["spec"]["props"]),
        "beats": [beat], "transitions": [], "camera_plan": [],
        "renderer": {"source": f"{shot['rel']}/build/index.html", "preview": f"the recorded video {shot['rel']}/out/{shot['id']}.mp4",
                     "clock": "frame counter (renderFrame(f)), never wall-clock", "rig_trace": "trace-multi.js actorTraceFrame",
                     "masks": f"{shot['rel']}/out/masks/{{line,shadow}}/{first['id']}", "hands": "catalogue grips of the kit; 2D arms of constant drawn length"},
    }
    for s in plan["shots"]:
        spec["camera_plan"].append({k: s[k] for k in ("shot", "beat", "size", "angle", "lens_mm", "move", "start_frame_desc", "end_frame_desc", "dur_s", "why", "serves_emotion", "safe_boxes", "thumbnail")})
    if len(c["actors"]) > 1:
        _two_actor_spec(c, spec, beat)
    if "lipsync" in c:
        spec["lipsync"] = copy.deepcopy(c["lipsync"])   # voice-aware shot: the rig gate holds every mouth to it (LIPSYNC-ACTIVE / LIPSYNC-SILENT)
    return spec


def _two_actor_spec(c: dict, spec: dict, beat: dict):
    """Second actor: its character rig, a per-actor emotion block, and the no-touch proof (hand outlines never closer than min_gap_px)."""
    kits = [kit_of(a["kit"]) for a in c["actors"]]
    dur = c["duration_s"]
    spec["actors"] = []
    spec["characters"] = []
    spec["physics_profiles"] = {}
    spec["props"] = []
    ae = {}
    for i, (a, kit) in enumerate(zip(c["actors"], kits)):
        entry = copy.deepcopy(kit["spec"]["actor_entry"])
        entry.update({"layer": i, "screen_side": "left" if i == 0 else "right"})
        spec["actors"].append(entry)
        spec["characters"].append(copy.deepcopy(kit["spec"]["character"]))
        spec["physics_profiles"].update(copy.deepcopy(kit["spec"]["physics_profiles"]))
        spec["props"] += [p for p in copy.deepcopy(kit["spec"]["props"]) if p["id"] not in {q["id"] for q in spec["props"]}]
        bb = copy.deepcopy(kit["spec"]["beat_base"])
        em = a["emotion"] if a["emotion"] in EMOTIONS else "calm"
        lo, hi = BLINK_BANDS.get(em, (0, 30))
        et = bb["emotion_track"]
        et["eyes"].update({"gaze_target": a["gaze_to_label"], "darts_per_s": a["darts_per_s"], "blink_per_min": [lo, hi]})
        et["face"]["aus"] = {k: v for k, v in a["expr_to"]["aus"].items() if v}
        et["sfx"] = [{**s, "at_s": min(float(s.get("at_s", 0.0)), round(dur - 0.1, 2))} for s in et.get("sfx", [])]
        have = {x.get("caster") for x in beat["cast_shadows"]}
        beat["cast_shadows"] += [copy.deepcopy(x) for x in bb["cast_shadows"] if x.get("caster") == a["id"] and a["id"] not in have]   # every actor casts its own mass-proxy shadow (R-355)
        ae[a["id"]] = {"emotion": {"primary": em, "intensity": a["intensity"], "shown": "visible", "peak_s": a["peak_s"], "cause": c["cause"], "character": a["id"]}, "emotion_track": et}
    beat["actor_emotions"] = ae
    beat["lead_actor"] = next((a["id"] for a in c["actors"] if a.get("role") == "speaker"), c["actors"][0]["id"])
    beat["actors"] = [a["id"] for a in c["actors"]]
    beat["depth_z"] = {a["id"]: float(k["actor"]["z"]) for a, k in zip(c["actors"], kits)}
    far_first = sorted(beat["actors"], key=lambda i: -beat["depth_z"][i])
    beat["draw_order"] = [{"order": [t for i in far_first for t in (f"{i}:body", f"{i}:arms")],   # exactly what the engine draws: actors far to near, each body then its arms
                           "why": "the farther person is drawn first, then the nearer; each body then its arms, so no hand is drawn over the other person's hand (they stand apart)"}]
    beat["actors_apart_because"] = "calm two-shot: the pair stands more than two reaches apart, hands never meet"
    beat["poses"] = []
    for a, kit in zip(c["actors"], kits):
        sp = copy.deepcopy(pose_of(kit, a["pose_name"]).get("spec_pose") or {"character": a["id"], "pose_id": a["pose_name"], "angle": "front", "contacts": []})
        for ct in sp.get("contacts", []):
            ct["t0"], ct["t1"] = 0.0, dur
        beat["poses"].append(sp)
    a0, a1 = c["actors"][0]["id"], c["actors"][1]["id"]
    spec["actor_interactions"] = [{"id": "no-touch-b1", "kind": "apart", "beat": "b1", "t0": 0.0, "t1": dur, "a": {"actor": a0, "hands": ["L", "R"]}, "b": {"actor": a1, "hands": ["L", "R"]},
                                   "min_gap_px": 12, "why": "the owner 2026-10-23: no touch between unrelated men and women; the pair stands apart and the counter or the air is between their hands (measured on the drawn hand outlines every frame)"}]


def shot_json(c: dict) -> dict:
    kits = [kit_of(a["kit"]) for a in c["actors"]]
    actors, new = [], []
    for a, kit in zip(c["actors"], kits):
        ent = copy.deepcopy(kit["actor"])
        cat = ent["catalogue"]
        cat["expression_dir"] = a["expr_dir"]
        cat["expressions"] = a["expr_files"]
        ent["uses"]["refs"] = list(dict.fromkeys([r for r in ent["uses"]["refs"] if "/expr" not in r] + a["expr_refs"]))
        ent["layer"] = len(actors)
        actors.append(ent)
        new += kit.get("new", [])
    return {
        "id": c["id"], "title": f"{c['id']}: calm {c['template'].replace('_', ' ')} ({', '.join(a['id'] for a in c['actors'])}, {c['duration_s']:g} s)", "format": "calm",
        **({"event": True} if c.get("event") else {}),   # format v2: the plan marks this scene as a shown event (the shot gate uses the action ceilings)
        "fps": FPS, "duration_s": c["duration_s"], "canvas": CANVAS, "world": SETS[c["set"]]["world"], "actors": actors, "new": list(dict.fromkeys(new)),
        "cuts": [], "smears": [], "fonts": FONTS, "scene_files": ["scene/calm-scene.js"] + [f"scene/kit-{a['kit']}.js" for a in c["actors"]], "library": LIBRARY,
        "record": {"fps": FPS, "codec": "h264_nvenc", "size": "1080x1920"}, "review": {"hands_every": 3, "faces_every": 6, "props_every": 6, "frames_every": 6},
        "calm": {"template": c["template"], "set": c["set"], "actors": c["actors"], "life": c.get("life", LIFE), "xp": c.get("xp", {}), **({"depth": c["depth"]} if c.get("depth") else {}), **({"grade": c["grade"]} if c.get("grade") else {}), "lipsync": c.get("lipsync", []),
                 "camera": c["camera"]},   # the camera is in shot.json so shot.py's input hashes see a changed framing (size, push, pan) and re-plan, re-build and re-record (it was only in plan/camera.py's runtime read of calm.json: a changed size reused the old video)
    }


def write_shot(c: dict, shot_dir: Path) -> list[Path]:
    """Write the shot folder. Never overwrites a shot that already has a recorded video (a finished shot is not rewritten by a template)."""
    sd = Path(shot_dir)
    if c.get("kind") == "card":
        if c.get("template") == "intro_freeze":
            import calm_intro
            return calm_intro.write_shot(c, sd)
        import calm_cards
        return calm_cards.write_shot(c, sd)
    rep = sd / "gate" / "report.json"
    if rep.is_file() and json.loads(rep.read_text(encoding="utf-8")).get("verdict") == "PASS":
        raise CalmError("CALM-EXISTS", f"{sd} passed its gates: a finished shot is not rewritten by a template (use a new id)")
    c = {**c, "id": sd.name}
    for sub in ("plan", "scene"):
        (sd / sub).mkdir(parents=True, exist_ok=True)
    out = []
    (sd / "calm.json").write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8"); out.append(sd / "calm.json")
    (sd / "shot.json").write_text(json.dumps(shot_json(c), ensure_ascii=False, indent=1), encoding="utf-8"); out.append(sd / "shot.json")
    (sd / "plan" / "camera.py").write_text(camera_py(c), encoding="utf-8"); out.append(sd / "plan" / "camera.py")
    (sd / "plan" / "spec.py").write_text(spec_py(c), encoding="utf-8"); out.append(sd / "plan" / "spec.py")
    shutil.copy2(TPL_DIR / "scene" / "calm-scene.js", sd / "scene" / "calm-scene.js"); out.append(sd / "scene" / "calm-scene.js")
    for a in c["actors"]:
        shutil.copy2(TPL_DIR / "kits" / f"{a['kit']}.js", sd / "scene" / f"kit-{a['kit']}.js"); out.append(sd / "scene" / f"kit-{a['kit']}.js")
    return out


# ------------------------------------------------------------------ validation of a written shot
def validate_calm(c: dict) -> list[str]:
    """Static checks on a calm description (no browser): the calm rules the shot must satisfy before it is recorded."""
    f = []
    d = c.get("duration_s", 0)
    dmax = MAX_CHOICE_S if c.get("template") == "choice_split" else MAX_S   # C4: the choice sequence lasts as long as the narrator reads the question, both choices and the hook
    if not (MIN_S - 1e-9 <= d <= dmax + 1e-9):
        f.append(f"CALM-DURATION {d} s outside {MIN_S}..{dmax} s")
    if abs(d * FPS - round(d * FPS)) > 1e-6:
        f.append(f"CALM-DURATION {d} s is not on the {FPS} fps grid")
    if c.get("kind") == "card":
        return f
    acts = c.get("actors", [])
    if not 1 <= len(acts) <= 2:
        f.append(f"CALM-SUBJECTS {len(acts)} actors: one subject per frame, two only in a two-shot")
    if len(acts) == 2 and c.get("template") != "two_shot":
        f.append("CALM-SUBJECTS two actors outside the two_shot template")
    if len(acts) == 2:
        xs = [(ck.load_kit(a["kit"]).get("root") or {}).get("X") or 0.0 for a in acts]
        gap = abs((xs[0] + acts[0]["root_dx"]) - (xs[1] + acts[1]["root_dx"]))
        if gap < HAND_REACH_M * 1.2:
            f.append(f"CALM-NO-TOUCH the two roots are {gap:.2f} m apart, closer than 1.2 reaches ({HAND_REACH_M * 1.2:.2f} m): they could touch")
    cam = c.get("camera", {})
    if cam.get("move_pct", 0) < 2.0 and not cam.get("locked_because"):
        f.append("CALM-CAMERA no camera movement and no locked_because")
    if cam.get("move_pct", 0) > 40:
        f.append(f"CALM-CAMERA move of {cam['move_pct']} % is not calm (a push or drift stays under 40 %)")
    for e in c.get("lipsync", []):
        if e["actor"] not in [a["id"] for a in acts]:
            f.append(f"CALM-LIPSYNC {e['line']} is spoken by {e['actor']}, who is not in this shot")
        end = e["start_s"] + e["keys"][-1]["t"]
        if e["start_s"] < 0 or end > d + 1e-6:
            f.append(f"CALM-LIPSYNC {e['line']} runs {e['start_s']:.2f}..{end:.2f} s on a {d:g} s shot: the mouth would be cut off mid-word")
    for a in acts:
        for k in ("expr_from", "expr_to"):
            for key in a[k]["aus"]:
                if a[k]["aus"][key] > 1.0:
                    f.append(f"CALM-EXPRESSION AU{key} above 1.0")
    return f


# ------------------------------------------------------------------ CLI
def parse_kv(args: list[str]) -> dict:
    out = {}
    for a in args:
        if "=" in a and not a.startswith("--"):
            k, v = a.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def cmd_list() -> str:
    lines = ["TEMPLATES (actor shots)"]
    for n, (_, doc, need) in ACTOR_TEMPLATES.items():
        lines.append(f"  {n:18s} {doc}  [needs: {', '.join(need)}]")
    lines.append("TEMPLATES (cards): " + ", ".join(CARD_TEMPLATES))
    lines.append("KITS: " + (", ".join(ck.list_kits()) or "none"))
    for k in ck.list_kits():
        kit = ck.load_kit(k)
        lines.append(f"  {k}: poses {', '.join(kit.get('poses', {}))}; expressions {', '.join(kit.get('expressions', {}))}")
    lines.append("CHARACTERS WITHOUT A KIT: " + ", ".join(c for c in [x.split()[0] for x in ck.status().splitlines() if "no kit" in x]))
    lines.append("SETS: " + ", ".join(SETS))
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("list", "make", "validate"):
        print(__doc__)
        return 2
    try:
        if argv[0] == "list":
            print(cmd_list())
            return 0
        if argv[0] == "validate":
            c = json.loads((Path(argv[1]) / "calm.json").read_text(encoding="utf-8"))
            fails = validate_calm(c)
            for x in fails:
                print("FAIL [" + x.split(" ", 1)[0] + "] " + x.split(" ", 1)[1])
            print("PASS" if not fails else "FAIL")
            return 1 if fails else 0
        if len(argv) < 3:
            print(__doc__)
            return 2
        template, sd = argv[1], Path(argv[2]).resolve()
        params = parse_kv(argv[3:])
        if "--params" in argv:
            params = {**json.loads(Path(argv[argv.index("--params") + 1]).read_text(encoding="utf-8")), **params}
        params.setdefault("id", sd.name)
        c = resolve(template, params)
        fails = validate_calm(c)
        if fails:
            raise CalmError(fails[0].split(" ", 1)[0], "; ".join(f.split(" ", 1)[1] for f in fails))
        files = write_shot(c, sd)
        print(f"OK {template} -> {sd} ({len(files)} files, {c['duration_s']:g} s)")
        if "--run" in argv:
            import subprocess
            r = subprocess.run(["uv", "run", str(TOOLS / "shot.py"), "all", str(sd)], env={**os.environ, "PYTHONUTF8": "1"})
            return r.returncode
        return 0
    except CalmError as e:
        print(e)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
