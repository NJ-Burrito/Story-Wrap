/* ===== Mix v5 POV plates (F14, R-388): drawn 2D inserts from HER side of the counter, not pitched 3D cameras =====
   s2 "top-pov": the counter plane seen from above her hands (x = her right, y = toward her); layers above the counter scale by
   eye/(eye - h), so hands, jar rim and dust slide over the paper with parallax. The nib touches the card's front and the viewer
   sees that same face, so the ink appears under the nib, right to left. s5 "pov": the tag hangs with its front toward her. */
"use strict";
const INS = {SL: [-.082 / HUM, .40 / HUM], SR: [.282 / HUM, .40 / HUM], hHand: .035, hR: .03};
let IC = null;
function insCam(f) {
  const t = f / FPS, sh = shotAt(t), I = sh.insert, k = clamp((t - sh.t0) / (sh.t1 - sh.t0), 0, 1);
  return {K: I.K, eye: I.eye, y0: I.y0_px, cx: lerp(I.cx0, I.cx1, k) + .0012 * noise(t * 1.4, 41), cy: lerp(I.cy0, I.cy1, k) + .001 * noise(t * 1.2, 43) + .0012 * ring(t, 2.995, 9, 9)};
}
const iscale = h => IC.K * IC.eye / (IC.eye - h);
function ipm(q, h = 0) { const s = iscale(h); return [W / 2 + (q[0] - IC.cx) * s, IC.y0 + (q[1] - IC.cy) * s]; }   // plane metres -> screen
const ipW = (w, h = 0) => ipm(planeOf(w), h);
/* the lamp seen from her POV: direction toward it on screen, and the flat offset of a shadow cast by a point h above the counter */
function lampPov() { const lp = planeOf([KEY.x, KEY.y, KEY.z]), Hl = YC - KEY.y, d = unit2(lp), hor = len2(lp); return {dir: d, k: hor / Math.max(.2, Hl)}; }
const shadowOff = (h, LP) => mul2(LP.dir, -h * LP.k * IC.K);
/* a hand as a pseudo-rig for CHAR.drawArms: R0 pins the hand's contact point on screen; one HU = pxHU at the hand's height */
function insertRig(A, pin, h) {
  const k = iscale(h) * HUM, c = A.contact;
  return {R0: {x: pin[0] - c[0] * k, y: pin[1] - c[1] * k, k}, arm: {[A.sd]: A}, w: clamp(k * .0122, 1.8, 6) / k, hands: false};
}
function insertLight() {   // the lamp's steady level: its flicker would push whole shapes across a posterised tone step (seen as popping, f26-f30)
  const k0 = {x: KEY.x, y: KEY.y, z: KEY.z, pow: KEY.pow}; Object.assign(KEY, {x: KEY.px, y: -2.65 + 2.4, z: KEY.pz, pow: 1.9});   // the lamp at rest
  const li = lightAt(CARD.X, YC - .04, CARD.Z); Object.assign(KEY, k0); const LP = lampPov(); li.ux = LP.dir[0]; li.uy = LP.dir[1]; return li; }
/* drawn wood grain: short ink strokes fixed in the counter plane (metres), so they move with it */
function woodGrain(proj, y0, y1, n, seed) {
  const RG = rng(seed); ctx.save(); ctx.lineCap = "round";
  for (let i = 0; i < n; i++) { const x = (RG() - .5) * .62, y = y0 + RG() * (y1 - y0), l = .02 + RG() * .07, w = .0015 * Math.sin(i), a = proj([x, y]), b = proj([x + l, y + w]), c = proj([x + l * .5, y + .0025 * (RG() - .5)]);
    ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.quadraticCurveTo(c[0], c[1], b[0], b[1]); ctx.lineWidth = RG() < .3 ? 3.2 : 2; ctx.strokeStyle = RG() < .5 ? "#2a170d" : "#3b2412"; ctx.stroke(); }
  ctx.restore();
}
function renderInsert(f) {
  const t = f / FPS, s = SIM[f], ins = s.ins, nb = s.nib, cs = s.cs; IC = insCam(f);
  const LP = lampPov(), li = insertLight();
  /* 1. beyond the counter's far edge (customer side) and the counter top */
  const yFar = ipm([0, ZCF - CARD.Z])[1], yNear = ipm([0, ZCB - CARD.Z])[1];
  ctx.fillStyle = "#120d14"; ctx.fillRect(0, 0, W, yFar);
  ctx.fillStyle = "#2a2028"; for (let i = 0; i < 6; i++) { const x = ((i * 233 + 40) % 1080); ctx.fillRect(x, 0, 6, yFar); }   // floor boards far below
  const wood = litCol([124, 96, 24], li, .74);
  ctx.fillStyle = wood; ctx.fillRect(0, yFar, W, yNear - yFar);
  ctx.save(); ctx.beginPath(); ctx.rect(0, yFar, W, yNear - yFar); ctx.clip();
  const sc = iscale(0); ctx.translate(ipm([0, 0])[0], ipm([0, 0])[1]); ctx.rotate(Math.PI / 2); ctx.globalAlpha = .55; ctx.fillStyle = patScaled(P_WOOD, sc / 1400); ctx.fillRect(-3000, -3000, 6000, 6000); ctx.restore();
  for (let k = -3; k <= 4; k++) { const y = ipm([0, k * .065 - .01])[1]; if (y > yFar && y < yNear) line2(0, y, W, y, 3, "#2a170d"); }   // plank seams
  woodGrain(q => ipm(q), ZCF - CARD.Z, ZCB - CARD.Z, 560, 7);   // drawn ink grain (counter plane: it slides with the paper)
  { const p = ipm([.30, -.20]), R = .55 * sc; steppedGlow(p[0] + LP.dir[0] * 120, p[1] + LP.dir[1] * 120, R, [255, 180, 100], Math.min(.2, .16 * KEY.pow / 1.9), .8, 3); }
  line2(0, yFar, W, yFar, 6, INKC); line2(0, yFar + 5, W, yFar + 5, 3, litCol([240, 190, 120], li, .8));
  /* 2. her coat front beyond the near edge (she stands at the counter) */
  ctx.fillStyle = litCol(CHAR.palette.coat, li, .62); ctx.fillRect(0, yNear, W, H - yNear); line2(0, yNear, W, yNear, 5, INKC);
  { const RC = rng(19); ctx.save(); ctx.beginPath(); ctx.rect(0, yNear, W, H - yNear); ctx.clip(); ctx.strokeStyle = "#5a3410"; ctx.lineWidth = 2.4;   // coat twill
    for (let i = 0; i < 70; i++) { const x = RC() * 1300 - 100, y = yNear + 12 + RC() * (H - yNear); ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + 46, y + 30); ctx.stroke(); } ctx.restore(); }
  /* 3. the jar of beads (top left): base on the counter, rim 0.17 m up (parallax) */
  const jp = planeOf([JAR.X, YC, JAR.Z]), jb = ipm(jp), jt = ipm(jp, JAR.h), rb = .065 * iscale(0), rt = .05 * iscale(JAR.h);
  /* 4. shadows on the counter and card: jar, both arms and hands, the pen (its rear stands ~0.1 m above the paper) */
  const shadowPath = () => {
    ctx.beginPath(); const so = shadowOff(JAR.h * .6, LP); ctx.moveTo(jb[0] + rb, jb[1]); ctx.arc(jb[0], jb[1], rb, 0, 6.3); ctx.moveTo(jb[0] + so[0] + rt, jb[1] + so[1]); ctx.arc(jb[0] + so[0], jb[1] + so[1], rt * 1.1, 0, 6.3);
    for (const sd of ["R", "L"]) { const A = ins[sd], h = sd === "L" ? INS.hHand + nb.h / 1000 : INS.hR, rig = insertRig(A, sd === "L" ? ipm(planeOf(s.nibW), nb.h / 1000) : ipm(planeOf(cardW(PRESS[0], PRESS[1], cs))), h), o = shadowOff(h, LP);
      ctx.save(); ctx.translate(rig.R0.x + o[0], rig.R0.y + o[1]); ctx.scale(rig.R0.k, rig.R0.k);
      for (const p of [...armPieces(A), ...handPieces(A)]) p.b();
      ctx.restore(); }
    const A = ins.L, pn = A.pose.pen, rig = insertRig(A, ipm(planeOf(s.nibW), nb.h / 1000), INS.hHand), tipS = add2([rig.R0.x, rig.R0.y], mul2(A.map(pn.tip), rig.R0.k)), rearS = add2([rig.R0.x, rig.R0.y], mul2(A.map(pn.rear), rig.R0.k));
    const t0 = add2(tipS, shadowOff(nb.h / 1000, LP)), t1 = add2(rearS, shadowOff(pn.rearH, LP)), rr = pn.r * rig.R0.k;
    capsule(t0[0], t0[1], t1[0], t1[1], rr * .5, rr * 1.2);
  };
  /* 5. the card, FRONT UP: outline, print (ruled line), punched hole, then the ink revealed so far, all in card mm (R-387, R-389) */
  const pmm = q => ipW(cardW(q[0], q[1], cs));
  mark("card");
  const out = cardOutlineMM().map(pmm); S = 1;
  solid(() => { out.forEach((p, i) => i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])); ctx.closePath(); }, CARDJ.colour, li, 14, {lw: 2.6, noRim: true, flat: true});
  { const a = pmm([-58, CARD.rule]), b = pmm([58, CARD.rule]); line2(a[0], a[1], b[0], b[1], 2.2, "rgba(80,120,170,.75)"); }
  { const hc = pmm(CARD.hole); ctx.beginPath(); ctx.arc(hc[0], hc[1], 13, 0, 6.3); ctx.fillStyle = litCol([214, 196, 160], li); ctx.fill(); ctx.lineWidth = 2.2; ctx.strokeStyle = INKC; ctx.stroke();
    ctx.beginPath(); ctx.arc(hc[0], hc[1], 6.5, 0, 6.3); ctx.fillStyle = litCol([150, 98, 58], li, .7); ctx.fill(); ctx.stroke(); }
  if (nb.ink > 0) drawInk(pmm, nb.ink, 4.4);
  ctx.save(); ctx.beginPath(); ctx.rect(0, yFar, W, yNear - yFar); ctx.clip(); shadowPath(); ctx.fillStyle = "rgba(20,10,24,.42)"; ctx.fill("nonzero"); ctx.restore();
  /* jar body over its shadow */
  ctx.save(); ctx.beginPath(); ctx.moveTo(jb[0] - rb, jb[1]); ctx.lineTo(jt[0] - rt, jt[1]); ctx.arc(jt[0], jt[1], rt, Math.PI, 0, false); ctx.lineTo(jb[0] + rb, jb[1]); ctx.arc(jb[0], jb[1], rb, 0, Math.PI, false); ctx.closePath();
  ctx.fillStyle = litCol([70, 140, 130], li, .9); ctx.fill(); ctx.lineWidth = 4; ctx.strokeStyle = INKC; ctx.stroke();
  ctx.beginPath(); ctx.arc(jt[0], jt[1], rt * .82, 0, 6.3); ctx.fillStyle = "#3d6f68"; ctx.fill(); ctx.stroke();
  const RB = rng(5); for (let i = 0; i < 16; i++) { const a = RB() * 6.28, r = RB() * rt * .7; ctx.beginPath(); ctx.arc(jt[0] + Math.cos(a) * r, jt[1] + Math.sin(a) * r, 9, 0, 6.3); ctx.fillStyle = "#ffc85a"; ctx.fill(); ctx.lineWidth = 2; ctx.stroke(); }
  ctx.restore();
  /* 6. her hands: right (pads on the corner, paper under the hand), then left with the pen in its layer slot (R-392) */
  const rigR = insertRig(ins.R, ipm(planeOf(cardW(PRESS[0], PRESS[1], cs))), INS.hR), rigL = insertRig(ins.L, ipm(planeOf(s.nibW), nb.h / 1000), INS.hHand);
  CHAR.drawArms(rigR, {}, {sides: ["R"], torso: false, li, angle: "top"});
  CHAR.drawArms(rigL, {pen: () => drawPen(ins.L, li)}, {sides: ["L"], torso: false, li, angle: "top"});
  /* 7. dust sifting down after the flap rattle (2.45 s): specks fall toward the counter, sliding toward the eye axis as they drop */
  if (t > 2.45) { const RD = rng(77); for (let i = 0; i < 26; i++) { const x0 = (RD() - .5) * .3, y0 = (RD() - .5) * .45, t0 = 2.45 + RD() * .35, fall = 1.1 + RD() * .6;
      if (t < t0) continue; const h = Math.max(0, .28 - (t - t0) * fall * .28); const p = ipm([x0 + .02 * Math.sin((t - t0) * 6 + i), y0], h), r = 2.2 + 5 * h / .28 + RD() * 2;
      ctx.beginPath(); ctx.arc(p[0], p[1], r, 0, 6.3); ctx.fillStyle = h > .01 ? "rgba(255,226,170,.85)" : "rgba(230,200,150,.6)"; ctx.fill(); } }
  /* 8. the falling bag's shadow sweeps over the counter from the right (2.62 -> 3.0 s), then the impact cuts */
  if (t > 2.62) { const k = clamp((t - 2.62) / .38, 0, 1), hb = .9 * (1 - k * k), bp = planeOf([BAG.X, YC, BAG.Z]), so = shadowOff(hb, LP), c = ipm(add2(bp, mul2(so, 1 / IC.K)));
    const g = sc * (1 + hb * .6); ctx.save(); ctx.translate(c[0], c[1]); ctx.rotate(-.12); ctx.beginPath(); ctx.ellipse(0, .02 * g, .17 * g, .1 * g, 0, 0, 6.3); ctx.moveTo(-.1 * g, -.07 * g); ctx.ellipse(0, -.07 * g, .1 * g, .07 * g, 0, Math.PI, 0);   // the bag's silhouette: body and handle loop
    ctx.fillStyle = `rgba(10,6,14,${(.25 + .4 * k).toFixed(3)})`; ctx.fill(); ctx.restore(); }
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  const Rb = CHAR.solve(Object.assign({}, s, {R0Now: rootScreen()}), rootScreen());   // the body (not drawn) for the trace's joints and contacts
  return {f, view: "top", angle: "top", R: Rb, cam: C, ic: Object.assign({}, IC), rigs: {L: rigL, R: rigR}, order: ORDER.slice(), sS: s, cs, nib: nb, bag: null, bagF: null};
}
/* line art (ink only) of the hands in the insert, for the seam check */
function insertMask(L, g) {
  const keep = ctx; ctx = g; MODE = "mask"; IC = L.ic;
  CHAR.drawArms(L.rigs.R, {}, {sides: ["R"], torso: false, li: insertLight(), angle: "top"});
  CHAR.drawArms(L.rigs.L, {pen: () => {}}, {sides: ["L"], torso: false, li: insertLight(), angle: "top"});
  MODE = "color"; ctx = keep;
}
/* ---------- s5: her POV of the tag hanging on the bag, FRONT toward her (and the lens) ---------- */
const POV = {cx: 540, top: 793, w: 560, ppm: 560 / .17};   // tag at screen scale ppm px per metre
function povFrame(f) {
  const t = f / FPS, sh = shotAt(t), k = clamp((t - sh.t0) / (sh.t1 - sh.t0), 0, 1), d = sh.insert.drift_px, sB = SIM[MAP.bag[f]];
  return {k, dx: d[0] * (k - .5) * 2 + 1.5 * noise(t * 1.3, 51), dy: d[1] * (k - .5) * 2, z: 1 + .018 * k, ang: -sB.btAng * .35 + .012 * Math.sin(t * 2.1), sB};
}
function povTagMap(F) {   // tag metres (x right, y down from the top-left corner) -> screen
  const c = Math.cos(F.ang), s = Math.sin(F.ang), ppm = POV.ppm * F.z, hx = POV.cx + F.dx, hy = POV.top + .012 * ppm + F.dy;   // pivot at the hole
  return (x, y) => { const X = x - TAGW / 2, Y = y - .012; return {x: hx + (X * c - Y * s) * ppm, y: hy + (X * s + Y * c) * ppm, s: ppm}; };
}
function povTextBoxes(f) { const F = povFrame(f), m = povTagMap(F);
  const bb = (x0, y0, x1, y1) => { const q = [m(x0, y0), m(x1, y0), m(x1, y1), m(x0, y1)], xs = q.map(v => v.x), ys = q.map(v => v.y); return {x: Math.round(Math.min(...xs)), y: Math.round(Math.min(...ys)), w: Math.round(Math.max(...xs) - Math.min(...xs)), h: Math.round(Math.max(...ys) - Math.min(...ys))}; };
  return {name: bb(TAGW / 2 - .036, .038, TAGW / 2 + .036, .08), date: bb(TAGW / 2 - .054, .088, TAGW / 2 + .054, .106)}; }
function renderPov(f) {
  const t = f / FPS, F = povFrame(f), m = povTagMap(F), sB = F.sB, li = lightAt(-.225, .345, 2.38), par = (k2, p) => [p[0] + F.dx * k2, p[1] + F.dy * k2];
  /* counter top seen steeply from her side; the customer side beyond is dark */
  ctx.fillStyle = "#100c13"; ctx.fillRect(0, 0, W, 330 + F.dy * .6);
  ctx.fillStyle = litCol([150, 98, 58], li, .9); ctx.fillRect(0, 330 + F.dy * .6, W, H);
  ctx.save(); ctx.beginPath(); ctx.rect(0, 330 + F.dy * .6, W, H); ctx.clip(); ctx.translate(F.dx * .6, F.dy * .6); ctx.rotate(Math.PI / 2); ctx.globalAlpha = .5; ctx.fillStyle = patScaled(P_WOOD, 2.2); ctx.fillRect(-3000, -3000, 6000, 6000); ctx.restore();
  for (const y of [520, 760, 1010]) line2(0, y + F.dy * .6, W, y + F.dy * .6 + 8, 3, "#2a170d");
  woodGrain(q => [540 + q[0] * 1800 + F.dx * .6, 330 + (q[1] + .2) * 4000 + F.dy * .6], -.2, .2, 640, 23);
  line2(0, 330 + F.dy * .6, W, 330 + F.dy * .6, 6, INKC);
  { const q = par(.6, [300, 520]); steppedGlow(q[0], q[1], 520, [255, 175, 95], Math.min(.4, .3 * KEY.pow / 1.9), .7, 3); }
  /* the bag from her side (its knot is on HER right, screen right), halftone, on threes in b3 */
  mark("bag");
  const b = sB.bag, wob = b ? b.sq * 30 : 0, bc = par(.85, [540, 1480]);
  ctx.save(); ctx.translate(bc[0], bc[1]); ctx.scale(1 + wob / 900, 1 - wob / 640);
  const bagBody = () => ctx.roundRect(-470, -330, 940, 700, 90), li2 = lightAt(BAG.X, YC - .1, BAG.Z);
  S = 1; solid(() => bagBody(), [122, 38, 34], li2, 260, {bag: true, lw: 3.4, mis: "bag"});
  if (ST.bag > .01) { ctx.save(); ctx.beginPath(); bagBody(); ctx.clip(); ctx.globalAlpha = .9; ctx.fillStyle = patScaled(P_DOT, 2.2); ctx.fillRect(-600, -500, 1200, 1000); ctx.restore(); }
  solid(() => { ctx.moveTo(-470, -250); ctx.lineTo(470, -250); ctx.lineTo(400, -60); ctx.quadraticCurveTo(0, 0, -400, -60); ctx.closePath(); }, [98, 28, 28], li2, 200, {bag: true, lw: 3, mis: "bag"});
  ctx.setLineDash([16, 12]); line2(-440, -230, 440, -230, 3, "#e8c696"); ctx.setLineDash([]);
  solid(() => { ctx.moveTo(-330, -330); ctx.quadraticCurveTo(0, -760, 330, -330); ctx.lineTo(290, -330); ctx.quadraticCurveTo(0, -690, -290, -330); ctx.closePath(); }, [90, 40, 30], li2, 120, {bag: true, lw: 3, mis: "bag"});
  ctx.restore();
  const knot = par(.85, [540 + 300, 1480 - 360]);
  /* the cold glow behind the tag, three flat stepped rings */
  { const c = m(TAGW / 2, TAGH / 2); steppedGlow(c.x, c.y, 470, [110, 220, 255], .5 * clamp(GLOW.pow, 0, 1.2), 1, 3); }
  /* string from the knot to the hole, then the tag: FRONT toward her: the name and the date on its clean plate (F4) */
  const hole = m(TAGW / 2, .012); mark("tag-string");
  ctx.beginPath(); ctx.moveTo(knot[0], knot[1]); ctx.quadraticCurveTo((knot[0] + hole.x) / 2 + 30, Math.min(knot[1], hole.y) - 60, hole.x, hole.y); ctx.lineWidth = 5; ctx.strokeStyle = "#e9dcc0"; ctx.stroke(); ctx.lineWidth = 1.6; ctx.strokeStyle = INKC; ctx.stroke();
  mark("bag-tag");
  const pc = [m(0, 0), m(TAGW, 0), m(TAGW, TAGH), m(0, TAGH)];
  solid(() => { ctx.moveTo(pc[0].x, pc[0].y); pc.forEach(v => ctx.lineTo(v.x, v.y)); ctx.closePath(); }, [205, 245, 255], li, 60, {lw: 3.4, noRim: true, flat: true, half: 0});
  drawPovPlate(m, F);
  /* dust in front of the tag (nearest layer, moves most) */
  { const RD = rng(91); for (let i = 0; i < 18; i++) { const x = RD() * W, y0 = RD() * H, sp = 20 + RD() * 40, y = (y0 + t * sp) % H, q = par(1.6, [x + 14 * Math.sin(t * 1.3 + i), y]);
      ctx.beginPath(); ctx.arc(q[0], q[1], 2.5 + RD() * 4, 0, 6.3); ctx.fillStyle = "rgba(200,240,255,.55)"; ctx.fill(); } }
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  const Rb = CHAR.solve(Object.assign({}, SIM[f], {R0Now: rootScreen()}), rootScreen());
  return {f, view: "pov", angle: "pov", R: Rb, cam: C, order: ORDER.slice(), sS: SIM[f], pov: F, bag: sB.bag, bagF: null};
}
function drawPovPlate(m, F) {
  const p = [m(.004, .008), m(TAGW - .004, .008), m(TAGW - .004, TAGH - .004), m(.004, TAGH - .004)];
  ctx.beginPath(); ctx.moveTo(p[0].x, p[0].y); p.forEach(v => ctx.lineTo(v.x, v.y)); ctx.closePath(); ctx.fillStyle = "#e4f6fb"; ctx.fill();
  { const h = m(TAGW / 2, .012); ctx.beginPath(); ctx.arc(h.x, h.y, 13, 0, 6.3); ctx.fillStyle = "#3a2c22"; ctx.fill(); ctx.lineWidth = 2.4; ctx.strokeStyle = INKC; ctx.stroke(); }
  ctx.save(); const o = m(TAGW / 2, 0); ctx.translate(o.x, o.y); ctx.rotate(F.ang); ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.direction = "rtl"; ctx.fillStyle = "#14100c";
  const k = o.s; ctx.font = `700 ${(.036 * k).toFixed(1)}px thmanyahseriftext`; ctx.fillText("هدى", 0, .06 * k);
  ctx.font = `700 ${(.0165 * k).toFixed(1)}px thmanyahsans`; ctx.fillStyle = "#3a0a06"; ctx.fillText("الخميس القادم", 0, .097 * k); ctx.restore();
}
function povTextMask(f, g) {
  const F = povFrame(f), m = povTagMap(F), o = m(TAGW / 2, 0), k = o.s;
  g.save(); g.translate(o.x, o.y); g.rotate(F.ang); g.textAlign = "center"; g.textBaseline = "middle"; g.direction = "rtl"; g.fillStyle = "#fff"; g.strokeStyle = "#fff"; g.lineJoin = "round";
  g.lineWidth = 2.5; g.font = `700 ${(.036 * k).toFixed(1)}px thmanyahseriftext`; g.fillText("هدى", 0, .06 * k); g.strokeText("هدى", 0, .06 * k);
  g.lineWidth = 2; g.font = `700 ${(.0165 * k).toFixed(1)}px thmanyahsans`; g.fillText("الخميس القادم", 0, .097 * k); g.strokeText("الخميس القادم", 0, .097 * k); g.restore();
}
