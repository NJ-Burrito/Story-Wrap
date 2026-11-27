# /// script
# requires-python = ">=3.11"
# dependencies = ["playwright", "pillow", "numpy", "scipy"]
# ///
"""Calm-format composing (owner, 2026-10-24, CLAUDE.md "Calm format"): the finished shots, the wrapper cards, ONE narrator, big word-by-word captions
and a HUD become one Reel. Not a replacement for tools/compose.py (the E01 premium path); this is the calm path the daily pipeline uses.

  uv run tools/calm_compose.py plan     <ep>   calm-plan.json + voice takes -> work/calm/<ep>/timeline.json (scene lengths come from the takes)
  uv run tools/calm_compose.py captions <ep>   word timing from each take's energy (numpy, no model) -> the FULL sentence (2 lines at most) with the spoken word highlighted + HUD plates
  uv run tools/calm_compose.py audio    <ep>   phone-first mix (tools/calm_mix.py): cleaned voices, a pad bed, sfx at dialogue-relative levels, voice-driven ducking, -14 LUFS -> mix.wav + audio/stems/
  uv run tools/calm_compose.py assemble <ep>   shots + wrapper cards with soft joins, plates, mix, NVENC -> episode.mp4
  uv run tools/calm_compose.py gate     <ep>   calm episode checks (declared data + the calm bands of qg_checks) -> gate.json
  uv run tools/calm_compose.py all      <ep>

<ep> is an episode id (E02). Plan: bible/series/<series>/episodes/<ep>/calm-plan.json (schema in pipelines/DAILY.md); script: .../script.json (voice.py lines);
takes: work/voice/<ep>/<line>.trimmed.wav; shots: work/shots/<ep>-<scene>/out/<ep>-<scene>.mp4; cards: work/shots/<ep>-<card>/out/<ep>-<card>.mp4.
Outputs: work/episodes/<ep>/ (where ig.py looks: episode.mp4, gate/report.json, heal/critic.json). Exit 0 ok, 1 a check failed (`FAIL [ID] message`), 2 usage. GPU first (NVDEC/NVENC), ffmpeg -threads 2, no network, no model.
"""
from __future__ import annotations

# --- the body of this module lives in calm_compose_parts/p01..p03.py, run in THIS namespace in order, so every global,
# --- monkeypatch (`calm_compose.X = ...`) and `__file__` behaves as in the single file this was split from.
import pathlib as _pl
for _f in ('p01.py', 'p02.py', 'p03.py'):
    _p = _pl.Path(__file__).resolve().parent / "calm_compose_parts" / _f
    exec(compile(_p.read_text(encoding="utf-8"), str(_p), "exec", flags=annotations.compiler_flag, dont_inherit=True), globals())
del _pl, _f, _p

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
