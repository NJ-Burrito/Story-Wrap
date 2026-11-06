"""Recorder server (security 2026-10-27 #6): Host and cross-site guards."""
import http.client
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "record"))
import server  # noqa: E402


def _req(port, method, path, headers):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    c.request(method, path, body=b"{}" if method == "POST" else None, headers=headers)
    r = c.getresponse()
    r.read()
    c.close()
    return r.status


def test_guards(tmp_path):
    (tmp_path / "a.txt").write_text("x")
    srv = server.start(tmp_path, tmp_path / "out")
    try:
        p = srv.port
        host = {"Host": f"127.0.0.1:{p}"}
        assert _req(p, "GET", "/a.txt", host) == 200
        assert _req(p, "GET", "/a.txt", {"Host": "evil.example"}) == 403
        assert _req(p, "GET", "/a.txt", {**host, "Sec-Fetch-Site": "cross-site"}) == 403
        assert _req(p, "POST", "/trace", {**host, "Origin": "http://evil.example"}) == 403
        assert _req(p, "POST", "/trace", {**host, "Origin": f"http://127.0.0.1:{p}"}) == 200
        assert (tmp_path / "out" / "rig-trace.json").exists()
    finally:
        srv.stop()
