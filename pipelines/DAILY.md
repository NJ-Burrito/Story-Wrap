# 📆 The daily run

➡️ The calm pipeline step by step, with the cheap check to run before each expensive step: [CALM.md](CALM.md). This page is the runner (`daily.py`), its limits and the plan schema.

⭐ **One command makes one calm episode a day, unattended, free, in under 4 hours of machine time.** `uv run tools/daily.py run` (owner, 2026-10-24: "Target pipeline" and "Calm format" in `CLAUDE.md`).

🧠 **Calm format = his pacing, our art.** Slow shots, holds, one subject, one narrator, full-sentence captions with the spoken word highlighted, a fixed wrapper. Our 2D ink characters and the world-a set stay. Evidence: `research/stickman-recipe.md`. Plan: `research/stickman-replication.md`.

## 🧭 The day in one table

| # | Stage | Who | Machine? | Leaves | Stops the run when |
|---|---|---|---|---|---|
| 1 | `votes` | `ig.py comments`, `vote.py tally/next` | no | `decision.json`, `next-brief.md` | (skipped: no posted episode or no token) |
| 2 | `script` | writer agent, headless Sonnet | no | `script.json`, `calm-plan.json`, `caption.txt` | plan fails the deterministic checks twice |
| 3 | `voice` | `voice.py` Chatterbox, local GPU, **one take per line**; per take: edge clean, then the mastering chain ending in the pause floor (R-472); cast voices and gen caps: [VOICE.md](VOICE.md) | yes | `work/voice/<ep>/L*.trimmed.wav` | a take fails its gate |
| 4 | `plan` | `calm_compose plan` (in process) | no | `work/episodes/<ep>/timeline.json` | the timeline is not renderable |
| 5 | `animatic` | `tools/animatic.py` (early preview: real voice, timeline, captions, mix; flat low-res picture) | yes | `animatic/animatic.mp4`, `animatic/report.json`, `mix.wav` | a caption, timing, gloss or mix check fails |
| 6 | `shots` | `calm.py` templates, `shot.py all` | yes | `work/shots/<ep>-<scene>/` + cards | a shot fails a gate |
| 7 | `compose` | `calm_compose.py` (captions, the animatic's mix, assemble) | yes | `work/episodes/<ep>/episode.mp4` | an ffmpeg step fails |
| 8 | `gates` | `calm_compose.py gate` | yes | `work/episodes/<ep>/gate/report.json` | any calm check fails |
| 9 | `critic` | critic agent, headless Sonnet | no | `work/episodes/<ep>/heal/critic.json` | score under 9 after 2 heal rounds |
| 9b | `retro` | `learn.py retro`, one headless Sonnet call on the day's token budget | no | `work/episodes/<ep>/learn/retro.json` | never stops anything: a failure is reported, the stage ends `skipped`; see `LEARN.md` |
| 10 | `post` | `daily.py post` → `ig.py publish --go` | no | `post.json` | gates red, critic under 9, or no token |
| 11 | `schedule` | `ig.py plan` | no | `harvest-task.txt` (**not registered**) | |
| 12 | `yt_stories` (post stage) | `post_extra.py`: YouTube, the stories, then the **after-post steps A1-A5** (first comment, catch-up pass, sticker-story card, peer comment drafts; `after_post.run_all`) | no | `youtube.json`, `stories.json`, `first-comment.json`, `after-post/sticker-story.json`, `board/data/after-post.json` | never stops the run: a step that waits or fails makes the stage `partial` and the next Post tick repeats it; see AUDIENCE.md "After the post" |

🛡️ **After every stage a verify runs and the next stage waits for it** (contract of outputs and input hashes, then the stage's own gates). A failure stops with the check id and a fix brief in `STOPPED.md`. A rerun reruns exactly the stages whose input hashes changed: **[STAGE-GATES.md](STAGE-GATES.md)**. `daily.py stale <ep>` shows what a fix would rerun, `daily.py verify <ep> [stage]` re-verifies, `work/daily/<ep>/timings.jsonl` holds the seconds of every stage and verify.

🔁 A rerun skips every stage that is fresh (ok, outputs present, input and output hashes unchanged, verify passed). `--force STAGE` reruns one. State: `work/daily/<ep>/STATE.json` (status, seconds, info, inputs, outputs, verify per stage).

## 📌 After the post (A1-A5, R-483 to R-490)

The `yt_stories` post stage (and the StoryWrap-Post tick, every 5 minutes from 19:00) also runs the five after-post steps for each episode: **A2** the first comment of ours under the Instagram Reel at once and under the Facebook Reel when it goes live (automatic), **A4** the catch-up pass that opens the windows of earlier episodes for 36 h (automatic, the engagement ticks do the replies), **A1** the sticker-story card and **A3/A5** the peer comment drafts for the owner to post by hand (drafts only, on the board). Dry without `--go`. Details and rules: **[AUDIENCE.md](AUDIENCE.md)** "After the post: five steps (A1-A5)".

## 🤖 The autopilot (owner, 2026-10-27, R-491 to R-495)

"Always push at 7pm, harvest at 2pm the next day, start the next episode immediately without coming back to me." `uv run tools/daily.py autopilot` (tools/autopilot.py) is the one entry the **StoryWrap-Autopilot** task runs: every 15 minutes around the clock (R-505, 2026-10-30; before it fired 14:00 to 18:30 only and a later stop sat idle until someone asked), per-user and no admin, run only when logged on, StartWhenAvailable, no WakeToRun, no overlap, 5 h limit (`tools/register-autopilot.ps1`; it disables StoryWrap-Daily and moves StoryWrap-Post to 19:00). The launcher `tools/autopilot.ps1` opens VS Code on this folder if no Code.exe runs, runs the autopilot headless (it starts the Claude jobs for writer, critic and healer itself) and, on exit code 6, starts ONE headless Lead session.

One run decides one thing from the files (`autopilot.decide`) and is idempotent behind `work/daily/autopilot.lock`:

| Case | When | What |
|---|---|---|
| (a) finish | an episode is built (started) but not complete: no gate PASS + critic 9 + retro | `daily.py run --ep E`: critic, heal within `pipelines/heal.json`, retro. No harvest. If the loop gate waits for a harvest that is due, that harvest is done first |
| (b) harvest, then build | 14:00 the day after the latest post and that post is not harvested | harvest (`ig_board.harvest_cycle`: comments, replies, vote tally on Instagram, next brief, metrics, learning review; `inbox.py harvest` for DMs; live numbers), then `daily.py run` for the next episode (votes, script through critic and retro) |
| (c) build | the latest post is harvested and nothing is started | `daily.py run` for the next episode |
| idle | waiting for 14:00, complete and waiting for the 19:00 post, or stuck for today | one log line, exit 0 |

It **never posts** (the Post tick does, at 19:00, only when every gate passed, the critic scored 9 or more and the episode was ready by the slot). Exit codes as `daily.py`: 0, 1, 3, 4, 5, plus **6 = needs the Lead**. A transient failure (timeout, child error, critic call failed) is retried by the next tick up to 3 times a day; **a take over its slot (`PLAN-DURATION`) is cured inside the run (R-502, 2026-10-30): `tools/line_refit.py` rewords that line under a new id (H01 -> H01r1), voices only it once and plans again, so such an episode is never terminal or stuck while the refit has rounds left (`autopilot.refit_pending`; `work/daily/<ep>/refit.json`), and the script stage already sends a line over its slot back to the writer before any voice is made (`tools/line_fit.py`, `SCRIPT-FIT`); a deterministic stop (heal rounds spent `CRITIC-LOW`, a gate, the render cap) is not retried: exit 6, and the launcher runs `daily.py autopilot --lead` once per episode per day: a headless Sonnet session (`tools/templates/autopilot-lead.md`; the flags of `daily.build_cmd`: `NJ_ROLE=job`, dontAsk, capped turns and budget, no shell) reads `handoff.md` and the log and writes `work/daily/autopilot-lead-<date>.md` and one decision (`rerun`, `rerun-stage` of plan/animatic/shots/compose/gates/critic/retro, `refit-line`, or `give-up`) which the autopilot executes. The session never commits, posts or loosens a gate. Budget: `SW_LLM_DAILY_TOKENS=5000000`, the default for every run (the owner 2026-10-28; one episode used about 1 M); the 4 h machine cap per episode stays.

**Every stop code is a real code, and a stop with no heal gets a fixer (R-506).** A failing child tool raises its own check id (`daily.inner_fail`), never a bare `CHILD`. A plate with no place on screen (`CAP-FACE-CLEAR`, `CAP-SAFE`, `CALM-PLATE-SAFE`) is cut in two by `tools/cap_heal.py` (`work/daily/<ep>/cap-heal.json`), else its line is reworded shorter under a new id. When no specific heal has a round left, the autopilot starts ONE bounded headless fixer session (`autopilot.try_fixer`; once per episode and stop code per day, 3 per episode per day; Read/Edit/Write on the episode's data and `work/daily/<ep>/**` only, no shell, no tools/, no gate, no voiced line), validates and, if needed, rolls back its edit, and runs `daily.py run` again; the result is in `work/daily/<ep>/fixer.json`, the ledger and the Build panel.

**Never parked silently (R-505).** After the bounded heals and the Lead repair of a stop code, the next tick checks again: when `tools/` code, a template, `pipelines/heal.json` or any episode input file changed since the failure (`autopilot.code_fingerprint` is stored with each failure) the episode is retried at once; otherwise it is backed off, not parked: one retry 2 h after the last failure, at most 3 extra a day, never past the 4 h machine cap or the day's token budget (`autopilot.parked`). A stop nobody can heal (or a Lead `give-up`) writes `work/daily/<ep>/FIX-REQUEST.md` (stop code, files, measured numbers, heals that ran, suggested change) and the board shows it in red; the file is renamed `FIX-REQUEST.resolved.md` when the episode builds. A tick with nothing due logs one line (identical idle lines replace each other). An episode that completes after 19:00 is posted AT ONCE by the autopilot, however late and across midnight, never before its 19:00 slot (R-507, `loop_gate.late_post_due`, `post_extra.py tick --late-ep`, one post run at a time through `work/daily/post.lock`); a failed post is `PUBLISH-FAILED` in red and is retried at the next tick (8 a day). The harvest is due 14:00 the day after the day the post was for, never less than 12 h after it.

Every run appends one line to `work/daily/autopilot.log` and writes `work/daily/autopilot.json` (last run, attempts, to-do); the board's Today tab shows the log tail and "needs you" items (a stuck episode, a failed harvest, a missing token) and, at the top of every tab, the live **Build** panel (`tools/build_status.py`, R-505): the stages of the current episode (ok / running / failed / waiting), the heals applied, each named (`refit.json` line refit, `read-heal.json` reading time, `depth-heal.json`, `cap-heal.json` plate cut, `fixer.json` general fixer, with what it did last and a play mark while it runs), what the autopilot is doing right now, machine time and tokens against their caps, the last autopilot line, the next tick, and a red banner for any stop, backed-off episode, `FIX-REQUEST.md`, `PUBLISH-FAILED`, failed harvest or an autopilot that stopped ticking. It is rewritten by every tick and at every stage boundary of `daily.py run`.

## 💬 Engagement is not a daily stage

Comments, DMs, likes and replies are handled by their own tick, `uv run tools/engage.py run [--go]`, every 10 min between 08:30 and 23:30 Amman, for 72 h after each platform's post (R-460 to R-480); it is not part of `daily.py run` and does not block a build. The votes stage above reads Instagram comments for the vote only. The rules, caps, Haiku decider (`story-engager`), automatic DMs, the likes that need a session, and the board's Engage tab are in **[AUDIENCE.md](AUDIENCE.md)** "Engagement flow". Entry points: `engage.py status` (windows, counts, caps, halts), `engage.py run` (dry unless `--go`), `dm_auto.py apply --go` (Lead, once). Our own account is never replied to; the owner's `owner_account` is replied to like any viewer (R-473).

## 🧱 Calm shot templates

`uv run tools/calm.py list` · `uv run tools/calm.py make <template> <shot-dir> key=value … [--run]`

Data in, a normal `tools/shot.py` shot folder out. It carries `"format": "calm"`, so `shot.py gate` runs the calm profile.

| Template | What it shows | Needs |
|---|---|---|
| `push_in` | slow dolly-in on one subject | `character` `pose` `expression` `gaze` |
| `parallax_pan` | slow pan, the layers slide at different speeds | `character` `expression` `pan` `span` |
| `hold_breathe` | a deliberate hold: breath, a blink, a 2.5 % drift | `character` `expression` |
| `insert` | a prop or a hand, close | `character` `target=hand_L\|hand_R\|prop:<name>` |
| `insert_depth` | a prop close-up with real depth: far set, counter, the prop with a flat 2D shadow, a dark occluder, a slow dolly | `character` `target=prop:<tag\|key\|cards>` (kit `hero` entry) |
| `reaction_closeup` | one expression turns into another | `character` `expression` `expression_to` `change_at` |
| `two_shot` | two people, hands apart (no touch) | `characters=a,b` `expressions` `gap` |
| `title_card` `day_card` `recap_card` `choice_card` `follow_card` | the wrapper, Thmanyah text | see `tools/calm_cards.py` |
| `choice_split` | C4: question and two choices in the bottom half, the top half cuts between two close-ups | `question` `choice1` `choice2` |
| `object_card` | C3: a brass plate for the written object; the caption is engraved on it | `heading` |
| `intro_freeze` | C10: a character's FIRST appearance: the `freeze` cut (riser and hit), the frame frozen, a grey rim and halo around them, the rest dimmed, hand-drawn graffiti (name + one bible line), the music dips | plan key `intros` (below); built by `tools/calm_intro.py` from the scene before it |

🧩 **Kits.** A character enters the calm format through a kit: `tools/templates/calm/kits/<char>.json` (+ `.js` drawing hook). It is taken from a gated smoke shot (`calm_kit.py extract`). Today: **partner, guide**. `calm_kit.py status` lists the rest.

🎚️ **Calm life.** The set moves less in a calm shot (lamp sway ×0.35, flicker ×0.3, no dust, set clock ×0.3). Parameters `lamp`, `world`, `dust`.

## ✍️ The writer's two files

`bible/series/<series>/episodes/<ep>/script.json` (voice.py lines: characters in their own cast voices plus a short narrator, format v2) and `calm-plan.json`:

**Slot limits (R-502, the owner 2026-10-30): every line must fit its slot when SPOKEN**, because a line is voiced once and the plan stage refuses a longer take. The recap hook (the first line, behind the recap card): at most 2.45 s aloud, about 12 Arabic letters of `tts_text`, 3 words. A scene line: 9.45 s (about 60 letters). An intro's narrator line: 8.45 s (about 54). The four choice lines together: 13.7 s (about 79 letters). The brief the script stage gives the writer carries these numbers (`line_fit.brief_block`); a line the estimate puts over its slot is sent back before any voice is made (`SCRIPT-FIT`); `uv run tools/line_fit.py limits` prints them.

```json
{
  "series": "series", "episode": "E02", "day": 2,
  "place": "the series", "clock0": "9:04 م", "series_name": "the series",
  "recap": {"line": "اخترتم:", "word": "الرف"},
  "hook": {"pattern": 1, "line": "H01"},
  "scenes": [
    {"id": "s01", "line": "L01", "block": "consequence", "template": "push_in",
     "params": {"character": "partner", "pose": "offer", "expression": "giving-relief"}, "clock": "9:06 م",
     "event": "Partner closes the floor drain with the iron cover", "night": "n1", "role": "link"}
  ],
  "needs_art": [{"what": "iron drain cover, closed", "for_scene": "s01"}],
  "choice": {"question": "...", "choice1": "...", "choice2": "...", "line": "L14"},
  "post_caption": "..."
}
```

- 🎬 `block`: `consequence` scenes come first (before the day card), then `story`, then `cliff` last.
- 🗣️ **Format v2 (the owner 2026-10-28, from E03)**: 10 to 15 character lines (`speaker` a character id, own cast voice, at least 2 speakers answering each other: `DIALOGUE-LINES`); the narrator (`speaker: "narrator"`) only for the recap, short night links (scene `"role": "link"`, at most 14 words) and the vote question, at most 25 % of the voice time (`NARRATOR-SHARE`). `text` without tashkeel (it is the caption), `tts_text` with tashkeel.
- 🎬 **Scene fields added by format v2**: `event` (one sentence of the visible action; 2 to 5 scenes per episode, a template that shows it, not `reaction_closeup` or `hold_breathe`), `night` (optional segment id; default: `consequence` = n1, `story`/`cliff` = n2; every night needs an event), `role` (`link` for a narrator night link; the example above shows all three on one scene only to show the keys). Plan key `needs_art`: `[{what, for_scene}]` for art that must be created (`EVENTS`). Intros only for characters never seen in an earlier episode (`PLAN-INTRO`).
- 📏 A line is at most 8 s read aloud. The scene lasts line + 0.55 s, snapped to 24 fps (min 2.5 s, max 10 s).
- ✌️ **Two** choices every episode, each a **short phrase a viewer can type** (at most 4 words, no digits: `CALM-CHOICE`), with optional `choice.variants` {"1": [...], "2": [...]} (other ways to say it, for `vote.py`). The closing line (`choice.lines.hook`) asks viewers to write the choice in their own words, what they think and what they want to see next; never "comment 1 or 2" (owner, 2026-10-25, C13). `vote.py` counts from the wording and carries the free ideas into the next writer brief (`next-brief.md`, "Ideas from the audience").
- 🧊 **`intros`** (C10, the owner 2026-10-25): every character's first appearance as a person (a prop close-up or a bare hand does not count) is followed by an `intro_freeze`: `"intros": [{"id": "intro-hero", "character": "hero", "after": "s02", "line": "I01", "name": "هدى", "tag": "تضع بطاقة على كل شيء"}]`. `name` at most 2 words, `tag` at most 6 words (one line from the bible: what they are extreme about), no tashkeel; `line` is an optional narrator line (a new take). The plan's `transitions` carry `{from: <scene>, to: <intro id>, cut: "freeze"}` and a cut back into the story. `PLAN-INTRO` refuses a plan with a missing or doubled intro; `CALM-INTRO`, `CALM-INTRO-SFX` and the shot's `INTRO-*` checks gate the build.
- 🎣 **From E02 the plan also has** `hook` {pattern 1..10, line} (the narrator line spoken over the recap card: the first spoken line, at most 8 words in its first plate, 2.4 s aloud at most: `PLAN-HOOK`), a first scene line that names a cast member (`PLAN-SOFAR`), `choice.variants` {"1": [8+], "2": [8+]} (`PLAN-VARIANTS`), an open-question closing line and prompt (`PLAN-PROMPT`), and optionally `follow_line` (default «الحلقة القادمة تتبع ما تكتبونه») and `cover` {object: image path} for the cover silhouette. The recap card is built from `calm_compose.recap_card_params(plan)` (adds the `tag` «الحلقة N · the series»), the follow card from `calm_compose.follow_card_line(plan)`. Details: `kb/quality/gate-spec.md` H.2b.
- 🔁 **Recaps start at E02** (owner, 2026-10-25; `RECAP_FROM_EPISODE` in `tools/calm_compose.py`). An E01 plan has no `recap` key (`PLAN-RECAP` refuses one) and opens on its story at 0 s, with the first story event inside the first second; from E02 the `recap` key is required. The shotlist declares `episode_no` and `recap_from`, and `CALM-WRAPPER` / `CALM-RECAP-FIRST` follow them.
- 🗣️ The narrator, where it speaks, addresses the audience in the second person plural «أنتم» (owner, 2026-10-25).
- 🚫 No tashkeel in anything visible. The planner refuses it.

## ⏱️ Limits

- 🕓 **4 h of machine time** (`CAP_S`). Voice, shots, compose, gates and publish are timed. The child process gets the remaining seconds as its timeout. At the cap: kill, `STOPPED.md`, exit 4.
- 🪙 **Tokens**: `SW_LLM_DAILY_TOKENS` (default 250 000, estimated). Counted from each call's JSON usage; the next call is refused when spent (exit 3).
- 🆓 **Free only**: the child environment is scrubbed of paid keys (`PAID_ENV`); a config naming a paid engine, model or poster is refused (exit 5). Voice = Chatterbox (cast: [VOICE.md](VOICE.md) "Casting order"; the daily run never casts or changes a reference). LLM = Sonnet through the subscription. Posting = official Instagram Graph API.
- 🚫 No git. No Gemini (banned for good). No second take. The healer never edits `script.json` (restored, run stops).
- 🧹 Every child is waited for. Nothing is left running.

## 🤖 The headless Claude call

Same pattern as the LinkedIn project's `claude_run.py` (not run, only read): `claude -p … --model sonnet --effort medium|high --allowedTools <explicit, no Agent> --permission-mode dontAsk --max-turns 40 --max-budget-usd 3 --output-format json --no-session-persistence`, env `NJ_ROLE=job`, `NJ_WRITE_ALLOW`. Writer: `Read,Glob,Grep,Write`. Critic: `Read,Glob,Grep`. Healer: `Read,Glob,Grep,Write,Edit`.

## 🗓️ Windows Task Scheduler plan (documented, **not registered**)

`uv run tools/daily.py plan-task` prints it. Summary:

| Task | When | Command |
|---|---|---|
| `StoryWrap-Daily-Build` | daily 06:00 | `daily.py run` |
| `StoryWrap-Daily-Post` | daily 18:00 | `daily.py post --latest --go` |
| `StoryWrap-IG-Refresh` | monthly | `ig.py refresh` |

The harvest is due 14:00 the day after the post (the owner 2026-10-27); the `votes` stage of the next run reads it if it is not done. Exit codes the history shows: 0 ready or posted, 1 stage failed, 3 token budget, 4 render cap, 5 paid service.

## ✅ Before the first unattended day

1. the owner's Instagram token in `~/.config/story-wrap/instagram.env` (`ig.py status`).
2. One rehearsal on a throwaway episode (`work/rehearsal/<ep>`), approved by the owner (the rehearsal rule in `CLAUDE.md`).
3. `VOICE.md` says the owner starts `voice --go`. The daily run starts it itself (`autovoice`), because the target is unattended. **the owner decides.**
4. A characters kit for every character the writer may stage (Hero has none yet).
5. Register the three tasks.

## 📐 Measured vs estimated

✅ **Measured on this PC (2026-10-24, RTX 2060, 2 threads)**

| What | Number |
|---|---|
| One actor shot, 3.5 to 4 s | about 59 s machine (build 3, trace 7, record 11, gate 36, review 2) |
| One card (recap, day, choice, follow) | 4 to 5 s |
| Rehearsal episode R01: 6 scenes + 4 cards, 32 s | `shots` 397 s first pass (two shots failed and were fixed, 4 reruns, 625 s in all), `compose` 17 s, `gates` 26 s |
| Rehearsal loudness | -14.0 LUFS, LRA 4.2 LU, true peak -1.5 dBTP |
| Unit suite | 582 passed, 4 skipped, 185 s (2026-10-24); 812 passed at E01 calm v5 (2026-10-25) |
| E01 calm v5 (the approved reference) | 127 s long, 26 episode checks pass, critic 9/10; one clean compose pass about 11 minutes (`work/episodes/E01C`) |
| Calm gate, passing shots | motion coverage 0.19 to 0.35, clusters 1.6 to 7.9, depth bands 4.1 to 5.6, parallax 0.14 to 0.49 |

Templates verified through every gate in the calm profile: `push_in` (partner), `hold_breathe` (guide), `reaction_closeup` (guide, size medium), `two_shot` (partner + guide), `parallax_pan` (partner, span 0.01), `insert` (partner bread, at_y 0.62 push 2.5; guide hand_R, at_y 0.55 push 2). All five cards pass `CARD-*`.

⚠️ **Fragile:** `insert` on Partner passes by 0.001 on motion coverage. Close crops fail the art checks (luma, line, depth), so `insert` uses a wide frame with the hand low. `parallax_pan` wider than 0.015 of the frame fails `CALM-MOTION` (0.47 at 0.03, 0.70 at 0.08).

🔮 **Estimated, not measured**
- A real 60 s episode: about 15 to 25 machine minutes (R01 scaled by scene count), plus Chatterbox voice time (not measured here; 8 to 15 min in the plan).
- Tokens: 75 to 180 K per episode (plan), counted for real from the first run.
- Narrator coverage: the rehearsal used synthetic tone takes, not Chatterbox. It fails `CALM-NARRATOR` (0.56 of runtime, need 0.85) because the four cards are un-narrated and the takes were short. Real lines must cover the recap, day and follow cards or run longer.
- Joins: `fadeblack` 0.25 s was chosen when the gate counted detector hits. Since 2026-10-25 the gate counts the DECLARED shots and ignores hits inside declared transition windows (gate-spec H.1a), so any declared cut type (flash, whoosh, ink, page) is one shot change, not several.
- Length (the owner 2026-10-25): whatever suits the story. `CALM-LENGTH` has a 25 s floor and a soft warning over 92 s, no ceiling; `PLAN-SCENES` has a floor of 4 scenes and no ceiling.
- Foreign words (the owner 2026-10-25): the writer uses a character's own-language word only if it is in `bible/series/<series>/glossary.json`; captions then show «(meaning)» under it automatically, and `PLAN-GLOSS` / `CAP-FOREIGN-GLOSS` fail a visible string or plate without it.

⚠️ **Budget (E01 calm v5):** the 4 h render cap and the token budget were both already spent by earlier runs that day; the agent bypassed the cap for its own calls and filled in the critic report itself when the tokens ran out. Do not repeat that: a spent budget stops the run (exit 3 or 4).

🧪 **Not run:** the writer, critic and healer agents (no model was called), `voice.py --go`, `ig.py` with a token, Task Scheduler registration.
