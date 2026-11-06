"""READ-HEAL (the owner 2026-10-30, R-503): the animatic's reading-time findings are fed back to the plan, so an estimate that was too small never parks an episode.
The E05 case: L06 «كرسيي هذا!» (10 characters, the FIRST sentence of a three-sentence line) was up 1.23 s, the least is max(1.5, chars / 12) = 1.50 s; the plan's pause after the scene
(read_hold) cannot reach a sentence in the middle of a take, the silence BEFORE the voice (lead_hold) can. No model, no browser, no network."""
import json
import wave

import pytest

import autopilot as ap
import calm_compose as cc
import cap_sentence as CS
import daily
import read_heal as RH
from test_daily import ctx_for, mk_root, plan_ok, script_ok

pytestmark = pytest.mark.usefixtures("neutral_project")      # the plan checks read the neutral fixture project, not a user's own series

L06 = "كرسيي هذا! نصف فتيلة لكل ساعة جلوس. سارو؟"
# seconds inside the take, per word: the first sentence is two quick words, the second starts 1.17 s after the first word began
WORD_T = [(0.24, 0.70), (0.70, 1.15), (1.41, 1.80), (1.80, 2.20), (2.20, 2.60), (2.60, 3.00), (3.00, 3.40), (3.80, 4.40)]


def wav(path, seconds):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(16000)
        w.writeframes(b"\x00\x00" * int(16000 * seconds))


def e05_like(tmp_path):
    """An episode whose scene s2 speaks L06 and is followed by s2 (so the line has a next voice), with the plan stage's real arithmetic."""
    root = mk_root(tmp_path)
    ed = root / "bible" / "series" / "series" / "episodes" / "E02"
    p, s = plan_ok(), script_ok()
    s["lines"][1].update({"text": L06, "tts_text": L06})
    (ed / "calm-plan.json").write_text(json.dumps(p, ensure_ascii=False), encoding="utf-8")
    (ed / "script.json").write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")
    for lid in ["H1"] + [f"L{i}" for i in range(1, 6)]:
        wav(root / "work" / "voice" / "E02" / f"{lid}.trimmed.wav", 4.6 if lid == "L2" else (2.0 if lid == "H1" else 3.0))
    return root, ed, s


def states_for(root, s, lead_hold, monkeypatch, tmp_path):
    """caption_states of the L1 scene with scripted word widths and word times (no Chrome, no audio engine)."""
    monkeypatch.setattr(cc, "measure_words", lambda words, work: {w: 330.0 for w in words})
    monkeypatch.setattr(cc, "word_timing", lambda take, words, weights=None: WORD_T[:len(words)])
    ep = cc.Ep("E02", root)
    tl = {"day": 2, "place": "x", "items": [{"id": "s2", "kind": "scene", "clock": "9:00 م", "line": "L2", "t0": 10.0, "t1": 20.0, "dur": 10.0, "voice_t0": 10.45 + lead_hold, "lead_hold": lead_hold},
                    {"id": "s3", "kind": "scene", "clock": "9:02 م", "line": "L3", "t0": 19.75, "t1": 25.0, "dur": 5.25, "voice_t0": 20.2}]}
    states = cc.caption_states(ep, tl, s, tmp_path)[0]
    return [st for st in states if st["line"] == "L2"]


def l1_findings(states):
    plates = [{"line": st["line"], "unit": st["unit"], "text": st["text"], "active_index": st["active"], "word_i": st["word_i"], "n_lines": st["n_lines"], "carry": st.get("carry", []),
               "clause_words": st["clause_words"], "split": st["split"], "start": st["start"], "end": st["end"], "word_start": st["word_start"]} for st in states]
    return [x for x in CS.check_plates(plates, {"L2": {"id": "L2", "text": L06}}, None) if x.startswith(("CAP-READING-SPEED", "CAP-READ-TIME"))]


# ------------------------------------------------------------------ the plate math
def test_the_first_sentence_of_a_line_is_short_without_a_lead_and_whole_with_one(tmp_path, monkeypatch):
    root, ed, s = e05_like(tmp_path)
    bad = l1_findings(states_for(root, s, 0.0, monkeypatch, tmp_path))
    assert bad and bad[0].startswith("CAP-READING-SPEED L2 unit 0"), bad
    ok = l1_findings(states_for(root, s, 0.4, monkeypatch, tmp_path))
    assert not [x for x in ok if " unit 0" in x], ok      # the first sentence is whole; what the fixture's crude widths make of the other units is not this test's concern


def test_the_lead_is_not_a_loosened_cap_it_is_only_what_the_plan_added(tmp_path, monkeypatch):
    root, ed, s = e05_like(tmp_path)
    st0 = [x for x in states_for(root, s, 0.0, monkeypatch, tmp_path) if x["unit"] == 0][0]
    st1 = [x for x in states_for(root, s, 0.4, monkeypatch, tmp_path) if x["unit"] == 0][0]
    assert CS.LEAD_MAX_S == 0.06 and st0["word_start"] - st0["start"] <= CS.LEAD_MAX_S + 1e-6     # without it: the usual hair at most
    assert st1["start"] < st1["word_start"] and st1["word_start"] - st1["start"] <= CS.LEAD_MAX_S + 0.4 + 1e-6


def test_the_plan_applies_the_record_as_silence_before_the_voice_inside_the_shot(tmp_path):
    root, ed, s = e05_like(tmp_path)
    cc.stage_plan(cc.Ep("E02", root))
    base = json.loads(cc.Ep("E02", root).timeline_p.read_text(encoding="utf-8"))["items"]
    (root / "work" / "daily" / "E02").mkdir(parents=True, exist_ok=True)
    (root / "work" / "daily" / "E02" / "read-heal.json").write_text(json.dumps({"lines": {"L2": {"lead": 0.4, "hold": 0.0}}}), encoding="utf-8")
    cc.stage_plan(cc.Ep("E02", root))
    after = json.loads(cc.Ep("E02", root).timeline_p.read_text(encoding="utf-8"))["items"]
    a, b = next(i for i in base if i["id"] == "s2"), next(i for i in after if i["id"] == "s2")
    assert b["lead_hold"] == pytest.approx(0.4167, abs=0.001) and b["dur"] == pytest.approx(a["dur"] + b["lead_hold"], abs=1e-3)       # snapped up to whole frames
    assert b["voice_t0"] == pytest.approx(a["voice_t0"] + b["lead_hold"], abs=1e-3) and b["dur_shot"] == pytest.approx(a["dur_shot"] + b["lead_hold"], abs=1e-3)
    assert b["read_hold"] == a["read_hold"]                                                                     # the pause after the line is untouched by a lead


def test_a_hold_extends_the_pause_after_the_line(tmp_path):
    root, ed, s = e05_like(tmp_path)
    cc.stage_plan(cc.Ep("E02", root))
    a = next(i for i in json.loads(cc.Ep("E02", root).timeline_p.read_text(encoding="utf-8"))["items"] if i["id"] == "s2")
    (root / "work" / "daily" / "E02").mkdir(parents=True, exist_ok=True)
    (root / "work" / "daily" / "E02" / "read-heal.json").write_text(json.dumps({"lines": {"L2": {"lead": 0.0, "hold": 0.5}}}), encoding="utf-8")
    cc.stage_plan(cc.Ep("E02", root))
    b = next(i for i in json.loads(cc.Ep("E02", root).timeline_p.read_text(encoding="utf-8"))["items"] if i["id"] == "s2")
    assert b["read_hold"] >= a["read_hold"] + 0.5 - 1 / 24 and b["voice_t0"] == a["voice_t0"] and b["dur_shot"] == a["dur_shot"]


# ------------------------------------------------------------------ the feedback
FINDING = {"id": "CAP-READING-SPEED", "sev": "fail", "fix": "x",
           "msg": "L2 unit 0: «كرسيي هذا!» (10 characters) is on screen 1.23 s, the least is max(1.5, chars / 12 cps) = 1.50 s"}


def test_the_finding_is_read_back_into_numbers():
    p = RH.parse(FINDING)
    assert p == {"id": "CAP-READING-SPEED", "line": "L2", "unit": 0, "shown": 1.23, "need": 1.5}
    t = RH.parse({"id": "CAP-READ-TIME", "sev": "fail", "msg": "L4 unit 2: «a b c» is on screen 1.00 s, a reader needs 1.60 s (1 gloss words included)"})
    assert t["line"] == "L4" and t["unit"] == 2 and t["need"] == 1.6
    assert RH.parse({"id": "CALM-ONE-PLATE", "msg": "x"}) is None and RH.parse({**FINDING, "sev": "warn"}) is None


def fake_animatic(ctx):
    """The animatic stage for a unit run: the L06 situation measured on the timeline the plan wrote (first plate 1.23 s up, plus the lead the plan gave it), report.json as the real one."""
    tl = json.loads((ctx.work / "timeline.json").read_text(encoding="utf-8"))
    it = next(i for i in tl["items"] if i["id"] == "s2")
    shown = 1.23 + min(float(it.get("lead_hold") or 0.0), 1.0)
    ad = ctx.work / "animatic"
    ad.mkdir(parents=True, exist_ok=True)
    fails = [] if shown + 1e-6 >= 1.5 else [{"id": FINDING["id"], "msg": FINDING["msg"].replace("1.23", f"{shown:.2f}"), "fix": "x", "sev": "fail"}]
    (ad / "report.json").write_text(json.dumps({"findings": fails, "plates": [["L2", 0, 0, 1.0, 1.4], ["L2", 1, 0, 1.4, 3.0], ["L2", 2, 0, 3.0, 4.0]]}), encoding="utf-8")
    return {"shown": shown}


def verify_from_report(ctx):
    rep = json.loads((ctx.work / "animatic" / "report.json").read_text(encoding="utf-8"))
    return [dict(f) for f in rep["findings"]]


def wire(monkeypatch, animatic_run=fake_animatic, verify=verify_from_report):
    monkeypatch.setitem(daily.STAGES, "plan", daily.Stage("plan", daily.s_plan, lambda c: [c.work / "timeline.json"], "io",
                                                          inputs=lambda c: {"read-heal.json": c.root / "work" / "daily" / c.ep / "read-heal.json", "script": c.ep_dir / "script.json"}))
    monkeypatch.setitem(daily.STAGES, "animatic", daily.Stage("animatic", animatic_run, lambda c: [], "machine", inputs=lambda c: {"timeline.json": c.work / "timeline.json"}, verify=verify))
    monkeypatch.setattr(daily, "require_upstream", lambda *a, **k: None)
    monkeypatch.setattr(daily, "validate_episode_files", lambda c: [])
    monkeypatch.setattr(daily.SG, "contract", lambda *a, **k: [])


def test_e05_l06_a_plate_up_1_23_s_is_healed_and_the_animatic_passes(tmp_path, monkeypatch):
    root, ed, s = e05_like(tmp_path)
    wire(monkeypatch)
    ctx = ctx_for(root)
    assert daily.run_list(ctx, ["plan", "animatic"]) == 0
    assert not (ctx.dir / "STOPPED.md").exists()
    rec = RH.load(root, "E02")
    assert rec["rounds"] == 1 and rec["lines"]["L2"]["lead"] == pytest.approx(0.37, abs=0.001) and rec["lines"]["L2"]["hold"] == 0.0     # 1.50 - 1.23 + the margin
    tl = json.loads((ctx.work / "timeline.json").read_text(encoding="utf-8"))
    assert next(i for i in tl["items"] if i["id"] == "s2")["lead_hold"] >= 0.37
    led = [json.loads(x) for x in (root / "kb" / "lessons" / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(led) == 1 and led[0]["source"] == "read-heal" and "L2 unit 0" in led[0]["summary"]


def test_a_measurement_that_never_improves_is_healed_in_bounded_rounds(tmp_path, monkeypatch):
    root, ed, s = e05_like(tmp_path)
    wire(monkeypatch, verify=lambda c: [{"id": FINDING["id"], "msg": FINDING["msg"], "fix": "x", "sev": "fail"}])
    ctx = ctx_for(root)
    assert daily.run_list(ctx, ["plan", "animatic"]) == 1
    rec = RH.load(root, "E02")
    assert rec["rounds"] == daily.READ_HEAL_CALLS == 2 and "CAP-READING-SPEED" in (ctx.dir / "STOPPED.md").read_text(encoding="utf-8")
    assert RH.heal_possible(root, "E02")                                                                         # 2 of 4 rounds: the next run may heal again
    rec["rounds"] = RH.MAX_ROUNDS
    RH.save(root, "E02", rec)
    assert not RH.heal_possible(root, "E02")


def test_a_sentence_in_the_middle_of_the_line_cannot_be_healed_by_the_plan(tmp_path, monkeypatch):
    root, ed, s = e05_like(tmp_path)
    mid = {**FINDING, "msg": FINDING["msg"].replace("unit 0", "unit 1")}
    wire(monkeypatch, verify=lambda c: [mid])
    ctx = ctx_for(root)
    assert daily.run_list(ctx, ["plan", "animatic"]) == 1
    rec = RH.load(root, "E02")
    assert rec["rounds"] == 0 and rec["exhausted"]["reason"] == "uncurable" and not RH.heal_possible(root, "E02") and rec["lines"] == {}


def test_a_stale_artefact_is_rerun_once(tmp_path, monkeypatch):
    root, ed, s = e05_like(tmp_path)
    n = []
    wire(monkeypatch, animatic_run=lambda c: n.append(1) or {}, verify=lambda c: [{"id": "ANI-VIDEO", "msg": "animatic.mp4 is missing", "fix": "rerun", "sev": "fail"}] if len(n) < 2 else [])
    ctx = ctx_for(root)
    assert daily.run_list(ctx, ["plan", "animatic"]) == 0 and len(n) == 2


# ------------------------------------------------------------------ the autopilot
NOW = ap.dt.datetime(2026, 10, 30, 18, 0)


def stopped(root, code="CAP-READING-SPEED", ep="E05"):
    d = root / "work" / "daily" / ep
    d.mkdir(parents=True, exist_ok=True)
    (d / "STOPPED.md").write_text(f"# stopped\n\n`FAIL [{code}]` x\n", encoding="utf-8")


def test_a_reading_time_stop_is_not_terminal_nor_stuck_while_the_heal_has_rounds(tmp_path):
    stopped(tmp_path)
    st = ap.load_state(tmp_path)
    st["attempts"]["E05"] = {"date": "2026-10-30", "n": 3, "last_code": "CAP-READING-SPEED", "at": "2026-10-30T17:30:00"}       # the state E05 was parked in
    assert ap.heal_pending(tmp_path, "E05", NOW)
    assert ap.record_failure(tmp_path, st, "E05", 1, NOW) is False and st["attempts"]["E05"]["n"] < ap.MAX_ATTEMPTS
    rec = RH.load(tmp_path, "E05")
    rec["rounds"] = RH.MAX_ROUNDS
    RH.save(tmp_path, "E05", rec)
    assert not ap.heal_pending(tmp_path, "E05", NOW) and ap.record_failure(tmp_path, st, "E05", 1, NOW) is True
    stopped(tmp_path, "CRITIC-LOW")
    assert not ap.heal_pending(tmp_path, "E05", NOW)


def test_the_lead_repair_runs_once_per_episode_and_stop_code_per_day(tmp_path):
    st = ap.load_state(tmp_path)
    assert not ap.lead_done(st, "E05", "PLAN-DURATION", NOW)
    st["lead"][ap.lead_key("E05", "PLAN-DURATION")] = "2026-10-30"
    assert ap.lead_done(st, "E05", "PLAN-DURATION", NOW) and not ap.lead_done(st, "E05", "CAP-READING-SPEED", NOW)         # a new code gets its own repair
    st["lead"]["E05"] = "2026-10-30"                                                                              # the old bare key (E05 on 2026-10-30) no longer blocks
    assert not ap.lead_done(st, "E05", "CAP-READING-SPEED", NOW)
    for c in ("A", "B"):
        st["lead"][ap.lead_key("E05", c)] = "2026-10-30"
    assert ap.lead_done(st, "E05", "ZZZ", NOW) and not ap.lead_done(st, "E05", "ZZZ", NOW + ap.dt.timedelta(days=1))       # a runaway guard: 3 a day


def test_lead_once_uses_the_per_code_key(tmp_path):
    st = ap.load_state(tmp_path)
    st["needs_lead"] = {"ep": "E05", "code": "CAP-READING-SPEED"}
    st["lead"]["E05"] = "2026-10-30"
    ap.save_state(tmp_path, st)

    def llm(prompt, name):
        d = tmp_path / "work" / "daily"
        (d / "autopilot-lead-2026-10-30.md").write_text("cause: x\n", encoding="utf-8")
        (d / "autopilot-lead-2026-10-30.json").write_text(json.dumps({"action": "give-up", "reason": "x"}), encoding="utf-8")
        return {"rc": 0}
    rc, line = ap.lead_once(tmp_path, NOW, llm=llm, build=lambda e, f=None: (0, "ok"))
    assert line.split()[2] != "LEAD-SKIP" and ap.load_state(tmp_path)["lead"][ap.lead_key("E05", "CAP-READING-SPEED")] == "2026-10-30"
