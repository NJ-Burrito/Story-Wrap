# Emotion channels: every feeling travels on every channel together

Trigger (owner, 2026-10-23, F6 on Mix v2, 6/10): "Eye tracking is good; make it better: show feelings through the eyes, facial expression, body language, voice, action, environment, colours, SFX and VFX."
Rules: R-360 to R-379. Root cause and gate proposals: `kb/quality/rca-emotion.md`. Companions: R-201 to R-214 (`kb/quality/root-causes.md`), F1 biomechanics, F2/F3 transitions and camera (`bible/craft/transitions-camera.md`), F7 body catalogue (`bible/craft/construction-catalogue.md`). Grades follow `kb/README.md`: S = source read, J = judgement (craft default, unsourced), M = measured by us. Sources marked "not fetched" were not opened in this session.

## 0. The principle

1. A beat has ONE named feeling (or one named blend). Without it no channel knows what to do.
2. The feeling is carried by at least 6 of 9 channels (eyes, face, body, voice, action, environment and light, colour, SFX, VFX); no channel contradicts it unless the contradiction is declared as a hidden feeling (section 4).
3. Channels do not start together. Eyes lead, then brows and head, then body, then the world answers (R-362). Ed Hooks: emotion leads to action; acting is reacting [S secondary listing https://www.betterread.com.au/book/acting-for-animators-book-9781032267517.do; check the book].
4. The feeling changes the physics of the whole shot (timing, light, colour, camera), not only the face.
5. Each character overrides the map with their bible tell, culture and display rules. A map entry is a default, never a verdict.

## 1. Research summary (what we take, with limits)

### 1.1 Eyes
- Blink: lab average about 17 a minute at rest, 2 to 10 s between blinks, 4 to 5 a minute during sustained looking such as reading; a blink lasts about 100 to 150 ms (3 frames at 24 fps), 100 to 400 ms in another source; closure over 1 s is a microsleep; blink rate is linked to stress, dopamine and possibly lying [S https://en.wikipedia.org/wiki/Blinking]. Lab values; animation exaggerates.
- Pupil: size indexes arousal and emotional content dilates it, but luminance confounds it (larger dilation on a dark background) [S https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9367726/]. Our stylised eyes use iris size and highlight size as the cue, and only when the light itself does not explain the change.
- Saccades and arousal: a 2023 study reports saccades start later from an emotional picture, in proportion to its arousal, so high arousal means the eye sticks to the cause [S search result only, https://frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2023.1297192/text, not opened]. Use: stick, then break hard (R-363).
- Culture: Easterners represent emotional intensity with distinctive dynamic eye activity [S https://pmc.ncbi.nlm.nih.gov/articles/PMC3358835 and https://www.gla.ac.uk/news/archiveofnews/2012/april/headline_230511_en.html]. A later York study found no cultural difference in perceptual similarity of whole-face images (Yan, Andrews, Young); the two do not directly conflict.
- Craft conventions, not sourced here [J]: the eye-line is the line from pupil to target and must hit it, an off-target line reads dead or deceptive; eye darts are 1 to 3 frame jumps of 2 to 6 % of eye width while thinking; the lower lid raised reads fear, tension or squint, the upper lid dropped reads tiredness or scorn.

### 1.2 Face
- FACS (Ekman and Friesen) codes muscle movements, not emotions. EMFACS-style mapping [S https://en.wikipedia.org/wiki/Facial_Action_Coding_System]: happiness AU6+12; sadness 1+4+15; surprise 1+2+5B+26; fear 1+2+4+5+7+20+26; anger 4+5+7+23; disgust 9+15+17; contempt R12A+R14A. We turn each AU into a rig control.
- Limits: Jack et al. 2012 (PNAS 109(19):7241): Western observers hold distinct facial movement sets for the six basic emotions, East Asian observers do not and lean on eyes and intensity; universality is contested [S https://pmc.ncbi.nlm.nih.gov/articles/PMC3358835]. Display rules: 32-country survey, in-group expression freer than out-group, individualist and collectivist cultures differ in endorsed expressivity [S Matsumoto, Yoo, Fontaine 2008, https://cris.haifa.ac.il/en/publications/mapping-expressive-differences-around-the-world-the-relationship-/]. Consequence: a face is a per-character, per-relationship signal; one stock "angry face" for the cast is a defect (R-372).

### 1.3 Body and action
- Laban effort: Weight (strong, light), Time (sudden, sustained), Space (direct, indirect), Flow (bound, free). Eight effort actions: punch (strong, direct, sudden), slash (strong, indirect, sudden), dab (light, direct, sudden), flick (light, indirect, sudden), press (strong, direct, sustained), wring (strong, indirect, sustained), glide (light, direct, sustained), float (light, indirect, sustained) [S https://en.wikipedia.org/wiki/Laban_movement_analysis; the table is the fetcher's derivation]. We use the four factors as the numeric body setting per emotion.
- Hooks: emotion leads to action, play an action against an obstacle. Every beat's feeling gets an action (R-367).

### 1.4 Voice
- Juslin and Laukka 2003 (104 voice studies, 41 music studies): emotions carry emotion-specific patterns of tempo, intensity, high-frequency energy, pitch level, variability, contour, onset shape and irregularity, consistent with Scherer [S https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4017128/ topic page]. Per-emotion directions were NOT retrieved: the voice table is [J]. Positive emotions are less well characterised [S https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7093353/].
- Project constraint: one TTS model, one take, no verifier (machine-wide rule). Voice emotion is a style direction and pace/pitch/energy target per line; the owner checks by ear. Mix v2 has no audio stream (`ffprobe`: video only).

### 1.5 Colour, light, environment
- Pixar colour script (Ralph Eggleston, Toy Story): colour, value and drama planned per sequence in chalk pastel; Lasseter saw colour intensify as emotion rose and mute in sombre moments; pastel and cheerful turns bleak and muddy for the sinister [S https://hyperallergic.com/610771/the-art-of-pixar-chronicle-books/ and https://www.moma.org/audio/playlist/192/2581]. We keep a colour-script row per beat.
- Pathetic fallacy: setting mirrors feeling [S not fetched, https://en.wikipedia.org/wiki/Pathetic_fallacy]. In our world the answer comes through motivated sources (lamp flicker, tide light, draught), never an unmotivated weather change.
- Colour meaning is cultural [J, culture seats check]. Colour grammar in section 3 is the series' own, taught by repetition, not claimed universal.

### 1.6 SFX and VFX as punctuation
- Emanata: the cross-shaped anger vein, sweat drops (size and number = intensity) [S https://public.websites.umich.edu/%7Eanime/info_emotions.html and https://www.japanesewithanime.com/2020/03/anger-mark.html]. A learned convention: an Arabic Reels audience may not read it, so it is used only when taught (R-376).
- Impact frames and mixed rates: `kb/guides/animation.md` section 3 (Spider-Verse, Hobie jacket on 4s, body on 3s) [S from earlier research, not re-fetched]. Use: a 1 to 3 frame impact frame on the emotional peak, with treatment B as the vehicle.
- Gap: no primary source retrieved for impact-frame practice or emotion-specific Spider-Verse styling. [J]

## 2. Rules R-360 to R-379

| ID | Rule | Check (where) |
|---|---|---|
| R-360 | Every beat declares one `emotion`: primary, optional secondary or blend, intensity 0 to 1, `shown` (visible or hidden), cause and `peak_s`. Neutral is declared as `calm` with its own settings, never absent. | SPEC: `beats[].emotion.primary` present and in the section 3 vocabulary. |
| R-361 | Channel coverage: at least 6 of the 9 channels carry the primary emotion in each beat, at least 4 of them non-facial. Feeling carried only by the face fails. | SPEC: `emotion_track` has >= 6 channel entries, >= 4 non-face. |
| R-362 | Order of arrival. Eyes lead by 2 to 4 frames, brows and head follow, body 2 to 4 frames after the head, the world's answer (light, SFX, VFX) 1 to 3 frames after the cause. Each channel has an `onset_s`; eyes are earliest unless the beat declares a reflex (startle: body first). | SPEC: onset order. RENDER: face log, eye move precedes head move. |
| R-363 | Eye-lines and eye life. Every beat names the gaze target and the eye-line hits it (within 1 iris width). Eyes never hold perfectly still over 0.5 s: micro-darts of 1 to 3 frames, 2 to 6 % of eye width, at an emotion rate (calm 0.3/s, thinking 0.8, fear 1.2 to 2). Gaze breaks are events with a cause. Eyes driven only by head turn (the Mix v2 build) is not enough: eyes own a target. | SPEC: `gaze.target`, `darts_per_s`. RENDER: eye-position log shows independent motion. |
| R-364 | Blink grammar. A blink is about 3 frames, closing faster than opening [S Blinking]. Blinks are placed, not random: one at each thought change and gaze shift, none during shock or intense attention, a cluster of 2 to 3 for confusion or suppressed tears, slow half-lidded for fatigue or trust. Rate bands per emotion in section 3. No two intervals in a beat equal. Lids and iris carry shape per emotion (upper lid level, lower lid push, iris size, highlight size). | SPEC: `blink_per_min` band and `lids`. RENDER: measured rate and interval spread inside the band. |
| R-365 | Face by action units. Each emotion is built from named FACS AUs mapped to rig controls: AU1 inner brow up, AU2 outer up, AU4 brow lower, AU5 upper lid raise, AU6 cheek raise, AU7 lid tighten, AU9 nose wrinkle, AU12 lip corner pull, AU15 corner depress, AU20 lip stretch, AU23 lip tighten, AU26 jaw drop. The face rig has these 12 controls, independent per side. One brow scalar and one mouth-open scalar can only express surprise and mild worry. Sides differ by a few percent. | SPEC: `face.aus` with intensity; character `face_controls` >= 12. |
| R-366 | Body by effort. Each emotion sets Laban Weight, Time, Space, Flow plus posture (spine, shoulders, head, chest, hands) and gait. Shoulders and head carry feeling before hands. F1 range limits and F7 construction apply. | SPEC: `body.effort` four values, `body.posture`. |
| R-367 | Feeling makes an action. Each beat names the action the feeling causes, the obstacle, and the outcome (completed, changed, aborted). An action with no feeling behind it needs the feeling named first. | SPEC: `action.from_emotion` linked to `actions[]`. |
| R-368 | Voice by prosody. Each line and breath has a style string and numbers: pace (relative to the character's base), pitch shift (semitones), energy, quality (breathy, tense, creaky, tremor), pauses. Silence is a setting. Pace and energy rank-match the map (sadness slower and quieter than calm; anger and fear faster). One model, one take; the check is the written direction, the ear check is the owner's. | SPEC: `voice` per beat; every dialogue line has a style string. |
| R-369 | Environment answers with motive: the world reacts through its own sources (lamp, draught, tide light, shadows, objects), recorded as a cause-effect interaction (R-209) that carries the emotion label. No unmotivated weather. | SPEC: >= 1 `interactions[]` with `carries_emotion: true`. |
| R-370 | Colour script. Each beat has a colour row (hue family, saturation, value, contrast, key and fill temperature) derived from the emotion. When consecutive beats differ in emotion, key or fill hue moves >= 30 degrees or saturation or value moves >= 20 % (defaults [J], to calibrate). The render's per-beat mean colour is compared with the declared row. | SPEC: `colour` row and delta. RENDER: per-beat mean hue, saturation, luma. |
| R-371 | Light as feeling. Key direction, hardness, size, colour and flicker are chosen for the feeling (low and hard for threat, soft and high for safety, face half in shadow for hidden intent). The beat's light block cites the emotion it serves. | SPEC: `light.serves_emotion` equals `emotion.primary` or `secondary`. |
| R-372 | Per-character override. The bible gives an `emotion_profile`: baseline blink rate, gaze habit, display rule per relationship tier (family, peer, authority, stranger), the hidden-feeling leak channel (from the Tell), what makes them cry or laugh, channels never used. The beat track is the map plus this override. The culture seat checks it against sourced research. | SPEC: character `emotion_profile`; track names the override. |
| R-373 | Hidden and mixed feelings. A hidden emotion is visible in exactly one declared leak channel and contradicted by the shown emotion in the others. A blend names which channel carries which part. An undeclared contradiction is an error. | SPEC: hidden/blend consistent with the channel map. |
| R-374 | Intensity scales every channel by the same 0 to 1 value with a per-channel cap. Small feelings use 1 to 2 channels strongly; big feelings spread and add VFX. At `peak_s` the most channels reach their maximum within 3 frames of each other. | SPEC: `intensity`, `peak_s`. RENDER: motion-energy peak near `peak_s`. |
| R-375 | SFX by feeling. Each beat names a room-tone bed (never dead silence unless declared), 1 to 3 punctuation sounds timed on the peak, the low or high frequency setting, and what is deliberately silent. Silence before a peak is a declared cue (pre-roll 0.2 to 0.5 s). Sounds tie to the interaction list. | SPEC: `sfx[]` with `at_s` and an interaction ref. |
| R-376 | VFX as punctuation, sparingly: at most 1 emotional VFX per beat and 3 per 9 s. Types: impact frame, halftone burst, speed lines, emanata, chromatic split, vignette pulse, focus rack. Emanata only after the series teaches them or with a local equivalent; VFX never cover text (F4). | SPEC: `vfx[]` count, type, text-safe zone. |
| R-377 | Camera by feeling (with F3): distance (close for intimacy or fear, wide for loneliness), angle (low power, high smallness, tilt unease), speed (slow push for dread, whip for shock). Chosen from the map before drawing. | SPEC: `camera.distance`, `angle`, `move`, reason = emotion. |
| R-378 | Transitions between feelings are designed (F2): each consecutive pair of different emotions names its bridge (blink, breath, sound, colour move, object) and 6 to 24 frames. Feelings do not snap, except a startle. | SPEC: `emotion_change` with `bridge`, `frames`. |
| R-379 | Read-out test. With the sound off at phone size each beat's emotion is identifiable from face and body; with the picture off, from voice and SFX [J]. the owner does it by eye and ear on the finished episode (run once); the machine compares declared against measured. | PROCESS: read-out card in the preview tab lists each beat's declared feeling; the owner marks mismatches. |

## 3. EMOTION MAP (defaults, [J] unless section 1 cites a source)

Blink bands are blinks per minute (lab rest 17, reading 4 to 5 [S Blinking]).

### 3.1 Eyes, brows, mouth, head (AUs from [S FACS page])

| Emotion | Eyes (gaze, darts, blink, lids, iris) | Brows | Mouth and cheeks | Head |
|---|---|---|---|---|
| Calm | Soft gaze on task, darts 0.3/s, blink 10 to 17, lids relaxed, iris mid | Neutral, slight asymmetry | Closed, neutral corners | Level, slow drift |
| Joy (6+12) | Gaze finds the other face, lower lid crinkled, blink 12 to 18, iris bright, big highlight | Slightly raised | Corners up, cheeks up | Tilt back or sideways, bounce |
| Sadness (1+4+15) | Gaze drops, long holds then slow look away, darts 0.1/s, blink 6 to 10 slow, upper lid heavy, wet highlight | Inner ends up and together | Corners down, chin tremor at high | Lowered, tilted |
| Fear (1+2+4+5+7+20+26) | Wide, whites show, snaps to threat and flicks away, darts 1.2 to 2/s, blink suppressed then burst 20 to 30, iris small | Raised and drawn together | Lips stretched back, jaw slightly dropped | Pulled back, chin down, flinch |
| Anger (4+5+7+23) | Hard stare held on target, 0 darts, blink 3 to 6, upper lid low, lower lid tight, iris small | Low, together, V | Lips pressed or bared, jaw set, nostrils flare | Forward, chin down |
| Surprise (1+2+5B+26) | Wide on the cause, no blink 0.3 to 0.6 s then a double blink, lids up | High, arched | Jaw dropped, round mouth | Snaps back 2 to 4 frames, then forward |
| Disgust (9+15+17) | Gaze flinches from the object, lids narrowed, one fast blink | Lowered, centre pulled | Upper lip up, nose wrinkle, chin raise | Leans away, turns |
| Contempt (R12A+R14A) | Slow half-lidded look down the nose, one slow blink | One brow up | One corner tight | Chin up, tilt |
| Shame | Gaze breaks and returns in darts 1/s, avoids the eye-line, blink cluster 2 to 3, lids low | Inner up, low energy | Lips pressed, small smile or tremble | Down and turned |
| Longing or wonder | Gaze held on the object past need, glint, large iris, slow blink, darts 0.2/s | Soft raise | Lips slightly parted | Tilts toward the object |
| Suspicion | Narrow, side-eye, holds then darts to a second point, blink 6 to 10 | One lowered, one neutral | Lips pressed | Slight turn, chin forward |
| Dread (fear + curiosity; Mix v2 beat 3) | Locked on the object, tiny darts away and back 0.8/s, blink withheld then one slow, iris small then wide | Inner up, outer slightly low | Lips apart, held breath, corner twitch | Leans in slowly while shoulders pull back |
| Relief | One long blink, eyes soften, blink 8 | Drops, releases | Exhale, corners flutter | Falls forward, settles |
| Bitter joy | Smile reaches the lower lid, gaze wet, unfocused, blink 8 | Inner up, one low | Corners up and tremble | Tilt |

### 3.2 Body and action (Laban: W weight, T time, S space, F flow)

| Emotion | Shoulders and chest | Hands | Posture and gait | Effort | Typical action |
|---|---|---|---|---|---|
| Calm | Low, loose | On the habit task | Upright, even steps | Light, sustained, direct, free | Continue the task |
| Joy | Lifted, open chest | Open, quick, wide | Bounce, spring | Light, sudden, indirect, free (flick, float) | Reach, hop, share |
| Sadness | Drop, round, chest caved | Slack | Slow, dragging, head down | Light, sustained, indirect, bound | Stop, withdraw |
| Fear | Up toward ears, arms guard | Clutch, tremor, hide | Crouch, small steps | Light, sudden, indirect, bound (dab, flick) | Freeze, recoil, shield |
| Anger | Broad, forward, tense | Fists, jabbing | Planted, heavy | Strong, sudden or sustained, direct, bound (punch, press) | Strike, slam, stand over |
| Surprise | Jolts up and back 2 to 4 frames | Fling out or to chest | Weight back | Light, sudden, direct, free | Flinch, grab |
| Disgust | Hunch away | Push away | Turn away | Strong, sustained, direct (press) | Push, avert |
| Contempt | Squared, still | Slow flick | Upright, chin up | Light, sustained, indirect, bound | Turn away slowly |
| Shame | Shrinking, folded | Hide in sleeves, fidget | Smaller, turned | Light, sustained, indirect, bound | Hide |
| Longing or wonder | Open, slight lift | Reach, stop short | Slow lean in | Light, sustained, direct, free (glide) | Approach, almost touch |
| Suspicion | Guard, one shoulder forward | Still, near object | Stillness, then small step | Strong, sustained, direct, bound | Watch, test |
| Dread | Pulls back while head leans in | Hover, stop short, tremor | Slow lean, locked knees | Light, sustained, direct, bound | Reach, stop, reach again |
| Relief | Falls, settles | Open, shaking | Sag then recover | Light, sustained, free | Sit, breathe |

### 3.3 Voice ([J] to be checked by ear)

| Emotion | Pace | Pitch | Energy and quality | Pauses |
|---|---|---|---|---|
| Calm | Baseline | Baseline, narrow | Normal, clear | Regular |
| Joy | Faster | Higher, wide | Louder, bright | Few |
| Sadness | Slower | Lower, flat | Quiet, breathy, trailing | Long, mid-sentence |
| Fear | Fast, broken | Higher, tremor | Tight, breath audible | Gasps, held breath |
| Anger | Fast or slow-clipped | Lower, hard attack | Loud or dangerously quiet | Sharp stops |
| Surprise | Instant intake | Jumps up | Short vowel, exhale | Sound before word |
| Disgust | Slower | Lower, nasal | Compressed | Short |
| Contempt | Slow | Low, drawl | Quiet, clipped | Long, deliberate |
| Shame | Slower, falters | Lower, shaky | Soft, mumbling | Restarts |
| Longing or wonder | Slow | Slightly higher, rising | Soft, breathy | Long |
| Suspicion | Slow, deliberate | Low | Quiet, even | Measured |
| Dread | Slow, held | Narrow, a little high | Hushed, breath-led | Silence before the word |
| Relief | Slower, exhale first | Falling | Breathy | One long exhale |

### 3.4 World

| Emotion | Light | Colour (series grammar) | Camera | SFX | VFX | Environment |
|---|---|---|---|---|---|---|
| Calm | Soft warm key, even fill | Warm mid, low contrast | Slow drift, medium | Room tone, small task sound | none | Gentle sway, dust motes |
| Joy | High key, warm, rim sparkle | High saturation, warm, bright | Slight push, bounce | Bright accents, rising pitch | Sparkles, flare | Objects bob, dappled light |
| Sadness | Low key, soft, blue-grey fill | Desaturated, cool, low value | Wide, static or slow pull back | Hushed room, distant drip | Gloom lines | Flame lowers, drip |
| Fear | Hard low-angle key, deep face shadow | Cold, high contrast, one hot accent | Tight, shake, tilt | Sub rumble, sudden silence, heartbeat | Vignette pulse, speed lines | Flicker, shadows lengthen, creaks |
| Anger | Hard red-orange key, rim from below | Saturated red-orange, high contrast | Push in, low angle | Low impact, bass, sharp hits | Anger vein, shake, impact frame | Lamp swings, objects rattle |
| Surprise | Flash, sudden bright key | Colour pop, hue jump | Punch-in, 1 to 3 frame shake | Hit, ring, silence after | Impact frame, burst | Objects jump, dust burst |
| Disgust | Greenish, flat | Sickly yellow-green | Turn away, cut | Wet or scrape | Wave lines | Haze |
| Contempt | Cool, one-sided | Cool, muted | Low angle, static | Dry, sparse | none | Still |
| Shame | Spot on her, dark around | Flush on face, rest muted | Pull away, off-centre | Muffled | Blush, sweat drop | Space narrows |
| Longing or wonder | Glow from the object, soft rim | One saturated accent in a muted frame | Slow push to the object | Soft tone, rising shimmer | Particles, bloom | Things lean toward it |
| Suspicion | Half-lit face, split | Muted teal-orange split | Slow creep, over the shoulder | Sparse ticks | Small glint | Details stay still |
| Dread | Cold glow from the cause, key dims | Cold teal accent in a warm world, saturation falls | Push 3 to 5 % of width per s | Bed drops, one low note, silence pre-roll | Subtle chromatic split, vignette | Lamp gutters, shadows lean |
| Relief | Key warms and widens | Colour returns, saturation rises | Settle, slow pull | Exhale, bed returns | Soft bloom | Draught calms |

## 4. Per-beat EMOTION TRACK format (in the shot spec, one per beat)

```json
"emotion": {
  "primary": "dread", "secondary": "curiosity", "blend": {"dread": 0.7, "curiosity": 0.3},
  "intensity": 0.7, "shown": "visible", "peak_s": 6.3,
  "cause": "the tag on the bag reads her own name", "character": "hero"
},
"emotion_track": {
  "eyes":   {"gaze_target": "bag-tag", "darts_per_s": 0.8, "blink_per_min": [3, 6], "blink_events": [{"at_s": 5.4, "kind": "slow"}], "lids": "lower-lid-raised", "iris": "small-then-wide", "onset_s": 5.05},
  "face":   {"aus": {"1": 0.5, "4": 0.2, "5": 0.4, "26": 0.2}, "asymmetry": 0.05, "onset_s": 5.15},
  "body":   {"effort": {"weight": "light", "time": "sustained", "space": "direct", "flow": "bound"}, "posture": "shoulders pull back, head leans in", "onset_s": 5.25},
  "voice":  {"line": null, "breath": "held", "pace": "slow", "pitch_st": 0, "energy": "soft", "style_text": "hushed, breath-led, stops mid-word", "silence_s": [5.1, 5.6]},
  "action": {"from_emotion": "reaches for the tag, stops short, tries again", "obstacle": "fear of her own name", "outcome": "aborted-then-completed"},
  "environment": {"response": "lamp flame gutters, shadows lean toward her", "interaction_ref": "tag glow -> cold light on Hero"},
  "colour": {"hue_family": "teal accent in warm world", "sat": "falling", "value": "falling", "key_temp": "neutral", "fill_temp": "cold"},
  "sfx":    [{"at_s": 5.0, "what": "bed drops to silence"}, {"at_s": 5.05, "what": "low single note"}],
  "vfx":    [{"at_s": 5.1, "what": "slight chromatic split on the tag"}],
  "camera": {"distance": "close", "move": "push 4%", "reason": "dread"}
},
"emotion_change": {"from": "shock", "to": "dread", "bridge": "one slow blink and the bed dropping", "frames": 12}
```

Per-character override (character bible, mirrored in `characters[].emotion_profile`):

```json
"emotion_profile": {
  "baseline": {"blink_per_min": 12, "gaze_habit": "avoids eye contact with authority"},
  "display_rules": {"family": "open", "peer": "guarded", "authority": "masked", "stranger": "polite"},
  "hidden_feeling_channel": "hands",
  "leak": {"fear": "hands: fingers stop, coat tags go still", "shame": "blink cluster"},
  "never_uses": ["voice raise"],
  "overrides": {"fear": {"face": "calm", "eyes": "calm", "hands": "tremor 1.0", "body": "stillness"}}
}
```

Worked example, a character who hides fear and shows it only in the hands: `shown: "hidden"`, leak = hands. Face and eyes use the `calm` row (blink 10 to 17, soft gaze), voice stays at baseline pace, the hands stop the habit task and tremble at the fingertips, and the coat tags (rig part, lag 3) stop for 6 frames. Light and colour still answer the real feeling (cold shift, shadows lean), so the viewer sees the world know what she hides. R-373 checks exactly one channel leaks and the rest hold the shown feeling.

## 5. Applying it to a character with a culture and a tell

1. The bible Tell is the default leak channel (pitch-1 cast tells in `previews/index.html`: Salma lifts her fingers off the strings, Hagop turns a radio knob, Jamil sands harder, Marcos loses the beat).
2. Display rules per relationship tier come from the culture seat's sourced notes, not from stereotype. The research says rules vary with in-group and out-group and across individualist and collectivist cultures (Matsumoto 2008), and that eye-region and intensity cues differ in some East Asian samples (Jack 2012). Never assign a cultural face as a fixed rule.
3. No two characters in one scene use the same channel set for the same emotion (contrast matrix, `kb/guides/character-writing.md` section 9).

## 6. Open questions

- Primary sources for eye-line, eye-dart and lid conventions (Williams, Hooks, Blair), impact-frame practice and Spider-Verse emotion styling: not retrieved. Marked [J].
- Juslin and Laukka 2003 per-emotion vocal directions: craft defaults until the paper's table is read.
- R-370 colour-delta thresholds need more than the 4 reels to calibrate.
