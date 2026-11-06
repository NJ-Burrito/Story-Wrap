# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = ["numpy", "torch", "transformers", "pillow", "scipy"]
# [tool.uv.sources]
# torch = { index = "pytorch-cu126" }
# [[tool.uv.index]]
# name = "pytorch-cu126"
# url = "https://download.pytorch.org/whl/cu126"
# explicit = true
# ///
"""Story-Wrap quality gate: "never a slideshow".

  uv run tools/quality_gate.py render <video.mp4> [--no-depth] [--json out.json] [--quiet]
  uv run tools/quality_gate.py spec   <shot-spec.json>
  uv run tools/quality_gate.py json   <metrics.json>      (re-evaluate stored metrics)
  uv run tools/quality_gate.py both   <video.mp4> <shot-spec.json>
  uv run tools/quality_gate.py calm   <video.mp4> [--timeline timeline.json] [--json out.json] [--quiet]   (format "calm": pacing, holds, motion band, subjects, narrator audio; qg_checks.CALM)
  uv run tools/quality_gate.py hands  <rig-trace.json>   (HAND-TOPO/SIDE/SWAP, PROP-FACE, WRITE-REVEAL, NIB-CONTACT, LAYER-GRIP; also run inside `rig`)
  uv run tools/quality_gate.py rig    <rig-trace.json> [<shot-spec.json>]          (per-frame rig/face trace, kb/quality/rig-trace.schema.json)
  uv run tools/quality_gate.py extras <video.mp4> <shot-spec.json> [--text-mask-dir D] [--shadow-dir D]
  uv run tools/quality_gate.py look2d <video.mp4> [--json out.json]     # R-380 2D look
  uv run tools/quality_gate.py preview <previews/index.html> [--dynamic]  # R-382 playback (static scan; --dynamic needs Playwright)
  (SEAM, R-381, runs inside `rig` when the trace carries line_mask + seams[])
                                      (text-box contrast + texture, shadow mask holes, per-beat colour script vs declared)
  spec options: --root <repo root for bible/physics lookups>  --files (also check that thumbnails/sheets exist)
  --format premium|calm   (render, spec, both, json; default premium = "never a slideshow". calm = the calm-format profile,
                           CALM_RENDER_OVERRIDES / CALM_SPEC_OVERRIDES: pacing checks only, art checks unchanged; CLAUDE.md "Calm format")

Exit 0 = pass, 1 = fail (each failing check printed with its value), 2 = tool error.
GPU first: NVDEC decode (-hwaccel cuda) + scale_cuda, torch CUDA for flow and depth.
CPU: ffmpeg -threads 2, torch threads 2. Frames are sampled at 15 fps and 270x480.
Depth model: Depth-Anything-V2-SMALL only (Apache-2.0). Base/Large are CC-BY-NC: never.
Thresholds live in RENDER_GATES / SPEC_GATES below; calibration table in kb/quality/gate-spec.md.
"""
from __future__ import annotations
import json, math, re, subprocess, sys, shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qg_checks as qc   # merged spec checks, rig checks, render extras (R-300..R-379)

W, H, FPS = 270, 480, 15           # analysis size and rate
BLK, RAD = 16, 6                   # block size (px) and search radius (px) of the block matcher
DEPTH_MODEL = "depth-anything/Depth-Anything-V2-Small-hf"   # Apache-2.0. Never Base/Large.

# ---------------------------------------------------------------- thresholds (see gate-spec.md)
# (metric key, operator, threshold, human label)
RENDER_GATES = [
    ("freeze_share_05s",       "<=", 0.03, "share of runtime frozen in holds >= 0.5 s (ffmpeg freezedetect)"),
    ("dead_window_share",      "<=", 0.05, "share of 0.5 s windows with zero change"),
    ("low_motion_window_share","<=", 0.05, "share of 0.5 s windows where under 5% of blocks change (stills with a drift)"),
    ("motion_coverage",        ">=", 0.50, "mean share of 16 px blocks that change per step, over moving steps"),
    ("uniform_share",          "<=", 0.35, "share of moving steps explained by ONE global transform (slideshow detector)"),
    ("independent_share",      ">=", 0.50, "mean share of textured blocks that move differently from the global fit (layers, parts, objects)"),
    ("luma_range",             ">=", 0.85, "mean (p99 - p1) luminance range per frame, 0..1 (light has real highlights and darks)"),
    ("local_contrast",         ">=", 0.085, "mean 16 px block luminance std, 0..1 (light shapes forms)"),
]
DEPTH_GATES = [
    ("depth_bands",            ">=", 4.0,  "occupied depth bands (of 6) per frame, Depth Anything V2 Small"),
    ("parallax_corr",          ">=", 0.10, "correlation of depth with motion magnitude on moving blocks (near moves differently from far)"),
]
# Calibrated on Mix v5 (2026-10-23, 10/10) against the known fails (style.html v1, reels base 1/2): motion_coverage 0.50, local_contrast 0.085,
# parallax_corr 0.10 each sit between the highest fail and v5 / the liked reels. Others keep their earlier values (see kb/quality/gate-spec.md).
# Reported, never gating (measured, did not separate the 4 reels): kept so the numbers stay visible.
ADVISORY = ["motion_clusters", "direction_entropy", "soft_gradient_share", "depth_std", "cuts_per_min"]
SPEC_GATES = {
    "min_depth_planes": 5, "min_distinct_parallax": 4, "min_parallax_gap": 0.12,
    "min_rig_parts": 8, "min_lagged_parts": 3, "min_lag_frames": 2,
    "min_interactions_per_beat": 1, "max_static_s": 2.0, "max_hold_s": 0.8, "max_hold_share": 0.10,
    "min_anticipation_frames": 3, "min_camera_move_pct": 4,
}

# ---------------------------------------------------------------- the "calm" format profile (owner, 2026-10-24: CLAUDE.md "Calm format")
# HIS PACING, OUR ART: calm shots hold, breathe and drift. A separate profile beside the premium one; the premium numbers above are never
# edited. Only the pacing checks move (holds, static elements, camera move, frozen / dead / low-motion share, motion coverage, global-transform
# share, independent motion); the art checks (depth, light, contrast, 2D look, seams, hands, shadows) keep their premium thresholds.
# Source of every number: research/stickman-recipe.md section 2 (12 reels, ffmpeg + this gate): frozen share 13-17 %, low-motion windows
# 20-27 %, motion coverage 0.155-0.226, independent share 0.31-0.43. Each limit sits on the far side of the measured range (margin), so a
# calm shot can look like theirs and still fail when it is dead. PROVISIONAL until the first recorded calm shots are measured (DAILY.md).
CALM_RENDER_OVERRIDES = {
    "freeze_share_05s":        ("<=", 0.35),   # measured 0.13-0.17
    "dead_window_share":       ("<=", 0.20),   # a calm shot breathes and drifts: windows with zero change stay rare
    "low_motion_window_share": ("<=", 0.45),   # measured 0.20-0.27
    "motion_coverage":         (">=", 0.10),   # measured 0.155-0.226
    "uniform_share":           ("<=", 0.90),   # a slow whole-frame push IS one global transform; the check only fails a pure pan of a still
    "independent_share":       (">=", 0.015),  # MEASURED on our calm shots 0.02-0.24 (texture-dense ink set: most textured blocks rest); the stickman reels' 0.31-0.43
                                               # come from dark, flat frames. A non-zero floor: a pure pan of a still scores ~0 and still fails; uniform_share is the slideshow detector
}
CALM_SPEC_OVERRIDES = {
    "max_static_s": 4.5,        # a calm shot is about 3.7 s (recipe 3), up to 9 s; an element may rest for the whole shot if declared a hold
    "max_hold_s": 4.5, "max_hold_share": 0.50,
    "calm": True, "min_camera_move_pct": 2,   # a slow drift counts (recipe: scale 1.00 to 1.08 over a scene)
}
FORMATS = getattr(qc, "FORMATS", ("premium", "calm"))   # one declaration of the format names (qg_checks.py owns the episode-level calm checks)


def render_gates(fmt: str = "premium") -> list:
    if fmt == "calm":
        return [(k, *CALM_RENDER_OVERRIDES.get(k, (op, thr)), label) for k, op, thr, label in RENDER_GATES]
    return RENDER_GATES


def spec_gates(fmt: str = "premium") -> dict:
    return {**SPEC_GATES, **CALM_SPEC_OVERRIDES} if fmt == "calm" else SPEC_GATES

# ---------------------------------------------------------------- decode helpers
def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, **kw)

def decode_gray(path: str):
    import numpy as np
    cmd = ["ffmpeg", "-v", "error", "-hwaccel", "cuda", "-hwaccel_output_format", "cuda", "-threads", "2",
           "-i", path, "-an", "-vf", f"scale_cuda={W}:{H}:format=nv12,hwdownload,format=nv12,fps={FPS},format=gray",
           "-f", "rawvideo", "-"]
    p = run(cmd)
    if p.returncode != 0 or not p.stdout:
        raise RuntimeError("ffmpeg cuda decode failed: " + p.stderr.decode(errors="replace")[:400])
    a = np.frombuffer(p.stdout, np.uint8)
    n = a.size // (W * H)
    return a[: n * W * H].reshape(n, H, W)

def decode_rgb_at(path: str, t: float):
    import numpy as np
    cmd = ["ffmpeg", "-v", "error", "-hwaccel", "cuda", "-threads", "2", "-ss", f"{t:.3f}", "-i", path,
           "-frames:v", "1", "-vf", "scale=364:644", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]
    p = run(cmd)
    if p.returncode != 0 or len(p.stdout) != 364 * 644 * 3:
        return None
    return np.frombuffer(p.stdout, np.uint8).reshape(644, 364, 3)

def freezedetect(path: str) -> tuple[float, int, float]:
    """Same command as research/10: returns (frozen seconds, holds, duration)."""
    pr = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path])
    dur = float(pr.stdout.decode().strip())
    p = run(["ffmpeg", "-hwaccel", "cuda", "-threads", "2", "-i", path, "-vf", "freezedetect=n=0.003:d=0.5",
             "-an", "-f", "null", "-"])
    txt = p.stderr.decode(errors="replace")
    ds = [float(x) for x in re.findall(r"freeze_duration: ([0-9.]+)", txt)]
    return sum(ds), len(ds), dur

# ---------------------------------------------------------------- block matching flow (torch, CUDA)
def block_flow(torch, a, b):
    """a, b: (H,W) float32 cuda. Returns fx, fy (hb,wb) sub-pixel, zero-shift block diff, texture mask."""
    import torch.nn.functional as F
    Hh, Ww = a.shape
    ac = a[RAD:Hh - RAD, RAD:Ww - RAD]
    costs = []
    for dy in range(-RAD, RAD + 1):
        for dx in range(-RAD, RAD + 1):
            bs = b[RAD + dy:Hh - RAD + dy, RAD + dx:Ww - RAD + dx]
            c = F.avg_pool2d((ac - bs).abs()[None, None], BLK)[0, 0]
            costs.append(c + 1e-3 * (dx * dx + dy * dy))
    cv = torch.stack(costs)                       # (S,hb,wb)
    n = 2 * RAD + 1
    idx = cv.argmin(0)
    iy, ix = idx // n, idx % n
    cv3 = cv.view(n, n, *cv.shape[1:])
    def at(yy, xx):
        yy = yy.clamp(0, n - 1); xx = xx.clamp(0, n - 1)
        return cv3[yy, xx, torch.arange(cv.shape[1], device=cv.device)[:, None], torch.arange(cv.shape[2], device=cv.device)[None, :]]
    c0 = at(iy, ix)
    def para(cm, cp):
        den = (cm + cp - 2 * c0)
        return torch.where(den.abs() > 1e-6, 0.5 * (cm - cp) / den, torch.zeros_like(den)).clamp(-0.5, 0.5)
    sx = para(at(iy, ix - 1), at(iy, ix + 1))
    sy = para(at(iy - 1, ix), at(iy + 1, ix))
    fx = (ix - RAD).float() + sx
    fy = (iy - RAD).float() + sy
    m = F.avg_pool2d(ac[None, None], BLK)[0, 0]
    v = F.avg_pool2d((ac * ac)[None, None], BLK)[0, 0] - m * m
    tex = v > 25.0                                 # std > 5 levels
    d0 = F.avg_pool2d((ac - b[RAD:Hh - RAD, RAD:Ww - RAD]).abs()[None, None], BLK)[0, 0]
    return fx, fy, d0, tex, c0

def fit_similarity(torch, fx, fy, mask):
    """Least squares tx,ty,scale,rot on masked blocks. Returns residual rms and predicted field."""
    hb, wb = fx.shape
    ys, xs = torch.meshgrid(torch.arange(hb, device=fx.device, dtype=torch.float32),
                            torch.arange(wb, device=fx.device, dtype=torch.float32), indexing="ij")
    xs = (xs - (wb - 1) / 2) * BLK; ys = (ys - (hb - 1) / 2) * BLK
    x, y, u, v = xs[mask], ys[mask], fx[mask], fy[mask]
    one, zero = torch.ones_like(x), torch.zeros_like(x)
    A = torch.cat([torch.stack([one, zero, x, -y], 1), torch.stack([zero, one, y, x], 1)], 0)
    bvec = torch.cat([u, v], 0)
    sol = torch.linalg.lstsq(A.cpu(), bvec.cpu()[:, None]).solution[:, 0].to(fx.device)
    px = sol[0] + sol[2] * xs - sol[3] * ys
    py = sol[1] + sol[3] * xs + sol[2] * ys
    return px, py

# ---------------------------------------------------------------- parallax estimator (E01 run 1: eight to ten samples were too few to trust a 0.098 against 0.10)
PAR = {"stride": 3,             # frame pair (i, i+3): enough travel for the block flow, short enough to stay one camera move
       "candidates": 96,        # evenly spaced positions over the video that are looked at (cheap flow only)
       "samples": 32,           # positions that get the depth model: the evenly spaced valid ones among the candidates
       "min_moving_blocks": 6,  # a sample needs this many textured, matched, moving blocks (as before)
       "bootstrap": 2000, "seed": 7}

def parallax_summary(corrs: list, n_candidates: int, n_valid: int, thr: float | None = None) -> dict:
    """The parallax metrics from the per-sample correlations. parallax_corr is the MEDIAN (what the gate compares against the unchanged threshold);
    the rest says how far to trust it: spread (p25, p75), a bootstrap 95 % interval of the median, a 0..1 confidence (sample count x agreement),
    and `parallax_marginal` when the interval straddles the threshold (the verdict could flip on another sample set)."""
    import numpy as np
    if thr is None:
        thr = next(t for k, _, t, _ in DEPTH_GATES if k == "parallax_corr")
    c = np.asarray(corrs, dtype=float)
    out = {"parallax_samples": int(c.size), "parallax_candidates": int(n_candidates), "parallax_valid": int(n_valid)}
    if c.size == 0:
        out.update(parallax_corr=0.0, parallax_corr_p25=None, parallax_corr_p75=None, parallax_ci95=None, parallax_conf=0.0, parallax_marginal=True)
        return out
    rng = np.random.default_rng(PAR["seed"])
    boots = np.median(rng.choice(c, size=(PAR["bootstrap"], c.size), replace=True), axis=1)
    lo, hi = np.percentile(boots, [2.5, 97.5])
    p25, p75 = np.percentile(c, [25, 75])
    conf = min(1.0, c.size / 16.0) * (1.0 - min(1.0, float(p75 - p25) / 0.5)) if c.size >= 4 else 0.0
    out.update(parallax_corr=round(float(np.median(c)), 3), parallax_corr_p25=round(float(p25), 3), parallax_corr_p75=round(float(p75), 3),
               parallax_ci95=[round(float(lo), 3), round(float(hi), 3)], parallax_conf=round(float(conf), 2), parallax_marginal=bool(lo < thr <= hi or lo <= thr < hi))
    return out

def parallax_estimate(torch, F, np, g, n: int, depth_of, cut: float) -> dict:
    """Correlation of depth with motion magnitude on moving blocks, over up to PAR['samples'] evenly spread frame pairs. g = (n,H,W) float gray on the device;
    depth_of(i) = depth map of frame i (or None)."""
    cands = sorted({int(round(q)) for q in np.linspace(max(1, n * 0.03), n * 0.95, PAR["candidates"])})
    valid = []
    for i in cands:
        if i + PAR["stride"] >= n: continue
        a, b = g[i], g[i + PAR["stride"]]
        if (a - b).abs().mean().item() > cut: continue                      # a hard cut is not parallax
        fx, fy, d0, tex, c0 = block_flow(torch, a, b)
        mag = torch.sqrt(fx * fx + fy * fy)
        ok = tex & (c0 < 14.0)
        if int((ok & (mag > 0.3)).sum()) < PAR["min_moving_blocks"]: continue
        valid.append((i, ok, mag))
    pick = valid if len(valid) <= PAR["samples"] else [valid[k] for k in sorted({int(round(q)) for q in np.linspace(0, len(valid) - 1, PAR["samples"])})]
    corrs = []
    for i, ok, mag in pick:
        d = depth_of(i)
        if d is None: continue
        db = F.avg_pool2d(d[RAD:H - RAD, RAD:W - RAD][None, None], BLK)[0, 0]
        x, y = db[ok], mag[ok]
        if x.std() < 1e-4 or y.std() < 1e-4: continue
        c = torch.corrcoef(torch.stack([x, y]))[0, 1].item()
        if c == c: corrs.append(c)      # not NaN
    return parallax_summary(corrs, len(cands), len(valid))

# ---------------------------------------------------------------- render analysis
def analyse_render(path: str, use_depth: bool = True, quiet: bool = False) -> dict:
    import numpy as np, torch
    torch.set_num_threads(2)
    dev = "cuda"
    assert torch.cuda.is_available(), "CUDA not available: GPU-first gate refuses to run on CPU"
    log = (lambda *a: None) if quiet else (lambda *a: print(*a, file=sys.stderr))
    fz, holds, dur = freezedetect(path)
    fr = decode_gray(path)
    n = len(fr)
    log(f"decoded {n} frames at {FPS} fps, {W}x{H}; duration {dur:.1f}s")
    g = torch.from_numpy(fr).to(dev).float()

    CUT = 35.0                                # mean abs diff above this = a hard cut, not motion
    rows = []                                 # per step: dict
    for i in range(n - 1):
        a, b = g[i], g[i + 1]
        diff = (a - b).abs().mean().item()
        if diff > CUT:
            rows.append(dict(cut=True)); continue
        fx, fy, d0, tex, c0 = block_flow(torch, a, b)
        changed = (d0 > 1.5)
        cov = changed.float().mean().item()
        mag = torch.sqrt(fx * fx + fy * fy)
        valid = tex & (c0 < 14.0)
        moving = valid & (mag > 0.3)
        r = dict(cut=False, diff=diff, cov=cov, dead=(cov < 0.002 and diff < 0.25), nvalid=int(valid.sum()),
                 nmov=int(moving.sum()), uniform=False, indep=0.0, clusters=0, entropy=0.0)
        if r["nmov"] >= 6:
            px, py = fit_similarity(torch, fx, fy, valid)
            res = torch.sqrt((fx - px) ** 2 + (fy - py) ** 2)
            rms_res = res[valid].pow(2).mean().sqrt().item()
            rms_f = mag[valid].pow(2).mean().sqrt().item()
            r["uniform"] = (rms_res < 0.20) or (rms_res < 0.25 * max(rms_f, 1e-6))
            r["indep"] = (res[valid] > 0.5).float().mean().item()
            q = torch.stack([(fx[moving] * 2).round(), (fy[moving] * 2).round()], 1)
            u, cnt = torch.unique(q, dim=0, return_counts=True)
            r["clusters"] = int((cnt >= 3).sum())
            ang = torch.atan2(fy[moving], fx[moving]); wgt = mag[moving]
            hist = torch.histc(ang, 8, -math.pi, math.pi) if wgt.numel() else torch.zeros(8, device=dev)
            hsum = hist.sum()
            if hsum > 0:
                p = hist / hsum; p = p[p > 0]
                r["entropy"] = float(-(p * p.log()).sum() / math.log(8))
        rows.append(r)
    steps = [r for r in rows if not r["cut"]]
    cuts = n - 1 - len(steps)
    moving_steps = [r for r in steps if r["nmov"] >= 6]
    # dead windows: 0.5 s = 7 steps at 15 fps
    win = 7; dead_w = 0; tot_w = 0; low_w = 0
    for s in range(0, len(rows) - win + 1, win):
        chunk = rows[s:s + win]
        tot_w += 1
        if all((not c["cut"]) and c["dead"] for c in chunk): dead_w += 1
        if all(not c["cut"] for c in chunk) and float(np.mean([c["cov"] for c in chunk])) < 0.05: low_w += 1
    m = {}
    m["duration_s"] = round(dur, 2)
    m["cuts_per_min"] = round(cuts / max(dur, 1e-6) * 60, 1)
    m["freeze_share_05s"] = round(fz / dur, 4)
    m["freeze_holds_05s"] = holds
    m["dead_window_share"] = round(dead_w / max(tot_w, 1), 4)
    m["low_motion_window_share"] = round(low_w / max(tot_w, 1), 4)
    m["moving_step_share"] = round(len(moving_steps) / max(len(steps), 1), 4)
    m["motion_coverage"] = round(float(np.mean([r["cov"] for r in moving_steps])) if moving_steps else 0.0, 4)
    m["uniform_share"] = round(float(np.mean([r["uniform"] for r in moving_steps])) if moving_steps else 1.0, 4)
    m["independent_share"] = round(float(np.mean([r["indep"] for r in moving_steps])) if moving_steps else 0.0, 4)
    m["motion_clusters"] = round(float(np.mean([r["clusters"] for r in moving_steps])) if moving_steps else 0.0, 3)
    m["direction_entropy"] = round(float(np.mean([r["entropy"] for r in moving_steps])) if moving_steps else 0.0, 3)

    # luminance, local contrast, soft gradients on sampled frames (every 0.5 s)
    import torch.nn.functional as F
    lr, lc, sg = [], [], []
    kx = torch.tensor([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], device=dev, dtype=torch.float32)[None, None] / 8
    ky = kx.transpose(2, 3)
    for i in range(0, n, 8):
        f = g[i] / 255.0
        lo, hi = torch.quantile(f.flatten()[::7], torch.tensor([0.01, 0.99], device=dev)).tolist()
        lr.append(hi - lo)
        mu = F.avg_pool2d(f[None, None], BLK); v = F.avg_pool2d((f * f)[None, None], BLK) - mu * mu
        sd = v.clamp_min(0).sqrt()[0, 0]
        lc.append(sd.mean().item())
        gx = F.conv2d(f[None, None], kx); gy = F.conv2d(f[None, None], ky)
        mgx, mgy = F.avg_pool2d(gx, BLK)[0, 0], F.avg_pool2d(gy, BLK)[0, 0]
        mag = F.avg_pool2d(torch.sqrt(gx * gx + gy * gy), BLK)[0, 0]
        coh = torch.sqrt(mgx * mgx + mgy * mgy) / (mag + 1e-6)     # 1 = one steady direction = a ramp
        h2, w2 = min(coh.shape[0], sd.shape[0]), min(coh.shape[1], sd.shape[1])
        ramp = (coh[:h2, :w2] >= 0.7) & (mag[:h2, :w2] >= 0.004) & (sd[:h2, :w2] >= 0.02) & (sd[:h2, :w2] <= 0.25)
        sg.append(ramp.float().mean().item())
    m["luma_range"] = round(float(np.mean(lr)), 3)
    m["local_contrast"] = round(float(np.mean(lc)), 4)
    m["soft_gradient_share"] = round(float(np.mean(sg)), 4)

    # depth and parallax (Depth Anything V2 Small, CUDA fp16)
    m["depth_bands"] = None; m["depth_std"] = None; m["parallax_corr"] = None; m["parallax_samples"] = 0
    if use_depth:
        try:
            from transformers import AutoImageProcessor, AutoModelForDepthEstimation
            from PIL import Image
            proc = AutoImageProcessor.from_pretrained(DEPTH_MODEL)
            model = AutoModelForDepthEstimation.from_pretrained(DEPTH_MODEL, torch_dtype=torch.float16).to(dev).eval()
            bands, stds = [], []
            depth_cache: dict = {}

            def depth_of(i):          # normalised depth of frame i, 0 far .. 1 near (cached: the band stats and the parallax pass share frames)
                if i in depth_cache:
                    return depth_cache[i]
                rgb = decode_rgb_at(path, i / FPS)
                if rgb is None:
                    depth_cache[i] = None; return None
                inp = proc(images=Image.fromarray(rgb), return_tensors="pt")
                with torch.no_grad():
                    d = model(pixel_values=inp["pixel_values"].to(dev, torch.float16)).predicted_depth
                d = F.interpolate(d[None].float(), size=(H, W), mode="bilinear")[0, 0]
                d = (d - d.min()) / (d.max() - d.min() + 1e-6)
                depth_cache[i] = d
                return d
            for i in [int(n * q) for q in (0.08, 0.17, 0.26, 0.35, 0.44, 0.53, 0.62, 0.71, 0.80, 0.89)]:   # band / spread stats: the same ten frames as before
                if i + 3 >= n: continue
                d = depth_of(i)
                if d is None: continue
                hist = torch.histc(d, 6, 0, 1) / d.numel()
                bands.append(int((hist >= 0.04).sum())); stds.append(d.std().item())
            if bands:
                m["depth_bands"] = round(float(np.mean(bands)), 2); m["depth_std"] = round(float(np.mean(stds)), 3)
            m.update(parallax_estimate(torch, F, np, g, n, depth_of, CUT))
            del model; torch.cuda.empty_cache()
        except Exception as e:                  # report, do not hide: depth checks then FAIL as "not measured"
            m["depth_error"] = repr(e)[:200]
    return m

# ---------------------------------------------------------------- calm format (research/stickman-recipe.md; bands in qg_checks.CALM)
def scene_changes(path: str, thr: float = 0.08) -> list[float]:
    """Times of ffmpeg scene changes above thr (soft joins count) on a 270x480 copy. Same command as research/stickman-recipe.md section 2."""
    p = run(["ffmpeg", "-hide_banner", "-nostdin", "-threads", "2", "-i", path, "-vf", f"scale=270:480,select='gt(scene,{thr})',showinfo",
             "-an", "-f", "null", "-"])
    return [float(x) for x in re.findall(r"pts_time:([0-9.]+)", p.stderr.decode(errors="replace"))]

def freeze_spans(path: str) -> list[tuple[float, float]]:
    """Each hold of 0.5 s or more as (start, end) (same freezedetect command as freezedetect())."""
    p = run(["ffmpeg", "-hwaccel", "cuda", "-threads", "2", "-i", path, "-vf", "freezedetect=n=0.003:d=0.5", "-an", "-f", "null", "-"])
    t = p.stderr.decode(errors="replace")
    st = [float(x) for x in re.findall(r"freeze_start: ([0-9.]+)", t)]
    en = [float(x) for x in re.findall(r"freeze_end: ([0-9.]+)", t)]
    du = [float(x) for x in re.findall(r"freeze_duration: ([0-9.]+)", t)]
    if len(en) < len(st) and len(du) == len(st):      # a hold that runs to the end of the file has no freeze_end line
        en += [st[i] + du[i] for i in range(len(en), len(st))]
    return list(zip(st, en))

def freeze_durations(path: str) -> list[float]:
    """Each hold of 0.5 s or more (same freezedetect command as freezedetect())."""
    p = run(["ffmpeg", "-hwaccel", "cuda", "-threads", "2", "-i", path, "-vf", "freezedetect=n=0.003:d=0.5", "-an", "-f", "null", "-"])
    return [float(x) for x in re.findall(r"freeze_duration: ([0-9.]+)", p.stderr.decode(errors="replace"))]

def audio_stats(path: str) -> dict:
    """Audio track facts without any model: active share (20 ms frames above -40 dBFS), integrated LUFS and LRA (ffmpeg ebur128)."""
    import numpy as np
    pr = run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_type", "-of", "csv=p=0", path])
    if not pr.stdout.strip():
        return {"has_audio": False}
    p = run(["ffmpeg", "-v", "error", "-threads", "2", "-i", path, "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"])
    a = np.frombuffer(p.stdout, np.int16).astype(np.float32) / 32768
    if a.size < 320:
        return {"has_audio": False}
    fr = a[: a.size // 320 * 320].reshape(-1, 320)
    db = 20 * np.log10(np.sqrt((fr ** 2).mean(1)) + 1e-9)
    e = run(["ffmpeg", "-hide_banner", "-nostdin", "-threads", "2", "-i", path, "-vn", "-af", "ebur128=framelog=quiet", "-f", "null", "-"]).stderr.decode(errors="replace")
    tail = e[e.rfind("Summary:"):]
    mi, ml = re.search(r"I:\s+(-?[0-9.]+) LUFS", tail), re.search(r"LRA:\s+([0-9.]+) LU", tail)
    return {"has_audio": True, "audio_active": round(float((db > -40).mean()), 3),
            "loudness_i": float(mi.group(1)) if mi else None, "lra": float(ml.group(1)) if ml else None}

def analyse_calm(path: str, quiet: bool = False, timeline: dict | None = None) -> dict:
    """Metrics for the calm format: pacing (shot changes, holds), motion (coverage, clusters), narrator audio. No depth model.
    With `timeline` (the episode's timeline.json) the pacing is measured per DECLARED shot: detector hits inside a declared transition window are
    ignored and holds are measured outside those windows (qg_checks.declared_pacing). Without it (the harvested reels carry no plan) the detector counts."""
    m = analyse_render(path, use_depth=False, quiet=quiet)
    cuts = scene_changes(path)
    dur = m["duration_s"]
    if timeline:
        m.update(qc.declared_pacing(timeline, dur, cuts, freeze_spans(path)))
        m["pacing_source"] = "declared shots (timeline.json)"
    else:
        m["scene_changes"] = len(cuts)
        m["shot_len_s"] = round(dur / (len(cuts) + 1), 2)
        m["cuts_per_min"] = round(len(cuts) / max(dur, 1e-6) * 60, 1)       # calm cut rate counts soft joins (scene > 0.08); the premium advisory above counts hard cuts
        fd = freeze_durations(path)
        m["longest_hold_s"] = round(max(fd), 2) if fd else 0.0
        m["pacing_source"] = "video detector (no declaration)"
    m.update(audio_stats(path))
    return m

# ---------------------------------------------------------------- gates
OPS = {"<=": lambda v, t: v <= t, ">=": lambda v, t: v >= t}

def evaluate(metrics: dict, use_depth: bool = True, fmt: str = "premium") -> list[str]:
    fails = []
    for key, op, thr, label in render_gates(fmt) + (DEPTH_GATES if use_depth else []):
        v = metrics.get(key)
        if v is None:
            fails.append(f"FAIL {key} = not measured (need {op} {thr}): {label}"); continue
        if not OPS[op](v, thr):
            fails.append(f"FAIL {key} = {v} (need {op} {thr}): {label}")
    return fails

# ---------------------------------------------------------------- spec checks
def check_spec(spec: dict, root=None, files: bool = False, fmt: str = "premium") -> list[str]:
    return check_spec_core(spec, fmt) + qc.check_spec_v2(spec, root, files)

def check_spec_core(spec: dict, fmt: str = "premium") -> list[str]:
    G = spec_gates(fmt); f = []
    beats = spec.get("beats", [])
    if not beats: return ["FAIL beats = 0: the spec has no beats"]
    rig = spec.get("characters", [])
    for ch in rig:
        parts = ch.get("parts", [])
        lagged = [p for p in parts if p.get("lag_frames", 0) >= G["min_lag_frames"] and p.get("follows")]
        if len(parts) < G["min_rig_parts"]:
            f.append(f"FAIL character {ch.get('id')} parts = {len(parts)} (need >= {G['min_rig_parts']}): rigid sprite risk")
        if len(lagged) < G["min_lagged_parts"]:
            f.append(f"FAIL character {ch.get('id')} lagged parts = {len(lagged)} (need >= {G['min_lagged_parts']} with follows + lag_frames >= {G['min_lag_frames']}): no follow-through")
        ind = [p for p in parts if p.get("own_curve")]
        if len(ind) < len(parts) * 0.75:
            f.append(f"FAIL character {ch.get('id')} parts with own animation curve = {len(ind)}/{len(parts)} (need >= 75%)")
    if not rig: f.append("FAIL characters = 0: no rigged character declared")
    prev_light = None; light_sigs = set()
    total = 0.0; hold_total = 0.0
    for b in beats:
        bid = b.get("id", "?"); dur = float(b.get("end", 0)) - float(b.get("start", 0)); total += dur
        planes = b.get("depth_planes", [])
        par = sorted({round(float(p.get("parallax", 0)), 3) for p in planes})
        gaps_ok = all(par[i + 1] - par[i] >= G["min_parallax_gap"] for i in range(len(par) - 1)) if len(par) > 1 else False
        if len(planes) < G["min_depth_planes"]: f.append(f"FAIL beat {bid} depth_planes = {len(planes)} (need >= {G['min_depth_planes']})")
        if len(par) < G["min_distinct_parallax"] or not gaps_ok:
            f.append(f"FAIL beat {bid} distinct parallax factors = {len(par)} with gap >= {G['min_parallax_gap']}: {par}")
        if planes and not (min(par) < 1.0 < max(par)):
            f.append(f"FAIL beat {bid} parallax must straddle 1.0 (background < 1 < foreground): {par}")
        if float(b.get("camera_move_pct", 0)) < G["min_camera_move_pct"] and not b.get("locked_camera_because"):
            f.append(f"FAIL beat {bid} camera_move_pct = {b.get('camera_move_pct', 0)} (need >= {G['min_camera_move_pct']} or locked_camera_because)")
        lt = b.get("light", {})
        for role in ("key", "fill", "rim"):
            if not lt.get(role) or not lt[role].get("dir") or not lt[role].get("color"):
                f.append(f"FAIL beat {bid} light.{role} missing dir/color")
        sig = json.dumps(lt, sort_keys=True); light_sigs.add(sig)
        if not b.get("cast_shadows"):
            f.append(f"FAIL beat {bid} cast_shadows = 0 (need >= 1 caster -> receiver)")
        elif not any(s.get("receiver") not in (None, "", "ground") for s in b["cast_shadows"]) and len(b["cast_shadows"]) < 2:
            f.append(f"FAIL beat {bid} only a ground shadow: add one shadow on a non-ground receiver")
        ia = b.get("interactions", [])
        need = G["min_interactions_per_beat"] if G.get("calm") else max(G["min_interactions_per_beat"], int(dur // 3))   # calm: one subject, one cause-effect per beat
        good = [x for x in ia if x.get("cause") and x.get("effect") and x.get("kind")]
        if len(good) < need: f.append(f"FAIL beat {bid} interactions = {len(good)} (need >= {need}: cause -> effect, kind)")
        if b.get("treatment") not in ("A", "B", "A+B") or not b.get("treatment_reason"):
            f.append(f"FAIL beat {bid} treatment must be A, B or A+B with treatment_reason")
        for act in b.get("actions", []):
            if act.get("anticipation_frames", 0) < G["min_anticipation_frames"] and not act.get("no_anticipation_because"):
                f.append(f"FAIL beat {bid} action {act.get('part')} anticipation_frames = {act.get('anticipation_frames', 0)} (need >= {G['min_anticipation_frames']} or a reason)")
        for el in b.get("elements", []):
            st = float(el.get("static_s", 0))
            if st > G["max_static_s"] and not any(h.get("element") == el.get("id") for h in b.get("holds", [])):
                f.append(f"FAIL beat {bid} element {el.get('id')} static {st}s > {G['max_static_s']}s and not a declared hold")
        for h in b.get("holds", []):
            d = float(h.get("end", 0)) - float(h.get("start", 0)); hold_total += d
            if d > G["max_hold_s"] or not h.get("why"):
                f.append(f"FAIL beat {bid} hold {h.get('element')} {d:.2f}s (max {G['max_hold_s']}s, needs why)")
    if len(beats) > 1 and len(light_sigs) < 2:
        f.append("FAIL light is identical in every beat: one global light that never changes")
    if total and hold_total / total > G["max_hold_share"]:
        f.append(f"FAIL declared holds = {hold_total/total:.0%} of runtime (max {G['max_hold_share']:.0%})")
    return f

# ---------------------------------------------------------------- rig + render extras (R-300..R-379)
def iter_rgb(path: str, w: int, h: int, fps: float):
    """Stream RGB frames (h,w,3) with NVDEC decode + scale_cuda; constant memory, 2 ffmpeg threads."""
    import numpy as np
    cmd = ["ffmpeg", "-v", "error", "-hwaccel", "cuda", "-hwaccel_output_format", "cuda", "-threads", "2", "-i", path, "-an",
           "-vf", f"scale_cuda={w}:{h}:format=nv12,hwdownload,format=nv12,fps={fps}", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]
    pr = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    n = w * h * 3; i = 0
    while True:
        buf = pr.stdout.read(n)
        if len(buf) < n:
            break
        yield i / fps, np.frombuffer(buf, np.uint8).reshape(h, w, 3)
        i += 1
    pr.stdout.close(); err = pr.stderr.read().decode(errors="replace"); pr.wait()
    if i == 0:
        raise RuntimeError("ffmpeg cuda decode produced no frames: " + err[:300])

def check_extras(video: str, spec: dict, text_mask_dir=None, shadow_dir=None, quiet=True) -> list[str]:
    import numpy as np
    from PIL import Image
    FW, FH, RFPS = 540, 960, 8.0; scale = FW / 1080.0
    beats = spec.get("beats", []); fails: list[str] = []
    per_beat: list[list] = [[] for _ in beats]
    text_samples: dict = {}
    texts = [(t, b) for b in beats for t in b.get("texts", [])]
    fails += qc.piece_caption_issues(spec) if "reference" not in Path(video).resolve().parts else []   # PIECE-NO-CAPTION, declared side
    stray_frames, stray_px = [], 0
    for t_s, fr in iter_rgb(video, FW, FH, RFPS):
        if text_mask_dir:   # PIECE-NO-CAPTION, drawn side: text pixels outside every declared text box are undeclared text (a baked caption)
            mp0 = Path(text_mask_dir) / f"{int(round(t_s * float(spec.get('fps', 24)))):04d}.png"
            if mp0.exists():
                m0 = np.asarray(Image.open(mp0).convert("L").resize((FW, FH))) > 127
                if m0.any():
                    allowed = np.zeros_like(m0)
                    for t, b in texts:
                        if t.get("t0", 0) - 0.05 <= t_s <= t.get("t1", 0) + 0.05:
                            bx = t["box"]; pad = qc.RENDER2.get("stray_text_pad_px", 12) * scale
                            allowed[max(int((bx["y"] - 0) * scale - pad), 0):int((bx["y"] + bx["h"]) * scale + pad), max(int(bx["x"] * scale - pad), 0):int((bx["x"] + bx["w"]) * scale + pad)] = True
                    n_out = int((m0 & ~allowed).sum())
                    if n_out >= qc.RENDER2.get("stray_text_px", 150):
                        stray_frames.append(round(t_s, 2)); stray_px = max(stray_px, n_out)
        for bi, b in enumerate(beats):
            if float(b["start"]) <= t_s < float(b["end"]):
                per_beat[bi].append(fr[::4, ::4])
        for t, b in texts:
            if t.get("t0", 0) <= t_s <= t.get("t1", 0):
                mask = None
                if text_mask_dir:
                    mp = Path(text_mask_dir) / f"{int(round(t_s * float(spec.get('fps', 24)))):04d}.png"
                    if mp.exists():
                        mask = np.asarray(Image.open(mp).convert("L").resize((FW, FH))) > 127
                c, tx, sh, used = qc.text_box_metrics(fr, t["box"], t["height_px"], scale, mask)
                text_samples.setdefault(t["id"], (t, []))[1].append({"contrast": c, "texture": tx, "share": sh, "mask": used})
    for tid, (t, smp) in text_samples.items():
        fails += qc.check_text_render(smp, t["height_px"], tid)
    for t, b in texts:
        if t["id"] not in text_samples:
            fails.append(qc.F("REND-TEXT-CONTRAST", f"text {t['id']} has no frames in {t.get('t0')}..{t.get('t1')} s to measure"))
    if len(stray_frames) >= qc.RENDER2.get("stray_text_frames", 3) and "reference" not in Path(video).resolve().parts:
        fails.append(qc.F("PIECE-NO-CAPTION", f"text drawn outside every declared text box on {len(stray_frames)} sampled frames (first at {stray_frames[0]} s, up to {stray_px} px): "
                          "a baked caption or undeclared text; pieces draw only declared diegetic text, compose.py owns the dialogue captions"))
    stats = [qc.colour_stats(fs) if fs else {"hue": 0, "sat": 0, "val": 0, "luma": 0} for fs in per_beat]
    fails += qc.check_colour_script(stats, spec)
    if shadow_dir:
        for mp in sorted(Path(shadow_dir).rglob("*.png")):   # rglob: several characters keep one folder each (masks/shadow/<actor>/NNNN.png)
            im = Image.open(mp).convert("L"); im = im.resize((max(im.width // 2, 1), max(im.height // 2, 1)))
            fails += qc.shadow_mask_issues(np.asarray(im) > 127, mp.relative_to(shadow_dir).as_posix())
    if not quiet:
        print(json.dumps({"colour_script": stats}), file=sys.stderr)
    return fails

def check_look2d(video: str, quiet=True):
    """R-380 2D look: hard-edge share and smooth-ramp area on 540x960 luma frames at 2 fps."""
    import numpy as np
    lum = (( (0.2126 * fr[..., 0] + 0.7152 * fr[..., 1] + 0.0722 * fr[..., 2]) / 255.0).astype(np.float32) for _, fr in iter_rgb(video, 540, 960, 2.0))
    m = qc.look2d_metrics(lum)
    return m, qc.check_look2d(m)

# ---------------------------------------------------------------- cli
def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] == "json":          # re-evaluate stored metrics, no decoding
        res = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        fails = evaluate(res, res.get("depth_bands") is not None, "calm" if "--format" in argv and argv[argv.index("--format") + 1] == "calm" else "premium")
        print(json.dumps({k: v for k, v in res.items() if k not in ("fails", "verdict")}))
        for x in fails: print(x)
        print("FAIL" if fails else "PASS"); return 1 if fails else 0
    if len(argv) >= 2 and argv[0] == "calmjson":      # re-evaluate stored calm metrics, no decoding (episode-level bands)
        res = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        fails = qc.check_calm_render(res)
        for x in fails: print(x)
        print("FAIL" if fails else "PASS"); return 1 if fails else 0
    if len(argv) < 2 or argv[0] not in ("render", "spec", "both", "rig", "extras", "look2d", "preview", "hands", "calm"):
        print(__doc__); return 2
    cmd = argv[0]; quiet = "--quiet" in argv; use_depth = "--no-depth" not in argv
    opt = lambda k: argv[argv.index(k) + 1] if k in argv else None
    out_json = opt("--json"); root = opt("--root") or str(Path(__file__).resolve().parent.parent)
    fmt = opt("--format") or "premium"
    if fmt not in FORMATS:
        print(f"TOOL ERROR: --format must be one of {FORMATS}"); return 2
    optvals = {out_json, opt("--timeline"), opt("--root"), opt("--text-mask-dir"), opt("--shadow-dir"), opt("--format")} - {None}
    pos = [a for a in argv[1:] if not a.startswith("--") and a not in optvals]
    if cmd == "preview":
        try:
            pth = Path(pos[0]); fails = qc.check_preview_static(pth.read_text(encoding="utf-8"), pth.name)
            if "--dynamic" in argv:
                fails += qc.check_preview_dynamic(pth.resolve().as_uri())
        except Exception as e:
            print("TOOL ERROR:", repr(e)); return 2
        for x in fails: print(x)
        print("FAIL" if fails else "PASS"); return 1 if fails else 0
    if cmd == "calm":
        try:
            tlp = opt("--timeline")
            res = analyse_calm(pos[0], quiet, json.loads(Path(tlp).read_text(encoding="utf-8")) if tlp else None)
            fails = qc.check_calm_render(res)
        except Exception as e:
            print("TOOL ERROR:", repr(e)); return 2
        res["verdict"] = "FAIL" if fails else "PASS"; res["fails"] = fails; res["format"] = "calm"
        if out_json: Path(out_json).write_text(json.dumps(res, indent=1), encoding="utf-8")
        print(json.dumps({k: v for k, v in res.items() if k != "fails"}))
        for x in fails: print(x)
        print(res["verdict"]); return 1 if fails else 0
    if cmd == "look2d":
        try:
            m, fails = check_look2d(pos[0], quiet)
        except Exception as e:
            print("TOOL ERROR:", repr(e)); return 2
        if out_json: Path(out_json).write_text(json.dumps(m, indent=1), encoding="utf-8")
        print(json.dumps({k: round(v, 4) if isinstance(v, float) else v for k, v in m.items()}))
        for x in fails: print(x)
        print("FAIL" if fails else "PASS"); return 1 if fails else 0
    if cmd == "hands":
        try:
            fails = qc.check_hands_writing(json.loads(Path(pos[0]).read_text(encoding="utf-8")))
        except Exception as e:
            print("TOOL ERROR:", repr(e)); return 2
        for x in fails: print(x)
        print("FAIL" if fails else "PASS"); return 1 if fails else 0
    if cmd in ("rig", "extras"):
        try:
            if cmd == "rig":
                tr = json.loads(Path(pos[0]).read_text(encoding="utf-8"))
                sp = json.loads(Path(pos[1]).read_text(encoding="utf-8")) if len(pos) > 1 else None
                fails = qc.check_rig(tr, sp, root, Path(pos[0]).parent)
            else:
                sp = json.loads(Path(pos[1]).read_text(encoding="utf-8"))
                fails = check_extras(pos[0], sp, opt("--text-mask-dir"), opt("--shadow-dir"), quiet)
        except Exception as e:
            print("TOOL ERROR:", repr(e)); return 2
        for x in fails: print(x)
        print("FAIL" if fails else "PASS"); return 1 if fails else 0
    fails: list[str] = []; res: dict = {}
    try:
        if cmd in ("render", "both"):
            res = analyse_render(pos[0], use_depth, quiet)
            fails += evaluate(res, use_depth, fmt)
            if fmt == "calm":   # a calm SHOT: the restlessness ceilings too (a shot has no wrapper, narrator or shot-length band of its own)
                fails += qc.check_calm_shot(res, event="--event" in argv)
        if cmd in ("spec", "both"):
            sp = Path(pos[-1])
            spec_doc = json.loads(sp.read_text(encoding="utf-8"))
            sfmt = opt("--format") or (qc.format_of(spec_doc) if hasattr(qc, "format_of") else "premium")   # a spec that declares "format": "calm" is gated as calm
            fl = check_spec(spec_doc, root, "--files" in argv, sfmt)
            if "reference" in sp.resolve().parts:   # approved references predate the no-tashkeel rule; never re-rendered
                fl = [x for x in fl if "TEXT-NO-TASHKEEL" not in x and "PIECE-NO-CAPTION" not in x]   # ... and the baked captions that compose.py now owns
            fails += fl
    except Exception as e:
        print("TOOL ERROR:", repr(e)); return 2
    res["verdict"] = "FAIL" if fails else "PASS"; res["fails"] = fails
    if out_json: Path(out_json).write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "fails"}))
    for x in fails: print(x)
    print(res["verdict"])
    return 1 if fails else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
