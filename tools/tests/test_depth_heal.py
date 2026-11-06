"""DEPTH-HEAL (the owner 2026-10-30, R-504): a calm shot that fails only a depth gate is re-layered (a longer dolly plus a slight drift, then the near tags), gated again, and never parks the
episode. The E05 case: E05-s01 measured parallax_corr = 0.063 against the unchanged gate >= 0.10 (the other 15 shots of the episode: 0.107 to 0.461). No model, no browser, no network."""
import json
from types import SimpleNamespace

import autopilot as ap
import calm_compose as cc
import daily
import depth_heal as DH
import quality_gate as QG
from test_daily import ctx_for, mk_root

NOW = ap.dt.datetime(2026, 10, 30, 18, 0)


def report(sd, depth=("parallax_corr",), other=(), pc=0.063):
    """A shot's gate report as shot.py writes it (gate/report.json + gate/render.json)."""
    g = sd / "gate"
    g.mkdir(parents=True, exist_ok=True)
    gates = {n: {"verdict": "PASS", "fail_ids": []} for n in ("spec", "rig", "hands", "extras", "look2d", "preview", "render")}
    gates["render"] = {"verdict": "FAIL" if depth else "PASS", "fail_ids": list(depth)}
    for i in other:
        gates["rig"] = {"verdict": "FAIL", "fail_ids": [i]}
    (g / "report.json").write_text(json.dumps({"shot": sd.name, "verdict": "FAIL" if depth or other else "PASS", "gates": gates}), encoding="utf-8")
    (g / "render.json").write_text(json.dumps({"parallax_corr": pc, "depth_bands": 4.9, "motion_coverage": 0.24}), encoding="utf-8")


class LogCtx(SimpleNamespace):
    def log(self, *a):
        self.lines.append(" ".join(str(x) for x in a))


def lctx(root, ep="E05"):
    return LogCtx(root=root, ep=ep, lines=[])


def test_the_depth_ids_are_exactly_the_depth_gates():
    assert set(DH.DEPTH_IDS) == {k for k, *_ in QG.DEPTH_GATES}
    assert next(t for k, _, t, _ in QG.DEPTH_GATES if k == "parallax_corr") == 0.10            # the gate is not what the heal changes


def test_the_rungs_only_lengthen_the_dolly_and_stay_inside_the_calm_band():
    pushes = [r["push"] for r in DH.RUNGS]
    assert pushes == sorted(pushes) and pushes[0] > 3.0 and pushes[-1] <= 8.0            # E01C's liked inserts push 7 %; CALM-CAMERA allows < 40 %
    assert all(r.get("span", 0) <= 0.03 for r in DH.RUNGS)                              # calm.py num(q, "span", .., 0.0, 0.03)


def test_overlay_raises_but_never_lowers_and_leaves_locked_and_depth_inserts_alone(tmp_path):
    rec = {"shots": {"E05-s01": {"rung": 1}, "E05-s02": {"rung": 2}}}
    prm = {"character": "hero", "push": "3", "x_near": "1"}
    out = DH.overlay(rec, "E05-s01", "push_in", prm)
    assert float(out["push"]) == DH.RUNGS[0]["push"] and float(out["span"]) == DH.RUNGS[0]["span"] and prm["push"] == "3"       # a copy
    assert DH.overlay(rec, "E05-s01", "push_in", {"push": "9"})["push"] == "9"                                                  # the plan asked for more: kept
    assert DH.overlay(rec, "E05-s02", "push_in", prm)["x_near"] == "1"
    assert DH.overlay(rec, "E05-s03", "push_in", prm) is prm                                                                     # no rung recorded
    assert DH.overlay(rec, "E05-s01", "insert_depth", prm) is prm                                                                # already the depth cure
    assert DH.overlay(rec, "E05-s01", "push_in", {**prm, "locked": "the lamp"}) is not None and "span" not in DH.overlay(rec, "E05-s01", "push_in", {**prm, "locked": "the lamp"})


def test_curable_only_when_a_depth_gate_is_the_only_failure(tmp_path):
    sd = tmp_path / "E05-s01"
    rec = DH.load(tmp_path, "E05")
    report(sd)
    assert DH.curable(sd, "push_in", {}, rec, "E05-s01")
    report(sd, other=("RIG-SEAM",))
    assert not DH.curable(sd, "push_in", {}, rec, "E05-s01")                       # a rig fault is not a camera matter
    report(sd, depth=())
    assert not DH.curable(sd, "push_in", {}, rec, "E05-s01")
    report(sd)
    assert not DH.curable(sd, "insert_depth", {}, rec, "E05-s01") and not DH.curable(sd, "push_in", {"locked": "x"}, rec, "E05-s01")


def test_a_rung_that_passes_heals_the_shot_and_is_remembered(tmp_path):
    sd = tmp_path / "work" / "shots" / "E05-s01"
    report(sd)
    seen = []
    def attempt(p):
        seen.append(p)
        report(sd, depth=(), pc=0.14) if len(seen) == 1 else None
        return len(seen) == 1
    ctx = lctx(tmp_path)
    assert DH.cure(ctx, "E05-s01", "push_in", {"push": "3"}, sd, attempt) is True
    assert len(seen) == 1 and float(seen[0]["push"]) == DH.RUNGS[0]["push"]
    rec = DH.load(tmp_path, "E05")
    st = rec["shots"]["E05-s01"]
    assert st["rung"] == 1 and st["history"][0]["ok"] is True and st["history"][0]["before"]["parallax_corr"] == 0.063 and st["history"][0]["after"]["parallax_corr"] == 0.14
    assert not st.get("exhausted") and DH.heal_possible(tmp_path, "E05")
    again = DH.overlay(rec, "E05-s01", "push_in", {"push": "3"})                    # the next run resolves the shot with the same rung (the cache then holds)
    assert float(again["push"]) == DH.RUNGS[0]["push"]


def test_rounds_are_bounded_per_run_and_per_shot_and_the_stop_then_stands(tmp_path):
    sd = tmp_path / "work" / "shots" / "E05-s01"
    n = []
    def attempt(p):
        n.append(1)
        report(sd, pc=0.07)
        return False
    ctx = lctx(tmp_path)
    report(sd)
    assert DH.cure(ctx, "E05-s01", "push_in", {"push": "3"}, sd, attempt) is False
    assert len(n) == min(DH.ROUNDS_PER_RUN, len(DH.RUNGS))
    if len(DH.RUNGS) > DH.ROUNDS_PER_RUN:
        assert DH.heal_possible(tmp_path, "E05")                                   # a later run still has a rung left
        assert DH.cure(ctx, "E05-s01", "push_in", {"push": "3"}, sd, attempt) is False
    assert len(n) == len(DH.RUNGS)
    assert not DH.heal_possible(tmp_path, "E05") and DH.load(tmp_path, "E05")["shots"]["E05-s01"]["exhausted"] is True
    assert DH.cure(ctx, "E05-s01", "push_in", {"push": "3"}, sd, attempt) is False and len(n) == len(DH.RUNGS)       # nothing more is ever tried


def test_a_non_depth_failure_is_not_waited_for(tmp_path):
    sd = tmp_path / "work" / "shots" / "E05-s01"
    report(sd, depth=(), other=("RIG-SEAM",))
    assert DH.cure(lctx(tmp_path), "E05-s01", "push_in", {}, sd, lambda p: (_ for _ in ()).throw(AssertionError("must not run"))) is False
    assert not DH.heal_possible(tmp_path, "E05")


def test_every_round_is_a_lessons_ledger_entry(tmp_path):
    sd = tmp_path / "work" / "shots" / "E05-s01"
    report(sd)
    DH.cure(lctx(tmp_path), "E05-s01", "push_in", {"push": "3"}, sd, lambda p: (report(sd, depth=(), pc=0.12), True)[1])
    led = [json.loads(x) for x in (tmp_path / "kb" / "lessons" / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(led) == 1 and led[0]["source"] == "depth-heal" and led[0]["fault"] == "parallax_corr" and "E05-s01" in led[0]["summary"] and "passes" in led[0]["summary"]


# ------------------------------------------------------------------ the autopilot does not call the stop terminal or stuck
def stopped(root, text="1 shot(s) failed their gates: E05-s01: FAIL FAIL [parallax_corr] gate failed: render:parallax_corr", code="SHOT-GATE", ep="E05"):
    d = root / "work" / "daily" / ep
    d.mkdir(parents=True, exist_ok=True)
    (d / "STOPPED.md").write_text(f"# stopped\n\n`FAIL [{code}]` {text}\n", encoding="utf-8")


def test_a_depth_stop_is_heal_pending_until_the_rungs_are_spent(tmp_path):
    stopped(tmp_path)
    st = ap.load_state(tmp_path)
    st["attempts"]["E05"] = {"date": "2026-10-30", "n": 4, "last_code": "SHOT-GATE", "at": "2026-10-30T17:30:00"}        # the state E05 was parked in
    assert ap.depth_heal_pending(tmp_path, "E05") and ap.heal_pending(tmp_path, "E05", NOW)
    assert ap.record_failure(tmp_path, st, "E05", 1, NOW) is False and st["attempts"]["E05"]["n"] < ap.MAX_ATTEMPTS
    rec = DH.load(tmp_path, "E05")
    rec["shots"]["E05-s01"] = {"rung": len(DH.RUNGS), "history": [], "exhausted": True}
    DH.save(tmp_path, "E05", rec)
    assert not ap.heal_pending(tmp_path, "E05", NOW) and ap.record_failure(tmp_path, st, "E05", 1, NOW) is True        # then it is the Lead's
    stopped(tmp_path, text="E05-s02: FAIL [RIG-SEAM] x")
    assert not ap.depth_heal_pending(tmp_path, "E05")                                                                    # another shot fault is not a depth one
    stopped(tmp_path, code="CRITIC-LOW", text="parallax_corr")
    assert not ap.depth_heal_pending(tmp_path, "E05")


# ------------------------------------------------------------------ daily.s_shots: the heal is in the stage, only the failing shot is rendered again
def shots_world(tmp_path, monkeypatch, results):
    """One scene shot through the real s_shots with the template, the browser and the gates replaced; `results` = pass/fail of each `shot.py all` call in order."""
    import calm
    root = mk_root(tmp_path, "E05")
    ep_dir = root / "bible" / "series" / "series" / "episodes" / "E05"
    plan = {"scenes": [{"id": "s01", "template": "push_in", "params": {"character": "hero", "push": "3"}}]}
    tl = {"items": [{"id": "s01", "kind": "scene", "shot": "E05-s01", "dur": 4.375, "t0": 0, "voice_t0": 0.2}]}
    fake = SimpleNamespace(plan_p=ep_dir / "calm-plan.json", timeline_p=root / "work" / "episodes" / "E05" / "timeline.json", script_p=ep_dir / "script.json")
    fake.timeline_p.parent.mkdir(parents=True, exist_ok=True)
    fake.plan_p.write_text(json.dumps(plan), encoding="utf-8")
    fake.timeline_p.write_text(json.dumps(tl), encoding="utf-8")
    fake.script_p.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(cc, "Ep", lambda e, r: fake)
    resolved = []
    monkeypatch.setattr(calm, "resolve", lambda tpl, prm: (resolved.append(dict(prm)), {"template": tpl, "actors": [{"id": "hero"}], "prm": dict(prm)})[1])
    monkeypatch.setattr(calm, "validate_calm", lambda c: [])
    monkeypatch.setattr(calm, "set_lipsync", lambda c, e: None)
    monkeypatch.setattr(calm, "lipsync_entry", lambda *a, **k: {})
    monkeypatch.setattr(calm, "write_shot", lambda c, sd: (sd.mkdir(parents=True, exist_ok=True), (sd / "calm.json").write_text(json.dumps({**c, "id": sd.name}, sort_keys=True), encoding="utf-8")))
    monkeypatch.setattr(daily, "shot_inputs_fresh", lambda sd: True)
    runs = []
    def sh(cmd, *, label, timeout=None, machine=True):
        ok = results[len(runs)]
        runs.append(label)
        sd = root / "work" / "shots" / "E05-s01"
        report(sd, depth=() if ok else ("parallax_corr",), pc=0.15 if ok else 0.06)
        if ok:
            rep = json.loads((sd / "gate" / "report.json").read_text(encoding="utf-8"))
            rep["verdict"] = "PASS"
            (sd / "gate" / "report.json").write_text(json.dumps(rep), encoding="utf-8")
        return SimpleNamespace(returncode=0 if ok else 1, stdout="" if ok else "FAIL [parallax_corr] gate failed: render:parallax_corr\n", stderr="")
    ctx = ctx_for(root, "E05")
    ctx.sh = sh
    return ctx, root, runs, resolved


def test_s_shots_heals_a_depth_failure_in_the_stage_and_keeps_the_rung(tmp_path, monkeypatch):
    ctx, root, runs, resolved = shots_world(tmp_path, monkeypatch, [False, True])
    out = daily.s_shots(ctx)
    assert out["results"] == {"s01": "ok"} and len(runs) == 2                                  # the failing shot only, twice
    assert float(resolved[-1]["push"]) == DH.RUNGS[0]["push"] and resolved[0]["push"] == "3"
    assert DH.load(root, "E05")["shots"]["E05-s01"]["rung"] == 1
    runs.clear(); resolved.clear()
    out = daily.s_shots(ctx)                                                                   # a later run resolves the shot with its rung: the passed shot is cached
    assert out["results"] == {"s01": "cached"} and not runs and float(resolved[-1]["push"]) == DH.RUNGS[0]["push"]


def test_s_shots_stops_with_shot_gate_when_every_rung_fails(tmp_path, monkeypatch):
    ctx, root, runs, resolved = shots_world(tmp_path, monkeypatch, [False] * 10)
    try:
        daily.s_shots(ctx)
        raise AssertionError("must stop")
    except daily.StageFail as e:
        assert e.code == "SHOT-GATE" and "parallax_corr" in e.msg
    assert len(runs) == 1 + min(DH.ROUNDS_PER_RUN, len(DH.RUNGS))
