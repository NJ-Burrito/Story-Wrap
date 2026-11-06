# Heal playbooks (fault class to root cause to fix)

Version 1, 2026-10-23. Read by `tools/heal.py classify` (the table below is machine-read: do not change its columns) and by every fixer. One class per kind of fault. The root causes are the ones already found in `kb/quality/rca-*.md` and `root-causes.md`; the rules are in `kb/rulebook.md`.

## 🚫 Forbidden fixes (every class, no exceptions)

| Kind | Why it is forbidden |
|---|---|
| `loosen_threshold` | A gate that moves to let a fault pass stops seeing it (R-396). A threshold moves only under R-212, with a measured sample, as a Lead-merged proposal, never inside a heal. |
| `edit_trace` | A trace is measured, not written. Hand-editing `rig-trace.json`, masks or gate outputs hides the fault from the gate (R-396). A trace changes only because its stage re-ran. |
| `hide_from_camera` | Cropping, covering, darkening, blurring, cutting away or re-framing so the viewer cannot see the fault leaves it in the data. Fix what is drawn. |
| `skip_check` | Dropping a check, a stage or `--skip-render-gate`, or adding an `exempt` entry. A gate that did not run is not a pass (R-400). |
| `widen_exemption` | Adding to `BIO-EXEMPT` or any waiver list to make an id pass. |
| `edit_approved_version` | Approved catalogue and sheet versions never change; add v2 and a changelog line (R-347). |
| `hand_edit_output` | Editing a video, sheet, report or trace output instead of the source that produced it. |

The files these touch are frozen in `pipelines/heal.json` (`protected_paths`); `heal.py round` refuses a round that changes one, and `heal.py guard` re-hashes them.

## 🗺️ Class table (machine-read)

Columns: `class | match (check ids, fnmatch, comma list; an exact id beats a wildcard) | questions | fix_in | fixer | rerun_from | rules`. `fix_in` is where the fix belongs. `fixer`: always Sonnet 5.5 (owner, 2026-10-23); the brief differs: creative faults get the drawing/writing crew member, tool faults the tooling one. `rerun_from` is the first stage to run again (shot stage name, episode stage name, or `artbook`).

| class | match | questions | fix_in | fixer | rerun_from | rules |
|---|---|---|---|---|---|---|
| BIOMECH | BIO-*,RIG-LIMITS,RIG-HINGE,RIG-SEGLEN,RIG-REACH,RIG-BALANCE,RIG-PEAK | CQ-B1,CQ-B6,CQ-B7,CQ-B8 | catalogue,scene | sonnet | build | R-300..R-319 |
| SHOULDER | RIG-SHOULDER,RIG-SHOULDER-RIDES,ATT-ANCHORS | CQ-B2 | catalogue,module | sonnet | build | R-307,R-308,R-341,R-342 |
| ATTACH | ATT-DECLARED,ATT-MODEL,ATT-FINGERS,ATT-HAIR,RIG-ATTACH,RIG-CONTACT-GAP | CQ-B5,CQ-H8 | spec,module | sonnet | spec | R-304,R-310..R-313,R-350..R-354 |
| SHADOW | SHADOW-MASS,SHADOW-CONTACT,SHADOW-SELF,RIG-SHADOW-HOLES | CQ-B4 | module,scene | sonnet | build | R-317,R-356..R-359 |
| SEAM | SEAM-* | CQ-B3 | shared_code | sonnet | build | R-381,R-343 |
| LOOK2D | LOOK2D-*,SHADOW-FLAT,SHADOW-SOFT | CQ-T1,CQ-C3 | shared_code,scene | sonnet | build | R-380 |
| MOTION-LIGHT-DEPTH | freeze_*,dead_*,low_motion_*,motion_*,moving_*,independent_*,uniform_*,direction_*,luma_*,local_*,soft_gradient_*,depth_*,parallax_*,cuts_* | CQ-T2,CQ-T8,CQ-T9,CQ-T10 | spec,scene | sonnet | spec | R-201..R-213 |
| HANDS | HAND-TOPO,HAND-SIDE,HAND-SWAP | CQ-H1,CQ-H2,CQ-H3 | catalogue,module | sonnet | build | R-383..R-386 |
| WRITING-FACE | PROP-FACE,WRITE-REVEAL,NIB-CONTACT | CQ-H4,CQ-H5,CQ-H7,CQ-C6 | catalogue,scene,camera_plan | sonnet | camera | R-387..R-391 |
| LAYERS | LAYER-GRIP,RIG-LAYERS,ATT-LAYERS | CQ-H6 | catalogue,scene | sonnet | build | R-352,R-392 |
| TEXT | TEXT-*,REND-TEXT-* | CQ-X1,CQ-X2,CQ-X4 | spec,scene | sonnet | spec | R-334..R-339 |
| TRANSITION | TRANS-COUNT,TRANS-FIELDS,TRANS-STYLE,TRANS-RATE,TRANS-CAUSE,TRANS-CARRIER,PLAN-TRANSITION | CQ-C1,CQ-C2 | spec,scene | sonnet | spec | R-320..R-327,R-378 |
| CAMERA | CAM-*,CAMERA-* | CQ-T5,CQ-T6,CQ-C4,CQ-C5 | camera_plan | sonnet | camera | R-328..R-333,R-377 |
| EMOTION | EMO-*,RIG-EYE-*,RIG-BLINK,RIG-FACE,REND-COLOUR | CQ-F2,CQ-F3,CQ-F6 | spec,module | sonnet | spec | R-360..R-379 |
| FACE-FEATURES | EMO-PROFILE | CQ-F1,CQ-F4,CQ-F5,CQ-A3 | catalogue | sonnet | build | R-393,R-365 |
| ACTORS | NO-TOUCH,ACTOR-*,MULTI-ACTOR,HANDOVER | CQ-T7,CQ-B9,CQ-H9 | scene,spec | sonnet | spec | R-350..R-354 |
| PLAYBACK | PLAYBACK-*,PREV-* | CQ-T3,CQ-P5 | preview | sonnet | gate | R-382,R-394 |
| STALE | GATE-INPUT,PREREQ,STALE-*,TRACE-STALE | CQ-P1 | rerun | sonnet | trace | R-398,R-399 |
| GATE-BLIND | *-NODATA,CHECK-ID,TRACE-GAP,GATE-INCOMPLETE | CQ-P2,CQ-P3 | shared_code,tool | sonnet | trace | R-396,R-398 |
| CATALOGUE | POSE-CATALOGUE,CATALOGUE-*,INIT-*,CAT-* | CQ-P4 | catalogue | sonnet | catalogue | R-318,R-347,R-348 |
| SPEC-FIELDS | SPEC-*,SCHEMA-* | CQ-T4 | spec | sonnet | spec | R-210 |
| CAPTIONS | CAP-*,EP-CAPTIONS | CQ-X3,CQ-E7 | episode_plan | sonnet | captions | R-334..R-339 |
| EPISODE-PLAN | PLAN-*,EP-LENGTH,EP-HOOK,EP-NOT-FOUND,ASM-* | CQ-E1,CQ-E6 | episode_plan,script | sonnet | plan | R-063,R-064 |
| EPISODE-AUDIO | EP-LOUDNESS,EP-MUSIC-LICENCE,AUDIO-*,LICENCE-*,TRANS-AUDIO | CQ-E5 | episode_plan | sonnet | audio | R-368 |
| EPISODE-END | EP-CHOICE,END-CARD,END-ASSEMBLED,EP-SAFEZONE,EP-RENDER-GATE | CQ-E4 | episode_plan | sonnet | end | R-334 |
| EPISODE-VOICE | EP-VOICE,VOICE-* | CQ-E2,CQ-E3,CQ-V1 | voice | sonnet | audio | R-366..R-368 |
| ARTBOOK-SHEET | ARTBOOK-* | CQ-A1,CQ-A2,CQ-A4,CQ-A5,CQ-A6,CQ-A7,CQ-A8,CQ-A9 | shared_code,module | sonnet | artbook | R-347,R-348 |
| BIBLE | BIBLE-*,WORLD-LINK,ENSEMBLE-CONTRAST | CQ-W1,CQ-W2,CQ-W3,CQ-W4 | script | sonnet | writing | R-030..R-045 |
| TOOL | TOOL-ERROR,USAGE,REVIEW-EMPTY | | tool | sonnet | init | R-396 |
| UNKNOWN | | | | sonnet | | R-395 |

`UNKNOWN` is the fallback. A fault that lands there (no check id matches and no critic question maps) gets a lesson proposal in `kb/lessons/proposals/` (new rule, new check, test idea) for the Lead to merge.

## 📘 Per-class playbooks

Each: what the fault is, the root cause already known, where the fix goes, the steps, what a fixer must not do.

### BIOMECH (F1)
- Root cause: joints had no limits or physics profile; the elbow flipped side in one frame (rca-biomechanics).
- Fix in: the character's physics profile and pose in the catalogue, then the scene keyframes.
- Steps: read the failing frame range in `rig.out`; find the joint and limit in the profile; fix the key pose or the profile; reach is clamped in the data, never silently in the renderer (R-304).
- Do not: widen a limit to fit the animation; clamp in the renderer.

### SHOULDER (F7)
- Root cause: shoulder joint set arbitrarily (middle of the chest) and then a fixed clavicle line that failed raised arms.
- Fix in: the model's `anchors.clavicle_L/R` and `rest_shoulder_y_px`; the module's shoulder rise.
- Steps: build up shapes, then clavicle line, then neck; shoulder at its outer end; rise follows R-308.
- Do not: move the clavicle line to the lowest arm frame; hide the chest under a garment to pass.

### ATTACH (F5)
- Root cause: no parent or contact declared; held objects joined by overdraw.
- Fix in: the spec (`parent`, `anchor`, `contact`, `layer order`) and the module attachment point.
- Do not: pull the object to the hand by a draw offset; declare a fake contact.

### SHADOW (F8)
- Root cause: shadow redrawn from the 2D silhouette, not the mass (hollow gradient circles, a cut at the neck).
- Fix in: the mass proxy in the module, a flat 2D cast shape from it, one connected mask.
- Do not: fill the hole with a patch; blur the edge to hide it.

### SEAM (F11)
- Root cause: every part drew its own outline.
- Fix in: the shared renderer line pass (one silhouette outline, inner lines only where the drawing wants a fold), then re-run every reference.
- Do not: thin the line until the check passes; colour the seam like the fill.

### LOOK2D (F9)
- Root cause: the gate rewarded lit volume and nothing measured line art; the renderer smoothed shading.
- Fix in: the look module (2 or 3 tone steps, hard shadow edge) and the scene's light; no smooth gradients on bodies.
- Do not: raise the hard-edge share by drawing a thin outline over a gradient.

### MOTION-LIGHT-DEPTH (RC1 to RC8)
- Root cause: a rigid sprite on one clock, one global light, flat plates, tween-only easing, no contacts, a spec that never asked.
- Fix in: the spec (planes with parallax, parts with lags, key/fill/rim, shadows, interactions) and the scene layers.
- Do not: add a fake camera drift to raise coverage (R-330); add noise.

### HANDS (F13)
- Root cause: discrete switches (pinch flag, contact kind) inside a continuous blend; a grip authored for the other hand; the trace hid it.
- Fix in: the hand model and grip entries in the catalogue; blend over 4 frames or more; author each hand.
- Do not: mirror a grip to save time; hold the hand off screen.

### WRITING-FACE (F14)
- Root cause: the card had no faces; ink drawn on the camera face while she touched the other.
- Fix in: the prop's front/back in the catalogue, ink in the card's own coordinates, and the staging in the camera plan (card front-up under a top insert, or held to the lens).
- Do not: flip the ink to the other side only at the cut.

### LAYERS (F15)
- Root cause: layer order was a draw-order accident; the nib was not tied to the paper.
- Fix in: the catalogued layer order per angle; nib contact point on the paper surface.
- Do not: overdraw the held object over the hand.

### TEXT (F4)
- Root cause: text drawn in the same pass as the dots, same colour.
- Fix in: the spec text layer (top, own pass, at least 36 px, 4.5 to 1, still while read).
- Do not: raise opacity of the dots; shrink the dots; move the text off the safe band.

### TRANSITION (F2)
- Root cause: the style or rate switch keyed to a beat index, so it happened on one frame.
- Fix in: the spec (cause, carrier, duration of the change, ramp) and the scene's ramped strength.
- Do not: add a flash on the cut frame to hide the switch.

### CAMERA (F3)
- Root cause: no camera design step; the camera was one formula.
- Fix in: `plan/camera.py` (thumbnail, `why`, overhead plan, 180 line), before any drawing.
- Do not: add a move for parallax.

### EMOTION (F6)
- Root cause: no emotion field; the face rig was two scalars.
- Fix in: the spec emotion per beat on 6 of 9 channels, eyes first; the face module.
- Do not: only turn up the colour or add VFX to compensate for a flat face.

### FACE-FEATURES (F12)
- Root cause: no designed nose and lips, only a few scalars.
- Fix in: the catalogue face sheet (every angle, every expression, visemes) as a new version.
- Do not: edit the approved face version in place; hide the nose with shadow.

### ACTORS (shot 2, no touch)
- Root cause: staging let two unrelated characters touch; actor order and occlusion not declared.
- Fix in: staging in the scene and the spec: an object between them, a hand that stops short, an `apart` contact kind.
- Do not: cut the frame at the moment of touch.

### PLAYBACK (F10)
- Root cause: per-frame canvas painting with blur passes and a wall-clock loop.
- Fix in: the preview tab (a recorded video, autoplay muted, controls).
- Do not: lower the canvas size to hide the stall.

### STALE (stale outputs, 7cf8b90)
- Root cause: a catalogue or module edit did not rerun the stages that read it, so the trace and the video were older than the sources.
- Fix in: nothing but a rerun from the first stale stage (`shot.py status` names it); stage hashes cover every catalogue file and module the shot resolves.
- Do not: copy a trace or video from another run; touch the file to refresh its date.

### GATE-BLIND (F13 trace gap)
- Root cause: the tracer exported a max over fingers or one constant, so the check could not see the fault.
- Fix in: the shared tracer (per-frame, per-finger, per-part data) and a new check proposal; then re-run every reference.
- Do not: edit the trace; relax the check that now sees the fault.

### CATALOGUE
- Fix in: add the missing pose, hand, face, angle or prop as a new version with a changelog line; look up before building.
- Do not: rebuild a catalogued pose; store a picture only.

### SPEC-FIELDS
- Fix in: the spec; fill every required field with a real value and a `why`.
- Do not: fill with placeholders.

### CAPTIONS, EPISODE-PLAN, EPISODE-AUDIO, EPISODE-END, EPISODE-VOICE
- Fix in: the episode `plan.json`, `shotlist.json`, audio and caption inputs named in `pipelines/COMPOSE.md`.
- Do not: re-voice a line (one take); use an unlicensed file; skip the render gate.

### ARTBOOK-SHEET (art book 8/10)
- Root cause: workarounds in one character's sheet and per-character gaps in the shared sheet code (side head, nose, head tie, back of head, hidden ring).
- Fix in: the shared sheet code or a module hook at the root; then re-render and re-look every character that uses it, including ones nobody touched (Han).
- Do not: patch one character only; edit an approved sheet version.

### BIBLE
- Fix in: the bible, culture brief or ensemble matrix; run `bible_check.py`; keep Arabic and English pairs in step.
- Do not: invent numbers; make culture the punchline.

### TOOL
- Fix in: the tool or its wiring, with a test that failed first.
- Do not: swallow the error and print PASS.

### UNKNOWN
- Steps: describe the fault in full (frame, sheet, what a viewer sees); find its root cause by reading the source, not by guessing; fix at the root; write a lesson proposal (new rule text, new check design, test idea). The Lead merges it.
