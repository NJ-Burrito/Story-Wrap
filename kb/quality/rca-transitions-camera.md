# RCA: transitions, camera design and text legibility (F2, F3, F4)

Source of the complaints: `bible/feedback/2026-10-23-mix-v2.md` (Mix v2 scored 6/10). Rules that fix them: `bible/craft/transitions-camera.md` (R-320..R-339). Evidence: `previews/index.html` (Mix v2 code), `work/demo-v2/shot-spec.json`, `work/demo-v2/mix-v2.mp4`; frames in `work/rca/transcam/` (`sheet1.png` = 2.96, 3.0, 3.04, 4.9, 5.04, 6.9, 7.04, 8.5 s; `crop_tag_4.9.png` = the bag tag at 4.9 s). Grades: M measured, S source read, J judgement.

## RC-T1. The style and rate switch is a beat index, so it happens on one frame

Mechanism. `setup(t)` computes `b = t < 3 ? 0 : t < 5 ? 1 : t < 7 ? 2 : 3` and then, on that index, flips everything at once: `HALF = b === 1; MIS = b === 1;` (`previews/index.html:841`), and ambient, fill and rim colours are looked up from arrays of four entries (`:838-840`). The frame rate is flipped the same way: `tB = beat === 2 ? floor(t*8)/8 : t` and `tS = beat === 1 ? ... floor(t*12)/12 : t` (`:860-861`). The first frame of the beat is the first frame of halftone, offset ink and twos. There is no ramp, no carrier and no cover. Frames at 2.96 s and 3.04 s in `sheet1.png` show it: Hero's face, coat and hijab go from flat cel to full dots with no in-between frame, while the lamp, the shelves and the counter stay clear. [M, frames]

Why it reads as a split frame. `solid()` draws the halftone on one half of every shape: the dot pattern is a `fillRect` on the shadow side of the light axis only (`:589-592`). So in a B beat every object is two looks side by side (dots and clean), and in a mixed A+B beat the world is clear while the bag is dotted. The eye sees a cut line through objects and through the frame (the world next to the dotted objects). In the 5.04 s frame of the sheet a hard vertical edge is visible across the frame at about x = 1000 of the sheet panel (the post at the left edge of the next panel, a foreground plane), which adds a second seam. [M, frame; the cause of that seam was not isolated, J]. For v1 (`previews/style.html`), the options A and B are shown as two cards side by side and each option flips inside the clip at fixed times (`leap = d.mode === "B" && t >= 2.95 && t < 4.4`, `:427`); I did not trace the exact v1 split and treat that as unverified [J].

Why nobody caught it. The spec has `treatment` and `treatment_reason` per beat (`shot-spec.schema.json`: required `treatment`, `treatment_reason`) but nothing at the boundary. The spec in `work/demo-v2/shot-spec.json` therefore lists four beats with A, B, A+B, A and no field for how one becomes the next. The render gate has no style or cadence check (`mix-v2.checks.md` metrics: freeze, motion coverage, luma, depth). Mix v2 passed every gate and scored 6/10. [M]

Construction rule: R-320..R-325, catalogue in `bible/craft/transitions-camera.md`.

## RC-T2. No camera design step: the camera is one formula, and the spec only asks "how much"

Mechanism. The camera is a single continuous function of time for the whole 9 s: `C = {x: -.2 + .044*t + ..., z: .35 + .035*t + .24*sstep(5,7.2,t) + ...}` (`:823-826`) with an impact shake. It is not per shot. The spec asks for `camera_move_pct` (>= 4 or `locked_camera_because`) per beat (`shot-spec.schema.json`), and the demo answers 9, 7, 8, 7 (`work/demo-v2/shot-spec.json`). That is a quantity, not a design: no size, angle, lens, move type or reason. In the frames the camera sits at the same eye-level medium shot of Hero behind the counter in all four beats (`sheet1.png`): the shock beat (3-5 s) has no change of size or angle, and the plot-turn beat (5-7 s) is the same framing with a slow push. [M, frames]

Why it happened. The pipeline order in CLAUDE.md is research, writing, sketching, animating, composing. There is no stage between writing and sketching that decides the camera, so the code author invented a camera while coding the world. the owner's note F3 ("design the camera angles before drawing") names exactly the missing stage. The RC1-RC8 fixes in `root-causes.md` added depth planes and parallax, and the gate rewards a move (`camera_move_pct >= 4`, `parallax_corr`), which pushes the author to add a drift to pass, the same "metric rewards filler" failure as in RC4 [J].

Construction rule: R-328..R-333, and a `camera_plan[]` that the spec gate requires.

## RC-T3. Halftone, offset ink and bloom are drawn into the same pass as the text, and the text has the same colour as the dots

Mechanism. The name text is drawn by a callback inside `drawTag` (`:676` `o.text(tw, th)`) after `solid()` has already filled the tag with the halftone (`:589-592`, `half` true in beats 2 and 3, `:1098`). The tag is therefore a plate that is half dots. The dot colour is `#0a0f2a` (`:558`), the main name colour is `#14100c` (`:1108`): relative luminance about 0.005 and 0.006, a ratio of about 1.0:1 where the glyph overlaps a dot [J, computed from the two colours; the true value depends on the dot coverage]. The sub-line "الخميس القادم" is `500 13px` drawn under `ctx.scale(.001)` (`:1107-1109`), in `#6b1a12`, a size and colour that no halftone background allows. The offset-ink pass (`mis: true` draws a cyan and magenta shifted outline, `:614`) adds two more coloured edges around shapes under the glyphs. The bloom, lamp and glow passes are `lighter` composites over the whole picture (`:965-967`), and the vignette multiplies it, so even a clean tag is washed. No step is "text, last". [M, `crop_tag_4.9.png`: the name is a dark glyph over dark dots, the sub-line is merged into the dots and unreadable]

Why it happened. Text was treated as a texture on the object (a thing that rotates and swings with the tag) and not as information. The spec has no field for text at all: no box, no read time, no contrast. The gate checks `local_contrast >= 0.09` and `luma_range` over the whole frame, and those two numbers go UP when halftone is added; a measure of whole-frame contrast rewards the very pattern that hides the text. [M, `mix-v2.checks.md`: local_contrast 0.0966 passed]

Second cause: movement. The tag swings (`ang` in `:1103`, `ring(...)` terms up to 1.6 rad at the slam) and the text is on it, so the text is moving in the same frames it is meant to be read. [J]

Construction rule: R-334..R-339.

## RC-T4. The gate measures motion and light; it has no text, transition or camera field

This is the common root cause behind the three above. `root-causes.md` RC6 says "what a spec does not ask for, a coding agent does not build". The schema has nothing for transitions, camera design or text, so none was built. Gate proposals follow.

## Gate proposals (exact diffs; I have not edited the schema or the tool)

### G1. Spec: `transitions[]` and `rate_change[]` for every beat boundary (R-320..R-325, R-327)

Add to the top-level `required` list of `kb/quality/shot-spec.schema.json`: `"camera_plan"`, `"transitions"`, and add these properties (next to `beats`):

```json
"transitions": {
  "type": "array",
  "description": "One entry per beat boundary (n beats -> n-1 entries). Style, frame rate and camera never change without one.",
  "items": {
    "type": "object",
    "required": ["from_beat", "to_beat", "type", "frames", "cause", "style_entry", "rate_change"],
    "properties": {
      "from_beat": {"type": "string"},
      "to_beat": {"type": "string"},
      "type": {"enum": ["match-cut", "action-cut", "impact-cover", "carrier-bleed", "whip-smear", "contour-wipe", "fade-through-light"]},
      "frames": {"type": "integer", "minimum": 0, "maximum": 24},
      "cause": {"type": "string", "minLength": 8, "description": "On-screen element or event in the 6 frames before (e.g. 'bag hits counter at 3.42 s')."},
      "carrier": {"type": "string", "description": "Required for carrier-bleed: the object the new look spreads from."},
      "style_entry": {"enum": ["under-cover", "bleed-6-12", "none-same-style"]},
      "style_entry_frames": {"type": "integer", "minimum": 0},
      "rate_change": {
        "type": "array",
        "items": {"type": "object", "required": ["part", "from", "to", "ramp"],
          "properties": {
            "part": {"type": "string"},
            "from": {"enum": ["ones", "twos", "threes", "fours"]},
            "to": {"enum": ["ones", "twos", "threes", "fours"]},
            "ramp": {"enum": ["hold-sequence-2-2-1-1-1", "under-cover", "none"]}}}
      },
      "audio_lead_frames": {"type": "integer", "minimum": 4, "maximum": 12},
      "audio_lead_none_because": {"type": "string"}
    }
  }
}
```

`quality_gate.py spec` additional checks (each prints a named failure):
1. `len(transitions) == len(beats) - 1` and the ids match consecutive beats.
2. If the `treatment` of the two beats differ, `style_entry != "none-same-style"` and `cause` is non-empty.
3. `style_entry == "bleed-6-12"` requires `6 <= style_entry_frames <= 12`; `"under-cover"` requires `type in {impact-cover, whip-smear}` and `frames >= 2`.
4. `type == "contour-wipe"` or `"carrier-bleed"` has a non-empty `carrier` or `edge_follows` (no straight edge).
5. Every `rate_change` with `ramp == "none"` needs `type in {match-cut, action-cut, impact-cover}`.
6. `audio_lead_frames` in 4..12 or `audio_lead_none_because` present.

Against `work/demo-v2/shot-spec.json` this refuses: it has four beats with A, B, A+B, A and no transitions, so it fails check 1 (needs 3 entries) and check 2 (A to B, B to A+B, A+B to A).

### G2. Spec: `camera_plan[]` before drawing (R-328..R-333)

```json
"camera_plan": {
  "type": "array", "minItems": 1,
  "items": {
    "type": "object",
    "required": ["shot", "beat", "size", "angle", "lens_mm", "move", "start_frame_desc", "end_frame_desc", "dur_s", "why"],
    "properties": {
      "shot": {"type": "string"},
      "beat": {"type": "string"},
      "size": {"enum": ["ECU", "CU", "MCU", "MS", "MWS", "WS", "EWS"]},
      "angle": {"enum": ["eye", "low", "high", "overhead", "dutch"]},
      "dutch_deg": {"type": "number"},
      "lens_mm": {"enum": [24, 35, 50, 85, 135]},
      "move": {"enum": ["locked", "push", "pull", "track", "pan", "tilt", "crane", "handheld", "whip"]},
      "start_frame_desc": {"type": "string"},
      "end_frame_desc": {"type": "string"},
      "dur_s": {"type": "number"},
      "why": {"type": "string", "minLength": 12, "description": "Emotion or information that motivates size, angle and move."},
      "thumbnail": {"type": "string", "description": "path to the 9:16 thumbnail in work/<episode>/camera/"},
      "line_180": {"type": "string"},
      "safe_boxes": {"type": "array", "items": {"type": "object", "required": ["id", "x", "y", "w", "h"]}}
    }
  }
}
```

`quality_gate.py spec` checks: each beat has at least one shot; the shot durations of a beat sum to its `end - start` within 0.05 s; `thumbnail` file exists; consecutive shots in a beat differ in `size` or `angle` by at least one step unless the second says why in `why` (this stops "same frame four times", the Mix v2 failure); `move != "locked"` needs a `why` of at least 12 characters; the `camera_move_pct` in beats stays, but is derived from the plan (not a free number); `safe_boxes` lie inside x 0..960, y 250..1580 (top 250, bottom 340, right 120) at 1080 x 1920. The existing `camera_move_pct` rule in the schema description stays as is.

### G3. Spec and render: text layer, plate, contrast, size, texture-free region (R-334..R-339)

Add to each beat:

```json
"texts": {
  "type": "array",
  "items": {
    "type": "object",
    "required": ["id", "string", "lang", "box", "layer", "plate", "min_contrast", "height_px", "read_time_s", "appear", "leave"],
    "properties": {
      "id": {"type": "string"}, "string": {"type": "string"}, "lang": {"enum": ["ar", "en"]},
      "box": {"type": "object", "required": ["x", "y", "w", "h"], "description": "px at 1080x1920, per-frame track allowed as 'box_track' path"},
      "layer": {"const": "top", "description": "drawn after every effect, grade and vignette"},
      "plate": {"enum": ["opaque-flat", "caption-bar"]},
      "min_contrast": {"type": "number", "minimum": 4.5},
      "height_px": {"type": "number", "minimum": 28},
      "decor": {"type": "boolean"},
      "read_time_s": {"type": "number"},
      "appear": {"type": "string", "description": "transition id or 'cut-on-beat-start'"},
      "leave": {"type": "string"}
    }
  }
}
```

`quality_gate.py spec`: `layer == "top"`, `plate` present, `height_px >= 36` for non-decor (28 for sub-lines), `read_time_s >= 0.6 + 0.1 * words`, the box lies inside the safe band, and the text interval does not overlap a transition with `style_entry != "none-same-style"` that includes the box.

`quality_gate.py render` (new `text` sub-check; read the boxes from the spec, sample frames `ceil(appear*24)..floor(leave*24)`, work on the decoded luma frames, no extra model):

| Metric | Definition | Threshold | Mix v2 expected |
|---|---|---|---|
| `text_contrast_p10` | WCAG contrast of the glyph-mask mean luminance (the renderer writes `work/<ep>/text-mask/NNNN.png`, a 1-bit text mask) against the mean luminance of the plate ring (box dilated by 6 px minus the mask); take the 10th percentile over visible frames | >= 4.5 (>= 3.0 for `height_px >= 48` large text); 7.0 target for the Arabic name | fails (about 1.0 on the dot side, judged from the code colours) |
| `text_region_texture` | std dev of luma inside the knockout region (box + 0.5 cap height) after subtracting the mean, glyph pixels masked out; max over visible frames | <= 6 (of 255) | fails (the dot grid gives a std dev of tens) |
| `text_edge_clean` | share of ring pixels whose chroma is outside the palette of the plate (offset-ink cyan and magenta) | <= 0.02 | fails with `mis` on |
| `text_motion_px_s` | median speed of the box centre while visible | <= 60 | fails at the slam (the tag swings) |

If the renderer cannot give a text mask, a fallback that needs only the video: compute the luma histogram inside the box and require its two main modes to differ by a contrast of 4.5 (WCAG formula on the mode luminances) with the minority mode holding at least 8% of the pixels. This is weaker and says so in the report [J].

### G4. Render: style-strength and cadence tracks (R-321, R-322)

The renderer writes `work/<ep>/tracks.json` with, per frame, `style_strength` (0 = pure A, 1 = full B: the mean of the halftone coverage of lit shapes) and `unique_frame_share` per declared part layer. `quality_gate.py render` fails when: `|style_strength[f] - style_strength[f-1]| > 0.35` on a frame not inside a declared `impact-cover` or `whip-smear` window; or a part's cadence (frames per unique image) changes at a frame that is not a declared `rate_change` frame (tolerance 1 frame). Mix v2 would fail at 3.0 s (`HALF` jumps 0 to 1 on one frame) [M, `:841`].

A video-only fallback when the renderer is not instrumented: a halftone-coverage proxy by the share of pixels whose 9 x 9 neighbourhood has a high-frequency periodic pattern (FFT peak at the dot pitch, 9 px at 1080 wide: `dotC` is a 9 px tile, `:559`), taken per frame; the same step rule applies. [J: untested]

### G5. Process: the stage and its order

Add to CLAUDE.md "Stage order": research, writing, **camera and transitions plan**, sketching, animating, composing. A sketch or art task is refused without a spec that already passes G1 and G2. Mix v3 is the first piece that follows it.

## Priority

1. G1 (transitions, required per boundary): it is the direct fix for F2, cheap and testable on the spec.
2. G3 (text layer plus measured contrast and texture-free region): it is the direct fix for F4 and the measure is on the render.
3. G2 (camera_plan before drawing): it is the fix for F3, and also gives the F7 catalogue its camera angles.
G4 follows; it needs the renderer to write tracks.

## Limits

- I did not trace the v1 (`style.html`) split frame to a line; the Mix v2 mechanism is traced. The v1 claim is a reading of the page structure.
- The contrast figure for the tag text is computed from the source colours, not measured on pixels; the `crop_tag_4.9.png` frame shows the effect.
- The frame counts and ramps for style and rate changes are our judgement (no source documents Spider-Verse's exact mechanics); rehearse once before series use.
- The Reels safe-zone numbers come from third-party guides, not from Meta.
