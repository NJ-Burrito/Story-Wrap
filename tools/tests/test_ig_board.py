"""The Instagram board feed (tools/ig_board.py), the loop gate and the post slot (tools/loop_gate.py), the schedule file and the task script.
No network, no Task Scheduler, no model: every call that would reach Instagram is replaced."""
import datetime as dt
import json
import os
import re
import subprocess
from pathlib import Path

import pytest

import sw_fixtures
import ig
import ig_board as gb
import loop_gate as lg

REPO = Path(__file__).resolve().parents[2]
TOKEN = "IGAAsecretTOKEN123456789"
ENV = {"IG_USER_ID": "1784", "IG_ACCESS_TOKEN": TOKEN, "IG_USERNAME": "story_account", "IG_TOKEN_ISSUED": "2026-10-20T00:00:00"}
T0 = dt.datetime(2026, 11, 1, 12, 0)


def wj(p, d):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def finish(root, ep):
    w = root / "work" / "episodes" / ep
    wj(w / "gate" / "report.json", {"verdict": "PASS", "complete": True, "checks": [{"id": "a", "status": "pass"}], "fails": [], "warnings": []})
    wj(w / "heal" / "critic.json", {"score": 9, "verdict": "pass"})
    (w / "episode.mp4").write_bytes(b"\0" * 8)
    stamp = (T0 - dt.timedelta(hours=1)).timestamp()      # "finished" before T0, not at the real clock (ready_at reads file mtimes)
    for f in (w / "gate" / "report.json", w / "heal" / "critic.json", w / "episode.mp4"):
        os.utime(f, (stamp, stamp))


def post(root, ep, when):
    wj(root / "work" / "episodes" / ep / "post.json", {"episode": ep, "media_id": "m1", "permalink": f"https://instagram.com/reel/{ep}/", "posted_at": when.isoformat(), "username": "story_account"})


def harvest(root, ep, comments, own=("story_account",)):
    w = root / "work" / "episodes" / ep
    ch = [{"id": "1", "text_ar": "نفتح الحقيبة"}, {"id": "2", "text_ar": "نتركها مغلقة"}]
    wj(w / "comments.json", {"episode": ep, "count": len(comments), "own_usernames": list(own), "comments": comments})
    wj(w / "decision.json", {"episode": ep, "choices": ch, "counts": {"1": 3, "2": 1}, "counted": 4, "winner": None, "status": "SHOWRUNNER_LOW_VOTES",
                             "margin": 2, "ideas": [{"id": "c9", "username": "u9", "text": "اريد ان اشاهد المفتش يكتشف السر"}], "idea_count": 1, "excluded_own": 1})


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "repo"
    (r / "board").mkdir(parents=True)
    (r / "work" / "daily").mkdir(parents=True)
    (r / "board" / "schedule.json").write_text(sw_fixtures.SCHEDULE.read_text(encoding="utf-8"), encoding="utf-8")
    return r


# ------------------------------------------------------------------ the LOOP GATE
def test_first_episode_is_free(root):
    assert lg.check("E01", root, token=False)["allowed"] is True


def test_n_plus_1_waits_until_n_is_posted(root):
    finish(root, "E01")
    g = lg.check("E02", root, token=True)
    assert not g["allowed"] and g["code"] == "WAIT-POST" and g["waiting_for"] == "E01" and "ready to post" in g["why"]


def test_without_a_token_production_stops_at_one_finished_episode(root):
    finish(root, "E01")
    g = lg.check("E02", root, token=False)
    assert not g["allowed"] and "No Instagram token" in g["why"]
    assert lg.check("E03", root, token=False)["code"] == "WAIT-POST"       # never two ahead


def test_posted_but_not_harvested_waits_for_the_harvest(root):
    post(root, "E01", T0)
    g = lg.check("E02", root, token=True, at=T0 + dt.timedelta(hours=3))
    assert not g["allowed"] and g["code"] == "WAIT-HARVEST" and g["due"] == "2026-11-02T14:00" and "overdue" not in g["why"]
    assert "overdue" in lg.check("E02", root, token=True, at=T0 + dt.timedelta(hours=27))["why"]


def test_posted_and_harvested_opens_the_next_episode(root):
    post(root, "E01", T0)
    harvest(root, "E01", [])
    assert lg.check("E02", root, token=True)["allowed"]


def test_explicit_predecessor_for_a_suffixed_id(root):
    finish(root, "E01C")
    assert lg.check("E02", root, token=False, prev="E01C")["code"] == "WAIT-POST"


def test_pick_episode_resumes_an_unposted_started_episode(root):
    nxt = lambda r: "E09"                                                          # noqa: E731
    assert lg.pick_episode(root, nxt) == "E09"
    wj(root / "work" / "daily" / "E02" / "STATE.json", {"stages": {}})
    assert lg.pick_episode(root, nxt) == "E02"
    post(root, "E02", T0)
    assert lg.pick_episode(root, nxt) == "E09"


def test_daily_run_waits_cleanly_and_runs_nothing(root, monkeypatch, capsys):
    import daily
    monkeypatch.setattr(daily, "ROOT", root)
    monkeypatch.setattr(lg, "ROOT", root)
    monkeypatch.setattr(lg, "has_token", lambda *a, **k: False)
    finish(root, "E01")
    wj(root / "work" / "daily" / "E02" / "STATE.json", {"stages": {}})             # E02 was started earlier and is unposted
    monkeypatch.setattr(daily, "Ctx", lambda *a, **k: pytest.fail("a waiting run must not build a context"))
    assert daily.main(["run", "--ep", "E02"]) == 0
    assert "WAIT [WAIT-POST]" in capsys.readouterr().out
    assert json.loads((root / "work" / "daily" / "tasks" / "StoryWrap-Daily.json").read_text(encoding="utf-8"))["status"] == "WAIT"


def test_post_task_without_token_exits_cleanly_with_a_status(root, monkeypatch, capsys):
    import daily
    monkeypatch.setattr(daily, "ROOT", root)
    monkeypatch.setattr(lg, "has_token", lambda *a, **k: False)
    monkeypatch.setattr(lg, "has_fb_token", lambda *a, **k: False)
    finish(root, "E01")
    assert daily.main(["post", "--latest", "--due", "--go"]) == 0
    assert "NO-TOKEN" in capsys.readouterr().out
    assert json.loads((root / "work" / "daily" / "tasks" / "StoryWrap-Post.json").read_text(encoding="utf-8"))["status"] == "NO-TOKEN"


# ------------------------------------------------------------------ the post slot
def test_slot_is_fixed_1900_on_every_platform():
    """the owner, 2026-10-27: 19:00 on every platform (was 19:30 Instagram, 20:30 Facebook, DESIGN 6.2)."""
    for d in range(60):
        day = dt.date(2026, 11, 1) + dt.timedelta(days=d)
        assert lg.post_slot("E02", day) == dt.datetime.combine(day, dt.time(19, 0)) == lg.post_slot("E77", day)
        assert lg.fb_slot("E02", day) == dt.datetime.combine(day, dt.time(19, 0))


def test_post_due_waits_for_the_slot_then_goes_and_keeps_20_hours_apart(root):
    finish(root, "E02")
    slot = lg.post_slot("E02", T0.date())
    assert lg.post_due("E02", slot - dt.timedelta(minutes=1), root)["code"] == "WAIT-SLOT"
    assert lg.post_due("E02", slot + dt.timedelta(minutes=2), root)["due"] is True
    post(root, "E01", slot - dt.timedelta(hours=19))
    assert lg.post_due("E02", slot + dt.timedelta(minutes=2), root)["code"] == "WAIT-GAP"
    post(root, "E02", slot)
    assert lg.post_due("E02", slot + dt.timedelta(hours=1), root)["code"] == "ALREADY"


# ------------------------------------------------------------------ the feed
def test_empty_root_builds_a_valid_board_without_a_token(root):
    d = gb.build_all(root, T0, env={})
    assert d["token"] is False and d["posts"] == [] and d["comments"] == []
    assert d["health"]["token"]["state"] == "missing" and d["schedule"]["next_post"]["episode"] is None
    json.dumps(d)


def test_today_shows_stages_gate_critic_and_the_loop(root):
    finish(root, "E01")
    wj(root / "work" / "daily" / "E01" / "STATE.json", {"started": "x", "stages": {"script": {"status": "ok", "seconds": 61.5}, "voice": {"status": "failed", "check": "CHILD", "message": "boom", "seconds": 3}}})
    wj(root / "work" / "daily" / "E01" / "deadline.json", {"cap_s": 14400, "machine_s": 7200})
    t = gb.build_all(root, T0, env={})["today"]
    assert t["episode"] == "E01" and t["gate"]["verdict"] == "PASS" and t["critic"]["score"] == 9 and t["machine_s"] == 7200
    assert {s["stage"]: s["status"] for s in t["stages"]}["voice"] == "failed" and {s["stage"]: s["status"] for s in t["stages"]}["critic"] == "pending"
    assert t["loop"]["episode"] == "E02" and t["loop"]["code"] == "WAIT-POST"


def sch_autopilot():
    return json.loads(sw_fixtures.SCHEDULE.read_text(encoding="utf-8"))["tasks"]["StoryWrap-Autopilot"]


def test_schedule_names_next_post_slot_and_flags_the_missing_token(root):
    finish(root, "E01")
    s = gb.build_all(root, T0, env={})["schedule"]
    assert s["next_post"]["episode"] == "E01" and s["next_post"]["blocked"] and "token" in s["next_post"]["blocked"]
    assert re.fullmatch(r"2026-11-0[12]T(1[7-9]|20):\d\d", s["next_post"]["slot"])
    names = [t["task"] for t in s["tasks"]]
    assert names == ["StoryWrap-Autopilot", "StoryWrap-Post", "StoryWrap-Harvest", "StoryWrap-Board", "StoryWrap-Health"]
    assert gb.next_tick(sch_autopilot(), T0).isoformat(timespec="minutes") == s["tasks"][0]["next"] and s["tasks"][0]["next"] <= "2026-11-01T12:15"      # ticks every 15 min all day (R-505)
    ok = gb.build_all(root, T0, env=ENV)["schedule"]["next_post"]
    assert ok["blocked"] is None


def test_posts_and_comments_tab_count_votes_ideas_and_draft_replies(root):
    post(root, "E01", T0 - dt.timedelta(hours=13))
    harvest(root, "E01", [
        {"id": "c1", "parent_id": None, "text": "نفتح الحقيبة", "username": "a", "timestamp": "t"},
        {"id": "c2", "parent_id": None, "text": "اريد ان اشاهد المفتش يكتشف السر الكبير", "username": "b", "timestamp": "t"},
        {"id": "c3", "parent_id": None, "text": "حلقة جميلة", "username": "c", "timestamp": "t"},
        {"id": "c4", "parent_id": None, "text": "رأيكم؟", "username": "story_account", "timestamp": "t"},
        {"id": "c5", "parent_id": None, "text": "نتركها مغلقة", "username": "d", "timestamp": "t"},
        {"id": "r5", "parent_id": "c5", "text": "شكرا", "username": "story_account", "timestamp": "t"}])
    wj(root / "work" / "episodes" / "E01" / "calm-plan.json", {})
    wj(root / "work" / "episodes" / "E01" / "metrics.json", {"likes": 12, "comments": 6, "fetched_at": "2026-11-01T11:00:00"})
    d = gb.build_all(root, T0, env=ENV)
    p = d["posts"][0]
    assert p["likes"] == 12 and p["harvested"] and p["vote"]["counts"] == {"1": 3, "2": 1}
    kinds = {c["id"]: c["kind"] for c in d["comments"]}
    assert kinds["c1"] == "vote" and kinds["c2"] == "idea" and kinds["c3"] == "chat" and kinds["c4"] == "own"
    drafts = {r["id"]: r for r in d["replies"]["items"]}
    assert set(drafts) == {"c1", "c2", "c3"}                                       # c4 is ours, c5 already has our reply
    assert "نفتح الحقيبة" in drafts["c1"]["text"] and all(r["status"] == "draft" for r in drafts.values())
    assert not any(ig.has_tashkeel(r["text"]) for r in drafts.values())
    assert d["tallies"][0]["ideas"][0]["username"] == "u9"


def test_decisions_survive_a_rebuild_and_text_edits_are_checked(root):
    post(root, "E01", T0 - dt.timedelta(hours=13))
    harvest(root, "E01", [{"id": "c3", "parent_id": None, "text": "حلقة جميلة", "username": "c", "timestamp": "t"}])
    gb.write_all(root, T0, env=ENV)
    gb.decide(root, "c3", "approve", "شكرا لك 🙏")
    d = gb.write_all(root, T0, env=ENV)
    assert d["replies"]["items"][0]["status"] == "approved" and d["replies"]["items"][0]["text"] == "شكرا لك 🙏"
    assert gb.decide(root, "c3", "approve", "شُكراً")["text"] == "شكرا"              # tashkeel is stripped, never stored
    with pytest.raises(ValueError):
        gb.decide(root, "c3", "approve", "   ")
    with pytest.raises(KeyError):
        gb.decide(root, "nope", "reject")


def test_board_files_hold_no_credential(root):
    post(root, "E01", T0 - dt.timedelta(hours=13))
    harvest(root, "E01", [{"id": "c3", "parent_id": None, "text": "حلقة جميلة", "username": "c", "timestamp": "t"}])
    gb.write_all(root, T0, env=ENV)
    for f in (root / "board" / "data").glob("*"):
        assert TOKEN not in f.read_text(encoding="utf-8"), f.name
    h = gb.build_all(root, T0, env=ENV)["health"]["token"]
    assert h == {"state": "ok", "present": True, "days_left": 49, "note": "present"} or h["present"] is True
    with pytest.raises(SystemExit, match="IGB-LEAK"):
        stop = root / "work" / "daily" / "E05" / "STOPPED.md"      # an unposted, unfinished episode: its stop is shown (a posted one's is history)
        wj(root / "work" / "daily" / "E05" / "STATE.json", {"stages": {}})
        stop.write_text("leaked " + TOKEN, encoding="utf-8")
        os.utime(stop, (T0.timestamp(), T0.timestamp()))
        # redact_log only strips access_token=/Bearer forms; a bare value must still be caught by the output check
        gb.write_all(root, T0, env=ENV)


# ------------------------------------------------------------------ replies, limits, harvest
def test_replies_post_only_approved_within_the_daily_and_run_limits(root):
    items = [{"id": f"c{i}", "episode": "E01", "username": "u", "comment": "x", "kind": "chat", "text": "شكرا", "status": "approved", "created": "t"} for i in range(6)]
    wj(root / "board" / "data" / "replies.json", {"replies": items + [{"id": "d1", "episode": "E01", "username": "u", "comment": "x", "kind": "vote", "text": "ok", "status": "draft", "created": "t"}]})
    sent = []
    fake = lambda cid, text, go: sent.append(cid) or {"reply_id": "r" + cid}         # noqa: E731
    r = gb.post_replies(root, go=True, at=T0, do_reply=fake, token=True)
    assert r["sent"] == 3 and sent == ["c0", "c1", "c2"]                              # per-run limit 3; the draft is not sent (auto_reply is off)
    wj(root / "board" / "config.json", {"max_replies_per_day": 4})
    sent.clear()
    assert gb.post_replies(root, go=True, at=T0, do_reply=fake, token=True)["sent"] == 1   # 4 a day minus 3 already sent today
    assert gb.post_replies(root, go=True, at=T0, do_reply=fake, token=True)["sent"] == 0


def test_auto_reply_sends_only_the_allowed_kinds(root):
    wj(root / "board" / "config.json", {"auto_reply": True, "auto_kinds": ["vote"]})
    mk = lambda i, k: {"id": i, "episode": "E01", "username": "u", "comment": "x", "kind": k, "text": "ok", "status": "draft", "created": "t"}   # noqa: E731
    wj(root / "board" / "data" / "replies.json", {"replies": [mk("a", "vote"), mk("b", "chat"), mk("c", "idea")]})
    sent = []
    gb.post_replies(root, go=True, at=T0, do_reply=lambda cid, t, g: sent.append(cid) or {}, token=True)
    assert sent == ["a"]


def test_dry_run_and_no_token_send_nothing(root):
    wj(root / "board" / "data" / "replies.json", {"replies": [{"id": "a", "episode": "E01", "username": "u", "comment": "x", "kind": "vote", "text": "ok", "status": "approved", "created": "t"}]})
    sent = []
    r = gb.post_replies(root, go=False, at=T0, do_reply=lambda cid, t, g: sent.append(g) or {}, token=True)
    assert r["dry"] == ["a"] and sent == [False]
    assert gb.post_replies(root, go=True, at=T0, do_reply=lambda *a: pytest.fail("no token"), token=False)["status"] == "NO-TOKEN"


def test_ig_reply_dry_run_needs_no_credentials_and_refuses_tashkeel(capsys):
    assert ig.cmd_reply("1789", "شكرا لك", go=False)["mode"] == "DRY RUN"
    assert "DRY RUN" in capsys.readouterr().out
    assert ig.cmd_reply("1789", "شُكراً", go=False)["text"] == "شكرا"              # display_text strips it before anything is sent
    with pytest.raises(SystemExit, match="IG-REPLY-ID"):
        ig.cmd_reply("12/../x", "ok")


def test_harvest_without_token_is_a_clean_no_token(root):
    post(root, "E01", T0 - dt.timedelta(days=2))
    r = gb.harvest_due(root, go=True, at=T0, token=False, do_comments=lambda e: pytest.fail("no token"))
    assert r["status"] == "NO-TOKEN" and "E01 waiting" in r["detail"]
    assert json.loads((root / "work" / "daily" / "tasks" / "StoryWrap-Harvest.json").read_text(encoding="utf-8"))["status"] == "NO-TOKEN"


def test_harvest_waits_for_14_00_the_next_day_then_runs_the_three_steps_in_order(root):
    post(root, "E01", T0 - dt.timedelta(hours=20))          # posted 2026-10-31 16:00: due 2026-11-01 14:00
    calls = []
    kw = dict(token=True, do_comments=lambda e: calls.append(("comments", e)), do_tally=lambda e: calls.append(("tally", e)), do_next=lambda e: calls.append(("next", e)))
    assert gb.harvest_due(root, go=True, at=T0, **kw)["status"] == "IDLE" and calls == []
    r = gb.harvest_due(root, go=True, at=T0 + dt.timedelta(hours=2, minutes=1), **kw)
    assert r["status"] == "OK" and calls == [("comments", "E01"), ("tally", "E01"), ("next", "E01")]


def test_harvest_failure_is_reported_not_raised(root):
    post(root, "E01", T0 - dt.timedelta(days=2))
    def boom(e):
        raise SystemExit("FAIL [IG-HTTP] 400")
    r = gb.harvest_due(root, go=True, at=T0, token=True, do_comments=boom, do_tally=boom, do_next=boom)
    assert r["status"] == "FAIL" and "IG-HTTP" in r["detail"]


def test_dry_harvest_changes_nothing(root):
    post(root, "E01", T0 - dt.timedelta(days=2))
    r = gb.harvest_due(root, go=False, at=T0, token=True, do_comments=lambda e: pytest.fail("dry"))
    assert r["harvested"] == ["E01 (dry)"]


# ------------------------------------------------------------------ health
def test_health_alerts(root):
    wj(root / "work" / "daily" / f"budget-{T0.date().isoformat()}.json", {"tokens": 300000, "limit": 250000, "calls": []})
    lg.write_task_status(root, "StoryWrap-Post", "FAIL", "gate red", T0)
    env = {**ENV, "IG_TOKEN_ISSUED": "2026-09-01T00:00:00"}
    h = gb.health_block(root, T0, env, tasks={"StoryWrap-Board": {"registered": False}})
    text = " | ".join(h["alerts"])
    assert "refresh" in text and "budget" in text and "StoryWrap-Post failed" in text and "StoryWrap-Board is not registered" in text
    assert not any("token has" in a for a in gb.health_block(root, T0, {}, tasks=None)["alerts"])


HENV = {**ENV, "FB_PAGE_ID": "1", "FB_PAGE_TOKEN": "x"}      # Facebook configured, so the only alerts are the ones a test creates


def _capped_episode(root, ep="E01C"):
    wj(root / "work" / "daily" / ep / "STATE.json", {"stages": {}})
    wj(root / "work" / "daily" / ep / "deadline.json", {"machine_s": 15000, "cap_s": 14400})


def test_health_never_quotes_its_own_previous_status(root):
    lg.write_task_status(root, "StoryWrap-Health", "FAIL", "StoryWrap-Health failed at X: old alert", T0)
    lg.write_task_status(root, "StoryWrap-Post", "FAIL", "gate red", T0)
    al = gb.health_block(root, T0, HENV, tasks=None)["alerts"]
    assert not any("StoryWrap-Health" in a for a in al) and any("StoryWrap-Post failed" in a for a in al)


def test_token_budget_is_today_amman_only(root):
    wj(root / "work" / "daily" / "budget-2026-10-25.json", {"tokens": 300000, "limit": 250000, "calls": []})
    # 2026-10-25 22:00 UTC is 01:00 on the 26th in Amman: yesterday's file must not alert
    at = dt.datetime(2026, 10, 25, 22, 0, tzinfo=dt.timezone.utc)
    h = gb.health_block(root, at, HENV, tasks=None)
    assert not any("budget" in a for a in h["alerts"]) and h["tokens_today"]["used"] == 0
    # 2026-10-25 20:00 UTC is 23:00 on the 25th in Amman: still the same day, so it alerts
    at = dt.datetime(2026, 10, 25, 20, 0, tzinfo=dt.timezone.utc)
    assert any("budget" in a for a in gb.health_block(root, at, HENV, tasks=None)["alerts"])
    # a naive clock is local (Amman) time
    assert any("budget" in a for a in gb.health_block(root, dt.datetime(2026, 10, 25, 23, 59), HENV, tasks=None)["alerts"])
    assert not any("budget" in a for a in gb.health_block(root, dt.datetime(2026, 10, 26, 0, 1), HENV, tasks=None)["alerts"])


def test_render_cap_alert_skips_an_adopted_episode(root, monkeypatch):
    _capped_episode(root)
    monkeypatch.setattr(gb, "adoption", lambda root, ep: None)
    assert any("render cap" in a for a in gb.health_block(root, T0, HENV, tasks=None)["alerts"])
    monkeypatch.setattr(gb, "adoption", lambda root, ep: {"approved_by": "the owner", "adopted_at": "2026-10-25T10:00:00"})
    assert not any("render cap" in a for a in gb.health_block(root, T0, HENV, tasks=None)["alerts"])


def test_health_with_only_stale_alerts_reports_ok(root, monkeypatch, capsys):
    _capped_episode(root)
    monkeypatch.setattr(gb, "adoption", lambda root, ep: {"approved_by": "the owner", "adopted_at": "2026-10-25T10:00:00"})
    wj(root / "work" / "daily" / "budget-2026-10-25.json", {"tokens": 300000, "limit": 250000, "calls": []})
    lg.write_task_status(root, "StoryWrap-Health", "FAIL", "old: today's budget is spent; E01C used the whole 4 h render cap", dt.datetime(2026, 10, 25, 21, 20))
    monkeypatch.setattr(gb, "ROOT", root)
    monkeypatch.setattr(gb, "query_tasks", lambda: None)
    monkeypatch.setattr(gb, "env_values", lambda path=None: dict(HENV))
    monkeypatch.setattr(gb, "write_all", lambda r, tasks=None: {"health": gb.health_block(r, dt.datetime(2026, 10, 26, 3, 20), HENV, tasks=None)})
    assert gb.main(["health"]) == 0
    assert "all clear" in capsys.readouterr().out
    assert lg.read_task_statuses(root)["StoryWrap-Health"]["status"] == "OK"


def test_render_cap_alert_skips_a_posted_or_finished_episode(root):
    _capped_episode(root)
    assert any("render cap" in a for a in gb.health_block(root, T0, HENV, tasks=None)["alerts"])
    finish(root, "E01C")
    assert not any("render cap" in a for a in gb.health_block(root, T0, HENV, tasks=None)["alerts"])


def test_recent_stops_skip_closed_and_old_episodes(root):
    old, new = root / "work" / "daily" / "E03" / "STOPPED.md", root / "work" / "daily" / "E04" / "STOPPED.md"
    done = root / "work" / "daily" / "E05" / "STOPPED.md"
    for f in (old, new, done):
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("stopped", encoding="utf-8")
    os.utime(old, ((T0 - dt.timedelta(hours=60)).timestamp(),) * 2)
    os.utime(new, ((T0 - dt.timedelta(hours=2)).timestamp(),) * 2)
    os.utime(done, ((T0 - dt.timedelta(hours=2)).timestamp(),) * 2)
    finish(root, "E05")
    assert [f["episode"] for f in gb.health_block(root, T0, HENV, tasks=None)["failures"]] == ["E04"]


def test_today_hides_the_stop_of_an_adopted_episode_and_overlays_its_stages(root, monkeypatch):
    wj(root / "work" / "daily" / "E01C" / "STATE.json", {"stages": {"voice": {"status": "failed", "message": "old"}, "critic": {"status": "failed"}}})
    (root / "work" / "daily" / "E01C" / "STOPPED.md").write_text("# stopped", encoding="utf-8")
    t = gb.today_block(root, T0, False)
    assert t["state"] == "stopped" and t["stopped"]
    monkeypatch.setattr(gb, "adoption", lambda r, ep: {"approved_by": "the owner", "adopted_at": "2026-10-25T10:00:00"})
    t = gb.today_block(root, T0, False)
    rows = {r["stage"]: r for r in t["stages"]}
    assert t["state"] == "adopted" and t["stopped"] is None and t["adopted"]["text"] == "adopted by the owner 2026-10-25"
    assert rows["voice"]["status"] == "ok" and rows["voice"]["message"] == "adopted by the owner 2026-10-25" and rows["publish"]["status"] == "pending"


def test_stale_task_status_is_dimmed_never_an_alert(root):
    lg.write_task_status(root, "StoryWrap-Post", "FAIL", "old gate red", T0 - dt.timedelta(days=3))
    h = gb.health_block(root, T0, HENV, tasks=None)
    assert not h["alerts"] and h["task_status"]["StoryWrap-Post"]["stale"] is True
    lg.write_task_status(root, "StoryWrap-Post", "FAIL", "fresh gate red", T0 - dt.timedelta(hours=1))
    assert any("StoryWrap-Post failed" in a for a in gb.health_block(root, T0, HENV, tasks=None)["alerts"])


def test_board_or_harvest_silent_for_three_intervals_is_an_alert(root):
    (root / "board" / "schedule.json").write_text(json.dumps({"tasks": {"StoryWrap-Board": {"kind": "repeat", "every_min": 15}, "StoryWrap-Harvest": {"kind": "repeat", "every_min": 60}}}), encoding="utf-8")
    lg.write_task_status(root, "StoryWrap-Board", "OK", "x", T0 - dt.timedelta(minutes=50))
    lg.write_task_status(root, "StoryWrap-Harvest", "OK", "x", T0 - dt.timedelta(minutes=170))
    al = gb.health_block(root, T0, HENV, tasks=None)["alerts"]
    assert len(al) == 1 and "StoryWrap-Board said nothing" in al[0]
    lg.write_task_status(root, "StoryWrap-Board", "OK", "x", T0 - dt.timedelta(minutes=10))
    assert gb.health_block(root, T0, HENV, tasks=None)["alerts"] == []


def test_scheduler_column_carries_its_age(root):
    h = gb.build_all(root, T0, env=HENV, tasks={"StoryWrap-Board": {"registered": True, "ok": True}})["health"]
    assert h["scheduler_at"] == "2026-11-01T12:00"
    wj(root / "board" / "data" / "health.json", h)
    again = gb.build_all(root, T0 + dt.timedelta(hours=1), env=HENV)["health"]       # reused: keeps the time it was really asked
    assert again["scheduler_at"] == "2026-11-01T12:00" and again["scheduler"] == h["scheduler"]


def test_posted_times_show_in_amman_time(root):
    post(root, "E01", dt.datetime(2026, 10, 25, 16, 30, tzinfo=dt.timezone.utc))
    wj(root / "work" / "episodes" / "E01" / "youtube.json", {"video_id": "v", "state": "done", "posted_at": "2026-10-25T16:30:00+00:00"})
    wj(root / "work" / "episodes" / "E01" / "stories.json", {"items": {"vote:instagram": {"state": "done", "at": "2026-10-25T16:40:00+00:00"}}})
    row = gb.posts_block(root)[0]
    expect = lg.parse_time("2026-10-25T16:30:00+00:00").isoformat(timespec="minutes")
    assert row["posted_at"] == expect == row["youtube"]["posted_at"]
    assert row["stories"][0]["at"] == lg.parse_time("2026-10-25T16:40:00+00:00").isoformat(timespec="minutes")


def test_loop_gate_continues_from_the_last_posted_or_adopted_episode(root):
    # E01 was never posted; E01C (the calm cut) was
    assert lg.prev_ep("E02C") == "E01" and lg.prev_ep("E01C") is None
    assert lg.check("E02", root, token=True)["waiting_for"] == "E01"
    wj(root / "work" / "episodes" / "E01C" / "adopted.json", {"episode": "E01C"})
    r = lg.check("E02", root, token=True)
    assert r["code"] == "WAIT-POST" and r["waiting_for"] == "E01C"
    post(root, "E01C", T0 - dt.timedelta(hours=30))
    assert lg.check("E02", root, token=True, at=T0)["code"] == "WAIT-HARVEST"
    wj(root / "work" / "episodes" / "E01C" / "decision.json", {"status": "ok"})
    assert lg.check("E02", root, token=True, at=T0)["allowed"] is True
    import daily
    assert daily.prev_ep("E02", root) == "E01C" and daily.prev_ep("E02") == "E01"
    assert daily.next_episode(root) == "E02"


def test_pick_episode_never_resumes_an_adopted_episode(root):
    wj(root / "work" / "daily" / "E01C" / "STATE.json", {"stages": {}})
    assert lg.pick_episode(root, lambda r: "E02") == "E01C"
    wj(root / "work" / "episodes" / "E01C" / "adopted.json", {"episode": "E01C"})
    assert lg.pick_episode(root, lambda r: "E02") == "E02"


def test_health_task_writes_ok_with_a_count_and_dry_post_ticks_say_nothing(root, monkeypatch):
    monkeypatch.setattr(gb, "ROOT", root)
    monkeypatch.setattr(gb, "query_tasks", lambda: None)
    monkeypatch.setattr(gb, "write_all", lambda r, tasks=None: {"health": {"alerts": ["a", "b"]}})
    assert gb.main(["health"]) == 0
    st = lg.read_task_statuses(root)["StoryWrap-Health"]
    assert st["status"] == "OK" and st["detail"] == "2 alert(s)"
    import daily
    monkeypatch.setattr(daily, "ROOT", root)
    monkeypatch.setattr(lg, "has_token", lambda *a, **k: False)
    monkeypatch.setattr(lg, "has_fb_token", lambda *a, **k: False)
    wj(root / "work" / "episodes" / "E02" / "heal" / "critic.json", {"score": 9})
    assert daily.main(["post", "E02", "--due"]) == 0
    assert "StoryWrap-Post" not in lg.read_task_statuses(root)


def test_a_clean_run_settles_the_stop_note(root):
    import daily
    ctx = type("C", (), {"dir": root / "work" / "daily" / "E09"})()
    ctx.dir.mkdir(parents=True)
    (ctx.dir / "STOPPED.md").write_text("x", encoding="utf-8")
    assert daily.run_list(ctx, []) == 0
    assert not (ctx.dir / "STOPPED.md").exists() and (ctx.dir / "STOPPED.resolved.md").exists()


def test_page_pill_classes_match_the_css():
    html = (REPO / "board" / "index.html").read_text(encoding="utf-8")
    assert ".toLowerCase()" in html.split("const pill")[1][:200]
    for cls in ("partial", "idle", "no-token", "stale"):
        assert f".pill.{cls}" in html
    assert "not run yet" in html and "267011" in html


# ------------------------------------------------------------------ the schedule file, the task script, the page
def test_schedule_ticks():
    sch = json.loads(sw_fixtures.SCHEDULE.read_text(encoding="utf-8"))["tasks"]
    assert [t.strftime("%H:%M") for t in gb.ticks_of(sch["StoryWrap-Post"], dt.date(2026, 11, 1))] == ["19:00", "19:05", "19:10", "19:15", "19:20", "19:25", "19:30", "19:35", "19:40", "19:45", "19:50", "19:55", "20:00", "20:05", "20:10", "20:15", "20:20", "20:25"]
    assert len(gb.ticks_of(sch["StoryWrap-Harvest"], dt.date(2026, 11, 1))) == 24
    assert gb.ticks_of(sch["StoryWrap-Harvest"], dt.date(2026, 11, 1))[0].minute == 35


def harvest_ticks_of(sch, day):
    return gb.ticks_of(sch["StoryWrap-Harvest"], day)


def test_schedule_keeps_the_loop_in_step():
    """the owner, 2026-10-27: post 19:00, harvest 14:00 the next day, the autopilot starts at 14:00 (after the harvest it runs itself) and never posts."""
    sch = json.loads(sw_fixtures.SCHEDULE.read_text(encoding="utf-8"))["tasks"]
    day = dt.date(2026, 11, 1)
    last_post = max(gb.ticks_of(sch["StoryWrap-Post"], day))
    latest_slot = max(lg.post_slot("E02", day + dt.timedelta(days=i)) for i in range(60))
    assert latest_slot.time() <= last_post.time() and last_post.time() < lg.POST_CUTOFF                 # the slot (19:00) has retry ticks after it, none past the cutoff
    harvest_due = dt.datetime.combine(day + dt.timedelta(days=1), dt.time(14, 0))                          # the later post of day D is at 19:00: the harvest is 14:00 on D+1
    auto = gb.ticks_of(sch["StoryWrap-Autopilot"], day + dt.timedelta(days=1))
    assert harvest_due in auto and auto[-1].time() == dt.time(23, 45) and len(auto) == 96             # R-505: ticks all day; the 14:00 harvest rule is decided in autopilot.decide
    harvest_ticks = gb.ticks_of(sch["StoryWrap-Harvest"], day + dt.timedelta(days=1))
    assert min(t for t in harvest_ticks if t >= harvest_due).strftime("%H:%M") == "14:35"                     # the hourly safety net follows the autopilot
    for t in sch.values():
        assert t["cmd"].startswith("uv run tools/") and t["limit_h"] > 0


def test_register_script_matches_the_schedule_and_registers_nothing_in_dry_run():
    ps = REPO / "tools" / "register-tasks.ps1"
    src = ps.read_text(encoding="utf-8")
    assert "board\\schedule.json" in src and "-DryRun" in src and "StoryWrap-BoardServer" in src
    exe = subprocess.run(["where", "powershell"], capture_output=True, text=True).stdout.split("\n")[0].strip() if hasattr(subprocess, "run") else None
    if not exe:
        pytest.skip("no powershell")
    r = subprocess.run([exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps), "-DryRun"], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    sch = json.loads(sw_fixtures.SCHEDULE.read_text(encoding="utf-8"))["tasks"]
    mine = {n: t for n, t in sch.items() if not t.get("registered_by")}          # the autopilot has its own script (tools/register-autopilot.ps1)
    for name, t in mine.items():
        assert f"[dry run] {name}:" in r.stdout
        assert t["cmd"].replace("uv run ", "") in r.stdout.replace("\r", "")
    assert r.stdout.count("[dry run]") == len(mine) and "[skip] StoryWrap-Autopilot" in r.stdout


def test_page_has_five_tabs_thmanyah_and_no_other_font():
    html = (REPO / "board" / "index.html").read_text(encoding="utf-8")
    for tab in ("Today", "📸 Instagram", "📘 Facebook", "▶️ YouTube", "Schedule", "Health"):      # Posts and Comments moved into the platform tabs (2026-10-26)
        assert f'"{tab}"' in html
    assert "Thmanyah Sans" in html and "Thmanyah Serif Display" in html and "Cairo" not in html
    assert "innerHTML" in html and html.count("esc(") > 40                              # comment text is escaped before it reaches the page
    assert (REPO / "board" / "serve.py").is_file()


def test_server_binds_locally_and_needs_a_token_for_posts():
    src = (REPO / "board" / "serve.py").read_text(encoding="utf-8")
    assert '("127.0.0.1", PORT)' in src and "X-Board-Token" in src and "403" in src


def test_sweep_media_reports_and_never_raises():
    assert "2 stale" in gb.sweep_media(lambda: ["ig-tmp-a", "ig-tmp-b"])
    assert "0 stale" in gb.sweep_media(lambda: [])

    def boom():
        raise SystemExit("FAIL [MH-GH] no login")
    assert gb.sweep_media(boom).startswith("media sweep skipped")
