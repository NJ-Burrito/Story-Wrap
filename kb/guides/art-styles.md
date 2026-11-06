# Art styles: reconciled ranking, matrix, Arcane

Sources: `research/03`, `research/04`, plus the 2026-10-22 verification pass. Decision file: `../style-decision.md`.

## 1. Why R03 and R04 disagreed

- R03 ranked by breadth of hard evidence (anime first, Western flat 5th, Arcane 6th and left to R04). R04 ranked by audience love at cinema scale (Pixar first, Arcane 5th, Western flat 6th, so Arcane fell between the lanes).
- Both lanes analysed Western flat; neither analysed Arcane in depth. Section 4 fills that.
- Neither found surveys, fan-art counts or a single metric that compares all ten. Every rank is therefore a judgement on unlike metrics. [J]

## 2. Reconciled top 10 (by mass reach, hard evidence first)

| # | Style | Best verified evidence | Grade |
|---|---|---|---|
| 1 | Pixar/Disney 3D | Zootopia 2 about $1.703B worldwide, highest-grossing Hollywood animated film (19 Jan 2026) | V https://www.cartoonbrew.com/box-office-report/zootopia-2-highest-grossing-hollywood-animated-film-258294.html |
| 2 | Japanese anime/manga | Demon Slayer: Infinity Castle above 106.4 billion yen by 16 Nov 2025; Crunchyroll 21M paid subscribers May 2026 | S https://www.nippon.com/en/news/l00372/ , https://www.broadbandtvnews.com/2026/05/11/crunchyroll-reaches-21-million-subscribers/ |
| 3 | Ghibli painterly | Studio total about $1.396B from 19 films to Nov 2021 (Guinness) | S https://www.guinnessworldrecords.com/world-records/107736-most-successful-foreign-language-animation-studio |
| 4 | Spider-Verse comic hybrid | Across the Spider-Verse $690.8M worldwide ($381.6M domestic, $309.2M international) | V https://www.the-numbers.com/movie/Spider-Man-Across-the-Spider-Verse-%282023%29 |
| 5 | Western cartoon, CalArts flat | Bluey 55.62 billion US minutes in 2024 (Nielsen); 45B in 2025 | S https://thedesk.net/2025/01/nielsen-most-streamed-tv-movies-2024/ |
| 6 | Arcane painterly 3D | 34.17M hours in its first full Netflix week, 38.42M in week two; Emmy for Outstanding Animated Program 2022 | S https://whats-on-netflix.com/news/how-well-has-arcane-done-on-netflix-all-the-stats-so-far |
| 7 | Korean webtoon/manhwa | Domestic market 2.286 trillion won in 2024, up 4.4% | S https://www.kedglobal.com/us/webtoons/newsView/ked202501030004 |
| 8 | Stop-motion/claymation | Chicken Run about $227.8M (2000), still the record for stop-motion | S https://www.the-numbers.com/movie/Chicken-Run |
| 9 | French BD/ligne claire | France BD market 68M copies in 2024 (print, not screen) | S https://www.livreshebdo.fr/article/le-marche-de-la-bande-dessinee-en-repli-en-2024 |
| 10 | Motion graphics/corporate flat | No consumer-love evidence found | gap |

Ordering rules: box-office and streaming figures that have a dated third-party number outrank print or market-size figures; anime over Pixar on breadth is arguable (anime is many styles) so Pixar leads on the single clean number. Ranks 7 to 10 are measured in different media and are soft. Out of pool: Ne Zha 2 (about $1.98B by 1 March 2025) [S https://www.nbcnews.com/news/world/chinese-film-nezha-2-becomes-worlds-highest-grossing-animated-movie-rcna192753]. Metric conflicts: Arcane is measured in hours (FlixPatrol: about 220.7M cumulative to June 2026 [S https://flixpatrol.com/title/Arcane/hours/]); R03's "34M views" is a different metric. Demon Slayer's dollar total (about $737M on an undated Box Office Mojo snippet) is not used.

## 3. Matrix (R04 scores 1 to 5, all judgement [J])

Cost 5 = cheapest; AI feasibility 5 = most feasible on 6 GB. "Fit sum" is our unweighted sum of the six project columns (Reels, cost, AI, premium, distinct, B&W); audience love is excluded because it is the ranking above. Derived [J].

| Style | Love | Reels | Cost | AI | Premium | Distinct | B&W | Fit sum |
|---|---|---|---|---|---|---|---|---|
| Pixar/Disney 3D | 5 | 3 | 1 | 2 | 5 | 4 | 2 | 17 |
| Anime/manga | 5 | 4 | 2 | 3 | 4 | 4 | 5 | 22 |
| Ghibli | 5 | 3 | 1 | 2 | 5 | 4 | 4 | 19 |
| Spider-Verse hybrid | 4 | 4 | 2 | 3 | 5 | 5 | 5 | 24 |
| Arcane | 4 | 3 | 1 | 2 | 5 | 4 | 3 | 18 |
| Western flat | 4 | 4 | 4 | 4 | 3 | 3 | 4 | 22 |
| Webtoon | 4 | 5 | 3 | 4 | 3 | 3 | 5 | 23 |
| Stop-motion | 3 | 3 | 1 | 1 | 4 | 5 | 2 | 16 |
| Ligne claire | 3 | 2 | 3 | 4 | 4 | 3 | 5 | 21 |
| Corporate flat | 2 | 4 | 5 | 5 | 2 | 1 | 3 | 20 |

Reading: the ink-native styles (Spider-Verse, webtoon, anime, ligne claire) lead on fit. 3D painterly styles (Pixar, Arcane) and stop-motion lead on prestige and lose on a 6 GB GPU and on black-and-white ink. Ghibli: borrow the idea (rich background, simple character), never the studio's look; the "Ghiblification" wave and IP tie make a Ghibli-like look a legal and taste risk [S research/04].

## 4. Arcane in depth (the gap)

- **Technique.** Characters are 3D (Maya: modelling, rigging, keyframe animation, virtual camera), with textures painted by hand in Photoshop to mimic oil brushstrokes; highlights and shadows are painted onto the textures instead of relying on CG lighting; smoke, explosions and Jinx's scribbles are hand-drawn 2D effects at 12 fps while characters and environments run at 24 fps; Nuke and After Effects composite [S https://redsharknews.com/why-netflixs-arcane-looks-so-good-how-fortiche-ramped-up-the-animation-pipeline]. Backgrounds use projected paintings rather than modelled objects, and a Fortiche lead said most effects come from four or five 2D artists, animated on twos [S search summary of the iAnimate podcast with Alexis Wanneroy; transcript not read].
- **Why it is loved.** Painterly texture plus 2D effects on 3D gives a hand-made look with cinematic camera; Fortiche aimed for "real" and "raw", imperfect characters [S research/07 citing SyncSketch and Hollywood Reporter]. Emmy 2022, first streaming show to win Outstanding Animated Program [S https://www.invenglobal.com/articles/17816/arcane-wins-emmy-for-outstanding-animated-program].
- **Lessons we can use on 6 GB.** (1) Paint light into the textures instead of simulating it: cheap and art-directable. (2) Mix rates on purpose: 2D effects at 12 fps over 24 fps characters. (3) Projected paintings for backgrounds give depth from a depth map, not a 3D scene. [J]
- **What we cannot use.** The full 3D character pipeline is too heavy for the hardware and the tooling (Maya, Nuke) is not free; a 300-person team built it [S Red Shark News]. B&W ink translation is weaker (score 3). [J]
- **Verdict.** Arcane is a lighting and effects reference, not a base style.

## 5. Candidate looks and the project brief

| Brief item | Best-matching evidence |
|---|---|
| Premium, depth, HDR-grade light | Arcane (painted light), Pixar (GI), Ghibli (painted backgrounds); on our hardware reached by layered 2.5D + painted light + grade (`../style-decision.md`) |
| Black-and-white ink art book | Spider-Verse, webtoon, anime/manga, ligne claire |
| Extreme, distinct cast | Spider-Verse (rate and colour per character), stop-motion (physical identity), anime (silhouette) |
| Reels 9:16 | Webtoon (native vertical), anime (panel format) |
| Cheap to keep consistent | Flat fills, clean line (Western flat, webtoon, ligne claire) |

## 6. Rules this guide feeds

R-004, R-020 to R-022 (evidence), R-070 to R-080 (sketch), R-090 to R-096 (animate). Detail: `research/03`, `research/04`.
