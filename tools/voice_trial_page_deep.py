"""Builds the "Narrator round 2: deep and wise" block of previews/index.html (idempotent), ABOVE the round-1 block.

Inputs: work/voice-trial/narrator-deep/{metrics.json,plan.json,ref/dN.provenance.json}. Block lives between
<!--NTRIAL2_BEGIN--> and <!--NTRIAL2_END-->; first run inserts it before <!--NTRIAL_BEGIN-->.
Also relabels round 1 as "Round 1 (rated)" and shows the owner's round-1 ratings (work/voice-trial/ratings-2026-10-26.json).
Usage: python tools/voice_trial_page_deep.py <deep-dir> <ratings.json> [index.html]
"""
import json
import sys
from pathlib import Path

B2, E2 = "<!--NTRIAL2_BEGIN-->", "<!--NTRIAL2_END-->"
B1 = "<!--NTRIAL_BEGIN-->"
R1_OLD = '<h2 id="nt-h">🎙️ Narrator trial: 4 voices, same 5 lines</h2>'
R1_NEW = '<h2 id="nt-h">🎙️ Round 1 (rated): 4 voices, same 5 lines</h2>'
R1_MARK = "<!--NTRIAL_R1RATINGS-->"

CSS = """
.nd{margin:22px 0 28px;padding:18px;border:2px solid var(--ink-acc);border-radius:16px;background:var(--card)}
.nd h2{margin:0 0 4px;font-size:clamp(24px,4vw,34px)}
.nd-lead{color:var(--soft);margin:0 0 12px}
.nd-lines{margin:0 0 14px;padding:12px 14px;border-radius:12px;background:var(--chip);list-style:none}
.nd-lines li{margin:4px 0;font-size:1.05rem}
.nd-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:14px}
@media (max-width:900px){.nd-grid{grid-template-columns:1fr}}
.nd-card{border:1px solid var(--line);border-radius:14px;padding:14px;background:var(--bg)}
.nd-card h3{margin:0 0 4px;font-size:1.2rem}
.nd-ref{color:var(--soft);font-size:.88rem;margin:0 0 6px}
.nd-ref a{color:var(--ink-acc)}
.nd-knobs{margin:6px 0 10px;padding:8px 10px;border-radius:10px;background:var(--chip);font-size:.9rem}
.nd-row{margin:8px 0}
.nd-row b{display:block;margin-bottom:2px}
.nd-row audio,.nd-join audio{width:100%}
.nd-join{margin:10px 0;padding:10px;border-radius:12px;background:var(--okbg)}
.nd-stars{display:flex;gap:6px;margin:10px 0 6px}
.nd-star{min-width:44px;min-height:44px;font-size:1.4rem;border-radius:12px;border:1px solid var(--line);background:var(--chip);color:var(--ink);cursor:pointer}
.nd-star[aria-pressed=true]{background:var(--amber);color:#fff;border-color:var(--amber)}
.nd-star:focus-visible,.nd-copy:focus-visible,.nd-note:focus-visible{outline:3px solid var(--ink-acc);outline-offset:2px}
.nd-note{width:100%;min-height:44px;padding:8px 10px;border-radius:10px;border:1px solid var(--line);background:var(--card);color:var(--ink);font:inherit}
.nd-tab{width:100%;border-collapse:collapse;margin:10px 0;font-size:.92rem}
.nd-tab th,.nd-tab td{text-align:start;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
.nd-wrap{overflow-x:auto}
.nd-copy{min-height:44px;padding:8px 18px;border-radius:12px;border:0;background:var(--ink-acc);color:#fff;cursor:pointer;font:inherit;font-weight:700}
.nd-out{width:100%;min-height:90px;margin-top:8px;font-family:ui-monospace,Consolas,monospace;font-size:.85rem}
.nd-bad{color:var(--bad);font-weight:700}
.nd-r1{margin:6px 0 12px;padding:10px 12px;border-radius:12px;background:var(--chip)}
"""

JS = r"""
(function(){
const KEY = "ntrial2-ratings-v1";
let R = {}; try { R = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(R)); } catch (e) {} };
document.querySelectorAll(".nd-card").forEach(card => {
  const k = card.dataset.voice; const st = card.querySelectorAll(".nd-star"); const note = card.querySelector(".nd-note");
  const paint = () => st.forEach((b, i) => b.setAttribute("aria-pressed", (R[k] && R[k].stars > i) ? "true" : "false"));
  note.value = (R[k] && R[k].note) || ""; paint();
  st.forEach((b, i) => b.addEventListener("click", () => { R[k] = Object.assign({stars: 0, note: ""}, R[k]); R[k].stars = (R[k].stars === i + 1) ? 0 : i + 1; paint(); save(); }));
  note.addEventListener("input", () => { R[k] = Object.assign({stars: 0, note: ""}, R[k]); R[k].note = note.value; save(); });
});
const out = document.getElementById("nd-out");
document.getElementById("nd-copy").addEventListener("click", async () => {
  const j = JSON.stringify({trial: "narrator-deep-2026-10-26", ratings: R}, null, 1);
  out.value = j; out.hidden = false; out.select();
  try { await navigator.clipboard.writeText(j); document.getElementById("nd-copied").textContent = "✅ Copied. Paste it back to Claude."; }
  catch (e) { document.getElementById("nd-copied").textContent = "📋 Select the text below and copy it."; }
});
})();
"""


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def f(v, nd=1, unit=""):
    return "n/a" if v is None else (f"{v:.{nd}f}{unit}" if isinstance(v, float) else f"{v}{unit}")


def hms(stamp):
    return stamp.split(" ")[-1]


def build(metrics, plan, provs):
    base = plan["page_base"]
    vk = list(metrics["voices"])
    pv = {v["id"]: v for v in plan["voices"]}
    h = ['<section class="nd" id="narrator-trial-2" aria-labelledby="nd-h">',
         '<h2 id="nd-h">🎙️ Narrator round 2: deep and wise</h2>',
         f'<p class="nd-lead">👂 the owner asked for a deeper, wiser narrator after round 1. 4 male MSA voices from public-domain LibriVox readings, same engine (Chatterbox), same 5 lines, one take each. Played at one level (-23 LUFS). Made {hms(metrics["generated"])}.</p>',
         '<p class="nd-lead">🧪 How each one was made: a clean public-domain reading (6 to 9 s) became the voice reference; grave settings (low exaggeration, low cfg weight, lower temperature) were fixed once per voice before any take. No ASR, no judge model.</p>',
         '<ol class="nd-lines" dir="rtl" lang="ar">' + "".join(f'<li>{esc(l["text"])}</li>' for l in plan["lines"]) + "</ol>",
         '<div class="nd-grid">']
    for k in vk:
        v = metrics["voices"][k]
        vid = k.split("-")[-1]
        p = provs[vid]
        m = p["measures"]
        st = pv[vid]["settings"]
        h.append(f'<div class="nd-card" data-voice="{k}"><h3>👨 {esc(v["label"])} · {m["f0_median_hz"]} Hz</h3>')
        h.append(f'<p class="nd-ref">🎤 Reference: {esc(p["work"])}, chapter {p["chapter"]}. '
                 f'📎 <a href="{p["source_url"]}" target="_blank" rel="noopener">source</a> · '
                 f'⚖️ <a href="{p["licence_url"]}" target="_blank" rel="noopener">public domain</a> · '
                 f'<a href="{p["download_url"]}" target="_blank" rel="noopener">file</a></p>')
        h.append(f'<p class="nd-ref">📏 Reference clip: pitch {m["f0_median_hz"]} Hz · SNR {m["snr_db"]} dB · floor {m["floor_dbfs"]} dBFS · {m["seconds"]} s · DSP: {esc(p["dsp"])}</p>')
        h.append(f'<div class="nd-knobs">🎛️ Exaggeration {st["exaggeration"]} · cfg weight {st["cfg_weight"]} · temperature {st["temperature"]}</div>')
        if v.get("joined"):
            h.append(f'<div class="nd-join"><b>▶️ All 5 lines joined ({v["joined"]["audio_s"]} s)</b><audio controls preload="none" src="{base}{v["joined"]["play"]}"></audio></div>')
        for ln in v["lines"]:
            if "play" in ln:
                h.append(f'<div class="nd-row"><b>{ln["id"]} · {ln["audio_s"]} s</b><audio controls preload="none" src="{base}{ln["play"]}"></audio></div>')
            else:
                h.append(f'<div class="nd-row nd-bad">{ln["id"]}: failed {esc(ln.get("error", ""))}</div>')
        h.append('<div class="nd-stars" role="group" aria-label="Rating">' + "".join(
            f'<button type="button" class="nd-star" aria-pressed="false" aria-label="{i} star{"s" if i > 1 else ""}">⭐</button>' for i in range(1, 6)) + "</div>")
        h.append('<input class="nd-note" type="text" placeholder="📝 Note: deep, wise, too slow ..." aria-label="Note">')
        h.append("</div>")
    h.append("</div>")
    h.append('<p><button type="button" class="nd-copy" id="nd-copy">📋 Copy ratings</button> <span id="nd-copied"></span></p><textarea class="nd-out" id="nd-out" hidden readonly aria-label="Ratings JSON"></textarea>')
    S = lambda v: v.get("signal") or {}
    rows = [
        ("🎯 Median pitch of the takes (Hz, lower is deeper)", lambda v: f(S(v).get("f0", {}).get("median_hz"))),
        ("〰️ Pitch spread (semitones, lower is steadier)", lambda v: f(S(v).get("f0", {}).get("sd_semitones"), 2)),
        ("🔇 Pause level under the voice (dB)", lambda v: f(S(v).get("pause_rel_db_median"))),
        ("📶 SNR estimate (dB)", lambda v: f(S(v).get("snr_est_db"))),
        ("🏛️ Reverb proxy: 20 dB decay (s)", lambda v: f(S(v).get("reverb_decay20_s"), 2)),
        ("🗣️ Words per second (mean)", lambda v: f(S(v).get("words_per_s_mean"), 2)),
        ("✂️ Clipped samples", lambda v: f(S(v).get("clip_samples"))),
        ("⏱️ Wall time, 5 lines (s)", lambda v: f(v.get("total_wall_s"), 1)),
        ("⏱️ Wall per line (s)", lambda v: " · ".join(f(l["wall_s"], 1) for l in v["lines"])),
        ("⚡ Real-time factor (lower is faster)", lambda v: f(v.get("rtf"), 2)),
        ("🔊 Audio, 5 lines (s)", lambda v: f(v.get("audio_s_total"), 1)),
        ("📢 Loudness, natural (LUFS)", lambda v: f((v.get("joined") or {}).get("lufs"), 1)),
        ("📈 True peak, natural (dBFS)", lambda v: f((v.get("joined") or {}).get("true_peak_dbfs"), 1)),
        ("🎮 VRAM peak over baseline (MiB)", lambda v: f(v.get("vram_peak_mib_over_baseline"))),
        ("🧠 RAM peak, process (MiB)", lambda v: f(v.get("ram_peak_mib"))),
        ("🖥️ CPU, % of 12 threads (cores used)", lambda v: f"{f(v.get('cpu_pct_of_machine'), 1)} % ({f(v.get('cpu_cores_equiv'), 2)})"),
        ("🚫 Failures", lambda v: esc("; ".join(v["failures"])) or "none"),
    ]
    h.append('<h3>📊 Metrics per voice</h3><div class="nd-wrap"><table class="nd-tab"><thead><tr><th></th>' +
             "".join(f'<th>{esc(metrics["voices"][k]["label"])}</th>' for k in vk) + "</tr></thead><tbody>")
    for name, fn in rows:
        h.append(f"<tr><th>{name}</th>" + "".join(f"<td>{fn(metrics['voices'][k])}</td>" for k in vk) + "</tr>")
    h.append("</tbody></table></div>")
    ml = metrics["methods"]["chatterbox"]["load"]
    h.append(f'<p class="nd-lead">⏳ Model load {f(ml["wall_s"], 1)} s (separate from synthesis) · 🎮 load VRAM peak {ml["vram_peak_mib_over_baseline"]} MiB over baseline. 📝 {esc(metrics["method_notes"]["chatterbox"])}</p>')
    h.append('<p class="nd-lead">⚖️ Licence: LibriVox recordings are public domain (<a href="https://librivox.org/pages/public-domain/" target="_blank" rel="noopener">librivox.org/pages/public-domain</a>). The volunteer readers are not named per chapter and nobody is identified. Full records: <code>work/voice-trial/narrator-deep/ref/dN.provenance.json</code>. Raw numbers: <code>work/voice-trial/narrator-deep/metrics.json</code>.</p>')
    h.append("</section>")
    return "\n".join(h)


def r1_line(r1):
    names = {"chatterbox-male": "Chatterbox male", "chatterbox-female": "Chatterbox female", "silma-male": "SILMA male", "silma-female": "SILMA female"}
    parts = [f'{names[k]} {r1[k]["stars"]} ⭐ ({esc(r1[k]["note"])})' for k in names if k in r1]
    return (f'{R1_MARK}<p class="nd-r1">⭐ Your round 1 ratings: ' + " · ".join(parts) +
            f'. ➡️ Decision: {esc(r1.get("decision", ""))}.</p>{R1_MARK}')


def main(argv):
    d = Path(argv[0])
    metrics = json.loads((d / "metrics.json").read_text(encoding="utf-8"))
    plan = json.loads((d / "plan.json").read_text(encoding="utf-8"))
    provs = {v["id"]: json.loads((d / "ref" / f"{v['id']}.provenance.json").read_text(encoding="utf-8")) for v in plan["voices"]}
    r1 = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    page = Path(argv[2] if len(argv) > 2 else Path(__file__).resolve().parents[1] / "previews" / "index.html")
    html = page.read_text(encoding="utf-8")
    if R1_MARK in html:
        a = html.index(R1_MARK)
        b = html.rindex(R1_MARK) + len(R1_MARK)
        html = html[:a] + r1_line(r1) + html[b:]
    else:
        assert html.count(R1_OLD) == 1 or html.count(R1_NEW) == 1, "round-1 heading not found"
        html = html.replace(R1_OLD, R1_NEW)
        html = html.replace(R1_NEW, R1_NEW + "\n" + r1_line(r1), 1)
    block = f"{B2}\n<style>{CSS}</style>\n{build(metrics, plan, provs)}\n<script>{JS}</script>\n{E2}\n"
    if B2 in html:
        a, b = html.index(B2), html.index(E2) + len(E2)
        html = html[:a] + block.rstrip("\n") + html[b:]
    else:
        assert html.count(B1) == 1, "round-1 block marker not found"
        html = html.replace(B1, block + B1)
    page.write_text(html, encoding="utf-8")
    print("page updated", page)


if __name__ == "__main__":
    main(sys.argv[1:])
