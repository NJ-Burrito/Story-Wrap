# 🎬 Composing stage (episode assembly)

🧭 **Two paths.** The **calm path** (`tools/calm_compose.py`, used by the daily run and approved on E01 calm v5) is the one in use: its steps, checks and notes are in [CALM.md](CALM.md). The **premium path** (`tools/compose.py`, below, with the `EP-*` gate) is kept for a premium episode. Sections below the line "Calm sound and picture design" describe the calm path.

⭐ Shots in, one gated Reel out: `uv run tools/compose.py <stage> <ep>`. `<ep>` is a folder, `<series>/<ep>` or a bare id like `E01`. Last stage of the project order (research → writing → sketching → animating → **composing**). Starts only when the script is written, voiced (or flagged "no voice yet") and every shot in the shotlist has a recorded render that passed `shot.py gate`.
Tool: `tools/compose.py` (PEP 723, `uv run`). Tests: `tools/tests/test_compose.py`. Check ids: `kb/quality/gate-spec.md` section F. Shot side: `RUNBOOK.md`. Voice side: `VOICE.md`.

## 🧭 The order

`plan → audio → captions → assemble → end → gate → preview`   (`all` runs the first six and stops at the first failure)

| # | Stage | Who | Writes (`work/episodes/<ep>/`) | Must pass |
|---|---|---|---|---|
| 0 | Outline, script, **shotlist** | `sw-showrunner-writer` and `sw-director` (Sonnet) | `bible/series/<s>/episodes/<ep>/{outline.md, script.json, shotlist.json}` | `bible_check`, schema `kb/quality/shotlist.schema.json` |
| 1 | `plan` | `sw-editor-compositor` | `plan.json` (timeline) | `PLAN-*` (below) |
| 2 | `audio` | `sw-editor-compositor` | `audio/mix.wav`, `audio/audio.json` | `AUDIO-LICENCE`, `AUDIO-PARTIAL`, `AUDIO-MODE` |
| 3 | `captions` | `sw-editor-compositor` | `captions/<line>.png`, `captions.json` | `CAP-FONT`, `CAP-TIMING` |
| 4 | `assemble` | `sw-editor-compositor` | `assembled.mp4` | `ASM-SHOT-VIDEO`, `ASM-AUDIO` |
| 5 | `end` | `sw-editor-compositor` | `end/card.png`, `end/end.json`, **`episode.mp4`** | `END-CARD` |
| 6 | `gate` | `sw-editor-compositor` (Sonnet) | `gate/report.json` | all `EP-*` |
| 7 | `preview` | `sw-editor-compositor` | a tab in `previews/index.html` | `PREV-*` |
| 8 | the owner watches and listens | the owner | note in `bible/feedback/` | his eye and ear |

Every stage records status and input hashes in `work/episodes/<ep>/STATE.json` (the `shot.py` engine). A rerun skips a finished stage whose inputs did not change; `--force` reruns it; `status <ep>` lists `ok (fresh)`, `ok (stale: inputs changed)` or `FAIL [ID] message`. A fix reruns one stage, not all. A failed stage prints `FAIL [CHECK-ID] message` and exits 1 (2 = tool error). Changing `--silent` or `--skip-render-gate` needs `--force` (flags are not inputs).

## 🗂️ Layout

```
bible/series/<s>/episodes/<ep>/   outline.md  script.json  shotlist.json     (the writer / director owns these)
work/shots/<id>/                  one tools/shot.py folder per shot            (out/<id>.mp4 = the recorded render)
work/voice/<ep>/                  <line>.wav from tools/voice.py, visemes/<line>.json
work/episodes/<ep>/               everything compose.py writes (git-ignored)
assets/audio/LICENCES.md          the music and SFX licence register (committed; the audio files are git-ignored)
```

`uv run tools/compose.py init <series>/<ep>` scaffolds `outline.md` + `shotlist.json` (never overwrites; `script.json` stays with the writer).

## 🧾 shotlist.json (the director's map)

Schema: `kb/quality/shotlist.schema.json`. In short:
- `hook`: the story event that lands in the first 2 s (`event`, `at_s`).
- `shots[]`: `id`, `folder` (a shot folder), `in_frame`/`out_frame` of its render, `lines[]`, `faces[]` (boxes from the camera plan), `sfx[]`.
- `shots[].lines[]` (a spoken line **starts** in this shot; it is placed on the episode timeline and may run across cuts): `line` (id from `script.json`), `at_s` (seconds from this shot's start to the line's start; **negative = J-cut**, the sound starts in the shot before; a line that outlasts the shot is an **L-cut**), optional `est_dur_s` (only until the take exists), `on_screen` (default true; false for an off-screen voice, a cutaway or a POV insert), `visible_in` (shot ids where the speaker is visible and facing camera while the line plays; the visemes apply only there), `overlap_with` (ids of lines of a different speaker this one deliberately talks over), `note` (a director's note; start it with `TODO` for an unknown).
- `transitions[]`: one per neighbouring pair, `type` (`cut`, `fade`, `dip`, `wipe`, `slide…`, `circleopen`…) and `frames`. A transition of N frames overlaps the shots by N/24 s. A plain cut is `cut`, 0 frames.
- `sfx_map`: the shot spec's `emotion_track.sfx[].what` text → a licensed file. Cues with no entry are listed as unfilled (a warning, never a silent skip).
- `music`: one bed (`file`, `licence_id`).
- `end_card`: `duration_s`, `question_ar`, exactly two `choices` (`text_ar`), `comment_prompt_ar`. These come from the episode's choice ending in `series.md` (episode engine).

## 1️⃣ plan (checks `PLAN-*`)

The shotlist against the script. Audio and captions sit on the **episode timeline**, independent of shot boundaries (real editing lets dialogue run across cuts). `PLAN-SHOTLIST` (schema), `PLAN-LINE-SHOT` (every spoken line is in a shot), `PLAN-LINE-UNKNOWN`, `PLAN-LINE-DUP`, `PLAN-LINE-TIMELINE` (the line lies inside the episode picture, 0 to the end of the last shot; it may cross cuts), `PLAN-LIPSYNC` (a line with `on_screen` true needs at least one `visible_in` shot that is playing during the line; that overlap is its viseme window, written to `plan.json` as `lipsync`; `on_screen: false` needs none), `PLAN-LINE-OVERLAP` (two lines may overlap in time only if they have different speakers and one declares the other in `overlap_with`; a speaker never talks over themselves), `PLAN-LINE-CAPTION` (every line has Arabic caption text), `PLAN-TRANSITION`, `PLAN-FRAMES` (frame range exists in the render), `PLAN-HOOK`, `PLAN-LENGTH` (30–60 s planned, end card included). `PLAN-LINE-FIT` (a line must fit inside its shot) is retired: it was the tool's mistake, not the script's. `plan.json` lines carry `spans_shots`, `on_screen`, `lipsync`, `overlap_with`. Missing shot renders are a warning here and a hard stop at `assemble`.

## 2️⃣ audio

- **Voice**: each take from `work/voice/<ep>/<line>.wav` is placed at its line start (the take's real length; voice first: when the piece's spec has a `voice_lines` entry for the line, the start is that entry's `start_s` minus the shot's `in_frame / fps`, and `at_s` in the shotlist may be left out, `PLAN-VOICE-OFFSET` if it disagrees), bus normalised to −16 LUFS (`nj-kit:bg-music` rule: voice −16, bed −23).
- **Music bed**: looped, trimmed, faded, measured and set to −23 LUFS; ducked under dialogue (`sidechaincompress`, ratio 8, 20 ms attack, 400 ms release).
- **SFX**: cues from the shot specs' `emotion_track.sfx` (shot-relative `at_s`) through `sfx_map`, plus explicit `shots[].sfx`; default −18 dB, ducked lightly (ratio 4). Defaults are house numbers, **tune by ear** (`bg-music/reference/sfx-practice.md`).
- **Loudness target: −14 LUFS integrated, true peak ≤ −1.0 dBTP (mix aims at −1.5), two-pass `loudnorm`, gate tolerance ±1 LU.** Source: **measured** on the delivered Instagram renditions of the benchmark reels, −14.1 LUFS on three of four (`kb/guides/reels.md` section 3, `research/10`). Instagram publishes no number (gap, reels.md section 1), so this is the measured norm, not a platform rule. Baseline 2 peaked at +0.1 dBFS, hence the true-peak ceiling.
- **Silent / caption-only mode** — `--silent`, or automatically when no take exists: the voice is skipped, line times come from `est_dur_s` or an estimate (12 Arabic letters/s, house default), `audio.json` says `mode: no-voice-yet`, `banner: NO VOICE YET`, the gate reports `EP-VOICE: WARN` and the preview tab shows the banner. With some but not all takes, `AUDIO-PARTIAL` stops: a partly voiced episode is the owner's decision (`VOICE.md`). The whole pipeline is proven this way before any TTS money is spent. **A "no voice yet" episode is a proof, never a deliverable.**
- **Licences**: every music/SFX file needs a row in `assets/audio/LICENCES.md` (`licence-add` records its sha256). Allowed: CC0, PD, CC-BY, CC-BY-SA, OWN (made by us). NC and ND are refused, CC-BY needs its credit line published with the Reel. Sourcing: `~/.claude/skills/bg-music` and `media-use resolve --type sfx`; both are free and record licences. Never rip sound from a reel. Nothing is fetched yet.
- ffmpeg runs `-threads 2 -filter_threads 2`. Audio filters have no GPU path; they are light.

## 3️⃣ captions

**Compose is the single caption owner** (E01 run 1): pieces never draw dialogue captions (`PIECE-NO-CAPTION`); only diegetic text stays in the picture. One Arabic plate per spoken line: Thmanyah Sans Bold, RTL, white on a translucent dark plate, drawn by Chrome (the same engine that shaped the art), cropped PNG, transparent. Timed to the viseme track when `visemes/<line>.json` exists, else to the take, else to the estimate. Placed centred with the bottom edge 4% above the lower safe line. A plate is **one overlay on the episode clock**: it stays on screen across a cut (no flicker, no re-entry or animation at the cut; `captions.json` records `spans_shots`). The plate of a declared overlap ends where the next line starts (known limit: one plate at a time, `EP-CAPTIONS`). Never a fallback font: missing Thmanyah files stop the stage (`CAP-FONT`).

## 4️⃣ assemble

Shots trimmed to `in_frame..out_frame`, joined with `concat` (cut) or `xfade` (declared type and frames), captions overlaid with `enable=between(t,a,b)`, mix muxed (AAC 192k, 48 kHz). Decode `-hwaccel cuda`, encode `h264_nvenc` (p5, `-cq 19`), 24 fps.

## 5️⃣ end (the choice card)

A 1080×1920 card in Thmanyah: the question (serif display), the two choices on big cards (A / B badges), the comment prompt. All text 44 px or larger, inside the safe zone. **It sits over live footage** (E01 run 1: the outline wants it over the office, not a flat card): `end_card.backdrop` is `live-loop` (default: the last `loop_s`, default 1.5 s, of the last piece played forward and back, so the picture never freezes or jumps), `live-hold` (the last frame held) or `static` (the old flat card, proofs only). The question and the prompt sit on a scrim (rgba 20,18,15 at 0.80); the choice cards are opaque. `end/overlay.png` is the card on a transparent ground; `end/card.png` is the overlay flattened over white, so contrast is measured on the worst case. It is appended to the assembled video; its sound is the tail of the same mix. `episode.mp4` is the file everything downstream reads.

## 6️⃣ gate (Sonnet reads the receipt; the gate decides)

| ID | Checks |
|---|---|
| `EP-LENGTH` | `episode.mp4` is 30–60 s |
| `EP-HOOK` | hook event declared at ≤ 2 s **and** measured motion in the first 2 s of shot 1 (≥ 60% of 12 fps steps move ≥ 5% of blocks) |
| `EP-CAPTIONS` | every script line has a plate, contrast ≥ 4.5 (measured from the PNG, worst case over white), font ≥ 40 px, RTL Thmanyah, windows valid, no two plates at once |
| `EP-SAFEZONE` | plates and end-card text inside the safe rect; declared face boxes too (no boxes declared = WARN) |
| `EP-LOUDNESS` | −14 ±1 LUFS, true peak ≤ −1.0 dBTP, measured on the final AAC |
| `EP-CHOICE` | exactly 2 Arabic choices + comment prompt, card ≥ 2.5 s, text ≥ 44 px and contrast ≥ 4.5 (over white footage for a live backdrop), **the last frame of the video is the card** (the opaque card pixels match the overlay; with `live-loop` the footage around the scrim must move) |
| `EP-MUSIC-LICENCE` | every music/SFX file used has an allowed licence row (credit, source, date, sha256 match) |
| `EP-VOICE` | WARN while "no voice yet" |
| `EP-RENDER-GATE` | `tools/quality_gate.py render episode.mp4` (freeze, motion, depth, light…) |

Safe zones: top 14%, bottom 35%, sides 5% (top/bottom are a third-party attribution to Meta, **unverified, Q-05**; sides are a house default). They are constants (`SAFE`) in one place, so a verified number changes one line. `--skip-render-gate` exists for synthetic tests and marks the report `complete: false`; a real episode never uses it. The render gate needs the GPU (about a minute).

## 7️⃣ preview

`uv run tools/compose.py preview <ep>` adds or updates one tab `ep-<ep>` in `previews/index.html` (the one preview page) with the gated video, the check chips, the loudness and the "no voice yet" banner. Then open `previews/index.html#ep-<ep>` for the owner. The tab plays the recorded video, never a live renderer.

## 👥 Who does what

| Role | Model | Does |
|---|---|---|
| Director and script | Sonnet (`sw-showrunner-writer`, `sw-director`) | `outline.md`, `script.json`, `shotlist.json`, the choice ending, which sound goes where |
| Assembler | Sonnet (`sw-editor-compositor`) | runs `plan … end`, `preview`; copies the receipt |
| Gatekeeper | Sonnet (`sw-editor-compositor`; the Lead reads the receipt) | runs `gate`, reads `gate/report.json`, sends a failure back to the stage that owns it |
| Eye and ear | **the owner** | approves by watching and listening; his note goes to `bible/feedback/` |

## 🛟 When a check fails

Fix the cause, never the gate: `PLAN-*` → shotlist/script; `EP-CAPTIONS`/`EP-SAFEZONE` → `captions` (or a shot that puts a face in a UI zone → camera plan); `EP-LOUDNESS` → `audio` (levels), `EP-CHOICE` → `end_card` text; `EP-RENDER-GATE` → the shot, back through `shot.py`. One fix, one rerun (`--force` for that stage). Owner exception: one run, no second look; report the failing line.

## ⚠️ Known limits

- Safe zones, loudness and reading speed are secondary or measured-on-four numbers; Q-05 is open.
- Faces are checked only if the shotlist declares boxes. The gate cannot see text baked into a shot.
- No GPU audio path; the end card joins by a hard cut; a video-only `concat -c copy` needs identical encoder settings (same tool, so it holds).
- `EP-RENDER-GATE` was calibrated on single shots; whole episodes with a dark end card may need a declared hold. Do not loosen a threshold.

## 🚀 To compose E01

1. `episodes/E01/{script.json, outline.md}` (`sw-showrunner-writer`) and `uv run tools/compose.py init series/E01` for the shotlist.
2. Every shot recorded and gated (`work/shots/<id>/out/<id>.mp4`), face boxes copied from the camera plans.
3. Voice: `voice.py` (VOICE.md); the daily run starts it itself (the owner decided, unattended) — or compose in `--silent` mode first.
4. Music bed and SFX files chosen and registered in `assets/audio/LICENCES.md` (nothing fetched yet).
5. `uv run tools/compose.py all E01`, then `preview E01`.

## 🩹 Healing (optional stage, on by default)

Covers the `EP-*` gate and the critic questions CQ-E1 to CQ-E7 (hook, voice, lip sync, end card, music licence, continuity, captions) next to the shot questions.
- After the gates: `uv run tools/compose.py heal <ep>` (also after `compose.py all)` writes `heal/critic-brief.md` and, if anything failed, `heal/fix-brief.md` in `work/episodes/<ep>`. A Sonnet critic answers `kb/quality/critic-checklist.md` into `heal/critic.json`; `heal.py classify` maps each fault to a class, a fix place and a fixer (`kb/quality/heal-playbooks.md`); the fixer repairs the root cause, records it with `heal.py round`, and the stage reruns. Up to 3 rounds; then stop and report.
- the owner sees this only when `uv run tools/heal.py status work/episodes/<ep>` says ready: all gates pass, critic score 9 or more of 10, guard clean. Never loosen a gate, edit a trace or hide a fault; the guard refuses it.
- Then `heal.py learn` writes each healed fault to `kb/lessons/ledger.jsonl`. Full loop: [HEAL.md](HEAL.md).
- No tashkeel in anything people see: `tools/arabic_display.py` `display_text()` feeds the caption plates and end card; gate checks CAP-NO-TASHKEEL (compose), TEXT-NO-TASHKEEL (spec; skips `reference/`); `voice.py` keeps the vowelled `tts_text`.

## Calm path (the owner 2026-10-25; end to end in [CALM.md](CALM.md))
`calm_compose.py plan | captions | audio | assemble | gate | all <ep>`; outputs in `work/episodes/<ep>/` (`timeline.json`, `captions.json`, `plates/`, `hud.json`, `sfx.json`, `mix.wav`, `audio/stems/`, `episode.mp4`, `gate/report.json`). Plan schema: [DAILY.md](DAILY.md).
- **Captions (C7, C12, C1, face)**: a plate is a full sentence or clause (2 lines, at most 8 words, 104 px Thmanyah) with the word being spoken highlighted, one plate at a time (`CAP-FULL-SENTENCE`, `CALM-ONE-PLATE`). Word times come from the take's energy, laid by syllable weight (an estimate within 0.08 s, no model). A plate stays up at least 1.5 s and its characters / 12 a second plus a 0.6 s tail; the planner adds a `hold` (0 to 1.5 s) when the voice is faster (`CAP-READ-TIME`, `CAP-READING-SPEED`, `PLAN-HOLD`). The outline is a separate under-layer so joined letters never break (`CAP-ARABIC-SHAPING`). A plate sits outside the face boxes of every shot on screen (`cap_face.py`, `CAP-FACE-CLEAR`) and inside `SAFE` (`CALM-PLATE-SAFE`). The old 1 to 3 word grouping (`group_words`) is legacy.
- **Intros (C10)**: `intro_freeze` items sit on the timeline right after the scene that introduced the character (plan key `intros`); `CALM-INTRO`, `CALM-INTRO-SFX`, `INTRO-*`. The music dips under each.
- **Recap**: from E02 only (`RECAP_FROM_EPISODE`); E01 opens on its story at 0 s.
- **Gate ids run by `calm_compose.py gate`**: `CALM-LOUDNESS CALM-NO-SILENCE CALM-ONE-PLATE CALM-PLATE-SAFE CALM-HUD CALM-NO-TASHKEEL CALM-TWO-CHOICES CALM-VOICE-COVERAGE NARRATOR-SHARE DIALOGUE-LINES EVENTS CALM-RECAP-FIRST CALM-LENGTH CALM-INTRO CALM-TRANSITION-SFX CAP-* AUDIO-DIALOGUE-CLARITY`, plus `quality_gate.py calm`.

## Calm sound and picture design (C3 + C4 + C5, the owner 2026-10-25)
- **Foreign-word gloss (`CAP-FOREIGN-GLOSS`, the owner 2026-10-25)**: `bible/series/<series>/glossary.json` lists every signature word of every character bible (`word`, `language`, `meaning_ar`, `character`, no tashkeel; check it with `uv run tools/gloss.py`). `calm_compose.py captions` puts «(meaning)» on its own smaller line (64 px) under every plate of the group that holds a glossary word, and `captions.json` carries `text` (with the bracket) and `gloss`. The gloss is never spoken and never timed. Words typed on the recap, choice or post-caption strings are not glossed for you: `PLAN-GLOSS` (plan time) and `CAP-FOREIGN-GLOSS` (gate) fail until the writer adds «(meaning)». The premium `compose.py` path has no glossary.
- **Pacing counts declared shots (gate-spec H.1a)**: the calm gate runs `quality_gate.py calm episode.mp4 --timeline timeline.json`; detector hits inside a declared transition window are not cuts. **Length** has a 25 s floor and a soft warning over 92 s, no ceiling (the owner 2026-10-25).
- **Transitions (`CALM-TRANSITION-SFX`)**: `plan.transitions` names a cut type per join (`wind whoosh page ink ink-fade door close horn bell flash steps`); one name gives the xfade visual AND the sound (`tools/calm_sfx.py CUTS`). No declaration means the default by template. Unknown cut or join: `PLAN-TRANSITION`.
- **Written object at 0:08**: `plan.written` (line W01, `object_card` brass plate). Horn cut into it, narrator reads it in the `data` style with a line `tone` (`exaggeration`, `cfg_weight`, honoured by `voice.py line_tone`), caption engraved on the plate (`cap_style: object`).
- **Choice sequence (`choice_split`)**: `plan.choice.lines` (question, choice1, choice2, hook: four narrator lines) and `plan.choice.split` (two close-ups cropped from rendered shots, cuts at the lines). Bottom half: question and pills, each lit as read; top half: cuts with a VFX each. `CALM-CHOICE-SFX`: a pop at every cut and every line.
- **Foley (`CALM-FOLEY`)**: cues come from each shot spec's `emotion_track.sfx`, plus `foley` / `foley_mute` per scene in the plan; every file must have a LICENCES.md row with a matching sha. Own sounds: `uv run tools/calm_sfx.py synth` (OWN).
- Stages: `calm_compose audio` writes `work/episodes/<ep>/sfx.json`; the sfx bus is ducked under the narrator. The choice card shot must be rebuilt as `choice_split` and the day card as `object_card` (daily.py shots).
- **Phone-first mix (C9, the owner 2026-10-25)**: `calm_compose audio` runs `tools/calm_mix.py` (preset `phone-first`; `mix_preset: legacy` in calm-plan.json reproduces the old chain). Research and numbers: `research/sound-e01c.md`. The chain, in order:
  1. **Voice**: every take gets high-pass 90 Hz, a 220 Hz low-mid cut, a 3.2 kHz presence lift, a de-esser only when that take's 5 to 9 kHz band is within 17 dB of its speech band, and a gentle compressor (ratio 2.5); each take is then set to the same loudness (-19 LUFS gated) so narrator and characters sit together; the bus has a lookahead limiter at -7.5 dBFS.
  2. **Bed**: a numpy pad (Am / F / Am, notes from 110 Hz, harmonics to 2.5 kHz, a soft 55 Hz sub for earbuds), shaped 110 Hz to 3.2 kHz with a speech scoop at 2.4 kHz, set 15 LU under the voice measured through the phone simulation. Width comes from different swells per side, never phase, so the mono fold keeps every note.
  3. **SFX**: each sound is band-limited per sound (`calm_mix.SFX_BAND`) and mono-folded, then set to a loudness **relative to the voice in the phone simulation** (transition -9, choice pop -10, foley -13 LU, per-sound adjustments in `sound_adj_db`; the horn is +7), never from the file's peak. A cue's peak stays 2 dB under the voice peak. Two cues of one sound within 30 ms count once; a foley cue that repeats its transition's sound within 0.4 s is dropped (`calm_sfx.dedupe_stacked`).
  4. **Ducking**: dialogue first, computed from the voice stem: bed -9 dB, stingers -8 dB, foley -9 dB while anybody speaks, 80 ms lookahead, 50 ms attack, 450 ms release, gaps under 0.3 s bridged (no pumping between words).
  5. **Master**: one linear gain to -14 LUFS (BS.1770 gated, from the same stems the checks read); a lookahead limiter only if the true peak would pass -1.5 dBTP. No compressor on the sum.
  `audio/stems/{voice,bed,sfx}.wav` (after ducking and the master gain) are kept so the checks and a later remix read the same files.
- **Audio checks (`tools/audio_checks.py`, run by `gate`, thresholds in `THRESH`)**: `AUDIO-DIALOGUE-CLARITY` (on a phone simulation: mono, 300 Hz to 8 kHz, the voice over music + sfx on the frames where somebody speaks: median >= 20 dB, weakest tenth >= 14 dB, no window under 8 dB, at most 4 % under 12 dB), `AUDIO-MONO` (the fold-down loses at most 1 LU and 1.5 dB of clarity; L/R correlation 5th percentile >= 0.2), `AUDIO-PEAK` (true peak <= -1.0 dBTP on the delivered AAC, sample peak <= -1.0 dBFS, no clipped sample, no sound louder than the dialogue under it). They need `audio/stems/`: a legacy episode fails them on purpose. Fix the cause, never the threshold: clarity -> `calm_mix.PRESETS` (bed, duck, `rel_db`) or the cue's sound; mono -> the bed or a stereo source; peak -> `rel_db` or the limiter.
