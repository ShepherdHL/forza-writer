import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "tools"))
from forza_writer.script_detect import SCRIPTS, detect_font_scripts  # noqa: E402

AMARILLO_FONT = Path.home() / "Desktop" / "amarillo-usaf" / "amarurgt.ttf"
requires_amarillo = pytest.mark.skipif(not AMARILLO_FONT.exists(), reason="test font not present on this machine")

JOKERMAN_FONT = Path(r"C:\Windows\Fonts\JOKERMAN.TTF")
requires_jokerman = pytest.mark.skipif(not JOKERMAN_FONT.exists(), reason="Jokerman not installed on this machine")

# Real fonts confirmed present on this Windows machine (checked against
# the registry via enumerate_installed_fonts during implementation) —
# each guarded individually so the suite degrades gracefully on a
# differently-provisioned machine rather than failing outright.
ARIAL_FONT = Path(r"C:\Windows\Fonts\arial.ttf")
requires_arial = pytest.mark.skipif(not ARIAL_FONT.exists(), reason="Arial not installed on this machine")

MALGUN_FONT = Path(r"C:\Windows\Fonts\malgun.ttf")
requires_malgun = pytest.mark.skipif(not MALGUN_FONT.exists(), reason="Malgun Gothic not installed on this machine")

LEELAWADEE_FONT = Path(r"C:\Windows\Fonts\leelawui.ttf")
requires_leelawadee = pytest.mark.skipif(not LEELAWADEE_FONT.exists(),
                                          reason="Leelawadee UI not installed on this machine")


def test_scripts_list_matches_requested_order():
    assert SCRIPTS == [
        "Latin", "Cyrillic", "Greek", "Japanese", "Korean",
        "Traditional Chinese", "Simplified Chinese", "Arabic", "Hebrew", "Devanagari", "Thai",
    ]


def test_detect_font_scripts_returns_empty_set_for_missing_file(tmp_path):
    assert detect_font_scripts(tmp_path / "does-not-exist.ttf") == set()


def test_detect_font_scripts_returns_empty_set_for_malformed_file(tmp_path):
    bad = tmp_path / "bad.ttf"
    bad.write_bytes(b"not a real font file")
    assert detect_font_scripts(bad) == set()


@requires_amarillo
def test_amarillo_usaf_detected_as_latin_only():
    detected = detect_font_scripts(AMARILLO_FONT, "AmarilloUSAF")
    assert "Latin" in detected
    assert "Japanese" not in detected
    assert "Arabic" not in detected
    assert "Traditional Chinese" not in detected
    assert "Simplified Chinese" not in detected


@requires_jokerman
def test_jokerman_detected_as_latin_only():
    detected = detect_font_scripts(JOKERMAN_FONT, "Jokerman")
    assert detected == {"Latin"}


@requires_arial
def test_arial_detected_as_latin_cyrillic_greek_arabic():
    # Confirmed empirically: modern Windows-shipped Arial carries full
    # Cyrillic/Greek/Arabic cmap coverage, not just Latin.
    detected = detect_font_scripts(ARIAL_FONT, "Arial")
    assert {"Latin", "Cyrillic", "Greek", "Arabic"} <= detected
    assert "Thai" not in detected
    assert "Devanagari" not in detected


@requires_malgun
def test_malgun_gothic_detected_as_korean_and_japanese():
    # Real Korean UI font that also happens to carry full Hiragana/Katakana
    # coverage (86-90%, measured) — genuinely usable for Japanese kana too.
    detected = detect_font_scripts(MALGUN_FONT, "Malgun Gothic")
    assert "Korean" in detected
    assert "Japanese" in detected
    assert "Thai" not in detected


@requires_leelawadee
def test_leelawadee_ui_detected_as_thai():
    detected = detect_font_scripts(LEELAWADEE_FONT, "Leelawadee UI")
    assert "Thai" in detected
    assert "Korean" not in detected
    assert "Japanese" not in detected


def test_chinese_classification_uses_simplified_name_hint():
    from forza_writer.script_detect import _classify_chinese
    assert _classify_chinese("Microsoft YaHei") == {"Simplified Chinese"}
    assert _classify_chinese("Noto Sans SC") == {"Simplified Chinese"}


def test_chinese_classification_uses_traditional_name_hint():
    from forza_writer.script_detect import _classify_chinese
    assert _classify_chinese("Microsoft JhengHei") == {"Traditional Chinese"}
    assert _classify_chinese("Noto Sans TC") == {"Traditional Chinese"}


def test_chinese_classification_ambiguous_name_returns_both():
    from forza_writer.script_detect import _classify_chinese
    assert _classify_chinese("Noto Sans JP") == {"Simplified Chinese", "Traditional Chinese"}
