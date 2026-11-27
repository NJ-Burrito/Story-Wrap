# qg_checks.py part 4 of 4: executed into the qg_checks module namespace by qg_checks.py (a pure move).
# ---------------------------------------------------------------- SEAM (R-381, the owner F11): one connected silhouette
# DEFAULT, uncalibrated: no approved line-art mask exists yet. Calibrate on the first hand-approved render (gate-spec K).
SEAM = {"r_heads": 0.12,        # joint disc radius as a share of head_unit_px (a seam may give r_px)
        "r_px_fallback": 14.0,  # disc radius when neither r_px nor head_unit_px is known
        "cross_frac": 0.6,      # a stroke crosses when its extent perpendicular to the bone >= this share of the disc diameter
        "head_neck_cross_frac": 0.45,   # stricter for head-neck (the head must join through a neck or garment)
        "max_along_ratio": 0.6, # ...and its extent along the bone is <= this share of the perpendicular extent (not a limb outline)
        "ink_level": 127}       # mask pixel value above which a pixel is ink (alpha or luma)

def _unit(v):
    n = math.hypot(v[0], v[1])
    return (v[0] / n, v[1] / n) if n > 1e-9 else None

def seam_axis(seam: dict):
    if seam.get("axis"):
        return _unit(seam["axis"])
    if seam.get("from") and seam.get("to"):
        return _unit((seam["to"][0] - seam["from"][0], seam["to"][1] - seam["from"][1]))
    return None

def crossing_strokes(ink, centre, radius, axis, cross_frac, max_along=SEAM["max_along_ratio"]) -> list[dict]:
    """ink: 2-D bool array in mask pixels. Returns the ink strokes inside the disc (centre, radius) that run across the bone
    axis: perpendicular extent >= cross_frac * diameter and along-axis extent <= max_along * perpendicular extent."""
    import numpy as np
    from scipy import ndimage as ndi
    h, w = ink.shape
    cx, cy = centre
    x0, x1 = max(int(math.floor(cx - radius)), 0), min(int(math.ceil(cx + radius)) + 1, w)
    y0, y1 = max(int(math.floor(cy - radius)), 0), min(int(math.ceil(cy + radius)) + 1, h)
    if x1 <= x0 or y1 <= y0:
        return []
    yy, xx = np.mgrid[y0:y1, x0:x1]
    sub = ink[y0:y1, x0:x1] & (((xx - cx) ** 2 + (yy - cy) ** 2) <= radius * radius)
    lab, n = ndi.label(sub, structure=np.ones((3, 3)))
    ax, ay = axis
    out = []
    for i in range(1, n + 1):
        m = lab == i
        dx, dy = xx[m] - cx, yy[m] - cy
        along = dx * ax + dy * ay
        perp = -dx * ay + dy * ax
        pe, ae = float(perp.max() - perp.min() + 1), float(along.max() - along.min() + 1)
        if pe >= cross_frac * 2 * radius and ae <= max_along * pe:
            out.append({"perp_px": round(pe, 1), "along_px": round(ae, 1), "pixels": int(m.sum())})
    return out

def _declared_overlap(seam: dict, overlaps) -> bool:
    ids = {str(o) for o in (overlaps or [])}
    a, b = (seam.get("parts") or ["", ""])[:2]
    return seam.get("id") in ids or f"{a}|{b}" in ids or f"{b}|{a}" in ids

def seam_frame_issues(ink, scale: float, seams: list, overlaps, head_unit_px, label: str) -> list[str]:
    """One frame: SEAM-CROSS for body seams, SEAM-HEADNECK for the head join. scale = mask px per canvas px."""
    f = []
    for s in seams or []:
        axis = seam_axis(s)
        if axis is None or not s.get("at"):
            continue                                   # no bone direction: cannot tell a seam line from a limb outline
        kind = s.get("kind", "joint")
        r = float(s.get("r_px") or (SEAM["r_heads"] * head_unit_px if head_unit_px else SEAM["r_px_fallback"]))
        centre = (s["at"][0] * scale, s["at"][1] * scale)
        name = s.get("id") or "|".join(s.get("parts", []))
        if kind == "head-neck":
            if not s.get("via"):
                f.append(F("SEAM-HEADNECK", f"{label} seam {name}: no neck shape or garment declared in 'via'; a round head must not sit on the body with an outline between (R-381, F11)"))
            hits = crossing_strokes(ink, centre, r * scale, axis, SEAM["head_neck_cross_frac"])
            if hits:   # overlaps[] cannot waive the head-neck join
                f.append(F("SEAM-HEADNECK", f"{label} seam {name}: an outline of {hits[0]['perp_px']} px cuts the head-to-neck join; the head must connect through the neck or garment shape (R-381, F11)"))
            continue
        if _declared_overlap(s, overlaps):
            continue
        hits = crossing_strokes(ink, centre, r * scale, axis, SEAM["cross_frac"])
        if hits:
            f.append(F("SEAM-CROSS", f"{label} seam {name}: {len(hits)} stroke(s) ({hits[0]['perp_px']} px wide across the joint) cut the silhouette and no overlap/fold is declared here (R-381, F11)"))
    return f

def rig_seams(trace: dict, base: Path | None = None, max_report: int = 6) -> list[str]:
    """Needs per frame: line_mask (PNG, ink strokes only, canvas-aligned), seams[], optional overlaps[]. Frames without them are skipped;
    a trace that declares seams but yields no readable mask fails SEAM-NODATA."""
    try:
        from PIL import Image
        import numpy as np
    except ImportError:
        return [F("SEAM-NODATA", "numpy/PIL missing")]
    cw = float((trace.get("canvas") or {}).get("w") or 1080)
    f, seen, read = [], 0, 0
    for cid, ch in trace.get("characters", {}).items():
        for fr in _frames(ch):
            if not fr.get("seams"):
                continue
            seen += 1
            p = fr.get("line_mask")
            pp = (Path(p) if Path(p).is_absolute() or base is None else Path(base) / p) if p else None
            if pp is None or not pp.exists():
                continue
            im = Image.open(pp)
            alpha = np.asarray(im.getchannel("A")) if im.mode in ("RGBA", "LA") else None
            a = alpha if alpha is not None and alpha.min() < 255 else np.asarray(im.convert("L"))
            read += 1
            f += seam_frame_issues(a > SEAM["ink_level"], im.size[0] / cw, fr["seams"], fr.get("overlaps"),
                                   ch.get("head_unit_px"), f"{cid} frame {fr['f']}")
    if seen and not read:
        f.append(F("SEAM-NODATA", f"{seen} frames declare seams but no line_mask PNG could be read: the renderer must export the line-art mask (R-381)"))
    if len(f) > max_report:
        f = f[:max_report] + [F("SEAM-CROSS", f"... {len(f) - max_report} more seam faults")]
    return f

# ---------------------------------------------------------------- PLAYBACK (R-382, rca-playback.md): previews play the gated video
PLAYBACK = {"p99_ms": 50.0, "long_task_ms": 100.0, "loops": 2}   # DEFAULT, from rca-playback.md (not calibrated on a real preview)

from html.parser import HTMLParser

_VOID = {"br", "img", "input", "meta", "link", "source", "hr", "canvas", "video", "iframe", "area", "col", "embed", "wbr"}

class _PanelScan(HTMLParser):
    """Collects, per section.panel, its canvases, videos and iframes, plus every inline script of the page."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.panels, self.scripts = [], []
        self._cur, self._depth, self._buf, self._in_script, self._details = None, 0, [], False, []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "script" and not a.get("src"):
            self._in_script, self._buf = True, []
        if tag == "section" and "panel" in (a.get("class") or "").split():
            self._cur = {"id": a.get("data-tab") or a.get("id") or f"panel{len(self.panels)}", "canvases": [], "videos": [], "iframes": []}
            self._depth = 0
            self.panels.append(self._cur)
        if tag == "details":
            self._details.append("open" in a)
        if self._cur is None:
            return
        if tag not in _VOID:
            self._depth += 1
        # a canvas is a live opt-in when it is hidden, inside a closed <details>, or marked data-live
        optin = (not all(self._details)) or "hidden" in a or a.get("data-live") is not None
        if tag == "canvas":
            self._cur["canvases"].append({"id": a.get("id", ""), "optin": optin})
        elif tag == "video":
            self._cur["videos"].append({"src": a.get("src") or "", "hidden": "hidden" in a})
        elif tag == "source" and self._cur["videos"] and not self._cur["videos"][-1]["src"]:
            self._cur["videos"][-1]["src"] = a.get("src", "")
        elif tag == "iframe":
            self._cur["iframes"].append(a.get("data-src") or a.get("src") or "")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag == "script":
            self.scripts.append("".join(self._buf)); self._in_script = False
        if tag == "details" and self._details:
            self._details.pop()
        if self._cur is not None and tag not in _VOID:
            self._depth -= 1
            if self._depth <= 0:
                self._cur = None

    def handle_data(self, d):
        if self._in_script:
            self._buf.append(d)

def _autoplays(canvas_id: str, scripts: list) -> bool:
    """True when a script that names this canvas also runs an animation loop (rAF / setInterval / renderAt)."""
    for s in scripts:
        touches = bool(canvas_id) and re.search(r"""['"]#?%s['"]""" % re.escape(canvas_id), s) is not None
        if touches and re.search(r"requestAnimationFrame|setInterval\s*\(|renderAt\s*\(", s):
            return True
    return False

PREVIEW_MAX_TABS = 4

def check_preview_static(html: str, label: str = "preview") -> list[str]:
    """PLAYBACK-VIDEO: every tab that has a canvas renderer must also play a recorded <video src=...> (default view).
    PLAYBACK-AUTOPLAY: no canvas that is visible by default may be driven by an animation loop. Hidden, closed-<details>
    and data-live canvases are opt-in editors and are allowed."""
    sc = _PanelScan(); sc.feed(html); sc.close()
    f = []
    for p in sc.panels:
        if not p["canvases"]:
            continue
        if not [v for v in p["videos"] if v["src"] and not v["hidden"]]:
            f.append(F("PLAYBACK-VIDEO", f"{label} tab '{p['id']}' paints a canvas but plays no recorded <video src=...>; the preview must be the gated render (R-382)"))
        for c in p["canvases"]:
            if not c["optin"] and _autoplays(c["id"], sc.scripts):
                f.append(F("PLAYBACK-AUTOPLAY", f"{label} tab '{p['id']}' canvas #{c['id'] or '?'} is a live per-frame painter shown by default (rAF/setInterval/renderAt); put it behind data-live or a closed <details> and show the video (R-382)"))
    n = max(len(re.findall(r'\{\s*id:\s*"', (re.search(r"const TABS\s*=\s*\[(.*?)\];", html, re.S) or [0, ""])[1] if re.search(r"const TABS\s*=\s*\[(.*?)\];", html, re.S) else "")), len(sc.panels))
    if n > PREVIEW_MAX_TABS:
        f.append(F("PREVIEW-MAX-TABS", f"{label} has {n} tabs; at most {PREVIEW_MAX_TABS} (CLAUDE.md): move older tabs to previews/archive/index-<date>.html"))
    return f

_DYN_JS = """async (loops) => {
  const out = {frames: [], long: [], errors: []};
  window.addEventListener('error', e => out.errors.push(String(e.message)));
  try { new PerformanceObserver(l => l.getEntries().forEach(e => out.long.push(e.duration))).observe({entryTypes: ['longtask']}); } catch (e) {}
  const v = document.querySelector('video'); if (v) { v.muted = true; try { await v.play(); } catch (e) {} }
  const dur = v && isFinite(v.duration) ? v.duration * 1000 * loops : 9000 * loops;
  let last = performance.now(); const t0 = last;
  await new Promise(res => { const step = now => { out.frames.push(now - last); last = now; now - t0 < dur ? requestAnimationFrame(step) : res(); }; requestAnimationFrame(step); });
  return out; }"""

def check_preview_dynamic(url: str, loops: int = PLAYBACK["loops"]) -> list[str]:
    """Optional (--dynamic): cold load, two loops, foreground window. p99 frame <= 50 ms, no long task > 100 ms, no exception.
    Needs Playwright plus a browser; headless rAF is throttled, so it opens a real window. Not run in the test suite."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError("playwright not installed: dynamic playback check not run (uv run --with playwright ...)")
    errs = []
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=False, args=["--enable-gpu-rasterization", "--ignore-gpu-blocklist"])
        pg = b.new_page(viewport={"width": 540, "height": 960})
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        pg.goto(url, wait_until="load"); pg.bring_to_front()
        r = pg.evaluate(_DYN_JS, loops); b.close()
    return dynamic_issues(r["frames"], r["long"], r["errors"] + errs)

def dynamic_issues(frame_ms: list, long_tasks: list, errors: list) -> list[str]:
    f = []
    if frame_ms:
        s = sorted(frame_ms); p99 = s[min(int(math.ceil(0.99 * len(s))) - 1, len(s) - 1)]
        if p99 > PLAYBACK["p99_ms"]:
            f.append(F("PLAYBACK-FRAMETIME", f"p99 frame time {p99:.0f} ms > {PLAYBACK['p99_ms']:.0f} ms over {len(s)} frames (R-382)"))
    big = [d for d in long_tasks if d > PLAYBACK["long_task_ms"]]
    if big:
        f.append(F("PLAYBACK-LONGTASK", f"{len(big)} long task(s), worst {max(big):.0f} ms > {PLAYBACK['long_task_ms']:.0f} ms (R-382)"))
    if errors:
        f.append(F("PLAYBACK-ERROR", f"page raised {len(errors)} exception/console error(s): {errors[0][:120]} (R-382)"))
    return f



# ================================================================== CALM format profile (the owner 2026-10-24, CLAUDE.md "Calm format")
# His pacing, our art. A shot spec declares "format": "calm"; a shotlist declares "profile": "calm" (its own `format` key is the schema id
# "shotlist/1"). Anything else is "premium" and keeps the never-a-slideshow thresholds untouched. The art checks (LOOK2D, SEAM, joints, hands,
# shadows, no-touch, no-tashkeel) apply to both formats.
# BAND = (lo, hi): lo is a floor (the format needs it: holds are expected), hi a ceiling (restlessness fails). None = open on that side.
# Every band below was MEASURED with `quality_gate.py calm` on the 10 stickman story reels in work/stickman/ and checked against E01 run 1; the table
# is kb/quality/gate-spec.md section H. A value marked DEFAULT has no harvested sample behind it (the reels carry no caption or wrapper data).
FORMATS = ("premium", "calm")

def format_of(obj) -> str:
    """'calm' or 'premium' (default): a spec's `format`, or a shotlist / plan `profile`."""
    if not isinstance(obj, dict):
        return "premium"
    v = obj.get("profile") if obj.get("profile") in FORMATS else obj.get("format")
    return v if v in FORMATS else "premium"

CALM = {
    # --- measured on the video (quality_gate.py calm)
    "shot_len_s":       (1.8, 6.0),   # average shot length in seconds = duration / (scene changes + 1)
    "cuts_per_min":     (8.0, 30.0),   # ffmpeg scene > 0.08 changes per minute (soft joins count)
    "hold_share":       (0.05, 0.25),   # share of runtime frozen in holds >= 0.5 s (freezedetect)
    "motion_coverage":  (0.08, 0.35),   # mean share of 16 px blocks changing per moving step
    "motion_clusters":  (2.0, 8.0),   # independent motion clusters per moving step: the measured stand-in for "subjects in frame"
    "longest_hold_s":   (None, 3.0),   # longest single hold in seconds (freezedetect): a hold is a deliberate beat, not a stall
    "audio_active":     (0.80, None),   # share of 20 ms frames above -40 dBFS: voice + bed never drop out
    "loudness_i":       (-15.0, -13.0),   # integrated LUFS
    "lra":              (None, 5.0),   # loudness range LU
    # --- declared data (captions.json, plan.json, end.json, shotlist): the reels cannot show these
    "caption_words_max": 8,             # the owner 2026-10-25 (C7) replaces "1 to 3 words a plate" (recipe section 3): a plate is a whole sentence or clause, at most 8 words on 2 lines (cap_sentence.UNIT_WORDS_MAX)
    "caption_lines_max": 2,
    "caption_font_px_min": 90,          # DEFAULT: recipe estimates the caption at about 7 % of frame height (134 px at 1920); 90 px at 1080 wide is the floor
    "voice_share_min":  0.85,           # DEFAULT: union of the placed voice takes (any speaker) / runtime; narrator share is NARRATOR-SHARE (calm_compose), format v2 2026-10-28
    "wrapper_parts":    ("recap", "day_card", "choice_card", "follow_card"),
    "recap_by_s":       3.0,            # recipe: recap hook 0 to 2.2 s
    "choice_last_s":    20.0,           # recipe: choice card at 66 s of 85 s, i.e. inside the last 20 s
    "subjects_max":     1,              # declared figures per shot: one subject per frame
}

def _band_fail(cid: str, v, band, label: str, unit: str = "") -> list[str]:
    lo, hi = band
    if v is None:
        return [F(cid, f"{label} not measured")]
    if lo is not None and v < lo:
        return [F(cid, f"{label} = {v}{unit} < {lo}{unit}: below the calm band {lo}..{hi}")]
    if hi is not None and v > hi:
        return [F(cid, f"{label} = {v}{unit} > {hi}{unit}: above the calm band {lo}..{hi}")]
    return []

# ---- declared transitions (E01C run, the owner's mix-v2 C3: flash, whoosh, ink wipes are DECLARED joins, not scene changes)
# Root cause of the false CALM-CUTRATE / CALM-SHOTLEN / CALM-HOLDS fails on E01C: the video detector (ffmpeg scene > 0.08) fires several times inside
# ONE declared transition (a flash or an ink wipe repaints the whole frame over 0.25 s), so 22 declared items read as 60 scene changes. The plan
# already says where every shot starts and where every transition runs, so the gate counts SHOTS from that list, ignores detector hits that fall
# inside a declared transition window, and measures holds per shot outside those windows. A detector hit OUTSIDE every window is an UNDECLARED
# change (a real cut nobody planned, a glitch) and still counts, so a restless episode is still caught.
TRANSITION_PAD_S = 0.10    # the detector's frame can sit a little outside the nominal overlap (the effect's first and last frames)
INNER_CUT_S = 0.16         # the crossfade of a cut inside the choice sequence's top half (calm_compose XD)


def declared_boundaries(timeline: dict) -> list[dict]:
    """Every declared shot boundary of an episode timeline as {t, a, b, kind}: t = the cut point, [a, b] = the transition window (padded).
    Between two items the overlap runs t0(next)..t1(prev); a hard join (no overlap) is a window of 2 pads around the join. Cuts the choice item
    declares inside its own split (`split.cuts`, seconds from the item start) are boundaries too."""
    items = sorted((timeline or {}).get("items", []), key=lambda i: i["t0"])
    out = []
    for prev, nxt in zip(items, items[1:]):
        a, b = nxt["t0"], prev["t1"]
        if b < a:
            a = b = (a + b) / 2
        out.append({"t": (a + b) / 2, "a": a - TRANSITION_PAD_S, "b": b + TRANSITION_PAD_S, "kind": "join"})
    for it in items:
        for c in (it.get("split") or {}).get("cuts", []):
            t = it["t0"] + float(c["t"])
            out.append({"t": t + INNER_CUT_S / 2, "a": t - TRANSITION_PAD_S, "b": t + INNER_CUT_S + TRANSITION_PAD_S, "kind": "inner"})
    return sorted(out, key=lambda x: x["t"])


def _merge_windows(windows):   # was `_merge`: the same name as the profile merger at the top of this file, which it shadowed (resolve_profile crashed: TypeError, 2 args)
    out = []
    for a, b in sorted(windows):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def _clip(spans, segs):
    """The parts of spans that lie inside segs (both lists of (a, b))."""
    out = []
    for a, b in spans:
        for c, d in segs:
            lo, hi = max(a, c), min(b, d)
            if hi > lo:
                out.append((lo, hi))
    return out


def declared_pacing(timeline: dict, dur: float, change_times: list, freeze_spans: list, hold_min_s: float = 0.5) -> dict:
    """Pacing metrics from the DECLARED shots. change_times = detector hits (s); freeze_spans = [(start, end)] of every freezedetect hold >= hold_min_s.
    Returns scene_changes (= declared + undeclared), declared_cuts, undeclared_changes, ignored_in_transitions, shot_len_s, shortest_shot_s,
    cuts_per_min, freeze_share_05s (held time / time outside transition windows), longest_hold_s, transition_s."""
    bd = declared_boundaries(timeline)
    win = _merge_windows([(x["a"], x["b"]) for x in bd])
    inside = lambda t: any(a <= t <= b for a, b in win)
    undeclared = [t for t in change_times if not inside(t)]
    cuts = len(bd) + len(undeclared)
    pts = sorted([0.0] + [x["t"] for x in bd] + list(undeclared) + [dur])
    lens = [b - a for a, b in zip(pts, pts[1:]) if b - a > 1e-6]
    segs, cur = [], 0.0                       # shots with their transition windows taken out
    for a, b in win:
        if a > cur:
            segs.append((cur, a))
        cur = max(cur, b)
    if cur < dur:
        segs.append((cur, dur))
    holds = [(a, b) for a, b in _clip(freeze_spans, segs) if b - a >= hold_min_s]
    open_s = sum(b - a for a, b in segs)
    held = sum(b - a for a, b in holds)
    return {"scene_changes": cuts, "declared_cuts": len(bd), "undeclared_changes": len(undeclared),
            "ignored_in_transitions": len(change_times) - len(undeclared),
            "shot_len_s": round(dur / (cuts + 1), 2), "shortest_shot_s": round(min(lens), 2) if lens else round(dur, 2),
            "cuts_per_min": round(cuts / max(dur, 1e-6) * 60, 1),
            "freeze_share_05s": round(held / max(open_s, 1e-6), 4), "freeze_holds_05s": len(holds),
            "longest_hold_s": round(max((b - a for a, b in holds), default=0.0), 2), "transition_s": round(dur - open_s, 2)}


def check_calm_render(m: dict) -> list[str]:
    """Video-measured calm checks. m = quality_gate.analyse_calm(...) metrics."""
    f: list[str] = []
    f += _band_fail("CALM-SHOTLEN", m.get("shot_len_s"), CALM["shot_len_s"], "average shot length", " s")
    f += _band_fail("CALM-CUTRATE", m.get("cuts_per_min"), CALM["cuts_per_min"], "shot changes per minute")
    f += _band_fail("CALM-HOLDS", m.get("freeze_share_05s"), CALM["hold_share"], "share of runtime held (>= 0.5 s)")
    f += _band_fail("CALM-HOLD-LONGEST", m.get("longest_hold_s"), CALM["longest_hold_s"], "longest single hold", " s")
    f += _band_fail("CALM-MOTION", m.get("motion_coverage"), CALM["motion_coverage"], "motion coverage")
    f += _band_fail("CALM-SUBJECTS", m.get("motion_clusters"), CALM["motion_clusters"], "independent motion clusters per step (subjects proxy)")
    if not m.get("has_audio", True):
        f.append(F("CALM-VOICE-COVERAGE", "no audio track: a calm episode needs voice (narrator and characters) that covers the runtime"))
    else:
        f += _band_fail("CALM-VOICE-COVERAGE", m.get("audio_active"), CALM["audio_active"], "audio-active share of runtime")
        f += _band_fail("CALM-LOUDNESS", m.get("loudness_i"), CALM["loudness_i"], "integrated loudness", " LUFS")
        f += _band_fail("CALM-LRA", m.get("lra"), CALM["lra"], "loudness range", " LU")
    return f

CALM_EVENT_CEILING = {"motion_coverage": 0.45, "motion_clusters": 10.0}   # format v2 (the owner 2026-10-28): a shot the plan marks as an `event` shows an action while a character speaks over it


def check_calm_shot(m: dict, event: bool = False) -> list[str]:
    """A single calm SHOT (quality_gate render --format calm): only the ceilings, restlessness fails. The floors (holds, shot length) belong to the whole episode.
    event=True (the plan's scene has an `event`): the action ceilings CALM_EVENT_CEILING apply instead; every other shot keeps the calm ones."""
    f: list[str] = []
    for cid, key, label in (("CALM-MOTION", "motion_coverage", "motion coverage"), ("CALM-SUBJECTS", "motion_clusters", "independent motion clusters per step (subjects proxy)")):
        hi = CALM_EVENT_CEILING[key] if event else CALM[key][1]
        v = m.get(key)
        if v is not None and hi is not None and v > hi:
            f.append(F(cid, f"{label} = {v} > {hi}: restless for the calm format"))
    return f

def _union_s(spans) -> float:
    tot, end = 0.0, None
    for a, b in sorted(spans):
        if end is None or a > end:
            tot += b - a; end = b
        elif b > end:
            tot += b - end; end = b
    return tot

def check_calm_declared(plan, caps, end, sl, total_s: float) -> list[str]:
    """Calm checks on declared data: plan.json lines, captions.json plates, end.json card, shotlist `wrapper` and per-shot `subjects`.
    Missing data fails, it is never skipped."""
    f: list[str] = []
    C = CALM
    plates = sorted((caps or {}).get("captions", []), key=lambda c: c.get("start", 0))
    if not plates:
        f.append(F("CALM-CAPTION-STYLE", "no caption plates declared"))
    else:
        from gloss import strip_gloss   # a bracketed «(meaning)» after a foreign word is an annotation under the plate, not a caption word (CLAUDE.md "Gloss foreign words")
        nwords = lambda c: len(strip_gloss(str(c.get("text", ""))).split())
        many = [f"{c.get('line', '?')}:{nwords(c)}" for c in plates if nwords(c) > C["caption_words_max"]]
        if many:
            f.append(F("CALM-CAPTION-STYLE", f"{len(many)} of {len(plates)} plates carry more than {C['caption_words_max']} words ({', '.join(many[:5])}): a calm caption is a whole sentence or clause of at most {C['caption_words_max']} words, the spoken word highlighted"))
        tall = [f"{c.get('line', '?')}:{c['n_lines']}" for c in plates if c.get("n_lines", 1) > C["caption_lines_max"]]
        if tall:
            f.append(F("CALM-CAPTION-STYLE", f"{len(tall)} plates run over {C['caption_lines_max']} lines ({', '.join(tall[:5])}): a sentence plate is two lines at most"))
        over = [f"{a.get('line')}/{b.get('line')}" for a, b in zip(plates, plates[1:]) if b.get("start", 0) < a.get("end", 0) - 1e-6]
        if over:
            f.append(F("CALM-CAPTION-STYLE", f"{len(over)} plate pair(s) on screen together ({', '.join(over[:4])}): one caption at a time"))
        small = [str(c.get("line", "?")) for c in plates if c.get("font_px_1080", 0) < C["caption_font_px_min"]]
        if small:
            f.append(F("CALM-CAPTION-STYLE", f"{len(small)} plates under {C['caption_font_px_min']} px at 1080 wide ({', '.join(small[:4])}): calm captions are big"))
    lines = (plan or {}).get("lines", [])
    spans = [(float(l["start"]), float(l["start"]) + float(l["dur"])) for l in lines if "start" in l and "dur" in l]
    # intro_freeze time is excluded from the coverage count, the way a title card is. The caller declares it as plan["intro_s"] (the summed length
    # of the timeline's intro items); coverage = placed voice seconds / (runtime - intro seconds). Every other silent gap still counts against the 0.85 floor.
    intro_s = max(0.0, float((plan or {}).get("intro_s") or 0.0))
    base = total_s - intro_s
    share = _union_s(spans) / base if base > 0 and spans else 0.0
    if share < C["voice_share_min"]:
        f.append(F("CALM-VOICE-COVERAGE", f"placed voice (narrator and characters, any speaker) covers {share:.2f} of the runtime (need >= {C['voice_share_min']}): silence is not the pacing"))
    wr = (sl or {}).get("wrapper") or {}
    ep_no, recap_from = (sl or {}).get("episode_no"), (sl or {}).get("recap_from")
    no_recap = isinstance(ep_no, int) and isinstance(recap_from, int) and ep_no < recap_from   # a recap recaps a vote: the shotlist declares the episode number and the first episode with a recap, and an episode before it opens on its story (the owner 2026-10-25); a shotlist that declares neither keeps the recap required
    parts = [p for p in C["wrapper_parts"] if not (no_recap and p == "recap")]
    if no_recap and "recap" in wr:
        f.append(F("CALM-WRAPPER", f"episode {ep_no} declares a recap card but recaps start at episode {recap_from}"))
    miss = [p for p in parts if not isinstance(wr.get(p), dict)]
    if miss:
        f.append(F("CALM-WRAPPER", f"wrapper part(s) not declared: {', '.join(miss)} (shotlist `wrapper`: recap, day_card, choice_card, follow_card, each {{t0, t1}} in seconds)"))
    else:
        t = lambda k, e: float(wr[k].get(e, -1))
        if not no_recap and not (0 <= t("recap", "t0") and t("recap", "t1") <= C["recap_by_s"] + 1e-6):
            f.append(F("CALM-WRAPPER", f"recap is {t('recap', 't0')}..{t('recap', 't1')} s: it must sit inside the first {C['recap_by_s']:g} s"))
        if total_s and t("choice_card", "t0") < total_s - C["choice_last_s"]:
            f.append(F("CALM-WRAPPER", f"choice card starts at {t('choice_card', 't0')} s: it belongs in the last {C['choice_last_s']:g} s of {total_s:.1f}"))
        if not t("follow_card", "t0") >= t("choice_card", "t0"):
            f.append(F("CALM-WRAPPER", "the follow card must come after the choice card"))
        if not 0 <= t("day_card", "t0") < t("choice_card", "t0"):
            f.append(F("CALM-WRAPPER", "the day card must come before the choice card"))
        if end is not None and len(end.get("choices", [])) != 2:
            f.append(F("CALM-WRAPPER", f"the choice card shows {len(end.get('choices', []))} choices (need exactly 2)"))
    big = [str(s.get("id", "?")) for s in (sl or {}).get("shots", []) if len(s.get("subjects", [])) > C["subjects_max"]]
    if big:
        f.append(F("CALM-SUBJECTS", f"shot(s) {', '.join(big[:6])} declare more than {C['subjects_max']} subject in `subjects`: one subject per frame"))
    return f
