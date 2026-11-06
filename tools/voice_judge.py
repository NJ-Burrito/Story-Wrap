"""Narrator voice search, chief judge (owner, 2026-10-26: a male MSA radio-broadcaster narrator, صوت إذاعي).

Deterministic, no model listens (R-446, R-459). Three steps, each leaves a file the next one reads:

  refs  <scout_root> <judge_dir>   merge every scout's candidates.jsonl, licence tiers, EDGE FIX (strip exact-zero and
                                   sub-floor edges that MP3 decode/padding leaves, never the inside), re-measure with the
                                   repo's own functions (voice.ref_profile / ref_quality_problems, ref_audit.f0_stats method,
                                   voice_master.measure), score by RUBRIC_REF, shortlist 10 -> refs-scored.json, plan.json,
                                   refs/<key>.wav (the fixed clips that are cloned)
  run   (engine venv)              python tools/voice_trial_narrator.py run chatterbox <judge_dir>/plan.json
                                   (one model load, one take per line and voice, seeds from the ids, no re-voice)
  takes <judge_dir>                end-trim + mastering chain (voice.cmd_trim, role narrator), measure each take
                                   (VOICE-MASTER metrics and gate, TAKE-QUALITY, VOICE-TAIL, F0, sibilance, and the
                                   noise-only lead-in / tail window), score by RUBRIC_TAKE, joined clip per voice,
                                   ranking.json (all rows + rubric) and top3.json
  page  <judge_dir> <index.html>   the "Narrator search" block at the top of the Cast voices tab

uv run --with numpy --with scipy --with soundfile --with librosa python tools/voice_judge.py <cmd> ...
"""
from __future__ import annotations

import hashlib
import html
import json
import math
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import voice as V  # noqa: E402

MAIN = Path(r"<repo>")
LINES = ("L01", "L02", "L03", "L10", "L16")
MANIFEST = HERE.parent / "bible/series/series/episodes/E01/calm/narration-manifest.json"
SETTINGS = {"exaggeration": 0.30, "cfg_weight": 0.30, "temperature": 0.70}   # round 2 (d2) grave settings, the same for every voice
SHORTLIST_N = 10
EDGE_FLOOR_DBFS = V.REFQ["min_floor_dbfs"]   # -75: below this an edge frame is digital silence, not a microphone (REF-QUALITY's own line)


def read_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def write_json(p, obj):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(p) + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def sha_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def lin(v, lo, hi):
    """0 at lo, 1 at hi (either direction), clamped."""
    if v is None:
        return 0.0
    t = (v - lo) / (hi - lo)
    return max(0.0, min(1.0, t))


def band(v, full_lo, full_hi, zero_lo, zero_hi):
    """1 inside [full_lo, full_hi], falling linearly to 0 at zero_lo / zero_hi."""
    if v is None:
        return 0.0
    if full_lo <= v <= full_hi:
        return 1.0
    if v < full_lo:
        return lin(v, zero_lo, full_lo)
    return lin(v, zero_hi, full_hi)


# ------------------------------------------------------------------ licence tiers (written, deterministic, by source family)
TIER_RULES = [
    # (tier, test on the row, reason). First match wins. A = clean and castable today (voice.py LICENSES: CC0-1.0, PUBLIC-DOMAIN);
    # B = allowed licence but the speaker's consent is not documented by the source, or share-alike on the voice (VOICE-DATA §3), ranked BELOW A;
    # X = banned (identifiable public figure, broadcast/PA, commercial course tape, lecturer who is not the uploader).
    ("X", lambda r: r["speaker_id"] in ("s11-riad-esmat", "s11-riadismat"), "voice named by the source as a known public figure (رياض عصمت); R-451 bans identifiable public figures"),
    ("X", lambda r: r["speaker_id"] == "s16-08-emna-mizouni", "identifiable public figure (named activist); R-451"),
    ("X", lambda r: r["speaker_id"] == "s18-fs-588639", "airline PA announcement recorded on a flight: broadcast-like, the crew speaker never consented"),
    ("X", lambda r: r["speaker_id"] in ("s16-04-learn-tape", "s16-06-nama-lesson1"), "a commercial course tape / programme uploaded by a third party: unclear licence"),
    ("X", lambda r: r["speaker_id"] in ("s16-20-ahmedalnassri-lecture", "s16-21-docmohamed-lecture"), "lecture where the lecturer is presumed not the uploader: unclear licence"),
    ("A", lambda r: "Common Voice" in r["source_name"] and r["licence"].replace(" ", "-").upper().startswith("CC0"), "Mozilla Common Voice, CC0-1.0 volunteer donation"),
    ("A", lambda r: "librivox" in str(r["source_url"]).lower() and "ClArTTS" not in r["source_name"], "LibriVox, public domain (LibriVox publishes every recording PD)"),
    ("B", lambda r: "SA" in r["licence"].upper().replace("-", " ").split(), "share-alike licence on the voice (VOICE-DATA §3 bans it; not castable without the owner's decision)"),
    ("B", lambda r: True, "licence allows it but the speaker's consent is not documented by the source (or not castable by voice.py LICENSES today)"),
]


def tier_of(r):
    for t, test, why in TIER_RULES:
        try:
            if test(r):
                return t, why
        except Exception:
            continue
    return "X", "no rule"


REJECTED_SOURCES = {   # every narrator the owner has rejected so far (round 2: d1-d4, the d2 pick, 2026-10-26) and the banned voice
    "tabaialistibdad_00_": "d2 (rejected 2026-10-26)", "tabaialistibdad_05_": "d1 (rejected)", "tabaialistibdad_09_": "d3 (rejected)",
    "kalilawadimna_24_": "d4 (rejected)", "common_voice_ar_21519152": "banned narrator-cv-ar-21519152"}


def cv_ids(r):
    return sorted(set(re.findall(r"common_voice_ar_\d+", json.dumps(r, ensure_ascii=False))))


def vote_info(r):
    """Common Voice votes when the scout recorded them; else the split (test/dev/train hold only validated clips)."""
    ups, downs = [], []
    for c in r.get("source_clips") or []:
        if isinstance(c, dict) and "up" in c:
            ups.append(int(c.get("up", 0)))
            downs.append(int(c.get("down", 0)))
    if ups:
        ok = min(ups) >= V.REFQ["min_up_votes"] and max(downs) <= V.REFQ["max_down_votes"]
        return {"basis": "votes recorded", "up_min": min(ups), "down_max": max(downs), "pass": ok}
    if "Common Voice" in r["source_name"]:
        return {"basis": "CV split (validated clips only); per-clip votes not recorded by the scout", "pass": None}
    return {"basis": "no votes (published audiobook or upload)", "pass": None}


def speaker_key(r):
    """One key per real speaker across scouts: Common Voice client-id prefix (8 hex), one key for single-speaker corpora,
    the LibriVox reader slug, else the scout's speaker id."""
    if "Common Voice" in r["source_name"]:
        for t in (r.get("client_id"), r.get("client_id_prefix"), r["speaker_id"]):
            m = re.findall(r"[0-9a-f]{8,}", str(t or ""))
            if m:
                return "cv:" + max(m, key=len)[:8]
    if "NightPrince" in r["source_name"]:
        return "corpus:nightprince"
    if "librivox" in str(r["source_url"]).lower() and "ClArTTS" not in r["source_name"]:
        return "lv:" + r["speaker_id"].split("-")[-1].lower()
    return "id:" + r["speaker_id"]


def clip_abspath(r, scout_dir):
    cp = r.get("clip_path") or ""
    if not cp:
        return None
    p = Path(cp)
    if p.is_absolute():
        return p
    if cp.replace("\\", "/").startswith("work/"):
        return MAIN / cp
    return scout_dir / cp


# ------------------------------------------------------------------ edge fix and measurement
def edge_fix(x, rate):
    """Strip leading/trailing exact zeros, then leading/trailing 10 ms frames under EDGE_FLOOR_DBFS. Inside untouched.
    -> (floats, record)."""
    n = len(x)
    a, b = 0, n
    while a < b and x[a] == 0.0:
        a += 1
    while b > a and x[b - 1] == 0.0:
        b -= 1
    z_lead, z_tail = a, n - b
    hop = max(1, int(rate * 0.010))

    def lvl(s, e):
        seg = x[s:e]
        return 20 * math.log10(max(1e-9, math.sqrt(sum(v * v for v in seg) / max(1, len(seg)))))
    while b - a > hop and lvl(a, a + hop) < EDGE_FLOOR_DBFS:
        a += hop
    while b - a > hop and lvl(b - hop, b) < EDGE_FLOOR_DBFS:
        b -= hop
    y = x[a:b]
    return y, {"cut_lead_ms": round(a * 1000 / rate), "cut_tail_ms": round((n - b) * 1000 / rate),
               "zero_lead_ms": round(z_lead * 1000 / rate), "zero_tail_ms": round(z_tail * 1000 / rate),
               "seconds_before": round(n / rate, 2), "seconds_after": round(len(y) / rate, 2)}


def f0_ext(y, sr):
    """ref_audit.f0_stats' method (librosa pyin 60-450 Hz on a 16 kHz copy) plus the pyin-floor share and the frame-to-frame step."""
    import numpy as np
    import librosa
    y = np.asarray(y, dtype="float32")
    if sr != 16000:
        y = librosa.resample(y, orig_sr=sr, target_sr=16000)
    f0, vflag, _ = librosa.pyin(y, fmin=60, fmax=450, sr=16000, frame_length=1024, hop_length=160)
    v = f0[~np.isnan(f0)]
    out = {"voiced_frac": round(float(np.mean(~np.isnan(f0))), 3), "_f0": f0}
    if len(v) < 10:
        out.update(f0_median_hz=None)
        return out
    st = 12 * np.log2(v / np.median(v))
    steps = []
    for i in range(1, len(f0)):
        if not (np.isnan(f0[i]) or np.isnan(f0[i - 1])):
            steps.append(abs(12 * math.log2(f0[i] / f0[i - 1])))
    out.update(f0_median_hz=round(float(np.median(v)), 1),
               f0_p10_p90_hz=[round(float(np.percentile(v, 10)), 1), round(float(np.percentile(v, 90)), 1)],
               f0_sd_semitones=round(float(st.std()), 2),
               f0_iqr_semitones=round(float(np.percentile(st, 75) - np.percentile(st, 25)), 2),
               f0_floor_share=round(float(np.mean(v < 66.0)), 3),      # pyin pinned at its 60 Hz floor = an artefact, not a voice
               f0_octave_jumps=int(sum(1 for s in steps if s > 9.0)),
               f0_step_st=round(float(np.median(steps)), 3) if steps else None)
    return out


def measure_ref(x, rate):
    import voice_master as VM
    prof = V.ref_profile(list(x), rate)
    bad = V.ref_quality_problems(prof, None)
    vm = VM.measure(x, rate)
    f0 = f0_ext(x, rate)
    f0.pop("_f0", None)
    return {"refq": prof, "refq_problems": bad, "refq_pass": not bad,
            "tone": {k: vm[k] for k in ("tilt_db_per_oct", "mud_rel_db", "presence_rel_db", "sibilance_db", "lufs", "true_peak_dbtp")},
            "f0": f0, "rate": rate}


# ------------------------------------------------------------------ rubric
RUBRIC_REF = {
    "what": "reference score 0-100, broadcaster target: deep natural male, steady but not monotone, clean studio, dry, full band, warm",
    "gates_before_score": ["licence tier A first, B below A, X excluded", "male by F0 (median under 165 Hz) and not a rejected narrator",
                           "duplicate Common Voice clips merged (first scout kept)", "REF-QUALITY (after the edge fix) pass ranks above fail"],
    "pitch_20": "median F0: full 90-115 Hz, 0 at 75 and 150 Hz; x0 if pyin floor share > 0.15 (artefact, not a voice)",
    "steady_8": "F0 sd: full 1.8-3.5 semitones (calm, not monotone), 0 at 0.8 and 5.5",
    "smooth_7": "median frame-to-frame F0 step: full <= 0.15 st, 0 at 0.6 st; -2 per octave jump (max -6)",
    "snr_20": "REF-QUALITY SNR: 0 at 35 dB, full at 50 dB (only counts with a real floor, -75 to -53 dBFS)",
    "dry_15": "decay20 (reverb proxy): full <= 0.06 s, 0 at 0.15 s",
    "band_10": "energy > 8 kHz re 0.1-1 kHz: full >= -38 dB, 0 at -58 dB",
    "warm_10": "centroid full 450-750 Hz (0 at 400 / 1100); 60% of it, plus 40% from tilt full -9 to -5 dB/oct (0 at -14 / -2)",
    "crest_5": "full 20-26 dB, 0 at 18 / 30",
    "voiced_5": "voiced share full 0.45-0.75, 0 at 0.25 / 0.9",
}


def score_ref(m):
    f, q, t = m["f0"], m["refq"], m["tone"]
    s = {}
    pitch = band(f.get("f0_median_hz"), 90, 115, 75, 150) * 20
    if (f.get("f0_floor_share") or 0) > 0.15:
        pitch = 0.0
    s["pitch"] = pitch
    s["steady"] = band(f.get("f0_sd_semitones"), 1.8, 3.5, 0.8, 5.5) * 8
    s["smooth"] = max(0.0, lin(f.get("f0_step_st"), 0.6, 0.15) * 7 - min(6, 2 * (f.get("f0_octave_jumps") or 0)))
    real_floor = -75 <= q["floor_dbfs"] <= -53
    s["snr"] = lin(q["snr_db"], 35, 50) * 20 if real_floor else 0.0
    s["dry"] = lin(q["decay20_s"] if q["decay20_s"] is not None else 0.15, 0.15, 0.06) * 15
    s["band"] = lin(q["top_db"], -58, -38) * 10
    s["warm"] = (0.6 * band(q["centroid_hz"], 450, 750, 400, 1100) + 0.4 * band(t["tilt_db_per_oct"], -9, -5, -14, -2)) * 10
    s["crest"] = band(q["crest_db"], 20, 26, 18, 30) * 5
    s["voiced"] = band(f.get("voiced_frac"), 0.45, 0.75, 0.25, 0.9) * 5
    s = {k: round(v, 2) for k, v in s.items()}
    return round(sum(s.values()), 2), s


def _measure_job(job):
    import numpy as np
    try:
        x, rate = V.read_float(job["clip"])
        x = np.asarray(x, dtype="float64")
        y, er = edge_fix(list(x), rate)
        y = np.asarray(y, dtype="float64")
        if len(y) < rate:
            return {**job, "error": "under 1 s after the edge fix"}
        before = V.ref_profile(list(x), rate)
        m = measure_ref(y, rate)
        m["edge_fix"] = er
        m["refq_before_fix"] = {"problems": V.ref_quality_problems(before, None), "zero_frac": before["zero_frac"],
                                "snr_db": before["snr_db"], "floor_dbfs": before["floor_dbfs"]}
        return {**job, **m}
    except Exception as e:  # recorded, never hidden
        return {**job, "error": f"{type(e).__name__}: {e}"[:300]}


def cmd_refs(scout_root, judge):
    from concurrent.futures import ProcessPoolExecutor
    scout_root, judge = Path(scout_root), Path(judge)
    rows, seen_cv, dupes = [], {}, []
    scouts = sorted(p for p in scout_root.glob("s[0-9][0-9]") if p.is_dir())
    for sd in scouts:
        f = sd / "candidates.jsonl"
        if not f.exists():
            continue
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines()):
            if not line.strip():
                continue
            r = json.loads(line)
            key = f"{sd.name}:{r['speaker_id']}:{i}"
            ids = cv_ids(r)
            dup = next((seen_cv[c] for c in ids if c in seen_cv), None)
            tier, why = tier_of(r)
            rej = next((v for k, v in REJECTED_SOURCES.items() if k in json.dumps(r, ensure_ascii=False)), None)
            clip = clip_abspath(r, sd)
            row = {"key": key, "scout": sd.name, "speaker_id": r["speaker_id"], "source_name": r["source_name"],
                   "source_url": r.get("source_file_url") or r["source_url"], "licence": r["licence"], "licence_url": r["licence_url"],
                   "consent_basis": r["consent_basis"], "gender_label": r.get("gender"), "tier": tier, "tier_reason": why,
                   "votes": vote_info(r), "cv_clip_ids": ids, "transcript": r.get("transcript"),
                   "clip": str(clip) if clip else None, "rejected_before": rej, "duplicate_of": dup, "speaker_key": speaker_key(r)}
            for c in ids:
                seen_cv.setdefault(c, key)
            rows.append(row)
    jobs = [r for r in rows if r["clip"] and Path(r["clip"]).exists() and not r["duplicate_of"]]
    missing = [r["key"] for r in rows if not (r["clip"] and Path(r["clip"]).exists())]
    workers = int(os.environ.get("JUDGE_WORKERS", "4"))          # spare the CPU (CLAUDE.md hardware rule): 4 of 12 threads
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=workers) as ex:
        done = list(ex.map(_measure_job, jobs, chunksize=2))
    by = {d["key"]: d for d in done}
    out = []
    for r in rows:
        d = by.get(r["key"], r)
        if "refq" in d:
            sc, parts = score_ref(d)
            d["ref_score"], d["ref_parts"] = sc, parts
            f0 = d["f0"].get("f0_median_hz")
            d["male_by_f0"] = f0 is not None and f0 < 165 and (d["f0"].get("f0_floor_share") or 0) <= 0.5
        out.append(d)

    def eligible(d):
        return "refq" in d and d["tier"] in ("A", "B") and d["male_by_f0"] and not d["rejected_before"] and not d["duplicate_of"]
    rank_key = lambda d: ({"A": 0, "B": 1}[d["tier"]], not d["refq_pass"], -d["ref_score"])
    best = {}
    for d in sorted([d for d in out if "refq" in d and not d["duplicate_of"]], key=lambda d: (d["tier"] == "X", rank_key(d) if d["tier"] != "X" else (9, 1, 0))):
        if d["speaker_key"] in best:
            d["same_speaker_as"] = best[d["speaker_key"]]       # one speaker, several clips: only the best clip of each speaker competes
        else:
            best[d["speaker_key"]] = d["key"]
    ranked = sorted([d for d in out if eligible(d) and not d.get("same_speaker_as")], key=rank_key)
    for i, d in enumerate(ranked):
        d["ref_rank"] = i + 1
    short = ranked[:SHORTLIST_N]
    refdir = judge / "refs"
    refdir.mkdir(parents=True, exist_ok=True)
    voices = []
    for i, d in enumerate(short):
        vid = f"j{i + 1:02d}"
        x, rate = V.read_float(d["clip"])
        y, _ = edge_fix(x, rate)
        dst = refdir / f"{vid}.wav"
        V.write_wav16(dst, y, rate)
        import numpy as np
        xx, rr = V.read_float(dst)
        d["as_cloned"] = measure_ref(np.asarray(xx, dtype="float64"), rr)
        d["as_cloned"]["sha256"] = sha_file(dst)
        d["vid"] = vid
        voices.append({"id": vid, "method": "chatterbox", "label": vid, "sex": "male", "ref": str(dst).replace("\\", "/"), "ref_text": "",
                       "reference_note": f"{d['source_name']} | {d['speaker_id']} | {d['licence']}", "settings": SETTINGS})
    man = read_json(MANIFEST)
    lines = [{"id": l["id"], "text": l["text"], "tts_text": l["tts_text"]} for l in man["lines"] if l["id"] in LINES]
    plan = {"out_dir": str(judge / "audio").replace("\\", "/"), "lines": lines, "voices": voices,
            "settings": SETTINGS, "source_manifest": str(MANIFEST.relative_to(HERE.parent)).replace("\\", "/")}
    write_json(judge / "plan.json", plan)
    summ = {"generated": time.strftime("%Y-%m-%d %H:%M:%S"), "scouts_read": [s.name for s in scouts],
            "scouts_with_rows": sorted({r["scout"] for r in rows}), "rows": len(rows), "duplicates": sum(1 for r in rows if r["duplicate_of"]),
            "missing_clip": missing, "measured": len(done), "distinct_speakers_measured": len({d["speaker_key"] for d in done if "refq" in d}), "errors": [d["key"] + ": " + d["error"] for d in done if "error" in d],
            "eligible": len(ranked), "measure_wall_s": round(time.time() - t0, 1),
            "tiers": {t: sum(1 for r in rows if r["tier"] == t) for t in "ABX"},
            "refq_pass_before_fix": sum(1 for d in done if "refq" in d and not d["refq_before_fix"]["problems"]),
            "refq_pass_after_fix": sum(1 for d in done if d.get("refq_pass")),
            "rubric_ref": RUBRIC_REF, "tier_rules": [(t, w) for t, _, w in TIER_RULES], "rejected_sources": REJECTED_SOURCES,
            "shortlist": [d["vid"] + " = " + d["key"] for d in short]}
    write_json(judge / "refs-scored.json", {"summary": summ, "rows": out})
    print(json.dumps({k: v for k, v in summ.items() if k not in ("rubric_ref", "tier_rules")}, ensure_ascii=False, indent=1))
    return 0


# ------------------------------------------------------------------ takes
EDGE_ACTIVE_BELOW_P95_DB = 50.0   # a frame counts as sound (not silence) if within 50 dB of the loud part ...
EDGE_ACTIVE_MIN_DBFS = -70.0      # ... and above -70 dBFS
LEAD_ALLOW_S = 0.12               # an unvoiced first consonant (ت) before the first voiced frame is speech, not noise
TAIL_ALLOW_S = 0.25               # a final unvoiced sound (the ة read as h) plus the 100 ms hang-over and the fade


def noise_edges(x, rate, f0):
    """Noise-only lead-in and tail: sound before the first voiced frame and after the last one, beyond the allowances.
    Voiced = pyin found F0 (10 ms hop on a 16 kHz copy) on a frame within 30 dB of the loud part. -> dict."""
    import numpy as np
    import voice_master as VM
    M = VM.load_profile()["voice"]["measure"]
    db, hop, win = VM.frame_db(np.asarray(x, dtype="float64"), rate, M)
    p95 = float(np.percentile(db, 95))
    act = np.nonzero((db >= p95 - EDGE_ACTIVE_BELOW_P95_DB) & (db > EDGE_ACTIVE_MIN_DBFS))[0]
    nf = min(len(db), len(f0))
    voiced = [i for i in range(nf) if not np.isnan(f0[i]) and db[i] >= p95 - V.SPEECH_BELOW_PEAK_DB]
    if not len(act) or not voiced:
        return {"lead_noise_s": None, "tail_noise_s": None, "note": "no voiced speech found"}
    t = lambda i: i * hop / rate

    def win_db(i0, i1):
        if i1 <= i0:
            return None
        seg = np.asarray(x[int(t(i0) * rate):int(t(i1) * rate)], dtype="float64")
        return round(float(20 * np.log10(max(1e-9, np.sqrt(np.mean(seg ** 2)))) - p95), 1) if len(seg) else None
    a0, v0, v1, a1 = int(act[0]), voiced[0], voiced[-1], int(act[-1])
    lead_win = max(0.0, t(v0) - t(a0))
    tail_win = max(0.0, t(a1) - t(v1))
    return {"lead_window_s": round(lead_win, 3), "lead_noise_s": round(max(0.0, lead_win - LEAD_ALLOW_S), 3),
            "lead_rel_db": win_db(a0, v0), "tail_window_s": round(tail_win, 3), "tail_noise_s": round(max(0.0, tail_win - TAIL_ALLOW_S), 3),
            "tail_rel_db": win_db(v1 + 1, a1 + 1), "first_sound_s": round(t(a0), 3), "first_voiced_s": round(t(v0), 3),
            "last_voiced_s": round(t(v1), 3), "last_sound_s": round(t(a1), 3)}


RUBRIC_TAKE = {
    "what": "take score 0-100 over the 5 mastered takes (what the owner hears)",
    "edge_noise_25": "per take: (lead_noise_s + tail_noise_s) / 0.4 s, capped at 1, times audibility (window level re loud part: 0 at -55 dB, 1 at -35 dB); 25 x (1 - mean over takes)",
    "flags_20": "20 - 5 per take with any TAKE-QUALITY, VOICE-MASTER or VOICE-TAIL problem (min 0)",
    "pitch_20": "median of the takes' F0 medians: full 90-115 Hz, 0 at 75 / 150; x0 if pyin floor share > 0.15",
    "natural_10": "median F0 sd per take: full 1.8-3.5 st, 0 at 0.8 / 5.5",
    "clean_10": "median VOICE-MASTER snr (noise under the voice) 0 at 40 dB, full at 60 dB; takes with no measurable floor count as 50",
    "stable_5": "spread of the 5 take F0 medians (sd in semitones): full <= 0.5, 0 at 2.0 (the clone holds one voice)",
    "warm_5": "median take centroid (voice.py measure): full 450-800 Hz, 0 at 380 / 1200",
    "sibilance_5": "median sibilance: full <= -24 dB, 0 at the VOICE-MASTER limit -14 dB",
    "final": "0.4 x reference score + 0.6 x take score; tier A always above tier B",
}


def score_takes(takes):
    import statistics as S
    s = {}
    pen = []
    for tk in takes:
        e = tk["edges"]
        tot = (e.get("lead_noise_s") or 0) + (e.get("tail_noise_s") or 0)
        lv = [v for v, n in ((e.get("lead_rel_db"), e.get("lead_noise_s")), (e.get("tail_rel_db"), e.get("tail_noise_s"))) if n and v is not None]
        aud = lin(max(lv), -55, -35) if lv else 0.0
        pen.append(min(1.0, tot / 0.4) * aud)
    s["edge_noise"] = 25 * (1 - sum(pen) / len(pen))
    flagged = sum(1 for tk in takes if tk["problems"])
    s["flags"] = max(0, 20 - 5 * flagged)
    f0s = [tk["f0"]["f0_median_hz"] for tk in takes if tk["f0"].get("f0_median_hz")]
    med = S.median(f0s) if f0s else None
    floor = max((tk["f0"].get("f0_floor_share") or 0) for tk in takes)
    s["pitch"] = 0.0 if floor > 0.15 else band(med, 90, 115, 75, 150) * 20
    s["natural"] = band(S.median([tk["f0"].get("f0_sd_semitones") or 0 for tk in takes]), 1.8, 3.5, 0.8, 5.5) * 10
    snr = S.median([tk["master"]["snr_db"] if tk["master"]["snr_db"] is not None else 50 for tk in takes])
    s["clean"] = lin(snr, 40, 60) * 10
    spread = (S.pstdev([12 * math.log2(f / med) for f in f0s]) if len(f0s) > 1 else 0) if med else 9
    s["stable"] = lin(spread, 2.0, 0.5) * 5
    s["warm"] = band(S.median([tk["takeq"]["centroid_hz"] for tk in takes]), 450, 800, 380, 1200) * 5
    s["sibilance"] = lin(S.median([tk["master"]["sibilance_db"] for tk in takes]), -14, -24) * 5
    s = {k: round(v, 2) for k, v in s.items()}
    summ = {"f0_median_hz": med, "f0_spread_st": round(spread, 2), "snr_db_median": snr, "flagged_takes": flagged,
            "edge_noise_mean_penalty": round(sum(pen) / len(pen), 3),
            "lead_noise_s_total": round(sum(tk["edges"].get("lead_noise_s") or 0 for tk in takes), 3),
            "tail_noise_s_total": round(sum(tk["edges"].get("tail_noise_s") or 0 for tk in takes), 3)}
    return round(sum(s.values()), 2), s, summ


def ffmpeg_lufs(path):
    r = subprocess.run(["ffmpeg", "-nostats", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    m = re.search(r"I:\s+(-?[\d.]+) LUFS", r.stderr.split("Summary:")[-1])
    return float(m.group(1)) if m else None


def cmd_takes(judge):
    import numpy as np
    import voice_master as VM
    judge = Path(judge)
    plan = read_json(judge / "plan.json")
    refs = read_json(judge / "refs-scored.json")
    run = read_json(Path(plan["out_dir"]) / "run-chatterbox.json")
    role = VM.role_of("narrator")
    gap = Path(plan["out_dir"]) / "gap.wav"
    V.write_wav16(gap, [0.0] * int(24000 * 0.7), 24000)
    rows = {d.get("vid"): d for d in refs["rows"] if d.get("vid")}
    voices = []
    for v in plan["voices"]:
        vid = v["id"]
        rv = run["voices"].get(vid) or {}
        vdir = Path(plan["out_dir"]) / f"chatterbox-{vid}"
        takes, errs = [], []
        for pl in rv.get("lines", []):
            if "error" in pl:
                errs.append(f"{pl['id']}: {pl['error']}")
                continue
            raw = vdir / pl["file"]
            dst = vdir / f"{pl['id']}.wav"
            xr, sr = V.read_float(raw)
            f0r = f0_ext(xr, sr)
            raw_edges = noise_edges(xr, sr, f0r.pop("_f0"))
            info = V.cmd_trim(raw, dst, role=role)                 # the end-trim + mastering chain, voice.py's own path
            x, sr = V.read_float(dst)
            xa = np.asarray(x, dtype="float64")
            met = VM.measure(xa, sr)
            tp = V.take_profile(x, sr)
            f0 = f0_ext(x, sr)
            edges = noise_edges(x, sr, f0.pop("_f0"))
            probs = [f"TAKE-QUALITY: {p}" for p in V.take_quality_problems(tp)] + \
                    [f"{c}: {m}" for c, m in VM.gate_problems(met, role)] + \
                    [f"{c}: {m}" for c, m in V.tail_problems(x, sr, info)] + \
                    [f"MASTER-CONTRACT: {m}" for m in (info.get("master") or {}).get("contract", [])]
            takes.append({"id": pl["id"], "file": str(dst), "seed": pl.get("seed"), "gen_wall_s": pl.get("wall_s"),
                          "raw_s": round(len(xr) / sr, 2), "audio_s": round(len(x) / sr, 2),
                          "trim": {k: info[k] for k in ("cut_start_ms", "cut_end_ms", "edge_db_rel", "clipped_end", "dropped_runs")},
                          "master": {k: met[k] for k in ("lufs", "true_peak_dbtp", "snr_db", "noise_floor_dbfs", "pause_rel_db", "sibilance_db",
                                                         "tilt_db_per_oct", "mud_rel_db", "presence_rel_db", "zero_runs")},
                          "takeq": tp, "f0": f0, "edges": edges, "raw_edges": raw_edges, "problems": probs})
        entry = {"vid": vid, "ref_key": rows[vid]["key"], "errors": errs, "takes": takes}
        if len(takes) == len(LINES):
            sc, parts, summ = score_takes(takes)
            entry.update(take_score=sc, take_parts=parts, take_summary=summ)
            lst = vdir / "join.txt"
            items = []
            for i, tk in enumerate(takes):
                items += [f"file '{Path(tk['file']).as_posix()}'"] + ([f"file '{gap.as_posix()}'"] if i < len(takes) - 1 else [])
            lst.write_text("\n".join(items), encoding="utf-8")
            joined = vdir / "joined.wav"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-ar", "24000",
                            "-c:a", "pcm_s16le", str(joined)], check=True)
            entry["joined"] = {"file": str(joined), "lufs": ffmpeg_lufs(joined), "seconds": round(V.wav_seconds(joined), 2)}
        else:
            entry.update(take_score=0.0, take_parts={}, take_summary={"note": "a take is missing: scored 0, never re-voiced"})
        r = rows[vid]
        entry["ref_score"] = r["ref_score"]
        entry["tier"] = r["tier"]
        entry["final_score"] = round(0.4 * r["ref_score"] + 0.6 * entry["take_score"], 2)
        voices.append(entry)
    voices.sort(key=lambda e: ({"A": 0, "B": 1}[e["tier"]], -e["final_score"]))
    for i, e in enumerate(voices):
        e["final_rank"] = i + 1
    summ = refs["summary"]
    ranking = {"generated": time.strftime("%Y-%m-%d %H:%M:%S"), "judge": "deterministic rubric, no model listened; the judge cannot hear",
               "engine": "chatterbox-multilingual (local GPU, one load, one take per line and voice, seeds from the ids)", "settings": plan["settings"],
               "lines": [l["id"] for l in plan["lines"]], "rubric_ref": RUBRIC_REF, "rubric_take": RUBRIC_TAKE,
               "edge_noise_definition": {"active_below_p95_db": EDGE_ACTIVE_BELOW_P95_DB, "active_min_dbfs": EDGE_ACTIVE_MIN_DBFS,
                                         "lead_allow_s": LEAD_ALLOW_S, "tail_allow_s": TAIL_ALLOW_S},
               "tier_rules": summ["tier_rules"], "summary": {k: v for k, v in summ.items() if k not in ("rubric_ref", "tier_rules")},
               "tested": voices, "all_rows": refs["rows"]}
    write_json(judge / "ranking.json", ranking)
    top = []
    for e in voices[:3]:
        r = rows[e["vid"]]
        top.append({"rank": e["final_rank"], "vid": e["vid"], "speaker_id": r["speaker_id"], "scout": r["scout"],
                    "source_name": r["source_name"], "source_url": r["source_url"], "licence": r["licence"], "licence_url": r["licence_url"],
                    "consent_basis": r["consent_basis"], "tier": r["tier"], "tier_reason": r["tier_reason"], "votes": r["votes"],
                    "cv_clip_ids": r["cv_clip_ids"], "reference_clip": plan["voices"][int(e["vid"][1:]) - 1]["ref"],
                    "reference_sha256": r["as_cloned"]["sha256"], "edge_fix": r["edge_fix"],
                    "ref_metrics": {"f0": r["as_cloned"]["f0"], "refq": r["as_cloned"]["refq"], "refq_problems": r["as_cloned"]["refq_problems"],
                                    "tone": r["as_cloned"]["tone"]},
                    "ref_score": e["ref_score"], "ref_parts": r["ref_parts"], "take_score": e["take_score"], "take_parts": e["take_parts"],
                    "take_summary": e["take_summary"], "final_score": e["final_score"], "settings": plan["settings"],
                    "takes": [{"id": t["id"], "file": t["file"], "seconds": t["audio_s"], "f0_hz": t["f0"].get("f0_median_hz"),
                               "lufs": t["master"]["lufs"], "snr_db": t["master"]["snr_db"], "sibilance_db": t["master"]["sibilance_db"],
                               "lead_noise_s": t["edges"].get("lead_noise_s"), "tail_noise_s": t["edges"].get("tail_noise_s"),
                               "problems": t["problems"]} for t in e["takes"]],
                    "joined": e.get("joined"), "reasons": reasons(e, r)})
    write_json(judge / "top3.json", {"generated": ranking["generated"], "of_n_measured": summ["distinct_speakers_measured"], "clips_measured": summ["measured"], "scouts": len(summ["scouts_read"]),
                                     "note": "numbers are not ears (R-459): the owner's ear decides; the judge cannot listen", "top3": top})
    for e in voices:
        print(e["final_rank"], e["vid"], e["tier"], e["final_score"], e["ref_score"], e["take_score"], e.get("take_summary"))
    return 0


def reasons(e, r):
    f = r["as_cloned"]["f0"]
    q = r["as_cloned"]["refq"]
    ts = e["take_summary"]
    out = [f"reference F0 {f.get('f0_median_hz')} Hz (sd {f.get('f0_sd_semitones')} st), SNR {q['snr_db']} dB over a real floor of {q['floor_dbfs']} dBFS, "
           f"decay20 {q['decay20_s']} s, >8 kHz {q['top_db']} dB, centroid {q['centroid_hz']} Hz",
           f"takes: F0 {ts.get('f0_median_hz')} Hz, spread {ts.get('f0_spread_st')} st, {ts.get('flagged_takes')} flagged take(s), "
           f"noise-only lead-in {ts.get('lead_noise_s_total')} s and tail {ts.get('tail_noise_s_total')} s over 5 takes",
           f"licence tier {r['tier']}: {r['tier_reason']}"]
    if r["refq_problems"]:
        out.append("REF-QUALITY after the edge fix still fails: " + "; ".join(r["refq_problems"]))
    return out


# ------------------------------------------------------------------ page block
def rel(p, page=None):
    """Audio lives in the MAIN checkout's git-ignored work/; the page is served from MAIN/previews after the merge."""
    return os.path.relpath(Path(p), MAIN / "previews").replace("\\", "/")


def cmd_page(judge, page):
    judge, page = Path(judge), Path(page)
    t3 = read_json(judge / "top3.json")
    n, ns = t3["of_n_measured"], t3["scouts"]
    medal = ["🥇", "🥈", "🥉"]
    said = {l["id"]: l["text"] for l in read_json(judge / "plan.json")["lines"]}     # the visible text, without tashkeel
    cards = []
    for i, v in enumerate(t3["top3"]):
        rm, ts = v["ref_metrics"], v["take_summary"]
        lines = "".join(
            f'<div class="njs-line"><span>{html.escape(t["id"])} · {t["seconds"]} s</span><audio controls preload="none" src="{rel(t["file"], page)}"></audio></div>'
            f'<p class="njs-ar ar" dir="rtl" lang="ar">{html.escape(said.get(t["id"], ""))}</p>'
            for t in v["takes"])
        why = "".join(f"<li>{html.escape(x)}</li>" for x in v["reasons"])
        cards.append(f'''<div class="njs-card">
<h3>{medal[i]} #{v["rank"]} · {html.escape(v["vid"])} · {html.escape(v["speaker_id"])}</h3>
<p class="njs-src">📚 {html.escape(v["source_name"])} · <a href="{html.escape(v["licence_url"])}" target="_blank">{html.escape(v["licence"])}</a> · <a href="{html.escape(str(v["source_url"]).split(" ")[0])}" target="_blank">source</a> · tier {v["tier"]}</p>
<div class="njs-line"><span>🎧 reference</span><audio controls preload="none" src="{rel(v["reference_clip"], page)}"></audio></div>
<div class="njs-line njs-join"><span>▶️ all 5 lines</span><audio controls preload="none" src="{rel(v["joined"]["file"], page)}"></audio></div>
{lines}
<p class="njs-num">📏 F0 {ts.get("f0_median_hz")} Hz · ref SNR {rm["refq"]["snr_db"]} dB · reverb {rm["refq"]["decay20_s"]} s · noisy edges {round((ts.get("lead_noise_s_total") or 0) + (ts.get("tail_noise_s_total") or 0), 2)} s · score {v["final_score"]}</p>
<details><summary>🧭 why it ranked</summary><ul>{why}</ul></details>
<p class="njs-pick">👉 Pick this one: tell Claude «{html.escape(v["vid"])}».</p>
</div>''')
    block = f'''<!-- narrator-search:start -->
<section class="njs" id="narrator-search">
<style>
.njs{{margin:0 0 26px;padding:18px;border:2px solid var(--ink-acc);border-radius:16px;background:var(--card)}}
.njs h2{{font-family:"thmanyahserifdisplay",serif;margin:0 0 4px;font-size:clamp(24px,4vw,34px)}}
.njs .njs-sub{{color:var(--soft);margin:0 0 12px}}
.njs-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}}
@media (max-width:1100px){{.njs-grid{{grid-template-columns:1fr}}}}
.njs-card{{border:1px solid var(--line);border-radius:14px;padding:14px;background:var(--bg)}}
.njs-card h3{{font-family:"thmanyahserifdisplay",serif;margin:0 0 4px;font-size:1.15rem}}
.njs-src,.njs-num{{color:var(--soft);font-size:.88rem;margin:4px 0}}
.njs-line{{display:flex;align-items:center;gap:8px;margin:4px 0;font-size:.9rem}}
.njs-line span{{min-width:100px}}
.njs-line audio{{flex:1;min-width:0}}
.njs-join span{{font-weight:700}}
.njs-pick{{margin:10px 0 0;font-weight:700}}
.njs details{{font-size:.88rem;margin-top:6px}}
.njs-ar{{font-family:"thmanyahseriftext",serif;margin:0 0 6px;font-size:1rem;color:var(--soft)}}
</style>
<h2>🎙️ Narrator search: top 3 of {n} voices</h2>
<p class="njs-sub">🔎 {n} voices measured from {ns} sources · 🎯 radio-broadcaster target: deep, warm, calm, clean · 🤖 picked by numbers only: no model listened, your ear decides · ⏱️ {html.escape(t3["generated"][11:19])}</p>
<div class="njs-grid">
{"".join(cards)}
</div>
</section>
<!-- narrator-search:end -->'''
    text = page.read_text(encoding="utf-8")
    text = re.sub(r"<!-- narrator-search:start -->.*?<!-- narrator-search:end -->\n?", "", text, flags=re.S)
    m = re.search(r'<section class="panel" id="panel-castvoices"[^>]*>\s*<main class="wrap">', text)
    if not m:
        raise SystemExit("no Cast voices tab (id=panel-castvoices) found in the page")
    text = text[:m.end()] + "\n" + block + "\n" + text[m.end():]
    page.write_text(text, encoding="utf-8")
    print("page block written; audio files:", 3 * 7)
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["refs"]:
        sys.exit(cmd_refs(a[1], a[2]))
    if a[:1] == ["takes"]:
        sys.exit(cmd_takes(a[1]))
    if a[:1] == ["page"]:
        sys.exit(cmd_page(a[1], a[2]))
    print(__doc__)
