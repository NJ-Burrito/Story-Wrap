# qg_checks.py part 3 of 4: executed into the qg_checks module namespace by qg_checks.py (a pure move).
# ------------------------------------------------------------------ MULTI-ACTOR (gate-spec N): several characters in one shot
# Spec: actors[] {id, module, depth_z, layer, catalogue_refs}, beats[].draw_order, beats[].actor_emotions{id}, actor_interactions[].
# Trace: characters{<actor id>}, scene{actors[], frames[{f, present, draw_order, depth, props[]}]}. DEFAULT numbers (no measured two-actor sample yet).
ACTOR = {"contact_tol_px": 8.0,       # a declared contact: the two points within this many canvas px on every frame of the window (= HANDW grip_contact_px)
         "handover_both_frames": 3,   # both hands on the prop for at least this many frames before the hand-off frame
         "handover_gap_px": 8.0,      # "a hand is on the prop": its contact point within this many px of the prop's grip point
         "handover_jump_px": 16.0,    # the prop's centre moves at most this far between the frame before and the hand-off frame (no teleport)
         "z_eps": 1e-6}
HANDS = ("L", "R")

def _presence():
    try:
        from shotlib import presence
    except ImportError:       # qg_checks imported without tools/ on sys.path
        import sys as _s; _s.path.insert(0, str(Path(__file__).resolve().parent)); from shotlib import presence
    return presence

def _spec_frames(spec: dict) -> int:
    """Frames of the shot: last beat end x fps."""
    ends = [float(b.get("end", 0)) for b in spec.get("beats", [])]
    return round(max(ends or [0.0]) * float(spec.get("fps", 24)))

def _actor_ids(spec) -> list:
    return [a.get("id") for a in ((spec or {}).get("actors") or [])]

def _expand_tokens(order) -> list:
    """['partner', 'hero:arms'] -> ['partner:body', 'partner:arms', 'hero:arms']: a bare id is its body then its arms."""
    out = []
    for tk in order:
        out += [f"{tk}:body", f"{tk}:arms"] if ":" not in str(tk) else [str(tk)]
    return out

def _beat_actors(b: dict, spec: dict) -> list:
    return list(b.get("actors") or _actor_ids(spec))

def _order_windows(b: dict) -> list:
    """beat.draw_order -> [(t0, t1, order, why)]; a window without t0/t1 spans the whole beat."""
    return [(float(w.get("t0", b.get("start", 0))), float(w.get("t1", b.get("end", 0))), list(w.get("order") or []), w.get("why")) for w in (b.get("draw_order") or [])]

def _declared_order(spec: dict, t: float):
    """The draw order the spec declares at time t (a window is [t0, t1); the last window also owns the final instant)."""
    beats = spec.get("beats", [])
    for bi, b in enumerate(beats):
        last = bi == len(beats) - 1
        if float(b.get("start", 0)) - 1e-9 <= t < float(b.get("end", 0)) - 1e-9 or (last and t >= float(b.get("end", 0)) - 1e-9):
            for t0, t1, order, _ in _order_windows(b):
                if t0 - 1e-9 <= t < t1 - 1e-9 or (last and t >= t1 - 1e-9):
                    return order
    return None

def _non_contiguous(tokens: list) -> list:
    """actors whose tokens are split by another actor's token (A, B, A): drawn "through" B unless the spec declares the split"""
    pos = {}
    for i, tk in enumerate(tokens):
        pos.setdefault(tk.split(":")[0], []).append(i)
    return [a for a, ix in pos.items() if ix[-1] - ix[0] + 1 != len(ix)]

def check_actors(spec: dict, root=None) -> list[str]:
    """Spec side of the multi-actor rules. A spec without `actors` is a one-character spec and is not touched."""
    f: list[str] = []
    if "actors" not in spec:
        return f
    A = spec["actors"] or []; ids = [a.get("id") for a in A]
    if not A:
        return [F("ACTOR-DECLARED", "actors[] is empty: declare each character instance (id, module, depth_z, layer, catalogue_refs)")]
    rig = {c.get("id") for c in spec.get("characters", [])}; seen = set()
    for a in A:
        aid = a.get("id")
        miss = [k for k in ("id", "module", "depth_z", "layer", "catalogue_refs") if a.get(k) in (None, "", [])]
        if miss:
            f.append(F("ACTOR-DECLARED", f"actor {aid} missing {miss}")); continue
        if aid in seen:
            f.append(F("ACTOR-DECLARED", f"actor id {aid} declared twice"))
        seen.add(aid)
        if aid not in rig:
            f.append(F("ACTOR-DECLARED", f"actor {aid} has no characters[] rig entry with the same id (rig, hands, seam and shadow checks run per id)"))
        if not isinstance(a["depth_z"], (int, float)) or not isinstance(a["layer"], int):
            f.append(F("ACTOR-DECLARED", f"actor {aid} depth_z must be a number (metres from the camera plane, larger = farther) and layer an integer"))
        bad = [r for r in a["catalogue_refs"] if not str(r).startswith(str(a["module"]) + "/")]
        if bad:
            f.append(F("ACTOR-DECLARED", f"actor {aid} catalogue_refs {bad} are not in the {a['module']} catalogue"))
        if root is not None and not (Path(root) / "tools" / "render" / "characters" / f"{a['module']}.js").is_file():
            f.append(F("ACTOR-DECLARED", f"actor {aid} module {a['module']} has no tools/render/characters/{a['module']}.js"))
    extra = rig - set(ids)
    if extra:
        f.append(F("ACTOR-DECLARED", f"characters[] entries {sorted(extra)} are not declared in actors[]"))
    pr, nfs, fps0 = _presence(), _spec_frames(spec), float(spec.get("fps", 24))   # per-actor frame ranges (actors[].frames, [f0, f1) pairs): an actor may enter, exit or be cut between
    amap = {a.get("id"): a for a in A}
    for a in A:
        if pr.declared(a) is not None:
            for msg in pr.problems(pr.declared(a), nfs):
                f.append(F("ACTOR-RANGE", f"actor {a.get('id')} frames: {msg}"))
    zl = {a["id"]: (a.get("depth_z"), a.get("layer")) for a in A if a.get("id")}
    inter = spec.get("actor_interactions", [])
    for b in spec.get("beats", []):
        bid = b.get("id", "?"); present = _beat_actors(b, spec)
        unk = [p for p in present if p not in zl]
        if unk:
            f.append(F("ACTOR-DECLARED", f"beat {bid} names actors {unk} that are not declared")); continue
        posed = {ps.get("character") for ps in b.get("poses", [])}
        bf0, bf1 = round(float(b.get("start", 0)) * fps0), round(float(b.get("end", 0)) * fps0)
        for aid in present:   # every actor a beat shows is in the shot for the whole beat (an absent actor must be left out of beat.actors)
            a_ = amap.get(aid, {})
            if pr.declared(a_) is not None and not pr.problems(pr.declared(a_), nfs):
                gone = [k for k in range(bf0, bf1) if not pr.present_at(a_, k, nfs)]
                if gone:
                    f.append(F("ACTOR-RANGE", f"beat {bid} shows actor {aid} but its frames {pr.declared(a_)} leave out {len(gone)} frame(s) of the beat's {bf0}..{bf1} (first {gone[0]}): list only the actors present in beat.actors, or widen the range"))
        for aid in present:
            if aid not in posed:
                f.append(F("ACTOR-DECLARED", f"beat {bid} has no pose for actor {aid} (poses[].character) (R-318)"))
            if not any(s.get("caster") == aid for s in b.get("cast_shadows", [])):
                f.append(F("SHADOW-ACTOR", f"beat {bid} has no cast shadow whose caster is actor {aid}: every actor casts its own mass-proxy shadow (R-355)"))
        if len(present) < 2:
            continue
        for aid in present:   # per-actor emotion
            ae = (b.get("actor_emotions") or {}).get(aid)
            if not ae or not ae.get("emotion") or not ae.get("emotion_track"):
                f.append(F("ACTOR-EMOTION", f"beat {bid} actor {aid} has no actor_emotions[{aid}] with emotion and emotion_track: each actor feels on its own track (R-360)"))
        wins = _order_windows(b)   # draw order
        if not wins:
            f.append(F("ACTOR-ORDER", f"beat {bid} shows {present} but declares no draw_order (who is in front, back to front)"))
        else:
            z = {a: zl[a][0] for a in present}
            z.update({k: v for k, v in (b.get("depth_z") or {}).items() if k in z})
            wins = sorted(wins, key=lambda w: w[0]); cur = float(b.get("start", 0))
            for i, (t0, t1, order, why) in enumerate(wins):
                if abs(t0 - cur) > 1e-6:
                    f.append(F("ACTOR-ORDER", f"beat {bid} draw_order windows leave {cur:.3f}..{t0:.3f} s without an order"))
                cur = t1
                toks = _expand_tokens(order)
                names = [tk.split(":")[0] for tk in toks]
                if sorted(set(names)) != sorted(present) or any(toks.count(f"{a}:{p}") != 1 for a in present for p in ("body", "arms")):
                    f.append(F("ACTOR-ORDER", f"beat {bid} draw_order {order} must name every present actor {present} once (id, or id:body and id:arms)")); continue
                bodies = [tk.split(":")[0] for tk in toks if tk.endswith(":body")]
                for a, c in zip(bodies, bodies[1:]):
                    if z[a] < z[c] - ACTOR["z_eps"] or (abs(z[a] - z[c]) <= ACTOR["z_eps"] and zl[a][1] >= zl[c][1]):
                        f.append(F("ACTOR-ORDER", f"beat {bid} draws {c} over {a} but {a} is nearer (depth_z {z[a]} vs {z[c]}, layer {zl[a][1]} vs {zl[c][1]}): the order must follow depth (farther first)"))
                split = _non_contiguous(toks)
                if split and len(str(why or "")) < SPEC2["min_why_chars"]:
                    f.append(F("ACTOR-ORDER", f"beat {bid} draw_order interleaves {split} (one actor's parts on both sides of another's) with no why of >= 12 chars"))
                if i and not why and wins[i - 1][2] != order:
                    f.append(F("ACTOR-ORDER", f"beat {bid} draw_order changes at {t0:.3f} s with no why (who passes in front of whom, and what the viewer sees)"))
            if abs(cur - float(b.get("end", 0))) > 1e-6:
                f.append(F("ACTOR-ORDER", f"beat {bid} draw_order windows end at {cur:.3f} s, the beat ends at {b.get('end')} s"))
        if not any(x.get("beat") == bid for x in inter) and not b.get("actors_apart_because"):
            f.append(F("ACTOR-INTERACTION", f"beat {bid} shows {present} together but declares no actor_interactions and no actors_apart_because"))
    props = {p.get("id"): p for p in spec.get("props", [])}; fps = float(spec.get("fps", 24)); beats = {b.get("id"): b for b in spec.get("beats", [])}
    for x in inter:
        xid = x.get("id", "?"); kind = x.get("kind"); b = beats.get(x.get("beat"))
        if kind not in ("contact", "handover", "apart") or b is None or x.get("t0") is None or x.get("t1") is None:
            f.append(F("ACTOR-INTERACTION", f"interaction {xid} needs kind contact|handover|apart, an existing beat, t0 and t1")); continue
        if kind == "apart":   # a declared NO-TOUCH (CLAUDE.md, the owner 2026-10-23): the two actors' hands stay at least min_gap_px apart (proved by ACTOR-CONTACT on the trace)
            ea, eb = x.get("a") or {}, x.get("b") or {}
            if ea.get("actor") not in ids or eb.get("actor") not in ids or ea.get("actor") == eb.get("actor"):
                f.append(F("ACTOR-INTERACTION", f"apart {xid} needs two different declared actors a and b"))
            if not all(h in HANDS for h in (ea.get("hands") or [])) or not all(h in HANDS for h in (eb.get("hands") or [])) or not ea.get("hands") or not eb.get("hands"):
                f.append(F("ACTOR-INTERACTION", f"apart {xid} needs a.hands and b.hands (L, R)"))
            if not isinstance(x.get("min_gap_px"), (int, float)) or x["min_gap_px"] < 1:
                f.append(F("ACTOR-INTERACTION", f"apart {xid} needs min_gap_px >= 1"))
            if not (float(b["start"]) - 1e-9 <= float(x["t0"]) < float(x["t1"]) <= float(b["end"]) + 1e-9):
                f.append(F("ACTOR-INTERACTION", f"interaction {xid} window {x['t0']}..{x['t1']} s lies outside beat {b['id']}"))
            if len(str(x.get("why") or "")) < SPEC2["min_why_chars"]:
                f.append(F("ACTOR-INTERACTION", f"interaction {xid} needs a why of >= 12 chars (the story reason they do not touch)"))
            continue
        if not (float(b["start"]) - 1e-9 <= float(x["t0"]) < float(x["t1"]) <= float(b["end"]) + 1e-9):
            f.append(F("ACTOR-INTERACTION", f"interaction {xid} window {x['t0']}..{x['t1']} s lies outside beat {b['id']}"))
        if len(str(x.get("why") or "")) < SPEC2["min_why_chars"]:
            f.append(F("ACTOR-INTERACTION", f"interaction {xid} needs a why of >= 12 chars (the story reason for the touch)"))

        def end_ok(e, what):
            if not isinstance(e, dict) or (e.get("actor") not in ids and not e.get("prop")):
                f.append(F("ACTOR-INTERACTION", f"interaction {xid} {what} must name a declared actor (+ point) or a prop")); return False
            if e.get("actor") and e["actor"] not in _beat_actors(b, spec):
                f.append(F("ACTOR-INTERACTION", f"interaction {xid} {what} actor {e['actor']} is not in beat {b['id']}"))
            if e.get("prop") and e["prop"] not in props:
                f.append(F("ACTOR-INTERACTION", f"interaction {xid} {what} prop {e['prop']} is not in props[]"))
            return True
        if kind == "contact":
            if end_ok(x.get("a"), "a") and end_ok(x.get("b"), "b"):
                if not x["a"].get("actor") or not x["a"].get("point"):
                    f.append(F("ACTOR-INTERACTION", f"interaction {xid} a needs actor and point (hand_L, hand_R, ...)"))
                if x["b"].get("prop") and not (x["b"].get("held_by") or {}).get("actor"):
                    f.append(F("ACTOR-INTERACTION", f"interaction {xid} b is a prop: name the hand that holds it (held_by {{actor, hand}}), a hand to an object held by the other"))
                if x["b"].get("actor") and not x["b"].get("point"):
                    f.append(F("ACTOR-INTERACTION", f"interaction {xid} b needs a point (hand_L, hand_R, ...)"))
                if x["b"].get("actor") and x["b"].get("actor") == x["a"].get("actor"):
                    f.append(F("ACTOR-INTERACTION", f"interaction {xid} touches an actor with itself"))
            if float(x.get("tol_px", ACTOR["contact_tol_px"])) > 2 * ACTOR["contact_tol_px"]:
                f.append(F("ACTOR-INTERACTION", f"interaction {xid} tol_px {x.get('tol_px')} > {2 * ACTOR['contact_tol_px']:.0f} (a wider tolerance is not a contact)"))
        else:
            g, r = x.get("giver") or {}, x.get("receiver") or {}
            if x.get("prop") not in props:
                f.append(F("ACTOR-INTERACTION", f"handover {xid} prop {x.get('prop')!r} is not in props[]"))
            for who, e in (("giver", g), ("receiver", r)):
                if e.get("actor") not in ids or e.get("hand") not in HANDS:
                    f.append(F("ACTOR-INTERACTION", f"handover {xid} {who} needs a declared actor and hand L|R"))
            if g.get("actor") == r.get("actor"):
                f.append(F("ACTOR-INTERACTION", f"handover {xid} giver and receiver are the same actor"))
            hf = x.get("handoff_frame"); a0, a1 = round(float(x["t0"]) * fps), round(float(x["t1"]) * fps)
            if not isinstance(hf, int) or not a0 < hf < a1:
                f.append(F("ACTOR-INTERACTION", f"handover {xid} handoff_frame {hf!r} must be an integer frame strictly inside {a0}..{a1}"))
            n = x.get("both_hands_frames", ACTOR["handover_both_frames"])
            if not isinstance(n, int) or n < ACTOR["handover_both_frames"]:
                f.append(F("ACTOR-INTERACTION", f"handover {xid} both_hands_frames = {n!r} (need an integer >= {ACTOR['handover_both_frames']}: both hands on the prop before it changes hands)"))
            elif isinstance(hf, int) and hf - n < a0:
                f.append(F("ACTOR-INTERACTION", f"handover {xid} window starts {hf - a0} frames before the hand-off, both_hands_frames needs {n}"))
    return f

# ---- trace side
def _sframes(trace: dict) -> dict:
    return {fr["f"]: fr for fr in (trace.get("scene") or {}).get("frames", [])}

def _point(trace: dict, actor: str, name: str, f: int):
    ch = (trace.get("characters") or {}).get(actor) or {}
    fr = next((x for x in ch.get("frames", []) if x.get("f") == f), None)
    if fr is None:
        return None
    p = (fr.get("contact_points") or {}).get(name)
    return p if p is not None else (fr.get("anchors") or {}).get(name)

def _frame_of(trace: dict, actor: str, f: int):
    return next((x for x in ((trace.get("characters") or {}).get(actor) or {}).get("frames", []) if x.get("f") == f), None)

def _poly_gap(a, b) -> float:
    """Smallest distance between two polygons (0 when they overlap): vertex-to-edge both ways, and a vertex inside the other."""
    def inside(p, poly):
        c = False
        for i in range(len(poly)):
            x1, y1 = poly[i]; x2, y2 = poly[i - 1]
            if (y1 > p[1]) != (y2 > p[1]) and p[0] < (x2 - x1) * (p[1] - y1) / ((y2 - y1) or 1e-12) + x1:
                c = not c
        return c
    def seg(p, q, r):
        dx, dy = r[0] - q[0], r[1] - q[1]; L2 = dx * dx + dy * dy or 1e-12; t = max(0.0, min(1.0, ((p[0] - q[0]) * dx + (p[1] - q[1]) * dy) / L2))
        return math.hypot(p[0] - q[0] - t * dx, p[1] - q[1] - t * dy)
    if any(inside(p, b) for p in a) or any(inside(p, a) for p in b):
        return 0.0
    if not a or not b:
        return 1e9
    return min(min(min(seg(p, b[i - 1], b[i]) for i in range(len(b))) for p in a), min(min(seg(p, a[i - 1], a[i]) for i in range(len(a))) for p in b))

def _prop_at(sf, pid: str):
    return next((p for p in (sf or {}).get("props", []) if p.get("id") == pid), None)

def _parent_key(par):
    return (par.get("actor"), par.get("hand")) if isinstance(par, dict) else None

def rig_actors(trace: dict, spec: dict | None) -> list[str]:
    """ACTOR-TRACE, ACTOR-OCCLUSION, ACTOR-CONTACT, HANDOVER. Runs when the trace has a scene block, more than one character, or the spec declares 2+ actors."""
    chars = trace.get("characters") or {}; sc = trace.get("scene") or {}; ids = _actor_ids(spec)
    if not (sc or len(chars) > 1 or len(ids) > 1):
        return []
    if not sc.get("frames"):
        return [F("ACTOR-TRACE", f"trace has {len(chars)} characters but no scene.frames: the renderer must export the draw order, depths and props per frame (rig-trace.schema.json)")]
    f: list[str] = []; fps = float(trace.get("fps", 24))
    if ids and sorted(ids) != sorted(chars):
        f.append(F("ACTOR-TRACE", f"trace characters {sorted(chars)} differ from the spec's actors {sorted(ids)}"))
    sfr = _sframes(trace)
    for cid, ch in chars.items():
        fs = {x["f"] for x in ch.get("frames", [])}; sp = {k for k, v in sfr.items() if cid in (v.get("present") or [])}
        if fs != sp:
            f.append(F("ACTOR-TRACE", f"actor {cid} has {len(fs)} frames but scene.frames lists it present on {len(sp)} frames")); break
    pr = _presence(); sp_actors = {a.get("id"): a for a in ((spec or {}).get("actors") or [])}; nfs = (max(sfr) + 1) if sfr else 0
    for cid, ch in chars.items():   # declared frame ranges (spec actors[].frames) vs the frames the trace has for the actor
        a = sp_actors.get(cid)
        if a is not None and pr.declared(a) is not None and not pr.problems(pr.declared(a), nfs):
            want = set(pr.frames(a, nfs)); fs = {x["f"] for x in ch.get("frames", [])}
            if fs != want:
                f.append(F("ACTOR-RANGE", f"actor {cid} is traced on {len(fs)} frames, its declared frames {pr.declared(a)} are {len(want)} (missing {sorted(want - fs)[:4]}, extra {sorted(fs - want)[:4]})"))
    zlayer = {a.get("id"): a.get("layer", 0) for a in (sc.get("actors") or [])}
    n_bad = 0; msgs: list[str] = []
    for k in sorted(sfr):
        fr = sfr[k]; toks = fr.get("draw_order") or []; present = fr.get("present") or []; t = float(fr.get("t", k / fps)); why = None
        if not toks:
            why = "has no draw_order: nothing says who was drawn in front"
        else:
            names = [tk.split(":")[0] for tk in toks]; dep = fr.get("depth") or {}
            if sorted(set(names)) != sorted(present) or any(toks.count(f"{a}:{p}") != 1 for a in present for p in ("body", "arms")):
                why = f"draws {toks} for actors present {present}: each present actor is drawn once (body, arms), nobody else"
            elif any(a not in dep for a in present):
                why = f"has no depth for {[a for a in present if a not in dep]}"
            else:
                bodies = [tk.split(":")[0] for tk in toks if tk.endswith(":body")]
                for a, c in zip(bodies, bodies[1:]):
                    if dep[a] < dep[c] - ACTOR["z_eps"] or (abs(dep[a] - dep[c]) <= ACTOR["z_eps"] and zlayer.get(a, 0) >= zlayer.get(c, 0)):
                        why = f"{c} is drawn over {a} but {a} is nearer (depth {dep[a]} vs {dep[c]}): a character drawn through another"; break
                if why is None:
                    want = _declared_order(spec, t) if spec and spec.get("beats") else None
                    if want is not None:
                        exp = [tk for tk in _expand_tokens(want) if tk.split(":")[0] in present]
                        if exp != toks:
                            why = f"draw order {toks} differs from the declared {exp}"
                    elif _non_contiguous(toks):
                        why = f"interleaves {_non_contiguous(toks)} with no declared draw_order for this time: one actor's parts drawn on both sides of another's"
        if why:
            n_bad += 1
            if n_bad <= 4:
                msgs.append(F("ACTOR-OCCLUSION", f"frame {k} {why}"))
    f += msgs
    if n_bad > 4:
        f.append(F("ACTOR-OCCLUSION", f"... {n_bad - 4} more frames with a draw-order fault"))
    for x in (spec or {}).get("actor_interactions", []):
        xid = x.get("id", "?"); f0, f1 = round(float(x["t0"]) * fps), round(float(x["t1"]) * fps)
        if x.get("kind") == "contact":
            a, b = x["a"], x["b"]; tol = float(x.get("tol_px", ACTOR["contact_tol_px"])); worst, bad_n, first, nodata = 0.0, 0, None, None
            for k in range(f0, f1):
                pa = _point(trace, a["actor"], a["point"], k); pb = None
                if b.get("prop"):
                    pr = _prop_at(sfr.get(k), b["prop"])
                    if pr is not None:
                        hb = b.get("held_by") or {}
                        if _parent_key(pr.get("parent")) != (hb.get("actor"), hb.get("hand")):
                            f.append(F("ACTOR-CONTACT", f"{xid} frame {k} prop {b['prop']} is parented to {_parent_key(pr.get('parent'))}, the contact needs it held by {(hb.get('actor'), hb.get('hand'))}")); nodata = False; break
                        pts = pr.get("touch") or [pr.get("pos")]
                        pb = min(pts, key=lambda q: _dist(pa, q)) if pa is not None else None
                else:
                    pb = _point(trace, b["actor"], b["point"], k)
                if pa is None or pb is None:
                    nodata = k; break
                d = _dist(pa, pb); worst = max(worst, d)
                if d > tol:
                    bad_n += 1; first = first if first is not None else (k, d)
            if nodata is not None and nodata is not False:
                f.append(F("ACTOR-CONTACT", f"{xid} frame {nodata} has no data for the contact points (no data fails)"))
            if first:
                f.append(F("ACTOR-CONTACT", f"{xid} {bad_n} of {f1 - f0} frames miss by more than {tol:.0f} px (first frame {first[0]}: {first[1]:.1f} px, worst {worst:.1f} px)"))
        elif x.get("kind") == "apart":   # no-touch proof: the drawn hand outlines (trace hand_outline_px, canvas px) of the two actors never come closer than min_gap_px
            gap_min = float(x.get("min_gap_px", 1)); A, Bx = x["a"], x["b"]; worst, first, nd, bad_n = 1e9, None, None, 0
            both = 0
            for k in range(f0, f1):
                pa = _frame_of(trace, A["actor"], k); pb = _frame_of(trace, Bx["actor"], k)
                if pa is None or pb is None:   # an actor not in the frame (not present) has no hand to touch with
                    continue
                both += 1
                oa, ob = (pa or {}).get("hand_outline_px") or {}, (pb or {}).get("hand_outline_px") or {}
                for ha in A["hands"]:
                    for hb in Bx["hands"]:
                        if not oa.get(ha) or not ob.get(hb):
                            nd = nd if nd is not None else (k, ha, hb); continue
                        d = _poly_gap(oa[ha], ob[hb]); worst = min(worst, d)
                        if d < gap_min:
                            bad_n += 1; first = first or (k, ha, hb, d)
            if not both:
                f.append(F("ACTOR-CONTACT", f"{xid} has no frame with both {A['actor']} and {Bx['actor']} present in {f0}..{f1} (no data fails)"))
            if nd is not None:
                f.append(F("ACTOR-CONTACT", f"{xid} frame {nd[0]} has no hand outline for {A['actor']} {nd[1]} / {Bx['actor']} {nd[2]} (no data fails)"))
            if first:
                f.append(F("ACTOR-CONTACT", f"{xid} {A['actor']} hand {first[1]} and {Bx['actor']} hand {first[2]} come within {first[3]:.1f} px on frame {first[0]} (min {gap_min:.0f} px; {bad_n} hand pairs too close): a touch the spec says must not happen"))
        elif x.get("kind") == "handover":
            H, pid = x["handoff_frame"], x["prop"]; n = int(x.get("both_hands_frames", ACTOR["handover_both_frames"]))
            gk, rk = (x["giver"]["actor"], x["giver"]["hand"]), (x["receiver"]["actor"], x["receiver"]["hand"])
            ps = {k: _prop_at(sfr.get(k), pid) for k in range(f0, f1)}
            miss = [k for k, p in ps.items() if p is None]
            if miss:
                f.append(F("HANDOVER", f"{xid} prop {pid} is not in scene.props on frames {miss[:4]} (no data fails)")); continue
            wrong = [(k, _parent_key(p.get("parent"))) for k, p in ps.items() if _parent_key(p.get("parent")) != (gk if k < H else rk)]
            if wrong:
                k, par = wrong[0]
                f.append(F("HANDOVER", f"{xid} prop {pid} parent is {par} on frame {k}; it must be the giver {gk} before frame {H} and the receiver {rk} from frame {H} on ({len(wrong)} frames wrong)"))
            both = []
            for k in range(H - n, H):
                hs = {(h.get("actor"), h.get("hand")): h.get("gap_px", 1e9) for h in (ps.get(k) or {}).get("hands", [])}
                if not (hs.get(gk, 1e9) <= ACTOR["handover_gap_px"] and hs.get(rk, 1e9) <= ACTOR["handover_gap_px"]):
                    both.append(k)
            if both:
                f.append(F("HANDOVER", f"{xid} both hands are not on {pid} (gap <= {ACTOR['handover_gap_px']:.0f} px) on frames {both} of the {n} before the hand-off at {H}"))
            p0, p1 = ps.get(H - 1), ps.get(H)
            if p0 and p1:
                jump = _dist(p0["pos"], p1["pos"]); lim = float(x.get("max_jump_px", ACTOR["handover_jump_px"]))
                if jump > lim:
                    f.append(F("HANDOVER", f"{xid} prop {pid} jumps {jump:.1f} px at the hand-off frame {H} (max {lim:.0f}): it teleports between the hands"))
    return f

# ------------------------------------------------------------------ RENDER extras (frames as numpy arrays)
def rel_luminance(rgb):
    import numpy as np
    c = np.asarray(rgb, float) / 255.0
    c = np.where(c <= 0.03928, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * c[..., 0] + 0.7152 * c[..., 1] + 0.0722 * c[..., 2]

def wcag(l1: float, l2: float) -> float:
    a, b = max(l1, l2), min(l1, l2)
    return (a + 0.05) / (b + 0.05)

def _otsu_split(lum):
    import numpy as np
    v = lum.ravel(); lo, hi = float(v.min()), float(v.max())
    if hi - lo < 1e-6:
        return np.zeros_like(lum, bool)
    best, bt = -1, lo
    for t in np.linspace(lo, hi, 33)[1:-1]:
        a, b = v[v <= t], v[v > t]
        if len(a) == 0 or len(b) == 0:
            continue
        s = len(a) * len(b) * (a.mean() - b.mean()) ** 2
        if s > best:
            best, bt = s, t
    return lum > bt

def text_box_metrics(frame_rgb, box, height_px, scale, mask=None):
    """-> (contrast, texture_std, minority_share, used_mask). box in 1080x1920 px; frame is scaled by `scale`.
    With a 1-bit glyph mask (same size as the frame) the contrast is glyph vs ring; without, a two-mode fallback."""
    import numpy as np
    x, y, w, h = (int(round(box[k] * scale)) for k in ("x", "y", "w", "h"))
    ring = max(int(round(6 * scale)), 1); pad = int(round(0.5 * height_px * scale))
    H, W = frame_rgb.shape[:2]
    x0, y0, x1, y1 = max(x - ring, 0), max(y - ring, 0), min(x + w + ring, W), min(y + h + ring, H)
    lum = rel_luminance(frame_rgb)
    luma255 = (0.2126 * frame_rgb[..., 0] + 0.7152 * frame_rgb[..., 1] + 0.0722 * frame_rgb[..., 2]).astype(float)
    kx0, ky0, kx1, ky1 = max(x - pad, 0), max(y - pad, 0), min(x + w + pad, W), min(y + h + pad, H)
    if mask is not None:
        g = mask[ky0:ky1, kx0:kx1].astype(bool)
        region = luma255[ky0:ky1, kx0:kx1]
        bg = region[~g]
        texture = float(bg.std()) if bg.size else 0.0
        gl = lum[ky0:ky1, kx0:kx1]
        ringmask = np.zeros(lum.shape, bool); ringmask[y0:y1, x0:x1] = True; ringmask[y:y + h, x:x + w] = False
        if mask[y:y + h, x:x + w].any() and ringmask.any():
            c = wcag(float(lum[mask.astype(bool)].mean()), float(lum[ringmask & ~mask.astype(bool)].mean()))
        else:
            c = 1.0
        return c, texture, float(g.mean()) if g.size else 0.0, True
    sub = lum[y:y + h, x:x + w]
    if sub.size == 0:
        return 1.0, 0.0, 0.0, False
    cls = _otsu_split(sub); share = min(float(cls.mean()), 1 - float(cls.mean()))
    if share == 0:
        return 1.0, float(luma255[y:y + h, x:x + w].std()), 0.0, False
    minority = cls if cls.mean() < 0.5 else ~cls
    c = wcag(float(sub[minority].mean()), float(sub[~minority].mean()))
    r = luma255[y:y + h, x:x + w]
    return c, float(r[~minority].std()), share, False

def check_text_render(samples: list[dict], height_px: float, label: str) -> list[str]:
    """samples: [{'contrast','texture','share','mask'}] one per visible frame."""
    f = []
    if not samples:
        return [F("REND-TEXT-CONTRAST", f"text {label} has no visible frames to measure")]
    import numpy as np
    cs = [s["contrast"] for s in samples]; p10 = float(np.percentile(cs, 10))
    need = RENDER2["text_contrast_large"] if height_px >= 48 else RENDER2["text_contrast_p10"]
    note = "" if samples[0].get("mask") else " [fallback two-mode estimate, weaker than a text mask]"
    if p10 < need:
        f.append(F("REND-TEXT-CONTRAST", f"text {label} contrast p10 = {p10:.2f}:1 (need >= {need}:1){note} (R-336)"))
    tx = max(s["texture"] for s in samples)
    if tx > RENDER2["text_texture_max"]:
        f.append(F("REND-TEXT-TEXTURE", f"text {label} texture std in the knockout region = {tx:.1f}/255 (need <= 6): halftone/grain under the text (R-335)"))
    return f

def colour_stats(frames_rgb) -> dict:
    """Mean hue (deg, circular, saturation weighted), saturation, value and relative luma (0..1) over frames."""
    import numpy as np
    hs, ss, vs, ls = [], [], [], []
    for fr in frames_rgb:
        a = np.asarray(fr, float) / 255.0
        mx = a.max(-1); mn = a.min(-1); d = mx - mn
        s = np.where(mx > 0, d / np.maximum(mx, 1e-9), 0)
        r, g, b = a[..., 0], a[..., 1], a[..., 2]
        h = np.zeros_like(mx)
        m = d > 1e-9
        h = np.where(m & (mx == r), ((g - b) / np.maximum(d, 1e-9)) % 6, h)
        h = np.where(m & (mx == g), (b - r) / np.maximum(d, 1e-9) + 2, h)
        h = np.where(m & (mx == b), (r - g) / np.maximum(d, 1e-9) + 4, h)
        h = h * 60.0
        w = s
        if w.sum() > 1e-9:
            hs.append(math.degrees(math.atan2((np.sin(np.radians(h)) * w).sum(), (np.cos(np.radians(h)) * w).sum())) % 360)
        else:
            hs.append(0.0)
        ss.append(float(s.mean())); vs.append(float(mx.mean())); ls.append(float(rel_luminance(fr).mean()))
    cx = sum(math.cos(math.radians(h)) for h in hs); sx = sum(math.sin(math.radians(h)) for h in hs)
    return {"hue": math.degrees(math.atan2(sx, cx)) % 360 if hs else 0.0, "sat": float(sum(ss) / max(len(ss), 1)),
            "val": float(sum(vs) / max(len(vs), 1)), "luma": float(sum(ls) / max(len(ls), 1))}

def _hdiff(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)

def check_colour_script(stats: list[dict], spec: dict) -> list[str]:
    """stats: one dict per beat in order {'hue','sat','val','luma'}. R-370: change between differing emotions and match to declared target."""
    f = []; beats = spec.get("beats", [])
    for i, b in enumerate(beats):
        tgt = ((b.get("emotion_track") or {}).get("colour") or {}).get("target")
        if tgt and i < len(stats):
            s = stats[i]
            if "hue_deg" in tgt and _hdiff(s["hue"], tgt["hue_deg"]) > RENDER2["colour_target_hue"]:
                f.append(F("REND-COLOUR", f"beat {b['id']} measured hue {s['hue']:.0f} vs declared {tgt['hue_deg']} (tol 30) (R-370)"))
            if "sat" in tgt and abs(s["sat"] - tgt["sat"]) > RENDER2["colour_target_sv"]:
                f.append(F("REND-COLOUR", f"beat {b['id']} measured saturation {s['sat']:.2f} vs declared {tgt['sat']} (tol 0.2) (R-370)"))
            if "value" in tgt and abs(s["val"] - tgt["value"]) > RENDER2["colour_target_sv"]:
                f.append(F("REND-COLOUR", f"beat {b['id']} measured value {s['val']:.2f} vs declared {tgt['value']} (tol 0.2) (R-370)"))
        if i > 0 and i < len(stats):
            pe = (beats[i - 1].get("emotion") or {}).get("primary"); ce = (b.get("emotion") or {}).get("primary")
            if pe and ce and pe != ce:
                a, c = stats[i - 1], stats[i]
                rel = lambda x, y: abs(x - y) / max(x, y, 1e-9)
                if not (_hdiff(a["hue"], c["hue"]) >= RENDER2["colour_hue_deg"] or rel(a["sat"], c["sat"]) >= RENDER2["colour_rel"]
                        or rel(a["luma"], c["luma"]) >= RENDER2["colour_rel"]):
                    f.append(F("REND-COLOUR", f"beats {beats[i - 1]['id']}->{b['id']} change emotion {pe}->{ce} but the measured colour barely moves (hue {_hdiff(a['hue'], c['hue']):.0f} deg, sat {rel(a['sat'], c['sat']):.0%}, luma {rel(a['luma'], c['luma']):.0%}) (R-370)"))
    return f

# ---------------------------------------------------------------- 2D look (R-380, the owner 2026-10-23: "2D, not 3D")
# Measured on 540x960 luma frames sampled at 2 fps. Calibrated on Mix v2 (liked, closer to 2D) vs Mix v3 (went 3D).
LOOK2D = {"min_hard_edge": 0.08,   # share of pixels on a hard step (luma step >= 0.10 per px): ink line + cel edges
          "max_ramp_area": 0.03,   # share of 24 px blocks that vary by >= 0.10 luma with no hard step inside: smooth volume ramps
          "block": 24, "hard_step": 0.10, "ramp_range": 0.10, "ramp_edge_max": 0.06}

def look2d_frame(lum) -> dict:
    """lum: (h,w) float luma 0..1. Returns hard_edge and ramp_area shares for one frame."""
    import numpy as np
    L = np.asarray(lum, np.float32)
    g = np.zeros_like(L)
    g[:-1, :-1] = np.maximum(np.abs(np.diff(L, axis=1))[:-1, :], np.abs(np.diff(L, axis=0))[:, :-1])
    B = LOOK2D["block"]; H = L.shape[0] // B; W = L.shape[1] // B
    if H == 0 or W == 0:
        return {"hard_edge": float((g >= LOOK2D["hard_step"]).mean()), "ramp_area": 0.0}
    bl = L[:H * B, :W * B].reshape(H, B, W, B).transpose(0, 2, 1, 3).reshape(H, W, B * B)
    bg = g[:H * B, :W * B].reshape(H, B, W, B).transpose(0, 2, 1, 3).reshape(H, W, B * B)
    ramp = ((bl.max(-1) - bl.min(-1)) >= LOOK2D["ramp_range"]) & (bg.max(-1) < LOOK2D["ramp_edge_max"])
    return {"hard_edge": float((g >= LOOK2D["hard_step"]).mean()), "ramp_area": float(ramp.mean())}

def look2d_metrics(frames_lum) -> dict:
    ms = [look2d_frame(f) for f in frames_lum]
    if not ms:
        return {"hard_edge": 0.0, "ramp_area": 0.0, "frames": 0}
    return {"hard_edge": sum(m["hard_edge"] for m in ms) / len(ms), "ramp_area": sum(m["ramp_area"] for m in ms) / len(ms), "frames": len(ms)}

def check_look2d(m: dict) -> list[str]:
    f = []
    if m["hard_edge"] < LOOK2D["min_hard_edge"]:
        f.append(F("LOOK2D-LINE", f"hard-edge share {m['hard_edge']:.3f} < {LOOK2D['min_hard_edge']}: ink line and cel edges lost or replaced by soft shading (R-380)"))
    if m["ramp_area"] > LOOK2D["max_ramp_area"]:
        f.append(F("LOOK2D-RAMP", f"smooth-ramp area {m['ramp_area']:.3f} > {LOOK2D['max_ramp_area']}: lit-volume gradients instead of flat or 2-3 step cel tone (R-380)"))
    return f

def check_shadow_flat(spec: dict) -> list[str]:
    """R-380: the mass proxy shapes the shadow; the shadow is drawn as a flat shape. Fails only when a spec asks for a soft edge."""
    f = []
    for b in spec.get("beats", []):
        for s in b.get("cast_shadows", []):
            if str(s.get("edge", "hard")).lower() in ("soft", "blur", "gaussian") or float(s.get("blur_px") or 0) > 2:
                f.append(F("SHADOW-FLAT", f"beat {b.get('id','?')} shadow of {s.get('caster')} has a soft/blurred edge: draw it as a flat 2D shape (edge 'hard' or 'cel') (R-380)"))
    return f
