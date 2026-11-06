# Style decision for the final animation (the owner decides)

Brief (CLAUDE.md): premium, high resolution, depth, HDR-grade light; Reels 9:16; RTX 2060 6 GB, i5-10400; extreme and different cast; the black-and-white ink art book must share its line with the final look. Evidence: `guides/art-styles.md`, `guides/animation.md`, `guides/gpu-pipeline.md`.

## Common to both options

- Line and flat-colour base drawn from the ink art book (ink-native, cheapest to keep consistent). [J]
- Premium comes from light, depth and grade, not from the line: layered art, a depth map (Depth Anything V2 **Small** only, Apache-2.0 [V https://huggingface.co/depth-anything/Depth-Anything-V2-Small-hf]), a parallax camera, one deliberate light plan per scene. [J]
- "HDR-grade" is an SDR grade with a tone curve. The Instagram files we measured are 8-bit SDR class VP9 at 1080x1920 30 fps [M research/10]. No sourced HDR grading tool exists yet (Q-06).
- Premium-corporate easing and kinetic type for titles and captions: precise ease curves, one idea per screen. [J, from R02 s3.2]
- Duplicated frames for stepped rhythm; RIFE only on shots where smoothness is the goal. [J, from R02]

## Option A: "Clear-line depth" (recommended starting point)

Ligne claire (even line, flat colour, composed backgrounds) plus webtoon vertical pacing (one beat per vertical frame, expressive faces, speed lines), 2.5D parallax, 24 fps drawn on twos (12 drawings a second, frames duplicated), halftone only as a rare accent.

| Trade-off | Detail |
|---|---|
| For | Ink-native: B&W score 5 for both parents [J, art-styles.md]; flat fills and clean line are the most AI-friendly and consistent on a small GPU [S research/04]; lowest render load; art book and final share one line. |
| Against | Reads flat unless light and depth are done well (premium risk). Ligne claire has thin animation evidence [S research/04]. Characters differ by design only, not by motion. |
| Cost | Lowest. One frame size, one rate. |
| Risk control | Light plan per scene; depth layers with real separation; parallax tested on one shot first. |

## Option B: "Halftone mixed-rate" (Spider-Verse inspired)

Same ink base, but each character gets a declared frame rate (ones, twos, threes, fours) as a motion signature; a halftone/offset layer on emotional beats and fast moves; line that takes light; rate jumps as story events.

| Trade-off | Detail |
|---|---|
| For | Highest project-fit sum (24) and distinctiveness 5 [J]. Frame rate per character serves "no two characters alike". Proven premium: Oscar for Into the Spider-Verse [S research/04]; Across the Spider-Verse grossed $690.8M [V https://www.the-numbers.com/movie/Spider-Man-Across-the-Spider-Verse-%282023%29]. |
| Against | Labour: Hobie needed multiple rigs and a custom tool (StepSets) [S https://beforesandafters.com/2023/06/17/the-across-the-spider-verse-spider-punk-character-hobie-was-animated-with-different-frame-rates-fo]; production note of about a week per second of footage [S Slashfilm via research/02]. "On twos everywhere" is contested (Q-08). Halftone mechanics are unverified [S Kottke via research/02]. Halftone on every shot becomes wallpaper. |
| Cost | Higher: per-character timing plans, overlay shader, more checks. |
| Risk control | At most two frame rates in a shot; halftone only on named beats; one rehearsal shot before any series commitment. |

## Lead's reading (judgement, not a decision)

Start with Option A as the production base. Adopt Option B's per-character frame rate as an opt-in layer for the 2 or 3 most extreme characters once Option A's pipeline has delivered one episode. That keeps one pipeline while testing whether motion signature is worth its labour. the owner may instead choose B outright, or approve one private rehearsal of both on a throwaway shot (allowed once by CLAUDE.md "Rehearsal").

## Decisions needed from the owner

1. A, B, or A with B as opt-in.
2. Colour: full colour from the start, or a limited palette per episode (cost lever). Colour is not decided anywhere yet.
3. Whether to run the one private rehearsal on both options.
