# Construction and catalogue: how a figure is built, stored, attached and shadowed

Trigger: the owner's notes on Mix v2, 2026-10-23 (`bible/feedback/2026-10-23-mix-v2.md`): F5 (fingers, needle, hijab and what is under it do not connect), F7 (body ugly, shoulders from the middle, build the way artists do, keep a catalogue), F8 (shadow copies the illustration, not the mass). Evidence and root causes: `kb/quality/rca-construction.md`. Rules R-340 to R-359. Grades: S = source read, J = judgement, M = measured in our files.

## 1. Build process (only for a NEW character or a NEW position)

A returning character in a catalogued pose and angle is never rebuilt: it is looked up (section 2). Build only what the catalogue lacks.

| Step | What is made | Output (file) | Done when |
|---|---|---|---|
| 1 Gesture | One action line, C, S or straight; 30 s to 2 min [S Proko] | `gesture.svg` | the pose reads from the line alone |
| 2 Shapes | Head ball, chest and pelvis boxes, cylinders for limbs, spine line between them; the shoulder line (clavicle) sits on the top of the chest box | `mannequin.json` (joints, segment lengths, clavicle line, head unit) | joint list complete, proportions in head units, shoulder line drawn |
| 3 Sketch over | Contour, clothing and hair drawn over the mannequin, never replacing it; layers built inside out: body, neck, under-layer, garment | `sketch.svg` with named layers | every garment layer sits on a named mannequin part |
| 4 Angles | Front, three-quarter, side, back of the same mannequin; the camera angle comes from the shot first (F3) | `angles/*.json` | each angle has its own layer order (R-352) |
| 5 Clean line | Final art cut into rig parts: one part per joint plus cloth | `parts/*.svg`, `rig.json` | part outlines overlap at every joint (R-343) |

Order: gesture, simple shapes, mannequin, sketch over, angles, clean line [S https://www.proko.com/course-lesson/mannequinization-structure-of-the-human-body/ and its community threads: build the mannequin on top of the gesture so the gesture is not lost; losing it makes figures stiff].

## 2. Catalogue format

Studios hold a character constant with model sheets: turnaround (front, three-quarter, side, three-quarter back, back), expression sheet, pose sheet; a drawing that matches is "on-model" [S https://blog.cg-wire.com/character-sheet-animation, https://www.clipstudio.net/how-to-draw/archives/164740]. In 2D rigs a library of drawing substitutions (hands, mouths, eyes) sits on the rig under a master controller [S https://docs.toonboom.com/help/harmony-21/premium/cut-out-animation/about-swap-drawing.html, https://forums.toonboom.com/t/script-to-attach-substitute-drawings-to-controls-in-rig/11236]. Spine separates bone hierarchy from draw order with slots [S https://esotericsoftware.com/spine-slots]. We do the same in plain files.

```
catalogue/   (real location: catalogue/characters/<char-id>/, index.json per character)
  INDEX.json                       one line per entry: {id, kind, version, status, path, hash, used_by[]}
  characters/<char-id>/
    character.json                 id, head_unit, proportions, mechanics (F1), accent, version history
    v1/
      model/        mannequin.json  rig.json  parts/*.svg
      angles/       front.json  three-quarter-L.json  side-L.json  back.json   (anchors + layer order per angle)
      poses/        <pose-id>.json   joint angles, grip refs, weight, silhouette name
      expressions/  <expr-id>.json   eyes, brows, mouth, cheeks, head tilt, the feeling it carries (F6)
      body-language/<id>.json        posture, gesture set, tell (bible "tell"), when used
      hands/        <grip-id>.json   finger poses + the object it fits
      garments/     <id>.json        parent part, layers beneath, drape rules (hijab, coat)
      mass-proxy.json                shadow proxy volumes (R-355)
  props/<prop-id>/v1/   prop.json (size in head units, mass proxy, grip points, parent options, materials) + art
  environments/<env-id>/v1/   set.json (planes, receivers, light sources, surfaces with heights, contact zones) + art
  cameras/<angle-id>.json       focal, height, tilt, which characters and props have art for it
```

Index entry example: `{"id":"hero/pose/write-tag","kind":"pose","version":"1.2","status":"approved","path":"characters/hero/v1/poses/write-tag.json","used_by":["ep01-s03"]}`.

A shot spec never copies a pose or model, it references it by id and version (fields proposed in `rca-construction.md`).

## 3. Rules R-340 to R-359 (each with a check)

### Construction (F7)

- **R-340 Build before draw.** A new character or new position has `mannequin.json` and `gesture.svg` before any clean art. Check: a catalogue entry cannot reach status `approved` without both files. Exempt: a catalogued pose.
- **R-341 Shoulders sit at the ends of the clavicle line.** Each shoulder joint is at the outer end of the clavicle line, on the top of the chest box, at the body outline at that height and lower than the neck base. Check (machine): shoulder anchor x is at least 85% of the torso half-width at shoulder height, and its y is within 0.03 head units of the clavicle line (`rca-construction.md` G3).
- **R-342 Neck and trapezius exist.** Head and torso are joined by a neck part, or by a garment that drapes over a neck and declares so. The head part never ends exactly where the torso starts. Check: neck length at least 0.25 head unit in `mannequin.json`.
- **R-343 Parts overlap at every joint.** Each limb part extends under its parent by at least one joint radius (a ball or cap), so rotation never opens a gap or shows a straight cut. Check: per joint the child cap radius is at least the child half-width and covers the pivot.
- **R-344 Proportion in head units, per character.** 7.5 to 8.5 heads is a start only [S kb/guides/drawing.md]; the numbers are recorded in `character.json` (upper arm, forearm, torso, leg in head units). Check: rendered segment lengths stay within 2% of the recorded lengths in every frame, unless the bible names a rubber or stretch attribute (F1).
- **R-345 One mannequin, many angles.** The same joint list and segment lengths serve every angle and pose. Check: `angles/*.json` reference the model version and list the same joint ids.

### Catalogue (F7)

- **R-346 Look up before build.** Before drawing, the writer queries `INDEX.json` for character, pose, expression and camera angle. A hit is referenced, a miss goes through section 1 and is added. Check: the shot spec lists a catalogue id for every character, pose and angle; the gate refuses an unknown id.
- **R-347 Versions are immutable.** `v1` is never edited after approval; a change is `v2` plus a changelog line. A shot keeps the version it was approved with. Check: the file hash in `INDEX.json` matches.
- **R-348 Entries are parameters, not pictures.** Poses, expressions and body language are stored as parameters on the rig (joint angles, part swaps) so they recombine. Check: schema-valid JSON; no entry that is only an image.
- **R-349 Entries carry meaning.** An expression or body-language entry records the feeling, its cause in the story and its tell (F6). Check: non-empty `feeling` and `tell`.

### Attachment (F5)

- **R-350 Declare parent and contact.** Every held object and every garment piece lists `parent` (a rig part), `parent_anchor` (a named point on it) and `contact_points` (where hand or body touches it). Check: the spec lists all three; the gate refuses an object without them.
- **R-351 Contact is a constraint, not a coincidence.** In every frame the child's contact points stay within N px of the parent anchor (N = 0.4% of frame width, about 4 px at 1080). The IK target is the contact point (grip centre, pen tip on paper), never the wrist. If the target is out of reach the parent moves (lean, step) or the object comes with the hand; the object is never left behind. Check (machine): per-frame distance report (`rca-construction.md` G1).
- **R-352 Layer order is declared per camera angle.** Each attachment lists the draw order for each angle, back to front, with the reason (for example: pen behind the index finger and in front of the palm; thumb over the pen). Check: the spec has `layer_order` per angle; the render dump matches it.
- **R-353 Hands grip with fingers.** A hand holding a thing has separate parts: palm, thumb, index, and the other fingers, with a grip pose from `hands/`; the fingers wrap and conform to the object [S low-quality tutorials https://drawingtest.rjuuc.edu.np/read/how-to-draw-a-hand-holding-a-pencil.html; use the Proko hand lessons in `kb/guides/drawing.md` level 3 as the real source]. A pen rests in the web between thumb and index, crosses under the index finger, and presses at its tip on the surface. Check: at least 3 finger parts, each with its own place in the layer order relative to the held object.
- **R-354 Garments sit on layers, built inside out.** Order: body, neck, under-layer, garment, accessories. A headscarf (hijab) is built as: head and face; hairline hidden by an under-cap or by the scarf's inner edge; the scarf wrapping the head with a visible fold at the forehead, the temples and under the chin; then the drape falling to the shoulders and chest, covering the neck if the style does. Hair is never drawn outside the scarf for a character who wears it; the face shows brows, eyes, nose and mouth only. Check: no hair part is placed in the face opening unless the profile says hair is shown; the drape part names a parent (neck or shoulders) and a lag. Accuracy: styles differ by region and community (wrap, turban-style, long drape), and the style comes from the character profile and the culture reviewer, not from a fashion shop page [S https://www.hautehijab.com/pages/hijab-style-guide describes fashion practice only; underscarf or cap as base, wrap, drape, neck covered or not]. Respect: the scarf is clothing with structure (cap, fold, pin, drape), never a flat ring around a face.

### Shadow (F8)

- **R-355 Shadows come from a mass proxy.** Each character and prop has `mass-proxy.json`: a few closed, simple volumes in world units (head ellipsoid, neck cylinder, torso box, limb capsules, garment hull). The cast shadow is the projection of the proxy from the light, never a re-drawing of the art. Check: the spec names `shadow.source = "mass_proxy"` and the proxy id.
- **Note (R-380, 2026-10-23):** the mass proxy decides the shadow's *shape and place* only. The shadow is then drawn as a flat 2D shape with a hard edge (one or two cel tones). Never blur it, never fill it with a gradient: Mix v3 did, and it read as 3D. Check `SHADOW-FLAT`, `look2d`.
- **R-356 No holes, no cut-outs.** The projection is one connected mask: the volumes are unioned before projection, and every path fills with one winding direction. Check (machine): the shadow mask has no interior hole larger than 4 px, and no gap between head and torso volumes (`rca-construction.md` G2).
- **R-357 Contact shadow at every contact.** Where a body or object touches a surface (hand on counter, jar on counter, elbow on desk, feet on ground, held object on skin) a tight, dark, soft shape sits under it, narrower than the cast shadow and darkest at the contact point [S https://gamedev.net/shaderlab/32-soft-shadows-and-ambient-occlusion/: shadows where light cannot reach and creases that block ambient light ground objects]. Check: each `contacts` entry has a contact-shadow layer.
- **R-358 Soft versus hard follows the light.** Penumbra width grows with light size and with the distance from caster to receiver: near zero at contact, widest at the far end [S https://archive.gamedev.net/archive/reference/articles/article2032.html; Harmony soft shadow: https://docs.toonboom.com/help/harmony-20/premium/effects/cast-shadow/about-soft-shadow-options.html]. Check: each light has `size`; blur is a function of caster distance, not one constant.
- **R-359 Self-shadow and receiver shape.** A shadow on a wall follows the wall (steps, shelves, gaps), and the body shades itself (head on neck, arm on coat) from the same proxy. A gap in the receiver (aisle, window) lists what shows through it so the shadow continues at the right place instead of being clipped. Check: no clip rectangle without a declared receiver; at least one self-shadow per beat on the character.

## 4. What changes in the pipeline

1. After writing, **pre-production**: catalogue lookup, and construction for what is new, before sketch and animation.
2. The shot spec carries catalogue references, attachments and shadow source (`rca-construction.md`, Gate proposals).
3. The renderer writes a per-frame debug dump (anchors, contact points, layer order, shadow mask) for the gate.
4. A reviewer opens one frame per beat and looks at shoulders, hands, scarf and shadow edge.

## 5. Gaps and cautions

- Live2D draw-order and Moho bone-layer sources were not found; Spine and Toon Boom are cited from their documentation.
- The hijab sources found are retailer guides: they show mechanics, not culture. The culture-check seat (CLAUDE.md) decides the style per character, and the owner gives the final read.
- The hand-grip tutorials found are low quality; read the Proko hand lessons before drawing the first grip pose.
