# Contributing to Story-Wrap

Thanks for helping. Small pull requests with one topic each are easiest to review.

## Start here

- New? Look for issues labelled [good first issue](https://github.com/NJ-Burrito/Story-Wrap/labels/good%20first%20issue).
- Bug or idea: open an issue from the templates first, so we agree on the change before you write it.

## Run the checks

```bash
PYTHONUTF8=1 uv run -q --no-project --with pytest --with numpy --with scipy --with pillow --with requests --with jsonschema python -m pytest tools/tests -q -rs -p no:cacheprovider
```

Tests use fakes and the neutral fixtures in `tools/tests/fixtures/`. A test that needs your own series data skips with `needs your own project data:`. The list below groups the tests by the data they need. Pytest reports parametrized cases separately. Other skips, such as missing FFmpeg or PowerShell, have their own reasons.

**`catalogue/characters/<id>/artbook-proportions.json derived from your approved art-book sheets`**

- `test_art_proportion.py::test_reference_files_are_derived_from_the_approved_sheets` (3 cases)

**`tools/render/characters/<id>.js (your characters' rig profiles)`**

- `test_art_proportion.py::test_close_profiles_keep_art_book_scale`

**`calm kits (tools/templates/calm/kits/<char>.json and .js, built from your characters' smoke shots) and the character catalogue`**

- `test_calm.py::test_actor_template_resolves_validates_and_writes_a_shot_folder` (7 cases)
- `test_calm.py::test_camera_plan_and_spec_build_and_pass_the_spec_gate` (7 cases)
- `test_calm.py::test_durations_snap_to_the_frame_grid_and_are_bounded`
- `test_calm.py::test_missing_or_unknown_inputs_are_refused_not_guessed`
- `test_calm.py::test_the_expression_arrives_on_a_neutral_face_and_the_peak_is_the_arrival`
- `test_calm.py::test_reaction_turns_one_expression_into_another`
- `test_calm.py::test_one_subject_per_frame_except_the_two_shot_and_no_touch_distance`
- `test_calm.py::test_two_shot_spec_declares_the_no_touch_proof`
- `test_calm.py::test_a_passed_shot_is_not_rewritten_by_a_template`
- `test_calm.py::test_kits_are_complete_and_name_real_catalogue_files`
- `test_calm.py::test_kit_status_names_the_characters_that_cannot_be_shot_yet`
- `test_calm.py::test_generic_scene_names_no_character`
- `test_calm.py::test_every_kit_has_its_drawing_hook_and_the_plans_plain_feelings_resolve`
- `test_calm.py::test_scene_parameters_for_the_kit_hook_travel_in_shot_json`
- `test_calm.py::test_a_quiet_face_puts_the_declared_peak_on_the_blink`
- `test_calm.py::test_a_locked_camera_needs_and_keeps_its_reason`
- `test_calm.py::test_a_changed_camera_changes_shot_json`
- `test_calm.py::test_insert_depth_builds_real_planes_and_a_calm_dolly` (3 cases)
- `test_calm.py::test_insert_depth_refuses_a_prop_without_a_hero_drawing_and_an_occluder_inside_the_lens`
- `test_calm.py::test_insert_depth_data_reaches_the_scene_through_shot_json_and_the_scene_draws_it`

**`calm kits (tools/templates/calm/kits/<char>.json and .js, built from your characters' smoke shots)`**

- `test_calm_fixes.py::test_grade_defaults_to_nothing_so_no_cached_shot_changes`
- `test_calm_fixes.py::test_grade_reaches_calm_json_and_shot_json_and_is_bounded`
- `test_calm_fixes.py::test_hero_lamp_thread_is_a_scene_param_drawn_after_the_key_lamp_and_absent_by_default`

**`assets/audio/LICENCES.md (your sound licence register)`**

- `test_compose.py::test_real_register_rows_are_all_usable`

**`your early episodes under bible/series/<series>/episodes`**

- `test_format_v2.py::test_the_real_early_episodes_give_the_known_cast`

**`kb/lessons/ledger.jsonl (your own lessons ledger)`**

- `test_heal.py::test_seeded_ledger_is_complete`

**`voice casting (bible/series/<series>/voices/casting.json) and its reference clips`**

- `test_line_fit.py::test_refit_mark_lets_the_voice_stage_voice_only_the_new_id`

**`calm kits (tools/templates/calm/kits/<char>.json and .js, built from your characters' smoke shots) and the voice casting`**

- `test_lipsync.py::test_shot_carries_the_track_in_json_and_spec`
- `test_lipsync.py::test_a_shot_with_no_lipsync_key_is_not_voice_aware`
- `test_lipsync.py::test_a_line_that_outruns_the_shot_is_refused`

**`your character catalogue (catalogue/characters/<id>/ face files)`**

- `test_lipsync.py::test_visemes_skip_the_narrator_and_read_the_trimmed_take`

**`your characters' rig modules (tools/render/characters/<id>.js)`**

- `test_multi_actor.py::test_two_actor_spec_passes_every_spec_check`
- `test_multi_actor.py::test_draw_order_may_interleave_when_the_spec_declares_it`
- `test_multi_actor.py::test_declared_order_change_is_followed_frame_exact`

**`research/algo/DESIGN.md and the approved episode E01C under bible/series/`**

- `test_stories.py::test_e01c_captions_are_exactly_the_approved_design_texts`

**`voice casting (bible/series/<series>/voices/casting.json), its reference clips and your nj-writer voice registry`**

- `test_voice.py::test_casting_is_legal_and_md_in_sync`
- `test_voice.py::test_manifest_copies_text_and_registry_direction`
- `test_voice.py::test_manifest_refuses_uncast_and_illegal_style`
- `test_voice.py::test_other_engines_are_refused_and_no_network_path`
- `test_voice.py::test_voice_and_casting_enforce_ref_quality`
- `test_voice.py::test_every_real_reference_in_the_casting_passes_ref_quality`
- `test_voice.py::test_voice_one_take_writes_raw_trimmed_and_log`
- `test_voice.py::test_voice_refuses_a_missing_reference`
- `test_voice.py::test_voice_refuses_an_unlicensed_reference`
- `test_voice.py::test_voice_refuses_without_a_gate_receipt`
- `test_voice.py::test_tail_check_runs_on_every_trimmed_take`
- `test_voice.py::test_casting_is_marked_retired`
- `test_voice.py::test_symbols_use_the_characters_letters`
- `test_voice.py::test_visemes_end_to_end`
- `test_voice.py::test_load_failure_frees_every_line_and_keeps_the_cause`
- `test_voice.py::test_mid_line_failure_blocks_only_started_lines`
- `test_voice.py::test_started_line_without_wav_is_blocked_and_gate_agrees`
- `test_voice.py::test_preflight_refuses_and_says_which_resource`
- `test_voice.py::test_voice_writes_measured_seconds_and_measure_refills`
- `test_voice.py::test_measure_fails_without_takes_and_full_gate_needs_seconds`
- `test_voice.py::test_character_band_pass_and_fail`
- `test_voice.py::test_narrator_band_unchanged_and_dialogue_wpm_dropped`
- `test_voice.py::test_every_cast_character_has_a_sourced_band_and_chatterbox_settings`
- `test_voice.py::test_only_dropped_failures_clear_the_result_line`
- `test_voice.py::test_banned_voice_is_refused_by_clip_hash_and_speaker`
- `test_voice.py::test_the_real_banned_list_names_the_old_narrator_and_no_cast_voice_uses_it`
- `test_voice.py::test_retext_drops_every_stale_take_source_not_only_the_first`
- `test_voice.py::test_retext_sets_aside_only_the_takes_whose_words_changed`
- `test_voice.py::test_supersede_moves_a_banned_voices_takes_and_only_then`
- `test_voice.py::test_job_line_carries_the_temperature`
- `test_voice.py::test_new_take_is_mastered_by_default_and_the_raw_take_is_kept`
- `test_voice.py::test_master_switch_off_keeps_the_old_behaviour`
- `test_voice.py::test_voice_master_gate_runs_on_a_mastered_take`
- `test_voice_breath.py::test_cmd_voice_segments_joins_and_logs`
- `test_voice_breath.py::test_no_breath_flag_keeps_one_utterance`
- `test_voice_breath.py::test_a_crash_keeps_the_finished_lines_and_resume_completes_only_what_is_missing`
- `test_voice_breath.py::test_resume_refuses_a_started_line_with_no_audio`
- `test_voice_breath.py::test_rejoin_rebuilds_every_line_from_the_saved_takes_without_the_model`

## Rules

- No episodes, fonts, voice clips, characters or account tokens in a commit. The repo holds the toolkit only.
- Python runs with `uv`, never pip. On Windows set `PYTHONUTF8=1`.
- One topic per branch, pull request into `main`.
- Deletions go to the recycle bin, never `rm -rf`.

## Commit messages

Imperative and scoped, for example `site: fix the Arabic footer link`.
