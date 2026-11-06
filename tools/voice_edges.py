# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy"]
# ///
"""Word-safe edge cleaner for voice takes (owner, 2026-10-26: "a small window sometimes appears before or after with noise
only, no words being said ... develop methods to prevent it without cutting the sounds and words short").

    uv run tools/voice_edges.py measure <take.wav> [...]      speech span, noise-only lead-in / tail, VOICE-EDGE-NOISE
    uv run tools/voice_edges.py clean   <in.wav> <out.wav>    cut the noise-only edges (guards kept, equal-power fades)

Deterministic, numpy only, no model (R-446, R-459). Every number is `take.edge.*` / `checks.edge_noise.*` in
tools/sound_profile.json, each with its reason.

How the speech span is found (four features per 20 ms frame, 10 ms hop):
  1. energy        frame level in dBFS and its distance under the loud part (p95 of the frame levels)
  2. F0 voicing    normalised autocorrelation peak in the F0 range (Boersma's window-corrected method, Praat's 0.45 voicing
                   threshold) AND a share of the energy in the formant band, so a mains hum or a low drone is not "voiced"
  3. flatness and  a fricative frame (س ش ف ث, the release of ت) has its energy above the split frequency and a high
     zero-crossing zero-crossing rate; it may sit lower than the vowels and still be a sound of the word
  The CORE is the voiced frames grouped into runs (short gaps bridged), with stray runs (far under the loud part after a
  long gap: a hum, a drone) dropped. The core is then EXTENDED outward through every attached frame that is loud, or that
  is energetic, or that is fricative and clearly above the noise floor, across gaps of at most `attach_bridge_s`; loud
  attached frames have no length limit (a creaky or pharyngeal onset is speech), quieter ones at most `attach_max_*_s`.
  That is the speech span: onset = first phoneme, offset = end of the last phoneme.
The cleaner keeps a guard before the onset and after the offset (the decay of a final ه, a soft release), fades inside
the guard only (equal-power), so no frame of the span is ever scaled, and removes everything outside: a noise-only
lead-in, a breath far from the words, a drone or hiss after the line, a model run-on of noise.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

TOOLS = Path(__file__).resolve().parent
PROFILE_PATH = TOOLS / "sound_profile.json"
_P = {}


def params(profile: dict | None = None) -> dict:
    if profile is not None:
        return profile["take"]["edge"]
    if "edge" not in _P:
        _P["edge"] = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))["take"]["edge"]
    return _P["edge"]


def check_limits(profile: dict | None = None) -> dict:
    if profile is not None:
        return profile["checks"]["edge_noise"]
    if "chk" not in _P:
        _P["chk"] = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))["checks"]["edge_noise"]
    return _P["chk"]


# ------------------------------------------------------------------ frame features
def _frames(x: np.ndarray, n: int, hop: int) -> np.ndarray:
    if len(x) < n:
        x = np.pad(x, (0, n - len(x)))
    k = 1 + (len(x) - n) // hop
    idx = np.arange(n)[None, :] + hop * np.arange(k)[:, None]
    return x[idx]


def features(x, rate: int, E: dict | None = None) -> dict:
    """Per-frame features of a mono float signal. -> dict of numpy arrays plus hop/win/p95/floor."""
    E = E or params()
    x = np.asarray(x, dtype="float64")
    hop, win = max(1, int(round(rate * E["hop_s"]))), max(2, int(round(rate * E["frame_s"])))
    fr = _frames(x, win, hop)
    nf = len(fr)
    rms = np.sqrt(np.mean(fr ** 2, axis=1))
    db = np.where(rms > 1e-6, 20 * np.log10(np.maximum(rms, 1e-12)), -120.0)
    # spectrum of the 20 ms frame: flatness (100 Hz-8 kHz), high-band ratio, formant-band share
    w = np.hanning(win)
    nfft = 1 << max(6, (win - 1).bit_length())
    S = np.abs(np.fft.rfft(fr * w, nfft, axis=1)) ** 2 + 1e-20
    f = np.fft.rfftfreq(nfft, 1.0 / rate)
    fb = (f >= 100) & (f <= min(8000, rate / 2))
    flat = np.exp(np.mean(np.log(S[:, fb]), axis=1)) / np.mean(S[:, fb], axis=1)
    split = E["fricative"]["hi_split_hz"]
    lo_e = S[:, (f >= 100) & (f < split)].sum(axis=1)
    hi_e = S[:, f >= split].sum(axis=1)
    hi_db = 10 * np.log10(hi_e / lo_e)
    b0, b1 = E["voiced_band_hz"]
    tot = S[:, (f >= 40)].sum(axis=1)
    band_db = 10 * np.log10(S[:, (f >= b0) & (f <= b1)].sum(axis=1) / tot)
    zcr = np.mean(np.abs(np.diff(np.signbit(fr).astype(np.int8), axis=1)), axis=1)
    # periodicity on a longer window centred on the frame (two periods of the lowest F0 fit in it)
    pw = max(win, int(round(rate * E["periodicity_win_s"])))
    off = (pw - win) // 2
    xp = np.pad(x, (off, pw))
    fp = _frames(xp, pw, hop)[:nf]
    fp = fp - fp.mean(axis=1, keepdims=True)
    wp = np.hanning(pw)
    n2 = 1 << (2 * pw - 1).bit_length()
    ac = np.fft.irfft(np.abs(np.fft.rfft(fp * wp, n2, axis=1)) ** 2, n2, axis=1)[:, :pw]
    aw = np.fft.irfft(np.abs(np.fft.rfft(wp, n2)) ** 2, n2)[:pw]
    lo_lag = max(1, int(rate / E["f0_range_hz"][1]))
    hi_lag = min(pw // 2, int(rate / E["f0_range_hz"][0]))
    r0 = np.maximum(ac[:, :1], 1e-20)
    rn = (ac[:, lo_lag:hi_lag + 1] / r0) / np.maximum(aw[lo_lag:hi_lag + 1] / aw[0], 1e-6)
    period = np.clip(rn.max(axis=1), -1.0, 1.0)
    f0 = rate / (lo_lag + np.argmax(rn, axis=1))
    live = db[db > -100]
    top = db[db >= db.max() - E["ref_window_db"]] if len(db) else db   # the loud part, counted only over frames near the top, so how much
    p95 = float(np.percentile(top, 95)) if len(top) else -120.0       # noise surrounds the words (a 4 s tail, or none) does not move it
    floor = float(np.percentile(live, 10)) if len(live) else -120.0
    return {"db": db, "flat": flat, "hi_db": hi_db, "band_db": band_db, "zcr": zcr, "period": period, "f0": f0,
            "hop": hop, "win": win, "p95": p95, "floor": floor, "n": nf}


# ------------------------------------------------------------------ the speech span
def speech_span(x, rate: int, E: dict | None = None, F: dict | None = None, done_after_s: float | None = None,
                _masks: dict | None = None) -> dict:
    """Find onset and offset of the words. -> dict (frame and second values). Raises ValueError on silent audio.
    done_after_s (optional, from the text: letters / the voice's slowest rate, `take.gen_cap`): by then the line is
    certainly spoken, so a voiced run that STARTS later, after a pause of at least `run_gap_s`, is the model running on
    past the text, not a word. Without it no run is dropped for its position."""
    E = E or params()
    F = F or features(x, rate, E)
    db, p95, floor, hop, win = F["db"], F["p95"], F["floor"], F["hop"], F["win"]
    if p95 < E["silent_p95_dbfs"]:
        raise ValueError("audio is silent")
    voiced = (F["period"] >= E["voicing_threshold"]) & (db >= p95 - E["voiced_below_p95_db"]) & \
             (F["band_db"] >= E["voiced_min_band_share_db"])
    strong = voiced & (db >= p95 - E["loud_below_p95_db"])
    ref = F["f0"][strong] if strong.sum() >= 5 else F["f0"][voiced]
    med_f0 = float(np.median(ref)) if len(ref) else 0.0
    pitch_ok = np.abs(12 * np.log2(np.maximum(F["f0"], 1e-6) / med_f0)) <= E["core_f0_max_st"] if med_f0 > 0 else np.ones(len(db), bool)
    voiced &= pitch_ok                               # the speaker's own pitch: a drone or a squeal far from it is not a voice
    gap_f =max(1, int(round(E["run_gap_s"] / E["hop_s"])))
    runs, cur, last = [], None, None
    for i in np.nonzero(voiced)[0]:
        if cur is not None and i - last <= gap_f:
            cur[1] = i
        else:
            cur = [int(i), int(i)]
            runs.append(cur)
        last = i
    min_run = max(1, int(round(E["min_run_s"] / E["hop_s"])))
    kept, dropped, runon = [], 0, 0
    for a, b in runs:
        v = np.sort(db[a:b + 1][voiced[a:b + 1]])
        p90 = v[min(len(v) - 1, int(len(v) * .9))]
        if p90 >= p95 - E["stray_below_p95_db"] and int(voiced[a:b + 1].sum()) >= min_run:
            kept.append((a, b))
        else:
            dropped += 1
    if not kept:
        raise ValueError("no voiced speech found")
    if done_after_s is not None:                     # Chatterbox run-on: a run that starts after the text must be spoken, after a pause
        lim_f = kept[0][0] + done_after_s * rate / hop
        keep2 = [kept[0]]
        for a, b in kept[1:]:
            if a > lim_f and a - keep2[-1][1] > gap_f:
                runon += 1
                continue
            keep2.append((a, b))
        kept = keep2
    fr = E["fricative"]
    loud = db >= p95 - E["loud_below_p95_db"]
    attached = (db >= p95 - E["attach_below_p95_db"]) & (F["band_db"] >= E["attach_min_band_share_db"]) & \
               (F["flat"] <= E["attach_max_flatness"])   # energetic and shaped like a voice; a flat hiss is not
    fric = (db >= p95 - fr["below_p95_db"]) & \
           (F["hi_db"] >= fr["min_hi_db"]) & (F["zcr"] >= fr["min_zcr"]) & (F["flat"] <= fr["max_flatness"])   # a hiss is flat across the band; a fricative piles its energy high
    decay = (F["period"] >= E["voicing_threshold"]) & pitch_ok & (db >= p95 - E["decay_below_p95_db"])   # a final nasal (م ن) or voiced decay: periodic at the speaker's pitch, low in level and in band
    sound = loud | attached | fric | decay
    if _masks is not None:                           # the per-frame classes, for pause_mask (the mastering expander reads them)
        _masks.update(sound=sound | voiced, voiced=voiced, loud=loud, fric=fric, decay=decay, attached=attached, F=F)
    bridge = max(0, int(round(E["attach_bridge_s"] / E["hop_s"])))

    def extend(i0, step, max_s):
        """Walk from core edge i0 outward; return the last frame that is still a sound of the word."""
        lim = int(round(max_s / E["hop_s"]))
        edge, i, gap, quiet = i0, i0 + step, 0, 0
        while 0 <= i < len(db):
            if sound[i]:
                if not loud[i]:
                    quiet += 1 + gap
                    if quiet > lim:
                        break
                edge, gap = i, 0
            else:
                gap += 1
                if gap > bridge:
                    break
            i += step
        return edge

    c0, c1 = kept[0][0], kept[-1][1]
    on_f = extend(c0, -1, E["attach_max_lead_s"])
    off_f = extend(c1, +1, E["attach_max_tail_s"])
    act = np.nonzero((db >= p95 - E["active_below_p95_db"]) & (db > E["active_min_dbfs"]))[0]
    a0 = int(act[0]) if len(act) else on_f
    a1 = int(act[-1]) if len(act) else off_f
    t = lambda i: i * hop / rate
    onset_s, offset_s = t(on_f), t(off_f) + win / rate
    first_s, last_s = t(min(a0, on_f)), t(max(a1, off_f)) + win / rate
    return {"onset_s": round(onset_s, 4), "offset_s": round(offset_s, 4), "span_s": round(offset_s - onset_s, 4),
            "core_on_s": round(t(c0), 4), "core_off_s": round(t(c1) + win / rate, 4),
            "first_sound_s": round(first_s, 4), "last_sound_s": round(last_s, 4),
            "lead_window_s": round(max(0.0, onset_s - first_s), 4), "tail_window_s": round(max(0.0, last_s - offset_s), 4),
            "p95_db": round(p95, 1), "floor_db": round(floor, 1), "f0_median_hz": round(med_f0, 1), "dropped_runs": dropped,
            "runon_runs": runon, "seconds": round(len(x) / rate, 4)}


def pause_mask(x, rate: int, pad_s: float, pause_min_s: float, E: dict | None = None, done_after_s: float | None = None) -> dict:
    """Which 20 ms / 10 ms frames are TRUE PAUSES: the mastering expander may lower these and nothing else (owner, 2026-10-26: the
    expander pulled quiet voiced word endings down by about 10 dB). Same detector as the cleaner and VOICE-EDGE-NOISE (`speech_span`),
    so the three agree on what is speech.
      protected = every frame the detector calls a sound of a word (loud, attached, voiced, fricative, voiced decay), widened by pad_s
                  each side; and every gap between protected frames shorter than pause_min_s (a pause inside a phrase, a word gap).
      pause     = the rest: gaps of at least pause_min_s between phrases, and everything outside the speech span that is not a sound.
    Frames inside the speech span that are not in a pause are never touched. -> {"pause": bool[n], "protected": bool[n], "span": record,
    "hop", "win", "pause_s", "protected_s"}. Raises ValueError on a silent take, as speech_span does."""
    from scipy.ndimage import maximum_filter1d
    E = E or params()
    m: dict = {}
    s = speech_span(x, rate, E, done_after_s=done_after_s, _masks=m)
    F = m["F"]
    n, hop = F["n"], F["hop"]
    pad = max(0, int(round(pad_s / E["hop_s"])))
    prot = m["sound"].copy()
    if pad:
        prot = maximum_filter1d(prot.astype("uint8"), size=2 * pad + 1, mode="constant").astype(bool)
    on_f, off_f = int(s["onset_s"] * rate / hop), int(round((s["offset_s"] * rate - F["win"]) / hop))
    minf = max(1, int(round(pause_min_s / E["hop_s"])))
    idx = np.nonzero(~prot)[0]
    pause = np.zeros(n, dtype=bool)
    if len(idx):
        cuts = np.nonzero(np.diff(idx) > 1)[0] + 1
        for run in np.split(idx, cuts):
            a, b = int(run[0]), int(run[-1])
            outside = b < on_f or a > off_f                                 # entirely before the first word or after the last one
            edge = a == 0 or b == n - 1                                     # a run touching the file edge has no word on one side
            if outside or edge or (b - a + 1) >= minf:
                pause[a:b + 1] = True
    protected = ~pause
    return {"pause": pause, "protected": protected, "span": s, "hop": hop, "win": F["win"],
            "pause_s": round(float(pause.sum()) * E["hop_s"], 3), "protected_s": round(float(protected.sum()) * E["hop_s"], 3)}


def noise_edges(x, rate: int, E: dict | None = None, done_after_s: float | None = None) -> dict:
    """VOICE-EDGE-NOISE measure: noise-only sound before the onset and after the offset, beyond the guards, in ms."""
    E = E or params()
    s = speech_span(x, rate, E, done_after_s=done_after_s)
    s["lead_noise_ms"] = round(max(0.0, s["lead_window_s"] - E["lead_guard_s"]) * 1000)
    s["tail_noise_ms"] = round(max(0.0, s["tail_window_s"] - E["tail_guard_s"]) * 1000)
    return s


def edge_problems(x, rate: int, profile: dict | None = None) -> list[str]:
    """-> messages (empty = the take's edges are clean). Same detector as the cleaner, limits in `checks.edge_noise`."""
    E, C = params(profile), check_limits(profile)
    try:
        s = noise_edges(x, rate, E)
    except ValueError as e:
        return [f"no speech span: {e}"]
    out = []
    if s["lead_noise_ms"] > C["max_lead_ms"]:
        out.append(f"noise-only lead-in {s['lead_noise_ms']} ms before the first word, beyond the {round(E['lead_guard_s'] * 1000)} ms guard (limit {C['max_lead_ms']})")
    if s["tail_noise_ms"] > C["max_tail_ms"]:
        out.append(f"noise-only tail {s['tail_noise_ms']} ms after the last word, beyond the {round(E['tail_guard_s'] * 1000)} ms guard (limit {C['max_tail_ms']})")
    return out


# ------------------------------------------------------------------ the cleaner
def clean_bounds(x, rate: int, E: dict | None = None, done_after_s: float | None = None) -> dict:
    """-> start/end sample of what is kept (span plus guards), and the span record."""
    E = E or params()
    s = speech_span(x, rate, E, done_after_s=done_after_s)
    n = len(x)
    start = max(0, int(round((s["onset_s"] - E["lead_guard_s"]) * rate)))
    end = min(n, int(round((s["offset_s"] + E["tail_guard_s"]) * rate)))
    return {"start": start, "end": end, "span": s}


def fade(n: int, out: bool) -> np.ndarray:
    """Equal-power (sine/cosine) fade of n samples."""
    if n <= 0:
        return np.ones(0)
    t = (np.arange(n) + 0.5) / n
    return np.cos(0.5 * math.pi * t) if out else np.sin(0.5 * math.pi * t)


def clean(x, rate: int, E: dict | None = None, done_after_s: float | None = None) -> tuple[np.ndarray, dict]:
    """Keep span + guards, equal-power fades inside the guards only, nothing else touched. -> (body, record).
    The body has no pads; trim_take adds the clean digital-silence pads."""
    E = E or params()
    x = np.asarray(x, dtype="float64")
    b = clean_bounds(x, rate, E, done_after_s)
    s, start, end = b["span"], b["start"], b["end"]
    body = x[start:end].copy()
    on = int(round(s["onset_s"] * rate)) - start          # first sample of the span inside body
    off = int(round(s["offset_s"] * rate)) - start        # first sample after the span inside body
    fi = min(int(round(E["fade_in_s"] * rate)), max(0, on))
    fo = min(int(round(E["fade_out_s"] * rate)), max(0, len(body) - off))
    if fi and start > 0:                                   # a fade only where something was cut away
        body[:fi] *= fade(fi, out=False)
    if fo and end < len(x):
        body[len(body) - fo:] *= fade(fo, out=True)
    rec = {"start": start, "end": end, "cut_lead_ms": round(start * 1000 / rate), "cut_tail_ms": round((len(x) - end) * 1000 / rate),
           "fade_in_ms": round(fi * 1000 / rate) if start > 0 else 0, "fade_out_ms": round(fo * 1000 / rate) if end < len(x) else 0,
           "span": s, "method": "voice_edges.clean (take.edge.*)"}
    return body, rec


# ------------------------------------------------------------------ cli
def _read(path):
    sys.path.insert(0, str(TOOLS))
    import voice as V
    x, rate = V.read_float(path)
    return np.asarray(x, dtype="float64"), rate


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    if len(argv) >= 2 and argv[0] == "measure":
        bad = 0
        for p in argv[1:]:
            x, r = _read(p)
            s = noise_edges(x, r)
            pr = edge_problems(x, r)
            bad += bool(pr)
            print(json.dumps({"file": p, **s, "problems": pr}, ensure_ascii=False))
        return 1 if bad else 0
    if len(argv) == 3 and argv[0] == "clean":
        if Path(argv[1]).resolve() == Path(argv[2]).resolve():
            print("refused: the output would overwrite the input", file=sys.stderr)
            return 2
        sys.path.insert(0, str(TOOLS))
        import voice as V
        x, r = _read(argv[1])
        y, rec = clean(x, r)
        V.write_wav16(argv[2], [float(v) for v in y], r)
        print(json.dumps(rec, ensure_ascii=False))
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
