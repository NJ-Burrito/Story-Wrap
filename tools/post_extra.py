"""What happens after the Instagram and Facebook Reels: the YouTube upload and the Instagram / Facebook Page stories (CLAUDE.md "Platforms", "Stories and highlights").

    uv run tools/post_extra.py tick [--dry]   the StoryWrap-Post task (--dry: nothing is posted, nothing is written to the task status): `daily.py post --latest --due --go`, then the extras for every episode posted in the last 36 h
    uv run tools/post_extra.py run <ep> [--go]   the extras for one episode (dry run without --go)

One place for the logic so tools/daily.py carries only a stage entry (`s_extras` below is that stage's body) and so the scheduled Post task keeps retrying the parts that
were waiting (the Facebook story waits for the Facebook Reel's go-live, 19:00 like Instagram since 2026-10-27; a failed upload is retried only when no record exists).
Each part is its own attempt with its own record (youtube.json, stories.json); one failing never blocks or undoes the other, and a part already on record is never repeated.

The children are started with `uv run` (yt.py declares the google libraries, stories.py playwright, as inline script dependencies), so this module needs nothing installed.
Standard library only. The functions take a `run(script, *args) -> str` callable (raises on failure) so tests run without a process.
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ig   # noqa: E402
import stories   # noqa: E402
import yt   # noqa: E402

TOOLS = Path(__file__).resolve().parent
ROOT = ig.REPO
WITHIN_H = 36            # an episode posted longer ago than this is left alone by the scheduled tick
STAGE = "yt_stories"
AFTER_POST = True        # the five after-post steps (tools/after_post.py, R-483 to R-490); tests that must not touch Instagram switch it off


def uv_runner(root: Path = ROOT):
    def run(script: str, *args) -> str:
        r = subprocess.run(["uv", "run", str(TOOLS / script), *map(str, args)], cwd=str(root), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3600,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        out = (r.stdout or "") + (r.stderr or "")
        if r.returncode != 0:
            first = next((l for l in out.splitlines() if l.startswith("FAIL")), out.strip().splitlines()[-1] if out.strip() else f"exit {r.returncode}")
            raise RuntimeError(f"{script} {' '.join(map(str, args[:2]))}: {first[:300]}")
        return out
    return run


def extras_run(root: Path, ep: str, go: bool, run, after=None) -> dict:
    """YouTube first (once Instagram is on record), then the stories, then the after-post steps (first comment, catch-up, sticker card, peer drafts). Returns
    {"youtube": str, "stories": {...}, "after_post": {...}, "errors": {...}, "waiting": bool}."""
    root = Path(root)
    w = root / "work" / "episodes" / ep
    res, errs = {}, {}
    if not (w / "post.json").is_file():
        return {"youtube": "waits: not on Instagram", "stories": "waits: not on Instagram", "errors": {}, "waiting": True}
    # ---- YouTube
    if not yt.has_token():
        res["youtube"] = "no YouTube token"
    elif yt.is_posted(ep, root):
        rec = yt.load_record(ep, root) or {}
        if go and rec.get("video_id") and not rec.get("playlist_item_id") and not rec.get("playlist_error") and not rec.get("playlist_state") and not rec.get("corrupt"):
            try:
                run("yt.py", "playlist", ep, "--go")
                res["youtube"] = "already uploaded; playlist retried"
            except Exception as e:     # noqa: BLE001
                errs["youtube"] = str(e)
        else:
            res["youtube"] = "already"
    else:
        try:
            out = run("yt.py", "publish", ep, *(["--go"] if go else []))
            res["youtube"] = (out.strip().splitlines() or [""])[-1][:200]
        except Exception as e:     # noqa: BLE001
            errs["youtube"] = str(e)
    # ---- stories
    st = {}
    try:
        out = run("stories.py", "announce", ep, *(["--go"] if go else []))
        st["output"] = (out.strip().splitlines() or [""])[-1][:200]
    except Exception as e:     # noqa: BLE001
        errs["stories"] = str(e)
    items = stories.load_record(ep, root)["items"]
    have = {"instagram": bool(ig.load_env().get("IG_ACCESS_TOKEN")), "facebook": bool(ig.load_env().get("FB_PAGE_TOKEN"))}
    waiting = [p for p in stories.PLATFORMS if have[p] and stories.item_key("announce", p) not in items]
    if go:
        st["waiting_for"] = waiting
    res["stories"] = st
    ap = None
    if AFTER_POST and after is not False:
        try:
            import after_post      # lazy: an import or run failure here must never stop the Reel, YouTube or the stories
            ap = after_post.run_all(root, ep, go, **(after or {}))
        except Exception as e:     # noqa: BLE001
            errs["after_post"] = str(e)[:200]
    if ap is not None:
        res["after_post"] = {k: v for k, v in ap.items() if k not in ("errors", "waiting")}
        errs.update({f"after_post.{k}": v for k, v in ap["errors"].items()})
        waiting = waiting or ap["waiting"]
        if go and (ap.get("catchup") or {}).get("status") == "started":      # the catch-up pass just opened: one engagement tick now, the watcher and the hourly task continue it
            try:
                run("engage.py", "run", "--go")
                res["after_post"]["catchup_tick"] = "ran"
            except Exception as e:     # noqa: BLE001  harmless: the hourly engage task does the same tick
                res["after_post"]["catchup_tick"] = "failed (the hourly engage task continues): " + str(e)[:120]
    if go:
        try:      # the posted links appear on the episode's preview tab (no Edge window); a preview failure never changes the post result
            if (root / "previews" / "index.html").is_file() and (w / "episode.mp4").is_file():
                import preview_tab
                res["preview"] = preview_tab.safe_add(root, ep, open_=False, only_if_present=True)   # refresh only: an archived tab is never brought back
        except BaseException as e:     # noqa: BLE001
            res["preview"] = f"preview tab failed: {str(e)[:80]}"
    return {**res, "errors": errs, "waiting": bool(waiting)}


def covers_run(root: Path, ep: str, go: bool, run, build=None) -> dict:
    """R-501 retro-covers: render the grid poster of an already posted episode to work/covers/<ep>-grid.png (+ .jpg) and, where a platform's API can change an existing video's thumbnail,
    set it: Facebook (Graph `/{video}/thumbnails`, not verified for Reels) and YouTube (thumbnails.set). Instagram's API CANNOT change a published Reel's cover: the owner sets it in the app
    (Edit > Edit cover > Add from camera roll) with the png this prints. Dry run without --go: only the poster is rendered. Returns {"poster", "facebook", "youtube", "instagram", "errors"}."""
    root = Path(root)
    import grid_poster
    out = root / "work" / "covers" / f"{ep}-grid.png"
    b = (build or grid_poster.build)(ep, root, out)
    jpg = str(b["jpg"])
    res = {"poster": str(b["png"]), "instagram": f"the Instagram API cannot change a published Reel's cover: in the app use Edit > Edit cover > Add from camera roll, file {b['png']}", "errors": {}}
    for name, script, has in (("facebook", "fb.py", (root / "work" / "episodes" / ep / "facebook.json").is_file()), ("youtube", "yt.py", (root / "work" / "episodes" / ep / "youtube.json").is_file())):
        if not has:
            res[name] = "not posted there"
            continue
        try:
            o = run(script, "thumbnail", ep, "--cover", jpg, *(["--go"] if go else []))
            res[name] = (o.strip().splitlines() or [""])[-1][:200]
        except Exception as e:     # noqa: BLE001
            res["errors"][name] = str(e)[:300]
    return res


def s_extras(ctx) -> dict:
    """The daily.py stage body (POST_STAGES, after `publish`): dry run unless the post run has --go. A stage that still waits or failed is `partial` (stale), so the next run repeats it."""
    ep = ctx.ep
    go = bool(ctx.config.get("go", False))
    if not (ctx.work / "post.json").is_file():
        return {"_status": "partial", "why": "not on Instagram: YouTube and stories wait for it"}   # partial = stale: the next run repeats it (a "skipped" stage would count as done)
    run = lambda script, *a: ctx.uv(script, *a, label=f"{script} {a[0]}", machine=False)   # noqa: E731
    r = extras_run(ctx.root, ep, go, run)
    if not go:
        return {"_status": "partial", "why": "dry run: add --go to post", "youtube": r["youtube"]}
    if r["errors"] or r["waiting"]:
        return {"_status": "partial", "youtube": r["youtube"], "errors": {k: v[:200] for k, v in r["errors"].items()}, "waiting": r["waiting"]}
    return {"youtube": r["youtube"], "stories": r["stories"], "after_post": r.get("after_post")}


def stages(Stage) -> dict:
    """The stage table entry daily.py adds (kind io, no input fingerprints: its records are youtube.json and stories.json)."""
    return {STAGE: Stage(STAGE, s_extras, lambda c: [], "io")}


# ---------------------------------------------------------------- harvest side (ig_board.py harvest-due)
def youtube_comments(ep: str, root: Path = ROOT, run=None) -> str | None:
    """YouTube comments of an uploaded episode into comments.json as ideas (platform=youtube). Returns an error text or None. Never raises, never touches the vote."""
    if not (yt.has_token() and yt.is_posted(ep, root)) or not (yt.load_record(ep, root) or {}).get("video_id"):
        return None
    try:
        (run or uv_runner(root))("yt.py", "comments", ep, "--force")
        return None
    except Exception as e:     # noqa: BLE001
        return str(e)[:200]


def vote_stories(root: Path = ROOT, go: bool = False, run=None) -> dict:
    """The next-morning result stories (decision.json written within stories.VOTE_WINDOW_H). One subprocess; an error is returned, never raised."""
    try:
        out = (run or uv_runner(root))("stories.py", "vote-due", *(["--go"] if go else []))
        return {"ok": True, "out": out.strip()[-400:]}
    except Exception as e:     # noqa: BLE001
        return {"ok": False, "error": str(e)[:300]}


# ---------------------------------------------------------------- the scheduled Post task
def unrecorded_errors(root: Path, ep: str, errors: dict) -> dict:
    """The errors of an extras run that left NO record behind (so nothing on the board shows them): a YouTube upload that failed before youtube.json existed, a stories
    run that failed with no stories.json entry on any platform that has credentials. A failure that left a record is visible there already."""
    out = {}
    if "youtube" in errors and not yt.is_posted(ep, root):
        out["youtube"] = errors["youtube"]
    if "stories" in errors and not stories.load_record(ep, root)["items"]:
        out["stories"] = errors["stories"]
    for k, v in errors.items():     # an after-post step that failed before it could leave a record (the first comment writes one before the call; the others write none)
        if (k == "after_post" or k.startswith("after_post.")) and k != "after_post.first_comment":
            out[k] = v
    return out


def tick(root: Path = ROOT, at: datetime | None = None, run=None, daily=None, go: bool = True, late_ep: str | None = None) -> int:
    """`daily.py post --latest --due --go` first (its exit code is this task's exit code), then the extras for every episode on Instagram within WITHIN_H hours.
    `late_ep` (R-507, the autopilot's late post): `daily.py post <ep> --go --late` instead of `--latest --due`: the same stages and gates for a complete episode whose slot has passed."""
    root, cur = Path(root), at or datetime.now()
    run = run or uv_runner(root)
    post_args = ["post", late_ep, "--late"] if late_ep else ["post", "--latest", "--due"]
    rc = (daily or (lambda: subprocess.run(["uv", "run", str(TOOLS / "daily.py"), *post_args, *(["--go"] if go else [])], cwd=str(root)).returncode))()
    wd = root / "work" / "episodes"
    lost = []
    for d in sorted(wd.glob("*")) if wd.is_dir() else []:
        try:
            post = ig.read_json(d / "post.json")             # an unreadable post.json skips that episode, it never stops the tick
            t = datetime.fromisoformat(post["posted_at"]) if isinstance(post, dict) else None
        except (KeyError, ValueError, TypeError, OSError):
            t = None
        if t is None:
            continue
        if t.tzinfo is not None:
            t = t.astimezone().replace(tzinfo=None)
        if cur - t > timedelta(hours=WITHIN_H):
            continue
        try:
            r = extras_run(root, d.name, go, run)
        except Exception as e:     # noqa: BLE001  one episode's failure never aborts the others or the PARTIAL status below
            r = {"errors": {"extras": str(e)[:200]}}
            lost.append(f"{d.name} extras: {str(e)[:120]}")
        print(f"{d.name} extras: youtube={r.get('youtube', 'error')}; stories={r.get('stories', 'error')}; after_post={r.get('after_post', 'off')}" + (f"; ERRORS {r['errors']}" if r["errors"] else ""))
        lost.extend(f"{d.name} {k}: {str(v)[:120]}" for k, v in unrecorded_errors(root, d.name, r["errors"]).items())
    if lost and rc == 0 and go:       # a step failed and left no record behind: say so on the board (the next tick retries it)
        import loop_gate
        loop_gate.write_task_status(root, "StoryWrap-Post", "PARTIAL", "extras failed without a record: " + "; ".join(lost), cur)
    return rc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="YouTube and stories after the Reels")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("tick"); p.add_argument("--dry", action="store_true", help="no --go anywhere: the daily.py post dry run and the extras dry runs; writes no task status")
    p.add_argument("--late-ep", help="the autopilot's late post of this episode (R-507): daily.py post <ep> --late --go")
    p = sub.add_parser("run"); p.add_argument("ep"); p.add_argument("--go", action="store_true")
    p = sub.add_parser("covers"); p.add_argument("ep"); p.add_argument("--go", action="store_true", help="set the new grid poster as the thumbnail on Facebook and YouTube (never Instagram: the app does that)")
    a = ap.parse_args(argv)
    if a.cmd == "tick":
        return tick(go=not a.dry, late_ep=a.late_ep)
    if a.cmd == "covers":
        r = covers_run(ROOT, a.ep, a.go, uv_runner(ROOT))
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return 1 if r["errors"] else 0
    r = extras_run(ROOT, a.ep, a.go, uv_runner(ROOT))
    print(r)
    return 1 if r["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
