"""Story-Wrap quality gate, part 2: merged spec checks (R-300..R-379), rig-trace checks and render extras.

Pure functions, numpy only (scipy/PIL imported lazily). Imported by tools/quality_gate.py; unit-tested in tools/tests/.
Every failure string is "FAIL [CHECK-ID] message"; the check ids are listed in kb/quality/gate-spec.md.
Calibration status per check: CALIBRATED = derived from a measured sample, DEFAULT = judgement default [J] not yet
calibrated on real renders (see CHECK_STATUS and gate-spec.md).
"""
from __future__ import annotations

# --- the body of this module lives in qg_checks_parts/p01..p04.py, run in THIS namespace in order, so every global,
# --- monkeypatch (`qg_checks.X = ...`) and `__file__` behaves as in the single file this was split from.
import pathlib as _pl
for _f in ('p01.py', 'p02.py', 'p03.py', 'p04.py'):
    _p = _pl.Path(__file__).resolve().parent / "qg_checks_parts" / _f
    exec(compile(_p.read_text(encoding="utf-8"), str(_p), "exec", flags=annotations.compiler_flag, dont_inherit=True), globals())
del _pl, _f, _p

