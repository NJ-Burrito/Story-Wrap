# -*- coding: utf-8 -*-
"""Small NJ monogram on every frame (owner, 2026-10-25, CLAUDE.md "Small NJ logo on every frame"): a small, faint cream NJ mark in ONE corner of every episode file, ours only.
It is the last compose step. Two ways in, one result:

  stage_assemble   the overlay is one more input of the assemble filter graph (calm_compose.stage_assemble), so the final encode carries it, no extra generation
  apply(src, dst)  the same overlay over an already composed master (re-encodes the video once on NVENC, copies the audio stream bit for bit): how the approved E01C v5
                   gets its mark without any other change.

Where (measured against the calm layout, `place()` below and the WATERMARK-CLEAR gate):
  TOP-RIGHT, just inside the Reels safe area (calm_compose.SAFE 54, 270, 1026, 1250), rect (926, 282, 96, 96).
  - not top-left: the HUD plate lives there (calm_compose.HUD_XY 64, 280);
  - not the right-side button rail (Reels and Shorts: x from about 86 % of the width, y from about 45 % of the height down; a judgement, MAX_RAIL below);
  - not the bottom: the caption plates, the choice card and the app's own caption zone are there (y >= 1010; the safe area ends at 1250);
  - not above y 270: the app's own top bar (back arrow, camera, account) covers it.
Opacity 0.40 cream (#eee8dc, the glyph colour of assets/brand/mark-source.png) on a transparent ground: faint, readable on the dark ink ground, never competing with the story.

The mark is derived once from mark-source.png: the cream glyph is the alpha, the dark-red ground is dropped (`derive_mark`, written to assets/brand/nj-mark-cream.png).

Gate checks (calm_compose.stage_gate): WATERMARK-PRESENT (the mark is in the delivered file: sidecar spec + the mark's alpha correlates with the frame corner on sampled frames, and the
same corner of an un-marked master does not), WATERMARK-CLEAR (the rect misses every caption plate, HUD plate, lit choice plate, face box and card text box of the episode, and the UI zones).
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("STORYWRAP_ROOT") or TOOLS.parent)
W, H = 1080, 1920
SAFE = (54, 270, 1026, 1250)
MARK_PX = 96
MARK_XY = (SAFE[2] - 4 - MARK_PX, SAFE[1] + 12)          # (926, 282): top-right, inside the safe area
OPACITY = 0.40
OPACITY_RANGE = (0.25, 0.50)                              # faint, but visible: the gate refuses a mark outside this band
MARK_MAX_PX = 128                                         # a "small" mark
CREAM = (238, 232, 221)
SRC = ROOT / "assets" / "brand" / "mark-source.png"
MARK = ROOT / "assets" / "brand" / "nj-mark-cream.png"
PAD_PX = 12                                               # clear space kept between the mark and any plate, face or card text
# Phone UI zones the mark stays out of (x0, y0, x1, y1). The top and bottom bands are the safe area's own bounds; the rail is a judgement from the known layout of the
# Reels / Shorts action buttons (right edge, lower half): there is no official pixel spec.
UI_ZONES = {
    "top-bar": (0, 0, W, SAFE[1]),
    "bottom-caption-zone": (0, SAFE[3], W, H),
    "right-button-rail": (int(W * 0.86), int(H * 0.45), W, H),
}
# presence measurement (sampled frames): normalised correlation of the corner's local contrast with the mark's alpha
SAMPLES = 24
NCC_MIN = 0.35
PRESENT_SHARE_MIN = 0.80


def rect() -> dict:
    return {"x": MARK_XY[0], "y": MARK_XY[1], "w": MARK_PX, "h": MARK_PX}


def sha256(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def derive_mark(src: Path = SRC, out: Path = MARK, px: int = MARK_PX) -> Path:
    """Cream-on-transparent NJ mark from the profile picture: the alpha is how cream a pixel is (the two dark-red tones of the picture, its ground and the N's diagonal, drop out),
    cropped to the glyph's bounding box and fitted into a px x px square with a small margin. Deterministic."""
    import numpy as np
    from PIL import Image
    im = np.asarray(Image.open(src).convert("RGB")).astype(np.float32)
    lum = 0.2126 * im[..., 0] + 0.7152 * im[..., 1] + 0.0722 * im[..., 2]
    a = np.clip((lum - 120.0) / (205.0 - 120.0), 0.0, 1.0)
    # the picture's second tone (the N's diagonal and the lid of the J, dark red) comes back as a half-strength cream, so the N still reads as an N on a transparent ground
    from scipy import ndimage as ndi
    dark = lum < 34
    dark[:200], dark[800:], dark[:, :200], dark[:, 800:] = False, False, False, False
    dark = ndi.binary_opening(dark, iterations=3)
    lab, n = ndi.label(dark)
    sizes = ndi.sum(dark, lab, range(1, n + 1))
    tone = np.isin(lab, [i + 1 for i, s_ in enumerate(sizes) if s_ > 5000]).astype(np.float32)
    a = np.maximum(a, 0.45 * ndi.gaussian_filter(tone, 1.2))
    ys, xs = np.where(a > 0.3)
    box = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)
    glyph = a[box[1]:box[3], box[0]:box[2]]
    gh, gw = glyph.shape
    inner = px - 8
    s = inner / max(gh, gw)
    g = Image.fromarray((glyph * 255).astype(np.uint8), "L").resize((max(1, round(gw * s)), max(1, round(gh * s))), Image.LANCZOS)
    canvas = Image.new("L", (px, px), 0)
    canvas.paste(g, ((px - g.width) // 2, (px - g.height) // 2))
    rgba = Image.new("RGBA", (px, px), CREAM + (0,))
    rgba.putalpha(canvas)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    rgba.save(out)
    return out


def ensure_mark() -> Path:
    if not MARK.is_file():
        derive_mark()
    return MARK


def filter_chain(in_label: str, mark_idx: int, out_label: str) -> list[str]:
    """The ffmpeg filter lines that lay the mark over `in_label` (shared by assemble and apply): the mark input is faded to OPACITY and placed at MARK_XY."""
    return [f"[{mark_idx}:v]format=rgba,colorchannelmixer=aa={OPACITY:.3f}[wm{mark_idx}]",
            f"[{in_label}][wm{mark_idx}]overlay={MARK_XY[0]}:{MARK_XY[1]}:format=auto[{out_label}]"]


def spec() -> dict:
    return {"schema": "watermark/1", "corner": "top-right", "rect": rect(), "opacity": OPACITY, "colour": "#%02x%02x%02x" % CREAM, "mark": MARK.name, "mark_sha256": sha256(ensure_mark()),
            "source": SRC.name, "applied_by": "tools/watermark.py", "canvas": [W, H]}


def write_sidecar(workdir: Path) -> Path:
    p = Path(workdir) / "watermark.json"
    p.write_text(json.dumps(spec(), ensure_ascii=False, indent=1), encoding="utf-8")
    return p


# ------------------------------------------------------------------ apply to a finished master
def apply(src: Path, dst: Path, workdir: Path | None = None) -> dict:
    """Lay the mark over every frame of an existing episode file and write dst: video re-encoded once (h264_nvenc, the same settings as the assemble), audio stream copied bit for bit,
    same fps, size, duration and `+faststart`. Nothing else changes."""
    import compose as C
    src, dst = Path(src), Path(dst)
    if src.resolve() == dst.resolve() or (dst.exists() and dst.samefile(src)):
        raise ValueError(f"watermark.apply: dst is the source {src}: the approved master is never overwritten, write to another file")
    if "approved" in dst.name.lower():
        raise ValueError(f"watermark.apply: {dst.name} looks like an approved master: it is never an output")
    mark = ensure_mark()
    fl = ";".join(["[0:v]format=yuv420p[base]"] + filter_chain("base", 1, "vwm") + ["[vwm]format=yuv420p[vout]"])
    tmp = dst.with_name(dst.stem + ".wm-tmp.mp4")
    C.ff([*C.hw_in(), "-i", src, "-i", mark, "-filter_complex", fl, "-map", "[vout]", "-map", "0:a:0", "-c:a", "copy", "-r", "24", *C.venc_args(), "-movflags", "+faststart", tmp])
    os.replace(tmp, dst)
    if workdir:
        write_sidecar(Path(workdir))
    return {"dst": str(dst), "spec": spec()}


# ------------------------------------------------------------------ geometry (WATERMARK-CLEAR)
def _inter(a: dict, b: dict, pad: int = 0) -> bool:
    return not (a["x"] + a["w"] + pad <= b["x"] or b["x"] + b["w"] + pad <= a["x"] or a["y"] + a["h"] + pad <= b["y"] or b["y"] + b["h"] + pad <= a["y"])


def clear_problems(wm: dict | None, plates: list[dict], huds: list[dict], faces: list[dict], texts: list[dict]) -> list[str]:
    """WATERMARK-CLEAR: the mark's rect against every caption plate, HUD plate, face box and card text box (each a dict x, y, w, h, optional `what`), against the UI zones, and
    inside the canvas. Static on purpose: the mark is on every frame, so a plate that ever overlaps it counts. Returns 'detail' strings."""
    r = wm or rect()
    f = []
    if not (0 <= r["x"] and r["x"] + r["w"] <= W and 0 <= r["y"] and r["y"] + r["h"] <= H):
        f.append(f"mark rect {r} leaves the canvas")
    if max(r["w"], r["h"]) > MARK_MAX_PX:
        f.append(f"mark is {r['w']} x {r['h']} px: a small mark is at most {MARK_MAX_PX} px")
    for name, z in UI_ZONES.items():
        if _inter(r, {"x": z[0], "y": z[1], "w": z[2] - z[0], "h": z[3] - z[1]}):
            f.append(f"mark rect {r['x']},{r['y']},{r['w']},{r['h']} sits in the phone UI zone '{name}' {z}")
    for what, boxes in (("caption plate", plates), ("HUD plate", huds), ("face box", faces), ("card text", texts)):
        hits = [b for b in boxes if _inter(r, b, PAD_PX)]
        if hits:
            b = hits[0]
            f.append(f"{len(hits)} {what}(s) overlap the mark (within {PAD_PX} px), first {b.get('what', '')} at {b['x']:.0f},{b['y']:.0f},{b['w']:.0f},{b['h']:.0f}")
    return f


# ------------------------------------------------------------------ presence (WATERMARK-PRESENT)
def _alpha():
    import numpy as np
    from PIL import Image
    return np.asarray(Image.open(ensure_mark()).convert("RGBA"))[..., 3].astype("float32") / 255.0


def corner_ncc(gray, alpha=None) -> float:
    """Normalised correlation between the local contrast of the mark's rect in a grey frame (the rect minus a heavy blur of itself, so the ground's slow gradient drops out) and the
    mark's alpha. About 1 when the cream mark is there, about 0 on a clean ground."""
    import numpy as np
    from scipy.ndimage import gaussian_filter
    a = _alpha() if alpha is None else alpha
    x0, y0 = MARK_XY
    pad = 24
    crop = gray[y0 - pad:y0 + MARK_PX + pad, x0 - pad:min(x0 + MARK_PX + pad, W)].astype("float32")
    if crop.shape[1] < MARK_PX + pad:     # the mark runs to the right edge of the crop window: pad by edge replication
        crop = np.pad(crop, ((0, 0), (0, MARK_PX + 2 * pad - crop.shape[1])), mode="edge")
    hp = crop - gaussian_filter(crop, 8.0)
    inner = hp[pad:pad + MARK_PX, pad:pad + MARK_PX]
    av = a - a.mean()
    iv = inner - inner.mean()
    den = float(np.sqrt((av ** 2).sum() * (iv ** 2).sum()))
    return float((av * iv).sum() / den) if den > 1e-6 else 0.0


def sample_times(duration: float, n: int = SAMPLES) -> list[float]:
    return [round(duration * (i + 0.5) / n, 3) for i in range(n)]


def read_gray_frames(video: Path, times: list[float]):
    """Decode one grey 1080x1920 frame per time (ffmpeg seek, GPU decode when wanted)."""
    import numpy as np
    out = []
    for t in times:
        r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1", "-vf", f"scale={W}:{H},format=gray", "-f", "rawvideo", "-"],
                           capture_output=True)
        if r.returncode != 0 or len(r.stdout) != W * H:
            out.append(None)
        else:
            out.append(np.frombuffer(r.stdout, dtype=np.uint8).reshape(H, W))
    return out


def measure_present(video: Path, duration: float) -> dict:
    a = _alpha()
    times = sample_times(duration)
    vals = [corner_ncc(g, a) if g is not None else None for g in read_gray_frames(video, times)]
    ok = [v for v in vals if v is not None]
    share = sum(1 for v in ok if v >= NCC_MIN) / max(len(ok), 1)
    return {"samples": len(vals), "decoded": len(ok), "ncc_min": NCC_MIN, "share_present": round(share, 3), "ncc_median": round(sorted(ok)[len(ok) // 2], 3) if ok else None,
            "ncc_p10": round(sorted(ok)[len(ok) // 10], 3) if ok else None}


def present_problems(video: Path, duration: float, sidecar: Path | None) -> tuple[list[str], dict]:
    """WATERMARK-PRESENT: the sidecar says the policy mark (same rect, opacity in band, the mark's own hash) AND the mark's alpha shows in the delivered file's pixels on at least
    PRESENT_SHARE_MIN of the sampled frames. Returns (problems, metrics)."""
    f, m = [], {}
    if not sidecar or not Path(sidecar).is_file():
        f.append("watermark.json is missing next to the episode: the mark step did not run (stage_assemble or tools/watermark.py apply)")
    else:
        sc = json.loads(Path(sidecar).read_text(encoding="utf-8"))
        if sc.get("rect") != rect():
            f.append(f"watermark.json rect {sc.get('rect')} is not the policy rect {rect()}")
        if not (OPACITY_RANGE[0] <= float(sc.get("opacity", 0)) <= OPACITY_RANGE[1]):
            f.append(f"opacity {sc.get('opacity')} is outside the faint band {OPACITY_RANGE}")
        if sc.get("mark_sha256") != sha256(ensure_mark()):
            f.append("watermark.json names a different mark file than assets/brand/nj-mark-cream.png")
    m = measure_present(video, duration)
    if m["decoded"] < m["samples"]:
        f.append(f"only {m['decoded']} of {m['samples']} sampled frames could be decoded")
    if m["share_present"] < PRESENT_SHARE_MIN:
        f.append(f"the mark shows on {m['share_present']:.0%} of {m['decoded']} sampled frames (need {PRESENT_SHARE_MIN:.0%}; median correlation {m['ncc_median']}, threshold {NCC_MIN})")
    return f, m


def main(argv: list[str]) -> int:
    if argv[:1] == ["derive"]:
        print(derive_mark())
        return 0
    if argv[:1] == ["apply"] and len(argv) >= 3:
        print(json.dumps(apply(Path(argv[1]), Path(argv[2]), Path(argv[3]) if len(argv) > 3 else None), ensure_ascii=False, indent=1))
        return 0
    if argv[:1] == ["present"] and len(argv) >= 2:
        import compose as C
        f, m = present_problems(Path(argv[1]), C.duration(argv[1]), Path(argv[2]) if len(argv) > 2 else None)
        print(json.dumps({"problems": f, "metrics": m}, ensure_ascii=False, indent=1))
        return 1 if f else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.path.insert(0, str(TOOLS))
    sys.exit(main(sys.argv[1:]))
