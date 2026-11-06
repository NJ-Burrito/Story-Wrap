# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""LINE-REFIT: the cure when a voiced line is too long for its slot (owner, 2026-10-30: "never stop again", rule R-502).

The plan stage raises PLAN-DURATION when a take is longer than the slot the plan gives it (the recap card 3.0 s, a scene 10 s, an intro 9 s, the choice sequence 16 s). A line is voiced
ONCE (R-4xx), so the old answer was to stop: E04 (2026-10-29) and E05 (2026-10-30, the recap line H01, 3.88 s against 3.0 s) were parked for the day.

`cure(ctx, error)` is called by `daily.py run` the moment the plan stage fails with PLAN-DURATION (and by `daily.py refit` and the Lead action "refit-line"):

  1. finds the lines whose real take is over their slot (tools/line_fit.overruns - the plan stage's own arithmetic),
  2. has the writer (one small headless Sonnet call per line, Read + Write under work/daily/ only) rewrite ONLY that line, shorter, to a stated length,
  3. gives the rewrite a NEW line id (H01 -> H01r1 -> H01r2): script.json and calm-plan.json point at the new id; the old take stays on disk, unused (never re-voiced, never deleted),
  4. marks the new id as the only line the voice stage may voice (voice.cmd_refit_mark) and runs the voice stage: ONE take, no verify, no re-voice,
  5. restamps the script stage so the edit is a verified output, not a hand edit; the caller reruns plan and every stage after it.

Bounds (all in work/daily/<ep>/refit.json): at most MAX_ROUNDS_PER_LINE=2 rewrites of one line, at most MAX_LINES_PER_EPISODE=6 different lines per episode, no refit when the day's token
budget has under MIN_TOKENS_LEFT left or the 4 h machine cap has under MIN_MACHINE_LEFT_S left (those are the same caps every other stage obeys; nothing is loosened). A rewrite that does
not apply cleanly (the plan or the script fails its checks) is rolled back byte for byte.

    uv run tools/daily.py refit --ep E05 [--line H01] [--dry]     refit the lines the plan stage rejects, then run the stages again
"""
from __future__ import annotations

import datetime as dt
import json
import re
import shutil
from pathlib import Path

import line_fit

MAX_ROUNDS_PER_LINE = 2          # H01 -> H01r1 -> H01r2, never a third
MAX_LINES_PER_EPISODE = 6
MAX_FAILED_ROUNDS = 3            # rewrites that did not apply cleanly (per episode)
MIN_TOKENS_LEFT = 60_000
MIN_MACHINE_LEFT_S = 900
ASKS_PER_LINE = 2                # the writer is asked at most twice per line per round (the second time with the failed check named)
PLAN_REF_KEYS = ("line",)        # keys whose value is a line id: scenes[].line, intros[].line, hook.line, written.line, choice.line
CHOICE_ROLES = ("question", "choice1", "choice2", "hook")

REFIT_PROMPT = """You are the Story-Wrap line-fitter. ONE spoken line of episode {ep} is too long for the slot it plays in, and a voiced line is never re-voiced, so you reword ONLY this line, shorter, as a NEW line.

The line (id {lid}, speaker {speaker}, emotion {emotion}):
  text (the caption, NO tashkeel):      {text}
  tts_text (the same letters WITH full tashkeel): {tts_text}
  direction for the voice: {direction}
It was voiced at {seconds:.2f} s. Its slot is the {slot} ({ref}) and takes at most {max_s:.2f} s of speech. The new line must be about {target_s:.1f} s aloud: AT MOST {max_letters} Arabic letters in tts_text (not counting the vowel marks), about {max_words} words.

Context (do not change it): {context}
{why}
Rules: keep the same speaker, the same idea and the same register (a character sounds like their bible/series/{series}/characters/<id>/voice.md; the narrator is second person plural «أنتم», present tense); do not add facts; no AI slop; no numbers that were not in the line.
text has NO tashkeel; tts_text has the same letters with full tashkeel; the letters of the two must be identical. An own-language word keeps its meaning: keep it only if it still appears, written exactly as in text.
{retry}
Write ONE file, {out}, with only this JSON object and nothing else: {{"text": "...", "tts_text": "...", "foreign": [{{"word": "...", "language": "...", "meaning_ar": "..."}}]}} ("foreign" only for own-language words that remain; otherwise []).
Edit no other file. Reply with the file path."""


# ------------------------------------------------------------------ ids
def base_id(lid: str) -> str:
    return re.sub(r"r\d+$", "", lid)


def round_of(lid: str) -> int:
    m = re.search(r"r(\d+)$", lid)
    return int(m.group(1)) if m else 0


def next_id(lid: str) -> str:
    return f"{base_id(lid)}r{round_of(lid) + 1}"


# ------------------------------------------------------------------ the record (work/daily/<ep>/refit.json)
def record_path(root: Path, ep: str) -> Path:
    return Path(root) / "work" / "daily" / ep / "refit.json"


def load_record(root: Path, ep: str) -> dict:
    try:
        r = json.loads(record_path(root, ep).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        r = {}
    r.setdefault("lines", {})            # base id -> {"rounds": n, "chain": [ids]}
    r.setdefault("events", [])
    r.setdefault("failed_rounds", 0)
    r.setdefault("exhausted", None)      # {"reason", "date"} once the cure had to give up
    return r


def save_record(root: Path, ep: str, rec: dict) -> None:
    p = record_path(root, ep)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def refit_possible(root: Path, ep: str, today: str | None = None) -> bool:
    """Pure file read for the autopilot: may a PLAN-DURATION stop of this episode still be cured? False once the cure gave up for good (rounds, lines, failures)
    or for today (budget, cap)."""
    ex = load_record(root, ep).get("exhausted")
    if not ex:
        return True
    if ex.get("reason") in ("budget", "cap"):
        return ex.get("date") != (today or dt.date.today().isoformat())
    return False


def _give_up(ctx, rec: dict, reason: str, why: str):
    rec["exhausted"] = {"reason": reason, "date": dt.date.today().isoformat(), "why": why[:200]}
    rec["events"].append({"at": dt.datetime.now().isoformat(timespec="seconds"), "event": "gave-up", "reason": reason, "why": why[:200]})
    save_record(ctx.root, ctx.ep, rec)
    ctx.log(f"[refit] not possible: {why}")
    return False


# ------------------------------------------------------------------ editing the writer's files
def replace_line_id(plan: dict, old: str, new: str) -> int:
    """Point every use of line `old` in calm-plan.json at `new`: scenes[].line, intros[].line, hook.line, written.line, choice.line, choice.lines.*. -> how many were changed."""
    n = 0

    def fix(d: dict, key: str):
        nonlocal n
        if d.get(key) == old:
            d[key] = new
            n += 1
    for s in plan.get("scenes", []):
        fix(s, "line")
    for ix in plan.get("intros", []) or []:
        fix(ix, "line")
    for k in ("hook", "written", "choice"):
        if isinstance(plan.get(k), dict):
            fix(plan[k], "line")
    for role, v in list(((plan.get("choice") or {}).get("lines") or {}).items()):
        if v == old:
            plan["choice"]["lines"][role] = new
            n += 1
    return n


def apply_rewrite(script: dict, plan: dict, old: str, new: str, cand: dict, info: dict) -> None:
    """script.json: the old line is replaced IN PLACE (order is kept) by a copy with the new id, text, tts_text and foreign tags; calm-plan.json is pointed at the new id."""
    for i, ln in enumerate(script["lines"]):
        if ln["id"] == old:
            nl = dict(ln)
            nl.update({"id": new, "text": cand["text"], "tts_text": cand["tts_text"]})
            if cand.get("foreign"):
                nl["foreign"] = cand["foreign"]
            else:
                nl.pop("foreign", None)
            nl["refit"] = info
            script["lines"][i] = nl
            break
    else:
        raise KeyError(old)
    if replace_line_id(plan, old, new) == 0:
        raise KeyError(f"the plan does not use {old}")


def candidate_problems(cand: dict) -> list[str]:
    """Mechanical checks of the writer's rewrite (before anything is written to the episode files)."""
    from arabic_display import has_tashkeel
    bad = []
    t, tts = str(cand.get("text", "")).strip(), str(cand.get("tts_text", "")).strip()
    if not t or not tts:
        return ["text or tts_text is empty"]
    if has_tashkeel(t):
        bad.append("text carries tashkeel (it is the caption: none)")
    if not has_tashkeel(tts):
        bad.append("tts_text has no tashkeel (the voice text carries full vowels)")
    if "".join(line_fit.AR_LETTER.findall(t)) != "".join(line_fit.AR_LETTER.findall(tts)):
        bad.append("text and tts_text have different letters")
    return bad


def context_of(plan: dict, script: dict, lid: str) -> str:
    lines = script["lines"]
    i = next(k for k, l in enumerate(lines) if l["id"] == lid)
    sc = next((s for s in plan.get("scenes", []) if s.get("line") == lid), None)
    bits = []
    if i > 0:
        bits.append(f"the line before ({lines[i - 1]['speaker']}): {lines[i - 1]['text']}")
    if i + 1 < len(lines):
        bits.append(f"the line after ({lines[i + 1]['speaker']}): {lines[i + 1]['text']}")
    if sc:
        ev = sc.get("event") or (sc.get("params") or {}).get("cause") or ""
        if ev:
            bits.append(f"what the scene shows: {str(ev)[:240]}")
    if lid == (plan.get("hook") or {}).get("line"):
        bits.append("this is the spoken recap hook: the first sound of the episode; the card behind it says the vote result: " + json.dumps(plan.get("recap") or {}, ensure_ascii=False))
    return " | ".join(bits) or "(none)"


# ------------------------------------------------------------------ the cure
def measured_seconds(ctx, script: dict) -> dict:
    import calm_compose as cc
    out = {}
    for l in script["lines"]:
        p = ctx.root / "work" / "voice" / ctx.ep / f"{l['id']}.trimmed.wav"
        if p.is_file():
            out[l["id"]] = cc.wav_seconds(p)
    return out


def find_overruns(ctx, message: str = "", only: str | None = None) -> list[dict]:
    ed = ctx.ep_dir
    plan, script = json.loads((ed / "calm-plan.json").read_text(encoding="utf-8")), json.loads((ed / "script.json").read_text(encoding="utf-8"))
    items = line_fit.overruns(plan, measured_seconds(ctx, script), message)
    return [i for i in items if not only or i["line"] == only]


def ask_writer(ctx, plan: dict, script: dict, item: dict, rec: dict) -> dict | None:
    """One line's rewrite from the writer (at most ASKS_PER_LINE calls). -> the candidate {text, tts_text, foreign} that fits best, or None."""
    ln = next(l for l in script["lines"] if l["id"] == item["line"])
    tgt = line_fit.rewrite_target(item, ln.get("speaker"))
    nid = next_id(item["line"])
    out = ctx.dir / "refit" / f"{nid}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    best, retry, best_est = None, "", 1e9
    for k in range(ASKS_PER_LINE):
        if out.exists():
            out.unlink()
        prompt = REFIT_PROMPT.format(ep=ctx.ep, lid=ln["id"], speaker=ln.get("speaker"), emotion=ln.get("emotion", "calm"), text=ln["text"], tts_text=ln["tts_text"], direction=str(ln.get("direction", ""))[:300],
                                     seconds=item["seconds"], slot=item["slot"], ref=item["ref"], max_s=item["max_s"], target_s=tgt["target_s"], max_letters=tgt["max_letters"],
                                     max_words=max(2, tgt["max_letters"] // 4), context=context_of(plan, script, ln["id"]), why=("Why: " + item["why"]) if item.get("why") else "",
                                     series=script.get("series", ""), retry=retry, out=out.as_posix())
        r = ctx.llm(prompt, name=f"refit-{ctx.ep}-{nid}-{k}", tools="Read(./bible/**),Read(./work/daily/**),Write", expect=[out], write_allow="work/daily/**", timeout=900)
        rec["tokens"] = int(rec.get("tokens", 0)) + int(r.get("tokens") or 0)
        if r.get("rc") != 0 or not out.is_file():
            retry = "A previous attempt wrote no usable file. Write the JSON file."
            continue
        try:
            cand = json.loads(out.read_text(encoding="utf-8"))
        except ValueError:
            retry = "Your last file was not valid JSON."
            continue
        bad = candidate_problems(cand)
        probe = {**ln, "text": cand.get("text", ""), "tts_text": cand.get("tts_text", "")}
        if not bad and line_fit.letters(probe["tts_text"]) > 0:
            est = line_fit.estimate_s(probe)
            why = line_fit.new_line_ok(probe, item)
            if best is None or est < best_est:
                best, best_est = cand, est
            if why is None:
                return best
            retry = f"Your last attempt ({line_fit.letters(probe['tts_text'])} letters) was too long: {why}. Make it clearly shorter: at most {tgt['max_letters']} letters."
        else:
            retry = "Your last attempt failed: " + "; ".join(bad or ["empty"]) + "."
    return best


def cure(ctx, error=None, *, only: str | None = None, items: list[dict] | None = None) -> bool:
    """Refit every line whose take overruns its slot. True = the episode files and the voice are updated and the caller reruns plan; False = nothing to do or the cure
    must stop (recorded in refit.json). `items` = forced overrun items from tools/cap_heal.py (a caption with no place on screen); the same bounds apply. Raises StageFail only from the voice stage it runs (the same codes the voice stage always raises)."""
    import daily
    import voice
    rec = load_record(ctx.root, ctx.ep)
    ed = ctx.ep_dir
    try:
        items = list(items) if items is not None else find_overruns(ctx, getattr(error, "msg", "") or "", only)      # `items`: the caption heal (R-506) asks for a shorter line that is not over its slot
    except (OSError, ValueError, KeyError, StopIteration) as e:
        return _give_up(ctx, rec, "files", f"cannot read the episode files: {e}")
    if not items:
        ctx.log("[refit] no take is over its slot: nothing to refit")
        return False
    if rec["failed_rounds"] >= MAX_FAILED_ROUNDS:
        return _give_up(ctx, rec, "failed", f"{rec['failed_rounds']} refit rounds did not apply cleanly")
    todo = []
    for it in items:
        base = base_id(it["line"])
        row = rec["lines"].get(base, {"rounds": 0, "chain": [base]})
        if row["rounds"] >= MAX_ROUNDS_PER_LINE:
            return _give_up(ctx, rec, "rounds", f"line {base} was already reworded {row['rounds']} times ({' -> '.join(row['chain'])}) and still does not fit")
        if base not in rec["lines"] and len(rec["lines"]) >= MAX_LINES_PER_EPISODE:
            return _give_up(ctx, rec, "lines", f"more than {MAX_LINES_PER_EPISODE} lines of {ctx.ep} do not fit their slots: the script needs the writer")
        todo.append(it)
    if ctx.budget.left < MIN_TOKENS_LEFT:
        return _give_up(ctx, rec, "budget", f"{ctx.budget.left} tokens left today (need {MIN_TOKENS_LEFT})")
    if ctx.remaining() < MIN_MACHINE_LEFT_S:
        return _give_up(ctx, rec, "cap", f"{ctx.remaining():.0f} s of machine time left (need {MIN_MACHINE_LEFT_S})")
    plan_p, script_p = ed / "calm-plan.json", ed / "script.json"
    plan, script = json.loads(plan_p.read_text(encoding="utf-8")), json.loads(script_p.read_text(encoding="utf-8"))
    cands = {}
    for it in todo:
        c = ask_writer(ctx, plan, script, it, rec)
        if c is None:
            rec["failed_rounds"] += 1
            save_record(ctx.root, ctx.ep, rec)
            return _give_up(ctx, rec, "writer", f"the writer returned no usable rewrite for {it['line']}") if rec["failed_rounds"] >= MAX_FAILED_ROUNDS else False
        cands[it["line"]] = c
    bk = ctx.dir / "refit" / f"backup-{dt.datetime.now():%H%M%S}"
    bk.mkdir(parents=True, exist_ok=True)
    for p in (plan_p, script_p):
        shutil.copy2(p, bk / p.name)
    applied = []
    try:
        for it in todo:
            old, new = it["line"], next_id(it["line"])
            apply_rewrite(script, plan, old, new, cands[old], {"of": old, "round": round_of(new), "was_s": it["seconds"], "cap_s": it["max_s"], "slot": it["slot"], "at": dt.datetime.now().isoformat(timespec="seconds")})
            applied.append((old, new))
        for p, d in ((script_p, script), (plan_p, plan)):
            p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        bad = [b for b in daily.validate_episode_files(ctx) if not b.startswith("PLAN-DURATION")]
    except KeyError as e:
        bad = [f"REFIT-APPLY {e}"]
    if bad:
        for p in (plan_p, script_p):       # rolled back byte for byte: a bad rewrite never reaches the voice stage
            shutil.copy2(bk / p.name, p)
        rec["failed_rounds"] += 1
        rec["events"].append({"at": dt.datetime.now().isoformat(timespec="seconds"), "event": "rolled-back", "why": "; ".join(bad[:3])[:300]})
        save_record(ctx.root, ctx.ep, rec)
        ctx.log("[refit] the rewrite broke the episode checks and was rolled back: " + "; ".join(bad[:2]))
        return False
    paths = voice.episode_paths(ed, repo=ctx.root)
    for old, new in applied:
        voice.cmd_refit_mark(paths, old, new, f"{ctx.ep} {old}: take over its slot (line_refit)")
        base = base_id(old)
        row = rec["lines"].setdefault(base, {"rounds": 0, "chain": [base]})
        row["rounds"] += 1
        row["chain"].append(new)
        rec["events"].append({"at": dt.datetime.now().isoformat(timespec="seconds"), "event": "refit", "old": old, "new": new, "was_s": next(i["seconds"] for i in todo if i["line"] == old),
                              "cap_s": next(i["max_s"] for i in todo if i["line"] == old), "text": cands[old]["text"]})
    rec["exhausted"] = None
    save_record(ctx.root, ctx.ep, rec)
    daily.restamp(ctx, "script")                      # the verified edit of the script stage's own outputs
    ctx.log(f"[refit] reworded {', '.join(f'{o} -> {n}' for o, n in applied)}; voicing the new line(s) once")
    daily.run_stage(ctx, daily.STAGES["voice"], force=True)       # always runs (script.json changed): the marker lets it voice ONLY the new ids, every settled take is skipped
    return True
