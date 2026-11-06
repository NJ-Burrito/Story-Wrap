"""The learning phases (tools/learn.py): build retro, audience review, playbook promotion, proposals, the next brief, the budget. No model, no network, no GPU."""
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

import pytest

import daily
import learn

REPO = Path(__file__).resolve().parents[2]
D = dt.datetime


def jw(p, d):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def jl(p, rows):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")


def mk(tmp_path, ep="E02", posted=True):
    root = tmp_path / "repo"
    ed = root / "bible" / "series" / "series" / "episodes" / ep
    ed.mkdir(parents=True)
    jw(ed / "script.json", {"lines": [{"id": "L01", "text": "حقيبة تصل بلا صاحب."}, {"id": "L02", "text": "عليها اسم موظفة جديدة."}]})
    jw(ed / "calm-plan.json", {"scenes": [{"id": "s01"}, {"id": "s02"}], "hook_pattern": 3})
    (ed / "caption.txt").write_text("الحلقة 2 | the series", encoding="utf-8")
    shutil_copy(REPO / "pipelines" / "heal.json", root / "pipelines" / "heal.json")
    w, dd = root / "work" / "episodes" / ep, root / "work" / "daily" / ep
    jw(w / "gate" / "report.json", {"verdict": "PASS", "checks": [{"id": "CALM-LENGTH", "status": "pass", "detail": "127 s", "warning": "long"},
                                                                  {"id": "CAP-ARABIC-SHAPING", "status": "fail", "detail": "seam ratio 0.004"}]})
    jl(w / "heal" / "rounds.jsonl", [{"round": 1, "stage": "compose", "fault": "C1", "class": "GATE-BLIND", "check": "CAP-ARABIC-SHAPING", "kind": "tool", "result": "fixed", "tokens": 5200, "fix": "outline under-layer"},
                                     {"round": 2, "stage": "compose", "fault": "C2", "class": "AUDIO", "check": "AUDIO-DIALOGUE-CLARITY", "kind": "tool", "result": "fixed", "tokens": 3100, "fix": "dip"}])
    jw(w / "heal" / "critic.json", {"score": 9, "round": 1, "tokens": 4000, "faults": [{"id": "F-001", "severity": "S4", "description": "tag touches the hijab"}], "answers": [{"q": "Q01", "ok": False, "evidence": "frame 516"}],
                                    "notes_x": "the intro freeze was tight"})
    jw(w / "timeline.json", {"total_s": 100.0})
    jw(dd / "STATE.json", {"episode": ep, "stages": {"critic": {"status": "ok", "seconds": 180.0, "info": {"tokens": 4000}, "verify": {"status": "pass", "findings": []}},
                                                      "compose": {"status": "ok", "seconds": 600.0, "verify": {"status": "fail", "findings": [{"id": "COMPOSE-X", "sev": "fail"}]}}}})
    jl(dd / "timings.jsonl", [{"stage": "compose", "phase": "run", "seconds": 600.0, "result": "ok"}, {"stage": "compose", "phase": "verify", "seconds": 2.0, "result": "fail"}])
    jw(root / "work" / "daily" / "budget-2026-10-26.json", {"tokens": 12000, "calls": [{"name": f"writer-{ep}", "tokens": 8000}, {"name": f"critic-{ep}-0", "tokens": 4000}]})
    jl(root / "kb" / "lessons" / "ledger.jsonl", [{"id": "L-0001", "build": "style-v1", "class": "GATE-BLIND", "summary": "an old lesson", "source": "heal"}])
    if posted:
        jw(w / "post.json", {"media_id": "m1", "posted_at": "2026-10-26T19:30:00", "permalink": "https://x"})
        jw(w / "facebook.json", {"video_id": "v1", "publish_at": "2026-10-26T20:30:00"})
        jw(w / "comments.json", {"own_usernames": ["story_account"], "comments": [
            {"id": "1", "platform": "instagram", "username": "a", "text": "لم أفهم لماذا اسمها على الحقيبة؟"},
            {"id": "2", "platform": "instagram", "username": "b", "text": "أتمنى حلقة عن هدى"},
            {"id": "3", "platform": "instagram", "username": "story_account", "text": "شكرا لكم"}]})
    return root


def shutil_copy(a, b):
    b.parent.mkdir(parents=True, exist_ok=True)
    b.write_bytes(a.read_bytes())


class FakeLLM:
    def __init__(self, payload, tokens=1000, fail=False, budget=None):
        self.payload, self.tokens, self.fail, self.budget, self.prompts, self.calls = payload, tokens, fail, budget, [], 0

    def __call__(self, prompt, *, name, tools="Read,Glob,Grep", effort="medium", **kw):
        self.calls += 1
        self.prompts.append(prompt)
        assert tools == "Read,Glob,Grep" and "Agent" not in tools        # read-only tools: the script writes the files
        if self.fail:
            return {"rc": 1, "text": "", "err": "boom", "tokens": 0}
        if self.budget is not None:
            self.budget.add(name, self.tokens)
        return {"rc": 0, "text": json.dumps(self.payload, ensure_ascii=False), "err": "", "tokens": self.tokens}


RETRO_OUT = {"lessons": [{"summary": "The Arabic caption seam was only caught after 5200 tokens of heal.", "class": "GATE-BLIND", "root_cause": "cause not recorded", "fix": "check plates early", "check": "CAP-ARABIC-SHAPING", "evidence": ["work/episodes/E02/gate/report.json"]},
                        {"summary": "Audio dialogue clarity needed a dip.", "class": "AUDIO", "root_cause": "cause not recorded", "fix": "dip the bed", "check": "AUDIO-DIALOGUE-CLARITY", "evidence": ["work/episodes/E02/heal/rounds.jsonl"]},
                        {"summary": "The critic scored 9.", "class": "PROCESS", "root_cause": "x", "fix": "y", "check": "", "evidence": ["work/episodes/E02/heal/critic.json"]}],
             "playbook": [{"section": "Captions", "key": "arabic-seams", "text": "Check Arabic caption joins before compose.", "evidence": ["work/episodes/E02/gate/report.json"]},
                          {"section": "Sound", "key": "dip-bed", "text": "Dip the music under introductions.", "evidence": ["work/episodes/E02/heal/rounds.jsonl"]}],
             "proposals": [{"kind": "gate", "target": "tools/qg_checks.py", "text": "Make CAP-ARABIC-SHAPING stricter on seam ratio.", "direction": "stricter", "evidence": ["work/episodes/E02/gate/report.json"]},
                           {"kind": "code", "target": "tools/calm_compose.py", "text": "Run the shaping check before the plates are composed.", "evidence": []}]}


# ------------------------------------------------------------------ the build retro
def test_retro_facts_come_from_the_files(tmp_path):
    root = mk(tmp_path)
    jw(root / "work" / "episodes" / "E01C" / "learn" / "retro-facts.json", {"gate": {"failed": [{"id": "CAP-ARABIC-SHAPING"}]}, "heal": {"by_check": {}, "by_class": {"GATE-BLIND": {}}}})
    f = learn.collect_build_facts(root, "E02")
    assert f["gate"]["failed"][0]["id"] == "CAP-ARABIC-SHAPING" and f["gate"]["warnings"][0]["id"] == "CALM-LENGTH"
    assert f["heal"]["by_class"]["GATE-BLIND"] == {"rounds": 1, "tokens": 5200, "fixed": 1} and f["heal"]["tokens"] == 8300
    assert f["critic"]["score"] == 9 and f["critic"]["faults"][0]["id"] == "F-001" and "intro freeze" in f["critic"]["notes"]["notes_x"]
    assert f["timings"]["compose"]["runs"] == 1 and f["timings"]["compose"]["verify_fails"] == 1 and f["stages"]["compose"]["verify_fails"] == ["COMPOSE-X"]
    assert f["tokens"]["total"] == 12000
    assert f["repeated"]["checks"]["CAP-ARABIC-SHAPING"] == ["E01C"] and "E01C" in f["repeated"]["classes"]["GATE-BLIND"]
    assert any("ledger" in x for x in f["repeated"]["classes"]["GATE-BLIND"])


def test_retro_writes_lessons_playbook_and_proposals(tmp_path):
    root = mk(tmp_path)
    llm = FakeLLM(RETRO_OUT)
    r = learn.retro("E02", root, llm=llm, now=D(2026, 10, 26, 12))
    assert r["status"] == "done" and len(r["lessons"]) == 3 and 3 <= len(r["lessons"]) <= 7
    led = [json.loads(x) for x in (root / "kb/lessons/ledger.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [e["id"] for e in led] == ["L-0001", "L-0002", "L-0003", "L-0004"] and led[-1]["source"] == "retro" and led[-1]["build"] == "E02"
    pb = learn.playbook_load(root)
    e = pb["Captions"][0]
    assert e["status"] == "candidate" and e["episodes"] == ["E02"] and e["evidence"] == ["work/episodes/E02/gate/report.json"]
    props = [json.loads(x) for x in (root / "work/learn/proposals.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [p["status"] for p in props] == ["pending", "pending"] and props[0]["kind"] == "gate"
    assert "Arabic caption" in learn.playbook_block(root)


def test_retro_drops_invented_numbers_and_missing_evidence_falls_back_to_the_facts_file(tmp_path):
    root = mk(tmp_path)
    out = json.loads(json.dumps(RETRO_OUT))
    out["lessons"][1]["summary"] = "Heal cost 99999 tokens."                       # not in the facts
    out["lessons"][0]["evidence"] = ["nope/missing.json"]
    r = learn.retro("E02", root, llm=FakeLLM(out))
    assert len(r["lessons"]) == 2 and any("99999" in x["reason"] for x in r["rejected"])
    led = [json.loads(x) for x in (root / "kb/lessons/ledger.jsonl").read_text(encoding="utf-8").splitlines()]
    assert led[1]["files"] == ["work/episodes/E02/learn/retro-facts.json"]


def test_retro_is_idempotent_and_force_adds_nothing_twice(tmp_path):
    root = mk(tmp_path)
    llm = FakeLLM(RETRO_OUT)
    learn.retro("E02", root, llm=llm)
    n_led = (root / "kb/lessons/ledger.jsonl").read_text(encoding="utf-8")
    n_pb = (root / "kb/playbook.md").read_text(encoding="utf-8")
    r2 = learn.retro("E02", root, llm=llm)
    assert llm.calls == 1 and "skipped" in r2                                        # no second model call
    learn.retro("E02", root, llm=llm, force=True)
    assert llm.calls == 2
    assert (root / "kb/lessons/ledger.jsonl").read_text(encoding="utf-8") == n_led     # same episode, same lessons: no duplicates
    assert (root / "kb/playbook.md").read_text(encoding="utf-8") == n_pb               # same episode does not promote its own candidate
    assert len((root / "work/learn/proposals.jsonl").read_text(encoding="utf-8").splitlines()) == 2


def test_retro_failure_is_reported_not_raised(tmp_path):
    root = mk(tmp_path)
    r = learn.retro("E02", root, llm=FakeLLM({}, fail=True))
    assert r["status"] == "facts-only" and "failed rc=1" in r["error"]
    assert (root / "work/episodes/E02/learn/retro-facts.json").is_file()
    assert "retro" in (root / "work/learn/failures.jsonl").read_text(encoding="utf-8")


# ------------------------------------------------------------------ the playbook: candidate -> rule
def test_candidate_becomes_rule_when_it_repeats_in_another_episode(tmp_path):
    root = tmp_path / "r"
    ev = ["a.json"]
    assert learn.playbook_add(root, "Hooks", "warn-first", "Open on a direct warning.", ev, "E01C") == "new"
    assert learn.playbook_add(root, "Hooks", "warn-first", "Open on a direct warning.", ev, "E01C") == "same-episode"
    assert learn.playbook_load(root)["Hooks"][0]["status"] == "candidate"
    assert learn.playbook_add(root, "Hooks", "warn-first", "Open on a direct warning.", ["b.json"], "E02") == "promoted"
    e = learn.playbook_load(root)["Hooks"][0]
    assert e["status"] == "rule" and e["episodes"] == ["E01C", "E02"] and e["evidence"] == ["a.json", "b.json"]
    assert learn.playbook_add(root, "Hooks", "warn-first", "Open on a direct warning.", ev, "E03") == "repeat"
    learn.playbook_add(root, "Pacing", "other", "A new idea.", ev, "E03")
    block = learn.playbook_block(root)
    assert block.index("[rule]") < block.index("[candidate]")                          # rules first
    with pytest.raises(ValueError):
        learn.playbook_add(root, "Marketing", "x", "y", ev, "E01")


def test_a_near_duplicate_text_joins_the_same_entry(tmp_path):
    root = tmp_path / "r"
    learn.playbook_add(root, "Writing", "k1", "Keep every sentence under eight words.", ["a"], "E01")
    assert learn.playbook_add(root, "Writing", "different-key", "Keep every sentence under eight words!", ["b"], "E02") == "promoted"
    assert len(learn.playbook_load(root)["Writing"]) == 1


def test_the_playbook_block_is_capped(tmp_path):
    root = tmp_path / "r"
    for i in range(80):
        learn.playbook_add(root, "Visuals", f"k{i}", f"Habit number {i} " + "x" * 80, ["a"], f"E{i:02d}")
    assert len(learn.playbook_block(root)) <= learn.PLAYBOOK_PROMPT_CHARS


# ------------------------------------------------------------------ proposals: never applied, a gate never loosened
def test_no_gate_loosening_proposal_is_accepted(tmp_path):
    root = mk(tmp_path)
    bad = [{"kind": "gate", "target": "tools/qg_checks.py", "text": "Raise the CAP-ARABIC-SHAPING seam ratio limit to 0.01.", "direction": "looser"},
           {"kind": "gate", "target": "tools/qg_checks.py", "text": "Tighten the seam check.", "direction": "none"},
           {"kind": "code", "target": "tools/qg_checks.py", "text": "Skip the loudness check on long episodes."},
           {"kind": "rule", "target": "R-212", "text": "Relax the gate threshold when the critic scores 9."},
           {"kind": "template", "target": "t", "text": "Exempt intros from the check."}]
    ok = [{"kind": "gate", "target": "tools/qg_checks.py", "text": "Make the loudness gate stricter by half a dB.", "direction": "stricter"},
          {"kind": "template", "target": "tools/templates/x", "text": "Add a second marker cue."}]
    ids, rejected = learn.add_proposals(root, "E02", bad + ok, "retro", "2026-10-26")
    assert len(ids) == 2 and len(rejected) == 5
    rej = [json.loads(x) for x in (root / "work/learn/rejected.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rej) == 5 and all(r["reason"] for r in rej)
    assert all(p["status"] == "pending" for p in learn.read_jsonl(root / "work/learn/proposals.jsonl"))
    assert not any(re.search(r"relax|skip|exempt|raise", p["text"], re.I) for p in learn.read_jsonl(root / "work/learn/proposals.jsonl"))


def test_proposals_are_never_applied(tmp_path):
    root = mk(tmp_path)
    for rel in ("tools/qg_checks.py", "tools/calm_compose.py", "pipelines/heal.json"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        if rel != "pipelines/heal.json":
            (root / rel).write_text("# original\n", encoding="utf-8")
    before = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file() and p.suffix in (".py", ".json") and "work" not in p.parts and "bible" not in p.parts}
    learn.retro("E02", root, llm=FakeLLM(RETRO_OUT))
    after = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file() and p.suffix in (".py", ".json") and "work" not in p.parts and "bible" not in p.parts}
    assert before == after                                                            # code, gates and heal.json untouched
    assert not [n for n in dir(learn) if n.startswith(("apply", "merge", "accept"))]  # there is no function that applies a proposal
    assert {p["status"] for p in learn.read_jsonl(root / "work/learn/proposals.jsonl")} == {"pending"}


# ------------------------------------------------------------------ the audience review
def test_review_is_due_with_the_harvest_14_00_the_day_after_the_later_post(tmp_path):
    root = mk(tmp_path)
    assert learn.review_due_at(root, "E02") == D(2026, 10, 27, 14, 0)                 # 14:00 the day after the later post (the owner 2026-10-27)
    assert learn.review(  "E02", root, now=D(2026, 10, 27, 13, 59), fetch=lambda e, r: {})["status"] == "waits"
    (root / "work/episodes/E02/facebook.json").unlink()
    assert learn.review_due_at(root, "E02") == D(2026, 10, 27, 14, 0)                 # Instagram only: the same time
    r = learn.review_due(root, go=False, at=D(2026, 10, 27, 13, 59))
    assert r["status"] == "IDLE"
    r = learn.review_due(root, go=False, at=D(2026, 10, 27, 14, 1))
    assert r["reviewed"] == ["E02 (dry)"] and not (root / "work/episodes/E02/learn/review.json").exists()
    assert learn.review("E01", root, now=D(2026, 10, 28))["status"] == "not posted"


def metrics_fixture(ep="E02"):
    return {"episode": ep, "fetched_at": "2026-10-27T10:35:00",
            "instagram": {"reach": {"value": 480}, "views": {"value": 1250}, "ig_reels_avg_watch_time": {"value": 31500}, "shares": {"value": 7}, "saved": {"value": 12}, "likes": {"value": 61},
                          "comments": {"value": 9}, "reels_skip_rate": {"status": "not available", "reason": "HTTP 400"}},
            "facebook": {"total_video_views": {"value": 300}}, "youtube": {"status": "not available", "reason": "private"}}


REVIEW_OUT = {"summary": "E02 reached 480 accounts with 1250 views and 12 saves; the skip rate is not available.",
              "findings": [{"section": "Hooks", "key": "object-first", "text": "An object-first opening kept 31500 ms of average watch time.", "evidence": []}],
              "confusions": ["why her name is on the bag"], "requests": ["more Hero"], "favourites": ["Hero"],
              "experiment_result": None, "next_experiment": {"idea": "Open on a character line instead of the object.", "metric": "views"},
              "brief": ["Explain the bag label in the first minute."], "proposals": []}


def reviewed(root, llm, **kw):
    return learn.review("E02", root, llm=llm, fetch=lambda e, r: metrics_fixture(), now=D(2026, 10, 27, 14, 40), **kw)


def test_review_writes_metrics_playbook_experiment_and_the_next_brief(tmp_path):
    root = mk(tmp_path)
    brief = root / "work/episodes/E02/next-brief.md"
    brief.write_text("# Brief for E03\n\n## The vote\n\n- x\n", encoding="utf-8")
    r = reviewed(root, FakeLLM(REVIEW_OUT))
    assert r["status"] == "done" and r["brief_attached"] is True
    m = json.loads((root / "work/episodes/E02/learn/metrics.json").read_text(encoding="utf-8"))
    assert m["instagram"]["reels_skip_rate"]["status"] == "not available" and m["context"]["length_s"] == 100.0 and m["context"]["hook_pattern"] == 3
    assert m["comparison"]["derived"]["instagram.avg_watch_share_of_length"] == 0.315          # 31.5 s of 100 s, computed by the script
    pb = learn.playbook_load(root)
    assert pb["Hooks"][0]["status"] == "candidate" and pb["Hooks"][0]["evidence"] == ["work/episodes/E02/learn/metrics.json"]
    exp = learn.read_jsonl(root / "work/learn/experiments.jsonl")
    assert exp[0]["status"] == "open" and exp[0]["for_episode"] == "E03" and exp[0]["baseline"] == 1250 and exp[0]["metric"] == "views"
    t = brief.read_text(encoding="utf-8")
    assert learn.LEARNED_BEGIN in t and "## Learned from E02" in t and "Explain the bag label" in t and "Test only this one idea in E03" in t and "why her name is on the bag" in t


def test_review_summary_numbers_all_come_from_the_metrics_file(tmp_path):
    root = mk(tmp_path)
    r = reviewed(root, FakeLLM(REVIEW_OUT))
    blob = (root / "work/episodes/E02/learn/metrics.json").read_text(encoding="utf-8")
    assert learn.numbers_in(r["summary"]) <= learn.numbers_in(blob)
    invented = json.loads(json.dumps(REVIEW_OUT))
    invented["summary"] = "E02 reached 7777 accounts."
    invented["findings"][0]["text"] = "Retention was 88 percent."
    invented["brief"] = ["Cut the episode to 60 s", "Keep the bag label."]
    root2 = mk(tmp_path / "b")
    r2 = reviewed(root2, FakeLLM(invented))
    assert "7777" not in r2["summary"] and learn.numbers_in(r2["summary"]) <= learn.numbers_in((root2 / "work/episodes/E02/learn/metrics.json").read_text(encoding="utf-8"))
    assert r2["findings"] == [] and len(r2["rejected"]) >= 3
    t = (root2 / "work/episodes/E02/learn/learned-brief.md").read_text(encoding="utf-8")
    assert "60" not in t and "Keep the bag label" in t


def test_review_is_idempotent(tmp_path):
    root = mk(tmp_path)
    llm = FakeLLM(REVIEW_OUT)
    reviewed(root, llm)
    snap = {p.name: p.read_bytes() for p in (root / "work/learn").glob("*.jsonl")}
    pb = (root / "kb/playbook.md").read_bytes()
    r = reviewed(root, llm)
    assert llm.calls == 1 and r["skipped"] == "already reviewed"
    assert {p.name: p.read_bytes() for p in (root / "work/learn").glob("*.jsonl")} == snap and (root / "kb/playbook.md").read_bytes() == pb
    res = learn.review_due(root, go=True, at=D(2026, 10, 28), llm=llm, fetch=lambda e, r: metrics_fixture())
    assert llm.calls == 1 and res["status"] == "IDLE"                                  # the hourly tick leaves a finished review alone


def test_review_repeat_in_the_next_episode_promotes_to_a_rule(tmp_path):
    root = mk(tmp_path)
    reviewed(root, FakeLLM(REVIEW_OUT))
    root_e3 = mk(tmp_path / "x", ep="E03")                                             # a second episode in a second tree, then its playbook is merged by copying
    (root_e3 / "kb").mkdir(exist_ok=True)
    (root_e3 / "kb/playbook.md").write_bytes((root / "kb/playbook.md").read_bytes())
    jw(root_e3 / "work/episodes/E03/post.json", {"media_id": "m", "posted_at": "2026-10-27T19:30:00"})
    r = learn.review("E03", root_e3, llm=FakeLLM(REVIEW_OUT), fetch=lambda e, rr: {**metrics_fixture("E03")}, now=D(2026, 10, 28, 14, 30))
    assert r["findings"][0]["result"] == "promoted"
    assert learn.playbook_load(root_e3)["Hooks"][0]["status"] == "rule"


def test_review_failures_retry_then_keep_the_metrics(tmp_path):
    root = mk(tmp_path)
    r = reviewed(root, FakeLLM({}, fail=True))
    assert r["status"] == "retry" and r["attempts"] == 1
    assert learn.review_due(root, go=True, at=D(2026, 10, 27, 14, 30), llm=FakeLLM({}, fail=True), fetch=lambda e, rr: metrics_fixture())["status"] == "WAIT"
    r = reviewed(root, FakeLLM({}, fail=True))
    assert r["status"] == "metrics-only" and "480" in r["summary"] and r["attempts"] == 3
    assert reviewed(root, FakeLLM(REVIEW_OUT))["skipped"] == "already reviewed"


def test_review_waits_without_a_token_and_when_the_budget_is_spent(tmp_path):
    root = mk(tmp_path)
    nt = lambda e, r: {"episode": e, "instagram": {"status": "not available", "reason": "no Instagram token"}, "facebook": None, "youtube": None}   # noqa: E731
    r = learn.review("E02", root, llm=FakeLLM(REVIEW_OUT), fetch=nt, now=D(2026, 10, 28))
    assert r["status"] == "NO-TOKEN" and not (root / "work/episodes/E02/learn/review.json").exists()
    b = daily.Budget(root, limit=100, today="2026-10-26")
    guard = lambda prompt, **kw: (learn.budget_guard(b, kw["name"]), {"rc": 0, "text": "{}", "tokens": 0})[1]   # noqa: E731
    r = reviewed(root, guard)
    assert r["status"] == "waits" and r["attempts"] == 0 and "LLM-BUDGET" in r["error"]       # waiting for the budget is not a failed try
    assert not (root / "work/episodes/E02/learn/review.json").exists()


def test_comment_themes_count_by_pattern_and_leave_the_own_account_out(tmp_path):
    root = mk(tmp_path)
    t = learn.comment_themes(root, "E02")
    assert t["total"] == 2 and t["kinds"]["confusion"] == 1 and t["kinds"]["question"] == 1 and t["kinds"]["request"] == 1


def test_fetch_metrics_records_what_the_api_does_not_offer_and_never_leaks(tmp_path, monkeypatch):
    import fb
    import ig
    root = mk(tmp_path)
    env = {"IG_ACCESS_TOKEN": "SECRET-IG", "FB_PAGE_TOKEN": "SECRET-FB", "FB_PAGE_ID": "p"}

    def igapi(env_, method, path, params=None, **kw):
        m = (params or {}).get("metric")
        if m in ("plays", "reels_skip_rate", "ig_reels_skip_rate"):
            ig.fail("IG-HTTP", "HTTP 400 metric not supported")
        if m:
            return {"data": [{"name": m, "values": [{"value": 5}]}]}
        return {"like_count": 61, "comments_count": 9}

    monkeypatch.setattr(ig, "api", igapi)
    monkeypatch.setattr(fb, "api", lambda e, method, path, params=None, **kw: {"data": [{"values": [{"value": 3}]}]} if (params or {}).get("metric") else {"likes": {"summary": {"total_count": 2}}, "comments": {"summary": {"total_count": 1}}})
    jw(root / "work/episodes/E02/facebook.json", {"video_id": "v1", "state": "posted", "posted_at": "2026-10-26T20:30:00"})
    m = learn.fetch_metrics("E02", root, env=env, now=D(2026, 10, 27, 11), yt_stats=lambda e, r: {"status": "not available", "reason": "private"})
    assert m["instagram"]["reach"] == {"value": 5} and m["instagram"]["reels_skip_rate"]["status"] == "not available" and m["instagram"]["plays"]["status"] == "not available"
    assert m["facebook"]["likes"] == {"value": 2} and m["facebook"]["total_video_views"] == {"value": 3} and m["youtube"]["reason"] == "private"
    assert "SECRET" not in json.dumps(m)


# ------------------------------------------------------------------ the next episode uses it
def test_the_writer_and_healer_prompts_carry_the_playbook_and_the_learned_section(tmp_path):
    root = tmp_path / "repo"
    (root / "bible/series/series/episodes/E02").mkdir(parents=True)
    (root / "work").mkdir()
    learn.playbook_add(root, "Hooks", "r1", "Open on a direct warning.", ["a"], "E01")
    learn.playbook_add(root, "Hooks", "r1", "Open on a direct warning.", ["a"], "E02")
    learn.playbook_add(root, "Sound", "c1", "Dip the bed under introductions.", ["a"], "E02")
    w1 = root / "work/episodes/E01"
    w1.mkdir(parents=True)
    (w1 / "next-brief.md").write_text(f"# Brief for E02\n\n{learn.LEARNED_BEGIN}\n## Learned from E01\n- Result: reach was 480.\n- Test only this one idea in E02: open on a line.\n{learn.LEARNED_END}\n", encoding="utf-8")
    seen = []

    def fake(prompt, **kw):
        seen.append(prompt)
        return {"rc": 0, "text": "", "err": "", "tokens": 0, "missing": [], "seconds": 0}
    ctx = daily.Ctx("E02", root=root, llm=lambda prompt, **kw: fake(prompt, **kw), budget=daily.Budget(root, limit=10**6, today="2026-10-26"), log=lambda *a: None)
    with pytest.raises(daily.StageFail):                                               # the fake writes no files, so the plan check fails after the prompt was sent
        daily.s_script(ctx)
    p = seen[0]
    assert "CRAFT PLAYBOOK" in p and "[rule] Hooks: Open on a direct warning." in p and "[candidate] Sound: Dip the bed" in p
    assert p.index("[rule]") < p.index("[candidate]")
    assert "LEARNED FROM THE LAST EPISODE" in p and "## Learned from E01" in p and "Test only this one idea in E02" in p
    assert 'its section "Learned from"' in p
    assert "[rule] Hooks" in daily.learned_block(ctx)                                  # the healer prompt carries the same block


def test_vote_next_keeps_the_learned_block_when_it_rewrites_the_brief(tmp_path):
    root = mk(tmp_path)
    reviewed(root, FakeLLM(REVIEW_OUT))                                                # no brief yet: learned-brief.md only
    brief = root / "work/episodes/E02/next-brief.md"
    assert not brief.exists() and "Learned from E02" in learn.learned_text(root, "E02")
    brief.write_text("# Brief for E03\n\n## The vote\n\n- first\n", encoding="utf-8")   # what vote.py writes
    assert learn.attach_learned(root, "E02")
    brief.write_text("# Brief for E03\n\n## The vote\n\n- rewritten\n", encoding="utf-8")  # vote.py runs again
    assert learn.LEARNED_BEGIN not in brief.read_text(encoding="utf-8")
    learn.attach_learned(root, "E02")
    t = brief.read_text(encoding="utf-8")
    assert t.count(learn.LEARNED_BEGIN) == 1 and "rewritten" in t
    learn.attach_learned(root, "E02")
    assert brief.read_text(encoding="utf-8").count(learn.LEARNED_BEGIN) == 1          # replaced in place, never doubled


# ------------------------------------------------------------------ the budget and the stage
def test_the_retro_stage_respects_the_token_budget(tmp_path):
    root = mk(tmp_path)
    called = []
    ctx = daily.Ctx("E02", root=root, llm=lambda prompt, **kw: called.append(1) or {"rc": 0, "text": "{}", "tokens": 0}, budget=daily.Budget(root, limit=learn.MIN_LEFT - 1, today="2026-10-26"), log=lambda *a: None)
    info = daily.s_retro(ctx)
    assert called == [] and info["_status"] == "skipped" and info["retro_failed"] and "LLM-BUDGET" in info["why"]
    assert (root / "work/episodes/E02/learn/retro-facts.json").is_file()               # the deterministic half still ran


def test_the_retro_call_uses_the_daily_budget_and_a_capped_prompt(tmp_path):
    root = mk(tmp_path)
    b = daily.Budget(root, limit=250000, today="2026-10-26")
    prompts = []

    def llm(prompt, *, name, tools, **kw):
        prompts.append(prompt)
        b.add(name, 1500)
        return {"rc": 0, "text": json.dumps(RETRO_OUT), "err": "", "tokens": 1500, "missing": [], "seconds": 0}
    big = root / "work/episodes/E02/heal/rounds.jsonl"
    learn.append_jsonl(big, {"round": 3, "stage": "x", "fault": "Z", "class": "UNKNOWN", "fix": "y" * 5000, "result": "fixed"})
    ctx = daily.Ctx("E02", root=root, llm=llm, budget=b, log=lambda *a: None)
    info = daily.s_retro(ctx)
    assert info["lessons"] == 3 and len(prompts) == 1 and len(prompts[0]) <= learn.MAX_PROMPT_CHARS
    assert b.data["tokens"] == 13500 and b.data["calls"][-1]["name"] == "retro-E02"     # counted on the same day's budget file as the writer and critic


def test_the_retro_never_blocks_publishing(tmp_path):
    root = mk(tmp_path)
    ctx = daily.Ctx("E02", root=root, llm=lambda prompt, **kw: {"rc": 1, "text": "", "err": "model down", "tokens": 0}, budget=daily.Budget(root, limit=250000, today="2026-10-26"), log=lambda *a: None)
    assert daily.run_stage(ctx, daily.STAGES["retro"]) == "skipped"
    assert "retro" in daily.NONBLOCKING
    ctx.state["stages"].pop("retro", None)                                              # even a retro that never ran is no condition of the post
    assert daily.stage_state(ctx, daily.STAGES["retro"])[0] == "stale"
    daily.require_upstream(ctx, ["retro"])                                              # does not raise UPSTREAM-NOT-VERIFIED
    assert daily.RUN_STAGES[-1] == "retro" and daily.RUN_STAGES.index("retro") == daily.RUN_STAGES.index("critic") + 1


def test_the_stage_failure_path_leaves_a_retro_record(tmp_path, monkeypatch):
    root = mk(tmp_path)
    monkeypatch.setattr(learn, "retro", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk full")))
    ctx = daily.Ctx("E02", root=root, llm=lambda *a, **k: {}, budget=daily.Budget(root, limit=250000, today="2026-10-26"), log=lambda *a: None)
    info = daily.s_retro(ctx)
    assert info["_status"] == "skipped" and json.loads((root / "work/episodes/E02/learn/retro.json").read_text(encoding="utf-8"))["status"] == "error"


# ------------------------------------------------------------------ the board
def test_the_board_data_lists_lessons_rules_and_pending_proposals(tmp_path):
    root = mk(tmp_path)
    learn.retro("E02", root, llm=FakeLLM(RETRO_OUT))
    learn.playbook_add(root, "Captions", "arabic-seams", "Check Arabic caption joins before compose.", ["a"], "E03")
    d = learn.write_board(root, D(2026, 10, 26, 13))
    assert d["counts"] == {"rules": 1, "candidates": 1, "pending_proposals": 2}
    assert d["lessons"][0]["build"] == "E02" and d["proposals"][0]["id"].startswith("LP-")
    assert json.loads((root / "board/data/learning.json").read_text(encoding="utf-8"))["counts"]["rules"] == 1
    assert (root / "board/data/learning.js").read_text(encoding="utf-8").startswith("window.__LEARNING__ = ")


def test_ig_board_write_all_writes_the_learning_file(tmp_path):
    import ig_board
    root = mk(tmp_path)
    ig_board.write_all(root, env={})
    assert (root / "board/data/learning.json").is_file()


def test_numbers_helper_ignores_ids_dates_and_clock_times():
    assert learn.numbers_in("E01C and R-368 on 2026-10-26 at 19:30 had 12 saves, 0.5 and ٣ more, L-0004 F-001") == {"12", "0.5", "3"}
    assert learn.invented_numbers("12 saves and 99", {"saved": 12}) == {"99"}


# ------------------------------------------------------------------ where our viewers are (the owner 2026-10-26: SA, IQ, EG and the top 5 countries)
IG_CC = {"data": [{"total_value": {"breakdowns": [{"results": [{"dimension_values": ["SA"], "value": 40}, {"dimension_values": ["IQ"], "value": 25}, {"dimension_values": ["EG"], "value": 20},
                                                                {"dimension_values": ["AE"], "value": 10}, {"dimension_values": ["JO"], "value": 3}, {"dimension_values": ["KW"], "value": 2}]}]}}]}


def test_fetch_countries_reads_both_platforms_and_records_what_is_missing():
    env = {"IG_ACCESS_TOKEN": "x", "IG_USER_ID": "u", "FB_PAGE_TOKEN": "y", "FB_PAGE_ID": "p"}
    calls = []

    def igapi(e, method, path, params=None, **kw):
        calls.append(params["metric"])
        assert params["breakdown"] == "country" and path == "u/insights"
        if params["metric"] == "engaged_audience_demographics":
            __import__("ig").fail("IG-HTTP", "HTTP 400 not enough followers")
        return IG_CC

    c = learn.fetch_countries(env, ig_api=igapi, fb_api=lambda e, m, path, params=None, **kw: {"data": [{"values": [{"value": {"SA": 7, "EG": 3}}, {"value": {"SA": 8, "EG": 4}}]}]})
    assert calls == ["follower_demographics", "engaged_audience_demographics"]
    assert c["instagram"]["follower_demographics"]["counts"]["SA"] == 40 and c["instagram"]["engaged_audience_demographics"]["status"] == "not available"
    assert c["facebook"]["page_fans_country"]["counts"] == {"SA": 8, "EG": 4}                 # the latest day
    none = learn.fetch_countries({}, ig_api=igapi, fb_api=igapi)
    assert none["instagram"]["status"] == "not available" and none["facebook"]["status"] == "not available"
    small = learn.fetch_countries({"IG_ACCESS_TOKEN": "x", "IG_USER_ID": "u"}, ig_api=lambda *a, **k: {"data": []})
    assert "100+ followers" in small["instagram"]["follower_demographics"]["reason"]


def test_the_review_records_the_share_of_sa_iq_eg_and_the_top_five_over_time(tmp_path):
    root = mk(tmp_path)
    m = metrics_fixture()
    m["countries"] = {"instagram": {"follower_demographics": {"counts": {"SA": 40, "IQ": 25, "EG": 20, "AE": 10, "JO": 3, "KW": 2}}}, "facebook": {"status": "not available", "reason": "no Facebook Page token"}}
    r = learn.review("E02", root, llm=FakeLLM(REVIEW_OUT), fetch=lambda e, rr: m, now=D(2026, 10, 27, 14, 40))
    assert r["where"].startswith("Where our viewers are (instagram.follower_demographics, 100 people): SA 40.0%, IQ 25.0%, EG 20.0%; top 5: SA 40.0%, IQ 25.0%, EG 20.0%, AE 10.0%, JO 3.0%")
    rows = learn.read_jsonl(root / "work/learn/countries.jsonl")
    assert len(rows) == 1 and rows[0]["shares"] == {"SA": 0.4, "IQ": 0.25, "EG": 0.2} and [t[0] for t in rows[0]["top5"]] == ["SA", "IQ", "EG", "AE", "JO"]
    assert "Where our viewers are" in (root / "work/episodes/E02/learn/learned-brief.md").read_text(encoding="utf-8")
    learn.review("E02", root, llm=FakeLLM(REVIEW_OUT), fetch=lambda e, rr: m, now=D(2026, 10, 27, 11), force=True)
    assert len(learn.read_jsonl(root / "work/learn/countries.jsonl")) == 1                       # one row per episode and source, however often it runs
    d = learn.write_board(root)
    assert d["where"].startswith("Where our viewers are") and d["countries"][0]["shares"]["SA"] == 0.4


def test_where_line_says_not_available_plainly():
    m = {"episode": "E02", "countries": {"instagram": {"follower_demographics": {"status": "not available", "reason": "needs 100+ followers"}}, "facebook": {"status": "not available", "reason": "no Facebook Page token"}}}
    assert learn.country_rows(m, "t") == []
    assert learn.where_line([], m).startswith("Where our viewers are: not available (instagram.follower_demographics: needs 100+ followers")
    assert learn.where_line([], {"episode": "E02"}) == "Where our viewers are: not available."
