# 🖋️ Sketch stage: the art book

Starts only when the bible of the piece is approved (writing stage). Output: black-and-white ink sheets per character and world, and the **Art Book** tab (`previews/index.html#artbook`) for the owner. Black, white and greys only; Thmanyah for every word.

## 🧭 Steps

| # | Step | Who | Output (checkpoint file) | Done when |
|---|---|---|---|---|
| 1 | Read the bible: fields marked `SKETCH`, `CATALOGUE`, `RIG` (looks, silhouette, wardrobe layers, props, handedness, 8 emotions, `height_head_units`) | Sonnet | notes in the module comments | nothing in the module is invented |
| 2 | Build the **character module** `tools/render/characters/<id>.js` (contract: `tools/render/characters/README.md`). For a world: `tools/render/worlds/<id>.js` with `bible_world: "<world file>"` | **Sonnet draws** | the module + catalogue data (`catalogue/characters/<id>/`: `character.json`, `physics.json`, model, face with nose/lips/visemes, hands, grips) | `registerCharacter` loads without error |
| 3 | Render the sheets: `uv run tools/sheets.py character <id>` / `world <id>` | Sonnet (`sw-character-artist`, `sw-world-artist`) runs it | `catalogue/characters/<id>/<sheet_version>/sheets/` (`01-shapes` to `08-props`, SVG + 300 dpi PNG + `sheets.json`); worlds: `catalogue/environments/<id>/<v>/sheets/` (`w1` to `w4`) | the tool prints `OK` |
| 4 | Assemble: `uv run tools/artbook.py build` | **Sonnet assembles** | the Art Book tab (spreads per `kb/templates/artbook-*-spread.md`, captions cut from bible lines) | exit 0 |
| 5 | Check: `uv run tools/artbook.py check` (and the suite `uv run pytest tools/tests`) | **Sonnet checks** | the four PASS lines | see below |
| 6 | Culture reviewer seat signs the spread or records "pending" | Sonnet | note on the spread | per R-041 |
| 7 | the owner's read: open `previews/index.html#artbook`, point to the spread | Lead | his notes in `bible/feedback/` | his decision |

A changed bible line means re-run steps 3 to 5 for that piece only; a changed module hash makes `ARTBOOK-MATCH` fail until the sheets are re-rendered.

## ✅ Checks (`uv run tools/artbook.py check`, add `--built-only` while pieces are still pending)

- **ARTBOOK-SHEETS**: every character of the series has sheets 01 to 08, every world w1 to w4 (SVG and PNG on disk).
- **ARTBOOK-INK**: PNG chroma at most 8 of 255 and SVG colours only black, white, greys.
- **ARTBOOK-MATCH**: drawn height and shoulder width equal the module, the catalogue `character.json` and the bible (2 %); the rig profile is the one the bible names; the SVGs are the ones that were measured (sha256).
- **ARTBOOK-TEXT**: every caption has a source file and line, and its text is found in that bible line. Never type a caption by hand.

If a check fails: fix the module or the bible, re-run the sheets, never edit the check. Exit 1 on any FAIL.

## 🎨 What the Sonnet artist produces

**Per character**: the module `characters/<id>.js` (proportions, palette, handedness, `solve/drawBody/drawArms`, mass proxy, and the `sheet` block: mannequin sizes, 4 gesture poses, wardrobe layers, `figure()` for front / three-quarter / side / back with the layer order per angle, the 8 emotions as action units, three head-study picks, hands and grips per hand, 8 props), plus `catalogue/characters/<id>/` (`character.json`, `physics.json`, `v1/model/mannequin.json`, `face.json` with nose, lips, visemes, `hand-model.json`, grip files). Every shape traces to a bible line.

**Per world**: `worlds/<id>.js` (`bible_world`, rule, light, set drawing) with the sheet block: one establishing plate, six key places, ten props, six materials.

## 🧑‍🤝‍🧑 Roles

Sonnet artists draw (modules, sheets); Sonnet checks (the four checks, the culture seat); Sonnet assembles (build, re-runs, file moves). GPU Chromium renders; one page, closed at the end. Previews must still pass `uv run tools/quality_gate.py preview previews/index.html --static`.

## 🩹 Healing (optional stage, on by default)

The critic reads each sheet (CQ-A1 to CQ-A9: same person on every sheet, side and back views, nose per angle, cloth, ink only, every sheet re-looked, fixed in shared code). A shared-code fix re-renders every character.
- After the gates: `uv run tools/artbook.py heal` writes `heal/critic-brief.md` and, if anything failed, `heal/fix-brief.md` in `work/artbook`. A Sonnet critic answers `kb/quality/critic-checklist.md` into `heal/critic.json`; `heal.py classify` maps each fault to a class, a fix place and a fixer (`kb/quality/heal-playbooks.md`); the fixer repairs the root cause, records it with `heal.py round`, and the stage reruns. Up to 3 rounds; then stop and report.
- the owner sees this only when `uv run tools/heal.py status work/artbook` says ready: all gates pass, critic score 9 or more of 10, guard clean. Never loosen a gate, edit a trace or hide a fault; the guard refuses it.
- Then `heal.py learn` writes each healed fault to `kb/lessons/ledger.jsonl`. Full loop: [HEAL.md](HEAL.md).
