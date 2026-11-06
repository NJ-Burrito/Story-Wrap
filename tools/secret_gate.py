"""Outbound secret gate: text that is about to be published (a reply, a caption, a title, a description) must not carry a credential.

`secret_problems(text)` returns reasons (never the secret itself). Two checks:
  1. token SHAPES: Google OAuth (ya29., 1//0..., GOCSPX-, AIza), Meta (EAA, IGQ, IGAA), GitHub (ghp_, gho_, ghu_, ghs_, ghr_, github_pat_), AWS (AKIA/ASIA), Slack, OpenAI-style sk-,
     private-key headers, JWTs, and any unbroken run of 32+ characters of [A-Za-z0-9_-+/] (long base64 / hex).
  2. VALUES: any value of 8+ characters in the local credential files (~/.config/story-wrap/*.env, *token*.json; SW_IG_ENV and SW_YT_TOKEN override) found in the text,
     compared at call time; the values are never logged or returned.
Standard library only."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

SHAPES = [
    ("Google OAuth token", re.compile(r"ya29\.[A-Za-z0-9_\-.]{8,}|(?<![A-Za-z0-9])1//[A-Za-z0-9_\-]{8,}|GOCSPX-[A-Za-z0-9_\-]{6,}|AIza[A-Za-z0-9_\-]{20,}")),
    ("Meta token", re.compile(r"(?<![A-Za-z0-9])(?:EAA|IGQ|IGAA)[A-Za-z0-9]{12,}")),
    ("GitHub token", re.compile(r"(?<![A-Za-z0-9])(?:gh[pousr]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{16,})")),
    ("AWS key", re.compile(r"(?<![A-Za-z0-9])(?:AKIA|ASIA)[A-Z0-9]{12,}")),
    ("API key", re.compile(r"(?<![A-Za-z0-9])(?:sk-[A-Za-z0-9_\-]{16,}|xox[abprs]-[A-Za-z0-9\-]{10,})")),
    ("private key header", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY", re.I)),
    ("JWT", re.compile(r"eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]*")),
]
LONG_RUN = re.compile(r"[A-Za-z0-9_\-+/=]{32,}")


def _long_run(t: str) -> bool:
    """A 32+ character run that looks like a key (base64 / hex): letters and digits, few separators. Plain snake_case words and paths do not count."""
    for m in LONG_RUN.finditer(t):
        r = m.group(0)
        if re.search(r"\d", r) and re.search(r"[A-Za-z]", r) and sum(c in "_-/" for c in r) <= 0.1 * len(r):
            return True
    return False
MIN_VALUE = 8


def _conf_dir() -> Path:
    return Path.home() / ".config" / "story-wrap"


def _env_values(p: Path) -> list[str]:
    out = []
    try:
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                out.append(line.split("=", 1)[1].strip().strip('"').strip("'"))
    except OSError:
        pass
    return out


def _json_values(p: Path) -> list[str]:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [v for v in d.values() if isinstance(v, str)] if isinstance(d, dict) else []


def local_secret_values() -> list[str]:
    """Credential values on this PC (never logged)."""
    vals: list[str] = []
    d = _conf_dir()
    files_env = list(d.glob("*.env")) if d.is_dir() else []
    files_json = list(d.glob("*token*.json")) if d.is_dir() else []
    if os.environ.get("SW_IG_ENV"):
        files_env.append(Path(os.environ["SW_IG_ENV"]))
    if os.environ.get("SW_YT_TOKEN"):
        files_json.append(Path(os.environ["SW_YT_TOKEN"]))
    for p in files_env:
        vals += _env_values(p)
    for p in files_json:
        vals += _json_values(p)
    return sorted({v for v in vals if len(v) >= MIN_VALUE})


def secret_problems(text: str, extra_values=()) -> list[str]:
    t = str(text or "")
    why = [f"looks like a secret: {name}" for name, rx in SHAPES if rx.search(t)]
    if _long_run(t):
        why.append("looks like a secret: long token-like run (32+ characters)")
    if any(v in t for v in list(local_secret_values()) + [str(x) for x in extra_values if x and len(str(x)) >= MIN_VALUE]):
        why.append("contains a credential value")
    return why
