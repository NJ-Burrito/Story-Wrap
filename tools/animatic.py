# /// script
# requires-python = ">=3.11"
# dependencies = ["playwright", "pillow", "numpy", "scipy"]
# ///
"""The animatic: a cheap, early preview of the whole episode (owner, 2026-10-25: "add safe fixing, measurement and testing stages between steps so we don't redo the work").

It runs after the plan and BEFORE any shot is rendered. It has the real voice (the takes), the real timeline, the real captions (every sentence, its highlight windows, its gloss)
and the real mix, and a low-resolution picture: flat colour blocks per item, a box where each caption plate will be, a bar where the narrator speaks. No character is drawn, so it
costs seconds, not the minutes of a shot. Every fault that does not need a drawn pixel is found here, and the shots (the expensive part) start only when this passes:

  captions    one plate at a time, whole sentences, every plate up long enough to read (CAP-FULL-SENTENCE, CAP-READ-TIME, CAP-READING-SPEED), the glossary (CAP-FOREIGN-GLOSS),
              Arabic joining (text only), safe width, no tashkeel, every spoken line has a plate, every plate sits inside the item that speaks it
  timing      the voice fits its scene, nothing speaks over anything, the voice covers the runtime (CALM-VOICE-COVERAGE) and the narrator is a quarter of it at most (NARRATOR-SHARE), the length (CALM-LENGTH), the declared calm data (qg_checks)
  audio       the phone-first mix is rendered ONCE here (compose reuses it): loudness and true peak in band, the three audio checks, the sound cues of every join, no silent gap

  uv run tools/animatic.py build <ep>      writes work/episodes/<ep>/animatic/{animatic.mp4, report.json}, mix.wav, sfx.json, audio/stems; exit 0, or 1 when a check failed (report lists it)

Nothing here is a gate by itself: report.json feeds the VERIFY of the `animatic` stage in tools/stagegate.py. No model, no network, one Chrome page for the word widths.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import calm_compose as cc  # noqa: E402
import gloss as G  # noqa: E402
import cap_sentence as CS  # noqa: E402
from arabic_display import display_text, has_tashkeel  # noqa: E402

PX_W, PX_H, PX_FPS = 270, 480, 12      # a quarter of the canvas, a quarter of the frame rate
SCALE = PX_W / cc.W
KIND_COLOUR = {"card": "0x2b2b4a", "scene": "0x1d3a30", "intro": "0x4a2b2b", "cliff": "0x3d1d1d"}
SIDE_PAD_PX = 2 * cc.CAP_PAD_X


def F(cid: str, msg: str, fix: str, sev: str = "fail") -> dict:
    return {"id": cid, "msg": msg, "fix": fix, "sev": sev}


def pseudo_plates(states: list[dict]) -> list[dict]:
    """A caption state as the dict captions.json will hold (the keys the gate's checks read), minus the pixels."""
    out = []
    for st in states:
        out.append({"line": st["line"], "unit": st["unit"], "text": st["text"], "gloss": st["gloss"], "active": st["words"][st["active"]], "active_index": st["active"], "word_i": st["word_i"],
                    "n_lines": st["n_lines"], "carry": st.get("carry", []), "clause_words": st["clause_words"], "split": st["split"], "start": st["start"], "end": st["end"],
                    "word_start": st["word_start"], "word_end": st["word_end"], "font_px_1080": cc.CAP_FONT_PX, "style": st.get("style")})
    return out


def plate_px_width(st: dict, px: dict[str, float]) -> float:
    """The widest row of a plate as the plate draws it: Thmanyah widths measured in Chrome, the per-word margin of stage_captions, the plate padding."""
    margin = 2 * 0.22 * cc.CAP_FONT_PX
    rows = [sum(px.get(w, 0.0) + margin for w in (st["words"][j] for j in row)) for row in st["lines"]]
    return (max(rows) if rows else 0.0) + SIDE_PAD_PX


def caption_findings(states: list[dict], tl: dict, plan: dict, script: dict, px: dict, glossary: list, lex: dict) -> list[dict]:
    out: list[dict] = []
    cp = sorted(pseudo_plates(states), key=lambda c: c["start"])
    if not cp:
        return [F("ANI-CAP-COVER", "no caption plates at all", "script: the narrator lines have no words to show")]
    if not all(b["start"] >= a["end"] - 1e-6 for a, b in zip(cp, cp[1:])):
        bad = next((a, b) for a, b in zip(cp, cp[1:]) if b["start"] < a["end"] - 1e-6)
        out.append(F("CALM-ONE-PLATE", f"two plates on screen together at {bad[1]['start']:.2f} s ({bad[0]['line']} / {bad[1]['line']})", "plan: lines come too close; lengthen the scene so one plate ends before the next"))
    shown = {l["id"]: {**l, "text": display_text(l["text"])} for l in script["lines"]}
    for x in CS.check_plates(cp, shown, None):
        cid = x.split(" ", 1)[0]
        out.append(F(cid, x.split(" ", 1)[1][:260], "plan: a plate is up for less than a reader needs; the plan adds a reading pause after the scene (read_hold) or the writer shortens the line, before any shot is rendered"))
    by_id = {l["id"]: l for l in script["lines"]}
    gp = G.check_captions(cp, by_id, glossary)
    gp += [x for k, v in cc._visible_strings(plan) for x in G.check_text(str(v), None, glossary, where=f"{k} ")]
    gp += G.check_script_tags(script["lines"], glossary)
    gp += [x for c in cp for x in G.check_foreign(c["text"], (by_id.get(c["line"]) or {}).get("speaker"), glossary, lex["foreign_keys"], f"plate {c['line']} ", lex["loanwords"])]
    if gp:
        out.append(F("CAP-FOREIGN-GLOSS", "; ".join(gp[:3])[:300], "script: tag the own-language word on its line and add it to glossary.json (meaning in at most 3 words)"))
    if any(has_tashkeel(c["text"]) for c in cp):
        out.append(F("CALM-NO-TASHKEEL", "a caption plate carries tashkeel", "script: text (the caption) has none; tashkeel lives only in tts_text"))
    items_by_line = {ln["line"]: it for it in tl["items"] for ln in cc.item_lines(it)}
    spoken = {l for l in items_by_line}
    covered = {c["line"] for c in cp}
    miss = sorted(l for l in spoken if l not in covered and display_text(shown[l]["text"]).split())
    if miss:
        out.append(F("ANI-CAP-COVER", f"spoken line(s) with no caption: {', '.join(miss[:6])}", "plan: every spoken line is captioned (Reels are watched muted)"))
    total = float(tl["total_s"])
    for c in cp:
        it = items_by_line.get(c["line"])
        if it is None:
            continue
        if c["start"] < it["t0"] - 0.05 or c["end"] > total + 0.05:
            out.append(F("ANI-CAP-WINDOW", f"plate «{c['text'][:24]}» ({c['start']:.2f} to {c['end']:.2f} s) is outside the item that speaks it ({it['id']}, {it['t0']} to {it['t1']} s)",
                         "plan: lengthen the scene so its plates stay inside it"))
            break
    wide = [(st["text"][:22], round(plate_px_width(st, px))) for st in states if plate_px_width(st, px) > cc.SAFE[2] - cc.SAFE[0] + 1]
    if wide:
        out.append(F("CALM-PLATE-SAFE", f"{len(wide)} plate(s) wider than the {cc.SAFE[2] - cc.SAFE[0]} px safe area, first «{wide[0][0]}» at {wide[0][1]} px", "script: shorten the line or split it at a clause"))
    return out


def timing_findings(ep, tl: dict, plan: dict, script: dict, ep_takes_s: dict[str, float]) -> list[dict]:
    out: list[dict] = []
    ok, detail, warn = cc.length_check(float(tl["total_s"]))
    if not ok:
        out.append(F("CALM-LENGTH", detail, "script: under the 25 s floor; the writer adds scenes"))
    elif warn:
        out.append(F("CALM-LENGTH", warn, "plan: the story sets the length (the owner 2026-10-25); the Lead confirms", "warn"))
    sl_ = script["lines"]
    if cc.format_v2(plan):      # format v2 (the owner 2026-10-28): the narrator is at most a quarter of the placed voice time
        spk = {l["id"]: l.get("speaker") for l in sl_}
        share = cc.narrator_share([(spk.get(ln["line"]), ep_takes_s[ln["line"]]) for it, ln in cc._spoken(tl["items"]) if ln["line"] in ep_takes_s and it.get("id") != "choice"])   # the vote card is the narrator's by role (the owner 2026-10-28): not counted
        if share > cc.NARRATOR_SHARE_MAX + 1e-9:
            out.append(F("NARRATOR-SHARE", f"the narrator is {share:.0%} of the placed voice time (at most {cc.NARRATOR_SHARE_MAX:.0%}, the vote card not counted)", "script: give the story lines to the characters; the narrator keeps the recap, night links and the vote question"))
    try:
        import qg_checks as qc
        pl = {"lines": [{"start": ln["voice_t0"], "dur": ep_takes_s[ln["line"]]} for it, ln in cc._spoken(tl["items"]) if ln["line"] in ep_takes_s],
              "intro_s": sum(float(it.get("dur") or 0.0) for it in tl["items"] if it.get("kind") == "intro")}      # intro_freeze time is not counted in voice coverage
        sh = cc.episode_shotlist(ep, tl, plan)
        end = {"choices": [plan["choice"]["choice1"], plan["choice"]["choice2"]]}
        mine = [x for x in qc.check_calm_declared(pl, {"captions": []}, end, sh, tl["total_s"]) if "CALM-CAPTION-STYLE" not in x]     # the plates are checked above from the real states; here only voice share, wrapper, choice position, subjects
        return out + [F((re.search(r"\[([A-Z0-9-]+)\]", x) or [0, "CALM-DECLARED"])[1], x[:260], "plan: see the check id in kb/quality/gate-spec.md; fix it in the plan or the script") for x in mine]
    except ImportError:
        return out + [F("CALM-DECLARED", "qg_checks is not importable", "tools: install numpy", "warn")]


def audio_findings(ep, tl: dict, plan: dict, info: dict) -> list[dict]:
    import numpy as np
    out: list[dict] = []
    lufs, tp = info.get("integrated_lufs"), info.get("true_peak_dbtp")
    if lufs is None or not -15.0 <= lufs <= -13.0 or (tp is not None and tp > -1.0):
        out.append(F("CALM-LOUDNESS", f"the mix is {lufs} LUFS / {tp} dBTP (band -15 to -13 LUFS, true peak at most -1)", "compose: the mix chain is in tools/calm_mix.py; the bed level comes from the plan's mix_preset"))
    ac = info.get("audio_checks")
    if isinstance(ac, list):
        for x in ac:
            out.append(F(x.split(" ", 1)[0], x.split(" ", 1)[-1][:260], "compose: phone-first mix thresholds are in tools/audio_checks.py; the sources are in tools/calm_mix.py"))
    dur = cc.wav_seconds(ep.mix)
    if abs(dur - float(tl["total_s"])) > 0.15:
        out.append(F("ANI-MIX-LENGTH", f"mix.wav lasts {dur:.2f} s, the timeline {tl['total_s']} s", "compose: rerun the animatic stage"))
    import audio_checks as AC
    x, sr = AC.read_wav(ep.mix)
    m = np.abs(x).max(axis=1)
    blk = max(1, int(sr * 0.01))
    n = len(m) // blk
    quiet = (m[: n * blk].reshape(n, blk).max(axis=1) < 10 ** (-45 / 20))
    run = best = 0
    for q in quiet:
        run = run + 1 if q else 0
        best = max(best, run)
    if best * 0.01 > cc.SILENCE_MAX_S:
        out.append(F("CALM-NO-SILENCE", f"the mix has a silent gap of {best * 0.01:.2f} s (limit {cc.SILENCE_MAX_S} s)", "plan: the bed or the narrator must cover it"))
    try:
        import calm_sfx
        sfx = json.loads((ep.work / "sfx.json").read_text(encoding="utf-8"))
        bad = calm_sfx.check(sfx, plan, tl)
        for cid in ("CALM-TRANSITION-SFX", "CALM-FOLEY", "CALM-CHOICE-SFX", "CALM-INTRO-SFX"):
            mine = [b.split(" ", 1)[1] for b in bad if b.startswith(cid + " ")]
            if mine:
                out.append(F(cid, "; ".join(mine[:2])[:260], "plan: every join declares a cut type with a sound (tools/calm_sfx.py CUTS)"))
    except ImportError:
        pass
    return out


def build_video(ep, tl: dict, states: list[dict], hud: list[dict], px: dict, takes_s: dict, out: Path) -> None:
    """Flat colour per item, a box per caption plate (white; yellow when the sentence carries a gloss), a green bar where a take plays, the mix as sound. 270x480 at 12 fps."""
    T = float(tl["total_s"])
    ch = []
    r = lambda v: max(1, round(v * SCALE))
    for it in tl["items"]:
        col = KIND_COLOUR["cliff"] if it.get("block") == "cliff" and it["kind"] == "scene" else KIND_COLOUR.get(it["kind"], KIND_COLOUR["scene"])
        ch.append(f"drawbox=x=0:y=0:w={PX_W}:h={PX_H}:color={col}:t=fill:enable='between(t,{it['t0']:.3f},{it['t1']:.3f})'")
    for h in hud:
        ch.append(f"drawbox=x={r(cc.HUD_XY[0])}:y={r(cc.HUD_XY[1])}:w={r(380)}:h={r(110)}:color=0x888888@0.8:t=fill:enable='between(t,{h['t0']:.3f},{h['t1']:.3f})'")
    for st in states:
        w = min(PX_W - 4, r(plate_px_width(st, px)))
        hgt = r(cc.CAP_H1 * max(1, st["n_lines"]))
        y = r(st.get("cap_y") or cc.CAP_Y) + r(cc.CAP_H1) - hgt
        col = "0xf2d030" if st["gloss"] else "0xf4f4f4"
        ch.append(f"drawbox=x={(PX_W - w) // 2}:y={y}:w={w}:h={hgt}:color={col}@0.92:t=fill:enable='between(t,{st['start']:.3f},{st['end']:.3f})'")
    for it, ln in cc._spoken(tl["items"]):
        d = takes_s.get(ln["line"])
        if d:
            ch.append(f"drawbox=x=0:y={PX_H - 8}:w={PX_W}:h=8:color=0x3ddc84:t=fill:enable='between(t,{ln['voice_t0']:.3f},{ln['voice_t0'] + d:.3f})'")
    script = ",\n".join(ch)
    gf = out.with_suffix(".filtergraph")
    gf.write_text(f"[0:v]{script}[vout]", encoding="utf-8")
    cc.ff(["-f", "lavfi", "-i", f"color=c=0x101018:s={PX_W}x{PX_H}:r={PX_FPS}:d={T:.3f}", "-i", ep.mix, "-filter_complex_script", gf,
           "-map", "[vout]", "-map", "1:a", "-t", f"{T:.3f}", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "34", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", out])


def build(ep_id: str, root: Path | None = None) -> dict:
    t_all = time.time()
    ep = cc.Ep(ep_id, root or cc.ROOT)
    adir = ep.work / "animatic"
    adir.mkdir(parents=True, exist_ok=True)
    tl, plan, script = cc.read_json(ep.timeline_p), cc.read_json(ep.plan_p), cc.read_json(ep.script_p)
    tm: dict = {}
    findings: list[dict] = []
    t0 = time.time()
    try:
        states, hud, _timing, px, _chunks = cc.caption_states(ep, tl, script, adir)
    except cc.Fail as e:
        findings.append(F(e.cid, e.msg[:300], "script: the words of a line cannot be shown as a caption; reword the line (before it is voiced)"))
        return finish(ep, adir, findings, [], {"total": round(time.time() - t_all, 1)}, tl)
    tm["captions_s"] = round(time.time() - t0, 1)
    glossary = G.load(ep.root, script.get("series") or ep.series)
    lex = G.lexicon(ep.root, script.get("series") or ep.series)
    t0 = time.time()
    takes_s = {l["id"]: cc.wav_seconds(ep.take(l["id"])) for l in script["lines"] if ep.take(l["id"]).is_file()}
    findings += caption_findings(states, tl, plan, script, px, glossary, lex)
    findings += timing_findings(ep, tl, plan, script, takes_s)
    tm["checks_s"] = round(time.time() - t0, 1)
    t0 = time.time()
    try:
        info = cc.stage_audio(ep)
        cc.record_stage(ep, "audio")
        findings += audio_findings(ep, tl, plan, info)
    except cc.Fail as e:
        findings.append(F(e.cid, e.msg[:300], "compose: the mix cannot be built from the takes and cues"))
    tm["audio_s"] = round(time.time() - t0, 1)
    t0 = time.time()
    if ep.mix.is_file():
        build_video(ep, tl, states, hud, px, takes_s, adir / "animatic.mp4")
    tm["video_s"] = round(time.time() - t0, 1)
    tm["total"] = round(time.time() - t_all, 1)
    plates = [[st["line"], st["unit"], st["active"], round(st["start"], 2), round(st["end"], 2)] for st in sorted(states, key=lambda s: (s["start"], s["line"]))]
    return finish(ep, adir, findings, plates, tm, tl)


def finish(ep, adir: Path, findings: list[dict], plates: list, tm: dict, tl: dict) -> dict:
    rep = {"episode": ep.id, "total_s": tl.get("total_s"), "findings": findings, "verdict": "FAIL" if any(f["sev"] == "fail" for f in findings) else "PASS", "plates": plates, "timings": tm,
           "note": "early preview: no shot is drawn; captions, timing and the mix are the real ones (pipelines/STAGE-GATES.md)"}
    cc.write_json(adir / "report.json", rep)
    return rep


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] != "build":
        print(__doc__)
        return 2
    try:
        rep = build(argv[1])
    except cc.Fail as e:
        print(e)
        return 1
    for f in rep["findings"]:
        print(f"{'FAIL' if f['sev'] == 'fail' else 'WARN'} [{f['id']}] {f['msg']}")
    print(f"[animatic] {rep['verdict']} {rep['timings']}")
    return 0 if rep["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
