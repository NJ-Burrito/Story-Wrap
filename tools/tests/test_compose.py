"""tools/compose.py: unit tests and an end-to-end run on tiny synthetic fixtures (test-pattern clips, sine audio, 270x480).
Plates are drawn by the test stub unless Chrome + playwright + the Thmanyah fonts are present (then one extra test uses the real engine).
Run: uv run --no-project --with pytest --with numpy --with pillow --with scipy --with jsonschema --with playwright pytest tools/tests/test_compose.py -q"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

import compose

SOURCE_REPO = Path(__file__).resolve().parents[2]


def sh(*cmd):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stderr[-500:]


def sine(path, secs, freq=330, rate=24000, ch=1, amp=0.25):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    sh("ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", f"sine=frequency={freq}:sample_rate={rate}:duration={secs}",
       "-af", f"volume={amp}", "-ac", ch, "-c:a", "pcm_s16le", path)


LINES = [("l1", "hero", "أَيْنَ الحَقِيبَةُ؟"), ("l2", "guide", "ضَاعَتْ فِي يَوْمٍ لَمْ يَأْتِ بَعْدُ."), ("l3", "hero", "سَأَجِدُهَا.")]


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("NJ_COMPOSE_CPU", "1")
    monkeypatch.setenv("NJ_COMPOSE_STUB_PLATES", "1")
    monkeypatch.setenv("NJ_COMPOSE_ALLOW_STUB", "1")


def make_repo(tmp, voiced=False, with_music=True, shot_s=11, licence="OWN"):
    repo = tmp / "repo"
    ep = repo / "bible" / "series" / "ser" / "episodes" / "E01"
    ep.mkdir(parents=True)
    (ep / "script.json").write_text(json.dumps({"series": "ser", "episode": "E01", "lines": [
        {"id": i, "speaker": s, "emotion": "calm", "text": t, "tts_text": t} for i, s, t in LINES]}, ensure_ascii=False), encoding="utf-8")
    base = tmp / "base.mp4"
    sh("ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc2=s=270x480:r=24:d={shot_s}", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", base)
    n = int(shot_s * 24)
    shots = []
    for k, sid in enumerate(["s1", "s2", "s3"]):
        d = repo / "work" / "shots" / sid / "out"
        d.mkdir(parents=True)
        shutil.copy(base, d / f"{sid}.mp4")
        shots.append({"id": sid, "folder": f"work/shots/{sid}", "in_frame": 0, "out_frame": n, "beat": f"b{k}",
                      "lines": [{"line": LINES[k][0], "at_s": 1.0, "est_dur_s": 2.0, "visible_in": [sid]}], "faces": [{"t0": 0, "t1": 3, "box": [60, 100, 200, 250]}]})
    (repo / "work" / "shots" / "s2" / "shot-spec.json").write_text(json.dumps({"beats": [{"id": "b1", "emotion_track": {"sfx": [
        {"at_s": 3.0, "what": "door click"}, {"at_s": 5.0, "what": "unmapped thing"}]}}]}), encoding="utf-8")
    (repo / "assets" / "audio").mkdir(parents=True)
    shutil.copy(Path(__file__).parent / "fixtures" / "LICENCES.header.md", repo / "assets" / "audio" / "LICENCES.md")
    sine(repo / "assets/audio/bed.wav", 40, 220, 48000, 2, 0.5)
    sine(repo / "assets/audio/click.wav", 0.3, 1200, 48000, 2, 0.5)
    sl = {"format": "shotlist/1", "episode": "E01", "fps": 24, "canvas": [270, 480],
          "hook": {"event": "the bag lands on the counter", "at_s": 0.5}, "shots": shots,
          "transitions": [{"from": "s1", "to": "s2", "type": "fade", "frames": 12}, {"from": "s2", "to": "s3", "type": "cut", "frames": 0}],
          "sfx_map": {"door click": {"file": "assets/audio/click.wav", "licence_id": "click1"}},
          "end_card": {"duration_s": 3.0, "question_ar": "ماذا تفعل هُدى؟", "choices": [{"id": "A", "text_ar": "تفتح الحقيبة"}, {"id": "B", "text_ar": "تُعيدها إلى الرف"}],
                       "comment_prompt_ar": "اكتب أ أو ب في التعليقات"}}
    if with_music:
        sl["music"] = {"file": "assets/audio/bed.wav", "licence_id": "bed1"}
    (ep / "shotlist.json").write_text(json.dumps(sl, ensure_ascii=False), encoding="utf-8")
    for fid, fl, kind in (("bed1", "assets/audio/bed.wav", "music"), ("click1", "assets/audio/click.wav", "sfx")):
        lic = licence if fid == "bed1" else "OWN"
        if lic in compose.LICENCES:
            assert compose.main(["licence-add", "--id", fid, "--file", fl, "--kind", kind, "--licence", lic, "--source", "synthesised in tests", "--retrieved", "2026-10-23"], repo) == 0
        else:       # the tool refuses NC/ND, so a hand-edited register row is what the audio stage must catch
            with open(repo / "assets/audio/LICENCES.md", "a", encoding="utf-8") as fh:
                fh.write(f"| {fid} | {fl} | {kind} | {lic} |  | http://x | 2026-10-23 | |" + chr(10))
    if voiced:
        for i, _, _ in LINES:
            sine(repo / "work" / "voice" / "E01" / f"{i}.wav", 2.0)
    return repo


def go(repo, *args):
    return compose.main([*args], repo)


def J(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


# ------------------------------------------------------------------ unit tests
def test_timeline_overlap_math():
    sl = {"fps": 24, "shots": [{"id": "a", "in_frame": 0, "out_frame": 240}, {"id": "b", "in_frame": 0, "out_frame": 240}, {"id": "c", "in_frame": 0, "out_frame": 120}],
          "transitions": [{"from": "a", "to": "b", "type": "fade", "frames": 12}, {"from": "b", "to": "c", "type": "cut", "frames": 0}], "end_card": {"duration_s": 3}}
    t = compose.timeline(sl)
    assert [s["start"] for s in t["shots"]] == [0.0, 9.5, 19.5]
    assert t["picture_s"] == 24.5 and t["total_s"] == 27.5


def test_estimate_and_letters():
    assert compose.ar_letters("هُدى abc 12") == 3
    assert compose.estimate_seconds("") == 0.8
    assert compose.estimate_seconds("س" * 24) == pytest.approx(2.25)


def test_contrast_values():
    assert compose.contrast((255, 255, 255), (0, 0, 0)) == pytest.approx(21.0)
    assert compose.contrast((120, 120, 120), (128, 128, 128)) < 1.2


def test_safe_rect_and_inside():
    r = compose.safe_rect((1080, 1920))
    assert r == pytest.approx((54.0, 268.8, 1026.0, 1248.0))
    assert compose.inside([100, 300, 900, 1200], r)
    assert not compose.inside([100, 100, 900, 1200], r)
    assert not compose.inside([100, 300, 900, 1400], r)


def test_licence_register_rules(tmp_path):
    reg = tmp_path / "L.md"
    reg.write_text("| id | file | kind | licence | credit | source | retrieved | sha256 |\n|---|---|---|---|---|---|---|---|\n"
                   "| a | a.wav | music | CC0 |  | http://x | 2026-10-23 | |\n| b | b.wav | music | CC-BY |  | http://x | 2026-10-23 | |\n"
                   "| c | c.wav | music | CC-BY-NC |  | http://x | 2026-10-23 | |\n| d | d.wav | sfx | CC-BY | Name, title, CC BY 4.0 | http://x | 2026-10-23 | |\n"
                   "| e | e.wav | sfx | CC0 |  |  |  | |\n", encoding="utf-8")
    r = compose.parse_licences(reg)
    assert set(r) == {"a", "b", "c", "d", "e"}
    assert compose.licence_problem(r, "a") is None
    assert "credit" in compose.licence_problem(r, "b")
    assert "not allowed" in compose.licence_problem(r, "c")
    assert compose.licence_problem(r, "d") is None
    assert "source" in compose.licence_problem(r, "e")
    assert "not in" in compose.licence_problem(r, "zzz")


@pytest.mark.skipif(not (SOURCE_REPO / "assets" / "audio" / "LICENCES.md").is_file(), reason="needs your own project data: assets/audio/LICENCES.md (your sound licence register)")
def test_real_register_rows_are_all_usable():
    """The real register is filled (the music bed was licensed, so 'empty' no longer holds): every row has an allowed licence, a source and a date."""
    reg = compose.parse_licences(SOURCE_REPO / "assets" / "audio" / "LICENCES.md")
    assert all(compose.licence_problem(reg, lid) is None for lid in reg)


def test_licence_sha_mismatch(tmp_path):
    f = tmp_path / "a.wav"
    f.write_bytes(b"abc")
    r = {"a": {"licence": "CC0", "credit": "", "source": "u", "retrieved": "d", "sha256": "deadbeefdeadbeef"}}
    assert "sha256" in compose.licence_problem(r, "a", f)


def test_measure_loudness_parses_ebur128(tmp_path):
    f = tmp_path / "t.wav"
    sine(f, 4, 1000, 48000, 2, 1.0)
    m = compose.measure_loudness(f)
    assert -30 < m["integrated_lufs"] < -15 and m["true_peak_dbtp"] < -15


def test_licence_add_refuses_nc(tmp_path):
    repo = tmp_path / "r"
    (repo / "assets/audio").mkdir(parents=True)
    f = repo / "assets/audio/x.wav"
    sine(f, 1)
    assert compose.main(["licence-add", "--id", "x", "--file", "assets/audio/x.wav", "--kind", "sfx", "--licence", "CC-BY-NC", "--source", "u", "--retrieved", "d"], repo) == 1


# ------------------------------------------------------------------ plan
def test_plan_ok_and_state(tmp_path, env, capsys):
    repo = make_repo(tmp_path)
    assert go(repo, "plan", "E01") == 0
    plan = J(repo / "work/episodes/E01/plan.json")
    assert plan["voice_mode"] == "no-voice-yet" and 34 < plan["total_s"] < 36
    assert plan["shots"][1]["start"] == pytest.approx(10.5) and plan["shots"][2]["start"] == pytest.approx(21.5)
    assert [l["start"] for l in plan["lines"]] == [1.0, 11.5, 22.5]
    assert J(repo / "work/episodes/E01/STATE.json")["stages"]["plan"]["status"] == "ok"
    capsys.readouterr()
    assert go(repo, "plan", "E01") == 0 and "skipped" in capsys.readouterr().out


def edit(repo, fn):
    d = repo / "bible/series/ser/episodes/E01"
    sl, sc = J(d / "shotlist.json"), J(d / "script.json")
    fn(sl, sc)
    (d / "shotlist.json").write_text(json.dumps(sl, ensure_ascii=False), encoding="utf-8")
    (d / "script.json").write_text(json.dumps(sc, ensure_ascii=False), encoding="utf-8")


def _overlap(sl, sc):
    sl["shots"][0]["lines"][0].update(at_s=8.0, est_dur_s=2.5)
    sl["shots"][1]["lines"][0].update(at_s=0.0, est_dur_s=2.0)    # shot 2 starts at 10.5; line 1 ends at 10.5 -> touching is fine
    sl["shots"][0]["lines"].append({"line": "l2", "at_s": 9.9, "est_dur_s": 0.6, "visible_in": ["s1"]})
    sl["shots"][1]["lines"] = [{"line": "l3", "at_s": 0.0, "est_dur_s": 2.0, "visible_in": ["s2"]}]
    sl["shots"][2]["lines"] = []


def _same_speaker(sl, sc):
    """Declared overlap between two lines of the SAME speaker is still refused."""
    _overlap(sl, sc)
    sc["lines"][1]["speaker"] = "hero"
    sl["shots"][0]["lines"][0]["overlap_with"] = ["l2"]


def _drop_l2(sl, sc):
    sl["shots"][2]["lines"] = [{"line": "l3", "at_s": 1.0, "visible_in": ["s3"]}]
    sl["shots"][1]["lines"] = []


@pytest.mark.parametrize("mutate,check", [
    (lambda sl, sc: sl["shots"][2].update(lines=[]), "PLAN-LINE-SHOT"),
    (lambda sl, sc: sl["shots"][0]["lines"].append({"line": "nope", "at_s": 3}), "PLAN-LINE-UNKNOWN"),
    (lambda sl, sc: sl["shots"][0]["lines"][0].update(at_s=-1.0), "PLAN-LINE-TIMELINE"),
    (lambda sl, sc: sl["shots"][2]["lines"][0].update(at_s=10.5), "PLAN-LINE-TIMELINE"),       # runs past the end of the picture
    (lambda sl, sc: sl["shots"][0]["lines"][0].pop("visible_in"), "PLAN-LIPSYNC"),            # on screen, no shot carries the visemes
    (lambda sl, sc: sl["shots"][0]["lines"][0].update(visible_in=["s3"]), "PLAN-LIPSYNC"),    # named shot is not playing during the line
    (lambda sl, sc: sl["shots"][0]["lines"][0].update(visible_in=["zz"]), "PLAN-LIPSYNC"),
    (_same_speaker, "PLAN-LINE-OVERLAP"),
    (lambda sl, sc: sl["transitions"].pop(), "PLAN-TRANSITION"),
    (lambda sl, sc: sl["hook"].update(at_s=3.5), "PLAN-HOOK"),
    (lambda sl, sc: sc["lines"][0].update(text="   "), "PLAN-LINE-CAPTION"),
    (lambda sl, sc: [s.update(out_frame=96) for s in sl["shots"]], "PLAN-LENGTH"),
    (lambda sl, sc: sl["shots"][0].update(in_frame=10, out_frame=5), "PLAN-FRAMES"),
    (lambda sl, sc: sl["shots"][1]["lines"].append({"line": "l1", "at_s": 5, "visible_in": ["s2"]}), "PLAN-LINE-DUP"),
    (_overlap, "PLAN-LINE-OVERLAP"),
])
def test_plan_failures(tmp_path, env, capsys, mutate, check):
    repo = make_repo(tmp_path)
    edit(repo, mutate)
    assert go(repo, "plan", "E01") == 1
    assert f"FAIL [{check}]" in capsys.readouterr().out


def test_line_across_a_cut_passes_and_caption_holds(tmp_path, env):
    """L-cut: l1 starts in s1 and ends in s2. Plan passes; its caption is one plate on the episode clock, not clipped at the cut."""
    repo = make_repo(tmp_path)

    def m(sl, sc):
        sl["shots"][0]["lines"][0].update(at_s=9.9, visible_in=["s1", "s2"])
        sl["shots"][1]["lines"][0].update(at_s=2.5)
    edit(repo, m)
    assert go(repo, "plan", "E01") == 0
    l1 = J(repo / "work/episodes/E01/plan.json")["lines"][0]
    assert l1["spans_shots"] == ["s1", "s2"] and [x["shot"] for x in l1["lipsync"]] == ["s1", "s2"]
    assert l1["lipsync"][0]["end"] == pytest.approx(11.0) and l1["lipsync"][1]["start"] == pytest.approx(10.5)
    assert go(repo, "captions", "E01") == 0
    c = J(repo / "work/episodes/E01/captions.json")["captions"][0]
    assert c["start"] == pytest.approx(9.9) and c["end"] == pytest.approx(11.9) and c["spans_shots"] == ["s1", "s2"]
    assert sum(1 for x in J(repo / "work/episodes/E01/captions.json")["captions"] if x["line"] == "l1") == 1


def test_j_cut_negative_at_s_passes(tmp_path, env):
    repo = make_repo(tmp_path)
    edit(repo, lambda sl, sc: sl["shots"][1]["lines"][0].update(at_s=-0.5))   # sound starts in s1, speaker shown in s2
    assert go(repo, "plan", "E01") == 0
    l2 = J(repo / "work/episodes/E01/plan.json")["lines"][1]
    assert l2["start"] == pytest.approx(10.0) and l2["spans_shots"] == ["s1", "s2"] and [x["shot"] for x in l2["lipsync"]] == ["s2"]


def test_declared_overlap_of_two_speakers_passes(tmp_path, env):
    repo = make_repo(tmp_path)
    def m(sl, sc):
        _overlap(sl, sc)
        sl["shots"][0]["lines"][0]["overlap_with"] = ["l2"]
    edit(repo, m)
    assert go(repo, "plan", "E01") == 0


def test_off_screen_line_needs_no_lipsync_shot(tmp_path, env):
    repo = make_repo(tmp_path)
    def m(sl, sc):
        ln = sl["shots"][0]["lines"][0]
        ln.pop("visible_in")
        ln["on_screen"] = False
    edit(repo, m)
    assert go(repo, "plan", "E01") == 0
    l1 = J(repo / "work/episodes/E01/plan.json")["lines"][0]
    assert l1["on_screen"] is False and l1["lipsync"] == []


def test_plan_long_episode_refused(tmp_path, env, capsys):
    repo = make_repo(tmp_path, shot_s=25)
    assert go(repo, "plan", "E01") == 1 and "PLAN-LENGTH" in capsys.readouterr().out


def test_plan_schema_rejects_one_choice(tmp_path, env, capsys):
    repo = make_repo(tmp_path)
    edit(repo, lambda sl, sc: sl["end_card"]["choices"].pop())
    assert go(repo, "plan", "E01") == 1 and "PLAN-SHOTLIST" in capsys.readouterr().out


def test_partial_voice_refused_and_silent_flag(tmp_path, env, capsys):
    repo = make_repo(tmp_path)
    sine(repo / "work/voice/E01/l1.wav", 2.0)
    assert go(repo, "plan", "E01") == 1 and "AUDIO-PARTIAL" in capsys.readouterr().out
    assert go(repo, "plan", "E01", "--silent") == 0


# ------------------------------------------------------------------ audio
def test_audio_no_voice_mode_is_flagged_and_on_target(tmp_path, env):
    repo = make_repo(tmp_path)
    assert go(repo, "plan", "E01") == 0 and go(repo, "audio", "E01") == 0
    a = J(repo / "work/episodes/E01/audio/audio.json")
    assert a["mode"] == "no-voice-yet" and a["banner"] == "NO VOICE YET"
    assert abs(a["loudness"]["integrated_lufs"] - compose.LOUD_TARGET_I) <= compose.LOUD_TOL
    assert a["loudness"]["true_peak_dbtp"] <= compose.LOUD_TP_MAX
    assert [c["file"] for c in a["sfx_cues"]] == ["assets/audio/click.wav"] and a["sfx_cues"][0]["t"] == pytest.approx(13.5)
    assert a["unfilled_sfx_cues"][0]["what"] == "unmapped thing"
    assert {u["role"] for u in a["used_files"]} == {"music", "sfx"}


def test_audio_voice_mode_hits_target_and_ducks_bed(tmp_path, env):
    repo = make_repo(tmp_path, voiced=True)
    assert go(repo, "plan", "E01") == 0
    plan = J(repo / "work/episodes/E01/plan.json")
    assert plan["voice_mode"] == "voice" and plan["lines"][0]["timing_source"] == "take" and plan["lines"][0]["dur"] == pytest.approx(2.0, abs=0.01)
    assert go(repo, "audio", "E01") == 0
    a = J(repo / "work/episodes/E01/audio/audio.json")
    assert a["mode"] == "voice" and a["banner"] == ""
    assert abs(a["loudness"]["integrated_lufs"] - compose.LOUD_TARGET_I) <= compose.LOUD_TOL
    pre = repo / "work/episodes/E01/audio/premix.wav"

    def mean_db(t0, t1):
        r = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-ss", str(t0), "-t", str(t1 - t0), "-i", str(pre), "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True)
        return float(re.search(r"mean_volume: (-?[\d.]+)", r.stderr).group(1))
    # a 330 Hz line speaks 1.0-3.0 s and a 220 Hz bed runs throughout: the bed alone (6-9 s) is quieter than the voice+bed window
    assert mean_db(1.2, 2.8) > mean_db(6, 9) + 3


def test_audio_refuses_nc_and_missing_licence(tmp_path, env, capsys):
    repo = make_repo(tmp_path, licence="CC-BY-NC")
    assert go(repo, "plan", "E01") == 0 and go(repo, "audio", "E01") == 1
    out = capsys.readouterr().out
    assert "AUDIO-LICENCE" in out and "not allowed" in out
    repo2 = make_repo(tmp_path / "b")
    reg = repo2 / "assets/audio/LICENCES.md"
    reg.write_text("\n".join(l for l in reg.read_text(encoding="utf-8").splitlines() if not l.startswith("| click1")) + "\n", encoding="utf-8")
    assert go(repo2, "plan", "E01") == 0 and go(repo2, "audio", "E01") == 1 and "click1" in capsys.readouterr().out


def test_audio_all_silent_when_nothing_to_mix(tmp_path, env):
    repo = make_repo(tmp_path, with_music=False)
    edit(repo, lambda sl, sc: sl.update(sfx_map={}))
    assert go(repo, "plan", "E01") == 0 and go(repo, "audio", "E01") == 0
    assert J(repo / "work/episodes/E01/audio/audio.json")["silent"] is True


# ------------------------------------------------------------------ whole pipeline
def run_all(repo, skip=True):
    for st in ("plan", "audio", "captions", "assemble", "end"):
        assert go(repo, st, "E01") == 0, st
    return go(repo, "gate", "E01", *(["--skip-render-gate"] if skip else []))


def test_pipeline_end_to_end_no_voice(tmp_path, env, capsys):
    repo = make_repo(tmp_path)
    assert run_all(repo) == 0
    out = capsys.readouterr().out
    assert "PASS (INCOMPLETE" in out and "NO VOICE YET" in out
    w = repo / "work/episodes/E01"
    assert 34 < compose.duration(w / "episode.mp4") < 36 and compose.has_audio(w / "episode.mp4")
    rep = J(w / "gate/report.json")
    st = {c["id"]: c["status"] for c in rep["checks"]}
    assert all(st[k] == "pass" for k in ("EP-LENGTH", "EP-HOOK", "EP-CAPTIONS", "EP-SAFEZONE", "EP-LOUDNESS", "EP-CHOICE", "EP-MUSIC-LICENCE")), st
    assert st["EP-VOICE"] == "warn" and st["EP-RENDER-GATE"] == "skip" and rep["complete"] is False
    caps = J(w / "captions.json")["captions"]
    assert len(caps) == 3 and all(c["rtl"] and "thmanyah" in c["font"] for c in caps)
    ss = J(w / "STATE.json")["stages"]
    assert all(ss[s]["status"] == "ok" for s in ("plan", "audio", "captions", "assemble", "end", "gate"))


def test_pipeline_with_voice_and_viseme_timing(tmp_path, env):
    repo = make_repo(tmp_path, voiced=True)
    assert run_all(repo) == 0
    assert {c["id"]: c["status"] for c in J(repo / "work/episodes/E01/gate/report.json")["checks"]}["EP-VOICE"] == "pass"
    vd = repo / "work/voice/E01/visemes"
    vd.mkdir(parents=True)
    (vd / "l1.json").write_text(json.dumps({"keys": [{"t": 0.0, "id": "V0"}, {"t": 0.4, "id": "V3"}, {"t": 1.5, "id": "V0"}]}), encoding="utf-8")
    assert go(repo, "captions", "E01") == 0
    c = J(repo / "work/episodes/E01/captions.json")["captions"][0]
    assert c["start"] == pytest.approx(1.4) and c["end"] == pytest.approx(2.5) and c["timing"] == "viseme track"


def tamper(repo, fn):
    p = repo / "work/episodes/E01/captions.json"
    j = J(p)
    fn(j)
    p.write_text(json.dumps(j), encoding="utf-8")


@pytest.mark.parametrize("fn,check", [
    (lambda j: j["captions"][0].update(box=[10, 10, 200, 60]), "EP-SAFEZONE"),
    (lambda j: j["captions"].pop(), "EP-CAPTIONS"),
    (lambda j: j["captions"][1].update(start=j["captions"][0]["start"]), "EP-CAPTIONS"),
    (lambda j: j["captions"][0].update(font_px_1080=30), "EP-CAPTIONS"),
])
def test_gate_catches_caption_faults(tmp_path, env, capsys, fn, check):
    repo = make_repo(tmp_path)
    assert run_all(repo) == 0
    tamper(repo, fn)
    capsys.readouterr()
    assert go(repo, "gate", "E01", "--skip-render-gate", "--force") == 1
    assert f"FAIL  [{check}]" in capsys.readouterr().out


def test_gate_catches_licence_loudness_choice(tmp_path, env, capsys):
    repo = make_repo(tmp_path)
    assert run_all(repo) == 0
    w = repo / "work/episodes/E01"
    reg = repo / "assets/audio/LICENCES.md"
    good = reg.read_text(encoding="utf-8")
    reg.write_text("\n".join(l for l in good.splitlines() if not l.startswith("| bed1")) + "\n", encoding="utf-8")
    capsys.readouterr()
    assert go(repo, "gate", "E01", "--skip-render-gate", "--force") == 1 and "FAIL  [EP-MUSIC-LICENCE]" in capsys.readouterr().out
    reg.write_text(good, encoding="utf-8")
    ep, keep, hot = w / "episode.mp4", w / "keep.mp4", w / "hot.mp4"
    shutil.copy(ep, keep)
    sh("ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", keep, "-c:v", "copy", "-af", "volume=12dB", "-c:a", "aac", hot)
    shutil.copy(hot, ep)
    capsys.readouterr()
    assert go(repo, "gate", "E01", "--skip-render-gate", "--force") == 1 and "FAIL  [EP-LOUDNESS]" in capsys.readouterr().out
    shutil.copy(keep, ep)
    e = J(w / "end/end.json")
    e["choices"].pop()
    (w / "end/end.json").write_text(json.dumps(e, ensure_ascii=False), encoding="utf-8")
    capsys.readouterr()
    assert go(repo, "gate", "E01", "--skip-render-gate", "--force") == 1 and "FAIL  [EP-CHOICE]" in capsys.readouterr().out


def test_gate_catches_wrong_last_frame(tmp_path, env, capsys):
    repo = make_repo(tmp_path)
    assert run_all(repo) == 0
    w = repo / "work/episodes/E01"
    shutil.copy(w / "assembled.mp4", w / "episode.mp4")        # no end card at the end
    capsys.readouterr()
    assert go(repo, "gate", "E01", "--skip-render-gate", "--force") == 1
    assert "EP-CHOICE" in capsys.readouterr().out


def test_gate_refuses_stub_plates_in_real_runs(tmp_path, env, monkeypatch, capsys):
    repo = make_repo(tmp_path)
    assert run_all(repo) == 0
    monkeypatch.delenv("NJ_COMPOSE_ALLOW_STUB")
    capsys.readouterr()
    assert go(repo, "gate", "E01", "--skip-render-gate", "--force") == 1
    assert "test stub" in capsys.readouterr().out


def test_hook_fails_on_a_still_first_shot(tmp_path, env, capsys):
    repo = make_repo(tmp_path)
    still = repo / "work/shots/s1/out/s1.mp4"
    sh("ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=0x336699:s=270x480:r=24:d=11", "-c:v", "libx264", "-pix_fmt", "yuv420p", still)
    assert run_all(repo) == 1
    assert "FAIL  [EP-HOOK]" in capsys.readouterr().out


def test_face_in_ui_zone_fails_safezone(tmp_path, env, capsys):
    repo = make_repo(tmp_path)
    edit(repo, lambda sl, sc: sl["shots"][1]["faces"].append({"t0": 0, "t1": 2, "box": [60, 10, 200, 100]}))
    assert run_all(repo) == 1
    assert "FAIL  [EP-SAFEZONE]" in capsys.readouterr().out


def test_preview_adds_and_updates_tab(tmp_path, env):
    repo = make_repo(tmp_path)
    assert run_all(repo) == 0
    page = repo / "previews" / "index.html"
    page.parent.mkdir()
    page.write_text('<html><body><nav class="tabbar"></nav>\n<section class="panel" id="panel-a" data-tab="a"></section>\n<script>\n/* One preview page per project. */\nconst TABS = [\n  {id: "a", emoji: "x", label: "A"},\n];\n</script></body></html>', encoding="utf-8")
    assert go(repo, "preview", "E01") == 0
    t1 = page.read_text(encoding="utf-8")
    assert 'id: "ep-e01"' in t1 and 'data-tab="ep-e01"' in t1 and "../work/episodes/E01/episode.mp4" in t1 and "NO VOICE YET" in t1
    assert go(repo, "preview", "E01") == 0
    t2 = page.read_text(encoding="utf-8")
    assert t2.count('data-tab="ep-e01"') == 1 and t2.count('id: "ep-e01"') == 1


def test_init_never_overwrites(tmp_path):
    repo = tmp_path / "r"
    assert compose.main(["init", "ser/E09"], repo) == 0
    d = repo / "bible/series/ser/episodes/E09"
    assert (d / "shotlist.json").is_file() and (d / "outline.md").is_file() and not (d / "script.json").exists()
    (d / "outline.md").write_text("mine", encoding="utf-8")
    assert compose.main(["init", "ser/E09"], repo) == 0
    assert (d / "outline.md").read_text(encoding="utf-8") == "mine"


def test_status_runs(tmp_path, env, capsys):
    repo = make_repo(tmp_path)
    go(repo, "plan", "E01")
    capsys.readouterr()
    assert go(repo, "status", "E01") == 0
    assert "plan" in capsys.readouterr().out


def chrome_ok():
    try:
        import playwright.sync_api as p
        with p.sync_playwright() as pw:
            pw.chromium.launch().close()
        return all((compose.FONTS / f).is_file() for f in ("thmanyahsans-Bold.woff2", "thmanyahsans-Medium.woff2", "thmanyahserifdisplay-Black.woff2"))
    except Exception:
        return False


@pytest.mark.skipif(not chrome_ok(), reason="playwright Chromium or Thmanyah fonts not available")
def test_real_chrome_plates_and_card(tmp_path, monkeypatch):
    monkeypatch.setenv("NJ_COMPOSE_CPU", "1")
    repo = make_repo(tmp_path)
    assert run_all(repo) == 0                # no stub env: Thmanyah plates and card, contrast measured from the pixels
    st = {c["id"]: c["status"] for c in J(repo / "work/episodes/E01/gate/report.json")["checks"]}
    assert st["EP-CAPTIONS"] == st["EP-CHOICE"] == st["EP-SAFEZONE"] == "pass"


@pytest.mark.skipif("h264_nvenc" not in subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True).stdout, reason="no NVENC")
def test_nvenc_assemble(tmp_path, monkeypatch):
    monkeypatch.setenv("NJ_COMPOSE_STUB_PLATES", "1")
    monkeypatch.setenv("NJ_COMPOSE_ALLOW_STUB", "1")
    monkeypatch.delenv("NJ_COMPOSE_CPU", raising=False)
    repo = make_repo(tmp_path)
    assert run_all(repo) == 0
    info = compose.probe(repo / "work/episodes/E01/episode.mp4", "stream=codec_name")
    assert "h264" in [s["codec_name"] for s in info["streams"]]
