# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Temporary public hosting for the one file Meta must fetch (Instagram video_url), through the `gh` CLI that is already signed in on this PC.

    uv run tools/media_host.py sweep            delete every stale ig-tmp-* release (older than 2 h)
    uv run tools/media_host.py selftest <file>  create, verify and delete a release for a small file (no Instagram call)

Why: the resumable upload is refused above about 20 MB (research/instagram-api.md, measured 2026-10-26), and the episode is always uploaded in its ORIGINAL quality.
host(path) -> (download_url, cleanup). The release lives on the public repo OWNER/OWNER.github.io under the tag ig-tmp-<name>-<UTC stamp>.
The upload is verified through the public URL (Content-Length equals the local size, sha256 of the first and last MiB match). cleanup() deletes the release and
its tag and checks that both are gone. Any failure inside host() removes what it created before the error is raised. No token is read or stored here: `gh` holds the login.
Standard library only.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = os.environ.get("SW_MEDIA_REPO") or "owner/owner.github.io"      # public repo whose temporary releases host the video (see config/story-wrap.example.env)
PREFIX = "ig-tmp-"
STALE_AFTER = timedelta(hours=2)
MIB = 1024 * 1024
GONE_CHECKS, GONE_EVERY_S = 6, 2.0
_sleep = time.sleep


class MediaHostError(SystemExit):
    pass


def fail(code: str, msg: str):
    raise MediaHostError(f"FAIL [{code}] {msg}")


GH_ENV = Path(os.environ.get("SW_GH_ENV") or Path.home() / ".config" / "story-wrap" / "github.env")


def gh_token(path: Path | None = None) -> str:
    """The narrow token for this one repo (a fine-grained PAT, Contents: read and write on OWNER/OWNER.github.io only), from ~/.config/story-wrap/github.env
    (GH_TOKEN=... or GITHUB_TOKEN=...). Empty when the file is absent: gh then uses its own login (security 2026-10-27, #3). Never printed."""
    try:
        for line in Path(path or GH_ENV).read_text(encoding="utf-8").splitlines():
            k, _, v = line.partition("=")
            if k.strip() in ("GH_TOKEN", "GITHUB_TOKEN") and v.strip():
                return v.strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def gh(args: list, run=None, check: bool = True) -> subprocess.CompletedProcess:
    """One gh call; `run` is the injectable runner (tests). Output is text; a non-zero exit fails with MH-GH unless check is False. With github.env present the child gets
    GH_TOKEN from it (the narrow token); without it gh uses its own login."""
    kw = {}
    tok = gh_token()
    if tok:
        kw["env"] = {**os.environ, "GH_TOKEN": tok}
    r = (run or subprocess.run)(["gh", *args], capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)
    if check and r.returncode != 0:
        out = (r.stderr or r.stdout or '')
        out = out.replace(tok, '[REDACTED]') if tok else out
        fail("MH-GH", f"gh {' '.join(args[:2])} exited {r.returncode}: {out.strip()[:300]}")
    return r


def http_get(url: str, rng: str | None = None) -> tuple:
    """(status, headers, body). Follows redirects (the release asset is served from a CDN). Only the requested range is read."""
    req = urllib.request.Request(url, headers={"Range": rng} if rng else {})
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read()


def _safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", s).strip("-") or "media"


def make_tag(name: str, at: datetime | None = None) -> str:
    return f"{PREFIX}{_safe(name)}-{(at or datetime.now(timezone.utc)).strftime('%Y%m%dT%H%M%SZ')}"


def download_url(tag: str, filename: str) -> str:
    return f"https://github.com/{REPO}/releases/download/{tag}/{filename}"


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def verify_public(url: str, path: Path, fetch=None) -> None:
    """The public copy is the local file: size equal, first and last MiB identical (sha256). Fails with MH-VERIFY."""
    fetch = fetch or http_get
    size = path.stat().st_size
    n = min(MIB, size)
    with path.open("rb") as f:
        first = f.read(n)
        f.seek(size - n)
        last = f.read(n)
    try:
        st, hd, body = fetch(url, f"bytes=0-{n - 1}")
        if st == 206:
            m = re.search(r"/(\d+)\s*$", hd.get("content-range", ""))
            total = int(m.group(1)) if m else -1
            got_first = body
            st2, _, got_last = fetch(url, f"bytes={size - n}-{size - 1}")
            if st2 != 206:
                fail("MH-VERIFY", f"last-MiB request answered {st2}, not 206")
        elif st == 200:     # the server ignored Range: the body is the whole file
            total, got_first, got_last = int(hd.get("content-length", len(body))), body[:n], body[-n:]
            if len(body) != total:
                fail("MH-VERIFY", f"body is {len(body)} bytes but Content-Length says {total}")
        else:
            fail("MH-VERIFY", f"public download answered HTTP {st}, not 200/206")
    except MediaHostError:
        raise
    except Exception as e:
        fail("MH-VERIFY", f"public download failed: {type(e).__name__}: {str(e)[:200]}")
    if total != size:
        fail("MH-VERIFY", f"public size {total} != local size {size}")
    if _sha(got_first) != _sha(first) or _sha(got_last) != _sha(last):
        fail("MH-VERIFY", "sha256 of the first or last MiB differs from the local file")


def _gone(tag: str, run=None) -> str | None:
    """None when both the release and its tag are gone, else what is left."""
    if gh(["release", "view", tag, "--repo", REPO], run, check=False).returncode == 0:
        return "release"
    if gh(["api", f"repos/{REPO}/git/ref/tags/{tag}"], run, check=False).returncode == 0:
        return "tag"
    return None


def _delete(tag: str, run=None) -> None:
    """Delete release + tag and prove both are gone (the tag can linger a few seconds: measured live, so it is re-checked). Already absent counts as gone."""
    gh(["release", "delete", tag, "--repo", REPO, "--cleanup-tag", "--yes"], run, check=False)
    left = _gone(tag, run)
    for _ in range(GONE_CHECKS):
        if left is None:
            return
        _sleep(GONE_EVERY_S)
        left = _gone(tag, run)
    if left:
        fail("MH-CLEANUP", f"{left} {tag} still exists on {REPO}; run `media_host.py sweep`")


def host(path: Path, name: str | None = None, run=None, fetch=None, at: datetime | None = None) -> tuple:
    """Upload `path` to a temporary public release. Returns (download_url, cleanup). On any failure the release is removed and an MH-* error raised."""
    path = Path(path)
    if not path.is_file() or path.stat().st_size == 0:
        fail("MH-FILE", f"{path} is missing or empty")
    if _safe(path.name) != path.name:
        fail("MH-FILE", f"file name {path.name!r} has characters GitHub would rename; use a plain name")
    tag = make_tag(name or path.parent.name or path.stem, at)
    url = download_url(tag, _safe(path.name))
    state = {"done": False}

    def cleanup() -> None:
        if not state["done"]:
            _delete(tag, run)
            state["done"] = True

    try:
        gh(["release", "create", tag, "--repo", REPO, "--title", tag, "--notes", "temporary host for an Instagram video_url fetch; deleted right after", "--latest=false"], run)
        gh(["release", "upload", tag, str(path), "--repo", REPO], run)
        verify_public(url, path, fetch)
    except BaseException:
        try:
            cleanup()
        except SystemExit as e:
            print(f"WARNING cleanup after a failed upload: {e}", file=sys.stderr)
        raise
    return url, cleanup


def sweep(run=None, now: datetime | None = None) -> list:
    """Delete every ig-tmp-* release older than 2 h. Returns the tags removed. Releases of other names are never touched."""
    now = now or datetime.now(timezone.utc)
    out = json.loads(gh(["release", "list", "--repo", REPO, "--limit", "100", "--json", "tagName,createdAt"], run).stdout or "[]")
    gone = []
    for r in out:
        tag = r.get("tagName", "")
        if not tag.startswith(PREFIX):
            continue
        if now - datetime.fromisoformat(r["createdAt"].replace("Z", "+00:00")) > STALE_AFTER:
            _delete(tag, run)
            gone.append(tag)
    return gone


def main(argv: list) -> int:
    try:
        if argv[:1] == ["sweep"]:
            gone = sweep()
            print(f"swept {len(gone)} stale release(s): {', '.join(gone) or '-'}")
        elif argv[:1] == ["selftest"] and len(argv) == 2:
            url, cleanup = host(Path(argv[1]), name="selftest")
            print(f"hosted and verified: {url}")
            cleanup()
            print("cleaned up: release and tag gone")
        else:
            print(__doc__)
            return 2
    except MediaHostError as e:
        print(e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
