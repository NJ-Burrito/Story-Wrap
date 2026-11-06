"""Voice first: a piece takes its line timing from the real voice outputs, never from script estimates (E01 run 1: pieces were cut to estimated
line lengths and the measured takes were far from them).

Spec field `voice_lines[]` (top level of shot-spec.json; the piece's plan/spec.py writes the references, the spec stage resolves them):
  {"line": "L03", "start_s": 0.4, "speaker": "guide", "on_screen": true, "spans_out": false, "visemes": true}
    line      id in the episode's script.json; the take is work/voice/<ep>/<line>.trimmed.wav (else <line>.wav), the visemes visemes/<line>.json
    start_s   seconds from the START OF THE PIECE where the line begins (negative = a J-cut: it began in the piece before; then spans_in is true)
    spans_out true when the line deliberately runs on into the next piece (an L-cut); otherwise it must end inside the piece
    visemes   false for an off-screen voice (no mouth to move); default true
Resolved by the spec stage (tools/shot.py `spec`, `resolve()`), written back into the spec: dur_s (measured), end_s, take (repo path), take_sha256,
viseme_keys (the track's keys moved onto the piece clock: t + start_s). Check id SPEC-VOICE-TIMING (kb/quality/gate-spec.md) fails when a referenced
line has no measured take (or no viseme track), when a stored dur_s no longer matches the take, or when a line outruns its piece.
compose.py reads the same field: the line is placed where the piece says (PLAN-VOICE-OFFSET if the shotlist disagrees).
"""
from __future__ import annotations
import hashlib, json, wave
from pathlib import Path

CHECK_ID = "SPEC-VOICE-TIMING"
TOL_S = 0.02            # a stored dur_s may differ from the take by this much (rounding), not more
FIT_TOL_S = 0.05        # a line may end this far past the piece end (the same slack compose uses, PLAN-LINE-TIMELINE)


class VoiceTimingError(Exception):
    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("; ".join(problems))


def voice_dir(root, episode: str) -> Path:
    return Path(root) / "work" / "voice" / episode


def take_path(root, episode: str, line: str) -> Path | None:
    d = voice_dir(root, episode)
    for name in (f"{line}.trimmed.wav", f"{line}.wav"):   # the end-trimmed take is the one compose uses (VOICE.md)
        if (d / name).is_file():
            return d / name
    return None


def wav_seconds(p: Path) -> float:
    with wave.open(str(p), "rb") as w:
        return w.getnframes() / w.getframerate()


def take(root, episode: str, line: str, need_visemes: bool = True) -> dict:
    """The measured take of one line: {line, dur_s, take, take_sha256, viseme_keys[{t, id}], viseme_fps}. Raises VoiceTimingError when it does not exist."""
    root = Path(root)
    p = take_path(root, episode, line)
    if p is None:
        raise VoiceTimingError([f"line {line}: no measured take in work/voice/{episode}/ ({line}.trimmed.wav or {line}.wav); voice the line first, the piece cannot be timed from an estimate"])
    try:
        rel = p.relative_to(root).as_posix()
    except ValueError:
        rel = str(p)
    out = {"line": line, "dur_s": round(wav_seconds(p), 3), "take": rel, "take_sha256": hashlib.sha256(p.read_bytes()).hexdigest()[:16]}
    vp = voice_dir(root, episode) / "visemes" / f"{line}.json"
    if vp.is_file():
        v = json.loads(vp.read_text(encoding="utf-8"))
        out["viseme_keys"] = [{"t": float(k["t"]), "id": k["id"]} for k in v.get("keys", [])]
        out["viseme_fps"] = v.get("fps")
    elif need_visemes:
        raise VoiceTimingError([f"line {line}: no viseme track work/voice/{episode}/visemes/{line}.json (run the voice stage; or set visemes false for an off-screen voice)"])
    return out


def resolve(spec: dict, root, episode: str | None = None, duration_s: float | None = None) -> dict:
    """Fill every spec['voice_lines'] entry from the voice outputs. Raises VoiceTimingError listing every problem (all lines, not just the first)."""
    ep = episode or spec.get("voice_episode")
    entries = spec.get("voice_lines") or []
    probs: list[str] = []
    if entries and not ep:
        raise VoiceTimingError(["voice_lines is set but the spec names no voice_episode (and shot.json has no piece.episode)"])
    if duration_s is None:
        ends = [float(b.get("end", 0)) for b in spec.get("beats", [])]
        duration_s = max(ends) if ends else None
    for e in entries:
        lid = e.get("line")
        if not lid or e.get("start_s") is None:
            probs.append(f"voice_lines entry {e!r} needs line and start_s"); continue
        try:
            t = take(root, ep, lid, need_visemes=e.get("visemes", True) is not False and e.get("on_screen", True) is not False)
        except VoiceTimingError as x:
            probs += x.problems; continue
        s0 = float(e["start_s"])
        e.update({"dur_s": t["dur_s"], "end_s": round(s0 + t["dur_s"], 3), "take": t["take"], "take_sha256": t["take_sha256"], "spans_in": s0 < 0})
        if "viseme_keys" in t:
            e["viseme_keys"] = [{"t": round(k["t"] + s0, 3), "id": k["id"]} for k in t["viseme_keys"]]
        if duration_s is not None and e["end_s"] > duration_s + FIT_TOL_S and not e.get("spans_out"):
            probs.append(f"line {lid} runs {s0:.2f}-{e['end_s']:.2f} s but the piece is {duration_s:.2f} s: lengthen the piece to {e['end_s']:.2f} s or more, or set spans_out true for a deliberate L-cut")
    if probs:
        raise VoiceTimingError(probs)
    return spec


def referenced_lines(spec: dict) -> set[str]:
    """Every line id the spec's beats name as spoken (emotion_track.voice.line, also under actor_emotions)."""
    out: set[str] = set()

    def walk(o):
        if isinstance(o, dict):
            v = o.get("voice")
            if isinstance(v, dict) and v.get("line"):
                out.add(str(v["line"]))
            for x in o.values():
                walk(x)
        elif isinstance(o, list):
            for x in o:
                walk(x)
    walk(spec.get("beats", []))
    return out


def issues(spec: dict, root=None, files: bool = False) -> list[str]:
    """Messages for the SPEC-VOICE-TIMING check (qg_checks wraps them). Applies only to a spec that opts into voice-first (voice_episode or voice_lines)."""
    if "voice_lines" not in spec and "voice_episode" not in spec:
        return []
    out: list[str] = []
    entries = spec.get("voice_lines") or []
    ids = [e.get("line") for e in entries]
    if len(set(ids)) != len(ids):
        out.append("voice_lines names a line twice")
    missing = sorted(referenced_lines(spec) - set(ids))
    if missing:
        out.append(f"beats name spoken line(s) {missing} that voice_lines does not reference: reference each with its start_s so the piece is timed from the voice")
    ends = [float(b.get("end", 0)) for b in spec.get("beats", [])]
    dur = max(ends) if ends else None
    for e in entries:
        lid = e.get("line")
        if not lid or not isinstance(e.get("start_s"), (int, float)):
            out.append(f"voice_lines entry {lid!r} needs a line id and a numeric start_s"); continue
        if not isinstance(e.get("dur_s"), (int, float)) or e["dur_s"] <= 0:
            out.append(f"line {lid} has no measured dur_s: the spec stage resolves it from work/voice (no estimate is accepted)"); continue
        if abs(e.get("end_s", -1) - (e["start_s"] + e["dur_s"])) > 0.002:
            out.append(f"line {lid} end_s {e.get('end_s')} is not start_s + dur_s")
        if dur is not None and e.get("end_s", 0) > dur + FIT_TOL_S and not e.get("spans_out"):
            out.append(f"line {lid} ends at {e['end_s']:.2f} s, after the piece ({dur:.2f} s), and spans_out is not set")
        if e.get("visemes", True) is not False and e.get("on_screen", True) is not False and not e.get("viseme_keys"):
            out.append(f"line {lid} is on screen but carries no viseme_keys")
        if files and root is not None and spec.get("voice_episode"):
            p = take_path(Path(root), spec["voice_episode"], lid)
            if p is None:
                out.append(f"line {lid}: the take is gone from work/voice/{spec['voice_episode']}/")
            elif abs(wav_seconds(p) - e["dur_s"]) > TOL_S:
                out.append(f"line {lid}: stored dur_s {e['dur_s']} s but the take is {wav_seconds(p):.3f} s (re-run the spec stage; the voice changed)")
    return out
