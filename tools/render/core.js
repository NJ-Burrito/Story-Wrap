/* ===== Mix v4 core: flat 2D camera, cel shading (flat tones, hard edges), ink, light model =====
   F9 rules kept here: no yaw/pitch camera, no gradients in shading, no ctx.filter, no full-frame grade, no self-copy. */
"use strict";
// SHOT (fps, duration_s, canvas) is defined by the page before this file loads (build/shot-config.js).
const W = SHOT.canvas[0], H = SHOT.canvas[1], FPS = SHOT.fps, DUR = SHOT.duration_s, NF = Math.round(SHOT.fps * SHOT.duration_s);
let HUM = 0.207;   // metres per head unit of the active character: set by registerCharacter (characters/README.md)
const clamp = (x, a, b) => x < a ? a : x > b ? b : x, lerp = (a, b, k) => a + (b - a) * k, rad = d => d * Math.PI / 180, deg = r => r * 180 / Math.PI;
const EASE = {lin: k => k, io: k => k < .5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2, out: k => 1 - Math.pow(1 - k, 3), in: k => k * k * k,
  sine: k => .5 - .5 * Math.cos(Math.PI * k), back: k => { const c1 = 1.7, c3 = c1 + 1; return 1 + c3 * Math.pow(k - 1, 3) + c1 * Math.pow(k - 1, 2); }};
function KF(keys) { return t => { if (t <= keys[0][0]) return keys[0][1];
  for (let i = 1; i < keys.length; i++) { const k1 = keys[i]; if (t <= k1[0]) { const k0 = keys[i - 1];
    return k0[1] + (k1[1] - k0[1]) * EASE[k1[2] || "io"]((t - k0[0]) / (k1[0] - k0[0])); } }
  return keys[keys.length - 1][1]; }; }
function KV(keys) { return t => { if (t <= keys[0][0]) return keys[0][1].slice();
  for (let i = 1; i < keys.length; i++) { const k1 = keys[i]; if (t <= k1[0]) { const k0 = keys[i - 1], e = EASE[k1[2] || "io"]((t - k0[0]) / (k1[0] - k0[0]));
    return k0[1].map((v, j) => v + (k1[1][j] - v) * e); } }
  return keys[keys.length - 1][1].slice(); }; }
const ring = (t, t0, f, d) => t < t0 ? 0 : Math.exp(-d * (t - t0)) * Math.sin(6.2832 * f * (t - t0));
const sstep = (a, b, t) => { const k = clamp((t - a) / (b - a), 0, 1); return k * k * (3 - 2 * k); };
function rng(a) { return () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a);
  t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
function noise(x, seed) { const i = Math.floor(x), f = x - i;
  const h = n => { const s = Math.sin((n + seed * 57.3) * 127.1) * 43758.5453; return s - Math.floor(s); };
  return lerp(h(i), h(i + 1), f * f * (3 - 2 * f)) * 2 - 1; }

/* ---------------- canvas, flat camera ---------------- */
let ctx, C, S = 1, MODE = "color";     // MODE "color" | "mask" (ink-only line art of the character)
function P(X, Y, Z) { const d = Math.max(.05, Z - C.z), s = C.F / d; return {x: W / 2 + (X - C.x) * s, y: H / 2 + (Y - C.y) * s, s, d}; }
function enter(X, Y, Z, k = 1) { const p = P(X, Y, Z); ctx.save(); ctx.translate(p.x, p.y); ctx.scale(p.s * k, p.s * k); S = p.s * k; return p; }
function leave() { ctx.restore(); }
function poly(pts) { ctx.beginPath(); pts.forEach((q, i) => { const p = P(q[0], q[1], q[2]); i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y); }); ctx.closePath(); }
function poly2(pts) { pts.forEach((q, i) => { const p = P(q[0], q[1], q[2]); i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y); }); ctx.closePath(); }
function rrect(x, y, w, h, r) { ctx.roundRect(x, y, w, h, r); }
function capsule(x1, y1, x2, y2, w1, w2) { const a = Math.atan2(y2 - y1, x2 - x1), nx = -Math.sin(a), ny = Math.cos(a);
  ctx.moveTo(x1 + nx * w1, y1 + ny * w1); ctx.lineTo(x2 + nx * w2, y2 + ny * w2); ctx.arc(x2, y2, w2, a + Math.PI / 2, a - Math.PI / 2, true);
  ctx.lineTo(x1 - nx * w1, y1 - ny * w1); ctx.arc(x1, y1, w1, a - Math.PI / 2, a + Math.PI / 2, true); ctx.closePath(); }
/* smooth closed/open path through points (Catmull-Rom as bezier) */
function smooth(pts, closed = true, k = 1) {
  const n = pts.length; if (n < 2) return; const g = i => closed ? pts[(i + n) % n] : pts[clamp(i, 0, n - 1)];
  ctx.moveTo(pts[0][0], pts[0][1]);
  for (let i = 0; i < (closed ? n : n - 1); i++) { const p0 = g(i - 1), p1 = g(i), p2 = g(i + 1), p3 = g(i + 2), t = k / 6;
    ctx.bezierCurveTo(p1[0] + (p2[0] - p0[0]) * t, p1[1] + (p2[1] - p0[1]) * t, p2[0] - (p3[0] - p1[0]) * t, p2[1] - (p3[1] - p1[1]) * t, p2[0], p2[1]); }
  if (closed) ctx.closePath();
}

/* ---------------- character and world registry (tools/render/characters/README.md, worlds/README.md) ---------------- */
let CHAR = null, WORLD = null;
const CHAR_REQUIRED = ["id", "hu_m", "proportions_hu", "palette", "handedness", "sides", "physics_profile", "data", "solve", "drawBody", "drawArms", "massProxy", "sheet"];
const WORLD_REQUIRED = ["id", "bible_world", "rule", "locations", "materials", "sheet"];
function validateModule(kind, m, req) { const miss = req.filter(k => m[k] === undefined || m[k] === null); if (miss.length) throw new Error(kind + " module '" + (m && m.id) + "' lacks: " + miss.join(", ")); return m; }
/* every registered module is also kept by id: a shot with several characters picks one per actor (actors.js). CHAR stays "the active one" so a module and the shared drawers keep reading it. */
const CHAR_MODULES = {};
function registerCharacter(m) { CHAR = validateModule("character", m, CHAR_REQUIRED); HUM = m.hu_m; CHAR_MODULES[m.id] = m; return m; }
function registerWorld(m) { WORLD = validateModule("world", m, WORLD_REQUIRED); return m; }

/* ---------------- painted textures (built once; flat paint, hard edges) ---------------- */
function tex(w, h, fn) { const c = document.createElement("canvas"); c.width = w; c.height = h; fn(c.getContext("2d"), w, h); return c; }
const dotC = tex(10, 10, g => { g.fillStyle = "#0a0f2a"; g.beginPath(); g.arc(5, 5, 3.3, 0, 7); g.fill(); });
let P_DOT;
/* the halftone dot pattern is generic; a world adds its own textures through WORLD.initPatterns (worlds/README.md) */
function initPatterns() { P_DOT = ctx.createPattern(dotC, "repeat"); if (typeof WORLD !== "undefined" && WORLD && WORLD.initPatterns) WORLD.initPatterns(); }
function patScaled(p, k) { p.setTransform(new DOMMatrix().scaleSelf(k, k)); return p; }

/* ---------------- light: flat per shape (one colour per shape per frame) ---------------- */
let AMB, FILLC, RIM, KEY, GLOW, AL1, AL2, LIGHTS, ST;
function lightAt(X, Y, Z) {
  let r = AMB[0], g = AMB[1], b = AMB[2], bx = 0, by = 0, bi = 0, gx = 0, gy = 0;
  for (const L of LIGHTS) { if (L.pow <= 0) continue;
    const dx = L.x - X, dy = L.y - Y, dz = L.z - Z, d2 = dx * dx + dy * dy + dz * dz;
    const i = L.pow / (1 + d2 * L.fall) * (dz < 0 ? 1 : .6);
    r += L.c[0] * i; g += L.c[1] * i; b += L.c[2] * i;
    const n = Math.hypot(dx, dy) + 1e-4; bx += dx / n * i; by += dy / n * i; bi += i;
    if (L === GLOW) { gx = dx / n; gy = dy / n; } }
  const n = Math.hypot(bx, by) + 1e-6;
  return {r, g, b, ux: bx / n, uy: by / n, i: bi, gx, gy};
}
/* posterise the light level to 3 steps so tone never ramps across shapes (R-380) */
const q3 = v => Math.round(v * 6) / 6;
const litCol = (c, li, k = 1) => `rgb(${Math.min(255, c[0] * q3(li.r) * k) | 0},${Math.min(255, c[1] * q3(li.g) * k) | 0},${Math.min(255, c[2] * q3(li.b) * k) | 0})`;
function shadeCol(c, li, k = 1) { const f = FILLC, a = .38; const m = q3(Math.min(li.r, 1.4)) * .52 * k;
  return `rgb(${Math.min(255, c[0] * m * (1 - a) + f[0] * a) | 0},${Math.min(255, c[1] * m * (1 - a) + f[1] * a) | 0},${Math.min(255, c[2] * m * (1 - a) + f[2] * a) | 0})`; }
const INKC = "#120b08";

/* cel: the path from build() is filled with the lit tone; the crescent away from the light (shape minus the shape moved
   toward the light) gets the shade tone (or halftone dots in B); a hard rim line sits on the shade edge. 2-3 tone steps, hard edges. */
function cel(build, col, li, r, o = {}) {
  const rule = o.rule || "nonzero";
  ctx.beginPath(); build();
  if (MODE === "mask") { if (!o.noFill) { ctx.save(); ctx.globalCompositeOperation = "destination-out"; ctx.fillStyle = "#000"; ctx.fill(rule); ctx.restore(); } return; }
  if (!o.noFill) { ctx.fillStyle = litCol(col, li, o.k || 1); ctx.fill(rule); }
  if (o.flat) return;
  const d = r * (o.shadeK || .3), ux = o.ux !== undefined ? o.ux : li.ux, uy = o.uy !== undefined ? o.uy : li.uy;
  ctx.save(); ctx.clip(rule);
  crescentClip(build, ux * d, uy * d);
  ctx.fillStyle = shadeCol(col, li, o.k || 1); ctx.fillRect(-1e4, -1e4, 2e4, 2e4);
  const hv = o.half !== undefined ? o.half : (o.bag ? ST.bag : ST.room);
  if (hv > .01) { ctx.save(); if (ST.front && !o.bag) frontOutside(); ctx.globalAlpha = .85 * hv; ctx.fillStyle = patScaled(P_DOT, 1 / S); ctx.fillRect(-1e4, -1e4, 2e4, 2e4); ctx.restore(); }
  if (!o.noRim && RIM.k > .05) { const rc = RIM.c; ctx.beginPath(); build(); ctx.lineWidth = 7 / S * (o.rimW || 1); ctx.strokeStyle = `rgb(${rc[0]},${rc[1]},${rc[2]})`; ctx.globalAlpha = clamp(RIM.k * clamp(li.i, .3, 1), 0, .9); ctx.stroke(); }
  ctx.restore();
}
/* clip to the current clip minus the shape shifted by (dx,dy): the crescent on the far side of the light */
function crescentClip(build, dx, dy) {
  const m = ctx.getTransform(); ctx.beginPath(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.rect(-50, -50, W + 100, H + 100); ctx.setTransform(m);
  ctx.translate(dx, dy); build(); ctx.translate(-dx, -dy); ctx.clip("evenodd");
}
/* the carrier-bleed front: halftone only outside the glow front */
function frontOutside() { const f = ST.front, m = ctx.getTransform(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.beginPath(); ctx.rect(-50, -50, W + 100, H + 100);
  const n = 40; for (let i = n; i >= 0; i--) { const a = i / n * 6.2832, rr = f.R * (1 + .08 * noise(a * 3 + f.seed, 21)); const x = f.x + Math.cos(a) * rr, y = f.y + Math.sin(a) * rr; i === n ? ctx.moveTo(x, y) : ctx.lineTo(x, y); }
  ctx.closePath(); ctx.setTransform(m); ctx.clip("evenodd"); }
function ink(lw, mis) {
  ctx.lineJoin = "round"; ctx.lineCap = "round";
  const w = (lw || 2.6) * 1.6 / S, m = MODE === "mask" ? 0 : (mis === "bag" ? ST.misBag : mis ? ST.mis : 0);
  if (m > .01) { ctx.save(); ctx.globalAlpha = m; ctx.lineWidth = w * 1.3; ctx.translate(4 / S, 2 / S); ctx.strokeStyle = "#00bef0"; ctx.stroke();
    ctx.translate(-8 / S, -4 / S); ctx.strokeStyle = "#ff2a6e"; ctx.stroke(); ctx.restore(); }
  ctx.lineWidth = w; ctx.strokeStyle = MODE === "mask" ? "#000" : INKC; ctx.stroke();
}
/* object = cel + ink outline (props and set; the character uses its own merged-silhouette painter) */
function solid(build, col, li, r, o = {}) { cel(build, col, li, r, o); ctx.beginPath(); build(); ink(o.lw, o.mis); }
function line(x1, y1, x2, y2, w, c) { ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.lineWidth = w / S; ctx.strokeStyle = c || INKC; ctx.lineCap = "round"; ctx.stroke(); }
function line2(x1, y1, x2, y2, w, c) { ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.lineWidth = w; ctx.strokeStyle = c; ctx.stroke(); }
/* light pool / glow as 3 flat stepped rings (no radial gradient) */
function steppedGlow(x, y, R, rgb, a, sy = 1, steps = 3) {
  ctx.save(); ctx.translate(x, y); ctx.scale(1, sy); ctx.globalCompositeOperation = "lighter";
  for (let i = 0; i < steps; i++) { const rr = R * (1 - i / steps); ctx.beginPath(); ctx.arc(0, 0, rr, 0, 6.2832); ctx.fillStyle = `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${a / steps})`; ctx.fill(); }
  ctx.restore();
}
