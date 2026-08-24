from pathlib import Path

import pytest

from forza_writer.direct_generate import generate_modern
from forza_writer.shaped_text import _directional_runs, shape_text


ARIAL = Path(r"C:\Windows\Fonts\arial.ttf")
requires_arial = pytest.mark.skipif(not ARIAL.exists(), reason="Arial is unavailable")


@requires_arial
def test_arabic_shapes_to_contextual_forms_and_lam_alef_ligature():
    line = shape_text("سلام", ARIAL)[0]

    names = [glyph.glyph_name for glyph in line.glyphs]
    assert line.direction == "rtl"
    assert names == ["uni0645", "uniFEFC", "uniFEB3"]
    assert len(names) < len("سلام")
    assert all(glyph.x_advance >= 0 for glyph in line.glyphs)


@requires_arial
def test_modern_arabic_generation_uses_shaped_glyph_names():
    shapes, warnings, metadata = generate_modern("سلام", ARIAL)

    assert shapes
    assert warnings == []
    assert metadata["shaping"] == "harfbuzz"
    assert metadata["line_directions"] == ["rtl"]
    assert set(metadata["strategies"]) == {"uni0645", "uniFEFC", "uniFEB3"}


@requires_arial
def test_directional_mark_or_join_control_does_not_crash_empty_outline_path():
    shapes, _warnings, metadata = generate_modern("\u200fسلام\u200d", ARIAL)

    assert shapes
    assert metadata["shaping"] == "harfbuzz"


def test_common_mixed_direction_runs_are_put_in_visual_order():
    base, runs = _directional_runs("سباق 2026")
    assert base == "rtl"
    assert [direction for _start, _text, direction in runs] == ["ltr", "rtl"]

