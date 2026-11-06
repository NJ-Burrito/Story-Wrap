"""Shot-spec data for the smoke shot (stage spec): Partner alone through the multi-actor engine. build(plan, shot, lib) returns the spec dict.
Gate: quality_gate.py spec. One actor, one beat of 2 s; the multi-actor fields (actors[], per-actor emotion) are filled so the same file shape serves two actors."""

def part(name, pivot, own=True, follows=None, lag=None, **kw):
    p = {"name": name, "pivot": pivot, "own_curve": own}
    if follows: p["follows"] = follows
    if lag is not None: p["lag_frames"] = lag
    p.update(kw); return p

PARTS = [
    part("pelvis", "root"), part("torso", "pelvis"), part("clavicle-L", "sternal-notch", follows="torso", lag=1), part("clavicle-R", "sternal-notch", follows="torso", lag=1),
    part("neck", "neck-base", follows="torso", lag=1), part("head", "neck-top", follows="torso", lag=2),
    part("eyes", "head"), part("brows", "head"), part("lids", "head"), part("nose", "head", own=False), part("lips", "head"),
    part("helmet", "head", follows="head", lag=0, note="rigid, rides the head with zero lag (physics partner-v1)"), part("lamp-flame", "helmet", follows="head", lag=2),
    part("sweater", "torso", follows="torso", lag=1), part("aguayo", "sweater", follows="sweater", lag=3), part("aguayo-corner", "aguayo", follows="aguayo", lag=3),
    part("upper-arm-L", "shoulder-L", follows="clavicle-L", lag=1), part("forearm-L", "elbow-L", follows="upper-arm-L", lag=2),
    part("palm-L", "wrist-L", follows="forearm-L", lag=1, hand_grip="bread"), part("thumb-L", "palm-L"), part("finger-index-L", "palm-L"),
    part("finger-middle-L", "palm-L"), part("finger-ring-L", "palm-L", follows="finger-middle-L", lag=1), part("finger-little-L", "palm-L", follows="finger-ring-L", lag=1),
    part("upper-arm-R", "shoulder-R", follows="clavicle-R", lag=1), part("forearm-R", "elbow-R", follows="upper-arm-R", lag=2),
    part("palm-R", "wrist-R", follows="forearm-R", lag=1), part("thumb-R", "palm-R"), part("finger-index-R", "palm-R"),
    part("finger-middle-R", "palm-R"), part("finger-ring-R", "palm-R", follows="finger-middle-R", lag=1), part("finger-little-R", "palm-R", follows="finger-ring-R", lag=1),
]
ANGLES = ("front", "three-quarter-L", "three-quarter-R")
def lo(order, angles=ANGLES): return {a: order for a in angles}
BREAD_LAYERS = ["palm-L", "finger-little-L", "finger-ring-L", "finger-middle-L", "finger-index-L", "thumb-L", "bread"]
ATT = [
    {"id": "bread-in-palm", "child": "bread", "parent": "palm-L", "parent_anchor": "bread_rest_L", "kind": "held", "contact_points": ["bread_grip"], "max_gap_px": 4,
     "layer_order": lo(BREAD_LAYERS), "why": "catalogue hands v2 give-open-L: palm up, the loaf rests on the palm in front of everything (bible catalogue_hands 1)"},
    {"id": "helmet-on-head", "child": "helmet", "parent": "head", "parent_anchor": "helmet_crown", "kind": "garment", "contact_points": ["helmet_band"], "max_gap_px": 4,
     "layer_order": lo(["head", "fringe", "helmet"]), "why": "the dome rides the head with zero lag; the fringe shows under the brim"},
    {"id": "lamp-on-helmet", "child": "lamp-flame", "parent": "helmet", "parent_anchor": "lamp_mount", "kind": "prop", "contact_points": ["lamp_hook"], "max_gap_px": 4,
     "layer_order": lo(["helmet", "lamp"]), "why": "the carbide lamp sits on the brow of the helmet; the flame is a VFX on top of it"},
    {"id": "aguayo-knot", "child": "aguayo", "parent": "sweater", "parent_anchor": "knot_L", "kind": "garment", "contact_points": ["knot_tie"], "max_gap_px": 4,
     "layer_order": lo(["sweater", "aguayo", "knot"]), "why": "the carrying cloth is knotted at the left shoulder and runs across the chest to the right hip"},
]
CHAR = {
    "id": "partner", "parts": PARTS, "physics_profile": "partner-v1", "model_ref": {"id": "partner/model", "version": "1.0"}, "face_ref": {"id": "partner/face", "version": "2.0"},
    "build": {"silhouette": "merged: body (sweater, aguayo, neck, head) once, arms and hands once", "interior_lines": "only at real overlaps, following the form (F11)"},
    "catalogue": "catalogue/characters/partner/index.json",
    "rest_proportions": {"head_h": 100, "shoulder_w": 180, "neck_len": 30, "upper_arm": 140, "forearm": 112, "hand": 80, "thigh": 162, "shank": 152},
    "anchors": {"clavicle_L": [85, -247], "clavicle_R": [-85, -247], "neck_base": [0, -257], "head_unit_px": 100, "space": "body space, 1 HU = 100 px, origin pelvis centre"},
    "covers_hair": False, "attachments": ATT,
    "handedness": "gives and greets with the LEFT hand; takes, climbs and walls with the RIGHT (catalogue hands v2 authored per side, no mirrors)", "hands_ref": "catalogue/characters/partner/v2/hands",
    "emotion_profile": {"baseline": {"blink_per_min": 12, "gaze_habit": "looks up and away, then at the person"},
                        "display_rules": {"family": "open", "peer": "direct", "authority": "polite and brief", "stranger": "warm, a little shy"},
                        "hidden_feeling_channel": "right hand", "leak": {"fear": "the right hand tightens on the ledge", "shame": "eyes break away"},
                        "never_uses": ["pointing with the right hand", "giving with the right hand"]},
    "face_controls": ["AU1", "AU2", "AU4", "AU5", "AU6", "AU7", "AU9", "AU12", "AU15", "AU20", "AU23", "AU26"],
}
PROFILES = {
    "partner-v1": {"extends": "_human-default", "kind": "character", "mass_class": "light", "bone_lengths_tolerance_pct": 2, "source": "catalogue/characters/partner/physics.json"},
    "rigid": {"kind": "object", "material": "rigid", "mass_class": "light", "stretch": {"max_scale": 1.0}},
    "soft": {"kind": "object", "material": "soft body", "mass_class": "light", "squash_pct": [5, 15]},
    "hinged": {"kind": "object", "material": "one-axis hinge", "mass_class": "light", "limits_deg": {"open": [0, 110]}},
}
PROPS = [{"id": "bread", "physics_profile": "soft", "mass_class": "light", "catalogue": "partner/hand/give-open-L (holding: bread)"},
         {"id": "jar", "physics_profile": "rigid", "mass_class": "medium"}, {"id": "lamp", "physics_profile": "rigid", "mass_class": "medium", "note": "pendulum on a chain"},
         {"id": "drawers", "physics_profile": "hinged", "mass_class": "medium"}]

def planes(beat):
    sh = next(x for x in plan["shots"] if x["beat"] == beat)
    cz = sh["cam0"]["z"]; subj = 2.56
    cand = [("back-wall", 8.0), ("aisle", 5.6), ("back-unit", 3.6), ("drawers-shelves", 3.3), ("partner", 2.56), ("counter-props", 2.4), ("counter-front", 2.2), ("hanging-tags-fg", 1.7), ("post-fg", 1.62)]
    out = []
    for pid, z in cand:
        if z - cz < 0.25: continue
        par = round((subj - cz) / (z - cz), 2)
        if not out or abs(par - out[-1]["parallax"]) >= 0.12:
            out.append({"id": pid, "parallax": par, "z_m": z})
    return out

def light(kd, kc, size, fd, fc, rd, rc, serves, src):
    return {"key": {"dir": kd, "color": kc, "source": src, "size": size}, "fill": {"dir": fd, "color": fc}, "rim": {"dir": rd, "color": rc}, "serves_emotion": serves}

plan = None

def build(plan_in, shot, lib):
    global plan
    plan = plan_in
    ID = shot["id"]
    B = [{"id": "b1", "start": 0.0, "end": 2.0, "treatment": "A", "treatment_reason": "a quiet offer: clear line, depth and smooth ones carry the warmth",
          "rates": {"partner": "ones", "props": "ones", "camera": "ones"}, "depth_planes": planes("b1"),
          "light": light("high-right-front", "#ffb36b", 0.12, "left", "#3c4e86", "back-left", "#ffd08a", "joy", "oil lamp on a chain, swaying in the draught"),
          "cast_shadows": [{"caster": "partner", "receiver": "back-unit", "source": "mass_proxy", "proxy": "partner-proxy", "light": "key", "self_shadow": True,
                            "contacts": [{"a": "right-heel", "b": "wall"}], "edge": "hard", "drawn": "one flat 2D shape: the union of the mass proxy projected from the lamp, no blur (R-380)"},
                           {"caster": "jar", "receiver": "counter-top", "source": "mass_proxy", "proxy": "props-proxy", "light": "key", "edge": "hard"}],
          "interactions": [{"cause": "Partner's raised left palm", "effect": "the loaf's flat shadow crosses his sweater and the lamp light catches the crust", "kind": "contact", "carries_emotion": True},
                           {"cause": "draught through the office", "effect": "dust drifts in the lamp light and the lamp swings", "kind": "wind"}],
          "actions": [{"part": "forearm-L", "anticipation_frames": 4, "overshoot": False, "what": "lift the open palm with the loaf"}, {"part": "eyes", "anticipation_frames": 3, "what": "dart from the loaf to the person"}],
          "elements": [{"id": "back-wall", "static_s": 0.0}, {"id": "drawers", "static_s": 1.2}], "holds": [], "camera_move_pct": 6,
          "poses": [{"character": "partner", "pose_id": "offer-bread", "new": True, "build_up_sheet": "partner/sheet/03-sketch@1.0", "angle": "front",
                     "contacts": [{"part": "palm-L", "target": "bread", "t0": 0.0, "t1": 2.0, "kind": "grip"}]}],
          "texts": [],
          "emotion": {"primary": "joy", "intensity": 0.55, "shown": "visible", "peak_s": 1.25, "cause": "he is about to give someone bread", "character": "partner"},
          "emotion_track": {"eyes": {"gaze_target": "the loaf, then the person", "darts_per_s": 1.5, "blink_per_min": [12, 18], "onset_s": 0.0, "lids": "lifted", "iris": "mid"},
                            "face": {"aus": {"1": 0.4, "6": 0.5, "12": 0.7, "26": 0.4}, "asymmetry": 0.05, "onset_s": 0.08},
                            "body": {"effort": {"weight": "light", "time": "sustained", "space": "direct", "flow": "free"}, "posture": "weight forward, chest open, left palm lifted", "onset_s": 0.17},
                            "voice": {"line": None, "breath": "easy", "pace": "base", "pitch_st": 1, "energy": "warm", "style_text": "a soft hum, Andean vowels"},
                            "action": {"from_emotion": "lifts the loaf on an open palm", "obstacle": "none", "outcome": "completed"},
                            "environment": {"response": "lamp sways gently, dust drifts in the light", "interaction_ref": "draught through the office"},
                            "colour": {"hue_family": "warm amber", "sat": "mid", "value": "mid", "key_temp": "warm", "fill_temp": "cool"},
                            "sfx": [{"at_s": 0.0, "what": "harbour room tone, distant water"}, {"at_s": 0.9, "what": "cloth rustle as the arm lifts"}]},
          "actor_emotions": {}}]
    # one actor: the shared emotion block is his; actor_emotions stays empty (two actors: one entry each, see kb/quality/shot-spec.schema.json)
    CAMP = []
    for s in plan["shots"]:
        e = {k: s[k] for k in ("shot", "beat", "size", "angle", "lens_mm", "move", "start_frame_desc", "end_frame_desc", "dur_s", "why", "serves_emotion", "safe_boxes", "thumbnail")}
        CAMP.append(e)   # the camera catalogue has no partner entries yet: the camera is new in this shot (a new catalogue entry comes with the first real Partner shot)
    del B[0]["actor_emotions"]
    return {"episode": f"{ID} (smoke test of the multi-actor engine: Partner alone, 2 s)", "fps": 24, "canvas": "1080x1920", "duration_s": 2.0,
            "camera_plan_file": f"{shot['rel']}/camera-plan.json",
            "actors": [{"id": "partner", "module": "partner", "depth_z": 2.56, "layer": 0,
                        "catalogue_refs": ["partner/model@1.0", "partner/hand-model@1.0", "partner/hand/give-open-L@1.0", "partner/physics/partner-v1@1.0"]}],
            "characters": [CHAR], "physics_profiles": PROFILES, "props": PROPS, "beats": B, "transitions": [], "camera_plan": CAMP,
            "renderer": {"source": f"{shot['rel']}/build/index.html", "preview": f"the recorded video {shot['rel']}/out/{ID}.mp4", "clock": "frame counter (renderFrame(f)), never wall-clock",
                         "rig_trace": "trace-multi.js actorTraceFrame", "masks": f"{shot['rel']}/out/masks/{{line,shadow}}/partner", "hands": "catalogue partner v2 grips (give-open-L, wall-flat-R, hook-ledge-R); 2D arms of constant drawn length"}}
