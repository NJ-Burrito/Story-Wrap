"""Arabic display text: nothing people see carries tashkeel (CLAUDE.md "No tashkeel in anything people see").

display_text(s) is for captions, on-screen text, end cards, post captions, comments and the bio.
It is never applied to TTS input (tts_text keeps its vowels) or to agents' reading copies.
"""
from __future__ import annotations

import re

# fathatan..sukun (U+064B-U+0652), superscript alef (U+0670), tatweel (U+0640)
DIACRITICS = "".join(chr(c) for c in range(0x064B, 0x0653)) + "\u0670"
TATWEEL = "\u0640"
_STRIP = re.compile("[" + DIACRITICS + TATWEEL + "]")
_BAD = _STRIP


def has_tashkeel(s) -> bool:
    return bool(isinstance(s, str) and _BAD.search(s))


def tashkeel_chars(s) -> list[str]:
    """The distinct offending code points in s, as U+XXXX strings."""
    return sorted({f"U+{ord(c):04X}" for c in _BAD.findall(s)}) if isinstance(s, str) else []


def display_text(s):
    """Strip diacritics and tatweel, collapse runs of spaces/tabs, trim line ends. Newlines are kept."""
    if not isinstance(s, str):
        return s
    s = _STRIP.sub("", s)
    s = re.sub(r"[ \t\u00a0]{2,}", " ", s)
    return "\n".join(line.strip(" \t") for line in s.split("\n")).strip()
