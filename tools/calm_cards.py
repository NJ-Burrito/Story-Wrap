"""Calm card templates (owner, 2026-10-24, CLAUDE.md "Calm format": a recurring wrapper). Five typographic cards, all live text in Thmanyah:

  title_card    series title + a line under it                                  title [line] [accent]
  day_card      the HUD card: day counter, clock, place                         series day [clock] [place]
  recap_card    the last vote as the hook: a small line over the winning word  line word [backdrop=<image>]
  choice_card   the two-choice question                                         question choice1 choice2 [prompt]
  follow_card   the follow card                                                 line [handle]
  choice_split  (C4, 2026-10-25) the question and the two choices in the BOTTOM half; the top half stays empty here: calm_compose cuts two close-ups
                into it in time with the narrator, and lights the question and each choice as it is read (lit plates, `lit_plates`)  question choice1 choice2
  object_card   (C3, 2026-10-25) a written object (a brass plate): the card draws the plate, the narrator's caption plates are ENGRAVED on it word by word  heading [object]
  cover_card    (DESIGN.md 2.6, 2026-10-25) the series-grid cover «بطاقة اليوم»: a big episode numeral, the series name small beneath, the day's lost object behind as a flat
                silhouette, key content inside the profile grid's central square. Renders a still PNG (`render_cover`, cover.png 1080x1920, no mark, no border)  series day [object] [backdrop]

Each is a shot folder that tools/shot.py runs like any other (shot.json "kind": "card", "format": "calm"; the stages keep their names):
  init/catalogue/camera/spec  nothing to look up: the card is text; spec checks the text rules (no tashkeel, one idea, safe area)
  build   writes the card page (HTML) and checks the fonts load (Thmanyah, never a fallback)
  trace   renders the card PNG once (Playwright, GPU raster) and measures every text box
  record  encodes the clip with ffmpeg (a 4 % push over the first half, then a held frame, and a fade; NVENC), exactly fps x duration frames
  gate    CARD-TASHKEEL, CARD-FONT, CARD-SAFE, CARD-CONTRAST, CARD-ONE-IDEA, CARD-FORMAT (calm profile: no motion threshold applies to a card)
  review  a contact sheet of three frames
Text is written WITHOUT tashkeel (CLAUDE.md). Colours: one accent per card, dark ground, high contrast (WCAG AA 4.5).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("STORYWRAP_ROOT") or TOOLS.parent)
sys.path.insert(0, str(TOOLS))
from arabic_display import has_tashkeel, tashkeel_chars   # noqa: E402
from shotlib.engine import Stage, StageFail   # noqa: E402
import watermark as WM   # noqa: E402  (the mark's rectangle: a card's text must clear it, WATERMARK-CLEAR)

FPS, W, H = 24, 1080, 1920
SAFE = {"x0": 54, "y0": 270, "x1": 1026, "y1": 1250}      # Reels UI: top 14 %, bottom 35 %, side 5 % (compose.py SAFE)
FONTS = ROOT / "assets" / "fonts"
DEFAULT_S = {"title_card": 2.5, "day_card": 2.0, "recap_card": 2.5, "choice_card": 5.0, "follow_card": 3.0, "choice_split": 9.0, "object_card": 3.5, "cover_card": 2.5}
ACCENT = {"title_card": "#f2c14e", "day_card": "#ff4d4d", "recap_card": "#ff4d4d", "choice_card": "#f2c14e", "follow_card": "#8ddc6b", "choice_split": "#f2c14e", "object_card": "#e8b94a", "cover_card": "#ff4d4d"}
INK, GROUND = "#f3ede4", "#13110e"
PAPER = "#f3ede4"       # the cover is black ink on paper (DESIGN.md 2.6), the one card on a light ground
PUSH_PCT = 4.0
CARD_FIELDS = {
    "title_card": (["title"], ["line", "accent"]),
    "day_card": (["series", "day"], ["clock", "place"]),
    "recap_card": (["line", "word"], ["backdrop", "tag", "backdrop_video"]),     # tag (DESIGN.md 2.3): «الحلقة N · the series» as a small line; the word limit of line and word is unchanged
    "choice_card": (["question", "choice1", "choice2"], ["prompt"]),
    "follow_card": (["line"], ["handle"]),
    "choice_split": (["question", "choice1", "choice2"], ["prompt"]),
    "object_card": (["heading"], ["object"]),
    "cover_card": (["series", "day"], ["object", "backdrop"]),
}
AR_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
CHOICE_WORDS_MAX = 4        # C13: a choice phrase is short enough to type in a comment
COMMENT_PROMPT_LEGACY = "اكتبوا اختياركم بكلماتكم، وما رأيكم، وماذا تريدون بعدها"     # E01 and E01C v5: a rebuild keeps the approved card text (Lead, 2026-10-25)
COMMENT_PROMPT = "ما رأيكم، ولماذا؟"     # DESIGN.md 5.2, from E02 only (calm_compose.choice_card_prompt): an open question and a reason, nothing to type
FOLLOW_LINE = "الحلقة القادمة تتبع ما تكتبونه"     # DESIGN.md 2.4 item 12: a statement of fact, not «تابعوا لتعرفوا» (a follow-for-part-2 plea, the bait text of IG 6.10 / FB 1.4)
# Words an E02+ prompt, closing line or follow line never carries (DESIGN.md 5.2, "Words banned"): none asks a viewer to type, vote, pick, share or follow.
BANNED_ASK = ("اكتبوا اختياركم", "اكتب اختيارك", "علقوا", "صوتوا", "اختاروا", "شاركوا", "اذكروا", "اضغطوا", "تابعوا لتعرفوا", "تابع لتعرف", "تابعوا")
QUESTION_WORDS = ("أين", "اين", "ماذا", "لماذا", "كيف", "هل", "متى", "كم", "من", "ما", "أي", "اي")     # a statement needs «؟» or one of these as its FIRST word (ask_problems)
MARK_CLEAR_INLINE_PX = 130      # right-hand margin (RTL inline start) of a card's first block: the text's right edge ends left of the mark's column (1026 - 130 = 896 < 926 - PAD)
COVER_SQUARE = (0, 420, 1080, 1500)    # the profile grid crops a 1080x1920 cover to its central square: numeral and series name stay inside it (DESIGN.md 2.6, OPINION-grade serial-grid advice)


def ask_problems(text: str, what: str, need_question: bool) -> list[str]:
    """PLAN-PROMPT / CALM-FOLLOW-LINE text rules (DESIGN.md 5.2): no digit, none of BANNED_ASK, and (a prompt or a closing line) a question mark or a question word."""
    f = []
    t = str(text)
    if re.search(r"[0-9٠-٩۰-۹]", t):
        f.append(f"{what} carries a digit: viewers are never asked to type a number")
    hit = [b for b in BANNED_ASK if b in t]
    if hit:
        f.append(f"{what} uses the banned ask «{hit[0]}» (DESIGN.md 5.2: no request to type, vote, choose, share or follow)")
    words = re.sub(r"[،؟?.!:؛]", " ", t).split()
    if need_question and not ("؟" in t or "?" in t or (words and words[0].lstrip("وف") in QUESTION_WORDS)):
        f.append(f"{what} is not a question (it needs a question mark or a question word)")
    return f


class CardError(Exception):
    def __init__(self, code, msg):
        super().__init__(f"FAIL [{code}] {msg}")
        self.code, self.msg = code, msg


def _err(code, msg):
    from calm import CalmError
    return CalmError(code, msg)


def esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def resolve(template: str, p: dict) -> dict:
    """Template + parameters -> the calm description of a card (validated; the text rules are enforced here, not at the end)."""
    req, opt = CARD_FIELDS[template]
    miss = [k for k in req if not str(p.get(k, "")).strip()]
    if miss:
        raise _err("CALM-PARAM", f"{template} needs {', '.join(miss)}")
    unknown = [k for k in p if k not in req + opt + ["id", "duration", "set", "template", "seed"]]
    if unknown:
        raise _err("CALM-PARAM", f"{template} does not take {', '.join(unknown)} (takes {', '.join(req + opt)})")
    text = {k: str(p[k]).strip() for k in req + opt if str(p.get(k, "")).strip() and k not in ("backdrop", "object", "backdrop_video")}
    for k, v in text.items():
        if has_tashkeel(v):
            raise _err("CALM-TASHKEEL", f"{k} carries tashkeel ({', '.join(tashkeel_chars(v))}): nothing people see carries tashkeel (CLAUDE.md); write the visible text without it")
    if template == "day_card":
        text["day_label"] = "اليوم " + str(text["day"]).translate(AR_DIGITS)
        if text.get("clock"):
            text["clock"] = text["clock"].translate(AR_DIGITS)
    if template == "cover_card":
        text["numeral"] = str(text["day"]).translate(AR_DIGITS)
    if template in ("choice_card", "choice_split"):
        # C13 (owner, 2026-10-25): never "comment 1 or 2". The pills show the SHORT PHRASE a viewer can type, in quotes; the prompt asks for the choice in their own words,
        # what they think, and what they want to see next.
        for k in ("choice1", "choice2"):
            if len(text[k].split()) > CHOICE_WORDS_MAX:
                raise _err("CALM-CHOICE", f"{k} is {len(text[k].split())} words: a choice is a short phrase a viewer can type (at most {CHOICE_WORDS_MAX} words)")
            if re.search(r"[0-9٠-٩۰-۹]", text[k]):
                raise _err("CALM-CHOICE", f"{k} carries a digit: viewers write the choice in words, never 1 or 2 (CLAUDE.md \"Comments we ask for\")")
        text.setdefault("prompt", COMMENT_PROMPT_LEGACY)      # the episode-aware default is calm_compose.choice_card_prompt(plan), which daily.py passes
    dur = round(float(p.get("duration", DEFAULT_S[template])) * FPS) / FPS
    dmax = 16.0 if template == "choice_split" else 9.0     # the choice sequence runs as long as the narrator takes to read the question, both choices and the hook
    if not 1.5 <= dur <= dmax:
        raise _err("CALM-DURATION", f"{dur} s outside 1.5..{dmax:g} s")
    backdrop = backdrop_sha = None
    if p.get("backdrop"):
        bp = Path(p["backdrop"]).resolve()
        if not bp.is_file():
            raise _err("CALM-PARAM", f"backdrop {bp} not found")
        backdrop = str(bp)
        backdrop_sha = hashlib.sha256(bp.read_bytes()).hexdigest()[:16]      # the picture's content is part of the card's description: a re-cut story frame rebuilds the card (daily.py compares descriptions)
    bvid = bvid_sha = None      # E04 round 3 (critic Q01): a MOVING story picture under the recap type: the first seconds of a shot's video, dimmed like the still (opacity .38), the card's type over it
    if p.get("backdrop_video"):
        vp = Path(p["backdrop_video"]).resolve()
        if not vp.is_file():
            raise _err("CALM-PARAM", f"backdrop_video {vp} not found")
        bvid = str(vp)
        bvid_sha = hashlib.sha256(vp.read_bytes()).hexdigest()[:16]
    cover_obj = None
    if template == "cover_card" and p.get("object"):
        op = Path(p["object"]).resolve()
        if not op.is_file():
            raise _err("CALM-PARAM", f"object image {op} not found")
        cover_obj = str(op)
    sid = re.sub(r"[^a-z0-9]+", "-", str(p.get("id") or f"calm-{template}").lower()).strip("-")
    return {"schema": "calm-shot/1", "format": "calm", "kind": "card", "template": template, "id": sid, "fps": FPS, "duration_s": dur, "canvas": [W, H],
            "card": {"template": template, "text": text, "accent": ACCENT[template], "backdrop": backdrop, **({"backdrop_sha256": backdrop_sha} if backdrop_sha else {}), **({"backdrop_video": bvid, "backdrop_video_sha256": bvid_sha} if bvid else {}), "object": str(p.get("object") or "plate") if template == "object_card" else cover_obj,
                     "push_pct": 0.0 if template == "choice_split" else PUSH_PCT},
            "set": None, "actors": [], "camera": {"move": "push", "move_pct": 0.0 if template == "choice_split" else PUSH_PCT}}


# ------------------------------------------------------------------ HTML
def font_css() -> str:
    out = []
    for fam, wt, f in (("thmanyahsans", 500, "Medium"), ("thmanyahsans", 700, "Bold"), ("thmanyahsans", 900, "Black"), ("thmanyahserifdisplay", 700, "Bold"), ("thmanyahserifdisplay", 900, "Black")):
        out.append(f'@font-face{{font-family:"{fam}";src:url("{(FONTS / f"{fam}-{f}.woff2").as_uri()}") format("woff2");font-weight:{wt}}}')
    return "".join(out)


def card_html(card: dict) -> str:
    t, tx, ac = card["template"], card["text"], card["accent"]
    bd = ""
    if card.get("backdrop_png"):
        bd = f'<div class="bd" style="background-image:url(\'{Path(card["backdrop_png"]).as_uri()}\')"></div>'
    css = (f"{font_css()}html,body{{margin:0;width:{W}px;height:{H}px;background:{GROUND};overflow:hidden}}"
           f"body{{position:relative;font-family:'thmanyahsans';color:{INK};direction:rtl;text-align:center}}"
           f".bd{{position:absolute;inset:0;background-size:cover;background-position:center;opacity:.38;filter:saturate(.7)}}"
           f".vig{{position:absolute;inset:0;background:radial-gradient(ellipse at 50% 46%,rgba(0,0,0,0) 38%,rgba(0,0,0,.72) 100%)}}"
           f".box{{position:absolute;left:{SAFE['x0']}px;right:{W - SAFE['x1']}px;top:{SAFE['y0']}px;height:{SAFE['y1'] - SAFE['y0']}px;display:flex;flex-direction:column;justify-content:center;align-items:center;gap:36px}}"
           f".big{{font-family:'thmanyahserifdisplay';font-weight:900;font-size:176px;line-height:1.25;color:{INK}}}"
           f".acc{{color:{ac}}}.mid{{font-weight:700;font-size:78px;line-height:1.4}}.small{{font-weight:500;font-size:56px;line-height:1.5;opacity:.9}}"
           f".pill{{font-weight:900;font-size:70px;line-height:1.3;padding:30px 60px;border-radius:999px;border:6px solid {ac};background:rgba(0,0,0,.45);width:760px;box-sizing:border-box}}"
           f".tag{{display:inline-block;color:{ac};margin-inline-start:22px}}.tagred{{display:inline-block;font-weight:900;font-size:64px;color:#fff;background:{ac};padding:8px 34px;border-radius:14px}}")
    if t in ("choice_card", "recap_card"):    # the mark sits top-right (WM.rect, 926,282): the first block starts at y 330-340, so it leaves the mark's column free (WATERMARK-CLEAR looks at card text; E02, 2026-10-27)
        css += f".box>:first-child{{margin-inline-start:{MARK_CLEAR_INLINE_PX}px}}"
    if t == "choice_card":   # the caption plates sit in the lower third (calm_compose CAP_Y 1010): the question, the two pills and the comment prompt stay above them, one line per pill
        css += ".box{justify-content:flex-start;padding-top:60px;gap:30px}.pill{font-size:60px;padding:22px 44px;width:900px}.tag{margin-inline-start:0;margin-inline-end:24px}"
    if t == "choice_split":   # C4: the BOTTOM half holds the question and both choices (y 975..1250, inside the Reels safe area); the top half is for the two close-ups
        css += (f".box{{top:964px;height:286px;justify-content:flex-start;gap:8px}}.q{{font-weight:900;font-size:58px;line-height:1.25}}"
                f".pill{{font-size:54px;line-height:1.3;padding:8px 40px;border-width:5px;width:900px}}.tag{{margin-inline-start:0;margin-inline-end:24px}}"
                f".top{{position:absolute;left:0;top:0;width:{W}px;height:960px;background:linear-gradient(#0c0a08,{GROUND})}}"
                f".bar{{position:absolute;left:0;top:948px;width:{W}px;height:6px;background:{ac};box-shadow:0 0 24px {ac}}}"
                f".lit.pill{{background:{ac};color:{GROUND};border-color:{ac}}}.lit.q{{color:{ac}}}.lit .tag{{color:{GROUND}}}")
    if t == "recap_card":    # DESIGN.md 2.1: the recap is spoken and its caption plate sits in the lower third (calm_compose CAP_Y): the card's text stays in the upper part, above the plate
        css += ".box{justify-content:flex-start;padding-top:70px;box-sizing:border-box;gap:28px}"
    if t == "object_card":    # C3: a brass plate, engraved: the narrator's words appear on it (calm_compose, caption style "object")
        css += (f".box{{top:560px;height:640px;left:90px;right:90px;justify-content:flex-start;padding-top:36px;box-sizing:border-box;border:10px double {ac};border-radius:26px;"
                f"background:linear-gradient(160deg,#3a2c1b,#241a10 60%,#1a130b);box-shadow:inset 0 0 60px rgba(0,0,0,.7),0 0 70px rgba(232,185,74,.22)}}"
                f".plate-h{{font-family:'thmanyahserifdisplay';font-weight:900;font-size:60px;line-height:1.3;color:{ac};letter-spacing:.02em;width:70%;border-bottom:4px solid {ac};padding-bottom:10px}}"
                f".rivet{{position:absolute;z-index:2;width:26px;height:26px;border-radius:50%;background:radial-gradient(circle at 35% 30%,#f7dc8a,#8a6a1f 70%);box-shadow:0 3px 6px rgba(0,0,0,.6)}}")
    if t == "cover_card":    # DESIGN.md 2.6: black ink on paper, a big numeral, the series name small beneath, the object as a flat silhouette behind; no border, no mark
        css += (f"html,body{{background:{PAPER}}}body{{color:{GROUND}}}.vig{{display:none}}.box{{top:{COVER_SQUARE[1]}px;height:{COVER_SQUARE[3] - COVER_SQUARE[1]}px;left:{SAFE['x0']}px;right:{W - SAFE['x1']}px;gap:10px}}"
                f".numeral{{font-family:'thmanyahserifdisplay';font-weight:900;font-size:520px;line-height:1.05;color:{GROUND}}}.series{{font-weight:900;font-size:84px;line-height:1.3;color:{GROUND}}}"
                f".sil{{position:absolute;left:0;top:{COVER_SQUARE[1]}px;width:{W}px;height:{COVER_SQUARE[3] - COVER_SQUARE[1]}px;background-size:contain;background-repeat:no-repeat;background-position:center;opacity:.13}}")
    if t == "cover_card":
        sil = ('<div class="sil" style="background-image:url(&quot;' + Path(card["object_png"]).as_uri() + '&quot;)"></div>') if card.get("object_png") else ""
        body = f'<div class="numeral">{esc(tx["numeral"])}</div><div class="series">{esc(tx["series"])}</div>'
        bd = bd or sil
    elif t == "title_card":
        body = f'<div class="big">{esc(tx["title"])}</div>' + (f'<div class="mid acc">{esc(tx["line"])}</div>' if tx.get("line") else "")
    elif t == "day_card":
        body = (f'<div class="small">{esc(tx["series"])}</div><div class="big acc">{esc(tx["day_label"])}</div>'
                + (f'<div class="mid">{esc(tx["clock"])}</div>' if tx.get("clock") else "") + (f'<div class="small">{esc(tx["place"])}</div>' if tx.get("place") else ""))
    elif t == "recap_card":
        body = (f'<div class="small">{esc(tx["tag"])}</div>' if tx.get("tag") else "") + f'<div class="mid">{esc(tx["line"])}</div><div class="big acc">{esc(tx["word"])}</div>'
    elif t == "object_card":
        body = f'<div class="plate-h">{esc(tx["heading"])}</div>'
    elif t == "choice_split":
        body = (f'<div class="q">{esc(tx["question"])}</div>'
                f'<div class="pill">«{esc(tx["choice1"])}»</div><div class="pill">«{esc(tx["choice2"])}»</div>')
    elif t == "choice_card":
        body = (f'<div class="mid">{esc(tx["question"])}</div>'
                f'<div class="pill">«{esc(tx["choice1"])}»</div><div class="pill">«{esc(tx["choice2"])}»</div>'
                f'<div class="small">{esc(tx["prompt"])}</div>')
    else:
        body = f'<div class="big acc">{esc(tx["line"])}</div>' + (f'<div class="mid" dir="ltr">{esc(tx["handle"])}</div>' if tx.get("handle") else "")
    extra = ""
    if t == "choice_split":
        extra = '<div class="top"></div><div class="bar"></div>'
    if t == "object_card":
        extra = "".join(f'<div class="rivet" style="left:{x}px;top:{y}px"></div>' for x, y in ((112, 582), (942, 582), (112, 1152), (942, 1152)))
    return f'<!doctype html><html lang="ar" dir="rtl"><meta charset="utf-8"><style>{css}</style><body>{bd}<div class="vig"></div>{extra}<div class="box" id="box">{body}</div></body></html>'


# ------------------------------------------------------------------ render helpers (browser and ffmpeg)
def ff(args, check=True):
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", *map(str, args)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise StageFail("CARD-ENCODE", (r.stderr or "")[-300:])
    return r


def backdrop_png(card: dict, work: Path) -> str | None:
    bd = card.get("backdrop")
    if not bd:
        return None
    out = work / "backdrop.png"
    ff(["-i", bd, "-frames:v", "1", "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}", out])
    return str(out)


def object_png(card: dict, work: Path) -> str | None:
    """cover_card: the lost object as a flat black silhouette on a transparent ground (alpha of the image when it has one, otherwise everything unlike the corner colour)."""
    src = card.get("object")
    if not src or card.get("template") != "cover_card":
        return None
    import numpy as np
    from PIL import Image
    im = Image.open(src).convert("RGBA")
    a = np.asarray(im)
    if a[..., 3].min() < 250:
        mask = a[..., 3] > 40
    else:
        bg = a[0, 0, :3].astype(float)
        mask = np.abs(a[..., :3].astype(float) - bg).sum(axis=2) > 60
    out = np.zeros(a.shape, dtype=np.uint8)
    out[..., :3] = (19, 17, 14)
    out[..., 3] = mask * 255
    p = work / "object-silhouette.png"
    Image.fromarray(out, "RGBA").save(p)
    return str(p.resolve())


def need_fonts():
    miss = [f for f in ("thmanyahsans-Bold.woff2", "thmanyahsans-Medium.woff2", "thmanyahsans-Black.woff2", "thmanyahserifdisplay-Black.woff2") if not (FONTS / f).is_file()]
    if miss:
        raise StageFail("CARD-FONT", f"Thmanyah font file(s) missing in assets/fonts/: {', '.join(miss)} (git-ignored; Cairo or any fallback is banned)")


def render_png(sd: Path, card: dict) -> dict:
    """Render the card page once and measure every text box. Returns {boxes: [...], fonts_ok: bool, png: path}."""
    from playwright.sync_api import sync_playwright
    need_fonts()
    work = sd / "build"
    work.mkdir(parents=True, exist_ok=True)
    card = {**card, "backdrop_png": backdrop_png(card, work), "object_png": object_png(card, work)}
    page = work / "card.html"
    page.write_text(card_html(card), encoding="utf-8")
    png = sd / "out" / "card.png"
    png.parent.mkdir(parents=True, exist_ok=True)
    res = {"png": str(png)}
    with sync_playwright() as pw:
        b = pw.chromium.launch(args=["--enable-gpu-rasterization", "--ignore-gpu-blocklist", "--allow-file-access-from-files"])
        try:
            pg = b.new_page(viewport={"width": W, "height": H})
            pg.goto(page.as_uri())
            specs = ("500 40px thmanyahsans", "700 40px thmanyahsans", "900 40px thmanyahsans", "900 40px thmanyahserifdisplay")
            pg.evaluate("Promise.all(%s.map(s => document.fonts.load(s, 'هدى'))).then(() => 1)" % json.dumps(list(specs)))
            res["fonts_ok"] = all(pg.evaluate(f"document.fonts.check('{s}')") for s in specs)
            res["boxes"] = pg.evaluate("""() => [...document.querySelectorAll('#box > *')].map(e => {
                const r = e.getBoundingClientRect(), cs = getComputedStyle(e);
                return {text: e.textContent, x0: r.left, y0: r.top, x1: r.right, y1: r.bottom, font_px: parseFloat(cs.fontSize), family: cs.fontFamily, color: cs.color};
            })""")
            pg.screenshot(path=str(png))
        finally:
            b.close()
    return res


def render_cover(p: dict, out_png: Path) -> dict:
    """DESIGN.md 2.6: render the cover still (a PNG only, 1080x1920) from {series, day, [object]} and check it (CARD-*, COVER-SQUARE). Raises StageFail on a failed check.
    Returns {png, boxes, fonts_ok}. The episode's assemble calls this for work/episodes/<ep>/cover.png; no watermark is laid on a cover (it is a still, not an episode frame)."""
    c = resolve("cover_card", {**p, "id": "cover"})
    out_png = Path(out_png).resolve()
    sd = out_png.parent / "cover-build"
    meas = render_png(sd, c["card"])
    fails = check_card(c["card"], meas)
    if fails:
        raise StageFail(fails[0].split(" ", 1)[0], "; ".join(fails[:3]))
    import shutil
    shutil.copyfile(sd / "out" / "card.png", out_png)
    return {"png": str(out_png), "boxes": len(meas["boxes"]), "fonts_ok": meas["fonts_ok"]}


def push_frames(dur: float) -> int:
    """The push lasts about half the card (at most 2.2 s); the rest is a held frame (a deliberate hold: calm holds are 5 to 25 % of an episode, longest 3 s: qg_checks.CALM)."""
    return max(6, round(min(2.2, dur * 0.5) * FPS))


def encode(sd: Path, card: dict, dur: float) -> Path:
    """The card as a clip: a 4 % push-in over the first half, then a held frame, a short fade in and out, 24 fps, exactly dur x 24 frames (h264_nvenc, yuv420p)."""
    n = round(dur * FPS)
    png = sd / "out" / "card.png"
    out = sd / "out" / f"{sd.name}.mp4"
    if card.get("backdrop_video") and Path(card["backdrop_video"]).is_file():
        return encode_moving(sd, card, dur, out)
    pf = push_frames(dur)
    z = card["push_pct"] / 100.0 / pf
    vf = (f"scale={W * 2}:{H * 2}:flags=bicubic,zoompan=z='1+{z:.8f}*min(on,{pf})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={n}:s={W}x{H}:fps={FPS},"
          + ("" if card["template"] == "choice_split" else f"fade=t=in:st=0:d=0.25,fade=t=out:st={max(0.0, dur - 0.35):.3f}:d=0.35,")   # the split sequence is a composite: its joins do the fading
          + "format=yuv420p")
    ff(["-loop", "1", "-i", png, "-vf", vf, "-frames:v", n, "-r", FPS, "-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "19", "-b:v", "0", "-pix_fmt", "yuv420p", "-threads", "2", out])
    return out


def encode_moving(sd: Path, card: dict, dur: float, out: Path) -> Path:
    """E04 round 3 (critic Q01): the recap card over a MOVING picture. The page is shot again with a transparent ground (type and vignette only), the story shot's video runs under it from
    1.0 s, dimmed to the still's 38 % and desaturated, then the same fade in and out as the still card. 24 fps, exactly dur x 24 frames."""
    from playwright.sync_api import sync_playwright
    need_fonts()
    n = round(dur * FPS)
    work = sd / "build"
    work.mkdir(parents=True, exist_ok=True)
    page, ov = work / "overlay.html", work / "overlay.png"
    page.write_text(card_html({**card, "backdrop_png": None}).replace("</style>", "html,body{background:transparent!important}</style>"), encoding="utf-8")
    with sync_playwright() as pw:
        b = pw.chromium.launch(args=["--enable-gpu-rasterization", "--ignore-gpu-blocklist", "--allow-file-access-from-files"])
        try:
            pg = b.new_page(viewport={"width": W, "height": H})
            pg.goto(page.as_uri())
            pg.evaluate("Promise.all(['500 40px thmanyahsans','700 40px thmanyahsans','900 40px thmanyahsans','900 40px thmanyahserifdisplay'].map(s => document.fonts.load(s, 'هدى'))).then(() => 1)")
            pg.screenshot(path=str(ov), omit_background=True)
        finally:
            b.close()
    fc = (f"[0:v]scale={W}:{H}:flags=bicubic,format=rgb24,colorchannelmixer=rr=.38:gg=.38:bb=.38,eq=saturation=.75,setsar=1[bg];[bg][1:v]overlay=0:0:format=auto,"
          f"fade=t=in:st=0:d=0.25,fade=t=out:st={max(0.0, dur - 0.35):.3f}:d=0.35,format=yuv420p[o]")
    ff(["-ss", "1.0", "-i", card["backdrop_video"], "-loop", "1", "-i", ov, "-filter_complex", fc, "-map", "[o]", "-frames:v", n, "-r", FPS, "-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "19",
        "-b:v", "0", "-pix_fmt", "yuv420p", "-threads", "2", out])
    return out


# ------------------------------------------------------------------ gates
def lum(rgb):
    def ch(v):
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(rgb[0]) + 0.7152 * ch(rgb[1]) + 0.0722 * ch(rgb[2])


def contrast(a, b):
    la, lb = lum(a), lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def parse_rgb(css: str):
    m = re.findall(r"[\d.]+", css)
    return tuple(float(x) for x in m[:3])


def mark_problems(boxes: list[dict]) -> list[str]:
    """CARD-MARK: no measured text box of a card touches the NJ mark's rectangle (WM.rect() grown by WM.PAD_PX) that every delivered frame carries. The episode-level WATERMARK-CLEAR
    found this only after the assemble; the card checks it in the second it is drawn. A box is {x0, y0, x1, y1, text}."""
    r = WM.rect()
    pad = WM.PAD_PX
    f = []
    for b in boxes:
        if not (b["x1"] <= r["x"] - pad or b["x0"] >= r["x"] + r["w"] + pad or b["y1"] <= r["y"] - pad or b["y0"] >= r["y"] + r["h"] + pad):
            f.append(f"CARD-MARK text '{str(b.get('text', ''))[:20]}' box ({b['x0']:.0f},{b['y0']:.0f},{b['x1']:.0f},{b['y1']:.0f}) overlaps the NJ mark {r['x']},{r['y']},{r['w']},{r['h']} (+{pad} px)")
    return f


def check_card(card: dict, meas: dict) -> list[str]:
    """CARD-* checks on the rendered measurements. Returns 'ID message' strings (empty = pass)."""
    f = []
    for k, v in card["text"].items():
        if has_tashkeel(v):
            f.append(f"CARD-TASHKEEL {k} carries tashkeel")
    if not meas.get("fonts_ok"):
        f.append("CARD-FONT a Thmanyah face did not load: refusing to render with a fallback")
    for b in meas.get("boxes", []):
        if not all(x in b["family"].lower() for x in ("thmanyah",)):
            f.append(f"CARD-FONT text '{b['text'][:20]}' is set in {b['family']}, not Thmanyah")
        if card["template"] != "cover_card" and (b["x0"] < SAFE["x0"] - 1 or b["x1"] > SAFE["x1"] + 1 or b["y0"] < SAFE["y0"] - 1 or b["y1"] > SAFE["y1"] + 1):   # a cover is a grid still, not a Reel frame: COVER-SQUARE below replaces the Reels safe area
            f.append(f"CARD-SAFE text '{b['text'][:20]}' box ({b['x0']:.0f},{b['y0']:.0f},{b['x1']:.0f},{b['y1']:.0f}) leaves the Reels safe area {SAFE}")
        if b["font_px"] < 54:
            f.append(f"CARD-SAFE text '{b['text'][:20]}' is {b['font_px']:.0f} px: cards carry big text (at least 54 px at 1080)")
    if card["template"] != "cover_card":      # the cover is a profile-grid still: no mark (calm_compose assemble)
        f += mark_problems(meas.get("boxes", []))
    n_text = len(meas.get("boxes", []))
    limit = {"title_card": 2, "day_card": 4, "recap_card": 2, "choice_card": 4, "follow_card": 2, "choice_split": 3, "object_card": 2, "cover_card": 2}[card["template"]]
    if card["template"] == "recap_card" and card["text"].get("tag"):
        limit += 1      # the series strip's twin (DESIGN.md 2.3) is a label, not a second idea: only a card that carries a tag gets the extra block
    if n_text > limit:
        f.append(f"CARD-ONE-IDEA {n_text} text blocks on a {card['template']} (at most {limit}): one idea per card")
    if card["template"] == "cover_card":      # DESIGN.md 2.6: the numeral and the series name sit in the grid's central square
        sq = COVER_SQUARE
        for b in meas.get("boxes", []):
            if b["x0"] < sq[0] or b["x1"] > sq[2] or b["y0"] < sq[1] or b["y1"] > sq[3]:
                f.append(f"COVER-SQUARE text '{b['text'][:20]}' box ({b['x0']:.0f},{b['y0']:.0f},{b['x1']:.0f},{b['y1']:.0f}) leaves the central square {sq} the profile grid keeps")
    ground = (243, 237, 228) if card["template"] == "cover_card" else (19, 17, 14)
    for b in meas.get("boxes", []):
        c = contrast(parse_rgb(b["color"]), ground)
        if c < 4.5:
            f.append(f"CARD-CONTRAST text '{b['text'][:20]}' contrast {c:.1f} < 4.5 against the card ground")
    return f


def probe(p: Path) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=codec_name,width,height,r_frame_rate,nb_read_frames,pix_fmt",
                        "-of", "json", str(p)], capture_output=True, text=True)
    return json.loads(r.stdout)["streams"][0]


# ------------------------------------------------------------------ the shot folder and its stages
def write_shot(c: dict, sd: Path) -> list[Path]:
    sd = Path(sd)
    sd.mkdir(parents=True, exist_ok=True)
    c = {**c, "id": sd.name}
    shot = {"id": sd.name, "title": f"{sd.name}: calm {c['template'].replace('_', ' ')}", "kind": "card", "format": "calm", "fps": FPS, "duration_s": c["duration_s"], "canvas": [W, H],
            "card": c["card"], "scene_files": [], "library": []}
    (sd / "calm.json").write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
    (sd / "shot.json").write_text(json.dumps(shot, ensure_ascii=False, indent=1), encoding="utf-8")
    return [sd / "calm.json", sd / "shot.json"]


def _shot(sd: Path) -> dict:
    return json.loads((sd / "shot.json").read_text(encoding="utf-8"))


def s_ok(sd: Path):
    return {"card": True}


def s_spec(sd: Path):
    sh = _shot(sd)
    bad = [k for k, v in sh["card"]["text"].items() if has_tashkeel(v)]
    if bad:
        raise StageFail("CARD-TASHKEEL", f"{', '.join(bad)} carry tashkeel")
    (sd / "shot-spec.json").write_text(json.dumps({"format": "calm", "kind": "card", "template": sh["card"]["template"], "text": sh["card"]["text"], "duration_s": sh["duration_s"]}, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"text_fields": len(sh["card"]["text"])}


def s_build(sd: Path):
    sh = _shot(sd)
    need_fonts()
    work = sd / "build"
    work.mkdir(exist_ok=True)
    card = {**sh["card"], "backdrop_png": None}
    (work / "page.html").write_text(card_html(card), encoding="utf-8")
    (work / "diag.json").write_text(json.dumps({"frames": round(sh["fps"] * sh["duration_s"]), "kind": "card"}), encoding="utf-8")
    return {"html_bytes": len(card_html(card))}


def s_trace(sd: Path):
    sh = _shot(sd)
    meas = render_png(sd, sh["card"])
    (sd / "out" / "card-measure.json").write_text(json.dumps(meas, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"boxes": len(meas["boxes"]), "fonts_ok": meas["fonts_ok"]}


def s_record(sd: Path):
    sh = _shot(sd)
    n = round(sh["fps"] * sh["duration_s"])
    out = encode(sd, sh["card"], sh["duration_s"])
    v = probe(out)
    bad = [k for k, ok in (("codec h264", v["codec_name"] == "h264"), (f"size {W}x{H}", (v["width"], v["height"]) == (W, H)), ("24 fps", v["r_frame_rate"] == "24/1"),
                           (f"{n} frames", int(v["nb_read_frames"]) == n), ("yuv420p", v["pix_fmt"] == "yuv420p")) if not ok]
    if bad:
        raise StageFail("RECORD-FORMAT", f"card video {v} fails: {bad}")
    (sd / "out" / f"{sd.name}.encode.json").write_text(json.dumps({"frames": n, "ffmpeg_exit": 0}), encoding="utf-8")
    return {"frames": n}


def s_gate(sd: Path):
    sh = _shot(sd)
    meas = json.loads((sd / "out" / "card-measure.json").read_text(encoding="utf-8"))
    fails = check_card(sh["card"], meas)
    (sd / "gate").mkdir(exist_ok=True)
    rep = {"shot": sd.name, "format": "calm", "kind": "card", "gates": {"card": {"verdict": "FAIL" if fails else "PASS", "fail_ids": sorted({x.split(" ", 1)[0] for x in fails})}},
           "fails": [f"card:{x.split(' ', 1)[0]}" for x in fails], "details": fails, "verdict": "FAIL" if fails else "PASS"}
    (sd / "gate" / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    (sd / "gate" / "report.txt").write_text(f"gate report for {sd.name}: {rep['verdict']}\n" + "\n".join(fails) + "\n", encoding="utf-8")
    if fails:
        raise StageFail(fails[0].split(" ", 1)[0], "; ".join(fails[:4]))
    return {"card": "PASS"}


def s_review(sd: Path):
    vid = sd / "out" / f"{sd.name}.mp4"
    dur = _shot(sd)["duration_s"]
    (sd / "review").mkdir(exist_ok=True)
    for i, t in enumerate((0.3, dur / 2, max(0.4, dur - 0.5))):
        ff(["-ss", f"{t:.2f}", "-i", vid, "-frames:v", 1, "-vf", "scale=360:-1", sd / "review" / f"frame-{i}.png"])
    (sd / "review" / "index.json").write_text(json.dumps({"frames": {"tiles": 3}}), encoding="utf-8")
    return {"frames": 3}


def stages(sd: Path) -> list[Stage]:
    me = Path(__file__)
    vid = lambda d: d / "out" / f"{d.name}.mp4"
    shot = lambda d: [d / "shot.json"]
    code = [me, TOOLS / "arabic_display.py"]

    def media(d):      # the backdrop picture / cover object a card reads: a re-recorded story shot behind the recap must rebuild the card
        try:
            card = _shot(d)["card"]
        except (OSError, ValueError, KeyError):
            return []
        return [Path(p) for p in (card.get("backdrop"), card.get("object")) if p and Path(p).is_file() and p != "plate"]
    return [
        Stage("init", lambda d: [], lambda d: [d / "shot.json", d / "calm.json"], lambda d: {"template": "card"}),
        Stage("catalogue", lambda d: shot(d), lambda d: [d / "shot.json"], s_ok),
        Stage("camera", lambda d: shot(d), lambda d: [d / "shot.json"], s_ok),
        Stage("spec", lambda d: shot(d) + code, lambda d: [d / "shot-spec.json"], s_spec),
        Stage("build", lambda d: shot(d) + code, lambda d: [d / "build" / "page.html", d / "build" / "diag.json"], s_build),
        Stage("trace", lambda d: shot(d) + media(d) + code, lambda d: [d / "out" / "card-measure.json", d / "out" / "card.png"], s_trace),
        Stage("record", lambda d: shot(d) + [d / "out" / "card.png"] + code,      # shot.json too: the video length (duration_s) is not in card.png, so a duration-only change used to keep the old video (E02-day, 2026-10-27)
               lambda d: [vid(d), d / "out" / f"{d.name}.encode.json"], s_record),
        Stage("gate", lambda d: [vid(d), d / "out" / "card-measure.json"] + code, lambda d: [d / "gate" / "report.json"], s_gate),
        Stage("review", lambda d: [vid(d)], lambda d: [d / "review" / "index.json"], s_review),
    ]


# ------------------------------------------------------------------ the lit plates of choice_split (C4): the question and each choice light up as the narrator reads them
LIT_STATES = ("question", "choice1", "choice2", "hook")   # hook: both choices light together (the call to pick one)


def lit_plates(card: dict, outdir: Path) -> list[dict]:
    """Screenshot the lit state of each part of a choice_split card as a transparent PNG at its exact place (overlay it on the card video).
    Returns [{state, png, x, y, w, h}]. Thmanyah is loaded from assets/fonts; a missing face refuses (never a fallback)."""
    from playwright.sync_api import sync_playwright
    need_fonts()
    outdir.mkdir(parents=True, exist_ok=True)
    page = outdir / "lit.html"
    page.write_text(card_html({**card, "backdrop_png": None}).replace("</style>", "html,body{background:transparent!important}.vig,.top,.bar{display:none}</style>"), encoding="utf-8")
    res = []
    with sync_playwright() as pw:
        b = pw.chromium.launch(args=["--enable-gpu-rasterization", "--ignore-gpu-blocklist", "--allow-file-access-from-files"])
        try:
            pg = b.new_page(viewport={"width": W, "height": H})
            pg.goto(page.as_uri())
            pg.evaluate("Promise.all(['500 40px thmanyahsans','700 40px thmanyahsans','900 40px thmanyahsans'].map(s => document.fonts.load(s, 'هدى'))).then(() => 1)")
            for st in LIT_STATES:
                idx = {"question": [0], "choice1": [1], "choice2": [2], "hook": [1, 2]}[st]
                pg.evaluate("""(idx) => { const kids = [...document.querySelectorAll('#box > *')];
                    kids.forEach((e, i) => { e.classList.toggle('lit', idx.includes(i)); e.style.visibility = idx.includes(i) ? 'visible' : 'hidden'; }); }""", idx)
                bb = pg.evaluate("""(idx) => { const kids = [...document.querySelectorAll('#box > *')]; const r = idx.map(i => kids[i].getBoundingClientRect());
                    return {x: Math.min(...r.map(a => a.left)), y: Math.min(...r.map(a => a.top)), w: Math.max(...r.map(a => a.right)) - Math.min(...r.map(a => a.left)), h: Math.max(...r.map(a => a.bottom)) - Math.min(...r.map(a => a.top))}; }""", idx)
                png = outdir / f"lit-{st}.png"
                pg.screenshot(path=str(png), omit_background=True, clip={"x": bb["x"], "y": bb["y"], "width": bb["w"], "height": bb["h"]})
                res.append({"state": st, "png": png.name, "x": round(bb["x"]), "y": round(bb["y"]), "w": round(bb["w"]), "h": round(bb["h"])})
        finally:
            b.close()
    return res
