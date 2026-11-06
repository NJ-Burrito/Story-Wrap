# Story-Wrap Board

A monitor for the StoryPage Instagram account (`story_account`). It shows what the daily pipeline did, how the posts and the vote are doing, which replies wait for the owner, when things run next, and whether anything is broken. Nothing here posts an episode or loosens a gate.

## Open it

| How | Command | Notes |
|---|---|---|
| From disk | open `board/index.html` | read only (the buttons need the server); data comes from `data/board.js` |
| Served | `python board/serve.py` then http://127.0.0.1:8771/ | buttons work; binds to 127.0.0.1; every POST needs the per-start token in the page |
| At logon | `tools/register-tasks.ps1 -WithServer` | task `StoryWrap-BoardServer` |

Fonts are Thmanyah from `assets/fonts/` (git-ignored). Comment text is escaped before it reaches the page.

## Tabs

| Tab | Shows | Fed by |
|---|---|---|
| Today | the active episode: stage table with seconds, gate verdict, critic score, render time against the 4 h cap, the loop gate for the next episode | `work/daily/<ep>/STATE.json`, `deadline.json`, `STOPPED.md`, `work/episodes/<ep>/gate/report.json`, `heal/critic.json` |
| Build panel (top of every tab; full on Today) | the current episode's stages (ok / running / failed / waiting), heals applied, machine time and tokens against their caps, the last autopilot line, the next tick, and a RED banner for any stop, backed-off episode, FIX-REQUEST.md, PUBLISH-FAILED, failed harvest or an autopilot that stopped ticking | `board/data/build.json` / `build.js`, written by `tools/build_status.py` at every autopilot tick and every stage boundary |
| Schedule | next production run, next post slot, next harvest, the five tasks with rules | `board/schedule.json`, `tools/loop_gate.py` |
| Health | token present or missing and days left (never the value), render cap, agent tokens today, each task's last word, Task Scheduler results, recent stops, alerts | `~/.config/story-wrap/instagram.env` (presence only), `work/daily/tasks/*.json`, `schtasks` |
| 📊 All platforms | all platforms added up (views, likes, comments, shares, saves, follows) with delta and sparkline, a card per platform, general notes for Claude, the Engage caps and windows | `tools/monitor_board.py` |
| 📸 Instagram, 📘 Facebook, ▶️ YouTube | one tab per platform (colour per platform, sticky strip): account link and totals, the nine metrics for the platform, then every post newest first: cover (platform thumbnail if a writer kept one, else a frame of `episode.mp4` in `board/data/thumbs/`), title and caption, posted HH:MM:SS Amman, length, live link, 72 h window and time left, the nine metrics (big number, delta since the last reading, sparkline, or "not available yet: reason"), stories, what the bot said and drafts waiting, comment threads, a note box. Then that platform's DMs and a general note box. Instagram also holds the old Posts vote bars and the old Comments content (tally, ideas, Approve/Reject drafts). | post/facebook/youtube.json, metrics*.json, `learn/metrics.json`, `work/perf/youtube`, `work/inbox`, `work/engage`, `board/data/monitor.*` (git-ignored: DM text is private) |

## Notes for Claude

Every post card, every platform tab and the All tab has a note box (needs `python board/serve.py`; the page opened from disk shows it disabled). A note is saved by `POST /api/note` (localhost, per-start token) to `work/board/notes.jsonl` as `{id, ts, platform, post, text, picked_up}`; secrets, empty or over-long notes are refused. Claude reads them with `uv run tools/monitor_board.py notes --pending` and marks one done with `uv run tools/monitor_board.py pick <id>`; the page then shows it as picked up.

## Data

`uv run tools/ig_board.py refresh` rewrites `board/data/`: `today.json`, `posts.json`, `comments.json`, `schedule.json`, `health.json`, `replies.json`, `board.json` (everything) and `board.js` (the same as `window.__BOARD__`, so the page works from disk). The folder is generated; the Board task refreshes it every 15 minutes: `ig_board.py refresh --metrics` first runs `tools/live_numbers.py` (YouTube statistics, Instagram media insights, Facebook video insights), then rebuilds the Monitor feed. Every number card shows "as of HH:MM:SS" and a stale badge after 30 minutes.

## Reply drafts

Deterministic Arabic templates in the page's voice (warm, short, no tashkeel, one question to keep people talking): a counted vote gets a thank-you naming the choice, an idea gets "saved for the writer", anything else gets a thank-you and an invitation. Drafts never send by themselves unless `board/config.json` says so:

```json
{ "auto_reply": false, "auto_kinds": ["vote"], "max_replies_per_day": 10, "max_replies_per_run": 3 }
```

Approved replies (and, with `auto_reply: true`, drafts of the listed kinds) are sent by the Harvest task through `ig.py reply`: official API only, own account, at most `max_replies_per_run` per hourly run and `max_replies_per_day` per day. Nothing is sent without a token.

## The five tasks (times: `board/schedule.json`, local time)

| Task | When | Does | No token |
|---|---|---|---|
| StoryWrap-Autopilot | 14:00, then every 30 min to 18:30, limit 5 h (replaces StoryWrap-Daily, 2026-10-27) | `daily.py autopilot`: harvest, then the next episode (or finish a built one); never posts | not needed |
| StoryWrap-Post | every 5 min from 19:00 to 20:25 (retries only) | `daily.py post --latest --due --go`: every platform at the fixed 19:00 slot, 20 h after the last post, only if the episode was ready by 19:00, when the gates passed and the critic is 9 or more | `NO-TOKEN`, exit 0 |
| StoryWrap-Harvest | hourly at :35 | `ig_board.py harvest-due --go` (safety net for the autopilot's 14:00 harvest): due 14:00 the day after a post, comments, tally, ideas, next brief, metrics, then approved replies | `NO-TOKEN`, exit 0 |
| StoryWrap-Board | every 15 min | `ig_board.py refresh --metrics` | files only |
| StoryWrap-Health | every 3 h | `ig_board.py health` | reports "token missing" |

**Loop gate** (`tools/loop_gate.py`): episode N+1 is not produced until N was posted and harvested. A wait is a clean exit (the board says WAIT and why). Without a token nothing can be posted, so production stops after one finished episode.

Register: `powershell -ExecutionPolicy Bypass -File tools\register-tasks.ps1 -DryRun` (look), the same without `-DryRun` (do it), `-Remove` (undo). See `pipelines/AUDIENCE.md`.

## How Health decides (alerts, stale data, times)

- Health never reads its own previous status (that nested every old alert into the next one). It writes `OK` with "N alert(s)" or "all clear"; the alerts live on the board.
- Token budget: today's file only, and "today" resets at midnight Amman time.
- The 4 h render cap guards **building**: no alert for an episode that is posted, finished (gate PASS, critic 9+, `episode.mp4`) or adopted (`tools/adopt.py` valid). An adopted episode shows "adopted by <name> <date>" on its stage table and "the build cap does not apply to posting"; its old stop is hidden.
- Recent stops: only episodes still being built, only stops from the last 48 h. A later clean `daily.py run` renames `STOPPED.md` to `STOPPED.resolved.md`.
- A task status older than its interval (a repeating task: `every_min`; daily and windowed tasks: 24 h) is **stale**: dimmed on the Health tab, never red, never an alert. A Board or Harvest status older than 3 of its intervals is an alert ("the board data is older than N min").
- The Task Scheduler column is reused from the last `ig_board.py health` run; it shows when it was asked. Result 267011 is shown as "not run yet".
- Every posted/story/harvest time is shown in Amman time (stored values are UTC). Dry ticks (`daily.py post --due` without `--go`) write no task status.

