/* ===== Mix v5 timeline: deterministic per frame (renderFrame(f) is a pure function of the frame number) =====
   v5 (F13-F15): hands from catalogue v3 grips with k-blends, 2D arms of constant drawn length, the card face up on the counter,
   the s2 insert and the s5 close-up are her POV (insert.js), the bag tag shows its stamped back to the front shots. */
let PLAN = null, SIM = null;
/* ---------- camera from the plan: flat, x/y/z/F only ---------- */
function shotAt(t) { return PLAN.shots.find(s => t >= s.t0 - 1e-6 && t < s.t1 - 1e-6) || PLAN.shots[PLAN.shots.length - 1]; }
function frameCam(f) {
  const t = f / FPS, sh = shotAt(t);
  if (sh.pov) { const r = sh.world_ref; return {x: r.x, y: r.y, z: r.z, F: r.F, roll: 0, shot: sh.shot, pov: true}; }
  const k = clamp((t - sh.t0) / (sh.t1 - sh.t0), 0, 1), e = sh.move === "track" || sh.move === "drift" ? k : EASE.sine(k), a = sh.cam0, b = sh.cam1;
  const c = {x: lerp(a.x, b.x, e), y: lerp(a.y, b.y, e), z: lerp(a.z, b.z, e), F: lerp(a.F, b.F, e), roll: 0, shot: sh.shot};
  if (sh.move === "handheld") { c.x += .006 * noise(t * 2.3, 11) + .003 * noise(t * 6.1, 12); c.y += .005 * noise(t * 2.1, 13); c.roll = .012 * noise(t * 1.7, 15); }
  if (sh.shot === "s3") { c.x += .02 * ring(t, 3.0, 7, 5); c.y += .025 * ring(t, 3.0, 8, 4.5); c.roll += .02 * ring(t, 3.0, 6, 4); }
  return c;
}
/* ---------- light per beat: flat colours, the key lamp swings on its chain ---------- */
function setLights(f) {
  const t = f / FPS, b = t < 3 ? 0 : t < 4.625 ? 1 : t < 6.875 ? 2 : 3;
  const th = .085 * Math.sin(6.283 * .42 * t + .4) + .03 * noise(t * .8, 3) + .26 * ring(t, 3.02, .55, .85);
  const px = -.42, py = -2.65, pz = 2.12, L = 2.4;
  const base = [1.9, 4.2, .8, 1.6][b] * (b === 1 ? 1 + .4 * Math.exp(-(t - 3.0) * 4) : 1);
  const fl = 1 + .06 * noise(t * 9, 1) + (b === 2 ? .08 * noise(t * 14, 5) : 0);
  const kc = [[1, .72, .42], [1, .3, .95], [.85, .62, .5], [.8, .8, .74]][b];
  KEY = {x: px + L * Math.sin(th), y: py + L * Math.cos(th), z: pz + .04 * Math.sin(6.283 * .31 * t), pow: base * fl, fall: .9, c: kc, th, px, pz};
  AL1 = {x: .02 * Math.sin(t * 1.3), y: -1.25, z: 5.0, pow: .55, fall: 2.0, c: [1, .7, .4]};
  AL2 = {x: -.02 * Math.sin(t * 1.1), y: -1.1, z: 6.8, pow: .5, fall: 2.2, c: [1, .66, .38]};
  const tc = SIM ? SIM[f].tagC : [-.225, .345, 2.38];
  GLOW = {x: tc[0], y: tc[1], z: tc[2] - .03, pow: t < 4.625 ? 0 : t < 6.875 ? (.55 + .4 * sstep(4.625, 5.6, t)) * (1 + .1 * Math.sin(t * 7)) : .3 * (1 - sstep(6.875, 7.6, t)) + .1, fall: 6, c: [.35, .85, 1]};
  LIGHTS = [KEY, AL1, AL2, GLOW];
  AMB = [[.13, .15, .22], [.34, .05, .4], [.04, .11, .17], [.08, .13, .17]][b];
  FILLC = [[30, 40, 78], [120, 20, 110], [16, 56, 72], [22, 60, 74]][b];
  RIM = [{c: [255, 217, 154], k: .7}, {c: [255, 110, 150], k: .95}, {c: [127, 224, 255], k: .9}, {c: [191, 239, 255], k: .8}][b];
  return b;
}
/* ---------- frame maps: ones / twos / threes (Mix v3 ramps kept) ---------- */
const MAP = {hero: [], bag: []};
(function () { for (let f = 0; f <= NF; f++) {
  let s; if (f < 72) s = f; else if (f <= 74) s = 72; else if (f === 75) s = 75; else if (f <= 110) s = 76 + 2 * Math.floor((f - 76) / 2);
  else { const r = [111, 111, 113, 113, 115]; s = f - 111 < r.length ? r[f - 111] : f; } MAP.hero.push(s);
  let b; if (f < 111) b = f; else if (f < 165) { const r = [111, 112, 113, 114, 114, 116, 116]; b = f - 111 < r.length ? r[f - 111] : 118 + 3 * Math.floor((f - 118) / 3); }
  else { const r = [165, 165, 167, 167, 169]; b = f - 165 < r.length ? r[f - 165] : f; } MAP.bag.push(b); } })();
/* ---------- body tracks ---------- */
const TR = {
  flex: KF([[0, 14], [2.42, 14], [2.62, 10], [3.0, 10], [3.083, -4, "out"], [3.45, -1], [4.0, 2], [4.625, 4], [5.45, 18], [6.875, 18], [7.25, 15], [7.8, 7], [9, 6]]),
  tilt: KF([[0, 3], [3, 3], [3.1, -3, "out"], [4.6, -1], [5.5, 2], [7, 2], [7.7, 0], [9, -1]]),
  twist: KF([[0, 6], [3, 6], [3.12, -6, "out"], [4.6, -4], [5.5, -6], [7.3, -4], [7.7, 0], [9, 0]]),
  shrug: KF([[0, 0], [3, 0], [3.083, .12, "out"], [3.6, .09], [4.6, .05], [5.5, .06], [6.9, .05], [7.7, .02], [9, .02]]),
  neckFlex: KF([[0, 26], [2.42, 26], [2.6, 4], [3.0, 6], [3.083, -12, "out"], [3.5, 4], [4.625, 10], [5.45, 22], [6.875, 20], [7.3, 22], [7.8, 16], [8.3, 16], [8.55, -6], [9, -4]]),
  neckTilt: KF([[0, 4], [3, 4], [3.1, -6], [4.6, -3], [5.5, 6], [6.875, 6], [7.6, -5], [9, -4]]),
};
const AU = {
  "1": KF([[0, 0], [2.42, 0], [2.64, .18], [2.9, .12], [3.0, .12], [3.125, .85, "out"], [3.6, .7], [4.6, .5], [5.1, .42], [5.5, .42], [5.58, .68, "out"], [6.875, .55], [7.3, .25], [9, .2]]),
  "2": KF([[0, 0], [2.42, 0], [2.64, .15], [2.9, .1], [3.0, .1], [3.125, .85, "out"], [3.6, .6], [4.6, .35], [5.1, .1], [6.875, .1], [7.3, .15], [7.88, .15], [7.96, .1], [9, .12]]),
  "4": KF([[0, .05], [3.0, .05], [3.125, 0], [4.6, .05], [5.1, .22], [5.5, .25], [5.58, .3], [6.875, .28], [7.3, .2], [7.88, .2], [7.96, .48, "out"], [9, .45]]),
  "5": KF([[0, 0], [3.0, 0], [3.125, .95, "out"], [3.6, .75], [4.6, .5], [5.1, .35], [5.5, .3], [5.58, .55, "out"], [6.875, .4], [7.3, .1], [7.88, .05], [7.96, 0], [9, 0]]),
  "6": KF([[0, .05], [1.96, .05], [2.04, .28, "lin"], [2.4, .2], [2.7, .05], [9, 0]]),
  "7": KF([[0, .08], [3.0, .08], [3.125, 0], [4.6, 0], [5.1, .1], [6.875, .12], [7.3, .15], [7.88, .15], [7.96, .6, "out"], [9, .55]]),
  "9": KF([[0, 0], [9, 0]]),
  "12": KF([[0, .12], [1.96, .12], [2.04, .4, "lin"], [2.4, .3], [2.75, .08], [3.0, .08], [3.125, 0], [9, 0]]),
  "15": KF([[0, 0], [4.6, 0], [5.1, .15], [5.5, .15], [5.58, .22], [6.875, .2], [7.3, .05], [9, .05]]),
  "20": KF([[0, 0], [3.0, 0], [3.125, .3, "out"], [3.8, .15], [4.6, .05], [5.1, 0], [9, 0]]),
  "23": KF([[0, .15], [1.96, .15], [2.04, .04, "lin"], [3.0, .05], [3.125, 0], [6.875, 0], [7.3, .2], [7.88, .2], [7.96, .45, "out"], [9, .42]]),
  "26": KF([[0, 0], [3.0, 0], [3.125, .75, "out"], [3.6, .4], [4.6, .25], [5.1, .18], [5.5, .15], [5.58, .35, "out"], [6.875, .25], [7.3, .05], [9, 0]]),
};
const AU12ASYM = KF([[0, 0], [6.875, 0], [7.5, .12], [9, .12]]);
const IRIS = KF([[0, 1], [3.0, 1], [3.125, .8], [4.6, .95], [5.5, 1.0], [5.58, 1.3, "out"], [6.875, 1.25], [7.5, .95], [9, .95]]);
const BLINKS = [[30, 0], [61, 0], [86, 0], [92, 0], [125, 1], [172, 0], [196, 0]], BLINK_SHAPE = [[.6, 1, .7, .25], [.5, .85, 1, 1, .8, .45, .2]];
const DARTS = [[.55, 3, -4, 4], [1.32, -4, 3, 3], [2.12, 4, 2, 3], [3.58, -5, -3, 4], [4.2, 5, 2, 3], [5.1, -4, 3, 3], [5.92, 4, -2, 3], [6.42, -3, -3, 3], [7.1, 4, 2, 3], [7.62, -4, 2, 4], [8.1, 3, -3, 3], [8.86, -3, 2, 3]];
/* mouthing her own name in b4: س ُ ه ى -> V7 V4 V9 V3 (catalogue face.json) */
function visemeAt(t) { const m = FD.mouthing_in_mix_v4, at = m.at_s; if (t < at[0] - .04 || t > m.end_s + .08) return null;
  let id = m.visemes[0]; for (let i = 0; i < at.length; i++) if (t >= at[i]) id = m.visemes[i];
  return {id, w: clamp((t - (at[0] - .04)) / .08, 0, 1) * clamp((m.end_s + .08 - t) / .08, 0, 1)}; }
/* ---------- props on the counter ---------- */
const JAR = {X: .30, Z: 2.30, w: .13, h: .17};   // the jar of yellow beads the card will label (moved clear of the card)
const BAG = {X: -.12, Z: 2.42}, TAGW = .17, TAGH = .12, STRING = .1;
function bagState(t) { const t0 = 2.62, t1 = 3.0; if (t < t0) return null;
  if (t < t1) { const k = (t - t0) / (t1 - t0); return {X: BAG.X, Y: lerp(CHUTE.yMouth + .1, YC, k * k), Z: lerp(CHUTE.Z + .02, BAG.Z, k), rot: .5 * (1 - k) - .12 * k, sq: 0}; }
  const x = t - t1; return {X: BAG.X, Y: YC - .02 * Math.max(0, Math.sin(Math.min(1, x / .2) * Math.PI)) * (x < .2 ? 1 : 0), Z: BAG.Z, rot: -.12 * Math.exp(-x * 6) * Math.cos(6.283 * 2 * x), sq: .2 * Math.exp(-x * 8) * Math.cos(6.283 * 3 * x)}; }
function bagKnot(b) { const c = Math.cos(b.rot), s = Math.sin(b.rot), lx = -.105, ly = -.2; return [b.X + (lx * c - ly * s) * (1 + b.sq * .7), b.Y + (lx * s + ly * c) * (1 - b.sq), b.Z - .02]; }
/* ---------- grips (catalogue v3). The right hand changes grip three times, each a k-blend (R-386): under the impact cover
   (3.0 -> 3.125 s, the switch lands on the declared smear frame f75), then 7 in-between frames each in b3 and b4. ---------- */
const POSEC = {};
const poseOf = id => POSEC[id] || (POSEC[id] = gripPose(id));
function rPose(t) {
  if (t < 3.0) return poseOf("press-card-R");
  if (t < 3.125) return blendPose(poseOf("press-card-R"), poseOf("startle-open-R"), (t - 3.0) / .125);
  if (t < 4.80) return poseOf("startle-open-R");
  if (t < 5.10) return blendPose(poseOf("startle-open-R"), poseOf("flat-support-R"), EASE.sine((t - 4.80) / .30));
  if (t < 7.08) return poseOf("flat-support-R");
  if (t < 7.375) return blendPose(poseOf("flat-support-R"), poseOf("pinch-tag-R"), EASE.sine((t - 7.08) / .295));
  return poseOf("pinch-tag-R");
}
/* ---------- the simulation (precomputed once, deterministic) ---------- */
function buildSim() {
  const SM = [], tagAng = [0, 0, 0, 0], tagVel = [0, 0, 0, 0], prevA = [], prev2 = [];
  /* the nib through b1 in her POV plane (HU), and its letter-scale part (nib minus a 7-frame mean) that the digits make */
  const NIBP = []; for (let f = 0; f <= NF; f++) { const t = f / FPS, nb = WR.nibAt(t); NIBP.push(mul2(planeOf(cardW(nb.p[0], nb.p[1], cardState(t))), 1 / HUM)); }
  const hfAt = f => { let a = [0, 0]; for (let d = -3; d <= 3; d++) a = add2(a, NIBP[clamp(f + d, 0, 71)]); return sub2(NIBP[f], mul2(a, 1 / 7)); };
  let lastNibW = null, graspLoc = null;
  /* the digits' share of each letter stroke: the pen shifts in the hand (hand frame, clamped, then smoothed 1-2-1 so no finger jumps) */
  const RAW = [], SHIFT = [];
  for (let f = 0; f < 72; f++) { const A = solveArm2D(INS.SL, NIBP[f], poseOf("tripod-pen-L"), 1, -1, UA, FA, 1), hf = hfAt(f);
    RAW.push([clamp((hf[0] * A.U[0] + hf[1] * A.U[1]) * .45, -.025, .025), clamp((hf[0] * A.Rv[0] + hf[1] * A.Rv[1]) * .45, -.025, .025)]); }
  for (let f = 0; f < 72; f++) { const a = RAW[Math.max(0, f - 1)], b = RAW[f], c = RAW[Math.min(71, f + 1)]; SHIFT.push([(a[0] + 2 * b[0] + c[0]) / 4, (a[1] + 2 * b[1] + c[1]) / 4]); }
  let neckRot = 0, neckRotV = 0, neckFl = 0, neckFlV = 0, btAng = 0, btVel = 0, prevKnot = null, prevKnot2 = null;
  for (let f = 0; f <= NF; f++) {
    const t = f / FPS, s = {f, t}; C = frameCam(f);
    s.flex = TR.flex(t); s.tilt = TR.tilt(t); s.twist = TR.twist(t); s.shrug = TR.shrug(t); s.headTilt = TR.neckTilt(t);
    s.bag = bagState(t);
    /* bag tag: pendulum from the handle knot while it hangs; pinched and lifted from 7.375 s */
    if (s.bag) { const kn = bagKnot(s.bag); let acc = 0; if (prevKnot && prevKnot2) acc = (kn[0] - 2 * prevKnot[0] + prevKnot2[0]) * FPS * FPS;
      const land = t >= 3.0 && t < 3.05 ? 30 : 0;
      for (let q = 0; q < 4; q++) { const a = -(9.8 / .15) * Math.sin(btAng) - 3.0 * btVel - acc * Math.cos(btAng) / .15 * .5 + land * (q === 0 ? 1 : 0) + .6 * Math.sin(t * 2.2) * gust(t) * (t > 4.625 && t < 6.875 ? .15 : 1); btVel += a / (FPS * 4); btAng += btVel / (FPS * 4); }
      btAng = clamp(btAng, -1.2, 1.2); prevKnot2 = prevKnot; prevKnot = kn; s.knot = kn; }
    s.btAng = btAng;
    /* hands (catalogue v3 grips). b1: the nib follows the writing; her POV solve (counter plane, HU) splits each letter stroke
       between the digits (the pen shifts in the hand) and the wrist (the smooth line), then the front view reuses the same poses. */
    const H = {}, R0 = rootScreen(), loc = w => toLocal(R0, w[0], w[1], w[2]), chestL = [.45, -.98], chestR = [-.42, -1.15];   // startle: both hands jerk up off the counter and freeze open above it (2D bones: hands kept low and inside the shoulders, elbows stay at mid-height)
    const cs = cardState(t), nb = WR.nibAt(t), nibW = cardW(nb.p[0], nb.p[1], cs, nb.h); s.nib = nb; s.cs = cs; s.nibW = nibW;
    let poseL = poseOf("tripod-pen-L");
    const poseR = rPose(t);
    if (t < 3.0) {
      const T_L = NIBP[f], T_R = mul2(planeOf(cardW(PRESS[0], PRESS[1], cs)), 1 / HUM);
      const sh = SHIFT[f];
      poseL = gripPose("tripod-pen-L", {penShift: sh}); const A = solveArm2D(INS.SL, T_L, poseL, 1, -1, UA, FA, 1);
      const B = solveArm2D(INS.SR, T_R, poseR, -1, 1, UA, FA, 1);
      s.ins = {L: Object.assign(A, {pose: poseL, hl: handGeom(poseL), sd: "L", rs: 1}), R: Object.assign(B, {pose: poseR, hl: handGeom(poseR), sd: "R", rs: -1}), penShift: sh};
      H.L = {local: loc(nibW), pose: poseL}; lastNibW = nibW;
    }
    else if (t < 4.625) { const k = sstep(3.0, 3.2, t); H.L = {local: lerp2(loc(lastNibW), chestL, k), pose: poseL}; }
    else if (t < 6.875) { const k = sstep(4.8, 5.3, t), tr = t > 5.3 ? .004 * Math.sin(t * 47) : 0; H.L = {local: lerp2(chestL, add2(loc([.02, .25, 2.40]), [tr, 0]), k), pose: poseL}; }
    else { const k = sstep(6.95, 7.45, t); H.L = {local: lerp2(loc([.02, .25, 2.40]), loc([.13, .36, 2.42]), k), pose: poseL}; }
    const press = loc(cardW(PRESS[0], PRESS[1], t < 3.0 ? cs : cardState(2.99)));
    if (t < 3.0) H.R = {local: press, pose: poseR};
    else if (t < 4.625) H.R = {local: lerp2(press, chestR, sstep(3.0, 3.2, t)), pose: poseR};
    else if (t < 6.875) H.R = {local: lerp2(chestR, loc([-.30, YC - .002, 2.44]), sstep(4.8, 5.1, t)), pose: poseR};
    else { const k1 = EASE.io(clamp((t - 6.9) / .475, 0, 1)), k2 = sstep(7.4, 8.0, t), lifted = [-.31, .36, 2.38];   // the 0.10 m string keeps the lift near the handle
      const ant = t < 7.0 ? -.06 * Math.sin(Math.PI * clamp((t - 6.875) / .125, 0, 1)) : 0;
      if (t < 7.375) { graspLoc = loc(tagGripHanging(s)); H.R = {local: add2(lerp2(loc([-.30, YC - .02, 2.44]), graspLoc, k1), [0, ant]), pose: poseR}; }
      else H.R = {local: lerp2(graspLoc, loc(lifted), k2), pose: poseR}; }
    s.hands = H; s.face = {au: {}, eyeX: 0, eyeY: 0, blink: 0, iris: 1};
    const R = CHAR.solve(s, R0);
    s.tagHeld = t >= 7.375; s.R0 = R0; s.R = R;
    s.pinchW = s.tagHeld ? fromLocal(R0, R.arm.R.contact, 2.38) : null;
    s.tagC = s.tagHeld ? s.pinchW : (s.bag ? tagCentreHanging(s) : [-.225, .345, 2.38]);
    /* gaze, head, eyes (eyes lead; the head follows 75 % with a 2-frame delay) */
    const hc = [ROOT.X + R.HC[0] * HUM, ROOT.Y + R.HC[1] * HUM, Z_S];
    const G = t < 2.42 ? nibW : t < 2.62 ? [CHUTE.X, CHUTE.yMouth, CHUTE.Z] : t < 3.0 ? (s.bag ? [s.bag.X, s.bag.Y - .1, s.bag.Z] : [CHUTE.X, CHUTE.yMouth, CHUTE.Z]) : t < 4.625 ? [BAG.X, YC - .12, BAG.Z] : t < 8.3 ? s.tagC : t < 8.75 ? [CHUTE.X, CHUTE.yMouth, CHUTE.Z] : s.tagC;
    const d = [G[0] - hc[0], G[1] - hc[1], G[2] - hc[2]];
    let gy = deg(Math.atan2(d[0], -d[2] + .35)), gp = deg(Math.atan2(d[1], Math.hypot(d[0], d[2] - .35)));
    for (const [dt, dy, dp, n] of DARTS) { const df = f - Math.round(dt * FPS); if (df >= 0 && df < n) { gy += dy; gp += dp; } }
    s.gazeRaw = [gy, gp]; s.G = G; SM.push(s);
  }
  for (let f = 0; f <= NF; f++) {
    const s = SM[f], src = SM[Math.max(0, f - 2)], t = s.t;
    const want = clamp(src.gazeRaw[0] * .75, -40, 40);
    for (let q = 0; q < 4; q++) { const a = 22 * 22 * (want - neckRot) - 2 * 22 * neckRotV; neckRotV += a / (FPS * 4); neckRot += neckRotV / (FPS * 4); }
    const wantP = clamp((src.gazeRaw[1] - TR.neckFlex(t)) * .45, -12, 18);
    for (let q = 0; q < 4; q++) { const a = 18 * 18 * (wantP - neckFl) - 2 * 18 * neckFlV; neckFlV += a / (FPS * 4); neckFl += neckFlV / (FPS * 4); }
    s.neck = {rot: neckRot, flex: clamp(TR.neckFlex(t) + neckFl, -40, 42), tilt: TR.neckTilt(t)};
    s.headYaw = neckRot; s.faceYaw = clamp(neckRot / 42, -1, 1); s.faceNod = (s.neck.flex + s.flex * .3) / 90 * .13;
    const prevE = f ? SM[f - 1].eyeDir : s.gazeRaw, jump = Math.hypot(s.gazeRaw[0] - prevE[0], s.gazeRaw[1] - prevE[1]) > 6;
    s.eyeDir = jump ? [lerp(prevE[0], s.gazeRaw[0], .6), lerp(prevE[1], s.gazeRaw[1], .6)] : s.gazeRaw;
    const blinkV = (() => { for (const [b0, k] of BLINKS) { const dd = f - b0, sh = BLINK_SHAPE[k]; if (dd >= 0 && dd < sh.length) return sh[dd]; } return 0; })();
    s.face = {eyeX: clamp((s.eyeDir[0] - s.headYaw) / 35, -1, 1), eyeY: clamp((s.eyeDir[1] - s.neck.flex) / 30, -1, 1), blink: blinkV, iris: IRIS(t), au: {}};
    for (const k in AU) s.face.au[k] = AU[k](t); s.face.au["12_asym"] = AU12ASYM(t);
    s.viseme = visemeAt(t);
    s.tagLife = t >= 4.625 && t < 6.875 ? .12 : t >= 3.0 && t < 4.625 ? 1.4 : 1;
  }
  /* secondary: drape and scarf-end lag the chest; coat tags are pendulums driven by their anchors */
  const chestRef = f => { const s = SM[f]; return solveChestOnly(s, [0, -1.8]); };
  const anchors = f => [[.55, -1.82], [-.6, -1.62], [.45, -1.08], [-.5, -1.0]].map(p => solveChestOnly(SM[f], p));
  for (let f = 0; f <= NF; f++) {
    const s = SM[f], t = s.t, g = gust(t) * s.tagLife;
    const lagV = (n, k) => { const a = chestRef(Math.max(0, f - n)), b = chestRef(f); return [clamp((a[0] - b[0]) * k, -.15, .15), clamp((a[1] - b[1]) * k, -.15, .15)]; };
    s.drapeLag = add2(lagV(3, .8), [.02 * Math.sin(t * 2.3) * g, 0]);
    s.endLag = add2(lagV(4, 1.2), [.04 * Math.sin(t * 2.0 + .7) * g, .01 * Math.sin(t * 3.1)]);
    const an = anchors(f);
    for (let i = 0; i < 4; i++) { let acc = 0; if (f >= 2) acc = (an[i][0] - 2 * prevA[i][0] + prev2[i][0]) * HUM * FPS * FPS;
      const Lm = .045, damp = s.tagLife < .5 ? 9 : 2.2, wind = .9 * g * Math.sin(t * (2.1 + i * .37) + i * 1.7) * (s.tagLife > .5 ? 1 : 0);
      for (let q = 0; q < 4; q++) { const a = -(9.8 / Lm) * Math.sin(tagAng[i]) - damp * tagVel[i] - acc * Math.cos(tagAng[i]) / Lm * .35 + wind; tagVel[i] += a / (FPS * 4); tagAng[i] += tagVel[i] / (FPS * 4); }
      tagAng[i] = clamp(tagAng[i], -1.1, 1.1); }
    for (let i = 0; i < 4; i++) { prev2[i] = prevA[i] || an[i]; prevA[i] = an[i]; }
    s.tags = tagAng.slice();
  }
  return SM;
}
function solveChestOnly(s, p) { const cf = Math.cos(rad(s.flex)), rel = [p[0], (p[1] - WAIST[1]) * cf]; return add2(WAIST, rot2(rel, rad(s.tilt))); }
const V3lerp = (a, b, k) => [lerp(a[0], b[0], k), lerp(a[1], b[1], k), lerp(a[2], b[2], k)];
function fromLocal(R0, q, Z) { const x = R0.x + q[0] * R0.k, y = R0.y + q[1] * R0.k, d = Z - C.z, s = C.F / d; return [C.x + (x - W / 2) / s, C.y + (y - H / 2) / s, Z]; }
/* hanging bag tag: the string from the knot to the hole (top centre), the tag below it */
function tagHang(s) { const kn = s.knot, a = s.btAng, hole = [kn[0] + Math.sin(a) * STRING, kn[1] + Math.cos(a) * STRING, kn[2] - .02]; return {hole, ang: -a * .7}; }
function tagCentreHanging(s) { const h = tagHang(s), c = Math.cos(h.ang), sn = Math.sin(h.ang), q = [0, TAGH / 2 - .012]; return [h.hole[0] + q[0] * c - q[1] * sn, h.hole[1] + q[0] * sn + q[1] * c, h.hole[2]]; }
function tagGripHanging(s) { const h = tagHang(s), c = Math.cos(h.ang), sn = Math.sin(h.ang), g = GRIPS["pinch-tag-R"].tag_grip_m, q = [-TAGW / 2 + g[0], -.012 + g[1]]; return [h.hole[0] + q[0] * c - q[1] * sn, h.hole[1] + q[0] * sn + q[1] * c, h.hole[2]]; }
function tagCornerHanging(s) { const h = tagHang(s), c = Math.cos(h.ang), sn = Math.sin(h.ang), q = [-TAGW / 2, -.012]; return [h.hole[0] + q[0] * c - q[1] * sn, h.hole[1] + q[0] * sn + q[1] * c, h.hole[2]]; }
/* bag tag frame on screen: corner o (top-left), axes ex (width), ey (height), in world */
function bagTagFrame(s, R) {
  if (!s.bag) return null;
  if (s.tagHeld && R) { const p = fromLocal(s.R0Now || s.R0, R.arm.R.contact, 2.38), a = -.18 + .1 * Math.sin(s.t * 3) * (1 - sstep(7.4, 8, s.t)), g = GRIPS["pinch-tag-R"].tag_grip_m, c = Math.cos(a), sn = Math.sin(a);
    return {o: [p[0] - (g[0] * c - g[1] * sn), p[1] - (g[0] * sn + g[1] * c), p[2]], ang: a, grip: p}; }
  const h = tagHang(s), c = Math.cos(h.ang), sn = Math.sin(h.ang), q = [-TAGW / 2, -.012]; return {o: [h.hole[0] + q[0] * c - q[1] * sn, h.hole[1] + q[0] * sn + q[1] * c, h.hole[2]], ang: h.ang};
}
/* ---------- style per frame (A, B, A+B; impact cover, carrier-bleed, contour-wipe) ---------- */
function styleFor(f, L) {
  const st = {room: 0, bag: 0, mis: 0, misBag: 0, tagLife: SIM[f].tagLife, front: null, wipe: null};
  if (f >= 72 && f <= 110) { st.room = 1; st.bag = 1; st.mis = 1; st.misBag = 1; }
  if (f >= 111 && f < 173) { st.bag = 1; st.misBag = .8; }
  if (f >= 111 && f <= 120) { st.room = 1; st.mis = 1 - (f - 111) / 10; const k = EASE.out((f - 110) / 10); st.front = {x: 0, y: 0, R: 80 + k * 2600, seed: f * .3}; }
  if (f >= 165 && f <= 172) st.wipe = true;
  return st;
}
/* ---------- render one frame ---------- */
let LAST = null;
function renderFrame(f, opt = {}) {
  const t = f / FPS, s = SIM[f], sS = SIM[MAP.hero[f]], sB = SIM[MAP.bag[f]]; LAST_T = t;
  C = frameCam(f); setLights(f); ST = styleFor(f);
  ORDER = []; MODE = "color";
  ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = 1; ctx.globalCompositeOperation = "source-over";
  ctx.fillStyle = "#07080d"; ctx.fillRect(0, 0, W, H);
  if (C.shot === "s2") return (LAST = renderInsert(f));
  if (C.shot === "s5") return (LAST = renderPov(f));
  ctx.translate(W / 2, H / 2); ctx.rotate(C.roll); ctx.translate(-W / 2, -H / 2);
  const R0 = rootScreen(), R = CHAR.solve(Object.assign({}, sS, {R0Now: R0}), R0);
  const bag = sB.bag, bagF = bagTagFrame(Object.assign({}, sB, {tagHeld: s.tagHeld, t}), s.tagHeld ? R : null);
  if (ST.front) { const q = P(s.tagC[0], s.tagC[1], s.tagC[2]); ST.front.x = q.x; ST.front.y = q.y; }
  /* back to front: set (with Hero's mass-proxy shadow on the back unit), chute, counter, Hero's body, counter props (jar, card), bag,
     arms and hands by their grips' layer lists (pen and bag tag in their declared slots), lamp, dust, fg */
  drawBackdrop(t, () => { const polys = proxyOnPlane(R, ZP); ctx.beginPath(); for (const p of polys) { p.forEach((q, i) => { const s2 = P(q[0], q[1], ZP); i ? ctx.lineTo(s2.x, s2.y) : ctx.moveTo(s2.x, s2.y); }); ctx.closePath(); } ctx.fillStyle = SHADOW_FILL(); ctx.fill("nonzero"); });
  drawChute(t);
  const casters = [{X: JAR.X, Y: YC, Z: JAR.Z, w: JAR.w, h: JAR.h}, {X: .55, Y: YC, Z: 2.42, w: .32, h: .04}, {X: .86, Y: YC, Z: 2.36, w: .08, h: .09}];
  if (bag && bag.Y > YC - .05) casters.push({X: bag.X, Y: bag.Y, Z: bag.Z, w: .3, h: .2});
  drawCounter(t, casters);
  const cut = P(0, YC, ZCB), cutY = (cut.y - R0.y) / R0.k;
  CHAR.drawBody(R, cutY);
  { const a = P(-1.2, YC, ZCB), b = P(1.2, YC, ZCB); line2(a.x, a.y, b.x, b.y, 3, INKC); }   // the counter's back edge occludes her waist
  drawCoatTags(R, sS);
  drawCounterProps(t, s);
  if (bag) drawBag(bag, t, f);
  const extras = {pen: () => drawPen(R.arm.L)};
  if (bagF) extras["bag-tag"] = () => drawBagTag(bagF, bag, t, f, R, true);
  const angle = viewOf(sS);
  CHAR.drawArms(R, extras, {angle});
  drawLamp(t);
  drawDust(t, BAG.X);
  drawForeground(t);
  if (f === 72) impactFrame(bag);
  if (f === 75) smearFrame();
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  LAST = {f, R, cam: C, bagF, bag, order: ORDER.slice(), sS, cutY, view: "ms", angle};
  return LAST;
}
const TEXT = {t0: 5.875, t1: 6.792};
function drawCoatTags(R, sS) {
  const k = R.R0.k; ctx.save(); ctx.translate(R.R0.x, R.R0.y); ctx.scale(k, k); S = k; mark("coat-tags");
  const li = bodyLight(R); [[.55, -1.82], [-.6, -1.62], [.45, -1.08], [-.5, -1.0]].forEach((p, i) => { const a = R.chest(p); if (a[1] > R.cutY - .25) return;
    ctx.save(); ctx.translate(a[0], a[1]); drawTag(0, 0, .22, (sS.tags || [])[i] || 0, .2, .13, li, {lw: 1.4}); ctx.restore(); });
  ctx.restore(); S = 1;
}
function drawCounterProps(t, s) {
  { const X = .55, Z = 2.42, li = lightAt(X, YC - .05, Z), jump = .03 * Math.max(0, ring(t, 3.03, 2.4, 5)); enter(X, YC - jump, Z);
    solid(() => { ctx.moveTo(-.18, 0); ctx.lineTo(.18, 0); ctx.lineTo(.16, -.035); ctx.lineTo(-.16, -.035); ctx.closePath(); }, [110, 40, 30], li, .2, {lw: 2.2});
    const pg = .25 + .15 * Math.sin(t * 2.7) * gust(t) * ST.tagLife + .8 * Math.max(0, ring(t, 3.04, 1.6, 2.5)); ctx.save(); ctx.translate(0, -.035); ctx.rotate(-pg * .6);
    solid(() => { ctx.moveTo(0, 0); ctx.quadraticCurveTo(.08, -.02, .16, -.005); ctx.lineTo(.16, .002); ctx.lineTo(0, .002); ctx.closePath(); }, [238, 226, 196], li, .15, {lw: 1.8, noRim: true}); ctx.restore(); leave(); }
  { const X = .86, Z = 2.36, li = lightAt(X, YC - .05, Z), sw = .25 * ring(t, 3.04, 3.2, 3); enter(X, YC, Z); ctx.rotate(sw);
    solid(() => { ctx.moveTo(-.045, 0); ctx.quadraticCurveTo(-.045, -.07, 0, -.075); ctx.quadraticCurveTo(.045, -.07, .045, 0); ctx.closePath(); ctx.rect(-.006, -.095, .012, .022); }, [214, 162, 60], li, .07, {lw: 2}); leave(); }
  { const X = -.62, Z = 2.36, li = lightAt(X, YC - .03, Z); enter(X, YC, Z); solid(() => { rrect(-.035, -.05, .07, .05, .01); ctx.rect(-.018, -.065, .036, .016); }, [30, 40, 70], li, .05, {lw: 2}); leave(); }
  { const li = lightAt(JAR.X, YC - .1, JAR.Z), hop = .03 * Math.max(0, ring(t, 3.03, 2.6, 5)); enter(JAR.X, YC - hop, JAR.Z); ctx.rotate(.1 * ring(t, 3.03, 3, 4));
    solid(() => { rrect(-.065, -.17, .13, .17, .03); ctx.rect(-.05, -.2, .1, .035); }, [70, 140, 130], li, .13, {lw: 2.6});
    line(-.04, -.15, -.04, -.04, 4, "#cfe8dc"); ctx.fillStyle = "#ffc85a"; for (let k = 0; k < 5; k++) { ctx.beginPath(); ctx.arc(-.02 + (k % 3) * .02, -.05 - (k * .023) % .08, .009, 0, 6.3); ctx.fill(); }
    leave(); }
  drawCardMS(t);
}
/* (v4's jar tag removed: the card she writes lies face up on the counter, write.js) */
let LAST_T = 0;
/* pen: rigid, from the grip (catalogue tripod-pen-L@3.0): nib on the paper, barrel in the web, drawn in the hand's layer slot */
function penGeom(A) { const pn = A.pose.pen, tip = A.map(pn.tip), rear = A.map(pn.rear), u = unit2(sub2(rear, tip)); return {tip, rear, u, r: pn.r}; }
function drawPen(A, li) { const g = penGeom(A), r = g.r; li = li || bodyLight();
  const barrel = () => capsule(g.tip[0] + g.u[0] * .065, g.tip[1] + g.u[1] * .065, g.rear[0], g.rear[1], r * .92, r * 1.12);
  cel(barrel, [29, 43, 74], li, .1, {noRim: true}); ctx.beginPath(); barrel(); ink(1.6);
  const cap = () => capsule(g.rear[0] - g.u[0] * .09, g.rear[1] - g.u[1] * .09, g.rear[0], g.rear[1], r * 1.14, r * 1.12);
  cel(cap, [176, 140, 64], li, .05, {noRim: true, flat: true}); ctx.beginPath(); cap(); ink(1.2);
  const nib = () => capsule(g.tip[0], g.tip[1], g.tip[0] + g.u[0] * .07, g.tip[1] + g.u[1] * .07, .005, r * .9);
  cel(nib, [214, 170, 70], li, .05, {noRim: true, flat: true}); ctx.beginPath(); nib(); ink(1.2);
  A.penG = g; }
/* the bag: soft leather, squashes on the slam; B treatment on threes in b3 */
function drawBag(b, t, f) {
  mark("bag");
  const li = lightAt(b.X, b.Y - .1, b.Z), mis = "bag"; enter(b.X, b.Y, b.Z); ctx.rotate(b.rot); ctx.scale(1 + b.sq * .7, 1 - b.sq);
  solid(() => { ctx.moveTo(-.12, -.18); ctx.quadraticCurveTo(-.02, -.33, .12, -.18); ctx.lineTo(.1, -.17); ctx.quadraticCurveTo(-.02, -.29, -.1, -.17); ctx.closePath(); }, [90, 40, 30], li, .15, {bag: true, lw: 2.4, mis});
  wipeClip(() => solid(() => rrect(-.16, -.19, .32, .19, .035), [122, 38, 34], li, .2, {bag: true, lw: 3, mis}));
  solid(() => { ctx.moveTo(-.16, -.17); ctx.lineTo(.16, -.17); ctx.lineTo(.13, -.08); ctx.quadraticCurveTo(0, -.05, -.13, -.08); ctx.closePath(); }, [98, 28, 28], li, .18, {bag: true, lw: 2.4, mis});
  if (ST.bag > .01) { ctx.save(); ctx.beginPath(); rrect(-.16, -.19, .32, .19, .035); ctx.clip(); ctx.globalAlpha = .45; ctx.fillStyle = patScaled(P_DOT, 1 / S); ctx.fillRect(-1, -1, 2, 2); ctx.restore(); }
  solid(() => rrect(-.025, -.1, .05, .04, .008), [222, 172, 70], li, .04, {half: 0, lw: 2});
  ctx.setLineDash([.012, .01]); line(-.14, -.03, .14, -.03, 1.6, "#e8c696"); line(-.15, -.165, .15, -.165, 1.6, "#e8c696"); line(-.15, -.165, -.15, -.02, 1.6, "#e8c696"); line(.15, -.165, .15, -.02, 1.6, "#e8c696"); ctx.setLineDash([]);
  leave();
}
/* contour-wipe (b3 -> b4): the bag's halftone clears behind her right sleeve's edge as it sweeps in */
function wipeClip(fn) { fn(); }
function bagTagRegion(F, R) { const q = tagCorners(F).map(v => toLocal(R.R0, v[0], v[1], v[2])); ctx.beginPath(); q.forEach((v, i) => i ? ctx.lineTo(v[0], v[1]) : ctx.moveTo(v[0], v[1])); ctx.closePath(); }
function tagCorners(F) { const c = Math.cos(F.ang), s = Math.sin(F.ang), m = (x, y) => [F.o[0] + x * c - y * s, F.o[1] + x * s + y * c, F.o[2]];
  return [m(0, 0), m(TAGW, 0), m(TAGW, TAGH), m(0, TAGH)]; }
function drawBagTag(F, bag, t, f, R, held) {
  const cs = tagCorners(F), hole = (() => { const c = Math.cos(F.ang), s = Math.sin(F.ang); return [F.o[0] + TAGW / 2 * c - .012 * s, F.o[1] + TAGW / 2 * s + .012 * c, F.o[2]]; })();
  const kn = bagKnot(bag), a = P(kn[0], kn[1], kn[2]), b = P(hole[0], hole[1], hole[2]), slack = Math.max(0, STRING - Math.hypot(hole[0] - kn[0], hole[1] - kn[1]));
  mark("tag-string"); const keepT = ctx.getTransform(); if (held) { ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.translate(W / 2, H / 2); ctx.rotate(C.roll); ctx.translate(-W / 2, -H / 2); }
  ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.quadraticCurveTo((a.x + b.x) / 2, Math.max(a.y, b.y) + slack * b.s * 1.2, b.x, b.y); ctx.lineWidth = Math.max(1.5, .002 * b.s); ctx.strokeStyle = "#e9dcc0"; ctx.stroke();
  const p = cs.map(v => P(v[0], v[1], v[2])), li = lightAt(F.o[0], F.o[1], F.o[2] - .05), glow = GLOW.pow; S = 1;
  const col = glow > .05 ? [205, 245, 255] : [238, 226, 196];
  solid(() => { ctx.moveTo(p[0].x, p[0].y); p.forEach(v => ctx.lineTo(v.x, v.y)); ctx.closePath(); }, col, li, .05 * b.s, {bag: true, mis: "bag", lw: 2.2, noRim: true, k: 1 + glow * .4});
  ctx.beginPath(); ctx.arc(b.x, b.y, Math.max(2, .005 * b.s), 0, 6.3); ctx.fillStyle = "#3a2c22"; ctx.fill();
  // R-387: the front (her name, the date) faces her; a front-view camera sees the BACK: only the printed intake stamp is drawn
  const m = (x, y) => { const c = Math.cos(F.ang), s = Math.sin(F.ang), w = [F.o[0] + x * c - y * s, F.o[1] + x * s + y * c, F.o[2]]; return P(w[0], w[1], w[2]); };
  if (bagTagFacing("ms") === "back") drawStamp(m, b.s);
  if (held) ctx.setTransform(keepT);
}
function bagTagFacing(view) { return view === "pov" ? "front" : "back"; }
function drawStamp(m, sc) {   // printed on the back: an intake ring with two bars, flat purple ink
  const c = m(.118, .07), r = .024 * sc; ctx.save(); ctx.globalAlpha = .75; ctx.strokeStyle = "#4e3a78"; ctx.lineWidth = Math.max(1.2, .0022 * sc);
  ctx.beginPath(); ctx.arc(c.x, c.y, r, 0, 6.3); ctx.stroke(); ctx.beginPath(); ctx.arc(c.x, c.y, r * .72, 0, 6.3); ctx.stroke();
  for (const [y, x0, x1] of [[.05, .022, .078], [.066, .022, .07], [.082, .022, .062]]) { const a = m(x0, y), b2 = m(x1, y); ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b2.x, b2.y); ctx.stroke(); }
  ctx.restore(); }
/* F4: the name on a flat opaque plate, drawn after every effect (no dots, no glow, no dust over it) */
function drawTextPlate(F, f) {
  const c = Math.cos(F.ang), s = Math.sin(F.ang), m = (x, y) => { const w = [F.o[0] + x * c - y * s, F.o[1] + x * s + y * c, F.o[2]]; return P(w[0], w[1], w[2]); };
  const p = [m(.004, .008), m(TAGW - .004, .008), m(TAGW - .004, TAGH - .004), m(.004, TAGH - .004)];
  ctx.beginPath(); ctx.moveTo(p[0].x, p[0].y); p.forEach(v => ctx.lineTo(v.x, v.y)); ctx.closePath(); ctx.fillStyle = "#e4f6fb"; ctx.fill();
  { const h = m(TAGW / 2, .012); ctx.beginPath(); ctx.arc(h.x, h.y, Math.max(2, .005 * h.s), 0, 6.3); ctx.fillStyle = "#3a2c22"; ctx.fill(); }
  const box = textBoxes(F);
  ctx.save(); const o = m(TAGW / 2, 0); ctx.translate(o.x, o.y); ctx.rotate(F.ang); ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.direction = "rtl"; ctx.fillStyle = "#14100c";
  const k = o.s; ctx.font = `700 ${(.036 * k).toFixed(1)}px thmanyahseriftext`; ctx.fillText("هدى", 0, .06 * k);
  ctx.font = `700 ${(.0165 * k).toFixed(1)}px thmanyahsans`; ctx.fillStyle = "#3a0a06"; ctx.fillText("الخميس القادم", 0, .097 * k); ctx.restore();
  return box;
}
function textBoxes(F) { const c = Math.cos(F.ang), s = Math.sin(F.ang), m = (x, y) => { const w = [F.o[0] + x * c - y * s, F.o[1] + x * s + y * c, F.o[2]]; return P(w[0], w[1], w[2]); };
  const bb = (x0, y0, x1, y1) => { const q = [m(x0, y0), m(x1, y0), m(x1, y1), m(x0, y1)], xs = q.map(v => v.x), ys = q.map(v => v.y); return {x: Math.round(Math.min(...xs)), y: Math.round(Math.min(...ys)), w: Math.round(Math.max(...xs) - Math.min(...xs)), h: Math.round(Math.max(...ys) - Math.min(...ys))}; };
  return {name: bb(TAGW / 2 - .036, .038, TAGW / 2 + .036, .08), date: bb(TAGW / 2 - .054, .088, TAGW / 2 + .054, .106)}; }
/* impact cover (f72): ink frame, white burst; f75: drawn speed lines (no blur) */
function impactFrame(bag) {
  ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.fillStyle = "#0b0706"; ctx.fillRect(0, 0, W, H);
  const c = P(BAG.X, YC - .1, BAG.Z), R = rng(721);
  for (let i = 0; i < 34; i++) { const a = R() * 6.283, r0 = 140 + R() * 120, r1 = r0 + 300 + R() * 600; ctx.beginPath(); ctx.moveTo(c.x + Math.cos(a) * r0, c.y + Math.sin(a) * r0); ctx.lineTo(c.x + Math.cos(a + .03) * r1, c.y + Math.sin(a + .03) * r1); ctx.lineTo(c.x + Math.cos(a - .03) * r1, c.y + Math.sin(a - .03) * r1); ctx.closePath(); ctx.fillStyle = "#fff4e6"; ctx.fill(); }
  enter(BAG.X, YC, BAG.Z); ctx.beginPath(); rrect(-.17, -.2, .34, .2, .035); ctx.fillStyle = "#fff4e6"; ctx.fill(); leave();
  ctx.save(); ctx.globalAlpha = .9; ctx.fillStyle = patScaled(P_DOT, 1.6); ctx.beginPath(); ctx.arc(c.x, c.y, 360, 0, 6.3); ctx.fill(); ctx.restore();
}
function smearFrame() { ctx.setTransform(1, 0, 0, 1, 0, 0); const R = rng(751); for (let i = 0; i < 40; i++) { const x = R() * W, y = R() * H * .8, l = 120 + R() * 380; ctx.fillStyle = i % 3 ? "rgba(255,240,220,.55)" : "rgba(10,6,4,.6)"; ctx.fillRect(x, y, 5 + R() * 8, l); } }
