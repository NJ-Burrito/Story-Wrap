# /// script
# requires-python = ">=3.11"
# dependencies = ["playwright", "pillow", "numpy", "scipy"]
# ///
"""Story-Wrap shot pipeline: ONE resumable path from an empty folder to a gated, recorded shot (the Mix v5 path).

  uv run tools/shot.py <stage> <shot-dir> [--force] [--template NAME]
  uv run tools/shot.py status <shot-dir>

Stages, in order (each writes its output files and records status + input hashes in <shot-dir>/STATE.json;
a rerun skips a finished stage whose inputs did not change):
  init       scaffold work/shots/<id>/ from tools/templates/<template>/ (shot.json, plan/, scene/) + STATE.json
  catalogue  every catalogue ref the shot uses exists (character model/pose/hand/face/angle/prop); lists what must be built new
  camera     plan/camera.py -> camera-plan.json + thumbnails; validated (CAMERA-*)
  spec       plan/spec.py -> shot-spec.json; runs the spec gate (quality_gate.py spec --files)
  build      generate build/index.html from the SHARED renderer library tools/render/ + the shot's scene/; syntax + load smoke test
  trace      export rig-trace.json + text/shadow/line masks (browser, frame counter, no video)
  record     deterministic frame-counter capture: 1080x1920, 24 fps, h264_nvenc, GPU Chrome -> out/<id>.mp4
  gate       spec, rig (incl. SEAM + hands), hands, extras, look2d, preview, render: all, one report (gate/report.json)
  review     frame-by-frame contact sheets (hands, faces, props, every Nth frame) for the human/agent look pass
  all        run the stages above in order, stop at the first failure
  heal       OPTIONAL, after gate/review when pipelines/heal.json says enabled: snapshot the gates, classify faults, write
             heal/critic-brief.md and heal/fix-brief.md (tools/heal.py; the critic and fixer are agents the Lead dispatches).
             `all` ends with it. the owner sees the shot only when `heal.py status` says ready. See pipelines/HEAL.md.

Exit 0 = ok, 1 = a stage failed (prints 'FAIL [CHECK-ID] message' and records it in STATE.json), 2 = usage or tool error.
GPU first: NVENC encode, NVDEC decode, GPU Chromium. At most 2 heavy CPU jobs (everything here runs one at a time).
"""
from __future__ import annotations
import importlib.util, json, os, re, shutil, subprocess, sys, time
from pathlib import Path
from types import SimpleNamespace

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
from shotlib.engine import STAGE_ORDER, Stage, StageFail, State, run_stage, is_fresh, hash_inputs   # noqa: E402

TRASH = Path.home() / ".claude" / "skills" / "safe-delete" / "scripts" / "trash.py"
ENV = {**os.environ, "PYTHONUTF8": "1"}


# ------------------------------------------------------------------ helpers
def load_shot(sd: Path) -> dict:
    p = Path(sd) / "shot.json"
    if not p.is_file():
        raise StageFail("INIT-MISSING", f"{p} not found: run `shot.py init {sd}` first")
    shot = json.loads(p.read_text(encoding="utf-8"))
    shot["rel"] = Path(sd).resolve().relative_to(ROOT).as_posix()
    return shot


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def recycle(p: Path):
    """Deletions go to the recycle bin (safe-delete), never rm."""
    if not p.exists():
        return
    if not TRASH.is_file():
        raise StageFail("TOOL-ERROR", f"safe-delete script missing at {TRASH}; refusing to delete {p}")
    r = subprocess.run([sys.executable, str(TRASH), str(p)], capture_output=True, text=True, env=ENV)
    if r.returncode != 0 or p.exists():
        raise StageFail("TOOL-ERROR", f"could not recycle {p}: {r.stdout[-200:]} {r.stderr[-200:]}")


def gate_cmd(args: list[str]) -> tuple[int, str]:
    """Run tools/quality_gate.py through uv (it carries its own dependencies). Returns (exit code, combined output)."""
    r = subprocess.run(["uv", "run", str(TOOLS / "quality_gate.py"), *args], capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV, cwd=ROOT)
    return r.returncode, (r.stdout or "") + (("\n" + r.stderr) if r.returncode == 2 else "")


FAIL_RE = re.compile(r"^FAIL(?: \[([A-Za-z0-9_-]+)\]| ([A-Za-z0-9_]+))")


def failing_ids(text: str) -> list[str]:
    ids = []
    for line in text.splitlines():
        m = FAIL_RE.match(line.strip())
        if m:
            ids.append(m.group(1) or m.group(2))
    return ids


def first_fail_line(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("FAIL ") or line.startswith("TOOL ERROR"):
            return line.strip()
    return text.strip().splitlines()[-1] if text.strip() else "no output"


def recorder_run(sd: Path, shot: dict, expr: str, timeout_s: float = 1200):
    """Start the local recorder server, open the shot page in GPU Chromium, run `expr`, always close both. Returns the driver dict."""
    from record import server, driver
    out = sd / "out"
    out.mkdir(parents=True, exist_ok=True)
    srv = server.start(ROOT, out, shot["fps"])
    try:
        url = f"http://127.0.0.1:{srv.port}/{shot['rel']}/build/index.html"
        return driver.drive(url, expr, timeout_s)
    finally:
        srv.stop()



# ------------------------------------------------------------------ stage bodies
def s_init(sd: Path, template: str = "shot"):
    tpl = TOOLS / "templates" / template
    if not tpl.is_dir():
        raise StageFail("INIT-TEMPLATE", f"template {tpl} not found")
    sd.mkdir(parents=True, exist_ok=True)
    for src in tpl.rglob("*"):
        if src.is_dir() or "__pycache__" in src.parts:
            continue
        dst = sd / src.relative_to(tpl)
        if dst.exists():
            continue   # never overwrite the shot's own data
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    p = sd / "shot.json"
    t = p.read_text(encoding="utf-8")
    p.write_text(t.replace("SHOT_ID", sd.name), encoding="utf-8")
    return {"template": template}


def s_catalogue(sd: Path):
    from shotlib import catalogue
    shot = load_shot(sd)
    report, fails = catalogue.check(shot, ROOT)
    (sd / "catalogue-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    if fails:
        raise StageFail(fails[0].split(" ", 1)[0], "; ".join(f.split(" ", 1)[1] for f in fails[:6]) + (f" (+{len(fails) - 6} more)" if len(fails) > 6 else ""))
    return {"found": len(report["found"]), "to_build": report["to_build"]}


def s_camera(sd: Path):
    from shotlib import camera
    shot = load_shot(sd)
    mod = load_module(sd / "plan" / "camera.py", "shot_plan_camera")
    plan = camera.build_plan(sd, shot, mod)
    fails = camera.validate_plan(plan, shot, ROOT)
    if fails:
        raise StageFail(fails[0].split(" ", 1)[0], "; ".join(f.split(" ", 1)[1] for f in fails[:6]))
    return {"shots": len(plan["shots"]), "beats": len(plan["beats"])}


def _voice_take(voicetiming, episode, line, visemes=True):
    if not episode:
        raise StageFail("SPEC-VOICE-TIMING", "no episode to read the voice from: shot.json piece.episode is empty")
    try:
        return voicetiming.take(ROOT, episode, line, need_visemes=visemes)
    except voicetiming.VoiceTimingError as e:
        raise StageFail(voicetiming.CHECK_ID, "; ".join(e.problems))


def s_spec(sd: Path):
    from shotlib import catalogue
    shot = load_shot(sd)
    plan = json.loads((sd / "camera-plan.json").read_text(encoding="utf-8"))
    cats = {a["module"]: catalogue.Catalogue(ROOT, a["module"]) for a in catalogue.actor_list(shot)}   # one catalogue per character (several actors: one each)
    from shotlib import voicetiming
    ep_id = (shot.get("piece") or {}).get("episode")   # voice first: the piece's lines are timed from work/voice/<episode>, never from estimates
    lib = SimpleNamespace(camera_ref=lambda character, name: cats[character].camera_ref(character, name),
                          voice_take=lambda line, episode=None, visemes=True: _voice_take(voicetiming, episode or ep_id, line, visemes))
    has = lambda ref: any(c.has(ref) for c in cats.values())
    mod = load_module(sd / "plan" / "spec.py", "shot_plan_spec")
    spec = mod.build(plan, shot, lib)
    if ep_id and "voice_episode" not in spec:
        spec["voice_episode"] = ep_id   # opts the spec into the voice-first checks
    if spec.get("voice_lines") or spec.get("voice_episode"):
        try:
            voicetiming.resolve(spec, ROOT, spec.get("voice_episode"), shot.get("duration_s"))
        except voicetiming.VoiceTimingError as e:
            raise StageFail(voicetiming.CHECK_ID, "; ".join(e.problems[:4]) + (f" (+{len(e.problems) - 4} more)" if len(e.problems) > 4 else ""))
    (sd / "shot-spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
    # catalogue refs the spec names (poses, cameras) must exist or be declared new
    refs = [p.get("catalogue") for b in spec.get("beats", []) for p in b.get("poses", []) if p.get("catalogue")]
    refs += [c.get("catalogue_camera") for c in spec.get("camera_plan", []) if c.get("catalogue_camera")]
    declared = set(shot.get("new", []))
    bad = [r for r in refs if r.split(" ")[0] not in declared and not has(r.split(" ")[0])]
    if bad:
        raise StageFail("SPEC-CATALOGUE", f"spec names catalogue refs that do not exist: {sorted(set(bad))}")
    (sd / "gate").mkdir(exist_ok=True)
    rc, out = gate_cmd(["spec", str(sd / "shot-spec.json"), "--files", "--root", str(ROOT)])
    (sd / "gate" / "spec.out").write_text(out, encoding="utf-8")
    if rc != 0:
        ids = failing_ids(out)
        raise StageFail(ids[0] if ids else "SPEC-GATE", f"spec gate failed ({len(ids)} checks: {', '.join(sorted(set(ids))[:12])}); first: {first_fail_line(out)}")
    return {"beats": len(spec["beats"]), "transitions": len(spec["transitions"])}


def s_build(sd: Path):
    from shotlib import page
    shot = load_shot(sd)
    # syntax check every script the page loads (node --check): a typo fails here, before a browser is opened
    node = shutil.which("node")
    manifest = page.write_build(ROOT, sd, shot)
    if node:
        for u in manifest["scripts"]:
            f = ROOT / u.lstrip("/")
            r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True, encoding="utf-8", errors="replace")
            if r.returncode != 0:
                raise StageFail("BUILD-SYNTAX", f"{u}: {(r.stderr or r.stdout).strip().splitlines()[0:3]}")
    res = recorder_run(sd, shot, "Shot.diag()", 300)
    errs = [e for e in res["errors"] if e.startswith("pageerror") or e.startswith("error")]
    if errs or not res["result"]:
        raise StageFail("BUILD-LOAD", f"page did not load cleanly: {errs[:3]}")
    diag = res["result"]
    (sd / "build" / "diag.json").write_text(json.dumps(diag, indent=1), encoding="utf-8")
    nf = round(shot["fps"] * shot["duration_s"])
    if diag.get("frames") != nf:
        raise StageFail("BUILD-FRAMES", f"renderer reports {diag.get('frames')} frames, shot.json says {nf}")
    return {"scripts": len(manifest["scripts"]), "frames": nf}


def _clean_masks(sd: Path):
    recycle(sd / "out" / "masks")


def s_trace(sd: Path):
    shot = load_shot(sd)
    nf = round(shot["fps"] * shot["duration_s"])
    _clean_masks(sd)
    res = recorder_run(sd, shot, "Shot.record({video:false})", 1800)
    st = res["result"] or {}
    if st.get("err") or not st.get("done"):
        raise StageFail("TRACE-INCOMPLETE", f"trace pass did not finish: {str(st.get('err'))[:400]}")
    tp = sd / "out" / "rig-trace.json"
    tr = json.loads(tp.read_text(encoding="utf-8"))
    chars = tr["characters"]
    from shotlib import presence   # per-actor frame ranges: an actor that enters, exits or is cut between is traced on its own frames only
    issues = presence.trace_issues(chars, shot.get("actors") or None, nf, sd / "out" / "masks")
    if issues:
        raise StageFail("TRACE-INCOMPLETE", f"{'; '.join(issues[:4])}" + (f" (+{len(issues) - 4} more)" if len(issues) > 4 else ""))
    shadows = len(list((sd / "out" / "masks" / "shadow").rglob("*.png")))
    return {"frames": nf, "actors": sorted(chars), "shadow_masks": shadows, "line_masks": len(list((sd / "out" / "masks" / "line").rglob("*.png"))),
            "text_masks": len(list((sd / "out" / "masks" / "text").rglob("*.png")))}


def probe_video(p: Path) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                        "stream=codec_name,width,height,r_frame_rate,nb_read_frames,pix_fmt", "-of", "json", str(p)], capture_output=True, text=True)
    return json.loads(r.stdout)["streams"][0]


def s_record(sd: Path):
    shot = load_shot(sd)
    nf = round(shot["fps"] * shot["duration_s"])
    res = recorder_run(sd, shot, "Shot.record({data:false})", 1800)
    st = res["result"] or {}
    if st.get("err") or not st.get("done"):
        raise StageFail("RECORD-INCOMPLETE", f"record pass did not finish: {str(st.get('err'))[:400]}")
    out = sd / "out"
    enc = json.loads((out / f"{shot['id']}.encode.json").read_text(encoding="utf-8"))
    if enc["ffmpeg_exit"] != 0 or enc["frames"] != nf:
        raise StageFail("RECORD-ENCODE", f"encoder exit {enc['ffmpeg_exit']}, frames {enc['frames']} (need {nf})")
    v = probe_video(out / f"{shot['id']}.mp4")
    W, H = shot["canvas"]
    want = f"{shot['fps']}/1"
    bad = [k for k, ok in (("codec h264", v["codec_name"] == "h264"), (f"size {W}x{H}", (v["width"], v["height"]) == (W, H)),
                           (f"{shot['fps']} fps", v["r_frame_rate"] == want), (f"{nf} frames", int(v["nb_read_frames"]) == nf), ("yuv420p", v["pix_fmt"] == "yuv420p")) if not ok]
    if bad:
        raise StageFail("RECORD-FORMAT", f"video {v} fails: {bad}")
    return {"frames": nf, "size": f"{W}x{H}", "fps": shot["fps"], "codec": "h264_nvenc"}


GATES = ["spec", "rig", "hands", "extras", "look2d", "preview", "render"]


def s_gate(sd: Path):
    shot = load_shot(sd)
    out, g = sd / "out", sd / "gate"
    g.mkdir(exist_ok=True)
    vid, trace, spec = out / f"{shot['id']}.mp4", out / "rig-trace.json", sd / "shot-spec.json"
    fmt = ["--format", shot["format"]] if shot.get("format") else []   # "calm": the calm-format profile (pacing checks only; research/stickman-replication.md 5); default = premium
    cmds = {
        "spec": ["spec", str(spec), "--files", "--root", str(ROOT), *fmt],
        "rig": ["rig", str(trace), str(spec)],
        "hands": ["hands", str(trace)],
        "extras": ["extras", str(vid), str(spec), "--text-mask-dir", str(out / "masks" / "text"), "--shadow-dir", str(out / "masks" / "shadow")],
        "look2d": ["look2d", str(vid), "--json", str(g / "look2d.json")],
        "preview": ["preview", str(ROOT / "previews" / "index.html")],
        "render": ["render", str(vid), "--quiet", "--json", str(g / "render.json"), *fmt, *(["--event"] if shot.get("event") else [])],   # an event shot: the action ceilings (qg_checks.CALM_EVENT_CEILING)
    }
    report = {"shot": shot["id"], "gates": {}, "fails": []}
    for name in GATES:
        t0 = time.time()
        rc, text = gate_cmd(cmds[name])
        (g / f"{name}.out").write_text(text, encoding="utf-8")
        ids = failing_ids(text) if rc == 1 else (["TOOL-ERROR"] if rc == 2 else [])
        report["gates"][name] = {"verdict": "PASS" if rc == 0 else "FAIL", "exit": rc, "fail_ids": sorted(set(ids)), "seconds": round(time.time() - t0, 1)}
        report["fails"] += [f"{name}:{i}" for i in sorted(set(ids))]
        if rc == 2:
            report["gates"][name]["error"] = first_fail_line(text)
    for name, f in (("render", g / "render.json"), ("look2d", g / "look2d.json")):
        if f.is_file():
            report["gates"][name]["metrics"] = {k: v for k, v in json.loads(f.read_text(encoding="utf-8")).items() if k not in ("fails",)}
    report["verdict"] = "FAIL" if report["fails"] else "PASS"
    (g / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = [f"gate report for {shot['id']}: {report['verdict']}"] + [f"  {n:8s} {r['verdict']}  {', '.join(r['fail_ids'])}" for n, r in report["gates"].items()]
    (g / "report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if report["fails"]:
        first = report["fails"][0].split(":", 1)[1]
        raise StageFail(first, f"gate failed: {', '.join(report['fails'][:14])}  (details: {g / 'report.txt'})")
    return {n: r["verdict"] for n, r in report["gates"].items()}


def s_review(sd: Path):
    from shotlib import review
    shot = load_shot(sd)
    out = sd / "out"
    res = review.run(out / f"{shot['id']}.mp4", out / "rig-trace.json", sd / "review", shot["canvas"], shot.get("review", {}))
    empty = [k for k in ("hands", "faces", "props", "frames") if not res[k]["tiles"]]
    if "frames" in empty:
        raise StageFail("REVIEW-EMPTY", "no frames could be extracted from the video")
    return {k: res[k]["tiles"] for k in ("hands", "faces", "props", "frames")}


# ------------------------------------------------------------------ stage table (inputs decide what 'unchanged' means)
def build_stages(sd: Path, template: str = "shot") -> list[Stage]:
    shot = json.loads((sd / "shot.json").read_text(encoding="utf-8")) if (sd / "shot.json").is_file() else {"id": sd.name, "character": "hero"}
    shot = {"id": sd.name, "character": "hero", **shot}
    if shot.get("kind") == "card":   # a calm-format card (tools/calm_cards.py): text on a plate, the same stage names, its own checks
        if (shot.get("card") or {}).get("template") == "intro_freeze":   # C10: the character introduction (tools/calm_intro.py): a frozen frame, a grey glow, graffiti
            import calm_intro
            return calm_intro.stages(sd)
        import calm_cards
        return calm_cards.stages(sd)
    vid = sd / "out" / f"{shot['id']}.mp4"
    from shotlib import catalogue as _cat
    cat_index = [ROOT / "catalogue" / "characters" / a["module"] / "index.json" for a in _cat.actor_list(shot)] if (shot.get("actors") or shot.get("catalogue")) else [ROOT / "catalogue" / "characters" / shot.get("character", "hero") / "index.json"]
    cat_files = _cat.input_files(shot, ROOT)   # every catalogue file + character/world module the shot resolves
    lib = lambda *n: [TOOLS / "shotlib" / x for x in n]
    buildfiles = [sd / "build" / "manifest.json", sd / "build" / "index.html", sd / "build" / "shot-config.js", sd / "camera-plan.json"] + cat_files
    return [
        Stage("init", lambda d: [], lambda d: [d / "shot.json", d / "plan" / "camera.py", d / "plan" / "spec.py", d / "scene" / "main.js"], lambda d: s_init(d, template)),
        Stage("catalogue", lambda d: [d / "shot.json"] + cat_index + cat_files + lib("catalogue.py"), lambda d: [d / "catalogue-report.json"], s_catalogue),
        Stage("camera", lambda d: [d / "shot.json", d / "plan" / "camera.py"] + cat_files + lib("camera.py"), lambda d: [d / "camera-plan.json"], s_camera),
        Stage("spec", lambda d: [d / "shot.json", d / "plan" / "spec.py", d / "camera-plan.json"] + cat_index + cat_files + [TOOLS / "quality_gate.py", TOOLS / "qg_checks.py"] + lib("catalogue.py"),
              lambda d: [d / "shot-spec.json", d / "gate" / "spec.out"], s_spec),
        Stage("build", lambda d: [d / "shot.json", d / "scene", d / "camera-plan.json", TOOLS / "render"] + cat_files + lib("page.py"),
              lambda d: [d / "build" / "index.html", d / "build" / "manifest.json", d / "build" / "diag.json"], s_build),
        Stage("trace", lambda d: buildfiles, lambda d: [d / "out" / "rig-trace.json"], s_trace),
        Stage("record", lambda d: buildfiles, lambda d: [vid, d / "out" / f"{shot['id']}.encode.json"], s_record),
        Stage("gate", lambda d: [vid, d / "out" / "rig-trace.json", d / "out" / "masks", d / "shot-spec.json", TOOLS / "quality_gate.py", TOOLS / "qg_checks.py", ROOT / "previews" / "index.html"],
              lambda d: [d / "gate" / "report.json", d / "gate" / "report.txt"], s_gate),
        Stage("review", lambda d: [vid, d / "out" / "rig-trace.json", d / "shot.json"] + lib("review.py"), lambda d: [d / "review" / "index.json"], s_review),
    ]


def run_pipeline(stage: str, sd: Path, force: bool = False, template: str = "shot", log=print) -> list[tuple[str, str]]:
    """Run one stage (after checking the stages before it are fresh) or `all`. Raises StageFail."""
    stages_for = lambda: build_stages(sd, template)
    done: list[tuple[str, str]] = []
    if stage == "all":
        for name in STAGE_ORDER:
            st = next(s for s in stages_for() if s.name == name)   # rebuilt each time: shot.json exists after init
            done.append((name, run_stage(st, sd, ROOT, force=force, log=log)))
        return done
    if stage not in STAGE_ORDER:
        raise StageFail("USAGE", f"unknown stage {stage!r}; stages: {', '.join(STAGE_ORDER)}, all, status")
    if stage != "init":
        if not (sd / "shot.json").is_file():
            raise StageFail("PREREQ", f"{sd} has no shot.json: run `shot.py init {sd}` first")
        state = State(sd)
        for prev in STAGE_ORDER[:STAGE_ORDER.index(stage)]:
            st = next(s for s in stages_for() if s.name == prev)
            fresh, _ = is_fresh(st, sd, state, ROOT)
            if not fresh:
                raise StageFail("PREREQ", f"stage {prev!r} is not finished for the current inputs: run `shot.py {prev} {sd}` (or `all`) first")
    st = next(s for s in stages_for() if s.name == stage)
    return [(stage, run_stage(st, sd, ROOT, force=force, log=log))]


def status(sd: Path) -> str:
    state = State(sd)
    rows = []
    stages = build_stages(sd)
    for st in stages:
        e = state.get(st.name)
        fresh, _ = is_fresh(st, sd, state, ROOT) if (sd / "shot.json").is_file() or st.name == "init" else (False, {})
        label = "ok (fresh)" if fresh else (e.get("status", "-") + (" (stale: inputs changed)" if e.get("status") == "ok" else ""))
        extra = f"  FAIL [{e.get('check')}] {e.get('message', '')[:100]}" if e.get("status") == "failed" else ""
        rows.append(f"{st.name:10s} {label}{extra}")
    return "\n".join(rows)


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    force = "--force" in argv
    template = argv[argv.index("--template") + 1] if "--template" in argv else "shot"
    if template in args:
        args.remove(template)
    if len(args) != 2:
        print(__doc__)
        return 2
    stage, sdp = args
    sd = Path(sdp).resolve()
    try:
        sd.relative_to(ROOT)
    except ValueError:
        print(f"FAIL [USAGE] the shot dir must be inside {ROOT} (the recorder serves the repo root)")
        return 2
    try:
        if stage == "status":
            print(status(sd)); return 0
        if stage == "heal":
            import heal
            res = heal.prepare(sd, "shot", ROOT)
            return 0 if res is None or res["ready_for_owner"] else 1
        done = run_pipeline(stage, sd, force=force, template=template)
        print("OK " + ", ".join(f"{n}:{r}" for n, r in done))
        if stage == "all" and json.loads((sd / "shot.json").read_text(encoding="utf-8")).get("kind") != "card":   # a calm card has its own CARD-* gate: nothing for the shot healer to classify
            import heal
            heal.prepare(sd, "shot", ROOT)   # optional stage: prints what is still needed, never changes the exit code
        return 0
    except StageFail as e:
        print(f"FAIL [{e.check}] {e.message}")
        return 2 if e.check in ("USAGE",) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
