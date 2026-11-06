# Character bible: <NAME>

Copy to `bible/series/<series>/characters/<id>/bible.md` (the folder name is the `id`, lowercase, no spaces). Fill every field. A blank is allowed only as `n/a because ...`. Write top to bottom (`guides/character-writing.md`): inner engine before culture, looks last. No length limit: a field may carry nested bullets, and long material goes to `voice.md` and `relationships.md` next to this file. Tag real-world facts V/S/M/J (`kb/README.md`).

**Machine format (checked by `uv run tools/bible_check.py <series-dir>`):** every field is one top-level line `- key: value`, with extra lines nested under it (two spaces, `- ` or a table row). Keep the key names exactly. `<...>` is a placeholder and counts as empty. HTML comments `<!-- feeds: X -->` mark the pipeline stage that reads the field and are ignored by the check.

## Which field feeds which stage

| Stage | Fields it reads |
|---|---|
| WRITE (scripts, outlines) | sections 0 to 4, 10 |
| SKETCH (art book, character design) | looks_link, silhouette_family, build, age_markers, wardrobe_layers, props_carried, catalogue_* |
| CATALOGUE (parts, poses, hands, expressions) | handedness, catalogue_poses, catalogue_expressions, catalogue_hands, catalogue_angles, garment_construction |
| RIG (`tools/rig_checks`, physics) | height_head_units, build, handedness, physics_hints, garment_construction, movement_signature |
| SPEC (emotion gate `EMO-*`, `kb/quality/gate-spec.md`) | section 7 emotion profile, tell, coping_habit |
| VOICE (one model, one take) | section 8 |

## 0. Identity
- id: <same as the folder name>
- name: <full name, Arabic first, then Latin>
- age: <number or range, and in-world birth date if it matters> <!-- feeds: SKETCH, RIG -->
- role: <role in the story: spine lead, genre register carried>
- arc_type: <positive | flat | negative>
- world: <world ids this character belongs to, comma separated; each must exist as worlds/<id>.md> <!-- feeds: WORLD-LINK -->
- languages: <home, anger, family, work>
- origin: <place, region, people, family; real or invented; named sources if real> <!-- feeds: VOICE, SKETCH -->
- culture_brief: <relative path to the culture brief, e.g. ../../culture/<id>.md> <!-- feeds: SKETCH, CATALOGUE -->
- culture_status: <closed | pending | open: closed = reader read it and the owner gave the final read>

## 1. Inner engine
- ghost: <one dated event, one witness, one lasting consequence>
- ghost_type: <loss | betrayal | shame | injustice | neglect | ambition | other, in one word>
- lie: <one sentence the character could say aloud; a belief, not a mood>
- want: <external goal>
- need: <the truth that answers the lie>
- cost: <what pursuing the want costs, and where it is shown>
- hidden_history: <not-for-the-screen life history, as long as you like>

## 2. Values and contradictions
- says_values: <what they say they value>
- does_under_pressure: <what they actually do>
- refuses: <what they will not do>
- contradiction_1: <belief vs behaviour, and its cause in the ghost>
- contradiction_2: <two loyalties>
- contradiction_3: <self-image vs how others see them>
- unrelated_trait: <one trait unrelated to origin or culture>

## 3. Extreme trait
- extreme_trait: <what they are extreme about, one thing>
- extreme_habit: <drawable action that shows it in a boring scene> <!-- feeds: SKETCH, CATALOGUE -->
- extreme_human: <how it stays human: where it is right, what it protects, what it costs them>
- extreme_wins: <what it wins>
- extreme_loses: <what it loses>
- extreme_limit: <which character sets a limit on it>

## 4. Mentality, interests, habits, tells
- mentality: <how they think: what they notice first, how they decide, what they fear, what they find funny>
- interests_plot: <interest that drives the plot>
- interests_private: <interest nobody on screen knows>
- habits_daily: <daily habit, time, place>
- skills: <skill, where learned, what it costs to use>
- bad_at: <what they are bad at>
- tell: <how they lie / are afraid / are in love; unique in the cast; one drawable line> <!-- feeds: SPEC, SKETCH -->
- coping_habit: <fight | flee | freeze | fawn | plan | joke | pray | withdraw | other> <!-- feeds: SPEC -->
- authority_attitude: <to authority and to the group>

## 5. Looks tied to personality
- looks_link: <one line per visible choice, each linking the look to a fact above (what the eye sees, why)> <!-- feeds: SKETCH -->
- silhouette_family: <circle | square | triangle | star | hook | tall line | low dome | tower | other: one word, unique in the cast> <!-- feeds: SKETCH, ENSEMBLE -->
- silhouette_note: <one sentence a thumbnail could be drawn from>

## 6. Physical profile for the rig
- height_head_units: <number, e.g. 6.5, and why> <!-- feeds: RIG, SKETCH -->
- height_cm: <number or n/a because ...>
- build: <build, weight, posture> <!-- feeds: RIG -->
- age_markers: <how age shows in posture, hands, wear> <!-- feeds: SKETCH -->
- handedness: <left | right | ambidextrous> <!-- feeds: CATALOGUE (hands), RIG -->
- movement_signature: <walk, sit, carry: one drawable sentence> <!-- feeds: RIG, ANIMATING -->
- physics_hints: <hair, cloth, tags, jewellery, mass, gait: what moves on its own, how heavy, how stiff, what lags> <!-- feeds: RIG -->

## 7. Emotion profile
How this character shows and hides each core emotion, per channel. Channels: eyes, face, body, voice, action, environment, colour, sfx, vfx (`kb/quality/gate-spec.md` EMO-CHANNELS). `shows` names at least 4 channels as `channel: how`. `hides` says what they do to conceal it; `leak` is the one thing that still escapes. Add further emotions (longing, relief, suspicion, dread, contempt, bitter-joy) as `### emotion: <name>` blocks. Feeds: SPEC.

### emotion: calm
- shows: <eyes: ...; face: ...; body: ...; voice: ...>
- hides: <...>
- leak: <...>

### emotion: joy
- shows: <eyes: ...; face: ...; body: ...; voice: ...>
- hides: <...>
- leak: <...>

### emotion: sadness
- shows: <eyes: ...; face: ...; body: ...; voice: ...>
- hides: <...>
- leak: <...>

### emotion: fear
- shows: <eyes: ...; face: ...; body: ...; voice: ...>
- hides: <...>
- leak: <...>

### emotion: anger
- shows: <eyes: ...; face: ...; body: ...; voice: ...>
- hides: <...>
- leak: <...>

### emotion: surprise
- shows: <eyes: ...; face: ...; body: ...; voice: ...>
- hides: <...>
- leak: <...>

### emotion: disgust
- shows: <eyes: ...; face: ...; body: ...; voice: ...>
- hides: <...>
- leak: <...>

### emotion: shame
- shows: <eyes: ...; face: ...; body: ...; voice: ...>
- hides: <...>
- leak: <...>

## 8. Voice
Long lines, scripts and dialect notes go in `voice.md`. Accent rule (CLAUDE.md): the accent matches the origin; `accent_source` names the origin place or people it comes from (it must share a word with `origin`), and `accent_features` lists at least two concrete features (sounds, words, rhythm), separated by `;`. Feeds: VOICE.
- voice_register: <Arabic register: fusha, Gulf, Levant, Egyptian, Maghrebi, mixed; register never used>
- accent_source: <the place or people the accent comes from; echoes `origin`>
- accent_features: <feature 1; feature 2; feature 3 (sounds, loan words, rhythm)>
- accent_tts_note: <how the accent is carried under the one-model, one-take rule, or "open: settled at the voice stage">
- voice_pace: <slow | measured | quick; pauses; what happens under stress>
- voice_pitch: <low | mid | high; range; breath>
- voice_signature_words: <words, address habits, titles, words from other languages>
- voice_refuses: <what they refuse to say>
- voice_under_stress: <what changes>
- voice_sample_1: <line written without the name>
- voice_sample_2: <line written without the name>
- voice_sample_3: <line written without the name>

## 9. Wardrobe, attachments, props
- wardrobe_layers: <garments inside out, one per line, with the layer order stated once> <!-- feeds: SKETCH, CATALOGUE -->
- garment_construction: <for each garment that moves: how it is held (pin, knot, seam, weight), what it hangs from, its length, whether it gets a physics chain> <!-- feeds: RIG, CATALOGUE -->
- props_carried: <objects they carry, each with its cultural connotation check and the hand that holds it> <!-- feeds: CATALOGUE -->

## 10. Relationships, arc, catalogue needs
- relationships: <one row per person>
  | Person | One word (A to B) | One word (B to A) | Secret held | Debt owed | Tests the lie / offers the need |
  |---|---|---|---|---|---|
  | <id> | <...> | <...> | <...> | <...> | <...> |
- arc_by_episode: <one line per episode: state of the lie, what changes>
  - <ep 1: ...>
- catalogue_poses: <first poses to build, in order: idle, walk, signature habit, tell, ...> <!-- feeds: CATALOGUE -->
- catalogue_expressions: <first expressions to build: the ones section 7 needs most> <!-- feeds: CATALOGUE -->
- catalogue_hands: <hand shapes to build first: the habit's grip, the tell, handedness> <!-- feeds: CATALOGUE -->
- catalogue_angles: <angles needed first: front, three-quarter, profile, back, from-above> <!-- feeds: CATALOGUE -->

## 11. Review record
- culture_reader: <seat, date, changes; or "pending">
- native_dialogue_check: <native speaker, language, date; or "pending">
- checks_run: <date and result of `bible_check.py`, then the human read by the owner>
