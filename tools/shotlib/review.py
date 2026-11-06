"""Review stage: frame-by-frame contact sheets cropped from the RECORDED video, positioned by the rig trace, for the
human/agent look pass (hands, faces, props, and every Nth full frame). This is a look, not a gate: the numbers are in the gate stage.
Output: review/sheet-hands.png, sheet-faces.png, sheet-props.png, sheet-frames.png, index.json."""
from __future__ import annotations
import json, subprocess
from pathlib import Path


def stream_frames(video: Path, want: set[int], w: int, h: int):
    """Yield (index, HxWx3 uint8 array) for the wanted frame indexes, decoding sequentially on NVDEC (frames not wanted are dropped)."""
    import numpy as np
    cmd = ["ffmpeg", "-v", "error", "-hwaccel", "cuda", "-threads", "2", "-i", str(video), "-an", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    n, size = 0, w * h * 3
    try:
        while True:
            buf = p.stdout.read(size)
            if len(buf) < size:
                break
            if n in want:
                yield n, np.frombuffer(buf, np.uint8).reshape(h, w, 3).copy()
            n += 1
    finally:
        p.stdout.close(); p.wait()


def _crop(img, cx, cy, half):
    from PIL import Image
    h, w = img.shape[:2]
    x0, y0 = int(round(cx - half)), int(round(cy - half))
    im = Image.fromarray(img)
    return im.crop((x0, y0, x0 + 2 * half, y0 + 2 * half))   # PIL pads outside the frame with black


def _pts(v):
    if v is None: return None
    if isinstance(v, dict):
        if "x" in v and "y" in v: return [v["x"], v["y"]]
        return None
    if isinstance(v, (list, tuple)) and len(v) >= 2 and all(isinstance(a, (int, float)) for a in v[:2]): return [v[0], v[1]]
    return None


def anchors_for(frame: dict) -> dict:
    """Crop centres (canvas px) for this trace frame: {'hand_L','hand_R','face','card','tag','pen'} where known."""
    out: dict = {}
    cp, an, hp = frame.get("contact_points") or {}, frame.get("anchors") or {}, frame.get("hand_pose") or {}
    grip = {"L": cp.get("pen_grip") or cp.get("hand_L"), "R": cp.get("card_press") or cp.get("bag_tag_grip") or cp.get("hand_R")}
    for sd, h in hp.items():
        wr = _pts(h.get("wrist_px")); g = _pts(grip.get(sd))
        if wr and g: out["hand_" + sd] = [(wr[0] + g[0]) / 2, (wr[1] + g[1]) / 2]
        elif wr: out["hand_" + sd] = wr
        elif g: out["hand_" + sd] = g
    if frame.get("view") not in ("top", "pov") and an.get("cap_band_front") and an.get("neck_front"):
        a, b = an["cap_band_front"], an["neck_front"]
        out["face"] = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]
        out["face_half"] = max(150, int(1.25 * ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** .5))
    elif frame.get("view") not in ("top", "pov") and an.get("face_center"):   # multi-actor traces (trace-multi.js)
        out["face"] = an["face_center"]; out["face_half"] = 170
    for pr in frame.get("props") or []:
        q = pr.get("quad_px")
        if q:
            xs, ys = [p[0] for p in q], [p[1] for p in q]
            out["card"] = [(min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2]
            out["card_half"] = int(max(max(xs) - min(xs), max(ys) - min(ys)) * .6) + 20
    t = _pts(cp.get("tag_hole")) or _pts(cp.get("bag_tag_grip"))
    if t: out["tag"] = t
    if cp.get("pen_grip"): out["pen"] = cp["pen_grip"]
    return out


def sheet(tiles, cols, tw, label_h=16, path: Path | None = None):
    from PIL import Image, ImageDraw
    if not tiles: return None
    rows = (len(tiles) + cols - 1) // cols
    th = tiles[0][0].height * tw // tiles[0][0].width
    sh = Image.new("RGB", (cols * tw, rows * (th + label_h)), "white")
    d = ImageDraw.Draw(sh)
    for i, (im, lab) in enumerate(tiles):
        x, y = (i % cols) * tw, (i // cols) * (th + label_h)
        sh.paste(im.resize((tw, th)), (x, y + label_h)); d.text((x + 3, y + 2), lab, fill="black")
    if path: sh.save(path)
    return sh


def run(video: Path, trace_path: Path, out_dir: Path, canvas, cfg: dict) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    tr = json.loads(Path(trace_path).read_text(encoding="utf-8"))
    chars = {cid: c["frames"] for cid, c in tr["characters"].items()}   # one character: labels as before; several: each label starts with the actor id
    many = len(chars) > 1
    ch = next(iter(chars.values()))
    W, H = canvas
    ev = lambda k, d: max(1, int(cfg.get(k, d)))
    he, fe, pe, ae = ev("hands_every", 3), ev("faces_every", 6), ev("props_every", 6), ev("frames_every", 12)
    want = {i for i in range(len(ch)) if i % he == 0 or i % fe == 0 or i % pe == 0 or i % ae == 0}
    hands, faces, props, full = [], [], [], []
    for n, img in stream_frames(video, want, W, H):
        for cid, frs in chars.items():
            if n >= len(frs): continue
            pre = f"{cid} " if many else ""
            a = anchors_for(frs[n])
            if n % he == 0:
                for sd in ("L", "R"):
                    if "hand_" + sd in a: hands.append((_crop(img, *a["hand_" + sd], 210), f"{pre}f{n} {sd}"))
            if n % fe == 0 and "face" in a:
                faces.append((_crop(img, *a["face"], a["face_half"]), f"{pre}f{n}"))
            if n % pe == 0:
                for k in ("card", "tag", "pen"):
                    if k in a: props.append((_crop(img, *a[k], a.get(k + "_half", 190)), f"{pre}f{n} {k}"))
        if n % ae == 0:
            from PIL import Image
            full.append((Image.fromarray(img), f"f{n}"))
    res = {}
    for name, tiles, cols, tw in (("hands", hands, 6, 240), ("faces", faces, 6, 240), ("props", props, 6, 240), ("frames", full, 9, 160)):
        p = out_dir / f"sheet-{name}.png"
        s = sheet(tiles, cols, tw, path=p)
        res[name] = {"file": p.name if s else None, "tiles": len(tiles), "labels": [lab for _, lab in tiles][:200]}
    res["every"] = {"hands": he, "faces": fe, "props": pe, "frames": ae}
    (out_dir / "index.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res
