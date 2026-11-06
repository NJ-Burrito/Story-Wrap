"""shot.py engine: stage ordering, skip-on-unchanged, failure stop, prerequisite check, camera validation."""
import json
import pytest
import shot
from shotlib.engine import Stage, StageFail, State, run_all, run_stage, STAGE_ORDER, is_fresh
from shotlib import camera


def make(tmp_path, calls, fail_at=None, names=("a", "b", "c")):
    sd = tmp_path / "shotx"; sd.mkdir()
    (sd / "in.txt").write_text("1")
    stages = []
    prev = None
    for n in names:
        def run(d, n=n):
            calls.append(n)
            if n == fail_at:
                raise StageFail("TEST-" + n.upper(), "boom")
            (d / f"{n}.out").write_text(f"{n}:{(d / 'in.txt').read_text()}")
            return {}
        ins = (lambda d, prev=prev: [d / "in.txt"] if prev is None else [d / f"{prev}.out"])
        stages.append(Stage(n, ins, (lambda d, n=n: [d / f"{n}.out"]), run))
        prev = n
    return sd, stages


def test_stage_order_matches_interface():
    assert STAGE_ORDER == ["init", "catalogue", "camera", "spec", "build", "trace", "record", "gate", "review"]
    assert [s.name for s in shot.build_stages(shot.ROOT / "work" / "shots" / "nonexistent")] == STAGE_ORDER


def test_runs_in_order(tmp_path):
    calls = []; sd, st = make(tmp_path, calls)
    assert run_all(st, sd, tmp_path, log=lambda *_: None) == [("a", "ran"), ("b", "ran"), ("c", "ran")]
    assert calls == ["a", "b", "c"]


def test_skip_when_unchanged(tmp_path):
    calls = []; sd, st = make(tmp_path, calls)
    run_all(st, sd, tmp_path, log=lambda *_: None); calls.clear()
    assert [r for _, r in run_all(st, sd, tmp_path, log=lambda *_: None)] == ["skipped"] * 3
    assert calls == []


def test_changed_input_reruns_that_stage_and_downstream_only(tmp_path):
    calls = []; sd, st = make(tmp_path, calls)
    run_all(st, sd, tmp_path, log=lambda *_: None); calls.clear()
    (sd / "in.txt").write_text("2")
    assert [r for _, r in run_all(st, sd, tmp_path, log=lambda *_: None)] == ["ran"] * 3 and calls == ["a", "b", "c"]
    calls.clear()
    (sd / "b.out").write_text("tampered")       # b's output changed -> c (reads b.out) reruns, a and b do not need to
    res = dict(run_all(st, sd, tmp_path, log=lambda *_: None))
    assert res["a"] == "skipped" and res["c"] == "ran"


def test_missing_output_reruns(tmp_path):
    calls = []; sd, st = make(tmp_path, calls)
    run_all(st, sd, tmp_path, log=lambda *_: None); calls.clear()
    (sd / "a.out").unlink()
    assert dict(run_all(st, sd, tmp_path, log=lambda *_: None))["a"] == "ran"


def test_failure_stops_and_is_recorded(tmp_path):
    calls = []; sd, st = make(tmp_path, calls, fail_at="b")
    with pytest.raises(StageFail) as e:
        run_all(st, sd, tmp_path, log=lambda *_: None)
    assert e.value.check == "TEST-B" and calls == ["a", "b"]          # c never ran
    s = State(sd).get("b")
    assert s["status"] == "failed" and s["check"] == "TEST-B"
    assert State(sd).get("a")["status"] == "ok" and State(sd).get("c") == {}


def test_failed_stage_is_not_skipped_next_time(tmp_path):
    calls = []; sd, st = make(tmp_path, calls, fail_at="b")
    with pytest.raises(StageFail):
        run_all(st, sd, tmp_path, log=lambda *_: None)
    calls.clear()
    with pytest.raises(StageFail):
        run_all(st, sd, tmp_path, log=lambda *_: None)
    assert calls == ["b"]                                              # a skipped, b retried


def test_tool_error_becomes_stagefail(tmp_path):
    sd = tmp_path / "s"; sd.mkdir()
    st = Stage("x", lambda d: [], lambda d: [d / "x"], lambda d: 1 / 0)
    with pytest.raises(StageFail) as e:
        run_stage(st, sd, tmp_path, log=lambda *_: None)
    assert e.value.check == "TOOL-ERROR"


def test_upto_stops_early(tmp_path):
    calls = []; sd, st = make(tmp_path, calls)
    run_all(st, sd, tmp_path, upto="b", log=lambda *_: None)
    assert calls == ["a", "b"]


def test_single_stage_needs_fresh_prerequisites(tmp_path, monkeypatch):
    sd = shot.ROOT / "work" / "shots" / "_pytest_prereq"
    sd.mkdir(parents=True, exist_ok=True)
    try:
        (sd / "shot.json").write_text("{}")
        with pytest.raises(StageFail) as e:
            shot.run_pipeline("camera", sd, log=lambda *_: None)
        assert e.value.check == "PREREQ"
        with pytest.raises(StageFail) as e:
            shot.run_pipeline("nope", sd, log=lambda *_: None)
        assert e.value.check == "USAGE"
    finally:
        import shutil; shutil.rmtree(sd, ignore_errors=True)


def test_camera_validation_flags_gap_and_bad_frame_grid():
    shot_cfg = {"fps": 24, "duration_s": 2}
    plan = {"beats": [{"id": "b1", "start": 0, "end": 2}],
            "shots": [dict(shot="s1", beat="b1", t0=0.0, t1=0.9, size="MS", angle="eye", lens_mm=35, move="push", start_frame_desc="a", end_frame_desc="b",
                            why="w", serves_emotion="calm", safe_boxes=[1], catalogue_camera="x", cam0={}, cam1={}, thumbnail="none.svg")],
            "cuts": {}}
    ids = [f.split(" ", 1)[0] for f in camera.validate_plan(plan, shot_cfg, shot.ROOT)]
    assert "CAMERA-FRAMES" in ids and "CAMERA-SHOTS" in ids and "CAMERA-THUMB" in ids


# ---- catalogue files are stage inputs: editing one reruns exactly the stages that depend on it
def _mini_repo(tmp_path):
    root = tmp_path / "repo"
    cdir = root / "catalogue" / "characters" / "hero"
    (cdir / "v4" / "hands").mkdir(parents=True)
    (cdir / "v4" / "hands" / "grip-a.json").write_text('{"k":1}')
    (cdir / "v4" / "hands" / "unused.json").write_text('{"k":9}')
    (cdir / "v1").mkdir()
    (cdir / "v1" / "m.json").write_text("{}")
    (cdir / "pose.json").write_text('{"p":1}')
    (cdir / "index.json").write_text(json.dumps({"entries": [{"id": "hero/pose/x", "version": "1.0", "path": "pose.json"}]}))
    (root / "catalogue" / "environments" / "lab" / "v1" / "locations").mkdir(parents=True)
    (root / "catalogue" / "environments" / "lab" / "v1" / "locations" / "loc.json").write_text("{}")
    (root / "tools" / "render" / "characters").mkdir(parents=True)
    (root / "tools" / "render" / "characters" / "hero.js").write_text("//c")
    (root / "tools" / "render" / "worlds").mkdir()
    (root / "tools" / "render" / "worlds" / "lab.js").write_text("//w")
    sd = root / "work" / "shots" / "t1"
    sd.mkdir(parents=True)
    shotj = {"id": "t1", "world": "lab", "character": "hero", "catalogue": {"model": "v1/m.json", "grip_dir": "v4/hands/", "grips": ["grip-a"]},
             "uses": {"refs": ["hero/pose/x@1.0"]}}
    (sd / "shot.json").write_text(json.dumps(shotj))
    return root, sd


def test_catalogue_input_files_cover_actors_refs_world_and_modules(tmp_path):
    from shotlib import catalogue
    root, sd = _mini_repo(tmp_path)
    names = {p.name for p in catalogue.input_files(json.loads((sd / "shot.json").read_text()), root)}
    assert {"grip-a.json", "m.json", "pose.json", "index.json", "loc.json", "hero.js", "lab.js"} <= names
    assert "unused.json" not in names


def test_editing_a_grip_file_makes_trace_and_later_stages_stale(tmp_path, monkeypatch):
    root, sd = _mini_repo(tmp_path)
    monkeypatch.setattr(shot, "ROOT", root)
    monkeypatch.setattr(shot, "TOOLS", shot.TOOLS)
    stages = {s.name: s for s in shot.build_stages(sd)}
    state = State(sd)
    for name, st in stages.items():            # pretend every stage finished ok with its outputs present
        for o in st.outputs(sd):
            o.parent.mkdir(parents=True, exist_ok=True)
            if not o.exists(): o.write_text("x")
        state.put(name, {"status": "ok", "inputs": __import__("shotlib.engine", fromlist=["hash_inputs"]).hash_inputs(st.inputs(sd), root)})
    fresh = lambda: {n: is_fresh(s, sd, State(sd), root)[0] for n, s in {s.name: s for s in shot.build_stages(sd)}.items()}
    base = fresh()
    assert base["trace"] and base["record"] and base["catalogue"]      # untouched shot: everything skips
    (root / "catalogue/characters/hero/v4/hands/unused.json").write_text('{"k":10}')
    assert fresh() == base                                              # a file the shot does not use changes nothing
    (root / "catalogue/characters/hero/v4/hands/grip-a.json").write_text('{"k":2}')
    after = fresh()
    assert not any(after[n] for n in ("catalogue", "camera", "spec", "build", "trace", "record"))
    assert after["init"]
    (root / "catalogue/characters/hero/v4/hands/grip-a.json").write_text('{"k":1}')
    (root / "tools/render/worlds/lab.js").write_text("//w2")            # world module change is an input too
    assert not fresh()["trace"]


def test_all_fresh_flips_when_a_rig_input_changes(tmp_path):
    """A passed shot is reusable only while every stage input (rig module, render code) is byte-identical (E01C 2026-10-25: stale hands kept as 'cached')."""
    from shotlib.engine import Stage, State, all_fresh, hash_inputs
    sd = tmp_path / "shot"
    sd.mkdir()
    rig, out = tmp_path / "hands.js", sd / "out.txt"
    rig.write_text("v1", encoding="utf-8")
    out.write_text("x", encoding="utf-8")
    st = Stage("build", lambda d: [rig], lambda d: [out], lambda d: {})
    State(sd).put("build", {"status": "ok", "inputs": hash_inputs([rig], tmp_path)})
    assert all_fresh([st], sd, tmp_path)
    rig.write_text("v2 art-book hands", encoding="utf-8")
    assert not all_fresh([st], sd, tmp_path)
