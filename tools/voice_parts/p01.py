# voice.py part 1 of 4: executed into the voice module namespace by voice.py (a pure move).

import argparse
import array
import hashlib
import json
import math
import os
import re
import struct
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MODEL = "chatterbox-multilingual (local, MIT; Gemini banned 2026-10-23)"
ENGINE = "chatterbox"
CHATTERBOX_DIR = REPO / "work" / "tts-engines" / "chatterbox"
# Retired Gemini voice names: kept only so existing casting files and manifests still validate. No engine uses them.
VOICES = ("Zephyr Puck Charon Kore Fenrir Leda Orus Aoede Callirrhoe Autonoe Enceladus Iapetus Umbriel Algieba Despina "
          "Erinome Algenib Rasalgethi Laomedeia Achernar Alnilam Schedar Gacrux Pulcherrima Achird Zubenelgenubi "
          "Vindemiatrix Sadachbia Sadaltager Sulafat").split()
PCM_RATE = 24000          # default wav rate for write_wav (kept for the next engine)
FPS = 24
MIN_HOLD_FRAMES = 2       # rule of face.json: a consonant shape is held 2 frames minimum
NJ_WRITER = Path(os.environ.get("NJ_WRITER_DIR", "nj-writer"))
AR_LETTER = re.compile("[ء-غف-يٱ]")
AR_MARK = re.compile("[ً-ْٰ]")


class Fail(Exception):
    def __init__(self, cid, msg):
        super().__init__(f"FAIL [{cid}] {msg}")
        self.cid = cid


# ---------------------------------------------------------------- paths and io
def sha(data):
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode("utf-8")).hexdigest()


def read_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def write_json(p, obj):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, p)


def episode_paths(ep, repo=REPO):
    ep = Path(ep)
    d = ep.parent if ep.suffix == ".json" else ep
    return {"dir": d, "script": d / "script.json", "manifest": d / "narration-manifest.json",
            "work": repo / "work" / "voice" / d.name}


def load_script(paths):
    if not paths["script"].exists():
        raise Fail("VOICE-SCRIPT", f"{paths['script']} not found")
    s = read_json(paths["script"])
    if not s.get("lines"):
        raise Fail("VOICE-SCRIPT", "script has no lines")
    return s


def casting_path(series, repo=REPO):
    return repo / "bible" / "series" / series / "voices" / "casting.json"


def load_casting(script, repo=REPO, override=None):
    p = Path(override) if override else casting_path(script.get("series", "series"), repo)
    if not p.exists():
        raise Fail("VOICE-CAST", f"{p} not found")
    return read_json(p)


def load_registry():
    p = NJ_WRITER / "voice-styles.json"
    if not p.exists():
        raise Fail("VOICE-REGISTRY", f"{p} not found (set NJ_WRITER_DIR)")
    return {s["id"]: s for s in read_json(p)["styles"]}


# ---------------------------------------------------------------- casting checks (offline)
def casting_problems(casting, reg):
    out = []
    emos = set(casting["emotions"])
    voices_used = {}
    chatterbox = casting.get("engine", ENGINE) == ENGINE
    for cid, c in casting["characters"].items():
        if chatterbox:
            # Chatterbox clones the reference clip: `voice` is only a label (a source or clip code). The Gemini voice-name list
            # applies to no engine any more (Gemini banned 2026-10-23), so it is not required here.
            if not isinstance(c.get("voice"), str) or not c["voice"].strip():
                out.append(("VOICE-CAST", f"{cid}: voice must be a non-empty label (the set or clip code of its reference)"))
            code = (c.get("reference") or {}).get("source_code")
            if code and code != c.get("voice"):
                out.append(("VOICE-CAST", f"{cid}: voice {c.get('voice')!r} differs from the reference source_code {code!r}"))
        elif c["voice"] not in VOICES:
            out.append(("VOICE-CAST", f"{cid}: voice {c['voice']!r} is not one of the 30 built-in voices"))
        if c["voice"] in voices_used:
            declared = set(casting.get("reused_voices", {}).get(c["voice"], []))     # a deliberate reuse is listed on both roles
            if not (chatterbox and {cid, voices_used[c["voice"]]} <= declared):
                out.append(("VOICE-CAST", f"{cid} and {voices_used[c['voice']]} share the voice {c['voice']}"))
        voices_used[c["voice"]] = cid
        if (c.get("reference") or {}).get("license") == CLEARED and (lp := licence_problem(c["reference"])):
            out.append(("VOICE-REF", f"{cid}: {lp}"))
        if "carried in text" not in c.get("accent", ""):
            out.append(("VOICE-CAST", f"{cid}: accent line must say where the accent lives ('carried in text')"))
        for e, ids in c["styles"].items():
            if e not in emos:
                out.append(("VOICE-STYLE", f"{cid}: emotion {e!r} is not in the casting emotion list"))
            for i in ids:
                if i not in reg:
                    out.append(("VOICE-STYLE", f"{cid}/{e}: style {i!r} is not in voice-styles.json (never invent a style)"))
                if i == "alert" and e not in ("warning", "anger"):
                    out.append(("VOICE-STYLE", f"{cid}/{e}: alert is for warning (or an angry order) only"))
                if i == "data" and e not in ("figures", "anger", "fear"):
                    out.append(("VOICE-STYLE", f"{cid}/{e}: data is for figures (or an itemised anger/fear list) only"))
    return out


# ---------------------------------------------------------------- manifest
def pick_style(c, line):
    emo = line.get("emotion")
    allowed = c["styles"].get(emo)
    return emo, allowed


def build_manifest(script, casting, reg):
    lines = []
    for ln in script["lines"]:
        sp = ln.get("speaker")
        c = casting["characters"].get(sp)
        if c is None:
            raise Fail("VOICE-CAST", f"line {ln.get('id')}: speaker {sp!r} is not cast")
        emo, allowed = pick_style(c, ln)
        if not allowed:
            raise Fail("VOICE-STYLE", f"line {ln.get('id')}: {sp} has no allowed style for emotion {emo!r}")
        style = ln.get("style") or allowed[0]
        if style not in allowed:
            raise Fail("VOICE-STYLE", f"line {ln.get('id')}: style {style!r} is not allowed for {sp}/{emo} (allowed: {', '.join(allowed)})")
        lines.append({"id": ln["id"], "speaker": sp, "voice": c["voice"], "lang": "ar", "emotion": emo, "style": style,
                      "direction": reg[style]["direction"], "text": ln["text"], "tts_text": ln.get("tts_text", ""), **({"tone": ln["tone"]} if ln.get("tone") else {})})
    return {"episode": script.get("episode"), "series": script.get("series"), "model": MODEL,
            "script_sha256": None, "lines": lines}


# ---------------------------------------------------------------- gate
def gate_checks(script, manifest, casting, reg, work, once=True):
    """Our offline checks. Returns [(id, message)]."""
    f = []
    f += casting_problems(casting, reg)
    sl, ml = script["lines"], manifest.get("lines", [])
    if [l["id"] for l in sl] != [l.get("id") for l in ml]:
        f.append(("VOICE-TEXT", "manifest line ids/order differ from the script"))
    seen = set()
    for i, m in enumerate(ml):
        n = m.get("id", i)
        if n in seen:
            f.append(("VOICE-TEXT", f"duplicate line id {n}"))
        seen.add(n)
        c = casting["characters"].get(m.get("speaker"))
        if c is None:
            f.append(("VOICE-CAST", f"line {n}: speaker {m.get('speaker')!r} is not cast"))
            continue
        if m.get("voice") != c["voice"]:
            f.append(("VOICE-CAST", f"line {n}: voice {m.get('voice')!r} differs from the casting ({c['voice']})"))
        allowed = c["styles"].get(m.get("emotion"), [])
        if m.get("style") not in allowed:
            f.append(("VOICE-STYLE", f"line {n}: style {m.get('style')!r} is not allowed for {m.get('speaker')}/{m.get('emotion')} (allowed: {', '.join(allowed) or 'none'})"))
        elif m["style"] in reg and m.get("direction") != reg[m["style"]]["direction"]:
            f.append(("VOICE-STYLE", f"line {n}: direction is not byte-equal to the registry"))
        if i < len(sl):
            for key in ("text", "tts_text"):
                if m.get(key) != sl[i].get(key, ""):
                    f.append(("VOICE-TEXT", f"line {n}: {key} differs from the script"))
            if m.get("speaker") != sl[i].get("speaker"):
                f.append(("VOICE-TEXT", f"line {n}: speaker differs from the script"))
        if not once:
            continue
        if superseded_log(work).exists() and (work / f"{n}.wav").exists() and (attempts(work).get(n) or {}).get("status") == "ok":
            continue                      # a settled take that stays; the superseded speaker's lines were moved away
        if (work / f"{n}.wav").exists() or (work / f"{n}.pcm").exists():
            f.append(("VOICE-ONCE", f"line {n}: audio already exists; a line is voiced once, never re-voiced"))
        att = attempts(work).get(n)
        if att and att.get("status") not in NOT_TAKEN and not (work / f"{n}.wav").exists():
            f.append(("VOICE-ONCE", f"line {n}: generation already started (status {att.get('status')}); no second take"))
    return f


def run_style_gate(manifest_path, full):
    gate = NJ_WRITER / "scripts" / "voice_style_gate.py"
    if not gate.exists():
        return [("VOICE-GATE", f"{gate} not found")]
    cmd = [sys.executable, str(gate), str(manifest_path)] + ([] if full else ["--text-only"])
    env = dict(os.environ, PYTHONUTF8="1")
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", env=env)
    if r.returncode == 0:
        return []
    lines = [x for x in (r.stdout + r.stderr).splitlines() if x.strip()]
    return [("VOICE-GATE", x.strip()) for x in lines[:40]] or [("VOICE-GATE", "voice_style_gate failed")]


def pace_band(casting, speaker):
    """The speaker's own wpm band for dialogue, or None (narrator roles keep the nj-writer band)."""
    pc = (casting["characters"].get(speaker) or {}).get("pace")
    return list(pc["band_wpm"]) if pc else None


def pace_findings(manifest, casting):
    """VOICE-PACE: own check for character dialogue (words of visible text / measured seconds * 60)."""
    f = []
    for m in manifest["lines"]:
        band = pace_band(casting, m.get("speaker"))
        sec = m.get("seconds")
        if band is None or not sec or sec <= 0:
            continue
        wpm = len(m.get("text", "").split()) / sec * 60
        if not band[0] <= wpm <= band[1]:
            f.append(("VOICE-PACE", f"line {m['id']}: {m['speaker']} wpm {wpm:.0f} outside the character band {band[0]}-{band[1]}"))
    return f


def drop_dialogue_wpm(findings, manifest, casting):
    """Remove the narrator-band wpm findings of voice_style_gate.py for lines that have a character band."""
    own = {str(m["id"]) for m in manifest["lines"] if pace_band(casting, m.get("speaker"))}
    out = []
    for cid, msg in findings:
        mt = re.search(r"line (\S+): wpm \d+ outside ", msg)
        if mt and mt.group(1) in own:
            continue
        out.append((cid, msg))
    if len(out) < len(findings) and not any(m.lstrip().startswith("FAIL:") for _, m in out):
        out = [x for x in out if not x[1].lstrip().startswith("RESULT:")]   # only the dropped lines had failed
    return out


def cmd_gate(paths, full=False, casting_override=None, repo=REPO):
    script = load_script(paths)
    casting = load_casting(script, repo, casting_override)
    reg = load_registry()
    if not paths["manifest"].exists():
        raise Fail("VOICE-TEXT", f"{paths['manifest']} not found; run `manifest` first")
    manifest = read_json(paths["manifest"])
    fails = gate_checks(script, manifest, casting, reg, paths["work"], once=not full)
    style = run_style_gate(paths["manifest"], full)
    if full:
        style = drop_dialogue_wpm(style, manifest, casting)
        fails += pace_findings(manifest, casting)
    fails += style
    if full:
        fails += tail_checks(paths["work"], manifest)
    receipt = paths["work"] / "gate.json"
    if fails:
        if receipt.exists():
            receipt.unlink()
        return fails
    write_json(receipt, {"passed": True, "manifest_sha256": sha(paths["manifest"].read_bytes()),
                         "script_sha256": sha(paths["script"].read_bytes()), "full": full, "lines": len(manifest["lines"])})
    return []


# ---------------------------------------------------------------- the one take
def attempts(work):
    p = work / "attempts.jsonl"
    out = {}
    if p.exists():
        for ln in p.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                r = json.loads(ln)
                out[r["id"]] = r
    return out


NOT_TAKEN = ("not-taken", "error_no_generation")   # statuses that never reached generation: the line may be voiced later


def line_state(work, n):
    """taken | not-taken | blocked-after-start | untouched. A wav (or an ok record) always means taken."""
    if (work / f"{n}.wav").exists() or (work / f"{n}.pcm").exists():
        return "taken"
    att = attempts(work).get(n)
    if not att:
        return "untouched"
    if att.get("status") == "ok":
        return "taken"
    if att.get("status") in NOT_TAKEN:
        return "not-taken"
    return "blocked-after-start"


def read_marks(path):
    """Worker marker file -> (model_loaded, set of line ids whose generation started)."""
    loaded, started = False, set()
    p = Path(path)
    if p.exists():
        for ln in p.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            if r.get("event") == "loaded":
                loaded = True
            elif r.get("event") == "generating":
                started.add(r.get("id"))
    return loaded, started


def mark(path, rec):
    """Append one marker record and force it to disk (the worker may die on the next instruction)."""
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def stderr_tail(path, lines=12, chars=1500):
    p = Path(path)
    if not p.exists():
        return ""
    txt = [x for x in p.read_text(encoding="utf-8", errors="replace").splitlines() if x.strip()]
    return "\n".join(txt[-lines:])[-chars:]


def settle_failed_run(work, ids, marks_path, error):
    """After a failed run: lines whose generation never started become not-taken (may be voiced later); lines whose
    generation started stay blocked forever. -> (not_taken ids, blocked ids)."""
    loaded, started = read_marks(marks_path)
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    nt, bl = [], []
    for n in ids:
        if (work / f"{n}.wav").exists() or attempts(work).get(n, {}).get("status") == "ok":
            continue
        if n in started:
            log_attempt(work, {"id": n, "status": "error", "engine": ENGINE, "at": now, "generation_started": True, "error": error})
            bl.append(n)
        else:
            why = "engine failed to load" if not loaded else "worker died before this line started"
            log_attempt(work, {"id": n, "status": "not-taken", "engine": ENGINE, "at": now,
                               "reason": f"not-taken ({why}: {error})"})
            nt.append(n)
    return nt, bl


def log_attempt(work, rec):
    work.mkdir(parents=True, exist_ok=True)
    with open(work / "attempts.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def write_wav(path, pcm: bytes, rate=PCM_RATE):
    tmp = Path(str(path) + ".tmp")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    os.replace(tmp, path)


# ---------------------------------------------------------------- wav reading (16-bit PCM and 32-bit float)
def _riff(path):
    """Minimal RIFF reader: the stdlib `wave` module refuses the float32 wav that torchaudio writes."""
    b = Path(path).read_bytes()
    if b[:4] != b"RIFF" or b[8:12] != b"WAVE":
        raise Fail("VOICE-AUDIO", f"{path}: not a RIFF wav")
    pos, fmt, data = 12, None, None
    while pos + 8 <= len(b):
        cid, sz = b[pos:pos + 4], struct.unpack("<I", b[pos + 4:pos + 8])[0]
        body = b[pos + 8:pos + 8 + sz]
        if cid == b"fmt ":
            fmt = struct.unpack("<HHIIHH", body[:16])
        elif cid == b"data":
            data = body
        pos += 8 + sz + (sz & 1)
    if fmt is None or data is None:
        raise Fail("VOICE-AUDIO", f"{path}: no fmt/data chunk")
    return fmt, data


def read_float(path):
    """-> (list of floats in [-1, 1] from the first channel, sample rate)."""
    fmt, data = _riff(path)
    tag, ch, rate, _, _, bits = fmt
    if tag == 3 and bits == 32:
        a = array.array("f")
    elif tag in (1, 0xFFFE) and bits == 16:
        a = array.array("h")
    else:
        raise Fail("VOICE-AUDIO", f"{path}: only 16-bit PCM and 32-bit float wav are read (tag {tag}, {bits} bit)")
    a.frombytes(data[:len(data) - len(data) % a.itemsize])
    if sys.byteorder == "big":
        a.byteswap()
    sc = 1.0 if tag == 3 else 1 / 32768
    return [x * sc for x in a[::ch]], rate


def resample(x, rate, target=PCM_RATE, taps=24):
    """Band-limited (windowed-sinc, Hann) resample of floats from `rate` to `target`, stdlib only. Used by REF-QUALITY so a
    44.1 / 48 kHz reference is measured on the same 24 kHz grid as every other (before 2026-11-07 its frames were longer than
    the 512-point FFT and `refcheck` crashed with IndexError). Returns x unchanged when the rates are equal."""
    if rate == target or not x:
        return x, rate
    g = math.gcd(rate, target)
    up, down = target // g, rate // g           # out[j] sits at input position j * down / up
    cut = min(1.0, target / rate) * 0.95        # cutoff re the input Nyquist (anti-alias when going down)
    coef = {}
    n_out = (len(x) * up) // down
    out = []
    half = taps if cut >= 1.0 else int(math.ceil(taps / cut))
    for j in range(n_out):
        pos_num = j * down
        i0, ph = divmod(pos_num, up)
        c = coef.get(ph)
        if c is None:
            frac = ph / up
            c = []
            for k in range(-half + 1, half + 1):
                t = k - frac
                s = 1.0 if t == 0 else math.sin(math.pi * cut * t) / (math.pi * cut * t)
                c.append(cut * s * (0.5 + 0.5 * math.cos(math.pi * t / half)))
            coef[ph] = c
        a = i0 - half + 1
        seg = x[max(0, a):i0 + half + 1]
        cc = c[max(0, -a):max(0, -a) + len(seg)]
        out.append(sum(map(float.__mul__, seg, cc)))
    return out, target


def write_wav16(path, samples, rate):
    """Write floats in [-1, 1] as 16-bit mono wav, atomically."""
    pcm = array.array("h", (max(-32768, min(32767, int(round(x * 32767)))) for x in samples))
    if sys.byteorder == "big":
        pcm.byteswap()
    write_wav(path, pcm.tobytes(), rate)


# ---------------------------------------------------------------- end-trim (offline, no model)
TRIM_HOP = 0.010          # s between frames
TRIM_WIN = 0.020          # s per frame
SPEECH_BELOW_PEAK_DB = 30  # a frame is speech only if within this many dB of the loud part (p95 of frame levels)
HISS_FLATNESS = 0.12      # band flatness (100 Hz-8 kHz) at or above this is hiss, not voice ...
HISS_BELOW_PEAK_DB = 24   # ... when the frame is also this far under the loud part (real fricatives are louder)
GAP_S = 0.40              # silence this long (or longer) separates a "run"; shorter gaps are pauses inside the line
STRAY_BELOW_PEAK_DB = 12  # a run after such a gap whose p90 level is this far under the peak is stray, not speech
PRE_ROLL_S = 0.030        # kept before the first speech frame (soft onsets)
HANGOVER_S = 0.100        # kept after the last speech frame (final consonants and their decay)
FADE_IN_S = 0.010
FADE_OUT_S = 0.045        # 30-60 ms
LEAD_PAD_S = 0.080        # clean digital silence put before the speech
TAIL_PAD_S = 0.150        # clean digital silence put after the fade-out
TAIL_CHECK_S = 0.100      # VOICE-TAIL: the last N ms ...
TAIL_FLOOR_DB = -60.0     # ... must sit under this level (dBFS, rms)
CLIP_EDGE_DB = -24.0      # VOICE-TAIL: level of the last 10 ms before the cut, relative to the peak; louder = a clipped word (same line as the hiss limit)


def _fft(a):
    """In-place iterative radix-2 FFT of a list of complex numbers (length a power of two)."""
    n = len(a)
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j ^= bit
        if i < j:
            a[i], a[j] = a[j], a[i]
    ln = 2
    while ln <= n:
        w = _TW[ln]
        for i in range(0, n, ln):
            h = ln // 2
            for k in range(h):
                u, v = a[i + k], a[i + k + h] * w[k]
                a[i + k], a[i + k + h] = u + v, u - v
        ln <<= 1


_TW = {}
for _ln in (2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048):
    _TW[_ln] = [complex(math.cos(-2 * math.pi * k / _ln), math.sin(-2 * math.pi * k / _ln)) for k in range(_ln // 2)]


def band_flatness(frame, rate, lo=100.0, hi=8000.0):
    """Spectral flatness (geometric / arithmetic mean of the power spectrum) between lo and hi Hz: ~0 tonal, ~1 noise."""
    n = 1
    while n < len(frame):
        n <<= 1
    n = max(n, 64)
    m = len(frame)
    buf = [complex(x * (0.5 - 0.5 * math.cos(2 * math.pi * i / max(1, m - 1))), 0) for i, x in enumerate(frame)]
    buf += [0j] * (n - m)
    _fft(buf)
    k0, k1 = max(1, int(lo * n / rate)), min(n // 2, int(hi * n / rate))
    p = [abs(buf[k]) ** 2 + 1e-20 for k in range(k0, k1)]
    if not p:
        return 1.0
    return math.exp(sum(math.log(v) for v in p) / len(p)) / (sum(p) / len(p))


def _db(rms):
    return 20 * math.log10(rms) if rms > 1e-6 else -120.0


def frame_levels(x, rate):
    hop, win = max(1, int(rate * TRIM_HOP)), max(2, int(rate * TRIM_WIN))
    n = max(1, (len(x) - win) // hop + 1) if len(x) >= win else 1
    out = []
    for i in range(n):
        seg = x[i * hop:i * hop + win]
        out.append(_db(math.sqrt(sum(v * v for v in seg) / max(1, len(seg)))))
    return out, hop, win


def trim_bounds(x, rate):
    """Find the true start and end of speech. -> dict(start, end (sample indices), peak_db, edge_db_rel, clipped_end,
    dropped_runs). Raises Fail if the audio is silent. Uses frame energy and spectral flatness only."""
    db, hop, win = frame_levels(x, rate)
    ordered = sorted(db)
    peak = ordered[min(len(ordered) - 1, int(len(ordered) * .95))]
    if peak < -50:
        raise Fail("VOICE-AUDIO", "audio is silent")
    flat_cache = {}

    def is_hiss(i):
        if db[i] >= peak - HISS_BELOW_PEAK_DB:
            return False
        if i not in flat_cache:
            flat_cache[i] = band_flatness(x[i * hop:i * hop + win], rate)
        return flat_cache[i] >= HISS_FLATNESS

    voiced = [d >= peak - SPEECH_BELOW_PEAK_DB and not is_hiss(i) for i, d in enumerate(db)]
    gap_f = max(1, int(round(GAP_S / TRIM_HOP)))
    runs, cur, last = [], None, None
    for i, v in enumerate(voiced):
        if not v:
            continue
        if cur is not None and i - last <= gap_f:
            cur[1] = i
        else:
            cur = [i, i]
            runs.append(cur)
        last = i
    if not runs:
        raise Fail("VOICE-AUDIO", "no speech found")
    kept, dropped = [], 0
    for a, b in runs:
        lv = sorted(db[i] for i in range(a, b + 1) if voiced[i])
        p90 = lv[min(len(lv) - 1, int(len(lv) * .9))]
        if p90 >= peak - STRAY_BELOW_PEAK_DB:
            kept.append((a, b))
        else:
            dropped += 1
    if not kept:
        raise Fail("VOICE-AUDIO", "no speech above the stray-run level")
    first, lastf = kept[0][0], kept[-1][1]
    start = max(0, first * hop - int(PRE_ROLL_S * rate))
    end_f = lastf
    for _ in range(int(HANGOVER_S / TRIM_HOP)):
        if end_f + 1 >= len(db) or is_hiss(end_f + 1):
            break
        end_f += 1
    end = min(len(x), end_f * hop + win)
    edge = x[max(start, end - hop):end]
    edge_db = _db(math.sqrt(sum(v * v for v in edge) / max(1, len(edge)))) - peak
    return {"start": start, "end": end, "peak_db": round(peak, 1), "edge_db_rel": round(edge_db, 1),
            "clipped_end": edge_db > CLIP_EDGE_DB, "dropped_runs": dropped}


def trim_take(x, rate, done_after_s=None, edge_overrides=None):
    """Cut the noise-only edges before and after the words, fade inside the guards, add clean silence. Post-processing
    of the one take (2026-10-26: the word-safe edge cleaner, tools/voice_edges.py, numbers `take.edge.*` in
    tools/sound_profile.json; the speech span itself is never scaled or cut). `done_after_s` (from the text, see
    edge_done_after_s) lets the cleaner drop a voiced run the model made after the line was spoken.
    -> (new floats, info). info has cut_start_ms and cut_end_ms (what was removed from the raw take)."""
    import numpy as np
    import voice_edges as VE                         # numpy: imported here, so the Chatterbox worker never needs it
    E = {**VE.params(), **(edge_overrides or {})}      # a breath-joined take widens run_gap_s so its own pauses are not read as a gap before a stray run
    xa = np.asarray(x, dtype="float64")
    try:
        body, rec = VE.clean(xa, rate, E, done_after_s)
    except ValueError as e:
        raise Fail("VOICE-AUDIO", str(e))
    start, end = rec["start"], rec["end"]
    peak = rec["span"]["p95_db"]
    hop = max(1, int(rate * TRIM_HOP))
    guard_end = int(round((rec["span"]["offset_s"] + E["tail_guard_s"]) * rate))
    # VOICE-TAIL's clipped-word test reads the level at the cut. The cleaner cuts only after the offset plus the whole guard,
    # so the word can be clipped only where the take ENDS inside the guard (the model stopped mid-word): there the raw level at
    # the file end is measured; elsewhere what is delivered at the cut (after the fade-out) is.
    edge = xa[max(start, end - hop):end] if end < guard_end else body[-hop:]
    edge_db = _db(float(np.sqrt(np.mean(edge ** 2))) if len(edge) else 0.0) - peak
    lead, tail = int(round(E["lead_pad_s"] * rate)), int(round(E["tail_pad_s"] * rate))
    y = [0.0] * lead + [float(v) for v in body] + [0.0] * tail
    info = {"start": start, "end": end, "peak_db": peak, "edge_db_rel": round(edge_db, 1), "clipped_end": edge_db > CLIP_EDGE_DB,
            "dropped_runs": rec["span"]["dropped_runs"] + rec["span"]["runon_runs"],
            "rate": rate, "raw_ms": round(len(x) * 1000 / rate), "trimmed_ms": round(len(y) * 1000 / rate),
            "cut_start_ms": rec["cut_lead_ms"], "cut_end_ms": rec["cut_tail_ms"],
            "fade_in_ms": rec["fade_in_ms"], "fade_out_ms": rec["fade_out_ms"], "lead_pad_ms": round(lead * 1000 / rate),
            "tail_pad_ms": round(tail * 1000 / rate),
            "edge": {k: rec["span"][k] for k in ("onset_s", "offset_s", "span_s", "lead_window_s", "tail_window_s",
                                                 "f0_median_hz", "dropped_runs", "runon_runs")} | {"method": rec["method"],
                     "done_after_s": None if done_after_s is None else round(done_after_s, 2)}}
    return y, info


MASTER_TAKES = os.environ.get("STORYWRAP_VOICE_MASTER", "1") != "0"   # the one switch: the mastering chain is the default for every new take


def master_sidecar(dst):
    return Path(str(dst)[:-4] + ".master.json") if str(dst).endswith(".wav") else Path(str(dst) + ".master.json")


def cmd_trim(src, dst, master=None, role="dialogue", done_after_s=None, edge_overrides=None):
    """Edge-clean one take, then (default) the mastering chain; writes dst (16-bit) and, when mastered, dst's .master.json report.
    -> the trim record, with `master` (role, before/after metrics, stages, contract) when the chain ran."""
    x, rate = read_float(src)
    y, info = trim_take(x, rate, done_after_s, edge_overrides)
    if MASTER_TAKES if master is None else master:
        import voice_master as VM                    # numpy/scipy: imported only here, so the Chatterbox worker never needs them
        ya, rep = VM.master_take(y, rate, role)
        rep["contract"] = VM.contract_problems(y, ya, rep)
        y = [float(v) for v in ya]
        info["master"] = {"role": role, "profile_version": rep["profile_version"], "after": rep["after"], "before": rep["before"],
                          "contract": rep["contract"], "stages": rep["stages"]}
        write_json(master_sidecar(dst), rep)
    write_wav16(dst, y, rate)
    return info
