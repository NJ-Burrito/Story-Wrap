/* ===== SvgCtx: a minimal SVG recorder with the canvas 2D API subset the renderer uses (face, hands, character sheets). Moved out of face.js so the shot pages need not load it ===== */
/* minimal SVG recorder with the canvas API subset the face uses (catalogue sheets are drawn by the same code) */
class SvgCtx {
  constructor() { this.out = []; this.m = [1, 0, 0, 1, 0, 0]; this.stack = []; this.d = ""; this.fillStyle = "#000"; this.strokeStyle = "#000"; this.lineWidth = 1; this.lineCap = "round"; this.lineJoin = "round"; this.clips = []; this.nclip = 0; this.globalCompositeOperation = "source-over"; this.dash = []; this.globalAlpha = 1; }
  T(x, y) { const m = this.m; return [m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]]; }
  get sc() { return Math.hypot(this.m[0], this.m[1]); }
  f(v) { return (+v).toFixed(2); }
  save() { this.stack.push({m: this.m.slice(), c: this.clips.slice(), fs: this.fillStyle, ss: this.strokeStyle, lw: this.lineWidth, dash: this.dash, ga: this.globalAlpha}); }
  restore() { const s = this.stack.pop(); this.m = s.m; this.clips = s.c; this.fillStyle = s.fs; this.strokeStyle = s.ss; this.lineWidth = s.lw; this.dash = s.dash; this.globalAlpha = s.ga; }
  setLineDash(a) { this.dash = a.slice(); }
  fillRect(x, y, w, h) { this.beginPath(); this.rect(x, y, w, h); this.fill(); }
  strokeRect(x, y, w, h) { this.beginPath(); this.rect(x, y, w, h); this.stroke(); }
  roundRect(x, y, w, h, r) { r = Math.min(r, w / 2, h / 2); this.moveTo(x + r, y); this.lineTo(x + w - r, y); this.quadraticCurveTo(x + w, y, x + w, y + r); this.lineTo(x + w, y + h - r); this.quadraticCurveTo(x + w, y + h, x + w - r, y + h); this.lineTo(x + r, y + h); this.quadraticCurveTo(x, y + h, x, y + h - r); this.lineTo(x, y + r); this.quadraticCurveTo(x, y, x + r, y); this.closePath(); }
  translate(x, y) { const m = this.m; m[4] += m[0] * x + m[2] * y; m[5] += m[1] * x + m[3] * y; }
  scale(a, b) { const m = this.m; m[0] *= a; m[1] *= a; m[2] *= b; m[3] *= b; }
  rotate(r) { const c = Math.cos(r), s = Math.sin(r), m = this.m; const a = m[0], b = m[1], cc = m[2], d = m[3]; m[0] = a * c + cc * s; m[1] = b * c + d * s; m[2] = -a * s + cc * c; m[3] = -b * s + d * c; }
  beginPath() { this.d = ""; }
  moveTo(x, y) { const p = this.T(x, y); this.d += `M${this.f(p[0])} ${this.f(p[1])}`; }
  lineTo(x, y) { const p = this.T(x, y); this.d += `L${this.f(p[0])} ${this.f(p[1])}`; }
  quadraticCurveTo(a, b, x, y) { const c = this.T(a, b), p = this.T(x, y); this.d += `Q${this.f(c[0])} ${this.f(c[1])} ${this.f(p[0])} ${this.f(p[1])}`; }
  bezierCurveTo(a, b, c2, d2, x, y) { const c = this.T(a, b), e = this.T(c2, d2), p = this.T(x, y); this.d += `C${this.f(c[0])} ${this.f(c[1])} ${this.f(e[0])} ${this.f(e[1])} ${this.f(p[0])} ${this.f(p[1])}`; }
  closePath() { this.d += "Z"; }
  rect(x, y, w, h) { this.moveTo(x, y); this.lineTo(x + w, y); this.lineTo(x + w, y + h); this.lineTo(x, y + h); this.closePath(); }
  ellipse(x, y, rx, ry, rot, a0, a1) { const n = 28; for (let i = 0; i <= n; i++) { const a = a0 + (Math.min(a1, a0 + 6.2832) - a0) * i / n, px = x + Math.cos(rot) * rx * Math.cos(a) - Math.sin(rot) * ry * Math.sin(a), py = y + Math.sin(rot) * rx * Math.cos(a) + Math.cos(rot) * ry * Math.sin(a); i ? this.lineTo(px, py) : (this.d ? this.lineTo(px, py) : this.moveTo(px, py)); } }
  arc(x, y, r, a0, a1, ccw) { if (ccw) { const n = 16; for (let i = 0; i <= n; i++) { const a = a0 - (((a0 - a1) % 6.2832 + 6.2832) % 6.2832) * i / n; const px = x + r * Math.cos(a), py = y + r * Math.sin(a); this.d ? this.lineTo(px, py) : this.moveTo(px, py); } } else this.ellipse(x, y, r, r, 0, a0, a1); }
  _wrap(el) { let s = el; for (const id of this.clips.slice().reverse()) s = `<g clip-path="url(#${id})">${s}</g>`; this.out.push(s); }
  fill(rule) { if (this.globalCompositeOperation === "destination-out") return; this._wrap(`<path d="${this.d}" fill="${this.fillStyle}"${rule === "evenodd" ? ' fill-rule="evenodd"' : ""}/>`); }
  stroke() { this._wrap(`<path d="${this.d}" fill="none" stroke="${this.strokeStyle}" stroke-width="${this.f(this.lineWidth * this.sc)}" stroke-linecap="${this.lineCap}" stroke-linejoin="${this.lineJoin}"${this.dash.length ? ` stroke-dasharray="${this.dash.map(d => this.f(d * this.sc)).join(" ")}"` : ""}/>`); }
  clip(rule) { const id = "c" + (this.nclip++); this.out.push(`<clipPath id="${id}"><path d="${this.d}"${rule === "evenodd" ? ' clip-rule="evenodd"' : ""}/></clipPath>`); this.clips = this.clips.concat(id); }
  text(x, y, s, size, o = {}) { const p = this.T(x, y); this.out.push(`<text x="${this.f(p[0])}" y="${this.f(p[1])}" font-size="${size}" ${o.anchor ? `text-anchor="${o.anchor}"` : ""} font-family="${o.font || "thmanyahsans, sans-serif"}" fill="${o.fill || "#000"}"${o.weight ? ` font-weight="${o.weight}"` : ""}>${s}</text>`); }
}

/* ===== Ink: shared ink-stroke helpers for the catalogue sheets, so every module draws ink the same way (black, white and greys only).
   All take a canvas-like context g (SvgCtx or a 2D canvas) and points in whatever unit the caller's transform is in. Nothing here names a character.
     Ink.crs(pts, n, closed)            Catmull-Rom through the points
     Ink.rib(pts, w0, w1, wm)           outline of a tapered ribbon along a polyline (width w0 at the start, wm in the middle if given, w1 at the end)
     Ink.brush(g, pts, w0, w1, wm, o)   a tapered brush stroke, filled ink; o.fill overrides the colour (default #000)
     Ink.hatch(g, pts, angleDeg, gap, lw, o)       parallel hatching clipped to the closed polygon pts (o.smooth, o.k for a smoothed outline)
     Ink.crossHatch(g, pts, angleDeg, gap, lw, o)  two passes, the second at angle + o.cross (default 90) and o.gap2 (default gap)
     Ink.spotted(g, pts, o)             a spotted black: solid ink with a slightly broken edge (o.jitter in outline units, o.seed) and optional white nicks (o.nicks)
     Ink.clipPoly(sub, clip), Ink.area(p)   Sutherland-Hodgman against a convex clip polygon; signed area ===== */
const Ink = (() => {
  const area = p => { let a = 0; for (let i = 0; i < p.length; i++) { const q = p[i], r = p[(i + 1) % p.length]; a += q[0] * r[1] - r[0] * q[1]; } return a / 2; };
  function crs(P, n = 6, closed = false) {
    const m = P.length; if (m < 3) return P.map(p => p.slice()); const out = [], g = i => closed ? P[(i + m) % m] : P[Math.max(0, Math.min(m - 1, i))], segs = closed ? m : m - 1;
    for (let i = 0; i < segs; i++) { const p0 = g(i - 1), p1 = g(i), p2 = g(i + 1), p3 = g(i + 2);
      for (let j = 0; j < n; j++) { const t = j / n, t2 = t * t, t3 = t2 * t; out.push([0, 1].map(k => .5 * (2 * p1[k] + (-p0[k] + p2[k]) * t + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t2 + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * t3))); } }
    if (!closed) out.push(P[m - 1].slice()); return out;
  }
  function rib(P, w0, w1, wm, n = 5) {
    const Q = crs(P, n), N = Q.length, L = [], R = [];
    for (let i = 0; i < N; i++) { const a = Q[Math.max(0, i - 1)], b = Q[Math.min(N - 1, i + 1)], dx = b[0] - a[0], dy = b[1] - a[1], l = Math.hypot(dx, dy) || 1e-6, nx = -dy / l, ny = dx / l, t = N > 1 ? i / (N - 1) : 0;
      const w = (wm === undefined ? w0 + (w1 - w0) * t : t < .5 ? w0 + (wm - w0) * t * 2 : wm + (w1 - wm) * (t - .5) * 2) / 2; L.push([Q[i][0] + nx * w, Q[i][1] + ny * w]); R.push([Q[i][0] - nx * w, Q[i][1] - ny * w]); }
    return [...L, ...R.reverse()];
  }
  function polyPath(g, pts, closed = true) { g.beginPath(); pts.forEach((p, i) => i ? g.lineTo(p[0], p[1]) : g.moveTo(p[0], p[1])); if (closed) g.closePath(); }
  function brush(g, pts, w0, w1, wm, o = {}) { polyPath(g, rib(pts, w0, w1, wm, o.n || 5)); g.fillStyle = o.fill || "#000"; g.fill(); }
  function bbox(pts) { let x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9; for (const p of pts) { x0 = Math.min(x0, p[0]); x1 = Math.max(x1, p[0]); y0 = Math.min(y0, p[1]); y1 = Math.max(y1, p[1]); } return {x0, x1, y0, y1}; }
  function lines(g, pts, ang, gap, lw) {
    const b = bbox(pts), cx = (b.x0 + b.x1) / 2, cy = (b.y0 + b.y1) / 2, R = Math.hypot(b.x1 - b.x0, b.y1 - b.y0) / 2 + gap, a = ang * Math.PI / 180, ux = Math.cos(a), uy = Math.sin(a);
    g.beginPath(); for (let d = -R; d <= R; d += gap) { const px = cx - uy * d, py = cy + ux * d; g.moveTo(px - ux * R, py - uy * R); g.lineTo(px + ux * R, py + uy * R); }
    g.lineWidth = lw; g.strokeStyle = "#000"; g.stroke();
  }
  function outline(g, pts, o) { if (o && o.smooth && pts.length > 2) { const prev = typeof ctx === "undefined" ? undefined : ctx; ctx = g; g.beginPath(); smooth(pts, true, o.k || .5); ctx = prev; } else polyPath(g, pts, true); }
  function hatch(g, pts, ang, gap, lw, o = {}) { g.save(); outline(g, pts, o); g.clip(); lines(g, pts, ang, gap, lw); g.restore(); }
  function crossHatch(g, pts, ang, gap, lw, o = {}) { g.save(); outline(g, pts, o); g.clip(); lines(g, pts, ang, gap, lw); lines(g, pts, ang + (o.cross === undefined ? 90 : o.cross), o.gap2 || gap, o.lw2 || lw); g.restore(); }
  function spotted(g, pts, o = {}) {
    let s = (o.seed || 7) >>> 0; const rnd = () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
    const j = o.jitter === undefined ? 0 : o.jitter, P = j ? pts.map(p => [p[0] + (rnd() - .5) * j, p[1] + (rnd() - .5) * j]) : pts;
    outline(g, P, o); g.fillStyle = o.fill || "#111"; g.fill();
    if (o.nicks) { const b = bbox(P); g.save(); outline(g, P, o); g.clip(); g.fillStyle = "#fff";
      for (let i = 0; i < o.nicks; i++) { const x = b.x0 + rnd() * (b.x1 - b.x0), y = b.y0 + rnd() * (b.y1 - b.y0), r = (o.nick_r || (b.x1 - b.x0) * .012) * (.5 + rnd()); g.beginPath(); g.arc(x, y, r, 0, 6.2832); g.fill(); } g.restore(); }
  }
  function clipPoly(sub, clip) {
    let out = sub; const sg = Math.sign(area(clip)) || 1;
    for (let i = 0; i < clip.length && out.length; i++) { const A = clip[i], B = clip[(i + 1) % clip.length], inp = out; out = [];
      const ins = p => sg * ((B[0] - A[0]) * (p[1] - A[1]) - (B[1] - A[1]) * (p[0] - A[0])) >= 0;
      const X = (p, q) => { const a1 = B[1] - A[1], b1 = A[0] - B[0], c1 = a1 * A[0] + b1 * A[1], a2 = q[1] - p[1], b2 = p[0] - q[0], c2 = a2 * p[0] + b2 * p[1], d = a1 * b2 - a2 * b1 || 1e-9; return [(b2 * c1 - b1 * c2) / d, (a1 * c2 - a2 * c1) / d]; };
      for (let k = 0; k < inp.length; k++) { const cur = inp[k], prev = inp[(k + inp.length - 1) % inp.length];
        if (ins(cur)) { if (!ins(prev)) out.push(X(prev, cur)); out.push(cur); } else if (ins(prev)) out.push(X(prev, cur)); } }
    return out;
  }
  return {area, crs, rib, brush, hatch, crossHatch, spotted, clipPoly, polyPath, bbox};
})();
