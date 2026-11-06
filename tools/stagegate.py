# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Safe stages for the daily pipeline (owner, 2026-10-25: "add safe fixing, measurement and testing stages between steps so we don't redo the work after finishing and find out bugs").

A stage of tools/daily.py is no longer "run, then trust". After every stage a VERIFY runs at once, and the next stage cannot start until it passed. This module holds the parts that
are not the runner: the hash fingerprints, the staleness rule (a fix at stage N reruns exactly the stages downstream whose inputs changed) and one verifier per stage.
pipelines/STAGE-GATES.md is the human document; tools/tests/test_stagegate.py tests every verifier and the invalidation logic.

  fingerprint(spec)        {label: sha256} of files, folders, lists of files and literals
  inputs_for / outputs_for (stage, ctx)   what a stage reads and what it writes, as a spec
  VERIFY[stage](ctx)       -> [finding]; a finding is {"id", "msg", "fix", "sev"}; sev "fail" stops the run, "warn" is written to the report only
  brief(stage, findings)   the fix brief STOPPED.md carries: the check id, what is wrong, who fixes it and what reruns afterwards

Nothing here calls a model, the network or a renderer. ffprobe is the only child process (shot and episode files). Every id is stable; none is ever loosened to pass.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

MAX_LINE_WORDS = 22           # a narrator line is at most 8 s read aloud (pipelines/DAILY.md); 22 words at the slowest planned rate of 2.5 words a second is 8.8 s
TAKE_S = (0.3, 14.0)          # a take outside this is a truncation or a runaway
TAKE_WPS = (0.5, 4.5)         # words a second: Chatterbox measured 1.4 to 1.8; the band catches a truncated or garbled take, it is not a taste limit
TAKE_PEAK = (0.02, 0.9995)    # not silent, not clipped
CAPTION_HASHTAGS = 3          # caption.txt: one line plus three hashtags (CLAUDE.md "Episodes after E01", writer prompt)
JOIN_S = 0.25                 # calm_compose.JOIN_S (asserted equal by the tests)
FPS = 24
GATE_REQUIRED = ("CALM-LENGTH", "CALM-NO-TASHKEEL", "CALM-LOUDNESS", "AUDIO-DIALOGUE-CLARITY", "AUDIO-MONO", "AUDIO-PEAK", "CALM-NO-SILENCE", "CALM-ONE-PLATE", "CAP-ARABIC-SHAPING",
                 "CAP-FULL-SENTENCE", "CAP-READ-TIME", "CAP-READING-SPEED", "CAP-FACE-CLEAR", "CAP-FOREIGN-GLOSS", "CALM-PLATE-SAFE", "CALM-HUD", "CALM-RECAP-FIRST", "CALM-INTRO",
                 "CALM-TWO-CHOICES", "CALM-VOICE-COVERAGE", "CALM-TRANSITION-SFX", "CALM-RENDER")   # a gate report that lacks one of these skipped it: that is a failure, never a pass

GATE_REQUIRED_V2 = ("NARRATOR-SHARE", "DIALOGUE-LINES", "EVENTS")      # format v2, E03 on: calm_compose.stage_gate records them


def F(cid: str, msg: str, fix: str = "", sev: str = "fail") -> dict:
    return {"id": cid, "msg": msg, "fix": fix, "sev": sev}


# ------------------------------------------------------------------ fingerprints
_CACHE: dict = {}


def sha_file(p) -> str:
    p = Path(p)
    try:
        stt = p.stat()
    except OSError:
        return "absent"
    key = (str(p), stt.st_size, stt.st_mtime_ns)
    if key not in _CACHE:
        h = hashlib.sha256()
        with open(p, "rb") as fh:
            for blk in iter(lambda: fh.read(1 << 20), b""):
                h.update(blk)
        _CACHE[key] = h.hexdigest()
    return _CACHE[key]


def tree_files(d) -> list[Path]:
    d = Path(d)
    skip = {"__pycache__", "node_modules", ".git"}
    return sorted(p for p in d.rglob("*") if p.is_file() and not (skip & set(p.relative_to(d).parts)))


def sha_tree(d) -> str:
    d = Path(d)
    h = hashlib.sha256()
    for p in tree_files(d):
        h.update(f"{p.relative_to(d).as_posix()}:{sha_file(p)}\n".encode())
    return h.hexdigest()


def fp_value(v) -> str:
    """A file -> its sha256; a folder -> the hash of its files; a list -> the hash of its members (name + hash); 'const:<text>' -> the hash of the text; a missing path -> 'absent'."""
    if isinstance(v, str) and v.startswith("const:"):
        return hashlib.sha256(v[6:].encode("utf-8")).hexdigest()
    if isinstance(v, (list, tuple)):
        h = hashlib.sha256()
        for m in sorted(v, key=lambda x: Path(x).name):
            h.update(f"{Path(m).name}:{fp_value(m)}\n".encode())
        return h.hexdigest()
    p = Path(v)
    if p.is_dir():
        return sha_tree(p)
    return sha_file(p)


def fingerprint(spec: dict) -> dict:
    return {k: fp_value(v) for k, v in spec.items()}


def changed(old: dict | None, new: dict) -> list[str]:
    old = old or {}
    return sorted(k for k in set(old) | set(new) if old.get(k) != new.get(k))


def code_files(*names: str) -> list[Path]:
    """Files or folders under tools/, flattened to files."""
    out: list[Path] = []
    for n in names:
        p = TOOLS / n
        out += tree_files(p) if p.is_dir() else [p]
    return out


# the tools a stage's result depends on: a change to one of them reruns that stage (a changed rig, caption or mix rule must not leave a stale result behind; E01C, 2026-10-25)
CODE = {
    "plan": ("calm_compose.py", "calm_intro.py", "calm_sfx.py", "gloss.py", "stagegate.py"),
    "animatic": ("calm_compose.py", "calm_intro.py", "calm_sfx.py", "calm_mix.py", "gloss.py", "cap_sentence.py", "cap_shaping.py", "cap_face.py", "audio_checks.py", "qg_checks.py", "animatic.py", "arabic_display.py"),
    "shots": ("render", "shotlib", "templates", "shot.py", "calm.py", "calm_cards.py", "calm_intro.py", "calm_kit.py"),
    "compose": ("calm_compose.py", "compose.py", "cap_sentence.py", "cap_shaping.py", "cap_face.py", "calm_mix.py", "calm_sfx.py", "calm_cards.py", "gloss.py", "arabic_display.py"),
    "gates": ("calm_compose.py", "qg_checks.py", "quality_gate.py", "audio_checks.py", "cap_sentence.py", "gloss.py"),
}


# ------------------------------------------------------------------ what a stage reads and writes
def _takes(ctx) -> list[Path]:
    d = ctx.root / "work" / "voice" / ctx.ep
    return sorted(d.glob("*.trimmed.wav")) if d.is_dir() else []


def _timeline(ctx) -> dict | None:
    p = ctx.work / "timeline.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _shot_videos(ctx) -> list[Path]:
    tl = _timeline(ctx)
    out = []
    for it in (tl or {}).get("items", []):
        out.append(ctx.root / it["video"])
        for c in (it.get("split") or {}).get("top", []):
            out.append(ctx.root / "work" / "shots" / f"{ctx.ep}-{c['shot']}" / "out" / f"{ctx.ep}-{c['shot']}.mp4")
    return out


def _glossary(ctx) -> list[Path]:
    return sorted(ctx.root.glob("bible/series/*/glossary.json"))


def inputs_for(name: str, ctx) -> dict | None:
    ed, w = ctx.ep_dir, ctx.work
    code = lambda k: code_files(*CODE[k])
    import daily
    brief = ctx.root / "work" / "episodes" / (daily.prev_ep(ctx.ep) or "none") / "next-brief.md"
    capheal = ctx.root / "work" / "daily" / ctx.ep / "cap-heal.json"
    ch = {"cap-heal.json": capheal} if capheal.is_file() else {}       # R-506: the plates the caption heal cut in two; listed only once it exists, so a finished episode is not made stale by a new key
    spec = {
        "script": {"brief": brief},      # the writer's inputs; the files themselves are its OUTPUTS, and a rerun keeps existing files (only --force script rewrites them)
        "voice": {"script.json": ed / "script.json"},
        "plan": {"calm-plan.json": ed / "calm-plan.json", "script.json": ed / "script.json", "takes": _takes(ctx), "glossary": _glossary(ctx),
                 "read-heal.json": ctx.root / "work" / "daily" / ctx.ep / "read-heal.json", "code": code("plan")},      # R-503: the animatic's measured reading shortfalls, fed back by tools/read_heal.py
        "animatic": {"timeline.json": w / "timeline.json", "calm-plan.json": ed / "calm-plan.json", "script.json": ed / "script.json", "takes": _takes(ctx), "glossary": _glossary(ctx),
                     **ch, "code": code("animatic")},
        "shots": {"timeline.json": w / "timeline.json", "calm-plan.json": ed / "calm-plan.json", "visemes": ctx.root / "work" / "voice" / ctx.ep / "visemes", "code": code("shots")},
        "compose": {"timeline.json": w / "timeline.json", "calm-plan.json": ed / "calm-plan.json", "script.json": ed / "script.json", "takes": _takes(ctx), "shot-videos": _shot_videos(ctx),
                    "glossary": _glossary(ctx), **ch, "code": code("compose")},
        "gates": {"episode.mp4": w / "episode.mp4", "timeline.json": w / "timeline.json", "captions.json": w / "captions.json", "mix.wav": w / "mix.wav", "calm-plan.json": ed / "calm-plan.json",
                  "script.json": ed / "script.json", "code": code("gates")},
        "critic": {"episode.mp4": w / "episode.mp4", "gate-report": w / "gate" / "report.json", "script.json": ed / "script.json", "calm-plan.json": ed / "calm-plan.json",
                   "questions": "const:" + " | ".join(daily.CRITIC_QUESTIONS)},
    }
    return spec.get(name)


def outputs_for(name: str, ctx) -> dict | None:
    ed, w = ctx.ep_dir, ctx.work
    spec = {
        "script": {"script.json": ed / "script.json", "calm-plan.json": ed / "calm-plan.json", "caption.txt": ed / "caption.txt"},
        "voice": {"takes": _takes(ctx), "take-sources": ctx.root / "work" / "voice" / ctx.ep / "take-sources.json"},
        "plan": {"timeline.json": w / "timeline.json"},
        "animatic": {"report.json": w / "animatic" / "report.json", "mix.wav": w / "mix.wav", "sfx.json": w / "sfx.json"},
        "shots": {"videos": _shot_videos(ctx)},
        "compose": {"episode.mp4": w / "episode.mp4", "captions.json": w / "captions.json", "hud.json": w / "hud.json", "mix.wav": w / "mix.wav"},
        "gates": {"report.json": w / "gate" / "report.json"},
        "critic": {"critic.json": w / "heal" / "critic.json"},
    }
    return spec.get(name)


def output_paths(name: str, ctx) -> list[Path]:
    """The files that must exist and be non-empty after a stage."""
    o = outputs_for(name, ctx) or {}
    out: list[Path] = []
    for v in o.values():
        out += list(v) if isinstance(v, (list, tuple)) else [Path(v)]
    return [p for p in out if p.name != "take-sources.json"]


# ------------------------------------------------------------------ small readers
def jload(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def wav_info(p) -> tuple[float, float, int]:
    """(seconds, peak 0..1, rate) of a take; float and 16-bit wav through voice.read_float."""
    import voice
    x, rate = voice.read_float(p)
    return len(x) / rate, (max(abs(v) for v in x) if x else 0.0), rate


def ffprobe_json(p) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate,duration:format=duration", "-of", "json", str(p)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        return json.loads(r.stdout or "{}")
    except ValueError:
        return {}


def _fps(s: str) -> float:
    try:
        a, b = str(s).split("/")
        return float(a) / float(b)
    except (ValueError, ZeroDivisionError):
        return 0.0


def plan_line_ids(plan: dict) -> set[str]:
    ids = {s["line"] for s in plan.get("scenes", []) if s.get("line")}
    ids |= {i["line"] for i in plan.get("intros", []) or [] if i.get("line")}
    ch = plan.get("choice") or {}
    if ch.get("line"):
        ids.add(ch["line"])
    ids |= set((ch.get("lines") or {}).values())
    if (plan.get("written") or {}).get("line"):
        ids.add(plan["written"]["line"])
    if (plan.get("hook") or {}).get("line"):      # the spoken recap (calm_compose.stage_plan reads plan["hook"]["line"]) is a use: E02 and E03 H01 were reported as orphans
        ids.add(plan["hook"]["line"])
    return ids


AR_LETTER = re.compile("[ء-غف-ي]")


# ------------------------------------------------------------------ the verifiers
def v_votes(ctx) -> list[dict]:
    p = ctx.root / "work" / "episodes"
    out = []
    for d in p.glob("*/decision.json"):
        try:
            j = jload(d)
        except ValueError:
            out.append(F("VOTES-JSON", f"{d} is not valid JSON", "votes: rerun `ig.py comments` and `vote.py tally` for that episode"))
            continue
        if not isinstance(j, dict) or not j:
            out.append(F("VOTES-EMPTY", f"{d} is empty", "votes: rerun `vote.py tally`"))
    return out


def v_script(ctx) -> list[dict]:
    ed = ctx.ep_dir
    out: list[dict] = []
    try:
        script, plan = jload(ed / "script.json"), jload(ed / "calm-plan.json")
        cap = (ed / "caption.txt").read_text(encoding="utf-8")
    except (OSError, ValueError) as e:
        return [F("SCRIPT-FILES", f"script.json, calm-plan.json or caption.txt is missing or not valid: {e}", "script: the writer must write all three files; rerun `daily.py run --force script`")]
    lines = script.get("lines")
    if not isinstance(lines, list) or not lines:
        return [F("SCRIPT-SCHEMA", "script.json has no lines", "script: the writer must write `lines`")]
    ids = [l.get("id") for l in lines]
    if len(ids) != len(set(ids)) or not all(isinstance(i, str) and i for i in ids):
        out.append(F("SCRIPT-SCHEMA", "line ids are missing or repeat", "script: every line needs a unique id"))
    from arabic_display import has_tashkeel
    for l in lines:
        for k in ("speaker", "text", "tts_text", "style"):
            if not isinstance(l.get(k), str) or not l[k].strip():
                out.append(F("SCRIPT-SCHEMA", f"line {l.get('id')} has no {k}", f"script: add {k} to line {l.get('id')}"))
        t, tts = str(l.get("text", "")), str(l.get("tts_text", ""))
        if "".join(AR_LETTER.findall(t)) != "".join(AR_LETTER.findall(tts)):
            out.append(F("SCRIPT-TTS-DRIFT", f"line {l.get('id')}: the caption text and the voice text have different letters", f"script: make tts_text the same letters as text for line {l.get('id')} (tashkeel only added)"))
        if has_tashkeel(t):
            out.append(F("SCRIPT-TASHKEEL", f"line {l.get('id')} text carries tashkeel", "script: text is the caption and has none; tashkeel lives in tts_text"))
        if len(t.split()) > MAX_LINE_WORDS:
            out.append(F("SCRIPT-LINE-LEN", f"line {l.get('id')} has {len(t.split())} words (max {MAX_LINE_WORDS}, about 8 s read aloud)", f"script: split line {l.get('id')} before it is voiced"))
    used = plan_line_ids(plan)
    orphan = [i for i in ids if i not in used]
    if orphan:
        out.append(F("SCRIPT-ORPHAN-LINE", f"{len(orphan)} script line(s) no scene, intro or choice uses: {', '.join(orphan[:6])} (they would be voiced for nothing)",
                     "script: remove them or give them a scene before the voice stage", "warn"))
    gone = sorted(used - set(ids))
    if gone:
        out.append(F("SCRIPT-PLAN-LINE", f"the plan names line(s) script.json does not have: {', '.join(gone[:6])}", "script: add the lines or fix the plan"))
    n_tags = len(re.findall(r"#\S+", cap))
    if n_tags != CAPTION_HASHTAGS:
        out.append(F("SCRIPT-CAPTION", f"caption.txt has {n_tags} hashtags (need {CAPTION_HASHTAGS})", "script: one line plus three hashtags, the same form every day"))
    if has_tashkeel(cap):
        out.append(F("SCRIPT-CAPTION", "caption.txt carries tashkeel", "script: no tashkeel in anything people see"))
    import daily
    bad = daily.validate_episode_files(ctx)
    for b in bad:
        cid = b.split(" ", 1)[0]
        out.append(F(cid, b.split(" ", 1)[1][:300] if " " in b else b, "script: edit calm-plan.json / caption.txt (the writer's files); the voice takes are not touched"))
    return out


def take_sources_path(ctx) -> Path:
    return ctx.root / "work" / "voice" / ctx.ep / "take-sources.json"


def v_voice(ctx) -> list[dict]:
    ed = ctx.ep_dir
    out: list[dict] = []
    try:
        script = jload(ed / "script.json")
    except (OSError, ValueError) as e:
        return [F("VOICE-NO-SCRIPT", f"script.json unreadable: {e}", "script: fix the script stage first")]
    vd = ctx.root / "work" / "voice" / ctx.ep
    lines = script.get("lines", [])
    missing = [l["id"] for l in lines if not (vd / f"{l['id']}.trimmed.wav").is_file()]
    if missing:
        out.append(F("VOICE-TAKES", f"no take for {len(missing)} line(s): {', '.join(missing[:8])}", "voice: rerun the voice stage; each line is voiced once"))
    sp = take_sources_path(ctx)
    try:
        rec = jload(sp) if sp.is_file() else {}
    except ValueError:
        rec = {}
    new = dict(rec)
    for l in lines:
        tk = vd / f"{l['id']}.trimmed.wav"
        if not tk.is_file():
            continue
        h = hashlib.sha256(str(l.get("tts_text", "")).encode("utf-8")).hexdigest()
        if l["id"] in rec and rec[l["id"]] != h:
            out.append(F("VOICE-STALE-TAKE", f"line {l['id']}: tts_text changed after its take was made (one take per line, no re-voice)",
                         f"script: restore line {l['id']} to the voiced text, or give the new wording a NEW line id and update the plan; the Lead decides before anything is voiced again"))
        new.setdefault(l["id"], h)
        try:
            sec, peak, rate = wav_info(tk)
        except Exception as e:     # noqa: BLE001 - an unreadable wav is a finding, not a crash
            out.append(F("VOICE-AUDIO", f"take {l['id']} cannot be read: {e}", "voice: the take file is damaged"))
            continue
        words = len(str(l.get("text", "")).split())
        if not TAKE_S[0] <= sec <= TAKE_S[1]:
            out.append(F("VOICE-LENGTH", f"take {l['id']} lasts {sec:.2f} s (band {TAKE_S[0]} to {TAKE_S[1]} s)", f"script: line {l['id']} is truncated or runaway; rewrite it under a new id"))
        elif words and not TAKE_WPS[0] <= words / sec <= TAKE_WPS[1]:
            out.append(F("VOICE-RATE", f"take {l['id']}: {words} words in {sec:.2f} s = {words / sec:.2f} words a second (band {TAKE_WPS[0]} to {TAKE_WPS[1]})",
                         f"voice: take {l['id']} is truncated or garbled; reword the line under a new id (no second take of the same line)"))
        if peak < TAKE_PEAK[0]:
            out.append(F("VOICE-SILENT", f"take {l['id']} peaks at {peak:.4f}: it is silent", "voice: the engine returned no speech for this line"))
        if peak > TAKE_PEAK[1]:
            out.append(F("VOICE-CLIPPED", f"take {l['id']} peaks at {peak:.4f}: it clips", "voice: the take is clipped; reword the line"))
    if new != rec and not any(o["id"] == "VOICE-STALE-TAKE" for o in out):
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text(json.dumps(new, indent=1, sort_keys=True), encoding="utf-8")
    extra = sorted(p.name.split(".")[0] for p in vd.glob("*.trimmed.wav") if p.name.split(".")[0] not in {l["id"] for l in lines})
    if extra:
        out.append(F("VOICE-ORPHAN-TAKE", f"{len(extra)} take(s) belong to no script line: {', '.join(extra[:6])}", "voice: harmless; they are ignored", "warn"))
    for l in lines:
        if l.get("speaker") != "narrator" and (vd / f"{l['id']}.trimmed.wav").is_file() and not (vd / "visemes" / f"{l['id']}.json").is_file():
            out.append(F("VOICE-VISEME", f"line {l['id']} ({l.get('speaker')}) has no mouth track", "voice: run `voice.py visemes` (without it no mouth moves)"))
    return out


def v_plan(ctx) -> list[dict]:
    import calm_compose as cc
    out: list[dict] = []
    tl = _timeline(ctx)
    if not tl or not tl.get("items"):
        return [F("PLAN-TL-SCHEMA", "timeline.json is missing or has no items", "plan: rerun the plan stage")]
    if tl.get("episode") != ctx.ep:
        out.append(F("PLAN-TL-SCHEMA", f"timeline.json is for {tl.get('episode')!r}, not {ctx.ep}", "plan: rerun the plan stage"))
    items = tl["items"]
    need = ("kind", "id", "shot", "video", "dur", "t0", "t1")
    for it in items:
        gone = [k for k in need if k not in it]
        if gone:
            out.append(F("PLAN-TL-SCHEMA", f"item {it.get('id')} lacks {', '.join(gone)}", "plan: rerun the plan stage"))
    if out:
        return out
    shots = [it["shot"] for it in items]
    if len(shots) != len(set(shots)):
        out.append(F("PLAN-TL-SCHEMA", "two timeline items share one shot name", "script: scene or intro ids repeat"))
    if abs(items[0]["t0"]) > 1e-6:
        out.append(F("PLAN-TL-ORDER", f"the first item starts at {items[0]['t0']} s, not 0", "plan: rerun the plan stage"))
    for a, b in zip(items, items[1:]):
        if abs(b["t0"] - (a["t1"] - tl.get("join_s", JOIN_S))) > 0.01:
            out.append(F("PLAN-TL-ORDER", f"{a['id']} -> {b['id']}: the join is not one join long ({a['t1']} / {b['t0']})", "plan: rerun the plan stage"))
            break
    bad_order = next((it for it in items if abs(it["t1"] - (it["t0"] + it["dur"])) > 0.01), None)
    if bad_order:
        out.append(F("PLAN-TL-ORDER", f"item {bad_order['id']}: t1 != t0 + dur", "plan: rerun the plan stage"))
    bad_snap = next((it for it in items if abs(it["dur"] * FPS - round(it["dur"] * FPS)) > 0.02), None)
    if bad_snap:
        out.append(F("PLAN-TL-SNAP", f"item {bad_snap['id']} lasts {bad_snap['dur']} s, not a whole number of frames at {FPS} fps", "plan: a length must be snapped to the frame"))
    if abs(tl.get("total_s", -1) - items[-1]["t1"]) > 0.01:
        out.append(F("PLAN-TL-ORDER", f"total_s {tl.get('total_s')} != the last item's end {items[-1]['t1']}", "plan: rerun the plan stage"))
    ok, detail, warn = cc.length_check(float(tl.get("total_s", 0)))
    if not ok:
        out.append(F("CALM-LENGTH", detail, "script: the story is under the 25 s floor; the writer adds scenes"))
    elif warn:
        out.append(F("CALM-LENGTH", warn, "plan: the story sets the length (the owner 2026-10-25); confirm", "warn"))
    try:
        plan = jload(ctx.ep_dir / "calm-plan.json")
    except (OSError, ValueError) as e:
        return out + [F("PLAN-TL-SCHEMA", f"plan or script unreadable: {e}", "script: fix the script stage")]
    placed: list[tuple[str, float]] = []
    for it in items:
        for ln in cc.item_lines(it):
            placed.append((ln["line"], ln["voice_t0"]))
            tk = ctx.root / "work" / "voice" / ctx.ep / f"{ln['line']}.trimmed.wav"
            if not tk.is_file():
                out.append(F("PLAN-TL-VOICE", f"line {ln['line']} is placed but has no take", "voice: rerun the voice stage"))
                continue
            sec = cc.wav_seconds(tk)
            end = ln["voice_t0"] + sec
            tail = it["t1"] + (0.05 if it.get("kind") != "card" else 0.6)     # a card's last line may finish over the follow card (calm_compose MAX_CARD_S)
            if ln["voice_t0"] < it["t0"] - 0.01 or end > tail + 0.01:
                out.append(F("PLAN-TL-VOICE", f"line {ln['line']} ({ln['voice_t0']:.2f} to {end:.2f} s) does not fit its item {it['id']} ({it['t0']} to {it['t1']} s)",
                             f"plan: lengthen the scene that carries {ln['line']} or shorten the line (before it is voiced)"))
    spans = sorted((t, t + cc.wav_seconds(ctx.root / "work" / "voice" / ctx.ep / f"{l}.trimmed.wav"), l) for l, t in placed if (ctx.root / "work" / "voice" / ctx.ep / f"{l}.trimmed.wav").is_file())
    for a, b in zip(spans, spans[1:]):
        if b[0] < a[1] - 0.02:
            out.append(F("PLAN-TL-OVERLAP", f"voice {a[2]} ({a[0]:.2f} to {a[1]:.2f} s) overlaps {b[2]} (starts {b[0]:.2f} s)", "plan: two lines speak at once; the plan must separate them"))
            break
    dup = sorted({l for l, _ in placed if [x for x, _t in placed].count(l) > 1})
    if dup:
        out.append(F("PLAN-TL-COVER", f"line(s) placed twice: {', '.join(dup[:6])}", "plan: a line is spoken once"))
    miss = sorted(plan_line_ids(plan) - {l for l, _ in placed})
    if miss:
        out.append(F("PLAN-TL-COVER", f"line(s) the plan uses but the timeline never speaks: {', '.join(miss[:6])}", "plan: rerun the plan stage; check the choice and intro lines"))
    ids = [it["id"] for it in items]
    if cc.recap_expected(plan) and ids[0] != "recap":
        out.append(F("PLAN-TL-WRAPPER", "the recap card does not open the episode", "plan: recaps start at E02"))
    if ids[-2:] != ["choice", "follow"]:
        out.append(F("PLAN-TL-WRAPPER", "the episode must end on the choice card then the follow card", "plan: the plan lost its choice or follow card"))
    for ix in plan.get("intros", []) or []:
        k = ids.index(ix["id"]) if ix["id"] in ids else -1
        if k < 1 or items[k - 1]["id"] != ix["after"]:
            out.append(F("PLAN-TL-INTRO", f"intro {ix['id']} does not follow scene {ix['after']}", "plan: an intro freezes right after the scene that first shows the character"))
    return out


def v_animatic(ctx) -> list[dict]:
    p = ctx.work / "animatic" / "report.json"
    try:
        rep = jload(p)
    except (OSError, ValueError):
        return [F("ANI-REPORT", f"{p} is missing: the animatic did not finish", "animatic: rerun `daily.py run --force animatic`")]
    out = [F(f["id"], f["msg"], f.get("fix", ""), f.get("sev", "fail")) for f in rep.get("findings", [])]
    tl = _timeline(ctx) or {}
    mp4 = ctx.work / "animatic" / "animatic.mp4"
    if not mp4.is_file():
        out.append(F("ANI-VIDEO", "animatic.mp4 is missing", "animatic: rerun the animatic stage"))
    else:
        pr = ffprobe_json(mp4)
        d = float((pr.get("format") or {}).get("duration") or 0)
        if tl and abs(d - float(tl.get("total_s", 0))) > 0.4:
            out.append(F("ANI-VIDEO", f"animatic.mp4 lasts {d:.2f} s, the timeline {tl.get('total_s')} s", "animatic: rerun the animatic stage"))
        if not any(s.get("codec_type") == "audio" for s in pr.get("streams", [])):
            out.append(F("ANI-VIDEO", "animatic.mp4 has no audio stream", "animatic: rerun the animatic stage"))
    return out


def v_shots(ctx) -> list[dict]:
    tl = _timeline(ctx)
    if not tl:
        return [F("SHOTS-NO-TIMELINE", "timeline.json is missing", "plan: run the plan stage first")]
    out: list[dict] = []
    seen = set()
    canvas = tl.get("canvas") or [1080, 1920]
    for it in tl["items"]:
        vids = [(it["shot"], ctx.root / it["video"], it.get("dur_shot", it["dur"]))]
        for c in (it.get("split") or {}).get("top", []):
            sn = f"{ctx.ep}-{c['shot']}"
            vids.append((sn, ctx.root / "work" / "shots" / sn / "out" / f"{sn}.mp4", None))
        for name, vp, need in vids:
            if name in seen:
                continue
            seen.add(name)
            if not vp.is_file():
                out.append(F("SHOTS-VIDEO", f"shot {name} has no video", f"shots: rerun the shots stage (shot {name})"))
                continue
            rep = ctx.root / "work" / "shots" / name / "gate" / "report.json"
            try:
                verdict = jload(rep).get("verdict")
            except (OSError, ValueError):
                verdict = None
            if verdict != "PASS":
                out.append(F("SHOTS-GATE-REPORT", f"shot {name}: gate report is {verdict or 'missing'}", f"shots: `shot.py all work/shots/{name}` must pass its own gates"))
            pr = ffprobe_json(vp)
            v = next((s for s in pr.get("streams", []) if s.get("codec_type") == "video"), None)
            if not v:
                out.append(F("SHOTS-VIDEO", f"shot {name}: no video stream", f"shots: rerun shot {name}"))
                continue
            d = float((pr.get("format") or {}).get("duration") or v.get("duration") or 0)
            if need and d + 0.1 < need:
                out.append(F("SHOTS-SHORT", f"shot {name} lasts {d:.2f} s but its planned length is {need:.2f} s (a stale shorter render ended the episode early on E01C)", f"shots: re-record shot {name}"))
            if [int(v.get("width", 0)), int(v.get("height", 0))] != [int(canvas[0]), int(canvas[1])]:
                out.append(F("SHOTS-SIZE", f"shot {name} is {v.get('width')}x{v.get('height')}, the canvas is {canvas[0]}x{canvas[1]}", f"shots: re-record shot {name}"))
            if abs(_fps(v.get("r_frame_rate", "0/1")) - FPS) > 0.05:
                out.append(F("SHOTS-FPS", f"shot {name} runs at {v.get('r_frame_rate')} fps, not {FPS}", f"shots: re-record shot {name}"))
    return out


def v_compose(ctx) -> list[dict]:
    out: list[dict] = []
    ep = ctx.work / "episode.mp4"
    tl = _timeline(ctx) or {}
    if not ep.is_file():
        return [F("COMPOSE-VIDEO", "episode.mp4 is missing", "compose: rerun the compose stage")]
    pr = ffprobe_json(ep)
    v = next((s for s in pr.get("streams", []) if s.get("codec_type") == "video"), {})
    a = next((s for s in pr.get("streams", []) if s.get("codec_type") == "audio"), None)
    d = float((pr.get("format") or {}).get("duration") or 0)
    if tl and abs(d - float(tl.get("total_s", 0))) > 0.25:
        out.append(F("COMPOSE-LENGTH", f"episode.mp4 lasts {d:.2f} s, the timeline {tl.get('total_s')} s", "shots: a shot file is shorter than planned; re-record it"))
    if [int(v.get("width", 0)), int(v.get("height", 0))] != [1080, 1920]:
        out.append(F("COMPOSE-SIZE", f"episode.mp4 is {v.get('width')}x{v.get('height')}", "compose: rerun the compose stage"))
    if abs(_fps(v.get("r_frame_rate", "0/1")) - FPS) > 0.05:
        out.append(F("COMPOSE-FPS", f"episode.mp4 runs at {v.get('r_frame_rate')} fps", "compose: rerun the compose stage"))
    if not a or int(a.get("sample_rate", 0) or 0) != 48000:
        out.append(F("COMPOSE-AUDIO", "episode.mp4 has no 48 kHz audio stream", "compose: rerun the compose stage"))
    try:
        caps = jload(ctx.work / "captions.json")["captions"]
    except (OSError, ValueError, KeyError):
        return out + [F("COMPOSE-CAPTIONS", "captions.json is missing", "compose: rerun the compose stage")]
    missing = [c["png"] for c in caps if not (ctx.work / c["png"]).is_file()]
    if missing:
        out.append(F("COMPOSE-PLATES", f"{len(missing)} plate image(s) are missing: {', '.join(missing[:3])}", "compose: rerun the compose stage"))
    try:       # the animatic predicted these plates; the real ones must be the same sentences at the same times (else its verdict does not hold for this episode)
        pred = jload(ctx.work / "animatic" / "report.json").get("plates")
    except (OSError, ValueError):
        pred = None
    if pred is not None:
        real = [(c["line"], c["unit"], c["active_index"], c["start"], c["end"]) for c in sorted(caps, key=lambda c: (c["start"], c["line"]))]
        same = len(real) == len(pred) and all(a[:3] == tuple(b[:3]) and abs(a[3] - b[3]) <= 0.02 and abs(a[4] - b[4]) <= 0.02 for a, b in zip(real, pred))
        if not same:
            out.append(F("COMPOSE-ANIMATIC-DRIFT", f"the composed captions ({len(real)} plates) differ from the animatic's ({len(pred)}); the early checks do not cover this build",
                         "animatic: rerun `daily.py run --force animatic`, then compose"))
    return out


def v_gates(ctx) -> list[dict]:
    try:
        rep = jload(ctx.work / "gate" / "report.json")
    except (OSError, ValueError):
        return [F("GATE-REPORT", "gate/report.json is missing", "gates: rerun the gates stage")]
    out: list[dict] = []
    if rep.get("verdict") != "PASS":
        out.append(F("GATE-VERDICT", f"the gate verdict is {rep.get('verdict')}: {'; '.join(rep.get('fails', [])[:3])}", "gates: fix the failing check at its stage"))
    if rep.get("complete") is False:
        out.append(F("GATE-INCOMPLETE", "the gate ran without the render checks (--skip-render-gate)", "gates: rerun the full gate"))
    ids = {c.get("id") for c in rep.get("checks", []) if c.get("status") == "pass"}
    need = GATE_REQUIRED
    try:      # format v2 (the owner 2026-10-28), from E03 on: the three new checks must have run and passed
        import calm_compose as _cc
        if _cc.format_v2(jload(ctx.ep_dir / "calm-plan.json")):
            need = GATE_REQUIRED + GATE_REQUIRED_V2
    except (OSError, ValueError):
        pass
    gone = [c for c in need if c not in ids]
    if gone:
        out.append(F("GATE-INCOMPLETE", f"required check(s) did not pass or did not run: {', '.join(gone)}", "gates: a skipped check is a failure; rerun the full gate"))
    return out


def v_critic(ctx) -> list[dict]:
    try:
        j = jload(ctx.work / "heal" / "critic.json")
    except (OSError, ValueError):
        return [F("CRITIC-FILE", "heal/critic.json is missing or invalid", "critic: rerun the critic stage")]
    out: list[dict] = []
    ans = j.get("answers") or []
    got = {a.get("q") for a in ans}
    gone = [f"Q{i:02d}" for i in range(1, 13) if f"Q{i:02d}" not in got]
    if gone:
        out.append(F("CRITIC-INCOMPLETE", f"unanswered: {', '.join(gone)}", "critic: rerun the critic stage"))
    blank = [a.get("q") for a in ans if not str(a.get("evidence", "")).strip()]
    if blank:
        out.append(F("CRITIC-EVIDENCE", f"answers without evidence: {', '.join(map(str, blank[:6]))}", "critic: every answer names a frame or a line"))
    faults = {f.get("q") for f in j.get("faults", [])}
    unex = [a.get("q") for a in ans if a.get("ok") is False and a.get("q") not in faults]
    if unex:
        out.append(F("CRITIC-UNEXPLAINED", f"failed answers with no fault entry: {', '.join(map(str, unex[:6]))}", "critic: each failed answer lists its fault", "warn"))
    sc = j.get("score")
    if not isinstance(sc, int) or isinstance(sc, bool) or not 1 <= sc <= 10:
        out.append(F("CRITIC-SCORE", f"score {sc!r} is not an integer 1..10", "critic: rerun the critic stage"))
    sha = j.get("video_sha")
    cur = sha_file(ctx.work / "episode.mp4")
    if sha and sha != cur:
        out.append(F("CRITIC-STALE", "the critic judged a different episode.mp4 than the one on disk", "critic: rerun the critic stage"))
    return out


def _v_facebook(ctx) -> list[dict]:
    fbp = ctx.work / "facebook.json"
    if not fbp.is_file():
        return []
    try:
        fj = jload(fbp)
    except ValueError:
        return [F("PUBLISH-RECORD", "facebook.json is not valid JSON", "publish: do not post to Facebook again; read the Page and repair facebook.json by hand")]
    if not fj.get("video_id"):
        return [F("PUBLISH-RECORD", "facebook.json carries no video id", "publish: check the Facebook Page before posting again")]
    return []


def v_publish(ctx) -> list[dict]:
    post = ctx.work / "post.json"
    if not post.is_file():
        return _v_facebook(ctx)         # a dry run or a missing token is a skipped stage, not a fault
    try:
        j = jload(post)
    except ValueError:
        return [F("PUBLISH-RECORD", "post.json is not valid JSON", "publish: do not post again; read the Instagram account and repair post.json by hand")]
    if not (j.get("media_id") or j.get("id") or j.get("permalink")):
        return [F("PUBLISH-RECORD", "post.json carries no media id", "publish: check the account before posting again")]
    return _v_facebook(ctx)


def v_schedule(ctx) -> list[dict]:
    if not (ctx.work / "post.json").is_file():
        return []
    t = ctx.dir / "harvest-task.txt"
    if not t.is_file() or not t.read_text(encoding="utf-8").strip():
        return [F("SCHEDULE-PLAN", "harvest-task.txt is missing or empty after a post", "schedule: rerun `daily.py post` (the harvest plan)")]
    return []


def v_retro(ctx) -> list[dict]:
    """Report-only (sev warn, never stops a run): the build retro (tools/learn.py) must not block anything; a retro that kept only its facts is named in the verify report."""
    try:
        j = json.loads((ctx.work / "learn" / "retro.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [F("RETRO-MISSING", "learn/retro.json is missing", "learn.py retro <ep>", sev="warn")]
    return [] if j.get("status") == "done" else [F("RETRO-FACTS-ONLY", f"the retro kept only its facts: {str(j.get('error'))[:120]}", "learn.py retro <ep> --force", sev="warn")]


VERIFY = {"votes": v_votes, "script": v_script, "voice": v_voice, "plan": v_plan, "animatic": v_animatic, "shots": v_shots, "compose": v_compose, "gates": v_gates, "critic": v_critic,
          "retro": v_retro, "publish": v_publish, "schedule": v_schedule}


def contract(name: str, ctx, entry: dict, declared_inputs: dict | None) -> list[dict]:
    """The generic contract of every stage: its outputs exist and are not empty, JSON outputs parse, and every declared input has a recorded hash that did not move during the run."""
    out: list[dict] = []
    for p in output_paths(name, ctx):
        if not p.exists() or (p.is_file() and p.stat().st_size == 0):
            out.append(F("CONTRACT-OUTPUT", f"{name}: output {p.name} is missing or empty", f"{name}: rerun the stage"))
        elif p.suffix == ".json":
            try:
                json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                out.append(F("CONTRACT-OUTPUT", f"{name}: {p.name} is not valid JSON", f"{name}: rerun the stage"))
    if declared_inputs:
        rec = entry.get("inputs") or {}
        lost = [k for k in declared_inputs if k not in rec]
        if lost:
            out.append(F("CONTRACT-INPUTS", f"{name}: no hash recorded for input(s) {', '.join(lost)}", f"{name}: rerun the stage"))
        now = fingerprint(declared_inputs)
        moved = [k for k in rec if k in now and rec[k] != now[k]]
        if moved:
            out.append(F("CONTRACT-INPUT-MOVED", f"{name}: input(s) changed while the stage ran: {', '.join(moved)}", f"{name}: a stage may not change what it reads; find the writer and rerun"))
    return out


def brief(stage: str, findings: list[dict], ep: str) -> str:
    """The fix brief of a stopped run: one block per failing check. After the fix, `daily.py run` reruns only the stages whose inputs changed."""
    rows = [f"- `{f['id']}` {f['msg']}\n  fix: {f['fix'] or 'see pipelines/STAGE-GATES.md'}" for f in findings if f.get("sev", "fail") == "fail"]
    return (f"stage {stage} produced its files but its VERIFY failed ({len(rows)} check(s)):\n" + "\n".join(rows[:12]) +
            f"\n\nAfter the fix run `uv run tools/daily.py run --ep {ep}`: only the stages whose inputs changed rerun (hash-based), each with its own verify.")


def stale_downstream(order: list[str], first: str) -> list[str]:
    """The stages that come after `first`, in order (the planner of a fix; the real decision is the hash comparison in daily.stage_state)."""
    return order[order.index(first) + 1:] if first in order else []
