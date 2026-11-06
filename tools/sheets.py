# /// script
# requires-python = ">=3.11"
# dependencies = ["playwright", "pillow", "numpy"]
# ///
"""Catalogue sheet renderer: draws a character's (or a world's) sheets from its MODULE, in black-and-white ink only.

  uv run tools/sheets.py character <id> [--version v4] [--out DIR] [--no-png]
  uv run tools/sheets.py world <id>     [--version v1] [--out DIR] [--no-png]

Character sheets (catalogue/characters/<id>/<version>/sheets/): 01-shapes, 02-mannequin, 03-sketch, 04-turnaround,
05-expressions (the 8 bible emotions), 06-hands-grips, 07-face (nose, lips, visemes), 08-props.
World sheets (catalogue/environments/<id>/<version>/sheets/): w1-establishing, w2-locations, w3-props, w4-materials.
Each sheet is written as SVG (vector) and as a 300 dpi PNG (A4 landscape, 3508 x 2480, greyscale), plus sheets.json
(measurements read from the drawn geometry, captions-in-sheet, regions, sha256 of every file) that `tools/artbook.py check` reads.

The drawing code is tools/render/sheets.js (generic) + the module's `sheet` block (tools/render/characters/<id>.js,
tools/render/worlds/<id>.js; contract in the README next to each). GPU Chromium, one page, closed before exit.
Exit 0 = ok, 1 = a sheet failed, 2 = usage or tool error."""
from __future__ import annotations
import argparse, hashlib, json, re, sys, threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
GPU_ARGS = ["--use-angle=d3d11", "--enable-gpu-rasterization", "--ignore-gpu-blocklist", "--enable-unsafe-swiftshader=false"]
SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")
PAGE_W, PAGE_H, DSF = 1754, 1240, 2     # A4 landscape at 150 dpi in SVG units, x2 = 3508 x 2480 px = A4 at 300 dpi
FONT_FACES = [("thmanyahsans", "Regular", 400), ("thmanyahsans", "Medium", 500), ("thmanyahsans", "Bold", 700), ("thmanyahserifdisplay", "Bold", 700),
              ("thmanyahserifdisplay", "Black", 900), ("thmanyahseriftext", "Regular", 400), ("thmanyahseriftext", "Bold", 700)]


def font_css(base: str = "") -> str:
    return "\n".join(f'@font-face{{font-family:"{fam}";src:url("{base}/assets/fonts/{fam}-{w}.woff2") format("woff2");font-weight:{wt}}}' for fam, w, wt in FONT_FACES)


def page_html(kind: str, mid: str, world_for_char: str | None = None) -> str:
    libs = ["core.js", "geom2d.js", "svgctx.js"]
    if kind == "world":
        libs += [f"worlds/{mid}.js"]
    else:
        libs += ["face.js", "hands.js", "write.js", f"characters/{mid}.js"]
    libs += ["sheets.js"]
    scripts = "".join(f'<script src="/tools/render/{u}"></script>' for u in libs)
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>sheets {kind} {mid}</title>
<style>{font_css()}</style></head><body>
<script>const SHOT = {{id: "sheets", fps: 24, duration_s: 1, canvas: [1080, 1920]}};</script>
<canvas id="shot" width="1080" height="1920" style="display:none"></canvas>
{scripts}
<script>window.__ready = true;</script></body></html>"""


def make_handler(page: str):
    class H(SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(ROOT), **k)

        def log_message(self, *a):
            pass

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def do_GET(self):
            if self.path.split("?")[0] == "/__sheets.html":
                b = page.encode("utf-8")
                self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(b))); self.end_headers()
                self.wfile.write(b)
                return
            if self.path.split("?")[0] == "/__blank.html":
                b = b"<!doctype html><html><head><meta charset='utf-8'></head><body style='margin:0;background:#fff'></body></html>"
                self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(b))); self.end_headers()
                self.wfile.write(b)
                return
            super().do_GET()
    return H


def rel(p: Path) -> str:   # --out may point outside the repo (tests, scratch)
    try:
        return p.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(p)


def sha(b: bytes) -> str:
    return "sha256:" + hashlib.sha256(b).hexdigest()[:16]


def default_out(kind: str, mid: str, version: str) -> Path:
    base = ROOT / "catalogue" / ("characters" if kind == "character" else "environments") / mid / version / "sheets"
    return base


def module_version(kind: str, mid: str, version: str | None) -> str:
    if version:
        return version
    src = (TOOLS / "render" / ("characters" if kind == "character" else "worlds") / f"{mid}.js").read_text(encoding="utf-8")
    m = re.search(r"sheet_version:\s*\"(v\d+)\"", src)
    if not m:
        raise SystemExit(f"module {mid} declares no sheet_version; pass --version")
    return m.group(1)


def png_from_svg(pg, base: str, svg: str, w: int, h: int, out: Path):
    from PIL import Image
    import io
    pg.set_viewport_size({"width": w, "height": h})
    pg.goto(base + "/__blank.html", wait_until="load")
    pg.set_content(f"<style>{font_css()} html,body{{margin:0;background:#fff}} svg{{display:block}}</style>{svg}", wait_until="load")
    pg.evaluate("document.fonts.ready")
    pg.evaluate("Promise.all([...document.fonts].map(f => f.load().catch(() => null)))")
    png = pg.screenshot(type="png", clip={"x": 0, "y": 0, "width": w, "height": h})
    im = Image.open(io.BytesIO(png)).convert("L")
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out, format="PNG", optimize=True, dpi=(300, 300))
    return im.size


def run(kind: str, mid: str, version: str | None, out: Path | None, png: bool, log=print) -> int:
    if not SAFE_ID.match(mid):
        log(f"FAIL [SHEETS-USAGE] bad id {mid!r}"); return 2
    modp = TOOLS / "render" / ("characters" if kind == "character" else "worlds") / f"{mid}.js"
    if not modp.is_file():
        log(f"FAIL [SHEETS-MODULE] no {kind} module at {modp.relative_to(ROOT).as_posix()}: an Opus artist builds it first (pipelines/ARTBOOK.md step 2)"); return 1
    try:   # imported after the usage and module checks, so a bad id or a missing module is reported even where playwright is not installed
        from playwright.sync_api import sync_playwright
    except ImportError:
        log("FAIL [SHEETS-TOOL] playwright is not installed in this interpreter; run it as `uv run tools/sheets.py ...` (the script header lists the dependencies)"); return 2
    version = module_version(kind, mid, version)
    out = out or default_out(kind, mid, version)
    out.mkdir(parents=True, exist_ok=True)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(page_html(kind, mid)))
    th = threading.Thread(target=srv.serve_forever, daemon=True); th.start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    errs: list[str] = []
    result = None
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch(headless=True, args=GPU_ARGS)
            try:
                pg = b.new_page(viewport={"width": 800, "height": 600})
                pg.on("pageerror", lambda e: errs.append("pageerror: " + str(e)))
                pg.on("console", lambda m: errs.append(m.type + ": " + m.text) if m.type == "error" else None)
                pg.set_default_timeout(300000)
                pg.goto(base + "/__sheets.html", wait_until="load")
                pg.evaluate("document.fonts.ready")
                result = pg.evaluate(f"(async () => await Sheets.run({json.dumps(kind)}, {json.dumps(mid)}))()")
                if result and png and not errs:
                    cx = b.new_context(viewport={"width": PAGE_W, "height": PAGE_H}, device_scale_factor=DSF)
                    pg2 = cx.new_page()
                    for s in result["sheets"]:
                        size = png_from_svg(pg2, base, s["svg"], PAGE_W, PAGE_H, out / (s["id"] + ".png"))
                        s["png_px"] = list(size)
                    cx.close()
            finally:
                b.close()
    except Exception as e:   # noqa: BLE001
        log(f"FAIL [SHEETS-RENDER] {type(e).__name__}: {str(e)[:300]}"); errs.append(str(e))
        return 1
    finally:
        srv.shutdown(); srv.server_close()
    if errs or not result:
        for e in errs[:6]:
            log("FAIL [SHEETS-PAGE] " + e[:300])
        return 1
    files = []
    for s in result["sheets"]:
        svg = s.pop("svg")
        (out / (s["id"] + ".svg")).write_text(svg, encoding="utf-8")
        ent = {"id": s["id"], "title": s["title"], "svg": s["id"] + ".svg", "svg_sha": sha(svg.encode("utf-8")), "svg_size": [PAGE_W, PAGE_H],
               "regions": s.get("regions", {}), "labels": s.get("labels", [])}
        pp = out / (s["id"] + ".png")
        if png and pp.is_file():
            ent.update({"png": s["id"] + ".png", "png_sha": sha(pp.read_bytes()), "png_px": s.get("png_px"), "dpi": 300})
        files.append(ent)
    meta = {"kind": kind, "id": mid, "module": modp.relative_to(ROOT).as_posix(), "module_sha": sha(modp.read_bytes()), "version": version,
            "page": {"w": PAGE_W, "h": PAGE_H, "dpi_svg": 150, "dpi_png": 300}, "ink": "black, white and greys only",
            "measures": result["measures"], "module_summary": result["module"], "sheets": files}
    (out / "sheets.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"OK {kind} {mid} {version}: {len(files)} sheets -> {rel(out)} ({'svg + 300 dpi png' if png else 'svg only'})")
    for f in files:
        log(f"  {f['id']}  {f.get('png_px', '')}")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("kind", choices=["character", "world"])
    ap.add_argument("id")
    ap.add_argument("--version")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--no-png", action="store_true")
    a = ap.parse_args(argv)
    return run(a.kind, a.id, a.version, a.out, not a.no_png)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
