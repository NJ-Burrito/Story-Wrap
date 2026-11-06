"""Resumable stage engine for tools/shot.py. Every stage writes its output files and records status + input hashes in
<shot-dir>/STATE.json; a rerun skips a finished stage whose inputs (file hashes) did not change (checkpoints are files).
No heavy imports here, so the engine is unit-testable (tools/tests/test_shot_engine.py)."""
from __future__ import annotations
import hashlib, json, time
from pathlib import Path
from typing import Callable

STAGE_ORDER = ["init", "catalogue", "camera", "spec", "build", "trace", "record", "gate", "review"]


class StageFail(Exception):
    """A stage failed on a named check: check is the check id (e.g. 'CAMERA-SHOTS', 'TRANS-COUNT'), message the detail."""
    def __init__(self, check: str, message: str):
        super().__init__(f"[{check}] {message}")
        self.check, self.message = check, message


def sha_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def expand(paths, base: Path) -> list[Path]:
    """Files for a list of paths/dirs/globs (dirs recursive, pycache and dotfiles skipped), sorted."""
    out: list[Path] = []
    for p in paths:
        p = Path(p)
        p = p if p.is_absolute() else base / p
        if p.is_dir():
            out += [q for q in sorted(p.rglob("*")) if q.is_file() and "__pycache__" not in q.parts]
        elif p.is_file():
            out.append(p)
    return out


def hash_inputs(paths, base: Path) -> dict:
    res = {}
    for q in expand(paths, base):
        try:
            res[q.relative_to(base).as_posix()] = sha_file(q)
        except ValueError:
            res[q.as_posix()] = sha_file(q)
    return res


class State:
    def __init__(self, shot_dir: Path):
        self.path = Path(shot_dir) / "STATE.json"
        self.data = json.loads(self.path.read_text(encoding="utf-8")) if self.path.is_file() else {"shot": Path(shot_dir).name, "stages": {}}

    def get(self, name: str) -> dict:
        return self.data["stages"].get(name, {})

    def put(self, name: str, entry: dict):
        self.data["stages"][name] = entry
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)


class Stage:
    """name; inputs(shot_dir) -> list of paths hashed; outputs(shot_dir) -> list of paths that must exist; run(shot_dir) -> dict info."""
    def __init__(self, name: str, inputs: Callable, outputs: Callable, run: Callable, base: Path | None = None):
        self.name, self.inputs, self.outputs, self.run, self.base = name, inputs, outputs, run, base


def is_fresh(stage: Stage, shot_dir: Path, state: State, base: Path):
    """(fresh, current_input_hashes): fresh = recorded ok, same input hashes, every output present."""
    cur = hash_inputs(stage.inputs(shot_dir), base)
    e = state.get(stage.name)
    ok = bool(e) and e.get("status") == "ok" and e.get("inputs") == cur and all(Path(o).exists() for o in stage.outputs(shot_dir))
    return ok, cur


def all_fresh(stages, shot_dir: Path, base: Path) -> bool:
    """True when every stage is recorded ok for the CURRENT input hashes (rig modules, catalogue, render code, shot files) with its outputs present.
    A caller that reuses a finished shot must ask this, not only whether the gate once passed (E01C 2026-10-25: a rig change left stale hands in 8 shots)."""
    state = State(shot_dir)
    return all(is_fresh(st, shot_dir, state, base)[0] for st in stages)


def run_stage(stage: Stage, shot_dir: Path, base: Path, force: bool = False, log=print) -> str:
    """Run one stage honouring the checkpoint. Returns 'ran' or 'skipped'; raises StageFail after recording the failure."""
    state = State(shot_dir)
    fresh, cur = is_fresh(stage, shot_dir, state, base)
    if fresh and not force:
        log(f"[{stage.name}] skipped (inputs unchanged, outputs present)")
        return "skipped"
    t0 = time.time()
    log(f"[{stage.name}] running")
    try:
        info = stage.run(shot_dir) or {}
    except StageFail as e:
        state.put(stage.name, {"status": "failed", "check": e.check, "message": e.message[:2000], "inputs": cur, "at": time.strftime("%Y-%m-%dT%H:%M:%S")})
        raise
    except Exception as e:      # tool error: still recorded, still a stop
        state.put(stage.name, {"status": "failed", "check": "TOOL-ERROR", "message": repr(e)[:2000], "inputs": cur, "at": time.strftime("%Y-%m-%dT%H:%M:%S")})
        raise StageFail("TOOL-ERROR", repr(e)) from e
    # inputs may have been produced during the run (e.g. init creates shot.json): hash again after success
    cur2 = hash_inputs(stage.inputs(shot_dir), base)
    state = State(shot_dir)
    state.put(stage.name, {"status": "ok", "inputs": cur2, "outputs": [Path(o).relative_to(shot_dir).as_posix() if str(o).startswith(str(shot_dir)) else str(o) for o in stage.outputs(shot_dir)],
                           "seconds": round(time.time() - t0, 1), "info": info, "at": time.strftime("%Y-%m-%dT%H:%M:%S")})
    log(f"[{stage.name}] ok ({round(time.time() - t0, 1)} s)")
    return "ran"


def run_all(stages: list[Stage], shot_dir: Path, base: Path, upto: str | None = None, force: bool = False, log=print) -> list[tuple[str, str]]:
    """Run stages in order, stop at the first failure (the StageFail propagates). Returns [(stage, 'ran'|'skipped')]."""
    done = []
    for st in stages:
        done.append((st.name, run_stage(st, shot_dir, base, force=force, log=log)))
        if upto and st.name == upto:
            break
    return done
