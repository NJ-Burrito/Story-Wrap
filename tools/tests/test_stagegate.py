"""Safe stages (tools/stagegate.py, tools/animatic.py, the verify/invalidation part of tools/daily.py): fingerprints, hash-based invalidation, one verifier per stage, the early preview's
checks. No model, no GPU, no browser: ffprobe is replaced, the animatic's analysis is tested on data."""
import json
import math
import struct
import wave
from pathlib import Path

import pytest

import animatic
import calm_compose as cc
import daily
import stagegate as SG

SERIES = "series"


# ------------------------------------------------------------------ fixtures
def mk_root(tmp_path, ep="E01"):
    root = tmp_path / "repo"
    (root / "bible" / "series" / SERIES / "episodes" / ep).mkdir(parents=True)
    (root / "work").mkdir()
    return root


def ctx_for(root, ep="E01", **kw):
    return daily.Ctx(ep, root=root, config=kw.pop("config", {}), budget=daily.Budget(root, limit=1000, today="2026-10-25"), log=lambda *a: None, **kw)


def write_wav(path, seconds=2.0, amp=0.3, rate=24000):
    path.parent.mkdir(parents=True, exist_ok=True)
    n = int(seconds * rate)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", int(32767 * amp * math.sin(2 * math.pi * 220 * i / rate))) for i in range(n)))


TEXT = "كلام بلا تشكيل"
TTS = "كَلَامٌ بِلَا تَشْكِيلٌ"


def script_ok(n=5):
    return {"series": SERIES, "lines": [{"id": f"L{i}", "speaker": "narrator", "text": TEXT, "tts_text": TTS, "style": "story", "emotion": "calm"} for i in range(1, n + 1)]}


def plan_ok():
    return {"series": SERIES, "episode": "E01", "day": 1, "place": "the series", "clock0": "9:04 م",
            "scenes": [{"id": f"s{i}", "line": f"L{i}", "block": "story", "template": "push_in", "params": {"character": "partner"}} for i in range(1, 6)],
            "choice": {"question": "أين تنام؟", "choice1": "على الرف", "choice2": "في اليد"}}


def put_episode(root, ep="E01", script=None, plan=None, caption="حلقة ١\n#المكتب #قصة #رسوم_متحركة\n"):
    ed = root / "bible" / "series" / SERIES / "episodes" / ep
    (ed / "script.json").write_text(json.dumps(script or script_ok(), ensure_ascii=False), encoding="utf-8")
    (ed / "calm-plan.json").write_text(json.dumps(plan or plan_ok(), ensure_ascii=False), encoding="utf-8")
    (ed / "caption.txt").write_text(caption, encoding="utf-8")
    return ed


def wr(*pairs):
    """Write (path, text) pairs; returns nothing, like a stage body that has no info to report."""
    for p, t in zip(pairs[::2], pairs[1::2]):
        p.write_text(t, encoding="utf-8")


def ids(findings, sev="fail"):
    return {f["id"] for f in findings if f["sev"] == sev}


# ------------------------------------------------------------------ fingerprints and the staleness rule
def test_fingerprint_covers_files_folders_lists_literals_and_absence(tmp_path):
    a, b = tmp_path / "a.txt", tmp_path / "d"
    a.write_text("1", encoding="utf-8")
    b.mkdir()
    (b / "x.txt").write_text("x", encoding="utf-8")
    fp = SG.fingerprint({"file": a, "dir": b, "list": [a, b / "x.txt"], "const": "const:hello", "gone": tmp_path / "none"})
    assert fp["gone"] == "absent" and len(set(fp.values())) == 5
    a.write_text("2", encoding="utf-8")
    (b / "y.txt").write_text("y", encoding="utf-8")
    fp2 = SG.fingerprint({"file": a, "dir": b, "list": [a, b / "x.txt"], "const": "const:hello", "gone": tmp_path / "none"})
    assert SG.changed(fp, fp2) == ["dir", "file", "list"]
    assert SG.changed(None, fp2) == sorted(fp2)


def test_a_pycache_or_node_modules_folder_never_changes_a_folder_hash(tmp_path):
    d = tmp_path / "d"
    (d / "__pycache__").mkdir(parents=True)
    (d / "m.py").write_text("x", encoding="utf-8")
    h = SG.sha_tree(d)
    (d / "__pycache__" / "m.pyc").write_bytes(b"junk")
    assert SG.sha_tree(d) == h


def chain(tmp_path, ctx, runs, verify_fail=None):
    """Three stages A -> B -> C in a line (B reads A's output, C reads B's) and an independent D (reads only its own file)."""
    f = {n: tmp_path / f"{n}.txt" for n in "SABCD"}      # S = the source A reads, D reads Dsrc
    src_d = tmp_path / "Dsrc.txt"
    src_d.write_text("d", encoding="utf-8")
    f["S"].write_text("s1", encoding="utf-8")

    def body(name, src):
        def run(c):
            runs.append(name)
            f[name].write_text(f"{name}({src.read_text(encoding='utf-8')})", encoding="utf-8")
        return run

    def verify(name):
        return lambda c: [SG.F("X-FAIL", f"{name} is wrong", f"{name}: fix it")] if verify_fail == name else []

    def mk(name, src):
        return daily.Stage(name, body(name, src), lambda c, n=name: [f[n]], "io", inputs=lambda c, s=src: {"in": s}, verify=verify(name), out_spec=lambda c, n=name: {"out": f[n]})
    return f, src_d, {"A": mk("A", f["S"]), "B": mk("B", f["A"]), "C": mk("C", f["B"]), "D": mk("D", src_d)}


def test_a_fix_reruns_exactly_the_stages_whose_inputs_changed(tmp_path):
    ctx, runs = ctx_for(mk_root(tmp_path)), []
    f, src_d, st = chain(tmp_path, ctx, runs)
    for n in "ABCD":
        assert daily.run_stage(ctx, st[n]) == "ok"
    assert runs == ["A", "B", "C", "D"]
    assert all(daily.stage_state(ctx, st[n])[0] == "fresh" for n in "ABCD")
    f["S"].write_text("s2", encoding="utf-8")                          # the fix at stage A's input
    assert daily.stage_state(ctx, st["A"])[0] == "stale" and "in" in daily.stage_state(ctx, st["A"])[1]
    assert daily.stage_state(ctx, st["B"])[0] == "fresh"               # B's own inputs have not moved yet: it is stale only once A has produced something new
    runs.clear()
    for n in "ABCD":
        daily.run_stage(ctx, st[n])
    assert runs == ["A", "B", "C"]                                      # D never reran: its inputs did not change


def test_a_rerun_that_writes_the_same_output_leaves_downstream_untouched(tmp_path):
    ctx, runs = ctx_for(mk_root(tmp_path)), []
    f, _d, st = chain(tmp_path, ctx, runs)
    for n in "ABC":
        daily.run_stage(ctx, st[n])
    f["S"].write_text("s1 ", encoding="utf-8")       # a different file ...
    def again(c):
        runs.append("A")
        f["A"].write_text("A(s1)", encoding="utf-8")      # ... that yields the identical output
    st["A"].run = again
    runs.clear()
    for n in "ABC":
        daily.run_stage(ctx, st[n])
    assert runs == ["A"]


def test_a_hand_edit_of_an_output_makes_the_stage_stale_and_reports_it(tmp_path):
    ctx, runs = ctx_for(mk_root(tmp_path)), []
    f, _d, st = chain(tmp_path, ctx, runs)
    daily.run_stage(ctx, st["A"])
    f["A"].write_text("edited by hand", encoding="utf-8")
    state, why = daily.stage_state(ctx, st["A"])
    assert state == "stale" and "outputs changed" in why
    daily.restamp(ctx, "A") if "A" in daily.STAGES else None      # restamp only knows the real stages; the real-stage path is covered below


def test_an_ok_stage_from_before_fingerprints_is_adopted_not_rerun(tmp_path):
    ctx, runs = ctx_for(mk_root(tmp_path)), []
    f, _d, st = chain(tmp_path, ctx, runs)
    f["S"].write_text("old", encoding="utf-8")
    f["A"].write_text("A(old)", encoding="utf-8")
    ctx.state["stages"]["A"] = {"status": "ok", "seconds": 5.0}        # a STATE.json written before this feature
    assert daily.stage_state(ctx, st["A"])[0] == "adopt"
    assert daily.run_stage(ctx, st["A"]) == "skipped" and runs == []
    e = ctx.state["stages"]["A"]
    assert e["verify"]["status"] == "pass" and set(e["inputs"]) == {"in"} and set(e["outputs"]) == {"out"}
    assert daily.stage_state(ctx, st["A"])[0] == "fresh"


def test_a_legacy_stage_without_hooks_keeps_the_old_skip_rule(tmp_path):
    ctx = ctx_for(mk_root(tmp_path))
    out, n = tmp_path / "o.txt", {"k": 0}
    def body(c):
        n["k"] += 1
        out.write_text("1", encoding="utf-8")
    st = daily.Stage("script", body, lambda c: [out], "llm")
    assert daily.run_stage(ctx, st) == "ok" and daily.run_stage(ctx, st) == "skipped" and n["k"] == 1


# ------------------------------------------------------------------ verify after every stage, and the stop
def test_a_failing_verify_stops_with_the_check_id_and_a_fix_brief_and_blocks_the_next_stage(tmp_path, monkeypatch):
    root = mk_root(tmp_path)
    ctx, runs = ctx_for(root), []
    f, _d, st = chain(tmp_path, ctx, runs, verify_fail="A")
    for n in ("A", "B"):
        monkeypatch.setitem(daily.STAGES, n, st[n])
    monkeypatch.setattr(daily, "RUN_STAGES", ["A", "B"])
    rc = daily.run_list(ctx, ["A", "B"])
    assert rc == 1 and runs == ["A"]                                    # B never started
    e = ctx.state["stages"]["A"]
    assert e["status"] == "verify-failed" and e["check"] == "X-FAIL" and e["verify"]["status"] == "fail"
    stop = (root / "work" / "daily" / "E01" / "STOPPED.md").read_text(encoding="utf-8")
    assert "X-FAIL" in stop and "A: fix it" in stop and "only the stages whose inputs changed rerun" in stop
    rep = json.loads((root / "work" / "daily" / "E01" / "verify" / "A.json").read_text(encoding="utf-8"))
    assert rep["status"] == "fail" and rep["findings"][0]["id"] == "X-FAIL"
    with pytest.raises(daily.StageFail) as x:                           # even a direct attempt at B is refused
        daily.require_upstream(ctx, ["A"])
    assert x.value.code == "UPSTREAM-NOT-VERIFIED"


def test_a_warning_does_not_stop_the_run(tmp_path):
    ctx = ctx_for(mk_root(tmp_path))
    out = tmp_path / "o.txt"
    st = daily.Stage("X", lambda c: wr(out, "1"), lambda c: [out], "io", inputs=lambda c: {"o": tmp_path / "none"}, verify=lambda c: [SG.F("W-1", "careful", "", "warn")])
    assert daily.run_stage(ctx, st) == "ok"
    assert ctx.state["stages"]["X"]["verify"]["status"] == "pass" and ctx.state["stages"]["X"]["verify"]["checks"] == 1


def test_a_stage_that_changes_what_it_reads_fails_the_contract(tmp_path):
    ctx = ctx_for(mk_root(tmp_path))
    src, out = tmp_path / "src.txt", tmp_path / "o.txt"
    src.write_text("a", encoding="utf-8")
    st = daily.Stage("X", lambda c: wr(src, "b", out, "1"), lambda c: [out], "io", inputs=lambda c: {"src": src}, verify=lambda c: [])
    with pytest.raises(daily.VerifyFail) as x:
        daily.run_stage(ctx, st)
    assert x.value.code == "CONTRACT-INPUT-MOVED"


def test_the_contract_names_an_empty_or_unparseable_output(tmp_path):
    ctx = ctx_for(mk_root(tmp_path))
    out = tmp_path / "o.json"
    st = daily.Stage("X", lambda c: wr(out, "{not json"), lambda c: [out], "io", inputs=lambda c: {}, verify=lambda c: [])
    st.inputs = lambda c: {"k": tmp_path}
    monkey = SG.output_paths
    SG.output_paths = lambda name, c: [out] if name == "X" else monkey(name, c)
    try:
        with pytest.raises(daily.VerifyFail) as x:
            daily.run_stage(ctx, st)
    finally:
        SG.output_paths = monkey
    assert x.value.code == "CONTRACT-OUTPUT"


def test_time_per_stage_and_per_verify_is_recorded_and_counts_against_the_cap(tmp_path):
    root = mk_root(tmp_path)
    ctx = ctx_for(root, cap_s=100)
    out = tmp_path / "o.txt"
    src = tmp_path / "src"
    src.mkdir()
    st = daily.Stage("voice", lambda c: wr(out, "1"), lambda c: [out], "machine", inputs=lambda c: {"k": src}, verify=lambda c: [])
    daily.run_stage(ctx, st)
    lines = [json.loads(l) for l in (root / "work" / "daily" / "E01" / "timings.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [(l["stage"], l["phase"]) for l in lines] == [("voice", "run"), ("voice", "verify")] and all("seconds" in l for l in lines)
    e = ctx.state["stages"]["voice"]
    assert abs(ctx.deadline["machine_s"] - (e["seconds"] + e["verify"]["seconds"])) < 0.11
    assert "verify pass" in daily.render_status(ctx)


def test_stale_and_verify_commands_run_nothing(tmp_path, capsys):
    root = mk_root(tmp_path)
    ctx = ctx_for(root)
    text = daily.render_stale(ctx)
    for n in daily.RUN_STAGES:
        assert n in text
    assert "not run yet" in text


def test_the_stage_list_has_plan_and_animatic_before_the_shots():
    r = daily.RUN_STAGES
    assert r.index("plan") < r.index("animatic") < r.index("shots") < r.index("compose") < r.index("gates") < r.index("critic")
    assert set(daily.STAGES) == set(daily.RUN_STAGES + daily.POST_STAGES) and set(SG.VERIFY) == set(daily.STAGES) - {"yt_stories"}   # the YouTube/stories stage keeps its own records (youtube.json, stories.json) and has no stage verify
    assert "animatic" in daily.MACHINE_STAGES and "plan" not in daily.MACHINE_STAGES
    assert cc.JOIN_S == SG.JOIN_S and cc.FPS == SG.FPS


def test_every_real_stage_declares_inputs_and_outputs_and_a_verify(tmp_path):
    ctx = ctx_for(mk_root(tmp_path))
    for n in daily.RUN_STAGES:
        st = daily.STAGES[n]
        assert st.verify is not None
        if n not in ("votes", "retro"):      # votes and the build retro keep their own records and have no input fingerprints
            assert st.inputs is not None and st.out_spec is not None
            assert SG.fingerprint(st.inputs(ctx)) is not None and SG.fingerprint(st.out_spec(ctx)) is not None


def test_the_critic_rehashes_what_it_healed_and_the_healer_edit_is_restamped(tmp_path):
    root = mk_root(tmp_path)
    ctx = ctx_for(root)
    ed = put_episode(root)
    (ctx.work).mkdir(parents=True)
    ctx.state["stages"]["script"] = {"status": "ok", "inputs": SG.fingerprint(SG.inputs_for("script", ctx)), "outputs": SG.fingerprint(SG.outputs_for("script", ctx)), "verify": {"status": "pass"}}
    assert daily.stage_state(ctx, daily.STAGES["script"])[0] == "fresh"
    (ed / "calm-plan.json").write_text(json.dumps({**plan_ok(), "post_caption": "x"}, ensure_ascii=False), encoding="utf-8")      # the healer's edit
    assert "outputs changed" in daily.stage_state(ctx, daily.STAGES["script"])[1]
    daily.restamp(ctx, "script")
    assert daily.stage_state(ctx, daily.STAGES["script"])[0] == "fresh"
    assert daily.STAGES["critic"].heals is True


# ------------------------------------------------------------------ verifiers: script
def test_script_verify_passes_a_good_episode_and_names_each_fault(tmp_path, monkeypatch):
    root = mk_root(tmp_path)
    ctx = ctx_for(root)
    put_episode(root)
    monkeypatch.setattr(daily, "validate_episode_files", lambda c: [])
    assert ids(SG.v_script(ctx)) == set()
    s = script_ok()
    s["lines"][0]["tts_text"] = "شيء آخر تماما"
    s["lines"][1]["text"] = "كَلَامٌ"
    s["lines"][2]["text"] = " ".join(["كلمة"] * 30)
    s["lines"][2]["tts_text"] = " ".join(["كلمة"] * 30)
    s["lines"].append({"id": "L9", "speaker": "narrator", "text": TEXT, "tts_text": TTS, "style": "story"})
    s["lines"].append({"id": "L1", "speaker": "narrator", "text": TEXT, "tts_text": TTS, "style": "story"})
    put_episode(root, script=s, caption="لا وسوم هنا\n")
    got = SG.v_script(ctx)
    assert {"SCRIPT-TTS-DRIFT", "SCRIPT-TASHKEEL", "SCRIPT-LINE-LEN", "SCRIPT-SCHEMA", "SCRIPT-CAPTION"} <= ids(got)
    assert "SCRIPT-ORPHAN-LINE" in ids(got, "warn")


def test_script_verify_folds_in_the_plan_checks_of_the_writer_gate(tmp_path, monkeypatch):
    root = mk_root(tmp_path)
    ctx = ctx_for(root)
    put_episode(root)
    monkeypatch.setattr(daily, "validate_episode_files", lambda c: ["PLAN-TASHKEEL recap carries tashkeel", "PLAN-GLOSS a word has no gloss"])
    got = SG.v_script(ctx)
    assert {"PLAN-TASHKEEL", "PLAN-GLOSS"} <= ids(got)
    assert SG.v_script(ctx_for(mk_root(tmp_path / "other"))) and ids(SG.v_script(ctx_for(mk_root(tmp_path / "other2")))) == {"SCRIPT-FILES"}


# ------------------------------------------------------------------ verifiers: voice
def test_voice_verify_checks_every_take_and_one_take_per_line(tmp_path):
    root = mk_root(tmp_path)
    ctx = ctx_for(root)
    put_episode(root)
    vd = root / "work" / "voice" / "E01"
    for i in range(1, 6):
        write_wav(vd / f"L{i}.trimmed.wav", 2.0)
    assert ids(SG.v_voice(ctx)) == set()
    assert SG.take_sources_path(ctx).is_file()                                              # the text each take was made from is recorded
    (vd / "L5.trimmed.wav").unlink()
    write_wav(vd / "L2.trimmed.wav", 0.1)                                                   # a truncated take
    write_wav(vd / "L3.trimmed.wav", 2.0, amp=0.001)                                        # silent
    write_wav(vd / "L4.trimmed.wav", 2.0, amp=1.0)                                          # clipped
    got = ids(SG.v_voice(ctx))
    assert {"VOICE-TAKES", "VOICE-LENGTH", "VOICE-SILENT", "VOICE-CLIPPED"} <= got


def test_voice_verify_catches_a_wrong_speaking_rate(tmp_path):
    root = mk_root(tmp_path)
    ctx = ctx_for(root)
    s = script_ok(1)
    s["lines"][0]["text"] = " ".join(["كلمة"] * 20)
    s["lines"][0]["tts_text"] = s["lines"][0]["text"]
    put_episode(root, script=s)
    write_wav(root / "work" / "voice" / "E01" / "L1.trimmed.wav", 1.0)                     # 20 words in 1 s
    assert "VOICE-RATE" in ids(SG.v_voice(ctx))


def test_a_line_reworded_after_it_was_voiced_is_a_stale_take_never_an_automatic_revoice(tmp_path):
    root = mk_root(tmp_path)
    ctx = ctx_for(root)
    put_episode(root)
    vd = root / "work" / "voice" / "E01"
    for i in range(1, 6):
        write_wav(vd / f"L{i}.trimmed.wav", 2.0)
    assert "VOICE-STALE-TAKE" not in ids(SG.v_voice(ctx))
    s = script_ok()
    s["lines"][2]["tts_text"] = "كَلَامٌ مُخْتَلِفٌ"
    put_episode(root, script=s)
    got = SG.v_voice(ctx)
    assert "VOICE-STALE-TAKE" in ids(got) and "NEW line id" in next(f for f in got if f["id"] == "VOICE-STALE-TAKE")["fix"]


def test_a_character_line_needs_its_mouth_track(tmp_path):
    root = mk_root(tmp_path)
    ctx = ctx_for(root)
    s = script_ok(2)
    s["lines"][1]["speaker"] = "hero"
    put_episode(root, script=s)
    vd = root / "work" / "voice" / "E01"
    for i in (1, 2):
        write_wav(vd / f"L{i}.trimmed.wav", 2.0)
    assert "VOICE-VISEME" in ids(SG.v_voice(ctx))
    (vd / "visemes").mkdir()
    (vd / "visemes" / "L2.json").write_text("{}", encoding="utf-8")
    assert "VOICE-VISEME" not in ids(SG.v_voice(ctx))


# ------------------------------------------------------------------ verifiers: plan
def build_timeline(ctx, n=5, dur=6.0, voice_s=2.0, make_takes=True):
    items = [{"kind": "card", "id": "day", "shot": f"{ctx.ep}-day", "video": f"work/shots/{ctx.ep}-day/out/{ctx.ep}-day.mp4", "dur": 2.5, "t0": 0.0, "t1": 2.5, "line": None}]
    t = 2.5
    for i in range(n):
        t0 = round(t - cc.JOIN_S, 4)
        it = {"kind": "scene", "id": f"s{i + 1}", "shot": f"{ctx.ep}-s{i + 1}", "video": f"work/shots/{ctx.ep}-s{i + 1}/out/{ctx.ep}-s{i + 1}.mp4", "dur": dur, "t0": t0, "t1": round(t0 + dur, 4),
              "line": f"L{i + 1}", "voice_t0": round(t0 + cc.JOIN_S + cc.VOICE_LEAD_S, 4), "block": "story"}
        items.append(it)
        t = it["t1"]
    for kind, d in (("choice", 5.0), ("follow", 2.5)):
        t0 = round(t - cc.JOIN_S, 4)
        items.append({"kind": "card", "id": kind, "shot": f"{ctx.ep}-{kind}", "video": f"work/shots/{ctx.ep}-{kind}/out/{ctx.ep}-{kind}.mp4", "dur": d, "t0": t0, "t1": round(t0 + d, 4), "line": None})
        t = items[-1]["t1"]
    tl = {"episode": ctx.ep, "series": SERIES, "fps": 24, "canvas": [1080, 1920], "profile": "calm", "day": 1, "items": items, "total_s": items[-1]["t1"], "join_s": cc.JOIN_S}
    ctx.work.mkdir(parents=True, exist_ok=True)
    (ctx.work / "timeline.json").write_text(json.dumps(tl), encoding="utf-8")
    if make_takes:
        for i in range(1, n + 1):
            write_wav(ctx.root / "work" / "voice" / ctx.ep / f"L{i}.trimmed.wav", voice_s)
    return tl


def plan_setup(tmp_path):
    root = mk_root(tmp_path)
    ctx = ctx_for(root)
    put_episode(root)
    return root, ctx


def test_plan_verify_accepts_a_good_timeline(tmp_path):
    _root, ctx = plan_setup(tmp_path)
    build_timeline(ctx)
    assert ids(SG.v_plan(ctx)) == set()


def test_plan_verify_names_each_timeline_fault(tmp_path):
    _root, ctx = plan_setup(tmp_path)
    tl = build_timeline(ctx)
    tl["items"][2]["t0"] += 0.4                                    # a broken join
    tl["items"][4]["dur"] = 6.013                                  # not a whole number of frames
    tl["items"][4]["t1"] = round(tl["items"][4]["t0"] + 6.013, 4)
    (ctx.work / "timeline.json").write_text(json.dumps(tl), encoding="utf-8")
    assert {"PLAN-TL-ORDER", "PLAN-TL-SNAP"} <= ids(SG.v_plan(ctx))


def test_plan_verify_catches_a_voice_that_does_not_fit_its_scene_or_overlaps_another(tmp_path):
    _root, ctx = plan_setup(tmp_path)
    build_timeline(ctx, voice_s=7.5)                               # a 7.5 s take in a 6 s scene
    got = ids(SG.v_plan(ctx))
    assert "PLAN-TL-VOICE" in got
    _root2, ctx2 = plan_setup(tmp_path / "b")
    tl = build_timeline(ctx2)
    tl["items"][2]["voice_t0"] = tl["items"][1]["voice_t0"] + 1.0  # the second line starts while the first still speaks
    (ctx2.work / "timeline.json").write_text(json.dumps(tl), encoding="utf-8")
    assert "PLAN-TL-OVERLAP" in ids(SG.v_plan(ctx2))


def test_plan_verify_wants_the_floor_the_wrapper_and_every_planned_line(tmp_path):
    _root, ctx = plan_setup(tmp_path)
    tl = build_timeline(ctx, n=2, dur=4.0)                         # 2 scenes of 4 s: under the 25 s floor, and L3..L5 never spoken
    got = SG.v_plan(ctx)
    assert {"CALM-LENGTH", "PLAN-TL-COVER"} <= ids(got)
    _root2, ctx2 = plan_setup(tmp_path / "b")
    tl = build_timeline(ctx2)
    tl["items"].pop()                                              # the follow card is gone
    tl["total_s"] = tl["items"][-1]["t1"]
    (ctx2.work / "timeline.json").write_text(json.dumps(tl), encoding="utf-8")
    assert "PLAN-TL-WRAPPER" in ids(SG.v_plan(ctx2))


def test_plan_verify_checks_the_intro_follows_its_scene(tmp_path):
    root, ctx = plan_setup(tmp_path)
    put_episode(root, plan={**plan_ok(), "intros": [{"id": "intro-partner", "character": "partner", "after": "s1", "name": "عيسى", "tag": "يحمل المصباح"}]})
    build_timeline(ctx)
    assert "PLAN-TL-INTRO" in ids(SG.v_plan(ctx))


# ------------------------------------------------------------------ verifiers: shots, compose, gates, critic, animatic
def fake_probe(width=1080, height=1920, fps="24/1", dur=6.0, audio=False, rate=48000):
    streams = [{"codec_type": "video", "width": width, "height": height, "r_frame_rate": fps, "duration": str(dur)}]
    if audio:
        streams.append({"codec_type": "audio", "sample_rate": str(rate)})
    return {"streams": streams, "format": {"duration": str(dur)}}


def put_shots(root, ctx, tl, verdict="PASS"):
    for it in tl["items"]:
        v = root / it["video"]
        v.parent.mkdir(parents=True, exist_ok=True)
        v.write_bytes(b"x")
        g = root / "work" / "shots" / it["shot"] / "gate"
        g.mkdir(parents=True, exist_ok=True)
        (g / "report.json").write_text(json.dumps({"verdict": verdict}), encoding="utf-8")


def test_shots_verify_checks_each_video_its_size_its_length_and_its_own_gate(tmp_path, monkeypatch):
    root, ctx = plan_setup(tmp_path)
    tl = build_timeline(ctx)
    put_shots(root, ctx, tl)
    monkeypatch.setattr(SG, "ffprobe_json", lambda p: fake_probe(dur=10.0))
    assert ids(SG.v_shots(ctx)) == set()
    monkeypatch.setattr(SG, "ffprobe_json", lambda p: fake_probe(dur=2.0, width=540, fps="30/1"))
    assert {"SHOTS-SHORT", "SHOTS-SIZE", "SHOTS-FPS"} <= ids(SG.v_shots(ctx))
    (root / tl["items"][0]["video"]).unlink()
    (root / "work" / "shots" / tl["items"][1]["shot"] / "gate" / "report.json").write_text(json.dumps({"verdict": "FAIL"}), encoding="utf-8")
    monkeypatch.setattr(SG, "ffprobe_json", lambda p: fake_probe(dur=10.0))
    assert {"SHOTS-VIDEO", "SHOTS-GATE-REPORT"} <= ids(SG.v_shots(ctx))


def put_captions(ctx, plates, png=True):
    for c in plates:
        if png:
            (ctx.work / c["png"]).parent.mkdir(parents=True, exist_ok=True)
            (ctx.work / c["png"]).write_bytes(b"x")
    (ctx.work / "captions.json").write_text(json.dumps({"captions": plates}), encoding="utf-8")


def plates():
    return [{"line": "L1", "unit": 0, "active_index": 0, "start": 1.0, "end": 2.0, "png": "plates/c0.png"}, {"line": "L1", "unit": 0, "active_index": 1, "start": 2.0, "end": 3.0, "png": "plates/c1.png"}]


def test_compose_verify_checks_the_file_the_plates_and_the_animatic_prediction(tmp_path, monkeypatch):
    root, ctx = plan_setup(tmp_path)
    tl = build_timeline(ctx)
    (ctx.work / "episode.mp4").write_bytes(b"x")
    put_captions(ctx, plates())
    monkeypatch.setattr(SG, "ffprobe_json", lambda p: fake_probe(dur=tl["total_s"], audio=True))
    assert ids(SG.v_compose(ctx)) == set()
    pred = [["L1", 0, 0, 1.0, 2.0], ["L1", 0, 1, 2.01, 3.0]]
    (ctx.work / "animatic").mkdir()
    (ctx.work / "animatic" / "report.json").write_text(json.dumps({"plates": pred}), encoding="utf-8")
    assert "COMPOSE-ANIMATIC-DRIFT" not in ids(SG.v_compose(ctx))                      # rounding is tolerated
    pred[1][3] = 2.5
    (ctx.work / "animatic" / "report.json").write_text(json.dumps({"plates": pred}), encoding="utf-8")
    assert "COMPOSE-ANIMATIC-DRIFT" in ids(SG.v_compose(ctx))
    monkeypatch.setattr(SG, "ffprobe_json", lambda p: fake_probe(dur=tl["total_s"] - 5, width=540))
    assert {"COMPOSE-LENGTH", "COMPOSE-SIZE", "COMPOSE-AUDIO"} <= ids(SG.v_compose(ctx))
    (ctx.work / "plates" / "c0.png").unlink()
    assert "COMPOSE-PLATES" in ids(SG.v_compose(ctx))


def test_gates_verify_refuses_a_pass_that_skipped_a_check(tmp_path):
    _root, ctx = plan_setup(tmp_path)
    (ctx.work / "gate").mkdir(parents=True)
    full = {"verdict": "PASS", "complete": True, "checks": [{"id": i, "status": "pass"} for i in SG.GATE_REQUIRED], "fails": []}
    (ctx.work / "gate" / "report.json").write_text(json.dumps(full), encoding="utf-8")
    assert ids(SG.v_gates(ctx)) == set()
    part = {**full, "checks": full["checks"][:-3]}
    (ctx.work / "gate" / "report.json").write_text(json.dumps(part), encoding="utf-8")
    assert "GATE-INCOMPLETE" in ids(SG.v_gates(ctx))
    (ctx.work / "gate" / "report.json").write_text(json.dumps({**full, "verdict": "FAIL", "fails": ["CALM-LENGTH x"], "complete": False}), encoding="utf-8")
    assert {"GATE-VERDICT", "GATE-INCOMPLETE"} <= ids(SG.v_gates(ctx))


def test_gate_required_list_matches_the_ids_calm_compose_records():
    src = Path(cc.__file__).read_text(encoding="utf-8")
    for cid in SG.GATE_REQUIRED:
        assert f'"{cid}"' in src, cid


def good_critic(**kw):
    j = {"score": 9, "answers": [{"q": f"Q{i:02d}", "ok": True, "evidence": "frame-0.png"} for i in range(1, 13)], "faults": []}
    j.update(kw)
    return j


def test_critic_verify_wants_twelve_evidenced_answers_for_this_exact_video(tmp_path):
    _root, ctx = plan_setup(tmp_path)
    (ctx.work / "heal").mkdir(parents=True)
    (ctx.work / "episode.mp4").write_bytes(b"video")
    sha = SG.sha_file(ctx.work / "episode.mp4")
    (ctx.work / "heal" / "critic.json").write_text(json.dumps(good_critic(video_sha=sha)), encoding="utf-8")
    assert ids(SG.v_critic(ctx)) == set()
    bad = good_critic(video_sha="0" * 64)
    bad["answers"][0]["evidence"] = ""
    bad["answers"][1]["ok"] = False
    bad["answers"].pop()
    (ctx.work / "heal" / "critic.json").write_text(json.dumps(bad), encoding="utf-8")
    got = SG.v_critic(ctx)
    assert {"CRITIC-INCOMPLETE", "CRITIC-EVIDENCE", "CRITIC-STALE"} <= ids(got) and "CRITIC-UNEXPLAINED" in ids(got, "warn")


def test_animatic_verify_reads_the_report_and_the_video(tmp_path, monkeypatch):
    _root, ctx = plan_setup(tmp_path)
    tl = build_timeline(ctx)
    ad = ctx.work / "animatic"
    ad.mkdir()
    assert ids(SG.v_animatic(ctx)) == {"ANI-REPORT"}
    (ad / "report.json").write_text(json.dumps({"findings": [{"id": "CAP-READING-SPEED", "msg": "too fast", "fix": "plan: pause", "sev": "fail"}, {"id": "CALM-LENGTH", "msg": "long", "fix": "", "sev": "warn"}]}), encoding="utf-8")
    (ad / "animatic.mp4").write_bytes(b"x")
    monkeypatch.setattr(SG, "ffprobe_json", lambda p: fake_probe(dur=tl["total_s"], audio=True))
    got = SG.v_animatic(ctx)
    assert ids(got) == {"CAP-READING-SPEED"} and ids(got, "warn") == {"CALM-LENGTH"}
    monkeypatch.setattr(SG, "ffprobe_json", lambda p: fake_probe(dur=3.0))
    assert "ANI-VIDEO" in ids(SG.v_animatic(ctx))


def test_votes_and_publish_and_schedule_verifiers(tmp_path):
    root, ctx = plan_setup(tmp_path)
    assert SG.v_votes(ctx) == [] and SG.v_publish(ctx) == [] and SG.v_schedule(ctx) == []
    (ctx.work).mkdir(parents=True, exist_ok=True)
    (ctx.work / "post.json").write_text(json.dumps({"media_id": "17"}), encoding="utf-8")
    assert SG.v_publish(ctx) == [] and "SCHEDULE-PLAN" in ids(SG.v_schedule(ctx))
    (ctx.work / "post.json").write_text(json.dumps({}), encoding="utf-8")
    assert "PUBLISH-RECORD" in ids(SG.v_publish(ctx))
    (root / "work" / "episodes" / "E00").mkdir()
    (root / "work" / "episodes" / "E00" / "decision.json").write_text("{}", encoding="utf-8")
    assert "VOTES-EMPTY" in ids(SG.v_votes(ctx))


def test_the_fix_brief_names_the_check_the_cause_and_the_rerun(tmp_path):
    b = SG.brief("voice", [SG.F("VOICE-RATE", "take L3 is truncated", "voice: reword under a new id"), SG.F("W", "note", "", "warn")], "E02")
    assert "VOICE-RATE" in b and "reword under a new id" in b and "`W`" not in b and "daily.py run --ep E02" in b and "inputs changed" in b


# ------------------------------------------------------------------ the early preview's analysis (tools/animatic.py)
def st(line, unit, active, start, end, words=("كلمة", "ثانية"), gloss=None):
    return {"line": line, "unit": unit, "words": list(words), "lines": [[0, 1]], "active": active, "start": start, "end": end, "style": None, "cap_y": None, "gloss": gloss or [], "gloss_pairs": [],
            "text": " ".join(words), "word_i": active, "word_start": start, "word_end": end, "n_lines": 1, "clause_words": len(words), "split": False}


def an_setup(tmp_path):
    root, ctx = plan_setup(tmp_path)
    tl = build_timeline(ctx)
    s = script_ok()
    for l in s["lines"]:
        l["text"] = "كلمة ثانية"
        l["tts_text"] = "كَلِمَةٌ ثَانِيَةٌ"
    return tl, plan_ok(), s


def test_the_preview_finds_two_plates_on_screen_together(tmp_path):
    tl, plan, s = an_setup(tmp_path)
    states = [st("L1", 0, 0, 1.0, 2.5), st("L1", 0, 1, 2.0, 3.5)]               # the second starts before the first ends
    got = animatic.caption_findings(states, tl, plan, s, {"كلمة": 300.0, "ثانية": 300.0}, [], {"foreign_keys": {}, "loanwords": {}})
    assert "CALM-ONE-PLATE" in ids(got)


def test_the_preview_finds_a_plate_up_too_briefly_to_read(tmp_path):
    tl, plan, s = an_setup(tmp_path)
    states = [st("L1", 0, 0, 1.0, 1.2), st("L1", 0, 1, 1.2, 1.4)]               # 0.4 s for a sentence
    got = animatic.caption_findings(states, tl, plan, s, {"كلمة": 300.0, "ثانية": 300.0}, [], {"foreign_keys": {}, "loanwords": {}})
    assert ids(got) & {"CAP-READING-SPEED", "CAP-READ-TIME"}
    assert all("before any shot is rendered" in f["fix"] for f in got if f["id"] in ("CAP-READING-SPEED", "CAP-READ-TIME"))


def test_the_preview_accepts_well_timed_plates_and_flags_an_uncaptioned_line_and_a_wide_plate(tmp_path):
    tl, plan, s = an_setup(tmp_path)
    ok = [st("L1", 0, 0, 1.0, 2.0), st("L1", 0, 1, 2.0, 4.0)]
    px = {"كلمة": 300.0, "ثانية": 300.0}
    got = animatic.caption_findings(ok, tl, plan, s, px, [], {"foreign_keys": {}, "loanwords": {}})
    assert "ANI-CAP-COVER" in ids(got)                                          # L2..L5 are spoken in the timeline and have no plate
    assert not ids(got) & {"CALM-ONE-PLATE", "CAP-READING-SPEED", "CAP-READ-TIME"}
    wide = animatic.caption_findings(ok, tl, plan, s, {"كلمة": 700.0, "ثانية": 700.0}, [], {"foreign_keys": {}, "loanwords": {}})
    assert "CALM-PLATE-SAFE" in ids(wide)


def test_the_preview_flags_a_plate_outside_the_item_that_speaks_it_and_tashkeel(tmp_path):
    tl, plan, s = an_setup(tmp_path)
    states = [st("L1", 0, 0, 40.0, 41.0), st("L1", 0, 1, 41.0, 43.0)]            # L1 is spoken in the first scene
    got = animatic.caption_findings(states, tl, plan, s, {"كلمة": 300.0, "ثانية": 300.0}, [], {"foreign_keys": {}, "loanwords": {}})
    assert ids(got) >= {"ANI-CAP-WINDOW"} or "ANI-CAP-WINDOW" in {f["id"] for f in got}
    tashkeel = [st("L1", 0, 0, 1.0, 2.0, words=("كَلِمَةٌ", "ثانية")), st("L1", 0, 1, 2.0, 4.0, words=("كَلِمَةٌ", "ثانية"))]
    assert "CALM-NO-TASHKEEL" in ids(animatic.caption_findings(tashkeel, tl, plan, s, {}, [], {"foreign_keys": {}, "loanwords": {}}))


def test_plate_width_uses_the_measured_word_widths_and_the_plate_padding():
    s = st("L1", 0, 0, 0, 1)
    w = animatic.plate_px_width(s, {"كلمة": 300.0, "ثانية": 200.0})
    assert w == pytest.approx(300 + 200 + 2 * 2 * 0.22 * cc.CAP_FONT_PX + 2 * cc.CAP_PAD_X)


def test_the_preview_length_and_narrator_checks(tmp_path):
    root, ctx = plan_setup(tmp_path)
    tl = build_timeline(ctx, n=2, dur=4.0)
    ep = cc.Ep("E01", root)
    s = script_ok(2)       # format v2 (2026-10-28): all narrator = 100 % of the voice time, over the 25 % ceiling (E03 on)
    plan = {**plan_ok(), "episode": "E03", "scenes": plan_ok()["scenes"][:2]}
    got = animatic.timing_findings(ep, tl, plan, s, {"L1": 2.0, "L2": 2.0})
    assert {"CALM-LENGTH", "NARRATOR-SHARE"} <= ids(got)
    for l in s["lines"]:
        l["speaker"] = "hero"
    assert "NARRATOR-SHARE" not in ids(animatic.timing_findings(ep, tl, plan, s, {"L1": 2.0, "L2": 2.0}))
    assert "NARRATOR-SHARE" not in ids(animatic.timing_findings(ep, tl, {**plan, "episode": "E02"}, script_ok(2), {"L1": 2.0, "L2": 2.0}))      # E01 and E02 keep the old format


def test_the_preview_video_has_a_box_per_plate_and_a_bar_per_take(tmp_path, monkeypatch):
    root, ctx = plan_setup(tmp_path)
    tl = build_timeline(ctx)
    ep = cc.Ep("E01", root)
    calls = {}
    monkeypatch.setattr(cc, "ff", lambda args, **k: calls.setdefault("args", [str(a) for a in args]))
    ctx.work.mkdir(parents=True, exist_ok=True)
    states = [st("L1", 0, 0, 1.0, 2.0), st("L1", 0, 1, 2.0, 3.0, gloss=["معنى"])]
    out = ctx.work / "animatic" / "animatic.mp4"
    out.parent.mkdir()
    animatic.build_video(ep, tl, states, [], {"كلمة": 300.0, "ثانية": 300.0}, {f"L{i}": 2.0 for i in range(1, 6)}, out)
    g = out.with_suffix(".filtergraph").read_text(encoding="utf-8")
    assert g.count("0xf4f4f4") == 1 and g.count("0xf2d030") == 1 and g.count("0x3ddc84") == 5          # white plate, yellow glossed plate, one green voice bar per take
    assert any("270x480" in a for a in calls["args"]) and "-crf" in calls["args"]


# ------------------------------------------------------------------ the stage bodies that connect the early preview to compose
def test_s_plan_turns_a_plan_failure_into_a_stage_failure_with_its_check_id(tmp_path, monkeypatch):
    root, ctx = plan_setup(tmp_path)
    monkeypatch.setattr(cc, "stage_plan", lambda ep: (_ for _ in ()).throw(cc.Fail("PLAN-DURATION", "scene s3 would last 12 s")))
    with pytest.raises(daily.StageFail) as e:
        daily.s_plan(ctx)
    assert e.value.code == "PLAN-DURATION"


def test_s_animatic_runs_the_preview_once_and_lets_its_findings_reach_the_verify(tmp_path):
    root, ctx = plan_setup(tmp_path)
    seen = []
    ctx.uv = lambda script, *a, **k: seen.append((script, a, k.get("ok"))) or "WARN x\n[animatic] FAIL {}\n"
    info = daily.s_animatic(ctx)
    assert seen == [("animatic.py", ("build", "E01"), (0, 1))] and "FAIL" in info["animatic"]


def test_compose_reuses_the_animatics_mix_only_while_the_animatic_is_fresh(tmp_path):
    root, ctx = plan_setup(tmp_path)
    build_timeline(ctx)
    (ctx.work / "animatic").mkdir()
    (ctx.work / "animatic" / "report.json").write_text(json.dumps({"findings": [], "plates": []}), encoding="utf-8")
    (ctx.work / "mix.wav").write_bytes(b"mix")
    (ctx.work / "sfx.json").write_text("{}", encoding="utf-8")
    (ctx.work / "audio" / "stems").mkdir(parents=True)
    st = daily.STAGES["animatic"]
    ctx.state["stages"]["animatic"] = {"status": "ok", "inputs": SG.fingerprint(st.inputs(ctx)), "outputs": SG.fingerprint(st.out_spec(ctx)), "verify": {"status": "pass"}}
    assert daily.stage_state(ctx, st)[0] == "fresh" and daily.audio_reusable(ctx)
    calls = []
    ctx.uv = lambda script, *a, **k: calls.append(a[0]) or "ok\n"
    info = daily.s_compose(ctx)
    assert calls == ["captions", "assemble"] and "reused" in info["audio"]
    write_wav(root / "work" / "voice" / "E01" / "L1.trimmed.wav", 3.0)          # a take changed: the mix is no longer the animatic's
    assert not daily.audio_reusable(ctx)
    calls.clear()
    daily.s_compose(ctx)
    assert calls == ["captions", "audio", "assemble"]


def test_the_spoken_recap_hook_line_is_a_used_line():
    plan = {"scenes": [{"line": "L01"}], "hook": {"pattern": 1, "line": "H01"}, "choice": {}}
    assert SG.plan_line_ids(plan) == {"L01", "H01"}
