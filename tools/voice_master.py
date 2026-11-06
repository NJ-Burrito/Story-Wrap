# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "scipy"]
# ///
"""ONE fixed mastering chain for every voice take (narrator and every cast character). the owner, 2026-10-26.

    uv run tools/voice_master.py measure <take.wav> [--role narrator|dialogue]
    uv run tools/voice_master.py master  <in.wav> <out.wav> --role narrator|dialogue
    uv run tools/voice_master.py proof   <out-dir> --role-map <json> <wav> [<wav> ...]   (before/after table; never writes over an input)

The numbers live in ONE file, tools/sound_profile.json (each with a `why`). This module only implements them.
The chain, in order (all CPU, numpy/scipy, deterministic, causal, no model, no network):
  1. high-pass             rumble and DC out (Butterworth, causal)
  2. de-noise              downward expander in the pauses, ONLY when the pauses sit above the profile's floor; never to zero
  3. corrective EQ         mud cut / presence lift toward the role's tonal target, clamped, never the other way; dead band
  4. de-ess                split-band, frame by frame, ONLY on takes whose sibilant band is hot
  5. level + compressor    pre-gain to the role level, gentle RMS compressor, gain back to the role level
  6. true-peak limiter     lookahead, never above the ceiling (a static trim guarantees it)
Contract: same length as the input, no new digital silence, never clips, a second pass is a no-op within the profile's tolerance.
The one-take rule is untouched: this is post-processing of the take that was made, not a new take.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from scipy import signal
from scipy.ndimage import maximum_filter1d, minimum_filter1d, uniform_filter1d

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import audio_checks as A  # noqa: E402
import voice_edges as VE  # noqa: E402

PROFILE_PATH = TOOLS / "sound_profile.json"
ROLES = ("narrator", "dialogue")
_PROFILE = {}


def load_profile(path: Path | str | None = None) -> dict:
    p = Path(path or PROFILE_PATH)
    key = str(p.resolve())
    if key not in _PROFILE:
        _PROFILE[key] = json.loads(p.read_text(encoding="utf-8"))
    return _PROFILE[key]


def role_of(speaker: str | None) -> str:
    """The narrator has his own variant; every cast character is dialogue."""
    return "narrator" if (speaker or "").lower() == "narrator" else "dialogue"


def role_params(role: str, profile: dict | None = None) -> dict:
    """The take chain of one role (`voice.take_chain.<role>`), with the shared `voice.lufs_target` filled in unless the role overrides it."""
    P = profile or load_profile()
    tc = P["voice"]["take_chain"]
    if role not in tc["roles"]:
        raise ValueError(f"unknown role {role!r} (roles: {', '.join(tc['roles'])})")
    r = dict(tc["roles"][role])
    r.setdefault("lufs_target", P["voice"]["lufs_target"])
    return r


# ------------------------------------------------------------------ measurement (the report and the gates use the same functions)
def _mono64(x) -> np.ndarray:
    a = np.asarray(x, dtype="float64")
    return a.mean(axis=1) if a.ndim == 2 else a


def frame_db(x: np.ndarray, rate: int, M: dict) -> tuple[np.ndarray, int, int]:
    """RMS level per frame (dBFS): the same 20 ms window / 10 ms hop as voice.py's trim and TAKE-QUALITY."""
    hop, win = max(1, int(rate * M["hop_s"])), max(2, int(rate * M["frame_s"]))
    if len(x) < win:
        r = np.sqrt(np.mean(x ** 2)) if len(x) else 0.0
        return np.array([20 * np.log10(max(r, 1e-6))]), hop, win
    c = np.concatenate([[0.0], np.cumsum(x ** 2)])
    idx = np.arange(0, len(x) - win + 1, hop)
    ms = (c[idx + win] - c[idx]) / win
    return 20 * np.log10(np.maximum(np.sqrt(np.maximum(ms, 0.0)), 1e-6)), hop, win


def speech_stats(x: np.ndarray, rate: int, M: dict) -> dict:
    """p95 frame level (the loud part), the speech span, the pause level INSIDE the speech (TAKE-QUALITY's pause_rel: median of the frames
    18 dB under p95) and the noise floor (median of the frames that are not speech at all, 30 dB under p95, when there are enough of them)."""
    db, hop, win = frame_db(x, rate, M)
    p95 = float(np.percentile(db, 95)) if len(db) else -120.0
    sp = np.nonzero(db >= p95 - M["speech_below_p95_db"])[0]
    pause_rel = None
    if len(sp):
        inside = db[sp[0]:sp[-1] + 1] - p95
        gaps = inside[inside < -M["pause_below_p95_db"]]
        if len(gaps) >= 3:
            pause_rel = float(np.median(gaps))
    noise_rel = None
    if len(sp):
        quiet = db[sp[0]:sp[-1] + 1] - p95
        quiet = quiet[quiet < -M["speech_below_p95_db"]]
        if len(quiet) >= M["noise_min_frames"]:
            noise_rel = float(np.median(quiet))
    return {"db": db, "hop": hop, "win": win, "p95": p95, "speech_frames": sp, "pause_rel_db": pause_rel, "noise_rel_db": noise_rel}


def pause_noise_rel(x: np.ndarray, rate: int, st: dict, M: dict) -> float | None:
    """The noise floor: median level (re the loud part) of the frames that are quiet (`speech_below_p95_db` under it), inside the
    speech window AND true pauses (voice_edges.pause_mask, the cleaner's own detector). Quiet frames next to a word, a quiet voiced
    ending or a fricative are the word's own decay, not the room, and the expander never lowers them, so they do not count.
    None when there are fewer than `noise_min_frames` of them, or no speech can be found. Without `voice.measure.pause` it is the
    old all-quiet-frames median (`speech_stats` noise_rel_db)."""
    if not M.get("pause"):
        return st["noise_rel_db"]
    sp = st["speech_frames"]
    if not len(sp):
        return None
    try:
        pm = VE.pause_mask(x, rate, M["pause"]["pad_s"], M["pause"]["pause_min_s"])
    except ValueError:
        return None
    n = min(len(st["db"]), len(pm["pause"]))
    idx = np.arange(sp[0], min(sp[-1] + 1, n))
    q = idx[(st["db"][idx] - st["p95"] < -M["speech_below_p95_db"]) & pm["pause"][idx]]
    return float(np.median(st["db"][q] - st["p95"])) if len(q) >= M["noise_min_frames"] else None


def ltas(x: np.ndarray, rate: int, st: dict, M: dict) -> tuple[np.ndarray, np.ndarray]:
    """Long-term average power spectrum over the speech frames only (Hann, n = M['ltas_n'])."""
    n = M["ltas_n"]
    f = np.fft.rfftfreq(n, 1 / rate)
    hop = st["hop"]
    sel = [i for i in st["speech_frames"] if st["db"][i] >= st["p95"] - M["speech_below_p95_db"]]
    starts = sorted({min(max(0, i * hop - n // 2), max(0, len(x) - n)) for i in sel[::2]})
    if not starts or len(x) < n:
        seg = np.pad(x, (0, max(0, n - len(x))))[:n]
        return f, np.abs(np.fft.rfft(seg * np.hanning(n))) ** 2
    w = np.hanning(n)
    P = np.zeros(len(f))
    for s in starts:
        P += np.abs(np.fft.rfft(x[s:s + n] * w)) ** 2
    return f, P / len(starts)


def _band(f, P, lo, hi):
    hi = min(hi, f[-1])
    return float(P[(f >= lo) & (f < hi)].sum()) + 1e-30


def sibilance(x: np.ndarray, rate: int) -> float:
    """audio_checks.sibilance_index (5 to 9 kHz minus 200 Hz to 4 kHz on the voiced 400 ms blocks, 48 kHz): the same number calm_mix's de-ess switch reads."""
    return float(A.sibilance_index(A.stereo(A.to48(np.asarray(x, dtype="float32")[:, None], rate)))["sib_minus_speech_db"])


def tone(x: np.ndarray, rate: int, st: dict, M: dict) -> dict:
    """mud and presence relative to the whole speech band (dB), sibilance, spectral tilt (dB per octave, 150 Hz to 6 kHz)."""
    f, P = ltas(x, rate, st, M)
    ref = _band(f, P, *M["ref_band_hz"])
    mud = 10 * np.log10(_band(f, P, *M["mud_band_hz"]) / ref)
    pres = 10 * np.log10(_band(f, P, *M["presence_band_hz"]) / ref)
    sib = sibilance(x, rate)
    lo, hi = M["tilt_range_hz"]
    centres = [c for c in lo * 2 ** np.arange(0, 8) if c * 1.41 <= min(hi, rate / 2)]
    lv = [10 * np.log10(_band(f, P, c / 1.41, c * 1.41)) for c in centres]
    tilt = float(np.polyfit(np.log2(centres), lv, 1)[0]) if len(centres) >= 3 else 0.0
    return {"mud_rel_db": round(float(mud), 2), "presence_rel_db": round(float(pres), 2), "sibilance_db": round(float(sib), 2), "tilt_db_per_oct": round(tilt, 2)}


def loudness(x: np.ndarray, rate: int) -> float:
    """Integrated loudness (BS.1770, gated) of the take as the mix plays it: dual-mono (centre-panned) at 48 kHz, calm_mix's convention."""
    return float(A.integrated_lufs(A.stereo(A.to48(np.asarray(x, dtype="float32")[:, None], rate))))


def true_peak(x: np.ndarray) -> float:
    return float(A.true_peak_db(np.asarray(x, dtype="float64")[:, None]))


def measure(x, rate: int, profile: dict | None = None) -> dict:
    P = profile or load_profile()
    M = P["voice"]["measure"]
    x = _mono64(x)
    st = speech_stats(x, rate, M)
    t = tone(x, rate, st, M)
    pr, nr = st["pause_rel_db"], pause_noise_rel(x, rate, st, M)
    noise_dbfs = None if nr is None else round(st["p95"] + nr, 2)
    return {"lufs": round(loudness(x, rate), 2), "true_peak_dbtp": round(true_peak(x), 2), "sample_peak_dbfs": round(float(20 * np.log10(max(np.abs(x).max(), 1e-9))), 2),
            "speech_p95_dbfs": round(st["p95"], 2), "pause_rel_db": None if pr is None else round(pr, 2),
            "noise_rel_db": None if nr is None else round(nr, 2), "noise_all_rel_db": None if st["noise_rel_db"] is None else round(st["noise_rel_db"], 2), "snr_db": None if nr is None else round(-nr, 2), "noise_floor_dbfs": noise_dbfs, **t,
            "seconds": round(len(x) / rate, 4), "zero_runs": zero_runs(x, rate, P["voice"]["contract"]["zero_run_ms"])}


def zero_runs(x: np.ndarray, rate: int, min_ms: float) -> int:
    """Runs of exact digital zeros of at least `min_ms` that sit INSIDE the signal (lead and tail pads are not counted)."""
    nz = np.nonzero(x != 0.0)[0]
    if len(nz) < 2:
        return 0
    inner = x[nz[0]:nz[-1] + 1] == 0.0
    if not inner.any():
        return 0
    d = np.diff(np.concatenate([[0], inner.astype(np.int8), [0]]))
    lens = np.nonzero(d == -1)[0] - np.nonzero(d == 1)[0]
    return int((lens >= min_ms / 1000 * rate).sum())


# ------------------------------------------------------------------ the stages
def _db2lin(db):
    return 10.0 ** (np.asarray(db, dtype="float64") / 20.0)


def _frames_to_samples(g_frames: np.ndarray, hop: int, win: int, n: int) -> np.ndarray:
    centres = np.arange(len(g_frames)) * hop + win / 2
    return np.interp(np.arange(n), centres, g_frames)


def stage_hpf(x, rate, c):
    sos = signal.butter(c["order"], c["hz"], btype="highpass", fs=rate, output="sos")
    return signal.sosfilt(sos, x), {"hz": c["hz"], "order": c["order"]}


def stage_denoise(x, rate, c, M, ref=None):
    """Downward expander toward a noise floor, in up to c['iterations'] passes that share one budget of c['max_range_db'] (the hold and
    lookahead keep the edges of the gaps open, so one pass reaches only part of its range). Bypassed when the floor is already low enough."""
    y, total, first, info = x, 0.0, None, {"applied": False}
    pm = None
    if M.get("pause"):                               # act only on true pauses: the cleaner's own speech detector says which frames are speech
        try:
            pm = VE.pause_mask(ref if ref is not None else x, rate, M["pause"]["pad_s"], M["pause"]["pause_min_s"])
        except ValueError as e:
            return x, {"applied": False, "noise_rel_db": None, "protect": f"no speech found ({e}): expander bypassed, nothing is safe to lower"}
        info["protect"] = {"pause_s": pm["pause_s"], "protected_s": pm["protected_s"]}
    for _ in range(c["iterations"]):
        budget = c["max_range_db"] - total
        if budget < 0.5:
            break
        y2, i = _expand_once(y, rate, c, M, budget, ref, pm)
        if first is None:
            first = i.get("noise_rel_db")
        if not i["applied"]:
            break
        y, total = y2, total + i["range_db"]
        info = {**info, "applied": True, "noise_rel_db": round(first, 2) if first is not None else None, "range_db": round(total, 2)}
    if not info["applied"]:
        info["noise_rel_db"] = first
    return y, info


def _expand_once(x, rate, c, M, budget, ref=None, pm=None):
    """`ref` (the take before the compressor) decides WHICH frames are not speech: the compressor lifts the noise by its own gain
    reduction, so after it the gaps can no longer be told from soft speech. The level of those frames is read on `x`.
    `pm` (voice_edges.pause_mask): when given, only its pause frames are measured and lowered; every frame of a word, a quiet voiced
    ending, a fricative or a pause inside a phrase keeps gain 0 dB."""
    st = speech_stats(x, rate, M)
    cls = speech_stats(ref, rate, M) if ref is not None else st
    pr = None
    sp = cls["speech_frames"]
    n = min(len(cls["db"]), len(st["db"]))
    if len(sp):
        idx = np.arange(sp[0], min(sp[-1] + 1, n))
        quiet = idx[cls["db"][idx] - cls["p95"] < -M["speech_below_p95_db"]]
        if pm is not None:
            quiet = quiet[pm["pause"][np.minimum(quiet, len(pm["pause"]) - 1)]]
        if len(quiet) >= M["noise_min_frames"]:
            pr = float(np.median(st["db"][quiet] - st["p95"]))
    if pr is None or pr <= c["skip_if_noise_rel_at_or_below_db"]:
        return x, {"applied": False, "noise_rel_db": pr}
    rng = float(min(budget, pr - c["target_noise_rel_db"]))
    rel = cls["db"][: len(st["db"])] - cls["p95"]
    thr, knee = -c["open_below_p95_db"], c["knee_db"]
    depth = np.clip((thr - rel) / knee, 0.0, 1.0)              # 0 above the threshold, 1 a knee under it
    if pm is not None:
        pz = np.zeros(len(rel), dtype=bool)
        k = min(len(rel), len(pm["pause"]))
        pz[:k] = pm["pause"][:k]
        depth = depth * pz                                      # words, endings, fricatives and in-phrase gaps: depth 0
    g_db = -rng * depth
    hop_s = M["hop_s"]
    look, hold = max(1, int(round(c["lookahead_ms"] / 1000 / hop_s))), max(1, int(round(c["hold_ms"] / 1000 / hop_s)))
    # open early (lookahead) and stay open (hold): the frame's gain is the most open gain from `hold` frames back to `look` frames ahead
    size = look + hold + 1
    g_db = maximum_filter1d(g_db, size=size, origin=(hold - look) // 2 if size % 2 else (hold - look) // 2, mode="nearest")
    g_db = uniform_filter1d(g_db, size=max(1, int(round(c["smooth_ms"] / 1000 / hop_s))), mode="nearest")
    g = _db2lin(_frames_to_samples(g_db, st["hop"], st["win"], len(x)))
    g = np.maximum(g, _db2lin(-rng))
    return x * g, {"applied": True, "noise_rel_db": round(pr, 2), "range_db": round(rng, 2)}


def _peaking(rate, hz, q, gain_db):
    A_ = 10 ** (gain_db / 40)
    w = 2 * np.pi * hz / rate
    al = np.sin(w) / (2 * q)
    b = [1 + al * A_, -2 * np.cos(w), 1 - al * A_]
    a = [1 + al / A_, -2 * np.cos(w), 1 - al / A_]
    return signal.tf2sos(np.array(b) / a[0], np.array(a) / a[0])


def stage_eq(x, rate, c, M):
    """Corrective EQ toward the role's tonal target: a mud CUT (never a boost) and a presence LIFT (never a cut), each clamped.
    The gain is solved on the take (two refinements of the measured error) and skipped inside the dead band, so a second pass does nothing."""
    st = speech_stats(x, rate, M)
    base = tone(x, rate, st, M)
    gains = {"mud": 0.0, "presence": 0.0}
    key = {"mud": "mud_rel_db", "presence": "presence_rel_db"}
    err = {b: c[b]["target_rel_db"] - base[key[b]] for b in gains}
    if all(abs(err[b]) < c["dead_band_db"] or (b == "mud" and err[b] > 0) or (b == "presence" and err[b] < 0) for b in gains):
        return x, {"applied": False, "mud_db": 0.0, "presence_db": 0.0, "before": base}

    def clampg(b, g):
        return float(np.clip(g, -c["mud"]["max_cut_db"], 0.0)) if b == "mud" else float(np.clip(g, 0.0, c["presence"]["max_boost_db"]))

    y = x
    for _ in range(c["iterations"]):
        gains = {b: clampg(b, gains[b] + (c[b]["target_rel_db"] - tone(y, rate, st, M)[key[b]])) for b in gains}
        y = x
        for b in gains:
            if abs(gains[b]) >= 0.05:
                y = signal.sosfilt(_peaking(rate, c[b]["hz"], c[b]["q"], gains[b]), y)
    return y, {"applied": True, "mud_db": round(gains["mud"], 2), "presence_db": round(gains["presence"], 2), "before": base}


def stage_deess(x, rate, c, M):
    """Split-band de-esser: y = x - (1 - g) * hi, hi = the band above c['split_hz']. g = 1 (exact bypass) on every frame under the threshold."""
    st = speech_stats(x, rate, M)
    sib = tone(x, rate, st, M)["sibilance_db"]
    if sib <= c["when_db"] or rate / 2 <= c["split_hz"] * 1.1:
        return x, {"applied": False, "sibilance_db": sib}
    hi = signal.sosfilt(signal.butter(2, c["split_hz"], btype="highpass", fs=rate, output="sos"), x)
    hop, win = st["hop"], st["win"]
    db_all, _, _ = frame_db(x, rate, M)
    db_hi, _, _ = frame_db(hi, rate, M)
    over = (db_hi - db_all) - c["frame_thresh_db"]                         # how far the sibilant band rises above its allowed share of the frame
    loud = db_all >= st["p95"] - M["speech_below_p95_db"]
    red_db = np.where(loud, np.clip(over * (1 - 1 / c["ratio"]), 0.0, c["max_reduction_db"]), 0.0)
    red_db = maximum_filter1d(red_db, size=3, mode="nearest")
    red_db = uniform_filter1d(red_db, size=3, mode="nearest")
    g = _db2lin(-_frames_to_samples(red_db, hop, win, len(x)))
    return x - (1.0 - g) * hi, {"applied": True, "sibilance_db": sib, "max_reduction_db": round(float(red_db.max()), 2)}


def stage_compress(x, rate, c):
    """Feed-forward RMS compressor with a soft knee; threshold relative to the role's target level (the take is pre-gained to it first)."""
    det = max(1, int(rate * c["detector_ms"] / 1000))
    ms = uniform_filter1d(x ** 2, size=det, mode="nearest")
    lvl = 10 * np.log10(np.maximum(ms, 1e-12))
    T, R, K = c["threshold_dbfs"], c["ratio"], c["knee_db"]
    over = lvl - T
    gr = np.where(over <= -K / 2, 0.0, np.where(over >= K / 2, over * (1 - 1 / R), (1 - 1 / R) * (over + K / 2) ** 2 / (2 * K)))
    step = max(1, rate // 1000)                                            # gain smoothing at 1 ms resolution
    n = len(gr) // step
    frames = gr[: n * step].reshape(n, step).max(axis=1) if n else np.array([gr.max() if len(gr) else 0.0])
    ca, cr = 1 - np.exp(-1.0 / max(c["attack_ms"], 0.01)), 1 - np.exp(-1.0 / max(c["release_ms"], 0.01))
    s, out = 0.0, np.empty(len(frames))
    for i, v in enumerate(frames):
        s += (ca if v > s else cr) * (v - s)
        out[i] = s
    g = _db2lin(-np.interp(np.arange(len(x)), np.arange(len(out)) * step + step / 2, out))
    return x * g, {"max_gr_db": round(float(out.max()) if len(out) else 0.0, 2), "mean_gr_db": round(float(out.mean()) if len(out) else 0.0, 2)}


def _tq_pause_rel(x, rate, M):
    """TAKE-QUALITY's `pause_rel_db`, computed the way `voice.take_profile` does (same frames, p95 by sorted index, upper median),
    so this stage and the gate agree to the last 0.1 dB. -> (pause_rel_db or None, p95, frame levels)."""
    db, hop, win = frame_db(x, rate, M)
    p95 = float(np.sort(db)[min(len(db) - 1, int(len(db) * 0.95))])
    sp = np.nonzero(db >= p95 - M["speech_below_p95_db"])[0]
    if not len(sp):
        return None, p95, db
    gaps = np.sort(db[sp[0]:sp[-1] + 1][db[sp[0]:sp[-1] + 1] < p95 - M["pause_below_p95_db"]] - p95)
    return (float(gaps[len(gaps) // 2]) if len(gaps) >= 3 else None), p95, db


def stage_pause_floor(ref, y, rate, c, M):
    """R-472: the chain never brings the pauses closer to the voice than the take came in.
    Compressor and limiter lower the loud part and let their gain recover under every soft frame, so the take's p95 falls and the soft
    frames do not: TAKE-QUALITY's pause distance (median of the frames more than `pause_below_p95_db` under the p95, inside the speech)
    shrinks by the compressor's gain reduction and the limiter's. E01C L05, L13, L19, L22, L23 were generated at -24.1 to -24.6 dB (limit
    -24.0) and left the chain at -21.2 to -23.3 dB. Here the frames that are soft on `ref` (the take before the compressor) take the
    gain the loud part lost, i.e. their gain is held down with it instead of recovering: the smallest cut (steps of c['pause_floor_step_db'],
    at most c['pause_floor_max_db']) that puts the measured distance of `y` back at, or under, the distance of `ref`.
    Only frames that are soft by that measure move; every other frame, every word, every ending above that line keeps its gain exactly,
    the ramps lie inside the soft region, and nothing is ever raised. Bypassed when `ref` has no pause distance (under 3 such frames)."""
    want, p95, db = _tq_pause_rel(ref, rate, M)
    got = _tq_pause_rel(y, rate, M)[0]
    if want is None or got is None:
        return y, {"applied": False, "reason": "no pause frames to protect"}
    if got <= want:
        return y, {"applied": False, "before_rel_db": round(got, 2), "target_rel_db": round(want, 2)}
    hop, win = max(1, int(rate * M["hop_s"])), max(2, int(rate * M["frame_s"]))
    quiet = db < p95 - M["pause_below_p95_db"]
    core = quiet.copy()
    core[1:-1] = quiet[1:-1] & quiet[:-2] & quiet[2:]                             # ramps stay inside the soft region
    shape = uniform_filter1d(core.astype(float), size=3, mode="nearest")
    step, top = float(c.get("pause_floor_step_db", 0.25)), float(c.get("pause_floor_max_db", 6.0))
    d, z = 0.0, y
    while d < top:
        d += step
        g = _db2lin(-d * _frames_to_samples(shape, hop, win, len(y)))
        z = y * g
        now = _tq_pause_rel(z, rate, M)[0]
        if now is not None and now <= want:
            break
    return z, {"applied": True, "cut_db": round(d, 2), "before_rel_db": round(got, 2), "target_rel_db": round(want, 2),
               "after_rel_db": round(_tq_pause_rel(z, rate, M)[0], 2), "frames": int(core.sum())}


def _tp_env(x: np.ndarray) -> np.ndarray:
    """Per-sample true-peak magnitude: max |x| over the 4x oversampled points around each sample."""
    up = np.abs(signal.resample_poly(x, 4, 1))[: 4 * len(x)]
    up = np.pad(up, (0, 4 * len(x) - len(up)))
    return np.maximum(up.reshape(-1, 4).max(axis=1), np.abs(x))


def stage_limit(x, rate, c):
    """Lookahead true-peak limiter: gain = min over the lookahead window, held, ramped; then a static trim if the true peak is still over."""
    ceil = 10 ** (c["ceiling_dbtp"] / 20)
    req = np.minimum(1.0, ceil / np.maximum(_tp_env(x), 1e-12))
    engaged = bool((req < 1.0).any())
    g = np.ones(len(x))
    if engaged:
        L = max(1, int(rate * c["lookahead_ms"] / 1000))
        H = max(1, int(rate * c["hold_ms"] / 1000))
        m = minimum_filter1d(req, size=L, origin=-(L // 2), mode="nearest")       # m[n] = min(req[n .. n+L-1]): starts L samples early
        m = minimum_filter1d(m, size=H, origin=(H - 1) // 2, mode="nearest")      # held for H samples after
        s = uniform_filter1d(m, size=L, origin=(L - 1) // 2, mode="nearest")      # ramp of L samples (average of past L): never above req at a peak
        step = max(1, rate // 1000)
        n = len(s) // step + 1
        fr = np.array([s[i * step:(i + 1) * step].min() for i in range(n) if i * step < len(s)])
        rc = 1 - np.exp(-1.0 / max(c["release_ms"], 0.01))
        r, out = 1.0, np.empty(len(fr))
        for i, v in enumerate(fr):                                              # release: gain recovers with a one-pole, falls at once
            r = v if v < r else r + rc * (v - r)
            out[i] = r
        g = np.minimum(s, np.interp(np.arange(len(x)), np.arange(len(out)) * step, out))
    y = x * g
    tp = true_peak(y)
    trim = 0.0
    if tp > c["ceiling_dbtp"]:                                                   # the guarantee: never above the ceiling
        trim = c["ceiling_dbtp"] - tp - 0.01
        y = y * 10 ** (trim / 20)
    return y, {"engaged": engaged, "max_gr_db": round(float(-20 * np.log10(max(g.min(), 1e-9))), 2), "trim_db": round(trim, 2)}


# ------------------------------------------------------------------ the chain
def master_take(x, rate: int, role: str, profile: dict | None = None) -> tuple[np.ndarray, dict]:
    """The one chain. x: mono floats in [-1, 1] (list or array), rate in Hz, role 'narrator' or 'dialogue'.
    -> (y float64 array of the SAME length, report dict with before/after metrics and what each stage did)."""
    P = profile or load_profile()
    R = role_params(role, P)
    M = P["voice"]["measure"]
    x0 = _mono64(x).copy()
    n = len(x0)
    if n == 0 or not np.any(x0):
        raise ValueError("silent take: nothing to master")
    before = measure(x0, rate, P)
    why_not = in_spec(x0, rate, role, P, before)
    if not why_not:                                                              # already mastered: a second pass changes nothing
        return x0, {"role": role, "profile_version": P["version"], "rate": rate, "samples": n, "before": before, "after": before,
                    "stages": {"bypass": "in spec: level, peak, noise floor, sibilance and tone already where the chain puts them"}}
    st = {"why_processed": why_not}
    y, st["hpf"] = stage_hpf(x0, rate, {"hz": R["highpass_hz"], "order": R["highpass_order"]})
    target = R["lufs_target"]
    pre = target - loudness(y, rate)
    y = y * 10 ** (pre / 20)
    pre_comp = y.copy()
    y, st["comp"] = stage_compress(y, rate, R["comp"])
    y, st["eq"] = stage_eq(y, rate, R["eq"], M)                                 # after the compressor: compression changes which frames dominate the tone
    y, st["deess"] = stage_deess(y, rate, {**R["deess"], "when_db": R["deess_when_db"]}, M)   # after the compressor: it lowers the vowels, so the s rises
    y, st["denoise"] = stage_denoise(y, rate, R["denoise"], M, ref=pre_comp)                  # after the compressor: it lifts the pauses by its own gain reduction
    for k in range(P["voice"]["take_chain"]["level_passes"]):                   # level, limit, and again for what the limiter took
        post = target - loudness(y, rate)
        if abs(post) < P["voice"]["take_chain"]["settle_lu"] and k:
            break
        y = y * 10 ** (post / 20)
        y, st["limit"] = stage_limit(y, rate, R["limit"])
    st["gain_db"] = {"pre": round(pre, 2), "post": round(post, 2)}
    if R["comp"].get("pause_floor", False):                                      # after the limiter: it lifts the pauses too (R-472)
        y, st["pause_floor"] = stage_pause_floor(pre_comp, y, rate, R["comp"], M)
    y[x0 == 0.0] = np.where(np.abs(y[x0 == 0.0]) < P["voice"]["contract"]["pad_zero_below"], 0.0, y[x0 == 0.0])   # zero pads stay zero only where the filters left nothing audible
    if np.abs(y).max() >= 1.0:                                                   # cannot happen after the limiter; the contract is checked anyway
        y = y * (0.999 / np.abs(y).max())
    after = measure(y, rate, P)
    rep = {"role": role, "profile_version": P["version"], "rate": rate, "samples": n, "before": before, "after": after, "stages": st}
    return y, rep


def in_spec(x, rate, role, profile=None, m=None) -> list[str]:
    """Why the take still needs the chain ([] = it is already where the chain would put it, so it passes through untouched).
    In spec = loudness within in_spec_lu of the role target, true peak at or under the ceiling, noise floor and sibilance inside the
    VOICE-MASTER gate, and mud / presence within in_spec_tone_db of the role's tonal target. This is what makes the chain idempotent."""
    P = profile or load_profile()
    R = role_params(role, P)
    M = P["voice"]["measure"]
    m = m or measure(x, rate, P)
    out = []
    if abs(m["lufs"] - R["lufs_target"]) > P["voice"]["take_chain"]["in_spec_lu"]:
        out.append(f"loudness {m['lufs']} (target {R['lufs_target']})")
    if m["true_peak_dbtp"] > R["limit"]["ceiling_dbtp"] + P["checks"]["voice_master"]["true_peak_margin_db"]:
        out.append(f"true peak {m['true_peak_dbtp']} (ceiling {R['limit']['ceiling_dbtp']})")
    G = P["checks"]["voice_master"]
    if m["noise_rel_db"] is not None and m["noise_rel_db"] > G["max_noise_rel_db"]:
        out.append(f"noise floor {m['noise_rel_db']}")
    if m["sibilance_db"] > G["max_sibilance_db"]:
        out.append(f"sibilance {m['sibilance_db']}")
    e = R["eq"]
    tol = P["voice"]["take_chain"]["in_spec_tone_db"]
    if m["mud_rel_db"] - e["mud"]["target_rel_db"] > tol:
        out.append(f"mud {m['mud_rel_db']} (target {e['mud']['target_rel_db']})")
    if e["presence"]["target_rel_db"] - m["presence_rel_db"] > tol:
        out.append(f"presence {m['presence_rel_db']} (target {e['presence']['target_rel_db']})")
    return out


def contract_problems(x, y, rep, profile: dict | None = None) -> list[str]:
    """The chain's promises, checked on its own output."""
    P = profile or load_profile()
    out = []
    if len(y) != len(x):
        out.append(f"length changed: {len(x)} -> {len(y)} samples")
    if np.abs(y).max() >= 1.0:
        out.append("clipped: a sample reached full scale")
    if rep["after"]["zero_runs"] > rep["before"]["zero_runs"]:
        out.append(f"new digital silence: {rep['after']['zero_runs'] - rep['before']['zero_runs']} run(s) of >= {P['voice']['contract']['zero_run_ms']} ms")
    return out


def gate_problems(rep_or_metrics: dict, role: str, profile: dict | None = None) -> list[tuple[str, str]]:
    """VOICE-MASTER checks on a finished take (metrics from `measure`, or a report's 'after')."""
    P = profile or load_profile()
    G = P["checks"]["voice_master"]
    m = rep_or_metrics.get("after", rep_or_metrics)
    tgt = role_params(role, P)["lufs_target"]
    ceil = role_params(role, P)["limit"]["ceiling_dbtp"]
    f = []
    if abs(m["lufs"] - tgt) > G["lufs_tolerance_lu"]:
        f.append(("VOICE-MASTER", f"loudness {m['lufs']} LUFS, target {tgt} +-{G['lufs_tolerance_lu']} LU ({role})"))
    if m["true_peak_dbtp"] > ceil + G["true_peak_margin_db"]:
        f.append(("VOICE-MASTER", f"true peak {m['true_peak_dbtp']} dBTP over the ceiling {ceil} ({role})"))
    if m.get("noise_rel_db") is not None and m["noise_rel_db"] > G["max_noise_rel_db"]:
        f.append(("VOICE-MASTER", f"noise floor {m['noise_rel_db']} dB under the voice (limit {G['max_noise_rel_db']})"))
    if m["sibilance_db"] > G["max_sibilance_db"]:
        f.append(("VOICE-MASTER", f"sibilance {m['sibilance_db']} dB (limit {G['max_sibilance_db']})"))
    if m.get("zero_runs", 0) > 0:
        f.append(("VOICE-MASTER", f"{m['zero_runs']} digital-silence run(s) inside the take"))
    return f


def octave_levels(x, rate, profile=None) -> np.ndarray:
    P = profile or load_profile()
    M = P["voice"]["measure"]
    x = _mono64(x)
    st = speech_stats(x, rate, M)
    f, Pw = ltas(x, rate, st, M)
    centres = [c for c in 125 * 2 ** np.arange(0, 7) if c * 1.41 <= rate / 2]
    tot = _band(f, Pw, 100, rate / 2)
    return np.array([10 * np.log10(_band(f, Pw, c / 1.41, c * 1.41) / tot) for c in centres])


def idempotence(y, rate, role, profile=None) -> dict:
    """Run the chain on its own output and compare what a listener hears: loudness, true peak, pause floor, sibilance and the
    octave-band balance (125 Hz to 8 kHz). A sample-by-sample difference is NOT used: a second high-pass only turns the phase."""
    P = profile or load_profile()
    y2, r2 = master_take(y, rate, role, P)
    a, b = measure(y, rate, P), r2["after"]
    pa = a["noise_rel_db"] if a["noise_rel_db"] is not None else 0.0
    pb = b["noise_rel_db"] if b["noise_rel_db"] is not None else 0.0
    return {"d_lufs": round(abs(b["lufs"] - a["lufs"]), 3), "d_true_peak_db": round(abs(b["true_peak_dbtp"] - a["true_peak_dbtp"]), 3),
            "d_noise_db": round(abs(pb - pa), 3), "d_sibilance_db": round(abs(b["sibilance_db"] - a["sibilance_db"]), 3),
            "d_octave_max_db": round(float(np.abs(octave_levels(y2, rate, P) - octave_levels(y, rate, P)).max()), 3),
            "bypassed_in_spec": bool(r2["stages"].get("bypass")), "stages_applied": [k for k in ("denoise", "eq", "deess") if r2["stages"].get(k, {}).get("applied")]}


def idempotence_problems(d: dict, profile=None) -> list[str]:
    T = (profile or load_profile())["voice"]["take_chain"]["idempotence_tolerance"]
    return [f"second pass moved {k} by {d[k]} (tolerance {T[k]})" for k in T if k in d and d[k] > T[k]]


# ------------------------------------------------------------------ files
def read(path) -> tuple[np.ndarray, int]:
    x, sr = A.read_wav(path)
    return x[:, 0].astype("float64"), sr


def write16(path, y: np.ndarray, rate: int):
    """16-bit mono wav, atomically (same format as voice.py's trimmed takes)."""
    from scipy.io import wavfile
    p = Path(path)
    tmp = p.with_name(p.name + ".tmp")
    pcm = np.clip(np.round(np.asarray(y) * 32767), -32768, 32767).astype("<i2")
    with open(tmp, "wb") as fh:
        wavfile.write(fh, rate, pcm)
    tmp.replace(p)


def master_file(src, dst, role: str, profile=None) -> dict:
    x, sr = read(src)
    y, rep = master_take(x, sr, role, profile)
    write16(dst, y, sr)
    rep["contract"] = contract_problems(x, y, rep, profile)
    return rep


def _row(name, role, rep):
    b, a = rep["before"], rep["after"]
    return {"file": name, "role": role, "lufs": (b["lufs"], a["lufs"]), "tp": (b["true_peak_dbtp"], a["true_peak_dbtp"]), "snr": (b["snr_db"], a["snr_db"]),
            "sib": (b["sibilance_db"], a["sibilance_db"]), "tilt": (b["tilt_db_per_oct"], a["tilt_db_per_oct"]), "mud": (b["mud_rel_db"], a["mud_rel_db"]),
            "presence": (b["presence_rel_db"], a["presence_rel_db"])}


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("measure", "master", "proof"):
        print(__doc__)
        return 2
    role = argv[argv.index("--role") + 1] if "--role" in argv else "dialogue"
    if argv[0] == "measure":
        x, sr = read(argv[1])
        m = measure(x, sr)
        m["gate"] = gate_problems(m, role)
        print(json.dumps(m, ensure_ascii=False))
        return 0
    if argv[0] == "master":
        src, dst = Path(argv[1]), Path(argv[2])
        if src.resolve() == dst.resolve():
            print("refused: the output would overwrite the input", file=sys.stderr)
            return 2
        rep = master_file(src, dst, role)
        print(json.dumps({"before": rep["before"], "after": rep["after"], "contract": rep["contract"], "gate": gate_problems(rep, role)}, ensure_ascii=False))
        return 1 if rep["contract"] or gate_problems(rep, role) else 0
    out = Path(argv[1])
    rm = json.loads(Path(argv[argv.index("--role-map") + 1]).read_text(encoding="utf-8")) if "--role-map" in argv else {}
    skip = {argv.index("--role-map") + 1} if "--role-map" in argv else set()
    files = [Path(a) for i, a in enumerate(argv[2:], 2) if not a.startswith("--") and i not in skip and argv[i - 1] not in ("--role", "--role-map")]
    out.mkdir(parents=True, exist_ok=True)
    rows, bad = [], 0
    for f in files:
        r = rm.get(f.stem.split(".")[0], role)
        dst = out / (f.parent.name + "__" + f.name)
        if dst.resolve() == f.resolve():
            raise SystemExit("refused: output equals input")
        rep = master_file(f, dst, r)
        x, sr = read(dst)
        rep["idempotence"] = idempotence(x, sr, r)
        rep["idempotence_problems"] = idempotence_problems(rep["idempotence"])
        rep["gate"] = gate_problems(rep, r)
        bad += bool(rep["gate"] or rep["contract"] or rep["idempotence_problems"])
        (out / (dst.stem + ".report.json")).write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
        rows.append({**_row(f.parent.name + "/" + f.name, r, rep), "gate": [m for _, m in rep["gate"]], "contract": rep["contract"], "idem": rep["idempotence"], "idem_problems": rep["idempotence_problems"]})
    (out / "proof.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    for r in rows:
        print(json.dumps(r, ensure_ascii=False))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
