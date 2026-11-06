"""media_host and the upload routing in ig.py / stories.py: fakes only, no network, no gh call."""
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import ig
import media_host
import stories
from test_ig import ENV, Fake, make_repo


class FakeGh:
    """Stands in for subprocess.run(['gh', ...]): a tiny release store."""
    def __init__(self, listing=None, fail_on=None, undeletable=False):
        self.releases, self.calls, self.fail_on, self.undeletable = dict(listing or {}), [], fail_on, undeletable

    def __call__(self, cmd, **kw):
        a = cmd[1:]
        self.calls.append(a)

        def ok(out=""):
            return SimpleNamespace(returncode=0, stdout=out, stderr="")

        def bad():
            return SimpleNamespace(returncode=1, stdout="", stderr="not found")
        if self.fail_on and a[:2] == self.fail_on:
            return bad()
        if a[:2] == ["release", "create"]:
            self.releases[a[2]] = datetime.now(timezone.utc).isoformat()
            return ok()
        if a[:2] == ["release", "upload"]:
            return ok()
        if a[:2] == ["release", "delete"]:
            if not self.undeletable:
                self.releases.pop(a[2], None)
            return ok()
        if a[:2] == ["release", "view"]:
            return ok() if a[2] in self.releases else bad()
        if a[0] == "api":
            return ok() if a[1].rsplit("/", 1)[-1] in self.releases else bad()
        if a[:2] == ["release", "list"]:
            return ok(json.dumps([{"tagName": t, "createdAt": c} for t, c in self.releases.items()]))
        raise AssertionError(a)


def fetcher(path, size_lie=0, corrupt=False):
    data = path.read_bytes()

    def fetch(url, rng):
        lo, hi = map(int, rng.split("=")[1].split("-"))
        body = data[lo:hi + 1]
        if corrupt:
            body = b"x" * len(body)
        return 206, {"content-range": f"bytes {lo}-{hi}/{len(data) + size_lie}"}, body
    return fetch


@pytest.fixture
def mp4(tmp_path):
    p = tmp_path / "episode.mp4"
    p.write_bytes(bytes(range(256)) * 20000)    # 5 MB, more than one MiB
    return p


def test_host_verifies_and_cleanup_removes_release_and_tag(mp4):
    g = FakeGh()
    url, cleanup = media_host.host(mp4, name="E01", run=g, fetch=fetcher(mp4))
    tag = next(iter(g.releases))
    assert tag.startswith("ig-tmp-E01-") and url == f"https://github.com/{media_host.REPO}/releases/download/{tag}/episode.mp4"
    cleanup()
    assert g.releases == {}
    assert ["release", "delete", tag, "--repo", media_host.REPO, "--cleanup-tag", "--yes"] in g.calls
    cleanup()   # idempotent


@pytest.mark.parametrize("kw", [{"size_lie": 5}, {"corrupt": True}])
def test_host_verification_failure_leaves_nothing_behind(mp4, kw):
    g = FakeGh()
    with pytest.raises(SystemExit) as e:
        media_host.host(mp4, run=g, fetch=fetcher(mp4, **kw))
    assert "MH-VERIFY" in str(e.value) and g.releases == {}


def test_host_upload_failure_leaves_nothing_behind(mp4):
    g = FakeGh(fail_on=["release", "upload"])
    with pytest.raises(SystemExit) as e:
        media_host.host(mp4, run=g, fetch=fetcher(mp4))
    assert "MH-GH" in str(e.value) and g.releases == {}


def test_host_create_failure_and_bad_files(mp4, tmp_path):
    g = FakeGh(fail_on=["release", "create"])
    with pytest.raises(SystemExit) as e:
        media_host.host(mp4, run=g, fetch=fetcher(mp4))
    assert "MH-GH" in str(e.value) and g.releases == {}
    (tmp_path / "empty.mp4").write_bytes(b"")
    with pytest.raises(SystemExit) as e:
        media_host.host(tmp_path / "empty.mp4", run=FakeGh())
    assert "MH-FILE" in str(e.value)


def test_cleanup_that_cannot_delete_fails_loudly(mp4, monkeypatch):
    monkeypatch.setattr(media_host, "_sleep", lambda s: None)
    g = FakeGh()
    url, cleanup = media_host.host(mp4, run=g, fetch=fetcher(mp4))
    g.undeletable = True
    with pytest.raises(SystemExit) as e:
        cleanup()
    assert "MH-CLEANUP" in str(e.value)


def test_sweep_removes_only_stale_ig_tmp_releases():
    now = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)

    def iso(h):
        return (now - timedelta(hours=h)).isoformat().replace("+00:00", "Z")
    g = FakeGh(listing={"ig-tmp-E01-old": iso(3), "ig-tmp-E02-fresh": iso(1), "v1.0": iso(50)})
    assert media_host.sweep(run=g, now=now) == ["ig-tmp-E01-old"]
    assert set(g.releases) == {"ig-tmp-E02-fresh", "v1.0"}


# ---------------------------------------------------------------- routing in ig / stories
class FakeHost:
    def __init__(self, fail=False):
        self.hosted, self.cleaned, self.fail, self.log = [], [], fail, []

    def host(self, path, name=None, **kw):
        self.hosted.append(name)
        self.log.append("host")
        if self.fail:
            raise media_host.MediaHostError("FAIL [MH-VERIFY] test")

        def clean():
            self.cleaned.append(name)
            self.log.append("cleanup")
        return "https://example.test/episode.mp4", clean

    def sweep(self, **kw):
        return []


@pytest.fixture
def host(monkeypatch):
    h = FakeHost()
    monkeypatch.setattr(ig.media_host, "host", h.host)
    monkeypatch.setattr(ig.media_host, "sweep", h.sweep)
    monkeypatch.delenv("IG_VIDEO_URL", raising=False)
    return h


def test_route_by_size_and_env(monkeypatch):
    monkeypatch.delenv("IG_VIDEO_URL", raising=False)
    assert ig.upload_route(ig.URL_ABOVE_BYTES) == "resumable"
    assert ig.upload_route(ig.URL_ABOVE_BYTES + 1) == "video_url-github"
    monkeypatch.setenv("IG_VIDEO_URL", "https://x/y.mp4")
    assert ig.upload_route(5) == "video_url-env"


def test_small_file_stays_resumable_and_is_recorded(tmp_path, host, monkeypatch):
    f = Fake()
    monkeypatch.setattr(ig, "_http", f)
    repo, w = make_repo(tmp_path)
    ig.cmd_publish("E01", go=True, repo=repo, env=dict(ENV), sleep=lambda s: None)
    assert host.hosted == [] and json.loads((w / "post.json").read_text(encoding="utf-8"))["upload"] == "resumable"
    assert any("rupload" in c[1] for c in f.calls)


def test_large_file_goes_by_video_url_and_cleans_after_finished(tmp_path, host, monkeypatch):
    f = Fake()
    monkeypatch.setattr(ig, "_http", f)
    monkeypatch.setattr(ig, "URL_ABOVE_BYTES", 10)
    repo, w = make_repo(tmp_path)
    ig.cmd_publish("E01", go=True, repo=repo, env=dict(ENV), sleep=lambda s: None)
    rec = json.loads((w / "post.json").read_text(encoding="utf-8"))
    assert rec["upload"] == "video_url-github" and host.log == ["host", "cleanup"]
    urls = [c[1].split("?")[0] for c in f.calls]
    i_status = max(i for i, u in enumerate(urls) if u.endswith("/CONT1"))
    i_pub = next(i for i, u in enumerate(urls) if u.endswith("/media_publish"))
    assert i_status < i_pub
    body = next(c for c in f.calls if c[1].split("?")[0].endswith("/1784/media"))[3].decode()
    assert "video_url=https%3A%2F%2Fexample.test%2Fepisode.mp4" in body and "resumable" not in body
    assert not any("rupload" in c[1] for c in f.calls)


def test_cleanup_happens_before_media_publish(tmp_path, host, monkeypatch):
    seen = {}
    f = Fake()

    def http(method, url, headers=None, data=None):
        if url.split("?")[0].endswith("/media_publish"):
            seen["cleaned_before_publish"] = list(host.cleaned)
        return f(method, url, headers, data)
    monkeypatch.setattr(ig, "_http", http)
    monkeypatch.setattr(ig, "URL_ABOVE_BYTES", 10)
    repo, w = make_repo(tmp_path)
    ig.cmd_publish("E01", go=True, repo=repo, env=dict(ENV), sleep=lambda s: None)
    assert seen["cleaned_before_publish"] == ["E01"]


def test_cleanup_runs_when_container_errors(tmp_path, host, monkeypatch):
    monkeypatch.setattr(ig, "_http", Fake(status="ERROR"))
    monkeypatch.setattr(ig, "URL_ABOVE_BYTES", 10)
    repo, w = make_repo(tmp_path)
    with pytest.raises(SystemExit) as e:
        ig.cmd_publish("E01", go=True, repo=repo, env=dict(ENV), sleep=lambda s: None)
    assert "IG-PROCESS" in str(e.value) and host.cleaned == ["E01"] and not (w / "post.json").exists()


def test_cleanup_runs_when_the_api_raises(tmp_path, host, monkeypatch):
    class Boom(Fake):
        def __call__(self, method, url, headers=None, data=None):
            if url.split("?")[0].endswith("/CONT1"):
                raise ig.IgError("FAIL [IG-HTTP] boom")
            return super().__call__(method, url, headers, data)
    monkeypatch.setattr(ig, "_http", Boom())
    monkeypatch.setattr(ig, "URL_ABOVE_BYTES", 10)
    repo, w = make_repo(tmp_path)
    with pytest.raises(SystemExit):
        ig.cmd_publish("E01", go=True, repo=repo, env=dict(ENV), sleep=lambda s: None)
    assert host.cleaned == ["E01"]


def test_host_failure_publishes_nothing(tmp_path, monkeypatch):
    h = FakeHost(fail=True)
    monkeypatch.setattr(ig.media_host, "host", h.host)
    monkeypatch.setattr(ig.media_host, "sweep", h.sweep)
    monkeypatch.delenv("IG_VIDEO_URL", raising=False)
    f = Fake()
    monkeypatch.setattr(ig, "_http", f)
    monkeypatch.setattr(ig, "URL_ABOVE_BYTES", 10)
    repo, w = make_repo(tmp_path)
    with pytest.raises(SystemExit) as e:
        ig.cmd_publish("E01", go=True, repo=repo, env=dict(ENV), sleep=lambda s: None)
    assert "MH-VERIFY" in str(e.value) and not (w / "post.json").exists()
    assert not any(c[1].split("?")[0].endswith(("/1784/media", "/media_publish")) for c in f.calls)


def test_env_url_still_wins_over_hosting(tmp_path, host, monkeypatch):
    monkeypatch.setattr(ig, "_http", Fake())
    monkeypatch.setattr(ig, "URL_ABOVE_BYTES", 10)
    monkeypatch.setenv("IG_VIDEO_URL", "https://hand.test/e.mp4")
    repo, w = make_repo(tmp_path)
    ig.cmd_publish("E01", go=True, repo=repo, env=dict(ENV), sleep=lambda s: None)
    assert host.hosted == [] and json.loads((w / "post.json").read_text(encoding="utf-8"))["upload"] == "video_url-env"


def test_dry_run_names_the_path(tmp_path, host, monkeypatch, capsys):
    repo, w = make_repo(tmp_path)
    ig.cmd_publish("E01", go=False, repo=repo, env={})
    assert "resumable upload" in capsys.readouterr().out
    monkeypatch.setattr(ig, "URL_ABOVE_BYTES", 10)
    ig.cmd_publish("E01", go=False, repo=repo, env={})
    assert "temporary GitHub release" in capsys.readouterr().out and host.hosted == []


def test_story_large_file_uses_host_records_route_and_cleans(tmp_path, host, monkeypatch):
    f = Fake()
    monkeypatch.setattr(ig, "_http", f)
    monkeypatch.setattr(ig, "URL_ABOVE_BYTES", 10)
    v = tmp_path / "S1" / "announce.mp4"
    v.parent.mkdir()
    v.write_bytes(b"\x00" * 64)
    res = stories.post_instagram(dict(ENV), v, sleep=lambda s: None)
    assert res == {"container_id": "CONT1", "upload": "video_url-github"} and host.cleaned == ["story-S1"]
    body = next(c for c in f.calls if c[1].split("?")[0].endswith("/1784/media"))[3].decode()
    assert "media_type=STORIES" in body and "video_url=" in body


def test_a_tag_that_lingers_briefly_is_rechecked(mp4, monkeypatch):
    monkeypatch.setattr(media_host, "_sleep", lambda s: None)
    g = FakeGh()
    url, cleanup = media_host.host(mp4, run=g, fetch=fetcher(mp4))
    tag = next(iter(g.releases))
    real, n = g.__call__, {"api": 0}

    def lingering(cmd, **kw):
        if cmd[1] == "api" and n["api"] < 2:
            n["api"] += 1
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return real(cmd, **kw)
    g.releases.pop(tag)
    media_host._delete(tag, lingering)
    assert n["api"] == 2
