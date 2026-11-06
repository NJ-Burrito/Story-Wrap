/* ===== Smoke shot: Partner alone, 2 s, through the multi-actor engine (actors.js, trace-multi.js, bootstrap-multi.js) =====
   Scene contract (tools/render/trace-multi.js): PLAN, SIM, buildSim, renderFrame(f) -> L, LAST; optional traceExtra(id, rec, q, L).
   renderFrame is a pure function of the frame number. Back to front: set, chute, counter, Partner (body, then arms by their grips' layer lists), lamp, dust, foreground. */
let PLAN = null, SIM = null, LAST = null;
function shotAt(t) { return PLAN.shots.find(s => t >= s.t0 - 1e-6 && t < s.t1 - 1e-6) || PLAN.shots[PLAN.shots.length - 1]; }
function frameCam(f) {
  const t = f / FPS, sh = shotAt(t), k = clamp((t - sh.t0) / (sh.t1 - sh.t0), 0, 1), e = sh.move === "track" || sh.move === "drift" ? k : EASE.sine(k), a = sh.cam0, b = sh.cam1;
  return {x: lerp(a.x, b.x, e), y: lerp(a.y, b.y, e), z: lerp(a.z, b.z, e), F: lerp(a.F, b.F, e), roll: 0, shot: sh.shot};
}
/* light: one beat, flat colours, the key lamp swings on its chain */
function setLights(f) {
  const t = f / FPS, th = .085 * Math.sin(6.283 * .42 * t + .4) + .03 * noise(t * .8, 3);
  const px = -.42, py = -2.65, pz = 2.12, L = 2.4, fl = 1 + .06 * noise(t * 9, 1);
  KEY = {x: px + L * Math.sin(th), y: py + L * Math.cos(th), z: pz + .04 * Math.sin(6.283 * .31 * t), pow: KPOW(t) * fl, fall: .9, c: [1, .72, .42], th, px, pz};
  AL1 = {x: .02 * Math.sin(t * 1.3), y: -1.25, z: 5.0, pow: .55, fall: 2.0, c: [1, .7, .4]};
  AL2 = {x: -.02 * Math.sin(t * 1.1), y: -1.1, z: 6.8, pow: .5, fall: 2.2, c: [1, .66, .38]};
  GLOW = {x: 0, y: .3, z: 2.3, pow: 0, fall: 6, c: [.35, .85, 1]};
  LIGHTS = [KEY, AL1, AL2, GLOW];
  AMB = [.09, .1, .17]; FILLC = [30, 40, 78]; RIM = {c: [255, 217, 154], k: .7};
}
const KPOW = KF([[0, 2.8], [.9, 3.4], [1.17, 3.6], [1.25, 4.6, "out"], [2, 3.2]]);   // the lamp catches the loaf at the peak
/* ---------- Partner's tracks (precomputed once, deterministic) ---------- */
const TRK = {
  flex: KF([[0, 6], [.9, 10], [1.5, 8], [2, 5]]), tilt: KF([[0, 2], [1, -2], [2, 1]]), shrug: KF([[0, 0], [.9, .06], [1.5, .03], [2, 0]]),
  neckFlex: KF([[0, 8], [.9, 14], [1.5, 12], [2, 6]]), neckTilt: KF([[0, 3], [1, -2], [2, 2]]),
  gx: KF([[0, -10], [.5, 6], [.9, 0], [1.5, 0], [2, -6]]), gp: KF([[0, 6], [.7, 18], [1.5, 12], [2, 4]]),
  flame: KF([[0, 1], [.5, 1.3], [1, .8], [1.5, 1.2], [2, 1]]),
};
const AU = {   // the grin lands at 1.17 -> 1.25 s (peak_s 1.25): the biggest face change sits on the declared peak (R-374)
  "1": KF([[0, 0], [.6, .1], [1.17, .15], [1.25, .6, "out"], [2, .4]]), "2": KF([[0, 0], [1.17, .05], [1.25, .3, "out"], [2, .15]]), "4": KF([[0, .3], [.7, 0], [2, 0]]), "5": KF([[0, 0], [1.17, .05], [1.25, .3, "out"], [2, .1]]),
  "6": KF([[0, 0], [1.17, .1], [1.25, .6, "out"], [2, .5]]), "7": KF([[0, .2], [1.0, 0], [2, .1]]), "9": KF([[0, 0], [2, 0]]), "12": KF([[0, 0], [1.17, .15], [1.25, .85, "out"], [2, .65]]),
  "15": KF([[0, .2], [.7, 0], [2, 0]]), "20": KF([[0, 0], [2, 0]]), "23": KF([[0, .15], [.8, 0], [2, 0]]), "26": KF([[0, .05], [1.17, .1], [1.25, .55, "out"], [2, .35]]),
};
const BLINKS = [[20, 0]], BLINK_SHAPE = [[.6, 1, .7, .25]];
const DARTS = [[.35, 4, -3, 3], [.9, -5, 3, 3], [1.45, 4, 2, 3]];
const IRISK = KF([[0, 1], [1.0, .9], [2, 1]]);
/* hands: local targets in body HU (origin pelvis, y down); L offers the loaf (give-open-L), R rests its heel on the wall, then blends to hook-ledge-R (R-386) */
const L_POS = KV([[0, [1.35, -.75]], [.9, [1.9, -1.1], "io"], [1.5, [1.9, -1.2], "io"], [2, [1.75, -1.0], "io"]]);
const R_POS = KV([[0, [-1.9, -1.35]], [.9, [-1.9, -1.4], "io"], [1.4, [-1.8, -1.05], "io"], [2, [-1.8, -1.07]]]);
function rPose(f) {   // eight in-between frames, k rising 1/9..8/9, then the new grip (the reported id stays the FROM grip's until k = 1)
  const a = actorGrip("partner", "wall-flat-R"), b = actorGrip("partner", "hook-ledge-R"), f0 = 26, n = 8;
  if (f < f0) return a;
  if (f <= f0 + n) return blendPose(a, b, (f - f0) / (n + 1));
  return b;
}
function buildSim() {
  const SM = [], poseL = actorGrip("partner", "give-open-L");
  let neckRot = 0, neckRotV = 0, neckFl = 0, neckFlV = 0;
  for (let f = 0; f <= NF; f++) {
    const t = f / FPS, s = {f, t};
    s.flex = TRK.flex(t); s.tilt = TRK.tilt(t); s.twist = 0; s.shrug = TRK.shrug(t); s.headTilt = TRK.neckTilt(t); s.flame = TRK.flame(t);
    s.hands = {L: {local: L_POS(t), pose: poseL, contact: "bread-offer-L"}, R: {local: R_POS(t), pose: rPose(f), contact: "right-hand-reach"}};
    let gy = TRK.gx(t), gp = TRK.gp(t);
    for (const [dt, dy, dp, n] of DARTS) { const df = f - Math.round(dt * FPS); if (df >= 0 && df < n) { gy += dy; gp += dp; } }
    s.gazeRaw = [gy, gp]; SM.push(s);
  }
  for (let f = 0; f <= NF; f++) {   // eyes lead; the head follows 75 % with a 2-frame delay through a critically damped spring
    const s = SM[f], src = SM[Math.max(0, f - 2)], t = s.t;
    const want = clamp(src.gazeRaw[0] * .75, -40, 40);
    for (let q = 0; q < 4; q++) { const a = 22 * 22 * (want - neckRot) - 2 * 22 * neckRotV; neckRotV += a / (FPS * 4); neckRot += neckRotV / (FPS * 4); }
    const wantP = clamp((src.gazeRaw[1] - TRK.neckFlex(t)) * .45, -12, 18);
    for (let q = 0; q < 4; q++) { const a = 18 * 18 * (wantP - neckFl) - 2 * 18 * neckFlV; neckFlV += a / (FPS * 4); neckFl += neckFlV / (FPS * 4); }
    s.neck = {rot: neckRot, flex: clamp(TRK.neckFlex(t) + neckFl, -40, 42), tilt: TRK.neckTilt(t)};
    s.headYaw = neckRot; s.faceYaw = clamp(neckRot / 42, -1, 1); s.faceNod = (s.neck.flex + s.flex * .3) / 90 * .13;
    const prevE = f ? SM[f - 1].eyeDir : s.gazeRaw, jump = Math.hypot(s.gazeRaw[0] - prevE[0], s.gazeRaw[1] - prevE[1]) > 6;
    s.eyeDir = jump ? [lerp(prevE[0], s.gazeRaw[0], .6), lerp(prevE[1], s.gazeRaw[1], .6)] : s.gazeRaw;
    const blinkV = (() => { for (const [b0, k] of BLINKS) { const dd = f - b0, sh = BLINK_SHAPE[k]; if (dd >= 0 && dd < sh.length) return sh[dd]; } return 0; })();
    s.face = {eyeX: clamp((s.eyeDir[0] - s.headYaw) / 35, -1, 1), eyeY: clamp((s.eyeDir[1] - s.neck.flex) / 30, -1, 1), blink: blinkV, iris: IRISK(t), au: {}};
    for (const k in AU) s.face.au[k] = AU[k](t);
    s.gazeTarget = t < .9 ? "bread" : "person";
    s.clothLag = [.02 * Math.sin(t * 2.3), .01 * Math.sin(t * 3.1)];
  }
  return SM;
}
/* where an actor stands on screen this frame (the module's root and depth, through the flat camera) */
function rootOf(id) { const m = ACTORS[id].mod, p = P(m.root.X, m.root.Y, ACTORS[id].z); return {x: p.x, y: p.y, k: p.s * m.hu_m}; }
function drawBread(R, li) {   // a loaf on the palm, drawn in the arm space (HU) by the grip's "bread" slot
  const A = R.arm.L, c = A.map([.26, -.02]), ang = A.ah;
  solid(() => { ctx.ellipse(c[0], c[1], .34, .17, ang, 0, 6.2832); }, [196, 132, 62], li, .15, {lw: 2.2});
  ctx.save(); ctx.beginPath(); ctx.ellipse(c[0], c[1], .34, .17, ang, 0, 6.2832); ctx.clip();
  for (const o of [-.16, 0, .16]) { const a = A.map([.26 + o, -.02]); line(a[0] - .05, a[1] - .1, a[0] + .04, a[1] + .1, 2.2, "#7a4a22"); }
  ctx.restore();
}
function renderFrame(f) {
  const t = f / FPS, s = SIM[f]; C = frameCam(f); setLights(f); ST = {room: 0, bag: 0, mis: 0, misBag: 0, tagLife: 1, front: null, wipe: null};
  MODE = "color"; resetLayerOrders();
  ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = 1; ctx.globalCompositeOperation = "source-over";
  ctx.fillStyle = "#07080d"; ctx.fillRect(0, 0, W, H);
  ctx.translate(W / 2, H / 2); ctx.rotate(C.roll); ctx.translate(-W / 2, -H / 2);
  const R0 = rootOf("partner"), R = actorSolve("partner", s, R0), angle = "front";
  const cut = P(0, YC, ZCB), cutY = (cut.y - R0.y) / R0.k;
  const li = withActor("partner", () => lightAt(CHAR.root.X, CHAR.root.Y - 2 * HUM, CHAR.z));
  const per = {partner: {R, s, angle, view: "front", cutY, extras: {bread: () => drawBread(R, li)}, gaze: s.gazeTarget}};
  drawBackdrop(t, () => { ctx.beginPath(); for (const id of ACTOR_IDS) withActor(id, () => { for (const p of CHAR.massProxyOnPlane(per[id].R, ZP)) { p.forEach((q, i) => { const s2 = P(q[0], q[1], ZP); i ? ctx.lineTo(s2.x, s2.y) : ctx.moveTo(s2.x, s2.y); }); ctx.closePath(); } }); ctx.fillStyle = SHADOW_FILL(); ctx.fill("nonzero"); });
  drawChute(t);
  drawCounter(t, [{X: .3, Y: YC, Z: 2.3, w: .13, h: .17}]);
  const calls = drawActors(orderAt(f), per, tk => { if (tk === "partner:body") { const a = P(-1.2, YC, ZCB), b = P(1.2, YC, ZCB); line2(a.x, a.y, b.x, b.y, 3, INKC); } });   // the counter's back edge occludes his waist
  drawLamp(t);
  drawDust(t, -.12);
  drawForeground(t);
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  return (LAST = {f, cam: C, view: "ms", actors: per, draw_calls: calls, props: [], layers: ACTORS.partner.mod.layerOrder.get().slice()});
}
/* the anchors the spec's attachments name (screen px): the module's own head, lamp, knot and palm points, through its root */
function traceExtra(id, rec, q, L) {
  const R = q.R, R0 = R.R0, A = R.arm.L, sc = p => toScr(R0, p);
  rec.anchors.helmet_crown = sc(R.crown); rec.contact_points.helmet_band = sc(R.crown);
  rec.anchors.lamp_mount = sc(R.lamp); rec.contact_points.lamp_hook = sc(R.lamp);
  rec.anchors.knot_L = sc(R.knot); rec.contact_points.knot_tie = sc(R.knot);
  rec.anchors.bread_rest_L = sc(A.contact); rec.contact_points.bread_grip = sc(A.contact);
  if (rec.seams) { rec.overlaps = ["wrist_L", "wrist_R"]; rec.overlap_why = {wrist_L: "the reknitted cuff lies over the wrist (partner.js cuff(): its ink arc is the designed overlap)", wrist_R: "the reknitted cuff lies over the wrist (partner.js cuff(): its ink arc is the designed overlap)"}; }
}
