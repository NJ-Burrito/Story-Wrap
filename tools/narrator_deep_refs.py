"""Signal-only measurements of candidate narrator reference clips (owner, 2026-10-26: deep, calm, clean).

No ASR, no model: median F0 (librosa pyin, DSP), REF-QUALITY profile (tools/voice.py ref_profile), reverb proxy
(decay20_s of the profile), noise floor and SNR. Subcommands (run with: uv run --with numpy,soundfile,librosa python -I? no: see usage):

  scan   <dir-of-wavs> <out.json> [--maxf0 130]   fast yin F0 for every wav, keep those under maxf0, then profile them
  measure <wav> ...                                 pyin F0 + profile + REF-QUALITY problems, printed as JSON
  clean  <in.wav> <out.wav>                         deterministic DSP only: trim to speech, 40 Hz high-pass, gentle
                                                    spectral denoise (afftdn nr 6 dB, no gate), -23 LUFS; log printed
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import numpy as np
import soundfile as sf
import librosa
import voice


def load24(p):
    x, sr = sf.read(str(p), dtype="float32")
    if x.ndim > 1:
        x = x.mean(1)
    if sr != 24000:
        x = librosa.resample(x, orig_sr=sr, target_sr=24000)
    return x, 24000


def f0_stats(x, sr, fast=False):
    y = librosa.resample(x, orig_sr=sr, target_sr=16000)
    hop = 160
    rms = librosa.feature.rms(y=y, frame_length=1024, hop_length=hop)[0]
    if fast:
        f0 = librosa.yin(y, fmin=55, fmax=300, sr=16000, frame_length=1024, hop_length=hop)
        n = min(len(f0), len(rms))
        f0, rms = f0[:n], rms[:n]
        keep = rms > rms.max() * 0.15
        v = f0[keep]
    else:
        f0, vf, _ = librosa.pyin(y, fmin=55, fmax=300, sr=16000, frame_length=1024, hop_length=hop)
        n = min(len(f0), len(rms))
        f0, rms = f0[:n], rms[:n]
        v = f0[~np.isnan(f0)]
    if len(v) < 10:
        return None
    semis = 12 * np.log2(v / np.median(v))
    return {"median_hz": round(float(np.median(v)), 1), "p10_hz": round(float(np.percentile(v, 10)), 1),
            "p90_hz": round(float(np.percentile(v, 90)), 1), "sd_semitones": round(float(semis.std()), 2), "voiced_frames": int(len(v))}


def profile(p):
    x, sr = load24(p)
    xs = [float(v) for v in x]
    prof = voice.ref_profile(xs, sr)
    return prof, voice.ref_quality_problems(prof)


def cmd_scan(d, out, maxf0=130.0):
    rows = []
    wavs = sorted(list(Path(d).glob("*.wav")) + list(Path(d).glob("*.mp3")))
    for i, w in enumerate(wavs):
        try:
            x, sr = load24(w)
            f = f0_stats(x, sr, fast=True)
        except Exception as e:
            continue
        if f and f["median_hz"] <= maxf0:
            prof, bad = profile(w)
            rows.append({"file": str(w), "f0_fast": f, "profile": prof, "problems": bad})
        if i % 100 == 0:
            print(i, len(wavs), len(rows), flush=True)
    rows.sort(key=lambda r: r["f0_fast"]["median_hz"])
    Path(out).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print("kept", len(rows), "->", out)


def cmd_cut(src, outdir, lo=6.0, hi=11.0):
    """Cut pause-bounded windows of lo..hi seconds (pauses of 250 ms or more) from a decoded source; 10 ms fades; no other processing."""
    Path(outdir).mkdir(parents=True, exist_ok=True)
    tmp = Path(outdir) / "_src.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-ac", "1", "-ar", "24000", str(tmp)], check=True)
    x, sr = sf.read(str(tmp), dtype="float32")
    tmp.unlink()
    hop = 240
    n = len(x) // hop
    db = 20 * np.log10(np.sqrt((x[:n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-9)
    sil = db < np.percentile(db, 95) - 28
    cuts, run = [0], 0
    for i, v in enumerate(sil):
        run = run + 1 if v else 0
        if run == 25:
            cuts.append(i - 12)
    cuts.append(n)
    i, k = 0, 0
    stem = Path(src).stem
    while i < len(cuts) - 1:
        j = i + 1
        while j < len(cuts) and (cuts[j] - cuts[i]) * hop / sr < lo:
            j += 1
        if j >= len(cuts):
            break
        a, b = cuts[i] * hop, cuts[j] * hop
        if lo <= (b - a) / sr <= hi:
            y = x[max(0, a - int(.2 * sr)):b + int(.25 * sr)].copy()
            f = int(.01 * sr)
            y[:f] *= np.linspace(0, 1, f)
            y[-f:] *= np.linspace(1, 0, f)
            sf.write(str(Path(outdir) / f"{stem}_{cuts[i]:06d}.wav"), y, sr, subtype="PCM_16")
            k += 1
        i = j
    print(stem, "windows", k)


def cmd_signals(plan_path):
    """Adds per voice: F0 and REF-quality profile of the joined clip, words per second per line (text words / trimmed seconds)."""
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    mp = Path(plan["metrics_out"])
    m = json.loads(mp.read_text(encoding="utf-8"))
    root = Path(plan["out_dir"])
    words = {l["id"]: len(l["text"].split()) for l in plan["lines"]}
    for k, v in m["voices"].items():
        if not v.get("joined"):
            continue
        x, sr = load24(root / v["joined"]["file"])
        prof = voice.ref_profile([float(t) for t in x], sr)
        tps = []
        for l in v["lines"]:
            if "file" in l:
                lx, lsr = load24(root / l["file"])
                tps.append(voice.take_profile([float(t) for t in lx], lsr))
        pr = sorted(t["pause_rel_db"] for t in tps if t["pause_rel_db"] is not None)
        bad = sorted({m for t in tps for m in voice.take_quality_problems(t)})
        pause_med = pr[len(pr) // 2] if pr else None
        v["signal"] = {"f0": f0_stats(x, sr), "pause_rel_db_median": pause_med,
                       "snr_est_db": None if pause_med is None else round(-pause_med, 1),
                       "centroid_hz": prof["centroid_hz"], "crest_db": prof["crest_db"],
                       "clip_samples": sum(t["clip_samples"] for t in tps), "hum_db_max": max((t["hum_db"] or 0) for t in tps),
                       "gate_gaps": sum(t["gate_gaps"] for t in tps), "take_quality_problems": bad,
                       "reverb_decay20_s": prof["decay20_s"],
                       "words_per_s": {l["id"]: round(words[l["id"]] / l["audio_s"], 2) for l in v["lines"] if "audio_s" in l}}
        ws = list(v["signal"]["words_per_s"].values())
        v["signal"]["words_per_s_mean"] = round(sum(ws) / len(ws), 2)
        print(k, json.dumps(v["signal"], ensure_ascii=False))
    mp.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")


def cmd_measure(paths):
    for p in paths:
        x, sr = load24(p)
        prof, bad = profile(p)
        print(json.dumps({"file": str(p), "f0": f0_stats(x, sr), "profile": prof, "problems": bad}, ensure_ascii=False))


def lufs(path):
    import re
    r = subprocess.run(["ffmpeg", "-nostats", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    m = re.search(r"I:\s+(-?[\d.]+) LUFS", r.stderr.split("Summary:")[-1])
    return float(m.group(1))


def cmd_clean(src, dst, hp=40):
    """Deterministic DSP only: trim to speech edges (voice.trim_bounds, energy only), 40 Hz high-pass (below any male F0),
    one linear gain to -23 LUFS. No denoise and no gate: on these clips afftdn lowered the SNR and made digital silence (measured)."""
    x, sr = load24(src)
    b = voice.trim_bounds([float(v) for v in x], sr)
    a, e = max(0, b["start"] - int(0.30 * sr)), min(len(x), b["end"] + int(0.30 * sr))
    tmp = Path(str(dst) + ".cut.wav")
    sf.write(str(tmp), x[a:e], sr, subtype="PCM_16")
    hpf = Path(str(dst) + ".hp.wav")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(tmp), "-af", f"highpass=f={hp}:poles=2", "-c:a", "pcm_s16le", str(hpf)], check=True)
    gain = round(-23.0 - lufs(hpf), 2)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(hpf), "-af", f"volume={gain}dB", "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", str(dst)], check=True)
    tmp.unlink(); hpf.unlink()
    log = {"in": str(src), "trim_s": [round(a / sr, 2), round(e / sr, 2)], "steps": [f"highpass {hp} Hz 2 poles", f"gain {gain} dB to -23 LUFS"], "out": str(dst)}
    print(json.dumps(log, ensure_ascii=False))
    return log


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[0] == "scan":
        cmd_scan(a[1], a[2], float(a[a.index("--maxf0") + 1]) if "--maxf0" in a else 130.0)
    elif a[0] == "cut":
        cmd_cut(a[1], a[2])
    elif a[0] == "signals":
        cmd_signals(a[1])
    elif a[0] == "measure":
        cmd_measure(a[1:])
    elif a[0] == "clean":
        cmd_clean(a[1], a[2])
    else:
        print(__doc__)
