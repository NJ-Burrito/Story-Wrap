# RCA F1 (and F5, F7, F8 body parts): why limbs left human range, and the gates that would have stopped it

Source of the complaint: `bible/feedback/2026-10-23-mix-v2.md` (F1 on v1, F5 fingers/needle/hijab, F7 shoulders, F8 shadow from the illustration). Rules that fix it: `bible/craft/biomechanics.md` (R-300 to R-319). Grades: M = measured, S = source read, J = judgement.

Measurement tool (read-only port of the Mix v2 arm rig, runs on the real keyframes): `work/rca/biomech/rig_audit.js`, output `work/rca/biomech/rig_audit.json` (216 frames x 2 arms). Frames: `work/rca/biomech/sheet.png` (frames 0, 84, 191, 205 cropped from `work/demo-v2/mix-v2.mp4`).

## 1. Root cause (2 lines)
The arm is not a skeleton, it is a 2-bone IK solver fed by free-floating hand targets: `ik()` (`previews/index.html:711`) has no joint limits, no reach check (it silently clamps the wrist, so the hand can miss its target), and no bend-side memory (the bend is a number lerped from -1 to +1, which passes through a fully folded arm). Nothing stopped it because the gates (`tools/quality_gate.py`) measure motion, light and depth and spec completeness, and the shot spec has no field for joint limits, bone lengths, proportions or targets, so `quality_gate.py spec` PASSED a figure whose elbow folded to 175 degrees.

## 2. Evidence

### 2.1 v1 (`previews/style.html`)
- No limb lengths exist. The arm is `shoulder (sx,sy)` to `hand (hx,hy)` with the elbow at the midpoint plus a constant (`style.html:344-351`: `ex = (sx+hx)/2 + side*3 ...`). The hand position is lerped between three poses (`hx = lerp(hx, ..., sw)`, `lerp(..., a)`); the segment lengths follow the distance, so the arm stretches and shrinks freely and a lerp between two valid poses passes through impossible ones. Shoulders are at `lean ± 8` and `shY + 4`, driven by the same scalars as the whole figure (RC1 in `root-causes.md`), so they never lift with the arm. This is the "arm movement went out of human range" the owner saw [S, J].

### 2.2 Mix v2 (`previews/index.html`, Hero, 16-part rig)
All numbers M, from `rig_audit.js`; elbow flexion is 0 straight, 150 = anatomical maximum.

| Finding | Where | Frames and numbers |
|---|---|---|
| Elbow folds to the anatomical limit and past it | arm B (screen right), `bendB = lerp(-1, 1, sstep(7.75, 8.15, t))` at `index.html:737`, solved by `ik(...)` at `:803`/`:930` | Flexion 85 (f185) then 132 (f189), **175 degrees at f191 (t = 7.958 s)**, then 136 (f193). Human max 150. Frames over 145: f190-192. |
| The elbow flips side through the straight fold | same | `elbow_side` goes -1 to +1 at **f191**: the elbow reverses its bend direction in one frame (a hyperextension-through-a-fold). `sheet.png` frame 3 (f191) shows the forearm lying across the chest. |
| Wrist target inside the shoulder joint | arm B flinch keys `[3.5, [.1, -.42], "out"]` at `:734`, shoulder at (.15, -.38) at `:745` | Wrist-to-shoulder distance 0.025 m at f83-f84 (t = 3.46-3.50), against a limb of 0.45 m: elbow flexion **174 degrees** at f84, and the upper arm at 115 degrees. Arm A also reaches 150 at f83 (distance 0.116). `sheet.png` frame 2 (f84): arm A and B both folded into the chest, sleeves read as pipes. |
| Hand never reaches the jar it "holds" | arm B at rest, target `A.JR = toLocal(jar + (.09, -.09))` | Target is 0.474 to 0.501 m from the shoulder; reach is 0.45 m. **Wrist misses its target by 0.025-0.052 m on frames 0-64** (65 frames, 2.7 s); `ik()` clamps `d` to `a + b - 1e-3` and nobody is told. The same unclamped target is used by the hand pose (grip) so the hand is drawn 3 to 5 cm off the object. This is F5 ("fingers do not connect"). `sheet.png` frame 1 (f0). |
| No scapula, no clavicle, shoulder fixed | `const sh = [[-.15, -.38], [.15, -.38]]` at `index.html:745`, rotated by the torso tilt `p.ta` only | Shoulder point never moves with the arm (arm elevation reaches 105 to 115 degrees at f11 and f84, the shoulder does not lift). The same fixed point is where the arm capsule starts, and the arm is drawn in a second pass (`:951`, `drawHero(... {armA, armB})`) after the counter, so the sleeve begins at x = +-0.15 which is 0.08 m INSIDE the coat edge (+-0.23). The sleeve emerges from the middle of the chest: F7 ("shoulders come from a strange place in the middle"). |
| Proportions wrong | head `ellipse(0, -.15, .15, .17)` at `:769` (head height .34, hijab .37) on a neck pivot at -.44; shoulder y = -.38 | Shoulder width 0.30 = **0.9 head heights** (humans: about 2). Head centre at -.59, so the chin (-.39) sits on the shoulder line (-.38): there is no neck. |
| Cloth, hand and tool do not connect | hijab is a head-shaped ellipse + band (`:769-771`), hands are an ellipse + a second ellipse (`:810-811`), the pen is two `line()` calls (`:812`) | Hand has no fingers or grip points; the pen is drawn in hand space with a fixed offset, not attached at a grip point; the hijab has no pins and no body under it, so anything "under the hijab" (neck, chin, hair) is separate shapes at fixed offsets: F5. |
| Shadow from the picture | shadow pass `:932-939` redraws `drawHero(... SHADOW = true)` scaled and projected | The shadow is a projection of the 2D silhouette (head ellipse + coat + sleeves), not of a mass proxy; where the 2D shapes have gaps (no neck) the shadow has holes: F8. |
| Segment lengths | `ik(sx, sy, tx, ty, .23, .22, bend)` at `:803` | Upper arm 0.23, forearm 0.22 (ratio 1.05; human 1.27), hand 0.09. They are constants (so lengths do not drift in v2, a real improvement on v1), but they are not tied to any profile. |

### 2.3 Why nothing stopped it
1. **The spec has no body mechanics.** `kb/quality/shot-spec.schema.json` `characters[].parts[]` has name, pivot, follows, lag_frames, own_curve only. There is no joint limit, no bone length, no proportions, no hand target, no profile. `work/demo-v2/mix-v2.checks.md` records `quality_gate.py spec` PASS before drawing and `render` PASS after: both are blind to anatomy. The render metrics (`motion_coverage`, `independent_share`, `luma_range`, `parallax_corr`...) are about motion and light, and `independent_share` and `motion_coverage` are even helped by wild limb motion [J].
2. **The rig is code, and the keyframes are targets in screen space.** Targets (`A.JT`, `A.JR`, `A.TAG`, `[.1,-.42]` ...) are positions in torso-local metres chosen by eye. An IK solver always returns some pose, so nothing fails; the error shows up only as a bad elbow in the output (fold, flip, detached hand).
3. **The reviewer had only the render gate.** Per `mix-v2.checks.md`, "Iterations: 2 recordings", both aimed at luma and contrast numbers. The repo's run-once rule means nobody looked at a frame sheet of the arm beats.
4. **No profile, so no yardstick.** Without a declared character mechanics there is nothing to be consistent with: the "rubber vs human" question cannot be asked.

## 3. Gate proposals (exact changes; not applied)

Two layers, as in `gate-spec.md`: a SPEC gate (before drawing, cheap) and a RIG gate (after the rig runs, before the final render). The rig gate needs a trace file the previews already can produce: add to `renderAt(t)` a `rigTrace(t)` that records per frame the solved joints. The IK code already computes everything needed (`j.ex, j.ey, j.wx, j.wy, j.dd, bend`).

### 3.1 Schema diff: `kb/quality/shot-spec.schema.json`

```diff
   "required": [
     "episode",
     "fps",
     "characters",
     "beats"
   ],
@@ characters[].items.required
-        "required": [
-          "id",
-          "parts"
-        ],
+        "required": [
+          "id",
+          "parts",
+          "physics_profile"
+        ],
@@ characters[].items.properties  (add next to "id")
+          "physics_profile": {
+            "type": "string",
+            "description": "Id of bible/physics/<id>.json (R-300). Default human profile is '_human-default'."
+          },
+          "rest_proportions": {
+            "type": "object",
+            "description": "Measured from the rest-pose rig (R-307). Checked against the profile's bands.",
+            "required": ["head_h", "shoulder_w", "neck_len", "upper_arm", "forearm", "hand", "thigh", "shank"],
+            "properties": {
+              "head_h": {"type": "number"}, "shoulder_w": {"type": "number"}, "neck_len": {"type": "number"},
+              "upper_arm": {"type": "number"}, "forearm": {"type": "number"}, "hand": {"type": "number"},
+              "thigh": {"type": "number"}, "shank": {"type": "number"}
+            }
+          },
@@ parts[].items.properties  (add next to "own_curve")
+                "joint": {
+                  "type": "string",
+                  "description": "Profile joint id this part rotates about (e.g. 'elbow_flex'). Enables the limit check (R-301)."
+                },
+                "hand_grip": {
+                  "type": "string",
+                  "description": "For hand parts: id of the held object's grip_point (R-310)."
+                }
@@ beats[].items.required  -> add "poses"
+          "poses": {
+            "type": "array",
+            "minItems": 1,
+            "description": "One entry per character pose used in the beat (R-318).",
+            "items": {
+              "type": "object",
+              "required": ["character", "pose_id"],
+              "properties": {
+                "character": {"type": "string"},
+                "pose_id": {"type": "string", "description": "Catalogue id in bible/catalog/<character>/ or a new one."},
+                "new": {"type": "boolean", "description": "True = not in the catalogue yet: needs build_up_sheet (R-306)."},
+                "build_up_sheet": {"type": "string", "description": "Path of the shapes-first sheet for a new pose."},
+                "contacts": {
+                  "type": "array",
+                  "description": "Declared hand/tool contacts (R-304, R-310, R-311): the rig gate checks the miss distance on these frames.",
+                  "items": {
+                    "type": "object",
+                    "required": ["part", "target", "t0", "t1"],
+                    "properties": {
+                      "part": {"type": "string"}, "target": {"type": "string"},
+                      "t0": {"type": "number"}, "t1": {"type": "number"},
+                      "kind": {"enum": ["grip", "touch", "tool-tip"]}
+                    }
+                  }
+                },
+                "exceed": {
+                  "type": "array",
+                  "description": "Declared soft-limit exceedance windows (R-301): max 4 frames each.",
+                  "items": {"type": "object", "required": ["joint", "t0", "t1", "reason"],
+                           "properties": {"joint": {"type": "string"}, "t0": {"type": "number"}, "t1": {"type": "number"}, "reason": {"enum": ["impact", "comedy"]}}}
+                },
+                "stretch_events": {
+                  "type": "array",
+                  "description": "Windows where a stretch profile is active (R-303, R-319).",
+                  "items": {"type": "object", "required": ["segment", "t0", "t1", "max_scale"],
+                           "properties": {"segment": {"type": "string"}, "t0": {"type": "number"}, "t1": {"type": "number"}, "max_scale": {"type": "number"}}}
+                }
+              }
+            }
+          },
@@ beats[].cast_shadows.items.properties
+              "proxy": {"enum": ["mass-proxy", "silhouette"], "description": "Characters must use 'mass-proxy' (R-317)."}
@@ top level properties: add props
+    "props": {
+      "type": "array",
+      "items": {"type": "object", "required": ["id", "physics_profile"],
+                "properties": {"id": {"type": "string"}, "physics_profile": {"type": "string"}, "mass_class": {"enum": ["feather", "light", "medium", "heavy", "immovable"]}}}
+    }
```

New schema file `kb/quality/physics-profile.schema.json` validates `bible/physics/*.json` (required: id, kind, and for `kind = character`: limits_deg with `soft` and `hard` pairs where `hard` encloses `soft`, proportions, mass_class; `extends` resolves; `overrides` only names existing keys).

### 3.2 Spec gate additions: `tools/quality_gate.py::check_spec` (after the parts loop)

Checks the spec only; each returns a "FAIL ..." string as the existing checks do.

| # | Check | Fail when |
|---|---|---|
| S1 | profile resolves | `physics_profile` missing, or `bible/physics/<id>.json` not found or invalid (R-300). |
| S2 | rest proportions | `shoulder_w / head_h` outside the profile's `shoulder_width_heads`; `neck_len / head_h` < `neck_length_heads` x 0.7; `upper_arm / forearm` outside `upper_arm_to_forearm`; `forearm / hand` outside `forearm_to_hand` (R-307). For Hero: 0.30 / 0.34 = 0.88 fails against 1.8 to 2.1 (a stylised profile that wants 1.4 minimum would also fail). |
| S3 | every pose has a source | `poses[]` missing for a beat; `new: true` with no `build_up_sheet` file; `new` absent and `pose_id` not in the catalogue (R-306, R-318). |
| S4 | contacts exist for every held item | A part with `hand_grip` has no `contacts[]` entry (R-310/R-311). |
| S5 | exemptions are scoped | profile `overrides` contains a key not in the base profile; a `stretch_event` has `max_scale` above the profile's `stretch.segments[segment]`; a stretch_event while the profile's `stretch.max_scale` is 1.0 (R-303, R-319). |
| S6 | shadows from mass | any `cast_shadows[].caster` that is a character without `proxy = "mass-proxy"` (R-317). |
| S7 | props have a mass class | a prop with no `physics_profile` or `mass_class` (R-300, R-315). |

### 3.3 Rig gate: new subcommand `uv run tools/quality_gate.py rig <rig-trace.json> <shot-spec.json>`

Input: `rig-trace.json` from the previews: per frame, per character, per joint: `{angle_deg, elbow_side, wrist:[x,y], target:[x,y]|null, seg_len:{...}, com:[x,y], support:[x0,x1]}`. Output: PASS or a list of `FAIL frame f, joint j, value v, limit l`. Run on the trace BEFORE the final render (the rig can be run headless at no GPU cost), and again on every render.

| # | Check | Rule | Threshold | Would have caught (M) |
|---|---|---|---|---|
| G1 | **Joint angle within soft limits** (hard limit always) | R-301 | `soft` else a declared `exceed` window of <= 4 frames | Arm B elbow 175 (f191), 174 (f84), arm A 150 (f83): 6 frames over the 145 soft limit; f190-192 over the 150 hard limit. |
| G2 | **Hinge sign** | R-302 | elbow/knee side sign changes only while angle < 10 degrees, and not at all without a declared flip | The f191 flip. |
| G3 | **Bone length constant** | R-303 | segment length within 1% of rest, unless inside a `stretch_event` | Passes Mix v2 (lengths are constants); would fail v1 (`style.html:344-351`). |
| G4 | **Contact miss** | R-304, R-310 | on frames of a `contacts[]` entry: `|wrist - target|` <= 0.02 x (upper arm + forearm); also the same for the grip point of the object | Arm B jar grip: miss 0.025-0.052 m = 5.6% to 11.6% of limb length on f0-f64; fails. |
| G5 | **Reach ratio** | R-305 | `|target - shoulder| / (upper arm + forearm)` between 0.35 and 0.99 | f83-f84: 0.025/0.45 = 0.06 fails; jar target 1.05 to 1.11 fails (beyond reach). |
| G6 | **Shoulder rides the arm** | R-308 | for arm elevation > 30 degrees, shoulder offset must increase with elevation (correlation > 0.7, offset >= 0.08 head heights at 120 degrees) | Fails: shoulder fixed at `(+-.15, -.38)`. |
| G7 | **Hand-tool tip** | R-311 | tool length constant (1%); tip within 0.02 x limb length of `work_point` on contact frames | New check for the needle and pen. |
| G8 | **Centre of mass over support** | R-314 | COM x within `support` +- margin on each frame | New. |
| G9 | **Lag order** | R-309 | peak times shoulder <= upper arm <= forearm <= hand, each 1-2 frames apart | New; v1 and v2 both use the same scalar for the whole body. |
| G10 | **Soft shape area** | R-316 | soft object area within 5% between frames; rigid exactly constant | Bag squash `ctx.scale(1 + sq*.7, 1 - sq)` at `index.html:1086` is 0.7 vs 1, not volume-preserving: width x height changes up to 15%: fails unless a stretch is declared. |

The rig trace is cheap to produce (216 frames, no pixels). The numbers in G1-G6 reproduce with `work/rca/biomech/rig_audit.js`; it is the proof of concept for the gate.

### 3.4 Review additions (not machine-checkable; frame sheet)
A reviewer opens one cropped frame sheet per contact beat: hand over object, needle through cloth, hijab edge around face, neck visible, shoulders on the torso edge, shadow without holes. Mix v2's `mix-v2.checks.md` has no such sheet; the template adds a "Body and contact" section with the 7 crops (R-306, R-310 to R-312, R-317). Per the project run-once rule, this is the single review, not a retry loop.

### 3.5 Engineering fixes (what to change in the rig, not in the gates)
1. Replace `ik(...)` with a limit-aware solver: clamp the elbow angle to the profile, keep the bend sign fixed, and when the target is out of reach return `reachable: false` so the caller moves the root or shoulder (R-304). Never lerp the bend sign; lerp the target and let the solver pick the pose.
2. Make the shoulder a joint: `sh = clavicleBase + shoulder_lift(armElevation)` (R-308), placed at the torso silhouette edge below a visible neck (R-307), with neck length and shoulder width from the profile.
3. Give the hand grip points and a closed-finger pose family; attach pen, needle and tag to those grip points (R-310, R-311).
4. Build the shadow from a mass proxy projected from the key light (R-317).
5. Tools in `previews/index.html` stay read-only for this task; the fixes belong to the next sketching/animating work item.

## 4. What this cannot see (honest limits)
- The port in `rig_audit.js` approximates `toLocal()` with the camera at each frame and ignores the 12 fps stepping of beat 2 (`tS`); angles could differ by a few degrees on stepped frames. The 175 and 174 degree values come from analytic IK and are not sensitive to that.
- Joint limits come from textbook values [K]; ranges vary 5 to 20 degrees between published tables. Re-verify against the AAOS table before the gate is calibrated. Stylised characters (a small clerk in an oversized coat) may legitimately choose different proportions; the profile makes that a declared choice rather than an accident.
- The gates cannot judge appeal: a pose can be inside every limit and still look stiff (the "pipe arm" sleeves in `sheet.png`). That is the reviewer's call and the build-up step (R-306).
