"""Source text of a tool module that was split into <name>_parts/ (the entry file plus its parts, in order)."""
from pathlib import Path


def module_source(path) -> str:
    p = Path(path)
    parts = sorted((p.parent / f"{p.stem}_parts").glob("p*.py"))
    return "\n".join(f.read_text(encoding="utf-8") for f in [p, *parts])
