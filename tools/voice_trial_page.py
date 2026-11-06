"""Builds the "Narrator trial" block of previews/index.html from work/voice-trial/metrics.json (idempotent).

Replaces everything between <!--NTRIAL_BEGIN--> and <!--NTRIAL_END--> (inserted above #narrator-voice on first run).
Audio paths are relative to previews/index.html, like the rest of the page: ../work/voice-trial/narrator/audio/...
Usage: python tools/voice_trial_page.py <metrics.json> <plan.json> [index.html]
"""
import json
import sys
from pathlib import Path

BEGIN, END = "<!--NTRIAL_BEGIN-->", "<!--NTRIAL_END-->"
ANCHOR = '<section class="nv" id="narrator-voice"'

CSS = """
.nt{margin:22px 0 28px;padding:18px;border:2px solid var(--ink-acc);border-radius:16px;background:var(--card)}
.nt h2{margin:0 0 4px;font-size:clamp(24px,4vw,34px)}
.nt-lead{color:var(--soft);margin:0 0 12px}
.nt-lines{margin:0 0 14px;padding:12px 14px;border-radius:12px;background:var(--chip);list-style:none}
.nt-lines li{margin:4px 0;font-size:1.05rem}
.nt-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:14px}
@media (max-width:900px){.nt-grid{grid-template-columns:1fr}}
.nt-card{border:1px solid var(--line);border-radius:14px;padding:14px;background:var(--bg)}
.nt-card h3{margin:0 0 4px;font-size:1.2rem}
.nt-ref{color:var(--soft);font-size:.88rem;margin:0 0 10px}
.nt-row{margin:8px 0}
.nt-row b{display:block;margin-bottom:2px}
.nt-row audio,.nt-join audio{width:100%}
.nt-join{margin:10px 0;padding:10px;border-radius:12px;background:var(--okbg)}
.nt-stars{display:flex;gap:6px;margin:10px 0 6px}
.nt-star{min-width:44px;min-height:44px;font-size:1.4rem;border-radius:12px;border:1px solid var(--line);background:var(--chip);color:var(--ink);cursor:pointer}
.nt-star[aria-pressed=true]{background:var(--amber);color:#fff;border-color:var(--amber)}
.nt-star:focus-visible,.nt-copy:focus-visible,.nt-note:focus-visible{outline:3px solid var(--ink-acc);outline-offset:2px}
.nt-note{width:100%;min-height:44px;padding:8px 10px;border-radius:10px;border:1px solid var(--line);background:var(--card);color:var(--ink);font:inherit}
.nt-tab{width:100%;border-collapse:collapse;margin:10px 0;font-size:.92rem}
.nt-tab th,.nt-tab td{text-align:start;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
.nt-wrap{overflow-x:auto}
.nt-copy{min-height:44px;padding:8px 18px;border-radius:12px;border:0;background:var(--ink-acc);color:#fff;font-weight:700;cursor:pointer;font:inherit;font-weight:700}
.nt-out{width:100%;min-height:90px;margin-top:8px;font-family:ui-monospace,Consolas,monospace;font-size:.85rem}
.nt-bad{color:var(--bad);font-weight:700}
"""

JS = r"""
(function(){
const D = JSON.parse(document.getElementById("ntrial-data").textContent);
const KEY = "ntrial-ratings-v1";
let R = {}; try { R = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(R)); } catch (e) {} };
document.querySelectorAll(".nt-card").forEach(card => {
  const k = card.dataset.voice; const st = card.querySelectorAll(".nt-star"); const note = card.querySelector(".nt-note");
  const paint = () => st.forEach((b, i) => b.setAttribute("aria-pressed", (R[k] && R[k].stars > i) ? "true" : "false"));
  note.value = (R[k] && R[k].note) || ""; paint();
  st.forEach((b, i) => b.addEventListener("click", () => { R[k] = Object.assign({stars: 0, note: ""}, R[k]); R[k].stars = (R[k].stars === i + 1) ? 0 : i + 1; paint(); save(); }));
  note.addEventListener("input", () => { R[k] = Object.assign({stars: 0, note: ""}, R[k]); R[k].note = note.value; save(); });
});
const out = document.getElementById("nt-out");
document.getElementById("nt-copy").addEventListener("click", async () => {
  const j = JSON.stringify({trial: "narrator-2026-10-26", ratings: R}, null, 1);
  out.value = j; out.hidden = false; out.select();
  try { await navigator.clipboard.writeText(j); document.getElementById("nt-copied").textContent = "✅ Copied. Paste it back to Claude."; }
  catch (e) { document.getElementById("nt-copied").textContent = "📋 Select the text below and copy it."; }
});
})();
"""


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def f(v, nd=1, unit=""):
    return "n/a" if v is None else (f"{v:.{nd}f}{unit}" if isinstance(v, float) else f"{v}{unit}")


def build(metrics, plan):
    base = plan["page_base"]
    vk = list(metrics["voices"])
    h = ['<section class="nt" id="narrator-trial" aria-labelledby="nt-h">',
         '<h2 id="nt-h">🎙️ Round 1 (rated): 4 voices, same 5 lines</h2>',
         '<p class="nt-lead">👂 Rate by ear, 1 to 5 stars. All clips are played at one level (-23 LUFS) so you hear the voice, not the volume. Natural levels are in the table. One take per line, no retakes.</p>',
         '<p class="nt-lead">🅰️ Chatterbox Multilingual (the engine the cast uses) · 🅱️ SILMA TTS v1 base (F5 family). Same reference clips for both.</p>',
         '<ol class="nt-lines" dir="rtl" lang="ar">' + "".join(f'<li>{esc(l["text"])}</li>' for l in plan["lines"]) + "</ol>",
         '<div class="nt-grid">']
    for k in vk:
        v = metrics["voices"][k]
        icon = "🅰️" if v["method"] == "chatterbox" else "🅱️"
        sex = "👨" if v["sex"] == "male" else "👩"
        h.append(f'<div class="nt-card" data-voice="{k}"><h3>{icon} {sex} {esc(v["label"])}</h3>')
        h.append(f'<p class="nt-ref">🎤 Reference: {esc(v["reference"])}</p>')
        if v.get("joined"):
            h.append(f'<div class="nt-join"><b>▶️ All 5 lines joined ({v["joined"]["audio_s"]} s)</b><audio controls preload="none" src="{base}{v["joined"]["play"]}"></audio></div>')
        for ln, pl in zip(v["lines"], plan["lines"]):
            if "play" in ln:
                h.append(f'<div class="nt-row"><b>{ln["id"]} · {ln["audio_s"]} s</b><audio controls preload="none" src="{base}{ln["play"]}"></audio></div>')
            else:
                h.append(f'<div class="nt-row nt-bad">{ln["id"]}: failed {esc(ln.get("error", ""))}</div>')
        if not v["lines"]:
            h.append(f'<div class="nt-row nt-bad">🚫 Not run: {esc("; ".join(v["failures"]))}</div>')
        h.append('<div class="nt-stars" role="group" aria-label="Rating">' + "".join(
            f'<button type="button" class="nt-star" aria-pressed="false" aria-label="{i} star{"s" if i > 1 else ""}">⭐</button>' for i in range(1, 6)) + "</div>")
        h.append('<input class="nt-note" type="text" placeholder="📝 Note: warm, noisy, too fast ..." aria-label="Note">')
        h.append("</div>")
    h.append("</div>")
    h.append('<p><button type="button" class="nt-copy" id="nt-copy">📋 Copy ratings</button> <span id="nt-copied"></span></p><textarea class="nt-out" id="nt-out" hidden readonly aria-label="Ratings JSON"></textarea>')

    rows = [
        ("⏱️ Wall time, 5 lines (s)", lambda v: f(v.get("total_wall_s"), 1)),
        ("⏱️ Wall per line (s)", lambda v: " · ".join(f(l["wall_s"], 1) for l in v["lines"])),
        ("⚡ Real-time factor (wall / audio, lower is faster)", lambda v: f(v.get("rtf"), 2)),
        ("🔊 Audio, 5 lines (s)", lambda v: f(v.get("audio_s_total"), 1)),
        ("🎚️ Sample rate (Hz)", lambda v: f(v.get("sample_rate"))),
        ("📢 Loudness, natural (LUFS)", lambda v: f((v.get("joined") or {}).get("lufs"), 1)),
        ("📈 True peak, natural (dBFS)", lambda v: f((v.get("joined") or {}).get("true_peak_dbfs"), 1)),
        ("🎮 VRAM peak over baseline (MiB)", lambda v: f(v.get("vram_peak_mib_over_baseline"))),
        ("🧠 RAM peak, process (MiB)", lambda v: f(v.get("ram_peak_mib"))),
        ("🖥️ CPU, % of 12 threads (cores used)", lambda v: f"{f(v.get('cpu_pct_of_machine'), 1)} % ({f(v.get('cpu_cores_equiv'), 2)})"),
        ("🚫 Failures", lambda v: esc("; ".join(v["failures"])) or "none"),
    ]
    h.append('<h3>📊 Metrics per voice</h3><div class="nt-wrap"><table class="nt-tab"><thead><tr><th></th>' +
             "".join(f'<th>{esc(metrics["voices"][k]["label"])}</th>' for k in vk) + "</tr></thead><tbody>")
    for name, fn in rows:
        h.append(f"<tr><th>{name}</th>" + "".join(f"<td>{fn(metrics['voices'][k])}</td>" for k in vk) + "</tr>")
    h.append("</tbody></table></div>")
    ms = metrics["methods"]
    h.append('<h3>📦 Per engine (load, memory, disk)</h3><div class="nt-wrap"><table class="nt-tab"><thead><tr><th></th><th>🅰️ Chatterbox</th><th>🅱️ SILMA</th></tr></thead><tbody>')
    def mrow(name, fn):
        h.append(f"<tr><th>{name}</th>" + "".join(f"<td>{fn(ms[m]) if m in ms else 'not run'}</td>" for m in ("chatterbox", "silma")) + "</tr>")
    mrow("⏳ Load time (s, separate from synthesis)", lambda m: f(m["load"]["wall_s"], 1))
    mrow("🎮 VRAM peak while loading (MiB over baseline)", lambda m: f(m["load"]["vram_peak_mib_over_baseline"]))
    mrow("💾 Model on disk (MiB)", lambda m: esc(" + ".join(f"{k.split('/')[-1]} {v}" for k, v in m["model_disk_mib"].items())))
    mrow("🧠 Process peak working set / commit (MiB)", lambda m: f"{m['process_peak_working_set_mib']} / {m['process_peak_commit_mib']}")
    mrow("🧮 Other GPU use before the run (MiB)", lambda m: f(m["vram_baseline_mib"]))
    mrow("🚫 Failures", lambda m: str(len(m["failures"])) + " failed")
    h.append("</tbody></table></div>")
    h.append('<p class="nt-lead">📝 ' + esc(ms.get("chatterbox") and metrics["method_notes"]["chatterbox"]) + '</p>')
    h.append('<p class="nt-lead">📝 ' + esc(metrics["method_notes"]["silma"]) + '</p>')
    h.append('<p class="nt-lead">📄 Raw numbers: <code>work/voice-trial/metrics.json</code>. Rated 1 to 5 stars here, saved in this browser.</p>')
    h.append(f'<script type="application/json" id="ntrial-data">{json.dumps({"keys": vk}, ensure_ascii=False)}</script>')
    h.append("</section>")
    return "\n".join(h)


def main(argv):
    metrics = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    plan = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    page = Path(argv[2] if len(argv) > 2 else Path(__file__).resolve().parents[1] / "previews" / "index.html")
    html = page.read_text(encoding="utf-8")
    block = f"{BEGIN}\n<style>{CSS}</style>\n{build(metrics, plan)}\n<script>{JS}</script>\n{END}\n"
    if BEGIN in html:
        a, b = html.index(BEGIN), html.index(END) + len(END)
        html = html[:a] + block.rstrip("\n") + html[b:]
    else:
        assert html.count(ANCHOR) == 1, "anchor not found"
        html = html.replace(ANCHOR, block + ANCHOR)
    page.write_text(html, encoding="utf-8")
    print("page updated", page)


if __name__ == "__main__":
    main(sys.argv[1:])
