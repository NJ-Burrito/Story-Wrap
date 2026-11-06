// Node harness for the shared drawing code (no browser): loads geom2d.js, svgctx.js and face.js into one vm context with the few core.js names they need.
// Prints one JSON object of results; tests/test_shared_render.py asserts on it.
const vm = require("vm"), fs = require("fs"), path = require("path");
const R = path.join(__dirname, "..", "render");
const sandbox = {console, Math, JSON, Object, Array, Number, String};
vm.createContext(sandbox);
const run = (name) => vm.runInContext(fs.readFileSync(path.join(R, name), "utf8"), sandbox, {filename: name});
vm.runInContext(`var clamp = (x, a, b) => x < a ? a : x > b ? b : x, lerp = (a, b, k) => a + (b - a) * k;
  var ctx = null, CHAR = null;
  function smooth(pts, closed = true, k = 1) { ctx.moveTo(pts[0][0], pts[0][1]); for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]); if (closed) ctx.closePath(); }`, sandbox);
run("geom2d.js"); run("svgctx.js"); run("face.js");
const out = {};
vm.runInContext(`
var FD0 = {oval: {rx: .3, ry: .45, cy: 0}, eyes: {x: .12, y: -.05, w: .06, h: .03, tilt: .01, iris_r: .03, lash_w: .008}, brows: {y: -.14, thick: .02, taper: .5},
  nose: {tip_y: .1, wing_x: .05, wing_y: .08, base_w: .03, bridge_top_y: -.05, ink_w: .006}, lips: {y: .2, half_w: .1, upper_t: .03, lower_t: .04, bow_x: .5, bow: .01},
  visemes: {}, details: [{id: "chip", layer: "details", anchor: "mouth", unit: "hw", shape: "poly", pts: [[.1, .0], [.2, .0], [.15, .02]], fill: "ink", when: {open_min: .1}}]};
function face(au, extra) { const g = new SvgCtx(); ctx = g; const f = Object.assign({pal: n => "#888", mode: "sheet", yaw: 0, au, inkK: 1}, extra || {}); drawFaceFeatures(g, FD0, f); return g.out.join(""); }
function mouthY(au, extra) { const g = new SvgCtx(); ctx = g; const f = Object.assign({pal: n => "#888", mode: "sheet", yaw: 0, au, inkK: 1}, extra || {}); return drawFaceFeatures(g, FD0, f).mouth; }
`, sandbox);
const ev = s => vm.runInContext(s, sandbox);
// 1 helpers exist as globals and from Geo2
out.helpers = ["rot2", "add2", "sub2", "mul2", "len2", "unit2", "lerp2", "ik2"].every(n => typeof ev(n) === "function" && typeof ev("Geo2")[n] === "function");
out.fd_slot = ev("typeof FD") !== "undefined" && ev("FD") === null;
const ik = ev("ik2([0,0],[1.5,0],1,1,1)"); out.ik_len = Math.hypot(ik.E[0], ik.E[1]);
// 2 expression range: sheet range 1.5 opens the mouth further than range 1 for the same AU; film (color) mode unchanged
out.open_range1 = ev("mouthY({'26': .5}, {range: 1})").open; out.open_range15 = ev("mouthY({'26': .5})").open; out.open_color = ev("mouthY({'26': .5}, {mode: 'color'})").open;
// 3 hooks run in layer order
ev(`CHAR = {face_hooks: Object.fromEntries(FACE_LAYERS.map(l => [l, (g, f, info) => { (globalThis.__order = globalThis.__order || []).push(l + (info.mouth ? "" : "!")); }]))}`);
ev("face({})"); out.order = ev("__order"); out.layers = ev("FACE_LAYERS");
// 4 data-driven detail drawn only when the mouth is open enough
ev("CHAR = null");
const closed = ev("face({})"), open = ev("face({'26': .9})");
out.detail_closed = (closed.match(/<path/g) || []).length; out.detail_open = (open.match(/<path/g) || []).length;
// 5 Ink helpers
out.ink = {brush: (() => { const g = ev("new SvgCtx()"); ev("Ink").brush(g, [[0, 0], [10, 0], [20, 5]], 1, 4, 6); return g.out.join("").includes("fill=\"#000\""); })(),
  hatch: (() => { const g = ev("new SvgCtx()"); ev("Ink").hatch(g, [[0, 0], [10, 0], [10, 10], [0, 10]], 45, 2, 1); return g.out.join("").includes("clipPath") && g.out.join("").includes("stroke-width"); })(),
  cross: (() => { const g = ev("new SvgCtx()"); ev("Ink").crossHatch(g, [[0, 0], [10, 0], [10, 10], [0, 10]], 45, 2, 1); return (g.out.join("").match(/<path d="M[^"]*" fill="none"/g) || []).length; })(),
  spotted: (() => { const g = ev("new SvgCtx()"); ev("Ink").spotted(g, [[0, 0], [10, 0], [10, 10], [0, 10]], {nicks: 3, jitter: .5, seed: 3}); return g.out.join("").includes("#111") && g.out.join("").includes("#fff"); })()};
console.log(JSON.stringify(out));
