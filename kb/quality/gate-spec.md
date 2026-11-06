# Gate spec: measurable "never a slideshow" checks

Tool: `tools/quality_gate.py` (PEP 723 script, run with `uv run`). Spec schema: `kb/quality/shot-spec.schema.json`; passing template: `kb/quality/shot-spec.example.json`. Why each check exists: `root-causes.md`. Rules: `kb/rulebook.md` section Q (R-201 to R-214) and the craft sections B, T, C, E (R-300 to R-379). Sections E to I below cover the merged craft checks.

Verdict rule: every gating check must pass. The tool prints each failing check with its value and the threshold, ends with PASS or FAIL, and exits 0 / 1 (2 = tool error).

## A. SPEC checks (shot spec JSON, before any art or render)

Command: `uv run tools/quality_gate.py spec <spec.json>`. Pure JSON, runs in about a second.

| Check | Threshold | Rule |
|---|---|---|
| Character parts | >= 8 per character, each with a pivot | R-201 |
| Parts with their own curve | >= 75% of parts | R-201 |
| Lagged follower parts (`follows` + `lag_frames`) | >= 3 parts with lag >= 2 frames | R-202 |
| Depth planes per beat | >= 5 | R-205 |
| Distinct parallax factors per beat | >= 4, adjacent gap >= 0.12, min < 1.0 < max | R-205 |
| Camera move per beat | >= 4% of frame width, or `locked_camera_because` | R-206 |
| Light roles per beat | key, fill, rim each with `dir` and `color` | R-203 |
| Light changes across the episode | >= 2 distinct light setups | R-203 |
| Cast shadows per beat | >= 1; one on a non-ground receiver (or two shadows) | R-204 |
| Interactions per beat | >= max(1, floor(duration / 3 s)), each cause + effect + kind | R-209 |
| Treatment per beat | A, B or A+B plus a reason | R-210 |
| Action anticipation | >= 3 frames, or a written reason | R-207 |
| Static element | none static > 2.0 s unless declared as a hold | R-208 |
| Holds | each <= 0.8 s with a reason; total <= 10% of runtime | R-208 |

Check on `previews/style.html` option A written up as a spec from its source (`work/quality/style-html.spec.json`): FAIL with 14 findings (no follow-through, 2 of 10 parts with their own curve, parallax gap under 0.12, no fill light, ground shadow only, one interaction in 6 s, zero-frame anticipation on the scarf, four elements static for 6 s, camera move 2.6%). The example template passes.

## B. RENDER checks (output video)

Command: `uv run tools/quality_gate.py render <video.mp4> [--json out.json]`; `--no-depth` skips the depth model.

Method, GPU first. Decode: `ffmpeg -hwaccel cuda -hwaccel_output_format cuda -threads 2 -vf scale_cuda=270:480:format=nv12,hwdownload,format=nv12,fps=15,format=gray` (NVDEC; 270x480 at 15 fps). Motion: a 16 px block matcher in torch on CUDA, search +-6 px at 270 px width with parabola sub-pixel refinement, between consecutive sampled frames. A least-squares similarity transform (translation, scale, rotation) is fitted to the textured blocks; the residual says whether ONE camera-like transform explains the motion. Hard cuts (mean frame difference over 35 of 255) are excluded from motion statistics. Freeze: ffmpeg `freezedetect=n=0.003:d=0.5`, as in `research/10`. Depth: Depth Anything V2 SMALL (`depth-anything/Depth-Anything-V2-Small-hf`, Apache-2.0; Base and Large are CC-BY-NC and are never loaded), fp16 on CUDA, 10 frames sampled from 8% to 89% of the runtime, correlated with block motion over 0.2 s. At most 2 CPU threads (ffmpeg and torch).

| Metric | Gate | Meaning |
|---|---|---|
| `freeze_share_05s` | <= 0.03 (default: v5 = 0, nothing tighter is evident) | share of runtime inside holds of 0.5 s or more (freezedetect) |
| `dead_window_share` | <= 0.05 (default) | share of 0.5 s windows with no change at all |
| `low_motion_window_share` | <= 0.05 (default) | share of 0.5 s windows where under 5% of blocks change: a still with a drift, which freezedetect misses |
| `motion_coverage` | >= 0.50 (calibrated-on-v5; was 0.35) | mean share of blocks that change per step, over moving steps |
| `uniform_share` | <= 0.35 (default: every pass and fail measured is <= 0.14) | slideshow detector: share of moving steps where one global transform explains the motion (residual under 0.20 px, or under 25% of the motion) |
| `independent_share` | >= 0.50 (calibrated-on-v5: v5 0.540, highest fail 0.432) | mean share of textured blocks whose motion differs from the global fit by over 0.5 px: layers, parts and objects moving on their own |
| `luma_range` | >= 0.85 (calibrated-on-v5: lowest pass 0.864, highest fail 0.834; meet it with flat tone steps, not gradients: R-380) | mean (p99 - p1) luminance per frame: real highlights and real darks |
| `local_contrast` | >= 0.085 (calibrated-on-v5; was 0.09, v5 = 0.0921 left 2% margin; highest fail 0.0753) | mean 16 px block luminance std: light that shapes forms |
| `depth_bands` | >= 4.0 (default; v5 4.5, the one fail it separates is 3.1) | occupied bands (of 6, at least 4% each) of the normalised depth map |
| `parallax_corr` | >= 0.10 (calibrated-on-v5; was 0.15, v5 = 0.191; highest fail -0.043) | correlation of depth with motion magnitude on moving blocks: motion that depends on depth. **Estimator (2026-10-24, E01 run 1):** the median over up to 32 frame pairs, evenly spread over the moving ones of 96 candidates (was 10 fixed positions); the threshold did not move. Reported next to it, never gating: `parallax_samples`, `parallax_candidates`, `parallax_valid`, `parallax_corr_p25/p75`, `parallax_ci95` (bootstrap interval of the median), `parallax_conf` (0..1: sample count x agreement), `parallax_marginal` (the interval straddles 0.10: the verdict could flip on another sample set; read the frames before trusting it) |

Advisory (printed, never gating, because they did not separate the reels): `motion_clusters`, `direction_entropy`, `soft_gradient_share` (a ramp detector meant as a shadow/glow proxy; both baselines are dark and full of gradients, so it cannot separate), `depth_std`, `cuts_per_min`.

## C. Calibration on the four reels (and on style.html)

Reels: A `Deu0eKalKi1` and B `DezkWyyANhZ` are the inspirations the owner likes (must pass); base 1 `DeqjQlmv5MA` and base 2 `DepIFCzsTdL` are rated 2/10 (must fail). The style columns are the 6 s loop of `previews/style.html` options A and B, recorded as 180 deterministic frames (`d.time = i/30`, then `render(d)`, element screenshot via Playwright with the stage forced to 1080 px wide, encoded `h264_nvenc` 30 fps): `work/quality/style-A.mp4`, `style-B.mp4`. Bold x marks a failed gate. Raw numbers: `work/quality/<id>.json`.

| Metric | Threshold | A (liked) | B (liked) | base 1 (2/10) | base 2 (2/10) | style.html A | style.html B |
|---|---|---|---|---|---|---|---|
| `freeze_share_05s` | <= 0.03 | 0.0 | 0.0 | 0.173 **x** | 0.5513 **x** | 0.0 | 0.0 |
| `dead_window_share` | <= 0.05 | 0.0 | 0.0 | 0.0179 | 0.0709 **x** | 0.0 | 0.0 |
| `low_motion_window_share` | <= 0.05 | 0.0 | 0.0 | 0.2381 **x** | 0.6325 **x** | 0.0 | 0.0 |
| `motion_coverage` | >= 0.50 | 0.6928 | 0.7131 | 0.2142 **x** | 0.1567 **x** | 0.1823 **x** | 0.4121 |
| `uniform_share` | <= 0.35 | 0.0 | 0.0 | 0.0888 | 0.1374 | 0.0112 | 0.0 |
| `independent_share` | >= 0.50 | 0.7368 | 0.7655 | 0.4316 **x** | 0.195 **x** | 0.1777 **x** | 0.1775 **x** |
| `luma_range` | >= 0.85 | 0.882 | 0.874 | 0.793 **x** | 0.797 **x** | 0.738 **x** | 0.834 **x** |
| `local_contrast` | >= 0.085 | 0.1046 | 0.1152 | 0.0513 **x** | 0.0729 **x** | 0.0667 **x** | 0.0753 **x** |
| `depth_bands` | >= 4.0 | 5.4 | 4.4 | 5.1 | 4.5 | 5.1 | 3.1 **x** |
| `parallax_corr` | >= 0.10 | 0.443 | 0.245 | -0.157 **x** | -0.085 **x** | -0.37 **x** | -0.043 **x** |
| **Verdict** | all pass | PASS | PASS | FAIL | FAIL | FAIL | FAIL |

| Advisory (not gating) | - | A (liked) | B (liked) | base 1 (2/10) | base 2 (2/10) | style.html A | style.html B |
|---|---|---|---|---|---|---|---|
| `motion_clusters` | - | 13.585 | 15.183 | 6.274 | 5.56 | 4.09 | 5.453 |
| `direction_entropy` | - | 0.848 | 0.837 | 0.763 | 0.78 | 0.866 | 0.843 |
| `soft_gradient_share` | - | 0.0921 | 0.0965 | 0.0653 | 0.1098 | 0.0508 | 0.0056 |
| `depth_std` | - | 0.282 | 0.299 | 0.271 | 0.305 | 0.212 | 0.165 |
| `cuts_per_min` | - | 13.4 | 49.2 | 5.3 | 0.0 | 0.0 | 20.0 |
| `duration_s` | - | 22.38 | 23.17 | 78.81 | 178.0 | 6.0 | 6.0 |


Result: both inspirations PASS, both baselines FAIL (base 1 on 7 gates, base 2 on 8), `style.html` option A FAILS on 5 gates and option B on 5. The gates that separate the groups: freeze, low-motion windows, motion coverage, independent motion, luminance range, local contrast and parallax correlation. `uniform_share` and `dead_window_share` did not separate anything on their own; they stay as guards against pure pans and fully dead windows.

Commands that produced the numbers (repo root, `PYTHONUTF8=1`):

```
uv run tools/quality_gate.py render work/reels/Deu0eKalKi1/Deu0eKalKi1.mp4 --quiet --json work/quality/Deu0eKalKi1.json
uv run tools/quality_gate.py render work/reels/DezkWyyANhZ/DezkWyyANhZ.mp4 --quiet --json work/quality/DezkWyyANhZ.json
uv run tools/quality_gate.py render work/reels/DeqjQlmv5MA/DeqjQlmv5MA.mp4 --quiet --json work/quality/DeqjQlmv5MA.json
uv run tools/quality_gate.py render work/reels/DepIFCzsTdL/DepIFCzsTdL.mp4 --quiet --json work/quality/DepIFCzsTdL.json
uv run tools/quality_gate.py render work/quality/style-A.mp4 --quiet --json work/quality/style-A.json
uv run tools/quality_gate.py render work/quality/style-B.mp4 --quiet --json work/quality/style-B.json
uv run tools/quality_gate.py json work/quality/<id>.json      # re-evaluate stored metrics with the current thresholds
```

Run time on the RTX 2060 (includes model load): about 65 s for the 22 s reel, a few minutes for the 178 s reel. Peak VRAM was not logged [unverified]. The freeze numbers equal the earlier R10 probe (17.3% and 55.1%), which cross-checks the decode path.

## D. Limits and use [J]

- Four reels is a small calibration set. Each threshold sits between two groups of two, so margins are thin on some gates (base 1 independent motion 0.43 vs gate 0.50; style B luma range 0.834 vs 0.85). Add more liked and disliked reels to the table; never loosen a gate to let one render through.
- The liked reels are bright cut-out reels with a cut every 2 to 5 s. A deliberately calm, dark premium scene may fail `luma_range` or `motion_coverage`. The fix is a declared hold or a lighting decision in the spec, not a silent threshold change.
- The render gate cannot prove that a shadow or a contact exists. The SPEC gate demands them in writing, and a reviewer opens one contact sheet per beat.
- The depth model is trained on photos; on flat vector art the map is approximate. It separated flat reels here; treat `depth_bands` and `parallax_corr` as proxies.
- Run-once exception: the gate is a deterministic correctness gate and runs every time; it is not a visual second look.

## E. Merged craft checks (R-300..R-379, 2026-10-23): one spec, one trace, one gate

Commands (repo root, `PYTHONUTF8=1`):
```
uv run tools/quality_gate.py spec   <shot-spec.json> [--root .] [--files]     # sections A + F-spec below
uv run tools/quality_gate.py rig    <rig-trace.json> [<shot-spec.json>]       # F-rig; trace format: kb/quality/rig-trace.schema.json
uv run tools/quality_gate.py extras <video.mp4> <shot-spec.json> [--text-mask-dir D] [--shadow-dir D]   # F-render
uv run --no-project --with pytest --with numpy --with pillow --with scipy --with jsonschema pytest tools/tests -q   # 89 tests
```
Every failure prints `FAIL [CHECK-ID] message`. `extras` decodes with NVDEC (`-hwaccel cuda`, `scale_cuda` to 540x960, 8 fps, streamed so memory stays flat), ffmpeg `-threads 2`, analysis in numpy on the CPU (light). Code: `tools/qg_checks.py` (checks), `tools/quality_gate.py` (CLI, decode, motion/depth gates), tests in `tools/tests/`.

### E.1 Conflicts between the four proposals and how they were settled (one name per concept)

| Concept | Proposals | Merged decision |
|---|---|---|
| Shadow source | biomechanics `cast_shadows[].proxy = "mass-proxy"`; construction `source = "mass_proxy"` + `proxy` id + `light` + `contacts` | `cast_shadows[]` requires `source: "mass_proxy"`, `proxy` (volume-set id), `light`; optional `contacts[]`, `self_shadow`. Checks `SHADOW-MASS`, `SHADOW-CONTACT`, `SHADOW-SELF`, `SHADOW-SOFT`; mask holes `RIG-SHADOW-HOLES`. |
| Shadow hole test | biomechanics review only; construction numpy mask test | One function, `shadow_mask_issues`: holes of 4 px or more and more than one piece fail. Used by `rig` (trace `shadow_mask`) and `extras --shadow-dir`. |
| Shoulder | biomechanics R-307 band + R-308 rides the arm; construction R-341 clavicle anchor + R-342 neck | Complementary, kept as three ids: `BIO-PROPORTIONS` (rest proportions incl. neck >= 0.25 head), `RIG-SHOULDER` (R-341: at the torso edge, on the clavicle line, neck length per frame), `RIG-SHOULDER-RIDES` (R-308). Anchor field is `anchors.clavicle_L/R`. |
| Segment length tolerance | R-303 1%; R-344 2% | One value from the profile `bone_lengths_tolerance_pct`, default **2%** (renderer rounding at 1080 px makes 1% fire on noise). `RIG-SEGLEN`. R-303's "1%" text is superseded. |
| Contact vs attachment | biomechanics `poses[].contacts` (timed hand targets); construction `attachments[]` (structure) | Both kept, different jobs. `contacts` = a hand reaches a target in a time window (`BIO-CONTACTS`, `RIG-CONTACT-GAP`, `RIG-REACH`). `attachments` = parent, `parent_anchor`, `contact_points`, `layer_order` per angle, `max_gap_px` (`ATT-*`, `RIG-ATTACH`, `RIG-LAYERS`). |
| Camera by feeling | emotion R-377 put `camera` inside `emotion_track` | Removed from `emotion_track`; the camera lives only in `camera_plan[]` with `serves_emotion` (`CAM-EMOTION`). `camera_move_pct` stays as the beat total. |
| Catalogue reference | biomechanics `pose_id` + `new`; construction `catalogue: "id@version"` | `poses[]` entry: `pose_id`, `catalogue` (`id@version`) or `new: true` + `build_up_sheet` (`POSE-CATALOGUE`); `characters[].model_ref {id, version}`. |
| Text interval | transitions `appear`/`leave` as transition ids | Kept for the art note, plus numeric `t0`/`t1` seconds so the render check and `TEXT-TRANSITION` can work. |
| VFX vs text | emotion R-376 and text R-334 | `vfx[].box` must not meet a text box that is on screen (`EMO-SFXVFX`). |

## F. The checks

Status vocabulary: **calibrated** = a measured sample sets the number (only the section B gates); **source-backed** = the number comes from a cited source, nothing else measured; **default** = judgement [J], not yet calibrated on liked renders. None of the checks below is "calibrated" on the four reels; those carry no body, text or emotion content. Change a default only with a measured sample and a line here.

### F-spec (`spec`)

| Check id | Rule | Fails when | Status |
|---|---|---|---|
| BIO-PROFILE | R-300, R-315 | character `physics_profile` unresolved (built-in `_human-default`, inline `physics_profiles`, or `bible/physics/<id>.json`); prop without profile or mass_class | default |
| BIO-PROPORTIONS | R-307, R-342 | shoulder_w/head_h outside 1.8..2.1 (a wider band needs `stylised_reason`), neck under 0.25 head, upper arm/forearm outside 1.1..1.4, forearm/hand outside 1.2..1.5, or `rest_proportions` missing | default (proportions are memory-grade [K], Drillis-Contini and de Leva) |
| BIO-EXEMPT | R-301, R-303, R-319 | exceed window over 4 frames or not impact/comedy; stretch_event above the profile (a human profile allows none) | default |
| BIO-CONTACTS | R-304, R-310, R-311 | a contact lacks part/target/t0/t1; a `hand_grip` part has no declared contact | default |
| POSE-CATALOGUE | R-306, R-318, R-340, R-346 | beat has no `poses[]`; pose neither `catalogue` (`id@version`) nor `new` + `build_up_sheet` | default |
| ATT-MODEL, ATT-ANCHORS | R-341, R-345 | no `model_ref`; anchors lack clavicle_L/R, neck_base, head_unit_px | default |
| ATT-DECLARED, ATT-LAYERS | R-350, R-351, R-352 | no attachments; one lacks child/parent/parent_anchor/contact_points/layer_order; `max_gap_px` over 6; a `layer_order[angle]` shorter than 2 | default (4 px at 1080 wide is 0.4% of width) |
| ATT-FINGERS | R-353 | a held object with fewer than 3 finger/thumb/palm parts | default |
| ATT-HAIR | R-354 | `covers_hair` and a hair part not `under_garment` | default |
| SHADOW-FLAT | R-380 | a cast shadow has `edge` soft/blur/gaussian or `blur_px` over 2 (absent = hard, passes) | default |
| SHADOW-MASS, SHADOW-CONTACT, SHADOW-SELF, SHADOW-SOFT | R-317, R-355, R-357, R-358, R-359 | shadow lacks source `mass_proxy`, proxy, light; fewer shadow `contacts` than contact/grab interactions; no `self_shadow`; `light.key.size` missing | default |
| TRANS-COUNT, TRANS-FIELDS | R-320 | transitions missing, not n-1, ids not consecutive; entry lacks type/frames/cause/style_entry/rate_change | default |
| TRANS-STYLE | R-321 | treatment changes with `none-same-style`; bleed not 6..12 frames; under-cover without impact-cover/whip-smear and 2+ frames | default (frame counts are ours; no source documents them) |
| TRANS-CAUSE, TRANS-CARRIER, TRANS-RATE, TRANS-AUDIO | R-323, R-324, R-322, R-327 | cause under 8 chars; contour-wipe/carrier-bleed without carrier or edge_follows; ramp `none` outside match-cut/action-cut/impact-cover, or from == to; audio lead outside 4..12 frames without a reason | default |
| CAM-PLAN, CAM-DUR, CAM-VARY, CAM-WHY | R-328, R-330 | no camera_plan, a beat without a shot, missing fields; shot durations not summing to the beat (0.05 s); consecutive shots repeat size and angle without a long why; why under 12 chars | default |
| CAM-SAFE, CAM-FILES, CAM-EMOTION | R-332, R-329, R-377 | safe box outside x 0..960, y 250..1580; thumbnail missing (with `--files`); moving shot not serving the beat's emotion | default (the safe band is from third-party guides, not a Meta spec) |
| TEXT-SPEC, TEXT-LAYER, TEXT-SIZE, TEXT-CONTRAST, TEXT-DWELL, TEXT-SAFE, TEXT-TRANSITION | R-334..R-339 | `texts` absent; layer not `top` or plate missing; height under 36 px (sub 28); min_contrast under 4.5; read_time under 0.6 s + 0.1 s per word or on screen shorter; box outside the band; text on screen during a style entry | source-backed for 4.5:1 / 3:1 (WCAG 1.4.3), default for the rest |
| EMO-DECLARED, EMO-CHANNELS, EMO-ORDER, EMO-GAZE, EMO-BLINK, EMO-HIDDEN | R-360..R-364, R-373, R-374 | primary outside the 14-word vocabulary or no intensity/shown/cause; under 6 channels or under 4 non-face; eyes not first (unless a reflex); no gaze target or darts; blink band outside the emotion's band; hidden without leak or blend not summing to 1 | **default** (all emotion thresholds are judgement) |
| EMO-COLOUR, EMO-CHANGE, EMO-LIGHT, EMO-ENV, EMO-SFXVFX, EMO-PROFILE | R-365, R-369..R-372, R-375, R-376, R-378 | emotion changes with identical colour row; no `emotion_change` (bridge, 6..24 frames; a reflex is exempt); `light.serves_emotion` mismatch; no interaction with `carries_emotion`; vfx over 1 per beat or 3 per 9 s, no sfx at intensity 0.6 or more, vfx over a text; no `emotion_profile` or fewer than 12 face_controls | **default** |

### F-rig (`rig`)

| Check id | Rule | Fails when | Status |
|---|---|---|---|
| RIG-LIMITS | R-301 | joint beyond the hard limit, or beyond the soft limit outside a declared exceed window | source-backed (joint table in `bible/craft/biomechanics.md`, verified 2026-10-23, section G) |
| RIG-HINGE | R-302 | elbow/knee side flips while either frame is over 10 degrees | default (the Mix v2 flip was measured at f191) |
| RIG-SEGLEN | R-303, R-344 | segment length off rest by more than 2% outside a stretch_event | default |
| ART-PROPORTION | CLAUDE.md (owner, 2026-10-25) | drawn hand length and width, finger radius, head height, nose, lips and eye sizes (trace frame `art`, per head height) more than 8% off catalogue/characters/<id>/artbook-proportions.json (derived from the approved art-book sheets by tools/artbook_proportions.py); a trace without `art` or a character without the file is not judged | default |
| RIG-CONTACT-GAP, RIG-REACH | R-304, R-305, R-310 | contact point more than 2% of limb length from its target; reach ratio outside 0.35..0.99 | default (Mix v2 jar miss of 0.025-0.052 m = 5.6-11.6% of limb was measured) |
| RIG-ATTACH, RIG-LAYERS | R-351, R-352 | a contact point over `max_gap_px` from its parent anchor for 2 frames in a row; draw order differs from the declared order | default |
| RIG-SHOULDER | R-341, R-342 | allowed shoulder point is a function of `arm_elevation_deg`: lift = 0.1 head per 60 deg above 30 deg (R-308), y within 0.03 head + 35% of the lift of (rest line - lift) and never above it by more than a 0.2 head shrug, x at least 0.85 of the half width minus the clavicle-arc inward shift L(1 - cos asin(lift/L)), L = half width; neck under 0.25 head. Rest line: character `rest_shoulder_y_px`, else the median of (y + model lift) over the lowest third of elevations. No `arm_elevation_deg`: the old fixed clavicle line (3 px) | onset at 30 deg and the 2:1 glenohumeral:scapular rhythm are source-backed (Inman 1944; `bible/craft/biomechanics.md`); the 0.1 head per 60 deg slope, the 35% tolerance and the 0.2 head shrug cap are judgement (Mix v5 calibration); x test default (Mix v2: x ratio 0.6..0.75 from code) |
| RIG-SHOULDER-RIDES | R-308 | for an arm that spans 40+ degrees above 30: lift correlation under 0.7 or lift under 0.08 head per 90 degrees | source-backed ratio (scapulohumeral rhythm), threshold default |
| RIG-BALANCE | R-314 | centre of mass x outside the support span by more than 10% | default |
| RIG-BLINK | R-364 | blink not 2..5 frames (at 24 fps); beats of 4 s or more outside the declared band (plus or minus one blink); all intervals equal | default (lab values on live people) |
| RIG-EYE-DART, RIG-EYE-INDEP, RIG-EYE-LEAD | R-362, R-363 | no eye dart in a 1 s window of a beat with intensity 0.3 or more; eye/head-yaw correlation over 0.9; eye lead not 2..4 frames when the head moves 5 degrees or more | default |
| RIG-FACE, RIG-PEAK | R-365, R-374 | fewer than 5 face controls move by 0.15; biggest face change more than 3 frames from the declared `peak_s` | default |
| RIG-SHADOW-HOLES | R-356 | a shadow mask with an interior hole of 4 px or more, or more than one piece | default |

### F-render (`extras`)

| Check id | Rule | Fails when | Status |
|---|---|---|---|
| REND-TEXT-CONTRAST | R-336 | 10th percentile of WCAG contrast (glyph mask vs a 6 px ring, or the two-mode fallback without a mask, which is weaker) under 4.5:1 (3:1 at 48 px and up) | source-backed threshold |
| REND-TEXT-TEXTURE | R-335 | luma std of the knockout region (box plus 0.5 cap height, glyphs excluded) over 6/255 | default (the dot grid of Mix v2 should give tens) |
| REND-COLOUR | R-370 | consecutive beats with different emotions whose measured hue (under 30 degrees), saturation or luma (under 20% relative) barely move; measured hue/saturation/value outside a declared `colour.target` by more than 30 degrees / 0.2 | default |

Not built (they need renderer tracks that do not exist yet, so a check would only guess): per-frame style-strength step (R-321), cadence change (R-322), lag-order of peaks (R-309), ease length per mass class (R-315), soft-shape area (R-316), loudness per beat (R-375, only for episodes with sound). They stay in `rca-*.md` as proposals and in `kb/rulebook.md` as "review".

Smoke run, 2026-10-23: `extras work/demo-v2/mix-v2.mp4 work/demo-v2/shot-spec.json` decodes on NVDEC and prints the per-beat colour script (hue 19 to 25, saturation 0.49 to 0.60, luma 0.115 to 0.128 across the four beats); the Mix v2 spec has no texts or emotions, so no render finding is raised there. The spec failures on Mix v2 are the evidence for those checks (section I).

## G. Joint range of motion: what was verified (2026-10-23)

`bible/craft/biomechanics.md` section 1.1 was written from memory. It was checked against an AAOS-based table (Hendriks et al. 2020 supplement), the Enlyte clinical chart, WikEM and a 300-person cervical study; the URLs are in that file. The original AAOS book and the PMC table PMC9218764 could not be opened (bot check), so no value is read from the 1965 primary text. Corrections: finger MCP/PIP/DIP 90/110/80 to 80/90/65 soft (90/100/85 hard), hip adduction minimum -10 to -30, neck to AAOS 45/45/60/45 soft with measured adult values as hard limits, knee hard limit 150, trunk rotation soft 35. Sources disagree by 5 to 20 degrees for elbow, hip, knee, shoulder rotation and fingers; each such row is tagged (range) and the gate uses soft and hard limits for that reason.

## H. Uncalibrated defaults to calibrate first

1. Every emotion number: blink bands per emotion, onset order, channel counts (6 of 9, 4 non-face), vfx rate, colour delta (30 degrees / 20%), eye lead 2..4 frames. Calibrate on liked reels that show clear emotion; none are in the set.
2. Rig tolerances (2% segment, 2% contact, 85% shoulder edge, 10% balance margin): calibrate on the first rig trace of a hand-approved pose.
3. Text texture 6/255 and the fallback two-mode contrast: calibrate on frames from a render the user approves.
4. Transition frame counts (bleed 6..12, cover 2+, audio lead 4..12): ours, no source; rehearse once before series use.
5. Safe band (top 250, bottom 340, right 120 at 1080x1920): third-party guides.

## I. Mix v2 spec as a regression case

`kb/quality/fixtures/mix-v2.shot-spec.json` is an unchanged copy of `work/demo-v2/shot-spec.json`. The old spec checks passed it; the merged checks fail it on: BIO-PROFILE, BIO-PROPORTIONS, POSE-CATALOGUE (4 beats), ATT-MODEL, ATT-ANCHORS, ATT-DECLARED, SHADOW-MASS (11), SHADOW-CONTACT (2), SHADOW-SELF (4), SHADOW-SOFT (4), TRANS-COUNT, CAM-PLAN, TEXT-SPEC (4), EMO-DECLARED (4), EMO-PROFILE (2). `tools/tests/test_spec_checks.py::test_mix_v2_spec_fails_the_new_checks` pins this. Its render and rig faults (elbow 175 degrees at f191, jar miss, shoulders at 0.6 to 0.75 of the coat edge) need a rig trace from the renderer to be caught by `rig`; the trace format is defined, the previews do not write it yet.

## J. 2D look check (R-380, 2026-10-23)

Why: Mix v3 "went 3D" and passed every gate. Nothing measured line art or flat tone, and `luma_range`, `local_contrast`, R-203 (key/fill/rim), R-358 (penumbra grows with light size) and R-317 (shadow from a 3D proxy) all pushed toward lit volume. Root cause and frames: `work/rca/2d/` (`v2-sheet.png`, `v3-sheet.png`).

Command: `uv run tools/quality_gate.py look2d <video.mp4> [--json out.json]`. NVDEC decode (`-hwaccel cuda`, `-threads 2`), 540x960 at 2 fps, numpy.

| Metric | Gate | Meaning |
|---|---|---|
| `hard_edge` (`LOOK2D-LINE`) | >= 0.08 (calibrated-on-v5: v3 0.064 fails, v5 0.1017 / v2 0.0986 pass) | share of pixels with a luma step >= 0.10 to the next pixel: ink line and cel edges |
| `ramp_area` (`LOOK2D-RAMP`) | <= 0.03 (calibrated-on-v5; was 0.04) | share of 24 px blocks that vary by >= 0.10 luma with no hard step inside: smooth lit-volume ramps |

Calibration (Mix v2 must pass, Mix v3 must fail; the thresholds sit between those two, the reels are reported only):

| Video | hard_edge | ramp_area | Verdict |
|---|---|---|---|
| Mix v2 (liked) | 0.0986 | 0.0220 | PASS |
| Mix v3 (went 3D) | 0.0640 | 0.0622 | FAIL (both) |
| reel Deu0eKalKi1 | 0.061 | 0.097 | FAIL (both) |
| reel DezkWyyANhZ | 0.067 | 0.0505 | FAIL (both) |
| reel DeqjQlmv5MA | 0.0267 | 0.0213 | FAIL (line) |
| reel DepIFCzsTdL | 0.0372 | 0.0357 | FAIL (line) |

Limits: two videos set the thresholds, so margins are thin (v2 hard_edge 0.099 vs 0.08). Photographic and cut-out reels fail by design; they are motion references, not style references. Not built: tone-step count per figure region and shadow-edge hardness measured in pixels (the figure mask exists only in the renderer; `SHADOW-FLAT` covers the shadow at spec level). Tried and dropped: global luma-histogram peak count (28.1 v2 vs 26.5 v3, no separation) and 12 px gradient blocks (0.52 vs 0.45 of non-edge blocks).


## K. Seam lines and preview playback (R-381, R-382, 2026-10-23)

Both are DEFAULT, uncalibrated thresholds: no hand-approved line-art mask or preview run exists yet. Tests: `tools/tests/test_seam_playback.py` (one passing and one failing synthetic fixture per check).

### K.1 SEAM (`rig`, R-381, the owner F11)

Why: Mix v3 drew outlines that separated elbow from arm, shoulder from body, fingers from hand and a round head from a square body. A body is one connected silhouette; an inner line is allowed only at a real overlap, fold or crease.

Runs inside `uv run tools/quality_gate.py rig <trace.json>` (function `qg_checks.rig_seams`). Per sampled frame it needs `line_mask` (PNG of ink strokes only, canvas-aligned, any uniform scale; ink = alpha or luma > 127) and `seams[]` (id, parts[2], `at`, and a bone axis from `axis` or `from`/`to`; optional `r_px`, `kind`, `via`); `overlaps[]` lists the seam ids (or `partA|partB`) that are real overlaps in that frame. Fields are in `rig-trace.schema.json`. Frames without them are skipped; seams declared but no mask readable fails `SEAM-NODATA`.

| Id | Decision |
|---|---|
| `SEAM-CROSS` | Take the disc of radius r (0.12 head units, or `r_px`) at the joint. Label the 8-connected ink strokes inside it. A stroke is a seam line when its extent across the bone axis is >= 0.6 of the disc diameter and its extent along the axis is <= 0.6 of the across extent (a stroke running along the limb is the outline and passes). Fails unless the seam is in `overlaps[]` for that frame. |
| `SEAM-HEADNECK` | Seams with `kind: "head-neck"` fail when `via` (the neck shape, collar or hijab that connects head and body) is missing, or when any stroke crosses the join (across extent >= 0.45 of the diameter). `overlaps[]` cannot waive it: a chin or collar edge is drawn as a tone step, not an ink line. |
| `SEAM-NODATA` | Seams declared, no `line_mask` readable. |

Limits: a limb outline that bends sharply inside the disc (elbow outer corner) can read as crossing; declare it or shrink `r_px`. Frames without a bone axis are skipped. Ink in the mask must be the character's own strokes (no props, no text).

What the renderer must export: per sampled frame (every 6th is enough) the ink-only line-art PNG, `seams[]` from the rig (joint anchor plus the two bone ends and the two part names) for every joint, finger root, shoulder and the head-neck join, and `overlaps[]` naming the seams where it draws an intentional overlap or crease.

### K.2 PLAYBACK (`preview`, R-382, from `rca-playback.md`)

`uv run tools/quality_gate.py preview previews/index.html [--dynamic]` (function `qg_checks.check_preview_static`, no browser). Each `section.panel` is scanned on its own.

| Id | Decision |
|---|---|
| `PLAYBACK-VIDEO` | A tab that has a `<canvas>` must also have a visible `<video src=...>` (or `<source src>`): the preview is the recorded render the gate measured. |
| `PLAYBACK-AUTOPLAY` | A canvas shown by default (not `hidden`, not in a closed `<details>`, no `data-live`) whose id is named by a script that runs `requestAnimationFrame`, `setInterval(` or `renderAt(` fails. Live painters are allowed only as an opt-in editor. |

Dynamic part (`--dynamic`, Playwright, `PLAYBACK-FRAMETIME` p99 <= 50 ms, `PLAYBACK-LONGTASK` no task > 100 ms, `PLAYBACK-ERROR` no exception or console error): implemented in `check_preview_dynamic` (cold load, two loops of the page's first `<video>`, real foreground window, GPU flags) and the threshold logic is unit-tested (`dynamic_issues`). The browser run itself is NOT verified: Playwright is not a project dependency, headless Chromium throttles rAF so it opens a headed window, and the pass/fail depends on the user's GPU. Without Playwright the flag exits 2 (tool error), never a silent pass. Not implemented from the RCA: cold p50 within 2x of warm p50 and the monotonic displayed-time check (they only matter for live painters, which the static part forbids by default).

Current state: `previews/index.html` FAILS both (tab `mix` paints a live `mixCanvas` with no video), which is the regression this check was written for.


## L. Hands, props and writing (R-383 to R-392, the owner F13 to F15, 2026-10-23)

Command: `uv run tools/quality_gate.py hands <rig-trace.json>` (the same checks also run inside `rig`). Pure JSON, about a second. Thresholds are DEFAULT (uncalibrated) in `qg_checks.HANDW`; calibrate on the first clean Mix v5 trace. Fields the renderer must export per frame are in `rig-trace.schema.json` (`hand_pose`, `props`, `writing`, `cut`, `smear`). Why each exists: `rca-hands-writing.md`. Tests: `tools/tests/test_hands_writing.py` (pass fixture plus one failing mutation per id). A frame without the inputs is skipped, but a trace that has `writing` or `holding` and omits a required field fails.

| Check | Rule | Fails when |
|---|---|---|
| `HAND-TOPO` | R-383, R-384 | finger count is not 4 + thumb, order is not thumb, index, middle, ring, little, topology differs from the hand's first frame, any finger joint changes more than 35 deg in one frame, the hand axis turns more than 40 deg in one frame, or the wrist moves more than 120 px in one frame; waived on a `cut` frame or a declared `smear` frame |
| `HAND-SIDE` | R-385 | the grip id ends in `-L` or `-R` and that is not the hand's side, unless `mirrored: true` |
| `HAND-SWAP` | R-386 | grip id, `contact_kind` or `pinch` changes without 4 earlier frames each carrying `blend{to_id,to_kind,k}` with rising k |
| `PROP-FACE` | R-387, R-388 | a drawn mark is on an undeclared face, on a face the camera does not see (`facing`), or an `ink` mark is on a different face from the one the nib touches (`writing.nib_face`) |
| `WRITE-REVEAL` | R-389, R-390 | ink length grows while `writing.active` is false, ink shrinks, the revealed end is more than 6 px from the nib, or fewer than half of the ink-growing frames move in the script's direction (`rtl`: leftwards) or the net movement is the wrong way |
| `NIB-CONTACT` | R-391 | while writing, `nib_gap_px` (or nib to paper point) is over 6 px or the nib is outside the paper |
| `LAYER-GRIP` | R-392 | a hand `holding` a prop has no `grip_layers`; the drawn `layer_order` restricted to the declared parts differs from the declared order for that angle (paper above the writing hand); or a digit listed in `grip_contacts` is more than 8 px from the held object |

Regression value: on Mix v4 these would have failed at the frames named in `rca-hands-writing.md` (f117 to f118 and f170 to f171 snaps, ink on the card face away from the nib for f10 to f60, paper drawn over the pen hand, thumb 20+ px from the pen).


## M. Calibration on Mix v5 (2026-10-23, the owner 10/10) and the shot pipeline

Reference bar: `reference/mix-v5/` (video, trace, spec, `*.out`). Reproduced by `uv run tools/shot.py all work/shots/mix-v5-repro`: every gate PASS, rig trace identical to the reference frame for frame, video vs `mix-v5.mp4` PSNR 51.5 dB mean (min 40.0), SSIM 0.9981; the pipeline's render metrics are within 0.003 of the reference (independent_share 0.5387 vs 0.5404, parallax_corr 0.199 vs 0.191). Per-shot gate report: `<shot>/gate/report.json`.

Known fails used as the other side of each threshold: style.html v1 A/B and reels base 1/2 (motion), Mix v3 (went 3D: only `look2d` separates it; the render gates pass it at motion_coverage 0.854, independent 0.865), Mix v4 (hand faults: no hand data in its trace, so the hand checks cannot run on it; its faults are known only from `rca-hands-writing.md`: a snap that turned the hand axis about 45 degrees).

Status of every numeric threshold (calibrated-on-v5 = v5 and the known fails bracket it with margin on both sides; default = no evidence from v5 beats the earlier judgement):

| Threshold | Value | Status | Evidence |
|---|---|---|---|
| `motion_coverage` | >= 0.50 (was 0.35) | calibrated-on-v5 | v5 0.774, liked reels 0.69 / 0.71, highest fail 0.412 |
| `independent_share` | >= 0.50 | calibrated-on-v5 (unchanged) | v5 0.540, highest fail 0.432; thin on the pass side: watch it |
| `luma_range` | >= 0.85 | calibrated-on-v5 (unchanged) | lowest pass 0.864 (v4), highest fail 0.834 |
| `local_contrast` | >= 0.085 (was 0.09) | calibrated-on-v5 | v5 0.0921, v3 0.0931; highest fail 0.0753 |
| `parallax_corr` | >= 0.10 (was 0.15) | calibrated-on-v5 | v5 0.191, lowest pass 0.191; highest fail -0.043 |
| `depth_bands` | >= 4.0 | default | v5 4.5; only style B (3.1) fails it |
| `freeze_share_05s`, `dead_window_share`, `low_motion_window_share`, `uniform_share` | 0.03 / 0.05 / 0.05 / 0.35 | default | every pass is 0.0; no tighter value is evident |
| `look2d` `hard_edge` | >= 0.08 | calibrated-on-v5 (unchanged) | v5 0.1017, v2 0.0986, v3 0.064 |
| `look2d` `ramp_area` | <= 0.03 (was 0.04) | calibrated-on-v5 | v5 0.0024, v2 0.022, v3 0.0622 |
| `HANDW.max_joint_jump_deg` | 25 (was 35) | calibrated-on-v5 | v5 max 12.1 deg |
| `HANDW.max_orient_jump_deg` | 30 (was 40) | calibrated-on-v5 | v5 max 15.7 deg; v4 snap about 45 |
| `HANDW.nib_gap_px` | 3 (was 6) | calibrated-on-v5 | v5 0 px while writing |
| `HANDW.grip_contact_px` | 8 | calibrated-on-v5 (unchanged) | v5 max 6.8 px |
| `HANDW.max_wrist_jump_px` | 120 | default | v5 reaches 86.7 px; nothing tighter is evident |
| `HANDW.swap_frames`, `reveal_tol_px`, `min_toward_share` | 4 / 6 / 0.5 | default | not stressed by v5 |
| Rig tolerances (segment 2%, contact 2%, shoulder 85%, balance 10%) | unchanged | default | v5 trace shows 0.0% segment deviation and 0.0% contact gap: the v5 rig is exact by construction, so it gives no margin evidence; calibrate on a second approved shot |
| Section F emotion numbers, text texture, transition frame counts, safe band | unchanged | default | v5 is one 9 s shot with four emotions; too few samples |

Re-evaluating stored metrics with the new values (`quality_gate.py json`): v3, v4, v5 and both liked reels PASS; style.html A/B and both base reels FAIL. Tests: 132 pass (`tools/tests`, includes `test_shot_engine.py`).

Catalogue finding from the pipeline: the v5 spec named `hero/camera/top-pov-insert@2.0` and `pov-tag-cu@2.0`, which do not exist (the entries are `@3.0`). The `catalogue` and `spec` stages now resolve camera refs to the newest catalogue version and fail `SPEC-CATALOGUE` on a ref that does not exist.

## N. Several characters in one shot (2026-10-23, multi-actor engine)

A shot may carry two or more character instances ("actors"). Everything that was keyed by character already was keyed by `characters[<id>]` in the trace, so every rig, hand, face, seam and shadow check runs per actor id and names the actor in its message (`RIG-LIMITS partner frame 5 ...`). What is new is below. Field reference: `shot-spec.schema.json` (`actors`, `actor_interactions`, `beats[].draw_order`, `beats[].actor_emotions`, `beats[].depth_z`) and `rig-trace.schema.json` (`scene`). Engine: `tools/render/actors.js`, `trace-multi.js`, `bootstrap-multi.js`; how to use it: `pipelines/RUNBOOK.md` ("Several characters in one shot"). A spec without `actors[]` and a one-character trace without `scene` are not touched by any of these checks (the v5 repro is the regression case).

Convention: `depth_z` is metres from the camera plane, larger = farther. Draw order is back to front, so the farther actor is drawn first. A draw-order token is an actor id (body, then arms) or `id:body` / `id:arms`.

| Check id | Runs on | Fails when | Status |
|---|---|---|---|
| `ACTOR-DECLARED` | spec | an actor lacks `id/module/depth_z/layer/catalogue_refs`; duplicate id; no `characters[]` rig entry with that id (or an entry that is no actor); the module file is missing; a catalogue ref is not in the module's catalogue; a beat shows an actor with no pose entry | default |
| `ACTOR-ORDER` | spec | a beat with 2+ actors has no `draw_order`; an order omits or repeats an actor; the order draws a farther actor over a nearer one (depth_z, then layer); windows leave a gap or do not end with the beat; a split (A, B, A) or a change of order has no `why` of 12+ chars | default |
| `ACTOR-EMOTION` | spec | a beat with 2+ actors lacks `actor_emotions[<id>]` with `emotion` and `emotion_track` for any present actor. Each actor's block is then checked by every `EMO-*` check on its own (message `actor <id>: ...`); the light may serve either actor's feeling | default |
| `ACTOR-INTERACTION` | spec | 2+ actors in a beat with no `actor_interactions` and no `actors_apart_because`; kind not `contact`, `handover` or `apart`; an `apart` without two different actors, `a.hands`/`b.hands` (L, R), `min_gap_px` >= 1 or a why; an interaction with no why, outside its beat, naming an unknown actor or prop; a contact with `tol_px` above 16, a prop end without `held_by`, or an actor touching itself; a handover with `handoff_frame` not strictly inside its window, `both_hands_frames` below 3, giver = receiver, or a prop not in `props[]` | default |
| `SHADOW-ACTOR` | spec | a present actor has no `cast_shadows` entry with itself as caster (each actor casts its own mass-proxy shadow, R-355) | default |
| `ACTOR-TRACE` | rig | more than one character and no `scene.frames`; trace characters differ from the spec's actors; an actor's frames are not the frames the scene lists it present on | default |
| `ACTOR-OCCLUSION` | rig | a frame has no `draw_order`; a present actor is not drawn exactly once as body and as arms, or an absent one is; an actor is drawn over a nearer one (per-frame `depth`, then layer); the drawn order differs from the spec's declared order for that time; one actor's parts are drawn on both sides of another's with no declared split ("a character drawn through another"). Up to 4 frames are listed, then a count | default |
| `ACTOR-CONTACT` | rig | on any frame of a declared contact window the two points (`contact_points` or `anchors` of the actor; `props[].touch` of a prop) are further apart than `tol_px` (default 8 px, equal to `HANDW.grip_contact_px`); a point is missing (no data fails); a prop end is not parented to its `held_by` hand. **`apart`** (no touch, CLAUDE.md 2026-10-23, added for shot 2): on any frame where both actors are present, any hand of `a.hands` comes closer than `min_gap_px` to any hand of `b.hands`, measured between the drawn hand outlines (`characters[id].frames[].hand_outline_px.{L,R}`, convex hull of palm and digit joints, canvas px; 0 when they overlap); an outline is missing, or no frame has both actors (no data fails) | default |
| `HANDOVER` | rig | the prop's `parent` is not the giver's hand on every frame before `handoff_frame` and the receiver's from it on (the switch is exactly on that frame); either hand's measured `gap_px` is above 8 px on any of the `both_hands_frames` (3 or more) frames before it; the prop's centre jumps more than 16 px between the frame before and the hand-off frame; the prop is not in `scene.props` (no data fails) | default |

Calibration: none of these numbers is measured on a real two-actor shot yet (there is none). They reuse the v5 hand threshold (8 px grip contact) and a 3-frame minimum for the shared grip. Calibrate on the first approved two-actor shot and record the numbers here.

Fixtures and tests (`tools/tests/test_multi_actor.py`): `kb/quality/fixtures/two-actor.shot-spec.json` and `two-actor.rig-trace.json` are the pass case (built by `tools/tests/multi_actor_fixture.py`; a test asserts the stored files equal the builder). Every check id has several one-line mutations that must fail exactly that id and nothing else in its family. The registry has a node harness (`tools/tests/actors_harness.js`, no browser).

Findings from the first multi-actor shot (`work/shots/smoke-partner`, Partner alone through the new engine):

- `RIG-SHOULDER` (resolved 2026-10-23): the old fixed 3 px clavicle line failed any arm raised above about 36 degrees, so earlier artists kept lifts low. The y test now follows the scapulohumeral model above, so one arm may rise to 180 degrees; a shoulder that stays down, or a shoulder anchored in the chest, still fails. Limit: a clip in which every frame is raised with no rise at all has no low-elevation frames to define the rest line; set `rest_shoulder_y_px` in the trace (tracer change, not made).
- `RIG-LIMITS` fails Partner's fist grips: `catalogue/characters/partner/v2/hands/fear-thumb-R.json` (finger flex up to 88 / 98 deg at mcp / pip against the soft limits 80 / 90) and `push-finger-L.json` (little finger 84 / 94). The soft limit is the human default; Partner's `physics.json` overrides only `hip_flex` and `shoulder_flex`. Either the grips curl less or `partner-v1` gets a `finger_mcp` / `finger_pip` soft override with a source. The smoke shot uses `hook-ledge-R` instead.
- `SEAM-CROSS` at both wrists is the reknitted cuff (`partner.js` `cuff()`): a designed overlap, so the shot declares `overlaps` + `overlap_why` (the multi-actor tracer takes them from the module's `seam_overlaps` or from the scene's `traceExtra`).

## O. E01 run-1 process fixes (2026-10-24): voice first, captions only in compose, actors that come and go, a live end card

Root causes found by the first full episode (`work/shots/e01-*/heal/`, `work/episodes/E01/gate/report.json`). Code: `tools/shotlib/voicetiming.py`, `tools/shotlib/presence.py`, `tools/qg_checks.py`, `tools/quality_gate.py`, `tools/shot.py`, `tools/compose.py`. Tests: `tools/tests/test_voice_first.py`. All numbers below are DEFAULTS (no measured sample), none touches an existing threshold.

| Check id | Runs on | Fails when | Status |
|---|---|---|---|
| `SPEC-VOICE-TIMING` | spec (`shot.py spec` and `quality_gate.py spec`) | a spec that opts in (`voice_episode` or `voice_lines`) has a referenced line with no measured take in `work/voice/<ep>/` (`<line>.trimmed.wav` or `.wav`) or, for an on-screen line, no viseme track; a `voice_lines` entry has no measured `dur_s`/`end_s`; a stored `dur_s` differs from the take by more than 0.02 s (the voice changed: re-run the spec stage); a line ends more than 0.05 s after the piece and `spans_out` is not set; a beat's `emotion_track.voice.line` is not in `voice_lines`; a line is listed twice. The spec stage resolves the entries (it fails with the same id before writing) | default |
| `PLAN-VOICE-OFFSET` | compose `plan` | the shotlist's `at_s` disagrees (over 0.05 s) with the piece spec's `voice_lines[].start_s` minus `in_frame / fps`; the piece was timed on a take whose length is no longer the take's (over 0.02 s); a line has neither an `at_s` nor a piece-spec entry | default |
| `PIECE-NO-CAPTION` | spec (`check_texts`) and render (`extras`) | spec: a beat text has `role: caption`, a `caption-bar` plate, or a `speaker`, unless it is marked `diegetic: true` (a tag, card or sign in the world; `role: caption` is never diegetic). Render: text-mask pixels (540x960, 2 fps sampling) outside every declared text box (padded 12 px) reach 150 px on 3 or more sampled frames: a baked caption that the spec does not even declare. Compose is the single caption owner (`EP-CAPTIONS`). `reference/**` is exempt (approved before the rule) | default |
| `ACTOR-RANGE` | spec, rig | an actor's `frames` (`[[f0, f1], ...]`, half-open, integers, sorted, disjoint, inside the shot) is malformed; a beat shows an actor (`beat.actors`, default every actor) that is absent for part of the beat; the trace's frames for an actor differ from its declared `frames` | default |
| `TRACE-INCOMPLETE` (shot.py trace stage) | trace | per actor: the traced frames are not exactly the actor's declared frames (`shot.json` `actors[].present`, same format; default every frame), or a shadow or line mask is missing on one of its `f % 6 == 0` frames. The recorder (`trace-multi.js`) also refuses a scene whose `renderFrame` draws an actor outside, or omits it inside, its declared frames | default |
| `END-CARD` (compose `end`, `EP-CHOICE` on the gate) | end, gate | `end_card.backdrop` is not `live-loop` (default), `live-hold` or `static`. With a live backdrop the card is laid over the last piece's last `loop_s` (default 1.5 s) seconds, played forward and back (or its last frame held) under a scrim (rgba 20,18,15 at 0.80, behind the question and the prompt); contrast is measured on the overlay flattened over WHITE footage, the worst case; `EP-CHOICE` fails when the opaque card pixels of the last frame differ from the overlay (mean diff over 0.06) or, for `live-loop`, when the footage outside the scrim does not move (mean change under 0.0008 between 1.2 s and 0.1 s before the end) | default |

Fields: spec `voice_episode` (set by the spec stage from `shot.json` `piece.episode`), `voice_lines[]` {`line`, `start_s` (from the piece start, negative = J-cut), `speaker`, `on_screen`, `visemes`, `spans_out`; resolved: `dur_s`, `end_s`, `take`, `take_sha256`, `spans_in`, `viseme_keys` on the piece clock}; spec `actors[].frames`; `shot.json` `actors[].present`; spec text `diegetic`; shotlist `end_card.backdrop`, `end_card.loop_s`; shotlist line `at_s` is optional when the piece spec supplies it. `plan.json` lines carry `offset_source` (`shotlist at_s` or `shot spec voice_lines`).

Parallax estimator rerun on E01 (2026-10-24): see the table in `pipelines/RUNBOOK.md` "Parallax estimator report" or `work/episodes/E01/gate/parallax-2026-10-24.json`.

## F. Episode checks (composing stage, 2026-10-23)

Command: `uv run tools/compose.py gate <ep>` (after `plan, audio, captions, assemble, end`); receipt `work/episodes/<ep>/gate/report.json`. Pipeline: `pipelines/COMPOSE.md`; shotlist schema: `kb/quality/shotlist.schema.json`. Each failure prints `FAIL  [ID] message`.

| Check | Threshold | Source |
|---|---|---|
| `EP-LENGTH` | 30 to 60 s | the owner 2026-10-22; Instagram advice (reels.md section 1) |
| `EP-HOOK` | story event declared at <= 2.0 s and >= 60% of 12 fps steps in the first 2 s of shot 1 move >= 5% of 8 px blocks | reels.md section 2; motion definition from `low_motion_window_share` (house default) |
| `EP-CAPTIONS` | one plate per script line; contrast >= 4.5; font >= 40 px (at 1080 wide); RTL Thmanyah; no two plates at once | WCAG AA; CLAUDE.md "Caption every spoken line" |
| `EP-SAFEZONE` | caption and end-card text boxes, and declared face boxes, inside x 5%..95%, y 14%..65% | top/bottom: third-party attribution to Meta, unverified (Q-05); sides: house default |
| `EP-LOUDNESS` | -14 +-1 LUFS integrated, true peak <= -1.0 dBTP, on the final AAC | measured -14.1 LUFS on 3 of 4 delivered benchmark reels (reels.md section 3); the ceiling is a house default |
| `EP-CHOICE` | exactly two Arabic choices, Arabic comment prompt, card >= 2.5 s, text >= 44 px, contrast >= 4.5, the last frame of the video is the card | series.md episode engine |
| `EP-MUSIC-LICENCE` | every music/SFX file used has a row in `assets/audio/LICENCES.md` with licence CC0, PD, CC-BY, CC-BY-SA or OWN (NC/ND refused), credit for CC-BY*, source and date, matching sha256 | `nj-kit:bg-music` |
| `EP-VOICE` | WARN while the episode is "no voice yet" | CLAUDE.md "Voices" |
| `EP-RENDER-GATE` | section B on `episode.mp4` | this file |

Plan/audio/caption stage ids: `PLAN-SHOTLIST, PLAN-LINE-SHOT, PLAN-LINE-UNKNOWN, PLAN-LINE-DUP, PLAN-LINE-TIMELINE, PLAN-LIPSYNC (PLAN-LINE-FIT retired 2026-10-24: lines may cross cuts), PLAN-LINE-OVERLAP, PLAN-LINE-CAPTION, PLAN-VOICE-OFFSET (2026-10-24), PLAN-TRANSITION, PLAN-FRAMES, PLAN-HOOK, PLAN-LENGTH, AUDIO-PARTIAL, AUDIO-MODE, AUDIO-LICENCE, CAP-FONT, CAP-TIMING, ASM-SHOT-VIDEO, ASM-AUDIO, END-CARD`.

## H. Calm format profile (the owner 2026-10-24: "his pacing, our art")

A shot spec declares `"format": "calm"`, a shotlist declares `"profile": "calm"` (the shotlist's own `format` key is the schema id `shotlist/1`). Anything else is **premium** and keeps sections A to B untouched: `RENDER_GATES`, `SPEC_GATES` and the EP-LENGTH / EP-HOOK motion rules do not change. Code: `tools/qg_checks.py` (`CALM`, `format_of`, `check_calm_render`, `check_calm_shot`, `check_calm_declared`), `tools/quality_gate.py` (`calm` command, `analyse_calm`, `--format calm`, `calmjson`), `tools/compose.py` gate (profile read from the shotlist). Tests: `tools/tests/test_calm_gate.py`.

**Art checks apply to both formats**: LOOK2D-LINE/RAMP, SEAM, joints, hands, shadows (flat), no touch, no tashkeel, contrast. The calm episode gate runs `look2d` as `EP-LOOK2D`. At shot level `render --format calm` keeps the premium luma, contrast and depth thresholds (the peer profile `CALM_RENDER_OVERRIDES` moves only the pacing numbers).

### H.1 Video-measured checks (`quality_gate.py calm <video>`; whole episode)

Bands are `[floor, ceiling]`. Floors say holds and breathing are required; ceilings say restlessness fails. Calibration set = the 10 story reels of stickmanstorys22 (`work/stickman/`, measured 2026-10-24, same ffmpeg and torch commands as the gate), margin put on the far side of the measured range.

| Check id | Metric | Band | 10 story reels (min..max) | E01 run 1 |
|---|---|---|---|---|
| `CALM-SHOTLEN` | average shot length = duration / (ffmpeg scene > 0.08 changes + 1), s | 1.8 .. 6.0 | 2.21 .. 4.82 | **1.35 fail** |
| `CALM-CUTRATE` | scene > 0.08 changes per minute (soft joins count) | 8 .. 30 | 11.8 .. 26.5 | **43.5 fail** |
| `CALM-HOLDS` | share of runtime frozen in holds >= 0.5 s (freezedetect n=0.003) | 0.05 .. 0.25 | 0.092 .. 0.173 | **0.0 fail** (a calm episode must rest) |
| `CALM-HOLD-LONGEST` | longest single hold, s | <= 3.0 | 1.27 .. 2.27 | 0 |
| `CALM-MOTION` | motion coverage (mean share of 16 px blocks changing per moving step) | 0.08 .. 0.35 | 0.145 .. 0.249 | **0.753 fail** (restless) |
| `CALM-SUBJECTS` | independent motion clusters per moving step: the measured stand-in for subjects in frame | 2.0 .. 8.0 | 4.19 .. 6.30 | **17.48 fail** |
| `CALM-VOICE-COVERAGE` (audio; was `CALM-NARRATOR`, renamed 2026-10-28) | share of 20 ms frames above -40 dBFS: voice (any speaker) and bed never drop out | >= 0.80 | 0.870 .. 0.967 | 0.976 pass |
| `CALM-LOUDNESS` | integrated LUFS (ebur128) | -15 .. -13 | -14.1 for all | -14.8 pass |
| `CALM-LRA` | loudness range, LU | <= 5.0 | 3.1 .. 4.2 | **7.8 fail** |

The 10 story reels all PASS. The other two harvested items are not story reels and FAIL on purpose: `DeqdR6UPVf6` (shop ad, basketball: clusters 10.5, LRA 8.0) and `DetfQMFvo7U` (4 s YouTube plug, silent: cut rate 0, holds 0.36, coverage 0.075, no audio). Calibrating the bands wide enough to admit them would also admit E01 (E01's LRA 7.8 sits below the ad's 8.0), so they stay out.

**H.1a Pacing is counted from the DECLARED shots (2026-10-25; fixing a wrong measurement, not loosening a band).** E01C (the calm retelling with C3 transitions: flash, whoosh, ink wipe, page turn, iris) failed `CALM-CUTRATE` (36.3 a minute), `CALM-SHOTLEN` (1.63 s) and read 60 scene changes for 22 declared items. Root cause: ffmpeg `scene > 0.08` fires several times inside ONE declared transition (a 0.25 s overlap repaints the whole frame; measured: 60 hits, every one inside a declared window), and the old code counted each hit as a cut. The bands (calibrated on reels that cut hard or dissolve, never on a plan-declared effect) were right; the count was wrong. The fix, `qg_checks.declared_boundaries` / `declared_pacing`, used when `quality_gate.py calm <video> --timeline timeline.json` is given (the compose gate always gives it):

| Metric | Declared path (a timeline is given) | Undeclared path (no timeline: the harvested reels, E01 run 1) |
|---|---|---|
| shots / `scene_changes` | declared boundaries (items joined by an overlap, plus the cuts inside the choice sequence's `split.cuts`) + detector hits OUTSIDE every transition window | detector hits |
| transition window | the overlap `t0(next)..t1(prev)` padded 0.10 s each side (a hard join: 2 pads); detector hits inside are ignored and reported as `ignored_in_transitions` | none |
| `shot_len_s`, `cuts_per_min` | duration / (shots) and shots per minute; `shortest_shot_s` is reported | same formulas on detector hits |
| `CALM-HOLDS`, `CALM-HOLD-LONGEST` | freezedetect holds >= 0.5 s clipped to the shot spans outside the windows, share = held / time outside the windows | whole-runtime freezedetect |
| undeclared change | counts as a cut (a real unplanned cut or glitch still fails the rate and length bands) | n/a |

Bands, thresholds and the freezedetect settings are unchanged. Recalibration: the 10 story reels have no plan, so they run the undeclared path, byte-for-byte the old measurement, and still all PASS (re-measured 2026-10-25 on De1AdirP-wb 2.21 s / 37 changes and De29AiJpzZn 3.53 s / 23 changes; the other 8 read from `work/calm/m_*.json`); E01 run 1 still FAILS (`work/calm/m_E01.json`: shot 1.35 s, 43.5 a minute, holds 0.0, motion 0.753, clusters 17.48, LRA 7.8). E01C on the declared path: 25 declared cuts, 0 undeclared, 60 ignored, shot length 3.81 s, 15.1 a minute: both now PASS. Left failing, for a real reason: `CALM-HOLDS` 0.035 (< 0.05). Every story shot of E01C keeps moving (the engine breathes and drifts; even the two `hold_breathe` shots show frame differences of 0.0027 to 0.0030, no 0.5 s frozen run at n=0.003), and only the recap and card openings freeze. That is a creative finding for the Lead, not a measurement error: either the writer plans real stills, or the definition of a hold changes to "quiet" (needs its own calibration on the reels' `low_motion_window_share` 0.02 to 0.25 and the owner's say).

Advisory, reported but not gating: the audio-active share does not separate E01 (0.976, music bed under the voice), so narrator coverage is judged on the placed takes (H.2). `independent_share`, `low_motion_window_share`, `uniform_share` of the premium list stay in `analyse_render` output.

### H.2 Declared-data checks (compose gate, `check_calm_declared`)

The reels carry no caption or wrapper data, so these are not calibrated on them; numbers come from `research/stickman-recipe.md` section 3 (counted by eye on contact sheets) and are marked DEFAULT where nothing was measured. A missing input FAILS, it is never skipped.

| Check id | Fails when | Source | E01 run 1 |
|---|---|---|---|
| `CALM-CAPTION-STYLE` | a plate has more than 3 words; two plates overlap in time; a plate font is under 90 px at 1080 wide; no plates declared | recipe: 1 to 3 words, big, one at a time. 90 px (4.7 % of height) is a DEFAULT floor under the recipe's estimate of about 7 % | **fail**: 9 of 12 plates over 3 words (up to 11), all 12 plates at 52 px |
| `CALM-VOICE-COVERAGE` (declared; was `CALM-NARRATOR`, renamed 2026-10-28) | union of ALL placed voice takes, narrator and characters alike (plan.json `lines`) covers less than 0.85 of the runtime | DEFAULT: the reels' audio is continuous (92 % active) but a voiced share needs ASR, which is banned | **fail**: 0.67 |
| `NARRATOR-SHARE` | format v2, E03 on (`calm_compose.narrator_role_problems`, animatic `timing_findings`, `stage_gate`): the narrator speaks a line that is not the hook, the first scene's recap, a `role: "link"` scene line (at most 14 words), a choice line, the written object or an intro; or the narrator is over 25 % of the placed voice TIME (`NARRATOR_SHARE_MAX`), the vote card not counted (the owner 2026-10-28: the vote question is the narrator's by role) | the owner 2026-10-28, R-497 | E03 (old format): 19 of 19 lines narrator |
| `DIALOGUE-LINES` | format v2, plan/script verify before the voice (`calm_compose.dialogue_problems`): fewer than 10 or more than 15 lines with speaker != narrator; fewer than 2 character speakers; no two character lines of different speakers one after the other | the owner 2026-10-28, R-497 | E03: 0 |
| `EVENTS` | format v2, plan verify before the voice (`calm_compose.event_problems`): fewer than 2 or more than 5 scenes with an `event`; an event scene on `reaction_closeup` or `hold_breathe`; an `event` under 3 words; a night (consequence block / story+cliff, or the plan's `night` ids) with no event scene; a malformed `needs_art` | the owner 2026-10-28, R-498/R-499 | E03: 1 shown event, an empty night |
| `PLAN-INTRO` (extended) | a character introduced in an earlier episode of the series (plan `intros` of E01C, E02, ...) has an intro again; from E03 on the first-appearance rule skips them (`calm_intro.introduced_before`) | the owner 2026-10-28, R-500 | E03 re-introduced 4 characters |
| `CALM-WRAPPER` | shotlist `wrapper` lacks recap, day_card, choice_card or follow_card (`{t0, t1}` seconds); recap not inside the first 3 s; choice card not inside the last 20 s; follow card before the choice card; day card after it; the end card does not show exactly two choices | recipe table: recap 0 to 2.2 s, choice card from 66 s of 85 s, follow card after | **fail**: nothing declared |
| `CALM-LENGTH` (compose) | the episode is shorter than 25 s (sanity floor). **No upper cap**: the owner decided 2026-10-25 that length is whatever suits the story, so the former 92 s ceiling (a DEFAULT taken from the reels, never a measured limit) and the 20-scene plan ceiling are gone. Over 92 s is a WARNING in `gate/report.json` (`warnings`), never a fail | the owner's decision, CLAUDE.md "Calm format" | E01C 99.2 s: was a fail, now pass with a warning |
| `CAP-FOREIGN-GLOSS` | a caption plate, or a visible plan string (recap, choice, post caption, place), contains a glossary word (`bible/series/<series>/glossary.json`, matched in the speaker's own lines, the narrator may quote any unambiguous word) with no «(meaning)» after it, or with a different meaning. `PLAN-GLOSS` is the same check at plan time. `GLOSSARY` validates the file (provenance in the character bible, no tashkeel, no Latin, meaning at most 3 words) | the owner 2026-10-25, CLAUDE.md "Gloss foreign words". A gloss is an annotation line under the plate, so it does not count toward the 3-word plate limit (`CALM-PLATE-WORDS`, `CALM-CAPTION-STYLE`) | E01C L15 «شيكامو» and L06 «أري» had none |
| `CALM-SUBJECTS` (declared) | a shot lists more than one entry in `subjects` | CLAUDE.md "one subject per frame" | not declared |

### H.2b Reach, hook, prompt and mark checks (research/algo/DESIGN.md, the owner approved section 9 on 2026-10-25)

Added in R-212/R-396 style: every new check names its source and its failing line. The plan checks run from E02 on (`calm_compose.algo_on`, the same switch as the recap): E01C v5 is approved and keeps its format. Never loosened, never skipped; a missing input fails.

| Check id | Where | Fails when | Source |
|---|---|---|---|
| `PLAN-HOOK` | `validate_plan` (`validate_algo`) | from E02 the plan has no `hook` {pattern 1..10, line}; the line is not in `script.json`, is not the narrator's, is also a scene or choice line (it is the FIRST spoken line, on the recap card, nowhere else); its first clause has more than 8 words; it opens with a greeting, «تابعوا», a logo or the series name alone | DESIGN.md 2.1, 3; hook research H A |
| `CALM-HOOK-3S` | gate, all episodes | no voiced line and no declared story event (a scene's `foley` cue) starts before 3.0 s. Reads `timeline.json` and the plan, no render. E01C passes on its bag landing at 0.53 s and L01 at 0.2 s | DESIGN.md 2.1; IG 3-second skip rate (OFFICIAL, IG 2) |
| (recap length) | `stage_plan` `PLAN-DURATION` | the SPOKEN recap card would last over 3.0 s (`RECAP_MAX_S`, the existing `CALM-RECAP-FIRST` / `CALM-WRAPPER` cap, not moved): the narrator line must be about 2.4 s aloud | DESIGN.md 2.1 |
| `SCRIPT-FIT` | script stage, before any voice (`line_fit.script_problems`, R-502): a line the estimate (seconds = a + b x Arabic letters, fitted to the real takes in `tools/line_fit_rates.json`, `a` raised by the p90 residual) puts over its slot: recap 2.45 s, scene 9.45 s, intro 8.45 s, the four choice lines together 13.7 s; sent back to the writer with its letter budget, up to 2 repair rounds, never a stop | the owner 2026-10-30, R-502 | E04, E05: recap H01 3.88 s against the 3.0 s card |
| (take over its slot) | `PLAN-DURATION` is CURED, not a stop (R-502): `line_refit.cure` rewords the line under a new id (H01r1), voices only it once, and plan runs again; the caps in the rows above do not move | the owner 2026-10-30, R-502 | E05 |
| (plate up too briefly) | `CAP-READING-SPEED` / `CAP-READ-TIME` at the animatic are HEALED, not a stop (R-503): `read_heal.cure` feeds the measured shortfall to the plan (`lead_hold` before the voice for a first sentence, `read_hold` after the line for a last one) and reruns plan and animatic; the 1.5 s floor, 12 cps and `LEAD_MAX_S` do not move; a middle sentence stays a stop | the owner 2026-10-30, R-503 | E05 L06 |
| (shot fails a depth gate) | `parallax_corr` / `depth_bands` at the shot gate are HEALED, not a stop (R-504): `depth_heal.cure` gives the failing calm shot a longer dolly plus a slight sideways drift (then the near tags), rung by rung, and gates it again with the same unchanged thresholds (`parallax_corr >= 0.10`, `depth_bands >= 4.0`); 2 rounds a run, each rung once per shot, a rig/hands/look fault is never retried this way | the owner 2026-10-30, R-504 | E05-s01 (0.063) |
| `PLAN-SOFAR` | `validate_plan` | from E02 the first scene's narrator line names no cast member (the glossary `names` and the plan's intro names, a clitic و ف ل ب ك allowed) | DESIGN.md 2.2 |
| `CALM-HUD` (extended) | gate | a story scene has a gap in its HUD plates (the strip plate and the plate that takes over share one handover); from E02 the first HUD plate does not carry the strip «الحلقة N · the series» for 3.0 s starting inside the first 3 s; the recap card's tag (timeline item and the recap shot's `calm.json`) is not the same words | DESIGN.md 2.3 |
| `PLAN-PROMPT` | `validate_plan` | from E02 `choice.prompt` (default `calm_cards.COMMENT_PROMPT` «ما رأيكم، ولماذا؟») or the closing narrator line (`choice.lines.hook`) carries a digit, one of `BANNED_ASK` («اكتبوا اختياركم», «علقوا», «صوتوا», «اختاروا», «شاركوا», «اذكروا», «اضغطوا», «تابعوا لتعرفوا», «تابعوا»), or is not a question (a «؟» or a question word) | DESIGN.md 5.2, 5.3 |
| `PLAN-FOLLOW` / `CALM-FOLLOW-LINE` | `validate_plan` / gate | from E02 the follow card line (the shot's `calm.json`) is not the plan's `follow_line` or `calm_cards.FOLLOW_LINE` «الحلقة القادمة تتبع ما تكتبونه», or it fails the same ask rules | DESIGN.md 2.4 item 12 (IG 6.10, FB 1.4) |
| `PLAN-VARIANTS` | `validate_plan` | from E02 `choice.variants` {"1": [...], "2": [...]} has fewer than 8 distinct wordings on a side | DESIGN.md 5.3, 5.4 item 1 |
| `CALM-COVER` / `COVER-SQUARE` | gate / `calm_cards.check_card` | from E02 `cover.png` is missing or not 1080x1920 (written by assemble with `cover.json`); a `cover_card` text box leaves the central square (y 420..1500) the profile grid keeps | DESIGN.md 2.6 |
| `WATERMARK-PRESENT` | gate, every episode | `watermark.json` is missing, names another rect, an opacity outside 0.25..0.50 or another mark file; or the mark's alpha correlates with the corner's local contrast (`watermark.corner_ncc`, threshold 0.35) on under 80 % of 24 frames sampled across the delivered file. Calibrated on E01C v5: 0.0 % of samples on the unmarked master (median correlation 0.03), 91.7 % on the marked file (median 0.83) | the owner 2026-10-25, CLAUDE.md "Small NJ logo on every frame" |
| `WATERMARK-CLEAR` | gate, every episode | the mark's rect (top-right, 926,282, 96 x 96, 12 px clear space) touches any caption plate, HUD plate, face box (the rig-trace union per shot), card text box or intro box of the episode (static: the mark is on every frame, so a plate that ever overlaps it counts), sits in a phone UI zone (the top 270 px bar, the bottom 670 px caption zone, the right button rail x >= 929 and y >= 864: a judgement, no official pixel spec), or is over 128 px | the owner 2026-10-25; Reels / Shorts UI zones as in `SAFE` |

`tools/compose.py`'s older non-calm profile does not lay the mark and must not be used to deliver an episode. A card or intro with no `card-measure.json` / `intro-measure.json` fails `WATERMARK-CLEAR` (never skipped); card boxes are scaled by the 4 % push-in before the test. `ask_problems`: a statement is a question only with «؟» or a leading interrogative (أين ماذا لماذا كيف هل متى كم من ما أي).

The mark is the last compose step: `stage_assemble` adds it as one more input of the single final encode, so a new episode is never encoded twice; an already composed master gets it through `uv run tools/watermark.py apply <in.mp4> <out.mp4> <episode work dir>` (video re-encoded once, same NVENC settings; audio copied bit for bit). On E01C v5 that left 42.9 dB or better PSNR outside the mark's rect on 12 sampled frames and an identical audio stream.

### H.3 Shot level

`quality_gate.py render <shot.mp4> --format calm` applies the peer profile's pacing overrides plus the ceilings of `check_calm_shot` (`CALM-MOTION`, `CALM-SUBJECTS`: a still shot is a hold, not a fault). `spec` with `"format": "calm"` relaxes holds (declared hold up to 4.5 s, 50 % of runtime), camera move (2 %) and interactions per beat (one cause and effect, not one per 3 s); depth planes, parallax, light, shadows, anticipation, rig parts keep their premium values.

### H.4 Episode gate switches (compose.py, shotlist `profile: calm`)

`EP-LENGTH` is a 5 s sanity floor (the story sets the length); `EP-HOOK` keeps the story-event-in-2-s rule and drops the first-shot-motion floor; `EP-CAPTIONS` allows plates of 0.15 s (word by word) instead of 0.3 s; `EP-RENDER-GATE` runs `quality_gate.py calm`; `EP-LOOK2D` is added; the four declared checks above run as their own results; `gate/report.json` carries `"format"`. Still unchanged and still run: EP-SAFEZONE, EP-LOUDNESS, EP-CHOICE, EP-MUSIC-LICENCE, CAP-NO-TASHKEEL, EP-VOICE.

### H.5 Limits

Calibrated on 10 reels from one creator: the numbers describe his pacing, not a law. Caption style has no video-side check: a white-text-in-the-lower-band proxy was tried on the 12 reels plus E01 and did not separate them (E01 1.76 plate changes a second against 0.9 to 2.5), so it was dropped; caption style is judged on `captions.json`. The first real calm episode of ours must be measured and written back here (and the peer profile's provisional shot numbers re-checked against it).
