# Open questions, ranked by what they block

Owner column: N = the owner decides; L = Lead; R = a research agent can close it. Update through the Lead only.

## Blocks everything after writing

| ID | Question | Blocks | Owner | How to close |
|---|---|---|---|---|
| Q-01 | Final animation style: Option A, B, or A with B opt-in; colour policy (full colour or limited palette); run the one rehearsal? | Sketch look approval, all animating, grade, pipeline tests | N | `style-decision.md` |
| Q-14 | Who reviews each culture, and how, given "no paid services"? Sensitivity readers are normally paid and booked ahead [S research/05]. R-041 needs a named reviewer per culture before a bible closes | Closing any character or world bible; sketch approval | N | Decide: volunteer/community readers, cultures limited to those the owner can source, or invented cultures first |
| Q-16 | Voice and music for episodes: no tool chosen in this KB. the owner's standing voice rule applies (single TTS model, one take); music source and licence not researched | Stage 11 sound | N / R | Short research lane |

## Blocks the animating stage

| ID | Question | Blocks | Owner | How to close |
|---|---|---|---|---|
| Q-02 | SDXL base Attachment A (use-based restrictions) read in full; confirm commercial use fits | Any SDXL asset in a published episode | R | Open LICENSE.md in a browser and read Attachment A |
| Q-04 | VRAM/throughput of SDXL + ControlNet scribble + IP-Adapter on the 2060 at 768 px; LoRA on 6 GB; depth and RIFE cost | Pipeline plan, batch size, LoRA decision | R | One rehearsal shot with `nvidia-smi` log; one short LoRA test run |
| Q-06 | HDR-grade look on 8-bit SDR delivery: a sourced grading method and tool | Premium light target | R | Search for free tone-curve/LUT tools with licences; test on one shot |
| Q-07 | Parallax tool and its licence (DepthFlow licence unread) | 2.5D camera | R | Read repo LICENSE; test on one background |
| Q-13 | xinsir lineart licence (401); scribble is cleared | Using lineart instead of scribble | R | Open the repo in a browser |
| Q-03 | Real-ESRGAN pretrained weights terms | Upscaling for published frames | R | Read repo LICENSE and weight release notes |
| Q-09 | RTX 2060 NVENC support for chosen encoder settings | Final encode settings | R | `ffmpeg -h encoder=h264_nvenc` |
| Q-08 | Spider-Verse: on twos everywhere or selective; motion blur present or not; halftone mechanics | Fidelity of Option B | R | Primary SIGGRAPH/Imageworks material |

## Blocks the composing stage

| ID | Question | Blocks | Owner | How to close |
|---|---|---|---|---|
| Q-05 | Instagram safe-zone numbers (top and bottom overlay) | Layout, captions | R | Read the Meta help page https://www.facebook.com/business/help/980593475366490/ in a browser, then confirm on a phone |
| Q-15 | Primary Instagram sources for the 3-minute cap, ranking signals, View Rate, 30-60 s tip, loudness | Public claims, length strategy | R | Find Mosseri/Instagram posts |
| Q-17 | Episode length: genre guides assume 60 to 90 s, Instagram advice is 30 to 60 s, inspiration reels are 22 to 23 s | Script timing | N | Pick the launch band; default 30 to 60 s (R-111) |
| Q-10 | "Hojas Studio": not found; closest Hojandina Studio (Colombian 2D explainer studio) | Using it as a model | N | the owner sends the handle or link |

## Does not block, but weakens decisions

| ID | Question | Owner | How to close |
|---|---|---|---|
| Q-11 | Story Grid per-genre lists and Truby's genre chapters not retrieved; WEBTOON genre count; Japanese viewer survey source; microdrama genre shares | R | Read the books/sources |
| Q-12 | Thin sources: two-point perspective, facial-muscle expression, screentone, Drawabox official lessons, Loomis, Vilppu, Hampton | R | Dedicated reads |
| Q-18 | No survey ranks styles; no fan-art volumes measured | R | Logged-out counts on Pixiv/DeviantArt tags if wanted |
| Q-19 | Reels retention by genre, style, loops, captions, series: no data | L | Ship episodes 1 to 3 and log (R-116) |
| Q-20 | Across the Spider-Verse and Demon Slayer current totals; Arcane season 2 numbers | R | Box Office Mojo / Netflix pages |
