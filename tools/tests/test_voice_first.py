"""E01 run-1 process fixes: voice first (SPEC-VOICE-TIMING, PLAN-VOICE-OFFSET), captions only in compose (PIECE-NO-CAPTION), per-actor frame ranges
(ACTOR-RANGE, TRACE-INCOMPLETE per actor), the live end card, and the parallax estimator's summary (confidence, interval).
New check ids: SPEC-VOICE-TIMING, PLAN-VOICE-OFFSET, PIECE-NO-CAPTION, ACTOR-RANGE."""
import copy, json, shutil, wave, struct
from pathlib import Path

import pytest

import qg_checks as qc
import quality_gate as qg
from conftest import REPO
from multi_actor_fixture import two_spec, two_trace
from shotlib import presence, voicetiming


def ids(f): return qc.ids_of(f)


def write_wav(path, secs, rate=8000):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(struct.pack("<h", 0) * int(secs * rate))


def voice_root(tmp, lines):
    """tmp/work/voice/E01/<line>.trimmed.wav + visemes/<line>.json for {line: seconds}."""
    for lid, secs in lines.items():
        write_wav(tmp / "work" / "voice" / "E01" / f"{lid}.trimmed.wav", secs)
        v = tmp / "work" / "voice" / "E01" / "visemes" / f"{lid}.json"
        v.parent.mkdir(parents=True, exist_ok=True)
        v.write_text(json.dumps({"format": "viseme-track/1", "line": lid, "fps": 24, "duration_s": secs, "keys": [{"t": 0.0, "id": "V0"}, {"t": 0.1, "id": "V4"}, {"t": secs - 0.2, "id": "V0"}]}), encoding="utf-8")
    return tmp


def piece_spec(duration=6.0, lines=None, episode="E01", refs=("L01",)):
    sp = {"fps": 24, "voice_episode": episode, "voice_lines": lines if lines is not None else [{"line": "L01", "start_s": 0.5, "speaker": "hero"}],
          "beats": [{"id": "b1", "start": 0.0, "end": duration, "emotion_track": {"voice": {"line": r}}} for r in refs[:1]]}
    return sp


# ---------------------------------------------------------------- 1. voice first
def test_resolve_fills_measured_timing_and_visemes_on_the_piece_clock(tmp_path):
    voice_root(tmp_path, {"L01": 3.0})
    sp = voicetiming.resolve(piece_spec(), tmp_path)
    e = sp["voice_lines"][0]
    assert e["dur_s"] == 3.0 and e["end_s"] == 3.5 and e["take"].endswith("L01.trimmed.wav") and e["spans_in"] is False
    assert [k["t"] for k in e["viseme_keys"]] == [0.5, 0.6, 3.3]            # track t + start_s
    assert qc.check_voice_timing(sp, tmp_path, True) == []


def test_missing_take_fails_spec_voice_timing_for_every_line(tmp_path):
    voice_root(tmp_path, {"L01": 3.0})
    sp = piece_spec(lines=[{"line": "L01", "start_s": 0.5}, {"line": "L02", "start_s": 4.0}, {"line": "L03", "start_s": 5.0}])
    with pytest.raises(voicetiming.VoiceTimingError) as e:
        voicetiming.resolve(sp, tmp_path)
    assert len(e.value.problems) == 2 and "L02" in e.value.problems[0] and "estimate" in e.value.problems[0]


def test_missing_viseme_track_fails_unless_off_screen(tmp_path):
    voice_root(tmp_path, {"L01": 2.0})
    (tmp_path / "work/voice/E01/visemes/L01.json").unlink()
    with pytest.raises(voicetiming.VoiceTimingError):
        voicetiming.resolve(piece_spec(), tmp_path)
    ok = voicetiming.resolve(piece_spec(lines=[{"line": "L01", "start_s": 0.5, "visemes": False}]), tmp_path)
    assert ok["voice_lines"][0]["dur_s"] == 2.0 and "viseme_keys" not in ok["voice_lines"][0]


def test_line_that_outruns_the_piece_fails_unless_spans_out(tmp_path):
    voice_root(tmp_path, {"L01": 7.0})
    with pytest.raises(voicetiming.VoiceTimingError) as e:
        voicetiming.resolve(piece_spec(duration=6.0), tmp_path)
    assert "lengthen the piece" in e.value.problems[0]
    sp = voicetiming.resolve(piece_spec(duration=6.0, lines=[{"line": "L01", "start_s": 0.5, "spans_out": True}]), tmp_path)
    assert qc.check_voice_timing(sp, tmp_path, True) == []


def test_check_catches_stale_unresolved_and_unreferenced_lines(tmp_path):
    voice_root(tmp_path, {"L01": 3.0})
    sp = voicetiming.resolve(piece_spec(), tmp_path)
    stale = copy.deepcopy(sp); write_wav(tmp_path / "work/voice/E01/L01.trimmed.wav", 4.0)
    assert ids(qc.check_voice_timing(stale, tmp_path, True)) == {"SPEC-VOICE-TIMING"}        # the voice changed after the spec was resolved
    raw = piece_spec()                                                                       # never resolved: no measured dur_s
    assert any("measured dur_s" in m for m in qc.check_voice_timing(raw, tmp_path, True))
    unref = copy.deepcopy(sp); unref["voice_lines"] = []
    assert any("L01" in m and "does not reference" in m for m in qc.check_voice_timing(unref, tmp_path, True))


def test_spec_without_voice_first_fields_is_untouched():
    assert qc.check_voice_timing({"beats": [{"id": "b1", "start": 0, "end": 3, "emotion_track": {"voice": {"line": "L9"}}}]}) == []


# ---------------------------------------------------------------- 2. captions only in compose
def text(**kw):
    t = {"id": "t1", "string": "بطاقة", "lang": "ar", "box": {"x": 100, "y": 600, "w": 400, "h": 120}, "layer": "top", "plate": "opaque-flat", "min_contrast": 7.0,
         "height_px": 52, "read_time_s": 1.5, "t0": 0.0, "t1": 3.0}
    t.update(kw)
    return t


@pytest.mark.parametrize("kw", [{"role": "caption"}, {"plate": "caption-bar"}, {"speaker": "hero"}, {"role": "caption", "diegetic": True}])
def test_dialogue_captions_are_refused_in_a_piece(kw):
    sp = {"fps": 24, "beats": [{"id": "b1", "start": 0, "end": 3, "texts": [text(**kw)]}]}
    assert "PIECE-NO-CAPTION" in ids(qc.piece_caption_issues(sp)) and "PIECE-NO-CAPTION" in ids(qc.check_texts(sp))


def test_diegetic_text_stays_allowed():
    sp = {"fps": 24, "beats": [{"id": "b1", "start": 0, "end": 3, "texts": [text(role="main"), text(id="t2", plate="caption-bar", diegetic=True)]}]}
    assert qc.piece_caption_issues(sp) == []


def test_reference_specs_are_exempt_from_the_new_rule(tmp_path):
    d = tmp_path / "reference" / "old"; d.mkdir(parents=True)
    sp = json.loads((REPO / "kb/quality/shot-spec.example.json").read_text(encoding="utf-8"))
    sp["beats"][0]["texts"] = [text(role="caption", plate="caption-bar")]
    (d / "shot-spec.json").write_text(json.dumps(sp), encoding="utf-8")
    import subprocess, sys
    r = subprocess.run([sys.executable, str(REPO / "tools/quality_gate.py"), "spec", str(d / "shot-spec.json")], capture_output=True, text=True, encoding="utf-8")
    assert "PIECE-NO-CAPTION" not in r.stdout


# ---------------------------------------------------------------- 3. per-actor frame ranges
def test_presence_helpers():
    a = {"id": "x", "present": [[0, 30], [60, 90]]}
    assert presence.frames(a, 96)[:2] == [0, 1] and len(presence.frames(a, 96)) == 60
    assert presence.mask_frames(a, 96) == [0, 6, 12, 18, 24, 60, 66, 72, 78, 84]
    assert presence.present_at(a, 75, 96) and not presence.present_at(a, 45, 96)
    assert presence.frames({"id": "y"}, 10) == list(range(10))
    assert presence.problems([[0, 30], [20, 40]], 96) and presence.problems([[0, 99]], 96) and presence.problems([], 96) and presence.problems([[3, 3]], 96)
    assert presence.problems([[0, 30], [30, 40]], 96) == []


def make_masks(root, actor, frames):
    for kind in ("shadow", "line"):
        for f in frames:
            p = root / kind / actor / f"{f:04d}.png"; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(b"x")


def test_trace_accepts_an_actor_that_enters_late_and_one_that_exits(tmp_path):
    nf = 60
    actors = [{"id": "a", "present": [[0, 36]]}, {"id": "b", "present": [[24, 60]]}]
    chars = {"a": {"frames": [{"f": f} for f in range(0, 36)]}, "b": {"frames": [{"f": f} for f in range(24, 60)]}}
    make_masks(tmp_path, "a", presence.mask_frames(actors[0], nf)); make_masks(tmp_path, "b", presence.mask_frames(actors[1], nf))
    assert presence.trace_issues(chars, actors, nf, tmp_path) == []


def test_trace_refuses_undeclared_absence_and_missing_masks(tmp_path):
    nf = 60
    actors = [{"id": "a"}, {"id": "b", "present": [[24, 60]]}]
    chars = {"a": {"frames": [{"f": f} for f in range(0, 50)]}, "b": {"frames": [{"f": f} for f in range(24, 60)]}}     # a vanishes at 50 without saying so
    make_masks(tmp_path, "a", range(0, 60, 6)); make_masks(tmp_path, "b", [24, 30, 36, 42, 48])                       # b lacks the mask of frame 54
    msgs = presence.trace_issues(chars, actors, nf, tmp_path)
    assert any("actor a traced 50 frames, declared present on 60" in m and "missing 50-59" in m for m in msgs)
    assert any("actor b lacks 1 of 6 shadow masks (frames 54)" in m for m in msgs)


def test_trace_still_demands_every_frame_when_nothing_is_declared(tmp_path):
    chars = {"solo": {"frames": [{"f": f} for f in range(10)]}}
    assert presence.trace_issues(chars, None, 12) != []
    assert presence.trace_issues({"solo": {"frames": [{"f": f} for f in range(12)]}}, None, 12) == []


def test_spec_actor_ranges_must_cover_the_beats_that_show_the_actor():
    sp = two_spec(); nf = qc._spec_frames(sp)
    assert nf > 0
    ok = copy.deepcopy(sp)
    for a in ok["actors"]:
        a["frames"] = [[0, nf]]
    assert "ACTOR-RANGE" not in ids(qc.check_actors(ok))
    bad = copy.deepcopy(sp)
    bad["actors"][1]["frames"] = [[nf // 2, nf]]                      # the partner enters half way but every beat still lists him
    assert "ACTOR-RANGE" in ids(qc.check_actors(bad))
    worse = copy.deepcopy(sp); worse["actors"][0]["frames"] = [[0, nf + 5]]
    assert "ACTOR-RANGE" in ids(qc.check_actors(worse))


def test_trace_must_match_the_spec_ranges():
    sp, tr = two_spec(), two_trace()
    nf = len(tr["scene"]["frames"])
    sp2 = copy.deepcopy(sp)
    for a in sp2["actors"]:
        a["frames"] = [[0, nf]]
    assert "ACTOR-RANGE" not in ids(qc.rig_actors(tr, sp2))
    sp2["actors"][0]["frames"] = [[0, nf - 3]]                        # the spec says the actor leaves 3 frames before the trace does
    assert "ACTOR-RANGE" in ids(qc.rig_actors(tr, sp2))


# ---------------------------------------------------------------- 5. parallax estimator
def test_parallax_summary_reports_spread_interval_and_marginal_flag():
    s = qg.parallax_summary([0.30, 0.34, 0.28, 0.31, 0.29, 0.33, 0.32, 0.30, 0.31, 0.29, 0.33, 0.30, 0.32, 0.31, 0.30, 0.29], 96, 20)
    assert s["parallax_corr"] == pytest.approx(0.305, abs=0.01) and s["parallax_samples"] == 16 and s["parallax_candidates"] == 96 and s["parallax_valid"] == 20
    assert s["parallax_conf"] > 0.9 and s["parallax_marginal"] is False and s["parallax_ci95"][0] > 0.28
    m = qg.parallax_summary([0.02, 0.19, 0.08, 0.12, 0.05, 0.16, 0.09, 0.11], 96, 8)      # median 0.10: the verdict could flip on another sample set
    assert m["parallax_marginal"] is True and m["parallax_conf"] < s["parallax_conf"]
    none = qg.parallax_summary([], 96, 0)
    assert none["parallax_corr"] == 0.0 and none["parallax_conf"] == 0.0 and none["parallax_marginal"] is True


def test_parallax_threshold_is_unchanged():
    assert ("parallax_corr", ">=", 0.10) == next(g[:3] for g in qg.DEPTH_GATES if g[0] == "parallax_corr")
    assert qg.PAR["samples"] >= 24 and qg.PAR["candidates"] > qg.PAR["samples"]
    assert any("parallax_corr" in f for f in qg.evaluate({"depth_bands": 5, "parallax_corr": 0.098}, True))
    assert not any("parallax_corr" in f for f in qg.evaluate({"depth_bands": 5, "parallax_corr": 0.101}, True))


# ---------------------------------------------------------------- compose: voice-first offsets and the live end card
import compose
from test_compose import J, env, go, make_repo, run_all, sh   # noqa: F401  (env is a fixture)


def spec_for(repo, sid, entries):
    (repo / "work/shots" / sid / "shot-spec.json").write_text(json.dumps({"voice_episode": "E01", "voice_lines": entries}), encoding="utf-8")


def shotlist(repo):
    return repo / "bible/series/ser/episodes/E01/shotlist.json"


def test_compose_takes_the_offset_from_the_piece_spec(tmp_path, env):
    repo = make_repo(tmp_path, voiced=True)
    spec_for(repo, "s1", [{"line": "l1", "start_s": 1.25, "dur_s": 2.0}])
    sl = J(shotlist(repo)); del sl["shots"][0]["lines"][0]["at_s"]; shotlist(repo).write_text(json.dumps(sl, ensure_ascii=False), encoding="utf-8")
    assert go(repo, "plan", "E01") == 0
    ln = next(l for l in J(repo / "work/episodes/E01/plan.json")["lines"] if l["id"] == "l1")
    assert ln["start"] == 1.25 and ln["offset_source"] == "shot spec voice_lines" and ln["timing_source"] == "take"


def test_plan_voice_offset_fails_on_disagreement_stale_take_or_no_offset(tmp_path, env, capsys):
    repo = make_repo(tmp_path, voiced=True)
    spec_for(repo, "s1", [{"line": "l1", "start_s": 3.0, "dur_s": 2.0}])             # shotlist says at_s 1.0
    capsys.readouterr()
    assert go(repo, "plan", "E01") == 1 and "PLAN-VOICE-OFFSET" in capsys.readouterr().out
    spec_for(repo, "s1", [{"line": "l1", "start_s": 1.0, "dur_s": 3.1}])             # the piece was timed on a 3.1 s take, the take is 2.0 s
    assert go(repo, "plan", "E01", "--force") == 1 and "re-run `shot.py spec`" in capsys.readouterr().out
    spec_for(repo, "s1", [])
    sl = J(shotlist(repo)); del sl["shots"][0]["lines"][0]["at_s"]; shotlist(repo).write_text(json.dumps(sl, ensure_ascii=False), encoding="utf-8")
    assert go(repo, "plan", "E01", "--force") == 1 and "no at_s" in capsys.readouterr().out


def test_end_card_is_laid_over_live_footage_by_default(tmp_path, env):
    repo = make_repo(tmp_path)
    assert run_all(repo) == 0
    w = repo / "work/episodes/E01"
    e = J(w / "end/end.json")
    assert e["backdrop"] == "live-loop" and e["loop_s"] == 1.5 and (w / "end/overlay.png").is_file() and e["scrim_rgba"][3] == 0.8
    from PIL import Image
    assert Image.open(w / "end/overlay.png").mode == "RGBA"
    assert abs(compose.duration(w / "episode.mp4") - (compose.duration(w / "assembled.mp4") + 3.0)) < 0.2


def test_live_loop_over_a_still_tail_fails_but_live_hold_and_static_pass(tmp_path, env, capsys):
    repo = make_repo(tmp_path)
    still = tmp_path / "still.mp4"
    sh("ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=0x445566:s=270x480:r=24:d=11", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", still)
    shutil.copy(still, repo / "work/shots/s3/out/s3.mp4")
    capsys.readouterr()
    assert run_all(repo) == 1 and "backdrop does not move" in capsys.readouterr().out
    for mode in ("live-hold", "static"):
        sl = J(shotlist(repo)); sl["end_card"]["backdrop"] = mode; shotlist(repo).write_text(json.dumps(sl, ensure_ascii=False), encoding="utf-8")
        assert go(repo, "end", "E01", "--force") == 0 and go(repo, "gate", "E01", "--skip-render-gate", "--force") == 0, mode
        assert J(repo / "work/episodes/E01/end/end.json")["backdrop"] == mode


def test_unknown_backdrop_is_refused(tmp_path, env, capsys):
    repo = make_repo(tmp_path)
    for st in ("plan", "audio", "captions", "assemble"):
        assert go(repo, st, "E01") == 0
    sl = J(shotlist(repo)); sl["end_card"]["backdrop"] = "blur"; shotlist(repo).write_text(json.dumps(sl, ensure_ascii=False), encoding="utf-8")
    capsys.readouterr()
    assert go(repo, "end", "E01") == 1
