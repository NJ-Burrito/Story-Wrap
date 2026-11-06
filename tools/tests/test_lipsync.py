"""C6 lip sync (owner, 2026-10-25: "the mouths do not move with the words"): the voice stage writes a viseme track per character line on the take that is mixed,
calm.py places it on the shot, calm-scene.js drives the mouth from it, and the rig checks LIPSYNC-ACTIVE / LIPSYNC-SILENT hold the trace to it. No browser, no GPU, no network."""
import hashlib
import json
import math
import struct
import wave
from pathlib import Path

import pytest

import calm
import qg_checks as qc
import voice
import sw_fixtures

TOOLS = Path(__file__).resolve().parents[1]
FPS = 24
SCENE_JS = (TOOLS / "templates" / "calm" / "scene" / "calm-scene.js").read_text(encoding="utf-8")

# a line of 1.2 s on the shot clock from 0.5 s: V0 0..0.3 | V3 0.3..0.6 | V1 0.6..0.8 (lips closed) | V0 0.8..1.0 (a pause) | V4 1.0..1.2 | V0 end
KEYS = [{"t": 0.0, "id": "V0"}, {"t": 0.3, "id": "V3"}, {"t": 0.6, "id": "V1"}, {"t": 0.8, "id": "V0"}, {"t": 1.0, "id": "V4"}, {"t": 1.2, "id": "V0"}]
ENTRY = {"actor": "hero", "line": "L04", "start_s": 0.5, "ramp_s": 0.04, "keys": KEYS}
SHAPE_OPEN = {"V3": 0.75, "V1": 0.0, "V4": 0.3}
SPEC = {"lipsync": [ENTRY]}


def trace_for(entry, seconds=2.5, drive=True, offset=0.0, listener_wobble=False, silent_open=0.0, extra_actor=True):
    """A rig trace the way trace-multi.js writes it: per frame the viseme (from the track, shifted by `offset` s when a scene reads it wrongly) and the drawn mouth."""
    def frames(ent, wobble=False):
        out = []
        for f in range(int(seconds * FPS)):
            t = f / FPS
            r = qc.lip_track_at(ent, t - offset) if (ent and drive) else None
            vid, w = (r if r else (None, 0.0))
            op = SHAPE_OPEN.get(vid, 0.0) * w if vid and vid != "V0" else silent_open
            if wobble:
                op = 0.1 + 0.1 * math.sin(2 * math.pi * 1.5 * t)   # a jaw that opens and closes on its own
            out.append({"f": f, "t": round(t, 4), "face": {"viseme": vid if (vid and drive) else None, "viseme_w": w, "mouth": {"open": op}, "mouth_open": op}})
        return out
    chars = {"hero": {"frames": frames(ENTRY)}}
    if extra_actor:
        chars["guide"] = {"frames": frames(None, wobble=listener_wobble)}
    return {"fps": FPS, "characters": chars}


def ids(fails):
    return sorted({x.split("]")[0].split("[")[-1] for x in fails})


def test_voice_aware_shot_with_a_mouth_that_follows_its_track_passes():
    assert qc.rig_lipsync(trace_for(ENTRY), SPEC) == []


def test_a_spec_without_lipsync_is_not_judged():
    assert qc.rig_lipsync(trace_for(ENTRY, drive=False), {}) == []
    assert qc.rig_lipsync(trace_for(ENTRY, drive=False), None) == []


def test_mouth_that_never_reads_the_track_fails_active():
    f = qc.rig_lipsync(trace_for(ENTRY, drive=False), SPEC)   # the E01 calm bug: s.viseme was never set
    assert "LIPSYNC-ACTIVE" in ids(f)


def test_wrong_time_offset_fails_active():
    f = qc.rig_lipsync(trace_for(ENTRY, offset=0.35), SPEC)   # the track runs 0.35 s late against the audio
    assert "LIPSYNC-ACTIVE" in ids(f)


def test_mouth_open_in_a_pause_fails_silent():
    f = qc.rig_lipsync(trace_for(ENTRY, silent_open=0.3), SPEC)   # the jaw hangs open between the words
    assert "LIPSYNC-SILENT" in ids(f)


def test_a_viseme_with_weight_in_silence_fails_silent():
    tr = trace_for(ENTRY)
    for fr in tr["characters"]["hero"]["frames"]:
        if fr["t"] < 0.25:
            fr["face"]["viseme"], fr["face"]["viseme_w"] = "V3", 1.0
    assert "LIPSYNC-SILENT" in ids(qc.rig_lipsync(tr, SPEC))


def test_a_mouth_that_is_drawn_but_too_small_fails_active():
    tr = trace_for(ENTRY)
    for fr in tr["characters"]["hero"]["frames"]:
        fr["face"]["mouth"]["open"] = min(fr["face"]["mouth"]["open"], 0.05)
    assert "LIPSYNC-ACTIVE" in ids(qc.rig_lipsync(tr, SPEC))


def test_narrator_line_never_moves_a_characters_mouth():
    spec = {"lipsync": []}   # a narrator scene: nobody on screen speaks
    assert qc.rig_lipsync(trace_for(None, extra_actor=False, drive=False), spec) == []
    wob = {"fps": FPS, "characters": {"hero": {"frames": [{"f": i, "t": round(i / FPS, 4), "face": {"viseme": None, "viseme_w": 0, "mouth": {"open": 0.1 + 0.1 * math.sin(2 * math.pi * 1.5 * i / FPS)}}} for i in range(60)]}}}
    assert "LIPSYNC-SILENT" in ids(qc.rig_lipsync(wob, spec))
    viseme_on = {"fps": FPS, "characters": {"hero": {"frames": [{"f": i, "t": round(i / FPS, 4), "face": {"viseme": "V3" if i == 5 else None, "viseme_w": 1, "mouth": {"open": 0.0}}} for i in range(30)]}}}
    assert "LIPSYNC-SILENT" in ids(qc.rig_lipsync(viseme_on, spec))


def test_listener_wobble_while_another_speaks_fails_silent():
    assert "LIPSYNC-SILENT" in ids(qc.rig_lipsync(trace_for(ENTRY, listener_wobble=True), SPEC))


def test_a_gasp_is_not_talking():
    series = [0.0] * 10 + [0.1 * k for k in range(1, 7)] + [0.6] * 20 + [0.6 - 0.05 * k for k in range(1, 9)] + [0.2] * 10
    tr = {"fps": FPS, "characters": {"hero": {"frames": [{"f": i, "t": round(i / FPS, 4), "face": {"viseme": None, "viseme_w": 0, "mouth": {"open": v}}} for i, v in enumerate(series)]}}}
    assert qc.rig_lipsync(tr, {"lipsync": []}) == []


def test_track_reader_twin_matches_face_js():
    K = [{"t": 0, "id": "V0"}, {"t": .2, "id": "V3"}, {"t": .5, "id": "V4"}, {"t": .8, "id": "V0"}]
    e = {"start_s": 0.0, "ramp_s": .04, "keys": K}
    assert qc.lip_track_at(e, .3) == ("V3", 1.0) and qc.lip_track_at(e, .6) == ("V4", 1.0) and qc.lip_track_at(e, .9) is None


def test_the_rig_gate_runs_the_lipsync_check():
    tr = trace_for(ENTRY, drive=False)
    assert "LIPSYNC-ACTIVE" in ids([x for x in qc.rig_lipsync(tr, SPEC)])
    import inspect
    assert "rig_lipsync(trace, spec)" in inspect.getsource(qc.check_rig)


# ------------------------------------------------------------------ the calm scene is wired to the track (what failed in E01 calm)
def test_scene_reads_the_track_and_the_jaw_no_longer_drifts():
    assert "visemeTrackAt(e, t - e.start_s)" in SCENE_JS and "s.viseme" in SCENE_JS and "CALM.lipsync" in SCENE_JS
    assert 'au["26"] +=' not in SCENE_JS   # the old breathing jaw: a mouth that opened and closed with no word, in narrator scenes too
    assert 'au["26"] = 0' in SCENE_JS      # a speaker's jaw is shut except through the viseme


def test_trace_exports_the_mouth_per_frame_per_actor():
    for fn in ("trace-multi.js", "trace.js"):
        src = (TOOLS / "render" / fn).read_text(encoding="utf-8")
        assert "viseme_w" in src and "mouthRec(R.mouth)" in src
    assert "function mouthRec" in (TOOLS / "render" / "face.js").read_text(encoding="utf-8")


# ------------------------------------------------------------------ calm.py places the track on the shot
def wav(path, seconds=1.5, tone=1.0):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(b"".join(struct.pack("<h", int(tone * 9000 * math.sin(i / 20))) for i in range(int(24000 * seconds))))


def voice_root(tmp_path, speaker="hero", with_track=True):
    vdir = tmp_path / "work" / "voice" / "E99"
    (vdir / "visemes").mkdir(parents=True)
    wav(vdir / "L04.trimmed.wav")
    sha = hashlib.sha256((vdir / "L04.trimmed.wav").read_bytes()).hexdigest()
    if with_track:
        (vdir / "visemes" / "L04.json").write_text(json.dumps({"format": "viseme-track/1", "line": "L04", "ramp_s": .04, "source": {"audio_sha256": sha}, "keys": KEYS}), encoding="utf-8")
    return {"lines": [{"id": "L04", "speaker": speaker}, {"id": "L01", "speaker": "narrator"}]}


def test_entry_for_the_narrator_is_none(tmp_path):
    script = voice_root(tmp_path)
    assert calm.lipsync_entry(tmp_path, "E99", script, "L01", 0.45, ["hero"]) is None


def test_entry_for_a_speaker_off_screen_is_none(tmp_path):
    script = voice_root(tmp_path, speaker="guide")
    assert calm.lipsync_entry(tmp_path, "E99", script, "L04", 0.45, ["hero"]) is None


def test_entry_places_the_track_on_the_shot_clock(tmp_path):
    script = voice_root(tmp_path)
    e = calm.lipsync_entry(tmp_path, "E99", script, "L04", 0.45, ["hero"])
    assert e["actor"] == "hero" and e["start_s"] == 0.45 and e["keys"][1] == {"t": 0.3, "id": "V3"}


def test_a_character_line_without_a_track_is_refused(tmp_path):
    script = voice_root(tmp_path, with_track=False)
    with pytest.raises(calm.CalmError) as e:
        calm.lipsync_entry(tmp_path, "E99", script, "L04", 0.45, ["hero"])
    assert e.value.code == "LIPSYNC-NO-TRACK"


def test_a_track_measured_on_other_audio_is_refused(tmp_path):
    script = voice_root(tmp_path)
    wav(tmp_path / "work" / "voice" / "E99" / "L04.trimmed.wav", seconds=1.6, tone=0.5)   # the take was re-voiced after the track was written
    with pytest.raises(calm.CalmError) as e:
        calm.lipsync_entry(tmp_path, "E99", script, "L04", 0.45, ["hero"])
    assert e.value.code == "LIPSYNC-STALE-TRACK"


def calm_shot(**kw):
    return calm.resolve("push_in", {"character": "hero", "pose": "write", "expression": "calm", "duration": "3.75", "id": "t-lip", **kw})


@sw_fixtures.needs_project("calm kits (tools/templates/calm/kits/<char>.json and .js, built from your characters' smoke shots) and the voice casting", "tools/templates/calm/kits/hero.json")
def test_shot_carries_the_track_in_json_and_spec():
    c = calm_shot()
    calm.set_lipsync(c, [ENTRY])
    assert calm.validate_calm(c) == []
    assert calm.shot_json(c)["calm"]["lipsync"][0]["line"] == "L04"
    plan = {"shots": []}
    spec = calm.build_spec(c, plan, {"id": "t-lip", "rel": "work/shots/t-lip"})
    assert spec["lipsync"] == [ENTRY]


@sw_fixtures.needs_project("calm kits (tools/templates/calm/kits/<char>.json and .js, built from your characters' smoke shots) and the voice casting", "tools/templates/calm/kits/hero.json")
def test_a_shot_with_no_lipsync_key_is_not_voice_aware():
    c = calm_shot()
    assert "lipsync" not in calm.build_spec(c, {"shots": []}, {"id": "t-lip", "rel": "x"})
    calm.set_lipsync(c, [None])
    assert calm.build_spec(c, {"shots": []}, {"id": "t-lip", "rel": "x"})["lipsync"] == []


@sw_fixtures.needs_project("calm kits (tools/templates/calm/kits/<char>.json and .js, built from your characters' smoke shots) and the voice casting", "tools/templates/calm/kits/hero.json")
def test_a_line_that_outruns_the_shot_is_refused():
    c = calm_shot(duration="1.5")
    calm.set_lipsync(c, [ENTRY])   # 0.5 + 1.2 = 1.7 s on a 1.5 s shot
    assert any(x.startswith("CALM-LIPSYNC") for x in calm.validate_calm(c))


# ------------------------------------------------------------------ the voice stage writes tracks for characters only, on the take that is mixed
@sw_fixtures.needs_project("your character catalogue (catalogue/characters/<id>/ face files)", "catalogue/characters/hero")
def test_visemes_skip_the_narrator_and_read_the_trimmed_take(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    man = {"lines": [{"id": "n1", "speaker": "narrator", "text": "هذا", "tts_text": "هَذَا"}, {"id": "s1", "speaker": "hero", "text": "هذا", "tts_text": "هَذَا"}]}
    (tmp_path / "m.json").write_text(json.dumps(man), encoding="utf-8")
    import test_voice as tv
    for name, bursts in (("n1.wav", ((0.2, 0.7),)), ("s1.wav", ((0.0, 0.5),)), ("s1.trimmed.wav", ((0.2, 0.7),))):   # the raw take starts at once, the trimmed one after a lead
        tv.fake_wav(work / name, bursts=bursts, total=1.0)
    paths = {"manifest": tmp_path / "m.json", "work": work}
    assert voice.cmd_visemes(paths) == 1
    assert not (work / "visemes" / "n1.json").exists()
    t = json.loads((work / "visemes" / "s1.json").read_text(encoding="utf-8"))
    assert t["source"]["audio_sha256"] == hashlib.sha256((work / "s1.trimmed.wav").read_bytes()).hexdigest()
    assert min(k["t"] for k in t["keys"] if k["id"] != "V0") >= 0.15
