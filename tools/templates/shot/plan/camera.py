"""Camera data for this shot: beats, shots (2D flat camera: x, y, z, F; R-328..R-333) and the cuts between them.
The library (tools/shotlib/camera.py) turns this into camera-plan.json + thumbnails and validates it.
Written before any animation (stage camera)."""
BEATS = [
    {"id": "b1", "start": 0.0, "end": 3.0, "treatment": "A", "emotion": "calm"},
    {"id": "b2", "start": 3.0, "end": 4.625, "treatment": "B", "emotion": "surprise"},
    {"id": "b3", "start": 4.625, "end": 6.875, "treatment": "A+B", "emotion": "dread"},
    {"id": "b4", "start": 6.875, "end": 9.0, "treatment": "A", "emotion": "suspicion"},
]
SHOTS = [
    {"shot": "s1", "beat": "b1", "t0": 0.0, "t1": 0.75, "size": "MS", "angle": "eye", "lens_mm": 35, "move": "push",
     "cam0": {"x": 0.04, "y": -0.02, "z": 0.40, "F": 1700}, "cam1": {"x": 0.06, "y": 0.02, "z": 0.55, "F": 1700},
     "start_frame_desc": "Hero waist up behind the counter; a blank card lies face up in front of her left hand, her right hand pads hold its corner; the pen is raised in her left hand",
     "end_frame_desc": "a little closer; the nib comes down onto the card (cut on the touch)",
     "why": "settle the viewer into her routine: a slow push says 'watch what she cares about'", "serves_emotion": "calm",
     "safe_boxes": [{"id": "face", "x": 380, "y": 640, "w": 320, "h": 380}], "catalogue_camera": "ms-eye-flat"},
    {"shot": "s2", "beat": "b1", "t0": 0.75, "t1": 3.0, "size": "ECU", "angle": "top-pov", "lens_mm": 35, "move": "track", "pov": True,
     "insert": {"K": 3800, "eye": 0.55, "cx0": 0.012, "cy0": 0.004, "cx1": -0.018, "cy1": 0.010, "y0_px": 860},
     "world_ref": {"x": 0.06, "y": 0.02, "z": 0.55, "F": 1700},
     "start_frame_desc": "her POV from above: the card front up on the counter, her left hand's tripod grip with the nib touching the card's right side, her right hand's pads on its lower-right corner",
     "end_frame_desc": "the label stands on the card; the flap rattles off screen, the pen lifts, dust sifts down, the falling bag's shadow sweeps in (cut on the impact at 3.0 s)",
     "why": "her trait is labelling: the viewer must watch the ink appear right to left on the face the nib touches, so the camera goes to her side of the page (R-388); a small track keeps the nib near centre",
     "serves_emotion": "calm", "safe_boxes": [{"id": "pen-tip", "x": 300, "y": 600, "w": 520, "h": 420}], "catalogue_camera": "top-pov-insert"},
    {"shot": "s3", "beat": "b2", "t0": 3.0, "t1": 4.625, "size": "MS", "angle": "eye", "lens_mm": 35, "move": "handheld",
     "cam0": {"x": -0.05, "y": 0.06, "z": 0.48, "F": 1700}, "cam1": {"x": -0.07, "y": 0.05, "z": 0.56, "F": 1700},
     "start_frame_desc": "the bag big on the counter left of centre, its tag hanging at the knot showing its stamped back; Hero recoiling behind it, drawers popping, the card hops",
     "end_frame_desc": "she settles, hands at her chest, pen still in the left hand, staring at the bag",
     "why": "shock: the bag sits between us and her; the drawn shake carries the impact; the front line is re-established after the POV insert", "serves_emotion": "surprise",
     "safe_boxes": [{"id": "face", "x": 380, "y": 560, "w": 380, "h": 420}], "catalogue_camera": "ms-eye-flat"},
    {"shot": "s4", "beat": "b3", "t0": 4.625, "t1": 5.75, "size": "MCU", "angle": "eye", "lens_mm": 50, "move": "push",
     "cam0": {"x": -0.02, "y": -0.07, "z": 1.0, "F": 2600}, "cam1": {"x": -0.04, "y": -0.05, "z": 1.22, "F": 2600},
     "start_frame_desc": "chest up; the cold glow of the tag climbs her coat from below frame left",
     "end_frame_desc": "closer on her face as she leans in; eyes locked down-left on the tag's front (eye-line to her POV)",
     "why": "dread grows: a slow push follows her lean, the face fills the frame", "serves_emotion": "dread",
     "safe_boxes": [{"id": "face", "x": 300, "y": 420, "w": 480, "h": 560}], "catalogue_camera": "mcu-eye-long"},
    {"shot": "s5", "beat": "b3", "t0": 5.75, "t1": 6.875, "size": "CU", "angle": "pov", "lens_mm": 50, "move": "drift", "pov": True,
     "insert": {"drift_px": [6, 3]}, "world_ref": {"x": -0.03, "y": -0.05, "z": 1.20, "F": 2600},
     "start_frame_desc": "her POV over the counter: the bag (halftone) below, the tag hanging from its knot with the FRONT toward her: the name settles on its plate",
     "end_frame_desc": "same frame, a hair closer; the cold light on the tag flickers",
     "why": "the name must be read, and only the face toward her carries it: her POV shows the front she sees (R-387, R-388); a near-locked drift holds it still",
     "serves_emotion": "dread", "safe_boxes": [{"id": "tag-text", "x": 240, "y": 760, "w": 600, "h": 460}], "catalogue_camera": "pov-tag-cu"},
    {"shot": "s6", "beat": "b4", "t0": 6.875, "t1": 9.0, "size": "MS", "angle": "eye", "lens_mm": 35, "move": "pull",
     "cam0": {"x": -0.06, "y": 0.04, "z": 0.86, "F": 1700}, "cam1": {"x": -0.04, "y": 0.0, "z": 0.56, "F": 1700},
     "start_frame_desc": "her right sleeve sweeps in; thumb behind, index in front, she pinches the tag's corner; the string goes taut to the bag handle",
     "end_frame_desc": "pulled back: she reads its front (we see the stamped back), mouths her name, narrows her eyes, glances up at the chute",
     "why": "suspicion: the pull-out reveals the cold room around the clue and the chute it came from", "serves_emotion": "suspicion",
     "safe_boxes": [{"id": "face", "x": 360, "y": 560, "w": 380, "h": 420}], "catalogue_camera": "ms-eye-flat"},
]
CUTS = {"s1->s2": "action-cut on the nib touching the card, into her POV (the writing hand flips to screen left: a POV insert, declared)", "s2->s3": "impact-cover at 3.0 s (bag hits the counter)",
        "s3->s4": "carrier-bleed from the tag's cold glow", "s4->s5": "eye-line match into her POV: her gaze goes down-left, the tag front sits where she looks",
        "s5->s6": "contour-wipe: the cut lands on her sleeve entering; the bag's halftone wipes off along the sleeve edge"}

# Extra fields copied into camera-plan.json as written (rules the plan states for the reviewer).
EXTRA = {
    "lens_rule": "2D flat camera: x, y, z and focal only; no yaw, no pitch (F9). Front shots are 'eye'; s2 (top-pov) and s5 (pov) are drawn POV plates from her side of the counter, not pitched 3D cameras.",
    "staging_rule": "R-388: the viewer sees writing appear only on the face the nib touches; the card lies front up and s2 is her POV; the bag tag's front faces her, so only her POV (s5) shows the name",
    "line_180": "across the counter, camera side for the front shots; s2 and s5 are POV inserts from her side (declared)",
    "screen_direction": "front shots: the bag falls screen left of her, the pen hand works screen right; her POV mirrors left and right",
}


def thumb_art(s, ink, grey, figure):
    """Sketch of each shot inside the thumbnail frame (library passes the ink/grey styles and the figure helper)."""
    sid = s["shot"]
    p = []
    if sid == "s1":
        p += ['<path d="M0 340 L270 340 L270 480 L0 480Z" fill="#eee" stroke="#000" stroke-width="1.5"/>'] + figure(135, 175, 1.0) + \
             [f'<path d="M190 250 Q210 300 176 322" {ink}/>', f'<rect x="160" y="300" width="22" height="16" {grey}/>', f'<path d="M60 20 L60 140" {ink}/><circle cx="60" cy="150" r="10" {grey}/>']
    elif sid == "s2":
        p += ['<rect x="0" y="0" width="270" height="480" fill="#eee"/>', '<path d="M0 30 L270 30" stroke="#000" stroke-width="2"/>', '<path d="M0 395 L270 395" stroke="#000" stroke-width="2"/>',
              '<rect x="70" y="165" width="130" height="82" rx="4" fill="#fff" stroke="#000" stroke-width="2.4" transform="rotate(-6 135 206)"/>',
              '<text x="168" y="214" font-size="20" text-anchor="end">خرز أصفر</text>',
              f'<path d="M150 205 L60 330 L30 480" {ink}/>', '<path d="M150 205 L95 262" stroke="#000" stroke-width="5"/>', f'<ellipse cx="88" cy="290" rx="34" ry="44" {grey}/>',
              f'<ellipse cx="205" cy="268" rx="34" ry="40" {grey}/>', f'<path d="M215 300 L250 480" {ink}/>', '<text x="6" y="470" font-size="11">her coat</text>', '<text x="6" y="44" font-size="11">counter edge</text>']
    elif sid == "s3":
        p += ['<path d="M0 360 L270 360 L270 480 L0 480Z" fill="#eee" stroke="#000" stroke-width="1.5"/>'] + figure(150, 160, 1.0) + \
             [f'<rect x="40" y="280" width="110" height="80" rx="12" fill="#999" stroke="#000" stroke-width="2"/>', '<text x="60" y="326" font-size="13">bag</text>']
    elif sid == "s4":
        p += figure(140, 230, 2.0) + ['<path d="M30 470 L10 478" stroke="#0aa" stroke-width="6"/>', '<text x="12" y="460" font-size="13">glow</text>']
    elif sid == "s5":
        p += ['<rect x="0" y="0" width="270" height="480" fill="#ddd"/>', '<rect x="10" y="300" width="250" height="200" rx="26" fill="#bbb" stroke="#000" stroke-width="2"/>',
              '<path d="M200 300 Q220 230 180 196" stroke="#000" stroke-width="1.5" fill="none"/>',
              '<path d="M55 190 L215 190 L215 300 L55 300Z" fill="#fff" stroke="#000" stroke-width="2.4"/>', '<text x="135" y="250" font-size="30" font-weight="700" text-anchor="middle">هدى</text>',
              '<text x="135" y="282" font-size="14" text-anchor="middle">الخميس القادم</text>', '<text x="6" y="40" font-size="12">her POV: the tag FRONT</text>']
    elif sid == "s6":
        p += ['<path d="M0 360 L270 360 L270 480 L0 480Z" fill="#eee" stroke="#000" stroke-width="1.5"/>'] + figure(150, 165, 0.9) + \
             [f'<rect x="56" y="318" width="34" height="22" fill="#fff" stroke="#000" stroke-width="2"/>', f'<rect x="40" y="320" width="100" height="44" {grey}/>', '<path d="M100 10 L100 80" stroke="#000" stroke-width="6"/>']
    return p
