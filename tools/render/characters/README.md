# Character module contract

One file per character: `tools/render/characters/<id>.js`. The generic renderer (`core.js`, `face.js`, `hands.js`, `trace.js`, `insert.js`, `bootstrap.js`, `sheets.js`) never names a character; it reads the active one through the global `CHAR`, set by `registerCharacter({...})` at the end of the module. `registerCharacter` throws if a required key is missing; `tools/tests/test_sheets_contract.py` checks the same list statically.

Reference module: `hero.js`. Read it next to this page.

## Required keys

| Key | What it is |
|---|---|
| `id`, `name_ar`, `version`, `sheet_version` | the id is the folder name in `catalogue/characters/` and `bible/.../characters/`; `sheet_version` is the catalogue version folder the sheets are written to (e.g. `"v4"`) |
| `hu_m` | metres per head unit (sets `HUM`) |
| `proportions_hu` | `height, head_h, shoulder_w, neck_len, upper_arm, forearm, hand, thigh, shank` in head units. Must equal `catalogue/characters/<id>/character.json` and the bible (`height_head_units`, shoulder width): ARTBOOK-MATCH |
| `rest_lengths_hu` | `upper_arm`, `forearm` drawn lengths the rig keeps constant |
| `physics_profile`, `mass_class` | the id in `catalogue/characters/<id>/physics.json`, named in the bible |
| `palette` | `skin, coat, ...` as `[r,g,b]`; the film uses colour, the sheets never do |
| `handedness`, `sides` | `{write, give, take, greet, indicate}` = `"L"` or `"R"`; `sides` is `["L","R"]` (L = the character's left = screen right when facing us). The bible's `handedness` field is the source |
| `root`, `z` | pelvis position and depth plane in the world (the shot places the body) |
| `data` | catalogue files, relative to `catalogue/characters/<id>/`: `model` (mannequin joints), `face` (oval, eyes, brows, **nose**, **lips**, **visemes**), `hand_model`, `grip_dir`, `grips[]`, `expression_dir`, `expressions[]`, `garments[]`, `mass_proxy` |
| `solve(s, R0)` | body solve for a shot frame: chest transform, 2-bone IK arms of constant length, head, garment outlines. Returns `R` (`R.arm[L/R]`, `R.HC`, ...) |
| `drawBody(R, cutY)`, `drawArms(R, extras, opts)` | the film drawing: one merged silhouette per group, garments in layer order, hands in the grip's declared layer order |
| `massProxy(R)`, `massProxyOnPlane(R, Zr)` | closed volumes for the cast shadow (R-355); the shadow is then drawn flat |
| `sheet` | the sheet block below |

Everything character-specific lives here: garment outlines and their layer order per angle, face drawing parameters, hand grips and the pen/prop extras, handedness, palette, proportions. Shots and the generic files only call `CHAR.*`.

## The `sheet` block (read by `tools/sheets.js`, drawn by `tools/sheets.py character <id>`)

Black ink, white and greys only. Geometry is data; no canvas calls outside `hand` and `props`.

| Key | Content |
|---|---|
| `mannequin` | `radius{thigh,shank,foot,upper_arm,forearm,hand_tip}`, `hand_len`, `chest{y0,y1,a,b}`, `pelvis{...}`, `neck_r`, `head{rx,ry}`, `shoulder_cap`, `floor_pad`; joints come from `data.model` |
| `gesture_poses[]` | `{id,name,note,lean,head,armL:[deg,deg],armR,stance}` for sheet 01 |
| `layers[]` | wardrobe layers, inside out (sheet 03; from the bible `wardrobe_layers`) |
| `angles[]` | `{id,label,theta,faceYaw}`: front, three-quarter-L, side-L, back; `theta` degrees about the vertical axis, `faceYaw` -1..1 (1.6 = profile, `null` = no face) |
| `guides[]` | `{name,y}` guide lines of the turnaround |
| `figure(angle, {face})` | the silhouette builder: `{shapes[], order[], bbox{x0,y0,x1,y1}, head{c}}`. Shapes are `{id, pts, closed, smooth, fill: paper/g1/g2/g3/ink, hatch, holes, lw}` in head units (origin pelvis, y down), **back to front = the layer order for that angle** (R-352); a shape with `kind:"face"` is drawn by the shared face drawer with `face.au`. Garments carry their attachment by position (drape on the shoulder shelf, cloth around the head, tags on named anchors) |
| `emotions[]` | the 8 bible emotions `calm, joy, sadness, fear, anger, surprise, disgust, shame`: `{id, au:{FACS unit: 0..1}, eye:{eyeX,eyeY,iris}}`; each must match the bible's `### emotion:` block |
| `head_study` | three emotion ids for the art book's head study (neutral, the extreme trait, a reaction) |
| `hand(g, gripId, {x,y,k})` | draws one grip in ink in its layer order; returns `{note, layers[]}` |
| `props[]` | `{id,label,hand,draw(g,cx,cy)}`: each prop or signature object in ink, with the hand that holds it (bible `props_carried`) |

Face data (`data.face`) must hold `oval, eyes, brows, nose, lips, visemes` (nose at every angle, lips, mouth shapes). Hand model and grips are per hand, never mirrored (R-385).

## Checks that read it

`ARTBOOK-MATCH` (drawn proportions = module = catalogue = bible), `ARTBOOK-INK`, the v5 repro gates (`uv run tools/shot.py all work/shots/mix-v5-repro`), and `test_generic_renderer_files_do_not_name_the_character`.

## Shared code a module can rely on (v2 of the contract, 2026-10-23)

Load order on every page: `core.js`, `geom2d.js`, `svgctx.js` (sheets), `face.js`, `hands.js`, `write.js`, the module, `sheets.js`. A module no longer needs its own copies of the shared helpers.

- **2D helpers and the face slot**: `geom2d.js` exports `Geo2` and installs `rot2, add2, sub2, mul2, len2, unit2, lerp2, ik2` and the global `FD` (null until `bootstrap.js` / `sheets.js` assign it) as configurable globals. A module may still declare its own `const add2 = ...` (it shadows); delete those lines when convenient. `FD` and `HM3` are assigned by the tools, never by the module.
- **Ink** (`svgctx.js`): `Ink.crs, rib, brush(g,pts,w0,w1,wm), hatch(g,pts,deg,gap,lw), crossHatch, spotted(g,pts,{jitter,nicks,seed}), clipPoly, area, bbox`. `Sheets.hatchIn` calls `Ink.hatch`. Use them instead of local `rib`/`crs`/`clipPoly`.
- **Sheet 01 (gesture)** uses the character's own joints (`data.model`) and `sheet.mannequin` radii and boxes. Pose keys: `lean, head, armL:[upper,fore], armR, stance`, plus optional `pivot` (joint the torso leans about: `"pelvis"` default, `"waist"` for a stoop), `legL/legR:[thighDeg, kneeDeg]` (knee bends lower the pelvis, feet stay planted), `facing` (+1/-1), `feet_planted:false`. One scale for all poses.
- **Sheets 03/04** fit the page per figure: the scale comes from the extent of every shape (loads, props, the head), so an 8.5-head figure or a 9-head figure with a load fits. A module may set `fig.extent = {x0,y0,x1,y1}`. **Hands at figure scale**: set `sheet.hand_scale` (for example 2.2) and return `fig.hands = [{grip, at:[x,y] HU, label?}]` from `figure()`; each becomes a boxed inset drawn by the module's `hand()` with a leader line (sheet 03 under the layer list, sheet 04 beside each figure).
- **Sheet 05 and `face.js`**: every action unit is multiplied by a gain: `f.range`, else `FD.expr_range`, else 1.5 on the sheets and 1 in the film. The module may set `sheet.expression_range` (shared face) or `sheet.expression_gain` (a module that draws its own face). On the sheets the drawer also inks glabella (AU4), cheek crease (AU6), nasolabial folds (AU12/10), marionette lines (AU15), chin dimple (AU17), and the chin drops with the jaw (AU26/27).
- **Per-character head**: `sheet.head_outline(yaw, {jaw, FD}) -> pts | {pts, smooth, k}` (full control), or `sheet.face_shape = {pts, smooth, k, jaw_from}` for the frontal outline, or `sheet.profile` / `FD.profile = {tip_x, mouth_x, mouth_w, eye_x, nose_wing:[[x,y],[x,y],[x,y]], smooth, k, sections:{brow, nose, mouth, jaw, skull}}` (HU from the head centre, facing +x; any missing section falls back to the generic one; or give `outline` for one closed polygon).
- **Accessory hooks**: `face_hooks: {<layer>: fn(g, f, info) | [fn...]}` in `registerCharacter`, called in this layer order: `behind, skin` (head drawer), then `beard, ears, eyes, nose, mouth, details, moustache, spectacles, hair, headwear, front` (face drawer). `info` carries `yaw, side, sgn, nod, au, A(), mode, mask, sheet, u, mouth, mx, my, hw, tip, eyes[], X(p), col(name, grey)` and the bound helpers `fill(pts,col,sm,k)`, `ink(pts,lw,closed,sm,k,dash)`, `hatch(pts,deg,gap,lw)`. Modules no longer wrap `drawFaceFeatures`.
- **Small details**: `FD.details = [{id, layer, anchor: "mouth"|"nose"|"head"|"eye-L"|"eye-R", unit: "hu"|"hw", shape: "poly"|"line"|"dot", pts, r, fill, lw, outline, mirror, views, when:{open_min, au:{"12":[min,max]}}}]`. A chipped tooth is a `poly` in layer `details` anchored on the mouth with `when.open_min`.
- **Sheet 06**: any number of grips: 1-3 in a row, 4-6 as 3x2, 7-8 as 4x2, 9 as 3x3, 10-12 as 4x3, more on extra pages `06b-hands-grips`, `06c-...`. `hand(g, id, {x,y,k,box})` receives the cell box; the note under the page lists handedness from the bible, or `sheet.notes.grips`. `sheet.notes.props` adds a line to sheet 08.
- **Sheet 07**: mouth labels sit in strips below their drawings and never over them; the head is the module's own (`head_outline`, `face_shape`, `profile`), not the generic oval.
- **Angle files** (`<char>/v1/angles/<id>.json`, or `data.angle_dir`) are optional: absent files are listed in `sheets.json` (`module_summary.angle_files`) and the figure's own layer order is printed; `data.angles_required: true` turns a missing file into a clear error naming it; invalid JSON always is. The layer-order key is `data.angle_order_key` (default `hijab_layer_order`, array only).

## Several characters in one shot (2026-10-23, `actors.js`)

A shot with two or more characters (Hero and Partner in the office) uses the multi-actor engine instead of the v5 one-character path (`bootstrap.js` + `trace.js`). The v5 path is unchanged: `mix-v5-repro` still reproduces it (SSIM 0.998 against the reference). Worked example: `work/shots/smoke-partner/` (one actor, same files a two-actor shot has).

**shot.json**: `actors: [{id, module, z, layer, catalogue_url?, catalogue: {model, face, hand_model, grip_dir, grips[], expression_dir, expressions[]}, uses: {refs[]}}]` replaces `character` / `catalogue` / `uses`; optional `draw_order: [{f0, f1, order[]}]` (frame windows). `library`: `core.js, geom2d.js, <world>.js, face.js, hands.js, actors.js, @scene, trace-multi.js, bootstrap-multi.js`. Character modules are NOT listed there: `actors.js` loads them (the build stage still runs `node --check` on each).

**One actor = one instance of a module**: its own id (the key in the trace, the draw order, the interactions and `masks/<kind>/<id>/`), its own evaluation of the module (own `ORDER` layer list, own state), its own face / hand model / grips, `z` (metres from the camera, larger = farther) and `layer`. Two actors may use the same module.

**Why an isolated loader**: two modules as classic scripts collide on top-level names (`SKIN`, `UA`, `drawHead`, `rootScreen`...). `loadCharacterModule` runs each module source in its own function scope. A legacy top-level `let CAT = null, FD = null;` (hero.js) is cut out, because `FD` and `CAT` are the shared slots the actors swap. A new module must not declare `CAT`, `FD`, `HM3` or `GRIPS` (it may read them). The module still ends in `registerCharacter({...})`.

**Scene API** (all in `actors.js`):

| Call | Does |
|---|---|
| `setupActors(SHOT.actors)` (bootstrap does it) | loads module and catalogue data per actor |
| `useActor(id)` / `withActor(id, fn)` | points `CHAR, HUM, FD, HM3, GRIPS, CAT` at one actor (the shared drawers read these); `withActor` restores the previous one |
| `actorGrip(id, gripId, opts?)`, `blendPose` | an actor's grip pose (cached); blends as in hands.js |
| `actorSolve(id, s, R0)` | the actor's body solve for its own pose state `s` |
| `orderAt(f)` | the draw order for frame f: the declared window, else farther first (z), then layer |
| `drawActors(order, per, between?)` | draws `per[id] = {R, cutY, extras, angle, opts}` back to front and returns the calls (`"partner:body"`, `"partner:arms"`...); `between(token)` lets the scene draw a counter edge or a prop between two actors |
| `resetLayerOrders()` | call at the start of every frame: each actor's layer list restarts |

A draw-order token is an actor id (body, then arms) or `id:body` / `id:arms`: `["partner:body", "hero", "partner:arms"]` draws his arms over her. An interleave must be declared in the spec with a why.

**Scene contract** (`bootstrap-multi.js` + `trace-multi.js`): the scene defines `PLAN, SIM, buildSim, renderFrame(f), LAST` and optionally `traceExtra(id, rec, q, L)`. `renderFrame` returns `L = {f, cam, view, actors: {id: {R, s, angle, view, cutY, extras, gaze?, holdPoly?, support_x?}}, draw_calls, props: [{id, pos, parent: {actor, hand} | null, hands: [{actor, hand, gap_px}], touch?}]}`. The pose state `s` per actor is the module's (`flex, tilt, shrug, headTilt, hands: {L: {local, pose, contact?}, R}, face`) plus `neck: {rot, flex, tilt}`, `headYaw`, `viseme?`, which the generic tracer reads. `rootOf(id)` belongs to the scene: `P(mod.root.X, mod.root.Y, actor.z)`.

**Trace** (`trace-multi.js`): `characters[<id>]` carries joints, per-finger `hand_pose`, face, seams, `contact_points.hand_L/hand_R` (the touching point of each hand), `anchors.wrist_*`, `layer_order`, `shadow_mask` / `line_mask` (`masks/shadow/<id>/NNNN.png`). `scene.frames[]` carries `present`, `draw_order` (the draw calls as run), `depth` per actor and the props with the hand each is parented to. The module may give `torso_half_width_hu`, `seams_shoulder: false` and `seam_overlaps: {wrist_L: "why", ...}`; the scene can add anything through `traceExtra` (attachment anchors, overlaps).

**What a module must offer for this**: `root {X, Y}`, `z`, `sides`, `rest_lengths_hu`, `proportions_hu.neck_len`, and from `solve()`: `R.arm[side] = {S, E, W, Sc, T, contact, map, hl, pose, elev, elbow, wflex, wdev, bendSide, sd}`, `R.lift`, `R.chest`, `R.HC`, optionally `R.NB, R.NT, R.mouth`. Partner and Hero both do.

## Lip sync: the viseme track (voice stage)

A voiced line has a track at `work/voice/<episode>/visemes/<line-id>.json` (format `viseme-track/1`, schema `kb/quality/viseme-track.schema.json`), written offline by `uv run tools/voice.py visemes <episode>`: the audio envelope finds the voiced stretches, the line's Arabic letters (with tashkeel) are mapped through the character's own `face.json` viseme `letters` (latest catalogue version) and spread over the voiced time only, consonants held 2 frames minimum, vowels carrying the jaw. No model is called. The shot reads it with `visemeTrackAt(track, t)` from `tools/render/face.js` and assigns the result to the actor's `s.viseme` (`{id, w}`, the same shape the drawer already takes); `t` is shot time minus the line's start in the shot. It returns `null` outside the track, so the scene's own mouth (expression visemes) takes over. The track is approximate by design (the audio is not aligned word by word): the owner judges sync by eye.
