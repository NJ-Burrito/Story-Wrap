"""C9 (2026-10-25): the phone-first mix chain (tools/calm_mix.py) and its three checks (tools/audio_checks.py).

The checks are tested the way a check must be: a bad mix fails with the right id, a good one passes, and each threshold has a case that sits on the wrong side of it.
"""
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import audio_checks as A  # noqa: E402
import calm_mix as M  # noqa: E402
import calm_sfx as S  # noqa: E402

SR = A.SR


def tone(f, secs, amp=0.1, ch=2):
    t = np.arange(int(secs * SR)) / SR
    x = (amp * np.sin(2 * np.pi * f * t)).astype("float32")
    return np.repeat(x[:, None], ch, axis=1)


def speechlike(secs, amp=0.12, seed=1):
    """Noise shaped to 150 Hz to 4 kHz and chopped into 'words' of 0.35 s with 0.15 s gaps."""
    from scipy import signal
    rng = np.random.default_rng(seed)
    n = int(secs * SR)
    x = rng.standard_normal(n)
    sos = signal.butter(2, [150, 4000], "bandpass", fs=SR, output="sos")
    x = signal.sosfilt(sos, x)
    env = ((np.arange(n) / SR) % 0.5 < 0.35).astype(float)
    x = x * env
    x = x / (np.abs(x).max() + 1e-9) * amp * 3
    return np.repeat(x[:, None].astype("float32"), 2, axis=1)


def stems(voice, bed=None, sfx=None):
    z = np.zeros_like(voice)
    return {"voice": voice, "bed": z if bed is None else bed, "sfx": z if sfx is None else sfx}


# ------------------------------------------------------------------ measurement
def test_loudness_of_a_reference_tone():
    # BS.1770: a 1 kHz sine at 0.1 amplitude in both channels reads -20 LUFS (K-weighting is +0.7 dB at 1 kHz, the -0.691 offset removes it)
    assert A.integrated_lufs(tone(1000, 5)) == pytest.approx(-20.0, abs=0.3)


def test_true_peak_sees_more_than_sample_peak():
    x = tone(11025, 1, 0.9)       # a tone at SR/4.35 whose samples miss the crest
    assert A.true_peak_db(x) >= A.sample_peak_db(x) - 1e-6


def test_phone_simulation_drops_the_low_end_and_keeps_speech():
    low, mid = A.phone_sim(tone(80, 2)), A.phone_sim(tone(1000, 2))
    assert A.sample_peak_db(low[SR // 2:]) < -35 and A.sample_peak_db(mid[SR // 2:]) == pytest.approx(A.sample_peak_db(tone(1000, 1)), abs=1.0)


# ------------------------------------------------------------------ AUDIO-DIALOGUE-CLARITY
def test_clear_mix_passes():
    v = speechlike(20)
    bed = tone(440, 20, 0.0035)
    fails, m = A.check_dialogue_clarity(stems(v, bed))
    assert not fails and m["median_db"] > 20


def test_a_bed_a_phone_cannot_hear_does_not_fake_a_pass_for_earbuds():
    v = speechlike(20)
    loud_sub = tone(55, 20, 0.12)                                           # as loud as the voice, but under 300 Hz
    phone = A.clarity(v, loud_sub)["median_db"]
    buds = A.clarity(v, loud_sub, sim=A.earbud_sim)["median_db"]
    assert phone > buds + 10        # the phone simulation does not hear it, earbuds do: the audit reports both


def test_loud_music_on_the_words_fails_the_check():
    v = speechlike(20)
    fails, m = A.check_dialogue_clarity(stems(v, tone(900, 20, 0.12)))
    assert any(f.startswith("AUDIO-DIALOGUE-CLARITY") for f in fails) and m["median_db"] < 10


def test_one_cue_on_top_of_a_word_fails_even_if_the_rest_is_clean():
    v = speechlike(20)
    s = np.zeros_like(v)
    s[int(10.0 * SR):int(10.35 * SR)] = tone(1500, 0.35, 0.2)                # a stinger exactly on a word
    fails, m = A.check_dialogue_clarity(stems(v, None, s))
    assert any("AUDIO-DIALOGUE-CLARITY" in f for f in fails) and m["min_db"] < 8


def test_a_sound_in_the_pause_after_a_word_does_not_count_against_the_word():
    v = speechlike(20)                                                       # words 0..0.35 of every 0.5 s, so 0.35..0.5 is a gap
    s = np.zeros_like(v)
    for k in range(4, 30):
        a = int((k * 0.5 + 0.37) * SR)
        s[a:a + int(0.1 * SR)] = tone(1500, 0.1, 0.2)
    fails, m = A.check_dialogue_clarity(stems(v, None, s))
    assert not fails, (fails, m)


# ------------------------------------------------------------------ AUDIO-MONO
def test_in_phase_mix_passes_mono():
    fails, m = A.check_mono(stems(speechlike(20), tone(330, 20, 0.004)))
    assert not fails and m["mono_loss_lu"] < 0.2


def test_anti_phase_bed_fails_mono():
    v = speechlike(20)
    bed = tone(330, 20, 0.12)
    bed[:, 1] *= -1                                                          # left and right cancel when folded
    fails, m = A.check_mono(stems(v, bed))
    assert any(f.startswith("AUDIO-MONO") for f in fails)


def test_anti_phase_voice_is_caught_by_the_mono_fold():
    v = speechlike(20)
    v[:, 1] *= -1
    fails, _ = A.check_mono(stems(v, tone(330, 20, 0.004)))
    assert any(f.startswith("AUDIO-MONO") for f in fails)


# ------------------------------------------------------------------ AUDIO-PEAK
def test_peak_passes_for_a_mix_under_the_ceiling():
    v = speechlike(10, 0.2)
    fails, m = A.check_peak(stems(v))
    assert not fails and m["true_peak_dbtp"] < -1.0


def test_peak_fails_on_a_hot_mix_and_on_clipped_samples():
    v = speechlike(10, 0.2)
    hot = stems(v * 4.5)
    fails, m = A.check_peak(hot)
    ids = " ".join(fails)
    assert "AUDIO-PEAK true peak" in ids and m["clipped_samples"] >= 0
    clipped = speechlike(10, 0.2)
    clipped[1000:1010] = 1.0
    f2, m2 = A.check_peak(stems(clipped))
    assert m2["clipped_samples"] == 20 and any("clipped" in x for x in f2)


def test_peak_fails_when_a_sound_effect_is_louder_than_the_dialogue():
    v = speechlike(10, 0.1)
    s = tone(1500, 10, 0.3)
    f, m = A.check_peak(stems(v, None, s))
    assert any("louder than the dialogue" in x for x in f)


def test_run_checks_reads_stems_from_disk(tmp_path):
    v = speechlike(10, 0.1)
    for k, x in stems(v, tone(440, 10, 0.003)).items():
        A.write_wav(tmp_path / f"{k}.wav", x)
    fails, metrics = A.run_checks(tmp_path)
    assert not fails and set(metrics) == {"dialogue_clarity", "mono", "peak"}


# ------------------------------------------------------------------ ducking
def test_duck_envelope_is_unity_away_from_voice_and_at_depth_under_it():
    act = np.zeros(1000, dtype=bool)
    act[300:500] = True                                                      # 3 s .. 5 s
    env = M.duck_envelope(act, 10 * SR, 9.0)
    assert env[int(1.0 * SR)] == pytest.approx(1.0, abs=1e-3)
    assert 20 * np.log10(env[int(4.0 * SR)]) == pytest.approx(-9.0, abs=0.3)
    assert env[int(9.5 * SR)] > 0.97


def test_duck_starts_before_the_voice_and_bridges_word_gaps():
    act = np.zeros(1000, dtype=bool)
    act[300:340] = True
    act[360:400] = True                                                      # a 0.2 s gap between two words
    env = M.duck_envelope(act, 10 * SR, 10.0, lead_s=0.08, bridge_s=0.3)
    assert env[int(2.97 * SR)] < env[int(2.0 * SR)]                          # already going down 30 ms before the voice
    assert 20 * np.log10(env[int(3.5 * SR)]) < -8.0                          # still ducked inside the gap: no pumping between words


def test_duck_releases_after_a_long_pause():
    act = np.zeros(1000, dtype=bool)
    act[100:200] = True
    env = M.duck_envelope(act, 10 * SR, 10.0)
    assert env[int(5.0 * SR)] > 0.95


# ------------------------------------------------------------------ levels and presets
def test_cue_levels_are_relative_to_the_dialogue_and_clamped():
    P = M.PRESETS["phone-first"]
    fg = M.cue_target_lufs({"kind": "transition", "sound": "whoosh"}, -20.0, P)
    bg = M.cue_target_lufs({"kind": "foley", "sound": "pen"}, -20.0, P)
    assert fg > bg and fg < -20.0 and bg < -20.0                              # a transition sits above foley, both under the voice
    assert M.cue_target_lufs({"kind": "transition", "sound": "horn"}, -20.0, P) > fg       # the horn is the one dramatic cue
    assert M.cue_gain_db(-50.0, -20.0) == 30.0 and M.cue_gain_db(0.0, -80.0) == -40.0


def test_preset_numbers_are_sane():
    for name, P in M.PRESETS.items():
        assert P["voice_target_lufs"] < -14.0
        assert P["bed_below_voice_lu"] >= 12 and all(v > 0 for v in P["duck_db"].values())
        assert P["rel_db"]["transition"] > P["rel_db"]["foley"]
        assert set(P["sound_adj_db"]) <= set(S.LIB)
        assert P["voice_limit"] < 0.6


def test_every_sound_has_a_band_that_leaves_a_phone_something_to_play():
    for sid in S.LIB:
        hp, lp = M.SFX_BAND.get(sid, M.SFX_BAND["default"])
        assert hp >= 80 and lp > hp * 4


def test_voice_chain_has_the_phone_first_stages_in_order():
    P = M.PRESETS["phone-first"]
    c = M.voice_chain(P, deess=True).split(",")
    assert c[0].startswith("highpass") and any(x.startswith("equalizer") for x in c) and c[-1].startswith("acompressor")
    assert c.index(P["deess"]) < len(c) - 1 and P["deess"] not in M.voice_chain(P, deess=False)


def test_bed_pad_is_deterministic_and_audible_on_a_phone():
    a, b = M.synth_pad(8.0), M.synth_pad(8.0)
    assert np.array_equal(a, b)
    shaped = a
    full = A.integrated_lufs(shaped)
    phone = A.integrated_lufs(M.phone_stereo(shaped))
    assert full - phone < 14           # the old bed lost 14 to 22 LU on a phone; the pad keeps most of its level
    assert A.correlation_per_second(shaped).mean() > 0.7                      # same waveform in both channels, only the swell differs: wide enough to move, never out of phase


def test_bed_pad_is_mono_safe():
    s = M.synth_pad(8.0)
    mono_i = A.integrated_lufs(np.repeat(A.mono(s), 2, axis=1))
    assert A.integrated_lufs(s) - mono_i < 0.5


def test_stacked_duplicates_are_dropped_not_added_up():
    cues = [{"t": 64.075, "sound": "bell", "kind": "transition"}, {"t": 64.125, "sound": "bell", "kind": "foley"}, {"t": 69.1, "sound": "watch", "kind": "foley"}, {"t": 20.0, "sound": "bell", "kind": "foley"}]
    keep, dropped = S.dedupe_stacked(cues)
    assert [c["t"] for c in keep] == [64.075, 69.1, 20.0] and len(dropped) == 1
    pops = [{"t": 91.308, "sound": "pop", "kind": "choice"}, {"t": 91.308, "sound": "pop", "kind": "choice"}, {"t": 92.0, "sound": "pop", "kind": "choice"}]
    k2, d2 = M.dedupe_cues(pops)
    assert len(k2) == 2 and len(d2) == 1


# ------------------------------------------------------------------ the sfx library (recorded licences, phone-playable)
SFX = Path(S.SFX_DIR)


@pytest.mark.skipif(not (SFX / "horn-ship-v2-own.wav").is_file(), reason="sfx files are git-ignored; run calm_sfx.py synth")
def test_horn_v2_is_playable_on_a_phone_and_v1_was_not():
    v2 = M.sfx_audit()
    by = {r["file"]: r for r in v2}
    assert by["horn-ship-v2-own.wav"]["phone_loss_db"] < 5 and by["horn-ship-v2-own.wav"]["under_200_pct"] < 60
    if "horn-ship-own.wav" in by:
        assert by["horn-ship-own.wav"]["phone_loss_db"] > 8


@pytest.mark.skipif(not (SFX / "ratchet-v2-own.wav").is_file(), reason="sfx files are git-ignored; run calm_sfx.py synth")
def test_all_library_sounds_have_a_licence_row_and_a_matching_sha():
    reg = S.parse_licences()
    bad = [S.licence_problems(f"assets/audio/sfx/{f}", lid, reg) for f, lid in S.LIB.values() if (SFX / f).is_file()]
    assert not [b for b in bad if b]


def test_replaced_sounds_keep_their_old_files_registered():
    assert S.LIB["horn"][0] == "horn-ship-v2-own.wav" and S.LIB["horn-v1"][0] == "horn-ship-own.wav"
    assert S.LIB["ink"][1] == "sfx-ink-splash-v2-own" and S.LIB["watch"][1] == "sfx-ratchet-v2-own" and S.LIB["hum"][1] == "sfx-hum-v2-own"


# ------------------------------------------------------------------ the whole chain on a tiny synthetic episode (needs ffmpeg)
@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_render_a_tiny_episode_end_to_end(tmp_path):
    from scipy.io import wavfile
    total = 12.0
    voice_dir = tmp_path / "voice"
    voice_dir.mkdir()
    rng = np.random.default_rng(3)
    for lid, amp in (("L01", 0.05), ("L02", 0.2)):                           # two takes at very different levels: the bus must bring them together
        x = speechlike(4.0, amp)[:, 0]
        x = np.interp(np.arange(int(4.0 * 24000)) / 24000, np.arange(len(x)) / SR, x)
        wavfile.write(str(voice_dir / f"{lid}.trimmed.wav"), 24000, x.astype("float32"))
    pop = tmp_path / "pop.wav"
    wavfile.write(str(pop), SR, np.repeat(tone(700, 0.3, 0.5)[:, :1], 2, axis=1))
    tl = {"total_s": total, "items": [{"id": "s01", "kind": "scene", "line": "L01", "voice_t0": 0.5, "t0": 0.0, "t1": 6.0}, {"id": "s02", "kind": "scene", "line": "L02", "voice_t0": 6.5, "t0": 6.0, "t1": 12.0}]}
    work = tmp_path / "work"
    work.mkdir()
    (work / "timeline.json").write_text(json.dumps(tl))
    (work / "sfx.json").write_text(json.dumps({"cues": [{"t": 5.8, "sound": "whoosh", "file": str(pop), "kind": "transition"}, {"t": 3.0, "sound": "pen", "file": str(pop), "kind": "foley"}]}))
    ep = SimpleNamespace(timeline_p=work / "timeline.json", work=work, mix=work / "mix.wav", take=lambda lid: voice_dir / f"{lid}.trimmed.wav")
    rep = M.render(ep, "phone-first")
    assert rep["loudness_python"]["integrated_lufs"] == pytest.approx(-14.0, abs=0.4)
    assert rep["loudness_python"]["true_peak_dbtp"] <= -1.0
    t = {k["line"]: k for k in rep["takes"]}
    assert abs(t["L01"]["lufs_after_chain"] + t["L01"]["gain_db"] - (t["L02"]["lufs_after_chain"] + t["L02"]["gain_db"])) < 0.1     # both takes land at the same level
    fails, m = A.run_checks(work / "audio" / "stems", ep.mix)
    assert not fails, fails
    # the cue peaks stay under the dialogue
    assert all(c["gain_db"] < 40 for c in rep["cues"])
