# -*- coding: utf-8 -*-
"""Foreign-word glossary (owner, 2026-10-25, CLAUDE.md "Gloss foreign words").

A line that uses a word from a character's own language (a signature word such as «شيكامو») shows, in its caption, the word followed by its
Arabic meaning in brackets: «شيكامو (تحية احترام للكبار)». The glossary is data: bible/series/<series>/glossary.json, built from each
character bible's voice_signature_words. This module is pure text logic (no browser, no model):

  load(root, series)                       entries of the series glossary ([] when the series has none)
  gloss_map(words, speaker, entries)       {index of the LAST word of a glossary match: entry}, longest match first
  with_gloss(words, speaker, entries)      the same words with "(meaning)" inserted after each glossary word (a plate's text)
  strip_gloss(text)                        the text without its bracketed glosses (what counts as the plate's words)
  check_text(text, speaker, entries)       CAP-FOREIGN-GLOSS problems for one caption or on-screen string
  check_captions(captions, lines, entries) the same over captions.json plates (speaker from the script line)
  check_glossary(entries, series_dir)      GLOSSARY problems of the glossary file itself (provenance, no tashkeel, short meanings)

C8 (owner, 2026-10-25: the manager's «أري» showed no translation long enough to read): the glossary is checked against the bibles and the writer tags words.
  foreign_tags(line)                       the line's own "foreign" tags: [{"word", "language", "meaning_ar"}], written by the writer in script.json
  line_entries(line, entries)              the series glossary plus that line's tags (speaker = the line's speaker)
  check_script_tags(lines, entries)        FOREIGN-TAG problems: a tag is in the line with language + short Arabic meaning; an UNTAGGED word of the speaker's is a fault
  bible_candidates(series_dir)             {character: [own-language words]} read from each bible's voice_signature_words block and each voice.md table row (exclamations too)
  audit_coverage(entries, series_dir, arabic_ok)   GLOSSARY-COVERAGE problems: a candidate that is neither a glossary word nor confirmed Arabic (glossary.json "arabic_words")
  unrecognised_words(words, corpus)        caption words the series text never used: a list for a human (CAP-ARABIC-REVIEW, a warning, not a failure)

C11 (owner, 2026-10-25: EVERY cultural word gets its Arabic meaning): CAP-FOREIGN-GLOSS now fails on three things, not one.
  1. a glossary word with no «(meaning)» after it (as before);
  2. a word that is plainly not Arabic: Latin letters, or the non-Arabic letters پ چ گ ڤ ڨ (foreign_script_words);
  3. a word from a character bible's own-language voice section that nobody put in the glossary (bible_foreign_keys): the gap is named, the glossary is the fix.
  Anything else the independent Arabic lexicon does not know goes to a review list (review_words, CAP-ARABIC-REVIEW): a human or the writer says Arabic (glossary.json "arabic_words"),
  a name ("names"), or adds a glossary entry. The lexicon is bibles, voices, culture briefs, worlds and series.md; episode scripts are left OUT of it (series_corpus skip_episodes), because a
  foreign word that only the script itself uses would otherwise vouch for itself (the C8 hole).
  check_foreign(text, speaker, entries, foreign_keys, where)   the problems of items 2 and 3 for one caption string
  bible_foreign_keys(series_dir, entries, arabic_ok)           {normalised phrase: (character, word)} of candidates that are neither glossary nor confirmed Arabic
  review_words(words, corpus, entries, arabic_ok, names)       the words for the review list (not glossary, not confirmed Arabic, not a name, not in the lexicon)

Scope: a character's words are matched in that character's own lines; the narrator (or any speaker that is not a glossary character) may quote
any word that is not ambiguous (same spelling, different meaning, for two characters). Matching is exact on whole words after folding
hamza/alef/ya and stripping punctuation and tashkeel; an Arabic prefix glued to a word (و، ب، ل) is NOT matched, write the word apart.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from arabic_display import display_text, has_tashkeel   # noqa: E402

MEANING_WORDS_MAX = 3
_PUNCT = re.compile(r"[\s،؛؟.,;:!?\"'«»()\[\]{}…\-–—_*]+")
_FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ئ": "ي", "ؤ": "و", "ة": "ه"})
_GLOSS_GROUP = re.compile(r"\s*\(([^)]*)\)")
_LATIN = re.compile(r"[A-Za-z]")


def norm(word: str) -> str:
    """The comparison form of one word: no tashkeel/tatweel, no punctuation, hamza/alef/ya/ta marbuta folded."""
    return _PUNCT.sub("", display_text(word)).translate(_FOLD)


def load(root, series: str | None) -> list[dict]:
    """Entries of bible/series/<series>/glossary.json; no file means no glossary words (an empty list), never an error."""
    if not series:
        return []
    p = Path(root) / "bible" / "series" / series / "glossary.json"
    if not p.is_file():
        return []
    return json.loads(p.read_text(encoding="utf-8")).get("entries", [])


def _key(entry: dict) -> tuple[str, ...]:
    return tuple(norm(w) for w in entry["word"].split())


def _scoped(entries: list[dict], speaker: str | None) -> list[dict]:
    """The entries that may appear in a line: the speaker's own; for anyone else (the narrator) every entry whose spelling is unambiguous."""
    own = [e for e in entries if e.get("character") == speaker]
    if own:
        return own
    count: dict[tuple, int] = {}
    for e in entries:
        count[_key(e)] = count.get(_key(e), 0) + 1
    return [e for e in entries if count[_key(e)] == 1]


def gloss_map(words: list[str], speaker: str | None, entries: list[dict]) -> dict[int, dict]:
    """{index of the last word of each match: entry}. Longest phrase first, left to right, no overlaps."""
    if not entries:
        return {}
    pool = sorted(_scoped(entries, speaker), key=lambda e: -len(_key(e)))
    nw = [norm(w) for w in words]
    out: dict[int, dict] = {}
    i = 0
    while i < len(nw):
        hit = None
        for e in pool:
            k = _key(e)
            if tuple(nw[i:i + len(k)]) == k and all(k):
                hit = (e, len(k))
                break
        if hit:
            out[i + hit[1] - 1] = hit[0]
            i += hit[1]
        else:
            i += 1
    return out


def with_gloss(words: list[str], speaker: str | None, entries: list[dict]) -> list[str]:
    """The words with "(meaning)" put in after each glossary word."""
    gm = gloss_map(words, speaker, entries)
    out: list[str] = []
    for i, w in enumerate(words):
        out.append(w)
        if i in gm:
            out.append(f"({gm[i]['meaning_ar']})")
    return out


def strip_gloss(text: str) -> str:
    return _GLOSS_GROUP.sub("", text).strip()


def _split_glossed(text: str) -> tuple[list[str], dict[int, str]]:
    """A caption text -> (its words without glosses, {word index: the gloss written right after it})."""
    words, glosses = [], {}
    pos = 0
    for m in _GLOSS_GROUP.finditer(text):
        for w in text[pos:m.start()].split():
            words.append(w)
        if words:
            glosses[len(words) - 1] = m.group(1).strip()
        pos = m.end()
    words += text[pos:].split()
    return words, glosses


def check_text(text: str, speaker: str | None, entries: list[dict], where: str = "") -> list[str]:
    """CAP-FOREIGN-GLOSS: every glossary word in the text is followed by its meaning in brackets. Returns problems, [] when clean."""
    if not entries or not text:
        return []
    words, glosses = _split_glossed(text)
    f = []
    for idx, e in gloss_map(words, speaker, entries).items():
        got = glosses.get(idx)
        shown = " ".join(words[idx - len(_key(e)) + 1: idx + 1])
        if not got:
            f.append(f"CAP-FOREIGN-GLOSS {where}«{shown}» ({e.get('language', '?')}) has no «({e['meaning_ar']})» after it")
        elif norm(got) != norm(e["meaning_ar"]):
            f.append(f"CAP-FOREIGN-GLOSS {where}«{shown}» is glossed «({got})» but the glossary says «({e['meaning_ar']})»")
    return f


def foreign_tags(line: dict) -> list[dict]:
    """The writer's own-language tags of one script line (the optional "foreign" list)."""
    return [t for t in (line or {}).get("foreign", []) or [] if isinstance(t, dict)]


def line_entries(line: dict, entries: list[dict]) -> list[dict]:
    """Series glossary + the line's tags. A tag the glossary does not hold becomes an entry for the line's speaker, so a tagged word with no
    gloss is caught even when nobody put it in glossary.json yet (the C8 root cause: the check only knew the glossary)."""
    out = list(entries)
    have = {(e.get("character"), _key(e)) for e in entries if e.get("word")}
    sp = (line or {}).get("speaker")
    for t in foreign_tags(line):
        if t.get("word") and t.get("meaning_ar") and (sp, _key(t)) not in have:
            out.append({"word": t["word"], "language": t.get("language", "?"), "meaning_ar": t["meaning_ar"], "character": sp, "source": "script tag"})
    return out


def check_captions(captions: list[dict], lines: dict[str, dict], entries: list[dict]) -> list[str]:
    """Plates of captions.json: the speaker comes from the plate's script line; the line's own tags count as glossary words."""
    f: list[str] = []
    for c in captions:
        ln = lines.get(c.get("line")) or {}
        f += check_text(str(c.get("text", "")), ln.get("speaker"), line_entries(ln, entries), where=f"plate {c.get('line', '?')} ")
    return f


def check_script_tags(lines: list[dict], entries: list[dict]) -> list[str]:
    """FOREIGN-TAG: the writer tags every own-language word of a line. A tag names a word of the line, a language and an Arabic meaning of at most
    MEANING_WORDS_MAX words (no tashkeel, no Latin), and agrees with the glossary when the glossary has the word. A glossary word of the speaker's
    that the line uses but does not tag is a fault: the caption would show a bare foreign word to the viewer."""
    f: list[str] = []
    for ln in lines:
        words = ln.get("text", "").split()
        nw = [norm(w) for w in words]
        tagged = set()
        for t in foreign_tags(ln):
            w = str(t.get("word", ""))
            where = f"FOREIGN-TAG line {ln.get('id', '?')} «{w}»"
            if not w.strip() or not str(t.get("language", "")).strip() or not str(t.get("meaning_ar", "")).strip():
                f.append(f"{where}: word, language and meaning_ar are all required")
                continue
            k = tuple(norm(x) for x in w.split())
            if not any(tuple(nw[i:i + len(k)]) == k for i in range(len(nw))):
                f.append(f"{where}: the word is not in the line's text")
            if has_tashkeel(t["meaning_ar"]) or _LATIN.search(t["meaning_ar"]) or len(t["meaning_ar"].split()) > MEANING_WORDS_MAX:
                f.append(f"{where}: meaning «{t['meaning_ar']}» must be Arabic without tashkeel, at most {MEANING_WORDS_MAX} words")
            tagged.add(k)
            for e in entries:
                if e.get("character") == ln.get("speaker") and _key(e) == k and norm(e["meaning_ar"]) != norm(t["meaning_ar"]):
                    f.append(f"{where}: tagged «{t['meaning_ar']}» but the glossary says «{e['meaning_ar']}»")
        own = [x for x in entries if x.get("character") == ln.get("speaker")]
        for idx, e in gloss_map(words, ln.get("speaker"), own).items():
            if _key(e) not in tagged:
                f.append(f"FOREIGN-TAG line {ln.get('id', '?')} «{e['word']}» ({e.get('language', '?')}) is the speaker's own-language word but the line does not tag it in \"foreign\"")
    return f


_CAND_QUOTED = re.compile(r"«([^»]+)»\s*(?:\(|\|)\s*\*?[A-Za-zñ\"“]")
_CAND_PLAIN = re.compile(r"([ء-يً-ْ]+(?: [ء-يً-ْ]+)?) [a-zñ]+ \(")
_BLOCK = re.compile(r"^- voice_signature_words:.*?(?=^- \w+:)", re.S | re.M)


def bible_candidates(series_dir) -> dict[str, list[str]]:
    """Own-language word candidates per character: «word» followed by a romanisation or translation in the voice_signature_words block of bible.md
    and in the first two cells of every voice.md table row (exclamations such as «آيغو» live there). Recall over precision: what is Arabic is
    confirmed once in glossary.json "arabic_words"."""
    out: dict[str, list[str]] = {}
    for c in sorted((Path(series_dir) / "characters").iterdir()):
        if not c.is_dir():
            continue
        found: list[str] = []
        b = c / "bible.md"
        if b.is_file():
            m = _BLOCK.search(b.read_text(encoding="utf-8"))
            if m:
                found += _CAND_QUOTED.findall(m.group(0)) + _CAND_PLAIN.findall(m.group(0))
        v = c / "voice.md"
        if v.is_file():
            rows = []
            for ln in v.read_text(encoding="utf-8").splitlines():
                cells = ln.split("|")
                if ln.startswith("|") and "«" in ln and len(cells) > 2:
                    rows.append(cells[1] + "|" + cells[2])
            found += _CAND_QUOTED.findall("\n".join(rows))
        out[c.name] = list(dict.fromkeys(w.strip().rstrip(".،:") for w in found))
    return out


def audit_coverage(entries: list[dict], series_dir, arabic_ok: list[str] | None = None) -> list[str]:
    """GLOSSARY-COVERAGE: every candidate of every character bible is a glossary word of that character or confirmed Arabic."""
    ok = {" ".join(norm(w) for w in a.split()) for a in (arabic_ok or [])}
    have = {(e.get("character"), " ".join(_key(e))) for e in entries if e.get("word")}
    f: list[str] = []
    for ch, words in bible_candidates(series_dir).items():
        for w in words:
            k = " ".join(norm(x) for x in w.split())
            if k and (ch, k) not in have and k not in ok:
                f.append(f"GLOSSARY-COVERAGE {ch}: «{w}» is in the bible's voice section with a romanisation but is neither in the glossary nor in glossary.json \"arabic_words\"")
    return f


_AR_TOKEN = re.compile(r"[ء-يٱ]+")


def series_corpus(series_dir, skip_episodes: bool = False) -> set[str]:
    """Every Arabic word the series text has used (bibles, voices, culture briefs, worlds, scripts, outlines), folded. glossary.json is left out: its foreign words
    must not make themselves look like Arabic. skip_episodes also leaves out episodes/ (the scripts under review must not vouch for themselves)."""
    words: set[str] = set()
    for p in Path(series_dir).rglob("*"):
        if skip_episodes and "episodes" in p.relative_to(series_dir).parts:
            continue
        if p.is_file() and p.suffix in (".md", ".json") and p.name != "glossary.json":
            for t in _AR_TOKEN.findall(display_text(p.read_text(encoding="utf-8", errors="ignore"))):
                words.add(norm(t))
    return words


def _stems(w: str):
    yield w
    for pre in ("وال", "فال", "بال", "كال", "لل", "ال", "و", "ف", "ب", "ل", "ك"):
        if w.startswith(pre) and len(w) - len(pre) >= 2:
            rest = w[len(pre):]
            yield rest
            if rest.startswith("ال") and len(rest) > 4:
                yield rest[2:]


def unrecognised_words(words: list[str], corpus: set[str], entries: list[dict] | None = None) -> list[str]:
    """Caption words none of whose stems is in the series corpus and that are not glossary words: not proof of an error, a list for a human to
    read (CAP-ARABIC-REVIEW, a warning). A word the series has never used is exactly how an own-language exclamation slips in without a gloss."""
    known = {w for e in entries or [] for w in _key(e)}
    out = []
    for w in words:
        n = norm(w)
        if n and n not in known and _AR_TOKEN.search(n) and not any(s in corpus for s in _stems(n)):
            out.append(w)
    return out


_NON_ARABIC_LETTERS = re.compile("[پچگڤڨ]")


def foreign_script_words(words: list[str]) -> list[str]:
    """Words that are not Arabic by their letters alone: any Latin letter, or a Persian/Urdu/Pashto letter (the proofreading rule bans them in transliterations)."""
    return [w for w in words if _LATIN.search(w) or _NON_ARABIC_LETTERS.search(w)]


def bible_foreign_keys(series_dir, entries: list[dict], arabic_ok: list[str] | None = None) -> dict[str, tuple[str, str]]:
    """{folded phrase: (character, word as the bible writes it)} of every bible candidate that is not a glossary word (of any character) and not confirmed Arabic."""
    ok = {" ".join(norm(w) for w in a.split()) for a in (arabic_ok or [])}
    have = {" ".join(_key(e)) for e in entries if e.get("word")}
    out: dict[str, tuple[str, str]] = {}
    for ch, words in bible_candidates(series_dir).items():
        for w in words:
            k = " ".join(norm(x) for x in w.split())
            if k and k not in have and k not in ok:
                out[k] = (ch, w)
    return out


def check_foreign(text: str, speaker: str | None, entries: list[dict], foreign_keys: dict[str, tuple[str, str]] | None = None, where: str = "",
                  loanwords: dict[str, tuple[str, str]] | None = None) -> list[str]:
    """CAP-FOREIGN-GLOSS items 2 and 3 for one caption string: a word that is plainly not Arabic, a foreign loanword the glossary lists (انيميشن), and an own-language
    word of a bible that has no glossary entry. A word followed by its own bracket is accepted (shown with its meaning, which is the point of the rule). Hashtags are
    read word by word (#رسوم_متحركة is two words)."""
    if not text:
        return []
    words, glosses = _split_glossed(text)
    f: list[str] = []
    for i, w in enumerate(words):
        if i in glosses:
            continue
        if foreign_script_words([w]):
            f.append(f"CAP-FOREIGN-GLOSS {where}«{w}» is not written in Arabic letters only: gloss it, or write it in Arabic")
        for part in re.split(r"[#_]+", w):
            hit = (loanwords or {}).get(norm(part)) if norm(part) else None
            if hit:
                f.append(f"CAP-FOREIGN-GLOSS {where}«{part}» is a foreign loanword ({hit[1]}): write «{hit[0]}» instead, or gloss it")
    nw = [norm(w) for w in words]
    for k, (ch, shown) in (foreign_keys or {}).items():
        kk = k.split()
        for i in range(len(nw) - len(kk) + 1):
            if nw[i:i + len(kk)] == kk and (i + len(kk) - 1) not in glosses:
                f.append(f"CAP-FOREIGN-GLOSS {where}«{shown}» is an own-language word of {ch}'s bible with no glossary entry and no gloss: add it to glossary.json")
    return f


def lexicon(root, series: str | None) -> dict:
    """Everything the C11 checks read, from glossary.json and the series folder: entries, arabic_ok (confirmed Arabic), names, loanwords {folded word: (Arabic replacement,
    language)}, foreign_keys (bible own-language words with no entry), corpus (the independent lexicon: series text without the episode scripts)."""
    empty = {"entries": [], "arabic_ok": [], "names": [], "loanwords": {}, "foreign_keys": {}, "corpus": set()}
    if not series:
        return empty
    sd = Path(root) / "bible" / "series" / series
    gp = sd / "glossary.json"
    if not gp.is_file():
        return empty
    data = json.loads(gp.read_text(encoding="utf-8"))
    ent = data.get("entries", [])
    ok = data.get("arabic_words", [])
    return {"entries": ent, "arabic_ok": ok, "names": data.get("names", []), "corpus": series_corpus(sd, skip_episodes=True),
            "loanwords": {norm(l["word"]): (l["meaning_ar"], l.get("language", "?")) for l in data.get("loanwords", [])},
            "foreign_keys": bible_foreign_keys(sd, ent, ok) if (sd / "characters").is_dir() else {}}


def review_words(words: list[str], corpus: set[str], entries: list[dict] | None = None, arabic_ok: list[str] | None = None, names: list[str] | None = None) -> list[str]:
    """The review list of one episode: caption words that are not glossary words, not confirmed Arabic, not a listed name, and whose stems are not in the lexicon corpus."""
    ok = {w for a in (arabic_ok or []) for w in (norm(x) for x in a.split())}
    ok |= {norm(n) for nm in (names or []) for n in nm.split()}
    return list(dict.fromkeys(re.sub(r"[#_]+", " ", w).strip(" ،؛؟.,;:!?\"«»()") for w in unrecognised_words(words, corpus, entries) if norm(w) not in ok))


def check_glossary(entries: list[dict], series_dir: Path | None = None) -> list[str]:
    """GLOSSARY problems of the file itself. With series_dir, every word must also appear in its character's bible (provenance)."""
    f: list[str] = []
    seen: dict[tuple, str] = {}
    bibles: dict[str, str] = {}
    for e in entries:
        w = e.get("word", "")
        for k in ("word", "language", "meaning_ar", "character"):
            if not str(e.get(k, "")).strip():
                f.append(f"GLOSSARY {w or '?'}: field '{k}' is empty")
        for k in ("word", "meaning_ar"):
            v = str(e.get(k, ""))
            if has_tashkeel(v):
                f.append(f"GLOSSARY {w}: {k} carries tashkeel (everything people see is written without it)")
            if _LATIN.search(v) or any(c in v for c in "()"):
                f.append(f"GLOSSARY {w}: {k} holds Latin letters or brackets")
        if len(str(e.get("meaning_ar", "")).split()) > MEANING_WORDS_MAX:
            f.append(f"GLOSSARY {w}: meaning is over {MEANING_WORDS_MAX} words (a plate shows it under the word)")
        key = (e.get("character"), _key(e) if w else ())
        if key in seen:
            f.append(f"GLOSSARY {w}: listed twice for {e.get('character')}")
        seen[key] = w
        if series_dir is not None and e.get("character"):
            b = Path(series_dir) / "characters" / e["character"] / "bible.md"
            if not b.is_file():
                f.append(f"GLOSSARY {w}: no bible for character {e['character']}")
                continue
            vo = b.parent / "voice.md"      # C11: the voice section's own tables are a source too (Partner's Spanish bursts live only there)
            txt = bibles.setdefault(e["character"], norm_text(b.read_text(encoding="utf-8") + (" " + vo.read_text(encoding="utf-8") if vo.is_file() else "")))
            if " ".join(_key(e)) not in txt:
                f.append(f"GLOSSARY {w}: not found in {e['character']}'s bible (words come from voice_signature_words)")
    return f


def norm_text(s: str) -> str:
    return " ".join(norm(w) for w in re.split(r"\s+", s) if norm(w))


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    bad = 0
    for g in sorted((root / "bible" / "series").glob("*/glossary.json")):
        data = json.loads(g.read_text(encoding="utf-8"))
        probs = check_glossary(data.get("entries", []), g.parent) + audit_coverage(data.get("entries", []), g.parent, data.get("arabic_words", []))
        print(g.relative_to(root), "OK" if not probs else "")
        for p in probs:
            print(" ", p)
        bad += len(probs)
    sys.exit(1 if bad else 0)
