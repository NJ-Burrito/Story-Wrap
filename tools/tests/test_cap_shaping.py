# -*- coding: utf-8 -*-
"""CAP-ARABIC-SHAPING (the owner 2026-10-25, C1): Arabic caption words keep their joining and the outline never cuts into a letter.
Text and pixel checks are pure; one test drives the real Chromium plate renderer when playwright and the Thmanyah fonts exist."""
import sys
from pathlib import Path

import numpy as np
import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import cap_shaping as cs  # noqa: E402

CLEAN = [["الريح", "تفتح"], ["النافذة"], ["وحقيبة", "تسقط"], ["العالية."], ["اسمي", "أنا."], ["كل", "شيء", "هنا"]]


@pytest.mark.parametrize("words", CLEAN)
def test_clean_arabic_words_pass(words):
    assert cs.text_problems(words, words[0]) == []


@pytest.mark.parametrize("bad,why", [
    (["ال\u200cريح"], "joiner"),            # ZWNJ inside a word breaks the join
    (["ال\u200dريح"], "joiner"),
    (["\u202bالريح\u202c"], "bidi"),
    (["الـريح"], "tatweel"),
    (["\ufe8d\ufee4\ufee0"], "pre-shaped"),   # isolated/presentation forms bypass the font's joining
    (["\ufedf\ufe8e"], "pre-shaped"),
    (["الriح"], "Latin"),
    (["الريح "], "space"),
])
def test_word_with_join_breaker_fails(bad, why):
    probs = cs.text_problems(bad)
    assert probs and why.lower() in probs[0].lower()


def test_highlight_must_be_a_whole_word_of_the_plate():
    assert cs.text_problems(["وحقيبة", "تسقط"], "وحقي")           # a cut inside a word
    assert cs.text_problems(["وحقيبة", "تسقط"], "تسقط") == []


def _blob(h=60, w=120, val=255):
    a = np.zeros((h, w, 4), np.uint8)
    a[10:50, 10:110] = (val, val, val, 255)
    return a


def test_seam_ratio_zero_for_a_plate_equal_to_its_fill_reference():
    ref = _blob()
    assert cs.seam_ratio(ref.copy(), ref) == 0.0


def test_dark_seam_across_a_join_is_caught():
    ref = _blob()
    plate = ref.copy()
    plate[10:50, 58:62] = (10, 8, 6, 255)          # a stroke of the next glyph painted over the previous glyph's fill
    r = cs.seam_ratio(plate, ref)
    assert r > cs.SEAM_MAX
    chunks = [{"words": ["العالية."], "active": "العالية."}]
    assert any("outline cuts" in f for f in cs.shaping_problems(chunks, [(plate, ref)]))
    assert cs.shaping_problems(chunks, [(ref.copy(), ref)]) == []


def test_layout_mismatch_is_an_error_not_a_pass():
    with pytest.raises(ValueError):
        cs.seam_ratio(_blob(60), _blob(61))


def test_plate_html_keeps_whole_words_and_paints_the_outline_underneath():
    import calm_compose as cc
    states = [{"words": ["وحقيبة", "تسقط"], "active": 1}, {"words": ["العالية."], "active": 0}]
    html = cc.plate_html(states, [], with_ref=True)
    assert html.count('data-t="وحقيبة"') == 2                                      # the plate and its ref twin
    assert '<span data-t="تسقط" class="on">تسقط</span>' in html
    assert 'id="r0"' in html and 'id="r1"' in html
    css = html.split("<style>")[1].split("</style>")[0]
    cap_rule = css.split(".cap{")[1].split("}")[0]
    assert "text-stroke" not in cap_rule and "letter-spacing:0" in cap_rule     # no stroke on the fill glyphs, no tracking
    assert "span::before{content:attr(data-t)" in css and "z-index:-1" in css and "-webkit-text-stroke" in css
    assert css.count("-webkit-text-stroke") == 1                                 # only the under-layer carries the stroke
    assert not cs._JOIN_BREAKERS.search(html.split("</style>")[1])               # no ZWNJ/ZWJ/bidi control sneaks into the markup


def _chrome_ok():
    try:
        import playwright.sync_api as p
        import compose as C
        with p.sync_playwright() as pw:
            pw.chromium.launch().close()
        return all((C.FONTS / f).is_file() for f in ("thmanyahsans-Black.woff2", "thmanyahsans-Bold.woff2", "thmanyahsans-Medium.woff2", "thmanyahserifdisplay-Black.woff2"))
    except Exception:
        return False


@pytest.mark.skipif(not _chrome_ok(), reason="playwright Chromium or Thmanyah fonts not available")
def test_real_chromium_plates_have_no_seams_and_the_old_stroke_method_does(tmp_path):
    import io

    import calm_compose as cc
    import compose as C
    from PIL import Image
    states = [{"words": ["اسمي", "أنا."], "active": 0}, {"words": ["العالية."], "active": 0}, {"words": ["وحقيبة", "تسقط"], "active": 1}]
    good = cc.plate_html(states, [], with_ref=True)
    # the pre-fix css: the outline stroked on the fill glyphs themselves
    legacy = good.replace(".cap span::before{", ".cap span::before{display:none;").replace(
        "font-kerning:normal;", "font-kerning:normal;-webkit-text-stroke:9px rgb(10,8,6);paint-order:stroke fill;")

    def ratios(html):
        out = []

        def go(pg):
            for k in range(len(states)):
                pl = np.array(Image.open(io.BytesIO(pg.locator(f"#c{k}").screenshot(omit_background=True))).convert("RGBA"))
                rf = np.array(Image.open(io.BytesIO(pg.locator(f"#r{k}").screenshot(omit_background=True))).convert("RGBA"))
                out.append(cs.seam_ratio(pl, rf))
        C.chrome_page(html, tmp_path, 1080, 1920, go)
        return out
    assert max(ratios(good)) <= cs.SEAM_MAX
    assert max(ratios(legacy)) > cs.SEAM_MAX      # the check would have failed the plates the owner rejected


def test_calm_compose_declares_scipy_for_the_shaping_check():
    """`uv run tools/calm_compose.py captions` died with No module named 'scipy' on E01C (2026-10-25): cap_shaping imports it, the script header must list it."""
    from pathlib import Path
    head = (Path(__file__).resolve().parents[1] / "calm_compose.py").read_text(encoding="utf-8").splitlines()[:5]
    assert any("dependencies" in l and "scipy" in l for l in head)
