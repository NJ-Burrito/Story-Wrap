"""Adopt an episode that was approved and gated by hand, so the Post task may publish it without rebuilding it (the owner's approved reference E01C).

    uv run tools/adopt.py adopt  <ep> --approved-by <name> --reason "<why>"   record the adoption (refuses on any failed condition)
    uv run tools/adopt.py status <ep>                                         is the adoption still valid? (exit 0 valid, 1 not)
    uv run tools/adopt.py revoke <ep>                                         delete the adoption record

Why: `daily.py post` refuses an episode whose run stages (script, voice, ..., critic) are not fresh and verified (UPSTREAM-NOT-VERIFIED). An episode built
before the stage fingerprints, or rebuilt by another path, would never post. An adoption is the explicit, recorded answer: it does NOT touch STATE.json and
does NOT weaken `require_upstream`; `daily.run_list` skips only the RUN_STAGES check, and only while `valid()` says the adoption still holds. Every post stage
(publish, schedule, yt_stories) and every gate in ig.publish_gates still runs.

An adoption is refused unless: the compose gate report says PASS, complete, with no failing check; the critic scored 9 or more; episode.mp4 exists and the gate
report is NEWER than it (the gate saw this file); the episode is not already posted; and the approver and a reason of at least 10 characters are named.
It records the SHA-256 of the gate report and of episode.mp4 in work/episodes/<ep>/adopted.json (and one line in work/daily/adoptions.jsonl). `valid()` re-reads
both files each time: if either hash changed (a new render, a marked version, a re-gate), the adoption is void and the episode must be adopted again, which
needs a fresh PASS gate for the new file. Standard library only.
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ig   # noqa: E402
from ig import read_json, wdir, write_json   # noqa: E402

REPO = ig.REPO
MIN_REASON = 10


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def rec_path(ep: str, root: Path = REPO) -> Path:
    return wdir(ep, root) / "adopted.json"


def problems(ep: str, root: Path = REPO) -> list:
    """Why the adoption of <ep> does not hold right now (empty = it holds). Hashes are recomputed from the files on disk."""
    try:
        rec = read_json(rec_path(ep, root))
    except ValueError:
        return ["adopted.json is not valid JSON"]
    if not isinstance(rec, dict):
        return ["not adopted"]
    w, why = wdir(ep, root), []
    gate, video = w / "gate" / "report.json", w / "episode.mp4"
    if not gate.is_file() or not video.is_file():
        return ["gate report or episode.mp4 is missing"]
    if sha256(gate) != rec.get("gate_report_sha256"):
        why.append("the gate report changed since the adoption")
    if sha256(video) != rec.get("episode_sha256"):
        why.append("episode.mp4 changed since the adoption")
    why += ig.publish_gates(ep, root)
    return why


def valid(ep: str, root: Path = REPO) -> bool:
    return not problems(ep, root)


def adopt(ep: str, approved_by: str, reason: str, root: Path = REPO, at: datetime | None = None) -> dict:
    root = Path(root)
    if not (approved_by or "").strip():
        ig.fail("ADOPT-WHO", "--approved-by must name who approved the episode")
    if len((reason or "").strip()) < MIN_REASON:
        ig.fail("ADOPT-WHY", f"--reason must say why in at least {MIN_REASON} characters")
    w = wdir(ep, root)
    if (w / "post.json").is_file():
        ig.fail("ADOPT-POSTED", f"{ep} is already posted (post.json); nothing to adopt")
    why = ig.publish_gates(ep, root)             # gate PASS and complete, no failing check, critic >= 9, episode.mp4 exists
    if why:
        ig.fail("ADOPT-GATES", "refusing to adopt " + ep + ": " + "; ".join(why))
    gate, video = w / "gate" / "report.json", w / "episode.mp4"
    if gate.stat().st_mtime < video.stat().st_mtime:
        ig.fail("ADOPT-STALE-GATE", f"{ep}: episode.mp4 is newer than its gate report: the gate never saw this file; run the gate again")
    g, cr = read_json(gate), read_json(w / "heal" / "critic.json")
    rec = {"episode": ep, "approved_by": approved_by.strip(), "reason": reason.strip(), "adopted_at": (at or datetime.now()).isoformat(timespec="seconds"),
           "gate_report_sha256": sha256(gate), "episode_sha256": sha256(video), "gate_verdict": g.get("verdict"), "gate_checks": len(g.get("checks", [])),
           "critic_score": cr.get("score")}
    write_json(rec_path(ep, root), rec)
    log = root / "work" / "daily" / "adoptions.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"ADOPTED {ep} (approved by {rec['approved_by']}): gate {rec['gate_verdict']} with {rec['gate_checks']} checks, critic {rec['critic_score']}; "
          f"the Post task may now publish it without rebuilding")
    return rec


def revoke(ep: str, root: Path = REPO) -> bool:
    p = rec_path(ep, root)
    if not p.is_file():
        return False
    p.unlink()
    print(f"adoption of {ep} revoked")
    return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Adopt an approved, gated episode so it can be posted without a rebuild")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("adopt"); p.add_argument("ep"); p.add_argument("--approved-by", required=True); p.add_argument("--reason", required=True)
    for n in ("status", "revoke"):
        p = sub.add_parser(n); p.add_argument("ep")
    a = ap.parse_args(argv)
    if a.cmd == "adopt":
        adopt(a.ep, a.approved_by, a.reason)
        return 0
    if a.cmd == "revoke":
        revoke(a.ep)
        return 0
    why = problems(a.ep)
    print(f"{a.ep}: adoption " + ("valid" if not why else "NOT valid: " + "; ".join(why)))
    return 0 if not why else 1


if __name__ == "__main__":
    sys.exit(main())
