/* ===== Multi-actor rig trace, masks and recorder (the counterpart of trace.js for shots with `actors` in shot.json) =====
   trace.characters[<actor id>] = {profile, head_unit_px, rest_lengths_px, frames[]}: joints, per-finger hand_pose, faces, seams, shadow and line masks
   (masks/shadow/<actor>/NNNN.png, masks/line/<actor>/NNNN.png), contact points and anchors, all of that actor only.
   trace.scene = {actors[{id, module, z}], frames[{f, t, present[], draw_order[], depth{}, props[]}]}: what no single actor owns: the order the actors were
   DRAWN in (tokens "id:body" / "id:arms"), each actor's depth that frame, and the props with the hand each one is parented to.
   Schema: kb/quality/rig-trace.schema.json, checks ACTOR-CONTACT / HANDOVER / ACTOR-OCCLUSION: kb/quality/gate-spec.md (section N).
   Scene contract (see tools/templates/shot-multi/scene/main.js): PLAN, SIM, buildSim, renderFrame(f) -> L with
   L = {f, cam?, actors: {id: {R, s, angle, view, cutY, extras, holdPoly?}}, draw_calls[], props[]}, LAST; optional traceExtra(id, rec, q, L). */
"use strict";
const r2 = v => +(+v).toFixed(2);
const toScr = (R0, p) => [r2(R0.x + p[0] * R0.k), r2(R0.y + p[1] * R0.k)];
const CUT_F = SHOT.cuts || [], SMEAR_F = SHOT.smears || [];
/* Presence (shot.json actors[].present = [[f0, f1), ...], default every frame): an actor that enters, exits or is cut between is traced, and its masks are
   written, on its own frames only. The scene's renderFrame must put an actor in L.actors exactly on those frames; record() refuses a mismatch (TRACE-INCOMPLETE). */
const PRESENT = Object.fromEntries((SHOT.actors || []).map(a => { const r = a.present || a.frames; return [a.id, r ? (f => r.some(p => f >= p[0] && f < p[1])) : (() => true)]; }));
const isPresent = (id, f) => (PRESENT[id] || (() => true))(f);
function segDist(p, a, b) { const d = sub2(b, a), L2 = d[0] * d[0] + d[1] * d[1] || 1, k = clamp(((p[0] - a[0]) * d[0] + (p[1] - a[1]) * d[1]) / L2, 0, 1); return len2(sub2(p, add2(a, mul2(d, k)))); }
function polyDist(p, poly) { let inside = false; for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) { const a = poly[i], b = poly[j];
    if ((a[1] > p[1]) !== (b[1] > p[1]) && p[0] < (b[0] - a[0]) * (p[1] - a[1]) / (b[1] - a[1]) + a[0]) inside = !inside; }
  if (inside) return 0; let d = 1e9; for (let i = 0; i < poly.length; i++) d = Math.min(d, segDist(p, poly[i], poly[(i + 1) % poly.length])); return d; }
/* one hand as drawn (same numbers as trace.js handPoseRec): toS maps the hand's HU coordinates to canvas px; objPoly = the held object's outline, if any */
function handRec(A, toS, k, objPoly) {
  const P0 = A.pose, fingers = {thumb: P0.thumb.fl.map(r2)}; for (const f of FING) fingers[f] = P0.fingers[f].fl.map(r2);
  const w = toS(A.W), e = toS(A.E), kn = toS(A.map([.44, 0])), ax = Math.atan2(kn[1] - w[1], kn[0] - w[0]), strip = new RegExp("^" + CHAR.id + "/hand/");
  const rec = {id: P0.id.replace(strip, ""), mirrored: false, contact_kind: P0.kind, pinch: !!P0.pinch, topo: {fingers: 4, order: DIGITS.slice()}, fingers,
               orient_deg: r2(deg(ax)), wrist_px: w.map(r2), forearm_drawn_px: r2(len2(sub2(w, e))), forearm_drawn_hu: r2(len2(sub2(A.W, A.E)))};
  if (P0.blend) rec.blend = {to_id: P0.blend.to_id.replace(strip, ""), to_kind: P0.blend.to_kind, k: P0.blend.k};
  if (P0.holding) {
    rec.holding = P0.holding; rec.grip_layers = P0.layers;
    const pad = d => toS(A.map(A.hl[d].pad)), gc = {};
    if (P0.holding === "pen" && P0.pen) { const pn = P0.pen, a = toS(A.map(pn.tip)), b = toS(A.map(pn.rear)), r = pn.r * k;
      for (const d of ["thumb", "index", "middle"]) gc[d] = r2(Math.max(0, segDist(pad(d), a, b) - r)); }
    else if (objPoly) for (const d of P0.holding === "card" ? ["index", "middle"] : ["thumb", "index"]) gc[d] = r2(polyDist(pad(d), objPoly));
    rec.grip_contacts = gc;
  }
  return rec;
}
const FACE_AUS = ["1", "2", "4", "5", "6", "7", "9", "12", "15", "20", "23", "26"];
/* one actor's frame record. Reads only what a character module's solve() returns (R.arm[side], R.chest, R.HC, R.NB, R.NT, R.lift) and the actor's pose state s. */
function actorTraceFrame(id, L) {
  const q = L.actors[id], mod = ACTORS[id].mod;
  return withActor(id, () => {
    const R = q.R, s = R.s, R0 = R.R0, f = L.f, t = f / FPS, sides = CHAR.sides || ["L", "R"], nk = s.neck || {};
    const rec = {f, t: +t.toFixed(4), view: q.view || "front", joints: {}, bend_side: {}, segments_px: {}, anchors: {}, contact_points: {}, contacts: [], arm_elevation_deg: {}, shoulder_lift_px: {}};
    if (CUT_F.includes(f)) rec.cut = true;
    if (SMEAR_F.includes(f)) rec.smear = true;
    for (const sd of sides) { const A = R.arm[sd];
      rec.joints["shoulder_flex_" + sd] = r2(A.elev); rec.joints["elbow_flex_" + sd] = r2(A.elbow); rec.joints["wrist_flex_" + sd] = r2(A.wflex); rec.joints["wrist_dev_" + sd] = r2(A.wdev);
      const fl = FING.map(k => A.pose.fingers[k].fl);
      rec.joints["finger_mcp_" + sd] = r2(Math.max(...fl.map(x => x[0]))); rec.joints["finger_pip_" + sd] = r2(Math.max(...fl.map(x => x[1]))); rec.joints["finger_dip_" + sd] = r2(Math.max(...fl.map(x => x[2])));
      rec.bend_side["elbow_" + sd] = A.bendSide;
      rec.segments_px["upper_arm_" + sd] = r2(len2(sub2(A.E, A.S)) * 100); rec.segments_px["forearm_" + sd] = r2(len2(sub2(A.W, A.E)) * 100);
      rec.segments_px["forearm_drawn_" + sd] = rec.segments_px["forearm_" + sd];
      rec.arm_elevation_deg[sd] = r2(A.elev); rec.shoulder_lift_px[sd] = r2(R.lift[sd] * 100);
      rec.anchors["shoulder_" + sd] = [r2(A.Sc[0] * 100), r2(A.Sc[1] * 100)];
      rec.anchors["wrist_" + sd] = toScr(R0, A.W);
      rec.contact_points["hand_" + sd] = toScr(R0, A.contact);   // the point of the hand that touches (pads, palm, heel, pinch): what ACTOR-CONTACT compares
    }
    rec.anchors.face_center = toScr(R0, R.HC);
    rec.joints.neck_flex = r2(nk.flex || 0); rec.joints.neck_rot = r2(nk.rot || 0); rec.joints.neck_tilt = r2(nk.tilt || 0);
    rec.joints.trunk_flex = r2(s.flex || 0); rec.joints.trunk_rot = r2(s.twist || 0); rec.joints.hip_flex_L = rec.joints.hip_flex_R = r2(s.flex || 0); rec.joints.knee_flex_L = rec.joints.knee_flex_R = 4;
    rec.segments_px.neck = R.NB && R.NT ? r2(len2(sub2(R.NT, R.NB)) * 100) : r2(CHAR.proportions_hu.neck_len * 100);
    const sy = sides.reduce((a, sd) => a + rec.anchors["shoulder_" + sd][1], 0) / sides.length;
    rec.anchors.torso_center = [0, r2(sy)]; rec.torso_half_width_px = (CHAR.torso_half_width_hu || CHAR.proportions_hu.shoulder_w / 2) * 100; rec.clavicle_y = r2(sy); rec.neck_length_px = rec.segments_px.neck;
    /* declared reaches: the scene names the hands that are placed on a target (s.hands[side].contact = id); the IK point vs its target, body px */
    for (const sd of sides) { const A = R.arm[sd], h = (s.hands || {})[sd] || {};
      if (h.contact) rec.contacts.push({id: h.contact, point: [r2(A.contact[0] * 100), r2(A.contact[1] * 100)], target: [r2(A.T[0] * 100), r2(A.T[1] * 100)], shoulder: [r2(A.S[0] * 100), r2(A.S[1] * 100)], limb_len_px: (CHAR.rest_lengths_hu.upper_arm + CHAR.rest_lengths_hu.forearm) * 100}); }
    rec.layer_order = {angle: q.angle || "front", order: mod.layerOrder.get().slice()};
    const segs = [[R.HC, .081], [R.chest([0, -1.8]), .46], [[0, 1.0], .37]];
    for (const sd of sides) { const A = R.arm[sd]; segs.push([lerp2(A.S, A.E, .5), .027], [lerp2(A.E, A.W, .5), .016], [A.map([.4, 0]), .006]); }
    const m = segs.reduce((a, [, w]) => a + w, 0), com = segs.reduce((a, [p, w]) => add2(a, mul2(p, w / m)), [0, 0]);
    rec.com = [r2(com[0] * 100), r2(com[1] * 100)]; rec.support_x = (q.support_x || [-44, 44]).map(r2);
    const fc = s.face || {au: {}}, controls = {}; for (const k of FACE_AUS) controls["AU" + k] = +((fc.au || {})[k] || 0).toFixed(4);
    rec.face = {eye_x: +(fc.eyeX || 0).toFixed(4), eye_y: +(fc.eyeY || 0).toFixed(4), head_yaw: +(s.headYaw || 0).toFixed(3), blink: fc.blink || 0, mouth_open: R.mouth ? +R.mouth.open.toFixed(3) : 0,
                viseme: s.viseme ? s.viseme.id : null, viseme_w: s.viseme ? +s.viseme.w.toFixed(3) : 0, mouth: mouthRec(R.mouth), gaze_target: q.gaze || s.gazeTarget || "", controls};
    const toS = p => toScr(R0, p), hp = {};
    for (const sd of sides) hp[sd] = handRec(R.arm[sd], toS, R0.k, q.holdPoly ? q.holdPoly[sd] : null);
    rec.hand_pose = hp;
    rec.art = artMeasure(R, sides);   // ART-PROPORTION: hand, head and face sizes as drawn (hands.js)
    if (f % 6 === 0) {
      const dir = String(f).padStart(4, "0");
      rec.shadow_mask = `masks/shadow/${id}/${dir}.png`; rec.line_mask = `masks/line/${id}/${dir}.png`;
      const seams = [], add = (A, sc, k, withShoulder) => { const sd = A.sd;
        if (withShoulder) seams.push({id: "shoulder_" + sd, parts: ["body", "upper-arm-" + sd], at: sc(A.S), from: sc(A.S), to: sc(A.E), r_px: r2(.1 * k)});
        seams.push({id: "elbow_" + sd, parts: ["upper-arm-" + sd, "forearm-" + sd], at: sc(A.E), from: sc(A.S), to: sc(A.W), r_px: r2(.1 * k)});
        seams.push({id: "wrist_" + sd, parts: ["forearm-" + sd, "palm-" + sd], at: sc(A.W), from: sc(A.E), to: sc(A.map([.44, 0])), r_px: r2(.1 * k)});
        for (const fn of DIGITS) { const pts = A.hl[fn].pts; seams.push({id: `root_${fn}_${sd}`, parts: ["palm-" + sd, fn === "thumb" ? "thumb-" + sd : `finger-${fn}-${sd}`], at: sc(A.map(pts[fn === "thumb" ? 1 : 0])), from: sc(A.map(pts[0])), to: sc(A.map(pts[fn === "thumb" ? 2 : 1])), r_px: r2((fn === "thumb" ? .04 : .03) * k)}); } };
      for (const sd of sides) add(R.arm[sd], toS, R0.k, mod.seams_shoulder !== false);
      rec.seams = seams;
      const ov = mod.seam_overlaps || {}; if (Object.keys(ov).length) { rec.overlaps = Object.keys(ov); rec.overlap_why = ov; }
    }
    if (typeof traceExtra === "function") traceExtra(id, rec, q, L);
    return rec;
  });
}
function sceneTraceFrame(L) {
  const present = ACTOR_IDS.filter(id => L.actors[id]), f = L.f;
  return {f, t: +(f / FPS).toFixed(4), present, draw_order: (L.draw_calls || []).slice(), depth: Object.fromEntries(present.map(id => [id, +depthAt(id, f).toFixed(4)])),
          props: (L.props || []).map(p => ({id: p.id, pos: p.pos.map(r2), parent: p.parent || null, hands: (p.hands || []).map(h => ({actor: h.actor, hand: h.hand, gap_px: r2(h.gap_px)})), touch: (p.touch || []).map(a => a.map(r2))}))};
}
/* ---------- masks (per actor) ---------- */
const OFF = {}; function off(name, w, h) { if (!OFF[name]) { const c = document.createElement("canvas"); c.width = w; c.height = h; OFF[name] = c; } return OFF[name]; }
const noExtras = ex => Object.fromEntries(Object.keys(ex || {}).map(k => [k, () => {}]));
function lineMask(id, f) {   // ink strokes of ONE actor, half size; no other actor, no props
  const L = LAST && LAST.f === f ? LAST : renderFrame(f), keep = ctx, oc = off("line", 540, 960), q = L.actors[id];
  ctx = oc.getContext("2d"); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, 540, 960); ctx.scale(.5, .5);
  ctx.translate(W / 2, H / 2); ctx.rotate(C.roll || 0); ctx.translate(-W / 2, -H / 2);
  MODE = "mask";
  withActor(id, () => { CHAR.drawBody(q.R, q.cutY); CHAR.drawArms(q.R, noExtras(q.extras), Object.assign({angle: q.angle}, q.opts || {})); });
  MODE = "color"; ctx = keep; return oc;
}
function shadowMask(id, f) {   // receiver plane Z = ZP (the world's back unit): 1080 x 960 px, 200 px per metre, origin x -2.7, y -3.2
  const L = LAST && LAST.f === f ? LAST : renderFrame(f), oc = off("smask", 1080, 960), g = oc.getContext("2d"), q = L.actors[id];
  g.setTransform(1, 0, 0, 1, 0, 0); g.fillStyle = "#000"; g.fillRect(0, 0, 1080, 960); if (typeof setLights === "function") setLights(f);
  g.beginPath(); withActor(id, () => { for (const p of CHAR.massProxyOnPlane(q.R, ZP)) { p.forEach((v, i) => { const x = (v[0] + 2.7) * 200, y = (v[1] + 3.2) * 200; i ? g.lineTo(x, y) : g.moveTo(x, y); }); g.closePath(); } });
  g.fillStyle = "#fff"; g.fill("nonzero"); return oc;
}
/* ---------- recorder (posts to tools/record/server.py; the clock is the frame counter) ---------- */
async function post(url, body, type) { let last;
  for (let k = 0; k < 5; k++) { try { const r = await fetch(url, {method: "POST", body, headers: {"Content-Type": type || "application/octet-stream"}}); if (r.ok) return; last = new Error(url + " " + r.status); } catch (e) { last = e; } await new Promise(r => setTimeout(r, 300 * (k + 1))); }
  throw last; }
const blobOf = c => new Promise(res => c.toBlob(res, "image/png"));
async function record(opts = {}) {
  const from = opts.from || 0, to = opts.to == null ? NF : opts.to, st = window.__rec = {done: false, f: from, err: null, ms: []};
  try {
    const trace = {fps: FPS, canvas: {w: W, h: H}, units: "joints deg; segments, shoulder anchors, torso_center, clavicle_y, com, support_x, contacts in BODY px (1 HU = 100 px); anchors, contact_points, seams, props in SCREEN px of the frame",
      characters: {}, scene: {actors: ACTOR_IDS.map(id => ({id, module: ACTORS[id].mod.id, z: ACTORS[id].z, layer: ACTORS[id].layer})), frames: []}};
    for (const id of ACTOR_IDS) { const m = ACTORS[id].mod, rl = m.rest_lengths_hu, o = {};
      for (const sd of m.sides) { o["upper_arm_" + sd] = rl.upper_arm * 100; o["forearm_" + sd] = rl.forearm * 100; o["forearm_drawn_" + sd] = rl.forearm * 100; }
      o.neck = Math.round(m.proportions_hu.neck_len * 100);
      trace.characters[id] = {profile: m.physics_profile, module: m.id, head_unit_px: 100, rest_lengths_px: o, frames: []}; }
    if (opts.video !== false) await post("/start", JSON.stringify({name: opts.name || SHOT.id, from}), "application/json");
    for (let f = from; f < to; f++) {
      st.f = f; const t0 = performance.now(); const L = renderFrame(f); st.ms.push(performance.now() - t0);
      for (const id of ACTOR_IDS) if (!!L.actors[id] !== isPresent(id, f)) throw new Error(`actor ${id} is declared ${isPresent(id, f) ? "present" : "absent"} on frame ${f} (shot.json actors[].present) but renderFrame ${L.actors[id] ? "drew" : "omitted"} it`);
      if (opts.video !== false) await post("/frame?i=" + f, await blobOf(cv));
      if (opts.data === false) continue;
      for (const id of ACTOR_IDS) if (L.actors[id]) trace.characters[id].frames.push(actorTraceFrame(id, L));
      trace.scene.frames.push(sceneTraceFrame(L));
      if (f % 6 === 0) for (const id of ACTOR_IDS) if (L.actors[id]) {
        await post(`/mask?kind=shadow&actor=${id}&i=${f}`, await blobOf(shadowMask(id, f)));
        await post(`/mask?kind=line&actor=${id}&i=${f}`, await blobOf(lineMask(id, f)));
        renderFrame(f); }
    }
    if (opts.video !== false) await post("/finish", "{}", "application/json");
    if (opts.data !== false) await post("/trace", JSON.stringify(trace), "application/json");
    st.done = true;
  } catch (e) { st.err = String(e && e.stack || e); }
  return st;
}
async function still(f, name) { renderFrame(f); await post("/png?name=" + (name || "f" + String(f).padStart(3, "0")), await blobOf(cv)); }
