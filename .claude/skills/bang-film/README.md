<div align="center">

<img src="icon.svg" width="120" alt="Bang Film icon">

# Bang Film

**An agent skill that designs AI live-action video — vertical microdrama series, short films, single scenes and trailers — and writes the prompts you paste into any AI image and video model.**

[![Version](https://img.shields.io/badge/version-1.2.0-2f6fd6?style=flat-square)](CHANGELOG.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-3fa34d?style=flat-square)](LICENSE)
[![Agent Skills](https://img.shields.io/badge/format-Agent%20Skills-1c2a4a?style=flat-square)](#install)
[![Works with](https://img.shields.io/badge/works%20with-Claude%20Code%20%C2%B7%20Codex%20%C2%B7%20Gemini%20CLI%20%C2%B7%20Cursor-7a5af5?style=flat-square)](#install)

It never generates media. Output is a folder of text files: concept, cast and set bible, shot list, asset prompts, video prompts.

</div>

---

## Why

Ask an agent for "an AI drama" and the prompts it writes fall apart on screen: the lead's face changes between clips, extras nod in unison like a choir, a shipping label turns into gibberish, the clip plays like a trailer montage, and a scooter parked in the lane is inside the gate after the next cut.
Bang Film encodes what a director and a script supervisor would insist on — character blocks copied letter for letter, one continuous moment covered from many camera positions, no beat told through on-screen text, objects that stay where they were left — as **gates the agent must pass** and **a checker it must run** before handing anything over.

## What you get

- **Three presets, one engine**: microdrama (hard hook up front, cliffhanger every episode, cast reused across episodes), short movie (three acts, a resolution), scene / trailer (one moment, no resolution).
- **Seven gates, three approvals**: brief → concept → cast, set & props → script + shot list → asset prompts → video prompts → verification. Concept, bible and shot list each wait for your OK — changing a paragraph is cheaper than rewriting forty prompts.
- **Nothing assumed**: aspect ratio, duration and episode count are always asked. Shot count is never asked — the script and the video model decide.
- **A locked bible**: every character, location and recurring prop gets a long form (for its sheet) and a short form (for the video prompt), copied identically everywhere, plus an image token like `[gambar_adit]` that matches its file name.
- **Three-panel character sheets**: close-up on the left, full body front and back beside it, the character's name printed on the image so sheets never get swapped.
- **Eleven-block video prompts**: VIDEO STYLE & FORMAT · LANGUAGE · OPTICS · CAMERA · LIGHTING · CRITICAL · CHARACTERS · LOCATION · AUDIO · MOVEMENT NOTE · SHOT BREAKDOWN, plus an optional CONTINUITY block. Dialogue is written inside the prompt in the language you chose. No ratio, no headers, no file names, no subtitles inside the block.
- **One prompt = one generation = 4–30 seconds**: longer episodes are split along the story (60 s → 30 + 30 or 20 + 20 + 20), never mid-line.
- **Risky shots flagged before you spend credits**: shots through a gap or glass, the same place seen from both sides of a door, reverse angles the plate doesn't show, absences that must read on screen, props that must survive a cut — each with a safer alternative. You decide whether to keep them.
- **A repair loop for when a clip comes back wrong**: dissect it (cuts, contact sheet, transcript), change one or two sentences, save a new version, roll back if it got worse.
- **A checker**: `assets/tools/check_prompts.py` verifies locked blocks, block order, timecodes, 4–30 s durations, tokens against attached files, location tags and banned words.

## Quick start

*"Bikin microdrama 3 episode tentang kurir yang tiap hari antar paket ke alamat yang sama, tapi pintunya nggak pernah dibuka."*

1. Two question cards: topic, format, ratio, dialogue language — then duration, episode count, look.
2. `konsep.md` — logline, three-line premise, an arc per episode, three hooks built on different formulas. You pick one.
3. `cast.md` and `set.md` — locked blocks for every character, location and prop.
4. `epNN/naskah.md` — the script readable as a story, the shot list, the split into generations, and the risky shots.
5. `epNN/prompt-aset.md` — character sheets and plates. Generate them in any image model and save them under the names given.
6. `epNN/prompt-video.md` — one block per generation. Attach the files listed above the block, set ratio and duration in your video tool, paste, generate.

A complete three-episode project produced by the skill itself lives in `assets/contoh/alamat-yang-sama/`.

## Language

The skill's instructions and its conversation with you are in **Indonesian**. The prompts it writes are in **English**, with dialogue in whatever language you choose — the LANGUAGE block tells the video model which language and register to use and to speak the lines exactly as written.

## Install

Bang Film follows the open **Agent Skills** layout: a folder with `SKILL.md` (frontmatter + instructions), `references/`, `assets/`. It also ships as a Claude Code **plugin**, so it can be installed and updated with two commands.

### As a plugin (Claude Code)

```
/plugin marketplace add bangtutorial/bang-film
```
```
/plugin install bang-film@bang-film
```

The skill then shows up in your skill list and stays updatable with `/plugin marketplace update bang-film`.

### Manual (any agent)

```bash
git clone https://github.com/bangtutorial/bang-film
```

| Agent | Where it goes |
|---|---|
| Claude Code | `~/.claude/skills/bang-film` (Windows: `C:\Users\<you>\.claude\skills\bang-film`) |
| Codex CLI | your Codex skills folder, or add to `AGENTS.md`: *"For AI video concepts and prompts, read and follow `bang-film/SKILL.md`."* |
| Gemini CLI · Cursor · others | copy into the project and reference `SKILL.md` from `GEMINI.md`, `.cursor/rules`, or the system prompt |
| Plain chat (no agent) | paste `SKILL.md` + `references/prompt-video.md` as instructions |

The skill triggers on requests like "bikin microdrama…", "short movie AI…", "prompt video AI…", "sheet karakter…", or continuing an existing series.

## Requirements

| To… | You need |
|---|---|
| Get concepts and prompts | nothing — it's all text |
| Generate assets and clips | any AI image model, and any AI video model that accepts reference images |
| Run the checker | Python 3, no packages |
| Dissect a generated clip | ffmpeg for cuts and contact sheets; Whisper optional, for the dialogue transcript |

## How the rules work

- **Approval before volume**: concept, bible and shot list are each approved before anything downstream is written.
- **Copied, never paraphrased**: one changed word in a character block changes the face. The checker compares every copy.
- **Rules first, scene last**: the eleven blocks state style, language, optics, camera, light and consistency before the shot breakdown, so the model reads them as constraints for the whole clip. Ratio, resolution and model names stay in the tool's settings.
- **Every cut moves**: "never two consecutive shots from the same position" is written into every prompt.
- **Bodies, not just faces**: MOVEMENT NOTE is always present; with more than two people it breaks extras out of unison.
- **No beat lives in text**: labels, phone screens and signs can't be trusted to render, so the story is carried by image and sound.
- **Space that holds across cuts**: a generation with more than one location plate gets a reference map, a location tag on every shot, and a CONTINUITY block locking where people and props are.
- **Small, versioned fixes**: when a clip comes back wrong, one or two sentences change, the old version is kept, and a fix that makes things worse is rolled back. Longer prompts don't make models more obedient.

Full detail lives in `SKILL.md` and `references/`.

## Layout

```
SKILL.md                     gates & rules (read by the agent)
.claude-plugin/              plugin + marketplace manifests (Claude Code install)
references/
  brief.md                   gate 1: two question cards, no guessing
  konsep.md                  gates 2 & 4: formats, hooks, cliffhangers, shot list, risky shots, splitting
  copywriting.md             anti-generic writing, cliché detector, rubric
  cast.md                    gate 3: locked character, set and prop blocks, image tokens
  prompt-aset.md             gate 5: three-panel sheets, set and prop plates
  prompt-video.md            gate 6: the eleven blocks, CONTINUITY, reference map, location tags
  verifikasi.md              gate 7: checker, manual checklist, symptom → cause, repair loop
assets/
  template/                  empty skeletons copied into a new project
  contoh/                    "Unit 7" excerpts + RAFA sheet; alamat-yang-sama/ is a full project
  tools/check_prompts.py     gate 7 checker (Python 3, no dependencies)
```

## Contributing

Issues and pull requests are welcome. Most rules here came from a real generation that went wrong — if you add one, say which failure it prevents and on what kind of shot. Bump `version` in `SKILL.md` and `.claude-plugin/`, and add a line to `CHANGELOG.md`.

## License

[MIT](LICENSE) © 2026 [Bang Tutorial](https://youtube.com/bangtutorial)
