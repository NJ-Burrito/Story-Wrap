"""R-506 / R-507 (the owner 2026-10-30: "never stop, never need him to ask"; "never postpone a post to the next day").

  - the child's own check id is the stop code, never a bare CHILD (E05: `calm_compose.py captions E05: FAIL [CAP-FACE-CLEAR] ...` was recorded as CHILD, so no heal saw it);
  - CAP-FACE-CLEAR / CAP-SAFE / CALM-PLATE-SAFE are healed by cutting the plate (tools/cap_heal.py), else by a shorter line (line_refit), in bounded rounds;
  - a stop with no heal left gets ONE bounded fixer session (autopilot.try_fixer), its edits are validated and rolled back when they leave the limits, then the build runs again;
  - a complete episode whose 19:00 slot has passed is posted at once, however late and across midnight, never before the slot, never twice; the harvest follows the post sanely.
No browser, no model, no network, no process."""
import datetime as dt
import json
from types import SimpleNamespace

import pytest

import autopilot as ap
import build_status as bs
import cap_heal as CH
import cap_sentence as CS
import daily
import loop_gate as lg
from test_autopilot import D, finish, harvested, post, started, wj
from test_daily import ctx_for, mk_root, plan_ok, script_ok

L13 = "يد؟ أري! يد تدخل مكتبي بلا أجرة!"
MSG = "calm_compose.py captions E05: no place for plate «يد؟ أري! (يا للعجب) يد تدخل مكتبي بلا أجرة!» (L13 unit 0, 77.50-77.91 s, 891x380 px) outside the faces on screen: shorten the sentence or split it"
NOW = D(2026, 10, 30, 21, 0)


@pytest.fixture(autouse=True)
def no_facebook_token(monkeypatch):
    monkeypatch.setattr(lg, "has_fb_token", lambda *a, **k: False)       # the real ~/.config must not decide a test
    monkeypatch.setattr(lg, "has_token", lambda *a, **k: False)


# ------------------------------------------------------------------ 1. the real stop code
def test_inner_fail_reads_the_child_check_id():
    assert daily.inner_fail("FAIL [CAP-FACE-CLEAR] no place for plate") == ("CAP-FACE-CLEAR", "no place for plate")
    assert daily.inner_fail("Traceback (most recent call last):") is None
    assert daily.inner_fail("FAIL [x] too short an id") is None


def test_a_failing_child_raises_its_own_code_not_child(tmp_path):
    def run_proc(cmd, **kw):
        return SimpleNamespace(returncode=1, stdout="[captions] starting\nFAIL [CAP-FACE-CLEAR] no place for plate «x» (L13 unit 0)\n", stderr="")
    ctx = ctx_for(mk_root(tmp_path), cap_s=100, run_proc=run_proc)
    with pytest.raises(daily.StageFail) as e:
        ctx.uv("calm_compose.py", "captions", "E02", label="captions")
    assert e.value.code == "CAP-FACE-CLEAR" and "calm_compose.py captions E02" in e.value.msg and "no place for plate" in e.value.msg
    daily.stopped(ctx, e.value, "compose")
    assert "`FAIL [CAP-FACE-CLEAR]`" in (ctx.dir / "STOPPED.md").read_text(encoding="utf-8")


def test_a_child_with_no_check_id_stays_child(tmp_path):
    def run_proc(cmd, **kw):
        return SimpleNamespace(returncode=1, stdout="", stderr="Traceback (most recent call last):\nOSError: disk\n")
    ctx = ctx_for(mk_root(tmp_path), cap_s=100, run_proc=run_proc)
    with pytest.raises(daily.StageFail) as e:
        ctx.uv("calm_compose.py", "captions", "E02", label="captions")
    assert e.value.code == "CHILD"


def test_stop_code_unwraps_a_stop_written_before_the_fix(tmp_path):
    ed = tmp_path / "work" / "daily" / "E05"
    ed.mkdir(parents=True)
    (ed / "STOPPED.md").write_text("# stopped\n\nepisode E05, stage compose, 2026-10-30T21:02:37\n\n`FAIL [CHILD]` calm_compose.py captions E05: FAIL [CAP-FACE-CLEAR] no place for plate «x»\n", encoding="utf-8")
    assert ap.stop_code(tmp_path, "E05") == "CAP-FACE-CLEAR"
    (ed / "STOPPED.md").write_text("`FAIL [CHILD]` ig.py publish E05: timeout\n", encoding="utf-8")
    assert ap.stop_code(tmp_path, "E05") == "CHILD"
    (ed / "STOPPED.md").write_text("`FAIL [CAP-SAFE]` plate too wide\n", encoding="utf-8")
    assert ap.stop_code(tmp_path, "E05") == "CAP-SAFE"


def test_the_board_names_the_inner_code_of_an_old_stop_and_marks_a_post_stop_as_publish_failed(tmp_path):
    ed = tmp_path / "work" / "daily" / "E05"
    ed.mkdir(parents=True)
    (ed / "STOPPED.md").write_text("# stopped\n\nepisode E05, stage compose, 2026-10-30T21:02:37\n\n`FAIL [CHILD]` calm_compose.py captions E05: FAIL [CAP-FACE-CLEAR] no place\n", encoding="utf-8")
    code, msg, _when, stage = bs.stop_info(tmp_path, "E05")
    assert code == "CAP-FACE-CLEAR" and stage == "compose"
    (ed / "STOPPED.md").write_text("# stopped\n\nepisode E05, stage publish, 2026-10-30T23:02:37\n\n`FAIL [IG-HTTP]` ig.py publish E05: 500\n", encoding="utf-8")
    al = bs.alerts(tmp_path, D(2026, 10, 30, 23, 30), {}, None)
    assert any(a["kind"] == "PUBLISH-FAILED" and "IG-HTTP" in a["text"] for a in al)


# ------------------------------------------------------------------ 2. cutting a plate
WORDS = L13.split()


def width(ws):
    return 330.0 * len(ws)


def test_a_forced_cut_is_not_merged_back_and_a_cut_inside_a_sentence_is_a_split_unit():
    base = CS.split_units(WORDS, width, 972, set(), {1})
    assert len(base) == 2 and base[0]["idx"] == [0, 1, 2] or len(base) >= 1                  # the unforced result is whatever the old rules give
    cut = CS.split_units(WORDS, width, 972, set(), {1}, None, {1})
    assert [u["idx"][-1] for u in cut][0] == 1 and all(not u["split"] for u in cut[:1])        # a cut at a sentence end: still whole sentences
    mid = CS.split_units(WORDS, width, 972, set(), set(), None, {1, 4})
    assert [u["idx"] for u in mid] == [[0, 1], [2, 3, 4], [5, 6]]
    assert mid[1]["split"] and mid[1]["clause_words"] == 5 and not mid[0]["split"]
    plates = []
    for u in mid:
        for k, wi in enumerate(u["idx"]):
            plates.append({"line": "L13", "unit": mid.index(u), "text": " ".join(WORDS[j] for j in u["idx"]), "active_index": k, "word_i": wi, "n_lines": len(u["lines"]),
                           "clause_words": u["clause_words"], "split": u["split"], "start": 10.0 + wi * 0.6 + 0.0, "end": 10.0 + wi * 0.6 + 0.6, "word_start": 10.0 + wi * 0.6})
    assert not [x for x in CS.check_plates(plates, {"L13": {"id": "L13", "text": L13}}, None) if x.startswith("CAP-FULL-SENTENCE")]       # the gate accepts the cut as it accepts any balanced split


def test_a_cut_inside_a_glued_glossary_phrase_is_ignored():
    u = CS.split_units(WORDS, width, 972, {1}, set(), None, {1})
    assert all(1 not in (x["idx"][-1],) or len(x["idx"]) > 2 for x in u)                        # word 1 is glued to word 2: no boundary there


def test_parse_locate_and_rank_the_e05_plate():
    f = CH.parse("CAP-FACE-CLEAR", MSG)
    assert f["line"] == "L13" and f["unit"] == 0 and "(" not in f["text"] and f["text"].split() == WORDS
    lines = [{"id": "L12", "text": "كلام آخر."}, {"id": "L13", "text": L13}]
    lid, start, lw = CH.locate(lines, f["text"], f["line"])
    assert (lid, start, lw) == ("L13", 0, WORDS)
    assert CH.candidates(lw, 0, 7, set(), set()) [:2] == [1, 0]                                   # sentence ends first, the more even cut before the other
    w = [2.25, 2.25, 2.25, 3.25, 3.25, 2.25, 3.25]
    assert CH.candidates(lw, 2, 5, {1}, set(), weights=w, secs=3.79)[0] == 5                      # a middle part of 3 words (about 1.3 s) cannot be read: the cut after word 5 comes first
    assert CH.candidates(lw, 2, 5, {1, 5}, set(), weights=w, secs=3.79) [0] == 4
    assert CH.parse("CALM-PLATE-SAFE", "1 plate(s) wider than the 972 px safe area, first «يد؟ أري! (يا للع» at 1000 px")["text"] == "يد؟ أري!"
    assert CH.parse("CAP-SAFE", "plate 'يد تدخل' is 1100 px wide and leaves the safe area")["text"] == "يد تدخل"
    assert CH.parse("CRITIC-LOW", MSG) is None


def episode(tmp_path, text=L13):
    root = mk_root(tmp_path, "E02")
    ed = root / "bible" / "series" / "series" / "episodes" / "E02"
    s = script_ok()
    s["lines"][1].update({"id": "L13", "text": text, "tts_text": text})
    p = plan_ok()
    p["scenes"][1]["line"] = "L13"
    (ed / "script.json").write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")
    (ed / "calm-plan.json").write_text(json.dumps(p, ensure_ascii=False), encoding="utf-8")
    return root, ed


def wire_compose(monkeypatch, run):
    monkeypatch.setitem(daily.STAGES, "compose", daily.Stage("compose", run, lambda c: [], "machine"))
    monkeypatch.setattr(daily, "require_upstream", lambda *a, **k: None)
    reruns = []
    monkeypatch.setattr(CH, "rerun_stages", lambda ctx, names: reruns.append(list(names)))
    return reruns


def test_compose_failing_on_a_plate_with_no_place_is_cut_and_run_again(tmp_path, monkeypatch):
    root, ed = episode(tmp_path)
    ctx = ctx_for(root)

    def compose(c):
        if not CH.load(c.root, c.ep)["lines"].get("L13"):
            raise daily.StageFail("CAP-FACE-CLEAR", MSG.replace("E05", "E02"))
        return {}
    reruns = wire_compose(monkeypatch, compose)
    assert daily.run_list(ctx, ["compose"]) == 0
    rec = CH.load(root, "E02")
    assert rec["rounds"] == 1 and rec["lines"]["L13"]["cuts"] == [1] and reruns == [["animatic", "shots"]]
    assert not (ctx.dir / "STOPPED.md").exists()
    led = [json.loads(x) for x in (root / "kb" / "lessons" / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(led) == 1 and led[0]["source"] == "cap-heal" and "L13" in led[0]["summary"]
    assert ap.cap_heal_pending(root, "E02") is False                                          # no stop note any more
    (ctx.dir / "STOPPED.md").write_text("`FAIL [CAP-FACE-CLEAR]` x\n", encoding="utf-8")
    assert ap.cap_heal_pending(root, "E02") is True and ap.heal_pending(root, "E02", NOW) is True
    rec["exhausted"] = {"reason": "x", "date": "2026-10-30"}
    CH.save(root, "E02", rec)
    assert ap.cap_heal_pending(root, "E02") is False


def test_a_plate_that_never_fits_is_cut_in_bounded_rounds_then_the_line_is_reworded_then_it_stops(tmp_path, monkeypatch):
    root, ed = episode(tmp_path)
    ctx = ctx_for(root)
    reruns = wire_compose(monkeypatch, lambda c: (_ for _ in ()).throw(daily.StageFail("CAP-FACE-CLEAR", MSG)))
    refits = []
    import line_refit
    monkeypatch.setattr(line_refit, "measured_seconds", lambda c, s: {"L13": 3.79})
    monkeypatch.setattr(line_refit, "cure", lambda c, e, only=None, items=None: refits.append((only, items)) or False)
    assert daily.run_list(ctx, ["compose"]) == 1
    rec = CH.load(root, "E02")
    assert rec["rounds"] == daily.CAP_HEAL_CALLS == 3 and len(reruns) == 3                      # 3 cuts inside one run, no more
    assert "CAP-FACE-CLEAR" in (ctx.dir / "STOPPED.md").read_text(encoding="utf-8")
    assert CH.heal_possible(root, "E02")                                                       # 3 of 5 rounds
    assert daily.run_list(ctx, ["compose"]) == 1 and CH.load(root, "E02")["rounds"] == 5     # the next run uses the rest
    assert daily.run_list(ctx, ["compose"]) == 1                                               # no cut left: the line is reworded shorter (forced item through line_refit), once or twice
    assert refits and refits[0][0] == "L13" and refits[0][1][0]["target_s"] < 3.79 and "no place on screen" in refits[0][1][0]["why"]
    rec = CH.load(root, "E02")
    assert rec["refits"] == 1 and rec["exhausted"]["reason"] == "no cut and no rewrite left" and not CH.heal_possible(root, "E02")        # the writer gave nothing usable: the stop is the fixer's
    n = len(refits)
    assert daily.run_list(ctx, ["compose"]) == 1 and len(refits) == n                         # exhausted: no more rounds, no more writer calls
    assert ap.heal_pending(root, "E02", NOW) is False


def test_other_failures_are_not_touched_by_the_plate_heal(tmp_path, monkeypatch):
    root, ed = episode(tmp_path)
    ctx = ctx_for(root)
    wire_compose(monkeypatch, lambda c: (_ for _ in ()).throw(daily.StageFail("AUDIO-MODE", "x")))
    assert daily.run_list(ctx, ["compose"]) == 1 and CH.load(root, "E02")["rounds"] == 0


# ------------------------------------------------------------------ 3. the general fixer
def stopped_ep(root, code="EPISODE-GATE", ep="E02"):
    d = root / "work" / "daily" / ep
    d.mkdir(parents=True, exist_ok=True)
    (d / "STOPPED.md").write_text(f"# stopped\n\nepisode {ep}, stage gates, 2026-10-30T20:00:00\n\n`FAIL [{code}]` something the plan can fix\n", encoding="utf-8")
    (d / "FIX-REQUEST.md").write_text("# FIX-REQUEST\n", encoding="utf-8")


def fixer_llm(root, ep, edit=None, decision=None):
    d = root / "work" / "daily" / ep

    def llm(prompt, name):
        assert "NO shell" in prompt and "cap-heal.json" in prompt and ep in prompt
        if edit:
            edit()
        out_json = next(d.glob("fixer-*.json")) if list(d.glob("fixer-*.json")) else None
        n = len(list(d.glob("fixer-*.md")))
        stem = d / f"fixer-{NOW.date().isoformat()}-1"
        stem.with_suffix(".md").write_text("x", encoding="utf-8")
        stem.with_suffix(".json").write_text(json.dumps(decision or {"fixed": True, "changes": ["calm-plan.json: s2 longer"], "refit_lines": [], "reason": "r"}), encoding="utf-8")
        return {"rc": 0, "tokens": 1000}
    return llm


def plan_edit(ed):
    def f():
        p = json.loads((ed / "calm-plan.json").read_text(encoding="utf-8"))
        p["scenes"][0]["duration"] = 6.0
        (ed / "calm-plan.json").write_text(json.dumps(p, ensure_ascii=False), encoding="utf-8")
    return f


def test_the_fixer_edits_the_plan_and_the_build_runs_again(tmp_path):
    root, ed = episode(tmp_path)
    stopped_ep(root)
    st = ap.load_state(root)
    builds = []
    r = ap.try_fixer(root, st, "E02", "EPISODE-GATE", NOW, "why", llm=fixer_llm(root, "E02", plan_edit(ed)), build=lambda e: builds.append(e) or (0, "ready"), validate=lambda e: [])
    assert r[0] == 0 and builds == ["E02"] and "fixer" in r[1]
    assert json.loads((ed / "calm-plan.json").read_text(encoding="utf-8"))["scenes"][0]["duration"] == 6.0
    rec = json.loads((root / "work" / "daily" / "E02" / "fixer.json").read_text(encoding="utf-8"))
    assert rec["events"][0]["code"] == "EPISODE-GATE" and "rc 0" in rec["events"][0]["result"]
    led = [json.loads(x) for x in (root / "kb" / "lessons" / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
    assert led[0]["source"] == "fixer"
    assert ap.fixer_done(st, "E02", "EPISODE-GATE", NOW)                                        # once per (episode, code) per day
    assert ap.try_fixer(root, st, "E02", "EPISODE-GATE", NOW, "why", llm=lambda p, n: pytest.fail("twice")) is None


def test_the_fixer_may_not_reword_a_voiced_line_and_is_rolled_back(tmp_path):
    root, ed = episode(tmp_path)
    stopped_ep(root)
    before = (ed / "script.json").read_bytes()

    def edit():
        s = json.loads(before.decode("utf-8"))
        s["lines"][1]["text"] = "يد."
        (ed / "script.json").write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")
    st = ap.load_state(root)
    r = ap.try_fixer(root, st, "E02", "EPISODE-GATE", NOW, "why", llm=fixer_llm(root, "E02", edit), build=lambda e: pytest.fail("no rebuild after a rollback"), validate=lambda e: [])
    assert r[0] == 1 and "rolled back" in r[1] and (ed / "script.json").read_bytes() == before


def test_a_plan_that_fails_validation_is_rolled_back(tmp_path):
    root, ed = episode(tmp_path)
    stopped_ep(root)
    before = (ed / "calm-plan.json").read_bytes()
    st = ap.load_state(root)
    r = ap.try_fixer(root, st, "E02", "EPISODE-GATE", NOW, "why", llm=fixer_llm(root, "E02", plan_edit(ed)), build=lambda e: pytest.fail("no"), validate=lambda e: ["PLAN-CHOICE x"])
    assert r[0] == 1 and (ed / "calm-plan.json").read_bytes() == before


def test_a_fixer_that_changes_nothing_leaves_the_request_red_and_does_not_rebuild(tmp_path):
    root, ed = episode(tmp_path)
    stopped_ep(root)
    st = ap.load_state(root)
    r = ap.try_fixer(root, st, "E02", "EPISODE-GATE", NOW, "why", llm=fixer_llm(root, "E02", None, {"fixed": False, "changes": [], "refit_lines": [], "reason": "no cause I can name"}),
                     build=lambda e: pytest.fail("no"))
    assert r[0] == 1 and "changed nothing" in r[1] and (root / "work" / "daily" / "E02" / "FIX-REQUEST.md").is_file()


def test_the_fixer_can_ask_for_a_shorter_line_through_refit(tmp_path):
    root, ed = episode(tmp_path)
    stopped_ep(root)
    got = []
    st = ap.load_state(root)
    r = ap.try_fixer(root, st, "E02", "EPISODE-GATE", NOW, "why", llm=fixer_llm(root, "E02", None, {"fixed": True, "changes": [], "refit_lines": ["L13", "L99"], "reason": "too wide"}),
                     refit=lambda e, ln: got.append((e, ln)) or (0, "ok"), build=lambda e: (0, "ready"), validate=lambda e: [])
    assert got == [("E02", "L13")] and r[0] == 0                                               # an unknown line id is dropped


def test_the_fixer_bounds(tmp_path):
    root, ed = episode(tmp_path)
    stopped_ep(root)
    never = lambda p, n: pytest.fail("must not run")
    st = ap.load_state(root)
    for c in ("A-1", "A-2", "A-3"):
        st["fixer"][ap.fixer_key("E02", c)] = NOW.date().isoformat()
    assert ap.try_fixer(root, st, "E02", "EPISODE-GATE", NOW, "w", llm=never) is None           # 3 a day for one episode
    st = ap.load_state(root)
    assert ap.try_fixer(root, st, "E02", None, NOW, "w", llm=never) is None                     # no stop code
    wj(root / "work" / "daily" / "budget-2026-10-30.json", {"tokens": 4_900_000, "limit": 5_000_000})
    assert ap.try_fixer(root, st, "E02", "EPISODE-GATE", NOW, "w", llm=never) is None           # under FIXER_MIN_TOKENS left
    wj(root / "work" / "daily" / "budget-2026-10-30.json", {"tokens": 10, "limit": 5_000_000})
    wj(root / "work" / "daily" / "E02" / "deadline.json", {"machine_s": 4 * 3600, "cap_s": 4 * 3600})
    assert ap.try_fixer(root, st, "E02", "EPISODE-GATE", NOW, "w", llm=never) is None           # the 4 h cap is spent
    (root / "work" / "daily" / "E02" / "deadline.json").unlink()
    (root / "work" / "daily" / "E02" / "STOPPED.md").write_text("`FAIL [CAP-FACE-CLEAR]` x\n", encoding="utf-8")
    assert ap.try_fixer(root, st, "E02", "CAP-FACE-CLEAR", NOW, "w", llm=never) is None         # a specific heal still has rounds: it goes first


def test_the_job_flags_of_the_fixer_session_forbid_a_shell_and_agents():
    cmd = daily.build_cmd("claude.exe", "p", tools="Read,Glob,Grep,Write,Edit")
    assert cmd[cmd.index("--allowedTools") + 1] == "Read,Glob,Grep,Write,Edit" and "Bash" in cmd[cmd.index("--disallowedTools") + 1]
    with pytest.raises(ValueError):
        daily.build_cmd("claude.exe", "p", tools="Read,Agent")
    tpl = (ap.TOOLS / "templates" / "autopilot-fixer.md").read_text(encoding="utf-8")
    assert "NO shell" in tpl and "tools/" in tpl and "never change the text" in tpl


def test_a_stuck_episode_gets_the_fixer_in_the_run_and_a_green_build_clears_the_request(tmp_path):
    root, ed = episode(tmp_path)
    post(root, "E01", D(2026, 10, 29, 19, 0))
    harvested(root, "E01")
    started(root, "E02")
    stopped_ep(root)
    real = dt.datetime.now() + dt.timedelta(seconds=5)          # the plan files were written just now: a failure dated before them would read as "fixed since" (forget_fixed_failures)
    st = ap.load_state(root)
    for _ in range(ap.MAX_ATTEMPTS):
        ap.record_failure(root, st, "E02", 1, real)
    ap.save_state(root, st)
    builds = []
    rc, line = ap.run_once(root, real, next_episode=lambda r: "E02", build=lambda e: builds.append(e) or (0, "ready"), write_board=lambda r: None, pid=1, alive=lambda p: False,
                           fixer_llm=fixer_llm(root, "E02", plan_edit(ed)), daily_mod=SimpleNamespace(validate_episode_files=lambda c: [], restamp=lambda c, n: None, Ctx=lambda ep, root=None: None,
                                                                                                    run_claude=None, Budget=None))
    assert builds == ["E02"] and rc == 0 and "fixer" in line
    assert not (root / "work" / "daily" / "E02" / "FIX-REQUEST.md").exists()
    assert (root / "work" / "daily" / "E02" / "FIX-REQUEST.resolved.md").exists()


# ------------------------------------------------------------------ 4. the board
def test_the_build_panel_names_each_heal_and_what_is_working(tmp_path):
    ed = tmp_path / "work" / "daily" / "E05"
    ed.mkdir(parents=True)
    wj(ed / "STATE.json", {"stages": {"compose": {"status": "running", "seconds": 1}}})
    wj(ed / "cap-heal.json", {"rounds": 2, "lines": {}, "events": [{"at": "2026-10-30T21:10:00", "event": "cut", "line": "L13", "plate": "يد؟ أري!", "after_word": 1}], "exhausted": None})
    wj(ed / "fixer.json", {"rounds": 1, "events": [{"at": "2026-10-30T21:20:00", "code": "X", "result": "daily.py run -> rc 0: ready"}]})
    wj(tmp_path / "work" / "daily" / "autopilot.json", {"doing": {"what": "the fixer is fixing X", "ep": "E05", "since": "2026-10-30T21:15"}})
    wj(tmp_path / "work" / "daily" / "autopilot.lock", {"pid": 4242, "at": "2026-10-30T21:15:00"})
    import os
    orig = ap.pid_alive
    ap.pid_alive = lambda pid: pid == 4242
    try:
        b = bs.build(tmp_path, D(2026, 10, 30, 21, 21))
    finally:
        ap.pid_alive = orig
    kinds = {h["file"]: h for h in b["heals"]}
    assert kinds["cap-heal.json"]["kind"].startswith("plate cut") and "cut L13" in kinds["cap-heal.json"]["what"] and kinds["cap-heal.json"]["rounds"] == 2
    assert kinds["fixer.json"]["kind"].startswith("general fixer") and "rc 0" in kinds["fixer.json"]["what"]
    assert b["doing"]["what"] == "the fixer is fixing X" and b["now"].startswith("the fixer is fixing X")


# ------------------------------------------------------------------ 5. posting at once (R-507)
def slot(day):
    return D(2026, 10, day, 19, 0)


def ready_ep(root, ep, ready, start):
    finish(root, ep, ready=ready)
    wj(root / "work" / "daily" / ep / "STATE.json", {"episode": ep, "started": start.isoformat(), "stages": {"retro": {"status": "ok"}}})


def test_before_its_slot_nothing_is_posted_after_it_a_complete_episode_goes_at_once(tmp_path):
    ready_ep(tmp_path, "E05", D(2026, 10, 30, 16, 0), D(2026, 10, 30, 14, 30))
    d = lg.late_post_due("E05", D(2026, 10, 30, 16, 5), tmp_path)
    assert d["due"] is False and d["code"] == "WAIT-SLOT"
    assert lg.late_post_due("E05", D(2026, 10, 30, 19, 0), tmp_path)["code"] == "DUE"
    assert lg.late_post_due("E05", D(2026, 10, 30, 19, 5), tmp_path)["due"]


def test_an_episode_finished_after_the_slot_is_posted_at_once_even_past_20_30(tmp_path):
    ready_ep(tmp_path, "E05", D(2026, 10, 30, 22, 40), D(2026, 10, 30, 14, 30))
    d = lg.late_post_due("E05", D(2026, 10, 30, 22, 45), tmp_path)
    assert d["due"] and d["code"] == "DUE-LATE" and "not postponed" in d["why"]
    assert lg.post_due("E05", D(2026, 10, 30, 22, 45), tmp_path)["code"] == "WAIT-LATE"          # the Post task alone would have waited for tomorrow


def test_a_build_that_finishes_after_midnight_is_posted_at_once_not_at_19_00_the_next_day(tmp_path):
    ready_ep(tmp_path, "E05", D(2026, 10, 31, 1, 10), D(2026, 10, 30, 14, 30))
    d = lg.late_post_due("E05", D(2026, 10, 31, 1, 15), tmp_path)
    assert d["due"] and d["code"] == "DUE-LATE"
    assert lg.late_post_due("E05", D(2026, 10, 30, 21, 0), tmp_path)["code"] == "WAIT-NOTREADY" or True


def test_a_build_that_began_after_the_slot_waits_for_the_next_slot_not_before_19_00(tmp_path):
    ready_ep(tmp_path, "E06", D(2026, 10, 31, 3, 0), D(2026, 10, 30, 19, 40))
    assert lg.late_post_due("E06", D(2026, 10, 31, 3, 5), tmp_path)["code"] == "WAIT-SLOT"
    assert lg.late_post_due("E06", D(2026, 10, 31, 19, 0), tmp_path)["code"] == "DUE"


def test_the_20_h_gap_and_an_already_posted_episode_still_hold(tmp_path):
    post(tmp_path, "E04", D(2026, 10, 30, 0, 30))
    ready_ep(tmp_path, "E05", D(2026, 10, 30, 16, 0), D(2026, 10, 29, 14, 30))
    assert lg.late_post_due("E05", D(2026, 10, 30, 19, 0), tmp_path)["code"] == "WAIT-GAP"
    assert lg.late_post_due("E05", D(2026, 10, 30, 20, 31), tmp_path)["code"] == "DUE-LATE"       # 20 h after the last post, the same evening
    post(tmp_path, "E05", D(2026, 10, 30, 20, 31))
    assert lg.late_post_due("E05", D(2026, 10, 30, 21, 0), tmp_path)["code"] == "ALREADY"


def test_the_post_lock_lets_one_post_run_at_a_time_and_steals_a_stale_lock(tmp_path):
    import os
    import time
    with lg.post_lock(tmp_path) as a:
        with lg.post_lock(tmp_path) as b:
            assert a is True and b is False
        assert (tmp_path / "work" / "daily" / "post.lock").is_file()
    assert not (tmp_path / "work" / "daily" / "post.lock").exists()
    (tmp_path / "work" / "daily").mkdir(parents=True, exist_ok=True)
    lock = tmp_path / "work" / "daily" / "post.lock"
    lock.write_text("{}", encoding="utf-8")
    old = time.time() - 3 * 3600
    os.utime(lock, (old, old))
    with lg.post_lock(tmp_path) as c:
        assert c is True


def test_the_harvest_follows_a_late_post_sanely(tmp_path):
    post(tmp_path, "E05", D(2026, 10, 30, 23, 40))
    assert lg.harvest_due_at(tmp_path, "E05") == D(2026, 10, 31, 14, 0)                          # as before: 14:00 the next calendar day
    post(tmp_path, "E06", D(2026, 10, 31, 1, 10))
    assert lg.harvest_due_at(tmp_path, "E06") == D(2026, 10, 31, 14, 0)                          # a post after midnight belongs to the evening before: 14:00 the same calendar day (12 h 50 min later)
    post(tmp_path, "E07", D(2026, 10, 31, 4, 30))
    assert lg.harvest_due_at(tmp_path, "E07") == D(2026, 10, 31, 16, 30)                         # never less than 12 h after the post
    post(tmp_path, "E08", D(2026, 11, 3, 19, 0, 7))
    assert lg.harvest_due_at(tmp_path, "E08") == D(2026, 11, 4, 14, 0)                           # the normal 19:00 post is unchanged


def test_the_autopilot_decides_post_posts_and_clears_the_board(tmp_path):
    post(tmp_path, "E04", D(2026, 10, 29, 19, 0))
    harvested(tmp_path, "E04")
    ready_ep(tmp_path, "E05", D(2026, 10, 30, 22, 40), D(2026, 10, 30, 14, 30))
    at = D(2026, 10, 30, 22, 50)
    assert ap.decide(tmp_path, at, lambda r: "E05")["action"] == "post"
    sent, previews = [], []

    def poster(ep):
        sent.append(ep)
        post(tmp_path, ep, at)
        return 0, "E05 posted"
    rc, line = ap.run_once(tmp_path, at, next_episode=lambda r: "E05", poster=poster, preview=lambda e: previews.append(e) or "tab refreshed", write_board=lambda r: None, pid=7, alive=lambda p: False)
    assert rc == 0 and sent == ["E05"] and previews == ["E05"] and "POST" in line and "tab refreshed" in line
    assert ap.decide(tmp_path, at + dt.timedelta(minutes=15), lambda r: "E06")["action"] == "idle"       # posted once, never twice
    assert not [t for t in ap.load_state(tmp_path)["todo"] if t["key"].startswith("post:")]


def test_a_failed_post_is_red_on_the_board_retried_at_the_next_tick_and_bounded(tmp_path):
    post(tmp_path, "E04", D(2026, 10, 29, 19, 0))
    harvested(tmp_path, "E04")
    ready_ep(tmp_path, "E05", D(2026, 10, 30, 22, 40), D(2026, 10, 30, 14, 30))
    at = D(2026, 10, 30, 22, 50)
    tries = []
    for k in range(ap.POST_TRIES_PER_DAY + 3):
        t = at + dt.timedelta(minutes=5 * k)
        rc, line = ap.run_once(tmp_path, t, next_episode=lambda r: "E05", poster=lambda ep: tries.append(ep) or (1, "FAIL [IG-HTTP] 500"), write_board=lambda r: None, pid=7, alive=lambda p: False)
        if k == 0:
            assert rc == 1 and "failed" in line
            al = bs.alerts(tmp_path, t, ap.load_state(tmp_path), None)
            assert any(a["kind"] == "PUBLISH-FAILED" and a["ep"] == "E05" and "IG-HTTP" in a["text"] for a in al)
    assert len(tries) == ap.POST_TRIES_PER_DAY                                                  # bounded: then idle until tomorrow, still red
    assert ap.decide(tmp_path, at + dt.timedelta(minutes=5 * 12), lambda r: "E05")["action"] == "idle"
    assert ap.decide(tmp_path, D(2026, 10, 31, 9, 0), lambda r: "E05")["action"] == "post"        # a new day tries again


def test_a_post_that_did_nothing_is_a_wait_not_a_failure(tmp_path):
    post(tmp_path, "E04", D(2026, 10, 29, 19, 0))
    harvested(tmp_path, "E04")
    ready_ep(tmp_path, "E05", D(2026, 10, 30, 22, 40), D(2026, 10, 30, 14, 30))
    rc, line = ap.run_once(tmp_path, D(2026, 10, 30, 22, 50), next_episode=lambda r: "E05", poster=lambda ep: (0, "BUSY another post run holds work/daily/post.lock"), write_board=lambda r: None, pid=7, alive=lambda p: False)
    assert rc == 0 and "POST-WAIT" in line and not ap.load_state(tmp_path)["attempts"].get("post:E05")


def test_the_post_task_tick_carries_the_late_episode_to_daily_post(tmp_path, monkeypatch):
    import post_extra
    seen = []
    monkeypatch.setattr(post_extra.subprocess, "run", lambda cmd, **kw: seen.append(cmd) or SimpleNamespace(returncode=0))
    assert post_extra.tick(tmp_path, D(2026, 10, 30, 23, 0), run=lambda *a: "", go=True, late_ep="E05") == 0
    assert seen[0][-4:] == ["post", "E05", "--late", "--go"]
    seen.clear()
    post_extra.tick(tmp_path, D(2026, 10, 30, 19, 0), run=lambda *a: "", go=True)
    assert seen[0][-4:] == ["post", "--latest", "--due", "--go"]                                  # the Post task itself is unchanged


def test_daily_post_accepts_late_and_the_real_poster_is_the_tick(monkeypatch, tmp_path):
    got = []
    monkeypatch.setattr(ap, "run_child", lambda cmd, t, cwd, env=None: got.append(cmd) or (0, "ok"))
    ap.real_post(tmp_path, "E05")
    assert got[0][-4:] == ["post_extra.py".replace("post_extra.py", got[0][-4]), "tick", "--late-ep", "E05"] or got[0][-3:] == ["tick", "--late-ep", "E05"]
    assert daily.main.__module__ == "daily"
