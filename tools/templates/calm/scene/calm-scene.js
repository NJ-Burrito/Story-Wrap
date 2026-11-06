/* ===== Calm shot scene: ONE generic scene for every calm template (tools/calm.py writes SHOT.calm; nothing here names a character) =====
   Data in: SHOT.calm = {set, actors[{id, kit, root_dx, pose, breath, expr, gaze, blinks, darts}], camera}. Per-character hooks come from
   kit-<id>.js (registerKit): root, cut line, extras (props), state extras, trace anchors. Scene contract: tools/render/trace-multi.js.
   renderFrame is a pure function of the frame number. Back to front: set, chute, counter, actors (body, arms), lamp, dust, foreground.
   Calm = one subject, slow camera, breathing, blinking, a small drift: the whole look is the catalogue's 2D ink art (CLAUDE.md "Calm format"). */
"use strict";
let PLAN = null, SIM = null, LAST = null;
const CALM = SHOT.calm;
/* INSERT_DEPTH (calm insert_depth template): a prop close-up built as separate planes so the parallax is real and the motion stays calm.
   CALM.depth = {hero, hero_z, dim_far, occ: {z, side, frac, ...}}. Back to front: the dimmed far set, the counter surface, the counter's props and the actor's side of it,
   the hero prop on its own plane with a flat 2D cast shadow on the counter top (the kit's hero hook), and a dark soft-edged occluder on the lens side. The camera is a
   close dolly (tools/calm.py t_insert_depth), so each plane moves at its own rate. No blur and no ramps: edges are stepped flat tones (the 2D rule). */
const DEPTH = CALM.depth || null;
let CALM_T = 0;   // seconds of the frame being drawn: kit hooks that animate a prop (a bag that falls in) read it
const KIT = {};
function registerKit(id, k) { KIT[id] = k; }
const AIDS = CALM.actors.map(a => a.id);
const ACT = Object.fromEntries(CALM.actors.map(a => [a.id, a]));
const BLINK_SHAPE = [[.6, 1, .7, .25]];
/* LIP SYNC (C6, 2026-10-25): SHOT.calm.lipsync = [{actor, line, start_s, ramp_s, keys[{t, id}]}], one per line an ON-SCREEN character speaks (tools/calm.py lipsync_entry,
   from work/voice/<ep>/visemes). The speaker's mouth is s.viseme = visemeTrackAt(entry, shotT - start_s) on every frame: V0 (closed, w 0) between words and in pauses.
   A speaker's jaw (AU26) is held shut so only the viseme opens the mouth; NO actor's jaw drifts on its own (it used to: a mouth opening and closing on the breath,
   unrelated to any word, in narrator scenes too). The narrator is not an actor, so its lines never reach a mouth. */
const LIP = {}; for (const e of (CALM.lipsync || [])) (LIP[e.actor] = LIP[e.actor] || []).push(e);

function shotAt(t) { return PLAN.shots.find(s => t >= s.t0 - 1e-6 && t < s.t1 - 1e-6) || PLAN.shots[PLAN.shots.length - 1]; }
function frameCam(f) {
  const t = f / FPS, sh = shotAt(t), k = clamp((t - sh.t0) / (sh.t1 - sh.t0), 0, 1), a = sh.cam0, b = sh.cam1;
  const e = sh.move === "drift" || sh.move === "track" ? k : EASE.sine(k);
  return {x: lerp(a.x, b.x, e), y: lerp(a.y, b.y, e), z: lerp(a.z, b.z, e), F: lerp(a.F, b.F, e), roll: 0, shot: sh.shot};
}
/* light: one lamp on a chain that sways in the draught (the world-a key); strength and colour come from the first actor's kit */
function setLights(f) {
  const t = f / FPS, L0 = KIT[AIDS[0]].light || {}, LF = CALM.life || {lamp: 1, flicker: 1, dust: true};   // calm: the lamp sways less, flickers less, no drifting dust (motion coverage band, qg_checks.CALM)
  const th = LF.lamp * (.085 * Math.sin(6.283 * .42 * t + .4) + .03 * noise(t * .8, 3));
  const px = -.42, py = -2.65, pz = 2.12, L = L0.L || 2.4, fl = 1 + LF.flicker * .06 * noise(t * 9, 1);
  KEY = {x: px + L * Math.sin(th), y: py + L * Math.cos(th), z: pz + .04 * Math.sin(6.283 * .31 * t), pow: (L0.pow || 3) * fl * (LF.gain || 1), fall: .9, c: L0.c || [1, .72, .44], th, px, pz};
  AL1 = {x: .02 * Math.sin(t * 1.3), y: -1.25, z: 5.0, pow: .55, fall: 2.0, c: [1, .7, .4]};
  AL2 = {x: -.02 * Math.sin(t * 1.1), y: -1.1, z: 6.8, pow: .5, fall: 2.2, c: [1, .66, .38]};
  GLOW = {x: 0, y: .3, z: 2.3, pow: 0, fall: 6, c: [.35, .85, 1]};
  LIGHTS = [KEY, AL1, AL2, GLOW];
  AMB = L0.amb || [.09, .1, .17]; FILLC = L0.fill || [30, 40, 78]; RIM = {c: L0.rim || [255, 217, 154], k: L0.rimk || .7};
}
/* the nearest layers (depth for the calm depth gate: bands and parallax): a row of tags on long strings across the top at Z 1.25 and two strings of tags at the lens edges at Z 1.45,
   swaying slowly on their own. On for a kit with `nearTags: true`, or for one scene with the plan parameter x_near=1. */
function drawNearTags(t) {
  const nk = KIT[AIDS[0]], Z = nk.nearZ || 1.25, ZE = Z + .2, sz = nk.nearScale || 1, c0 = shotAt(CALM_T).cam0, s = c0.F / (Z - c0.z);
  if (Z - C.z >= .3) { const yr = c0.y + (-30 - 960) / s;
    for (let k = 0; k < 12; k++) { const X = -.7 + k * .125 + .02 * Math.sin(k * 2.3); enter(X, yr, Z); const li = lightAt(X, yr + .2, Z);
      const ang = .6 * (.34 + .1 * gust(t)) * Math.sin(t * (1.5 + k * .13) + k * 1.9) + .03 * Math.sin(k);
      drawTag(0, 0, (.24 + .04 * (k % 3)) * sz, ang, .11 * sz, .075 * sz, li, {k: .9}); leave(); } }
  const Z2 = ZE, s2 = C.F / (Z2 - C.z);
  if (Z2 - C.z >= .3) for (const [px, ph] of [[22, 0], [1062, 2.1]]) { const X = C.x + (px - W / 2) / s2;
    for (let k = 0; k < 7; k++) { const Y = C.y + (150 + k * 250 - H / 2) / s2; enter(X, Y, Z2); const li = lightAt(X, Y, Z2);
      const ang = .6 * (.28 + .14 * gust(t)) * Math.sin(t * (1.9 + k * .21) + k * 1.3 + ph) + .05 * Math.sin(k * 2 + ph);
      drawTag(0, 0, .05 * sz, ang, .07 * sz, .05 * sz, li, {k: .85}); leave(); } }
}
/* the far set (back unit, aisle, harbour wall) is dimmed in two flat steps: the eye goes to the prop plane and the depth model reads it as far */
function flatDim(a) {
  if (!(a > 0)) return;
  ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0);
  for (const k of [.62, .38]) { ctx.fillStyle = `rgba(7,8,13,${(a * k).toFixed(3)})`; ctx.fillRect(0, 0, W, H); }
  ctx.restore();
}
function farDim() { flatDim(DEPTH.dim_far || 0); }
/* Q10: the plan's per-shot darkness (calm.py apply_grade): the set behind the actor, then (grade.actor) everything up to the actor, each as the same two flat value steps */
function gradeSet() { flatDim((CALM.grade || {}).set || 0); }
function gradeActor() { const g = CALM.grade || {}; flatDim(g.actor || 0); }
/* the occluder: a dark soft-edged mass on one lens edge (three stepped flat tones, hard shapes, no blur) with two paper tags hanging from it on strings,
   on its own plane (DEPTH.occ.z, nearest to the lens) so it slides faster than everything else; it sways slowly and never touches the hero. */
function drawOccluder(t) {
  const O = DEPTH.occ; if (!O || O.on === false) return;
  const c0 = shotAt(CALM_T).cam0, Z = O.z, d0 = Z - c0.z; if (d0 < .3 || Z - C.z < .3) return;
  const s0 = c0.F / d0, side = O.side === "right" ? 1 : -1, wm = O.frac * W / s0;   // world width of the mass
  const Xe = c0.x + side * (W / 2 - O.frac * W * .5) / s0 + side * O.bleed * wm;   // its centre (it bleeds a little past the frame edge)
  const Y0 = c0.y - (H / 2) / s0 * 1.1, Y1 = c0.y + (H / 2) / s0 * 1.1;
  enter(Xe, 0, Z); const li = lightAt(Xe, c0.y, Z);
  for (const [w, a] of [[1.45, .22], [1.18, .3], [.9, .42]]) { const xi = -side * wm * .5 * w, xo = side * wm * 3; ctx.fillStyle = `rgba(6,5,12,${a})`; ctx.fillRect(Math.min(xi, xo), Y0, Math.abs(xo - xi), Y1 - Y0); }
  for (const [k, yy, ph] of [[0, c0.y - (H * .52) / s0, 0], [1, c0.y - (H * .47) / s0, 2.1]]) { const ang = .05 * Math.sin(t * .8 + ph) + .02 * Math.sin(t * 1.7 + ph), xx = -side * wm * (.62 + .3 * k);
    ctx.beginPath(); ctx.moveTo(xx, Y0); ctx.lineTo(xx, yy); ctx.lineWidth = 2 / S; ctx.strokeStyle = "#0d0907"; ctx.stroke();
    drawTag(xx, yy, .05 + .035 * k, ang, .04, .026, li, {k: .5, lw: 2}); }
  leave();
}
const ease01 = k => EASE.sine(clamp(k, 0, 1));
/* ---------- one actor's tracks, precomputed once, deterministic ---------- */
function actorSim(a) {
  const kit = KIT[a.id], P0 = a.pose, br = a.breath, SM = [], ng = {rot: 0, rv: 0, fl: 0, fv: 0}, nk = kit.neck || {};
  const poseL = P0.hands.L ? actorGrip(a.id, P0.hands.L.grip) : null, poseR = P0.hands.R ? actorGrip(a.id, P0.hands.R.grip) : null;
  const blinkAt = f => { for (const b0 of a.blinks) { const dd = f - b0; if (dd >= 0 && dd < BLINK_SHAPE[0].length) return BLINK_SHAPE[0][dd]; } return 0; };
  const AUKEYS = ["1", "2", "4", "5", "6", "7", "9", "10", "12", "15", "20", "23", "26"];
  const mix = (x, y, k) => { const o = {}; for (const key of new Set([...AUKEYS, ...Object.keys(x), ...Object.keys(y)])) o[key] = (x[key] || 0) + ((y[key] || 0) - (x[key] || 0)) * k; return o; };
  for (let f = 0; f <= NF; f++) {
    const t = f / FPS, ph = 6.283 * br.cycles * f / NF, s = {f, t};   // whole cycles per shot: the breath loops seamlessly
    const bt = Math.sin(ph), bt2 = Math.sin(ph + 1.1);
    s.flex = P0.flex + br.flex_amp * bt; s.tilt = P0.tilt + br.tilt_amp * Math.sin(6.283 * br.sway_cycles * f / NF + .7); s.twist = 0; s.shrug = (P0.shrug || 0) + br.shrug_amp * bt;
    s.headTilt = P0.neckTilt + (a.head_tilt || 0) * ease01((f - a.change_f) / a.change_frames);
    const hb = br.hand_amp;
    s.hands = {};
    for (const sd of ["L", "R"]) { const h = P0.hands[sd]; if (!h) continue; const ph2 = sd === "L" ? 1 : 2.3;
      s.hands[sd] = {local: [h.local[0] + hb[0] * Math.sin(ph + ph2), h.local[1] + hb[1] * Math.sin(ph + ph2 + .8)], pose: sd === "L" ? poseL : poseR, contact: h.contact}; }
    // expression: AUs ease from the "from" expression to the "to" one over change_frames at change_f (a hold when from == to)
    const k = ease01((f - a.change_f) / a.change_frames);
    const au = mix(a.expr_from.aus, a.expr_to.aus, k); for (const key in au) au[key] = +(au[key] * a.intensity).toFixed(4);
    // a little life on the face: brows, lids and jaw drift with the breath (never a still mask); five controls move on their own
    const lf = 6.283 * br.cycles * f / NF;
    au["1"] += .12 + .10 * Math.sin(lf + .3); au["2"] += .11 + .10 * Math.sin(lf + 1.9); au["5"] += .10 + .10 * Math.sin(lf + 2.6);
    au["7"] += .11 + .10 * Math.sin(lf + 4.1); au["4"] += .10 + .10 * Math.sin(lf);   // the fifth drifting control is the brow (it was the jaw, AU26: a mouth that moved with no word)
    const eye = mix(a.expr_from.eye, a.expr_to.eye, k);
    const gk = a.gaze_change_f >= NF ? 0 : ease01((f - a.gaze_change_f) / a.gaze_change_frames);
    let gy = lerp(a.gaze_from[0], a.gaze_to[0], gk), gp = lerp(a.gaze_from[1], a.gaze_to[1], gk);
    for (const [dt, dy, dp, n] of a.darts) { const df = f - Math.round(dt * FPS); if (df >= 0 && df < n) { gy += dy; gp += dp; } }
    s.gazeRaw = [gy, gp]; s.eyeBias = [eye.eyeX || 0, eye.eyeY || 0]; s.au = au; s.blinkV = blinkAt(f);
    s.gazeTarget = k > .5 ? a.gaze_to_label : a.gaze_from_label;
    s.clothLag = [.02 * Math.sin(t * 2.3), .01 * Math.sin(t * 3.1)];
    s.viseme = null;
    if (LIP[a.id]) { au["26"] = 0; const vis = ACTORS[a.id].ctx.FD.visemes;
      for (const e of LIP[a.id]) { const v = visemeTrackAt(e, t - e.start_s); if (v && vis[v.id]) s.viseme = v; } }
    if (kit.state) kit.state(s, t, f);
    SM.push(s);
  }
  let pe = null;
  for (let f = 0; f <= NF; f++) {   // eyes lead; the head follows with a 2-frame delay through a critically damped spring (the engine's own rule)
    const s = SM[f], src = SM[Math.max(0, f - 2)], t = s.t;
    const want = clamp(src.gazeRaw[0] * (nk.rot_gain || .75), -(nk.rot_max || 40), nk.rot_max || 40);
    for (let q = 0; q < 4; q++) { const ac = 22 * 22 * (want - ng.rot) - 2 * 22 * ng.rv; ng.rv += ac / (FPS * 4); ng.rot += ng.rv / (FPS * 4); }
    const wantP = clamp((src.gazeRaw[1] - P0.neckFlex) * (nk.flex_gain || .45), nk.flex_lo === undefined ? -12 : nk.flex_lo, nk.flex_hi === undefined ? 18 : nk.flex_hi);
    for (let q = 0; q < 4; q++) { const ac = 18 * 18 * (wantP - ng.fl) - 2 * 18 * ng.fv; ng.fv += ac / (FPS * 4); ng.fl += ng.fv / (FPS * 4); }
    s.neck = {rot: ng.rot, flex: clamp(P0.neckFlex + ng.fl, -40, 42), tilt: s.headTilt};
    s.headYaw = ng.rot; s.faceYaw = clamp(ng.rot / 42, -1, 1); s.faceNod = (s.neck.flex + s.flex * .3) / 90 * .13;
    const prev = pe || s.gazeRaw, jump = Math.hypot(s.gazeRaw[0] - prev[0], s.gazeRaw[1] - prev[1]) > 6;
    s.eyeDir = jump ? [lerp(prev[0], s.gazeRaw[0], .6), lerp(prev[1], s.gazeRaw[1], .6)] : s.gazeRaw; pe = s.eyeDir;
    s.face = {eyeX: clamp((s.eyeDir[0] - s.headYaw) / 35 + s.eyeBias[0] * .35, -1, 1), eyeY: clamp((s.eyeDir[1] - s.neck.flex) / 30 + s.eyeBias[1] * .35, -1, 1), blink: s.blinkV, iris: 1, au: s.au};
  }
  return SM;
}
function buildSim() {
  for (const id of AIDS) if (KIT[id].init) KIT[id].init();   // once: a kit may patch its module (a filled mass proxy)
  // SIM[f] = {f, t, per: {actor id: that actor's pose state}}: the engine's diag skips entries without `hands`
  const per = Object.fromEntries(AIDS.map(id => [id, actorSim(ACT[id])]));
  return Array.from({length: NF + 1}, (_, f) => ({f, t: f / FPS, per: Object.fromEntries(AIDS.map(id => [id, per[id][f]]))}));
}
function rootOf(id) {
  const kit = KIT[id], m = ACTORS[id].mod, X = (kit.root ? kit.root.X : m.root.X) + (ACT[id].root_dx || 0), Y = kit.root ? kit.root.Y : m.root.Y;
  const p = P(X, Y, ACTORS[id].z); return {x: p.x, y: p.y, k: p.s * m.hu_m};
}
function renderFrame(f) {
  const t = f / FPS, tw = t * ((CALM.life && CALM.life.world) || 1); C = frameCam(f); setLights(f); ST = {room: 0, bag: 0, mis: 0, misBag: 0, tagLife: 1, front: null, wipe: null};
  MODE = "color"; resetLayerOrders(); CALM_T = t;
  ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = 1; ctx.globalCompositeOperation = "source-over"; ctx.direction = "ltr";
  ctx.fillStyle = "#07080d"; ctx.fillRect(0, 0, W, H);
  ctx.translate(W / 2, H / 2); ctx.rotate(C.roll); ctx.translate(-W / 2, -H / 2);
  const per = {}, R0s = {}, props = [];
  for (const id of AIDS) {
    const kit = KIT[id], s = SIM[f].per[id], R0 = rootOf(id), R = actorSolve(id, s, R0), m = ACTORS[id].mod;
    const li = lightAt((kit.root ? kit.root.X : m.root.X) + (ACT[id].root_dx || 0), (kit.root ? kit.root.Y : m.root.Y) - 2 * m.hu_m, ACTORS[id].z);
    R0s[id] = R0;
    per[id] = {R, s, angle: "front", view: "front", opts: kit.opts || {}, cutY: kit.cutY ? kit.cutY(R0) : 12, extras: kit.extras ? kit.extras(R, li, s) : {}, gaze: s.gazeTarget};
    if (kit.props) props.push(...kit.props(id, R0, R));
  }
  drawBackdrop(tw, () => { ctx.beginPath(); for (const id of AIDS) withActor(id, () => { for (const poly of CHAR.massProxyOnPlane(per[id].R, ZP)) { poly.forEach((q, i) => { const s2 = P(q[0], q[1], ZP); i ? ctx.lineTo(s2.x, s2.y) : ctx.moveTo(s2.x, s2.y); }); ctx.closePath(); } }); ctx.fillStyle = SHADOW_FILL(); ctx.fill("nonzero"); });
  if (DEPTH) farDim();
  drawChute(tw);
  drawCounter(tw, AIDS.flatMap(id => KIT[id].casters || []));
  gradeSet();   // the set and the counter, darker than the figure
  for (const id of AIDS) if (KIT[id].pre) KIT[id].pre(per[id].R, R0s[id]);   // under the actors: legs below a coat hem
  const calls = drawActors(orderAt(f), per, tk => { for (const id of AIDS) if (KIT[id].between) KIT[id].between(tk); });
  gradeActor();   // the figure and its props, before the lamp's own glow is laid on top
  drawLamp(tw);
  /* the hero lamp (E02 critic Q02): plan params x_lamp_thread = "tied" | "cut" lay the carbide lamp with its red thread on the counter, after the swaying key lamp; x_lamp_x (default -0.22) and
     x_lamp_z (default 2.3) place it (metres, the counter top is Z 2.22 to 2.6); x_lamp_scale default 1.7. Nothing is drawn without x_lamp_thread, so every other shot is unchanged. */
  { const xp = CALM.xp || {}, st = xp.lamp_thread;
    if (st === "tied" || st === "cut") { const X = xp.lamp_x === undefined ? -.22 : +xp.lamp_x, Z = xp.lamp_z === undefined ? 2.3 : +xp.lamp_z, sc = xp.lamp_scale === undefined ? 1.7 : +xp.lamp_scale;
      enter(X, YC, Z); drawLampThread(0, 0, st, lightAt(X, YC, Z), {scale: sc}); leave(); } }
  /* E03: the chute drops a second sent object. plan params x_drop = "mug", x_drop_t (second it leaves the chute; negative = already lying there), x_drop_x (where it lands, default -0.34), x_drop_z, x_drop_scale */
  { const xp = CALM.xp || {};
    if (xp.drop === "mug") { const t0 = xp.drop_t === undefined ? .6 : +xp.drop_t, lx = xp.drop_x === undefined ? -.34 : +xp.drop_x, lz = xp.drop_z === undefined ? 2.3 : +xp.drop_z, sc = xp.drop_scale === undefined ? 1.7 : +xp.drop_scale;
      drawChuteFlap(t, t0);
      const st = mugState(t, t0);
      if (st) { const X = lerp(CHUTE.X, lx, st.x), Y = YC + st.y; enter(X, Y, lz); drawMugThread(0, 0, lightAt(X, Y, lz), {scale: sc, rot: st.rot, noLying: !st.landed}); leave();
        if (xp.drop_puff !== "0" && st.landed && st.since >= 0 && st.since < .5) { const k = st.since / .5, p = P(lx, YC, lz); for (let i = 0; i < 7; i++) { const a = -Math.PI * (.1 + .8 * i / 6), r = p.s * .07 * k * (1 + .3 * (i % 2)); ctx.beginPath(); ctx.arc(p.x + Math.cos(a) * r * 2.2, p.y + Math.sin(a) * r * 1.1, Math.max(2, p.s * .012 * (1 - k)), 0, 6.2832); ctx.fillStyle = "rgba(226,206,170," + (.8 * (1 - k)).toFixed(2) + ")"; ctx.fill(); } } } } }
  /* E04: the chute drops a knotted red thread (x_drop = "thread"; x_drop_n = knots, "5" or a list "7,6,5" lying one above the other; world-a.js drawKnotThread) */
  { const xp = CALM.xp || {};
    if (xp.drop === "thread") { const t0 = xp.drop_t === undefined ? .6 : +xp.drop_t, lx = xp.drop_x === undefined ? -.1 : +xp.drop_x, lz = xp.drop_z === undefined ? 2.3 : +xp.drop_z, sc = xp.drop_scale === undefined ? 2.3 : +xp.drop_scale;
      const ns = String(xp.drop_n || "5").split(",").map(Number), curl = xp.drop_curl === undefined ? .6 : +xp.drop_curl;
      const fall = xp.drop_fall === undefined ? 0 : +xp.drop_fall; drawChuteFlap(t, t0, fall > 0);
      const st = mugState(t, t0, fall);
      if (st) { ns.forEach((n, i) => { const X = lerp(CHUTE.X, lx + (ns.length > 1 ? .2 * sc / 1.5 * i : 0), st.x), Y = YC + st.y; enter(X, Y, lz); drawKnotThread(0, 0, lightAt(X, Y, lz), {scale: sc, rot: st.rot * (1 + i * .3) + (st.landed ? .03 * (i % 2 ? 1 : -1) : 0), knots: n, curl: curl + .15 * i, noShadow: false}); leave(); });
        if (xp.drop_puff !== "0" && st.landed && st.since >= 0 && st.since < .5) { const k = st.since / .5, p = P(lx, YC, lz); for (let i = 0; i < 7; i++) { const a = -Math.PI * (.1 + .8 * i / 6), r = p.s * .07 * k * (1 + .3 * (i % 2)); ctx.beginPath(); ctx.arc(p.x + Math.cos(a) * r * 2.2, p.y + Math.sin(a) * r * 1.1, Math.max(2, p.s * .012 * (1 - k)), 0, 6.2832); ctx.fillStyle = "rgba(226,206,170," + (.8 * (1 - k)).toFixed(2) + ")"; ctx.fill(); } } } } }
  if (!CALM.life || CALM.life.dust) drawDust(tw, KIT[AIDS[0]].dustX || 0);
  if (!DEPTH) drawForeground(tw);   // the world's own near strings and pole are replaced by the one occluder in an insert_depth shot (they would sit a hand's width from the lens)
  { const xn = (CALM.xp || {}).near; if (!DEPTH && (xn === "1" || (xn !== "0" && AIDS.some(id => KIT[id].nearTags)))) drawNearTags(tw * (KIT[AIDS[0]].nearRate || 1)); }
  { const xd = CALM.xp || {}; if (xd.drain === "plan") drawDrainPlan(t, NF / FPS, xd); }
  { const xd = CALM.xp || {}; if (xd.threads === "plan") drawThreadsPlan(t, NF / FPS, xd); if (xd.ledger === "plan") drawLedgerPlan(t, NF / FPS, xd); }   // E04: the cut threads counted from above, the ledger page over the clerk's shoulder (world-a.js)
  /* E04 Q10: the world narrows toward the dilemma: x_narrow = 0..1 darkens flat bands from the four edges inward (three stepped bands, never a gradient); x_narrow_to = how much of the frame is left lit */
  { const xd = CALM.xp || {}; if (xd.narrow !== undefined) { const nv = +xd.narrow, k = clamp(t / (NF / FPS), 0, 1), a = clamp(nv * (xd.narrow_grow === "0" ? 1 : .55 + .45 * k), 0, .95);
      /* round 3 (critic Q07): the bands were three stacked rectangles whose edges showed as blocky steps. Now 28 nested elliptical rings, each a hair darker than the one outside it
         (about 3 % of the total each), so the edge falls off smoothly while the corners and sides stay as dark as before (luma_range unchanged). */
      ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); const NS = 28, amax = a * .88, sMin = .70, step = 1 - Math.pow(1 - amax, 1 / NS);
      for (let i = 0; i < NS; i++) { const sc = 1.28 - (1.28 - sMin) * (i / (NS - 1)); ctx.beginPath(); ctx.rect(-4, -4, W + 8, H + 8); ctx.ellipse(W / 2, H / 2, W * .5 * sc, H * .5 * sc, 0, 0, 6.2832, true); ctx.fillStyle = `rgba(2,3,6,${step.toFixed(4)})`; ctx.fill("evenodd"); }
      ctx.restore(); } }   // E03: the drain seen from above, painted over the whole frame (world-a.js drawDrainPlan)
  if (DEPTH) drawOccluder(t);   // x_near=0 turns the kit's near tags off for one scene (they add motion; a short scene may not afford it)
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  return (LAST = {f, cam: C, view: "ms", actors: per, draw_calls: calls, props, layers: AIDS.length === 1 && KIT[AIDS[0]].layers ? ACTORS[AIDS[0]].mod.layerOrder.get().slice() : []});
}
/* the drawn outline of each hand in canvas px (the no-touch proof of two actors, qg_checks "apart") */
function hullPx(pts) { const p = pts.slice().sort((a, b) => a[0] - b[0] || a[1] - b[1]), cr = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]), lo = [], up = [];
  for (const q of p) { while (lo.length >= 2 && cr(lo[lo.length - 2], lo[lo.length - 1], q) <= 0) lo.pop(); lo.push(q); }
  for (let i = p.length - 1; i >= 0; i--) { const q = p[i]; while (up.length >= 2 && cr(up[up.length - 2], up[up.length - 1], q) <= 0) up.pop(); up.push(q); }
  up.pop(); lo.pop(); return lo.concat(up); }
function handOutlinePx(R, sd) {
  const A = R.arm[sd], R0 = R.R0, pts = [A.W, A.map([.44, 0])]; for (const d of DIGITS) for (const q of A.hl[d].pts) pts.push(A.map(q));
  const pad = [], rr = .05 * (A.hs || 1); for (const p of pts) for (let k = 0; k < 8; k++) { const a = k / 8 * 6.2832; pad.push([p[0] + Math.cos(a) * rr, p[1] + Math.sin(a) * rr]); }
  return hullPx(pad).map(p => [+(R0.x + p[0] * R0.k).toFixed(1), +(R0.y + p[1] * R0.k).toFixed(1)]);
}
function traceExtra(id, rec, q, L) {
  rec.hand_outline_px = {L: handOutlinePx(q.R, "L"), R: handOutlinePx(q.R, "R")};
  const kit = KIT[id]; if (kit.trace) kit.trace(id, rec, q, L);
}
