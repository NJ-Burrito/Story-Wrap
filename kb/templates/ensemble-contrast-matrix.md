# Ensemble contrast matrix

Copy to `bible/series/<series>/ensemble-matrix.md`. Run before any drawing (R-032). One row per character. Checked by `uv run tools/bible_check.py <series-dir>` (check `ENSEMBLE-CONTRAST`).

## 1. Values per character

The check reads the first table whose header starts with `Character`: columns 1 to 10 are the axes, then `Tell`. Write short values (a phrase), not labels like "brave". Two cells are the same when their text is the same after lowercasing and trimming; if a cell ends in a `[tag]` (as ghost type and coping habit do), the tag decides. The script cannot see two lies that mean the same in different words: the Sonnet seat reads axes 1 and 2 by meaning.

| Character | 1 Lie | 2 Want | 3 Ghost type | 4 Coping habit | 5 Arc type | 6 Authority/group attitude | 7 Speech register + silence | 8 Cultural/linguistic base | 9 Movement signature | 10 Extreme trait | Tell |
|---|---|---|---|---|---|---|---|---|---|---|---|

## 2. Pair table

Optional write-up of flagged pairs. The script prints the count for every pair.

| Pair | Same on axes | Differs on (count) | Same on axes 1 to 4 (count) | Result |
|---|---|---|---|---|

## 3. Pass conditions

- Machine (`ENSEMBLE-CONTRAST`): every pair differs on at least 8 of the 10 axes (`--min-diff`, default 8); all Extreme traits differ; all Tells differ. This implies the R-032 floor (3 of 10, no pair equal on 2 or more of axes 1 to 4).
- Human (Sonnet seat): no two lies or wants say the same thing in other words; no two characters share a primary silhouette family; the cast contains positive, flat and negative arcs (R-034); culture is not the only axis on which a pair differs.

## 4. Result
- Flagged pairs:
- Rewrites made (character, axis, old, new):
- Pass/fail and date:
