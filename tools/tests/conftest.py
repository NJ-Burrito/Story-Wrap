import copy, json, os, sys
from pathlib import Path
import pytest

TOOLS = Path(__file__).resolve().parents[1]
REPO = TOOLS.parent
sys.path.insert(0, str(TOOLS))

# The suite runs the same on a fresh clone and on a machine that holds a user's own project: the neutral fixtures win over personal settings.
os.environ["SW_SERIES_NAME"] = "the series"
os.environ["SW_YT_PLAYLIST_TITLE"] = "the series"
import seo  # noqa: E402  (tools/seo.py reads its keyword file at import time of ig.py / yt.py, so point it first)
seo.DATA = Path(__file__).resolve().parent / "fixtures" / "seo-keywords.json"


@pytest.fixture
def example():
    return json.loads((REPO / "kb/quality/shot-spec.example.json").read_text(encoding="utf-8"))


@pytest.fixture
def mix_v2():
    return json.loads((REPO / "kb/quality/fixtures/mix-v2.shot-spec.json").read_text(encoding="utf-8"))


@pytest.fixture
def clone():
    return copy.deepcopy


@pytest.fixture
def neutral_project(monkeypatch):
    """Plan checks read the series glossary and cast names under calm_compose.ROOT: point it at the neutral fixture project (never a user's own series)."""
    import calm_compose
    import sw_fixtures
    monkeypatch.setattr(calm_compose, "ROOT", sw_fixtures.PROJECT)
