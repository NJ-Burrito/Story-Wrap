---
name: story-wrap
description: "Run the Story-Wrap tool: make a short animated story reel episode end to end (plan, voice, captions, shots, compose, mix, quality gates, critic and heal loop), then optionally post it through the official Instagram, Facebook Page and YouTube APIs with the user's own apps, and run the audience loop. Triggers: make a Story-Wrap episode, build the next episode, post the episode, daily.py, compose.py, shot.py, ig.py, fb.py, yt.py, heal.py, quality gate."
---

# story-wrap

Generic operating guide for this repository. It contains no project data: episodes, series bibles,
characters, fonts and credentials are the user's own and are supplied through config.

## Before anything runs

1. Read `CLAUDE.md` and `pipelines/RUNBOOK.md`. Stage docs: `pipelines/DAILY.md` (the day and the templates),
   `COMPOSE.md`, `VOICE.md`, `HEAL.md`, `STAGE-GATES.md`, `CALM.md`, `AUDIENCE.md`, `LEARN.md`, `CREW.md`.
2. Check configuration: copy `config/story-wrap.example.env` and the credential examples, fill the keys, and
   confirm fonts exist (`SW_FONTS` or `assets/fonts/`). Nothing is shipped for these.
3. Check the cast: renderer characters and worlds go in `tools/render/characters/` and `tools/render/worlds/`
   (see the READMEs there).

## Run

- Whole day: `uv run tools/daily.py --help` lists the subcommands (`autopilot`, `plan`, `status`, task registration notes).
- Single stages: `tools/compose.py`, `tools/shot.py`, `tools/voice.py`, `tools/calm_compose.py`, `tools/heal.py`.
- Gates: `tools/quality_gate.py`, `tools/loop_gate.py`, `tools/stagegate.py`. A refused gate is fixed at its
  root cause, never bypassed.
- Posting is dry-run by default: `tools/ig.py`, `tools/fb.py`, `tools/yt.py`, `tools/stories.py` take `--go` to act.
  Post only to accounts the user owns, with their own tokens.
- Board: `python board/serve.py` serves a local monitor on 127.0.0.1.

## Rules

- Sound: the `earshot`, `real-sound` and `bg-duck` skills check and mix audio; install the vendored package
  from `tools/vendor/earshot` into a venv there.
- Costs: free tools and the user's own subscriptions by default; respect `SW_LLM_DAILY_TOKENS`.
- Never print or store credentials; never post for an account that is not the user's own.
