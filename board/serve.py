"""The Story-Wrap board server: a local page on http://127.0.0.1:8771.

    python board/serve.py            (or the StoryWrap-BoardServer task from tools/register-tasks.ps1)

- Binds to 127.0.0.1 only. Every POST needs the per-start token embedded in the page, so no other site can press buttons.
- GET /            board/index.html          GET /data/*   board/data/*          GET /fonts/*   assets/fonts/* (Thmanyah)
- POST /api/reply  {id, action: approve|reject, text?}  -> ig_board.decide (a reply draft; sending is done by the Harvest task within its limits)
- POST /api/note   {platform, post, text}              -> monitor_board.add_note (work/board/notes.jsonl; Claude reads it with `monitor_board.py notes --pending`)
- POST /api/refresh                                     -> ig_board.write_all
Standard library only; it never touches the Instagram API itself.
"""
import json
import secrets
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import ig_board  # noqa: E402
import monitor_board  # noqa: E402

PORT = 8771
TOKEN = secrets.token_urlsafe(24)
TYPES = {".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8", ".json": "application/json; charset=utf-8", ".woff2": "font/woff2", ".css": "text/css", ".jpg": "image/jpeg"}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body: bytes, ctype="application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def file(self, base: Path, rel: str):
        p = (base / rel).resolve()
        if base.resolve() not in p.parents and p != base.resolve() or not p.is_file():
            return self.send(404, b'{"error":"not found"}')
        self.send(200, p.read_bytes(), TYPES.get(p.suffix, "application/octet-stream"))

    def host_ok(self) -> bool:
        """DNS-rebinding guard (security 2026-10-27, #4): only the page's own origin names may reach any route."""
        return (self.headers.get("Host") or "").lower() in (f"127.0.0.1:{PORT}", f"localhost:{PORT}")

    def do_GET(self):
        if not self.host_ok():
            return self.send(403, b'{"error":"forbidden host"}')
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            html = (ROOT / "board" / "index.html").read_text(encoding="utf-8").replace("__TOKEN__", TOKEN)
            return self.send(200, html.encode("utf-8"), TYPES[".html"])
        if path.startswith("/data/"):
            return self.file(ROOT / "board" / "data", path[len("/data/"):])
        if path.startswith("/fonts/"):
            return self.file(ROOT / "assets" / "fonts", path[len("/fonts/"):])
        self.send(404, b'{"error":"not found"}')

    def do_POST(self):
        if not self.host_ok():
            return self.send(403, b'{"error":"forbidden host"}')
        if self.headers.get("X-Board-Token") != TOKEN or self.headers.get("Origin") not in (None, f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"):
            return self.send(403, b'{"error":"forbidden"}')
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(min(n, 20000)) or b"{}")
            if self.path == "/api/reply":
                r = ig_board.decide(ROOT, str(body.get("id", "")), str(body.get("action", "")), body.get("text"))
                ig_board.write_all(ROOT)
                return self.send(200, json.dumps({"ok": True, "status": r["status"]}).encode())
            if self.path == "/api/note":
                r = monitor_board.add_note(ROOT, str(body.get("platform", "")), str(body.get("post", "general")), str(body.get("text", "")), env=monitor_board.load_env_safe())
                monitor_board.write(ROOT)
                return self.send(200, json.dumps({"ok": True, "id": r["id"]}).encode())
            if self.path == "/api/refresh":
                ig_board.write_all(ROOT)
                return self.send(200, b'{"ok":true}')
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            return self.send(400, json.dumps({"ok": False, "error": str(e)[:200]}).encode())
        self.send(404, b'{"error":"not found"}')


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    print(f"Story-Wrap board on http://127.0.0.1:{PORT}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
