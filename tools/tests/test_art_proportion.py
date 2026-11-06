"""ART-PROPORTION (owner, 2026-10-25: the art book is the reference, every time): the film's drawn hand, head and face sizes per head height stay within 8 % of the approved
art-book model. The fixture holds one real trace record per character (render/hands.js artMeasure, taken from the fixed close profiles); the `as it was` cases multiply it by the
numbers the old profiles used (hero close-v3: hand 1.34x, fingers 1.18x, face 1.22x; guide close-v2: hand 1.3x, head 1.14x, nose 1.25x, lips 1.3x; lead v2: hand 1.16x, fingers 1.1x more, face 1.15x)."""
import copy, json
import pytest
import qg_checks as qc
from conftest import REPO, TOOLS
import sw_fixtures

PROJECT = sw_fixtures.PROJECT      # the neutral fixture project holds the reference files (catalogue/characters/<id>/artbook-proportions.json)

ART = json.loads((TOOLS / "tests" / "fixtures" / "art_records.json").read_text(encoding="utf-8"))
FACE = ("nose_w_hu", "nose_len_hu", "lips_w_hu", "lips_t_hu", "eye_w_hu", "eye_h_hu")


def trace(cid, art, n=3):
    return {"characters": {cid: {"frames": [{"f": i, "t": i / 24, "art": copy.deepcopy(art)} for i in range(n)]}}}


def old(cid):
    a = copy.deepcopy(ART[cid])
    def grow(key, k):
        if isinstance(a[key], dict):
            a[key] = {s: v * k for s, v in a[key].items()}
        else:
            a[key] *= k
    if cid == "hero":
        grow("hand_len_hu", 1.34); grow("hand_w_hu", 1.34); grow("finger_r_hu", 1.18)
        for k in FACE: grow(k, 1.22)
    elif cid == "guide":
        grow("hand_len_hu", 1.3); grow("hand_w_hu", 1.3); grow("finger_r_hu", 1.3); a["head_h_hu"] *= 1.14
        grow("nose_w_hu", 1.25); grow("nose_len_hu", 1.25); grow("lips_w_hu", 1.3); grow("lips_t_hu", 1.3)
    else:
        grow("hand_len_hu", 1.16); grow("hand_w_hu", 1.16); grow("finger_r_hu", 1.16 * 1.1)
        for k in FACE: grow(k, 1.15)
    return a


@pytest.mark.parametrize("cid", ["hero", "guide", "lead"])
def test_the_fixed_close_profiles_pass(cid):
    assert qc.rig_art_proportion(trace(cid, ART[cid]), PROJECT) == []


@pytest.mark.parametrize("cid", ["hero", "guide", "lead"])
def test_the_old_enlarged_profiles_fail(cid):
    got = qc.rig_art_proportion(trace(cid, old(cid)), PROJECT)
    assert qc.ids_of(got) == {"ART-PROPORTION"}
    assert any("hand_len" in m for m in got) and any("hand_w" in m for m in got) and any("finger_r" in m for m in got)
    assert any("nose_w" in m or "lips_w" in m or "eye_w" in m for m in got)


def test_hero_hands_at_134_percent_are_reported_in_numbers():
    got = qc.rig_art_proportion(trace("hero", old("hero")), PROJECT)
    assert any("hero hand_len_L is +34%" in m for m in got)


def test_the_tolerance_is_eight_percent():
    a = copy.deepcopy(ART["hero"]); a["hand_len_hu"] = {s: v * 1.07 for s, v in a["hand_len_hu"].items()}
    assert qc.rig_art_proportion(trace("hero", a), PROJECT) == []
    a["hand_len_hu"] = {s: v * 1.09 / 1.07 for s, v in a["hand_len_hu"].items()}
    assert qc.rig_art_proportion(trace("hero", a), PROJECT) != []


def test_a_bigger_head_shrinks_every_ratio():
    a = copy.deepcopy(ART["guide"]); a["head_h_hu"] *= 1.14
    assert any("hand_len" in m for m in qc.rig_art_proportion(trace("guide", a), PROJECT))


def test_legacy_traces_and_characters_without_a_reference_are_not_judged():
    assert qc.rig_art_proportion({"characters": {"hero": {"frames": [{"f": 0, "t": 0}]}}}, PROJECT) == []
    assert qc.rig_art_proportion(trace("extra", old("hero")), PROJECT) == []
    assert qc.rig_art_proportion(trace("hero", old("hero")), None) == []


def test_check_rig_runs_it():
    assert "ART-PROPORTION" in qc.ids_of(qc.check_rig(trace("hero", old("hero")), None, PROJECT))


@sw_fixtures.needs_project("catalogue/characters/<id>/artbook-proportions.json derived from your approved art-book sheets", "catalogue/characters/hero/artbook-proportions.json")
@pytest.mark.parametrize("cid", ["hero", "guide", "lead"])
def test_reference_files_are_derived_from_the_approved_sheets(cid):
    import artbook_proportions as ap
    on_disk = json.loads((REPO / "catalogue" / "characters" / cid / "artbook-proportions.json").read_text(encoding="utf-8"))
    assert on_disk == json.loads(json.dumps(ap.measure(cid), ensure_ascii=False)), "re-run tools/artbook_proportions.py"
    assert on_disk["approved_sheet_version"] == ap.APPROVED[cid] and on_disk["tolerance_pct"] == 8.0
    assert on_disk["sheets_module_sha"].startswith("sha256:")


@sw_fixtures.needs_project("tools/render/characters/<id>.js (your characters' rig profiles)", "tools/render/characters/hero.js")
def test_close_profiles_keep_art_book_scale():
    import re
    for cid, names in (("hero", ("close-v2", "close-v3")), ("guide", ("close-v2",)), ("lead", ("v2",))):
        src = (REPO / "tools" / "render" / "characters" / f"{cid}.js").read_text(encoding="utf-8")
        for n in names:
            line = next(l for l in src.splitlines() if re.search(r'"?%s"?: \{name: "%s"' % (n, n), l))
            assert re.search(r"hs: 1[,.]", line) and "hs: 1." not in line.replace("hs: 1,", ""), (cid, n, line)
