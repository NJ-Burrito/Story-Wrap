# Pre-publish audio checklist

Run before an episode posts. Every row is a gate that runs every time; none is skipped to save time.
A FAIL is fixed at the stage that owns it (`SOUND.md` §10), then only that stage and later ones rerun (R-422).
Limits come from `tools/sound_profile.json`; this list names checks, not numbers.

| # | Check | Gate | Run by |
|---|---|---|---|
| 1 | Every reference is CC0 or verifiable public domain, with full provenance | `VOICE-REF` | `uv run tools/voice.py gate <ep-dir>` |
| 2 | No reference is banned | `VOICE-BANNED-REF` | `voice.py gate` |
| 3 | Every reference is clean (floor, SNR, no digital silence, not boxy, not reverberant), measured on the edge-cleaned reference as cloned, not on the judge clip (`VOICE-DATA.md` §5b); a short reference (under 4 s) is flagged for the owner's ear | `REF-QUALITY` | `voice.py refcheck`, `voice.py gate` |
| 4 | Every speaker is cast and uses its cast voice; the narrator is the recorded one | `VOICE-CAST` | `voice.py gate` |
| 5 | Engine is Chatterbox; no Gemini, no paid service; the engine is installed | `VOICE-BANNED`, `VOICE-ENGINE` | `voice.py voice` refuses |
| 6 | Each line voiced once, never re-voiced | `VOICE-ONCE` | `voice.py gate` |
| 7 | Takes clean: no gate gaps, no clipping, no boxy take, no noisy pauses (the pause floor, R-472, keeps the chain from bringing pauses closer to the voice; a take generated over the limit is regenerated as a new line); no trailing noise; no noise-only window before or after the words | `TAKE-QUALITY`, `VOICE-TAIL`, `VOICE-EDGE-NOISE` | `voice.py gate --full` |
| 8 | The narrator carries the story | `CALM-NARRATOR`, `AUDIO-NO-VOICE` | `calm_compose.py gate` |
| 9 | Every sound and music file has a licence row and hash | `AUDIO-LICENCE` | `calm_compose.py audio` |
| 10 | Transitions, foley, choice and intro all have sound | `CALM-TRANSITION-SFX`, `CALM-FOLEY`, `CALM-CHOICE-SFX`, `CALM-INTRO-SFX` | `calm_sfx.py check`, `calm_compose.py gate` |
| 11 | The mix went through the mastering chain (stems exist; not the legacy preset) | `AUDIO-*` need stems | `calm_compose.py audio` |
| 12 | Words clear over music and effects on a phone | `AUDIO-DIALOGUE-CLARITY` | `uv run tools/audio_checks.py check` |
| 13 | Mono is safe | `AUDIO-MONO` | `audio_checks.py check` |
| 14 | True peak and sample peak under the ceiling; no cue louder than the words under it | `AUDIO-PEAK` | `audio_checks.py check`, on stems and on the delivered AAC |
| 15 | No silence gap over the limit | `CALM-NO-SILENCE` | `calm_compose.py gate` |
| 16 | Delivered loudness and true peak on the AAC meet the platform target | `CALM-LOUDNESS` (calm format), `EP-LOUDNESS` (`compose.py`) | `calm_compose.py gate`, `compose.py gate` |
| 17 | The gate report is PASS and newer than `episode.mp4` | `adopt.py status` (R-438) | before any post |
| 18 | the owner's ear | none: a person | after the gates, never instead of them |

Not automated yet (doc rules): written consent for own or talent recordings (`VOICE-DATA.md` §2), the per-platform split of loudness targets when the profile defines one.
