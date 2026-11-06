# RCA F6: feelings do not travel through the channels (Mix v2)

Trigger (owner, 2026-10-23, `bible/feedback/2026-10-23-mix-v2.md` F6): "Eye tracking is good; make it better: show feelings through the eyes, facial expression, body language, voice, action, environment, colours, SFX and VFX." Score 6/10.
Rules that answer it: R-360 to R-379 in `bible/craft/emotion-channels.md`. Grades: M measured by us, S source read, J judgement.
Evidence: `previews/index.html` (Mix v2 tab, read-only; line numbers below), `work/demo-v2/shot-spec.json`, `work/demo-v2/mix-v2.mp4`, frames in `work/rca/emotion/` (`sheet2.png`: face at 1.0, 3.7, 5.9, 8.8 s).

## Root cause in two lines

The spec and the rig have no concept of feeling: no `emotion` field per beat, so nothing tells eyes, face, body, voice, light, colour, sound or VFX what to express, and the face has two scalars (one brow, one mouth-open) that can only say surprise and mild worry. What is called "eye tracking" is the eyes following the head by 3 frames; there are no saccades, darts, lid or pupil changes, and no audio or emotional VFX exists in the render at all.

## RC-E1. The spec has no emotion field (the brief never asked)

Same mechanism as RC6 in `root-causes.md`: what the spec does not ask for, a coding agent does not build. `kb/quality/shot-spec.schema.json` beats require `treatment, treatment_reason, depth_planes, light, cast_shadows, interactions`. `treatment_reason` mentions feeling in prose only ("Action and shock", "calm") and is free text; nothing reads it. `characters[].parts` lists `brows`, `eyes`, `mouth` as parts with a pivot and `own_curve: true`, but the schema has no place for what those parts DO (expression keys, AUs, gaze target). The schema has no field for voice, SFX, VFX, colour, camera or per-character emotional profile at all.
Measured [M]: `grep -i "emotion\|feel\|mood\|shock\|calm" work/demo-v2/shot-spec.json` finds only two prose hits inside `treatment_reason` ("Calm = smooth ones", "Action and shock"); zero structured fields.

## RC-E2. The face rig is two scalars

`previews/index.html:704-722`: `BROW = KF([...])` is one scalar in [-0.6, 1]; `MOUTH = KF([...])` is one scalar in [0, 0.85]. Drawing (lines 779-790): brows are two quadratic curves moved up or down by `p.brow * .014` (tilted only when `p.brow < 0`); the mouth is an ellipse whose height and width grow with `p.mouth`. Consequences:
- No lip corners (AU12, AU15, AU20, AU23), no cheek raise (AU6), no nose wrinkle (AU9), no lid tighten (AU7), no lower-lid push, no upper-lid change (AU5), no asymmetry. Fear, anger, sadness, joy, disgust and contempt are not expressible; the only readable states are neutral, open-mouth surprise and brows up.
- Frame evidence [M, `work/rca/emotion/sheet2.png`]: at 1.0 s (calm), 5.9 s (dread, "her name") and 8.8 s (the grab) Hero's eye shape is the same white almond with the same round dark iris, the same highlight, the same small closed-mouth ellipse; only 3.7 s (the slam) differs, with an open mouth and raised brows. Beat 3 is named "her name" and is meant to be uncanny, and it reads as neutral.

## RC-E3. Eye tracking is head-follow only, and blinks are a fixed list

`previews/index.html:714-715`: `p.eyeX = clamp(TURN(t + 3/24) * 1.4, -1, 1); p.eyeY = clamp(NOD(t + 3/24) * 2.2, -1, 1);` The eyes are a function of the head's turn and nod 3 frames ahead. That is why "eye tracking is good": they lead the head. But:
- Eyes have no gaze target of their own: they never look at the bag tag when the tag matters; they never look away (aversion); no eye-line check exists. Iris offset is `p.eyeX * .009` (a 0.9 % of head unit shift), constant radius `.011`; no pupil/iris size change, no highlight change.
- No saccades or darts: the eye position is a smooth function of the head, so it never jumps.
- Lids: the lid is the same ellipse; height only changes in a blink (`op = 1 - p.blink`, line ~784). No lid shape per emotion.
- Blinks (line 707): `for (const b of [1.35, 4.15, 6.75, 8.5])`, a hard-coded list, triangular, half-width 0.075 s (0.15 s, 3.6 frames, symmetric). Measured from the list [M]: 4 blinks in 9 s = 26.7 a minute against 17 a minute at rest in the lab [S https://en.wikipedia.org/wiki/Blinking]; intervals 2.8, 2.6, 1.75 s. Not tied to any event: the shock at 3.42 to 3.52 s has no blink until 4.15 s, and the "her name" beat (5 to 7 s) has one blink at 6.75 s that is not at a thought change.

## RC-E4. Body motion is physics-timed, not feeling-timed

`LEAN`, `TA`, `NOD`, `TURN` (lines 698-702) are keyframe curves keyed to impacts and gestures (3.42 s slam, 5.17, 7.17), good timing (anticipation, overshoot) but with no declared effort quality. There is no per-emotion change in Weight, Time, Space or Flow: Hero's breath (`Math.sin(t * 2.4) * .006`) and head sway (`.03 * sin(t * 1.3 + 1)`, line ~713) are the same in every beat. Hands are driven by IK targets (`p.tA`, `p.tB`) for the grab; no tremor, hesitation or freeze channel. Her gestures read as events (startle, lean, grab) but not as a person who feels fear then curiosity: the lean at 5.95 to 7.9 is the same slow lean whatever she feels.

## RC-E5. Light and colour answer the plot, not the feeling

The spec does vary light per beat (b2 key jolted to +-26 deg and a flare rim `#ff7a4a`; b3 cold rim `#7fe0ff`; b4 fill `#5fc8e8`), and each source is motivated ("lamp flare on impact", "cold glow from the bag tag"). That is event motivation, and it works as punctuation. But the light block has no emotion reference and the colour has no per-emotion plan.
Measured [M] with `ffmpeg signalstats` on 270x480 frames at 1.5, 4.0, 6.0, 8.0 s: hue median 140, 139, 139, 138 (the same across the whole film, the brown world dominates); saturation mean 17.6, 23.8, 17.7, 15.1; luma mean 73.9, 83.9, 80.2, 80.8. So the colour script is nearly flat: only the slam beat raises saturation (+6), and the end of the film has the lowest saturation without a stated reason. The existing quality gate (`quality_gate.py render`) measures luma range, local contrast, depth and motion, and nothing about hue or saturation moving with a feeling.

## RC-E6. No sound, no emotional VFX

`ffprobe work/demo-v2/mix-v2.mp4` shows a single video stream and no audio [M]. The spec has no `voice`, `sfx` or `vfx` field, and the Mix v2 renderer has no audio code and no emanata or impact-frame code (the halftone of treatment B is a stylistic treatment, not an emotional VFX). Voice, SFX and VFX are therefore 3 of the 9 channels at zero. This is expected for a silent process demo, but the demo spec had no field that would have forced the question.

## RC-E7. Nothing is per character

Hero's bible has a Tell (pitch 1 tells in `previews/index.html`) and a culture, but the rig and the spec have no `emotion_profile`: no baseline blink rate, no display rule, no hidden-feeling leak channel. So a character who hides fear and shows it only in the hands cannot be written down, and a cast of different cultures will express the same feeling with the same face (R-372, section 1.2 of the craft file).

## RC-E8. No check ever looked

The gate suite (R-212, R-213) is calibrated to the four motion reels. No check reads emotion from the spec or the render, so a 6/10 "I like the result" passes with every channel's emotion undeclared. the owner's eye was the only detector again, as with RC8.

## What carries emotion today (honest list)

| Channel | State in Mix v2 | Evidence |
|---|---|---|
| Eyes | Head-follow, 3-frame lead, fixed blinks | lines 714-715, 707 |
| Face | 2 scalars, readable only for surprise | lines 704-705, 779-790 |
| Body | Event-timed (flinch, lean, grab), no emotion setting | lines 698-702 |
| Voice | None (no audio stream) | ffprobe |
| Action | Written as events, not as a result of a feeling | spec `actions[]` |
| Environment | Reacts to events (lamp swing, drawer) not to feeling | spec `interactions[]` |
| Light | Varies with events, motivated | spec `light` per beat |
| Colour | Hue constant, saturation +6 on the slam only | signalstats [M] |
| SFX | None | ffprobe |
| VFX | Halftone treatment only; no emanata, no impact frame | previews/index.html |

The good news is the eye lead and the event-timed body; the structure to carry feeling exists as parts with own curves. What is missing is the layer above: a declared feeling and a rule that spreads it to every channel.

## GATE PROPOSALS (exact diffs; not applied, the schema and tools are owned elsewhere)

Priority: P1 = do first, P2 next, P3 later. Thresholds are defaults [J] until calibrated on a set of liked reels with visible emotion.

### G-E1 (P1). Emotion per beat and channel track: schema diff

In `kb/quality/shot-spec.schema.json`, `beats.items.required` add `"emotion"` and `"emotion_track"`; in `beats.items.properties` add:

```json
"emotion": {
  "type": "object",
  "required": ["primary", "intensity", "shown", "cause"],
  "properties": {
    "primary": {"enum": ["calm","joy","sadness","fear","anger","surprise","disgust","contempt","shame","longing","suspicion","dread","relief","bitter-joy"]},
    "secondary": {"type": "string"},
    "blend": {"type": "object", "additionalProperties": {"type": "number", "minimum": 0, "maximum": 1}},
    "intensity": {"type": "number", "minimum": 0, "maximum": 1},
    "shown": {"enum": ["visible", "hidden"]},
    "leak_channel": {"enum": ["eyes","face","body","hands","voice","environment","colour"]},
    "peak_s": {"type": "number"},
    "cause": {"type": "string"},
    "character": {"type": "string"}
  }
},
"emotion_track": {
  "type": "object",
  "description": "One entry per channel that carries the feeling; >= 6 of 9, >= 4 non-face (R-361).",
  "properties": {
    "eyes":        {"type": "object", "required": ["gaze_target", "darts_per_s", "blink_per_min", "onset_s"]},
    "face":        {"type": "object", "required": ["aus", "onset_s"]},
    "body":        {"type": "object", "required": ["effort", "posture", "onset_s"]},
    "voice":       {"type": "object", "required": ["pace", "pitch_st", "energy", "style_text"]},
    "action":      {"type": "object", "required": ["from_emotion", "outcome"]},
    "environment": {"type": "object", "required": ["response", "interaction_ref"]},
    "colour":      {"type": "object", "required": ["hue_family", "sat", "value"]},
    "sfx":         {"type": "array", "items": {"type": "object", "required": ["at_s", "what"]}},
    "vfx":         {"type": "array", "maxItems": 1, "items": {"type": "object", "required": ["at_s", "what"]}}
  }
},
"emotion_change": {
  "type": "object",
  "required": ["from", "to", "bridge", "frames"],
  "properties": {"from": {"type": "string"}, "to": {"type": "string"}, "bridge": {"type": "string"}, "frames": {"type": "integer", "minimum": 6, "maximum": 24}}
}
```

In `characters.items.properties` add `"emotion_profile"` (shape in craft file section 4: `baseline`, `display_rules`, `hidden_feeling_channel`, `leak`, `never_uses`, `overrides`) and `"face_controls": {"type":"array","minItems":12}` (the 12 AU controls of R-365). Add `"audio_bed"` as an optional beat field only if the episode has sound. Add to `interactions.items.properties`: `"carries_emotion": {"type": "boolean"}`. Add to `light.properties`: `"serves_emotion": {"type": "string"}`.

### G-E2 (P1). Spec checks in `tools/quality_gate.py spec`

Add these checks (names `E1`..`E9`, each prints PASS or the failing beat id):

| Check | Rule | Fails when |
|---|---|---|
| E1 declared | R-360 | any beat lacks `emotion.primary` or it is outside the vocabulary |
| E2 channel count | R-361 | fewer than 6 channels in `emotion_track`, or fewer than 4 non-face |
| E3 order of arrival | R-362 | `eyes.onset_s` is later than `face.onset_s` or `body.onset_s`, unless `emotion.cause` contains the word "reflex" or the beat names `reflex: true` |
| E4 gaze target | R-363 | `eyes.gaze_target` empty, or `darts_per_s` is 0 for a beat longer than 0.5 s |
| E5 blink band | R-364 | `blink_per_min` outside the band for the declared emotion (table in craft file section 3.1) |
| E6 hidden feeling | R-373 | `shown: hidden` without a `leak_channel`, or leak channel equals the shown-channel set; blend weights not summing to 1 |
| E7 colour change | R-370 | consecutive beats with different `emotion.primary` and no hue or saturation or value change declared in `colour` |
| E8 emotion change | R-378 | consecutive different emotions with no `emotion_change` entry or `frames` outside 6 to 24 |
| E9 sfx and vfx | R-375, R-376 | `vfx` above 1 per beat or 3 per 9 s; no `sfx` entry in a beat with intensity >= 0.6; `light.serves_emotion` mismatch (R-371) |

Run on the current Mix v2 spec these must FAIL with E1 on 4 of 4 beats (a calibration case: the same way both 2/10 baselines must fail the render gate).

### G-E3 (P2). Face log from the renderer, and render checks

Renderer (`renderAt`) writes a sidecar `work/<ep>/face-log.json` with one record per frame: `{f, eyeX, eyeY, lidUpper, lidLower, irisR, blink, browL, browR, mouthOpen, cornerL, cornerR, headYaw, headPitch, gazeTarget}`. The gate then measures, from the log AND cross-checks on the video (the eye anchor pixel is known from the log, sample the eye-white luma and iris luma in a 24x24 crop):

| Check | Rule | Pass |
|---|---|---|
| R1 blink rate | R-364 | per-beat measured blinks per minute within the declared `blink_per_min` band, and interval standard deviation > 0.3 s |
| R2 blink length | R-364 | each blink 2 to 5 frames |
| R3 eye darts | R-363 | per-beat `darts_per_s` within +-50 % of declared; at least one eye saccade (iris speed above 3 times its median) in any 1 s window of a beat with intensity >= 0.3 |
| R4 eye independence | R-363 | the correlation between eye position and head yaw is below 0.9 (head-follow only gives 1.0 by construction) |
| R5 eye leads | R-362 | cross-correlation lag between eye and head is -2 to -4 frames in beats with a head move |
| R6 face energy | R-365 | at least 5 of the 12 face controls change value by >= 0.15 across the film; a 1-control face fails |
| R7 peak | R-374 | the frame with the highest per-frame change in the face log is within 3 frames of the declared `peak_s` |

The video cross-check (eye-white luma dips for a blink) is a proxy and is run on a crop; if it disagrees with the log, the build fails, which catches a log that does not match the picture.

### G-E4 (P2). Colour script from the render

For each beat compute mean hue, saturation and luma of the beat's frames (270x480, `ffmpeg signalstats` or the existing sampler) and write `work/<ep>/colour-script.json`. Check R-370: between consecutive beats with different `emotion.primary`, mean saturation or luma changes by >= 20 % relative, or key and fill hue by >= 30 degrees; and for each beat the measured values fall in the declared row's band. Output a colour-script strip PNG (one swatch per beat) into the preview tab, as Pixar does. Mix v2 baseline for calibration: hue 138 to 140, saturation 15.1 to 23.8, luma 73.9 to 83.9 (fails R-370 in 2 of 3 transitions, which is the expected result).

### G-E5 (P3). Audio and VFX checks (only when the episode has sound)

- `ffprobe` shows an audio stream; loudness of each beat (EBU R128 short-term, `ffmpeg ebur128`) rank-matches the declared energy; the quietest beat is not a declared-loud one; silence cue before the peak is >= 0.2 s (R-375). No second model touches the voice: pace is checked from the written line and syllable count only (words per second against the declared pace), never from a transcriber (machine rule: one model, one take).
- VFX: emanata and impact frames are listed in the spec; the render check finds 1 to 3 flat or inverted frames at the declared time (impact frame) by a frame-mean test; no VFX frame overlaps the text-safe region (ties F4).

### G-E6 (P3). Read-out card (R-379)

The preview tab for each episode shows a card per beat with the declared feeling, six small channel icons ticked from the spec, and a "does it read?" choice for the owner. It is the only human check, run once.

## Fix order for the next build (Mix v3)

1. Spec: write `emotion`, `emotion_track` and `emotion_profile` for the 4 beats before any drawing (G-E1, G-E2 pass).
2. Rig: replace the two scalars with the 12 AU controls plus gaze target, lids and iris size; give eyes their own target, darts and placed blinks (R-363 to R-365).
3. Body: per-emotion effort and posture settings added to `LEAN`, `TA`, `NOD`, breath and sway (R-366).
4. World: light, colour row, camera and environment response from the map (R-369, R-370, R-371, R-377).
5. Sound and VFX: bed, 1 to 3 hits per beat, one emotional VFX at the slam (R-375, R-376); voice remains open until the voice stage (accent conflict in CLAUDE.md).
6. Run G-E3 and G-E4 once; the owner does the read-out (R-379).

## Honest limits

- The face-log measurements verify that the declared eye and blink behaviour is in the render; they cannot verify that a viewer feels the emotion. Only R-379 does that.
- FACS and the emotion map are built from Western-sample research; Jack et al. 2012 and Matsumoto 2008 say expression and display rules vary by culture, so defaults can mislead a multicultural cast. The per-character override and the culture seat are the control.
- Blink and pupil numbers are lab values on live people; animation uses them as a floor for believability, not a target.
- Threshold values in G-E2 to G-E4 are [J], not calibrated on any reel set. Only one measured case exists (Mix v2).
- Frames were read by one reviewer at four timestamps; no frame-by-frame eye review was run (Owner exception: run once).
