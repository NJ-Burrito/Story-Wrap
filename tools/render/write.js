/* ===== Mix v5 writing (F14, R-387..R-391): a two-sided card lying FRONT UP on the counter; the ink is a polyline in the card's
   own millimetres, revealed by arc length under the nib, right to left, letter bodies then dots; it moves with the card. ===== */
"use strict";
const CARD = {X: .10, Z: 2.42, yaw: -6 * Math.PI / 180, w: 125, h: 78, r: 3, hole: [-54, 0], rule: 17};
const PRESS = [49, 26];               // card mm: her right hand's index and middle pads on the card's lower-right corner
const INKCOL = "#1d2b4a";
let WR = null, CARDJ = null;
function cardState(t) {
  if (t < 3.0) return {dx: 0, lift: 0, yaw: CARD.yaw};
  const x = t - 3.0;
  return {dx: .004 * (1 - Math.exp(-x * 8)), lift: .006 * Math.max(0, ring(t, 3.0, 3, 6)), yaw: CARD.yaw + .05 * ring(t, 3.0, 2.2, 3.5) + .03 * (1 - Math.exp(-x * 6))};
}
/* card mm (u to the reader's right, v down the page) plus a height above the card in mm -> world metres */
function cardW(u, v, cs, h = 0) {
  const c = Math.cos(cs.yaw), s = Math.sin(cs.yaw), uu = u / 1000, vv = v / 1000;
  return [CARD.X + cs.dx - (uu * c - vv * s), YC - .0004 - cs.lift - h / 1000, CARD.Z + (uu * s + vv * c)];
}
/* the counter plane seen from her side (insert / POV): x = her right, y = toward her, metres, origin the card's rest centre */
const planeOf = w => [-(w[0] - CARD.X), w[2] - CARD.Z];
function cardOutlineMM(n = 6) {   // rounded rectangle, card mm
  const a = CARD.w / 2, b = CARD.h / 2, r = CARD.r, out = [];
  for (const [cx, cy, a0] of [[a - r, -b + r, -90], [a - r, b - r, 0], [-a + r, b - r, 90], [-a + r, -b + r, 180]])
    for (let i = 0; i <= n; i++) { const t = rad(a0 + 90 * i / n); out.push([cx + Math.cos(t) * r, cy + Math.sin(t) * r]); }
  return out;
}
function crSample(pts, step) {   // Catmull-Rom through the points, sampled every `step` mm
  const out = [pts[0]], g = i => pts[clamp(i, 0, pts.length - 1)];
  for (let i = 0; i < pts.length - 1; i++) { const p0 = g(i - 1), p1 = g(i), p2 = g(i + 1), p3 = g(i + 2), n = Math.max(2, Math.ceil(len2(sub2(p2, p1)) / step));
    for (let k = 1; k <= n; k++) { const t = k / n, t2 = t * t, t3 = t2 * t;
      out.push([0, 1].map(j => .5 * ((2 * p1[j]) + (-p0[j] + p2[j]) * t + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t2 + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * t3))); } }
  return out;
}
function buildWriting(js, t0) {
  const strokes = js.strokes.map(st => { const pts = st.pts.map(([x, y]) => [js.scale * (x + js.shift_x), js.baseline_v + js.scale * y]);
    const poly = st.kind === "dot" ? pts : crSample(pts, .4), cum = [0]; for (let i = 1; i < poly.length; i++) cum.push(cum[i - 1] + len2(sub2(poly[i], poly[i - 1])));
    return {id: st.id, kind: st.kind, poly, cum, len: cum[cum.length - 1]}; });
  const VB = 165, AIR0 = .035, AIRV = 620, ev = [], fr = d => Math.max(1, Math.round(d * FPS)) / FPS; let t = t0, done = 0;   // whole frames: a stroke ends ON a frame, so ink never grows across a lift
  strokes.forEach((s, i) => {
    if (i > 0) { const a = strokes[i - 1].poly[strokes[i - 1].poly.length - 1], b = s.poly[0], d = len2(sub2(b, a)), dur = fr(AIR0 + d / AIRV);
      ev.push({type: "air", a, b, t0: t, t1: t + dur, hmax: 1.6 + d * .07, ink: done}); t += dur; }
    const dur = fr(s.kind === "dot" ? .04 : s.kind === "hamza" ? s.len / VB * 1.5 : s.len / VB);
    ev.push({type: "ink", s: i, t0: t, t1: t + dur, ink: done}); t += dur; done += s.len; });
  const tEnd = t, last = strokes[strokes.length - 1].poly.slice(-1)[0], first = strokes[0].poly[0], total = done;
  const at = (s, L) => { const c = s.cum; let i = 1; while (i < c.length - 1 && c[i] < L) i++; const k = clamp((L - c[i - 1]) / Math.max(1e-6, c[i] - c[i - 1]), 0, 1); return lerp2(s.poly[i - 1], s.poly[i], k); };
  function nibAt(tt) {
    if (tt < t0) { const k = EASE.io(clamp(tt / t0, 0, 1)), from = add2(first, [-18, 24]); return {p: lerp2(from, first, k), h: 40 * (1 - k), active: false, ink: 0, phase: "approach"}; }
    for (const e of ev) if (tt <= e.t1 + 1e-6) {
      const k = clamp((tt - e.t0) / (e.t1 - e.t0), 0, 1);
      if (e.type === "air") return {p: lerp2(e.a, e.b, EASE.sine(k)), h: e.hmax * Math.sin(Math.PI * k), active: false, ink: e.ink, phase: "air"};
      const s = strokes[e.s], L = s.len * (s.kind === "dot" ? k : EASE.sine(k));
      return {p: at(s, L), h: 0, active: k > 0 && k < 1 + 1e-9, ink: e.ink + L, phase: "ink", stroke: e.s};
    }
    /* after the last dot: the nib lifts and hovers; the rattle at 2.45 s makes her freeze with it a little higher */
    const x = tt - tEnd, h = 9 * EASE.out(clamp(x / .18, 0, 1)) + 8 * sstep(2.45, 2.6, tt) + .6 * Math.sin(tt * 23) * sstep(2.45, 2.6, tt);
    const back = EASE.io(clamp(x / .32, 0, 1)); return {p: add2(last, [-14 * back, 26 * back]), h: h + 5 * back, active: false, ink: total, phase: "lifted"};   // she draws the hand back toward her: the finished word shows
  }
  return {strokes, events: ev, t0, tEnd, total, nibAt};
}
/* draw the revealed ink: strokes in writing order up to `inkLen` mm, mapped by m(card mm) -> screen [x, y]; returns the leading end */
function drawInk(m, inkLen, lw) {
  let left = inkLen, end = null;
  ctx.lineJoin = "round"; ctx.lineCap = "round"; ctx.strokeStyle = MODE === "sheet" ? "#000" : INKCOL; ctx.lineWidth = lw;
  for (const s of WR.strokes) { if (left <= 1e-6) break;
    ctx.beginPath(); let p0 = m(s.poly[0]); ctx.moveTo(p0[0], p0[1]); end = s.poly[0];
    if (s.kind === "dot") { const L = Math.min(left, s.len), q = lerp2(s.poly[0], s.poly[1], L / s.len), p = m(q); ctx.lineTo(p[0] + .01, p[1]); ctx.lineWidth = lw * 1.9; ctx.stroke(); ctx.lineWidth = lw; end = q; left -= s.len; continue; }
    for (let i = 1; i < s.poly.length; i++) { const seg = s.cum[i] - s.cum[i - 1];
      if (s.cum[i] <= left) { const p = m(s.poly[i]); ctx.lineTo(p[0], p[1]); end = s.poly[i]; }
      else { const q = lerp2(s.poly[i - 1], s.poly[i], clamp((left - s.cum[i - 1]) / seg, 0, 1)), p = m(q); ctx.lineTo(p[0], p[1]); end = q; break; } }
    ctx.stroke(); left -= s.len; }
  return end;
}
/* the leading end of the revealed ink (card mm), no drawing */
function inkEnd(inkLen) { let left = inkLen, end = null;
  for (const s of WR.strokes) { if (left <= 1e-6) break; if (left >= s.len) { end = s.poly[s.poly.length - 1]; left -= s.len; continue; }
    if (s.kind === "dot") return lerp2(s.poly[0], s.poly[1], left / s.len);
    let i = 1; while (i < s.cum.length - 1 && s.cum[i] < left) i++; return lerp2(s.poly[i - 1], s.poly[i], clamp((left - s.cum[i - 1]) / (s.cum[i] - s.cum[i - 1]), 0, 1)); }
  return end; }
/* the card in a front-view shot: a thin quad on the counter top (the camera above the counter sees its FRONT), ink and print on it */
function drawCardMS(t) {
  const cs = cardState(t), pmm = q => { const w = cardW(q[0], q[1], cs), p = P(w[0], w[1], w[2]); return [p.x, p.y]; }, c = P(CARD.X, YC, CARD.Z);
  mark("card"); if (cardFacing("ms") !== "front") return;
  const li = lightAt(CARD.X, YC - .02, CARD.Z), out = cardOutlineMM().map(pmm); S = 1;
  solid(() => { out.forEach((p, i) => i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])); ctx.closePath(); }, CARDJ.colour, li, .03 * c.s, {lw: 1.4, noRim: true, flat: true});
  const r0 = pmm([-58, CARD.rule]), r1 = pmm([58, CARD.rule]); line2(r0[0], r0[1], r1[0], r1[1], Math.max(.8, .0004 * c.s), "rgba(80,120,170,.7)");
  const nb = SIM ? SIM[Math.round(t * FPS)].nib : null;
  if (nb && nb.ink > 0) drawInk(pmm, nb.ink, Math.max(1.1, .0007 * c.s));
}
/* which face the camera sees: every Mix v5 view is above the counter plane, so the card shows its front (R-387) */
function cardFacing(view) { return view === "pov" ? "front" : C && C.y < YC ? "front" : "back"; }
