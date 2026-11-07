# 🕯️ The calm-format pipeline, end to end

⭐ **Reference: E01 calm v5** (`work/episodes/E01C`, commit `679437b`, **APPROVED by the owner 2026-10-25**; critic 9/10, 26 episode checks, 812 tests). Every step below is what that episode was built with. The next episode follows this page and needs no repeat notes. Notes C1 to C13 are in `bible/feedback/2026-10-23-mix-v2.md` (verbatim); the creative DO and NEVER list is `bible/craft/calm-format.md`; the rules are `kb/rulebook.md` section 15 (R-403 on).

🧠 **Calm format = his pacing, our art** (`CLAUDE.md` "Calm format"). Calm shots of about 3.7 s, one subject per frame, a narrator who carries the story, short character lines, a fixed wrapper, our 2D ink art and the cast of the world-a series. Length is whatever suits the story (E01C is 127 s).

One command builds a day: `uv run tools/daily.py run` ([DAILY.md](DAILY.md)). This page explains what each of its stages is made of, so a fault is fixed at the step that owns it.

## 🧭 The steps in one table

| # | Step | Tool | Reads | Leaves | Note |
|---|---|---|---|---|---|
| 0 | Votes | `ig.py comments`, `vote.py tally/next` | the last post | `decision.json`, `next-brief.md` | C13 |
| 1 | Script + plan | writer (headless Sonnet) | `next-brief.md`, series bible, glossary | `script.json`, `calm-plan.json`, `caption.txt` | C2, C8, C10, C11, C13 |
| 2 | Plan check | `calm_compose.py plan` (validate) | the two files | `timeline.json` (after the voice) | C3, C4, C10, C12 |
| 3 | Voice | `voice.py manifest, gate, voice --go, measure, visemes` | `script.json`, `casting.json` | `work/voice/<ep>/L*.trimmed.wav`, `visemes/` | C2, C6 |
| 4 | Shots | `calm.py make` templates, `shot.py all` | the plan, kits, catalogue | `work/shots/<ep>-<scene>/`, cards | C4, C6, C10 |
| 5 | Sound design | `calm_sfx.py synth, build, check` | timeline, plan, shot specs | `sfx.json` | C3, C4, C5 |
| 6 | Captions | `calm_compose.py captions` | takes, glossary, shot traces | `captions.json`, `plates/`, `hud.json` | C1, C7, C8, C11, C12 |
| 7 | Mix | `calm_compose.py audio` (`calm_mix.py`) | takes, `sfx.json` | `mix.wav`, `audio/stems/` | C9 |
| 8 | Assemble | `calm_compose.py assemble` | shots, cards, plates, mix | `episode.mp4` | C3, C4, C10 |
| 9 | Gate | `calm_compose.py gate`, `audio_checks.py check` | everything above | `gate/report.json` | all |
| 10 | Critic + heal | critic and healer agents | the report, frames | `heal/critic.json` | F-notes |
| 11 | Preview | one tab in `previews/index.html` | `episode.mp4` | the tab, opened on it | 4-tab rule |
| 12 | Post + harvest | `ig.py publish --go`, 12 h later step 0 | gates PASS, critic 9+ | `post.json` | audience loop |

🔁 A rerun skips every step whose status is ok and whose outputs exist (`work/daily/<ep>/STATE.json`); `--force STAGE` reruns one.

## 🛡️ Safe fixing: a cheap check between every two steps

Why this exists (owner, 2026-10-25): a fault found after the final render costs the whole render again. So every expensive step is **guarded by the cheapest check that can see its faults**, run first, offline, in seconds. A fault is fixed at the step that owns it, then only that step and the ones after it rerun.

| Before this step... | ...run this first (seconds, no render, no model) | It catches | Fix place |
|---|---|---|---|
| voice (8 to 15 min of GPU) | `calm_compose.py plan <ep>` validation and `gloss.py` | PLAN-* (intros, transitions, choice, gloss, tashkeel, recap, scene length), FOREIGN-TAG, GLOSSARY-COVERAGE | the writer's plan or script |
| voice | `voice.py manifest <ep>` then `gate <ep>` | VOICE-CAST, VOICE-STYLE, VOICE-TEXT, VOICE-REF, REF-QUALITY, VOICE-BANNED-REF | casting, text |
| shots (about 1 min per shot) | `calm.py validate <shot-dir>` | CALM-* template and parameter faults | the plan params, a kit |
| shots | `voice.py visemes <ep>` done and not stale | LIPSYNC-NO-TRACK, LIPSYNC-STALE-TRACK | rerun visemes |
| captions | `calm_intro.py list <plan>` | a first appearance with no intro | the plan |
| mix and assemble | `calm_sfx.py check <ep>` | CALM-TRANSITION-SFX, CALM-FOLEY, CALM-CHOICE-SFX, CALM-INTRO-SFX | the plan's cut type, `calm_sfx.py` |
| assemble (NVENC render) | `calm_compose.py captions <ep>` checks, then `audio_checks.py check <ep>` | CAP-* checks, AUDIO-* checks | captions, `calm_mix.PRESETS` |
| post | `ig.py publish <ep>` (dry run) | missing gate, critic below 9, no token | the earlier step |

**Measurement before a fix**: read the failing check's own numbers (every `FAIL [ID]` prints them), change one cause, rerun the one step. A threshold moves only with a measured sample and a note in `kb/quality/gate-spec.md` (R-212, R-396). **Testing before the commit**: the suite stays green (`uv run --with pytest --with numpy --with pillow --with scipy --with jsonschema --with opencv-python-headless pytest tools/tests -q`; 812 passed on E01 calm v5). **Limits** of a heal loop: `pipelines/heal.json`, at most 2 rounds for the daily run ([HEAL.md](HEAL.md)); each healed fault goes to `kb/lessons/ledger.jsonl`.

✅ Since 2026-10-25 `daily.py` runs a verify after every stage, an early animatic preview (real voice, timeline, captions and mix; no shot drawn) before the shots, and reruns only the stages whose input hashes changed: [STAGE-GATES.md](STAGE-GATES.md). The ladder above is still the order by hand.

---

## 1. Script and plan (the writer)

**Inputs**: `next-brief.md` (from E02), the series bible, `glossary.json`, `bible/series/<series>/voices/casting.json`. **Outputs**: `script.json` (voice.py lines), `calm-plan.json` (schema in [DAILY.md](DAILY.md)), `caption.txt`.

- **Narrator and characters (format v2, the owner 2026-10-28, from E03; replaces C2's "narrator carries half")**: the CHARACTERS carry the story in their own cast voices: 10 to 15 spoken character lines (`speaker` = a character id from `casting.json`), at least 2 speakers, some answering each other (`DIALOGUE-LINES`, `calm_compose.dialogue_problems`). The narrator (`speaker: "narrator"`, «أنتم», present tense) speaks ONLY the recap (the hook and the first scene's story-so-far clause), short night links (the scene carries `"role": "link"`, one sentence of at most 14 words) and the vote question; it is at most 25 % of the placed voice time (`NARRATOR-SHARE`), while all placed voice, any speaker, covers at least 0.85 of the runtime (`CALM-VOICE-COVERAGE`). `text` has no tashkeel (it is the caption); `tts_text` carries the full marks. A line is at most 8 s aloud; a dialogue scene may run up to about 10 s (`MAX_SCENE_S`).
- **Events (format v2)**: 2 to 5 scenes carry `"event": "<one sentence of the visible action>"` (`EVENTS`). An event is SHOWN as its own action scene on a template that shows the action (`push_in`, `parallax_pan`, `two_shot`, `insert`, `insert_depth`), never `reaction_closeup` or `hold_breathe` alone. Every night has at least one: the `consequence` block is the first night, `story` + `cliff` the second, or give scenes your own `"night": "<id>"`. Looking at an empty box is not an event. A prop, pose or set piece the kits lack is created (art-book style, added to the catalogue) and listed in the plan's `needs_art`: `[{"what": "...", "for_scene": "s04"}]`; it is never avoided by telling it in narration.
- **Blocks**: `consequence` scenes first (before the day card), then `story`, then `cliff`.
- **Recap**: none in E01; the episode opens on its story at 0 s with the first story event in the first second. From E02 the `recap` key is required (`RECAP_FROM_EPISODE = 2`; `PLAN-RECAP`, `CALM-RECAP-FIRST`, `CALM-WRAPPER`).
- **Hook, spoken recap, story so far (DESIGN.md 2.1, 2.2; from E02)**: the recap card is SPOKEN. Plan key `hook` {pattern 1..10 from DESIGN.md section 3, line}: the line is a narrator line in `script.json`, the first spoken line of the episode, said over the recap card, one sentence about the vote in the plural «أنتم», first plate at most 8 words, no greeting, no «تابعوا», no series name alone, and about 2.4 s aloud so the card keeps its 3.0 s cap (`PLAN-HOOK`, `CALM-HOOK-3S`). The first scene's narrator line carries one clause of story so far that names the heroine (`PLAN-SOFAR`). The series strip «الحلقة N · the series» sits on the HUD for the first 3 s and as the recap card's `tag` (`CALM-HUD`); `calm_compose.recap_card_params(plan)` builds the recap card's parameters.
- **Intros (C10)**: plan key `intros`, one per character's first appearance as a person IN THE WHOLE SERIES (the owner 2026-10-28): a character any earlier episode's `intros` introduced (E01C counts as E01) is never introduced again, and `PLAN-INTRO` rejects it (`calm_intro.introduced_before`, from E03). `name` at most 2 words, `tag` at most 6 words, no tashkeel (`PLAN-INTRO`). **Coverage:** intro_freeze seconds are excluded from the `CALM-VOICE-COVERAGE` count, like a title card: placed voice seconds / (runtime - intro seconds) (`qg_checks.check_calm_declared`, plan key `intro_s`); every other silent gap still counts against the 0.85 floor. **Deferral:** an episode may defer a character's intro to a later episode only by recording it in plan key `intros_deferred` [{character, to_episode, reason}] (`calm_intro.deferred_intros`); an unrecorded missing intro is still refused.
- **Cultural words (C8, C11)**: use a character's own-language word only if it is in `glossary.json`, or tag it in the script line (`foreign`: word, language, `meaning_ar`). Every such word is glossed, not only the ones the owner pointed at (`PLAN-GLOSS`, `PLAN-FOREIGN`).
- **Written object (C3)**: `written` {line W01, template `object_card`, heading}: about 0:08 an iris opens onto a brass plate with a horn; the narrator reads the engraving in a different, flat register (the line's `tone`).
- **Choice (C4, C13; prompt replaced 2026-10-25, DESIGN.md 5.2)**: `choice` has the question, two **short phrases** (at most 4 words, no digits, the option labels), and four narrator lines (`question`, `choice1`, `choice2`, `hook`). From E02 the closing `hook` line and the card prompt (default «ما رأيكم، ولماذا؟») are an OPEN QUESTION about the story with a reason («أين تضعون الحقيبة الليلة؟ قولوا لنا لماذا.»): no digit, none of «اكتبوا اختياركم», «علقوا», «صوتوا», «اختاروا», «شاركوا», «اذكروا», «اضغطوا», «تابعوا» (`PLAN-PROMPT`), and `variants` {"1": [...], "2": [...]} lists at least 8 other wordings per side for `vote.py` (`PLAN-VARIANTS`). `split` names the two close-ups for the top half. `PLAN-CHOICE`, `CALM-CHOICE`.
- **Transitions (C3)**: `transitions` names a cut type per join (`wind whoosh page ink ink-fade door close horn bell flash steps freeze`); no declaration means the default by template.
- **Reading pause (C12)**: `hold` per scene, 0 to 1.5 s, is computed by the planner when a caption would be up for less than a reader needs (`PLAN-HOLD`).
- **Length**: the story sets it. Floor 25 s (`CALM-LENGTH`), soft warning over 92 s that the owner confirms, no ceiling; at least 4 scenes (`PLAN-SCENES`).

**Gate before moving on**: the plan validation above. **Fix place**: the writer; the healer never edits `script.json`.

## 2. Voice first (C2, C6)

**Inputs**: `script.json`, `casting.json`. **Outputs**: `L*.wav`, `L*.trimmed.wav`, `attempts.jsonl`, `visemes/<line>.json`. Full stage: [VOICE.md](VOICE.md).

1. `manifest`, then `gate` (offline): VOICE-CAST, VOICE-STYLE, VOICE-TEXT, VOICE-ONCE.
2. `voice --go`: Chatterbox Multilingual, local GPU, **one take per line**, no ASR, no judge, no re-voice. A line may carry its own `tone` {exaggeration, cfg_weight} (the written object).
3. **Voice quality guard (C2)**: a reference clip is refused when it was noise-gated or denoised (exact-zero samples, floor below -75 dBFS, centroid under 400 Hz), has noise, or is on `bible/voices-banned.json` (`VOICE-BANNED-REF`, `REF-QUALITY`). The narrator must be a firm voice with a clean reference. The first narrator (`common_voice_ar_21519152`) is banned for good.
4. `measure`, `gate --full` (VOICE-TAIL, VOICE-PACE, TAKE-QUALITY): findings go to the owner, never a retake.
5. `visemes` (C6): one mouth track per **drawn** speaker, measured on the trimmed take that is mixed. The narrator has no mouth and no track. `daily.py s_voice` runs it.
6. New words are a new line: `voice.py retext` sets the old take aside (kept) for changed lines only.

## 3. Shots and templates (C4, C6, C10)

`uv run tools/calm.py list` · `make <template> <shot-dir> key=value ... [--run]` · `validate <shot-dir>`. Data in, a normal `shot.py` folder out (`"format": "calm"`, so the calm gate profile runs: motion, depth and the art checks stay, the "never a slideshow" cut thresholds do not).

| Template | Use | Note |
|---|---|---|
| `push_in` `parallax_pan` `hold_breathe` `reaction_closeup` `two_shot` | the story scenes (one subject, hands apart in a two-shot) | no touch between unrelated men and women |
| `insert` | a plain hand or prop close-up | wide frame, hand low |
| `insert_depth` | **a prop close-up with real depth** (tag, key, cards): far set dimmed, counter, the prop on its own plane with a flat 2D cast shadow, a dark occluder with hanging tags, a slow dolly (`dist`, `win`, `push`, `span`, `dim`, `occ`) | E01C: plain inserts failed the parallax check because the prop sat on one flat plane; a wider pan broke `CALM-MOTION`. Needs a `hero` entry in the kit (`CALM-HERO`) |
| `push_in` with `x_drain=plan` | **E03 event scenes: the drain seen from above** (a screen-space plate over the whole frame, the actors underneath are not seen): `x_cover0/x_cover1` (0 lid parked on the rails, 1 shut), `x_water/x_water1` (0 still .. 1 surging), `x_figs=push|brace|kneel|none` (Hero and Partner from above), `x_jolts="1.0,2.4"` (knocks). Drawn by `drawDrainPlan` in `world-a.js`; layers dolly at different rates for the parallax gate, floor flagstones and a lit lid give `luma_range` and `local_contrast`. A silent scene sets `duration` in the plan and carries `foley` cues | catalogue `world-a/location/drain-plan`, `prop/figure-top-hero`, `prop/figure-top-partner` |
| `push_in` with `x_drop=mug` | **E03 event scene: the chute drops a thing**: `x_drop_t` (second it leaves, negative = already lying on the counter), `x_drop_x` (landing X), `x_drop_scale`; the flap rattles and swings open, the mug tumbles, bounces once, rocks, still; a puff of dust (`drawChuteFlap`, `mugState`, `drawMugThread`) | catalogue `world-a/prop/mug-thread-cut`, `location/chute-drop` |
| `intro_freeze` | C10: a character's first appearance (card-kind shot built by `calm_intro.py` from the scene before it) | `INTRO-*` |
| `title_card` `day_card` `recap_card` `choice_card` `follow_card` | the wrapper (Thmanyah, `CARD-*` checks) | |
| `choice_split` | C4: question and two choices in the bottom half, top half left for the close-ups | |
| `object_card` | C3: the brass plate; the narrator's caption is engraved on it | |

- **Kits**: a character enters the calm format only through `tools/templates/calm/kits/<char>.json` (`calm_kit.py extract`, `status`).
- **Art book is the reference, every time** (the owner 2026-10-25, after Hero's hands came out too big): every rig, close-up and shot keeps the approved art-book proportions, hands, faces and costume (`catalogue/characters/<id>/<approved version>/sheets/`; values in `artbook-proportions.json` from `tools/artbook_proportions.py`). Readability in a close-up comes from the camera (closer, insert), never from enlarging a body part. `ART-PROPORTION` runs on every shot (8 % tolerance).
- **Lip sync (C6)**: `calm.py lipsync_entry` places each on-screen line into the shot (`lipsync` in `calm.json` and the spec). The rig gate holds the mouth to the track: `LIPSYNC-ACTIVE` (the viseme follows the track) and `LIPSYNC-SILENT` (shut when silent; a listener's mouth never reads as talking over the narrator). A missing or stale track is refused (`LIPSYNC-NO-TRACK`, `LIPSYNC-STALE-TRACK`).
- **Intro freeze (C10)**: the cut INTO the beat is `freeze` (a riser, a white flash, a zoom punch, the `impact` hit); the frame freezes on the last frame of the scene that introduced the character; a grey glow and rim isolate them (the engine's own line-art mask, no model); the rest dims; hand-drawn graffiti Thmanyah text names them and gives one bible line; the music dips; the colour returns and a declared cut goes back to the story. 3 to 9 s. `INTRO-ISOLATE`, `INTRO-FROZEN`, `INTRO-READ`, `INTRO-TEXT`, `INTRO-LEN`, `CALM-INTRO`, `CALM-INTRO-SFX`.
- **Grade: darkness per shot (Q10, E02 critic 2026-10-27).** `grade=<0..0.12>` darkens the set behind the actor (backdrop, chute, counter) and `grade_actor=<0..0.12>` also the figure and the props she handles (it is laid over the whole frame after the actor, so the set gets it too). Each is TWO flat value steps of one dark ink, like `insert_depth`'s far-set `dim`: a flat 2D value shift, no gradient, no 3D, nothing for LOOK2D to read as smooth shading. `grade_actor` may never exceed `grade` (the lit figure stays the brightest thing). **The ceiling 0.12 is measured, not a taste** (push_in hero medium, 3 s, `shot.py all`, `luma_range` must be >= 0.85): grade 0 = 0.91, 0.12 = 0.882 pass, 0.18 = 0.842, 0.24 = 0.820, 0.4 and 0.6 = 0.809 fail; 0.4 with grade_actor 0.1 = 0.776 and LOOK2D-LINE 0.079 (min 0.08). The set dim drops the bright shelves out of the frame's 99th percentile at once, so past about 0.17 the gate refuses the shot; `calm.py` refuses a bigger number before a render is spent. A darker, emptier ending than 0.12 allows needs a Lead-merged R-212 proposal (a declared dark beat in `gate-spec.md`), never a bigger number here; until then darkness has to come from several small steps across scenes (s08 0.03, s09 0.06, s10 0.09, s11 0.12), tighter framing and the lamp and `world` motion going quiet. Both default to 0 and then calm.json and shot.json are unchanged, so a shot that does not use them keeps its cache. `lamp` and `world` are NOT darkness: they only set how much the lamp and the set move. Use `grade` for "darker towards the end" (E02 s09 to s11), and a tighter `size` (closer framing) for "narrower"; the plan values are the writer's, the healer may change them. Test: `tools/tests/test_calm_fixes.py`.
- **Recap with a story picture (Q01).** The recap card opens the episode, so type on black reads as no story. Plan `recap.backdrop_from`: `"first_shot"` (a frame 1.0 s into the episode's first scene, cut with ffmpeg from its recorded video; `daily.py s_shots` builds the recap card LAST for that reason) or `"episode:<id>@<seconds>"` (a frame of an earlier episode's `work/episodes/<id>/episode.mp4`), or `recap.backdrop: <image path>`; never both (`PLAN-RECAP-BACKDROP`). The card shows it dimmed (opacity .38, desaturated, vignette) under the type. The picture's sha256 is in the card description, so a re-recorded scene 1 rebuilds the card. No `backdrop*` key = type on black as before.
- **Cards and the NJ mark.** Every card checks `CARD-MARK` at once: no measured text box may touch the mark's rectangle plus `WM.PAD_PX` (it was found only at the episode's WATERMARK-CLEAR). The first block of a `choice_card` and a `recap_card` keeps a right margin (`MARK_CLEAR_INLINE_PX`) so it ends left of the mark. The cover has no mark and is exempt.
- **Card hashes.** A card's `record` stage hashes `shot.json` (video length), and its `trace` stage hashes the backdrop picture: a duration-only change (E02-day) or a changed recap picture rebuilds the card.
- Each shot passes `shot.py all` (about 1 min) and the heal loop before composing.

## 4. Sound design (C3, C4, C5)

`calm_sfx.py synth` (our own sounds, licence OWN, deterministic, numpy) · `build <ep>` · `check <ep>`. **One cut type picks the picture AND the sound** (`CUTS` in `calm_sfx.py`), so they cannot drift apart: `wind whoosh page ink ink-fade door close horn bell flash steps freeze`. The horn (steamship) belongs to the written object at about 0:08.

- `CALM-TRANSITION-SFX`: every join declares a known cut, with a visual and a sound cue at the join.
- `CALM-FOLEY` (C5): every prop or hand action with a sound in a shot spec (pen, key, tag, card, bag, bell, watch, steps, cloth, lamp) has a cue; every file is licensed in `assets/audio/LICENCES.md` with a matching sha256. A foley cue repeating its transition's sound within 0.4 s is dropped.
- `CALM-CHOICE-SFX` (C4): a pop at every cut of the choice sequence and one per narrated line.
- `CALM-INTRO-SFX` (C10): the `impact` cue on the join into an intro, and the marker sound for the graffiti.

## 5. Captions (C1, C7, C8, C11, C12)

`calm_compose.py captions <ep>`. Time of each word comes from the take's own energy (numpy, no model) laid by syllable weight, so it is an estimate within `SYNC_TOL_S` 0.08 s.

- **Full sentence, spoken word highlighted (C7)**: a plate holds a whole sentence or clause (at most 8 words, 2 lines, 104 px Thmanyah) with the word being spoken lit. One plate at a time (`CALM-ONE-PLATE`). `CAP-FULL-SENTENCE`.
- **Reading time (C12)**: a plate stays at least 1.5 s and at least its characters divided by 12 a second, plus a tail of 0.6 s; a sentence shorter than a reader needs makes the edit add a short pause. 12 characters a second is a judgement, tuned by the owner's eye. `CAP-READ-TIME`, `CAP-READING-SPEED`.
- **Letters join (C1)**: the dark outline is a separate under-layer, never `-webkit-text-stroke` on the fill glyphs; words are plain Arabic (no ZWNJ, tatweel, pre-shaped forms). `CAP-ARABIC-SHAPING`.
- **Gloss every cultural word (C8, C11)**: the meaning «(...)» sits on its own 64 px line under the sentence for the whole time the sentence is up, never inside a short flash. `CAP-FOREIGN-GLOSS`. Unknown caption words go to `work/episodes/<ep>/review/arabic-words.json` for a reader (`CAP-ARABIC-REVIEW`, a warning).
- **Off faces**: a plate is placed outside the face boxes of every shot on screen while it is up (`cap_face.py`). `CAP-FACE-CLEAR`. Inside the safe area `SAFE` = (54, 270, 1026, 1250): `CALM-PLATE-SAFE`.
- **The object card** engraves the caption on the plate; **the choice sequence** keeps plates in the top-half zone it needs, and lights the question and each choice as the narrator reads them.
- No tashkeel on screen (`CAP-TASHKEEL`, `CALM-NO-TASHKEEL`). The HUD (day, clock, place) covers every story scene (`CALM-HUD`).

## 6. Mix (C9): phone first

`calm_compose.py audio <ep>` runs `tools/calm_mix.py` (preset `phone-first`; `mix_preset: legacy` reproduces the old chain). Research and numbers: `research/sound-e01c.md`. Role: `sw-sound-engineer`.

1. **Voice**: high-pass 90 Hz, cut 220 Hz, lift 3.2 kHz, de-ess only when needed, gentle compression, every take set to -19 LUFS so narrator and characters sit together.
2. **Bed**: a numpy pad shaped 110 Hz to 3.2 kHz with a speech scoop, set 15 LU under the voice **as a phone plays it** (a bed with only low energy plays nothing on a phone).
3. **SFX**: band-limited per sound and set to a loudness **relative to the voice** (transition -9, choice pop -10, foley -13), never from the file's peak.
4. **Ducking** computed from the voice stem: bed -9 dB, 80 ms lookahead, gaps under 0.3 s bridged; the music also dips under every intro.
5. **Master**: one linear gain to -14 LUFS, a limiter only if the true peak needs it, no compressor on the sum.

Checks: `CALM-LOUDNESS` (-15 to -13 LUFS, true peak at or under -1.0), `AUDIO-DIALOGUE-CLARITY`, `AUDIO-MONO`, `AUDIO-PEAK` (`audio_checks.py`), `CALM-NO-SILENCE` (no gap over 0.6 s). Fix the cause in `calm_mix.PRESETS`, never the threshold.

## 7. Assemble, gate, critic (C3, C4, C10)

- `assemble`: shots and cards joined by the declared cut types (ffmpeg xfade, NVENC, 2 threads), plates, mix. In the choice sequence the top half cuts between two close-ups with a pop and a VFX at each cut, in time with the narrator. **The last step lays the small NJ mark** (only the calm path does: the older non-calm profile of `tools/compose.py` has no mark and must not be used for delivery) (the owner 2026-10-25: faint cream, top-right, 926,282, 96 px, opacity 0.40, `tools/watermark.py`) over every frame in the same final encode and writes `watermark.json`; it also writes `cover.png` (the «بطاقة اليوم» cover, `calm_cards.cover_card`, no mark) and `cover.json` for the uploader.
- **Follow card (from E02)**: the line is «الحلقة القادمة تتبع ما تكتبونه», a statement, never «تابعوا لتعرفوا» (`CC.FOLLOW_LINE`, `PLAN-FOLLOW`, `CALM-FOLLOW-LINE`).
- `gate`: the declared checks above plus the calm bands of `quality_gate.py calm` (declared shots, not detector hits inside transition windows). `CALM-TWO-CHOICES`, `CALM-VOICE-COVERAGE`, `NARRATOR-SHARE`, `CALM-HOLDS`, `CALM-LENGTH`, and the 2026-10-25 additions `CALM-HOOK-3S`, `CALM-HUD` (series strip), `CALM-FOLLOW-LINE`, `CALM-COVER`, `WATERMARK-PRESENT`, `WATERMARK-CLEAR` (notes in `kb/quality/gate-spec.md` H.2b). Exit 1 on any failure; "check with no data fails".
- **Heal guard (2026-10-27).** `daily.py s_critic` never keeps a plan edit that turns a passing shot into a failing one: it remembers which scene shots PASSED before the healer ran, and when the rerun fails on a scene the healer edited, it takes the edit back (first only the framing parameters `FRAMING_KEYS`: size, push, target, at_y, span, pan, dist, win; then the whole scene entry), rewrites and re-checks the plan, reruns, and logs each refusal in `heal/refused-edits.jsonl` and in the next healer prompt ("Edits already refused"). A failure that is not such a regression still stops the stage. E02 s10 `size: mwide` -> `medium` failed `depth_bands` round after round.
- `critic`: 12 format questions (`daily.py CRITIC_QUESTIONS`), 9 or more of 10 to pass, plus every past F and C note. The healer edits the plan, never the script, at most 2 rounds.

## 8. Preview: four tabs at most

One new tab in `previews/index.html`, opened on that tab, playing the **recorded** `episode.mp4`. At most 4 tabs: older tabs move to `previews/archive/index-<date>.html` (kept), a new tab replaces the oldest (`PREVIEW-MAX-TABS`). ADHD-friendly: hook first, short emoji-led blocks, big choice cards.

## 9. Post and the comment rule (C13)

`ig.py publish <ep> --go` (official Graph API only, after gates and critic). The post caption, the choice card and the narrator's hook ask an OPEN QUESTION about the story and for a reason (DESIGN.md 5.2); never "comment 1 or 2", never a request to type a specific word, and the follow card states a fact («الحلقة القادمة تتبع ما تكتبونه») instead of begging. 12 hours later `vote.py tally` counts a vote from the choice phrase, its variants and its distinctive words (a bare 1/2 still counts), and keeps longer comments as ideas for the next writer brief ([AUDIENCE.md](AUDIENCE.md)).

## 🧾 Note to step map

| Note | Created | Step | Checks |
|---|---|---|---|
| C1 letters break | outline stroke on joined glyphs | 5 | CAP-ARABIC-SHAPING |
| C2 narrator banned | gated reference scored as the cleanest | 2 | VOICE-BANNED-REF, REF-QUALITY, TAKE-QUALITY |
| C3 transition SFX, written object | no sound on joins | 4, 7 | CALM-TRANSITION-SFX |
| C4 choice sequence | ended on a situation | 1, 3, 7 | CALM-CHOICE-SFX, CALM-TWO-CHOICES |
| C5 foley | none | 4 | CALM-FOLEY |
| C6 lip sync | visemes not run; narrator crash | 2, 3 | LIPSYNC-ACTIVE, LIPSYNC-SILENT |
| C7 full sentence | word flashes | 5 | CAP-FULL-SENTENCE |
| C8 and C11 gloss | only pointed-at words | 1, 5 | CAP-FOREIGN-GLOSS, PLAN-GLOSS |
| C9 phone mix | headphone numbers | 6 | AUDIO-* |
| C10 intros | no template, no check | 1, 3 | CALM-INTRO, INTRO-* |
| C12 reading time | plates too short | 1, 5 | CAP-READ-TIME |
| C13 comments | digits only | 1, 9 | PLAN-CHOICE, CALM-CHOICE, vote.py |
| face cover | plates over faces | 5 | CAP-FACE-CLEAR |

Related: [DAILY.md](DAILY.md), [COMPOSE.md](COMPOSE.md), [VOICE.md](VOICE.md), [AUDIENCE.md](AUDIENCE.md), [HEAL.md](HEAL.md), [CREW.md](CREW.md), `research/stickman-recipe.md`.
