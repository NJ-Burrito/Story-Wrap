# calm_compose.py part 1 of 3: executed into the calm_compose module namespace by calm_compose.py (a pure move).

import json
import math
import os
import re
import shutil
import subprocess
import sys
import wave
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("STORYWRAP_ROOT") or TOOLS.parent)
sys.path.insert(0, str(TOOLS))
from arabic_display import display_text, has_tashkeel   # noqa: E402
import gloss as G   # noqa: E402  (foreign-word glossary: CLAUDE.md "Gloss foreign words")
import cap_sentence as CS   # noqa: E402  (full-sentence captions with the spoken word highlighted: the owner 2026-10-25, C7)
import cap_face as CF   # noqa: E402  (captions never cover a face: the owner 2026-10-25, F-001)
import calm_cards as CC   # noqa: E402  (card texts and the ask rules shared with the plan checks: DESIGN.md 5.2)
import grid_poster as GP   # noqa: E402  (the grid poster: frame 0 of every episode and the cover every platform gets, R-501)
import watermark as WM   # noqa: E402  (the small NJ mark on every frame, the last compose step: the owner 2026-10-25)

FPS, W, H = 24, 1080, 1920
JOIN_S = 0.25                 # soft join (dissolve) between items: the recipe's joins are soft (hard cuts only on a stinger)
VOICE_LEAD_S = 0.2            # the narrator starts this long after the scene starts
PAD_S = 0.35                  # the scene outlives its line by this much (a breath before the next join); was 0.45: with the real Chatterbox takes (85 to 110 wpm, 78 s of speech) 0.45 put E01 calm at 92.7 s, over the 92 s Reel length and under the 0.85 voice share (qg_checks voice_share_min)
MIN_SCENE_S, MAX_SCENE_S = 2.5, 10.0   # 9.0 until format v2 (the owner 2026-10-28): dialogue scenes run up to about 10 s; a line is still at most 8 s aloud (SCRIPT-LINE-LEN) and the calm average shot-length band is unchanged
MAX_CHOICE_S = 16.0           # C4 (2026-10-25): the choice sequence lasts as long as the narrator takes to read the question, both choices and the hook. 14.0 until C13 (2026-10-25): the closing line now asks for the choice in words, a thought and a wish (a 6.5 s take), so the E01C sequence is 15.4 s; qg_checks CALM choice_last_s (20 s) still bounds it
CHOICE_TAIL_S = 0.7           # the sequence outlives the hook by this much before the follow card
CHOICE_GAP_S = 0.35           # a breath between the four choice lines
XD = 0.16                     # the crossfade of one cut inside the choice sequence's top half (a pop and a VFX at every cut)
TOP_H = 948                   # the top half of the choice sequence: above the accent bar of the card (y 948)
OBJ_CAP_Y = 760               # the narrator's caption is engraved on the brass plate (calm_cards object_card, plate y 560..1200)
MAX_CARD_S = 9.0              # calm_cards: no card lasts over 9 s; a narrated choice line that runs longer (L18 took 9.55 s on the real take) finishes over the follow card
CAP_WORDS_MAX = 3             # LEGACY word-by-word grouping (group_words); the plates are whole sentences since the owner 2026-10-25 (C7), see cap_sentence.py
CAP_FONT_PX = 104             # at 1080 wide: about 5.4 % of the height; qg_checks.CALM caption_font_px_min is 90
CAP_H1 = 152                  # height of a one-line plate (padding 12 + one 140 px line); plates are anchored by their BOTTOM edge so a second line grows upwards
CAP_PAD_X = 30                # horizontal padding of a plate
CAP_LINE_W_MAX = 900          # widest text line (px): the safe width 972 less the plate padding 60 and a 12 px slack
SAFE = (54, 270, 1026, 1250)  # x0, y0, x1, y1: Reels UI top 14 %, bottom 35 %, side 5 % (compose.py SAFE)
def measure_faces() -> list[str]:
    """Every face a plate is measured in must be loaded before it is measured: the sentence (900 weight, CAP_FONT_PX) AND the bracketed meaning (700 weight, GLOSS_FONT_PX).
    The inline-gloss test used to load the 900 weight only, so the meaning was measured in a fallback face while the 700 file was still loading (E02, 2026-10-27)."""
    return [f"900 {CAP_FONT_PX}px thmanyahsans", f"700 {GLOSS_FONT_PX}px thmanyahsans"]


GLOSS_INLINE_GAP_PX = 36      # space between the last row of a sentence and a meaning that sits beside it
GLOSS_FONT_PX = 64            # the bracketed meaning under a foreign word: smaller than the word, still large on a phone
CAP_Y = 1010                  # plate top, lower third inside the safe area
HUD_XY = (64, 280)
PLATE_BOTTOM_MAX = SAFE[3] + 100   # a moved plate's bottom edge stays inside the bound CALM-PLATE-SAFE has always allowed (the safe area's own bottom plus 100 px)
FACE_GRACE_S = 0.1            # F-001: a join dissolves two shots over JOIN_S; a plate that overlaps a shot for less than this (under three frames of a page-turn or a flash) is not asked to clear that shot's face
READ_HOLD_MARGIN_S = 0.05     # C12: the plan's pause is computed on the last clause from the take's length (no envelope), so it keeps this much slack
SOUND = json.loads((Path(__file__).resolve().parent / "sound_profile.json").read_text(encoding="utf-8"))   # the one sound profile (2026-10-26)
LOUD_I, LOUD_TP, LOUD_LRA = SOUND["master"]["lufs_target"], SOUND["master"]["true_peak_target_dbtp"], SOUND["master"]["calm_legacy_lra"]     # recipe: -14.1 LUFS measured on the delivered reels, LRA 3.1-4.2
VOICE_LUFS_NOTE = "voice about -16 LUFS under the master, bed -23 (nj-kit:bg-music)"
SILENCE_MAX_S = SOUND["silence"]["max_gap_s"]           # recipe 5: no silence gap over 0.6 s
LEN_MIN_S = 25.0              # sanity floor only. Length: whatever suits the story (owner, 2026-10-24 CLAUDE.md "Calm format"; he DECIDED 2026-10-25 to drop the upper cap: the gate's former 92 s ceiling is gone).
LEN_WARN_S = 92.0             # SOFT warning, never a fail: the harvested reels run 72-92 s (work/calm/m_*.json), so a longer episode is flagged for the Lead and the owner to confirm it is the story's length
# Scene count: the 12 harvested reels of 72 to 92 s run 12 to 26 shot changes a minute (work/calm/m_*.json: 11.8 to 26.5), that is 15 to 37 shots; the old bound of 14
# scenes + 4 cards sat under every one of them. The 20-scene ceiling existed only to keep an episode inside 92 s; with the length decision (above) it has no job and is gone.
SCENES_MIN = 4
# ---- Format v2 (the owner 2026-10-28, kb/rulebook.md R-420 on; replaces CALM-NARRATOR "the narrator carries the story"): characters carry the story in their own cast voices.
FORMAT_V2_FROM_EPISODE = 3    # E01 and E02 are published under the old format and stay valid; the v2 gates run from E03 on (episode_number: E01C counts as 1)
NARRATOR_SHARE_MAX = 0.25     # NARRATOR-SHARE: the narrator is at most this share of the placed voice TIME (CALM-VOICE-COVERAGE, 0.85 of the runtime by any speaker, is qg_checks.CALM voice_share_min)
NARRATOR_LINK_WORDS_MAX = 14  # a night link or the vote question line is short
NARRATOR_RECAP_WORDS_MAX = 22
DIALOGUE_MIN, DIALOGUE_MAX = 10, 15      # DIALOGUE-LINES: spoken character lines (speaker != narrator) per episode
EVENTS_MIN, EVENTS_MAX = 2, 5            # EVENTS: scenes with an `event` per episode
NO_ACTION_TEMPLATES = ("reaction_closeup", "hold_breathe")   # these show a face or a held pose: a reaction, never an action, so an event scene may not use them
RECAP_FROM_EPISODE = 2        # the owner 2026-10-25, plan-builder DATA: an episode recaps the audience's vote, so recaps start at E02; E01 has no vote and opens on its story (the bag) at 0 s. validate_plan, stage_plan, the shotlist and the gate all read this one number.
AR_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
AR_LETTER = re.compile("[ء-غف-يٱ]")
ENV = {**os.environ, "PYTHONUTF8": "1"}


class Fail(Exception):
    def __init__(self, cid, msg):
        super().__init__(f"FAIL [{cid}] {msg}")
        self.cid, self.msg = cid, msg


def read_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def write_json(p, obj):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def ff(args, check=True, log="error"):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-v", log, "-y", "-threads", "2", *map(str, args)], capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV)
    if check and r.returncode != 0:
        raise Fail("TOOL-ERROR", f"ffmpeg: {(r.stderr or '')[-400:]}")
    return r


def probe_dur(p) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)], capture_output=True, text=True)
    return float(r.stdout.strip())


def wav_seconds(p) -> float:
    with wave.open(str(p), "rb") as w:
        return w.getnframes() / w.getframerate()


def _graph_file(path: Path, fl: list) -> str:
    """A long filter graph goes through a file: ~190 caption plates plus the sfx cues outgrow the 32 k command line of Windows (WinError 206)."""
    Path(path).write_text((";" + chr(10)).join(fl), encoding="utf-8")
    return str(path)


def snap(t: float) -> float:
    return round(t * FPS) / FPS


def item_lines(it: dict) -> list[dict]:
    """Every narrated line of a timeline item as {line, voice_t0}: the item's own line plus `more_lines` (the choice sequence reads four)."""
    out = [{"line": it["line"], "voice_t0": it["voice_t0"]}] if it.get("line") else []
    return out + [{"line": m["line"], "voice_t0": m["voice_t0"]} for m in it.get("more_lines", [])]


def _spoken(items: list):
    for it in items:
        for ln in item_lines(it):
            yield it, ln


# ------------------------------------------------------------------ paths and the plan
class Ep:
    def __init__(self, ep: str, root: Path = ROOT):
        self.id, self.root = ep, Path(root)
        hits = sorted((self.root / "bible" / "series").glob(f"*/episodes/{ep}"))
        rehearsal = self.root / "work" / "rehearsal" / ep   # a throwaway rehearsal episode (never posted, git-ignored): same files, same stages
        if not hits and rehearsal.is_dir():
            hits = [rehearsal]
        if not hits:
            raise Fail("EP-NOT-FOUND", f"no episode folder bible/series/*/episodes/{ep} (or work/rehearsal/{ep})")
        self.dir = hits[0]
        self.series = self.dir.parents[1].name if self.dir.parent.name == "episodes" else "rehearsal"
        self.plan_p = self.dir / "calm-plan.json"
        self.script_p = self.dir / "script.json"
        self.work = self.root / "work" / "episodes" / ep   # the same folder ig.py publishes from (gate/report.json, heal/critic.json, episode.mp4)
        self.voice = self.root / "work" / "voice" / ep
        self.timeline_p, self.caps_p, self.hud_p = self.work / "timeline.json", self.work / "captions.json", self.work / "hud.json"
        self.mix, self.out, self.gate_p = self.work / "mix.wav", self.work / "episode.mp4", self.work / "gate" / "report.json"

    def shot(self, sid: str) -> Path:
        return self.root / "work" / "shots" / f"{self.id}-{sid}" / "out" / f"{self.id}-{sid}.mp4"

    def take(self, lid: str) -> Path:
        return self.voice / f"{lid}.trimmed.wav"


def episode_number(ep_id) -> int | None:
    """E01 -> 1, E01C (the calm rehearsal of E01) -> 1, E12 -> 12; anything not named E<number> -> None."""
    m = re.match(r"E(\d+)", str(ep_id or ""))
    return int(m.group(1)) if m else None


def recap_expected(plan: dict) -> bool:
    """RECAP_FROM_EPISODE: the recap card recaps a vote, so it exists from E02 on; E01 (and E01C) opens on the story. An episode with no E<number> id keeps its recap."""
    n = episode_number(plan.get("episode"))
    return n is None or n >= RECAP_FROM_EPISODE


# ---- DESIGN.md (research/algo, the owner 2026-10-25, section 9 approved): hook, story-so-far, series strip, open-question prompt, follow line, cover. They run from E02 on (algo_on):
# E01C v5 is approved and posted exactly as it is.
SERIES_NAME = "the series"
RECAP_MAX_S = 3.0             # the recap card's cap (qg_checks CALM recap_by_s, CALM-RECAP-FIRST): the spoken recap must fit it, the cap does not move
HOOK_S = 3.0                  # CALM-HOOK-3S: a voiced line or a declared story event starts before this
HOOK_PATTERNS = tuple(range(1, 11))   # the ten Arabic patterns of DESIGN.md section 3
HOOK_FIRST_PLATE_WORDS_MAX = 8
HOOK_BAD_START = ("مرحبا", "مرحبًا", "اهلا", "أهلا", "اهلاً", "أهلاً", "السلام", "سلام", "صباح", "هلا", "تابعوا", "تابع", "NJ", "إن جي")   # a greeting, «تابعوا» or a logo is never the hook (H A, "Do not use as the hook")
STRIP_S = 3.0                 # the series strip row stays on the HUD plate this long (DESIGN.md 2.3)
VARIANTS_MIN = 8              # PLAN-VARIANTS: other ways to type each choice, for vote.py (DESIGN.md 5.4 item 1)
NAME_CLITICS = "وفلبك"


def algo_on(plan: dict) -> bool:
    """The DESIGN.md additions (spoken recap hook, story-so-far name, series strip, open-question prompt, follow line, cover) start with the recap, at E02."""
    return recap_expected(plan)


def episode_label(plan: dict) -> str | None:
    """«الحلقة N · the series» (DESIGN.md 2.3): the strip's text and the recap card's tag. None when the id has no episode number."""
    n = episode_number(plan.get("episode"))
    return f"الحلقة {str(n).translate(AR_DIGITS)} · {plan.get('series_name') or SERIES_NAME}" if n else None


RECAP_BACKDROP_FROM = re.compile(r"^(first_shot|episode:[A-Za-z0-9_.-]+@\d+(\.\d+)?)$")
RECAP_BACKDROP_KEYS = ("backdrop", "backdrop_from", "backdrop_motion")


def recap_backdrop_problems(plan: dict) -> list[str]:
    """Q01 (E02 critic, 2026-10-27): the recap card may carry a story picture under its type, dimmed by the card (calm_cards .bd, opacity .38). The plan names it in `recap`:
    `backdrop_from: "first_shot"` (a frame of the episode's own first scene, 1.0 s in) or `"episode:<id>@<seconds>"` (a frame of an earlier episode's episode.mp4), or `backdrop: <image path>`.
    Never both. Static check, no file read except that an explicit `backdrop` file must exist."""
    r = plan.get("recap") or {}
    f = []
    if r.get("backdrop") and r.get("backdrop_from"):
        f.append("PLAN-RECAP-BACKDROP recap names both backdrop and backdrop_from: one picture")
    if r.get("backdrop_from") and not RECAP_BACKDROP_FROM.match(str(r["backdrop_from"])):
        f.append(f"PLAN-RECAP-BACKDROP backdrop_from {r['backdrop_from']!r} is not 'first_shot' or 'episode:<id>@<seconds>'")
    if r.get("backdrop") and not (ROOT / str(r["backdrop"])).is_file() and not Path(str(r["backdrop"])).is_file():
        f.append(f"PLAN-RECAP-BACKDROP backdrop file {r['backdrop']} not found")
    return f


def recap_backdrop_source(plan: dict, root: Path, ep_id: str) -> tuple[Path, float] | Path | None:
    """Where the recap's picture comes from: an image Path, or (video Path, seconds) to cut a frame from, or None (the card stays type on black). Raises Fail when the source is missing:
    a plan that asks for a story picture never silently gets none."""
    r = plan.get("recap") or {}
    if r.get("backdrop"):
        p = Path(str(r["backdrop"]))
        p = p if p.is_absolute() else root / p
        if not p.is_file():
            raise Fail("PLAN-RECAP-BACKDROP", f"recap backdrop {p} not found")
        return p
    src = str(r.get("backdrop_from") or "")
    if not src:
        return None
    if src == "first_shot":
        sid = plan["scenes"][0]["id"]
        v = root / "work" / "shots" / f"{ep_id}-{sid}" / "out" / f"{ep_id}-{sid}.mp4"
        return v, 1.0
    eid, _, t = src[len("episode:"):].partition("@")
    v = root / "work" / "episodes" / eid / "episode.mp4"
    return v, float(t)


def recap_backdrop_png(plan: dict, root: Path, ep_id: str, out: Path) -> Path | None:
    """The recap's story picture as a PNG at `out` (a frame cut with ffmpeg from the video the plan names, or the named image copied). None when the plan asks for none."""
    src = recap_backdrop_source(plan, root, ep_id)
    if src is None:
        return None
    out.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(src, Path):
        shutil.copyfile(src, out)
        return out
    vid, t = src
    if not vid.is_file():
        raise Fail("PLAN-RECAP-BACKDROP", f"the recap picture comes from {vid}, which does not exist yet (build that shot first)")
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(vid), "-frames:v", "1", str(out)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0 or not out.is_file():
        raise Fail("PLAN-RECAP-BACKDROP", f"could not cut a frame at {t:g} s of {vid}: {(r.stderr or '')[-200:]}")
    return out


def recap_card_params(plan: dict, backdrop: Path | str | None = None) -> dict:
    """The parameters of the recap card shot: line, word, (from E02) the series tag and, when the plan asks for one, the story picture under the type (`backdrop`, from recap_backdrop_png).
    tools/daily.py builds the card from this."""
    r = plan.get("recap") or {}
    p = {"line": r.get("line", ""), "word": r.get("word", "")}
    if backdrop:
        p["backdrop"] = str(backdrop)
    if backdrop and r.get("backdrop_motion"):      # E04 round 3 (Q01): the picture under the recap type MOVES (the first scene's video from 1.0 s); the still stays the measuring frame
        src = recap_backdrop_source(plan, Path(str(backdrop)).parents[3], plan.get("episode", ""))
        if isinstance(src, tuple):
            p["backdrop_video"] = str(src[0])
    tag = r.get("tag") or (episode_label(plan) if algo_on(plan) else None)
    if tag:
        p["tag"] = tag
    return p


FOLLOW_LINE_LEGACY = "تابع لتعرف ماذا حدث"      # daily.py's old default, kept for E01 / E01C (approved v5)


def follow_card_line(plan: dict) -> str:
    """The follow card's line. From E02: a statement of fact (DESIGN.md 2.4 item 12; the plan may word its own, under the same ask rules). E01 and E01C keep the plan's line or the old default."""
    if algo_on(plan):
        return str(plan.get("follow_line") or CC.FOLLOW_LINE)
    return str(plan.get("follow_line") or FOLLOW_LINE_LEGACY)


def choice_card_prompt(plan: dict) -> str:
    """The choice card's prompt: the plan's own, else «ما رأيكم، ولماذا؟» from E02, else v5's legacy text for E01 and E01C."""
    return str((plan.get("choice") or {}).get("prompt") or (CC.COMMENT_PROMPT if algo_on(plan) else CC.COMMENT_PROMPT_LEGACY))


def _name_in(word: str, names: list[str]) -> bool:
    w = G.norm(word)
    for n in names:
        nn = G.norm(n)
        if nn and (w == nn or (len(w) > len(nn) and w.endswith(nn) and all(c in NAME_CLITICS for c in w[:len(w) - len(nn)]))):
            return True
    return False


def validate_algo(plan: dict, script: dict | None, names: list[str]) -> list[str]:
    """PLAN-HOOK, PLAN-SOFAR, PLAN-PROMPT, PLAN-FOLLOW, PLAN-VARIANTS (DESIGN.md 2.1, 2.2, 2.4, 5.3, 5.4). Static, from E02 on."""
    f = []
    lines = {l["id"]: l for l in (script or {}).get("lines", [])}
    h = plan.get("hook")
    if not isinstance(h, dict) or h.get("pattern") not in HOOK_PATTERNS or not str(h.get("line", "")).strip():
        f.append(f"PLAN-HOOK plan needs hook {{pattern 1..{len(HOOK_PATTERNS)} (DESIGN.md section 3), line <the narrator line id the recap card speaks>}}")
    elif script is not None:
        hl = lines.get(h["line"])
        if hl is None:
            f.append(f"PLAN-HOOK hook line {h['line']} is not in script.json")
        else:
            text = display_text(hl["text"])
            if hl.get("speaker") != "narrator":
                f.append("PLAN-HOOK the hook line is spoken by the narrator (the recap card has no character)")
            used = [s_.get("id") for s_ in plan["scenes"] if s_.get("line") == h["line"]] + [k for k, v in ((plan["choice"].get("lines") or {}).items()) if v == h["line"]]
            if used:
                f.append(f"PLAN-HOOK the hook line {h['line']} is also used by {', '.join(map(str, used))}: it is the FIRST spoken line, on the recap card, and nowhere else")
            first_clause = re.split(r"[.؟?!؛:]", text)[0].strip() or text
            if len(first_clause.split()) > HOOK_FIRST_PLATE_WORDS_MAX:
                f.append(f"PLAN-HOOK the first plate of the hook has {len(first_clause.split())} words (at most {HOOK_FIRST_PLATE_WORDS_MAX}): «{first_clause}»")
            first_word = text.split()[0] if text.split() else ""
            if any(G.norm(first_word) == G.norm(b) or text.startswith(b) for b in HOOK_BAD_START) or G.norm(text.rstrip(".،")) == G.norm(plan.get("series_name") or SERIES_NAME):
                f.append(f"PLAN-HOOK the hook «{text}» opens with a greeting, «تابعوا», a logo or the series name alone (DESIGN.md H A: none of these is a hook)")
    sc = plan["scenes"][0] if plan.get("scenes") else {}
    if script is not None:
        first = lines.get(sc.get("line"))
        if first is None:
            f.append("PLAN-SOFAR the first scene has no narrator line: it carries the one clause of story so far (DESIGN.md 2.2)")
        else:
            cast = list(names) + [i.get("name", "") for i in plan.get("intros", []) or []]
            if not any(_name_in(w, cast) for w in display_text(first["text"]).split()):
                f.append(f"PLAN-SOFAR the first scene line {sc['line']} names no character of the cast ({', '.join(cast[:5])}...): from E02 it carries one clause of story so far, naming the heroine and the situation")
    ch = plan["choice"]
    f += [f"PLAN-PROMPT choice.prompt {x}" for x in CC.ask_problems(ch.get("prompt", CC.COMMENT_PROMPT), "text", True)]
    hook_id = (ch.get("lines") or {}).get("hook")
    if script is not None and hook_id in lines:
        f += [f"PLAN-PROMPT closing line {hook_id} {x}" for x in CC.ask_problems(display_text(lines[hook_id]["text"]), "text", True)]
    if plan.get("follow_line"):
        f += [f"PLAN-FOLLOW follow_line {x}" for x in CC.ask_problems(plan["follow_line"], "text", False)]
    var = ch.get("variants")
    for k in ("1", "2"):
        vs = [str(v).strip() for v in ((var or {}).get(k) or []) if str(v).strip()]
        n = len({G.norm_text(v) for v in vs})
        if n < VARIANTS_MIN:
            f.append(f"PLAN-VARIANTS choice.variants[{k!r}] has {n} distinct entries (at least {VARIANTS_MIN}: Gulf, Levant and Egyptian wordings and the verbs people use, for vote.py)")
    return f


def validate_plan(plan: dict, script: dict | None = None) -> list[str]:
    """Static checks of calm-plan.json (the writer's output). Returns 'ID message' strings."""
    f = []
    if "day_card_s" in plan and not (isinstance(plan["day_card_s"], (int, float)) and 0.5 <= plan["day_card_s"] <= 4.0):
        f.append(f"PLAN-DURATION day_card_s {plan['day_card_s']!r} outside 0.5..4 s")
    for k in ("series", "episode", "day", "scenes", "choice") + (("recap",) if recap_expected(plan) else ()):
        if k not in plan:
            f.append(f"PLAN-FIELD missing '{k}'")
    if f:
        return f
    if not recap_expected(plan) and plan.get("recap"):
        f.append(f"PLAN-RECAP {plan.get('episode')} has no vote to recap (recaps start at E{RECAP_FROM_EPISODE:02d}): it opens on the story at 0 s, drop the 'recap' key")
    ids = [s.get("id") for s in plan["scenes"]]
    if len(ids) != len(set(ids)):
        f.append("PLAN-IDS scene ids repeat")
    if len(plan["scenes"]) < SCENES_MIN:
        f.append(f"PLAN-SCENES {len(plan['scenes'])} scenes (a calm episode runs at least {SCENES_MIN}; there is no upper limit, the story sets the length)")
    blocks = [s.get("block", "story") for s in plan["scenes"]]
    if any(b not in ("consequence", "story", "cliff") for b in blocks):
        f.append("PLAN-BLOCK a scene block must be consequence, story or cliff")
    if "cliff" in blocks and blocks[-1] != "cliff":
        f.append("PLAN-BLOCK the cliff scenes come last, right before the choice card")
    lines = {l["id"]: l for l in (script or {}).get("lines", [])}
    for s in plan["scenes"]:
        if not s.get("template"):
            f.append(f"PLAN-TEMPLATE scene {s.get('id')} has no template")
        if s.get("line") and script is not None and s["line"] not in lines:
            f.append(f"PLAN-LINE scene {s['id']} names line {s['line']} which script.json does not have")
        if s.get("hold") is not None and not (0.0 <= float(s["hold"]) <= 1.5):
            f.append(f"PLAN-HOLD scene {s.get('id')} hold={s['hold']} outside 0..1.5 s")
        if not s.get("line") and not s.get("duration"):
            f.append(f"PLAN-DURATION scene {s.get('id')} has no narration line and no duration")
    for k in ("question", "choice1", "choice2"):
        if not str(plan["choice"].get(k, "")).strip():
            f.append(f"PLAN-CHOICE choice.{k} is empty (every episode ends on TWO choices)")
    if str(plan["choice"].get("choice1", "")).strip() == str(plan["choice"].get("choice2", "")).strip():
        f.append("PLAN-CHOICE the two choices are the same")
    for k, v in _visible_strings(plan):
        if has_tashkeel(v):
            f.append(f"PLAN-TASHKEEL {k} carries tashkeel: visible text is written without it (the TTS copy in script.json keeps it)")
    for l in (script or {}).get("lines", []):
        if has_tashkeel(l.get("text", "")):
            f.append(f"PLAN-TASHKEEL line {l['id']} text carries tashkeel (text is the caption; tts_text keeps the vowels)")
    f += [x.replace("FOREIGN-TAG", "PLAN-FOREIGN", 1) for x in G.check_script_tags((script or {}).get("lines", []), G.load(ROOT, (script or {}).get("series") or plan.get("series")))]
    f += validate_c345(plan, script)
    f += recap_backdrop_problems(plan)
    import calm_intro
    f += calm_intro.plan_problems(plan, script, ROOT)     # C10: every character's first appearance is followed by an intro_freeze
    f += [x.replace("CAP-FOREIGN-GLOSS", "PLAN-GLOSS", 1) for k, v in _visible_strings(plan) for x in G.check_text(str(v), None, G.load(ROOT, (script or {}).get("series") or plan.get("series")), where=f"{k} ")]
    _ser = (script or {}).get("series") or plan.get("series")
    lex = G.lexicon(ROOT, _ser)      # C11: plainly foreign words, foreign loanwords and own-language words with no glossary entry stop the plan, before any voice or shot is made
    f += [x.replace("CAP-FOREIGN-GLOSS", "PLAN-GLOSS", 1) for k, v in _foreign_checked_strings(plan) for x in G.check_foreign(str(v), None, lex["entries"], lex["foreign_keys"], f"{k} ", lex["loanwords"])]
    f += [x.replace("CAP-FOREIGN-GLOSS", "PLAN-GLOSS", 1) for l in (script or {}).get("lines", []) for x in G.check_foreign(display_text(l.get("text", "")), l.get("speaker"), G.line_entries(l, lex["entries"]), lex["foreign_keys"], f"line {l.get('id')} ", lex["loanwords"])]
    if algo_on(plan):
        f += validate_algo(plan, script, lex["names"])
    if script is not None and format_v2(plan):      # format v2 (the owner 2026-10-28), from E03 on
        f += dialogue_problems(script)
        f += event_problems(plan)
        f += narrator_role_problems(plan, script)
    return f


def validate_c345(plan: dict, script: dict | None) -> list[str]:
    """C3 + C4 static checks of the plan: transitions name a known cut type, the written object and the choice lines exist in the script, the split names real scenes."""
    import calm_sfx
    f = []
    ids = {s.get("id") for s in plan.get("scenes", [])} | ({"recap"} if recap_expected(plan) else set()) | {"day", "choice", "follow"} | {i.get("id") for i in plan.get("intros", []) or []}
    for t in plan.get("transitions", []):
        if t.get("cut") not in calm_sfx.CUTS:
            f.append(f"PLAN-TRANSITION {t.get('from')} -> {t.get('to')}: cut type {t.get('cut')!r} is not one of {', '.join(calm_sfx.CUTS)} (a cut type gives the visual AND the sound)")
        if t.get("from") not in ids or t.get("to") not in ids:
            f.append(f"PLAN-TRANSITION {t.get('from')} -> {t.get('to')}: names an item the episode does not have")
    lines = {l["id"]: l for l in (script or {}).get("lines", [])}
    w = plan.get("written")
    if w:
        if script is not None and w.get("line") not in lines:
            f.append(f"PLAN-WRITTEN line {w.get('line')} is not in script.json")
        elif script is not None and lines[w["line"]].get("speaker") != "narrator":
            f.append("PLAN-WRITTEN the written object is read by the narrator")
        if not str(w.get("heading", "")).strip():
            f.append("PLAN-WRITTEN the object needs a heading")
    ch = plan.get("choice") or {}
    cl = ch.get("lines")
    if cl:
        need = ("question", "choice1", "choice2", "hook")
        if [k for k in need if k not in cl]:
            f.append(f"PLAN-CHOICE choice.lines needs {', '.join(need)}")
        elif script is not None:
            f += [f"PLAN-CHOICE choice line {cl[k]} is not in script.json" for k in need if cl[k] not in lines]
        sp = ch.get("split")
        if sp:
            top = {c.get("id"): c for c in sp.get("top", [])}
            if len(top) != 2 or any(c.get("shot") not in ids for c in top.values()):
                f.append("PLAN-CHOICE choice.split.top needs two close-ups (ids A and B), each naming a scene of the plan")
            for c in sp.get("cuts", []):
                if c.get("clip") not in top or c.get("at") not in need:
                    f.append(f"PLAN-CHOICE a split cut names clip {c.get('clip')!r} at {c.get('at')!r}: clips are A or B, `at` is one of {', '.join(need)}")
            if len(sp.get("cuts", [])) < 4:
                f.append("PLAN-CHOICE the top half must cut at least 4 times while the question and the choices are read")
    elif ch.get("split"):
        f.append("PLAN-CHOICE choice.split needs choice.lines (the cuts follow the narrator)")
    return f


def format_v2(plan: dict) -> bool:
    """Format v2 (the owner 2026-10-28) applies from E03 on. An id that is not E<number> keeps it (a new series or a test episode follows the current rules)."""
    n = episode_number(plan.get("episode"))
    return n is None or n >= FORMAT_V2_FROM_EPISODE


def dialogue_problems(script: dict) -> list[str]:
    """DIALOGUE-LINES: 10 to 15 spoken character lines (speaker != narrator), at least 2 different speakers, and at least one exchange (two character lines of different speakers one after the other)."""
    lines = (script or {}).get("lines", [])
    chars = [l for l in lines if l.get("speaker") != "narrator"]
    f = []
    if not DIALOGUE_MIN <= len(chars) <= DIALOGUE_MAX:
        f.append(f"DIALOGUE-LINES {len(chars)} spoken character lines (speaker != narrator); an episode has {DIALOGUE_MIN} to {DIALOGUE_MAX}: the characters carry the story in their own voices")
    if len({l.get("speaker") for l in chars}) < 2:
        f.append("DIALOGUE-LINES fewer than 2 different character speakers: the characters must talk to each other")
    elif not any(a.get("speaker") != "narrator" and b.get("speaker") != "narrator" and a.get("speaker") != b.get("speaker") for a, b in zip(lines, lines[1:])):
        f.append("DIALOGUE-LINES no exchange: no two character lines of different speakers follow one another in script.json")
    return f


def night_of(scene: dict) -> str:
    """The night (day/night segment) a scene belongs to: its explicit `night` key, else the consequence block is the first night and story + cliff the second."""
    return str(scene.get("night") or ("n1" if scene.get("block") == "consequence" else "n2"))


def event_problems(plan: dict) -> list[str]:
    """EVENTS: 2 to 5 scenes carry `event` (the visible action in a few words); each uses a template that can show an action; every night has at least one."""
    f = []
    scenes = plan.get("scenes", [])
    ev = [s for s in scenes if str(s.get("event") or "").strip()]
    if not EVENTS_MIN <= len(ev) <= EVENTS_MAX:
        f.append(f"EVENTS {len(ev)} event scenes (scenes with an `event` field); an episode has {EVENTS_MIN} to {EVENTS_MAX}, each SHOWN on screen as an action")
    for s in ev:
        if s.get("template") in NO_ACTION_TEMPLATES:
            f.append(f"EVENTS scene {s.get('id')} is an event but uses {s.get('template')}, a reaction or a held pose: use a template that shows the action (push_in, parallax_pan, two_shot, insert, insert_depth)")
        if len(str(s["event"]).split()) < 3:
            f.append(f"EVENTS scene {s.get('id')} event {s['event']!r} is not a sentence: say what is seen happening")
    nights: dict[str, bool] = {}
    for s in scenes:
        nights[night_of(s)] = nights.get(night_of(s), False) or bool(str(s.get("event") or "").strip())
    for n, ok in nights.items():
        if not ok:
            f.append(f"EVENTS night {n} has no event scene: every night shows at least one real event (looking at an empty box is not one)")
    na = plan.get("needs_art")
    if na is not None and not (isinstance(na, list) and all(isinstance(x, dict) and str(x.get("what", "")).strip() for x in na)):
        f.append("EVENTS needs_art must be a list of {what, for_scene} objects naming the prop, pose or set piece the kits lack (it is created, not avoided)")
    return f


def narrator_allowed_ids(plan: dict) -> dict[str, str]:
    """line id -> the role that lets the narrator speak it: hook, recap (the first scene, story so far), link, choice, written, intro."""
    out: dict[str, str] = {}
    hk = (plan.get("hook") or {}).get("line")
    if hk:
        out[hk] = "hook"
    scenes = plan.get("scenes", [])
    if scenes and recap_expected(plan) and scenes[0].get("line"):
        out[scenes[0]["line"]] = "recap"
    for s in scenes:
        if s.get("role") in ("recap", "link") and s.get("line"):
            out[s["line"]] = s["role"]
    ch = plan.get("choice") or {}
    for v in list((ch.get("lines") or {}).values()) + [ch.get("line")]:
        if isinstance(v, str) and v:
            out[v] = "choice"
    if (plan.get("written") or {}).get("line"):
        out[plan["written"]["line"]] = "written"
    for i in plan.get("intros", []) or []:
        if i.get("line"):
            out[i["line"]] = "intro"
    return out


def narrator_role_problems(plan: dict, script: dict) -> list[str]:
    """NARRATOR-SHARE (static part): the narrator speaks only the recap, a short night link (scene `role: "link"`) and the vote question; a link is one short sentence."""
    allowed = narrator_allowed_ids(plan)
    f = []
    for l in (script or {}).get("lines", []):
        if l.get("speaker") != "narrator":
            continue
        role = allowed.get(l.get("id"))
        if role is None:
            f.append(f"NARRATOR-SHARE line {l.get('id')} is narrator speech outside recap, night link and vote question: give it to a character or mark its scene `role: \"link\"`")
        elif role == "link" and len(str(l.get("text", "")).split()) > NARRATOR_LINK_WORDS_MAX:
            f.append(f"NARRATOR-SHARE night link {l.get('id')} has {len(str(l.get('text', '')).split())} words (at most {NARRATOR_LINK_WORDS_MAX}): a link is one short sentence")
    return f


def narrator_share(spans: list) -> float:
    """The narrator's share of the placed voice TIME. spans = (speaker, seconds) per placed line."""
    tot = sum(d for _s, d in spans)
    return sum(d for s, d in spans if s == "narrator") / tot if tot > 0 else 0.0


def _foreign_checked_strings(plan: dict):
    """The visible strings that are TEXT for C11 (the choice's line ids and split data are plan plumbing, not words a viewer reads)."""
    for k, v in _visible_strings(plan):
        if not k.startswith(("choice.line", "choice.split")):
            yield k, v


def _visible_strings(plan: dict):
    for k in ("place", "clock0", "post_caption", "follow_line", "cover_hook"):
        if plan.get(k):
            yield k, str(plan[k])
    for k, v in (plan.get("recap") or {}).items():
        if k not in RECAP_BACKDROP_KEYS:      # a picture source (an id, a path), not words people read
            yield f"recap.{k}", str(v)
    for k, v in (plan.get("choice") or {}).items():
        if k != "variants":      # other ways to type a choice, for vote.py: never shown
            yield f"choice.{k}", str(v)
    for s in plan.get("scenes", []):
        if s.get("clock"):
            yield f"scene {s.get('id')} clock", str(s["clock"])
    for i in plan.get("intros", []) or []:       # C10: the graffiti is visible text
        for k in ("name", "tag"):
            if i.get(k):
                yield f"intro {i.get('id')} {k}", str(i[k])
