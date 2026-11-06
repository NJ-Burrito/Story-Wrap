"""heal.py: classify mapping, critic validation and rubric, round limits, budget stop, learn to the ledger,
proposals for unknown faults, and the forbidden-fix guard (a changed threshold file or a hand-edited trace is refused)."""
import json
import re
import shutil
import time
from pathlib import Path

import pytest

import heal
from conftest import REPO, TOOLS
import sw_fixtures

FROZEN_FAKES = ["tools/qg_checks.py", "tools/quality_gate.py", "kb/quality/shot-spec.schema.json",
                "kb/quality/rig-trace.schema.json", "kb/quality/shotlist.schema.json", "kb/quality/viseme-track.schema.json"]


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "repo"
    for rel in ("pipelines/heal.json", "kb/quality/critic-checklist.md", "kb/quality/heal-playbooks.md"):
        (r / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / rel, r / rel)
    for rel in FROZEN_FAKES:
        (r / rel).parent.mkdir(parents=True, exist_ok=True)
        (r / rel).write_text("THRESHOLD = 0.35\n", encoding="utf-8")
    (r / "reference" / "mix-v5").mkdir(parents=True)
    (r / "reference" / "mix-v5" / "rig.out").write_text("PASS\n", encoding="utf-8")
    return r


def shot_dir(root, fails=None, gates=heal.SHOT_GATES, name="shot-x"):
    d = root / "work" / "shots" / name
    (d / "gate").mkdir(parents=True)
    (d / "shot.json").write_text("{}", encoding="utf-8")
    g = {}
    for n in gates:
        ids = (fails or {}).get(n, [])
        g[n] = {"verdict": "FAIL" if ids else "PASS", "exit": 1 if ids else 0, "fail_ids": ids}
    (d / "gate" / "report.json").write_text(json.dumps({"shot": name, "gates": g}), encoding="utf-8")
    return d


def make_critic(root, kind="shot", no=(), score=None, evidence="frame 12"):
    cl = heal.load_checklist(root)
    answers, faults = [], []
    for q, v in cl.items():
        if kind not in v["applies"]:
            continue
        hit = next((n for n in no if n[0] == q), None)
        if hit:
            fid = f"F-{len(faults) + 1:03d}"
            answers.append({"q": q, "answer": "no", "evidence": evidence, "fault": fid})
            faults.append({"id": fid, "q": q, "severity": hit[1], "frame": 12, "evidence": evidence, "description": f"fault in {q}"})
        else:
            answers.append({"q": q, "answer": "yes", "evidence": evidence})
    sc = heal.compute_score(faults) if score is None else score
    return {"target": "x", "kind": kind, "checklist_version": 1, "critic_model": "sonnet", "answers": answers, "faults": faults, "score": sc, "verdict": "pass" if sc >= 9 else "fail"}


def put_critic(d, critic):
    (d / "heal").mkdir(exist_ok=True)
    (d / "heal" / "critic.json").write_text(json.dumps(critic), encoding="utf-8")


# ------------------------------------------------------------------ the real data files
def test_checklist_covers_every_f_note_and_every_question_maps_to_a_class():
    cl = heal.load_checklist(REPO)
    pbs = heal.load_playbooks(REPO)
    assert len(cl) >= 50
    maps = " ".join(v["maps"] for v in cl.values())
    for n in range(1, 16):
        assert re.search(rf"\bF{n}\b", maps), f"F{n} has no checklist question"
    for q, v in cl.items():
        assert v["severity"] in heal.SEV_ORDER, q
        assert v["applies"] <= set(heal.KINDS), q
        assert heal.class_for_question(q, pbs) is not None, f"{q} maps to no playbook class"


def test_every_check_id_of_the_craft_table_classifies():
    pbs = heal.load_playbooks(REPO)
    text = (REPO / "bible/craft/README.md").read_text(encoding="utf-8")
    ids = set()
    for line in text.splitlines():
        if re.match(r"\| F\d+ \|", line):
            ids |= set(re.findall(r"\b[A-Z][A-Z0-9]+(?:-[A-Z0-9*]+)+\b", line.split("|")[-2]))
    ids = {i for i in ids if not i.startswith("R-")}
    assert len(ids) > 40
    for i in sorted(ids):
        pb = heal.match_class(i, pbs)
        assert pb is not None and pb["class"] != "UNKNOWN", i


def test_playbook_classes_are_unique_and_have_a_fixer():
    pbs = heal.load_playbooks(REPO)
    names = [p["class"] for p in pbs]
    assert len(names) == len(set(names)) >= 25
    assert names[-1] == "UNKNOWN"
    assert all(p["fixer"] == "sonnet" for p in pbs)


@sw_fixtures.needs_project("kb/lessons/ledger.jsonl (your own lessons ledger)", "kb/lessons/ledger.jsonl")
def test_seeded_ledger_is_complete():
    rows = heal.read_jsonl(REPO / "kb/lessons/ledger.jsonl")
    classes = {p["class"] for p in heal.load_playbooks(REPO)}
    assert len(rows) >= 30
    assert {f"F{n}" for n in range(1, 16)} <= {r["fault"] for r in rows}
    for r in rows:
        for k in ("id", "date", "build", "fault", "class", "root_cause", "fix", "rule", "check", "status"):
            assert r.get(k), (r.get("id"), k)
        assert r["class"] in classes, r["id"]
    assert len({r["id"] for r in rows}) == len(rows)


def test_heal_json_is_the_setting():
    cfg = heal.load_config(REPO)
    assert cfg["enabled"] is True
    assert cfg["critic"]["min_score"] == 9 and cfg["critic"]["model"] == "sonnet" and {cfg["fixer"][k] for k in ("creative_model","tool_model","helper_model")} == {"sonnet"}
    assert cfg["on_budget_exhausted"]["loosen_gates"] is False and cfg["on_budget_exhausted"]["show_owner_unhealed_as_done"] is False
    assert {"loosen_threshold", "edit_trace", "hide_from_camera"} <= set(cfg["forbidden_fix_kinds"])
    assert "tools/qg_checks.py" in cfg["protected_paths"]["frozen"]


def test_stage_tools_are_wired():
    assert '"heal"' in (TOOLS / "compose.py").read_text(encoding="utf-8")
    assert '"heal"' in (TOOLS / "artbook.py").read_text(encoding="utf-8")
    assert "heal.prepare" in (TOOLS / "shot.py").read_text(encoding="utf-8")


# ------------------------------------------------------------------ classify
def test_classify_maps_gate_failures_to_classes(root):
    d = shot_dir(root, {"hands": ["HAND-SWAP"], "rig": ["SEAM-CROSS", "RIG-SHOULDER"], "extras": ["REND-TEXT-TEXTURE"],
                        "render": ["motion_coverage"], "preview": ["PLAYBACK-VIDEO"], "look2d": ["LOOK2D-LINE"]})
    res = heal.classify(d, "shot", root)
    got = {f["check"]: f["class"] for f in res["faults"]}
    assert got == {"HAND-SWAP": "HANDS", "SEAM-CROSS": "SEAM", "RIG-SHOULDER": "SHOULDER", "REND-TEXT-TEXTURE": "TEXT",
                   "motion_coverage": "MOTION-LIGHT-DEPTH", "PLAYBACK-VIDEO": "PLAYBACK", "LOOK2D-LINE": "LOOK2D"}
    f = next(x for x in res["faults"] if x["check"] == "HAND-SWAP")
    assert f["fixer"] == "sonnet" and "catalogue" in f["fix_in"] and f["rerun_from"] == "build"
    assert next(x for x in res["faults"] if x["check"] == "PLAYBACK-VIDEO")["fixer"] == "sonnet"
    assert not res["ready_for_owner"]
    assert (d / "heal" / "classified.json").is_file()


def test_exact_id_beats_wildcard_and_unknown_falls_back(root):
    pbs = heal.load_playbooks(root)
    assert heal.match_class("TRANS-AUDIO", pbs)["class"] == "EPISODE-AUDIO"
    assert heal.match_class("TRANS-RATE", pbs)["class"] == "TRANSITION"
    assert heal.match_class("ATT-LAYERS", pbs)["class"] == "LAYERS"
    assert heal.match_class("ATT-FINGERS", pbs)["class"] == "ATTACH"
    assert heal.match_class("ZZZ-NEVER-SEEN", pbs) is None
    d = shot_dir(root, {"rig": ["ZZZ-NEVER-SEEN"]})
    res = heal.classify(d, "shot", root)
    assert res["faults"][0]["class"] == "UNKNOWN"


def test_missing_or_incomplete_gate_is_a_fault(root):
    d = root / "work" / "shots" / "empty"
    d.mkdir(parents=True)
    (d / "shot.json").write_text("{}", encoding="utf-8")
    assert heal.classify(d, "shot", root)["faults"][0]["check"] == "GATE-INPUT"
    d2 = shot_dir(root, gates=("spec", "rig"), name="partial")
    res = heal.classify(d2, "shot", root)
    assert {f["check"] for f in res["faults"]} == {"GATE-INCOMPLETE"}
    assert {f["class"] for f in res["faults"]} == {"GATE-BLIND"}


def test_episode_and_artbook_reports(root):
    ep = root / "work" / "episodes" / "E01"
    (ep / "gate").mkdir(parents=True)
    (ep / "gate" / "report.json").write_text(json.dumps({"complete": False, "checks": [
        {"id": "EP-HOOK", "status": "fail", "detail": "late"}, {"id": "EP-LENGTH", "status": "pass", "detail": ""}]}), encoding="utf-8")
    res = heal.classify(ep, None, root)
    assert res["kind"] == "episode"
    assert {f["check"]: f["class"] for f in res["faults"]} == {"EP-HOOK": "EPISODE-PLAN", "GATE-INCOMPLETE": "GATE-BLIND"}
    ab = root / "work" / "artbook"
    (ab / "gate").mkdir(parents=True)
    (ab / "gate" / "artbook.out").write_text("FAIL [ARTBOOK-MATCH] hero sheet 3 differs\nPASS ARTBOOK-INK\nFAIL ARTBOOK-MATCH (1)\n", encoding="utf-8")
    res = heal.classify(ab, None, root)
    assert res["kind"] == "artbook"
    assert [(f["check"], f["class"]) for f in res["faults"]] == [("ARTBOOK-MATCH", "ARTBOOK-SHEET")]


# ------------------------------------------------------------------ critic and rubric
def test_rubric_calibration():
    assert heal.compute_score([]) == 10
    assert heal.compute_score([{"severity": "S4"}]) == 10
    assert heal.compute_score([{"severity": "S3"}] * 2) == 8            # 9.0 but capped by S3
    assert heal.compute_score([{"severity": "S2"}] * 4 + [{"severity": "S3"}]) == 6   # Mix v2
    assert heal.compute_score([{"severity": "S1"}, {"severity": "S2"}]) == 4          # Mix v3
    assert heal.compute_score([{"severity": "S4"}] * 4) == 9


def test_validate_critic(root):
    c = make_critic(root)
    assert heal.validate_critic(c, "shot", root) == ([], 10)
    c = make_critic(root, no=[("CQ-H4", "S2")])
    assert heal.validate_critic(c, "shot", root) == ([], 6)
    inflated = make_critic(root, no=[("CQ-H4", "S2")], score=9)
    errs, eff = heal.validate_critic(inflated, "shot", root)
    assert any("higher than the rubric" in e for e in errs) and eff == 6
    missing = make_critic(root)
    missing["answers"].pop()
    assert any("not answered" in e for e in heal.validate_critic(missing, "shot", root)[0])
    noev = make_critic(root, no=[("CQ-H4", "S2")])
    noev["answers"][[a["q"] for a in noev["answers"]].index("CQ-H4")].pop("fault")
    assert any("matching fault" in e for e in heal.validate_critic(noev, "shot", root)[0])
    low = make_critic(root, no=[("CQ-H4", "S4")])      # CQ-H4 is S2 in the checklist: a critic may not demote it
    assert any("lower than the checklist" in e for e in heal.validate_critic(low, "shot", root)[0])


def test_ready_needs_gates_critic_and_score(root):
    d = shot_dir(root)
    assert not heal.classify(d, "shot", root)["ready_for_owner"]          # no critic yet
    put_critic(d, make_critic(root))
    res = heal.classify(d, "shot", root)
    assert res["ready_for_owner"] and res["score"] == 10
    put_critic(d, make_critic(root, no=[("CQ-F6", "S4")] ))               # one polish fault: 10, still ready (S4 does not block)
    assert heal.classify(d, "shot", root)["ready_for_owner"]
    put_critic(d, make_critic(root, no=[("CQ-F1", "S3")]))                # an S3 caps at 8
    res = heal.classify(d, "shot", root)
    assert not res["ready_for_owner"] and res["score"] == 8 and res["faults"][0]["class"] == "FACE-FEATURES"
    d2 = shot_dir(root, {"hands": ["HAND-TOPO"]}, name="s2")
    put_critic(d2, make_critic(root))
    assert not heal.classify(d2, "shot", root)["ready_for_owner"]          # a perfect critic cannot override a failing gate


def test_prepare_writes_briefs_and_respects_disabled(root):
    d = shot_dir(root, {"hands": ["HAND-TOPO"]})
    msgs = []
    res = heal.prepare(d, "shot", root, log=msgs.append)
    assert res["faults"] and (d / "heal" / "critic-brief.md").is_file() and (d / "heal" / "fix-brief.md").is_file()
    brief = (d / "heal" / "critic-brief.md").read_text(encoding="utf-8")
    assert "CQ-H1" in brief and "CQ-A1" not in brief                      # artbook-only question absent from a shot brief
    fb = (d / "heal" / "fix-brief.md").read_text(encoding="utf-8")
    assert "HAND-TOPO" in fb and "loosen_threshold" in fb
    cfg = json.loads((root / "pipelines/heal.json").read_text(encoding="utf-8"))
    cfg["enabled"] = False
    (root / "pipelines/heal.json").write_text(json.dumps(cfg), encoding="utf-8")
    assert heal.prepare(d, "shot", root, log=msgs.append) is None


# ------------------------------------------------------------------ rounds and budget
def faulty(root, name="r"):
    d = shot_dir(root, {"hands": ["HAND-SWAP"], "rig": ["SEAM-CROSS"]}, name=name)
    heal.classify(d, "shot", root, now=1000.0)
    return d


def test_round_is_recorded_with_its_class(root):
    d = faulty(root)
    rec = heal.record_round(d, "G-002", "authored the left grip", "catalogue", ["catalogue/characters/hero/v2/grips.json"], "fixed", root=root, now=1100.0)
    assert rec["class"] == "HANDS" and rec["check"] == "HAND-SWAP" and rec["round"] == 1
    assert heal.rounds(d)[0]["files"] == ["catalogue/characters/hero/v2/grips.json"]
    st = heal.status(d, root, now=1100.0)
    assert st["records"] == 1 and st["max_rounds"] == 3 and len(st["open_faults"]) == 2


def test_max_rounds_then_stop_and_report(root):
    d = faulty(root)
    for i in range(3):
        heal.record_round(d, "G-001", f"try {i}", "scene", [], "failed", new_round=i > 0, root=root, now=1100.0 + i)
    with pytest.raises(heal.HealRefused) as e:
        heal.record_round(d, "G-001", "try 4", "scene", [], "failed", new_round=True, root=root, now=1200.0)
    assert e.value.code == 3 and "never loosen" in e.value.msg
    stopped = (d / "heal" / "STOPPED.md").read_text(encoding="utf-8")
    assert "BLOCKED" in stopped and "HAND-SWAP" in stopped and "SEAM-CROSS" in stopped and "No gate was loosened" in stopped
    assert len(heal.rounds(d)) == 3
    assert heal.status(d, root, now=1300.0)["stopped"] is True


def test_time_and_token_budget_stop(root):
    d = faulty(root, "t")
    over_minutes = 1000.0 + 181 * 60
    with pytest.raises(heal.HealRefused) as e:
        heal.record_round(d, "G-001", "late", "scene", [], "pending", root=root, now=over_minutes)
    assert e.value.code == 3 and "time budget" in e.value.msg
    d2 = faulty(root, "k")
    heal.record_round(d2, "G-001", "big", "scene", [], "failed", tokens=3_900_000, root=root, now=1100.0)
    with pytest.raises(heal.HealRefused) as e:
        heal.record_round(d2, "G-002", "more", "scene", [], "failed", tokens=200_000, root=root, now=1101.0)
    assert e.value.code == 3 and "token budget" in e.value.msg


def test_dispatch_cap(root):
    cfg = json.loads((root / "pipelines/heal.json").read_text(encoding="utf-8"))
    cfg["max_heal_rounds"]["default"] = 99
    cfg["max_heal_rounds"]["shot"] = 99
    cfg["budget"]["max_fix_dispatches_per_build"] = 2
    (root / "pipelines/heal.json").write_text(json.dumps(cfg), encoding="utf-8")   # before the snapshot: heal.json is frozen once a heal starts
    d = faulty(root, "dc")
    heal.record_round(d, "G-001", "a", "scene", [], "failed", root=root, now=1100.0)
    heal.record_round(d, "G-001", "b", "scene", [], "failed", new_round=True, root=root, now=1101.0)
    with pytest.raises(heal.HealRefused) as e:
        heal.record_round(d, "G-001", "c", "scene", [], "failed", new_round=True, root=root, now=1102.0)
    assert e.value.code == 3


# ------------------------------------------------------------------ the forbidden-fix guard
@pytest.mark.parametrize("kind", ["loosen_threshold", "edit_trace", "hide_from_camera", "skip_check", "widen_exemption", "edit_approved_version", "hand_edit_output"])
def test_forbidden_fix_kinds_are_refused(root, kind):
    d = faulty(root, "fk-" + kind)
    with pytest.raises(heal.HealRefused) as e:
        heal.record_round(d, "G-001", "x", kind, [], "fixed", root=root, now=1100.0)
    assert e.value.code == 4
    assert heal.rounds(d) == []


def test_declaring_a_threshold_file_or_a_trace_is_refused(root):
    d = faulty(root, "decl")
    for f in ("tools/qg_checks.py", "tools/quality_gate.py", "kb/quality/rig-trace.schema.json", "reference/mix-v5/rig.out", "pipelines/heal.json"):
        with pytest.raises(heal.HealRefused) as e:
            heal.record_round(d, "G-001", "x", "shared_code", [f], "fixed", root=root, now=1100.0)
        assert e.value.code == 4, f
    with pytest.raises(heal.HealRefused) as e:
        heal.record_round(d, "G-001", "x", "scene", [str(d / "out" / "rig-trace.json")], "fixed", root=root, now=1100.0)
    assert e.value.code == 4


def test_a_changed_threshold_is_caught_by_the_snapshot(root):
    d = faulty(root, "thr")
    assert heal.guard(d, root) == []
    q = root / "tools" / "qg_checks.py"
    q.write_text("THRESHOLD = 0.20\n", encoding="utf-8")       # loosened to make the gate pass
    bad = heal.guard(d, root)
    assert bad and "qg_checks.py" in bad[0]
    with pytest.raises(heal.HealRefused) as e:
        heal.record_round(d, "G-001", "innocent-looking fix", "scene", ["scene/main.js"], "fixed", root=root, now=1100.0)
    assert e.value.code == 4 and "qg_checks.py" in e.value.msg
    assert heal.main(["guard", str(d), "--root", str(root)]) == 4


def test_a_hand_edited_trace_is_caught_but_a_regenerated_one_is_not(root):
    d = shot_dir(root, name="trace")
    (d / "out").mkdir()
    tr = d / "out" / "rig-trace.json"
    tr.write_text('{"frames": 1}', encoding="utf-8")
    now = time.time()
    (d / "STATE.json").write_text(json.dumps({"stages": {"trace": {"status": "ok", "at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now - 3600))}}}), encoding="utf-8")
    heal.snapshot(d, root)
    assert heal.guard(d, root) == []
    tr.write_text('{"frames": 2}', encoding="utf-8")            # edited by hand: newer than the last stage record
    bad = heal.guard(d, root)
    assert bad and "edited by hand" in bad[0]
    # the same change, but the stage re-ran afterwards and says so
    (d / "STATE.json").write_text(json.dumps({"stages": {"trace": {"status": "ok", "at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() + 60))}}}), encoding="utf-8")
    assert heal.guard(d, root) == []


def test_reference_files_are_frozen(root):
    d = faulty(root, "ref")
    (root / "reference" / "mix-v5" / "rig.out").write_text("FAIL\n", encoding="utf-8")
    assert any("reference/mix-v5/rig.out" in b for b in heal.guard(d, root))


def _git(root, *a):
    import subprocess
    subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", *a], check=True, capture_output=True)


def test_frozen_guard_compares_against_head_not_the_snapshot(root):
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    d = faulty(root, "head")
    assert heal.guard(d, root) == []
    # an uncommitted edit to a frozen file during the heal is refused
    f = root / "tools" / "qg_checks.py"
    f.write_text("THRESHOLD = 0.10\n", encoding="utf-8")
    bad = heal.guard(d, root)
    assert bad and "tools/qg_checks.py" in bad[0] and "uncommitted" in bad[0]
    with pytest.raises(heal.HealRefused):
        heal.record_round(d, "G-001", "x", "scene", [], "failed", root=root, now=1100.0)
    # the Lead commits that change: HEAD now holds it, the guard no longer sees a violation
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "lead change")
    assert heal.guard(d, root) == []
    # a deleted frozen file is still refused
    f.unlink()
    assert any("removed" in b and "tools/qg_checks.py" in b for b in heal.guard(d, root))


# ------------------------------------------------------------------ learn
def test_learn_appends_healed_faults_only_and_is_idempotent(root):
    d = faulty(root, "lrn")
    heal.record_round(d, "G-002", "authored the left grip over 6 frames", "catalogue", ["catalogue/x.json"], "fixed", root=root, now=1100.0)
    heal.record_round(d, "G-001", "tried thinner lines", "shared_code", [], "failed", new_round=True, root=root, now=1101.0)
    r = heal.learn(d, "lrn-build", root, "2026-10-24")
    assert len(r["added"]) == 1 and r["proposals"] == []
    rows = heal.read_jsonl(heal.ledger_path(root))
    e = rows[0]
    assert e["id"] == "L-0001" and e["class"] == "HANDS" and e["check"] == "HAND-SWAP" and e["rule"] == "R-383..R-386"
    assert e["build"] == "lrn-build" and e["fix_kind"] == "catalogue" and e["date"] == "2026-10-24" and e["status"] == "healed"
    assert heal.learn(d, "lrn-build", root)["added"] == []
    assert len(heal.read_jsonl(heal.ledger_path(root))) == 1


def test_unknown_fault_writes_a_proposal(root):
    d = shot_dir(root, {"rig": ["ZZZ-NEVER-SEEN"]}, name="unk")
    heal.classify(d, "shot", root, now=1000.0)
    heal.record_round(d, "G-001", "found the real cause in the tracer and fixed it there", "shared_code", [], "fixed", root=root, now=1100.0)
    r = heal.learn(d, "unk", root, "2026-10-24")
    assert len(r["proposals"]) == 1
    p = root / r["proposals"][0]
    text = p.read_text(encoding="utf-8")
    assert p.parent.name == "proposals" and "New rule text" in text and "New check design" in text and "Test idea" in text
    e = heal.read_jsonl(heal.ledger_path(root))[0]
    assert e["class"] == "UNKNOWN" and e["proposal"] == r["proposals"][0]


def test_new_critic_fault_writes_a_proposal(root):
    d = shot_dir(root, name="newf")
    c = make_critic(root)
    c["faults"] = [{"id": "F-001", "q": "NEW", "severity": "S3", "frame": 40, "evidence": "frame 40: the jar floats", "description": "a prop floats above the desk"}]
    c["score"] = heal.compute_score(c["faults"])
    put_critic(d, c)
    res = heal.classify(d, "shot", root, now=1000.0)
    assert res["faults"][0]["class"] == "UNKNOWN" and res["faults"][0]["question"] == "NEW"
    heal.record_round(d, "F-001", "added a contact and a shadow for the jar", "spec", [], "fixed", root=root, now=1100.0)
    assert len(heal.learn(d, "newf", root)["proposals"]) == 1


def test_gate_blind_fault_also_writes_a_proposal(root):
    d = shot_dir(root, gates=("spec", "rig"), name="blind")
    heal.classify(d, "shot", root, now=1000.0)
    heal.record_round(d, "G-001", "ran every gate", "tool", [], "fixed", root=root, now=1100.0)
    assert len(heal.learn(d, "blind", root)["proposals"]) == 1


# ------------------------------------------------------------------ cli
def test_cli_exit_codes(root, capsys):
    d = shot_dir(root, {"hands": ["HAND-SWAP"], "rig": ["SEAM-CROSS"]}, name="cli")
    heal.classify(d, "shot", root)
    assert heal.main(["status", str(d), "--root", str(root)]) == 1
    assert heal.main(["round", str(d), "--root", str(root), "--fault", "G-001", "--fix", "x", "--fix-kind", "loosen_threshold"]) == 4
    assert heal.main(["round", str(d), "--root", str(root), "--fault", "G-001", "--fix", "x", "--fix-kind", "catalogue", "--result", "fixed"]) == 0
    assert heal.main(["learn", str(d), "--root", str(root)]) == 0
    assert heal.main(["critic-brief", str(d), "--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert "REFUSED" in out and "round 1 recorded" in out
    put_critic(d, make_critic(root))
    assert heal.main(["validate-critic", str(d), "--root", str(root), "--kind", "shot"]) == 0
