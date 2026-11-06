/* ===== Shared 2D helpers and face-data slot: the explicit dependency of hands.js, trace.js, write.js, insert.js and every character module =====
   Load this file right after core.js (before hands.js / write.js / the character module). It exports `Geo2` and installs the helpers as
   configurable global properties ONLY when nothing defined them yet, so a module that still declares its own `const add2 = ...` keeps working
   (a top-level const may shadow a configurable global property; it may not shadow a var or function).
   Helpers (same maths as the Hero rig, so the film does not change): rot2, add2, sub2, mul2, len2, unit2, lerp2, ik2 (2-bone IK, constant lengths,
   fixed bend side). `FD` (the face data, catalogue face.json) is set up here as a null slot; bootstrap.js, sheets.js and the shot page assign it.
   Needs `lerp` and `clamp` from core.js. ===== */
"use strict";
const Geo2 = (() => {
  const rot2 = (p, a) => [p[0] * Math.cos(a) - p[1] * Math.sin(a), p[0] * Math.sin(a) + p[1] * Math.cos(a)];
  const add2 = (a, b) => [a[0] + b[0], a[1] + b[1]], sub2 = (a, b) => [a[0] - b[0], a[1] - b[1]], mul2 = (a, k) => [a[0] * k, a[1] * k], len2 = a => Math.hypot(a[0], a[1]);
  const unit2 = v => { const n = Math.hypot(v[0], v[1]) || 1; return [v[0] / n, v[1] / n]; };
  const lerp2 = (a, b, k) => [lerp(a[0], b[0], k), lerp(a[1], b[1], k)];
  /* 2-bone IK: shoulder S, target T, bone lengths a (upper) and b (lower), bend = +1 / -1 (the elbow side never flips) -> {E, W, miss} */
  function ik2(S, T, a, b, bend) {
    const d = sub2(T, S), dist = len2(d), dc = clamp(dist, Math.abs(a - b) + 1e-4, a + b - 1e-4), ang = Math.atan2(d[1], d[0]);
    const A = Math.acos(clamp((a * a + dc * dc - b * b) / (2 * a * dc), -1, 1)), ea = ang + bend * A;
    const E = [S[0] + a * Math.cos(ea), S[1] + a * Math.sin(ea)], Wr = [S[0] + d[0] / (dist || 1) * dc, S[1] + d[1] / (dist || 1) * dc];
    return {E, W: Wr, miss: dist - dc};
  }
  const api = {rot2, add2, sub2, mul2, len2, unit2, lerp2, ik2};
  /* install only what is missing: a configurable property on the global object never blocks a later `const` of the same name */
  const G = globalThis;
  const put = (n, v) => { if (typeof G[n] === "undefined") Object.defineProperty(G, n, {value: v, writable: true, configurable: true, enumerable: false}); };
  for (const [n, f] of Object.entries(api)) put(n, f);
  if (!("FD" in G)) Object.defineProperty(G, "FD", {value: null, writable: true, configurable: true, enumerable: false});
  if (!("CAT" in G)) Object.defineProperty(G, "CAT", {value: null, writable: true, configurable: true, enumerable: false});   // per-shot catalogue slot (bootstrap.js assigns it; a multi-actor shot swaps it per actor)
  return api;
})();
