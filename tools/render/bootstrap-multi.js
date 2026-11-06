/* ===== Multi-actor shot bootstrap (the counterpart of bootstrap.js): loads the plan, every actor's module and catalogue data, prepares the sim,
   exposes window.Shot. Scene contract: PLAN, SIM, buildSim, renderFrame, LAST (see trace-multi.js). Needs actors.js and trace-multi.js loaded first. ===== */
"use strict";
const cv = document.getElementById("shot");
ctx = cv.getContext("2d", {alpha: false});
if (!WORLD) throw new Error("no world module registered (tools/render/worlds/README.md)");
initPatterns();
const READY = (async () => {
  PLAN = await J_(SHOT.plan_url);
  await setupActors(SHOT.actors);
  useActor(ACTOR_IDS[0]);
  await Promise.all(SHOT.fonts.map(f => document.fonts.load(f)));
  await document.fonts.ready;
  SIM = buildSim();
  renderFrame(0);
  return true;
})();
function diag() {   // build checks: digit misses per grip, joint ranges, per actor
  const out = {frames: NF, fps: FPS, actors: {}};
  for (const id of ACTOR_IDS) withActor(id, A => {
    const o = out.actors[id] = {module: A.mod.id, z: A.z, miss: {}, maxElbow: {L: 0, R: 0}};
    for (const g of Object.keys(GRIPS)) o.miss[g] = Object.fromEntries(Object.entries(gripPose(g).miss).map(([k, v]) => [k, +v.toFixed(4)]));
    const R0 = {x: 0, y: 0, k: 1};   // the joint angles do not depend on where the root is on screen
    for (const s of SIM) { if (!s.hands) continue; const R = CHAR.solve(Object.assign({}, s, {R0Now: R0}), R0); for (const sd of CHAR.sides) o.maxElbow[sd] = Math.max(o.maxElbow[sd], +R.arm[sd].elbow.toFixed(1)); }
  });
  return out;
}
window.Shot = {ready: READY, renderFrame, record, still, diag, sim: () => SIM, last: () => LAST, NF, FPS, id: SHOT.id};
