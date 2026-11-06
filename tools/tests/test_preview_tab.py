"""Each finished episode gets its own tab in previews/index.html (tools/preview_tab.py, R-496). Fake repo in tmp_path: no Edge, no process, no network."""
import datetime as dt
import json

import pytest

import autopilot as ap
import preview_tab as pt

PAGE = """<html><body><nav class="tabbar"></nav>
<!--EP_TODAY1027_BEGIN--><section class="panel" id="panel-today" data-tab="today" hidden><main>today</main></section><!--EP_TODAY1027_END-->
<!--EP_E01CALM_BEGIN--><section class="panel" id="panel-e01calm" data-tab="e01calm" hidden><main>e01</main></section><!--EP_E01CALM_END-->
<section class="panel" id="panel-castvoices" data-tab="castvoices" hidden><main>cv</main></section>
<section class="panel" id="panel-artbook" data-tab="artbook" hidden><main><section>inner</section></main></section>
<footer><p><a href="archive/index-2026-10-27.html">older</a></p></footer>
<script>
const TABS = [
  {id: "today", emoji: "📅", label: "Today 27 Oct"},
  {id: "e01calm", emoji: "🕯️", label: "E01 calm"},
  {id: "castvoices", emoji: "🎭", label: "Cast voices"},
  {id: "artbook", emoji: "🖋️", label: "Art Book"},
];
</script></body></html>"""
D = dt.date(2026, 10, 28)


def wj(p, d):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def read(root):
    return (root / "previews" / "index.html").read_text(encoding="utf-8")


def make(tmp_path, ep="E03", full=True):
    root = tmp_path / "repo"
    (root / "previews").mkdir(parents=True)
    (root / "previews" / "index.html").write_text(PAGE, encoding="utf-8")
    w = root / "work" / "episodes" / ep
    w.mkdir(parents=True)
    (w / "episode.mp4").write_bytes(b"\x00video")
    if full:
        (w / "cover.png").write_bytes(b"png")
        wj(w / "gate" / "report.json", {"verdict": "PASS", "complete": True, "checks": [{"id": "A", "status": "pass"}]})
        wj(w / "heal" / "critic.json", {"score": 9})
        wj(root / "work" / "episodes" / "E02" / "decision.json",
           {"choices": [{"id": "1", "text_ar": "تُغلق البالوعة"}, {"id": "2", "text_ar": "تبحث"}], "counts": {"1": 3, "2": 1}, "winner": "1", "status": "OK"})
        wj(w / "post.json", {"permalink": "https://www.instagram.com/reel/X/", "posted_at": "2026-10-28T16:00:00+00:00"})
        d = root / "bible" / "series" / "s" / "episodes" / ep
        d.mkdir(parents=True)
        (d / "caption.txt").write_text("الحلقة ٣ | المكتب\n\nسطر", encoding="utf-8")
    return root


def test_adds_one_tab_with_blocks(tmp_path):
    root = make(tmp_path)
    r = pt.add_tab(root, "E03", D)
    page = read(root)
    assert r["id"] == "e03" and "e03" in pt.tab_ids(page)
    assert page.count('data-tab="e03"') == 1
    assert "preview-snap/E03/episode.mp4" in page and "playsinline" in page and "controls" in page
    assert (root / "work" / "preview-snap" / "E03" / "episode.mp4").is_file()
    assert (root / "work" / "preview-snap" / "E03" / "cover.png").is_file()
    assert "instagram.com/reel/X" in page and "Gates pass" in page and "9/10" in page and "🏆" in page
    assert not pt.TASHKEEL.search(page.split('id="panel-e03"')[1])      # no visible tashkeel


def test_idempotent_replace(tmp_path):
    root = make(tmp_path)
    pt.add_tab(root, "E03", D)
    first = read(root)
    pt.add_tab(root, "E03", D)
    second = read(root)
    assert first == second
    assert second.count('data-tab="e03"') == 1 and pt.tab_ids(second).count("e03") == 1
    wj(root / "work" / "episodes" / "E03" / "facebook.json", {"permalink": "https://www.facebook.com/reel/9/"})
    pt.add_tab(root, "E03", D)
    third = read(root)
    assert "facebook.com/reel/9" in third and third.count('data-tab="e03"') == 1 and len(pt.tab_ids(third)) == 4


def test_four_tab_limit_archives_oldest(tmp_path):
    root = make(tmp_path)
    pt.add_tab(root, "E03", D)
    page = read(root)
    ids = pt.tab_ids(page)
    assert len(ids) == 4 and "today" not in ids and "e03" in ids and {"castvoices", "artbook"} <= set(ids)
    assert 'data-tab="today"' not in page and "inner" in page            # the nested artbook section survived
    arch = root / "previews" / "archive" / "index-2026-10-28.html"
    assert arch.is_file() and 'data-tab="today"' in arch.read_text(encoding="utf-8")   # the archive keeps the full old page
    assert 'href="archive/index-2026-10-28.html"' in page
    e4 = root / "work" / "episodes" / "E04"
    e4.mkdir(parents=True)
    (e4 / "episode.mp4").write_bytes(b"x")
    r = pt.add_tab(root, "E04", D)
    assert r["dropped"] == "e01calm" and (root / "previews" / "archive" / "index-2026-10-28-2.html").is_file()
    assert len(pt.tab_ids(read(root))) == 4


def test_missing_optional_files(tmp_path):
    root = make(tmp_path, full=False)
    pt.add_tab(root, "E03", D)
    page = read(root)
    assert "Not posted yet" in page and "No gate report yet" in page and "poster=" not in page


def test_no_video_and_bad_inputs(tmp_path):
    root = make(tmp_path, full=False)
    (root / "work" / "episodes" / "E03" / "episode.mp4").unlink()
    pt.add_tab(root, "E03", D)
    assert "No episode.mp4" in read(root)
    with pytest.raises(ValueError):
        pt.add_tab(root, "../x")
    with pytest.raises(FileNotFoundError):
        pt.add_tab(tmp_path / "nowhere", "E03")


def test_safe_add_never_raises_and_open_is_injected(tmp_path):
    msgs, opened = [], []
    assert "skipped" in pt.safe_add(tmp_path / "nowhere", "E03", open_=True, log=msgs.append, opener=lambda *a: opened.append(a))
    assert msgs and not opened
    root = make(tmp_path)
    pt.safe_add(root, "E03", open_=False, opener=lambda *a: opened.append(a))
    assert not opened
    pt.safe_add(root, "E03", open_=True, opener=lambda r, i: opened.append(i))
    assert opened == ["e03"]

    def boom(*a):
        raise RuntimeError("edge")
    assert "ok" in pt.safe_add(root, "E03", open_=True, log=msgs.append, opener=boom)


def test_open_edge_uses_msedge_not_default_browser(tmp_path):
    calls = []
    pt.open_edge(tmp_path, "e03", run=lambda cmd, **k: calls.append(cmd))
    assert "Start-Process msedge" in calls[0][-1] and calls[0][-1].rstrip("'").endswith("index.html#e03")


def test_autopilot_hook_skips_without_media_and_failure_is_contained(tmp_path):
    assert ap.real_preview(tmp_path, "E03").startswith("no episode video")      # nothing on disk: skipped, Edge not launched
    root = make(tmp_path)

    def boom(*a, **k):
        raise RuntimeError("preview exploded")
    import preview_tab
    old = preview_tab.safe_add
    preview_tab.safe_add = boom
    try:
        assert "preview tab failed" in ap.real_preview(root, "E03")
    finally:
        preview_tab.safe_add = old


def test_the_oldest_episode_is_dropped_not_the_first_in_display_order(tmp_path):
    # 2026-10-29: [e02 re-added after e03] -> adding E04 dropped e03 instead of e02
    root = make(tmp_path)
    for ep in ("E03", "E02"):
        w = root / "work" / "episodes" / ep
        w.mkdir(parents=True, exist_ok=True)
        (w / "episode.mp4").write_bytes(b"x")
    pt.add_tab(root, "E03", D)          # drops "today": tabs e01calm, e03, castvoices, artbook
    pt.add_tab(root, "E02", D)          # drops e01calm: e03, e02, ...
    assert pt.tab_ids(read(root))[:2] == ["e03", "e02"]
    e4 = root / "work" / "episodes" / "E04"
    e4.mkdir(parents=True)
    (e4 / "episode.mp4").write_bytes(b"x")
    r = pt.add_tab(root, "E04", D)
    assert r["dropped"] == "e02" and "e03" in pt.tab_ids(read(root))


def test_the_after_post_refresh_never_brings_back_an_archived_tab(tmp_path):
    root = make(tmp_path)
    r = pt.add_tab(root, "E03", D, only_if_present=True)
    assert r.get("skipped") and "e03" not in pt.tab_ids(read(root))
    pt.add_tab(root, "E03", D)
    r = pt.add_tab(root, "E03", D, only_if_present=True)
    assert not r.get("skipped") and "e03" in pt.tab_ids(read(root))
