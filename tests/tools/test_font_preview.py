import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "tools"))
from font_preview import clear_cache, render_font_name  # noqa: E402

AMARILLO_FONT = Path.home() / "Desktop" / "amarillo-usaf" / "amarurgt.ttf"
requires_font = pytest.mark.skipif(not AMARILLO_FONT.exists(), reason="test font not present on this machine")


def setup_function():
    clear_cache()


@requires_font
def test_renders_a_real_font_to_an_image_of_the_requested_size():
    img = render_font_name(AMARILLO_FONT, "Amarillo USAF", size=(180, 40))
    assert img.size == (180, 40)


@requires_font
def test_result_is_cached():
    img1 = render_font_name(AMARILLO_FONT, "Amarillo USAF")
    img2 = render_font_name(AMARILLO_FONT, "Amarillo USAF")
    assert img1 is img2


def test_nonexistent_font_falls_back_without_raising():
    img = render_font_name(Path("C:/does/not/exist.ttf"), "Nonexistent Font", size=(180, 40))
    assert img.size == (180, 40)


def test_corrupt_font_file_falls_back_without_raising(tmp_path):
    bad_font = tmp_path / "bad.ttf"
    bad_font.write_bytes(b"not a real font file")
    img = render_font_name(bad_font, "Bad Font", size=(180, 40))
    assert img.size == (180, 40)


def test_different_bg_fg_produce_different_cache_entries():
    img1 = render_font_name(Path("C:/does/not/exist.ttf"), "X", bg="#000000", fg="#ffffff")
    img2 = render_font_name(Path("C:/does/not/exist.ttf"), "X", bg="#ffffff", fg="#000000")
    assert img1 is not img2
