# -*- coding: utf-8 -*-
"""Full-sentence captions with the spoken word highlighted (owner, 2026-10-25, note C7 on E01 calm v3).

the owner: "make it display full sentences, not just words, and highlight the word you are speaking now, so the viewer has enough time to see."
This replaces the 1-3 word plates of 2026-10-24. Pure text and number logic (no browser, no model); tools/calm_compose.py draws and times the plates.

  split_units(words, width_fn, glued)     the words of one script line -> units: a whole sentence, else a whole clause, else (only when a clause
                                          cannot fit two lines) a balanced cut. Each unit: {"idx": [...], "lines": [[...], [...]], "clause_words", "split"}
  wrap_lines(words, width_fn)             one or two balanced lines inside the plate width, None when it does not fit
  syllable_weights(text, tts_text)        per word timing weight from the vowelled copy (vowel marks = syllables, shadda longer), letters when it cannot align
  unit_windows(...)                       the plate windows: each word's highlight, then the sentence held to the end of the line plus a short tail
  check_plates(plates, lines, ...)        CAP-FULL-SENTENCE, CAP-READ-TIME, CAP-READING-SPEED problems over captions.json plates

Honest limit: no model and no ASR (both banned), so word times are an estimate: the voiced stretches of the take come from its own energy, and the
words are laid over them by syllable weight (the same method as the lip-sync visemes). CAP-FULL-SENTENCE therefore allows SYNC_TOL_S of drift between a
plate's highlight and an independent recomputation, not frame accuracy.
"""
from __future__ import annotations

import re

UNIT_WORDS_MAX = 8        # a whole clause on two lines of a 1080 px phone screen at 104 px letters
UNIT_LINES_MAX = 2
SHORT_UNIT_WORDS = 2      # a sentence of this many words or fewer (an exclamation, "لا...") would flash by: it takes the next sentence along when both fit
TAIL_S = 0.6              # the finished sentence stays this long after its last word (or until the next plate starts)
READ_BASE_S = 0.4         # reading budget of a unit: orientation + READ_PER_WORD_S per word (3.3 words a second)
READ_PER_WORD_S = 0.30
READ_MIN_S = 1.5          # C12 (owner, 2026-10-25: "captions are still too fast to read"): a plate never stays up less than this, however short
READ_CPS = 12.0           # ... and never less than its characters divided by this reading rate. JUDGEMENT, not a measured Arabic figure: no source was found that gives one Arabic
                          # silent-reading rate for on-screen captions (the Netflix timed-text guide page fetched 2026-10-25 states 5/6 s minimum and 7 s maximum per event, and keeps its
                          # CPS limits on a language page that was not retrieved). 12 characters a second is deliberately slower than the 17 to 20 cps commonly used for adult
                          # subtitles in other languages [NOT VERIFIED here], because a phone, a 104 px display face and a diacritic-free Arabic text read slower, and the viewer is
                          # also watching an animation. Tune it by the owner's eye; it lives in this one place.
SYNC_TOL_S = 0.08         # a highlight may start this far from the recomputed word start
MIN_PLATE_S = 0.12
LEAD_MAX_S = 0.06         # C12: a sentence the voice leaves on screen for a hair less than a reader needs may start this much before its first word, taking the time from the sentence
                          # before it when that one has it to spare. Kept under SYNC_TOL_S (0.08): the word times are an estimate with that much uncertainty already.
SENT_END = ".؟!?…"
CLAUSE_END = "،,؛:"
_CLOSERS = "»\"')]"
_MARKS = {"َ", "ُ", "ِ", "ً", "ٌ", "ٍ"}   # fatha damma kasra + tanween
_SHADDA = "ّ"
_AR = re.compile("[ء-يٱ]")


def _tail(w: str) -> str:
    return w.rstrip(_CLOSERS)


def ends_sentence(w: str) -> bool:
    t = _tail(w)
    return bool(t) and t[-1] in SENT_END


def ends_clause(w: str) -> bool:
    t = _tail(w)
    return bool(t) and (t[-1] in SENT_END or t[-1] in CLAUSE_END)


def wrap_lines(words: list[str], width_fn, max_w: float, max_lines: int = UNIT_LINES_MAX):
    """[[words...]] of one or two lines, the cut chosen to make the lines as even as possible; None when it cannot fit."""
    if not words:
        return None
    if width_fn(words) <= max_w:
        return [list(words)]
    if max_lines < 2:
        return None
    best = None
    for k in range(1, len(words)):
        a, b = words[:k], words[k:]
        wa, wb = width_fn(a), width_fn(b)
        if wa <= max_w and wb <= max_w:
            score = max(wa, wb)
            if best is None or score < best[0]:
                best = (score, [list(a), list(b)])
    return best[1] if best else None


def _fits(words, width_fn, max_w) -> bool:
    return len(words) <= UNIT_WORDS_MAX and wrap_lines(words, width_fn, max_w) is not None


def _cuts(words, glued: set[int], forced: set[int] | None = None):
    """Segments of the words ending at each sentence end, in index ranges (a, b) half open. `glued` boundaries (after word i) are never cut. `forced` (R-506, tools/cap_heal.py)
    are boundaries after word i that count as a sentence end too: the plate that had no place beside a face is cut there."""
    out, a = [], 0
    for i, w in enumerate(words):
        if (ends_sentence(w) or i in (forced or ())) and i not in glued:
            out.append((a, i + 1))
            a = i + 1
    if a < len(words):
        out.append((a, len(words)))
    return out


def _balanced_split(idx, words, width_fn, max_w, glued):
    """A clause too long for two lines: cut it in parts that each fit, choosing the cut nearest the middle that is not glued. Recursive."""
    ws = [words[i] for i in idx]
    if _fits(ws, width_fn, max_w) or len(idx) < 2:
        return [idx]
    cands = [k for k in range(1, len(idx)) if (idx[k - 1] not in glued)]
    if not cands:
        return [idx]
    k = min(cands, key=lambda c: abs(width_fn(ws[:c]) - width_fn(ws[c:])))
    return _balanced_split(idx[:k], words, width_fn, max_w, glued) + _balanced_split(idx[k:], words, width_fn, max_w, glued)


def split_units(words: list[str], width_fn, max_w: float, glued: set[int] | None = None, glossed: set[int] | None = None, short_fn=None, forced: set[int] | None = None) -> list[dict]:
    """The units of one line. Rule order: a whole sentence if it fits; else its clauses (comma cuts), merged while they fit; else a balanced cut of a
    clause that cannot fit two lines by itself (flagged `split`, and `clause_words` records how long the clause was so the gate can verify the excuse)."""
    glued = glued or set()
    glossed = glossed or set()
    forced = set(forced or ()) - glued          # R-506: cuts the caption heal asked for (only at a sentence or clause end, so CAP-FULL-SENTENCE still holds); never inside a glued glossary phrase
    units: list[dict] = []

    def add(idx, clause_words, split):
        ws = [words[i] for i in idx]
        lines = wrap_lines(ws, width_fn, max_w) or [ws]
        # lines are lists of line-local indexes into idx: keep absolute word indexes
        a, out = 0, []
        for ln in lines:
            out.append(idx[a:a + len(ln)])
            a += len(ln)
        units.append({"idx": list(idx), "lines": out, "clause_words": clause_words, "split": split})

    natural = _cuts(words, glued) if forced else []

    def inside(a, b):
        """R-506: a unit the caption heal cut out of the middle of a sentence is a `split` unit of that sentence (the same excuse CAP-FULL-SENTENCE already allows a balanced cut)."""
        return next(((nb - na) for na, nb in natural if na <= a and b <= nb and (na, nb) != (a, b)), None)
    for a, b in _cuts(words, glued, forced):
        idx = list(range(a, b))
        if _fits([words[i] for i in idx], width_fn, max_w):
            cw = inside(a, b)
            add(idx, cw if cw else len(idx), bool(cw))
            continue
        # clause pieces inside this sentence
        pieces, s = [], a
        for i in range(a, b):
            if ends_clause(words[i]) and i not in glued and i + 1 < b:
                pieces.append(list(range(s, i + 1)))
                s = i + 1
        pieces.append(list(range(s, b)))
        merged: list[list[int]] = []
        for p in pieces:
            if merged and _fits([words[i] for i in merged[-1] + p], width_fn, max_w):
                merged[-1] = merged[-1] + p
            else:
                merged.append(p)
        for p in merged:
            if _fits([words[i] for i in p], width_fn, max_w):
                add(p, len(p), False)
            else:
                for q in _balanced_split(p, words, width_fn, max_w, glued):
                    add(q, len(p), True)
    # C7/C8/C12: a very short sentence, one that carries a gloss, or (short_fn, C12) one the voice leaves on screen for less than a reader needs, takes the next whole
    # sentence along when both fit; a last unit that is too brief takes the one before it instead (the pause the plan adds is only for the line's end)
    def merged(a, b):
        both = a["idx"] + b["idx"]
        ws = [words[i] for i in both]
        lines = wrap_lines(ws, width_fn, max_w)
        out, pos = [], 0
        for ln in lines:
            out.append(both[pos:pos + len(ln)])
            pos += len(ln)
        return {"idx": both, "lines": out, "clause_words": len(both), "split": False}

    def fits2(a, b):
        return a["idx"][-1] not in forced and not a["split"] and not b["split"] and _fits([words[i] for i in a["idx"] + b["idx"]], width_fn, max_w)
    k = 0
    while k < len(units):
        a = units[k]
        last = k + 1 == len(units)
        brief = bool(short_fn and short_fn(a["idx"], last))           # up for less than a reader needs, as the voice leaves it
        needy = (not last) and (len(a["idx"]) <= SHORT_UNIT_WORDS or any(i in glossed for i in a["idx"]) or brief)
        if needy and fits2(a, units[k + 1]):
            units[k:k + 2] = [merged(a, units[k + 1])]
        elif brief and k > 0 and fits2(units[k - 1], a):               # C12: it cannot take the next sentence along (too wide): it joins the one before it
            units[k - 1:k + 1] = [merged(units[k - 1], a)]
            k -= 1
        else:
            k += 1
    return units


def syllable_weights(text: str, tts_text: str | None, pause: float = 0.25) -> tuple[list[float], str]:
    """(weights, method). From the vowelled tts_text: one syllable per vowel mark (a long vowel is a mark plus its letter, counted once), a shadda
    adds half a syllable, every word a small boundary weight. Falls back to Arabic letter counts when the vowelled copy is missing or its words do
    not line up one to one with the caption text."""
    words = text.split()
    tw = (tts_text or "").split()
    if tw and len(tw) == len(words):
        w = []
        for t in tw:
            syl = sum(1 for c in t if c in _MARKS) + 0.5 * t.count(_SHADDA)
            w.append(syl + pause if syl else None)
        if all(x is not None for x in w):
            return w, "syllable"
    return [max(1, len(_AR.findall(x))) + 1.0 for x in words], "letter"


def unit_windows(units: list[dict], word_times: list[tuple[float, float]], line_end: float, next_start: float | None, tail: float = TAIL_S) -> list[dict]:
    """One state per (unit, highlighted word). Highlights run word to word without a gap; the last word of a unit holds until the next unit of the
    same line begins; the last unit of the line holds through TAIL_S, but never into the next plate. Times are absolute seconds."""
    states: list[dict] = []
    for u_i, u in enumerate(units):
        for k, wi in enumerate(u["idx"]):
            s0, e0 = word_times[wi]
            last = k == len(u["idx"]) - 1
            if not last:
                end = word_times[u["idx"][k + 1]][0]
            elif u_i + 1 < len(units):
                end = word_times[units[u_i + 1]["idx"][0]][0]
            else:
                end = max(e0, line_end) + tail
                if next_start is not None:
                    end = min(end, next_start - 0.02)
            states.append({"unit": u_i, "word": wi, "k": k, "start": round(s0, 3), "end": round(max(end, s0 + MIN_PLATE_S), 3), "word_start": round(s0, 3), "word_end": round(e0, 3)})
    return states


def borrow_lead(states: list[dict], need_s: dict[int, float], max_lead: float = LEAD_MAX_S, first_max: float | None = None) -> None:
    """States of ONE line in time order, `need_s` {unit: seconds it must stay up}. A unit that is short of its need by less than max_lead starts early (its first plate's `start` moves
    back, `word_start` stays the voice's) and the unit before it ends as much earlier, if that one keeps its own need. Mutates the states."""
    units = sorted({x["unit"] for x in states})
    if units:      # the FIRST unit has no unit before it to pay, but the silence before the line is free: it may start up to max_lead before its first word (E03 I04: 1.59 s up, 1.60 s needed)
        g0 = [x for x in states if x["unit"] == units[0]]
        short_0 = need_s[units[0]] - (g0[-1]["end"] - g0[0]["start"])
        fm = max_lead if first_max is None else first_max      # first_max: the silence the plan itself added before the line (lead_hold) on top of the usual hair
        if 1e-6 < short_0 <= fm + 0.005:
            g0[0]["start"] = round(g0[0]["start"] - min(fm, short_0 + 0.005), 3)
    for a, b in zip(units, units[1:]):
        ga, gb = [x for x in states if x["unit"] == a], [x for x in states if x["unit"] == b]
        short_b = need_s[b] - (gb[-1]["end"] - gb[0]["start"])
        slack_a = (ga[-1]["end"] - ga[0]["start"]) - need_s[a]
        if 1e-6 < short_b:
            d = min(max_lead, short_b + 0.005, slack_a)
            if d > 0.0 and short_b <= max_lead + 0.005:
                gb[0]["start"] = round(gb[0]["start"] - d, 3)
                ga[-1]["end"] = round(ga[-1]["end"] - d, 3)


def carry_glosses(states: list[dict], unit_gloss: dict[int, list[tuple[str, str]]], unit_words: dict[int, int]) -> None:
    """States of ONE line, in time order. A sentence that carries a gloss but is on screen too briefly to read the sentence AND the meaning (the voice
    moves on to the next sentence of the line) hands the meaning to the plates that follow, as «word (meaning)», until its reading budget is met (whole sentences at a time, so the text never jumps).
    Mutates: each state may get `carry` = [{"unit", "word", "meaning"}]. Nothing is spoken for it and no plate is added: the sentence plates stay one at a time."""
    for u, gl in unit_gloss.items():
        grp = [x for x in states if x["unit"] == u]
        if not gl or not grp:
            continue
        need = read_budget_s(unit_words[u] + sum(len(m.split()) for _, m in gl))
        shown = grp[-1]["end"] - grp[0]["start"]
        for v in sorted({x["unit"] for x in states if x["unit"] > u}):       # whole units, so the sentence under it never jumps when the meaning leaves
            if shown >= need:
                break
            nxt = [x for x in states if x["unit"] == v]
            for x in nxt:
                x.setdefault("carry", []).extend({"unit": u, "word": w, "meaning": m} for w, m in gl)
            shown += nxt[-1]["end"] - nxt[0]["start"]


def visible_chars(text: str) -> int:
    """Characters a viewer reads on a plate: the sentence and any bracketed meaning, spaces counted, the brackets themselves not."""
    return len(re.sub(r"[()]", "", text).strip())


def read_speed_need_s(chars: int) -> float:
    """CAP-READING-SPEED: the least a plate may stay up, max(READ_MIN_S, chars / READ_CPS)."""
    return max(READ_MIN_S, chars / READ_CPS)


def read_budget_s(n_words: int) -> float:
    return READ_BASE_S + READ_PER_WORD_S * n_words


def check_plates(plates: list[dict], lines: dict[str, dict], recomputed: dict[str, list[tuple[float, float]]] | None = None) -> list[str]:
    """CAP-FULL-SENTENCE and CAP-READ-TIME over captions.json plates (each plate: line, unit, text, active_index, word_i, n_lines, clause_words, split,
    start, end, word_start).  `recomputed` {line id: [(start, end) per word]} is the independent timing for the sync check."""
    from gloss import strip_gloss
    f: list[str] = []
    by_line: dict[str, list[dict]] = {}
    for p in plates:
        by_line.setdefault(p["line"], []).append(p)
    for lid, ps in by_line.items():
        ln = lines.get(lid)
        if ln is None:
            f.append(f"CAP-FULL-SENTENCE plate line {lid} is not in the script")
            continue
        lw = ln["text"].split()
        units: dict[int, list[dict]] = {}
        for p in ps:
            units.setdefault(p["unit"], []).append(p)
        order = sorted(units)
        cover: list[str] = []
        pos = 0
        for u in order:
            grp = sorted(units[u], key=lambda p: p["start"])
            words = strip_gloss(grp[0]["text"]).split()
            n = len(words)
            if any(strip_gloss(p["text"]).split() != words for p in grp):
                f.append(f"CAP-FULL-SENTENCE {lid} unit {u}: the plates of one sentence show different words")
            if [p["active_index"] for p in grp] != list(range(n)):
                f.append(f"CAP-FULL-SENTENCE {lid} unit {u}: the highlight must visit each of the {n} words once, in order (got {[p['active_index'] for p in grp]})")
            if n > UNIT_WORDS_MAX:
                f.append(f"CAP-FULL-SENTENCE {lid} unit {u}: {n} words (max {UNIT_WORDS_MAX})")
            if grp[0].get("n_lines", 1) > UNIT_LINES_MAX:
                f.append(f"CAP-FULL-SENTENCE {lid} unit {u}: {grp[0]['n_lines']} lines (max {UNIT_LINES_MAX})")
            if words != lw[pos:pos + n]:
                f.append(f"CAP-FULL-SENTENCE {lid} unit {u}: «{' '.join(words)}» is not the next words of the script line")
            first_ok = pos == 0 or ends_clause(lw[pos - 1])
            last_ok = pos + n == len(lw) or ends_clause(lw[pos + n - 1])
            if not (first_ok and last_ok) and not (grp[0].get("split") and grp[0].get("clause_words", 0) > n):
                f.append(f"CAP-FULL-SENTENCE {lid} unit {u}: «{' '.join(words)}» starts or ends in the middle of a sentence or clause")
            shown = grp[-1]["end"] - grp[0]["start"]
            shown += sum(q["end"] - q["start"] for q in ps if any(c.get("unit") == u for c in q.get("carry", [])))      # the meaning handed on to the next plates is still being read
            gloss_words = sum(len(m.split()) for m in re.findall(r"\(([^)]*)\)", grp[0]["text"]))     # a bracketed meaning is read too
            need = read_budget_s(n + gloss_words)
            if shown + 1e-6 < need:
                f.append(f"CAP-READ-TIME {lid} unit {u}: «{' '.join(words)}» is on screen {shown:.2f} s, a reader needs {need:.2f} s" + (f" ({gloss_words} gloss words included)" if gloss_words else ""))
            need_c = read_speed_need_s(visible_chars(grp[0]["text"]))
            if shown + 1e-6 < need_c:
                f.append(f"CAP-READING-SPEED {lid} unit {u}: «{' '.join(words)}» ({visible_chars(grp[0]['text'])} characters) is on screen {shown:.2f} s, the least is max({READ_MIN_S}, chars / {READ_CPS:g} cps) = {need_c:.2f} s")
            cover += words
            pos += n
        if cover != lw:
            f.append(f"CAP-FULL-SENTENCE {lid}: the units show {len(cover)} of the line's {len(lw)} words, or in another order")
        if recomputed and lid in recomputed:
            rt = recomputed[lid]
            for p in ps:
                wi = p.get("word_i")
                if wi is not None and wi < len(rt) and abs(p["word_start"] - rt[wi][0]) > SYNC_TOL_S:
                    f.append(f"CAP-FULL-SENTENCE {lid}: highlight of word {wi} starts {p['word_start']:.2f} s, the voice says {rt[wi][0]:.2f} s (tolerance {SYNC_TOL_S} s)")
                    break
    return f
