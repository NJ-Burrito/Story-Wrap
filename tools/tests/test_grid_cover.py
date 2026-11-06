"""Grid poster and cover publishing (R-501, the owner 2026-10-28): layout inside the 3:4 crop, frame 0 not black, cover_url in the IG container, YouTube thumbnails.set. No network."""
import json
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

import fb
import grid_poster as GP
import ig
import post_extra
import watermark as WM
import yt
from test_ig import ENV as IG_ENV, Fake as IgFake, make_repo as ig_make_repo
import test_yt
from test_yt import env  # noqa: F401  (autouse: the YouTube token file and the stubbed media/seconds)


def tiny_png(path: Path):
    Image.fromarray(np.full((64, 36, 3), 90, np.uint8)).save(path)


def test_every_box_is_inside_the_3x4_grid_crop_and_clear_of_the_mark():
    assert GP.CROP == (0, 240, 1080, 1680) and (GP.CROP[2] - GP.CROP[0]) * 4 == (GP.CROP[3] - GP.CROP[1]) * 3
    assert GP.box_problems() == []
    for name, (x0, y0, x1, y1, px) in GP.BOXES.items():
        assert GP.CROP[0] <= x0 < x1 <= GP.CROP[2] and GP.CROP[1] <= y0 < y1 <= GP.CROP[3], name
    r = WM.rect()
    assert all(not (b[0] < r["x"] + r["w"] and b[2] > r["x"] and b[1] < r["y"] + r["h"] and b[3] > r["y"]) for b in GP.BOXES.values())


def test_a_box_outside_the_crop_or_too_small_for_a_grid_tile_is_refused():
    assert any("leaves the 3:4 crop" in p for p in GP.box_problems({**GP.BOXES, "hook": (64, 1600, 1016, 1760, 96)}))
    assert any("too small" in p for p in GP.box_problems({**GP.BOXES, "series": (64, 1578, 1016, 1642, 30)}))


def test_hook_comes_from_the_plan_else_the_first_clause_of_the_caption_and_is_at_most_three_words():
    assert GP.hook_text({"cover_hook": "خيط أحمر مقطوع"}) == "خيط أحمر مقطوع"
    assert GP.hook_text({"cover_hook": "واحد اثنان ثلاثة أربعة"}) == "واحد اثنان ثلاثة"
    cap = "الحلقة ٢ | the series 🕯️ مصباح مضاء يصعد من تحت الأرض، وخيطه الأحمر مقطوع\n\nx"
    assert GP.hook_text({"post_caption": cap}) == "مصباح مضاء يصعد"
    with pytest.raises(SystemExit):
        GP.hook_text({})
    with pytest.raises(SystemExit):
        GP.hook_text({"cover_hook": "هُدى"})     # tashkeel is refused


def test_scene_is_the_first_event_scene_else_the_first_scene():
    assert GP.pick_scene({"scenes": [{"id": "s01"}, {"id": "s05", "event": "x"}, {"id": "s07", "event": "y"}]})["id"] == "s05"
    assert GP.pick_scene({"scenes": [{"id": "s01"}, {"id": "s02"}]})["id"] == "s01"


def video(path: Path, color: str, secs: float = 1.0):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c={color}:s=1080x1920:r=24:d={secs}", "-pix_fmt", "yuv420p", str(path)], check=True)


def test_frame0_black_is_refused_and_the_poster_is_accepted(tmp_path):
    poster = tmp_path / "p.png"
    Image.fromarray(np.full((1920, 1080, 3), (120, 90, 60), np.uint8)).save(poster)
    black, good, other = tmp_path / "black.mp4", tmp_path / "good.mp4", tmp_path / "other.mp4"
    video(black, "black")
    video(good, "0x785a3c")
    video(other, "0x2060ff")
    ok, detail = GP.frame0_check(black, poster)
    assert not ok and "near-black" in detail
    ok, detail = GP.frame0_check(good, poster)
    assert ok, detail
    ok, detail = GP.frame0_check(other, poster)
    assert not ok and "does not match" in detail


def test_the_gate_has_the_cover_frame0_check_and_assemble_puts_the_poster_first():
    src = (Path(GP.__file__).parent / "calm_compose.py").read_text(encoding="utf-8")
    assert 'rec("COVER-FRAME0"' in src and "GP.frame0_check(ep.out, cp_)" in src
    assert "overlay=0:0:eof_action=pass" in src and '"-loop", "1"' in src      # the poster overlays frame 0 of the delivered file


def cover_body(f):
    return next(c[3] for c in f.calls if c[1].split("?")[0].endswith("/1784/media")).decode()


def test_ig_container_carries_cover_url_when_the_episode_has_a_poster(tmp_path, monkeypatch):
    repo, w = ig_make_repo(tmp_path)
    tiny_png(w / "cover.png")
    hosted, cleaned = [], []
    monkeypatch.setattr(ig.media_host, "host", lambda p, name=None, **k: (hosted.append((Path(p).name, name)) or "https://example.test/cover.jpg", lambda: cleaned.append(1)))
    f = IgFake()
    monkeypatch.setattr(ig, "_http", f)
    rec = ig.cmd_publish("E01", go=True, repo=repo, env=dict(IG_ENV), sleep=lambda s: None)
    body = cover_body(f)
    assert "cover_url=https%3A%2F%2Fexample.test%2Fcover.jpg" in body and "media_type=REELS" in body
    assert hosted == [("cover.jpg", "E01-cover")] and cleaned == [1] and rec["cover"] is True and (w / "cover.jpg").is_file()


def test_ig_container_has_no_cover_url_without_a_poster_and_a_hosting_failure_never_blocks_the_post(tmp_path, monkeypatch):
    repo, w = ig_make_repo(tmp_path)
    f = IgFake()
    monkeypatch.setattr(ig, "_http", f)
    ig.cmd_publish("E01", go=True, repo=repo, env=dict(IG_ENV), sleep=lambda s: None)
    assert "cover_url" not in cover_body(f)
    repo2, w2 = ig_make_repo(tmp_path / "b")
    tiny_png(w2 / "cover.png")
    monkeypatch.setattr(ig.media_host, "host", lambda *a, **k: (_ for _ in ()).throw(SystemExit("MH-GH no gh")))
    f2 = IgFake()
    monkeypatch.setattr(ig, "_http", f2)
    rec = ig.cmd_publish("E01", go=True, repo=repo2, env=dict(IG_ENV), sleep=lambda s: None)
    assert rec["media_id"] == "MEDIA1" and rec["cover"] is False and "cover_url" not in cover_body(f2)


def test_yt_publish_calls_thumbnails_set_with_the_poster(tmp_path, monkeypatch):
    repo, w = test_yt.make_repo(tmp_path)
    tiny_png(w / "cover.png")
    monkeypatch.setattr(yt, "_image", lambda p: f"image:{p.name}")
    f, calls = test_yt.Fake(), []

    class T:
        def set(self, videoId, media_body):
            calls.append((videoId, media_body))
            return test_yt.Req(lambda: {"kind": "youtube#thumbnailSetResponse"})
    f.thumbnails = lambda: T()
    yt.cmd_publish("E01", go=True, repo=repo, svc=f)
    assert calls == [("VID1", "image:cover.jpg")]
    assert json.loads((w / "youtube.json").read_text(encoding="utf-8"))["thumbnail"]["state"] == "set"


def test_yt_thumbnail_refused_by_the_channel_is_skipped_logged_and_the_upload_stands(tmp_path, monkeypatch, capsys):
    repo, w = test_yt.make_repo(tmp_path)
    tiny_png(w / "cover.png")
    monkeypatch.setattr(yt, "_image", lambda p: "image")
    f = test_yt.Fake()

    class T:
        def set(self, videoId, media_body):
            return test_yt.Req(lambda: (_ for _ in ()).throw(test_yt.HttpErr(403, "forbidden")))
    f.thumbnails = lambda: T()
    rec = yt.cmd_publish("E01", go=True, repo=repo, svc=f)
    saved = json.loads((w / "youtube.json").read_text(encoding="utf-8"))
    assert rec["video_id"] == "VID1" and saved["thumbnail"]["state"] == "skipped" and saved["playlist_item_id"] == "PLI1"
    assert "thumbnail not set" in capsys.readouterr().out


def test_fb_thumbnail_is_a_multipart_post_and_the_covers_command_never_goes_live_without_go(tmp_path, monkeypatch):
    body, ctype = fb.multipart({"is_preferred": "true"}, "source", "cover.jpg", b"JPEGBYTES")
    assert ctype.startswith("multipart/form-data; boundary=") and b'name="source"; filename="cover.jpg"' in body and b"JPEGBYTES" in body and b'name="is_preferred"' in body
    seen = []
    monkeypatch.setattr(ig, "_http", lambda m, u, h=None, d=None: (seen.append((m, u)) or {"success": True}))
    jpg = tmp_path / "c.jpg"
    jpg.write_bytes(b"x")
    assert fb.set_thumbnail({"FB_PAGE_ID": "1", "FB_PAGE_TOKEN": "T"}, "VID9", jpg)["state"] == "set"
    assert seen and seen[0][0] == "POST" and seen[0][1].endswith("/VID9/thumbnails")
    calls, root = [], tmp_path / "r"
    (root / "work/episodes/E02").mkdir(parents=True)
    (root / "work/episodes/E02/facebook.json").write_text("{}", encoding="utf-8")
    (root / "work/episodes/E02/youtube.json").write_text("{}", encoding="utf-8")
    res = post_extra.covers_run(root, "E02", False, lambda script, *a: calls.append((script, a)) or "DRY RUN ok", build=lambda ep, r, out: {"png": str(out), "jpg": str(out.with_suffix(".jpg"))})
    assert [c[0] for c in calls] == ["fb.py", "yt.py"] and all("--go" not in c[1] for c in calls) and all(c[1][0] == "thumbnail" for c in calls)
    assert "cannot change a published Reel" in res["instagram"] and not res["errors"]
