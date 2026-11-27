<p align="center">
  <img src="media/hero.gif" alt="Story-Wrap: an idea moves through script, voice, animation, sound, compose and publish and comes out as a short Arabic reel. / فكرة تمر بالنص والصوت والحركة والمؤثرات والمونتاج والنشر وتصير ريلًا عربيًا قصيرًا." width="540">
</p>

# Story-Wrap

**Story-Wrap is a free, open-source (MIT) Claude Code toolkit that turns a story idea into a short animated Arabic reel: script, voice, sound, compose and publish.**
It is for creators, educators, Arabic storytellers and developers who want to make their own reels. You bring Claude Code, a GPU, your own fonts and characters.

![Licence: MIT](https://img.shields.io/badge/licence-MIT-7A1F3D)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-4A4C50)
![Node 18+](https://img.shields.io/badge/node-18%2B-4A4C50)

> ملخص بالعربية: Story-Wrap أداة مفتوحة المصدر تعمل مع Claude Code، تحوّل فكرتك إلى ريل قصصي متحرك: نص، صوت، رسوم، مؤثرات، ثم نشر. مجانية برخصة MIT، وعليك أن تحضر Claude Code وبطاقة رسومية وخطوطك وشخصياتك. المستودع يحتوي الأداة فقط؛ حلقاتك وخطوطك وصوتياتك وبياناتك تبقى عندك. تحتاج سطر الأوامر وClaude Code، فهذه أداة وليست محررًا بالنقر.

Command line and Claude Code are required. This is not a point-and-click editor.
Posting goes through the official Instagram, Facebook Page and YouTube APIs, with your own apps and tokens.

Site: <https://nj-burrito.github.io/story-wrap/> (Arabic: <https://nj-burrito.github.io/story-wrap/ar/>)

## Quick start

These five lines run on a clean checkout and print the command list. They do not make a reel.

```bash
git clone https://github.com/NJ-Burrito/Story-Wrap
cd Story-Wrap
mkdir -p ~/.config/story-wrap
cp config/story-wrap.example.env ~/.config/story-wrap/story-wrap.env
uv run tools/daily.py --help
```

Set `PYTHONUTF8=1` on Windows. Python scripts run with uv, never pip: `uv run --with <deps> tools/<script>.py`.
Before your first reel you supply fonts, characters and worlds, a voice reference clip and account tokens; each has an example file in `config/`. **No sample reel ships yet.**

## The pipeline

Six stages. Each leaves a file the next one reads. Start with [`pipelines/RUNBOOK.md`](pipelines/RUNBOOK.md).

| # | Stage | What happens | Leaves | Doc |
|---|---|---|---|---|
| 1 | Script | A script and a plan, checked by machine before anything is drawn | `script.json` | [`pipelines/WRITING.md`](pipelines/WRITING.md) |
| 2 | Voice | A local voice engine on your GPU, one take per line | `work/voice/<ep>/<line>.wav` | [`pipelines/VOICE.md`](pipelines/VOICE.md) |
| 3 | Animate | 2D characters and sets; each shot runs nine checked stages (`tools/shot.py`) | `shot.json` | [`pipelines/RUNBOOK.md`](pipelines/RUNBOOK.md) |
| 4 | Sound | Sound design, mix and audio checks | `sfx.json` | [`bible/sound/SOUND.md`](bible/sound/SOUND.md) |
| 5 | Compose | Captions follow the voice; gates, a critic and a heal loop run until it passes | `captions.json`, `episode.mp4` | [`pipelines/COMPOSE.md`](pipelines/COMPOSE.md), [`pipelines/HEAL.md`](pipelines/HEAL.md) |
| 6 | Publish | Dry run first; `--go` posts to your own Instagram, Facebook Page and YouTube | `post.json` | [`pipelines/AUDIENCE.md`](pipelines/AUDIENCE.md) |

Arabic is the first language: fully voweled voice text, caption shaping and right-to-left layout. Other languages are possible but untested.

## Requirements

| You need | Detail |
|---|---|
| Claude Code | Your own plan. The toolkit runs inside it. |
| Python and uv | Python 3.11 or newer for most scripts (a few also run on 3.10), run through uv. |
| Node and a browser | Node 18 or newer, and a Chromium for rendering. |
| ffmpeg | For audio and video. |
| A GPU | NVIDIA, about 4 GB of free video memory, for the local voice engine. It installs into its own environment; the steps are in [`pipelines/VOICE.md`](pipelines/VOICE.md). |
| Your own assets | Fonts, characters, worlds, and one CC0 reference clip per voice with its provenance. |
| Accounts, to post | Meta and Google developer apps and tokens for Instagram, a Facebook Page and YouTube. Skip them and nothing posts. |
| System | Developed and tested on Windows. macOS and Linux are not tested. |

What you must supply, by config key:

Environment (see `config/story-wrap.example.env`): `STORYWRAP_ROOT`, `SW_FONTS`, `SW_OWN_ACCOUNTS`,
`SW_PAGE_NAME`, `SW_SERIES_NAME`, `SW_INSTAGRAM_URL`, `SW_YOUTUBE_URL`, `SW_YT_CHANNEL_ID`,
`SW_YT_PLAYLIST_TITLE`, `SW_MEDIA_REPO`, `SW_IG_ENV`, `SW_GH_ENV`, `SW_YT_TOKEN`, `SW_LLM_DAILY_TOKENS`.
Credential files (`config/instagram.example.env`, `config/github.example.env`): `IG_USER_ID`, `IG_USERNAME`,
`IG_ACCESS_TOKEN`, `IG_TOKEN_ISSUED`, `FB_PAGE_ID`, `FB_PAGE_TOKEN`, `GH_TOKEN`, plus a YouTube OAuth token JSON
from your own Google project. Schedule and board settings: `config/schedule.example.json`, `config/board-config.example.json`
(copy them to `board/schedule.json` and `board/config.json`). Credentials live only in `~/.config/story-wrap/`, never in the repo.

### Not included (bring your own)

- **Fonts.** No font files are shipped. Put your own licensed Arabic fonts in `assets/fonts/` (or point `SW_FONTS` at them).
- **Characters and worlds.** `tools/render/characters/` and `tools/render/worlds/` hold only READMEs; add your own cast and sets.
- **Voices, audio, reference images and videos.** None are included.
- **Third-party skills with a licence conflict.** `svg-character-animation` and `character-rigging` (from
  `calesthio/OpenMontage`, AGPL-3.0 upstream) are not redistributed here. Install them from upstream if you want them.

## Cost and limits

The toolkit is free (MIT) and calls no paid service. Your Claude Code usage is yours. Posting is a dry run until you pass `--go`, and only to accounts you own.

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

## Example project

*The Lost Property Office* (مكتب المفقودات) is an animated Arabic story series made with Story-Wrap: one example of what you can make, not part of the toolkit. Series page: <https://nj-burrito.github.io/story-wrap/lost-property-office/>

## Third-party notices and licence

See [`THIRD-PARTY.md`](THIRD-PARTY.md). Each bundled skill keeps its LICENSE and `SOURCE.md`.
Story-Wrap is MIT, copyright NJ-Burrito. See [`LICENSE`](LICENSE).

## More tools by Nader Alzghoul (NJ-Burrito)

[Portfolio](https://nj-burrito.github.io/) · [QA-Wrap](https://nj-burrito.github.io/QA-Wrap/) (browser bug-report recorder) · [Business-Wrap](https://nj-burrito.github.io/Business-Wrap/) (requirements documents in Arabic and English) · [NJ-Kit](https://nj-burrito.github.io/NJ-Kit/) (working method for Claude Code) · [NJ-Whip](https://nj-burrito.github.io/NJ-Whip/) (on-screen whip for Claude Code) · [Profile-Wrap](https://nj-burrito.github.io/Profile-Wrap/) (LinkedIn posts, your approval first) · [NJ-Flush](https://nj-burrito.github.io/NJ-Flush/) (free Windows RAM cleaner) · [NJ-Sort](https://nj-burrito.github.io/NJ-Sort/) (keeps Windows desktop icons where you put them, even after File Explorer restarts).
