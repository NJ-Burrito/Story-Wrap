# Sound bible: how the series sounds

Owner of the words: this file. Owner of the numbers: `tools/sound_profile.json` (the mastering chain owner).
This file never types a level, a frequency or a time. It names the key in the profile, written like `voice.lufs_target`.
If a key named here is missing from the profile, the profile wins and this file is corrected (see "Numbers").

Read with: `VOICE-DATA.md` (where voices come from), `CHECKLIST.md` (what runs before a post), `kb/rulebook.md`
section "Sound engineering (2026-10-26)" (R-446 onward), `research/sound-e01c.md` (the measurements behind the chain).

## 1. Sonic identity

- **Calm, warm, close.** One narrator sits next to the listener and tells them what they see («أنتم»). No announcer, no trailer voice, no hype.
- **Clarity first.** Every word of Modern Standard Arabic must be understood on a phone speaker, in a room, at low volume. If a sound choice and a word compete, the word wins.
- **Arabic MSA intelligibility.** Case endings and long vowels are part of meaning. The chain never cuts word ends, never squashes consonants, and keeps the presence band where Arabic consonants live.
- **One world, one sound.** Each of the three worlds has its own entrance sound (wind window, floor drain, brass slot; `bible/series/series/series.md`). The sound tells the world before the picture does.
- **The heart thread is quiet.** Hero and the voice nobody remembers: quiet, close, no music swell, one line at most (series.md).
- **Phone first.** The normal viewer listens on a phone speaker: mono, nothing low. Every mix decision is measured through the phone simulation in `tools/audio_checks.py`, then on earbuds.

## 2. Voice hierarchy

1. **Narrator.** Carries the story and most of the lines (`CALM-NARRATOR`). Fixed once (`VOICE-DATA.md` §4). Firm, deep, calm reader register.
2. **Characters.** Short lines in their own cast voice and accent (`bible/series/series/voices/casting.json`). A character never sounds louder or closer than the narrator.
3. **Everything else** sits under the voices (section 4).

Narrator and characters are matched to one loudness per take before the bus (`voice.lufs_target`), so the listener never reaches for the volume between speakers. Accent comes from the reference clip and the written word habits, never from level or effects.

## 3. The mastering chain, in order

The chain lives in `tools/calm_mix.py` (preset `phone-first`), called by `tools/calm_compose.py audio <ep>`. It runs on every take and every episode. No take reaches an episode without it.

| # | Stage | What it is for | Keys |
|---|---|---|---|
| 0 | Reference clean (once per voice, at casting) | Deterministic DSP on the reference clip only: trim to speech (the edge cleaner of stage 1: no noise-only lead-in or tail, guards kept), high-pass, gentle denoise with no gate, level. Logged. Chatterbox copies the reference's noise and colour into every take, so the reference is cleaned once, at the source. Casting rule (2026-10-27): a judge clip can pass REF-QUALITY only because the room tone at its edges flatters the floor and the SNR, so a candidate is measured and cast only from its edge-cleaned reference (the j03 method), never from the judged clip; when it fails after the clean, the next candidate of the judge ranking that passes is cast (`voices/audit/cast_next.py`, `VOICE-DATA.md` §5b). | `reference.highpass_hz`, `reference.denoise_db`, `reference.lufs_target`, `take.edge.*` |
| 1 | Take edge clean (`voice.py trim_take`, `tools/voice_edges.py`) | Prevent first: a per-line generation cap from the text and the voice's measured rate, and a stop after the text is spoken (the model otherwise runs on to the cap). Then remove every noise-only window before the first word and after the last one: the speech span is found from four features (energy, F0 voicing, spectral flatness, zero crossings), a guard is kept on both sides, equal-power fades sit inside the guards, and no frame of the span is ever touched (word-initial and word-final consonants such as س ش ف ث ز ه and a final م are inside the span). No model. Post-processing, not a re-voice. | `take.gen_cap.*`, `take.eos.*`, `take.edge.*` |
| 2 | Voice high-pass | Remove rumble a phone cannot play and that eats headroom. | `voice.highpass_hz` |
| 3 | Voice EQ | Cut the boxy low mids a phone turns to honk; lift presence so consonants read. | `voice.eq` |
| 4 | Conditional de-ess | Only on a take whose sibilant band comes too close to its speech band. A de-esser on every take dulls it. | `voice.deess_when_db`, `voice.deess` |
| 5 | Voice compressor | Gentle, per voice, to even syllables. Never on the sum. The pause floor that closes this stage runs after the limiter (row 7b). | `voice.comp` |
| 6 | Per-take level match | Every take to one gated loudness: narrator and characters at one level. | `voice.lufs_target` |
| 7 | Voice bus limiter | Keeps voice peaks below full scale before the master gain. | `voice.limit` |
| 7b | Pause floor (R-472, `voice_master.stage_pause_floor`), last stage of the take chain, after the limiter | The compressor and the limiter lower the loud part and let their gain recover under every soft frame, so the p95 falls and the soft frames do not: the pauses end closer to the voice than the take was generated (E01C L05, L13, L19, L22, L23: inside the limit when generated, over it after the chain; figures in R-472). Frames more than `voice.measure.pause_below_p95_db` under the p95 of the take before the compressor take the gain the loud part lost: the smallest cut, in steps, until TAKE-QUALITY's pause distance (same frames, same median) is back at the distance the take came in with. No frame above that line changes, nothing is raised, no threshold or gate moves. A take generated over the limit stays over it: that is the TTS, so the line is regenerated as a new line (E01C L16, L18, L21), not patched here. | `comp.pause_floor`, `comp.pause_floor_step_db`, `comp.pause_floor_max_db`, TAKE-QUALITY `max_pause_rel_db` |
| 8 | Music bed | A synthesised pad (numpy, no licence question), band-limited, with a scoop where speech lives, set under the voice as measured on the phone. | `bed.highpass_hz`, `bed.lowpass_hz`, `bed.scoop`, `bed.below_voice_lu` |
| 9 | SFX | Per-sound band limits, mono fold, level set relative to the voice on the phone simulation (never from the file's peak), peak kept under the voice peak, stacked duplicates dropped. | `sfx.band.<sound>`, `sfx.rel_db.<kind>`, `sfx.sound_adj_db.<sound>`, `sfx.gain_limits_db`, `sfx.peak_under_voice_db`, `sfx.dedupe_window_s` |
| 10 | Ducking | An envelope computed from the voice stem: fixed depth per bus, lookahead so the dip lands before the word, short gaps bridged so the bed does not pump. An intro dip under the opening line. | `duck.depth_db.<bus>`, `duck.lead_s`, `duck.attack_s`, `duck.release_s`, `duck.bridge_s`, `duck.intro_dip_db`, `duck.intro_dip_fade_s` |
| 11 | Master | One linear gain to the delivery loudness, computed from the same stems the checks read; a lookahead limiter only when the true peak needs it. No compressor on the sum. | `master.lufs_target`, `master.true_peak_target_dbtp` |
| 12 | Encode and measure | AAC in the episode file; loudness and true peak measured again on the delivered AAC, because the encode moves peaks. | `delivery.<platform>.*` |

Stems `voice.wav`, `bed.wav`, `sfx.wav` are written after ducking and after the master gain, so their sum is the delivered mix. The checks read them. The `legacy` preset keeps no stems and fails the checks on purpose: it is for comparison, never for delivery.

## 4. Mix hierarchy

**Voice > SFX > music bed.** Always, in every scene, on the phone.

- The voice is the reference. Everything else is set relative to it, measured the way a phone plays it.
- SFX sit under the dialogue they share a moment with. A cue may lead a word or follow it; it never covers it (`AUDIO-PEAK` refuses a cue louder than the dialogue under it).
- The bed is felt more than heard while somebody speaks, and fills the pauses between lines.
- Ducking is computed, not reactive: fixed depth per bus, from the voice stem. Sidechain compression with a swinging depth is not used.
- A dramatic cue (the steamship horn of E01C, note C3) may sit closer to the voice by design, in the pause before a line, and still inside the clarity floor.

## 5. Music bed rules

- Synthesised pad by default: deterministic, licence-free, notes and harmonics in the band a phone plays.
- No energy a phone cannot play as the main content. A sub layer may exist for earbuds only and stays small.
- Wide but mono-safe: both channels carry the same waveform; width comes from slow swells, never from detune or phase tricks (`AUDIO-MONO`; test `test_bed_pad_is_mono_safe`).
- A scoop in the speech band so the bed never fights consonants.
- No swell under the heart thread (section 1).
- Any recorded music needs a free licence row in `assets/audio/LICENCES.md` and passes the same band and level rules.

## 6. SFX rules

- Every transition has a sound; props and hand actions have foley (`CALM-TRANSITION-SFX`, `CALM-FOLEY`, `CALM-CHOICE-SFX`, `CALM-INTRO-SFX`).
- Level by loudness relative to the voice, never by the file's peak. Two files of the same peak can differ hugely in loudness.
- Band-limit each sound before measuring it. Low energy is rumble on a phone.
- Never stack the same sound twice at one moment (a join sound and a shot foley on the same frame). The chain drops duplicates; the plan should not create them.
- A sound that is weak on a phone (`uv run tools/calm_mix.py sfx-audit` marks it) is replaced in the library, once, not boosted per episode.
- Every sound has a licence row with sha256 in `assets/audio/LICENCES.md` (`AUDIO-LICENCE`). Own synthesised sounds are labelled OWN.

## 7. Silence and room tone

- No silence gap longer than `silence.max_gap_s` in the delivered audio (`CALM-NO-SILENCE`). Silence is not the pacing; the narrator carries the story.
- Pauses are never digital zero. The bed fills them. A deliberate quiet moment is bed and room, not a hole.
- References and takes must not carry digital silence inside speech (a noise gate or denoiser fingerprint). `REF-QUALITY` and `TAKE-QUALITY` refuse it.
- A recorded room tone is used only if it passes the phone check; the old `room-tone-503255` is all below what a phone plays and is not a room tone for us.

## 8. Loudness and true peak per platform

One master serves Instagram, Facebook and YouTube unless the profile gives a platform its own target.

| Platform | Integrated loudness | Tolerance | True peak ceiling | Source of the number |
|---|---|---|---|---|
| Instagram Reels | `delivery.instagram.lufs_target` | `delivery.instagram.tolerance_lu` | `delivery.instagram.true_peak_max_dbtp` | measured on delivered reels, `kb/guides/reels.md` section 3 |
| Facebook Reels | `delivery.facebook.lufs_target` | `delivery.facebook.tolerance_lu` | `delivery.facebook.true_peak_max_dbtp` | the profile cites it |
| YouTube | `delivery.youtube.lufs_target` | `delivery.youtube.tolerance_lu` | `delivery.youtube.true_peak_max_dbtp` | the profile cites it |

- Measured on the delivered AAC, not on the WAV (`CALM-LOUDNESS` in the calm format, `EP-LOUDNESS` in `compose.py`, and `AUDIO-PEAK`).
- The master aims below the ceiling (`master.true_peak_target_dbtp`) so the encode has headroom.
- We never upload a file that fails, and never trust a platform to fix loudness.
- A platform target with no source in the profile is a gap to report, not a number to guess.

## 9. What "done" sounds like

- Every word is clear on a phone at low volume, including the quiet ends of sentences.
- Narrator and characters sound like one production: same level, same closeness, same room.
- No breathing under the voice (no pumping), no hiss in pauses, no click or tail at the end of a take.
- Effects land on the action and get out of the way of the next word.
- The bed is present in the pauses and does not swell over the heart thread.
- Mono sounds the same as stereo.
- The numbers pass every gate in `CHECKLIST.md`, and the owner's ear is the last check. Numbers are not ears.

## 10. Failure modes and their fix at the source

A fault is fixed at the stage that owns it, once, for every future episode. Never by hand gain on one line, one cue or one episode.

| What is heard or measured | Root cause | Fix at the source | Gate that sees it |
|---|---|---|---|
| Noise, hiss or a "boxy" voice in every take of one speaker | The reference clip carries it; Chatterbox copies it | Clean or replace the reference (`VOICE-DATA.md`); ban a bad reference in `bible/voices-banned.json` | `REF-QUALITY`, `TAKE-QUALITY`, `VOICE-BANNED-REF` |
| Trailing breath or noise after a line | Take not end-trimmed | The trim stage in `voice.py` | `VOICE-TAIL` |
| A window of noise only, no words, before or after a line (the owner 2026-10-26) | The model ran on past the text (no EOS, up to the token cap); the old trim took a drone or a loud breath for speech; the reference carried room tone at its edges | Generation cap and EOS stop per voice, the edge cleaner on every take, the reference cleaned once | `VOICE-EDGE-NOISE` |
| Effects as loud as the words | SFX gain set from file peak, or stacked duplicates | Loudness-relative SFX levels and dedupe in the chain; fix the plan that stacks cues | `AUDIO-PEAK`, `AUDIO-DIALOGUE-CLARITY` |
| Music inaudible on a phone but loudness spent | Bed energy below what a phone plays | Bed band and pad design in the chain | `AUDIO-DIALOGUE-CLARITY`, `sfx-audit` style measure on the bed |
| Breathing or pumping under the narrator | Compressor on the sum, or reactive sidechain ducking | Per-source compression and computed ducking | `AUDIO-DIALOGUE-CLARITY` (weakest tenth) |
| Bed or effects vanish in mono | Out-of-phase or detuned stereo | Same waveform on both sides; width from swells | `AUDIO-MONO` |
| Too quiet or too loud on a platform | Master target or encode headroom wrong | The profile `delivery.*` and `master.*` keys | `CALM-LOUDNESS`, `AUDIO-PEAK` |
| A dead hole in the audio | A plan gap, or bed missing | The plan timing or the bed stage | `CALM-NO-SILENCE` |
| A sound weak on phones in every episode | The library file itself | Replace it in `assets/audio/sfx/` with a new file and licence row; old file stays | `calm_mix.py sfx-audit` |
| Quiet word endings thinned or gone after mastering (measured 2026-10-26: the old expander pulled voiced endings down by up to 15 dB) | The expander lowered every frame 24 dB under the loud part, and word endings sit there | The expander acts only on frames the cleaner's detector does not call a sound of a word (`voice.measure.pause.*`); the noise floor is read from the same frames | `VOICE-MASTER` (noise floor), `test_voice_master.py` |
| Pauses closer to the voice after mastering than the take was generated (measured 2026-10-27 on E01C L05, L13, L19, L22, L23; figures in R-472) | The compressor and the limiter lower the loud part and their gain recovers under every soft frame, so the p95 falls and the soft frames do not | The pause floor after the limiter (row 7b, R-472); a take generated over the limit is a TTS fault: regenerate it as a new line | `TAKE-QUALITY` (`max_pause_rel_db`), `test_voice_master.py` |
| A cast voice noisy or boxy although its judge clip passed REF-QUALITY (2026-10-27: extra-c2, han-c4, guide-c1 failed after the clean) | The judged clip carried room tone at its edges, which flattered the floor and the SNR; Chatterbox clones the reference as cloned, not as judged | Cast only from the edge-cleaned reference; walk the judge ranking to the next candidate that passes (`cast_next.py`) | `REF-QUALITY` on the cleaned reference |
| Wrong pronunciation of a word | The vowelled TTS text | Fix `tts_text` and voice it as a new line (`voice.py retext`, R-426); never re-voice the old one | `VOICE-ONCE` |

## 11. Numbers

Every number the sound depends on has one key in `tools/sound_profile.json`. Docs, briefs and new code read the key. The table lists the keys this bible expects and where the value lives in code today, so the chain owner can map them. If the profile names a key differently, the profile wins and this table is corrected in the next bible edit.

| Key | Meaning | Lives today in |
|---|---|---|
| `reference.highpass_hz`, `reference.denoise_db`, `reference.lufs_target` | Reference clean, once per voice | `tools/narrator_deep_refs.py clean` |
| `take.edge.*` (guards, fades, pads, the speech-span features) | Word-safe edge cleaner | `tools/voice_edges.py`, called by `tools/voice.py trim_take` |
| `take.gen_cap.*`, `take.eos.*` | Per-line generation cap and the stop after the text is spoken | `tools/voice.py token_cap`, `install_eos_guard` |
| `voice.measure.pause.pad_s`, `voice.measure.pause.pause_min_s` | Which frames are true pauses: the expander may lower only these, and the noise floor is read from them | `tools/voice_edges.py pause_mask`, `tools/voice_master.py stage_denoise` |
| `take.gen_cap.voices.<speaker>` | Slowest plausible rate of each cast voice (its own takes, its own reference) | `tools/voice.py voice_rate` |
| `checks.edge_noise.*` | Noise-only lead-in and tail limits beyond the guards | `VOICE-EDGE-NOISE` (`voice_edges.edge_problems`) |
| `voice.lufs_target` | Per-take gated loudness before the bus | `calm_mix.PRESETS["phone-first"]["voice_target_lufs"]` |
| `voice.highpass_hz` | Voice high-pass | `voice_hp_hz` |
| `voice.eq` | Voice EQ bands (frequency, Q, gain) | `voice_eq` |
| `voice.deess_when_db`, `voice.deess` | When and how to de-ess | `deess_when_db`, `deess` |
| `voice.comp` | Voice compressor settings | `comp` |
| `voice.limit` | Voice bus limiter ceiling | `voice_limit` |
| `bed.below_voice_lu` | Bed loudness under the voice, phone simulation | `bed_below_voice_lu` |
| `bed.highpass_hz`, `bed.lowpass_hz`, `bed.scoop` | Bed band and speech scoop | `bed_hp_hz`, `bed_lp_hz`, `bed_scoop` |
| `sfx.rel_db.<kind>` | Cue loudness re voice per kind (transition, choice, foley) | `rel_db` |
| `sfx.sound_adj_db.<sound>` | Per-sound adjustment | `sound_adj_db` |
| `sfx.band.<sound>` | Per-sound high-pass and low-pass | `calm_mix.SFX_BAND` |
| `sfx.gain_limits_db` | Cue gain floor and ceiling | `gain_limits_db` |
| `sfx.peak_under_voice_db` | Cue peak margin under the voice peak | `sfx_peak_under_voice_db` |
| `sfx.dedupe_window_s` | Window for dropping stacked duplicates | `calm_mix.dedupe_cues(window=...)` |
| `duck.depth_db.<bus>` | Duck depth for bed, fg, bg | `duck_db` |
| `duck.lead_s`, `duck.attack_s`, `duck.release_s`, `duck.bridge_s` | Duck timing | `duck` |
| `duck.intro_dip_db`, `duck.intro_dip_fade_s` | Bed dip under the opening line | `calm_mix.INTRO_DIP_DB`, `INTRO_DIP_FADE_S` |
| `master.lufs_target`, `master.true_peak_target_dbtp` | Master gain target and limiter aim | `calm_mix.LOUD_I`, `LOUD_TP`; `compose.LOUD_TARGET_I`, `LOUD_TP_TARGET` |
| `delivery.<platform>.lufs_target`, `.tolerance_lu`, `.true_peak_max_dbtp` | Platform delivery targets (instagram, facebook, youtube) | `compose.LOUD_TARGET_I`, `LOUD_TOL`, `LOUD_TP_MAX` (one set for all today) |
| `silence.max_gap_s` | Longest allowed gap | `calm_compose.SILENCE_MAX_S` |
| `checks.clarity_median_db`, `checks.clarity_p10_db`, `checks.clarity_min_db`, `checks.clarity_share_below_db`, `checks.clarity_share_max` | Dialogue clarity floors | `audio_checks.THRESH` |
| `checks.mono_loss_lu_max`, `checks.mono_clarity_drop_db_max`, `checks.corr_p05_min` | Mono safety | `audio_checks.THRESH` |
| `checks.tp_max_dbtp`, `checks.sample_peak_max_db`, `checks.sfx_over_voice_db` | Peak and cue-over-voice limits | `audio_checks.THRESH` |
| `checks.refq.*`, `checks.takeq.*` | Reference and take quality limits | `voice.REFQ`, `voice.TAKEQ` |

Voice casting settings (engine, exaggeration, cfg weight, temperature per speaker) are not mastering numbers. They live in the casting record (`voices/casting.json`, owned by the casting owner) and, for the narrator, in `bible/sound/narrator-record.json`.

Changing a number: a profile edit by the chain owner, with the measurement that justifies it, in one commit. A check threshold is never loosened to make a mix pass (R-441, R-442).
