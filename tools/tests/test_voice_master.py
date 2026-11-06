"""The one mastering chain (tools/voice_master.py) and its profile (tools/sound_profile.json). Offline: synthetic takes, plus the real
E01C / d2 takes when the main checkout has them (skipped otherwise)."""
import json
from pathlib import Path

import numpy as np
import pytest

import voice_master as VM

RATE = 24000
PROFILE = VM.load_profile()
MAIN = Path(r"<repo>\work")


def take(seconds=3.0, f0=120.0, noise_db=-70.0, sib=0.0, level=0.3, seed=3, pads=True):
    """Speech-like take: harmonic syllables (4 Hz), two real pauses, a noise floor, optional sibilant bursts, trim_take's zero pads."""
    rng = np.random.default_rng(seed)
    n = int(seconds * RATE)
    t = np.arange(n) / RATE
    ph = rng.uniform(0, 2 * np.pi, 30)                                  # random harmonic phases: a voice's crest factor, not a sawtooth's
    voiced = sum(np.sin(2 * np.pi * f0 * k * t + ph[k]) / k ** 1.3 for k in range(1, 30) if f0 * k < 5000)   # a voice's roll-off: no sibilance of its own
    env = np.clip(np.sin(2 * np.pi * 2.0 * t), 0, None) ** 0.6
    env[(t > 0.9) & (t < 1.25)] = 0.0
    env[(t > 2.0) & (t < 2.3)] = 0.0
    x = level * env * voiced / 3.0
    if sib:
        hiss = rng.standard_normal(n)
        from scipy import signal
        hiss = signal.sosfilt(signal.butter(4, [5200, 9000], btype="bandpass", fs=RATE, output="sos"), hiss)
        burst = ((t % 0.5) > 0.35) & ((t % 0.5) < 0.45)
        x = x + sib * hiss * burst
    x = x + 10 ** (noise_db / 20) * rng.standard_normal(n) * 0.5
    if pads:
        x = np.concatenate([np.zeros(int(0.08 * RATE)), x, np.zeros(int(0.15 * RATE))])
    return np.clip(x, -0.99, 0.99)


def test_profile_has_a_why_for_every_stage_and_both_roles():
    roles = PROFILE["voice"]["take_chain"]["roles"]
    assert set(roles) == {"narrator", "dialogue"}
    for r in roles.values():
        for stage in ("highpass", "denoise", "eq", "deess", "comp", "limit"):
            assert r.get(f"{stage}_why"), stage
    for sec in ("bed", "sfx", "duck", "master", "delivery", "silence", "compose"):
        assert PROFILE[sec].get("why"), sec
    assert PROFILE["checks"]["voice_master"]["why"] and PROFILE["voice"]["measure"]["why"]
    assert PROFILE["master"]["lufs_target"] == -14.0 and PROFILE["delivery"]["instagram"]["true_peak_max_dbtp"] == -1.0


@pytest.mark.parametrize("role", ["narrator", "dialogue"])
def test_contract_same_length_no_clip_on_target_under_ceiling(role):
    x = take(f0=110 if role == "narrator" else 210)
    y, rep = VM.master_take(x, RATE, role)
    R = VM.role_params(role)
    assert len(y) == len(x)
    assert np.abs(y).max() < 1.0
    assert abs(rep["after"]["lufs"] - R["lufs_target"]) <= 0.3
    assert rep["after"]["true_peak_dbtp"] <= R["limit"]["ceiling_dbtp"] + 0.05
    assert VM.contract_problems(x, y, rep) == []
    assert VM.gate_problems(rep, role) == []


def test_never_clips_a_hot_take_and_never_lengthens():
    x = take(level=0.9)
    y, rep = VM.master_take(x, RATE, "dialogue")
    assert len(y) == len(x) and np.abs(y).max() < 1.0
    assert rep["after"]["true_peak_dbtp"] <= VM.role_params("dialogue")["limit"]["ceiling_dbtp"] + 0.05


def test_no_new_digital_silence_and_pads_stay_zero():
    x = take(noise_db=-40.0)
    y, rep = VM.master_take(x, RATE, "narrator")
    assert rep["after"]["zero_runs"] <= rep["before"]["zero_runs"] == 0
    lead = int(0.08 * RATE)
    assert np.all(y[:lead] == 0.0)                     # causal filters: the lead pad is untouched
    inner = y[lead:-int(0.15 * RATE)]
    assert VM.zero_runs(inner, RATE, 20) == 0          # the expander lowers the noise, it never gates it to zero


def test_deterministic():
    x = take()
    a, _ = VM.master_take(x, RATE, "dialogue")
    b, _ = VM.master_take(x, RATE, "dialogue")
    assert np.array_equal(a, b)


def test_second_pass_is_a_no_op_once_in_spec():
    y, rep = VM.master_take(take(), RATE, "dialogue")
    if VM.in_spec(y, RATE, "dialogue"):
        pytest.fail(f"the chain's own output is not in spec: {VM.in_spec(y, RATE, 'dialogue')}")
    y2, rep2 = VM.master_take(y, RATE, "dialogue")
    assert "bypass" in rep2["stages"] and np.array_equal(y2, y)
    assert VM.idempotence_problems(VM.idempotence(y, RATE, "dialogue")) == []


def test_denoise_lowers_a_noisy_floor_and_leaves_a_clean_one():
    x = take(noise_db=-50.0)
    before = VM.measure(x, RATE)["noise_rel_db"]
    noisy, rep = VM.master_take(x, RATE, "narrator")
    m = VM.measure(noisy, RATE)
    assert before is not None and before > VM.role_params("narrator")["denoise"]["skip_if_noise_rel_at_or_below_db"]
    assert rep["stages"]["denoise"]["applied"] and m["noise_rel_db"] <= PROFILE["checks"]["voice_master"]["max_noise_rel_db"]
    clean_in = take(noise_db=-90.0)
    _, rep = VM.master_take(clean_in, RATE, "narrator")
    assert rep["stages"].get("denoise", {}).get("applied") in (False, None)


def test_deess_only_on_a_hot_take():
    _, hot = VM.master_take(take(sib=0.03), RATE, "dialogue")
    _, calm = VM.master_take(take(), RATE, "dialogue")
    assert hot["stages"]["deess"]["applied"] and not calm["stages"]["deess"]["applied"]
    x = take(sib=0.03)
    M = PROFILE["voice"]["measure"]
    c = {**VM.role_params("dialogue")["deess"], "when_db": VM.role_params("dialogue")["deess_when_db"]}
    y, info = VM.stage_deess(x, RATE, c, M)
    assert info["applied"] and VM.sibilance(y, RATE) < VM.sibilance(x, RATE) - 1.0
    z, info = VM.stage_deess(take(), RATE, c, M)
    assert not info["applied"] and np.array_equal(z, take())         # under the switch: exact bypass


def test_eq_never_boosts_mud_or_cuts_presence():
    _, rep = VM.master_take(take(), RATE, "narrator")
    eq = rep["stages"]["eq"]
    assert eq.get("mud_db", 0.0) <= 0.0 and eq.get("presence_db", 0.0) >= 0.0


def test_gate_names_each_fault():
    R = VM.role_params("dialogue")
    good = {"lufs": R["lufs_target"], "true_peak_dbtp": R["limit"]["ceiling_dbtp"] - 1, "noise_rel_db": -50.0, "sibilance_db": -30.0, "zero_runs": 0}
    assert VM.gate_problems(good, "dialogue") == []
    bad = dict(good, lufs=R["lufs_target"] - 2, true_peak_dbtp=-1.0, noise_rel_db=-20.0, sibilance_db=-5.0, zero_runs=1)
    msgs = " ".join(m for _, m in VM.gate_problems(bad, "dialogue"))
    for word in ("loudness", "true peak", "noise floor", "sibilance", "digital-silence"):
        assert word in msgs


def test_role_of_and_unknown_role():
    assert VM.role_of("narrator") == "narrator" and VM.role_of("hero") == "dialogue" and VM.role_of(None) == "dialogue"
    with pytest.raises(ValueError):
        VM.master_take(take(), RATE, "chorus")


def test_silent_take_is_refused():
    with pytest.raises(ValueError):
        VM.master_take(np.zeros(RATE), RATE, "narrator")


def test_master_file_cli_refuses_to_overwrite_its_input(tmp_path):
    p = tmp_path / "a.wav"
    VM.write16(p, take(), RATE)
    assert VM.main(["master", str(p), str(p), "--role", "narrator"]) == 2
    assert VM.main(["master", str(p), str(tmp_path / "b.wav"), "--role", "narrator"]) == 0
    x, sr = VM.read(tmp_path / "b.wav")
    assert sr == RATE and len(x) == len(VM.read(p)[0])


REAL = sorted((MAIN / "voice" / "E01C").glob("L0[1-4].trimmed.wav")) + sorted((MAIN / "voice-trial" / "narrator-deep" / "audio" / "chatterbox-d2").glob("L0[12].wav"))


@pytest.mark.skipif(not REAL, reason="main checkout's E01C / d2 takes not on this machine")
@pytest.mark.parametrize("path", REAL, ids=[p.parent.name + "/" + p.name for p in REAL])
def test_real_takes_meet_the_gate_and_the_contract(path):
    role = "dialogue" if path.name.startswith("L04") and "E01C" in str(path) else "narrator"
    x, sr = VM.read(path)
    y, rep = VM.master_take(x, sr, role)
    assert VM.contract_problems(x, y, rep) == [] and VM.gate_problems(rep, role) == []
    assert VM.idempotence_problems(VM.idempotence(y, sr, role)) == []


# ---------------------------------------------------------------- the profile is the one source: the mix modules read it, values unchanged
def test_mix_modules_read_the_profile_with_their_old_values():
    import audio_checks as A
    import calm_compose as CC
    import calm_mix as M
    import compose as C
    assert A.THRESH == A.THRESH_LITERAL
    assert (C.LOUD_TARGET_I, C.LOUD_TOL, C.LOUD_TP_MAX, C.LOUD_TP_TARGET, C.LOUD_LRA, C.VOICE_LUFS, C.BED_LUFS, C.SFX_GAIN_DB) == (-14.0, 1.0, -1.0, -1.5, 11.0, -16.0, -23.0, -18.0)
    assert (CC.LOUD_I, CC.LOUD_TP, CC.LOUD_LRA, CC.SILENCE_MAX_S) == (-14.0, -1.5, 4.5, 0.6)
    P = M.PRESETS["phone-first"]
    assert P["voice_target_lufs"] == -19.0 and P["voice_eq"] == [(220, 0.9, -3.0), (3200, 0.8, 2.5)] and P["voice_limit"] == 0.42
    assert P["comp"] == "acompressor=threshold=0.063:ratio=2.5:attack=8:release=160:knee=4:makeup=1" and P["duck_db"] == {"bed": 9.0, "fg": 8.0, "bg": 9.0}
    assert M.SFX_BAND["page"] == (350, 10000) and M.INTRO_DIP_DB == 12.0 and (M.LOUD_I, M.LOUD_TP) == (-14.0, -1.5)
    assert VM.role_params("dialogue")["lufs_target"] == P["voice_target_lufs"]      # a mastered take arrives where calm_mix levels takes


def test_calm_loudness_gate_reads_the_profile():
    src = (Path(VM.TOOLS) / "calm_compose.py").read_text(encoding="utf-8")
    assert "-15.0 <= loud" not in src and 'SOUND["delivery"]["instagram"]' in src


def test_calm_mix_skips_its_chain_for_a_mastered_take(tmp_path):
    import calm_mix as M
    t = tmp_path / "L01.trimmed.wav"
    VM.write16(t, take(), RATE)
    assert M.master_record(t) is None
    (tmp_path / "L01.trimmed.master.json").write_text(json.dumps({"role": "narrator"}), encoding="utf-8")
    assert M.master_record(t) == {"role": "narrator"}


# ------------------------------------------------------------------ the expander acts on true pauses only (owner, 2026-10-26)
def _words_with_quiet_endings(seed=2):
    """Two words, each followed by a soft voiced ending 27 dB under the word and a 0.35 s pause with a room noise 42 dB under the word."""
    from scipy import signal
    r = np.random.default_rng(seed)
    t = lambda s: np.arange(int(s * RATE)) / RATE
    def v(sec, amp, f0=120.0):
        x = t(sec)
        return amp * sum(np.sin(2 * np.pi * f0 * k * x + k) / k ** 1.2 for k in range(1, 25))
    noise = lambda s: 10 ** (-62 / 20) * r.standard_normal(int(s * RATE))
    word = lambda: v(0.45, 0.06)
    ending = lambda: v(0.2, 0.06 * 10 ** (-27 / 20)) * np.linspace(1.0, 0.6, int(0.2 * RATE))
    segs = [noise(0.3), word(), ending(), noise(0.35), word(), ending(), noise(0.35)]
    return np.concatenate(segs), np.cumsum([0] + [len(s) for s in segs])


def test_expander_leaves_voiced_endings_alone_and_lowers_the_pauses():
    x, b = _words_with_quiet_endings()
    c = VM.role_params("narrator")["denoise"]
    y, info = VM.stage_denoise(x, RATE, c, PROFILE["voice"]["measure"])
    assert info["applied"]
    fr = lambda z: VM.frame_db(z, RATE, PROFILE["voice"]["measure"])[0]
    a, o = fr(x), fr(y)
    sl = lambda i: slice(int(b[i] / RATE * 100) + 3, int(b[i + 1] / RATE * 100) - 3)
    for seg in (1, 2, 4, 5):                                             # both words and both soft endings
        assert np.abs(o[sl(seg)] - a[sl(seg)]).max() <= 1.0, seg
    for seg in (3,):                                                      # the real pause
        assert (a[sl(seg)] - o[sl(seg)]).max() >= 6.0


def test_the_old_expander_did_pull_the_endings_down():
    """The regression this fix is for: without voice.measure.pause the same take loses its soft endings."""
    import copy
    x, b = _words_with_quiet_endings()
    M = copy.deepcopy(PROFILE["voice"]["measure"])
    M.pop("pause")
    y, _ = VM.stage_denoise(x, RATE, VM.role_params("narrator")["denoise"], M)
    a, o = (VM.frame_db(z, RATE, M)[0] for z in (x, y))
    sl = slice(int(b[2] / RATE * 100) + 3, int(b[3] / RATE * 100) - 3)
    assert (a[sl] - o[sl]).max() > 3.0


def test_noise_floor_is_read_from_the_true_pauses():
    x, _ = _words_with_quiet_endings()
    m = VM.measure(x, RATE)
    assert m["noise_rel_db"] is not None and m["noise_all_rel_db"] is not None
    assert m["noise_rel_db"] <= m["noise_all_rel_db"] + 0.01             # soft endings sit above the room, so the all-frames median is never lower


def test_profile_pause_keys_have_a_reason():
    p = PROFILE["voice"]["measure"]["pause"]
    assert p["pad_s"] > 0 and p["pause_min_s"] > 0 and len(p["why"]) > 200 and "PLACEHOLDER" not in p["why"]


def test_every_cast_voice_has_a_fitted_gen_cap():
    G = PROFILE["take"]["gen_cap"]
    cast = {"narrator", "hero", "extra", "han", "rival", "lead", "partner", "guide"}
    assert cast <= set(G["voices"])
    for name, v in G["voices"].items():
        assert v["takes"] == len(v["measured"]) >= 1 and v["slowest_letters_per_s"] > 0 and len(v["ref_sha256"]) == 64 and v["source"] and v["fit"]
        lo = min(v["measured"].values())
        assert v["slowest_letters_per_s"] <= lo + 1e-9                    # never faster than the slowest take it was fitted on
        if v["takes"] < 3:
            assert v["slowest_letters_per_s"] <= lo * G["thin_sample_spread"] + 0.01
        for letters in (8, 20, 45):                                       # the cap leaves room for the slowest measured reading
            assert G["base_s"] + letters / (v["slowest_letters_per_s"] / G["margin"]) >= letters / lo + 0.5


# ---- R-472: the chain never brings the pauses closer to the voice than the take came in (E01C L05/L13/L19/L22/L23, 2026-10-27)
def _dip_take(seconds=3.0, dip_db=-23.5, seed=5):
    """Syllables 0.28 s long with a 0.12 s soft dip between them (in-phrase, shorter than the 0.2 s pause line), so the soft
    frames sit about `dip_db` under the loud part, as in the E01C narrator takes whose pause distance sat at -24.1 to -24.6 dB."""
    rng = np.random.default_rng(seed)
    n = int(seconds * RATE)
    t = np.arange(n) / RATE
    ph = rng.uniform(0, 2 * np.pi, 30)
    voiced = sum(np.sin(2 * np.pi * 110 * k * t + ph[k]) / k ** 1.3 for k in range(1, 30)) / 3.0
    loud = ((t % 0.40) < 0.28).astype(float)
    ramp = np.convolve(loud, np.ones(240) / 240, mode="same")
    env = 10 ** (dip_db / 20) + (1 - 10 ** (dip_db / 20)) * ramp
    x = 0.4 * env * voiced + 10 ** (-72 / 20) * rng.standard_normal(n) * 0.5
    return np.clip(np.concatenate([np.zeros(int(0.08 * RATE)), x, np.zeros(int(0.15 * RATE))]), -0.99, 0.99)


def _tq_rel(x):
    import voice as V
    return V.take_profile([float(v) for v in x], RATE)["pause_rel_db"]


def _profile_without_floor():
    import copy
    P = copy.deepcopy(PROFILE)
    for r in P["voice"]["take_chain"]["roles"].values():
        r["comp"]["pause_floor"] = False
    return P


def test_compressor_alone_lifts_the_pauses_and_the_floor_stage_takes_it_back():
    x = _dip_take()
    came_in = VM._tq_pause_rel(x, RATE, PROFILE["voice"]["measure"])[0]
    assert came_in is not None
    y_off, rep_off = VM.master_take(x, RATE, "narrator", _profile_without_floor())
    y_on, rep_on = VM.master_take(x, RATE, "narrator")
    assert "pause_floor" not in rep_off["stages"]
    assert _tq_rel(y_off) > came_in + 1.0, "the test take must show the lift, or it proves nothing"
    assert rep_on["stages"]["pause_floor"]["applied"]
    assert _tq_rel(y_on) <= round(came_in, 1) + 0.05
    assert VM.contract_problems(x, y_on, rep_on) == []
    assert VM.gate_problems(rep_on, "narrator") == []


def test_floor_stage_moves_only_frames_that_are_soft_and_never_raises():
    M = PROFILE["voice"]["measure"]
    x = _dip_take()
    y, _ = VM.master_take(x, RATE, "narrator", _profile_without_floor())                              # the loud part fell, the soft frames did not
    ref = x
    z, info = VM.stage_pause_floor(ref, y, RATE, VM.role_params("narrator")["comp"], M)
    assert info["applied"]
    db, hop, win = VM.frame_db(ref, RATE, M)
    quiet = db < np.sort(db)[int(len(db) * 0.95)] - M["pause_below_p95_db"]
    solid = np.nonzero(~np.convolve(quiet, np.ones(7), mode="same").astype(bool))[0]                  # frames with no soft frame within 3 either side
    assert len(solid) > 50
    for k in solid:
        a, b = k * hop, k * hop + win
        assert np.array_equal(z[a:b], y[a:b]), "a frame above the pause line changed"
    assert np.all(np.abs(z) <= np.abs(y) + 1e-12), "the stage raised a sample"


def test_floor_stage_is_a_no_op_when_the_distance_already_holds_and_when_off_the_take():
    M = PROFILE["voice"]["measure"]
    x = take()
    z, info = VM.stage_pause_floor(x, x, RATE, VM.role_params("narrator")["comp"], M)
    assert not info["applied"] and np.array_equal(z, x)


def test_profile_comp_has_the_pause_floor_keys_for_both_roles():
    for role in ("narrator", "dialogue"):
        c = VM.role_params(role)["comp"]
        assert c["pause_floor"] is True and c["pause_floor_step_db"] > 0 and c["pause_floor_max_db"] > c["pause_floor_step_db"]


E01C_TAKES = ["L05", "L13", "L19", "L22", "L23"]


@pytest.mark.skipif(not (MAIN / "voice" / "E01C" / "L05.wav").exists(), reason="E01C raw takes are not in this checkout")
@pytest.mark.parametrize("line", E01C_TAKES)
def test_e01c_takes_that_the_compressor_pushed_over_the_pause_limit_now_pass(line):
    import voice as V
    raw, rate = V.read_float(MAIN / "voice" / "E01C" / f"{line}.wav")
    trimmed, _ = V.trim_take(raw, rate, None)
    y, rep = VM.master_take(np.asarray(trimmed, dtype="float64"), rate, "narrator")
    out = [float(v) for v in y]
    assert V.take_quality_problems(V.take_profile(out, rate)) == []
    assert V.edge_noise_problems(out, rate) == []
    assert VM.gate_problems(VM.measure(y, rate), "narrator") == [] and VM.contract_problems(trimmed, y, rep) == []
