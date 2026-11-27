# calm_compose.py part 2 of 3: executed into the calm_compose module namespace by calm_compose.py (a pure move).
# ------------------------------------------------------------------ stage: plan -> timeline
def scene_seconds(line_s: float | None, explicit) -> float:
    """A scene lasts its line + a lead and a pad (grid-snapped), at least MIN_SCENE_S; a line that needs more than MAX_SCENE_S must be split by the writer."""
    if line_s is None:
        d = snap(float(explicit))
    else:
        d = snap(max(MIN_SCENE_S, line_s + VOICE_LEAD_S + PAD_S))
    if d > MAX_SCENE_S + 1e-9:
        raise Fail("PLAN-DURATION", f"a scene would last {d:.2f} s (> {MAX_SCENE_S} s): split the line")
    return d


def read_hold_s(lines: list[dict], line_id: str, line_s: float, gap_s: float, glossary: list[dict]) -> float:
    """C12 (CAP-READING-SPEED): the pause a scene needs after its line so that the LAST sentence plate of the line is up for max(1.5 s, chars / 12 cps) (cap_sentence.read_speed_need_s).
    gap_s is the room between the line's end and the next voice. The last plate is estimated from the text alone (no browser, no envelope): the last clause of the line, its
    share of the take by syllable weight, its bracketed meanings counted. The captions stage merges a unit that would still be too brief with its neighbour, and the gate
    (CAP-READING-SPEED) measures the real plates, so an estimate that is too small fails loudly there, never silently. Returns seconds (0 when the room is enough)."""
    ln = next((l for l in lines if l["id"] == line_id), None)
    if not ln:
        return 0.0
    words = display_text(ln["text"]).split()
    if not words:
        return 0.0
    start = len(words) - 1
    while start > 0 and not CS.ends_clause(words[start - 1]):
        start -= 1
    w, _m = CS.syllable_weights(" ".join(words), ln.get("tts_text"))
    speech = line_s * sum(w[start:]) / max(sum(w), 1e-9)
    shown = " ".join(G.with_gloss(words[start:], ln.get("speaker"), G.line_entries(ln, glossary)))
    need = CS.read_speed_need_s(CS.visible_chars(shown))
    return max(0.0, need - speech - (gap_s - 0.02) + READ_HOLD_MARGIN_S)


def read_heal_record(root, ep_id: str) -> dict:
    """R-503: work/daily/<ep>/read-heal.json {"lines": {line id: {"lead": s, "hold": s}}}: the reading time the animatic measured as missing, fed back to the plan by tools/read_heal.py. {} when absent."""
    try:
        r = json.loads((Path(root) / "work" / "daily" / ep_id / "read-heal.json").read_text(encoding="utf-8"))
        return r if isinstance(r, dict) else {}
    except (OSError, ValueError):
        return {}


def cap_heal_cuts(root, ep_id: str) -> dict[str, set[int]]:
    """R-506: work/daily/<ep>/cap-heal.json {"lines": {line id: {"cuts": [i, ...]}}}: boundaries after display word i where the caption heal (tools/cap_heal.py) asked for a new plate, because the
    plate that was there had no place outside the faces. {line id: {i}}; {} when the file is absent."""
    try:
        r = json.loads((Path(root) / "work" / "daily" / ep_id / "cap-heal.json").read_text(encoding="utf-8"))
        return {lid: {int(i) for i in (row or {}).get("cuts", [])} for lid, row in (r.get("lines") or {}).items()}
    except (OSError, ValueError, AttributeError, TypeError):
        return {}


def stage_plan(ep: Ep) -> dict:
    plan, script = read_json(ep.plan_p), read_json(ep.script_p)
    bad = validate_plan(plan, script)
    if bad:
        raise Fail(bad[0].split(" ", 1)[0], "; ".join(b.split(" ", 1)[1] for b in bad[:4]))
    items = []
    heal_rec = read_heal_record(ep.root, ep.id)

    def card(kind, dur):
        items.append({"kind": "card", "id": kind, "shot": f"{ep.id}-{kind}", "video": f"work/shots/{ep.id}-{kind}/out/{ep.id}-{kind}.mp4", "dur": snap(dur), "line": None})

    label = episode_label(plan) if algo_on(plan) else None
    if recap_expected(plan):
        card("recap", 2.5)
        hk = plan.get("hook") if algo_on(plan) else None
        if hk:    # DESIGN.md 2.1: the recap is SPOKEN, by the narrator, and it is the hook; it must fit the existing 3.0 s cap, so the cap is not touched
            tk = ep.take(hk["line"])
            if not tk.is_file():
                raise Fail("VOICE-MISSING", f"no take for {hk['line']} at {tk}: the voice stage comes before the shots")
            hd = snap(max(2.5, wav_seconds(tk) + VOICE_LEAD_S + PAD_S))
            if hd > RECAP_MAX_S + 1e-9:
                raise Fail("PLAN-DURATION", f"the spoken recap {hk['line']} would last {hd:.2f} s (> {RECAP_MAX_S} s, the recap card's cap): shorten the line to about {RECAP_MAX_S - VOICE_LEAD_S - PAD_S:.1f} s aloud")
            items[-1].update({"dur": hd, "line": hk["line"], "hook_pattern": hk.get("pattern")})
        if label:
            items[-1]["tag"] = label
    import calm_intro
    intros_after: dict = {}
    for ix in plan.get("intros", []) or []:
        intros_after.setdefault(ix["after"], []).append(ix)
    clock = _clock_minutes(plan.get("clock0", "9:00 م"))
    day_done = False
    for s in plan["scenes"]:
        if s.get("block", "story") != "consequence" and not day_done:
            wr, wd = plan.get("written"), float(plan.get("day_card_s", 2.0))      # per-plan option (e.g. 0.5 s so a second hook lands under a duration limit); absent = 2.0 s as before
            if wr:     # C3: the day card is a written object and the narrator reads it
                wt = ep.take(wr["line"])
                if not wt.is_file():
                    raise Fail("VOICE-MISSING", f"no take for {wr['line']} at {wt}: the voice stage comes before the shots")
                wd = max(2.5, wav_seconds(wt) + JOIN_S + VOICE_LEAD_S + PAD_S + 0.2)
            card("day", wd)
            if wr:
                items[-1].update({"line": wr["line"], "cap_style": "object", "cap_y": OBJ_CAP_Y, "written": True})
            day_done = True
        take = ep.take(s["line"]) if s.get("line") else None
        line_s = wav_seconds(take) if take else None
        if take is not None and not take.is_file():
            raise Fail("VOICE-MISSING", f"no take for {s['line']} at {take}: the voice stage comes before the shots")
        dur = scene_seconds(line_s, s.get("duration"))
        read_hold, dur_shot, lead_hold = 0.0, dur, 0.0
        if line_s is not None:     # C12: when the next line starts too soon for the last plate to be read, the plan inserts a pause; the shot holds its last frame, the voice never moves
            need_h = read_hold_s(script["lines"], s["line"], line_s, dur - line_s - (JOIN_S if items else 0.0), G.load(ep.root, script.get("series") or ep.series))
            heal = (heal_rec.get("lines") or {}).get(s["line"]) or {}      # R-503: what the animatic measured and the self-heal fed back (tools/read_heal.py)
            need_h += float(heal.get("hold") or 0.0)
            read_hold = math.ceil(need_h * FPS - 1e-9) / FPS if need_h > 0 else 0.0
            lead_hold = math.ceil(float(heal.get("lead") or 0.0) * FPS - 1e-9) / FPS if float(heal.get("lead") or 0.0) > 0 else 0.0
            dur = round(dur + read_hold + lead_hold, 4)
            dur_shot = round(dur_shot + lead_hold, 4)       # the lead is silence BEFORE the voice, inside the shot's own length (the lipsync offset is voice_t0 - t0)
            if dur > MAX_SCENE_S + 1.5 + 1e-9:
                raise Fail("PLAN-DURATION", f"scene {s['id']} would last {dur:.2f} s with its reading pause: shorten the line")
        clock = _clock_minutes(s["clock"]) if s.get("clock") else clock + 2
        items.append({"kind": "scene", "id": s["id"], "shot": f"{ep.id}-{s['id']}", "video": f"work/shots/{ep.id}-{s['id']}/out/{ep.id}-{s['id']}.mp4", "dur": dur,
                      "line": s.get("line"), "block": s.get("block", "story"), "clock": _clock_text(clock), "template": s["template"],
                      "read_hold": round(read_hold, 4), "lead_hold": round(lead_hold, 4), "dur_shot": round(dur_shot, 4),   # C12: the shot itself is rendered at dur_shot; the pause after it is its last frame held
                      "hold": float(s.get("hold") or 0.0),   # a deliberate hold: the last `hold` seconds of the shot are its last frame, still (the calm recipe's 13 to 17 % frozen share; E01C had none, so CALM-HOLDS failed)
                      "subjects": [s.get("params", {}).get("character")] if s["template"] != "two_shot" else [x.strip() for x in str(s["params"].get("characters", "")).split(",")],
                      **({"day": str(s["day"])} if s.get("day") not in (None, "") else {})})   # E04 Q06: a scene may carry its own HUD day (night one is day three, the day card then moves it to day four)
        for ix in intros_after.get(s["id"], []):      # C10: right after the scene that first shows the character the story freezes on them (calm_intro.py)
            itk = ep.take(ix["line"]) if ix.get("line") else None
            if itk is not None and not itk.is_file():
                raise Fail("VOICE-MISSING", f"no take for {ix['line']} at {itk}: the voice stage comes before the shots")
            need = calm_intro.min_duration(len(str(ix["name"]).split()) + len(str(ix["tag"]).split()))
            idur = snap(max(need, scene_seconds(wav_seconds(itk), None) if itk is not None else need))
            if idur > calm_intro.MAX_S + 1e-9:
                raise Fail("PLAN-DURATION", f"intro {ix['id']} would last {idur:.2f} s (> {calm_intro.MAX_S} s): shorten its narrator line")
            items.append({"kind": "intro", "id": ix["id"], "shot": f"{ep.id}-{ix['id']}", "video": f"work/shots/{ep.id}-{ix['id']}/out/{ep.id}-{ix['id']}.mp4", "dur": idur, "line": ix.get("line"),
                          "block": s.get("block", "story"), "template": "intro_freeze", "hold": 0.0, "subjects": [], "character": ix["character"], "name": ix["name"], "tag": ix["tag"], "after": s["id"]})
    if not day_done:
        raise Fail("PLAN-BLOCK", "every scene is a consequence scene: a calm episode needs story scenes after the day card")
    cq = plan["choice"].get("line")
    chl, rel_t = plan["choice"].get("lines"), {}
    if chl:    # C4: the question, both choices and the hook are four narrated lines; the card lasts as long as they take
        t_rel = JOIN_S + 0.3
        for k in ("question", "choice1", "choice2", "hook"):
            tk = ep.take(chl[k])
            if not tk.is_file():
                raise Fail("VOICE-MISSING", f"no take for {chl[k]} at {tk}: the voice stage comes before the shots")
            d = wav_seconds(tk)
            rel_t[k] = (round(t_rel, 4), round(t_rel + d, 4))
            t_rel += d + CHOICE_GAP_S
        cdur = t_rel - CHOICE_GAP_S + CHOICE_TAIL_S
        if cdur > MAX_CHOICE_S:
            raise Fail("PLAN-DURATION", f"the choice sequence would last {cdur:.2f} s (> {MAX_CHOICE_S} s): shorten the question, the choices or the hook")
    else:
        cdur = min(MAX_CARD_S, max(5.0, (wav_seconds(ep.take(cq)) + 1.2) if cq and ep.take(cq).is_file() else 5.0))
    card("choice", cdur)
    card("follow", 2.5)
    t, starts = 0.0, []
    for i, it in enumerate(items):
        it["t0"] = round(t if i == 0 else t - JOIN_S, 4)
        t = it["t0"] + it["dur"]
        it["t1"] = round(t, 4)
        if it["line"]:
            it["voice_t0"] = round(it["t0"] + (JOIN_S if i else 0) + VOICE_LEAD_S + float(it.get("lead_hold") or 0.0), 4)
        starts.append(it["t0"])
    if chl:
        ch = next(it for it in items if it["id"] == "choice")
        ch["line"], ch["voice_t0"] = chl["question"], round(ch["t0"] + rel_t["question"][0], 4)
        ch["more_lines"] = [{"line": chl[k], "voice_t0": round(ch["t0"] + rel_t[k][0], 4), "role": k} for k in ("choice1", "choice2", "hook")]
        sp = plan["choice"].get("split")
        if sp:
            ch["cap_y"] = sp.get("captions_y", 640)
            vfx = sp.get("vfx") or ["flash"]
            cuts = []
            for i, c in enumerate(sp["cuts"]):
                a, b = rel_t[c["at"]]
                cuts.append({"t": round(a + c.get("frac", 0.0) * (b - a), 3), "clip": c["clip"], "vfx": vfx[i % len(vfx)]})
            cuts.sort(key=lambda c: c["t"])
            lit = [{"state": k, "t0": rel_t[k][0], "t1": rel_t[k][1] if k != "hook" else round(ch["dur"] - 0.3, 3)} for k in ("question", "choice1", "choice2", "hook")]
            ch["split"] = {"first": sp.get("first", "A"), "top": sp["top"], "cuts": cuts, "lit": lit}
    elif cq:
        ch = next(it for it in items if it["id"] == "choice")
        ch["line"] = cq
        ch["voice_t0"] = round(ch["t0"] + JOIN_S + 0.3, 4)
    import calm_sfx    # C3: every join has a declared cut type: ONE name gives the visual (xfade) and the sound; a plan without `transitions` gets the defaults by template
    decl = {(t["from"], t["to"]): t["cut"] for t in plan.get("transitions", [])}
    pairs = {(a["id"], b["id"]) for a, b in zip(items, items[1:])}
    stray = [f"{a} -> {b}" for (a, b) in decl if (a, b) not in pairs]
    if stray:
        raise Fail("PLAN-TRANSITION", f"transitions name joins the episode does not have: {', '.join(stray[:4])}")
    for i, it in enumerate(items):
        if i:
            cut = decl.get((items[i - 1]["id"], it["id"])) or calm_sfx.default_cut(it)
            vfx_n, xf, snd = calm_sfx.CUTS[cut][:3]
            it["join_in"] = {"cut": cut, "vfx": vfx_n, "xfade": xf, "sound": snd}
    tl = {"episode": ep.id, "series": ep.series, "fps": FPS, "canvas": [W, H], "profile": "calm", "day": plan["day"], "place": plan.get("place", ""), "items": items,
          "total_s": round(items[-1]["t1"], 4), "join_s": JOIN_S}
    if label:
        tl["episode_label"] = label      # the HUD strip (first STRIP_S of the first HUD) and the recap tag say this (DESIGN.md 2.3)
        tl["strip_s"] = STRIP_S
    write_json(ep.timeline_p, tl)
    return {"items": len(items), "total_s": tl["total_s"]}


def _clock_minutes(text: str) -> int:
    m = re.search(r"(\d{1,2})[:٫.](\d{2})", str(text).translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")))
    if not m:
        return 9 * 60
    h, mi = int(m.group(1)), int(m.group(2))
    pm = "م" in str(text) or "PM" in str(text).upper()
    if pm and h < 12:
        h += 12
    return h * 60 + mi


def _clock_text(minutes: int) -> str:
    h, mi = divmod(minutes % (24 * 60), 60)
    suffix = "م" if h >= 12 else "ص"
    h12 = h % 12 or 12
    return f"{h12}:{mi:02d} {suffix}".translate(AR_DIGITS)


# ------------------------------------------------------------------ word timing (numpy, no model)
def envelope(path: Path, hop_s: float = 0.01):
    import numpy as np
    with wave.open(str(path), "rb") as w:
        n, sr, ch, sw = w.getnframes(), w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(n)
    a = np.frombuffer(raw, dtype={1: np.uint8, 2: np.int16, 4: np.int32}[sw]).astype(np.float64)
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    a = a / (float(2 ** (8 * sw - 1)) if sw > 1 else 128.0)
    hop = max(1, int(sr * hop_s))
    k = len(a) // hop
    env = np.sqrt((a[: k * hop].reshape(k, hop) ** 2).mean(axis=1) + 1e-12) if k else np.zeros(1)
    return env, hop_s


VOICED_GAP_S = 0.10           # a dip shorter than this inside speech is not a pause
VOICED_MIN_S = 0.05
PAUSE_SNAP_S = 0.20           # a word boundary that falls this close (voiced seconds) to a real pause moves onto it


def voiced_spans(env, hop: float) -> list[tuple[float, float]]:
    """(start, end) seconds of the voiced stretches of a take, from its own energy: frames within 38 dB of the peak (floor -55 dB), dips under
    VOICED_GAP_S bridged, specks under VOICED_MIN_S dropped. Empty take: the whole file."""
    import numpy as np
    db = 20 * np.log10(env + 1e-9)
    thr = max(db.max() - 38.0, -55.0)
    act = np.where(db > thr)[0]
    if not len(act):
        return [(0.0, len(env) * hop)]
    spans, a, b = [], act[0], act[0]
    for i in act[1:]:
        if (i - b) * hop > VOICED_GAP_S:
            spans.append((a * hop, (b + 1) * hop))
            a = i
        b = i
    spans.append((a * hop, (b + 1) * hop))
    keep = [s for s in spans if s[1] - s[0] >= VOICED_MIN_S]
    return keep or [(act[0] * hop, (act[-1] + 1) * hop)]


def word_timing(path: Path, words: list[str], weights: list[float] | None = None) -> list[tuple[float, float]]:
    """Seconds (start, end) of each word inside the take. ESTIMATED, not measured per word (no model, no ASR: banned): the voiced stretches of the take
    come from its own energy, the words are laid over the VOICED time only by weight, so a pause inside the line (a comma, a breath) is never spent on a
    word and the highlight waits for the voice after it. `weights` is a per-word syllable weight (cap_sentence.syllable_weights, from the vowelled
    text); without it, Arabic letters + 1. A boundary inside a stretch snaps to the quietest 10 ms frame within +-60 ms."""
    import numpy as np
    env, hop = envelope(path)
    spans = voiced_spans(env, hop)
    wts = np.array(weights if weights is not None else [max(1, len(AR_LETTER.findall(w))) + 1.0 for w in words], dtype=float)
    total = sum(b - a for a, b in spans)
    cum = np.concatenate([[0.0], np.cumsum(wts) / wts.sum()]) * total
    edges = np.cumsum([b - a for a, b in spans])[:-1]          # voiced-time of every pause: pauses sit between words (at punctuation), never inside one
    if len(edges):
        for i in range(1, len(words)):
            k = int(np.argmin(np.abs(edges - cum[i])))
            if abs(edges[k] - cum[i]) <= PAUSE_SNAP_S:
                cum[i] = edges[k]
        cum = np.maximum.accumulate(cum)

    def at(vt: float, start_side: bool) -> tuple[float, bool]:
        acc = 0.0
        for a, b in spans:
            if vt < acc + (b - a) - 1e-9 or (not start_side and vt <= acc + (b - a) + 1e-9):
                return a + (vt - acc), abs(vt - acc) < 1e-9 or abs(vt - acc - (b - a)) < 1e-9
            acc += b - a
        return spans[-1][1], True
    out = []
    prev_end = spans[0][0]
    for i in range(len(words)):
        s, s_edge = at(float(cum[i]), True)
        e, e_edge = at(float(cum[i + 1]), False)
        if not s_edge and i > 0:
            j0, j1 = int(max(0, (s - 0.06) / hop)), int(min(len(env) - 1, (s + 0.06) / hop))
            s = max(prev_end + 0.0, (j0 + int(np.argmin(env[j0:j1 + 1]))) * hop) if j1 >= j0 else s
        out.append([s, e, e_edge])
        prev_end = e
    # a snapped end must equal the next word's snapped start when the two touch inside one stretch; every word keeps at least 0.08 s
    for i in range(len(out) - 1):
        if not out[i][2]:
            out[i][1] = out[i + 1][0]
    res, t = [], 0.0
    for s, e, _ in out:
        s = max(s, t)
        e = max(e, s + 0.08)
        res.append((round(s, 3), round(e, 3)))
        t = e
    return res


def _text_with_gloss(words: list[str], group: list[int], gm: dict) -> list[str]:
    """The tokens of one plate's text: its words, each glossary word followed by (meaning)."""
    out = []
    for j in group:
        out.append(words[j])
        if j in gm:
            out.append(f"({gm[j]['meaning_ar']})")
    return out


def group_words(words: list[str], max_words: int = CAP_WORDS_MAX, max_chars: int = 13) -> list[list[int]]:
    """Indexes of the words, grouped 1 to 3 per plate; a long word stands alone."""
    groups, cur = [], []
    for i, w in enumerate(words):
        if cur and (len(cur) >= max_words or sum(len(words[j]) for j in cur) + len(w) + len(cur) > max_chars):
            groups.append(cur)
            cur = []
        cur.append(i)
    if cur:
        groups.append(cur)
    return groups


# ------------------------------------------------------------------ stage: captions (plates) and HUD
def plate_html(groups_states: list[dict], hud_items: list[dict], accent: str = "#c6ff3d", with_ref: bool = False) -> str:
    """The caption plates. The dark outline is NOT `-webkit-text-stroke` on the fill glyphs: Arabic letters overlap their neighbours, so a
    centred stroke of the next glyph cut a dark seam into the previous letter at every join and word end (the owner 2026-10-25, C1). Each word
    carries its outline as a `::before` under-layer (z-index -1 inside the plate's own stacking context), painted below EVERY fill.
    with_ref adds a fill-only twin of each plate (`.ref`, id r<k>, same layout) that CAP-ARABIC-SHAPING compares against."""
    import compose as C
    parts = []
    for k, st in enumerate(groups_states):
        lines = st.get("lines") or [list(range(len(st["words"])))]     # a sentence is one or two lines of word indexes; a bare word list is one line
        spans = "".join('<div class="ln">' + "".join(f'<span data-t="{_esc(st["words"][j])}" class="{"on" if j == st["active"] else ""}">{_esc(st["words"][j])}</span>' for j in ln) + "</div>" for ln in lines)
        carry = [f"{c['word']} ({c['meaning']})" for c in st.get("carry", [])]     # the meaning of an earlier sentence of the line that is still being read
        if st.get("gloss") or carry:   # the meaning of a foreign word, in brackets, on its own smaller line under the words (CLAUDE.md "Gloss foreign words")
            own = [f"{w} ({m})" for w, m in st["gloss_pairs"]] if st.get("gloss_pairs") else ([("(" + " · ".join(st["gloss"]) + ")")] if st.get("gloss") else [])
            gtxt = " · ".join(own + carry)
            spans += f'<div class="gl"><span data-t="{_esc(gtxt)}">{_esc(gtxt)}</span></div>'
        parts.append(f'<div class="cap{" obj" if st.get("style") == "object" else ""}" id="c{k}" dir="rtl" lang="ar">{spans}</div>')
        if with_ref:
            parts.append(f'<div class="cap ref{" obj" if st.get("style") == "object" else ""}" id="r{k}" dir="rtl" lang="ar">{spans}</div>')
    for k, h in enumerate(hud_items):
        strip = f'<span class="strip">{_esc(h["strip"])}</span>' if h.get("strip") else ""
        parts.append(f'<div class="hud" id="h{k}" dir="rtl" lang="ar">{strip}<b class="day">{_esc(h["day"])}</b><span>{_esc(h["clock"])}</span><span>{_esc(h["place"])}</span></div>')
    css = (f"{C.font_css(1.0)}html,body{{margin:0;background:transparent}}"
           f".cap{{display:block;width:max-content;position:relative;isolation:isolate;margin:40px 40px;padding:6px {CAP_PAD_X}px;font-family:'thmanyahsans';font-weight:900;font-size:{CAP_FONT_PX}px;line-height:{round(CAP_FONT_PX*1.35)}px;color:#fff;white-space:nowrap;"
           f"font-kerning:normal;letter-spacing:0;word-spacing:0;text-rendering:optimizeLegibility}}"
           f".cap .gl{{display:block;text-align:center;font-size:{GLOSS_FONT_PX}px;line-height:{round(GLOSS_FONT_PX*1.35)}px;font-weight:700;color:#fff3c9;margin-top:2px}}.cap .gl span{{margin:0}}"
           f".cap .ln{{display:block;text-align:center;white-space:nowrap}}"
           f".cap .ln .gl-in{{font-size:{GLOSS_FONT_PX}px;font-weight:700;color:#fff3c9;margin:0 {GLOSS_INLINE_GAP_PX}px 0 .22em}}"      # F-001: a meaning that fits beside the last row of the sentence sits there (the plate stays two rows tall)
           f".cap span{{display:inline-block;position:relative;margin:0 .22em}}.cap span.on{{color:{accent}}}"
           f".cap span::before{{content:attr(data-t);position:absolute;inset:0;z-index:-1;color:rgb(10,8,6);-webkit-text-stroke:9px rgb(10,8,6);text-shadow:0 6px 18px rgba(0,0,0,.55)}}"
           f".cap.ref span::before{{display:none}}"
           f".cap.obj span{{font-family:'thmanyahserifdisplay';color:#f4cf6a}}.cap.obj span.on{{color:#fff3c9}}"   # C3: engraved in the plate's own letters (serif display, brass gold)
           f".hud{{display:inline-flex;flex-direction:column;align-items:flex-start;gap:4px;margin:10px;padding:10px 22px;border-radius:14px;background:rgba(10,8,6,.55);font-family:'thmanyahsans';font-size:44px;font-weight:700;color:#f3ede4;line-height:1.25}}"
           f".hud .day{{font-size:56px;font-weight:900;color:#ff4d4d}}"
           f".hud .strip{{font-size:40px;font-weight:700;color:#f3ede4;opacity:.92;padding-bottom:6px;margin-bottom:2px;border-bottom:3px solid rgba(243,237,228,.45);white-space:nowrap}}")
    return f'<!doctype html><meta charset="utf-8"><style>{css}</style>{"".join(parts)}'


def _esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def measure_words(words: list[str], work: Path) -> dict[str, float]:
    """Width in px of each distinct word as the caption draws it (Thmanyah Sans Black 104 px), measured in the same Chrome the plates use."""
    import compose as C
    res: dict[str, float] = {}
    html = plate_html([{"words": [w], "active": 0} for w in words], [])

    def go(pg):
        pg.evaluate("document.fonts.load('900 104px thmanyahsans', 'هدى').then(() => document.fonts.ready).then(() => 1)")
        ws = pg.evaluate("Array.from(document.querySelectorAll('.cap .ln > span')).map(s => s.getBoundingClientRect().width)")
        res.update(dict(zip(words, ws)))
        return True
    C.chrome_page(html, work, W, H, go)
    if len(res) != len(words) or not all(v > 0 for v in res.values()):
        raise Fail("CAP-MEASURE", f"measured {len(res)} of {len(words)} words")
    return res


def face_boxes_by_item(ep: Ep, tl: dict) -> dict[str, list[dict]]:
    """F-001: the face boxes of every item of the timeline in screen px, read from each shot's own rig trace (cap_face.shot_face_boxes); the choice sequence gets the faces its
    two top-half close-ups show. A scene with no trace is a hard stop: a plate cannot be proved clear of a face nobody located."""
    sb, missing = {}, []
    for it in tl["items"]:
        if it["kind"] == "scene":
            try:
                sb[it["id"]] = CF.shot_face_boxes(ep.root / "work" / "shots" / it["shot"])
            except (FileNotFoundError, KeyError) as e:
                missing.append(str(e))
    if missing:
        raise Fail("CAP-FACE-CLEAR", "no face data (run the shots first): " + "; ".join(missing[:3]))
    out = dict(sb)
    for it in tl["items"]:
        if it.get("split"):
            out[it["id"]] = CF.choice_face_boxes(it, sb, {c["id"]: c["shot"] for c in it["split"]["top"]}, TOP_H, W)
    return out


def _face_boxes_for_plate(tl: dict, boxes: dict, p: dict, t0: float | None = None, t1: float | None = None) -> list[dict]:
    return CF.window_face_boxes(tl["items"], boxes, p["start"] if t0 is None else t0, p["end"] if t1 is None else t1, FACE_GRACE_S)


def mark_avoid_box() -> dict:
    """The NJ mark's rect grown by WATERMARK-CLEAR's pad: a plate moved off a face must not land on the mark either. Root cause (E03, 2026-10-28): the choice plates were
    lifted above a face to y 384, 6 px under the mark, and the episode gate failed WATERMARK-CLEAR; E02 cleared it at y 390 by chance."""
    r, p = WM.rect(), WM.PAD_PX
    return {"x": r["x"] - p, "y": r["y"] - p, "w": r["w"] + 2 * p, "h": r["h"] + 2 * p, "char": "NJ mark"}


def _hud_boxes(hud: list[dict], t0: float, t1: float) -> list[dict]:
    pad = CF.HUD_PAD_PX
    return [{"x": h["x"] - pad, "y": h["y"] - pad, "w": h["w"] + 2 * pad, "h": h["h"] + 2 * pad} for h in hud if h.get("w") and hud_window(h)[0] < t1 and hud_window(h)[1] > t0]


def hud_window(h: dict) -> tuple[float, float]:
    """When a HUD plate is on screen: its own show window (the strip plate and the plate that takes over from it), else the scene's span less half a join each side."""
    return (h["show0"], h["show1"]) if "show0" in h else (h["t0"] + JOIN_S / 2, h["t1"] - JOIN_S / 2)


def place_clear_of_faces(ep: Ep, tl: dict, caps: list[dict], hud: list[dict]) -> dict:
    """F-001: move each sentence plate off every face on screen while it is up. A sentence keeps ONE position for all its states when one exists (the highlight changes
    word to word, the plate does not wander); if no single position clears the faces of the shots it crosses (a sentence over a join between two close-ups), each state is
    placed for its own window, so the plate moves only where the picture forces it. Position = the legal one nearest the original (cap_face.place_plate): inside the safe
    area, bottom edge at most PLATE_BOTTOM_MAX (the bound CALM-PLATE-SAFE already allowed), clear of the HUD when possible; the choice sequence keeps its plates in the top half.
    Mutates caps (x, y, `moved_for_face`). Returns counts."""
    boxes = face_boxes_by_item(ep, tl)
    groups: dict[tuple, list[dict]] = {}
    for c in caps:
        groups.setdefault((c["line"], c["unit"]), []).append(c)
    n_moved = n_split = 0
    for (lid, u), grp in groups.items():
        if all(c.get("style") == "object" for c in grp):
            # An engraved plate (C3) lives ON the brass plate: it never moves for a face, and its engraving goes with the plate. Root cause (E01C, 2026-10-25): the last state ran 0.11 s into the
            # page turn onto s02, over the 0.1 s grace, so the whole sentence was thrown 206 px down and its second line crossed the plate's own border. The engraving now ends when the next shot begins.
            nxt = [it["t0"] for it in tl["items"] if it["t0"] > min(c["start"] for c in grp) + 1e-6]
            if nxt:
                for c in grp:
                    c["end"] = round(min(c["end"], min(nxt)), 3)
            continue
        t0, t1 = min(c["start"] for c in grp), max(c["end"] for c in grp)
        in_choice = any(it.get("split") and it["t0"] <= t0 < it["t1"] for it in tl["items"])
        ymax = TOP_H - 8 if in_choice else PLATE_BOTTOM_MAX
        w, h = max(c["w"] for c in grp), max(c["h"] for c in grp)
        x0, y0 = grp[0]["x"], min(c["y"] for c in grp)
        av = _face_boxes_for_plate(tl, boxes, grp[0], t0, t1) + [mark_avoid_box()]
        if not any(CF.intersects({"x": x0, "y": y0, "w": w, "h": h}, b) for b in av):
            continue
        pos = CF.place_plate(w, h, (x0, y0), av, _hud_boxes(hud, t0, t1), SAFE, ymax)
        if pos:
            for c in grp:
                c.update({"x": pos[0] + (w - c["w"]) // 2, "y": pos[1] + (h - c["h"]), "moved_for_face": True})
                n_moved += 1
            continue
        for c in grp:      # no single place for the whole sentence: this state alone
            avc = _face_boxes_for_plate(tl, boxes, c) + [mark_avoid_box()]
            pc = CF.place_plate(c["w"], c["h"], (c["x"], c["y"]), avc, _hud_boxes(hud, c["start"], c["end"]), SAFE, ymax)
            if not pc:
                raise Fail("CAP-FACE-CLEAR", f"no place for plate «{c['text']}» ({lid} unit {u}, {c['start']:.2f}-{c['end']:.2f} s, {c['w']}x{c['h']} px) outside the faces on screen: shorten the sentence or split it")
            c.update({"x": pc[0], "y": pc[1], "moved_for_face": True})
            n_moved += 1
        n_split += 1
    return {"plates_moved": n_moved, "sentences_placed_per_state": n_split, "sentences": len(groups)}


def _unit_need_s(shown_words: list[str], n_words: int) -> float:
    """The least a sentence plate stays up: the larger of CAP-READING-SPEED (max(1.5 s, chars / 12 cps)) and CAP-READ-TIME (0.4 s + 0.3 s a word, its bracketed meaning counted), the two checks the plate must pass."""
    txt = " ".join(shown_words)
    gloss_words = sum(len(m.split()) for m in re.findall(r"\(([^)]*)\)", txt))
    return max(CS.read_speed_need_s(CS.visible_chars(txt)), CS.read_budget_s(n_words + gloss_words))


def caption_states(ep: Ep, tl: dict, script: dict, work: Path | None = None) -> tuple[list, list, dict, dict, list]:
    """The caption plates as DATA (no pixels): every sentence unit with its highlight windows, the HUD items, the timing method per line, the measured word widths and the
    text chunks the shaping check reads. Shared by stage_captions (which then draws the plates) and tools/animatic.py (the early preview, before any shot is rendered).
    Raises Fail (CAP-TASHKEEL, CAP-ARABIC-SHAPING). `work` is the folder the width measurement may write its page in."""
    work = Path(work) if work else ep.work
    lines = {l["id"]: l for l in script["lines"]}
    glossary = G.load(ep.root, script.get("series") or ep.series)
    states, timing_info, unit_gloss_pairs = [], {}, {}
    heal_cuts = cap_heal_cuts(ep.root, ep.id)       # R-506: plates the caption heal cut in two
    spoken = []
    for it, ln_it in _spoken(tl["items"]):
        words = display_text(lines[ln_it["line"]]["text"]).split()
        if words:
            spoken.append((it, ln_it, words))
    px = measure_words(sorted({w for _, _, ws in spoken for w in ws}), work)         # real Thmanyah widths: a sentence is wrapped to what fits, not to a guess
    margin = 2 * 0.22 * CAP_FONT_PX
    width_fn = lambda ws: sum(px[w] for w in ws) + margin * len(ws)
    starts_sorted = sorted(l_["voice_t0"] for _, l_, _w in spoken)
    for it, ln_it, words in spoken:
        line = lines[ln_it["line"]]
        weights, method = CS.syllable_weights(" ".join(words), line.get("tts_text"))
        timing = word_timing(ep.take(ln_it["line"]), words, weights)   # timing is over the SPOKEN words only; a gloss is never spoken
        timing_info[ln_it["line"]] = method
        gm = G.gloss_map(words, line.get("speaker"), G.line_entries(line, glossary))
        glued = {i for idx, e in gm.items() for i in range(idx - len(G._key(e)) + 1, idx)}   # a glossary phrase (بور لو دوسييه) is never cut in two plates
        abs_t = [(round(ln_it["voice_t0"] + a_, 3), round(ln_it["voice_t0"] + b_, 3)) for a_, b_ in timing]
        later = [t_ for t_ in starts_sorted if t_ > ln_it["voice_t0"] + 1e-6]
        room_end = (later[0] - 0.02) if later else abs_t[-1][1] + 2.0      # the plate of the line's last sentence may stay up until the next line's plate starts

        def short_fn(idx, is_last, words=words, gm=gm, abs_t=abs_t, room_end=room_end):
            """C12: this unit, as the voice leaves it on screen, is up for less than max(1.5 s, chars / 12 cps)."""
            shown = (room_end if is_last else abs_t[idx[-1] + 1][0]) - abs_t[idx[0]][0]
            txt = " ".join(_text_with_gloss(words, idx, gm))
            return shown + 1e-6 < CS.read_speed_need_s(CS.visible_chars(txt))
        units = CS.split_units(words, width_fn, CAP_LINE_W_MAX, glued, set(gm), short_fn, heal_cuts.get(ln_it["line"]))
        last = units[-1]
        need_last = CS.read_speed_need_s(CS.visible_chars(" ".join(_text_with_gloss(words, last["idx"], gm))))
        tail = max(CS.TAIL_S, abs_t[last["idx"][0]][0] + need_last - abs_t[-1][1])      # C12: the last sentence holds until it has been readable long enough (the plan made the room)
        win = CS.unit_windows(units, abs_t, abs_t[-1][1], None, tail)
        own = it if it.get("line") == ln_it["line"] else {}      # R-503: the silence the plan added before this scene's voice may be used by the FIRST plate (never by the others, never a loosened cap)
        CS.borrow_lead(win, {k_: _unit_need_s(_text_with_gloss(words, u_["idx"], gm), len(u_["idx"])) for k_, u_ in enumerate(units)}, first_max=CS.LEAD_MAX_S + float(own.get("lead_hold") or 0.0))
        for st in win:
            u = units[st["unit"]]
            first = u["idx"][0]
            local = [[j - first for j in ln_] for ln_ in u["lines"]]
            gl = [gm[j]["meaning_ar"] for j in u["idx"] if j in gm]   # the meaning stays under the sentence for every state of its unit
            unit_gloss_pairs[(ln_it["line"], st["unit"])] = [(" ".join(words[j - len(G._key(gm[j])) + 1: j + 1]).rstrip("،,.؟?!؛:"), gm[j]["meaning_ar"]) for j in u["idx"] if j in gm]
            states.append({"line": ln_it["line"], "words": [words[j] for j in u["idx"]], "lines": local, "active": st["k"], "start": st["start"], "end": st["end"],
                           "style": it.get("cap_style"), "cap_y": it.get("cap_y"), "gloss": gl, "gloss_pairs": unit_gloss_pairs[(ln_it["line"], st["unit"])], "text": " ".join(_text_with_gloss(words, u["idx"], gm)),
                           "unit": st["unit"], "word_i": st["word"], "word_start": st["word_start"], "word_end": st["word_end"], "n_lines": len(local),
                           "clause_words": u["clause_words"], "split": u["split"]})
    # one plate on screen at a time: the last sentence of a line holds its tail, but never into the next line's first plate
    states.sort(key=lambda s: s["start"])
    for a, b in zip(states, states[1:]):
        if a["line"] != b["line"]:
            a["end"] = round(min(max(a["end"], a["start"] + 0.12), b["start"] - 0.02), 3)
        else:
            a["end"] = round(min(a["end"], b["start"]), 3)
    cap_plate_ends(states, {ln_it["line"]: it["t1"] - JOIN_S for it, ln_it, _w in spoken if it.get("kind") == "scene"})
    for lid_ in dict.fromkeys(st["line"] for st in states):      # a glossed sentence that is up too briefly hands its meaning to the plates after it
        ls = [st for st in states if st["line"] == lid_]
        ug = {st["unit"]: unit_gloss_pairs[(lid_, st["unit"])] for st in ls if unit_gloss_pairs.get((lid_, st["unit"]))}
        CS.carry_glosses(ls, ug, {st["unit"]: len(st["words"]) for st in ls})
    hud = []
    label = tl.get("episode_label")
    for it in tl["items"]:
        if it["kind"] == "scene":
            base = {"id": it["id"], "day": hud_day(it, tl), "clock": it["clock"], "place": tl.get("place", ""), "t0": it["t0"], "t1": it["t1"]}
            if label and not any(h_.get("strip") for h_ in hud):
                # DESIGN.md 2.3: the first HUD plate carries «الحلقة N · the series» as its first row for STRIP_S, then the normal three rows (two plates, one handover, no gap)
                a, b = it["t0"] + JOIN_S / 2, it["t1"] - JOIN_S / 2
                cut = min(b, a + float(tl.get("strip_s", STRIP_S)))
                hud.append({**base, "strip": label, "show0": round(a, 4), "show1": round(cut, 4)})
                if cut < b - 1e-6:
                    hud.append({**base, "show0": round(cut, 4), "show1": round(b, 4)})
            else:
                hud.append(base)
    for h in hud:
        for k, v in h.items():
            if k in ("day", "clock", "place", "strip") and has_tashkeel(v):
                raise Fail("CAP-TASHKEEL", f"HUD {k} carries tashkeel")
    import cap_shaping
    chunks = [{"words": st["words"], "active": st["words"][st["active"]]} for st in states]
    chunks += [{"words": " ".join(st["gloss"]).split(), "active": None} for st in states if st["gloss"]]
    chunks += [{"words": f"{c['word']} {c['meaning']}".split(), "active": None} for st in states for c in st.get("carry", [])]   # the gloss words must join like any caption word (appended after the plates: pairs align with the plates)
    text_f = cap_shaping.shaping_problems(chunks, [])
    if text_f:
        raise Fail("CAP-ARABIC-SHAPING", "; ".join(text_f[:4]))
    return states, hud, timing_info, px, chunks


def stage_captions(ep: Ep) -> dict:
    import compose as C
    tl, script = read_json(ep.timeline_p), read_json(ep.script_p)
    states, hud, timing_info, _px, chunks = caption_states(ep, tl, script)
    caps = []
    import cap_shaping
    html = plate_html(states, hud, with_ref=True)
    pdir = ep.work / "plates"
    pdir.mkdir(parents=True, exist_ok=True)

    pairs = []

    inline_ids: set[str] = set()

    def go(pg):
        import io
        import numpy as np
        from PIL import Image
        # F-001: a bracketed meaning goes on the last row of the sentence when it fits beside it in the plate width, so a glossed sentence is as tall as a plain one
        # (a third row of 88 px left no place outside a close-up's face for the plate). Same move on the plate and on its CAP-ARABIC-SHAPING twin.
        moved = pg.evaluate("""([maxw, gap, faces]) => Promise.all(faces.map(f => document.fonts.load(f, 'هدى'))).then(() => document.fonts.ready).then(() => {
            const ids = [];
            document.querySelectorAll('.cap').forEach(c => {
                const gl = c.querySelector('.gl'); if (!gl) return;
                const lns = c.querySelectorAll('.ln'); const last = lns[lns.length - 1]; if (!last) return;
                const gs = gl.querySelector('span');
                const lw = Array.from(last.children).reduce((a, s) => a + s.getBoundingClientRect().width, 0);
                const gw = gs.getBoundingClientRect().width;
                if (lw + gap + gw + 40 <= maxw) { gs.classList.add('gl-in'); last.appendChild(gs); gl.remove(); ids.push(c.id); }
            });
            return ids; })""", [CAP_LINE_W_MAX + 2 * CAP_PAD_X, GLOSS_INLINE_GAP_PX, measure_faces()])
        inline_ids.update(moved)
        for k, st in enumerate(states):
            el = pg.locator(f"#c{k}")
            out = pdir / f"c{k:04d}.png"
            el.screenshot(path=str(out), omit_background=True)
            ref = pg.locator(f"#r{k}").screenshot(omit_background=True)
            pairs.append((np.array(Image.open(out).convert("RGBA")), np.array(Image.open(io.BytesIO(ref)).convert("RGBA"))))
            bb = el.bounding_box()
            fixed = st.get("style") == "object" or st.get("cap_y")          # a plate with its own place (the brass plate, the choice sequence) keeps its top edge
            y = (st.get("cap_y") or CAP_Y) if fixed else max(SAFE[1], CAP_Y + CAP_H1 - round(bb["height"]))   # otherwise the bottom edge stays put and a second line grows upwards
            caps.append({"line": st["line"], "text": st["text"], "gloss": st["gloss"], "active": st["words"][st["active"]], "active_index": st["active"], "word_i": st["word_i"],
                         "unit": st["unit"], "n_lines": st["n_lines"], "carry": st.get("carry", []), "clause_words": st["clause_words"], "split": st["split"],
                         "start": st["start"], "end": st["end"], "word_start": st["word_start"], "word_end": st["word_end"], "png": f"plates/c{k:04d}.png",
                         "w": round(bb["width"]), "h": round(bb["height"]), "x": round((W - bb["width"]) / 2), "y": y, "font_px_1080": CAP_FONT_PX, "style": st.get("style"), "gloss_inline": f"c{k}" in inline_ids})
        for k, h in enumerate(hud):
            el = pg.locator(f"#h{k}")
            out = pdir / f"h{k:03d}.png"
            el.screenshot(path=str(out), omit_background=True)
            bb = el.bounding_box()
            h.update({"png": f"plates/h{k:03d}.png", "w": round(bb["width"]), "h": round(bb["height"]), "x": HUD_XY[0], "y": HUD_XY[1]})
        return True
    C.chrome_page(html, ep.work, W, H, go)
    seams = [round(cap_shaping.seam_ratio(pl, rf), 5) for pl, rf in pairs]
    shape_f = cap_shaping.shaping_problems(chunks, pairs)
    if shape_f:
        raise Fail("CAP-ARABIC-SHAPING", "; ".join(shape_f[:4]))
    for c, r in zip(caps, seams):
        c["seam_ratio"] = r
    face_info = place_clear_of_faces(ep, tl, caps, hud)
    for c in caps:
        if c["x"] < SAFE[0] or c["x"] + c["w"] > SAFE[2]:
            raise Fail("CAP-SAFE", f"plate '{c['text']}' is {c['w']} px wide and leaves the safe area: shorten the line or split the words")
    write_json(ep.caps_p, {"captions": caps, "mode": "sentence", "unit_words_max": CS.UNIT_WORDS_MAX, "unit_lines_max": CS.UNIT_LINES_MAX, "font_px_1080": CAP_FONT_PX,
                           "seam_max": cap_shaping.SEAM_MAX, "timing": "estimated: voiced stretches of each take from its energy, words laid over them by weight (no ASR, banned)",
                           "timing_method": timing_info, "face_clear": face_info})
    write_json(ep.hud_p, {"hud": hud})
    return {"plates": len(caps), "hud": len(hud), **face_info}
