# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Every finished episode gets its OWN tab in previews/index.html (owner, 2026-10-28; R-496).

    uv run tools/preview_tab.py add E03 [--open] [--root DIR]    snapshot the media, write (or replace) the tab, optionally open Edge at it
    uv run tools/preview_tab.py ids                              the tab ids now in the page

Idempotent: a second `add` for the same episode replaces that tab. At most 4 tabs (CLAUDE.md): a fifth archives the page to previews/archive/index-<date>.html
and drops the oldest episode/dated tab (the evergreen tabs castvoices and artbook stay). The media is COPIED to work/preview-snap/<EP>/ so the page keeps working
after work/episodes changes. Missing optional files (cover, vote, gate, critic, post records) just leave their block out. Never raises into a caller: use `safe_add`.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_TABS = 4
PINNED = ("castvoices", "artbook")          # evergreen tabs: never the one dropped
TASHKEEL = re.compile("[ً-ٰٟۖ-ۭـ]")
TABS_RE = re.compile(r"(const TABS = \[\n)(.*?)(\n\];)", re.S)
TAB_LINE = re.compile(r'\{id:\s*"([^"]+)"')
EP_RE = re.compile(r"^[A-Za-z]+\d+[A-Z]?$")


def rj(p: Path, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def clean(s) -> str:
    """HTML-escaped text with no tashkeel (the owner: Arabic people see is unvowelled)."""
    return html.escape(TASHKEEL.sub("", str(s or "")))


def copy_if_changed(src: Path, dst: Path) -> bool:
    if not src.is_file():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not (dst.is_file() and dst.stat().st_size == src.stat().st_size and dst.stat().st_mtime >= src.stat().st_mtime):
        shutil.copy2(src, dst)
    return True


def prev_ep(ep: str) -> str | None:
    m = re.match(r"^([A-Za-z]+)(\d+)", ep)
    if not m or int(m.group(2)) <= 1:
        return None
    return f"{m.group(1)}{int(m.group(2)) - 1:0{len(m.group(2))}d}"


def find_vote(root: Path, ep: str) -> tuple[str, dict] | None:
    """The decision that chose this episode: the nearest lower episode's decision.json (E02 -> E01, falling back to its calm cut E01C)."""
    p = prev_ep(ep)
    if not p:
        return None
    w = root / "work" / "episodes"
    for cand in (p, p + "C"):
        d = rj(w / cand / "decision.json")
        if d:
            return cand, d
    return None


def find_caption(root: Path, ep: str, post: dict) -> str:
    for f in sorted((root / "bible" / "series").glob(f"*/episodes/{ep}/caption.txt")):
        try:
            return f.read_text(encoding="utf-8").strip()
        except OSError:
            pass
    return str(post.get("caption") or "").strip()


def gate_critic(root: Path, ep: str) -> dict:
    w = root / "work" / "episodes" / ep
    g = rj(w / "gate" / "report.json", {}) or {}
    c = rj(w / "heal" / "critic.json", {}) or {}
    st = rj(root / "work" / "daily" / ep / "STATE.json", {}) or {}
    retro = (st.get("stages", {}).get("retro") or {}).get("status")
    checks = g.get("checks") or []
    return {"verdict": g.get("verdict"), "complete": g.get("complete"), "n": len(checks),
            "failed": [x.get("id") for x in checks if x.get("status") == "fail"] + list(g.get("fails") or []),
            "score": c.get("score"), "retro": retro}


def build_panel(root: Path, ep: str, snap_video: bool, snap_cover: bool) -> str:
    w = root / "work" / "episodes" / ep
    eid = ep.lower()
    post, fb, yt = (rj(w / n, {}) or {} for n in ("post.json", "facebook.json", "youtube.json"))
    cap = find_caption(root, ep, post)
    cap_lines = [l for l in cap.splitlines() if l.strip()]
    title = cap_lines[0] if cap_lines else ep
    gc = gate_critic(root, ep)
    snap = f"../work/preview-snap/{ep}"
    out = [f'<!--EP_{ep.upper()}_BEGIN--><section class="panel" id="panel-{eid}" data-tab="{eid}" hidden>', "<main class=\"wrap\">"]
    out.append(f'<p class="hook">🎬 {clean(ep)}: {clean(title)}</p>')
    verdict = "✅ Gates pass" if gc["verdict"] == "PASS" else ("❌ Gates: " + clean(gc["verdict"])) if gc["verdict"] else "⚪ No gate report yet"
    posted = bool(post.get("permalink") or fb.get("permalink") or yt.get("url"))
    out.append(f'<p class="sub">{verdict}' + (f', critic {clean(gc["score"])}/10' if gc["score"] is not None else "") + (" · 📣 posted" if posted else " · ⏳ not posted yet (posts at 19:00)") + "</p>")
    out.append('<div class="mix-grid"><figure class="mix-stage">')
    if snap_video:
        poster = f' poster="{snap}/cover.png"' if snap_cover else ""
        out.append(f'<video src="{snap}/episode.mp4"{poster} controls playsinline preload="metadata" width="1080" height="1920" aria-label="Episode {clean(ep)}"></video>')
    else:
        out.append("<p class=\"sub\">⚠️ No episode.mp4 found for this episode.</p>")
    out.append(f"<figcaption>🎥 The recorded video the gates measured (copy: <code>work/preview-snap/{clean(ep)}/episode.mp4</code>). Tap the speaker for sound.</figcaption></figure>")
    out.append('<div class="mix-side">')
    if cap:
        out.append("<h3>📝 Caption</h3>")
        out.append('<p class="sub" dir="auto">' + "<br>".join(clean(l) for l in cap_lines) + "</p>")
    vote = find_vote(root, ep)
    if vote:
        vep, d = vote
        out.append(f"<h3>🗳 The vote that chose it ({clean(vep)})</h3><ul class=\"chips\">")
        counts = d.get("counts") or {}
        win = d.get("winner")
        if win is None:
            sp = d.get("showrunner_pick")
            win = sp.get("id") if isinstance(sp, dict) else sp
        for c in d.get("choices") or []:
            cid = str(c.get("id"))
            mark = "🏆 " if win is not None and str(win) == cid else ""
            out.append(f'<li class="chip" dir="auto">{mark}{clean(c.get("text_ar"))} <small>{clean(counts.get(cid, 0))}</small></li>')
        out.append("</ul>")
        extra = []
        if d.get("status"):
            extra.append(f"status {clean(d['status'])}")
        if d.get("counted") is not None:
            extra.append(f"{clean(d['counted'])} counted of {clean(d.get('total_comments', '?'))} comments")
        if extra:
            out.append(f'<p class="sub">{" · ".join(extra)}</p>')
    out.append("<h3>🔎 Checks</h3><ul class=\"chips\">")
    out.append(f'<li class="chip">{verdict}' + (f" <small>{gc['n']} checks</small>" if gc["n"] else "") + "</li>")
    if gc["score"] is not None:
        out.append(f'<li class="chip">🎯 Critic <small>{clean(gc["score"])}/10</small></li>')
    if gc["retro"]:
        out.append(f'<li class="chip">🧠 Retro <small>{clean(gc["retro"])}</small></li>')
    for f in gc["failed"][:6]:
        out.append(f'<li class="chip">❌ {clean(f)}</li>')
    out.append("</ul>")
    links = [(lab, u) for lab, u in (("📸 Instagram", post.get("permalink")), ("📘 Facebook", fb.get("permalink")), ("▶️ YouTube", yt.get("url"))) if u]
    out.append("<h3>🔗 Posted</h3>")
    if links:
        out.append('<ul class="chips">' + "".join(f'<li class="chip"><a href="{html.escape(u, quote=True)}" target="_blank" rel="noopener">{lab}</a></li>' for lab, u in links) + "</ul>")
        when = post.get("posted_at")
        if when:
            out.append(f'<p class="sub">🕖 {clean(when)}</p>')
    else:
        out.append('<p class="sub">⏳ Not posted yet. Links appear here after the 19:00 post.</p>')
    out.append("</div></div></main>")
    out.append(f"</section><!--EP_{ep.upper()}_END-->")
    return "\n".join(out)


# ------------------------------------------------------------------ page surgery
def section_span(page: str, tab_id: str) -> tuple[int, int] | None:
    """(start, end) of the panel with data-tab=tab_id, including its BEGIN/END comments when present."""
    m = re.search(r'<section class="panel"[^>]*data-tab="%s"[^>]*>' % re.escape(tab_id), page)
    if not m:
        return None
    start, depth, pos = m.start(), 0, m.start()
    for t in re.finditer(r"<section\b|</section>", page[m.start():]):
        depth += 1 if t.group(0) == "<section" else -1
        if depth == 0:
            pos = m.start() + t.end()
            break
    else:
        return None
    b = re.search(r"<!--[A-Z0-9_]+_BEGIN-->\s*$", page[:start])
    if b:
        start = b.start()
    e = re.match(r"\s*<!--[A-Z0-9_]+_END-->", page[pos:])
    if e:
        pos += e.end()
    return start, pos


def tab_ids(page: str) -> list[str]:
    m = TABS_RE.search(page)
    return TAB_LINE.findall(m.group(2)) if m else []


def tab_lines(page: str) -> list[str]:
    m = TABS_RE.search(page)
    return [l for l in m.group(2).split("\n") if l.strip()] if m else []


def set_tabs(page: str, lines: list[str]) -> str:
    return TABS_RE.sub(lambda m: m.group(1) + "\n".join(lines) + m.group(3), page, count=1)


def archive_page(root: Path, page: str, today: dt.date) -> Path:
    d = root / "previews" / "archive"
    d.mkdir(parents=True, exist_ok=True)
    p, n = d / f"index-{today.isoformat()}.html", 2
    while p.exists():
        p, n = d / f"index-{today.isoformat()}-{n}.html", n + 1
    p.write_text(page, encoding="utf-8")
    return p


def victim_key(tab_id: str) -> tuple:
    """The order tabs are dropped in when the page is full: dated or other tabs first, then episode tabs from the OLDEST episode. Root cause (2026-10-29): the first tab
    in display order was dropped, so a re-added E02 tab survived and the newer E03 tab went to the archive."""
    m = re.match(r"e(\d+)", tab_id)
    return (1, int(m.group(1)), tab_id) if m else (0, 0, tab_id)


def add_tab(root: Path, ep: str, today: dt.date | None = None, only_if_present: bool = False) -> dict:
    """only_if_present: refresh a tab the page already has (the after-post refresh), never re-add one that was archived."""
    root = Path(root)
    today = today or dt.date.today()
    if not EP_RE.match(ep):
        raise ValueError(f"not an episode id: {ep!r}")
    index = root / "previews" / "index.html"
    if not index.is_file():
        raise FileNotFoundError(f"{index} missing")
    page = index.read_text(encoding="utf-8")
    if not TABS_RE.search(page):
        raise ValueError("const TABS = [ ... ]; not found in the page")
    if only_if_present and ep.lower() not in tab_ids(page):
        return {"ep": ep, "id": ep.lower(), "tabs": tab_ids(page), "archived": None, "dropped": None, "video": False, "skipped": "no tab on the page"}
    w = root / "work" / "episodes" / ep
    snap = root / "work" / "preview-snap" / ep
    has_v = copy_if_changed(w / "episode.mp4", snap / "episode.mp4")
    has_c = copy_if_changed(w / "cover.png", snap / "cover.png")
    eid = ep.lower()
    new_panel = build_panel(root, ep, has_v, has_c)
    new_line = f'  {{id: "{eid}", emoji: "🎬", label: "{ep}"}},'
    archived, dropped = None, None
    ids = tab_ids(page)
    lines = tab_lines(page)
    span = section_span(page, eid)
    if eid in ids and span:                                    # replace in place
        page = page[:span[0]] + new_panel + page[span[1]:]
        lines = [new_line if TAB_LINE.search(l) and TAB_LINE.search(l).group(1) == eid else l for l in lines]
    else:
        if span:                                               # a stray panel without a tab entry
            page = page[:span[0]] + page[span[1]:]
        if len(ids) + 1 > MAX_TABS:
            archived = archive_page(root, page, today)
            while len(ids) + 1 > MAX_TABS:
                victim = min((i for i in ids if i not in PINNED and i != eid), key=victim_key, default=None)
                if victim is None:
                    break
                sp = section_span(page, victim)
                if sp:
                    page = page[:sp[0]] + page[sp[1]:]
                lines = [l for l in lines if not (TAB_LINE.search(l) and TAB_LINE.search(l).group(1) == victim)]
                ids.remove(victim)
                dropped = victim
            page = re.sub(r'<a href="archive/index-[^"]*\.html">', f'<a href="archive/{archived.name}">', page, count=1)
        pos = next((i for i, l in enumerate(lines) if (TAB_LINE.search(l) or [None, ""])[1] in PINNED), len(lines))
        lines.insert(pos, new_line)
        at = page.find("<footer>")
        at = at if at != -1 else page.find("<script>")
        page = page[:at] + new_panel + "\n" + page[at:]
    page = set_tabs(page, lines)
    index.write_text(page, encoding="utf-8")
    return {"ep": ep, "id": eid, "tabs": tab_ids(page), "archived": str(archived) if archived else None, "dropped": dropped, "video": has_v}


def open_edge(root: Path, tab_id: str, run=subprocess.run) -> None:
    """Edge explicitly (not the OS default browser): Start-Process msedge file:///.../previews/index.html#<id>."""
    url = (Path(root) / "previews" / "index.html").resolve().as_uri() + "#" + tab_id
    run(["powershell", "-NoProfile", "-Command", f"Start-Process msedge '{url}'"], check=False, timeout=60)


def safe_add(root: Path, ep: str, open_: bool = False, log=None, opener=open_edge, only_if_present: bool = False) -> str:
    """add_tab that never raises: returns a one-line status. A preview failure must not block a build or a post."""
    log = log or (lambda s: print(s, file=sys.stderr))
    try:
        r = add_tab(root, ep, only_if_present=only_if_present)
        if open_:
            try:
                opener(root, r["id"])
            except BaseException as e:     # noqa: BLE001
                log(f"preview tab {ep}: Edge did not open: {str(e)[:120]}")
        return f"preview tab {ep}: ok" + (f" (archived, dropped {r['dropped']})" if r["dropped"] else "")
    except BaseException as e:     # noqa: BLE001
        msg = f"preview tab {ep}: skipped ({type(e).__name__}: {str(e)[:120]})"
        log(msg)
        return msg


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("ep")
    a.add_argument("--open", action="store_true", help="open the page in Microsoft Edge at this tab")
    a.add_argument("--root", default=str(ROOT))
    i = sub.add_parser("ids")
    i.add_argument("--root", default=str(ROOT))
    args = ap.parse_args(argv)
    if args.cmd == "ids":
        print(" ".join(tab_ids((Path(args.root) / "previews" / "index.html").read_text(encoding="utf-8"))))
        return 0
    try:
        r = add_tab(Path(args.root), args.ep)
    except (OSError, ValueError) as e:
        print(f"FAIL {e}", file=sys.stderr)
        return 1
    print(json.dumps(r, ensure_ascii=False))
    if args.open:
        open_edge(Path(args.root), r["id"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
