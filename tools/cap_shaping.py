# -*- coding: utf-8 -*-
"""CAP-ARABIC-SHAPING: the word-by-word Arabic caption plates keep every word's joining, and the outline never cuts into a letter.

Root cause it guards (E01 calm, the owner 2026-10-25, C1 "the letters break where words meet"): the plates drew the dark outline with
`-webkit-text-stroke` on the same glyphs as the fill. Arabic letters are joined, so every glyph overlaps its neighbour; a centred 9 px
stroke of the NEXT glyph was painted over the fill of the PREVIOUS one, leaving a dark seam at each join and at the word ends.
The fix paints the outline as a separate under-layer (one `::before` per word, drawn below every fill), so no stroke can touch a fill.

Two layers of checks, both deterministic, no model:
  1. text_problems(): every word is a whole, plain Arabic word: no ZWNJ/ZWJ/bidi controls/tatweel/pre-shaped presentation forms
     (U+FB50-FDFF, U+FE70-FEFF: they bypass the font's joining), no Latin letters mixed into a word, the highlighted word is one of the chunk's words.
  2. seam_ratio(): pixel check on the finished plate against a fill-only reference render of the same chunk at the same layout:
     inside the reference fill (eroded 2 px) no pixel of the plate may be the outline colour. Ratio must stay under SEAM_MAX.
"""
from __future__ import annotations

import re

SEAM_MAX = 0.002            # share of interior fill pixels allowed to be outline-dark (a clean render measures 0.0)
ERODE_PX = 2
OUTLINE_LUMA_MAX = 70       # outline colour is rgb(10,8,6); fills are white or the accent (luma > 150)
_JOIN_BREAKERS = re.compile("[\u200c\u200d\u200e\u200f\u202a-\u202e\u2066-\u2069\u061c\u0640]")
_PRESHAPED = re.compile("[\ufb50-\ufdff\ufe70-\ufeff]")
_AR = re.compile("[\u0621-\u064a\u0671-\u06d3]")
_LATIN = re.compile("[A-Za-z]")


def text_problems(words: list[str], active: str | None = None) -> list[str]:
    """Problems with the words of one plate, as short strings; [] when every word can join as the font intends."""
    out = []
    for w in words:
        if not w or w != w.strip() or re.search(r"\s", w):
            out.append(f"word {w!r} is empty or holds a space")
            continue
        if _JOIN_BREAKERS.search(w):
            out.append(f"word {w!r} holds a joiner, bidi control or tatweel")
        if _PRESHAPED.search(w):
            out.append(f"word {w!r} holds pre-shaped presentation forms (they bypass contextual joining)")
        if _AR.search(w) and _LATIN.search(w):
            out.append(f"word {w!r} mixes Latin and Arabic letters")
    if active is not None and active not in words:
        out.append(f"highlighted {active!r} is not a whole word of the plate {words!r}")
    return out


def seam_ratio(plate_rgba, ref_rgba) -> float:
    """plate_rgba: the finished plate (outline + fill). ref_rgba: the same chunk, fill only, same size. Both numpy HxWx4 uint8.
    Returns the share of the reference's interior fill pixels that the plate shows as outline-dark (a seam)."""
    import numpy as np
    from scipy.ndimage import binary_erosion
    if plate_rgba.shape != ref_rgba.shape:
        raise ValueError(f"plate {plate_rgba.shape} and reference {ref_rgba.shape} differ in size: the layout is not the same")
    inside = binary_erosion(ref_rgba[..., 3] > 250, iterations=ERODE_PX)
    n = int(inside.sum())
    if n == 0:
        return 1.0
    rgb = plate_rgba[..., :3].astype(float)
    luma = rgb @ np.array([0.2126, 0.7152, 0.0722])
    dark = inside & ((luma < OUTLINE_LUMA_MAX) | (plate_rgba[..., 3] < 250))
    return float(dark.sum()) / n


def shaping_problems(chunks: list[dict], pairs: list[tuple]) -> list[str]:
    """chunks: [{'words': [...], 'active': str}]; pairs: [(plate_rgba, ref_rgba)] in the same order (may be empty for a text-only pass)."""
    f = []
    for i, c in enumerate(chunks):
        f += [f"plate {i}: {p}" for p in text_problems(c["words"], c.get("active"))]
    for i, (pl, rf) in enumerate(pairs):
        r = seam_ratio(pl, rf)
        if r > SEAM_MAX:
            f.append(f"plate {i} ('{' '.join(chunks[i]['words'])}'): outline cuts into the letters, {r:.4f} of the fill is outline-dark (max {SEAM_MAX})")
    return f
