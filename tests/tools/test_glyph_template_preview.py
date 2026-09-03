import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "tools"))
from glyph_template_preview import render_block_sample, render_grid_preview  # noqa: E402
from gen_glyph_template import build_template, categorized_for_charset  # noqa: E402
from forza_writer.glyph_template import build_flat_template  # noqa: E402

_ASSETS_FONTS = Path(__file__).resolve().parent.parent.parent / "assets" / "fonts"
LIBERATION_SANS = _ASSETS_FONTS / "LiberationSans-Regular.ttf"


def _basic_latin_template(chars_per_row=10):
    return build_template(categorized_for_charset("basic-latin"), "PREVIEW", chars_per_row=chars_per_row)


def test_grid_preview_font_traced_returns_requested_size():
    template = _basic_latin_template()
    img = render_grid_preview(template, LIBERATION_SANS, text_color="#ff8800", size=(400, 260))
    assert img.size == (400, 260)


def test_grid_preview_blank_returns_requested_size():
    template = _basic_latin_template()
    img = render_grid_preview(template, None, size=(400, 260))
    assert img.size == (400, 260)


def test_grid_preview_missing_glyphs_falls_back_without_raising():
    # Liberation Sans has no Hiragana coverage, so every slot is "missing" --
    # matches the real SVG generator's own label-only fallback, must not raise.
    template = build_flat_template(list("あいうえお"), "PREVIEW-KANA", chars_per_row=5)
    img = render_grid_preview(template, LIBERATION_SANS, size=(300, 200))
    assert img.size == (300, 200)


def test_grid_preview_nonexistent_font_falls_back_without_raising():
    template = _basic_latin_template()
    img = render_grid_preview(template, Path("C:/does/not/exist.ttf"), size=(300, 200))
    assert img.size == (300, 200)


def test_grid_preview_large_grid_does_not_raise():
    # A big Split-mode-style block (well beyond a typical checked block) --
    # cell size shrinks but rendering must still complete and stay in bounds.
    template = build_flat_template(list("ABCDEFGHIJKLMNOPQRSTUVWXYZ") * 20, "PREVIEW-BIG", chars_per_row=20)
    img = render_grid_preview(template, LIBERATION_SANS, size=(640, 420))
    assert img.size == (640, 420)


def test_block_sample_short_list():
    img = render_block_sample(LIBERATION_SANS, list(".,!?"), size=(220, 40))
    assert img.size == (220, 40)


def test_block_sample_long_list_truncates_to_sample_size():
    # 26 chars but sample_size defaults to 8 -- must not error or blow past
    # the box just because the block itself is large.
    img = render_block_sample(LIBERATION_SANS, list("ABCDEFGHIJKLMNOPQRSTUVWXYZ"), size=(220, 40))
    assert img.size == (220, 40)


def test_block_sample_nonexistent_font_falls_back_without_raising():
    img = render_block_sample(Path("C:/does/not/exist.ttf"), list(".,!?"), size=(220, 40))
    assert img.size == (220, 40)
