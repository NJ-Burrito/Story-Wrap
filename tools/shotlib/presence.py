"""Per-actor presence: which frames of a shot each actor is in (E01 run 1: actors that enter, exit or are cut between were forced into every frame).

An actor may declare `present` (shot.json actors[], list of [f0, f1) frame ranges) or `frames` (shot spec actors[], same format).
No declaration = present on every frame. Masks (shadow and line, one every MASK_EVERY frames) and the trace are expected per actor, on that actor's frames only.
Shared by tools/shot.py (trace stage), tools/qg_checks.py (spec and trace checks) and the recorder contract in tools/render/trace-multi.js.
"""
from __future__ import annotations

MASK_EVERY = 6   # trace-multi.js writes a shadow and a line mask on frames with f % 6 == 0


def declared(actor: dict) -> list | None:
    """The raw ranges an actor declares (spec `frames` or shot.json `present`), or None."""
    for k in ("frames", "present"):
        if actor.get(k) is not None:
            return actor[k]
    return None


def problems(rng, nf: int) -> list[str]:
    """Why a declared range list is not usable (empty = fine): integers, f0 < f1, inside 0..nf, sorted, not overlapping."""
    if not isinstance(rng, list) or not rng:
        return ["must be a non-empty list of [f0, f1) pairs"]
    out, last = [], 0
    for i, r in enumerate(rng):
        if not (isinstance(r, (list, tuple)) and len(r) == 2 and all(isinstance(x, int) and not isinstance(x, bool) for x in r)):
            out.append(f"range {i} {r!r} is not an [f0, f1] pair of integers"); continue
        f0, f1 = r
        if not 0 <= f0 < f1 <= nf:
            out.append(f"range {i} [{f0}, {f1}) must satisfy 0 <= f0 < f1 <= {nf}")
        if f0 < last:
            out.append(f"range {i} [{f0}, {f1}) overlaps or precedes the one before it (sorted, disjoint)")
        last = max(last, f1)
    return out


def ranges(actor: dict, nf: int) -> list[tuple[int, int]]:
    d = declared(actor)
    return [(0, nf)] if d is None else [(int(a), int(b)) for a, b in d]


def frames(actor: dict, nf: int) -> list[int]:
    return [f for a, b in ranges(actor, nf) for f in range(a, b)]


def mask_frames(actor: dict, nf: int) -> list[int]:
    return [f for f in frames(actor, nf) if f % MASK_EVERY == 0]


def present_at(actor: dict, f: int, nf: int) -> bool:
    return any(a <= f < b for a, b in ranges(actor, nf))


def _squash(fs) -> str:
    """[0,1,2,5,6] -> '0-2, 5-6' for messages."""
    fs = sorted(fs); out, i = [], 0
    while i < len(fs):
        j = i
        while j + 1 < len(fs) and fs[j + 1] == fs[j] + 1:
            j += 1
        out.append(f"{fs[i]}" if i == j else f"{fs[i]}-{fs[j]}"); i = j + 1
    return ", ".join(out[:6]) + (" ..." if len(out) > 6 else "")


def trace_issues(chars: dict, actors: list | None, nf: int, mask_root=None, shadow_floor: int | None = None) -> list[str]:
    """Check an exported trace against the declared presence. `chars` = trace['characters']; `actors` = shot.json actors[] (None = one character, every frame).
    Each actor must have exactly its declared frames (none missing, none extra) and a shadow and a line mask on each of its mask frames; an actor outside its
    range is not required to exist. `mask_root` = <shot>/out/masks. Returns messages (empty = fine)."""
    from pathlib import Path
    out: list[str] = []
    if actors:
        for a in actors:
            bad = problems(declared(a), nf) if declared(a) is not None else []
            if bad:
                out.append(f"actor {a.get('id')} presence: {'; '.join(bad)}")
        if out:
            return out
        want = {a["id"]: set(frames(a, nf)) for a in actors}
    else:
        want = {cid: set(range(nf)) for cid in chars}
    if sorted(chars) != sorted(want):
        return [f"trace has actors {sorted(chars)}, shot.json declares {sorted(want)}"]
    for cid, ch in chars.items():
        got = [fr["f"] for fr in ch["frames"]]
        gs = set(got)
        if len(got) != len(gs) or gs != want[cid]:
            out.append(f"actor {cid} traced {len(gs)} frames, declared present on {len(want[cid])}"
                       + (f"; missing {_squash(want[cid] - gs)}" if want[cid] - gs else "") + (f"; extra {_squash(gs - want[cid])}" if gs - want[cid] else ""))
    if mask_root is not None:
        mr = Path(mask_root)
        for cid in chars:
            mf = sorted(f for f in want[cid] if f % MASK_EVERY == 0)
            for kind in ("shadow", "line"):
                dirs = [mr / kind / cid] if actors else [mr / kind / cid, mr / kind]
                d = next((x for x in dirs if x.is_dir()), None)
                miss = [f for f in mf if d is None or not (d / f"{f:04d}.png").is_file()]
                if miss:
                    out.append(f"actor {cid} lacks {len(miss)} of {len(mf)} {kind} masks (frames {_squash(miss)})")
    return out
