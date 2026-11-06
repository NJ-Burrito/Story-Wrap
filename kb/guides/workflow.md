# Workflow: stage gates

Source: `research/09` section 1 (vendor and primary tool docs, plus our synthesis) and `CLAUDE.md`. Principle: each stage writes a file the next reads; a failed gate sends work back one stage; changes cost more the later they happen [S vendor Pixune]. Writing and the art book are the only stages where a human reads every word; everything after the locked script can be regenerated from files [J].

Models by job (CLAUDE): Haiku does fetching, measuring, bulk edits; Sonnet does analysis, verification and coordination; Opus does the creative writing and drawing.

| # | Stage | Inputs | Outputs | Gate (pass before the next stage) | Rules | Human approval |
|---|---|---|---|---|---|---|
| 0 | Research | Brief, this KB | `research/*.md`, `kb/` | Every number has a URL or measured file; grades applied | R-002, R-003, R-020 to R-023 | Lane summary |
| 1 | World bible | Research | `bible/worlds/<name>.md`, series page | Rules testable; costs, limits, shared power rule; culture reviewed or "pending" | R-041, R-060 to R-062 | World |
| 2 | Characters | World bible | `bible/characters/<name>.md`, `bible/ensemble-matrix.md` | Template complete; matrix passes; all arc types present | R-030 to R-039, R-040 to R-046 | Cast |
| 3 | Story bible and outline | Cast, worlds | `bible/series.md`, `episodes/EP-XX/outline.md` | Spine named; 7 or 8 genres each placed once; tonal range; heart; each episode has goal, turn, ending | R-050 to R-056 | Arc |
| 4 | Script | Outline | `episodes/EP-XX/script.md` with timed beats | Read-aloud fit; hook in first 3 s; no line depends on screen text alone | R-063, R-064 | Script lock |
| 5 | Sketching: art book | Locked script, characters, worlds | `artbook/` B&W ink plates, `artbook/INK-POLICY.md` | Silhouette and thumbnail tests; ink-only; crop test; trait sentence equals bible | R-070 to R-080 | Look (the owner) |
| 6 | Storyboard | Script, art book | `episodes/EP-XX/storyboard/` | Every script beat has a panel and no panel lacks a beat | R-093, R-094 | Boards |
| 7 | Animatic | Storyboard, temp voice, temp music | `animatic.mp4` | Length in band; hook lands; loop works | R-111, R-094 | Timing |
| 8 | Layout | Animatic, art book | Layout files per shot | Matches animatic; safe-zone overlay | R-099 | Layout |
| 9 | Animation | Layout, style decision | Frame sequences or rigs per shot | Declared rates; timing tolerance; holds check | R-090 to R-098 | Shots |
| 10 | Compositing and finish | Animation, backgrounds | Final frames, grade | No banding; upscale and interpolation checked on one shot | R-004, R-005, R-091 | Picture |
| 11 | Sound | Locked script, animatic | Voices, music, effects, mix | Loudness and peaks; audible on a phone speaker | R-112 | Mix |
| 12 | Assembly | Picture, sound | `final.mp4`, caption file, cover | Probe commands in `reels.md` pass | R-110 to R-117 | Publish decision |

## Notes

- Stage order is fixed; stages 1 to 4 are writing and come first. Sketching starts for a piece only when its script is locked (CLAUDE). If the art book needs a character change, go back to stage 2, not forward.
- Rehearsal exception (CLAUDE): when the pipeline is new, one private rehearsal on a throwaway piece is allowed and the owner approves the plan before any full render.
- Run once: one render, one probe pass; on failure report the failing line and stop (R-012).
- Checkpoints are files. Each stage leaves a `.checks.md` listing each rule id, pass/fail and evidence.
- Roles for a small team of one person and agents: writer and story editor; art director; layout and animator (one agent per shot is possible); compositor; sound [J].
- Each asset's `meta.json` records base model and licence (R-004).

## Folder map

`research/` raw lanes; `kb/` this KB; `bible/` worlds, characters, series; `episodes/EP-XX/` outline, script, storyboard, animatic, final; `artbook/` ink plates; `work/` scratch (git-ignored).
