# Audience loop: post at 19:00, harvest at 14:00 the next day, count the votes, write the next episode

the owner, 2026-10-24: every episode ends with TWO story choices; the audience decides what happens next. Rules: `CLAUDE.md` ("Episodes after E01", "Audience loop"). API facts and the owner's one-time setup: `research/instagram-api.md`. Tools: `tools/ig.py`, `tools/fb.py`, `tools/vote.py`. Two platforms (owner, 2026-10-25): every episode posts to Instagram AND to the Facebook Page StoryPage as a Reel, through the official Graph API, and the VOTE IS READ FROM INSTAGRAM ONLY (owner, 2026-10-25): other platforms are upload only, their comments may feed the idea pool but never the decision.

## One-time setup (the owner does it himself)

Page name **StoryPage** (brand: `assets/brand/README.md`, picture `assets/brand/mark-source.png`). the owner creates every account himself; Claude never logs in or signs up and never handles his password.
1. Instagram account StoryPage, switched to a Creator or Business (professional) account.
2. Facebook Page StoryPage (page id `<your page id>`), linked to it. Facebook posting is on: a Page token that does not expire, scopes `pages_manage_posts`, `pages_read_engagement`, `pages_read_user_content`, `pages_manage_engagement`, `pages_show_list`.
3. developers.facebook.com: app "StoryPage" (Business, use case Other) > Instagram > API setup with Instagram business login; add the account as Instagram Tester and accept the invite.
4. Generate the token; save `IG_USER_ID`, `IG_ACCESS_TOKEN`, `IG_USERNAME` in `~/.config/story-wrap/instagram.env`.
4b. Save `FB_PAGE_ID` and `FB_PAGE_TOKEN` in the same file. Host `graph.facebook.com`, same API version as Instagram (`IG_API_VERSION`).
5. Verify: `uv run tools/ig.py status` and `uv run tools/fb.py status --live` (reads the Page name; neither prints a token). Click-by-click: `research/instagram-api.md` section 7.

## Timeline

```
episode composed + gate PASS + critic >= 9
   |  ig.py publish E02 + fb.py publish E02   (dry run first; --go posts; `daily.py post` runs both)
   v
POST  -> work/episodes/E02/post.json (Instagram: post id, link, time; a `facebook` key mirrors Facebook's)
      -> work/episodes/E02/facebook.json (Facebook: video id, link, time, state)
   |  14:00 the next day, Amman (loop_gate.harvest_due_at; ig.py / fb.py comments still refuse earlier than 12 h)
   v
HARVEST -> fb.py harvest E02 -> comments.json (Instagram AND Facebook comments and replies, each row has `platform`)
   v
TALLY   -> vote.py tally E02    -> decision.json (counts, winner, margin, samples)
   v
BRIEF   -> vote.py next E02     -> next-brief.md (+ losing branch parked in bible/ideas/)
   v
sw-showrunner-writer writes E03 from the winner, then the normal stages
```

## Who does what

| Step | Who | Output |
|---|---|---|
| Post | the Lead runs `daily.py post --go` (or `ig.py publish` and `fb.py publish`, each `--go`; never a worker) | `post.json`, `facebook.json` |
| Harvest, tally, brief | Task Scheduler (below) or the Lead | `comments.json`, `decision.json`, `next-brief.md` |
| Tie or near-empty vote | sw-showrunner-writer picks the stronger story and writes one Arabic sentence for the next caption | `showrunner_pick` in `decision.json` |
| Recap card (E02 on) | the plan's `recap` takes the winning choice word; E01 has none | `calm-plan.json` |
| Next episode | sw-showrunner-writer, then the usual crew | `episodes/E03/...` |
| Tool faults | sw-pipeline-engineer | `tools/ig.py`, `tools/fb.py`, `tools/vote.py` |

## Rules in plain words

- **Posting gate:** `ig.py publish` refuses unless `gate/report.json` says PASS and complete, `heal/critic.json` scores 9 or more, and `episode.mp4` exists. It refuses a second post of the same episode unless `--force`.
- **Facebook is the same gate, same caption, its own record.** `fb.py publish` runs the same `publish_gates`, posts the Page Reel (`POST /{page-id}/video_reels`: `upload_phase=start`, binary upload to the returned `upload_url` with the `Authorization: OAuth` header and `offset`/`file_size`, then `upload_phase=finish` with `video_state=PUBLISHED` and the caption as `description`), polls the video status until it is `ready`, and records `facebook.json` at once after `finish` so a slow poll can never cause a second post. It refuses a second post of the same episode unless `--force`.
- **One platform failing never blocks or undoes the other.** `daily.py post` tries Instagram, then Facebook, each on its own; a platform already on record is skipped on a rerun; the stage reports `PUBLISH-PARTIAL` naming the one that failed. The scheduled Post task retries a missing Facebook half for an Instagram post at most 36 h old (older episodes are never back-filled).
- **Votes from Instagram only (owner, 2026-10-25).** `fb.py harvest` (the daily `votes` stage and the Harvest task) reads Instagram first and requires it: if Instagram is not posted or cannot be read, nothing is finalised. Facebook comments are read after it for the idea pool only, written into `comments.json` with `platform: facebook` (deduped by platform plus comment id), never counted in `decision.json`. The Page's own comments are flagged `own`. A Facebook failure (token, network, FB-TOO-EARLY) is returned under `errors`, marks the harvest `partial` (`fb.py harvest` exits 3, the Harvest task says PARTIAL) and never blocks or changes the Instagram decision. 24 h after the later post a late pass (`fb.py late <ep>`, run by the Harvest task) files new comments from both platforms in `late-ideas.json` as ideas only. Replies still go out through `ig.py reply` only. Facebook likes and comment counts: `fb.py metrics <ep>` -> `metrics-facebook.json`.
- **Dry run by default:** without `--go` it prints the caption and touches nothing (no credentials, no network).
- **Captions (DESIGN 4 and 5.2, the owner approved 2026-10-25), one per platform.** Instagram: `caption.txt` (the writer's text) or the template: first line series + number + hook, three emoji-led lines, ONE open question that names the two options as story facts, then a request for the reason («قولوا لنا لماذا ...»), the closing statement «الحلقة القادمة تتبع ما تكتبونه.» and 3 Arabic hashtags. Facebook: `caption-facebook.txt` and `title-facebook.txt` win, otherwise the Instagram text is rewritten (`ig.facebook_parts`): `title` = «the series | الحلقة N», the first line is the hook only, the closing line gains «الحلقة N من ...», 2 hashtags; the Reel is posted with `is_ai_generated=true`. **Never** a digit to type, "comment 1 or 2", «اكتبوا اختياركم», «علقوا», «صوتوا», «اختاروا», «شاركوا», «اذكروا», «اضغطوا», «تابعوا لتعرفوا»: `ig.caption_problems` refuses a caption that has one (IG-CAPTION-BAIT / FB-CAPTION-BAIT) or too many hashtags. Last vote's result line opens the next template caption.
- **Credentials:** only in `~/.config/story-wrap/instagram.env`. No tool prints, logs or writes them (tests check every output file).
- **Counting (by wording):** every comment and reply that names exactly one choice is one vote. A choice is recognised from the card's short phrase, its listed `variants` (other ways to say it) and its distinctive words (diacritics, letter variants and small spelling slips ignored, `FUZZY_RATIO` 0.84); a bare `1`/`2`, `١`/`٢`, Persian digits or keycap emoji from an older habit still counts. `decision.json` records how each vote was recognised (`via`). A comment naming both or neither counts for nobody. Our own account is excluded.
  Free answers with reasons (DESIGN 5.4): the part before a reason marker («لأن», «حتى», «عشان», «علشان») decides the vote and the reason is kept as an idea only; a choice word within two words after «لا ما لن ليس بدون» is flipped to the other side and counted weak (both sides negated is listed under `ambiguous`); strong votes (the card phrase or a listed variant) decide first, weak votes (distinctive word, bare digit, flip) only when strong votes tie or number fewer than `MIN_VOTES`; one account counts once (its latest counted comment). `decision.json` records `strong`, `weak`, `basis`, `ambiguous`, `duplicates_collapsed` and `seen_ids`.
- **Ideas:** a comment that says more than the choice (at least `IDEA_MIN_WORDS` 3 words of its own) is also kept as an idea (`decision.json` `ideas`, at most 40) and printed in `next-brief.md` under "Ideas from the audience" for the writer.
- **Tie, or fewer than 5 counted votes** (`MIN_VOTES` in `vote.py`): `decision.json` says `SHOWRUNNER_TIE` or `SHOWRUNNER_LOW_VOTES`. The brief starts with "DECISION NEEDED FIRST". The showrunner-writer adds `showrunner_pick` `{"id","reason_ar"}` to `decision.json`, reruns `vote.py next`, and the reason goes into the next caption.
- **Reuse first:** every brief lists the catalogue, character and world modules, approved references and built shots. New work only for what the story truly needs.
- **Parked, never deleted:** the losing branch is written to `bible/ideas/parked-<ep>-choice-<n>.md`.

## Commands

| Command | Does |
|---|---|
| `uv run tools/ig.py status [--live]` | token days left, per-episode state, blockers |
| `uv run tools/ig.py publish E02 [--go]` | dry run, then post |
| `uv run tools/ig.py comments E02 [--force]` | harvest (not before 12 h unless `--force`; the scheduled harvest is 14:00 the next day) |
| `uv run tools/fb.py status [--live]` | Facebook token state, per-episode state; `--live` reads the Page name |
| `uv run tools/fb.py publish E02 [--go]` | dry run, then post the Page Reel |
| `uv run tools/fb.py harvest E02 [--force]` | Instagram + Facebook comments -> one `comments.json` (`fb.py comments` = Facebook only) |
| `uv run tools/fb.py metrics E02` | Facebook likes and comment count -> `metrics-facebook.json` |
| `uv run tools/yt.py status [--live]` | YouTube token state; `--live` reads the channel |
| `uv run tools/yt.py publish E02 [--go]` | dry run, then the resumable upload (after Instagram) |
| `uv run tools/yt.py playlist E02 [--go]` / `comments E02` | add to the playlist / read comments as ideas |
| `uv run tools/stories.py announce E02 [--go]` / `vote E02 [--go]` / `vote-due [--go]` | Instagram and Facebook Page stories |
| `uv run tools/adopt.py adopt E01C --approved-by the owner --reason "..."` / `status` / `revoke` | let an approved, gated episode post without a rebuild |
| `uv run tools/yt.py prune [--go]` / `forget [--go] [--records]` | YouTube data retention / delete all stored YouTube data |
| `uv run tools/post_extra.py tick` | what the Post task runs: the Reels, then YouTube and the stories |
| `uv run tools/vote.py tally E02` | count, write `decision.json` |
| `uv run tools/vote.py next E02` | write `next-brief.md`, park the losing branch |
| `uv run tools/ig.py refresh` | refresh the 60-day token (every 30 days) |
| `uv run tools/ig.py plan E02` | print the Task Scheduler command for the harvest (14:00 the next day) |
| `uv run tools/ig.py metrics E02` | likes and comment count -> `metrics.json` (the board) |
| `uv run tools/ig.py reply <comment_id> "<text>" [--go]` | one reply (dry run without --go; the board calls it within its limits) |
| `uv run tools/ig_board.py refresh` | rebuild `board/data/` |


## YouTube and stories (owner, 2026-10-25; tools/yt.py, tools/stories.py, tools/post_extra.py)

**YouTube (upload only; the vote stays on Instagram).** `yt.py publish <ep> [--go]` uploads the episode through the official Data API v3 (`videos.insert`, resumable, chunked) with the token in `~/.config/story-wrap/youtube-token.json` (refreshed and saved back when needed; never printed, logged or written to a record: `yt.redact`). Same gates as the Reels (`ig.publish_gates`), and never before Instagram: no `post.json`, no upload. `youtube.json` is written as `uploading` BEFORE the first byte, so a crash or a lost answer can never lead to a second upload (YouTube treats a deleted and re-posted Short as a spam risk); any retry needs `--force`, after the owner has looked at Studio.
- Title: «the series | الحلقة N | {hook}» (at most 100 characters). Description: the Instagram text with the series moved to the title, the same open question, the closing line gaining «الحلقة N من the series.», and three hashtags (`#المكتب #قصص_متحركة #Shorts`; `#حكايات` instead of `#Shorts` when the video is over 3 minutes). `caption-youtube.txt` / `title-youtube.txt` in the episode folder win. The bait-wording check (`ig.caption_problems`) and the tashkeel check run first.
- Fields: `categoryId` 1 (Film and Animation), `defaultLanguage` and `defaultAudioLanguage` `ar`, `selfDeclaredMadeForKids` false (so comments stay open), `containsSyntheticMedia` true (`status.containsSyntheticMedia`, a boolean in the videos resource), `privacyStatus` public. YouTube keeps every upload of an unaudited API project private; the real value is read back with `videos.list` and recorded (`privacy_actual`, `locked_private`), and the board and Health say so.
- Playlist «the series»: created once (an existing one with that title is reused), its id stored in `work/state/youtube.json`, each uploaded video added with `playlistItems.insert`. These two calls need the `https://www.googleapis.com/auth/youtube` scope (OFFICIAL, the playlists.insert and playlistItems.insert reference pages); the token today holds `youtube.upload` + `youtube.readonly`, so the playlist step is recorded as `playlist_error` and never fails the upload. the owner authorises the broader scope once to switch it on; `yt.py playlist <ep> --go` retries.
- Comments: `yt.py comments <ep>` reads `commentThreads.list` into `comments.json` as `platform: youtube` rows (our own are flagged `own`). `vote.py` counts only Instagram rows, so they are ideas for the writer, never votes. The Harvest task reads them before the tally (and again at 24 h); a failed read is reported as `youtube` under `errors` (PARTIAL) and never changes a decision.
- `yt.py status [--live]`: token state (scopes, expiry, missing playlist scope), the playlist id, per-episode state; `--live` asks `channels.list(mine)` and checks it is channel YOUR_CHANNEL_ID.

- **Privacy until the audit (documented rule).** `yt.py` requests `privacyStatus: private` until the flag file `work/state/yt_audit_passed` exists (the Lead or the owner creates it after Google's audit approval email; nothing else does), then `public`. YouTube would lock an unaudited project's upload to private anyway; asking for private means nothing is half-published. `youtube.json` is created with `O_EXCL` right after the is_posted check, so two overlapping runs cannot both upload. The playlist step is recorded (`playlist_state: adding`) before the insert call; a crash leaves it, and nothing adds the video again until `yt.py playlist <ep> --go --force`. A video that is private because we asked for it is information on the board, not an alert; `locked_private` (we asked public, YouTube kept it private) is also information.
- **Retention (the public privacy page).** YouTube comments are deleted or refreshed within 30 days, and stored YouTube data within 7 days of a deletion request. Every YouTube comment row carries `fetched_at` (set by each `yt.py comments` read, which replaces the whole YouTube set). The Harvest task runs `yt.prune_comments` on every run: YouTube rows older than 30 days are deleted from every `comments.json`, and their copies from `decision.json` `ideas`, `late-ideas.json` and the lines of `next-brief.md` that contain their text. Instagram and Facebook rows are never touched. `yt.py prune [--go]` does the same by hand. `yt.py forget [--go]` deletes ALL stored YouTube comment data and idea copies at once (a deletion request; dry run without `--go`); `--records` also deletes the upload records and the playlist state (the episode could then be uploaded again: only on purpose). The OAuth token is ours, not user data: revoke it in the Google account. Ideas the writer already copied into `bible/ideas/` or a script are the writer's own text and are not tracked here.

**Stories (Instagram and the Facebook Page; image or video only, no stickers, polls or links; highlights have no API and are never touched by a job).** `stories.py` renders every story as a short vertical VIDEO (1080x1920, H.264 by NVENC, AAC, 3 to 60 s) so the resumable upload path needs no public URL.
- Instagram: `POST /{ig-user}/media` with `media_type=STORIES` and `upload_type=resumable`, binary to `rupload.facebook.com/ig-api-upload/...`, poll `status_code`, `POST /{ig-user}/media_publish`. Facebook Page: `POST /{page}/video_stories` `upload_phase=start`, binary to the returned `upload_url`, `upload_phase=finish` with `is_ai_generated=true`.
- `announce <ep>`: after the platform's Reel is live (Instagram: `post.json`; Facebook: `facebook.json` whose go-live time has passed, so the Facebook story follows the Facebook Reel's go-live, 19:00 like Instagram) ONE story per platform: «الحلقة N الآن على الصفحة» over `work/episodes/<ep>/cover.png` (6 s, silent) or, when there is no cover, over the first 25 s of the episode with its sound.
- `vote <ep>` / `vote-due`: the next morning (the Harvest task, after the decision is written and within 30 h of it) ONE story per platform with the result card: «نتيجة الحلقة N», the winning choice as its short phrase, and the count (or the writer's reason after a tie). No bait wording (`ig.caption_problems`), no hashtag.
- Records: `work/episodes/<ep>/stories.json`, one entry per kind and platform. A `publishing` entry is written before the call that makes the story public; any entry (pending, failed or published) blocks a repeat without `--force`. A failure before that point leaves no entry, so the next Post tick retries it. One platform failing never blocks the other. Tokens are redacted from every message and record.
- **Claims and the 3 hour rule.** Before anything is rendered or sent, each story takes a claim: a lock file `work/episodes/<ep>/story/claim-<kind>-<platform>.lock` created with `O_EXCL` and a `claiming` entry in `stories.json`. Of two overlapping runs only one gets it; the other reports `already`. A failure that happened before the story could be public (a failed render, a refused upload) gives the claim back; a crash leaves it, and the retry needs `--force`. An announce story is skipped when the Reel went live more than 3 hours ago (a story saying «الآن» a day late is wrong); the Post tick writes `PARTIAL` on the board when an extras step failed and left no record behind.
- The StoryWrap-Post task now runs `post_extra.py tick`: `daily.py post --latest --due --go` first (its exit code is the task's), then YouTube and the stories for every episode posted in the last 36 h. `daily.py` carries one extra post stage `yt_stories` with the same logic.

**Posting an approved episode without rebuilding it (`tools/adopt.py`, E01C).** `daily.py post` refuses an episode whose run stages are not fresh and verified (UPSTREAM-NOT-VERIFIED), and that must stay so. An episode that the owner approved and the gate passed by hand (E01C: calm v5 plus the NJ mark, gate 29/29) is posted by recording an adoption first:
`uv run tools/adopt.py adopt E01C --approved-by the owner --reason "approved reference, calm v5 with the NJ mark, gate 29/29"`.
It refuses unless the gate report is PASS, complete, with no failing check; the critic scored 9 or more; `episode.mp4` exists and the gate report is newer than it; the episode is not posted; and the approver and a reason (10 characters or more) are named. It writes `work/episodes/<ep>/adopted.json` (approver, reason, time, SHA-256 of the gate report and of `episode.mp4`) and one line to `work/daily/adoptions.jsonl`. `daily.run_list` then skips ONLY the run-stage check for the post stages, and only while `adopt.valid` re-reads both files and finds the same hashes and all the posting gates still green: a new render, a marked version or a re-gate voids the adoption and it must be done again against the new PASS. Every post stage and every gate still runs. `adopt.py status <ep>` says whether it holds, `adopt.py revoke <ep>` removes it. The scheduled `post --latest --due` then posts the episode normally at its slot.

## The board and the schedule (owner, 2026-10-25: a monitor like the LinkedIn one, and posting without launching anything)

`board/index.html` (Today, Posts, Comments, Schedule, Health; `board/README.md`) is fed by `tools/ig_board.py` from the files `ig.py`, `vote.py` and `daily.py` already write. Five Windows tasks run the loop; their times live in `board/schedule.json`, and `tools/register-tasks.ps1` reads that same file.

| Task | Time | Command | Gate |
|---|---|---|---|
| StoryWrap-Autopilot | 14:00, then every 30 min to 18:30 (replaces StoryWrap-Daily, the owner 2026-10-27) | `uv run tools/daily.py autopilot` via `tools/autopilot.ps1` | LOOP GATE, 4 h cap, free only, token budget 1 200 000, lock, never posts |
| StoryWrap-Post | every 5 min, 19:00 to 20:25 (retries only) | `uv run tools/post_extra.py tick` (= `daily.py post --latest --due --go`, then YouTube and the stories) | gates PASS, critic 9 or more, a token, fixed slot 19:00 on every platform (Instagram, then the Facebook Reel at once, then YouTube), ready by the slot, 20 h gap |
| StoryWrap-Harvest | hourly at :35 (safety net) | `uv run tools/ig_board.py harvest-due --go` | due 14:00 the day after the post, token |
| StoryWrap-Board | every 15 min | `uv run tools/ig_board.py refresh --metrics` | none (files) |
| StoryWrap-Health | every 3 h | `uv run tools/ig_board.py health` | none |

**LOOP GATE** (`tools/loop_gate.py`): episode N+1 is produced only after N was posted (`post.json`) and harvested (`decision.json`). The day closes the loop (owner, 2026-10-27): post 19:00 on every platform, harvest 14:00 the next day (`harvest_due_at`: the day after the later post at 14:00), and the autopilot's first run at 14:00 harvests and builds N+1 at once, so N+1 is ready for its own 19:00 slot (a test keeps these times in step). A wait exits 0, writes the task status as `WAIT`, and the board says why. `daily.py run` resumes an episode it started and never posted instead of starting a new one.

**Post time (owner, 2026-10-27, replaces DESIGN 6.2's 19:30 / 20:30 and the varied minute of the LinkedIn rule):** 19:00 Amman every day on every platform: Instagram first, the Facebook Reel at once after it (`FB_AFTER_IG_MIN = 0`, so no schedule ahead), then YouTube and the stories, all in the same Post run. Never within 20 h of the last post (`loop_gate.post_slot`, `fb_slot`, `post_due`). The Post task ticks every 5 minutes from 19:00 to 20:25 only to retry a failed attempt; after 20:30 the day's slot is missed (`WAIT-LATE`). An episode whose gate report, critic verdict or video is newer than the 19:00 slot is `WAIT-NOTREADY`: it posts at the next 19:00, never off-slot. **Facebook never goes live before Instagram:** `fb.py publish` refuses (`FB-WAIT-INSTAGRAM`) while `post.json` is missing, and the daily stage does not attempt it after an Instagram failure. The Instagram `post.json` is written (with `media_id`) right after `media_publish`, before the permalink is read, so a failed read can never lead to a second post; `ig.py metrics` fills the link in later. The Facebook `finish` parameters `title`, `description`, `video_state`, `scheduled_publish_time` and `is_ai_generated` are the ones Meta documents for the Reels publishing API (checked 2026-10-25). **Each platform is its own attempt:** Instagram live and Facebook failed is `PARTIAL` (the schedule stage still runs, the Post task says PARTIAL not FAIL, the next run retries Facebook only); Facebook live and Instagram failed is a failure with a board row and a Health alert, and the loop keeps waiting for Instagram (the vote source). A Facebook record written before the `finish` call (`state: finishing`) counts as posted: a lost answer is never retried without `--force` and a look at the Page. If the Pages API refuses the video (for example its length), the episode is NOT trimmed: `FB-PROCESS` reports the API's words and stops.

**Replies** are drafted by `ig_board.py` in the page's voice (templates, no model, no tashkeel) and wait on the Comments tab. the owner approves or edits; the Harvest task sends approved ones through `ig.py reply` (official API, own account). `board/config.json` can turn on `auto_reply` for counted votes only; limits 10 a day and 3 a run. Default: off.

**What the missing token blocks.** Posting, the 14:00 harvest, likes and comment counts, replies, the token-age alert. Until `~/.config/story-wrap/instagram.env` has `IG_USER_ID` and `IG_ACCESS_TOKEN`: Post and Harvest write `NO-TOKEN` and exit 0, the board shows "No Instagram token yet", and production stops after one finished episode (the loop gate). Still working: the first episode's Daily run, gates and critic, and the Today, Schedule and Health tabs.

Review, then register (nothing registers itself):

```
powershell -ExecutionPolicy Bypass -File "<repo>\tools\register-tasks.ps1" -DryRun
powershell -ExecutionPolicy Bypass -File "<repo>\tools\register-tasks.ps1" -WithServer
uv run tools/daily.py plan-task        # also prints the monthly token-refresh task
```

Remove with `-Remove`. The older per-episode one-shot (`ig.py plan <ep>`, `StoryWrap-Votes-<ep>`) still works but is no longer needed: the hourly Harvest task finds due episodes itself.

## Done when

`ig.py status` shows no blocker, `decision.json` exists, `next-brief.md` has the winner (or the showrunner pick) and the reuse list, and the parked branch file exists.

- Post captions and replies go through `display_text()` (no tashkeel); `ig.py publish` refuses with IG-NO-TASHKEEL otherwise.

## Engagement flow (the owner 2026-10-27, R-474 to R-480)

`tools/engage.py run [--go]` is one tick, run every 10 min between 08:30 and 23:30 Amman. Dry unless `--go`.

| # | Step | What happens | Where it lives |
|---|------|--------------|----------------|
| 1 | Harvest | read only: Instagram and Messenger DMs, Instagram, Facebook and YouTube comments (`tools/inbox.py`); YouTube has no DMs | `work/inbox/` |
| 2 | Rules gate | window (72 h for comments, own 24 h for DMs), our own account, thread already answered, spam / hostile / sensitive / under-18 are never answered; empty-text GIF, sticker or image = kind `media` | `engage.classify`, `decide_item` |
| 3 | Haiku decides | ONE call for the batch: `{action: reply\|like\|react\|skip, text, reaction, why}` with bible facts; ice-breaker taps and the welcome are canned, no model; the model failing = template bank | `engage.haiku_llm`, `data/engage/dm_auto.json` |
| 4 | Text gates | no tashkeel, no link / hashtag / mention, no bait, 220 characters, 3 emoji, no duplicate in 14 days (dialect and non-Arabic allowed for the model) | `engage.reply_problems(relaxed=True)` |
| 5 | Send / like / react | reply 2-8 min after the item (DMs 1-4), or now if older; Facebook comment like and DM `love` reaction by API; Instagram and YouTube comment likes = "like: no API" in `work/engage/likes_todo.jsonl` for the Lead's browser session; keyword comment = one private reply | caps in R-475 |
| 6 | Log | `sent.jsonl`, `likes.jsonl`, `likes_todo.jsonl`, `pm.jsonl`, `decisions.jsonl` (no viewer text), `state.json` | `work/engage/` |
| 7 | Board | each platform tab shows the Engage log: who, what they wrote, our reply, action, Haiku's why, HH:MM:SS Amman, and the "like: no API, do in session" list | `tools/monitor_board.py engage_log`, `board/index.html engageLog` |

**Trigger (R-481).** The tick above is no longer only hourly: `tools/watch.py` (task `StoryWrap-Watch`) polls one light signal per platform (Instagram and Facebook comment counts of the open reels and the Page conversations' `updated_time`; YouTube's 5 newest comment threads) every 60 s, YouTube 150 s, jittered, and starts a tick when a signal changed. Meta webhooks need a public HTTPS endpoint and YouTube has no comment push, so polling is the only option here. The hourly task remains the safety net.

One-time: `uv run tools/dm_auto.py apply --go` (the Lead) sets the Instagram ice breakers.

## After the post: five steps (A1-A5) (the owner 2026-10-27, R-483 to R-490)

From the ak4app carousel (analysis, adaptations and exclusions: `research/algo/after-post-ak4app-2026-10-27.md`). Code: `tools/after_post.py`, `engage.start_catchup`, wired into `tools/post_extra.py` so the Post task runs them for each episode (E02 on). Everything is dry without `--go`.

| Step | What | Who does it | Where it shows |
|---|---|---|---|
| A1 | Sticker story: Question sticker (ideas for next time), emoji slider, countdown to the next slot. The API adds no stickers, so the automatic announce story stays and this is a card of texts over the cover | the owner, from the phone | board, Instagram tab, "Sticker story for your phone"; `work/episodes/<ep>/after-post/sticker-story.json` |
| A2 | ONE first comment of ours under the live Instagram Reel (and the Facebook Reel at its go-live): an open question plus a save ask, from `after-post.json` `first_comment` or a template; then recorded and never repeated | automatic (official API) | `first-comment.json`, `post.json` / `facebook.json` key `first_comment` |
| A3 | Drafts for the latest post of up to 10 niche peers a day | the owner posts by hand | board "Comments to post (the owner)" |
| A4 | Catch-up: when a new episode goes live, one pass answers the still-unanswered viewer comments of ALL earlier episodes, outside their 72 h windows | automatic (engage ticks) | `decisions.jsonl` (`catchup_start`, items with `catchup`) |
| A5 | Drafts for the latest reel or carousel of up to 3 big peers a day (50,000 followers or more) | the owner posts by hand | board "Comments to post (the owner)" |

- **Texts** live in `bible/series/<series>/episodes/<ep>/after-post.json` (`first_comment`, `story_question`, `story_slider`; template `kb/templates/after-post.example.json`); a missing or gate-failing text falls back to `after_post.FIRST_COMMENT_TEMPLATES` / `STORY_QUESTIONS` / `SLIDER_PROMPTS`.
- **A2 rules:** the text passes `secret_gate`, the reply gates (no link, hashtag, bait, digit to type, call to follow; one question mark; 220 characters) and the no-tashkeel check. It goes up only within 6 h of the Reel going live (after that it would no longer be first). The record is written as `posting` BEFORE the call; a lost answer is never retried without `--force`; an HTTP error retries up to 3 times; a missing `instagram_manage_comments` waits 1 h and tries again. The comment id is also the proof of ownership: `engage.collect_items` (`own_ids`), `vote.tally_comments` (`own_ids`) and `ig_board` skip it even when the API hides the author. **Pinning has no API**: the Lead's browser session or the owner pins it.
- **A4 rules:** `engage.start_catchup(root, new_ep)` sets `state.json` `catchup` = {eps, until now + 36 h} once per new episode; every tick then holds the windows of those episodes open, revives comments that expired unanswered, and treats them with the same classifier, caps (5 a tick, 20 a day), jitter, quiet hours and gates; the new episode's own items are sent first. `post_extra` runs one `engage.py run --go` tick the moment the pass opens; the watcher and the hourly task do the rest. Direct messages are not part of it (their 24 h window is Meta's rule).
- **A3 / A5 rules:** targets in `data/engage/peers.json` (`{handle, tier: niche|big, region, why}`; empty until the researcher fills it from `research/peers-2026-10-27.md`). `after_post.peers_run` reads each due peer's media with `business_discovery` (read only, same token), keeps a niche peer's post of the last 7 days and a big peer's newest reel or carousel of the last 3 days (and only if `followers_count` is 50,000 or more), then ONE Haiku call (`story-engager`, no tools, captions fenced as data) drafts comments of the five types (add value, smart question, personal experience, specific praise, light humour) in the post's own language. Gates: the reply gates, no mention of our page or series, no ask to follow, visit, like, share or save, language equal to the post's. No model answer = no draft. Per Amman day at most 10 niche and 3 big drafts; a post is drafted once. Nobody is ever followed or added (R-469).
- **Commands:** `uv run tools/after_post.py first-comment E02 [--go]`, `sticker E02`, `peers [--go]`, `mark <key> posted|skipped`, `status`.
- **Excluded on purpose:** the "93.2% forget" statistic (no source), the DM-keyword call to action (a fixed word to type), slide 8 (an advert).
