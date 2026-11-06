# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "scipy"]
# ///
"""Phone-first mix chain for the calm format (owner, 2026-10-25, note C9: "an agent specialised in sound engineering to make and mix the sounds better for a normal viewer on his phone").

  uv run tools/calm_mix.py render <ep> [--preset phone-first]   re-mix an episode's audio only (voice takes + sfx.json + a pad bed) into mix.wav and audio/stems/
  uv run tools/calm_mix.py sfx-audit                            measure every sound in assets/audio/sfx/ the way a phone plays it (research/sound-e01c.md table)
  uv run tools/calm_mix.py presets                              list the presets

`calm_compose.stage_audio` calls `render`, so `calm_compose.py audio E01C` is the normal way in; the module is also runnable on its own for a quick re-mix.

Why the chain looks like this (measured on E01C, research/sound-e01c.md):
  * The old bed (55 and 82 Hz sines + brown noise) had no energy above 200 Hz, so a phone played none of it, while it still took 22 LU of the loudness budget.
    The new bed is a pad whose notes and harmonics sit at 150 Hz to 2.5 kHz, with a scoop at 2 to 3 kHz where speech lives.
  * SFX gains were set from each FILE'S PEAK, so two sounds of equal peak could differ by 20 LU in loudness; some needed +22 dB. Now a cue is set to a loudness
    relative to the dialogue, measured the way a phone plays it (band-limited, mono).
  * Ducking was ffmpeg `sidechaincompress` (ratio 9 on the bed): the depth swung with the keyed level and it had no lookahead. The envelope is now computed from the voice
    stem: fixed depth per bus, 80 ms lookahead, gaps under 0.3 s bridged so the bed does not pump between words.
  * A compressor on the SUM (threshold 0.03, ratio 8, makeup 3) moved the whole mix 20 dB around, raising the sfx tails and bed in every pause. Compression is now per source.
  * Final loudness is a linear gain to -14 LUFS (BS.1770 gated, computed from the same stems the checks read), then a lookahead limiter only if the true peak needs it.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
from scipy import signal

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import audio_checks as A  # noqa: E402

ROOT = Path(os.environ.get("STORYWRAP_ROOT") or TOOLS.parent)
SR = A.SR
ENV = {**os.environ, "PYTHONUTF8": "1"}

PROFILE = json.loads((TOOLS / "sound_profile.json").read_text(encoding="utf-8"))   # every number below comes from the one profile (2026-10-26)
LOUD_I, LOUD_TP = PROFILE["master"]["lufs_target"], PROFILE["master"]["true_peak_target_dbtp"]


def _preset(P: dict) -> dict:
    V, B, S, D = P["voice"], P["bed"], P["sfx"], P["duck"]
    return {
        "voice_target_lufs": V["lufs_target"],          # every take is brought to this (gated) before the bus: narrator and characters sit at one level
        "voice_hp_hz": V["highpass_hz"],
        "voice_eq": [tuple(b) for b in V["eq"]],         # (Hz, Q, dB): cut the boxy low mids a phone turns to honk, lift presence
        "deess_when_db": V["deess_when_db"],             # de-ess a take only when its 5 to 9 kHz band is within this many dB of its speech band
        "deess": V["deess"],
        "comp": V["comp"],
        "voice_limit": V["limit"],                       # lookahead limiter on the voice bus: the voice peaks stay 7.5 dB under full scale before the master gain
        "bed_below_voice_lu": B["below_voice_lu"],       # bed loudness under the voice, both measured through the phone simulation
        "bed_hp_hz": B["highpass_hz"], "bed_lp_hz": B["lowpass_hz"], "bed_scoop": tuple(B["scoop"]),
        "duck_db": dict(D["depth_db"]),                  # how far each bus drops while somebody speaks
        "duck": {k: D[k] for k in ("lead_s", "attack_s", "release_s", "bridge_s")},
        "rel_db": dict(S["rel_db"]),                     # cue loudness (phone simulation, loudest 400 ms) relative to the voice
        "sound_adj_db": dict(S["sound_adj_db"]),
        "gain_limits_db": tuple(S["gain_limits_db"]),
        "sfx_peak_under_voice_db": S["peak_under_voice_db"],   # a cue's peak stays at least this far under the voice stem's peak
    }


# ------------------------------------------------------------------ presets (numbers from tools/sound_profile.json; tune by ear, never loosen a check)
PRESETS = {"phone-first": _preset(PROFILE)}

# per-sound filtering applied before the level is measured: (high-pass Hz, low-pass Hz). A phone speaker plays nothing under ~300 Hz, so energy there is rumble that eats headroom.
SFX_BAND = {k: tuple(v) for k, v in PROFILE["sfx"]["band"].items()}
DEDUPE_WINDOW_S = PROFILE["sfx"]["dedupe_window_s"]


# ------------------------------------------------------------------ small helpers
def ff(args, check=True):
    r = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-v", "error", "-threads", "2", "-filter_threads", "2", *map(str, args)], capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV)
    if check and r.returncode:
        raise RuntimeError("ffmpeg failed: " + r.stderr[-600:])
    return r


def padded(x: np.ndarray, n: int) -> np.ndarray:
    return np.pad(x, ((0, max(0, n - len(x))), (0, 0)))[:n]


def event_loudness(x: np.ndarray) -> float:
    """Loudest window of one sound in LUFS: 400 ms, or the sound's own length when shorter (a 160 ms pop averaged over 400 ms would read 4 dB too quiet). Input is stereo 48 kHz."""
    w = min(0.4, max(len(x) / SR, 0.02))
    ms = A.block_ms(x, w, 0.02)
    return float(A.lufs(ms.max()))


def phone_stereo(x: np.ndarray) -> np.ndarray:
    return np.repeat(A.phone_sim(x), 2, axis=1)


def _graph_file(path: Path, fl: list) -> str:
    Path(path).write_text((";" + chr(10)).join(fl), encoding="utf-8")   # long graphs go through a file: Windows' command line is 32 k
    return str(path)


# ------------------------------------------------------------------ the bed: a pad a phone can play
def synth_pad(total_s: float, seed: int = 2525) -> np.ndarray:
    """A dark ambient pad, stereo, deterministic (numpy, no sample, no licence): A minor to F major seventh, two slow chord changes, each tone one oscillator stack with harmonics to
    2.5 kHz and a slow swell that differs per side (width without phase tricks: the mono fold keeps every note). Notes sit from 110 Hz up: a phone (300 Hz and up) plays the 2nd to 8th harmonics and still hears a chord. A soft 55 Hz sub gives earbuds the floor."""
    rng = np.random.default_rng(seed)
    n = int(round(total_s * SR))
    t = np.arange(n) / SR
    chords = [(110.0, 164.81, 220.0, 261.63, 329.63), (87.31, 174.61, 220.0, 261.63, 349.23), (110.0, 164.81, 207.65, 261.63, 329.63)]   # Am, F, Am(E7-ish colour)
    seg = max(total_s / 3.0, 1.0)
    out = np.zeros((n, 2))
    for ci, ch in enumerate(chords):
        centre = (ci + 0.5) * seg
        w = np.exp(-0.5 * ((t - centre) / (seg * 0.55)) ** 2)           # each chord swells in and out; neighbours overlap, so the harmony drifts rather than switches
        for fi, f0 in enumerate(ch):
            ph0 = rng.uniform(0, 2 * np.pi)
            tone = np.zeros(n)
            for h in range(1, 9):
                if f0 * h > 2500:
                    break
                tone += np.sin(2 * np.pi * f0 * (1.0 + 0.0004 * fi) * h * t + ph0 * h) / (h ** 1.15)
            for side in (0, 1):
                # width comes from a different slow swell per side, NOT from detuning or different phases: both channels carry the same waveform, so the mono fold-down keeps every note
                lfo = 0.6 + 0.4 * np.sin(2 * np.pi * rng.uniform(0.04, 0.11) * t + rng.uniform(0, 6.28))
                out[:, side] += tone * w * lfo * 0.22
    sub = np.sin(2 * np.pi * 55.0 * t) * 0.10 * (0.7 + 0.3 * np.sin(2 * np.pi * 0.05 * t))
    out += sub[:, None]
    fade = np.minimum(1.0, np.minimum(t / 2.0, (total_s - t) / 2.0))
    return (out * fade[:, None]).astype("float32")


# ------------------------------------------------------------------ dialogue-first ducking
def voice_activity(voice: np.ndarray, frame_s: float = 0.01) -> np.ndarray:
    """True per 10 ms frame where the voice is above 38 dB under its own loudest 400 ms block (the pause floor of a calm narrator)."""
    mono = A.mono(voice)[:, 0].astype("float64")
    h = int(frame_s * SR)
    n = len(mono) // h
    r = np.sqrt((mono[: n * h].reshape(n, h) ** 2).mean(1) + 1e-14)
    db = 20 * np.log10(r)
    return db > (np.percentile(db, 99) - 38.0)


def duck_envelope(active: np.ndarray, n_samples: int, depth_db: float, lead_s=0.08, attack_s=0.05, release_s=0.45, bridge_s=0.30, frame_s: float = 0.01) -> np.ndarray:
    """Gain per sample (1.0 = untouched, 10^(-depth/20) = fully ducked). Gaps shorter than `bridge_s` between words are bridged; the duck starts `lead_s` BEFORE the voice (lookahead);
    attack and release are one-pole smoothers at the frame rate. Deterministic, so the same voice always gives the same duck, whatever level the voice has."""
    a = active.astype(float)
    br = max(1, int(bridge_s / frame_s))
    # bridge: dilate then erode by br/2 frames each side keeps gaps shorter than bridge_s closed
    k = np.ones(br)
    dil = np.convolve(a, k, mode="same") > 0
    ero = np.convolve(dil.astype(float), k, mode="same") >= br - 1e-6
    closed = ero | a.astype(bool)
    lead = int(lead_s / frame_s)
    sh = np.zeros_like(closed)
    sh[:-lead if lead else None] = closed[lead:] if lead else closed             # look ahead: the frame at t is ducked if the voice is active at t + lead
    tgt = sh.astype(float)
    g = np.zeros(len(tgt))
    ca, cr = 1 - np.exp(-frame_s / attack_s), 1 - np.exp(-frame_s / release_s)
    s = 0.0
    for i, v in enumerate(tgt):
        s += (ca if v > s else cr) * (v - s)
        g[i] = s
    depth = 1 - 10 ** (-depth_db / 20)
    env = 1 - depth * g
    t_frames = (np.arange(len(env)) + 0.5) * frame_s
    return np.interp(np.arange(n_samples) / SR, t_frames, env).astype("float32")


INTRO_DIP_DB, INTRO_DIP_FADE_S = PROFILE["duck"]["intro_dip_db"], PROFILE["duck"]["intro_dip_fade_s"]


def intro_dip(tl: dict, n_samples: int, depth_db: float = INTRO_DIP_DB, fade_s: float = INTRO_DIP_FADE_S) -> np.ndarray:
    """C10: the music holds its breath while the story is frozen on a character. The bed drops by `depth_db` for the whole intro_freeze item (after its join, before the next one starts),
    with `fade_s` fades. It also keeps the narrator's introduction clear of the bed in the soft stretches of a slow line (E01C I01: a 7.9 s line with a 1.3 s soft middle sat 7.45 dB over the bed). 1.0 elsewhere."""
    env = np.ones(n_samples, dtype="float32")
    g = 10 ** (-depth_db / 20)
    for it in tl.get("items", []):
        if it.get("kind") != "intro":
            continue
        a, b = it["t0"] + 0.25, it["t1"] - 0.25
        t = np.arange(n_samples) / SR
        up = np.clip((t - (a - fade_s)) / fade_s, 0, 1)
        down = np.clip(((b + fade_s) - t) / fade_s, 0, 1)
        env = np.minimum(env, 1 - (1 - g) * np.minimum(up, down)).astype("float32")
    return env


# ------------------------------------------------------------------ cue levels
def cue_target_lufs(cue: dict, voice_ref_lufs: float, P: dict) -> float:
    rel = P["rel_db"].get(cue.get("kind"), P["rel_db"]["foley"]) + P["sound_adj_db"].get(cue["sound"], 0.0)
    return voice_ref_lufs + rel


def cue_gain_db(file_loudness_lufs: float, target_lufs: float, limits=(-40.0, 32.0)) -> float:
    return round(float(min(max(target_lufs - file_loudness_lufs, limits[0]), limits[1])), 2)


def dedupe_cues(cues: list[dict], window: float = DEDUPE_WINDOW_S) -> tuple[list[dict], list[dict]]:
    """Two cues of the SAME sound within `window` s are one event placed twice (the choice sequence puts a pop on the cut and a pop on the line that start together):
    they add 6 dB. Keep the first, record the other."""
    keep, dropped = [], []
    for c in sorted(cues, key=lambda c: c["t"]):
        if any(k["sound"] == c["sound"] and abs(k["t"] - c["t"]) <= window for k in keep):
            dropped.append({"t": c["t"], "sound": c["sound"], "why": "same sound within %d ms" % int(window * 1000)})
        else:
            keep.append(c)
    return keep, dropped


def bus_of(cue: dict) -> str:
    return "bg" if cue.get("kind") == "foley" else "fg"      # foley sits under the dialogue deeper than a stinger does


# ------------------------------------------------------------------ voice chain
def master_record(take: Path) -> dict | None:
    """The report voice.py writes next to a mastered take (<id>.trimmed.master.json), or None for a take voiced before the chain."""
    p = Path(str(take)[:-4] + ".master.json")
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def voice_chain(P: dict, deess: bool) -> str:
    f = [f"highpass=f={P['voice_hp_hz']}:poles=2"]
    f += [f"equalizer=f={hz}:t=q:w={q}:g={g}" for hz, q, g in P["voice_eq"]]
    if deess:
        f.append(P["deess"])
    f.append(P["comp"])
    return ",".join(f)


def render(ep, preset: str = "phone-first") -> dict:
    """ep: calm_compose.Ep. Reads timeline.json, sfx.json, the trimmed takes. Writes mix.wav (16 bit, 48 kHz, stereo), audio/stems/{voice,bed,sfx}.wav (f32, after ducking and master gain)
    and audio/mix-report.json. Returns the numbers calm_compose records in audio.json."""
    P = PRESETS[preset]
    tl = json.loads(ep.timeline_p.read_text(encoding="utf-8"))
    sfx = json.loads((ep.work / "sfx.json").read_text(encoding="utf-8"))
    total = tl["total_s"]
    n = int(round(total * SR))
    wd = ep.work / "audio"
    pd, sd = wd / "proc", wd / "stems"
    pd.mkdir(parents=True, exist_ok=True)
    sd.mkdir(parents=True, exist_ok=True)

    # ---- 1. voice: clean each take, normalise it, place it
    lines = []
    for it in tl["items"]:
        if it.get("line"):
            lines.append((it["line"], it["voice_t0"]))
        lines += [(m["line"], m["voice_t0"]) for m in it.get("more_lines", [])]
    takes = []
    for lid, t0 in lines:
        src = ep.take(lid)
        raw, sr = A.read_wav(src)
        raw48 = A.stereo(A.to48(raw[:, :1], sr))
        sib = A.sibilance_index(raw48)["sib_minus_speech_db"]
        mastered = master_record(src)
        deess = (sib > P["deess_when_db"]) and not mastered
        out = pd / f"{lid}.wav"
        # a take voiced since 2026-10-26 went through THE chain (voice_master) already: only resampled here, never EQ'd or compressed twice.
        # A take without a master record (E01C and older) gets the 2026-10-25 mix chain, so an approved episode re-mixes exactly as before.
        ff(["-i", src, "-af", "aresample=48000" + ("" if mastered else "," + voice_chain(P, deess)), "-ac", "1", "-c:a", "pcm_f32le", out])
        x, _ = A.read_wav(out)
        li = A.integrated_lufs(np.repeat(x, 2, axis=1))
        gain = round(P["voice_target_lufs"] - li, 2)
        takes.append({"line": lid, "t0": t0, "sibilance_db": sib, "deessed": bool(deess), "mastered": bool(mastered), "lufs_after_chain": round(li, 2), "gain_db": gain, "file": str(out)})
    args, fl, labels = [], [], []
    for k, tk in enumerate(takes):
        ms = int(round(tk["t0"] * 1000))
        args += ["-i", tk["file"]]
        fl.append(f"[{k}:a]volume={tk['gain_db']}dB,pan=stereo|c0=c0|c1=c0,adelay={ms}|{ms}[v{k}]")
        labels.append(f"[v{k}]")
    fl.append(f"{''.join(labels)}amix=inputs={len(takes)}:normalize=0:duration=longest,apad=whole_dur={total:.3f},atrim=0:{total:.3f},alimiter=limit={P['voice_limit']}:attack=3:release=60:level=disabled[o]")
    ff([*args, "-filter_complex_script", _graph_file(wd / "voice.filtergraph", fl), "-map", "[o]", "-ar", SR, "-c:a", "pcm_f32le", wd / "voice_pre.wav"])
    voice = padded(A.read_wav(wd / "voice_pre.wav")[0], n)
    voice_phone = A.integrated_lufs(phone_stereo(voice))
    voice_ref = A.integrated_lufs(voice)

    # ---- 2. bed: the pad, band-shaped, set a fixed number of LU under the voice IN THE PHONE DOMAIN
    A.write_wav(wd / "bed_raw.wav", synth_pad(total))
    bs = f"highpass=f={P['bed_hp_hz']}:poles=2,lowpass=f={P['bed_lp_hz']}:poles=2,equalizer=f={P['bed_scoop'][0]}:t=q:w={P['bed_scoop'][1]}:g={P['bed_scoop'][2]}"
    ff(["-i", wd / "bed_raw.wav", "-af", bs, "-c:a", "pcm_f32le", wd / "bed_shaped.wav"])
    bed = padded(A.read_wav(wd / "bed_shaped.wav")[0], n)
    bed_gain = (voice_phone - P["bed_below_voice_lu"]) - A.integrated_lufs(phone_stereo(bed))
    bed = bed * 10 ** (bed_gain / 20)

    # ---- 3. sfx: one processed file per sound, a loudness per cue relative to the voice, two buses
    cues, dropped_same = dedupe_cues([c for c in sfx["cues"] if c["t"] < total - 0.05])
    proc, loud, peak = {}, {}, {}
    voice_peak = A.sample_peak_db(voice)
    for sid in sorted({c["sound"] for c in cues}):
        src = next(ROOT / c["file"] for c in cues if c["sound"] == sid)
        hp, lp = SFX_BAND.get(sid, SFX_BAND["default"])
        out = pd / f"sfx-{sid}.wav"
        ff(["-i", src, "-af", f"aresample=48000,aformat=channel_layouts=mono,highpass=f={hp}:poles=2,lowpass=f={lp}:poles=2,afade=t=in:d=0.004", "-c:a", "pcm_f32le", out])
        x, _ = A.read_wav(out)
        proc[sid] = out
        loud[sid] = event_loudness(phone_stereo(np.repeat(x, 2, axis=1)))
        peak[sid] = A.sample_peak_db(x)
    gains = []
    bus_args = {"fg": [], "bg": []}
    bus_fl = {"fg": [], "bg": []}
    for k, c in enumerate(cues):
        tgt = cue_target_lufs(c, voice_phone, P)
        g = cue_gain_db(loud[c["sound"]], tgt, P["gain_limits_db"])
        g = round(min(g, voice_peak - P["sfx_peak_under_voice_db"] - peak[c["sound"]]), 2)      # no sound peaks above the dialogue (AUDIO-PEAK), whatever its loudness target
        gains.append({"t": c["t"], "sound": c["sound"], "kind": c["kind"], "bus": bus_of(c), "target_phone_lufs": round(tgt, 1), "gain_db": g, "legacy_gain_db": c.get("gain_db")})
        b = bus_of(c)
        i = len(bus_args[b]) // 2
        bus_args[b] += ["-i", proc[c["sound"]]]
        ms = int(round(c["t"] * 1000))
        cut = f"atrim=0:{c['dur']:.3f},afade=t=out:st={max(0.0, c['dur'] - 0.12):.3f}:d=0.12," if c.get("dur") else ""
        bus_fl[b].append(f"[{i}:a]{cut}volume={g}dB,pan=stereo|c0=c0|c1=c0,adelay={ms}|{ms}[x{i}]")
    buses = {}
    for b in ("fg", "bg"):
        if bus_fl[b]:
            m = len(bus_fl[b])
            bus_fl[b].append(f"{''.join(f'[x{i}]' for i in range(m))}amix=inputs={m}:normalize=0:duration=longest,apad=whole_dur={total:.3f},atrim=0:{total:.3f}[o]")
            ff([*bus_args[b], "-filter_complex_script", _graph_file(wd / f"sfx_{b}.filtergraph", bus_fl[b]), "-map", "[o]", "-ar", SR, "-c:a", "pcm_f32le", wd / f"sfx_{b}_pre.wav"])
            buses[b] = padded(A.read_wav(wd / f"sfx_{b}_pre.wav")[0], n)
        else:
            buses[b] = np.zeros((n, 2), dtype="float32")

    # ---- 4. duck: the voice decides, fixed depth per bus
    act = voice_activity(voice)
    dk = P["duck"]
    env = {k: duck_envelope(act, n, P["duck_db"][k], **dk) for k in P["duck_db"]}
    bed_d = bed * env["bed"][:, None] * intro_dip(tl, n)[:, None]
    fg_d = buses["fg"] * env["fg"][:, None]
    bg_d = buses["bg"] * env["bg"][:, None]
    sfx_d = fg_d + bg_d

    # ---- 5. sum, master gain to -14 LUFS, limiter only when the true peak asks for it
    pre = voice + bed_d + sfx_d
    gain = LOUD_I - A.integrated_lufs(pre)
    lin = 10 ** (gain / 20)
    mix = pre * lin
    limited = False
    if A.true_peak_db(mix) > LOUD_TP:
        limited = True
        lim = 10 ** ((LOUD_TP - 0.4) / 20)
        for _ in range(4):
            lin_used = lin
            A.write_wav(wd / "premaster.wav", pre * lin)
            ff(["-i", wd / "premaster.wav", "-af", f"alimiter=limit={lim:.4f}:attack=5:release=60:level=disabled", "-c:a", "pcm_f32le", wd / "limited.wav"])
            mix = padded(A.read_wav(wd / "limited.wav")[0], n)
            short = LOUD_I - A.integrated_lufs(mix)
            if abs(short) < 0.15 and A.true_peak_db(mix) <= LOUD_TP + 0.05:
                break
            lin *= 10 ** (min(max(short, -1.0), 1.0) / 20)      # the limiter took some loudness: add it back and limit again
        lin = lin_used                                          # the stems carry the gain the delivered mix was actually made with
    stems = {"voice": voice * lin, "bed": bed_d * lin, "sfx": sfx_d * lin}
    for k, v in stems.items():
        A.write_wav(sd / f"{k}.wav", v.astype("float32"))
    A.write_wav(wd / "premix.wav", pre.astype("float32"))
    A.write_wav(wd / "master_f32.wav", mix.astype("float32"))
    ff(["-i", wd / "master_f32.wav", "-ar", SR, "-ac", "2", "-c:a", "pcm_s16le", ep.mix])
    rep = {"preset": preset, "voice_lines": len(takes), "sfx_cues": len(cues), "master_gain_db": round(20 * np.log10(lin), 2), "limiter_used": limited,
           "voice_ref_lufs": round(voice_ref, 2), "voice_phone_lufs": round(voice_phone, 2), "bed_gain_db": round(float(bed_gain), 2), "takes": takes, "cues": gains, "dropped_cues": dropped_same + sfx.get("dropped_stacked", []),
           "duck_db": P["duck_db"], "loudness_python": {"integrated_lufs": round(A.integrated_lufs(mix), 2), "true_peak_dbtp": round(A.true_peak_db(mix), 2), "lra_lu": round(A.loudness_range(mix), 2)}}
    (wd / "mix-report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    return rep


# ------------------------------------------------------------------ the sfx library, as a phone plays it
def sfx_audit(root: Path = ROOT) -> list[dict]:
    rows = []
    for p in sorted((root / "assets" / "audio" / "sfx").glob("*.wav")):
        x, sr = A.read_wav(p)
        x = A.stereo(A.to48(x, sr))
        m = A.mono(x)[:, 0].astype("float64")
        f = np.fft.rfftfreq(len(m), 1 / SR)
        P_ = np.abs(np.fft.rfft(m)) ** 2
        tot = max(P_.sum(), 1e-18)
        full = event_loudness(x)
        ph = event_loudness(phone_stereo(x))
        rows.append({"file": p.name, "dur_s": round(len(x) / SR, 2), "peak_db": round(A.sample_peak_db(x), 1), "event_lufs": round(full, 1), "phone_event_lufs": round(ph, 1),
                     "phone_loss_db": round(full - ph, 1), "under_200_pct": round(float(P_[f < 200].sum() / tot * 100), 1), "centroid_hz": int((f * P_).sum() / tot)})
    return rows


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("render", "sfx-audit", "presets"):
        print(__doc__)
        return 2
    if argv[0] == "presets":
        print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk in ("voice_target_lufs", "bed_below_voice_lu", "duck_db", "rel_db")} for k, v in PRESETS.items()}, indent=1))
        return 0
    if argv[0] == "sfx-audit":
        for r in sfx_audit():
            print(json.dumps(r))
        return 0
    import calm_compose as CC
    preset = argv[argv.index("--preset") + 1] if "--preset" in argv else "phone-first"
    rep = render(CC.Ep(argv[1]), preset)
    print(json.dumps({k: rep[k] for k in ("preset", "master_gain_db", "limiter_used", "loudness_python")}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
