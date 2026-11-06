# -*- coding: utf-8 -*-
"""Grid poster (owner, 2026-10-28, R-501): ONE template for the first frame of every episode and for the Instagram grid cover.

  - 1080x1920 (a Reel cover), every piece of content inside the centre 3:4 crop (1080x1440, y 240..1680) that the profile grid shows;
  - the episode's strongest drawn frame full bleed: the first scene with an `event` in calm-plan.json (fallback: the first scene), a frame at 60 % of its rendered shot;
  - a dark gradient band under the text, the episode numeral big (Arabic-Indic digits), a 1 to 3 word hook (plan `cover_hook`, fallback the first clause of `post_caption`),
    the series name small: always in the SAME place, SAME colours (cream text, one gold accent), Thmanyah only, no tashkeel;
  - readable at grid size (a 360 px wide tile): numeral >= 250 px, hook >= 90 px, series >= 48 px at 1080 px width.

The assembled episode starts on this poster (calm_compose.stage_assemble holds it for POSTER_HOLD_S, then fades into the normal opening) so frame 0 is never black;
the same png (cover.png, plus cover.jpg for the platforms that want a JPEG) is the cover every uploader sends.

  uv run tools/grid_poster.py render <EP> [--out work/covers/<EP>-grid.png]
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("STORYWRAP_ROOT") or TOOLS.parent)
sys.path.insert(0, str(TOOLS))
from arabic_display import has_tashkeel   # noqa: E402

W, H = 1080, 1920
CROP = (0, 240, 1080, 1680)             # the 3:4 centre crop the IG profile grid shows (1080 x 1440)
FRAME_AT = 0.60                         # the share of the chosen shot the background frame is taken at
POSTER_HOLD_S = 0.5                     # the poster is the first frame of the episode and stays this long before it fades into the opening
POSTER_FADE_S = 0.25
LUMA_FLOOR = 40.0                       # COVER-FRAME0: frame 0 of the episode must be brighter than this mean luma (0..255); a black fade-in is ~0
MATCH_MAX = 12.0                        # COVER-FRAME0: mean absolute difference (0..255) allowed between frame 0 and the poster
HOOK_MAX_WORDS = 3
EMOJI = "[🌀-🫿☀-➿️]+"
AR_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
CREAM, GOLD, INK = "#f3ecdc", "#f2c14e", "#0b0907"
# Every box is right-aligned at x = RIGHT and stacked in the lower part of the crop; nothing sits in the top-right where the NJ mark is (watermark.rect()).
RIGHT, LEFT = 1016, 64
BOXES = {                                # name: (x0, y0, x1, y1, font_px) , declared once: the HTML below is built from it and the test reads it
    "numeral": (LEFT, 1130, RIGHT, 1450, 340),
    "hook": (LEFT, 1450, RIGHT, 1570, 96),
    "series": (LEFT, 1578, RIGHT, 1642, 52),
}
BAND_TOP = 900                           # the gradient starts here and is solid at the bottom of the crop


def fail(code: str, msg: str):
    raise SystemExit(f"FAIL [{code}] {msg}")


# ---------------------------------------------------------------- content
def ar_num(n) -> str:
    return str(n).translate(AR_DIGITS)


def episode_number(ep_id) -> int | None:
    m = re.match(r"E(\d+)", str(ep_id or ""))
    return int(m.group(1)) if m else None


def hook_text(plan: dict) -> str:
    """The cover hook, 1 to 3 words: plan `cover_hook`, else the first clause of `post_caption` (after the title line and its emoji). Never invented."""
    h = str(plan.get("cover_hook") or "").strip()
    if not h:
        first = next((l.strip() for l in str(plan.get("post_caption") or "").splitlines() if l.strip()), "")
        parts = re.split(EMOJI, first)
        clause = parts[-1] if len(parts) > 1 else first      # the title line is "الحلقة ٢ | the series 🕯️ <clause>": what follows the emoji
        h = re.split(r"[،,.:؛!?؟|]", clause.strip())[0]
    h = re.sub(EMOJI, "", h)
    h = " ".join(h.split()[:HOOK_MAX_WORDS])
    if not h:
        fail("POSTER-HOOK", "no cover_hook in the plan and no usable clause in post_caption")
    if has_tashkeel(h):
        fail("POSTER-TASHKEEL", f"the cover hook «{h}» carries tashkeel")
    return h


def pick_scene(plan: dict) -> dict:
    """The first scene with an `event` (an action scene SHOWN, Format v2), else the first scene."""
    scenes = plan.get("scenes") or []
    if not scenes:
        fail("POSTER-SCENE", "the plan has no scenes")
    return next((s for s in scenes if s.get("event")), scenes[0])


def shot_video(root: Path, ep: str, scene_id: str) -> Path:
    return Path(root) / "work" / "shots" / f"{ep}-{scene_id}" / "out" / f"{ep}-{scene_id}.mp4"


def probe_dur(p: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)], capture_output=True, text=True)
    return float((r.stdout or "0").strip() or 0)


def extract_frame(video: Path, out: Path, frac: float = FRAME_AT) -> Path:
    if not video.is_file():
        fail("POSTER-SHOT", f"{video} is missing: the shot is rendered before the poster")
    t = max(0.0, probe_dur(video) * frac)
    out.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1", "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}", str(out)],
                       capture_output=True, text=True)
    if r.returncode != 0 or not out.is_file():
        fail("POSTER-FRAME", f"ffmpeg could not read a frame of {video}: {(r.stderr or '').strip()[:200]}")
    return out


# ---------------------------------------------------------------- layout
def box_problems(boxes: dict | None = None) -> list[str]:
    """Every declared box lies inside the 3:4 crop, clear of the NJ mark's rect, and is big enough to read at grid size (a tile 1/3 of the width)."""
    import watermark as WM
    boxes = boxes or BOXES
    out = []
    r = WM.rect()
    for name, (x0, y0, x1, y1, px) in boxes.items():
        if x0 < CROP[0] or x1 > CROP[2] or y0 < CROP[1] or y1 > CROP[3]:
            out.append(f"{name} box {(x0, y0, x1, y1)} leaves the 3:4 crop {CROP}")
        if not (x1 <= r["x"] - WM.PAD_PX or x0 >= r["x"] + r["w"] + WM.PAD_PX or y1 <= r["y"] - WM.PAD_PX or y0 >= r["y"] + r["h"] + WM.PAD_PX):
            out.append(f"{name} box touches the NJ mark")
        if px / 3 < {"numeral": 80, "hook": 28, "series": 16}.get(name, 0):
            out.append(f"{name} is {px}px: {px / 3:.0f} px on a 360 px grid tile is too small")
    return out


def poster_html(bg_uri: str, numeral: str, hook: str, series: str) -> str:
    import calm_cards as CCARD

    def esc(t):
        return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def abs_(name, css):
        x0, y0, x1, y1, px = BOXES[name]
        return f"#{name}{{position:absolute;left:{x0}px;top:{y0}px;width:{x1 - x0}px;height:{y1 - y0}px;font-size:{px}px;{css}}}"
    css = (CCARD.font_css() + f"*{{margin:0;padding:0;box-sizing:border-box}}html,body{{width:{W}px;height:{H}px;background:{INK};overflow:hidden}}"
           f"body{{direction:rtl;font-family:'thmanyahsans';color:{CREAM}}}"
           f"#bg{{position:absolute;inset:0;width:{W}px;height:{H}px;object-fit:cover}}"
           f"#band{{position:absolute;left:0;right:0;top:{BAND_TOP}px;bottom:0;background:linear-gradient(to bottom,rgba(11,9,7,0) 0%,rgba(11,9,7,.78) 42%,rgba(11,9,7,.94) 100%)}}"
           + abs_("numeral", f"font-family:'thmanyahserifdisplay';font-weight:900;line-height:1;color:{GOLD};text-align:right;white-space:nowrap")
           + abs_("hook", f"font-weight:900;line-height:1.2;color:{CREAM};text-align:right;white-space:nowrap;text-shadow:0 2px 14px rgba(0,0,0,.6)")
           + abs_("series", f"font-weight:700;line-height:1.2;color:{CREAM};opacity:.88;text-align:right;white-space:nowrap"))
    return (f'<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><style>{css}</style></head><body>'
            f'<img id="bg" src="{bg_uri}"><div id="band"></div><div id="numeral">{esc(numeral)}</div><div id="hook">{esc(hook)}</div><div id="series">{esc(series)}</div></body></html>')


def render_poster(frame_png: Path, numeral: str, hook: str, series: str, out_png: Path) -> dict:
    """Render the poster page, measure the real text boxes and check them against the crop (a text wider than its box fails here, not on the grid)."""
    from playwright.sync_api import sync_playwright
    import calm_cards as CCARD
    bad = box_problems()
    if bad:
        fail("POSTER-LAYOUT", "; ".join(bad))
    for k, v in (("numeral", numeral), ("hook", hook), ("series", series)):
        if has_tashkeel(v):
            fail("POSTER-TASHKEEL", f"{k} «{v}» carries tashkeel")
    CCARD.need_fonts()
    out_png = Path(out_png).resolve()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    page = out_png.with_suffix(".poster.html")
    page.write_text(poster_html(Path(frame_png).resolve().as_uri(), numeral, hook, series), encoding="utf-8")
    res = {}
    with sync_playwright() as pw:
        b = pw.chromium.launch(args=["--allow-file-access-from-files"])
        try:
            pg = b.new_page(viewport={"width": W, "height": H})
            pg.goto(page.as_uri())
            specs = ("700 40px thmanyahsans", "900 40px thmanyahsans", "900 40px thmanyahserifdisplay")
            pg.evaluate("Promise.all(%s.map(s => document.fonts.load(s, 'هدى'))).then(() => 1)" % json.dumps(list(specs)))
            if not all(pg.evaluate(f"document.fonts.check('{s}')") for s in specs):
                fail("POSTER-FONT", "a Thmanyah face did not load; no fallback face is allowed")
            res["boxes"] = pg.evaluate("""() => ['numeral','hook','series'].map(id => { const e = document.getElementById(id), rg = document.createRange(); rg.selectNodeContents(e);
                const r = rg.getBoundingClientRect(); return {id, x0: r.left, y0: r.top, x1: r.right, y1: r.bottom}; })""")
            pg.screenshot(path=str(out_png))
        finally:
            b.close()
    try:
        page.unlink()
    except OSError:
        pass
    over = [f"{m['id']} text {round(m['x0'])},{round(m['y0'])},{round(m['x1'])},{round(m['y1'])} leaves its box" for m in res["boxes"]
            if m["x0"] < BOXES[m["id"]][0] - 1 or m["x1"] > BOXES[m["id"]][2] + 1 or m["y0"] < CROP[1] or m["y1"] > CROP[3]]
    if over:
        fail("POSTER-OVERFLOW", "; ".join(over) + " (shorten the hook: at most 3 words)")
    jpg = out_png.with_suffix(".jpg")
    from PIL import Image
    Image.open(out_png).convert("RGB").save(jpg, quality=95)
    return {"png": str(out_png), "jpg": str(jpg), "boxes": res["boxes"]}


def build(ep: str, root: Path = ROOT, out_png: Path | None = None, plan_path: Path | None = None, scratch: Path | None = None) -> dict:
    """Make the poster of an episode: pick the scene, take the frame, render. Returns render_poster's result plus {scene, hook, numeral}."""
    root = Path(root)
    plan_path = plan_path or next(iter(sorted((root / "bible" / "series").glob(f"*/episodes/{ep}/calm-plan.json"))), None)
    if not plan_path or not Path(plan_path).is_file():
        fail("POSTER-PLAN", f"no calm-plan.json for {ep}")
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    sc = pick_scene(plan)
    out_png = Path(out_png) if out_png else root / "work" / "covers" / f"{ep}-grid.png"
    scratch = Path(scratch) if scratch else out_png.parent
    frame = extract_frame(shot_video(root, ep, sc["id"]), scratch / f"{ep}-poster-frame.png")
    n = episode_number(plan.get("episode") or ep)
    numeral = ar_num(n) if n else ar_num(plan.get("day", ""))
    hook = hook_text(plan)
    series = str(plan.get("series_name") or "the series")
    r = render_poster(frame, numeral, hook, series, out_png)
    return {**r, "scene": sc["id"], "hook": hook, "numeral": numeral}


# ---------------------------------------------------------------- frame-0 check
def frame0_check(video: Path, poster: Path) -> tuple[bool, str]:
    """COVER-FRAME0: frame 0 of the episode is not near-black and matches the poster. Returns (ok, detail)."""
    import numpy as np
    from PIL import Image
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-vf", f"scale={W}:{H}", "-"], capture_output=True)
    if r.returncode != 0 or len(r.stdout) != W * H * 3:
        return False, f"frame 0 of {Path(video).name} could not be decoded"
    f0 = np.frombuffer(r.stdout, np.uint8).reshape(H, W, 3).astype(np.float32)
    luma = float((0.2126 * f0[..., 0] + 0.7152 * f0[..., 1] + 0.0722 * f0[..., 2]).mean())
    p = np.asarray(Image.open(poster).convert("RGB").resize((W, H)), np.float32)
    diff = float(np.abs(f0 - p).mean())
    probs = []
    if luma <= LUMA_FLOOR:
        probs.append(f"frame 0 is near-black (mean luma {luma:.1f} <= {LUMA_FLOOR:g})")
    if diff > MATCH_MAX:
        probs.append(f"frame 0 does not match the grid poster (mean difference {diff:.1f} > {MATCH_MAX:g})")
    return not probs, "; ".join(probs) or f"frame 0 is the grid poster (mean luma {luma:.1f}, difference {diff:.1f})"


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Story-Wrap grid poster")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("render"); p.add_argument("ep"); p.add_argument("--out")
    a = ap.parse_args(argv)
    r = build(a.ep, ROOT, Path(a.out) if a.out else None)
    print(json.dumps({k: v for k, v in r.items() if k != "boxes"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
