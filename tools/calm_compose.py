# /// script
# requires-python = ">=3.11"
# dependencies = ["playwright", "pillow", "numpy", "scipy"]
# ///
"""Calm-format composing (owner, 2026-10-24, CLAUDE.md "Calm format"): the finished shots, the wrapper cards, ONE narrator, big word-by-word captions
and a HUD become one Reel. Not a replacement for tools/compose.py (the E01 premium path); this is the calm path the daily pipeline uses.

  uv run tools/calm_compose.py plan     <ep>   calm-plan.json + voice takes -> work/calm/<ep>/timeline.json (scene lengths come from the takes)
  uv run tools/calm_compose.py captions <ep>   word timing from each take's energy (numpy, no model) -> the FULL sentence (2 lines at most) with the spoken word highlighted + HUD plates
  uv run tools/calm_compose.py audio    <ep>   phone-first mix (tools/calm_mix.py): cleaned voices, a pad bed, sfx at dialogue-relative levels, voice-driven ducking, -14 LUFS -> mix.wav + audio/stems/
  uv run tools/calm_compose.py assemble <ep>   shots + wrapper cards with soft joins, plates, mix, NVENC -> episode.mp4
  uv run tools/calm_compose.py gate     <ep>   calm episode checks (declared data + the calm bands of qg_checks) -> gate.json
  uv run tools/calm_compose.py all      <ep>

<ep> is an episode id (E02). Plan: bible/series/<series>/episodes/<ep>/calm-plan.json (schema in pipelines/DAILY.md); script: .../script.json (voice.py lines);
takes: work/voice/<ep>/<line>.trimmed.wav; shots: work/shots/<ep>-<scene>/out/<ep>-<scene>.mp4; cards: work/shots/<ep>-<card>/out/<ep>-<card>.mp4.
Outputs: work/episodes/<ep>/ (where ig.py looks: episode.mp4, gate/report.json, heal/critic.json). Exit 0 ok, 1 a check failed (`FAIL [ID] message`), 2 usage. GPU first (NVDEC/NVENC), ffmpeg -threads 2, no network, no model.
"""
from __future__ import annotations

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


# ------------------------------------------------------------------ stage: plan -> timeline
def scene_seconds(line_s: float | None, explicit) -> float:
    """A scene lasts its line + a lead and a pad (grid-snapped), at least MIN_SCENE_S; a line that needs more than MAX_SCENE_S must be split by the writer."""
    if line_s is None:
        d = snap(float(explicit))
    else:
        d = snap(max(MIN_SCENE_S, line_s + VOICE_LEAD_S + PAD_S))
    if d > MAX_SCENE_S + 1e-9:
        raise Fail("PLAN-DURATION", f"a scene would last {d:.2f} s (> {MAX_SCENE_S} s): split the line")
    return d


def read_hold_s(lines: list[dict], line_id: str, line_s: float, gap_s: float, glossary: list[dict]) -> float:
    """C12 (CAP-READING-SPEED): the pause a scene needs after its line so that the LAST sentence plate of the line is up for max(1.5 s, chars / 12 cps) (cap_sentence.read_speed_need_s).
    gap_s is the room between the line's end and the next voice. The last plate is estimated from the text alone (no browser, no envelope): the last clause of the line, its
    share of the take by syllable weight, its bracketed meanings counted. The captions stage merges a unit that would still be too brief with its neighbour, and the gate
    (CAP-READING-SPEED) measures the real plates, so an estimate that is too small fails loudly there, never silently. Returns seconds (0 when the room is enough)."""
    ln = next((l for l in lines if l["id"] == line_id), None)
    if not ln:
        return 0.0
    words = display_text(ln["text"]).split()
    if not words:
        return 0.0
    start = len(words) - 1
    while start > 0 and not CS.ends_clause(words[start - 1]):
        start -= 1
    w, _m = CS.syllable_weights(" ".join(words), ln.get("tts_text"))
    speech = line_s * sum(w[start:]) / max(sum(w), 1e-9)
    shown = " ".join(G.with_gloss(words[start:], ln.get("speaker"), G.line_entries(ln, glossary)))
    need = CS.read_speed_need_s(CS.visible_chars(shown))
    return max(0.0, need - speech - (gap_s - 0.02) + READ_HOLD_MARGIN_S)


def read_heal_record(root, ep_id: str) -> dict:
    """R-503: work/daily/<ep>/read-heal.json {"lines": {line id: {"lead": s, "hold": s}}}: the reading time the animatic measured as missing, fed back to the plan by tools/read_heal.py. {} when absent."""
    try:
        r = json.loads((Path(root) / "work" / "daily" / ep_id / "read-heal.json").read_text(encoding="utf-8"))
        return r if isinstance(r, dict) else {}
    except (OSError, ValueError):
        return {}


def cap_heal_cuts(root, ep_id: str) -> dict[str, set[int]]:
    """R-506: work/daily/<ep>/cap-heal.json {"lines": {line id: {"cuts": [i, ...]}}}: boundaries after display word i where the caption heal (tools/cap_heal.py) asked for a new plate, because the
    plate that was there had no place outside the faces. {line id: {i}}; {} when the file is absent."""
    try:
        r = json.loads((Path(root) / "work" / "daily" / ep_id / "cap-heal.json").read_text(encoding="utf-8"))
        return {lid: {int(i) for i in (row or {}).get("cuts", [])} for lid, row in (r.get("lines") or {}).items()}
    except (OSError, ValueError, AttributeError, TypeError):
        return {}


def stage_plan(ep: Ep) -> dict:
    plan, script = read_json(ep.plan_p), read_json(ep.script_p)
    bad = validate_plan(plan, script)
    if bad:
        raise Fail(bad[0].split(" ", 1)[0], "; ".join(b.split(" ", 1)[1] for b in bad[:4]))
    items = []
    heal_rec = read_heal_record(ep.root, ep.id)

    def card(kind, dur):
        items.append({"kind": "card", "id": kind, "shot": f"{ep.id}-{kind}", "video": f"work/shots/{ep.id}-{kind}/out/{ep.id}-{kind}.mp4", "dur": snap(dur), "line": None})

    label = episode_label(plan) if algo_on(plan) else None
    if recap_expected(plan):
        card("recap", 2.5)
        hk = plan.get("hook") if algo_on(plan) else None
        if hk:    # DESIGN.md 2.1: the recap is SPOKEN, by the narrator, and it is the hook; it must fit the existing 3.0 s cap, so the cap is not touched
            tk = ep.take(hk["line"])
            if not tk.is_file():
                raise Fail("VOICE-MISSING", f"no take for {hk['line']} at {tk}: the voice stage comes before the shots")
            hd = snap(max(2.5, wav_seconds(tk) + VOICE_LEAD_S + PAD_S))
            if hd > RECAP_MAX_S + 1e-9:
                raise Fail("PLAN-DURATION", f"the spoken recap {hk['line']} would last {hd:.2f} s (> {RECAP_MAX_S} s, the recap card's cap): shorten the line to about {RECAP_MAX_S - VOICE_LEAD_S - PAD_S:.1f} s aloud")
            items[-1].update({"dur": hd, "line": hk["line"], "hook_pattern": hk.get("pattern")})
        if label:
            items[-1]["tag"] = label
    import calm_intro
    intros_after: dict = {}
    for ix in plan.get("intros", []) or []:
        intros_after.setdefault(ix["after"], []).append(ix)
    clock = _clock_minutes(plan.get("clock0", "9:00 م"))
    day_done = False
    for s in plan["scenes"]:
        if s.get("block", "story") != "consequence" and not day_done:
            wr, wd = plan.get("written"), 2.0
            if wr:     # C3: the day card is a written object and the narrator reads it
                wt = ep.take(wr["line"])
                if not wt.is_file():
                    raise Fail("VOICE-MISSING", f"no take for {wr['line']} at {wt}: the voice stage comes before the shots")
                wd = max(2.5, wav_seconds(wt) + JOIN_S + VOICE_LEAD_S + PAD_S + 0.2)
            card("day", wd)
            if wr:
                items[-1].update({"line": wr["line"], "cap_style": "object", "cap_y": OBJ_CAP_Y, "written": True})
            day_done = True
        take = ep.take(s["line"]) if s.get("line") else None
        line_s = wav_seconds(take) if take else None
        if take is not None and not take.is_file():
            raise Fail("VOICE-MISSING", f"no take for {s['line']} at {take}: the voice stage comes before the shots")
        dur = scene_seconds(line_s, s.get("duration"))
        read_hold, dur_shot, lead_hold = 0.0, dur, 0.0
        if line_s is not None:     # C12: when the next line starts too soon for the last plate to be read, the plan inserts a pause; the shot holds its last frame, the voice never moves
            need_h = read_hold_s(script["lines"], s["line"], line_s, dur - line_s - (JOIN_S if items else 0.0), G.load(ep.root, script.get("series") or ep.series))
            heal = (heal_rec.get("lines") or {}).get(s["line"]) or {}      # R-503: what the animatic measured and the self-heal fed back (tools/read_heal.py)
            need_h += float(heal.get("hold") or 0.0)
            read_hold = math.ceil(need_h * FPS - 1e-9) / FPS if need_h > 0 else 0.0
            lead_hold = math.ceil(float(heal.get("lead") or 0.0) * FPS - 1e-9) / FPS if float(heal.get("lead") or 0.0) > 0 else 0.0
            dur = round(dur + read_hold + lead_hold, 4)
            dur_shot = round(dur_shot + lead_hold, 4)       # the lead is silence BEFORE the voice, inside the shot's own length (the lipsync offset is voice_t0 - t0)
            if dur > MAX_SCENE_S + 1.5 + 1e-9:
                raise Fail("PLAN-DURATION", f"scene {s['id']} would last {dur:.2f} s with its reading pause: shorten the line")
        clock = _clock_minutes(s["clock"]) if s.get("clock") else clock + 2
        items.append({"kind": "scene", "id": s["id"], "shot": f"{ep.id}-{s['id']}", "video": f"work/shots/{ep.id}-{s['id']}/out/{ep.id}-{s['id']}.mp4", "dur": dur,
                      "line": s.get("line"), "block": s.get("block", "story"), "clock": _clock_text(clock), "template": s["template"],
                      "read_hold": round(read_hold, 4), "lead_hold": round(lead_hold, 4), "dur_shot": round(dur_shot, 4),   # C12: the shot itself is rendered at dur_shot; the pause after it is its last frame held
                      "hold": float(s.get("hold") or 0.0),   # a deliberate hold: the last `hold` seconds of the shot are its last frame, still (the calm recipe's 13 to 17 % frozen share; E01C had none, so CALM-HOLDS failed)
                      "subjects": [s.get("params", {}).get("character")] if s["template"] != "two_shot" else [x.strip() for x in str(s["params"].get("characters", "")).split(",")],
                      **({"day": str(s["day"])} if s.get("day") not in (None, "") else {})})   # E04 Q06: a scene may carry its own HUD day (night one is day three, the day card then moves it to day four)
        for ix in intros_after.get(s["id"], []):      # C10: right after the scene that first shows the character the story freezes on them (calm_intro.py)
            itk = ep.take(ix["line"]) if ix.get("line") else None
            if itk is not None and not itk.is_file():
                raise Fail("VOICE-MISSING", f"no take for {ix['line']} at {itk}: the voice stage comes before the shots")
            need = calm_intro.min_duration(len(str(ix["name"]).split()) + len(str(ix["tag"]).split()))
            idur = snap(max(need, scene_seconds(wav_seconds(itk), None) if itk is not None else need))
            if idur > calm_intro.MAX_S + 1e-9:
                raise Fail("PLAN-DURATION", f"intro {ix['id']} would last {idur:.2f} s (> {calm_intro.MAX_S} s): shorten its narrator line")
            items.append({"kind": "intro", "id": ix["id"], "shot": f"{ep.id}-{ix['id']}", "video": f"work/shots/{ep.id}-{ix['id']}/out/{ep.id}-{ix['id']}.mp4", "dur": idur, "line": ix.get("line"),
                          "block": s.get("block", "story"), "template": "intro_freeze", "hold": 0.0, "subjects": [], "character": ix["character"], "name": ix["name"], "tag": ix["tag"], "after": s["id"]})
    if not day_done:
        raise Fail("PLAN-BLOCK", "every scene is a consequence scene: a calm episode needs story scenes after the day card")
    cq = plan["choice"].get("line")
    chl, rel_t = plan["choice"].get("lines"), {}
    if chl:    # C4: the question, both choices and the hook are four narrated lines; the card lasts as long as they take
        t_rel = JOIN_S + 0.3
        for k in ("question", "choice1", "choice2", "hook"):
            tk = ep.take(chl[k])
            if not tk.is_file():
                raise Fail("VOICE-MISSING", f"no take for {chl[k]} at {tk}: the voice stage comes before the shots")
            d = wav_seconds(tk)
            rel_t[k] = (round(t_rel, 4), round(t_rel + d, 4))
            t_rel += d + CHOICE_GAP_S
        cdur = t_rel - CHOICE_GAP_S + CHOICE_TAIL_S
        if cdur > MAX_CHOICE_S:
            raise Fail("PLAN-DURATION", f"the choice sequence would last {cdur:.2f} s (> {MAX_CHOICE_S} s): shorten the question, the choices or the hook")
    else:
        cdur = min(MAX_CARD_S, max(5.0, (wav_seconds(ep.take(cq)) + 1.2) if cq and ep.take(cq).is_file() else 5.0))
    card("choice", cdur)
    card("follow", 2.5)
    t, starts = 0.0, []
    for i, it in enumerate(items):
        it["t0"] = round(t if i == 0 else t - JOIN_S, 4)
        t = it["t0"] + it["dur"]
        it["t1"] = round(t, 4)
        if it["line"]:
            it["voice_t0"] = round(it["t0"] + (JOIN_S if i else 0) + VOICE_LEAD_S + float(it.get("lead_hold") or 0.0), 4)
        starts.append(it["t0"])
    if chl:
        ch = next(it for it in items if it["id"] == "choice")
        ch["line"], ch["voice_t0"] = chl["question"], round(ch["t0"] + rel_t["question"][0], 4)
        ch["more_lines"] = [{"line": chl[k], "voice_t0": round(ch["t0"] + rel_t[k][0], 4), "role": k} for k in ("choice1", "choice2", "hook")]
        sp = plan["choice"].get("split")
        if sp:
            ch["cap_y"] = sp.get("captions_y", 640)
            vfx = sp.get("vfx") or ["flash"]
            cuts = []
            for i, c in enumerate(sp["cuts"]):
                a, b = rel_t[c["at"]]
                cuts.append({"t": round(a + c.get("frac", 0.0) * (b - a), 3), "clip": c["clip"], "vfx": vfx[i % len(vfx)]})
            cuts.sort(key=lambda c: c["t"])
            lit = [{"state": k, "t0": rel_t[k][0], "t1": rel_t[k][1] if k != "hook" else round(ch["dur"] - 0.3, 3)} for k in ("question", "choice1", "choice2", "hook")]
            ch["split"] = {"first": sp.get("first", "A"), "top": sp["top"], "cuts": cuts, "lit": lit}
    elif cq:
        ch = next(it for it in items if it["id"] == "choice")
        ch["line"] = cq
        ch["voice_t0"] = round(ch["t0"] + JOIN_S + 0.3, 4)
    import calm_sfx    # C3: every join has a declared cut type: ONE name gives the visual (xfade) and the sound; a plan without `transitions` gets the defaults by template
    decl = {(t["from"], t["to"]): t["cut"] for t in plan.get("transitions", [])}
    pairs = {(a["id"], b["id"]) for a, b in zip(items, items[1:])}
    stray = [f"{a} -> {b}" for (a, b) in decl if (a, b) not in pairs]
    if stray:
        raise Fail("PLAN-TRANSITION", f"transitions name joins the episode does not have: {', '.join(stray[:4])}")
    for i, it in enumerate(items):
        if i:
            cut = decl.get((items[i - 1]["id"], it["id"])) or calm_sfx.default_cut(it)
            vfx_n, xf, snd = calm_sfx.CUTS[cut][:3]
            it["join_in"] = {"cut": cut, "vfx": vfx_n, "xfade": xf, "sound": snd}
    tl = {"episode": ep.id, "series": ep.series, "fps": FPS, "canvas": [W, H], "profile": "calm", "day": plan["day"], "place": plan.get("place", ""), "items": items,
          "total_s": round(items[-1]["t1"], 4), "join_s": JOIN_S}
    if label:
        tl["episode_label"] = label      # the HUD strip (first STRIP_S of the first HUD) and the recap tag say this (DESIGN.md 2.3)
        tl["strip_s"] = STRIP_S
    write_json(ep.timeline_p, tl)
    return {"items": len(items), "total_s": tl["total_s"]}


def _clock_minutes(text: str) -> int:
    m = re.search(r"(\d{1,2})[:٫.](\d{2})", str(text).translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")))
    if not m:
        return 9 * 60
    h, mi = int(m.group(1)), int(m.group(2))
    pm = "م" in str(text) or "PM" in str(text).upper()
    if pm and h < 12:
        h += 12
    return h * 60 + mi


def _clock_text(minutes: int) -> str:
    h, mi = divmod(minutes % (24 * 60), 60)
    suffix = "م" if h >= 12 else "ص"
    h12 = h % 12 or 12
    return f"{h12}:{mi:02d} {suffix}".translate(AR_DIGITS)


# ------------------------------------------------------------------ word timing (numpy, no model)
def envelope(path: Path, hop_s: float = 0.01):
    import numpy as np
    with wave.open(str(path), "rb") as w:
        n, sr, ch, sw = w.getnframes(), w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(n)
    a = np.frombuffer(raw, dtype={1: np.uint8, 2: np.int16, 4: np.int32}[sw]).astype(np.float64)
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    a = a / (float(2 ** (8 * sw - 1)) if sw > 1 else 128.0)
    hop = max(1, int(sr * hop_s))
    k = len(a) // hop
    env = np.sqrt((a[: k * hop].reshape(k, hop) ** 2).mean(axis=1) + 1e-12) if k else np.zeros(1)
    return env, hop_s


VOICED_GAP_S = 0.10           # a dip shorter than this inside speech is not a pause
VOICED_MIN_S = 0.05
PAUSE_SNAP_S = 0.20           # a word boundary that falls this close (voiced seconds) to a real pause moves onto it


def voiced_spans(env, hop: float) -> list[tuple[float, float]]:
    """(start, end) seconds of the voiced stretches of a take, from its own energy: frames within 38 dB of the peak (floor -55 dB), dips under
    VOICED_GAP_S bridged, specks under VOICED_MIN_S dropped. Empty take: the whole file."""
    import numpy as np
    db = 20 * np.log10(env + 1e-9)
    thr = max(db.max() - 38.0, -55.0)
    act = np.where(db > thr)[0]
    if not len(act):
        return [(0.0, len(env) * hop)]
    spans, a, b = [], act[0], act[0]
    for i in act[1:]:
        if (i - b) * hop > VOICED_GAP_S:
            spans.append((a * hop, (b + 1) * hop))
            a = i
        b = i
    spans.append((a * hop, (b + 1) * hop))
    keep = [s for s in spans if s[1] - s[0] >= VOICED_MIN_S]
    return keep or [(act[0] * hop, (act[-1] + 1) * hop)]


def word_timing(path: Path, words: list[str], weights: list[float] | None = None) -> list[tuple[float, float]]:
    """Seconds (start, end) of each word inside the take. ESTIMATED, not measured per word (no model, no ASR: banned): the voiced stretches of the take
    come from its own energy, the words are laid over the VOICED time only by weight, so a pause inside the line (a comma, a breath) is never spent on a
    word and the highlight waits for the voice after it. `weights` is a per-word syllable weight (cap_sentence.syllable_weights, from the vowelled
    text); without it, Arabic letters + 1. A boundary inside a stretch snaps to the quietest 10 ms frame within +-60 ms."""
    import numpy as np
    env, hop = envelope(path)
    spans = voiced_spans(env, hop)
    wts = np.array(weights if weights is not None else [max(1, len(AR_LETTER.findall(w))) + 1.0 for w in words], dtype=float)
    total = sum(b - a for a, b in spans)
    cum = np.concatenate([[0.0], np.cumsum(wts) / wts.sum()]) * total
    edges = np.cumsum([b - a for a, b in spans])[:-1]          # voiced-time of every pause: pauses sit between words (at punctuation), never inside one
    if len(edges):
        for i in range(1, len(words)):
            k = int(np.argmin(np.abs(edges - cum[i])))
            if abs(edges[k] - cum[i]) <= PAUSE_SNAP_S:
                cum[i] = edges[k]
        cum = np.maximum.accumulate(cum)

    def at(vt: float, start_side: bool) -> tuple[float, bool]:
        acc = 0.0
        for a, b in spans:
            if vt < acc + (b - a) - 1e-9 or (not start_side and vt <= acc + (b - a) + 1e-9):
                return a + (vt - acc), abs(vt - acc) < 1e-9 or abs(vt - acc - (b - a)) < 1e-9
            acc += b - a
        return spans[-1][1], True
    out = []
    prev_end = spans[0][0]
    for i in range(len(words)):
        s, s_edge = at(float(cum[i]), True)
        e, e_edge = at(float(cum[i + 1]), False)
        if not s_edge and i > 0:
            j0, j1 = int(max(0, (s - 0.06) / hop)), int(min(len(env) - 1, (s + 0.06) / hop))
            s = max(prev_end + 0.0, (j0 + int(np.argmin(env[j0:j1 + 1]))) * hop) if j1 >= j0 else s
        out.append([s, e, e_edge])
        prev_end = e
    # a snapped end must equal the next word's snapped start when the two touch inside one stretch; every word keeps at least 0.08 s
    for i in range(len(out) - 1):
        if not out[i][2]:
            out[i][1] = out[i + 1][0]
    res, t = [], 0.0
    for s, e, _ in out:
        s = max(s, t)
        e = max(e, s + 0.08)
        res.append((round(s, 3), round(e, 3)))
        t = e
    return res


def _text_with_gloss(words: list[str], group: list[int], gm: dict) -> list[str]:
    """The tokens of one plate's text: its words, each glossary word followed by (meaning)."""
    out = []
    for j in group:
        out.append(words[j])
        if j in gm:
            out.append(f"({gm[j]['meaning_ar']})")
    return out


def group_words(words: list[str], max_words: int = CAP_WORDS_MAX, max_chars: int = 13) -> list[list[int]]:
    """Indexes of the words, grouped 1 to 3 per plate; a long word stands alone."""
    groups, cur = [], []
    for i, w in enumerate(words):
        if cur and (len(cur) >= max_words or sum(len(words[j]) for j in cur) + len(w) + len(cur) > max_chars):
            groups.append(cur)
            cur = []
        cur.append(i)
    if cur:
        groups.append(cur)
    return groups


# ------------------------------------------------------------------ stage: captions (plates) and HUD
def plate_html(groups_states: list[dict], hud_items: list[dict], accent: str = "#c6ff3d", with_ref: bool = False) -> str:
    """The caption plates. The dark outline is NOT `-webkit-text-stroke` on the fill glyphs: Arabic letters overlap their neighbours, so a
    centred stroke of the next glyph cut a dark seam into the previous letter at every join and word end (the owner 2026-10-25, C1). Each word
    carries its outline as a `::before` under-layer (z-index -1 inside the plate's own stacking context), painted below EVERY fill.
    with_ref adds a fill-only twin of each plate (`.ref`, id r<k>, same layout) that CAP-ARABIC-SHAPING compares against."""
    import compose as C
    parts = []
    for k, st in enumerate(groups_states):
        lines = st.get("lines") or [list(range(len(st["words"])))]     # a sentence is one or two lines of word indexes; a bare word list is one line
        spans = "".join('<div class="ln">' + "".join(f'<span data-t="{_esc(st["words"][j])}" class="{"on" if j == st["active"] else ""}">{_esc(st["words"][j])}</span>' for j in ln) + "</div>" for ln in lines)
        carry = [f"{c['word']} ({c['meaning']})" for c in st.get("carry", [])]     # the meaning of an earlier sentence of the line that is still being read
        if st.get("gloss") or carry:   # the meaning of a foreign word, in brackets, on its own smaller line under the words (CLAUDE.md "Gloss foreign words")
            own = [f"{w} ({m})" for w, m in st["gloss_pairs"]] if st.get("gloss_pairs") else ([("(" + " · ".join(st["gloss"]) + ")")] if st.get("gloss") else [])
            gtxt = " · ".join(own + carry)
            spans += f'<div class="gl"><span data-t="{_esc(gtxt)}">{_esc(gtxt)}</span></div>'
        parts.append(f'<div class="cap{" obj" if st.get("style") == "object" else ""}" id="c{k}" dir="rtl" lang="ar">{spans}</div>')
        if with_ref:
            parts.append(f'<div class="cap ref{" obj" if st.get("style") == "object" else ""}" id="r{k}" dir="rtl" lang="ar">{spans}</div>')
    for k, h in enumerate(hud_items):
        strip = f'<span class="strip">{_esc(h["strip"])}</span>' if h.get("strip") else ""
        parts.append(f'<div class="hud" id="h{k}" dir="rtl" lang="ar">{strip}<b class="day">{_esc(h["day"])}</b><span>{_esc(h["clock"])}</span><span>{_esc(h["place"])}</span></div>')
    css = (f"{C.font_css(1.0)}html,body{{margin:0;background:transparent}}"
           f".cap{{display:block;width:max-content;position:relative;isolation:isolate;margin:40px 40px;padding:6px {CAP_PAD_X}px;font-family:'thmanyahsans';font-weight:900;font-size:{CAP_FONT_PX}px;line-height:{round(CAP_FONT_PX*1.35)}px;color:#fff;white-space:nowrap;"
           f"font-kerning:normal;letter-spacing:0;word-spacing:0;text-rendering:optimizeLegibility}}"
           f".cap .gl{{display:block;text-align:center;font-size:{GLOSS_FONT_PX}px;line-height:{round(GLOSS_FONT_PX*1.35)}px;font-weight:700;color:#fff3c9;margin-top:2px}}.cap .gl span{{margin:0}}"
           f".cap .ln{{display:block;text-align:center;white-space:nowrap}}"
           f".cap .ln .gl-in{{font-size:{GLOSS_FONT_PX}px;font-weight:700;color:#fff3c9;margin:0 {GLOSS_INLINE_GAP_PX}px 0 .22em}}"      # F-001: a meaning that fits beside the last row of the sentence sits there (the plate stays two rows tall)
           f".cap span{{display:inline-block;position:relative;margin:0 .22em}}.cap span.on{{color:{accent}}}"
           f".cap span::before{{content:attr(data-t);position:absolute;inset:0;z-index:-1;color:rgb(10,8,6);-webkit-text-stroke:9px rgb(10,8,6);text-shadow:0 6px 18px rgba(0,0,0,.55)}}"
           f".cap.ref span::before{{display:none}}"
           f".cap.obj span{{font-family:'thmanyahserifdisplay';color:#f4cf6a}}.cap.obj span.on{{color:#fff3c9}}"   # C3: engraved in the plate's own letters (serif display, brass gold)
           f".hud{{display:inline-flex;flex-direction:column;align-items:flex-start;gap:4px;margin:10px;padding:10px 22px;border-radius:14px;background:rgba(10,8,6,.55);font-family:'thmanyahsans';font-size:44px;font-weight:700;color:#f3ede4;line-height:1.25}}"
           f".hud .day{{font-size:56px;font-weight:900;color:#ff4d4d}}"
           f".hud .strip{{font-size:40px;font-weight:700;color:#f3ede4;opacity:.92;padding-bottom:6px;margin-bottom:2px;border-bottom:3px solid rgba(243,237,228,.45);white-space:nowrap}}")
    return f'<!doctype html><meta charset="utf-8"><style>{css}</style>{"".join(parts)}'


def _esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def measure_words(words: list[str], work: Path) -> dict[str, float]:
    """Width in px of each distinct word as the caption draws it (Thmanyah Sans Black 104 px), measured in the same Chrome the plates use."""
    import compose as C
    res: dict[str, float] = {}
    html = plate_html([{"words": [w], "active": 0} for w in words], [])

    def go(pg):
        pg.evaluate("document.fonts.load('900 104px thmanyahsans', 'هدى').then(() => document.fonts.ready).then(() => 1)")
        ws = pg.evaluate("Array.from(document.querySelectorAll('.cap .ln > span')).map(s => s.getBoundingClientRect().width)")
        res.update(dict(zip(words, ws)))
        return True
    C.chrome_page(html, work, W, H, go)
    if len(res) != len(words) or not all(v > 0 for v in res.values()):
        raise Fail("CAP-MEASURE", f"measured {len(res)} of {len(words)} words")
    return res


def face_boxes_by_item(ep: Ep, tl: dict) -> dict[str, list[dict]]:
    """F-001: the face boxes of every item of the timeline in screen px, read from each shot's own rig trace (cap_face.shot_face_boxes); the choice sequence gets the faces its
    two top-half close-ups show. A scene with no trace is a hard stop: a plate cannot be proved clear of a face nobody located."""
    sb, missing = {}, []
    for it in tl["items"]:
        if it["kind"] == "scene":
            try:
                sb[it["id"]] = CF.shot_face_boxes(ep.root / "work" / "shots" / it["shot"])
            except (FileNotFoundError, KeyError) as e:
                missing.append(str(e))
    if missing:
        raise Fail("CAP-FACE-CLEAR", "no face data (run the shots first): " + "; ".join(missing[:3]))
    out = dict(sb)
    for it in tl["items"]:
        if it.get("split"):
            out[it["id"]] = CF.choice_face_boxes(it, sb, {c["id"]: c["shot"] for c in it["split"]["top"]}, TOP_H, W)
    return out


def _face_boxes_for_plate(tl: dict, boxes: dict, p: dict, t0: float | None = None, t1: float | None = None) -> list[dict]:
    return CF.window_face_boxes(tl["items"], boxes, p["start"] if t0 is None else t0, p["end"] if t1 is None else t1, FACE_GRACE_S)


def mark_avoid_box() -> dict:
    """The NJ mark's rect grown by WATERMARK-CLEAR's pad: a plate moved off a face must not land on the mark either. Root cause (E03, 2026-10-28): the choice plates were
    lifted above a face to y 384, 6 px under the mark, and the episode gate failed WATERMARK-CLEAR; E02 cleared it at y 390 by chance."""
    r, p = WM.rect(), WM.PAD_PX
    return {"x": r["x"] - p, "y": r["y"] - p, "w": r["w"] + 2 * p, "h": r["h"] + 2 * p, "char": "NJ mark"}


def _hud_boxes(hud: list[dict], t0: float, t1: float) -> list[dict]:
    pad = CF.HUD_PAD_PX
    return [{"x": h["x"] - pad, "y": h["y"] - pad, "w": h["w"] + 2 * pad, "h": h["h"] + 2 * pad} for h in hud if h.get("w") and hud_window(h)[0] < t1 and hud_window(h)[1] > t0]


def hud_window(h: dict) -> tuple[float, float]:
    """When a HUD plate is on screen: its own show window (the strip plate and the plate that takes over from it), else the scene's span less half a join each side."""
    return (h["show0"], h["show1"]) if "show0" in h else (h["t0"] + JOIN_S / 2, h["t1"] - JOIN_S / 2)


def place_clear_of_faces(ep: Ep, tl: dict, caps: list[dict], hud: list[dict]) -> dict:
    """F-001: move each sentence plate off every face on screen while it is up. A sentence keeps ONE position for all its states when one exists (the highlight changes
    word to word, the plate does not wander); if no single position clears the faces of the shots it crosses (a sentence over a join between two close-ups), each state is
    placed for its own window, so the plate moves only where the picture forces it. Position = the legal one nearest the original (cap_face.place_plate): inside the safe
    area, bottom edge at most PLATE_BOTTOM_MAX (the bound CALM-PLATE-SAFE already allowed), clear of the HUD when possible; the choice sequence keeps its plates in the top half.
    Mutates caps (x, y, `moved_for_face`). Returns counts."""
    boxes = face_boxes_by_item(ep, tl)
    groups: dict[tuple, list[dict]] = {}
    for c in caps:
        groups.setdefault((c["line"], c["unit"]), []).append(c)
    n_moved = n_split = 0
    for (lid, u), grp in groups.items():
        if all(c.get("style") == "object" for c in grp):
            # An engraved plate (C3) lives ON the brass plate: it never moves for a face, and its engraving goes with the plate. Root cause (E01C, 2026-10-25): the last state ran 0.11 s into the
            # page turn onto s02, over the 0.1 s grace, so the whole sentence was thrown 206 px down and its second line crossed the plate's own border. The engraving now ends when the next shot begins.
            nxt = [it["t0"] for it in tl["items"] if it["t0"] > min(c["start"] for c in grp) + 1e-6]
            if nxt:
                for c in grp:
                    c["end"] = round(min(c["end"], min(nxt)), 3)
            continue
        t0, t1 = min(c["start"] for c in grp), max(c["end"] for c in grp)
        in_choice = any(it.get("split") and it["t0"] <= t0 < it["t1"] for it in tl["items"])
        ymax = TOP_H - 8 if in_choice else PLATE_BOTTOM_MAX
        w, h = max(c["w"] for c in grp), max(c["h"] for c in grp)
        x0, y0 = grp[0]["x"], min(c["y"] for c in grp)
        av = _face_boxes_for_plate(tl, boxes, grp[0], t0, t1) + [mark_avoid_box()]
        if not any(CF.intersects({"x": x0, "y": y0, "w": w, "h": h}, b) for b in av):
            continue
        pos = CF.place_plate(w, h, (x0, y0), av, _hud_boxes(hud, t0, t1), SAFE, ymax)
        if pos:
            for c in grp:
                c.update({"x": pos[0] + (w - c["w"]) // 2, "y": pos[1] + (h - c["h"]), "moved_for_face": True})
                n_moved += 1
            continue
        for c in grp:      # no single place for the whole sentence: this state alone
            avc = _face_boxes_for_plate(tl, boxes, c) + [mark_avoid_box()]
            pc = CF.place_plate(c["w"], c["h"], (c["x"], c["y"]), avc, _hud_boxes(hud, c["start"], c["end"]), SAFE, ymax)
            if not pc:
                raise Fail("CAP-FACE-CLEAR", f"no place for plate «{c['text']}» ({lid} unit {u}, {c['start']:.2f}-{c['end']:.2f} s, {c['w']}x{c['h']} px) outside the faces on screen: shorten the sentence or split it")
            c.update({"x": pc[0], "y": pc[1], "moved_for_face": True})
            n_moved += 1
        n_split += 1
    return {"plates_moved": n_moved, "sentences_placed_per_state": n_split, "sentences": len(groups)}


def _unit_need_s(shown_words: list[str], n_words: int) -> float:
    """The least a sentence plate stays up: the larger of CAP-READING-SPEED (max(1.5 s, chars / 12 cps)) and CAP-READ-TIME (0.4 s + 0.3 s a word, its bracketed meaning counted), the two checks the plate must pass."""
    txt = " ".join(shown_words)
    gloss_words = sum(len(m.split()) for m in re.findall(r"\(([^)]*)\)", txt))
    return max(CS.read_speed_need_s(CS.visible_chars(txt)), CS.read_budget_s(n_words + gloss_words))


def caption_states(ep: Ep, tl: dict, script: dict, work: Path | None = None) -> tuple[list, list, dict, dict, list]:
    """The caption plates as DATA (no pixels): every sentence unit with its highlight windows, the HUD items, the timing method per line, the measured word widths and the
    text chunks the shaping check reads. Shared by stage_captions (which then draws the plates) and tools/animatic.py (the early preview, before any shot is rendered).
    Raises Fail (CAP-TASHKEEL, CAP-ARABIC-SHAPING). `work` is the folder the width measurement may write its page in."""
    work = Path(work) if work else ep.work
    lines = {l["id"]: l for l in script["lines"]}
    glossary = G.load(ep.root, script.get("series") or ep.series)
    states, timing_info, unit_gloss_pairs = [], {}, {}
    heal_cuts = cap_heal_cuts(ep.root, ep.id)       # R-506: plates the caption heal cut in two
    spoken = []
    for it, ln_it in _spoken(tl["items"]):
        words = display_text(lines[ln_it["line"]]["text"]).split()
        if words:
            spoken.append((it, ln_it, words))
    px = measure_words(sorted({w for _, _, ws in spoken for w in ws}), work)         # real Thmanyah widths: a sentence is wrapped to what fits, not to a guess
    margin = 2 * 0.22 * CAP_FONT_PX
    width_fn = lambda ws: sum(px[w] for w in ws) + margin * len(ws)
    starts_sorted = sorted(l_["voice_t0"] for _, l_, _w in spoken)
    for it, ln_it, words in spoken:
        line = lines[ln_it["line"]]
        weights, method = CS.syllable_weights(" ".join(words), line.get("tts_text"))
        timing = word_timing(ep.take(ln_it["line"]), words, weights)   # timing is over the SPOKEN words only; a gloss is never spoken
        timing_info[ln_it["line"]] = method
        gm = G.gloss_map(words, line.get("speaker"), G.line_entries(line, glossary))
        glued = {i for idx, e in gm.items() for i in range(idx - len(G._key(e)) + 1, idx)}   # a glossary phrase (بور لو دوسييه) is never cut in two plates
        abs_t = [(round(ln_it["voice_t0"] + a_, 3), round(ln_it["voice_t0"] + b_, 3)) for a_, b_ in timing]
        later = [t_ for t_ in starts_sorted if t_ > ln_it["voice_t0"] + 1e-6]
        room_end = (later[0] - 0.02) if later else abs_t[-1][1] + 2.0      # the plate of the line's last sentence may stay up until the next line's plate starts

        def short_fn(idx, is_last, words=words, gm=gm, abs_t=abs_t, room_end=room_end):
            """C12: this unit, as the voice leaves it on screen, is up for less than max(1.5 s, chars / 12 cps)."""
            shown = (room_end if is_last else abs_t[idx[-1] + 1][0]) - abs_t[idx[0]][0]
            txt = " ".join(_text_with_gloss(words, idx, gm))
            return shown + 1e-6 < CS.read_speed_need_s(CS.visible_chars(txt))
        units = CS.split_units(words, width_fn, CAP_LINE_W_MAX, glued, set(gm), short_fn, heal_cuts.get(ln_it["line"]))
        last = units[-1]
        need_last = CS.read_speed_need_s(CS.visible_chars(" ".join(_text_with_gloss(words, last["idx"], gm))))
        tail = max(CS.TAIL_S, abs_t[last["idx"][0]][0] + need_last - abs_t[-1][1])      # C12: the last sentence holds until it has been readable long enough (the plan made the room)
        win = CS.unit_windows(units, abs_t, abs_t[-1][1], None, tail)
        own = it if it.get("line") == ln_it["line"] else {}      # R-503: the silence the plan added before this scene's voice may be used by the FIRST plate (never by the others, never a loosened cap)
        CS.borrow_lead(win, {k_: _unit_need_s(_text_with_gloss(words, u_["idx"], gm), len(u_["idx"])) for k_, u_ in enumerate(units)}, first_max=CS.LEAD_MAX_S + float(own.get("lead_hold") or 0.0))
        for st in win:
            u = units[st["unit"]]
            first = u["idx"][0]
            local = [[j - first for j in ln_] for ln_ in u["lines"]]
            gl = [gm[j]["meaning_ar"] for j in u["idx"] if j in gm]   # the meaning stays under the sentence for every state of its unit
            unit_gloss_pairs[(ln_it["line"], st["unit"])] = [(" ".join(words[j - len(G._key(gm[j])) + 1: j + 1]).rstrip("،,.؟?!؛:"), gm[j]["meaning_ar"]) for j in u["idx"] if j in gm]
            states.append({"line": ln_it["line"], "words": [words[j] for j in u["idx"]], "lines": local, "active": st["k"], "start": st["start"], "end": st["end"],
                           "style": it.get("cap_style"), "cap_y": it.get("cap_y"), "gloss": gl, "gloss_pairs": unit_gloss_pairs[(ln_it["line"], st["unit"])], "text": " ".join(_text_with_gloss(words, u["idx"], gm)),
                           "unit": st["unit"], "word_i": st["word"], "word_start": st["word_start"], "word_end": st["word_end"], "n_lines": len(local),
                           "clause_words": u["clause_words"], "split": u["split"]})
    # one plate on screen at a time: the last sentence of a line holds its tail, but never into the next line's first plate
    states.sort(key=lambda s: s["start"])
    for a, b in zip(states, states[1:]):
        if a["line"] != b["line"]:
            a["end"] = round(min(max(a["end"], a["start"] + 0.12), b["start"] - 0.02), 3)
        else:
            a["end"] = round(min(a["end"], b["start"]), 3)
    cap_plate_ends(states, {ln_it["line"]: it["t1"] - JOIN_S for it, ln_it, _w in spoken if it.get("kind") == "scene"})
    for lid_ in dict.fromkeys(st["line"] for st in states):      # a glossed sentence that is up too briefly hands its meaning to the plates after it
        ls = [st for st in states if st["line"] == lid_]
        ug = {st["unit"]: unit_gloss_pairs[(lid_, st["unit"])] for st in ls if unit_gloss_pairs.get((lid_, st["unit"]))}
        CS.carry_glosses(ls, ug, {st["unit"]: len(st["words"]) for st in ls})
    hud = []
    label = tl.get("episode_label")
    for it in tl["items"]:
        if it["kind"] == "scene":
            base = {"id": it["id"], "day": hud_day(it, tl), "clock": it["clock"], "place": tl.get("place", ""), "t0": it["t0"], "t1": it["t1"]}
            if label and not any(h_.get("strip") for h_ in hud):
                # DESIGN.md 2.3: the first HUD plate carries «الحلقة N · the series» as its first row for STRIP_S, then the normal three rows (two plates, one handover, no gap)
                a, b = it["t0"] + JOIN_S / 2, it["t1"] - JOIN_S / 2
                cut = min(b, a + float(tl.get("strip_s", STRIP_S)))
                hud.append({**base, "strip": label, "show0": round(a, 4), "show1": round(cut, 4)})
                if cut < b - 1e-6:
                    hud.append({**base, "show0": round(cut, 4), "show1": round(b, 4)})
            else:
                hud.append(base)
    for h in hud:
        for k, v in h.items():
            if k in ("day", "clock", "place", "strip") and has_tashkeel(v):
                raise Fail("CAP-TASHKEEL", f"HUD {k} carries tashkeel")
    import cap_shaping
    chunks = [{"words": st["words"], "active": st["words"][st["active"]]} for st in states]
    chunks += [{"words": " ".join(st["gloss"]).split(), "active": None} for st in states if st["gloss"]]
    chunks += [{"words": f"{c['word']} {c['meaning']}".split(), "active": None} for st in states for c in st.get("carry", [])]   # the gloss words must join like any caption word (appended after the plates: pairs align with the plates)
    text_f = cap_shaping.shaping_problems(chunks, [])
    if text_f:
        raise Fail("CAP-ARABIC-SHAPING", "; ".join(text_f[:4]))
    return states, hud, timing_info, px, chunks


def stage_captions(ep: Ep) -> dict:
    import compose as C
    tl, script = read_json(ep.timeline_p), read_json(ep.script_p)
    states, hud, timing_info, _px, chunks = caption_states(ep, tl, script)
    caps = []
    import cap_shaping
    html = plate_html(states, hud, with_ref=True)
    pdir = ep.work / "plates"
    pdir.mkdir(parents=True, exist_ok=True)

    pairs = []

    inline_ids: set[str] = set()

    def go(pg):
        import io
        import numpy as np
        from PIL import Image
        # F-001: a bracketed meaning goes on the last row of the sentence when it fits beside it in the plate width, so a glossed sentence is as tall as a plain one
        # (a third row of 88 px left no place outside a close-up's face for the plate). Same move on the plate and on its CAP-ARABIC-SHAPING twin.
        moved = pg.evaluate("""([maxw, gap, faces]) => Promise.all(faces.map(f => document.fonts.load(f, 'هدى'))).then(() => document.fonts.ready).then(() => {
            const ids = [];
            document.querySelectorAll('.cap').forEach(c => {
                const gl = c.querySelector('.gl'); if (!gl) return;
                const lns = c.querySelectorAll('.ln'); const last = lns[lns.length - 1]; if (!last) return;
                const gs = gl.querySelector('span');
                const lw = Array.from(last.children).reduce((a, s) => a + s.getBoundingClientRect().width, 0);
                const gw = gs.getBoundingClientRect().width;
                if (lw + gap + gw + 40 <= maxw) { gs.classList.add('gl-in'); last.appendChild(gs); gl.remove(); ids.push(c.id); }
            });
            return ids; })""", [CAP_LINE_W_MAX + 2 * CAP_PAD_X, GLOSS_INLINE_GAP_PX, measure_faces()])
        inline_ids.update(moved)
        for k, st in enumerate(states):
            el = pg.locator(f"#c{k}")
            out = pdir / f"c{k:04d}.png"
            el.screenshot(path=str(out), omit_background=True)
            ref = pg.locator(f"#r{k}").screenshot(omit_background=True)
            pairs.append((np.array(Image.open(out).convert("RGBA")), np.array(Image.open(io.BytesIO(ref)).convert("RGBA"))))
            bb = el.bounding_box()
            fixed = st.get("style") == "object" or st.get("cap_y")          # a plate with its own place (the brass plate, the choice sequence) keeps its top edge
            y = (st.get("cap_y") or CAP_Y) if fixed else max(SAFE[1], CAP_Y + CAP_H1 - round(bb["height"]))   # otherwise the bottom edge stays put and a second line grows upwards
            caps.append({"line": st["line"], "text": st["text"], "gloss": st["gloss"], "active": st["words"][st["active"]], "active_index": st["active"], "word_i": st["word_i"],
                         "unit": st["unit"], "n_lines": st["n_lines"], "carry": st.get("carry", []), "clause_words": st["clause_words"], "split": st["split"],
                         "start": st["start"], "end": st["end"], "word_start": st["word_start"], "word_end": st["word_end"], "png": f"plates/c{k:04d}.png",
                         "w": round(bb["width"]), "h": round(bb["height"]), "x": round((W - bb["width"]) / 2), "y": y, "font_px_1080": CAP_FONT_PX, "style": st.get("style"), "gloss_inline": f"c{k}" in inline_ids})
        for k, h in enumerate(hud):
            el = pg.locator(f"#h{k}")
            out = pdir / f"h{k:03d}.png"
            el.screenshot(path=str(out), omit_background=True)
            bb = el.bounding_box()
            h.update({"png": f"plates/h{k:03d}.png", "w": round(bb["width"]), "h": round(bb["height"]), "x": HUD_XY[0], "y": HUD_XY[1]})
        return True
    C.chrome_page(html, ep.work, W, H, go)
    seams = [round(cap_shaping.seam_ratio(pl, rf), 5) for pl, rf in pairs]
    shape_f = cap_shaping.shaping_problems(chunks, pairs)
    if shape_f:
        raise Fail("CAP-ARABIC-SHAPING", "; ".join(shape_f[:4]))
    for c, r in zip(caps, seams):
        c["seam_ratio"] = r
    face_info = place_clear_of_faces(ep, tl, caps, hud)
    for c in caps:
        if c["x"] < SAFE[0] or c["x"] + c["w"] > SAFE[2]:
            raise Fail("CAP-SAFE", f"plate '{c['text']}' is {c['w']} px wide and leaves the safe area: shorten the line or split the words")
    write_json(ep.caps_p, {"captions": caps, "mode": "sentence", "unit_words_max": CS.UNIT_WORDS_MAX, "unit_lines_max": CS.UNIT_LINES_MAX, "font_px_1080": CAP_FONT_PX,
                           "seam_max": cap_shaping.SEAM_MAX, "timing": "estimated: voiced stretches of each take from its energy, words laid over them by weight (no ASR, banned)",
                           "timing_method": timing_info, "face_clear": face_info})
    write_json(ep.hud_p, {"hud": hud})
    return {"plates": len(caps), "hud": len(hud), **face_info}


# ------------------------------------------------------------------ stage: audio
def bed_filter(total: float) -> str:
    """A dark ambient bed that never drops out: two sines a fifth apart and low brown noise, all procedural (ffmpeg lavfi), no licence to track."""
    return (f"sine=frequency=55:sample_rate=48000:duration={total:.3f}[a];sine=frequency=82.5:sample_rate=48000:duration={total:.3f}[b];"
            f"anoisesrc=color=brown:amplitude=0.25:sample_rate=48000:duration={total:.3f}[n];"
            f"[a]volume=0.5[a2];[b]volume=0.25[b2];[n]lowpass=f=220[n2];[a2][b2][n2]amix=inputs=3:normalize=0,aformat=channel_layouts=stereo,volume=0.35[bed]")


def stage_audio_legacy(ep: Ep) -> dict:
    """The first calm mix (E01C v1/v2): kept so `mix_preset: legacy` in calm-plan.json reproduces the 'before' numbers of research/sound-e01c.md. Not used by default."""
    import compose as C
    tl = read_json(ep.timeline_p)
    total = tl["total_s"]
    wd = ep.work / "audio"
    wd.mkdir(parents=True, exist_ok=True)
    args, fl, labels = [], [], []
    n = 0
    for it, ln in _spoken(tl["items"]):
        args += ["-i", ep.take(ln["line"])]
        ms = int(round(ln["voice_t0"] * 1000))
        fl.append(f"[{n}:a]aresample=48000,aformat=channel_layouts=stereo,volume=0dB,adelay={ms}|{ms}[v{n}]")
        labels.append(f"[v{n}]")
        n += 1
    if not n:
        raise Fail("AUDIO-NO-VOICE", "no narrator lines in the timeline")
    fl.append(f"{''.join(labels)}amix=inputs={n}:normalize=0:duration=longest,apad=whole_dur={total:.3f},atrim=0:{total:.3f},asplit=3[voice][vsc][vsc2]")
    fl.append(bed_filter(total))
    fl.append("[bed][vsc]sidechaincompress=threshold=0.02:ratio=9:attack=15:release=500:makeup=1[bedd]")   # about -10 dB under the voice
    import calm_sfx    # C3 + C4 + C5: transition sounds, the horn, the choice pops and the foley, from sfx.json (built from the plan, the timeline and the shot specs)
    sfx = calm_sfx.build(ep.id, read_json(ep.plan_p), tl)
    write_json(ep.work / "sfx.json", sfx)
    reg = calm_sfx.parse_licences()
    lic = sorted({p for p in (calm_sfx.licence_problems(c["file"], c["licence_id"], reg) for c in sfx["cues"]) if p})
    if lic:
        raise Fail("AUDIO-LICENCE", "; ".join(lic[:3]) + " (nothing unlicensed is mixed)")
    cues = [c for c in sfx["cues"] if c["t"] < total - 0.05]
    for k, c in enumerate(cues):
        args += ["-i", ep.root / c["file"]]
        ms = int(round(c["t"] * 1000))
        cut = f"atrim=0:{c['dur']:.3f},afade=t=out:st={max(0.0, c['dur'] - 0.12):.3f}:d=0.12," if c.get("dur") else ""
        fl.append(f"[{n + k}:a]aresample=48000,aformat=channel_layouts=stereo,{cut}volume={c['gain_db']}dB,adelay={ms}|{ms}[x{k}]")
    if cues:
        fl.append(f"{''.join(f'[x{k}]' for k in range(len(cues)))}amix=inputs={len(cues)}:normalize=0:duration=longest,apad=whole_dur={total:.3f},atrim=0:{total:.3f}[sfxbus]")
        fl.append("[sfxbus][vsc2]sidechaincompress=threshold=0.02:ratio=4:attack=15:release=400:makeup=1[sfxd]")      # the whole sfx bus ducks under the narrator, as in compose.py
        fl.append("[voice][bedd][sfxd]amix=inputs=3:normalize=0:duration=longest,acompressor=threshold=0.03:ratio=8:attack=10:release=300:makeup=3,atrim=0:%.3f[o]" % total)
    else:
        fl.append("[vsc2]anullsink")
        fl.append("[voice][bedd]amix=inputs=2:normalize=0:duration=longest,acompressor=threshold=0.03:ratio=8:attack=10:release=300:makeup=3,atrim=0:%.3f[o]" % total)   # loudness range <= 5 LU: a compressor, loudnorm alone cannot narrow it
    premix = wd / "premix.wav"
    ff([*args, "-filter_complex_script", _graph_file(wd / "audio.filtergraph", fl), "-map", "[o]", "-ar", "48000", "-c:a", "pcm_f32le", premix])
    r = ff(["-i", premix, "-af", f"loudnorm=I={LOUD_I}:TP={LOUD_TP}:LRA={LOUD_LRA}:print_format=json", "-f", "null", "-"], log="info")   # loudnorm prints its measurement at info level
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr, re.S)
    if not m:
        raise Fail("TOOL-ERROR", "loudnorm printed no measurement")
    ms = json.loads(m.group(0))
    ln = (f"loudnorm=I={LOUD_I}:TP={LOUD_TP}:LRA={LOUD_LRA}:measured_I={ms['input_i']}:measured_TP={ms['input_tp']}:measured_LRA={ms['input_lra']}:"
          f"measured_thresh={ms['input_thresh']}:offset={ms['target_offset']}:linear=true")
    ff(["-i", premix, "-af", f"{ln},aresample=48000", "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", ep.mix])
    loud = C.measure_loudness(ep.mix)
    write_json(ep.work / "audio.json", {"voice_lines": n, "sfx_cues": len(cues), "loudness": loud, "bed": "procedural: 55 Hz + 82.5 Hz sines + brown noise (ffmpeg lavfi), ducked by sidechaincompress", "note": VOICE_LUFS_NOTE})
    return {"integrated_lufs": loud["integrated_lufs"], "true_peak_dbtp": loud["true_peak_dbtp"], "lines": n}


def stage_audio(ep: Ep) -> dict:
    """Phone-first mix (owner, 2026-10-25, C9): per-source cleanup and levels measured the way a phone plays them, a pad bed a phone can hear, dialogue-first ducking from the voice,
    final -14 LUFS. The chain and its presets live in tools/calm_mix.py; `mix_preset: legacy` in calm-plan.json runs the old chain. Writes mix.wav, audio/stems/, audio.json."""
    import compose as C
    plan = read_json(ep.plan_p)
    preset = plan.get("mix_preset", "phone-first")
    if preset == "legacy":
        return stage_audio_legacy(ep)
    import calm_mix
    import calm_sfx
    tl = read_json(ep.timeline_p)
    if not any(True for _ in _spoken(tl["items"])):
        raise Fail("AUDIO-NO-VOICE", "no narrator lines in the timeline")
    sfx = calm_sfx.build(ep.id, plan, tl)
    write_json(ep.work / "sfx.json", sfx)
    reg = calm_sfx.parse_licences()
    lic = sorted({p for p in (calm_sfx.licence_problems(c["file"], c["licence_id"], reg) for c in sfx["cues"]) if p})
    if lic:
        raise Fail("AUDIO-LICENCE", "; ".join(lic[:3]) + " (nothing unlicensed is mixed)")
    if preset not in calm_mix.PRESETS:
        raise Fail("AUDIO-MODE", f"mix_preset {preset!r} is not one of {', '.join(sorted(calm_mix.PRESETS))} or legacy")
    rep = calm_mix.render(ep, preset)
    loud = C.measure_loudness(ep.mix)
    import audio_checks as AC
    fails, metrics = AC.run_checks(ep.work / "audio" / "stems", ep.mix)
    write_json(ep.work / "audio.json", {"voice_lines": rep["voice_lines"], "sfx_cues": rep["sfx_cues"], "loudness": loud, "mix_preset": preset, "master_gain_db": rep["master_gain_db"], "limiter_used": rep["limiter_used"],
                                        "bed": "pad (numpy, deterministic): Am / F / Am, notes 110 Hz and up with harmonics to 2.5 kHz, ducked 9 dB under every voice (calm_mix.synth_pad)", "audio_checks": metrics,
                                        "note": f"voice {rep['voice_phone_lufs']} LUFS through the phone simulation, bed {rep['bed_gain_db']} dB set 15 LU under it"})
    return {"integrated_lufs": loud["integrated_lufs"], "true_peak_dbtp": loud["true_peak_dbtp"], "lines": rep["voice_lines"], "audio_checks": "pass" if not fails else fails[:2]}


# ------------------------------------------------------------------ stage: assemble
VFX_XFADE = {"flash": "fadewhite", "ink_wipe": "wiperight", "smear": "hblur", "iris": "circleopen", "page_turn": "revealright", "ink_fade": "fadeblack", "iris_close": "circleclose"}


def _choice_card(ep: Ep) -> dict:
    """The card of the choice_split shot as it was recorded (work/shots/<ep>-choice/calm.json); a stale card (the old choice_card) is refused, never guessed."""
    c = read_json(ep.root / "work" / "shots" / f"{ep.id}-choice" / "calm.json")
    if c.get("template") != "choice_split":
        raise Fail("ASM-CHOICE-STALE", f"work/shots/{ep.id}-choice is a {c.get('template')}, the plan asks for choice_split: rebuild that card shot (daily.py shots)")
    return c["card"]


def choice_top_filters(it: dict, k: int, extra: dict) -> list[str]:
    """C4: the top half of the choice sequence (1080 x TOP_H, it['dur'] s): the two close-ups cut into each other, a crossfade VFX at every cut, each close-up a slow drift
    (a crop window moving over a rendered shot, so the top half keeps moving). Segment j shows its clip from where that clip last stopped; a clip that runs out holds its last frame."""
    sp = it["split"]
    top = {c["id"]: c for c in sp["top"]}
    bounds = [0.0] + [c["t"] for c in sp["cuts"]] + [it["dur"]]
    clips = [sp["first"]] + [c["clip"] for c in sp["cuts"]]
    m = len(clips)
    uses = {cid: clips.count(cid) for cid in top}
    fl, cur = [], {cid: 0.0 for cid in top}
    for cid, nuse in uses.items():
        nn = max(nuse, 1)
        fl.append(f"[{extra[cid]}:v]scale={W}:{H}:flags=bicubic,setsar=1,format=yuv420p,tpad=stop_mode=clone:stop_duration=12,split={nn}" + "".join(f"[tp{k}{cid}{j}]" for j in range(nn)))
    seen = {cid: 0 for cid in top}
    lens = []
    for j, cid in enumerate(clips):
        d = bounds[j + 1] - bounds[j]
        ln = d + (XD / 2 if m > 1 else 0.0) if j == 0 else (d + XD / 2 if j == m - 1 else d + XD)
        c = top[cid]["crop"]
        cw = int(c["w"]) // 2 * 2
        ch = int(round(cw * TOP_H / W)) // 2 * 2
        fl.append(f"[tp{k}{cid}{seen[cid]}]trim=start={cur[cid]:.4f}:duration={ln:.4f},setpts=PTS-STARTPTS,fps={FPS},"
                  f"crop=w={cw}:h={ch}:x='{c['x']}+{c.get('dx', 0)}*t/{max(ln, 0.1):.4f}':y='{c['y']}+{c.get('dy', 0)}*t/{max(ln, 0.1):.4f}',scale={W}:{TOP_H}:flags=lanczos,setsar=1,format=yuv420p[tg{k}_{j}]")
        seen[cid] += 1
        cur[cid] += d
        lens.append(ln)
    acc, acc_len = f"tg{k}_0", lens[0]
    for j in range(1, m):
        nxt = f"tx{k}_{j}" if j < m - 1 else f"top{k}"
        xf = VFX_XFADE.get(sp["cuts"][j - 1].get("vfx", "flash"), "fadewhite")
        fl.append(f"[{acc}][tg{k}_{j}]xfade=transition={xf}:duration={XD:.4f}:offset={acc_len - XD:.4f}[{nxt}]")
        acc_len = acc_len - XD + lens[j]
        acc = nxt
    if m == 1:
        fl.append(f"[{acc}]null[top{k}]")
    return fl


def stage_assemble(ep: Ep) -> dict:
    import compose as C
    tl, caps, hud = read_json(ep.timeline_p), read_json(ep.caps_p)["captions"], read_json(ep.hud_p)["hud"]
    miss = [it["video"] for it in tl["items"] if not (ep.root / it["video"]).is_file()]
    tops = {}      # C4: the two close-ups cut into the top half of the choice sequence (clip id -> its rendered shot)
    for it in tl["items"]:
        for c in (it.get("split") or {}).get("top", []):
            tops[c["id"]] = ep.root / "work" / "shots" / f"{ep.id}-{c['shot']}" / "out" / f"{ep.id}-{c['shot']}.mp4"
    miss += [str(v.relative_to(ep.root)) for v in tops.values() if not v.is_file()]
    if miss:
        raise Fail("ASM-SHOT-VIDEO", f"no render for: {', '.join(miss[:4])} (shots and cards are recorded before composing)")
    if not ep.mix.is_file():
        raise Fail("ASM-AUDIO", "mix.wav missing: run `audio` first")
    poster = build_poster(ep, read_json(ep.plan_p))       # R-501: frame 0 is the grid poster, never black; built first, it is one more input of the graph
    args, fl = [], []
    n_items = len(tl["items"])
    for k, it in enumerate(tl["items"]):
        args += [*C.hw_in(), "-i", ep.root / it["video"]]
        sp = it.get("split")
        hold = float(it.get("hold") or 0.0) + float(it.get("read_hold") or 0.0)   # the last `hold` s are the last played frame, held: same length, so no voice, caption or join moves; read_hold (C12) is the plan's reading pause after the shot's own length
        if hold > 0:
            fl.append(f"[{k}:v]trim=duration={it['dur'] - hold:.4f},setpts=PTS-STARTPTS,fps={FPS},tpad=stop_mode=clone:stop_duration={hold:.4f},scale={W}:{H}:flags=bicubic,setsar=1,format=yuv420p[{'sc' if sp else 's'}{k}]")
        else:
            fl.append(f"[{k}:v]trim=duration={it['dur']:.4f},setpts=PTS-STARTPTS,fps={FPS},scale={W}:{H}:flags=bicubic,setsar=1,format=yuv420p[{'sc' if sp else 's'}{k}]")
    extra = {}
    for cid, vp in tops.items():
        args += [*C.hw_in(), "-i", vp]
        extra[cid] = n_items + len(extra)
    for k, it in enumerate(tl["items"]):
        if it.get("split"):
            fl += choice_top_filters(it, k, extra)
            fl.append(f"[sc{k}][top{k}]overlay=0:0:format=auto,format=yuv420p[s{k}]")
    acc, length = "s0", tl["items"][0]["dur"]
    for k in range(1, len(tl["items"])):
        nxt = f"j{k}"
        fl.append(f"[{acc}][s{k}]xfade=transition={tl['items'][k].get('join_in', {}).get('xfade', 'fadeblack')}:duration={JOIN_S:.4f}:offset={length - JOIN_S:.4f}[{nxt}]")   # C3: the cut type of the join picks the visual
        length += tl["items"][k]["dur"] - JOIN_S
        acc = nxt
    n = n_items + len(extra)
    idx = n
    for c in caps:
        args += ["-i", ep.work / c["png"]]
        nxt = f"c{idx}"
        fl.append(f"[{acc}][{idx}:v]overlay=x={c['x']}:y={c['y']}:enable='between(t,{c['start']},{c['end']})':format=auto[{nxt}]")
        acc, idx = nxt, idx + 1
    for h in hud:
        args += ["-i", ep.work / h["png"]]
        nxt = f"c{idx}"
        fl.append(f"[{acc}][{idx}:v]overlay=x={h['x']}:y={h['y']}:enable='between(t,{hud_window(h)[0]},{hud_window(h)[1]})':format=auto[{nxt}]")
        acc, idx = nxt, idx + 1
    for it in tl["items"]:    # C4: the question and each choice light up as the narrator reads them (lit plates over the card, bottom half)
        if it.get("split"):
            import calm_cards
            for lp in calm_cards.lit_plates(_choice_card(ep), ep.work / "plates" / "lit"):
                st = next(l for l in it["split"]["lit"] if l["state"] == lp["state"])
                args += ["-i", ep.work / "plates" / "lit" / lp["png"]]
                nxt = f"c{idx}"
                fl.append(f"[{acc}][{idx}:v]overlay=x={lp['x']}:y={lp['y']}:enable='between(t,{it['t0'] + st['t0']:.3f},{it['t0'] + st['t1']:.3f})':format=auto[{nxt}]")
                acc, idx = nxt, idx + 1
    args += ["-loop", "1", "-framerate", str(FPS), "-t", f"{GP.POSTER_HOLD_S + GP.POSTER_FADE_S:.3f}", "-i", poster["png"]]      # R-501: the grid poster covers frame 0 for POSTER_HOLD_S, then fades into the opening (above the plates, under the mark)
    fl.append(f"[{idx}:v]format=yuva420p,fade=t=out:st={GP.POSTER_HOLD_S:.3f}:d={GP.POSTER_FADE_S:.3f}:alpha=1[pz]")
    fl.append(f"[{acc}][pz]overlay=0:0:eof_action=pass:format=auto[pzo]")
    acc, idx = "pzo", idx + 1
    args += ["-i", WM.ensure_mark()]      # the last compose step (the owner 2026-10-25): the small NJ mark over every frame, in the one final encode
    fl += WM.filter_chain(acc, idx, "wm")
    acc, idx = "wm", idx + 1
    args += ["-i", ep.mix]
    fl.append(f"[{acc}]format=yuv420p[vout]")
    T = tl["total_s"]
    C.ff([*args, "-filter_complex_script", _graph_file(ep.work / "assemble.filtergraph", fl), "-map", "[vout]", "-map", f"{idx}:a", "-t", f"{T:.4f}", "-r", str(FPS), *C.venc_args(), "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
          "-movflags", "+faststart", ep.out])
    vd = float(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=duration", "-of", "csv=p=0", str(ep.out)], capture_output=True, text=True).stdout.strip() or 0)
    if abs(vd - T) > 0.25:   # E01C 2026-10-25: a stale, shorter shot ended the graph at 12.5 s while the audio ran 101.8 s, and every stage still said ok
        raise Fail("ASSEMBLE-SHORT", f"the video stream is {vd:.2f} s but the timeline is {T:.2f} s: a shot's file is shorter than its planned length (rebuild the shots) or an input ended early")
    WM.write_sidecar(ep.work)
    cover = stage_cover(ep, read_json(ep.plan_p))
    return {"duration_s": round(probe_dur(ep.out), 3), "items": n_items, "plates": len(caps), "watermark": "top-right", **cover}


def build_poster(ep: Ep, plan: dict) -> dict:
    """R-501: the grid poster (tools/grid_poster.py) of this episode: cover.png and cover.jpg in the episode folder. Frame 0 of episode.mp4 and every platform's cover are this image."""
    try:
        return GP.build(ep.id, ep.root, ep.work / "cover.png", ep.plan_p, scratch=ep.work / "cover-build")
    except SystemExit as e:
        raise Fail("ASM-COVER", f"the grid poster was not made: {e}")
    except Exception as e:      # a missing browser or font
        raise Fail("ASM-COVER", f"the grid poster was not made: {e}")


def stage_cover(ep: Ep, plan: dict) -> dict:
    """DESIGN.md 2.6 + R-501: cover.json for the uploaders (tools/ig.py, fb.py, yt.py read it): {png, jpg, hook, scene, fallback_frame_offset_s}. The poster itself was built by stage_assemble
    (it is frame 0 of the episode); the cover is that same image, so the offset fallback is 0 s."""
    cp = ep.work / "cover.png"
    if not cp.is_file():
        raise Fail("ASM-COVER", "cover.png was not made")
    n = episode_number(plan.get("episode"))
    write_json(ep.work / "cover.json", {"png": "cover.png", "jpg": "cover.jpg", "size": [W, H], "numeral": GP.ar_num(n) if n else plan.get("day", ""), "hook": GP.hook_text(plan),
                                        "scene": GP.pick_scene(plan)["id"], "grid_poster": True, "fallback_frame_offset_s": 0.0})
    return {"cover": "cover.png"}


# ------------------------------------------------------------------ stage: gate
def episode_shotlist(ep: Ep, tl: dict, plan: dict | None = None) -> dict:
    """The shapes qg_checks.check_calm_declared reads: wrapper {recap, day_card, choice_card, follow_card: {t0, t1}} and per-shot `subjects`."""
    it = {x["id"]: x for x in tl["items"]}
    w = lambda k: {"t0": it[k]["t0"], "t1": it[k]["t1"]}
    wrapper = {"day_card": w("day"), "choice_card": w("choice"), "follow_card": w("follow")}
    if "recap" in it:
        wrapper = {"recap": w("recap"), **wrapper}
    n = episode_number((plan or {}).get("episode") if plan else tl.get("episode"))
    return {"profile": "calm", "wrapper": wrapper, "episode_no": n, "recap_from": RECAP_FROM_EPISODE,
            "shots": [{"id": x["id"], "subjects": [s for s in x.get("subjects", []) if s]} for x in tl["items"] if x["kind"] == "scene"]}


def length_check(d: float) -> tuple[bool, str, str | None]:
    """CALM-LENGTH: a floor and a soft warning, no ceiling (the owner 2026-10-25: length is whatever suits the story). Returns (ok, detail, warning)."""
    detail = f"{d:.1f} s (floor {LEN_MIN_S:g} s; no upper cap, the owner 2026-10-25: the story sets the length)"
    warn = f"{d:.1f} s is over the {LEN_WARN_S:g} s of the harvested reels: confirm this is the story's length" if d > LEN_WARN_S else None
    return d >= LEN_MIN_S, detail + (f" - WARNING: {warn}" if warn else ""), warn


def cap_plate_ends(states: list[dict], scene_end: dict) -> None:
    """E04 Q04/Q05: a line's last plate must not stay up over the NEXT scene's picture (Lead's words over Hero's face at the s14/s15 join). It ends where its own scene's join begins
    (scene t1 minus half a join), but only when it has then been up long enough to read (CS.read_speed_need_s); otherwise it keeps its reading time and the planner's hold is the cure."""
    for lid_ in dict.fromkeys(st["line"] for st in states):
        ls = [st for st in states if st["line"] == lid_]
        cap = scene_end.get(lid_)
        last = ls[-1]
        if cap is None or last["end"] <= cap + 1e-6:
            continue
        # the plate has been up since its UNIT began (its states only move the highlight): measuring from the last state's start never let a long sentence be capped (E04 round 3: L14's
        # last state started 1.0 s before the join, the 1.5 s floor refused, and «إنها تتأخر ثانيتين» stayed over s15)
        unit_start = min(st["start"] for st in ls if st.get("unit") == last.get("unit"))
        if cap - unit_start + 1e-6 >= CS.read_speed_need_s(CS.visible_chars(last.get("text") or " ".join(last["words"]))):
            last["end"] = round(cap, 3)


def hud_day(it: dict, tl: dict) -> str:
    """The HUD's day row of a scene: the scene's own `day` (plan scene key, E04 Q06: night one is day three) or else the episode's."""
    return "اليوم " + str(it.get("day") or tl["day"]).translate(AR_DIGITS)


def hud_problems(tl: dict, huds: list[dict], recap_tag: str | None = None) -> list[str]:
    """CALM-HUD: the HUD plates (one, or the strip plate and the plate that takes over from it) cover every story scene without a gap; from E02 (the timeline carries an `episode_label`)
    the first HUD plate also carries the series strip «الحلقة N · the series» for STRIP_S, it starts within the first STRIP_S of the episode, and the recap card carries the same words as its tag."""
    f = []
    for it in tl["items"]:
        if it["kind"] != "scene":
            continue
        a, b = it["t0"] + JOIN_S / 2, it["t1"] - JOIN_S / 2
        spans = sorted(hud_window(h) for h in huds if hud_window(h)[1] > a and hud_window(h)[0] < b)
        at, gap = a, False
        for x0, x1 in spans:
            if x0 > at + 0.02:
                gap = True
                break
            at = max(at, x1)
        if gap or at < b - 0.02 or not spans:
            f.append(f"scene {it['id']} has no HUD plate over {a:.2f}..{b:.2f} s")
    label = tl.get("episode_label")
    if label:
        strips = [h for h in huds if h.get("strip")]
        if len(strips) != 1 or strips[0]["strip"] != label:
            f.append(f"the first HUD plate must carry the series strip «{label}» (found {len(strips)} strip plate(s))")
        else:
            w0, w1 = hud_window(strips[0])
            first = next((it for it in tl["items"] if it["kind"] == "scene"), None)
            scene_len = (first["t1"] - first["t0"] - JOIN_S) if first else 0
            if w0 > STRIP_S + 1e-6:
                f.append(f"the series strip starts at {w0:.2f} s: it belongs inside the first {STRIP_S:g} s")
            if abs((w1 - w0) - min(float(tl.get("strip_s", STRIP_S)), scene_len)) > 0.06:
                f.append(f"the series strip is up {w1 - w0:.2f} s (it stays {STRIP_S:g} s, or the whole first scene when that is shorter)")
        rc = next((it for it in tl["items"] if it["id"] == "recap"), None)
        if rc is not None and rc.get("tag") != label:
            f.append(f"the recap card's tag is {rc.get('tag')!r}, not «{label}»")
        if rc is not None and recap_tag != label:
            f.append(f"the recap card shot carries tag {recap_tag!r}, not «{label}»: tools/daily.py must build the recap card from calm_compose.recap_card_params(plan)")
    return f


def hook_3s_problems(tl: dict, plan: dict) -> list[str]:
    """CALM-HOOK-3S (DESIGN.md 2.1): a voiced line, or a story event the plan declares (a foley cue of a scene), starts before HOOK_S. Reads timeline.json and the plan, no render."""
    voiced = [ln["voice_t0"] for _, ln in _spoken(tl["items"])]
    events = []
    by_id = {s_["id"]: s_ for s_ in plan.get("scenes", [])}
    for it in tl["items"]:
        if it["kind"] == "scene":
            events += [round(it["t0"] + float(fy.get("at", 0.0)), 3) for fy in by_id.get(it["id"], {}).get("foley", []) or []]
    first = min(voiced + events) if (voiced or events) else None
    if first is None:
        return ["no voiced line and no declared story event: the first seconds are empty"]
    if first >= HOOK_S:
        return [f"the first voiced line or declared story event starts at {first:.2f} s (it must start before {HOOK_S:g} s)"]
    return []


CARD_PUSH = 1.0 + CC.PUSH_PCT / 100.0      # a card's clip pushes in 4 % about the frame centre (calm_cards.encode): its text boxes are measured on the still, before the push


def _pushed(b: dict) -> dict:
    """A measured box (x0, y0, x1, y1) after the card's push-in, as x, y, w, h: scaled about the frame centre."""
    cx, cy = W / 2, H / 2
    x0, x1, y0, y1 = (cx + (b["x0"] - cx) * CARD_PUSH, cx + (b["x1"] - cx) * CARD_PUSH, cy + (b["y0"] - cy) * CARD_PUSH, cy + (b["y1"] - cy) * CARD_PUSH)
    return {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0}


def card_text_boxes(ep: Ep, tl: dict) -> tuple[list[dict], list[str]]:
    """The measured text boxes of every card (card-measure.json) and every intro's placed boxes (intro-measure.json), after the card push-in, as x, y, w, h in screen px: what
    WATERMARK-CLEAR keeps clear. Returns (boxes, missing): a card or intro with no measure file is a failure for the caller, never a skip."""
    out, missing = [], []
    for it in tl["items"]:
        d = ep.root / "work" / "shots" / it["shot"] / "out"
        if it["kind"] in ("card", "intro"):
            mp = d / ("card-measure.json" if it["kind"] == "card" else "intro-measure.json")
            if not mp.is_file():
                missing.append(f"{it['id']}: {mp.name} is missing, so its text cannot be proved clear of the mark")
                continue
            m = read_json(mp)
            for b in (m.get("boxes", []) if it["kind"] == "card" else m.get("placed_boxes", [])):
                out.append({**_pushed(b), "what": f"{it['id']} {str(b.get('text') or b.get('layer') or '')[:12]}"})
    return out, missing


def stage_gate(ep: Ep, skip_render: bool = False) -> dict:
    import compose as C
    tl, caps = read_json(ep.timeline_p), read_json(ep.caps_p)
    plan = read_json(ep.plan_p)
    checks, fails = [], []

    def rec(cid, ok, detail):
        checks.append({"id": cid, "status": "pass" if ok else "fail", "detail": detail})
        if not ok:
            fails.append(f"{cid} {detail}")
    d = probe_dur(ep.out)
    ok, detail, warn = length_check(d)
    rec("CALM-LENGTH", ok, detail)
    if warn:
        checks[-1]["warning"] = warn
    vis = [str(v) for _, v in _visible_strings(plan)] + [c["text"] for c in caps["captions"]]
    rec("CALM-NO-TASHKEEL", not any(has_tashkeel(v) for v in vis), f"{len(vis)} visible strings checked")
    loud = C.measure_loudness(ep.out)
    dv = SOUND["delivery"]["instagram"]        # one file goes to Instagram, Facebook and YouTube: one set of limits (-15..-13 LUFS, <= -1.0 dBTP, unchanged)
    rec("CALM-LOUDNESS", loud["integrated_lufs"] is not None and abs(loud["integrated_lufs"] - dv["lufs_target"]) <= dv["tolerance_lu"] and (loud["true_peak_dbtp"] or 0) <= dv["true_peak_max_dbtp"], f"{loud}")
    # C9 phone-first audio checks, on the stems of the mix and the AAC that was actually delivered (a missing stem is a failure, never a skip)
    try:
        import audio_checks as AC
        sd = ep.work / "audio" / "stems"
        if not (sd / "voice.wav").is_file():
            for cid in ("AUDIO-DIALOGUE-CLARITY", "AUDIO-MONO", "AUDIO-PEAK"):
                rec(cid, False, "audio/stems is missing: run `audio` first (the legacy chain keeps no stems, so a legacy episode fails here on purpose)")
        else:
            final = ep.work / "audio" / "final.wav"
            ff(["-i", ep.out, "-vn", "-c:a", "pcm_f32le", "-ar", "48000", final])
            afails, ametrics = AC.run_checks(sd, final)
            write_json(ep.work / "audio" / "checks.json", {"fails": afails, "metrics": ametrics})
            for cid in ("AUDIO-DIALOGUE-CLARITY", "AUDIO-MONO", "AUDIO-PEAK"):
                mine = [b.split(" ", 1)[1] for b in afails if b.startswith(cid + " ")]
                rec(cid, not mine, "; ".join(mine[:3]) or {"AUDIO-DIALOGUE-CLARITY": f"voice over music+sfx on a phone simulation: median {ametrics['dialogue_clarity']['median_db']} dB, weakest tenth {ametrics['dialogue_clarity']['p10_db']} dB",
                                                         "AUDIO-MONO": f"mono fold-down loses {ametrics['mono']['mono_loss_lu']} LU, correlation p05 {ametrics['mono']['corr_p05']}",
                                                         "AUDIO-PEAK": f"true peak {ametrics['peak']['true_peak_dbtp']} dBTP, {ametrics['peak']['clipped_samples']} clipped samples"}[cid])
    except ImportError:
        rec("AUDIO-DIALOGUE-CLARITY", False, "audio_checks.py not available")
    r = ff(["-i", ep.out, "-vn", "-af", f"silencedetect=n=-45dB:d={SILENCE_MAX_S}", "-f", "null", "-"], check=False)
    gaps = re.findall(r"silence_duration: ([\d.]+)", r.stderr)
    rec("CALM-NO-SILENCE", not gaps, f"{len(gaps)} gap(s) over {SILENCE_MAX_S} s")
    cp = sorted(caps["captions"], key=lambda c: c["start"])
    rec("CALM-ONE-PLATE", all(b["start"] >= a["end"] - 1e-6 for a, b in zip(cp, cp[1:])), f"{len(cp)} plates, never two at once")
    import cap_shaping
    shp = cap_shaping.shaping_problems([{"words": G.strip_gloss(c["text"]).split(), "active": c.get("active")} for c in cp], [])
    shp += [f"plate '{c['text']}' seam_ratio {c.get('seam_ratio')} over {cap_shaping.SEAM_MAX}" for c in cp if c.get("seam_ratio") is None or c["seam_ratio"] > cap_shaping.SEAM_MAX]
    rec("CAP-ARABIC-SHAPING", not shp, "; ".join(shp[:3]) or f"{len(cp)} plates: whole words, joining intact, outline never cuts a letter (max seam {max((c['seam_ratio'] for c in cp), default=0)})")
    script_lines = read_json(ep.script_p)["lines"]
    shown_lines = {l["id"]: {**l, "text": display_text(l["text"])} for l in script_lines}
    recomputed = {}      # the voice's word times, recomputed from the takes and the timeline, independent of what the plates stored
    for _, ln_it in _spoken(tl["items"]):
        take = ep.take(ln_it["line"])
        lw = shown_lines[ln_it["line"]]["text"].split()
        if take.is_file() and lw:
            wt, _m = CS.syllable_weights(" ".join(lw), shown_lines[ln_it["line"]].get("tts_text"))
            recomputed[ln_it["line"]] = [(ln_it["voice_t0"] + a_, ln_it["voice_t0"] + b_) for a_, b_ in word_timing(take, lw, wt)]
    fs = CS.check_plates(cp, shown_lines, recomputed)
    rec("CAP-FULL-SENTENCE", not [x for x in fs if x.startswith("CAP-FULL-SENTENCE")],
        "; ".join(x for x in fs if x.startswith("CAP-FULL-SENTENCE"))[:600] or f"{len(cp)} plates: every plate shows a whole sentence or clause (at most {CS.UNIT_WORDS_MAX} words, {CS.UNIT_LINES_MAX} lines), exactly one whole word highlighted, in order, within {CS.SYNC_TOL_S} s of the voice ({len(recomputed)} lines recomputed)")
    rec("CAP-READ-TIME", not [x for x in fs if x.startswith("CAP-READ-TIME")],
        "; ".join(x for x in fs if x.startswith("CAP-READ-TIME"))[:600] or f"every sentence stays up at least {CS.READ_BASE_S} s + {CS.READ_PER_WORD_S} s a word, and holds {CS.TAIL_S} s after its line when the next plate allows")
    rec("CAP-READING-SPEED", not [x for x in fs if x.startswith("CAP-READING-SPEED")],
        "; ".join(x for x in fs if x.startswith("CAP-READING-SPEED"))[:600] or f"every plate stays up at least max({CS.READ_MIN_S} s, characters / {CS.READ_CPS:g} cps) (a judgement rate, cap_sentence.READ_CPS), counting the time its meaning is carried on")
    tl_ids = {it["id"]: it for it in tl["items"]}
    fb = face_boxes_by_item(ep, tl)
    ff_ = CF.check_plates(cp, lambda p: _face_boxes_for_plate(tl, fb, p))
    nfaces = sum(len(v) for v in fb.values())
    rec("CAP-FACE-CLEAR", not ff_, "; ".join(ff_[:3]) or f"{len(cp)} plates clear of {nfaces} face boxes (face {CF.FACE_W_M} x {CF.FACE_H_M} m + {CF.FACE_PAD_PX} px, from each shot's rig trace; overlaps under {FACE_GRACE_S} s of a join ignored); {sum(1 for c in cp if c.get('moved_for_face'))} plates were moved to get there")
    series_ = read_json(ep.script_p).get("series") or ep.series
    glossary = G.load(ep.root, series_)
    lex = G.lexicon(ep.root, series_)
    by_id = {l["id"]: l for l in script_lines}
    gp = G.check_captions(cp, by_id, glossary)
    gp += [x for k, v in _visible_strings(plan) for x in G.check_text(str(v), None, glossary, where=f"{k} ")]
    gp += G.check_script_tags(script_lines, glossary)
    gp += [x for c in cp for x in G.check_foreign(c["text"], (by_id.get(c["line"]) or {}).get("speaker"), glossary, lex["foreign_keys"], f"plate {c['line']} ", lex["loanwords"])]
    gp += [x for k, v in _foreign_checked_strings(plan) for x in G.check_foreign(str(v), None, glossary, lex["foreign_keys"], f"{k} ", lex["loanwords"])]
    rec("CAP-FOREIGN-GLOSS", not gp, "; ".join(gp[:3]) or f"{len(glossary)} glossary words and {sum(len(G.foreign_tags(l)) for l in script_lines)} writer tags: every one shown carries its «(meaning)», every own-language word of a speaker is tagged")
    vis_words = [w for l in script_lines for w in shown_lines[l["id"]]["text"].split()] + [w for k, v in _visible_strings(plan) for w in re.split(r"[\s#_]+", str(v)) if re.search("[ء-ي]", w)]
    odd = G.review_words(vis_words, lex["corpus"], glossary, lex["arabic_ok"], lex["names"])      # C11: the review list; the lexicon excludes the episode scripts, so a script cannot vouch for its own words
    write_json(ep.work / "review" / "arabic-words.json", {"episode": ep.id, "note": "caption and post-caption words the series bibles never used: say Arabic (glossary.json arabic_words), a name (names), or add a glossary entry", "words": odd})
    rec("CAP-ARABIC-REVIEW", True, (f"{len(odd)} caption word(s) the series text has never used, for a human to read (may be fine): {' '.join(odd[:12])}") if odd else "every caption word is a word the series text already uses or a glossary word")
    if odd:
        checks[-1]["warning"] = f"words not recognised as series Arabic: {' '.join(odd[:12])}"
    rec("CALM-PLATE-SAFE", all(SAFE[0] <= c["x"] and c["x"] + c["w"] <= SAFE[2] and SAFE[1] <= c["y"] and c["y"] + c["h"] <= SAFE[3] + 100 for c in cp), "inside the Reels safe area")
    huds = read_json(ep.hud_p)["hud"]
    recap_tag = None
    rp = ep.root / "work" / "shots" / f"{ep.id}-recap" / "calm.json"
    if tl.get("episode_label") and rp.is_file():
        recap_tag = ((read_json(rp).get("card") or {}).get("text") or {}).get("tag")
    hp = hud_problems(tl, huds, recap_tag)
    rec("CALM-HUD", not hp, "; ".join(hp[:3]) or ("a HUD plate covers every story scene" + (f"; the first one carries the series strip «{tl['episode_label']}» for {tl.get('strip_s', STRIP_S):g} s and the recap card says the same" if tl.get("episode_label") else "")))
    hk = hook_3s_problems(tl, plan)
    rec("CALM-HOOK-3S", not hk, "; ".join(hk) or f"the first voiced line or declared story event starts before {HOOK_S:g} s ({min([ln['voice_t0'] for _, ln in _spoken(tl['items'])] or [0]):.2f} s)")
    if algo_on(plan):       # DESIGN.md 2.4 and 2.6, from E02: the follow line is a statement, the cover still exists
        fp = ep.root / "work" / "shots" / f"{ep.id}-follow" / "calm.json"
        fline = ((read_json(fp).get("card") or {}).get("text") or {}).get("line") if fp.is_file() else None
        want = follow_card_line(plan)
        fprob = ([f"no follow card shot at {fp}"] if fline is None else CC.ask_problems(fline, "follow card line", False)) + ([f"the follow card says «{fline}», not «{want}»"] if fline is not None and fline != want else [])
        rec("CALM-FOLLOW-LINE", not fprob, "; ".join(fprob[:3]) or f"the follow card says «{fline}»")
        cp_ = ep.work / "cover.png"
        cprob = []
        if not cp_.is_file():
            cprob.append("cover.png is missing next to the episode (assemble writes it)")
        else:
            from PIL import Image
            if Image.open(cp_).size != (W, H):
                cprob.append(f"cover.png is {Image.open(cp_).size}, not {W}x{H}")
        rec("CALM-COVER", not cprob, "; ".join(cprob) or "cover.png 1080x1920 (DESIGN.md 2.6)")
        # R-501 (the owner 2026-10-28): the first frame is the grid poster, not black (it is the hook, and the Reels grid tile when no cover is sent)
        if cp_.is_file():
            f0ok, f0d = GP.frame0_check(ep.out, cp_)
            rec("COVER-FRAME0", f0ok, f0d)
        else:
            rec("COVER-FRAME0", False, "no cover.png to compare frame 0 with")
    # the small NJ mark (the owner 2026-10-25): in the delivered file, and clear of every plate, HUD plate, face and card text
    wf, wmet = WM.present_problems(ep.out, d, ep.work / "watermark.json")
    rec("WATERMARK-PRESENT", not wf, "; ".join(wf[:3]) or f"the NJ mark shows on {wmet['share_present']:.0%} of {wmet['decoded']} sampled frames (median correlation {wmet['ncc_median']}); top-right {WM.rect()}, opacity {WM.OPACITY}")
    wsc = json.loads((ep.work / "watermark.json").read_text(encoding="utf-8")) if (ep.work / "watermark.json").is_file() else {}
    all_faces = [{**b, "what": f"face {k}"} for k, v in fb.items() for b in v]
    ctexts, cmissing = card_text_boxes(ep, tl)
    wc = cmissing + WM.clear_problems(wsc.get("rect"), [{"x": c["x"], "y": c["y"], "w": c["w"], "h": c["h"], "what": f"«{c['text'][:14]}»"} for c in caps["captions"]],
                           [{"x": h["x"], "y": h["y"], "w": h["w"], "h": h["h"], "what": f"HUD {h['id']}"} for h in huds if h.get("w")], all_faces, ctexts)
    rec("WATERMARK-CLEAR", not wc, "; ".join(wc[:3]) or f"the mark's rect clears {len(caps['captions'])} caption plates, {len(huds)} HUD plates, {len(all_faces)} face boxes, the card text and the phone UI zones")
    if recap_expected(plan):
        rec("CALM-RECAP-FIRST", tl["items"][0]["id"] == "recap" and tl["items"][0]["dur"] <= 3.0 + 1e-6, "the recap card opens the episode")
    else:
        rec("CALM-RECAP-FIRST", tl["items"][0]["kind"] == "scene" and tl["items"][0]["t0"] == 0 and not any(i["id"] == "recap" for i in tl["items"]),
            f"{plan.get('episode')} has no vote to recap (recaps start at E{RECAP_FROM_EPISODE:02d}): the story opens at 0 s")
    import calm_intro      # C10: every character's first appearance is followed by an intro_freeze, entered by the dramatic cut and left by a declared cut
    imeas = {}
    for it in tl["items"]:
        if it.get("kind") == "intro":
            mp = ep.root / "work" / "shots" / it["shot"] / "out" / "intro-measure.json"
            imeas[it["id"]] = read_json(mp) if mp.is_file() else None
    ip = calm_intro.episode_problems(plan, tl, imeas)
    intro_items = [it for it in tl["items"] if it.get("kind") == "intro"]
    rec("CALM-INTRO", not ip, "; ".join(x.split(" ", 1)[1] for x in ip[:3]) or (f"{len(intro_items)} character(s) introduced at their first appearance ("
        + ", ".join(it["character"] + " after " + it["after"] for it in intro_items) + "); each frozen, isolated by a grey glow, named in graffiti"))
    rec("CALM-TWO-CHOICES", bool(plan["choice"].get("choice1")) and bool(plan["choice"].get("choice2")), "two choices on the choice card")
    try:      # C3 + C4 + C5: every transition a sound and a visual, every prop and hand action foley, the choice sequence pops with the narrator
        import calm_sfx
        sfx_p = ep.work / "sfx.json"
        bad = calm_sfx.check(read_json(sfx_p), plan, tl) if sfx_p.is_file() else ["CALM-TRANSITION-SFX sfx.json is missing: run `audio` first"]
        for cid in ("CALM-TRANSITION-SFX", "CALM-FOLEY", "CALM-CHOICE-SFX", "CALM-INTRO-SFX"):
            mine = [b.split(" ", 1)[1] for b in bad if b.startswith(cid + " ")]
            rec(cid, not mine, "; ".join(mine[:3]) or "ok")
    except ImportError:
        rec("CALM-TRANSITION-SFX", False, "calm_sfx.py not available")
    sl_ = read_json(ep.script_p)["lines"]
    if format_v2(plan):      # format v2 (the owner 2026-10-28), from E03 on
        spk = {l["id"]: l.get("speaker") for l in sl_}
        nshare = narrator_share([(spk.get(ln["line"]), wav_seconds(ep.take(ln["line"]))) for it, ln in _spoken(tl["items"]) if it.get("id") != "choice"])   # the vote card is the narrator's by role (the owner 2026-10-28): not counted
        rec("NARRATOR-SHARE", nshare <= NARRATOR_SHARE_MAX + 1e-9, f"the narrator is {nshare:.0%} of the placed voice time (at most {NARRATOR_SHARE_MAX:.0%}): recap, night links and the vote question only")
        dl = dialogue_problems(read_json(ep.script_p))
        rec("DIALOGUE-LINES", not dl, "; ".join(x.split(" ", 1)[1] for x in dl[:2]) or "10 to 15 character lines, at least one exchange")
        evp = event_problems(plan)
        rec("EVENTS", not evp, "; ".join(x.split(" ", 1)[1] for x in evp[:2]) or "2 to 5 shown events, every night has one")
    try:
        import qg_checks as qc
        pl = {"lines": [{"start": ln["voice_t0"], "dur": wav_seconds(ep.take(ln["line"]))} for it, ln in _spoken(tl["items"])],
              "intro_s": sum(float(it.get("dur") or 0.0) for it in tl["items"] if it.get("kind") == "intro")}      # intro_freeze time is not counted in voice coverage (qg_checks.check_calm_declared)
        sl = episode_shotlist(ep, tl, plan)
        end = {"choices": [plan["choice"]["choice1"], plan["choice"]["choice2"]]}
        declared = qc.check_calm_declared(pl, {"captions": [{**c, "line": c["line"]} for c in cp]}, end, sl, tl["total_s"])
        for x in declared:
            checks.append({"id": (re.search(r"\[([A-Z0-9-]+)\]", x) or [0, "CALM-DECLARED"])[1], "status": "fail", "detail": x})
            fails.append(x)
        if not any("[CALM-VOICE-COVERAGE]" in x for x in declared):      # all placed voice (narrator and characters) covers >= 0.85 of the runtime
            checks.append({"id": "CALM-VOICE-COVERAGE", "status": "pass", "detail": f"placed voice covers at least {qc.CALM['voice_share_min']:.0%} of the runtime, any speaker"})
        if not skip_render:
            r = subprocess.run(["uv", "run", str(TOOLS / "quality_gate.py"), "calm", str(ep.out), "--timeline", str(ep.timeline_p), "--json", str(ep.work / "calm-render.json"), "--quiet"], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", env=ENV, cwd=ep.root)
            ok = r.returncode == 0
            checks.append({"id": "CALM-RENDER", "status": "pass" if ok else "fail", "detail": (r.stdout or "")[-600:]})
            if not ok:
                fails += [l for l in (r.stdout or "").splitlines() if l.startswith("FAIL")] or ["CALM-RENDER failed"]
    except ImportError:
        checks.append({"id": "CALM-DECLARED", "status": "skip", "detail": "qg_checks calm functions not available"})
        skip_render = True
    rep = {"episode": ep.id, "profile": "calm", "verdict": "FAIL" if fails else "PASS", "complete": not skip_render, "checks": checks, "fails": fails,
           "warnings": [c["warning"] for c in checks if c.get("warning")]}
    write_json(ep.gate_p, rep)
    if fails:
        raise Fail(fails[0].split(" ", 1)[0].replace("FAIL", "").strip() or "CALM-GATE", "; ".join(fails[:4]))
    return {"verdict": "PASS", "checks": len(checks)}


STAGES = {"plan": stage_plan, "captions": stage_captions, "audio": stage_audio, "assemble": stage_assemble, "gate": stage_gate}


def record_stage(ep: Ep, name: str) -> None:
    """Leave a stage record in work/episodes/<ep>/STATE.json (the shot engine's format: stages.<name>.at). Root cause (E01C, 2026-10-25): a calm episode had no STATE.json, so
    `heal.py guard` could not tell a re-run of the gate (which rewrites gate/report.json) from a hand edit and refused every honest rebuild. The record proves the re-run; the guard is unchanged."""
    p = ep.work / "STATE.json"
    try:
        st = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    except ValueError:
        st = {}
    st.setdefault("episode", ep.id if hasattr(ep, "id") else str(ep.work.name))
    st.setdefault("stages", {})[name] = {"status": "ok", "kind": "calm", "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    p.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[0] not in list(STAGES) + ["all"]:
        print(__doc__)
        return 2
    try:
        ep = Ep(argv[1])
        order = list(STAGES) if argv[0] == "all" else [argv[0]]
        for name in order:
            res = STAGES[name](ep) if name != "gate" else stage_gate(ep, "--skip-render-gate" in argv)
            record_stage(ep, name)
            print(f"[{name}] ok {res}")
        return 0
    except Fail as e:
        print(e)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
