# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Story-Wrap healing loop, the deterministic half (pipelines/HEAL.md).

  uv run tools/heal.py classify <dir> [--kind shot|episode|artbook|writing|voice]
  uv run tools/heal.py critic-brief <dir>        write heal/critic-brief.md for the Sonnet critic
  uv run tools/heal.py validate-critic <dir>     check heal/critic.json against the checklist and the rubric
  uv run tools/heal.py fix-brief <dir>           write heal/fix-brief.md (classified faults + playbooks) for the fixer
  uv run tools/heal.py round <dir> --fault F-001 --fix "..." --fix-kind scene --files a b [--result fixed|partial|failed]
                                   [--new-round] [--stage shot] [--tokens N] [--class C]
  uv run tools/heal.py guard <dir>               refuse if a frozen file, threshold or hand-edited trace changed
  uv run tools/heal.py learn <dir> [--build ID]  healed faults -> kb/lessons/ledger.jsonl (+ proposals for new kinds)
  uv run tools/heal.py status <dir>              open faults, rounds, budget, and whether the owner may see it
  uv run tools/heal.py prepare <dir>             snapshot + classify + briefs (what shot.py/compose.py/artbook.py call)

<dir> is a shot folder, an episode work folder or the art book work folder. State lives in <dir>/heal/.
Exit: 0 ok / ready, 1 open faults or not ready, 2 usage, 3 rounds or budget exhausted (stop and report), 4 forbidden fix.
The LLM steps (critic, fixer) are run by the Lead as agents; this tool prepares their inputs and validates their outputs.
It never loosens a gate: the heal setting is pipelines/heal.json.
"""
from __future__ import annotations
import argparse, datetime as dt, fnmatch, hashlib, json, math, os, re, subprocess, sys, time
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("STORYWRAP_ROOT") or TOOLS.parent)

SEV_ORDER = {"S1": 1, "S2": 2, "S3": 3, "S4": 4}
PENALTY = {"S1": 3.0, "S2": 0.5, "S3": 0.4, "S4": 0.25}
CAP = {"S1": 4, "S2": 6, "S3": 8}
KINDS = ("shot", "episode", "artbook", "writing", "voice")
SEV_BY_CLASS = {"LOOK2D": "S1", "PLAYBACK": "S1", "ACTORS": "S1", "GATE-BLIND": "S1", "TEXT": "S2"}


class HealRefused(Exception):
    """A heal action was refused. code 3 = rounds or budget exhausted, 4 = forbidden fix."""
    def __init__(self, code: int, msg: str):
        super().__init__(msg)
        self.code, self.msg = code, msg


# ------------------------------------------------------------------ config, checklist, playbooks
def load_config(root: Path = ROOT) -> dict:
    return json.loads((root / "pipelines" / "heal.json").read_text(encoding="utf-8"))


def enabled(root: Path = ROOT) -> bool:
    try:
        return bool(load_config(root).get("enabled"))
    except (OSError, ValueError):
        return False


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def load_checklist(root: Path = ROOT) -> dict[str, dict]:
    """CQ-* rows of kb/quality/critic-checklist.md: id -> {applies, severity, question, look, maps}."""
    out = {}
    for line in (root / "kb" / "quality" / "critic-checklist.md").read_text(encoding="utf-8").splitlines():
        if not line.startswith("| CQ-"):
            continue
        c = _cells(line)
        if len(c) < 6:
            continue
        out[c[0]] = {"id": c[0], "applies": {a.strip() for a in c[1].split(",")}, "severity": c[2], "question": c[3], "look": c[4], "maps": c[5]}
    return out


def load_playbooks(root: Path = ROOT) -> list[dict]:
    """The class table of kb/quality/heal-playbooks.md."""
    rows, on = [], False
    for line in (root / "kb" / "quality" / "heal-playbooks.md").read_text(encoding="utf-8").splitlines():
        if line.startswith("| class |"):
            on = True
            continue
        if on and line.startswith("|---"):
            continue
        if on and line.startswith("|"):
            c = _cells(line)
            if len(c) < 7:
                continue
            sp = lambda s: [x.strip() for x in s.split(",") if x.strip()]
            rows.append({"class": c[0], "match": sp(c[1]), "questions": sp(c[2]), "fix_in": sp(c[3]), "fixer": c[4],
                         "rerun_from": c[5], "rules": c[6]})
        elif on and rows:
            break
    return rows


def match_class(check_id: str, playbooks: list[dict]) -> dict | None:
    """Most specific pattern wins: an exact id beats a wildcard; among wildcards the longest literal prefix."""
    best, best_score = None, -1
    for pb in playbooks:
        for pat in pb["match"]:
            if fnmatch.fnmatchcase(check_id, pat):
                score = 10_000 if "*" not in pat else len(pat.split("*")[0])
                if score > best_score:
                    best, best_score = pb, score
    return best


def class_for_question(q: str, playbooks: list[dict]) -> dict | None:
    for pb in playbooks:
        if q in pb["questions"]:
            return pb
    return None


def unknown_class(playbooks: list[dict]) -> dict:
    return next((p for p in playbooks if p["class"] == "UNKNOWN"), {"class": "UNKNOWN", "match": [], "questions": [], "fix_in": [], "fixer": "opus", "rerun_from": "", "rules": "R-395"})


# ------------------------------------------------------------------ helpers
def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(p: Path, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(p: Path, data) -> None:
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def read_jsonl(p: Path) -> list[dict]:
    out = []
    if Path(p).is_file():
        for line in Path(p).read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
    return out


def append_jsonl(p: Path, rec: dict) -> None:
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def heal_dir(d: Path) -> Path:
    return Path(d) / "heal"


def detect_kind(d: Path) -> str:
    d = Path(d)
    rep = read_json(d / "gate" / "report.json") or {}
    if "gates" in rep or (d / "shot.json").is_file():
        return "shot"
    if "checks" in rep or (d / "plan.json").is_file():
        return "episode"
    if (d / "gate" / "artbook.out").is_file() or d.name == "artbook":
        return "artbook"
    return "shot"


# ------------------------------------------------------------------ gate failures
FAIL_RE = re.compile(r"^FAIL(?: \[([A-Za-z0-9_*-]+)\]| ([A-Za-z0-9_]+))")
SHOT_GATES = ("spec", "rig", "hands", "extras", "look2d", "preview", "render")


def read_gate_failures(d: Path, kind: str) -> list[dict]:
    """Failing check ids from the stage's own gate report. A missing or incomplete report is itself a fault."""
    d = Path(d)
    out: list[dict] = []
    rep = read_json(d / "gate" / "report.json")
    if kind == "shot":
        if rep is None:
            return [{"check": "GATE-INPUT", "gate": "-", "detail": "gate/report.json missing: run `shot.py gate` first"}]
        gates = rep.get("gates", {})
        for g in SHOT_GATES:
            if g not in gates:
                out.append({"check": "GATE-INCOMPLETE", "gate": g, "detail": f"gate {g!r} did not run (every gate runs every time, R-400)"})
        for g, e in gates.items():
            ids = e.get("fail_ids") or []
            if e.get("verdict") != "PASS" and not ids:
                ids = ["TOOL-ERROR"]
            for i in ids:
                out.append({"check": i, "gate": g, "detail": f"{g} gate: FAIL {i}"})
    elif kind == "episode":
        if rep is None:
            return [{"check": "GATE-INPUT", "gate": "-", "detail": "gate/report.json missing: run `compose.py gate` first"}]
        if rep.get("complete") is False:
            out.append({"check": "GATE-INCOMPLETE", "gate": "render", "detail": "the render gate was skipped: the report is NOT complete"})
        for c in rep.get("checks", []):
            if c.get("status") == "fail":
                out.append({"check": c["id"], "gate": "episode", "detail": c.get("detail", "")[:240]})
    else:   # artbook, writing, voice: text output, one FAIL [ID] line per fault
        outs = sorted((d / "gate").glob("*.out")) if (d / "gate").is_dir() else []
        if not outs:
            return [{"check": "GATE-INPUT", "gate": "-", "detail": f"no gate/*.out in {d}: run the stage's check first"}]
        for p in outs:
            for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                m = FAIL_RE.match(line.strip())
                if m and (m.group(1) or m.group(2)) and not re.match(r"^FAIL ARTBOOK-[A-Z]+( \(\d+\))?$", line.strip()):
                    out.append({"check": m.group(1) or m.group(2), "gate": p.stem, "detail": line.strip()[:240]})
    return out


# ------------------------------------------------------------------ critic
def compute_score(faults: list[dict]) -> int:
    raw = 10.0 - sum(PENALTY.get(f.get("severity"), 0) for f in faults)
    score = math.ceil(raw - 0.5)           # half rounds down
    for sev, cap in CAP.items():
        if any(f.get("severity") == sev for f in faults):
            score = min(score, cap)
    return max(1, min(10, score))


def validate_critic(critic: dict, kind: str, root: Path = ROOT) -> tuple[list[str], int | None]:
    """Errors (empty = valid) and the effective score (the lower of the claimed and the rubric score)."""
    cl = load_checklist(root)
    errs: list[str] = []
    if not isinstance(critic, dict):
        return ["critic.json is not an object"], None
    faults = critic.get("faults")
    answers = critic.get("answers")
    if not isinstance(faults, list) or not isinstance(answers, list):
        return ["critic.json needs `answers` and `faults` lists"], None
    fault_ids = {f.get("id") for f in faults}
    need = {q for q, v in cl.items() if kind in v["applies"]}
    seen = {}
    for a in answers:
        q = a.get("q")
        if q not in cl:
            errs.append(f"answer for unknown question {q!r}")
            continue
        seen[q] = a
        ans = a.get("answer")
        if ans not in ("yes", "no", "na"):
            errs.append(f"{q}: answer must be yes, no or na")
        if not str(a.get("evidence", "")).strip():
            errs.append(f"{q}: evidence missing (a frame number or a sheet tile)")
        if ans == "no" and a.get("fault") not in fault_ids:
            errs.append(f"{q}: a `no` needs a matching fault id")
    for q in sorted(need - set(seen)):
        errs.append(f"{q}: not answered (it applies to {kind})")
    for f in faults:
        sev, q = f.get("severity"), f.get("q")
        if sev not in SEV_ORDER:
            errs.append(f"fault {f.get('id')}: severity must be S1..S4")
            continue
        if q != "NEW" and q not in cl:
            errs.append(f"fault {f.get('id')}: unknown question {q!r} (use NEW for a new kind of fault)")
        elif q in cl and SEV_ORDER[sev] > SEV_ORDER[cl[q]["severity"]]:
            errs.append(f"fault {f.get('id')}: severity {sev} is lower than the checklist's {cl[q]['severity']} for {q}")
        if not str(f.get("evidence", "")).strip():
            errs.append(f"fault {f.get('id')}: evidence missing")
    rubric = compute_score(faults)
    claimed = critic.get("score")
    if not isinstance(claimed, int) or not 1 <= claimed <= 10:
        errs.append("score must be an integer 1..10")
        return errs, rubric
    if claimed > rubric:
        errs.append(f"score {claimed} is higher than the rubric allows from the faults ({rubric})")
    return errs, min(claimed, rubric)


# ------------------------------------------------------------------ guard (the forbidden-fix refusal)
def _matches(rel: str, pats: list[str]) -> bool:
    rel = rel.replace("\\", "/")
    return any(fnmatch.fnmatchcase(rel, p.replace("**", "*")) for p in pats)


def _regen_files(d: Path, cfg: dict) -> list[Path]:
    pats = cfg["protected_paths"]["regenerated_only"]
    out = []
    for p in Path(d).rglob("*"):
        if p.is_file() and "heal" not in p.relative_to(d).parts and p.name != "STATE.json":
            if _matches(p.relative_to(d).as_posix(), pats):
                out.append(p)
    return sorted(out)


def _frozen_files(root: Path, cfg: dict) -> dict[str, Path]:
    pp = cfg["protected_paths"]
    out = {}
    for rel in pp["frozen"]:
        p = root / rel
        if p.is_file():
            out[rel] = p
    for g in pp.get("frozen_globs", []):
        base = root / g.split("**")[0].rstrip("/")
        if base.is_dir():
            for p in base.rglob("*"):
                if p.is_file():
                    out[p.relative_to(root).as_posix()] = p
    return out


def snapshot(d: Path, root: Path = ROOT, now: float | None = None, force: bool = False) -> dict:
    """Hash the frozen files and the regenerated-only outputs once, at the start of a heal. Never overwritten (unless forced)."""
    hd = heal_dir(d)
    sp = hd / "snapshot.json"
    if sp.is_file() and not force:
        return read_json(sp)
    cfg = load_config(root)
    snap = {"created": now if now is not None else time.time(),
            "frozen": {rel: sha256(p) for rel, p in _frozen_files(root, cfg).items()},
            "regen": {p.relative_to(d).as_posix(): sha256(p) for p in _regen_files(d, cfg)}}
    write_json(sp, snap)
    return snap


def _stage_times(d: Path) -> dict[str, float]:
    st = (read_json(Path(d) / "STATE.json") or {}).get("stages", {})
    out = {}
    for name, e in st.items():
        at = e.get("at")
        if at:
            try:
                out[name] = time.mktime(time.strptime(at, "%Y-%m-%dT%H:%M:%S"))
            except ValueError:
                pass
    return out


def _git_dirty(root: Path, rels: list[str]) -> set[str] | None:
    """Of `rels`, those with an uncommitted change (modified, staged or deleted) against HEAD, or None when root is not a git
    checkout with a HEAD. Lead-committed edits are clean here; only uncommitted ones count."""
    if not rels:
        return set()
    try:
        r = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no", "--", *rels],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        h = subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", "-q", "HEAD"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0 or h.returncode != 0:
        return None
    out = set()
    for line in r.stdout.splitlines():
        path = line[3:].strip().strip('"')
        if " -> " in path:
            path = path.split(" -> ")[-1]
        out.add(path.replace("\\", "/"))
    return out


def _git_tracked(root: Path, rels: list[str]) -> set[str]:
    try:
        r = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--", *rels], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60)
    except (OSError, subprocess.SubprocessError):
        return set()
    return {x for x in r.stdout.split("\0") if x} if r.returncode == 0 else set()


def _frozen_violations(root: Path, frozen_snap: dict) -> list[str]:
    """A frozen file is judged against the last commit (HEAD), not a stored snapshot: edits the Lead committed (git log) are
    legitimate, an uncommitted edit made during a heal is refused. Files git does not track, or a root that is not a git
    checkout, fall back to the hashes stored at the start of the heal."""
    msg = " (a gate threshold, check, schema or reference may not change inside a heal; R-396, R-212)"
    rels = list(frozen_snap)
    tracked = _git_tracked(root, rels)
    dirty = _git_dirty(root, sorted(tracked)) if tracked else set()
    bad = []
    for rel, h in frozen_snap.items():
        p = root / rel
        if dirty is not None and rel in tracked:
            if rel in dirty:
                bad.append(f"frozen file {'removed' if not p.is_file() else 'has an uncommitted change'}: {rel}{msg}")
            continue
        if not p.is_file():
            bad.append(f"frozen file removed: {rel}")
        elif sha256(p) != h:
            bad.append(f"frozen file changed: {rel}{msg}")
    return bad


def guard(d: Path, root: Path = ROOT) -> list[str]:
    """Violations since the snapshot. A frozen file (a threshold, a check, a schema, a reference) may not change at all.
    A trace, mask or gate output may change only because its stage re-ran: its mtime may not be later than the newest
    stage record in STATE.json (a later mtime means somebody edited it by hand)."""
    d = Path(d)
    snap = read_json(heal_dir(d) / "snapshot.json")
    if snap is None:
        raise HealRefused(2, f"no heal/snapshot.json in {d}: run `heal.py classify {d}` first")
    cfg = load_config(root)
    bad = []
    bad += _frozen_violations(root, snap["frozen"])
    times = _stage_times(d)
    newest = max(times.values()) if times else None
    for rel, h in snap["regen"].items():
        p = d / rel
        if not p.is_file():
            bad.append(f"output removed: {rel}")
            continue
        if sha256(p) != h:
            if newest is None or p.stat().st_mtime > newest + 2:
                bad.append(f"trace/mask/gate output edited by hand: {rel} (outputs change only by re-running their stage; R-396)")
    for p in _regen_files(d, cfg):
        rel = p.relative_to(d).as_posix()
        if rel not in snap["regen"] and (newest is None or p.stat().st_mtime > newest + 2):
            bad.append(f"new trace/mask/gate output written by hand: {rel}")
    return bad


def check_declared(files: list[str], kind: str, root: Path, d: Path) -> list[str]:
    """Refuse a round whose declared fix kind or files are on the forbidden list."""
    cfg = load_config(root)
    bad = []
    if kind in cfg["forbidden_fix_kinds"]:
        bad.append(f"fix kind {kind!r} is forbidden (kb/quality/heal-playbooks.md)")
    pp = cfg["protected_paths"]
    for f in files:
        fp = Path(f)
        full = fp if fp.is_absolute() else (root / fp)
        rel_root = None
        try:
            rel_root = full.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            pass
        if rel_root and (rel_root in pp["frozen"] or _matches(rel_root, pp.get("frozen_globs", []))):
            bad.append(f"{f}: frozen (threshold, check, schema or reference)")
            continue
        try:
            rel_dir = full.resolve().relative_to(Path(d).resolve()).as_posix()
        except ValueError:
            rel_dir = None
        if rel_dir and _matches(rel_dir, pp["regenerated_only"]):
            bad.append(f"{f}: a trace, mask or gate output; re-run its stage instead of editing it")
    return bad


# ------------------------------------------------------------------ classify
def _fault_from_gate(g: dict, pbs: list[dict], n: int) -> dict:
    pb = match_class(g["check"], pbs) or unknown_class(pbs)
    return {"id": f"G-{n:03d}", "source": "gate", "check": g["check"], "question": None, "severity": SEV_BY_CLASS.get(pb["class"], "S2"),
            "class": pb["class"], "fix_in": pb["fix_in"], "fixer": pb["fixer"], "rerun_from": pb["rerun_from"], "rules": pb["rules"],
            "frame": None, "detail": g["detail"], "gate": g["gate"]}


def _fault_from_critic(f: dict, pbs: list[dict]) -> dict:
    q = f.get("q")
    pb = class_for_question(q, pbs) if q != "NEW" else None
    pb = pb or unknown_class(pbs)
    return {"id": f["id"], "source": "critic", "check": None, "question": q, "severity": f["severity"], "class": pb["class"],
            "fix_in": pb["fix_in"], "fixer": pb["fixer"], "rerun_from": pb["rerun_from"], "rules": pb["rules"],
            "frame": f.get("frame"), "detail": f.get("description") or f.get("evidence", ""), "gate": None}


def classify(d: Path, kind: str | None = None, root: Path = ROOT, now: float | None = None) -> dict:
    d = Path(d)
    kind = kind or detect_kind(d)
    cfg = load_config(root)
    pbs = load_playbooks(root)
    snapshot(d, root, now)
    faults = [_fault_from_gate(g, pbs, i + 1) for i, g in enumerate(read_gate_failures(d, kind))]
    critic = read_json(heal_dir(d) / "critic.json")
    cerrs, cscore = [], None
    if critic is not None:
        cerrs, cscore = validate_critic(critic, kind, root)
        if not cerrs:
            faults += [_fault_from_critic(f, pbs) for f in critic["faults"]]
    # a fault fixed in an earlier round is closed only when a fresh gate run and a fresh critic no longer list it;
    # classify always reads the current gate report and the current critic.json, so it never carries stale faults.
    min_score = cfg["critic"]["min_score"]
    gate_clean = not any(f["source"] == "gate" for f in faults)
    blocking = set(cfg["critic"]["blocking_severities"])
    open_blocking = [f for f in faults if f["severity"] in blocking]
    ready = gate_clean and critic is not None and not cerrs and cscore is not None and cscore >= min_score and not open_blocking
    res = {"dir": str(d), "kind": kind, "critic_present": critic is not None, "critic_errors": cerrs, "score": cscore, "min_score": min_score,
           "gate_clean": gate_clean, "faults": faults, "ready_for_owner": ready,
           "next": _next_action(faults, critic, cerrs, cscore, min_score, gate_clean)}
    write_json(heal_dir(d) / "classified.json", res)
    return res


def _next_action(faults, critic, cerrs, cscore, min_score, gate_clean) -> str:
    if not gate_clean:
        return "fix the gate failures (fix-brief), rerun from the earliest rerun_from, then gate again"
    if critic is None:
        return "gates pass: dispatch the Sonnet critic with heal/critic-brief.md, it writes heal/critic.json"
    if cerrs:
        return "critic.json is invalid: send it back to the critic with the errors"
    if faults:
        return "fix the critic faults (fix-brief), rerun, gate, then a fresh critic"
    if cscore is not None and cscore < min_score:
        return f"critic score {cscore} is below {min_score} with no listed fault: ask the critic to name what costs the points"
    return "ready: add the preview tab and show the owner"


# ------------------------------------------------------------------ briefs
def critic_brief(d: Path, kind: str | None = None, root: Path = ROOT) -> Path:
    d = Path(d)
    kind = kind or detect_kind(d)
    cl = load_checklist(root)
    qs = [v for v in cl.values() if kind in v["applies"]]
    sheets = sorted(p.relative_to(root).as_posix() if p.is_relative_to(root) else str(p) for p in (list((d / "review").glob("*.png")) if (d / "review").is_dir() else []))
    refs = [p for p in ("reference/mix-v5/hands-sheet.png", "reference/mix-v5/mix-v5.mp4", "reference/shot2-partner-drain/review") if (root / p).exists()]
    lines = [f"# Critic brief: {d.name} ({kind})", "",
             "You are the Sonnet critic. You replace the owner's notes. Read the work yourself, then answer every question below.",
             "Yes = good. A `no` is a fault. Evidence is a frame number or a sheet tile, never a feeling.", "",
             "## Read", f"- Work folder: `{d}`", f"- Gate report: `{d / 'gate' / 'report.json'}`",
             "- Review sheets: " + (", ".join(f"`{s}`" for s in sheets) or "none yet (run the review stage first)"),
             "- References to hold it against: " + (", ".join(f"`{r}`" for r in refs) or "none"),
             f"- Checklist, rubric and anchors: `kb/quality/critic-checklist.md` (v1)", "",
             "## Write", f"`{heal_dir(d) / 'critic.json'}`, exactly the schema at the end of the checklist. Score with the rubric; the tool recomputes it and refuses a higher claim.",
             "A fault with no matching question uses `q: \"NEW\"` and a full description.", "", f"## Questions that apply ({len(qs)})", ""]
    for v in qs:
        lines.append(f"- **{v['id']}** [{v['severity']}] {v['question']}  Look at: {v['look']}  (maps to {v['maps']})")
    lines += ["", "Do not fix anything. Do not loosen anything. Return a receipt of 15 lines or fewer; the detail is critic.json."]
    p = heal_dir(d) / "critic-brief.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def fix_brief(d: Path, root: Path = ROOT) -> Path:
    d = Path(d)
    cls = read_json(heal_dir(d) / "classified.json") or classify(d, root=root)
    cfg = load_config(root)
    st = status(d, root)
    lines = [f"# Fix brief: {d.name} ({cls['kind']})", "",
             f"Round {st['round']} of {st['max_rounds']} at most. Budget left: {st['minutes_left']} min, {st['tokens_left']} tokens.", "",
             "## Rules for the fixer", "- Fix the root cause named below, where the playbook says it belongs. One class at a time, creative faults to Opus, tool faults to Sonnet.",
             "- Never: " + ", ".join(cfg["forbidden_fix_kinds"]) + ". Frozen files: " + ", ".join(cfg["protected_paths"]["frozen"]) + ".",
             "- After the fix, rerun from the earliest `rerun_from` below (`shot.py <stage> <dir>` / `compose.py` / `artbook.py`), then the gate. Record each fix with `heal.py round`.",
             "- Playbooks: `kb/quality/heal-playbooks.md`. A new kind of fault: write what you learned in your receipt; `heal.py learn` turns it into a proposal.", "",
             f"## Faults ({len(cls['faults'])})", ""]
    if not cls["faults"]:
        lines.append("None.")
    for f in cls["faults"]:
        lines += [f"### {f['id']} [{f['severity']}] class {f['class']}",
                  f"- Check: {f['check'] or 'critic ' + str(f['question'])}  Frame: {f['frame']}  Source: {f['source']}",
                  f"- What: {f['detail']}", f"- Fix in: {', '.join(f['fix_in']) or 'find the root cause first'}  Fixer: {f['fixer']}  Rerun from: {f['rerun_from'] or 'the stage that owns it'}  Rules: {f['rules']}", ""]
    p = heal_dir(d) / "fix-brief.md"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


# ------------------------------------------------------------------ rounds and budget
def rounds(d: Path) -> list[dict]:
    return read_jsonl(heal_dir(d) / "rounds.jsonl")


def status(d: Path, root: Path = ROOT, now: float | None = None) -> dict:
    d = Path(d)
    cfg = load_config(root)
    rs = rounds(d)
    snap = read_json(heal_dir(d) / "snapshot.json") or {}
    now = now if now is not None else time.time()
    kind = (read_json(heal_dir(d) / "classified.json") or {}).get("kind") or detect_kind(d)
    per_stage = {}
    for r in rs:
        per_stage.setdefault(r.get("stage", "default"), set()).add(r["round"])
    mx = cfg["max_heal_rounds"].get(kind, cfg["max_heal_rounds"]["default"])
    elapsed = (now - snap["created"]) / 60 if snap.get("created") else 0.0
    tokens = sum(int(r.get("tokens", 0) or 0) for r in rs)
    cls = read_json(heal_dir(d) / "classified.json") or {}
    return {"kind": kind, "round": max((r["round"] for r in rs), default=0), "max_rounds": mx,
            "rounds_by_stage": {k: len(v) for k, v in per_stage.items()}, "records": len(rs),
            "minutes_used": round(elapsed, 1), "minutes_left": round(cfg["budget"]["max_minutes_per_build"] - elapsed, 1),
            "tokens_used": tokens, "tokens_left": cfg["budget"]["max_tokens_per_build"] - tokens,
            "dispatches": len({r["round"] for r in rs}), "max_dispatches": cfg["budget"]["max_fix_dispatches_per_build"],
            "open_faults": [f for f in cls.get("faults", [])], "score": cls.get("score"), "ready_for_owner": bool(cls.get("ready_for_owner")),
            "stopped": (heal_dir(d) / "STOPPED.md").is_file()}


def _stop_report(d: Path, reason: str, root: Path) -> None:
    cls = read_json(heal_dir(d) / "classified.json") or {}
    lines = ["# Heal stopped: BLOCKED", "", f"Reason: {reason}", "",
             "The build is not done and is not shown to the owner as done. No gate was loosened.", "", "## Remaining faults", ""]
    for f in cls.get("faults", []):
        lines.append(f"- {f['id']} [{f['severity']}] {f['class']}: {f['detail']} (check {f['check'] or f['question']}, frame {f['frame']})")
    if not cls.get("faults"):
        lines.append("- (none listed; the score or the critic was the blocker)")
    (heal_dir(d) / "STOPPED.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def record_round(d: Path, fault: str, fix: str, kind: str, files: list[str] | None = None, result: str = "pending", stage: str | None = None,
                 tokens: int = 0, cls_override: str | None = None, new_round: bool = False, root: Path = ROOT, now: float | None = None) -> dict:
    """Record one fix. Refuses (HealRefused) a forbidden fix, a protected file, and a round past the limits or the budget."""
    d = Path(d)
    files = files or []
    cfg = load_config(root)
    bad = check_declared(files, kind, root, d)
    snap = read_json(heal_dir(d) / "snapshot.json")
    if snap is not None:
        bad += guard(d, root)
    if bad:
        raise HealRefused(4, "forbidden fix refused: " + "; ".join(bad))
    cls = read_json(heal_dir(d) / "classified.json") or {}
    f = next((x for x in cls.get("faults", []) if x["id"] == fault), None)
    pbs = load_playbooks(root)
    if cls_override:
        cn = cls_override
    else:
        cn = f["class"] if f else "UNKNOWN"
    if cn not in {p["class"] for p in pbs}:
        raise HealRefused(2, f"unknown class {cn!r}")
    st = status(d, root, now)
    stage = stage or st["kind"]
    rs = rounds(d)
    cur = st["round"] or 1
    if new_round and rs:
        cur += 1
    mx = cfg["max_heal_rounds"].get(stage, cfg["max_heal_rounds"]["default"])
    stage_rounds = {r["round"] for r in rs if r.get("stage", stage) == stage} | {cur}
    over = None
    if len(stage_rounds) > mx:
        over = f"max_heal_rounds for {stage} is {mx}"
    elif len({r["round"] for r in rs} | {cur}) > cfg["budget"]["max_fix_dispatches_per_build"]:
        over = f"max_fix_dispatches_per_build is {cfg['budget']['max_fix_dispatches_per_build']}"
    elif st["minutes_left"] <= 0:
        over = f"time budget of {cfg['budget']['max_minutes_per_build']} min is used"
    elif st["tokens_used"] + tokens > cfg["budget"]["max_tokens_per_build"]:
        over = f"token budget of {cfg['budget']['max_tokens_per_build']} is used"
    if over:
        _stop_report(d, over, root)
        raise HealRefused(3, f"budget: {over}. Stop and report the remaining faults (heal/STOPPED.md); never loosen a gate.")
    rec = {"round": cur, "stage": stage, "fault": fault, "class": cn, "check": (f or {}).get("check"), "question": (f or {}).get("question"),
           "severity": (f or {}).get("severity"), "detail": (f or {}).get("detail"), "fix": fix, "kind": kind, "files": files, "result": result,
           "tokens": int(tokens or 0), "at": dt.datetime.fromtimestamp(now if now is not None else time.time()).isoformat(timespec="seconds")}
    append_jsonl(heal_dir(d) / "rounds.jsonl", rec)
    return rec


# ------------------------------------------------------------------ learn
def ledger_path(root: Path = ROOT) -> Path:
    return root / "kb" / "lessons" / "ledger.jsonl"


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "fault"


def learn(d: Path, build: str | None = None, root: Path = ROOT, date: str | None = None) -> dict:
    """Healed faults -> the lessons ledger. A fault of a new kind (no class, a NEW critic fault, a gate blind spot) also gets a proposal."""
    d = Path(d)
    build = build or d.name
    date = date or dt.date.today().isoformat()
    lp = ledger_path(root)
    ledger = read_jsonl(lp)
    seen = {(e.get("build"), e.get("fault"), e.get("summary")) for e in ledger}
    n = len(ledger)
    pbs = {p["class"]: p for p in load_playbooks(root)}
    added, proposals = [], []
    for r in rounds(d):
        if r.get("result") != "fixed":
            continue
        key = (build, r["fault"], r.get("detail") or r["fix"])
        if key in seen:
            continue
        pb = pbs.get(r["class"], pbs.get("UNKNOWN", {}))
        n += 1
        entry = {"id": f"L-{n:04d}", "date": date, "build": build, "stage": r.get("stage"), "fault": r["fault"], "summary": r.get("detail") or r["fix"],
                 "class": r["class"], "root_cause": r.get("root_cause") or f"see kb/quality/heal-playbooks.md#{r['class'].lower()}", "fix": r["fix"],
                 "fix_kind": r["kind"], "files": r.get("files", []), "rule": pb.get("rules", ""), "check": r.get("check") or (f"critic:{r['question']}" if r.get("question") else "human look"),
                 "source": "heal", "status": "healed"}
        if r["class"] in ("UNKNOWN", "GATE-BLIND") or r.get("question") == "NEW":
            entry["proposal"] = _write_proposal(root, entry, r)
            proposals.append(entry["proposal"])
        append_jsonl(lp, entry)
        seen.add(key)
        added.append(entry["id"])
    return {"added": added, "proposals": proposals}


def _write_proposal(root: Path, entry: dict, r: dict) -> str:
    pd = root / "kb" / "lessons" / "proposals"
    pd.mkdir(parents=True, exist_ok=True)
    n = len(list(pd.glob("P-*.md"))) + 1
    pid = f"P-{n:04d}-{_slug(entry['fault'] + '-' + entry['summary'])}"
    p = pd / f"{pid}.md"
    p.write_text("\n".join([
        f"# Proposal {pid}", "", f"Status: open (the Lead merges or rejects). From ledger entry {entry['id']}, build {entry['build']}, {entry['date']}.", "",
        "## The fault", entry["summary"], "", "## Root cause (as found by the fixer)", entry["root_cause"], "",
        "## What fixed it", entry["fix"], "Files: " + (", ".join(entry["files"]) or "none listed"), "",
        "## New rule text (fill in, one sentence, with its why)", "R-???: ", "",
        "## New check design (what to measure, from which data, the threshold and its source)", f"Class {entry['class']}. A check that would have failed this build before the fix: ", "",
        "## Test idea (a fixture that fails before the fix and passes after)", "", ""]), encoding="utf-8")
    return p.relative_to(root).as_posix()


# ------------------------------------------------------------------ prepare (what the stage tools call)
def prepare(d: Path, kind: str | None = None, root: Path = ROOT, log=print) -> dict | None:
    """Optional `heal` stage: runs after gate/review when pipelines/heal.json says enabled. Never fails the stage."""
    if not enabled(root):
        log("heal: disabled in pipelines/heal.json")
        return None
    d = Path(d)
    kind = kind or detect_kind(d)
    res = classify(d, kind, root)
    critic_brief(d, kind, root)
    if res["faults"]:
        fix_brief(d, root)
    log(f"heal [{kind}] {d.name}: {len(res['faults'])} open fault(s), critic {'score ' + str(res['score']) if res['critic_present'] else 'not run yet'}, ready for the owner: {'YES' if res['ready_for_owner'] else 'NO'}")
    log(f"heal next: {res['next']}")
    log(f"heal files: {heal_dir(d)}/ (critic-brief.md{', fix-brief.md' if res['faults'] else ''}, classified.json)")
    return res


# ------------------------------------------------------------------ cli
def _print_status(s: dict) -> None:
    print(f"kind {s['kind']}  round {s['round']}/{s['max_rounds']}  records {s['records']}  dispatches {s['dispatches']}/{s['max_dispatches']}")
    print(f"budget: {s['minutes_used']} min used ({s['minutes_left']} left), {s['tokens_used']} tokens used ({s['tokens_left']} left)")
    print(f"score {s['score']}  ready for the owner: {'YES' if s['ready_for_owner'] else 'NO'}" + ("  STOPPED (see heal/STOPPED.md)" if s["stopped"] else ""))
    for f in s["open_faults"]:
        print(f"  open {f['id']} [{f['severity']}] {f['class']}: {f['detail'][:110]}")
    if not s["open_faults"]:
        print("  no open faults")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="heal.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["classify", "critic-brief", "validate-critic", "fix-brief", "round", "guard", "learn", "status", "prepare"])
    ap.add_argument("dir")
    ap.add_argument("--kind", choices=KINDS)
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--fault")
    ap.add_argument("--fix")
    ap.add_argument("--files", nargs="*", default=[])
    ap.add_argument("--result", choices=["fixed", "partial", "failed", "pending"], default="pending")
    ap.add_argument("--stage")
    ap.add_argument("--tokens", type=int, default=0)
    ap.add_argument("--build")
    ap.add_argument("--class", dest="cls")
    ap.add_argument("--new-round", action="store_true")
    ap.add_argument("--fix-kind", dest="fix_kind", default=None)
    a = ap.parse_args(argv)
    d, root = Path(a.dir).resolve(), a.root.resolve()
    try:
        if a.cmd == "classify":
            res = classify(d, a.kind, root)
            for f in res["faults"]:
                print(f"{f['id']} [{f['severity']}] {f['class']:18s} {f['check'] or f['question']}  -> fix in {','.join(f['fix_in'])} ({f['fixer']}), rerun from {f['rerun_from']}")
            print(f"{len(res['faults'])} fault(s); critic {'valid, score ' + str(res['score']) if res['critic_present'] and not res['critic_errors'] else ('INVALID' if res['critic_present'] else 'not run')}; ready for the owner: {'YES' if res['ready_for_owner'] else 'NO'}")
            print("next:", res["next"])
            return 0 if res["ready_for_owner"] else 1
        if a.cmd == "critic-brief":
            print(critic_brief(d, a.kind, root))
            return 0
        if a.cmd == "fix-brief":
            print(fix_brief(d, root))
            return 0
        if a.cmd == "validate-critic":
            c = read_json(heal_dir(d) / "critic.json")
            if c is None:
                print("FAIL no heal/critic.json")
                return 1
            errs, sc = validate_critic(c, a.kind or detect_kind(d), root)
            for e in errs:
                print("FAIL", e)
            print(("INVALID" if errs else "VALID") + f" effective score {sc}")
            return 1 if errs else 0
        if a.cmd == "guard":
            bad = guard(d, root)
            for b in bad:
                print("FORBIDDEN", b)
            print("guard: " + ("REFUSED" if bad else "clean"))
            return 4 if bad else 0
        if a.cmd == "round":
            if not a.fault or not a.fix:
                print("round needs --fault and --fix")
                return 2
            rec = record_round(d, a.fault, a.fix, a.fix_kind or "scene", a.files, a.result, a.stage, a.tokens, a.cls, a.new_round, root)
            print(f"round {rec['round']} recorded: {rec['fault']} [{rec['class']}] {rec['result']}")
            return 0
        if a.cmd == "learn":
            r = learn(d, a.build, root)
            print(f"ledger: +{len(r['added'])} {r['added']}  proposals: {r['proposals']}")
            return 0
        if a.cmd == "status":
            s = status(d, root)
            _print_status(s)
            return 0 if s["ready_for_owner"] else 1
        if a.cmd == "prepare":
            res = prepare(d, a.kind, root)
            return 0 if res is None or res["ready_for_owner"] else 1
    except HealRefused as e:
        print(f"{'STOP' if e.code == 3 else 'REFUSED'} {e.msg}")
        return e.code
    return 2


if __name__ == "__main__":
    sys.exit(main())
