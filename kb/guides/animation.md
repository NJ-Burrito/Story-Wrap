# Animation: four-level ladder and the AI-assisted route

Source: `research/02`, `research/10`. Definitions of the principles are from secondary summaries; check Thomas and Johnston before quoting [S]. Rules: R-090 to R-099.

## 0. Mechanics

- Twelve principles (Thomas and Johnston, 1981): squash and stretch, anticipation, staging, straight-ahead and pose-to-pose, follow-through and overlapping action, slow in and slow out, arcs, secondary action, timing, exaggeration, solid drawing, appeal [S https://en.wikipedia.org/wiki/Twelve_basic_principles_of_animation]. Follow-through has no sourced definition in our files.
- Spacing and easing: frames bunch at the start and end of a move; linear motion reads as mechanical [S https://blog.cg-wire.com/slow-in-out].
- Ones, twos, threes: on 24 fps film, twos is about 12 drawings a second, threes about 8; fast action goes to ones [S https://en.wikipedia.org/wiki/Frame_rate].
- Limited animation: cuts inbetweens, reuses layers; sources disagree on cost versus style as the motive [S research/02].

## Level 1: Basics (one character, one emotion, one action)

Squash and stretch with constant volume, anticipation, slow in and out, arcs, staging to one focal point. Pose-to-pose. AI route: one locked master sheet, cut into layers (head, torso, arms, props), animate with 2D transforms and easing; one generation per layer, not per frame [J]. Hard part: model drift, solved by the locked sheet and rig.

Checks: anticipation on every key action or a reason; no linear easing; silhouette on-model first to last frame; one focal point per shot; motion does not depend on sound.

## Level 2: Intermediate (characters that act)

Exaggeration and appeal, secondary action, timing as emotion; keyed viseme mouth shapes rather than flapping; framing for 9:16; text and key subject out of the platform overlay zones (numbers unverified, Q-05). AI route: generate a mouth set once; viseme swap.

## Level 3: Advanced

### Mixed frame rates (Spider-Verse)

- Across the Spider-Verse: Hobie's jacket on 4s, body on 3s, other parts sometimes on 2s, the guitar sometimes on 6s; multiple rigs; a custom tool, StepSets [S https://beforesandafters.com/2023/06/17/the-across-the-spider-verse-spider-punk-character-hobie-was-animated-with-different-frame-rates-fo].
- The film as a whole on twos; "not one frame of motion blur" [S Slashfilm, research/02]. Conflicts: a Sony Imageworks abstract describes a Variable Motion Blur tool [S https://www.fxphd.com/fxblog/spider-verse-at-siggraph/]; an Inverse interview calls 24 fps standard with twos used selectively [S Inverse via research/04]. Treat both as claims; plan selective rates (Q-08).
- Lines drawn in 3D over characters that could accept light or not [S Slashfilm].
- Halftone and offset artefacts used to blur backgrounds and fast elements; the mechanics are unverified [S Kottke].
- Frame-rate modulation exists in anime (ones for a thrown axe, threes for a giant's scale in *Horus*) [S Animation Obsessive].
- Cost: a typical animated film is about a week per four seconds; this one a week per second [S Slashfilm].
- Arcane: 2D effects at 12 fps over 24 fps characters (see `art-styles.md`).

### Premium corporate motion

Easing with reasons (ease-in, ease-out, ease-in-out; linear only for mechanical moves) [S Morphic glossary]. Kinetic type follows the same timing rules as characters: one word lands, holds, leaves; one idea per screen [J]. 2.5D parallax needs real depth layers; foreground, midground and background separation gives the best result [S Morphic]. Sources for this tradition are thin (no School of Motion material retrieved).

### Tools with verified descriptions

DepthFlow (open-source parallax shader, loops) [S https://pypi.org/project/depthflow]; Depth Anything V2 (NeurIPS 2024, arXiv 2406.09414; **only Small is licence-clean for us**) [V]; RIFE (ECCV 2022, authors report 4 to 27 times the speed of SuperSlomo and DAIN on their benchmarks) [S https://arxiv.org/abs/2011.06294].

Checks: each character has a declared rate; interpolation is a per-shot choice; real layer separation; stylised layers tied to story; camera moves motivated by a beat.

Common mistakes: interpolating everything (kills stepped rhythm; on twos duplicate frames); parallax on flat images; motion blur added to a style that has none; accidental mixed rates.

## Level 4: Mastery

Rate change is an event (a character jumps to ones at the moment they decide). Each character has a physical signature that follows from their extreme (R-097). Light and colour are picked per scene, no default palette. Stylised layers appear only on beats. Scene paced to emotion, not a clock. The director keeps the keys: poses, rate changes, camera beats, mouth keys; AI handles layers, backgrounds, depth maps, and inbetweens where the rule allows; every AI output is checked against the style sheet.

Checks: every rate change has a named reason; characters distinguishable with sound off; stylised layers only on beats; the same rules across episodes; the story reads in the first second at phone size.

## Pipeline map [S research/02, J]

| Technique | Level | AI assist | GPU need | Main risk |
|---|---|---|---|---|
| Layered rig, 2D transforms | 1 | Image generation per layer | Low-moderate (estimate) | Model drift |
| Viseme mouth swap | 2 | Mouth set once | Low | Mouth does not match face |
| Parallax move | 2-3 | Depth map | Moderate; measure | Thin or hairy objects |
| RIFE | 3 | Interpolation | Moderate; measure | Destroys stepped rhythm |
| Duplicated-frame holds | 3-4 | None | None | Judder if rates mixed by accident |
| Mixed rates per character | 4 | None, rig-level | Low-moderate | A rig per rate |
| Halftone/offset overlay | 3-4 | Post shader | Low-moderate | Reads as noise |

## From the inspiration reels (research/10)

Motion floor: zero holds of 0.5 s or more. Hook: a moving element within 2 s. The FPS-meter idea (making smoothness the visible subject) is a hook pattern. `rossark-motion-skill` principles (one clock per scene, real pivots, trailing parts follow a beat later, idle motion that never stops, smooth curves through key poses) map onto this stage [S research/10]; adopt the principles, not its mobile templates.

## Gaps

Williams on holds, follow-through definition, primary halftone mechanics, VRAM for depth and interpolation on the 2060 (Q-04, Q-09).
