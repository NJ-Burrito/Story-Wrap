# qg_checks.py part 1 of 4: executed into the qg_checks module namespace by qg_checks.py (a pure move).
import copy, json, math, re
from pathlib import Path

# ------------------------------------------------------------------ constants (thresholds)
EMOTIONS = ["calm", "joy", "sadness", "fear", "anger", "surprise", "disgust", "contempt", "shame", "longing",
            "suspicion", "dread", "relief", "bitter-joy"]
CHANNELS = ["eyes", "face", "body", "voice", "action", "environment", "colour", "sfx", "vfx"]
# blinks per minute allowed per emotion (emotion-channels.md 3.1). DEFAULT: judgement, lab rest 17/min.
BLINK_BANDS = {"calm": (10, 17), "joy": (12, 18), "sadness": (6, 10), "fear": (3, 30), "anger": (3, 6),
               "surprise": (0, 20), "suspicion": (6, 10), "relief": (6, 10), "bitter-joy": (6, 10)}
BLINK_DEFAULT_BAND = (0, 30)
TRANSITION_TYPES = ["match-cut", "action-cut", "impact-cover", "carrier-bleed", "whip-smear", "contour-wipe",
                    "fade-through-light"]
SAFE = (0, 250, 960, 1580)          # x0,y0,x1,y1 at 1080x1920 (Reels UI: top 250, bottom 340, right 120). DEFAULT.
SPEC2 = {
    "shoulder_width_heads": (1.8, 2.1), "neck_min_heads": 0.25, "upper_arm_to_forearm": (1.1, 1.4),
    "forearm_to_hand": (1.2, 1.5), "exceed_max_frames": 4, "max_gap_px": 6.0,
    "min_finger_parts": 3, "style_bleed": (6, 12), "min_cover_frames": 2, "audio_lead": (4, 12),
    "shot_dur_tol_s": 0.05, "min_why_chars": 12, "text_min_h": 36, "text_sub_min_h": 28, "text_min_contrast": 4.5,
    "min_channels": 6, "min_nonface_channels": 4, "emotion_change_frames": (6, 24), "max_vfx_per_beat": 1,
    "max_vfx_per_9s": 3, "sfx_intensity": 0.6, "min_face_controls": 12,
}
RIG = {
    "reach_ratio": (0.35, 0.99), "contact_tol_limb": 0.02, "seg_tol_pct": 2.0, "shoulder_x_frac": 0.85,
    "shoulder_y_heads": 0.03, "lift_heads_per_60": 0.1, "shoulder_y_lift_frac": 0.35, "shrug_max_heads": 0.2, "neck_min_heads": 0.25, "hinge_flip_deg": 10.0, "rides_min_elev": 30.0,
    "rides_corr": 0.7, "rides_min_lift_heads": 0.08, "com_margin_pct": 10.0, "blink_frames": (2, 5),
    "eye_lead": (2, 4), "eye_head_corr_max": 0.9, "face_controls_changed": 5, "face_control_delta": 0.15,
    "dart_min_speed": 0.01, "head_move_deg": 5.0, "peak_frames": 3,
}
RENDER2 = {"text_contrast_p10": 4.5, "text_contrast_large": 3.0, "text_texture_max": 6.0, "shadow_hole_px": 4,
           "colour_hue_deg": 30.0, "colour_rel": 0.20, "colour_target_hue": 30.0, "colour_target_sv": 0.20,
           "fallback_minority": 0.08,
           # PIECE-NO-CAPTION, drawn side (DEFAULT, no measured sample): text-mask pixels (540x960) outside every declared text box + pad, on >= N sampled frames
           "stray_text_pad_px": 12, "stray_text_px": 150, "stray_text_frames": 3}
# check id -> (rule ids, status). CALIBRATED only where a measured sample sets the number; everything else DEFAULT.
CHECK_STATUS = {}

def F(cid: str, msg: str) -> str:
    return f"FAIL [{cid}] {msg}"

def ids_of(fails: list[str]) -> set[str]:
    return {m.group(1) for f in fails for m in [re.match(r"FAIL \[([A-Z0-9-]+)\]", f)] if m}

# ------------------------------------------------------------------ physics profiles
_HUMAN_LIMITS = {
    "shoulder_flex": ([-45, 170], [-60, 180]), "shoulder_abd": ([-20, 170], [-30, 180]),
    "shoulder_rot": ([-60, 80], [-70, 90]), "elbow_flex": ([0, 145], [-5, 150]),
    "forearm_rot": ([-75, 75], [-80, 80]), "wrist_flex": ([-70, 60], [-80, 70]),
    "wrist_dev": ([-15, 25], [-20, 30]), "finger_mcp": ([0, 80], [0, 90]), "finger_pip": ([0, 90], [0, 100]),
    "finger_dip": ([0, 65], [0, 85]), "neck_flex": ([-45, 45], [-60, 60]), "neck_rot": ([-60, 60], [-75, 75]),
    "neck_tilt": ([-40, 40], [-45, 45]), "trunk_flex": ([-25, 70], [-30, 80]), "trunk_rot": ([-35, 35], [-45, 45]),
    "hip_flex": ([-20, 110], [-30, 120]), "hip_abd": ([-20, 40], [-30, 45]), "hip_rot": ([-40, 40], [-40, 45]),
    "knee_flex": ([0, 135], [0, 150]), "ankle_flex": ([-18, 45], [-20, 50]),
}
HUMAN_DEFAULT = {
    "id": "_human-default", "kind": "character", "mass_class": "medium",
    "limits_deg": {k: {"soft": v[0], "hard": v[1]} for k, v in _HUMAN_LIMITS.items()},
    "stretch": {"max_scale": 1.0, "segments": {}}, "bone_lengths_tolerance_pct": RIG["seg_tol_pct"],
    "balance": {"com_margin_pct": RIG["com_margin_pct"]},
}

def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else copy.deepcopy(v)
    return out

def resolve_profile(pid, spec: dict | None = None, root: Path | None = None, _depth: int = 0):
    """Built-in default, then spec['physics_profiles'][id] (inline), then <root>/bible/physics/<id>.json."""
    if not pid or _depth > 5:
        return None
    if pid == "_human-default":
        return copy.deepcopy(HUMAN_DEFAULT)
    raw = (spec or {}).get("physics_profiles", {}).get(pid)
    if raw is None and root is not None:
        p = Path(root) / "bible" / "physics" / f"{pid}.json"
        if p.exists():
            raw = json.loads(p.read_text(encoding="utf-8"))
    if raw is None:
        return None
    base = resolve_profile(raw.get("extends"), spec, root, _depth + 1) if raw.get("extends") else None
    if raw.get("extends") and base is None:
        return None
    prof = _merge(base or {}, {k: v for k, v in raw.items() if k not in ("extends", "overrides")})
    return _merge(prof, raw.get("overrides", {})) if raw.get("overrides") else prof

def _dur(b: dict) -> float:
    return float(b.get("end", 0)) - float(b.get("start", 0))

def _box_in(box: dict, safe=SAFE) -> bool:
    x, y, w, h = (float(box.get(k, 0)) for k in ("x", "y", "w", "h"))
    return x >= safe[0] and y >= safe[1] and x + w <= safe[2] and y + h <= safe[3]

def _boxes_overlap(a: dict, b: dict) -> bool:
    return not (a["x"] + a["w"] <= b["x"] or b["x"] + b["w"] <= a["x"] or a["y"] + a["h"] <= b["y"] or b["y"] + b["h"] <= a["y"])

# ------------------------------------------------------------------ SPEC checks (merged)
def check_bio(spec: dict, root=None) -> list[str]:
    f: list[str] = []
    chars = spec.get("characters", [])
    for ch in chars:
        cid = ch.get("id")
        prof = resolve_profile(ch.get("physics_profile"), spec, root)
        if prof is None:
            f.append(F("BIO-PROFILE", f"character {cid} physics_profile {ch.get('physics_profile')!r} missing or unknown (R-300)"))
        rp = ch.get("rest_proportions")
        if not rp:
            f.append(F("BIO-PROPORTIONS", f"character {cid} has no rest_proportions (R-307)"))
        else:
            need = ("head_h", "shoulder_w", "neck_len", "upper_arm", "forearm", "hand", "thigh", "shank")
            miss = [k for k in need if not rp.get(k)]
            if miss:
                f.append(F("BIO-PROPORTIONS", f"character {cid} rest_proportions missing {miss} (R-307)"))
            else:
                band = tuple(rp.get("shoulder_width_heads_band") or SPEC2["shoulder_width_heads"])
                if rp.get("shoulder_width_heads_band") and not rp.get("stylised_reason"):
                    f.append(F("BIO-PROPORTIONS", f"character {cid} widens the shoulder band without stylised_reason (R-307)"))
                sw = rp["shoulder_w"] / rp["head_h"]
                if not band[0] <= sw <= band[1]:
                    f.append(F("BIO-PROPORTIONS", f"character {cid} shoulder width = {sw:.2f} heads (need {band[0]}..{band[1]}): shoulders from the chest (R-307)"))
                nk = rp["neck_len"] / rp["head_h"]
                if nk < SPEC2["neck_min_heads"]:
                    f.append(F("BIO-PROPORTIONS", f"character {cid} neck = {nk:.2f} heads (need >= {SPEC2['neck_min_heads']}) (R-307, R-342)"))
                r1 = rp["upper_arm"] / rp["forearm"]; r2 = rp["forearm"] / rp["hand"]
                lo, hi = SPEC2["upper_arm_to_forearm"]
                if not lo <= r1 <= hi:
                    f.append(F("BIO-PROPORTIONS", f"character {cid} upper_arm/forearm = {r1:.2f} (need {lo}..{hi}) (R-307)"))
                lo, hi = SPEC2["forearm_to_hand"]
                if not lo <= r2 <= hi:
                    f.append(F("BIO-PROPORTIONS", f"character {cid} forearm/hand = {r2:.2f} (need {lo}..{hi}) (R-307)"))
    for p in spec.get("props", []):
        if not p.get("physics_profile") or not p.get("mass_class"):
            f.append(F("BIO-PROFILE", f"prop {p.get('id')} needs physics_profile and mass_class (R-300, R-315)"))
    # poses, contacts, exceed, stretch
    ch_by_id = {c.get("id"): c for c in chars}
    for b in spec.get("beats", []):
        bid = b.get("id", "?")
        poses = b.get("poses") or []
        if not poses:
            f.append(F("POSE-CATALOGUE", f"beat {bid} has no poses[] (R-306, R-318)"))
        for ps in poses:
            if not ps.get("character") or not ps.get("pose_id"):
                f.append(F("POSE-CATALOGUE", f"beat {bid} pose needs character and pose_id (R-318)"))
            elif ps.get("new"):
                if not ps.get("build_up_sheet"):
                    f.append(F("POSE-CATALOGUE", f"beat {bid} pose {ps['pose_id']} is new but has no build_up_sheet (R-306)"))
            elif not re.fullmatch(r".+@[0-9][0-9.]*", str(ps.get("catalogue", ""))):
                f.append(F("POSE-CATALOGUE", f"beat {bid} pose {ps['pose_id']} has no catalogue 'id@version' and is not new (R-346)"))
            prof = resolve_profile((ch_by_id.get(ps.get("character")) or {}).get("physics_profile"), spec, root) or HUMAN_DEFAULT
            for ex in ps.get("exceed", []):
                fr = (float(ex.get("t1", 0)) - float(ex.get("t0", 0))) * float(spec.get("fps", 24))
                if fr > SPEC2["exceed_max_frames"] + 1e-6 or ex.get("reason") not in ("impact", "comedy"):
                    f.append(F("BIO-EXEMPT", f"beat {bid} exceed window {ex.get('joint')} = {fr:.1f} frames / reason {ex.get('reason')} (max {SPEC2['exceed_max_frames']}, impact or comedy) (R-301)"))
            for se in ps.get("stretch_events", []):
                seg_max = (prof.get("stretch", {}).get("segments") or {}).get(se.get("segment"), prof.get("stretch", {}).get("max_scale", 1.0))
                if prof.get("stretch", {}).get("max_scale", 1.0) <= 1.0 or float(se.get("max_scale", 0)) > float(seg_max):
                    f.append(F("BIO-EXEMPT", f"beat {bid} stretch_event {se.get('segment')} max_scale {se.get('max_scale')} exceeds the profile ({seg_max}) (R-303, R-319)"))
            for c in ps.get("contacts", []):
                if not all(k in c for k in ("part", "target", "t0", "t1")):
                    f.append(F("BIO-CONTACTS", f"beat {bid} contact needs part, target, t0, t1 (R-304)"))
    # hand_grip parts need a contact somewhere
    contact_parts = {c.get("part") for b in spec.get("beats", []) for ps in b.get("poses", []) for c in ps.get("contacts", [])}
    for ch in chars:
        for p in ch.get("parts", []):
            if p.get("hand_grip") and p.get("name") not in contact_parts:
                f.append(F("BIO-CONTACTS", f"part {p.get('name')} grips {p['hand_grip']} but no pose declares a contact for it (R-310, R-311)"))
    return f

def check_attach(spec: dict) -> list[str]:
    f: list[str] = []
    for ch in spec.get("characters", []):
        cid = ch.get("id"); parts = ch.get("parts", [])
        names = {p.get("name") for p in parts}
        if not (ch.get("model_ref") or {}).get("id") or not (ch.get("model_ref") or {}).get("version"):
            f.append(F("ATT-MODEL", f"character {cid} model_ref {{id, version}} missing (R-345, R-346)"))
        an = ch.get("anchors") or {}
        miss = [k for k in ("clavicle_L", "clavicle_R", "neck_base", "head_unit_px") if k not in an]
        if miss:
            f.append(F("ATT-ANCHORS", f"character {cid} anchors missing {miss} (R-341)"))
        atts = ch.get("attachments") or []
        if not atts:
            f.append(F("ATT-DECLARED", f"character {cid} has no attachments (held objects and garments need parent, anchor, contact points) (R-350)"))
        for a in atts:
            miss = [k for k in ("id", "child", "parent", "parent_anchor", "contact_points", "layer_order") if not a.get(k)]
            if miss:
                f.append(F("ATT-DECLARED", f"character {cid} attachment {a.get('id')} missing {miss} (R-350, R-352)"))
                continue
            if float(a.get("max_gap_px", 4)) > SPEC2["max_gap_px"]:
                f.append(F("ATT-DECLARED", f"attachment {a['id']} max_gap_px {a.get('max_gap_px')} > {SPEC2['max_gap_px']} (R-351)"))
            for ang, order in a["layer_order"].items():
                if not isinstance(order, list) or len(order) < 2:
                    f.append(F("ATT-LAYERS", f"attachment {a['id']} layer_order[{ang}] needs >= 2 parts back to front (R-352)"))
        fingers = [p for p in parts if re.search(r"finger|thumb|index|palm", p.get("name", ""))]
        grips = [a for a in atts if a.get("kind") == "held"]
        grips += [1 for p in parts if p.get("hand_grip")]
        if grips and len(fingers) < SPEC2["min_finger_parts"]:
            f.append(F("ATT-FINGERS", f"character {cid} holds an object with {len(fingers)} finger/palm parts (need >= {SPEC2['min_finger_parts']}) (R-353)"))
        if ch.get("covers_hair"):
            bad = [p["name"] for p in parts if p.get("name", "").startswith("hair") and not p.get("under_garment")]
            if bad:
                f.append(F("ATT-HAIR", f"character {cid} covers_hair but {bad} are not under_garment (R-354)"))
    return f

def check_shadows(spec: dict) -> list[str]:
    f: list[str] = []
    for b in spec.get("beats", []):
        bid = b.get("id", "?"); sh = b.get("cast_shadows", [])
        for s in sh:
            if s.get("source") != "mass_proxy" or not s.get("proxy") or not s.get("light"):
                f.append(F("SHADOW-MASS", f"beat {bid} shadow of {s.get('caster')} needs source 'mass_proxy', a proxy id and a light (R-317, R-355)"))
        need = sum(1 for i in b.get("interactions", []) if i.get("kind") in ("contact", "grab"))
        have = sum(len(s.get("contacts") or []) for s in sh)
        if have < need:
            f.append(F("SHADOW-CONTACT", f"beat {bid} contact shadows = {have} for {need} contact/grab interactions (R-357)"))
        if spec.get("characters") and not any(s.get("self_shadow") for s in sh):
            f.append(F("SHADOW-SELF", f"beat {bid} has no self-shadow on a character (R-359)"))
        k = (b.get("light") or {}).get("key") or {}
        if not isinstance(k.get("size"), (int, float)):
            f.append(F("SHADOW-SOFT", f"beat {bid} light.key.size missing (penumbra follows light size) (R-358)"))
    return f

def check_transitions(spec: dict) -> list[str]:
    f: list[str] = []; beats = spec.get("beats", []); tr = spec.get("transitions")
    if tr is None:
        return [F("TRANS-COUNT", f"transitions[] missing: {max(len(beats) - 1, 0)} beat boundaries are undeclared (R-320)")]
    if len(tr) != max(len(beats) - 1, 0):
        f.append(F("TRANS-COUNT", f"transitions = {len(tr)} for {len(beats)} beats (need {len(beats) - 1}) (R-320)"))
    for i, t in enumerate(tr):
        tid = f"{t.get('from_beat')}->{t.get('to_beat')}"
        if i + 1 < len(beats) and (t.get("from_beat"), t.get("to_beat")) != (beats[i].get("id"), beats[i + 1].get("id")):
            f.append(F("TRANS-COUNT", f"transition {i} is {tid} but the boundary is {beats[i].get('id')}->{beats[i + 1].get('id')} (R-320)"))
        miss = [k for k in ("type", "frames", "cause", "style_entry", "rate_change") if t.get(k) in (None, "")]
        if miss:
            f.append(F("TRANS-FIELDS", f"transition {tid} missing {miss} (R-320)")); continue
        if t["type"] not in TRANSITION_TYPES:
            f.append(F("TRANS-FIELDS", f"transition {tid} unknown type {t['type']} (R-320)"))
        if i + 1 < len(beats):
            diff = beats[i].get("treatment") != beats[i + 1].get("treatment")
            if diff and t["style_entry"] == "none-same-style":
                f.append(F("TRANS-STYLE", f"transition {tid} changes treatment but style_entry is none-same-style (R-321)"))
        if len(str(t["cause"])) < 8:
            f.append(F("TRANS-CAUSE", f"transition {tid} cause {t['cause']!r} is not an on-screen event (R-323)"))
        se = t["style_entry"]; sf = t.get("style_entry_frames", 0)
        if se == "bleed-6-12" and not SPEC2["style_bleed"][0] <= sf <= SPEC2["style_bleed"][1]:
            f.append(F("TRANS-STYLE", f"transition {tid} bleed frames = {sf} (need 6..12) (R-321)"))
        if se == "under-cover" and (t["type"] not in ("impact-cover", "whip-smear") or t["frames"] < SPEC2["min_cover_frames"]):
            f.append(F("TRANS-STYLE", f"transition {tid} under-cover needs impact-cover or whip-smear with >= 2 frames (R-321)"))
        if t["type"] in ("contour-wipe", "carrier-bleed") and not (t.get("carrier") or t.get("edge_follows")):
            f.append(F("TRANS-CARRIER", f"transition {tid} {t['type']} has no carrier or edge_follows: a straight edge reads as a split frame (R-324)"))
        for rc in t["rate_change"]:
            if rc.get("ramp") == "none" and t["type"] not in ("match-cut", "action-cut", "impact-cover"):
                f.append(F("TRANS-RATE", f"transition {tid} part {rc.get('part')} changes rate with no ramp on a {t['type']} (R-322)"))
            if rc.get("from") == rc.get("to"):
                f.append(F("TRANS-RATE", f"transition {tid} part {rc.get('part')} rate_change from == to (R-322)"))
        al = t.get("audio_lead_frames")
        if al is None:
            if not t.get("audio_lead_none_because"):
                f.append(F("TRANS-AUDIO", f"transition {tid} has neither audio_lead_frames nor audio_lead_none_because (R-327)"))
        elif not SPEC2["audio_lead"][0] <= al <= SPEC2["audio_lead"][1]:
            f.append(F("TRANS-AUDIO", f"transition {tid} audio_lead_frames = {al} (need 4..12) (R-327)"))
    return f

def check_camera(spec: dict, root=None, files=False) -> list[str]:
    f: list[str] = []; plan = spec.get("camera_plan")
    if not plan:
        return [F("CAM-PLAN", "camera_plan missing: the camera is designed before drawing (R-328)")]
    by_beat: dict = {}
    for s in plan:
        miss = [k for k in ("shot", "beat", "size", "angle", "lens_mm", "move", "start_frame_desc", "end_frame_desc", "dur_s", "why") if s.get(k) in (None, "")]
        if miss:
            f.append(F("CAM-PLAN", f"shot {s.get('shot')} missing {miss} (R-328)"))
        by_beat.setdefault(s.get("beat"), []).append(s)
        if s.get("move") not in (None, "locked") and len(str(s.get("why", ""))) < SPEC2["min_why_chars"]:
            f.append(F("CAM-WHY", f"shot {s.get('shot')} moves ({s.get('move')}) with why shorter than 12 chars (R-330)"))
        if len(str(s.get("why", ""))) < SPEC2["min_why_chars"]:
            f.append(F("CAM-WHY", f"shot {s.get('shot')} why shorter than 12 chars (R-330)"))
        for bx in s.get("safe_boxes", []):
            if not _box_in(bx):
                f.append(F("CAM-SAFE", f"shot {s.get('shot')} box {bx.get('id')} outside the safe band x 0..960, y 250..1580 (R-332)"))
        if files and s.get("thumbnail") and root is not None and not (Path(root) / s["thumbnail"]).exists():
            f.append(F("CAM-FILES", f"shot {s.get('shot')} thumbnail {s['thumbnail']} does not exist (R-329)"))
    for b in spec.get("beats", []):
        shots = by_beat.get(b.get("id"), [])
        if not shots:
            f.append(F("CAM-PLAN", f"beat {b.get('id')} has no shot in camera_plan (R-328)")); continue
        tot = sum(float(s.get("dur_s", 0)) for s in shots)
        if abs(tot - _dur(b)) > SPEC2["shot_dur_tol_s"]:
            f.append(F("CAM-DUR", f"beat {b.get('id')} shot durations sum {tot:.2f}s, beat is {_dur(b):.2f}s (R-328)"))
        for a, c in zip(shots, shots[1:]):
            if a.get("size") == c.get("size") and a.get("angle") == c.get("angle") and len(str(c.get("why", ""))) < SPEC2["min_why_chars"] + 20:
                f.append(F("CAM-VARY", f"beat {b.get('id')} shots {a.get('shot')} and {c.get('shot')} repeat size and angle without a long why (R-330)"))
        em = (b.get("emotion") or {})
        ok = {em.get("primary"), em.get("secondary")}
        for s in shots:
            if s.get("move") not in (None, "locked") and s.get("serves_emotion") not in ok:
                f.append(F("CAM-EMOTION", f"shot {s.get('shot')} moves but serves_emotion {s.get('serves_emotion')!r} is not the beat's emotion (R-377)"))
    return f

def is_dialogue_caption(t: dict) -> bool:
    """A piece text that captions speech: role 'caption', a caption-bar plate, or a speaker, unless it is declared diegetic (a tag, card or sign in the world).
    Dialogue captions belong to compose.py alone (E01 run 1: the piece's baked captions fought the compose plates)."""
    if t.get("role") == "caption":
        return True
    return not t.get("diegetic") and (t.get("plate") == "caption-bar" or bool(t.get("speaker")))

def piece_caption_issues(spec: dict) -> list[str]:
    """PIECE-NO-CAPTION (spec side): no beat text of a piece captions dialogue. compose.py is the single caption owner (EP-CAPTIONS)."""
    f: list[str] = []
    for b in spec.get("beats", []):
        for t in b.get("texts") or []:
            if is_dialogue_caption(t):
                f.append(F("PIECE-NO-CAPTION", f"beat {b.get('id', '?')} text {t.get('id')} captions dialogue (role {t.get('role')!r}, plate {t.get('plate')!r}, speaker {t.get('speaker')!r}): "
                           "pieces never draw dialogue captions, compose.py does; keep only diegetic text (tag, card, sign) and mark it diegetic: true"))
    return f

def check_texts(spec: dict) -> list[str]:
    f: list[str] = piece_caption_issues(spec); beats = spec.get("beats", []); tr = spec.get("transitions") or []
    for i, b in enumerate(beats):
        bid = b.get("id", "?")
        if "texts" not in b:
            f.append(F("TEXT-SPEC", f"beat {bid} has no texts[] (an empty list is allowed) (R-334)")); continue
        for t in b["texts"]:
            tid = t.get("id")
            try:
                from arabic_display import has_tashkeel as _tk
            except ImportError:       # qg_checks imported without tools/ on sys.path
                import sys as _s; _s.path.insert(0, str(Path(__file__).resolve().parent)); from arabic_display import has_tashkeel as _tk
            if _tk(str(t["string"])):
                f.append(F("TEXT-NO-TASHKEEL", f"text {tid} carries tashkeel or tatweel; on-screen text is written without it (CLAUDE.md)"))
            miss = [k for k in ("id", "string", "lang", "box", "layer", "plate", "min_contrast", "height_px", "read_time_s", "t0", "t1") if t.get(k) in (None, "")]
            if miss:
                f.append(F("TEXT-SPEC", f"beat {bid} text {tid} missing {miss} (R-334)")); continue
            if t["layer"] != "top":
                f.append(F("TEXT-LAYER", f"text {tid} layer {t['layer']!r} (must be 'top', above every effect) (R-334)"))
            if t["plate"] not in ("opaque-flat", "caption-bar"):
                f.append(F("TEXT-LAYER", f"text {tid} plate {t['plate']!r} (R-334, R-335)"))
            if not t.get("decor"):
                mh = SPEC2["text_sub_min_h"] if t.get("role") == "sub" else SPEC2["text_min_h"]
                if t["height_px"] < mh:
                    f.append(F("TEXT-SIZE", f"text {tid} height {t['height_px']} px (need >= {mh}) (R-337)"))
                if t["min_contrast"] < SPEC2["text_min_contrast"]:
                    f.append(F("TEXT-CONTRAST", f"text {tid} min_contrast {t['min_contrast']} (need >= 4.5) (R-336)"))
                need = 0.6 + 0.1 * len(str(t["string"]).split())
                if t["read_time_s"] < need - 1e-9 or (t["t1"] - t["t0"]) < t["read_time_s"] - 1e-9:
                    f.append(F("TEXT-DWELL", f"text {tid} read_time {t['read_time_s']} s on screen {t['t1'] - t['t0']:.2f} s (need >= {need:.1f}) (R-338)"))
            if not _box_in(t["box"]):
                f.append(F("TEXT-SAFE", f"text {tid} box outside the safe band (R-332)"))
            fps = float(spec.get("fps", 24))
            for k, x in enumerate(tr):
                if x.get("style_entry") == "none-same-style" or k + 1 >= len(beats):
                    continue
                w0 = float(beats[k].get("end", 0)); w1 = w0 + float(x.get("frames", 0)) / fps + float(x.get("style_entry_frames", 0)) / fps
                if t["t0"] < w1 and t["t1"] > w0:
                    f.append(F("TEXT-TRANSITION", f"text {tid} is on screen during the style entry of {x.get('from_beat')}->{x.get('to_beat')} (R-339)"))
    return f

def _actor_view(spec: dict, aid: str) -> dict:
    """The spec as one actor sees it: its own rig entry, and each beat's emotion / emotion_track / emotion_change taken from beat.actor_emotions[aid]."""
    v = copy.deepcopy(spec)
    v["characters"] = [c for c in v.get("characters", []) if c.get("id") == aid]
    union = set()
    for b in spec.get("beats", []):
        for ae in (b.get("actor_emotions") or {}).values():
            em = ae.get("emotion") or {}; union |= {em.get("primary"), em.get("secondary")}
    for b in v.get("beats", []):
        ae = (b.get("actor_emotions") or {}).get(aid)
        if ae:
            b["emotion"] = ae.get("emotion"); b["emotion_track"] = ae.get("emotion_track") or {}
            if ae.get("emotion_change"): b["emotion_change"] = ae["emotion_change"]
            else: b.pop("emotion_change", None)
            lt = b.get("light") or {}
            if lt.get("serves_emotion") in union and lt.get("serves_emotion") not in ((ae.get("emotion") or {}).get("primary"), (ae.get("emotion") or {}).get("secondary")):
                lt["serves_emotion"] = (ae.get("emotion") or {}).get("primary")   # the light serves one of the actors' feelings, not necessarily this one's
    return v

def check_emotion(spec: dict) -> list[str]:
    """One emotion block per beat for a one-character shot; with several actors every actor has its own (beat.actor_emotions[id]) and each is checked on its own."""
    ids = _actor_ids(spec)
    if len(ids) < 2:
        return _check_emotion_one(spec)
    f: list[str] = []
    for aid in ids:
        f += [re.sub(r"^(FAIL \[[A-Z0-9-]+\] )", lambda m, aid=aid: m.group(1) + f"actor {aid}: ", x) for x in _check_emotion_one(_actor_view(spec, aid))]
    return f

def _check_emotion_one(spec: dict) -> list[str]:
    f: list[str] = []; beats = spec.get("beats", [])
    for ch in spec.get("characters", []):
        ep = ch.get("emotion_profile")
        need = ("baseline", "display_rules", "hidden_feeling_channel", "leak")
        if not ep or [k for k in need if k not in ep]:
            f.append(F("EMO-PROFILE", f"character {ch.get('id')} emotion_profile missing {[k for k in need if k not in (ep or {})]} (R-372)"))
        if len(ch.get("face_controls") or []) < SPEC2["min_face_controls"]:
            f.append(F("EMO-PROFILE", f"character {ch.get('id')} face_controls = {len(ch.get('face_controls') or [])} (need >= 12 AU controls) (R-365)"))
    vfx_total = 0.0; runtime = 0.0
    for i, b in enumerate(beats):
        bid = b.get("id", "?"); em = b.get("emotion") or {}; tk = b.get("emotion_track") or {}
        if em.get("primary") not in EMOTIONS:
            f.append(F("EMO-DECLARED", f"beat {bid} emotion.primary {em.get('primary')!r} missing or outside the vocabulary (R-360)")); continue
        if not all(k in em for k in ("intensity", "shown", "cause")) or not 0 <= em.get("intensity", -1) <= 1:
            f.append(F("EMO-DECLARED", f"beat {bid} emotion needs intensity 0..1, shown and cause (R-360)"))
        if "peak_s" in em and not float(b.get("start", 0)) <= em["peak_s"] <= float(b.get("end", 0)):
            f.append(F("EMO-DECLARED", f"beat {bid} peak_s {em['peak_s']} outside the beat (R-374)"))
        have = [c for c in CHANNELS if tk.get(c)]
        nonface = [c for c in have if c != "face"]
        if len(have) < SPEC2["min_channels"] or len(nonface) < SPEC2["min_nonface_channels"]:
            f.append(F("EMO-CHANNELS", f"beat {bid} carries the feeling in {len(have)} channels / {len(nonface)} non-face (need >= 6 / >= 4) (R-361)"))
        eyes = tk.get("eyes") or {}; face = tk.get("face") or {}; body = tk.get("body") or {}
        reflex = "reflex" in str(em.get("cause", "")).lower() or b.get("reflex")
        if not reflex and eyes and face and body and not (eyes.get("onset_s", 9e9) <= face.get("onset_s", -1) and eyes.get("onset_s", 9e9) <= body.get("onset_s", -1)):
            f.append(F("EMO-ORDER", f"beat {bid} eyes onset {eyes.get('onset_s')} is not the earliest (face {face.get('onset_s')}, body {body.get('onset_s')}) (R-362)"))
        if not eyes.get("gaze_target") or (_dur(b) > 0.5 and not eyes.get("darts_per_s")):
            f.append(F("EMO-GAZE", f"beat {bid} eyes need gaze_target and darts_per_s > 0 (R-363)"))
        bb = eyes.get("blink_per_min")
        if bb:
            lo, hi = BLINK_BANDS.get(em["primary"], BLINK_DEFAULT_BAND)
            if bb[0] < lo or bb[1] > hi:
                f.append(F("EMO-BLINK", f"beat {bid} blink_per_min {bb} outside the {em['primary']} band {[lo, hi]} (R-364)"))
        else:
            f.append(F("EMO-BLINK", f"beat {bid} eyes.blink_per_min missing (R-364)"))
        if em.get("shown") == "hidden":
            if not em.get("leak_channel") or em.get("leak_channel") == "none":
                f.append(F("EMO-HIDDEN", f"beat {bid} hidden feeling has no leak_channel (R-373)"))
        if em.get("blend") and abs(sum(em["blend"].values()) - 1.0) > 0.01:
            f.append(F("EMO-HIDDEN", f"beat {bid} blend weights sum {sum(em['blend'].values()):.2f} (need 1) (R-373)"))
        if i > 0:
            pe = (beats[i - 1].get("emotion") or {}).get("primary")
            if pe and pe != em["primary"]:
                pc = (beats[i - 1].get("emotion_track") or {}).get("colour") or {}; cc = tk.get("colour") or {}
                if all(pc.get(k) == cc.get(k) for k in ("hue_family", "sat", "value")):
                    f.append(F("EMO-COLOUR", f"beat {bid} emotion changes {pe}->{em['primary']} with no hue/sat/value change in colour (R-370)"))
                ec = b.get("emotion_change") or {}
                lo, hi = SPEC2["emotion_change_frames"]
                if not ec or not ec.get("bridge") or not lo <= ec.get("frames", 0) <= hi:
                    if not reflex:
                        f.append(F("EMO-CHANGE", f"beat {bid} emotion {pe}->{em['primary']} needs emotion_change with bridge and 6..24 frames (R-378)"))
        vf = tk.get("vfx") or []; sf = tk.get("sfx") or []
        vfx_total += len(vf); runtime += _dur(b)
        if len(vf) > SPEC2["max_vfx_per_beat"]:
            f.append(F("EMO-SFXVFX", f"beat {bid} vfx = {len(vf)} (max 1 per beat) (R-376)"))
        if em.get("intensity", 0) >= SPEC2["sfx_intensity"] and not sf:
            f.append(F("EMO-SFXVFX", f"beat {bid} intensity {em.get('intensity')} with no sfx (R-375)"))
        for v in vf:
            if v.get("box") and any(_boxes_overlap(v["box"], t["box"]) and t.get("t0", 0) < v.get("at_s", 0) + 0.5 and t.get("t1", 0) > v.get("at_s", 0)
                                    for t in b.get("texts", []) if t.get("box")):
                f.append(F("EMO-SFXVFX", f"beat {bid} vfx box covers a text box (R-376, R-334)"))
        lt = b.get("light") or {}
        if lt.get("serves_emotion") not in (em.get("primary"), em.get("secondary")):
            f.append(F("EMO-LIGHT", f"beat {bid} light.serves_emotion {lt.get('serves_emotion')!r} does not name the beat's emotion (R-371)"))
        if not any(x.get("carries_emotion") for x in b.get("interactions", [])):
            f.append(F("EMO-ENV", f"beat {bid} has no interaction with carries_emotion true (R-369)"))
    if runtime and vfx_total > SPEC2["max_vfx_per_9s"] * runtime / 9.0 + 1e-9:
        f.append(F("EMO-SFXVFX", f"vfx = {vfx_total:.0f} in {runtime:.1f} s (max 3 per 9 s) (R-376)"))
    return f

def check_voice_timing(spec: dict, root=None, files: bool = False) -> list[str]:
    """SPEC-VOICE-TIMING: a piece is timed from the real voice takes (tools/shotlib/voicetiming.py). Opt-in: a spec with voice_episode or voice_lines."""
    try:
        from shotlib import voicetiming
    except ImportError:       # qg_checks imported without tools/ on sys.path
        import sys as _s; _s.path.insert(0, str(Path(__file__).resolve().parent)); from shotlib import voicetiming
    return [F("SPEC-VOICE-TIMING", m) for m in voicetiming.issues(spec, root, files)]

def check_spec_v2(spec: dict, root=None, files: bool = False) -> list[str]:
    root = Path(root) if root else None
    return (check_voice_timing(spec, root, files) + check_bio(spec, root) + check_attach(spec) + check_shadows(spec) + check_transitions(spec)
            + check_camera(spec, root, files) + check_texts(spec) + check_emotion(spec) + check_shadow_flat(spec) + check_actors(spec, root))

# ------------------------------------------------------------------ RIG checks (per-frame trace)
def _frames(ch: dict) -> list[dict]:
    return ch.get("frames", [])

def _side_key(name: str) -> str:
    return re.sub(r"_[LR]$", "", name)

def _dist(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])

def _in_window(t: float, wins) -> bool:
    return any(w[0] - 1e-9 <= t <= w[1] + 1e-9 for w in wins)

def _spec_windows(spec: dict | None, cid: str, key: str, field: str | None = None, match: str | None = None):
    out = []
    if not spec:
        return out
    for b in spec.get("beats", []):
        for ps in b.get("poses", []):
            if ps.get("character") != cid:
                continue
            for e in ps.get(key, []):
                if match is None or e.get(field) == match:
                    out.append((float(e.get("t0", 0)), float(e.get("t1", 0))))
    return out

def _beats_for(spec: dict | None, cid: str) -> list[dict]:
    """The beats as actor `cid` lives them: its own emotion / emotion_track (beat.actor_emotions[cid]) where the spec declares them."""
    out = []
    for b in (spec or {}).get("beats", []):
        ae = (b.get("actor_emotions") or {}).get(cid)
        if ae:
            b = dict(b, emotion=ae.get("emotion", b.get("emotion")), emotion_track=ae.get("emotion_track", b.get("emotion_track")))
        out.append(b)
    return out

def rig_limits(trace: dict, spec: dict | None, root=None) -> list[str]:
    f = []
    for cid, ch in trace.get("characters", {}).items():
        sc = next((c for c in (spec or {}).get("characters", []) if c.get("id") == cid), {})
        prof = resolve_profile(ch.get("profile") or sc.get("physics_profile") or "_human-default", spec, root) or HUMAN_DEFAULT
        lim = prof["limits_deg"]; run = {}
        for fr in _frames(ch):
            for j, ang in (fr.get("joints") or {}).items():
                k = _side_key(j)
                if k not in lim:
                    continue
                soft, hard = lim[k]["soft"], lim[k]["hard"]
                if not hard[0] <= ang <= hard[1]:
                    f.append(F("RIG-LIMITS", f"{cid} frame {fr['f']} {j} = {ang:.1f} deg beyond the HARD limit {hard} (R-301)")); continue
                if not soft[0] <= ang <= soft[1]:
                    wins = [w for w in _spec_windows(spec, cid, "exceed", "joint", j) + _spec_windows(spec, cid, "exceed", "joint", k)]
                    if _in_window(fr["t"], wins):
                        continue
                    run[j] = run.get(j, 0) + 1
                    f.append(F("RIG-LIMITS", f"{cid} frame {fr['f']} {j} = {ang:.1f} deg beyond the soft limit {soft}, no exceed window (R-301)"))
    return f

def rig_hinge(trace: dict, spec=None) -> list[str]:
    f = []
    for cid, ch in trace.get("characters", {}).items():
        prev = None
        for fr in _frames(ch):
            for j, side in (fr.get("bend_side") or {}).items():
                if prev and j in prev["bend_side"] and prev["bend_side"][j] != side and side != 0 and prev["bend_side"][j] != 0:
                    ang = (fr.get("joints") or {}).get(j.replace("elbow", "elbow_flex").replace("knee", "knee_flex"), 0)
                    pang = (prev.get("joints") or {}).get(j.replace("elbow", "elbow_flex").replace("knee", "knee_flex"), 0)
                    if max(abs(ang), abs(pang)) >= RIG["hinge_flip_deg"]:
                        f.append(F("RIG-HINGE", f"{cid} frame {fr['f']} {j} bend side flips {prev['bend_side'][j]}->{side} at {pang:.0f}->{ang:.0f} deg (R-302)"))
            prev = fr
    return f

def rig_seglen(trace: dict, spec: dict | None, root=None) -> list[str]:
    f = []
    for cid, ch in trace.get("characters", {}).items():
        rest = ch.get("rest_lengths_px") or {}
        sc = next((c for c in (spec or {}).get("characters", []) if c.get("id") == cid), {})
        prof = resolve_profile(ch.get("profile") or sc.get("physics_profile") or "_human-default", spec, root) or HUMAN_DEFAULT
        tol = float(prof.get("bone_lengths_tolerance_pct", RIG["seg_tol_pct"])) / 100.0
        for fr in _frames(ch):
            for s, ln in (fr.get("segments_px") or {}).items():
                if s in rest and abs(ln - rest[s]) > tol * rest[s]:
                    if _in_window(fr["t"], _spec_windows(spec, cid, "stretch_events", "segment", s) + _spec_windows(spec, cid, "stretch_events", "segment", _side_key(s))):
                        continue
                    f.append(F("RIG-SEGLEN", f"{cid} frame {fr['f']} {s} = {ln:.1f} px vs rest {rest[s]:.1f} ({(ln / rest[s] - 1) * 100:+.1f}%, tol {tol * 100:.0f}%) (R-303, R-344)"))
    return f

def rig_contacts(trace: dict) -> list[str]:
    f = []
    for cid, ch in trace.get("characters", {}).items():
        for fr in _frames(ch):
            for c in fr.get("contacts") or []:
                limb = float(c.get("limb_len_px", 0))
                if limb <= 0:
                    continue
                gap = _dist(c["point"], c["target"])
                if gap > RIG["contact_tol_limb"] * limb:
                    f.append(F("RIG-CONTACT-GAP", f"{cid} frame {fr['f']} {c.get('id')} misses its target by {gap:.1f} px = {gap / limb * 100:.1f}% of limb (max 2%) (R-304, R-310)"))
                if c.get("shoulder"):
                    r = _dist(c["shoulder"], c["target"]) / limb
                    lo, hi = RIG["reach_ratio"]
                    if not lo <= r <= hi:
                        f.append(F("RIG-REACH", f"{cid} frame {fr['f']} {c.get('id')} reach ratio {r:.2f} (need {lo}..{hi}): out of reach or inside the joint (R-304, R-305)"))
    return f

def rig_attach(trace: dict, spec: dict | None) -> list[str]:
    f = []
    for cid, ch in trace.get("characters", {}).items():
        sc = next((c for c in (spec or {}).get("characters", []) if c.get("id") == cid), {})
        for a in sc.get("attachments", []):
            gap_max = float(a.get("max_gap_px", 4)); streak = 0
            for fr in _frames(ch):
                anc = (fr.get("anchors") or {}).get(a["parent_anchor"]); cps = fr.get("contact_points") or {}
                worst = 0.0
                if anc is not None:
                    worst = max([_dist(cps[n], anc) for n in a["contact_points"] if n in cps] or [0.0])
                streak = streak + 1 if worst > gap_max else 0
                if streak == 2:
                    f.append(F("RIG-ATTACH", f"{cid} frame {fr['f']} {a['id']} contact is {worst:.1f} px from {a['parent_anchor']} for 2+ frames (max {gap_max}) (R-351)"))
    return f

def rig_layers(trace: dict, spec: dict | None) -> list[str]:
    f = []
    for cid, ch in trace.get("characters", {}).items():
        sc = next((c for c in (spec or {}).get("characters", []) if c.get("id") == cid), {})
        for fr in _frames(ch):
            lo = fr.get("layer_order")
            if not lo:
                continue
            for a in sc.get("attachments", []):
                want = (a.get("layer_order") or {}).get(lo.get("angle"))
                if not want:
                    continue
                got = [p for p in lo["order"] if p in want]
                if got != [p for p in want if p in got] or len(got) != len(want):
                    f.append(F("RIG-LAYERS", f"{cid} frame {fr['f']} angle {lo.get('angle')} draws {got}, declared {want} (R-352)"))
                    break
    return f

def shoulder_lift_model(elev_deg: float, hu: float) -> float:
    """Expected rise of the shoulder point (px) for a humeral elevation (R-308, scapulohumeral rhythm).
    Onset at 30 deg (the first ~30 deg are almost all glenohumeral), then the shoulder girdle carries 1 of every 3 degrees
    (2:1 glenohumeral:scapular, Inman 1944; source-backed). The slope, 0.1 head per 60 deg, is a judgement calibration
    (Mix v5). Linear, capped at 180 deg."""
    return RIG["lift_heads_per_60"] * hu * max(0.0, min(elev_deg, 180.0) - RIG["rides_min_elev"]) / 60.0

def _arc_inward(lift_px: float, half_w: float) -> float:
    """The shoulder point rides a circle about the sternal end of the clavicle (radius ~ the half shoulder width):
    a rise of `lift_px` also moves it inward by L*(1 - cos(asin(lift/L)))."""
    if half_w <= 0:
        return 0.0
    r = min(abs(lift_px) / half_w, 1.0)
    return half_w * (1.0 - math.sqrt(1.0 - r * r))
