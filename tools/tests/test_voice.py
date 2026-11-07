"""Voice stage tests: offline only (fake audio, injected post function, no network, no credentials)."""
import json
import math
import random
import struct
import subprocess
import wave
from pathlib import Path

import pytest

import voice
import voice_edges
import sw_fixtures

GATE = voice.NJ_WRITER / "scripts" / "voice_style_gate.py"
needs_gate = pytest.mark.skipif(not GATE.exists(), reason="nj-writer voice_style_gate.py not on this machine")

AR_TTS = "تَعَرَّفُوا عَلَى إِنْسِيرَا."
AR_VIS = "تعرفوا على إنسيرا."


def fake_wav(path, bursts=((0.2, 0.7), (1.0, 1.6)), total=2.0, rate=24000):
    n = int(total * rate)
    frames = bytearray()
    for i in range(n):
        t = i / rate
        a = 9000 if any(lo <= t < hi for lo, hi in bursts) else 0
        frames += struct.pack("<h", int(a * math.sin(2 * math.pi * 180 * t)))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))


@pytest.fixture
def ep(tmp_path):
    d = tmp_path / "bible" / "series" / "series" / "episodes" / "ep01"
    d.mkdir(parents=True)
    script = {"episode": "ep01", "series": "series", "lines": [
        {"id": "l01", "speaker": "hero", "emotion": "calm", "text": AR_VIS, "tts_text": AR_TTS},
        {"id": "l02", "speaker": "lead", "emotion": "figures", "style": "data", "text": AR_VIS, "tts_text": AR_TTS}]}
    (d / "script.json").write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")
    return voice.episode_paths(d, repo=tmp_path), tmp_path


def make_manifest(paths):
    s = voice.load_script(paths)
    m = voice.build_manifest(s, voice.load_casting(s), voice.load_registry())
    voice.write_json(paths["manifest"], m)
    return m


def ids(fails):
    return {f[0] for f in fails}


def no_net(*a, **k):
    pytest.fail("network call")


@sw_fixtures.needs_project("voice casting (bible/series/<series>/voices/casting.json), its reference clips and your nj-writer voice registry", "bible/series/series/voices/casting.json")
def test_casting_is_legal_and_md_in_sync():
    c = voice.read_json(voice.casting_path("series"))
    assert voice.casting_problems(c, voice.load_registry()) == []
    assert len({v["voice"] for v in c["characters"].values()}) == len(c["characters"])   # every cast voice distinct (7 characters + the narrator)
    md = voice.casting_path("series").with_name("casting.md")
    assert md.read_text(encoding="utf-8") == voice.render_casting_md(c)


@sw_fixtures.needs_project("voice casting (bible/series/<series>/voices/casting.json), its reference clips and your nj-writer voice registry", "bible/series/series/voices/casting.json")
def test_manifest_copies_text_and_registry_direction(ep):
    paths, _ = ep
    m = make_manifest(paths)
    reg = voice.load_registry()
    assert m["lines"][0]["voice"] == "Leda" and m["lines"][0]["style"] == "chat"
    assert m["lines"][0]["direction"] == reg["chat"]["direction"]
    assert m["lines"][0]["tts_text"] == AR_TTS


@sw_fixtures.needs_project("voice casting (bible/series/<series>/voices/casting.json), its reference clips and your nj-writer voice registry", "bible/series/series/voices/casting.json")
def test_manifest_refuses_uncast_and_illegal_style(ep):
    paths, _ = ep
    s = voice.load_script(paths)
    c, r = voice.load_casting(s), voice.load_registry()
    cases = (({"speaker": "nobody"}, "VOICE-CAST"), ({"style": "alert"}, "VOICE-STYLE"),
             ({"emotion": "bogus"}, "VOICE-STYLE"), ({"style": "invented"}, "VOICE-STYLE"))
    for patch, cid in cases:
        s2 = json.loads(json.dumps(s))
        s2["lines"][0].update(patch)
        with pytest.raises(voice.Fail) as e:
            voice.build_manifest(s2, c, r)
        assert e.value.cid == cid


@needs_gate
def test_gate_passes_and_writes_receipt(ep):
    paths, root = ep
    make_manifest(paths)
    assert voice.cmd_gate(paths) == []
    assert (paths["work"] / "gate.json").exists()


@needs_gate
def test_gate_text_drift_style_and_cast(ep):
    paths, root = ep
    m = make_manifest(paths)
    m["lines"][0]["text"] = "نص آخر"
    m["lines"][1]["style"] = "alert"
    m["lines"][1]["voice"] = "Kore"
    voice.write_json(paths["manifest"], m)
    assert {"VOICE-TEXT", "VOICE-STYLE", "VOICE-CAST"} <= ids(voice.cmd_gate(paths))
    assert not (paths["work"] / "gate.json").exists()


@needs_gate
def test_gate_style_gate_catches_unmarked_tts(ep):
    paths, root = ep
    s = json.loads(paths["script"].read_text(encoding="utf-8"))
    s["lines"][0]["tts_text"] = AR_VIS
    paths["script"].write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")
    make_manifest(paths)
    assert "VOICE-GATE" in ids(voice.cmd_gate(paths))


@needs_gate
def test_voice_once_refuses_existing_audio(ep):
    paths, root = ep
    make_manifest(paths)
    paths["work"].mkdir(parents=True)
    fake_wav(paths["work"] / "l01.wav")
    assert "VOICE-ONCE" in ids(voice.cmd_gate(paths))


@sw_fixtures.needs_project("voice casting (bible/series/<series>/voices/casting.json), its reference clips and your nj-writer voice registry", "bible/series/series/voices/casting.json")
def test_other_engines_are_refused_and_no_network_path(ep, capsys):
    paths, root = ep
    for eng in ("gemini", "openrouter", "silma"):
        with pytest.raises(voice.Fail) as e:
            voice.cmd_voice(paths, go=True, engine=eng)
        assert e.value.cid == "VOICE-BANNED"
    assert voice.main(["voice", str(paths["script"].parent), "--engine", "gemini"]) == 1
    assert "VOICE-BANNED" in capsys.readouterr().out
    src = Path(voice.__file__).read_text(encoding="utf-8").lower()
    assert "urllib" not in src and "openrouter" not in src and "http" not in src.replace("https://", "")
    assert not hasattr(voice, "http_post") and not hasattr(voice, "api_key")


# ---------------------------------------------------------------- synthetic speech for the end-trim
RATE = 24000


def speech(seconds, f0=140, amp=0.3):
    """Speech-like: harmonics with a slow syllable wobble (tonal, so low spectral flatness)."""
    n = int(seconds * RATE)
    return [amp * (0.6 + 0.4 * math.sin(2 * math.pi * 4 * i / RATE)) *
            sum(math.sin(2 * math.pi * f0 * k * i / RATE) / k for k in range(1, 6)) / 2 for i in range(n)]


def hiss(seconds, amp):
    r = random.Random(7)
    return [r.uniform(-amp, amp) for _ in range(int(seconds * RATE))]


def hum(seconds, amp, f=110):
    return [amp * math.sin(2 * math.pi * f * i / RATE) for i in range(int(seconds * RATE))]


def silence(seconds):
    return [0.0] * int(seconds * RATE)


def ms(n):
    return n * RATE // 1000


def test_trim_removes_trailing_noise_after_a_gap():
    x = silence(.1) + speech(1.2) + silence(.5) + hum(.8, .008) + hiss(.7, .004)   # the shape of the real Chatterbox tail
    y, info = voice.trim_take(x, RATE)
    assert not info["clipped_end"]                                                # the hum is not voiced (no formant band), so it is no run at all (2026-10-26)
    assert info["cut_end_ms"] > 1500                                              # 0.5 s gap + 1.5 s noise, minus the tail guard
    E = voice_edges.params()
    assert len(y) / RATE < 1.2 + E["lead_guard_s"] + E["tail_guard_s"] + E["lead_pad_s"] + E["tail_pad_s"] + .05
    assert voice.tail_problems(y, RATE, info) == []
    assert max(abs(v) for v in y[-ms(150):]) == 0                                 # clean digital silence at the end


def test_trim_removes_hiss_glued_to_the_speech():
    y, info = voice.trim_take(silence(.1) + speech(1.0) + hiss(1.0, .006), RATE)
    assert info["cut_end_ms"] >= 750                                              # 1 s of hiss minus the 200 ms tail guard (take.edge.tail_guard_s; the old hangover was 100 ms)
    assert voice.tail_problems(y, RATE, info) == []


def test_trim_fades_and_pads():
    y, info = voice.trim_take(silence(.3) + speech(1.0) + silence(.6), RATE)
    assert 30 <= info["fade_out_ms"] <= 60
    assert max(abs(v) for v in y[:ms(60)]) == 0                                   # lead pad is silent
    assert abs(y[len(y) - ms(150) - 1]) < 0.01                                    # faded to (almost) zero at the cut
    assert not info["clipped_end"]


def test_clean_file_keeps_its_speech_unchanged():
    body = speech(1.0)
    y, info = voice.trim_take(silence(.2) + body + silence(.3), RATE)
    s0 = ms(200) - info["start"] + ms(80)                                         # where the body starts inside y
    assert all(abs(a - b) < 1e-9 for a, b in zip(y[s0 + ms(100):s0 + ms(900)], body[ms(100):ms(900)]))
    y2, info2 = voice.trim_take(y, RATE)                                          # trimming again changes nothing that matters
    assert abs(len(y2) - len(y)) <= ms(40) and not info2["clipped_end"]


def test_word_ending_at_the_very_edge_is_kept_and_flagged():
    y, info = voice.trim_take(silence(.2) + speech(1.0), RATE)                    # no silence after: the word runs to the file end
    assert info["cut_end_ms"] == 0 and info["clipped_end"]
    assert len(y) >= ms(1000) + ms(80)                                            # nothing of the word was cut away
    fails = voice.tail_problems(y, RATE, info)
    assert [f[0] for f in fails] == ["VOICE-TAIL"] and "clipped" in fails[0][1]


def test_tail_check_catches_energy_in_the_last_ms():
    x = speech(1.0) + hiss(.3, .02)
    f = voice.tail_problems(x, RATE, {"edge_db_rel": -60})
    assert f and f[0][0] == "VOICE-TAIL" and "last 100 ms" in f[0][1]
    assert voice.tail_problems(x + silence(.2), RATE, {"edge_db_rel": -60}) == []
    assert voice.tail_problems(silence(1), RATE, None)[0][0] == "VOICE-TAIL"       # no trim record: cannot show the ending is whole


def test_trim_refuses_silent_audio():
    with pytest.raises(voice.Fail):
        voice.trim_take(silence(1), RATE)


def test_float32_wav_is_read_like_torchaudio_writes_it(tmp_path):
    x = [0.5 * math.sin(2 * math.pi * 200 * i / RATE) for i in range(RATE // 2)]
    data = struct.pack(f"<{len(x)}f", *x)
    hdr = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 3, 1, RATE, RATE * 4, 4, 32)
    (tmp_path / "f.wav").write_bytes(hdr + b"data" + struct.pack("<I", len(data)) + data)
    y, r = voice.read_float(tmp_path / "f.wav")
    assert r == RATE and len(y) == len(x) and abs(y[100] - x[100]) < 1e-6
    s, _ = voice.read_wav(tmp_path / "f.wav")
    assert len(s) == len(x) and abs(voice.wav_seconds(tmp_path / "f.wav") - .5) < 1e-6


def test_cmd_trim_writes_a_16bit_wav(tmp_path):
    voice.write_wav16(tmp_path / "raw.wav", silence(.1) + speech(.8) + silence(.5) + hum(.6, .01), RATE)
    info = voice.cmd_trim(tmp_path / "raw.wav", tmp_path / "t.wav")
    assert info["cut_end_ms"] > 800
    assert abs(voice.wav_seconds(tmp_path / "t.wav") - info["trimmed_ms"] / 1000) < .01


def test_real_chatterbox_trial_tail_is_cut():
    raw = voice.REPO / "work" / "voice-trial" / "chatterbox.wav"
    out = voice.REPO / "work" / "voice-trial" / "chatterbox-trimmed.wav"
    if not (raw.exists() and out.exists()):
        pytest.skip("trial files not on this machine")
    x, r = voice.read_float(raw)
    y, info = voice.trim_take(x, r)
    assert info["cut_end_ms"] > 1500 and not info["clipped_end"]                  # about 2.3 s of tail in the 4.56 s take
    assert voice.tail_problems(y, r, info) == []
    z, r2 = voice.read_float(out)
    assert voice.tail_problems(z, r2, info) == []


def test_token_cap_is_a_safety_net_not_a_clamp():
    assert voice.token_cap("ا" * 18) == 115 and voice.token_cap("ا" * 4000) == 1000 and voice.token_cap("ا") >= 50


# ---------------------------------------------------------------- REF-QUALITY
def ref_samples(kind="clean", sec=4.0):
    """Synthetic reference clip: words with pauses. kinds: clean, noisy, hot, muffled, reverb."""
    r = random.Random(3)
    out = []
    for i in range(int(sec * RATE)):
        t = i / RATE
        gate = 1.0 if (t % 1.0) < 0.7 else 0.0
        env = gate * (0.5 + 0.5 * abs(math.sin(2 * math.pi * 3 * t)))
        v = sum(math.sin(2 * math.pi * 150 * k * t) / k for k in range(1, 6)) * 0.12 * env + 0.05 * math.sin(2 * math.pi * 1200 * t) * env   # formant-like energy: a voice is not all fundamental
        if kind != "muffled":
            v += r.uniform(-1, 1) * 0.02 * env                      # breath and fricatives: energy above 8 kHz
        if kind != "muffled":
            v += r.uniform(-1, 1) * (0.03 if kind == "noisy" else 0.0004)   # room floor
        out.append(v)
    if kind == "muffled":
        out = [v * (1 + 5 * math.sin(math.pi * (i - 2500) / 1000) ** 2 if 2500 < i < 3500 else 1) for i, v in enumerate(out)]   # a smooth loud syllable for the crest
    else:
        out[3000] = 0.9                                             # a plosive peak
    if kind == "gated":                                             # a noise gate / denoiser: the pauses are exact digital zero
        out = [v if abs(v) > 0.004 else 0.0 for v in out]
    if kind == "hot":
        out = [max(-1.0, min(1.0, v * 8)) for v in out]             # squashed and clipped
    if kind == "reverb":                                            # a slow decay after every word (a bare room)
        for i in range(len(out)):
            t = i / RATE
            if (t % 1.0) >= 0.7:
                out[i] += 0.1 * math.exp(-((t % 1.0) - 0.7) / 0.07) * sum(math.sin(2 * math.pi * 150 * k * t) / k for k in range(1, 4))
    return out


def test_ref_quality_passes_a_clean_clip_and_names_each_fault():
    ok = voice.ref_profile(ref_samples(), RATE)
    assert voice.ref_quality_problems(ok, {"up_votes": 2, "down_votes": 0}) == []
    expect = {"noisy": "noise floor", "hot": "full scale", "muffled": "muffled", "reverb": "reverberant"}
    for kind, word in expect.items():
        bad = voice.ref_quality_problems(voice.ref_profile(ref_samples(kind), RATE), {"up_votes": 2, "down_votes": 0})
        assert bad and any(word in m for m in bad), (kind, bad)
    hot = voice.ref_quality_problems(voice.ref_profile(ref_samples("hot"), RATE))
    assert any("crest" in m for m in hot)
    assert any("not validated" in m for m in voice.ref_quality_problems(ok, {"up_votes": 0, "down_votes": 0}))
    assert any("not validated" in m for m in voice.ref_quality_problems(ok, {"up_votes": 3, "down_votes": 1}))


def test_ref_quality_thresholds_are_calibrated_on_the_four_approved_clips():
    q = voice.REFQ
    assert "2026-10-24" in q["calibrated_on"] and "rival" in q["calibrated_on"]
    approved = {"rival": (-58.9, 38.3, 22.7, -31.4, 0.05), "lead": (-62.8, 40.2, 21.5, -29.6, 0.05),
                "partner": (-55.6, 42.4, 21.1, -31.9, 0.09), "guide": (-55.7, 36.6, 20.1, -50.3, 0.12)}
    rejected = {"hero": (-48.8, 36.2, 19.4, -63.0, 0.14), "extra": (-51.7, 41.2, 14.1, -74.5, 0.11), "han": (-61.7, 56.7, 9.7, -39.8, 0.03)}

    def prof(v, clip=0):
        return {"floor_dbfs": v[0], "snr_db": v[1], "crest_db": v[2], "top_db": v[3], "decay20_s": v[4], "clip_samples": clip}
    for k, v in approved.items():
        assert voice.ref_quality_problems(prof(v)) == [], k
    for k, v in rejected.items():
        assert voice.ref_quality_problems(prof(v, 6 if k == "han" else 0), {"up_votes": 0 if k == "han" else 2, "down_votes": 0}), k


@sw_fixtures.needs_project("voice casting (bible/series/<series>/voices/casting.json), its reference clips and your nj-writer voice registry", "bible/series/series/voices/casting.json")
def test_voice_and_casting_enforce_ref_quality(ep, tmp_path):
    paths, root = ep
    cast_with_refs(root)
    cp = voice.casting_path("series", root)
    make_manifest(paths)
    assert voice.casting_ref_problems(voice.read_json(cp), root) == []
    voice.write_wav16(root / "refs" / "hero.wav", ref_samples("noisy"), RATE)          # a noisy clip is refused
    with pytest.raises(voice.Fail) as e:
        voice.cmd_voice(paths, go=True, repo=root, synth=no_net)
    assert e.value.cid == "REF-QUALITY" and "hero" in str(e.value)
    assert [c for c, _ in voice.casting_ref_problems(voice.read_json(cp), root)] == ["REF-QUALITY"]


def test_refcheck_command_exit_codes(tmp_path, capsys):
    good, bad = tmp_path / "g.wav", tmp_path / "b.wav"
    voice.write_wav16(good, ref_samples(), RATE)
    voice.write_wav16(bad, ref_samples("hot"), RATE)
    assert voice.main(["refcheck", str(good)]) == 0
    assert voice.main(["refcheck", str(bad)]) == 1 and "REF-QUALITY" in capsys.readouterr().out


@sw_fixtures.needs_project("voice casting (bible/series/<series>/voices/casting.json), its reference clips and your nj-writer voice registry", "bible/series/series/voices/casting.json")
def test_every_real_reference_in_the_casting_passes_ref_quality():
    c = voice.read_json(voice.casting_path("series"))
    if not all((voice.REPO / ch["reference"]["clip"]).exists() for ch in c["characters"].values()):
        pytest.skip("reference clips (work/, git-ignored) are not on this machine")
    assert voice.casting_ref_problems(c) == []


# ---------------------------------------------------------------- the voice stage with a fake engine (no GPU, no model)
def cast_with_refs(root, series="series", refs=True):
    c = voice.read_json(voice.casting_path(series))
    c["engine"] = "chatterbox"
    for k, ch in c["characters"].items():
        ch.pop("reference", None)
        if refs:
            (root / "refs").mkdir(exist_ok=True)
            (root / "refs" / "prov.json").write_text('{"up_votes": 2, "down_votes": 0}', encoding="utf-8")
            voice.write_wav16(root / "refs" / f"{k}.wav", ref_samples(), RATE)
            ch["reference"] = {"clip": f"refs/{k}.wav", "license": "CC0-1.0", "provenance": "refs/prov.json"}
    d = root / "bible" / "series" / series / "voices"
    d.mkdir(parents=True)
    voice.write_json(d / "casting.json", c)


def fake_engine(job):
    for ln in job["lines"]:
        for part in ln.get("segments") or [ln]:             # breath segmentation: one wav per segment, joined by the stage
            voice.write_wav16(part["out"], silence(.1) + speech(.9) + silence(.5) + hum(.6, .01) + hiss(.4, .004), RATE)
    voice.write_json(job["result"], {"lines": [{"id": ln["id"], "gen_s": 0.1} for ln in job["lines"]]})


def write_receipt(paths):
    paths["work"].mkdir(parents=True, exist_ok=True)
    voice.write_json(paths["work"] / "gate.json", {"passed": True, "manifest_sha256": voice.sha(paths["manifest"].read_bytes()),
                                                    "script_sha256": voice.sha(paths["script"].read_bytes())})


@sw_fixtures.needs_project("voice casting (bible/series/<series>/voices/casting.json), its reference clips and your nj-writer voice registry", "bible/series/series/voices/casting.json")
def test_voice_one_take_writes_raw_trimmed_and_log(ep):
    paths, root = ep
    cast_with_refs(root)
    make_manifest(paths)
    write_receipt(paths)
    assert voice.cmd_voice(paths, go=False, repo=root, synth=no_net) == 0          # dry run: nothing made
    assert not (paths["work"] / "l01.wav").exists()
    assert voice.cmd_voice(paths, go=True, repo=root, synth=fake_engine) == 0
    for n in ("l01", "l02"):
        assert (paths["work"] / f"{n}.wav").exists() and (paths["work"] / f"{n}.trimmed.wav").exists()
    att = voice.attempts(paths["work"])
    assert att["l01"]["status"] == "ok" and att["l01"]["trim"]["cut_end_ms"] > 800 and att["l01"]["engine"] == "chatterbox"
    assert [f for f in voice.tail_checks(paths["work"], voice.read_json(paths["manifest"])) if f[0] == "VOICE-TAIL"] == []   # the synthetic tone is boxy by design (TAKE-QUALITY is tested on its own)
    with pytest.raises(voice.Fail) as e:                                            # a second take is refused
        voice.cmd_voice(paths, go=True, repo=root, synth=fake_engine)
    assert e.value.cid == "VOICE-ONCE"


@sw_fixtures.needs_project("voice casting (bible/series/<series>/voices/casting.json), its reference clips and your nj-writer voice registry", "bible/series/series/voices/casting.json")
def test_voice_refuses_a_missing_reference(ep):
    paths, root = ep
    cast_with_refs(root, refs=False)
    make_manifest(paths)
    with pytest.raises(voice.Fail) as e:
        voice.cmd_voice(paths, go=True, repo=root, synth=no_net)
    assert e.value.cid == "VOICE-REF"


@sw_fixtures.needs_project("voice casting (bible/series/<series>/voices/casting.json), its reference clips and your nj-writer voice registry", "bible/series/series/voices/casting.json")
def test_voice_refuses_an_unlicensed_reference(ep):
    paths, root = ep
    cast_with_refs(root)
    c = voice.read_json(voice.casting_path("series", root))
    c["characters"]["hero"]["reference"]["license"] = "CC-BY-NC"
    voice.write_json(voice.casting_path("series", root), c)
    make_manifest(paths)
    with pytest.raises(voice.Fail) as e:
        voice.cmd_voice(paths, go=True, repo=root, synth=no_net)
    assert e.value.cid == "VOICE-REF"


@sw_fixtures.needs_project("voice casting (bible/series/<series>/voices/casting.json), its reference clips and your nj-writer voice registry", "bible/series/series/voices/casting.json")
def test_voice_refuses_without_a_gate_receipt(ep):
    paths, root = ep
    cast_with_refs(root)
    make_manifest(paths)
    with pytest.raises(voice.Fail) as e:
        voice.cmd_voice(paths, go=True, repo=root, synth=no_net)
    assert e.value.cid == "VOICE-GATE"


@sw_fixtures.needs_project("voice casting (bible/series/<series>/voices/casting.json), its reference clips and your nj-writer voice registry", "bible/series/series/voices/casting.json")
def test_tail_check_runs_on_every_trimmed_take(ep):
    paths, root = ep
    m = make_manifest(paths)
    paths["work"].mkdir(parents=True)
    voice.write_wav16(paths["work"] / "l01.trimmed.wav", speech(1.0), RATE)        # not trimmed: energy to the very end
    voice.log_attempt(paths["work"], {"id": "l01", "status": "ok", "trim": {"edge_db_rel": -60}})
    f = voice.tail_checks(paths["work"], m)
    assert f and f[0][0] == "VOICE-TAIL" and "l01" in f[0][1]


@sw_fixtures.needs_project("voice casting (bible/series/<series>/voices/casting.json), its reference clips and your nj-writer voice registry", "bible/series/series/voices/casting.json")
def test_casting_is_marked_retired():
    c = voice.read_json(voice.casting_path("series"))
    assert c["status"] == "retired: Gemini banned"
    assert c["engine"] == "chatterbox"
    assert all(set(ch["reference"]) >= {"sex", "age_range", "accent_region", "clip", "fallback"} for ch in c["characters"].values())


def test_voiced_segments_from_fake_audio(tmp_path):
    fake_wav(tmp_path / "a.wav")
    s, r = voice.read_wav(tmp_path / "a.wav")
    segs, dur = voice.voiced_segments(s, r)
    assert len(segs) == 2 and abs(segs[0][0] - .2) < .05 and abs(segs[1][1] - 1.6) < .05 and abs(dur - 2) < .01


def test_silent_audio_is_refused(tmp_path):
    fake_wav(tmp_path / "s.wav", bursts=())
    s, r = voice.read_wav(tmp_path / "s.wav")
    with pytest.raises(voice.Fail):
        voice.voiced_segments(s, r)


@sw_fixtures.needs_project("voice casting (bible/series/<series>/voices/casting.json), its reference clips and your nj-writer voice registry", "bible/series/series/voices/casting.json")
def test_symbols_use_the_characters_letters():
    face, _ = voice.latest_face("hero")
    lmap = voice.letter_map(voice.read_json(face))
    assert lmap["ب"] == "V1" and lmap["ف"] == "V2"
    assert [s[0] for s in voice.symbols("هُدَى", lmap)][:2] == ["V7", "V4"]


@sw_fixtures.needs_project("voice casting (bible/series/<series>/voices/casting.json), its reference clips and your nj-writer voice registry", "bible/series/series/voices/casting.json")
def test_visemes_end_to_end(ep):
    paths, _ = ep
    m = make_manifest(paths)
    paths["work"].mkdir(parents=True)
    for ln in m["lines"]:
        fake_wav(paths["work"] / f"{ln['id']}.wav")
    assert voice.cmd_visemes(paths) == 2
    t = voice.read_json(paths["work"] / "visemes" / "l01.json")
    assert t["format"] == "viseme-track/1" and t["face"].startswith("hero/v")
    keys = t["keys"]
    assert keys[0]["t"] == 0 and keys[-1]["id"] == "V0"
    assert all(keys[i]["t"] <= keys[i + 1]["t"] for i in range(len(keys) - 1))
    open_keys = [k for k in keys if k["id"] != "V0"]
    assert open_keys and open_keys[0]["t"] >= .15 and open_keys[-1]["t"] <= 1.6
    hold = voice.MIN_HOLD_FRAMES / voice.FPS
    assert all(keys[i + 1]["t"] - keys[i]["t"] >= hold - 1e-3 for i in range(len(keys) - 1))
    schema = json.loads((voice.REPO / "kb/quality/viseme-track.schema.json").read_text(encoding="utf-8"))
    assert set(schema["required"]) <= set(t)


def test_reader_in_face_js(tmp_path):
    track = {"ramp_s": .04, "keys": [{"t": 0, "id": "V0"}, {"t": .2, "id": "V3"}, {"t": .5, "id": "V4"}, {"t": .8, "id": "V0"}]}
    js = (voice.REPO / "tools/render/face.js").read_text(encoding="utf-8")
    prog = js + f"\nconst T={json.dumps(track)};console.log(JSON.stringify([visemeTrackAt(T,.3),visemeTrackAt(T,.6),visemeTrackAt(T,.9)]));"
    f = tmp_path / "r.js"
    f.write_text(prog, encoding="utf-8")
    try:
        r = subprocess.run(["node", str(f)], capture_output=True, text=True, encoding="utf-8")
    except FileNotFoundError:
        pytest.skip("node not installed")
    assert json.loads(r.stdout) == [{"id": "V3", "w": 1}, {"id": "V4", "w": 1}, None]


# ---------------------------------------------------------------- load failure vs mid-line failure; status; repair; pre-flight
def prep_go(ep):
    paths, root = ep
    cast_with_refs(root)
    make_manifest(paths)
    write_receipt(paths)
    return paths, root


def dies_at_load(job):
    raise OSError("[WinError 1455] The paging file is too small for this operation to complete")


def dies_mid_line(job):
    voice.mark(job["marks"], {"event": "loaded"})
    first, second = job["lines"][0], job["lines"][1]
    voice.mark(job["marks"], {"event": "generating", "id": first["id"]})
    voice.write_wav16(first["out"], speech(.8), RATE)
    raise RuntimeError("CUDA out of memory")                  # dies before the second line starts


@sw_fixtures.needs_project("voice casting (bible/series/<series>/voices/casting.json), its reference clips and your nj-writer voice registry", "bible/series/series/voices/casting.json")
def test_load_failure_frees_every_line_and_keeps_the_cause(ep):
    paths, root = prep_go(ep)
    with pytest.raises(voice.Fail) as e:
        voice.cmd_voice(paths, go=True, repo=root, synth=dies_at_load)
    assert "1455" in str(e.value) and "l01, l02" in str(e.value)
    att = voice.attempts(paths["work"])
    assert att["l01"]["status"] == "not-taken" and "engine failed to load" in att["l01"]["reason"] and "1455" in att["l01"]["reason"]
    assert voice.cmd_status(paths["dir"], repo=root) == [("l01", "not-taken"), ("l02", "not-taken")]
    assert voice.cmd_voice(paths, go=True, repo=root, synth=fake_engine) == 0     # may be voiced now
    assert voice.cmd_status(paths["dir"], repo=root) == [("l01", "taken"), ("l02", "taken")]


@sw_fixtures.needs_project("voice casting (bible/series/<series>/voices/casting.json), its reference clips and your nj-writer voice registry", "bible/series/series/voices/casting.json")
def test_mid_line_failure_blocks_only_started_lines(ep):
    paths, root = prep_go(ep)
    with pytest.raises(voice.Fail) as e:
        voice.cmd_voice(paths, go=True, repo=root, synth=dies_mid_line)
    assert "CUDA out of memory" in str(e.value)
    st = dict(voice.cmd_status(paths["dir"], repo=root))
    assert st == {"l01": "taken", "l02": "not-taken"}                             # l01 has a wav; l02 never started
    (paths["work"] / "l01.wav").unlink()                                          # even with the audio gone, l01 stays blocked
    assert dict(voice.cmd_status(paths["dir"], repo=root))["l01"] == "blocked-after-start"
    with pytest.raises(voice.Fail) as e:
        voice.cmd_voice(paths, go=True, repo=root, synth=fake_engine)
    assert e.value.cid == "VOICE-ONCE"


@sw_fixtures.needs_project("voice casting (bible/series/<series>/voices/casting.json), its reference clips and your nj-writer voice registry", "bible/series/series/voices/casting.json")
def test_started_line_without_wav_is_blocked_and_gate_agrees(ep):
    paths, root = prep_go(ep)
    voice.log_attempt(paths["work"], {"id": "l01", "status": "error", "generation_started": True})
    assert dict(voice.cmd_status(paths["dir"], repo=root))["l01"] == "blocked-after-start"
    assert "VOICE-ONCE" in ids(voice.gate_checks(voice.load_script(paths), voice.read_json(paths["manifest"]),
                                                  voice.load_casting(voice.load_script(paths), root),
                                                  voice.load_registry(), paths["work"]))


def test_repair_marks_old_started_only_logs_not_taken(tmp_path):
    w = tmp_path / "take"
    for n in ("a", "b"):
        voice.log_attempt(w, {"id": n, "status": "started", "engine": "chatterbox"})
    voice.log_attempt(w, {"id": "c", "status": "started", "engine": "chatterbox"})
    voice.log_attempt(w, {"id": "c", "status": "error", "generation_started": True})
    voice.write_wav16(w / "b.wav", speech(.5), RATE)
    assert voice.cmd_repair(w, "paging file too small") == ["a"]
    assert dict(voice.cmd_status(w)) == {"a": "not-taken", "b": "taken", "c": "blocked-after-start"}
    assert voice.main(["status", str(w)]) == 0


@sw_fixtures.needs_project("voice casting (bible/series/<series>/voices/casting.json), its reference clips and your nj-writer voice registry", "bible/series/series/voices/casting.json")
def test_preflight_refuses_and_says_which_resource(ep):
    paths, root = prep_go(ep)
    low_commit = lambda: {"commit_free": 1 * voice.GB, "gpu_free": 8 * voice.GB, "need_commit": 6 * voice.GB}
    with pytest.raises(voice.Fail) as e:
        voice.cmd_voice(paths, go=True, repo=root, synth=no_net, resources=low_commit)
    assert e.value.cid == "VOICE-PREFLIGHT" and "commit memory" in str(e.value) and "GPU" not in str(e.value)
    low_gpu = lambda: {"commit_free": 20 * voice.GB, "gpu_free": 1 * voice.GB, "need_commit": 6 * voice.GB}
    with pytest.raises(voice.Fail) as e:
        voice.cmd_voice(paths, go=True, repo=root, synth=no_net, resources=low_gpu)
    assert e.value.cid == "VOICE-PREFLIGHT" and "GPU memory" in str(e.value)
    assert not (paths["work"] / "attempts.jsonl").exists()                         # nothing logged: no line used up
    ok = lambda: {"commit_free": 20 * voice.GB, "gpu_free": 8 * voice.GB, "need_commit": 6 * voice.GB}
    assert voice.cmd_voice(paths, go=True, repo=root, synth=fake_engine, resources=ok) == 0


def test_preflight_numbers_and_need_from_model_files(tmp_path):
    (tmp_path / "m").mkdir()
    (tmp_path / "m" / "t3.safetensors").write_bytes(b"x" * 1000)
    assert voice.need_commit_bytes(tmp_path) == 1000 + voice.COMMIT_MARGIN
    assert voice.preflight_problems(None, None, 10) == []
    assert len(voice.preflight_problems(1, 1, 10)) == 2
    assert voice.NEED_VRAM >= int(3.6 * voice.GB)
    c = voice.free_commit_bytes()
    assert c is None or c > 0


@sw_fixtures.needs_project("voice casting (bible/series/<series>/voices/casting.json), its reference clips and your nj-writer voice registry", "bible/series/series/voices/casting.json")
def test_voice_writes_measured_seconds_and_measure_refills(ep):
    paths, root = ep
    cast_with_refs(root)
    make_manifest(paths)
    write_receipt(paths)
    voice.cmd_voice(paths, go=True, repo=root, synth=fake_engine)
    m = voice.read_json(paths["manifest"])["lines"][0]
    assert m["seconds"] == pytest.approx(voice.wav_seconds(paths["work"] / "l01.trimmed.wav"), abs=.001)
    assert m["raw_seconds"] > m["seconds"] > 0
    mm = voice.read_json(paths["manifest"])                                       # strip, then `measure` restores (no synthesis)
    for l in mm["lines"]:
        l.pop("seconds"); l.pop("raw_seconds")
    voice.write_json(paths["manifest"], mm)
    assert voice.measure_manifest(paths) == ["l01", "l02"]
    assert voice.read_json(paths["manifest"])["lines"][1]["seconds"] > 0


@sw_fixtures.needs_project("voice casting (bible/series/<series>/voices/casting.json), its reference clips and your nj-writer voice registry", "bible/series/series/voices/casting.json")
def test_measure_fails_without_takes_and_full_gate_needs_seconds(ep):
    paths, root = ep
    make_manifest(paths)
    with pytest.raises(voice.Fail) as e:
        voice.cmd_measure(paths["dir"], work=paths["work"])
    assert e.value.cid == "VOICE-AUDIO"
    fails = voice.run_style_gate(paths["manifest"], True)
    assert any("no measured seconds" in f[1] for f in fails)


# ---- per-character pace band (VOICE-PACE)
def _pace_manifest(speaker, words, seconds):
    return {"lines": [{"id": "p1", "speaker": speaker, "text": " ".join(["كلمة"] * words), "seconds": seconds}]}


@sw_fixtures.needs_project("voice casting (bible/series/<series>/voices/casting.json), its reference clips and your nj-writer voice registry", "bible/series/series/voices/casting.json")
def test_character_band_pass_and_fail():
    c = voice.read_json(voice.casting_path("series"))
    lo, hi = c["characters"]["lead"]["pace"]["band_wpm"]
    ok = _pace_manifest("lead", 4, 4 * 60 / ((lo + hi) / 2))
    assert voice.pace_findings(ok, c) == []
    bad = _pace_manifest("lead", 4, 4 * 60 / (hi + 40))          # far too fast for a slow speaker
    f = voice.pace_findings(bad, c)
    assert f and f[0][0] == "VOICE-PACE" and "lead" in f[0][1]


@sw_fixtures.needs_project("voice casting (bible/series/<series>/voices/casting.json), its reference clips and your nj-writer voice registry", "bible/series/series/voices/casting.json")
def test_narrator_band_unchanged_and_dialogue_wpm_dropped():
    c = voice.read_json(voice.casting_path("series"))
    c["characters"]["narrator"] = {k: v for k, v in c["characters"]["lead"].items() if k != "pace"}
    assert voice.pace_band(c, "narrator") is None
    m = {"lines": [{"id": "n1", "speaker": "narrator"}, {"id": "e1", "speaker": "lead"}]}
    style = [("VOICE-GATE", "FAIL: line n1: wpm 70 outside ar band 110-120"), ("VOICE-GATE", "FAIL: line e1: wpm 70 outside ar band 110-120"),
             ("VOICE-GATE", "FAIL: line e1: tempo 2 above max_tempo 1.7")]
    left = voice.drop_dialogue_wpm(style, m, c)
    assert len(left) == 2 and "line n1" in left[0][1] and "tempo" in left[1][1]
    assert voice.pace_findings(_pace_manifest("narrator", 4, 9), c) == []


@sw_fixtures.needs_project("voice casting (bible/series/<series>/voices/casting.json), its reference clips and your nj-writer voice registry", "bible/series/series/voices/casting.json")
def test_every_cast_character_has_a_sourced_band_and_chatterbox_settings():
    c = voice.read_json(voice.casting_path("series"))
    for k, ch in c["characters"].items():
        pc = ch["pace"]
        assert pc["band_wpm"][0] < pc["band_wpm"][1] and pc["source"] and 0 < pc["chatterbox"]["cfg_weight"] <= 1
        want = {"cfg_weight": pc["chatterbox"]["cfg_weight"], "exaggeration": pc["chatterbox"]["exaggeration"]}
        if "temperature" in pc["chatterbox"]:
            want["temperature"] = pc["chatterbox"]["temperature"]
        assert voice.character_settings(c, k) == want


@sw_fixtures.needs_project("voice casting (bible/series/<series>/voices/casting.json), its reference clips and your nj-writer voice registry", "bible/series/series/voices/casting.json")
def test_only_dropped_failures_clear_the_result_line():
    c = voice.read_json(voice.casting_path("series"))
    m = {"lines": [{"id": "e1", "speaker": "lead"}]}
    style = [("VOICE-GATE", "FAIL: line e1: wpm 70 outside ar band 110-120"), ("VOICE-GATE", "RESULT: FAIL (1 fail)")]
    assert voice.drop_dialogue_wpm(style, m, c) == []


# ---------------------------------------------------------------- 2026-10-25: the banned narrator and what REF-QUALITY missed
def test_ref_quality_catches_a_gated_clip_the_old_limits_passed():
    prof = voice.ref_profile(ref_samples("gated"), RATE)
    msgs = voice.ref_quality_problems(prof, {"up_votes": 2, "down_votes": 0})
    assert any("gated or denoised" in m for m in msgs) and any("digital silence" in m for m in msgs), msgs
    old = {k: v for k, v in prof.items() if k not in ("zero_frac", "centroid_hz", "hum_db")}
    old["floor_dbfs"] = -70.0
    assert voice.ref_quality_problems(old) == []        # the pre-2026-10-25 limits passed such a clip


def test_new_ref_limits_pass_the_approved_clips_and_fail_the_banned_narrator():
    approved = {"rival": (-58.9, 0.0047, 569), "lead": (-62.8, 0.0073, 1043), "partner": (-55.6, 0.0026, 475), "guide": (-55.7, 0.0017, 657),
                "hero": (-60.4, 0.0082, 593), "extra": (-60.8, 0.0075, 495), "han": (-62.0, 0.0092, 609)}
    base = {"snr_db": 40.0, "crest_db": 21.0, "top_db": -30.0, "decay20_s": 0.08, "clip_samples": 0}
    for k, (fl, z, c) in approved.items():
        assert voice.ref_quality_problems({**base, "floor_dbfs": fl, "zero_frac": z, "centroid_hz": c, "hum_db": 9.0}) == [], k
    banned = {**base, "floor_dbfs": -88.4, "snr_db": 66.7, "zero_frac": 0.0638, "centroid_hz": 334, "hum_db": 7.6}
    assert len(voice.ref_quality_problems(banned)) == 3


def test_take_quality_names_each_fault_and_passes_a_clean_take():
    clean = {"pause_rel_db": -35.0, "centroid_hz": 600, "clip_samples": 0, "hum_db": 5.0, "gate_gaps": 0}
    assert voice.take_quality_problems(clean) == []
    for key, val, word in [("pause_rel_db", -20.0, "noise between words"), ("centroid_hz", 340, "boxy"), ("clip_samples", 295, "full scale"),
                           ("hum_db", 50.0, "hum"), ("gate_gaps", 1, "digital-silence")]:
        assert any(word in m for m in voice.take_quality_problems({**clean, key: val})), key


def test_take_profile_sees_noise_between_words_and_a_chopping_gate():
    def line(pause_noise, gate):
        out = []
        r = random.Random(5)
        for w in range(3):
            out += [0.2 * math.sin(2 * math.pi * 150 * i / RATE) * (1 + 0.5 * math.sin(2 * math.pi * 3 * i / RATE)) + 0.12 * math.sin(2 * math.pi * 1800 * i / RATE) for i in range(int(.5 * RATE))]
            out += [0.0 if gate else r.uniform(-1, 1) * pause_noise for _ in range(int(.3 * RATE))]
        return out
    clean = voice.take_profile(line(0.0005, False), RATE)
    noisy = voice.take_profile(line(0.05, False), RATE)
    gated = voice.take_profile(line(0.0, True), RATE)
    assert voice.take_quality_problems(clean) == []
    assert any("noise between words" in m for m in voice.take_quality_problems(noisy))
    assert any("digital-silence" in m for m in voice.take_quality_problems(gated))


def test_gate_full_runs_take_quality_on_trimmed_takes(tmp_path):
    work = tmp_path / "t"
    work.mkdir()
    voice.write_wav16(work / "l01.trimmed.wav", [0.2 * math.sin(2 * math.pi * 150 * i / RATE) + (0.05 if (i // 2400) % 2 else 0) * random.Random(i).uniform(-1, 1)
                                                for i in range(RATE * 2)], RATE)
    f = voice.tail_checks(work, {"lines": [{"id": "l01"}]})
    assert all(c in ("VOICE-TAIL", "TAKE-QUALITY", "VOICE-EDGE-NOISE") for c, _ in f)


@sw_fixtures.needs_project("voice casting (bible/series/<series>/voices/casting.json), its reference clips and your nj-writer voice registry", "bible/series/series/voices/casting.json")
def test_banned_voice_is_refused_by_clip_hash_and_speaker(ep, tmp_path):
    paths, root = ep
    cast_with_refs(root)
    (root / "bible").mkdir(exist_ok=True)
    prov = {"clip": "x.mp3", "sha256_mp3": "abc", "speaker_id_hashed": "spk1", "up_votes": 2, "down_votes": 0}
    (root / "refs" / "prov.json").write_text(json.dumps(prov), encoding="utf-8")
    voice.write_json(root / voice.BANNED_VOICES, {"banned": [{"id": "b1", "date": "2026-10-25", "reason": "noisy", "clip_source_ids": [],
                                                              "sha256_mp3": [], "speaker_ids_hashed": ["spk1"]}]})
    c = voice.read_json(voice.casting_path("series", root))
    with pytest.raises(voice.Fail) as e:
        voice.reference_for(c, "hero", root)
    assert e.value.cid == "VOICE-BANNED-REF" and "noisy" in str(e.value)
    assert voice.banned_reason({"clip_source_id": "q.mp3"}, {"sha256_mp3": "abc"}, [{"id": "b", "date": "d", "reason": "r", "sha256_mp3": ["abc"]}])
    assert not voice.banned_reason({"clip_source_id": "q.mp3"}, {}, [{"id": "b", "date": "d", "reason": "r", "clip_source_ids": ["z.mp3"]}])


@sw_fixtures.needs_project("voice casting (bible/series/<series>/voices/casting.json), its reference clips and your nj-writer voice registry", "bible/series/series/voices/casting.json")
def test_the_real_banned_list_names_the_old_narrator_and_no_cast_voice_uses_it():
    banned = voice.load_banned()
    assert any("common_voice_ar_21519152.mp3" in b["clip_source_ids"] for b in banned)
    c = voice.read_json(voice.casting_path("series"))
    for k, ch in c["characters"].items():
        ref = ch.get("reference") or {}
        assert ref.get("clip_source_id") != "common_voice_ar_21519152.mp3", k


@sw_fixtures.needs_project("voice casting (bible/series/<series>/voices/casting.json), its reference clips and your nj-writer voice registry", "bible/series/series/voices/casting.json")
def test_retext_drops_every_stale_take_source_not_only_the_first(ep):
    """E02 (2026-10-27): `any(rec.pop(n) ... for n in moved)` stopped at the first hit, so a second retexted line kept its stale take-sources entry and its new take read as VOICE-STALE-TAKE."""
    paths, root = ep
    cast_with_refs(root)
    make_manifest(paths)
    write_receipt(paths)
    assert voice.cmd_voice(paths, go=True, repo=root, synth=fake_engine) == 0
    before = paths["manifest"].with_name("before.json")
    before.write_bytes(paths["manifest"].read_bytes())
    ts = paths["work"] / "take-sources.json"
    ts.write_text(json.dumps({"l01": "aaa", "l02": "bbb"}), encoding="utf-8")
    m = voice.read_json(paths["manifest"])
    for ln in m["lines"]:
        ln["tts_text"] += " جديد"
    voice.write_json(paths["manifest"], m)
    moved, same, unknown = voice.cmd_retext(paths, "both changed", baseline=before)
    assert moved == ["l01", "l02"] and same == []
    assert json.loads(ts.read_text(encoding="utf-8")) == {}


@sw_fixtures.needs_project("voice casting (bible/series/<series>/voices/casting.json), its reference clips and your nj-writer voice registry", "bible/series/series/voices/casting.json")
def test_retext_sets_aside_only_the_takes_whose_words_changed(ep):
    paths, root = ep
    cast_with_refs(root)
    make_manifest(paths)
    write_receipt(paths)
    assert voice.cmd_voice(paths, go=True, repo=root, synth=fake_engine) == 0
    before = paths["manifest"].with_name("before.json")
    before.write_bytes(paths["manifest"].read_bytes())
    m = voice.read_json(paths["manifest"])
    m["lines"][0]["tts_text"] += " جديد"
    voice.write_json(paths["manifest"], m)
    moved, same, unknown = voice.cmd_retext(paths, "new words", baseline=before)
    assert moved == ["l01"] and same == ["l02"] and unknown == []
    work = paths["work"]
    kept = work.with_name(work.name + "-superseded-text")
    assert not (work / "l01.wav").exists() and (work / "l02.wav").exists() and (kept / "l01.wav").exists()
    assert voice.cmd_retext(paths, "again", baseline=before)[0] == []                        # nothing left to set aside
    write_receipt(paths)
    assert voice.cmd_voice(paths, go=True, repo=root, synth=fake_engine) == 0                # voices l01 once; l02 keeps its take
    assert (work / "l01.wav").exists() and voice.attempts(work)["l01"]["tts_sha256"] != voice.attempts(work)["l02"]["tts_sha256"]


@sw_fixtures.needs_project("voice casting (bible/series/<series>/voices/casting.json), its reference clips and your nj-writer voice registry", "bible/series/series/voices/casting.json")
def test_supersede_moves_a_banned_voices_takes_and_only_then(ep):
    paths, root = ep
    cast_with_refs(root)
    cp = voice.casting_path("series", root)
    make_manifest(paths)
    write_receipt(paths)
    assert voice.cmd_voice(paths, go=True, repo=root, synth=fake_engine) == 0
    with pytest.raises(voice.Fail) as e:                       # no banned reference in the casting: a re-voice is refused
        voice.cmd_supersede(paths, "hero", "because", repo=root)
    assert e.value.cid == "VOICE-ONCE"
    c = voice.read_json(cp)
    c["characters"]["hero"]["banned_references"] = [{"clip": "old.wav"}]
    voice.write_json(cp, c)
    assert voice.cmd_supersede(paths, "hero", "voice banned", repo=root) == ["l01"]
    work = paths["work"]
    assert not (work / "l01.wav").exists() and (work / "l02.wav").exists()
    kept = work.with_name(work.name + "-superseded-hero")
    assert (kept / "l01.wav").exists() and "l01" in (kept / "attempts.jsonl").read_text(encoding="utf-8")
    assert "l01" not in voice.attempts(work) and "l02" in voice.attempts(work)
    write_receipt(paths)
    assert voice.cmd_voice(paths, go=True, repo=root, synth=fake_engine) == 0     # only l01 is voiced again; l02 stays
    assert voice.attempts(work)["l01"]["reference"]["sha256"] and (work / "l01.wav").exists()


# ---------------------------------------------------------------- the mastering chain in the voice stage (2026-10-26)
def test_character_temperature_reaches_chatterbox_and_default_stays():
    c = {"characters": {"narrator": {"pace": {"chatterbox": {"cfg_weight": 0.3, "exaggeration": 0.3, "temperature": 0.7}}},
                        "hero": {"pace": {"chatterbox": {"cfg_weight": 0.5}}}, "han": {}}}
    assert voice.character_settings(c, "narrator") == {"cfg_weight": 0.3, "exaggeration": 0.3, "temperature": 0.7}
    assert "temperature" not in voice.character_settings(c, "hero") and voice.character_settings(c, "han") == {}
    assert voice.CHATTERBOX_SETTINGS["temperature"] == 0.8                          # the default for everyone without their own
    c["characters"]["han"] = {"pace": {"chatterbox": {"temperature": 9.0}}}
    with pytest.raises(voice.Fail) as e:
        voice.character_settings(c, "han")
    assert e.value.cid == "VOICE-CAST"


@sw_fixtures.needs_project("voice casting (bible/series/<series>/voices/casting.json), its reference clips and your nj-writer voice registry", "bible/series/series/voices/casting.json")
def test_job_line_carries_the_temperature(ep):
    paths, root = ep
    cast_with_refs(root)
    cp = voice.casting_path("series", root)
    c = voice.read_json(cp)
    c["characters"]["hero"].setdefault("pace", {}).setdefault("chatterbox", {})["temperature"] = 0.7
    voice.write_json(cp, c)
    make_manifest(paths)
    write_receipt(paths)
    seen = {}

    def spy(job):
        seen.update({ln["id"]: ln["settings"] for ln in job["lines"]})
        fake_engine(job)
    voice.cmd_voice(paths, go=True, repo=root, synth=spy)
    assert seen["l01"]["temperature"] == 0.7 and "temperature" not in seen["l02"]


@sw_fixtures.needs_project("voice casting (bible/series/<series>/voices/casting.json), its reference clips and your nj-writer voice registry", "bible/series/series/voices/casting.json")
def test_new_take_is_mastered_by_default_and_the_raw_take_is_kept(ep):
    paths, root = ep
    cast_with_refs(root)
    make_manifest(paths)
    write_receipt(paths)
    assert voice.cmd_voice(paths, go=True, repo=root, synth=fake_engine) == 0
    w = paths["work"]
    rec = voice.attempts(w)["l01"]["trim"]["master"]
    assert rec["role"] == "dialogue" and rec["contract"] == []
    assert (w / "l01.wav").exists() and (w / "l01.trimmed.master.json").exists()
    x, _ = voice.read_float(w / "l01.trimmed.wav")
    assert len(x) == round(rec["after"]["seconds"] * RATE)
    f = voice.tail_checks(w, voice.read_json(paths["manifest"]))
    assert not [m for c, m in f if c == "VOICE-TAIL"]                                # the chain keeps the clean tail
    assert not [m for c, m in f if c == "VOICE-MASTER" and "loudness" in m]          # on its target


@sw_fixtures.needs_project("voice casting (bible/series/<series>/voices/casting.json), its reference clips and your nj-writer voice registry", "bible/series/series/voices/casting.json")
def test_master_switch_off_keeps_the_old_behaviour(ep, monkeypatch):
    paths, root = ep
    cast_with_refs(root)
    make_manifest(paths)
    write_receipt(paths)
    monkeypatch.setattr(voice, "MASTER_TAKES", False)
    assert voice.cmd_voice(paths, go=True, repo=root, synth=fake_engine) == 0
    assert "master" not in voice.attempts(paths["work"])["l01"]["trim"]
    assert not (paths["work"] / "l01.trimmed.master.json").exists()


@sw_fixtures.needs_project("voice casting (bible/series/<series>/voices/casting.json), its reference clips and your nj-writer voice registry", "bible/series/series/voices/casting.json")
def test_voice_master_gate_runs_on_a_mastered_take(ep):
    paths, root = ep
    cast_with_refs(root)
    make_manifest(paths)
    paths["work"].mkdir(parents=True, exist_ok=True)
    voice.write_wav16(paths["work"] / "l01.trimmed.wav", silence(.08) + speech(1.0, amp=.02) + silence(.15), RATE)   # far under -19 LUFS
    voice.log_attempt(paths["work"], {"id": "l01", "status": "ok", "trim": {"edge_db_rel": -60, "master": {"role": "dialogue", "contract": []}}})
    f = voice.tail_checks(paths["work"], voice.read_json(paths["manifest"]))
    assert any(c == "VOICE-MASTER" and "loudness" in m for c, m in f)


def test_casting_md_points_at_the_tracked_provenance():
    import inspect
    src = inspect.getsource(voice.render_casting_md)
    assert "voices/provenance/*.json" in src and "work/tts-refs/<character>/provenance.json" not in src
