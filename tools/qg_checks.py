"""Story-Wrap quality gate, part 2: merged spec checks (R-300..R-379), rig-trace checks and render extras.

Pure functions, numpy only (scipy/PIL imported lazily). Imported by tools/quality_gate.py; unit-tested in tools/tests/.
Every failure string is "FAIL [CHECK-ID] message"; the check ids are listed in kb/quality/gate-spec.md.
Calibration status per check: CALIBRATED = derived from a measured sample, DEFAULT = judgement default [J] not yet
calibrated on real renders (see CHECK_STATUS and gate-spec.md).
"""
from __future__ import annotations
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

def rig_shoulder_clavicle(trace: dict) -> list[str]:
    """RIG-SHOULDER (R-341/R-342). The allowed shoulder point is a function of humeral elevation: x at the clavicle end
    (inward shift along the clavicle arc as it rises), y at the rest line minus the scapulohumeral lift (a voluntary shrug may add up to 0.2 head above it, never below). y is "up negative"
    as the tracer writes it. Rest line: `rest_shoulder_y_px` on the character, else the median of (y + model lift) over the
    lowest third of elevations. Frames with no `arm_elevation_deg` fall back to the old fixed clavicle line."""
    f = []
    for cid, ch in trace.get("characters", {}).items():
        hu = float(ch.get("head_unit_px", 0)) or 1.0
        frames = _frames(ch)
        rest = ch.get("rest_shoulder_y_px")
        if rest is None:
            smp = []
            for fr in frames:
                el = fr.get("arm_elevation_deg") or {}
                for s in ("L", "R"):
                    sh = (fr.get("anchors") or {}).get(f"shoulder_{s}")
                    if sh is not None and el.get(s) is not None:
                        smp.append((float(el[s]), sh[1] + shoulder_lift_model(float(el[s]), hu)))
            if smp:
                smp.sort(); low = [v for _, v in smp[:max(1, len(smp) // 3)]]
                low.sort(); rest = low[len(low) // 2]
        for fr in frames:
            an = fr.get("anchors") or {}
            if "torso_center" not in an or "torso_half_width_px" not in fr:
                continue
            hw = fr["torso_half_width_px"]
            for s in ("L", "R"):
                sh = an.get(f"shoulder_{s}")
                if sh is None:
                    continue
                e = (fr.get("arm_elevation_deg") or {}).get(s)
                lift = shoulder_lift_model(float(e), hu) if e is not None and rest is not None else None
                inward = _arc_inward(lift, hw) if lift else 0.0
                dx = abs(sh[0] - an["torso_center"][0]); need = RIG["shoulder_x_frac"] * hw - inward
                if dx < need:
                    f.append(F("RIG-SHOULDER", f"{cid} frame {fr['f']} shoulder_{s} is {dx:.1f} px from the torso centre, edge is {hw:.1f} (need >= {need:.1f} at elevation {e if e is not None else 0:.0f} deg): sleeve from the chest (R-341)"))
                if lift is not None:
                    want = rest - lift; low = RIG["shoulder_y_heads"] * hu + RIG["shoulder_y_lift_frac"] * lift
                    if sh[1] - want > low:     # lower than the arm allows: the shoulder stayed down
                        f.append(F("RIG-SHOULDER", f"{cid} frame {fr['f']} shoulder_{s} y {sh[1]:.1f} is {sh[1] - want:.1f} px below the scapulohumeral line {want:.1f} for elevation {e:.0f} deg (allowed {low:.1f}; the shoulder must rise {lift:.1f} px with the arm) (R-341, R-308)"))
                    elif want - sh[1] > RIG["shrug_max_heads"] * hu:     # higher than lift plus a shrug can explain
                        f.append(F("RIG-SHOULDER", f"{cid} frame {fr['f']} shoulder_{s} y {sh[1]:.1f} is {want - sh[1]:.1f} px above the scapulohumeral line {want:.1f} (a shrug is allowed up to {RIG['shrug_max_heads'] * hu:.1f} px) (R-341)"))
                elif "clavicle_y" in fr and abs(sh[1] - fr["clavicle_y"]) > RIG["shoulder_y_heads"] * hu:
                    f.append(F("RIG-SHOULDER", f"{cid} frame {fr['f']} shoulder_{s} y is off the clavicle line by {abs(sh[1] - fr['clavicle_y']):.1f} px (R-341)"))
            if "neck_length_px" in fr and fr["neck_length_px"] < RIG["neck_min_heads"] * hu:
                f.append(F("RIG-SHOULDER", f"{cid} frame {fr['f']} neck {fr['neck_length_px']:.1f} px < {RIG['neck_min_heads'] * hu:.1f} (R-342)"))
    return f

def rig_shoulder_rides(trace: dict) -> list[str]:
    f = []
    for cid, ch in trace.get("characters", {}).items():
        hu = float(ch.get("head_unit_px", 0)) or 1.0
        for s in ("L", "R"):
            el = []; lift = []
            for fr in _frames(ch):
                e = (fr.get("arm_elevation_deg") or {}).get(s); l = (fr.get("shoulder_lift_px") or {}).get(s)
                if e is not None and l is not None and e > RIG["rides_min_elev"]:
                    el.append(e); lift.append(l)
            if len(el) < 4 or max(el) - min(el) < 40:
                continue
            c = _corr(el, lift)
            if c < RIG["rides_corr"] or max(lift) < RIG["rides_min_lift_heads"] * hu * (max(el) - RIG["rides_min_elev"]) / 90.0:
                f.append(F("RIG-SHOULDER-RIDES", f"{cid} arm {s}: shoulder lift correlates {c:.2f} with elevation, max lift {max(lift):.1f} px (need corr >= 0.7 and about 0.1 head per 60 deg) (R-308)"))
    return f

def _corr(a, b) -> float:
    n = len(a)
    if n < 2:
        return 0.0
    ma, mb = sum(a) / n, sum(b) / n
    sa = math.sqrt(sum((x - ma) ** 2 for x in a)); sb = math.sqrt(sum((y - mb) ** 2 for y in b))
    if sa < 1e-9 or sb < 1e-9:
        return 0.0
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb)

def rig_balance(trace: dict, spec=None, root=None) -> list[str]:
    f = []
    for cid, ch in trace.get("characters", {}).items():
        for fr in _frames(ch):
            if "com" not in fr or "support_x" not in fr:
                continue
            x0, x1 = fr["support_x"]; m = RIG["com_margin_pct"] / 100.0 * (x1 - x0)
            if not x0 - m <= fr["com"][0] <= x1 + m:
                f.append(F("RIG-BALANCE", f"{cid} frame {fr['f']} centre of mass x {fr['com'][0]:.1f} outside support {x0:.0f}..{x1:.0f} +- {m:.1f} (R-314)"))
    return f

def _blink_runs(frames: list[dict]):
    runs = []; start = None
    for i, fr in enumerate(frames):
        b = ((fr.get("face") or {}).get("blink", 0) or 0) >= 0.5
        if b and start is None:
            start = i
        if not b and start is not None:
            runs.append((start, i - start)); start = None
    if start is not None:
        runs.append((start, len(frames) - start))
    return runs

def rig_blink(trace: dict, spec: dict | None) -> list[str]:
    f = []; fps = float(trace.get("fps", 24))
    for cid, ch in trace.get("characters", {}).items():
        frames = _frames(ch)
        for (s, n) in _blink_runs(frames):
            nf = n * 24.0 / fps
            if not RIG["blink_frames"][0] <= round(nf) <= RIG["blink_frames"][1]:
                f.append(F("RIG-BLINK", f"{cid} frame {frames[s]['f']} blink lasts {n} frames at {fps:g} fps (need 2..5 at 24 fps) (R-364)"))
        for b in _beats_for(spec, cid):
            em = b.get("emotion") or {}; band = ((b.get("emotion_track") or {}).get("eyes") or {}).get("blink_per_min")
            seg = [fr for fr in frames if float(b["start"]) <= fr["t"] < float(b["end"])]
            if not seg:
                continue
            starts = [seg[s]["t"] for s, _ in _blink_runs(seg)]
            d = _dur(b)
            if band and d >= 4:
                cnt = len(starts)
                if not (band[0] * d / 60.0 - 1 <= cnt <= band[1] * d / 60.0 + 1):
                    f.append(F("RIG-BLINK", f"{cid} beat {b['id']} measured {cnt} blinks in {d:.1f} s = {cnt * 60 / d:.1f}/min, declared {band} (R-364)"))
            gaps = [round(b2 - a, 3) for a, b2 in zip(starts, starts[1:])]
            if len(gaps) >= 2 and len(set(gaps)) == 1:
                f.append(F("RIG-BLINK", f"{cid} beat {b['id']} blink intervals are all {gaps[0]} s: placed, not metronomic (R-364)"))
    return f

def _speed(frames):
    out = [0.0]
    for a, b in zip(frames, frames[1:]):
        fa, fb = a.get("face") or {}, b.get("face") or {}
        out.append(math.hypot(fb.get("eye_x", 0) - fa.get("eye_x", 0), fb.get("eye_y", 0) - fa.get("eye_y", 0)))
    return out

def rig_eye_dart(trace: dict, spec: dict | None) -> list[str]:
    f = []; fps = float(trace.get("fps", 24))
    for cid, ch in trace.get("characters", {}).items():
        frames = _frames(ch)
        if not frames:
            continue
        sp = _speed(frames); med = sorted(sp)[len(sp) // 2]; thr = max(3 * med, RIG["dart_min_speed"])
        for b in _beats_for(spec, cid):
            if (b.get("emotion") or {}).get("intensity", 0) < 0.3:
                continue
            t = float(b["start"])
            while t + 1.0 <= float(b["end"]) + 1e-9:
                idx = [i for i, fr in enumerate(frames) if t <= fr["t"] < t + 1.0]
                if idx and max(sp[i] for i in idx) < thr:
                    f.append(F("RIG-EYE-DART", f"{cid} {t:.1f}-{t + 1:.1f} s in beat {b['id']} the eyes never move on their own (no dart above {thr:.3f}) (R-363)"))
                t += 1.0
        ex = [(fr.get("face") or {}).get("eye_x", 0) for fr in frames]; hy = [(fr.get("face") or {}).get("head_yaw", 0) for fr in frames]
        c = _corr(ex, hy)
        if c > RIG["eye_head_corr_max"] and max(hy) - min(hy) > 1e-6:
            f.append(F("RIG-EYE-INDEP", f"{cid} eye position correlates {c:.2f} with head yaw (max 0.9): eyes only follow the head (R-363)"))
    return f

def rig_eye_lead(trace: dict) -> list[str]:
    f = []
    for cid, ch in trace.get("characters", {}).items():
        frames = _frames(ch)
        ex = [(fr.get("face") or {}).get("eye_x", 0) for fr in frames]; hy = [(fr.get("face") or {}).get("head_yaw", 0) for fr in frames]
        if len(frames) < 12 or max(hy) - min(hy) < RIG["head_move_deg"]:
            continue
        ev = [b - a for a, b in zip(ex, ex[1:])]; hv = [b - a for a, b in zip(hy, hy[1:])]
        best, bk = -9, 0
        for k in range(-8, 9):
            a = ev[max(0, -k): len(ev) - max(0, k)]; b = hv[max(0, k): len(hv) - max(0, -k)]
            c = _corr(a, b) if len(a) == len(b) and len(a) > 3 else -9
            if c > best:
                best, bk = c, k
        if not RIG["eye_lead"][0] <= bk <= RIG["eye_lead"][1]:
            f.append(F("RIG-EYE-LEAD", f"{cid} the eyes lead the head by {bk} frames (need 2..4) (R-362)"))
    return f

def _face_series(frames):
    names = set()
    for fr in frames:
        fc = fr.get("face") or {}
        names |= set(fc.get("controls", {}).keys())
        names |= {k for k in ("brow_L", "brow_R", "lid_upper", "lid_lower", "iris_r", "mouth_open", "corner_L", "corner_R") if k in fc}
    def val(fr, n):
        fc = fr.get("face") or {}
        return fc.get("controls", {}).get(n, fc.get(n, 0.0))
    return {n: [val(fr, n) for fr in frames] for n in names}

def rig_face(trace: dict, spec: dict | None) -> list[str]:
    f = []
    for cid, ch in trace.get("characters", {}).items():
        frames = _frames(ch)
        ser = _face_series(frames)
        moving = [n for n, v in ser.items() if v and max(v) - min(v) >= RIG["face_control_delta"]]
        if len(moving) < RIG["face_controls_changed"]:
            f.append(F("RIG-FACE", f"{cid} only {len(moving)} face controls move by >= 0.15 over the film (need >= 5; a 1-control face reads as surprise only) (R-365)"))
        for b in _beats_for(spec, cid):
            pk = (b.get("emotion") or {}).get("peak_s")
            if pk is None or len(frames) < 3:
                continue
            seg = [i for i, fr in enumerate(frames) if float(b["start"]) <= fr["t"] <= float(b["end"]) and i > 0]
            if not seg:
                continue
            ch_amt = {i: sum(abs(v[i] - v[i - 1]) for n, v in ser.items() if n != "mouth_open") for i in seg}   # the EMOTION peak: the mouth's own opening is speech (a viseme moves it every few frames, C6), not feeling; the jaw AU26 still counts
            top = max(ch_amt, key=ch_amt.get); fps = float(trace.get("fps", 24))
            if abs(frames[top]["t"] - pk) * fps > RIG["peak_frames"]:
                f.append(F("RIG-PEAK", f"{cid} beat {b['id']} biggest face change at {frames[top]['t']:.2f} s, declared peak_s {pk} (R-374)"))
    return f

def shadow_mask_issues(mask, label: str = "") -> list[str]:
    """mask: 2-D bool array. FAIL on interior holes >= 4 px and on more than one connected component."""
    import numpy as np
    from scipy import ndimage as ndi
    m = np.asarray(mask, bool)
    if not m.any():
        return [F("RIG-SHADOW-HOLES", f"{label} shadow mask is empty (R-356)")]
    filled = ndi.binary_fill_holes(m)
    holes = filled & ~m
    lab, n = ndi.label(holes)
    big = [int((lab == i).sum()) for i in range(1, n + 1) if (lab == i).sum() >= RENDER2["shadow_hole_px"]]
    out = []
    if big:
        out.append(F("RIG-SHADOW-HOLES", f"{label} shadow mask has {len(big)} interior holes {big[:4]} px (hollow gradient / cut-out) (R-356)"))
    _, comps = ndi.label(m)
    if comps > 1:
        out.append(F("RIG-SHADOW-HOLES", f"{label} shadow mask has {comps} separate pieces for one caster (clip cut-out) (R-356)"))
    return out

def rig_shadow(trace: dict, base: Path | None = None) -> list[str]:
    f = []
    try:
        from PIL import Image
        import numpy as np
    except ImportError:
        return [F("RIG-SHADOW-HOLES", "numpy/PIL missing")]
    for cid, ch in trace.get("characters", {}).items():
        for fr in _frames(ch):
            p = fr.get("shadow_mask")
            if not p:
                continue
            pp = Path(p) if Path(p).is_absolute() or base is None else Path(base) / p
            if not pp.exists():
                f.append(F("RIG-SHADOW-HOLES", f"{cid} frame {fr['f']} shadow mask {p} not found (R-356)")); continue
            im = Image.open(pp).convert("L"); w, h = im.size
            im = im.resize((max(w // 2, 1), max(h // 2, 1)))
            f += shadow_mask_issues(np.asarray(im) > 127, f"{cid} frame {fr['f']}")
    return f

# ------------------------------------------------------------------ HANDS, PROPS AND WRITING (R-383..R-392, gate-spec L)
HANDW = {"topo_fingers": 4, "finger_order": ["thumb", "index", "middle", "ring", "little"],
         "max_joint_jump_deg": 25.0,      # largest single-frame change of any finger joint angle (calibrated on v5: its max is 12.1 deg)
         "max_orient_jump_deg": 30.0,     # single-frame change of the hand axis (calibrated on v5: max 15.7 deg; the v4 snap turned about 45)
         "max_wrist_jump_px": 120.0,      # single-frame wrist travel (1080x1920 canvas) unless a cut or a declared smear (DEFAULT: v5 reaches 86.7 px, so no tighter value is evident)
         "swap_frames": 4,                # in-between frames a grip / contact-kind / pinch change needs
         "nib_gap_px": 3.0, "reveal_tol_px": 6.0, "grip_contact_px": 8.0,   # nib_gap calibrated on v5 (0 px while writing); grip_contact kept (v5 max 6.8 px)
         "min_toward_share": 0.5}

def _hp(fr: dict) -> dict:
    return fr.get("hand_pose") or {}

def _waived(fr: dict) -> bool:
    return bool(fr.get("cut") or fr.get("smear"))

def rig_hand_topo(trace: dict) -> list[str]:
    """HAND-TOPO (R-383, R-384) and HAND-SIDE (R-385): finger count and order constant, no single-frame shape jump, grip named for its side."""
    f = []
    for cid, ch in trace.get("characters", {}).items():
        fr_all = _frames(ch)
        for side in ("L", "R"):
            prev, topo0, bad = None, None, {}
            for fr in fr_all:
                hp = _hp(fr).get(side)
                if not hp:
                    prev = None
                    continue
                gid = hp.get("id", "")
                m = re.search(r"-([LR])$", gid)
                if m and m.group(1) != side and not hp.get("mirrored"):
                    bad.setdefault("HAND-SIDE", f"{cid} frame {fr['f']} hand {side} uses grip {gid} authored for the {m.group(1)} hand without `mirrored: true` (R-385)")
                tp = hp.get("topo") or {}
                key = (tp.get("fingers"), tuple(tp.get("order") or ()))
                if tp:
                    if tp.get("fingers") != HANDW["topo_fingers"] or list(tp.get("order") or ()) != HANDW["finger_order"]:
                        bad.setdefault("HAND-TOPO", f"{cid} frame {fr['f']} hand {side} topology {key}, expected 4 fingers + thumb in order {HANDW['finger_order']} (R-383)")
                    if topo0 is None:
                        topo0 = key
                    elif key != topo0:
                        bad.setdefault("HAND-TOPO", f"{cid} frame {fr['f']} hand {side} topology changed {topo0} -> {key} (R-383)")
                if prev is not None and not _waived(fr):
                    pf, cf = (prev.get("fingers") or {}), (hp.get("fingers") or {})
                    worst, wn = 0.0, ""
                    for fn in cf:
                        a, b = pf.get(fn), cf.get(fn)
                        if a and b:
                            for i, (x, y) in enumerate(zip(a, b)):
                                if abs(x - y) > worst:
                                    worst, wn = abs(x - y), f"{fn}[{i}]"
                    if worst > HANDW["max_joint_jump_deg"]:
                        bad.setdefault("HAND-TOPO", f"{cid} frame {fr['f']} hand {side} joint {wn} jumps {worst:.0f} deg in one frame (max {HANDW['max_joint_jump_deg']:.0f}; declare `smear` if intended) (R-384)")
                    if prev.get("orient_deg") is not None and hp.get("orient_deg") is not None:
                        d = (hp["orient_deg"] - prev["orient_deg"] + 180) % 360 - 180
                        if abs(d) > HANDW["max_orient_jump_deg"]:
                            bad.setdefault("HAND-TOPO", f"{cid} frame {fr['f']} hand {side} axis turns {d:.0f} deg in one frame (max {HANDW['max_orient_jump_deg']:.0f}) (R-384)")
                    if prev.get("wrist_px") and hp.get("wrist_px"):
                        d = _dist(prev["wrist_px"], hp["wrist_px"])
                        if d > HANDW["max_wrist_jump_px"]:
                            bad.setdefault("HAND-TOPO", f"{cid} frame {fr['f']} hand {side} wrist moves {d:.0f} px in one frame (max {HANDW['max_wrist_jump_px']:.0f}) (R-384)")
                prev = hp
            f += [F(k, v) for k, v in bad.items()]
    return f

def rig_hand_swap(trace: dict) -> list[str]:
    """HAND-SWAP (R-386): a change of grip id, contact kind or pinch needs >= N in-between frames carrying blend{to_id,to_kind,k} with k rising."""
    f = []
    n = HANDW["swap_frames"]
    for cid, ch in trace.get("characters", {}).items():
        for side in ("L", "R"):
            hist = []
            for fr in _frames(ch):
                hp = _hp(fr).get(side)
                if not hp:
                    hist = []
                    continue
                key = (hp.get("id"), hp.get("contact_kind"), bool(hp.get("pinch")))
                if hist and key != hist[-1][0] and not _waived(fr):
                    run = [h[1] for h in hist[-n:]]
                    ok = len(run) >= n and all(b and b.get("k") is not None and b.get("to_id", key[0]) == key[0] and b.get("to_kind", key[1]) == key[1] for b in run) \
                        and all(run[i]["k"] < run[i + 1]["k"] for i in range(len(run) - 1))
                    if not ok:
                        f.append(F("HAND-SWAP", f"{cid} frame {fr['f']} hand {side} changes {hist[-1][0]} -> {key} with {sum(1 for b in run if b)} of {n} required in-between frames (R-386)"))
                hist.append((key, hp.get("blend")))
    return f

def rig_prop_face(trace: dict) -> list[str]:
    """PROP-FACE (R-387, R-388): a mark is drawn only on the face the camera sees, and on the face the nib is touching."""
    f = []
    for cid, ch in trace.get("characters", {}).items():
        for fr in _frames(ch):
            wr = fr.get("writing") or {}
            for pr in fr.get("props", []):
                faces = pr.get("faces") or {}
                for mk in pr.get("marks", []):
                    if not mk.get("drawn", True):
                        continue
                    if mk.get("face") not in faces:
                        return f + [F("PROP-FACE", f"{cid} frame {fr['f']} prop {pr.get('id')} mark {mk.get('id')} is on undeclared face {mk.get('face')} (R-387)")]
                    if pr.get("facing") and mk["face"] != pr["facing"]:
                        return f + [F("PROP-FACE", f"{cid} frame {fr['f']} prop {pr.get('id')} mark {mk.get('id')} is drawn on its {mk['face']} but the camera sees its {pr['facing']} (R-387)")]
                    if wr.get("active") and wr.get("prop") == pr.get("id") and wr.get("nib_face") and mk.get("kind") == "ink" and mk["face"] != wr["nib_face"]:
                        return f + [F("PROP-FACE", f"{cid} frame {fr['f']} nib touches the {wr['nib_face']} of {pr.get('id')} but the ink is drawn on its {mk['face']} (R-388)")]
    return f

def rig_write_reveal(trace: dict) -> list[str]:
    """WRITE-REVEAL (R-389, R-390): ink grows only at the nib, never shrinks, only while writing, in the script's direction."""
    f = []
    for cid, ch in trace.get("characters", {}).items():
        prev, dxs, direction = None, [], None
        for fr in _frames(ch):
            wr = fr.get("writing")
            if not wr:
                prev = None
                continue
            direction = wr.get("direction", direction)
            L, d, nib = wr.get("ink_len_px", 0.0), wr.get("drawn_to_px"), wr.get("nib_px")
            if not wr.get("active") and prev is not None and L > prev["L"] + 0.5:
                f.append(F("WRITE-REVEAL", f"{cid} frame {fr['f']} ink grows {L - prev['L']:.1f} px while the nib is not writing (R-389)"))
                break
            if prev is not None and L < prev["L"] - 0.5 and not wr.get("erase"):
                f.append(F("WRITE-REVEAL", f"{cid} frame {fr['f']} ink shrinks (R-389)"))
                break
            if wr.get("active") and d and nib and _dist(d, nib) > HANDW["reveal_tol_px"]:
                f.append(F("WRITE-REVEAL", f"{cid} frame {fr['f']} ink end is {_dist(d, nib):.1f} px from the nib (max {HANDW['reveal_tol_px']:.0f}): ink is not revealed under the nib (R-389)"))
                break
            if wr.get("active") and prev is not None and prev.get("d") and d and L > prev["L"] + 0.5:
                dxs.append(d[0] - prev["d"][0])
            prev = {"L": L, "d": d}
        if len(dxs) >= 6 and direction in ("rtl", "ltr"):
            toward = sum(1 for x in dxs if (x <= 0 if direction == "rtl" else x >= 0)) / len(dxs)
            net = sum(dxs)
            if toward < HANDW["min_toward_share"] or (net > 0 if direction == "rtl" else net < 0):
                f.append(F("WRITE-REVEAL", f"{cid} writes {direction} but only {toward:.0%} of ink-growing frames move that way, net dx {net:.0f} px (R-390)"))
    return f

def rig_nib_contact(trace: dict) -> list[str]:
    """NIB-CONTACT (R-391): while writing, the nib tip is on the paper (gap <= N px, inside the paper)."""
    f = []
    for cid, ch in trace.get("characters", {}).items():
        for fr in _frames(ch):
            wr = fr.get("writing")
            if not wr or not wr.get("active"):
                continue
            gap = wr.get("nib_gap_px")
            if gap is None and wr.get("nib_px") and wr.get("paper_px"):
                gap = _dist(wr["nib_px"], wr["paper_px"])
            if gap is None:
                f.append(F("NIB-CONTACT", f"{cid} frame {fr['f']} writing without nib_gap_px or nib_px + paper_px"))
                break
            if gap > HANDW["nib_gap_px"] or wr.get("on_paper") is False:
                f.append(F("NIB-CONTACT", f"{cid} frame {fr['f']} nib is {gap:.1f} px off the paper (max {HANDW['nib_gap_px']:.0f}) or outside it (R-391)"))
                break
    return f

def rig_grip_layers(trace: dict) -> list[str]:
    """LAYER-GRIP (R-392): hand / pen / paper order drawn equals the grip's declared order for this camera angle; digits touch the held object."""
    for cid, ch in trace.get("characters", {}).items():
        for fr in _frames(ch):
            lo = fr.get("layer_order")
            for side, hp in _hp(fr).items():
                if not hp.get("holding"):
                    continue
                decl = hp.get("grip_layers") or {}
                if not decl:
                    return [F("LAYER-GRIP", f"{cid} frame {fr['f']} hand {side} holds {hp['holding']} but its grip {hp.get('id')} declares no grip_layers (R-392)")]
                if lo:
                    want = decl.get(lo.get("angle"))
                    if not want:
                        return [F("LAYER-GRIP", f"{cid} frame {fr['f']} grip {hp.get('id')} has no layer order for angle {lo.get('angle')} (R-392)")]
                    got = [p for p in lo["order"] if p in want]
                    if got != want:
                        return [F("LAYER-GRIP", f"{cid} frame {fr['f']} hand {side} draws {got}, grip {hp.get('id')} declares {want} for angle {lo.get('angle')} (R-392)")]
                far = {k: v for k, v in (hp.get("grip_contacts") or {}).items() if v > HANDW["grip_contact_px"]}
                if far:
                    return [F("LAYER-GRIP", f"{cid} frame {fr['f']} hand {side} digits {far} are further than {HANDW['grip_contact_px']:.0f} px from the held {hp['holding']}: it is not held (R-392)")]
    return []

def check_hands_writing(trace: dict) -> list[str]:
    return (rig_hand_topo(trace) + rig_hand_swap(trace) + rig_prop_face(trace) + rig_write_reveal(trace)
            + rig_nib_contact(trace) + rig_grip_layers(trace))

# ------------------------------------------------------------------ LIP SYNC (C6, the owner 2026-10-25: "the mouths do not move with the words")
# A voice-aware shot (spec["lipsync"], written by tools/calm.py from the voice stage's viseme tracks) places each on-screen speaker's line on the shot clock.
# The rig trace carries, per frame per actor, the viseme that drove the mouth (face.viseme, face.viseme_w) and the mouth as drawn (face.mouth.open ...).
#   LIPSYNC-ACTIVE   on the frames where a speaker's line is voiced, the traced viseme IS the track's viseme (frame by frame), the viseme changes at the track's rate
#                    and the mouth really opens (so a face that never reads the track, a wrong time offset or a hidden mouth all fail)
#   LIPSYNC-SILENT   on the frames where a speaker is silent (before, between words, after) the mouth is shut; an actor with NO line (the narrator speaks, not him)
#                    shows no viseme and no talking-like open/close
LIPSYNC = {"match_min": 0.95, "change_min": 0.6, "open_range_min": 0.15, "silent_open_max": 0.12, "guard_frames": 1,
           "listener_swing": 0.06, "listener_reversals_max": 1, "min_voiced_keys": 3}

def lip_track_at(e: dict, t: float):
    """Python twin of face.js visemeTrackAt for one lipsync entry, t on the SHOT clock -> (id, w) or None outside the track."""
    K = e["keys"]
    lt, ramp, end = t - float(e["start_s"]), float(e.get("ramp_s") or .04), K[-1]["t"]
    if lt < K[0]["t"] or lt > end:
        return None
    vid = K[0]["id"]
    for k in K:
        if lt >= k["t"]:
            vid = k["id"]
        else:
            break
    return vid, (0.0 if vid == "V0" else max(0.0, min(1.0, min((lt - K[0]["t"]) / ramp + .5, (end - lt) / ramp + .5))))

def _lip_expected(ents: list, t: float):
    for e in ents:
        r = lip_track_at(e, t)
        if r is not None and r[0] != "V0":
            return r[0]
    return None

def _lip_near_change(ents: list, t: float, guard: float) -> bool:
    """t within `guard` seconds of a key time or of the track's ends: the frame sits on a boundary and is not judged."""
    for e in ents:
        for k in e["keys"]:
            if abs(t - (float(e["start_s"]) + k["t"])) <= guard:
                return True
    return False

def _zigzag_reversals(series: list, swing: float) -> int:
    """How many times a series turns round, counting only turns after a move of at least `swing` (a gasp is 0 or 1, talking is many)."""
    if not series:
        return 0
    hi = lo = ext = series[0]
    direction = rev = 0
    for v in series:
        if direction == 0:
            hi, lo = max(hi, v), min(lo, v)
            if hi - lo >= swing:
                direction, ext = (1 if v >= hi else -1), v
        elif direction == 1:
            if v > ext:
                ext = v
            elif ext - v >= swing:
                direction, rev, ext = -1, rev + 1, v
        else:
            if v < ext:
                ext = v
            elif v - ext >= swing:
                direction, rev, ext = 1, rev + 1, v
    return rev

def rig_lipsync(trace: dict, spec: dict | None) -> list[str]:
    if not spec or "lipsync" not in spec:
        return []   # not a voice-aware shot: nothing to hold the mouth to
    f, L = [], LIPSYNC
    fps = float(trace.get("fps", 24))
    guard = L["guard_frames"] / fps + 1e-6
    for cid, ch in trace.get("characters", {}).items():
        frames = _frames(ch)
        if not frames:
            continue
        ents = [e for e in spec["lipsync"] if e.get("actor") == cid]
        face = lambda fr: fr.get("face") or {}
        op = lambda fr: float((face(fr).get("mouth") or {}).get("open", face(fr).get("mouth_open", 0.0)) or 0.0)
        if not ents:
            talk = [fr for fr in frames if face(fr).get("viseme")]
            if talk:
                f.append(F("LIPSYNC-SILENT", f"{cid} has no spoken line in this shot but a viseme drives its mouth on {len(talk)} frames (first at {talk[0]['t']:.2f} s): narrator lines never move a character's mouth"))
            rev = _zigzag_reversals([op(fr) for fr in frames], L["listener_swing"])
            if rev > L["listener_reversals_max"]:
                f.append(F("LIPSYNC-SILENT", f"{cid} has no spoken line but its mouth turns round {rev} times (open, close, open ...) (swings of >= {L['listener_swing']}): it reads as talking over the narrator"))
            continue
        voiced, silent = [], []
        for fr in frames:
            t = float(fr["t"])
            if _lip_near_change(ents, t, guard):
                continue
            (voiced if _lip_expected(ents, t) else silent).append(fr)
        total_voiced_keys = sum(1 for e in ents for k in e["keys"] if k["id"] != "V0")
        if total_voiced_keys and not voiced:
            f.append(F("LIPSYNC-ACTIVE", f"{cid} speaks {', '.join(e['line'] for e in ents)} but no frame of the shot falls inside the voiced part of the line (start_s {ents[0]['start_s']}): the line is cut off or placed outside the shot"))
            continue
        bad = [fr for fr in voiced if face(fr).get("viseme") != _lip_expected(ents, float(fr["t"])) or float(face(fr).get("viseme_w", 0) or 0) <= 0]
        share = 1 - len(bad) / len(voiced) if voiced else 1.0
        if share < L["match_min"]:
            b = bad[0]
            f.append(F("LIPSYNC-ACTIVE", f"{cid} mouth follows its viseme track on {share:.0%} of {len(voiced)} voiced frames (need >= {L['match_min']:.0%}); first miss at {b['t']:.2f} s: track says "
                                         f"{_lip_expected(ents, float(b['t']))}, the face drew {face(b).get('viseme')}. A scene that never passes s.viseme, a wrong time offset or a missing track gives this"))
        exp_ids = [_lip_expected(ents, float(fr["t"])) for fr in frames if not _lip_near_change(ents, float(fr["t"]), guard)]
        act_ids = [face(fr).get("viseme") for fr in frames if not _lip_near_change(ents, float(fr["t"]), guard)]
        n_exp = sum(1 for a, b in zip(exp_ids, exp_ids[1:]) if a != b and (a or b))
        n_act = sum(1 for a, b in zip(act_ids, act_ids[1:]) if a != b and (a or b))
        if n_exp and n_act < L["change_min"] * n_exp:
            f.append(F("LIPSYNC-ACTIVE", f"{cid} mouth shape changes {n_act} times, the viseme track changes {n_exp} times (need >= {L['change_min']:.0%} of them): the mouth does not keep the rhythm of the words"))
        if total_voiced_keys >= L["min_voiced_keys"] and voiced:
            opens = [op(fr) for fr in voiced]
            if max(opens) - min(opens) < L["open_range_min"]:
                f.append(F("LIPSYNC-ACTIVE", f"{cid} mouth opening varies only {max(opens) - min(opens):.2f} over the line (need >= {L['open_range_min']}): the mouth is too small, hidden or not drawn from the viseme"))
        loud = [fr for fr in silent if op(fr) > L["silent_open_max"] or float(face(fr).get("viseme_w", 0) or 0) > 0]
        if loud:
            b = max(loud, key=op)
            f.append(F("LIPSYNC-SILENT", f"{cid} mouth is open ({op(b):.2f}, viseme {face(b).get('viseme')}) on {len(loud)} of {len(silent)} frames where it is silent (first at {loud[0]['t']:.2f} s; limit {L['silent_open_max']}): closed between words and in pauses"))
    return f

# ART-PROPORTION (owner, 2026-10-25: the art book is the reference, every time): what the film DRAWS (trace frame `art`, render/hands.js artMeasure, head units) per head height must be
# within the reference's tolerance of the character's approved art-book model (catalogue/characters/<id>/artbook-proportions.json, written by tools/artbook_proportions.py from the
# data the approved sheets are drawn from). Close-ups read through the camera, never through scale. A character with no reference file, or a trace with no `art` records (a legacy
# trace), is not judged; the recorder always writes `art`, so a new trace is.
ART_HAND = ("hand_len_hu", "hand_w_hu", "finger_r_hu")
ART_FACE = ("nose_w_hu", "nose_len_hu", "lips_w_hu", "lips_t_hu", "eye_w_hu", "eye_h_hu")

def rig_art_proportion(trace: dict, root=None) -> list[str]:
    f = []
    if not root:
        return f
    for cid, ch in trace.get("characters", {}).items():
        rp = Path(root) / "catalogue" / "characters" / str(cid) / "artbook-proportions.json"
        if not rp.is_file():
            continue
        ref = json.loads(rp.read_text(encoding="utf-8"))
        tol = float(ref.get("tolerance_pct", 8.0)) / 100.0
        want = ref.get("per_head") or {}
        worst: dict = {}
        n_art = 0
        for fr in _frames(ch):
            a = fr.get("art")
            if not a:
                continue
            n_art += 1
            head = float(a.get("head_h_hu") or 0)
            if head <= 0:
                continue
            got = []
            for key in ART_HAND:
                for sd, v in (a.get(key) or {}).items():
                    got.append((f"{key[:-3]}_{sd}", key, float(v)))
            for key in ART_FACE:
                if key in a:
                    got.append((key[:-3], key, float(a[key])))
            for lab, key, v in got:
                if key not in want or want[key] <= 0:
                    continue
                dev = (v / head) / want[key] - 1
                if abs(dev) > tol:
                    w = worst.setdefault(lab, {"n": 0, "first": fr["f"], "dev": dev, "film": a.get("film")})
                    w["n"] += 1
                    if abs(dev) > abs(w["dev"]):
                        w["dev"] = dev
        for lab, w in sorted(worst.items()):
            f.append(F("ART-PROPORTION", f"{cid} {lab} is {w['dev'] * 100:+.0f}% off the art book (per head height; tolerance {tol * 100:.0f}%) on {w['n']} frames from frame {w['first']}, film profile "
                                         f"'{w['film']}' (approved sheets {ref.get('approved_sheet_version')}: {rp.name}). Close-ups read through the camera, never through scale (CLAUDE.md)"))
    return f

def check_rig(trace: dict, spec: dict | None = None, root=None, base: Path | None = None) -> list[str]:
    return (rig_limits(trace, spec, root) + rig_hinge(trace) + rig_seglen(trace, spec, root) + rig_contacts(trace)
            + rig_attach(trace, spec) + rig_layers(trace, spec) + rig_shoulder_clavicle(trace) + rig_shoulder_rides(trace)
            + rig_balance(trace) + rig_blink(trace, spec) + rig_eye_dart(trace, spec) + rig_eye_lead(trace)
            + rig_face(trace, spec) + rig_shadow(trace, base) + rig_seams(trace, base) + check_hands_writing(trace) + rig_actors(trace, spec) + rig_lipsync(trace, spec) + rig_art_proportion(trace, root))

# ------------------------------------------------------------------ MULTI-ACTOR (gate-spec N): several characters in one shot
# Spec: actors[] {id, module, depth_z, layer, catalogue_refs}, beats[].draw_order, beats[].actor_emotions{id}, actor_interactions[].
# Trace: characters{<actor id>}, scene{actors[], frames[{f, present, draw_order, depth, props[]}]}. DEFAULT numbers (no measured two-actor sample yet).
ACTOR = {"contact_tol_px": 8.0,       # a declared contact: the two points within this many canvas px on every frame of the window (= HANDW grip_contact_px)
         "handover_both_frames": 3,   # both hands on the prop for at least this many frames before the hand-off frame
         "handover_gap_px": 8.0,      # "a hand is on the prop": its contact point within this many px of the prop's grip point
         "handover_jump_px": 16.0,    # the prop's centre moves at most this far between the frame before and the hand-off frame (no teleport)
         "z_eps": 1e-6}
HANDS = ("L", "R")

def _presence():
    try:
        from shotlib import presence
    except ImportError:       # qg_checks imported without tools/ on sys.path
        import sys as _s; _s.path.insert(0, str(Path(__file__).resolve().parent)); from shotlib import presence
    return presence

def _spec_frames(spec: dict) -> int:
    """Frames of the shot: last beat end x fps."""
    ends = [float(b.get("end", 0)) for b in spec.get("beats", [])]
    return round(max(ends or [0.0]) * float(spec.get("fps", 24)))

def _actor_ids(spec) -> list:
    return [a.get("id") for a in ((spec or {}).get("actors") or [])]

def _expand_tokens(order) -> list:
    """['partner', 'hero:arms'] -> ['partner:body', 'partner:arms', 'hero:arms']: a bare id is its body then its arms."""
    out = []
    for tk in order:
        out += [f"{tk}:body", f"{tk}:arms"] if ":" not in str(tk) else [str(tk)]
    return out

def _beat_actors(b: dict, spec: dict) -> list:
    return list(b.get("actors") or _actor_ids(spec))

def _order_windows(b: dict) -> list:
    """beat.draw_order -> [(t0, t1, order, why)]; a window without t0/t1 spans the whole beat."""
    return [(float(w.get("t0", b.get("start", 0))), float(w.get("t1", b.get("end", 0))), list(w.get("order") or []), w.get("why")) for w in (b.get("draw_order") or [])]

def _declared_order(spec: dict, t: float):
    """The draw order the spec declares at time t (a window is [t0, t1); the last window also owns the final instant)."""
    beats = spec.get("beats", [])
    for bi, b in enumerate(beats):
        last = bi == len(beats) - 1
        if float(b.get("start", 0)) - 1e-9 <= t < float(b.get("end", 0)) - 1e-9 or (last and t >= float(b.get("end", 0)) - 1e-9):
            for t0, t1, order, _ in _order_windows(b):
                if t0 - 1e-9 <= t < t1 - 1e-9 or (last and t >= t1 - 1e-9):
                    return order
    return None

def _non_contiguous(tokens: list) -> list:
    """actors whose tokens are split by another actor's token (A, B, A): drawn "through" B unless the spec declares the split"""
    pos = {}
    for i, tk in enumerate(tokens):
        pos.setdefault(tk.split(":")[0], []).append(i)
    return [a for a, ix in pos.items() if ix[-1] - ix[0] + 1 != len(ix)]

def check_actors(spec: dict, root=None) -> list[str]:
    """Spec side of the multi-actor rules. A spec without `actors` is a one-character spec and is not touched."""
    f: list[str] = []
    if "actors" not in spec:
        return f
    A = spec["actors"] or []; ids = [a.get("id") for a in A]
    if not A:
        return [F("ACTOR-DECLARED", "actors[] is empty: declare each character instance (id, module, depth_z, layer, catalogue_refs)")]
    rig = {c.get("id") for c in spec.get("characters", [])}; seen = set()
    for a in A:
        aid = a.get("id")
        miss = [k for k in ("id", "module", "depth_z", "layer", "catalogue_refs") if a.get(k) in (None, "", [])]
        if miss:
            f.append(F("ACTOR-DECLARED", f"actor {aid} missing {miss}")); continue
        if aid in seen:
            f.append(F("ACTOR-DECLARED", f"actor id {aid} declared twice"))
        seen.add(aid)
        if aid not in rig:
            f.append(F("ACTOR-DECLARED", f"actor {aid} has no characters[] rig entry with the same id (rig, hands, seam and shadow checks run per id)"))
        if not isinstance(a["depth_z"], (int, float)) or not isinstance(a["layer"], int):
            f.append(F("ACTOR-DECLARED", f"actor {aid} depth_z must be a number (metres from the camera plane, larger = farther) and layer an integer"))
        bad = [r for r in a["catalogue_refs"] if not str(r).startswith(str(a["module"]) + "/")]
        if bad:
            f.append(F("ACTOR-DECLARED", f"actor {aid} catalogue_refs {bad} are not in the {a['module']} catalogue"))
        if root is not None and not (Path(root) / "tools" / "render" / "characters" / f"{a['module']}.js").is_file():
            f.append(F("ACTOR-DECLARED", f"actor {aid} module {a['module']} has no tools/render/characters/{a['module']}.js"))
    extra = rig - set(ids)
    if extra:
        f.append(F("ACTOR-DECLARED", f"characters[] entries {sorted(extra)} are not declared in actors[]"))
    pr, nfs, fps0 = _presence(), _spec_frames(spec), float(spec.get("fps", 24))   # per-actor frame ranges (actors[].frames, [f0, f1) pairs): an actor may enter, exit or be cut between
    amap = {a.get("id"): a for a in A}
    for a in A:
        if pr.declared(a) is not None:
            for msg in pr.problems(pr.declared(a), nfs):
                f.append(F("ACTOR-RANGE", f"actor {a.get('id')} frames: {msg}"))
    zl = {a["id"]: (a.get("depth_z"), a.get("layer")) for a in A if a.get("id")}
    inter = spec.get("actor_interactions", [])
    for b in spec.get("beats", []):
        bid = b.get("id", "?"); present = _beat_actors(b, spec)
        unk = [p for p in present if p not in zl]
        if unk:
            f.append(F("ACTOR-DECLARED", f"beat {bid} names actors {unk} that are not declared")); continue
        posed = {ps.get("character") for ps in b.get("poses", [])}
        bf0, bf1 = round(float(b.get("start", 0)) * fps0), round(float(b.get("end", 0)) * fps0)
        for aid in present:   # every actor a beat shows is in the shot for the whole beat (an absent actor must be left out of beat.actors)
            a_ = amap.get(aid, {})
            if pr.declared(a_) is not None and not pr.problems(pr.declared(a_), nfs):
                gone = [k for k in range(bf0, bf1) if not pr.present_at(a_, k, nfs)]
                if gone:
                    f.append(F("ACTOR-RANGE", f"beat {bid} shows actor {aid} but its frames {pr.declared(a_)} leave out {len(gone)} frame(s) of the beat's {bf0}..{bf1} (first {gone[0]}): list only the actors present in beat.actors, or widen the range"))
        for aid in present:
            if aid not in posed:
                f.append(F("ACTOR-DECLARED", f"beat {bid} has no pose for actor {aid} (poses[].character) (R-318)"))
            if not any(s.get("caster") == aid for s in b.get("cast_shadows", [])):
                f.append(F("SHADOW-ACTOR", f"beat {bid} has no cast shadow whose caster is actor {aid}: every actor casts its own mass-proxy shadow (R-355)"))
        if len(present) < 2:
            continue
        for aid in present:   # per-actor emotion
            ae = (b.get("actor_emotions") or {}).get(aid)
            if not ae or not ae.get("emotion") or not ae.get("emotion_track"):
                f.append(F("ACTOR-EMOTION", f"beat {bid} actor {aid} has no actor_emotions[{aid}] with emotion and emotion_track: each actor feels on its own track (R-360)"))
        wins = _order_windows(b)   # draw order
        if not wins:
            f.append(F("ACTOR-ORDER", f"beat {bid} shows {present} but declares no draw_order (who is in front, back to front)"))
        else:
            z = {a: zl[a][0] for a in present}
            z.update({k: v for k, v in (b.get("depth_z") or {}).items() if k in z})
            wins = sorted(wins, key=lambda w: w[0]); cur = float(b.get("start", 0))
            for i, (t0, t1, order, why) in enumerate(wins):
                if abs(t0 - cur) > 1e-6:
                    f.append(F("ACTOR-ORDER", f"beat {bid} draw_order windows leave {cur:.3f}..{t0:.3f} s without an order"))
                cur = t1
                toks = _expand_tokens(order)
                names = [tk.split(":")[0] for tk in toks]
                if sorted(set(names)) != sorted(present) or any(toks.count(f"{a}:{p}") != 1 for a in present for p in ("body", "arms")):
                    f.append(F("ACTOR-ORDER", f"beat {bid} draw_order {order} must name every present actor {present} once (id, or id:body and id:arms)")); continue
                bodies = [tk.split(":")[0] for tk in toks if tk.endswith(":body")]
                for a, c in zip(bodies, bodies[1:]):
                    if z[a] < z[c] - ACTOR["z_eps"] or (abs(z[a] - z[c]) <= ACTOR["z_eps"] and zl[a][1] >= zl[c][1]):
                        f.append(F("ACTOR-ORDER", f"beat {bid} draws {c} over {a} but {a} is nearer (depth_z {z[a]} vs {z[c]}, layer {zl[a][1]} vs {zl[c][1]}): the order must follow depth (farther first)"))
                split = _non_contiguous(toks)
                if split and len(str(why or "")) < SPEC2["min_why_chars"]:
                    f.append(F("ACTOR-ORDER", f"beat {bid} draw_order interleaves {split} (one actor's parts on both sides of another's) with no why of >= 12 chars"))
                if i and not why and wins[i - 1][2] != order:
                    f.append(F("ACTOR-ORDER", f"beat {bid} draw_order changes at {t0:.3f} s with no why (who passes in front of whom, and what the viewer sees)"))
            if abs(cur - float(b.get("end", 0))) > 1e-6:
                f.append(F("ACTOR-ORDER", f"beat {bid} draw_order windows end at {cur:.3f} s, the beat ends at {b.get('end')} s"))
        if not any(x.get("beat") == bid for x in inter) and not b.get("actors_apart_because"):
            f.append(F("ACTOR-INTERACTION", f"beat {bid} shows {present} together but declares no actor_interactions and no actors_apart_because"))
    props = {p.get("id"): p for p in spec.get("props", [])}; fps = float(spec.get("fps", 24)); beats = {b.get("id"): b for b in spec.get("beats", [])}
    for x in inter:
        xid = x.get("id", "?"); kind = x.get("kind"); b = beats.get(x.get("beat"))
        if kind not in ("contact", "handover", "apart") or b is None or x.get("t0") is None or x.get("t1") is None:
            f.append(F("ACTOR-INTERACTION", f"interaction {xid} needs kind contact|handover|apart, an existing beat, t0 and t1")); continue
        if kind == "apart":   # a declared NO-TOUCH (CLAUDE.md, the owner 2026-10-23): the two actors' hands stay at least min_gap_px apart (proved by ACTOR-CONTACT on the trace)
            ea, eb = x.get("a") or {}, x.get("b") or {}
            if ea.get("actor") not in ids or eb.get("actor") not in ids or ea.get("actor") == eb.get("actor"):
                f.append(F("ACTOR-INTERACTION", f"apart {xid} needs two different declared actors a and b"))
            if not all(h in HANDS for h in (ea.get("hands") or [])) or not all(h in HANDS for h in (eb.get("hands") or [])) or not ea.get("hands") or not eb.get("hands"):
                f.append(F("ACTOR-INTERACTION", f"apart {xid} needs a.hands and b.hands (L, R)"))
            if not isinstance(x.get("min_gap_px"), (int, float)) or x["min_gap_px"] < 1:
                f.append(F("ACTOR-INTERACTION", f"apart {xid} needs min_gap_px >= 1"))
            if not (float(b["start"]) - 1e-9 <= float(x["t0"]) < float(x["t1"]) <= float(b["end"]) + 1e-9):
                f.append(F("ACTOR-INTERACTION", f"interaction {xid} window {x['t0']}..{x['t1']} s lies outside beat {b['id']}"))
            if len(str(x.get("why") or "")) < SPEC2["min_why_chars"]:
                f.append(F("ACTOR-INTERACTION", f"interaction {xid} needs a why of >= 12 chars (the story reason they do not touch)"))
            continue
        if not (float(b["start"]) - 1e-9 <= float(x["t0"]) < float(x["t1"]) <= float(b["end"]) + 1e-9):
            f.append(F("ACTOR-INTERACTION", f"interaction {xid} window {x['t0']}..{x['t1']} s lies outside beat {b['id']}"))
        if len(str(x.get("why") or "")) < SPEC2["min_why_chars"]:
            f.append(F("ACTOR-INTERACTION", f"interaction {xid} needs a why of >= 12 chars (the story reason for the touch)"))

        def end_ok(e, what):
            if not isinstance(e, dict) or (e.get("actor") not in ids and not e.get("prop")):
                f.append(F("ACTOR-INTERACTION", f"interaction {xid} {what} must name a declared actor (+ point) or a prop")); return False
            if e.get("actor") and e["actor"] not in _beat_actors(b, spec):
                f.append(F("ACTOR-INTERACTION", f"interaction {xid} {what} actor {e['actor']} is not in beat {b['id']}"))
            if e.get("prop") and e["prop"] not in props:
                f.append(F("ACTOR-INTERACTION", f"interaction {xid} {what} prop {e['prop']} is not in props[]"))
            return True
        if kind == "contact":
            if end_ok(x.get("a"), "a") and end_ok(x.get("b"), "b"):
                if not x["a"].get("actor") or not x["a"].get("point"):
                    f.append(F("ACTOR-INTERACTION", f"interaction {xid} a needs actor and point (hand_L, hand_R, ...)"))
                if x["b"].get("prop") and not (x["b"].get("held_by") or {}).get("actor"):
                    f.append(F("ACTOR-INTERACTION", f"interaction {xid} b is a prop: name the hand that holds it (held_by {{actor, hand}}), a hand to an object held by the other"))
                if x["b"].get("actor") and not x["b"].get("point"):
                    f.append(F("ACTOR-INTERACTION", f"interaction {xid} b needs a point (hand_L, hand_R, ...)"))
                if x["b"].get("actor") and x["b"].get("actor") == x["a"].get("actor"):
                    f.append(F("ACTOR-INTERACTION", f"interaction {xid} touches an actor with itself"))
            if float(x.get("tol_px", ACTOR["contact_tol_px"])) > 2 * ACTOR["contact_tol_px"]:
                f.append(F("ACTOR-INTERACTION", f"interaction {xid} tol_px {x.get('tol_px')} > {2 * ACTOR['contact_tol_px']:.0f} (a wider tolerance is not a contact)"))
        else:
            g, r = x.get("giver") or {}, x.get("receiver") or {}
            if x.get("prop") not in props:
                f.append(F("ACTOR-INTERACTION", f"handover {xid} prop {x.get('prop')!r} is not in props[]"))
            for who, e in (("giver", g), ("receiver", r)):
                if e.get("actor") not in ids or e.get("hand") not in HANDS:
                    f.append(F("ACTOR-INTERACTION", f"handover {xid} {who} needs a declared actor and hand L|R"))
            if g.get("actor") == r.get("actor"):
                f.append(F("ACTOR-INTERACTION", f"handover {xid} giver and receiver are the same actor"))
            hf = x.get("handoff_frame"); a0, a1 = round(float(x["t0"]) * fps), round(float(x["t1"]) * fps)
            if not isinstance(hf, int) or not a0 < hf < a1:
                f.append(F("ACTOR-INTERACTION", f"handover {xid} handoff_frame {hf!r} must be an integer frame strictly inside {a0}..{a1}"))
            n = x.get("both_hands_frames", ACTOR["handover_both_frames"])
            if not isinstance(n, int) or n < ACTOR["handover_both_frames"]:
                f.append(F("ACTOR-INTERACTION", f"handover {xid} both_hands_frames = {n!r} (need an integer >= {ACTOR['handover_both_frames']}: both hands on the prop before it changes hands)"))
            elif isinstance(hf, int) and hf - n < a0:
                f.append(F("ACTOR-INTERACTION", f"handover {xid} window starts {hf - a0} frames before the hand-off, both_hands_frames needs {n}"))
    return f

# ---- trace side
def _sframes(trace: dict) -> dict:
    return {fr["f"]: fr for fr in (trace.get("scene") or {}).get("frames", [])}

def _point(trace: dict, actor: str, name: str, f: int):
    ch = (trace.get("characters") or {}).get(actor) or {}
    fr = next((x for x in ch.get("frames", []) if x.get("f") == f), None)
    if fr is None:
        return None
    p = (fr.get("contact_points") or {}).get(name)
    return p if p is not None else (fr.get("anchors") or {}).get(name)

def _frame_of(trace: dict, actor: str, f: int):
    return next((x for x in ((trace.get("characters") or {}).get(actor) or {}).get("frames", []) if x.get("f") == f), None)

def _poly_gap(a, b) -> float:
    """Smallest distance between two polygons (0 when they overlap): vertex-to-edge both ways, and a vertex inside the other."""
    def inside(p, poly):
        c = False
        for i in range(len(poly)):
            x1, y1 = poly[i]; x2, y2 = poly[i - 1]
            if (y1 > p[1]) != (y2 > p[1]) and p[0] < (x2 - x1) * (p[1] - y1) / ((y2 - y1) or 1e-12) + x1:
                c = not c
        return c
    def seg(p, q, r):
        dx, dy = r[0] - q[0], r[1] - q[1]; L2 = dx * dx + dy * dy or 1e-12; t = max(0.0, min(1.0, ((p[0] - q[0]) * dx + (p[1] - q[1]) * dy) / L2))
        return math.hypot(p[0] - q[0] - t * dx, p[1] - q[1] - t * dy)
    if any(inside(p, b) for p in a) or any(inside(p, a) for p in b):
        return 0.0
    if not a or not b:
        return 1e9
    return min(min(min(seg(p, b[i - 1], b[i]) for i in range(len(b))) for p in a), min(min(seg(p, a[i - 1], a[i]) for i in range(len(a))) for p in b))

def _prop_at(sf, pid: str):
    return next((p for p in (sf or {}).get("props", []) if p.get("id") == pid), None)

def _parent_key(par):
    return (par.get("actor"), par.get("hand")) if isinstance(par, dict) else None

def rig_actors(trace: dict, spec: dict | None) -> list[str]:
    """ACTOR-TRACE, ACTOR-OCCLUSION, ACTOR-CONTACT, HANDOVER. Runs when the trace has a scene block, more than one character, or the spec declares 2+ actors."""
    chars = trace.get("characters") or {}; sc = trace.get("scene") or {}; ids = _actor_ids(spec)
    if not (sc or len(chars) > 1 or len(ids) > 1):
        return []
    if not sc.get("frames"):
        return [F("ACTOR-TRACE", f"trace has {len(chars)} characters but no scene.frames: the renderer must export the draw order, depths and props per frame (rig-trace.schema.json)")]
    f: list[str] = []; fps = float(trace.get("fps", 24))
    if ids and sorted(ids) != sorted(chars):
        f.append(F("ACTOR-TRACE", f"trace characters {sorted(chars)} differ from the spec's actors {sorted(ids)}"))
    sfr = _sframes(trace)
    for cid, ch in chars.items():
        fs = {x["f"] for x in ch.get("frames", [])}; sp = {k for k, v in sfr.items() if cid in (v.get("present") or [])}
        if fs != sp:
            f.append(F("ACTOR-TRACE", f"actor {cid} has {len(fs)} frames but scene.frames lists it present on {len(sp)} frames")); break
    pr = _presence(); sp_actors = {a.get("id"): a for a in ((spec or {}).get("actors") or [])}; nfs = (max(sfr) + 1) if sfr else 0
    for cid, ch in chars.items():   # declared frame ranges (spec actors[].frames) vs the frames the trace has for the actor
        a = sp_actors.get(cid)
        if a is not None and pr.declared(a) is not None and not pr.problems(pr.declared(a), nfs):
            want = set(pr.frames(a, nfs)); fs = {x["f"] for x in ch.get("frames", [])}
            if fs != want:
                f.append(F("ACTOR-RANGE", f"actor {cid} is traced on {len(fs)} frames, its declared frames {pr.declared(a)} are {len(want)} (missing {sorted(want - fs)[:4]}, extra {sorted(fs - want)[:4]})"))
    zlayer = {a.get("id"): a.get("layer", 0) for a in (sc.get("actors") or [])}
    n_bad = 0; msgs: list[str] = []
    for k in sorted(sfr):
        fr = sfr[k]; toks = fr.get("draw_order") or []; present = fr.get("present") or []; t = float(fr.get("t", k / fps)); why = None
        if not toks:
            why = "has no draw_order: nothing says who was drawn in front"
        else:
            names = [tk.split(":")[0] for tk in toks]; dep = fr.get("depth") or {}
            if sorted(set(names)) != sorted(present) or any(toks.count(f"{a}:{p}") != 1 for a in present for p in ("body", "arms")):
                why = f"draws {toks} for actors present {present}: each present actor is drawn once (body, arms), nobody else"
            elif any(a not in dep for a in present):
                why = f"has no depth for {[a for a in present if a not in dep]}"
            else:
                bodies = [tk.split(":")[0] for tk in toks if tk.endswith(":body")]
                for a, c in zip(bodies, bodies[1:]):
                    if dep[a] < dep[c] - ACTOR["z_eps"] or (abs(dep[a] - dep[c]) <= ACTOR["z_eps"] and zlayer.get(a, 0) >= zlayer.get(c, 0)):
                        why = f"{c} is drawn over {a} but {a} is nearer (depth {dep[a]} vs {dep[c]}): a character drawn through another"; break
                if why is None:
                    want = _declared_order(spec, t) if spec and spec.get("beats") else None
                    if want is not None:
                        exp = [tk for tk in _expand_tokens(want) if tk.split(":")[0] in present]
                        if exp != toks:
                            why = f"draw order {toks} differs from the declared {exp}"
                    elif _non_contiguous(toks):
                        why = f"interleaves {_non_contiguous(toks)} with no declared draw_order for this time: one actor's parts drawn on both sides of another's"
        if why:
            n_bad += 1
            if n_bad <= 4:
                msgs.append(F("ACTOR-OCCLUSION", f"frame {k} {why}"))
    f += msgs
    if n_bad > 4:
        f.append(F("ACTOR-OCCLUSION", f"... {n_bad - 4} more frames with a draw-order fault"))
    for x in (spec or {}).get("actor_interactions", []):
        xid = x.get("id", "?"); f0, f1 = round(float(x["t0"]) * fps), round(float(x["t1"]) * fps)
        if x.get("kind") == "contact":
            a, b = x["a"], x["b"]; tol = float(x.get("tol_px", ACTOR["contact_tol_px"])); worst, bad_n, first, nodata = 0.0, 0, None, None
            for k in range(f0, f1):
                pa = _point(trace, a["actor"], a["point"], k); pb = None
                if b.get("prop"):
                    pr = _prop_at(sfr.get(k), b["prop"])
                    if pr is not None:
                        hb = b.get("held_by") or {}
                        if _parent_key(pr.get("parent")) != (hb.get("actor"), hb.get("hand")):
                            f.append(F("ACTOR-CONTACT", f"{xid} frame {k} prop {b['prop']} is parented to {_parent_key(pr.get('parent'))}, the contact needs it held by {(hb.get('actor'), hb.get('hand'))}")); nodata = False; break
                        pts = pr.get("touch") or [pr.get("pos")]
                        pb = min(pts, key=lambda q: _dist(pa, q)) if pa is not None else None
                else:
                    pb = _point(trace, b["actor"], b["point"], k)
                if pa is None or pb is None:
                    nodata = k; break
                d = _dist(pa, pb); worst = max(worst, d)
                if d > tol:
                    bad_n += 1; first = first if first is not None else (k, d)
            if nodata is not None and nodata is not False:
                f.append(F("ACTOR-CONTACT", f"{xid} frame {nodata} has no data for the contact points (no data fails)"))
            if first:
                f.append(F("ACTOR-CONTACT", f"{xid} {bad_n} of {f1 - f0} frames miss by more than {tol:.0f} px (first frame {first[0]}: {first[1]:.1f} px, worst {worst:.1f} px)"))
        elif x.get("kind") == "apart":   # no-touch proof: the drawn hand outlines (trace hand_outline_px, canvas px) of the two actors never come closer than min_gap_px
            gap_min = float(x.get("min_gap_px", 1)); A, Bx = x["a"], x["b"]; worst, first, nd, bad_n = 1e9, None, None, 0
            both = 0
            for k in range(f0, f1):
                pa = _frame_of(trace, A["actor"], k); pb = _frame_of(trace, Bx["actor"], k)
                if pa is None or pb is None:   # an actor not in the frame (not present) has no hand to touch with
                    continue
                both += 1
                oa, ob = (pa or {}).get("hand_outline_px") or {}, (pb or {}).get("hand_outline_px") or {}
                for ha in A["hands"]:
                    for hb in Bx["hands"]:
                        if not oa.get(ha) or not ob.get(hb):
                            nd = nd if nd is not None else (k, ha, hb); continue
                        d = _poly_gap(oa[ha], ob[hb]); worst = min(worst, d)
                        if d < gap_min:
                            bad_n += 1; first = first or (k, ha, hb, d)
            if not both:
                f.append(F("ACTOR-CONTACT", f"{xid} has no frame with both {A['actor']} and {Bx['actor']} present in {f0}..{f1} (no data fails)"))
            if nd is not None:
                f.append(F("ACTOR-CONTACT", f"{xid} frame {nd[0]} has no hand outline for {A['actor']} {nd[1]} / {Bx['actor']} {nd[2]} (no data fails)"))
            if first:
                f.append(F("ACTOR-CONTACT", f"{xid} {A['actor']} hand {first[1]} and {Bx['actor']} hand {first[2]} come within {first[3]:.1f} px on frame {first[0]} (min {gap_min:.0f} px; {bad_n} hand pairs too close): a touch the spec says must not happen"))
        elif x.get("kind") == "handover":
            H, pid = x["handoff_frame"], x["prop"]; n = int(x.get("both_hands_frames", ACTOR["handover_both_frames"]))
            gk, rk = (x["giver"]["actor"], x["giver"]["hand"]), (x["receiver"]["actor"], x["receiver"]["hand"])
            ps = {k: _prop_at(sfr.get(k), pid) for k in range(f0, f1)}
            miss = [k for k, p in ps.items() if p is None]
            if miss:
                f.append(F("HANDOVER", f"{xid} prop {pid} is not in scene.props on frames {miss[:4]} (no data fails)")); continue
            wrong = [(k, _parent_key(p.get("parent"))) for k, p in ps.items() if _parent_key(p.get("parent")) != (gk if k < H else rk)]
            if wrong:
                k, par = wrong[0]
                f.append(F("HANDOVER", f"{xid} prop {pid} parent is {par} on frame {k}; it must be the giver {gk} before frame {H} and the receiver {rk} from frame {H} on ({len(wrong)} frames wrong)"))
            both = []
            for k in range(H - n, H):
                hs = {(h.get("actor"), h.get("hand")): h.get("gap_px", 1e9) for h in (ps.get(k) or {}).get("hands", [])}
                if not (hs.get(gk, 1e9) <= ACTOR["handover_gap_px"] and hs.get(rk, 1e9) <= ACTOR["handover_gap_px"]):
                    both.append(k)
            if both:
                f.append(F("HANDOVER", f"{xid} both hands are not on {pid} (gap <= {ACTOR['handover_gap_px']:.0f} px) on frames {both} of the {n} before the hand-off at {H}"))
            p0, p1 = ps.get(H - 1), ps.get(H)
            if p0 and p1:
                jump = _dist(p0["pos"], p1["pos"]); lim = float(x.get("max_jump_px", ACTOR["handover_jump_px"]))
                if jump > lim:
                    f.append(F("HANDOVER", f"{xid} prop {pid} jumps {jump:.1f} px at the hand-off frame {H} (max {lim:.0f}): it teleports between the hands"))
    return f

# ------------------------------------------------------------------ RENDER extras (frames as numpy arrays)
def rel_luminance(rgb):
    import numpy as np
    c = np.asarray(rgb, float) / 255.0
    c = np.where(c <= 0.03928, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * c[..., 0] + 0.7152 * c[..., 1] + 0.0722 * c[..., 2]

def wcag(l1: float, l2: float) -> float:
    a, b = max(l1, l2), min(l1, l2)
    return (a + 0.05) / (b + 0.05)

def _otsu_split(lum):
    import numpy as np
    v = lum.ravel(); lo, hi = float(v.min()), float(v.max())
    if hi - lo < 1e-6:
        return np.zeros_like(lum, bool)
    best, bt = -1, lo
    for t in np.linspace(lo, hi, 33)[1:-1]:
        a, b = v[v <= t], v[v > t]
        if len(a) == 0 or len(b) == 0:
            continue
        s = len(a) * len(b) * (a.mean() - b.mean()) ** 2
        if s > best:
            best, bt = s, t
    return lum > bt

def text_box_metrics(frame_rgb, box, height_px, scale, mask=None):
    """-> (contrast, texture_std, minority_share, used_mask). box in 1080x1920 px; frame is scaled by `scale`.
    With a 1-bit glyph mask (same size as the frame) the contrast is glyph vs ring; without, a two-mode fallback."""
    import numpy as np
    x, y, w, h = (int(round(box[k] * scale)) for k in ("x", "y", "w", "h"))
    ring = max(int(round(6 * scale)), 1); pad = int(round(0.5 * height_px * scale))
    H, W = frame_rgb.shape[:2]
    x0, y0, x1, y1 = max(x - ring, 0), max(y - ring, 0), min(x + w + ring, W), min(y + h + ring, H)
    lum = rel_luminance(frame_rgb)
    luma255 = (0.2126 * frame_rgb[..., 0] + 0.7152 * frame_rgb[..., 1] + 0.0722 * frame_rgb[..., 2]).astype(float)
    kx0, ky0, kx1, ky1 = max(x - pad, 0), max(y - pad, 0), min(x + w + pad, W), min(y + h + pad, H)
    if mask is not None:
        g = mask[ky0:ky1, kx0:kx1].astype(bool)
        region = luma255[ky0:ky1, kx0:kx1]
        bg = region[~g]
        texture = float(bg.std()) if bg.size else 0.0
        gl = lum[ky0:ky1, kx0:kx1]
        ringmask = np.zeros(lum.shape, bool); ringmask[y0:y1, x0:x1] = True; ringmask[y:y + h, x:x + w] = False
        if mask[y:y + h, x:x + w].any() and ringmask.any():
            c = wcag(float(lum[mask.astype(bool)].mean()), float(lum[ringmask & ~mask.astype(bool)].mean()))
        else:
            c = 1.0
        return c, texture, float(g.mean()) if g.size else 0.0, True
    sub = lum[y:y + h, x:x + w]
    if sub.size == 0:
        return 1.0, 0.0, 0.0, False
    cls = _otsu_split(sub); share = min(float(cls.mean()), 1 - float(cls.mean()))
    if share == 0:
        return 1.0, float(luma255[y:y + h, x:x + w].std()), 0.0, False
    minority = cls if cls.mean() < 0.5 else ~cls
    c = wcag(float(sub[minority].mean()), float(sub[~minority].mean()))
    r = luma255[y:y + h, x:x + w]
    return c, float(r[~minority].std()), share, False

def check_text_render(samples: list[dict], height_px: float, label: str) -> list[str]:
    """samples: [{'contrast','texture','share','mask'}] one per visible frame."""
    f = []
    if not samples:
        return [F("REND-TEXT-CONTRAST", f"text {label} has no visible frames to measure")]
    import numpy as np
    cs = [s["contrast"] for s in samples]; p10 = float(np.percentile(cs, 10))
    need = RENDER2["text_contrast_large"] if height_px >= 48 else RENDER2["text_contrast_p10"]
    note = "" if samples[0].get("mask") else " [fallback two-mode estimate, weaker than a text mask]"
    if p10 < need:
        f.append(F("REND-TEXT-CONTRAST", f"text {label} contrast p10 = {p10:.2f}:1 (need >= {need}:1){note} (R-336)"))
    tx = max(s["texture"] for s in samples)
    if tx > RENDER2["text_texture_max"]:
        f.append(F("REND-TEXT-TEXTURE", f"text {label} texture std in the knockout region = {tx:.1f}/255 (need <= 6): halftone/grain under the text (R-335)"))
    return f

def colour_stats(frames_rgb) -> dict:
    """Mean hue (deg, circular, saturation weighted), saturation, value and relative luma (0..1) over frames."""
    import numpy as np
    hs, ss, vs, ls = [], [], [], []
    for fr in frames_rgb:
        a = np.asarray(fr, float) / 255.0
        mx = a.max(-1); mn = a.min(-1); d = mx - mn
        s = np.where(mx > 0, d / np.maximum(mx, 1e-9), 0)
        r, g, b = a[..., 0], a[..., 1], a[..., 2]
        h = np.zeros_like(mx)
        m = d > 1e-9
        h = np.where(m & (mx == r), ((g - b) / np.maximum(d, 1e-9)) % 6, h)
        h = np.where(m & (mx == g), (b - r) / np.maximum(d, 1e-9) + 2, h)
        h = np.where(m & (mx == b), (r - g) / np.maximum(d, 1e-9) + 4, h)
        h = h * 60.0
        w = s
        if w.sum() > 1e-9:
            hs.append(math.degrees(math.atan2((np.sin(np.radians(h)) * w).sum(), (np.cos(np.radians(h)) * w).sum())) % 360)
        else:
            hs.append(0.0)
        ss.append(float(s.mean())); vs.append(float(mx.mean())); ls.append(float(rel_luminance(fr).mean()))
    cx = sum(math.cos(math.radians(h)) for h in hs); sx = sum(math.sin(math.radians(h)) for h in hs)
    return {"hue": math.degrees(math.atan2(sx, cx)) % 360 if hs else 0.0, "sat": float(sum(ss) / max(len(ss), 1)),
            "val": float(sum(vs) / max(len(vs), 1)), "luma": float(sum(ls) / max(len(ls), 1))}

def _hdiff(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)

def check_colour_script(stats: list[dict], spec: dict) -> list[str]:
    """stats: one dict per beat in order {'hue','sat','val','luma'}. R-370: change between differing emotions and match to declared target."""
    f = []; beats = spec.get("beats", [])
    for i, b in enumerate(beats):
        tgt = ((b.get("emotion_track") or {}).get("colour") or {}).get("target")
        if tgt and i < len(stats):
            s = stats[i]
            if "hue_deg" in tgt and _hdiff(s["hue"], tgt["hue_deg"]) > RENDER2["colour_target_hue"]:
                f.append(F("REND-COLOUR", f"beat {b['id']} measured hue {s['hue']:.0f} vs declared {tgt['hue_deg']} (tol 30) (R-370)"))
            if "sat" in tgt and abs(s["sat"] - tgt["sat"]) > RENDER2["colour_target_sv"]:
                f.append(F("REND-COLOUR", f"beat {b['id']} measured saturation {s['sat']:.2f} vs declared {tgt['sat']} (tol 0.2) (R-370)"))
            if "value" in tgt and abs(s["val"] - tgt["value"]) > RENDER2["colour_target_sv"]:
                f.append(F("REND-COLOUR", f"beat {b['id']} measured value {s['val']:.2f} vs declared {tgt['value']} (tol 0.2) (R-370)"))
        if i > 0 and i < len(stats):
            pe = (beats[i - 1].get("emotion") or {}).get("primary"); ce = (b.get("emotion") or {}).get("primary")
            if pe and ce and pe != ce:
                a, c = stats[i - 1], stats[i]
                rel = lambda x, y: abs(x - y) / max(x, y, 1e-9)
                if not (_hdiff(a["hue"], c["hue"]) >= RENDER2["colour_hue_deg"] or rel(a["sat"], c["sat"]) >= RENDER2["colour_rel"]
                        or rel(a["luma"], c["luma"]) >= RENDER2["colour_rel"]):
                    f.append(F("REND-COLOUR", f"beats {beats[i - 1]['id']}->{b['id']} change emotion {pe}->{ce} but the measured colour barely moves (hue {_hdiff(a['hue'], c['hue']):.0f} deg, sat {rel(a['sat'], c['sat']):.0%}, luma {rel(a['luma'], c['luma']):.0%}) (R-370)"))
    return f

# ---------------------------------------------------------------- 2D look (R-380, the owner 2026-10-23: "2D, not 3D")
# Measured on 540x960 luma frames sampled at 2 fps. Calibrated on Mix v2 (liked, closer to 2D) vs Mix v3 (went 3D).
LOOK2D = {"min_hard_edge": 0.08,   # share of pixels on a hard step (luma step >= 0.10 per px): ink line + cel edges
          "max_ramp_area": 0.03,   # share of 24 px blocks that vary by >= 0.10 luma with no hard step inside: smooth volume ramps
          "block": 24, "hard_step": 0.10, "ramp_range": 0.10, "ramp_edge_max": 0.06}

def look2d_frame(lum) -> dict:
    """lum: (h,w) float luma 0..1. Returns hard_edge and ramp_area shares for one frame."""
    import numpy as np
    L = np.asarray(lum, np.float32)
    g = np.zeros_like(L)
    g[:-1, :-1] = np.maximum(np.abs(np.diff(L, axis=1))[:-1, :], np.abs(np.diff(L, axis=0))[:, :-1])
    B = LOOK2D["block"]; H = L.shape[0] // B; W = L.shape[1] // B
    if H == 0 or W == 0:
        return {"hard_edge": float((g >= LOOK2D["hard_step"]).mean()), "ramp_area": 0.0}
    bl = L[:H * B, :W * B].reshape(H, B, W, B).transpose(0, 2, 1, 3).reshape(H, W, B * B)
    bg = g[:H * B, :W * B].reshape(H, B, W, B).transpose(0, 2, 1, 3).reshape(H, W, B * B)
    ramp = ((bl.max(-1) - bl.min(-1)) >= LOOK2D["ramp_range"]) & (bg.max(-1) < LOOK2D["ramp_edge_max"])
    return {"hard_edge": float((g >= LOOK2D["hard_step"]).mean()), "ramp_area": float(ramp.mean())}

def look2d_metrics(frames_lum) -> dict:
    ms = [look2d_frame(f) for f in frames_lum]
    if not ms:
        return {"hard_edge": 0.0, "ramp_area": 0.0, "frames": 0}
    return {"hard_edge": sum(m["hard_edge"] for m in ms) / len(ms), "ramp_area": sum(m["ramp_area"] for m in ms) / len(ms), "frames": len(ms)}

def check_look2d(m: dict) -> list[str]:
    f = []
    if m["hard_edge"] < LOOK2D["min_hard_edge"]:
        f.append(F("LOOK2D-LINE", f"hard-edge share {m['hard_edge']:.3f} < {LOOK2D['min_hard_edge']}: ink line and cel edges lost or replaced by soft shading (R-380)"))
    if m["ramp_area"] > LOOK2D["max_ramp_area"]:
        f.append(F("LOOK2D-RAMP", f"smooth-ramp area {m['ramp_area']:.3f} > {LOOK2D['max_ramp_area']}: lit-volume gradients instead of flat or 2-3 step cel tone (R-380)"))
    return f

def check_shadow_flat(spec: dict) -> list[str]:
    """R-380: the mass proxy shapes the shadow; the shadow is drawn as a flat shape. Fails only when a spec asks for a soft edge."""
    f = []
    for b in spec.get("beats", []):
        for s in b.get("cast_shadows", []):
            if str(s.get("edge", "hard")).lower() in ("soft", "blur", "gaussian") or float(s.get("blur_px") or 0) > 2:
                f.append(F("SHADOW-FLAT", f"beat {b.get('id','?')} shadow of {s.get('caster')} has a soft/blurred edge: draw it as a flat 2D shape (edge 'hard' or 'cel') (R-380)"))
    return f


# ---------------------------------------------------------------- SEAM (R-381, the owner F11): one connected silhouette
# DEFAULT, uncalibrated: no approved line-art mask exists yet. Calibrate on the first hand-approved render (gate-spec K).
SEAM = {"r_heads": 0.12,        # joint disc radius as a share of head_unit_px (a seam may give r_px)
        "r_px_fallback": 14.0,  # disc radius when neither r_px nor head_unit_px is known
        "cross_frac": 0.6,      # a stroke crosses when its extent perpendicular to the bone >= this share of the disc diameter
        "head_neck_cross_frac": 0.45,   # stricter for head-neck (the head must join through a neck or garment)
        "max_along_ratio": 0.6, # ...and its extent along the bone is <= this share of the perpendicular extent (not a limb outline)
        "ink_level": 127}       # mask pixel value above which a pixel is ink (alpha or luma)

def _unit(v):
    n = math.hypot(v[0], v[1])
    return (v[0] / n, v[1] / n) if n > 1e-9 else None

def seam_axis(seam: dict):
    if seam.get("axis"):
        return _unit(seam["axis"])
    if seam.get("from") and seam.get("to"):
        return _unit((seam["to"][0] - seam["from"][0], seam["to"][1] - seam["from"][1]))
    return None

def crossing_strokes(ink, centre, radius, axis, cross_frac, max_along=SEAM["max_along_ratio"]) -> list[dict]:
    """ink: 2-D bool array in mask pixels. Returns the ink strokes inside the disc (centre, radius) that run across the bone
    axis: perpendicular extent >= cross_frac * diameter and along-axis extent <= max_along * perpendicular extent."""
    import numpy as np
    from scipy import ndimage as ndi
    h, w = ink.shape
    cx, cy = centre
    x0, x1 = max(int(math.floor(cx - radius)), 0), min(int(math.ceil(cx + radius)) + 1, w)
    y0, y1 = max(int(math.floor(cy - radius)), 0), min(int(math.ceil(cy + radius)) + 1, h)
    if x1 <= x0 or y1 <= y0:
        return []
    yy, xx = np.mgrid[y0:y1, x0:x1]
    sub = ink[y0:y1, x0:x1] & (((xx - cx) ** 2 + (yy - cy) ** 2) <= radius * radius)
    lab, n = ndi.label(sub, structure=np.ones((3, 3)))
    ax, ay = axis
    out = []
    for i in range(1, n + 1):
        m = lab == i
        dx, dy = xx[m] - cx, yy[m] - cy
        along = dx * ax + dy * ay
        perp = -dx * ay + dy * ax
        pe, ae = float(perp.max() - perp.min() + 1), float(along.max() - along.min() + 1)
        if pe >= cross_frac * 2 * radius and ae <= max_along * pe:
            out.append({"perp_px": round(pe, 1), "along_px": round(ae, 1), "pixels": int(m.sum())})
    return out

def _declared_overlap(seam: dict, overlaps) -> bool:
    ids = {str(o) for o in (overlaps or [])}
    a, b = (seam.get("parts") or ["", ""])[:2]
    return seam.get("id") in ids or f"{a}|{b}" in ids or f"{b}|{a}" in ids

def seam_frame_issues(ink, scale: float, seams: list, overlaps, head_unit_px, label: str) -> list[str]:
    """One frame: SEAM-CROSS for body seams, SEAM-HEADNECK for the head join. scale = mask px per canvas px."""
    f = []
    for s in seams or []:
        axis = seam_axis(s)
        if axis is None or not s.get("at"):
            continue                                   # no bone direction: cannot tell a seam line from a limb outline
        kind = s.get("kind", "joint")
        r = float(s.get("r_px") or (SEAM["r_heads"] * head_unit_px if head_unit_px else SEAM["r_px_fallback"]))
        centre = (s["at"][0] * scale, s["at"][1] * scale)
        name = s.get("id") or "|".join(s.get("parts", []))
        if kind == "head-neck":
            if not s.get("via"):
                f.append(F("SEAM-HEADNECK", f"{label} seam {name}: no neck shape or garment declared in 'via'; a round head must not sit on the body with an outline between (R-381, F11)"))
            hits = crossing_strokes(ink, centre, r * scale, axis, SEAM["head_neck_cross_frac"])
            if hits:   # overlaps[] cannot waive the head-neck join
                f.append(F("SEAM-HEADNECK", f"{label} seam {name}: an outline of {hits[0]['perp_px']} px cuts the head-to-neck join; the head must connect through the neck or garment shape (R-381, F11)"))
            continue
        if _declared_overlap(s, overlaps):
            continue
        hits = crossing_strokes(ink, centre, r * scale, axis, SEAM["cross_frac"])
        if hits:
            f.append(F("SEAM-CROSS", f"{label} seam {name}: {len(hits)} stroke(s) ({hits[0]['perp_px']} px wide across the joint) cut the silhouette and no overlap/fold is declared here (R-381, F11)"))
    return f

def rig_seams(trace: dict, base: Path | None = None, max_report: int = 6) -> list[str]:
    """Needs per frame: line_mask (PNG, ink strokes only, canvas-aligned), seams[], optional overlaps[]. Frames without them are skipped;
    a trace that declares seams but yields no readable mask fails SEAM-NODATA."""
    try:
        from PIL import Image
        import numpy as np
    except ImportError:
        return [F("SEAM-NODATA", "numpy/PIL missing")]
    cw = float((trace.get("canvas") or {}).get("w") or 1080)
    f, seen, read = [], 0, 0
    for cid, ch in trace.get("characters", {}).items():
        for fr in _frames(ch):
            if not fr.get("seams"):
                continue
            seen += 1
            p = fr.get("line_mask")
            pp = (Path(p) if Path(p).is_absolute() or base is None else Path(base) / p) if p else None
            if pp is None or not pp.exists():
                continue
            im = Image.open(pp)
            alpha = np.asarray(im.getchannel("A")) if im.mode in ("RGBA", "LA") else None
            a = alpha if alpha is not None and alpha.min() < 255 else np.asarray(im.convert("L"))
            read += 1
            f += seam_frame_issues(a > SEAM["ink_level"], im.size[0] / cw, fr["seams"], fr.get("overlaps"),
                                   ch.get("head_unit_px"), f"{cid} frame {fr['f']}")
    if seen and not read:
        f.append(F("SEAM-NODATA", f"{seen} frames declare seams but no line_mask PNG could be read: the renderer must export the line-art mask (R-381)"))
    if len(f) > max_report:
        f = f[:max_report] + [F("SEAM-CROSS", f"... {len(f) - max_report} more seam faults")]
    return f

# ---------------------------------------------------------------- PLAYBACK (R-382, rca-playback.md): previews play the gated video
PLAYBACK = {"p99_ms": 50.0, "long_task_ms": 100.0, "loops": 2}   # DEFAULT, from rca-playback.md (not calibrated on a real preview)

from html.parser import HTMLParser

_VOID = {"br", "img", "input", "meta", "link", "source", "hr", "canvas", "video", "iframe", "area", "col", "embed", "wbr"}

class _PanelScan(HTMLParser):
    """Collects, per section.panel, its canvases, videos and iframes, plus every inline script of the page."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.panels, self.scripts = [], []
        self._cur, self._depth, self._buf, self._in_script, self._details = None, 0, [], False, []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "script" and not a.get("src"):
            self._in_script, self._buf = True, []
        if tag == "section" and "panel" in (a.get("class") or "").split():
            self._cur = {"id": a.get("data-tab") or a.get("id") or f"panel{len(self.panels)}", "canvases": [], "videos": [], "iframes": []}
            self._depth = 0
            self.panels.append(self._cur)
        if tag == "details":
            self._details.append("open" in a)
        if self._cur is None:
            return
        if tag not in _VOID:
            self._depth += 1
        # a canvas is a live opt-in when it is hidden, inside a closed <details>, or marked data-live
        optin = (not all(self._details)) or "hidden" in a or a.get("data-live") is not None
        if tag == "canvas":
            self._cur["canvases"].append({"id": a.get("id", ""), "optin": optin})
        elif tag == "video":
            self._cur["videos"].append({"src": a.get("src") or "", "hidden": "hidden" in a})
        elif tag == "source" and self._cur["videos"] and not self._cur["videos"][-1]["src"]:
            self._cur["videos"][-1]["src"] = a.get("src", "")
        elif tag == "iframe":
            self._cur["iframes"].append(a.get("data-src") or a.get("src") or "")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag == "script":
            self.scripts.append("".join(self._buf)); self._in_script = False
        if tag == "details" and self._details:
            self._details.pop()
        if self._cur is not None and tag not in _VOID:
            self._depth -= 1
            if self._depth <= 0:
                self._cur = None

    def handle_data(self, d):
        if self._in_script:
            self._buf.append(d)

def _autoplays(canvas_id: str, scripts: list) -> bool:
    """True when a script that names this canvas also runs an animation loop (rAF / setInterval / renderAt)."""
    for s in scripts:
        touches = bool(canvas_id) and re.search(r"""['"]#?%s['"]""" % re.escape(canvas_id), s) is not None
        if touches and re.search(r"requestAnimationFrame|setInterval\s*\(|renderAt\s*\(", s):
            return True
    return False

PREVIEW_MAX_TABS = 4

def check_preview_static(html: str, label: str = "preview") -> list[str]:
    """PLAYBACK-VIDEO: every tab that has a canvas renderer must also play a recorded <video src=...> (default view).
    PLAYBACK-AUTOPLAY: no canvas that is visible by default may be driven by an animation loop. Hidden, closed-<details>
    and data-live canvases are opt-in editors and are allowed."""
    sc = _PanelScan(); sc.feed(html); sc.close()
    f = []
    for p in sc.panels:
        if not p["canvases"]:
            continue
        if not [v for v in p["videos"] if v["src"] and not v["hidden"]]:
            f.append(F("PLAYBACK-VIDEO", f"{label} tab '{p['id']}' paints a canvas but plays no recorded <video src=...>; the preview must be the gated render (R-382)"))
        for c in p["canvases"]:
            if not c["optin"] and _autoplays(c["id"], sc.scripts):
                f.append(F("PLAYBACK-AUTOPLAY", f"{label} tab '{p['id']}' canvas #{c['id'] or '?'} is a live per-frame painter shown by default (rAF/setInterval/renderAt); put it behind data-live or a closed <details> and show the video (R-382)"))
    n = max(len(re.findall(r'\{\s*id:\s*"', (re.search(r"const TABS\s*=\s*\[(.*?)\];", html, re.S) or [0, ""])[1] if re.search(r"const TABS\s*=\s*\[(.*?)\];", html, re.S) else "")), len(sc.panels))
    if n > PREVIEW_MAX_TABS:
        f.append(F("PREVIEW-MAX-TABS", f"{label} has {n} tabs; at most {PREVIEW_MAX_TABS} (CLAUDE.md): move older tabs to previews/archive/index-<date>.html"))
    return f

_DYN_JS = """async (loops) => {
  const out = {frames: [], long: [], errors: []};
  window.addEventListener('error', e => out.errors.push(String(e.message)));
  try { new PerformanceObserver(l => l.getEntries().forEach(e => out.long.push(e.duration))).observe({entryTypes: ['longtask']}); } catch (e) {}
  const v = document.querySelector('video'); if (v) { v.muted = true; try { await v.play(); } catch (e) {} }
  const dur = v && isFinite(v.duration) ? v.duration * 1000 * loops : 9000 * loops;
  let last = performance.now(); const t0 = last;
  await new Promise(res => { const step = now => { out.frames.push(now - last); last = now; now - t0 < dur ? requestAnimationFrame(step) : res(); }; requestAnimationFrame(step); });
  return out; }"""

def check_preview_dynamic(url: str, loops: int = PLAYBACK["loops"]) -> list[str]:
    """Optional (--dynamic): cold load, two loops, foreground window. p99 frame <= 50 ms, no long task > 100 ms, no exception.
    Needs Playwright plus a browser; headless rAF is throttled, so it opens a real window. Not run in the test suite."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError("playwright not installed: dynamic playback check not run (uv run --with playwright ...)")
    errs = []
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=False, args=["--enable-gpu-rasterization", "--ignore-gpu-blocklist"])
        pg = b.new_page(viewport={"width": 540, "height": 960})
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        pg.goto(url, wait_until="load"); pg.bring_to_front()
        r = pg.evaluate(_DYN_JS, loops); b.close()
    return dynamic_issues(r["frames"], r["long"], r["errors"] + errs)

def dynamic_issues(frame_ms: list, long_tasks: list, errors: list) -> list[str]:
    f = []
    if frame_ms:
        s = sorted(frame_ms); p99 = s[min(int(math.ceil(0.99 * len(s))) - 1, len(s) - 1)]
        if p99 > PLAYBACK["p99_ms"]:
            f.append(F("PLAYBACK-FRAMETIME", f"p99 frame time {p99:.0f} ms > {PLAYBACK['p99_ms']:.0f} ms over {len(s)} frames (R-382)"))
    big = [d for d in long_tasks if d > PLAYBACK["long_task_ms"]]
    if big:
        f.append(F("PLAYBACK-LONGTASK", f"{len(big)} long task(s), worst {max(big):.0f} ms > {PLAYBACK['long_task_ms']:.0f} ms (R-382)"))
    if errors:
        f.append(F("PLAYBACK-ERROR", f"page raised {len(errors)} exception/console error(s): {errors[0][:120]} (R-382)"))
    return f



# ================================================================== CALM format profile (the owner 2026-10-24, CLAUDE.md "Calm format")
# His pacing, our art. A shot spec declares "format": "calm"; a shotlist declares "profile": "calm" (its own `format` key is the schema id
# "shotlist/1"). Anything else is "premium" and keeps the never-a-slideshow thresholds untouched. The art checks (LOOK2D, SEAM, joints, hands,
# shadows, no-touch, no-tashkeel) apply to both formats.
# BAND = (lo, hi): lo is a floor (the format needs it: holds are expected), hi a ceiling (restlessness fails). None = open on that side.
# Every band below was MEASURED with `quality_gate.py calm` on the 10 stickman story reels in work/stickman/ and checked against E01 run 1; the table
# is kb/quality/gate-spec.md section H. A value marked DEFAULT has no harvested sample behind it (the reels carry no caption or wrapper data).
FORMATS = ("premium", "calm")

def format_of(obj) -> str:
    """'calm' or 'premium' (default): a spec's `format`, or a shotlist / plan `profile`."""
    if not isinstance(obj, dict):
        return "premium"
    v = obj.get("profile") if obj.get("profile") in FORMATS else obj.get("format")
    return v if v in FORMATS else "premium"

CALM = {
    # --- measured on the video (quality_gate.py calm)
    "shot_len_s":       (1.8, 6.0),   # average shot length in seconds = duration / (scene changes + 1)
    "cuts_per_min":     (8.0, 30.0),   # ffmpeg scene > 0.08 changes per minute (soft joins count)
    "hold_share":       (0.05, 0.25),   # share of runtime frozen in holds >= 0.5 s (freezedetect)
    "motion_coverage":  (0.08, 0.35),   # mean share of 16 px blocks changing per moving step
    "motion_clusters":  (2.0, 8.0),   # independent motion clusters per moving step: the measured stand-in for "subjects in frame"
    "longest_hold_s":   (None, 3.0),   # longest single hold in seconds (freezedetect): a hold is a deliberate beat, not a stall
    "audio_active":     (0.80, None),   # share of 20 ms frames above -40 dBFS: voice + bed never drop out
    "loudness_i":       (-15.0, -13.0),   # integrated LUFS
    "lra":              (None, 5.0),   # loudness range LU
    # --- declared data (captions.json, plan.json, end.json, shotlist): the reels cannot show these
    "caption_words_max": 8,             # the owner 2026-10-25 (C7) replaces "1 to 3 words a plate" (recipe section 3): a plate is a whole sentence or clause, at most 8 words on 2 lines (cap_sentence.UNIT_WORDS_MAX)
    "caption_lines_max": 2,
    "caption_font_px_min": 90,          # DEFAULT: recipe estimates the caption at about 7 % of frame height (134 px at 1920); 90 px at 1080 wide is the floor
    "voice_share_min":  0.85,           # DEFAULT: union of the placed voice takes (any speaker) / runtime; narrator share is NARRATOR-SHARE (calm_compose), format v2 2026-10-28
    "wrapper_parts":    ("recap", "day_card", "choice_card", "follow_card"),
    "recap_by_s":       3.0,            # recipe: recap hook 0 to 2.2 s
    "choice_last_s":    20.0,           # recipe: choice card at 66 s of 85 s, i.e. inside the last 20 s
    "subjects_max":     1,              # declared figures per shot: one subject per frame
}

def _band_fail(cid: str, v, band, label: str, unit: str = "") -> list[str]:
    lo, hi = band
    if v is None:
        return [F(cid, f"{label} not measured")]
    if lo is not None and v < lo:
        return [F(cid, f"{label} = {v}{unit} < {lo}{unit}: below the calm band {lo}..{hi}")]
    if hi is not None and v > hi:
        return [F(cid, f"{label} = {v}{unit} > {hi}{unit}: above the calm band {lo}..{hi}")]
    return []

# ---- declared transitions (E01C run, the owner's mix-v2 C3: flash, whoosh, ink wipes are DECLARED joins, not scene changes)
# Root cause of the false CALM-CUTRATE / CALM-SHOTLEN / CALM-HOLDS fails on E01C: the video detector (ffmpeg scene > 0.08) fires several times inside
# ONE declared transition (a flash or an ink wipe repaints the whole frame over 0.25 s), so 22 declared items read as 60 scene changes. The plan
# already says where every shot starts and where every transition runs, so the gate counts SHOTS from that list, ignores detector hits that fall
# inside a declared transition window, and measures holds per shot outside those windows. A detector hit OUTSIDE every window is an UNDECLARED
# change (a real cut nobody planned, a glitch) and still counts, so a restless episode is still caught.
TRANSITION_PAD_S = 0.10    # the detector's frame can sit a little outside the nominal overlap (the effect's first and last frames)
INNER_CUT_S = 0.16         # the crossfade of a cut inside the choice sequence's top half (calm_compose XD)


def declared_boundaries(timeline: dict) -> list[dict]:
    """Every declared shot boundary of an episode timeline as {t, a, b, kind}: t = the cut point, [a, b] = the transition window (padded).
    Between two items the overlap runs t0(next)..t1(prev); a hard join (no overlap) is a window of 2 pads around the join. Cuts the choice item
    declares inside its own split (`split.cuts`, seconds from the item start) are boundaries too."""
    items = sorted((timeline or {}).get("items", []), key=lambda i: i["t0"])
    out = []
    for prev, nxt in zip(items, items[1:]):
        a, b = nxt["t0"], prev["t1"]
        if b < a:
            a = b = (a + b) / 2
        out.append({"t": (a + b) / 2, "a": a - TRANSITION_PAD_S, "b": b + TRANSITION_PAD_S, "kind": "join"})
    for it in items:
        for c in (it.get("split") or {}).get("cuts", []):
            t = it["t0"] + float(c["t"])
            out.append({"t": t + INNER_CUT_S / 2, "a": t - TRANSITION_PAD_S, "b": t + INNER_CUT_S + TRANSITION_PAD_S, "kind": "inner"})
    return sorted(out, key=lambda x: x["t"])


def _merge_windows(windows):   # was `_merge`: the same name as the profile merger at the top of this file, which it shadowed (resolve_profile crashed: TypeError, 2 args)
    out = []
    for a, b in sorted(windows):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def _clip(spans, segs):
    """The parts of spans that lie inside segs (both lists of (a, b))."""
    out = []
    for a, b in spans:
        for c, d in segs:
            lo, hi = max(a, c), min(b, d)
            if hi > lo:
                out.append((lo, hi))
    return out


def declared_pacing(timeline: dict, dur: float, change_times: list, freeze_spans: list, hold_min_s: float = 0.5) -> dict:
    """Pacing metrics from the DECLARED shots. change_times = detector hits (s); freeze_spans = [(start, end)] of every freezedetect hold >= hold_min_s.
    Returns scene_changes (= declared + undeclared), declared_cuts, undeclared_changes, ignored_in_transitions, shot_len_s, shortest_shot_s,
    cuts_per_min, freeze_share_05s (held time / time outside transition windows), longest_hold_s, transition_s."""
    bd = declared_boundaries(timeline)
    win = _merge_windows([(x["a"], x["b"]) for x in bd])
    inside = lambda t: any(a <= t <= b for a, b in win)
    undeclared = [t for t in change_times if not inside(t)]
    cuts = len(bd) + len(undeclared)
    pts = sorted([0.0] + [x["t"] for x in bd] + list(undeclared) + [dur])
    lens = [b - a for a, b in zip(pts, pts[1:]) if b - a > 1e-6]
    segs, cur = [], 0.0                       # shots with their transition windows taken out
    for a, b in win:
        if a > cur:
            segs.append((cur, a))
        cur = max(cur, b)
    if cur < dur:
        segs.append((cur, dur))
    holds = [(a, b) for a, b in _clip(freeze_spans, segs) if b - a >= hold_min_s]
    open_s = sum(b - a for a, b in segs)
    held = sum(b - a for a, b in holds)
    return {"scene_changes": cuts, "declared_cuts": len(bd), "undeclared_changes": len(undeclared),
            "ignored_in_transitions": len(change_times) - len(undeclared),
            "shot_len_s": round(dur / (cuts + 1), 2), "shortest_shot_s": round(min(lens), 2) if lens else round(dur, 2),
            "cuts_per_min": round(cuts / max(dur, 1e-6) * 60, 1),
            "freeze_share_05s": round(held / max(open_s, 1e-6), 4), "freeze_holds_05s": len(holds),
            "longest_hold_s": round(max((b - a for a, b in holds), default=0.0), 2), "transition_s": round(dur - open_s, 2)}


def check_calm_render(m: dict) -> list[str]:
    """Video-measured calm checks. m = quality_gate.analyse_calm(...) metrics."""
    f: list[str] = []
    f += _band_fail("CALM-SHOTLEN", m.get("shot_len_s"), CALM["shot_len_s"], "average shot length", " s")
    f += _band_fail("CALM-CUTRATE", m.get("cuts_per_min"), CALM["cuts_per_min"], "shot changes per minute")
    f += _band_fail("CALM-HOLDS", m.get("freeze_share_05s"), CALM["hold_share"], "share of runtime held (>= 0.5 s)")
    f += _band_fail("CALM-HOLD-LONGEST", m.get("longest_hold_s"), CALM["longest_hold_s"], "longest single hold", " s")
    f += _band_fail("CALM-MOTION", m.get("motion_coverage"), CALM["motion_coverage"], "motion coverage")
    f += _band_fail("CALM-SUBJECTS", m.get("motion_clusters"), CALM["motion_clusters"], "independent motion clusters per step (subjects proxy)")
    if not m.get("has_audio", True):
        f.append(F("CALM-VOICE-COVERAGE", "no audio track: a calm episode needs voice (narrator and characters) that covers the runtime"))
    else:
        f += _band_fail("CALM-VOICE-COVERAGE", m.get("audio_active"), CALM["audio_active"], "audio-active share of runtime")
        f += _band_fail("CALM-LOUDNESS", m.get("loudness_i"), CALM["loudness_i"], "integrated loudness", " LUFS")
        f += _band_fail("CALM-LRA", m.get("lra"), CALM["lra"], "loudness range", " LU")
    return f

CALM_EVENT_CEILING = {"motion_coverage": 0.45, "motion_clusters": 10.0}   # format v2 (the owner 2026-10-28): a shot the plan marks as an `event` shows an action while a character speaks over it


def check_calm_shot(m: dict, event: bool = False) -> list[str]:
    """A single calm SHOT (quality_gate render --format calm): only the ceilings, restlessness fails. The floors (holds, shot length) belong to the whole episode.
    event=True (the plan's scene has an `event`): the action ceilings CALM_EVENT_CEILING apply instead; every other shot keeps the calm ones."""
    f: list[str] = []
    for cid, key, label in (("CALM-MOTION", "motion_coverage", "motion coverage"), ("CALM-SUBJECTS", "motion_clusters", "independent motion clusters per step (subjects proxy)")):
        hi = CALM_EVENT_CEILING[key] if event else CALM[key][1]
        v = m.get(key)
        if v is not None and hi is not None and v > hi:
            f.append(F(cid, f"{label} = {v} > {hi}: restless for the calm format"))
    return f

def _union_s(spans) -> float:
    tot, end = 0.0, None
    for a, b in sorted(spans):
        if end is None or a > end:
            tot += b - a; end = b
        elif b > end:
            tot += b - end; end = b
    return tot

def check_calm_declared(plan, caps, end, sl, total_s: float) -> list[str]:
    """Calm checks on declared data: plan.json lines, captions.json plates, end.json card, shotlist `wrapper` and per-shot `subjects`.
    Missing data fails, it is never skipped."""
    f: list[str] = []
    C = CALM
    plates = sorted((caps or {}).get("captions", []), key=lambda c: c.get("start", 0))
    if not plates:
        f.append(F("CALM-CAPTION-STYLE", "no caption plates declared"))
    else:
        from gloss import strip_gloss   # a bracketed «(meaning)» after a foreign word is an annotation under the plate, not a caption word (CLAUDE.md "Gloss foreign words")
        nwords = lambda c: len(strip_gloss(str(c.get("text", ""))).split())
        many = [f"{c.get('line', '?')}:{nwords(c)}" for c in plates if nwords(c) > C["caption_words_max"]]
        if many:
            f.append(F("CALM-CAPTION-STYLE", f"{len(many)} of {len(plates)} plates carry more than {C['caption_words_max']} words ({', '.join(many[:5])}): a calm caption is a whole sentence or clause of at most {C['caption_words_max']} words, the spoken word highlighted"))
        tall = [f"{c.get('line', '?')}:{c['n_lines']}" for c in plates if c.get("n_lines", 1) > C["caption_lines_max"]]
        if tall:
            f.append(F("CALM-CAPTION-STYLE", f"{len(tall)} plates run over {C['caption_lines_max']} lines ({', '.join(tall[:5])}): a sentence plate is two lines at most"))
        over = [f"{a.get('line')}/{b.get('line')}" for a, b in zip(plates, plates[1:]) if b.get("start", 0) < a.get("end", 0) - 1e-6]
        if over:
            f.append(F("CALM-CAPTION-STYLE", f"{len(over)} plate pair(s) on screen together ({', '.join(over[:4])}): one caption at a time"))
        small = [str(c.get("line", "?")) for c in plates if c.get("font_px_1080", 0) < C["caption_font_px_min"]]
        if small:
            f.append(F("CALM-CAPTION-STYLE", f"{len(small)} plates under {C['caption_font_px_min']} px at 1080 wide ({', '.join(small[:4])}): calm captions are big"))
    lines = (plan or {}).get("lines", [])
    spans = [(float(l["start"]), float(l["start"]) + float(l["dur"])) for l in lines if "start" in l and "dur" in l]
    # intro_freeze time is excluded from the coverage count, the way a title card is. The caller declares it as plan["intro_s"] (the summed length
    # of the timeline's intro items); coverage = placed voice seconds / (runtime - intro seconds). Every other silent gap still counts against the 0.85 floor.
    intro_s = max(0.0, float((plan or {}).get("intro_s") or 0.0))
    base = total_s - intro_s
    share = _union_s(spans) / base if base > 0 and spans else 0.0
    if share < C["voice_share_min"]:
        f.append(F("CALM-VOICE-COVERAGE", f"placed voice (narrator and characters, any speaker) covers {share:.2f} of the runtime (need >= {C['voice_share_min']}): silence is not the pacing"))
    wr = (sl or {}).get("wrapper") or {}
    ep_no, recap_from = (sl or {}).get("episode_no"), (sl or {}).get("recap_from")
    no_recap = isinstance(ep_no, int) and isinstance(recap_from, int) and ep_no < recap_from   # a recap recaps a vote: the shotlist declares the episode number and the first episode with a recap, and an episode before it opens on its story (the owner 2026-10-25); a shotlist that declares neither keeps the recap required
    parts = [p for p in C["wrapper_parts"] if not (no_recap and p == "recap")]
    if no_recap and "recap" in wr:
        f.append(F("CALM-WRAPPER", f"episode {ep_no} declares a recap card but recaps start at episode {recap_from}"))
    miss = [p for p in parts if not isinstance(wr.get(p), dict)]
    if miss:
        f.append(F("CALM-WRAPPER", f"wrapper part(s) not declared: {', '.join(miss)} (shotlist `wrapper`: recap, day_card, choice_card, follow_card, each {{t0, t1}} in seconds)"))
    else:
        t = lambda k, e: float(wr[k].get(e, -1))
        if not no_recap and not (0 <= t("recap", "t0") and t("recap", "t1") <= C["recap_by_s"] + 1e-6):
            f.append(F("CALM-WRAPPER", f"recap is {t('recap', 't0')}..{t('recap', 't1')} s: it must sit inside the first {C['recap_by_s']:g} s"))
        if total_s and t("choice_card", "t0") < total_s - C["choice_last_s"]:
            f.append(F("CALM-WRAPPER", f"choice card starts at {t('choice_card', 't0')} s: it belongs in the last {C['choice_last_s']:g} s of {total_s:.1f}"))
        if not t("follow_card", "t0") >= t("choice_card", "t0"):
            f.append(F("CALM-WRAPPER", "the follow card must come after the choice card"))
        if not 0 <= t("day_card", "t0") < t("choice_card", "t0"):
            f.append(F("CALM-WRAPPER", "the day card must come before the choice card"))
        if end is not None and len(end.get("choices", [])) != 2:
            f.append(F("CALM-WRAPPER", f"the choice card shows {len(end.get('choices', []))} choices (need exactly 2)"))
    big = [str(s.get("id", "?")) for s in (sl or {}).get("shots", []) if len(s.get("subjects", [])) > C["subjects_max"]]
    if big:
        f.append(F("CALM-SUBJECTS", f"shot(s) {', '.join(big[:6])} declare more than {C['subjects_max']} subject in `subjects`: one subject per frame"))
    return f
