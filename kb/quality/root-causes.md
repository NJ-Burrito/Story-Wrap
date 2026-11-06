# Root causes of "slideshow" animation, and the construction rule that removes each

Trigger (owner, 2026-10-22, hard rule in CLAUDE.md): across Claude's animation work, light and depth are weak and things move "like a slideshow". Missing: light, shadow, depth, background layers, layers inside the character, objects acting on each other.

Evidence sources: `previews/style.html` (line numbers below), an external motion rules book, the four reels (`research/10-reels-hojas.md`), and the measurements in `gate-spec.md` [M]. Grades follow `kb/README.md`: M = measured by us, S = source read, J = judgement.

Measured gap in one line [M, gate-spec.md]: the two liked reels change 69-71% of 16 px blocks per step and 74-77% of those blocks move differently from the global camera fit; `previews/style.html` option A changes 18% and 18%, option B 41% and 18%. The two 2/10 baselines sit at 16-21% coverage and 20-43% independent motion.

## RC1. Whole-character transforms: the figure is one rigid sprite driven by one clock

Mechanism. The character is a function of four scalars, `{c, L, a, sw}` plus two sines (`pose(t)`, `previews/style.html:303-310`). Every limb, the coat and the head read the SAME scalars (`drawChar`, lines ~314-380: `lean = c*7 - tuck*.2`, `hipY = -40 + c*13 - L`, arms `lerp(.., sw)` and `lerp(.., a)`). All parts therefore start and stop on the same frame, with the same ease. There is no per-part offset, so nothing drags, overlaps or settles after the body. The only independent parts are the scarf and hair tail, driven by a sine of time (`Math.sin(ph - i*.95)`, a loop, not a response to the motion). The whole figure is also re-rendered from scratch each step (`d.char.innerHTML = drawChar(...)`, line 449), so there is no persistent part with its own state or momentum.

Why it happens. A pose function of global parameters is the cheapest way to write a figure in code. A request that says "a character that jumps" is satisfied by it. Nothing in the brief asked for parts.

Construction rule (R-201, R-202). The character is a rig of at least 8 named parts (head, torso, pelvis, 2 upper arms, 2 forearms, 2 thighs, 2 shins, plus hair and cloth). Each part has a pivot and its own keyframed curve. Secondary parts name a parent they follow and a lag of 2 or more frames (hair 3, scarf 4, forearm 2). A key action has at least 3 frames of anticipation, then overshoot, then settle.

## RC2. One global light that never changes and casts no real shadow

Mechanism. Light is two screen-space overlays on top of the finished picture: `.bloom` (a radial gradient, line 50, with only an opacity "breathe") and `.vignette` (line 51). They sit ABOVE every layer, so they lighten and darken the picture but never hit an object differently from another. Consequences: nothing is lit on one side and dark on the other; the moon (a key light) and the neon sign (a second light) change no surface. The "rim light" is the same character redrawn in one fixed colour `#ffe2b0` at a fixed offset `(1.8, -1.6)` (`RIM`, line 312; `.rim` group line 272; filled at line 453) in every pose, whether the body faces the moon or not. The shadow is one black ellipse under the feet that changes only with jump height (line 271 and the update at line 455). Nothing casts a shadow onto a wall or a prop. The ink style also fills with flat colour, so there is no form shading at all.

The sibling repo shows the same habit: `MOTION.md` lists light as helper calls (`light.cast`, `light.rim`) but the plan files that drive a build (`videos/agent-sees-H/shot-plan.json`, keys: category, duration_s, fps, canvas, style, palette, preset, hold, beats, hit_s, identity) have no light field at all, only a palette. A palette is colours, not light.

Measured [M]: option A luma range 0.74 and local contrast 0.067, against 0.87-0.88 and 0.105-0.115 on the liked reels; both baselines (the flat dark reels) are also low (0.79, 0.05-0.07).

Construction rule (R-203, R-204). Every beat names a key, a fill and a rim, each with direction and colour, and a source object (moon, neon, window). The light CHANGES between beats with the story (time, mood, an event such as a flash). Every beat lists at least one cast shadow on a non-ground receiver. Shading is baked into the layers (two-tone cel shade plus a rim colour taken from the key), never a screen overlay. Overlays are allowed only as a final grade.

## RC3. Background as one flat plate per layer

Mechanism. The world is six SVG plates (`sky, clouds, far, mid, roof, fg`, line 400). Each plate is moved by the same camera scalar `p` with a factor: `scale(1 + p*.085*f)` and a translate (lines 435-437). That is one affine transform per plate, all derived from one clock. It is the textbook two-and-a-half-D "parallax" and it looks like cards sliding on rails. Inside a plate, nothing moves: the 20-odd lit windows are placed once from a seeded random (`rng(9)`, line 250) and never change; the buildings are static; the water tower, the sign and the stars are static (only the neon flickers, line 442, and the clouds drift linearly at 6 px/s, line 440). The parallax factors .15, .3, .4, .65, 1, 1.6 are fine in count but their steps (.15, .10, .25) include one gap below 0.12, and the camera move is a slow cosine over 12 s (a gentle drift, 7 px at most), so the layers' relative movement is under a pixel per frame.

Depth measured [M]: the Depth Anything V2 Small map of option A is well spread (5.1 bands) but motion does not follow depth: correlation of depth and motion magnitude is -0.37 (near layers move less than far ones in what moved), against +0.44 and +0.25 on the liked reels. Option B has only 3.1 bands and -0.04.

Construction rule (R-205, R-206). A beat has at least 5 depth planes with at least 4 distinct parallax factors, gaps of 0.12 or more, straddling 1.0 (background below, foreground above). The camera makes a real move (a push, a track or a pan) of at least 4% of the frame width during the beat. Each plane that is not far sky carries its own motion (wind, lights, traffic, people), so a plane is a layer of things, not a picture. Foreground gets blur or darkness plus a shadow onto the subject plane.

## RC4. Tween-only easing: no holds with life, no anticipation, no secondary motion

Mechanism. Every move is `ease` (smoothstep) between keys (`ease`, line 193; `pose` uses `ease(k)` and quadratic `(1-(1-k)^2)` only). One curve family means every move reads as a mechanical fade between poses. The jump has a 0.6 s crouch (good), but arms and legs do not anticipate separately, nothing overshoots, the landing has no squash on the clothes, and after the landing the figure returns to the same idle sines. The "on twos" control then steps the WHOLE drawing at 12/s (`tc = floor(t*24/step)*step/24`, line 429), which makes the problem worse: a global stepped rate turns the entire shot into a slideshow in the literal sense. Spider-Verse steps the body, the jacket and the guitar at different rates (`kb/guides/animation.md`); we stepped everything together.

The sibling repo has the opposite failure and reached it through a metric: the only motion gate in the LinkedIn repo is the share of still frames (`scripts/motion_metrics.py`, "still_frames 0-5 %"). The council itself records the result: "The still-frame gate rewards filler" (`council-2026-10-16.md`, "Metric lesson"). A slow camera drift or a pulsing ring makes every frame differ, so a shot passes while looking like a slide.

Construction rule (R-207, R-208). Each part animates on its own curve; allowed easing includes overshoot, back and spring families, not only smoothstep. Anticipation is 3 or more frames, overshoot and settle are written down for key actions. A mixed frame rate is assigned per PART or per layer, not per shot. A hold is allowed only as a declared event (max 0.8 s, with a reason), and during a hold the idle life of other parts continues unless the hold is an impact freeze.

## RC5. No contact: objects never act on each other

Mechanism. In `style.html` the only object-to-object effect is landing dust, spawned once at 4.3 s (lines 457-460). The neon sign flickers (line 442) but lights nothing; the beam sweeps (line 441) and touches nothing; the scarf reacts to a sine wind, not to the leap; the roof, the sign and the character never occlude or displace one another. In `agent-sees-H` (`index.html:190-250`) objects are mounted from a kit and pressed (`objects.press`), which is one object reacting to a click, and the shot plan lists beats and holds only, with no cause/effect list. An animation where each element moves on its own track, with no coupling, looks like layers sliding, which is a slideshow even at 60 fps.

Construction rule (R-209). Every beat lists at least 1 interaction (and 1 per 3 s) as cause -> effect -> kind (contact, displace, occlude, light-spill, cast-shadow, wind, dust, grab, reflect). The effect object has its own keyframes timed to the cause (impact frame +1 to +3). Checked in the shot spec before rendering.

## RC6. The brief never asked: the spec has no field for light, layers, parts or contact

Mechanism. A creative brief becomes a timeline of poses and a palette. In the sibling repo the shot plan has `palette`, `preset`, `hold`, `beats` and `identity`; in `previews/style.html` the "spec" is the prose on the cards (they say "light and depth make it premium" but nothing makes an agent produce them). What a spec does not ask for, a coding agent does not build, because the cheapest program that satisfies the words wins. The pipeline then offers no point where a missing layer is noticed.

Construction rule (R-210). The shot spec (`kb/quality/shot-spec.schema.json`) has required fields for depth planes with parallax, character parts with pivots and lags, key/fill/rim light, cast shadows, interactions and A/B treatment per beat. `tools/quality_gate.py spec` refuses a spec that lacks them, before any art or render is paid for.

## RC7. Constraints removed the expensive parts and nobody put them back

Mechanism. The LinkedIn motion standard retired depth on purpose: "Depth (deprecated for posts) ... T3 failed at 40.4 MB ... Posts use a locked camera" (`MOTION.md:99`, `council-2026-10-16.md` "Drop: the orbit and dolly, bokeh, vignette"). The cause was a 256-colour, 40 MB GIF with no dither, in which gradients, blur and a moving camera blow up the file and the palette. The fix removed depth (and light gradients) instead of changing the medium. The Story-Wrap target is a 1080x1920 H.264 reel with NVENC (`R-113`), where the file-size limit that caused the retirement does not apply. Habits learned under the GIF constraint (locked camera, flat fills, no gradients) were carried over to a medium that has no such limit.

Construction rule (R-213, amended by R-380). Each constraint is tied to its medium in the guide. When the medium changes, the rules that were only constraint workarounds are lifted explicitly: Story-Wrap output is H.264 video, so soft light, gradients, camera moves and depth blur are allowed and expected.

## RC8. Nothing was measured against a reference, so "premium" was a feeling

Mechanism. Neither repo measured motion against a liked example. The liked reels have measurable properties (zero frozen holds, 69-71% block coverage, 13-15 motion groups per step, 74-77% of motion independent of the camera fit, depth-correlated motion, high luminance range) [M]. The slideshow in `style.html` was only found by the owner's eye. A check that rewards one number (still frames) lets other failures through (RC4).

Construction rule (R-212, R-213). The gate in `tools/quality_gate.py` is calibrated on the four reels (both baselines must fail, both inspirations must pass) and is run on every render, and on the SPEC before the render. Thresholds are re-derived when the reel set changes. Nobody calls a render done without a printed PASS.

## What the tool cannot see (honest limits)

- Shadows and contact are only proxied in the render: luminance range and local contrast are necessary, not sufficient, so the SPEC checks (a named shadow receiver, a named interaction) are the real control. A reviewer still opens one frame sheet per beat.
- Depth Anything V2 Small works on photographs; on flat vector art its map is a guess. We calibrated on flat cut-out reels and it separated them, but it is a proxy and may misjudge a very flat style.
- Four reels is a tiny calibration set [J]: the thresholds sit between two groups of two. Treat them as a floor and recalibrate as the library of liked reels grows.
- A slow, deliberate, premium shot (a long calm close-up) can fail the coverage check legitimately. The answer is a declared hold in the spec, not a lower threshold.
