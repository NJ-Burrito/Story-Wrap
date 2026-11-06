# RCA: hands, writing and paper in Mix v4 (F13, F14, F15)

Date 2026-10-23. Evidence: `work/demo-v4/mix-v4.mp4` (24 fps, 216 frames, 1080x1920), renderer `work/demo-v4/src/{main,hero,trace}.js`, trace `work/demo-v4/rig-trace.json`, catalogue `catalogue/characters/hero/v1/hands/*.json` and `v2/poses/write-tag.json`. Contact sheets and crops: `work/rca/hands/` (`sheet_000-066.jpg` writing beat, `sheet_056-100.jpg`, `sheetB_112-134.jpg`, `snap_118_171.jpg`, `full/` and `crop/` hold every frame). Frame numbers are 0-based; `t = f/24`.

Convention: in the code `sd = "L"` is HER left hand and draws on SCREEN RIGHT (`sg = 1`, hero.js:80); `"R"` is her right hand, on screen left. the owner's note F13 says "left hand". The pen hand (her left, screen right) shows the held-object faults; the screen-left hand (her right) shows the snaps. Both are explained, because a viewer reading "left" off the screen sees the second one. Which one he meant is not known; both are fixed by the same checks.

## F13: the hand glitches

Measured state: the trace reports `finger_mcp/pip/dip_L` = 66/78/42 for all 216 frames (trace.js:15 takes the MAX over the four fingers, and the little finger of `tripod-pen-L` always wins) and `forearm_L` = 110 px for all frames. The numbers the gates see are constant while the drawn hand is not. This is the first reason every gate passed.

### F13-a. Discrete switches inside a continuous blend (the snaps)
Mechanism: `gripBlend` (hero.js:36-41) blends all numbers linearly but sets the thumb mode with a hard flag, `out.pinch = /pinch/.test(k > .5 ? b : a)` (hero.js:40). In `handLocal` the `pinch` flag triggers a search over -60..40 deg for the thumb direction that puts the thumb tip nearest the index pad, so the thumb jumps to a new bone direction on the frame k crosses .5. Separately the IK target is the hand's `contact` point chosen by `contactLocal(hl, kind)` (hero.js:61-66): `kind` is a string set per time window in main.js:103-109 and the offsets differ (`heel` = [.08, 0], palm = [.26, 0], `pinch` = midpoint of index and thumb pads, about [.74, .1]). When `kind` changes, the wrist is re-solved to a different point in ONE frame, because the target `local` is continuous but the hand-to-contact offset is not.
Frames and crops:
- f117 to f118 (kind `palm` to `heel`, t = 4.9, main.js:105 `kind: k > .5 ? "heel" : "palm"`): the hand drops from across the belly (f116, f117 in `snap_118_171.jpg`, top row) to out of frame under the bag handle in a single frame. The contact offset changes by 0.18 HU = 18 body px, times the camera scale (about 2 to 4x in b3).
- f170 to f171 (`kind: t < 7.1 ? "heel" : "pinch"` and grip `flat-support-L` to `pinch-tag-R`, main.js:109): the screen-left hand turns about 45 deg and the wrist moves tens of px in one frame (rows 3 and 4 of `snap_118_171.jpg`: diagonal hand at f169 and f170, hanging vertical hand at f171). The pinch flag flips at t = 7.05 (f169) and the contact kind at 7.1 (f170 to f171): two separate pops one frame apart.
- f74 to f75 (pinch flag on the way to `startle-open-R`, main.js:104): same mechanism; it hides behind the impact frame f72 and the smear frame f75, which is why nobody saw it.

### F13-b. A catalogue hand authored for the other hand
`flat-support-L` (`catalogue/characters/hero/v1/hands/flat-support-L.json`, `"hand": "L"`) is used for the RIGHT hand in b3 and b4 (main.js:105 `grip2: "flat-support-L"`, main.js:109). The code mirrors the thumb side by `rs` (hero.js:77-80), so it draws, but nothing says it is a deliberate mirror and nothing checks it. The L grip's wrist (`flex -40`) is applied with the right hand's sign, which is why the right hand's wrist hangs at about 90 deg in b4 (f171 to f192).

### F13-c. The pen hand is a mitten, not a tripod grip
`tripod-pen-L` runs through `gripBlend`, and `pinch` is false because the id does not contain "pinch" (hero.js:40). The thumb therefore stays in its open rest direction and never meets the pen. The pen is positioned from the INDEX pad (`contactLocal` "pen-tip" = index pad + 0.16 HU along the web direction, hero.js:62-63), not from the catalogue's declared `object_in_hand.grip_point_u_r_n` [0.62, 0.1, 0.1] and `tip_u_r_n` [0.86, 0.04, 0.22]. In the crops (`sheetB_112-134.jpg`, right hand) the four fingers read as one flat block with the pen lying behind it and the thumb absent. The hand also changes apparent scale: it is drawn at the body plane (Z 2.56) while the pen and card are drawn at their own planes (Z 2.40 and 2.396), about 7% nearer the camera.

### F13-d. 3D inverse kinematics drawn as a 2D capsule
`ik3` (hero.js:28-33) solves the arm in 3D with the hand pushed forward by `handDepth` .45 to .85 HU (hero.js:34), and the trace reports the 3D bone lengths (110 px, constant). The drawing uses only the x and y of the elbow and wrist (`armPieces`, hero.js:112-115, `A.E`, `A.W`): a flat projection. The DRAWN forearm therefore shortens as the hand reaches forward, up to a factor `sqrt(1 - (dz/FA)^2)` for a forearm that points straight at the lens (dz .85 gives 63% of its length), and lengthens again when it retracts, while the checked number never moves. That is the 3D-versus-2D mismatch: the checked quantity is 3D, the viewer sees 2D. The forearm visibly breathes between f84 and f132 and at f180. (The drawn lengths were not measured pixel by pixel; the bound follows from the code.)

### Why the gates passed (F13)
- `RIG-SEGLEN` reads `segments_px`, the 3D length (constant 110): it cannot see a foreshortened drawing.
- `RIG-LIMITS` reads the finger joints as the max over the fingers: constant 66/78/42, always in range.
- No check compares hand shape frame to frame (no HAND-TOPO), grip changes (no HAND-SWAP) or handedness (no HAND-SIDE).
- The only hand check, `RIG-CONTACT-GAP`, compares `contact` to `target`; `Cn` in trace.js writes both from the same solved values, so a snapped hand is "in contact" in both frames.

## F14: the writing is on the back of the card

Mechanism: the card is a single flat quad with no sides. The renderer has no concept of which face the writer touches and draws the ink on the face the camera sees.
- Depth: `P(X, Y, Z)` divides by `Z - C.z` (core.js:26), so a larger Z is FARTHER from the camera. Hero is at `Z_S = 2.56` (hero.js:8), the jar at 2.44, the jar tag (the card she writes on) at `JT.c[2] = 2.40` (main.js:71), the pen at `JT.c[2] - .004` (main.js:77), the ink at `JT.c[2] - .001` (main.js:248). She stands behind the counter and the jar; the card hangs on the jar's camera side; her pen is rendered nearer the camera than the card. Physically the nib is on the camera side of the card while the writer is on the far side, so the face she can reach is the one facing her: the BACK, as the audience sees it. The ink is drawn on the camera face anyway (`drawJarTagAt`, main.js:243-249, one stroke path in world coordinates). She writes on the back of the card; the audience watches the writing appear on the front.
- The card has no state for facing, so it never turns. After t = 3.04 it swings (`.5 * ring`, main.js:240) but the ink is replayed from `penPath` in WORLD coordinates (`n` capped at 60 points), not in the card's own coordinates, so ink is not attached to the card; nothing asserts that ink follows the card.
- The bag tag has the same flaw: its two hand-written lines and, in the CU, the name plate are drawn on the front (main.js:288-290, 299-303); in b4 the right hand lifts it by a corner; no face logic says which side she looks at.
Evidence: `sheet_000-066.jpg` (nib at the card, ink appears on the face toward the lens), `sheet_056-100.jpg`.
Why the gates passed: no check knows a prop has two faces; `RIG-LAYERS` and `ATT-LAYERS` compare part orders only; nothing compared the nib's side of the paper with the face carrying ink; the trace had no prop, nib or ink data.
Caveat: the physical reading (writer behind the card) follows from the Z values and the staging text of `v2/poses/write-tag.json` ("pen tip on the hanging jar tag"). It was not confirmed by the owner that this is what he saw; the alternative reading, that he saw the thick grey edge on the card's lower right as a back sheet, has the same cure (faces modelled, edge drawn as thickness only).

## F15: right hand, pen and paper layered and aligned illogically

Mechanism 1, layer order is a draw-order accident. `drawHeroArms` (hero.js:204-224) fills both whole hands, and only afterwards draws every `held` object (`jar-tag`, `bag-tag`, `pen`; main.js:205-207) over them, repainting only the INDEX finger of the holding hand over the object. So the card is drawn above the right hand's thumb, palm and other fingers, and the pen above the left palm, middle and ring fingers and thumb. The catalogue says the pen "crosses UNDER the index pad, lies on the side of the middle finger's last joint, rests in the web" and a tag corner is "pinched between the thumb pad and the side of the index pad": a specific order per camera angle, none of it encoded (`held[]` carries `sd`, `part`, `region` only). Evidence: `sheet_000-066.jpg` CU row (the card covers the left hand's fingertips, the pen hand's thumb is not visible), `sheetB_112-134.jpg`.
Mechanism 2, nothing fixes the nib to the paper. The pen tip is derived from the index pad (hero.js:62-63); the card is placed from its own world position; they are tied only through the IK target `H.L.local = loc(penPath)` (main.js:96-99), a screen-plane projection (`toLocal`, hero.js:16) of a point at Z 2.396 onto the body plane at Z 2.56, solved with the 3D arm (F13-d). The IK residual `miss` is neither checked nor clamped, and the pen offset from the index pad is not part of the target, so the drawn nib is not at the target: it floats above or sinks into the card.
Mechanism 3, the pen is "held" only by overdraw: thumb, index and middle are not constrained to the pen axis (F13-c).
Why the gates passed: `RIG-LAYERS` compares a fixed `layer_order` list to the spec's attachment declaration and the trace exports one list for the whole clip; `RIG-CONTACT-GAP` compares two copies of the same point; there was no nib or digit data.

## Missing checks, summarised
| Gap | New check |
|---|---|
| Hand shape and topology never compared across frames; max-over-fingers hides changes | `HAND-TOPO` |
| Grip, contact-kind and pinch switches unblended | `HAND-SWAP` |
| Grip authored for the other hand | `HAND-SIDE` |
| No face model for two-sided props; ink on the wrong face | `PROP-FACE` |
| Ink not tied to the nib; wrong direction | `WRITE-REVEAL` |
| Nib not on the paper | `NIB-CONTACT` |
| Hand/pen/paper order and digit contact not declared per grip | `LAYER-GRIP` |

## What the renderer must export (rig-trace.schema.json)
Per frame: `hand_pose.{L,R}` (`id`, `mirrored`, `contact_kind`, `pinch`, `blend{to_id,to_kind,k}`, `topo`, `fingers` joint angles per finger, `orient_deg`, `wrist_px`, `holding`, `grip_layers`, `grip_contacts`); `props[]` (`id`, `faces`, `facing`, `marks[]` with `face`, `kind`, `drawn`); `writing` (`prop`, `active`, `direction`, `nib_face`, `nib_px`, `paper_px`, `nib_gap_px`, `on_paper`, `drawn_to_px`, `ink_len_px`); `cut` on the first frame of a shot and `smear` on an intended smear. Also: stop reporting the max over fingers as the finger series, and report the DRAWN (projected) forearm length beside the 3D one.

## Fixes for Mix v5 (renderer work, not done here)
1. Choose the writing staging first (R-388): she lifts the card toward her and turns it to the lens as she finishes, or the camera sits on her side; the nib is always on the face the viewer sees while the ink grows.
2. Ink as a card-local polyline revealed by arc length; the nib is its moving end; the card carries it.
3. Grip library with digit contacts and a layer order per camera angle; blend every discrete switch; drive `pinch` with a continuous weight.
4. Draw the forearm at the 2D length the pose implies, and pick poses so 3D and 2D lengths agree.
