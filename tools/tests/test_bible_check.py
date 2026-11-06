"""bible_check: a passing fixture series (built by filling the real template) and one mutation per check id."""
import re
import subprocess
import sys

import pytest

import bible_check as bc
from conftest import REPO, TOOLS

SHOWS = "eyes: wide; face: still; body: stiff; voice: flat; action: freezes"
OVERRIDES = {
    "arc_type": "positive",
    "world": "harbour",
    "origin": "Omani coast, Muscat family",
    "accent_source": "Muscat coast, Oman",
    "accent_features": "dropped final vowels; Omani word for tea; fast clipped rhythm",
    "handedness": "right",
    "culture_brief": "../../culture/{id}.md",
    "culture_status": "pending",
}
MATRIX_HEAD = ("| Character | 1 Lie | 2 Want | 3 Ghost type | 4 Coping | 5 Arc | 6 Auth | 7 Speech | 8 Base | 9 Move "
               "| 10 Extreme | Tell |\n|---|---|---|---|---|---|---|---|---|---|---|---|\n")


def filled_bible(cid: str) -> str:
    text = bc.strip_comments(bc.TEMPLATE.read_text(encoding="utf-8"))
    out = []
    for ln in text.splitlines():
        m = bc.FIELD_RE.match(ln)
        if m and m.group(2).strip().startswith("<"):
            key = m.group(1)
            val = OVERRIDES.get(key, f"sample {key} for {cid}").replace("{id}", cid)
            if key == "id":
                val = cid
            if key == "shows":
                val = SHOWS
            ln = f"- {key}: {val}"
        elif m is None and "<" in ln and ln.strip().startswith(("|", "- <")):
            ln = re.sub(r"<[^>]*>", "x", ln)
        out.append(ln)
    return "\n".join(out) + "\n"


def matrix(n: int, shared: int = 0) -> str:
    rows = []
    for i in range(n):
        cells = [f"c{i}"] + [f"v{i}-{a}" for a in range(1, 12)]
        for a in range(1, shared + 1):  # make axes 1..shared identical across all characters
            cells[a] = f"same{a}"
        rows.append("| " + " | ".join(cells) + " |")
    return MATRIX_HEAD + "\n".join(rows) + "\n"


@pytest.fixture
def series(tmp_path):
    s = tmp_path / "bible" / "series" / "demo"
    (s / "worlds").mkdir(parents=True)
    (s / "culture").mkdir()
    (s / "series.md").write_text("# demo\n", encoding="utf-8")
    (s / "worlds" / "harbour.md").write_text("# harbour\n", encoding="utf-8")
    for cid in ("aa", "bb"):
        d = s / "characters" / cid
        d.mkdir(parents=True)
        (d / "bible.md").write_text(filled_bible(cid), encoding="utf-8")
        (s / "culture" / f"{cid}.md").write_text(
            "# brief\n\n## Decisions for the owner\n\n- Covers hair: open\n", encoding="utf-8")
    (s / "ensemble-matrix.md").write_text(matrix(2), encoding="utf-8")
    return s


def ids(findings):
    return {f.check for f in findings}


def edit(series, cid, fn):
    p = series / "characters" / cid / "bible.md"
    p.write_text(fn(p.read_text(encoding="utf-8")), encoding="utf-8")


def test_pass(series):
    assert bc.run(series) == []


def test_template_is_the_requirement_list():
    keys = bc.required_keys()
    for k in ("ghost", "lie", "want", "need", "handedness", "accent_features", "garment_construction",
              "physics_hints", "catalogue_poses", "catalogue_hands", "arc_by_episode", "relationships",
              "extreme_human", "culture_brief", "height_head_units"):
        assert k in keys
    assert "shows" not in keys  # emotion block keys are not character fields


def test_fields_fail(series):
    edit(series, "aa", lambda t: re.sub(r"^- ghost: .*$", "- ghost: <empty>", t, flags=re.M))
    f = bc.run(series)
    assert ids(f) == {"BIBLE-FIELDS"} and "ghost" in f[0].msg


def test_fields_nested_value_counts(series):
    edit(series, "aa", lambda t: re.sub(r"^- arc_by_episode: .*$", "- arc_by_episode:\n  - ep 1: lie holds", t, flags=re.M))
    assert bc.run(series) == []


def test_fields_missing_file(series):
    (series / "characters" / "bb" / "bible.md").unlink()
    assert "BIBLE-FIELDS" in ids(bc.run(series))


def test_culture_fail_missing_brief(series):
    (series / "culture" / "aa.md").unlink()
    assert ids(bc.run(series)) == {"BIBLE-CULTURE"}


def test_culture_fail_no_decisions(series):
    (series / "culture" / "aa.md").write_text("# brief\n\nNothing decided.\n", encoding="utf-8")
    assert ids(bc.run(series)) == {"BIBLE-CULTURE"}


def test_culture_fail_bad_status(series):
    edit(series, "aa", lambda t: t.replace("culture_status: pending", "culture_status: maybe"))
    assert ids(bc.run(series)) == {"BIBLE-CULTURE"}


def test_accent_fail_one_feature(series):
    edit(series, "aa", lambda t: re.sub(r"^- accent_features: .*$", "- accent_features: soft", t, flags=re.M))
    assert ids(bc.run(series)) == {"BIBLE-ACCENT"}


def test_accent_fail_not_from_origin(series):
    edit(series, "aa", lambda t: re.sub(r"^- accent_source: .*$", "- accent_source: Seoul Korea", t, flags=re.M))
    assert ids(bc.run(series)) == {"BIBLE-ACCENT"}


def test_emotion_fail_missing_block(series):
    edit(series, "aa", lambda t: t.replace("### emotion: shame", "### emotion: pride"))
    f = bc.run(series)
    assert ids(f) == {"BIBLE-EMOTION"} and "shame" in f[0].msg


def test_emotion_fail_few_channels(series):
    edit(series, "aa", lambda t: t.replace(SHOWS, "eyes: wide; face: still", 1))
    assert ids(bc.run(series)) == {"BIBLE-EMOTION"}


def test_emotion_fail_no_leak(series):
    edit(series, "aa", lambda t: re.sub(r"^- leak: .*$", "- leak: <x>", t, count=1, flags=re.M))
    assert ids(bc.run(series)) == {"BIBLE-EMOTION"}


@pytest.mark.parametrize("val", ["", "<left | right>", "both", "ambi"])
def test_hand_fail(series, val):
    edit(series, "aa", lambda t: re.sub(r"^- handedness: .*$", f"- handedness: {val}", t, flags=re.M))
    assert "BIBLE-HAND" in ids(bc.run(series))


def test_hand_pass_left(series):
    edit(series, "aa", lambda t: re.sub(r"^- handedness: .*$", "- handedness: left, writes with right", t, flags=re.M))
    assert bc.run(series) == []


def test_world_link_fail(series):
    edit(series, "bb", lambda t: t.replace("world: harbour", "world: harbour, moon"))
    f = bc.run(series)
    assert ids(f) == {"WORLD-LINK"} and "moon" in f[0].msg


def test_ensemble_pass_boundary(series):
    (series / "ensemble-matrix.md").write_text(matrix(3, shared=2), encoding="utf-8")
    (series / "characters" / "cc").mkdir()
    (series / "characters" / "cc" / "bible.md").write_text(filled_bible("cc"), encoding="utf-8")
    (series / "culture" / "cc.md").write_text("# b\n\n## Decisions\n\n- open\n", encoding="utf-8")
    assert bc.run(series) == []  # differ on exactly 8 of 10


def test_ensemble_fail_three_shared(series):
    (series / "ensemble-matrix.md").write_text(matrix(2, shared=3), encoding="utf-8")
    f = bc.run(series)
    assert ids(f) == {"ENSEMBLE-CONTRAST"} and "7 of 10" in f[0].msg


def test_ensemble_tag_decides(series):
    m = matrix(2)
    m = m.replace("v0-3", "family loss [legacy]").replace("v1-3", "other words [legacy]")
    m = m.replace("v0-4", "x [control]").replace("v1-4", "y [control]")
    (series / "ensemble-matrix.md").write_text(m, encoding="utf-8")
    assert bc.run(series) == []  # axes 3 and 4 same by tag, 8 differ -> pass
    (series / "ensemble-matrix.md").write_text(m.replace("v0-6", "v1-6"),
                                               encoding="utf-8")
    assert ids(bc.run(series)) == {"ENSEMBLE-CONTRAST"}


def test_ensemble_fail_same_tell(series):
    (series / "ensemble-matrix.md").write_text(matrix(2).replace("v1-11", "v0-11"), encoding="utf-8")
    f = bc.run(series)
    assert ids(f) == {"ENSEMBLE-CONTRAST"} and "tell" in f[0].msg


def test_ensemble_fail_missing(series):
    (series / "ensemble-matrix.md").unlink()
    assert ids(bc.run(series)) == {"ENSEMBLE-CONTRAST"}


def test_layout_fail(tmp_path):
    s = tmp_path / "empty"
    s.mkdir()
    assert "BIBLE-LAYOUT" in ids(bc.run(s))


def test_cli_exit_codes(series, tmp_path):
    ok = subprocess.run([sys.executable, str(TOOLS / "bible_check.py"), str(series)], capture_output=True, text=True)
    assert ok.returncode == 0 and "OK" in ok.stdout
    (series / "worlds" / "harbour.md").unlink()
    bad = subprocess.run([sys.executable, str(TOOLS / "bible_check.py"), str(series)], capture_output=True, text=True)
    assert bad.returncode == 1 and "FAIL [WORLD-LINK]" in bad.stdout
