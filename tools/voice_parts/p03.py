# voice.py part 3 of 4: executed into the voice module namespace by voice.py (a pure move).
# ---------------------------------------------------------------- breath segmentation
# Owner feedback on a test episode: the voice lacks the breath a speaker takes between sentences and after question marks, exclamation marks and
# commas, and the word after the pause must be said as a first word. So (default ON, `voice --no-breath` turns it off):
#   1. a line's tts_text is split after each punctuation mark, the mark stays on the end of its segment (the prosody follows it);
#   2. every segment is its own Chatterbox utterance (ONE take each, no verify, no re-voice), so the word after a pause starts as a first word;
#   3. the takes are joined with a breath pause whose length depends on the mark and which is filled with the voice's own quiet floor
#      (room tone cut from its reference), never digital zero (REF and VOICE gates flag digital silence).
BREATH_PAUSE_S = {                # seconds of quiet between the last word of a segment and the first word of the next (owner-chosen)
    "comma": 0.22,                # «،»  ,
    "semi": 0.30,                 # «؛»  ;  :
    "stop": 0.40,                 # .
    "ellipsis": 0.40,             # ...  …   (not in the owner's list: held like a full stop)
    "strong": 0.45,               # «؟»  ?  !
}
BREATH_MARKS = {"،": "comma", ",": "comma", "؛": "semi", ";": "semi", ":": "semi", ".": "stop", "…": "ellipsis",
                "؟": "strong", "?": "strong", "!": "strong"}
BREATH_CLOSERS = "»”’\"')]"       # a closing quote or bracket after a mark stays on that segment («…؟»)
BREATH_WEAK = ("comma", "semi")   # a SHORT segment ending in a weak mark joins its neighbour; a short one ending . ? ! ... stands alone
BREATH_MIN_WORDS = 3              # "very short" = fewer words than this
BREATH_LEAD_KEEP_S = 0.04         # speech-span margins kept around each segment take when joining (inside the pause budget)
BREATH_TAIL_KEEP_S = 0.10
BREATH_LEAD_PAD_S = 0.06          # room tone before the first and after the last word of a joined take (the edge cleaner keeps its own guards on top)
BREATH_TAIL_PAD_S = 0.25
BREATH_FADE_S = 0.05              # equal-power cross-fade between a segment's edge and the room tone under the pause
BREATH_TONE_WIN_S = 0.25          # length of the quietest stretch cut from the reference as room tone
BREATH_TONE_XFADE_S = 0.03
BREATH_TONE_MIN_DBFS = -84.0      # a room tone quieter than this is raised to it: under about 1.5 LSB of 16-bit it would round to digital zero in the wav
BREATH_FALLBACK_DBFS = -72.0      # room tone when the reference has no usable quiet stretch (every window holds digital zeros)
BREATH_TONE_MAX_DB = 15.0         # a room-tone window must sit at least this far under the reference's loud frames (p95), else it is speech, not a floor
BREATH_TONE_MAX_DBFS = -50.0      # a "room tone" louder than this is a fragment of speech, not a floor (measured on a real reference: its quietest 0.25 s was only 17 dB under
                                  # its speech, and tiled forwards and backwards into the pauses it was heard as a mumble / stutter); the seeded fallback floor is used instead
BREATH_SEG_RUN_GAP_S = 0.25       # inside ONE breath segment two voiced stretches more than this apart are not one phrase: the second is a model run-on / stray blip
                                  # (the default 0.4 s glued a 30 ms blip 0.38 s after the last word to the word, and the join kept ~0.5 s of hum / hiss after it)
BREATH_BURST_GAP_S = 0.25         # a loud stretch this far after the previous loud stretch ...
BREATH_BURST_MAX_S = 0.15         # ... and shorter than this is a model click / stray syllable after the sentence ended, not a word: the piece is cut before it
BREATH_BURST_BELOW_P95_DB = 20.0  # "loud" = within this many dB of the take's p95
BREATH_DECAY_BELOW_P95_DB = 26.0  # after the last frame louder than p95 minus this, at most BREATH_DECAY_KEEP_S of the take is kept; ...
BREATH_DECAY_KEEP_S = 0.15        # ... the model's breathy 35-40 dB-down decay (0.5 s of it can end a line) is not part of the word (the edge cleaner allows up to 0.35 s of "voiced decay")
BREATH_PAUSE_MAX_DBFS = -42.0     # join check: loudest 25 ms frame inside a built pause (speech-span edges included); louder = noise or speech in the pause
BREATH_TAIL_MAX_DBFS = -45.0      # join check: loudest 25 ms frame of the last BREATH_TAIL_PAD_S of the joined take
BREATH_MAX_ZERO_RUN_S = 0.002     # a room-tone window with a longer run of exact zeros is a gate/denoiser splice, not a microphone
BREATH_INHALE = False             # optional soft inhale (default OFF, owner decision: only if a clean breath can be cut from the speaker's own reference)
INHALE_PEAK_DBFS = -38.0          # "very soft"
INHALE_LEN_S = (0.18, 0.60)


def pause_kind(run):
    """The pause class of a run of marks («؟!», «...», «.»): the longest class in it; an ellipsis (… or three dots) counts as an ellipsis."""
    if "…" in run or "..." in run:
        return "ellipsis"
    kinds = [BREATH_MARKS[c] for c in run if c in BREATH_MARKS]
    return max(kinds, key=lambda k: BREATH_PAUSE_S[k]) if kinds else None


def split_breath(text):
    """Split tts_text after each punctuation mark. -> [{"text", "mark" (class or None)}]; the mark stays on the end of its segment.
    A mark between two digits (3.5, 1,000) or not followed by a space or the end is not a break. A piece with no letters is glued to the segment before it."""
    segs, cur, i, n = [], "", 0, len(text)
    while i < n:
        ch = text[i]
        cur += ch
        i += 1
        if ch not in BREATH_MARKS:
            continue
        if ch in ".,:" and i >= 2 and text[i - 2].isdigit() and i < n and text[i].isdigit():
            continue
        run = ch
        while i < n and (text[i] in BREATH_MARKS or text[i] in BREATH_CLOSERS):
            cur += text[i]
            run += text[i]
            i += 1
        if i < n and not text[i].isspace():
            continue
        segs.append({"text": cur.strip(), "mark": pause_kind(run)})
        cur = ""
    if cur.strip():
        segs.append({"text": cur.strip(), "mark": None})
    out = []
    for s in segs:
        if out and not AR_LETTER.search(s["text"]) and not re.search(r"[A-Za-z0-9]", s["text"]):
            out[-1]["text"] += " " + s["text"]
            out[-1]["mark"] = s["mark"] or out[-1]["mark"]
        else:
            out.append(dict(s))
    return out


def words_of(text):
    return len([w for w in re.split(r"\s+", text) if re.search(r"\w", w)])


def merge_short(segs, min_words=BREATH_MIN_WORDS):
    """Short-segment rule: a segment of fewer than `min_words` words that ends in a WEAK mark (comma, semicolon, colon) is spoken together with the
    NEXT segment (one utterance, its comma kept inside the text; the pause after the merged unit is the later segment's). A short LAST segment that
    follows a weak mark joins the one BEFORE it. A short segment that ends a sentence (. ? ! ...) is NEVER merged: it is a sentence of its own and
    gets its breath and its sentence-initial start («نعم.», «وكلماته؟»). -> segments with `pause_s` (0 for the last)."""
    segs = [dict(s) for s in segs]
    i = 0
    while i < len(segs) - 1:
        s = segs[i]
        if words_of(s["text"]) < min_words and s["mark"] in BREATH_WEAK:
            segs[i + 1]["text"] = s["text"] + " " + segs[i + 1]["text"]
            del segs[i]
            continue
        i += 1
    if len(segs) > 1 and words_of(segs[-1]["text"]) < min_words and segs[-2]["mark"] in BREATH_WEAK:
        segs[-2]["text"] += " " + segs[-1]["text"]
        segs[-2]["mark"] = segs[-1]["mark"]
        segs.pop()
    for k, s in enumerate(segs):
        s["pause_s"] = BREATH_PAUSE_S.get(s["mark"], 0.0) if k < len(segs) - 1 else 0.0
    return segs


def breath_plan(tts_text):
    """-> the segments to voice for one line (one entry = no split)."""
    return merge_short(split_breath(tts_text))


def room_tone_window(x, rate, win_s=BREATH_TONE_WIN_S, max_zero_run_s=BREATH_MAX_ZERO_RUN_S, max_dbfs=BREATH_TONE_MAX_DBFS):
    """The quietest stretch of the reference (lowest mean square over `win_s`), skipping stretches with a run of exact zeros. -> numpy array or None."""
    import numpy as np
    x = np.asarray(x, dtype="float64")
    w = int(win_s * rate)
    if len(x) < w * 1.2:
        return None
    hop = max(1, int(0.01 * rate))
    e = np.convolve(x * x, np.ones(w) / w, mode="valid")[::hop]
    zr = int(max_zero_run_s * rate)
    loud = float(np.percentile(e, 95))
    for k in np.argsort(e):
        if e[k] > loud * 10 ** (-BREATH_TONE_MAX_DB / 10):
            return None                                   # sorted by level: nothing quieter follows
        seg = x[k * hop:k * hop + w]
        z = np.diff(np.concatenate(([0], (seg == 0).astype(int), [0])))
        runs = np.nonzero(z == -1)[0] - np.nonzero(z == 1)[0]
        if len(runs) and runs.max() > zr:
            continue
        if float(np.sqrt(e[k])) <= 0.0:
            continue
        if 20 * math.log10(float(np.sqrt(e[k])) + 1e-12) > max_dbfs:
            return None                                   # the quietest usable stretch is still not a floor (speech tail): use the fallback noise
        return seg - float(np.mean(seg))
    return None


def tile_tone(tone, n, rate, xfade_s=BREATH_TONE_XFADE_S):
    """n samples of room tone: the window, then its time-reverse, and so on, equal-power cross-faded (deterministic)."""
    import numpy as np
    w = len(tone)
    xf = min(int(xfade_s * rate), w // 3)
    out = np.zeros(n + w)
    pos, k = 0, 0
    fi = np.sin(0.5 * math.pi * (np.arange(xf) + 0.5) / max(1, xf))
    while pos < n:
        t = (tone if k % 2 == 0 else tone[::-1]).copy()
        if k:
            t[:xf] *= fi
            out[pos:pos + xf] *= fi[::-1]
        out[pos:pos + w] += t
        pos += w - xf
        k += 1
    return out[:n]


def fallback_tone(n, rate, dbfs=BREATH_FALLBACK_DBFS):
    """Seeded low-level noise at `dbfs` RMS: the floor when a reference has no usable quiet stretch."""
    import numpy as np
    r = np.random.default_rng(20261107).standard_normal(n)
    return r / np.sqrt(np.mean(r * r)) * 10 ** (dbfs / 20)


def find_inhale(x, rate):
    """A clean breath cut from the speaker's OWN reference, or None: a noise-like (flat), quiet-but-above-floor stretch of 0.18-0.6 s with quiet frames
    on both sides. Used only with `inhale=True`; default off."""
    import numpy as np
    x = np.asarray(x, dtype="float64")
    hop, win = int(0.01 * rate), int(0.02 * rate)
    if len(x) < 10 * win:
        return None
    fr = np.array([x[i:i + win] for i in range(0, len(x) - win, hop)])
    db = 10 * np.log10(np.mean(fr * fr, axis=1) + 1e-12)
    floor, p95 = np.percentile(db, 10), np.percentile(db, 95)
    flat = np.array([band_flatness(list(f), rate) for f in fr])
    cand = (db > floor + 10) & (db < p95 - 22) & (flat > 0.35)
    i = 0
    while i < len(cand):
        if not cand[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(cand) and cand[j + 1]:
            j += 1
        ln = (j - i + 1) * hop / rate
        if INHALE_LEN_S[0] <= ln <= INHALE_LEN_S[1] and i > 3 and j < len(cand) - 4 and db[i - 3] < floor + 6 and db[j + 3] < floor + 6:
            seg = x[i * hop:(j + 1) * hop + win]
            seg = seg - np.mean(seg)
            return seg * 10 ** (INHALE_PEAK_DBFS / 20) / max(1e-9, float(np.max(np.abs(seg))))
        i = j + 1
    return None


def _fade_edges(p, rate, fi_s, fo_s):
    import numpy as np
    p = p.copy()
    fi, fo = min(int(fi_s * rate), len(p) // 3), min(int(fo_s * rate), len(p) // 3)
    if fi:
        p[:fi] *= np.sin(0.5 * math.pi * (np.arange(fi) + 0.5) / fi)
    if fo:
        p[len(p) - fo:] *= np.cos(0.5 * math.pi * (np.arange(fo) + 0.5) / fo)
    return p


def tail_burst_start(x, rate, onset_s, offset_s, p95_db, win_s=0.025):
    """Second of the first loud frame of an isolated short burst at the END of a segment take (BREATH_BURST_*), else None. Loud frames are grouped; two groups
    more than BREATH_BURST_GAP_S apart are separate stretches; the last stretch is a burst when it is shorter than BREATH_BURST_MAX_S."""
    import numpy as np
    x = np.asarray(x, dtype="float64")
    n = max(1, int(win_s * rate))
    a, b = int(onset_s * rate), min(len(x), int((offset_s + BREATH_TAIL_KEEP_S) * rate))
    idx = [i for i in range(0, max(0, b - a - n + 1), n) if 10 * math.log10(float(np.mean(x[a + i:a + i + n] ** 2)) + 1e-12) >= p95_db - BREATH_BURST_BELOW_P95_DB]
    if len(idx) < 2:
        return None
    gap_f = BREATH_BURST_GAP_S * rate / n                  # frames
    groups = [[idx[0]]]
    for i in idx[1:]:
        if (i - groups[-1][-1]) / n - 1 > gap_f:
            groups.append([i])
        else:
            groups[-1].append(i)
    last = groups[-1]
    if len(groups) >= 2 and len(last) * n / rate < BREATH_BURST_MAX_S:
        return (a + last[0]) / rate
    return None


def last_loud_end(x, rate, onset_s, offset_s, p95_db, win_s=0.025):
    """End (s) of the last 25 ms frame inside [onset, offset + tail keep] that is louder than p95 minus BREATH_DECAY_BELOW_P95_DB; None if there is none."""
    import numpy as np
    x = np.asarray(x, dtype="float64")
    n = max(1, int(win_s * rate))
    a, b = int(onset_s * rate), min(len(x), int((offset_s + BREATH_TAIL_KEEP_S) * rate))
    last = None
    for i in range(0, max(0, b - a - n + 1), n):
        if 10 * math.log10(float(np.mean(x[a + i:a + i + n] ** 2)) + 1e-12) >= p95_db - BREATH_DECAY_BELOW_P95_DB:
            last = (a + i + n) / rate
    return last


def frame_max_dbfs(x, rate, win_s=0.025):
    """Loudest win_s frame of x in dBFS (-200 for an empty/zero array)."""
    import numpy as np
    x = np.asarray(x, dtype="float64")
    n = max(1, int(win_s * rate))
    if len(x) == 0:
        return -200.0
    best = max(float(np.mean(x[i:i + n] ** 2)) for i in range(0, max(1, len(x) - n + 1), n))
    return round(10 * math.log10(best + 1e-20), 1)


def join_noise_check(y, rate, spans, tail_n):
    """Deterministic check of a joined take (a speech-fragment room tone, noise after the last word): loudest frame in each built pause and in the closing pad.
    -> {"pause_max_dbfs": [...], "tail_max_dbfs": x, "join_noise": [problems]}."""
    pm = [frame_max_dbfs(y[a:b], rate) for a, b in spans]
    tm = frame_max_dbfs(y[len(y) - tail_n:], rate)
    bad = [f"pause {k} peaks at {v} dBFS (limit {BREATH_PAUSE_MAX_DBFS})" for k, v in enumerate(pm) if v > BREATH_PAUSE_MAX_DBFS]
    if tm > BREATH_TAIL_MAX_DBFS:
        bad.append(f"closing pad peaks at {tm} dBFS (limit {BREATH_TAIL_MAX_DBFS})")
    return {"pause_max_dbfs": pm, "tail_max_dbfs": tm, "join_noise": bad}


def join_segments(parts, rate, pauses, tone, dones=None, inhale=None, kinds=None):
    """Join the segment takes with breath pauses. parts = float arrays (raw takes at `rate`); pauses[k] = seconds of quiet between the speech of segment k
    and k+1; tone = room-tone window (numpy) cut from the speaker's reference, or None for the seeded fallback floor.
    Each take keeps its speech span plus BREATH_LEAD_KEEP_S before and BREATH_TAIL_KEEP_S after (the model's noise lead-in and run-on are dropped); the
    pause is the rest of the budget, filled with room tone cross-faded in and out under the neighbouring takes, so no sample of the gap is digital zero.
    Every piece edge is faded (50 ms where audio was cut away, 20 ms where the model's take simply ended), and the joined take starts and ends with
    BREATH_LEAD_PAD_S / BREATH_TAIL_PAD_S of room tone, so the last word is never the last sample (VOICE-TAIL reads the level at the end).
    -> (numpy array, record with the designed and the measured gap per join)."""
    import numpy as np
    import voice_edges as VE
    E = dict(VE.params(), run_gap_s=BREATH_SEG_RUN_GAP_S)       # a segment is one short phrase: a stray stretch further than this from its words is run-on
    if tone is not None:
        rms = float(np.sqrt(np.mean(np.asarray(tone) ** 2)))
        floor = 10 ** (BREATH_TONE_MIN_DBFS / 20)
        tone = np.asarray(tone) * (floor / rms if rms < floor else 1.0)
    pieces, bursts = [], []
    for k, x in enumerate(parts):
        x = np.asarray(x, dtype="float64")
        sp = VE.speech_span(x, rate, E, done_after_s=(dones[k] if dones else None))
        burst = tail_burst_start(x, rate, sp["onset_s"], sp["offset_s"], sp["p95_db"])
        if burst is not None:                    # a stray burst after the last word: the piece ends before it (the 0.1 s tail keep stops short of it)
            sp = dict(sp, offset_s=min(sp["offset_s"], burst - BREATH_TAIL_KEEP_S - 0.02), burst_cut_s=round(burst, 3))
        ll = last_loud_end(x, rate, sp["onset_s"], sp["offset_s"], sp["p95_db"])
        if ll is not None and ll + BREATH_DECAY_KEEP_S - BREATH_TAIL_KEEP_S < sp["offset_s"]:      # the word is over: keep a short decay, drop the breathy tail
            sp = dict(sp, offset_s=ll + BREATH_DECAY_KEEP_S - BREATH_TAIL_KEEP_S)
        a = max(0, int(round((sp["onset_s"] - BREATH_LEAD_KEEP_S) * rate)))
        b = min(len(x), int(round((sp["offset_s"] + BREATH_TAIL_KEEP_S) * rate)))
        on = int(round(sp["onset_s"] * rate)) - a
        off = int(round(sp["offset_s"] * rate)) - a
        p = _fade_edges(x[a:b], rate, BREATH_FADE_S if a > 0 else 0.01, BREATH_FADE_S if b < len(x) else 0.02)
        pieces.append((p, on, off))
        bursts.append(sp.get("burst_cut_s"))
    fo_n = int(BREATH_FADE_S * rate)
    lead_n, tail_n = int(BREATH_LEAD_PAD_S * rate), int(BREATH_TAIL_PAD_S * rate)
    # the quiet between two speech spans is (what the take kept after its last sound) + (room tone) + (what the next kept before its first sound); a take
    # that starts speaking at once has less than BREATH_LEAD_KEEP_S before its onset, so the room tone is what is left of the pause budget
    gaps = [max(0, int(round(pauses[k] * rate)) - (len(pieces[k][0]) - pieces[k][2]) - pieces[k + 1][1]) for k in range(len(pieces) - 1)]
    total = lead_n + sum(len(p) for p, _, _ in pieces) + sum(gaps) + tail_n
    out = np.zeros(total)
    big = tile_tone(tone, total + fo_n, rate) if tone is not None else fallback_tone(total + fo_n, rate)
    pos, starts = lead_n, []
    for k, (p, on, off) in enumerate(pieces):
        out[pos:pos + len(p)] += p
        starts.append((pos, on, off))
        pos += len(p)
        if k < len(pieces) - 1:
            g = gaps[k]
            n1, n2 = min(fo_n, len(p)), min(fo_n, len(pieces[k + 1][0]))
            seg = big[pos - n1:pos + g + n2].copy()          # room tone under the whole pause, fading in over the end of piece k and out over the start of k+1
            seg[:n1] *= np.sin(0.5 * math.pi * (np.arange(n1) + 0.5) / max(1, n1))
            seg[len(seg) - n2:] *= np.cos(0.5 * math.pi * (np.arange(n2) + 0.5) / max(1, n2))
            out[pos - n1:pos + g + n2] += seg
            if inhale is not None and (kinds or [None] * len(pieces))[k] in ("stop", "strong", "ellipsis") and len(inhale) + int(0.1 * rate) < g:
                s0 = pos + g - len(inhale) - int(0.04 * rate)
                out[s0:s0 + len(inhale)] += _fade_edges(inhale, rate, 0.04, 0.06)
            pos += g
    e0, e1 = min(fo_n, len(pieces[0][0])), min(fo_n, len(pieces[-1][0]))
    env0 = np.concatenate([np.ones(lead_n), np.cos(0.5 * math.pi * (np.arange(e0) + 0.5) / max(1, e0))])      # floor before the first word, fading out as the first take fades in
    out[:len(env0)] += big[:len(env0)] * env0
    env1 = np.concatenate([np.sin(0.5 * math.pi * (np.arange(e1) + 0.5) / max(1, e1)), np.ones(tail_n)])        # floor after the last word, fading in as the last take fades out
    out[total - len(env1):] += big[:len(env1)] * env1
    rec, spans = [], []
    for k in range(len(pieces) - 1):
        p0, on0, off0 = starts[k]
        p1, on1, off1 = starts[k + 1]
        rec.append({"after_segment": k, "designed_s": round(pauses[k], 3), "measured_s": round(((p1 + on1) - (p0 + off0)) / rate, 3)})
        spans.append((p0 + off0, p1 + on1))
    chk = join_noise_check(out, rate, spans, tail_n)
    return out, {"joins": rec, "pause_spans": spans, "pieces": [{"onset_s": round(on / rate, 3), "offset_s": round(off / rate, 3), "burst_cut_s": bc, "kept_s": round(len(p) / rate, 3)} for (p, on, off), bc in zip(pieces, bursts)], **chk, "room_tone": "reference" if tone is not None else f"fallback {BREATH_FALLBACK_DBFS:.0f} dBFS noise", "inhale": inhale is not None}


def max_zero_run_s(x, rate):
    """Longest run of exact zeros in x, in seconds (the digital-silence test of the breath tests and the join record)."""
    import numpy as np
    z = np.diff(np.concatenate(([0], (np.asarray(x) == 0).astype(int), [0])))
    runs = np.nonzero(z == -1)[0] - np.nonzero(z == 1)[0]
    return float(runs.max() / rate) if len(runs) else 0.0


def join_line_files(seg_files, ref_path, pauses, kinds, dones, out_path, inhale=False):
    """Read the segment takes (wav), join them with room tone from the speaker's reference, write the raw take `out_path` (16-bit). -> join record."""
    import numpy as np
    parts, rate = [], None
    for f in seg_files:
        x, r = read_float(f)
        rate = rate or r
        if r != rate:
            raise Fail("VOICE-AUDIO", f"{f}: sample rate {r} differs from {rate}")
        parts.append(np.asarray(x))
    rx, rr = read_float(ref_path)
    rx = np.asarray(rx if rr == rate else resample(rx, rr, rate))
    tone = room_tone_window(rx, rate)
    inh = find_inhale(rx, rate) if inhale else None
    y, rec = join_segments(parts, rate, pauses, tone, dones=dones, inhale=inh, kinds=kinds)
    write_wav16(out_path, [float(v) for v in y], rate)
    rec["rate"] = rate
    q = np.round(y * 32767)
    rec["max_zero_run_s"] = round(max_zero_run_s(q, rate), 4)                    # the whole take: includes zeros the model itself wrote inside a segment
    rec["pause_zero_run_s"] = round(max([max_zero_run_s(q[a:b], rate) for a, b in rec.pop("pause_spans")] or [0.0]), 4)   # the pauses this join built
    return rec


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


def cmd_voice(paths=None, go=False, engine=ENGINE, repo=REPO, synth=None, resources=None, master=None, breath=True, inhale=BREATH_INHALE, resume=False, rejoin=False, **_ignored):
    """ONE Chatterbox take per line, then the offline end-trim. Without --go it only prints the plan.
    `rejoin=True` (`--rejoin`, implies resume): join, trim and master AGAIN from the saved segment takes of every line (post-processing only; no model runs,
    nothing is voiced). Use it after a change to the join or the trim, never to get another take.
    `resume=True` (`--resume`, after a worker CRASH only): a line the crashed run left unfinished is completed from the audio that already exists on disk
    (segment takes are reused, never regenerated; a line whose segments are all there is only joined, trimmed and logged); only a segment whose audio does not
    exist is voiced, once. A line with no audio at all that had started stays blocked (VOICE-ONCE).
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
    resume = resume or rejoin
    prev_job = read_json(work / "worker-job.json") if resume and (work / "worker-job.json").exists() else {}
    prev_segs = {pj["id"]: [s["text"] for s in (pj.get("segments") or [])] for pj in prev_job.get("lines", [])}
    if resume:                                        # the text each segment take voiced, from the lines that were finished and logged
        for ln_id, rec in attempts(work).items():
            if rec.get("status") == "ok" and (rec.get("breath") or {}).get("segments"):
                prev_segs[ln_id] = [s["text"] for s in rec["breath"]["segments"]]
    for m in manifest["lines"]:
        n = m["id"]
        st = line_state(work, n)
        if resume and not rejoin and st == "taken" and (work / f"{n}.trimmed.wav").exists():
            continue                      # finished by an earlier run
        if superseded_log(work).exists() and st == "taken":
            continue                      # only the lines of a superseded (banned) voice are voiced again; settled takes stay
        ref = reference_for(casting, m["speaker"], repo)
        if st in ("taken", "blocked-after-start") and not resume:
            raise Fail("VOICE-ONCE", f"line {n}: a take was already made or started; a line is voiced once, never re-voiced")
        jobs.append({"id": n, "speaker": m.get("speaker"), "text": m["tts_text"], "ref": str(ref), "out": str(work / f"{n}.wav"),
                     "ref_sha256": (rs := sha(ref.read_bytes())), "cap": token_cap(m["tts_text"], m.get("speaker"), rs),
                     "cap_rate": voice_rate(m.get("speaker"), rs)[1], "done_after_s": round(edge_done_after_s(m["tts_text"], m.get("speaker"), rs), 2),
                     "settings": {**character_settings(casting, m.get("speaker")), **line_tone(m)}})
        plan = breath_plan(m["tts_text"]) if breath else []
        if len(plan) > 1:                   # breath segmentation: one utterance per segment, joined by join_line_files after the worker
            j = jobs[-1]
            j["segments"] = [{"text": s["text"], "mark": s["mark"], "pause_s": s["pause_s"], "out": str(work / f"{n}.seg{k:02d}.wav"),
                              "cap": token_cap(s["text"], m.get("speaker"), j["ref_sha256"]), "seed_key": f"{n}#seg{k:02d}",
                              "done_after_s": round(edge_done_after_s(s["text"], m.get("speaker"), j["ref_sha256"]), 2)} for k, s in enumerate(plan)]
            j["cap"] = max(s["cap"] for s in j["segments"])
        if resume and st in ("taken", "blocked-after-start"):      # crash recovery: reuse the audio that exists, voice only what does not
            j = jobs[-1]
            if j.get("segments"):
                before = prev_segs.get(n, [])
                for k, s in enumerate(j["segments"]):
                    s["reuse"] = Path(s["out"]).exists() and k < len(before) and before[k] == s["text"]
                reused = [k for k, s in enumerate(j["segments"]) if s["reuse"]]
            else:
                j["reuse"] = Path(j["out"]).exists()
                reused = [0] if j["reuse"] else []
            if not reused:
                raise Fail("VOICE-ONCE", f"line {n}: it started in an earlier run and left no audio; a started line stays blocked (resume completes only what exists)")
            j["resumed"] = {"from_state": st, "reused_segments": reused, **({"rejoin": True} if rejoin else {})}
    gen_jobs = [j for j in jobs if (any(not s.get("reuse") for s in j["segments"]) if j.get("segments") else not j.get("reuse"))]
    if not go:
        print(f"dry run: {len(jobs)} take(s) ({len(gen_jobs)} to generate), engine {ENGINE}, one each, local GPU. Add --go to voice them.")
        return 0
    if gen_jobs:                                     # a pass that only joins and trims (--resume with nothing left, --rejoin) voices nothing and needs no receipt
        check_gate_receipt(paths)
    if resources is None and synth is None:
        resources = real_resources
    if resources is not None and gen_jobs:
        r = resources()
        short = preflight_problems(r.get("commit_free"), r.get("gpu_free"), r.get("need_commit", need_commit_bytes()))
        if short:
            raise Fail("VOICE-PREFLIGHT", "; ".join(short) + ". Nothing was started; no line is used up.")
    work.mkdir(parents=True, exist_ok=True)
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    marks = work / "worker-marks.jsonl"
    marks.write_text("", encoding="utf-8")           # earlier runs are settled in attempts.jsonl
    for j in gen_jobs:                               # logged BEFORE the model runs: a crash never allows a second take
        log_attempt(work, {"id": j["id"], "status": "resumed" if j.get("resumed") else "started", "engine": ENGINE, "at": now, **({"resumed": j["resumed"]} if j.get("resumed") else {})})
    job = {"lines": gen_jobs, "settings": CHATTERBOX_SETTINGS, "result": str(work / "worker-result.json"), "marks": str(marks),
           "eos_after_complete_tokens": eos_after_complete_tokens()}
    write_json(work / "worker-job.json", job)
    ids = [j["id"] for j in gen_jobs]
    err_log = work / "worker-stderr.log"
    failure = None
    if not gen_jobs:
        pass                                         # resume with nothing left to generate: only join, trim and log
    elif synth is not None:
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
    joined = {}

    def complete(j):
        return all(Path(s["out"]).exists() for s in j["segments"]) if j.get("segments") else Path(j["out"]).exists()

    def finish(js):
        """Join the segment takes of each complete line into <id>.wav, end-trim and master it, log it `ok`. -> ids finished."""
        import voice_master as VM
        done = []
        for j in js:
            if not complete(j):
                continue
            segs = j.get("segments")
            if segs:                                 # breath-segmented line: the segment takes are joined into the raw take <id>.wav
                joined[j["id"]] = join_line_files([s["out"] for s in segs], j["ref"], [s["pause_s"] for s in segs],
                                                  [s["mark"] for s in segs], [s["done_after_s"] for s in segs], j["out"], inhale=inhale)
            raw = Path(j["out"])
            pause_total = sum(s["pause_s"] for s in segs) if segs else 0.0
            info = cmd_trim(raw, work / f"{j['id']}.trimmed.wav", master=master, role=VM.role_of(j.get("speaker")),
                            done_after_s=(j.get("done_after_s") or 0) + pause_total if segs else j.get("done_after_s"),
                            edge_overrides={"run_gap_s": max(s["pause_s"] for s in segs) + 0.3} if segs else None)
            log_attempt(work, {"id": j["id"], "status": "ok", "engine": ENGINE, "settings": CHATTERBOX_SETTINGS,
                               "reference": {"clip": Path(j["ref"]).relative_to(repo).as_posix() if Path(j["ref"]).is_relative_to(repo) else j["ref"],
                                             "sha256": j["ref_sha256"]},
                               "token_cap": j["cap"], "token_cap_rate": j.get("cap_rate"), "eos_after_complete_tokens": job["eos_after_complete_tokens"], "gen_s": gen.get(j["id"], {}).get("gen_s"), "raw_sha256": sha(raw.read_bytes()),
                               "tts_sha256": sha(j["text"].encode("utf-8")),
                               "trim": info,
                               **({"resumed": j["resumed"]} if j.get("resumed") else {}),
                               **({"breath": {"on": True, "inhale": inhale, "pause_table_s": BREATH_PAUSE_S, "join": joined.get(j["id"]),
                                              "segments": [{"text": s["text"], "mark": s["mark"], "pause_s": s["pause_s"], "cap": s["cap"],
                                                            "tts_sha256": sha(s["text"].encode("utf-8")),
                                                            "raw_sha256": sha(Path(s["out"]).read_bytes())} for s in segs]}} if segs else {})})
            done.append(j["id"])
        return done

    if failure is None and any(not complete(j) for j in jobs):
        failure = "the worker finished but wrote no audio for: " + ", ".join(j["id"] for j in jobs if not complete(j))
    if failure is not None:
        # lines the worker finished before it died (its result file lists them) are real takes: finish them now, so a crash on line N never loses lines 1..N-1
        finish([j for j in jobs if complete(j) and (j["id"] in gen or j not in gen_jobs)])
        flat = " ".join(failure.split())
        nt, bl = settle_failed_run(work, ids, marks, flat[:1200])
        raise Fail("VOICE-ENGINE", f"{flat}. Not taken (may be voiced later): {', '.join(nt) or 'none'}. "
                                   f"Blocked, generation had started: {', '.join(bl) or 'none'}.")
    finish(jobs)
    measure_manifest(paths, work)
    return 0


NL = chr(10)


def superseded_log(work):
    return Path(work) / "supersede.jsonl"
