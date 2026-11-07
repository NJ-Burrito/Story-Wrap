"""Curated-clean casting: OWNER-CLEARED-COMMERCIAL licence, the `curated-clean` REF-QUALITY profile, 44.1 kHz refs,
and a casting whose `voice` is a source code instead of a Gemini name. Offline: synthetic clips only."""
import copy
import json
import math
import random

import pytest

import voice
from test_voice import RATE, ref_samples

CLEARANCE = {"who": "owner", "date": "2026-01-01", "scope": "commercial reuse of curated voices"}
PROV = {"code": "X1", "grade": "A", "never_clone": False}
REG = {"chat": {"id": "chat", "direction": "x"}}


def curated_like(sec=4.0, floor_amp=0.0097):
    """A curated ref: clean speech over a quiet but audible room floor (about -45 dBFS), well above the CV floor limit of -53."""
    r = random.Random(11)
    x = ref_samples("clean", sec)
    return [v + r.uniform(-1, 1) * floor_amp for v in x]


def wav_prov(tmp_path, samples, rate, name="r.wav", prov=PROV):
    w, p = tmp_path / name, tmp_path / (name + ".json")
    voice.write_wav16(w, samples, rate)
    p.write_text(json.dumps(prov), encoding="utf-8")
    return w, p


def cast(license_="OWNER-CLEARED-COMMERCIAL", clearance=CLEARANCE, **ref_extra):
    c = {"engine": "chatterbox", "emotions": ["calm"], "characters": {}}
    for k, code in (("a", "voice-a"), ("b", "voice-b")):
        ref = {"clip": f"refs/{k}.wav", "license": license_, "provenance": "refs/p.json", "source_code": code, **ref_extra}
        if clearance is not None:
            ref["owner_clearance"] = dict(clearance) if isinstance(clearance, dict) else clearance
        c["characters"][k] = {"voice": code, "accent": "carried in text: x", "styles": {"calm": ["chat"]}, "reference": ref}
    return c


# ---------------------------------------------------------------- 1. casting_problems: no Gemini voice name for Chatterbox
def test_chatterbox_casting_accepts_a_source_code_and_keeps_other_checks():
    reg = REG
    assert voice.casting_problems(cast(), reg) == []
    c = cast()
    c["characters"]["a"]["voice"] = "voice-c"                      # label no longer matches the reference's source_code
    assert any("source_code" in m for _, m in voice.casting_problems(c, reg))
    c = cast()
    c["characters"]["b"]["voice"] = c["characters"]["a"]["voice"]  # two roles on one voice, not declared
    c["characters"]["b"]["reference"].pop("source_code")
    assert any("share the voice" in m for _, m in voice.casting_problems(c, reg))
    c["reused_voices"] = {"voice-a": ["a", "b"]}                    # declared on both roles: allowed
    assert voice.casting_problems(c, reg) == []
    c = cast()
    c["characters"]["a"]["accent"] = "Gulf"
    assert any("carried in text" in m for _, m in voice.casting_problems(c, reg))
    c = cast()
    c["characters"]["a"]["styles"]["calm"] = ["invented"]
    assert any("never invent a style" in m for _, m in voice.casting_problems(c, reg))


def test_a_non_chatterbox_casting_still_needs_a_built_in_voice():
    c = cast()
    c["engine"] = "other"
    assert any("built-in voices" in m for _, m in voice.casting_problems(c, REG))


# ---------------------------------------------------------------- 2. licence
def test_owner_cleared_licence_needs_the_clearance_record():
    reg = REG
    assert voice.CLEARED in voice.LICENSES
    assert voice.casting_problems(cast(), reg) == []
    for bad in (None, {"who": "o", "date": "2026-01-01"}, {**CLEARANCE, "scope": " "}, "yes"):
        c = cast(clearance=bad)
        got = voice.casting_problems(c, reg)
        assert got and all(cid == "VOICE-REF" and "owner_clearance" in m for cid, m in got), bad
    assert voice.casting_problems(cast(license_="CC0-1.0", clearance=None), reg) == []     # other licences are unaffected


def test_reference_for_refuses_cleared_licence_without_record(tmp_path):
    refs = tmp_path / "refs"
    refs.mkdir()
    voice.write_wav16(refs / "a.wav", curated_like(), RATE)
    (refs / "p.json").write_text(json.dumps(PROV), encoding="utf-8")
    ok = cast(refq_profile="curated-clean")
    assert voice.reference_for(ok, "a", tmp_path) == tmp_path / "refs" / "a.wav"
    with pytest.raises(voice.Fail) as e:
        voice.reference_for(cast(clearance=None, refq_profile="curated-clean"), "a", tmp_path)
    assert e.value.cid == "VOICE-REF" and "owner_clearance" in str(e.value)
    with pytest.raises(voice.Fail) as e:
        voice.reference_for(cast(license_="MIT-ish", refq_profile="curated-clean"), "a", tmp_path)
    assert e.value.cid == "VOICE-REF"


# ---------------------------------------------------------------- 3. profile selection
def test_profile_is_selected_by_the_casting_entry_and_common_voice_stays_default(tmp_path):
    assert voice.DEFAULT_REFQ_PROFILE == "common-voice" and voice.REFQ_PROFILES["common-voice"] is voice.REFQ
    w, p = wav_prov(tmp_path, curated_like(), RATE, prov={"up_votes": 2, "down_votes": 0})
    _, as_cv = voice.check_reference_quality(w, p)
    _, as_cv2 = voice.check_reference_quality(w, p, "common-voice")
    _, as_lib = voice.check_reference_quality(w, p, "curated-clean")
    assert as_cv == as_cv2 and any("noise floor" in m for m in as_cv)     # the curated clip fails the Common Voice limits
    assert as_lib == []                                                  # and passes its own profile
    with pytest.raises(voice.Fail) as e:
        voice.check_reference_quality(w, p, "nope")
    assert e.value.cid == "REF-QUALITY" and "unknown" in str(e.value)
    # the limits the curated profile does not touch are the Common Voice ones
    for k in ("max_clip_samples", "min_top_db", "max_hum_db"):
        assert voice.REFQ_CURATED[k] == voice.REFQ[k]
    assert voice.REFQ_CURATED["max_floor_dbfs"] > voice.REFQ["max_floor_dbfs"]


def test_casting_ref_problems_uses_the_entry_profile(tmp_path):
    refs = tmp_path / "refs"
    refs.mkdir()
    voice.write_wav16(refs / "a.wav", curated_like(), RATE)
    voice.write_wav16(refs / "b.wav", curated_like(), RATE)
    (refs / "p.json").write_text(json.dumps(PROV), encoding="utf-8")
    c = cast(refq_profile="curated-clean")
    assert voice.casting_ref_problems(c, tmp_path) == []
    c["characters"]["b"]["reference"].pop("refq_profile")           # b falls back to the default profile
    got = voice.casting_ref_problems(c, tmp_path)
    assert [cid for cid, _ in got] == ["REF-QUALITY"] and "b" in got[0][1]


# ---------------------------------------------------------------- the bad clips the curated profile must still refuse
def test_curated_profile_still_rejects_clipping_music_bleed_and_wrong_rate(tmp_path):
    def run(samples, rate=RATE, prov=PROV):
        w, p = wav_prov(tmp_path, samples, rate, prov=prov)
        return voice.check_reference_quality(w, p, "curated-clean")[1]
    assert run(curated_like()) == []
    hot = [max(-1.0, min(1.0, v * 8)) for v in curated_like()]
    assert any("full scale" in m for m in run(hot))
    bed = [v + 0.05 * (math.sin(2 * math.pi * 262 * i / RATE) + math.sin(2 * math.pi * 330 * i / RATE) + math.sin(2 * math.pi * 392 * i / RATE))
           for i, v in enumerate(ref_samples("clean"))]                                    # a chord under the whole clip, pauses included
    got = run(bed)
    assert any("noise floor" in m for m in got) and any("SNR" in m for m in got)
    assert any("sample rate 16000" in m for m in run(curated_like(), 16000))
    assert any("sample rate 22050" in m for m in run(curated_like(), 22050))
    assert any("never_clone" in m for m in run(curated_like(), prov={**PROV, "never_clone": True}))
    muffled = voice.ref_profile(ref_samples("muffled"), RATE)
    assert any("muffled" in m for m in voice.ref_quality_problems({**muffled, "source_rate": 24000}, None, voice.REFQ_CURATED))


def test_the_cli_refcheck_takes_a_profile(tmp_path, capsys):
    w, p = wav_prov(tmp_path, curated_like(), RATE)
    assert voice.main(["refcheck", str(w), str(p)]) == 1                               # default profile: refused
    assert voice.main(["refcheck", str(w), str(p), "--profile", "curated-clean"]) == 0
    assert "OK reference is clean enough" in capsys.readouterr().out


# ---------------------------------------------------------------- 4. 44.1 kHz
def test_resample_keeps_length_and_level_and_removes_what_aliases():
    sr = 44100
    sine = [0.5 * math.sin(2 * math.pi * 1000 * i / sr) for i in range(sr)]
    y, r = voice.resample(sine, sr)
    assert r == 24000 and abs(len(y) - 24000) <= 1
    mid = y[2000:-2000]
    assert 0.48 < max(mid) < 0.52
    hi = [0.5 * math.sin(2 * math.pi * 20000 * i / sr) for i in range(sr)]           # above the new Nyquist: must be filtered, not folded
    z, _ = voice.resample(hi, sr)
    assert max(abs(v) for v in z[2000:-2000]) < 0.05
    same, r = voice.resample(sine, 24000)
    assert same is sine and r == 24000


@pytest.mark.parametrize("rate", [44100, 48000])
def test_refcheck_does_not_crash_on_high_rate_refs(tmp_path, rate):
    src = curated_like()
    up, _ = voice.resample(src, RATE, rate)
    w, p = wav_prov(tmp_path, up, rate)
    prof, bad = voice.check_reference_quality(w, p, "curated-clean")
    assert prof["source_rate"] == rate and bad == []
    _, p24 = voice.check_reference_quality(wav_prov(tmp_path, src, RATE, "s.wav")[0], None, "curated-clean")
    assert abs(prof["floor_dbfs"] - voice.check_reference_quality(tmp_path / "s.wav", None, "curated-clean")[0]["floor_dbfs"]) < 3.0
    assert voice.main(["refcheck", str(w), str(p), "--profile", "curated-clean"]) == 0


def test_a_clipped_44k_ref_is_still_counted_clipped(tmp_path):
    hot = [max(-1.0, min(1.0, v * 8)) for v in curated_like()]
    up, _ = voice.resample(hot, RATE, 44100)
    up = [max(-1.0, min(1.0, v)) for v in up]
    w, p = wav_prov(tmp_path, up, 44100)
    assert any("full scale" in m for m in voice.check_reference_quality(w, p, "curated-clean")[1])
