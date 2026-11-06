# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "scipy", "soundfile"]
# ///
"""Expander proof on real takes (2026-10-26): the mastering expander (voice_master.stage_denoise) must lower the noise in the true
pauses and leave every word, quiet voiced ending and fricative alone. Re-processes the SAME raw takes as tools/edge_proof.py
(edge cleaner, then the mastering chain), twice: with the old expander (profile `voice.measure.pause` removed) and the new one.
CPU only, no model, no re-voice, raw takes read only.

    uv run tools/expander_proof.py <out-dir> [--judge <judge_dir>] [--voices j03] [--e01c <take_dir> --manifest <manifest.json>]

Per take: the level change the expander made on every frame the cleaner's detector calls a sound of a word (voiced, loud, fricative,
voiced decay; `ending_*`), the noise floor before and after (old measure = median of every quiet frame; new measure = median of the
quiet frames in true pauses), TAKE-QUALITY's pause level (cleaned take, old chain, new chain), VOICE-MASTER, and idempotence (second
pass). Writes <out>/proof.json and <out>/proof.md; never writes over an input.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import edge_proof as EP  # noqa: E402
import voice as V  # noqa: E402
import voice_edges as VE  # noqa: E402
import voice_master as VM  # noqa: E402

ENDING_TOL_DB = 1.0        # the brief: a word ending may change by at most 1 dB through the expander


def ending_change(cap: dict, rate: int, profile: dict) -> dict:
    """Level change (dB, out minus in, 20 ms frames) of the expander over the frames the cleaner's detector calls a sound of a word.
    `quiet` = those that sit more than the expander's own threshold under the loud part, i.e. the ones the old expander reached."""
    inp, out, ref = cap["inp"], cap["out"], cap["ref"]
    M = profile["voice"]["measure"]
    m: dict = {}
    VE.speech_span(ref if ref is not None else inp, rate, _masks=m)
    snd = m["sound"]
    a, b = VM.frame_db(inp, rate, M)[0], VM.frame_db(out, rate, M)[0]
    n = min(len(a), len(b), len(snd))
    sel = snd[:n]
    d = (b[:n] - a[:n])[sel]
    p95 = float(np.percentile(a, 95))
    thr = profile["voice"]["take_chain"]["roles"]["narrator"]["denoise"]["open_below_p95_db"]
    q = ((a[:n] - p95) < -thr)[sel]
    return {"sound_frames": int(sel.sum()), "quiet_sound_frames": int(q.sum()),
            "ending_min_db": round(float(d.min()), 2) if len(d) else 0.0,
            "ending_quiet_min_db": round(float(d[q].min()), 2) if q.any() else 0.0}


def run_one(y, rate, role, profile):
    cap: dict = {}
    orig = VM.stage_denoise

    def wrap(x, r, c, M, ref=None):
        o, i = orig(x, r, c, M, ref)
        cap.update(inp=x.copy(), out=o.copy(), ref=None if ref is None else ref.copy())
        return o, i
    VM.stage_denoise = wrap
    try:
        z, rep = VM.master_take(y, rate, role, profile)
    finally:
        VM.stage_denoise = orig
    zl = [float(v) for v in z]
    tp = V.take_profile(zl, rate)
    idem = VM.idempotence(z, rate, role, profile)
    out = {"noise_all_after": rep["after"].get("noise_all_rel_db") if "noise_all_rel_db" in rep["after"] else rep["after"]["noise_rel_db"],
           "noise_after": rep["after"]["noise_rel_db"], "noise_before": rep["before"]["noise_rel_db"],
           "pause_rel_db": tp["pause_rel_db"], "take_quality": V.take_quality_problems(tp),
           "voice_master": [m for _, m in VM.gate_problems(rep["after"], role, profile)],
           "idempotence": VM.idempotence_problems(idem, profile), "idempotence_d": idem,
           "denoise": rep["stages"].get("denoise", {}), "bypassed": bool(rep["stages"].get("bypass"))}
    if cap:
        out["ending"] = ending_change(cap, rate, profile)
    return out, z


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--judge")
    ap.add_argument("--voices", default="j03")
    ap.add_argument("--e01c")
    ap.add_argument("--manifest")
    ap.add_argument("--pause", help="JSON override of voice.measure.pause for the new run")
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    items = []
    if a.judge:
        items += EP.judge_set(Path(a.judge), a.voices.split(","))
    if a.e01c:
        items += EP.e01c_set(Path(a.e01c), a.manifest)
    P0 = VM.load_profile()
    Pold, Pnew = copy.deepcopy(P0), copy.deepcopy(P0)
    Pold["voice"]["measure"].pop("pause", None)
    if a.pause:
        Pnew["voice"]["measure"]["pause"].update(json.loads(a.pause))
    rows, t0 = [], time.time()
    for label, raw, old, role, text, speaker, ref_sha in items:
        x, sr = V.read_float(raw)
        done = V.edge_done_after_s(text, speaker, ref_sha) if text else None
        y, _ = V.trim_take(x, sr, done)
        y = np.asarray(y, dtype="float64")
        r = {"id": label, "role": role, "pause_rel_cleaned": V.take_profile([float(v) for v in y], sr)["pause_rel_db"]}
        r["old"], _ = run_one(y, sr, role, Pold)
        r["new"], _ = run_one(y, sr, role, Pnew)
        rows.append(r)
        print(json.dumps({"id": label, "end_old": r["old"].get("ending"), "end_new": r["new"].get("ending"),
                          "noise_old": r["old"]["noise_after"], "noise_new": r["new"]["noise_after"]}, ensure_ascii=False), flush=True)
    lim = V.TAKEQ["max_pause_rel_db"]
    fail = lambda r, k: bool(r[k]["take_quality"])
    cleaned_fail = [r["id"] for r in rows if r["pause_rel_cleaned"] is not None and r["pause_rel_cleaned"] > lim]
    summ = {"generated": time.strftime("%Y-%m-%d %H:%M:%S"), "takes": len(rows), "wall_s": round(time.time() - t0, 1),
            "pause_params": Pnew["voice"]["measure"]["pause"],
            "ending_tol_db": ENDING_TOL_DB,
            "ending_quiet_min_db": {k: min((r[k].get("ending") or {}).get("ending_quiet_min_db", 0.0) for r in rows) for k in ("old", "new")},
            "ending_min_db": {k: min((r[k].get("ending") or {}).get("ending_min_db", 0.0) for r in rows) for k in ("old", "new")},
            "takes_with_ending_change_over_tol": {k: [r["id"] for r in rows if abs((r[k].get("ending") or {}).get("ending_min_db", 0.0)) > ENDING_TOL_DB] for k in ("old", "new")},
            "take_quality_fail": {"cleaned_only": cleaned_fail, "old_chain": [r["id"] for r in rows if fail(r, "old")], "new_chain": [r["id"] for r in rows if fail(r, "new")]},
            "take_quality_added_by_new_vs_old": [r["id"] for r in rows if fail(r, "new") and not fail(r, "old")],
            "voice_master_fail": {k: [r["id"] for r in rows if r[k]["voice_master"]] for k in ("old", "new")},
            "idempotence_fail": {k: [r["id"] for r in rows if r[k]["idempotence"]] for k in ("old", "new")},
            "idempotence_added_by_new_vs_old": [r["id"] for r in rows if r["new"]["idempotence"] and not r["old"]["idempotence"]]}
    both = [r for r in rows if r["old"]["noise_all_after"] is not None and r["new"]["noise_all_after"] is not None]
    summ["pause_floor_all_quiet_frames_db"] = {
        "takes_compared": len(both),
        "median_after_old_chain": round(float(np.median([r["old"]["noise_all_after"] for r in both])), 2) if both else None,
        "median_after_new_chain": round(float(np.median([r["new"]["noise_all_after"] for r in both])), 2) if both else None}
    pn = [r for r in rows if r["new"]["noise_after"] is not None and r["new"]["noise_before"] is not None]
    summ["pause_floor_true_pauses_db"] = {
        "takes_measured": len(pn),
        "median_before_chain": round(float(np.median([r["new"]["noise_before"] for r in pn])), 2) if pn else None,
        "median_after_new_chain": round(float(np.median([r["new"]["noise_after"] for r in pn])), 2) if pn else None,
        "takes_lower_after_than_before": sum(1 for r in pn if r["new"]["noise_after"] < r["new"]["noise_before"] - 0.5),
        "takes_higher_after_than_before": sum(1 for r in pn if r["new"]["noise_after"] > r["new"]["noise_before"] + 0.5)}
    (out / "proof.json").write_text(json.dumps({"summary": summ, "takes": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    L = ["# Expander proof", "", f"Generated {summ['generated']} by tools/expander_proof.py (CPU, no model, raw takes read only).", "",
         "old = the expander as it was (every frame 24 dB under the loud part); new = true pauses only (voice.measure.pause).",
         "ending = level change the expander made on frames the cleaner's detector calls a sound of a word (min over the take, dB; quiet = the frames the old expander reached).",
         "noise = median of the quiet frames (all = old measure, pause = true pauses only). TQ = TAKE-QUALITY pause level (limit -24.0).", "",
         "| take | ending old / new dB | ending quiet old / new dB | noise before (pause) | noise after old (all) / new (all) / new (pause) | TQ cleaned / old / new | VOICE-MASTER old / new | idempotence old / new |",
         "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        o, n = r["old"], r["new"]
        eo, en = o.get("ending") or {}, n.get("ending") or {}
        L.append(f"| {r['id']} | {eo.get('ending_min_db', '-')} / {en.get('ending_min_db', '-')} | {eo.get('ending_quiet_min_db', '-')} / {en.get('ending_quiet_min_db', '-')} | "
                 f"{n['noise_before']} | {o['noise_all_after']} / {n['noise_all_after']} / {n['noise_after']} | {r['pause_rel_cleaned']} / {o['pause_rel_db']} / {n['pause_rel_db']} | "
                 f"{'ok' if not o['voice_master'] else 'FAIL'} / {'ok' if not n['voice_master'] else 'FAIL'} | {'ok' if not o['idempotence'] else 'FAIL'} / {'ok' if not n['idempotence'] else 'FAIL'} |")
    L += ["", "## summary", "", "```", json.dumps(summ, ensure_ascii=False, indent=1), "```", ""]
    (out / "proof.md").write_text("\n".join(L), encoding="utf-8")
    print(json.dumps(summ, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
