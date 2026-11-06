# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "scipy"]
# ///
"""Voice stage: manifest -> gate -> voice (ONE take per line) -> visemes.

    uv run tools/voice.py casting [--series series]
    uv run tools/voice.py manifest <episode-dir>
    uv run tools/voice.py measure <episode-dir> [--work <take-dir>]   # fill seconds/raw_seconds from existing takes
    uv run tools/voice.py gate     <episode-dir> [--full]
    uv run tools/voice.py voice    <episode-dir> [--go]      (Chatterbox Multilingual, local GPU; dry run without --go)
    uv run tools/voice.py status   <episode-or-work-dir>     (per line: taken / not-taken / blocked-after-start)
    uv run tools/voice.py repair   <work-dir> --reason "<error>"   (old logs: started-only lines -> not-taken)
    uv run tools/voice.py trim     <in.wav> <out.wav> [--role narrator|dialogue] [--no-master]   (offline end-trim + the mastering chain; no model)
    uv run tools/voice.py refcheck <ref.wav> [provenance.json]   (REF-QUALITY of a reference clip; `casting` and `voice` enforce it)
    uv run tools/voice.py supersede <episode-dir> --speaker <id> --reason "<why>"   (a BANNED voice's takes move aside; the new voice then voices those lines once)
    uv run tools/voice.py refit-mark <episode-dir> --old H01 --new H01r1 --reason "<why>"   (a line too long for its slot was reworded under a NEW id, tools/line_refit.py, R-502: only the new id is voiced, once)
    uv run tools/voice.py visemes  <episode-dir>

Engine = Chatterbox Multilingual (owner, 2026-10-24): local, GPU, MIT, one take per line, no ASR, no other model.
Google Gemini is BANNED (owner, 2026-10-23, permanent): any other engine is refused (VOICE-BANNED); no code here calls a network.
Every take is end-trimmed offline (energy + spectral flatness, no model) and checked by VOICE-TAIL, then goes through the ONE mastering
chain (tools/voice_master.py, numbers in tools/sound_profile.json; the owner 2026-10-26) and is checked by VOICE-MASTER. The raw take stays
as <id>.wav; the finished take is <id>.trimmed.wav with its report in <id>.trimmed.master.json. STORYWRAP_VOICE_MASTER=0 turns the chain off (tests).
Casting voice names are retired Gemini names (status "retired"); the engine voice is the reference clip per character.
Exit 0 = ok, 1 = a check failed (`FAIL [ID] message`), 2 = usage or tool error. Pipeline text: pipelines/VOICE.md.
"""
from __future__ import annotations

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
    for cid, c in casting["characters"].items():
        if c["voice"] not in VOICES:
            out.append(("VOICE-CAST", f"{cid}: voice {c['voice']!r} is not one of the 30 built-in voices"))
        if c["voice"] in voices_used:
            out.append(("VOICE-CAST", f"{cid} and {voices_used[c['voice']]} share the voice {c['voice']}"))
        voices_used[c["voice"]] = cid
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


def trim_take(x, rate, done_after_s=None):
    """Cut the noise-only edges before and after the words, fade inside the guards, add clean silence. Post-processing
    of the one take (2026-10-26: the word-safe edge cleaner, tools/voice_edges.py, numbers `take.edge.*` in
    tools/sound_profile.json; the speech span itself is never scaled or cut). `done_after_s` (from the text, see
    edge_done_after_s) lets the cleaner drop a voiced run the model made after the line was spoken.
    -> (new floats, info). info has cut_start_ms and cut_end_ms (what was removed from the raw take)."""
    import numpy as np
    import voice_edges as VE                         # numpy: imported here, so the Chatterbox worker never needs it
    E = VE.params()
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


def cmd_trim(src, dst, master=None, role="dialogue", done_after_s=None):
    """Edge-clean one take, then (default) the mastering chain; writes dst (16-bit) and, when mastered, dst's .master.json report.
    -> the trim record, with `master` (role, before/after metrics, stages, contract) when the chain ran."""
    x, rate = read_float(src)
    y, info = trim_take(x, rate, done_after_s)
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


def edge_noise_problems(samples, rate):
    """VOICE-EDGE-NOISE (2026-10-26): no noise-only window before the first word or after the last one, beyond the guards
    (tools/voice_edges.py, limits `checks.edge_noise`). Same detector as the cleaner, so a take it cleaned passes and a take
    with a noise-only lead-in or tail (the old trim's j03 L01: 3.97 s) fails."""
    import numpy as np
    import voice_edges as VE
    return VE.edge_problems(np.asarray(samples, dtype="float64"), rate)


def tail_problems(samples, rate, info=None):
    """VOICE-TAIL on a trimmed take: nothing above the noise floor in the last TAIL_CHECK_S, and no clipped word ending
    (`info` is the trim record: the level at the cut must be below CLIP_EDGE_DB under the peak)."""
    out = []
    n = max(1, int(TAIL_CHECK_S * rate))
    tail = samples[-n:]
    lvl = _db(math.sqrt(sum(v * v for v in tail) / len(tail)))
    if lvl > TAIL_FLOOR_DB:
        out.append(("VOICE-TAIL", f"energy {lvl:.1f} dBFS in the last {round(TAIL_CHECK_S * 1000)} ms (limit {TAIL_FLOOR_DB:.0f})"))
    if info is None:
        out.append(("VOICE-TAIL", "no trim record, cannot show the word ending is whole"))
    elif info.get("edge_db_rel", 0) > CLIP_EDGE_DB:
        out.append(("VOICE-TAIL", f"word ending clipped: {info['edge_db_rel']:.1f} dB under the peak at the cut (limit {CLIP_EDGE_DB:.0f})"))
    return out


# ---------------------------------------------------------------- REF-QUALITY: is a reference clip clean enough to clone?
# Chatterbox copies the reference's level, compression, noise and bandwidth into every take. the owner approved the voices
# cloned from four clips (rival, lead, partner, guide) and rejected three (hero, extra, han: "a lot of noise, not
# clear", 2026-10-24). The limits below are set from the measured profile of the four approved clips with a margin;
# the profile of the three rejected clips shows which limit each one breaks (research/tts-alternatives.md,
# "Why three voices were bad"). No model: frame levels and one FFT per speech frame.
REFQ = {
    "calibrated_on": "the owner's 2026-10-24 verdict: rival, lead, partner, guide perfect; hero, extra, han bad",
    "min_up_votes": 2, "max_down_votes": 0,    # a clip nobody validated can be a mis-read or a noisy take (han: 0 votes)
    "max_clip_samples": 0,                     # approved clips: 0 samples at full scale; han: 6 (its take: 295)
    "max_floor_dbfs": -53.0,                   # p10 frame level; approved -55.6 to -62.8; hero -48.8, extra -51.7
    "min_snr_db": 35.0,                        # p90 speech level minus the floor; approved 36.6 to 42.4
    "min_crest_db": 18.0,                      # peak minus median speech level; approved 20.1 to 22.7; low = hot or squashed (extra 14.1, han 9.7)
    "min_top_db": -58.0,                       # energy above 8 kHz vs 100-1000 Hz (approved -29.6 to -50.3): very low = muffled (hero -63.0, extra -74.5)
    "max_decay20_s": 0.15,                     # median time for a 20 dB fall after a word; approved 0.05 to 0.12 (hero 0.14): high = reverberant
    # --- added 2026-10-25 (the owner banned the narrator reference common_voice_ar_21519152, "noise or similar issues: not good data").
    # The old limits could not see it: its pauses are digital silence (a noise gate or denoiser ran on the clip), which reads as
    # the best floor and SNR ever measured while the speech is boxy and low-passed. See research/narrator-ban-2026-10-25.md.
    "max_zero_frac": 0.02,                     # share of samples that are exactly 0; approved 0.0017 to 0.0073, banned narrator 0.0638 (8x): a gate/denoiser fingerprint
    "min_floor_dbfs": -75.0,                   # a floor below this is digital silence, not a microphone; approved -55.6 to -62.8, banned narrator -88.4
    "min_centroid_hz": 400.0,                  # power-weighted mean frequency of speech frames; approved 475 to 1043, banned narrator 334: boxy, low-passed
    "max_hum_db": 40.0,                        # mains hum (50/60 Hz and harmonics) over the pause spectrum next to it; approved 5 to 10, recast han 31 (the owner approved it by ear, so hum is NOT what he hears as noise; the limit only stops gross hum)
}
_REFQ_CACHE = {}


def _goertzel(seg, rate, f):
    w = 2 * math.pi * f / rate
    c = 2 * math.cos(w)
    s1 = s2 = 0.0
    for v in seg:
        s1, s2 = v + c * s1 - s2, s1
    return s1 * s1 + s2 * s2 - c * s1 * s2


def _pause_hum_db(x, rate, db, hop, win, max_s=1.0):
    """Mains hum: the strongest of 50/100/150 and 60/120/180 Hz over the pause spectrum 6-20 Hz either side, in dB.
    Pauses = the quietest quarter of the frames that are not digital silence. None if under 0.4 s of such pause
    (a hum line cannot be told from the noise with less). No model."""
    live = sorted((d, i) for i, d in enumerate(db) if d > -80)
    if len(live) < 12:
        return None
    pick = sorted(i for _, i in live[:max(1, len(live) // 4)])
    seg = []
    for i in pick:
        seg += x[i * hop:i * hop + hop]
        if len(seg) >= rate * max_s:
            break
    if len(seg) < rate * 0.4:
        return None
    seg = [v * (0.5 - 0.5 * math.cos(2 * math.pi * k / (len(seg) - 1))) for k, v in enumerate(seg)]
    best = -99.0
    for base in (50.0, 60.0):
        for m in (1, 2, 3):
            fc = base * m
            pk = max(_goertzel(seg, rate, fc + d) for d in (-1.5, -0.75, 0.0, 0.75, 1.5))
            nb = sorted(_goertzel(seg, rate, fc + d) for d in (-20, -16, -12, -8, 8, 12, 16, 20))
            best = max(best, 10 * math.log10((pk + 1e-30) / (nb[len(nb) // 2] + 1e-30)))
    return round(best, 1)


def ref_profile(x, rate):
    """Measured quality profile of a reference clip (floats, rate 16 kHz or more)."""
    db, hop, win = frame_levels(x, rate)
    ordered = sorted(db)
    p95 = ordered[min(len(ordered) - 1, int(len(ordered) * .95))]
    p10 = ordered[int(len(ordered) * .10)]
    speech = [i for i, d in enumerate(db) if d >= p95 - SPEECH_BELOW_PEAK_DB]
    sl = sorted(db[i] for i in speech)
    p90s = sl[min(len(sl) - 1, int(len(sl) * .9))]
    med = sl[len(sl) // 2]
    peak = max(abs(v) for v in x) or 1e-9
    n = 512
    lo_e = top_e = 0.0
    cen_n = cen_d = 0.0
    for i in speech[::2]:
        seg = x[i * hop:i * hop + win]
        m = len(seg)
        buf = [complex(v * (0.5 - 0.5 * math.cos(2 * math.pi * k / max(1, m - 1))), 0) for k, v in enumerate(seg)] + [0j] * (n - m)
        _fft(buf)
        for k in range(1, n // 2):
            f = k * rate / n
            pw = abs(buf[k]) ** 2
            if f >= 100:
                cen_n += pw * f
                cen_d += pw
            if 100 <= f < 1000:
                lo_e += pw
            elif f >= 8000:
                top_e += pw
    drops, i = [], 0
    while i < len(db) - 3:
        if db[i] > p95 - 10 and db[i + 1] <= p95 - 10:
            base, j = db[i + 1], i + 1
            while j < len(db) and db[j] > base - 20 and j - i < 40:
                j += 1
            if j < len(db) and db[j] <= base - 20:
                drops.append((j - i - 1) * TRIM_HOP)
            i = j
        else:
            i += 1
    drops.sort()
    return {"floor_dbfs": round(p10, 1), "snr_db": round(p90s - p10, 1), "speech_median_dbfs": round(med, 1),
            "peak_dbfs": round(_db(peak), 1), "crest_db": round(_db(peak) - med, 1),
            "clip_samples": sum(1 for v in x if abs(v) >= 0.999),
            "zero_frac": round(sum(1 for v in x if v == 0.0) / max(1, len(x)), 4),
            "centroid_hz": round(cen_n / cen_d) if cen_d else 0,
            "hum_db": _pause_hum_db(x, rate, db, hop, win),
            "top_db": round(10 * math.log10((top_e + 1e-20) / (lo_e + 1e-20)), 1),
            "decay20_s": round(drops[len(drops) // 2], 3) if drops else None, "seconds": round(len(x) / rate, 2)}


def ref_quality_problems(prof, prov=None, q=REFQ):
    """-> list of messages (empty = the reference may be cloned). `prov` is the clip's provenance dict (votes)."""
    out = []
    # a published audiobook (LibriVox, public domain) has no community votes; every other clip needs them
    if prov is not None and prov.get("validation") != "published-audiobook" and (int(prov.get("up_votes", 0)) < q["min_up_votes"] or int(prov.get("down_votes", 0)) > q["max_down_votes"]):
        out.append(f"not validated: {prov.get('up_votes', 0)} up / {prov.get('down_votes', 0)} down votes "
                   f"(need >= {q['min_up_votes']} up, {q['max_down_votes']} down)")
    if prof["clip_samples"] > q["max_clip_samples"]:
        out.append(f"{prof['clip_samples']} sample(s) at full scale (clipped; limit {q['max_clip_samples']})")
    if prof["floor_dbfs"] > q["max_floor_dbfs"]:
        out.append(f"noise floor {prof['floor_dbfs']} dBFS (limit {q['max_floor_dbfs']})")
    if prof["snr_db"] < q["min_snr_db"]:
        out.append(f"SNR {prof['snr_db']} dB (limit {q['min_snr_db']})")
    if prof["crest_db"] < q["min_crest_db"]:
        out.append(f"crest {prof['crest_db']} dB: hot or squashed (limit {q['min_crest_db']})")
    if prof["top_db"] < q["min_top_db"]:
        out.append(f"muffled: energy above 8 kHz is {prof['top_db']} dB re 0.1-1 kHz (limit {q['min_top_db']})")
    if prof["decay20_s"] is not None and prof["decay20_s"] > q["max_decay20_s"]:
        out.append(f"reverberant: 20 dB decay {prof['decay20_s']} s (limit {q['max_decay20_s']})")
    # 2026-10-25 limits: keys are optional so older stored profiles still evaluate
    if prof.get("zero_frac") is not None and prof["zero_frac"] > q["max_zero_frac"]:
        out.append(f"gated or denoised: {prof['zero_frac'] * 100:.1f}% of samples are exact digital silence (limit {q['max_zero_frac'] * 100:.0f}%)")
    if prof["floor_dbfs"] < q["min_floor_dbfs"]:
        out.append(f"floor {prof['floor_dbfs']} dBFS is digital silence, not a microphone (a gate or denoiser ran; limit {q['min_floor_dbfs']})")
    if prof.get("centroid_hz") and prof["centroid_hz"] < q["min_centroid_hz"]:
        out.append(f"boxy: speech centroid {prof['centroid_hz']} Hz (limit {q['min_centroid_hz']:.0f})")
    if prof.get("hum_db") is not None and prof["hum_db"] > q["max_hum_db"]:
        out.append(f"mains hum {prof['hum_db']} dB over the pause spectrum (limit {q['max_hum_db']})")
    return out


def check_reference_quality(wav, prov_path=None):
    """REF-QUALITY on one reference wav (24 kHz 16-bit) -> (profile, problems). Cached per file state."""
    wav = Path(wav)
    st = wav.stat()
    key = (str(wav), st.st_mtime_ns, st.st_size)
    if key not in _REFQ_CACHE:
        x, rate = read_float(wav)
        if len(x) < rate:
            raise Fail("REF-QUALITY", f"{wav}: under 1 s of audio")
        _REFQ_CACHE[key] = ref_profile(x, rate)
    prof = _REFQ_CACHE[key]
    prov = read_json(prov_path) if prov_path and Path(prov_path).exists() else None
    return prof, ref_quality_problems(prof, prov)


# ---------------------------------------------------------------- TAKE-QUALITY: is the generated take itself clean? (2026-10-25)
# REF-QUALITY judges the reference; this judges what Chatterbox made from it, trimmed take by trimmed take, offline, no model.
# Calibrated on every take the owner approved (the 8 character lines of E01 calm, the four 2026-10-24 trial takes) against the
# ten takes of the banned narrator and the three rejected trial takes. Numbers: research/narrator-ban-2026-10-25.md.
TAKEQ = {
    "calibrated_on": "the owner's verdicts 2026-10-24 (rival, lead, partner, guide, recast hero/extra/han approved) and 2026-10-25 (narrator common_voice_ar_21519152 banned)",
    "max_pause_rel_db": -24.0,     # median level of the pauses INSIDE the take, re the loud part; approved -24.9 (the rival trial take the owner called perfect) to -40.1, banned narrator L03 -23.4 (weak on its own: L05 -25.4, L16 -26.8, L11 -26.5 pass)
    "min_centroid_hz": 400.0,      # boxy / low-passed take; approved 500 to 1670, banned narrator 338 to 435 (5 of its 10 takes under 400 by the voice.py measure; with the pause limit 6 of 10 fail, 0 of 12 approved)
    "max_clip_samples": 20,        # samples at full scale; approved 0 to 2, rejected han take 295
    "max_hum_db": 40.0,            # as REFQ
    "max_gate_gaps": 0,            # runs of >= 20 ms of exact zeros inside the speech (a gate chopping words); approved 0
}


def take_profile(x, rate):
    """Quality profile of one trimmed take."""
    db, hop, win = frame_levels(x, rate)
    ordered = sorted(db)
    p95 = ordered[min(len(ordered) - 1, int(len(ordered) * .95))]
    speech = [i for i, d in enumerate(db) if d >= p95 - SPEECH_BELOW_PEAK_DB]
    pause_rel = None
    gate_gaps = 0
    if speech:
        a, b = speech[0], speech[-1]
        gaps = [db[i] - p95 for i in range(a, b + 1) if db[i] < p95 - 18]
        if len(gaps) >= 3:
            gaps.sort()
            pause_rel = round(gaps[len(gaps) // 2], 1)
        run = 0
        for v in x[a * hop:(b + 1) * hop + win]:
            if v == 0.0:
                run += 1
                continue
            if run >= 0.020 * rate:
                gate_gaps += 1
            run = 0
    prof = ref_profile(x, rate)
    return {"pause_rel_db": pause_rel, "centroid_hz": prof["centroid_hz"], "clip_samples": prof["clip_samples"],
            "hum_db": prof["hum_db"], "gate_gaps": gate_gaps, "seconds": prof["seconds"]}


def take_quality_problems(prof, q=TAKEQ):
    out = []
    if prof.get("pause_rel_db") is not None and prof["pause_rel_db"] > q["max_pause_rel_db"]:
        out.append(f"noise between words: pauses sit {prof['pause_rel_db']} dB under the voice (limit {q['max_pause_rel_db']})")
    if prof.get("centroid_hz") and prof["centroid_hz"] < q["min_centroid_hz"]:
        out.append(f"boxy take: speech centroid {prof['centroid_hz']} Hz (limit {q['min_centroid_hz']:.0f})")
    if prof.get("clip_samples", 0) > q["max_clip_samples"]:
        out.append(f"{prof['clip_samples']} samples at full scale (limit {q['max_clip_samples']})")
    if prof.get("hum_db") is not None and prof["hum_db"] > q["max_hum_db"]:
        out.append(f"mains hum {prof['hum_db']} dB (limit {q['max_hum_db']})")
    if prof.get("gate_gaps", 0) > q["max_gate_gaps"]:
        out.append(f"{prof['gate_gaps']} digital-silence gap(s) inside the speech (a gate chops the words)")
    return out


# ---------------------------------------------------------------- the engine: Chatterbox Multilingual (local GPU)
# Generation settings, applied to every take. Defaults of chatterbox-tts 0.1.7 `generate()` except the token cap.
CHATTERBOX_SETTINGS = {"language_id": "ar", "exaggeration": 0.5, "cfg_weight": 0.5, "temperature": 0.8,
                       "repetition_penalty": 2.0, "min_p": 0.05, "top_p": 1.0}
TOKENS_PER_S = 25         # the speech tokenizer runs at 25 tokens per second of audio
CAP_BASE_S, CAP_PER_LETTER_S = 1.0, 0.20   # safety net: the package hard-codes 1000 tokens (40 s) for any line


CHARACTER_KNOBS = {"cfg_weight": (0.0, 1.0), "exaggeration": (0.25, 2.0), "temperature": (0.05, 5.0)}   # chatterbox-tts 0.1.7 generate() arguments a casting may set


def character_settings(casting, speaker):
    """Per-character Chatterbox overrides (cfg_weight, exaggeration, temperature) from casting.json `pace.chatterbox`; {} if none.
    temperature (2026-10-26): the d2 narrator records 0.7; a character without it keeps CHATTERBOX_SETTINGS' 0.8. A value outside the
    package's legal range is refused (VOICE-CAST), never clamped silently."""
    cb = ((casting["characters"].get(speaker) or {}).get("pace") or {}).get("chatterbox") or {}
    out = {}
    for k, (lo, hi) in CHARACTER_KNOBS.items():
        if k in cb:
            v = float(cb[k])
            if not lo <= v <= hi:
                raise Fail("VOICE-CAST", f"{speaker}: pace.chatterbox.{k} = {v} is outside {lo}-{hi}")
            out[k] = v
    return out


def line_tone(m):
    """A line may carry its own `tone` {exaggeration, cfg_weight} (calm-format C3, 2026-10-25: the narrator reads a written object in a different, distinct tone).
    Only those two Chatterbox knobs, only inside their legal range; it replaces the character's pace for that line alone."""
    t = m.get("tone") or {}
    out = {}
    for k, lo, hi in (("exaggeration", 0.25, 1.0), ("cfg_weight", 0.2, 0.9)):
        if k in t:
            out[k] = min(hi, max(lo, float(t[k])))
    return out


_SOUND_PROFILE = {}


def sound_profile():
    """tools/sound_profile.json (stdlib json, so the Chatterbox worker and the dry run can read it)."""
    if "p" not in _SOUND_PROFILE:
        _SOUND_PROFILE["p"] = read_json(Path(__file__).resolve().parent / "sound_profile.json")
    return _SOUND_PROFILE["p"]


def letters_of(tts_text):
    return len(AR_LETTER.findall(tts_text)) or len(tts_text)


def voice_rate(speaker=None, ref_sha256=None, profile=None):
    """Slowest plausible speaking rate (letters per second) of one voice: its measured slowest take divided by the margin,
    when the profile has a measurement for this speaker AND this exact reference clip; else the default (the old cap's rate).
    -> (letters_per_s, source)."""
    G = (profile or sound_profile())["take"]["gen_cap"]
    v = (G.get("voices") or {}).get(speaker or "")
    if v and ref_sha256 and v.get("ref_sha256") == ref_sha256:
        return v["slowest_letters_per_s"] / G["margin"], f"measured {speaker}"
    return G["default_letters_per_s"], "default"


def token_cap(tts_text, speaker=None, ref_sha256=None, profile=None):
    """Per-line generation cap (2026-10-26, `take.gen_cap`): base + letters at the voice's slowest plausible rate. Chatterbox
    hard-codes 1000 tokens (40 s) for any line; a take that never emits EOS runs to this cap, so a tighter cap is a shorter
    noise tail. Without a measured voice it is the old 1 s + 0.2 s per letter."""
    G = (profile or sound_profile())["take"]["gen_cap"]
    rate, _ = voice_rate(speaker, ref_sha256, profile)
    s = G["base_s"] + letters_of(tts_text) / rate
    return max(G["min_tokens"], min(G["max_tokens"], math.ceil(TOKENS_PER_S * s)))


def edge_done_after_s(tts_text, speaker=None, ref_sha256=None, profile=None):
    """Time after the first word by which the line is certainly spoken (letters at the slowest plausible rate): a voiced
    run that starts later, after a pause, is a model run-on (voice_edges.speech_span)."""
    rate, _ = voice_rate(speaker, ref_sha256, profile)
    return letters_of(tts_text) / rate


def eos_after_complete_tokens(profile=None):
    E = (profile or sound_profile())["take"]["eos"]
    return max(1, int(round(E["after_complete_max_s"] * TOKENS_PER_S)))


def install_eos_guard(analyzer_cls, max_tokens):
    """Wrap chatterbox's AlignmentStreamAnalyzer.step (multilingual only) so that, once the analyzer has marked the text
    complete, at most `max_tokens` more speech tokens are made before EOS is forced (`take.eos`). The package's own rules
    (long_tail, alignment_repetition, token_repetition) stay; this closes the hole they leave: after completion, attention
    resting on the 4th or 5th text token from the end is neither a long tail (last 3) nor a repetition (all but the last 5),
    while EOS stays suppressed whenever the argmax sits before the last 3 tokens, so the take runs on to the token cap.
    Idempotent. Works on anything with `logits * 0` and item assignment (torch tensors; numpy in the tests)."""
    if getattr(analyzer_cls.step, "_nj_eos_guard", None) == max_tokens:
        return analyzer_cls
    orig = getattr(analyzer_cls.step, "_nj_orig", analyzer_cls.step)

    def step(self, logits, next_token=None):
        out = orig(self, logits, next_token=next_token)
        ca = getattr(self, "completed_at", None)
        if ca is not None and int(self.alignment.shape[0]) - int(ca) >= max_tokens:
            out = out * 0 - 2 ** 15
            out[..., self.eos_idx] = 2 ** 15
            self.nj_forced_eos = True
        return out

    step._nj_eos_guard, step._nj_orig = max_tokens, orig
    analyzer_cls.step = step
    return analyzer_cls


def engine_ok(casting, engine=ENGINE):
    if engine != ENGINE or casting.get("engine", ENGINE) != ENGINE:
        raise Fail("VOICE-BANNED", f"engine {engine!r} is refused: the only engine is Chatterbox Multilingual (owner, 2026-10-24). "
                                   "Google Gemini is banned for good; no other model may voice a line.")


LICENSES = ("CC0-1.0", "PUBLIC-DOMAIN")   # PUBLIC-DOMAIN (owner, 2026-10-25 task): only with a source_url and a licence_evidence_url in the provenance
BANNED_VOICES = "bible/voices-banned.json"


def load_banned(repo=REPO):
    """The repo-wide list of banned voices (owner, 2026-10-25): never cast again, in any series. [] if there is no file."""
    p = repo / BANNED_VOICES
    return read_json(p).get("banned", []) if p.exists() else []


def banned_reason(ref, prov, banned):
    """-> message if this reference (casting `reference` dict, provenance dict) is a banned voice, by clip id, mp3 hash or speaker id."""
    ids = {x for x in (ref.get("clip_source_id"), (prov or {}).get("clip")) if x}
    hashes = {x for x in ((prov or {}).get("sha256_mp3"),) if x}
    spk = (prov or {}).get("speaker_id_hashed")
    for b in banned:
        if ids & set(b.get("clip_source_ids", [])) or hashes & set(b.get("sha256_mp3", [])) or (spk and spk in b.get("speaker_ids_hashed", [])):
            return f"banned voice {b['id']} ({b['date']}): {b['reason']}"
    return None


def reference_for(casting, speaker, repo=REPO, check=True):
    c = casting["characters"].get(speaker, {})
    ref = c.get("reference") or {}
    clip = ref.get("clip")
    if not clip:
        raise Fail("VOICE-REF", f"{speaker}: no reference clip chosen yet (casting.json characters.{speaker}.reference.clip)")
    p = repo / clip
    prov = repo / ref.get("provenance", "")
    if not p.exists():
        raise Fail("VOICE-REF", f"{speaker}: reference clip {p} not found")
    if ref.get("license") not in LICENSES or not ref.get("provenance") or not prov.exists():
        raise Fail("VOICE-REF", f"{speaker}: a reference clip must be CC0-1.0 (or verifiably public domain, 2026-10-25) with a provenance file")
    if ref.get("license") == "PUBLIC-DOMAIN" and not (read_json(prov).get("licence_evidence_url") and read_json(prov).get("source_url")):
        raise Fail("VOICE-REF", f"{speaker}: a public-domain reference needs source_url and licence_evidence_url in its provenance")
    ban = banned_reason(ref, read_json(prov), load_banned(repo))
    if ban:
        raise Fail("VOICE-BANNED-REF", f"{speaker}: reference {clip} is a {ban}. A banned voice is never cast again; choose another CC0 clip.")
    if check:
        _, bad = check_reference_quality(p, prov)
        if bad:
            raise Fail("REF-QUALITY", f"{speaker}: reference {clip} is not clean enough to clone: " + "; ".join(bad) +
                       ". Choose another CC0 clip (uv run tools/voice.py refcheck <wav> <provenance.json>).")
    return p


def casting_ref_problems(casting, repo=REPO):
    """REF-QUALITY (and licence) for every character that has a reference clip -> [(id, message)]."""
    out = []
    for k, c in casting["characters"].items():
        if not (c.get("reference") or {}).get("clip"):
            continue
        try:
            reference_for(casting, k, repo)
        except Fail as e:
            out.append((e.cid, str(e)))
    return out


def check_gate_receipt(paths):
    r = paths["work"] / "gate.json"
    if not r.exists():
        raise Fail("VOICE-GATE", "no gate receipt: run `gate` first")
    g = read_json(r)
    if g.get("manifest_sha256") != sha(paths["manifest"].read_bytes()) or g.get("script_sha256") != sha(paths["script"].read_bytes()):
        raise Fail("VOICE-GATE", "manifest or script changed since `gate` passed; run `gate` again")


def chatterbox_worker(job_path):
    """Runs INSIDE work/tts-engines/chatterbox (torch there). Loads the model once and makes ONE take per job line."""
    import torch
    import torchaudio as ta
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    job = read_json(job_path)
    marks = job.get("marks")
    m = ChatterboxMultilingualTTS.from_pretrained(device="cuda")
    if marks:
        mark(marks, {"event": "loaded"})
    orig = m.t3.inference
    cap = {"n": 1000}

    def capped(*a, **k):
        k["max_new_tokens"] = cap["n"]
        return orig(*a, **k)

    m.t3.inference = capped
    if job.get("eos_after_complete_tokens"):         # take.eos (2026-10-26): stop a take that runs on after the text is spoken
        from chatterbox.models.t3.inference.alignment_stream_analyzer import AlignmentStreamAnalyzer
        install_eos_guard(AlignmentStreamAnalyzer, int(job["eos_after_complete_tokens"]))
    results = []
    for ln in job["lines"]:
        cap["n"] = ln["cap"]
        if marks:                                    # before generation: from here a crash may leave audio behind
            mark(marks, {"event": "generating", "id": ln["id"]})
        torch.manual_seed(int(sha(ln["id"])[:8], 16))
        t0 = time.time()
        wav = m.generate(ln["text"], audio_prompt_path=ln["ref"], **{**job["settings"], **ln.get("settings", {})})
        torch.cuda.synchronize()
        ta.save(ln["out"], wav.cpu(), m.sr)
        results.append({"id": ln["id"], "gen_s": round(time.time() - t0, 1), "sr": m.sr})
        write_json(job["result"], {"lines": results})
    return 0


# ---------------------------------------------------------------- pre-flight (resources the model needs before it loads)
GB = 1024 ** 3
NEED_VRAM = int(4.0 * GB)          # measured in the trial: about 3.6 GB VRAM, plus margin
COMMIT_MARGIN = int(2.0 * GB)      # on top of the model files (they are mapped into commit memory while loading)
COMMIT_FALLBACK = int(8.0 * GB)    # when the model cache cannot be measured
MODEL_EXT = (".safetensors", ".pt", ".pth", ".bin", ".ckpt")


def need_commit_bytes(hf_home=None):
    """Commit memory the load needs: sizes of the model weight files in the HF cache plus a margin."""
    root = Path(hf_home) if hf_home else REPO / "work" / "tts-engines" / "hf-cache"
    seen, total = set(), 0
    if root.exists():
        for f in root.rglob("*"):
            if f.suffix in MODEL_EXT and f.is_file():
                r = f.resolve()                      # snapshots are links to blobs: count each blob once
                if r not in seen:
                    seen.add(r)
                    total += r.stat().st_size
    return (total or COMMIT_FALLBACK - COMMIT_MARGIN) + COMMIT_MARGIN


def free_commit_bytes():
    """Windows: free commit memory (RAM + paging file) via GlobalMemoryStatusEx. None where it cannot be read."""
    if os.name != "nt":
        return None
    import ctypes

    class MS(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    ms = MS()
    ms.dwLength = ctypes.sizeof(MS)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms)):
        return None
    return int(ms.ullAvailPageFile)


def free_gpu_bytes(py):
    """Free VRAM as the engine venv's torch sees it. None if it cannot be read."""
    try:
        r = subprocess.run([str(py), "-c", "import torch;print(torch.cuda.mem_get_info()[0])"], capture_output=True,
                           text=True, timeout=120)
        return int(r.stdout.strip().splitlines()[-1]) if r.returncode == 0 else None
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None


def preflight_problems(commit_free, gpu_free, need_commit, need_gpu=NEED_VRAM):
    out = []
    if commit_free is not None and commit_free < need_commit:
        out.append(f"commit memory (RAM + paging file): {commit_free / GB:.1f} GB free, the model load needs {need_commit / GB:.1f} GB; "
                   "close programs or enlarge the paging file")
    if gpu_free is not None and gpu_free < need_gpu:
        out.append(f"GPU memory: {gpu_free / GB:.1f} GB free, Chatterbox needs {need_gpu / GB:.1f} GB; close what is using the GPU")
    return out


def engine_python():
    py = CHATTERBOX_DIR / "Scripts" / "python.exe"
    if not py.exists():
        py = CHATTERBOX_DIR / "bin" / "python"
    return py


def real_resources():
    py = engine_python()
    return {"commit_free": free_commit_bytes(), "gpu_free": free_gpu_bytes(py) if py.exists() else None,
            "need_commit": need_commit_bytes()}


def cmd_voice(paths=None, go=False, engine=ENGINE, repo=REPO, synth=None, resources=None, master=None, **_ignored):
    """ONE Chatterbox take per line, then the offline end-trim. Without --go it only prints the plan.
    `synth(job) -> None` replaces the GPU worker in tests; it must write each job line's `out` wav and call
    `mark(job["marks"], ...)` when it loads / starts a line. `resources() -> dict` replaces the pre-flight probe
    (default: probe only when the real worker is used)."""
    script = load_script(paths)
    casting = load_casting(script, repo)
    engine_ok(casting, engine)
    if not paths["manifest"].exists():
        raise Fail("VOICE-TEXT", f"{paths['manifest']} not found; run `manifest` first")
    manifest = read_json(paths["manifest"])
    work = paths["work"]
    jobs = []
    for m in manifest["lines"]:
        n = m["id"]
        if superseded_log(work).exists() and line_state(work, n) == "taken":
            continue                      # only the lines of a superseded (banned) voice are voiced again; settled takes stay
        ref = reference_for(casting, m["speaker"], repo)
        if line_state(work, n) in ("taken", "blocked-after-start"):
            raise Fail("VOICE-ONCE", f"line {n}: a take was already made or started; a line is voiced once, never re-voiced")
        jobs.append({"id": n, "speaker": m.get("speaker"), "text": m["tts_text"], "ref": str(ref), "out": str(work / f"{n}.wav"),
                     "ref_sha256": (rs := sha(ref.read_bytes())), "cap": token_cap(m["tts_text"], m.get("speaker"), rs),
                     "cap_rate": voice_rate(m.get("speaker"), rs)[1], "done_after_s": round(edge_done_after_s(m["tts_text"], m.get("speaker"), rs), 2),
                     "settings": {**character_settings(casting, m.get("speaker")), **line_tone(m)}})
    if not go:
        print(f"dry run: {len(jobs)} take(s), engine {ENGINE}, one each, local GPU. Add --go to voice them.")
        return 0
    check_gate_receipt(paths)
    if resources is None and synth is None:
        resources = real_resources
    if resources is not None:
        r = resources()
        short = preflight_problems(r.get("commit_free"), r.get("gpu_free"), r.get("need_commit", need_commit_bytes()))
        if short:
            raise Fail("VOICE-PREFLIGHT", "; ".join(short) + ". Nothing was started; no line is used up.")
    work.mkdir(parents=True, exist_ok=True)
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    marks = work / "worker-marks.jsonl"
    marks.write_text("", encoding="utf-8")           # earlier runs are settled in attempts.jsonl
    for j in jobs:                                   # logged BEFORE the model runs: a crash never allows a second take
        log_attempt(work, {"id": j["id"], "status": "started", "engine": ENGINE, "at": now})
    job = {"lines": jobs, "settings": CHATTERBOX_SETTINGS, "result": str(work / "worker-result.json"), "marks": str(marks),
           "eos_after_complete_tokens": eos_after_complete_tokens()}
    write_json(work / "worker-job.json", job)
    ids = [j["id"] for j in jobs]
    err_log = work / "worker-stderr.log"
    failure = None
    if synth is not None:
        try:
            synth(job)
        except Exception as e:                       # the synthetic worker died
            failure = f"{type(e).__name__}: {e}"
    else:
        py = engine_python()
        if not py.exists():
            for n in ids:
                log_attempt(work, {"id": n, "status": "not-taken", "engine": ENGINE, "reason": "not-taken (engine venv not found)"})
            raise Fail("VOICE-ENGINE", f"{CHATTERBOX_DIR} venv not found; no line is used up")
        env = dict(os.environ, PYTHONUTF8="1", HF_HOME=str(REPO / "work" / "tts-engines" / "hf-cache"))
        with open(err_log, "w", encoding="utf-8") as ef:
            r = subprocess.run([str(py), str(Path(__file__).resolve()), "chatterbox-worker", str(work / "worker-job.json")],
                               env=env, stderr=ef)
        if r.returncode != 0:
            failure = f"the Chatterbox worker exited {r.returncode}"
            tail = stderr_tail(err_log)
            if tail:
                failure += f" | stderr tail: {tail}"
    gen = {r["id"]: r for r in (read_json(job["result"])["lines"] if Path(job["result"]).exists() else [])}
    if failure is None and any(not Path(j["out"]).exists() for j in jobs):
        failure = "the worker finished but wrote no audio for: " + ", ".join(j["id"] for j in jobs if not Path(j["out"]).exists())
    if failure is not None:
        flat = " ".join(failure.split())
        nt, bl = settle_failed_run(work, ids, marks, flat[:1200])
        raise Fail("VOICE-ENGINE", f"{flat}. Not taken (may be voiced later): {', '.join(nt) or 'none'}. "
                                   f"Blocked, generation had started: {', '.join(bl) or 'none'}.")
    for j in jobs:
        raw = Path(j["out"])
        import voice_master as VM
        info = cmd_trim(raw, work / f"{j['id']}.trimmed.wav", master=master, role=VM.role_of(j.get("speaker")), done_after_s=j.get("done_after_s"))
        log_attempt(work, {"id": j["id"], "status": "ok", "engine": ENGINE, "settings": CHATTERBOX_SETTINGS,
                           "reference": {"clip": Path(j["ref"]).relative_to(repo).as_posix() if Path(j["ref"]).is_relative_to(repo) else j["ref"],
                                         "sha256": j["ref_sha256"]},
                           "token_cap": j["cap"], "token_cap_rate": j.get("cap_rate"), "eos_after_complete_tokens": job["eos_after_complete_tokens"], "gen_s": gen.get(j["id"], {}).get("gen_s"), "raw_sha256": sha(raw.read_bytes()),
                           "tts_sha256": sha(j["text"].encode("utf-8")),
                           "trim": info})
    measure_manifest(paths, work)
    return 0


NL = chr(10)


def superseded_log(work):
    return Path(work) / "supersede.jsonl"


def cmd_supersede(paths, speaker, reason, repo=REPO):
    """the owner banned a voice (bible/voices-banned.json): move the takes it made out of the way so the speaker's lines can be
    voiced with the NEW voice. This is a new voice, not a re-voice: it is refused unless the casting lists a banned reference
    for the speaker and the speaker's current reference is not banned. The old takes are kept in <work>-superseded-<speaker>/.
    -> list of moved line ids."""
    script = load_script(paths)
    casting = load_casting(script, repo)
    ch = casting["characters"].get(speaker) or {}
    if not ch.get("banned_references"):
        raise Fail("VOICE-ONCE", f"{speaker}: no banned reference in the casting; a voiced line is never re-voiced")
    reference_for(casting, speaker, repo)            # the new reference must exist, be licensed, not banned and clean
    manifest = read_json(paths["manifest"])
    work = paths["work"]
    ids = [m["id"] for m in manifest["lines"] if m["speaker"] == speaker]
    dest = work.with_name(work.name + f"-superseded-{speaker}")
    (dest / "visemes").mkdir(parents=True, exist_ok=True)
    moved = []
    for n in ids:
        for suffix in (".wav", ".trimmed.wav"):
            f = work / f"{n}{suffix}"
            if f.exists():
                os.replace(f, dest / f.name)
                if suffix == ".wav":
                    moved.append(n)
        v = work / "visemes" / f"{n}.json"
        if v.exists():
            os.replace(v, dest / "visemes" / v.name)
    ap = work / "attempts.jsonl"
    if ap.exists():
        rows = [ln for ln in ap.read_text(encoding="utf-8").splitlines() if ln.strip()]
        keep = [ln for ln in rows if json.loads(ln)["id"] not in ids]
        with open(dest / "attempts.jsonl", "a", encoding="utf-8") as fh:
            fh.write(NL.join(ln for ln in rows if ln not in keep) + NL)
        ap.write_text(NL.join(keep) + (NL if keep else ""), encoding="utf-8")
    with open(superseded_log(work), "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"speaker": speaker, "lines": ids, "moved": moved, "reason": reason, "kept_in": str(dest),
                             "at": time.strftime("%Y-%m-%dT%H:%M:%S")}, ensure_ascii=False) + NL)
    return moved


def cmd_retext(paths, reason, baseline=None, repo=REPO):
    """The writer changed the WORDS of lines that already have a take (the owner 2026-10-25: the narrator now addresses the audience as «أنتم»).
    New text is a new line, not a re-voice: a take belongs to the text it was made from. For every manifest line whose tts_text differs from the text
    its take voiced, the old take is moved to <work>-superseded-text/ (kept, never deleted) so `voice --go` voices that line once. A line whose text is
    UNCHANGED is never touched (VOICE-ONCE keeps its take). The voiced text is read from the take's `tts_sha256` in attempts.jsonl, or, for takes made before
    that field existed, from `baseline` (the manifest as it was when they were voiced). A line with no way to know is left alone and reported.
    -> (moved ids, unchanged ids, unknown ids)."""
    manifest = read_json(paths["manifest"])
    work = paths["work"]
    base = {m["id"]: sha(m["tts_text"].encode("utf-8")) for m in read_json(baseline)["lines"]} if baseline else {}
    att = attempts(work)
    moved, same, unknown = [], [], []
    dest = work.with_name(work.name + "-superseded-text")
    for m in manifest["lines"]:
        n = m["id"]
        if line_state(work, n) != "taken":
            continue
        voiced = (att.get(n) or {}).get("tts_sha256") or base.get(n)
        if voiced is None:
            unknown.append(n)
        elif voiced == sha(m["tts_text"].encode("utf-8")):
            same.append(n)
        else:
            moved.append(n)
    if not moved:
        return moved, same, unknown
    (dest / "visemes").mkdir(parents=True, exist_ok=True)
    for n in moved:
        for suffix in (".wav", ".trimmed.wav"):
            f = work / f"{n}{suffix}"
            if f.exists():
                os.replace(f, dest / f.name)
        v = work / "visemes" / f"{n}.json"
        if v.exists():
            os.replace(v, dest / "visemes" / v.name)
    ap = work / "attempts.jsonl"
    if ap.exists():
        rows = [ln for ln in ap.read_text(encoding="utf-8").splitlines() if ln.strip()]
        keep = [ln for ln in rows if json.loads(ln)["id"] not in moved]
        with open(dest / "attempts.jsonl", "a", encoding="utf-8") as fh:
            fh.write(NL.join(ln for ln in rows if ln not in keep) + NL)
        ap.write_text(NL.join(keep) + (NL if keep else ""), encoding="utf-8")
    ts = work / "take-sources.json"       # the stage-gate record of the text each take voiced (stagegate.v_voice): a retexted line has no take now, so its entry goes, or the new take reads as VOICE-STALE-TAKE (E02 H01, 2026-10-27)
    if ts.is_file():
        try:
            rec = json.loads(ts.read_text(encoding="utf-8"))
            dropped = [rec.pop(n, None) for n in moved]      # a list, not any(): any() stops at the first hit and left every other stale line in the record (E02, 2026-10-27)
            if any(d is not None for d in dropped):
                ts.write_text(json.dumps(rec, indent=1, sort_keys=True), encoding="utf-8")
        except ValueError:
            pass
    with open(superseded_log(work), "a", encoding="utf-8") as fh:     # the same marker supersede writes: voice --go then voices only the lines without a take
        fh.write(json.dumps({"kind": "retext", "lines": moved, "moved": moved, "unchanged": same, "reason": reason, "kept_in": str(dest),
                             "at": time.strftime("%Y-%m-%dT%H:%M:%S")}, ensure_ascii=False) + NL)
    return moved, same, unknown


def cmd_refit_mark(paths, old_id, new_id, reason):
    """A voiced line was too long for its slot and the writer reworded it under a NEW id (tools/line_refit.py, R-502: H01 -> H01r1). The new id is a new line, not a re-voice:
    this writes the same marker `supersede` and `retext` write, so `voice --go` voices only the lines that have no take and leaves every settled take alone. The old take
    stays on disk, unused (never deleted, never voiced again); it is refused when the new id already has a take or an attempt (one take per id) or the old id still stands in the script."""
    work = paths["work"]
    if new_id == old_id:
        raise Fail("VOICE-ONCE", f"{old_id}: a refit needs a new line id; the old id keeps its take")
    if line_state(work, new_id) not in ("untouched", "not-taken"):
        raise Fail("VOICE-ONCE", f"line {new_id}: a take was already made or started; a line is voiced once, never re-voiced")
    if any(l.get("id") == old_id for l in read_json(paths["script"]).get("lines", [])):
        raise Fail("VOICE-TEXT", f"line {old_id} is still in the script: the refit replaces it with {new_id}")
    work.mkdir(parents=True, exist_ok=True)
    with open(superseded_log(work), "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"kind": "refit", "lines": [new_id], "replaces": old_id, "reason": reason, "kept_in": str(work),
                             "at": time.strftime("%Y-%m-%dT%H:%M:%S")}, ensure_ascii=False) + NL)
    return new_id


def measure_manifest(paths, work=None):
    """Write the measured length of each line's take into the narration manifest: `seconds` = the trimmed (finished)
    clip, `raw_seconds` = the raw take. These are the fields voice_style_gate.py reads in full mode. No synthesis.
    -> ids measured."""
    work = Path(work or paths["work"])
    manifest = read_json(paths["manifest"])
    done = []
    for m in manifest["lines"]:
        t, r = work / f"{m['id']}.trimmed.wav", work / f"{m['id']}.wav"
        if not t.exists():
            continue
        m["seconds"] = round(wav_seconds(t), 3)
        if r.exists():
            m["raw_seconds"] = round(wav_seconds(r), 3)
        done.append(m["id"])
    if done:
        write_json(paths["manifest"], manifest)
    return done


def cmd_measure(d, work=None):
    paths = episode_paths(d)
    if work is None and (paths["dir"] / "take").is_dir():
        work = paths["dir"] / "take"
    done = measure_manifest(paths, work)
    if not done:
        raise Fail("VOICE-AUDIO", f"no trimmed takes found for {paths['dir']}; nothing measured")
    return done


def cmd_status(d, repo=REPO):
    """One line per id: taken / not-taken / blocked-after-start (untouched = never tried). `d` is an episode dir or a work dir."""
    d = Path(d)
    if (d / "script.json").exists() or d.suffix == ".json":
        paths = episode_paths(d, repo)
        work = paths["work"]
        ids = [m["id"] for m in read_json(paths["manifest"])["lines"]] if paths["manifest"].exists() else list(attempts(work))
    else:
        work, ids = d, list(attempts(d))
    return [(n, line_state(work, n)) for n in ids]


def cmd_repair(work, reason):
    """Mark `started`-only lines (no wav, no generation marker) not-taken. For logs written before the marker existed:
    the caller asserts the worker died at model load. Lines with any later record (generating/error/ok) stay blocked."""
    work = Path(work)
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    done = []
    for n, rec in attempts(work).items():
        if rec.get("status") == "started" and line_state(work, n) == "blocked-after-start":
            log_attempt(work, {"id": n, "status": "not-taken", "engine": rec.get("engine", ENGINE), "at": now,
                               "reason": f"not-taken (engine failed to load: {reason})", "was": rec})
            done.append(n)
    return done


def tail_checks(work, manifest):
    """VOICE-TAIL for every line that has a trimmed take (run by `gate --full`)."""
    f = []
    att = attempts(work)
    for m in manifest.get("lines", []):
        t = work / f"{m['id']}.trimmed.wav"
        if not t.exists():
            continue
        x, rate = read_float(t)
        f += [(c, f"line {m['id']}: {msg}") for c, msg in tail_problems(x, rate, (att.get(m["id"]) or {}).get("trim"))]
        f += [("VOICE-EDGE-NOISE", f"line {m['id']}: {msg}") for msg in edge_noise_problems(x, rate)]
        f += [("TAKE-QUALITY", f"line {m['id']}: {msg}") for msg in take_quality_problems(take_profile(x, rate))]
        mrec = ((att.get(m["id"]) or {}).get("trim") or {}).get("master")
        if mrec:                                     # VOICE-MASTER: measured again on the file, against the profile (a take voiced before the chain has no record)
            import voice_master as VM
            import numpy as np
            f += [(c, f"line {m['id']}: {msg}") for c, msg in VM.gate_problems(VM.measure(np.asarray(x), rate), mrec["role"])]
            f += [("VOICE-MASTER", f"line {m['id']}: {msg}") for msg in mrec.get("contract", [])]
    return f


# ---------------------------------------------------------------- audio envelope
def read_wav(path):
    try:
        with wave.open(str(path), "rb") as w:
            n, ch, sw, rate = w.getnframes(), w.getnchannels(), w.getsampwidth(), w.getframerate()
            raw = w.readframes(n)
    except wave.Error:                               # float32 wav from torchaudio
        x, rate = read_float(path)
        return array.array("h", (max(-32768, min(32767, int(v * 32767))) for v in x)), rate
    if sw != 2:
        raise Fail("VOICE-AUDIO", f"{path}: only 16-bit wav is read")
    a = array.array("h")
    a.frombytes(raw)
    if sys.byteorder == "big":
        a.byteswap()
    return a[::ch], rate


def wav_seconds(path):
    try:
        with wave.open(str(path), "rb") as w:
            return w.getnframes() / w.getframerate()
    except wave.Error:
        x, rate = read_float(path)
        return len(x) / rate


def voiced_segments(samples, rate, hop_ms=10, gap_ms=120, min_ms=50):
    hop = max(1, int(rate * hop_ms / 1000))
    win = hop * 2
    env = []
    for i in range(0, max(1, len(samples) - win + 1), hop):
        seg = samples[i:i + win]
        env.append(math.sqrt(sum(x * x for x in seg) / len(seg)))
    if not env or max(env) < 50:
        raise Fail("VOICE-AUDIO", "audio is silent")
    s = sorted(env)
    floor, peak = s[len(s) // 10], s[int(len(s) * .95) - 1 if len(s) > 1 else 0]
    thr = floor + .12 * (peak - floor)
    segs, start = [], None
    for k, v in enumerate(env):
        if v > thr and start is None:
            start = k
        elif v <= thr and start is not None:
            segs.append([start, k]); start = None
    if start is not None:
        segs.append([start, len(env)])
    merged = []
    for a, b in segs:
        if merged and (a - merged[-1][1]) * hop_ms < gap_ms:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    out = [(a * hop_ms / 1000, b * hop_ms / 1000) for a, b in merged if (b - a) * hop_ms >= min_ms]
    if not out:
        raise Fail("VOICE-AUDIO", "no voiced segment found")
    return out, len(samples) / rate


# ---------------------------------------------------------------- visemes
VOWEL_MARK = {"َ": "V3", "ُ": "V4", "ِ": "V5", "ً": "V3", "ٌ": "V4", "ٍ": "V5"}
FALLBACK = {"ة": "ه", "أ": "ء", "إ": "ء", "ؤ": "ء", "ئ": "ء", "ٱ": "ا", "پ": "ب"}
PAUSE_CH = ".؟?!،,:؛…"
SHADDA = "ّ"


def latest_face(char, repo=REPO):
    best, bv = None, -1
    for p in (repo / "catalogue" / "characters" / char).glob("v*/face/face.json"):
        v = int(re.sub(r"\D", "", p.parent.parent.name) or 0)
        if v > bv:
            best, bv = p, v
    if best is None:
        raise Fail("VOICE-VISEME", f"no face.json for {char}")
    return best, f"v{bv}"


def letter_map(face):
    m = {}
    for vid, v in face["visemes"].items():
        if not re.fullmatch(r"V\d+", vid):
            continue
        for tok in (v.get("letters") or "").split():
            for ch in tok:
                m[ch] = vid
    return m


def symbols(text, lmap):
    """text -> [(viseme id, weight)]. Consonants weight 1, vowels 2, shadda x1.6, punctuation a pause."""
    out = []
    chars = list(text)
    for i, ch in enumerate(chars):
        if ch in PAUSE_CH:
            out.append(("V0", .8)); continue
        if not AR_LETTER.match(ch):
            continue
        ch = FALLBACK.get(ch, ch)
        j, marks = i + 1, ""
        while j < len(chars) and AR_MARK.match(chars[j]):
            marks += chars[j]; j += 1
        vid = lmap.get(ch, "V8")
        vowel = next((VOWEL_MARK[m] for m in marks if m in VOWEL_MARK), None)
        if ch in "اآىٱ":
            out.append(("V3", 2.0)); continue
        if ch in "وي" and not marks:
            out.append((vid, 2.0)); continue
        if "ْ" in marks and SHADDA not in marks and vowel is None:
            out.append((vid, 1.0)); continue
        out.append((vid, 1.6 if SHADDA in marks else 1.0))
        if vowel:
            out.append((vowel, 2.0))
    return out


def spread(syms, segs):
    """Lay symbols over the voiced time only. Returns [(t0, t1, id)] with V0 in the gaps."""
    total = sum(b - a for a, b in segs)
    wsum = sum(w for _, w in syms) or 1
    # voiced-time -> absolute-time
    def at(vt):
        acc = 0.0
        for a, b in segs:
            if vt <= acc + (b - a) + 1e-9:
                return a + (vt - acc)
            acc += b - a
        return segs[-1][1]
    ivs, pos = [], 0.0
    for vid, w in syms:
        d = w / wsum * total
        a, b = at(pos), at(pos + d)
        ivs.append([a, b, vid])
        pos += d
    # open the mouth only when a voiced segment is running: split an interval across a gap
    res = []
    for a, b, vid in ivs:
        if b - a <= 1e-6:
            continue
        cur = a
        for sa, sb in segs:
            lo, hi = max(cur, sa), min(b, sb)
            if hi > lo:
                if lo > cur + 1e-6 and res:
                    res.append([cur, lo, "V0"])
                res.append([lo, hi, vid])
                cur = hi
    # fill gaps between intervals
    full = []
    for iv in res:
        if full and iv[0] > full[-1][1] + 1e-6:
            full.append([full[-1][1], iv[0], "V0"])
        full.append(iv)
    return full


def simplify(ivs, min_hold):
    changed = True
    while changed and len(ivs) > 1:
        changed = False
        for k, iv in enumerate(ivs):
            if iv[1] - iv[0] < min_hold:
                if k > 0:
                    ivs[k - 1][1] = iv[1]
                else:
                    ivs[1][0] = iv[0]
                del ivs[k]
                changed = True
                break
    out = []
    for iv in ivs:
        if out and out[-1][2] == iv[2]:
            out[-1][1] = iv[1]
        else:
            out.append(list(iv))
    return out


def build_track(line, wav, face, face_ver, repo=REPO, fps=FPS):
    samples, rate = read_wav(wav)
    segs, dur = voiced_segments(samples, rate)
    syms = symbols(line.get("tts_text") or line["text"], letter_map(face))
    if not any(v != "V0" for v, _ in syms):
        raise Fail("VOICE-VISEME", f"line {line['id']}: no Arabic letters to map")
    ivs = simplify(spread(syms, segs), MIN_HOLD_FRAMES / fps)
    keys = [{"t": round(a, 3), "id": vid} for a, b, vid in ivs]
    if keys[0]["t"] > 0:
        keys.insert(0, {"t": 0.0, "id": "V0"})
    keys.append({"t": round(ivs[-1][1], 3), "id": "V0"})
    return {"format": "viseme-track/1", "line": line["id"], "character": line["speaker"], "face": f"{line['speaker']}/{face_ver}",
            "fps": fps, "duration_s": round(dur, 3), "ramp_s": 0.04,
            "source": {"audio_sha256": sha(Path(wav).read_bytes()), "text_sha256": sha(line.get("tts_text") or line["text"]),
                       "method": "audio envelope + letters; no model"},
            "keys": keys}


def has_face(speaker, repo=REPO):
    """True when the speaker is a drawn character with a face.json. The narrator is a voice with no body: it has no mouth to move."""
    return any((repo / "catalogue" / "characters" / speaker).glob("v*/face/face.json"))


def heard_take(work, line_id):
    """The audio the viewer hears for a line: the trimmed take (what calm_compose and compose mix), else the raw one. The viseme track must be
    measured on THIS file: the trim removes leading silence, so a track built on the raw take runs late against the mix."""
    work = Path(work)
    for name in (f"{line_id}.trimmed.wav", f"{line_id}.wav"):
        if (work / name).exists():
            return work / name
    return None


def cmd_visemes(paths, repo=REPO):
    """One viseme track per line spoken by a drawn character (the narrator has no mouth), measured on the take that is mixed. -> tracks written."""
    manifest = read_json(paths["manifest"])
    work = paths["work"]
    n = 0
    for m in manifest["lines"]:
        if not has_face(m["speaker"], repo):
            continue   # no body, no mouth; a track left from an earlier casting is never read (calm.lipsync_for reads the speaker from the script)
        wav = heard_take(work, m["id"])
        if wav is None:
            raise Fail("VOICE-VISEME", f"line {m['id']}: no take in {work}; voice first")
        fp, ver = latest_face(m["speaker"], repo)
        t = build_track(m, wav, read_json(fp), ver, repo)
        write_json(work / "visemes" / f"{m['id']}.json", t)
        n += 1
    return n


# ---------------------------------------------------------------- casting.md from casting.json
def render_casting_md(casting):
    L = ["# Casting: voices for " + casting["series"], "",
         f"Engine: {casting.get('engine', 'none')} (Chatterbox Multilingual, one reference clip per character). Voice names below: {casting['model']}. Status: {casting['status']}.", "",
         casting.get("retired_note", ""), "",
         f"Voice gender: {casting['voice_gender_source']}.", "",
         "| Character | Voice (Google's word) | Sex | Age | Timbre |", "|---|---|---|---|---|"]
    for k, c in casting["characters"].items():
        L.append(f"| {k} | {c['voice']} ({c['voice_character']}) | {c['sex']} | {c['age']} | {c['timbre']} |")
    L += ["", "## Why, and the accent", ""]
    for k, c in casting["characters"].items():
        L += [f"- **{k}**: {c['reason']} Accent: {c['accent']}."]
    if any("pace" in c for c in casting["characters"].values()):
        L += ["", "## Pace per character (dialogue gate VOICE-PACE)", "", casting.get("pace_note", ""), "",
              "| Character | Pace | Band (wpm) | Chatterbox cfg_weight / exaggeration | Source |", "|---|---|---|---|---|"]
        for k, c in casting["characters"].items():
            pc = c.get("pace")
            if pc:
                cb = pc["chatterbox"]
                L.append(f"| {k} | {pc['label']} | {pc['band_wpm'][0]}-{pc['band_wpm'][1]} | {cb['cfg_weight']} / {cb['exaggeration']} | {pc['source']} |")
    if any("reference" in c for c in casting["characters"].values()):
        L += ["", "## Reference clip per character (CC0, still to be chosen)", "",
              "| Character | Sex | Age | Accent region wanted | Clip | Fallback if no clip exists |", "|---|---|---|---|---|---|"]
        for k, c in casting["characters"].items():
            r = c.get("reference", {})
            L.append(f"| {k} | {c['sex']} | {r.get('age_range', c['age'])} | {r.get('accent_region', '')} | {r.get('clip') or 'not chosen'} | {r.get('fallback', '')} |")
    chosen = [(k, c["reference"]) for k, c in casting["characters"].items() if (c.get("reference") or {}).get("measured")]
    if chosen:
        L += ["", "## Chosen reference clips and measured voices (CC0, REF-QUALITY enforced)", "",
              "Source for every clip: Mozilla Common Voice corpus 19.0 (CC0-1.0) via the public ungated mirror `fsicoli/common_voice_19_0`; provenance and hashes tracked in `bible/series/series/voices/provenance/*.json` (the clips stay in git-ignored `work/tts-refs/`). "
              "Pitch and centroid: `work/tts-refs/_tools/measure.py`; floor, crest and the rest: `uv run tools/voice.py refcheck`.", "",
              "| Character | Clip language | Sex | Age band | Pitch (Hz) | Centroid (Hz) | SNR (dB) | Floor (dBFS) | Crest (dB) | Length (s) | Fallback? |", "|---|---|---|---|---|---|---|---|---|---|---|"]
        for k, r in chosen:
            m, q = r["measured"], r.get("ref_quality") or {}
            L.append(f"| {k} | {r.get('clip_language', '')} | {r.get('clip_sex', '')} | {r.get('clip_age_band', '')} | {m['f0_median_hz']:.0f} | {m['spectral_centroid_hz']:.0f} | "
                     f"{m['snr_db']:.0f} | {q.get('floor_dbfs', '')} | {q.get('crest_db', '')} | {m['duration_s']} | {'yes' if r.get('fallback_used') else 'no'} |")
        order = sorted(chosen, key=lambda t: t[1]["measured"]["f0_median_hz"])
        L += ["", "Pitch order low to high: " + ", ".join(f"{k} {r['measured']['f0_median_hz']:.0f}" for k, r in order) + " Hz. " + casting.get("reference_note", ""), ""]
    L += ["", "## Styles allowed per emotion", "",
          "Only styles from `voice-styles.json`, chosen by `good_for` / `never_for`. The first listed is the default; a script line may name another listed one. `alert` is for `warning` lines, `data` for `figures` lines. Where no style fits an accent, the accent is carried in text.", "",
          "| Character | " + " | ".join(casting["emotions"]) + " |", "|---|" + "---|" * len(casting["emotions"])]
    for k, c in casting["characters"].items():
        L.append(f"| {k} | " + " | ".join(", ".join(c["styles"].get(e, [])) or "none" for e in casting["emotions"]) + " |")
    L += ["", "`none` means that emotion is not spoken by that character; the gate refuses a line that asks for it (write the beat in the picture or choose another emotion).", ""]
    return "\n".join(L)


# ---------------------------------------------------------------- cli
def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", choices=["casting", "manifest", "gate", "voice", "visemes", "trim", "measure", "status", "repair", "refcheck", "supersede", "retext", "refit-mark", "chatterbox-worker"])
    ap.add_argument("episode", nargs="?")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--engine", default=ENGINE)
    ap.add_argument("--go", action="store_true")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--work", default=None, help="take directory when it is not work/voice/<episode>")
    ap.add_argument("--series", default="series")
    ap.add_argument("--reason", default="")
    ap.add_argument("--baseline", default=None, help="retext: the manifest as it was when the old takes were voiced (takes made before tts_sha256 was logged)")
    ap.add_argument("--speaker", default="")
    ap.add_argument("--old", default="", help="refit-mark: the line id that was too long (its take stays, unused)")
    ap.add_argument("--new", default="", help="refit-mark: the new line id the writer gave the shorter wording")
    ap.add_argument("--role", default="dialogue", choices=["narrator", "dialogue"], help="trim: which mastering variant")
    ap.add_argument("--no-master", action="store_true", help="trim: end-trim only, no mastering chain")
    a = ap.parse_args(argv)
    try:
        if a.stage == "casting":
            c = read_json(casting_path(a.series))
            bad = casting_ref_problems(c)
            for cid, msg in bad:
                print(f"FAIL [{cid}] {msg}")
            if bad:
                return 1
            p = casting_path(a.series).with_name("casting.md")
            p.write_text(render_casting_md(c), encoding="utf-8")
            print(f"wrote {p}")
            return 0
        if a.stage == "chatterbox-worker":
            return chatterbox_worker(a.episode)
        if a.stage == "refcheck":
            if not a.episode:
                print("usage: refcheck <ref.wav> [provenance.json]", file=sys.stderr)
                return 2
            prof, bad = check_reference_quality(a.episode, a.out)
            if a.out and Path(a.out).exists():
                ban = banned_reason({}, read_json(a.out), load_banned())
                if ban:
                    bad = [ban] + bad
            print(json.dumps(prof))
            for msg in bad:
                print(f"FAIL [REF-QUALITY] {msg}")
            print("OK reference is clean enough" if not bad else f"{len(bad)} finding(s)")
            return 1 if bad else 0
        if a.stage == "trim":
            if not (a.episode and a.out):
                print("usage: trim <in.wav> <out.wav> [--role narrator|dialogue] [--no-master]", file=sys.stderr)
                return 2
            if Path(a.episode).resolve() == Path(a.out).resolve():
                print("refused: the output would overwrite the raw take", file=sys.stderr)
                return 2
            print(json.dumps(cmd_trim(a.episode, a.out, master=False if a.no_master else None, role=a.role), ensure_ascii=False))
            return 0
        if not a.episode:
            print("episode directory required", file=sys.stderr)
            return 2
        if a.stage == "measure":
            done = cmd_measure(a.episode, a.work)
            print(f"measured {len(done)} line(s): {', '.join(done)}")
            return 0
        if a.stage == "status":
            for n, st in cmd_status(a.episode):
                print(f"{n}: {st}")
            return 0
        if a.stage == "repair":
            if not a.reason:
                print("usage: repair <work-dir> --reason '<error that stopped the load>'", file=sys.stderr)
                return 2
            done = cmd_repair(a.episode, a.reason)
            print(f"marked not-taken: {', '.join(done) or 'none'}")
            return 0
        paths = episode_paths(a.episode)
        if a.work:
            paths["work"] = Path(a.work)
        elif a.stage == "gate" and (paths["dir"] / "take").is_dir():
            paths["work"] = paths["dir"] / "take"
        if a.stage == "manifest":
            script = load_script(paths)
            casting, reg = load_casting(script), load_registry()
            m = build_manifest(script, casting, reg)
            m["script_sha256"] = sha(paths["script"].read_bytes())
            write_json(paths["manifest"], m)
            print(f"wrote {paths['manifest']} ({len(m['lines'])} lines)")
            return 0
        if a.stage == "gate":
            fails = cmd_gate(paths, a.full)
            for cid, msg in fails:
                print(f"FAIL [{cid}] {msg}")
            print("OK gate passed" if not fails else f"{len(fails)} finding(s)")
            return 1 if fails else 0
        if a.stage == "voice":
            return cmd_voice(paths, a.go, engine=a.engine)
        if a.stage == "supersede":
            if not a.speaker or not a.reason:
                print("usage: supersede <episode-dir> --speaker <id> --reason '<why>'", file=sys.stderr)
                return 2
            print(f"superseded takes of {a.speaker}: {', '.join(cmd_supersede(paths, a.speaker, a.reason)) or 'none'}")
            return 0
        if a.stage == "retext":
            if not a.reason:
                print("usage: retext <episode-dir> --reason '<why>' [--baseline <manifest-before.json>]", file=sys.stderr)
                return 2
            mv, same, unk = cmd_retext(paths, a.reason, a.baseline)
            print(f"new text, old take set aside: {', '.join(mv) or 'none'} | unchanged, take kept: {', '.join(same) or 'none'}" + (f" | unknown (left alone): {', '.join(unk)}" if unk else ""))
            return 0
        if a.stage == "refit-mark":
            if not (a.old and a.new and a.reason):
                print("usage: refit-mark <episode-dir> --old H01 --new H01r1 --reason '<why>'", file=sys.stderr)
                return 2
            print(f"refit: {a.old} -> {cmd_refit_mark(paths, a.old, a.new, a.reason)} (voice --go voices only the new id)")
            return 0
        if a.stage == "visemes":
            print(f"wrote {cmd_visemes(paths)} viseme tracks")
            return 0
    except Fail as e:
        print(e)
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
