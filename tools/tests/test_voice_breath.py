"""Breath segmentation: split after marks, one take per segment, joined by room-tone pauses. Offline: synthetic audio, a fake engine."""
import numpy as np
import pytest

import voice
import sw_fixtures
import voice_edges as VE
from test_voice import RATE, cast_with_refs, ep, make_manifest, write_receipt  # noqa: F401  (ep is a pytest fixture)
from test_voice_edges import band_noise, vowel

COMMA, STOP, QMARK = "،", ".", "؟"


# ------------------------------------------------------------------ segmentation
def test_split_arabic_punctuation_keeps_the_mark_on_the_segment():
    segs = voice.split_breath("أَيْنَ ذَهَبَ؟ وَمَاذَا كَانَ يَحْمِلُ مَعَهُ؟")
    assert [s["text"] for s in segs] == ["أَيْنَ ذَهَبَ؟", "وَمَاذَا كَانَ يَحْمِلُ مَعَهُ؟"]
    assert [s["mark"] for s in segs] == ["strong", "strong"]
    for ch, kind in (("،", "comma"), (",", "comma"), ("؛", "semi"), (":", "semi"), (".", "stop"), ("!", "strong"), ("?", "strong"), ("؟", "strong")):
        s = voice.split_breath(f"أَلِفٌ بَاءٌ{ch} جِيمٌ دَالٌ")
        assert len(s) == 2 and s[0]["text"].endswith(ch) and s[0]["mark"] == kind, ch
    assert voice.split_breath("لَا أَفْتَحُهُ... لَكِنْ حَسَنًا.")[0]["mark"] == "ellipsis"
    assert voice.split_breath("لَا أَفْتَحُهُ… لَكِنْ")[0]["mark"] == "ellipsis"


def test_split_marks_inside_a_token_do_not_break():
    assert len(voice.split_breath("سِعْرُهُ 3.5 دِينَارٍ فَقَطْ")) == 1                 # 3.5
    assert len(voice.split_breath("أَلْفٌ 1,000 قِطْعَةٍ")) == 1                        # 1,000
    s = voice.split_breath("أَيُّ شَيْءٍ «الشَّيْءِ؟» وَمَاذَا بَعْدُ")
    assert s[0]["text"].endswith("؟»") and s[0]["mark"] == "strong"                    # the closing quote stays on its segment
    assert voice.split_breath("بِلَا عَلَامَةٍ")[0]["mark"] is None


def test_pause_lengths_table_and_plan():
    assert voice.BREATH_PAUSE_S == {"comma": 0.22, "semi": 0.30, "stop": 0.40, "ellipsis": 0.40, "strong": 0.45}
    plan = voice.breath_plan("هَلْ سَمِعْتَ الرِّيحَ عِنْدَ الْبَابِ؟ سَمِعْتُهَا يَا صَدِيقِي، وَهِيَ تَهُزُّ النَّافِذَةَ.")
    assert [s["mark"] for s in plan] == ["strong", "comma", "stop"]
    assert [s["pause_s"] for s in plan] == [0.45, 0.22, 0.0]                           # the last segment has nothing after it
    assert voice.pause_kind("؟!") == "strong" and voice.pause_kind("،") == "comma"


def test_short_segments_rule():
    # a short segment before a comma joins the next one (one utterance, comma kept inside)
    p = voice.breath_plan("نَعَمْ، سَمِعْتُ الرِّيحَ عِنْدَ الْبَابِ. مَنْ هُنَاكَ؟")
    assert [s["text"] for s in p] == ["نَعَمْ، سَمِعْتُ الرِّيحَ عِنْدَ الْبَابِ.", "مَنْ هُنَاكَ؟"]
    # a short sentence (. ? !) stands alone, so it gets its breath and its sentence-initial start
    p = voice.breath_plan("عَادَ بِسَلَامٍ. وَحَقِيبَتُهُ؟ لَا أَعْرِفُ.")
    assert [s["text"] for s in p] == ["عَادَ بِسَلَامٍ.", "وَحَقِيبَتُهُ؟", "لَا أَعْرِفُ."] and p[0]["pause_s"] == 0.40 and p[1]["pause_s"] == 0.45
    # a short last segment after a comma joins the one before it
    p = voice.breath_plan("ذَهَبَ الرَّجُلُ إِلَى السُّوقِ، فَعَادَ.")
    assert len(p) == 1 and p[0]["text"].endswith("فَعَادَ.")
    # a line with no mark is a single segment
    assert len(voice.breath_plan("بِلَا عَلَامَةٍ فِي النَّصِّ")) == 1


# ------------------------------------------------------------------ the join
def seg_take(seconds, seed):
    """A fake segment take: 0.15 s noise-floor lead, voiced speech, 0.2 s floor tail (what the model returns)."""
    return np.concatenate([band_noise(0.15, 20, 3000, 1e-4, seed), vowel(seconds), band_noise(0.2, 20, 3000, 1e-4, seed + 1)])


def room_tone_ref():
    return np.concatenate([band_noise(0.4, 20, 3000, 3e-4, 5), vowel(1.5), band_noise(0.5, 20, 3000, 3e-4, 6)])


def test_room_tone_is_the_quietest_stretch_and_never_digital_zero():
    ref = room_tone_ref()
    tone = voice.room_tone_window(ref, RATE)
    assert tone is not None and 1e-5 < np.sqrt(np.mean(tone ** 2)) < 1e-3
    spliced = np.concatenate([np.zeros(RATE), vowel(1.0), np.zeros(RATE)])               # a gated/denoised reference: only digital zeros are quiet
    assert voice.room_tone_window(spliced, RATE) is None
    y, rec = voice.join_segments([seg_take(0.6, 1), seg_take(0.6, 3)], RATE, [0.45], None)
    assert rec["room_tone"].startswith("fallback") and voice.max_zero_run_s(y, RATE) < voice.BREATH_MAX_ZERO_RUN_S


@pytest.mark.parametrize("kind", ["comma", "semi", "stop", "strong"])
def test_join_pause_length_and_no_digital_silence(kind):
    pause = voice.BREATH_PAUSE_S[kind]
    tone = voice.room_tone_window(room_tone_ref(), RATE)
    parts = [seg_take(0.7, 1), seg_take(0.5, 3), seg_take(0.6, 5)]
    y, rec = voice.join_segments(parts, RATE, [pause, pause], tone)
    assert len(rec["joins"]) == 2
    for j in rec["joins"]:
        assert abs(j["measured_s"] - pause) < 0.003, j                                    # designed == measured speech-to-speech gap
    # measured on the joined audio itself: the speech spans of the whole take are separated by that pause
    sp = [VE.speech_span(p, RATE) for p in parts]
    assert all(s["span_s"] > 0.4 for s in sp)
    assert voice.max_zero_run_s(y, RATE) < voice.BREATH_MAX_ZERO_RUN_S                                          # no digital-zero gap anywhere
    # the pause holds the voice's own floor: no 50 ms stretch of the whole take is digital silence, and the floor sits far under the speech
    w = int(0.05 * RATE)
    rms = np.array([np.sqrt(np.mean(y[i:i + w] ** 2)) for i in range(0, len(y) - w, w // 2)])
    assert rms.min() > 1e-5 and rms.min() < 2e-3 and np.sqrt(np.mean(vowel(0.5) ** 2)) > 20 * rms.min()


def test_a_take_that_ends_on_the_last_sound_still_ends_in_room_tone():
    tone = voice.room_tone_window(room_tone_ref(), RATE)
    abrupt = [np.concatenate([band_noise(0.15, 20, 3000, 1e-4, 1), vowel(0.6)]), np.concatenate([band_noise(0.15, 20, 3000, 1e-4, 3), vowel(0.6)])]   # the model stopped on the last sound
    y, _ = voice.join_segments(abrupt, RATE, [0.4], tone)
    assert np.sqrt(np.mean(y[-int(0.1 * RATE):] ** 2)) < 2e-3 and abs(y[-1]) < 2e-3                     # the last 100 ms is the floor
    assert voice.max_zero_run_s(y, RATE) < voice.BREATH_MAX_ZERO_RUN_S
    assert voice.tail_problems(list(np.round(y * 32767) / 32768), RATE, {"edge_db_rel": -30.0}) == []


def test_inhale_is_off_by_default_and_found_only_when_clean():
    assert voice.BREATH_INHALE is False
    assert voice.find_inhale(vowel(2.0), RATE) is None                                   # speech only: no breath to cut
    ref = np.concatenate([band_noise(0.3, 20, 3000, 1e-4, 2), vowel(0.8), band_noise(0.3, 20, 3000, 1e-4, 3),
                          band_noise(0.3, 100, 8000, 3e-3, 4), band_noise(0.3, 20, 3000, 1e-4, 6), vowel(0.8)])
    inh = voice.find_inhale(ref, RATE)
    assert inh is not None and 0.18 <= len(inh) / RATE <= 0.6 and np.max(np.abs(inh)) < 10 ** (-37 / 20)


# ------------------------------------------------------------------ the stage, through cmd_voice
def breath_engine(job):
    for ln in job["lines"]:
        for k, s in enumerate(ln.get("segments") or [{"out": ln["out"]}]):
            voice.write_wav16(s["out"], list(seg_take(0.5 + 0.1 * k, 10 + k)), RATE)
    voice.write_json(job["result"], {"lines": [{"id": ln["id"], "gen_s": 0.1} for ln in job["lines"]]})


@sw_fixtures.needs_project("voice casting (bible/series/<series>/voices/casting.json), its reference clips and your nj-writer voice registry", "bible/series/series/voices/casting.json")
def test_cmd_voice_segments_joins_and_logs(ep):
    paths, root = ep
    s = voice.read_json(paths["script"])
    s["lines"][0]["tts_text"] = "هَلْ سَمِعْتَ الرِّيحَ عِنْدَ الْبَابِ؟ سَمِعْتُهَا يَا صَدِيقِي، وَهِيَ تَهُزُّ النَّافِذَةَ."
    voice.write_json(paths["script"], s)
    cast_with_refs(root)
    make_manifest(paths)
    write_receipt(paths)
    seen = []
    assert voice.cmd_voice(paths, go=True, repo=root, synth=lambda job: (seen.extend(job["lines"]), breath_engine(job))) == 0
    l01 = next(j for j in seen if j["id"] == "l01")
    assert [x["mark"] for x in l01["segments"]] == ["strong", "comma", "stop"] and not [j for j in seen if j["id"] == "l02"][0].get("segments")
    att = voice.attempts(paths["work"])["l01"]
    assert att["status"] == "ok" and att["breath"]["on"] and len(att["breath"]["segments"]) == 3
    assert [j["measured_s"] for j in att["breath"]["join"]["joins"]] == pytest.approx([0.45, 0.22], abs=0.01)
    assert att["breath"]["join"]["pause_zero_run_s"] < voice.BREATH_MAX_ZERO_RUN_S and att["breath"]["inhale"] is False
    assert att["trim"]["clipped_end"] is False and voice.tail_problems(voice.read_float(paths["work"] / "l01.trimmed.wav")[0], RATE, att["trim"]) == []
    # the joined raw take is a normal wav, and trim / measure / visemes work on it
    raw, trimmed = paths["work"] / "l01.wav", paths["work"] / "l01.trimmed.wav"
    assert raw.exists() and trimmed.exists() and voice.wav_seconds(raw) > 2.5
    assert "l01" in voice.measure_manifest(paths, paths["work"])
    x, r = voice.read_float(trimmed)
    inner = np.asarray(x[int(0.5 * r):-int(0.5 * r)])
    assert voice.max_zero_run_s(inner, r) < 0.002                                        # no digital-zero gap between the words
    pcm, r2 = voice.read_wav(trimmed)
    segs, _ = voice.voiced_segments(pcm, r2)
    assert len(segs) >= 3                                                                # the pauses are seen as gaps by the viseme stage


@sw_fixtures.needs_project("voice casting (bible/series/<series>/voices/casting.json), its reference clips and your nj-writer voice registry", "bible/series/series/voices/casting.json")
def test_no_breath_flag_keeps_one_utterance(ep):
    paths, root = ep
    s = voice.read_json(paths["script"])
    s["lines"][0]["tts_text"] = "أَيْنَ ذَهَبَ؟ وَمَاذَا كَانَ يَحْمِلُ مَعَهُ؟"
    voice.write_json(paths["script"], s)
    cast_with_refs(root)
    make_manifest(paths)
    write_receipt(paths)
    seen = []
    voice.cmd_voice(paths, go=True, repo=root, breath=False, synth=lambda job: (seen.extend(job["lines"]), breath_engine(job)))
    assert not any(j.get("segments") for j in seen)
    assert "breath" not in voice.attempts(paths["work"])["l01"]


# ------------------------------------------------------------------ a worker crash (CUDA illegal memory access partway through an episode)
def _two_segment_ep(ep):
    paths, root = ep
    s = voice.read_json(paths["script"])
    for ln in s["lines"]:
        ln["tts_text"] = "هَلْ سَمِعْتَ الرِّيحَ عِنْدَ الْبَابِ؟ سَمِعْتُهَا يَا صَدِيقِي، وَهِيَ تَهُزُّ النَّافِذَةَ."
    voice.write_json(paths["script"], s)
    cast_with_refs(root)
    make_manifest(paths)
    write_receipt(paths)
    return paths, root


@sw_fixtures.needs_project("voice casting (bible/series/<series>/voices/casting.json), its reference clips and your nj-writer voice registry", "bible/series/series/voices/casting.json")
def test_a_crash_keeps_the_finished_lines_and_resume_completes_only_what_is_missing(ep):
    paths, root = _two_segment_ep(ep)

    def dies_in_line_two(job):
        ln1, ln2 = job["lines"][0], job["lines"][1]
        for s in ln1["segments"]:
            voice.write_wav16(s["out"], list(seg_take(0.5, 10)), RATE)
        voice.write_json(job["result"], {"lines": [{"id": ln1["id"], "gen_s": 0.1}]})      # line 1 is finished and recorded
        voice.mark(job["marks"], {"event": "loaded"})
        voice.mark(job["marks"], {"event": "generating", "id": ln2["id"]})
        voice.write_wav16(ln2["segments"][0]["out"], list(seg_take(0.5, 20)), RATE)         # line 2: first segment saved, then the GPU dies
        raise RuntimeError("CUDA error: an illegal memory access was encountered")

    with pytest.raises(voice.Fail) as e:
        voice.cmd_voice(paths, go=True, repo=root, synth=dies_in_line_two)
    assert "illegal memory access" in str(e.value)
    assert voice.line_state(paths["work"], "l01") == "taken" and (paths["work"] / "l01.trimmed.wav").exists()      # finished before the crash: kept, trimmed, logged
    assert voice.attempts(paths["work"])["l01"]["status"] == "ok"
    assert voice.line_state(paths["work"], "l02") == "blocked-after-start"
    with pytest.raises(voice.Fail) as e:                                                    # without --resume a started line stays blocked
        voice.cmd_voice(paths, go=True, repo=root, synth=breath_engine)
    assert e.value.cid == "VOICE-ONCE"
    seg0 = paths["work"] / "l02.seg00.wav"
    before = seg0.read_bytes()
    seen = []

    def finishes(job):
        seen.extend(job["lines"])
        for ln in job["lines"]:
            for s in ln["segments"]:
                if not s.get("reuse"):
                    voice.write_wav16(s["out"], list(seg_take(0.5, 30)), RATE)
        voice.write_json(job["result"], {"lines": [{"id": ln["id"], "gen_s": 0.1} for ln in job["lines"]]})

    assert voice.cmd_voice(paths, go=True, repo=root, synth=finishes, resume=True) == 0
    assert [j["id"] for j in seen] == ["l02"] and [s.get("reuse") for s in seen[0]["segments"]] == [True, False, False]   # l01 is not touched; l02 reuses its saved segment
    assert seg0.read_bytes() == before                                                       # the saved take was never regenerated
    att = voice.attempts(paths["work"])["l02"]
    assert att["status"] == "ok" and att["resumed"]["reused_segments"] == [0] and (paths["work"] / "l02.trimmed.wav").exists()


@sw_fixtures.needs_project("voice casting (bible/series/<series>/voices/casting.json), its reference clips and your nj-writer voice registry", "bible/series/series/voices/casting.json")
def test_resume_refuses_a_started_line_with_no_audio(ep):
    paths, root = _two_segment_ep(ep)

    def dies_at_once(job):
        voice.mark(job["marks"], {"event": "loaded"})
        voice.mark(job["marks"], {"event": "generating", "id": job["lines"][0]["id"]})
        raise RuntimeError("CUDA out of memory")

    with pytest.raises(voice.Fail):
        voice.cmd_voice(paths, go=True, repo=root, synth=dies_at_once)
    with pytest.raises(voice.Fail) as e:
        voice.cmd_voice(paths, go=True, repo=root, synth=breath_engine, resume=True)
    assert e.value.cid == "VOICE-ONCE" and "left no audio" in str(e.value)


@sw_fixtures.needs_project("voice casting (bible/series/<series>/voices/casting.json), its reference clips and your nj-writer voice registry", "bible/series/series/voices/casting.json")
def test_rejoin_rebuilds_every_line_from_the_saved_takes_without_the_model(ep):
    paths, root = _two_segment_ep(ep)
    assert voice.cmd_voice(paths, go=True, repo=root, synth=breath_engine) == 0
    segs = sorted(p.name for p in paths["work"].glob("*.seg*.wav"))
    before = {n: (paths["work"] / n).read_bytes() for n in segs}

    def no_model(job):
        pytest.fail("rejoin must not voice anything")

    assert voice.cmd_voice(paths, go=True, repo=root, synth=no_model, rejoin=True) == 0
    assert {n: (paths["work"] / n).read_bytes() for n in segs} == before                    # the takes are untouched
    att = voice.attempts(paths["work"])["l01"]
    assert att["status"] == "ok" and att["resumed"]["rejoin"] is True and len(att["breath"]["segments"]) == 3


def test_edge_noise_gate_reads_a_quiet_segment_after_a_long_pause_as_speech():
    """A long episode line: the second sentence is quieter than the shouted first one; after a 0.45 s pause the detector (run gap 0.4 s) read it as a stray run and
    reported a 1 s noise-only tail. The gate now widens the gap by the take's longest pause, as the cleaner does."""
    tone = voice.room_tone_window(room_tone_ref(), RATE)
    loud = np.concatenate([band_noise(0.15, 20, 3000, 1e-4, 1), vowel(1.2, amp=0.5), band_noise(0.2, 20, 3000, 1e-4, 2)])
    quiet = np.concatenate([band_noise(0.15, 20, 3000, 1e-4, 3), vowel(1.2, amp=0.05), band_noise(0.2, 20, 3000, 1e-4, 4)])
    y, _ = voice.join_segments([loud, quiet], RATE, [0.45], tone)
    assert voice.edge_noise_problems(list(y), RATE, 0.45) == []
    assert voice.edge_noise_problems(list(y), RATE) != []                                    # the plain detector does misread it
