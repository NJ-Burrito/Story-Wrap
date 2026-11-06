# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "scipy"]
# ///
"""Audio measurement and the three phone-first audio checks (owner, 2026-10-25, note C9: "make and mix the sounds better for a normal viewer on his phone").

Pure numpy/scipy, no model, no network, no ffmpeg: every number here can be recomputed from the stem files, so the checks are deterministic and testable.

  uv run tools/audio_checks.py check <ep>      the three checks on work/episodes/<ep>/audio/stems + mix.wav (exit 1 on a failure)
  uv run tools/audio_checks.py analyse <ep>    the full measurement (loudness, balance per scene, sibilance, mud, mono, peaks) as JSON on stdout

Checks (ids are stable; every one runs every time; thresholds are HOUSE defaults in THRESH, measured on E01C before and after, never loosened to pass):
  AUDIO-DIALOGUE-CLARITY  on a phone-speaker simulation (mono, 300 Hz to 8 kHz) the narrator/characters sit far enough above music + sfx while they speak
  AUDIO-MONO              folding to mono does not lose loudness or clarity (no phase cancellation)
  AUDIO-PEAK              true peak under the ceiling, no clipped sample, no cue louder than the dialogue

Stems: `voice.wav`, `bed.wav`, `sfx.wav` are the three buses AFTER ducking and AFTER the master gain, so voice + bed + sfx is the delivered mix (up to the safety limiter).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from scipy import signal
from scipy.io import wavfile

SR = 48000
TOOLS = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parent.parent

# ------------------------------------------------------------------ house thresholds (measured on E01C legacy -> phone-first; see research/sound-e01c.md)
_SOUND = __import__("json").loads((Path(__file__).resolve().parent / "sound_profile.json").read_text(encoding="utf-8"))
THRESH_LITERAL = {   # documentation of each key; the numbers used are the profile's
    "clarity_median_db": 20.0,     # median voice-over-everything-else ratio on the phone simulation, over every voiced 400 ms block
    "clarity_p10_db": 14.0,        # the weakest tenth of voiced blocks
    "clarity_min_db": 8.0,         # no voiced block under this: a cue that eats a word
    "clarity_share_below_db": 12.0, "clarity_share_max": 0.04,   # at most 4 % of voiced blocks under 12 dB
    "mono_loss_lu_max": 1.0,       # mono fold-down may lose at most 1 LU of integrated loudness against stereo
    "mono_clarity_drop_db_max": 1.5,   # and its median clarity ratio may drop at most 1.5 dB against stereo
    "corr_p05_min": 0.2,           # 5th percentile of the L/R correlation per second: not anti-phase
    "tp_max_dbtp": -1.0,           # delivered true peak ceiling (compose.py LOUD_TP_MAX)
    "sample_peak_max_db": -1.0,    # no sample closer than 1 dB to full scale
    "sfx_over_voice_db": 0.0,      # no sfx block may be louder than the dialogue block it sits under (phone simulation) by more than this
}
THRESH = {k: _SOUND["checks"][k] for k in THRESH_LITERAL}   # the values live in tools/sound_profile.json `checks` (2026-10-26); the literal above documents each key and the test asserts they agree
BLOCK_S, HOP_S = 0.4, 0.1


# ------------------------------------------------------------------ io
def read_wav(path) -> tuple[np.ndarray, int]:
    """(samples [n, ch] float32 in -1..1, sample rate)."""
    sr, a = wavfile.read(str(path))
    if a.dtype.kind == "i":
        a = a.astype("float32") / float(2 ** (8 * a.dtype.itemsize - 1))
    else:
        a = a.astype("float32")
    if a.ndim == 1:
        a = a[:, None]
    return a, int(sr)


def write_wav(path, x: np.ndarray, sr: int = SR):
    tmp = Path(str(path) + ".tmp")
    with open(tmp, "wb") as fh:
        wavfile.write(fh, sr, np.asarray(x, dtype="float32"))
    tmp.replace(path)


def to48(x: np.ndarray, sr: int) -> np.ndarray:
    if sr == SR:
        return x
    g = np.gcd(sr, SR)
    return signal.resample_poly(x, SR // g, sr // g, axis=0).astype("float32")


def stereo(x: np.ndarray) -> np.ndarray:
    return np.repeat(x[:, :1], 2, axis=1) if x.shape[1] == 1 else x[:, :2]


def mono(x: np.ndarray) -> np.ndarray:
    return x.mean(axis=1, keepdims=True) if x.shape[1] > 1 else x


# ------------------------------------------------------------------ ITU-R BS.1770 loudness (K-weighting at 48 kHz; the standard's published coefficients)
_KW = np.array([[1.53512485958697, -2.69169618940638, 1.19839281085285, 1.0, -1.69065929318241, 0.73248077421585],
                [1.0, -2.0, 1.0, 1.0, -1.99004745483398, 0.99007225036621]])


def kweight(x: np.ndarray) -> np.ndarray:
    return signal.sosfilt(_KW, x, axis=0)


def block_ms(x: np.ndarray, win_s: float = BLOCK_S, hop_s: float = HOP_S, weighted: bool = True) -> np.ndarray:
    """Mean-square per sliding window, channels summed (L and R weight 1, as BS.1770 does for stereo)."""
    y = kweight(x) if weighted else x
    p = (y.astype("float64") ** 2).sum(axis=1)
    c = np.concatenate([[0.0], np.cumsum(p)])
    w, h = int(win_s * SR), int(hop_s * SR)
    if len(p) < w:
        return np.array([p.mean() if len(p) else 0.0])
    idx = np.arange(0, len(p) - w + 1, h)
    return (c[idx + w] - c[idx]) / w


def lufs(ms) -> np.ndarray | float:
    ms = np.asarray(ms, dtype="float64")
    return -0.691 + 10 * np.log10(np.maximum(ms, 1e-12))


def integrated_lufs(x: np.ndarray) -> float:
    """BS.1770-4 gated integrated loudness: 400 ms blocks, -70 LUFS absolute gate, -10 LU relative gate."""
    ms = block_ms(x)
    keep = ms[lufs(ms) > -70.0]
    if not len(keep):
        return -120.0
    rel = lufs(keep.mean()) - 10.0
    keep = keep[lufs(keep) > rel]
    return float(lufs(keep.mean())) if len(keep) else -120.0


def short_term_series(x: np.ndarray) -> np.ndarray:
    """Short-term (3 s) loudness, every 100 ms."""
    return lufs(block_ms(x, 3.0, 0.1))


def loudness_range(x: np.ndarray) -> float:
    st = short_term_series(x)
    st = st[st > -70.0]
    if not len(st):
        return 0.0
    st = st[st > lufs(np.mean(10 ** ((st + 0.691) / 10))) - 20.0]
    return float(np.percentile(st, 95) - np.percentile(st, 10)) if len(st) else 0.0


def true_peak_db(x: np.ndarray) -> float:
    """4x oversampled peak (BS.1770 Annex 2 approximation) in dB."""
    up = signal.resample_poly(x.astype("float64"), 4, 1, axis=0)
    return float(20 * np.log10(max(np.abs(up).max(), 1e-9)))


def sample_peak_db(x: np.ndarray) -> float:
    return float(20 * np.log10(max(np.abs(x).max(), 1e-9)))


# ------------------------------------------------------------------ listening simulations
def phone_sim(x: np.ndarray) -> np.ndarray:
    """A small phone speaker: mono, high-pass 300 Hz (2nd order), low-pass 8 kHz (4th order). Real speakers also have a resonance bump near 1 to 3 kHz; leaving it out keeps the test strict about the band the voice needs."""
    m = mono(x).astype("float64")
    hp = signal.butter(2, 300, "highpass", fs=SR, output="sos")
    lp = signal.butter(4, 8000, "lowpass", fs=SR, output="sos")
    return signal.sosfilt(lp, signal.sosfilt(hp, m, axis=0), axis=0).astype("float32")


def earbud_sim(x: np.ndarray) -> np.ndarray:
    """Earbuds: stereo, flat from 40 Hz to 16 kHz (2nd order each side)."""
    hp = signal.butter(2, 40, "highpass", fs=SR, output="sos")
    lp = signal.butter(2, 16000, "lowpass", fs=SR, output="sos")
    return signal.sosfilt(lp, signal.sosfilt(hp, stereo(x).astype("float64"), axis=0), axis=0).astype("float32")


def band_db(x: np.ndarray, lo: float, hi: float) -> float:
    """Level (dB re 1.0 RMS) of the band lo..hi Hz of a mono-folded signal, by FFT power."""
    m = mono(x)[:, 0].astype("float64")
    if not len(m):
        return -120.0
    f = np.fft.rfftfreq(len(m), 1 / SR)
    p = np.abs(np.fft.rfft(m * np.hanning(len(m)))) ** 2
    p *= 2 / (np.sum(np.hanning(len(m)) ** 2) * len(m))
    sel = (f >= lo) & (f < hi)
    return float(10 * np.log10(max(p[sel].sum(), 1e-18)))


# ------------------------------------------------------------------ voiced blocks and the clarity ratio
def block_times(n_samples: int, win_s: float = BLOCK_S, hop_s: float = HOP_S) -> np.ndarray:
    w, h = int(win_s * SR), int(hop_s * SR)
    if n_samples < w:
        return np.array([0.0])
    return np.arange(0, n_samples - w + 1, h) / SR


def voiced_mask(voice: np.ndarray) -> np.ndarray:
    """Blocks where somebody is speaking: voice block loudness within 12 LU of the voice's own mean loudness (and above -60 LUFS). Pauses and word gaps fall outside; a 25 LU margin counted breath tails as speech and gave ratios of -30 dB that no listener hears."""
    ms = block_ms(voice)
    l = lufs(ms)
    ref = lufs(ms[l > -60].mean()) if (l > -60).any() else -60.0
    return (l > ref - 12.0) & (l > -60.0)


FRAME_S = 0.02
WIN_FRAMES, HOP_FRAMES = int(BLOCK_S / FRAME_S), int(HOP_S / FRAME_S)


def frame_ms(x: np.ndarray, frame_s: float = FRAME_S) -> np.ndarray:
    """K-weighted mean-square per 20 ms frame (channels summed)."""
    y = kweight(x.astype("float64"))
    p = (y ** 2).sum(axis=1)
    h = int(frame_s * SR)
    n = len(p) // h
    return p[: n * h].reshape(n, h).mean(axis=1)


def clarity(voice: np.ndarray, others: np.ndarray, sim=phone_sim) -> dict:
    """Voice over everything else, through the listening simulation, measured only on the frames where somebody is speaking.
    A frame is speech when the voice is within 20 LU of its own 90th-percentile frame level; a 400 ms window counts when at least 40 % of its frames are speech, and its ratio is
    the voice power over the music + sfx power on THOSE frames. A sound placed in the pause right after a word (a transition landing on the cut) therefore does not count against
    the word; a sound on top of the word does. The mono fold of `sim` makes anti-phase content count."""
    v, o = sim(voice), sim(others)
    n = min(len(v), len(o))
    fv, fo = frame_ms(v[:n]), frame_ms(o[:n])
    k = min(len(fv), len(fo))
    fv, fo = fv[:k], fo[:k]
    dbv = lufs(fv)
    live = dbv[dbv > -70.0]
    if not len(live):
        return {"voiced_blocks": 0, "median_db": 0.0, "p10_db": 0.0, "min_db": 0.0, "share_below": 1.0, "worst": []}
    act = (dbv > np.percentile(live, 90) - 20.0).astype(float)
    cs = lambda a: np.concatenate([[0.0], np.cumsum(a)])
    cv, co, ca = cs(fv * act), cs(fo * act), cs(act)
    idx = np.arange(0, max(k - WIN_FRAMES, 0) + 1, HOP_FRAMES)
    nact = ca[idx + WIN_FRAMES] - ca[idx]
    ok = nact >= 0.4 * WIN_FRAMES
    S = (cv[idx + WIN_FRAMES] - cv[idx])
    N = (co[idx + WIN_FRAMES] - co[idx])
    sbr = np.minimum(10 * np.log10(np.maximum(S, 1e-15) / np.maximum(N, 1e-15)), 60.0)
    s = sbr[ok]
    if not len(s):
        return {"voiced_blocks": 0, "median_db": 0.0, "p10_db": 0.0, "min_db": 0.0, "share_below": 1.0, "worst": []}
    t = idx * FRAME_S
    order = np.argsort(np.where(ok, sbr, 1e9))
    return {"voiced_blocks": int(ok.sum()), "median_db": round(float(np.median(s)), 2), "p10_db": round(float(np.percentile(s, 10)), 2), "min_db": round(float(s.min()), 2),
            "share_below": round(float((s < THRESH["clarity_share_below_db"]).mean()), 4),
            "worst": [{"t": round(float(t[i]), 2), "ratio_db": round(float(sbr[i]), 1)} for i in order[:8] if ok[i]][:5]}


def correlation_per_second(x: np.ndarray) -> np.ndarray:
    s = stereo(x)
    out = []
    for i in range(0, len(s) - SR + 1, SR):
        a, b = s[i:i + SR, 0].astype("float64"), s[i:i + SR, 1].astype("float64")
        d = np.sqrt((a * a).sum() * (b * b).sum())
        if d > 1e-6 * SR:
            out.append(float((a * b).sum() / d))
    return np.array(out) if out else np.array([1.0])


def sibilance_index(voice: np.ndarray) -> dict:
    """Sibilant band (5 to 9 kHz) against the speech band (200 Hz to 4 kHz) of the voice stem, in dB; higher is harsher. Takes at 24 kHz carry nothing above 12 kHz, so the band is inside what exists."""
    v = voice[: len(voice)]
    mask = voiced_mask(v)
    n = len(v)
    # use only voiced samples
    t = block_times(n)[:len(mask)]
    chunks = [v[int(a * SR): int((a + HOP_S) * SR)] for a, k in zip(t, mask) if k]
    if not chunks:
        return {"sib_minus_speech_db": -99.0}
    c = np.concatenate(chunks)
    return {"sib_minus_speech_db": round(band_db(c, 5000, 9000) - band_db(c, 200, 4000), 2),
            "air_9k_minus_speech_db": round(band_db(c, 9000, 12000) - band_db(c, 200, 4000), 2)}


def low_end(x: np.ndarray) -> dict:
    """Share of the signal's power under 200 Hz and in the mud band 200 to 400 Hz, in dB re total."""
    tot = band_db(x, 20, 20000)
    return {"under_200_db": round(band_db(x, 20, 200) - tot, 1), "mud_200_400_db": round(band_db(x, 200, 400) - tot, 1), "total_db": round(tot, 1)}


# ------------------------------------------------------------------ the three checks
def load_stems(stem_dir: Path) -> dict:
    out = {}
    for k in ("voice", "bed", "sfx"):
        x, sr = read_wav(Path(stem_dir) / f"{k}.wav")
        out[k] = stereo(to48(x, sr))
    n = max(len(v) for v in out.values())
    return {k: (np.pad(v, ((0, n - len(v)), (0, 0))) if len(v) < n else v) for k, v in out.items()}


def check_dialogue_clarity(stems: dict) -> tuple[list[str], dict]:
    others = stems["bed"] + stems["sfx"]
    m = clarity(stems["voice"], others)
    f = []
    T = THRESH
    if m["voiced_blocks"] == 0:
        f.append("AUDIO-DIALOGUE-CLARITY no voiced block found in the voice stem")
    else:
        if m["median_db"] < T["clarity_median_db"]:
            f.append(f"AUDIO-DIALOGUE-CLARITY median voice-over-music/sfx ratio on the phone simulation is {m['median_db']} dB (need >= {T['clarity_median_db']})")
        if m["p10_db"] < T["clarity_p10_db"]:
            f.append(f"AUDIO-DIALOGUE-CLARITY the weakest tenth of voiced blocks is {m['p10_db']} dB (need >= {T['clarity_p10_db']}); worst at {', '.join(str(w['t']) + ' s' for w in m['worst'][:3])}")
        if m["min_db"] < T["clarity_min_db"]:
            f.append(f"AUDIO-DIALOGUE-CLARITY a voiced block sits at {m['min_db']} dB (need >= {T['clarity_min_db']}) at {m['worst'][0]['t'] if m['worst'] else '?'} s")
        if m["share_below"] > T["clarity_share_max"]:
            f.append(f"AUDIO-DIALOGUE-CLARITY {m['share_below']:.1%} of voiced blocks are under {T['clarity_share_below_db']} dB (max {T['clarity_share_max']:.0%})")
    return f, m


def check_mono(stems: dict) -> tuple[list[str], dict]:
    mix = stems["voice"] + stems["bed"] + stems["sfx"]
    st_i = integrated_lufs(mix)
    mo_i = integrated_lufs(np.repeat(mono(mix), 2, axis=1))
    c_st = clarity(stems["voice"], stems["bed"] + stems["sfx"], sim=lambda x: mono(x))
    c_mo = clarity(np.repeat(mono(stems["voice"]), 2, axis=1), np.repeat(mono(stems["bed"] + stems["sfx"]), 2, axis=1), sim=lambda x: mono(x))
    corr = correlation_per_second(mix)
    m = {"stereo_lufs": round(st_i, 2), "mono_lufs": round(mo_i, 2), "mono_loss_lu": round(st_i - mo_i, 2), "stereo_median_db": c_st["median_db"], "mono_median_db": c_mo["median_db"],
         "corr_p05": round(float(np.percentile(corr, 5)), 3), "corr_min": round(float(corr.min()), 3)}
    f = []
    T = THRESH
    if m["mono_loss_lu"] > T["mono_loss_lu_max"]:
        f.append(f"AUDIO-MONO folding to mono loses {m['mono_loss_lu']} LU (max {T['mono_loss_lu_max']}): something cancels")
    if c_st["median_db"] - c_mo["median_db"] > T["mono_clarity_drop_db_max"]:
        f.append(f"AUDIO-MONO the mono fold-down drops the dialogue clarity ratio from {c_st['median_db']} to {c_mo['median_db']} dB (max drop {T['mono_clarity_drop_db_max']})")
    if m["corr_p05"] < T["corr_p05_min"]:
        f.append(f"AUDIO-MONO the L/R correlation falls to {m['corr_p05']} at the 5th percentile (need >= {T['corr_p05_min']}): out-of-phase material")
    return f, m


def check_peak(stems: dict, mix_path: Path | None = None) -> tuple[list[str], dict]:
    mix = (read_wav(mix_path)[0] if mix_path else stems["voice"] + stems["bed"] + stems["sfx"])
    tp, sp = true_peak_db(mix), sample_peak_db(mix)
    clipped = int((np.abs(mix) >= 0.999).sum())
    # the loudest moment of any sound effect against the dialogue it sits on: clarity of voice over sfx alone, same frames-where-somebody-speaks rule
    cs_ = clarity(stems["voice"], stems["sfx"])
    over = [-cs_["min_db"]] if cs_["voiced_blocks"] else [-99.0]
    m = {"true_peak_dbtp": round(tp, 2), "sample_peak_db": round(sp, 2), "clipped_samples": clipped, "worst_sfx_over_voice_db": round(float(over[0]), 1),
         "worst_sfx_over_voice_t": cs_["worst"][0]["t"] if cs_["worst"] else None}
    f = []
    T = THRESH
    if tp > T["tp_max_dbtp"]:
        f.append(f"AUDIO-PEAK true peak {m['true_peak_dbtp']} dBTP is over the {T['tp_max_dbtp']} ceiling")
    if sp > T["sample_peak_max_db"]:
        f.append(f"AUDIO-PEAK sample peak {m['sample_peak_db']} dBFS is over {T['sample_peak_max_db']}")
    if clipped:
        f.append(f"AUDIO-PEAK {clipped} clipped sample(s)")
    if over[0] > T["sfx_over_voice_db"]:
        f.append(f"AUDIO-PEAK at {m['worst_sfx_over_voice_t']} s a sound effect is {m['worst_sfx_over_voice_db']} dB louder than the dialogue under it (max {T['sfx_over_voice_db']})")
    return f, m


def run_checks(stem_dir: Path, mix_path: Path | None = None) -> tuple[list[str], dict]:
    stems = load_stems(stem_dir)
    fails, metrics = [], {}
    for name, fn in (("dialogue_clarity", lambda: check_dialogue_clarity(stems)), ("mono", lambda: check_mono(stems)), ("peak", lambda: check_peak(stems, mix_path))):
        f, m = fn()
        fails += f
        metrics[name] = m
    return fails, metrics


# ------------------------------------------------------------------ the full analysis (research/sound-e01c.md)
def analyse(stems: dict, mix: np.ndarray, timeline: dict | None = None, sfx_cues: list | None = None) -> dict:
    total = mix
    vox, bed, sfx = stems["voice"], stems["bed"], stems["sfx"]
    st = short_term_series(total)
    res = {"duration_s": round(len(total) / SR, 2),
           "mix": {"integrated_lufs": round(integrated_lufs(total), 2), "lra_lu": round(loudness_range(total), 2), "true_peak_dbtp": round(true_peak_db(total), 2),
                   "sample_peak_db": round(sample_peak_db(total), 2), "short_term_max_lufs": round(float(st.max()), 1), "short_term_min_lufs": round(float(st[st > -70].min()), 1)},
           "stems_lufs": {k: round(integrated_lufs(v), 2) for k, v in stems.items()},
           "phone": {"mix_lufs": round(integrated_lufs(np.repeat(phone_sim(total), 2, axis=1)), 2), "penalty_lu": round(integrated_lufs(total) - integrated_lufs(np.repeat(phone_sim(total), 2, axis=1)), 2),
                     "voice_lufs": round(integrated_lufs(np.repeat(phone_sim(vox), 2, axis=1)), 2),
                     "bed_lufs": round(integrated_lufs(np.repeat(phone_sim(bed), 2, axis=1)), 2), "sfx_lufs": round(integrated_lufs(np.repeat(phone_sim(sfx), 2, axis=1)), 2)},
           "earbuds": {"voice_lufs": round(integrated_lufs(earbud_sim(vox)), 2), "bed_lufs": round(integrated_lufs(earbud_sim(bed)), 2), "sfx_lufs": round(integrated_lufs(earbud_sim(sfx)), 2)},
           "clarity_phone": clarity(vox, bed + sfx), "clarity_earbuds": clarity(vox, bed + sfx, sim=earbud_sim),
           "clarity_bed_only_phone": clarity(vox, bed), "clarity_sfx_only_phone": clarity(vox, sfx),
           "sibilance_voice": sibilance_index(vox), "low_end_mix": low_end(total), "low_end_bed": low_end(bed), "low_end_sfx": low_end(sfx),
           "bed_energy_under_200_share_of_mix_power": round(float((band_db(bed, 20, 200) - band_db(total, 20, 20000))), 1)}
    ck_m = check_mono({"voice": vox, "bed": bed, "sfx": sfx})[1]
    res["mono"] = ck_m
    if timeline:
        rows = []
        pv, pb, ps = (phone_sim(vox), phone_sim(bed), phone_sim(sfx))
        for it in timeline["items"]:
            a, b = int(it["t0"] * SR), int(min(it["t1"], len(total) / SR) * SR)
            if b - a < SR // 2:
                continue
            seg = lambda x: np.repeat(x[a:b], 2, axis=1) if x.shape[1] == 1 else x[a:b]
            lv, lb, ls = integrated_lufs(seg(pv)), integrated_lufs(seg(pb)), integrated_lufs(seg(ps))
            rows.append({"item": it["id"], "t0": round(it["t0"], 2), "t1": round(it["t1"], 2), "voice_phone_lufs": round(lv, 1), "bed_phone_lufs": round(lb, 1), "sfx_phone_lufs": round(ls, 1),
                         "voice_minus_other_db": round(lv - 10 * np.log10(10 ** (lb / 10) + 10 ** (ls / 10) + 1e-12), 1)})
        res["per_scene"] = rows
    # the loudest sfx moments against the voice, with timestamps
    ps_ms, pv_ms = block_ms(phone_sim(sfx)), block_ms(phone_sim(vox))
    k = min(len(ps_ms), len(pv_ms))
    t = block_times(len(total))[:k]
    d = lufs(ps_ms[:k]) - lufs(pv_ms[:k])
    top = np.argsort(-lufs(ps_ms[:k]))[:6]
    res["loudest_sfx_moments"] = [{"t": round(float(t[i]), 2), "sfx_phone_lufs": round(float(lufs(ps_ms[i])), 1), "voice_phone_lufs": round(float(lufs(pv_ms[i])), 1)} for i in top]
    res["loudest_short_term"] = [{"t": round(float(i) * HOP_S, 1), "lufs": round(float(st[i]), 1)} for i in np.argsort(-st)[:3]]
    return res


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[0] not in ("check", "analyse"):
        print(__doc__)
        return 2
    work = ROOT / "work" / "episodes" / argv[1]
    sd = work / "audio" / "stems"
    if argv[0] == "check":
        fails, metrics = run_checks(sd, work / "mix.wav")
        print(json.dumps(metrics, ensure_ascii=False, indent=1))
        for x in fails:
            print("FAIL [" + x.split(" ", 1)[0] + "] " + x.split(" ", 1)[1])
        return 1 if fails else 0
    stems = load_stems(sd)
    tl = json.loads((work / "timeline.json").read_text(encoding="utf-8"))
    mix = stems["voice"] + stems["bed"] + stems["sfx"]
    print(json.dumps(analyse(stems, mix, tl), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
