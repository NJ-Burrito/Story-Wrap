"""Word-safe edge cleaner and VOICE-EDGE-NOISE (owner, 2026-10-26: noise-only windows before or after the words).
Offline: synthetic fixtures, one real regression fixture (j03 L01, the take with the 3.97 s noise tail), a fake EOS analyzer."""
import math
from pathlib import Path

import numpy as np
import pytest

import voice
import voice_edges as VE

RATE = 24000
FIX = Path(__file__).parent / "fixtures" / "audio" / "j03-L01-raw-tail.npz"
E = VE.params()


def t(n_s):
    return np.arange(int(n_s * RATE)) / RATE


def vowel(seconds, f0=110.0, amp=0.25):
    """Voiced, speech-like: harmonics with formant-ish weights (energy in 250 Hz-4 kHz) and a syllable wobble."""
    x = t(seconds)
    w = {1: 1.0, 2: 0.9, 3: 1.2, 4: 1.0, 5: 0.6, 6: 0.5, 7: 0.7, 8: 0.5, 9: 0.3, 10: 0.25, 12: 0.2, 15: 0.15, 20: 0.1}
    s = sum(a * np.sin(2 * np.pi * f0 * k * x) for k, a in w.items())
    return amp * (0.65 + 0.35 * np.sin(2 * np.pi * 4 * x)) * s / sum(w.values())


def band_noise(seconds, lo, hi, rms, seed=1):
    r = np.random.default_rng(seed)
    n = int(seconds * RATE)
    X = np.fft.rfft(r.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / RATE)
    X[(f < lo) | (f > hi)] = 0
    y = np.fft.irfft(X, n)
    return y * rms / (np.sqrt(np.mean(y ** 2)) + 1e-12)


def white(seconds, rms, seed=3):
    return np.random.default_rng(seed).standard_normal(int(seconds * RATE)) * rms


def hum(seconds, amp, f=60.0):
    return amp * np.sin(2 * np.pi * f * t(seconds))


def db2(x):
    return 10 ** (x / 20)


def find(hay, needle):
    """Start index of `needle` inside `hay` (exact samples), or -1."""
    n = len(needle)
    for i in range(0, len(hay) - n + 1):
        if hay[i] == needle[0] and np.array_equal(hay[i:i + n], needle):
            return i
    return -1


# ------------------------------------------------------------------ the cleaner
def test_noise_tail_after_the_words_is_removed_and_the_gate_sees_it():
    room = white(5.0, db2(-62))
    speech = vowel(1.5)
    x = np.concatenate([room[:int(.1 * RATE)], speech, white(.3, db2(-60)), white(2.0, db2(-45), seed=9), room[:int(.2 * RATE)]])
    before = VE.edge_problems(x, RATE)
    assert before and "tail" in before[0]                                         # 2 s of hiss after the words: VOICE-EDGE-NOISE fails
    y, rec = VE.clean(x, RATE)
    assert rec["cut_tail_ms"] > 2000
    assert VE.edge_problems(np.concatenate([np.zeros(2000), y, np.zeros(3600)]), RATE) == []
    i0 = int(round(rec["span"]["onset_s"] * RATE)) - rec["start"]
    i1 = int(round(rec["span"]["offset_s"] * RATE)) - rec["start"]
    src0 = int(round(rec["span"]["onset_s"] * RATE))
    assert np.array_equal(y[i0:i1], x[src0:src0 + (i1 - i0)])                      # nothing inside the span is touched


def test_word_ending_in_a_fricative_is_never_clipped():
    """A final س (4-8 kHz noise, 160 ms, 22 dB under the vowel) is a sound of the word; the hiss after it is not."""
    v = vowel(1.2)
    s = band_noise(.16, 4000, 8000, db2(-22) * np.sqrt(np.mean(v ** 2)), seed=5)
    tail = white(1.5, db2(-58))
    x = np.concatenate([white(.15, db2(-62)), v, s, tail])
    y, rec = VE.clean(x, RATE)
    fric_end = (.15 + 1.2 + .16)
    assert rec["span"]["offset_s"] >= fric_end - .02                               # the span reaches the end of the fricative
    assert rec["end"] / RATE >= fric_end + E["tail_guard_s"] - .02                 # plus the whole guard
    assert find(y, s[: int(.15 * RATE)]) >= 0                                      # the fricative's samples are in the output, unchanged
    assert rec["cut_tail_ms"] > 1000


def test_word_initial_fricative_and_plosive_burst_are_kept():
    """ش before the first vowel, and a ت release (a 15 ms burst) right before it: the onset is the first consonant."""
    v = vowel(1.0)
    sh = band_noise(.12, 2000, 6000, db2(-24) * np.sqrt(np.mean(v ** 2)), seed=7)
    burst = band_noise(.015, 1500, 9000, db2(-15) * np.sqrt(np.mean(v ** 2)), seed=8)
    lead = white(.6, db2(-60))
    x = np.concatenate([lead, burst, white(.03, db2(-60)), sh, v, white(.4, db2(-62))])
    y, rec = VE.clean(x, RATE)
    assert rec["span"]["onset_s"] <= .6 + .01                                      # starts at the burst, not at the vowel (.765)
    assert rec["start"] / RATE <= .6 - E["lead_guard_s"] + .02
    assert rec["cut_lead_ms"] >= 400                                               # most of the 0.6 s noise-only lead-in is gone
    assert find(y, burst) >= 0 and find(y, sh[: int(.1 * RATE)]) >= 0


def test_final_nasal_decay_is_kept():
    """م at the end: periodic at the speaker's pitch, mostly under 250 Hz, decaying well under the vowel."""
    v = vowel(1.0)
    k = t(.18)
    nasal = (0.25 * db2(-20)) * np.exp(-k / .06) * (np.sin(2 * np.pi * 110 * k) + .3 * np.sin(2 * np.pi * 220 * k))
    x = np.concatenate([white(.1, db2(-64)), v, nasal, white(1.0, db2(-64))])
    _, rec = VE.clean(x, RATE)
    assert rec["end"] / RATE >= .1 + 1.0 + .18                                    # the whole decay is inside what is kept


def test_hum_drone_and_breath_far_from_the_words_are_not_speech():
    """The j03 L01 shape: words, a second of quiet, a low drone, then a loud breath burst 3 s later."""
    v = vowel(1.4)
    x = np.concatenate([white(.1, db2(-64)), v, white(1.0, db2(-64)), hum(1.5, db2(-40), 70.0) + white(1.5, db2(-64)),
                        white(1.0, db2(-62)), white(.25, db2(-16), seed=11), white(1.0, db2(-62))])
    s = VE.speech_span(x, RATE)
    assert abs(s["offset_s"] - 1.5) < .08
    y, rec = VE.clean(x, RATE)
    assert len(y) / RATE < 1.4 + E["lead_guard_s"] + E["tail_guard_s"] + .15


def test_a_voiced_run_after_the_text_is_dropped_only_when_the_text_length_says_so():
    v = vowel(1.0)
    x = np.concatenate([white(.1, db2(-64)), v, white(1.5, db2(-64)), vowel(.5, f0=118), white(.3, db2(-64))])
    with_text = VE.speech_span(x, RATE, done_after_s=1.4)
    without = VE.speech_span(x, RATE)
    assert with_text["runon_runs"] == 1 and with_text["offset_s"] < 1.25
    assert without["runon_runs"] == 0 and without["offset_s"] > 3.0               # no text: a late word is never dropped for its position


def test_a_pause_inside_the_line_is_not_an_edge():
    x = np.concatenate([white(.1, db2(-64)), vowel(.9), white(.35, db2(-60)), vowel(.9, f0=105), white(.5, db2(-64))])
    s = VE.speech_span(x, RATE)
    assert s["onset_s"] < .12 and s["offset_s"] > 2.2


def test_silent_audio_is_refused():
    with pytest.raises(ValueError):
        VE.speech_span(np.zeros(RATE), RATE)


def test_fades_are_equal_power_and_inside_the_guards():
    fi, fo = VE.fade(100, out=False), VE.fade(100, out=True)
    assert np.allclose(fi ** 2 + fo ** 2, 1.0)                                   # sin^2 + cos^2: the sum of a fade-in and a fade-out keeps the power
    assert E["fade_in_s"] <= E["lead_guard_s"] and E["fade_out_s"] <= E["tail_guard_s"]


def test_trim_take_keeps_the_contract_and_records_the_edge():
    x = list(np.concatenate([white(.4, db2(-62)), vowel(1.2), white(1.5, db2(-48))]))
    y, info = voice.trim_take(x, RATE)
    assert info["edge"]["method"].startswith("voice_edges.clean")
    assert max(abs(v) for v in y[: int(E["lead_pad_s"] * RATE)]) == 0 and max(abs(v) for v in y[-int(E["tail_pad_s"] * RATE):]) == 0
    assert voice.tail_problems(y, RATE, info) == [] and voice.edge_noise_problems(y, RATE) == []


# ------------------------------------------------------------------ the real take (regression)
def test_real_j03_L01_noise_tail_is_removed_and_the_last_word_kept():
    if not FIX.exists():
        pytest.skip("fixture missing")
    z = np.load(FIX)
    x = z["pcm"].astype("float64") / 32767
    r = int(z["rate"])
    before = VE.noise_edges(x, r)
    assert before["tail_noise_ms"] > 3500                                          # the old path left 3.97 s of noise-only tail on this take
    assert VE.edge_problems(x, r)
    y, info = voice.trim_take(list(x), r)
    last_word_end = 6.68 - float(z["start_s"])                                     # the last voiced frame of the line (raw take, 6.68 s)
    assert info["end"] / r >= last_word_end + .15                                  # the word and its guard are kept
    assert info["cut_end_ms"] > 4500
    assert voice.edge_noise_problems(y, r) == [] and voice.tail_problems(y, r, info) == []


# ------------------------------------------------------------------ prevention at the source
def test_token_cap_per_voice_needs_the_same_reference():
    P = voice.sound_profile()
    txt = "أَنْتُمْ أَمَامَ النَّافِذَةِ الْعَالِيَةِ، وَالرِّيحُ تَفْتَحُهَا. وَحَقِيبَةٌ تَسْقُطُ عَلَى الْمِنْضَدَةْ."
    v = P["take"]["gen_cap"]["voices"]["narrator"]
    old = voice.token_cap(txt)                                                    # unmeasured voice: the old 1 s + 0.2 s per letter
    assert old == math.ceil(25 * (1.0 + 0.2 * voice.letters_of(txt)))
    new = voice.token_cap(txt, "narrator", v["ref_sha256"])
    assert new < old
    assert voice.token_cap(txt, "narrator", "another-clip") == old                 # a recast voice falls back to the default
    rate = v["slowest_letters_per_s"] / P["take"]["gen_cap"]["margin"]
    assert new / 25 >= voice.letters_of(txt) / v["slowest_letters_per_s"] + .5     # never shorter than the slowest measured reading plus room
    assert abs(voice.edge_done_after_s(txt, "narrator", v["ref_sha256"]) - voice.letters_of(txt) / rate) < 1e-9


class FakeAnalyzer:
    """The shape of chatterbox's AlignmentStreamAnalyzer that the guard reads: alignment (T x S), completed_at, eos_idx, step()."""
    def __init__(self, completed_at):
        self.alignment = np.zeros((0, 4))
        self.completed_at = completed_at
        self.eos_idx = 2

    def step(self, logits, next_token=None):
        self.alignment = np.vstack([self.alignment, np.zeros((1, 4))])
        return logits


def test_eos_guard_forces_eos_after_the_budget_and_not_before():
    cls = type("A", (FakeAnalyzer,), {})
    voice.install_eos_guard(cls, 30)
    voice.install_eos_guard(cls, 30)                                               # idempotent
    a = cls(completed_at=10)
    out = None
    for i in range(39):
        out = a.step(np.zeros((1, 5)))
        assert out[0, 2] == 0                                                      # 39 frames, 29 after completion: nothing forced
    out = a.step(np.zeros((1, 5)))
    assert out[0, 2] == 2 ** 15 and out[0, 0] == -2 ** 15 and a.nj_forced_eos
    b = cls(completed_at=None)                                                     # text not complete: the guard never fires
    for _ in range(100):
        assert b.step(np.zeros((1, 5)))[0, 2] == 0


def test_eos_budget_comes_from_the_profile_and_reaches_the_worker_job():
    assert voice.eos_after_complete_tokens() == round(voice.sound_profile()["take"]["eos"]["after_complete_max_s"] * 25)
    src = Path(voice.__file__).read_text(encoding="utf-8")
    assert '"eos_after_complete_tokens": eos_after_complete_tokens()' in src and "install_eos_guard(AlignmentStreamAnalyzer" in src


def test_every_edge_number_has_a_reason_in_the_profile():
    P = voice.sound_profile()
    for k in ("edge", "gen_cap", "eos"):
        assert P["take"][k]["why"] and "PLACEHOLDER" not in P["take"][k]["why"]
    assert P["checks"]["edge_noise"]["why"] and "PLACEHOLDER" not in P["checks"]["edge_noise"]["why"]


# ------------------------------------------------------------------ pause_mask: the frames the mastering expander may lower
def _line_with_decay_and_pause():
    """0.5 s word, a quiet voiced decay (-27 dB under the word, like a soft final م), a 0.4 s pause with room noise, a second word."""
    word = vowel(0.5, amp=0.3)
    decay = vowel(0.25, amp=0.3 * db2(-27)) * np.linspace(1.0, 0.5, int(0.25 * RATE))
    quiet = white(0.4, db2(-62), seed=5)
    x = np.concatenate([white(0.3, db2(-62), seed=4), word, decay, quiet, vowel(0.5, amp=0.3), white(0.3, db2(-62), seed=6)])
    return x, {"word": (0.3, 0.8), "decay": (0.8, 1.05), "pause": (1.05, 1.45), "word2": (1.45, 1.95), "lead": (0.0, 0.3), "tail": (1.95, 2.25)}


def test_pause_mask_protects_every_sound_and_finds_the_true_pauses():
    x, seg = _line_with_decay_and_pause()
    m = VE.pause_mask(x, RATE, pad_s=0.02, pause_min_s=0.06)
    f = lambda a, b: slice(int(a * 100) + 1, int(b * 100) - 2)          # 10 ms hop; stay clear of the window edges
    assert not m["pause"][f(*seg["word"])].any() and not m["pause"][f(*seg["word2"])].any()
    assert not m["pause"][f(*seg["decay"])].any()                       # the quiet voiced ending is a sound of the word, not a pause
    assert m["pause"][f(1.12, 1.42)].all()                              # the middle of the real pause
    assert m["pause"][f(0.0, 0.25)].all() and m["pause"][f(2.0, 2.25)].all()   # lead-in and tail outside the span
    assert (m["pause"] ^ m["protected"]).all()


def test_pause_mask_keeps_a_gap_shorter_than_pause_min_inside_the_phrase():
    word = vowel(0.4, amp=0.3)
    x = np.concatenate([white(0.3, db2(-62), seed=4), word, white(0.05, db2(-62), seed=5), word, white(0.3, db2(-62), seed=6)])
    m = VE.pause_mask(x, RATE, pad_s=0.0, pause_min_s=0.12)
    assert not m["pause"][int(0.3 * 100) + 5:int(1.1 * 100) - 5].any()  # the 50 ms word gap is protected
    m2 = VE.pause_mask(x, RATE, pad_s=0.0, pause_min_s=0.02)
    assert m2["pause"][int(0.7 * 100) + 2:int(0.75 * 100) - 1].any()    # a smaller pause_min lets the expander act on it


def test_pause_mask_raises_on_silence_like_speech_span():
    with pytest.raises(ValueError):
        VE.pause_mask(np.zeros(RATE), RATE, 0.02, 0.06)
