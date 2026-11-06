/* ===== Shot bootstrap: loads the catalogue pieces named in SHOT (build/shot-config.js), prepares the sim, exposes window.Shot.
   Scene contract (tools/templates/shot/scene/main.js must define): PLAN, SIM, buildSim, renderFrame, shotAt, setLights, LAST. ===== */
"use strict";
const cv = document.getElementById("shot");
ctx = cv.getContext("2d", {alpha: false});
if (!CHAR || !WORLD) throw new Error("no character or world module registered (tools/render/characters/README.md)");
initPatterns();
const J = u => fetch(u).then(r => { if (!r.ok) throw new Error(u + " " + r.status); return r.json(); });
const CATB = SHOT.catalogue_url, CK = SHOT.catalogue;
const GRIP_IDS = CK.grips, EXPR = CK.expressions;
const READY = (async () => {
  const [plan, model, face, hm, strokes, card, tag, ...rest] = await Promise.all([J(SHOT.plan_url), J(CATB + CK.model), J(CATB + CK.face),
    J(CATB + CK.hand_model), J(CATB + CK.writing), J(CATB + CK.props.card), J(CATB + CK.props.tag),
    ...GRIP_IDS.map(h => J(CATB + CK.grip_dir + h + ".json")), ...EXPR.map(e => J(CATB + CK.expression_dir + e + ".json"))]);
  FD_ART = CK.face === CHAR.data.face ? face : await J(CATB + CHAR.data.face);
  PLAN = plan; FD = face; HM3 = hm; CARDJ = card; TAGJ = tag;
  GRIP_IDS.forEach((h, i) => GRIPS[h] = rest[i]);
  CAT = {model, expr: {}}; EXPR.forEach((e, i) => CAT.expr[e] = rest[GRIP_IDS.length + i].aus);
  WR = buildWriting(strokes, SHOT.writing_t0);
  await Promise.all(SHOT.fonts.map(f => document.fonts.load(f)));
  await document.fonts.ready;
  SIM = buildSim();
  renderFrame(0);
  return true;
})();
function diag() {   // build checks: digit misses, writing schedule, joint ranges
  const out = {writing: {t0: WR.t0, tEnd: +WR.tEnd.toFixed(3), total_mm: +WR.total.toFixed(1), events: WR.events.length}, miss: {}, maxElbow: {L: 0, R: 0}, minReach: 9, frames: NF, fps: FPS};
  for (const id of GRIP_IDS) out.miss[id] = Object.fromEntries(Object.entries(gripPose(id).miss).map(([k, v]) => [k, +v.toFixed(4)]));
  for (const s of SIM) { const R = s.R; for (const sd of ["L", "R"]) { out.maxElbow[sd] = Math.max(out.maxElbow[sd], +R.arm[sd].elbow.toFixed(1)); } }
  return out;
}
window.Shot = {ready: READY, renderFrame, record, still, stillMask, traceFrame, post, diag, povTextBoxes, sim: () => SIM, last: () => LAST, NF, FPS, id: SHOT.id};
