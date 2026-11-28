# Contributing to Story-Wrap

Thanks for helping. Small pull requests with one topic each are easiest to review.

## Start here

- New? Look for issues labelled [good first issue](https://github.com/NJ-Burrito/Story-Wrap/labels/good%20first%20issue).
- Bug or idea: open an issue from the templates first, so we agree on the change before you write it.

## Run the checks

```bash
PYTHONUTF8=1 uv run -q --no-project --with pytest --with numpy --with scipy --with pillow --with requests --with jsonschema python -m pytest tools/tests -q -p no:cacheprovider
```

Tests use fakes and the neutral fixtures in `tools/tests/fixtures/`. A test that needs your own series data skips and says so.

## Rules

- No episodes, fonts, voice clips, characters or account tokens in a commit. The repo holds the toolkit only.
- Python runs with `uv`, never pip. On Windows set `PYTHONUTF8=1`.
- One topic per branch, pull request into `main`.
- Deletions go to the recycle bin, never `rm -rf`.

## Commit messages

Imperative and scoped, for example `site: fix the Arabic footer link`.
