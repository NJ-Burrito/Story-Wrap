# 👥 The production crew

⭐ **Thirteen Sonnet 5.5 agents. The Lead dispatches them. They never talk to each other.**

## 🔒 Two rules

- 🧠 **Every agent is Sonnet 5.5** (owner, 2026-10-23). `model: sonnet` in every file. No Opus, no Haiku, ever.
- 🚦 **Crew members never instruct each other.** The Lead reads each receipt, then dispatches the next member. A fault found by one member is a finding for the Lead to route, not a message to a peer.
- 🚫 **Google Gemini is banned.** No agent calls it. The voice engine is Chatterbox Multilingual (local, one take per line, [VOICE.md](VOICE.md)); no other engine, no ASR, no judge model.

## 🗂️ The crew

Calm-format owners: `sw-sound-voice` (takes, mouth tracks), `sw-sound-engineer` (mix, cues), `sw-editor-compositor` (captions, assemble, preview), `sw-pipeline-engineer` (templates, gates). The calm steps are in [CALM.md](CALM.md).

Order of work: **research → writing → sketching → animating → composing**. Definitions live in `.claude/agents/sw-*.md`.

| Agent | Stage | Owns | Lead dispatches when |
|---|---|---|---|
| `sw-showrunner-writer` | writing | `bible/series/<series>/series.md`, `pitch.md`, `characters/*/bible.md` and `voice.md`, `episodes/*/script.json` and outlines, `bible/ideas/` (rejected ideas move here, never deleted) | A new series, character or episode is needed, or a script changes |
| `sw-culture-reader` | writing (culture check, before sketching) | its culture brief only: `bible/series/<series>/culture/<character>.md` (verdict section); it never edits `bible.md` | A character is written and needs its culture check |
| `sw-director` | animating (init, catalogue, camera, spec stages of `tools/shot.py`) | `work/shots/<id>/shot.json`, camera plan and spec files, `bible/craft/` shot notes, beat sheets under `bible/series/<series>/episodes/<ep>/` | A script is approved and a shot needs its plan |
| `sw-character-artist` | sketching (art book) and the character side of animating | `tools/render/characters/**` (modules), character catalogue entries, `tools/sheets.py` outputs for characters, `work/artbook/` character pages | A written character needs drawing, or a catalogue version changes |
| `sw-world-artist` | sketching (art book) and the world side of animating | `tools/render/worlds/**` (modules), world catalogue entries, `tools/sheets.py` outputs for worlds, `work/artbook/` world pages | A written world or set needs drawing |
| `sw-animator` | animating (build, trace, record, gate, review stages) | `work/shots/<id>/` (source, trace, video, STATE.json) for the shot it is given; it does not edit `tools/` code | A shot spec is approved and needs building |
| `sw-critic` | heal loop, between gate and heal (`pipelines/HEAL.md`) | nothing. It returns its scores as text (or as the `heal/critic.json` content for the Lead to save) | After every build whose gates have run |
| `sw-healer` | heal loop, after critic (`pipelines/HEAL.md`) | the files named by the fix place of each fault class (`kb/quality/heal-playbooks.md`), `heal/` round records, `kb/lessons/ledger.jsonl` via `heal.py learn`; never `pipelines/heal.json` or `HEAL.md` | A gate failed or the critic scored below 9 |
| `sw-sound-voice` | voice (`pipelines/VOICE.md`) and the sound licences of composing | `bible/series/<series>/voices/**` (casting, banned list is `bible/voices-banned.json`, kept), `work/voice/<ep>/` manifests, takes and visemes, `assets/audio/` licence records. Chatterbox only, one take per line, `retext` for new words, never a re-voice; a finding goes to the owner and the Lead, never a retake | An episode script is final and needs its manifest, takes and mouth tracks, or a sound needs licensing |
| `sw-sound-engineer` | composing, the audio stages (`pipelines/CALM.md` steps 4 and 6) | `tools/calm_mix.py` (phone-first chain, `PRESETS`), `tools/audio_checks.py` (AUDIO-DIALOGUE-CLARITY, AUDIO-MONO, AUDIO-PEAK), `tools/calm_sfx.py` (cut types, synth, foley, choice pops), `tools/tests/test_audio_mix.py`, `research/sound-e01c.md`, `assets/audio/` and `LICENCES.md`, the audio sections of `pipelines/COMPOSE.md`. Judges the mix as a phone plays it; fixes the cause, never a threshold; never re-voices | An episode's audio needs analysis or a remix, a cue is missing or masks a word, or a new sound is needed (C3, C4, C5, C9) |
| `sw-editor-compositor` | composing episodes (`pipelines/COMPOSE.md`) | `work/episodes/<ep>/` compose inputs and outputs, `previews/index.html` (adds a new TAB only, never a new file) | All shots of an episode are gated and healed clean |
| `sw-pipeline-engineer` | all stages (the machinery, not the creative work) | `tools/*.py`, `tools/shotlib/**`, `tools/render/**` code, `tools/record/**`, `tools/templates/**`, `tools/tests/**` | A tool bug, a missing check, or a new engine adapter |
| `sw-continuity-editor` | writing (and a re-check before sketching and composing) | `bible/series/<series>/CONTINUITY.md`, `ensemble-matrix.md`, `bible/README.md`; it reports faults elsewhere and does not rewrite other writers' files | After any bible change, and before each stage hand-off |

## 🧾 What every dispatch carries

1. The goal in one line, and what "done" means.
2. The files it may write (its "owns" list, narrowed to this task).
3. The gates it must pass, with the command.
4. Where to leave the receipt: STATUS / FINDING / EVIDENCE / FILES-SYMBOLS / RISK / NEXT ACTION, at most 25 lines.

## 🔁 The build loop

`sw-animator` builds, gates run, `sw-critic` scores, `sw-healer` fixes and reruns ([HEAL.md](HEAL.md)). the owner sees the work only after it heals clean. A tool bug goes to `sw-pipeline-engineer`; a writing fault goes to `sw-showrunner-writer`; both through the Lead.

## ⚠️ Limits

- Writers have disjoint "owns" lists: one writer per file set.
- Critic and culture reader never fix what they judge.
- No agent loosens a gate. The healer's guard refuses it.
- The Lead commits; agents do not use git.
- Nobody loosens a gate; a budget that is spent (render cap, tokens) stops the run, no agent bypasses it.

Related: [CALM.md](CALM.md), [DAILY.md](DAILY.md), [RUNBOOK.md](RUNBOOK.md), [WRITING.md](WRITING.md), [ARTBOOK.md](ARTBOOK.md), [VOICE.md](VOICE.md), [COMPOSE.md](COMPOSE.md).
