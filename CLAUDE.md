# Story-Wrap tool: rules for agents working in this repository

- This repository is the tool only: scripts, skills, pipelines, docs. Never commit episodes, series, renders, audience data, fonts, voices, reference media, account names, ids, tokens or personal paths.
- Every account id, handle, channel id, path and schedule comes from env or a git-ignored local file (`config/*.example.*` lists the keys). Never hard-code one.
- Credentials only in `~/.config/story-wrap/`; no tool prints, logs or writes them.
- Use `uv` for Python packages, never pip. Set `PYTHONUTF8=1` on Windows.
- Use only official platform APIs with the user's own apps. Nothing disguises automation as a human.
- Read `pipelines/RUNBOOK.md` first, then the stage doc you need. The rulebook is `kb/rulebook.md`.
- Gates (`tools/quality_gate.py`, `tools/loop_gate.py`, `tools/secret_gate.py`) are never skipped or loosened to get a run through.
- Tests: `uv run -q --no-project --with pytest --with numpy --with scipy --with pillow --with requests --with jsonschema python -m pytest tools/tests -q -p no:cacheprovider` (they use fakes and the neutral fixtures in `tools/tests/fixtures/`; no network, no real credentials, no project data needed). A test that can only run against your own series, kits, casting or catalogue skips with the reason `needs your own project data: ...`.
