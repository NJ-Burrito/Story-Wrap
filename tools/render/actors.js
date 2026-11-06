/* ===== Actors: several characters in one shot (tools/render/characters/README.md, "Several characters in one shot") =====
   One ACTOR = one instance of a character module in a shot: its own id, its own copy of the module's data (face, hand model, grips),
   its own pose state, its own depth and layer. The shared drawers (face.js, hands.js) and the modules read the single globals
   CHAR, HUM, FD, HM3, GRIPS, CAT; `useActor(id)` points them at one actor, `withActor(id, fn)` does it for the duration of fn.
   Nothing here names a character. A v5-style one-character shot never loads this file.
   Needs core.js (CHAR registry, registerCharacter) and hands.js (HM3, GRIPS); geom2d.js is recommended (slots FD, CAT). */
"use strict";
if (!("FD" in globalThis)) globalThis.FD = null;
if (!("CAT" in globalThis)) globalThis.CAT = null;
const ACTORS = {}, ACTOR_IDS = [];
let ACTIVE = null;

/* ---------------- isolated module loader ----------------
   Two character modules cannot both be classic <script>s: each declares top-level const/function names (SKIN, UA, solve..., drawHead)
   and the second would throw "already declared". The loader fetches the module source and runs it inside its own function scope,
   so every module keeps its own names. Every ACTOR evaluates its own copy (two instances of one character do not share module state such as the layer list). The shared slots FD and CAT are NOT the module's: a legacy top-level `let CAT = null, FD = null;`
   is cut out (it would shadow the slot the actors swap). The module's layer list (`ORDER`, written by mark()) is exposed as
   mod.layerOrder = {get(), reset()} so the trace can export it per actor. */
const SLOT_DECL = /^let\s+(?:CAT|FD)(?:\s*=\s*null)?(?:\s*,\s*(?:CAT|FD)(?:\s*=\s*null)?)*\s*;[^\n]*$/gm;
async function loadCharacterModule(url) {
  const r = await fetch(url); if (!r.ok) throw new Error("character module " + url + " " + r.status);
  const src = (await r.text()).replace(SLOT_DECL, "/* shared slots CAT, FD: swapped per actor by actors.js */");
  let reg = null, hook = null;
  const registerHere = m => { reg = m; return registerCharacter(m); };
  const fn = new Function("registerCharacter", "__orderHook", src + "\n;if (typeof ORDER !== 'undefined') __orderHook(() => ORDER, () => { ORDER = []; });\n//# sourceURL=" + url);
  fn(registerHere, (get, reset) => { hook = {get, reset}; });
  if (!reg) throw new Error("character module " + url + " did not call registerCharacter");
  reg.layerOrder = hook || {get: () => [], reset: () => {}};
  return reg;
}

/* ---------------- actors ----------------
   cfg (one entry of SHOT.actors): {id, module, z, layer, catalogue_url?}; z = distance from the camera plane in metres (larger = farther),
   layer = stacking slot used when two actors have the same z. */
const J_ = u => fetch(u).then(r => { if (!r.ok) throw new Error(u + " " + r.status); return r.json(); });
async function setupActors(list) {
  for (const cfg of list) {
    if (ACTORS[cfg.id]) throw new Error("duplicate actor id " + cfg.id);
    const mod = await loadCharacterModule("/tools/render/characters/" + cfg.module + ".js"), D = mod.data;
    const base = cfg.catalogue_url || "/catalogue/characters/" + mod.id + "/";
    const ck = cfg.catalogue || {};   // the shot's own list (shot.json actors[].catalogue, checked by the catalogue stage) wins over the module's full list
    const grips = ck.grips || D.grips || [], exprs = ck.expressions || D.expressions || [];
    const [model, face, hm, ...rest] = await Promise.all([J_(base + (ck.model || D.model)), J_(base + (ck.face || D.face)), J_(base + (ck.hand_model || D.hand_model)),
      ...grips.map(g => J_(base + (ck.grip_dir || D.grip_dir) + g + ".json")), ...exprs.map(e => J_(base + (ck.expression_dir || D.expression_dir) + e + ".json"))]);
    const G = {}; grips.forEach((g, i) => G[g] = rest[i]);
    const expr = {}; exprs.forEach((e, i) => expr[e] = rest[grips.length + i].aus);
    const artFace = (ck.face || D.face) === D.face ? face : await J_(base + D.face);
    const A = {id: cfg.id, cfg, mod, z: cfg.z !== undefined ? cfg.z : mod.z, layer: cfg.layer || 0, ctx: {FD: face, FD_ART: artFace, HM3: hm, GRIPS: G, CAT: {model, expr}}, poses: {}};
    ACTORS[cfg.id] = A; ACTOR_IDS.push(cfg.id);
  }
  return ACTORS;
}
function useActor(id) {
  const A = ACTORS[id]; if (!A) throw new Error("no actor '" + id + "'");
  CHAR = A.mod; HUM = A.mod.hu_m; FD = A.ctx.FD; FD_ART = A.ctx.FD_ART; HM3 = A.ctx.HM3; GRIPS = A.ctx.GRIPS; CAT = A.ctx.CAT; ACTIVE = id; return A;
}
function withActor(id, fn) { const prev = ACTIVE; useActor(id); try { return fn(ACTORS[id]); } finally { if (prev && prev !== id) useActor(prev); } }
/* a grip pose of one actor, cached (a pose built with options is rebuilt each call) */
function actorGrip(id, gripId, o) { return withActor(id, A => o ? gripPose(gripId, o) : (A.poses[gripId] || (A.poses[gripId] = gripPose(gripId)))); }
/* solve one actor's body for a pose state s (the actor's own); R0 is its root on screen (the module's rootScreen is not shared: the scene passes it) */
function actorSolve(id, s, R0) { return withActor(id, () => CHAR.solve(Object.assign({}, s, {R0Now: R0}), R0)); }

/* ---------------- draw order ----------------
   An order is a list back to front. A token is an actor id ("partner" = body then arms) or "id:body" / "id:arms" (a split, e.g. her arm in front
   of his body). The scene declares the order per frame range in shot.json (`draw_order`); without one, actors sort by z (farther first), then layer. */
function expandOrder(order) {
  const out = [];
  for (const tk of order) { const [a, part] = String(tk).split(":"); if (!ACTORS[a]) throw new Error("draw order names unknown actor '" + a + "'");
    if (part === undefined) out.push({actor: a, part: "body"}, {actor: a, part: "arms"}); else if (part === "body" || part === "arms") out.push({actor: a, part}); else throw new Error("bad draw-order token " + tk); }
  return out;
}
function depthAt(id, f) { const A = ACTORS[id], z = A.cfg.z_track ? A.cfg.z_track[f] : undefined; return z !== undefined ? z : A.z; }
function orderAt(f) {
  const win = (SHOT.draw_order || []).find(w => f >= w.f0 && f < w.f1);
  if (win) return win.order.slice();
  return ACTOR_IDS.slice().sort((a, b) => depthAt(b, f) - depthAt(a, f) || ACTORS[a].layer - ACTORS[b].layer);
}
function resetLayerOrders() { for (const id of ACTOR_IDS) ACTORS[id].mod.layerOrder.reset(); }
/* draw the actors named in per (id -> {R, cutY, extras, angle, opts}) in the frame's order; returns the calls in drawing order.
   between(token) runs after each token's drawing so the scene can put an object between two actors (a counter edge, a held prop). */
function drawActors(order, per, between) {
  const calls = [];
  for (const {actor, part} of expandOrder(order)) { const q = per[actor]; if (!q) continue;
    withActor(actor, () => { if (part === "body") CHAR.drawBody(q.R, q.cutY); else CHAR.drawArms(q.R, q.extras || {}, Object.assign({angle: q.angle}, q.opts || {})); });
    calls.push(actor + ":" + part); if (between) between(actor + ":" + part); }
  return calls;
}
