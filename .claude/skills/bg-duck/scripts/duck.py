"""bg-duck: put a music bed under a voice track with the Story-Wrap calm_mix chain.

    python duck.py VOICE MUSIC OUT.wav [--depth-db 9] [--below-lu L] [--fade-in 1] [--fade-out 2] [--json]

The music is looped or trimmed to the voice length, faded, set L LU under the voice, ducked by a
voice-keyed envelope (80 ms lookahead, gaps under 0.3 s bridged, fixed depth), summed, brought to
-14 LUFS by one linear gain, and limited only if the true peak asks for it. Every default comes from
tools/sound_profile.json, the same numbers the episodes use. Reports measured loudness, true peak
and the duck depth actually applied (bed level while speaking vs while silent).
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

TOOLS = Path(__file__).resolve().parents[4] / "tools"      # .claude/skills/bg-duck/scripts -> repo/tools
sys.path.insert(0, str(TOOLS))
import audio_checks as A  # noqa: E402
import calm_mix as M  # noqa: E402

P = M.PRESETS["phone-first"]


def load(path: Path, wd: Path, name: str, loop_to: float | None = None) -> np.ndarray:
    out = wd / f"{name}.wav"
    pre = ["-stream_loop", "-1"] if loop_to else []
    post = ["-t", f"{loop_to:.3f}"] if loop_to else []
    M.ff([*pre, "-i", path, *post, "-ac", "2", "-ar", A.SR, "-c:a", "pcm_f32le", out])
    return A.read_wav(out)[0]


def fade(x: np.ndarray, fin: float, fout: float) -> np.ndarray:
    n = len(x)
    g = np.ones(n, dtype="float32")
    a, b = min(n, int(fin * A.SR)), min(n, int(fout * A.SR))
    if a:
        g[:a] = np.linspace(0, 1, a, dtype="float32")
    if b:
        g[n - b:] *= np.linspace(1, 0, b, dtype="float32")
    return x * g[:, None]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("voice", type=Path)
    ap.add_argument("music", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--depth-db", type=float, default=P["duck_db"]["bed"])
    ap.add_argument("--below-lu", type=float, default=P["bed_below_voice_lu"])
    ap.add_argument("--fade-in", type=float, default=1.0)
    ap.add_argument("--fade-out", type=float, default=2.0)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    for p in (a.voice, a.music):
        if not p.is_file():
            print(f"missing file: {p}", file=sys.stderr)
            return 2

    with tempfile.TemporaryDirectory(dir=a.out.resolve().parent) as td:
        wd = Path(td)
        voice = load(a.voice, wd, "voice")
        n = len(voice)
        dur = n / A.SR
        bed = M.padded(load(a.music, wd, "music", loop_to=dur), n)
        bed = fade(bed, a.fade_in, a.fade_out)

        v_lufs = A.integrated_lufs(voice)
        bed *= 10 ** (((v_lufs - a.below_lu) - A.integrated_lufs(bed)) / 20)

        act = M.voice_activity(voice)
        env = M.duck_envelope(act, n, a.depth_db, **P["duck"])
        bed_d = bed * env[:, None]

        pre = voice + bed_d
        lin = 10 ** ((M.LOUD_I - A.integrated_lufs(pre)) / 20)
        mix = pre * lin
        limited = False
        if A.true_peak_db(mix) > M.LOUD_TP:
            limited = True
            A.write_wav(wd / "premaster.wav", mix)
            lim = 10 ** ((M.LOUD_TP - 0.4) / 20)
            M.ff(["-i", wd / "premaster.wav", "-af", f"alimiter=limit={lim:.4f}:attack=5:release=60:level=disabled",
                  "-c:a", "pcm_f32le", wd / "limited.wav"])
            mix = M.padded(A.read_wav(wd / "limited.wav")[0], n)
        a.out.parent.mkdir(parents=True, exist_ok=True)
        A.write_wav(a.out, mix)

    # measured duck depth: bed level while the voice speaks vs while it is silent (10 ms frames)
    frames = np.repeat(act, int(0.01 * A.SR))[:n]
    def rms_db(x):
        return float(20 * np.log10(np.sqrt((A.mono(x)[:, 0].astype("float64") ** 2).mean() + 1e-14)))
    speak, quiet = bed_d[: len(frames)][frames], bed_d[: len(frames)][~frames]
    depth = round(rms_db(bed[: len(frames)][frames]) - rms_db(speak), 2) if speak.size else None
    rep = {"out": str(a.out), "duration_s": round(dur, 2), "integrated_lufs": round(A.integrated_lufs(mix), 2),
           "true_peak_dbtp": round(A.true_peak_db(mix), 2), "limited": limited,
           "bed_below_voice_lu": a.below_lu, "duck_depth_set_db": a.depth_db, "duck_depth_measured_db": depth,
           "voice_active_share": round(float(act.mean()), 3), "quiet_frames": int(quiet.shape[0] > 0)}
    ok = abs(rep["integrated_lufs"] - M.LOUD_I) <= 1.0 and rep["true_peak_dbtp"] <= M.LOUD_TP + 0.05
    rep["pass"] = ok
    print(json.dumps(rep, ensure_ascii=False, indent=None if a.json else 1))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
