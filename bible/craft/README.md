# How to make a v5-grade shot

⭐ Reference: Mix v5 scored 10/10 (owner, 2026-10-23). Source, spec, trace and video: `reference/mix-v5/`. This page turns his notes F1 to F15 into a checklist. Rule ids link to `kb/rulebook.md`; the commands are in `pipelines/RUNBOOK.md`.

## 🧱 What a v5-grade shot is made of

- 9 s, 1080x1920, 24 fps, 4 beats, 3 transitions, 6 camera shots (`reference/mix-v5/shot-spec.json`).
- A **camera plan first** (`camera-plan.json`, 6 shot drawings in `camera/`), then the spec, then the build.
- A **catalogue** the shot reads from (`catalogue/characters/hero/`: model, poses, hands, face, props, writing, cameras, mass proxy, physics profile).
- A **2D look**: ink line, flat or cel fills, hard-edged flat shadows, painted layers with parallax.
- A **rig trace** exported by the renderer, and **masks** for text, shadow and line.
- Six gate outputs that all say PASS: `spec.out`, `rig.out`, `hands.out`, `look2d.out`, `preview.out`, `extras.out`, plus `mix-v5.render.json`.
- A recorded **video** that the preview plays.

## ✅ DO and ❌ NEVER, by stage

### 1. Writing
- ✅ Write the character in full before any drawing ([R-030](../../kb/rulebook.md)). ✅ Give each a drawable habit ([R-031](../../kb/rulebook.md)).
- ✅ Have a culture seat review each character ([R-041](../../kb/rulebook.md)). ❌ Never make culture the punchline ([R-045](../../kb/rulebook.md)).
- ✅ Put a hook in the first 3 s and make every line fit its beat ([R-063, R-064](../../kb/rulebook.md)).

### 2. Catalogue (look up first, build only what is missing)
- ✅ Look up the pose, expression, angle and prop in `catalogue/characters/<id>/index.json` before drawing ([R-318](../../kb/rulebook.md)).
- ✅ New pose or character: gesture, shapes, mannequin, sketch over, angles ([R-306](../../kb/rulebook.md)). ❌ Never rebuild a catalogued pose.
- ✅ Shoulders at the outer clavicle end, below a visible neck ([R-307, R-341, R-342](../../kb/rulebook.md)). ❌ Never put the shoulder in the middle of the chest (F7).
- ✅ One physics profile per character and prop; rubber stays rubber only where declared ([R-300, R-319](../../kb/rulebook.md)).
- ✅ Hands: 4 fingers and a thumb, authored per hand, mirrored only on purpose, with a layer order per angle ([R-383, R-385, R-392](../../kb/rulebook.md)).
- ✅ Two-sided props: front, back, and what is printed on each ([R-387](../../kb/rulebook.md)).
- ✅ Design nose and lips for every angle and expression, with visemes ([R-393](../../kb/rulebook.md)).
- ❌ Never edit an approved version; add v2 and a changelog line ([R-347](../../kb/rulebook.md)).
- ❌ Never store an entry as a picture only ([R-348](../../kb/rulebook.md)).

### 3. Camera (before any art or code)
- ✅ One camera plan, every shot with a `why` about feeling or information ([R-328, R-330](../../kb/rulebook.md)).
- ✅ Thumbnails and an overhead plan with the 180 line ([R-329, R-333](../../kb/rulebook.md)).
- ✅ Stage writing so the viewer sees the face the nib touches: card front-up under a top POV insert, or held to the lens ([R-388](../../kb/rulebook.md)).
- ✅ Frontal flat camera: x, y, z and focal only ([R-331](../../kb/rulebook.md)). ❌ Never yaw or pitch the camera, never add wide-angle perspective to a figure (F9).
- ✅ Keep faces and text inside the safe band ([R-332](../../kb/rulebook.md)).
- ❌ Never add a camera move "for parallax" ([R-330](../../kb/rulebook.md)).

### 4. Spec
- ✅ Fill every required field, or the spec gate refuses ([R-210](../../kb/rulebook.md)).
- ✅ At least 5 depth planes, a real camera move, one interaction per 3 s, a held beat only when declared ([R-205, R-206, R-208, R-209](../../kb/rulebook.md)).
- ✅ Name a transition, its cause and its carrier at every boundary ([R-320, R-321, R-323, R-324](../../kb/rulebook.md)). ❌ Never switch style or frame rate on a single frame (F2).
- ✅ Text on its own top layer, 36 px or more, 4.5:1 contrast, still while read ([R-334, R-336, R-337, R-338](../../kb/rulebook.md)). ❌ Never let halftone, grain or bloom cover text (F4).
- ✅ One emotion per beat on at least 6 of 9 channels, eyes first ([R-360, R-361, R-362](../../kb/rulebook.md)).
- ✅ Declare parent, anchor, contact points and layer order for every held object and garment ([R-350, R-352](../../kb/rulebook.md)).
- ✅ Declare shadows from a mass proxy with a flat hard edge ([R-317, R-358](../../kb/rulebook.md)).

### 5. Build
- ✅ 2D look: ink line and 2-3 flat tone steps ([R-380](../../kb/rulebook.md)). ❌ Never model volume with gradients or blur (F9).
- ✅ One connected silhouette: no ink line across elbow, shoulder, fingers or head-neck ([R-381](../../kb/rulebook.md)). ❌ Never outline each part (F11).
- ✅ Keep joints inside limits, elbows one-way, bones constant ([R-301, R-302, R-303](../../kb/rulebook.md)). ❌ Never clamp an unreachable target silently ([R-304](../../kb/rulebook.md)).
- ✅ Contacts are constraints: the child stays on the parent anchor every frame ([R-351](../../kb/rulebook.md)).
- ✅ Grip changes are blended over at least 4 frames ([R-386](../../kb/rulebook.md)). ❌ Never flip a pinch flag or contact kind mid-blend (F13).
- ✅ Ink grows under the nib, in the script direction, on the face she touches ([R-388, R-389, R-390](../../kb/rulebook.md)). ❌ Never draw a hidden face on the visible one (F14).
- ✅ Pen tip on the paper, layers in the catalogued order ([R-391, R-392](../../kb/rulebook.md)). ❌ Never draw a held object over the hand by overdraw (F15).
- ✅ Shadow shape from the mass proxy, one connected mask ([R-317, R-356](../../kb/rulebook.md)).

### 6. Trace and record
- ✅ Export the trace in the same run as the video ([R-398](../../kb/rulebook.md)). ❌ Never export the max over fingers or one constant for the whole clip: the gate then cannot see the fault (F13).
- ✅ Record once, on the GPU ([R-399, R-005](../../kb/rulebook.md)).

### 7. Gate
- ✅ Run every check, every time ([R-400](../../kb/rulebook.md)).
- ❌ Never loosen a threshold or edit a trace to pass; fix the root cause ([R-396](../../kb/rulebook.md)). A threshold moves only with a measured sample ([R-212](../../kb/rulebook.md)).

### 8. Review (the one human look)
- ✅ Check each F-number against the contact sheet: joints, hands, writing, seams, shadows, cuts ([R-401](../../kb/rulebook.md)).
- ✅ Sound off at phone size, then picture off ([R-379](../../kb/rulebook.md)).
- ❌ Never re-inspect by eye after a fix; re-run the gates ([R-012](../../kb/rulebook.md)).

### 9. Preview (what the owner sees)
- ✅ The recorded video, from one new tab in `previews/index.html`, opened on that tab at once ([R-382, R-394](../../kb/rulebook.md)).
- ❌ Never default to a live canvas painter (F10).
- ✅ ADHD-friendly: hook first, short emoji-led blocks, one idea per block, choices as big cards.

### 10. Feedback
- ✅ Record each note verbatim with the next F-number in `bible/feedback/` ([R-395](../../kb/rulebook.md)).
- ✅ Then: root cause (`kb/quality/rca-*.md`), rule, check, a row in the table below.

## 📋 Past failures and root causes (F1 to F15)

| F | What the owner saw | Root cause | Rule | Check |
|---|---|---|---|---|
| F1 | Arm moved out of human range (Mix v1/v2) | no joint limits or profile; the elbow flipped side in one frame at 7.96 s ([rca-biomechanics](../../kb/quality/rca-biomechanics.md)) | [R-300 to R-305](../../kb/rulebook.md), [R-319](../../kb/rulebook.md) | BIO-PROFILE, RIG-LIMITS, RIG-HINGE, RIG-SEGLEN |
| F2 | Style switch looked like a split frame; ones, twos, threes felt off | the style and rate switch was a beat index, so it happened on one frame ([rca-transitions-camera](../../kb/quality/rca-transitions-camera.md) RC-T1) | [R-320 to R-327](../../kb/rulebook.md), [R-378](../../kb/rulebook.md) | TRANS-COUNT, TRANS-FIELDS, TRANS-STYLE, TRANS-RATE |
| F3 | Camera angles were not designed before drawing | no camera design step; the camera was one formula (RC-T2) | [R-328 to R-333](../../kb/rulebook.md), [R-377](../../kb/rulebook.md) | CAM-PLAN, CAM-DUR, CAM-WHY, CAM-SAFE |
| F4 | Halftone dots covered the text | text drawn in the same pass as the dots, same colour (RC-T3) | [R-334 to R-339](../../kb/rulebook.md) | TEXT-LAYER, TEXT-CONTRAST, REND-TEXT-TEXTURE, REND-TEXT-CONTRAST |
| F5 | Fingers, needle, hijab and what is under it did not connect | no parent or contact declared; held objects joined by overdraw ([rca-construction](../../kb/quality/rca-construction.md) RC-B) | [R-304, R-310 to R-313](../../kb/rulebook.md), [R-350 to R-354](../../kb/rulebook.md) | ATT-DECLARED, ATT-LAYERS, ATT-FINGERS, RIG-ATTACH, RIG-LAYERS |
| F6 | Eye tracking good but feelings thin | no emotion field in the spec; the face rig was two scalars ([rca-emotion](../../kb/quality/rca-emotion.md)) | [R-360 to R-379](../../kb/rulebook.md) | EMO-* (SPEC), RIG-BLINK, RIG-EYE-LEAD, REND-COLOUR |
| F7 | Ugly body, shoulders from the middle | no build-up step; the shoulder joint set arbitrarily (RC-A) | [R-306 to R-308](../../kb/rulebook.md), [R-341 to R-349](../../kb/rulebook.md) | POSE-CATALOGUE, BIO-PROPORTIONS, RIG-SHOULDER, ATT-MODEL |
| F8 | Shadow was a projection of the drawing, with holes at the neck | shadow redrawn from the 2D silhouette, not the mass (RC-C) | [R-317](../../kb/rulebook.md), [R-356 to R-359](../../kb/rulebook.md) | SHADOW-MASS, SHADOW-CONTACT, RIG-SHADOW-HOLES |
| F9 | Mix v3 went 3D | the gate rewarded lit volume (light roles, penumbra, 3D proxy shadow) and nothing measured line art | [R-380](../../kb/rulebook.md) | LOOK2D-LINE, LOOK2D-RAMP, SHADOW-FLAT |
| F10 | Live preview stalled at about 4.65 s | per-frame canvas painting with blur passes and a wall-clock loop ([rca-playback](../../kb/quality/rca-playback.md)) | [R-382](../../kb/rulebook.md), [R-394](../../kb/rulebook.md) | PLAYBACK-VIDEO, PLAYBACK-AUTOPLAY |
| F11 | Seam lines at elbow, shoulder, fingers, head and body | each part drew its own outline | [R-381](../../kb/rulebook.md), [R-343](../../kb/rulebook.md) | SEAM-CROSS, SEAM-HEADNECK |
| F12 | Lips and nose not done | the face had no designed nose and lips, only a few scalars ([rca-emotion](../../kb/quality/rca-emotion.md) RC-E2) | [R-393](../../kb/rulebook.md), [R-365](../../kb/rulebook.md) | human look (face sheet 07), EMO-PROFILE |
| F13 | Her left hand glitched badly | discrete switches (pinch flag, contact kind) inside a continuous blend; a grip authored for the other hand; the trace hid it ([rca-hands-writing](../../kb/quality/rca-hands-writing.md) F13) | [R-383 to R-386](../../kb/rulebook.md) | HAND-TOPO, HAND-SWAP, HAND-SIDE |
| F14 | Writing appeared on the back of the card | the card had no faces; ink drawn on the camera face while she touched the other | [R-387 to R-390](../../kb/rulebook.md), [R-388](../../kb/rulebook.md) | PROP-FACE, WRITE-REVEAL |
| F15 | Right hand, pen and paper layered illogically | layer order was a draw-order accident; nib not tied to the paper | [R-391, R-392](../../kb/rulebook.md), [R-352](../../kb/rulebook.md) | NIB-CONTACT, LAYER-GRIP, RIG-LAYERS |

Mix v5 scored 10/10 after F13 to F15 were fixed. No F-note is open.

## 📋 Calm format failures and root causes (C1 to C13, E01 calm, 2026-10-25)

E01 calm v5 was approved the same day. These rows are not matched by the F-table test; ids are listed in [calm-format.md](calm-format.md) and `pipelines/CALM.md`.

| C | What the owner saw | Root cause | Rule | Check |
|---|---|---|---|---|
| C1 | Arabic letters break where words meet | the outline was a text stroke on the same glyphs as the fill; joined letters overlap, so the next glyph's stroke painted over the last | [R-403](../../kb/rulebook.md) | CAP-ARABIC-SHAPING |
| C2 | The narrator's voice is noisy: banned | the reference had been noise-gated; the old limits scored exact silence as the cleanest floor, and the pick ranked by it | [R-404](../../kb/rulebook.md) | VOICE-BANNED-REF, REF-QUALITY, TAKE-QUALITY |
| C3 | No sound on transitions; the 0:08 moment flat | a join was a picture only; sound was added per file, not per gesture | [R-405, R-406](../../kb/rulebook.md) | CALM-TRANSITION-SFX |
| C4 | The episode ended on a situation, not a hook | the end was one static card with no pace of its own | [R-407](../../kb/rulebook.md) | CALM-CHOICE-SFX, CALM-TWO-CHOICES |
| C5 | No sound for objects and pen strokes | no foley list derived from the shot specs | [R-408](../../kb/rulebook.md) | CALM-FOLEY |
| C6 | Mouths do not move with the words | `visemes` never ran in the daily run, crashed on the narrator, and measured the raw take; no gate held the mouth to the track | [R-409](../../kb/rulebook.md) | LIPSYNC-ACTIVE, LIPSYNC-SILENT |
| C7 | Single words flash by | word-by-word plates of 1 to 3 words | [R-410](../../kb/rulebook.md) | CAP-FULL-SENTENCE |
| C8 | «أري» had no meaning shown | the gloss showed for 0.5 s inside a short plate, and untagged words were not found | [R-411](../../kb/rulebook.md) | CAP-FOREIGN-GLOSS |
| C9 | The sound is bad on a phone | the mix was tuned on headphone numbers; the bed had no energy a phone plays; cues were set from the file's peak | [R-412](../../kb/rulebook.md) | AUDIO-DIALOGUE-CLARITY, AUDIO-MONO, AUDIO-PEAK |
| C10 | Characters appear with no introduction | no template, no rule, and no check for a first appearance | [R-413](../../kb/rulebook.md) | CALM-INTRO, INTRO-* |
| C11 | Only the glosses the owner pointed at existed | the glossary was built from his examples | [R-411](../../kb/rulebook.md) | GLOSSARY-COVERAGE, PLAN-FOREIGN |
| C12 | Captions still too fast to read | the reading time was the length of the voice | [R-414](../../kb/rulebook.md) | CAP-READ-TIME, CAP-READING-SPEED |
| C13 | The episode asked for "1 or 2" | card, hook, caption and `vote.py` were all built around digits | [R-415](../../kb/rulebook.md) | CALM-CHOICE, PLAN-CHOICE |

Also fixed the same day: captions over a face (F-001, [R-416](../../kb/rulebook.md), CAP-FACE-CLEAR), Hero's hands too big in close-ups ([R-419](../../kb/rulebook.md), ART-PROPORTION), flat prop inserts ([R-420](../../kb/rulebook.md), `insert_depth`). the owner on v3/v4: other than C10 to C13, perfect. v5: approved. No C-note is open.

## ⚠️ What the gates cannot see (human look)

- Per-frame style strength and frame-rate cadence at transitions ([R-321, R-322](../../kb/rulebook.md)), peak order of joint chains ([R-309](../../kb/rulebook.md)), squash and stretch volume ([R-316](../../kb/rulebook.md)).
- Lens versus parallax spread ([R-331](../../kb/rulebook.md)), the quality of the face sheet ([R-393](../../kb/rulebook.md)), hair under cloth.
- Voice by ear ([R-368](../../kb/rulebook.md)); lip sync by eye, the phone mix by ear, and the graffiti against the head in an intro ([R-409, R-412, R-413](../../kb/rulebook.md)).
- Most thresholds are uncalibrated defaults (gate-spec H). A pass is evidence, not proof; the look is the second witness.

## 📚 The six craft files

| File | Covers | Rules |
|---|---|---|
| [biomechanics.md](biomechanics.md) | joints, chains, balance, mass, physics profiles | R-300 to R-319 |
| [transitions-camera.md](transitions-camera.md) | transitions, camera plan, text legibility | R-320 to R-339 |
| [construction-catalogue.md](construction-catalogue.md) | build-up, catalogue, attachment, mass-proxy shadows | R-340 to R-359 |
| [emotion-channels.md](emotion-channels.md) | nine channels per feeling | R-360 to R-379 |
| [hands-props.md](hands-props.md) | hands, grips, two-sided props, writing | R-383 to R-392 |
| [calm-format.md](calm-format.md) | the calm format: pacing, intros, narrator, captions, sound, choices | R-403 to R-426 |

2D look (R-380), seams (R-381) and playback (R-382) are specified in `kb/quality/gate-spec.md` sections J and K.
