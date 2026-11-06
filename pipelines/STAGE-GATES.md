# 🛡️ Safe stages: verify after every stage

⭐ **A stage is not done when it runs. It is done when its VERIFY passed.** the owner, 2026-10-25: "add safe fixing, measurement and testing stages between steps so we don't redo the work after finishing and find out bugs." Code: `tools/stagegate.py` (fingerprints, staleness, one verifier per stage), `tools/animatic.py` (the early preview), `tools/daily.py` (the runner). Tests: `tools/tests/test_stagegate.py`. Part of [DAILY.md](DAILY.md); the ladder of cheap checks per step is in [CALM.md](CALM.md).

## 🧭 The five rules

| # | Rule | Where it is enforced |
|---|---|---|
| 1 | After EVERY stage a verify runs at once: (a) the contract, (b) the stage's own gates | `daily.verify_stage` |
| 2 | The next stage cannot start until the one before it is fresh and its verify passed | `daily.require_upstream` (in `run_list`) |
| 3 | A failure stops with the check id and a fix brief (`STOPPED.md`, `work/daily/<ep>/verify/<stage>.json`) | `stagegate.brief` |
| 4 | A fix at stage N reruns EXACTLY the stages whose input hashes changed, each with its own verify | `daily.stage_state` |
| 5 | Time of every stage and every verify is recorded | `work/daily/<ep>/timings.jsonl`, `STATE.json` |

A gate is never loosened to pass. A stage that finds nothing wrong still leaves its report (`verify/<stage>.json`).

## 🪜 The stages and their verifies

`votes → script → voice → plan → animatic → shots → compose → gates → critic`, then `publish → schedule`. `plan` and `animatic` are new: the plan used to hide inside `shots` and `compose`, and nothing looked at timing, captions or the mix before the shots were drawn.

**(a) The contract, for every stage** (`stagegate.contract`): every declared output exists and is not empty, every JSON output parses (`CONTRACT-OUTPUT`); every declared input has a recorded sha256 (`CONTRACT-INPUTS`); no input moved while the stage ran (`CONTRACT-INPUT-MOVED`: a stage may not change what it reads).

**(b) The stage's own gates, run right after it:**

| Stage | Verify (check ids) | Catches |
|---|---|---|
| `votes` | `VOTES-JSON`, `VOTES-EMPTY` | a decision file that is not a vote |
| `script` | `SCRIPT-FILES`, `SCRIPT-SCHEMA` (id, speaker, text, tts_text, style), `SCRIPT-TTS-DRIFT` (caption and voice text have different letters), `SCRIPT-TASHKEEL`, `SCRIPT-LINE-LEN` (over 22 words), `SCRIPT-PLAN-LINE`, `SCRIPT-ORPHAN-LINE` (warn: voiced for nothing), `SCRIPT-CAPTION` (three hashtags, no tashkeel), plus every `PLAN-*` check of the writer gate (`validate_episode_files`: schema, gloss, intros, choice, templates) | a bad script before one second of voice is made |
| `voice` | `VOICE-TAKES`, `VOICE-LENGTH` (0.3 to 14 s), `VOICE-RATE` (0.5 to 4.5 words a second: a truncated or garbled take), `VOICE-SILENT`, `VOICE-CLIPPED`, `VOICE-VISEME` (a drawn speaker has a mouth track), **`VOICE-STALE-TAKE`**, `VOICE-ORPHAN-TAKE` (warn) | a take that is wrong, and a line reworded after it was voiced. The take-quality gates behind `voice.py gate --full` (`TAKE-QUALITY`, `VOICE-TAIL`, `VOICE-EDGE-NOISE`, `VOICE-MASTER`) are listed in [VOICE.md](VOICE.md); the mastering chain ends with the pause floor (R-472), so a pause-distance finding after it means the take was generated over the limit (regenerate the line as a new line, never patch the chain) |
| `plan` | `PLAN-TL-SCHEMA`, `PLAN-TL-ORDER` (joins, t1 = t0 + dur, total), `PLAN-TL-SNAP` (whole frames), `PLAN-TL-VOICE` (every take fits its scene), `PLAN-TL-OVERLAP`, `PLAN-TL-COVER` (each planned line spoken once), `PLAN-TL-WRAPPER`, `PLAN-TL-INTRO`, `CALM-LENGTH` | a timeline that cannot be rendered |
| `animatic` | the whole early-preview list below | captions, timing, gloss and mix faults, before any shot |
| `shots` | `SHOTS-VIDEO`, `SHOTS-GATE-REPORT` (the shot's own gate says PASS), **`SHOTS-SHORT`** (a stale shorter render, E01C), `SHOTS-SIZE`, `SHOTS-FPS` | a shot that does not match the timeline |
| `compose` | `COMPOSE-LENGTH`, `COMPOSE-SIZE`, `COMPOSE-FPS`, `COMPOSE-AUDIO` (48 kHz), `COMPOSE-PLATES`, **`COMPOSE-ANIMATIC-DRIFT`** (the composed plates are the animatic's, within 0.02 s) | an assemble that ended early, a missing plate, a preview that no longer describes this build |
| `gates` | `GATE-VERDICT`, `GATE-INCOMPLETE` (all 22 required check ids must be in the report as pass; a gate run without the render checks fails) | a "PASS" that skipped a check |
| `critic` | `CRITIC-INCOMPLETE` (12 answers), `CRITIC-EVIDENCE`, `CRITIC-SCORE`, `CRITIC-STALE` (the critic judged another `episode.mp4`), `CRITIC-UNEXPLAINED` (warn) | a critic report that does not describe this video |
| `publish`, `schedule` | `PUBLISH-RECORD`, `SCHEDULE-PLAN` | a post with no media id, a post with no harvest plan |

A finding is `{id, msg, fix, sev}`. `sev: fail` stops the run, `warn` is written to the report only (for example `CALM-LENGTH` over 92 s: the story sets the length, the Lead confirms). Every `fix` says which stage to fix and what to change.

## 🎞️ The early preview (the animatic)

**Idea**: the expensive part of an episode is the shots (about a minute each, 15 to 25 minutes for a whole episode, plus the compose and gate passes). Most faults the owner found were not in a drawing: they were in the words, the timing and the sound. All of those are known the moment the voice and the plan exist. So after `plan` and before `shots`, `tools/animatic.py build <ep>` makes a low-resolution film of the whole episode with the REAL voice, the REAL timeline, the REAL captions and the REAL mix, and the shots start only when it passes.

**What it builds** (`work/episodes/<ep>/animatic/`):
- `animatic.mp4`: 270 x 480, 12 fps, h264 + aac, 1.7 MB for 127 s. Flat colour per item (card, story, intro, cliff), a white box where each caption plate will be (yellow when the sentence carries a gloss), a green bar where a take speaks, a grey box for the HUD, and the mix as sound. No character is drawn.
- `report.json`: findings, the plate list (`line, unit, word, start, end`, the prediction `COMPOSE-ANIMATIC-DRIFT` compares against), timings.
- `mix.wav`, `sfx.json`, `audio/stems/`: the phone-first mix, rendered ONCE here. `compose` reuses it while the animatic stage is fresh (`daily.audio_reusable`): same takes, timeline and plan, same bytes (measured: the sha256 of `mix.wav` and the three stems was identical before and after a rerun on E01C).

**What it runs** (the same functions the final gate calls, on data instead of pixels):

| Area | Checks |
|---|---|
| Captions (`caption_states`, shared with `calm_compose captions`) | `CALM-ONE-PLATE`, `CAP-FULL-SENTENCE`, `CAP-READ-TIME`, `CAP-READING-SPEED` (C12), `CAP-FOREIGN-GLOSS` (C8, C11), `CALM-NO-TASHKEEL`, Arabic joining of the text (`CAP-ARABIC-SHAPING`, text part), `CALM-PLATE-SAFE` (measured Thmanyah widths, one Chrome page), `ANI-CAP-COVER` (every spoken line has a plate), `ANI-CAP-WINDOW` (a plate stays inside the item that speaks it) |
| Timing | `CALM-LENGTH`, `CALM-VOICE-COVERAGE`, `NARRATOR-SHARE`, `CALM-WRAPPER`, the declared calm data of `qg_checks.check_calm_declared` (voice share, wrapper position, subjects) |
| Audio | `CALM-LOUDNESS` (-15 to -13 LUFS, true peak at most -1), `AUDIO-DIALOGUE-CLARITY`, `AUDIO-MONO`, `AUDIO-PEAK`, `CALM-NO-SILENCE` (no gap over 0.6 s), `CALM-TRANSITION-SFX`, `CALM-FOLEY`, `CALM-CHOICE-SFX`, `CALM-INTRO-SFX`, `ANI-MIX-LENGTH` |

**What it cannot see** (left to the stages that have pixels): a caption on a face (`CAP-FACE-CLEAR` needs each shot's rig trace), the 2D look, seams, hands, shadows, lip sync, grips, the CALM-RENDER measures, the intro's graffiti touching a hijab. The animatic never replaces those gates; it moves the faults that do not need a drawing to the front.

**Cost, measured on E01C** (127.4 s, 23 items, 182 plates, 25 lines, this PC, 2026-10-25):

| Part | Seconds |
|---|---|
| Caption states incl. one Chrome page for word widths | 6.0 |
| Checks (captions, timing, declared data) | 0.4 |
| Mix render + audio checks (reused by compose, so not extra) | 61.7 |
| Low-res video | 3.5 |
| **Animatic total** | **71.6** |

Net extra for a day that passes first time: about 10 s (72 s minus the 62 s mix compose no longer renders), plus about 4 s of verifies over all stages (below) and about 1 s of hashing. A fault caught here saves a rerun of the shots, the compose and the gate: on E01C those were 108 s (cached shots), 75 s and 82 s, and 15 to 25 minutes when shots are drawn from scratch.

## ♻️ SAFE-FIX: what a fix reruns

Every stage records, in `work/daily/<ep>/STATE.json`: `inputs` (sha256 of everything it reads, hashed BEFORE it runs), `outputs` (sha256 of what it wrote, after its verify passed) and `verify`. A stage is **fresh** when it ran ok, its outputs exist, its verify passed, and its inputs and outputs still hash to the recorded values. Anything else is **stale**, with the reason (`inputs changed: timeline.json, takes`).

- Inputs of a stage are the OUTPUTS of the stages before it (and the tools it runs: `stagegate.CODE`). So a fix changes one stage's output, and exactly the stages that read the changed file go stale. Example: the writer fixes `calm-plan.json` (pose of one scene): `script` re-verifies, `plan` and `animatic` rerun in seconds, `shots` redraws only the changed shot (its own hash check), `compose` and `gates` rerun, the voice never reruns because its input (`script.json`) did not move.
- If a rerun produces byte-identical output, nothing downstream goes stale.
- A hand edit of an output is seen as a change of that stage's outputs (it goes stale and re-verifies). The healer's own plan edit is restamped (`daily.restamp`) after `validate_episode_files` passed.
- The heal loop no longer forces `shots, compose, gates`: after the healer it runs `plan, animatic, shots, compose, gates` unforced, so only the stages whose hashes changed run. The critic stage re-hashes its inputs after its heal loop (`Stage.heals`).
- One take per line stays: `script.json` reworded after a line was voiced is `VOICE-STALE-TAKE` (the text each take was made from is kept in `work/voice/<ep>/take-sources.json`). The fix brief says: restore the line, or give the new wording a NEW line id. Nothing is re-voiced automatically.
- **A take over its slot is cured, not a stop (R-502, 2026-10-30).** `PLAN-DURATION` from the plan stage (recap card 3.0 s, scene 10 s, intro 9 s, choice sequence 16 s) calls `tools/line_refit.py` inside `daily.py run`: the writer rewords only that line under a NEW id (`H01` -> `H01r1`), `script.json` and `calm-plan.json` are edited together (rolled back byte for byte if `validate_episode_files` fails), `voice.py refit-mark` records the new id so the voice stage voices only it once, the script stage is restamped (a verified edit, like the healer's), and `plan` runs again. The old take stays on disk: `VOICE-ORPHAN-TAKE` (warn). At most 2 rewrites per line and 6 lines per episode (`work/daily/<ep>/refit.json`). The same rule runs earlier too: the script stage sends a line the estimate puts over its slot back to the writer (`SCRIPT-FIT`, `tools/line_fit.py`) before any voice exists. `uv run tools/daily.py refit --ep <ep> [--line ID] [--dry]` does it by hand.
- **A plate up too briefly is healed, not a stop (R-503, 2026-10-30).** `CAP-READING-SPEED` / `CAP-READ-TIME` from the animatic verify call `tools/read_heal.py` inside `daily.py run`: the measured shortfall + 0.1 s goes to `work/daily/<ep>/read-heal.json` (an input of `plan`): `hold` (a short last sentence: more `read_hold`) or `lead` (a short first sentence: `lead_hold`, silence before the voice that only that scene's first plate may use; `voice_t0` and `dur_shot` move with it); plan and animatic rerun. A middle sentence is not curable and stays a stop. 2 passes per run, 4 per episode. The threshold (1.5 s, 12 cps) is never touched. `ANI-VIDEO`, `ANI-MIX-LENGTH`, `ANI-REPORT` ("rerun the stage") are rerun once. Every other animatic/plan stop code is listed with its reason in the receipt of R-503; none was loosened.
- **A plate with no place on screen is cut, not a stop (R-506, 2026-10-30).** `CAP-FACE-CLEAR` / `CAP-SAFE` from compose and `CALM-PLATE-SAFE` from the animatic call `tools/cap_heal.py` inside `daily.py run`: the failing unit is cut at one more sentence end (else clause end, else mid-sentence, the `split` unit CAP-FULL-SENTENCE allows), recorded in `work/daily/<ep>/cap-heal.json` (an input of animatic and compose), and animatic, shots and compose run again; the animatic still judges the new plates (CAP-READING-SPEED / CAP-READ-TIME, then R-503). When no cut is left the line is reworded shorter under a new id (R-502). 3 cuts a run, 5 an episode, 2 rewrites. The face padding, the safe area and every threshold are untouched. A stop with no heal left goes to the general fixer (see DAILY.md).
- **A shot that fails only a depth gate is re-layered, not a stop (R-504, 2026-10-30).** In the shots stage, when `shot.py all` fails and the only failing gates are `parallax_corr` / `depth_bands` (`quality_gate.DEPTH_GATES`) on a dolly template, `tools/depth_heal.py` re-resolves that shot with the next rung (a longer dolly plus a slight sideways drift, then the near tags), gates it again and re-renders only it (2 rounds per run, every rung once per shot). The rung is kept in `work/daily/<ep>/depth-heal.json` and applied on every later run. The gates, their thresholds and CALM-MOTION are untouched: a rung that breaks another gate fails and the next is tried; after the last rung the stop (`SHOT-GATE`) is the Lead's.
- A stage from before fingerprints (an old `STATE.json`) is **adopted**: hashed and verified, not rerun.

Commands (nothing here runs a stage):
- `uv run tools/daily.py stale <ep>`: every stage, fresh or stale, and why. This is the plan of a fix.
- `uv run tools/daily.py verify <ep> [stage]`: re-run the verifiers on what is on disk; prints each finding with its fix.
- `uv run tools/daily.py run --ep <ep>`: runs the stale stages in order, verifying each. `--force STAGE` still reruns one.
- `uv run tools/animatic.py build <ep>`: the preview alone.

## ⏱️ Cost of the verifies (E01C, measured)

| Verify | Seconds | | Hash of inputs + outputs | Seconds |
|---|---|---|---|---|
| script | 0.3 | | shots (23 videos) | 0.95 cold, 0.03 warm |
| voice (25 takes read) | 0.6 | | every other stage | under 0.15 cold |
| plan | 0.0 | | all 11 `stage_state` calls, warm | under 0.1 |
| shots (23 ffprobe) | 2.7 | | | |
| compose | 0.1 | | | |
| gates | 0.0 | | | |
| critic | 0.3 | | | |
| **all verifies except the animatic** | **about 4** | | | |

Verify time of a machine stage counts against the 4 h cap, like its run. Both are in `timings.jsonl` (`phase: run | verify`) and in `daily.py status`.

## ⚠️ Honest limits

- Measured on E01C, the one real episode. A full unattended day with the writer, the Chatterbox voice and the critic has not been run through the new stages; the stage bodies and every verifier are unit-tested, and `animatic.py`, `daily.py stale` and `daily.py verify` were run on the E01C files.
- E01C's old `STATE.json` shows `COMPOSE-ANIMATIC-DRIFT`: its `captions.json` was written before the last caption changes (one plate ends 0.11 s apart from what today's code makes). That is the check working; the next compose clears it.
- `VOICE-RATE` and the take bands are judgement bands (Chatterbox runs 1.4 to 1.8 words a second); they catch truncated or garbled takes, not taste. They live in `stagegate.py` (`TAKE_S`, `TAKE_WPS`, `TAKE_PEAK`).
- The animatic's caption widths come from one Chrome page, like the real plates, but a plate's final position (face avoidance) is only known after the shots.
- `critic` and `publish` verify the files, not the judgement; the critic's score still decides.
