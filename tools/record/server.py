# /// script
# requires-python = ">=3.11"
# ///
"""Local recorder for a shot (127.0.0.1 only). Serves the repo root read-only and accepts what the page's record() posts:
POST /start {name,from}   start ffmpeg: PNG pipe -> h264_nvenc (GPU), <fps> fps, yuv420p, threads 2
POST /frame?i=N           one PNG frame; frames are written strictly in order of the counter, never by arrival time
POST /finish              close the encoder, write <name>.encode.json {frames, ffmpeg_exit}
POST /mask?kind=text|shadow|line&i=N[&actor=ID]   mask PNG -> <out>/masks/<kind>/[<actor>/]NNNN.png
POST /trace               rig trace JSON -> <out>/rig-trace.json
POST /png?name=X          a check frame -> <out>/check/X.png
GET  /quit                stop the server
Library use (tools/shot.py): srv = start(root, out_dir, fps); ...; srv.stop().  CLI: uv run tools/record/server.py <root> <out-dir> [port] [fps]"""
from __future__ import annotations
import json, re, subprocess, sys, threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

SAFE = re.compile(r"^[A-Za-z0-9_.-]+$")


def ffmpeg_cmd(out: Path, fps: int) -> list[str]:
    return ["ffmpeg", "-y", "-v", "error", "-f", "image2pipe", "-framerate", str(fps), "-c:v", "png", "-i", "-", "-threads", "2",
            "-c:v", "h264_nvenc", "-preset", "p7", "-tune", "hq", "-rc", "vbr", "-cq", "15", "-b:v", "0", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)]


def make_handler(root: Path, out: Path, fps: int):
    st = {"ff": None, "n": 0, "name": None, "next": 0, "pend": {}}
    lock = threading.Lock()

    class H(SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(root), **k)
        def log_message(self, *a):
            pass
        def end_headers(self):
            self.send_header("Cache-Control", "no-store")   # the page must always see the files on disk now
            super().end_headers()
        def _ok(self, body=b"ok"):
            self.send_response(200); self.send_header("Content-Type", "text/plain"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        def host_ok(self):   # DNS-rebinding guard (security 2026-10-27, #6): only this server's own loopback names
            port = self.server.server_address[1]
            return (self.headers.get("Host") or "").lower() in (f"127.0.0.1:{port}", f"localhost:{port}")
        def origin_ok(self):   # cross-site guard (security 2026-10-27 #6): a browser sends Origin on a cross-site POST and Sec-Fetch-Site on any request; the recorder's own page is same-origin
            port = self.server.server_address[1]
            o = self.headers.get("Origin")
            if o is not None and o.lower() not in (f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
                return False
            return self.headers.get("Sec-Fetch-Site", "same-origin") in ("same-origin", "none")
        def do_GET(self):
            if not (self.host_ok() and self.origin_ok()):
                self.send_error(403, "forbidden host or origin"); return
            if self.path.startswith("/quit"):
                self._ok(); threading.Thread(target=self.server.shutdown, daemon=True).start(); return
            return super().do_GET()
        def do_POST(self):
            if not (self.host_ok() and self.origin_ok()):
                self.send_error(403, "forbidden host or origin"); return
            u = urlparse(self.path); q = {k: v[0] for k, v in parse_qs(u.query).items()}
            n = int(self.headers.get("Content-Length", 0)); body = self.rfile.read(n)
            try:
                if u.path == "/start":
                    js = json.loads(body or b"{}"); name = js.get("name", "shot")
                    assert SAFE.match(name)
                    out.mkdir(parents=True, exist_ok=True)
                    if st["ff"]:
                        try: st["ff"].stdin.close(); st["ff"].wait(timeout=10)
                        except Exception: st["ff"].kill()
                    st.update(ff=subprocess.Popen(ffmpeg_cmd(out / f"{name}.mp4", fps), stdin=subprocess.PIPE), n=0, name=name, next=int(js.get("from", 0)), pend={})
                elif u.path == "/frame":
                    i = int(q["i"])
                    with lock:
                        if i >= st["next"]:
                            st["pend"][i] = body
                            while st["next"] in st["pend"]:
                                st["ff"].stdin.write(st["pend"].pop(st["next"])); st["next"] += 1; st["n"] += 1
                elif u.path == "/finish":
                    ff = st["ff"]; ff.stdin.close(); rc = ff.wait(); st["ff"] = None
                    (out / f"{st['name']}.encode.json").write_text(json.dumps({"frames": st["n"], "ffmpeg_exit": rc}), encoding="utf-8")
                elif u.path == "/mask":
                    kind = q["kind"]; assert kind in ("text", "shadow", "line"); i = int(q["i"])
                    d = out / "masks" / kind
                    if q.get("actor"):   # several characters: masks/<kind>/<actor>/NNNN.png
                        assert SAFE.match(q["actor"]); d = d / q["actor"]
                    d.mkdir(parents=True, exist_ok=True); (d / f"{i:04d}.png").write_bytes(body)
                elif u.path == "/trace":
                    json.loads(body); out.mkdir(parents=True, exist_ok=True); (out / "rig-trace.json").write_bytes(body)
                elif u.path == "/png":
                    name = q["name"]; assert SAFE.match(name)
                    d = out / "check"; d.mkdir(parents=True, exist_ok=True); (d / f"{name}.png").write_bytes(body)
                else:
                    self.send_error(404); return
                self._ok()
            except Exception as e:
                self.send_error(500, str(e)[:200])
    return H


class Running:
    def __init__(self, srv, thread):
        self.srv, self.thread = srv, thread
        self.port = srv.server_address[1]
    def stop(self):
        self.srv.shutdown(); self.srv.server_close(); self.thread.join(timeout=5)


def start(root: Path, out: Path, fps: int = 24, port: int = 0) -> Running:
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(Path(root), Path(out), fps))
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return Running(srv, t)


if __name__ == "__main__":
    root, out = Path(sys.argv[1]), Path(sys.argv[2])
    port = int(sys.argv[3]) if len(sys.argv) > 3 else 8767
    fps = int(sys.argv[4]) if len(sys.argv) > 4 else 24
    r = start(root, out, fps, port)
    print(f"serving {root} on http://127.0.0.1:{r.port}, writing {out}", flush=True)
    r.thread.join()
