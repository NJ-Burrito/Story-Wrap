---
name: bg-duck
description: Put background music under a voice track (narration, reel, any clip) with the Story-Wrap calm_mix chain - music looped/trimmed to the voice, faded, set under the voice, ducked by a voice-keyed envelope with lookahead, mastered to -14 LUFS, limited only when needed. Use for "music under the voice", "duck the music", "mix narration with a bed", "background music too loud".
---

# bg-duck: music bed under a voice

One command, local, no model and no API. It reuses the episode chain (`tools/calm_mix.py`,
numbers from `tools/sound_profile.json`), so a stand-alone clip sounds like an episode.

```
"<repo>/tools/vendor/earshot/.venv/Scripts/python.exe" \
  "<repo>/.claude/skills/bg-duck/scripts/duck.py" VOICE MUSIC OUT.wav
```

Options: `--depth-db` (default 9, the bed duck depth), `--below-lu` (bed loudness under the voice,
default from the profile), `--fade-in 1`, `--fade-out 2`, `--json`.

## Why not ffmpeg sidechaincompress

The episodes used it first and dropped it (research/sound-e01c.md): its depth swung with the voice
level and it had no lookahead, so the first syllable played over full music. Here the voice decides a
fixed depth, the duck starts 80 ms before the word, and gaps under 0.3 s stay ducked.

## What it reports (gate)

Printed JSON: `integrated_lufs`, `true_peak_dbtp`, `limited`, `duck_depth_measured_db` (bed level
while speaking vs the same bed undocked), `pass`. Exit 1 when loudness is more than 1 LU off -14 or the
true peak is over the target. Fix the input or the option, never the threshold.

## Inside an episode

Do not call this for episodes: `calm_compose.py audio <ep>` already runs the full chain with SFX
buses and the intro dip. This skill is for clips outside the episode pipeline.

Music must come from a licensed source (research/2026-11-06-reset/skills/bg-music.md).
