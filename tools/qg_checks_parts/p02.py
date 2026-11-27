# qg_checks.py part 2 of 4: executed into the qg_checks module namespace by qg_checks.py (a pure move).
def rig_shoulder_clavicle(trace: dict) -> list[str]:
    """RIG-SHOULDER (R-341/R-342). The allowed shoulder point is a function of humeral elevation: x at the clavicle end
    (inward shift along the clavicle arc as it rises), y at the rest line minus the scapulohumeral lift (a voluntary shrug may add up to 0.2 head above it, never below). y is "up negative"
    as the tracer writes it. Rest line: `rest_shoulder_y_px` on the character, else the median of (y + model lift) over the
    lowest third of elevations. Frames with no `arm_elevation_deg` fall back to the old fixed clavicle line."""
    f = []
    for cid, ch in trace.get("characters", {}).items():
        hu = float(ch.get("head_unit_px", 0)) or 1.0
        frames = _frames(ch)
        rest = ch.get("rest_shoulder_y_px")
        if rest is None:
            smp = []
            for fr in frames:
                el = fr.get("arm_elevation_deg") or {}
                for s in ("L", "R"):
                    sh = (fr.get("anchors") or {}).get(f"shoulder_{s}")
                    if sh is not None and el.get(s) is not None:
                        smp.append((float(el[s]), sh[1] + shoulder_lift_model(float(el[s]), hu)))
            if smp:
                smp.sort(); low = [v for _, v in smp[:max(1, len(smp) // 3)]]
                low.sort(); rest = low[len(low) // 2]
        for fr in frames:
            an = fr.get("anchors") or {}
            if "torso_center" not in an or "torso_half_width_px" not in fr:
                continue
            hw = fr["torso_half_width_px"]
            for s in ("L", "R"):
                sh = an.get(f"shoulder_{s}")
                if sh is None:
                    continue
                e = (fr.get("arm_elevation_deg") or {}).get(s)
                lift = shoulder_lift_model(float(e), hu) if e is not None and rest is not None else None
                inward = _arc_inward(lift, hw) if lift else 0.0
                dx = abs(sh[0] - an["torso_center"][0]); need = RIG["shoulder_x_frac"] * hw - inward
                if dx < need:
                    f.append(F("RIG-SHOULDER", f"{cid} frame {fr['f']} shoulder_{s} is {dx:.1f} px from the torso centre, edge is {hw:.1f} (need >= {need:.1f} at elevation {e if e is not None else 0:.0f} deg): sleeve from the chest (R-341)"))
                if lift is not None:
                    want = rest - lift; low = RIG["shoulder_y_heads"] * hu + RIG["shoulder_y_lift_frac"] * lift
                    if sh[1] - want > low:     # lower than the arm allows: the shoulder stayed down
                        f.append(F("RIG-SHOULDER", f"{cid} frame {fr['f']} shoulder_{s} y {sh[1]:.1f} is {sh[1] - want:.1f} px below the scapulohumeral line {want:.1f} for elevation {e:.0f} deg (allowed {low:.1f}; the shoulder must rise {lift:.1f} px with the arm) (R-341, R-308)"))
                    elif want - sh[1] > RIG["shrug_max_heads"] * hu:     # higher than lift plus a shrug can explain
                        f.append(F("RIG-SHOULDER", f"{cid} frame {fr['f']} shoulder_{s} y {sh[1]:.1f} is {want - sh[1]:.1f} px above the scapulohumeral line {want:.1f} (a shrug is allowed up to {RIG['shrug_max_heads'] * hu:.1f} px) (R-341)"))
                elif "clavicle_y" in fr and abs(sh[1] - fr["clavicle_y"]) > RIG["shoulder_y_heads"] * hu:
                    f.append(F("RIG-SHOULDER", f"{cid} frame {fr['f']} shoulder_{s} y is off the clavicle line by {abs(sh[1] - fr['clavicle_y']):.1f} px (R-341)"))
            if "neck_length_px" in fr and fr["neck_length_px"] < RIG["neck_min_heads"] * hu:
                f.append(F("RIG-SHOULDER", f"{cid} frame {fr['f']} neck {fr['neck_length_px']:.1f} px < {RIG['neck_min_heads'] * hu:.1f} (R-342)"))
    return f

def rig_shoulder_rides(trace: dict) -> list[str]:
    f = []
    for cid, ch in trace.get("characters", {}).items():
        hu = float(ch.get("head_unit_px", 0)) or 1.0
        for s in ("L", "R"):
            el = []; lift = []
            for fr in _frames(ch):
                e = (fr.get("arm_elevation_deg") or {}).get(s); l = (fr.get("shoulder_lift_px") or {}).get(s)
                if e is not None and l is not None and e > RIG["rides_min_elev"]:
                    el.append(e); lift.append(l)
            if len(el) < 4 or max(el) - min(el) < 40:
                continue
            c = _corr(el, lift)
            if c < RIG["rides_corr"] or max(lift) < RIG["rides_min_lift_heads"] * hu * (max(el) - RIG["rides_min_elev"]) / 90.0:
                f.append(F("RIG-SHOULDER-RIDES", f"{cid} arm {s}: shoulder lift correlates {c:.2f} with elevation, max lift {max(lift):.1f} px (need corr >= 0.7 and about 0.1 head per 60 deg) (R-308)"))
    return f

def _corr(a, b) -> float:
    n = len(a)
    if n < 2:
        return 0.0
    ma, mb = sum(a) / n, sum(b) / n
    sa = math.sqrt(sum((x - ma) ** 2 for x in a)); sb = math.sqrt(sum((y - mb) ** 2 for y in b))
    if sa < 1e-9 or sb < 1e-9:
        return 0.0
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb)

def rig_balance(trace: dict, spec=None, root=None) -> list[str]:
    f = []
    for cid, ch in trace.get("characters", {}).items():
        for fr in _frames(ch):
            if "com" not in fr or "support_x" not in fr:
                continue
            x0, x1 = fr["support_x"]; m = RIG["com_margin_pct"] / 100.0 * (x1 - x0)
            if not x0 - m <= fr["com"][0] <= x1 + m:
                f.append(F("RIG-BALANCE", f"{cid} frame {fr['f']} centre of mass x {fr['com'][0]:.1f} outside support {x0:.0f}..{x1:.0f} +- {m:.1f} (R-314)"))
    return f

def _blink_runs(frames: list[dict]):
    runs = []; start = None
    for i, fr in enumerate(frames):
        b = ((fr.get("face") or {}).get("blink", 0) or 0) >= 0.5
        if b and start is None:
            start = i
        if not b and start is not None:
            runs.append((start, i - start)); start = None
    if start is not None:
        runs.append((start, len(frames) - start))
    return runs

def rig_blink(trace: dict, spec: dict | None) -> list[str]:
    f = []; fps = float(trace.get("fps", 24))
    for cid, ch in trace.get("characters", {}).items():
        frames = _frames(ch)
        for (s, n) in _blink_runs(frames):
            nf = n * 24.0 / fps
            if not RIG["blink_frames"][0] <= round(nf) <= RIG["blink_frames"][1]:
                f.append(F("RIG-BLINK", f"{cid} frame {frames[s]['f']} blink lasts {n} frames at {fps:g} fps (need 2..5 at 24 fps) (R-364)"))
        for b in _beats_for(spec, cid):
            em = b.get("emotion") or {}; band = ((b.get("emotion_track") or {}).get("eyes") or {}).get("blink_per_min")
            seg = [fr for fr in frames if float(b["start"]) <= fr["t"] < float(b["end"])]
            if not seg:
                continue
            starts = [seg[s]["t"] for s, _ in _blink_runs(seg)]
            d = _dur(b)
            if band and d >= 4:
                cnt = len(starts)
                if not (band[0] * d / 60.0 - 1 <= cnt <= band[1] * d / 60.0 + 1):
                    f.append(F("RIG-BLINK", f"{cid} beat {b['id']} measured {cnt} blinks in {d:.1f} s = {cnt * 60 / d:.1f}/min, declared {band} (R-364)"))
            gaps = [round(b2 - a, 3) for a, b2 in zip(starts, starts[1:])]
            if len(gaps) >= 2 and len(set(gaps)) == 1:
                f.append(F("RIG-BLINK", f"{cid} beat {b['id']} blink intervals are all {gaps[0]} s: placed, not metronomic (R-364)"))
    return f

def _speed(frames):
    out = [0.0]
    for a, b in zip(frames, frames[1:]):
        fa, fb = a.get("face") or {}, b.get("face") or {}
        out.append(math.hypot(fb.get("eye_x", 0) - fa.get("eye_x", 0), fb.get("eye_y", 0) - fa.get("eye_y", 0)))
    return out

def rig_eye_dart(trace: dict, spec: dict | None) -> list[str]:
    f = []; fps = float(trace.get("fps", 24))
    for cid, ch in trace.get("characters", {}).items():
        frames = _frames(ch)
        if not frames:
            continue
        sp = _speed(frames); med = sorted(sp)[len(sp) // 2]; thr = max(3 * med, RIG["dart_min_speed"])
        for b in _beats_for(spec, cid):
            if (b.get("emotion") or {}).get("intensity", 0) < 0.3:
                continue
            t = float(b["start"])
            while t + 1.0 <= float(b["end"]) + 1e-9:
                idx = [i for i, fr in enumerate(frames) if t <= fr["t"] < t + 1.0]
                if idx and max(sp[i] for i in idx) < thr:
                    f.append(F("RIG-EYE-DART", f"{cid} {t:.1f}-{t + 1:.1f} s in beat {b['id']} the eyes never move on their own (no dart above {thr:.3f}) (R-363)"))
                t += 1.0
        ex = [(fr.get("face") or {}).get("eye_x", 0) for fr in frames]; hy = [(fr.get("face") or {}).get("head_yaw", 0) for fr in frames]
        c = _corr(ex, hy)
        if c > RIG["eye_head_corr_max"] and max(hy) - min(hy) > 1e-6:
            f.append(F("RIG-EYE-INDEP", f"{cid} eye position correlates {c:.2f} with head yaw (max 0.9): eyes only follow the head (R-363)"))
    return f

def rig_eye_lead(trace: dict) -> list[str]:
    f = []
    for cid, ch in trace.get("characters", {}).items():
        frames = _frames(ch)
        ex = [(fr.get("face") or {}).get("eye_x", 0) for fr in frames]; hy = [(fr.get("face") or {}).get("head_yaw", 0) for fr in frames]
        if len(frames) < 12 or max(hy) - min(hy) < RIG["head_move_deg"]:
            continue
        ev = [b - a for a, b in zip(ex, ex[1:])]; hv = [b - a for a, b in zip(hy, hy[1:])]
        best, bk = -9, 0
        for k in range(-8, 9):
            a = ev[max(0, -k): len(ev) - max(0, k)]; b = hv[max(0, k): len(hv) - max(0, -k)]
            c = _corr(a, b) if len(a) == len(b) and len(a) > 3 else -9
            if c > best:
                best, bk = c, k
        if not RIG["eye_lead"][0] <= bk <= RIG["eye_lead"][1]:
            f.append(F("RIG-EYE-LEAD", f"{cid} the eyes lead the head by {bk} frames (need 2..4) (R-362)"))
    return f

def _face_series(frames):
    names = set()
    for fr in frames:
        fc = fr.get("face") or {}
        names |= set(fc.get("controls", {}).keys())
        names |= {k for k in ("brow_L", "brow_R", "lid_upper", "lid_lower", "iris_r", "mouth_open", "corner_L", "corner_R") if k in fc}
    def val(fr, n):
        fc = fr.get("face") or {}
        return fc.get("controls", {}).get(n, fc.get(n, 0.0))
    return {n: [val(fr, n) for fr in frames] for n in names}

def rig_face(trace: dict, spec: dict | None) -> list[str]:
    f = []
    for cid, ch in trace.get("characters", {}).items():
        frames = _frames(ch)
        ser = _face_series(frames)
        moving = [n for n, v in ser.items() if v and max(v) - min(v) >= RIG["face_control_delta"]]
        if len(moving) < RIG["face_controls_changed"]:
            f.append(F("RIG-FACE", f"{cid} only {len(moving)} face controls move by >= 0.15 over the film (need >= 5; a 1-control face reads as surprise only) (R-365)"))
        for b in _beats_for(spec, cid):
            pk = (b.get("emotion") or {}).get("peak_s")
            if pk is None or len(frames) < 3:
                continue
            seg = [i for i, fr in enumerate(frames) if float(b["start"]) <= fr["t"] <= float(b["end"]) and i > 0]
            if not seg:
                continue
            ch_amt = {i: sum(abs(v[i] - v[i - 1]) for n, v in ser.items() if n != "mouth_open") for i in seg}   # the EMOTION peak: the mouth's own opening is speech (a viseme moves it every few frames, C6), not feeling; the jaw AU26 still counts
            top = max(ch_amt, key=ch_amt.get); fps = float(trace.get("fps", 24))
            if abs(frames[top]["t"] - pk) * fps > RIG["peak_frames"]:
                f.append(F("RIG-PEAK", f"{cid} beat {b['id']} biggest face change at {frames[top]['t']:.2f} s, declared peak_s {pk} (R-374)"))
    return f

def shadow_mask_issues(mask, label: str = "") -> list[str]:
    """mask: 2-D bool array. FAIL on interior holes >= 4 px and on more than one connected component."""
    import numpy as np
    from scipy import ndimage as ndi
    m = np.asarray(mask, bool)
    if not m.any():
        return [F("RIG-SHADOW-HOLES", f"{label} shadow mask is empty (R-356)")]
    filled = ndi.binary_fill_holes(m)
    holes = filled & ~m
    lab, n = ndi.label(holes)
    big = [int((lab == i).sum()) for i in range(1, n + 1) if (lab == i).sum() >= RENDER2["shadow_hole_px"]]
    out = []
    if big:
        out.append(F("RIG-SHADOW-HOLES", f"{label} shadow mask has {len(big)} interior holes {big[:4]} px (hollow gradient / cut-out) (R-356)"))
    _, comps = ndi.label(m)
    if comps > 1:
        out.append(F("RIG-SHADOW-HOLES", f"{label} shadow mask has {comps} separate pieces for one caster (clip cut-out) (R-356)"))
    return out

def rig_shadow(trace: dict, base: Path | None = None) -> list[str]:
    f = []
    try:
        from PIL import Image
        import numpy as np
    except ImportError:
        return [F("RIG-SHADOW-HOLES", "numpy/PIL missing")]
    for cid, ch in trace.get("characters", {}).items():
        for fr in _frames(ch):
            p = fr.get("shadow_mask")
            if not p:
                continue
            pp = Path(p) if Path(p).is_absolute() or base is None else Path(base) / p
            if not pp.exists():
                f.append(F("RIG-SHADOW-HOLES", f"{cid} frame {fr['f']} shadow mask {p} not found (R-356)")); continue
            im = Image.open(pp).convert("L"); w, h = im.size
            im = im.resize((max(w // 2, 1), max(h // 2, 1)))
            f += shadow_mask_issues(np.asarray(im) > 127, f"{cid} frame {fr['f']}")
    return f

# ------------------------------------------------------------------ HANDS, PROPS AND WRITING (R-383..R-392, gate-spec L)
HANDW = {"topo_fingers": 4, "finger_order": ["thumb", "index", "middle", "ring", "little"],
         "max_joint_jump_deg": 25.0,      # largest single-frame change of any finger joint angle (calibrated on v5: its max is 12.1 deg)
         "max_orient_jump_deg": 30.0,     # single-frame change of the hand axis (calibrated on v5: max 15.7 deg; the v4 snap turned about 45)
         "max_wrist_jump_px": 120.0,      # single-frame wrist travel (1080x1920 canvas) unless a cut or a declared smear (DEFAULT: v5 reaches 86.7 px, so no tighter value is evident)
         "swap_frames": 4,                # in-between frames a grip / contact-kind / pinch change needs
         "nib_gap_px": 3.0, "reveal_tol_px": 6.0, "grip_contact_px": 8.0,   # nib_gap calibrated on v5 (0 px while writing); grip_contact kept (v5 max 6.8 px)
         "min_toward_share": 0.5}

def _hp(fr: dict) -> dict:
    return fr.get("hand_pose") or {}

def _waived(fr: dict) -> bool:
    return bool(fr.get("cut") or fr.get("smear"))

def rig_hand_topo(trace: dict) -> list[str]:
    """HAND-TOPO (R-383, R-384) and HAND-SIDE (R-385): finger count and order constant, no single-frame shape jump, grip named for its side."""
    f = []
    for cid, ch in trace.get("characters", {}).items():
        fr_all = _frames(ch)
        for side in ("L", "R"):
            prev, topo0, bad = None, None, {}
            for fr in fr_all:
                hp = _hp(fr).get(side)
                if not hp:
                    prev = None
                    continue
                gid = hp.get("id", "")
                m = re.search(r"-([LR])$", gid)
                if m and m.group(1) != side and not hp.get("mirrored"):
                    bad.setdefault("HAND-SIDE", f"{cid} frame {fr['f']} hand {side} uses grip {gid} authored for the {m.group(1)} hand without `mirrored: true` (R-385)")
                tp = hp.get("topo") or {}
                key = (tp.get("fingers"), tuple(tp.get("order") or ()))
                if tp:
                    if tp.get("fingers") != HANDW["topo_fingers"] or list(tp.get("order") or ()) != HANDW["finger_order"]:
                        bad.setdefault("HAND-TOPO", f"{cid} frame {fr['f']} hand {side} topology {key}, expected 4 fingers + thumb in order {HANDW['finger_order']} (R-383)")
                    if topo0 is None:
                        topo0 = key
                    elif key != topo0:
                        bad.setdefault("HAND-TOPO", f"{cid} frame {fr['f']} hand {side} topology changed {topo0} -> {key} (R-383)")
                if prev is not None and not _waived(fr):
                    pf, cf = (prev.get("fingers") or {}), (hp.get("fingers") or {})
                    worst, wn = 0.0, ""
                    for fn in cf:
                        a, b = pf.get(fn), cf.get(fn)
                        if a and b:
                            for i, (x, y) in enumerate(zip(a, b)):
                                if abs(x - y) > worst:
                                    worst, wn = abs(x - y), f"{fn}[{i}]"
                    if worst > HANDW["max_joint_jump_deg"]:
                        bad.setdefault("HAND-TOPO", f"{cid} frame {fr['f']} hand {side} joint {wn} jumps {worst:.0f} deg in one frame (max {HANDW['max_joint_jump_deg']:.0f}; declare `smear` if intended) (R-384)")
                    if prev.get("orient_deg") is not None and hp.get("orient_deg") is not None:
                        d = (hp["orient_deg"] - prev["orient_deg"] + 180) % 360 - 180
                        if abs(d) > HANDW["max_orient_jump_deg"]:
                            bad.setdefault("HAND-TOPO", f"{cid} frame {fr['f']} hand {side} axis turns {d:.0f} deg in one frame (max {HANDW['max_orient_jump_deg']:.0f}) (R-384)")
                    if prev.get("wrist_px") and hp.get("wrist_px"):
                        d = _dist(prev["wrist_px"], hp["wrist_px"])
                        if d > HANDW["max_wrist_jump_px"]:
                            bad.setdefault("HAND-TOPO", f"{cid} frame {fr['f']} hand {side} wrist moves {d:.0f} px in one frame (max {HANDW['max_wrist_jump_px']:.0f}) (R-384)")
                prev = hp
            f += [F(k, v) for k, v in bad.items()]
    return f

def rig_hand_swap(trace: dict) -> list[str]:
    """HAND-SWAP (R-386): a change of grip id, contact kind or pinch needs >= N in-between frames carrying blend{to_id,to_kind,k} with k rising."""
    f = []
    n = HANDW["swap_frames"]
    for cid, ch in trace.get("characters", {}).items():
        for side in ("L", "R"):
            hist = []
            for fr in _frames(ch):
                hp = _hp(fr).get(side)
                if not hp:
                    hist = []
                    continue
                key = (hp.get("id"), hp.get("contact_kind"), bool(hp.get("pinch")))
                if hist and key != hist[-1][0] and not _waived(fr):
                    run = [h[1] for h in hist[-n:]]
                    ok = len(run) >= n and all(b and b.get("k") is not None and b.get("to_id", key[0]) == key[0] and b.get("to_kind", key[1]) == key[1] for b in run) \
                        and all(run[i]["k"] < run[i + 1]["k"] for i in range(len(run) - 1))
                    if not ok:
                        f.append(F("HAND-SWAP", f"{cid} frame {fr['f']} hand {side} changes {hist[-1][0]} -> {key} with {sum(1 for b in run if b)} of {n} required in-between frames (R-386)"))
                hist.append((key, hp.get("blend")))
    return f

def rig_prop_face(trace: dict) -> list[str]:
    """PROP-FACE (R-387, R-388): a mark is drawn only on the face the camera sees, and on the face the nib is touching."""
    f = []
    for cid, ch in trace.get("characters", {}).items():
        for fr in _frames(ch):
            wr = fr.get("writing") or {}
            for pr in fr.get("props", []):
                faces = pr.get("faces") or {}
                for mk in pr.get("marks", []):
                    if not mk.get("drawn", True):
                        continue
                    if mk.get("face") not in faces:
                        return f + [F("PROP-FACE", f"{cid} frame {fr['f']} prop {pr.get('id')} mark {mk.get('id')} is on undeclared face {mk.get('face')} (R-387)")]
                    if pr.get("facing") and mk["face"] != pr["facing"]:
                        return f + [F("PROP-FACE", f"{cid} frame {fr['f']} prop {pr.get('id')} mark {mk.get('id')} is drawn on its {mk['face']} but the camera sees its {pr['facing']} (R-387)")]
                    if wr.get("active") and wr.get("prop") == pr.get("id") and wr.get("nib_face") and mk.get("kind") == "ink" and mk["face"] != wr["nib_face"]:
                        return f + [F("PROP-FACE", f"{cid} frame {fr['f']} nib touches the {wr['nib_face']} of {pr.get('id')} but the ink is drawn on its {mk['face']} (R-388)")]
    return f

def rig_write_reveal(trace: dict) -> list[str]:
    """WRITE-REVEAL (R-389, R-390): ink grows only at the nib, never shrinks, only while writing, in the script's direction."""
    f = []
    for cid, ch in trace.get("characters", {}).items():
        prev, dxs, direction = None, [], None
        for fr in _frames(ch):
            wr = fr.get("writing")
            if not wr:
                prev = None
                continue
            direction = wr.get("direction", direction)
            L, d, nib = wr.get("ink_len_px", 0.0), wr.get("drawn_to_px"), wr.get("nib_px")
            if not wr.get("active") and prev is not None and L > prev["L"] + 0.5:
                f.append(F("WRITE-REVEAL", f"{cid} frame {fr['f']} ink grows {L - prev['L']:.1f} px while the nib is not writing (R-389)"))
                break
            if prev is not None and L < prev["L"] - 0.5 and not wr.get("erase"):
                f.append(F("WRITE-REVEAL", f"{cid} frame {fr['f']} ink shrinks (R-389)"))
                break
            if wr.get("active") and d and nib and _dist(d, nib) > HANDW["reveal_tol_px"]:
                f.append(F("WRITE-REVEAL", f"{cid} frame {fr['f']} ink end is {_dist(d, nib):.1f} px from the nib (max {HANDW['reveal_tol_px']:.0f}): ink is not revealed under the nib (R-389)"))
                break
            if wr.get("active") and prev is not None and prev.get("d") and d and L > prev["L"] + 0.5:
                dxs.append(d[0] - prev["d"][0])
            prev = {"L": L, "d": d}
        if len(dxs) >= 6 and direction in ("rtl", "ltr"):
            toward = sum(1 for x in dxs if (x <= 0 if direction == "rtl" else x >= 0)) / len(dxs)
            net = sum(dxs)
            if toward < HANDW["min_toward_share"] or (net > 0 if direction == "rtl" else net < 0):
                f.append(F("WRITE-REVEAL", f"{cid} writes {direction} but only {toward:.0%} of ink-growing frames move that way, net dx {net:.0f} px (R-390)"))
    return f

def rig_nib_contact(trace: dict) -> list[str]:
    """NIB-CONTACT (R-391): while writing, the nib tip is on the paper (gap <= N px, inside the paper)."""
    f = []
    for cid, ch in trace.get("characters", {}).items():
        for fr in _frames(ch):
            wr = fr.get("writing")
            if not wr or not wr.get("active"):
                continue
            gap = wr.get("nib_gap_px")
            if gap is None and wr.get("nib_px") and wr.get("paper_px"):
                gap = _dist(wr["nib_px"], wr["paper_px"])
            if gap is None:
                f.append(F("NIB-CONTACT", f"{cid} frame {fr['f']} writing without nib_gap_px or nib_px + paper_px"))
                break
            if gap > HANDW["nib_gap_px"] or wr.get("on_paper") is False:
                f.append(F("NIB-CONTACT", f"{cid} frame {fr['f']} nib is {gap:.1f} px off the paper (max {HANDW['nib_gap_px']:.0f}) or outside it (R-391)"))
                break
    return f

def rig_grip_layers(trace: dict) -> list[str]:
    """LAYER-GRIP (R-392): hand / pen / paper order drawn equals the grip's declared order for this camera angle; digits touch the held object."""
    for cid, ch in trace.get("characters", {}).items():
        for fr in _frames(ch):
            lo = fr.get("layer_order")
            for side, hp in _hp(fr).items():
                if not hp.get("holding"):
                    continue
                decl = hp.get("grip_layers") or {}
                if not decl:
                    return [F("LAYER-GRIP", f"{cid} frame {fr['f']} hand {side} holds {hp['holding']} but its grip {hp.get('id')} declares no grip_layers (R-392)")]
                if lo:
                    want = decl.get(lo.get("angle"))
                    if not want:
                        return [F("LAYER-GRIP", f"{cid} frame {fr['f']} grip {hp.get('id')} has no layer order for angle {lo.get('angle')} (R-392)")]
                    got = [p for p in lo["order"] if p in want]
                    if got != want:
                        return [F("LAYER-GRIP", f"{cid} frame {fr['f']} hand {side} draws {got}, grip {hp.get('id')} declares {want} for angle {lo.get('angle')} (R-392)")]
                far = {k: v for k, v in (hp.get("grip_contacts") or {}).items() if v > HANDW["grip_contact_px"]}
                if far:
                    return [F("LAYER-GRIP", f"{cid} frame {fr['f']} hand {side} digits {far} are further than {HANDW['grip_contact_px']:.0f} px from the held {hp['holding']}: it is not held (R-392)")]
    return []

def check_hands_writing(trace: dict) -> list[str]:
    return (rig_hand_topo(trace) + rig_hand_swap(trace) + rig_prop_face(trace) + rig_write_reveal(trace)
            + rig_nib_contact(trace) + rig_grip_layers(trace))

# ------------------------------------------------------------------ LIP SYNC (C6, the owner 2026-10-25: "the mouths do not move with the words")
# A voice-aware shot (spec["lipsync"], written by tools/calm.py from the voice stage's viseme tracks) places each on-screen speaker's line on the shot clock.
# The rig trace carries, per frame per actor, the viseme that drove the mouth (face.viseme, face.viseme_w) and the mouth as drawn (face.mouth.open ...).
#   LIPSYNC-ACTIVE   on the frames where a speaker's line is voiced, the traced viseme IS the track's viseme (frame by frame), the viseme changes at the track's rate
#                    and the mouth really opens (so a face that never reads the track, a wrong time offset or a hidden mouth all fail)
#   LIPSYNC-SILENT   on the frames where a speaker is silent (before, between words, after) the mouth is shut; an actor with NO line (the narrator speaks, not him)
#                    shows no viseme and no talking-like open/close
LIPSYNC = {"match_min": 0.95, "change_min": 0.6, "open_range_min": 0.15, "silent_open_max": 0.12, "guard_frames": 1,
           "listener_swing": 0.06, "listener_reversals_max": 1, "min_voiced_keys": 3}

def lip_track_at(e: dict, t: float):
    """Python twin of face.js visemeTrackAt for one lipsync entry, t on the SHOT clock -> (id, w) or None outside the track."""
    K = e["keys"]
    lt, ramp, end = t - float(e["start_s"]), float(e.get("ramp_s") or .04), K[-1]["t"]
    if lt < K[0]["t"] or lt > end:
        return None
    vid = K[0]["id"]
    for k in K:
        if lt >= k["t"]:
            vid = k["id"]
        else:
            break
    return vid, (0.0 if vid == "V0" else max(0.0, min(1.0, min((lt - K[0]["t"]) / ramp + .5, (end - lt) / ramp + .5))))

def _lip_expected(ents: list, t: float):
    for e in ents:
        r = lip_track_at(e, t)
        if r is not None and r[0] != "V0":
            return r[0]
    return None

def _lip_near_change(ents: list, t: float, guard: float) -> bool:
    """t within `guard` seconds of a key time or of the track's ends: the frame sits on a boundary and is not judged."""
    for e in ents:
        for k in e["keys"]:
            if abs(t - (float(e["start_s"]) + k["t"])) <= guard:
                return True
    return False

def _zigzag_reversals(series: list, swing: float) -> int:
    """How many times a series turns round, counting only turns after a move of at least `swing` (a gasp is 0 or 1, talking is many)."""
    if not series:
        return 0
    hi = lo = ext = series[0]
    direction = rev = 0
    for v in series:
        if direction == 0:
            hi, lo = max(hi, v), min(lo, v)
            if hi - lo >= swing:
                direction, ext = (1 if v >= hi else -1), v
        elif direction == 1:
            if v > ext:
                ext = v
            elif ext - v >= swing:
                direction, rev, ext = -1, rev + 1, v
        else:
            if v < ext:
                ext = v
            elif v - ext >= swing:
                direction, rev, ext = 1, rev + 1, v
    return rev

def rig_lipsync(trace: dict, spec: dict | None) -> list[str]:
    if not spec or "lipsync" not in spec:
        return []   # not a voice-aware shot: nothing to hold the mouth to
    f, L = [], LIPSYNC
    fps = float(trace.get("fps", 24))
    guard = L["guard_frames"] / fps + 1e-6
    for cid, ch in trace.get("characters", {}).items():
        frames = _frames(ch)
        if not frames:
            continue
        ents = [e for e in spec["lipsync"] if e.get("actor") == cid]
        face = lambda fr: fr.get("face") or {}
        op = lambda fr: float((face(fr).get("mouth") or {}).get("open", face(fr).get("mouth_open", 0.0)) or 0.0)
        if not ents:
            talk = [fr for fr in frames if face(fr).get("viseme")]
            if talk:
                f.append(F("LIPSYNC-SILENT", f"{cid} has no spoken line in this shot but a viseme drives its mouth on {len(talk)} frames (first at {talk[0]['t']:.2f} s): narrator lines never move a character's mouth"))
            rev = _zigzag_reversals([op(fr) for fr in frames], L["listener_swing"])
            if rev > L["listener_reversals_max"]:
                f.append(F("LIPSYNC-SILENT", f"{cid} has no spoken line but its mouth turns round {rev} times (open, close, open ...) (swings of >= {L['listener_swing']}): it reads as talking over the narrator"))
            continue
        voiced, silent = [], []
        for fr in frames:
            t = float(fr["t"])
            if _lip_near_change(ents, t, guard):
                continue
            (voiced if _lip_expected(ents, t) else silent).append(fr)
        total_voiced_keys = sum(1 for e in ents for k in e["keys"] if k["id"] != "V0")
        if total_voiced_keys and not voiced:
            f.append(F("LIPSYNC-ACTIVE", f"{cid} speaks {', '.join(e['line'] for e in ents)} but no frame of the shot falls inside the voiced part of the line (start_s {ents[0]['start_s']}): the line is cut off or placed outside the shot"))
            continue
        bad = [fr for fr in voiced if face(fr).get("viseme") != _lip_expected(ents, float(fr["t"])) or float(face(fr).get("viseme_w", 0) or 0) <= 0]
        share = 1 - len(bad) / len(voiced) if voiced else 1.0
        if share < L["match_min"]:
            b = bad[0]
            f.append(F("LIPSYNC-ACTIVE", f"{cid} mouth follows its viseme track on {share:.0%} of {len(voiced)} voiced frames (need >= {L['match_min']:.0%}); first miss at {b['t']:.2f} s: track says "
                                         f"{_lip_expected(ents, float(b['t']))}, the face drew {face(b).get('viseme')}. A scene that never passes s.viseme, a wrong time offset or a missing track gives this"))
        exp_ids = [_lip_expected(ents, float(fr["t"])) for fr in frames if not _lip_near_change(ents, float(fr["t"]), guard)]
        act_ids = [face(fr).get("viseme") for fr in frames if not _lip_near_change(ents, float(fr["t"]), guard)]
        n_exp = sum(1 for a, b in zip(exp_ids, exp_ids[1:]) if a != b and (a or b))
        n_act = sum(1 for a, b in zip(act_ids, act_ids[1:]) if a != b and (a or b))
        if n_exp and n_act < L["change_min"] * n_exp:
            f.append(F("LIPSYNC-ACTIVE", f"{cid} mouth shape changes {n_act} times, the viseme track changes {n_exp} times (need >= {L['change_min']:.0%} of them): the mouth does not keep the rhythm of the words"))
        if total_voiced_keys >= L["min_voiced_keys"] and voiced:
            opens = [op(fr) for fr in voiced]
            if max(opens) - min(opens) < L["open_range_min"]:
                f.append(F("LIPSYNC-ACTIVE", f"{cid} mouth opening varies only {max(opens) - min(opens):.2f} over the line (need >= {L['open_range_min']}): the mouth is too small, hidden or not drawn from the viseme"))
        loud = [fr for fr in silent if op(fr) > L["silent_open_max"] or float(face(fr).get("viseme_w", 0) or 0) > 0]
        if loud:
            b = max(loud, key=op)
            f.append(F("LIPSYNC-SILENT", f"{cid} mouth is open ({op(b):.2f}, viseme {face(b).get('viseme')}) on {len(loud)} of {len(silent)} frames where it is silent (first at {loud[0]['t']:.2f} s; limit {L['silent_open_max']}): closed between words and in pauses"))
    return f

# ART-PROPORTION (owner, 2026-10-25: the art book is the reference, every time): what the film DRAWS (trace frame `art`, render/hands.js artMeasure, head units) per head height must be
# within the reference's tolerance of the character's approved art-book model (catalogue/characters/<id>/artbook-proportions.json, written by tools/artbook_proportions.py from the
# data the approved sheets are drawn from). Close-ups read through the camera, never through scale. A character with no reference file, or a trace with no `art` records (a legacy
# trace), is not judged; the recorder always writes `art`, so a new trace is.
ART_HAND = ("hand_len_hu", "hand_w_hu", "finger_r_hu")
ART_FACE = ("nose_w_hu", "nose_len_hu", "lips_w_hu", "lips_t_hu", "eye_w_hu", "eye_h_hu")

def rig_art_proportion(trace: dict, root=None) -> list[str]:
    f = []
    if not root:
        return f
    for cid, ch in trace.get("characters", {}).items():
        rp = Path(root) / "catalogue" / "characters" / str(cid) / "artbook-proportions.json"
        if not rp.is_file():
            continue
        ref = json.loads(rp.read_text(encoding="utf-8"))
        tol = float(ref.get("tolerance_pct", 8.0)) / 100.0
        want = ref.get("per_head") or {}
        worst: dict = {}
        n_art = 0
        for fr in _frames(ch):
            a = fr.get("art")
            if not a:
                continue
            n_art += 1
            head = float(a.get("head_h_hu") or 0)
            if head <= 0:
                continue
            got = []
            for key in ART_HAND:
                for sd, v in (a.get(key) or {}).items():
                    got.append((f"{key[:-3]}_{sd}", key, float(v)))
            for key in ART_FACE:
                if key in a:
                    got.append((key[:-3], key, float(a[key])))
            for lab, key, v in got:
                if key not in want or want[key] <= 0:
                    continue
                dev = (v / head) / want[key] - 1
                if abs(dev) > tol:
                    w = worst.setdefault(lab, {"n": 0, "first": fr["f"], "dev": dev, "film": a.get("film")})
                    w["n"] += 1
                    if abs(dev) > abs(w["dev"]):
                        w["dev"] = dev
        for lab, w in sorted(worst.items()):
            f.append(F("ART-PROPORTION", f"{cid} {lab} is {w['dev'] * 100:+.0f}% off the art book (per head height; tolerance {tol * 100:.0f}%) on {w['n']} frames from frame {w['first']}, film profile "
                                         f"'{w['film']}' (approved sheets {ref.get('approved_sheet_version')}: {rp.name}). Close-ups read through the camera, never through scale (CLAUDE.md)"))
    return f

def check_rig(trace: dict, spec: dict | None = None, root=None, base: Path | None = None) -> list[str]:
    return (rig_limits(trace, spec, root) + rig_hinge(trace) + rig_seglen(trace, spec, root) + rig_contacts(trace)
            + rig_attach(trace, spec) + rig_layers(trace, spec) + rig_shoulder_clavicle(trace) + rig_shoulder_rides(trace)
            + rig_balance(trace) + rig_blink(trace, spec) + rig_eye_dart(trace, spec) + rig_eye_lead(trace)
            + rig_face(trace, spec) + rig_shadow(trace, base) + rig_seams(trace, base) + check_hands_writing(trace) + rig_actors(trace, spec) + rig_lipsync(trace, spec) + rig_art_proportion(trace, root))
