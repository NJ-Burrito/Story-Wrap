"""LINE-FIT and LINE-REFIT (the owner 2026-10-30, R-502): a voiced line that is too long for its slot never parks an episode.
Prevention: tools/line_fit.py estimates every line at the script stage. Cure: tools/line_refit.py rewords ONLY the over-long line under a new id, the voice stage voices only that id once,
the plan runs again. The E05 case is reproduced from the real numbers: the recap line H01 (22 letters) took 3.34 s, the card allows 3.0 s. No model, no GPU, no network."""
import copy
import datetime as dt
import json
import re
import wave
from pathlib import Path

import pytest

import autopilot as ap
import calm_compose as cc
import daily
import line_fit as LF
import line_refit as LR
import voice
from test_daily import ctx_for, mk_root, plan_ok, script_ok
from test_voice import cast_with_refs, ep, fake_engine, make_manifest, write_receipt   # noqa: F401  (ep is a fixture)
import sw_fixtures

pytestmark = pytest.mark.usefixtures("neutral_project")      # the plan checks read the neutral fixture project, not a user's own series

E05_H01 = {"text": "هدى تراقب الفتحة النحاسية.", "tts_text": "هُدَى تُرَاقِبُ الْفَتْحَةَ النُّحَاسِيَّةَ."}      # the real E05 recap line: 22 letters, took 3.34 s, the card allows 2.45 s
SHORT = {"text": "هدى عند الفتحة.", "tts_text": "هُدَى عِنْدَ الْفَتْحَةِ."}                                                          # 12 letters
LONG = {"text": "هدى تراقب الفتحة النحاسية الآن.", "tts_text": "هُدَى تُرَاقِبُ الْفَتْحَةَ النُّحَاسِيَّةَ الْآنَ."}


@pytest.fixture(autouse=True)
def no_real_facebook_token(monkeypatch):
    """R-507: the autopilot also retries a missing Facebook half; the real ~/.config token must not decide a test that has no Facebook record."""
    import loop_gate as _lg
    orig = _lg.has_fb_token
    monkeypatch.setattr(_lg, "has_fb_token", lambda env_path=None: orig(env_path) if env_path else False)


def wav(path, seconds):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(16000)
        w.writeframes(b"\x00\x00" * int(16000 * seconds))


def e05_files(hook=E05_H01):
    """plan_ok / script_ok with the hook renamed H01 (as in E05) and the hook line's text replaced."""
    p, s = plan_ok(), script_ok()
    p["hook"]["line"] = "H01"
    for l in s["lines"]:
        if l["id"] == "H1":
            l.update({"id": "H01", **hook})
    return p, s


def e05_root(tmp_path, h01_s=3.34):
    root = mk_root(tmp_path)
    ed = root / "bible" / "series" / "series" / "episodes" / "E02"
    p, s = e05_files()
    (ed / "calm-plan.json").write_text(json.dumps(p, ensure_ascii=False), encoding="utf-8")
    (ed / "script.json").write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")
    for lid, sec in [("H01", h01_s)] + [(f"L{i}", 3.0) for i in range(1, 6)]:
        wav(root / "work" / "voice" / "E02" / f"{lid}.trimmed.wav", sec)
    return root, ed


def writer_stub(calls, answers):
    """A refit writer: writes the JSON file named in the prompt. `answers` is a list of dicts, one per call (the last repeats)."""
    def llm(prompt, *, name, tools, **kw):
        calls.append((name, prompt))
        out = re.search(r"Write ONE file, (\S+),", prompt).group(1)
        a = answers[min(len(calls) - 1, len(answers) - 1)]
        Path(out).write_text(json.dumps({**a, "foreign": []}, ensure_ascii=False), encoding="utf-8")
        return {"rc": 0, "text": "ok", "err": "", "tokens": 100, "cost": None, "missing": [], "seconds": 0.1}
    return llm


def wire(monkeypatch, voice_s=2.0, valid=lambda c: []):
    """The stage table of a unit run: the real plan stage (real arithmetic), a voice stage that checks the refit marker and writes one take per line that has none."""
    made = []

    def fake_voice(ctx):
        sc = json.loads((ctx.ep_dir / "script.json").read_text(encoding="utf-8"))
        assert voice.superseded_log(ctx.root / "work" / "voice" / ctx.ep).exists(), "the refit marker must come before the voice stage"
        for l in sc["lines"]:
            tk = ctx.root / "work" / "voice" / ctx.ep / f"{l['id']}.trimmed.wav"
            if not tk.exists():
                wav(tk, voice_s)
                made.append(l["id"])
        return {}
    monkeypatch.setitem(daily.STAGES, "plan", daily.Stage("plan", daily.s_plan, lambda c: [c.work / "timeline.json"], "io"))
    monkeypatch.setitem(daily.STAGES, "voice", daily.Stage("voice", fake_voice, lambda c: [], "machine"))
    monkeypatch.setattr(daily, "require_upstream", lambda *a, **k: None)
    monkeypatch.setattr(daily, "validate_episode_files", valid)
    return made


# ------------------------------------------------------------------ the limits and the estimate
def test_the_slot_limits_are_the_plan_stages_own_numbers():
    caps = LF.slot_caps(plan_ok())
    assert caps["H1"] == {"slot": "recap", "ref": "recap", "max_s": 2.45}                              # RECAP_MAX_S 3.0 - lead 0.2 - pad 0.35
    assert caps["L1"]["slot"] == "scene" and caps["L1"]["max_s"] == 9.45                              # MAX_SCENE_S 10 - 0.55
    assert caps["L1"]["max_s"] == pytest.approx(cc.MAX_SCENE_S - cc.VOICE_LEAD_S - cc.PAD_S)
    assert LF.choice_budget() == pytest.approx(cc.MAX_CHOICE_S - cc.JOIN_S - 0.3 - 3 * cc.CHOICE_GAP_S - cc.CHOICE_TAIL_S, abs=0.01)


def test_rates_are_measured_not_invented():
    r = LF.load_rates()
    assert r["samples"]["narrator"] >= 20 and r["samples"]["dialogue"] >= 20 and 0.08 < r["model"]["narrator"]["b"] < 0.2 and 0 < r["model"]["narrator"]["a"] < 2 and r["margin"] >= 1.0
    assert LF.letters(E05_H01["tts_text"]) == 22


def test_the_e05_recap_line_is_caught_before_it_is_voiced():
    p, s = e05_files()
    bad = LF.script_problems(p, s)
    assert len(bad) == 1 and bad[0].startswith("SCRIPT-FIT line H01 (recap recap)") and "at most" in bad[0]
    p, s = e05_files(SHORT)
    assert LF.script_problems(p, s) == []
    # the E02..E04 hooks (12 to 14 letters, 1.8 to 2.2 s as voiced) are not turned away
    assert LF.estimate_s({"speaker": "narrator", "tts_text": "ا" * 14}) <= 2.45
    p, s = e05_files()                                                                                      # no false alarm on a long scene line: E05 L07 (60 letters) really took 8.42 s
    s["lines"][0].update({"speaker": "hero", "tts_text": "ا" * 60})
    assert not any("line L1 " in b for b in LF.script_problems(p, s))


def test_a_choice_sequence_over_its_budget_names_the_longest_line():
    p, s = plan_ok(), script_ok()
    p["choice"]["lines"] = {"question": "Q1", "choice1": "C1", "choice2": "C2", "hook": "K1"}
    s["lines"] += [{"id": i, "speaker": "narrator", "text": "x", "tts_text": "ا" * n} for i, n in (("Q1", 30), ("C1", 25), ("C2", 25), ("K1", 20))]    # 100 letters = 17 s aloud
    bad = LF.script_problems(p, s)
    assert len(bad) == 1 and "choice sequence" in bad[0] and "shorten line Q1" in bad[0]


def test_the_writer_brief_carries_the_limits():
    b = LF.brief_block()
    assert "SLOT LIMITS" in b and "2.45 s" in b and "9.45 s" in b and "Arabic letters" in b
    assert "{fit}" in daily.WRITER_PROMPT


# ------------------------------------------------------------------ prevention at the script stage
def script_ctx(tmp_path, monkeypatch, answers):
    root = mk_root(tmp_path)
    ed = root / "bible" / "series" / "series" / "episodes" / "E02"
    monkeypatch.setattr(daily, "validate_episode_files", lambda c: [])
    calls = []

    def write(hook):
        p, s = e05_files(hook)
        (ed / "calm-plan.json").write_text(json.dumps(p, ensure_ascii=False), encoding="utf-8")
        (ed / "script.json").write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")
        (ed / "caption.txt").write_text("سطر #أ #ب #ج", encoding="utf-8")

    def llm(prompt, *, name, tools, **kw):
        calls.append((name, prompt))
        write(answers[min(len(calls) - 1, len(answers) - 1)])
        return {"rc": 0, "text": "ok", "err": "", "tokens": 10, "cost": None, "missing": [], "seconds": 0.1}
    return ctx_for(root, llm=llm), calls


def test_a_line_over_its_slot_goes_back_to_the_writer_before_any_voice(tmp_path, monkeypatch):
    ctx, calls = script_ctx(tmp_path, monkeypatch, [E05_H01, SHORT])
    info = daily.s_script(ctx)
    assert [n for n, _ in calls] == ["writer-E02", "writer-fix-E02"] and "fit_warnings" not in info
    assert "SLOT LIMITS" in calls[0][1] and "SCRIPT-FIT line H01" in calls[1][1] and "at most" in calls[1][1]


def test_a_writer_that_cannot_fit_a_line_never_stops_the_script_stage(tmp_path, monkeypatch):
    ctx, calls = script_ctx(tmp_path, monkeypatch, [E05_H01])
    info = daily.s_script(ctx)
    assert len(calls) == 1 + daily.FIT_REPAIR_ROUNDS and info["fit_warnings"] and info["fit_warnings"][0].startswith("SCRIPT-FIT line H01")   # the refit cures it after voicing


# ------------------------------------------------------------------ the E05 case end to end
def test_e05_the_recap_take_of_3_88_s_is_refit_and_the_plan_passes(tmp_path, monkeypatch):
    root, ed = e05_root(tmp_path)
    ctx = ctx_for(root, limit=10_000_000)
    with pytest.raises(cc.Fail) as e:                                        # the failure that parked E05 on 2026-10-30
        cc.stage_plan(cc.Ep("E02", root))
    assert e.value.cid == "PLAN-DURATION" and "3.88 s" in e.value.msg
    made = wire(monkeypatch)
    calls = []
    monkeypatch.setattr(ctx, "_llm", lambda prompt, **kw: writer_stub(calls, [SHORT])(prompt, name=kw["name"], tools=kw["tools"]))
    assert daily.run_list(ctx, ["plan"]) == 0
    assert not (ctx.dir / "STOPPED.md").exists() and len(calls) == 1 and made == ["H01r1"]               # one writer call, ONE take, only the new id
    script = json.loads((ed / "script.json").read_text(encoding="utf-8"))
    plan = json.loads((ed / "calm-plan.json").read_text(encoding="utf-8"))
    ids = [l["id"] for l in script["lines"]]
    assert "H01" not in ids and ids.index("H01r1") == 5 and plan["hook"]["line"] == "H01r1"            # replaced in place, the plan points at the new id
    assert script["lines"][5]["text"] == SHORT["text"] and script["lines"][5]["refit"]["of"] == "H01" and script["lines"][5]["refit"]["was_s"] == 3.34
    tl = json.loads(cc.Ep("E02", root).timeline_p.read_text(encoding="utf-8"))
    assert tl["items"][0]["line"] == "H01r1" and tl["items"][0]["dur"] <= cc.RECAP_MAX_S                # the recap card now fits its 3.0 s cap
    assert (root / "work" / "voice" / "E02" / "H01.trimmed.wav").exists()                               # the old take is kept, unused
    rec = LR.load_record(root, "E02")
    assert rec["lines"]["H01"] == {"rounds": 1, "chain": ["H01", "H01r1"]} and rec["events"][0]["event"] == "refit" and rec["exhausted"] is None


def test_a_rewrite_that_is_still_too_long_is_asked_again_with_the_failure_named(tmp_path, monkeypatch):
    root, ed = e05_root(tmp_path)
    ctx = ctx_for(root, limit=10_000_000)
    wire(monkeypatch)
    calls = []
    monkeypatch.setattr(ctx, "_llm", lambda prompt, **kw: writer_stub(calls, [LONG, SHORT])(prompt, name=kw["name"], tools=kw["tools"]))
    assert daily.run_list(ctx, ["plan"]) == 0
    assert len(calls) == 2 and "too long" in calls[1][1]


def test_at_most_two_rounds_per_line_then_the_run_stops_as_before(tmp_path, monkeypatch):
    root, ed = e05_root(tmp_path)
    ctx = ctx_for(root, limit=10_000_000)
    wire(monkeypatch, voice_s=3.5)                                                # every new take is still too long
    calls = []
    monkeypatch.setattr(ctx, "_llm", lambda prompt, **kw: writer_stub(calls, [SHORT])(prompt, name=kw["name"], tools=kw["tools"]))
    assert daily.run_list(ctx, ["plan"]) == 1
    rec = LR.load_record(root, "E02")
    assert rec["lines"]["H01"]["chain"] == ["H01", "H01r1", "H01r2"] and rec["lines"]["H01"]["rounds"] == LR.MAX_ROUNDS_PER_LINE == 2
    assert "PLAN-DURATION" in (ctx.dir / "STOPPED.md").read_text(encoding="utf-8") and len(calls) == 2
    assert LR.cure(ctx, None) is False and LR.load_record(root, "E02")["exhausted"]["reason"] == "rounds"
    assert not LR.refit_possible(root, "E02")


def test_a_rewrite_that_breaks_the_episode_checks_is_rolled_back_byte_for_byte(tmp_path, monkeypatch):
    root, ed = e05_root(tmp_path)
    ctx = ctx_for(root, limit=10_000_000)
    wire(monkeypatch, valid=lambda c: ["PLAN-GLOSS a word has no gloss"])
    before = {n: (ed / n).read_bytes() for n in ("script.json", "calm-plan.json")}
    calls = []
    monkeypatch.setattr(ctx, "_llm", lambda prompt, **kw: writer_stub(calls, [SHORT])(prompt, name=kw["name"], tools=kw["tools"]))
    assert daily.run_list(ctx, ["plan"]) == 1
    assert {n: (ed / n).read_bytes() for n in before} == before and not voice.superseded_log(root / "work" / "voice" / "E02").exists()
    assert LR.load_record(root, "E02")["failed_rounds"] == 1


def test_no_refit_when_the_day_s_token_budget_or_the_machine_cap_is_spent(tmp_path, monkeypatch):
    root, ed = e05_root(tmp_path)
    wire(monkeypatch)
    ctx = ctx_for(root, limit=1000)                                                # under MIN_TOKENS_LEFT
    ctx._llm = lambda *a, **k: pytest.fail("no writer call without budget")
    assert LR.cure(ctx, None) is False
    ex = LR.load_record(root, "E02")["exhausted"]
    assert ex["reason"] == "budget" and not LR.refit_possible(root, "E02", ex["date"]) and LR.refit_possible(root, "E02", "2099-01-01")   # tomorrow it may try again
    ctx2 = ctx_for(root, limit=10_000_000, cap_s=100)
    ctx2._llm = lambda *a, **k: pytest.fail("no writer call without machine time")
    assert LR.cure(ctx2, None) is False and LR.load_record(root, "E02")["exhausted"]["reason"] == "cap"


def test_at_most_six_different_lines_per_episode(tmp_path, monkeypatch):
    root, ed = e05_root(tmp_path)
    ctx = ctx_for(root, limit=10_000_000)
    rec = LR.load_record(root, "E02")
    rec["lines"] = {f"X{i}": {"rounds": 1, "chain": [f"X{i}", f"X{i}r1"]} for i in range(LR.MAX_LINES_PER_EPISODE)}
    LR.save_record(root, "E02", rec)
    ctx._llm = lambda *a, **k: pytest.fail("the script needs the writer, not the refit")
    assert LR.cure(ctx, None) is False and LR.load_record(root, "E02")["exhausted"]["reason"] == "lines"


def test_a_take_that_fits_is_not_touched(tmp_path, monkeypatch):
    root, ed = e05_root(tmp_path, h01_s=2.0)
    ctx = ctx_for(root, limit=10_000_000)
    ctx._llm = lambda *a, **k: pytest.fail("nothing overruns")
    assert LR.find_overruns(ctx) == [] and LR.cure(ctx, None) is False


# ------------------------------------------------------------------ the other slots, the ids, the plan edit
def test_overruns_of_scene_intro_and_choice_slots_use_the_plan_stages_arithmetic():
    p = plan_ok()
    p["intros"][0]["line"] = "I1"
    p["choice"]["lines"] = {"question": "Q1", "choice1": "C1", "choice2": "C2", "hook": "K1"}
    secs = {"H1": 2.4, "L1": 9.6, "L2": 9.4, "I1": 8.6, "Q1": 5.0, "C1": 4.0, "C2": 4.0, "K1": 3.0}       # 16 s of choice speech against 13.7
    got = {o["line"]: o for o in LF.overruns(p, secs)}
    assert set(got) == {"L1", "I1", "Q1"} and got["L1"]["slot"] == "scene" and got["I1"]["slot"] == "intro"            # 9.6 + 0.55 > 10; 8.6 + 0.55 > 9.0
    assert "H1" not in got and "L2" not in got
    assert got["Q1"]["slot"] == "choice" and got["Q1"]["max_s"] == pytest.approx(5.0 - (16 - LF.choice_budget() + 0.3), abs=0.01)     # the longest choice line gives back the excess
    msg = "scene s3 would last 11.60 s with its reading pause: shorten the line"
    assert [o["line"] for o in LF.overruns(p, {"L3": 9.4}, msg)] == ["L3"]                                    # only the message knows a reading pause pushed it over


def test_line_ids_chain_and_the_plan_follows():
    assert [LR.next_id(i) for i in ("H01", "H01r1", "L12")] == ["H01r1", "H01r2", "L12r1"] and LR.base_id("H01r2") == "H01" and LR.round_of("L12") == 0
    p = plan_ok()
    p["written"] = {"line": "L2"}
    p["choice"]["line"] = "L2"
    p["choice"]["lines"] = {"question": "L2", "choice1": "L3", "choice2": "L4", "hook": "L5"}
    p["intros"][0]["line"] = "L2"
    assert LR.replace_line_id(p, "L2", "L2r1") == 5 and '"L2"' not in json.dumps(p)                              # scene, intro, written, choice.line, choice.lines.question
    assert p["scenes"][1]["line"] == "L2r1" and p["choice"]["lines"]["question"] == "L2r1"


def test_a_candidate_must_keep_its_letters_and_carry_tashkeel_only_in_tts():
    assert LR.candidate_problems(SHORT) == []
    assert LR.candidate_problems({"text": "هُدَى", "tts_text": "هُدَى"})                                       # tashkeel in the caption
    assert LR.candidate_problems({"text": "هدى", "tts_text": "هدى"})                                           # no vowels for the voice
    assert LR.candidate_problems({"text": "هدى عند", "tts_text": "هُدَى"})                                     # different letters
    assert LR.candidate_problems({"text": "", "tts_text": ""})


def test_calibrate_reads_the_narration_manifests(tmp_path):
    d = tmp_path / "bible" / "series" / "s" / "episodes" / "E01"
    d.mkdir(parents=True)
    lines = [{"id": f"L{i}", "speaker": "narrator" if i % 2 else "hero", "tts_text": "ا" * (10 + i), "seconds": 0.5 + 0.13 * (10 + i)} for i in range(10)]    # exactly 0.13 s a letter after 0.5 s
    (d / "narration-manifest.json").write_text(json.dumps({"lines": lines}), encoding="utf-8")
    r = LF.calibrate(tmp_path)
    assert r["samples"] == {"narrator": 5, "dialogue": 5} and r["model"]["narrator"]["b"] == pytest.approx(0.13, abs=0.001) and r["model"]["narrator"]["a"] == pytest.approx(0.5, abs=0.01)


# ------------------------------------------------------------------ the voice stage voices only the new id, once
@sw_fixtures.needs_project("voice casting (bible/series/<series>/voices/casting.json) and its reference clips", "bible/series/series/voices/casting.json")
def test_refit_mark_lets_the_voice_stage_voice_only_the_new_id(ep):
    paths, root = ep
    cast_with_refs(root)
    make_manifest(paths)
    write_receipt(paths)
    assert voice.cmd_voice(paths, go=True, repo=root, synth=fake_engine) == 0
    s = voice.read_json(paths["script"])
    s["lines"][1] = {**s["lines"][1], "id": "l02r1"}                                                           # l02 was too long: reworded under a new id
    voice.write_json(paths["script"], s)
    make_manifest(paths)
    write_receipt(paths)
    with pytest.raises(voice.Fail) as e:                                                                     # without the marker a settled take is never touched
        voice.cmd_voice(paths, go=True, repo=root, synth=fake_engine)
    assert e.value.cid == "VOICE-ONCE"
    assert voice.cmd_refit_mark(paths, "l02", "l02r1", "over its slot") == "l02r1"
    seen = []
    assert voice.cmd_voice(paths, go=True, repo=root, synth=lambda job: (seen.extend(j["id"] for j in job["lines"]), fake_engine(job))) == 0
    work = paths["work"]
    assert seen == ["l02r1"] and (work / "l02r1.wav").exists() and (work / "l02.wav").exists() and (work / "l01.wav").exists()      # one take for the new id; the old takes untouched
    with pytest.raises(voice.Fail):                                                                          # a second refit-mark of the same new id is a re-voice: refused
        voice.cmd_refit_mark(paths, "l02", "l02r1", "again")
    with pytest.raises(voice.Fail):
        voice.cmd_refit_mark(paths, "l01", "l01", "same id")


# ------------------------------------------------------------------ the autopilot
NOW = dt.datetime(2026, 10, 30, 15, 0)


def stopped_plan_duration(root, ep="E05"):
    d = root / "work" / "daily" / ep
    d.mkdir(parents=True, exist_ok=True)
    (d / "STOPPED.md").write_text("# stopped\n\n`FAIL [PLAN-DURATION]` the spoken recap H01 would last 3.88 s\n", encoding="utf-8")
    (d / "STATE.json").write_text(json.dumps({"episode": ep, "stages": {"script": {"status": "ok"}}}), encoding="utf-8")


def test_plan_duration_is_not_a_terminal_stop_while_the_refit_has_rounds_left(tmp_path):
    stopped_plan_duration(tmp_path)
    st = ap.load_state(tmp_path)
    assert ap.record_failure(tmp_path, st, "E05", 1, NOW) is False and ap.refit_pending(tmp_path, "E05", NOW)    # not terminal: the next run refits by itself
    rec = LR.load_record(tmp_path, "E05")
    rec["exhausted"] = {"reason": "rounds", "date": "2026-10-30"}
    LR.save_record(tmp_path, "E05", rec)
    st2 = ap.load_state(tmp_path)
    assert ap.record_failure(tmp_path, st2, "E05", 1, NOW) is True and not ap.refit_pending(tmp_path, "E05", NOW)   # spent: the Lead is called
    (tmp_path / "work" / "daily" / "E05" / "STOPPED.md").write_text("`FAIL [CRITIC-LOW]` x", encoding="utf-8")
    assert not ap.refit_pending(tmp_path, "E05", NOW)


def test_an_episode_stopped_by_plan_duration_is_not_stuck_after_three_failures(tmp_path):
    """E05 on 2026-10-30: three failures made it STUCK until tomorrow. With the refit it is finished again at the next tick."""
    def wj(p, d):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(d), encoding="utf-8")
    wj(tmp_path / "work" / "episodes" / "E04" / "post.json", {"episode": "E04", "posted_at": "2026-10-29T21:05:00"})
    wj(tmp_path / "work" / "episodes" / "E04" / "decision.json", {"episode": "E04"})
    stopped_plan_duration(tmp_path)
    st = ap.load_state(tmp_path)
    st["attempts"]["E05"] = {"date": "2026-10-30", "n": 3, "last_code": "PLAN-DURATION", "at": "2026-10-30T14:30:00"}
    nxt = lambda root: "E05"      # noqa: E731
    assert ap.decide(tmp_path, NOW, nxt, st)["action"] == "finish"
    rec = LR.load_record(tmp_path, "E05")
    rec["exhausted"] = {"reason": "rounds", "date": "2026-10-30"}
    LR.save_record(tmp_path, "E05", rec)
    assert ap.decide(tmp_path, NOW, nxt, st)["action"] == "stuck"


def test_the_lead_may_choose_refit_line_and_nothing_else_new(tmp_path):
    assert "refit-line" in ap.LEAD_ACTIONS
    d = ap.parse_lead_decision('{"action": "refit-line", "line": "H01", "reason": "recap over its card"}')
    assert d["action"] == "refit-line" and d["line"] == "H01" and d["stage"] is None
    assert ap.parse_lead_decision('{"action": "refit-line", "line": "../x"}')["line"] == ""                    # a line id is letters and digits only
    assert ap.parse_lead_decision('{"action": "rerun-stage", "stage": "voice"}')["action"] == "give-up"      # the voice stage still cannot be forced
    state = ap.load_state(tmp_path)
    state["needs_lead"] = {"ep": "E05", "code": "PLAN-DURATION"}
    ap.save_state(tmp_path, state)

    def llm(prompt, name):
        dd = tmp_path / "work" / "daily"
        (dd / "autopilot-lead-2026-10-30.md").write_text("cause: the recap\n", encoding="utf-8")
        (dd / "autopilot-lead-2026-10-30.json").write_text(json.dumps({"action": "refit-line", "reason": "recap over its card"}), encoding="utf-8")
        assert "refit-line" in prompt
        return {"rc": 0}
    seen = []
    rc, line = ap.lead_once(tmp_path, NOW, llm=llm, refit=lambda e, line="": seen.append((e, line)) or (0, "resumed"), build=lambda *a: pytest.fail("not a rerun"))
    assert rc == 0 and seen == [("E05", "")] and "refit-line" in line


def test_the_daily_cli_has_the_refit_command():
    import argparse
    src = Path(daily.__file__).read_text(encoding="utf-8")
    assert 'sub.add_parser("refit"' in src and "daily.py refit --ep E05" in src
