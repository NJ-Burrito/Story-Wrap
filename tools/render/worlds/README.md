# World module contract

One file per world place: `tools/render/worlds/<id>.js`, ending in `registerWorld({...})` (sets `WORLD`; throws on a missing key). Reference: `world-a.js` (the office under the quay, which is one place of the bible world `port-monsoon`).

## Required keys

| Key | What it is |
|---|---|
| `id`, `name_ar`, `version`, `sheet_version` | `sheet_version` = folder under `catalogue/environments/<id>/` (e.g. `"v1"`) |
| `bible_world` | the world file it draws: `bible/series/<series>/worlds/<bible_world>.md`. `ARTBOOK-SHEETS` matches worlds to modules by this |
| `rule` | the story's rule for the place, one sentence, from the bible |
| `light` | `{key, horizon}`: one light source, one horizon (R-076, R-077) |
| `locations[]`, `materials[]` | names of the key places and materials (must equal the ids drawn in `sheet`) |
| `initPatterns()` | optional: builds the world's own painted textures; `core.initPatterns` calls it. Textures belong to the world, never to `core.js` |
| `sheet` | the sheet block below |

The film drawing (set, props, light, shadow receivers: `drawBackdrop`, `drawCounter`, `PROPS`, ...) stays in the same file; the generic renderer reaches it only through the shot scene.

## The `sheet` block (drawn by `tools/sheets.py world <id>`)

All draws take `(g, box)` with `box = {x,y,w,h}` in page units; ink strokes, white and grey fills, hatching for shade (heavier far from the light).

| Key | Content |
|---|---|
| `establishing` | `{note, draw}`: one plate, full frame: the value key for the whole world |
| `locations[]` | `{id,label,note,draw}`, six key places (sheet w2) |
| `props[]` | `{id,label,note,draw}`, ten props that fill the place (sheet w3) |
| `materials[]` | `{id,label,note,draw}`, six surfaces and how each is hatched (sheet w4) |

Cue objects must be specific and traceable to a bible line (stereotype list R-043); the power or technology of the world must be visible in at least one plate (R-061).

## Labels and layout (shared code, 2026-10-23)

- Every page title, subtitle and section label comes from the module: `sheet.labels = {establishing: {title, sub}, locations: {title, sub}, props: {title, sub}, materials: {title, sub}}` (the establishing subtitle defaults to `establishing.note`). The defaults are neutral ("key places", "props", "materials") and name no place or object; set the wording for the world in the module.
- The grid follows the item count: 1-6 as 3x2, 7-8 as 4x2, 9-10 as 5x2, 11-12 as 4x3, 13-15 as 5x3, 16-18 as 6x3; more are paginated onto `w2b-locations`, `w3b-props`, ... (`w1` to `w4` are always present).
- Ink helpers shared with the characters: `Ink.brush, hatch, crossHatch, spotted, crs, rib, clipPoly` (`svgctx.js`, loaded on world pages too), and `Sheets.hatchIn`.
- The sheets page loads `core.js`, `geom2d.js`, `svgctx.js`, the world module, `sheets.js`.
