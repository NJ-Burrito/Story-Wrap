# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "scipy"]
# ///
"""Voice stage: manifest -> gate -> voice (ONE take per line) -> visemes.

    uv run tools/voice.py casting [--series series]
    uv run tools/voice.py manifest <episode-dir>
    uv run tools/voice.py measure <episode-dir> [--work <take-dir>]   # fill seconds/raw_seconds from existing takes
    uv run tools/voice.py gate     <episode-dir> [--full]
    uv run tools/voice.py voice    <episode-dir> [--go] [--no-breath] [--inhale] [--resume | --rejoin]   (breath segmentation on by default; Chatterbox Multilingual, local GPU; dry run without --go)
    uv run tools/voice.py status   <episode-or-work-dir>     (per line: taken / not-taken / blocked-after-start)
    uv run tools/voice.py repair   <work-dir> --reason "<error>"   (old logs: started-only lines -> not-taken)
    uv run tools/voice.py trim     <in.wav> <out.wav> [--role narrator|dialogue] [--no-master]   (offline end-trim + the mastering chain; no model)
    uv run tools/voice.py refcheck <ref.wav> [provenance.json]   (REF-QUALITY of a reference clip; `casting` and `voice` enforce it)
    uv run tools/voice.py supersede <episode-dir> --speaker <id> --reason "<why>"   (a BANNED voice's takes move aside; the new voice then voices those lines once)
    uv run tools/voice.py refit-mark <episode-dir> --old H01 --new H01r1 --reason "<why>"   (a line too long for its slot was reworded under a NEW id, tools/line_refit.py, R-502: only the new id is voiced, once)
    uv run tools/voice.py visemes  <episode-dir>

Engine = Chatterbox Multilingual (owner, 2026-10-24): local, GPU, MIT, one take per line, no ASR, no other model.
Google Gemini is BANNED (owner, 2026-10-23, permanent): any other engine is refused (VOICE-BANNED); no code here calls a network.
Every take is end-trimmed offline (energy + spectral flatness, no model) and checked by VOICE-TAIL, then goes through the ONE mastering
chain (tools/voice_master.py, numbers in tools/sound_profile.json; the owner 2026-10-26) and is checked by VOICE-MASTER. The raw take stays
as <id>.wav; the finished take is <id>.trimmed.wav with its report in <id>.trimmed.master.json. STORYWRAP_VOICE_MASTER=0 turns the chain off (tests).
Casting voice names are retired Gemini names (status "retired"); the engine voice is the reference clip per character.
Exit 0 = ok, 1 = a check failed (`FAIL [ID] message`), 2 = usage or tool error. Pipeline text: pipelines/VOICE.md.
"""
from __future__ import annotations

# --- the body of this module lives in voice_parts/p01..p04.py, run in THIS namespace in order, so every global,
# --- monkeypatch (`voice.X = ...`) and `__file__` behaves as in the single file this was split from.
import pathlib as _pl
for _f in ('p01.py', 'p02.py', 'p03.py', 'p04.py'):
    _p = _pl.Path(__file__).resolve().parent / "voice_parts" / _f
    exec(compile(_p.read_text(encoding="utf-8"), str(_p), "exec", flags=annotations.compiler_flag, dont_inherit=True), globals())
del _pl, _f, _p

if __name__ == "__main__":
    sys.exit(main())
