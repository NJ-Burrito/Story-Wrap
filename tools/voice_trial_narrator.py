"""Narrator voice trial (owner, 2026-10-26): two engines, a male and a female voice each, the same 5 lines.

  run <method> <plan.json>   runs INSIDE the engine venv (torch there). Loads the model once, ONE take per line and
                             voice, measures wall time, VRAM (nvidia-smi sampling), RAM and CPU of this process.
  finalize <plan.json>       system python, stdlib + ffmpeg: trims tails (tools/voice.py trim_take), loudness (LUFS),
                             joined clip per voice, level-matched playback copies, metrics.json (page: tools/voice_trial_page.py).

No re-voice, no ASR, no judge model, no paid API. The plan file lists lines, voices and paths.
Usage: see work/voice-trial/narrator/plan.json.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import threading
import time
import types
from ctypes import wintypes
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def read_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def write_json(p, obj):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


# ------------------------------------------------------------------ process meters (ctypes, no psutil)
class _PMC(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t)]


def proc_mem():
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.GetCurrentProcess.restype = wintypes.HANDLE
    p = _PMC()
    p.cb = ctypes.sizeof(p)
    _ps = ctypes.WinDLL("psapi")
    _ps.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PMC), wintypes.DWORD]
    _ps.GetProcessMemoryInfo(k.GetCurrentProcess(), ctypes.byref(p), p.cb)
    return p.WorkingSetSize, p.PeakWorkingSetSize, p.PagefileUsage, p.PeakPagefileUsage


def cpu_seconds():
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.GetCurrentProcess.restype = wintypes.HANDLE
    k.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    c, e, kt, ut = (wintypes.FILETIME() for _ in range(4))
    k.GetProcessTimes(k.GetCurrentProcess(), ctypes.byref(c), ctypes.byref(e), ctypes.byref(kt), ctypes.byref(ut))
    f = lambda t: ((t.dwHighDateTime << 32) | t.dwLowDateTime) / 1e7
    return f(kt) + f(ut)


def gpu_used_mib():
    out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                         capture_output=True, text=True, timeout=10).stdout.strip().splitlines()
    return int(out[0])


class Meter:
    """Samples device VRAM (nvidia-smi) and this process's working set about 5 times a second; windows via mark()."""

    def __init__(self):
        self.samples = []          # (t, vram_mib, rss_bytes)
        self.stop = False
        self.th = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self.stop:
            try:
                self.samples.append((time.time(), gpu_used_mib(), proc_mem()[0]))
            except Exception:
                pass
            time.sleep(0.05)

    def __enter__(self):
        self.th.start()
        return self

    def __exit__(self, *a):
        self.stop = True
        self.th.join()

    def window(self, t0, t1, base_vram):
        s = [x for x in self.samples if t0 <= x[0] <= t1] or [(t1, base_vram, 0)]
        return {"vram_peak_mib_over_baseline": max(x[1] for x in s) - base_vram,
                "vram_peak_mib_absolute": max(x[1] for x in s),
                "ram_peak_mib": round(max(x[2] for x in s) / 2 ** 20), "samples": len(s)}


def sha8(s):
    return int(hashlib.sha256(s.encode("utf-8")).hexdigest()[:8], 16)


# ------------------------------------------------------------------ run (inside the engine venv)
def run(method, plan_path):
    import torch
    plan = read_json(plan_path)
    out_root = Path(plan["out_dir"])
    voices = [v for v in plan["voices"] if v["method"] == method]
    lines = plan["lines"]
    cores = os.cpu_count() or 1
    result = {"method": method, "cores": cores, "failures": [], "voices": {}, "started": time.strftime("%Y-%m-%d %H:%M:%S")}
    res_path = out_root / f"run-{method}.json"
    base = gpu_used_mib()
    result["vram_baseline_mib"] = base
    with Meter() as meter:
        t_load0 = time.time()
        cpu0 = cpu_seconds()
        if method == "chatterbox":
            import torchaudio as ta
            from chatterbox.mtl_tts import ChatterboxMultilingualTTS
            import voice as V
            m = ChatterboxMultilingualTTS.from_pretrained(device="cuda")
            sr = m.sr
            orig = m.t3.inference
            cap = {"n": 1000}

            def capped(*a, **k):
                k["max_new_tokens"] = cap["n"]
                return orig(*a, **k)
            m.t3.inference = capped
        else:
            for name in ["nemo_text_processing", "nemo_text_processing.text_normalization",
                         "nemo_text_processing.text_normalization.normalize"]:
                sys.modules[name] = types.ModuleType(name)
            sys.modules["nemo_text_processing.text_normalization.normalize"].Normalizer = object
            sys.modules["catt_tashkeel"] = types.ModuleType("catt_tashkeel")
            sys.modules["catt_tashkeel"].CATTEncoderOnly = object
            from silma_tts.api import SilmaTTS
            m = SilmaTTS(enable_normalizer=False, force_tashkeel=False)
            sr = 24000
        torch.cuda.synchronize()
        t_load1 = time.time()
        result["load"] = {"wall_s": round(t_load1 - t_load0, 1), "cpu_s": round(cpu_seconds() - cpu0, 1),
                          **meter.window(t_load0, t_load1, base)}
        write_json(res_path, result)
        for v in voices:
            vdir = out_root / f"{method}-{v['id']}"
            vdir.mkdir(parents=True, exist_ok=True)
            torch.cuda.reset_peak_memory_stats()
            vt0, vc0 = time.time(), cpu_seconds()
            per_line = []
            for ln in lines:
                out = vdir / f"{ln['id']}.raw.wav"
                lt0 = time.time()
                try:
                    seed = sha8(f"{method}-{v['id']}-{ln['id']}")
                    torch.manual_seed(seed)
                    if method == "chatterbox":
                        cap["n"] = V.token_cap(ln["tts_text"])
                        wav = m.generate(ln["tts_text"], audio_prompt_path=v["ref"], **{**V.CHATTERBOX_SETTINGS, **v.get("settings", {})})
                        torch.cuda.synchronize()
                        ta.save(str(out), wav.cpu(), sr)
                    else:
                        m.infer(ref_file=v["ref"], ref_text=v["ref_text"], gen_text=ln["tts_text"], file_wave=str(out),
                                seed=seed, normalize_numbers=False, force_tashkeel=False)
                        torch.cuda.synchronize()
                    per_line.append({"id": ln["id"], "wall_s": round(time.time() - lt0, 2), "seed": seed, "file": out.name})
                except Exception as e:                      # one take only: a failure is recorded, never retried
                    per_line.append({"id": ln["id"], "wall_s": round(time.time() - lt0, 2), "error": f"{type(e).__name__}: {e}"[:400]})
                    result["failures"].append({"voice": v["id"], "line": ln["id"], "error": per_line[-1]["error"]})
            vt1 = time.time()
            wall = vt1 - vt0
            result["voices"][v["id"]] = {
                "lines": per_line, "wall_s": round(wall, 2), "cpu_s": round(cpu_seconds() - vc0, 1),
                "cpu_pct_of_machine": round(100 * (cpu_seconds() - vc0) / wall / cores, 1),
                "cpu_cores_equiv": round((cpu_seconds() - vc0) / wall, 2),
                "torch_max_allocated_mib": round(torch.cuda.max_memory_allocated() / 2 ** 20),
                **meter.window(vt0, vt1, base)}
            write_json(res_path, result)
        result["process_peak_working_set_mib"] = round(proc_mem()[1] / 2 ** 20)
        result["process_peak_commit_mib"] = round(proc_mem()[3] / 2 ** 20)
    result["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    write_json(res_path, result)
    return 1 if result["failures"] else 0


# ------------------------------------------------------------------ finalize (system python)
def ffmpeg_lufs(path):
    r = subprocess.run(["ffmpeg", "-nostats", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    tail = r.stderr.split("Summary:")[-1]
    g = lambda pat: (re.search(pat, tail) or [None, None])[1]
    i, p = g(r"I:\s+(-?[\d.]+) LUFS"), g(r"Peak:\s+(-?[\d.]+) dBFS")
    return (float(i) if i else None), (float(p) if p else None)


def dir_size_mib(p):
    tot = 0
    for root, _, files in os.walk(p):
        for f in files:
            fp = Path(root) / f
            try:
                tot += fp.resolve().stat().st_size if fp.is_symlink() else fp.stat().st_size
            except OSError:
                pass
    return round(tot / 2 ** 20, 1)


def finalize(plan_path):
    import voice as V
    plan = read_json(plan_path)
    root = Path(plan["out_dir"])
    runs = {mt: read_json(root / f"run-{mt}.json") for mt in ("chatterbox", "silma") if (root / f"run-{mt}.json").exists()}
    silence = root / "gap.wav"
    V.write_wav16(silence, [0.0] * int(24000 * 0.7), 24000)
    metrics = {"generated": time.strftime("%Y-%m-%d %H:%M:%S"), "lines": [l["id"] for l in plan["lines"]],
               "method_notes": plan["method_notes"], "voices": {}}
    for v in plan["voices"]:
        run_ = runs.get(v["method"])
        key = f"{v['method']}-{v['id']}"
        rv = ((run_ or {}).get("voices") or {}).get(v["id"])
        entry = {"label": v["label"], "method": v["method"], "sex": v["sex"], "reference": v["reference_note"],
                 "failures": [], "lines": []}
        if not rv:
            entry["failures"].append(v.get("blocked") or "not run")
            metrics["voices"][key] = entry
            continue
        trimmed, durs = [], 0.0
        for pl in rv["lines"]:
            ln = {"id": pl["id"], "wall_s": pl["wall_s"]}
            if "error" in pl:
                ln["error"] = pl["error"]
                entry["failures"].append(f"{pl['id']}: {pl['error']}")
                entry["lines"].append(ln)
                continue
            raw = root / key / pl["file"]
            dst = root / key / f"{pl['id']}.wav"
            x, sr = V.read_float(raw)
            info = V.cmd_trim(raw, dst)
            x2, _ = V.read_float(dst)
            ln.update(file=f"{key}/{pl['id']}.wav", raw_s=round(len(x) / sr, 2), audio_s=round(len(x2) / sr, 2), sr=sr,
                      rtf=round(pl["wall_s"] / (len(x2) / sr), 2), trim=info and {k: info[k] for k in info if isinstance(info[k], (int, float))})
            ln["lufs"], ln["true_peak_dbfs"] = ffmpeg_lufs(dst)
            durs += len(x2) / sr
            trimmed.append(dst)
            entry["lines"].append(ln)
        if trimmed:
            lst = root / key / "join.txt"
            items = []
            for i, t in enumerate(trimmed):
                items += [f"file '{t.as_posix()}'"] + ([f"file '{silence.as_posix()}'"] if i < len(trimmed) - 1 else [])
            lst.write_text("\n".join(items), encoding="utf-8")
            joined = root / key / "joined.wav"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                            "-ar", "24000", "-c:a", "pcm_s16le", str(joined)], check=True)
            jx, jsr = V.read_float(joined)
            entry["joined"] = {"file": f"{key}/joined.wav", "audio_s": round(len(jx) / jsr, 2)}
            entry["joined"]["lufs"], entry["joined"]["true_peak_dbfs"] = ffmpeg_lufs(joined)
            # playback copies at one common level (-23 LUFS of the joined clip, one gain per voice, peak-limited), so the
            # ear compares voices, not loudness; the metrics keep the natural levels above.
            gain = round(-23.0 - entry["joined"]["lufs"], 2)
            entry["play_gain_db"] = gain
            for src_, dst_ in [(t, t.with_name(t.stem + ".lvl.wav")) for t in trimmed] + [(joined, joined.with_name("joined.lvl.wav"))]:
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src_), "-af", f"volume={gain}dB,alimiter=limit=0.89:level=false",
                                "-c:a", "pcm_s16le", str(dst_)], check=True)
            entry["joined"]["play"] = f"{key}/joined.lvl.wav"
            entry["joined"]["play_lufs"], _ = ffmpeg_lufs(root / key / "joined.lvl.wav")
            for ln in entry["lines"]:
                if "file" in ln:
                    ln["play"] = ln["file"].replace(".wav", ".lvl.wav")
        entry.update(total_wall_s=rv["wall_s"], audio_s_total=round(durs, 2), rtf=round(rv["wall_s"] / durs, 2) if durs else None,
                     vram_peak_mib_over_baseline=rv["vram_peak_mib_over_baseline"], vram_peak_mib_absolute=rv["vram_peak_mib_absolute"],
                     torch_max_allocated_mib=rv["torch_max_allocated_mib"], ram_peak_mib=rv["ram_peak_mib"],
                     cpu_pct_of_machine=rv["cpu_pct_of_machine"], cpu_cores_equiv=rv["cpu_cores_equiv"], cpu_s=rv["cpu_s"],
                     sample_rate=24000)
        metrics["voices"][key] = entry
    metrics["methods"] = {}
    for mt, r in runs.items():
        metrics["methods"][mt] = {"load": r["load"], "cores": r["cores"], "vram_baseline_mib": r["vram_baseline_mib"],
                                  "process_peak_working_set_mib": r.get("process_peak_working_set_mib"),
                                  "process_peak_commit_mib": r.get("process_peak_commit_mib"),
                                  "model_disk_mib": {k: dir_size_mib(p) for k, p in plan["model_dirs"][mt].items()},
                                  "failures": r["failures"]}
    outp = Path(plan["metrics_out"]) if plan.get("metrics_out") else root.parent.parent / "metrics.json"
    write_json(outp, metrics)
    print("wrote", outp)
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "run":
        sys.exit(run(a[1], a[2]))
    if a and a[0] == "finalize":
        sys.exit(finalize(a[1]))
    print(__doc__)
