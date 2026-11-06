/* ===== Catalogue sheet drawing, character-agnostic and world-agnostic (driven by tools/sheets.py; contract in characters/README.md and worlds/README.md).
   Everything here is black, white and greys: ink strokes, flat grey tone steps, hatching. The module (CHAR.sheet / WORLD.sheet) supplies the geometry
   (figure shapes, hands, props, places); this file lays the sheets out, draws the shared kinds (mannequin, face, expressions, grids) and measures
   what it drew, so ARTBOOK-MATCH compares drawn numbers, not declared ones. Output: SVG strings in page units 1754 x 1240 (A4 landscape at 150 dpi). ===== */
"use strict";
const Sheets = (() => {
  const PW = 1754, PH = 1240, SM = 56;
  const GREY = {g1: "#ececec", g2: "#cfcfcf", g3: "#a8a8a8", g4: "#7a7a7a"};
  const fillOf = n => !n || n === "paper" ? "#fff" : n === "none" ? "none" : n === "ink" ? "#111" : (GREY[n] || n);
  const X = s => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const SERIF = "thmanyahserifdisplay, serif", SERIFT = "thmanyahseriftext, serif";
  const J = u => fetch(u).then(r => { if (!r.ok) throw new Error(u + " " + r.status); return r.json(); });
  const r3 = v => Math.round(v * 1000) / 1000;
  let FRAME = null;   // current page object

  /* ---------- page, text, frames ---------- */
  function newPage(id, title, sub, num, total, who) {
    const g = new SvgCtx(), P = {id, title, g, regions: {}, labels: [], num};
    g.lineJoin = g.lineCap = "round"; g.strokeStyle = "#000"; g.lineWidth = 6; g.strokeRect(14, 14, PW - 28, PH - 28); g.lineWidth = 1.6; g.strokeRect(26, 26, PW - 52, PH - 52);
    g.text(SM, 94, X(title), 50, {font: SERIF, weight: 900}); P.labels.push(title);
    g.text(SM, 128, X(sub), 19, {}); P.labels.push(sub);
    g.fillStyle = "#000"; g.beginPath(); g.roundRect(PW - SM - 120, 56, 120, 44, 4); g.fill(); g.text(PW - SM - 60, 87, `${String(num).padStart(2, "0")} / ${String(total).padStart(2, "0")}`, 22, {anchor: "middle", fill: "#fff", weight: 700});
    g.text(SM, PH - 38, X(`Story-Wrap · Art Book · ${who} · black ink only · 150 dpi page, 300 dpi export`), 13, {fill: "#555"});
    FRAME = P; return P;
  }
  function T(P, x, y, s, size = 17, o = {}) { P.g.text(x, y, X(s), size, o); P.labels.push(s); }
  function wrapText(P, x, y, s, size, maxW, lh, o = {}) {
    const words = String(s).split(" "), per = Math.max(10, Math.floor(maxW / (size * .52))); let line = "", yy = y;
    for (const w of words) { if ((line + " " + w).length > per && line) { T(P, x, yy, line, size, o); yy += lh; line = w; } else line = line ? line + " " + w : w; }
    if (line) { T(P, x, yy, line, size, o); yy += lh; } return yy;
  }
  function box(g, x, y, w, h, lw = 3, fill) { g.beginPath(); g.rect(x, y, w, h); if (fill) { g.fillStyle = fill; g.fill(); } g.lineWidth = lw; g.strokeStyle = "#000"; g.stroke(); }
  function cellTitle(P, x, y, s, sub) { T(P, x, y, s, 24, {font: SERIF, weight: 700}); if (sub) T(P, x, y + 22, sub, 15, {fill: "#444"}); }
  function region(P, key, x, y, w, h) { P.regions[key] = [Math.round(x), Math.round(y), Math.round(w), Math.round(h)]; }

  /* ---------- path helpers (HU or page units, whichever transform is active) ---------- */
  function pathOf(g, pts, closed = true, sm = false, k = .5) {
    ctx = g;   // core.smooth draws on the global ctx
    g.beginPath();
    if (sm && pts.length > 2) smooth(pts, closed, k); else { pts.forEach((p, i) => i ? g.lineTo(p[0], p[1]) : g.moveTo(p[0], p[1])); if (closed) g.closePath(); }
  }
  function hatchIn(g, pts, ang, gap, lw, sm, k) { Ink.hatch(g, pts, ang, gap, lw, {smooth: sm, k}); }   // shared ink helper (svgctx.js)
  /* a shape record: {id, pts, closed, smooth, k, fill, lw, hatch:{a,gap,w}, dash, holes:[pts], line:0|1} -> ink */
  function drawShape(g, s, lw) {
    if (s.kind === "face") return;
    const closed = s.closed !== false, sm = !!s.smooth;
    pathOf(g, s.pts, closed, sm, s.k || .5);
    if (s.holes) for (const h of s.holes) { ctx = g; if (sm) smooth(h, true, s.k || .5); else { h.forEach((p, i) => i ? g.lineTo(p[0], p[1]) : g.moveTo(p[0], p[1])); g.closePath(); } }
    if (closed && s.fill !== "none") { g.fillStyle = fillOf(s.fill); g.fill(s.holes ? "evenodd" : undefined); }
    if (s.hatch && closed) { const hp = s.pts; g.save(); if (s.holes) { pathOf(g, s.pts, true, sm, s.k || .5); for (const h of s.holes) { ctx = g; h.forEach((p, i) => i ? g.lineTo(p[0], p[1]) : g.moveTo(p[0], p[1])); g.closePath(); } g.clip("evenodd"); g.beginPath();
        const r = hp.reduce((m, p) => Math.max(m, Math.hypot(p[0], p[1])), 0) + 1, a = (s.hatch.a || 45) * Math.PI / 180; for (let d = -r; d <= r; d += s.hatch.gap || .07) { g.moveTo(-Math.sin(a) * d - Math.cos(a) * r, Math.cos(a) * d - Math.sin(a) * r); g.lineTo(-Math.sin(a) * d + Math.cos(a) * r, Math.cos(a) * d + Math.sin(a) * r); }
        g.lineWidth = lw * (s.hatch.w || .5); g.strokeStyle = "#000"; g.stroke(); } else hatchIn(g, hp, s.hatch.a || 45, s.hatch.gap || .07, lw * (s.hatch.w || .5), sm, s.k || .5); g.restore(); }
    if (s.line !== 0) { pathOf(g, s.pts, closed, sm, s.k || .5); if (s.holes) for (const h of s.holes) { ctx = g; h.forEach((p, i) => i ? g.lineTo(p[0], p[1]) : g.moveTo(p[0], p[1])); g.closePath(); }
      g.setLineDash(s.dash || []); g.lineWidth = lw * (s.lw || 1); g.strokeStyle = "#000"; g.stroke(); g.setLineDash([]); }
  }
  /* a figure from the module: shapes in HU (origin pelvis, y down), drawn back to front; face shapes call the shared face drawer */
  function drawFig(g, fig, ox, oy, k, o = {}) {
    const lw = (o.lw || 2.2) / k; g.save(); g.translate(ox, oy); g.scale(k, k); g.lineJoin = g.lineCap = "round"; MODE = "sheet";
    for (const s of fig.shapes) { if (s.kind === "face") { faceHead(g, s.yaw || 0, s.face || {}, s.c, s.fill, lw); continue; } drawShape(g, s, lw); }
    g.restore();
  }
  /* ---------- the face (shared): head outline, features by FD; yaw -1..1 three-quarter, 1.6 side ---------- */
  const FPAL = n => n === "ink" ? "#000" : ({eye_white: "#fff", iris: "#666", pupil: "#000", highlight: "#fff", lip_upper: "#c4c4c4", lip_lower: "#e0e0e0", mouth_in: "#333", teeth: "#fff", tongue: "#999", skin_shade: "#dcdcdc", brow: "#000", blush: "#eee"})[n] || "#fff";
  /* The head shape comes from the module when it supplies one (CHAR.sheet.head_outline(yaw, {jaw, FD}) -> pts | {pts, smooth, k}; CHAR.sheet.face_shape or FD.face_shape =
     {pts: front outline, smooth, k, jaw_from}; CHAR.sheet.profile or FD.profile = {outline | sections:{brow,nose,mouth,jaw,skull}, tip_x, mouth_x, ...}); the generic oval and
     profile below are only the fallback. `jaw` (0..1) lowers the chin when the mouth opens. */
  const PROFILE_ORDER = ["brow", "nose", "mouth", "jaw", "skull"];
  function profileOutline(sgn, jaw) {
    const PR = faceProfile(FD); if (PR.outline) return PR.outline.map(p => [p[0] * sgn, p[1]]);
    const S = Object.assign({}, GENERIC_PROFILE.sections, PR.sections || {}), pts = [];
    for (const k of PROFILE_ORDER) S[k].forEach((p, i) => pts.push([p[0] * sgn, p[1] + (k === "jaw" ? .045 * jaw : k === "mouth" && i === S[k].length - 1 ? .027 * jaw : 0)]));
    return pts;
  }
  function headShape(yaw, jaw = 0) {
    const mod = typeof CHAR !== "undefined" && CHAR && CHAR.sheet && CHAR.sheet.head_outline, side = Math.abs(yaw) > 1.2;
    if (mod) { const r = mod(yaw, {jaw, FD}); if (r) return Array.isArray(r) ? {pts: r, smooth: side, k: 1} : Object.assign({smooth: side, k: 1}, r); }
    if (side) return {pts: profileOutline(Math.sign(yaw), jaw), smooth: faceProfile(FD).smooth !== false, k: faceProfile(FD).k || 1};
    const FS = (typeof CHAR !== "undefined" && CHAR && CHAR.sheet && CHAR.sheet.face_shape) || FD.face_shape, O = FD.oval, narrow = x => yaw * .05 + x * (1 - .12 * Math.abs(yaw) * (Math.sign(x) === Math.sign(yaw) ? 1 : 0));
    if (FS && FS.pts) { const from = FS.jaw_from === undefined ? .15 : FS.jaw_from; return {pts: FS.pts.map(p => [narrow(p[0]), p[1] + (p[1] > from ? .045 * jaw * Math.min(1, (p[1] - from) / .3) : 0)]), smooth: FS.smooth !== false, k: FS.k || 1}; }
    const pts = []; for (let i = 0; i < 40; i++) { const a = i / 40 * 6.2832, y = Math.sin(a), x = Math.cos(a) * (1 - .22 * Math.max(0, y) ** 2); pts.push([yaw * .05 + O.rx * x * (1 - .12 * Math.abs(yaw) * (Math.sign(x) === Math.sign(yaw) ? 1 : 0)), O.cy + O.ry * y + (y > 0 ? .05 * jaw * y * y : 0)]); }
    return {pts, smooth: false, k: 1};
  }
  const headOutline = (yaw, jaw) => headShape(yaw, jaw).pts;
  function faceHead(g, yaw, f, c, fill, lw, onlyOutline) {
    g.save(); if (c) g.translate(c[0], c[1]);
    ctx = g; MODE = "sheet";
    const ff = Object.assign({pal: FPAL, mode: "sheet", light: -1, eyeX: 0, eyeY: 0, blink: 0, iris: 1, yaw, inkK: lw ? lw / .012 * .8 : 1}, f);
    const info = faceInfo(g, FD, ff), jaw = clamp((info.au["26"] || 0) + .5 * (info.au["27"] || 0), 0, 1), hs = headShape(yaw, jaw);
    faceRunHooks(g, FD, ff, "behind", info);
    pathOf(g, hs.pts, true, hs.smooth, hs.k); g.fillStyle = fillOf(fill); g.fill(); g.lineWidth = (lw || .012) * 1.1; g.strokeStyle = "#000"; g.stroke();
    faceRunHooks(g, FD, ff, "skin", info);
    if (!onlyOutline) { ctx = g; MODE = "sheet"; drawFaceFeatures(g, FD, ff); }
    g.restore();
  }
  /* a mouth alone, fitted into the box (cx, cy, bw x bh) and clipped to it; label and note go BELOW the box at labelY, never over the drawing */
  function mouthOnly(P, cx, cy, bw, bh, f, label, sub, labelY) {
    const g = P.g, L = FD.lips, sc = Math.min(bh / .27, bw / (2 * L.half_w * 1.45), 1100);
    g.save(); g.beginPath(); g.rect(cx - bw / 2, cy - bh / 2, bw, bh); g.clip(); g.translate(cx, cy); g.scale(sc, sc); g.translate(0, -(L.y + .03)); ctx = g; MODE = "sheet";
    drawFaceFeatures(g, FD, Object.assign({pal: FPAL, mode: "sheet", light: -1, eyeX: 0, eyeY: 0, blink: 0, iris: 1, onlyMouth: true, inkK: .4, yaw: 0, au: {}}, f)); g.restore();
    T(P, cx, labelY, label, 14, {anchor: "middle", weight: 700}); if (sub) T(P, cx, labelY + 17, sub, 14, {anchor: "middle", font: SERIFT});
  }

  /* ---------- the mannequin (shared): joints from the catalogue model, projected by yaw; shapes sized from the module's proportions ---------- */
  function proj(j, th) { const c = Math.cos(th), s = Math.sin(th); return [j[0] * c + j[2] * s, j[1]]; }
  function capsulePts(a, b, ra, rb, n = 10) {
    const d = [b[0] - a[0], b[1] - a[1]], L = Math.hypot(d[0], d[1]) || 1e-6, u = [d[0] / L, d[1] / L], nn = [-u[1], u[0]], p = [];
    for (let i = 0; i <= n; i++) { const t = -Math.PI / 2 + Math.PI * i / n; p.push([b[0] + u[0] * Math.cos(t) * rb + nn[0] * Math.sin(t) * rb, b[1] + u[1] * Math.cos(t) * rb + nn[1] * Math.sin(t) * rb]); }
    for (let i = 0; i <= n; i++) { const t = Math.PI / 2 + Math.PI * i / n; p.push([a[0] + u[0] * Math.cos(t) * ra + nn[0] * Math.sin(t) * ra, a[1] + u[1] * Math.cos(t) * ra + nn[1] * Math.sin(t) * ra]); }
    return p;
  }
  function circlePts(c, rx, ry, n = 28) { const p = []; for (let i = 0; i < n; i++) { const a = i / n * 6.2832; p.push([c[0] + Math.cos(a) * rx, c[1] + Math.sin(a) * ry]); } return p; }
  /* mannequin(joints 3D dict, th, M) -> {shapes, lines, dots, bbox}; M = CHAR.sheet.mannequin (box sizes, radii) */
  function mannequin(J3, th, M, light) {
    const p = n => proj(J3[n], th), sh = [];
    const ang = Math.abs(Math.sin(th)), cs = Math.abs(Math.cos(th));
    const boxPts = (cy0, cy1, a, b, zc) => { const w = a * cs + b * ang, xc = zc * Math.sin(th); return [[xc - w, cy0], [xc + w, cy0], [xc + w, cy1], [xc - w, cy1]]; };
    const limb = (a, b, ra, rb, id) => ({id, pts: capsulePts(p(a), p(b), ra, rb), fill: "paper", lw: .7});
    const R = M.radius;
    const far = th > 0 ? "R" : "L";   // the limb away from the viewer is drawn first
    const legs = ["R", "L"].map(s => [limb("hip_" + s, "knee_" + s, R.thigh, R.thigh * .72, "thigh-" + s), limb("knee_" + s, "ankle_" + s, R.thigh * .72, R.shank, "shank-" + s), {id: "foot-" + s, pts: capsulePts(p("ankle_" + s), p("toe_" + s), R.foot, R.foot * .7), fill: "paper", lw: .7}]);
    sh.push(...legs[0], ...legs[1]);
    sh.push({id: "pelvis-box", pts: boxPts(M.pelvis.y0, M.pelvis.y1, M.pelvis.a, M.pelvis.b, 0), fill: "g1"});
    const arms = s => [limb("shoulder_" + s, "elbow_" + s, R.upper_arm, R.upper_arm * .85, "upper-arm-" + s), limb("elbow_" + s, "wrist_" + s, R.upper_arm * .85, R.forearm, "forearm-" + s), {id: "hand-" + s, pts: capsulePts(p("wrist_" + s), [p("wrist_" + s)[0], p("wrist_" + s)[1] + M.hand_len], R.forearm, R.hand_tip), fill: "paper", lw: .7}];
    const nearSide = Math.sin(th) >= 0 ? "L" : "R"; const farSide = nearSide === "L" ? "R" : "L";
    if (ang > .5) sh.push(...arms(farSide));
    sh.push({id: "chest-box", pts: boxPts(M.chest.y0, M.chest.y1, M.chest.a, M.chest.b, 0), fill: "g1"});
    sh.push({id: "waist-link", pts: [[-.28 * cs - .22 * ang, M.chest.y1], [.28 * cs + .22 * ang, M.chest.y1], [.28 * cs + .22 * ang, M.pelvis.y0], [-.28 * cs - .22 * ang, M.pelvis.y0]], fill: "g2", lw: .6});
    if (ang <= .5) sh.push(...arms("R"), ...arms("L")); else sh.push(...arms(nearSide));
    sh.push({id: "neck", pts: capsulePts(p("neck_base"), p("neck_top"), M.neck_r, M.neck_r * .9), fill: "paper"});
    const hc = p("head_center"); sh.push({id: "head", pts: circlePts(hc, M.head.rx * (cs * .75 + ang * .25 + .25), M.head.ry), fill: "paper", lw: 1.1});
    const lines = [], dots = [];
    const nb = p("neck_base"), tp = p("neck_top");
    lines.push({id: "spine", pts: [p("pelvis"), p("waist"), p("chest_base"), nb, tp, hc], dash: [], lw: 1.4});
    const sL = p("shoulder_L"), sR = p("shoulder_R"); lines.push({id: "clavicle", pts: [sR, [p("sternal_notch")[0], p("sternal_notch")[1]], sL], lw: 1.8});
    lines.push({id: "face-cross", pts: [[hc[0] - M.head.rx * .9, hc[1] + .05], [hc[0] + M.head.rx * .9, hc[1] + .05]], dash: [.03, .03], lw: .5});
    lines.push({id: "face-mid", pts: [[hc[0] + Math.sin(th) * M.head.rx * .8, hc[1] - M.head.ry], [hc[0] + Math.sin(th) * M.head.rx * .8, hc[1] + M.head.ry]], dash: [.03, .03], lw: .5});
    for (const n of Object.keys(J3)) dots.push({n, p: p(n)});
    // measures from the drawn joints (screen x of the shoulder caps, depth-free at th = 0)
    return {shapes: sh, lines, dots, sL, sR, hc};
  }
  function drawMannequin(g, mq, ox, oy, k, o = {}) {
    const lw = (o.lw || 1.8) / k; g.save(); g.translate(ox, oy); g.scale(k, k); g.lineJoin = g.lineCap = "round";
    for (const s of mq.shapes) drawShape(g, s, lw * (o.thin ? .6 : 1));
    for (const l of mq.lines) drawShape(g, Object.assign({closed: false, fill: "none"}, l), lw);
    if (o.joints !== false) for (const d of mq.dots) { g.beginPath(); g.arc(d.p[0], d.p[1], .035, 0, 6.3); g.fillStyle = "#000"; g.fill(); }
    g.restore();
  }
  /* ---------- 2D pose by forward kinematics (gesture sheet): the character's OWN joint heights (catalogue model) and lengths, not another character's ----------
     pose = {lean, head, pivot, armL:[upper, fore], armR, stance, legL:[thigh, knee], legR:[thigh, knee], facing}; angles in degrees.
     lean: the torso turns about the joint named by `pivot` (default "pelvis"; "waist" for a stooped character). thigh: swing of the thigh from straight down (+ = toward facing);
     knee: bend of the shank back from the thigh (0 = straight). Bent legs lower the pelvis so the planted foot stays on the floor. */
  function fkPose(prop, J, M, p) {
    const D = Math.PI / 180, j = n => [J[n][0], J[n][1]], R = (v, a) => [v[0] * Math.cos(a) - v[1] * Math.sin(a), v[0] * Math.sin(a) + v[1] * Math.cos(a)];
    const add = (a, b) => [a[0] + b[0], a[1] + b[1]], sub = (a, b) => [a[0] - b[0], a[1] - b[1]], lean = (p.lean || 0) * D, headA = (p.head || 0) * D, facing = p.facing || (lean < 0 ? -1 : 1);
    const dir = a => [Math.sin(a), Math.cos(a)];
    // legs: forward kinematics when a leg pose is given, otherwise the stance spread of the old sheet; the pelvis drops with the straightest leg
    const st = p.stance || 0, legFK = {}, drops = [];
    for (const s of ["L", "R"]) {
      const sg = s === "L" ? 1 : -1, H = j("hip_" + s), K0 = j("knee_" + s), A0 = j("ankle_" + s), T = Math.hypot(K0[0] - H[0], K0[1] - H[1]), Sh = Math.hypot(A0[0] - K0[0], A0[1] - K0[1]), lp = p["leg" + s];
      if (lp) { const a1 = facing * (lp[0] || 0) * D, a2 = a1 - facing * (lp[1] || 0) * D, K = add(H, [dir(a1)[0] * T, dir(a1)[1] * T]), A = add(K, [dir(a2)[0] * Sh, dir(a2)[1] * Sh]); legFK[s] = {H, K, A}; drops.push((T + Sh) - (A[1] - H[1])); }
      else { legFK[s] = {H, K: [H[0] * .9 + sg * st, K0[1]], A: [H[0] * .9 + sg * st - sg * st * .4, A0[1]]}; drops.push(0); }
    }
    const drop = p.feet_planted === false ? 0 : Math.max(0, Math.min(...drops)), dn = v => [v[0], v[1] + drop];
    const leg = s => { const L = legFK[s]; return {H: dn(L.H), K: dn(L.K), A: dn(L.A)}; };
    // torso: everything above the pivot turns by `lean` about it
    const pv = dn(j(p.pivot || "pelvis")), up = n => add(pv, R(sub(dn(j(n)), pv), lean));
    const pel = dn(j("pelvis")), waist = up("waist"), chestB = up("chest_base"), neckB = up("neck_base"), neckT = add(neckB, R(sub(dn(j("neck_top")), dn(j("neck_base"))), lean + headA * .5));
    const hc = add(neckT, R(sub(dn(j("head_center")), dn(j("neck_top"))), lean + headA)), crown = add(neckT, R(sub(dn(j("crown")), dn(j("neck_top"))), lean + headA));
    const arm = (s, a1, a2) => { const sg = s === "L" ? 1 : -1, S = up("shoulder_" + s), ua = Math.hypot(J["elbow_" + s][0] - J["shoulder_" + s][0], J["elbow_" + s][1] - J["shoulder_" + s][1]) || prop.upper_arm, fa = Math.hypot(J["wrist_" + s][0] - J["elbow_" + s][0], J["wrist_" + s][1] - J["elbow_" + s][1]) || prop.forearm;
      const e = [S[0] + Math.sin(a1 * D) * ua * sg, S[1] + Math.cos(a1 * D) * ua], ea = (a1 + a2) * D, W = [e[0] + Math.sin(ea) * fa * sg, e[1] + Math.cos(ea) * fa]; return {S, E: e, W}; };
    const aL = arm("L", p.armL ? p.armL[0] : 8, p.armL ? p.armL[1] : 6), aR = arm("R", p.armR ? p.armR[0] : 8, p.armR ? p.armR[1] : 6);
    return {pel, waist, chestB, neckB, neckT, hc, crown, aL, aR, lL: leg("L"), lR: leg("R"), lean, drop, pivot: pv};
  }
  const poseExtent = (f, M) => { const R = M.radius, pts = []; const add = (c, rx, ry) => { pts.push([c[0] - rx, c[1] - ry], [c[0] + rx, c[1] + ry]); };
    add(f.hc, M.head.rx * 1.1, M.head.ry * 1.04); pts.push(f.crown); for (const q of [f.lL, f.lR]) { add(q.H, R.thigh, R.thigh); add(q.K, R.thigh * .72, R.thigh * .72); add(q.A, R.shank, R.shank * 1.4); }
    for (const a of [f.aL, f.aR]) { add(a.S, R.upper_arm, R.upper_arm); add(a.E, R.upper_arm * .82, R.upper_arm * .82); add(a.W, R.forearm, R.forearm); }
    add(f.chestB, M.chest.a, .2); add(f.pel, M.pelvis.a, .2); pts.push([f.pel[0], f.pel[1] + M.pelvis.y1]);
    return Ink.bbox(pts); };

  /* ---------- sheet builders (character) ---------- */
  const emotions = () => CHAR.sheet.emotions;
  function sheet01(P, ctxm) {   // gesture lines + simple shapes for each pose, in the character's own proportions, one scale for all poses
    const g = P.g, prop = CHAR.proportions_hu, M = CHAR.sheet.mannequin, poses = CHAR.sheet.gesture_poses, J3 = ctxm.J3;
    const cw = (PW - 2 * SM) / poses.length, top = 262, bottom = 1096, fs = poses.map(ps => fkPose(prop, J3, M, ps)), ex = fs.map(f => poseExtent(f, M));
    // one scale for every pose: the tallest pose fits the cell, the widest fits the cell width; the planted floor is the same line in every cell
    const floorHU = Math.max(...fs.map(f => Math.max(f.lL.A[1], f.lR.A[1]))) + M.radius.shank * .4, topHU = Math.min(...ex.map(e => e.y0)), wHU = Math.max(...ex.map(e => e.x1 - e.x0));
    const k = Math.min(125, (bottom - top) / (floorHU - topHU), (cw - 70) / wHU), oy = bottom - floorHU * k;
    poses.forEach((ps, i) => {
      const x0 = SM + i * cw, cx = x0 + cw / 2; box(g, x0 + 6, 160, cw - 12, 1000, 3);
      cellTitle(P, x0 + 22, 200, ps.name, ps.note);
      const f = fs[i], W2 = a => [cx - (ex[i].x0 + ex[i].x1) / 2 * k + a[0] * k, oy + a[1] * k];
      g.save(); g.lineJoin = g.lineCap = "round";
      g.beginPath(); g.moveTo(x0 + 24, oy + floorHU * k); g.lineTo(x0 + cw - 24, oy + floorHU * k); g.lineWidth = 1.4; g.strokeStyle = "#777"; g.setLineDash([8, 6]); g.stroke(); g.setLineDash([]);
      // 1 gesture: one flowing action line head -> pelvis -> foot, heavier than the rest
      const mid = (a, b) => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2], gl = [f.hc, f.neckB, f.chestB, f.waist, f.pel, mid(f.lL.K, f.lR.K), mid(f.lL.A, f.lR.A)].map(W2);
      pathOf(g, gl, false, true, .8); g.lineWidth = 7; g.strokeStyle = "#000"; g.stroke();
      // 2 simple shapes over it: head ball, chest box, pelvis box, limb cylinders, thin line
      g.lineWidth = 2; const ink = (pts, fill) => { pathOf(g, pts, true, false); g.fillStyle = fill || "none"; if (fill) g.fill(); g.strokeStyle = "#000"; g.stroke(); };
      const capW = (a, b, ra, rb) => capsulePts(W2(a), W2(b), ra * k, rb * k), R = M.radius;
      for (const q of [f.lR, f.lL]) { ink(capW(q.H, q.K, R.thigh, R.thigh * .72)); ink(capW(q.K, q.A, R.thigh * .72, R.shank * .75)); }
      const rot = (v, an) => [v[0] * Math.cos(an) - v[1] * Math.sin(an), v[0] * Math.sin(an) + v[1] * Math.cos(an)];
      const boxQuad = (y0, y1, w, an) => [[-w, y0], [w, y0], [w, y1], [-w, y1]].map(v => { const q = rot([v[0] - f.pivot[0], v[1] + f.drop - f.pivot[1]], an); return W2([q[0] + f.pivot[0], q[1] + f.pivot[1]]); });
      ink(boxQuad(M.pelvis.y0, M.pelvis.y1, M.pelvis.a, 0)); ink(boxQuad(M.chest.y0, M.chest.y1, M.chest.a, f.lean));
      for (const a of [f.aR, f.aL]) { ink(capW(a.S, a.E, R.upper_arm, R.upper_arm * .82)); ink(capW(a.E, a.W, R.upper_arm * .82, R.forearm * .8)); }
      ink(circlePts(W2(f.hc), M.head.rx * 1.1 * k, M.head.ry * 1.04 * k)); pathOf(g, [W2(f.neckB), W2(f.neckT)], false); g.lineWidth = 8; g.stroke();
      g.restore();
      T(P, x0 + 22, 1130, "gesture line, then shapes on top", 14, {fill: "#444"});
    });
    region(P, "figure", SM + 6, 160, cw - 12, 1000);
    T(P, SM, PH - 62, "Order: gesture first (30 s to 2 min), then head ball, chest box, pelvis box, cylinders. The mannequin keeps the gesture (R-340).", 15, {fill: "#333"});
    ctxm.shapes = poses.length;
  }
  function sheet02(P, ctxm) {   // mannequin: front, three-quarter, side, with joint labels and the head-unit ruler
    const g = P.g, M = CHAR.sheet.mannequin, J3 = ctxm.J3, k = 108, floor = 1086, crown = J3.crown[1], toe = Math.max(J3.toe_L[1], J3.toe_R[1]) + (M.floor_pad || 0), oy = floor - toe * k;
    const views = [[0, "front", 330], [-0.7, "three-quarter", 760], [-1.5708, "side", 1150]];
    views.forEach(([th, nm, ox]) => { const mq = mannequin(J3, th, M); drawMannequin(g, mq, ox, oy, k); T(P, ox, 1128, nm, 22, {anchor: "middle", font: SERIF, weight: 700});
      if (th === 0) { ctxm.sL = mq.sL; ctxm.sR = mq.sR; } });
    // ruler in head units, 0 at the crown
    const rx = 120, hh = M.head_unit_label || 1; g.lineWidth = 2; g.strokeStyle = "#000"; g.beginPath(); g.moveTo(rx, oy + crown * k); g.lineTo(rx, oy + toe * k); g.stroke();
    for (let i = 0; i <= Math.floor(toe - crown); i++) { const y = oy + (crown + i) * k; g.beginPath(); g.moveTo(rx - 12, y); g.lineTo(rx + 12, y); g.stroke(); T(P, rx - 18, y + 5, String(i), 15, {anchor: "end"}); }
    g.beginPath(); g.moveTo(rx - 12, oy + toe * k); g.lineTo(rx + 12, oy + toe * k); g.stroke(); T(P, rx + 20, oy + toe * k + 5, `${r3(toe - crown)} heads`, 16, {weight: 700});
    // clavicle callout and key joints
    const sx = 330 + ctxm.sL[0] * k, sy = oy + ctxm.sL[1] * k; g.beginPath(); g.moveTo(sx + 10, sy - 8); g.lineTo(sx + 120, sy - 70); g.lineWidth = 1.6; g.stroke();
    T(P, sx + 126, sy - 74, "shoulder at the end of the clavicle line", 15, {weight: 700}); T(P, sx + 126, sy - 54, `${r3(Math.abs(ctxm.sL[0] - ctxm.sR[0]) + 2 * (M.shoulder_cap || 0))} HU wide`, 15);
    const nb = oy + J3.neck_base[1] * k; T(P, 330 + 60, nb - 6, "neck: " + r3(Math.abs(J3.neck_top[1] - J3.neck_base[1])) + " HU", 15);
    T(P, SM, PH - 62, "Joints in head units from the catalogue model; limbs are cylinders, torso two boxes. Every angle shares one joint list (R-345).", 15, {fill: "#333"});
    ctxm.height_m = r3(toe - crown);
    region(P, "front", 120, 160, 520, 980);
  }
  /* extent of a figure in HU: every shape point (loads, props and cloth included), the head circle, and the declared bbox; a module may set fig.extent = {x0,y0,x1,y1} */
  function figExtent(fig) {
    if (fig.extent) return fig.extent;
    const pts = [[fig.bbox.x0, fig.bbox.y0], [fig.bbox.x1, fig.bbox.y1]];
    for (const s of fig.shapes) { if (s.kind === "face") { const c = s.c || [0, 0]; pts.push([c[0] - .5, c[1] - .6], [c[0] + .5, c[1] + .6]); continue; } for (const p of s.pts || []) pts.push(p); }
    return Ink.bbox(pts);
  }
  /* hands at figure scale (module asks with sheet.hand_scale and fig.hands = [{grip, at:[x,y] in HU}]): a boxed inset per hand, drawn by the module's own hand(), with a leader line */
  function handInsets(P, fig, ox, oy, k, slots) {
    const g = P.g, S = CHAR.sheet; if (!S.hand_scale || !S.hand || !fig.hands || !fig.hands.length) return 0;
    let n = 0;
    fig.hands.forEach((h, i) => { const sl = slots[i]; if (!sl) return; n++;
      const ax = ox + h.at[0] * k, ay = oy + h.at[1] * k, cx = sl.x + sl.s / 2, cy = sl.y + sl.s / 2;
      g.save(); g.beginPath(); g.moveTo(ax, ay); g.lineTo(clamp(ax, sl.x, sl.x + sl.s), clamp(ay, sl.y, sl.y + sl.s)); g.lineWidth = 1.4; g.strokeStyle = "#000"; g.setLineDash([5, 4]); g.stroke(); g.setLineDash([]);
      g.beginPath(); g.arc(ax, ay, 4, 0, 6.3); g.fillStyle = "#000"; g.fill(); g.restore();
      box(g, sl.x, sl.y, sl.s, sl.s, 2.4, "#fff");
      g.save(); g.beginPath(); g.rect(sl.x + 2, sl.y + 2, sl.s - 4, sl.s - 4); g.clip(); S.hand(g, h.grip, {x: cx, y: cy + 4, k: Math.min(S.hand_scale * k, sl.s / 1.9), box: {w: sl.s, h: sl.s}}); g.restore();
      T(P, sl.x + 6, sl.y + sl.s - 6, h.label || h.grip, 12, {fill: "#333"}); });
    return n;
  }
  function sheet03(P, ctxm) {   // sketch over the mannequin: faint mannequin + final-line figure, with named layers; scaled to the figure's own height
    const g = P.g, M = CHAR.sheet.mannequin, floor = 1078, top = 188, cells = [[0, 330, "front"], [-0.7, 800, "three-quarter-L"]];
    const figs = cells.map(c => CHAR.sheet.figure(c[2])), ext = figs.map(figExtent);
    const hHU = Math.max(...ext.map(e => e.y1)) - Math.min(...ext.map(e => e.y0)), wHU = Math.max(...ext.map(e => e.x1 - e.x0)), yb = Math.max(...ext.map(e => e.y1));
    const k = Math.min(112, (floor - top) / hHU, 460 / wHU), oy = floor - yb * k;
    cells.forEach(([t, ox], i) => {
      const mq = mannequin(ctxm.J3, t, M); g.save(); drawMannequin(g, mq, ox, oy, k, {lw: .8, joints: false, thin: true}); g.restore();
      drawFig(g, figs[i], ox, oy, k, {lw: 2.4}); });
    // layer list, inside out
    const x = 1130; T(P, x, 190, "Layers, built inside out", 28, {font: SERIF, weight: 800}); let y = 232;
    CHAR.sheet.layers.forEach((l, i) => { g.beginPath(); g.rect(x, y - 21 + 0, 26, 26); g.fillStyle = "#fff"; g.fill(); g.lineWidth = 2; g.stroke(); T(P, x + 13, y - 2, String(i + 1), 15, {anchor: "middle", weight: 700}); T(P, x + 40, y - 1, l, 18); y += 40; });
    const s = 200, y0 = Math.max(y + 10, 640); handInsets(P, figs[0], cells[0][1], oy, k, [0, 1, 2, 3].map(i => ({x: x + (i % 2) * (s + 24), y: y0 + Math.floor(i / 2) * (s + 14), s})).filter(q => q.y + q.s < PH - 80));
    ctxm.fit_k03 = r3(k);
    T(P, SM, PH - 62, "Final line sits on named mannequin parts; the grey mannequin underneath is the proof (R-340, R-354).", 15, {fill: "#333"});
  }
  function sheet04(P, ctxm) {   // turnaround: four angles on shared guidelines, layer order per angle; one scale fitted to the tallest and widest figure
    const g = P.g, floor = 1000, top = 190, A = CHAR.sheet.angles, xs = [330, 690, 1050, 1410];
    const figs = A.map(a => CHAR.sheet.figure(a.id)), ext = figs.map(figExtent), G = CHAR.sheet.guides;
    const hHU = Math.max(...ext.map(e => e.y1)) - Math.min(...ext.map(e => e.y0)), wHU = Math.max(...ext.map(e => e.x1 - e.x0)), yb = Math.max(...ext.map(e => e.y1));
    const k = Math.min(104, (floor - top) / hHU, 340 / wHU), oy = floor - yb * k;
    // guidelines across the page with labels at the left
    g.save(); g.setLineDash([6, 6]); g.lineWidth = 1; g.strokeStyle = "#555";
    for (const gl of G) { const y = oy + gl.y * k; g.beginPath(); g.moveTo(SM + 70, y); g.lineTo(PW - SM, y); g.stroke(); } g.restore();
    for (const gl of G) T(P, SM, oy + gl.y * k - 4, gl.name, 13, {fill: "#333"});
    A.forEach((a, i) => { drawFig(g, figs[i], xs[i], oy, k, {lw: 2.3}); T(P, xs[i], 1038, a.label, 24, {anchor: "middle", font: SERIF, weight: 800});
      const ord = ctxm.angleFiles[a.id] || {}; const lay = (Array.isArray(ord[CHAR.data.angle_order_key || "hijab_layer_order"]) ? ord[CHAR.data.angle_order_key || "hijab_layer_order"] : figs[i].order || []).join(" > "); wrapText(P, xs[i] - 160, 1066, "back to front: " + lay, 13, 320, 17, {fill: "#333"});
      region(P, a.id, xs[i] - 170, 160, 340, 1000);
      const hx = clamp(xs[i] + (ext[i].x1 * k) * .5 + 30, xs[i] + 40, xs[i] + 70); handInsets(P, figs[i], xs[i], oy, k, [{x: hx, y: 176, s: 112}, {x: hx, y: 296, s: 112}]); });
    // measured: figure bbox height of the front figure
    ctxm.figure_height = r3(figs[0].bbox.y1 - figs[0].bbox.y0); ctxm.fit_k04 = r3(k);
    T(P, SM + 70, 160, `${ctxm.figure_height} heads, drawn`, 17, {weight: 700});
    // ruler of heads on the far right
    const rx = PW - 90; g.lineWidth = 2; g.beginPath(); g.moveTo(rx, oy + figs[0].bbox.y0 * k); g.lineTo(rx, oy + figs[0].bbox.y1 * k); g.stroke();
    for (let i = 0; i <= Math.floor(ctxm.figure_height); i++) { const y = oy + (figs[0].bbox.y0 + i) * k; g.beginPath(); g.moveTo(rx - 10, y); g.lineTo(rx + 10, y); g.stroke(); T(P, rx + 16, y + 5, String(i), 14); }
  }
  /* expression gain: the module may ask for a wider range (CHAR.sheet.expression_range for the shared face drawer, CHAR.sheet.expression_gain to scale the action units
     for a module that draws its own face); the shared drawer already widens the sheet range by 1.5 */
  const gained = au => { const gn = CHAR.sheet.expression_gain; if (!gn || gn === 1) return au; const o = {}; for (const k in au) o[k] = typeof au[k] === "number" ? clamp(au[k] * gn, -2, 2) : au[k]; return o; };
  function sheet05(P, ctxm) {   // the 8 emotions from the bible, bust with the shared face
    const g = P.g, E = emotions(), cw = (PW - 2 * SM) / 4, ch = 480, k = 330;
    E.forEach((e, i) => {
      const c = i % 4, r = Math.floor(i / 4), x0 = SM + c * cw, y0 = 150 + r * (ch + 24); box(g, x0 + 6, y0, cw - 12, ch, 3);
      const fig = CHAR.sheet.figure("front", {face: Object.assign({au: gained(e.au), range: CHAR.sheet.expression_range}, e.eye || {})}); const hc = fig.head;
      g.save(); g.beginPath(); g.rect(x0 + 9, y0 + 3, cw - 18, ch - 6); g.clip();
      drawFig(g, fig, x0 + cw / 2, y0 + 190 - hc.c[1] * k, k, {lw: 3}); g.restore();
      g.fillStyle = "#000"; g.beginPath(); g.rect(x0 + 6, y0 + ch - 64, cw - 12, 64); g.fill();
      T(P, x0 + 22, y0 + ch - 36, e.id.toUpperCase(), 24, {fill: "#fff", font: SERIF, weight: 800});
      T(P, x0 + 22, y0 + ch - 14, Object.entries(e.au).sort((a, b) => b[1] - a[1]).slice(0, 4).map(([a, v]) => "AU" + a + " " + v).join(" · "), 14, {fill: "#fff"});
      region(P, e.id, x0 + 6, y0, cw - 12, ch);
    });
    T(P, SM, PH - 62, "Eight bible emotions, one face. Action units (FACS) drive brows, lids, nose, lips, jaw and cheeks; ink only on lashes, brows, nose underside, the lip line and the expression folds.", 15, {fill: "#333"});
  }
  /* sheet 06: any number of grips. A page holds up to 12 in a grid chosen by the count (1-3 in a row, 4-6 as 3x2, 7-8 as 4x2, 9 as 3x3, 10-12 as 4x3); more are paginated onto 06b, 06c ... */
  const GRIPS_PER_PAGE = 12;
  function gripGrid(m) { return m <= 3 ? {cols: Math.max(1, m), rows: 1, ch: 700} : m <= 6 ? {cols: 3, rows: 2, ch: 490} : m <= 8 ? {cols: 4, rows: 2, ch: 490} : m <= 9 ? {cols: 3, rows: 3, ch: 322} : {cols: 4, rows: 3, ch: 322}; }
  function sheet06(P, ctxm, pageNo = 0) {   // hands and grips
    const g = P.g, all = CHAR.data.grips, grips = all.slice(pageNo * GRIPS_PER_PAGE, (pageNo + 1) * GRIPS_PER_PAGE), L = gripGrid(grips.length), cw = (PW - 2 * SM) / L.cols, ch = L.ch;
    grips.forEach((id, i) => {
      const c = i % L.cols, r = Math.floor(i / L.cols), x0 = SM + c * cw, y0 = 160 + r * (ch + 20); box(g, x0 + 6, y0, cw - 12, ch, 3);
      const sc = Math.min(1.25, (ch - 135) / 380, (cw - 30) / 520), cyh = 60 + (ch - 130) / 2;   // the drawing lives between the title strip and the layer note
      g.save(); g.beginPath(); g.rect(x0 + 9, y0 + 3, cw - 18, ch - 6); g.clip(); g.translate(x0 + cw / 2, y0 + cyh); g.scale(sc, sc);
      const info = CHAR.sheet.hand(g, id, {x: 0, y: 0, k: 300, box: {w: (cw - 18) / sc, h: ch / sc}}); g.restore();
      cellTitle(P, x0 + 22, y0 + 38, id, info.note);
      wrapText(P, x0 + 22, y0 + ch - 44, "back to front: " + info.layers.join(" > "), 13, cw - 50, 16, {fill: "#333"});
    });
    T(P, SM, PH - 62, "Four fingers and a thumb, three bones each, constant lengths; a grip changes joint angles only (R-383). " + (CHAR.sheet.notes && CHAR.sheet.notes.grips ? CHAR.sheet.notes.grips : "Handedness from the bible: " + Object.entries(CHAR.handedness).filter(([, v]) => v === "L" || v === "R").map(([a, v]) => a + " " + (v === "L" ? "left" : "right")).join(", ") + ".") + (all.length > GRIPS_PER_PAGE ? ` Grips ${pageNo * GRIPS_PER_PAGE + 1} to ${pageNo * GRIPS_PER_PAGE + grips.length} of ${all.length}.` : ""), 15, {fill: "#333"});
  }
  function sheet07(P, ctxm) {   // face: nose at five angles, lips per emotion, visemes; the head is the module's own shape, labels sit in strips below their drawings
    const g = P.g;
    T(P, SM, 170, "1  Nose and face at five angles", 21, {font: SERIF, weight: 800});
    [[-1.6, "side L"], [-.85, "three-quarter L"], [0, "front"], [.85, "three-quarter R"], [1.6, "side R"]].forEach(([y, l], i) => {
      const cx = SM + 170 + i * 340, cy = 356; g.save(); g.translate(cx, cy); g.scale(290, 290); faceHead(g, y, {au: {"12": .12}}, null, "#fff", .012); g.restore(); T(P, cx, 520, l, 15, {anchor: "middle", weight: 700}); });
    T(P, SM, 566, "2  Lips for the eight emotions", 21, {font: SERIF, weight: 800});
    const E = emotions(), ecw = (PW - 2 * SM) / E.length;
    E.forEach((e, i) => mouthOnly(P, SM + ecw * (i + .5), 636, ecw - 24, 104, {au: e.au}, e.id, null, 712));
    T(P, SM, 750, "3  Mouth shapes for the language (visemes), lips at 3x", 21, {font: SERIF, weight: 800});
    const V = Object.keys(FD.visemes).filter(k => /^V\d+$/.test(k)), cols = Math.min(6, Math.max(1, V.length)), rows = Math.ceil(V.length / cols), top = 770, bottom = PH - 90, pitch = (bottom - top) / rows, cw7 = (PW - 2 * SM) / cols;
    V.forEach((id, i) => { const col = i % cols, row = Math.floor(i / cols), y0 = top + row * pitch, bh = Math.max(40, pitch - 46);
      mouthOnly(P, SM + cw7 * (col + .5), y0 + bh / 2, cw7 - 30, bh, {viseme: {id, w: 1}}, id + " · " + FD.visemes[id].name, FD.visemes[id].letters || "rest", y0 + bh + 18); });
    region(P, "nose", SM, 140, PW - 2 * SM, 400);
  }
  function sheet08(P, ctxm) {   // props and signature objects
    const g = P.g, pr = CHAR.sheet.props, cols = 4, cw = (PW - 2 * SM) / cols, ch = 460;
    pr.forEach((p, i) => {
      const c = i % cols, r = Math.floor(i / cols), x0 = SM + c * cw, y0 = 160 + r * (ch + 24); box(g, x0 + 6, y0, cw - 12, ch, 3);
      g.save(); g.beginPath(); g.rect(x0 + 9, y0 + 3, cw - 18, ch - 90); g.clip(); g.lineJoin = g.lineCap = "round"; ctx = g; MODE = "sheet"; p.draw(g, x0 + cw / 2, y0 + (ch - 90) / 2 + 10, 1); g.restore();
      g.fillStyle = "#000"; g.beginPath(); g.rect(x0 + 6, y0 + ch - 78, cw - 12, 78); g.fill();
      T(P, x0 + 20, y0 + ch - 48, p.label, 21, {fill: "#fff", font: SERIF, weight: 800}); T(P, x0 + 20, y0 + ch - 22, p.hand, 15, {fill: "#fff"});
    });
    T(P, SM, PH - 62, "Props carried and signature objects, each with the hand that holds it. " + ((CHAR.sheet.notes && CHAR.sheet.notes.props) || ""), 15, {fill: "#333"});
  }

  /* ---------- world sheets: every title, subtitle and section label comes from WORLD.sheet.labels (the neutral defaults below name no place) ---------- */
  const WORLD_LABELS = {
    establishing: {title: "establishing view", sub: null},
    locations: {title: "key places", sub: "Each place in one frame, one light, hatching for the dark side."},
    props: {title: "props", sub: "The objects that fill the place, as plain ink silhouettes with their tags."},
    materials: {title: "materials", sub: "How each surface is hatched, one swatch per material."}
  };
  const worldLabel = (W, key) => Object.assign({}, WORLD_LABELS[key], (W.sheet.labels || {})[key] || {});
  /* grid by item count: 1-6 as 3x2, 7-8 as 4x2, 9-10 as 5x2, 11-12 as 4x3, 13-15 as 5x3, 16-18 as 6x3; more are paginated (w2b, w2c ...) */
  const WORLD_PER_PAGE = 18;
  function worldGridFor(n) { return n <= 6 ? {cols: 3, rows: 2} : n <= 8 ? {cols: 4, rows: 2} : n <= 10 ? {cols: 5, rows: 2} : n <= 12 ? {cols: 4, rows: 3} : n <= 15 ? {cols: 5, rows: 3} : {cols: 6, rows: 3}; }
  function worldGrid(P, items, cols, rows, y0, draw) {
    const g = P.g, cw = (PW - 2 * SM) / cols, ch = rows <= 2 ? 500 : Math.floor((1016 - 16 * (rows - 1)) / rows);
    items.forEach((it, i) => {
      const c = i % cols, r = Math.floor(i / cols), x0 = SM + c * cw, y = y0 + r * (ch + 16); box(g, x0 + 6, y, cw - 12, ch, 3);
      g.save(); g.beginPath(); g.rect(x0 + 9, y + 3, cw - 18, ch - 62); g.clip(); g.lineJoin = g.lineCap = "round"; ctx = g; MODE = "sheet";
      draw(it, g, {x: x0 + 9, y: y + 3, w: cw - 18, h: ch - 62}); g.restore();
      g.fillStyle = "#000"; g.beginPath(); g.rect(x0 + 6, y + ch - 58, cw - 12, 58); g.fill();
      T(P, x0 + 18, y + ch - 33, it.label, cols >= 5 ? 17 : 20, {fill: "#fff", font: SERIF, weight: 800}); if (it.note) T(P, x0 + 18, y + ch - 13, it.note, cols >= 5 ? 11 : 13, {fill: "#fff"});
      region(P, it.id, x0 + 6, y, cw - 12, ch);
    });
  }
  function worldSheets(W) {
    const S = W.sheet, who = W.id, nm = W.name_ar || W.id, plan = [];
    plan.push({id: "w1-establishing", key: "establishing"});
    for (const [prefix, key, items] of [["w2", "locations", S.locations], ["w3", "props", S.props], ["w4", "materials", S.materials]]) {
      const n = Math.max(1, Math.ceil(items.length / WORLD_PER_PAGE));
      for (let p = 0; p < n; p++) plan.push({id: `${prefix}${p ? String.fromCharCode(97 + p) : ""}-${key}`, key, page: p, pages: n, items: items.slice(p * WORLD_PER_PAGE, (p + 1) * WORLD_PER_PAGE)});
    }
    return plan.map((pl, i) => {
      const lb = worldLabel(W, pl.key), pg = pl.pages > 1 ? ` (${pl.page + 1}/${pl.pages})` : "";
      if (pl.key === "establishing") {
        const P = newPage(pl.id, `${nm} · ${lb.title}`, lb.sub || S.establishing.note, i + 1, plan.length, who), g = P.g;
        box(g, 60, 150, PW - 120, 1010, 4); g.save(); g.beginPath(); g.rect(62, 152, PW - 124, 1006); g.clip(); g.lineJoin = g.lineCap = "round"; ctx = g; MODE = "sheet"; S.establishing.draw(g, {x: 62, y: 152, w: PW - 124, h: 1006}); g.restore();
        region(P, "plate", 60, 150, PW - 120, 1010); return P;
      }
      const P = newPage(pl.id, `${nm} · ${lb.title}${pg}`, lb.sub, i + 1, plan.length, who), gr = worldGridFor(pl.items.length);
      worldGrid(P, pl.items, gr.cols, gr.rows, 150, (it, g2, b) => it.draw(g2, b)); return P;
    });
  }

  /* ---------- run ---------- */
  const doc = P => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${PW} ${PH}" width="${PW}" height="${PH}" font-family="thmanyahsans, sans-serif"><title>${X(P.title)}</title><rect width="100%" height="100%" fill="#fff"/>${P.g.out.join("")}</svg>`;
  /* angle files (catalogue <char>/v1/angles/<id>.json, the per-angle layer order) are optional: absent = the figure's own order is printed; a file that exists but is not valid JSON, or a module that
     sets data.angles_required and has no file, stops the run with a message that names the file */
  async function loadAngleFiles(C, D, angles) {
    const dir = D.angle_dir || "v1/angles/", out = {}, found = [], missing = [];
    await Promise.all(angles.map(async a => {
      const url = C + dir + a.id + ".json", r = await fetch(url);
      if (r.status === 404) { missing.push(a.id); out[a.id] = {}; if (D.angles_required) throw new Error(`angle file missing: ${url} (module ${CHAR.id} sets data.angles_required; add the file or drop the flag)`); return; }
      if (!r.ok) throw new Error(`angle file ${url} could not be read: HTTP ${r.status}`);
      try { out[a.id] = await r.json(); found.push(a.id); } catch (e) { throw new Error(`angle file ${url} is not valid JSON: ${e.message}`); }
    }));
    return {files: out, found, missing};
  }
  async function run(kind, id) {
    await document.fonts.ready; await Promise.all(["700 20px thmanyahserifdisplay", "900 20px thmanyahserifdisplay", "400 20px thmanyahsans", "700 20px thmanyahsans", "400 20px thmanyahseriftext"].map(f => document.fonts.load(f)));
    if (kind === "world") {
      if (!WORLD) throw new Error("no world registered"); const pages = worldSheets(WORLD);
      return {sheets: pages.map(P => ({id: P.id, title: P.title, svg: doc(P), regions: P.regions, labels: P.labels})), measures: {locations: WORLD.sheet.locations.length, props: WORLD.sheet.props.length, materials: WORLD.sheet.materials.length},
        module: {id: WORLD.id, bible_world: WORLD.bible_world, name_ar: WORLD.name_ar, version: WORLD.version, rule: WORLD.rule}};
    }
    if (!CHAR) throw new Error("no character registered");
    const C = "/catalogue/characters/" + CHAR.id + "/", D = CHAR.data;
    const [model, face, hm] = await Promise.all([J(C + D.model), J(C + D.face), J(C + D.hand_model)]);
    FD = face; HM3 = hm;
    const gr = await Promise.all(D.grips.map(i => J(C + D.grip_dir + i + ".json"))); D.grips.forEach((i, n) => GRIPS[i] = gr[n]);
    const ang = await loadAngleFiles(C, D, CHAR.sheet.angles);
    const cm = {J3: model.joints, angleFiles: ang.files}, nGripPages = Math.max(1, Math.ceil(D.grips.length / GRIPS_PER_PAGE));
    const builders = [["01-shapes", "Gesture and simple shapes", "One action line per pose, then head ball, chest and pelvis boxes, limb cylinders.", sheet01], ["02-mannequin", "Mannequin", "Shoulders at the ends of the clavicle line, a real neck, joints in head units.", sheet02],
      ["03-sketch", "Sketch over the mannequin", "Contour, cloth and tags drawn over the mannequin, layers built inside out.", sheet03], ["04-turnaround", "Turnaround", "One mannequin, four angles, shared guidelines; the layer order is declared per angle.", sheet04],
      ["05-expressions", "Expressions", "The eight bible emotions on the same face; action units listed under each.", sheet05]];
    for (let p = 0; p < nGripPages; p++) builders.push([`06${p ? String.fromCharCode(97 + p) : ""}-hands-grips`, "Hands and grips" + (nGripPages > 1 ? ` (${p + 1}/${nGripPages})` : ""), "Constant topology; each grip is a set of joint angles and a layer order.", (P, c) => sheet06(P, c, p)]);
    builders.push(["07-face", "Face: nose, lips, visemes", "Nose at five angles, lips for every emotion, the mouth shapes of the language.", sheet07], ["08-props", "Props and signature objects", "Each with the hand that holds it.", sheet08]);
    const pages = [];
    for (const [sid, title, sub, fn] of builders) { const P = newPage(sid, `${CHAR.name_ar || CHAR.id} · ${title}`, sub, pages.length + 1, builders.length, CHAR.id); fn(P, cm); pages.push(P); }
    const prop = CHAR.proportions_hu, sh = cm.sL && cm.sR ? Math.abs(cm.sL[0] - cm.sR[0]) + 2 * (CHAR.sheet.mannequin.shoulder_cap || 0) : null, J3 = cm.J3;
    const dist = (a, b) => Math.hypot(J3[a][0] - J3[b][0], J3[a][1] - J3[b][1], J3[a][2] - J3[b][2]);
    const measures = {height: cm.figure_height, mannequin_height: cm.height_m, shoulder_w: r3(sh), neck_len: r3(dist("neck_base", "neck_top")), upper_arm: r3(dist("shoulder_L", "elbow_L")), forearm: r3(dist("elbow_L", "wrist_L")), thigh: r3(dist("hip_L", "knee_L")), shank: r3(dist("knee_L", "ankle_L"))};
    return {sheets: pages.map(P => ({id: P.id, title: P.title, svg: doc(P), regions: P.regions, labels: P.labels})), measures,
      module: {id: CHAR.id, name_ar: CHAR.name_ar, version: CHAR.version, proportions_hu: prop, physics_profile: CHAR.physics_profile, hu_m: CHAR.hu_m, handedness: CHAR.handedness, head_study: CHAR.sheet.head_study, emotions: emotions().map(e => e.id),
        angle_files: {found: ang.found, missing: ang.missing}, fit_k: {sketch: cm.fit_k03, turnaround: cm.fit_k04}}};
  }
  return {run, pathOf, hatchIn, ink: Ink, capsulePts, circlePts, faceHead, drawShape, drawFig, fillOf, headOutline, headShape, fkPose, figExtent, gripGrid, worldGridFor, worldLabel};
})();
