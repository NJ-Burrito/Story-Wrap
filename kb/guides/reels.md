# Reels: market facts and the measured benchmark

Sources: `research/09` section 2, `research/10`, verification pass 2026-10-22. No primary Instagram page was reached in this pass; all platform facts below are secondary.

## 1. Market facts

| Fact | Value | Grade |
|---|---|---|
| Max Reel length | 3 minutes since 18 Jan 2025; Mosseri: "Starting today, you can upload Reels to Instagram up to three minutes long." | S https://www.socialmediatoday.com/news/instagram-officially-expands-reels-length-3-minutes/737766/ |
| Instagram's own length advice | "Reels that are 30-60 seconds long see better performance"; "Create 10 or more Reels per month, on average" (10 Jul 2024) | S https://www.socialmediatoday.com/news/instagram-shares-tips-reels-creators/721054/ |
| Hook metric | "View Rate": share of followers and non-followers who keep watching after the first three seconds (29 Jan 2025) | S https://techcrunch.com/2025/01/29/instagram-gives-creators-more-insight-into-their-reels-performance |
| Ranking signals | Mosseri named watch time, likes and sends; track average watch time, likes per reach, sends per reach | S https://www.socialmediatoday.com/news/instagram-shares-algorithm-insights-2025/738034/ |
| Sends weighting | Sends per reach correlates with reach most (Q&A claim, date unconfirmed). The "3 to 5 times" weighting has no Mosseri source: do not use | S https://www.socialmediatoday.com/news/instagram-chief-post-share-rates-key-driver-reach/716540/ |
| Retention bands by length (7-15 s best, etc.) | Vendor claims, no method | not usable |
| Replays as a signal, loop effect, caption effect, series performance | No source | gap |
| Safe zones | A third-party guide attributes top 14% (about 270 px) and bottom 35% (about 670 px) to Meta; unverified. Meta's help page exists but its numbers were not read: https://www.facebook.com/business/help/980593475366490/ | Q-05 |
| Reel size | 1080x1920 appears in third-party guides; Meta's Reels ad image spec in a search snippet is 1440x2560 | S |
| Loudness | No Instagram statement found | gap |

Implication [J]: completion and a strong first 3 seconds matter more than raw length; launch episodes 30 to 60 s, log every metric per episode, test one longer episode later.

## 2. Episode shape (feeds R-063, R-094, R-115)

1. 0 to 2 s: a moving element and a headline card or the story's question. Do not open on a logo.
2. Change composition every 2 to 5 s.
3. One turn in the middle; the last beat points to the next episode and, in early episodes, loops.
4. Number the episode in the caption and on the cover frame.
5. Do not reuse the inspiration reels' own claims (2 million views, 530 people): unsourced.

## 3. Measured benchmark of the four reels (research/10, all [M])

Delivered Instagram renditions, logged out, yt-dlp 2026.08.19, ffmpeg with `-hwaccel cuda -threads 2`. Reach (views) is not exposed logged out, so likes and comments are only context.

| Reel | Role | Length | Bitrate | Loudness I / peak | Cuts (T=0.3) | Frozen holds >=0.5 s | Likes / comments |
|---|---|---|---|---|---|---|---|
| A Deu0eKalKi1 | inspiration (SEO mascot) | 22.37 s | 2,158 kb/s | -14.1 LUFS / -1.4 dBTP | 5 (13.4 per min) | 0 (0%) | 825 / 2,509 |
| B DezkWyyANhZ | inspiration (animate-anything skill) | 23.17 s | 2,210 kb/s | -14.1 / -2.6 | 18 (46.6 per min, overstated; true nearer 20 to 25 per min) | 0 (0%) | 21 / 8 |
| Baseline 1 DeqjQlmv5MA | stickman serial | 78.80 s | 780 kb/s | -14.1 / -1.9 | 3 (2.3 per min) | 16, 13.63 s (17.3%) | 161,407 / 3,193 |
| Baseline 2 DepIFCzsTdL | Arabic spice reel | 178.00 s | 803 kb/s | -14.6 / +0.1 | 0 | 85, 98.13 s (55.1%) | 24,186 / 397 |

All four: VP9 1080x1920, 30 fps, AAC stereo. Loudness does not separate the groups. Baseline 2's true peak above 0 dBFS can clip after re-encode.

What the measurements say [J on M]:

- The inspiration reels never freeze 0.5 s, cut every 2 to 5 s, hook within 2 s and run 22 to 23 s. Targets: R-092, R-093, R-094.
- Baseline 1 (161,407 likes) shows a serial cliffhanger can carry reach with 17% frozen time and almost no cuts: story continuity beat animation quality there. Do not read this as permission to be static; our bar is premium.
- Baselines score 2 out of 10 against a premium bar by our reading [J]: motion coverage, shot rate, length, bitrate, hook.
- Reel B's FPS meter (1 to 30) is a reusable hook idea: make the quality visible. Reel A's counting number in the hook is another. [J]
- "Hojas Studio" was not found; the closest is Hojandina Studio (Colombian 2D explainer studio), unconfirmed (Q-10).

## 4. Probe commands (reuse for R-114)

```
ffprobe -v error -show_entries stream=codec_name,width,height,r_frame_rate,bit_rate -show_entries format=duration,size -of compact FILE
ffmpeg -hwaccel cuda -threads 2 -i FILE -af ebur128=peak=true -vn -f null -
ffmpeg -hwaccel cuda -threads 2 -i FILE -vf "select='gt(scene,0.3)',showinfo" -an -f null -
ffmpeg -hwaccel cuda -threads 2 -i FILE -vf "freezedetect=n=0.003:d=0.5" -an -f null -
```

## 5. Tools named in the reels (research/10)

- `rossark0/rossark-motion-skill`, MIT, 227 stars: principles usable as written (one clock per scene, pivots, follow-through, no idle motion that never stops) and measurement helpers (`sheet.sh`, `track_edges.py`, `sample_colors.py`). Its templates target React Native and SwiftUI, not our stack. Run the `nj-security-review` skill before installing anything. [S research/10]
- `illyism/seo-skills`: SEO packs, two call paid services, out of scope.
