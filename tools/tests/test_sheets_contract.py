"""Character and world module contract (tools/render/*/README.md): static checks on the module sources."""
import re
import subprocess
import sys

import pytest

from conftest import REPO, TOOLS

CHAR_KEYS = ["id", "hu_m", "proportions_hu", "palette", "handedness", "sides", "physics_profile", "data", "solve", "drawBody", "drawArms", "massProxy", "sheet", "sheet_version"]
WORLD_KEYS = ["id", "bible_world", "rule", "locations", "materials", "sheet", "sheet_version"]


def keys_in_register(src, fn):
    body = src[src.index(fn + "({"):]
    return set(re.findall(r"(?:^\s{2}|[{,]\s*)([A-Za-z_]+)\s*[:,(]", body, re.M))


@pytest.mark.parametrize("mod", sorted((REPO / "tools/render/characters").glob("*.js")))
def test_character_module_exports_contract(mod):
    src = mod.read_text(encoding="utf-8")
    assert "registerCharacter({" in src, "module must call registerCharacter"
    have = keys_in_register(src, "registerCharacter")
    assert not [k for k in CHAR_KEYS if k not in have], [k for k in CHAR_KEYS if k not in have]


@pytest.mark.parametrize("mod", sorted((REPO / "tools/render/worlds").glob("*.js")))
def test_world_module_exports_contract(mod):
    src = mod.read_text(encoding="utf-8")
    assert "registerWorld({" in src
    have = keys_in_register(src, "registerWorld")
    assert not [k for k in WORLD_KEYS if k not in have], [k for k in WORLD_KEYS if k not in have]


def test_module_missing_required_key_fails_fixture():
    bad = 'registerCharacter({\n  id: "x",\n  hu_m: 1,\n});'
    assert [k for k in CHAR_KEYS if k not in keys_in_register(bad, "registerCharacter")]


@pytest.mark.parametrize("name", ["core.js", "face.js", "hands.js", "trace.js", "insert.js", "bootstrap.js", "write.js", "sheets.js"])
def test_generic_renderer_files_do_not_name_the_character(name):
    src = (REPO / "tools/render" / name).read_text(encoding="utf-8")
    assert not re.search(r"solveHero|drawHero|\bHero\b", src), f"{name} names Hero: move it behind CHAR"


def test_generic_file_naming_the_character_is_detected():
    assert re.search(r"solveHero|drawHero|\bHero\b", "const R = solveHero(s);")


def test_sheets_tool_refuses_unknown_module():
    r = subprocess.run([sys.executable, str(TOOLS / "sheets.py"), "character", "nobody"], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 1 and "SHEETS-MODULE" in r.stdout
