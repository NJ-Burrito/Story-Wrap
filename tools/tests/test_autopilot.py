"""The schedule of 2026-10-27 and the autopilot (tools/autopilot.py): post at 19:00 on every platform, harvest at 14:00 the next day, and the autopilot's decision,
lock and launcher. A fake clock and fake files only: no process, no network, no model, no Task Scheduler."""
import datetime as dt
import json
import os
import subprocess
from pathlib import Path

import pytest

import sw_fixtures
import autopilot as ap
import fb
import loop_gate as lg

REPO = Path(__file__).resolve().parents[2]
D = dt.datetime


@pytest.fixture(autouse=True)
def no_real_facebook_token(monkeypatch):
    """R-507: the autopilot also retries a missing Facebook half; the real ~/.config token must not decide a test that has no Facebook record."""
    import loop_gate as _lg
    orig = _lg.has_fb_token
    monkeypatch.setattr(_lg, "has_fb_token", lambda env_path=None: orig(env_path) if env_path else False)


def wj(p, d):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def finish(root, ep, ready=None, retro=True):
    """An episode that is built and complete: gates PASS, critic 9, video, retro ok."""
    w = root / "work" / "episodes" / ep
    wj(w / "gate" / "report.json", {"verdict": "PASS", "complete": True, "checks": [], "fails": []})
    wj(w / "heal" / "critic.json", {"score": 9})
    (w / "episode.mp4").write_bytes(b"\0")
    if ready:
        for f in (w / "gate" / "report.json", w / "heal" / "critic.json", w / "episode.mp4"):
            os.utime(f, (ready.timestamp(), ready.timestamp()))
    stages = {"retro": {"status": "ok"}} if retro else {}
    wj(root / "work" / "daily" / ep / "STATE.json", {"episode": ep, "stages": stages})


def started(root, ep, stages=None):
    """An episode the pipeline started and has not finished (no gate report, no critic)."""
    wj(root / "work" / "daily" / ep / "STATE.json", {"episode": ep, "stages": stages or {"script": {"status": "ok"}}})


def post(root, ep, when):
    wj(root / "work" / "episodes" / ep / "post.json", {"episode": ep, "posted_at": when.isoformat()})


def harvested(root, ep):
    wj(root / "work" / "episodes" / ep / "decision.json", {"episode": ep})


def nxt(root):
    posted = [int(d.name[1:3]) for d in (root / "work" / "episodes").glob("E*") if (d / "post.json").is_file()]
    return f"E{max(posted + [0]) + 1:02d}"


# ------------------------------------------------------------------ 19:00 on every platform
def test_the_slot_is_19_00_for_instagram_facebook_and_the_countdown():
    day = dt.date(2026, 11, 3)
    assert lg.post_slot("E02", day) == D.combine(day, dt.time(19, 0)) == lg.post_slot("E77", day)
    assert lg.fb_slot("E02", day) == lg.post_slot("E02", day)                     # Facebook goes out in the same run: no +60 min
    assert lg.FB_SLOT_OFFSET_MIN == 0 and fb.FB_AFTER_IG_MIN == 0


def test_facebook_goes_live_at_once_after_instagram(tmp_path):
    t = D(2026, 11, 3, 19, 0, 5).astimezone()
    wj(tmp_path / "work" / "episodes" / "E02" / "post.json", {"posted_at": t.isoformat()})
    assert fb.plan_go_live("E02", tmp_path, t + dt.timedelta(seconds=30)) is None      # nothing to schedule ahead: published now


def test_post_window_matches_the_cutoff_and_the_task_ticks():
    sch = json.loads(sw_fixtures.SCHEDULE.read_text(encoding="utf-8"))["tasks"]["StoryWrap-Post"]
    assert sch["from"] == "19:00" and sch["every_min"] == 5
    slot = D.combine(dt.date(2026, 11, 3), dt.time(19, 0))
    assert (slot + dt.timedelta(minutes=lg.POST_GRACE_MIN)).time() == lg.POST_CUTOFF == dt.time(20, 30)
    import ig_board
    ticks = ig_board.ticks_of(sch, slot.date())
    assert ticks[0] == slot and ticks[-1].time() == dt.time(20, 25) and ticks[-1].time() < lg.POST_CUTOFF


def test_post_due_only_inside_the_window_after_19_00(tmp_path):
    at = lambda h, m: D(2026, 11, 3, h, m)      # noqa: E731
    assert lg.post_due("E02", at(18, 59), tmp_path)["code"] == "WAIT-SLOT"
    assert lg.post_due("E02", at(19, 0), tmp_path)["due"] is True and lg.post_due("E02", at(20, 25), tmp_path)["due"] is True     # a retry of a failed attempt
    late = lg.post_due("E02", at(20, 30), tmp_path)
    assert late["due"] is False and late["code"] == "WAIT-LATE" and "19:00" in late["why"]
    assert lg.post_due("E02", at(19, 0) + dt.timedelta(days=1), tmp_path)["due"] is True


def test_an_episode_not_ready_at_19_00_waits_for_the_next_19_00(tmp_path):
    slot = D(2026, 11, 3, 19, 0)
    finish(tmp_path, "E02", ready=D(2026, 11, 3, 19, 12))                                  # the critic passed at 19:12
    d = lg.post_due("E02", D(2026, 11, 3, 19, 15), tmp_path)
    assert d["due"] is False and d["code"] == "WAIT-NOTREADY" and "never off-slot" in d["why"]
    assert lg.next_post_slot("E02", D(2026, 11, 3, 19, 15), tmp_path) == slot + dt.timedelta(days=1)
    assert lg.post_due("E02", slot + dt.timedelta(days=1), tmp_path)["due"] is True        # tomorrow at 19:00 it is posted
    ready_early = tmp_path / "e"
    finish(ready_early, "E02", ready=D(2026, 11, 3, 15, 30))
    assert lg.post_due("E02", slot, ready_early)["due"] is True                            # ready at 15:30: posts at 19:00


def test_the_post_gap_still_holds(tmp_path):
    post(tmp_path, "E01", D(2026, 11, 3, 0, 30))
    assert lg.post_due("E02", D(2026, 11, 3, 19, 0), tmp_path)["code"] == "WAIT-GAP"


# ------------------------------------------------------------------ the harvest is 14:00 the next day
def test_harvest_is_due_at_14_00_the_day_after_the_later_post(tmp_path):
    post(tmp_path, "E02", D(2026, 11, 3, 19, 0, 7))
    assert lg.harvest_due_at(tmp_path, "E02") == D(2026, 11, 4, 14, 0)
    wj(tmp_path / "work" / "episodes" / "E02" / "facebook.json", {"publish_at": "2026-11-03T19:01:00"})
    assert lg.harvest_due_at(tmp_path, "E02") == D(2026, 11, 4, 14, 0)
    post(tmp_path, "E03", D(2026, 11, 3, 23, 50))                                          # a post just before midnight: the day after is the 4th
    assert lg.harvest_due_at(tmp_path, "E03") == D(2026, 11, 4, 14, 0)
    assert lg.harvest_due_at(tmp_path, "E09") is None                                      # not posted


def test_the_loop_gate_and_the_board_use_the_14_00_time(tmp_path):
    post(tmp_path, "E01", D(2026, 11, 3, 19, 0))
    g = lg.check("E02", tmp_path, token=True, at=D(2026, 11, 4, 9, 0))
    assert g["code"] == "WAIT-HARVEST" and g["due"] == "2026-11-04T14:00"
    assert "overdue" in lg.check("E02", tmp_path, token=True, at=D(2026, 11, 4, 14, 30))["why"]


def test_ig_board_harvests_nothing_before_14_00_and_everything_at_14_00(tmp_path):
    import ig_board
    post(tmp_path, "E01", D(2026, 11, 3, 19, 0))
    seen = []
    kw = dict(token=True, do_comments=lambda e: seen.append(e), do_tally=lambda e: None, do_next=lambda e: None)
    assert ig_board.harvest_due(tmp_path, go=True, at=D(2026, 11, 4, 13, 59), **kw)["harvested"] == []         # 19 h after the post, but not yet 14:00
    assert ig_board.harvest_due(tmp_path, go=True, at=D(2026, 11, 4, 14, 0), **kw)["harvested"] == ["E01"] and seen == ["E01"]


def test_the_learning_review_is_due_with_the_harvest(tmp_path):
    import learn
    post(tmp_path, "E01", D(2026, 11, 3, 19, 0))
    assert learn.review_due_at(tmp_path, "E01") == D(2026, 11, 4, 14, 0)


def test_the_ig_plan_names_14_00_the_next_day(tmp_path):
    import ig
    wj(tmp_path / "work" / "episodes" / "E01" / "post.json", {"posted_at": D(2026, 11, 3, 19, 0).astimezone().isoformat()})
    cmd = ig.cmd_plan("E01", tmp_path)
    assert "/SD 04/11/2026" in cmd and "/ST 14:00" in cmd


# ------------------------------------------------------------------ the autopilot decides
NOW = D(2026, 11, 4, 14, 0)


def dec(root, at=NOW, state=None):
    return ap.decide(root, at, nxt, state or ap.load_state(root))


def test_nothing_posted_yet_is_idle(tmp_path):
    assert dec(tmp_path)["action"] == "idle"


def test_a_built_but_incomplete_episode_is_finished_first_and_not_harvested(tmp_path):
    post(tmp_path, "E01", D(2026, 11, 3, 19, 0))
    harvested(tmp_path, "E01")
    started(tmp_path, "E02")                                                               # the E02 of today: built, critic pending
    d = dec(tmp_path)
    assert d["action"] == "finish" and d["ep"] == "E02"


def test_finishing_waits_for_a_harvest_that_the_loop_gate_needs_and_does_it_when_due(tmp_path):
    post(tmp_path, "E01", D(2026, 11, 3, 19, 0))
    started(tmp_path, "E02")                                                               # E01 is not harvested: E02 cannot run
    early = dec(tmp_path, D(2026, 11, 4, 9, 0))
    assert early["action"] == "idle" and early["due"] == "2026-11-04T14:00"
    due = dec(tmp_path, NOW)
    assert due["action"] == "harvest-next" and due["ep"] == "E01" and due["next"] == "E02"


def test_after_14_00_the_post_is_harvested_and_the_next_episode_built(tmp_path):
    post(tmp_path, "E02", D(2026, 11, 3, 19, 0))
    assert dec(tmp_path, D(2026, 11, 4, 13, 59))["action"] == "idle"
    d = dec(tmp_path, NOW)
    assert d["action"] == "harvest-next" and d["ep"] == "E02" and d["next"] == "E03"
    assert dec(tmp_path, D(2026, 11, 4, 17, 30))["action"] == "harvest-next"               # a later tick resumes a harvest that did not finish


def test_a_harvested_post_with_no_successor_builds_the_next_episode(tmp_path):
    post(tmp_path, "E02", D(2026, 11, 3, 19, 0))
    harvested(tmp_path, "E02")
    d = dec(tmp_path)
    assert d["action"] == "build-next" and d["ep"] == "E03"


def test_a_complete_episode_waits_for_the_19_00_post(tmp_path):
    post(tmp_path, "E02", D(2026, 11, 3, 19, 0))
    harvested(tmp_path, "E02")
    finish(tmp_path, "E03", ready=D(2026, 11, 4, 15, 30))        # ready before today's slot (R-507: a complete episode is judged against its slot, so its files carry the test's clock)
    d = dec(tmp_path, D(2026, 11, 4, 16, 0))
    assert d["action"] == "idle" and "19:00" in d["why"]


def test_after_the_third_failure_of_the_day_it_is_stuck_until_tomorrow(tmp_path):
    post(tmp_path, "E02", D(2026, 11, 3, 19, 0))
    harvested(tmp_path, "E02")
    started(tmp_path, "E03")
    st = ap.load_state(tmp_path)
    for _ in range(ap.MAX_ATTEMPTS):
        ap.record_failure(tmp_path, st, "E03", 1, NOW)
    assert dec(tmp_path, NOW, st)["action"] == "stuck"
    assert dec(tmp_path, NOW + dt.timedelta(days=1), st)["action"] == "finish"             # a new day resets the count


# ------------------------------------------------------------------ one run, with fakes
def run(root, at=NOW, harvest=None, build=None, **kw):
    boards = []
    rc, line = ap.run_once(root, at, next_episode=nxt, harvest=harvest or (lambda e: {"rc": 0, "notes": []}), build=build or (lambda e: (0, "done")),
                           write_board=lambda r: boards.append(1), pid=4242, alive=lambda p: False, **kw)
    return rc, line


def test_run_harvests_then_builds_and_writes_one_log_line_and_the_board(tmp_path):
    post(tmp_path, "E02", D(2026, 11, 3, 19, 0))
    calls = []

    def harvest(ep):
        calls.append(("harvest", ep))
        harvested(tmp_path, ep)
        return {"rc": 0, "notes": ["inbox rc=0"]}
    rc, line = run(tmp_path, harvest=harvest, build=lambda e: (calls.append(("build", e)) or 0, "ready"))
    assert rc == 0 and calls == [("harvest", "E02"), ("build", "E03")] and "HARVEST+BUILD" in line
    log = (tmp_path / "work" / "daily" / "autopilot.log").read_text(encoding="utf-8").splitlines()
    assert len(log) == 1 and log[0].startswith("2026-11-04 14:00:00")
    assert json.loads((tmp_path / "work" / "daily" / "tasks" / "StoryWrap-Autopilot.json").read_text(encoding="utf-8"))["status"] == "OK"
    assert not (tmp_path / "work" / "daily" / "autopilot.lock").exists()                       # released


def test_run_never_builds_when_the_harvest_left_no_decision(tmp_path):
    post(tmp_path, "E02", D(2026, 11, 3, 19, 0))
    built = []
    rc, line = run(tmp_path, harvest=lambda e: {"rc": 3, "notes": []}, build=lambda e: built.append(e) or (0, ""))
    assert built == [] and rc == 1 and "did not finish" in line
    assert any("harvest:E02" == t["key"] for t in ap.load_state(tmp_path)["todo"])           # the owner sees it on the board


def test_run_with_nothing_to_do_is_idle_and_exit_0(tmp_path):
    post(tmp_path, "E02", D(2026, 11, 3, 19, 0))
    rc, line = run(tmp_path, at=D(2026, 11, 4, 9, 0), harvest=lambda e: pytest.fail("too early"), build=lambda e: pytest.fail("too early"))
    assert rc == 0 and "WAIT" not in line.split()[2] and line.split()[2] == "IDLE"


def test_a_deterministic_stop_ends_with_exit_6_once_and_then_stays_quiet(tmp_path):
    post(tmp_path, "E02", D(2026, 11, 3, 19, 0))
    harvested(tmp_path, "E02")
    started(tmp_path, "E03")
    (tmp_path / "work" / "daily" / "E03" / "STOPPED.md").write_text("# stopped\n\n`FAIL [CRITIC-LOW]` critic score 6 < 9 after 2 heal round(s)\n", encoding="utf-8")
    rc, line = run(tmp_path, build=lambda e: (1, "FAIL [CRITIC-LOW] critic score 6"))
    assert rc == ap.NEEDS_LEAD_RC == 6 and ap.load_state(tmp_path)["needs_lead"]["ep"] == "E03"
    rc2, line2 = run(tmp_path, at=NOW + dt.timedelta(minutes=30), build=lambda e: pytest.fail("a spent heal is not retried"))
    assert rc2 == 0 and "STUCK" in line2


def test_a_transient_failure_is_retried_by_the_next_tick(tmp_path):
    post(tmp_path, "E02", D(2026, 11, 3, 19, 0))
    harvested(tmp_path, "E02")
    started(tmp_path, "E03")
    rc, _ = run(tmp_path, build=lambda e: (1, "FAIL [TIMEOUT] shots"))
    assert rc == 1 and dec(tmp_path, NOW + dt.timedelta(minutes=30))["action"] == "finish"


def test_the_token_budget_stops_the_day_without_calling_the_lead(tmp_path):
    post(tmp_path, "E02", D(2026, 11, 3, 19, 0))
    harvested(tmp_path, "E02")
    started(tmp_path, "E03")
    rc, _ = run(tmp_path, build=lambda e: (3, "FAIL [LLM-BUDGET]"))
    assert rc == 3 and ap.load_state(tmp_path).get("needs_lead") is None


def test_dry_run_changes_nothing(tmp_path):
    post(tmp_path, "E02", D(2026, 11, 3, 19, 0))
    rc, line = ap.run_once(tmp_path, NOW, next_episode=nxt, dry=True)
    assert rc == 0 and line.split()[2] == "DRY-HARVEST-NEXT" and not (tmp_path / "work" / "daily").exists()


def test_the_lead_repair_executes_one_allowed_action_only(tmp_path):
    state = ap.load_state(tmp_path)
    state["needs_lead"] = {"ep": "E03", "code": "CRITIC-LOW"}
    ap.save_state(tmp_path, state)
    seen = {}

    def llm(prompt, name):
        seen["prompt"] = prompt
        d = tmp_path / "work" / "daily"
        (d / "autopilot-lead-2026-11-04.md").write_text("cause: x\n", encoding="utf-8")
        (d / "autopilot-lead-2026-11-04.json").write_text(json.dumps({"action": "rerun-stage", "stage": "critic", "reason": "transient"}), encoding="utf-8")
        return {"rc": 0}
    forced = []
    rc, line = ap.lead_once(tmp_path, NOW, llm=llm, build=lambda e, f=None: forced.append((e, f)) or (0, "ok"))
    assert rc == 0 and forced == [("E03", "critic")] and "E03" in seen["prompt"] and "NO shell" in seen["prompt"]
    assert "executed by the autopilot" in (tmp_path / "work" / "daily" / "autopilot-lead-2026-11-04.md").read_text(encoding="utf-8")
    assert ap.lead_once(tmp_path, NOW, llm=lambda *a: pytest.fail("once a day"))[1].split()[2] == "LEAD-SKIP"


@pytest.mark.parametrize("text,action", [('{"action": "rerun"}', "rerun"), ('{"action": "rerun-stage", "stage": "shots"}', "rerun-stage"),
                                         ('{"action": "rerun-stage", "stage": "script"}', "give-up"), ('{"action": "rerun-stage", "stage": "voice"}', "give-up"),
                                         ('{"action": "post"}', "give-up"), ("not json", "give-up"), ("[1]", "give-up")])
def test_lead_decisions_are_limited_to_the_menu(text, action):
    assert ap.parse_lead_decision(text)["action"] == action


def test_the_lead_command_uses_the_job_flags_of_build_cmd():
    import daily
    cmd = daily.build_cmd("claude", "p", tools="Read,Glob,Grep,Write,Edit")
    assert "--permission-mode" in cmd and "dontAsk" in cmd and "--max-turns" in cmd and "--max-budget-usd" in cmd
    assert "Bash" in cmd[cmd.index("--disallowedTools") + 1]
    with pytest.raises(ValueError):
        daily.build_cmd("claude", "p", tools="Read,Bash,Agent")


# ------------------------------------------------------------------ the lock
def test_lock_excludes_a_live_run_and_steals_a_dead_or_old_one(tmp_path):
    t = D(2026, 11, 4, 14, 0)
    assert ap.lock_acquire(tmp_path, t, pid=111, alive=lambda p: True)
    assert not ap.lock_acquire(tmp_path, t + dt.timedelta(minutes=30), pid=222, alive=lambda p: True)          # the first is alive
    assert ap.lock_acquire(tmp_path, t + dt.timedelta(minutes=30), pid=222, alive=lambda p: False)             # its process is gone: stolen
    assert not ap.lock_acquire(tmp_path, t + dt.timedelta(minutes=31), pid=333, alive=lambda p: True)
    assert ap.lock_acquire(tmp_path, t + dt.timedelta(hours=ap.LOCK_STALE_H + 1), pid=333, alive=lambda p: True)  # older than the task limit: stale
    ap.lock_release(tmp_path, pid=999)                                                                         # not ours: kept
    assert (tmp_path / "work" / "daily" / "autopilot.lock").exists()
    ap.lock_release(tmp_path, pid=333)
    assert not (tmp_path / "work" / "daily" / "autopilot.lock").exists()


def test_a_second_run_while_locked_does_nothing(tmp_path):
    post(tmp_path, "E02", D(2026, 11, 3, 19, 0))
    assert ap.lock_acquire(tmp_path, NOW, pid=1, alive=lambda p: True)
    rc, line = ap.run_once(tmp_path, NOW, next_episode=nxt, harvest=lambda e: pytest.fail("locked"), build=lambda e: pytest.fail("locked"), alive=lambda p: True, pid=2)
    assert rc == 0 and "LOCKED" in line


def test_the_real_pid_probe_knows_itself_and_not_pid_0():
    assert ap.pid_alive(os.getpid()) and not ap.pid_alive(0)


# ------------------------------------------------------------------ the launcher (pure)
def test_launch_plan_starts_vscode_only_when_it_is_not_running():
    root = Path("<repo>")
    p = ap.launch_plan(root, "uv", False, "C:/bin/code.cmd", "/home/x/AppData/Local")
    assert p["vscode"] == ["C:/bin/code.cmd", str(root)]
    assert ap.launch_plan(root, "uv", True, "C:/bin/code.cmd")["vscode"] is None
    fallback = ap.launch_plan(root, "uv", False, None, "/home/x/AppData/Local")["vscode"]
    assert Path(fallback[0]) == Path("/home/x/AppData/Local/Programs/Microsoft VS Code/Code.exe") and fallback[1] == str(root)
    assert ap.launch_plan(root, "uv", False, None, None)["vscode"] is None                    # nothing to start it with: go on headless
    assert p["autopilot"] == ["uv", "run", "tools/daily.py", "autopilot"] and p["lead"] == p["autopilot"] + ["--lead"]
    assert p["env"] == {"PYTHONUTF8": "1", "SW_LLM_DAILY_TOKENS": "5000000"}


def powershell():
    r = subprocess.run(["where", "powershell"], capture_output=True, text=True)
    exe = r.stdout.split("\n")[0].strip()
    if not exe:
        pytest.skip("no powershell")
    return exe


def test_autopilot_ps1_builds_the_same_commands_as_the_python_function():
    exe = powershell()
    for running, args in ((False, ["-CodePath", "C:\\bin\\code.cmd"]), (True, ["-CodePath", "C:\\bin\\code.cmd", "-CodeRunning"]), (False, ["-LocalAppData", "C:\\Users\\x\\AppData\\Local"])):
        r = subprocess.run([exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(REPO / "tools" / "autopilot.ps1"), "-PlanOnly", "-Uv", "uv", *args],
                           capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, r.stderr
        got = json.loads(r.stdout)
        want = ap.launch_plan(REPO, "uv", running, "C:\\bin\\code.cmd" if "-CodePath" in args else None, "C:\\Users\\x\\AppData\\Local" if "-LocalAppData" in args else None)
        assert got["autopilot"] == want["autopilot"] and got["lead"] == want["lead"] and got["env"] == want["env"]
        assert (got["vscode"] is None) == (want["vscode"] is None)
        if want["vscode"]:
            assert [os.path.normcase(x) for x in got["vscode"]] == [os.path.normcase(x) for x in want["vscode"]]


def test_the_scripts_register_nothing_in_a_dry_run_and_describe_the_task():
    exe = powershell()
    r = subprocess.run([exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(REPO / "tools" / "register-autopilot.ps1"), "-DryRun"], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "StoryWrap-Autopilot : every 15 min around the clock" in out and "Interactive" in out and "StartWhenAvailable" in out and "no WakeToRun" in out and "no admin" in out
    assert "IgnoreNew" in out and "limit 5 h" in out and "StoryWrap-Daily" in out and "daily at 19:00" in out
    src = (REPO / "tools" / "register-autopilot.ps1").read_text(encoding="utf-8")
    assert "-Unregister" in src and "Disable-ScheduledTask" in src and "-MultipleInstances IgnoreNew" in src and "-LogonType Interactive" in src
    sch = json.loads(sw_fixtures.SCHEDULE.read_text(encoding="utf-8"))["tasks"]
    assert sch["StoryWrap-Autopilot"]["from"] == "00:00" and sch["StoryWrap-Autopilot"]["limit_h"] == 5 and "StoryWrap-Daily" not in sch
    import ig_board
    ticks = [t.strftime("%H:%M") for t in ig_board.ticks_of(sch["StoryWrap-Autopilot"], dt.date(2026, 11, 4))]
    assert len(ticks) == 96 and ticks[0] == "00:00" and "18:45" in ticks and "23:45" in ticks      # R-505: around the clock, not 14:00 to 18:30


def test_daily_py_autopilot_entry_is_wired(tmp_path, monkeypatch, capsys):
    import daily
    monkeypatch.setenv("SW_LLM_DAILY_TOKENS", "5000000")
    monkeypatch.setattr(ap, "ROOT", tmp_path)
    monkeypatch.setattr(ap, "run_once", lambda root, *a, **k: (0, "2026-11-04 14:00:00 IDLE - rc=0 test"))
    assert daily.main(["autopilot"]) == 0 and "IDLE" in capsys.readouterr().out


def test_a_fixed_plan_clears_the_day_s_failure_count(tmp_path):
    # 2026-10-29: one deterministic stop parked E04 for the day although its plan was fixed minutes later
    import os, time
    d = tmp_path / "bible" / "series" / "s" / "episodes" / "E09"
    d.mkdir(parents=True)
    plan = d / "calm-plan.json"
    plan.write_text("{}", encoding="utf-8")
    old = time.time() - 3600
    os.utime(plan, (old, old))
    st = {"attempts": {"E09": {"date": "2026-10-29", "n": 3, "at": dt.datetime.fromtimestamp(old + 60).isoformat(timespec="seconds")}, "harvest:E08": {"date": "2026-10-29", "n": 1, "at": "2026-10-29T14:00:00"}}}
    ap.forget_fixed_failures(tmp_path, st)
    assert "E09" in st["attempts"]                    # unchanged since the failure: still parked
    os.utime(plan, None)
    ap.forget_fixed_failures(tmp_path, st)
    assert "E09" not in st["attempts"] and "harvest:E08" in st["attempts"]
