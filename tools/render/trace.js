/* ===== Mix v5 rig trace (kb/quality/rig-trace.schema.json + gate-spec L), masks (shadow, text, line art), recorder, sheets 07, 08 =====
   New in v5: hand_pose per hand (grip id, contact kind, thumb mode, blend, topology, every finger's joints, axis, wrist, holding,
   grip layers, digit-to-object distances, DRAWN forearm length), props with faces / facing / marks, the writing block, cut and smear. */
const r2 = v => +(+v).toFixed(2);
const scr = (R0, q) => { const p = toScreen(R0, q); return [r2(p[0]), r2(p[1])]; };
const scrW = w => { const p = P(w[0], w[1], w[2]); return [r2(p.x), r2(p.y)]; };
function viewOf(s) { const y = s.twist || 0; return Math.abs(y) < 3 ? "front" : y > 0 ? "three-quarter-R" : "three-quarter-L"; }
const CUT_F = SHOT.cuts, SMEAR_F = SHOT.smears;   // from shot.json: cut frames and drawn smear frames
function segDist(p, a, b) { const d = sub2(b, a), L2 = d[0] * d[0] + d[1] * d[1] || 1, k = clamp(((p[0] - a[0]) * d[0] + (p[1] - a[1]) * d[1]) / L2, 0, 1); return len2(sub2(p, add2(a, mul2(d, k)))); }
function polyDist(p, poly) { let inside = false; for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) { const a = poly[i], b = poly[j];
    if ((a[1] > p[1]) !== (b[1] > p[1]) && p[0] < (b[0] - a[0]) * (p[1] - a[1]) / (b[1] - a[1]) + a[0]) inside = !inside; }
  if (inside) return 0; let d = 1e9; for (let i = 0; i < poly.length; i++) d = Math.min(d, segDist(p, poly[i], poly[(i + 1) % poly.length])); return d; }
/* one hand as drawn: toS maps the hand's HU coordinates to canvas px */
function handPoseRec(A, toS, k, objPoly) {
  const P0 = A.pose, fingers = {thumb: P0.thumb.fl.map(r2)}; for (const f of FING) fingers[f] = P0.fingers[f].fl.map(r2);
  const w = toS(A.W), e = toS(A.E), kn = toS(A.map([.44, 0])), ax = Math.atan2(kn[1] - w[1], kn[0] - w[0]);
  const rec = {id: P0.id.replace(new RegExp("^" + CHAR.id + "/hand/"), ""), mirrored: false, contact_kind: P0.kind, pinch: !!P0.pinch, topo: {fingers: 4, order: DIGITS.slice()}, fingers,
               orient_deg: r2(deg(ax)), wrist_px: w.map(r2), forearm_drawn_px: r2(len2(sub2(w, e))), forearm_drawn_hu: r2(len2(sub2(A.W, A.E)))};
  if (P0.blend) rec.blend = {to_id: P0.blend.to_id.replace(new RegExp("^" + CHAR.id + "/hand/"), ""), to_kind: P0.blend.to_kind, k: P0.blend.k};
  if (P0.holding) {
    rec.holding = P0.holding; rec.grip_layers = P0.layers;
    const pad = d => toS(A.map(A.hl[d].pad)), gc = {};
    if (P0.holding === "pen") { const pn = P0.pen, a = toS(A.map(pn.tip)), b = toS(A.map(pn.rear)), r = pn.r * k;
      for (const d of ["thumb", "index", "middle"]) gc[d] = r2(Math.max(0, segDist(pad(d), a, b) - r)); }
    else if (objPoly) for (const d of P0.holding === "card" ? ["index", "middle"] : ["thumb", "index"]) gc[d] = r2(polyDist(pad(d), objPoly));
    rec.grip_contacts = gc;
  }
  return rec;
}
const ID = s => s.replace(new RegExp("^" + CHAR.id + "/hand/"), "");
function traceFrame(L) {
  const {f, R} = L, t = f / FPS, R0 = R.R0, sim = SIM[f], s = R.s;
  const rec = {f, t: +t.toFixed(4), view: L.view, joints: {}, bend_side: {}, segments_px: {}, anchors: {}, contact_points: {}, contacts: [], arm_elevation_deg: {}, shoulder_lift_px: {}};
  if (CUT_F.includes(f)) rec.cut = true;
  if (SMEAR_F.includes(f)) rec.smear = true;
  for (const sd of ["L", "R"]) { const A = R.arm[sd];
    rec.joints["shoulder_flex_" + sd] = r2(A.elev); rec.joints["elbow_flex_" + sd] = r2(A.elbow); rec.joints["wrist_flex_" + sd] = r2(A.wflex); rec.joints["wrist_dev_" + sd] = r2(A.wdev);
    const fl = FING.map(k => A.pose.fingers[k].fl);   // the limit check reads the largest flex of the four fingers; hand_pose carries every finger
    rec.joints["finger_mcp_" + sd] = r2(Math.max(...fl.map(x => x[0]))); rec.joints["finger_pip_" + sd] = r2(Math.max(...fl.map(x => x[1]))); rec.joints["finger_dip_" + sd] = r2(Math.max(...fl.map(x => x[2])));
    rec.bend_side["elbow_" + sd] = A.bendSide;
    rec.segments_px["upper_arm_" + sd] = r2(len2(sub2(A.E, A.S)) * 100); rec.segments_px["forearm_" + sd] = r2(len2(sub2(A.W, A.E)) * 100);
    rec.arm_elevation_deg[sd] = r2(A.elev); rec.shoulder_lift_px[sd] = r2(R.lift[sd] * 100);
    rec.anchors["shoulder_" + sd] = [r2(A.Sc[0] * 100), r2(A.Sc[1] * 100)];
  }
  rec.joints.neck_flex = r2(sim.neck.flex); rec.joints.neck_rot = r2(sim.neck.rot); rec.joints.neck_tilt = r2(sim.neck.tilt);
  rec.joints.trunk_flex = r2(s.flex); rec.joints.trunk_rot = r2(s.twist); rec.joints.hip_flex_L = rec.joints.hip_flex_R = r2(s.flex); rec.joints.knee_flex_L = rec.joints.knee_flex_R = 4;
  rec.segments_px.neck = 32;
  const sy = (rec.anchors.shoulder_L[1] + rec.anchors.shoulder_R[1]) / 2;
  rec.anchors.torso_center = [0, r2(sy)]; rec.torso_half_width_px = HALFW * 100; rec.clavicle_y = r2(sy); rec.neck_length_px = 32;
  /* attachments (screen px of the body solve): children are built on their anchors (constraints, R-351) */
  const hL = R.arm.L, hR = R.arm.R;
  rec.anchors.pen_rest_L = scr(R0, hL.map(hL.pose.pen.rest)); rec.contact_points.pen_grip = scr(R0, hL.map(hL.pose.pen.rest));
  rec.anchors.pinch_R = scr(R0, hR.contact);
  if (t < 3.0) { rec.anchors.press_R = scr(R0, hR.contact); rec.contact_points.card_press = scr(R0, hR.T); }
  if (sim.tagHeld) { const F = bagTagFrame(Object.assign({}, sim, {R0Now: R0}), R); if (F) rec.contact_points.bag_tag_grip = scrW(F.grip); }
  if (sim.bag && L.view === "ms" && L.bagF) { const h = tagHoleW(L.bagF); rec.anchors.string_end = scrW(h); rec.contact_points.tag_hole = scrW(h); }
  rec.anchors.cap_band_front = scr(R0, R.capFront || R.head([0, -.45])); rec.contact_points.cap_band = rec.anchors.cap_band_front;
  rec.anchors.cap_crown = scr(R0, R.crown || R.head([0, -.61])); rec.contact_points.cloth_crown = rec.anchors.cap_crown;
  rec.anchors.cross_point = scr(R0, R.pin || R.head([.28, .32])); rec.contact_points.pin_mid = rec.anchors.cross_point;
  const nm = lerp2(R.NB, R.NT, .5); rec.anchors.neck_front = scr(R0, nm); rec.contact_points.drape_neck = scr(R0, nm);
  rec.anchors.shelf_L = scr(R0, R.shelf.L); rec.contact_points.drape_shelf_L = scr(R0, R.drapeLow[0]);
  rec.anchors.shelf_R = scr(R0, R.shelf.R); rec.contact_points.drape_shelf_R = scr(R0, R.drapeLow[R.drapeLow.length - 1]);
  rec.anchors.coat_shoulder_L = scr(R0, R.endAnchor); rec.contact_points.end_fold_L = scr(R0, R.endPts[2]);
  /* declared hand contacts, body px (1 HU = 100 px), 2D arm: the contact point the IK placed vs its target */
  const Cn = (id, A) => rec.contacts.push({id, point: [r2(A.contact[0] * 100), r2(A.contact[1] * 100)], target: [r2(A.T[0] * 100), r2(A.T[1] * 100)], shoulder: [r2(A.S[0] * 100), r2(A.S[1] * 100)], limb_len_px: (UA + FA) * 100});
  if (t < 3.0) { Cn("nib-on-card", hL); Cn("pads-on-card", hR); }
  if (t >= 5.1 && t < 6.875) Cn("heel-on-counter", hR);
  if (sim.tagHeld) Cn("pinch-bag-tag", hR);
  rec.layer_order = {angle: L.angle, order: L.order};
  const segs = [[R.HC, .081], [R.chest([0, -1.8]), .46], [[0, 1.0], .37]];
  for (const sd of ["L", "R"]) { const A = R.arm[sd]; segs.push([lerp2(A.S, A.E, .5), .027], [lerp2(A.E, A.W, .5), .016], [A.map([.4, 0]), .006]); }
  const m = segs.reduce((a, [, w]) => a + w, 0), com = segs.reduce((a, [p, w]) => add2(a, mul2(p, w / m)), [0, 0]);
  rec.com = [r2(com[0] * 100), r2(com[1] * 100)];
  let sup = [-44, 44]; if (t >= 5.1 && t < 6.875) { const hx = hR.contact[0] * 100; sup = [Math.min(sup[0], hx), Math.max(sup[1], hx)]; }
  rec.support_x = sup.map(r2);
  const fc = sim.face, controls = {}; for (const k of ["1", "2", "4", "5", "6", "7", "9", "12", "15", "20", "23", "26"]) controls["AU" + k] = +fc.au[k].toFixed(4);
  rec.face = {eye_x: +fc.eyeX.toFixed(4), eye_y: +fc.eyeY.toFixed(4), head_yaw: +sim.headYaw.toFixed(3), blink: fc.blink, mouth_open: R.mouth ? +R.mouth.open.toFixed(3) : 0,
              viseme: sim.viseme ? sim.viseme.id : null, viseme_w: sim.viseme ? +sim.viseme.w.toFixed(3) : 0, mouth: mouthRec(R.mouth), gaze_target: t < 2.42 ? "nib" : t < 3 ? "chute/bag" : t < 4.625 ? "bag" : t < 8.3 ? "bag-tag" : t < 8.75 ? "chute" : "bag-tag", controls};
  /* ---- hands as drawn (none in the POV close-up: no hand is drawn there) ---- */
  const cs = sim.cs || cardState(t);
  if (L.view === "ms") {
    const toS = q => scr(R0, q), cardPoly = cardOutlineMM(2).map(q => scrW(cardW(q[0], q[1], cs))), tagPoly = L.bagF ? tagCorners(L.bagF).map(scrW) : null;
    rec.hand_pose = {L: handPoseRec(hL, toS, R0.k, null), R: handPoseRec(hR, toS, R0.k, hR.pose.holding === "card" ? cardPoly : tagPoly)};
  } else if (L.view === "top") {
    const ins = sim.ins, mk = rig => q => [r2(rig.R0.x + q[0] * rig.R0.k), r2(rig.R0.y + q[1] * rig.R0.k)]; IC = L.ic;
    const cardPoly = cardOutlineMM(2).map(q => ipW(cardW(q[0], q[1], cs)));
    rec.hand_pose = {L: handPoseRec(ins.L, mk(L.rigs.L), L.rigs.L.R0.k, null), R: handPoseRec(ins.R, mk(L.rigs.R), L.rigs.R.R0.k, cardPoly)};
    rec.segments_px.forearm_drawn_L = r2(len2(sub2(ins.L.W, ins.L.E)) * 100); rec.segments_px.forearm_drawn_R = r2(len2(sub2(ins.R.W, ins.R.E)) * 100);
  }
  if (L.view === "ms" && R && R.arm) rec.art = artMeasure(R, ["L", "R"]);   // ART-PROPORTION: hand, head and face sizes as drawn (hands.js)
  if (L.view === "ms") { rec.segments_px.forearm_drawn_L = r2(len2(sub2(hL.W, hL.E)) * 100); rec.segments_px.forearm_drawn_R = r2(len2(sub2(hR.W, hR.E)) * 100); }
  /* ---- two-sided props (R-387): faces, the face the camera sees, every mark and whether it is drawn ---- */
  const cardF = cardFacing(L.view === "ms" ? "ms" : "pov"), cardDrawn = L.view !== "pov", nb = sim.nib;
  const cardQuad = (L.view === "top" ? (IC = L.ic, [[-62.5, -39], [62.5, -39], [62.5, 39], [-62.5, 39]].map(q => ipW(cardW(q[0], q[1], cs)).map(r2))) : L.view === "ms" ? [[-62.5, -39], [62.5, -39], [62.5, 39], [-62.5, 39]].map(q => scrW(cardW(q[0], q[1], cs))) : null);
  rec.props = [{id: "card", faces: CARDJ.faces, facing: cardF, quad_px: cardQuad, marks: [{id: "ink-khurz-asfar", face: "front", kind: "ink", drawn: cardDrawn && cardF === "front" && nb.ink > 0}, {id: "ruled-line", face: "front", kind: "print", drawn: cardDrawn && cardF === "front"}]}];
  if (sim.bag) { const tf = bagTagFacing(L.view === "pov" ? "pov" : "ms"), drawnTag = L.view !== "top";
    rec.props.push({id: "bag-tag", faces: TAGJ.faces, facing: tf, marks: [{id: "name", face: "front", kind: "ink", drawn: drawnTag && tf === "front"}, {id: "date", face: "front", kind: "ink", drawn: drawnTag && tf === "front"}, {id: "stamp", face: "back", kind: "print", drawn: drawnTag && tf === "back"}]}); }
  /* ---- the writing (b1): nib, the paper under it, the leading end of the revealed ink (R-389..R-391) ---- */
  if (f < 72) {
    const proj = L.view === "top" ? ((q, h) => ipW(cardW(q[0], q[1], cs), h / 1000)) : ((q, h) => scrW(cardW(q[0], q[1], cs, h)));
    const nib = proj(nb.p, nb.h).map(r2), paper = proj(nb.p, 0).map(r2), end = nb.ink > 0 ? inkEnd(nb.ink) : null;
    rec.writing = {prop: "card", active: !!nb.active, direction: "rtl", nib_face: "front", nib_px: nib, paper_px: paper, nib_gap_px: r2(len2(sub2(nib, paper))),
                   on_paper: Math.abs(nb.p[0]) <= CARD.w / 2 && Math.abs(nb.p[1]) <= CARD.h / 2, drawn_to_px: end ? proj(end, 0).map(r2) : null,
                   ink_len_px: r2(nb.ink * IC_NOMINAL_PX_PER_MM), nib_h_mm: r2(nb.h), phase: nb.phase};
  }
  /* ---- seams (every 6th frame): front shots as v4; the insert has wrists, elbows and finger roots; the POV has no character ---- */
  if (f % 6 === 0 && L.view !== "pov") {
    rec.shadow_mask = `masks/shadow/${String(f).padStart(4, "0")}.png`;
    rec.line_mask = `masks/line/${String(f).padStart(4, "0")}.png`;
    const seams = [], ov = ["wrist_L", "wrist_R"];
    const add = (A, sc, k, withShoulder) => { const sd = A.sd;
      if (withShoulder) seams.push({id: "shoulder_" + sd, parts: ["coat", "upper-arm-" + sd], at: sc(A.S), from: sc(A.S), to: sc(A.E), r_px: r2(.1 * k)});
      seams.push({id: "elbow_" + sd, parts: ["upper-arm-" + sd, "forearm-" + sd], at: sc(A.E), from: sc(A.S), to: sc(A.W), r_px: r2(.1 * k)});
      seams.push({id: "wrist_" + sd, parts: ["forearm-" + sd, "palm-" + sd], at: sc(A.W), from: sc(A.E), to: sc(A.map([.44, 0])), r_px: r2(.1 * k)});
      for (const fn of DIGITS) { const pts = A.hl[fn].pts; seams.push({id: `root_${fn}_${sd}`, parts: ["palm-" + sd, fn === "thumb" ? "thumb-" + sd : `finger-${fn}-${sd}`], at: sc(A.map(pts[fn === "thumb" ? 1 : 0])), from: sc(A.map(pts[0])), to: sc(A.map(pts[fn === "thumb" ? 2 : 1])), r_px: r2((fn === "thumb" ? .04 : .03) * k)}); } };
    if (L.view === "ms") {
      for (const sd of ["L", "R"]) add(R.arm[sd], q => scr(R0, q), R0.k, true);
      seams.push({id: "head_neck", parts: ["head", "neck"], kind: "head-neck", via: "hijab (head-cloth and drape are one garment outline over the neck)", at: scr(R0, lerp2(R.NB, R.NT, .5)), from: scr(R0, R.NB), to: scr(R0, R.HC), r_px: r2(.1 * R0.k)});
      ov.push("shoulder_L"); rec.overlap_why = {wrist_L: "the sleeve opening lies over the wrist", wrist_R: "the sleeve opening lies over the wrist", shoulder_L: "the thrown-back scarf end lies across her left shoulder"};
    } else {
      for (const sd of ["L", "R"]) { const rig = L.rigs[sd]; add(sim.ins[sd], q => [r2(rig.R0.x + q[0] * rig.R0.k), r2(rig.R0.y + q[1] * rig.R0.k)], rig.R0.k, false); }
      rec.overlap_why = {wrist_L: "the sleeve opening lies over the wrist", wrist_R: "the sleeve opening lies over the wrist"};
    }
    rec.seams = seams; rec.overlaps = ov;
  } else if (f % 6 === 0) rec.shadow_mask = `masks/shadow/${String(f).padStart(4, "0")}.png`;
  return rec;
}
const IC_NOMINAL_PX_PER_MM = 3.8;   // ink length unit: card mm at the insert's nominal 3800 px/m (constant, so the length never shrinks at a cut)
let TAGJ = null;
function tagHoleW(F) { const c = Math.cos(F.ang), s = Math.sin(F.ang); return [F.o[0] + TAGW / 2 * c - .012 * s, F.o[1] + TAGW / 2 * s + .012 * c, F.o[2]]; }
/* ---------- masks ---------- */
const OFF = {}; function off(name, w, h) { if (!OFF[name]) { const c = document.createElement("canvas"); c.width = w; c.height = h; OFF[name] = c; } return OFF[name]; }
function lineMask(f) {   // ink strokes of the character only (no fills, no props, no text): alpha = ink, half size
  const L = LAST && LAST.f === f ? LAST : renderFrame(f), keep = ctx, oc = off("line", 540, 960);
  ctx = oc.getContext("2d"); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, 540, 960); ctx.scale(.5, .5);
  if (L.view === "top") { const g = ctx; ctx = keep; insertMask(L, g); return oc; }
  ctx.translate(W / 2, H / 2); ctx.rotate(C.roll); ctx.translate(-W / 2, -H / 2);
  MODE = "mask";
  CHAR.drawBody(L.R, L.cutY); CHAR.drawArms(L.R, {pen: () => {}, "bag-tag": () => {}}, {angle: L.angle});
  MODE = "color"; ctx = keep; return oc;
}
function shadowMask(f) {   // receiver plane Z = 3.6: 1080 x 960 px, 200 px per metre, origin x -2.7, y -3.2
  const L = LAST && LAST.f === f ? LAST : renderFrame(f), oc = off("smask", 1080, 960), g = oc.getContext("2d");
  g.setTransform(1, 0, 0, 1, 0, 0); g.fillStyle = "#000"; g.fillRect(0, 0, 1080, 960); setLights(f);
  g.beginPath(); for (const p of CHAR.massProxyOnPlane(L.R, ZP)) { p.forEach((q, i) => { const x = (q[0] + 2.7) * 200, y = (q[1] + 3.2) * 200; i ? g.lineTo(x, y) : g.moveTo(x, y); }); g.closePath(); }
  g.fillStyle = "#fff"; g.fill("nonzero"); return oc;
}
function textMask(f) {
  const L = LAST && LAST.f === f ? LAST : renderFrame(f), t = f / FPS, oc = off("tmask", W, H), g = oc.getContext("2d");
  g.setTransform(1, 0, 0, 1, 0, 0); g.fillStyle = "#000"; g.fillRect(0, 0, W, H);
  if (L.view !== "pov" || t < TEXT.t0 - 1e-6 || t > TEXT.t1 + 1e-6) return {canvas: oc, any: false};
  povTextMask(f, g);   // glyphs dilated 2-2.5 px so codec ringing at the glyph edge is not counted as plate texture
  return {canvas: oc, any: true};
}
/* ---------- recorder (posts to tools/record/server.py; the clock is the frame counter, never wall time) ---------- */
async function post(url, body, type) { let last;
  for (let k = 0; k < 5; k++) { try { const r = await fetch(url, {method: "POST", body, headers: {"Content-Type": type || "application/octet-stream"}}); if (r.ok) return; last = new Error(url + " " + r.status); } catch (e) { last = e; } await new Promise(r => setTimeout(r, 300 * (k + 1))); }
  throw last; }
const blobOf = c => new Promise(res => c.toBlob(res, "image/png"));
async function record(opts = {}) {
  const from = opts.from || 0, to = opts.to == null ? NF : opts.to, st = window.__rec = {done: false, f: from, err: null, ms: []};
  try {
    const trace = {fps: FPS, canvas: {w: W, h: H}, units: "joints deg; segments, shoulder anchors, torso_center, clavicle_y, com, support_x, contacts in BODY px (1 HU = 100 px); attachment anchors, contact_points and seams in SCREEN px of the frame",
      characters: {[CHAR.id]: {profile: CHAR.physics_profile, head_unit_px: 100, rest_lengths_px: {upper_arm_L: CHAR.rest_lengths_hu.upper_arm * 100, upper_arm_R: CHAR.rest_lengths_hu.upper_arm * 100, forearm_L: CHAR.rest_lengths_hu.forearm * 100, forearm_R: CHAR.rest_lengths_hu.forearm * 100, forearm_drawn_L: CHAR.rest_lengths_hu.forearm * 100, forearm_drawn_R: CHAR.rest_lengths_hu.forearm * 100, neck: Math.round(CHAR.proportions_hu.neck_len * 100)}, frames: []}},
      units_v5: "hand_pose wrist_px / forearm_drawn_px / grip_contacts, writing and props in CANVAS px of the shot as drawn (front, top-pov insert); segments_px.forearm_drawn_* = drawn forearm in body px (constant = the rig length); writing.ink_len_px = card mm x 3.8 (nominal, never rescaled at a cut)"};
    if (opts.video !== false) await post("/start", JSON.stringify({name: opts.name || SHOT.id, from}), "application/json");
    for (let f = from; f < to; f++) {
      st.f = f; const t0 = performance.now(); const L = renderFrame(f); st.ms.push(performance.now() - t0);
      if (opts.video !== false) await post("/frame?i=" + f, await blobOf(cv));
      if (opts.data === false) continue;   // video-only pass (stage record); the trace pass (stage trace) sets video:false
      trace.characters[CHAR.id].frames.push(traceFrame(L));
      const tm = textMask(f); if (tm.any) await post("/mask?kind=text&i=" + f, await blobOf(tm.canvas));
      if (f % 6 === 0) { await post("/mask?kind=shadow&i=" + f, await blobOf(shadowMask(f))); if (L.view !== "pov") await post("/mask?kind=line&i=" + f, await blobOf(lineMask(f))); renderFrame(f); }
    }
    if (opts.video !== false) await post("/finish", "{}", "application/json");
    if (opts.data !== false) await post("/trace", JSON.stringify(trace), "application/json");
    st.done = true;
  } catch (e) { st.err = String(e && e.stack || e); }
  return st;
}
async function still(f, name) { renderFrame(f); await post("/png?name=" + (name || "f" + String(f).padStart(3, "0")), await blobOf(cv)); }
async function stillMask(f) { renderFrame(f); const c = lineMask(f); await post("/png?name=mask" + String(f).padStart(3, "0"), await blobOf(c)); }
