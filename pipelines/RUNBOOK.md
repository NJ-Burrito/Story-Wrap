# Shot pipeline runbook

🩹 Self-healing (owner, 2026-10-23): every build runs gate, critic, heal until it passes, then it is shown. Loop, limits and guard: [HEAL.md](HEAL.md), setting `heal.json`.

⭐ One shot, one folder, nine stages, one command: `uv run tools/shot.py <stage> <shot-dir>` (`all` runs them in order). The shot folder is `work/shots/<id>/`; `init` writes the id (the folder name) into `shot.json`. The folder must sit inside the repo.
Production crew (13 Sonnet agents in `.claude/agents/sw-*.md`, dispatched by the Lead only): `CREW.md`.
Calm episodes (the format in use, approved on E01 calm v5): the whole chain from script to post, with the cheap check before each expensive step, is `CALM.md`; the daily runner is `DAILY.md`; the creative DO and NEVER list is `bible/craft/calm-format.md`.
Safe stages (owner, 2026-10-25): a verify after EVERY stage of the daily run, an early animatic preview before any shot is drawn, and a hash-based fix that reruns only what changed: `STAGE-GATES.md`.
Voice stage (after the script, before the shot uses a line): `VOICE.md` (casting order from cleaned references, the edge clean, the mastering chain with its pause floor, gen caps per voice; sound bible `bible/sound/`).
Composing stage (shots + voice + captions + music into the gated Reel, `uv run tools/compose.py`): `COMPOSE.md`.
Engagement (replies, likes, reactions and DMs on our own posts for 72 h; Haiku decider; official APIs only; `tools/engage.py run [--go]` every 10 min 08:30-23:30 Amman, `engage.py status`, `dm_auto.py apply --go`; R-460 to R-480): `AUDIENCE.md` "Engagement flow".
Audience loop (post the Reel to Instagram AND the Facebook Page StoryPage through the official Graph API, harvest comments 12 h after the later post, count the two-choice vote from Instagram only (Facebook comments feed ideas), brief the next episode): `AUDIENCE.md`. Tools `tools/ig.py`, `tools/fb.py`; `daily.py post` posts both, each platform recorded separately.
Writing comes first: the writing stage and its machine check are in `WRITING.md` (`uv run tools/bible_check.py bible/series/<series>`).
Reference shot: `reference/mix-v5/` (the owner 10/10). Rules: `kb/rulebook.md`. Checklist and failure table: `bible/craft/README.md`.
Sketch stage (the art book, before any shot): `pipelines/ARTBOOK.md`. A new character or world needs its module (`tools/render/characters/README.md`, `tools/render/worlds/README.md`) and its sheets before a shot can use it.
`tools/shot.py` is built by the pipeline agent. If a file name below differs from what it prints, the tool wins and this page gets fixed.

## 🧭 The order (never skip, never reorder)

Project order (CLAUDE.md, R-001): **research → writing → sketching → animating → composing episodes.** A stage starts only when the one before it is finished for that piece. Writing is always first.

Inside animating, one shot runs:

`init → catalogue → camera → spec → build → trace → record → gate → review`  (`all` runs them in order and stops at the first failure)

- Camera before art. Spec before build. Trace and video from the same run. Gate before the owner sees it.
- A failed stage sends work back to that stage, not forward.
- Files are the checkpoints: each stage writes a file the next reads, so a fix reruns one stage.
- `uv run tools/shot.py status <shot-dir>` prints one row per stage: `ok (fresh)`, the last recorded status, `(stale: inputs changed)` when an input hash moved, or `FAIL [CHECK-ID] message` for a failed stage. The state lives in `<shot-dir>/STATE.json`.

## 👥 Who does what (models by job)

| Job | Model |
|---|---|
| Fetch, download, measure, bulk edits, run commands and report the exit code | Sonnet 5.5 (crew) |
| Research, analysis, gates, coordination, culture review, this runbook | Sonnet 5.5 |
| Creative writing (worlds, characters, script) and drawing (catalogue art, parts, key poses) | Sonnet 5.5 (crew) |

The Lead orchestrates and merges. Workers never instruct each other. The pipeline never calls a paid service (R-009).

## ✅ Rules for every stage

- Run once, report failures, stop on the first FAIL (R-012). A fault opens a heal round (R-402, [HEAL.md](HEAL.md)): the fix is made at the stage that owns the fault and only that stage and the later ones rerun. Run the cheap offline check before each expensive step (R-422, the ladder in [CALM.md](CALM.md)). A failed stage prints `FAIL [CHECK-ID] message` and exits 1; a usage or tool error exits 2. Each run is recorded in `<shot-dir>/STATE.json`. A rerun skips a stage whose input hashes are unchanged and whose outputs exist; `--force` reruns it. Every stage that depends on catalogue data also hashes each catalogue file the shot resolves (all actors' index, refs, grips, expressions, props, writing, world JSON) and the character and world module JS, so editing a grip or pose reruns catalogue to review without `--force`. A stage refuses to run (`PREREQ`) while an earlier stage is not fresh. Gate output goes to `<shot-dir>/gate/`.
- GPU first, CPU light (R-005, R-006). Record only through the local recorder on 127.0.0.1.
- On failure: **fix the root cause** (renderer, catalogue, spec). **Never loosen a gate, delete a check, or edit a trace by hand to pass** (R-396). A threshold moves only with a measured sample and a note in `kb/quality/gate-spec.md` (R-212).
- A check with no data fails; it never passes (R-398).
- No em dashes, no AI slop, no invented numbers (R-011, R-002).

## ⚠️ Known limits

- The review hand crops (`review/sheet-hands.png`) miss the hands in POV shots. Read those frames from the video.
- Character modules exist for Hero, Partner and others in `tools/render/characters/`; the only world with film code is world-a (`tools/render/worlds/world-a.js`). A new character or world needs its module in `tools/render/` plus a `shot.json` entry. Several characters in one shot: see the multi-actor section at the end of this page.
- Rig tolerances and hand thresholds rest on v5 alone (`reference/mix-v5/`), the only measured sample.

---

## 1️⃣ init

- 🎯 Purpose: make the shot folder from the template, with its state file.
- 📥 Inputs: the shot folder name (it becomes the shot id), `--template` (default `shot`, read from `tools/templates/<template>/`), the beat list from the script (R-063), which goes into `plan/camera.py` (BEATS).
- 📤 Outputs: `<shot-dir>/shot.json`, `plan/camera.py`, `plan/spec.py`, `scene/main.js`, copied from the template. An existing file is never overwritten, and `SHOT_ID` in `shot.json` is replaced by the folder name. Also `STATE.json`. `brief.md` and the checklist copy are not made by the tool. `camera/`, `build/`, `out/`, `gate/` and `review/` appear when the stages that fill them run.
- 👤 Who: Sonnet (folders), Sonnet (brief).
- ☑️ Checks: `INIT-TEMPLATE` if the template folder is missing. Script locked for this piece (R-001); every figure in the brief has a cited source or a measured file (R-002).
- 👀 Human look: none.
- 🔧 On failure: go back to writing; do not start a shot on an unlocked script.

## 2️⃣ catalogue

- 🎯 Purpose: look up what exists, build only what is missing (R-318).
- 📥 Inputs: `shot.json` (`uses.refs`, the catalogue files, `new`), `catalogue/characters/<id>/index.json`.
- 📤 Outputs: `catalogue-report.json` listing every pose, angle, expression, grip, prop and garment the shot needs, each as `id@version` or `new` with a build-up sheet (R-306). Its `found` and `to_build` lists hold the two groups. New entries added as the next version (R-347).
- 👤 Who: Sonnet (lookup, list), Sonnet (drawing new entries, key poses, face and hand sheets), Sonnet (hash and index updates).
- ☑️ Checks: shot.py fails `CATALOGUE-MISSING` (a ref or file is neither in the catalogue nor declared in `new`) and `CATALOGUE-FILE` (an index entry points at a missing file). Rules: SPEC POSE-CATALOGUE, ATT-MODEL; hand, prop and face rules R-383, R-385, R-387, R-392, R-393 satisfied by the entries.
- 👀 Human look: new sheets (face, hands, grips) on one tab; the owner sees them before they are used.
- 🔧 On failure: fix the entry (a new version), never the check. Do not draw a pose that is already in the catalogue.

## 3️⃣ camera

- 🎯 Purpose: design every shot before drawing (F3).
- 📥 Inputs: `plan/camera.py` (BEATS, SHOTS, CUTS, optional EXTRA), `shot.json`, the safe boxes per shot (R-332).
- 📤 Outputs: `camera-plan.json` (beats, shots with size, angle, lens, move, duration, `why`, `serves_emotion`, safe boxes, cuts, and the EXTRA text such as `line_180`), one thumbnail per shot as `camera/<shot>.svg` (for example `camera/s1.svg`). The 180 line is written as text in `camera-plan.json`; no overhead plan is drawn.
- 👤 Who: Sonnet (plan), Sonnet (thumbnails).
- ☑️ Checks: shot.py fails `CAMERA-BEATS`, `CAMERA-SHOTS`, `CAMERA-FRAMES`, `CAMERA-CUTS` and `CAMERA-THUMB`. Rules: SPEC CAM-PLAN, CAM-DUR, CAM-VARY, CAM-WHY, CAM-SAFE, CAM-EMOTION, CAM-FILES (R-328 to R-333, R-377); writing staged on the face the viewer sees (R-388); frontal flat camera (R-331).
- 👀 Human look: thumbnails in order.
- 🔧 On failure: change the plan; do not add a move to pass parallax (R-330).

## 4️⃣ spec

- 🎯 Purpose: declare everything the shot must contain, so a gap is caught before art is paid for.
- 📥 Inputs: `camera-plan.json`, `plan/spec.py` (`build(plan, shot, lib)`), the catalogue index, `shot.json`. The field reference is `kb/quality/shot-spec.schema.json`.
- 📤 Outputs: `shot-spec.json`: treatment per beat, depth planes, light, shadows from a mass proxy, interactions, actions, transitions with carriers, texts, emotion tracks, attachments with layer order, poses with catalogue ids. Also `gate/spec.out`, the spec gate output.
- 👤 Who: Sonnet (declares, runs the gate), Sonnet (the emotion and transition choices that are creative).
- ☑️ Checks: shot.py fails `SPEC-CATALOGUE` when a catalogue ref in the spec neither exists nor is declared new, and otherwise runs `uv run tools/quality_gate.py spec <shot-dir>/shot-spec.json --files --root <repo>`, which must print PASS. Rules: R-201 to R-211, R-300, R-315, R-320 to R-339, R-350, R-352, R-357 to R-359, R-360 to R-378.
- 👀 Human look: none.
- 🔧 On failure: fill the missing field or change the plan. If a field is impossible, the shot design is wrong, not the schema.

## 5️⃣ build

- 🎯 Purpose: the renderer, so each declared rule is true in the picture.
- 📥 Inputs: `shot.json`, `scene/main.js`, `camera-plan.json`, and the shared renderer `tools/render/` (one copy for every shot).
- 📤 Outputs: `build/` written by `shotlib/page.py`: `index.html` (loads the shared renderer and the shot's `scene/main.js`), `shot-config.js` (from `shot.json`), `manifest.json` (input hashes), `diag.json` (written by the load run). The renderer must show: 2D draw (R-380), one connected silhouette (R-381), grips blended (R-386), ink revealed under the nib on the touched face (R-387 to R-390), layer order per angle (R-392).
- 👤 Who: Sonnet (code that draws), Sonnet (code that measures and exports), Sonnet (bulk edits).
- ☑️ Checks: shot.py runs `node --check` on every script (`BUILD-SYNTAX`), loads the page in the recorder (`BUILD-LOAD`), and compares the frame count with fps x duration (`BUILD-FRAMES`). Rules: the renderer must export what the gates need (R-398); no gradient volume, blur shadows or full-frame grade (R-380).
- 👀 Human look: stills at the worst frames (hand switch, writing, seams, shadows) before the record.
- 🔧 On failure: fix the renderer. Do not change the rule or the trace.

## 6️⃣ trace

- 🎯 Purpose: export the numbers the gates read, in the same run as the video. The pass runs `Shot.record({video:false})` in the recorder, with no video.
- 📥 Inputs: `build/` (`index.html`, `shot-config.js`, `manifest.json`).
- 📤 Outputs: `out/rig-trace.json` (schema: `kb/quality/rig-trace.schema.json`: joints, per-finger values, contacts, layers, prop faces, nib, ink) and `out/masks/text/`, `out/masks/shadow/`, `out/masks/line/`, one `NNNN.png` per frame that has a mask (the frame number in the name).
- 👤 Who: Sonnet.
- ☑️ Checks: shot.py fails `TRACE-INCOMPLETE` when an actor's traced frames are not exactly its declared frames (default: all fps x duration; an actor that enters, exits or is cut between declares `present: [[f0, f1], ...]` in `shot.json` and the spec's `actors[].frames`, checked by `ACTOR-RANGE`), or when a shadow or line mask is missing on one of its `f % 6 == 0` frames. The scene draws an actor only on its declared frames; the recorder refuses a mismatch. The trace follows the schema; no field is a constant that hides motion (F13: max over fingers, one forearm value for every frame).
- 👀 Human look: none.
- 🔧 On failure: fix the exporter. A trace edited by hand is a failed run.

## 7️⃣ record

- 🎯 Purpose: the one video the gate measures and the owner watches.
- 🎯 Purpose: the one video the gate measures and the owner watches. Deterministic frame-counter capture.
- 📥 Inputs: `build/`, and the recorder: `tools/record/server.py` serves the repo root on 127.0.0.1; `tools/record/driver.py` opens GPU Chromium on the shot page and runs `Shot.record({data:false})`.
- 📤 Outputs: `out/<shot-id>.mp4` (1080x1920, 24 fps, H.264 on NVENC) and `out/<shot-id>.encode.json` (ffmpeg exit code, frame count, encoder).
- 👤 Who: Sonnet (runs it), Sonnet (checks the exit code).
- ☑️ Checks: shot.py fails `RECORD-INCOMPLETE` (the pass did not finish), `RECORD-ENCODE` (ffmpeg exit not 0, or frame count not fps x duration) and `RECORD-FORMAT` (ffprobe: h264, 1080x1920, 24/1, frame count, yuv420p). Rules: ffprobe size, rate and frame count (R-110, R-399); encoder is `h264_nvenc` (R-113, read from encode.json).
- 👀 Human look: none yet.
- 🔧 On failure: fix the recorder or the page; record again only after a fix, never as a retry.

## 8️⃣ gate

- 🎯 Purpose: measure every rule a machine can.
- 🎯 Purpose: measure every rule a machine can.
- 📥 Inputs: `shot-spec.json`, `out/rig-trace.json`, `out/masks/`, `out/<shot-id>.mp4`, `previews/index.html`.
- 📤 Outputs: `gate/<name>.out` for each of the seven gates (spec, rig, hands, extras, look2d, preview, render), each carrying the verdict PASS on a clean run. Also `gate/look2d.json`, `gate/render.json`, `gate/report.json` and `gate/report.txt` (one verdict per gate).
- 👤 Who: Sonnet (runs and reads), Sonnet (runs).
- ☑️ Checks, all must pass. shot.py runs all seven even when one fails, then stops with `FAIL [first-id] gate failed: ...` and lists the failing ids; details are in `gate/report.txt`.
  - `quality_gate.py spec <spec> --files --root <repo>`
  - `quality_gate.py rig <trace> <spec>` (limits, hinge, segments, contacts, attach, layers, shoulder, balance, eyes, blink, shadow holes, seams)
  - `quality_gate.py hands <trace>` (HAND-TOPO, HAND-SIDE, HAND-SWAP, PROP-FACE, WRITE-REVEAL, NIB-CONTACT, LAYER-GRIP)
  - `quality_gate.py extras <video> <spec> --text-mask-dir out/masks/text --shadow-dir out/masks/shadow`
  - `quality_gate.py render <video> --quiet --json gate/render.json` (motion, light, depth)
  - `quality_gate.py look2d <video> --json gate/look2d.json` (R-380)
  - `quality_gate.py preview previews/index.html` (R-382)
- 👀 Human look: none; but read the numbers against `reference/mix-v5/*.out` (flat layout) and `reference/mix-v5/mix-v5.render.json` (R-397), and the new ones in `<shot-dir>/gate/`.
- 🔧 On failure: read the failing id, find its F-note in `bible/craft/README.md`, fix the root cause (R-396). Never loosen a threshold. If you believe a threshold is wrong, take a measured sample and follow R-212.

## 9️⃣ review (the one human look)

- 🎯 Purpose: the things no gate can see.
- 🎯 Purpose: the things no gate can see.
- 📥 Inputs: `out/<shot-id>.mp4`, `out/rig-trace.json`, `shot.json` (its `review` block sets the cadence: `hands_every`, `faces_every`, `props_every`, `frames_every`), and the gate outputs in `gate/`.
- 📤 Outputs from shot.py: `review/sheet-hands.png`, `review/sheet-faces.png`, `review/sheet-props.png`, `review/sheet-frames.png` and `review/index.json` (tile counts and labels). The reviewer's notes go in `review.md`, which shot.py does not write: each F-number marked absent or present with a frame number; sound-off and picture-off read-out (R-379); cuts and transitions looked at frame by frame (R-325, R-326); unbuilt checks listed (R-309, R-316, R-321, R-322 cadence).
- 👤 Who: Sonnet reviewer seat (culture and craft), then the owner.
- ☑️ Checks: shot.py fails `REVIEW-EMPTY` when no frame can be extracted. Rules: R-097, R-379, R-401.
- 👀 Human look: this is it. One look. After a fix the gates re-run; nobody re-inspects by eye unless the owner asks (R-012).
- 🔧 On failure: a present fault that is the owner's gets a new F-number, a root cause, a rule and a check (R-395), then the shot goes back to the stage that owns it.

---

## 📺 Showing the owner (R-394)

1. Add **one new TAB** to `previews/index.html`. Never a new file. At most 4 tabs: older ones move to `previews/archive/index-<date>.html`, kept (R-423, `PREVIEW-MAX-TABS`).
2. The tab plays the **recorded video** the gate measured (R-382), autoplay, with the gate table beside it.
3. Open it in his browser on that tab at once: `index.html#<tab>`. Serve over 127.0.0.1; Playwright MCP blocks `file://`.
4. Tell him what to look at, in one line.
5. ADHD-friendly: hook first, short emoji-led blocks, one idea per block, visuals over paragraphs, choices as big clear cards.
6. Close what you opened: browser, recorder, background commands.

## 🗣️ Recording feedback (R-395)

1. Open `bible/feedback/<date>-<name>.md`.
2. Write the note **verbatim** as the next number (F16, F17... for a film shot; C14... for the calm format), under the version he scored.
3. Add the score if given.
4. Same session: root cause in `kb/quality/rca-*.md`, rule in `kb/rulebook.md` (a new number; old numbers never change), long text in `bible/craft/`, check in the gate, and a row in the failure table in `bible/craft/README.md` (F table or C table).
5. Never edit his words. Never delete a note.

## 🚦 `shot.py all`

Runs the nine stages in order, skipping any stage that is already fresh. It prints `[stage] running` and `[stage] ok` lines as it goes. It stops at the first FAIL and prints `FAIL [CHECK-ID] message`. On success it prints `OK` with each stage's result. It never retries. It does not do the human look: the review stage only makes the sheets.

## 🖼️ Art book check on every shot

Every film rig, close-up and shot keeps the approved art-book proportions, hands, faces and costume (R-419). Reference values: `uv run tools/artbook_proportions.py [<id>]` writes `catalogue/characters/<id>/artbook-proportions.json`; the gate check `ART-PROPORTION` compares what the trace says was drawn (8 % tolerance). Readability in a close-up comes from the camera, never from a bigger hand.

## 🧪 Rehearsal

When the pipeline itself is new or changed since its last good delivery, one private rehearsal on a tiny throwaway shot is allowed and the owner approves the plan before any full render (CLAUDE.md). It is not shown to him and not repeated.

---

## 👥 Several characters in one shot (multi-actor engine, 2026-10-23)

- 🎯 Purpose: one shot with two or more characters (Hero and Partner in the office) that interact: contact, a prop handed over, who stands in front. Same nine stages and `shot.py all`; what changes is the engine under them.
- 🔀 Which path: a `shot.json` with `actors[]` (and no `character`) is a multi-actor shot; one with `character` is the v5 path, untouched. Reference for the v5 path stays `mix-v5-repro`. Worked multi-actor example: `work/shots/smoke-partner/` (one actor, 2 s; same files a two-actor shot has). Template: `uv run tools/shot.py init work/shots/<id> --template shot-multi`.
- 🧱 Engine: `tools/render/actors.js` (registry, isolated module loader, draw order), `trace-multi.js` (trace, masks, recorder), `bootstrap-multi.js`. API, scene contract and module requirements: `tools/render/characters/README.md` ("Several characters in one shot").
- 📝 **shot.json**: `actors: [{id, module, z, layer, catalogue, uses}]`, optional `draw_order` windows; library `core, geom2d, world, face, hands, actors, @scene, trace-multi, bootstrap-multi`. The catalogue stage looks up every actor in its own character catalogue.
- 📝 **Spec** (`plan/spec.py`): `actors[]` (id, module, `depth_z`, `layer`, `catalogue_refs`) plus one `characters[]` rig entry per actor id; per beat `draw_order` (back to front, farther first; windows tile the beat; a split `["partner:body", "hero", "partner:arms"]` or a change needs a why), `actor_emotions{id: {emotion, emotion_track}}` (each actor feels on its own track), a pose and a cast shadow per actor; `actor_interactions[]`: `contact` (hand to hand, hand to an object the other holds: `held_by`) or `handover` (`prop`, `giver`, `receiver`, `handoff_frame`, `both_hands_frames` >= 3). Fields: `kb/quality/shot-spec.schema.json`.
- 🎬 **Scene** (`scene/main.js`): per actor a pose state in `buildSim`; `renderFrame` solves each actor (`actorSolve`), draws the set, then `drawActors(orderAt(f), per, between)`, and returns `L` with `draw_calls` and `props` (the prop's `parent` hand and each hand's measured `gap_px`). A handover is one prop whose `parent` switches from the giver's hand to the receiver's on `handoff_frame`, with both hands on it for the frames before.
- 📤 **Trace**: `characters[<id>]` per actor (all per-character blocks, masks in `masks/<kind>/<id>/`) and `scene.frames` (`present`, `draw_order` as run, `depth`, `props`). Schema: `rig-trace.schema.json`.
- ☑️ **Gate**: rig, hands, seam and shadow checks run per actor (the message names the actor). New ids: spec `ACTOR-DECLARED`, `ACTOR-ORDER`, `ACTOR-EMOTION`, `ACTOR-INTERACTION`, `SHADOW-ACTOR`; trace `ACTOR-TRACE`, `ACTOR-OCCLUSION`, `ACTOR-CONTACT`, `HANDOVER`. Table, numbers and findings: `kb/quality/gate-spec.md` section N. Tests: `tools/tests/test_multi_actor.py`.
- ⚠️ Known limits: the two-actor thresholds are defaults (no measured two-actor shot yet). Hand-to-hand contact needs the scene to export the touching point of each hand (done by `trace-multi.js` as `contact_points.hand_L/hand_R`); a contact elsewhere (a shoulder, a prop edge) is named in `traceExtra` or `props[].touch`. `RIG-SHOULDER` fails one-armed gestures (raised arms more than about 36 degrees apart): see gate-spec section N. Partner's fist grips exceed the soft finger limits (`fear-thumb-R`, `push-finger-L`): use another grip or give `partner-v1` a sourced override.
- 🔧 On failure: same rule as every stage: fix the root cause (scene, module data, spec), never the gate.

## 🎓 Learning phases (2026-10-26)

After each episode is made the daily `retro` stage runs, and 14 h after the later post the Harvest tick runs the audience review (`tools/learn.py`). Both write the craft playbook, the lessons ledger and the next brief; code, rule, template and gate changes are proposals only. See `LEARN.md`.

## 🩹 Healing (optional stage, on by default)

Replaces the old "fix after the owner's note" path for shots. A failing gate sends the shot into a heal round at the stage named by the class (`rerun_from`), not by hand.
- After the gates: `uv run tools/shot.py heal <shot-dir>` (also the last line of `shot.py all)` writes `heal/critic-brief.md` and, if anything failed, `heal/fix-brief.md` in the shot folder. A Sonnet critic answers `kb/quality/critic-checklist.md` into `heal/critic.json`; `heal.py classify` maps each fault to a class, a fix place and a fixer (`kb/quality/heal-playbooks.md`); the fixer repairs the root cause, records it with `heal.py round`, and the stage reruns. Up to 3 rounds; then stop and report.
- the owner sees this only when `uv run tools/heal.py status <dir>` says ready: all gates pass, critic score 9 or more of 10, guard clean. Never loosen a gate, edit a trace or hide a fault; the guard refuses it.
- Then `heal.py learn` writes each healed fault to `kb/lessons/ledger.jsonl`. Full loop: [HEAL.md](HEAL.md).

## 🎙️ Voice first, captions in compose only, a live end card (E01 run 1, 2026-10-24)

- 🎙️ **Voice first.** The voice stage (VOICE.md) runs before the spec. A piece's `plan/spec.py` lists `voice_lines: [{line, start_s, speaker, on_screen}]` (seconds from the piece start) and may call `lib.voice_take("L03")` for the measured length and viseme track while it plans beats and cuts. The spec stage sets `voice_episode` from `shot.json` `piece.episode`, resolves every entry from `work/voice/<ep>/` (measured `dur_s`, `end_s`, take path and hash, viseme keys on the piece clock) and fails `SPEC-VOICE-TIMING` when a referenced line has no measured take, no viseme track, or runs past the piece without `spans_out`. A beat that names `emotion_track.voice.line` must have that line in `voice_lines`. No estimate is ever accepted.
- 🔤 **No captions in a piece.** A piece never draws dialogue captions (`PIECE-NO-CAPTION`, spec and render): no text with `role: caption`, a `caption-bar` plate or a `speaker`. Diegetic text (a tag, card, sign in the world) stays and is marked `diegetic: true`. `compose.py captions` owns every dialogue caption (COMPOSE.md).
- 🎭 **Actors that come and go.** `shot.json` `actors[].present` and the spec's `actors[].frames` list `[f0, f1)` ranges; masks and checks are per actor range; beats list only the actors present for the whole beat (`ACTOR-RANGE`).
- 🎬 **Compose reads the piece.** A shotlist line may omit `at_s`: compose places it at the piece spec's `start_s` minus `in_frame / fps` (`PLAN-VOICE-OFFSET` if both are given and disagree, or if the take changed since the spec).
- 🃏 **End card over live footage.** `end_card.backdrop`: `live-loop` (default), `live-hold` or `static` (COMPOSE.md section 5).

## 📏 Parallax estimator report (2026-10-24, same threshold 0.10)

The estimator now takes up to 32 evenly spread frame pairs among 96 candidates (was 10 fixed positions) and reports spread, a bootstrap interval and a confidence. The table is filled by the rerun on the E01 episode and its pieces (numbers in `work/episodes/E01/gate/parallax-2026-10-24.json`).

PARALLAX_TABLE_PLACEHOLDER

## 📏 Line fit: a voiced line must fit its slot (owner, 2026-10-30, R-502)

- **Why.** The plan stage refuses a take longer than its slot (recap card 3.0 s, scene 10 s, intro 9 s, choice sequence 16 s) and a line is voiced once, so E04 (2026-10-29) and E05 (2026-10-30, recap line H01, 3.88 s) were parked for the day.
- **Prevention (script stage).** `tools/line_fit.py`: each line's seconds are estimated from its Arabic letters and the straight line fitted to the real takes in `tools/line_fit_rates.json` (`uv run tools/line_fit.py calibrate --root <main tree> --write` rebuilds it from the narration manifests; `limits` prints the numbers the writer brief carries; `check <episode-dir>` tests an episode). A line over its slot is sent back to the writer with its letter budget (`SCRIPT-FIT`, at most 2 repair rounds); what remains is a warning, never a stop.
- **Cure (after voicing).** `daily.py run` catches `PLAN-DURATION` at the plan stage and calls `tools/line_refit.py`: one small Sonnet call per over-long line (Read + Write under `work/daily/` only) rewrites ONLY that line shorter under a new id (`H01` -> `H01r1`); `script.json` and `calm-plan.json` point at it; `voice.py refit-mark` lets the voice stage voice only the new id, once; plan and the later stages rerun. Old takes stay, unused. Bounds: 2 rewrites per line, 6 lines per episode, the day's token budget and the 4 h cap; `work/daily/<ep>/refit.json` is the record.
- **By hand / from the Lead.** `uv run tools/daily.py refit --ep E05 [--line H01] [--dry]` (dry names the lines over their slot and changes nothing); the Lead repair has the action `refit-line`. After a merge, an episode already parked by `PLAN-DURATION` is picked up by the next autopilot tick (it is not stuck while the refit has rounds left) or by `daily.py refit --ep <ep>` at once.

## 🔁 Reading-time heal: a plate up too briefly is fed back to the plan (owner, 2026-10-30, R-503)

- **Why.** The plan estimates the last plate of a line from the text; the animatic measures the real plates. E05 stopped on `CAP-READING-SPEED` (L06 unit 0 up 1.23 s, least 1.50 s): the FIRST sentence of a line, which `read_hold` (a pause after the scene) cannot reach.
- **What runs.** In `daily.py run`, when the animatic verify fails on `CAP-READING-SPEED` / `CAP-READ-TIME`, `tools/read_heal.py` writes the measured shortfall + 0.1 s into `work/daily/<ep>/read-heal.json` (`lines.<id>.lead` for a short first sentence, `.hold` for a short last one), reruns plan and animatic. 2 passes per run, 4 per episode, at most 3 s extra per scene. A sentence in the middle of the take is not curable by the plan: the stop stays and the Lead/writer shortens the line. Every heal is a lessons-ledger entry.
- **Autopilot.** A reading-time stop with heal rounds left is neither terminal nor stuck (`heal_pending`, like the refit); the Lead repair is allowed once per (episode, stop code) per day (`state["lead"]["E05|CAP-READING-SPEED"]`), at most 3 codes per episode a day. `MAX_ATTEMPTS` still counts transient causes and unhealable stops.
- **Resume an episode parked by it.** Nothing to reset: `uv run tools/daily.py run --ep <ep>` (or the next autopilot tick) heals and goes on. `rm`-free reset if a heal ever must start over: delete `work/daily/<ep>/read-heal.json` with `safe-delete`.

## 🔁 Depth heal: a shot that fails a depth gate is re-layered (owner, 2026-10-30, R-504)

- **Why.** E05 stopped on `SHOT-GATE E05-s01: render FAIL parallax_corr` (0.063 against the unchanged gate >= 0.10; the other 15 shots: 0.107 to 0.461). The shot was one flat figure plane under a 3 % dolly, with nothing on its own plane. Same shape as E01C's prop inserts (calm.py `t_insert_depth`), which a hand-made real-depth template cured.
- **What runs.** In `daily.py` s_shots, when `shot.py all` fails and every failing gate is `parallax_corr` / `depth_bands`, `tools/depth_heal.py` re-resolves the shot with the next rung of `RUNGS` (see the module: a longer dolly, a slight sideways drift, then the near tags), writes it and gates it again; only that shot is rendered again (about 4 to 10 minutes). 2 rounds per run, every rung once per shot. The rung is stored in `work/daily/<ep>/depth-heal.json` and applied to the shot's plan parameters on every later run (a healed shot stays cached). Every round is a lessons-ledger entry (`source: depth-heal`). Nothing is loosened: the same gates judge every rung, CALM-MOTION included.
- **Autopilot.** A `SHOT-GATE` stop that names a depth gate is neither terminal nor stuck while a rung is left (`depth_heal_pending`, part of `heal_pending`). When all rungs are spent the Lead repairs once per (episode, stop code) per day.
- **Resume an episode parked by it.** `uv run tools/daily.py run --ep <ep>` (only `shots` and later stages rerun; the passed shots are cached). The autopilot's `attempts` and the `stuck:<ep>` todo of the old stop may be cleared by hand but are not needed. Reset a heal: delete `work/daily/<ep>/depth-heal.json` with `safe-delete`.


## 📺 YouTube and stories after the Reels (2026-10-25)

- 📺 **Order:** Instagram Reel, Facebook Reel (scheduled +60 min), then `yt.py publish` (needs `post.json`), then `stories.py announce` (each platform only once its Reel is live). Next morning `stories.py vote-due` posts the result card. Dry run by default, `--go` posts; one record per part (`youtube.json`, `stories.json`), never repeated without `--force`. Detail: [AUDIENCE.md](AUDIENCE.md) "YouTube and stories".
- 🔑 **Credentials:** `~/.config/story-wrap/youtube-token.json` (+ `youtube-client.json`), Google project `story-publisher`, channel YOUR_CHANNEL_ID. `uv run tools/yt.py status --live` is the read-only check. Stories reuse the Instagram and Facebook tokens in `instagram.env`.
- 🔒 **Private lock:** until the YouTube API audit passes every upload is private; `youtube.json` `privacy_actual` / `locked_private` and a Health alert show it. Do not re-upload to work around it.
- 🧩 **Playlist needs one more scope** (`https://www.googleapis.com/auth/youtube`); until the owner authorises it the upload works and `playlist_error` says so.
- 🧪 **Tests:** `tools/tests/test_yt.py`, `test_stories.py` (mocked HTTP, no browser; one real-ffmpeg smoke test). Cards are drawn by Chromium in `stories._render` (Thmanyah, real Arabic shaping) and are not covered by the unit tests.
- 🛂 **Posting E01C:** `uv run tools/adopt.py adopt E01C --approved-by the owner --reason "..."` once (refuses unless the gate is PASS on this exact file); the Post task then posts it. Detail: AUDIENCE.md "Posting an approved episode without rebuilding it".
- 🔒 **YouTube privacy:** private until `work/state/yt_audit_passed` exists. **Retention:** the Harvest task prunes YouTube comment rows older than 30 days; `yt.py forget --go` deletes everything stored.

## Loop gate and Health (audience loop)

- The next episode waits for the **latest posted or adopted episode with a lower number** (`loop_gate.predecessor`), not for the arithmetic `N-1`: with E01C adopted, E02 waits for E01C to be posted and harvested, never for E01. Suffixed ids (E01C) are understood by `prev_ep`, `pick_episode` and `next_episode`; an adopted episode is never resumed by the Daily run.
- Health rules (own status skipped, Amman-day token budget, no render-cap alert for posted/finished/adopted episodes, stale statuses dimmed, silent Board/Harvest = alert): `board/README.md`, section "How Health decides".
- `tools/register-tasks.ps1` builds repetition windows in minutes (`for_h` 1.5 is 90 minutes, not 2 h). Re-register with `-DryRun` first.

## 🔧 A stop always gets a cure, and a finished episode always posts (owner, 2026-10-30, R-506 and R-507)

- **The stop code is the child's.** `calm_compose.py captions E05: FAIL [CAP-FACE-CLEAR] ...` is stop code `CAP-FACE-CLEAR` in STOPPED.md, `autopilot.json` and the board (before it was `CHILD`, which no heal and no retry rule could read).
- **Plate too big (`CAP-FACE-CLEAR`, `CAP-SAFE`, `CALM-PLATE-SAFE`).** `tools/cap_heal.py` cuts the plate (`work/daily/<ep>/cap-heal.json`), reruns animatic and shots and compose; if no cut is left the line is reworded shorter (R-502, new id, one take). 3 cuts a run, 5 an episode, 2 rewrites an episode. See the Build panel row "plate cut".
- **The general fixer.** Lead repair gave up, or the episode is backed off, and no specific heal has a round left: `autopilot.try_fixer` runs one headless Sonnet session (template `tools/templates/autopilot-fixer.md`) limited to the episode's plan, caption data and `work/daily/<ep>/**`, then `daily.py run` again. Once per (episode, stop code) per day, 3 per episode per day, 150 000 tokens must be left. Its edit is rolled back if it touches a voiced line, `narration-manifest.json` or fails plan validation. Still failing: `FIX-REQUEST.md` stays red.
- **Late posts (R-507).** A complete episode whose 19:00 slot has passed is posted by the autopilot at its next tick, however late, past midnight too; never before the slot; one post run at a time (`work/daily/post.lock`, shared with StoryWrap-Post, whose 19:00 to 20:25 window is untouched). `PUBLISH-FAILED` is red until it posts, 8 tries a day. After a late post the harvest is due 14:00 the day after the post's slot day and at least 12 h after the post.
- **After the merge (the Lead).** Nothing to register. E05's `STOPPED.md` still names `[CHILD]` ... `[CAP-FACE-CLEAR]`; the code fingerprint changed, so the next tick retries E05 at once and `heal_pending` is true. If E05's entry sits in `work/daily/autopilot.json` `attempts`, it is dropped by the fingerprint check; nothing to delete.

## 🕒 The autopilot never waits to be asked (owner, 2026-10-30, R-505)

- **Why.** E05 stopped four times in one day (`PLAN-DURATION`, `CAP-READING-SPEED`, `SHOT-GATE`) and each time sat idle until a person asked: the task ticked only 14:00 to 18:30, and after three failures `decide()` parked the episode until tomorrow.
- **Schedule.** `board/schedule.json` StoryWrap-Autopilot: every 15 min from 00:00, no `for_h`. Register once (the Lead): `powershell -ExecutionPolicy Bypass -File tools
egister-autopilot.ps1 -DryRun`, then without `-DryRun`. Per-user, Interactive, Limited (no admin), no WakeToRun (a tick every 15 min must not wake the PC all night; the first tick after it wakes catches up). StoryWrap-Post at 19:00 and the 14:00 harvest rule are unchanged.
- **Retry rules.** Code or input changed since the failure: retry at once. Unchanged: back off 2 h, 3 extra retries a day, then wait for a change or the next day. Never past the 4 h machine cap or the token budget. The Lead repair runs once per stop code per day.
- **Watch it.** Board, Today tab and the banner on every tab; `uv run tools/build_status.py` prints the headline and the red items. `work/daily/<ep>/FIX-REQUEST.md` is the precise request for the next session.
- **Reset.** Nothing to reset after a merge: the code fingerprint changes and the next tick retries. To force a retry without a change, delete the episode's entry from `work/daily/autopilot.json` `attempts` (safe-delete the file only if it is corrupt).
