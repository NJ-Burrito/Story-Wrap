import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import arabic_display as ad  # noqa: E402
import qg_checks as qc  # noqa: E402

V = "ماذا تفعلُ هُدَى؟ كتــاب  ٱلْ"


def test_strips_marks_tatweel_and_spacing():
    out = ad.display_text(V)
    assert not ad.has_tashkeel(out) and "ـ" not in out and "  " not in out
    assert out.startswith("ماذا تفعل هدى؟ كتاب")
    assert ad.display_text("هُدى\n  ١ على الرّفِّ ") == "هدى\n١ على الرف"


def test_tts_text_untouched():
    line = {"text": "هُدى", "tts_text": "هُدَى"}
    ad.display_text(line["text"])
    assert line["tts_text"] == "هُدَى" and ad.has_tashkeel(line["tts_text"])


def test_spec_check_flags_vowelled_text():
    spec = {"beats": [{"id": "b", "texts": [{"id": "t", "string": "هُدى"}]}], "transitions": []}
    fails = qc.check_texts(spec)
    assert any("TEXT-NO-TASHKEEL" in f for f in fails)
    spec["beats"][0]["texts"][0]["string"] = "هدى"
    assert not any("TEXT-NO-TASHKEEL" in f for f in qc.check_texts(spec))
