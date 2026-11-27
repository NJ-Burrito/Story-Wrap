# voice.py part 2 of 4: executed into the voice module namespace by voice.py (a pure move).
def edge_noise_problems(samples, rate, max_pause_s=None):
    """VOICE-EDGE-NOISE (2026-10-26): no noise-only window before the first word or after the last one, beyond the guards
    (tools/voice_edges.py, limits `checks.edge_noise`). Same detector as the cleaner, so a take it cleaned passes and a take
    with a noise-only lead-in or tail (the old trim's j03 L01: 3.97 s) fails."""
    import numpy as np
    import voice_edges as VE
    prof = None
    if max_pause_s:                                  # a breath-joined take holds pauses longer than run_gap_s: widen the gap the way the cleaner did (trim_take edge_overrides)
        prof = {"take": {"edge": {**VE.params(), "run_gap_s": max(VE.params()["run_gap_s"], max_pause_s + 0.3)}}, "checks": {"edge_noise": VE.check_limits()}}
    return VE.edge_problems(np.asarray(samples, dtype="float64"), rate, prof)


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
DEFAULT_REFQ_PROFILE = "common-voice"
# Profile "curated-clean" (2026-11-07), chosen per casting entry with reference.refq_profile. The REFQ limits above are calibrated on raw
# Common Voice clips. The curated voice set holds curated refs that were denoised and level-normalised, which the CV limits read as a
# gate/denoiser fingerprint, a hot crest and a loud floor: all 25 failed. Limits below come from the measured distribution of the 12
# grade-A/B curated refs (44.1 kHz, `voices/**/ref.wav`, measured with ref_profile after a resample to 24 kHz). Measured min/max across the 12:
#   floor_dbfs -83.2..-38.4   snr_db 21.5..68.4   crest_db 10.2..22.6   top_db -83.2..-16.8   decay20_s 0.04..0.31
#   zero_frac 0.002..0.1034   centroid_hz 384..937   hum_db 3.3..11.7   clip_samples 0 in all
# Rule: a limit that the A/B refs break is moved to the worst A/B value plus a small margin; a limit all A/B refs already meet stays as in
# REFQ (no loosening without evidence). The one Tukey outlier on a quality metric (top_db -83.2, muffled) is NOT used: -58 stays.
# Not loosened: clipping (0 samples), muffled (-58), hum (40), reference length. Added: sample rate must be 24/44.1/48 kHz. Details and
# per-ref numbers: research/voice/refq-curated-clean-2026-11-07.md.
REFQ_CURATED = {
    **REFQ,
    "calibrated_on": "12 grade-A/B refs of the curated voice set, 2026-11-07 (see the comment above)",
    "min_up_votes": 0,                    # the set is graded by measurement, not by community votes
    "max_floor_dbfs": -36.0,              # A/B worst -38.4 + 2.4 dB
    "min_snr_db": 19.0,                   # A/B worst 21.5 - 2.5 dB
    "min_crest_db": 8.0,                  # A/B worst 10.2 - 2.2 dB; normalised refs have low crest
    "max_decay20_s": 0.35,                # A/B worst 0.31 + 0.04
    "max_zero_frac": 0.12,                # A/B worst 0.1034: denoised refs hold digital-silence pauses
    "min_floor_dbfs": -90.0,              # A/B lowest -83.2 - 6.8 dB; lower-grade refs at -97 and -120 stay refused
    "min_centroid_hz": 350.0,             # A/B lowest 384 - 34 Hz; the banned Common Voice narrator (334 Hz) stays refused
    "allowed_rates": (24000, 44100, 48000),   # any other source rate fails (8/16/22.05 kHz are band-limited, 96 kHz is unexpected)
    "refuse_never_clone": True,           # the set flags voices it says never to clone (meta never_clone)
}
REFQ_PROFILES = {DEFAULT_REFQ_PROFILE: REFQ, "curated-clean": REFQ_CURATED}


def refq_limits(profile):
    try:
        return REFQ_PROFILES[profile or DEFAULT_REFQ_PROFILE]
    except KeyError:
        raise Fail("REF-QUALITY", f"unknown REF-QUALITY profile {profile!r} (known: {', '.join(REFQ_PROFILES)})") from None


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
    if q.get("allowed_rates") and prof.get("source_rate") not in q["allowed_rates"]:
        out.append(f"sample rate {prof.get('source_rate')} Hz (allowed: {', '.join(str(r) for r in q['allowed_rates'])})")
    if q.get("refuse_never_clone") and prov is not None and prov.get("never_clone"):
        out.append("the set marks this voice never_clone")
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


def native_counts(x):
    """Counts that only mean something on the file's own samples (a resampler would change them): full-scale and exact-zero."""
    return {"clip_samples": sum(1 for v in x if abs(v) >= 0.999), "zero_frac": round(sum(1 for v in x if v == 0.0) / max(1, len(x)), 4)}


def check_reference_quality(wav, prov_path=None, profile=DEFAULT_REFQ_PROFILE):
    """REF-QUALITY on one reference wav (16-bit PCM or float32; 24 kHz is the engine's rate, higher rates are resampled to it
    for the measurement instead of crashing) -> (profile, problems). `profile` names the limit set (REFQ_PROFILES). Cached per file state."""
    wav = Path(wav)
    q = refq_limits(profile)
    st = wav.stat()
    key = (str(wav), st.st_mtime_ns, st.st_size)
    if key not in _REFQ_CACHE:
        x, rate = read_float(wav)
        if len(x) < rate:
            raise Fail("REF-QUALITY", f"{wav}: under 1 s of audio")
        if rate > PCM_RATE:
            y, _ = resample(x, rate)
            prof = {**ref_profile(y, PCM_RATE), **native_counts(x)}
        else:
            prof = ref_profile(x, rate)
        prof["source_rate"] = rate
        _REFQ_CACHE[key] = prof
    prof = _REFQ_CACHE[key]
    prov = read_json(prov_path) if prov_path and Path(prov_path).exists() else None
    return prof, ref_quality_problems(prof, prov, q)


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


CLEARED = "OWNER-CLEARED-COMMERCIAL"
LICENSES = ("CC0-1.0", "PUBLIC-DOMAIN", CLEARED)   # PUBLIC-DOMAIN (owner, 2026-10-25 task): only with a source_url and a licence_evidence_url in the provenance
# OWNER-CLEARED-COMMERCIAL (2026-11-07): the owner confirmed the clips of a curated voice set are free for commercial reuse. Valid
# only with an `owner_clearance` record {who, date, scope} on the casting entry's reference; without it the validator refuses.
CLEARANCE_FIELDS = ("who", "date", "scope")


def licence_problem(ref):
    """-> message when `ref` (a casting `reference` dict) claims OWNER-CLEARED-COMMERCIAL without a complete owner_clearance record."""
    rec = ref.get("owner_clearance")
    if not isinstance(rec, dict) or any(not str(rec.get(k, "")).strip() for k in CLEARANCE_FIELDS):
        return f"licence {CLEARED} needs an owner_clearance record with {', '.join(CLEARANCE_FIELDS)}"
    return None
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
        raise Fail("VOICE-REF", f"{speaker}: a reference clip must be CC0-1.0 (or verifiably public domain, 2026-10-25, or owner-cleared with a clearance record) with a provenance file")
    if ref.get("license") == CLEARED and (lp := licence_problem(ref)):
        raise Fail("VOICE-REF", f"{speaker}: {lp}")
    if ref.get("license") == "PUBLIC-DOMAIN" and not (read_json(prov).get("licence_evidence_url") and read_json(prov).get("source_url")):
        raise Fail("VOICE-REF", f"{speaker}: a public-domain reference needs source_url and licence_evidence_url in its provenance")
    ban = banned_reason(ref, read_json(prov), load_banned(repo))
    if ban:
        raise Fail("VOICE-BANNED-REF", f"{speaker}: reference {clip} is a {ban}. A banned voice is never cast again; choose another CC0 clip.")
    if check:
        _, bad = check_reference_quality(p, prov, ref.get("refq_profile", DEFAULT_REFQ_PROFILE))
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
        t0 = time.time()
        # Breath segmentation: a line with segments is voiced as one Chatterbox utterance per segment, ONE take each, so the word
        # after a pause starts with sentence-initial prosody. A line without segments is one utterance (the old path, seed from the line id).
        parts = ln.get("segments") or [{"text": ln["text"], "out": ln["out"], "cap": ln["cap"], "seed_key": ln["id"], "reuse": ln.get("reuse")}]
        for part in parts:
            if part.get("reuse"):                    # --resume: this segment's take already exists on disk; never voiced again
                continue
            cap["n"] = part.get("cap", ln["cap"])
            torch.manual_seed(int(sha(part.get("seed_key", ln["id"]))[:8], 16))
            wav = m.generate(part["text"], audio_prompt_path=ln["ref"], **{**job["settings"], **ln.get("settings", {})})
            torch.cuda.synchronize()
            ta.save(part["out"], wav.cpu(), m.sr)
        results.append({"id": ln["id"], "gen_s": round(time.time() - t0, 1), "sr": m.sr})
        write_json(job["result"], {"lines": results})
    return 0
