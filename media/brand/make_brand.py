"""Story-Wrap brand set generator.

Draws the mark as SVG, renders PNG/ICO with headless Chromium, outlines the wordmark from the
installed Thmanyah serif display Black font (read only, never copied into the repo).

  PYTHONUTF8=1 uv run --with pillow --with playwright --with fonttools python media/brand/make_brand.py \
      [--out DIR] [--sheet SHEET.png] [--font PATH]

Default --out is the folder of this script. Needs `playwright install chromium` once.
"""
import argparse
import io
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAPER, INK, BURG, AMBER, CREAM, NIGHT = "#F6F1E8", "#17120F", "#7A1F3D", "#E39A4D", "#F1DDB5", "#130D0A"
OPEN = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">'


def find_font(explicit):
    if explicit:
        return Path(explicit)
    p = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/Windows/Fonts/thmanyahserifdisplay-Black.otf"
    if p.exists():
        return p
    sys.exit("Thmanyah serif display Black not found; pass --font")


def mark(uid, detail=True, square=False):
    """The mark on a 512 viewBox: an open book, an amber ribbon bookmark, on a burgundy tile."""
    rx = 0 if square else 112
    s = [OPEN, f'''<defs>
<linearGradient id="{uid}bg" x1="0.1" y1="0" x2="0.9" y2="1"><stop offset="0" stop-color="#A2315A"/><stop offset="0.55" stop-color="{BURG}"/><stop offset="1" stop-color="#3E0C20"/></linearGradient>
<linearGradient id="{uid}pg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFF8E8"/><stop offset="1" stop-color="#EAD2A0"/></linearGradient>
<linearGradient id="{uid}rb" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFC878"/><stop offset="1" stop-color="#D9822B"/></linearGradient>
<radialGradient id="{uid}gl" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="{AMBER}" stop-opacity="0.55"/><stop offset="1" stop-color="{AMBER}" stop-opacity="0"/></radialGradient>
<linearGradient id="{uid}rim" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#D98AA6" stop-opacity="0.7"/><stop offset="1" stop-color="{AMBER}" stop-opacity="0.55"/></linearGradient>
</defs>''', f'<rect width="512" height="512" rx="{rx}" fill="url(#{uid}bg)"/>']
    if detail and not square:
        s.append(f'<rect x="3" y="3" width="506" height="506" rx="109" fill="none" stroke="url(#{uid}rim)" stroke-width="3"/>')
    if detail:
        s.append(f'<ellipse cx="256" cy="262" rx="190" ry="150" fill="url(#{uid}gl)" opacity="0.5"/>')
    s.append('<g transform="translate(256 262) scale(1.2) translate(-256 -266)">')
    if detail:
        s.append('<ellipse cx="256" cy="392" rx="172" ry="14" fill="#1c0510" opacity="0.4"/>')
    left = "M256 196 C222 166 150 158 84 176 L84 360 C150 342 222 350 256 384 Z"
    right = "M256 196 C290 166 362 158 428 176 L428 360 C362 342 290 350 256 384 Z"
    s.append(f'<path d="{left}" fill="url(#{uid}pg)"/><path d="{right}" fill="url(#{uid}pg)"/>')
    if detail:
        s.append('<path d="M256 196 L256 384" stroke="#B98A52" stroke-opacity="0.55" stroke-width="3"/>')
        for y in (222, 252, 282):
            s.append(f'<path d="M118 {y} C150 {y - 6} 200 {y} 226 {y + 10}" stroke="{BURG}" stroke-opacity="0.35" stroke-width="9" stroke-linecap="round" fill="none"/>')
            s.append(f'<path d="M286 {y + 10} C312 {y} 362 {y - 6} 394 {y}" stroke="{BURG}" stroke-opacity="0.35" stroke-width="9" stroke-linecap="round" fill="none"/>')
    rib = "M226 150 H286 V352 L256 322 L226 352 Z"
    s.append(f'<path d="{rib}" fill="url(#{uid}rb)"/>')
    if detail:
        s.append('<path d="M226 150 H286" stroke="#FFE2B0" stroke-width="4"/><path d="M236 158 V336" stroke="#FFE9C4" stroke-opacity="0.55" stroke-width="5" stroke-linecap="round"/>')
    s.append('</g></svg>')
    return "\n".join(s)


def wordmark_path(font_path, text, size):
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.transformPen import TransformPen
    from fontTools.ttLib import TTFont
    f = TTFont(str(font_path))
    gs, cmap, upm = f.getGlyphSet(), f.getBestCmap(), f["head"].unitsPerEm
    sc, x, pen = size / upm, 0.0, SVGPathPen(gs)
    for ch in text:
        g = cmap[ord(ch)]
        gs[g].draw(TransformPen(pen, (sc, 0, 0, -sc, x, 0)))
        x += gs[g].width * sc
    return pen.getCommands(), x


def lockup(font_path, dark):
    d, w = wordmark_path(font_path, "Story-Wrap", 170)
    W = round(512 + 56 + w + 40)
    inner = mark("l", True).replace(OPEN, '<svg x="0" y="0" width="512" height="512" viewBox="0 0 512 512">')
    bg = NIGHT if dark else PAPER
    ink = CREAM if dark else INK
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} 512" width="{W}" height="512">'
           f'<rect width="{W}" height="512" fill="{bg}"/>{inner}'
           f'<path transform="translate({512 + 56} 310)" d="{d}" fill="{ink}"/></svg>')
    return svg, W


def render(page, svg, n, ss=1, transparent=True):
    from PIL import Image
    px = n * ss
    page.set_viewport_size({"width": px, "height": px})
    page.set_content('<html><body style="margin:0;background:transparent">'
                     + svg.replace('width="512" height="512"', f'width="{px}" height="{px}"', 1) + '</body></html>')
    img = Image.open(io.BytesIO(page.screenshot(omit_background=transparent))).convert("RGBA")
    return img.resize((n, n), Image.LANCZOS) if ss != 1 else img


def build(out, font_path, sheet):
    from PIL import Image
    from playwright.sync_api import sync_playwright
    out.mkdir(parents=True, exist_ok=True)
    full, simple, square = mark("a", True), mark("b", False), mark("c", True, square=True)
    (out / "favicon.svg").write_text(simple, encoding="utf-8")
    (out / "story-wrap-mark.svg").write_text(full, encoding="utf-8")
    lk_light, wl = lockup(font_path, False)
    lk_dark, _ = lockup(font_path, True)
    (out / "story-wrap-logo-light.svg").write_text(lk_light, encoding="utf-8")
    (out / "story-wrap-logo-dark.svg").write_text(lk_dark, encoding="utf-8")
    imgs, lk = {}, {}
    if True:
        with sync_playwright() as p:
            b = p.chromium.launch()
            try:
                pg = b.new_page()
                for n in (16, 32, 48):
                    imgs[n] = render(pg, simple, n, ss=8)
                imgs[192] = render(pg, full, 192, ss=2)
                imgs[512] = render(pg, full, 512)
                imgs[180] = render(pg, square, 180, ss=2, transparent=False)
                h = round(1000 * 512 / wl)
                for k, svg in (("light", lk_light), ("dark", lk_dark)):
                    pg.set_viewport_size({"width": 1000, "height": h})
                    pg.set_content('<html><body style="margin:0">' + svg.replace(f'width="{wl}" height="512"', f'width="1000" height="{h}"', 1) + '</body></html>')
                    lk[k] = Image.open(io.BytesIO(pg.screenshot())).convert("RGB")
            finally:
                b.close()
    for n, im in imgs.items():
        im.save(out / ("apple-touch-icon.png" if n == 180 else f"icon-{n}.png"))
    # real multi-size ICO: Pillow keeps each entry from append_images when sizes are given
    ico_sizes = [(16, 16), (32, 32), (48, 48)]
    imgs[48].save(out / "favicon.ico", format="ICO", sizes=ico_sizes, append_images=[imgs[16], imgs[32]])
    if sheet:
        make_sheet(Path(sheet), imgs, lk)


def make_sheet(path, imgs, lk):
    from PIL import Image, ImageDraw
    path.parent.mkdir(parents=True, exist_ok=True)
    W = 1400
    lh = lk["light"].height
    H = 820 + 2 * (lh + 20) + 20
    sheet = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(sheet)
    half = W // 2
    d.rectangle([half, 0, W, 800], fill=NIGHT)
    for off in (0, half):
        x = off + 40
        for n in (16, 32, 48, 180, 192):
            sheet.paste(imgs[n], (x, 40), imgs[n])
            x += n + 30
        for i, (n, z) in enumerate(((16, 16), (32, 8))):
            zi = imgs[n].resize((n * z, n * z), Image.NEAREST)
            sheet.paste(zi, (off + 40, 260 if i == 0 else 530), zi)
        big = imgs[512].resize((300, 300), Image.LANCZOS)
        sheet.paste(big, (off + 340, 300), big)
    sheet.paste(lk["light"], (40, 820))
    sheet.paste(lk["dark"], (40, 820 + lh + 20))
    sheet.save(path)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE))
    ap.add_argument("--sheet")
    ap.add_argument("--font")
    a = ap.parse_args()
    build(Path(a.out), find_font(a.font), a.sheet)
    print("ok")
