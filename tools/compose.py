# /// script
# requires-python = ">=3.11"
# dependencies = ["playwright", "pillow", "numpy", "jsonschema"]
# ///
"""Story-Wrap composing stage: ONE resumable path from an episode's script + shot renders to a gated Reel.

  uv run tools/compose.py init     <series>/<ep>          scaffold outline.md + shotlist.json (never overwrites)
  uv run tools/compose.py plan     <ep>                   validate shotlist vs script, timeline, 30-60 s        -> work/episodes/<ep>/plan.json
  uv run tools/compose.py audio    <ep> [--silent]        voice takes + SFX + music bed, ducking, loudness      -> audio/mix.wav, audio/audio.json
  uv run tools/compose.py captions <ep>                   Arabic caption plates, RTL, Thmanyah, safe zones      -> captions/*.png, captions.json
  uv run tools/compose.py assemble <ep>                   shots + transitions + captions + audio, NVENC         -> assembled.mp4
  uv run tools/compose.py end      <ep>                   choice end card appended                              -> end/card.png, end.json, episode.mp4
  uv run tools/compose.py gate     <ep> [--skip-render-gate]   EP-* checks + tools/quality_gate.py render       -> gate/report.json
  uv run tools/compose.py preview  <ep> [--page previews/index.html]   add/update the episode tab
  uv run tools/compose.py all      <ep>                   plan, audio, captions, assemble, end, gate
  uv run tools/compose.py status   <ep>
  uv run tools/compose.py licence-add --id ID --file PATH --kind music|sfx --licence CC0|PD|CC-BY|CC-BY-SA|OWN --source URL --retrieved DATE [--credit TEXT]

<ep> is an episode folder, `<series>/<ep>`, or a bare id such as E01 (searched under bible/series/*/episodes/).
Each stage writes its files and records status + input hashes in work/episodes/<ep>/STATE.json (same engine as shot.py):
a rerun skips a finished stage whose inputs did not change; `--force` reruns. A failed stage prints `FAIL [CHECK-ID] message`.
Exit 0 = ok, 1 = a stage failed, 2 = usage or tool error. GPU first: NVDEC decode, NVENC encode (NJ_COMPOSE_CPU=1 forces
libx264, tests only); ffmpeg always `-threads 2`. Audio filters have no GPU path; they run on 2 threads. No network, no model.
Pipeline text: pipelines/COMPOSE.md. Check ids: kb/quality/gate-spec.md section F.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
import wave
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parent
sys.path.insert(0, str(TOOLS))
from arabic_display import display_text, has_tashkeel   # noqa: E402
import qg_checks as qc   # noqa: E402  (format profile: qc.format_of, qc.check_calm_declared)
from shotlib.engine import Stage, StageFail, State, hash_inputs, run_stage   # noqa: E402

ENV = {**os.environ, "PYTHONUTF8": "1"}
DEFAULT_SERIES = "series"

# ------------------------------------------------------------------ constants (every number says where it comes from)
SOUND = json.loads((TOOLS / "sound_profile.json").read_text(encoding="utf-8"))   # the one sound profile (2026-10-26); values unchanged
LOUD_TARGET_I = SOUND["delivery"]["instagram"]["lufs_target"]      # LUFS. MEASURED on delivered Instagram renditions of 3 of the 4 benchmark reels: -14.1 (A, B, baseline 1),
                           # baseline 2 -14.6 (kb/guides/reels.md section 3, research/10). Instagram states no number (gap, reels.md section 1).
LOUD_TOL = SOUND["delivery"]["instagram"]["tolerance_lu"]             # LU, house default: gate passes -15..-13 LUFS
LOUD_TP_MAX = SOUND["delivery"]["instagram"]["true_peak_max_dbtp"]         # dBTP gate ceiling, house default; the mix targets -1.5 so AAC re-encode headroom exists (baseline 2 peaked +0.1)
LOUD_TP_TARGET = SOUND["master"]["true_peak_target_dbtp"]
LOUD_LRA = SOUND["master"]["compose_lra"]            # loudnorm default LRA
VOICE_LUFS = SOUND["compose"]["voice_lufs"]         # nj-kit:bg-music rule 2 ("voice is -16, bed is -23")
BED_LUFS = SOUND["compose"]["bed_lufs"]
SFX_GAIN_DB = SOUND["compose"]["sfx_gain_db"]        # house default per cue, "to be tuned by ear" (bg-music reference/sfx-practice.md)
DUCK_BED, DUCK_SFX = SOUND["compose"]["duck_bed"], SOUND["compose"]["duck_sfx"]
CALM_LEN_MIN = 5.0         # calm format: "length: whatever suits the story" (the owner 2026-10-24); only a sanity floor
CALM_PLATE_MIN_S = 0.15    # calm word-by-word plates (1-3 words) change about twice a second in the measured reels
LEN_MIN, LEN_MAX = 30.0, 60.0   # the owner 2026-10-22; Instagram's own advice 30-60 s (reels.md section 1)
HOOK_WINDOW = 2.0          # reels.md section 2: a moving element and a story event in 0-2 s
# Reels UI zones as fractions of the canvas: top 14 %, bottom 35 % (third-party attribution to Meta, UNVERIFIED: open question Q-05).
SAFE = {"top": 0.14, "bottom": 0.35, "side": 0.05}   # side 5 % is a house default
CAP_FONT_MIN = 40          # px at 1080 wide, house default
CONTRAST_MIN = 4.5         # WCAG 2.x AA for normal text
EST_LETTERS_PER_S = 12.0   # house default for a line with no take yet; replaced by the take's length once voiced
CAP_GAP = 0.04             # s between consecutive caption plates
LICENCES = {"CC0", "PD", "CC-BY", "CC-BY-SA", "OWN"}   # NC and ND are refused (bg-music: a rendered deliverable is commercial and every edit is a derivative)
XFADE = {"fade", "fadeblack", "fadewhite", "dissolve", "wipeleft", "wiperight", "wipeup", "wipedown", "slideleft", "slideright",
         "slideup", "slidedown", "circleopen", "circleclose", "smoothleft", "smoothright", "pixelize", "hblur"}
ALIAS = {"dip": "fadeblack", "wipe": "wipeleft"}
AR_LETTER = re.compile("[ء-غف-يٱ]")
FONTS = REPO / "assets" / "fonts"


# ------------------------------------------------------------------ small helpers
def read_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def write_json(p, obj):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, p)


def run(cmd, check=True, cwd=None):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV, cwd=cwd)
    if check and r.returncode != 0:
        raise StageFail("TOOL-ERROR", f"{Path(str(cmd[0])).name} exited {r.returncode}: {(r.stderr or r.stdout)[-700:]}")
    return r


def ff(args, check=True):
    return run(["ffmpeg", "-hide_banner", "-nostdin", "-y", "-filter_threads", "2", "-filter_complex_threads", "2", *args], check)


def probe(path, entries="format=duration"):
    r = run(["ffprobe", "-v", "error", "-show_entries", entries, "-of", "json", path])
    return json.loads(r.stdout)


def duration(path) -> float:
    return float(probe(path)["format"]["duration"])


def has_audio(path) -> bool:
    return any(s.get("codec_type") == "audio" for s in probe(path, "stream=codec_type").get("streams", []))


def video_info(path) -> dict:
    s = probe(path, "stream=width,height,r_frame_rate,codec_type")["streams"]
    v = next(x for x in s if x.get("codec_type") == "video")
    n, d = v["r_frame_rate"].split("/")
    return {"w": int(v["width"]), "h": int(v["height"]), "fps": float(n) / float(d or 1)}


def wav_seconds(path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


def ar_letters(text: str) -> int:
    return len(AR_LETTER.findall(text or ""))


def estimate_seconds(text: str) -> float:
    return round(max(0.8, ar_letters(text) / EST_LETTERS_PER_S + 0.25), 3)


def nvenc_wanted() -> bool:
    return os.environ.get("NJ_COMPOSE_CPU") != "1"


def venc_args() -> list:
    if nvenc_wanted():
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-tune", "hq", "-rc", "vbr", "-cq", "19", "-b:v", "0", "-maxrate", "12M",
                "-bufsize", "24M", "-profile:v", "high", "-pix_fmt", "yuv420p", "-threads", "2"]
    return ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "20", "-pix_fmt", "yuv420p", "-threads", "2"]


def hw_in() -> list:
    return ["-hwaccel", "cuda"] if nvenc_wanted() else []


def rel(p, base=REPO) -> str:
    try:
        return Path(p).resolve().relative_to(Path(base).resolve()).as_posix()
    except ValueError:
        return Path(p).as_posix()


# ------------------------------------------------------------------ episode context
class Ep:
    def __init__(self, d: Path, repo: Path):
        self.repo, self.dir, self.name = repo, d, d.name
        self.series = d.parent.parent.name if d.parent.name == "episodes" else DEFAULT_SERIES
        self.script, self.shotlist, self.outline = d / "script.json", d / "shotlist.json", d / "outline.md"
        self.work = repo / "work" / "episodes" / self.name
        self.voice_dir = repo / "work" / "voice" / self.name
        self.manifest = d / "narration-manifest.json"
        self.plan_p, self.audio_p, self.caps_p, self.end_p = self.work / "plan.json", self.work / "audio" / "audio.json", self.work / "captions.json", self.work / "end" / "end.json"
        self.mix = self.work / "audio" / "mix.wav"
        self.assembled, self.card, self.episode = self.work / "assembled.mp4", self.work / "end" / "card.png", self.work / "episode.mp4"
        self.overlay = self.work / "end" / "overlay.png"      # live backdrop: the card on a transparent ground (card.png = this over white, the worst case)
        self.gate_p = self.work / "gate" / "report.json"
        self.licences = repo / "assets" / "audio" / "LICENCES.md"


def resolve_episode(arg: str, repo: Path = REPO) -> Ep:
    cands = [Path(arg), repo / arg, repo / "bible" / "series" / arg / ""]
    ser = repo / "bible" / "series"
    if "/" not in arg.replace("\\", "/") and ser.is_dir():
        cands += sorted(ser.glob(f"*/episodes/{arg}"))
    elif ser.is_dir():
        s, e = arg.replace("\\", "/").split("/", 1)
        cands.append(ser / s / "episodes" / e)
    for c in cands:
        if c.is_dir() and ((c / "shotlist.json").exists() or (c / "script.json").exists() or c.parent.name == "episodes"):
            return Ep(c.resolve(), repo)
    raise StageFail("EP-NOT-FOUND", f"episode {arg!r} not found (folder, <series>/<ep>, or an id under bible/series/*/episodes/)")


# ------------------------------------------------------------------ licence register
def parse_licences(path: Path) -> dict:
    """assets/audio/LICENCES.md table rows: id | file | kind | licence | credit | source | retrieved | sha256."""
    out = {}
    if not Path(path).is_file():
        return out
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.lstrip().startswith("|"):
            continue
        c = [x.strip() for x in line.strip().strip("|").split("|")]
        if len(c) < 7 or not c[0] or c[0].lower() in ("id", "") or set(c[0]) <= set("-: ") or c[0].startswith("<"):
            continue
        out[c[0]] = {"id": c[0], "file": c[1], "kind": c[2], "licence": c[3].upper().replace(" ", "-"), "credit": c[4],
                     "source": c[5], "retrieved": c[6], "sha256": (c[7] if len(c) > 7 else "")}
    return out


def licence_problem(reg: dict, lid: str, file: Path | None = None) -> str | None:
    r = reg.get(lid)
    if not r:
        return f"licence id {lid!r} is not in assets/audio/LICENCES.md"
    if r["licence"] not in LICENCES:
        return f"{lid}: licence {r['licence']!r} is not allowed (allowed: {', '.join(sorted(LICENCES))}; NC and ND are refused)"
    if r["licence"] in ("CC-BY", "CC-BY-SA") and not r["credit"]:
        return f"{lid}: {r['licence']} needs a credit line"
    if r["licence"] != "OWN" and not (r["source"] and r["retrieved"]):
        return f"{lid}: source URL and retrieved date are required"
    if file is not None and r["sha256"] and file.is_file():
        import hashlib
        if hashlib.sha256(file.read_bytes()).hexdigest()[:len(r["sha256"])] != r["sha256"]:
            return f"{lid}: file {file.name} does not match the recorded sha256 (the register describes a different file)"
    return None


def cmd_licence_add(a, repo: Path = REPO) -> int:
    import hashlib
    f = Path(a.file)
    f = f if f.is_absolute() else repo / f
    if not f.is_file():
        print(f"FAIL [LICENCE-FILE] {f} not found")
        return 1
    lic = a.licence.upper()
    if lic not in LICENCES:
        print(f"FAIL [LICENCE-KIND] {lic} is not allowed ({', '.join(sorted(LICENCES))})")
        return 1
    reg_p = repo / "assets" / "audio" / "LICENCES.md"
    if a.id in parse_licences(reg_p):
        print(f"FAIL [LICENCE-DUP] id {a.id} already in the register")
        return 1
    row = f"| {a.id} | {rel(f, repo)} | {a.kind} | {lic} | {a.credit or ''} | {a.source} | {a.retrieved} | {hashlib.sha256(f.read_bytes()).hexdigest()[:16]} |\n"
    with open(reg_p, "a", encoding="utf-8") as fh:
        fh.write(row)
    print("added", a.id)
    return 0


# ------------------------------------------------------------------ shotlist, timeline
def load_schema():
    return read_json(REPO / "kb" / "quality" / "shotlist.schema.json")


def load_inputs(ep: Ep):
    for p, cid in ((ep.script, "PLAN-SCRIPT"), (ep.shotlist, "PLAN-SHOTLIST")):
        if not p.is_file():
            raise StageFail(cid, f"{p} not found")
    script, sl = read_json(ep.script), read_json(ep.shotlist)
    import jsonschema
    errs = sorted(jsonschema.Draft202012Validator(load_schema()).iter_errors(sl), key=lambda e: list(e.path))
    if errs:
        e = errs[0]
        raise StageFail("PLAN-SHOTLIST", f"{'/'.join(map(str, e.path)) or 'shotlist'}: {e.message} ({len(errs)} schema problem(s))")
    if not script.get("lines"):
        raise StageFail("PLAN-SCRIPT", "script.json has no lines")
    return script, sl


def shot_video(ep: Ep, shot: dict) -> Path:
    folder = Path(shot["folder"])
    folder = folder if folder.is_absolute() else ep.repo / folder
    v = shot.get("video") or f"out/{folder.name}.mp4"
    v = Path(v)
    return v if v.is_absolute() else folder / v


def tkind(t: dict) -> tuple[str, float]:
    ty = ALIAS.get(t["type"], t["type"])
    return ("cut", 0.0) if ty == "cut" or t["frames"] == 0 else (ty, t["frames"])


def timeline(sl: dict) -> dict:
    """Shot start/end on the episode clock. A transition of d seconds overlaps the two shots by d."""
    fps = sl["fps"]
    tr = {(t["from"], t["to"]): t for t in sl.get("transitions", [])}
    shots, cursor, prev = [], 0.0, None
    for s in sl["shots"]:
        dur = (s["out_frame"] - s["in_frame"]) / fps
        t = tr.get((prev["id"], s["id"])) if prev else None
        ty, fr = tkind(t) if t else ("cut", 0.0)
        d = fr / fps
        start = round(cursor - d, 6) if prev else 0.0
        shots.append({"id": s["id"], "start": start, "dur": round(dur, 6), "end": round(start + dur, 6),
                      "in": s["in_frame"], "out": s["out_frame"], "trans_in": {"type": ty, "dur": round(d, 6)} if prev else None,
                      "declared": bool(t) or prev is None})
        cursor = start + dur
        prev = s
    picture = shots[-1]["end"] if shots else 0.0
    endd = float(sl.get("end_card", {}).get("duration_s", 0))
    return {"shots": shots, "picture_s": round(picture, 6), "end_card_s": endd, "total_s": round(picture + endd, 6)}


def take_path(ep: Ep, line_id: str) -> Path:
    """The take the episode uses: the end-trimmed one when it exists (VOICE.md), else the raw take."""
    t = ep.voice_dir / f"{line_id}.trimmed.wav"
    return t if t.is_file() else ep.voice_dir / f"{line_id}.wav"


def voice_files(ep: Ep, script: dict) -> dict:
    return {l["id"]: take_path(ep, l["id"]) for l in script["lines"] if take_path(ep, l["id"]).is_file()}


def voice_mode(ep: Ep, script: dict, silent=False) -> str:
    n, have = len(script["lines"]), len(voice_files(ep, script))
    if silent or have == 0:
        return "no-voice-yet"
    if have < n:
        raise StageFail("AUDIO-PARTIAL", f"{have} of {n} lines have a take; a partly voiced episode is the owner's decision (VOICE.md). Use --silent for the caption-only proof")
    return "voice"


def line_duration(ep: Ep, line: dict, placed: dict, mode: str) -> tuple[float, str]:
    wav = take_path(ep, line["id"])
    if mode == "voice" and wav.is_file():
        return round(wav_seconds(wav), 3), "take"
    if placed.get("est_dur_s"):
        return float(placed["est_dur_s"]), "shotlist est_dur_s"
    return estimate_seconds(line.get("text", "")), f"estimate ({EST_LETTERS_PER_S:g} letters/s house default)"


def spec_voice_entry(ep: Ep, shot: dict, line_id: str):
    """The shot spec's voice_lines entry for a line (voice first, tools/shotlib/voicetiming.py), or None when the piece has no spec or no entry."""
    folder = Path(shot["folder"])
    sp = (folder if folder.is_absolute() else ep.repo / folder) / "shot-spec.json"
    if not sp.is_file():
        return None
    try:
        spec = read_json(sp)
    except Exception:
        return None
    return next((e for e in spec.get("voice_lines") or [] if e.get("line") == line_id), None)


# ------------------------------------------------------------------ stage: plan
def stage_plan(ep: Ep, silent=False) -> dict:
    script, sl = load_inputs(ep)
    tl = timeline(sl)
    ids = [s["id"] for s in sl["shots"]]
    for s in sl["shots"]:
        if s["out_frame"] <= s["in_frame"]:
            raise StageFail("PLAN-FRAMES", f"shot {s['id']}: out_frame {s['out_frame']} must be greater than in_frame {s['in_frame']}")
    if len(set(ids)) != len(ids):
        raise StageFail("PLAN-SHOT-ID", "duplicate shot ids")
    by_id = {l["id"]: l for l in script["lines"]}
    warns, mode = [], voice_mode(ep, script, silent)
    # transitions: every adjacent pair declared, frames fit inside both shots
    for i in range(1, len(sl["shots"])):
        a, b = sl["shots"][i - 1]["id"], sl["shots"][i]["id"]
        t = next((x for x in sl.get("transitions", []) if x["from"] == a and x["to"] == b), None)
        if not t:
            raise StageFail("PLAN-TRANSITION", f"no transition declared between {a} and {b} (use type cut, frames 0, for a plain cut)")
        d = t["frames"] / sl["fps"]
        if t["type"] != "cut" and t["frames"] and (d >= tl["shots"][i - 1]["dur"] or d >= tl["shots"][i]["dur"]):
            raise StageFail("PLAN-TRANSITION", f"{a}->{b}: {t['frames']} frames is not shorter than both shots")
    for t in sl.get("transitions", []):
        if t["from"] not in ids or t["to"] not in ids or ids.index(t["to"]) != ids.index(t["from"]) + 1:
            raise StageFail("PLAN-TRANSITION", f"transition {t['from']}->{t['to']} does not join two neighbouring shots")
    # videos and frame ranges
    for s, ts in zip(sl["shots"], tl["shots"]):
        v = shot_video(ep, s)
        ts["video"] = rel(v, ep.repo)
        ts["video_exists"] = v.is_file()
        if v.is_file():
            n = round(duration(v) * video_info(v)["fps"])
            if s["out_frame"] > n + 1:
                raise StageFail("PLAN-FRAMES", f"shot {s['id']}: out_frame {s['out_frame']} is past the render's {n} frames")
        else:
            warns.append(f"shot {s['id']}: render {ts['video']} does not exist yet (assemble will refuse)")
    # lines: audio and captions live on the EPISODE clock; a line may run across cuts (J-cut, L-cut).
    # `at_s` is seconds from the start of the shot that carries the line's start (negative = the sound starts
    # early, a J-cut). Which shot shows the speaker is declared per line (`visible_in`) for the visemes.
    placed, lines, shot_t = {}, [], {t["id"]: t for t in tl["shots"]}
    for s, ts in zip(sl["shots"], tl["shots"]):
        for pl in s.get("lines", []):
            if pl["line"] not in by_id:
                raise StageFail("PLAN-LINE-UNKNOWN", f"shot {s['id']} places line {pl['line']!r}, which is not in script.json")
            if pl["line"] in placed:
                raise StageFail("PLAN-LINE-DUP", f"line {pl['line']} is placed in two shots")
            placed[pl["line"]] = pl
            dur, src = line_duration(ep, by_id[pl["line"]], pl, mode)
            sv = spec_voice_entry(ep, s, pl["line"])   # voice first: the piece was timed from this very take
            at_s, off_src = pl.get("at_s"), "shotlist at_s"
            if sv is not None:
                spec_at = round(float(sv["start_s"]) - s["in_frame"] / sl["fps"], 3)
                if mode == "voice" and abs(float(sv.get("dur_s", 0)) - dur) > 0.02:
                    raise StageFail("PLAN-VOICE-OFFSET", f"line {pl['line']}: shot {s['id']}'s spec was timed on a {sv.get('dur_s')} s take, the take is {dur:.3f} s now: re-run `shot.py spec` for that piece (the voice changed)")
                if at_s is not None and abs(at_s - spec_at) > 0.05:
                    raise StageFail("PLAN-VOICE-OFFSET", f"line {pl['line']}: shotlist at_s {at_s} disagrees with the shot spec's voice_lines start ({spec_at} s from the shot's in_frame): drop at_s or fix the piece")
                at_s, off_src = spec_at, "shot spec voice_lines"
            if at_s is None:
                raise StageFail("PLAN-VOICE-OFFSET", f"line {pl['line']} in shot {s['id']} has no at_s and the shot spec has no voice_lines entry for it")
            start = round(ts["start"] + at_s, 3)
            end = round(start + dur, 3)
            if start < -1e-6 or end > tl["picture_s"] + 0.05:
                raise StageFail("PLAN-LINE-TIMELINE", f"line {pl['line']} ({src}) runs {start:.2f}-{end:.2f} s, outside the episode picture 0-{tl['picture_s']:.2f} s")
            spans = [t["id"] for t in tl["shots"] if t["start"] < end - 1e-6 and t["end"] > start + 1e-6]
            on_screen = pl.get("on_screen", True)
            vis = pl.get("visible_in", [])
            lip = []
            if on_screen:
                bad = [v for v in vis if v not in shot_t]
                if bad:
                    raise StageFail("PLAN-LIPSYNC", f"line {pl['line']}: visible_in names unknown shot(s) {', '.join(bad)}")
                for v in vis:
                    a0, a1 = max(start, shot_t[v]["start"]), min(end, shot_t[v]["end"])
                    if a1 - a0 > 1e-6:
                        lip.append({"shot": v, "start": round(a0, 3), "end": round(a1, 3)})
                if not lip:
                    why = "declares no visible_in shot" if not vis else f"visible_in {', '.join(vis)} does not overlap the line's {start:.2f}-{end:.2f} s"
                    raise StageFail("PLAN-LIPSYNC", f"line {pl['line']} is on screen but {why}: no shot carries the speaker's visemes (declare the shot, or on_screen false for a cutaway / off-screen voice)")
            lines.append({"id": pl["line"], "speaker": by_id[pl["line"]].get("speaker"), "text": by_id[pl["line"]].get("text", ""),
                          "start": start, "dur": dur, "end": end, "shot": s["id"], "spans_shots": spans, "on_screen": on_screen,
                          "lipsync": lip, "overlap_with": list(pl.get("overlap_with", [])), "timing_source": src, "offset_source": off_src})
    missing = [l["id"] for l in script["lines"] if l["id"] not in placed]
    if missing:
        raise StageFail("PLAN-LINE-SHOT", f"spoken line(s) with no shot: {', '.join(missing)}")
    empty = [l["id"] for l in script["lines"] if not (l.get("text") or "").strip() or not ar_letters(l["text"])]
    if empty:
        raise StageFail("PLAN-LINE-CAPTION", f"line(s) with no Arabic caption text: {', '.join(empty)}")
    lines.sort(key=lambda l: l["start"])
    for i, a in enumerate(lines):
        for b in lines[i + 1:]:
            if b["start"] >= a["end"] - 0.01:
                break
            declared = a["speaker"] != b["speaker"] and (b["id"] in a["overlap_with"] or a["id"] in b["overlap_with"])
            if not declared:
                raise StageFail("PLAN-LINE-OVERLAP", f"lines {a['id']} ({a['speaker']}) and {b['id']} ({b['speaker']}) overlap ({a['end']:.2f} > {b['start']:.2f} s); "
                                + ("one speaker cannot talk over themselves" if a["speaker"] == b["speaker"] else "declare overlap_with on one of them if the crosstalk is intended"))
    if not LEN_MIN <= tl["total_s"] <= LEN_MAX:
        raise StageFail("PLAN-LENGTH", f"planned length {tl['total_s']:.2f} s is outside {LEN_MIN:g}-{LEN_MAX:g} s")
    hook = sl.get("hook") or {}
    if not hook.get("event") or hook.get("at_s", 99) > HOOK_WINDOW:
        raise StageFail("PLAN-HOOK", f"shotlist.hook needs an event and at_s <= {HOOK_WINDOW:g} s (reels.md section 2)")
    if mode == "no-voice-yet":
        warns.append("NO VOICE YET: caption-only mode; line times are estimates (the takes do not exist)")
    plan = {"episode": ep.name, "series": ep.series, "fps": sl["fps"], "canvas": sl["canvas"], "voice_mode": mode,
            "picture_s": tl["picture_s"], "end_card_s": tl["end_card_s"], "total_s": tl["total_s"],
            "shots": tl["shots"], "lines": lines, "warnings": warns}
    write_json(ep.plan_p, plan)
    return {"total_s": plan["total_s"], "shots": len(plan["shots"]), "lines": len(lines), "voice_mode": mode, "warnings": warns}


# ------------------------------------------------------------------ loudness
def measure_loudness(path) -> dict:
    r = ff(["-i", path, "-vn", "-af", "ebur128=peak=true:framelog=quiet", "-f", "null", "-"], check=False)
    txt = r.stderr
    if r.returncode != 0 and "Summary" not in txt:
        raise StageFail("TOOL-ERROR", f"ebur128 failed: {txt[-300:]}")
    i = re.findall(r"\bI:\s+(-?[\d.]+|-inf)\s+LUFS", txt)
    p = re.findall(r"\bPeak:\s+(-?[\d.]+|-inf)\s+dBFS", txt)
    lra = re.findall(r"\bLRA:\s+(-?[\d.]+)\s+LU", txt)
    f = lambda v: -120.0 if v == "-inf" else float(v)
    return {"integrated_lufs": f(i[-1]) if i else None, "true_peak_dbtp": f(p[-1]) if p else None, "lra_lu": float(lra[-1]) if lra else None}


def loudnorm_pass1(path) -> dict:
    r = ff(["-i", path, "-af", f"loudnorm=I={LOUD_TARGET_I}:TP={LOUD_TP_TARGET}:LRA={LOUD_LRA}:print_format=json", "-f", "null", "-"])
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr, re.S)
    if not m:
        raise StageFail("TOOL-ERROR", "loudnorm printed no measurement")
    return json.loads(m.group(0))


# ------------------------------------------------------------------ stage: audio
def sfx_cues(ep: Ep, sl: dict, plan: dict, reg: dict) -> tuple[list, list]:
    """Explicit shotlist cues + cues read from each shot spec's emotion_track.sfx (at_s on the shot clock), filled from sfx_map."""
    cues, unfilled = [], []
    smap = sl.get("sfx_map", {})
    for s, ts in zip(sl["shots"], plan["shots"]):
        for c in s.get("sfx", []):
            cues.append({"t": round(ts["start"] + c["t"], 3), "file": c["file"], "licence_id": c["licence_id"], "gain_db": c.get("gain_db", SFX_GAIN_DB), "shot": s["id"], "source": "shotlist"})
        folder = Path(s["folder"])
        spec_p = (folder if folder.is_absolute() else ep.repo / folder) / "shot-spec.json"
        if not spec_p.is_file():
            continue
        spec = read_json(spec_p)
        for b in spec.get("beats", []):
            for c in (b.get("emotion_track") or {}).get("sfx", []):
                what, at = c.get("what", ""), float(c.get("at_s", 0))
                m = smap.get(what)
                if m:
                    cues.append({"t": round(ts["start"] + at, 3), "file": m["file"], "licence_id": m["licence_id"], "gain_db": m.get("gain_db", SFX_GAIN_DB),
                                 "shot": s["id"], "source": f"spec {b.get('id')} emotion_track.sfx: {what}"})
                else:
                    unfilled.append({"shot": s["id"], "beat": b.get("id"), "at_s": at, "what": what})
    return sorted(cues, key=lambda c: c["t"]), unfilled


def resolve_media(ep: Ep, f: str) -> Path:
    p = Path(f)
    return p if p.is_absolute() else ep.repo / p


def stage_audio(ep: Ep, silent=False) -> dict:
    plan = read_json(ep.plan_p)
    _, sl = load_inputs(ep)
    script = read_json(ep.script)
    mode = voice_mode(ep, script, silent)
    if mode != plan["voice_mode"]:
        raise StageFail("AUDIO-MODE", f"plan was made in {plan['voice_mode']} mode but audio is {mode}; run `plan` again")
    T, wd = plan["total_s"], ep.work / "audio"
    wd.mkdir(parents=True, exist_ok=True)
    reg = parse_licences(ep.licences)
    used, problems = [], []
    cues, unfilled = sfx_cues(ep, sl, plan, reg)
    music = sl.get("music")
    for role, items in (("sfx", [(c["file"], c["licence_id"]) for c in cues]), ("music", [(music["file"], music["licence_id"])] if music else [])):
        for f, lid in items:
            p = resolve_media(ep, f)
            pr = licence_problem(reg, lid, p) if p.is_file() else f"{role} file {f} does not exist"
            if pr:
                problems.append(pr)
            used.append({"role": role, "file": rel(p, ep.repo), "licence_id": lid})
    if problems:
        raise StageFail("AUDIO-LICENCE", "; ".join(sorted(set(problems))) + " (nothing unlicensed is mixed)")
    seen = set()
    used = [u for u in used if not (u["file"] in seen or seen.add(u["file"]))]
    info = {"episode": ep.name, "mode": mode, "total_s": T, "banner": "NO VOICE YET" if mode == "no-voice-yet" else "", "used_files": used,
            "sfx_cues": cues, "unfilled_sfx_cues": unfilled,
            "target": {"integrated_lufs": LOUD_TARGET_I, "tolerance_lu": LOUD_TOL, "true_peak_max_dbtp": LOUD_TP_MAX,
                       "source": "kb/guides/reels.md section 3 (measured delivered reels -14.1 LUFS; Instagram states none)"},
            "levels": {"voice_lufs": VOICE_LUFS, "bed_lufs": BED_LUFS, "sfx_default_gain_db": SFX_GAIN_DB, "ducking": f"sidechaincompress ratio {DUCK_BED['ratio']} (bed), {DUCK_SFX['ratio']} (sfx), attack {DUCK_BED['attack_ms']} ms, release {DUCK_BED['release_ms']} ms; house defaults, tune by ear"}}
    voice_bus = None
    vlines = [l for l in plan["lines"] if mode == "voice"]
    if vlines:
        args, fl = [], []
        for k, l in enumerate(vlines):
            args += ["-i", take_path(ep, l["id"])]
            fl.append(f"[{k}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={int(l['start'] * 1000)}|{int(l['start'] * 1000)}[v{k}]")
        mixin = "".join(f"[v{k}]" for k in range(len(vlines)))
        fl.append(f"{mixin}amix=inputs={len(vlines)}:normalize=0:duration=longest,apad=whole_dur={T},atrim=0:{T}[o]")
        voice_bus = wd / "voice_bus.wav"
        ff([*args, "-filter_complex", ";".join(fl), "-map", "[o]", "-ar", "48000", "-c:a", "pcm_f32le", voice_bus])
        vm = measure_loudness(voice_bus)
        info["voice_bus_measured_lufs"] = vm["integrated_lufs"]
        vgain = VOICE_LUFS - vm["integrated_lufs"] if vm["integrated_lufs"] and vm["integrated_lufs"] > -70 else 0.0
    else:
        vgain = 0.0
    if not voice_bus and not music and not cues:
        ff(["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", f"{T}", "-c:a", "pcm_s16le", ep.mix])
        info.update({"silent": True, "loudness": {"integrated_lufs": None, "true_peak_dbtp": None, "note": "no audio at all (no voice yet, no music, no cue): nothing to measure"}})
        write_json(ep.audio_p, info)
        return {"mode": mode, "silent": True}
    args, fl, labels, n = [], [], [], 0
    sc = bool(voice_bus)
    if voice_bus:
        args += ["-i", voice_bus]
        n += 1
        fl.append(f"[0:a]volume={vgain:.2f}dB,asplit={1 + (1 if music else 0) + (1 if cues else 0)}[vmain]" +
                  "".join(f"[sc{j}]" for j in range((1 if music else 0) + (1 if cues else 0))))
        labels.append("[vmain]")
    sci = 0
    if music:
        mp = resolve_media(ep, music["file"])
        mm = measure_loudness(mp)
        mg = BED_LUFS - mm["integrated_lufs"] + music.get("gain_db", 0.0) if mm["integrated_lufs"] and mm["integrated_lufs"] > -70 else music.get("gain_db", -20.0)
        info["music_measured_lufs"], info["music_gain_db"] = mm["integrated_lufs"], round(mg, 2)
        args += ["-stream_loop", "-1", "-i", mp]
        mi = n
        n += 1
        chain = f"[{mi}:a]atrim=0:{T},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo,volume={mg:.2f}dB,afade=t=in:st=0:d=0.5,afade=t=out:st={max(0, T - 1.5):.3f}:d=1.5"
        if sc:
            fl.append(chain + "[m0]")
            fl.append(f"[m0][sc{sci}]sidechaincompress=threshold={DUCK_BED['threshold']}:ratio={DUCK_BED['ratio']}:attack={DUCK_BED['attack_ms']}:release={DUCK_BED['release_ms']}[bed]")
            sci += 1
        else:
            fl.append(chain + "[bed]")
        labels.append("[bed]")
    if cues:
        sl_labels = []
        for k, c in enumerate(cues):
            args += ["-i", resolve_media(ep, c["file"])]
            ms = int(c["t"] * 1000)
            fl.append(f"[{n}:a]aresample=48000,aformat=channel_layouts=stereo,volume={c['gain_db']}dB,adelay={ms}|{ms}[x{k}]")
            sl_labels.append(f"[x{k}]")
            n += 1
        fl.append(f"{''.join(sl_labels)}amix=inputs={len(cues)}:normalize=0:duration=longest[sfxbus]")
        if sc:
            fl.append(f"[sfxbus][sc{sci}]sidechaincompress=threshold={DUCK_SFX['threshold']}:ratio={DUCK_SFX['ratio']}:attack={DUCK_SFX['attack_ms']}:release={DUCK_SFX['release_ms']}[sfxd]")
            labels.append("[sfxd]")
        else:
            labels.append("[sfxbus]")
    fl.append(f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0:duration=longest,apad=whole_dur={T},atrim=0:{T}[o]")
    premix = wd / "premix.wav"
    ff([*args, "-filter_complex", ";".join(fl), "-map", "[o]", "-ar", "48000", "-c:a", "pcm_f32le", premix])
    m = loudnorm_pass1(premix)
    ln = (f"loudnorm=I={LOUD_TARGET_I}:TP={LOUD_TP_TARGET}:LRA={LOUD_LRA}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
          f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true:print_format=summary")
    ff(["-i", premix, "-af", f"{ln},aresample=48000", "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", ep.mix])
    info["loudness"] = measure_loudness(ep.mix)
    info["loudnorm_pass1"] = {k: m[k] for k in ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")}
    write_json(ep.audio_p, info)
    return {"mode": mode, "integrated_lufs": info["loudness"]["integrated_lufs"], "true_peak_dbtp": info["loudness"]["true_peak_dbtp"], "sfx_cues": len(cues), "unfilled_sfx_cues": len(unfilled)}


# ------------------------------------------------------------------ colour helpers
def rel_lum(rgb) -> float:
    def ch(v):
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = rgb[:3]
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a, b) -> float:
    la, lb = rel_lum(a), rel_lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def box_contrast(rgb_img, box) -> float:
    """Contrast of the text in a box: background = the most common colour in the box, text = the pixel farthest from it in luminance."""
    import numpy as np
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    px = rgb_img[max(0, y0):y1, max(0, x0):x1].reshape(-1, 3)
    if len(px) == 0:
        return 0.0
    q = (px // 8).astype(np.int32)
    keys = q[:, 0] * 1024 + q[:, 1] * 32 + q[:, 2]
    vals, counts = np.unique(keys, return_counts=True)
    top = vals[counts.argmax()]
    bg = px[keys == top].mean(axis=0)
    lum = np.array([rel_lum(p) for p in px[:: max(1, len(px) // 4000)]])
    sub = px[:: max(1, len(px) // 4000)]
    fg = sub[np.abs(lum - rel_lum(bg)).argmax()]
    return contrast(fg, bg)


def safe_rect(canvas) -> tuple:
    W, H = canvas
    return (W * SAFE["side"], H * SAFE["top"], W * (1 - SAFE["side"]), H * (1 - SAFE["bottom"]))


def inside(box, rect, tol=1.0) -> bool:
    return box[0] >= rect[0] - tol and box[1] >= rect[1] - tol and box[2] <= rect[2] + tol and box[3] <= rect[3] + tol


# ------------------------------------------------------------------ chrome rendering (plates, end card)
def font_css(scale: float) -> str:
    css = []
    for fam, wt, f in (("thmanyahsans", 500, "Medium"), ("thmanyahsans", 700, "Bold"), ("thmanyahsans", 900, "Black"),
                       ("thmanyahserifdisplay", 700, "Bold"), ("thmanyahserifdisplay", 900, "Black")):
        p = FONTS / f"{fam}-{f}.woff2"
        css.append(f'@font-face{{font-family:"{fam}";src:url("{p.as_uri()}") format("woff2");font-weight:{wt}}}')
    return "".join(css)


def need_fonts():
    miss = [f for f in ("thmanyahsans-Bold.woff2", "thmanyahsans-Medium.woff2", "thmanyahserifdisplay-Black.woff2") if not (FONTS / f).is_file()]
    if miss:
        raise StageFail("CAP-FONT", f"Thmanyah font file(s) missing in assets/fonts/: {', '.join(miss)} (git-ignored; Cairo or any fallback is banned)")


def chrome_page(html: str, workdir: Path, W: int, H: int, fn):
    from playwright.sync_api import sync_playwright
    need_fonts()
    hp = workdir / "page.html"
    hp.parent.mkdir(parents=True, exist_ok=True)
    hp.write_text(html, encoding="utf-8")
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--enable-gpu-rasterization", "--ignore-gpu-blocklist", "--allow-file-access-from-files"])
        try:
            pg = b.new_page(viewport={"width": W, "height": H})
            pg.goto(hp.as_uri())
            specs = ("700 40px thmanyahsans", "500 40px thmanyahsans", "900 40px thmanyahserifdisplay")
            pg.evaluate("Promise.all(%s.map(s => document.fonts.load(s, 'هدى'))).then(() => 1)" % json.dumps(list(specs)))
            for spec in specs:
                if not pg.evaluate(f"document.fonts.check('{spec}')"):
                    raise StageFail("CAP-FONT", f"font {spec} did not load: refusing to render with a fallback face")
            return fn(pg)
        finally:
            b.close()


PLATE_FG, PLATE_BG = (255, 255, 255), (18, 16, 14)
PLATE_ALPHA = 0.88


def render_plates_chrome(items, outdir: Path, W: int, H: int) -> dict:
    s = W / 1080.0
    fs = round(52 * s, 2)
    body = "".join(f'<div class="p" id="p{k}" dir="rtl" lang="ar">{_esc(it["text"])}</div>' for k, it in enumerate(items))
    html = (f'<!doctype html><meta charset="utf-8"><style>{font_css(s)}'
            f'html,body{{margin:0;background:transparent}}.p{{display:block;box-sizing:border-box;width:fit-content;max-width:{920 * s:.1f}px;margin:{10 * s:.1f}px;'
            f'padding:{20 * s:.1f}px {38 * s:.1f}px;border-radius:{28 * s:.1f}px;background:rgba({PLATE_BG[0]},{PLATE_BG[1]},{PLATE_BG[2]},{PLATE_ALPHA});'
            f'color:rgb({PLATE_FG[0]},{PLATE_FG[1]},{PLATE_FG[2]});font-family:"thmanyahsans";font-weight:700;font-size:{fs}px;line-height:1.6;text-align:center;unicode-bidi:plaintext}}'
            f'</style>{body}')
    res = {}

    def go(pg):
        for k, it in enumerate(items):
            el = pg.locator(f"#p{k}")
            out = outdir / f"{it['id']}.png"
            el.screenshot(path=str(out), omit_background=True)
            bb = el.bounding_box()
            res[it["id"]] = {"w": round(bb["width"]), "h": round(bb["height"]), "path": out}
        return res
    chrome_page(html, outdir, W, H, go)
    for r in res.values():
        r["font_px"] = round(fs / s) if s else fs
    return res


def render_plates_stub(items, outdir: Path, W: int, H: int) -> dict:
    """TEST ONLY: draws a plate rectangle and a white bar as 'text' with Pillow. The gate refuses it unless NJ_COMPOSE_ALLOW_STUB=1."""
    from PIL import Image, ImageDraw
    res, s = {}, W / 1080.0
    for it in items:
        w, h = int(min(900 * s, max(120 * s, ar_letters(it["text"]) * 24 * s))), int(110 * s)
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle([0, 0, w - 1, h - 1], radius=int(20 * s), fill=PLATE_BG + (int(255 * PLATE_ALPHA),))
        d.rectangle([w * 0.15, h * 0.35, w * 0.85, h * 0.65], fill=PLATE_FG + (255,))
        out = outdir / f"{it['id']}.png"
        im.save(out)
        res[it["id"]] = {"w": w, "h": h, "path": out, "font_px": 52}
    return res


def _esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def engine() -> str:
    return "stub" if os.environ.get("NJ_COMPOSE_STUB_PLATES") == "1" else "chrome"


# ------------------------------------------------------------------ stage: captions
def viseme_span(ep: Ep, lid: str):
    p = ep.voice_dir / "visemes" / f"{lid}.json"
    if not p.is_file():
        return None
    k = read_json(p).get("keys", [])
    live = [x["t"] for x in k if x["id"] != "V0"]
    return (min(live), max(x["t"] for x in k)) if live else None


def stage_captions(ep: Ep) -> dict:
    plan = read_json(ep.plan_p)
    W, H = plan["canvas"]
    out = ep.work / "captions"
    out.mkdir(parents=True, exist_ok=True)
    items = [{"id": l["id"], "text": display_text(l["text"])} for l in plan["lines"]]  # display copy: no tashkeel (tts_text is voice.py's)
    eng = engine()
    res = (render_plates_stub if eng == "stub" else render_plates_chrome)(items, out, W, H)
    rect = safe_rect((W, H))
    bottom = rect[3] - 0.04 * H          # plate bottom edge, inside the lower safe edge
    caps, lines = [], plan["lines"]
    for k, l in enumerate(lines):
        r = res[l["id"]]
        span = viseme_span(ep, l["id"]) if plan["voice_mode"] == "voice" else None
        a = l["start"] + (span[0] if span else 0.0)
        b = l["start"] + (span[1] if span else l["dur"])
        nxt = lines[k + 1]["start"] if k + 1 < len(lines) else plan["picture_s"]
        b = min(b, nxt - CAP_GAP, plan["picture_s"])
        w, h = r["w"], r["h"]
        x, y = round((W - w) / 2), round(bottom - h)
        caps.append({"line": l["id"], "png": rel(r["path"], ep.repo), "start": round(a, 3), "end": round(b, 3), "x": x, "y": y, "w": w, "h": h,
                     "box": [x, y, x + w, y + h], "font": "thmanyahsans 700", "font_px_1080": r["font_px"], "rtl": True,
                     "plate_rgba": [*PLATE_BG, PLATE_ALPHA], "text_rgb": list(PLATE_FG),
                     "timing": "viseme track" if span else l["timing_source"], "text": display_text(l["text"]),
                     "spans_shots": l.get("spans_shots", [l["shot"]]), "cut_behaviour": "one overlay on the episode clock: stays put across cuts, no re-entry or animation at a cut"})
    bad = [c["line"] for c in caps if c["end"] - c["start"] < 0.3]
    if bad:
        raise StageFail("CAP-TIMING", f"caption(s) shorter than 0.3 s: {', '.join(bad)}")
    write_json(ep.caps_p, {"episode": ep.name, "engine": eng, "canvas": [W, H], "safe_rect": [round(v) for v in rect],
                           "safe_source": "kb/guides/reels.md section 1 (top 14 %, bottom 35 %: third-party, unverified, Q-05)", "captions": caps})
    return {"captions": len(caps), "engine": eng}


# ------------------------------------------------------------------ stage: assemble
def stage_assemble(ep: Ep) -> dict:
    plan = read_json(ep.plan_p)
    _, sl = load_inputs(ep)
    caps = read_json(ep.caps_p)["captions"]
    W, H = plan["canvas"]
    fps = plan["fps"]
    miss = [s["id"] for s in plan["shots"] if not Path(ep.repo / s["video"]).is_file()]
    if miss:
        raise StageFail("ASM-SHOT-VIDEO", f"no render for shot(s): {', '.join(miss)} (record them with tools/shot.py first)")
    if not ep.mix.is_file():
        raise StageFail("ASM-AUDIO", "audio/mix.wav missing: run `audio` first")
    args, fl = [], []
    for k, s in enumerate(plan["shots"]):
        args += [*hw_in(), "-i", ep.repo / s["video"]]
        fl.append(f"[{k}:v]trim=start_frame={s['in']}:end_frame={s['out']},setpts=PTS-STARTPTS,fps={fps},scale={W}:{H}:flags=bicubic,setsar=1,format=yuv420p[s{k}]")
    acc, length = "s0", plan["shots"][0]["dur"]
    for k in range(1, len(plan["shots"])):
        t, d = plan["shots"][k]["trans_in"], plan["shots"][k]["trans_in"]["dur"]
        nxt = f"j{k}"
        if t["type"] == "cut" or d == 0:
            fl.append(f"[{acc}][s{k}]concat=n=2:v=1:a=0[{nxt}]")
            length += plan["shots"][k]["dur"]
        else:
            fl.append(f"[{acc}][s{k}]xfade=transition={t['type']}:duration={d:.6f}:offset={length - d:.6f}[{nxt}]")
            length += plan["shots"][k]["dur"] - d
        acc = nxt
    n = len(plan["shots"])
    for k, c in enumerate(caps):
        args += ["-i", ep.repo / c["png"]]
        nxt = f"c{k}"
        fl.append(f"[{acc}][{n + k}:v]overlay=x={c['x']}:y={c['y']}:enable='between(t,{c['start']},{c['end']})':format=auto[{nxt}]")
        acc = nxt
    ai = n + len(caps)
    args += ["-i", ep.mix]
    fl.append(f"[{acc}]format=yuv420p[vout]")
    T = plan["picture_s"]
    ff([*args, "-filter_complex", ";".join(fl), "-map", "[vout]", "-map", f"{ai}:a", "-t", f"{T:.6f}", "-r", str(fps), *venc_args(),
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", ep.assembled])
    return {"duration_s": round(duration(ep.assembled), 3), "encoder": "h264_nvenc" if nvenc_wanted() else "libx264 (NJ_COMPOSE_CPU)", "shots": n, "captions": len(caps)}


# ------------------------------------------------------------------ stage: end card
END_BG, END_INK, CARD_BG, CARD_INK = "#14120f", "#f1ebe2", "#f6f1e8", "#1e1a16"


SCRIM_RGBA = (20, 18, 15, 0.80)    # behind the question and the prompt when the backdrop is live footage; contrast is measured over WHITE footage, the worst case


def end_html(card: dict, W: int, H: int, live: bool = False) -> str:
    card = dict(card, choices=[dict(c, text_ar=display_text(c["text_ar"]), **({"badge": display_text(c["badge"])} if c.get("badge") else {})) for c in card["choices"]],
                question_ar=display_text(card.get("question_ar", "")), comment_prompt_ar=display_text(card["comment_prompt_ar"]))
    s = W / 1080.0
    r = safe_rect((W, H))
    ch = "".join(f'<div class="c" data-box="c{k}" dir="rtl" lang="ar"><span class="b">{_esc(c.get("badge") or "أب"[k:k + 1])}</span><span class="t">{_esc(c["text_ar"])}</span></div>'
                 for k, c in enumerate(card["choices"]))
    q = f'<div class="q" data-box="q" dir="rtl" lang="ar">{_esc(card.get("question_ar", ""))}</div>' if card.get("question_ar") else ""
    return (f'<!doctype html><meta charset="utf-8"><style>{font_css(s)}'
            f'html,body{{margin:0;width:{W}px;height:{H}px;background:{"transparent" if live else END_BG}}}'
            f'.w{{position:absolute;left:{r[0]:.0f}px;top:{r[1] + 20 * s:.0f}px;width:{r[2] - r[0]:.0f}px;height:{r[3] - r[1] - 40 * s:.0f}px;display:flex;flex-direction:column;justify-content:center;gap:{34 * s:.0f}px'
            f'{(";box-sizing:border-box;padding:" + format(24 * s, ".0f") + "px;border-radius:" + format(40 * s, ".0f") + "px;background:rgba(%d,%d,%d,%s)" % SCRIM_RGBA) if live else ""}}}'
            f'.q{{font-family:"thmanyahserifdisplay";font-weight:900;font-size:{66 * s:.0f}px;line-height:1.5;color:{END_INK};text-align:center;padding:0 {10 * s:.0f}px}}'
            f'.c{{display:flex;align-items:center;gap:{26 * s:.0f}px;padding:{26 * s:.0f}px {34 * s:.0f}px;border-radius:{34 * s:.0f}px;background:{CARD_BG};color:{CARD_INK};font-family:"thmanyahsans";font-weight:700;font-size:{54 * s:.0f}px;line-height:1.5}}'
            f'.b{{flex:0 0 auto;width:{92 * s:.0f}px;height:{92 * s:.0f}px;border-radius:50%;background:{CARD_INK};color:{CARD_BG};display:flex;align-items:center;justify-content:center;font-weight:900;font-size:{58 * s:.0f}px}}'
            f'.t{{flex:1 1 auto;text-align:right}}'
            f'.p{{font-family:"thmanyahsans";font-weight:700;font-size:{46 * s:.0f}px;line-height:1.6;color:{END_INK};text-align:center}}'
            f'</style><div class="w">{q}{ch}<div class="p" data-box="p" dir="rtl" lang="ar">{_esc(card["comment_prompt_ar"])}</div></div>')


def stage_end(ep: Ep) -> dict:
    plan = read_json(ep.plan_p)
    _, sl = load_inputs(ep)
    card = sl.get("end_card")
    if not card:
        raise StageFail("END-CARD", "shotlist has no end_card")
    if not ep.assembled.is_file():
        raise StageFail("END-ASSEMBLED", "assembled.mp4 missing: run `assemble` first")
    backdrop = card.get("backdrop", "live-loop")   # the choice card sits over the last piece's live frames (the outline wants it over the office), not a flat card
    if backdrop not in ("live-loop", "live-hold", "static"):
        raise StageFail("END-CARD", f"end_card.backdrop {backdrop!r} must be live-loop, live-hold or static")
    live = backdrop != "static"
    W, H = plan["canvas"]
    wd = ep.work / "end"
    wd.mkdir(parents=True, exist_ok=True)
    target = ep.overlay if live else ep.card
    if engine() == "stub":
        from PIL import Image, ImageDraw
        im = Image.new("RGBA" if live else "RGB", (W, H), (0, 0, 0, 0) if live else (20, 18, 15))
        d = ImageDraw.Draw(im)
        r = safe_rect((W, H))
        boxes, y = {}, r[1] + 0.08 * H
        for k, key in enumerate(["q", "c0", "c1", "p"]):
            b = [r[0] + 0.05 * W, y, r[2] - 0.05 * W, y + 0.09 * H]
            d.rectangle(b, fill=(246, 241, 232) + ((255,) if live else ()))
            d.rectangle([b[0] + 0.05 * (b[2] - b[0]), b[1] + 0.25 * (b[3] - b[1]), b[2] - 0.05 * (b[2] - b[0]), b[3] - 0.25 * (b[3] - b[1])], fill=(30, 26, 22) + ((255,) if live else ()))
            boxes[key] = {"box": b, "font_px": 54}
            y += 0.11 * H
        im.save(target)
    else:
        def go(pg):
            pg.screenshot(path=str(target), omit_background=live)
            return {el.get_attribute("data-box"): {"box": [(bb := el.bounding_box())["x"], bb["y"], bb["x"] + bb["width"], bb["y"] + bb["height"]],
                    "font_px": round(float(pg.evaluate("e=>parseFloat(getComputedStyle(e).fontSize)", el.element_handle())) / (W / 1080.0))}
                    for el in pg.locator("[data-box]").all()}
        boxes = chrome_page(end_html(card, W, H, live), wd, W, H, go)
    if live:   # card.png = the overlay flattened over WHITE footage: the gate measures contrast on the worst case, whatever the last piece shows
        from PIL import Image
        ov = Image.open(ep.overlay).convert("RGBA")
        flat = Image.new("RGBA", ov.size, (255, 255, 255, 255)); flat.alpha_composite(ov); flat.convert("RGB").save(ep.card)
    D = float(card["duration_s"])
    t0 = plan["picture_s"]
    cv = wd / "card.mp4"
    fps = plan["fps"]
    if not live:
        ff(["-loop", "1", "-framerate", str(fps), "-i", ep.card, "-ss", f"{t0:.6f}", "-t", f"{D:.6f}", "-i", ep.mix,
            "-vf", "format=yuv420p", "-t", f"{D:.6f}", "-r", str(fps), *venc_args(), "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest", cv])
    else:
        loop_s = min(float(card.get("loop_s", 1.5)), duration(ep.assembled))
        nf = max(2, round(loop_s * fps))
        if backdrop == "live-loop":   # the last loop_s seconds of the last piece, forward then back, over and over: the picture never freezes and never jumps
            bg = (f"[0:v]fps={fps},trim=end_frame={nf},setpts=PTS-STARTPTS,split[a][b];[b]reverse[r];[a][r]concat=n=2:v=1:a=0,"
                  f"loop=loop=-1:size={2 * nf},setpts=N/({fps}*TB),trim=duration={D:.6f}[bg]")
        else:                         # live-hold: the last frame held
            bg = f"[0:v]fps={fps},trim=end_frame=2,setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop={round(D * fps)},trim=duration={D:.6f}[bg]"
        ff([*hw_in(), "-sseof", f"-{loop_s + 0.05:.3f}", "-i", ep.assembled, "-loop", "1", "-framerate", str(fps), "-i", ep.overlay, "-ss", f"{t0:.6f}", "-t", f"{D:.6f}", "-i", ep.mix,
            "-filter_complex", f"{bg};[bg]scale={W}:{H}:flags=bicubic,setsar=1[bs];[bs][1:v]overlay=format=auto,format=yuv420p[v]", "-map", "[v]", "-map", "2:a",
            "-t", f"{D:.6f}", "-r", str(fps), *venc_args(), "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest", cv])
    lst = wd / "concat.txt"
    lst.write_text(f"file '{ep.assembled.as_posix()}'\nfile '{cv.as_posix()}'\n", encoding="utf-8")
    ff(["-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", "-movflags", "+faststart", ep.episode])
    write_json(ep.end_p, {"episode": ep.name, "engine": engine(), "canvas": [W, H], "duration_s": D, "starts_at_s": t0, "boxes": boxes,
                          "choices": [dict(c, text_ar=display_text(c["text_ar"])) for c in card["choices"]], "question_ar": display_text(card.get("question_ar", "")),
                          "comment_prompt_ar": display_text(card["comment_prompt_ar"]),
                          "colours": {"bg": END_BG, "ink": END_INK, "card": CARD_BG, "card_ink": CARD_INK}, "card": rel(ep.card, ep.repo),
                          "backdrop": backdrop, "loop_s": (loop_s if live else None), "overlay": (rel(ep.overlay, ep.repo) if live else None), "scrim_rgba": (list(SCRIM_RGBA) if live else None)})
    return {"episode_s": round(duration(ep.episode), 3), "end_card_s": D}


# ------------------------------------------------------------------ gate
def rgb_png(path):
    import numpy as np
    from PIL import Image
    return np.asarray(Image.open(path).convert("RGB"))


def plate_png_contrast(path) -> float:
    """Plate over WHITE (worst case for a dark translucent plate): text px alpha 255, plate px alpha < 255."""
    import numpy as np
    from PIL import Image
    a = np.asarray(Image.open(path).convert("RGBA")).astype(float)
    al = a[..., 3:4] / 255.0
    comp = (a[..., :3] * al + 255.0 * (1 - al)).astype("uint8")
    h, w = comp.shape[:2]
    return box_contrast(comp, [0, 0, w, h])


def first_shot_motion(ep: Ep, plan: dict) -> dict:
    import numpy as np
    s = plan["shots"][0]
    fps = plan["fps"]
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-threads", "2", "-ss", f"{s['in'] / fps:.4f}", "-t", f"{HOOK_WINDOW}", *hw_in(),
                        "-i", str(ep.repo / s["video"]), "-vf", "scale=135:240,fps=12,format=gray", "-f", "rawvideo", "-"],
                       capture_output=True, env=ENV)
    fr = np.frombuffer(r.stdout, dtype=np.uint8)
    n = len(fr) // (135 * 240)
    if n < 3:
        return {"steps": 0, "moving_share": 0.0}
    fr = fr[: n * 135 * 240].reshape(n, 240, 135).astype(np.int16)
    moving = 0
    for i in range(1, n):
        d = np.abs(fr[i] - fr[i - 1])[: 240 // 8 * 8, : 135 // 8 * 8]
        blocks = d.reshape(240 // 8, 8, 135 // 8, 8).mean(axis=(1, 3))
        moving += (blocks > 3.0).mean() >= 0.05
    return {"steps": n - 1, "moving_share": round(moving / (n - 1), 3)}


def check_result(cid, status, detail):
    return {"id": cid, "status": status, "detail": detail}


def stage_gate(ep: Ep, skip_render_gate=False) -> dict:
    needed = [(ep.plan_p, "plan"), (ep.audio_p, "audio"), (ep.caps_p, "captions"), (ep.episode, "end"), (ep.end_p, "end")]
    for p, st in needed:
        if not p.is_file():
            raise StageFail("GATE-INPUT", f"{rel(p, ep.repo)} missing: run `{st}` first")
    plan, audio, caps, end = read_json(ep.plan_p), read_json(ep.audio_p), read_json(ep.caps_p), read_json(ep.end_p)
    _, sl = load_inputs(ep)
    W, H = plan["canvas"]
    rect = safe_rect((W, H))
    R = []
    fmt = qc.format_of(sl)   # "premium" (default) or "calm" (shotlist `profile`): calm swaps the length, hook-motion and render gates (gate-spec.md section H)
    calm = fmt == "calm"
    # EP-LENGTH
    d = duration(ep.episode)
    if calm:
        R.append(check_result("EP-LENGTH", "pass" if d >= CALM_LEN_MIN else "fail", f"{d:.2f} s (calm format: the story sets the length, floor {CALM_LEN_MIN:g} s)"))
    else:
        R.append(check_result("EP-LENGTH", "pass" if LEN_MIN <= d <= LEN_MAX else "fail", f"{d:.2f} s, need {LEN_MIN:g}-{LEN_MAX:g} s"))
    # EP-HOOK
    hook, mo = sl.get("hook") or {}, first_shot_motion(ep, plan)
    ok_event = bool(hook.get("event")) and hook.get("at_s", 99) <= HOOK_WINDOW
    ok_motion = calm or mo["moving_share"] >= 0.6
    R.append(check_result("EP-HOOK", "pass" if ok_event and ok_motion else "fail",
                          f"story event {hook.get('event')!r} at {hook.get('at_s')} s (limit {HOOK_WINDOW:g}); first-shot motion: {mo['moving_share']:.2f} of {mo['steps']} steps move >=5% of blocks "
                          + ("(calm format: the hook is the recap card, no motion floor)" if calm else "(need >= 0.60, house default from gate-spec low_motion)")))
    # EP-CAPTIONS
    probs, c_by = [], {c["line"]: c for c in caps["captions"]}
    if caps.get("engine") == "stub" and os.environ.get("NJ_COMPOSE_ALLOW_STUB") != "1":
        probs.append("plates were drawn by the test stub, not Chrome with Thmanyah")
    for l in plan["lines"]:
        c = c_by.get(l["id"])
        if not c:
            probs.append(f"line {l['id']} has no caption")
            continue
        if not (ep.repo / c["png"]).is_file():
            probs.append(f"{l['id']}: plate file missing")
            continue
        cr = plate_png_contrast(ep.repo / c["png"])
        if cr < CONTRAST_MIN:
            probs.append(f"{l['id']}: contrast {cr:.2f} < {CONTRAST_MIN}")
        if c["font_px_1080"] < CAP_FONT_MIN:
            probs.append(f"{l['id']}: font {c['font_px_1080']} px < {CAP_FONT_MIN}")
        if not c.get("rtl") or "thmanyah" not in c["font"]:
            probs.append(f"{l['id']}: not RTL Thmanyah")
        if c["end"] - c["start"] < (CALM_PLATE_MIN_S if calm else 0.3) or c["end"] > d or c["start"] < 0:
            probs.append(f"{l['id']}: bad window {c['start']}-{c['end']}")
    cs = sorted(caps["captions"], key=lambda c: c["start"])
    for a, b in zip(cs, cs[1:]):
        if b["start"] < a["end"]:
            probs.append(f"captions {a['line']} and {b['line']} overlap in time")
    R.append(check_result("EP-CAPTIONS", "fail" if probs else "pass", "; ".join(probs[:6]) or f"{len(cs)} of {len(plan['lines'])} lines captioned, contrast >= {CONTRAST_MIN}, font >= {CAP_FONT_MIN} px, RTL Thmanyah, no overlap"))
    # CAP-NO-TASHKEEL: every visible text (caption plates, end card) is free of diacritics and tatweel
    tk = [f"caption {c['line']}" for c in caps["captions"] if has_tashkeel(c.get("text"))]
    tk += [f"end card {k}" for k, v in (("question", end.get("question_ar")), ("comment prompt", end.get("comment_prompt_ar"))) if has_tashkeel(v)]
    tk += [f"end card choice {c.get('id')}" for c in end.get("choices", []) if has_tashkeel(c.get("text_ar"))]
    R.append(check_result("CAP-NO-TASHKEEL", "fail" if tk else "pass", ("tashkeel or tatweel in visible text: " + "; ".join(tk[:6])) if tk else "no diacritics or tatweel in captions or the end card"))
    # EP-SAFEZONE
    sp = [f"caption {c['line']} box {[round(v) for v in c['box']]} leaves the safe area {[round(v) for v in rect]}" for c in cs if not inside(c["box"], rect)]
    sp += [f"end card '{k}' box leaves the safe area" for k, v in end["boxes"].items() if not inside(v["box"], rect)]
    nf = 0
    for s, ts in zip(sl["shots"], plan["shots"]):
        for f in s.get("faces", []):
            nf += 1
            if not inside(f["box"], rect):
                sp.append(f"face in shot {s['id']} {f['box']} is inside a Reels UI zone")
    status = "fail" if sp else ("warn" if nf == 0 else "pass")
    R.append(check_result("EP-SAFEZONE", status, "; ".join(sp[:6]) or (f"{len(cs)} plates, {len(end['boxes'])} end-card boxes, {nf} declared face boxes inside {[round(v) for v in rect]}" if nf else
                          "text inside the safe area; NO face boxes declared in the shotlist (faces are not checked); zones unverified (Q-05)")))
    # EP-LOUDNESS
    ld = measure_loudness(ep.episode) if has_audio(ep.episode) else {"integrated_lufs": None}
    if audio.get("silent"):
        R.append(check_result("EP-LOUDNESS", "warn", "silent episode (no voice yet, no music, no cue): nothing to measure"))
    else:
        i, tp = ld["integrated_lufs"], ld["true_peak_dbtp"]
        okl = i is not None and abs(i - LOUD_TARGET_I) <= LOUD_TOL and tp is not None and tp <= LOUD_TP_MAX
        R.append(check_result("EP-LOUDNESS", "pass" if okl else "fail", f"{i} LUFS (target {LOUD_TARGET_I:g} +-{LOUD_TOL:g}), true peak {tp} dBTP (max {LOUD_TP_MAX:g}), measured on episode.mp4 (AAC)"))
    # EP-CHOICE
    cp = []
    ch = end.get("choices", [])
    if len(ch) != 2:
        cp.append(f"{len(ch)} choices (need exactly 2)")
    for c in ch:
        if not ar_letters(c.get("text_ar", "")):
            cp.append(f"choice {c.get('id')} has no Arabic text")
    if not ar_letters(end.get("comment_prompt_ar", "")):
        cp.append("no Arabic comment prompt")
    if end["duration_s"] < 2.5:
        cp.append(f"end card shows {end['duration_s']} s (< 2.5 s: unreadable)")
    if not ep.card.is_file():
        cp.append("card.png missing")
    else:
        import numpy as np
        img = rgb_png(ep.card)
        for k, v in end["boxes"].items():
            if v.get("font_px", 99) < 44:
                cp.append(f"end card '{k}' font {v['font_px']} px < 44")
            if end.get("engine") != "stub" or os.environ.get("NJ_COMPOSE_ALLOW_STUB") != "1":
                cr = box_contrast(img, v["box"])
                if cr < CONTRAST_MIN:
                    cp.append(f"end card '{k}' contrast {cr:.2f} < {CONTRAST_MIN}")
        if end.get("engine") == "stub" and os.environ.get("NJ_COMPOSE_ALLOW_STUB") != "1":
            cp.append("end card drawn by the test stub")
        # the video's last frame must be the card
        def grab(sseof):
            r = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-threads", "2", "-sseof", sseof, "-i", str(ep.episode), "-frames:v", "1", "-vf", f"scale={W}:{H}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                               capture_output=True, env=ENV)
            return np.frombuffer(r.stdout[: W * H * 3], dtype=np.uint8).reshape(H, W, 3).astype(float) if len(r.stdout) >= W * H * 3 else None
        fr = grab("-0.4")
        live = end.get("backdrop", "static") != "static"
        if fr is None:
            cp.append("could not read the last frame")
        elif not live:
            diff = float(np.abs(fr - img.astype(float)).mean()) / 255.0
            if diff > 0.06:
                cp.append(f"the last frame of episode.mp4 is not the end card (mean diff {diff:.3f})")
        else:   # live footage behind the card: the opaque card pixels must match the overlay; with live-loop the footage must really move
            from PIL import Image
            ov = np.asarray(Image.open(ep.repo / end["overlay"]).convert("RGBA").resize((W, H)))
            solid = ov[..., 3] >= 250
            if not solid.any():
                cp.append("the live end card overlay has no opaque pixels")
            else:
                diff = float(np.abs(fr[solid] - ov[..., :3][solid].astype(float)).mean()) / 255.0
                if diff > 0.06:
                    cp.append(f"the last frame of episode.mp4 is not the end card over live footage (mean diff {diff:.3f} on the opaque card pixels)")
            if end.get("backdrop") == "live-loop":
                f1, f2 = grab(f"-{min(1.2, end['duration_s'] - 0.1):.2f}"), grab("-0.1")
                if f1 is not None and f2 is not None:
                    free = ov[..., 3] < 10
                    mv = float(np.abs(f1[free] - f2[free]).mean()) / 255.0 if free.any() else 0.0
                    if mv < 0.0008:
                        cp.append(f"the live end-card backdrop does not move (mean change {mv:.4f}): the last piece's tail is still, use live-hold or a piece that moves at its end")
    R.append(check_result("EP-CHOICE", "fail" if cp else "pass", "; ".join(cp[:6]) or f"2 Arabic choices + comment prompt, {end['duration_s']:g} s card, readable, last frame verified"))
    # EP-MUSIC-LICENCE
    reg, lp = parse_licences(ep.licences), []
    for u in audio.get("used_files", []):
        pr = licence_problem(reg, u["licence_id"], ep.repo / u["file"])
        if pr:
            lp.append(pr)
    credits = sorted({reg[u["licence_id"]]["credit"] for u in audio.get("used_files", []) if u["licence_id"] in reg and reg[u["licence_id"]]["licence"] in ("CC-BY", "CC-BY-SA")})
    n_used = len(audio.get("used_files", []))
    R.append(check_result("EP-MUSIC-LICENCE", "fail" if lp else ("pass" if n_used else "warn"),
                          "; ".join(lp) or (f"{n_used} file(s) all registered; credit lines to publish: {credits or 'none needed'}" if n_used else "no music or SFX file used (nothing to license)")))
    # EP-VOICE (information)
    R.append(check_result("EP-VOICE", "warn" if audio["mode"] == "no-voice-yet" else "pass",
                          "NO VOICE YET: caption-only proof; not a deliverable" if audio["mode"] == "no-voice-yet" else "voice takes placed; the owner listens"))
    # calm format: declared-data checks (captions, narrator cover, wrapper, subjects); an own-id result each so a failure names its check
    if calm:
        cf = qc.check_calm_declared(plan, caps, end, sl, d)
        for cid in ("CALM-CAPTION-STYLE", "CALM-VOICE-COVERAGE", "CALM-WRAPPER", "CALM-SUBJECTS"):
            mine = [x for x in cf if cid in x]
            R.append(check_result(cid, "fail" if mine else "pass", "; ".join(x.replace("FAIL ", "", 1) for x in mine[:3]) or f"{cid} ok"))
    # render gates on the assembled video
    if skip_render_gate:
        R.append(check_result("EP-RENDER-GATE", "skip", "skipped by --skip-render-gate: the report is NOT complete"))
    elif calm:
        gp = ep.work / "gate" / "render.json"
        gp.parent.mkdir(parents=True, exist_ok=True)
        r = run(["uv", "run", TOOLS / "quality_gate.py", "calm", ep.episode, "--json", gp], check=False, cwd=ep.repo)
        bad = [l.strip() for l in (r.stdout or "").splitlines() if l.strip().startswith("FAIL")]
        R.append(check_result("EP-RENDER-GATE", "pass" if r.returncode == 0 else "fail",
                              "tools/quality_gate.py calm PASS (pacing, holds, motion band, subjects, narrator audio)" if r.returncode == 0 else "; ".join(bad[:6]) or f"quality_gate exited {r.returncode}: {(r.stderr or '')[-200:]}"))
        lp_ = ep.work / "gate" / "look2d.json"
        r2 = run(["uv", "run", TOOLS / "quality_gate.py", "look2d", ep.episode, "--json", lp_], check=False, cwd=ep.repo)   # the art check still applies to the calm format
        bad2 = [l.strip() for l in (r2.stdout or "").splitlines() if l.strip().startswith("FAIL")]
        R.append(check_result("EP-LOOK2D", "pass" if r2.returncode == 0 else "fail",
                              "tools/quality_gate.py look2d PASS" if r2.returncode == 0 else "; ".join(bad2[:3]) or f"quality_gate look2d exited {r2.returncode}: {(r2.stderr or '')[-200:]}"))
    else:
        gp = ep.work / "gate" / "render.json"
        gp.parent.mkdir(parents=True, exist_ok=True)
        r = run(["uv", "run", TOOLS / "quality_gate.py", "render", ep.episode, "--json", gp], check=False, cwd=ep.repo)
        bad = [l.strip() for l in (r.stdout or "").splitlines() if l.strip().startswith("FAIL")]
        R.append(check_result("EP-RENDER-GATE", "pass" if r.returncode == 0 else "fail",
                              "tools/quality_gate.py render PASS" if r.returncode == 0 else "; ".join(bad[:6]) or f"quality_gate exited {r.returncode}: {(r.stderr or '')[-200:]}"))
    fails = [c for c in R if c["status"] == "fail"]
    rep = {"episode": ep.name, "format": fmt, "verdict": "FAIL" if fails else "PASS", "complete": not skip_render_gate, "voice_mode": audio["mode"], "checks": R}
    write_json(ep.gate_p, rep)
    for c in R:
        print(f"{c['status'].upper():5} [{c['id']}] {c['detail']}")
    print(rep["verdict"] + ("" if rep["complete"] else " (INCOMPLETE: render gate skipped)"))
    if fails:
        raise StageFail(fails[0]["id"], fails[0]["detail"] + (f" (+{len(fails) - 1} more, see gate/report.json)" if len(fails) > 1 else ""))
    return {"verdict": rep["verdict"], "warnings": [c["id"] for c in R if c["status"] == "warn"]}


# ------------------------------------------------------------------ preview tab
def stage_preview(ep: Ep, page: Path) -> dict:
    if not ep.gate_p.is_file() or not ep.episode.is_file():
        raise StageFail("PREV-INPUT", "gate/report.json or episode.mp4 missing: run `gate` first")
    rep, plan, audio = read_json(ep.gate_p), read_json(ep.plan_p), read_json(ep.audio_p)
    tab = f"ep-{ep.name.lower()}"
    label = ep.name
    txt = Path(page).read_text(encoding="utf-8")
    chips = "".join(f'<li class="chip">{ {"pass": "✅", "fail": "❌", "warn": "⚠️", "skip": "⏭️"}[c["status"]] } {c["id"]}</li>' for c in rep["checks"])
    vid = os.path.relpath(ep.episode, Path(page).resolve().parent).replace("\\", "/")
    banner = '<p class="sub"><b>🔇 NO VOICE YET</b>: captions, music and cuts are proven; the voices are not recorded. Not a deliverable.</p>' if audio["mode"] == "no-voice-yet" else ""
    ld = audio.get("loudness", {})
    block = (f'<!--EP_{ep.name.upper()}_BEGIN--><section class="panel" id="panel-{tab}" data-tab="{tab}" hidden>\n<main class="wrap">\n'
             f'<p class="hook">🎬 {label}: {plan["total_s"]:.0f} s Reel</p>\n'
             f'<p class="sub">{"✅ Every gate passed." if rep["verdict"] == "PASS" else "❌ A gate failed."} Look at the hook (first 2 s), the captions, the choice card.</p>\n{banner}\n'
             f'<div class="mix-grid"><figure class="mix-stage">\n<video src="{vid}" controls autoplay muted loop playsinline preload="auto" width="1080" height="1920" aria-label="Episode {label}"></video>\n'
             f'<figcaption>🎥 The assembled video the gates measured: <code>{rel(ep.episode, ep.repo)}</code> (NVENC).</figcaption></figure>\n'
             f'<div class="mix-side"><h3>🚦 Episode gate <small>tools/compose.py gate</small></h3><ul class="chips">{chips}</ul>\n'
             f'<p class="mix-note">🔊 Loudness: {ld.get("integrated_lufs")} LUFS, true peak {ld.get("true_peak_dbtp")} dBTP (target -14 LUFS).</p>\n'
             f'<p class="mix-note">📄 Files: <code>{rel(ep.work, ep.repo)}</code> plan.json, audio/, captions/, end/, gate/report.json.</p></div></div>\n</main>\n</section><!--EP_{ep.name.upper()}_END-->')
    pat = re.compile(rf"<!--EP_{ep.name.upper()}_BEGIN-->.*?<!--EP_{ep.name.upper()}_END-->", re.S)
    if pat.search(txt):
        txt = pat.sub(lambda m: block, txt)
    else:
        marker = "<script>\n/* One preview page per project."
        if marker not in txt:
            raise StageFail("PREV-PAGE", "page has no script marker to insert before")
        txt = txt.replace(marker, block + "\n" + marker, 1)
    entry = f'  {{id: "{tab}", emoji: "🎬", label: "{label}"}},\n'
    em = re.compile(rf'  \{{id: "{re.escape(tab)}"[^\n]*\n')
    if em.search(txt):
        txt = em.sub(lambda m: entry, txt, 1)
    else:
        i = txt.index("const TABS = [")
        j = txt.index("];", i)
        txt = txt[:j] + entry + txt[j:]
    tmp = Path(str(page) + ".tmp")
    tmp.write_text(txt, encoding="utf-8")
    os.replace(tmp, page)
    return {"tab": tab, "page": rel(page, ep.repo), "open": f"{rel(page, ep.repo)}#{tab}"}


# ------------------------------------------------------------------ init
SHOTLIST_TEMPLATE = {
    "format": "shotlist/1", "episode": "", "fps": 24, "canvas": [1080, 1920],
    "hook": {"event": "WRITE: the story event that happens in the first 2 s", "at_s": 1.0},
    "shots": [{"id": "s1", "folder": "work/shots/s1", "in_frame": 0, "out_frame": 240, "beat": "b1", "lines": [{"line": "l1", "at_s": 0.5}], "faces": []}],
    "transitions": [], "sfx_map": {}, "music": None,
    "end_card": {"duration_s": 3.0, "question_ar": "", "choices": [{"id": "A", "text_ar": ""}, {"id": "B", "text_ar": ""}], "comment_prompt_ar": ""}}


def cmd_init(arg: str, repo: Path = REPO) -> int:
    s, _, e = arg.replace("\\", "/").partition("/")
    d = repo / "bible" / "series" / (s if e else DEFAULT_SERIES) / "episodes" / (e or s)
    d.mkdir(parents=True, exist_ok=True)
    made = []
    if not (d / "shotlist.json").exists():
        t = dict(SHOTLIST_TEMPLATE, episode=d.name)
        t.pop("music")
        write_json(d / "shotlist.json", t)
        made.append("shotlist.json")
    if not (d / "outline.md").exists():
        (d / "outline.md").write_text(f"# {d.name} outline\n\n- Hook (0-2 s):\n- Beats:\n- Turn:\n- Ending and the two choices:\n", encoding="utf-8")
        made.append("outline.md")
    print(f"{rel(d, repo)}: wrote {', '.join(made) or 'nothing (already there)'}; script.json belongs to the Opus writer")
    return 0


# ------------------------------------------------------------------ engine wiring
def build_stages(ep: Ep, silent=False, skip_render_gate=False, page=None):
    r = ep.repo
    shot_videos = lambda: ([r / s["video"] for s in read_json(ep.plan_p)["shots"]] if ep.plan_p.is_file() else [])
    media = lambda: ([resolve_media(ep, u["file"]) for u in read_json(ep.audio_p).get("used_files", [])] if ep.audio_p.is_file() else [])

    def shot_inputs():
        out = []
        if ep.shotlist.is_file():
            try:
                sl = read_json(ep.shotlist)
                for s in sl.get("shots", []):
                    out += [shot_video(ep, s), (Path(s["folder"]) if Path(s["folder"]).is_absolute() else r / s["folder"]) / "shot-spec.json"]
            except Exception:
                pass
        return out
    voice = lambda: sorted(ep.voice_dir.rglob("*.json")) + sorted(ep.voice_dir.glob("*.trimmed.wav")) + sorted(ep.voice_dir.glob("L*.wav")) if ep.voice_dir.is_dir() else []
    st = lambda *a, **k: Stage(*a, **k)
    return [
        st("plan", lambda d: [ep.script, ep.shotlist, *shot_inputs(), *voice()], lambda d: [ep.plan_p], lambda d: stage_plan(ep, silent)),
        st("audio", lambda d: [ep.plan_p, ep.licences, *voice(), *media_from_shotlist(ep)], lambda d: [ep.mix, ep.audio_p], lambda d: stage_audio(ep, silent)),
        st("captions", lambda d: [ep.plan_p, *voice()], lambda d: [ep.caps_p], lambda d: stage_captions(ep)),
        st("assemble", lambda d: [ep.plan_p, ep.caps_p, ep.mix, *shot_videos(), *captions_pngs(ep)], lambda d: [ep.assembled], lambda d: stage_assemble(ep)),
        st("end", lambda d: [ep.shotlist, ep.assembled, ep.mix], lambda d: [ep.episode, ep.end_p, ep.card], lambda d: stage_end(ep)),
        st("gate", lambda d: [ep.episode, ep.end_p, ep.audio_p, ep.caps_p, ep.licences], lambda d: [ep.gate_p], lambda d: stage_gate(ep, skip_render_gate)),
    ]


def media_from_shotlist(ep: Ep):
    try:
        sl = read_json(ep.shotlist)
    except Exception:
        return []
    files = [m["file"] for m in sl.get("sfx_map", {}).values()] + [c["file"] for s in sl.get("shots", []) for c in s.get("sfx", [])]
    if sl.get("music"):
        files.append(sl["music"]["file"])
    return [resolve_media(ep, f) for f in files]


def captions_pngs(ep: Ep):
    return [ep.repo / c["png"] for c in read_json(ep.caps_p)["captions"]] if ep.caps_p.is_file() else []


def cmd_status(ep: Ep) -> int:
    stt = State(ep.work)
    for s in build_stages(ep):
        e = stt.get(s.name)
        if not e:
            print(f"{s.name:9} -")
            continue
        if e["status"] == "failed":
            print(f"{s.name:9} FAIL [{e.get('check')}] {e.get('message', '')[:140]}")
            continue
        try:
            fresh = hash_inputs(s.inputs(ep.work), ep.repo) == e.get("inputs")
        except Exception:
            fresh = False
        print(f"{s.name:9} ok ({'fresh' if fresh else 'stale: inputs changed'})  {json.dumps(e.get('info', {}), ensure_ascii=False)[:120]}")
    return 0


def main(argv=None, repo: Path = REPO) -> int:
    ap = argparse.ArgumentParser(prog="compose.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", choices=["init", "plan", "audio", "captions", "assemble", "end", "gate", "preview", "all", "status", "licence-add", "heal"])
    ap.add_argument("ep", nargs="?")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--silent", action="store_true", help="caption-only mode: ignore voice takes, flagged NO VOICE YET")
    ap.add_argument("--skip-render-gate", action="store_true")
    ap.add_argument("--page", default="previews/index.html")
    for f in ("id", "file", "kind", "licence", "source", "retrieved", "credit"):
        ap.add_argument(f"--{f}")
    a = ap.parse_args(argv)
    try:
        if a.stage == "licence-add":
            return cmd_licence_add(a, repo)
        if not a.ep:
            ap.error("an episode is required")
        if a.stage == "init":
            return cmd_init(a.ep, repo)
        ep = resolve_episode(a.ep, repo)
        if a.stage == "status":
            return cmd_status(ep)
        if a.stage == "preview":
            page = Path(a.page)
            page = page if page.is_absolute() else repo / page
            print(json.dumps(stage_preview(ep, page), ensure_ascii=False))
            return 0
        if a.stage == "heal":
            import heal
            res = heal.prepare(ep.work, "episode", repo)
            return 0 if res is None or res["ready_for_owner"] else 1
        stages = build_stages(ep, a.silent, a.skip_render_gate)
        names = [s.name for s in stages]
        todo = names if a.stage == "all" else [a.stage]
        for s in stages:
            if s.name in todo:
                print(f"[{s.name}] {run_stage(s, ep.work, repo, force=a.force)}")
        if a.stage == "all":
            import heal
            heal.prepare(ep.work, "episode", repo)   # optional stage: reports what is still needed, never changes the exit code
        return 0
    except StageFail as e:
        print(f"FAIL [{e.check}] {e.message}")
        return 1
    except (ImportError, FileNotFoundError, json.JSONDecodeError) as e:
        print(f"tool error: {e!r}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
