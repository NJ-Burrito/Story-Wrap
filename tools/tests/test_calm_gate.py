"""Calm format gate (qg_checks.CALM, check_calm_render / check_calm_shot / check_calm_declared, compose gate profile).
Pure checks on numbers and dicts: no video, no GPU. The calibration against the real reels lives in kb/quality/gate-spec.md section H."""
import json
from pathlib import Path

import qg_checks as qc

REPO = Path(__file__).resolve().parents[2]


def mid(band):
    lo, hi = band
    return (lo + hi) / 2 if lo is not None and hi is not None else (lo if lo is not None else hi)


def good_metrics():
    C = qc.CALM
    return {"shot_len_s": mid(C["shot_len_s"]), "cuts_per_min": mid(C["cuts_per_min"]), "freeze_share_05s": mid(C["hold_share"]),
            "longest_hold_s": mid(C["longest_hold_s"]), "motion_coverage": mid(C["motion_coverage"]), "motion_clusters": mid(C["motion_clusters"]),
            "has_audio": True, "audio_active": 0.93, "loudness_i": -14.1, "lra": 3.6}


def ids(fails):
    return {x.split("[")[1].split("]")[0] for x in fails}


def test_format_of():
    assert qc.format_of({"format": "calm"}) == "calm"
    assert qc.format_of({"format": "shotlist/1", "profile": "calm"}) == "calm"   # the shotlist's own `format` is the schema id
    assert qc.format_of({"format": "shotlist/1"}) == "premium"
    assert qc.format_of({}) == "premium" and qc.format_of(None) == "premium" and qc.format_of({"format": "weird"}) == "premium"


def test_every_band_is_calibrated_not_open():
    for k in ("shot_len_s", "cuts_per_min", "hold_share", "longest_hold_s", "motion_coverage", "motion_clusters", "audio_active", "loudness_i", "lra"):
        assert qc.CALM[k] != (None, None), f"{k} was never calibrated"


def test_good_calm_metrics_pass():
    assert qc.check_calm_render(good_metrics()) == []


def test_restless_and_fast_fail():
    m = good_metrics()
    m.update(shot_len_s=1.4, cuts_per_min=40.2, freeze_share_05s=0.0, motion_coverage=0.75, motion_clusters=17.5)   # E01 run 1 numbers
    assert {"CALM-SHOTLEN", "CALM-CUTRATE", "CALM-HOLDS", "CALM-MOTION", "CALM-SUBJECTS"} <= ids(qc.check_calm_render(m))


def test_a_dead_or_stalled_video_fails_the_other_side():
    m = good_metrics()
    m.update(motion_coverage=0.0, freeze_share_05s=0.9, longest_hold_s=30.0, shot_len_s=40.0)
    assert {"CALM-MOTION", "CALM-HOLDS", "CALM-HOLD-LONGEST", "CALM-SHOTLEN"} <= ids(qc.check_calm_render(m))


def test_missing_metric_fails_never_skips():
    m = good_metrics(); del m["motion_coverage"]
    assert "CALM-MOTION" in ids(qc.check_calm_render(m))


def test_audio_gates():
    m = good_metrics(); m["has_audio"] = False
    assert "CALM-VOICE-COVERAGE" in ids(qc.check_calm_render(m))
    m = good_metrics(); m.update(lra=7.8)
    assert "CALM-LRA" in ids(qc.check_calm_render(m))
    m = good_metrics(); m.update(loudness_i=-20.0)
    assert "CALM-LOUDNESS" in ids(qc.check_calm_render(m))
    m = good_metrics(); m.update(audio_active=0.4)
    assert "CALM-VOICE-COVERAGE" in ids(qc.check_calm_render(m))


def test_shot_check_only_ceilings():
    m = {"motion_coverage": 0.0, "motion_clusters": 0.0}
    assert qc.check_calm_shot(m) == []                       # a still shot is a hold, not a fault, at shot level
    assert ids(qc.check_calm_shot({"motion_coverage": 0.9, "motion_clusters": 30})) == {"CALM-MOTION", "CALM-SUBJECTS"}


# ---- declared data
def plates(words=1, n=6, font=140, gap=0.0):
    return {"captions": [{"line": f"L{i}", "text": " ".join(["كلمة"] * words), "start": i * 0.5, "end": i * 0.5 + 0.5 - gap, "font_px_1080": font} for i in range(n)]}


def wrapper(total=60.0):
    return {"recap": {"t0": 0, "t1": 2.2}, "day_card": {"t0": 10, "t1": 12}, "choice_card": {"t0": total - 8, "t1": total - 3}, "follow_card": {"t0": total - 3, "t1": total}}


def plan(total=60.0, cover=1.0):
    return {"lines": [{"id": "L01", "start": 0.0, "dur": total * cover}]}


END = {"choices": [{"id": "1"}, {"id": "2"}]}


def declared(**kw):
    total = kw.pop("total", 60.0)
    a = dict(plan=plan(total), caps=plates(), end=END, sl={"wrapper": wrapper(total), "shots": [{"id": "S1", "subjects": ["clerk"]}]})
    a.update(kw)
    return qc.check_calm_declared(a["plan"], a["caps"], a["end"], a["sl"], total)


def test_declared_good_passes():
    assert declared() == []


def test_caption_style():
    assert "CALM-CAPTION-STYLE" in ids(declared(caps=plates(words=9)))                 # more than a clause: 9 words
    assert declared(caps=plates(words=7)) == []                                        # C7 (2026-10-25): a whole sentence of 7 words is the calm caption now
    assert "CALM-CAPTION-STYLE" in ids(declared(caps={"captions": [{**c, "n_lines": 3} for c in plates(words=4)["captions"]]}))   # three lines
    assert "CALM-CAPTION-STYLE" in ids(declared(caps=plates(gap=-0.2)))                # two plates on screen at once
    assert "CALM-CAPTION-STYLE" in ids(declared(caps=plates(font=52)))                 # E01 plate size
    assert "CALM-CAPTION-STYLE" in ids(declared(caps={"captions": []}))
    assert declared(caps=plates(words=3)) == []


def test_narrator_cover():
    assert "CALM-VOICE-COVERAGE" in ids(declared(plan=plan(cover=0.67)))                     # E01 run 1: 0.67
    assert "CALM-VOICE-COVERAGE" in ids(declared(plan={"lines": []}))


def test_wrapper():
    for gone in ("recap", "day_card", "choice_card", "follow_card"):
        w = wrapper(); del w[gone]
        assert "CALM-WRAPPER" in ids(declared(sl={"wrapper": w, "shots": []})), gone
    assert "CALM-WRAPPER" in ids(declared(sl={"shots": []}))
    w = wrapper(); w["recap"] = {"t0": 5, "t1": 8}
    assert "CALM-WRAPPER" in ids(declared(sl={"wrapper": w, "shots": []}))             # recap not in the first 3 s
    w = wrapper(); w["choice_card"] = {"t0": 20, "t1": 25}
    assert "CALM-WRAPPER" in ids(declared(sl={"wrapper": w, "shots": []}))             # choice card not in the last 20 s


def test_recaps_start_at_the_declared_episode_and_the_first_episode_opens_on_its_story():
    w = wrapper(); del w["recap"]
    e1 = {"wrapper": w, "shots": [], "episode_no": 1, "recap_from": 2}
    assert "CALM-WRAPPER" not in ids(declared(sl=e1))                                   # E01: no vote, no recap card (the owner 2026-10-25)
    assert "CALM-WRAPPER" in ids(declared(sl={**e1, "episode_no": 2}))                  # E02 without a recap fails as before
    assert "CALM-WRAPPER" in ids(declared(sl={"wrapper": w, "shots": []}))              # nothing declared: the recap stays required
    assert "CALM-WRAPPER" in ids(declared(sl={**e1, "wrapper": wrapper()}))             # E01 may not declare one either
    w = wrapper(); w["follow_card"] = {"t0": 30, "t1": 33}
    assert "CALM-WRAPPER" in ids(declared(sl={"wrapper": w, "shots": []}))             # follow before choice
    assert "CALM-WRAPPER" in ids(declared(end={"choices": [{"id": "1"}]}))             # one choice only


def test_subjects_per_shot():
    assert "CALM-SUBJECTS" in ids(declared(sl={"wrapper": wrapper(), "shots": [{"id": "S1", "subjects": ["a", "b"]}]}))


def test_e01_run_1_declared_data_fails_where_it_is_uncomfortable():
    r = REPO / "work" / "episodes" / "E01"
    if not (r / "plan.json").is_file():
        return                                                                          # work/ is git-ignored: only where the run exists
    p, c, e = (json.loads((r / n).read_text(encoding="utf-8")) for n in ("plan.json", "captions.json", "end/end.json"))
    f = qc.check_calm_declared(p, c, e, {"shots": []}, p["total_s"])
    assert {"CALM-CAPTION-STYLE", "CALM-VOICE-COVERAGE", "CALM-WRAPPER"} <= ids(f)


def test_premium_thresholds_untouched():
    import quality_gate as qg
    assert dict(qg.SPEC_GATES)["max_hold_s"] == 0.8 and dict(qg.SPEC_GATES)["max_hold_share"] == 0.10
    prem = {k: (op, thr) for k, op, thr, _ in qg.RENDER_GATES}
    assert prem["motion_coverage"] == (">=", 0.50) and prem["freeze_share_05s"] == ("<=", 0.03)


# ---- compose.py gate selects the profile from the shotlist (uses the synthetic episode of test_compose.py)
def test_compose_gate_calm_profile(tmp_path, monkeypatch, capsys):
    import test_compose as tc
    for k, v in (("NJ_COMPOSE_CPU", "1"), ("NJ_COMPOSE_STUB_PLATES", "1"), ("NJ_COMPOSE_ALLOW_STUB", "1")):
        monkeypatch.setenv(k, v)
    repo = tc.make_repo(tmp_path)
    assert tc.run_all(repo) == 0                                          # premium: passes, its report says so
    assert tc.J(repo / "work/episodes/E01/gate/report.json")["format"] == "premium"
    tc.edit(repo, lambda sl, sc: sl.update(profile="calm"))
    capsys.readouterr()
    assert tc.go(repo, "plan", "E01", "--force") == 0 and tc.go(repo, "gate", "E01", "--skip-render-gate", "--force") == 1
    out = capsys.readouterr().out
    rep = tc.J(repo / "work/episodes/E01/gate/report.json")
    assert rep["format"] == "calm"
    for cid in ("CALM-WRAPPER", "CALM-VOICE-COVERAGE"):
        assert f"FAIL  [{cid}]" in out, cid
    assert "[EP-LENGTH]" in out and "calm format" in out                  # length is the story's, not 30-60 s


# ---- declared transitions: the detector reads a flash/whoosh/ink as many scene changes (E01C: 60 changes for 22 items)
def e01c_like(n=22, item_s=4.5, join=0.25):
    items, t = [], 0.0
    for i in range(n):
        items.append({"id": f"i{i}", "t0": round(t, 4), "t1": round(t + item_s, 4)})
        t += item_s - join
    return {"items": items}, round(items[-1]["t1"], 4)


def test_declared_pacing_ignores_detector_hits_inside_declared_transitions():
    tl, dur = e01c_like()
    bd = qc.declared_boundaries(tl)
    assert len(bd) == 21
    hits = [t for b in bd for t in (b["a"] + 0.05, b["t"], b["b"] - 0.05)]     # three detector hits inside every transition
    m = qc.declared_pacing(tl, dur, hits, [])
    assert m["undeclared_changes"] == 0 and m["ignored_in_transitions"] == 63 and m["declared_cuts"] == 21
    assert m["shot_len_s"] == round(dur / 22, 2)
    assert qc.check_calm_render({**good_metrics(), **{k: m[k] for k in ("shot_len_s", "cuts_per_min", "longest_hold_s")}}) == []


def test_declared_pacing_still_counts_a_change_nobody_declared():
    tl, dur = e01c_like()
    bd = qc.declared_boundaries(tl)
    stray = [(bd[3]["b"] + bd[4]["a"]) / 2 + i * 0.1 for i in range(8)]       # eight real cuts in the middle of one shot
    m = qc.declared_pacing(tl, dur, stray, [])
    assert m["undeclared_changes"] == 8 and m["scene_changes"] == 29 and m["shortest_shot_s"] <= 0.15
    many = [i * 1.0 for i in range(1, 99)]                                    # a restless video: a cut a second, nothing declared there
    r = qc.declared_pacing({"items": [{"id": "a", "t0": 0.0, "t1": 99.0}]}, 99.0, many, [])
    assert r["undeclared_changes"] == 98 and r["shot_len_s"] == 1.0
    assert {"CALM-SHOTLEN", "CALM-CUTRATE"} <= ids(qc.check_calm_render({**good_metrics(), **{k: r[k] for k in ("shot_len_s", "cuts_per_min")}}))


def test_declared_pacing_holds_are_measured_per_shot_outside_the_windows():
    tl, dur = e01c_like(n=4, item_s=5.0)
    bd = qc.declared_boundaries(tl)
    w0 = bd[0]
    m = qc.declared_pacing(tl, dur, [], [(1.0, 4.0)])
    assert m["freeze_holds_05s"] == 1 and m["longest_hold_s"] == 3.0 and m["transition_s"] > 0
    assert abs(m["freeze_share_05s"] - 3.0 / (dur - m["transition_s"])) < 1e-3          # the denominator leaves the windows out
    m2 = qc.declared_pacing(tl, dur, [], [(w0["a"] - 0.3, w0["b"] + 0.2)])               # a freeze the window cuts under 0.5 s is no hold
    assert m2["freeze_holds_05s"] == 0


def test_declared_pacing_counts_the_choice_sequence_inner_cuts():
    tl = {"items": [{"id": "a", "t0": 0.0, "t1": 5.0}, {"id": "choice", "t0": 4.75, "t1": 17.5, "split": {"cuts": [{"t": 1.66}, {"t": 3.12}, {"t": 5.83}]}}]}
    assert [b["kind"] for b in qc.declared_boundaries(tl)] == ["join", "inner", "inner", "inner"]
    assert qc.declared_pacing(tl, 17.5, [], [])["declared_cuts"] == 4
