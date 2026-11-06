# Critic checklist (replaces the owner's notes)

Version 1, 2026-10-23. Used by the Sonnet critic in `pipelines/HEAL.md`. Every note the owner ever gave (F1 to F15, the art book and shot 2 notes) is a yes/no question here, and so are the taste signals behind his scores. the owner should not have to say any of it again.

Read it like this: **yes = good**. A **no** is a fault. Answer every question that applies to the kind of work (`shot`, `episode`, `artbook`, `writing`, `voice`), with evidence: a frame number, a tile on a review sheet, or a file and line. `na` is allowed only when the thing is not in the work at all (say so). Never answer from memory of the script: look at the pixels.

## 🔎 What to look at (the critic's reading list)

| Work | Read these, in this order |
|---|---|
| shot | `gate/report.json`, `review/sheet-frames.png`, `review/sheet-hands.png`, `review/sheet-faces.png`, `review/sheet-props.png`, `review/index.json` (tile to frame map), then 8 to 12 raw frames from `out/<id>.mp4` (ffmpeg, one per beat plus every cut), `shot-spec.json`, `camera-plan.json`. Side by side with `reference/mix-v5/` (hands-sheet.png, mix-v5.mp4) and `reference/shot2-partner-drain/review/`. |
| episode | `gate/report.json`, `plan.json`, `captions/`, `end/`, 12 frames from `episode.mp4` incl. every cut and the end card, the script, the voice manifest. |
| artbook | the sheets listed in `bible/series/*/` modules (PNG, 300 dpi), `artbook.py check` output, the Art Book tab crops. One sheet at a time, all 8 per character. |
| writing | the bible file, `bible_check.py` output, the culture brief, `CONTINUITY.md`. |
| voice | not used now: voice is caption-only (Gemini banned). CQ-E2, CQ-E3 and CQ-V1 apply only to kind `voice`, which is dormant until a new TTS engine is chosen. |

## 🧮 Severity classes

| Class | Meaning | Cap on the score |
|---|---|---|
| S1 reject | the work is the wrong kind of thing: 3D look, a slideshow, a stall or an unplayable preview, touch between unrelated men and women | 4 |
| S2 blocker | a visible construction break a viewer sees at once: a glitching hand, writing on the wrong face, seam lines, shoulders from the middle, a hollow shadow, unconnected hijab or needle, an elbow flip | 6 |
| S3 major | clearly below the bar but the piece still works: thin face or emotion, missing nose or lips, a cut that feels off, a flat single framing, a missing caption, a weak sheet | 8 |
| S4 minor | polish: a stiff tie, a small drift, a label | none |

## ❓ The questions

Columns: `ID | applies | severity if no | question (yes = good) | look at | maps to (rule / check / F-note)`.

### T: taste signals (what made v5 a 10 and v2 a 6)

| ID | Applies | Sev | Question | Look at | Maps to |
|---|---|---|---|---|---|
| CQ-T1 | shot,episode | S1 | Is it plainly hand-drawn 2D: ink line, flat or cel fills with at most 2 or 3 tone steps, hard-edged flat shadows, no smooth gradient on bodies, no lit-sculpture look? | 4 raw frames, one close-up of an arm | F9, R-380, LOOK2D-LINE, LOOK2D-RAMP, SHADOW-FLAT |
| CQ-T2 | shot,episode | S1 | Is it never a slideshow: do background layers, character parts and objects each move on their own across consecutive tiles, with light and shadow that change? | `sheet-frames.png`, 6 consecutive tiles | RC1 to RC8, R-201 to R-213, render gate (motion_coverage, independent_share) |
| CQ-T3 | shot,episode | S1 | Does the preview play the recorded video smoothly from the first frame to the last, with no live canvas painter and no stall? | `previews/index.html` tab source, `gate/preview.out` | F10, R-382, R-394, PLAYBACK-VIDEO, PLAYBACK-AUTOPLAY |
| CQ-T4 | shot,episode | S3 | Next to `reference/mix-v5` and `shot2-partner-drain`, does it match their premium bar for depth, light, hands and faces? | raw frames next to the reference sheets | R-397 |
| CQ-T5 | shot,episode | S3 | Is the camera used with intent: more than one framing across the piece, every cut or move motivated, not one static medium shot for the whole time? | `camera-plan.json`, `sheet-frames.png` | F3, R-328, R-330, CAM-PLAN, CAM-WHY, CAM-VARY |
| CQ-T6 | shot,episode | S3 | With the sound off at phone size, does the story still read? | `sheet-frames.png` shrunk | R-379, R-401 |
| CQ-T7 | shot,episode | S1 | Is there no touch between unrelated men and women (an object between them, a hand that stops short)? | contact tiles; `shot-spec.json` contacts | the owner 2026-10-23 shot 2, NO-TOUCH, ACTOR-CONTACT |
| CQ-T8 | shot,episode | S3 | Does the light carry the mood of each beat (key, fill, rim from a named source), not one flat grade? | 4 raw frames, one per beat | RC2, R-203, R-204, EMO-LIGHT |
| CQ-T9 | shot,episode | S3 | Are there at least 5 readable depth planes with parallax, a foreground that overlaps the subject, and a background of things that move? | raw frames, `sheet-frames.png` | RC3, R-205, R-206, depth_bands, parallax_corr |
| CQ-T10 | shot,episode | S4 | Is any one frame wasted, such as an empty hold with nothing alive? | `sheet-frames.png` | R-208, freeze_share_05s |

### B: body and shadow (F1, F7, F8, F11)

| ID | Applies | Sev | Question | Look at | Maps to |
|---|---|---|---|---|---|
| CQ-B1 | shot,episode | S2 | Does every arm stay inside human range, with the elbow bending one way and no flip between two neighbouring frames? | `sheet-frames.png` and `sheet-hands.png`, the frames around the fastest arm move | F1, R-300 to R-305, RIG-LIMITS, RIG-HINGE, BIO-PROFILE |
| CQ-B2 | shot,episode | S2 | Do the shoulders sit at the outer end of the collarbone line, below a visible neck, and rise with the arm, never from the middle of the chest? | a raised-arm frame and a rest frame | F7, R-307, R-308, R-341, R-342, RIG-SHOULDER, RIG-SHOULDER-RIDES |
| CQ-B3 | shot,episode | S2 | Is the body one connected shape, with no ink line across elbow, shoulder, fingers or head-and-neck? | zoom on elbow, shoulder, neck in 3 frames | F11, R-381, SEAM-CROSS, SEAM-HEADNECK |
| CQ-B4 | shot,episode | S2 | Is the shadow a flat 2D shape of her mass, one connected shape, with no hollow circles and no cut-out at the neck? | frames with a strong light; `out/masks/shadow` | F8, R-317, R-356 to R-359, SHADOW-MASS, SHADOW-FLAT, RIG-SHADOW-HOLES |
| CQ-B5 | shot,episode | S2 | Do hijab, garment, needle and what is under them connect to a parent and stay attached in every frame? | frames with the head turned and the arm raised | F5, R-304, R-310 to R-313, R-350 to R-354, ATT-DECLARED, RIG-ATTACH, ATT-HAIR |
| CQ-B6 | shot,episode | S3 | Are proportions constant across shots: head size, neck, arm and bone lengths, costume? | one frame per shot side by side | R-301 to R-303, BIO-PROPORTIONS, RIG-SEGLEN |
| CQ-B7 | shot,episode | S3 | Does each character and prop keep its declared mechanics (rubber only where declared, a cloth that drapes, a stiff card that bends little)? | motion tiles of the prop | R-300, R-319, BIO-PROFILE |
| CQ-B8 | shot,episode | S3 | Does motion read as weight: anticipation, overshoot, settle, parts that follow with a lag? | consecutive tiles of the biggest move | RC1, RC4, R-201, R-202, R-207, RIG-PEAK |
| CQ-B9 | shot,episode | S2 | Do two characters keep their own place, order and overlap with no part of one passing through the other? | frames where both are on screen | ACTOR-ORDER, ACTOR-OCCLUSION, MULTI-ACTOR |

### H: hands, props, writing (F5, F13, F14, F15)

| ID | Applies | Sev | Question | Look at | Maps to |
|---|---|---|---|---|---|
| CQ-H1 | shot,episode | S2 | Does each hand have four fingers and a thumb, keep the same shape from tile to tile, and never glitch, pop or flip between two frames? | `sheet-hands.png`, every tile pair | F13, R-383 to R-385, HAND-TOPO |
| CQ-H2 | shot,episode | S2 | Is each hand the right side (left is left), with a grip authored for that hand, not a mirrored one by accident? | `sheet-hands.png` | F13, R-385, HAND-SIDE, HAND-SWAP |
| CQ-H3 | shot,episode | S2 | Is every grip change blended over several frames, with no switch of pinch or contact in the middle of a blend? | hand tiles around each grab and release | F13, R-386, HAND-SWAP |
| CQ-H4 | shot,episode | S2 | Does the writing appear on the face she touches, grow under the nib, and run in the script direction (Arabic right to left)? | `sheet-props.png`, writing frames | F14, R-388 to R-390, PROP-FACE, WRITE-REVEAL |
| CQ-H5 | shot,episode | S2 | Is the pen tip on the paper the whole time she writes? | writing frames | F15, R-391, NIB-CONTACT |
| CQ-H6 | shot,episode | S2 | Is the layer order of hand, pen, paper and held object logical (fingers over the pen, pen over the paper, a held thing in front of the palm and behind the fingers), never faked by overdraw? | `sheet-hands.png`, `sheet-props.png` | F15, R-352, R-392, LAYER-GRIP, RIG-LAYERS, ATT-LAYERS |
| CQ-H7 | shot,episode | S2 | Does a two-sided prop show the right side, and print on the right side, at every angle? | prop tiles when the prop turns | F14, R-387, PROP-FACE |
| CQ-H8 | shot,episode | S3 | Do held objects follow the hand with weight and a contact point (no sliding, no floating a few pixels away)? | contact frames | F5, R-350, R-351, RIG-CONTACT-GAP, ACTOR-CONTACT |
| CQ-H9 | shot,episode | S3 | Does a handover or grab between two characters read: reach, contact on the object, release, with the hands on different layers? | handover frames | ACTOR-INTERACTION, HANDOVER |

### F: face and feeling (F6, F12)

| ID | Applies | Sev | Question | Look at | Maps to |
|---|---|---|---|---|---|
| CQ-F1 | shot,episode,artbook | S3 | Are nose and lips designed and visible at the angle shown, with lips that shape speech and feeling, not two dots and a line? | `sheet-faces.png`; artbook face sheet 07 | F12, R-393, R-365, EMO-PROFILE |
| CQ-F2 | shot,episode | S3 | Do the eyes lead (eyes first, then head), track, blink and dart believably? | `sheet-faces.png`, 3 consecutive tiles | F6, R-360 to R-362, RIG-EYE-LEAD, RIG-BLINK, RIG-EYE-DART |
| CQ-F3 | shot,episode | S3 | Does each beat show one emotion on at least 6 of 9 channels (eyes, face, body, voice, action, environment, colour, SFX, VFX), not eyes only? | one frame per beat; `shot-spec.json` emotion | F6, R-360 to R-379, EMO-CHANNELS, EMO-DECLARED |
| CQ-F4 | shot,episode | S2 | Is the face free of texture that hides it: no halftone, grain or bloom over eyes, nose or lips? | face close-ups | F4, F12, R-334, REND-TEXT-TEXTURE |
| CQ-F5 | shot,episode | S3 | Does the face stay on model (same face as the catalogue sheet) at every angle and expression? | `sheet-faces.png` against the catalogue face sheet | R-393, R-347 |
| CQ-F6 | shot,episode | S4 | Is any expression held so long that it reads as a mask? | consecutive face tiles | EMO-CHANGE, R-362 |

### X: text and captions (F4)

| ID | Applies | Sev | Question | Look at | Maps to |
|---|---|---|---|---|---|
| CQ-X1 | shot,episode | S2 | Can every piece of on-screen text be read in full, with nothing over it: no halftone, grain, bloom, shadow or character? | the frame at each text time | F4, R-334 to R-339, TEXT-LAYER, REND-TEXT-TEXTURE, REND-TEXT-CONTRAST |
| CQ-X2 | shot,episode | S2 | Is text on its own top layer, at least 36 px, contrast 4.5 to 1 or better, and still while it is read? | text frames, `shot-spec.json` | R-336 to R-338, TEXT-SIZE, TEXT-CONTRAST, TEXT-DWELL |
| CQ-X3 | shot,episode | S3 | Is there an Arabic caption on its own plate for every spoken line, in Thmanyah, shaped and ordered correctly, with no Latin punctuation inside the Arabic? | `captions/`, 4 caption frames | the owner 2026-10-23, EP-CAPTIONS, CAP-FONT, CAP-TIMING |
| CQ-X4 | shot,episode | S2 | Do faces and text stay inside the safe band of the 9:16 frame? | frames at the top and bottom edges | R-332, TEXT-SAFE, CAM-SAFE, EP-SAFEZONE |

### C: transitions and camera (F2, F3)

| ID | Applies | Sev | Question | Look at | Maps to |
|---|---|---|---|---|---|
| CQ-C1 | shot,episode | S2 | Does a change of drawing style or frame rate play over several frames, with a named cause and carrier, never as a split frame or a one-frame switch? | the frames on both sides of each transition | F2, R-320 to R-327, TRANS-COUNT, TRANS-FIELDS, TRANS-STYLE, TRANS-RATE, TRANS-CAUSE |
| CQ-C2 | shot,episode | S3 | Is every cut motivated (match on action, shape, light or sound), with no jump that confuses where we are? | each cut pair | R-325, R-326, TRANS-CARRIER |
| CQ-C3 | shot,episode | S1 | Is the camera frontal and flat (x, y, z, focal only): no yaw, no pitch, no wide-angle perspective on a figure? | raw frames | F9, R-331 |
| CQ-C4 | shot | S3 | Was the camera plan made before the drawing, with a thumbnail and a `why` for every shot? | `camera-plan.json`, `camera/` | F3, R-328 to R-330, CAM-PLAN, CAM-WHY |
| CQ-C5 | shot | S3 | Is the 180 line respected and the staging clear when two characters share a frame? | `camera/` overhead plan | R-333, ACTOR-ORDER |
| CQ-C6 | shot,episode | S3 | Is writing staged so the viewer sees the face the nib touches (card front-up under a top insert, or held to the lens)? | writing shot | R-388, PROP-FACE |

### P: process truth (the stall, stale outputs, blind gates)

| ID | Applies | Sev | Question | Look at | Maps to |
|---|---|---|---|---|---|
| CQ-P1 | shot,episode | S2 | Is every output fresh: `STATE.json` says every stage is `ok (fresh)` for the current inputs, and the trace frame count equals the video frame count? | `shot.py status`, `rig-trace.json` header, `mix-*.encode.json` | stale outputs (7cf8b90), R-398 |
| CQ-P2 | shot,episode,artbook | S1 | Did all gates run, none skipped, with no threshold, exemption or trace changed since the heal began (`heal.py guard` clean)? | `heal/snapshot.json`, `heal.py guard` | R-396, R-400, R-212 |
| CQ-P3 | shot,episode | S2 | Does the trace carry per-frame, per-finger data (not a max or one constant), so the gates could see the fault? | `rig-trace.json` fields against the schema | F13, R-398, trace gap |
| CQ-P4 | shot,episode | S3 | Were catalogue entries versioned (v2, changelog), never edited in place, and is each entry more than a picture? | `catalogue/`, `git`-free: file names and changelog lines | R-347, R-348 |
| CQ-P5 | shot,episode,artbook | S3 | Is the the owner view ADHD-friendly: one new tab in `previews/index.html`, hook first, short emoji-led blocks, big cards? | the tab HTML | CLAUDE.md, R-394 |

### A: art book sheets (the 8/10 note)

| ID | Applies | Sev | Question | Look at | Maps to |
|---|---|---|---|---|---|
| CQ-A1 | artbook | S2 | Is the character the same person on every sheet and angle: head shape, nose, hair or head tie, build, costume? | sheets 01 to 08 side by side | ARTBOOK-MATCH, R-347 |
| CQ-A2 | artbook | S3 | Are side views, back of head and anything hidden (a ring turned in the palm) drawn logically and with the right anatomy? | the side, back and hands sheets | art book note: Guide side head, Lead back of head and ring |
| CQ-A3 | artbook | S3 | Is the nose designed for every angle (profile, three-quarter, front), not borrowed from the front? | face sheet | F12, R-393, art book note: Guide nose |
| CQ-A4 | artbook | S4 | Is a head tie, scarf or cloth drawn as cloth (folds, tension, direction), not stiff? | the head sheet | art book note: Extra head tie |
| CQ-A5 | artbook | S3 | Is it black-and-white ink strokes only, with no tone, colour or workaround hack? | every sheet | ARTBOOK-INK |
| CQ-A6 | artbook | S3 | Was every sheet re-looked after a fix, including the ones nobody touched that share the changed code? | `artbook.py check` plus one crop per sheet | art book note: Han sheets not re-looked, R-401 |
| CQ-A7 | artbook | S3 | Was the fault fixed in the shared sheet code or module hook at the root, and the other characters re-rendered, not patched in one character only? | the diff list in `heal/rounds.jsonl` | art book note: shared sheet code, R-396 |
| CQ-A8 | artbook | S3 | Does every caption and label come from the bible module (no invented text), in Thmanyah, and fit its box? | `ARTBOOK-TEXT` output, 3 crops | ARTBOOK-TEXT, CAP-FONT |
| CQ-A9 | artbook | S3 | Are the proportions on sheet 01 the ones in the bible (heights, knees, head count) and the same on every later sheet? | sheet 01 against the bible | BIO-PROPORTIONS, art book note: shared proportions |

### E: episode (composing)

| ID | Applies | Sev | Question | Look at | Maps to |
|---|---|---|---|---|---|
| CQ-E1 | episode | S3 | Is there a story event in the first 3 s, and does the piece run 30 to 60 s? | `plan.json`, first frames | EP-HOOK, EP-LENGTH, R-063 |
| CQ-E2 | voice | S3 | Does each voice match its character's cast voice and style, with the accent carried by word habits where the model cannot do it? | voice manifest, casting | R-366 to R-368, VOICE-* |
| CQ-E3 | voice | S3 | Do the mouth shapes follow the viseme track and the line timing? | frames at spoken lines | EP-VOICE, viseme-track |
| CQ-E4 | episode | S2 | Does the end card carry exactly two Arabic choices and a comment prompt, readable, last frame verified? | `end/` card frames | EP-CHOICE, END-CARD |
| CQ-E5 | episode | S2 | Is every music and sound file licensed in the register, and is loudness near -14 LUFS with the voice ducked? | `audio` report | EP-MUSIC-LICENCE, EP-LOUDNESS, AUDIO-LICENCE |
| CQ-E6 | episode | S3 | Is the story continuous across shots: costume, props, light direction, time of day and place? | one frame per shot | CONTINUITY.md, R-347 |
| CQ-E7 | episode | S2 | Does every spoken line have a caption on screen exactly while it is spoken? | `captions/`, plan line timing | EP-CAPTIONS, CAP-TIMING |

### W: writing and voice (scripts, bibles)

| ID | Applies | Sev | Question | Look at | Maps to |
|---|---|---|---|---|---|
| CQ-W1 | writing,episode | S3 | Is every line short, in the character's own voice and habit, with no AI slop and no invented numbers? | the script | R-030, R-031, no-ai-slop, BIBLE-FIELDS |
| CQ-W2 | writing,episode | S3 | Is the Arabic correct (hamza, taa marbuta, harakat where needed, no Latin punctuation), proofread? | the script | arabic-english-proofreading, CAP-FONT |
| CQ-W3 | writing | S3 | Does each character stay extreme and different from the others on the matrix, with culture never the punchline? | `ENSEMBLE` matrix | R-032, R-045, ENSEMBLE-CONTRAST, BIBLE-CULTURE |
| CQ-W4 | writing | S3 | Does every character bible have origin, accent source and features, a drawable habit, a hand and an emotion profile? | `bible_check.py` | BIBLE-FIELDS, BIBLE-ACCENT, BIBLE-EMOTION, BIBLE-HAND |
| CQ-V1 | voice | S2 | Is the episode caption-only, with no TTS take and no voice file, until the owner chooses a new engine (Google Gemini is banned)? | `voice-manifest.json` | VOICE.md one-take rule |

## 📏 Scoring rubric (1 to 10, the owner's scale)

Start at 10. Subtract for every **no**: S1 minus 3, S2 minus 0.5, S3 minus 0.4, S4 minus 0.25. Round to the nearest whole number (half rounds down). Then cap: any S1 caps at 4, any S2 caps at 6, any S3 caps at 8. A score of 9 or 10 therefore needs no S1, no S2, no S3 and at most two S4.

| Score | What it looks like | Known anchor |
|---|---|---|
| 10 | Every question yes. Looks hand-drawn 2D, premium, alive, every hand, face and shadow right, plays smoothly. | Mix v5, shot 2, the art book after its fixes |
| 9 | Only polish left (one or two S4). the owner would not write a note. | |
| 8 | A few S3 or S4: good and liked, with thin spots he would mention. | art book first pass (8/10) |
| 6 | Works and is liked, but several S2 construction faults (shoulders, hands not connected, shadow holes, text covered). | Mix v2 (6/10) |
| 4 and below | An S1: 3D look, slideshow, stall, a touch rule broken. Rework, not polish. | Mix v3 (went 3D, stalled) |
| 1 to 2 | Does not render or does not play. | |

The critic may not give a score higher than the rubric allows from its own faults. `heal.py validate-critic` recomputes it and rejects a higher claim.

## 🎯 Taste signals behind the scores

What made Mix v5 a **10**: it looks hand-drawn 2D with ink and flat shapes; the camera cuts between a wide, a top insert on the hands and a close-up face; the hands are drawn as real hands with a pen grip; the writing appears under the nib on the face she touches; the nose and lips exist; the shadow is one clean shape; text is clean; the light changes with the beat; the preview is a video that plays.

What made Mix v2 a **6**: he liked the result and the world, but the arms were pale unconnected tubes, shoulders came from the chest, hands were stubs and the needle did not connect, the shadow had holes, halftone covered text and the face, the face was two dots with no nose or lips, and the camera stayed in one medium shot.

What made Mix v3 fail: it turned 3D (lit sculpture shading, smooth gradients on sleeves, dark faces with no features) and the live preview stalled.

Always: 2D not 3D; never a slideshow; hands; the writing face; no seams; lips and nose; no touch between unrelated men and women; every spoken line captioned; premium depth and light; plays smoothly.

## 📤 What the critic writes: `critic.json`

```json
{
  "target": "s2-partner-drain", "kind": "shot", "checklist_version": 1, "critic_model": "sonnet",
  "reviewed": {"sheets": ["review/sheet-hands.png"], "frames": [12, 60, 96]},
  "answers": [
    {"q": "CQ-H1", "answer": "yes", "evidence": "sheet-hands.png tiles 3 to 9: same four fingers and thumb"},
    {"q": "CQ-H4", "answer": "no", "evidence": "frame 96: ink on the back of the tag", "fault": "F-001"}
  ],
  "faults": [
    {"id": "F-001", "q": "CQ-H4", "severity": "S2", "frame": 96, "evidence": "ink on the back of the tag", "description": "writing shows on the face she is not touching"}
  ],
  "score": 6, "verdict": "fail"
}
```

Rules: every question that applies to the kind has an answer; every `no` has evidence and a matching fault; a fault with no checklist question uses `"q": "NEW"` and describes the new kind of fault in full (this becomes a lesson proposal). Frame numbers are 0-based video frames.
