"""artbook: one passing fixture (a tiny series with sheets, built into a previews page) and one mutation per check id."""
import hashlib
import json
import re

import pytest
from PIL import Image

import artbook as ab

BIBLE = """# Test
- id: tess
- name: تيس بنت ريح / Tess bint Reeh. Second sentence.
- age: 19. Born in the harbour.
- origin: Born in a trading port, in the age of sail.
- extreme_trait: Labels everything.
- silhouette_note: A small upright figure in a coat too big for her.
- height_head_units: 7.5
- build: Slight, narrow shoulders (1.86 head units wide). Profile `tess-v1`.
- props_carried: Each with the hand that holds it.
  - **Dip pen with a brass cap** (left hand).
### emotion: calm
- leak: The little finger taps once after each tag.
### emotion: shame
- leak: She folds the spoiled tag into a tiny square.
### emotion: surprise
- leak: The pen cap pops off and rolls.
"""
PROP = {"height": 7.5, "shoulder_w": 1.86}


def sha(b):
    return "sha256:" + hashlib.sha256(b).hexdigest()[:16]


def make_root(tmp, svg_fill="#fff", png_rgb=(255, 255, 255), measures=None):
    root = tmp
    (root / "bible/series/s/characters/tess").mkdir(parents=True)
    (root / "bible/series/s/characters/tess/bible.md").write_text(BIBLE, encoding="utf-8")
    (root / "bible/series/s/worlds").mkdir(parents=True)
    d = root / "catalogue/characters/tess"
    (d / "v1/sheets").mkdir(parents=True)
    (d / "character.json").write_text(json.dumps({"proportions_hu": PROP}), encoding="utf-8")
    (d / "physics.json").write_text(json.dumps({"id": "tess-v1"}), encoding="utf-8")
    (root / "tools/render/characters").mkdir(parents=True)
    (root / "tools/render/characters/tess.js").write_text('sheet_version: "v1"', encoding="utf-8")
    sheets = []
    for sid in ab.CHAR_SHEETS:
        svg = f'<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10" fill="{svg_fill}" stroke="#000"/></svg>'
        (d / "v1/sheets" / f"{sid}.svg").write_text(svg, encoding="utf-8")
        Image.new("RGB", (40, 30), png_rgb).save(d / "v1/sheets" / f"{sid}.png")
        reg = {}
        if sid == "04-turnaround":
            reg = {"front": [0, 0, 20, 30]}
        if sid == "01-shapes":
            reg = {"figure": [0, 0, 20, 30]}
        if sid == "05-expressions":
            reg = {e: [0, 0, 20, 15] for e in ("calm", "shame", "surprise")}
        sheets.append({"id": sid, "title": sid, "svg": sid + ".svg", "png": sid + ".png", "svg_sha": sha(svg.encode()), "regions": reg})
    meta = {"kind": "character", "id": "tess", "version": "v1", "page": {"w": 40, "h": 30}, "sheets": sheets,
            "measures": measures or {"height": 7.5, "shoulder_w": 1.86},
            "module_summary": {"id": "tess", "proportions_hu": PROP, "physics_profile": "tess-v1", "head_study": ["calm", "shame", "surprise"]}}
    (d / "v1/sheets/sheets.json").write_text(json.dumps(meta), encoding="utf-8")
    (root / "previews").mkdir()
    html = root / "previews/index.html"
    html.write_text('<style>\n</style><script>\nconst TABS = [\n  {id: "hero", emoji: "x", label: "S"},\n];\n</script><section class="panel" id="panel-cast" data-tab="cast"></section>', encoding="utf-8")
    return root, root / "bible/series/s", html


@pytest.fixture
def fx(tmp_path):
    root, series, html = make_root(tmp_path)
    assert ab.build(root, series, html, log=lambda *_: None) == 0
    return root, series, html


def ids(fails):
    return {re.search(r"\[([A-Z-]+)\]", f).group(1) for f in fails}


def test_pass(fx):
    root, series, html = fx
    assert ab.check_sheets(root, series)[0] == []
    assert ab.check_ink(root, series) == []
    assert ab.check_match(root, series) == []
    assert ab.check_text(root, html) == []
    assert ab.run_checks(root, series, html, False, log=lambda *_: None) == 0
    page = html.read_text(encoding="utf-8")
    assert 'data-tab="artbook"' in page and 'id: "artbook"' in page


def test_build_is_idempotent(fx):
    root, series, html = fx
    a = html.read_text(encoding="utf-8")
    ab.build(root, series, html, log=lambda *_: None)
    assert html.read_text(encoding="utf-8") == a


def test_sheets_fail_missing_sheet(fx):
    root, series, html = fx
    (root / "catalogue/characters/tess/v1/sheets/07-face.png").unlink()
    assert "ARTBOOK-SHEETS" in ids(ab.check_sheets(root, series)[0])


def test_sheets_fail_no_module_character(fx):
    root, series, html = fx
    (series / "characters/zed").mkdir()
    (series / "characters/zed/bible.md").write_text("- id: zed\n", encoding="utf-8")
    f, pending = ab.check_sheets(root, series)
    assert "ARTBOOK-SHEETS" in ids(f)
    f2, pending2 = ab.check_sheets(root, series, built_only=True)
    assert f2 == [] and any("zed" in p for p in pending2)


def test_sheets_fail_world_without_sheets(fx):
    root, series, html = fx
    (series / "worlds/harbour.md").write_text("# Harbour\n", encoding="utf-8")
    assert any("harbour" in f for f in ab.check_sheets(root, series)[0])


def test_ink_fail_coloured_png(tmp_path):
    root, series, html = make_root(tmp_path, png_rgb=(255, 0, 0))
    assert "ARTBOOK-INK" in ids(ab.check_ink(root, series))


def test_ink_fail_coloured_svg(tmp_path):
    root, series, html = make_root(tmp_path, svg_fill="#c03030")
    assert "ARTBOOK-INK" in ids(ab.check_ink(root, series))


def test_ink_accepts_greys():
    assert ab.colour_is_grey("#cfcfcf") and ab.colour_is_grey("rgb(120,120,120)") and not ab.colour_is_grey("teal")


def test_match_fail_drawn_height(tmp_path):
    root, series, html = make_root(tmp_path, measures={"height": 8.2, "shoulder_w": 1.86})
    assert "ARTBOOK-MATCH" in ids(ab.check_match(root, series))


def test_match_fail_bible_height(fx):
    root, series, html = fx
    b = series / "characters/tess/bible.md"
    b.write_text(b.read_text(encoding="utf-8").replace("height_head_units: 7.5", "height_head_units: 6"), encoding="utf-8")
    assert "ARTBOOK-MATCH" in ids(ab.check_match(root, series))


def test_match_fail_stale_svg(fx):
    root, series, html = fx
    (root / "catalogue/characters/tess/v1/sheets/02-mannequin.svg").write_text("<svg/>", encoding="utf-8")
    assert any("changed since" in f for f in ab.check_match(root, series))


def test_match_fail_profile_not_in_bible(fx):
    root, series, html = fx
    b = series / "characters/tess/bible.md"
    b.write_text(b.read_text(encoding="utf-8").replace("tess-v1", "other"), encoding="utf-8")
    assert "ARTBOOK-MATCH" in ids(ab.check_match(root, series))


def test_text_fail_caption_not_in_bible(fx):
    root, series, html = fx
    b = series / "characters/tess/bible.md"
    b.write_text(b.read_text(encoding="utf-8").replace("Labels everything.", "Labels nothing."), encoding="utf-8")
    assert "ARTBOOK-TEXT" in ids(ab.check_text(root, html))


def test_text_fail_caption_without_source(fx):
    root, series, html = fx
    page = html.read_text(encoding="utf-8")
    page = page.replace("</main>", '<p class="ab-cap">made up line</p></main>', 1)
    html.write_text(page, encoding="utf-8")
    assert "ARTBOOK-TEXT" in ids(ab.check_text(root, html))


def test_text_fail_shown_text_differs(fx):
    root, series, html = fx
    page = html.read_text(encoding="utf-8")
    page = re.sub(r'(data-cap="c002">)[^<]*', r"\1edited by hand", page, count=1)
    html.write_text(page, encoding="utf-8")
    assert "ARTBOOK-TEXT" in ids(ab.check_text(root, html))
