"""Shared helpers for tests that read a user's own project files.

A fresh clone has no project data (board/schedule.json, assets/audio/LICENCES.md, bible/series/..., catalogue/...).
- `SCHEDULE`: the user's board/schedule.json when it exists, else the shipped config/schedule.example.json (same shape).
- `needs_project(what, *paths)`: a skipif mark for tests that can only run against a user's own files.
"""
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_own = REPO / "board" / "schedule.json"
SCHEDULE = _own if _own.is_file() else REPO / "config" / "schedule.example.json"

# A small neutral project ("Series A": hero, partner, guide, lead, han, extra) used instead of anyone's real bible/series data.
PROJECT = Path(__file__).resolve().parent / "fixtures" / "project"
SERIES = PROJECT / "bible" / "series" / "series"


def needs_project(what, *paths):
    """skipif mark: skip with an explicit reason when any of the given repo-relative paths is missing."""
    missing = [p for p in paths if not (REPO / p).exists()]
    return pytest.mark.skipif(bool(missing), reason=f"needs your own project data: {what}")
