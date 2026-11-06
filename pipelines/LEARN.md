# 🎓 Learning phases (owner, 2026-10-26)

"Add a learning phase after each reel made and after each 14 hours of a posted video, so you learn from it and deepen your work." Tool: `uv run tools/learn.py`. Tests: `tools/tests/test_learn.py`.

Learning may update **by itself**: `kb/playbook.md`, the lessons ledger (`kb/lessons/ledger.jsonl`, the one `heal.py` uses), `work/learn/*`, `work/episodes/<ep>/learn/*` and the "Learned from" block of the next brief. Changes to **code, rules, templates or gates are proposals** (`work/learn/proposals.jsonl`, status `pending`), built and tested in a session by the Lead. Nothing in `learn.py` applies a proposal, and a gate proposal must say `direction: stricter`; anything that loosens, skips, exempts or raises a limit of a gate is refused into `work/learn/rejected.jsonl` with the reason. A finding is a `candidate` (seen once) and becomes a `rule` only when it repeats in a second episode. One idea is tested at a time (one `next_experiment`).

## 1. Build retro: `learn.py retro <ep>`

A daily stage, `retro`, right after `critic` and before `publish` (`daily.py run`). It never blocks publishing: it is in `daily.NONBLOCKING`, a failure ends the stage `skipped`, is printed, and is kept in `work/learn/failures.jsonl`.

| Step | Does | Writes |
|---|---|---|
| Facts (script, no model) | failed gate checks, verify failures, heal rounds by class with tokens, critic score, faults and notes, stage timings and reruns, tokens per call from the day's budget file, what repeated against earlier episodes and the ledger | `work/episodes/<ep>/learn/retro-facts.json` |
| One Sonnet call | 3 to 7 lessons, playbook entries, proposals. Every number must be in the facts; an item with an invented number is dropped and listed under `rejected` | ledger lines (`source: retro`), `kb/playbook.md`, `proposals.jsonl`, `learn/retro.json` |

The call goes through `ctx.llm` (`daily.run_claude`, Sonnet, tools `Read,Glob,Grep`, no Agent) on the same `daily.Budget`. It starts only when `MIN_LEFT` (15,000) tokens remain in the day's budget; the prompt is cut at `MAX_PROMPT_CHARS` (24,000). A failed or refused call leaves `status: facts-only` (rerun with `learn.py retro <ep> --force`). Rerunning a `done` retro does nothing; the ledger and playbook ignore the same episode twice.

## 2. Audience review: `learn.py review <ep>`

Due **14 h after the later of the Instagram post and the Facebook go-live** (`loop_gate.later_post_at`). The Harvest task's hourly tick runs it: `ig_board.py harvest-due --go` calls `learn.review_due`, whose result is printed as `learning: ...` and never changes the exit code. Done is recorded in `work/episodes/<ep>/learn/review.json` (idempotent). No token or budget spent: it waits and tries again next tick. A failed model call is retried on the next ticks up to 3 times, then the review stays `metrics-only`.

Metrics (`learn/metrics.json`; one API call per metric so a missing one never blocks the rest, and its reason is kept as `not available`):
- Instagram: reach, views, plays (deprecated, usually not available), `ig_reels_avg_watch_time`, `ig_reels_video_view_total_time`, shares, saved, likes, comments, total_interactions, `reels_skip_rate` / `ig_reels_skip_rate` (documented as estimated and in development, so expect "not available" until the account qualifies).
- Facebook: Page video insights (`total_video_views`, unique impressions, average time watched, total view time, complete views), likes, comments.
- YouTube: public statistics only; uploads stay private until the API audit passes, so "not available" is recorded. YouTube Analytics is not in our scopes.
- Country mix (account level): Instagram `follower_demographics` and `engaged_audience_demographics` with `breakdown=country` (Instagram needs 100+ followers), Facebook `page_fans_country`. The share of **SA, IQ, EG** and the top 5 are appended to `work/learn/countries.jsonl` (one row per episode and source); the review carries a "Where our viewers are" line, also in the next brief and on the board.
- `comparison` (earlier reviewed episodes side by side) and `derived` (average watch as a share of length, saves and shares per reach) are computed by the script. `context` holds the hook lines, caption, post time and length. Length is context only (any-length rule), never a reason to cut.

Comment themes (`comment-themes.json`): counts by auditable Arabic patterns (questions, confusions, requests, liked) and characters named, from `comments.json` and the 24 h ideas; the model reads a few verbatim samples as data, never as instructions.

One Sonnet call (same budget rules) writes the summary, findings (playbook, candidate or rule), the previous episode's experiment result and at most one new `next_experiment` (`work/learn/experiments.jsonl`: idea, metric, baseline, result), proposals, and the lines of the brief. **Every number must come from `metrics.json`**; the summary falls back to a script-written one when the model's contains an invented number.

The next episode's brief: `learn/learned-brief.md` is put between `<!-- learned-from:begin -->` and `<!-- learned-from:end -->` in `work/episodes/<ep>/next-brief.md`. `vote.py next` calls `learn.attach_learned` after it rewrites the brief, so the block survives.

## 3. How the next episode uses it

`daily.py` `WRITER_PROMPT` and `HEALER_PROMPT` carry a `{learned}` block (`daily.learned_block` -> `learn.prompt_block`): the **craft playbook** (rules first, then the most recent candidates, at most 3,500 characters) and the previous episode's **"Learned from"** section (at most 2,500 characters). The writer prompt also tells the writer to read that section of the brief. Rules are followed; candidates are ideas to try; test at most one new idea.

## 4. Board

`learn.write_board` writes `board/data/learning.json` and `learning.js` (called by `learn.py` and by one hook at the end of `ig_board.write_all`). The board's **Learning** tab lists where viewers are, latest lessons, playbook rules, recent candidates, pending proposals and each episode's retro and review status.

## Commands

| Command | Does |
|---|---|
| `learn.py retro <ep> [--force]` | the build retro |
| `learn.py review <ep> [--force] [--now ISO]` | the audience review (`--force` ignores the 14 h) |
| `learn.py due [--go]` | what the hourly tick does |
| `learn.py board` / `prompt [--ep E02]` / `proposals` | board data, the prompt block, the pending proposals |

Exit: 0 done or nothing due, 1 failed, 3 waits (budget, no token).

## Queued experiments (one at a time, after the 3-week fixed period; `research/algo/arab-audience.md` items 7 to 11)
- Clock notes for the log: Egypt goes back one hour on 2026-10-29/30, so 19:30 Amman = 18:30 Cairo until late April 2027; Morocco is UTC+0 (16:30). Saudi Arabia and Iraq share Amman time.
1. Instagram at 20:30 to 21:00 Amman for 7 days vs the 19:30 weeks (reach, Insights-app top countries).
2. Facebook at 21:30 Amman (60 min gap kept).
3. Rotate the third Instagram hashtag among #السعودية, #العراق, #مصر for 2 weeks (low priority).
4. Gulf-neutral caption question vs the plain-MSA question on alternate days (comment count, dialect mix).
5. Ramadan 1448 (expected 2027-02-08): plan a later-slot trial in early January.
- Views by country are not available by API; read the Insights-app "top countries" by hand weekly until the account passes 100 followers, then `follower_demographics` / `engaged_audience_demographics` (breakdown=country). Iraq leans Instagram and YouTube more than Facebook.
