# Story-Wrap

A pipeline and a set of scripts, skills and docs for making short animated story reels
(Arabic-first, any language works): write, voice, rig and animate 2D characters, compose,
mix sound, run quality gates, and post through the official Instagram, Facebook Page and
YouTube APIs with your own apps. This repository is the **tool only**. Your episodes, series,
art, renders, audience data and accounts live in your own projects, never here.

> ملخص بالعربية: Story-Wrap أداة (سكربتات ومهارات ووثائق) لإنتاج ريلز قصصية متحركة: كتابة، تعليق صوتي،
> رسوم ثنائية الأبعاد، مونتاج، مزج صوت، بوابات جودة، ونشر عبر واجهات إنستغرام وفيسبوك ويوتيوب الرسمية
> بحساباتك أنت. المستودع يحتوي الأداة فقط؛ حلقاتك وخطوطك وصوتياتك وبياناتك تبقى عندك.

## Layout

| Path | What it is |
|---|---|
| `tools/` | Python and Node scripts: compose, shot engine, voice, captions, gates, heal loop, posting (`ig.py`, `fb.py`, `yt.py`), engagement, board feed; `tools/tests/` |
| `tools/vendor/earshot/` | Patched copy of the MIT `earshot` audio-realism package (see its `PATCHED.md`) |
| `pipelines/` | How each stage runs (`RUNBOOK.md` first) |
| `kb/` | Rulebook, guides, quality specs, templates |
| `bible/craft`, `bible/sound` | Craft and sound reference docs |
| `board/` | Local monitor page and server (`serve.py`, `index.html`); data is git-ignored |
| `config/` | Example env and JSON files for every value you must supply |
| `.claude/skills/`, `.claude/agents/` | Claude Code skills (`story-wrap` plus MIT/Apache/CC0/CC-BY third-party skills) and role agents |

## Quick start

```
git clone <this repo> && cd Story-Wrap
# Python scripts run with uv (never pip): uv run --with <deps> tools/<script>.py
cp config/story-wrap.example.env ~/.config/story-wrap/story-wrap.env   # then edit
cp config/schedule.example.json board/schedule.json
cp config/board-config.example.json board/config.json
uv run tools/daily.py --help
```

Python 3.10+, Node 18+, ffmpeg, and a Chromium for rendering are expected. Set `PYTHONUTF8=1` on Windows.

## What you must supply (config keys)

Environment (see `config/story-wrap.example.env`): `STORYWRAP_ROOT`, `SW_FONTS`, `SW_OWN_ACCOUNTS`,
`SW_PAGE_NAME`, `SW_SERIES_NAME`, `SW_INSTAGRAM_URL`, `SW_YOUTUBE_URL`, `SW_YT_CHANNEL_ID`,
`SW_YT_PLAYLIST_TITLE`, `SW_MEDIA_REPO`, `SW_IG_ENV`, `SW_GH_ENV`, `SW_YT_TOKEN`, `SW_LLM_DAILY_TOKENS`.
Credential files (`config/instagram.example.env`, `config/github.example.env`): `IG_USER_ID`, `IG_USERNAME`,
`IG_ACCESS_TOKEN`, `IG_TOKEN_ISSUED`, `FB_PAGE_ID`, `FB_PAGE_TOKEN`, `GH_TOKEN`, plus a YouTube OAuth token JSON
from your own Google project. Schedule and board settings: `config/schedule.example.json`, `config/board-config.example.json`.
Credentials live only in `~/.config/story-wrap/`, never in the repo.

## Not included (bring your own)

- **Fonts.** No font files are shipped. Put your own licensed Arabic fonts in `assets/fonts/` (or point `SW_FONTS` at them).
- **Characters and worlds.** `tools/render/characters/` and `tools/render/worlds/` hold only READMEs; add your own cast and sets.
- **Voices, audio, reference images and videos.** None are included.
- **Third-party skills with a licence conflict.** `svg-character-animation` and `character-rigging` (from
  `calesthio/OpenMontage`, AGPL-3.0 upstream) are not redistributed here. Install them from upstream if you want them.

## Third-party

See `THIRD-PARTY.md`. Each bundled skill keeps its LICENSE and `SOURCE.md`.

## Licence

MIT, copyright NJ-Burrito. See `LICENSE`.
