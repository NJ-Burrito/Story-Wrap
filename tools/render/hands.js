/* ===== Hands (catalogue <char>/v3/hands; character-agnostic, all data in HM3 and GRIPS): constant topology, digits solved onto the held object, continuous blends =====
   R-383 topology fixed (4 fingers + thumb, 3 bones each, constant lengths); R-384 continuity; R-385 grips authored per hand;
   R-386 every grip / contact / thumb-mode change is a k-blend of joint angles and of the contact offset (no flag flips mid-blend);
   R-392 the grip declares its layer order and digit contacts.
   Hand frame (u, r) in head units: u toward the knuckles, r toward the thumb side. Dorsal projection: a phalanx at cumulative
   flex c is drawn L*cos(c) long, so a curled finger dips toward the paper and reads short, but its bones never change. */
"use strict";
const DIGITS = ["thumb", "index", "middle", "ring", "little"], FING = ["index", "middle", "ring", "little"];
let HM3 = null, GRIPS = {};
let FD_ART = null;   // the character's ART-BOOK face file (its module's data.face): bootstrap.js / actors.js assign it next to FD
const unit2 = v => { const n = Math.hypot(v[0], v[1]) || 1; return [v[0] / n, v[1] / n]; };
const wrapA = a => Math.atan2(Math.sin(a), Math.cos(a));
function fingerChain(f, fl, a0) {
  const K = HM3.knuckles_ur[f], Lp = HM3.phalanges_hu[f];
  let p = [K[0], K[1]], c = 0; const pts = [p];
  for (let i = 0; i < 3; i++) { c += fl[i]; const a = a0 + rad(c) * HM3.curl_in_plane, l = Lp[i] * clamp(Math.cos(rad(c)), HM3.cos_floor, 1);
    p = [p[0] + Math.cos(a) * l, p[1] + Math.sin(a) * l]; pts.push(p); }
  return {pts, pad: lerp2(pts[2], pts[3], HM3.pad_at.finger)};
}
function thumbChain(fl, a0) {   // fl = [cmc, mcp, ip], degrees of in-plane turn toward the fingers; seen from its side, full bone lengths
  const T = HM3.thumb, Ls = [T.metacarpal, T.proximal, T.distal]; let p = [T.cmc_ur[0], T.cmc_ur[1]], a = a0; const pts = [p];
  for (let i = 0; i < 3; i++) { a -= rad(fl[i]); p = [p[0] + Math.cos(a) * Ls[i], p[1] + Math.sin(a) * Ls[i]]; pts.push(p); }
  return {pts, pad: lerp2(pts[2], pts[3], HM3.pad_at.thumb)};
}
/* a holding thumb: the metacarpal (inside the palm) at a fixed angle, MCP and IP solved as two bones whose knuckle bulges radially */
function solveThumb(metaDeg, target) {
  const T = HM3.thumb, am = rad(metaDeg), M = [T.cmc_ur[0] + Math.cos(am) * T.metacarpal, T.cmc_ur[1] + Math.sin(am) * T.metacarpal];
  const sol = ik2(M, target, T.proximal, T.distal * HM3.pad_at.thumb, 1), aJ = Math.atan2(sol.E[1] - M[1], sol.E[0] - M[0]), aT = Math.atan2(sol.W[1] - sol.E[1], sol.W[0] - sol.E[0]);
  const fl = [0, deg(wrapA(am - aJ)), deg(wrapA(aJ - aT))], out = thumbChain(fl, am);
  return {fl, a0: am, miss: len2(sub2(out.pad, target))};
}
/* digit solve: flex scale s by bisection on the reach (first crossing, so it moves continuously with the target), then one rotation */
function solveDigit(chain, ratio, target, sMax = 1.7) {
  const fl = s => ratio.map(r => r * s), K = chain(fl(0), 0).pts[0], d = len2(sub2(target, K)), reach = s => len2(sub2(chain(fl(s), 0).pad, K));
  let s = 0;
  if (reach(0) > d) { let prev = 0; s = sMax;
    for (let i = 1; i <= 64; i++) { const si = sMax * i / 64; if (reach(si) <= d) { let a = prev, b = si; for (let k = 0; k < 32; k++) { const m = (a + b) / 2; if (reach(m) <= d) b = m; else a = m; } s = (a + b) / 2; break; } prev = si; } }
  const pad0 = chain(fl(s), 0).pad, a0 = wrapA(Math.atan2(target[1] - K[1], target[0] - K[0]) - Math.atan2(pad0[1] - K[1], pad0[0] - K[0]));
  const out = chain(fl(s), a0);
  return {fl: fl(s), a0, miss: len2(sub2(out.pad, target)), s};
}
const thumbA0 = abd => rad(HM3.thumb.rest_dir_deg + (abd - 35) * .5);
/* a grip pose: joint angles of every digit (solved where the grip has a contact), wrist, contact offset, pen */
function gripPose(id, o = {}) {
  const G = GRIPS[id]; if (!G) throw new Error("no grip " + id);
  const P = {id, kind: G.contact_kind, holding: G.holding || null, pinch: G.thumb_mode === "pinch", fingers: {}, thumb: null, wrist: {flex: G.wrist.flex, dev: G.wrist.dev}, pen: null, layers: G.grip_layers || null, miss: {}};
  if (G.pen) {
    const tip = add2(G.pen.tip_ur, o.penShift || [0, 0]), rest = G.pen.rest_ur, dir = unit2(sub2(rest, tip));
    let n = [-dir[1], dir[0]]; if (n[1] < 0) n = [dir[1], -dir[0]];
    P.pen = {tip, rest, dir, n, rear: add2(tip, mul2(dir, G.pen.projected_len_hu)), r: G.pen.radius_hu, len: G.pen.projected_len_hu, rearH: G.pen.len_m * Math.sin(rad(G.pen.lean_deg_from_paper))};
  }
  const target = dg => { const c = (G.digit_contacts || {})[dg]; if (!c || !P.pen) return null; return add2(add2(P.pen.tip, mul2(P.pen.dir, c.along_hu)), mul2(P.pen.n, c.side_hu)); };
  for (const f of FING) {
    const T = target(f);
    if (T) { const s = solveDigit((fl, a) => fingerChain(f, fl, a), G.flex_ratio[f], T); P.fingers[f] = {fl: s.fl, a0: s.a0}; P.miss[f] = s.miss; }
    else { const g = G.fingers[f]; P.fingers[f] = {fl: g.flex.slice(), a0: rad(-g.spread * .6)}; }
  }
  if (G.thumb_mode === "on-object" && target("thumb")) { const s = solveThumb(G.thumb_meta_deg, target("thumb")); P.thumb = {fl: s.fl, a0: s.a0}; P.miss.thumb = s.miss; }
  else if (G.thumb_mode === "pinch") { const ip = fingerChain("index", P.fingers.index.fl, P.fingers.index.a0).pad, T = [ip[0] - .01, ip[1] + G.pinch_gap_hu];
    const s = solveThumb(G.thumb_meta_deg, T); P.thumb = {fl: s.fl, a0: s.a0}; P.miss.thumb = s.miss; }
  else P.thumb = {fl: G.thumb.flex.slice(), a0: thumbA0(G.thumb.abd)};
  P.contact = contactOf(P);
  return P;
}
function handGeom(P) {
  const out = {}; for (const f of FING) out[f] = fingerChain(f, P.fingers[f].fl, P.fingers[f].a0);
  out.thumb = thumbChain(P.thumb.fl, P.thumb.a0); return out;
}
function contactOf(P) {
  const g = handGeom(P);
  if (P.kind === "pen-tip") return P.pen.tip.slice();
  if (P.kind === "pinch") return lerp2(g.index.pad, g.thumb.pad, .5);
  if (P.kind === "pads") return lerp2(g.index.pad, g.middle.pad, .5);
  if (P.kind === "heel") return HM3.heel_ur.slice();
  return HM3.palm_point_ur.slice();
}
/* blend: every number moves on the same k; the reported id / kind / pinch stay the FROM grip's until k reaches 1 (R-386) */
function blendPose(A, B, k) {
  if (!B || k <= 0) return A; if (k >= 1) return B;
  const la = (x, y) => lerp(x, y, k), aa = (x, y) => x + wrapA(y - x) * k, dj = (a, b) => ({fl: a.fl.map((v, i) => la(v, b.fl[i])), a0: aa(a.a0, b.a0)});
  const P = {id: A.id, kind: A.kind, holding: A.holding, pinch: A.pinch, layers: A.layers, fingers: {}, thumb: dj(A.thumb, B.thumb),
             wrist: {flex: la(A.wrist.flex, B.wrist.flex), dev: la(A.wrist.dev, B.wrist.dev)}, pen: A.pen || B.pen, miss: {},
             contact: lerp2(A.contact, B.contact, k), blend: {to_id: B.id, to_kind: B.kind, k: +k.toFixed(4)}};
  for (const f of FING) P.fingers[f] = dj(A.fingers[f], B.fingers[f]);
  return P;
}
/* the arm in the drawing plane: two bones of constant length (the drawn forearm never breathes, F13-d); the hand angle is the
   forearm angle plus the wrist flex; the target is where the pose's contact point must land (nib, pads, pinch, heel) */
function solveArm2D(S, T, pose, rs, bend, ua, fa, hs) {
  const off = mul2(pose.contact, hs), wf = rad(pose.wrist.flex) * rs;
  let ah = Math.atan2(T[1] - S[1], T[0] - S[0]), sol;
  const solve = a => { const U = [Math.cos(a), Math.sin(a)], Rv = [-Math.sin(a) * rs, Math.cos(a) * rs]; return ik2(S, sub2(T, add2(mul2(U, off[0]), mul2(Rv, off[1]))), ua, fa, bend); };
  for (let it = 0; it < 48; it++) { sol = solve(ah); const fa2 = Math.atan2(sol.W[1] - sol.E[1], sol.W[0] - sol.E[0]); ah += .35 * wrapA(fa2 + wf - ah); }
  sol = solve(ah);
  const U = [Math.cos(ah), Math.sin(ah)], Rv = [-Math.sin(ah) * rs, Math.cos(ah) * rs], W0 = sol.W;
  const map = q => add2(W0, add2(mul2(U, q[0] * hs), mul2(Rv, q[1] * hs)));
  return {S, E: sol.E, W: W0, miss: sol.miss, ah, U, Rv, map, contact: map(pose.contact)};
}
/* ART-PROPORTION (owner, 2026-10-25: the art book is the reference): what the film actually draws, in head units, measured from the hand's own geometry (A.map of the straight middle finger
   and of the knuckle span: pose-independent) plus the face-feature sizes of the face data in play times the multipliers the character module reports (CHAR.artScale(R)). The gate
   (qg_checks ART-PROPORTION) divides by head_h_hu and compares with catalogue/characters/<id>/artbook-proportions.json. */
/* close profiles draw the face at the art book's SIZES: nose, lips and eyes take their dimensions from the art-book face file whatever later face version the shot names
   (a later version may have fuller lips or a bolder nose; the art book is the reference). Tones, ink, brows and placement stay the shot's. */
const ART_FACE_KEYS = {nose: ["wing_x", "wing_y", "base_w", "tip_y", "bridge_top_y"], lips: ["half_w", "upper_t", "lower_t"], eyes: ["w", "h", "iris_r", "lash_w"]}, ART_FD_CACHE = new WeakMap();
function artFaceFD(fd, art) {
  if (!fd || !art || fd === art) return fd; let c = ART_FD_CACHE.get(fd); if (c) return c;
  c = Object.assign({}, fd); for (const g in ART_FACE_KEYS) { c[g] = Object.assign({}, fd[g]); for (const k of ART_FACE_KEYS[g]) if (art[g] && art[g][k] !== undefined) c[g][k] = art[g][k]; }
  ART_FD_CACHE.set(fd, c); return c;
}
function artMeasure(R, sides) {
  const sc = Object.assign({hand: 1, finger: 1, head: 1, nose: 1, lips: 1, eyes: 1, handK: 1}, CHAR.artScale ? CHAR.artScale(R) : {}), r4 = v => +(+v).toFixed(4);
  const out = {film: sc.film ? sc.film : R.film ? R.film.name : ((typeof SHOT !== "undefined" && SHOT && SHOT.film) || "v1"), head_h_hu: r4((CHAR.proportions_hu.head_h || 1) * sc.head), hand_len_hu: {}, hand_w_hu: {}, finger_r_hu: {}};
  const K = HM3.knuckles_ur, Lp = HM3.phalanges_hu.middle, tip = [K.middle[0] + Lp[0] + Lp[1] + Lp[2], K.middle[1]];
  for (const sd of sides) { const A = R.arm[sd], M = q => A.map([q[0] * sc.handK, q[1] * sc.handK]), o = M([0, 0]);
    out.hand_len_hu[sd] = r4(len2(sub2(M(tip), o))); out.hand_w_hu[sd] = r4(len2(sub2(M(K.index), M(K.little)))); out.finger_r_hu[sd] = r4(HM3.radii_hu.finger[0] * sc.finger); }
  const fd = typeof FD !== "undefined" && FD ? (sc.artFace ? artFaceFD(FD, FD_ART) : FD) : null;
  if (fd && fd.nose && fd.lips && fd.eyes) {
    out.nose_w_hu = r4(2 * fd.nose.wing_x * sc.nose); out.nose_len_hu = r4((fd.nose.tip_y - fd.nose.bridge_top_y) * sc.nose);
    out.lips_w_hu = r4(2 * fd.lips.half_w * sc.lips); out.lips_t_hu = r4((fd.lips.upper_t + fd.lips.lower_t) * sc.lips);
    out.eye_w_hu = r4(fd.eyes.w * sc.eyes); out.eye_h_hu = r4(fd.eyes.h * sc.eyes); }
  return out;
}
