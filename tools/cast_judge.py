"""Cast voices, chief casting judge (owner, 2026-10-26 night: "top 3 + the current reference per character, I pick by ear").

Deterministic, no model listens (R-446, R-459). Reuses the narrator judge (tools/voice_judge.py: edge fix, F0, noise
window, take rubric) and the production take path (voice.py chatterbox_worker with the EOS guard and per-line token cap,
voice.cmd_trim = word-safe edge cleaner + mastering chain). casting.json is read, never written.

  refs  <judge_dir>    per character: the scout's 8 shortlisted clips + the current casting reference; clean data tier,
                       votes, REF-QUALITY re-checked on the clip as cloned (edge fix, word-safe edge clean, no pads, gentle
                       high-pass, one gain to -23 LUFS; the current reference is cloned exactly as cast), scored by the
                       character's OWN frozen rubric (work/cast-scout/<char>/rubric*.json) -> 4 best + current = 5 voices
                       -> refs.json, plan.json, worker-job.json, refs/<vid>.wav
  run   <judge_dir>    the Chatterbox worker in the engine venv: one model load, 105 takes in sequence, one take per line
  takes <judge_dir>    edge clean + mastering per take, measures (VOICE-MASTER, VOICE-EDGE-NOISE, TAKE-QUALITY, VOICE-TAIL,
                       F0, SNR, noise-only lead/tail), take score, final = 0.4 ref + 0.6 take, joined clip -> ranking.json
  page  <judge_dir> <index.html>   the "Cast voices: pick one per character" block at the top of the Cast voices tab
  verify <judge_dir> <index.html>  every audio src on the block exists and decodes (ffmpeg)

uv run --with numpy --with scipy --with soundfile --with librosa python tools/cast_judge.py <cmd> ...
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
import voice_judge as J  # noqa: E402

MAIN = Path(r"<repo>")
SCOUT = MAIN / "work" / "cast-scout"
SERIES = HERE.parent / "bible" / "series" / "series"
CASTING = SERIES / "voices" / "casting.json"
CHARS = ("hero", "extra", "han", "rival", "lead", "partner", "guide")
N_NEW = 4                    # voiced per character besides the current reference
N_TOP = 3                    # shown to the owner besides the current reference
REF_LUFS = -23.0
TASHKEEL = re.compile("[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed]")

# ------------------------------------------------------------------ the lines (same 3 for every voice of one character)
# E01 lines come from the episode manifests (tts_text = the TTS input with tashkeel); the others are the character's own
# sample lines from voice.md, copied verbatim (they carry tashkeel; the page shows them without it).
E01 = SERIES / "episodes" / "E01" / "narration-manifest.json"
E01C = SERIES / "episodes" / "E01" / "calm" / "narration-manifest.json"
BIBLE_LINES = {
    "extra": [("A02", "calm", "voice.md §7 #2", "للسِّجِلّ: الشيءُ في مكانِه، والرّفُّ مُرقَّم، وأنا شاهدة."),
                ("A08", "disgust", "voice.md §7 #8", "رفٌّ بلا رقم؟ هذا ليسَ رفًّا. هذا نِسيان."),
                ("A13", "fear", "voice.md §7 #13", "للسِّجِلّ. كلُّ شيءٍ معي. كلُّ شيء.")],
    "han": [("H01", "calm", "voice.md §8 #1", "البحرُ هادئٌ اليوم. نَفَسٌ طويل، وننزل."),
            ("H07", "sadness", "voice.md §8 #7", "الماءُ يأخذُ ولا يعتذر. وأنا مثلُه."),
            ("H12", "surprise", "voice.md §8 #12", "آيغو! من أين جاء هذا؟ لا تقلْ لي. ضعْه أمامي.")],
    "rival": [("D02", "calm", "voice.md §7 #2", "لن أضعَها أرضًا حتّى تمسكَها يدُ صاحبِها."),
             ("D05", "joy", "voice.md §7 #5", "وصلَت اليد! انظري، يا أناك، كيف عرفَتْها قبلَ أن تراها."),
             ("D11", "fear", "voice.md §7 #11", "لا، لا. ليس هنا. هنا ينزلُ الماء.")],
    "partner": [("I01", "calm", "voice.md §8 #1", "خُذْ. ليس لي. الشايُ للبرد. أنتَ أبردُ منّي."),
             ("I05", "fear", "voice.md §8 #5", "كويدادو! لا تمسكي. اتركي. اتركي!"),
             ("I08", "anger", "voice.md §8 #8", "الورقةُ تقول حادث. الورقةُ لم ترَ. أنا رأيت.")],
    "lead": [("E14", "calm", "E01C calm L14", None),
              ("E03", "calm", "voice.md §7 #3", "الزّنبركُ لا يحبُّ العجلة. لفّةٌ، ثمّ نفَسٌ، ثمّ لفّة."),
              ("E07", "sadness", "voice.md §7 #7", "لا. لا بأس. أعودُ غدًا في التّاسعة.")],
}
E01_LINES = {"hero": ("L01", "L04", "L11"), "guide": ("L02", "L03", "L05")}
GLOSSARY = SERIES / "glossary.json"      # the series glossary (tools/gloss.py validates it): word -> meaning_ar


def gloss_map():
    return {e["word"]: e["meaning_ar"] for e in json.loads(GLOSSARY.read_text(encoding="utf-8"))["entries"] if e.get("word") and e.get("meaning_ar")}

# ------------------------------------------------------------------ who they are (casting briefs, plainly; the owner's E01C note)
WHO = {   # neutral example briefs; a real project writes its own from its character bible
    "hero": {"ar": "هدى", "origin": "a young woman from a port city", "origin_ar": "من مدينة ساحلية", "age": 19, "accent": "clean MSA reference",
             "voice": "young woman, mid and narrow pitch, quick but precise, quiet when angry"},
    "extra": {"ar": "ياسمينة", "origin": "a woman who learned Arabic by recitation", "origin_ar": "تعلمت العربية بالتلاوة", "age": 34, "accent": "clean formal Arabic reference",
              "voice": "woman, low-mid, level, slow and exact, never raised, very clean"},
    "han": {"ar": "نادية", "origin": "an old diver, decades in the port", "origin_ar": "غواصة مسنة", "age": 72, "accent": "older woman's voice, any clean source",
            "voice": "old woman, low and weathered, even, few words, unhurried"},
    "rival": {"ar": "رامز", "origin": "a seafarer, now a courier", "origin_ar": "بحار قديم", "age": 45, "accent": "accented reference",
              "voice": "man, warm mid baritone, easy sway, smiling, unhurried"},
    "lead": {"ar": "إدريس", "origin": "a clockmaker's son and former sailor", "origin_ar": "ابن صانع ساعات", "age": 67, "accent": "calm older reference",
             "voice": "older man, courteous, very calm, level, slow, warm"},
    "partner": {"ar": "عيسى", "origin": "from a mining family of the highlands", "origin_ar": "من عائلة عمال مناجم", "age": 22, "accent": "low, level reference",
                "voice": "young man, low to mid, flat and level, quiet, breath before the line"},
    "guide": {"ar": "أنطوان", "origin": "a merchant family, third generation in the port", "origin_ar": "من عائلة تجار", "age": 61, "accent": "warm baritone reference",
              "voice": "man, warm baritone, quick exact patter, dry humour"},
}


def read_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


write_json = J.write_json
sha_file = J.sha_file


def visible(t):
    """What people read: no tashkeel (CLAUDE.md), foreign words glossed in Arabic (R gloss rule)."""
    t = TASHKEEL.sub("", t)
    for w, g in gloss_map().items():
        t = re.sub(rf"(?<![\u0621-\u064a]){w}(?![\u0621-\u064a])", f"{w} ({g})", t, count=1)
    return t


def lines_for(char):
    out = []
    if char in E01_LINES:
        man = {l["id"]: l for l in read_json(E01)["lines"]}
        for lid in E01_LINES[char]:
            l = man[lid]
            assert l["speaker"] == char, (char, lid)
            out.append({"id": lid, "emotion": l.get("emotion"), "source": f"E01 narration-manifest {lid}", "tts_text": l["tts_text"], "text": l["text"]})
        return out
    calm = {l["id"]: l for l in read_json(E01C)["lines"]}
    for lid, emo, src, tts in BIBLE_LINES[char]:
        if tts is None:
            l = calm["L14"]
            assert l["speaker"] == char
            tts = l["tts_text"]
        out.append({"id": lid, "emotion": emo, "source": src, "tts_text": tts, "text": TASHKEEL.sub("", tts)})
    return out


# ------------------------------------------------------------------ candidates
def rubric_of(char):
    d = SCOUT / char
    for n in (f"rubric.{char}.json", "rubric.json"):
        if (d / n).exists():
            return d / n, read_json(d / n)
    raise SystemExit(f"{char}: no rubric file")


def find_num(obj, key):
    """First numeric value for `key` anywhere in a nested dict/list (scout rows differ in shape)."""
    if isinstance(obj, dict):
        if key in obj and isinstance(obj[key], (int, float)) and not isinstance(obj[key], bool):
            return obj[key]
        for v in obj.values():
            r = find_num(v, key)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = find_num(v, key)
            if r is not None:
                return r
    return None


def clip_ids(obj):
    return sorted(set(re.findall(r"common_voice_[a-z]{2,3}_\d+", json.dumps(obj, ensure_ascii=False))))


def find_str(obj, keys):
    if isinstance(obj, dict):
        for k in keys:
            if isinstance(obj.get(k), str) and obj[k]:
                return obj[k]
        for v in obj.values():
            r = find_str(v, keys)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = find_str(v, keys)
            if r:
                return r
    return None


def votes_of(row):
    """Common Voice votes as the scout recorded them; a speaker built from several clips records the weakest clip
    (up_votes_min / down_votes_max)."""
    up = next((v for v in (find_num(row, k) for k in ("up_votes", "up_votes_min", "up")) if v is not None), None)
    dn = next((v for v in (find_num(row, k) for k in ("down_votes", "down_votes_max", "down")) if v is not None), None)
    return up, dn


def cand_rows(char):
    rows = []
    f = SCOUT / char / "candidates.jsonl"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return rows


META_KEYS = ("accent_points", "accent_fit", "age_mid_years", "age_mid", "age_fit", "lang_fit", "letters_per_s", "chars_per_s")
AGE_MID = {"teens": 16, "twenties": 25, "thirties": 35, "fourties": 45, "fifties": 55, "sixties": 65, "seventies": 75, "eighties": 85}


def current_meta(char, prov, rubric, clip_x, rate):
    """Metadata criteria for the current reference when no scout row carries them: from its provenance labels, by the
    rule the character's casting brief states (han age/accent; letters per speech second of the PUBLISHED transcript)."""
    out, notes = {}, []
    need = {c["metric"] for c in rubric["criteria"].values()}
    if "age_mid_years" in need or "age_mid" in need:
        a = AGE_MID.get(str(prov.get("speaker_age") or prov.get("age") or "").lower())
        out["age_mid_years"] = out["age_mid"] = a
        notes.append(f"age from provenance label {prov.get('speaker_age')}")
    if "accent_fit" in need:                       # han brief: ko 1.0, ja 0.7, other 0.2
        lang = str(prov.get("language") or "").lower()
        out["accent_fit"] = 1.0 if lang.startswith("korean") else 0.7 if lang.startswith("japanese") else 0.2
        notes.append(f"accent_fit from provenance language {lang[:20]!r}")
    if ("letters_per_s" in need or "chars_per_s" in need) and prov.get("transcript"):
        import numpy as np
        import voice_edges as VE
        s = VE.speech_span(np.asarray(clip_x, dtype="float64"), rate)
        span = max(0.1, s["offset_s"] - s["onset_s"])
        n = sum(1 for ch in prov["transcript"] if ch.isalpha())
        out["letters_per_s"] = out["chars_per_s"] = round(n / span, 2)
        notes.append(f"pace = {n} letters of the published transcript / {round(span, 2)} s speech span")
    return out, notes


def resample24(x, rate):
    import numpy as np
    if rate == 24000:
        return np.asarray(x, dtype="float64"), 24000
    from math import gcd
    from scipy.signal import resample_poly
    g = gcd(rate, 24000)
    return resample_poly(np.asarray(x, dtype="float64"), 24000 // g, rate // g), 24000


def prep_ref(x, rate, sex):
    """As the narrator judge cloned its 10 voices: the EDGE FIX only (exact-zero and sub-floor MP3 edges stripped, inside
    untouched). REF-QUALITY is calibrated on this input; measured 2026-10-27, the word-safe room-tone clean drops the edge
    frames the floor percentile is read from (han de-2c56: SNR 54.4 -> 34.7 dB with no change to the noise) and cut 2.2 s of
    one clip, so it is not used to judge. The room-tone clean (R-470) runs once at casting, on the clip the owner picks."""
    import numpy as np
    y, ef = J.edge_fix(list(x), rate)
    return np.asarray(y, dtype="float64"), {"edge_fix": ef, "note": "edge fix only (narrator-judge method); room-tone clean at casting"}


def rubric_score(metrics, rubric):
    """nj-narration scripts/voice_measure.py `score`, verbatim logic (imported there it would shadow tools/voice_edges)."""
    parts = {}
    for name, c in rubric["criteria"].items():
        v = metrics.get(c["metric"])
        r = J.band(v, *c["band"]) if "band" in c else J.lin(v, *c["lin"])
        if "require" in c:
            rv = metrics.get(c["require"]["metric"])
            lo, hi = c["require"]["between"]
            r = r if (rv is not None and lo <= rv <= hi) else 0.0
        z = c.get("zero_if")
        if z:
            zv = metrics.get(z["metric"]) or 0
            if ("gt" in z and zv > z["gt"]) or ("lt" in z and zv < z["lt"]):
                r = 0.0
        parts[name] = round(r * c["weight"], 2)
    return round(sum(parts.values()), 2), parts


def score_ref(meas, meta, rubric, scout_parts=None):
    """The character's own frozen rubric (voice_measure.py score form) on the clip as cloned: signal metrics re-measured
    here, metadata metrics (accent, age, pace) from the scout's row. Normalised to 0-100 by the rubric's total weight."""
    q, f = meas["refq"], meas["f0"]
    flat = {**q, **{k: v for k, v in f.items() if not k.startswith("_")}, "f0_sd_st": f.get("f0_sd_semitones"), **meta}
    s, parts = rubric_score(flat, rubric)
    for name, c in rubric["criteria"].items():          # a metadata criterion the scout scored but whose raw value it did not keep
        if c["metric"] in META_KEYS and meta.get(c["metric"]) is None and scout_parts and isinstance(scout_parts.get(name), (int, float)):
            parts[name] = round(min(c["weight"], float(scout_parts[name])), 2)
    s = sum(parts.values())
    tot = sum(c["weight"] for c in rubric["criteria"].values())
    return round(100 * s / tot, 2), parts


def cmd_refs(judge):
    import numpy as np
    judge = Path(judge)
    casting = read_json(CASTING)
    banned = V.load_banned(HERE.parent)
    out = {"generated": time.strftime("%Y-%m-%d %H:%M:%S"), "characters": {}}
    voices, plan_lines = [], {}
    for char in CHARS:
        rpath, rubric = rubric_of(char)
        sl = read_json(SCOUT / char / "shortlist.json")["shortlist"]
        crow = cand_rows(char)
        c = casting["characters"][char]
        ref = c["reference"]
        prov = read_json(HERE.parent / ref["provenance"])
        cur_ids = set(clip_ids({"a": ref.get("clip_source_id"), "b": prov.get("clip")}))
        sex = c["sex"]
        rows = []
        for r0 in sl:
            ids0 = set(clip_ids(r0))
            cand = next((x for x in crow if ids0 and set(clip_ids(x)) & ids0), None) or                 next((x for x in crow if x.get("speaker_id") and x.get("speaker_id") == r0.get("speaker_id")), None) or {}
            r = {**cand, **r0}                          # the scout's full measured row, the shortlist row on top
            cp = find_str(r0, ("clip_wav", "clip_path", "clip"))
            p = (SCOUT / char / cp) if cp and not Path(cp).is_absolute() else Path(cp or "")
            ids = clip_ids(r)
            up, dn = votes_of(r)
            lic = find_str(r, ("licence", "license")) or ""
            rows.append({"kind": "new", "scout_rank": r.get("rank"), "speaker": find_str(r, ("speaker_id", "speaker_key", "speaker")) or "?",
                         "clip_ids": ids, "clip": str(p), "licence": lic, "up": up, "down": dn, "row": r,
                         "language": find_str(r, ("language", "lang")), "age_label": find_str(r, ("age_band", "age_label", "age")),
                         "accent_label": find_str(r, ("accent_label", "accent")), "why_scout": r.get("why"),
                         "is_current": bool(set(ids) & cur_ids)})
        rows.append({"kind": "current", "scout_rank": None, "speaker": (prov.get("speaker_id_hashed") or "")[:12] or "current",
                     "clip_ids": sorted(cur_ids), "clip": str(MAIN / ref["clip"]), "licence": ref.get("license"),
                     "up": int(prov["up_votes"]) if str(prov.get("up_votes", "")).isdigit() else None,
                     "down": int(prov["down_votes"]) if str(prov.get("down_votes", "")).isdigit() else None,
                     "row": next((x for x in crow if set(clip_ids(x)) & cur_ids), None) or next((x for x in sl if set(clip_ids(x)) & cur_ids), None),
                     "language": ref.get("clip_language"), "age_label": ref.get("clip_age_band") or prov.get("speaker_age"),
                     "accent_label": prov.get("speaker_accent_tag") or None, "why_scout": None, "is_current": True})
        measured = []
        for r in rows:
            d = {k: v for k, v in r.items() if k != "row"}
            try:
                if not Path(r["clip"]).exists():
                    raise FileNotFoundError(r["clip"])
                x, rate = V.read_float(r["clip"])
                x, rate = resample24(x, rate)
                if r["kind"] == "current":
                    y, log = np.asarray(x, dtype="float64"), {"note": "the current casting reference, cloned exactly as cast (no new prep)"}
                else:
                    y, log = prep_ref(x, rate, sex)
                d["prep"] = log
                d["as_cloned"] = J.measure_ref(y, rate)
                meta = {k: find_num(r["row"], k) for k in META_KEYS} if r["row"] else {}
                meta = {k: v for k, v in meta.items() if v is not None}
                notes = []
                sp = next((r["row"][k] for k in ("score_parts", "rubric_parts", "rubric_scores") if r["row"] and isinstance(r["row"].get(k), dict)), None)
                if r["kind"] == "current" and not meta:
                    meta, notes = current_meta(char, prov, rubric, y, rate)
                d["meta"], d["meta_notes"] = meta, notes
                d["ref_score"], d["ref_parts"] = score_ref(d["as_cloned"], meta, rubric, sp)
                d["_y"] = y
            except Exception as e:                       # recorded, never hidden
                d["error"] = f"{type(e).__name__}: {e}"[:300]
            # clean-data tier (VOICE-DATA §3, voice.py LICENSES): CC0 Common Voice with >= 2 up / 0 down votes = A
            lic_ok = str(d["licence"]).replace(" ", "-").upper().startswith("CC0")
            votes_ok = d["up"] is not None and d["up"] >= V.REFQ["min_up_votes"] and (d["down"] or 0) <= V.REFQ["max_down_votes"]
            d["tier"] = "A" if lic_ok and votes_ok else "B" if lic_ok else "X"
            ban = next((b["id"] for b in banned if set(d["clip_ids"]) & set(b.get("clip_source_ids", []))), None)
            if ban:
                d["tier"], d["banned"] = "X", ban
            measured.append(d)
        cur = next(d for d in measured if d["kind"] == "current")
        pool = [d for d in measured if d["kind"] == "new" and not d["is_current"] and "error" not in d and d["tier"] == "A"]
        seen, uniq = set(), []
        for d in sorted(pool, key=lambda d: (not d["as_cloned"]["refq_pass"], -d["ref_score"])):
            if d["speaker"] in seen:
                continue
            seen.add(d["speaker"])
            uniq.append(d)
        pick = uniq[:N_NEW]
        refdir = judge / "refs"
        refdir.mkdir(parents=True, exist_ok=True)
        for i, d in enumerate(pick + [cur]):
            d["vid"] = f"{char}-cur" if d is cur else f"{char}-c{i + 1}"
            dst = refdir / f"{d['vid']}.wav"
            if "_y" in d:
                V.write_wav16(dst, [float(v) for v in d["_y"]], 24000)
                d["ref_wav"] = str(dst)
                d["ref_sha256"] = sha_file(dst)
                d["cast_sha256"] = sha_file(d["clip"]) if d is cur else None
        lines = lines_for(char)
        plan_lines[char] = lines
        for d in pick + [cur]:
            if "ref_wav" not in d:
                continue
            voices.append({"char": char, "vid": d["vid"], "current": d is cur, "ref": d["ref_wav"], "ref_sha256": d["ref_sha256"],
                           "cast_sha256": d.get("cast_sha256")})
        for d in measured:
            d.pop("_y", None)
        out["characters"][char] = {"rubric_file": str(rpath), "rubric": rubric, "lines": lines, "measured": measured,
                                   "picked": [d["vid"] for d in pick], "current": cur.get("vid"), "sex": sex,
                                   "pool_eligible": len(uniq)}
        print(char, "eligible", len(uniq), "picked", [(d["vid"], d["speaker"], d["ref_score"], d["as_cloned"]["refq_pass"]) for d in pick],
              "current", cur.get("ref_score"), cur.get("as_cloned", {}).get("refq_pass"), cur.get("error"))
    write_json(judge / "refs.json", out)
    # the worker job: voice.py chatterbox_worker (one load, EOS guard, per-line token cap, seeds from the line ids)
    settings = dict(V.CHATTERBOX_SETTINGS)
    jobs = []
    adir = judge / "audio"
    for v in voices:
        cs = V.character_settings(casting, v["char"])
        # a measured generation rate exists only for the current speaker AND its exact cast clip (take.gen_cap.voices)
        spk, sh = (v["char"], v["cast_sha256"]) if v["current"] else (None, None)
        for l in plan_lines[v["char"]]:
            jid = f"{v['vid']}-{l['id']}"
            (adir / v["vid"]).mkdir(parents=True, exist_ok=True)
            jobs.append({"id": jid, "char": v["char"], "vid": v["vid"], "line": l["id"], "text": l["tts_text"], "ref": v["ref"],
                         "out": str(adir / v["vid"] / f"{l['id']}.raw.wav"), "cap": V.token_cap(l["tts_text"], spk, sh),
                         "cap_rate": V.voice_rate(spk, sh)[1], "done_after_s": round(V.edge_done_after_s(l["tts_text"], spk, sh), 2),
                         "settings": cs})
    job = {"lines": jobs, "settings": settings, "result": str(judge / "worker-result.json"), "marks": str(judge / "worker-marks.jsonl"),
           "eos_after_complete_tokens": V.eos_after_complete_tokens()}
    write_json(judge / "worker-job.json", job)
    write_json(judge / "plan.json", {"voices": voices, "lines": plan_lines, "settings": settings,
                                     "character_settings": {c: V.character_settings(casting, c) for c in CHARS},
                                     "eos_after_complete_tokens": job["eos_after_complete_tokens"], "takes": len(jobs)})
    print("voices", len(voices), "takes", len(jobs))
    return 0


def cmd_run(judge):
    judge = Path(judge)
    py = MAIN / "work" / "tts-engines" / "chatterbox" / "Scripts" / "python.exe"
    env = dict(os.environ, PYTHONUTF8="1", HF_HOME=str(MAIN / "work" / "tts-engines" / "hf-cache"))
    with open(judge / "worker-stderr.log", "w", encoding="utf-8") as ef:
        r = subprocess.run([str(py), str(HERE / "voice.py"), "chatterbox-worker", str(judge / "worker-job.json")], env=env, stderr=ef)
    print("worker exit", r.returncode)
    return r.returncode


# ------------------------------------------------------------------ takes
def score_takes(takes, rubric):
    """voice_judge.RUBRIC_TAKE with the character's own pitch, movement and warmth bands (from its rubric)."""
    import statistics as S
    crit = rubric["criteria"]
    pb = crit["pitch"]["band"]
    sd = next(c for c in crit.values() if c["metric"] == "f0_sd_st")["band"]
    wb = next(c for c in crit.values() if c["metric"] == "centroid_hz")["band"]
    s, pen = {}, []
    for tk in takes:                 # VOICE-EDGE-NOISE's own detector (voice_edges, R-470): noise-only ms beyond the guards
        g = tk["edge_gate"]
        pen.append(min(1.0, (g["lead_noise_ms"] + g["tail_noise_ms"]) / 400.0))
    s["edge_noise"] = 25 * (1 - sum(pen) / len(pen))
    flagged = sum(1 for tk in takes if tk["problems"])
    s["flags"] = max(0, 20 - 5 * flagged)
    f0s = [tk["f0"]["f0_median_hz"] for tk in takes if tk["f0"].get("f0_median_hz")]
    med = S.median(f0s) if f0s else None
    floor = max((tk["f0"].get("f0_floor_share") or 0) for tk in takes)
    s["pitch"] = 0.0 if floor > 0.15 else J.band(med, *pb) * 20
    s["natural"] = J.band(S.median([tk["f0"].get("f0_sd_semitones") or 0 for tk in takes]), *sd) * 10
    snr = S.median([tk["master"]["snr_db"] if tk["master"]["snr_db"] is not None else 50 for tk in takes])
    s["clean"] = J.lin(snr, 40, 60) * 10
    spread = (S.pstdev([12 * math.log2(f / med) for f in f0s]) if len(f0s) > 1 else 0) if med else 9
    s["stable"] = J.lin(spread, 2.0, 0.5) * 5
    s["warm"] = J.band(S.median([tk["takeq"]["centroid_hz"] for tk in takes]), *wb) * 5
    s["sibilance"] = J.lin(S.median([tk["master"]["sibilance_db"] for tk in takes]), -14, -24) * 5
    s = {k: round(v, 2) for k, v in s.items()}
    summ = {"f0_median_hz": med, "f0_spread_st": round(spread, 2), "snr_db_median": snr, "flagged_takes": flagged,
            "lead_noise_s_total": round(sum(tk["edge_gate"]["lead_noise_ms"] for tk in takes) / 1000, 3),
            "tail_noise_s_total": round(sum(tk["edge_gate"]["tail_noise_ms"] for tk in takes) / 1000, 3),
            "pyin_unvoiced_edges_s_total": round(sum((tk["edges"].get("lead_noise_s") or 0) + (tk["edges"].get("tail_noise_s") or 0) for tk in takes), 3),
            "edge_gate_fails": sum(1 for tk in takes if any(p.startswith("VOICE-EDGE-NOISE") for p in tk["problems"]))}
    return round(sum(s.values()), 2), s, summ


RUBRIC_TAKE = {**J.RUBRIC_TAKE, "what": "take score 0-100 over the 3 mastered takes; pitch / natural / warm bands are the character's own rubric bands",
               "edge_noise_25": "per take: (lead + tail noise-only ms beyond the guards, VOICE-EDGE-NOISE's detector voice_edges.noise_edges) / 400 ms, capped at 1; "
                                "25 x (1 - mean). Changed from the narrator judge's pyin window: measured 2026-10-27 on these 105 takes, its 'noise' windows sat "
                                "-5 to -10 dB under the loudest speech, i.e. unvoiced or creaky speech pyin did not call voiced, not noise",
               "flags_20": "20 - 5 per take with any TAKE-QUALITY, VOICE-MASTER, VOICE-TAIL or VOICE-EDGE-NOISE problem (min 0)",
               "final": "0.4 x reference score (the character's own rubric) + 0.6 x take score; tier A always above tier B"}


def cmd_takes(judge):
    import numpy as np
    import voice_master as VM
    import voice_edges as VE
    judge = Path(judge)
    refs = read_json(judge / "refs.json")
    job = read_json(judge / "worker-job.json")
    res = read_json(judge / "worker-result.json") if (judge / "worker-result.json").exists() else {"lines": []}
    gen = {r["id"]: r for r in res["lines"]}
    gap = judge / "audio" / "gap.wav"
    V.write_wav16(gap, [0.0] * int(24000 * 0.7), 24000)
    by_vid = {}
    for j in job["lines"]:
        by_vid.setdefault(j["vid"], []).append(j)
    result = {"generated": time.strftime("%Y-%m-%d %H:%M:%S"), "judge": "deterministic rubric, no model listened; the judge cannot hear",
              "engine": "chatterbox-multilingual 0.1.7 (local GPU, one load, one take per line, seeds from the line ids, EOS guard, per-line token cap)",
              "settings": job["settings"], "eos_after_complete_tokens": job["eos_after_complete_tokens"], "rubric_take": RUBRIC_TAKE,
              "characters": {}}
    for char, cd in refs["characters"].items():
        rows = {d["vid"]: d for d in cd["measured"] if d.get("vid")}
        entries = []
        for vid, jl in by_vid.items():
            if not vid.startswith(char + "-"):
                continue
            takes, errs = [], []
            for j in jl:
                raw = Path(j["out"])
                if not raw.exists():
                    errs.append(f"{j['line']}: no raw take (worker did not reach it)")
                    continue
                dst = raw.with_name(f"{j['line']}.wav")
                xr, sr = V.read_float(raw)
                info = V.cmd_trim(raw, dst, role="dialogue", done_after_s=j["done_after_s"])   # edge clean + mastering chain
                x, sr = V.read_float(dst)
                xa = np.asarray(x, dtype="float64")
                met = VM.measure(xa, sr)
                tp = V.take_profile(x, sr)
                f0 = J.f0_ext(x, sr)
                edges = J.noise_edges(x, sr, f0.pop("_f0"))      # narrator-judge proxy, kept for the record only (see RUBRIC_TAKE)
                eg = VE.noise_edges(xa, sr)
                edge_gate = {k: eg[k] for k in ("lead_noise_ms", "tail_noise_ms", "onset_s", "offset_s")}
                probs = [f"TAKE-QUALITY: {p}" for p in V.take_quality_problems(tp)] + \
                        [f"{c}: {m}" for c, m in VM.gate_problems(met, "dialogue")] + \
                        [f"{c}: {m}" for c, m in V.tail_problems(x, sr, info)] + \
                        [f"VOICE-EDGE-NOISE: {m}" for m in VE.edge_problems(xa, sr)] + \
                        [f"MASTER-CONTRACT: {m}" for m in (info.get("master") or {}).get("contract", [])]
                takes.append({"id": j["line"], "file": str(dst), "raw": str(raw), "raw_s": round(len(xr) / sr, 2), "audio_s": round(len(x) / sr, 2),
                              "gen_s": (gen.get(j["id"]) or {}).get("gen_s"), "cap_tokens": j["cap"], "cap_s": round(j["cap"] / 25, 2),
                              "ran_to_cap": len(xr) / sr >= j["cap"] / 25 - 0.12,
                              "trim": {k: info.get(k) for k in ("cut_start_ms", "cut_end_ms", "clipped_end")},
                              "master": {k: met[k] for k in ("lufs", "true_peak_dbtp", "snr_db", "noise_floor_dbfs", "sibilance_db", "zero_runs")},
                              "takeq": tp, "f0": f0, "edges": edges, "edge_gate": edge_gate, "problems": probs})
            e = {"vid": vid, "current": vid.endswith("-cur"), "errors": errs, "takes": takes}
            if len(takes) == len(jl):
                sc, parts, summ = score_takes(takes, cd["rubric"])
                e.update(take_score=sc, take_parts=parts, take_summary=summ)
                lst = judge / "audio" / vid / "join.txt"
                items = []
                for i, tk in enumerate(takes):
                    items += [f"file '{Path(tk['file']).as_posix()}'"] + ([f"file '{gap.as_posix()}'"] if i < len(takes) - 1 else [])
                lst.write_text("\n".join(items), encoding="utf-8")
                joined = judge / "audio" / vid / "joined.wav"
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-ar", "24000",
                                "-c:a", "pcm_s16le", str(joined)], check=True)
                e["joined"] = {"file": str(joined), "lufs": J.ffmpeg_lufs(joined), "seconds": round(V.wav_seconds(joined), 2)}
            else:
                e.update(take_score=0.0, take_parts={}, take_summary={"note": "a take is missing: scored 0, never re-voiced"})
            r = rows[vid]
            e["ref_score"], e["tier"] = r["ref_score"], r["tier"]
            e["final_score"] = round(0.4 * r["ref_score"] + 0.6 * e["take_score"], 2)
            entries.append(e)
        new = sorted([e for e in entries if not e["current"]], key=lambda e: ({"A": 0, "B": 1}.get(e["tier"], 2), -e["final_score"]))
        for i, e in enumerate(new):
            e["final_rank"] = i + 1
        cur = next((e for e in entries if e["current"]), None)
        result["characters"][char] = {"ranked": new, "current": cur, "top": [e["vid"] for e in new[:N_TOP]]}
        print(char, [(e["vid"], e["final_score"], e["ref_score"], e["take_score"], e["take_summary"].get("flagged_takes")) for e in new],
              "cur", cur and (cur["final_score"], cur["ref_score"], cur["take_score"]))
    write_json(judge / "ranking.json", result)
    return 0


def reasons(e, r):
    q, f = r["as_cloned"]["refq"], r["as_cloned"]["f0"]
    ts = e["take_summary"]
    out = [f"reference: F0 {f.get('f0_median_hz')} Hz (sd {f.get('f0_sd_semitones')} st), SNR {q['snr_db']} dB over a floor of {q['floor_dbfs']} dBFS, "
           f"reverb {q['decay20_s']} s, centroid {q['centroid_hz']} Hz; own-rubric score {r['ref_score']}",
           f"takes: F0 {ts.get('f0_median_hz')} Hz, spread {ts.get('f0_spread_st')} st, SNR {ts.get('snr_db_median')} dB, "
           f"{ts.get('flagged_takes')} flagged take(s), noise-only lead {ts.get('lead_noise_s_total')} s / tail {ts.get('tail_noise_s_total')} s over 3 takes; take score {e['take_score']}",
           f"labels (source metadata, not heard): {r.get('language') or '?'}, {r.get('age_label') or '?'}, accent {r.get('accent_label') or 'none'}; "
           f"licence {r['licence']}, tier {r['tier']}, votes {r.get('up')} up / {r.get('down')} down"]
    if r["as_cloned"]["refq_problems"]:
        out.append("REF-QUALITY on the clip as cloned fails: " + "; ".join(r["as_cloned"]["refq_problems"]))
    probs = sorted({p.split(":")[0] for tk in e["takes"] for p in tk["problems"]})
    if probs:
        out.append("take gates flagged: " + ", ".join(probs))
    return out


# ------------------------------------------------------------------ page
def rel(p):
    """Audio lives in the MAIN checkout's git-ignored work/; the page is served from MAIN/previews after the merge."""
    return os.path.relpath(Path(p), MAIN / "previews").replace("\\", "/")


def src_link(r):
    ids = r.get("clip_ids") or []
    lang = (re.findall(r"common_voice_([a-z]{2,3})_", ids[0]) or ["?"])[0] if ids else "?"
    return f"https://huggingface.co/datasets/fsicoli/common_voice_19_0/tree/main/audio/{lang}", (ids[0] if ids else "clip")


def cmd_page(judge, page):
    judge, page = Path(judge), Path(page)
    refs = read_json(judge / "refs.json")
    rk = read_json(judge / "ranking.json")
    medal = ["🥇", "🥈", "🥉"]
    secs, n_audio = [], 0
    for char in CHARS:
        cd, rc = refs["characters"][char], rk["characters"][char]
        rows = {d["vid"]: d for d in cd["measured"] if d.get("vid")}
        said = {l["id"]: visible(l["text"]) for l in cd["lines"]}
        w = WHO[char]
        cards = []
        show = [(i, e) for i, e in enumerate(rc["ranked"][:N_TOP])] + ([(None, rc["current"])] if rc["current"] else [])
        for i, e in show:
            r = rows[e["vid"]]
            url, cid = src_link(r)
            ts = e["take_summary"]
            tag = "🔁 current" if e["current"] else f"{medal[i]} #{i + 1}"
            lines = "".join(
                f'<div class="cj-line"><span>{html.escape(t["id"])} · {t["audio_s"]} s</span><audio controls preload="none" src="{rel(t["file"])}"></audio></div>'
                f'<p class="cj-ar" dir="rtl" lang="ar">{html.escape(said.get(t["id"], ""))}</p>' for t in e["takes"])
            n_audio += len(e["takes"]) + 1 + (1 if e.get("joined") else 0)
            joined = (f'<div class="cj-line cj-join"><span>▶️ all 3 lines</span><audio controls preload="none" src="{rel(e["joined"]["file"])}"></audio></div>'
                      if e.get("joined") else '<p class="cj-warn">⚠️ a take is missing: no joined clip</p>')
            why = "".join(f"<li>{html.escape(x)}</li>" for x in reasons(e, r))
            noisy = round((ts.get("lead_noise_s_total") or 0) + (ts.get("tail_noise_s_total") or 0), 2)
            cards.append(f'''<div class="cj-card{' cj-cur' if e['current'] else ''}">
<label class="cj-pick"><input type="radio" name="cj-{char}" value="{html.escape(e['vid'])}"> <b>{tag} · {html.escape(e["vid"])}</b></label>
<p class="cj-src">📚 Common Voice 19.0 · <a href="{url}" target="_blank" rel="noopener">{html.escape(cid)}</a> · <a href="https://creativecommons.org/publicdomain/zero/1.0/" target="_blank" rel="noopener">{html.escape(str(r["licence"]))}</a> · tier {r["tier"]} · 🗣️ {html.escape(str(r.get("language") or "?"))}, {html.escape(str(r.get("age_label") or "?"))}</p>
<div class="cj-line"><span>🎧 reference</span><audio controls preload="none" src="{rel(r["ref_wav"])}"></audio></div>
{joined}
{lines}
<p class="cj-num">📏 F0 {ts.get("f0_median_hz")} Hz · SNR {ts.get("snr_db_median")} dB · noisy edges {noisy} s · flagged {ts.get("flagged_takes")}/3 · ref {e["ref_score"]} · takes {e["take_score"]} · <b>score {e["final_score"]}</b></p>
<details><summary>🧭 why it ranked here</summary><ul>{why}</ul></details>
</div>''')
        secs.append(f'''<section class="cj-char" id="cj-{char}">
<h3>{html.escape(w["ar"])} · {char.capitalize()} <span class="cj-picked" data-char="{char}"></span></h3>
<p class="cj-who">🌍 <b>Origin: {html.escape(w["origin"])}</b> <span class="cj-ar-in" dir="rtl" lang="ar">({html.escape(w["origin_ar"])})</span></p>
<p class="cj-who">🎂 {w["age"]} · 🗣️ {html.escape(w["accent"])} · 🎙️ {html.escape(w["voice"])}</p>
<div class="cj-grid">{"".join(cards)}</div>
</section>''')
    stamp = rk["generated"][11:19]
    block = f'''<!-- cast-judge:start -->
<section class="cj" id="cast-judge">
<style>
.cj{{margin:0 0 26px;padding:18px;border:2px solid var(--ink-acc);border-radius:16px;background:var(--card)}}
.cj h2{{font-family:"thmanyahserifdisplay",serif;margin:0 0 4px;font-size:clamp(24px,4vw,34px)}}
.cj h3{{font-family:"thmanyahserifdisplay",serif;margin:18px 0 4px;font-size:1.35rem}}
.cj .cj-sub,.cj-who{{color:var(--soft);margin:2px 0}}
.cj-note{{margin:10px 0;padding:10px 12px;border-radius:12px;border:1px dashed var(--ink-acc)}}
.cj-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:8px}}
@media (max-width:1300px){{.cj-grid{{grid-template-columns:repeat(2,1fr)}}}}
@media (max-width:760px){{.cj-grid{{grid-template-columns:1fr}}}}
.cj-card{{border:1px solid var(--line);border-radius:14px;padding:12px;background:var(--bg)}}
.cj-cur{{border-style:dashed;opacity:.92}}
.cj-pick{{display:block;font-family:"thmanyahsans",sans-serif;cursor:pointer;margin-bottom:4px}}
.cj-src,.cj-num{{color:var(--soft);font-size:.86rem;margin:4px 0}}
.cj-line{{display:flex;align-items:center;gap:8px;margin:4px 0;font-size:.88rem}}
.cj-line span{{min-width:92px}}
.cj-line audio{{flex:1;min-width:0}}
.cj-join span{{font-weight:700}}
.cj-ar,.cj-ar-in{{font-family:"thmanyahseriftext",serif;color:var(--soft)}}
.cj-ar{{margin:0 0 6px;font-size:1rem}}
.cj details{{font-size:.86rem;margin-top:6px}}
.cj-bar{{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:12px 0 0}}
.cj-bar button{{font:inherit;padding:8px 14px;border-radius:10px;border:2px solid var(--ink-acc);background:var(--bg);cursor:pointer}}
.cj-picked{{font-size:.9rem;color:var(--soft);font-family:"thmanyahsans",sans-serif}}
.cj-warn{{color:#b44}}
#cj-out{{width:100%;min-height:70px;font-family:monospace;font-size:.85rem;display:none}}
</style>
<h2>🎭 Cast voices: pick one per character (top 3 + current)</h2>
<p class="cj-sub">👂 7 characters · 4 voices each (top 3 new + 🔁 the current one) · 3 lines per voice, one take each, mastered · 🤖 ranked by numbers only: no model listened and the judge cannot hear, your ear decides · ⏱️ {stamp}</p>
<p class="cj-note">📝 Your E01C note: «viewers can't tell where the characters come from». So each section below starts with the character's origin in plain words. The fix for the episodes (a short line or card saying where each one is from) goes into the E02 brief.</p>
<div class="cj-bar"><button type="button" id="cj-copy">📋 Copy picks</button><button type="button" id="cj-clear">🧹 Clear picks</button><span id="cj-count" class="cj-picked"></span></div>
<textarea id="cj-out" readonly></textarea>
{"".join(secs)}
<script>
(function(){{
  var KEY="cast-picks-v1", chars={json.dumps(list(CHARS))};
  function load(){{try{{return JSON.parse(localStorage.getItem(KEY)||"{{}}")}}catch(e){{return {{}}}}}}
  function save(p){{localStorage.setItem(KEY,JSON.stringify(p))}}
  function paint(){{
    var p=load(), n=0;
    chars.forEach(function(c){{
      var v=p[c]; if(v) n++;
      document.querySelectorAll('input[name="cj-'+c+'"]').forEach(function(r){{r.checked=(r.value===v)}});
      var s=document.querySelector('.cj-picked[data-char="'+c+'"]'); if(s) s.textContent=v?("✅ picked: "+v):"";
    }});
    document.getElementById("cj-count").textContent="✅ "+n+" of "+chars.length+" picked";
  }}
  document.querySelectorAll('.cj input[type=radio]').forEach(function(r){{
    r.addEventListener("change",function(){{var p=load();p[r.name.slice(3)]=r.value;save(p);paint()}});
  }});
  document.getElementById("cj-clear").addEventListener("click",function(){{localStorage.removeItem(KEY);paint()}});
  document.getElementById("cj-copy").addEventListener("click",function(){{
    var t=JSON.stringify(Object.assign({{"_key":KEY,"_date":new Date().toISOString().slice(0,19).replace("T"," ")}},load()),null,1);
    var o=document.getElementById("cj-out"); o.value=t; o.style.display="block"; o.select();
    if(navigator.clipboard) navigator.clipboard.writeText(t).catch(function(){{document.execCommand("copy")}}); else document.execCommand("copy");
  }});
  paint();
}})();
</script>
</section>
<!-- cast-judge:end -->'''
    text = page.read_text(encoding="utf-8")
    text = re.sub(r"<!-- cast-judge:start -->.*?<!-- cast-judge:end -->\n?", "", text, flags=re.S)
    m = re.search(r'<section class="panel" id="panel-castvoices"[^>]*>\s*<main class="wrap">', text)
    if not m:
        raise SystemExit("no Cast voices tab (id=panel-castvoices) found in the page")
    text = text[:m.end()] + "\n" + block + "\n" + text[m.end():]
    if "\u2014" in block:
        raise SystemExit("em dash in the block")
    page.write_text(text, encoding="utf-8")
    print("page block written; audio elements:", n_audio)
    return 0


def cmd_verify(judge, page):
    """Every <audio src> inside the block resolves (from MAIN/previews) to a file that ffmpeg decodes without error."""
    text = Path(page).read_text(encoding="utf-8")
    blk = re.search(r"<!-- cast-judge:start -->.*?<!-- cast-judge:end -->", text, flags=re.S).group(0)
    srcs = re.findall(r'<audio[^>]*src="([^"]+)"', blk)
    bad = []
    for s in srcs:
        p = (MAIN / "previews" / s).resolve()
        if not p.exists():
            bad.append(f"missing {s}")
            continue
        r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0 or r.stderr.strip() or V.wav_seconds(p) <= 0.2:
            bad.append(f"decode {s}: {r.stderr.strip()[:120]}")
    tash = TASHKEEL.findall(re.sub(r"<script.*?</script>", "", blk, flags=re.S))
    out = {"audio_src": len(srcs), "unique": len(set(srcs)), "bad": bad, "tashkeel_chars_visible": len(tash), "em_dash": blk.count("\u2014")}
    write_json(Path(judge) / "verify.json", out)
    print(json.dumps(out, ensure_ascii=False))
    return 1 if bad or tash or out["em_dash"] else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    a = sys.argv[1:]
    cmds = {"refs": lambda: cmd_refs(a[1]), "run": lambda: cmd_run(a[1]), "takes": lambda: cmd_takes(a[1]),
            "page": lambda: cmd_page(a[1], a[2]), "verify": lambda: cmd_verify(a[1], a[2])}
    if a[:1] and a[0] in cmds:
        sys.exit(cmds[a[0]]())
    print(__doc__)
