"""R-505 (owner, 2026-10-30): the autopilot ticks around the clock, never parks an episode silently, retries when the code or the inputs changed, backs off otherwise, writes a
FIX-REQUEST.md when nobody can heal a stop, and the board shows all of it in a live Build panel. Fake clock and fake files only: no process, no network, no Task Scheduler."""
import datetime as dt
import json
import os
import time
from pathlib import Path

import pytest

import sw_fixtures
import autopilot as ap
import build_status as bs
import loop_gate as lg

REPO = Path(__file__).resolve().parents[2]
D = dt.datetime
NOW = D(2026, 10, 30, 19, 30)


@pytest.fixture(autouse=True)
def no_real_facebook_token(monkeypatch):
    """R-507: the autopilot also retries a missing Facebook half; the real ~/.config token must not decide a test that has no Facebook record."""
    import loop_gate as _lg
    orig = _lg.has_fb_token
    monkeypatch.setattr(_lg, "has_fb_token", lambda env_path=None: orig(env_path) if env_path else False)


def wj(p, d):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def nxt(root):
    return "E05"


def world(root, stop="SHOT-GATE"):
    """E04 posted and harvested; E05 started and stopped by `stop`."""
    wj(root / "work" / "episodes" / "E04" / "post.json", {"episode": "E04", "posted_at": "2026-10-29T19:00:00"})
    wj(root / "work" / "episodes" / "E04" / "decision.json", {"episode": "E04"})
    wj(root / "work" / "daily" / "E05" / "STATE.json", {"episode": "E05", "stages": {"script": {"status": "ok"}, "shots": {"status": "failed", "check": stop, "message": "1 shot failed"}}})
    (root / "work" / "daily" / "E05" / "STOPPED.md").write_text(f"# stopped\n\nepisode E05, stage shots\n\n`FAIL [{stop}]` E05-s01: FAIL [hands] hand_scale 0.12 over cap_s=2.45 s (details: work/shots/E05-s01/gate/report.txt)\n", encoding="utf-8")


def dec(root, at, st):
    return ap.decide(root, at, nxt, st)


def fail(root, st, at, n=1, rc=1):
    for _ in range(n):
        ap.record_failure(root, st, "E05", rc, at)


# ------------------------------------------------------------------ A. scheduling
def test_the_autopilot_ticks_every_15_minutes_around_the_clock_and_the_post_slot_stays():
    import ig_board
    sch = json.loads(sw_fixtures.SCHEDULE.read_text(encoding="utf-8"))["tasks"]
    t = [x.strftime("%H:%M") for x in ig_board.ticks_of(sch["StoryWrap-Autopilot"], dt.date(2026, 11, 4))]
    assert len(t) == 96 and {"00:00", "03:15", "14:00", "18:45", "19:00", "23:45"} <= set(t)
    assert sch["StoryWrap-Post"]["from"] == "19:00" and sch["StoryWrap-Post"]["every_min"] == 5          # the owner's 19:00 post rule is untouched
    src = (REPO / "tools" / "register-autopilot.ps1").read_text(encoding="utf-8")
    assert "-RunLevel Limited" in src and "-WakeToRun" not in src.split("$settings =")[1].split("\n")[0] and "-RepetitionDuration (New-TimeSpan -Days 3650)" in src


def test_an_episode_finished_after_19_00_is_posted_at_the_next_slot_not_early(tmp_path):
    wj(tmp_path / "work" / "episodes" / "E05" / "gate" / "report.json", {"verdict": "PASS", "complete": True, "checks": [], "fails": []})
    wj(tmp_path / "work" / "episodes" / "E05" / "heal" / "critic.json", {"score": 9})
    (tmp_path / "work" / "episodes" / "E05" / "episode.mp4").write_bytes(b"\0")
    ready = D(2026, 10, 30, 19, 40)
    for f in ("gate/report.json", "heal/critic.json", "episode.mp4"):
        os.utime(tmp_path / "work" / "episodes" / "E05" / f, (ready.timestamp(), ready.timestamp()))
    due = lg.post_due("E05", D(2026, 10, 30, 19, 55), tmp_path)
    assert due["due"] is False                                                                              # ready after the slot: not posted early
    assert lg.post_due("E05", D(2026, 10, 31, 19, 0), tmp_path)["due"] is True                              # the next 19:00 posts it


# ------------------------------------------------------------------ B. never park silently
def test_after_three_failures_the_episode_is_backed_off_then_retried_every_two_hours(tmp_path):
    world(tmp_path)
    st = ap.load_state(tmp_path)
    fail(tmp_path, st, NOW)
    d = dec(tmp_path, NOW + dt.timedelta(minutes=30), st)
    assert d["action"] == "stuck" and d["due"] == (NOW + dt.timedelta(hours=2)).isoformat(timespec="minutes") and "nothing changed" in d["why"] and "tomorrow" not in d["why"].replace("or tomorrow", "")
    assert dec(tmp_path, NOW + dt.timedelta(hours=1, minutes=59), st)["action"] == "stuck"
    assert dec(tmp_path, NOW + dt.timedelta(hours=2), st)["action"] == "finish"                          # the backoff retry is due


def test_backoff_retries_are_capped_per_day_and_a_new_day_resets(tmp_path):
    world(tmp_path)
    st = ap.load_state(tmp_path)
    t = NOW.replace(hour=8)
    fail(tmp_path, st, t)
    for k in range(ap.BACKOFF_MAX_PER_DAY):
        t += dt.timedelta(hours=2)
        assert dec(tmp_path, t, st)["action"] == "finish"
        fail(tmp_path, st, t)
    assert st["attempts"]["E05"]["backoff_n"] == ap.BACKOFF_MAX_PER_DAY
    d = dec(tmp_path, t + dt.timedelta(hours=3), st)
    assert d["action"] == "stuck" and d["due"] is None and "backoff retries" in d["why"]
    assert dec(tmp_path, D(2026, 10, 31, 0, 15), st)["action"] == "finish"


def test_a_merged_code_change_retries_at_once(tmp_path):
    world(tmp_path)
    (tmp_path / "tools").mkdir()
    code = tmp_path / "tools" / "plan.py"
    code.write_text("x = 1\n", encoding="utf-8")
    st = ap.load_state(tmp_path)
    fail(tmp_path, st, NOW)
    assert dec(tmp_path, NOW + dt.timedelta(minutes=15), st)["action"] == "stuck"                        # unchanged code: still backed off
    code.write_text("x = 2\n", encoding="utf-8")                                                          # the fix is merged
    assert dec(tmp_path, NOW + dt.timedelta(minutes=30), st)["action"] == "finish" and "E05" not in st["attempts"]
    (tmp_path / "tools" / "tests").mkdir()
    (tmp_path / "tools" / "tests" / "test_x.py").write_text("y", encoding="utf-8")
    assert ap.code_fingerprint(tmp_path) == ap.code_fingerprint(tmp_path)                                 # stable; a test file is not code that runs


def test_the_fingerprint_ignores_tests_and_follows_templates_and_heal_json(tmp_path):
    (tmp_path / "tools" / "tests").mkdir(parents=True)
    (tmp_path / "tools" / "a.py").write_text("1", encoding="utf-8")
    base = ap.code_fingerprint(tmp_path)
    (tmp_path / "tools" / "tests" / "t.py").write_text("2", encoding="utf-8")
    assert ap.code_fingerprint(tmp_path) == base
    wj(tmp_path / "pipelines" / "heal.json", {"a": 1})
    assert ap.code_fingerprint(tmp_path) != base


def test_any_changed_stage_input_retries_at_once(tmp_path):
    world(tmp_path)
    ed = tmp_path / "bible" / "series" / "s" / "episodes" / "E05"
    ed.mkdir(parents=True)
    f = ed / "shots.json"                                   # not script.json or calm-plan.json: the old rule missed it
    f.write_text("{}", encoding="utf-8")
    st = ap.load_state(tmp_path)
    failed = NOW - dt.timedelta(minutes=30)
    fail(tmp_path, st, failed)
    ts = failed.timestamp()
    os.utime(f, (ts - 3600, ts - 3600))
    assert dec(tmp_path, NOW, st)["action"] == "stuck"                                                    # input older than the failure: still backed off
    os.utime(f, (ts + 60, ts + 60))                                                                      # edited after the failure
    assert dec(tmp_path, NOW, st)["action"] == "finish" and "E05" not in st["attempts"]


def test_no_retry_past_the_token_budget_or_the_machine_cap(tmp_path):
    world(tmp_path)
    st = ap.load_state(tmp_path)
    fail(tmp_path, st, NOW)
    later = NOW + dt.timedelta(hours=3)
    wj(tmp_path / "work" / "daily" / f"budget-{later.date().isoformat()}.json", {"tokens": 5_000_000, "limit": 5_000_000, "calls": []})
    d = dec(tmp_path, later, st)
    assert d["action"] == "stuck" and "token budget" in d["why"] and d["due"] is None
    os.remove(tmp_path / "work" / "daily" / f"budget-{later.date().isoformat()}.json")
    wj(tmp_path / "work" / "daily" / "E05" / "deadline.json", {"machine_s": 14400, "cap_s": 14400})
    d = dec(tmp_path, later, st)
    assert d["action"] == "stuck" and "machine cap" in d["why"] and d["due"] is None


def test_a_heal_with_rounds_left_is_still_not_stuck(tmp_path, monkeypatch):
    world(tmp_path, "CAP-READING-SPEED")
    monkeypatch.setattr(ap, "heal_pending", lambda *a: True)
    st = ap.load_state(tmp_path)
    st["attempts"]["E05"] = {"date": NOW.date().isoformat(), "n": 3, "at": NOW.isoformat(timespec="seconds")}
    assert dec(tmp_path, NOW, st)["action"] == "finish"


def test_a_stuck_tick_writes_a_fix_request_and_a_parked_entry_and_success_resolves_it(tmp_path):
    world(tmp_path)
    st = ap.load_state(tmp_path)
    fail(tmp_path, st, NOW.replace(hour=18))
    ap.save_state(tmp_path, st)
    rc, line = ap.run_once(tmp_path, NOW.replace(hour=18, minute=30), next_episode=nxt, build=lambda e: pytest.fail("backed off"), harvest=lambda e: pytest.fail("n/a"),
                           write_board=lambda r: None, pid=1, alive=lambda p: False)
    assert rc == 0 and " STUCK " in line
    fr = tmp_path / "work" / "daily" / "E05" / "FIX-REQUEST.md"
    txt = fr.read_text(encoding="utf-8")
    assert "SHOT-GATE" in txt and "hand_scale" in txt and "2.45 s" in txt and "never a gate" in txt
    state = ap.load_state(tmp_path)
    assert "E05" in state["parked"] and state["parked"]["E05"]["due"]
    b = json.loads((tmp_path / "board" / "data" / "build.json").read_text(encoding="utf-8"))
    assert {a["kind"] for a in b["alerts"]} >= {"STOPPED", "FIX-REQUEST", "STUCK"}
    rc, _ = ap.run_once(tmp_path, NOW.replace(hour=20, minute=30), next_episode=nxt, build=lambda e: (0, "ready"), harvest=lambda e: {"rc": 0, "notes": []},
                        write_board=lambda r: None, pid=1, alive=lambda p: False)
    assert rc == 0 and not fr.exists() and (fr.parent / "FIX-REQUEST.resolved.md").exists()


def test_a_lead_give_up_writes_a_fix_request(tmp_path):
    world(tmp_path)
    st = ap.load_state(tmp_path)
    st["needs_lead"] = {"ep": "E05", "code": "SHOT-GATE"}
    ap.save_state(tmp_path, st)

    def llm(prompt, name):
        assert "FIX-REQUEST.md" in prompt
        d = tmp_path / "work" / "daily"
        (d / f"autopilot-lead-{NOW.date().isoformat()}.md").write_text("cause\n", encoding="utf-8")
        (d / f"autopilot-lead-{NOW.date().isoformat()}.json").write_text(json.dumps({"action": "give-up", "reason": "the parallax gate needs a tool change"}), encoding="utf-8")
        return {"rc": 0}
    rc, line = ap.lead_once(tmp_path, NOW, llm=llm)
    txt = (tmp_path / "work" / "daily" / "E05" / "FIX-REQUEST.md").read_text(encoding="utf-8")
    assert "the parallax gate needs a tool change" in txt and "SHOT-GATE" in txt


def test_a_fix_request_the_lead_wrote_is_kept(tmp_path):
    world(tmp_path)
    st = ap.load_state(tmp_path)
    st["needs_lead"] = {"ep": "E05", "code": "SHOT-GATE"}
    ap.save_state(tmp_path, st)

    def llm(prompt, name):
        d = tmp_path / "work" / "daily"
        (d / f"autopilot-lead-{NOW.date().isoformat()}.md").write_text("cause\n", encoding="utf-8")
        (d / f"autopilot-lead-{NOW.date().isoformat()}.json").write_text(json.dumps({"action": "give-up", "reason": "x"}), encoding="utf-8")
        (d / "E05" / "FIX-REQUEST.md").write_text("LEAD-WROTE-THIS\n", encoding="utf-8")
        return {"rc": 0}
    ap.lead_once(tmp_path, NOW, llm=llm)
    assert (tmp_path / "work" / "daily" / "E05" / "FIX-REQUEST.md").read_text(encoding="utf-8") == "LEAD-WROTE-THIS\n"


def test_identical_idle_ticks_do_not_bury_the_log(tmp_path):
    ap.append_log(tmp_path, "2026-10-30 14:00:04 FINISH E05 rc=1 E05 stopped (rc 1, SHOT-GATE)")
    for m in (15, 30, 45):
        ap.append_log(tmp_path, f"2026-10-30 14:{m}:04 IDLE E05 rc=0 waiting")
    log = (tmp_path / "work" / "daily" / "autopilot.log").read_text(encoding="utf-8").splitlines()
    assert len(log) == 2 and log[0].startswith("2026-10-30 14:00:04 FINISH") and log[1].startswith("2026-10-30 14:45:04 IDLE")
    ap.append_log(tmp_path, "2026-10-30 15:00:04 IDLE E05 rc=0 different")
    assert len((tmp_path / "work" / "daily" / "autopilot.log").read_text(encoding="utf-8").splitlines()) == 3


# ------------------------------------------------------------------ D. the Build panel data
def test_build_status_shows_the_e05_stop_in_red_with_its_stages_and_heals(tmp_path):
    world(tmp_path)
    wj(tmp_path / "work" / "daily" / "E05" / "read-heal.json", {"rounds": 1, "events": [{"at": "2026-10-30T18:05:35"}]})
    wj(tmp_path / "work" / "daily" / "E05" / "refit.json", {"lines": {"H01": {"rounds": 1}}, "events": [{"at": "2026-10-30T16:53:53"}], "exhausted": None})
    wj(tmp_path / "work" / "daily" / "E05" / "deadline.json", {"machine_s": 3420, "cap_s": 14400})
    wj(tmp_path / "work" / "daily" / "budget-2026-10-30.json", {"tokens": 375030, "limit": 5_000_000, "calls": []})
    wj(tmp_path / "board" / "schedule.json", json.loads(sw_fixtures.SCHEDULE.read_text(encoding="utf-8")))
    wj(tmp_path / "work" / "daily" / "autopilot.json", {"last": {"at": "2026-10-30T19:25:00", "line": "2026-10-30 19:25:00 FINISH E05 rc=1 stopped", "status": "FAIL"}, "todo": [], "parked": {}})
    b = bs.build(tmp_path, NOW)
    assert b["episode"] == "E05" and b["machine"]["used_s"] == 3420 and b["tokens"]["used"] == 375030
    st = {r["stage"]: r["state"] for r in b["stages"]}
    assert st["script"] == "ok" and st["shots"] == "failed" and st["compose"] == "waiting" and "publish" not in st
    assert {h["file"] for h in b["heals"]} == {"read-heal.json", "refit.json"}
    assert any(a["kind"] == "STOPPED" and "SHOT-GATE" in a["text"] for a in b["alerts"])
    assert b["autopilot"]["next_tick"] == "2026-10-30T19:45" and not any(a["kind"] == "AUTOPILOT-SILENT" for a in b["alerts"])


def test_build_status_raises_a_red_alert_when_the_autopilot_stops_ticking(tmp_path):
    wj(tmp_path / "board" / "schedule.json", json.loads(sw_fixtures.SCHEDULE.read_text(encoding="utf-8")))
    wj(tmp_path / "work" / "daily" / "E05" / "STATE.json", {"stages": {}})
    wj(tmp_path / "work" / "daily" / "autopilot.json", {"last": {"at": "2026-10-30T18:30:00", "line": "x"}})
    b = bs.build(tmp_path, D(2026, 10, 30, 21, 0))
    assert any(a["kind"] == "AUTOPILOT-SILENT" and "register-autopilot.ps1" in a["text"] for a in b["alerts"])


def test_build_status_flags_publish_failed_even_when_the_episode_is_finished(tmp_path):
    wj(tmp_path / "work" / "daily" / "E05" / "STATE.json", {"stages": {"publish": {"status": "failed", "check": "PUBLISH-FAILED"}}})
    (tmp_path / "work" / "daily" / "E05" / "STOPPED.md").write_text("`FAIL [PUBLISH-FAILED]` instagram refused\n", encoding="utf-8")
    wj(tmp_path / "work" / "episodes" / "E05" / "gate" / "report.json", {"verdict": "PASS", "complete": True, "checks": [], "fails": []})
    wj(tmp_path / "work" / "episodes" / "E05" / "heal" / "critic.json", {"score": 9})
    (tmp_path / "work" / "episodes" / "E05" / "episode.mp4").write_bytes(b"\0")
    b = bs.build(tmp_path, dt.datetime.now())
    assert any(a["kind"] == "PUBLISH-FAILED" and "instagram refused" in a["text"] for a in b["alerts"])


def test_a_running_stage_with_no_live_run_is_shown_interrupted(tmp_path):
    wj(tmp_path / "work" / "daily" / "E05" / "STATE.json", {"stages": {"script": {"status": "ok"}, "voice": {"status": "running"}}})
    old = time.time() - 3600
    os.utime(tmp_path / "work" / "daily" / "E05" / "STATE.json", (old, old))
    rows = {r["stage"]: r for r in bs.stage_rows(tmp_path, "E05", dt.datetime.now())}
    assert rows["voice"]["state"] == "failed" and "interrupted" in rows["voice"]["note"]
    os.utime(tmp_path / "work" / "daily" / "E05" / "STATE.json", None)
    assert {r["stage"]: r for r in bs.stage_rows(tmp_path, "E05", dt.datetime.now())}["voice"]["state"] == "running"


def test_write_makes_json_and_js_and_never_raises(tmp_path, capsys):
    wj(tmp_path / "work" / "daily" / "E05" / "STATE.json", {"stages": {}})
    d = bs.write(tmp_path, NOW)
    out = tmp_path / "board" / "data"
    assert d and json.loads((out / "build.json").read_text(encoding="utf-8"))["episode"] == "E05" and (out / "build.js").read_text(encoding="utf-8").startswith("window.__BUILD__ = ")
    assert bs.write(tmp_path / "work" / "daily" / "E05" / "STATE.json" / "nope", NOW) is None          # a path that cannot be written: None, no exception


def test_next_tick_follows_the_schedule():
    task = {"from": "00:00", "every_min": 15}
    assert bs.next_tick(task, D(2026, 10, 30, 18, 31)) == D(2026, 10, 30, 18, 45)
    assert bs.next_tick(task, D(2026, 10, 30, 23, 50)) == D(2026, 10, 31, 0, 0)


def test_daily_writes_the_panel_at_every_stage_boundary(tmp_path):
    import daily
    from test_daily import ctx_for
    ctx = ctx_for(tmp_path)
    seen = []
    daily.run_stage(ctx, daily.Stage("votes", lambda c: seen.append(json.loads((tmp_path / "board" / "data" / "build.json").read_text(encoding="utf-8"))) or {}, lambda c: []))
    assert {r["stage"]: r["state"] for r in seen[0]["stages"]}["votes"] == "running"                  # written when the stage started
    after = json.loads((tmp_path / "board" / "data" / "build.json").read_text(encoding="utf-8"))
    assert {r["stage"]: r["state"] for r in after["stages"]}["votes"] == "ok"                          # and when it ended


def test_the_page_has_the_build_panel_and_the_red_banner():
    html = (REPO / "board" / "index.html").read_text(encoding="utf-8")
    for needle in ("function buildPanel", "function buildBanner", "data/build.json", "data/build.js", "redbanner", "role=\"alert\""):
        assert needle in html
    assert "buildBanner() +" in html and "Cairo" not in html
