# /// script
# requires-python = ">=3.11"
# dependencies = ["playwright"]
# ///
"""Drive a shot's recording page in GPU Chromium. drive(url, expr) opens the page, waits for Shot.ready, evaluates
`expr` (a JS expression returning a value or a promise) and closes the browser before returning (no leftovers).
Examples of expr: "Shot.diag()", "Shot.record({data:false})", "Shot.record({video:false})", "Shot.still(30)".
Page errors and console errors are returned with the result; the caller decides whether they fail the stage."""
from __future__ import annotations
import json, sys

GPU_ARGS = ["--use-angle=d3d11", "--enable-gpu-rasterization", "--ignore-gpu-blocklist", "--enable-unsafe-swiftshader=false"]


def drive(url: str, expr: str, timeout_s: float = 900, tag: str = "story-wrap-shot") -> dict:
    from playwright.sync_api import sync_playwright
    errs: list[str] = []
    res = None
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True, args=GPU_ARGS)
        try:
            pg = b.new_page(viewport={"width": 400, "height": 600})
            pg.on("pageerror", lambda e: errs.append("pageerror: " + str(e)))
            pg.on("console", lambda m: errs.append(m.type + ": " + m.text) if m.type in ("error", "warning") else None)
            pg.set_default_timeout(timeout_s * 1000)
            pg.goto(url, wait_until="load")
            pg.evaluate("Shot.ready")
            res = pg.evaluate(f"(async () => {{ const r = await ({expr}); return r === undefined ? null : r; }})()")
        finally:
            b.close()
    return {"result": res, "errors": errs[:30]}


if __name__ == "__main__":
    print(json.dumps(drive(sys.argv[1], sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else 900), ensure_ascii=False)[:4000])
