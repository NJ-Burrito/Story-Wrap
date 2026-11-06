"""The video side of research/algo/DESIGN.md (the owner approved section 9, 2026-10-25): the spoken recap hook (PLAN-HOOK, CALM-HOOK-3S), the story-so-far clause (PLAN-SOFAR), the series strip and the
recap tag (CALM-HUD), the open-question prompt (PLAN-PROMPT, PLAN-VARIANTS), the follow line, the cover card, and the small NJ mark on every frame (WATERMARK-PRESENT, WATERMARK-CLEAR).
Pure checks on dicts and a short synthetic clip; no GPU needed (compose.venc_args falls back to x264)."""
import copy
import json
import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np
import pytest

import calm_cards as CC
import calm_compose as cc
import sw_fixtures
import watermark as WM
from test_daily import mk_root, plan_ok, script_ok


@pytest.fixture(autouse=True)
def _neutral_project(monkeypatch):
    """Plan checks read the series glossary under calm_compose.ROOT: use the neutral fixture project, not a user's own series."""
    monkeypatch.setattr(cc, "ROOT", sw_fixtures.PROJECT)


@pytest.fixture
def fake_mark(tmp_path, monkeypatch):
    """A synthetic stand-in for the brand picture (assets/brand/mark-source.png is not part of the tool): cream monogram strokes on a dark red ground."""
    from PIL import Image, ImageDraw
    src, out, orig = tmp_path / "mark-source.png", tmp_path / "nj-mark-cream.png", WM.derive_mark
    im = Image.new("RGB", (1000, 1000), (120, 40, 40))
    d = ImageDraw.Draw(im)
    cream = (238, 232, 221)
    d.rectangle([300, 300, 360, 700], fill=cream)
    d.rectangle([640, 300, 700, 700], fill=cream)
    d.polygon([(300, 300), (360, 300), (700, 700), (640, 700)], fill=cream)
    im.save(src)
    monkeypatch.setattr(WM, "SRC", src)
    monkeypatch.setattr(WM, "MARK", out)
    monkeypatch.setattr(WM, "derive_mark", lambda: orig(src, out))


def codes(fails):
    return {f.split(" ", 1)[0] for f in fails}


# ------------------------------------------------------------------ PLAN-HOOK
def test_the_good_e02_plan_passes_every_new_check():
    assert cc.validate_plan(plan_ok(), script_ok()) == []


def test_e01_and_e01c_are_untouched_by_the_new_checks():
    p = plan_ok()
    p["episode"] = "E01C"
    del p["recap"], p["hook"], p["choice"]["variants"]
    s = script_ok()
    s["lines"][0]["text"] = "كلام بلا اسم"                      # no cast name, no hook, no variants: the approved E01C format needs none
    assert cc.validate_plan(p, s) == []
    assert not cc.algo_on(p)
    assert cc.algo_on({"episode": "E02"}) and cc.algo_on({"episode": "R01"})


def test_plan_hook_needs_a_pattern_and_a_line():
    p = plan_ok()
    del p["hook"]
    assert "PLAN-HOOK" in codes(cc.validate_plan(p, script_ok()))
    p = plan_ok()
    p["hook"]["pattern"] = 11
    assert "PLAN-HOOK" in codes(cc.validate_plan(p, script_ok()))
    p = plan_ok()
    p["hook"]["line"] = "Z9"
    assert any("not in script.json" in f for f in cc.validate_plan(p, script_ok()))


def test_plan_hook_is_the_first_spoken_line_and_nowhere_else():
    p = plan_ok()
    p["hook"]["line"] = "L2"                                      # also a scene line
    assert any(f.startswith("PLAN-HOOK") and "also used" in f for f in cc.validate_plan(p, script_ok()))
    s = script_ok()
    s["lines"][-1]["speaker"] = "hero"
    assert any(f.startswith("PLAN-HOOK") and "narrator" in f for f in cc.validate_plan(p | {"hook": {"pattern": 1, "line": "H1"}}, s))


def test_plan_hook_first_plate_is_at_most_8_words_and_not_a_greeting():
    s = script_ok()
    s["lines"][-1]["text"] = "اخترتم أن تنام الحقيبة على الرف الذي بلا رقم في المكتب الليلة"
    assert any(f.startswith("PLAN-HOOK") and "words" in f for f in cc.validate_plan(plan_ok(), s))
    s["lines"][-1]["text"] = "اخترتم أن تنام الحقيبة على الرف. وهدى تنتظر عند الباب وفي يدها بطاقة قديمة"      # the FIRST plate is short: a long second clause is fine
    assert not any(f.startswith("PLAN-HOOK") for f in cc.validate_plan(plan_ok(), s))
    for bad in ("مرحبا بكم في the series", "تابعوا the series", "the series", "أهلا بكم"):
        s["lines"][-1]["text"] = bad
        assert any(f.startswith("PLAN-HOOK") and "greeting" in f for f in cc.validate_plan(plan_ok(), s)), bad


# ------------------------------------------------------------------ PLAN-SOFAR
def test_plan_sofar_the_first_scene_names_a_cast_member():
    s = script_ok()
    s["lines"][0]["text"] = "كلام بلا اسم أحد"
    assert any(f.startswith("PLAN-SOFAR") for f in cc.validate_plan(plan_ok(), s))
    for ok in ("ومنى ما زالت تحمل الحقيبة", "منى تنتظر", "تنتظر لمنى حقيبة"):      # the name with a clitic is still the name
        s["lines"][0]["text"] = ok
        assert not any(f.startswith("PLAN-SOFAR") for f in cc.validate_plan(plan_ok(), s)), ok
    s["lines"][0]["text"] = "ومن منية الليل جاء الريح"                              # a word that merely contains a name's letters is not the name
    assert any(f.startswith("PLAN-SOFAR") for f in cc.validate_plan(plan_ok(), s))


# ------------------------------------------------------------------ PLAN-PROMPT, PLAN-FOLLOW, PLAN-VARIANTS
def test_the_default_prompt_and_the_follow_line_pass_their_own_rules():
    assert CC.COMMENT_PROMPT == "ما رأيكم، ولماذا؟" and CC.FOLLOW_LINE == "الحلقة القادمة تتبع ما تكتبونه"
    assert CC.ask_problems(CC.COMMENT_PROMPT, "x", True) == [] and CC.ask_problems(CC.FOLLOW_LINE, "x", False) == []
    assert CC.ask_problems("أين تضعون الحقيبة الليلة؟ قولوا لنا لماذا.", "x", True) == []         # the DESIGN.md 5.2 spoken line


def test_plan_prompt_refuses_digits_banned_asks_and_statements():
    for bad in ("اكتبوا اختياركم الآن؟", "صوتوا 1 أو 2؟", "علقوا برأيكم؟", "تابعوا لتعرفوا؟"):
        p = plan_ok()
        p["choice"]["prompt"] = bad
        assert "PLAN-PROMPT" in codes(cc.validate_plan(p, script_ok())), bad
    p = plan_ok()
    p["choice"]["prompt"] = "هذا بيان وليس سؤالا"
    assert any("not a question" in f for f in cc.validate_plan(p, script_ok()))
    p = plan_ok()
    p["choice"]["prompt"] = "ما رأيكم، ولماذا؟"
    assert cc.validate_plan(p, script_ok()) == []
    s = script_ok()
    p = plan_ok()
    p["choice"]["lines"] = {"question": "L1", "choice1": "L2", "choice2": "L3", "hook": "L4"}
    s["lines"][3]["text"] = "اكتبوا اختياركم بكلماتكم"
    assert any(f.startswith("PLAN-PROMPT closing line L4") for f in cc.validate_plan(p, s))
    s["lines"][3]["text"] = "أين تضعون الحقيبة الليلة؟ قولوا لنا لماذا."
    assert not any(f.startswith("PLAN-PROMPT") for f in cc.validate_plan(p, s))


def test_plan_follow_line_may_not_beg():
    p = plan_ok()
    p["follow_line"] = "تابعوا لتعرفوا"
    assert "PLAN-FOLLOW" in codes(cc.validate_plan(p, script_ok()))
    p["follow_line"] = "الحلقة القادمة تتبع ما تكتبونه"
    assert cc.validate_plan(p, script_ok()) == []
    assert cc.follow_card_line({}) == CC.FOLLOW_LINE and cc.follow_card_line(p) == p["follow_line"]


def test_plan_variants_needs_eight_distinct_per_side():
    p = plan_ok()
    p["choice"]["variants"]["1"] = p["choice"]["variants"]["1"][:7]
    assert any(f.startswith("PLAN-VARIANTS") and "['1']" in f for f in cc.validate_plan(p, script_ok()))
    p = plan_ok()
    p["choice"]["variants"]["2"] = ["الرف"] * 9                    # nine copies of one wording are one wording
    assert any(f.startswith("PLAN-VARIANTS") and "['2']" in f for f in cc.validate_plan(p, script_ok()))
    p = plan_ok()
    del p["choice"]["variants"]
    assert len([f for f in cc.validate_plan(p, script_ok()) if f.startswith("PLAN-VARIANTS")]) == 2
    p = plan_ok()
    assert not any("variants" in k for k, _ in cc._visible_strings(p))   # never shown, so never glossed or checked as text


# ------------------------------------------------------------------ stage_plan: the spoken recap
def _write_takes(root, ep, h1_s):
    d = root / "work" / "voice" / ep
    d.mkdir(parents=True)
    for lid, sec in [("H1", h1_s)] + [(f"L{i}", 3.0) for i in range(1, 6)]:
        with wave.open(str(d / f"{lid}.trimmed.wav"), "wb") as w:
            w.setnchannels(1), w.setsampwidth(2), w.setframerate(16000)
            w.writeframes(b"\x00\x00" * int(16000 * sec))


def _stage(tmp_path, h1_s):
    root = mk_root(tmp_path)
    ed = root / "bible" / "series" / "series" / "episodes" / "E02"
    (ed / "calm-plan.json").write_text(json.dumps(plan_ok(), ensure_ascii=False), encoding="utf-8")
    (ed / "script.json").write_text(json.dumps(script_ok(), ensure_ascii=False), encoding="utf-8")
    _write_takes(root, "E02", h1_s)
    ep = cc.Ep("E02", root)
    cc.stage_plan(ep)
    return json.loads(ep.timeline_p.read_text(encoding="utf-8"))


def test_the_recap_card_speaks_the_hook_inside_its_cap(tmp_path):
    tl = _stage(tmp_path, 2.0)
    rc = tl["items"][0]
    assert rc["id"] == "recap" and rc["line"] == "H1" and rc["hook_pattern"] == 1
    assert rc["dur"] <= cc.RECAP_MAX_S and rc["voice_t0"] == pytest.approx(cc.VOICE_LEAD_S, abs=1e-6)
    assert rc["tag"] == "الحلقة ٢ · the series" == tl["episode_label"] and tl["strip_s"] == cc.STRIP_S
    assert cc.hook_3s_problems(tl, plan_ok()) == []
    first_voiced = min(ln["voice_t0"] for _, ln in cc._spoken(tl["items"]))
    assert first_voiced == rc["voice_t0"]                          # the recap is the FIRST spoken line


def test_a_recap_line_too_long_for_the_cap_stops_the_plan(tmp_path):
    with pytest.raises(cc.Fail) as e:
        _stage(tmp_path, 2.6)                                       # 2.6 + 0.2 + 0.35 = 3.15 s > 3.0 s
    assert e.value.args[0].startswith("FAIL [PLAN-DURATION]") or "PLAN-DURATION" in str(e.value)


def test_e01_has_no_strip_no_tag_and_no_label(tmp_path):
    root = mk_root(tmp_path, "E01")
    p = plan_ok()
    p["episode"] = "E01"
    del p["recap"], p["hook"]
    ed = root / "bible" / "series" / "series" / "episodes" / "E01"
    (ed / "calm-plan.json").write_text(json.dumps(p, ensure_ascii=False), encoding="utf-8")
    (ed / "script.json").write_text(json.dumps(script_ok(), ensure_ascii=False), encoding="utf-8")
    _write_takes(root, "E01", 2.0)
    ep = cc.Ep("E01", root)
    cc.stage_plan(ep)
    tl = json.loads(ep.timeline_p.read_text(encoding="utf-8"))
    assert "episode_label" not in tl and all("tag" not in i for i in tl["items"] if i["kind"] != "intro")


def test_recap_card_params_carry_the_tag_from_e02_only():
    assert cc.recap_card_params(plan_ok()) == {"line": "اخترتم:", "word": "الرف", "tag": "الحلقة ٢ · the series"}
    p = plan_ok()
    p["episode"] = "E01C"
    assert "tag" not in cc.recap_card_params(p)


# ------------------------------------------------------------------ HUD strip (CALM-HUD) and CALM-HOOK-3S
def _tl(label="الحلقة ٢ · the series", recap_tag="الحلقة ٢ · the series"):
    items = [{"id": "recap", "kind": "card", "t0": 0.0, "t1": 2.75, "line": "H1", "voice_t0": 0.2, "tag": recap_tag},
             {"id": "s1", "kind": "scene", "t0": 2.5, "t1": 9.5, "line": "L1", "voice_t0": 2.95},
             {"id": "s2", "kind": "scene", "t0": 9.25, "t1": 14.0, "line": "L2", "voice_t0": 9.7}]
    return {"items": items, "episode_label": label, "strip_s": 3.0}


def _huds(tl, strip=True):
    a, b = 2.5 + cc.JOIN_S / 2, 9.5 - cc.JOIN_S / 2
    h1 = {"id": "s1", "t0": 2.5, "t1": 9.5, "w": 400, "h": 200}
    hs = [{**h1, "strip": tl["episode_label"], "show0": a, "show1": a + 3.0}, {**h1, "show0": a + 3.0, "show1": b}] if strip else [{**h1}]
    hs.append({"id": "s2", "t0": 9.25, "t1": 14.0, "w": 400, "h": 200})
    return hs


def test_hud_strip_present_and_covering(tmp_path):
    tl = _tl()
    assert cc.hud_problems(tl, _huds(tl), recap_tag=tl["episode_label"]) == []
    assert any("series strip" in f for f in cc.hud_problems(tl, _huds(tl, strip=False), recap_tag=tl["episode_label"]))


def test_hud_strip_gap_and_recap_tag_are_caught():
    tl = _tl()
    hs = _huds(tl)
    hs[1]["show0"] += 0.5                                           # a gap between the strip plate and the plate that takes over
    assert any("no HUD plate" in f for f in cc.hud_problems(tl, hs, recap_tag=tl["episode_label"]))
    assert any("recap card shot carries tag" in f for f in cc.hud_problems(tl, _huds(tl), recap_tag=None))
    bad = _tl(recap_tag="")
    assert any("recap card's tag" in f for f in cc.hud_problems(bad, _huds(bad), recap_tag=bad["episode_label"]))


def test_hud_strip_is_not_asked_of_an_episode_without_a_label():
    tl = _tl(label=None, recap_tag=None)
    tl.pop("episode_label")
    assert cc.hud_problems(tl, _huds({"episode_label": "x"}, strip=False)[:1] + [{"id": "s2", "t0": 9.25, "t1": 14.0, "w": 1, "h": 1}], None) == []


def test_hud_plate_html_has_the_strip_row_only_on_the_strip_plate():
    html = cc.plate_html([], [{"day": "اليوم ٢", "clock": "٩:٠٤ م", "place": "المكتب", "strip": "الحلقة ٢ · the series"}, {"day": "اليوم ٢", "clock": "٩:٠٤ م", "place": "المكتب"}])
    assert html.count('class="strip"') == 1 and "الحلقة ٢ · the series" in html and "thmanyahsans" in html and "Cairo" not in html


def test_hook_3s_voiced_line_or_declared_event():
    tl = _tl()
    assert cc.hook_3s_problems(tl, plan_ok()) == []
    late = {"items": [{"id": "s1", "kind": "scene", "t0": 0.0, "t1": 8.0, "line": "L1", "voice_t0": 3.4}]}
    assert cc.hook_3s_problems(late, {"scenes": []})               # nothing starts before 3 s
    assert cc.hook_3s_problems(late, {"scenes": [{"id": "s1", "foley": [{"at": 0.53, "sound": "thud"}]}]}) == []     # E01C's bag lands at 0.53 s: a declared story event
    assert cc.hook_3s_problems({"items": []}, {})


# ------------------------------------------------------------------ cards: recap tag, cover
def test_recap_card_takes_a_tag_and_keeps_two_idea_blocks_otherwise():
    c = CC.resolve("recap_card", {"line": "اخترتم:", "word": "الرف", "tag": "الحلقة ٢ · the series"})
    html = CC.card_html({**c["card"], "backdrop_png": None})
    assert html.index("الحلقة ٢") < html.index("اخترتم") and "thmanyahsans" in html
    box = lambda t: {"text": t, "x0": 100, "y0": 400, "x1": 900, "y1": 500, "font_px": 78, "family": "thmanyahsans", "color": "rgb(243, 237, 228)"}
    meas = {"fonts_ok": True, "boxes": [box("a"), box("b"), box("c")]}
    assert CC.check_card(c["card"], meas) == []                     # a tag earns one more block
    plain = CC.resolve("recap_card", {"line": "اخترتم:", "word": "الرف"})
    assert any(f.startswith("CARD-ONE-IDEA") for f in CC.check_card(plain["card"], meas))          # the limit of a card without a tag is unchanged
    with pytest.raises(Exception):
        CC.resolve("recap_card", {"line": "اخترتم:", "word": "الرف", "tag": "الحلقة ٢ · the series الرَّف"})   # tashkeel in the tag


def test_cover_card_numeral_series_and_central_square():
    c = CC.resolve("cover_card", {"series": "the series", "day": 2})
    assert c["card"]["text"]["numeral"] == "٢"
    html = CC.card_html({**c["card"], "backdrop_png": None, "object_png": None})
    assert "٢" in html and "the series" in html and "border" not in html.split("<style>")[1].split("</style>")[0].split(".numeral")[1]
    ok = {"fonts_ok": True, "boxes": [{"text": "٢", "x0": 300, "y0": 600, "x1": 780, "y1": 1100, "font_px": 520, "family": "thmanyahserifdisplay", "color": "rgb(19, 17, 14)"},
                                      {"text": "the series", "x0": 200, "y0": 1100, "x1": 880, "y1": 1210, "font_px": 84, "family": "thmanyahsans", "color": "rgb(19, 17, 14)"}]}
    assert CC.check_card(c["card"], ok) == []
    low = copy.deepcopy(ok)
    low["boxes"][0].update(y0=300, y1=800)                          # above the grid's central square
    assert any(f.startswith("COVER-SQUARE") for f in CC.check_card(c["card"], low))
    for bad in ("الرَّف", ""):
        with pytest.raises(Exception):
            CC.resolve("cover_card", {"series": bad or "x", "day": "" if not bad else 1})


# ------------------------------------------------------------------ the NJ mark
def test_the_mark_is_small_cream_on_transparent_and_derived_from_the_profile_picture(fake_mark):
    from PIL import Image
    im = Image.open(WM.ensure_mark())
    a = np.asarray(im)
    assert im.size == (WM.MARK_PX, WM.MARK_PX) and a[..., 3].max() == 255 and a[..., 3].min() == 0
    assert tuple(int(v) for v in a[a[..., 3] > 200][:, :3].mean(axis=0)) == pytest.approx(WM.CREAM, abs=2)       # cream, not the picture's dark red
    assert (a[..., 3] > 0).mean() < 0.7                              # a monogram, not a filled square
    assert WM.SRC.is_file()


def test_the_mark_rect_is_top_right_inside_the_safe_area_and_outside_every_ui_zone():
    r = WM.rect()
    assert r["x"] + r["w"] <= WM.SAFE[2] and r["y"] >= WM.SAFE[1] and max(r["w"], r["h"]) <= WM.MARK_MAX_PX
    assert r["x"] > 1080 / 2 and r["y"] < 1920 / 2                  # top-right
    assert WM.OPACITY_RANGE[0] <= WM.OPACITY <= WM.OPACITY_RANGE[1]
    assert WM.clear_problems(None, [], [], [], []) == []
    hud = {"x": cc.HUD_XY[0], "y": cc.HUD_XY[1], "w": 450, "h": 220}   # the HUD sits top-left
    plate = {"x": 90, "y": 1010, "w": 900, "h": 150}                   # a caption plate in the lower third
    assert WM.clear_problems(None, [plate], [hud], [], []) == []


def test_clear_problems_names_an_overlap_with_each_kind_of_box_and_each_ui_zone():
    r = WM.rect()
    on = {"x": r["x"] - 20, "y": r["y"] + 10, "w": 80, "h": 40, "what": "x"}
    for kind in range(4):
        args = [[], [], [], []]
        args[kind] = [on]
        assert WM.clear_problems(None, *args), kind
    near = {"x": r["x"] - 100 - WM.PAD_PX + 2, "y": r["y"], "w": 100, "h": 100}      # inside the 12 px clear space
    assert WM.clear_problems(None, [near], [], [], [])
    assert not WM.clear_problems(None, [{**near, "x": near["x"] - 6}], [], [], [])
    assert any("UI zone" in f for f in WM.clear_problems({"x": 926, "y": 1000, "w": 96, "h": 96}, [], [], [], []))      # the right-side button rail
    assert any("UI zone" in f for f in WM.clear_problems({"x": 926, "y": 100, "w": 96, "h": 96}, [], [], [], []))       # the app's top bar
    assert any("small mark" in f for f in WM.clear_problems({"x": 800, "y": 300, "w": 200, "h": 200}, [], [], [], []))


def _frame(with_mark: bool):
    rng = np.random.default_rng(3)
    g = np.full((1920, 1080), 70.0)
    g += rng.normal(0, 3, g.shape)
    g[:, 540:] += 25                                                 # an edge in the ground
    if with_mark:
        a = WM._alpha() * WM.OPACITY
        x, y = WM.MARK_XY
        g[y:y + WM.MARK_PX, x:x + WM.MARK_PX] = g[y:y + WM.MARK_PX, x:x + WM.MARK_PX] * (1 - a) + 238 * a
    return np.clip(g, 0, 255).astype(np.uint8)


def test_the_presence_correlation_separates_a_marked_frame_from_a_clean_one(fake_mark):
    assert WM.corner_ncc(_frame(True)) > 0.7
    assert abs(WM.corner_ncc(_frame(False))) < 0.2
    assert WM.NCC_MIN > 0.2 > 0 and WM.NCC_MIN < 0.7


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg is needed to encode the synthetic clip")
def test_apply_puts_the_mark_on_every_frame_and_changes_nothing_else(tmp_path, fake_mark):
    src, dst = tmp_path / "in.mp4", tmp_path / "out.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x302820:s=1080x1920:r=24:d=2.0", "-f", "lavfi", "-i", "sine=frequency=440:duration=2.0:sample_rate=48000",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "12", "-c:a", "aac", "-b:a", "128k", "-shortest", str(src)], check=True)
    res = WM.apply(src, dst, tmp_path)
    assert res["spec"]["corner"] == "top-right" and (tmp_path / "watermark.json").is_file()
    probe = lambda p: json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,width,height,r_frame_rate:format=duration", "-of", "json", str(p)], capture_output=True, text=True).stdout)
    a, b = probe(src), probe(dst)
    assert [(s["codec_name"], s.get("width"), s.get("r_frame_rate")) for s in a["streams"]] == [(s["codec_name"], s.get("width"), s.get("r_frame_rate")) for s in b["streams"]]
    assert abs(float(a["format"]["duration"]) - float(b["format"]["duration"])) < 0.1
    md5 = lambda p: subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-map", "0:a", "-c", "copy", "-f", "md5", "-"], capture_output=True, text=True).stdout
    assert md5(src) == md5(dst)                                      # the audio stream is copied bit for bit
    before = WM.measure_present(src, 2.0)
    after = WM.measure_present(dst, 2.0)
    assert before["share_present"] == 0.0 and after["share_present"] >= WM.PRESENT_SHARE_MIN
    f, m = WM.present_problems(dst, 2.0, tmp_path / "watermark.json")
    assert f == [] and m["share_present"] >= WM.PRESENT_SHARE_MIN
    f2, _ = WM.present_problems(src, 2.0, None)
    assert any("watermark.json is missing" in x for x in f2) and any("shows on" in x for x in f2)
    side = tmp_path / "watermark.json"
    side.write_text(json.dumps({**WM.spec(), "rect": {"x": 0, "y": 0, "w": 96, "h": 96}}), encoding="utf-8")
    assert any("policy rect" in x for x in WM.present_problems(dst, 2.0, side)[0])
    side.write_text(json.dumps({**WM.spec(), "opacity": 0.9}), encoding="utf-8")
    assert any("faint band" in x for x in WM.present_problems(dst, 2.0, side)[0])


def test_assemble_lays_the_mark_in_its_last_step():
    src = Path(cc.__file__).read_text(encoding="utf-8")
    i = src.index("def stage_assemble")
    body = src[i:src.index("def stage_cover")]
    assert "WM.filter_chain(acc, idx" in body and body.index("WM.filter_chain") > body.index("lit_plates") and body.index("WM.filter_chain") < body.index('"-i", ep.mix')
    assert "WM.write_sidecar(ep.work)" in body
    g = src[src.index("def stage_gate"):]
    assert "WATERMARK-PRESENT" in g and "WATERMARK-CLEAR" in g and "CALM-HOOK-3S" in g and "CALM-FOLLOW-LINE" in g and "CALM-COVER" in g


# ------------------------------------------------------------------ daily.py's real card-building path (s_shots)
def _cards_through_daily(tmp_path, monkeypatch, episode):
    import types
    import calm
    import daily
    root = mk_root(tmp_path, episode)
    p = plan_ok()
    p["episode"] = episode
    s = script_ok()
    if episode != "E02":
        del p["recap"], p["hook"]
    ed = root / "bible" / "series" / "series" / "episodes" / episode
    (ed / "calm-plan.json").write_text(json.dumps(p, ensure_ascii=False), encoding="utf-8")
    (ed / "script.json").write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")
    _write_takes(root, episode, 2.0)
    cc.stage_plan(cc.Ep(episode, root))
    orig, built = calm.resolve, {}

    def fake_resolve(tpl, prm):
        if tpl in calm.CARD_TEMPLATES and tpl != "intro_freeze":
            c = orig(tpl, prm)
            built[tpl] = c["card"]["text"]
            return c
        return {"actors": [], "template": tpl}
    monkeypatch.setattr(calm, "resolve", fake_resolve)
    import calm_intro
    monkeypatch.setattr(calm_intro, "default_params", lambda *a, **k: {})
    monkeypatch.setattr(calm, "validate_calm", lambda c: [])
    monkeypatch.setattr(calm, "write_shot", lambda c, sd: None)
    monkeypatch.setattr(calm, "set_lipsync", lambda *a, **k: None)
    monkeypatch.setattr(calm, "lipsync_entry", lambda *a, **k: {})
    ctx = types.SimpleNamespace(ep=episode, root=root, sh=lambda *a, **k: types.SimpleNamespace(returncode=0, stdout="", stderr=""))
    daily.s_shots(ctx)
    return built


def test_e02_cards_carry_the_tag_the_new_follow_line_and_the_new_prompt(tmp_path, monkeypatch):
    built = _cards_through_daily(tmp_path, monkeypatch, "E02")
    assert built["recap_card"]["tag"] == "الحلقة ٢ · the series"
    assert built["follow_card"]["line"] == "الحلقة القادمة تتبع ما تكتبونه"
    assert built["choice_card"]["prompt"] == "ما رأيكم، ولماذا؟"
    html = CC.card_html({"template": "choice_card", "text": built["choice_card"], "accent": "#fff", "backdrop_png": None})
    assert "ما رأيكم، ولماذا؟" in html


def test_e01c_cards_are_unchanged_by_the_new_wiring(tmp_path, monkeypatch):
    built = _cards_through_daily(tmp_path, monkeypatch, "E01C")
    assert "recap_card" not in built
    assert built["follow_card"]["line"] == "تابع لتعرف ماذا حدث"
    assert built["choice_card"]["prompt"] == CC.COMMENT_PROMPT_LEGACY


def test_a_statement_with_a_question_word_inside_is_not_a_question():
    assert CC.ask_problems("هذا ما حدث ليلا", "x", True)
    assert CC.ask_problems("من الرف نبدأ", "x", True) == []          # a leading interrogative (or «؟») makes it a question
    assert CC.ask_problems("وماذا بعد", "x", True) == []


def test_watermark_clear_fails_on_a_missing_card_measure_and_scales_by_the_push(tmp_path):
    root = tmp_path
    ep = cc.Ep.__new__(cc.Ep)
    ep.root = root
    tl = {"items": [{"id": "day", "kind": "card", "shot": "E9-day"}]}
    boxes, missing = cc.card_text_boxes(ep, tl)
    assert boxes == [] and missing and "card-measure.json is missing" in missing[0]
    out = root / "work" / "shots" / "E9-day" / "out"
    out.mkdir(parents=True)
    (out / "card-measure.json").write_text(json.dumps({"boxes": [{"text": "x", "x0": 900, "y0": 300, "x1": 1000, "y1": 400}]}), encoding="utf-8")
    boxes, missing = cc.card_text_boxes(ep, tl)
    assert missing == [] and boxes[0]["x"] + boxes[0]["w"] == pytest.approx(540 + 460 * 1.04) and boxes[0]["x"] < 900 + 1e-9 + 20


def test_apply_refuses_to_overwrite_its_source_or_an_approved_master(tmp_path):
    f = tmp_path / "ep.mp4"
    f.write_bytes(b"x")
    with pytest.raises(ValueError):
        WM.apply(f, f)
    with pytest.raises(ValueError):
        WM.apply(f, tmp_path / "episode.approved-v5.mp4")
    assert f.read_bytes() == b"x" and not hasattr(WM, "CONTROL_NCC_MAX")


def test_hud_day_follows_the_scene_own_day_then_the_episode_day():
    """E04 Q06: night one is day three, the night after the day card is day four."""
    tl = {"day": "٤"}
    assert cc.hud_day({"id": "s1", "day": "٣"}, tl) == "اليوم ٣"
    assert cc.hud_day({"id": "s7"}, tl) == "اليوم ٤"
    assert cc.hud_day({"id": "s7", "day": "3"}, tl) == "اليوم ٣"


def test_last_plate_of_a_line_ends_at_its_scene_join_when_it_has_been_readable():
    """E04 Q04/Q05: no plate stays up over the next scene's picture."""
    st = [{"line": "L14", "start": 84.6, "end": 93.0, "words": ["إنها", "تتأخر", "ثانيتين"], "text": "إنها تتأخر ثانيتين"}]
    cc.cap_plate_ends(st, {"L14": 91.83})
    assert st[0]["end"] == 91.83
    short = [{"line": "L2", "start": 9.9, "end": 12.0, "words": ["كلمة", "طويلة", "جدا", "في", "الجملة"], "text": "كلمة طويلة جدا في الجملة"}]
    cc.cap_plate_ends(short, {"L2": 10.0})      # only 0.1 s of reading time left before the join: the plate keeps its time
    assert short[0]["end"] == 12.0


def test_last_state_of_a_long_unit_is_capped_by_the_unit_start_not_the_state_start():
    """E04 round 3: the highlight's last state starts 1.0 s before the join, but its plate has been up 2.3 s: it ends at the join (the real L14 numbers)."""
    base = {"line": "L14", "unit": 2, "words": ["إنها", "تتأخر", "ثانيتين"], "text": "إنها تتأخر ثانيتين"}
    st = [{**base, "start": 89.528, "end": 90.088}, {**base, "start": 90.088, "end": 90.818}, {**base, "start": 90.818, "end": 92.128}]
    cc.cap_plate_ends(st, {"L14": 91.7084})
    assert st[-1]["end"] == pytest.approx(91.7084, abs=1e-3) and st[0]["end"] == 90.088      # cap_plate_ends rounds to the millisecond
