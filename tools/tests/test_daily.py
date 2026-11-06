"""The daily pipeline (tools/daily.py, tools/calm_compose.py): stages, the 4 h cap, free-only, the headless Claude call, the critic loop, resume. No model, no GPU, no network."""
import json
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import calm_compose as cc
import daily
import sw_fixtures

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _neutral_project(monkeypatch):
    """Plan checks read the series glossary under calm_compose.ROOT: use the neutral fixture project, not a user's own series."""
    monkeypatch.setattr(cc, "ROOT", sw_fixtures.PROJECT)


def mk_root(tmp_path, ep="E02"):
    root = tmp_path / "repo"
    (root / "bible" / "series" / "series" / "episodes" / ep).mkdir(parents=True)
    (root / "work").mkdir()
    return root


def ctx_for(root, ep="E02", **kw):
    cfg = kw.pop("config", {})
    return daily.Ctx(ep, root=root, config=cfg, budget=daily.Budget(root, limit=kw.pop("limit", 1000), today="2026-10-25"), log=lambda *a: None, **kw)


# ------------------------------------------------------------------ the stage list and the dry run
def test_stage_order_is_the_briefs():
    assert daily.RUN_STAGES == ["votes", "script", "voice", "plan", "animatic", "shots", "compose", "gates", "critic", "retro"]   # retro: the build retro (tools/learn.py), never blocking
    assert daily.POST_STAGES == ["publish", "schedule", "yt_stories"]   # yt_stories: YouTube and stories after the Reels (post_extra.py)
    assert set(daily.STAGES) == set(daily.RUN_STAGES + daily.POST_STAGES)
    assert daily.MACHINE_STAGES >= {"voice", "animatic", "shots", "compose", "gates"} and "script" not in daily.MACHINE_STAGES and "critic" not in daily.MACHINE_STAGES


def test_cap_is_four_hours_and_the_critic_asks_twelve_questions():
    assert daily.CAP_S == 4 * 3600
    assert len(daily.CRITIC_QUESTIONS) == 13 and daily.CRITIC_QUESTIONS[0].startswith("Q01") and daily.CRITIC_QUESTIONS[-1].startswith("Q13")


def test_next_episode_counts_folders_and_posts(tmp_path):
    root = mk_root(tmp_path, "E01")
    assert daily.next_episode(root) == "E02"
    (root / "bible" / "series" / "series" / "episodes" / "E04").mkdir()
    assert daily.next_episode(root) == "E05"


def test_prev_episode():
    assert daily.prev_ep("E02") == "E01" and daily.prev_ep("E01") is None and daily.prev_ep("E10") == "E09"


# ------------------------------------------------------------------ free only
def test_paid_services_are_refused():
    for cfg in ({"voice_engine": "elevenlabs"}, {"voice_engine": "gemini"}, {"llm_model": "opus"}, {"llm_model": "haiku"}, {"publish": "buffer"}, {"openrouter": "x"}, {"llm_api_key": "x"}):
        with pytest.raises(daily.StageFail) as e:
            daily.assert_free(cfg)
        assert e.value.code == "PAID-SERVICE" and e.value.exit_code == 5
    daily.assert_free({"voice_engine": "chatterbox", "llm_model": "sonnet", "publish": "instagram-graph"})
    daily.assert_free(None)


def test_child_environment_never_carries_a_paid_key():
    env = daily.scrub_env({"PATH": "p", "OPENROUTER_API_KEY": "k", "GEMINI_API_KEY": "k", "ANTHROPIC_API_KEY": "k", "ELEVENLABS_API_KEY": "k", "KEEP": "1"})
    assert env["KEEP"] == "1" and env["PYTHONUTF8"] == "1"
    assert not any(k in env for k in daily.PAID_ENV)


def test_headless_command_is_sonnet_only_with_an_explicit_tool_list_and_no_agent():
    cmd = daily.build_cmd("claude.exe", "hi", tools="Read,Write")
    assert cmd[cmd.index("--model") + 1] == "sonnet" and cmd[cmd.index("--permission-mode") + 1] == "dontAsk" and "--no-session-persistence" in cmd
    assert cmd[cmd.index("--allowedTools") + 1] == "Read,Write" and "--max-budget-usd" in cmd and "--max-turns" in cmd
    for bad in ({"model": "opus"}, {"model": "haiku"}, {"tools": "Read,Agent"}, {"tools": "Task"}, {"tools": ""}, {"effort": "max"}):
        with pytest.raises(ValueError):
            daily.build_cmd("c", "x", **{"tools": "Read", **bad})


def test_run_claude_counts_tokens_checks_expected_files_and_scrubs_the_env(tmp_path):
    seen = {}
    out = tmp_path / "out.json"

    def runner(cmd, **kw):
        seen.update(cmd=cmd, env=kw["env"], cwd=kw["cwd"])
        out.write_text("{}", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout=json.dumps({"result": "done", "usage": {"input_tokens": 100, "output_tokens": 50, "cache_creation_input_tokens": 10, "cache_read_input_tokens": 9999}, "total_cost_usd": 0.1}), stderr="")
    b = daily.Budget(tmp_path, limit=1000, today="2026-10-25")
    import os
    os.environ["OPENROUTER_API_KEY"] = "secret"
    try:
        r = daily.run_claude("p", name="t", tools="Read,Write", root=tmp_path, expect=[out], budget=b, exe="claude.exe", runner=runner)
    finally:
        os.environ.pop("OPENROUTER_API_KEY", None)
    assert r["rc"] == 0 and r["tokens"] == 160 and b.data["tokens"] == 160          # cache reads are not new work
    assert seen["env"]["NJ_ROLE"] == "job" and "OPENROUTER_API_KEY" not in seen["env"]
    miss = daily.run_claude("p", name="t2", tools="Read", root=tmp_path, expect=[tmp_path / "never.json"], budget=b, exe="claude.exe", runner=runner)
    assert miss["rc"] == 3 and miss["missing"]


def test_token_budget_refuses_the_next_call(tmp_path):
    b = daily.Budget(tmp_path, limit=100, today="2026-10-25")
    b.add("a", 120)
    with pytest.raises(daily.StageFail) as e:
        b.check("writer")
    assert e.value.code == "LLM-BUDGET" and e.value.exit_code == 3
    assert daily.Budget(tmp_path, limit=100, today="2026-10-25").data["tokens"] == 120          # persisted


# ------------------------------------------------------------------ the 4 h cap, STATE, resume
def test_machine_stage_time_is_logged_and_capped(tmp_path):
    root = mk_root(tmp_path)
    ctx = ctx_for(root, cap_s=5)
    st = daily.Stage("voice", lambda c: {"takes": 3}, lambda c: [], "machine")
    daily.run_stage(ctx, st)
    e = ctx.state["stages"]["voice"]
    assert e["status"] == "ok" and e["seconds"] >= 0 and ctx.deadline["machine_s"] == e["seconds"]
    assert json.loads((root / "work" / "daily" / "E02" / "STATE.json").read_text(encoding="utf-8"))["stages"]["voice"]["info"] == {"takes": 3}
    ctx.deadline["machine_s"] = 5.0
    with pytest.raises(daily.StageFail) as x:
        daily.run_stage(ctx, daily.Stage("shots", lambda c: {}, lambda c: [], "machine"))
    assert x.value.code == "RENDER-CAP" and x.value.exit_code == 4


def test_llm_stages_do_not_count_against_the_render_cap(tmp_path):
    ctx = ctx_for(mk_root(tmp_path), cap_s=5)
    daily.run_stage(ctx, daily.Stage("critic", lambda c: (time.sleep(0.05), {})[1], lambda c: [], "llm"))
    assert ctx.deadline["machine_s"] == 0


def test_child_timeout_is_the_remaining_machine_time_and_a_cap_hit_kills_and_stops(tmp_path):
    seen = {}

    def run_proc(cmd, **kw):
        seen["timeout"] = kw["timeout"]
        raise subprocess.TimeoutExpired(cmd, kw["timeout"])
    ctx = ctx_for(mk_root(tmp_path), cap_s=100, run_proc=run_proc)
    ctx.deadline["machine_s"] = 40
    with pytest.raises(daily.StageFail) as e:
        ctx.sh(["x"], label="render")
    assert seen["timeout"] == 60 and e.value.code == "RENDER-CAP"


def test_a_stage_that_is_done_is_skipped_and_force_reruns_it(tmp_path):
    ctx = ctx_for(mk_root(tmp_path))
    out = tmp_path / "x.txt"
    n = {"k": 0}

    def body(c):
        n["k"] += 1
        out.write_text("1", encoding="utf-8")
    st = daily.Stage("script", body, lambda c: [out], "llm")
    assert daily.run_stage(ctx, st) == "ok" and daily.run_stage(ctx, st) == "skipped" and n["k"] == 1
    assert daily.run_stage(ctx, st, force=True) == "ok" and n["k"] == 2
    out.unlink()
    assert daily.run_stage(ctx, st) == "ok" and n["k"] == 3          # an output that vanished is rebuilt


def test_run_list_stops_at_the_first_failure_writes_stopped_md_and_returns_its_exit_code(tmp_path, monkeypatch):
    root = mk_root(tmp_path)
    ctx = ctx_for(root)
    calls = []
    monkeypatch.setitem(daily.STAGES, "votes", daily.Stage("votes", lambda c: calls.append("votes") or {}, lambda c: [], "io"))
    monkeypatch.setitem(daily.STAGES, "script", daily.Stage("script", lambda c: (_ for _ in ()).throw(daily.StageFail("LLM-BUDGET", "spent", 3)), lambda c: [], "llm"))
    monkeypatch.setitem(daily.STAGES, "voice", daily.Stage("voice", lambda c: calls.append("voice") or {}, lambda c: [], "machine"))
    rc = daily.run_list(ctx, ["votes", "script", "voice"])
    assert rc == 3 and calls == ["votes"]
    stop = (root / "work" / "daily" / "E02" / "STOPPED.md").read_text(encoding="utf-8")
    assert "LLM-BUDGET" in stop and "votes=ok" in stop and "script=failed" in stop


def test_votes_stage_skips_without_a_posted_previous_episode_or_a_token(tmp_path):
    root = mk_root(tmp_path)
    ctx = ctx_for(root)
    assert daily.s_votes(ctx)["_status"] == "skipped"                                     # E02 but E01 not posted
    (root / "work" / "episodes" / "E01").mkdir(parents=True)
    (root / "work" / "episodes" / "E01" / "post.json").write_text("{}", encoding="utf-8")
    import os
    os.environ["SW_IG_ENV"] = str(tmp_path / "no-such.env")
    try:
        assert "token" in daily.s_votes(ctx)["why"]
    finally:
        os.environ.pop("SW_IG_ENV", None)


# ------------------------------------------------------------------ the critic loop
def good_critic(score=9):
    return json.dumps({"score": score, "answers": [{"q": f"Q{i:02d}", "ok": True, "evidence": "frame-0.png"} for i in range(1, 13)], "faults": [{"q": "Q03", "fix_place": "plan", "what": "scene 3 too long"}]})


def test_critic_json_must_answer_every_question():
    assert daily.parse_critic("noise " + good_critic(9) + " tail")["score"] == 9
    short = json.loads(good_critic())
    short["answers"] = short["answers"][:11]
    with pytest.raises(daily.StageFail) as e:
        daily.parse_critic(json.dumps(short))
    assert e.value.code == "CRITIC-INCOMPLETE"
    with pytest.raises(daily.StageFail):
        daily.parse_critic(good_critic(11).replace('"score": 11', '"score": 11'))
    with pytest.raises(daily.StageFail):
        daily.parse_critic("no json here")


def critic_ctx(tmp_path, scores, monkeypatch, heal_edits_script=False):
    root = mk_root(tmp_path)
    ed = root / "bible" / "series" / "series" / "episodes" / "E02"
    (ed / "script.json").write_text(json.dumps({"lines": []}), encoding="utf-8")
    (root / "work" / "episodes" / "E02").mkdir(parents=True)
    monkeypatch.setattr(daily, "contact_sheet", lambda c, n=6: root / "work")
    monkeypatch.setattr(daily, "validate_episode_files", lambda c: [])
    seq = iter(scores)
    calls = []

    def llm(prompt, *, name, tools, **kw):
        calls.append(name)
        if name.startswith("critic"):
            return {"rc": 0, "text": good_critic(next(seq)), "err": "", "tokens": 10, "cost": None, "missing": [], "seconds": 0.1}
        if heal_edits_script:
            (ed / "script.json").write_text(json.dumps({"lines": [{"id": "L1"}]}), encoding="utf-8")
        return {"rc": 0, "text": "ok", "err": "", "tokens": 10, "cost": None, "missing": [], "seconds": 0.1}
    ctx = ctx_for(root, llm=llm)
    return ctx, calls, ed


def test_critic_passes_at_nine_and_writes_critic_json(tmp_path, monkeypatch):
    ctx, calls, _ = critic_ctx(tmp_path, [9], monkeypatch)
    info = daily.s_critic(ctx)
    assert info["score"] == 9 and calls == ["critic-E02-0"]
    cj = json.loads((ctx.work / "heal" / "critic.json").read_text(encoding="utf-8"))
    assert cj["score"] == 9 and cj["format"] == "calm" and len(cj["answers"]) == 12           # the shape ig.py publish_gates reads


def test_critic_below_nine_heals_the_plan_and_reruns_shots_compose_gates(tmp_path, monkeypatch):
    ctx, calls, _ = critic_ctx(tmp_path, [7, 9], monkeypatch)
    reran = []
    for nm in ("plan", "animatic", "shots", "compose", "gates"):
        monkeypatch.setitem(daily.STAGES, nm, daily.Stage(nm, lambda c, nm=nm: reran.append(nm) or {}, lambda c: [], "machine"))
    info = daily.s_critic(ctx)
    assert info["rounds"] == [7, 9] and calls == ["critic-E02-0", "healer-E02-0", "critic-E02-1"] and reran == ["plan", "animatic", "shots", "compose", "gates"]


def test_critic_gives_up_after_two_heal_rounds_and_never_posts(tmp_path, monkeypatch):
    ctx, calls, _ = critic_ctx(tmp_path, [6, 7, 8], monkeypatch)
    for nm in ("plan", "animatic", "shots", "compose", "gates"):
        monkeypatch.setitem(daily.STAGES, nm, daily.Stage(nm, lambda c: {}, lambda c: [], "machine"))
    with pytest.raises(daily.StageFail) as e:
        daily.s_critic(ctx)
    assert e.value.code == "CRITIC-LOW" and calls.count("healer-E02-0") + calls.count("healer-E02-1") == 2 and len([c for c in calls if c.startswith("critic")]) == 3


def test_the_healer_may_not_touch_the_script(tmp_path, monkeypatch):
    ctx, calls, ed = critic_ctx(tmp_path, [6, 9], monkeypatch, heal_edits_script=True)
    with pytest.raises(daily.StageFail) as e:
        daily.s_critic(ctx)
    assert e.value.code == "HEAL-FORBIDDEN"
    assert json.loads((ed / "script.json").read_text(encoding="utf-8")) == {"lines": []}      # restored: one take per line


# ------------------------------------------------------------------ publish only when everything is green
def test_publish_refuses_a_red_gate_and_a_low_critic_and_skips_without_a_token(tmp_path, monkeypatch):
    root = mk_root(tmp_path)
    ctx = ctx_for(root)
    with pytest.raises(daily.StageFail) as e:
        daily.s_publish(ctx)
    assert e.value.code == "PUBLISH-GATES"
    w = root / "work" / "episodes" / "E02"
    (w / "gate").mkdir(parents=True)
    (w / "heal").mkdir()
    (w / "episode.mp4").write_bytes(b"x")
    (w / "gate" / "report.json").write_text(json.dumps({"verdict": "PASS", "complete": True, "checks": []}), encoding="utf-8")
    (w / "heal" / "critic.json").write_text(json.dumps({"score": 8}), encoding="utf-8")
    with pytest.raises(daily.StageFail):
        daily.s_publish(ctx)
    (w / "heal" / "critic.json").write_text(json.dumps({"score": 9}), encoding="utf-8")
    monkeypatch.setattr(daily, "fb_token_exists", lambda r: False)         # Instagram-only here; the two-platform stage is in test_fb.py
    monkeypatch.setattr(daily, "token_exists", lambda r: False)
    assert "no Instagram token" in daily.s_publish(ctx)["why"]
    monkeypatch.setattr(daily, "token_exists", lambda r: True)
    ran = []
    monkeypatch.setattr(ctx, "uv", lambda script, *a, **k: ran.append(a) or "DRY RUN (add --go to post).\n")
    assert daily.s_publish(ctx)["_status"] == "skipped" and ran[0][0] == "publish" and "--go" not in ran[0]
    ctx.config["go"] = True
    daily.s_publish(ctx)
    assert "--go" in ran[1]


def test_schedule_writes_the_harvest_plan_and_never_registers_it(tmp_path, monkeypatch):
    root = mk_root(tmp_path)
    ctx = ctx_for(root)
    assert daily.s_schedule(ctx)["_status"] == "skipped"
    (root / "work" / "episodes" / "E02").mkdir(parents=True)
    (root / "work" / "episodes" / "E02" / "post.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(ctx, "uv", lambda *a, **k: 'NOT REGISTERED. schtasks /Create /TN "StoryWrap-Votes-E02" ...')
    info = daily.s_schedule(ctx)
    assert info["registered"] is False and "NOT REGISTERED" in Path(info["plan"]).read_text(encoding="utf-8")


def test_task_scheduler_plan_is_documented_not_registered():
    plan = daily.task_plan(Path("/x"))
    assert plan.startswith("NOT REGISTERED") and plan.count("schtasks /Create") == 1 and "register-tasks.ps1" in plan and "-DryRun" in plan and "ig.py refresh" in plan
    assert "LOOP GATE" in plan and "14:00" in plan and "19:00" in plan and "19:30" not in plan


# ------------------------------------------------------------------ the writer's plan and the compose side
def plan_ok():
    return {"series": "series", "episode": "E02", "day": 2, "place": "المكتب", "clock0": "9:04 م", "recap": {"line": "اخترتم:", "word": "الرف"},
            "hook": {"pattern": 1, "line": "H1"},     # DESIGN.md 2.1: the spoken recap is the first spoken line
            "scenes": [{"id": f"s{i}", "line": f"L{i}", "block": "consequence" if i < 3 else ("cliff" if i == 5 else "story"), "template": "push_in", "params": {"character": "partner"}} for i in range(1, 6)],
            "intros": [{"id": "intro-partner", "character": "partner", "after": "s1", "name": "عيسى", "tag": "يحمل المصباح"}],     # C10: a character's first appearance is followed by an intro_freeze
            "choice": {"question": "أين تنام؟", "choice1": "على الرف", "choice2": "في اليد",
                       "variants": {"1": ["الرف", "أتركها على الرف", "خلوها على الرف", "تنام على الرف", "على الرف بلا رقم", "تبقى على الرف", "أحطها على الرف", "ضعوها على الرف"],
                                    "2": ["اليد", "تبقى في يدها", "تحملها هدى", "خلوها معها", "في يد هدى", "أتركها في يدها", "تبقى معها", "تحملها"]}},
            "post_caption": "تابع للجزء التالي"}


def script_ok():
    lines = [{"id": f"L{i}", "speaker": "narrator", "text": "كلام بلا تشكيل", "tts_text": "كَلَامٌ"} for i in range(1, 6)]
    lines[0]["text"] = "ومنى ما زالت تحمل الحقيبة"       # DESIGN.md 2.2: the first scene line names the heroine (story so far)
    return {"lines": lines + [{"id": "H1", "speaker": "narrator", "text": "اخترتم أن تنام الحقيبة على الرف", "tts_text": "اِخْتَرْتُمْ"}]}


def test_plan_validation_accepts_a_good_plan_and_names_each_fault():
    assert cc.validate_plan(plan_ok(), script_ok()) == []
    p = plan_ok()
    p["choice"]["choice2"] = p["choice"]["choice1"]
    assert any(f.startswith("PLAN-CHOICE") for f in cc.validate_plan(p, script_ok()))
    p = plan_ok()
    p["choice"].pop("choice2")
    assert any(f.startswith("PLAN-CHOICE") for f in cc.validate_plan(p, script_ok()))
    p = plan_ok()
    p["recap"]["word"] = "الرَّف"
    assert any(f.startswith("PLAN-TASHKEEL") for f in cc.validate_plan(p, script_ok()))
    s = script_ok()
    for i in range(4):
        s["lines"][i]["speaker"] = "hero"  # format v2 (2026-10-28): the characters may speak most lines; the old narrator-share rule PLAN-NARRATOR is gone (E02 is not subject to the v2 gates either)
    assert not any(f.startswith(("PLAN-NARRATOR", "DIALOGUE-LINES", "EVENTS", "NARRATOR-SHARE")) for f in cc.validate_plan(plan_ok(), s))
    p = plan_ok()
    p["scenes"] = [{**p["scenes"][3], "id": f"x{i}"} for i in range(3)]
    assert any(f.startswith("PLAN-SCENES") for f in cc.validate_plan(p, script_ok()))          # a floor stays
    p["scenes"] = [{**p["scenes"][0], "id": f"x{i}", "line": "L1"} for i in range(60)]
    p["scenes"][-1]["block"] = "cliff"
    assert not any(f.startswith("PLAN-SCENES") for f in cc.validate_plan(p, script_ok()))      # no ceiling: the story sets the length (the owner 2026-10-25)


def test_calm_length_has_a_floor_and_a_soft_warning_but_no_ceiling():
    ok, detail, warn = cc.length_check(60.0)
    assert ok and warn is None
    assert not cc.length_check(24.9)[0]                              # the sanity floor stays
    for d in (99.2, 140.0, 300.0):                                   # E01C ran 99.2 s: it must not fail on length any more
        ok, detail, warn = cc.length_check(d)
        assert ok and warn and "confirm" in warn and "WARNING" in detail
    s = script_ok()
    s["lines"][1]["text"] = "كَلَامٌ"
    assert any(f.startswith("PLAN-TASHKEEL") for f in cc.validate_plan(plan_ok(), s))
    p = plan_ok()
    p["scenes"][0]["line"] = "L99"
    assert any(f.startswith("PLAN-LINE") for f in cc.validate_plan(p, script_ok()))
    p = plan_ok()
    p["scenes"][3]["block"] = "cliff"
    p["scenes"][4]["block"] = "story"          # a cliff scene followed by a story scene: the cliff must be last
    assert any(f.startswith("PLAN-BLOCK") for f in cc.validate_plan(p, script_ok()))
    p = plan_ok()
    del p["recap"]
    assert any(f.startswith("PLAN-FIELD") for f in cc.validate_plan(p, script_ok()))


def test_scene_length_comes_from_the_take_and_is_snapped_and_bounded():
    assert cc.scene_seconds(3.0, None) == cc.snap(3.0 + cc.VOICE_LEAD_S + cc.PAD_S)
    assert cc.scene_seconds(0.5, None) == cc.snap(cc.MIN_SCENE_S) == cc.MIN_SCENE_S
    assert cc.scene_seconds(None, 4.01) == cc.snap(4.01)
    with pytest.raises(cc.Fail):
        cc.scene_seconds(9.6, None)       # format v2: a dialogue scene may run to 10 s, so 9.0 + 0.55 now fits
    assert cc.scene_seconds(9.0, None) == cc.snap(9.0 + cc.VOICE_LEAD_S + cc.PAD_S)


def test_word_groups_are_one_to_three_words_and_timing_covers_the_take(tmp_path):
    import math
    import wave
    words = "تدخل the series في الليل".split()
    groups = cc.group_words(words)
    assert all(1 <= len(g) <= 3 for g in groups) and [i for g in groups for i in g] == list(range(len(words)))
    sr, secs = 16000, 2.0
    frames = bytearray()
    for i in range(int(sr * secs)):
        t = i / sr
        env = 0.0 if t < 0.2 or t > 1.8 else (0.05 if (int(t * 4) % 2) else 0.5)    # speech between 0.2 and 1.8 s, with pauses
        v = int(32767 * env * math.sin(2 * math.pi * 220 * t))
        frames += v.to_bytes(2, "little", signed=True)
    p = tmp_path / "take.wav"
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(sr)
        w.writeframes(bytes(frames))
    tm = cc.word_timing(p, words)
    assert len(tm) == len(words) and tm[0][0] >= 0.15 and tm[-1][1] <= 1.95
    assert all(b[0] >= a[1] - 1e-6 and b[1] > b[0] for a, b in zip(tm, tm[1:]))             # in order, no overlap, never empty


def test_clock_helpers_round_trip_arabic_digits():
    assert cc._clock_minutes("٩:٠٤ م") == 21 * 60 + 4
    assert cc._clock_text(21 * 60 + 8) == "٩:٠٨ م"


def test_timeline_places_the_wrapper_around_the_scenes_with_soft_joins(tmp_path):
    root = mk_root(tmp_path)
    ed = root / "bible" / "series" / "series" / "episodes" / "E02"
    (ed / "calm-plan.json").write_text(json.dumps(plan_ok(), ensure_ascii=False), encoding="utf-8")
    (ed / "script.json").write_text(json.dumps(script_ok(), ensure_ascii=False), encoding="utf-8")
    import wave
    (root / "work" / "voice" / "E02").mkdir(parents=True)
    for i in range(0, 6):
        with wave.open(str(root / "work" / "voice" / "E02" / (f"L{i}.trimmed.wav" if i else "H1.trimmed.wav")), "wb") as w:
            w.setnchannels(1), w.setsampwidth(2), w.setframerate(16000)
            w.writeframes(b"\x00\x00" * int(16000 * (3.0 if i else 2.0)))
    ep = cc.Ep("E02", root)
    info = cc.stage_plan(ep)
    tl = json.loads(ep.timeline_p.read_text(encoding="utf-8"))
    ids = [i["id"] for i in tl["items"]]
    assert ids[0] == "recap" and ids[-2:] == ["choice", "follow"] and ids.index("day") == 4 and ids[1:3] == ["s1", "intro-partner"]          # two consequence scenes and the character's intro freeze (C10), then the day card
    assert next(i for i in tl["items"] if i["id"] == "intro-partner")["kind"] == "intro" and next(i for i in tl["items"] if i["id"] == "intro-partner")["join_in"]["cut"] == "freeze"
    assert tl["profile"] == "calm" and info["total_s"] == tl["total_s"]
    for a, b in zip(tl["items"], tl["items"][1:]):
        assert abs((a["t1"] - b["t0"]) - cc.JOIN_S) < 1e-6                                           # each item starts as the last one dissolves out
    sc = [i for i in tl["items"] if i["kind"] == "scene"]
    assert all(i["voice_t0"] >= i["t0"] + cc.VOICE_LEAD_S - 1e-6 for i in sc)


def test_the_first_episode_has_no_recap_and_recaps_start_at_e02(tmp_path):
    assert cc.RECAP_FROM_EPISODE == 2 and cc.episode_number("E01C") == 1 and cc.episode_number("E12") == 12 and cc.episode_number("R01") is None
    p = plan_ok()
    p["episode"] = "E01C"
    assert any(f.startswith("PLAN-RECAP") for f in cc.validate_plan(p, script_ok()))        # E01 may not carry a recap
    del p["recap"]
    assert cc.validate_plan(p, script_ok()) == []                                           # and needs none
    p["episode"] = "E02"
    assert any(f.startswith("PLAN-FIELD") for f in cc.validate_plan(p, script_ok()))        # E02 does
    root = mk_root(tmp_path)
    ed = root / "bible" / "series" / "series" / "episodes" / "E01"
    ed.mkdir(parents=True)
    q = plan_ok()
    q["episode"] = "E01"
    del q["recap"]
    (ed / "calm-plan.json").write_text(json.dumps(q, ensure_ascii=False), encoding="utf-8")
    (ed / "script.json").write_text(json.dumps(script_ok(), ensure_ascii=False), encoding="utf-8")
    import wave
    (root / "work" / "voice" / "E01").mkdir(parents=True)
    for i in range(1, 6):
        with wave.open(str(root / "work" / "voice" / "E01" / f"L{i}.trimmed.wav"), "wb") as w:
            w.setnchannels(1), w.setsampwidth(2), w.setframerate(16000)
            w.writeframes(b"\x00\x00" * int(16000 * 3.0))
    cc.stage_plan(cc.Ep("E01", root))
    tl = json.loads((root / "work" / "episodes" / "E01" / "timeline.json").read_text(encoding="utf-8"))
    assert [i["id"] for i in tl["items"]][0] == "s1" and tl["items"][0]["t0"] == 0 and "recap" not in [i["id"] for i in tl["items"]]
    sl = cc.episode_shotlist(None, tl, q)
    assert "recap" not in sl["wrapper"] and sl["episode_no"] == 1 and sl["recap_from"] == 2


def test_episode_shotlist_has_the_wrapper_shape_the_calm_checks_read():
    tl = {"items": [{"id": "recap", "kind": "card", "t0": 0, "t1": 2.5}, {"id": "day", "kind": "card", "t0": 2.2, "t1": 4.2}, {"id": "s1", "kind": "scene", "t0": 4.0, "t1": 8.0, "subjects": ["partner"]},
                    {"id": "choice", "kind": "card", "t0": 7.8, "t1": 12.8}, {"id": "follow", "kind": "card", "t0": 12.6, "t1": 15.6}]}
    sl = cc.episode_shotlist(None, tl)
    assert set(sl["wrapper"]) == {"recap", "day_card", "choice_card", "follow_card"} and sl["shots"] == [{"id": "s1", "subjects": ["partner"]}]
    import qg_checks as qc
    if hasattr(qc, "check_calm_declared"):
        assert "CALM-WRAPPER" not in " ".join(qc.check_calm_declared({"lines": [{"start": 4.2, "dur": 10}]}, {"captions": [{"line": "L1", "text": "كلمة", "start": 4.2, "end": 5, "font_px_1080": 104}]},
                                                                      {"choices": ["a", "b"]}, sl, 15.6))


def test_script_stage_keeps_existing_episode_files(tmp_path):
    """A rerun without --force script must not call the writer when script.json and calm-plan.json exist: the writer overwrote the E01C rehearsal script (2026-10-25)."""
    import daily
    ed = tmp_path / "ep"
    ed.mkdir()
    (ed / "script.json").write_text("{}", encoding="utf-8")
    (ed / "calm-plan.json").write_text("{}", encoding="utf-8")

    class C:
        ep_dir = ed
        config = {}

        def llm(self, *a, **k):
            raise AssertionError("the writer was called")
    assert "kept" in daily.s_script(C())


def test_a_scene_hold_is_bounded_and_assemble_pads_the_last_frame():
    """E01C never froze (CALM-HOLDS 0.03 < 0.05): the calm recipe rests 13 to 17 % of the runtime. `hold` in a plan scene freezes the shot's last N s inside the same length."""
    p = plan_ok()
    p["scenes"][0]["hold"] = 1.3
    assert not any(f.startswith("PLAN-HOLD") for f in cc.validate_plan(p, script_ok()))
    p["scenes"][0]["hold"] = 4
    assert any(f.startswith("PLAN-HOLD") for f in cc.validate_plan(p, script_ok()))
    src = Path(cc.__file__).read_text(encoding="utf-8")
    assert "tpad=stop_mode=clone:stop_duration={hold" in src and '"hold": float(s.get("hold")' in src
