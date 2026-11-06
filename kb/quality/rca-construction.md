# RCA: construction, attachment and shadow in Mix v2 (F5, F7, F8)

Evidence: Mix v2 renderer in `previews/index.html` (read-only; line numbers below), `work/demo-v2/shot-spec.json`, `work/demo-v2/mix-v2.mp4`. Frames extracted with ffmpeg (cuda, 2 threads) into `work/rca/construct/` (`f_<seconds>.png`, `sheet1.png` = 1.5 s, 3.8 s, 8.0 s; `c6.png` = crops at 6.0 s and 2.5 s). Fixes live in `bible/craft/construction-catalogue.md` (R-340 to R-359). Grades: M measured/seen in file or frame, S source, J judgement.

## Summary in three lines

1. The figure is drawn as flat shapes in screen order with no skeleton of construction: the shoulder joint is a constant 0.15 m inside a rectangular coat, the arms are painted over the chest, and there is no neck, no clavicle, no under-layer. [M]
2. Held and worn things are positioned by offsets from the wrist or the head ellipse, with no parent, contact point or occlusion rule, so the pen drifts, the hand has no fingers and the hijab is a ring with hair on top. [M]
3. The shadow re-runs the drawing code with fills only, scaled from the lamp, so it inherits every hole and clip of the art and never uses a mass. [M]

## RC-A. Why the shoulders come from the middle (F7)

| Evidence | Where |
|---|---|
| Shoulder joints are the constants `sh = [[-.15,-.38],[.15,-.38]]`, unrelated to the coat outline | `previews/index.html:745` |
| The coat is a rectangle-ish path: top corners at x = ±.20 (y -.40), widest ±.25 at y -.36; shoulder x .15 is 0.05 to 0.10 m inside the outline; the top edge is a smooth quadratic to y -.47, so there is no shoulder slope or clavicle line | `:752-754` |
| Arms are capsules from the shoulder point, radius .046, drawn AFTER the torso, so the round shoulder cap lies on the chest, 0.15 m from the centre | `:799-806` |
| Head origin at y -.44; head ellipse centre -.15, radius .17, so its bottom is y -.42, and the torso top is about -.435 to -.47: head touches torso, no neck part exists | `:766-767` |
| In the frame, upper arms leave from the middle of the coat chest and the head sits on the coat | `work/rca/construct/c6.png`, `sheet1.png` |
| The shot spec lists 16 parts (pelvis, torso, head, arms, hair, tails) but no neck, no clavicle/shoulder, no upper-chest part, and no proportions in head units | `work/demo-v2/shot-spec.json`, `characters[0].parts` |

Root cause. The figure was designed as a costume silhouette first (oversized coat, jagged tags) and the skeleton was bolted on afterwards: joint positions were picked by eye in coat coordinates (R-340 missing). Nothing in the schema asks for a construction (mannequin, clavicle line, neck, head units), so a spec of 16 parts passed `minItems: 8` with the construction missing. The coat is also the only body mass: an oversized coat hides the body that should define where the shoulders are. Proportions are checked nowhere.

Fix: R-340 to R-345; gate G3 and the spec field `anchors` (below).

## RC-B. Why fingers, the pen, the hijab and what is under it do not connect (F5)

1. **The hand has no fingers.** The hand is an ellipse plus a second thin ellipse for a thumb, filled in one pass (`:810-811`). Grip is one number `grip` that squeezes an ellipse. No finger parts, no wrap, no occlusion of the held object. [M, frames 1.5 s and 2.5 s: orange blob with a stick]
2. **The pen is a line painted over the hand at a fixed offset.** `line(.06,-.01,.14,-.07, 4.5)` in the wrist frame (`:812`), drawn after the hand, so the pen is on top of every finger and never passes behind one. Its tip is at wrist + (.14,-.07) rotated by the forearm angle. The IK target is the WRIST, not the pen tip (`:803`, `heroPose` `p.tA = ...A.JT`, line ~736): when the forearm rotates the tip leaves the tag. At 6.0 s the tip is below the counter edge (`c6.png`, left). [M]
3. **Out-of-reach targets detach the hand.** `ik` clamps the distance to `a+b-1e-3` (`:711-713`, reach 0.45 m) and leaves the wrist short of the target; nothing moves the torso or the jar, so a held thing and the hand part ways. [S from code; effect on the jar visible at 2.5 s as the hand hovering over the jar rim]
4. **Draw order is call order, global, and not per angle.** Scarf tail, coat, collar, tags, head, then arms (`:748-815`). Arms are always on top of the coat and head. There is no per-attachment layer order, no parent, no contact record (spec has no such fields). [M]
5. **The hijab is a filled ellipse with a face ellipse stamped over it.** One path: ellipse plus a bottom polygon (`:767`), then dots (`:768-769`), then the face ellipse (`:771`), then a stroked ellipse as the front band (`:793-795`). There is no under-cap, no fold at the forehead, no pinned drape, no neck: the lower edge of the head ellipse sits on the coat collar. [M, `sheet1.png`: a ring around a flat face with an astronaut-helmet look]
6. **Hair strands are drawn on the face on top of the scarf** (`:776-779`, three strokes from y -.235 to -.195 inside the face ellipse). They read as hair showing under or through a hijab, which is wrong for the character and not respectful. [M]
7. **Nothing under the scarf is built.** No neck, no hair mass, no cap, no ears: what lies under the scarf was never created, so nothing can be revealed or connected when the head turns (`tx` shifts only the face ellipse by 0.6 of the scarf shift, `:767-771`).

Root causes (shared). (a) Attachments are drawn, not declared: the spec has no `parent`, `parent_anchor`, `contact_points` or `layer_order` per angle (R-350 to R-352 missing). (b) Targets are wrist-based, not contact-based (R-351). (c) The hand and the garment were never constructed as layered parts, only as outlines (R-353, R-354). (d) The gate measures motion, light and depth over the whole frame; it cannot see a pen 6 px off its hand.

## RC-C. Why the shadow copies the illustration (F8)

| Evidence | Where |
|---|---|
| The shadow calls `drawHero(...)` again with `SHADOW = true`; `solid()` then only runs `ctx.fill()` on the same paths (`:585`) | `:932-939`, `:585` |
| The call is scaled by `m = (ZP - KEY.z)/(root.Z - KEY.z)` and drawn twice (alpha .18 at 1.05x, .38 at 1.0x): a magnified silhouette copy, not a projected volume | `:932-938` |
| The head solid is ONE path: `ellipse(...)` (clockwise) plus a polygon `moveTo(-.13,-.08) ... (.13,-.08)` that runs counter-clockwise. Under the canvas default non-zero fill, overlapping opposite windings cancel (winding 0) so the overlap, the jaw and neck region, is a hole. At the projection scale it shows as a cut-out | `:767` |
| Parts without a `SHADOW` branch simply vanish from the shadow: `if (SHADOW) return` or `!SHADOW` guards skip hair, tags' strings, hand details, band | `:656, 671-676, 776, 793, 812` |
| The shadow is clipped to the two quads left and right of a gap (`poly` -2.6..-.5 and `poly2` .5..2.6), so the middle 1.0 m of the back unit receives nothing; the shape is cut at both edges | `:934` |
| One constant blur/alpha pair for all distances, no penumbra growth, no contact shadow at the hand, jar or counter | `:932-938`; counter shadows exist only for jar, ledger, bag (`:1042-1048`) |
| In frames, a large dark disc with a thin lighter ring on the right (8.0 s, 3.8 s) and gaps at neck and under the chin of the head shadow | `sheet1.png`, `c6.png` |

Honest note [J]: the large dark disc on the right is the magnified head/scarf shape plus the second pass; I did not isolate each sub-shape with a pass-by-pass render, because the brief forbids heavy CPU and edits to the source. A one-line diagnostic: fill with `"evenodd"` and with a single winding and compare.

Root cause. The shadow is defined as "the drawing, darker" instead of "the mass, projected". Any hole, winding error, clip or missing branch in the art appears in the shadow, and the art is not built from volumes, so the shadow cannot be accurate (R-355, R-356). Spec side: `cast_shadows` only needs `caster` and `receiver` strings (`kb/quality/shot-spec.schema.json`), and the demo spec passes with `caster: "hero"`.

## Gate proposals

Principle: refuse before render (spec), then verify per frame (debug dump). The renderer must write `work/<ep>/debug.jsonl`, one line per frame: anchors, contact points, layer order, and the shadow pass as a mask PNG.

### G1. Attachments stay within N px of their parent anchor across frames

Spec diff (`kb/quality/shot-spec.schema.json`), under `characters[].items.properties`, add:

```json
"model_ref": { "type": "object", "required": ["id","version"],
  "properties": { "id": {"type":"string"}, "version": {"type":"string"} } },
"anchors": { "type": "object",
  "required": ["clavicle_L","clavicle_R","neck_base","head_unit_px"],
  "description": "Named points on the rig. clavicle_* are the outer ends of the shoulder line." },
"attachments": { "type": "array", "minItems": 1,
  "items": { "type": "object",
    "required": ["id","child","parent","parent_anchor","contact_points","layer_order","max_gap_px"],
    "properties": {
      "id": {"type":"string"}, "child": {"type":"string"},
      "parent": {"type":"string"}, "parent_anchor": {"type":"string"},
      "contact_points": {"type":"array","minItems":1,"items":{"type":"string"}},
      "layer_order": {"type":"object",
        "description": "camera angle id -> list of part ids, back to front",
        "additionalProperties": {"type":"array","items":{"type":"string"}}},
      "max_gap_px": {"type":"number","default":4} } } }
```

Add `"model_ref"` and `"attachments"` to the character `required` list. In each beat add optional `catalogue`: `{ "pose": "id@version", "angle": "id", "expressions": ["id@version"] }` (required once the catalogue exists; R-346).

Machine check, `tools/quality_gate.py construct <debug.jsonl>`:
`for each frame, for each attachment: d = |child.contact - parent.anchor| in px; FAIL if d > max_gap_px for more than 1 frame in a row; report frame, id, d.` Also FAIL when the draw order in the dump differs from the declared `layer_order` for the beat's angle. Expected on Mix v2: pen tip vs jar tag fails (tip offset about 0.15 m x scale, tens of px, and 6.0 s hand-on-counter), proving the gate.

### G2. Shadow comes from a mass proxy and has no interior holes

Spec diff, in `beats[].cast_shadows[].items`: change `required` to `["caster","receiver","source","proxy"]` and add:

```json
"source": {"enum": ["mass_proxy"], "description": "Never the drawing (R-355)."},
"proxy": {"type":"string", "description":"id of a volume set in mass-proxy.json"},
"light": {"type":"string", "description":"key|fill|lamp id; its size sets the penumbra (R-358)"},
"contacts": {"type":"array","items":{"type":"object","required":["a","b"],
  "properties":{"a":{"type":"string"},"b":{"type":"string"},"occlusion":{"type":"boolean","default":true}}}}
```

And `beats[].required` gets a `contacts` rule: at least one contact shadow per surface contact listed in `interactions` of kind `contact` or `grab`.

Machine check: the renderer writes the shadow pass for each sampled frame (every 6th) to `shadow_<f>.png`. The gate computes `holes = binary_fill_holes(mask) & ~mask`, drops components under 4 px, FAIL on any left; and FAIL if the mask has more than one connected component per caster while the proxy is declared connected (catches clip cut-outs). Cheap: numpy plus `scipy.ndimage`, 1080x1920 masks downscaled by 2. Code fix pointer for the renderer (not done here): `:767` use `ctx.fill("evenodd")`-free single winding (draw the polygon with the same direction as the ellipse, or union via a second `fill()`), and replace `drawHero(... SHADOW)` by projecting `mass-proxy.json` volumes.

### G3. Shoulder anchors at the ends of the clavicle line

Spec: `anchors.clavicle_L/R` (G1 diff) plus `proportions` in `character.json`. Machine check on the debug dump, neutral and animated frames: with `halfW(y)` = half width of the torso mask at the shoulder anchor's y, FAIL if `abs(shoulder.x - torso_center.x) < 0.85 * halfW(shoulder.y)` or `abs(shoulder.y - clavicle_line.y) > 0.03 * head_unit_px`, or `neck_length < 0.25 * head_unit_px`. Mix v2 numbers [M from code]: shoulder x = .15, coat half-width at that height about .20 to .25, ratio .6 to .75: FAIL.

### G4 (smaller). Segment length and hair-on-scarf

- Segment lengths per frame within 2% of the catalogue values (R-344), except declared rubber parts.
- A part tagged `hair` may not be drawn inside the face opening when the character profile has `covers_hair: true`; fails Mix v2 (`:776`).

### Rollout order

1. Add the catalogue folder and `INDEX.json` with Hero (one pose, two angles) as the pilot.
2. Add the schema fields as optional, run the gate in warn mode on `work/demo-v2/shot-spec.json`, then make them required with a one-line version bump in the schema `$id`.
3. Renderer: emit `debug.jsonl` and shadow masks (a `?debug=1` switch in the renderer).
4. Re-run the Mix v2 build once under the Owner exception (one run, one fix per reported fault).

## Research used (S)

- Mannequin and gesture build order: https://www.proko.com/course-lesson/mannequinization-structure-of-the-human-body/
- Model sheets and turnarounds, "on-model": https://blog.cg-wire.com/character-sheet-animation ; https://www.clipstudio.net/how-to-draw/archives/164740
- Toon Boom swap drawings, substitution libraries, master controllers: https://docs.toonboom.com/help/harmony-21/premium/cut-out-animation/about-swap-drawing.html ; https://forums.toonboom.com/t/script-to-attach-substitute-drawings-to-controls-in-rig/11236
- Spine slots and draw order separate from bone hierarchy; re-parenting changes order: https://esotericsoftware.com/spine-slots ; https://ko.esotericsoftware.com/forum/d/27858-attachment-order
- Hijab mechanics (cap, wrap, drape, neck), fashion-shop source, not culture authority: https://www.hautehijab.com/pages/hijab-style-guide
- Penumbra, umbra, contact and ambient occlusion: https://archive.gamedev.net/archive/reference/articles/article2032.html ; https://gamedev.net/shaderlab/32-soft-shadows-and-ambient-occlusion/ ; https://docs.toonboom.com/help/harmony-20/premium/effects/cast-shadow/about-soft-shadow-options.html
- Hand grip tutorials (low quality, start only): https://drawingtest.rjuuc.edu.np/read/how-to-draw-a-hand-holding-a-pencil.html

Gaps: Live2D and Moho layer-order sources not found; a proper hijab reference from Muslim artists or the culture reviewer is still needed before drawing; hand lessons from Proko were not read in full.
