/* ===== Face renderer (F12), character-agnostic: eyes, brows, nose at every angle, lips, visemes. All proportions, colours and viseme shapes come from the character's face data (FD, catalogue face.json) =====
   Drawn on a generic 2D context g (the canvas, or SvgCtx from svgctx.js for catalogue sheet 07). Units: HU, origin = head centre.
   f = {yaw -1..1 (1.6 = side, sheet only), nod, au:{}, eyeX, eyeY, blink, iris, viseme:{id, w}, light: -1 key screen-left / +1 right,
        pal(name) -> colour string, mode: "color" | "mask" | "sheet", range: expression gain (see below), onlyMouth, hooks}
   Expression range: every action unit is multiplied by `range` (f.range, else FD.expr_range, else 1.5 in the "sheet" mode and 1 in the film), so brows, lids,
   mouth corners, jaw and cheeks travel further on the art-book sheets; the film path (range 1) is unchanged. In "sheet" mode the drawer also inks the
   expression lines the film leaves to colour: glabella (AU4), cheek crease (AU6), nasolabial folds (AU12/10), chin dimple (AU17).
   Per-character profile: FD.profile or CHAR.sheet.profile = {tip_x, mouth_x, mouth_w, eye_x, nose_wing:[[x,y],[x,y],[x,y]], sections:{brow,nose,mouth,jaw,skull}|outline}
   (see characters/README.md); sheets.js draws the outline, this file reads the numbers for the side view.
   Accessory hooks: CHAR.face_hooks (or f.hooks) = {<layer>: fn(g, f, info) | [fn...]} called in FACE_LAYERS order: behind and skin by the head drawer (sheets.js),
   beard, ears, eyes, nose, mouth, details, moustache, spectacles, hair, headwear, front by drawFaceFeatures. info = {yaw, ay, side, sgn, nod, au, A, mode, mask,
   sheet, u, FD, range, mouth, mx, my, hw, tip, eyes:[{sg,ex,ey,w}], X(p), col(name,grey), path/fill/ink/hatch helpers bound to g}.
   Small details: FD.details = [{id, layer, anchor: "mouth"|"head"|"nose"|"eye-L"|"eye-R", unit: "hu"|"hw", shape: "poly"|"line"|"dot", pts, r, fill, lw, views, when:{open_min, au:{id:[min,max]}}}]
   drawn by this file (a chipped tooth is a "poly" in the "details" layer anchored on the mouth with when.open_min). */
const FACE_LAYERS = ["behind", "skin", "beard", "ears", "eyes", "nose", "mouth", "details", "moustache", "spectacles", "hair", "headwear", "front"];
const FACE_MOUTH_LAYERS = ["mouth", "details", "moustache"];
const GENERIC_PROFILE = {   // facing +x, origin head centre; the shared fallback, split into the five sections a module may replace one by one
  tip_x: .3, mouth_x: .2, mouth_w: .45, nose_wing: [[.25, -.03], [.215, -.005], [.245, .02]],
  sections: {brow: [[-.2, -.5], [.12, -.47], [.2, -.3]], nose: [[.245, -.15], [.235, -.08], [.27, .04], [.325, .125], [.29, .145], [.25, .15]], mouth: [[.262, .2], [.245, .235], [.26, .26]], jaw: [[.235, .3], [.22, .37], [.15, .42], [0, .43]], skull: [[-.2, .3], [-.25, 0]]}};
function faceProfile(FDx) { const P = (typeof CHAR !== "undefined" && CHAR && CHAR.sheet && CHAR.sheet.profile) || (FDx && FDx.profile) || null; return P ? Object.assign({}, GENERIC_PROFILE, P) : GENERIC_PROFILE; }
function faceExprRange(FDx, f) { return f.range !== undefined ? f.range : (FDx && FDx.expr_range !== undefined ? FDx.expr_range : (f.mode === "sheet" ? 1.5 : 1)); }
function scaleAU(au, rg) { if (rg === 1) return au; const o = {}; for (const k in au) o[k] = typeof au[k] === "number" ? clamp(au[k] * rg, -2, 2) : au[k]; return o; }
function faceHookList(f, layer) { const HK = f.hooks || (typeof CHAR !== "undefined" && CHAR && CHAR.face_hooks) || null; if (!HK || !HK[layer]) return []; return Array.isArray(HK[layer]) ? HK[layer] : [HK[layer]]; }
function mouthShape(FD, au, vis) {
  const A = k => au[k] || 0;
  const s = {w: 1 + .1 * A("12") + .25 * A("20") - .1 * A("23"), cl: .6 * A("12") - .6 * A("15") + (A("12_asym") || 0), cr: .6 * A("12") - .6 * A("15") - (A("12_asym") || 0),
    open: A("26"), round: 0, teeth: .3 * A("26"), press: A("23"), under: 0, tongue: 0};
  if (vis && vis.w > 0) { const v = FD.visemes[vis.id].shape, k = vis.w;
    for (const key of ["w", "open", "round", "teeth", "press", "under", "tongue"]) s[key] = lerp(s[key], v[key] !== undefined ? v[key] : (key === "w" ? 1 : 0), k);
    s.cl += (v.cl || 0) * k; s.cr += (v.cr || 0) * k; }
  return s;
}
function faceFill(g, f, name) { if (f.mode === "mask") { g.save(); g.globalCompositeOperation = "destination-out"; g.fillStyle = "#000"; g.fill(); g.restore(); } else { g.fillStyle = f.pal(name); g.fill(); } }
function faceInk(g, f, w) { g.lineWidth = w * (f.inkK || 1); g.lineCap = "round"; g.lineJoin = "round"; g.strokeStyle = f.mode === "color" ? f.pal("ink") : "#000"; g.stroke(); }
/* data-driven small details (FD.details): a chipped tooth, a scar, a mole, a gap. Drawn in their `layer` by the face drawer; the film only inks them in mask mode */
function faceDetails(g, FDx, f, info, layer) {
  for (const d of (FDx && FDx.details) || []) {
    if ((d.layer || "details") !== layer) continue;
    const view = info.side ? "side" : info.ay > .25 ? "three-quarter" : "front", views = d.views || ["front", "three-quarter"]; if (!views.includes(view)) continue;
    const w = d.when || {}; if (w.open_min !== undefined && info.mouth.open < w.open_min) continue;
    let bad = false; for (const k in (w.au || {})) { const v = info.A(k), r = w.au[k]; if (v < r[0] || v > (r[1] === undefined ? 9 : r[1])) bad = true; } if (bad) continue;
    const an = d.anchor || "head", a = an === "mouth" ? [info.mx, info.my] : an === "nose" ? info.tip : an === "head" ? [0, 0] : (() => { const sg = an.endsWith("L") ? -1 : 1, e = info.eyes.find(q => q.sg === sg); return e ? [e.ex, e.ey] : null; })();
    if (!a) continue;
    const kx = d.unit === "hw" ? info.hw : 1, P = (d.pts || []).map(p => [a[0] + p[0] * kx * (d.mirror ? info.sgn : 1), a[1] + p[1]]);
    if (!P.length) continue;
    const inkC = info.mask ? "#000" : info.sheet ? "#000" : f.pal("ink"), lw = (d.lw || .006) * (f.inkK || 1);
    if (d.shape === "dot") { g.beginPath(); g.arc(P[0][0], P[0][1], d.r || .008, 0, 6.2832); g.fillStyle = d.fill === "ink" || info.mask ? inkC : (info.sheet ? "#000" : f.pal(d.fill || "ink")); g.fill(); }
    else if (d.shape === "line") { g.beginPath(); P.forEach((p, i) => i ? g.lineTo(p[0], p[1]) : g.moveTo(p[0], p[1])); g.lineWidth = lw; g.lineCap = g.lineJoin = "round"; g.strokeStyle = inkC; g.stroke(); }
    else { g.beginPath(); P.forEach((p, i) => i ? g.lineTo(p[0], p[1]) : g.moveTo(p[0], p[1])); g.closePath(); g.fillStyle = info.mask || d.fill === "ink" ? inkC : (info.sheet ? ({ink: "#000", mouth_in: "#333", teeth: "#fff", paper: "#fff", skin_shade: "#dcdcdc"})[d.fill] || "#555" : f.pal(d.fill || "mouth_in")); g.fill();
      if (d.outline) { g.lineWidth = lw; g.strokeStyle = inkC; g.stroke(); } }
  }
}
/* everything a hook (or the head drawer) needs to know about this face at this instant */
function faceInfo(g, FD, f) {
  const yaw = clamp(f.yaw || 0, -1.6, 1.6), ay = Math.abs(yaw), side = yaw > 1.2 || yaw < -1.2, sh = clamp(yaw, -1, 1) * .08, nod = f.nod || 0;
  const RG = faceExprRange(FD, f), au = scaleAU(f.au || {}, RG), A = k => au[k] || 0, E = FD.eyes, N = FD.nose, L = FD.lips, PR = faceProfile(FD), sgY = Math.sign(yaw) || 1, sheetM = f.mode === "sheet";
  const eyeAt = sg => { const far = Math.max(0, sg * clamp(yaw, -1, 1)); return {sg, far, ex: side && PR.eye_x !== undefined ? sgY * PR.eye_x : sh * (side ? 1.6 : 1) + sg * E.x * (1 - .22 * sg * clamp(yaw, -1, 1)) * (side ? .2 : 1), ey: E.y + nod, w: E.w * (1 - .32 * far) * (side ? .55 : 1)}; };
  const eyesInfo = [-1, 1].filter(sg => !(side && sg * yaw > 0)).map(eyeAt);
  /* mouth geometry first: the beard and moustache hooks need it */
  const m = mouthShape(FD, au, f.viseme), my = L.y + nod * 1.1, mx = side ? sgY * PR.mouth_x : sh * .7 + clamp(yaw, -1, 1) * .03;
  const hw = L.half_w * m.w * (1 - .38 * m.round) * (1 - .25 * Math.min(ay, 1)) * (side ? PR.mouth_w : 1);
  const tipX = side ? sgY * PR.tip_x : sh * .6 + clamp(yaw, -1, 1) * .07, ny = N.tip_y + nod;
  const mask = f.mode === "mask", u = .015 * (f.inkK || 1), inkCol = mask ? "#000" : sheetM ? "#000" : f.pal("ink");
  const info = {yaw, ay, side, sh, sgn: sgY, nod, au, A, mode: f.mode, mask, sheet: sheetM, u, FD, range: RG, PR, mouth: m, mx, my, hw, tip: [tipX, ny], tipX, ny, eyes: eyesInfo, eyeAt, onlyMouth: !!f.onlyMouth};
  info.X = p => [p[0] * sgY, p[1] + nod * (p[1] > -.1 ? 1 : .5)];
  info.col = (n, grey) => mask ? "#000" : sheetM ? grey : (f.pal ? f.pal(n) : grey);
  const trace = (pts, closed, sm, k) => { ctx = g; g.beginPath(); if (sm) smooth(pts, closed, k === undefined ? .6 : k); else { pts.forEach((p, i) => i ? g.lineTo(p[0], p[1]) : g.moveTo(p[0], p[1])); if (closed) g.closePath(); } };
  info.path = trace;
  info.fill = (pts, c, sm = true, k = .6) => { trace(pts, true, sm, k); g.fillStyle = c; g.fill(); };
  info.ink = (pts, lw, closed = false, sm = true, k = .6, dash) => { trace(pts, closed, sm, k); g.lineWidth = lw; g.lineCap = g.lineJoin = "round"; g.strokeStyle = inkCol; if (dash) g.setLineDash(dash); g.stroke(); if (dash) g.setLineDash([]); };
  info.hatch = (pts, a, gap, lw) => { if (mask || !sheetM || typeof Sheets === "undefined") return; Sheets.hatchIn(g, pts, a, gap, lw, false, .5); };
  return info;
}
/* run the hooks of one layer (the head drawer in sheets.js calls "behind" and "skin" with this) */
function faceRunHooks(g, FD, f, layer, info) {
  info = info || faceInfo(g, FD, f);
  if (f.onlyMouth && !FACE_MOUTH_LAYERS.includes(layer)) return info;
  for (const fn of faceHookList(f, layer)) { g.save(); try { fn(g, f, info); } finally { g.restore(); } }
  faceDetails(g, FD, f, info, layer); return info;
}
function drawFaceFeatures(g, FD, f) {
  const info = faceInfo(g, FD, f), {yaw, ay, side, sh, nod, A, sgY, sheetM, eyesInfo, m, my, mx, hw, tipX, ny, RG, PR} = Object.assign({}, info, {sgY: info.sgn, sheetM: info.sheet, eyesInfo: info.eyes, m: info.mouth});
  const E = FD.eyes, B = FD.brows, N = FD.nose, L = FD.lips;
  const hook = layer => { faceRunHooks(g, FD, f, layer, info); };
  hook("beard"); hook("ears");
  /* ---- eyes ---- */
  if (!f.onlyMouth) for (const ei of eyesInfo) {
    const sg = ei.sg, far = ei.far, ex = ei.ex, ey = ei.ey, w = ei.w;
    const open = clamp(1 + .5 * A("5") - .55 * A("7") - (f.lidUpper || 0) * .3, .1, 1.6 + .5 * (RG - 1)) * (1 - (f.blink || 0)), lowUp = .18 * A("7") + .15 * A("6");
    const iC = [ex - sg * w, ey + .004], oC = [ex + sg * w, ey - E.tilt], up = [ex + sg * .1 * w, ey - E.h * (.25 + 1.25 * open)], lo = [ex, ey + E.h * (.8 - 2 * lowUp)];
    const eyePath = () => { g.beginPath(); g.moveTo(iC[0], iC[1]); g.quadraticCurveTo(up[0], up[1], oC[0], oC[1]); g.quadraticCurveTo(lo[0], lo[1], iC[0], iC[1]); g.closePath(); };
    if (open > .06) {
      eyePath(); faceFill(g, f, "eye_white");
      if (f.mode !== "mask") { g.save(); eyePath(); g.clip();
        const ir = E.iris_r, ix = ex + (f.eyeX || 0) * w * .45 + sg * far * -.01, iy = ey + (f.eyeY || 0) * E.h * .4 + .004;
        g.beginPath(); g.ellipse(ix, iy, ir * (1 - .3 * far), ir, 0, 0, 6.2832); g.fillStyle = f.pal("iris"); g.fill();
        g.beginPath(); g.ellipse(ix, iy, ir * .45 * (f.iris || 1) * (1 - .3 * far), ir * .45 * (f.iris || 1), 0, 0, 6.2832); g.fillStyle = f.pal("pupil"); g.fill();
        const hl = -(f.light || -1); g.beginPath(); g.arc(ix - hl * ir * .35, iy - ir * .4, ir * .26, 0, 6.2832); g.fillStyle = f.pal("highlight"); g.fill();
        g.restore(); }
      g.beginPath(); g.moveTo(iC[0], iC[1]); g.quadraticCurveTo(up[0], up[1], oC[0], oC[1]); g.lineTo(oC[0] + sg * .018, oC[1] - .012); faceInk(g, f, E.lash_w);
      g.beginPath(); const lm = [lerp(iC[0], oC[0], .35), lerp(iC[1], oC[1], .35) + E.h * (.55 - 1.4 * lowUp)]; g.moveTo(lm[0], lm[1]); g.quadraticCurveTo(lerp(lo[0], oC[0], .5), lerp(lo[1], oC[1], .3), oC[0], oC[1]); faceInk(g, f, .007);
      g.beginPath(); g.moveTo(lerp(iC[0], up[0], .45), up[1] - .006 - .008 * open); g.quadraticCurveTo(up[0], up[1] - .022 - .006 * open, lerp(up[0], oC[0], .7), lerp(up[1], oC[1], .5) - .016); faceInk(g, f, .006);
    } else {   // closed lid: one lash curve bowed down
      g.beginPath(); g.moveTo(iC[0], iC[1]); g.quadraticCurveTo(ex, ey + E.h * .55, oC[0], oC[1]); g.lineTo(oC[0] + sg * .016, oC[1] - .008); faceInk(g, f, E.lash_w);
    }
    /* brow: a tapered filled stroke; AU1 lifts the inner end, AU2 the outer, AU4 lowers it and draws it in */
    const by = B.y + nod * .8, bIn = [ex - sg * w * (.95 - .2 * A("4")), by + .02 - .055 * A("1") + .03 * A("4")], bMid = [ex + sg * w * .25, by - .018 - .02 * A("1") - .03 * A("2") + .02 * A("4")],
      bOut = [ex + sg * w * (1.3 - .1 * far), by + .012 - .045 * A("2") + .01 * A("4")];
    const t0 = B.thick, t1 = B.thick * B.taper;
    g.beginPath(); g.moveTo(bIn[0], bIn[1] - t0 * .5); g.quadraticCurveTo(bMid[0], bMid[1] - t0 * .7, bOut[0], bOut[1] - t1 * .3);
    g.quadraticCurveTo(bOut[0] + sg * .01, bOut[1], bOut[0], bOut[1] + t1 * .3); g.quadraticCurveTo(bMid[0], bMid[1] + t0 * .4, bIn[0], bIn[1] + t0 * .5); g.closePath();
    if (f.mode === "color") { g.fillStyle = f.pal("brow"); g.fill(); } else { g.fillStyle = "#000"; g.fill(); }
    if (f.mode === "color" && A("6") > .05) { g.beginPath(); g.ellipse(ex + sg * .02, ey + .12, .055, .03, 0, 0, 6.2832); g.fillStyle = f.pal("blush"); g.fill(); }
  }
  /* ---- nose ---- */
  hook("eyes");
  if (f.onlyMouth) {} else if (side) {   // profile (sheet only): the nose is part of the profile line drawn by the head; here only the wing and nostril
    const nw = PR.nose_wing; g.beginPath(); g.moveTo(sgY * nw[0][0], ny + nw[0][1]); g.quadraticCurveTo(sgY * nw[1][0], ny + nw[1][1], sgY * nw[2][0], ny + nw[2][1]); faceInk(g, f, N.ink_w * .8);
  } else {
    const shadeSide = -(f.light || -1), wx = N.wing_x * (1 - .35 * ay);
    if (f.mode === "color") {   // bridge shade wedge: a flat tone, not a line
      g.beginPath(); g.moveTo(tipX * .25 + shadeSide * .03, N.bridge_top_y + nod); g.lineTo(tipX + shadeSide * .036, ny - .022); g.lineTo(tipX + shadeSide * .012, ny + .004); g.lineTo(tipX * .25 + shadeSide * .012, N.bridge_top_y + nod + .01); g.closePath();
      g.fillStyle = f.pal("skin_shade"); g.fill(); }
    if (ay > .25) {   // three-quarter: the bridge reads as one stroke on the far side
      const fs = -sgY; g.beginPath(); g.moveTo(sh * .3 + fs * .03, -.07 + nod); g.quadraticCurveTo(tipX + fs * .005 + sgY * .02, ny - .06, tipX + sgY * .02, ny - .006); faceInk(g, f, N.ink_w * .85); }
    // tip underside and nostril wings
    g.beginPath(); g.moveTo(tipX - N.base_w * (1 + .5 * sgY * clamp(yaw, -1, 1)), ny + .002); g.quadraticCurveTo(tipX, ny + .016, tipX + N.base_w * (1 - .5 * sgY * clamp(yaw, -1, 1)), ny + .002); faceInk(g, f, N.ink_w);
    for (const s2 of [-1, 1]) { const farW = Math.max(0, s2 * clamp(yaw, -1, 1)); if (farW > .6) continue;
      const wxs = tipX + s2 * wx * (1 - .5 * farW); g.beginPath(); g.moveTo(wxs - s2 * .004, N.wing_y + nod - .026); g.quadraticCurveTo(wxs + s2 * .012, N.wing_y + nod, wxs - s2 * .012, ny + .004); faceInk(g, f, N.ink_w * (1 - .3 * farW)); }
    if (A("9") > .05) { g.beginPath(); g.moveTo(tipX * .3 - .02, -.03 + nod); g.lineTo(tipX * .3 + .02, -.04 + nod); faceInk(g, f, .005); }
  }
  /* ---- mouth: lips are flat tones; ink only on the parting line and the corner tucks ---- */
  hook("nose");
  const cL = [mx - hw, my - m.cl * .03], cR = [mx + hw, my - m.cr * .03];
  const gT = my - m.open * .022 - .002 * m.round, gB = my + m.open * .075 + .002 * m.round, ut = L.upper_t * (1 - .45 * m.press) * (1 + .35 * m.round), lt = L.lower_t * (1 - .4 * m.press) * (1 + .25 * m.round);
  const tuck = m.under * .03, gB2 = lerp(gB, gT + .004, m.under);
  const upperPath = () => { g.beginPath(); g.moveTo(cL[0], cL[1]); g.quadraticCurveTo(mx - hw * .62, gT - ut * .85, mx - hw * L.bow_x, gT - ut); g.quadraticCurveTo(mx - hw * .1, gT - ut + .002, mx, gT - ut + L.bow);
    g.quadraticCurveTo(mx + hw * .1, gT - ut + .002, mx + hw * L.bow_x, gT - ut); g.quadraticCurveTo(mx + hw * .62, gT - ut * .85, cR[0], cR[1]);
    g.quadraticCurveTo(mx + hw * .45, gT + .004, mx, gT + .002); g.quadraticCurveTo(mx - hw * .45, gT + .004, cL[0], cL[1]); g.closePath(); };
  const lowerPath = () => { g.beginPath(); g.moveTo(cR[0], cR[1]); g.quadraticCurveTo(mx + hw * .5, gB2 + .002, mx, gB2 + .003); g.quadraticCurveTo(mx - hw * .5, gB2 + .002, cL[0], cL[1]);
    g.quadraticCurveTo(mx - hw * .7, gB2 + lt * .95 - tuck, mx, gB2 + lt - tuck); g.quadraticCurveTo(mx + hw * .7, gB2 + lt * .95 - tuck, cR[0], cR[1]); g.closePath(); };
  if (f.mode === "color") { g.beginPath(); g.moveTo(mx - hw * .45, gB2 + lt - tuck + .004); g.quadraticCurveTo(mx, gB2 + lt - tuck + .03, mx + hw * .45, gB2 + lt - tuck + .004); g.quadraticCurveTo(mx, gB2 + lt - tuck + .014, mx - hw * .45, gB2 + lt - tuck + .004); g.fillStyle = f.pal("skin_shade"); g.fill(); }
  const openNow = m.open > .04 || m.under > .3;
  if (openNow) {
    const inside = () => { g.beginPath(); g.moveTo(cL[0], cL[1]); g.quadraticCurveTo(mx - hw * .45, gT + .004, mx, gT + .002); g.quadraticCurveTo(mx + hw * .45, gT + .004, cR[0], cR[1]); g.quadraticCurveTo(mx + hw * .5, gB2 + .002, mx, gB2 + .003); g.quadraticCurveTo(mx - hw * .5, gB2 + .002, cL[0], cL[1]); g.closePath(); };
    inside(); faceFill(g, f, "mouth_in");
    if (f.mode !== "mask") { g.save(); inside(); g.clip();
      if (m.teeth > .05) { g.beginPath(); g.rect(mx - hw, gT - .01, 2 * hw, .012 + .02 * m.teeth); g.fillStyle = f.pal("teeth"); g.fill(); }
      if (m.tongue > .05) { g.beginPath(); g.ellipse(mx, gT + .02, hw * .45, .018 * m.tongue, 0, 0, 6.2832); g.fillStyle = f.pal("tongue"); g.fill(); }
      else if (m.open > .3) { g.beginPath(); g.ellipse(mx, gB2, hw * .6, .02, 0, 0, 6.2832); g.fillStyle = f.pal("tongue"); g.fill(); }
      g.restore(); }
  }
  upperPath(); faceFill(g, f, "lip_upper");
  lowerPath(); faceFill(g, f, "lip_lower");
  if (m.under > .3 && f.mode !== "mask") { g.beginPath(); g.rect(mx - hw * .55, gT, hw * 1.1, .014 * m.under); g.fillStyle = f.pal("teeth"); g.fill(); }
  g.beginPath(); g.moveTo(cL[0] - .004, cL[1] - .003); g.quadraticCurveTo(mx - hw * .45, gT + .006, mx, gT + .003); g.quadraticCurveTo(mx + hw * .45, gT + .006, cR[0] + .004, cR[1] - .003); faceInk(g, f, .011);
  if (openNow && m.open > .15) { g.beginPath(); g.moveTo(mx - hw * .4, gB2 + .002); g.quadraticCurveTo(mx, gB2 + .006, mx + hw * .4, gB2 + .002); faceInk(g, f, .006); }
  for (const c of [cL, cR]) { const sgc = c === cL ? -1 : 1; g.beginPath(); g.moveTo(c[0] - sgc * .004, c[1] - .008); g.quadraticCurveTo(c[0] + sgc * .006, c[1] - .002, c[0] - sgc * .002, c[1] + .009); faceInk(g, f, .006); }
  hook("mouth");
  if (sheetM && !side && !f.onlyMouth) {   // expression lines the film leaves to colour: inked only on the art-book sheets
    const lineI = (pts, lw) => { g.beginPath(); g.moveTo(pts[0][0], pts[0][1]); g.quadraticCurveTo(pts[1][0], pts[1][1], pts[2][0], pts[2][1]); faceInk(g, f, lw); };
    if (A("4") > .45) for (const s2 of [-1, 1]) lineI([[sh * .5 + s2 * .024, B.y + nod + .012], [sh * .5 + s2 * .03, B.y + nod + .04], [sh * .5 + s2 * .022, B.y + nod + .07]], .0055);
    if (A("6") > .4) for (const ei of eyesInfo) lineI([[ei.ex - ei.sg * ei.w * .75, ei.ey + .085], [ei.ex, ei.ey + .105 + .02 * A("6")], [ei.ex + ei.sg * ei.w * .75, ei.ey + .085]], .0055);
    if (Math.max(A("12"), A("10")) > .5) for (const s2 of [-1, 1]) { const farF = Math.max(0, s2 * clamp(yaw, -1, 1)); if (farF > .7) continue; lineI([[tipX + s2 * N.wing_x * 1.55, ny + .02], [tipX + s2 * (hw * 1.15 + .02), (ny + my) / 2], [mx + s2 * hw * 1.12, my - .02 - .015 * A("12")]], .0055); }
    if (A("15") > .5) for (const c of [cL, cR]) { const s2 = c === cL ? -1 : 1; lineI([[c[0] + s2 * .004, c[1] + .012], [c[0] + s2 * .014, c[1] + .06], [c[0] + s2 * .008, c[1] + .105]], .0055); }
    if (A("17") > .4) lineI([[mx - .035, my + .17], [mx, my + .17 + .02 * A("17")], [mx + .035, my + .17]], .0055);
  }
  hook("details"); hook("moustache"); hook("spectacles"); hook("hair"); hook("headwear"); hook("front");
  return {mouth: m, nose_tip: [tipX, ny], lips_c: [mx, my]};
}
/* ===== Viseme-track reader (voice stage, kb/quality/viseme-track.schema.json): visemeTrackAt(track, t) -> {id, w} | null =====
   A track is written by tools/voice.py visemes from the line's audio. `t` is seconds from the start of the LINE's audio (shot time minus the line's start).
   Keys are [{t, id}], each id held until the next key; V0 is rest. Returns null outside the track (the scene's own mouth takes over); w ramps in and out over track.ramp_s. */
function visemeTrackAt(track, t) {
  if (!track || !track.keys || !track.keys.length) return null;
  const K = track.keys, ramp = track.ramp_s || .04, end = K[K.length - 1].t;
  if (t < K[0].t || t > end) return null;
  let id = K[0].id;
  for (let i = 0; i < K.length; i++) { if (t >= K[i].t) id = K[i].id; else break; }
  return {id, w: id === "V0" ? 0 : Math.max(0, Math.min(1, Math.min((t - K[0].t) / ramp + .5, (end - t) / ramp + .5)))};
}

/* ===== The mouth as drawn, for the rig trace (C6 lip-sync checks LIPSYNC-ACTIVE / LIPSYNC-SILENT, qg_checks.rig_lipsync): R.mouth -> {open, w, round, teeth, press} per frame per actor ===== */
function mouthRec(m) {
  if (!m) return {open: 0, w: 1, round: 0, teeth: 0, press: 0};
  const q = v => +(+v || 0).toFixed(3);
  return {open: q(m.open), w: q(m.w), round: q(m.round), teeth: q(m.teeth), press: q(m.press)};
}
