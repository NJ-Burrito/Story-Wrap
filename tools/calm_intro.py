# /// script
# requires-python = ">=3.11"
# dependencies = ["playwright", "pillow", "numpy", "scipy"]
# ///
"""intro_freeze: the calm format's character introduction (owner, 2026-10-23 note C10; CLAUDE.md "Calm format", "Character introductions").

The first time a character is really on screen (not a prop close-up, not a bare hand), the story stops for one beat:
  1. a dramatic transition INTO the beat (the plan's cut type "freeze": a dissolve into a white flash and a zoom punch, with the `impact` sound);
  2. the frame FREEZES on that character (the last frame of the scene that introduced them);
  3. a GREY GLOW and outline isolate the character, the rest of the frame dims and loses its colour;
  4. a short GRAFFITI text (Thmanyah, no tashkeel) is drawn, by hand, behind the character: their name and one line from their bible
     (what they are extreme about), with a marker underline and a few tick marks; it stays long enough to read (cap_sentence reading-time rule);
  5. the colour comes back and the plan's next join carries the picture back into the story.
The narrator may read the introduction (a new narrator line = a new take). The caption plate under it is the ordinary one.

It is a card-kind shot ("kind": "card", "template": "intro_freeze"), so tools/shot.py runs it with the card stage names and calm_compose places it on
the timeline as an item of kind "intro" right after the scene that introduced the character (plan key `intros`).

The character is cut out of the freeze with the engine's own line-art mask of the source shot (work/shots/<src>/out/masks/line/<actor>/NNNN.png): the
mask is closed and filled into a silhouette (`silhouette`). Nothing is segmented by a model.

Checks (all deterministic, on the measured numbers and on the recorded video):
  CALM-INTRO (episode, calm_compose.stage_gate): every character's first appearance is followed by an intro_freeze item, entered by the "freeze" cut, left by a
    declared cut back into the story, never introduced twice; the shot's own gate must have passed.
  INTRO-ISOLATE   the silhouette is a plausible share of the frame; in the recorded video the character is brighter and more colourful than the rest, and a grey rim shows
  INTRO-FROZEN    the character's pixels do not move between two held frames
  INTRO-READ      the text is fully drawn at least READ_BASE_S + READ_PER_WORD_S x words before the beat ends
  INTRO-TEXT      Thmanyah only, no tashkeel, inside the safe area, at least VISIBLE_MIN of the text not hidden behind the character
  INTRO-LEN       the beat lasts 3..9 s on the 24 fps grid

  uv run tools/calm_intro.py list <plan.json>        the first appearances of the plan and which already have an intro
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("STORYWRAP_ROOT") or TOOLS.parent)
sys.path.insert(0, str(TOOLS))
import cap_sentence as CS   # noqa: E402
from arabic_display import has_tashkeel, tashkeel_chars   # noqa: E402
from shotlib.engine import Stage, StageFail   # noqa: E402

FPS, W, H = 24, 1080, 1920
SAFE = {"x0": 54, "y0": 270, "x1": 1026, "y1": 1250}
FONTS = ROOT / "assets" / "fonts"
ACCENT = "#f2c14e"
GREY = (200, 200, 200)

# ------------------------------------------------------------------ timing of the beat (seconds from the first frame of the clip)
FLASH_S = 0.20             # white flash that decays
PUNCH_S = 0.50             # zoom punch (1.10 -> 1.0) and a short shake
DIM_AT_S, DIM_S = 0.12, 0.45   # the rest of the frame dims and desaturates
NAME_AT_S, NAME_S = 0.85, 0.80
LINE_S = 0.30              # the marker underline, drawn right after the name
TAG_AT_S, TAG_S = 1.75, 1.00
TICKS_AT_S, TICKS_S = 1.20, 0.40
TEXT_DONE_S = TAG_AT_S + TAG_S        # everything is drawn at this time
OUT_S = 0.40               # colour and glow come back, the text fades (the plan's next join carries the picture away)
MIN_S, MAX_S = 3.0, 9.0
VISIBLE_MIN = 0.85         # at least this share of the text pixels is not hidden behind the character
SIL_SHARE = (0.03, 0.65)   # the silhouette's share of the frame
DIM_LUMA = 0.62            # outside the character the picture is at most this fraction of the character's brightness (measured on the video)
DIM_SAT = 0.60             # ... and at most this fraction of its colourfulness
RIM_GAIN = 18.0            # the rim around the character is at least this many levels (of 255) brighter than the dimmed picture just beyond it
FROZEN_MAX = 4.0           # mean absolute change of the character's pixels between two held frames, in levels (of 255)
MASK_STEP = 6              # shot.py writes a line mask every 6th frame
TAG_WORDS_MAX = 6
HEAD_ROOM_Y = 740          # the frozen picture is slid down (the camera tilts) until the character's head top is at least here, so the graffiti has the band above it
SHIFT_MAX = 240
NAME_WORDS_MAX = 2
FORMAT_V2_FROM_EPISODE = 3   # calm_compose.FORMAT_V2_FROM_EPISODE (asserted equal by the tests)


# ------------------------------------------------------------------ plan logic (pure)
def scene_characters(scene: dict) -> list[str]:
    """The characters a plan scene shows as people (a prop close-up or a bare hand shows an object or a part, not the character)."""
    p = scene.get("params", {}) or {}
    target = str(p.get("target", ""))
    if target.startswith("prop:") or target.startswith("hand"):
        return []
    if scene.get("template") == "two_shot":
        return [x.strip() for x in str(p.get("characters", "")).split(",") if x.strip()]
    return [p["character"]] if p.get("character") else []


def first_appearances(scenes: list[dict]) -> dict[str, str]:
    """character -> id of the first plan scene that shows them as a person."""
    out: dict[str, str] = {}
    for s in scenes:
        for c in scene_characters(s):
            out.setdefault(c, s["id"])
    return out


def _episode_no(ep_id) -> int | None:
    import re
    m = re.match(r"E(\d+)", str(ep_id or ""))
    return int(m.group(1)) if m else None


def deferred_intros(plan: dict) -> tuple[set[str], list[str]]:
    """A RECORDED exemption: an episode may keep fewer intros so that the freeze time stays short, by listing the characters it defers in the
    plan key `intros_deferred`: [{"character", "to_episode": "E03", "reason"}]. The exemption is valid only for a character who has NO intro in this plan, with a reason, and a
    LATER episode; that later episode then gets no exemption (introduced_before does not know them), so the intro cannot be skipped for good. Returns (valid characters, problems)."""
    n = _episode_no(plan.get("episode"))
    ok: set[str] = set()
    bad: list[str] = []
    have = {i.get("character") for i in plan.get("intros", []) or []}
    for d in plan.get("intros_deferred", []) or []:
        ch, to = d.get("character"), _episode_no(d.get("to_episode"))
        if not ch or not str(d.get("reason", "")).strip():
            bad.append(f"PLAN-INTRO a deferred intro needs a character and a reason: {d!r}")
        elif n is None or to is None or to <= n:
            bad.append(f"PLAN-INTRO {ch} is deferred to {d.get('to_episode')!r}, which is not a later episode than {plan.get('episode')!r}")
        elif ch in have:
            bad.append(f"PLAN-INTRO {ch} is both introduced and deferred")
        else:
            ok.add(ch)
    return ok, bad


def introduced_before(plan: dict, root: Path | None = None) -> set[str]:
    """Intros once per series (the owner 2026-10-28): the characters introduced in any EARLIER episode of the series, read from bible/series/<series>/episodes/E<n>*/calm-plan.json
    (`intros`; the E01 variant E01C counts as E01, the original). Only for format v2 episodes (E03 on): E01 and E02 are published and keep their own intros. A character who appears
    in an earlier plan's scenes is introduced too (they were on screen)."""
    n = _episode_no(plan.get("episode"))
    if n is None or n < FORMAT_V2_FROM_EPISODE:
        return set()
    base = Path(root or ROOT) / "bible" / "series" / str(plan.get("series", "")) / "episodes"
    out: set[str] = set()
    if not base.is_dir():
        return out
    for d in sorted(base.iterdir()):
        k = _episode_no(d.name)
        pf = d / "calm-plan.json"
        if k is None or k >= n or not pf.is_file():
            continue
        try:
            prev = json.loads(pf.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out |= {i.get("character") for i in prev.get("intros", []) or [] if i.get("character")}
    return out


def min_duration(words: int) -> float:
    """The shortest beat that lets the text finish drawing, stay up for its reading time, and give the colour back (on the 24 fps grid)."""
    need = TEXT_DONE_S + CS.READ_BASE_S + CS.READ_PER_WORD_S * words + OUT_S
    return math.ceil(need * FPS) / FPS


def read_budget(words: int) -> float:
    return CS.READ_BASE_S + CS.READ_PER_WORD_S * words


def plan_problems(plan: dict, script: dict | None = None, root: Path | None = None) -> list[str]:
    """Static CALM-INTRO checks of calm-plan.json (before anything is built). Returns 'PLAN-INTRO message' strings."""
    f: list[str] = []
    scenes = plan.get("scenes", [])
    ids = [s.get("id") for s in scenes]
    intros = plan.get("intros", []) or []
    lines = {l["id"]: l for l in (script or {}).get("lines", [])}
    seen_ch, seen_id = {}, set()
    known = introduced_before(plan, root)       # characters an earlier episode of the series introduced: never again (the owner 2026-10-28)
    for it in intros:
        iid = it.get("id")
        if not iid or iid in ids or iid in seen_id or iid in ("recap", "day", "choice", "follow"):
            f.append(f"PLAN-INTRO intro id {iid!r} is missing, repeats or clashes with a scene or card id")
        seen_id.add(iid)
        for k in ("character", "after", "name", "tag"):
            if not str(it.get(k, "")).strip():
                f.append(f"PLAN-INTRO {iid} has no {k}")
        if it.get("after") not in ids:
            f.append(f"PLAN-INTRO {iid} comes after {it.get('after')!r}, which is not a scene of the plan")
        for k in ("name", "tag"):
            v = str(it.get(k, ""))
            if has_tashkeel(v):
                f.append(f"PLAN-INTRO {iid} {k} carries tashkeel: the graffiti is visible text (CLAUDE.md)")
        if len(str(it.get("name", "")).split()) > NAME_WORDS_MAX:
            f.append(f"PLAN-INTRO {iid} name is over {NAME_WORDS_MAX} words")
        if len(str(it.get("tag", "")).split()) > TAG_WORDS_MAX:
            f.append(f"PLAN-INTRO {iid} tag is over {TAG_WORDS_MAX} words: graffiti is short")
        if it.get("line"):
            if script is not None and it["line"] not in lines:
                f.append(f"PLAN-INTRO {iid} line {it['line']} is not in script.json")
            elif script is not None and lines[it["line"]].get("speaker") != "narrator":
                f.append(f"PLAN-INTRO {iid} is read by the narrator, not {lines[it['line']].get('speaker')}")
        ch = it.get("character")
        if ch in seen_ch:
            f.append(f"PLAN-INTRO {ch} is introduced twice ({seen_ch[ch]} and {iid}): once per character per episode")
        seen_ch[ch] = iid
        if ch in known:
            f.append(f"PLAN-INTRO {ch} was introduced in an earlier episode of the series: an intro happens once per series, drop {iid} (and its transitions)")
    defer_ok, defer_bad = deferred_intros(plan)
    f += defer_bad
    firsts = {c: sid for c, sid in first_appearances(scenes).items() if c not in known and c not in defer_ok}      # a valid recorded deferral is the only way out of "no intro at first appearance"
    for ch, sid in firsts.items():
        mine = [it for it in intros if it.get("character") == ch]
        if not mine:
            f.append(f"PLAN-INTRO {ch} first appears in scene {sid} and has no intro_freeze (plan key `intros`): a character is introduced the first time they are on screen")
        elif mine[0].get("after") != sid:
            f.append(f"PLAN-INTRO {ch}'s intro comes after {mine[0].get('after')}, but their first appearance is scene {sid}")
    for ch in seen_ch:
        if ch not in firsts and ch not in known:
            f.append(f"PLAN-INTRO {ch} has an intro but is never shown as a person in a scene")
    return f


def episode_problems(plan: dict, tl: dict, measures: dict[str, dict | None]) -> list[str]:
    """CALM-INTRO on the built timeline. `measures` maps an intro item id to its shot's intro-measure.json (None when missing)."""
    f: list[str] = []
    items = tl.get("items", [])
    pos = {it["id"]: i for i, it in enumerate(items)}
    known = introduced_before(plan) | deferred_intros(plan)[0]      # a recorded deferral needs no intro item in this episode
    firsts = {c: sid for c, sid in first_appearances(plan.get("scenes", [])).items() if c not in known}
    intro_items = [it for it in items if it.get("kind") == "intro"]
    for ch, sid in firsts.items():
        i = pos.get(sid)
        nxt = items[i + 1] if i is not None and i + 1 < len(items) else None
        if nxt is None or nxt.get("kind") != "intro" or nxt.get("character") != ch:
            f.append(f"CALM-INTRO {ch} first appears in {sid} and no intro_freeze follows it")
            continue
        jin = (nxt.get("join_in") or {}).get("cut")
        if jin != "freeze":
            f.append(f"CALM-INTRO {ch}: the join into {nxt['id']} is {jin!r}, the dramatic transition is the cut 'freeze'")
        after = items[i + 2] if i + 2 < len(items) else None
        jout = ((after or {}).get("join_in") or {}).get("cut")
        if after is None or not jout or jout == "freeze":
            f.append(f"CALM-INTRO {ch}: nothing carries the picture back into the story after {nxt['id']} (a declared cut that is not 'freeze')")
        m = measures.get(nxt["id"])
        if not m:
            f.append(f"CALM-INTRO {nxt['id']} has no intro-measure.json: build its shot first")
        elif not m.get("ok"):
            f.append(f"CALM-INTRO {nxt['id']} failed its own gate: {'; '.join(m.get('fails', [])[:2])}")
    for it in intro_items:
        if it.get("character") not in firsts:
            f.append(f"CALM-INTRO {it['id']} introduces {it.get('character')}, who is never shown as a person")
        elif pos[firsts[it["character"]]] + 1 != pos[it["id"]]:
            f.append(f"CALM-INTRO {it['id']} is not right after {it['character']}'s first appearance ({firsts[it['character']]})")
    return f


def default_params(entry: dict, ep: str, scenes: dict) -> dict:
    """The intro_freeze parameters of one `intros` plan entry (daily.py s_shots)."""
    src = scenes[entry["after"]]
    return {"character": entry["character"], "name": entry["name"], "tag": entry["tag"], "source": f"work/shots/{ep}-{entry['after']}", "hold": float(src.get("hold") or 0.0)}


# ------------------------------------------------------------------ the picture (numpy, no browser)
def silhouette(line_alpha, pad: int = 6, close: int = 5, min_part: float = 0.04):
    """The character's filled silhouette (float 0..1, the shape of `line_alpha`) from its line-art mask: the ink is closed, the inside filled,
    stray specks dropped. A line that runs off the frame edge is closed along that edge, so a character cut by the frame is still filled."""
    import numpy as np
    from scipy import ndimage as ndi
    a = np.asarray(line_alpha) > 24
    h, w = a.shape
    g = np.zeros((h + 2 * pad, w + 2 * pad), bool)
    g[pad:pad + h, pad:pad + w] = a
    for rows, cols, fn in ((slice(pad, pad + 3), slice(None), "top"), (slice(pad + h - 3, pad + h), slice(None), "bottom")):
        band = g[rows, :].any(axis=0)
        if band.any():
            xs = np.where(band)[0]
            r = pad if fn == "top" else pad + h - 1
            g[r, xs.min():xs.max() + 1] = True
    for cols, fn in ((slice(pad, pad + 3), "left"), (slice(pad + w - 3, pad + w), "right")):
        band = g[:, cols].any(axis=1)
        if band.any():
            ys = np.where(band)[0]
            c = pad if fn == "left" else pad + w - 1
            g[ys.min():ys.max() + 1, c] = True
    closed = ndi.binary_closing(g, structure=ndi.generate_binary_structure(2, 1), iterations=close)
    filled = ndi.binary_fill_holes(closed)
    lab, n = ndi.label(filled)
    if n == 0:
        return np.zeros((h, w), np.float32)
    sizes = ndi.sum(filled, lab, range(1, n + 1))
    keep = [i + 1 for i, s in enumerate(sizes) if s >= min_part * sizes.max()]
    out = np.isin(lab, keep)[pad:pad + h, pad:pad + w]
    return out.astype(np.float32)


def shift_down(a, dy: int, fill_edge: bool = True):
    """The picture moved down by dy px; the strip that opens at the top repeats the top row (or is empty for a mask)."""
    import numpy as np
    out = np.empty_like(a)
    out[dy:] = a[:a.shape[0] - dy]
    out[:dy] = a[0] if fill_edge else 0
    return out


def to_canvas(sil, size=(W, H)):
    """A silhouette at any scale -> the canvas, edge smoothed (float32 H x W)."""
    import numpy as np
    from PIL import Image
    from scipy import ndimage as ndi
    im = Image.fromarray((np.asarray(sil) * 255).astype("uint8")).resize(size, Image.BILINEAR)
    return ndi.gaussian_filter(np.asarray(im, np.float32) / 255.0, 1.6)


def glow_fields(sil):
    """(rim, halo): a thin bright outline just outside the character, and a soft grey halo that falls off with distance. Both 0..1, zero inside."""
    import numpy as np
    from scipy import ndimage as ndi
    d = ndi.distance_transform_edt(np.asarray(sil) < 0.5).astype(np.float32)
    rim = np.clip(1.0 - np.abs(d - 5.0) / 3.5, 0.0, 1.0)
    halo = np.exp(-d / 46.0) * (d > 0) * 0.55
    return rim * (d > 0), halo.astype(np.float32)


def dimmed(rgb, sat: float = 0.16, gain: float = 0.40):
    """The picture with its colour mostly gone and its light turned down (float32 0..255)."""
    import numpy as np
    x = np.asarray(rgb, np.float32)
    g = (x * np.array([0.299, 0.587, 0.114], np.float32)).sum(axis=2, keepdims=True)
    y = (g + (x - g) * sat) * gain
    hh, ww = y.shape[:2]
    yy, xx = np.mgrid[0:hh, 0:ww].astype(np.float32)
    r = np.sqrt(((xx - ww / 2) / (ww * 0.62)) ** 2 + ((yy - hh * 0.46) / (hh * 0.62)) ** 2)
    return y * np.clip(1.15 - 0.55 * r ** 2, 0.45, 1.0)[..., None]


def ease_out(p: float) -> float:
    p = min(max(p, 0.0), 1.0)
    return 1 - (1 - p) ** 3


def ease_in_out(p: float) -> float:
    p = min(max(p, 0.0), 1.0)
    return p * p * (3 - 2 * p)


def dim_amount(t: float, dur: float) -> float:
    """0 -> 1 as the picture dims after the punch; 1 -> 0 over the last OUT_S."""
    up = ease_in_out((t - DIM_AT_S) / DIM_S)
    down = 1.0 - ease_in_out((t - (dur - OUT_S)) / OUT_S)
    return min(up, down)


def reveal_map(h: int, w: int, seed: int, rtl: bool = True):
    """Per pixel, when (0..1 of the draw time) the marker reaches it: a slanted, wobbly front that sweeps from the right for Arabic."""
    import numpy as np
    from PIL import Image
    rng = np.random.default_rng(seed)
    small = rng.random((max(2, h // 18), max(2, w // 18))).astype(np.float32)
    noise = np.asarray(Image.fromarray((small * 255).astype("uint8")).resize((w, h), Image.BICUBIC), np.float32) / 255.0
    x = np.linspace(0, 1, w, dtype=np.float32)[None, :]
    x = 1.0 - x if rtl else x
    y = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    s = 0.72 * x + 0.16 * y + 0.12 * noise
    return s / 1.0     # 0..1 (0.72 + 0.16 + 0.12)


def reveal_alpha(smap, p: float, soft: float = 0.07):
    import numpy as np
    return np.clip((p * (1.0 + soft) - smap) / soft, 0.0, 1.0)


def layer_progress(t: float, at: float, dur: float) -> float:
    return min(max((t - at) / dur, 0.0), 1.0)


def pick_layout(sil_small, block_alpha_small, scale: int, x_range, y_range, step: int = 20):
    """Where the graffiti block goes: the (left, top) on the canvas that keeps the most text uncovered by the character (the text is painted behind them).
    `sil_small` and `block_alpha_small` are the silhouette and the block's alpha at 1/scale of the canvas. Returns (left, top, visible_share)."""
    import numpy as np
    bh, bw = block_alpha_small.shape
    tot = float(block_alpha_small.sum()) or 1.0
    best = None
    sh, sw = sil_small.shape
    for top in range(y_range[0], y_range[1] + 1, step):
        for left in range(x_range[0], x_range[1] + 1, step):
            ty, lx = top // scale, left // scale
            if ty + bh > sh or lx + bw > sw:
                continue
            occ = float((sil_small[ty:ty + bh, lx:lx + bw] * block_alpha_small).sum()) / tot
            score = occ + 0.00025 * (top - y_range[0]) + 0.00008 * abs(left + bw * scale / 2 - W / 2)
            if best is None or score < best[0]:
                best = (score, left, top, 1.0 - occ)
    if best is None:
        raise ValueError("graffiti block does not fit the canvas")
    return best[1], best[2], best[3]


def pick_layout_parts(sil_small, parts, bw: int, bh: int, scale: int, x_range, y_range, step: int = 12):
    """Like pick_layout, but the block is several parts (each a small alpha with its own offset inside the block) and the place is chosen so that the
    WORST part is covered least: the name must stay readable AND so must the line. parts = [(alpha_small, ox_small, oy_small)]. Returns (left, top, worst_visible_share)."""
    import numpy as np
    sh, sw = sil_small.shape
    tots = [float(a.sum()) or 1.0 for a, _, _ in parts]
    best = None
    for top in range(y_range[0], y_range[1] + 1, step):
        for left in range(x_range[0], x_range[1] + 1, step):
            ty, lx = top // scale, left // scale
            if ty + bh > sh or lx + bw > sw:
                continue
            occs = []
            for (a, ox, oy), tot in zip(parts, tots):
                h, w = a.shape
                occs.append(float((sil_small[ty + oy:ty + oy + h, lx + ox:lx + ox + w] * a).sum()) / tot)
            worst = max(occs)
            score = worst + 0.15 * (sum(occs) / len(occs)) + 0.0002 * (top - y_range[0]) + 0.00006 * abs(left + bw * scale / 2 - W / 2)
            if best is None or score < best[0]:
                best = (score, left, top, 1.0 - worst)
    if best is None:
        raise ValueError("graffiti block does not fit the canvas")
    return best[1], best[2], best[3]


# ------------------------------------------------------------------ resolve (a card-kind calm description)
def resolve(p: dict) -> dict:
    """Template parameters -> the calm description of an intro_freeze beat. Raises calm.CalmError on a bad parameter (never guesses)."""
    from calm import CalmError
    allowed = {"id", "duration", "set", "template", "seed", "character", "name", "tag", "source", "hold", "accent"}
    unknown = [k for k in p if k not in allowed]
    if unknown:
        raise CalmError("CALM-PARAM", f"intro_freeze does not take {', '.join(unknown)} (takes character, name, tag, source, hold, duration, accent)")
    miss = [k for k in ("character", "name", "tag", "source") if not str(p.get(k, "")).strip()]
    if miss:
        raise CalmError("CALM-PARAM", f"intro_freeze needs {', '.join(miss)}")
    for k in ("name", "tag"):
        v = str(p[k]).strip()
        if has_tashkeel(v):
            raise CalmError("CALM-TASHKEEL", f"{k} carries tashkeel ({', '.join(tashkeel_chars(v))}): nothing people see carries tashkeel (CLAUDE.md)")
    name, tag = str(p["name"]).strip(), str(p["tag"]).strip()
    if len(name.split()) > NAME_WORDS_MAX or len(tag.split()) > TAG_WORDS_MAX:
        raise CalmError("CALM-PARAM", f"graffiti is short: a name of at most {NAME_WORDS_MAX} words and a line of at most {TAG_WORDS_MAX}")
    words = len(name.split()) + len(tag.split())
    dur = round(float(p.get("duration") or min_duration(words)) * FPS) / FPS
    if dur < min_duration(words) - 1e-9:
        raise CalmError("CALM-DURATION", f"{dur:.2f} s is too short for {words} words: the text needs {min_duration(words):.2f} s (drawn by {TEXT_DONE_S:.2f} s, read for {read_budget(words):.2f} s, colour back in {OUT_S} s)")
    if not MIN_S <= dur <= MAX_S:
        raise CalmError("CALM-DURATION", f"{dur} s outside {MIN_S}..{MAX_S} s")
    import re
    sid = re.sub(r"[^a-z0-9]+", "-", str(p.get("id") or "calm-intro").lower()).strip("-")
    return {"schema": "calm-shot/1", "format": "calm", "kind": "card", "template": "intro_freeze", "id": sid, "fps": FPS, "duration_s": dur, "canvas": [W, H],
            "card": {"template": "intro_freeze", "text": {"name": name, "tag": tag}, "accent": str(p.get("accent") or ACCENT), "backdrop": None, "object": None, "push_pct": 0.0},
            "intro": {"character": str(p["character"]).strip(), "source": str(p["source"]).strip(), "hold": float(p.get("hold") or 0.0), "words": words,
                      "seed": int(p.get("seed") or sum(ord(c) for c in sid))},
            "set": None, "actors": [], "camera": {"move": "freeze", "move_pct": 0.0}}


# ------------------------------------------------------------------ the shot folder
def write_shot(c: dict, sd: Path) -> list[Path]:
    sd = Path(sd)
    sd.mkdir(parents=True, exist_ok=True)
    c = {**c, "id": sd.name}
    shot = {"id": sd.name, "title": f"{sd.name}: calm intro freeze ({c['intro']['character']})", "kind": "card", "format": "calm", "fps": FPS, "duration_s": c["duration_s"], "canvas": [W, H],
            "card": c["card"], "intro": c["intro"], "scene_files": [], "library": []}
    (sd / "calm.json").write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
    (sd / "shot.json").write_text(json.dumps(shot, ensure_ascii=False, indent=1), encoding="utf-8")
    return [sd / "calm.json", sd / "shot.json"]


def _shot(sd: Path) -> dict:
    return json.loads((sd / "shot.json").read_text(encoding="utf-8"))


def _ffmpeg(args, check=True, **kw):
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", *map(str, args)], capture_output=True, **kw)
    if check and r.returncode != 0:
        raise StageFail("INTRO-ENCODE", (r.stderr or b"").decode("utf-8", "replace")[-300:])
    return r


def _frames_in(video: Path) -> int:
    r = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(video)], capture_output=True, text=True)
    return int(r.stdout.strip() or 0)


def source_frame(sh: dict) -> dict:
    """Which frame of the source shot is frozen: the last frame the timeline shows (the shot minus its deliberate hold), on the grid of the masks."""
    intro = sh["intro"]
    src = ROOT / intro["source"]
    vid = src / "out" / f"{src.name}.mp4"
    if not vid.is_file():
        raise StageFail("INTRO-SOURCE", f"{vid} is not rendered: the scene that introduces the character is recorded before its intro")
    n = _frames_in(vid)
    last = max(0, n - round(float(intro.get("hold") or 0.0) * FPS) - 1)
    idx = (last // MASK_STEP) * MASK_STEP
    mdir = src / "out" / "masks" / "line" / intro["character"]
    if not (mdir / f"{idx:04d}.png").is_file():
        have = sorted(int(q.stem) for q in mdir.glob("*.png")) if mdir.is_dir() else []
        cand = [i for i in have if i <= last]
        if not cand:
            raise StageFail("INTRO-MASK", f"no line mask for {intro['character']} in {mdir}")
        idx = cand[-1]
    return {"video": str(vid), "frames": n, "last_visible": last, "frame": idx, "mask": str(mdir / f"{idx:04d}.png")}


# ------------------------------------------------------------------ text layers (Chrome: Thmanyah, shaped Arabic)
def font_css() -> str:
    out = []
    for fam, wt, f in (("thmanyahsans", 900, "Black"), ("thmanyahserifdisplay", 900, "Black")):
        out.append(f'@font-face{{font-family:"{fam}";src:url("{(FONTS / f"{fam}-{f}.woff2").as_uri()}") format("woff2");font-weight:{wt}}}')
    return "".join(out)


def text_page(name: str, tag: str, accent: str) -> str:
    esc = lambda t: t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    css = (f"{font_css()}html,body{{margin:0;background:transparent;width:{W}px;height:{H}px;overflow:hidden}}"
           f".g{{position:absolute;white-space:nowrap;direction:rtl;font-weight:900;line-height:1.2;padding:26px 40px;paint-order:stroke fill}}"
           f"#name{{left:60px;top:120px;font-family:'thmanyahserifdisplay';font-size:200px;color:#fff3d2;-webkit-text-stroke:13px #14110d;text-shadow:11px 10px 0 {accent};transform:rotate(-4deg)}}"
           f"#tag{{left:60px;top:900px;font-family:'thmanyahsans';font-size:68px;color:{accent};-webkit-text-stroke:9px #14110d;text-shadow:5px 5px 0 #14110d;transform:rotate(-2deg);white-space:normal;max-width:430px;text-align:center;line-height:1.2;padding:24px 40px}}")
    return f'<!doctype html><html lang="ar" dir="rtl"><meta charset="utf-8"><style>{css}</style><body><div class="g" id="name">{esc(name)}</div><div class="g" id="tag">{esc(tag)}</div></body></html>'


def render_text_layers(sd: Path, name: str, tag: str, accent: str) -> dict:
    """Screenshot the name and the line as transparent PNGs; returns {fonts_ok, layers: {name|tag: {png, w, h}}, boxes}. A missing Thmanyah face refuses."""
    from playwright.sync_api import sync_playwright
    need = [f for f in ("thmanyahsans-Black.woff2", "thmanyahserifdisplay-Black.woff2") if not (FONTS / f).is_file()]
    if need:
        raise StageFail("CARD-FONT", f"Thmanyah font file(s) missing in assets/fonts/: {', '.join(need)} (git-ignored; Cairo or any fallback is banned)")
    work = sd / "build"
    out = sd / "out" / "layers"
    out.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    page = work / "page.html"
    page.write_text(text_page(name, tag, accent), encoding="utf-8")
    res: dict = {"layers": {}, "boxes": []}
    with sync_playwright() as pw:
        b = pw.chromium.launch(args=["--enable-gpu-rasterization", "--ignore-gpu-blocklist", "--allow-file-access-from-files"])
        try:
            pg = b.new_page(viewport={"width": W, "height": H})
            pg.goto(page.as_uri())
            specs = ("900 40px thmanyahsans", "900 40px thmanyahserifdisplay")
            pg.evaluate("Promise.all(%s.map(s => document.fonts.load(s, 'هدى'))).then(() => 1)" % json.dumps(list(specs)))
            res["fonts_ok"] = all(pg.evaluate(f"document.fonts.check('{s}')") for s in specs)
            for k in ("name", "tag"):
                el = pg.locator(f"#{k}")
                png = out / f"{k}.png"
                el.screenshot(path=str(png), omit_background=True)
                bb = el.bounding_box()
                res["layers"][k] = {"png": str(png), "w": round(bb["width"]), "h": round(bb["height"])}
                res["boxes"].append(pg.evaluate("""(id) => { const e = document.getElementById(id), cs = getComputedStyle(e);
                    return {text: e.textContent, font_px: parseFloat(cs.fontSize), family: cs.fontFamily, color: cs.color}; }""", k))
        finally:
            b.close()
    return res


def marker_layers(name_w: int, accent: str, seed: int, out: Path) -> dict:
    """The hand-drawn extras, drawn with PIL on a 3x canvas and brought down (anti-aliased): a wobbly marker underline and a few tick marks. -> {underline|ticks: {png, w, h}}"""
    import numpy as np
    from PIL import Image, ImageDraw
    rng = np.random.default_rng(seed + 7)
    col = tuple(int(accent[i:i + 2], 16) for i in (1, 3, 5)) + (255,)
    dark = (20, 17, 13, 255)
    S = 3
    uw, uh = int(name_w * 0.86), 46
    im = Image.new("RGBA", (uw * S, uh * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    xs = np.linspace(8, uw - 8, 14)
    ys = uh / 2 + np.cumsum(rng.normal(0, 2.4, 14)) - np.linspace(0, 6, 14)
    pts = [(float(x) * S, float(np.clip(y, 8, uh - 8)) * S) for x, y in zip(xs, ys)]
    d.line(pts, fill=dark, width=24 * S, joint="curve")
    d.line(pts, fill=col, width=13 * S, joint="curve")
    under = im.resize((uw, uh), Image.LANCZOS)
    tw, th = 200, 150
    im2 = Image.new("RGBA", (tw * S, th * S), (0, 0, 0, 0))
    d2 = ImageDraw.Draw(im2)
    for ang, r0, r1 in ((-28, 40, 118), (-8, 48, 132), (14, 40, 112)):
        a = math.radians(ang)
        p0 = ((tw - 30 - r0 * math.cos(a)) * S, (th - 20 - r0 * math.sin(a)) * S)
        p1 = ((tw - 30 - r1 * math.cos(a)) * S, (th - 20 - r1 * math.sin(a)) * S)
        d2.line([p0, p1], fill=dark, width=18 * S)
        d2.line([p0, p1], fill=col, width=9 * S)
    ticks = im2.resize((tw, th), Image.LANCZOS)
    out.mkdir(parents=True, exist_ok=True)
    res = {}
    for k, im_ in (("underline", under), ("ticks", ticks)):
        p = out / f"{k}.png"
        im_.save(p)
        res[k] = {"png": str(p), "w": im_.width, "h": im_.height}
    return res


def _small(path, sc):
    import numpy as np
    from PIL import Image
    a = np.asarray(Image.open(path).convert("RGBA"))[..., 3]
    return np.asarray(Image.fromarray(a).resize((max(1, a.shape[1] // sc), max(1, a.shape[0] // sc)), Image.BILINEAR), np.float32) / 255.0


def build_layout(sd: Path, sil_canvas, layers: dict, seed: int) -> dict:
    """Place the graffiti: block A (the name, its marker underline, the ticks) and block B (the line) each where the character hides the least of them;
    B avoids A. Returns the layout (canvas pixels) and the visible share of the WORST layer."""
    import numpy as np
    from PIL import Image
    nm, tg, ul, tk = layers["name"], layers["tag"], layers["underline"], layers["ticks"]
    sc = 4
    sil_s = np.asarray(Image.fromarray((np.asarray(sil_canvas) * 255).astype("uint8")).resize((W // sc, H // sc), Image.BILINEAR), np.float32) / 255.0
    aw = max(nm["w"], ul["w"]) + tk["w"] // 2
    ah = nm["h"] + ul["h"] - 38
    a_parts = [("name", (aw - nm["w"]) // 2 - tk["w"] // 4, 0), ("underline", (aw - ul["w"]) // 2 - tk["w"] // 4, nm["h"] - 38), ("ticks", aw - tk["w"], -10)]
    pa = [(_small(layers[k]["png"], sc), max(0, ox) // sc, (oy + 10) // sc) for k, ox, oy in a_parts if k != "ticks"]
    al, at, avis = pick_layout_parts(sil_s, pa, aw // sc + 1, (ah + 20) // sc + 1, sc, (SAFE["x0"], max(SAFE["x0"], SAFE["x1"] - aw)), (SAFE["y0"] + 4, 560), step=12)
    occ = sil_s.copy()                                   # B keeps off A as well as off the character
    occ[at // sc:(at + ah + 20) // sc + 1, al // sc:(al + aw) // sc + 1] = 1.0
    tsmall = _small(tg["png"], sc)
    bl, bt, bvis = pick_layout(occ, tsmall, sc, (SAFE["x0"], max(SAFE["x0"], SAFE["x1"] - tg["w"])), (SAFE["y0"] + 4, 820), step=12)
    placed = [{"layer": k, "x": al + ox, "y": at + oy + 10} for k, ox, oy in a_parts] + [{"layer": "tag", "x": bl, "y": bt}]
    boxes = [{"layer": p["layer"], "x0": p["x"], "y0": p["y"], "x1": p["x"] + layers[p["layer"]]["w"], "y1": p["y"] + layers[p["layer"]]["h"]} for p in placed]
    # the visible share is measured against the character alone (B's penalty for overlapping A is a placement rule, not hiding)
    tv = 1.0 - float((sil_s[bt // sc:bt // sc + tsmall.shape[0], bl // sc:bl // sc + tsmall.shape[1]] * tsmall[:sil_s.shape[0] - bt // sc, :sil_s.shape[1] - bl // sc]).sum()) / (float(tsmall.sum()) or 1.0)
    return {"placed": placed, "boxes": boxes, "block": {"x": al, "y": at, "w": aw, "h": ah}, "tag_at": {"x": bl, "y": bt}, "visible_name": round(float(avis), 4), "visible_tag": round(tv, 4),
            "visible_share": round(float(min(avis, tv)), 4), "seed": seed}


# ------------------------------------------------------------------ the stages
def s_ok(sd: Path):
    return {"card": True}


def s_spec(sd: Path):
    sh = _shot(sd)
    bad = [k for k, v in sh["card"]["text"].items() if has_tashkeel(v)]
    if bad:
        raise StageFail("CARD-TASHKEEL", f"{', '.join(bad)} carry tashkeel")
    words = sh["intro"]["words"]
    if sh["duration_s"] + 1e-9 < min_duration(words):
        raise StageFail("INTRO-READ", f"{sh['duration_s']} s is shorter than the {min_duration(words):.2f} s the text needs")
    (sd / "shot-spec.json").write_text(json.dumps({"format": "calm", "kind": "card", "template": "intro_freeze", "text": sh["card"]["text"], "duration_s": sh["duration_s"], "intro": sh["intro"]},
                                                  ensure_ascii=False, indent=1), encoding="utf-8")
    return {"words": words}


def s_build(sd: Path):
    sh = _shot(sd)
    work = sd / "build"
    work.mkdir(exist_ok=True)
    (work / "page.html").write_text(text_page(sh["card"]["text"]["name"], sh["card"]["text"]["tag"], sh["card"]["accent"]), encoding="utf-8")
    (work / "diag.json").write_text(json.dumps({"frames": round(sh["fps"] * sh["duration_s"]), "kind": "card", "template": "intro_freeze"}), encoding="utf-8")
    return {"page": True}


def s_trace(sd: Path):
    """Grab the frozen frame and the character's mask, cut the silhouette, render the text, lay the graffiti out, and write out/intro-measure.json."""
    import numpy as np
    from PIL import Image
    sh = _shot(sd)
    src = source_frame(sh)
    out = sd / "out"
    out.mkdir(exist_ok=True)
    _ffmpeg(["-i", src["video"], "-vf", f"select=eq(n\\,{src['frame']})", "-frames:v", 1, "-vsync", "0", out / "freeze.png"])
    if not (out / "freeze.png").is_file():
        raise StageFail("INTRO-SOURCE", f"could not read frame {src['frame']} of {src['video']}")
    m = np.asarray(Image.open(src["mask"]).convert("RGBA"))[..., 3]
    sil = silhouette(m)
    sc = to_canvas(sil)
    rows = np.where((sc > 0.5).any(axis=1))[0]
    dy = int(min(SHIFT_MAX, max(0, HEAD_ROOM_Y - int(rows.min())))) if rows.size else 0
    if dy:                                   # a slow tilt down in the freeze: the picture slides down, its top edge is stretched (it is dimmed), so the graffiti has the band above the head
        fr = np.asarray(Image.open(out / "freeze.png").convert("RGB"))
        Image.fromarray(shift_down(fr, dy)).save(out / "freeze.png")
        sc = shift_down(sc, dy, fill_edge=False)
    Image.fromarray((sc * 255).astype("uint8")).save(out / "silhouette.png")
    share = float((sc > 0.5).mean())
    seed = int(sh["intro"]["seed"])
    lay = render_text_layers(sd, sh["card"]["text"]["name"], sh["card"]["text"]["tag"], sh["card"]["accent"])
    lay["layers"].update(marker_layers(lay["layers"]["name"]["w"], sh["card"]["accent"], seed, out / "layers"))
    layout = build_layout(sd, sc, lay["layers"], seed)
    words = sh["intro"]["words"]
    boxes = [{**b, "inside_safe": b["x0"] >= SAFE["x0"] - 1 and b["x1"] <= SAFE["x1"] + 1 and b["y0"] >= SAFE["y0"] - 1 and b["y1"] <= SAFE["y1"] + 1} for b in layout["boxes"]]
    meas = {"shift_dy": dy, "source": src, "silhouette_share": round(share, 4), "fonts_ok": lay["fonts_ok"], "text_boxes": lay["boxes"], "placed_boxes": boxes, "layout": layout,
            "layers": lay["layers"], "visible_share": layout["visible_share"], "words": words, "duration_s": sh["duration_s"], "text_done_s": TEXT_DONE_S,
            "read_budget_s": round(read_budget(words), 3), "full_read_window_s": round(sh["duration_s"] - OUT_S - TEXT_DONE_S, 3), "texts": sh["card"]["text"]}
    (out / "intro-measure.json").write_text(json.dumps(meas, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"silhouette_share": meas["silhouette_share"], "visible_share": meas["visible_share"], "frame": src["frame"]}


def motes(seed: int, n: int = 46):
    import numpy as np
    rng = np.random.default_rng(seed + 31)
    return [{"x": float(rng.uniform(0, W)), "y": float(rng.uniform(0, H)), "r": float(rng.uniform(2.0, 5.5)), "vy": float(rng.uniform(14, 46)), "ph": float(rng.uniform(0, 6.28)),
             "amp": float(rng.uniform(6, 22)), "a": float(rng.uniform(0.10, 0.28))} for _ in range(n)]


def compose_frames(sd: Path, sh: dict, meas: dict):
    """Yield the clip's frames as uint8 H x W x 3 arrays."""
    import numpy as np
    from PIL import Image
    n = round(sh["fps"] * sh["duration_s"])
    dur = n / FPS
    seed = int(sh["intro"]["seed"])
    full = np.asarray(Image.open(sd / "out" / "freeze.png").convert("RGB").resize((W, H), Image.BICUBIC), np.float32)
    sil = np.asarray(Image.open(sd / "out" / "silhouette.png"), np.float32) / 255.0
    dim = dimmed(full)
    rim, halo = glow_fields(sil)
    lay = meas["layers"]
    place = {p["layer"]: p for p in meas["layout"]["placed"]}
    timing = {"name": (NAME_AT_S, NAME_S), "underline": (NAME_AT_S + NAME_S, LINE_S), "tag": (TAG_AT_S, TAG_S), "ticks": (TICKS_AT_S, TICKS_S)}
    rgba = {k: np.asarray(Image.open(lay[k]["png"]).convert("RGBA"), np.float32) for k in timing}
    smap = {k: reveal_map(rgba[k].shape[0], rgba[k].shape[1], seed + i) for i, k in enumerate(timing)}
    mote_list = motes(seed)
    rng = np.random.default_rng(seed + 99)
    boil = [(int(rng.integers(-2, 3)), int(rng.integers(-2, 3))) for _ in range(int(dur * 12) + 2)]
    grey = np.array(GREY, np.float32)
    for f in range(n):
        t = f / FPS
        d = dim_amount(t, dur)
        base = full + (dim - full) * d
        if d > 0.02:                                   # drifting dust in the dimmed room
            for m_ in mote_list:
                y = (m_["y"] - m_["vy"] * t) % H
                x = m_["x"] + m_["amp"] * math.sin(m_["ph"] + t * 0.9)
                r = int(m_["r"] * 2)
                x0, y0 = int(x) - r, int(y) - r
                if 0 <= x0 and x0 + 2 * r < W and 0 <= y0 and y0 + 2 * r < H:
                    yy, xx = np.mgrid[-r:r, -r:r]
                    g = np.exp(-(xx ** 2 + yy ** 2) / (2 * (m_["r"] * 0.55) ** 2))[..., None] * m_["a"] * d
                    patch = base[y0:y0 + 2 * r, x0:x0 + 2 * r]
                    base[y0:y0 + 2 * r, x0:x0 + 2 * r] = patch + (np.array([235.0, 232.0, 222.0], np.float32) - patch) * g
        fade_text = 1.0 - ease_in_out((t - (dur - OUT_S)) / (OUT_S * 0.75))
        bx, by = boil[int(t * 12)]
        for k in ("name", "underline", "ticks", "tag"):
            at, ln = timing[k]
            p = layer_progress(t, at, ln)
            if p <= 0:
                continue
            a = reveal_alpha(smap[k], p) * rgba[k][..., 3] / 255.0 * fade_text
            px, py = place[k]["x"] + bx, place[k]["y"] + by
            h_, w_ = a.shape
            y0, x0 = max(py, 0), max(px, 0)
            y1, x1 = min(py + h_, H), min(px + w_, W)
            if y1 <= y0 or x1 <= x0:
                continue
            aa = a[y0 - py:y1 - py, x0 - px:x1 - px, None]
            col = rgba[k][y0 - py:y1 - py, x0 - px:x1 - px, :3]
            base[y0:y1, x0:x1] = base[y0:y1, x0:x1] * (1 - aa) + col * aa
        m3 = sil[..., None]
        base = base + (full * 1.04 - base) * m3                    # the character, in front of the graffiti, in full colour
        breath = 1.0 + 0.10 * math.sin(2 * math.pi * t / 1.7)
        ga = np.clip((rim * 0.95 + halo) * d * breath, 0, 0.92)[..., None]
        base = base * (1 - ga) + grey * ga
        img = np.clip(base, 0, 255)
        if t < PUNCH_S:                                              # the dramatic entry: a zoom punch and a short shake
            p = t / PUNCH_S
            z = 1.0 + 0.10 * (1 - ease_out(p))
            sx = (7.0 * (1 - p) * math.sin(t * 2 * math.pi * 14)) if t < 0.30 else 0.0
            im = Image.fromarray(img.astype("uint8"))
            cx, cy = W / 2, H * 0.46
            im = im.transform((W, H), Image.AFFINE, (1 / z, 0, cx - cx / z + sx, 0, 1 / z, cy - cy / z), resample=Image.BILINEAR)
            img = np.asarray(im, np.float32)
        if t < FLASH_S:
            fa = (1 - t / FLASH_S) ** 2 * 0.85
            img = img + (255.0 - img) * fa
        yield np.clip(img, 0, 255).astype("uint8")


def s_record(sd: Path):
    sh = _shot(sd)
    meas = json.loads((sd / "out" / "intro-measure.json").read_text(encoding="utf-8"))
    n = round(sh["fps"] * sh["duration_s"])
    out = sd / "out" / f"{sd.name}.mp4"
    tmp = out.with_suffix(".part.mp4")
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-frames:v", str(n), "-r", str(FPS),
           "-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "19", "-b:v", "0", "-pix_fmt", "yuv420p", "-threads", "2", str(tmp)]
    pr = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for fr in compose_frames(sd, sh, meas):
            pr.stdin.write(fr.tobytes())
        pr.stdin.close()
        err = pr.stderr.read().decode("utf-8", "replace")
        if pr.wait() != 0:
            raise StageFail("INTRO-ENCODE", err[-300:])
    except BrokenPipeError:
        raise StageFail("INTRO-ENCODE", pr.stderr.read().decode("utf-8", "replace")[-300:])
    finally:
        if pr.poll() is None:
            pr.kill()
    os.replace(tmp, out)
    r = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=codec_name,width,height,r_frame_rate,nb_read_frames,pix_fmt", "-of", "json", str(out)],
                       capture_output=True, text=True)
    v = json.loads(r.stdout)["streams"][0]
    bad = [k for k, ok in (("codec h264", v["codec_name"] == "h264"), (f"size {W}x{H}", (v["width"], v["height"]) == (W, H)), ("24 fps", v["r_frame_rate"] == "24/1"),
                           (f"{n} frames", int(v["nb_read_frames"]) == n), ("yuv420p", v["pix_fmt"] == "yuv420p")) if not ok]
    if bad:
        raise StageFail("RECORD-FORMAT", f"intro video {v} fails: {bad}")
    (sd / "out" / f"{sd.name}.encode.json").write_text(json.dumps({"frames": n, "ffmpeg_exit": 0}), encoding="utf-8")
    return {"frames": n}


def grab(video: Path, t: float):
    import numpy as np
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True)
    if len(r.stdout) != W * H * 3:
        raise StageFail("INTRO-FRAME", f"could not read a frame at {t:.2f} s of {video}")
    return np.frombuffer(r.stdout, np.uint8).reshape(H, W, 3).astype(np.float32)


def video_problems(a, b, sil) -> tuple[list[str], dict]:
    """INTRO-ISOLATE and INTRO-FROZEN on two held frames of the recorded clip (a earlier, b later) and the silhouette."""
    import numpy as np
    from scipy import ndimage as ndi
    f: list[str] = []
    inside = sil > 0.9
    core = ndi.binary_erosion(inside, iterations=6)
    outside = ndi.binary_dilation(inside, iterations=40) == 0
    luma = lambda x: (x * np.array([0.299, 0.587, 0.114], np.float32)).sum(axis=2)
    sat = lambda x: x.max(axis=2) - x.min(axis=2)
    li, lo = float(luma(b)[core].mean()), float(np.median(luma(b)[outside]))      # the room's median: the graffiti's bright strokes are not "the rest of the frame"
    si, so = float(sat(b)[core].mean()), float(np.median(sat(b)[outside]))
    d = ndi.distance_transform_edt(~inside)
    ring = (d >= 2) & (d <= 8)
    beyond = (d >= 30) & (d <= 70)
    rim_gain = float(luma(b)[ring].mean() - np.median(luma(b)[beyond])) if ring.any() and beyond.any() else 0.0
    frozen = float(np.abs(a[core] - b[core]).mean())
    m = {"luma_in": round(li, 1), "luma_out": round(lo, 1), "sat_in": round(si, 1), "sat_out": round(so, 1), "rim_gain": round(rim_gain, 1), "frozen_diff": round(frozen, 2)}
    if lo > DIM_LUMA * li:
        f.append(f"INTRO-ISOLATE the rest of the frame is at {lo / max(li, 1e-6):.2f} of the character's brightness (needs <= {DIM_LUMA}): it is not dimmed enough to isolate them")
    if so > DIM_SAT * max(si, 1e-6):
        f.append(f"INTRO-ISOLATE the rest of the frame keeps {so / max(si, 1e-6):.2f} of the character's colour (needs <= {DIM_SAT}): it is not desaturated")
    if rim_gain < RIM_GAIN:
        f.append(f"INTRO-ISOLATE the grey rim is only {rim_gain:.0f} levels brighter than the dimmed picture beside it (needs >= {RIM_GAIN:g})")
    if frozen > FROZEN_MAX:
        f.append(f"INTRO-FROZEN the character's pixels changed by {frozen:.1f} levels between two held frames (needs <= {FROZEN_MAX:g}): the frame is not frozen")
    return f, m


def measure_problems(meas: dict, fonts_ok: bool | None = None) -> list[str]:
    """INTRO-TEXT, INTRO-READ, INTRO-LEN and the silhouette share, on the numbers of out/intro-measure.json."""
    f: list[str] = []
    ok_font = meas.get("fonts_ok") if fonts_ok is None else fonts_ok
    if not ok_font:
        f.append("INTRO-TEXT a Thmanyah face did not load: refusing to render with a fallback")
    for b in meas.get("text_boxes", []):
        if "thmanyah" not in str(b.get("family", "")).lower():
            f.append(f"INTRO-TEXT '{str(b.get('text', ''))[:20]}' is set in {b.get('family')}, not Thmanyah")
    for k, v in (meas.get("texts") or {}).items():
        if has_tashkeel(v):
            f.append(f"INTRO-TEXT {k} carries tashkeel")
    for b in meas.get("placed_boxes", []):
        if not b.get("inside_safe", True):
            f.append(f"INTRO-TEXT the {b['layer']} layer ({b['x0']},{b['y0']},{b['x1']},{b['y1']}) leaves the Reels safe area {SAFE}")
    if meas.get("visible_share", 0) < VISIBLE_MIN:
        f.append(f"INTRO-TEXT only {meas.get('visible_share', 0):.2f} of the graffiti is visible beside the character (needs >= {VISIBLE_MIN}): it is hidden behind them")
    share = meas.get("silhouette_share", 0)
    if not SIL_SHARE[0] <= share <= SIL_SHARE[1]:
        f.append(f"INTRO-ISOLATE the character's silhouette is {share:.3f} of the frame, outside {SIL_SHARE}: the mask did not close around them")
    if meas.get("full_read_window_s", 0) + 1e-6 < meas.get("read_budget_s", 0):
        f.append(f"INTRO-READ the text is fully drawn for {meas.get('full_read_window_s')} s but {meas.get('words')} words need {meas.get('read_budget_s')} s ({CS.READ_BASE_S} s + {CS.READ_PER_WORD_S} s a word)")
    d = meas.get("duration_s", 0)
    if not MIN_S - 1e-9 <= d <= MAX_S + 1e-9 or abs(d * FPS - round(d * FPS)) > 1e-6:
        f.append(f"INTRO-LEN {d} s is outside {MIN_S}..{MAX_S} s or off the {FPS} fps grid")
    return f


def s_gate(sd: Path):
    import numpy as np
    from PIL import Image
    sh = _shot(sd)
    out = sd / "out"
    meas = json.loads((out / "intro-measure.json").read_text(encoding="utf-8"))
    vid = out / f"{sd.name}.mp4"
    dur = sh["duration_s"]
    sil = np.asarray(Image.open(out / "silhouette.png"), np.float32) / 255.0
    fails = measure_problems(meas)
    t1, t2 = TEXT_DONE_S + 0.1, dur - OUT_S - 0.15
    vf, vm = video_problems(grab(vid, t1), grab(vid, t2), sil)
    fails += vf
    meas["video"] = vm
    meas["fails"] = fails
    meas["ok"] = not fails
    (out / "intro-measure.json").write_text(json.dumps(meas, ensure_ascii=False, indent=1), encoding="utf-8")
    (sd / "gate").mkdir(exist_ok=True)
    rep = {"shot": sd.name, "format": "calm", "kind": "card", "gates": {"intro": {"verdict": "FAIL" if fails else "PASS", "fail_ids": sorted({x.split(" ", 1)[0] for x in fails})}},
           "fails": [f"intro:{x.split(' ', 1)[0]}" for x in fails], "details": fails, "verdict": "FAIL" if fails else "PASS", "video": vm}
    (sd / "gate" / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    (sd / "gate" / "report.txt").write_text(f"gate report for {sd.name}: {rep['verdict']}\n" + "\n".join(fails) + "\n", encoding="utf-8")
    if fails:
        raise StageFail(fails[0].split(" ", 1)[0], "; ".join(fails[:4]))
    return {"intro": "PASS", **vm}


def s_review(sd: Path):
    vid = sd / "out" / f"{sd.name}.mp4"
    dur = _shot(sd)["duration_s"]
    (sd / "review").mkdir(exist_ok=True)
    for i, t in enumerate((0.1, 0.9, TEXT_DONE_S + 0.2, max(0.5, dur - 0.2))):
        _ffmpeg(["-ss", f"{t:.2f}", "-i", vid, "-frames:v", 1, "-vf", "scale=360:-1", sd / "review" / f"frame-{i}.png"])
    (sd / "review" / "index.json").write_text(json.dumps({"frames": {"tiles": 4}}), encoding="utf-8")
    return {"frames": 4}


def stages(sd: Path) -> list[Stage]:
    me = Path(__file__)
    code = [me, TOOLS / "arabic_display.py", TOOLS / "cap_sentence.py"]
    vid = lambda d: d / "out" / f"{d.name}.mp4"
    shot = lambda d: [d / "shot.json"]

    def source(d):     # the scene video and the character's masks decide whether a recorded intro is still current
        try:
            sh = _shot(d)
            src = ROOT / sh["intro"]["source"]
            return [src / "out" / f"{src.name}.mp4", src / "out" / "masks" / "line" / sh["intro"]["character"]]
        except (OSError, KeyError, ValueError):
            return []
    return [
        Stage("init", lambda d: [], lambda d: [d / "shot.json", d / "calm.json"], lambda d: {"template": "intro_freeze"}),
        Stage("catalogue", lambda d: shot(d), lambda d: [d / "shot.json"], s_ok),
        Stage("camera", lambda d: shot(d), lambda d: [d / "shot.json"], s_ok),
        Stage("spec", lambda d: shot(d) + code, lambda d: [d / "shot-spec.json"], s_spec),
        Stage("build", lambda d: shot(d) + code, lambda d: [d / "build" / "page.html", d / "build" / "diag.json"], s_build),
        Stage("trace", lambda d: shot(d) + code + source(d), lambda d: [d / "out" / "intro-measure.json", d / "out" / "freeze.png", d / "out" / "silhouette.png"], s_trace),
        Stage("record", lambda d: [d / "out" / "intro-measure.json", d / "out" / "freeze.png", d / "out" / "silhouette.png"] + code, lambda d: [vid(d), d / "out" / f"{d.name}.encode.json"], s_record),
        Stage("gate", lambda d: [vid(d), d / "out" / "intro-measure.json"] + code, lambda d: [d / "gate" / "report.json"], s_gate),
        Stage("review", lambda d: [vid(d)], lambda d: [d / "review" / "index.json"], s_review),
    ]


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] == "list":
        plan = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        have = {i.get("character"): i.get("id") for i in plan.get("intros", []) or []}
        for ch, sid in first_appearances(plan.get("scenes", [])).items():
            print(f"{ch:10s} first appears in {sid}: {'intro ' + have[ch] if ch in have else 'NO INTRO'}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
