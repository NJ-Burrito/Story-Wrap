# Story-Wrap knowledge base

Built 2026-10-22 from `research/01..10` by the Sonnet analysis agent, after a verification pass (see "Evidence grades"). This KB is for agents: precise, operational, checkable. the owner's gallery is `artbook/`, not this folder.

## Stage order (fixed)

research -> writing -> sketching -> animating -> composing episodes. Inside animating, a shot runs `init, catalogue, camera, spec, build, trace, record, gate, review` (`../pipelines/RUNBOOK.md`). A stage starts only when the stage before it is finished for that piece. A failed gate sends work back one stage. Gates, inputs and outputs: `guides/workflow.md`.

## Index

| File | Use it when |
|---|---|
| `rulebook.md` | Always. One list of rules grouped by stage (writing, catalogue, camera, spec, build, record, gate, review, preview). Each rule has its why and its check id or "human look". Section 15 is the calm format (R-403 to R-426). Numbers never change; retired rules say `retired -> R-xxx`. |
| `../bible/craft/README.md` | Before building any shot: DO and NEVER checklist per stage, and the table of past failures F1 to F15 and C1 to C13 with root cause, rule and check. |
| `../bible/craft/calm-format.md` | Making a calm-format episode: DO and NEVER for pacing, intros, narrator, captions, sound and the choice, each with its reason and note (C1 to C13). |
| `../pipelines/CALM.md` | Running the calm pipeline end to end (E01 calm v5, the approved reference): every step with inputs, outputs, gates, the cheap check to run before each expensive step, and the note that created it. |
| `../pipelines/WRITING.md` | Writing a series bible: folder layout, step order, who does it, the `tools/bible_check.py` checks, the owner's read. |
| `../pipelines/RUNBOOK.md` | Running a shot: `uv run tools/shot.py <stage> <shot-dir>`, stage by stage, who does it, what must pass, what to do on failure, how the owner is shown work. |
| `../pipelines/VOICE.md` | Voicing an episode: casting, manifest, gate, the one take, visemes for lip sync (`uv run tools/voice.py`). |
| `../pipelines/COMPOSE.md` | Composing an episode: the premium path (`uv run tools/compose.py`, `EP-*` gate) and the calm path (`tools/calm_compose.py`, captions, phone-first mix, sound design); steps in `CALM.md`. |
| `../pipelines/AUDIENCE.md` | After an episode passes every gate: posting it, the 12 h comment harvest, the vote tally, the next-episode brief (`uv run tools/ig.py`, `tools/vote.py`, vote by wording; API facts in `../research/instagram-api.md`). |
| `../pipelines/ARTBOOK.md` | Sketch stage: bible to character module to sheets to the Art Book tab to the owner's read; roles, checks (`uv run tools/artbook.py check`). |
| `../pipelines/HEAL.md` | A build fails a gate or the critic: the healing loop (gate, critic, classify, fix, rerun, learn), limits in `pipelines/heal.json`, when the owner is shown work. Questions: `quality/critic-checklist.md`; fixes: `quality/heal-playbooks.md`; memory: `lessons/ledger.jsonl` (`uv run tools/heal.py`). |
| `../bible/README.md` | Where the series bible, craft bible, culture briefs, catalogue, feedback and ideas live, and how they relate. |
| `quality/gate-spec.md`, `quality/root-causes.md`, `quality/rca-*.md` | The gate: thresholds, calibration, and why each check exists. Owned by the pipeline agent. |
| `style-decision.md` | the owner picks the final look (2 options). |
| `open-questions.md` | Before starting any stage: what is still unknown and what it blocks. |
| `guides/workflow.md` | Planning a piece; stage gates. |
| `guides/character-writing.md`, `guides/character-design.md` | Writing a cast; turning a profile into ink. |
| `guides/genres.md`, `guides/genre-blending.md` | Choosing and blending the top 10 genres. |
| `guides/worldbuilding.md` | Writing worlds. |
| `guides/drawing.md` | Sketch stage (ink, black and white). |
| `guides/art-styles.md` | Reconciled top 10 styles, matrix, Arcane. |
| `guides/animation.md` | Animating stage. |
| `guides/reels.md` | Market facts, episode shape, measured benchmark of 4 reels. |
| `guides/gpu-pipeline.md` | Tools, licences, VRAM, CPU-sparing flags. |
| `templates/*.md` | Copy into `bible/` or `artbook/` and fill in. |

## How an agent uses the KB

1. Read `CLAUDE.md`, then `handoff.md`, then `rulebook.md` (your stage's section), then the guide for your stage. For a shot, read `../bible/craft/README.md` and `../pipelines/RUNBOOK.md` first.
2. Copy the matching template into `bible/` (writing) or `artbook/` (sketching). Never write into `kb/`.
3. Before handing off, run every rule of your stage in `rulebook.md`: gate checks by their command, `human look` rules by the review stage. Record pass/fail in a checks file next to your output (`<output>.checks.md`).
4. If a rule cannot be checked or a fact is missing, report it to the Lead for `open-questions.md`; do not guess.
5. Link to `research/NN-*.md` for the full evidence; the KB only distils.

## Evidence grades (used on every claim)

- **[V url]** Verified: a primary page, or a fetched dated source, read in the 2026-10-22 verification pass. Fetch tools return summaries, so open the page before quoting it in public.
- **[S url]** Secondary: press, vendor, or a single search snippet. Usable for planning, not for public claims.
- **[M]** Measured by us (files in `work/`, commands in `research/10`).
- **[J]** Judgement: our reasoning or scoring. Never presented as data.

## Corrections the verification pass made to the raw research

- Depth Anything V2 Base and Large are **CC-BY-NC-4.0** (non-commercial); only **Small is Apache-2.0** [V https://huggingface.co/depth-anything/Depth-Anything-V2-Base-hf]. Use Small only.
- SDXL base: the card says "research purposes only", but the RAIL++-M LICENSE.md grants royalty-free use and allows hosting, subject to use restrictions in Attachment A, which was not read in full [V https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/blob/main/LICENSE.md]. Status: probably allowed, read Attachment A first (Q-02).
- xinsir **lineart** licence is still unverified (HTTP 401); **scribble** is Apache-2.0 [V https://huggingface.co/xinsir/controlnet-scribble-sdxl-1.0]. Use scribble until lineart is read.
- Bluey 2024: Nielsen gives 55.62 billion US minutes [S https://thedesk.net/2025/01/nielsen-most-streamed-tv-movies-2024/], replacing R03's "50 billion Disney+ minutes" (weaker source, different metric).
- Across the Spider-Verse: $690.8M worldwide is the verified total [V https://www.the-numbers.com/movie/Spider-Man-Across-the-Spider-Verse-%282023%29]; R04's $506M was a mid-run snapshot.
- Arcane technique (missing in R03/R04): 3D models with hand-painted textures, hand-drawn 2D effects at 12 fps, characters and environments at 24 fps [S https://redsharknews.com/why-netflixs-arcane-looks-so-good-how-fortiche-ramped-up-the-animation-pipeline].
- Instagram: the 3-minute cap, ranking signals and the 30-60 s tip are secondary only; no primary Instagram page was reached. Safe-zone numbers are unverified.

Production crew (who does which stage, all Sonnet 5.5): [../pipelines/CREW.md](../pipelines/CREW.md)
