"""Shot-spec data for this shot (stage spec). build(plan, shot, lib) returns the spec dict; the helpers
(planes, light, shadow, part) stay here because they carry this shot's choices. Gate: quality_gate.py spec."""
CAT = "hero/pose/{}@2.0"
CAT3 = "hero/pose/{}@3.0"

def part(name, pivot, own=True, follows=None, lag=None, **kw):
    p = {"name": name, "pivot": pivot, "own_curve": own}
    if follows: p["follows"] = follows
    if lag is not None: p["lag_frames"] = lag
    p.update(kw); return p

PARTS = [
    part("pelvis", "root"), part("torso", "pelvis"), part("clavicle-L", "sternal-notch", follows="torso", lag=1), part("clavicle-R", "sternal-notch", follows="torso", lag=1),
    part("neck", "neck-base", follows="torso", lag=1), part("head", "neck-top", follows="torso", lag=2),
    part("eyes", "head"), part("brows", "head"), part("lids", "head"), part("nose", "head", own=False), part("lips", "head"),
    part("cap", "head", own=False), part("hijab", "cap", follows="head", lag=3, note="head-cloth and drape are ONE garment outline (F11)"), part("pin", "hijab", own=False),
    part("scarf-end-L", "shoulder-L", follows="hijab", lag=4),
    part("coat", "torso", follows="torso", lag=1), part("coat-tags", "coat", follows="coat", lag=3),
    part("upper-arm-L", "shoulder-L", follows="clavicle-L", lag=1), part("forearm-L", "elbow-L", follows="upper-arm-L", lag=2),
    part("palm-L", "wrist-L", follows="forearm-L", lag=1, hand_grip="pen"), part("thumb-L", "palm-L"), part("finger-index-L", "palm-L"),
    part("finger-middle-L", "palm-L"), part("finger-ring-L", "palm-L", follows="finger-middle-L", lag=1), part("finger-little-L", "palm-L", follows="finger-ring-L", lag=1),
    part("upper-arm-R", "shoulder-R", follows="clavicle-R", lag=1), part("forearm-R", "elbow-R", follows="upper-arm-R", lag=2),
    part("palm-R", "wrist-R", follows="forearm-R", lag=1, hand_grip="card then tag"), part("thumb-R", "palm-R"), part("finger-index-R", "palm-R"),
    part("finger-middle-R", "palm-R"), part("finger-ring-R", "palm-R", follows="finger-middle-R", lag=1), part("finger-little-R", "palm-R", follows="finger-ring-R", lag=1),
]
ANGLES = ("three-quarter-R", "three-quarter-L", "front")
ANG5 = ANGLES + ("top",)
def lo(order, angles=ANGLES): return {a: order for a in angles}
ATT = [
    {"id": "pen-in-hand", "child": "pen", "parent": "palm-L", "parent_anchor": "pen_rest_L", "kind": "held", "contact_points": ["pen_grip"], "max_gap_px": 4,
     "layer_order": lo(["finger-middle-L", "palm-L", "pen", "thumb-L", "finger-index-L"], ANG5),
     "why": "catalogue hands/tripod-pen-L@3.0: curled fingers under the palm, the barrel over the web, thumb pad and index pad closed over the barrel (F15)"},
    {"id": "card-pressed", "child": "card", "parent": "finger-index-R", "parent_anchor": "press_R", "kind": "held", "contact_points": ["card_press"], "max_gap_px": 4,
     "layer_order": lo(["card", "palm-R", "finger-index-R"], ANG5), "active": "b1", "why": "press-card-R@3.0: index and middle pads hold the card's lower-right corner; paper under the hand (R-392)"},
    {"id": "bag-tag-pinch", "child": "bag-tag", "parent": "finger-index-R", "parent_anchor": "pinch_R", "kind": "held", "contact_points": ["bag_tag_grip"], "max_gap_px": 4,
     "layer_order": {"front": ["thumb-R", "bag-tag", "palm-R", "finger-index-R"]}, "active": "b4 from the grip at 7.375 s (the front angle of s6)",
     "why": "pinch-tag-R@3.0: the front faces her, thumb pad on the front (behind for the camera), index pad on the back (in front)"},
    {"id": "tag-on-string", "child": "bag-tag", "parent": "tag-string", "parent_anchor": "string_end", "kind": "prop", "contact_points": ["tag_hole"], "max_gap_px": 4,
     "layer_order": {"three-quarter-L": ["bag", "tag-string", "bag-tag"], "front": ["bag", "tag-string", "bag-tag"], "pov": ["bag", "tag-string", "bag-tag"]}, "why": "string tied through the tag hole; constant length 0.10 m (R-313)"},
    {"id": "cap-on-head", "child": "cap", "parent": "head", "parent_anchor": "cap_band_front", "kind": "garment", "contact_points": ["cap_band"], "max_gap_px": 4,
     "layer_order": lo(["head", "cap", "hijab"]), "why": "under-cap first; its band shows under the cloth edge; the hairline is hidden (R-354)"},
    {"id": "cloth-wrap", "child": "hijab", "parent": "cap", "parent_anchor": "cap_crown", "kind": "garment", "contact_points": ["cloth_crown"], "max_gap_px": 4,
     "layer_order": lo(["cap", "hijab"]), "why": "the cloth wraps skull and cap with volume; never painted on the skull"},
    {"id": "pin-in-cloth", "child": "pin", "parent": "hijab", "parent_anchor": "cross_point", "kind": "garment", "contact_points": ["pin_mid"], "max_gap_px": 4,
     "layer_order": lo(["hijab", "pin"]), "why": "one brass pin where the ends cross at her left jaw"},
    {"id": "drape-neck", "child": "hijab", "parent": "neck", "parent_anchor": "neck_front", "kind": "garment", "contact_points": ["drape_neck"], "max_gap_px": 4,
     "layer_order": lo(["coat", "neck", "hijab"]), "why": "the drape covers the neck: head and body join through the garment, no line at the neck (F11)"},
    {"id": "drape-shelf-L", "child": "hijab", "parent": "clavicle-L", "parent_anchor": "shelf_L", "kind": "garment", "contact_points": ["drape_shelf_L"], "max_gap_px": 4,
     "layer_order": lo(["coat", "hijab"]), "why": "the drape rests on the shoulder shelf before it falls"},
    {"id": "drape-shelf-R", "child": "hijab", "parent": "clavicle-R", "parent_anchor": "shelf_R", "kind": "garment", "contact_points": ["drape_shelf_R"], "max_gap_px": 4,
     "layer_order": lo(["coat", "hijab"])},
    {"id": "end-over-shoulder", "child": "scarf-end-L", "parent": "coat", "parent_anchor": "coat_shoulder_L", "kind": "garment", "contact_points": ["end_fold_L"], "max_gap_px": 4,
     "layer_order": lo(["coat", "hijab", "scarf-end-L"]), "why": "the left end is thrown back over the writing-hand shoulder"},
]
CHAR = {
    "id": "hero", "parts": PARTS, "physics_profile": "hero-v1", "model_ref": {"id": "hero/model", "version": "2.0"}, "face_ref": {"id": "hero/face", "version": "2.0"}, "build": {"silhouette": "merged: outline once per group (body: coat, neck, hijab, scarf end; arms: arms and hands)", "interior_lines": "only at real overlaps, folds and creases", "tone_steps": 3},
    "catalogue": "catalogue/characters/hero/index.json",
    "rest_proportions": {"head_h": 100, "shoulder_w": 186, "neck_len": 32, "upper_arm": 138, "forearm": 110, "hand": 80, "thigh": 170, "shank": 163},
    "anchors": {"clavicle_L": [88, -253], "clavicle_R": [-88, -253], "neck_base": [0, -263], "head_unit_px": 100, "space": "body space, 1 HU = 100 px, origin pelvis centre"},
    "covers_hair": True, "attachments": ATT,
    "handedness": "writes with the LEFT hand; gives and takes with the RIGHT (catalogue hands v3 authored per side, no mirrors)", "hands_ref": "catalogue/characters/hero/v3/hands", "emotion_profile": {"baseline": {"blink_per_min": 14, "gaze_habit": "reads the label before the face"},
                        "display_rules": {"family": "open", "peer": "direct", "authority": "polite and exact", "stranger": "brisk, friendly, slightly pushy"},
                        "hidden_feeling_channel": "hands", "leak": {"fear": "the pen stops mid-letter and the coat tags go still", "dread": "the pen tip presses until it stops"},
                        "never_uses": ["pointing with the index finger", "giving or taking with the left hand", "voice raise"]},
    "face_controls": ["AU1", "AU2", "AU4", "AU5", "AU6", "AU7", "AU9", "AU12", "AU15", "AU20", "AU23", "AU26"],
}
PROFILES = {
    "hero-v1": {"extends": "_human-default", "kind": "character", "mass_class": "medium", "bone_lengths_tolerance_pct": 2, "source": "catalogue/characters/hero/physics.json"},
    "rigid": {"kind": "object", "material": "rigid", "mass_class": "light", "stretch": {"max_scale": 1.0}},
    "soft-leather": {"kind": "object", "material": "soft body", "mass_class": "medium", "squash_pct": [10, 25], "note": "squash along the contact normal, keeps area"},
    "paper": {"kind": "object", "material": "stiff plane", "mass_class": "feather", "note": "rotates about its string knot, never stretches"},
    "cord": {"kind": "object", "material": "constant-length rope", "mass_class": "feather"},
    "hinged": {"kind": "object", "material": "one-axis hinge", "mass_class": "light", "limits_deg": {"open": [0, 110]}},
}
PROPS = [{"id": "pen", "physics_profile": "rigid", "mass_class": "light", "length_m": 0.128, "catalogue": "hero/hand/tripod-pen-L@3.0 (pen geometry)"}, {"id": "jar", "physics_profile": "rigid", "mass_class": "medium"},
         {"id": "card", "physics_profile": "paper", "mass_class": "feather", "catalogue": "hero/prop/card@3.0", "faces": {"front": "ruled line + her ink خرز أصفر", "back": "blank"},
          "staging": "front up on the counter; the nib and every camera see the front (R-387, R-388)"},
         {"id": "bag", "physics_profile": "soft-leather", "mass_class": "medium"}, {"id": "bag-tag", "physics_profile": "paper", "mass_class": "feather", "catalogue": "hero/prop/bag-tag@3.0", "faces": {"front": "هُدى + الخميس القادم (faces her)", "back": "intake stamp (faces the front-view camera)"}},
{"id": "tag-string", "physics_profile": "cord", "mass_class": "feather", "length_m": 0.16},
         {"id": "bell", "physics_profile": "rigid", "mass_class": "light"}, {"id": "ledger-page", "physics_profile": "paper", "mass_class": "feather"},
         {"id": "lamp", "physics_profile": "rigid", "mass_class": "medium", "note": "pendulum on a chain"}, {"id": "chute-flap", "physics_profile": "hinged", "mass_class": "light"},
         {"id": "drawers", "physics_profile": "hinged", "mass_class": "medium"}]

def planes(beat):
    sh = next(x for x in plan["shots"] if x["beat"] == beat)
    cz = sh["cam0"]["z"]; subj = 2.56
    cand = [("back-wall", 8.0), ("aisle", 5.6), ("back-unit", 3.6), ("drawers-shelves", 3.3), ("hero", 2.56), ("counter-props", 2.4), ("counter-front", 2.2), ("hanging-tags-fg", 1.7), ("post-fg", 1.62)]
    out = []
    for pid, z in cand:
        if z - cz < 0.25: continue
        par = round((subj - cz) / (z - cz), 2)
        if not out or abs(par - out[-1]["parallax"]) >= 0.12:
            out.append({"id": pid, "parallax": par, "z_m": z})
    return out

def light(kd, kc, size, fd, fc, rd, rc, serves, src):
    return {"key": {"dir": kd, "color": kc, "source": src, "size": size}, "fill": {"dir": fd, "color": fc}, "rim": {"dir": rd, "color": rc}, "serves_emotion": serves}

def shadow(contacts, receiver="back-unit"):
    return [{"caster": "hero", "receiver": receiver, "source": "mass_proxy", "proxy": "hero-proxy", "light": "key", "self_shadow": True, "contacts": contacts,
             "edge": "hard", "drawn": "one flat 2D shape: the union of the mass proxy projected from the lamp, no blur (R-380)"},
            {"caster": "counter-props", "receiver": "counter-top", "source": "mass_proxy", "proxy": "props-proxy", "light": "key", "edge": "hard"}]


plan = None

def build(plan_in, shot, lib):
    global plan
    plan = plan_in
    ID = shot["id"]
    shots = {s["shot"]: s for s in plan["shots"]}
    B = []
    B.append({"id": "b1", "start": 0.0, "end": 3.0, "treatment": "A", "treatment_reason": "routine and calm: clear line, depth and smooth ones carry the quiet office",
              "rates": {"hero": "ones", "props": "ones", "camera": "ones"}, "depth_planes": planes("b1"),
              "light": light("high-right-front", "#ffb36b", 0.12, "left", "#3c4e86", "back-left", "#ffd08a", "calm", "oil lamp on a chain, swaying in the draught"),
              "cast_shadows": shadow([{"a": "pen-tip", "b": "card"}, {"a": "jar", "b": "counter-top"}, {"a": "fingertips-R", "b": "card"}]),
              "interactions": [{"cause": "Hero's nib on the card's front", "effect": "خرز أصفر appears under the nib, right to left, letter bodies then dots; the pen's flat shadow meets the nib", "kind": "contact", "carries_emotion": True},
                               {"cause": "draught from the chute", "effect": "coat tags and hanging tags sway, lamp swings", "kind": "wind"},
                               {"cause": "chute flap rattle (2.45 s)", "effect": "flap judders, dust sifts down, her eyes dart up", "kind": "displace"}],
              "actions": [{"part": "forearm-L", "anticipation_frames": 4, "overshoot": False, "what": "nib down onto the card"}, {"part": "eyes", "anticipation_frames": 3, "what": "dart to the rattle"}],
              "elements": [{"id": "back-wall", "static_s": 0.0}, {"id": "drawers", "static_s": 1.2}], "holds": [], "camera_move_pct": 6,
              "poses": [{"character": "hero", "pose_id": "write-card", "catalogue": CAT3.format("write-card"), "angle": "three-quarter-R",
                         "contacts": [{"part": "palm-L", "target": "pen", "t0": 0.0, "t1": 3.0, "kind": "grip"},
                                      {"part": "pen", "target": "card", "t0": 0.75, "t1": 2.375, "kind": "tool-tip"},
                                      {"part": "palm-R", "target": "card", "t0": 0.0, "t1": 3.0, "kind": "grip"}]}],
              "writing": {"prop": "card", "face": "front", "text": "خرز أصفر", "direction": "rtl", "hand": "L", "strokes": "catalogue hero/writing/khurz-asfar@3.0",
                          "staging": "s2 is her POV from above: the face the nib touches is the face the viewer sees (R-388)", "t0": 0.75, "t1": 2.375},
              "texts": [],
              "emotion": {"primary": "calm", "intensity": 0.3, "shown": "visible", "peak_s": 2.05, "cause": "routine tagging, a job she likes", "character": "hero"},
              "emotion_track": {"eyes": {"gaze_target": "pen tip", "darts_per_s": 0.4, "blink_per_min": [10, 17], "onset_s": 0.0, "lids": "relaxed", "iris": "mid"},
                                "face": {"aus": {"6": 0.1, "12": 0.18, "23": 0.15}, "asymmetry": 0.04, "onset_s": 0.08},
                                "body": {"effort": {"weight": "light", "time": "sustained", "space": "direct", "flow": "free"}, "posture": "bent at the hips over the work, shoulders low", "onset_s": 0.17},
                                "voice": {"line": None, "breath": "even", "pace": "base", "pitch_st": 0, "energy": "soft", "style_text": "quiet hum under the breath, Omani lilt"},
                                "action": {"from_emotion": "writes the label in neat strokes, right to left", "obstacle": "none", "outcome": "completed"},
                                "environment": {"response": "lamp sways gently, dust drifts in the light", "interaction_ref": "draught from the chute"},
                                "colour": {"hue_family": "warm amber", "sat": "mid", "value": "mid", "key_temp": "warm", "fill_temp": "cool"},
                                "sfx": [{"at_s": 0.0, "what": "harbour room tone, distant water"}, {"at_s": 0.5, "what": "pen scratch"}, {"at_s": 2.45, "what": "chute flap rattle (leads the drop)"}]}})
    B.append({"id": "b2", "start": 3.0, "end": 4.625, "treatment": "B", "treatment_reason": "the slam: halftone, offset ink and Hero on twos while dust and shake stay on ones",
              "rates": {"hero": "twos", "dust": "ones", "camera-shake": "ones", "props": "ones"}, "depth_planes": planes("b2"),
              "light": light("high-right (lamp jolts)", "#fff1d6", 0.06, "left", "#7a2f78", "right", "#ff7a4a", "surprise", "impact flash, then the lamp swings hard"),
              "cast_shadows": shadow([{"a": "bag", "b": "counter-top"}, {"a": "jar", "b": "counter-top"}]),
              "interactions": [{"cause": "bag landing", "effect": "jar hops, ledger pages flip, bell rings, drawers pop open", "kind": "displace"},
                               {"cause": "bag hits the counter", "effect": "dust bursts off the counter top", "kind": "splash-dust"},
                               {"cause": "lamp swing after the slam", "effect": "every shadow in the room whips sideways", "kind": "light-spill", "carries_emotion": True},
                               {"cause": "bag base", "effect": "bag squashes 18 % on the counter and rebounds", "kind": "contact"}],
              "actions": [{"part": "torso", "anticipation_frames": 3, "overshoot": True, "what": "recoil"}, {"part": "palm-R", "anticipation_frames": 3, "what": "both hands jerk up off the counter and freeze open (grip change hidden under the impact cover)"}, {"part": "bag", "anticipation_frames": 6, "what": "flap rattle before the drop"}],
              "elements": [{"id": "back-wall", "static_s": 0.0}], "holds": [{"element": "hero", "start": 3.0, "end": 3.125, "why": "impact frames: the cover hides the style flip"}],
              "camera_move_pct": 5,
              "poses": [{"character": "hero", "pose_id": "startle-back", "catalogue": CAT.format("startle-back"), "angle": "three-quarter-L",
                         "contacts": [{"part": "palm-L", "target": "pen", "t0": 3.0, "t1": 4.625, "kind": "grip"}]}],
              "texts": [],
              "emotion": {"primary": "surprise", "intensity": 0.85, "shown": "visible", "peak_s": 3.08, "cause": "reflex startle: the bag slams the counter", "character": "hero"},
              "emotion_track": {"eyes": {"gaze_target": "bag", "darts_per_s": 1.2, "blink_per_min": [0, 20], "onset_s": 3.04, "lids": "wide", "iris": "small"},
                                "face": {"aus": {"1": 0.8, "2": 0.8, "5": 0.9, "26": 0.7, "20": 0.2}, "onset_s": 3.04},
                                "body": {"effort": {"weight": "light", "time": "sudden", "space": "direct", "flow": "free"}, "posture": "weight back, shoulders up, hands jerked up off the counter", "onset_s": 3.0},
                                "voice": {"line": None, "breath": "sharp inhale", "pace": "fast", "pitch_st": 4, "energy": "high", "style_text": "a short gasp, no word"},
                                "action": {"from_emotion": "recoils, hands jerk up off the counter, the pen still in her left hand", "obstacle": "the counter", "outcome": "completed"},
                                "environment": {"response": "lamp swings hard, drawers pop, dust bursts", "interaction_ref": "bag landing"},
                                "colour": {"hue_family": "hot white flash over ink", "sat": "rising", "value": "high then falling", "key_temp": "white", "fill_temp": "magenta"},
                                "sfx": [{"at_s": 3.0, "what": "leather slam on wood"}, {"at_s": 3.02, "what": "bell ring-out"}, {"at_s": 3.05, "what": "drawers knock"}],
                                "vfx": [{"at_s": 3.0, "what": "one ink impact frame (halftone burst)", "box": {"x": 80, "y": 900, "w": 560, "h": 560}}]},
              "emotion_change": {"from": "calm", "to": "surprise", "bridge": "the slam itself (reflex, body first)", "frames": 6}})
    B.append({"id": "b3", "start": 4.625, "end": 6.875, "treatment": "A+B", "treatment_reason": "the name: the room clears to line and depth; only the bag keeps halftone and threes: it is from another day",
              "rates": {"hero": "ones", "bag": "threes", "bag-tag": "ones", "camera": "ones"}, "depth_planes": planes("b3"),
              "light": light("high-right (lamp dims)", "#d99a5a", 0.12, "low-left (tag glow)", "#5fd6ff", "left", "#9fe8ff", "dread", "the lamp dims while the tag glows cold"),
              "cast_shadows": shadow([{"a": "palm-R", "b": "counter-top"}, {"a": "bag", "b": "counter-top"}]),
              "interactions": [{"cause": "tag glow", "effect": "cold light climbs her coat and face; her shadow leans away from it", "kind": "light-spill", "carries_emotion": True},
                               {"cause": "Hero's right palm", "effect": "presses on the counter, the ledger edge lifts", "kind": "contact"},
                               {"cause": "her lean", "effect": "her head occludes the lamp from the jar", "kind": "occlude"}],
              "actions": [{"part": "torso", "anticipation_frames": 5, "what": "lean in with shoulders held back"}, {"part": "forearm-L", "anticipation_frames": 4, "what": "pen hand stops short"}],
              "elements": [{"id": "bag", "static_s": 1.1}, {"id": "back-wall", "static_s": 0.0}], "holds": [], "camera_move_pct": 5,
              "poses": [{"character": "hero", "pose_id": "lean-dread", "catalogue": CAT.format("lean-dread"), "angle": "three-quarter-L",
                         "contacts": [{"part": "palm-L", "target": "pen", "t0": 4.625, "t1": 6.875, "kind": "grip"},
                                      {"part": "palm-R", "target": "counter", "t0": 5.0, "t1": 6.875, "kind": "touch"}]}],
              "texts": [{"id": "tag-name", "string": "هدى", "lang": "ar", "role": "main", "box": {"x": 417, "y": 916, "w": 238, "h": 140}, "layer": "top", "plate": "opaque-flat",
                         "min_contrast": 7.0, "height_px": 100, "read_time_s": 0.9, "t0": 5.875, "t1": 6.792, "appear": "plate settles, glyphs cut on", "leave": "cut before the wipe",
                         "font": "thmanyahseriftext 700", "in_world": "the FRONT of the bag tag, seen in her POV (the front faces her); plate is flat and opaque, drawn after every effect"},
                        {"id": "tag-date", "string": "الخميس القادم", "lang": "ar", "role": "sub", "box": {"x": 358, "y": 1080, "w": 357, "h": 61}, "layer": "top", "plate": "opaque-flat",
                         "min_contrast": 7.0, "height_px": 48, "read_time_s": 0.9, "t0": 5.875, "t1": 6.792, "appear": "with the name", "leave": "cut before the wipe",
                         "font": "thmanyahsans 700"}],
              "emotion": {"primary": "dread", "secondary": "longing", "blend": {"dread": 0.7, "longing": 0.3}, "intensity": 0.7, "shown": "visible", "peak_s": 5.55,
                          "cause": "the front of the tag on the bag, turned toward her, carries her own name", "character": "hero"},
              "emotion_track": {"eyes": {"gaze_target": "bag-tag", "darts_per_s": 0.8, "blink_per_min": [3, 8], "onset_s": 4.65, "lids": "lower lid raised", "iris": "small then wide",
                                         "blink_events": [{"at_s": 5.2, "kind": "slow"}]},
                                "face": {"aus": {"1": 0.55, "4": 0.25, "5": 0.4, "26": 0.2, "15": 0.15}, "asymmetry": 0.05, "onset_s": 4.75},
                                "body": {"effort": {"weight": "light", "time": "sustained", "space": "direct", "flow": "bound"}, "posture": "head leans in, shoulders pull back", "onset_s": 4.85},
                                "voice": {"line": None, "breath": "held", "pace": "slow", "pitch_st": 0, "energy": "soft", "style_text": "breath held; a whisper of her own name, not voiced yet", "silence_s": [5.4, 6.4]},
                                "action": {"from_emotion": "reaches toward the tag, stops short, braces on the counter", "obstacle": "fear of her own name", "outcome": "aborted"},
                                "environment": {"response": "lamp gutters, the tag glows cold, coat tags go still", "interaction_ref": "tag glow"},
                                "colour": {"hue_family": "cold teal accent in a warm room", "sat": "falling", "value": "falling", "key_temp": "neutral", "fill_temp": "cold"},
                                "sfx": [{"at_s": 4.625, "what": "room tone drops out"}, {"at_s": 4.7, "what": "one low glass note"}, {"at_s": 5.875, "what": "paper tick as the name is read"}],
                                "vfx": [{"at_s": 4.7, "what": "the tag's cold glow: three flat stepped rings", "box": {"x": 100, "y": 1250, "w": 300, "h": 300}}]},
              "emotion_change": {"from": "surprise", "to": "dread", "bridge": "one slow blink and the room tone dropping out", "frames": 12}})
    B.append({"id": "b4", "start": 6.875, "end": 9.0, "treatment": "A", "treatment_reason": "she takes control: back to clear line and ones; the cold grade stays as the suspicion",
              "rates": {"hero": "ones", "bag-tag": "ones", "bag": "ones", "camera": "ones"}, "depth_planes": planes("b4"),
              "light": light("high-right (lamp, cooler)", "#c9b48f", 0.12, "left", "#2e6f7a", "back-right", "#bfefff", "suspicion", "lamp settles cooler; half her face in the tag's cold light"),
              "cast_shadows": shadow([{"a": "tag-string", "b": "bag-handle"}, {"a": "fingertips-R", "b": "bag-tag"}]),
              "interactions": [{"cause": "Hero's right hand", "effect": "pinches the tag's lower corner and tips it toward her (front to her, stamped back to us); the string pulls taut", "kind": "grab", "carries_emotion": True},
                               {"cause": "the lifted tag", "effect": "its shadow crosses her coat", "kind": "cast-shadow"},
                               {"cause": "draught", "effect": "the hanging tags turn toward the chute", "kind": "wind"}],
              "actions": [{"part": "forearm-R", "anticipation_frames": 4, "overshoot": True, "what": "reach and pinch"}, {"part": "eyes", "anticipation_frames": 3, "what": "side look to the chute"}],
              "elements": [{"id": "back-wall", "static_s": 0.0}], "holds": [], "camera_move_pct": 7,
              "poses": [{"character": "hero", "pose_id": "lift-tag-read", "catalogue": CAT3.format("lift-tag-read"), "angle": "front",
                         "contacts": [{"part": "palm-L", "target": "pen", "t0": 6.875, "t1": 9.0, "kind": "grip"},
                                      {"part": "palm-R", "target": "bag-tag", "t0": 7.375, "t1": 9.0, "kind": "grip"}, {"part": "thumb-R", "target": "bag-tag", "t0": 7.375, "t1": 9.0, "kind": "grip"},
                                      {"part": "finger-index-R", "target": "bag-tag", "t0": 7.375, "t1": 9.0, "kind": "grip"}]}],
              "texts": [],
              "emotion": {"primary": "suspicion", "intensity": 0.6, "shown": "visible", "peak_s": 7.95, "cause": "the date on the tag is a day that has not come", "character": "hero"},
              "emotion_track": {"eyes": {"gaze_target": "bag-tag then chute", "darts_per_s": 0.9, "blink_per_min": [6, 10], "onset_s": 6.9, "lids": "narrowed", "iris": "mid"},
                                "face": {"aus": {"4": 0.45, "7": 0.55, "23": 0.4, "2": 0.15}, "asymmetry": 0.3, "onset_s": 7.0},
                                "body": {"effort": {"weight": "strong", "time": "sustained", "space": "direct", "flow": "bound"}, "posture": "squared, chin down, tag held up", "onset_s": 7.05},
                                "voice": {"line": None, "breath": "slow out", "pace": "slow", "pitch_st": -1, "energy": "quiet", "style_text": "low, even, Omani 'g' for qaf if she speaks"},
                                "action": {"from_emotion": "takes the tag with her right hand and reads its front, then looks to the chute", "obstacle": "the string holds the tag to the bag", "outcome": "completed"},
                                "environment": {"response": "hanging tags turn toward the chute, lamp settles", "interaction_ref": "draught"},
                                "colour": {"hue_family": "muted teal-orange split", "sat": "low", "value": "low", "key_temp": "neutral", "fill_temp": "teal"},
                                "sfx": [{"at_s": 7.375, "what": "paper snap as the string goes taut"}, {"at_s": 8.4, "what": "chute flap creak (off screen)"}]},
              "emotion_change": {"from": "dread", "to": "suspicion", "bridge": "a breath out and the eyes narrowing as the hand closes", "frames": 10}})

    TR = [
        {"from_beat": "b1", "to_beat": "b2", "type": "impact-cover", "frames": 4, "cause": "the bag hits the counter at 3.0 s (in frame in s2)", "style_entry": "under-cover", "style_entry_frames": 2,
         "frames_drawn": ["f72 ink impact frame (white burst on black ink)", "f73 hold on ones", "f74 hold on ones", "f75 drawn speed-line smear frame (no blur)"],
         "rate_change": [{"part": "hero", "from": "ones", "to": "twos", "ramp": "under-cover"}], "audio_lead_frames": 6, "cut": "s2 -> s3 hidden inside the cover; the right hand's grip change (press-card-R -> startle-open-R) lands on the declared smear frame f75"},
        {"from_beat": "b2", "to_beat": "b3", "type": "carrier-bleed", "frames": 10, "cause": "the tag on the bag lights up cold; its light spreads outward and clears the halftone",
         "carrier": "bag-tag glow", "edge_follows": "the glow front, grown from the tag along the counter and bag contours (ease-out radius, ink-noise edge)",
         "style_entry": "bleed-6-12", "style_entry_frames": 10,
         "rate_change": [{"part": "hero", "from": "twos", "to": "ones", "ramp": "hold-sequence-2-2-1-1-1"}, {"part": "bag", "from": "ones", "to": "threes", "ramp": "hold-sequence-2-2-1-1-1"}],
         "audio_lead_frames": 8, "cut": "s3 -> s4 on the glow's first frame"},
        {"from_beat": "b3", "to_beat": "b4", "type": "contour-wipe", "frames": 8, "cause": "her right sleeve sweeps in to take the tag", "edge_follows": "her right sleeve contour, 2 px offset ink on the edge",
         "style_entry": "bleed-6-12", "style_entry_frames": 8,
         "rate_change": [{"part": "bag", "from": "threes", "to": "ones", "ramp": "hold-sequence-2-2-1-1-1"}], "audio_lead_frames": 6, "cut": "s5 -> s6 revealed behind the sleeve edge"},
    ]
    CAMP = []
    for s in plan["shots"]:
        e = {k: s[k] for k in ("shot", "beat", "size", "angle", "lens_mm", "move", "start_frame_desc", "end_frame_desc", "dur_s", "why", "serves_emotion", "safe_boxes", "thumbnail")}
        e["catalogue_camera"] = lib.camera_ref("hero", s["catalogue_camera"])
        CAMP.append(e)
    spec = {"episode": f"{ID} (the series demo: the bag with her name; 2D build; hands, props and writing rebuilt, F13-F15)", "fps": 24, "canvas": "1080x1920", "duration_s": 9.0,
            "camera_plan_file": f"{shot['rel']}/camera-plan.json", "characters": [CHAR], "physics_profiles": PROFILES, "props": PROPS, "beats": B, "transitions": TR, "camera_plan": CAMP,
            "renderer": {"source": f"{shot['rel']}/build/index.html", "preview": f"the recorded video {shot['rel']}/out/{ID}.mp4 (previews play the video the gates measured)", "clock": "frame counter (renderFrame(f)), never wall-clock", "rig_trace": "Shot.traceFrame", "masks": f"{shot['rel']}/out/masks/{{line,shadow,text}}",
                         "hands": "catalogue hero v3 grips; 2D arms of constant drawn length; cut frames 18, 72, 111, 138, 165; smear frame 75"}}
    return spec
