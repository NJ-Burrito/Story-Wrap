"""Adopting an approved, gated episode (tools/adopt.py) so the Post task can publish it without a rebuild. The E01C folder is the neutral fixture under tests/fixtures/project."""
import json
import os
import shutil
from pathlib import Path

import pytest

import adopt
import daily
import ig
import sw_fixtures

REPO_ROOT = Path(__file__).resolve().parents[2]
EP = "E01C"


def make_root(tmp_path, verdict="PASS", score=9, complete=True, fail_check=False, gate_older=False):
    """A repo copy: the fixture E01C folder (find_ep, build_caption) and a fake gated work folder."""
    root = tmp_path / "repo"
    shutil.copytree(sw_fixtures.SERIES / "episodes" / EP, root / "bible" / "series" / "series" / "episodes" / EP)
    w = root / "work" / "episodes" / EP
    (w / "gate").mkdir(parents=True)
    (w / "heal").mkdir()
    (w / "episode.mp4").write_bytes(b"\x00video" * 50)
    checks = [{"id": f"C{i}", "status": "pass"} for i in range(29)] + ([{"id": "CALM-X", "status": "fail"}] if fail_check else [])
    (w / "gate" / "report.json").write_text(json.dumps({"episode": EP, "verdict": verdict, "complete": complete, "checks": checks}), encoding="utf-8")
    (w / "heal" / "critic.json").write_text(json.dumps({"score": score}), encoding="utf-8")
    t = (w / "episode.mp4").stat().st_mtime
    os.utime(w / "gate" / "report.json", (t - 100, t - 100) if gate_older else (t + 100, t + 100))
    return root, w


@pytest.fixture(autouse=True)
def no_tokens(monkeypatch):
    monkeypatch.setattr(daily, "token_exists", lambda root: False)       # this machine has real tokens; the publish stage must end as a clean "skipped"
    monkeypatch.setattr(daily, "fb_token_exists", lambda root: False)


def ctx_for(root):
    return daily.Ctx(EP, root=root, config={}, budget=daily.Budget(root, limit=1000, today="2026-10-25"), log=lambda *a: None)


def test_without_adoption_the_post_stage_is_refused(tmp_path):
    root, w = make_root(tmp_path)
    c = ctx_for(root)
    assert daily.run_list(c, ["publish"]) != 0                       # UPSTREAM-NOT-VERIFIED: script, voice ... are not fresh
    assert "publish" not in c.state["stages"]


def test_adopt_records_hashes_and_lets_the_post_stages_run(tmp_path):
    root, w = make_root(tmp_path)
    rec = adopt.adopt(EP, "the owner", "approved reference, calm v5 with the NJ mark, gate 29/29", root)
    assert rec["gate_report_sha256"] == adopt.sha256(w / "gate" / "report.json") and rec["episode_sha256"] == adopt.sha256(w / "episode.mp4")
    assert rec["approved_by"] == "the owner" and rec["gate_checks"] == 29 and rec["critic_score"] == 9
    assert json.loads((root / "work" / "daily" / "adoptions.jsonl").read_text(encoding="utf-8").splitlines()[-1])["episode"] == EP
    assert adopt.valid(EP, root) and adopt.problems(EP, root) == []
    c = ctx_for(root)
    assert daily.run_list(c, ["publish"]) == 0 and c.state["stages"]["publish"]["status"] == "skipped"
    # the run stages are NOT marked done: the adoption skips their check, it does not forge their state
    assert not any(n in c.state["stages"] for n in daily.RUN_STAGES)


def test_adoption_does_not_skip_the_gates_of_the_post_stages(tmp_path):
    root, w = make_root(tmp_path)
    adopt.adopt(EP, "the owner", "approved reference E01C", root)
    (w / "heal" / "critic.json").write_text(json.dumps({"score": 5}), encoding="utf-8")
    c = ctx_for(root)
    assert daily.run_list(c, ["publish"]) != 0                         # publish_gates still run (and valid() also fails: critic below 9)
    assert adopt.problems(EP, root)


@pytest.mark.parametrize("what", ["episode", "gate"])
def test_a_changed_file_voids_the_adoption(tmp_path, what):
    root, w = make_root(tmp_path)
    adopt.adopt(EP, "the owner", "approved reference E01C", root)
    f = w / ("episode.mp4" if what == "episode" else "gate/report.json")
    f.write_bytes(f.read_bytes() + b" ") if what == "episode" else f.write_text(f.read_text(encoding="utf-8").replace('"complete": true', '"complete": true '), encoding="utf-8")
    assert not adopt.valid(EP, root) and any("changed" in p for p in adopt.problems(EP, root))
    assert daily.run_list(ctx_for(root), ["publish"]) != 0


@pytest.mark.parametrize("kw,code", [({"verdict": "FAIL"}, "ADOPT-GATES"), ({"complete": False}, "ADOPT-GATES"), ({"score": 8}, "ADOPT-GATES"), ({"fail_check": True}, "ADOPT-GATES"),
                                     ({"gate_older": True}, "ADOPT-STALE-GATE")])
def test_adopt_refuses_unless_the_gate_passed_on_this_file(tmp_path, kw, code):
    root, w = make_root(tmp_path, **kw)
    with pytest.raises(SystemExit) as e:
        adopt.adopt(EP, "the owner", "approved reference E01C", root)
    assert code in str(e.value) and not adopt.rec_path(EP, root).exists()


def test_adopt_refuses_a_missing_gate_report_a_video_a_name_a_reason_and_a_posted_episode(tmp_path):
    root, w = make_root(tmp_path)
    for who, why, code in (("", "approved reference E01C", "ADOPT-WHO"), ("the owner", "short", "ADOPT-WHY")):
        with pytest.raises(SystemExit) as e:
            adopt.adopt(EP, who, why, root)
        assert code in str(e.value)
    (w / "post.json").write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        adopt.adopt(EP, "the owner", "approved reference E01C", root)
    assert "ADOPT-POSTED" in str(e.value)
    (w / "post.json").unlink()
    (w / "gate" / "report.json").unlink()
    with pytest.raises(SystemExit) as e:
        adopt.adopt(EP, "the owner", "approved reference E01C", root)
    assert "ADOPT-GATES" in str(e.value)


def test_revoke_and_status_cli(tmp_path, monkeypatch, capsys):
    root, w = make_root(tmp_path)
    monkeypatch.setattr(adopt, "REPO", root)
    adopt.adopt(EP, "the owner", "approved reference E01C", root)
    assert adopt.revoke(EP, root) and not adopt.valid(EP, root) and not adopt.revoke(EP, root)


def test_other_episodes_are_never_affected(tmp_path):
    root, w = make_root(tmp_path)
    adopt.adopt(EP, "the owner", "approved reference E01C", root)
    assert not adopt.valid("E02", root)


def test_the_real_e01c_files_find_ep_and_build_caption(tmp_path):
    root, w = make_root(tmp_path)
    ep = ig.find_ep(EP, root)
    assert ep.name == EP and (ep / "caption.txt").is_file()
    cap = ig.build_caption(EP, root)
    assert cap.splitlines()[0].startswith("الحلقة ١ | the series 🧳") and not ig.caption_problems(cap, "instagram")
    adopt.adopt(EP, "the owner", "approved reference E01C", root)
    assert ig.publish_gates(EP, root) == []                          # exactly what ig.py publish and daily's publish stage check
    assert ig.cmd_publish(EP, go=False, repo=root)["caption"] == cap


# ------------------------------------------------------------------ the caps guard building, not posting
def adopted_ctx(tmp_path, go, cap_used_s=None, tokens=None, run_proc=None):
    root, w = make_root(tmp_path) if not (tmp_path / "repo").exists() else (tmp_path / "repo", tmp_path / "repo/work/episodes/E01C")
    if not adopt.rec_path(EP, root).exists():
        adopt.adopt(EP, "the owner", "approved reference E01C", root)
    c = daily.Ctx(EP, root=root, config={"go": go}, budget=daily.Budget(root, limit=1000, today="2026-10-25"), log=lambda *a: None, run_proc=run_proc)
    if cap_used_s is not None:
        c.deadline["machine_s"] = cap_used_s
    if tokens is not None:
        c.budget.data["tokens"] = tokens
    return c, root


def fake_proc(calls):
    def run(cmd, **kw):
        calls.append(cmd[2:])
        return subprocess_result("DRY RUN (add --go to post). Gates clear. Caption:\nنص\n" if "--go" not in cmd else "POSTED E01C: x\n")
    return run


def subprocess_result(out):
    import subprocess
    return subprocess.CompletedProcess([], 0, out, "")


def test_an_adopted_episode_posts_even_when_the_render_cap_and_the_token_cap_are_spent(tmp_path, monkeypatch):
    monkeypatch.setattr(daily, "token_exists", lambda root: True)
    monkeypatch.setattr(daily, "fb_token_exists", lambda root: True)
    calls = []
    c, root = adopted_ctx(tmp_path, False, cap_used_s=4.32 * 3600, tokens=283038, run_proc=fake_proc(calls))
    assert c.remaining() < 0
    (c.dir / "STATE.json").write_text(json.dumps({"episode": EP, "stages": {"voice": {"status": "failed", "check": "VOICE-MANUAL"}, "critic": {"status": "failed", "check": "PLAN-CHOICE"}}}), encoding="utf-8")
    c = daily.Ctx(EP, root=root, config={"go": False}, budget=c.budget, log=lambda *a: None, run_proc=fake_proc(calls))
    c.deadline["machine_s"] = 4.32 * 3600
    assert daily.run_list(c, daily.POST_STAGES[:1]) == 0                      # publish, dry run: reaches the stage despite the spent cap and the stale failed stages
    assert [x[0].split("\\")[-1].split("/")[-1] for x in calls] == ["ig.py", "fb.py"] and all(x[1:3] == ["publish", EP] and "--go" not in x for x in calls)


def test_an_unadopted_episode_is_still_stopped_by_the_render_cap(tmp_path, monkeypatch):
    root, w = make_root(tmp_path)
    c = daily.Ctx(EP, root=root, config={}, budget=daily.Budget(root, limit=1000, today="2026-10-25"), log=lambda *a: None)
    c.deadline["machine_s"] = 5 * 3600
    with pytest.raises(daily.StageFail) as e:
        daily.run_stage(c, daily.STAGES["publish"])
    assert e.value.code == "RENDER-CAP"
    (root / "work" / "episodes" / EP / "heal" / "critic.json").write_text(json.dumps({"score": 9}), encoding="utf-8")
    adopt.adopt(EP, "the owner", "approved reference E01C", root)
    assert daily.run_stage(c, daily.STAGES["publish"]) == "skipped"             # adopted: the same spent cap no longer blocks the post stage
    c2 = daily.Ctx(EP, root=root, config={}, budget=c.budget, log=lambda *a: None)
    c2.deadline["machine_s"] = 5 * 3600
    with pytest.raises(daily.StageFail):                                        # a BUILD stage of the same adopted episode is still capped
        c2.check_cap("compose")


def test_a_dry_run_does_not_mark_publish_done_for_the_real_run(tmp_path, monkeypatch):
    """Found while checking the dry run: a dry run ended the publish stage as 'skipped', which stage_state counts as done, so the next --go run would skip the post."""
    monkeypatch.setattr(daily, "token_exists", lambda root: True)
    monkeypatch.setattr(daily, "fb_token_exists", lambda root: False)
    calls = []
    c, root = adopted_ctx(tmp_path, False, run_proc=fake_proc(calls))
    assert daily.run_list(c, ["publish"]) == 0 and len(calls) == 1 and "--go" not in calls[0]
    c2 = daily.Ctx(EP, root=root, config={"go": True}, budget=c.budget, log=lambda *a: None, run_proc=fake_proc(calls))
    assert daily.run_list(c2, ["publish"]) == 0
    assert len(calls) == 2 and "--go" in calls[1]                                # the real run really posts


def test_the_whole_post_path_of_an_adopted_episode_runs_as_a_dry_run(tmp_path, monkeypatch):
    monkeypatch.setattr(daily, "token_exists", lambda root: True)
    monkeypatch.setattr(daily, "fb_token_exists", lambda root: True)
    calls = []
    c, root = adopted_ctx(tmp_path, False, cap_used_s=5 * 3600, run_proc=fake_proc(calls))
    assert daily.run_list(c, daily.POST_STAGES) == 0                         # publish, schedule, yt_stories: all reached, nothing posted
    assert [x[0].split("\\")[-1] for x in calls] == ["ig.py", "fb.py"] and not (root / "work/episodes/E01C/post.json").exists()
