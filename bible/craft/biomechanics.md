# Biomechanics and mechanics: rules for bodies and objects (R-300 to R-319)

Trigger (owner, 2026-10-23, notes F1, F5, F7, F8): "arm movement went out of human range"; hand, needle and hijab did not connect; shoulders "come from a strange place"; the shadow was not her mass. Instruction: set rules, research biomechanics and mechanics, apply the same to objects, and let each character or object keep the mechanics set for it (a rubber hero stays rubber where it applies and human elsewhere, consistently).
Root cause with frames and gate proposals: `kb/quality/rca-biomechanics.md`. Evidence grades: S = source read this session, K = textbook value from memory, to be re-checked against the primary source before it is hard-coded as a gate, M = measured by us (`work/rca/biomech/rig_audit.js`), J = judgement.

## 1. Research distilled

### 1.1 Human joint range of motion (degrees, active, adult)
Primary table: AAOS "Joint Motion: Method of Measuring and Recording" (1965, reprinted in the AMA Guides). Reproduced in secondary tables: https://www.sncc.ca/resources/Documents/Dragon%20Boat/2024%20CCWCs/range%20of%20motion%20normal%20values.pdf , https://pmc.ncbi.nlm.nih.gov/articles/PMC9218764/table/T1 , https://pmc.ncbi.nlm.nih.gov/articles/PMC3685163/table/T0001 , https://actaorthop.org/actao/article/download/28654/33535/82106 . The sources disagree by 5 to 20 degrees (elbow flexion 140 to 150; hip flexion 100 to 130; knee flexion 135 to 150) [S], so the profile has two limits: a soft limit (comfortable, used as the gate) and a hard limit (the upper end of the published range, never exceeded). VERIFIED 2026-10-23 [S] against: the AAOS-based table in the supplement of Hendriks et al., Plast Reconstr Surg Glob Open 2020 (https://cdn-links.lww.com/permalink/prsgo/b/prsgo_8_6_2020_04_17_hendriks_gox-d-20-00155r2_sdc1.pdf : neck 45/45/60/45, shoulder flexion 180, extension 60, abduction 180, elbow flexion 150, wrist flexion 80, extension 70, hip flexion 120, knee flexion 135, ankle plantar 50, dorsi 20; fingers there are Richard and Parry medians: MCP 80, PIP 90, DIP 65), the Enlyte clinical chart (https://www.enlyte.com/insights/article/adjuster/understanding-normal-range-motion-joint-functionality : shoulder IR/ER 90/90, elbow 145, wrist radial 20, ulnar 30, hip abduction 45, adduction 30, extension 30, IR 40, ER 45, knee 135, ankle 20/50), WikEM (https://wikem.org/wiki/Joint_ROM_(Table) : forearm 80/80), and the cervical measurement study (https://avesis.iku.edu.tr/yayin/e6a38307-12a9-4526-9d9f-efa478dba5e1/normative-values-for-cervical-and-lumbar-range-of-motion-in-healthy-young-adults : young adults measured flexion 57.7, extension 59.1, lateral 42, rotation 71). Thoracolumbar values: AAOS-based sheets give flexion 80, extension 20 to 30, lateral 35, rotation 35 to 45 (https://www.scribd.com/document/585002577/AAOS-ROM-VALUES, secondary). The PMC table PMC9218764 and the original AAOS book could not be opened (bot check, no free copy); no value below is read from the 1965 primary text. CORRECTIONS made by this check: finger MCP/PIP/DIP were 90/110/80 and are now 80/90/65 (soft) with 90/100/85 hard; hip adduction minimum -10 was wrong (adduction is 30); neck soft limits now follow AAOS 45/45/60/45 with the measured adult values as the hard limit; knee hard limit is 150 because tables range 135 to 150; trunk rotation soft 35. Values still carried at 5 to 20 degrees of disagreement between sources are marked (range) in the table.

| Joint (movement) | Min | Max | Soft limit in the default profile |
|---|---|---|---|
| Shoulder flexion / extension (arm forward / back) | -60 | 180 | -45 .. 170 |
| Shoulder abduction / adduction (arm sideways) | -30 | 180 | -20 .. 170 |
| Shoulder internal / external rotation (IR 70 to 90) (range) | -70 | 90 | -60 .. 80 |
| Elbow flexion (0 = straight) | -5 (hyper) | 150 | 0 .. 145 |
| Forearm pronation / supination | -80 | 80 | -75 .. 75 |
| Wrist flexion / extension | -80 | 70 | -70 .. 60 |
| Wrist radial / ulnar deviation | -20 | 30 | -15 .. 25 |
| Finger knuckle (MCP) flexion (AAOS-based 80; Kapandji about 90) (range) | 0 | 90 | 0 .. 80 |
| Finger PIP flexion (90 to 100) (range) | 0 | 100 | 0 .. 90 |
| Finger DIP flexion (65 to 85) (range) | 0 | 85 | 0 .. 65 |
| Neck flexion / extension (AAOS 45/45; measured 58/59) | -60 | 60 | -45 .. 45 |
| Neck rotation (each side) (AAOS 60; measured 70) | -75 | 75 | -60 .. 60 |
| Neck lateral tilt (each side) | -45 | 45 | -40 .. 40 |
| Trunk flexion (forward) / extension (back) | -30 | 80 | -25 .. 70 |
| Trunk rotation (each side) (35 to 45) (range) | -45 | 45 | -35 .. 35 |
| Hip flexion / extension | -30 | 120 | -20 .. 110 |
| Hip abduction (+) / adduction (-) | -30 | 45 | -20 .. 40 |
| Hip rotation (internal 40, external 45) | -40 | 45 | -40 .. 40 |
| Knee flexion (never negative; tables 135 to 150) (range) | 0 | 150 | 0 .. 135 |
| Ankle dorsiflexion / plantar flexion | -20 | 50 | -18 .. 45 |

Joint types that matter for a 2D rig: elbow and knee are hinges (one direction only; the forearm and shin never fold forward); the shoulder, hip and wrist are multi-axis; fingers are chains of hinges that flex together (DIP follows PIP at about 2/3).

### 1.2 How joints chain
- **Shoulder girdle.** The arm does not rotate from a point in the chest. The collarbone (clavicle) is a strut from the breastbone to the shoulder point; the shoulder blade (scapula) slides on the ribs. Over a full lift, shoulder-joint (glenohumeral) to shoulder-blade motion is about 2:1 (120 + 60 degrees; measured 2.1:1 abduction, 2.4:1 flexion, 2.2:1 scapular plane; Inman 1944; later work questions the exact number) and the first ~30 degrees are almost all glenohumeral. The shoulder point therefore rises and moves forward as the arm goes up. Sources [S]: https://e3rehab.com/?p=437 , https://dsc.duq.edu/faculty/928 , https://pmc.ncbi.nlm.nih.gov/articles/PMC2841046 , https://ouhsc.edu/bserdac/dthompso/web/namics/scapryme.htm . Clavicle motion in the middle phase (about 40 degrees at the sternoclavicular and 20 at the acromioclavicular joint) is from a slide deck: approximate.
- **Gate model of the shoulder point (2026-10-23).** `RIG-SHOULDER` allows the shoulder point to rise with humeral elevation: nothing above 30 degrees, then 0.1 head per 60 degrees (2:1 rhythm = the girdle carries one degree in three; the slope is judgement, calibrated on Mix v5), moving inward along the clavicle arc, so an arm may rise to 180 degrees with no pose-lift cap; a shoulder that stays down or sits in the chest fails.
- **Proportions** (fraction of standing height; Drillis and Contini 1966, Winter, de Leva 1996 https://ebm.ufabc.edu.br/wp-content/uploads/2013/12/Leva-1996.pdf ) [K]: upper arm 0.186, forearm 0.146, hand 0.108, thigh 0.245, shank 0.246, shoulder width (biacromial) 0.259, head height about 0.13, so the shoulders are about 2 head heights wide; the neck is visible (about 0.3 head height). Forearm = 0.78 of upper arm. The elbow sits at the waist line, the fingertips reach mid-thigh.
- **Segment mass** (de Leva, fraction of body mass) [K; thigh row confirmed at https://pmc.ncbi.nlm.nih.gov/articles/PMC9602786/table/healthcare-10-02054-t005 ]: head and neck 0.07, trunk 0.43 to 0.49, upper arm 0.027, forearm 0.016, hand 0.006, thigh 0.14, shank 0.045, foot 0.014. The whole-body centre of mass sits near the navel (about 55% of height).
- **Balance.** A figure is stable while the vertical from its centre of mass falls inside the support polygon (feet; seated at a counter: seat plus feet). Reaching moves the mass; the body counterweights (hips back, other arm out).
- **Weight and momentum.** A heavy thing starts and stops slowly, needs longer ease-in, overshoot and settle, and the body shows the load (shoulder drops, knees bend, the other arm counterbalances). A light thing starts and stops at once. No part changes direction instantly without a cause (a contact frame).
- **Squash and stretch keeps volume** constant: stretch thin, squash wide (SIGGRAPH education https://education.siggraph.hosting.acm.org/static/HyperGraph/animation/character_animation/principles/squash_and_stretch.htm ; Stretch-Engine rule set derived from Looney Tunes https://diglib.eg.org/handle/10.1145/3099564-3106639 ) [S]. A stretchy CG rig does not keep volume unless it is built to (scaled joints or corrective shapes) [S, search summary].

### 1.3 Objects
- **Rigid** (jar, key, pen, needle, bell): no deformation; position, rotation and contact impulses only. A bounce needs a declared restitution. Pen, needle and key keep their length in every frame.
- **Hinged** (lid, door, drawer, flap): one axis, angle limits like a joint (a lid opens 0 to 110 degrees, never through the box).
- **Soft body** (leather bag, cushion, dough): deforms on contact and recovers; volume-preserving squash along the contact normal, damped over 3 to 6 oscillations or fewer. A bag landing squashes about 10 to 25% and rebounds.
- **Cloth** (hijab, coat, scarf, tag): attached at pins; its motion is the pin's motion, delayed, plus a damped swing; it never stretches (hem and seam lengths are constant), it folds instead. It cannot pass through the body it covers and it drapes over the shoulder form, so where cloth meets a limb the cloth has a start point on a named part.
- **Rope, thread, chain:** constant-length links under gravity; taut = straight line between two pins, slack = hanging curve; its ends move only with the parts they are tied to.
- **Paper and tags:** a stiff plane that rotates about its string knot, flutters with wind and curls rather than stretches.
- **Liquid:** takes the container's shape; its surface stays level (perpendicular to gravity) and lags the container's tilt with a damped slosh.
- **Mass and inertia:** every object declares a mass class (feather, light, medium, heavy, immovable). In a collision the lighter body changes velocity more; the heavier one barely reacts. The Disney principles apply: anticipation, follow-through and overlapping action, slow in and out, arcs (free limbs travel on arcs, not straight lines) [J, standard].

### 1.4 Character physics profiles (the idea added here)
Each character and each prop has a physics profile: a declared list of its own mechanics, compared with the default human profile. Reference pattern [J; rig numbers of these productions could not be retrieved this session]: *Spider-Man: Into the Spider-Verse* gives each Spider-Person their own movement vocabulary and frame rate and holds to it (see `kb/guides/animation.md`); *The Incredibles* gives Elastigirl a stretch that is bounded and keeps volume while the rest of the cast stays human; Luffy in *One Piece* stretches only when he uses the power, bounces and snaps back, while his skeleton logic, joint directions, balance and body proportions stay human. A creator-made rig tutorial for a Spider-Verse style rig (bendy limbs, stretchy head) gives no numbers either (https://www.therookies.co/projects/80775). What is portable is the contract: (1) say which parts are exempt from human limits and by how much, (2) say what is preserved (volume, joint order, hinge direction), (3) say when the exemption is active (a story event), (4) check it on every frame. A rubber hero's forearm may stretch to 3x at a punch, but the elbow still bends one way, the shoulder still sits on the torso, and the stretched arm keeps constant volume.

## 2. Rules

Each rule: statement, then how it is checked. "Rig gate" = machine check on the per-frame rig trace; "Spec gate" = machine check on the shot spec before drawing; "Review" = the frame-sheet reviewer. All gates are proposed in `kb/quality/rca-biomechanics.md`.

| ID | Rule | Checked by |
|---|---|---|
| R-300 | **Every character and every moving prop has a physics profile** (section 3). The shot spec names it per character and prop. None named = default human profile for a character, `rigid` for a prop. | Spec gate: `physics_profile` required; unknown id fails. |
| R-301 | **Every keyframed or solved joint angle stays inside the profile's limits.** Soft limits may be passed only inside a declared `exceed` window (max 4 frames, impact or comedy only). Hard limits are never passed. | Rig gate: per frame, per joint, angle against `limits_deg`; the failure lists frame, joint, value. |
| R-302 | **Hinge joints bend one way.** Elbow, knee, finger joints keep the sign of their bend; the elbow never flips side between two frames (Mix v2 did at 7.96 s). | Rig gate: elbow-side sign constant unless a declared flip. |
| R-303 | **Bone lengths are constant** (tolerance 1%) unless the profile gives `stretch.max_scale` for that segment AND the beat declares a `stretch_event`. When stretched, volume is kept: width scales by 1/sqrt(length scale). | Rig gate: segment length against rest length; width check. |
| R-304 | **An unreachable target is never fixed by silently clamping.** If a hand target (jar, tag, pen, needle) is farther than upper arm plus forearm, move the body (lean, shoulder, root) or the target. During a declared contact the wrist or grip point lands on the target within 2% of limb length. | Rig gate: `miss` per contact frame. |
| R-305 | **No target inside the joint:** a hand target closer than 0.35 x (upper arm + forearm) to its own shoulder is refused (the elbow would fold past 150 degrees). | Rig gate: minimum reach ratio. |
| R-306 | **Build bit by bit, shapes first**, for a new character or a new pose only: block with primitives (head ellipse, neck, clavicle line, rib cage, pelvis, limb capsules at bone lengths), check proportions and balance, sketch the character onto them, then set angles. Known poses come from the catalogue (R-318). | Spec gate: each beat's `pose_id` has `built_up: true` and a `build-up/` sheet path if `new: true`. |
| R-307 | **The shoulder joint sits at the outer edge of the torso, below a visible neck, about 2 head heights between the two shoulders** (`proportions.shoulder_width_heads`, default 1.8 to 2.1; a stylised profile may set 1.4 to 2.4 and says why). The arm is drawn from the shoulder, never from the chest. | Spec gate: rest-pose proportions inside the band; Review: rest pose sheet. |
| R-308 | **The shoulder rides the arm** (scapulohumeral rhythm): above 30 degrees of elevation the shoulder point rises about 0.1 head height per 60 degrees of elevation and moves forward; the clavicle follows. In 2D this is a `shoulder_lift` curve, derived from the arm angle or keyed, never a fixed point. | Rig gate: shoulder offset correlates with arm elevation above 30 degrees; a fixed shoulder with the arm over 120 degrees fails. |
| R-309 | **Joint chains move in order and overlap** (root, hip, spine, shoulder, upper arm, forearm, hand, fingers, 1 to 2 frames each; extends R-201). The lag applies to the targets; the solved IK pose is what is drawn. | Spec gate: `lag_frames`; rig gate: peak-time order. |
| R-310 | **Hand and fingers:** palm, thumb and four fingers (or a mitten with declared grip points); finger joints bend inward only and flex together; a held object has a `grip_point` in the palm and the hand closes to the object's width; the hand never floats off the held object (gap 0) and never overlaps its outline by more than 2% of its size. | Rig gate: grip distance per frame; Review: crop sheet per contact beat. |
| R-311 | **Held tools are rigid and attach at a grip point.** A needle, pen or key keeps its length; its working tip is a constraint on the work point (cloth, paper, lock), not a drawing. | Rig gate: tool length constant; tip within tolerance of `work_point` in contact frames. |
| R-312 | **Cloth over body (hijab, scarf, coat):** the cloth has pin points on named parts (nape, shoulders, collar) over a body form. Layer order from the inside: body form, garment layers outward, then held props. Nothing under a garment (neck, hair, chin) pokes through it. Where a needle or a finger meets cloth, the spec says which layer is over and which under, once. | Spec gate: `layers` order; Review: crop check. |
| R-313 | **Cloth and cord lengths are constant:** thread, string, tag strings and hems never stretch; they swing, fold or go slack. | Rig gate: link length drift under 2%. |
| R-314 | **Balance:** in every frame the centre of mass is over the support polygon within a margin; a lean beyond the margin shows a counterweight or a step. | Rig gate: COM against support box (uses mass fractions). |
| R-315 | **Weight and momentum:** each prop has a mass class; the class sets ease length and overshoot (feather 0.1 s, light 0.15, medium 0.25, heavy 0.4, immovable never moves); in a collision the lighter body gets the larger velocity change; heavy things get at least 3 frames of anticipation and 4 of settle. | Spec gate: `mass_class`; rig gate: ease length against class. |
| R-316 | **Squash and stretch keep volume;** soft bodies deform along the contact normal, rigid bodies never deform. | Gate: soft shape area within 5% between frames (stretch events excepted); rigid shape area constant. |
| R-317 | **Shadows come from the mass, not from the picture:** a character's cast shadow is projected from a 3D mass proxy (head sphere, neck cylinder, torso box or capsule, limb capsules at the same bone lengths), never from the 2D illustration; hollow gradients and holes (the neck) are then impossible. A contact shadow sits under each support. | Spec gate: `cast_shadows[].proxy = "mass-proxy"` for characters; Review: shadow frame has no holes. |
| R-318 | **Catalogue per character, prop and environment:** an approved pose, camera angle, expression or body language is recorded in `catalogue/characters/<id>/` (`pose_id`, joint angles, camera, notes) and reused first; build-up (R-306) is for new entries only. | Spec gate: every `pose_id` resolves to a catalogue entry or is `new: true`. |
| R-319 | **Exemptions are declared, scoped and consistent** (rubber, ghost, robot, cloth-bodied): a profile overrides only keys it names; everything else stays human; the exemption holds in every shot of every episode, and its trigger (`active_when`) is a story event. | Spec gate: `overrides` only on keys that exist; Review: continuity across episodes. |

## 3. The physics profile format

One JSON file per character or object in `bible/physics/<id>.json`, validated by `kb/quality/physics-profile.schema.json` (proposed in the RCA doc). Angles in degrees, 0 = neutral standing pose. `soft` is the comfortable range, `hard` is never exceeded. `extends` inherits a profile; `overrides` changes only the keys it lists.

### 3.1 Default human profile (`bible/physics/_human-default.json`)

```json
{
  "id": "_human-default",
  "kind": "character",
  "material": "flesh",
  "mass_class": "medium",
  "mass_fractions": {"head_neck": 0.07, "trunk": 0.46, "upper_arm": 0.027, "forearm": 0.016, "hand": 0.006, "thigh": 0.14, "shank": 0.045, "foot": 0.014},
  "proportions": {
    "height_heads": 7.5,
    "shoulder_width_heads": [1.8, 2.1],
    "neck_length_heads": 0.3,
    "upper_arm_to_forearm": [1.1, 1.4],
    "forearm_to_hand": [1.2, 1.5],
    "thigh_to_shank": [0.95, 1.05]
  },
  "bone_lengths_tolerance_pct": 1,
  "stretch": {"max_scale": 1.0},
  "squash": {"max_volume_change_pct": 0},
  "limits_deg": {
    "shoulder_flex": {"soft": [-45, 170], "hard": [-60, 180]},
    "shoulder_abd":  {"soft": [-20, 170], "hard": [-30, 180]},
    "shoulder_rot":  {"soft": [-60, 80],  "hard": [-70, 90]},
    "elbow_flex":    {"soft": [0, 145],   "hard": [-5, 150], "hinge": true},
    "forearm_rot":   {"soft": [-75, 75],  "hard": [-80, 80]},
    "wrist_flex":    {"soft": [-70, 60],  "hard": [-80, 70]},
    "wrist_dev":     {"soft": [-15, 25],  "hard": [-20, 30]},
    "finger_mcp":    {"soft": [0, 80],    "hard": [0, 90], "hinge": true},
    "finger_pip":    {"soft": [0, 90],    "hard": [0, 100],  "hinge": true},
    "finger_dip":    {"soft": [0, 65],    "hard": [0, 85],   "hinge": true},
    "neck_flex":     {"soft": [-45, 45],  "hard": [-60, 60]},
    "neck_rot":      {"soft": [-60, 60],  "hard": [-75, 75]},
    "neck_tilt":     {"soft": [-40, 40],  "hard": [-45, 45]},
    "trunk_flex":    {"soft": [-25, 70],  "hard": [-30, 80]},
    "trunk_rot":     {"soft": [-35, 35],  "hard": [-45, 45]},
    "hip_flex":      {"soft": [-20, 110], "hard": [-30, 120]},
    "hip_abd":       {"soft": [-20, 40],  "hard": [-30, 45]},
    "hip_rot":       {"soft": [-40, 40],  "hard": [-40, 45]},
    "knee_flex":     {"soft": [0, 135],   "hard": [0, 150],  "hinge": true},
    "ankle_flex":    {"soft": [-18, 45],  "hard": [-20, 50]}
  },
  "shoulder_girdle": {"rhythm_ratio": 2.0, "free_arm_deg": 30, "lift_heads_per_60deg": 0.1},
  "balance": {"support": "feet", "com_margin_pct": 10},
  "exceed": {"max_frames": 4, "allowed_for": ["impact", "comedy"]}
}
```

### 3.2 Example rubber hero (`bible/physics/example-rubber-hero.json`)

Rubber limbs and neck; human skeleton logic, proportions, balance and joints elsewhere.

```json
{
  "id": "example-rubber-hero",
  "kind": "character",
  "extends": "_human-default",
  "material": "rubber",
  "mass_class": "light",
  "overrides": {
    "stretch": {
      "max_scale": 3.0,
      "segments": {"upper_arm": 3.0, "forearm": 3.0, "hand": 1.0, "thigh": 2.0, "shank": 2.0, "neck": 2.5, "torso": 1.0, "head": 1.0},
      "volume_preserving": true,
      "recovery": {"ease": "back", "frames": 6, "overshoot_pct": 12},
      "active_when": "beat lists a stretch_event"
    },
    "squash": {"max_volume_change_pct": 25, "parts": ["torso", "head"]},
    "limits_deg": {
      "shoulder_flex": {"soft": [-90, 200], "hard": [-120, 240]},
      "shoulder_abd":  {"soft": [-60, 200], "hard": [-90, 240]}
    }
  },
  "keeps_human": ["torso proportions", "head size", "elbow and knee hinge direction", "finger joints", "balance R-314", "shoulder position R-307"],
  "note": "When the power is not in use the character measures, moves and balances exactly like the default human."
}
```

### 3.3 Example object profiles (`bible/physics/example-objects.json`)

```json
[
  {"id": "needle", "kind": "object", "material": "steel", "mass_class": "feather", "rigid": true, "length_m": 0.09, "grip_point": [0.015, 0], "work_point": "tip"},
  {"id": "hijab", "kind": "object", "material": "cloth", "mass_class": "light",
   "pins": ["nape", "chin-edge", "shoulder-L", "shoulder-R"], "length_drift_pct": 2,
   "swing": {"damping": 0.35, "lag_frames": 4}, "collides_with": ["head", "neck", "shoulders"], "layer": "above-body-below-props"},
  {"id": "leather-bag", "kind": "object", "material": "leather-soft", "mass_class": "medium",
   "squash": {"max_volume_change_pct": 25, "recover_oscillations": 3, "axis": "contact-normal"}},
  {"id": "string-tag", "kind": "object", "material": "cord+paper", "mass_class": "feather",
   "link_length_drift_pct": 2, "hinge_deg": [-80, 80]},
  {"id": "jar", "kind": "object", "material": "glass", "mass_class": "light", "rigid": true, "restitution": 0.1,
   "contents": {"type": "liquid", "level": "horizontal", "slosh_lag_frames": 3}}
]
```

## 4. Order of work for a new pose (R-306)
1. Choose or create the profile and the `pose_id` (catalogue lookup first, R-318).
2. Block with shapes at rest proportions. Check R-307 proportions and R-314 balance on the blocked figure.
3. Set joint angles inside the profile. Run the rig gate (R-301 to R-305). Fix numbers before drawing.
4. Sketch the character onto the shapes (face, hair, hijab, coat over the form; R-312 layer order).
5. Build the mass proxy for the shadow (R-317). Save the approved pose to the catalogue (R-318).
