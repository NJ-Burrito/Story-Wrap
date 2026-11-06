# Writing stage runbook

⭐ Writing comes first (CLAUDE.md stage order). It ends with one machine check and one human read: `uv run tools/bible_check.py bible/series/<series>`. Sketching starts only when that exits 0 **and** the owner has read and signed the cast. Shot pipeline for later: `RUNBOOK.md`. Rules: `kb/rulebook.md` R-030 to R-046, R-050 to R-056. Method: `kb/guides/character-writing.md`, `worldbuilding.md`, `genre-blending.md`.

## 📁 Folder layout (one series)

```
bible/series/<series>/
  pitch.md                    kept as is (the pitch and its status line)
  series.md                   story bible: spine, genres, tone, heart, arcs   (kb/templates/story-bible.md)
  ensemble-matrix.md          10-axis contrast matrix                         (kb/templates/ensemble-contrast-matrix.md)
  worlds/<world>.md           one world per file; series-wide rules live in series.md   (kb/templates/world-bible.md)
  culture/<id>.md             culture brief per character; ends with a Decisions section
  characters/<id>/
    bible.md                  the full character bible, machine-checked       (kb/templates/character-bible.md)
    voice.md                  optional: accent notes, long sample lines, dialect word list
    relationships.md          optional: long relationship notes (bible.md keeps the table)
  episodes/<ep>/outline.md    one outline per episode (30-60 s, Arabic)
```

`<id>` is lowercase ASCII (`hero`). The folder name must equal the `id` field. World ids are the file names in `worlds/`.

## 🧭 The order (never reorder)

| # | Step | Who | Output | Must pass |
|---|---|---|---|---|
| 1 | Grunt research: sources, facts, photos of everyday life per culture | Sonnet | `research/` notes with URLs | every fact has a URL or `[J]` |
| 2 | **Culture seat**: one reviewer per culture reads the sources and writes the culture brief | Sonnet | `culture/<id>.md` with DRAW THIS / NEVER THIS and a **Decisions** section | R-041, R-042, R-043; `BIBLE-CULTURE` |
| 3 | **Character bible**: ghost, lie, want, need first; culture shapes the how, never the want | Sonnet | `characters/<id>/bible.md` (+ voice.md) | `BIBLE-FIELDS`, `BIBLE-ACCENT`, `BIBLE-EMOTION`, `BIBLE-HAND`, `BIBLE-CULTURE` |
| 4 | **Ensemble check**: fill the matrix from the bibles, fix pairs that are too close | Sonnet (reads axes 1 and 2 by meaning), then the script | `ensemble-matrix.md` | `ENSEMBLE-CONTRAST` (every pair differs on 8 of 10 axes) |
| 5 | **World bible**: one file per world, linked from the characters | Sonnet | `worlds/<world>.md` | `WORLD-LINK` |
| 6 | **Series bible**: spine, genres (7 or 8), tone, heart, arcs | Sonnet | `series.md` | `BIBLE-LAYOUT`; story-bible checks R-050 to R-056 by the Sonnet seat |
| 7 | **Episode outlines**: hook in the first 3 s, one turn, an ending that points on | Sonnet | `episodes/<ep>/outline.md` | outline template; Sonnet seat reads for R-052 to R-056 |
| 8 | **Check run**, then the **human read** | Sonnet runs, the owner reads | `checks.md` in the series folder, the owner's note in `bible/feedback/` | script exits 0; the owner signs |

Steps 3 and 5 may run in parallel per character and per world; step 4 waits for all characters. A failed check sends work back to the step that owns the field, never forward.

## ✅ Rules for every step

- **Run the check after every file you write**: `uv run tools/bible_check.py bible/series/<series> --character <id>` for one character, no flag for the whole series. Output is `FAIL [CHECK-ID] path: message`; exit 1 on any finding, 2 on a usage error. Run once, fix the root cause, run again; never loosen the script or empty a field to pass.
- **A blank is allowed only as `n/a because ...`.** Placeholders `<...>` count as empty.
- No em dashes, no AI slop, no invented numbers. Real-world facts carry V/S/M/J grades.
- Arabic and English are both first class: dialogue is Arabic with the accent of the origin. Dialogue in a language is read by a native speaker or marked `pending` (R-044). Machine translation is never the final line.
- **Accent rule** (CLAUDE.md): each voice carries the accent of the origin. The bible records it (`accent_source`, `accent_features`); how it is voiced under the one-model, one-take rule stays `open` in `accent_tts_note` until the voice stage settles it.
- Culture is never the punchline or the lesson; build the person first (R-040, R-045).
- Never delete an idea: a dropped character, world or line moves to `bible/ideas/`.

## 🔎 What the script checks

| Id | Passes when |
|---|---|
| `BIBLE-LAYOUT` | `series.md` exists and `characters/<id>/` folders exist |
| `BIBLE-FIELDS` | every field of `kb/templates/character-bible.md` is present and filled (the template is the list); `id` equals the folder; `arc_type` is positive, flat or negative |
| `BIBLE-CULTURE` | `culture_brief` points to an existing file with a Decisions section holding at least one decision (decided or marked open); `culture_status` is closed, pending or open |
| `BIBLE-ACCENT` | `accent_source` shares a word with `origin`; `accent_features` lists at least 2 features |
| `BIBLE-EMOTION` | calm, joy, sadness, fear, anger, surprise, disgust, shame each have `shows` naming at least 4 channels (eyes, face, body, voice, action, environment, colour, sfx, vfx), plus `hides` and `leak` |
| `BIBLE-HAND` | `handedness` starts with left, right or ambidextrous |
| `ENSEMBLE-CONTRAST` | every pair differs on at least 8 of 10 axes (`--min-diff`); no shared extreme trait or tell; a `[tag]` at the end of a cell decides sameness (ghost type, coping habit) |
| `WORLD-LINK` | every id in `world` has `worlds/<id>.md` |

What the script cannot see, the Sonnet seat reads by meaning: two lies that say the same thing in other words, a culture detail that is a stereotype, a trait that is not human, a voice sample that could belong to anyone (blind-swap, R-038).

## 👀 The human read (the owner)

1. Sonnet makes ADHD-friendly cards per character: hook line first, then short emoji-led blocks (ghost, lie, extreme trait and its habit, one voice line, silhouette), one idea per block, choices as big clear cards.
2. Add them as **a new TAB** to `previews/index.html` (never a new file), open `index.html#<tab>` for him, say in one line what to look at.
3. He reads and decides per character: keep, change, park (parked goes to `bible/ideas/`).
4. Close what you opened: browser, background commands.

## 🗣️ Recording feedback

1. Write his words **verbatim** to `bible/feedback/<date>-writing-<series>.md` as the next F-number. Never edit his words, never delete a note.
2. Same session: apply the change in the bible file that owns the field, rerun the check for that character, note the decision in the culture brief's Decisions section if it is cultural.
3. A recurring fault becomes a rule in `kb/rulebook.md` (new number) and, if checkable, a new check in `tools/bible_check.py` with a pass and a fail test.

## 🚦 Done means

`bible_check.py` exits 0, `checks.md` records the run and date, the owner has signed each cast member, and every `culture_status` is `closed` (or he accepted `pending` in writing). Then, and only then, the sketch stage starts, reading `catalogue_*`, `looks_link`, `silhouette_family`, `wardrobe_layers`, and the culture briefs.

## 🩹 Healing (optional stage, on by default)

The critic uses CQ-W1 to CQ-W4 (own voice, no slop, correct Arabic, extreme and different, bible fields complete).
- After the gates: `uv run tools/bible_check.py` then `uv run tools/heal.py prepare <dir> --kind writing` writes `heal/critic-brief.md` and, if anything failed, `heal/fix-brief.md` in the series folder. A Sonnet critic answers `kb/quality/critic-checklist.md` into `heal/critic.json`; `heal.py classify` maps each fault to a class, a fix place and a fixer (`kb/quality/heal-playbooks.md`); the fixer repairs the root cause, records it with `heal.py round`, and the stage reruns. Up to 3 rounds; then stop and report.
- the owner sees this only when `uv run tools/heal.py status <dir>` says ready: all gates pass, critic score 9 or more of 10, guard clean. Never loosen a gate, edit a trace or hide a fault; the guard refuses it.
- Then `heal.py learn` writes each healed fault to `kb/lessons/ledger.jsonl`. Full loop: [HEAL.md](HEAL.md).
