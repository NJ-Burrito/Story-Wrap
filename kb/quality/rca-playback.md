# RCA: live preview stalls and restarts (Mix v3, 2026-10-23)

## Mechanism
A preview that paints each frame live from a function of time (`renderAt(t)`) on a 1080x1920 canvas has no guaranteed frame cost. Mix v3 spent 11-14 `ctx.filter = blur()` passes, two full-frame composite passes and a colour grade per frame. The blur radius is a moving value, so nearly every frame needs a blur the raster backend has not built yet. Cold frames cost 100-280 ms from about 2.9 s and 1-10 s from 4.96 s (the grade crossfade starts at 4.625 s); the same frames cost 10 ms on a second pass. All of it is flushed at one canvas-to-canvas `copy` drawImage (the contrast pass). Playback used the wall clock modulo the duration, so one stall longer than the time left in the loop makes the animation appear to restart. The cause is cost, not an exception: heap flat, no errors.
Evidence: `work/rca/stall/report.md`.

## Construction rule (every future preview)
1. A preview is the recorded video the gate measured (already a project rule), never a live renderer. If a live canvas is unavoidable (an editor), it runs from pre-rasterised frames or layers, not paint-per-frame.
2. No continuously varying `ctx.filter` blur, no full-frame composite pass and no `drawImage(ctx.canvas)` self-copy in a per-frame path. Quantise blur radii to a small fixed set, bake blurred shadow shapes once into sprites, apply the grade as a baked LUT or a compositor layer.
3. The playback clock never jumps: advance from a frame counter, hold the last frame when late, never derive position from `(now - t0) % duration` after a gap.
4. Warm before showing: render or decode every frame once off screen behind a loading state, then play.

## Proposed gate check (preview gate)
Script a full playthrough in the target browser with the flags a user has (GPU on), from a cold load, two loops, in a foreground window (a background window throttles rAF to 1 Hz and voids the check):
- frame times from `requestAnimationFrame` timestamps and the render call: p99 <= 50 ms, max <= 100 ms;
- `PerformanceObserver('longtask')`: no task > 100 ms;
- no uncaught exception and no console error from the page;
- displayed time is monotonic inside a loop and wraps exactly once per DUR;
- cold p50 within 2x of warm p50 (a larger gap means first-use costs that will stall).
Any failure blocks publishing the preview.
