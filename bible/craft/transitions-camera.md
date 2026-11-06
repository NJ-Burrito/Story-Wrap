# Transitions, camera design and text legibility (craft rules R-320..R-339)

Trigger: the owner's notes on v1 and Mix v2, 2026-10-23 (`bible/feedback/2026-10-23-mix-v2.md`): F2 the switch between styles, beats and ones/twos/threes looked like a split frame; F3 design the camera before drawing; F4 halftone covered the text. Root causes and evidence: `kb/quality/rca-transitions-camera.md`. Grades: M measured by us, S source read, J judgement.

## Principle

A change of style, frame rate or camera is an event with a cause, a type and a length. It is never a side effect of a beat index. Pre-production order is fixed: beat -> camera design -> transition plan -> text plan -> only then art.

## A. Transitions (R-320..R-327)

- **R-320** Every beat boundary names a transition: type from the catalogue, length in frames, and the motivation (action, plot or feeling). No bare cut between beats whose treatment (A, B, A+B) or frame-rate set differs. Check: spec gate, `transitions[]` covers every boundary.
- **R-321** Style (halftone, offset ink, palette, rim colour) is never switched on one frame. It enters through a carrier (an object, a light, a wipe edge) and bleeds in over 6 to 12 frames (24 fps), or it switches under a hard cover (flash, whip, impact freeze) that hides at least 2 frames. Check: render gate, the per-frame style-strength curve has no step above 0.35 in one frame outside a declared cover.
- **R-322** Frame rate changes only through the ramp in the catalogue (twos to ones: hold lengths 2,2,1,1,1; ones to threes the reverse), or on a declared impact freeze or cut. Each part has a rate; a boundary lists the parts that change and the ramp used. Check: the spec has `rate_change[]` per transition; the render gate finds no unexplained change of unique-frame cadence.
- **R-323** Motivated switch: an A to B change needs a cause visible on screen in the 6 frames before it (the bag hits the counter, a light flashes, a look). "Because it is beat 2" is rejected. Check: `transitions[].cause` is non-empty and names an element or event; a reviewer confirms it in the frame sheet.
- **R-324** Prefer the carrier to the wipe. Order of preference: (1) match cut on shape or motion, (2) cut on action, (3) object-driven bleed (a glowing tag spreads its look), (4) whip or smear frame, (5) graphic wipe. A wipe edge that is a straight vertical or horizontal line is forbidden: it reads as a split frame (F2). A wipe edge follows an object contour or an ink stroke, and moves with the action.
- **R-325** Transition frames are drawn, not computed: smear frames, motion-blur frames and impact frames are 1 to 3 frames, hand-built, each with its own art note. Their length is stated in the spec.
- **R-326** Cut on action: a cut between shots lands on the mid-point of a movement, with the movement continuing in the same screen direction, or on a matching shape (match cut). Eye-line match: the look leaves the frame in one direction and the target enters from the side the gaze points to. The 180-degree line is set per scene in the camera plan; crossing it needs a declared reason (a disorientation beat). [S https://www.studiobinder.com/blog/what-is-continuity-editing-in-film/, https://www.masterclass.com/articles/film-101-what-are-eyelines-how-to-use-eyeline-match-to-tell-a-story-and-drive-a-narrative]
- **R-327** Sound leads or trails picture across every beat boundary by 4 to 12 frames (J cut or L cut), and the beat's first SFX lands on the transition frame. Check: `transitions[].audio_lead_frames` is 4 to 12, or `audio_lead_none_because` is given. [J: the search found no usable source for J and L cuts; the frame range is ours.]

### Transition catalogue (24 fps)

| Type | Use when | Frames | Frame-rate ramp | Style entry |
|---|---|---|---|---|
| `match-cut` | two shots share a shape, motion or position (bag handle to hand) | cut + 4 shared-pose frames | both sides keep their rate; the matched element is on the same rate on both frames | new style starts on the 3rd frame after the cut |
| `action-cut` | a movement crosses beats (a drop, a swing) | cut at 40-60% of the move | change at the cut only if declared | the change is hidden by one motion-blur frame |
| `impact-cover` | shock, slam, reveal (A to B) | 3 to 5: 1 impact frame, 2 holds on ones, 1 to 3 blur | twos to ones across the cover, then the target rate | the style flips inside the cover frames; a 6-frame bleed follows |
| `carrier-bleed` | a plot object changes the world (tag glows, light spills) | 8 to 16 | ramp over 6 frames, starting at the carrier | spreads from the carrier outward along contours, radius grows by ease-out; never a full-frame rectangle |
| `whip-smear` | change of place or time | 4 to 6 | ones inside the whip, then the target rate | the smear frame carries both looks |
| `contour-wipe` | an A <-> B reversal (B to A) | 6 to 12 | ones during the wipe | the edge follows a moving ink line or object edge, with 2 px offset ink on the edge |
| `fade-through-light` | a feeling change, no action available | 8 to 12 | ones | through a light bloom to 85% white, the new look underneath |

Forbidden: an instant style flip on a beat index; a straight-line wipe; a cross-dissolve between two different styles (both halftones show as mud); a frame-rate change on a held pose with no event.

Sources. Spider-Verse is the evidence for style as signature and frame rate per part: Hobie's body on threes, guitar on fours, outline on twos while moving, vest delayed a few frames [S https://www.cgspectrum.com/blog/spider-man-into-the-spider-verse-how-they-got-that-mind-blowing-look, https://thekonews.org/2023/10/spider-verse-boundary-breaking-or-back-breaking/]. Earth-65 watercolour bleeds with Gwen's feeling, and Hobie's watch makes nearby scenery take his world's look when a portal opens: a carrier, not a flip [S https://www.awn.com/animationworld/unpacking-spot-and-hobies-disruptive-styles-spider-man-across-spider-verse, https://tvtropes.org/pmwiki/pmwiki.php/WesternAnimation/SpiderManAcrossTheSpiderVerse]. The searched sources do NOT document exact frame counts or the ramp of rate changes at world boundaries. The frame counts and ramps in this table are our judgement [J] and need one rehearsal on a throwaway shot before series use. Hair and cloth were kept on ones so they do not jump while the body is on twos [S cgspectrum, above]; the same holds for our cloth and hijab (see R-322: a part that must not jump keeps ones).

## B. Camera design before drawing (R-328..R-333)

- **R-328** A `camera_plan` exists, per shot, before any sketch, art or code is written, and the spec gate refuses without it. Each shot has: id, beat, size (ECU, CU, MCU, MS, WS), angle (eye, low, high, overhead, dutch degrees), lens (mm equivalent, 24 / 35 / 50 / 85, and what it does to depth), move (locked, push, pull, track, pan, tilt, crane, handheld) with start and end framing, duration, and `why` (the feeling or story reason). Source for the questions: Disney Animation layout asks which lens frames a shot best, which angle conveys the right attitude and which camera move expresses the feeling [S https://www.disneyanimation.com/process/layout/].
- **R-329** Order of work for a new episode: script, thumbnails (one per shot, rough, 9:16), shot list (the camera_plan), overhead plan (set, character positions, camera positions, 180 line), animatic with the transitions, and only then sketching. Thumbnails and the overhead plan are files in `work/<episode>/camera/` and linked in the spec. [S https://www.drawstory.ai/blog/what-is-cinematic-storyboard for the thumbnail, panel, animatic order; secondary source]
- **R-330** The camera is motivated by emotion or information, never by "parallax to pass the gate". A push in means growing intent or intimacy; a pull out means isolation or a reveal of space; handheld shake means fear or impact; a locked frame means control or stillness. The `why` field names the emotion. A shot with a move and no `why` fails.
- **R-331** Lens drives depth: wide (24 mm eq.) exaggerates parallax and foreground scale and suits space and unease; normal (35-50 mm) suits dialogue and reaction; long (85 mm and up) flattens and compresses planes and suits intimacy and tension. The spec's `depth_planes[].parallax` spread follows the lens (wide: gaps up to 0.3; long: gaps down to 0.12). [J: basic cinematography, no single source]
- **R-332** Vertical 9:16 composition: the subject's eyes sit on the upper third line of the safe area; headroom is 8 to 12% of the height; use the height for depth stacking (foreground low, subject mid, background up) rather than width; two-shots stack, not side by side; the horizon is set by the emotion (low = open, high = pressed). Faces and key action stay inside the Reels-safe band: the top 250 px and bottom 340 px are reserved for the Instagram UI, and the right 120 px stays clear of key action. Third-party guides give 200-270 px at the top, 400 px or more at the bottom and a safe band near 1080 x 1320-1420; none is an official Meta spec [S https://www.firstpier.com/resources/instagram-ad-safe-zones, https://imagevideofit.com/guides/instagram-reels-safe-zone, https://www.sirency.com/blog/instagram-reels-safe-zone]. Our 340 px bottom reserve is tight against these, so captions and text use 420 px at the bottom until a device test settles it.
- **R-333** Continuity per scene: the 180-degree line, each character's screen direction and the eye-line targets are written in the overhead plan, and a cut that breaks them is declared. The angles, lenses and moves used for each character go to that character's catalogue (F7) so later shots reuse them.

## C. Text legibility (R-334..R-339)

- **R-334** Text sits on its own layer, above every effect: halftone, grain, offset ink, bloom, vignette, light overlays, blur, dust. Draw order is fixed: world, effects, grade, text plate, text, UI-safe check. In-world text (a name on a tag) is a plate: a flat, opaque, effect-free shape inside the object, and the object keeps its look around the plate.
- **R-335** Halftone, grain, hatching and offset ink never cover a text box. The text box plus a margin of 0.5 x the cap height is a knockout region and those effects are masked out of it. Check: the knockout region has a texture energy (local standard deviation after removing the plate mean) at or below 6 of 255 grey levels, measured on the render.
- **R-336** Contrast of text against its effective background (the plate) is at least 4.5:1 below 24 px at 1080 wide and 3:1 for large text (24 px and up, or 18.66 px bold). Aim for 7:1 for Arabic name text, because the final view is a phone in daylight. WCAG 1.4.3 is the reference and covers text over images against the effective background [S https://www.w3.org/TR/WCAG22/, https://webaim.org/articles/contrast/]. Check: the render gate samples the box at every frame the text is visible and uses the 10th-percentile ratio.
- **R-337** Size: no text under 36 px high for anything that must be read, and no sub-line under 28 px. A line the viewer is not meant to read is declared `decor` in the spec and is exempt from R-336 only. In Mix v2 the sub-line was drawn at 13 units under a 0.001 scale (`previews/index.html:1107-1109`), far below legible size on a 1080 px frame. Arabic text uses Thmanyah at weight 700 or heavier, no letter spacing.
- **R-338** Text stays still enough to read: an in-world text object that moves (a swinging tag) moves under 60 px/s and rotates under 8 degrees while the text is meant to be read, for at least the read time (0.6 s + 0.1 s per Arabic word). Otherwise a caption plate carries the text. Read time is declared per text in the spec.
- **R-339** A text plate appears and leaves with its own transition (type, frames), and never during a style bleed or a frame-rate ramp that touches its region.

## How each rule is checked

| Rules | Check | Where | Status |
|---|---|---|---|
| R-320, R-322, R-323, R-327 | spec fields `transitions[]`, `rate_change[]` required for every beat boundary | `tools/quality_gate.py spec` | proposed |
| R-321 | style-strength step per frame under 0.35 outside a cover | `quality_gate.py render`, from a `style_strength` track the renderer writes | proposed |
| R-322 | unique-frame cadence changes only at declared frames | `quality_gate.py render` (frame-diff periodicity) | proposed |
| R-324, R-325 | straight-edge test on the wipe mask, plus a reviewer | spec + frame sheet | proposed |
| R-328..R-331, R-333 | `camera_plan[]` required, with `why`, lens, and files that exist | `quality_gate.py spec` | proposed |
| R-332 | face boxes and text boxes inside the safe band | spec (declared boxes) + render (box sampling) | proposed |
| R-334, R-335 | texture energy in the text box; spec flag `text_layer: "top"` | render gate + spec | proposed |
| R-336..R-338 | contrast, height and dwell measured in the text box | render gate | proposed |
| R-326, R-339 | reviewer against the frame sheet | review | human |

Honest limits: a contrast measure needs the box. Boxes come from the spec (declared by the renderer), not from OCR. Whether a bleed feels motivated is a human call; the gate only proves a cause is declared.
