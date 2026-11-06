# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy"]
# ///
"""Calm-format sound design (owner, 2026-10-25, notes C3 + C4 + C5 on E01 calm): every transition has a sound AND a visual, the 0:08 written-object
moment has a horn, the choice sequence pops in time with the narrator, and every prop and hand action in the shot specs has foley.

  uv run tools/calm_sfx.py synth          write the sounds we make ourselves (licence OWN) into assets/audio/sfx/ (deterministic, numpy, no network, no model)
  uv run tools/calm_sfx.py build <ep>     timeline.json + calm-plan.json + the shot specs -> work/episodes/<ep>/sfx.json (every cue: t, file, licence id, gain, why)
  uv run tools/calm_sfx.py check <ep>     the three checks below on sfx.json (also run by `calm_compose.py gate`)

Checks (ids are stable, every one runs every time, none is skipped):
  CALM-TRANSITION-SFX  every join between two items declares a cut type, the cut type gives a visual (xfade) AND a sound, and the sound is on the cue list at the join
  CALM-FOLEY           every shot whose spec lists a prop or a hand action with a sound (pen, key, tag, card, bag, bell, watch, steps, cloth, lamp) has a cue,
                       and every cue's file is licensed in assets/audio/LICENCES.md (sha256 matches)
  CALM-CHOICE-SFX      the choice sequence has a pop at every cut and one per narrated line (question, both choices, the hook)

Why a cut TYPE and not a free sound per join: the sound and the picture of a join are one gesture (a page turn is a reveal AND paper), so one name picks both
and they cannot drift apart. The plan names the type per join (`transitions` in calm-plan.json); this module only turns it into cues.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import wave
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("STORYWRAP_ROOT") or TOOLS.parent)
SFX_DIR = ROOT / "assets" / "audio" / "sfx"
LICENCES = ROOT / "assets" / "audio" / "LICENCES.md"
SR = 48000

# ------------------------------------------------------------------ the sound library (id -> file, licence id, kind). Licence ids are the rows of LICENCES.md.
LIB = {
    "whoosh":      ("whoosh-60007.wav", "sfx-whoosh-60007"),
    "page":        ("paper-page-136778.wav", "sfx-paper-page-136778"),
    "wind":        ("wind-roar-546871.wav", "sfx-wind-roar-546871"),
    "bell":        ("bell-low-378799.wav", "sfx-bell-low-378799"),
    "creak":       ("creak-323559.wav", "sfx-creak-323559"),
    "latch":       ("click-latch-278204.wav", "sfx-click-latch-278204"),
    "knock":       ("wood-knock-369710.wav", "sfx-wood-knock-369710"),
    "thud":        ("leather-thud-435534.wav", "sfx-leather-thud-435534"),
    "pen":         ("pencil-scratch-387926.wav", "sfx-pencil-scratch-387926"),
    "step":        ("step-stone-517118.wav", "sfx-step-stone-517118"),
    "boots":       ("boots-stair-616615.wav", "sfx-boots-stair-616615"),
    "ping":        ("metal-ping-217459.wav", "sfx-metal-ping-217459"),
    "lock":        ("lock-metal-146348.wav", "sfx-lock-metal-146348"),
    "watch":       ("ratchet-v2-own.wav", "sfx-ratchet-v2-own"),            # v2 (2026-10-25, C9): the recorded tick (watch-tick-478738) is centred on 15 kHz and vanishes on a phone speaker
    "watch-rec":   ("watch-tick-478738.wav", "sfx-watch-tick-478738"),
    "drawer":      ("drawer-rattle-573161.wav", "sfx-drawer-rattle-573161"),
    "hum":         ("hum-v2-own.wav", "sfx-hum-v2-own"),                    # v2: the sine hum (tone-low-hum-own) is 100 % under 200 Hz, so a phone plays nothing
    "hum-sine":    ("tone-low-hum-own.wav", "sfx-tone-low-hum-own"),
    # made by us (licence OWN), written by `synth`
    "horn":        ("horn-ship-v2-own.wav", "sfx-horn-ship-v2-own"),        # v2: v1 kept 91 % of its energy under 200 Hz, so on a phone the 0:08 moment lost 10 dB
    "horn-v1":     ("horn-ship-own.wav", "sfx-horn-ship-own"),
    "pop":         ("pop-own.wav", "sfx-pop-own"),
    "pop-high":    ("pop-high-own.wav", "sfx-pop-high-own"),
    "ink":         ("ink-splash-v2-own.wav", "sfx-ink-splash-v2-own"),      # v2: v1 was 86 % under 200 Hz (a thump, not a splash)
    "ink-v1":      ("ink-splash-own.wav", "sfx-ink-splash-own"),
    "cloth":       ("cloth-rustle-own.wav", "sfx-cloth-rustle-own"),
    "keys":        ("keys-jingle-own.wav", "sfx-keys-jingle-own"),
    "impact":      ("impact-v1-own.wav", "sfx-impact-v1-own"),              # C10 (2026-10-25): the dramatic hit into a character's introduction: a short riser, a crack, a boom with body above 200 Hz
}
OWN = {k: v for k, v in LIB.items() if v[1].endswith("-own") and k not in ("hum-sine",)}

# ------------------------------------------------------------------ cut types: ONE name picks the visual (ffmpeg xfade) and the sound, so the two cannot drift apart
#   cut -> (vfx name, xfade transition, sound id, level dB peak, start offset from the join start in seconds, why)
CUTS = {
    "wind":    ("smear",     "hblur",       "wind",     -16.0, -0.05, "the wind carries the picture across (hblur smear)"),
    "whoosh":  ("smear",     "hblur",       "whoosh",   -15.0, -0.04, "a fast slide: whoosh and a horizontal smear"),
    "page":    ("page_turn", "revealright",  "page",     -17.0, -0.05, "a page turn: the next picture is revealed from under the last, with the sound of paper"),
    "ink":     ("ink_wipe",  "wiperight",   "ink",      -16.0, -0.04, "an ink wipe: a wet splash and a hard-edged wipe"),
    "ink-fade":("ink_fade",  "fadeblack",   "ink",      -19.0, -0.02, "ink dropped in water: the picture goes to black through a quiet splash"),
    "door":    ("iris",      "circleopen",  "creak",    -17.0, -0.15, "a door opens on the next place: an iris opens with a creak"),
    "close":   ("iris_close","circleclose", "latch",    -15.0, -0.05, "a door closes on the last place: an iris closes with a latch click"),
    "horn":    ("iris",      "circleopen",  "horn",     -5.0,  -0.20, "the steamship horn: an iris opens onto the written object (0:08)"),
    "bell":    ("flash",     "fadewhite",   "bell",     -14.0, -0.05, "a bell stroke and a flash of light"),
    "flash":   ("flash",     "fadewhite",   "pop",      -13.0, -0.03, "a pop and a flash: the turn lands"),
    "steps":   ("smear",     "hlwind",      "boots",    -17.0, -0.10, "footsteps carry the cut: boots and a wind smear"),
    "freeze":  ("flash",     "fadewhite",   "impact",   -9.0,  -0.16, "C10: the dramatic cut into a character's introduction: a riser, then a hit as the picture flashes and the frame freezes (the riser starts 0.28 s before the hit)"),
}

DEFAULT_CUT = {"push_in": "whoosh", "insert": "page", "insert_depth": "page", "reaction_closeup": "flash", "hold_breathe": "ink-fade", "parallax_pan": "wind", "two_shot": "door",
               "recap": "wind", "day": "page", "choice": "ink", "follow": "whoosh", "intro": "freeze"}


def default_cut(it: dict) -> str:
    """The cut type of the join INTO this timeline item when the plan declares none (a plan's `transitions` always wins): by the item's template, or its card kind."""
    if it.get("kind") == "intro":     # the join INTO a character introduction is always the dramatic cut
        return "freeze"
    return DEFAULT_CUT.get(it.get("template") or it.get("id"), "whoosh")


# ------------------------------------------------------------------ foley: words in a shot spec's emotion_track.sfx / actions / props -> sound
#   (regex on the spec text, sound id, level dB peak, note). First match per cue wins. "room tone" is the bed, not foley, and is skipped on purpose.
SPEC_WORDS = [
    (r"room tone", None, 0, "the bed carries the room"),
    (r"pen scratch|pencil|writes|writing|pen on card", "pen", -20.0, "pen stroke on card"),
    (r"bell", "bell", -17.0, "the bell"),
    (r"crown wind|ratchet|watch", "watch", -22.0, "watch crown and ticks"),
    (r"his low voice|voice", None, 0, "a voice, not foley"),
    (r"key", "keys", -19.0, "keys"),
    (r"paper|card|tag", "page", -22.0, "paper"),
    (r"bag", "thud", -15.0, "the bag"),
    (r"step|walk|stair", "boots", -19.0, "footsteps"),
    (r"cloth|coat|sleeve", "cloth", -23.0, "cloth"),
    (r"lamp", "latch", -23.0, "the lamp"),
]
# a prop in a shot spec's `props` that must have a sound when the plan's `foley` for that scene names it (kept so a new prop cannot go silent unnoticed)
PROP_SOUND = {"pen": "pen", "iron-key": "keys", "intake-card": "page", "bag": "thud", "lapel-watches": "watch", "hat": "cloth"}


# ------------------------------------------------------------------ synth (numpy, deterministic): the sounds we make ourselves
def _write(path: Path, x, sr=SR):
    import numpy as np
    x = np.asarray(x, dtype="float64")
    peak = float(np.abs(x).max()) or 1.0
    x = x / peak * 0.89                                # normalise to -1 dBFS: the cue gain sets the real level
    st = np.stack([x, x], axis=1)
    pcm = (np.clip(st, -1, 1) * 32767).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(sr); w.writeframes(pcm.tobytes())
    tmp.replace(path)


def _lowpass(x, fc, sr=SR):
    import numpy as np
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / sr)
    X *= 1.0 / (1.0 + (f / fc) ** 4)
    return np.fft.irfft(X, len(x))


def _env(n, a, r, sr=SR, sustain=1.0):
    import numpy as np
    t = np.arange(n) / sr
    e = np.minimum(1.0, t / max(a, 1e-4)) * np.minimum(1.0, np.maximum(0.0, (n / sr - t) / max(r, 1e-4)))
    return e * sustain


def synth_horn():
    """A steamship horn: two low blown notes a fifth apart (about 98 Hz and 147 Hz), rich in odd harmonics, a breath of air on the attack, a long fall."""
    import numpy as np
    rng = np.random.default_rng(2510)
    n = int(2.6 * SR)
    t = np.arange(n) / SR
    x = np.zeros(n)
    for f0, a in ((98.0, 1.0), (147.5, 0.7), (49.0, 0.5)):
        for h in range(1, 12):
            x += a * np.sin(2 * np.pi * f0 * h * t * (1 + 0.0009 * np.sin(2 * np.pi * 5.1 * t))) / (h ** 1.25 if h % 2 else h ** 2.0)
    x = _lowpass(x, 1400)
    breath = _lowpass(rng.standard_normal(n), 900) * np.exp(-t / 0.18) * 0.35
    e = _env(n, 0.22, 1.5)
    return (x * 0.5 + breath) * e


def synth_pop(f0=640.0, f1=210.0, dur=0.16):
    import numpy as np
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = f1 + (f0 - f1) * np.exp(-t / 0.018)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * np.exp(-t / 0.035) * np.minimum(1.0, t / 0.002)


def synth_ink():
    """An ink splash: a wet burst (low-passed noise, fast decay) and a short low plop under it."""
    import numpy as np
    rng = np.random.default_rng(2511)
    n = int(0.55 * SR)
    t = np.arange(n) / SR
    burst = _lowpass(rng.standard_normal(n), 2600) * np.exp(-t / 0.09)
    plop = np.sin(2 * np.pi * (180 - 90 * (1 - np.exp(-t / 0.05))) * t) * np.exp(-t / 0.08) * 0.9
    return (burst * 0.8 + plop) * np.minimum(1.0, t / 0.003)


def synth_cloth():
    """Cloth rustle: band-limited noise with a slow double swell (a sleeve or a coat moving)."""
    import numpy as np
    rng = np.random.default_rng(2512)
    n = int(0.7 * SR)
    t = np.arange(n) / SR
    x = _lowpass(rng.standard_normal(n), 3200)
    x = x - _lowpass(x, 300)
    swell = np.sin(np.pi * np.clip(t / 0.7, 0, 1)) ** 2 * (0.6 + 0.4 * np.sin(2 * np.pi * 7.0 * t) ** 2)
    return x * swell


def synth_keys():
    """A small bunch of keys: six inharmonic metal pings, 2.3 to 5.1 kHz, bunched in the first 0.45 s, each with its own fast ring-down."""
    import numpy as np
    rng = np.random.default_rng(2513)
    n = int(0.9 * SR)
    x = np.zeros(n)
    for k in range(7):
        t0 = int(rng.uniform(0.0, 0.42) * SR)
        f = rng.uniform(2300, 5100)
        m = n - t0
        tt = np.arange(m) / SR
        x[t0:] += np.sin(2 * np.pi * f * tt) * np.exp(-tt / rng.uniform(0.05, 0.14)) * rng.uniform(0.4, 1.0)
        x[t0:] += 0.4 * np.sin(2 * np.pi * f * 2.76 * tt) * np.exp(-tt / 0.03)
    return x


def _band(x, lo, hi, sr=SR):
    """Zero-phase FFT band-pass (hard edges softened by a 4th-order roll-off each side)."""
    import numpy as np
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / sr)
    X *= (1.0 / (1.0 + (f / hi) ** 4)) * (1.0 - 1.0 / (1.0 + (f / max(lo, 1.0)) ** 4))
    return np.fft.irfft(X, len(x))


def synth_horn_v2():
    """A steamship horn that a phone can play: two blown notes a fifth apart (131 and 196 Hz) plus the octave below, harmonics out to 3.2 kHz (a real horn is bright), a breath of air on the attack and a long fall.
    v1 (98 Hz, low-passed at 1.4 kHz) kept 91 % of its energy under 200 Hz; this one keeps most of it above."""
    import numpy as np
    rng = np.random.default_rng(2520)
    n = int(2.8 * SR)
    t = np.arange(n) / SR
    bend = 1 + 0.012 * np.exp(-t / 0.25) - 0.0 * t                      # the note settles up into pitch, as a horn does
    x = np.zeros(n)
    for f0, a in ((131.0, 1.0), (196.5, 0.8), (65.5, 0.18)):
        ph = 2 * np.pi * np.cumsum(f0 * bend * (1 + 0.0007 * np.sin(2 * np.pi * 5.3 * t))) / SR
        for h in range(1, 25):
            if f0 * h > 3200:
                break
            x += a * np.sin(h * ph) / (h ** 0.7 if h % 2 else h ** 1.1)
    x = _lowpass(x, 3400)
    breath = _band(rng.standard_normal(n), 350, 2200) * np.exp(-t / 0.22) * 0.5
    e = _env(n, 0.18, 1.6)
    return (x * 0.5 + breath) * e


def synth_ink_v2():
    """An ink splash with a body a phone can play: a wet burst (noise 700 Hz to 5 kHz, fast decay), three droplet plinks at 600 to 1.4 kHz and a short low plop at 230 Hz under them."""
    import numpy as np
    rng = np.random.default_rng(2521)
    n = int(0.6 * SR)
    t = np.arange(n) / SR
    burst = _band(rng.standard_normal(n), 700, 5200) * np.exp(-t / 0.075)
    plop = np.sin(2 * np.pi * (230 - 80 * (1 - np.exp(-t / 0.05))) * t) * np.exp(-t / 0.07) * 0.7
    drops = np.zeros(n)
    for t0, f, a in ((0.07, 1250.0, 0.5), (0.15, 880.0, 0.4), (0.26, 640.0, 0.3)):
        m = n - int(t0 * SR)
        tt = np.arange(m) / SR
        drops[int(t0 * SR):] += a * np.sin(2 * np.pi * f * (1 - 0.25 * (1 - np.exp(-tt / 0.02))) * tt) * np.exp(-tt / 0.03)
    return (burst * 0.9 + plop + drops) * np.minimum(1.0, t / 0.002)


def synth_ratchet_v2():
    """A watch crown being wound: twelve ratchet ticks, 1.6 to 4 kHz (a phone plays that; the recorded tick sat at 15 kHz), speeding up and settling into a steady tick."""
    import numpy as np
    rng = np.random.default_rng(2522)
    n = int(3.0 * SR)
    x = np.zeros(n)
    times = [0.05, 0.30, 0.52, 0.70, 0.85, 0.98, 1.10, 1.22, 1.34, 1.46, 1.58, 1.70]
    for k, t0 in enumerate(times):
        m = int(0.03 * SR)
        tt = np.arange(m) / SR
        click = _band(rng.standard_normal(m), 1600, 4200) * np.exp(-tt / 0.004)
        ring = np.sin(2 * np.pi * (2400 + 90 * k) * tt) * np.exp(-tt / 0.006) * 0.6
        i = int(t0 * SR)
        x[i:i + m] += (click + ring) * (0.75 + 0.25 * rng.random())
    return x


def synth_hum_v2():
    """A low room hum with a voice: a 110 Hz buzz whose harmonics reach 1.2 kHz, swelling slowly. The sine hum was 100 % under 200 Hz, inaudible on a phone."""
    import numpy as np
    n = int(3.0 * SR)
    t = np.arange(n) / SR
    x = np.zeros(n)
    for h in range(1, 12):
        x += np.sin(2 * np.pi * 110.0 * h * t + h) / (h ** 1.1)
    x = _lowpass(x, 1300)
    return x * (0.7 + 0.3 * np.sin(2 * np.pi * 0.4 * t)) * _env(n, 0.3, 0.6)


def synth_impact():
    """The hit into a character's introduction (C10), built for a phone speaker: a 0.28 s riser of band-passed air (300 Hz to 3 kHz, swelling), then at 0.28 s a crack (noise 700 Hz to 5 kHz, 45 ms),
    a boom (a sine falling 190 -> 70 Hz with its 2nd and 3rd harmonics, so a small speaker still plays it) and a short dark tail. About 1.7 s; the hit is at SR * 0.28."""
    import numpy as np
    rng = np.random.default_rng(1025)
    n = int(1.7 * SR)
    t = np.arange(n) / SR
    x = np.zeros(n)
    k = int(0.28 * SR)
    rise = _band(rng.standard_normal(k), 300, 3000) * (np.linspace(0, 1, k) ** 2.2)
    x[:k] += rise * 0.55
    tt = np.arange(n - k) / SR
    f = 70 + 120 * np.exp(-tt / 0.09)
    ph = 2 * np.pi * np.cumsum(f) / SR
    boom = (np.sin(ph) + 0.55 * np.sin(2 * ph) + 0.35 * np.sin(3 * ph)) * np.exp(-tt / 0.32)
    crack = _band(rng.standard_normal(n - k), 700, 5000) * np.exp(-tt / 0.045)
    tail = _band(rng.standard_normal(n - k), 160, 900) * np.exp(-tt / 0.5) * 0.22
    x[k:] += boom * 0.8 + crack * 0.7 + tail
    return _lowpass(x, 6500) * _env(n, 0.002, 0.25)


def synth_all(force=False) -> list[str]:
    made = []
    jobs = {"horn": synth_horn_v2, "ink": synth_ink_v2, "watch": synth_ratchet_v2, "hum": synth_hum_v2, "pop": synth_pop, "pop-high": lambda: synth_pop(980.0, 380.0, 0.13), "cloth": synth_cloth, "keys": synth_keys, "impact": synth_impact}
    for k, fn in jobs.items():
        p = SFX_DIR / LIB[k][0]
        if force or not p.is_file():
            _write(p, fn())
            made.append(str(p.relative_to(ROOT)).replace("\\", "/"))
    return made


# ------------------------------------------------------------------ licences
def parse_licences(path: Path = LICENCES) -> dict:
    reg = {}
    if not Path(path).is_file():        # no register yet: every cue is reported as unlicensed instead of the tool crashing
        return reg
    for ln in path.read_text(encoding="utf-8").splitlines():
        c = [x.strip() for x in ln.strip().strip("|").split("|")]
        if len(c) >= 8 and c[0].startswith(("sfx-", "music-")):
            reg[c[0]] = {"file": c[1], "kind": c[2], "licence": c[3], "sha": c[7]}
    return reg


def sha16(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def licence_problems(file_rel: str, lid: str, reg: dict) -> str | None:
    r = reg.get(lid)
    p = ROOT / file_rel
    if not r:
        return f"{lid} has no row in LICENCES.md"
    if r["licence"] not in ("CC0", "PD", "CC-BY", "CC-BY-SA", "OWN"):
        return f"{lid} licence {r['licence']} is not allowed"
    if not p.is_file():
        return f"{file_rel} does not exist"
    if not sha16(p).startswith(r["sha"][:16]):
        return f"{file_rel} sha256 differs from the register row {lid}"
    return None


def peak_db(p: Path) -> float:
    """Peak level of a wav in dBFS (numpy on the PCM, 16-bit)."""
    import numpy as np
    with wave.open(str(p), "rb") as w:
        a = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    m = float(np.abs(a).max()) / 32768.0 if len(a) else 1e-6
    return 20 * np.log10(max(m, 1e-6))


def cue(t, sid, level_db, shot, kind, why, reg, pk_cache):
    f, lid = LIB[sid]
    rel = f"assets/audio/sfx/{f}"
    p = ROOT / rel
    if rel not in pk_cache:
        pk_cache[rel] = peak_db(p) if p.is_file() else -1.0
    gain = round(level_db - pk_cache[rel], 2)      # the cue names the PEAK it should reach; the gain is derived from the file's own peak
    return {"t": round(float(t), 3), "sound": sid, "file": rel, "licence_id": lid, "level_db": level_db, "gain_db": gain, "shot": shot, "kind": kind, "why": why}


# ------------------------------------------------------------------ build the cue list
STACK_S = 0.4


def dedupe_stacked(cues: list[dict], window: float = STACK_S) -> tuple[list[dict], list[dict]]:
    """A foley cue that is the SAME sound as a transition cue within `window` seconds is the same event heard twice (E01C 64.1 s: a bell as the cut AND a bell as the spec's foley, 50 ms apart,
    which doubled the power, +3 to +6 dB). The transition (the join's own sound) stays; the foley is dropped and recorded."""
    trans = [c for c in cues if c["kind"] == "transition"]
    keep, dropped = [], []
    for c in cues:
        if c["kind"] == "foley" and any(t["sound"] == c["sound"] and abs(t["t"] - c["t"]) <= window for t in trans):
            dropped.append({"t": c["t"], "sound": c["sound"], "why": "same sound as the transition cue within %.1f s" % window})
        else:
            keep.append(c)
    return keep, dropped


def spec_of(ep_id: str, sid: str) -> dict | None:
    p = ROOT / "work" / "shots" / f"{ep_id}-{sid}" / "shot-spec.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def spec_foley(spec: dict) -> list[dict]:
    """Cues read from a shot spec: each emotion_track.sfx entry (at_s on the shot clock) through SPEC_WORDS."""
    out = []
    for b in spec.get("beats", []):
        for c in (b.get("emotion_track") or {}).get("sfx", []):
            what = str(c.get("what", ""))
            for rx, sid, lvl, note in SPEC_WORDS:
                if re.search(rx, what, re.I):
                    if sid:
                        out.append({"at": float(c.get("at_s", 0)), "sound": sid, "level_db": lvl, "why": f"spec sfx '{what}': {note}"})
                    break
    return out


def build(ep_id: str, plan: dict, tl: dict) -> dict:
    reg = parse_licences()
    pk: dict = {}
    cues: list[dict] = []
    items = tl["items"]
    declared = {(t["from"], t["to"]): t for t in plan.get("transitions", [])}
    joins = []
    for a, b in zip(items, items[1:]):
        t = declared.get((a["id"], b["id"]))
        ct = (t or {}).get("cut")
        j = {"from": a["id"], "to": b["id"], "cut": ct}
        if ct in CUTS:
            vfx, xf, sid, lvl, off, why = CUTS[ct]
            j.update({"vfx": vfx, "xfade": xf, "sound": sid})
            start = b["t0"]                                    # the join starts where the next item starts (calm_compose: t0 = t - JOIN_S)
            cues.append(cue(max(0.0, start + off), sid, lvl, b["id"], "transition", f"{a['id']} -> {b['id']}: {why}", reg, pk))
        joins.append(j)
    by_scene = {s["id"]: s for s in plan["scenes"]}
    unmapped, no_foley = [], []
    for it in items:
        if it["kind"] != "scene":
            continue
        spec = spec_of(ep_id, it["id"]) or {}
        sc = by_scene.get(it["id"], {})
        mute = [m.lower() for m in sc.get("foley_mute", [])]
        evs = [e for e in spec_foley(spec) if not any(m in e["why"].lower() for m in mute)]
        for e in sc.get("foley", []):                          # declared foley: {at, sound, level_db?, why?}
            sid = e["sound"]
            evs.append({"at": float(e["at"]), "sound": sid, "level_db": float(e.get("level_db", -20.0)), "why": e.get("why", f"plan foley {sid}"), **({"dur": float(e["dur"])} if e.get("dur") else {})})
        for e in evs:
            if e["at"] < it["dur"] - 0.1:
                cues.append({**cue(it["t0"] + e["at"], e["sound"], e["level_db"], it["id"], "foley", e["why"], reg, pk), **({"dur": e["dur"]} if e.get("dur") else {})})
        props = [p.get("id") for p in spec.get("props", [])] if spec else []
        has_sound_prop = any(p in PROP_SOUND for p in props) or bool(sc.get("foley"))
        if has_sound_prop and not evs:
            no_foley.append(it["id"])
        if spec and not any(e for e in evs):
            unmapped.append(it["id"])
    for it in items:                                           # C10: the graffiti is drawn by hand: a marker scratch as the name, the underline and the line are drawn
        if it.get("kind") != "intro":
            continue
        import calm_intro as CI
        for at, why in ((CI.NAME_AT_S, "the name is drawn"), (CI.TAG_AT_S, "the line is drawn")):     # two strokes of sound, not three: the underline's cue sat 0.1 s from the line's and doubled it (AUDIO-DIALOGUE-CLARITY 5.3 dB under the narrator)
            cues.append(cue(it["t0"] + at, "pen", -24.0, it["id"], "foley", f"graffiti: {why}", reg, pk))
    # the written-object moment: the horn is a transition cue (cut "horn"); the day card's own reading needs no extra cue
    # the choice sequence: a pop at every cut and one per narrated line
    for it in items:
        sp = it.get("split")
        if not sp:
            continue
        for c in sp["cuts"]:
            cues.append(cue(it["t0"] + c["t"] - 0.02, "pop-high" if c.get("clip") == "B" else "pop", -12.0, it["id"], "choice", f"cut to close-up {c.get('clip')} ({c.get('vfx')})", reg, pk))
        for l in sp["lit"]:
            cues.append(cue(it["t0"] + l["t0"] - 0.02, "pop" if l["state"] != "hook" else "pop-high", -14.0, it["id"], "choice", f"the {l['state']} lights as the narrator reads it", reg, pk))
    cues.sort(key=lambda c: (c["t"], c["sound"]))
    cues, dropped = dedupe_stacked(cues)
    return {"episode": ep_id, "cues": cues, "dropped_stacked": dropped, "joins": joins, "unmapped_shots": unmapped, "shots_without_foley": no_foley,
            "levels": "each cue names the PEAK it reaches (dBFS); the mix ducks the whole sfx bus under the narrator (sidechain ratio 4), foley peaks sit 20 dB under full scale"}


# ------------------------------------------------------------------ checks
def check(sfx: dict, plan: dict, tl: dict) -> list[str]:
    reg = parse_licences()
    f = []
    cues = sfx.get("cues", [])
    # CALM-TRANSITION-SFX
    for j in sfx.get("joins", []):
        ct = j.get("cut")
        if not ct or ct not in CUTS:
            f.append(f"CALM-TRANSITION-SFX join {j['from']} -> {j['to']} declares no known cut type ({ct!r}): every transition needs a sound and a visual (types: {', '.join(CUTS)})")
            continue
        sid = CUTS[ct][2]
        near = [c for c in cues if c["kind"] == "transition" and c["sound"] == sid and c["shot"] == j["to"]]
        if not near:
            f.append(f"CALM-TRANSITION-SFX join {j['from']} -> {j['to']} ({ct}) has no {sid} cue on the cue list")
        if not j.get("xfade"):
            f.append(f"CALM-TRANSITION-SFX join {j['from']} -> {j['to']} ({ct}) has no visual transition")
    # CALM-FOLEY
    for s in sfx.get("shots_without_foley", []):
        f.append(f"CALM-FOLEY shot {s} has a prop or a declared action with a sound but no foley cue")
    bad = {c["file"]: licence_problems(c["file"], c["licence_id"], reg) for c in cues}
    for fl, pr in bad.items():
        if pr:
            f.append(f"CALM-FOLEY {pr}")
    if sum(1 for c in cues if c["kind"] == "foley") < 8:
        f.append("CALM-FOLEY fewer than 8 foley cues in the whole episode: props and hand actions are silent")
    # CALM-INTRO-SFX (C10): the dramatic cut into an introduction has its hit, and the graffiti is drawn with a marker sound
    for it in tl["items"]:
        if it.get("kind") != "intro":
            continue
        hit = [c for c in cues if c["kind"] == "transition" and c["sound"] == "impact" and c["shot"] == it["id"]]
        pens = [c for c in cues if c["kind"] == "foley" and c["sound"] == "pen" and c["shot"] == it["id"]]
        if not hit:
            f.append(f"CALM-INTRO-SFX {it['id']} has no impact cue on the join into it (the cut 'freeze' gives the dramatic sound)")
        if len(pens) < 2:
            f.append(f"CALM-INTRO-SFX {it['id']} has {len(pens)} marker cue(s) for its graffiti (needs >= 2)")
    # CALM-CHOICE-SFX
    for it in tl["items"]:
        sp = it.get("split")
        if not sp:
            continue
        ch = [c for c in cues if c["kind"] == "choice" and c["shot"] == it["id"]]
        need = len(sp["cuts"]) + len(sp["lit"])
        if len(ch) < need:
            f.append(f"CALM-CHOICE-SFX the choice sequence has {len(ch)} pop cues for {len(sp['cuts'])} cuts and {len(sp['lit'])} narrated lines (need {need})")
    if not any(it.get("split") for it in tl["items"]):
        f.append("CALM-CHOICE-SFX the timeline has no choice_split sequence")
    return f


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("synth", "build", "check"):
        print(__doc__)
        return 2
    if argv[0] == "synth":
        print(json.dumps({"made": synth_all("--force" in argv)}, ensure_ascii=False))
        return 0
    ep = argv[1]
    work = ROOT / "work" / "episodes" / ep
    tl = json.loads((work / "timeline.json").read_text(encoding="utf-8"))
    hits = sorted((ROOT / "bible" / "series").glob(f"*/episodes/{ep}")) or [ROOT / "work" / "rehearsal" / ep]
    plan = json.loads((hits[0] / "calm-plan.json").read_text(encoding="utf-8"))
    if argv[0] == "build":
        sfx = build(ep, plan, tl)
        (work / "sfx.json").write_text(json.dumps(sfx, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps({"cues": len(sfx["cues"]), "joins": len(sfx["joins"])}))
        return 0
    sfx = json.loads((work / "sfx.json").read_text(encoding="utf-8"))
    bad = check(sfx, plan, tl)
    for b in bad:
        print("FAIL [" + b.split(" ", 1)[0] + "] " + b.split(" ", 1)[1])
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
