# calm_compose.py part 3 of 3: executed into the calm_compose module namespace by calm_compose.py (a pure move).
# ------------------------------------------------------------------ stage: audio
def bed_filter(total: float) -> str:
    """A dark ambient bed that never drops out: two sines a fifth apart and low brown noise, all procedural (ffmpeg lavfi), no licence to track."""
    return (f"sine=frequency=55:sample_rate=48000:duration={total:.3f}[a];sine=frequency=82.5:sample_rate=48000:duration={total:.3f}[b];"
            f"anoisesrc=color=brown:amplitude=0.25:sample_rate=48000:duration={total:.3f}[n];"
            f"[a]volume=0.5[a2];[b]volume=0.25[b2];[n]lowpass=f=220[n2];[a2][b2][n2]amix=inputs=3:normalize=0,aformat=channel_layouts=stereo,volume=0.35[bed]")


def stage_audio_legacy(ep: Ep) -> dict:
    """The first calm mix (E01C v1/v2): kept so `mix_preset: legacy` in calm-plan.json reproduces the 'before' numbers of research/sound-e01c.md. Not used by default."""
    import compose as C
    tl = read_json(ep.timeline_p)
    total = tl["total_s"]
    wd = ep.work / "audio"
    wd.mkdir(parents=True, exist_ok=True)
    args, fl, labels = [], [], []
    n = 0
    for it, ln in _spoken(tl["items"]):
        args += ["-i", ep.take(ln["line"])]
        ms = int(round(ln["voice_t0"] * 1000))
        fl.append(f"[{n}:a]aresample=48000,aformat=channel_layouts=stereo,volume=0dB,adelay={ms}|{ms}[v{n}]")
        labels.append(f"[v{n}]")
        n += 1
    if not n:
        raise Fail("AUDIO-NO-VOICE", "no narrator lines in the timeline")
    fl.append(f"{''.join(labels)}amix=inputs={n}:normalize=0:duration=longest,apad=whole_dur={total:.3f},atrim=0:{total:.3f},asplit=3[voice][vsc][vsc2]")
    fl.append(bed_filter(total))
    fl.append("[bed][vsc]sidechaincompress=threshold=0.02:ratio=9:attack=15:release=500:makeup=1[bedd]")   # about -10 dB under the voice
    import calm_sfx    # C3 + C4 + C5: transition sounds, the horn, the choice pops and the foley, from sfx.json (built from the plan, the timeline and the shot specs)
    sfx = calm_sfx.build(ep.id, read_json(ep.plan_p), tl)
    write_json(ep.work / "sfx.json", sfx)
    reg = calm_sfx.parse_licences()
    lic = sorted({p for p in (calm_sfx.licence_problems(c["file"], c["licence_id"], reg) for c in sfx["cues"]) if p})
    if lic:
        raise Fail("AUDIO-LICENCE", "; ".join(lic[:3]) + " (nothing unlicensed is mixed)")
    cues = [c for c in sfx["cues"] if c["t"] < total - 0.05]
    for k, c in enumerate(cues):
        args += ["-i", ep.root / c["file"]]
        ms = int(round(c["t"] * 1000))
        cut = f"atrim=0:{c['dur']:.3f},afade=t=out:st={max(0.0, c['dur'] - 0.12):.3f}:d=0.12," if c.get("dur") else ""
        fl.append(f"[{n + k}:a]aresample=48000,aformat=channel_layouts=stereo,{cut}volume={c['gain_db']}dB,adelay={ms}|{ms}[x{k}]")
    if cues:
        fl.append(f"{''.join(f'[x{k}]' for k in range(len(cues)))}amix=inputs={len(cues)}:normalize=0:duration=longest,apad=whole_dur={total:.3f},atrim=0:{total:.3f}[sfxbus]")
        fl.append("[sfxbus][vsc2]sidechaincompress=threshold=0.02:ratio=4:attack=15:release=400:makeup=1[sfxd]")      # the whole sfx bus ducks under the narrator, as in compose.py
        fl.append("[voice][bedd][sfxd]amix=inputs=3:normalize=0:duration=longest,acompressor=threshold=0.03:ratio=8:attack=10:release=300:makeup=3,atrim=0:%.3f[o]" % total)
    else:
        fl.append("[vsc2]anullsink")
        fl.append("[voice][bedd]amix=inputs=2:normalize=0:duration=longest,acompressor=threshold=0.03:ratio=8:attack=10:release=300:makeup=3,atrim=0:%.3f[o]" % total)   # loudness range <= 5 LU: a compressor, loudnorm alone cannot narrow it
    premix = wd / "premix.wav"
    ff([*args, "-filter_complex_script", _graph_file(wd / "audio.filtergraph", fl), "-map", "[o]", "-ar", "48000", "-c:a", "pcm_f32le", premix])
    r = ff(["-i", premix, "-af", f"loudnorm=I={LOUD_I}:TP={LOUD_TP}:LRA={LOUD_LRA}:print_format=json", "-f", "null", "-"], log="info")   # loudnorm prints its measurement at info level
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr, re.S)
    if not m:
        raise Fail("TOOL-ERROR", "loudnorm printed no measurement")
    ms = json.loads(m.group(0))
    ln = (f"loudnorm=I={LOUD_I}:TP={LOUD_TP}:LRA={LOUD_LRA}:measured_I={ms['input_i']}:measured_TP={ms['input_tp']}:measured_LRA={ms['input_lra']}:"
          f"measured_thresh={ms['input_thresh']}:offset={ms['target_offset']}:linear=true")
    ff(["-i", premix, "-af", f"{ln},aresample=48000", "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", ep.mix])
    loud = C.measure_loudness(ep.mix)
    write_json(ep.work / "audio.json", {"voice_lines": n, "sfx_cues": len(cues), "loudness": loud, "bed": "procedural: 55 Hz + 82.5 Hz sines + brown noise (ffmpeg lavfi), ducked by sidechaincompress", "note": VOICE_LUFS_NOTE})
    return {"integrated_lufs": loud["integrated_lufs"], "true_peak_dbtp": loud["true_peak_dbtp"], "lines": n}


def stage_audio(ep: Ep) -> dict:
    """Phone-first mix (owner, 2026-10-25, C9): per-source cleanup and levels measured the way a phone plays them, a pad bed a phone can hear, dialogue-first ducking from the voice,
    final -14 LUFS. The chain and its presets live in tools/calm_mix.py; `mix_preset: legacy` in calm-plan.json runs the old chain. Writes mix.wav, audio/stems/, audio.json."""
    import compose as C
    plan = read_json(ep.plan_p)
    preset = plan.get("mix_preset", "phone-first")
    if preset == "legacy":
        return stage_audio_legacy(ep)
    import calm_mix
    import calm_sfx
    tl = read_json(ep.timeline_p)
    if not any(True for _ in _spoken(tl["items"])):
        raise Fail("AUDIO-NO-VOICE", "no narrator lines in the timeline")
    sfx = calm_sfx.build(ep.id, plan, tl)
    write_json(ep.work / "sfx.json", sfx)
    reg = calm_sfx.parse_licences()
    lic = sorted({p for p in (calm_sfx.licence_problems(c["file"], c["licence_id"], reg) for c in sfx["cues"]) if p})
    if lic:
        raise Fail("AUDIO-LICENCE", "; ".join(lic[:3]) + " (nothing unlicensed is mixed)")
    if preset not in calm_mix.PRESETS:
        raise Fail("AUDIO-MODE", f"mix_preset {preset!r} is not one of {', '.join(sorted(calm_mix.PRESETS))} or legacy")
    rep = calm_mix.render(ep, preset)
    loud = C.measure_loudness(ep.mix)
    import audio_checks as AC
    fails, metrics = AC.run_checks(ep.work / "audio" / "stems", ep.mix)
    write_json(ep.work / "audio.json", {"voice_lines": rep["voice_lines"], "sfx_cues": rep["sfx_cues"], "loudness": loud, "mix_preset": preset, "master_gain_db": rep["master_gain_db"], "limiter_used": rep["limiter_used"],
                                        "bed": "pad (numpy, deterministic): Am / F / Am, notes 110 Hz and up with harmonics to 2.5 kHz, ducked 9 dB under every voice (calm_mix.synth_pad)", "audio_checks": metrics,
                                        "note": f"voice {rep['voice_phone_lufs']} LUFS through the phone simulation, bed {rep['bed_gain_db']} dB set 15 LU under it"})
    return {"integrated_lufs": loud["integrated_lufs"], "true_peak_dbtp": loud["true_peak_dbtp"], "lines": rep["voice_lines"], "audio_checks": "pass" if not fails else fails[:2]}


# ------------------------------------------------------------------ stage: assemble
VFX_XFADE = {"flash": "fadewhite", "ink_wipe": "wiperight", "smear": "hblur", "iris": "circleopen", "page_turn": "revealright", "ink_fade": "fadeblack", "iris_close": "circleclose"}


def _choice_card(ep: Ep) -> dict:
    """The card of the choice_split shot as it was recorded (work/shots/<ep>-choice/calm.json); a stale card (the old choice_card) is refused, never guessed."""
    c = read_json(ep.root / "work" / "shots" / f"{ep.id}-choice" / "calm.json")
    if c.get("template") != "choice_split":
        raise Fail("ASM-CHOICE-STALE", f"work/shots/{ep.id}-choice is a {c.get('template')}, the plan asks for choice_split: rebuild that card shot (daily.py shots)")
    return c["card"]


def choice_top_filters(it: dict, k: int, extra: dict) -> list[str]:
    """C4: the top half of the choice sequence (1080 x TOP_H, it['dur'] s): the two close-ups cut into each other, a crossfade VFX at every cut, each close-up a slow drift
    (a crop window moving over a rendered shot, so the top half keeps moving). Segment j shows its clip from where that clip last stopped; a clip that runs out holds its last frame."""
    sp = it["split"]
    top = {c["id"]: c for c in sp["top"]}
    bounds = [0.0] + [c["t"] for c in sp["cuts"]] + [it["dur"]]
    clips = [sp["first"]] + [c["clip"] for c in sp["cuts"]]
    m = len(clips)
    uses = {cid: clips.count(cid) for cid in top}
    fl, cur = [], {cid: 0.0 for cid in top}
    for cid, nuse in uses.items():
        nn = max(nuse, 1)
        fl.append(f"[{extra[cid]}:v]scale={W}:{H}:flags=bicubic,setsar=1,format=yuv420p,tpad=stop_mode=clone:stop_duration=12,split={nn}" + "".join(f"[tp{k}{cid}{j}]" for j in range(nn)))
    seen = {cid: 0 for cid in top}
    lens = []
    for j, cid in enumerate(clips):
        d = bounds[j + 1] - bounds[j]
        ln = d + (XD / 2 if m > 1 else 0.0) if j == 0 else (d + XD / 2 if j == m - 1 else d + XD)
        c = top[cid]["crop"]
        cw = int(c["w"]) // 2 * 2
        ch = int(round(cw * TOP_H / W)) // 2 * 2
        fl.append(f"[tp{k}{cid}{seen[cid]}]trim=start={cur[cid]:.4f}:duration={ln:.4f},setpts=PTS-STARTPTS,fps={FPS},"
                  f"crop=w={cw}:h={ch}:x='{c['x']}+{c.get('dx', 0)}*t/{max(ln, 0.1):.4f}':y='{c['y']}+{c.get('dy', 0)}*t/{max(ln, 0.1):.4f}',scale={W}:{TOP_H}:flags=lanczos,setsar=1,format=yuv420p[tg{k}_{j}]")
        seen[cid] += 1
        cur[cid] += d
        lens.append(ln)
    acc, acc_len = f"tg{k}_0", lens[0]
    for j in range(1, m):
        nxt = f"tx{k}_{j}" if j < m - 1 else f"top{k}"
        xf = VFX_XFADE.get(sp["cuts"][j - 1].get("vfx", "flash"), "fadewhite")
        fl.append(f"[{acc}][tg{k}_{j}]xfade=transition={xf}:duration={XD:.4f}:offset={acc_len - XD:.4f}[{nxt}]")
        acc_len = acc_len - XD + lens[j]
        acc = nxt
    if m == 1:
        fl.append(f"[{acc}]null[top{k}]")
    return fl


def stage_assemble(ep: Ep) -> dict:
    import compose as C
    tl, caps, hud = read_json(ep.timeline_p), read_json(ep.caps_p)["captions"], read_json(ep.hud_p)["hud"]
    miss = [it["video"] for it in tl["items"] if not (ep.root / it["video"]).is_file()]
    tops = {}      # C4: the two close-ups cut into the top half of the choice sequence (clip id -> its rendered shot)
    for it in tl["items"]:
        for c in (it.get("split") or {}).get("top", []):
            tops[c["id"]] = ep.root / "work" / "shots" / f"{ep.id}-{c['shot']}" / "out" / f"{ep.id}-{c['shot']}.mp4"
    miss += [str(v.relative_to(ep.root)) for v in tops.values() if not v.is_file()]
    if miss:
        raise Fail("ASM-SHOT-VIDEO", f"no render for: {', '.join(miss[:4])} (shots and cards are recorded before composing)")
    if not ep.mix.is_file():
        raise Fail("ASM-AUDIO", "mix.wav missing: run `audio` first")
    poster = build_poster(ep, read_json(ep.plan_p))       # R-501: frame 0 is the grid poster, never black; built first, it is one more input of the graph
    args, fl = [], []
    n_items = len(tl["items"])
    for k, it in enumerate(tl["items"]):
        args += [*C.hw_in(), "-i", ep.root / it["video"]]
        sp = it.get("split")
        hold = float(it.get("hold") or 0.0) + float(it.get("read_hold") or 0.0)   # the last `hold` s are the last played frame, held: same length, so no voice, caption or join moves; read_hold (C12) is the plan's reading pause after the shot's own length
        if hold > 0:
            fl.append(f"[{k}:v]trim=duration={it['dur'] - hold:.4f},setpts=PTS-STARTPTS,fps={FPS},tpad=stop_mode=clone:stop_duration={hold:.4f},scale={W}:{H}:flags=bicubic,setsar=1,format=yuv420p[{'sc' if sp else 's'}{k}]")
        else:
            fl.append(f"[{k}:v]trim=duration={it['dur']:.4f},setpts=PTS-STARTPTS,fps={FPS},scale={W}:{H}:flags=bicubic,setsar=1,format=yuv420p[{'sc' if sp else 's'}{k}]")
    extra = {}
    for cid, vp in tops.items():
        args += [*C.hw_in(), "-i", vp]
        extra[cid] = n_items + len(extra)
    for k, it in enumerate(tl["items"]):
        if it.get("split"):
            fl += choice_top_filters(it, k, extra)
            fl.append(f"[sc{k}][top{k}]overlay=0:0:format=auto,format=yuv420p[s{k}]")
    acc, length = "s0", tl["items"][0]["dur"]
    for k in range(1, len(tl["items"])):
        nxt = f"j{k}"
        fl.append(f"[{acc}][s{k}]xfade=transition={tl['items'][k].get('join_in', {}).get('xfade', 'fadeblack')}:duration={JOIN_S:.4f}:offset={length - JOIN_S:.4f}[{nxt}]")   # C3: the cut type of the join picks the visual
        length += tl["items"][k]["dur"] - JOIN_S
        acc = nxt
    n = n_items + len(extra)
    idx = n
    for c in caps:
        args += ["-i", ep.work / c["png"]]
        nxt = f"c{idx}"
        fl.append(f"[{acc}][{idx}:v]overlay=x={c['x']}:y={c['y']}:enable='between(t,{c['start']},{c['end']})':format=auto[{nxt}]")
        acc, idx = nxt, idx + 1
    for h in hud:
        args += ["-i", ep.work / h["png"]]
        nxt = f"c{idx}"
        fl.append(f"[{acc}][{idx}:v]overlay=x={h['x']}:y={h['y']}:enable='between(t,{hud_window(h)[0]},{hud_window(h)[1]})':format=auto[{nxt}]")
        acc, idx = nxt, idx + 1
    for it in tl["items"]:    # C4: the question and each choice light up as the narrator reads them (lit plates over the card, bottom half)
        if it.get("split"):
            import calm_cards
            for lp in calm_cards.lit_plates(_choice_card(ep), ep.work / "plates" / "lit"):
                st = next(l for l in it["split"]["lit"] if l["state"] == lp["state"])
                args += ["-i", ep.work / "plates" / "lit" / lp["png"]]
                nxt = f"c{idx}"
                fl.append(f"[{acc}][{idx}:v]overlay=x={lp['x']}:y={lp['y']}:enable='between(t,{it['t0'] + st['t0']:.3f},{it['t0'] + st['t1']:.3f})':format=auto[{nxt}]")
                acc, idx = nxt, idx + 1
    args += ["-loop", "1", "-framerate", str(FPS), "-t", f"{GP.POSTER_HOLD_S + GP.POSTER_FADE_S:.3f}", "-i", poster["png"]]      # R-501: the grid poster covers frame 0 for POSTER_HOLD_S, then fades into the opening (above the plates, under the mark)
    fl.append(f"[{idx}:v]format=yuva420p,fade=t=out:st={GP.POSTER_HOLD_S:.3f}:d={GP.POSTER_FADE_S:.3f}:alpha=1[pz]")
    fl.append(f"[{acc}][pz]overlay=0:0:eof_action=pass:format=auto[pzo]")
    acc, idx = "pzo", idx + 1
    args += ["-i", WM.ensure_mark()]      # the last compose step (the owner 2026-10-25): the small NJ mark over every frame, in the one final encode
    fl += WM.filter_chain(acc, idx, "wm")
    acc, idx = "wm", idx + 1
    args += ["-i", ep.mix]
    fl.append(f"[{acc}]format=yuv420p[vout]")
    T = tl["total_s"]
    C.ff([*args, "-filter_complex_script", _graph_file(ep.work / "assemble.filtergraph", fl), "-map", "[vout]", "-map", f"{idx}:a", "-t", f"{T:.4f}", "-r", str(FPS), *C.venc_args(), "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
          "-movflags", "+faststart", ep.out])
    vd = float(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=duration", "-of", "csv=p=0", str(ep.out)], capture_output=True, text=True).stdout.strip() or 0)
    if abs(vd - T) > 0.25:   # E01C 2026-10-25: a stale, shorter shot ended the graph at 12.5 s while the audio ran 101.8 s, and every stage still said ok
        raise Fail("ASSEMBLE-SHORT", f"the video stream is {vd:.2f} s but the timeline is {T:.2f} s: a shot's file is shorter than its planned length (rebuild the shots) or an input ended early")
    WM.write_sidecar(ep.work)
    cover = stage_cover(ep, read_json(ep.plan_p))
    return {"duration_s": round(probe_dur(ep.out), 3), "items": n_items, "plates": len(caps), "watermark": "top-right", **cover}


def build_poster(ep: Ep, plan: dict) -> dict:
    """R-501: the grid poster (tools/grid_poster.py) of this episode: cover.png and cover.jpg in the episode folder. Frame 0 of episode.mp4 and every platform's cover are this image."""
    try:
        return GP.build(ep.id, ep.root, ep.work / "cover.png", ep.plan_p, scratch=ep.work / "cover-build")
    except SystemExit as e:
        raise Fail("ASM-COVER", f"the grid poster was not made: {e}")
    except Exception as e:      # a missing browser or font
        raise Fail("ASM-COVER", f"the grid poster was not made: {e}")


def stage_cover(ep: Ep, plan: dict) -> dict:
    """DESIGN.md 2.6 + R-501: cover.json for the uploaders (tools/ig.py, fb.py, yt.py read it): {png, jpg, hook, scene, fallback_frame_offset_s}. The poster itself was built by stage_assemble
    (it is frame 0 of the episode); the cover is that same image, so the offset fallback is 0 s."""
    cp = ep.work / "cover.png"
    if not cp.is_file():
        raise Fail("ASM-COVER", "cover.png was not made")
    n = episode_number(plan.get("episode"))
    write_json(ep.work / "cover.json", {"png": "cover.png", "jpg": "cover.jpg", "size": [W, H], "numeral": GP.ar_num(n) if n else plan.get("day", ""), "hook": GP.hook_text(plan),
                                        "scene": GP.pick_scene(plan)["id"], "grid_poster": True, "fallback_frame_offset_s": 0.0})
    return {"cover": "cover.png"}


# ------------------------------------------------------------------ stage: gate
def episode_shotlist(ep: Ep, tl: dict, plan: dict | None = None) -> dict:
    """The shapes qg_checks.check_calm_declared reads: wrapper {recap, day_card, choice_card, follow_card: {t0, t1}} and per-shot `subjects`."""
    it = {x["id"]: x for x in tl["items"]}
    w = lambda k: {"t0": it[k]["t0"], "t1": it[k]["t1"]}
    wrapper = {"day_card": w("day"), "choice_card": w("choice"), "follow_card": w("follow")}
    if "recap" in it:
        wrapper = {"recap": w("recap"), **wrapper}
    n = episode_number((plan or {}).get("episode") if plan else tl.get("episode"))
    return {"profile": "calm", "wrapper": wrapper, "episode_no": n, "recap_from": RECAP_FROM_EPISODE,
            "shots": [{"id": x["id"], "subjects": [s for s in x.get("subjects", []) if s]} for x in tl["items"] if x["kind"] == "scene"]}


def length_check(d: float) -> tuple[bool, str, str | None]:
    """CALM-LENGTH: a floor and a soft warning, no ceiling (the owner 2026-10-25: length is whatever suits the story). Returns (ok, detail, warning)."""
    detail = f"{d:.1f} s (floor {LEN_MIN_S:g} s; no upper cap, the owner 2026-10-25: the story sets the length)"
    warn = f"{d:.1f} s is over the {LEN_WARN_S:g} s of the harvested reels: confirm this is the story's length" if d > LEN_WARN_S else None
    return d >= LEN_MIN_S, detail + (f" - WARNING: {warn}" if warn else ""), warn


def cap_plate_ends(states: list[dict], scene_end: dict) -> None:
    """E04 Q04/Q05: a line's last plate must not stay up over the NEXT scene's picture (Lead's words over Hero's face at the s14/s15 join). It ends where its own scene's join begins
    (scene t1 minus half a join), but only when it has then been up long enough to read (CS.read_speed_need_s); otherwise it keeps its reading time and the planner's hold is the cure."""
    for lid_ in dict.fromkeys(st["line"] for st in states):
        ls = [st for st in states if st["line"] == lid_]
        cap = scene_end.get(lid_)
        last = ls[-1]
        if cap is None or last["end"] <= cap + 1e-6:
            continue
        # the plate has been up since its UNIT began (its states only move the highlight): measuring from the last state's start never let a long sentence be capped (E04 round 3: L14's
        # last state started 1.0 s before the join, the 1.5 s floor refused, and «إنها تتأخر ثانيتين» stayed over s15)
        unit_start = min(st["start"] for st in ls if st.get("unit") == last.get("unit"))
        if cap - unit_start + 1e-6 >= CS.read_speed_need_s(CS.visible_chars(last.get("text") or " ".join(last["words"]))):
            last["end"] = round(cap, 3)


def hud_day(it: dict, tl: dict) -> str:
    """The HUD's day row of a scene: the scene's own `day` (plan scene key, E04 Q06: night one is day three) or else the episode's."""
    return "اليوم " + str(it.get("day") or tl["day"]).translate(AR_DIGITS)


def hud_problems(tl: dict, huds: list[dict], recap_tag: str | None = None) -> list[str]:
    """CALM-HUD: the HUD plates (one, or the strip plate and the plate that takes over from it) cover every story scene without a gap; from E02 (the timeline carries an `episode_label`)
    the first HUD plate also carries the series strip «الحلقة N · the series» for STRIP_S, it starts within the first STRIP_S of the episode, and the recap card carries the same words as its tag."""
    f = []
    for it in tl["items"]:
        if it["kind"] != "scene":
            continue
        a, b = it["t0"] + JOIN_S / 2, it["t1"] - JOIN_S / 2
        spans = sorted(hud_window(h) for h in huds if hud_window(h)[1] > a and hud_window(h)[0] < b)
        at, gap = a, False
        for x0, x1 in spans:
            if x0 > at + 0.02:
                gap = True
                break
            at = max(at, x1)
        if gap or at < b - 0.02 or not spans:
            f.append(f"scene {it['id']} has no HUD plate over {a:.2f}..{b:.2f} s")
    label = tl.get("episode_label")
    if label:
        strips = [h for h in huds if h.get("strip")]
        if len(strips) != 1 or strips[0]["strip"] != label:
            f.append(f"the first HUD plate must carry the series strip «{label}» (found {len(strips)} strip plate(s))")
        else:
            w0, w1 = hud_window(strips[0])
            first = next((it for it in tl["items"] if it["kind"] == "scene"), None)
            scene_len = (first["t1"] - first["t0"] - JOIN_S) if first else 0
            if w0 > STRIP_S + 1e-6:
                f.append(f"the series strip starts at {w0:.2f} s: it belongs inside the first {STRIP_S:g} s")
            if abs((w1 - w0) - min(float(tl.get("strip_s", STRIP_S)), scene_len)) > 0.06:
                f.append(f"the series strip is up {w1 - w0:.2f} s (it stays {STRIP_S:g} s, or the whole first scene when that is shorter)")
        rc = next((it for it in tl["items"] if it["id"] == "recap"), None)
        if rc is not None and rc.get("tag") != label:
            f.append(f"the recap card's tag is {rc.get('tag')!r}, not «{label}»")
        if rc is not None and recap_tag != label:
            f.append(f"the recap card shot carries tag {recap_tag!r}, not «{label}»: tools/daily.py must build the recap card from calm_compose.recap_card_params(plan)")
    return f


def hook_3s_problems(tl: dict, plan: dict) -> list[str]:
    """CALM-HOOK-3S (DESIGN.md 2.1): a voiced line, or a story event the plan declares (a foley cue of a scene), starts before HOOK_S. Reads timeline.json and the plan, no render."""
    voiced = [ln["voice_t0"] for _, ln in _spoken(tl["items"])]
    events = []
    by_id = {s_["id"]: s_ for s_ in plan.get("scenes", [])}
    for it in tl["items"]:
        if it["kind"] == "scene":
            events += [round(it["t0"] + float(fy.get("at", 0.0)), 3) for fy in by_id.get(it["id"], {}).get("foley", []) or []]
    first = min(voiced + events) if (voiced or events) else None
    if first is None:
        return ["no voiced line and no declared story event: the first seconds are empty"]
    if first >= HOOK_S:
        return [f"the first voiced line or declared story event starts at {first:.2f} s (it must start before {HOOK_S:g} s)"]
    return []


CARD_PUSH = 1.0 + CC.PUSH_PCT / 100.0      # a card's clip pushes in 4 % about the frame centre (calm_cards.encode): its text boxes are measured on the still, before the push


def _pushed(b: dict) -> dict:
    """A measured box (x0, y0, x1, y1) after the card's push-in, as x, y, w, h: scaled about the frame centre."""
    cx, cy = W / 2, H / 2
    x0, x1, y0, y1 = (cx + (b["x0"] - cx) * CARD_PUSH, cx + (b["x1"] - cx) * CARD_PUSH, cy + (b["y0"] - cy) * CARD_PUSH, cy + (b["y1"] - cy) * CARD_PUSH)
    return {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0}


def card_text_boxes(ep: Ep, tl: dict) -> tuple[list[dict], list[str]]:
    """The measured text boxes of every card (card-measure.json) and every intro's placed boxes (intro-measure.json), after the card push-in, as x, y, w, h in screen px: what
    WATERMARK-CLEAR keeps clear. Returns (boxes, missing): a card or intro with no measure file is a failure for the caller, never a skip."""
    out, missing = [], []
    for it in tl["items"]:
        d = ep.root / "work" / "shots" / it["shot"] / "out"
        if it["kind"] in ("card", "intro"):
            mp = d / ("card-measure.json" if it["kind"] == "card" else "intro-measure.json")
            if not mp.is_file():
                missing.append(f"{it['id']}: {mp.name} is missing, so its text cannot be proved clear of the mark")
                continue
            m = read_json(mp)
            for b in (m.get("boxes", []) if it["kind"] == "card" else m.get("placed_boxes", [])):
                out.append({**_pushed(b), "what": f"{it['id']} {str(b.get('text') or b.get('layer') or '')[:12]}"})
    return out, missing


def stage_gate(ep: Ep, skip_render: bool = False) -> dict:
    import compose as C
    tl, caps = read_json(ep.timeline_p), read_json(ep.caps_p)
    plan = read_json(ep.plan_p)
    checks, fails = [], []

    def rec(cid, ok, detail):
        checks.append({"id": cid, "status": "pass" if ok else "fail", "detail": detail})
        if not ok:
            fails.append(f"{cid} {detail}")
    d = probe_dur(ep.out)
    ok, detail, warn = length_check(d)
    rec("CALM-LENGTH", ok, detail)
    if warn:
        checks[-1]["warning"] = warn
    vis = [str(v) for _, v in _visible_strings(plan)] + [c["text"] for c in caps["captions"]]
    rec("CALM-NO-TASHKEEL", not any(has_tashkeel(v) for v in vis), f"{len(vis)} visible strings checked")
    loud = C.measure_loudness(ep.out)
    dv = SOUND["delivery"]["instagram"]        # one file goes to Instagram, Facebook and YouTube: one set of limits (-15..-13 LUFS, <= -1.0 dBTP, unchanged)
    rec("CALM-LOUDNESS", loud["integrated_lufs"] is not None and abs(loud["integrated_lufs"] - dv["lufs_target"]) <= dv["tolerance_lu"] and (loud["true_peak_dbtp"] or 0) <= dv["true_peak_max_dbtp"], f"{loud}")
    # C9 phone-first audio checks, on the stems of the mix and the AAC that was actually delivered (a missing stem is a failure, never a skip)
    try:
        import audio_checks as AC
        sd = ep.work / "audio" / "stems"
        if not (sd / "voice.wav").is_file():
            for cid in ("AUDIO-DIALOGUE-CLARITY", "AUDIO-MONO", "AUDIO-PEAK"):
                rec(cid, False, "audio/stems is missing: run `audio` first (the legacy chain keeps no stems, so a legacy episode fails here on purpose)")
        else:
            final = ep.work / "audio" / "final.wav"
            ff(["-i", ep.out, "-vn", "-c:a", "pcm_f32le", "-ar", "48000", final])
            afails, ametrics = AC.run_checks(sd, final)
            write_json(ep.work / "audio" / "checks.json", {"fails": afails, "metrics": ametrics})
            for cid in ("AUDIO-DIALOGUE-CLARITY", "AUDIO-MONO", "AUDIO-PEAK"):
                mine = [b.split(" ", 1)[1] for b in afails if b.startswith(cid + " ")]
                rec(cid, not mine, "; ".join(mine[:3]) or {"AUDIO-DIALOGUE-CLARITY": f"voice over music+sfx on a phone simulation: median {ametrics['dialogue_clarity']['median_db']} dB, weakest tenth {ametrics['dialogue_clarity']['p10_db']} dB",
                                                         "AUDIO-MONO": f"mono fold-down loses {ametrics['mono']['mono_loss_lu']} LU, correlation p05 {ametrics['mono']['corr_p05']}",
                                                         "AUDIO-PEAK": f"true peak {ametrics['peak']['true_peak_dbtp']} dBTP, {ametrics['peak']['clipped_samples']} clipped samples"}[cid])
    except ImportError:
        rec("AUDIO-DIALOGUE-CLARITY", False, "audio_checks.py not available")
    r = ff(["-i", ep.out, "-vn", "-af", f"silencedetect=n=-45dB:d={SILENCE_MAX_S}", "-f", "null", "-"], check=False)
    gaps = re.findall(r"silence_duration: ([\d.]+)", r.stderr)
    rec("CALM-NO-SILENCE", not gaps, f"{len(gaps)} gap(s) over {SILENCE_MAX_S} s")
    cp = sorted(caps["captions"], key=lambda c: c["start"])
    rec("CALM-ONE-PLATE", all(b["start"] >= a["end"] - 1e-6 for a, b in zip(cp, cp[1:])), f"{len(cp)} plates, never two at once")
    import cap_shaping
    shp = cap_shaping.shaping_problems([{"words": G.strip_gloss(c["text"]).split(), "active": c.get("active")} for c in cp], [])
    shp += [f"plate '{c['text']}' seam_ratio {c.get('seam_ratio')} over {cap_shaping.SEAM_MAX}" for c in cp if c.get("seam_ratio") is None or c["seam_ratio"] > cap_shaping.SEAM_MAX]
    rec("CAP-ARABIC-SHAPING", not shp, "; ".join(shp[:3]) or f"{len(cp)} plates: whole words, joining intact, outline never cuts a letter (max seam {max((c['seam_ratio'] for c in cp), default=0)})")
    script_lines = read_json(ep.script_p)["lines"]
    shown_lines = {l["id"]: {**l, "text": display_text(l["text"])} for l in script_lines}
    recomputed = {}      # the voice's word times, recomputed from the takes and the timeline, independent of what the plates stored
    for _, ln_it in _spoken(tl["items"]):
        take = ep.take(ln_it["line"])
        lw = shown_lines[ln_it["line"]]["text"].split()
        if take.is_file() and lw:
            wt, _m = CS.syllable_weights(" ".join(lw), shown_lines[ln_it["line"]].get("tts_text"))
            recomputed[ln_it["line"]] = [(ln_it["voice_t0"] + a_, ln_it["voice_t0"] + b_) for a_, b_ in word_timing(take, lw, wt)]
    fs = CS.check_plates(cp, shown_lines, recomputed)
    rec("CAP-FULL-SENTENCE", not [x for x in fs if x.startswith("CAP-FULL-SENTENCE")],
        "; ".join(x for x in fs if x.startswith("CAP-FULL-SENTENCE"))[:600] or f"{len(cp)} plates: every plate shows a whole sentence or clause (at most {CS.UNIT_WORDS_MAX} words, {CS.UNIT_LINES_MAX} lines), exactly one whole word highlighted, in order, within {CS.SYNC_TOL_S} s of the voice ({len(recomputed)} lines recomputed)")
    rec("CAP-READ-TIME", not [x for x in fs if x.startswith("CAP-READ-TIME")],
        "; ".join(x for x in fs if x.startswith("CAP-READ-TIME"))[:600] or f"every sentence stays up at least {CS.READ_BASE_S} s + {CS.READ_PER_WORD_S} s a word, and holds {CS.TAIL_S} s after its line when the next plate allows")
    rec("CAP-READING-SPEED", not [x for x in fs if x.startswith("CAP-READING-SPEED")],
        "; ".join(x for x in fs if x.startswith("CAP-READING-SPEED"))[:600] or f"every plate stays up at least max({CS.READ_MIN_S} s, characters / {CS.READ_CPS:g} cps) (a judgement rate, cap_sentence.READ_CPS), counting the time its meaning is carried on")
    tl_ids = {it["id"]: it for it in tl["items"]}
    fb = face_boxes_by_item(ep, tl)
    ff_ = CF.check_plates(cp, lambda p: _face_boxes_for_plate(tl, fb, p))
    nfaces = sum(len(v) for v in fb.values())
    rec("CAP-FACE-CLEAR", not ff_, "; ".join(ff_[:3]) or f"{len(cp)} plates clear of {nfaces} face boxes (face {CF.FACE_W_M} x {CF.FACE_H_M} m + {CF.FACE_PAD_PX} px, from each shot's rig trace; overlaps under {FACE_GRACE_S} s of a join ignored); {sum(1 for c in cp if c.get('moved_for_face'))} plates were moved to get there")
    series_ = read_json(ep.script_p).get("series") or ep.series
    glossary = G.load(ep.root, series_)
    lex = G.lexicon(ep.root, series_)
    by_id = {l["id"]: l for l in script_lines}
    gp = G.check_captions(cp, by_id, glossary)
    gp += [x for k, v in _visible_strings(plan) for x in G.check_text(str(v), None, glossary, where=f"{k} ")]
    gp += G.check_script_tags(script_lines, glossary)
    gp += [x for c in cp for x in G.check_foreign(c["text"], (by_id.get(c["line"]) or {}).get("speaker"), glossary, lex["foreign_keys"], f"plate {c['line']} ", lex["loanwords"])]
    gp += [x for k, v in _foreign_checked_strings(plan) for x in G.check_foreign(str(v), None, glossary, lex["foreign_keys"], f"{k} ", lex["loanwords"])]
    rec("CAP-FOREIGN-GLOSS", not gp, "; ".join(gp[:3]) or f"{len(glossary)} glossary words and {sum(len(G.foreign_tags(l)) for l in script_lines)} writer tags: every one shown carries its «(meaning)», every own-language word of a speaker is tagged")
    vis_words = [w for l in script_lines for w in shown_lines[l["id"]]["text"].split()] + [w for k, v in _visible_strings(plan) for w in re.split(r"[\s#_]+", str(v)) if re.search("[ء-ي]", w)]
    odd = G.review_words(vis_words, lex["corpus"], glossary, lex["arabic_ok"], lex["names"])      # C11: the review list; the lexicon excludes the episode scripts, so a script cannot vouch for its own words
    write_json(ep.work / "review" / "arabic-words.json", {"episode": ep.id, "note": "caption and post-caption words the series bibles never used: say Arabic (glossary.json arabic_words), a name (names), or add a glossary entry", "words": odd})
    rec("CAP-ARABIC-REVIEW", True, (f"{len(odd)} caption word(s) the series text has never used, for a human to read (may be fine): {' '.join(odd[:12])}") if odd else "every caption word is a word the series text already uses or a glossary word")
    if odd:
        checks[-1]["warning"] = f"words not recognised as series Arabic: {' '.join(odd[:12])}"
    rec("CALM-PLATE-SAFE", all(SAFE[0] <= c["x"] and c["x"] + c["w"] <= SAFE[2] and SAFE[1] <= c["y"] and c["y"] + c["h"] <= SAFE[3] + 100 for c in cp), "inside the Reels safe area")
    huds = read_json(ep.hud_p)["hud"]
    recap_tag = None
    rp = ep.root / "work" / "shots" / f"{ep.id}-recap" / "calm.json"
    if tl.get("episode_label") and rp.is_file():
        recap_tag = ((read_json(rp).get("card") or {}).get("text") or {}).get("tag")
    hp = hud_problems(tl, huds, recap_tag)
    rec("CALM-HUD", not hp, "; ".join(hp[:3]) or ("a HUD plate covers every story scene" + (f"; the first one carries the series strip «{tl['episode_label']}» for {tl.get('strip_s', STRIP_S):g} s and the recap card says the same" if tl.get("episode_label") else "")))
    hk = hook_3s_problems(tl, plan)
    rec("CALM-HOOK-3S", not hk, "; ".join(hk) or f"the first voiced line or declared story event starts before {HOOK_S:g} s ({min([ln['voice_t0'] for _, ln in _spoken(tl['items'])] or [0]):.2f} s)")
    if algo_on(plan):       # DESIGN.md 2.4 and 2.6, from E02: the follow line is a statement, the cover still exists
        fp = ep.root / "work" / "shots" / f"{ep.id}-follow" / "calm.json"
        fline = ((read_json(fp).get("card") or {}).get("text") or {}).get("line") if fp.is_file() else None
        want = follow_card_line(plan)
        fprob = ([f"no follow card shot at {fp}"] if fline is None else CC.ask_problems(fline, "follow card line", False)) + ([f"the follow card says «{fline}», not «{want}»"] if fline is not None and fline != want else [])
        rec("CALM-FOLLOW-LINE", not fprob, "; ".join(fprob[:3]) or f"the follow card says «{fline}»")
        cp_ = ep.work / "cover.png"
        cprob = []
        if not cp_.is_file():
            cprob.append("cover.png is missing next to the episode (assemble writes it)")
        else:
            from PIL import Image
            if Image.open(cp_).size != (W, H):
                cprob.append(f"cover.png is {Image.open(cp_).size}, not {W}x{H}")
        rec("CALM-COVER", not cprob, "; ".join(cprob) or "cover.png 1080x1920 (DESIGN.md 2.6)")
        # R-501 (the owner 2026-10-28): the first frame is the grid poster, not black (it is the hook, and the Reels grid tile when no cover is sent)
        if cp_.is_file():
            f0ok, f0d = GP.frame0_check(ep.out, cp_)
            rec("COVER-FRAME0", f0ok, f0d)
        else:
            rec("COVER-FRAME0", False, "no cover.png to compare frame 0 with")
    # the small NJ mark (the owner 2026-10-25): in the delivered file, and clear of every plate, HUD plate, face and card text
    wf, wmet = WM.present_problems(ep.out, d, ep.work / "watermark.json")
    rec("WATERMARK-PRESENT", not wf, "; ".join(wf[:3]) or f"the NJ mark shows on {wmet['share_present']:.0%} of {wmet['decoded']} sampled frames (median correlation {wmet['ncc_median']}); top-right {WM.rect()}, opacity {WM.OPACITY}")
    wsc = json.loads((ep.work / "watermark.json").read_text(encoding="utf-8")) if (ep.work / "watermark.json").is_file() else {}
    all_faces = [{**b, "what": f"face {k}"} for k, v in fb.items() for b in v]
    ctexts, cmissing = card_text_boxes(ep, tl)
    wc = cmissing + WM.clear_problems(wsc.get("rect"), [{"x": c["x"], "y": c["y"], "w": c["w"], "h": c["h"], "what": f"«{c['text'][:14]}»"} for c in caps["captions"]],
                           [{"x": h["x"], "y": h["y"], "w": h["w"], "h": h["h"], "what": f"HUD {h['id']}"} for h in huds if h.get("w")], all_faces, ctexts)
    rec("WATERMARK-CLEAR", not wc, "; ".join(wc[:3]) or f"the mark's rect clears {len(caps['captions'])} caption plates, {len(huds)} HUD plates, {len(all_faces)} face boxes, the card text and the phone UI zones")
    if recap_expected(plan):
        rec("CALM-RECAP-FIRST", tl["items"][0]["id"] == "recap" and tl["items"][0]["dur"] <= 3.0 + 1e-6, "the recap card opens the episode")
    else:
        rec("CALM-RECAP-FIRST", tl["items"][0]["kind"] == "scene" and tl["items"][0]["t0"] == 0 and not any(i["id"] == "recap" for i in tl["items"]),
            f"{plan.get('episode')} has no vote to recap (recaps start at E{RECAP_FROM_EPISODE:02d}): the story opens at 0 s")
    import calm_intro      # C10: every character's first appearance is followed by an intro_freeze, entered by the dramatic cut and left by a declared cut
    imeas = {}
    for it in tl["items"]:
        if it.get("kind") == "intro":
            mp = ep.root / "work" / "shots" / it["shot"] / "out" / "intro-measure.json"
            imeas[it["id"]] = read_json(mp) if mp.is_file() else None
    ip = calm_intro.episode_problems(plan, tl, imeas)
    intro_items = [it for it in tl["items"] if it.get("kind") == "intro"]
    rec("CALM-INTRO", not ip, "; ".join(x.split(" ", 1)[1] for x in ip[:3]) or (f"{len(intro_items)} character(s) introduced at their first appearance ("
        + ", ".join(it["character"] + " after " + it["after"] for it in intro_items) + "); each frozen, isolated by a grey glow, named in graffiti"))
    rec("CALM-TWO-CHOICES", bool(plan["choice"].get("choice1")) and bool(plan["choice"].get("choice2")), "two choices on the choice card")
    try:      # C3 + C4 + C5: every transition a sound and a visual, every prop and hand action foley, the choice sequence pops with the narrator
        import calm_sfx
        sfx_p = ep.work / "sfx.json"
        bad = calm_sfx.check(read_json(sfx_p), plan, tl) if sfx_p.is_file() else ["CALM-TRANSITION-SFX sfx.json is missing: run `audio` first"]
        for cid in ("CALM-TRANSITION-SFX", "CALM-FOLEY", "CALM-CHOICE-SFX", "CALM-INTRO-SFX"):
            mine = [b.split(" ", 1)[1] for b in bad if b.startswith(cid + " ")]
            rec(cid, not mine, "; ".join(mine[:3]) or "ok")
    except ImportError:
        rec("CALM-TRANSITION-SFX", False, "calm_sfx.py not available")
    sl_ = read_json(ep.script_p)["lines"]
    if format_v2(plan):      # format v2 (the owner 2026-10-28), from E03 on
        spk = {l["id"]: l.get("speaker") for l in sl_}
        nshare = narrator_share([(spk.get(ln["line"]), wav_seconds(ep.take(ln["line"]))) for it, ln in _spoken(tl["items"]) if it.get("id") != "choice"])   # the vote card is the narrator's by role (the owner 2026-10-28): not counted
        rec("NARRATOR-SHARE", nshare <= NARRATOR_SHARE_MAX + 1e-9, f"the narrator is {nshare:.0%} of the placed voice time (at most {NARRATOR_SHARE_MAX:.0%}): recap, night links and the vote question only")
        dl = dialogue_problems(read_json(ep.script_p))
        rec("DIALOGUE-LINES", not dl, "; ".join(x.split(" ", 1)[1] for x in dl[:2]) or "10 to 15 character lines, at least one exchange")
        evp = event_problems(plan)
        rec("EVENTS", not evp, "; ".join(x.split(" ", 1)[1] for x in evp[:2]) or "2 to 5 shown events, every night has one")
    try:
        import qg_checks as qc
        pl = {"lines": [{"start": ln["voice_t0"], "dur": wav_seconds(ep.take(ln["line"]))} for it, ln in _spoken(tl["items"])],
              "intro_s": sum(float(it.get("dur") or 0.0) for it in tl["items"] if it.get("kind") == "intro")}      # intro_freeze time is not counted in voice coverage (qg_checks.check_calm_declared)
        sl = episode_shotlist(ep, tl, plan)
        end = {"choices": [plan["choice"]["choice1"], plan["choice"]["choice2"]]}
        declared = qc.check_calm_declared(pl, {"captions": [{**c, "line": c["line"]} for c in cp]}, end, sl, tl["total_s"])
        for x in declared:
            checks.append({"id": (re.search(r"\[([A-Z0-9-]+)\]", x) or [0, "CALM-DECLARED"])[1], "status": "fail", "detail": x})
            fails.append(x)
        if not any("[CALM-VOICE-COVERAGE]" in x for x in declared):      # all placed voice (narrator and characters) covers >= 0.85 of the runtime
            checks.append({"id": "CALM-VOICE-COVERAGE", "status": "pass", "detail": f"placed voice covers at least {qc.CALM['voice_share_min']:.0%} of the runtime, any speaker"})
        if not skip_render:
            r = subprocess.run(["uv", "run", str(TOOLS / "quality_gate.py"), "calm", str(ep.out), "--timeline", str(ep.timeline_p), "--json", str(ep.work / "calm-render.json"), "--quiet"], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", env=ENV, cwd=ep.root)
            ok = r.returncode == 0
            checks.append({"id": "CALM-RENDER", "status": "pass" if ok else "fail", "detail": (r.stdout or "")[-600:]})
            if not ok:
                fails += [l for l in (r.stdout or "").splitlines() if l.startswith("FAIL")] or ["CALM-RENDER failed"]
    except ImportError:
        checks.append({"id": "CALM-DECLARED", "status": "skip", "detail": "qg_checks calm functions not available"})
        skip_render = True
    rep = {"episode": ep.id, "profile": "calm", "verdict": "FAIL" if fails else "PASS", "complete": not skip_render, "checks": checks, "fails": fails,
           "warnings": [c["warning"] for c in checks if c.get("warning")]}
    write_json(ep.gate_p, rep)
    if fails:
        raise Fail(fails[0].split(" ", 1)[0].replace("FAIL", "").strip() or "CALM-GATE", "; ".join(fails[:4]))
    return {"verdict": "PASS", "checks": len(checks)}


STAGES = {"plan": stage_plan, "captions": stage_captions, "audio": stage_audio, "assemble": stage_assemble, "gate": stage_gate}


def record_stage(ep: Ep, name: str) -> None:
    """Leave a stage record in work/episodes/<ep>/STATE.json (the shot engine's format: stages.<name>.at). Root cause (E01C, 2026-10-25): a calm episode had no STATE.json, so
    `heal.py guard` could not tell a re-run of the gate (which rewrites gate/report.json) from a hand edit and refused every honest rebuild. The record proves the re-run; the guard is unchanged."""
    p = ep.work / "STATE.json"
    try:
        st = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    except ValueError:
        st = {}
    st.setdefault("episode", ep.id if hasattr(ep, "id") else str(ep.work.name))
    st.setdefault("stages", {})[name] = {"status": "ok", "kind": "calm", "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    p.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[0] not in list(STAGES) + ["all"]:
        print(__doc__)
        return 2
    try:
        ep = Ep(argv[1])
        order = list(STAGES) if argv[0] == "all" else [argv[0]]
        for name in order:
            res = STAGES[name](ep) if name != "gate" else stage_gate(ep, "--skip-render-gate" in argv)
            record_stage(ep, name)
            print(f"[{name}] ok {res}")
        return 0
    except Fail as e:
        print(e)
        return 1
