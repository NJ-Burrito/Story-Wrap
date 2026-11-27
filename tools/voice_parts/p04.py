# voice.py part 4 of 4: executed into the voice module namespace by voice.py (a pure move).
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
        bsegs = ((att.get(m["id"]) or {}).get("breath") or {}).get("segments") or []
        f += [("VOICE-EDGE-NOISE", f"line {m['id']}: {msg}") for msg in edge_noise_problems(x, rate, max((s["pause_s"] for s in bsegs), default=0) or None)]
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
    ap.add_argument("--rejoin", action="store_true", help="voice: join, trim and master again from the saved segment takes (post-processing only; nothing is voiced)")
    ap.add_argument("--resume", action="store_true", help="voice: after a worker crash, complete the unfinished lines from the audio that exists (segments are reused, never regenerated)")
    ap.add_argument("--no-breath", action="store_true", help="voice: one utterance per line (the pre-breath behaviour); breath segmentation is on by default")
    ap.add_argument("--inhale", action="store_true", help="voice: add a very soft inhale cut from the speaker's own reference, if it holds a clean one (default off)")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--work", default=None, help="take directory when it is not work/voice/<episode>")
    ap.add_argument("--series", default="series")
    ap.add_argument("--profile", default=DEFAULT_REFQ_PROFILE, help="refcheck: REF-QUALITY limit set (" + ", ".join(REFQ_PROFILES) + ")")
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
                print("usage: refcheck <ref.wav> [provenance.json] [--profile NAME]", file=sys.stderr)
                return 2
            prof, bad = check_reference_quality(a.episode, a.out, a.profile)
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
            return cmd_voice(paths, a.go, engine=a.engine, breath=not a.no_breath, inhale=a.inhale, resume=a.resume, rejoin=a.rejoin)
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
