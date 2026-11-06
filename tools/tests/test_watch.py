"""tools/watch.py: change detection, no tick when nothing changed, the lock, backoff, quiet hours, follow-up. No network, no engage."""
import json
import random
from datetime import datetime, timedelta, timezone

import watch

T0 = datetime(2026, 10, 27, 12, 0, 0, tzinfo=timezone.utc)      # 15:00 Amman


class Clock:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t

    def adv(self, s):
        self.t += timedelta(seconds=s)


def make(tmp_path, sigs, clock=None, quiet=False, due=None, tick=None, **kw):
    """sigs: {platform: list of signature dicts returned in turn (the last repeats)}"""
    clock = clock or Clock()
    calls = {"ticks": 0, "fetch": {p: 0 for p in sigs}}

    def fetcher(pf):
        def f(ctx):
            seq = sigs[pf]
            i = min(calls["fetch"][pf], len(seq) - 1)
            calls["fetch"][pf] += 1
            v = seq[i]
            if isinstance(v, Exception):
                raise v
            return v
        return f

    def default_tick():
        calls["ticks"] += 1
        return {"rc": 0, "sent": 1, "new_items": 1}

    w = watch.Watcher(tmp_path, fetchers={p: fetcher(p) for p in sigs}, tick=tick or default_tick, now_fn=clock, sleep=lambda s: None, env={},
                      rng=random.Random(1), windows_fn=lambda n: {}, quiet_fn=lambda t: quiet, due_fn=lambda after: due, **kw)
    return w, clock, calls


def test_changed_rules():
    assert watch.changed(None, {"c:1": 5}) is False                    # first look = baseline
    assert watch.changed({"c:1": 5}, {"c:1": 5}) is False
    assert watch.changed({"c:1": 5}, {"c:1": 6}) is True
    assert watch.changed({"c:1": 5}, {"c:1": 4}) is True              # a deleted comment is also a change
    assert watch.changed({"c:1": 5}, {"c:2": 0}) is False             # a new, empty reel is not a notification
    assert watch.changed({"c:1": 5}, {"c:2": 3}) is True
    assert watch.changed({"dm": ["a"]}, {"dm": ["b"]}) is True
    assert watch.changed({"c:1": 5, "dm": ["a"]}, {"c:1": 5}) is False  # a part that failed this time is simply absent


def test_baseline_then_no_tick_when_unchanged(tmp_path):
    w, clock, calls = make(tmp_path, {"instagram": [{"c:1": 2}]})
    r = w.step()
    assert r["polled"] == ["instagram"] and not r["changed"] and not r["ticked"]
    clock.adv(61)
    r = w.step()
    assert r["polled"] == ["instagram"] and not r["changed"] and calls["ticks"] == 0
    assert "baseline" in (tmp_path / "work/engage/watch.log").read_text(encoding="utf-8")


def test_poll_waits_for_the_interval(tmp_path):
    w, clock, calls = make(tmp_path, {"instagram": [{"c:1": 2}], "youtube": [{"v:1": []}]})
    w.step()
    clock.adv(30)
    assert w.step()["polled"] == []                                   # nothing is due 30 s later
    clock.adv(60)
    assert w.step()["polled"] == ["instagram"]                        # 90 s: Instagram (60 +- 15) is due, YouTube (150 +- 15) is not
    clock.adv(80)
    assert sorted(w.step()["polled"]) == ["instagram", "youtube"]


def test_change_runs_one_tick_and_rebaselines(tmp_path):
    w, clock, calls = make(tmp_path, {"instagram": [{"c:1": 2}, {"c:1": 3}]})
    w.step()                                                           # baseline c:1=2
    clock.adv(61)
    r = w.step()                                                       # sees 3 -> changed -> tick
    assert r["changed"] == ["instagram"] and r["ticked"] and calls["ticks"] == 1
    assert w.state["sigs"]["instagram"] == {"c:1": 3}                  # re-baselined after the tick
    clock.adv(61)
    assert w.step()["ticked"] is False and calls["ticks"] == 1         # our own reply did not trigger another tick
    log = (tmp_path / "work/engage/watch.log").read_text(encoding="utf-8")
    assert "CHANGE c:1" in log and "tick: start (instagram)" in log
    assert len(log.splitlines()[0].split(" ")[0]) == 8                 # HH:MM:SS


def test_min_gap_between_ticks_keeps_the_request(tmp_path):
    w, clock, calls = make(tmp_path, {"instagram": [{"c:1": 1}, {"c:1": 2}, {"c:1": 3}]}, intervals={"instagram": 20})
    w.step()
    clock.adv(21)
    assert w.step()["ticked"]                                          # first tick at +21 s
    w.state["sigs"]["instagram"] = {"c:1": 0}                          # force another change at once
    clock.adv(36)                                                      # past the 20 +- 15 s interval, still under 60 s since the tick
    r = w.step()
    assert r["changed"] and not r["ticked"] and "instagram" in w.pending     # < 60 s since the last tick: asked, not run
    clock.adv(30)
    assert w.step()["ticked"] and calls["ticks"] == 2 and not w.pending


def test_lock_blocks_overlap_and_stale_lock_is_cleared(tmp_path):
    w, clock, calls = make(tmp_path, {"instagram": [{"c:1": 1}, {"c:1": 2}]})
    w.step()
    other = watch.Watcher(tmp_path, fetchers={}, now_fn=clock, windows_fn=lambda n: {}, env={})
    assert other.lock() is True
    clock.adv(61)
    r = w.step()
    assert r["changed"] and not r["ticked"] and calls["ticks"] == 0 and "instagram" in w.pending       # lock held elsewhere: deferred
    assert "deferred" in (tmp_path / "work/engage/watch.log").read_text(encoding="utf-8")
    clock.adv(watch.LOCK_STALE_S + 10)
    assert w.step()["ticked"] and calls["ticks"] == 1                  # a dead lock is removed
    assert not (tmp_path / "work/engage/watch.lock").exists()          # and ours is released


def test_backoff_doubles_to_the_cap_and_recovers(tmp_path):
    boom = RuntimeError("HTTP 500 access_token=SECRETSECRET1234")
    w, clock, calls = make(tmp_path, {"facebook": [boom, boom, boom, boom, boom, boom, boom, boom, boom, boom, boom, {"c:1": 1}]})
    waits = []
    for _ in range(8):
        w.step(clock())
        waits.append((w.next_at["facebook"] - clock()).total_seconds())
        clock.t = w.next_at["facebook"]
    assert waits[0] >= 120 and waits[1] >= 240 and waits[2] >= 480
    assert max(waits) <= watch.BACKOFF_MAX_S * 1.1 + 1 and waits[-1] >= watch.BACKOFF_MAX_S
    assert w.state["health"]["facebook"]["status"] == "error" and calls["ticks"] == 0
    log = (tmp_path / "work/engage/watch.log").read_text(encoding="utf-8")
    assert "ERROR #1" in log
    for _ in range(5):
        w.step(clock())
        clock.t = w.next_at["facebook"]
    assert w.state["health"]["facebook"]["status"] == "ok" and w.fails["facebook"] == 0


def test_errors_never_leak_a_token_and_never_crash(tmp_path):
    w, clock, calls = make(tmp_path, {"instagram": [RuntimeError("boom access_token=ABCDEFGH12345678 end")]})
    w.step()
    text = (tmp_path / "work/engage/watch.log").read_text(encoding="utf-8") + json.dumps(w.state)
    assert "ABCDEFGH12345678" not in text


def test_quiet_hours_poll_nothing_and_tick_after(tmp_path):
    w, clock, calls = make(tmp_path, {"instagram": [{"c:1": 1}, {"c:1": 2}]}, quiet=False)
    w.step()
    clock.adv(61)
    w.quiet_fn = lambda t: True
    r = w.step()
    assert r["quiet"] and r["polled"] == [] and calls["fetch"]["instagram"] == 1 and calls["ticks"] == 0
    assert w.state["health"]["instagram"]["status"] == "quiet"
    w.quiet_fn = lambda t: False
    clock.adv(10)
    r = w.step()
    assert r["changed"] == ["instagram"] and r["ticked"] and calls["ticks"] == 1


def test_pending_during_quiet_is_kept_for_the_morning(tmp_path):
    w, clock, calls = make(tmp_path, {"instagram": [{"c:1": 1}, {"c:1": 2}]})
    w.step()
    clock.adv(61)
    w.step_poll = None
    w.pending.add("instagram")                                         # a change found just before the quiet span began
    w.quiet_fn = lambda t: True
    assert w.run_tick_if_due(clock()) is False and w.pending == {"instagram"}
    w.quiet_fn = lambda t: False
    assert w.run_tick_if_due(clock()) is True and calls["ticks"] == 1


def test_follow_up_tick_for_a_scheduled_reply(tmp_path):
    clock = Clock()
    due = T0 + timedelta(seconds=61 + 300)
    w, clock, calls = make(tmp_path, {"instagram": [{"c:1": 1}, {"c:1": 2}]}, clock=clock, due=due)
    w.step()
    clock.adv(61)
    assert w.step()["ticked"]
    assert w.follow_up is not None
    clock.adv(200)
    assert w.step()["ticked"] is False                                 # not yet
    clock.adv(150)
    assert w.step()["ticked"] and calls["ticks"] == 2                  # the reply that was due is sent without any new notification


def test_failed_tick_is_asked_again(tmp_path):
    n = {"i": 0}

    def tick():
        n["i"] += 1
        return {"rc": 1, "err": "boom"} if n["i"] == 1 else {"rc": 0, "sent": 0}

    w, clock, calls = make(tmp_path, {"instagram": [{"c:1": 1}, {"c:1": 2}]}, tick=tick)
    w.step()
    clock.adv(61)
    w.step()
    assert "instagram" in w.pending
    clock.adv(61)
    w.step()
    assert n["i"] == 2 and not w.pending


def test_health_files_are_written(tmp_path):
    (tmp_path / "board" / "data").mkdir(parents=True)
    w, clock, calls = make(tmp_path, {"instagram": [{"c:1": 1}]})
    w.step()
    d = json.loads((tmp_path / "board/data/watch.json").read_text(encoding="utf-8"))
    assert d["watching"] and d["platforms"]["instagram"]["status"] == "ok" and d["platforms"]["instagram"]["last_check"]
    assert (tmp_path / "board/data/watch.js").read_text(encoding="utf-8").startswith("window.__WATCH__ = ")
    assert json.loads((tmp_path / "work/engage/watch-state.json").read_text(encoding="utf-8"))["sigs"]["instagram"] == {"c:1": 1}


def test_state_survives_a_restart(tmp_path):
    w, clock, calls = make(tmp_path, {"instagram": [{"c:1": 1}]})
    w.step()
    w2, clock2, calls2 = make(tmp_path, {"instagram": [{"c:1": 5}]})
    r = w2.step()
    assert r["changed"] == ["instagram"] and r["ticked"]               # a comment that arrived while the watcher was off is caught


def test_instagram_fetcher_uses_open_reels_only(monkeypatch):
    import ig
    seen = {}

    def fake_read_pages(env, path, params, extra=""):
        seen["path"] = path
        return [{"id": "m1", "comments_count": 4}, {"id": "old", "comments_count": 9}]

    def fake_api(env, method, path, params=None, **kw):
        return {"data": [{"updated_time": "2026-10-27T10:00:00+0000"}, {"updated_time": "2026-10-27T11:00:00+0000"}]}

    monkeypatch.setattr(ig, "read_pages", fake_read_pages)
    monkeypatch.setattr(ig, "api", fake_api)
    env = {"IG_ACCESS_TOKEN": "x" * 12, "FB_PAGE_ID": "p", "IG_USER_ID": "u"}
    ctx = {"env": env, "now": T0, "cache": {}, "windows": {"E01": {"instagram": {"start": T0 - timedelta(hours=2), "end": T0 + timedelta(hours=70), "ids": ["m1"]}}}}
    sig = watch.fetch_instagram(ctx)
    assert sig == {"c:m1": 4, "dm": ["2026-10-27T11:00:00+0000"]}
