# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "scipy", "librosa", "soundfile"]
# ///
"""Edge-noise proof on real takes (2026-10-26): re-process RAW takes through the new take path (voice.trim_take with the
word-safe edge cleaner, then the mastering chain) into an output folder and compare with the files the old path made.
CPU only, no model, no re-voice (the raw takes are read, never written).

    uv run tools/edge_proof.py <out-dir> [--judge <judge_dir>] [--voices j03] [--e01c <take_dir> --manifest <manifest.json>]

Per take: noise-only lead-in / tail before and after (two measures: voice_edges' own, and the judge's independent librosa
pyin measure, tools/voice_judge.noise_edges), speech span on the raw take and on the new file (must agree within
SPAN_TOL_MS), pyin-voiced frames of the raw take that fall outside what the cleaner kept (must be 0 unless the frame is
far from the speaker's pitch), and the take gates on the new file (VOICE-EDGE-NOISE, VOICE-TAIL, TAKE-QUALITY, VOICE-MASTER).
Writes <out>/<set>/<id>.wav, <out>/proof.json and <out>/proof.md.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import voice as V  # noqa: E402
import voice_edges as VE  # noqa: E402
import voice_master as VM  # noqa: E402

SPAN_TOL_MS = 10


def pyin_edges(x, sr):
    import voice_judge as J
    f = J.f0_ext(x, sr)
    f0 = f.pop("_f0")
    return J.noise_edges(x, sr, f0), f0


def old_rep_exists(old):
    return Path(str(old)[:-4] + ".master.json").exists()


def master_noise(rep):
    b, a = rep.get("before") or {}, rep.get("after") or {}
    return b.get("noise_rel_db"), a.get("noise_rel_db")


def one(label, raw, old, role, text, speaker, ref_sha, out_dir):
    x, sr = V.read_float(raw)
    xa = np.asarray(x, dtype="float64")
    done = V.edge_done_after_s(text, speaker, ref_sha) if text else None
    dst = out_dir / f"{label}.wav"
    info = V.cmd_trim(raw, dst, role=role, done_after_s=done)
    y, _ = V.read_float(dst)
    ya = np.asarray(y, dtype="float64")
    o, _ = V.read_float(old)
    oa = np.asarray(o, dtype="float64")
    span_raw = VE.speech_span(xa, sr, done_after_s=done)
    span_new = VE.speech_span(ya, sr)
    y0, _ = V.trim_take(x, sr, done)                 # the cleaner alone (no mastering chain): what the cleaner itself did to the span
    body, crec = VE.clean(xa, sr, done_after_s=done)
    on, off = int(round(crec["span"]["onset_s"] * sr)), int(round(crec["span"]["offset_s"] * sr))
    identical = bool(np.array_equal(body[on - crec["start"]:off - crec["start"]], xa[on:off]))   # every sample of the span, untouched
    y0a = np.asarray(y0, dtype="float64")
    span_clean = VE.speech_span(y0a, sr)
    pj_clean, _ = pyin_edges(y0a, sr)
    ne_old, ne_new = VE.noise_edges(oa, sr), VE.noise_edges(ya, sr)
    pj_old, _ = pyin_edges(oa, sr)
    pj_new, _ = pyin_edges(ya, sr)
    _, f0raw = pyin_edges(xa, sr)
    hop = 160 / 16000                                   # f0_ext's hop
    s0, s1 = info["start"] / sr, info["end"] / sr
    med = float(np.nanmedian(f0raw)) if np.any(~np.isnan(f0raw)) else 0.0
    outside = [(i * hop, float(f0raw[i])) for i in range(len(f0raw)) if not np.isnan(f0raw[i]) and not (s0 <= i * hop <= s1)]
    near = [t for t, f in outside if med and abs(12 * np.log2(f / med)) <= 8.0]
    def take_gates(z, zl):
        return [f"VOICE-EDGE-NOISE: {m}" for m in V.edge_noise_problems(z, sr)] + \
               [f"TAKE-QUALITY: {m}" for m in V.take_quality_problems(V.take_profile(zl, sr))]
    gates_before = take_gates(oa, o)
    gates_cleaned = take_gates(y0a, y0)                  # the cleaner alone, unmastered: like for like with an unmastered old take (E01C)
    gates = [f"VOICE-EDGE-NOISE: {m}" for m in V.edge_noise_problems(ya, sr)] + \
            [f"{c}: {m}" for c, m in V.tail_problems(ya, sr, info)] + \
            [f"TAKE-QUALITY: {m}" for m in V.take_quality_problems(V.take_profile(y, sr))] + \
            [f"{c}: {m}" for c, m in VM.gate_problems(VM.measure(ya, sr), role)] + \
            [f"VOICE-MASTER: {m}" for m in (info.get("master") or {}).get("contract", [])]
    old_rep = Path(str(old)[:-4] + ".master.json")
    mb, ma = master_noise(json.loads(old_rep.read_text(encoding="utf-8"))) if old_rep.exists() else (None, None)
    return {"id": label, "raw": str(raw), "old": str(old), "new": str(dst), "role": role, "speaker": speaker,
            "done_after_s": None if done is None else round(done, 2), "raw_s": round(len(xa) / sr, 2),
            "old_s": round(len(oa) / sr, 2), "new_s": round(len(ya) / sr, 2),
            "before": {"lead_noise_ms": ne_old["lead_noise_ms"], "tail_noise_ms": ne_old["tail_noise_ms"],
                       "pyin_lead_noise_s": pj_old.get("lead_noise_s"), "pyin_tail_noise_s": pj_old.get("tail_noise_s"),
                       "span_s": ne_old["span_s"]},
            "after": {"lead_noise_ms": ne_new["lead_noise_ms"], "tail_noise_ms": ne_new["tail_noise_ms"],
                      "pyin_lead_noise_s": pj_new.get("lead_noise_s"), "pyin_tail_noise_s": pj_new.get("tail_noise_s"),
                      "span_s": ne_new["span_s"]},
            "span_raw_s": span_raw["span_s"], "span_new_s": span_new["span_s"], "span_clean_only_s": span_clean["span_s"],
            "span_delta_ms": round((span_clean["span_s"] - span_raw["span_s"]) * 1000),
            "span_delta_mastered_ms": round((span_new["span_s"] - span_raw["span_s"]) * 1000),
            "pyin_clean_only": {"lead_noise_s": pj_clean.get("lead_noise_s"), "tail_noise_s": pj_clean.get("tail_noise_s")},
            "gates_before": gates_before, "gates_cleaned_only": gates_cleaned, "span_samples_identical": identical,
            "old_was_mastered": old_rep_exists(old),
            "cut_lead_ms": info["cut_start_ms"], "cut_tail_ms": info["cut_end_ms"], "runon_runs": info["edge"]["runon_runs"],
            "pyin_voiced_removed_frames": len(outside), "pyin_voiced_removed_near_pitch_s": [round(t, 2) for t in near[:20]],
            "old_master_noise_rel_db": {"before_chain": mb, "after_chain": ma}, "gates_after": gates}


def judge_set(judge, voices):
    plan = json.loads((judge / "plan.json").read_text(encoding="utf-8"))
    texts = {l["id"]: l["tts_text"] for l in plan["lines"]}
    out = []
    for vid in voices:
        d = Path(plan["out_dir"]) / f"chatterbox-{vid}"
        ref = judge / "refs" / f"{vid}.wav"
        for lid in sorted(texts):
            raw = d / f"{lid}.raw.wav"
            if raw.exists():
                out.append((f"{vid}-{lid}", raw, d / f"{lid}.wav", "narrator", texts[lid], "narrator", V.sha(ref.read_bytes())))
    return out


def e01c_set(take_dir, manifest):
    m = json.loads(Path(manifest).read_text(encoding="utf-8"))
    spk = {l["id"]: l.get("speaker") for l in m["lines"]}
    txt = {l["id"]: l.get("tts_text") for l in m["lines"]}
    job = take_dir / "worker-job.json"
    if job.exists():
        for l in json.loads(job.read_text(encoding="utf-8"))["lines"]:
            txt[l["id"]] = l["text"]
            spk.setdefault(l["id"], l.get("speaker") or "narrator")
    out = []
    for raw in sorted(take_dir.glob("*.wav")):
        if raw.name.endswith(".trimmed.wav"):
            continue
        lid = raw.stem
        old = take_dir / f"{lid}.trimmed.wav"
        if old.exists():
            sp = spk.get(lid) or "narrator"
            out.append((f"E01C-{lid}", raw, old, VM.role_of(sp), txt.get(lid), sp, None))
    return out


def table(rows):
    L = ["| take | before lead / tail ms | after lead / tail ms | pyin lead s before / cleaned / after | pyin tail s before / cleaned / after | span raw / cleaned / mastered s | delta cleaned / mastered ms | cut lead / tail ms | gates before | gates cleaned only | gates after (mastered) |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        b, a = r["before"], r["after"]
        c = r["pyin_clean_only"]
        L.append(f"| {r['id']} | {b['lead_noise_ms']} / {b['tail_noise_ms']} | {a['lead_noise_ms']} / {a['tail_noise_ms']} | "
                 f"{b['pyin_lead_noise_s']} / {c['lead_noise_s']} / {a['pyin_lead_noise_s']} | {b['pyin_tail_noise_s']} / {c['tail_noise_s']} / {a['pyin_tail_noise_s']} | "
                 f"{r['span_raw_s']} / {r['span_clean_only_s']} / {r['span_new_s']} | {r['span_delta_ms']} / {r['span_delta_mastered_ms']} | "
                 f"{r['cut_lead_ms']} / {r['cut_tail_ms']} | {'PASS' if not r['gates_before'] else '; '.join(r['gates_before'])} | {'PASS' if not r['gates_cleaned_only'] else '; '.join(r['gates_cleaned_only'])} | {'PASS' if not r['gates_after'] else '; '.join(r['gates_after'])} |")
    return "\n".join(L)


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--judge")
    ap.add_argument("--voices", default="j03")
    ap.add_argument("--e01c")
    ap.add_argument("--manifest")
    a = ap.parse_args(argv)
    out = Path(a.out)
    sets = {}
    if a.judge:
        sets["judge"] = judge_set(Path(a.judge), a.voices.split(","))
    if a.e01c:
        sets["E01C"] = e01c_set(Path(a.e01c), a.manifest)
    rows, t0 = {}, time.time()
    for name, items in sets.items():
        d = out / name
        d.mkdir(parents=True, exist_ok=True)
        rows[name] = []
        for label, raw, old, role, text, speaker, ref_sha in items:
            if Path(raw).resolve().parent == d.resolve():
                raise SystemExit("refused: the output folder holds the raw takes")
            r = one(label, raw, old, role, text, speaker, ref_sha, d)
            rows[name].append(r)
            print(json.dumps({k: r[k] for k in ("id", "before", "after", "span_delta_ms", "gates_after")}, ensure_ascii=False))
    allr = [r for v in rows.values() for r in v]
    summ = {"generated": time.strftime("%Y-%m-%d %H:%M:%S"), "takes": len(allr), "wall_s": round(time.time() - t0, 1),
            "span_tol_ms": SPAN_TOL_MS, "span_within_tol_cleaned": sum(1 for r in allr if abs(r["span_delta_ms"]) <= SPAN_TOL_MS),
            "span_within_tol_mastered": sum(1 for r in allr if abs(r["span_delta_mastered_ms"]) <= SPAN_TOL_MS),
            "span_delta_ms_max_abs": {"cleaned": max(abs(r["span_delta_ms"]) for r in allr), "mastered": max(abs(r["span_delta_mastered_ms"]) for r in allr)},
            "take_quality_fail_before": sum(1 for r in allr if any(g.startswith("TAKE-QUALITY") for g in r["gates_before"])),
            "take_quality_fail_after": sum(1 for r in allr if any(g.startswith("TAKE-QUALITY") for g in r["gates_after"])),
            "take_quality_fail_cleaned_only": sum(1 for r in allr if any(g.startswith("TAKE-QUALITY") for g in r["gates_cleaned_only"])),
            "like_for_like": "judge takes: old file = old trim + mastering chain, compare with gates_after; E01C: old file = old trim, unmastered, compare with gates_cleaned_only",
            "edge_gate_pass_after": sum(1 for r in allr if not any(g.startswith("VOICE-EDGE-NOISE") for g in r["gates_after"])),
            "edge_gate_fail_before": sum(1 for r in allr if r["before"]["lead_noise_ms"] > VE.check_limits()["max_lead_ms"] or r["before"]["tail_noise_ms"] > VE.check_limits()["max_tail_ms"]),
            "all_gates_pass_after": sum(1 for r in allr if not r["gates_after"]),
            "tail_noise_ms_total": {"before": sum(r["before"]["tail_noise_ms"] for r in allr), "after": sum(r["after"]["tail_noise_ms"] for r in allr)},
            "lead_noise_ms_total": {"before": sum(r["before"]["lead_noise_ms"] for r in allr), "after": sum(r["after"]["lead_noise_ms"] for r in allr)},
            "pyin_tail_noise_s_total": {"before": round(sum(r["before"]["pyin_tail_noise_s"] or 0 for r in allr), 2), "after": round(sum(r["after"]["pyin_tail_noise_s"] or 0 for r in allr), 2)},
            "pyin_lead_noise_s_total": {"before": round(sum(r["before"]["pyin_lead_noise_s"] or 0 for r in allr), 2), "cleaned": round(sum(r["pyin_clean_only"]["lead_noise_s"] or 0 for r in allr), 2), "after": round(sum(r["after"]["pyin_lead_noise_s"] or 0 for r in allr), 2)},
            "pyin_tail_noise_s_total_cleaned": round(sum(r["pyin_clean_only"]["tail_noise_s"] or 0 for r in allr), 2),
            "span_samples_identical": sum(1 for r in allr if r["span_samples_identical"]),
            "pyin_voiced_near_pitch_removed": sum(len(r["pyin_voiced_removed_near_pitch_s"]) for r in allr),
            "profile": {"take": VE.json.loads(VE.PROFILE_PATH.read_text(encoding="utf-8"))["take"]["edge"], "checks": VE.check_limits()}}
    (out / "proof.json").write_text(json.dumps({"summary": summ, "sets": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    md = ["# Edge-noise proof", "", f"Generated {summ['generated']} by tools/edge_proof.py (CPU, no model, raw takes read only).", "",
          "before = the file the old take path made; after = the same raw take through the new path (edge cleaner + mastering chain).",
          "Noise ms = voice_edges measure beyond the guards; pyin = the judge's independent measure (librosa pyin, allowances 0.12 / 0.25 s).", ""]
    for name, rs in rows.items():
        md += [f"## {name}", "", table(rs), ""]
    md += ["## summary", "", "```", json.dumps({k: v for k, v in summ.items() if k != "profile"}, ensure_ascii=False, indent=1), "```", ""]
    (out / "proof.md").write_text("\n".join(md), encoding="utf-8")
    print(json.dumps({k: v for k, v in summ.items() if k != "profile"}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
