"""Search keywords and paste-ready platform text for the series (reads data/seo/keywords.json).

    python tools/seo.py show     the hashtags, the YouTube tags line and the description keyword line, as they would go out

Used by ig.py (HASHTAGS), yt.py (HASHTAGS, tags, description keyword line, seo-fix). No network, no credentials.
Evidence and the profile texts for the Lead: your research notes.
"""
import json
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "seo" / "keywords.json"
EXAMPLE = Path(__file__).resolve().parent.parent / "config" / "seo-keywords.example.json"   # used when your own keywords file is not there yet
TAGS_LIMIT = 500          # YouTube: the tags of one video add up to at most 500 characters (OFFICIAL, videos resource `snippet.tags[]`)


def load(path: Path | None = None) -> dict:
    p = Path(path) if path else (DATA if DATA.is_file() else EXAMPLE)
    return json.loads(p.read_text(encoding="utf-8"))


def hashtag_list(platform: str, path: Path | None = None) -> list:
    return list(load(path)["hashtags"][platform])


def hashtags(platform: str, path: Path | None = None) -> str:
    return " ".join(hashtag_list(platform, path))


def youtube_tags(extra=(), path: Path | None = None) -> list:
    """The tag list for a video: the series tags first, then `extra` (an episode's own words), no duplicates, never more than the character budget.
    A tag with a space counts two extra characters (YouTube wraps it in quotes)."""
    d = load(path)
    budget = min(int(d.get("youtube_tags_max_chars", TAGS_LIMIT)), TAGS_LIMIT)
    out, used = [], 0
    for t in [*d["youtube_tags"], *extra]:
        t = t.strip()
        cost = len(t) + (2 if " " in t else 0) + (1 if out else 0)
        if not t or t in out or used + cost > budget:
            continue
        out.append(t)
        used += cost
    return out


def keyword_line(path: Path | None = None) -> str:
    return load(path)["youtube_keyword_line"]


def show() -> str:
    d = load()
    return "\n".join([
        "instagram: " + hashtags("instagram"), "facebook: " + hashtags("facebook"), "youtube: " + hashtags("youtube"),
        "youtube tags (comma line for Studio): " + ", ".join(youtube_tags()),
        "youtube description keyword line: " + keyword_line(),
        "channel keywords: " + d["channel_keywords"],
    ])


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(show())
