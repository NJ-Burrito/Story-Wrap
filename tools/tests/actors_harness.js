// Node harness for tools/render/actors.js (no browser): core.js + geom2d.js + hands.js + actors.js in one vm context, fake canvas, fake fetch, two fake character modules
// that declare the SAME top-level names (the reason for the isolated loader). Prints one JSON object; tests/test_multi_actor.py asserts on it.
const vm = require("vm"), fs = require("fs"), path = require("path");
const R = path.join(__dirname, "..", "render");
const canvasCtx = () => new Proxy({}, {get: (t, k) => k in t ? t[k] : () => {}, set: (t, k, v) => { t[k] = v; return true; }});
const doc = {createElement: () => ({width: 0, height: 0, getContext: canvasCtx})};
const MOD = n => `
const SKIN = [${n}, 0, 0], UA = ${n};
let CAT = null, FD = null;   // a legacy module declares the shared slots; the loader must cut this line
let ORDER = []; const mark = x => ORDER.push(x);
function rootScreen() { return {x: ${n} * 100, y: 0, k: 1}; }
function solveX(s, R0) { return {s, R0, mod: ${n}, fdSeen: FD && FD.tag}; }
function drawBodyX(R) { mark("body-${n}"); globalThis.__log.push("body" + ${n}); }
function drawArmsX(R) { mark("arms-${n}"); globalThis.__log.push("arms" + ${n}); }
registerCharacter({id: "mod${n}", hu_m: 0.2 + ${n} / 100, proportions_hu: {}, palette: {}, handedness: {}, sides: ["L", "R"], physics_profile: "p", data: {model: "m.json", face: "f.json", hand_model: "h.json", grip_dir: "g/", grips: ["a"], expression_dir: "e/", expressions: []},
  solve: solveX, drawBody: drawBodyX, drawArms: drawArmsX, massProxy: () => [], sheet: {}, root: {X: 0, Y: 0}, z: ${n}.5, rest_lengths_hu: {upper_arm: 1, forearm: 1}});`;
const sources = {"/tools/render/characters/mod1.js": MOD(1), "/tools/render/characters/mod2.js": MOD(2)};
const json = {};
for (const n of [1, 2]) { const b = `/catalogue/characters/mod${n}/`; json[b + "m.json"] = {m: n}; json[b + "f.json"] = {tag: "face" + n}; json[b + "h.json"] = {tag: "hand" + n}; json[b + "g/a.json"] = {tag: "grip" + n}; }
const sandbox = {console, Math, JSON, Object, Array, Number, String, Promise, document: doc, DOMMatrix: function () { this.scaleSelf = () => this; }, __log: [], SHOT: {canvas: [1080, 1920], fps: 24, duration_s: 2, draw_order: []},
  fetch: async u => sources[u] ? {ok: true, text: async () => sources[u]} : json[u] ? {ok: true, json: async () => json[u]} : {ok: false, status: 404}};
vm.createContext(sandbox);
const run = name => vm.runInContext(fs.readFileSync(path.join(R, name), "utf8"), sandbox, {filename: name});
["core.js", "geom2d.js", "hands.js", "actors.js"].forEach(run);
const ev = s => vm.runInContext(s, sandbox);
(async () => {
  const out = {};
  ev(`SHOT.actors = [{id: "far", module: "mod2", z: 3.0, layer: 0}, {id: "near", module: "mod1", z: 2.0, layer: 0}, {id: "near2", module: "mod1", z: 2.0, layer: 1}]`);
  await ev(`setupActors(SHOT.actors)`);
  out.ids = ev("ACTOR_IDS");
  out.same_module_two_instances = ev(`ACTORS.near.ctx !== ACTORS.near2.ctx && ACTORS.near.mod !== ACTORS.near2.mod && ACTORS.near.mod.id === ACTORS.near2.mod.id`);   // one character twice: own data, own module state
  out.legacy_slots_cut = !ev(`ACTORS.near.mod.solve.toString()`).includes("let CAT");   // the let line is outside the function; what matters is solve sees the GLOBAL FD:
  ev(`useActor("far")`); out.far_fd = ev("FD.tag"); out.far_hum = ev("HUM"); out.far_char = ev("CHAR.id"); out.far_solve_sees_fd = ev(`CHAR.solve({}, {}).fdSeen`);
  ev(`useActor("near")`); out.near_fd = ev("FD.tag"); out.near_solve_sees_fd = ev(`CHAR.solve({}, {}).fdSeen`); out.near_hm3 = ev("HM3.tag"); out.near_grip = ev("Object.keys(GRIPS)");
  out.with_restores = ev(`(() => { useActor("near"); const inner = withActor("far", () => CHAR.id); return [inner, CHAR.id, ACTIVE]; })()`);
  // order: default = farther first, then layer; declared window wins; tokens expand
  out.order_default = ev("orderAt(0)");
  ev(`SHOT.draw_order = [{f0: 10, f1: 20, order: ["near", "far:body", "far:arms", "near2"]}]`);
  out.order_window = ev("orderAt(12)"); out.order_after = ev("orderAt(20)");
  out.expand = ev(`expandOrder(["far", "near:arms"]).map(x => x.actor + ":" + x.part)`);
  out.bad_actor = ev(`(() => { try { expandOrder(["ghost"]); return false; } catch (e) { return String(e.message); } })()`);
  out.bad_token = ev(`(() => { try { expandOrder(["far:legs"]); return false; } catch (e) { return String(e.message); } })()`);
  // drawing: each token draws the right actor's code, per-actor layer lists are separate
  ev(`__log.length = 0; resetLayerOrders()`);
  const calls = ev(`drawActors(["far", "near:body", "near2", "near:arms"], {far: {R: {}}, near: {R: {}}, near2: {R: {}}}, null)`);
  out.layer_near2 = ev("ACTORS.near2.mod.layerOrder.get()");
  out.calls = calls; out.log = ev("__log"); out.layer_far = ev("ACTORS.far.mod.layerOrder.get()"); out.layer_near = ev("ACTORS.near.mod.layerOrder.get()");
  ev("resetLayerOrders()"); out.layer_after_reset = ev("ACTORS.far.mod.layerOrder.get()");
  out.solve = ev(`actorSolve("far", {f: 1}, {x: 0, y: 0, k: 1}).mod`);
  out.duplicate = await ev(`setupActors([{id: "far", module: "mod2"}]).then(() => false, e => String(e.message))`);
  console.log(JSON.stringify(out));
})().catch(e => { console.error(e); process.exit(1); });
