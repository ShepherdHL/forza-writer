from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from forza_writer.legacy_primitive_fit import (
    SQUARE_TYPE_WORD,
    SQUARE_TYPECODE,
    _decompose_mask_to_rectangles,
    _render_glyph_mask,
    fit_glyph_legacy,
)

AMARILLO_FONT = Path.home() / "Desktop" / "amarillo-usaf" / "amarurgt.ttf"
requires_font = pytest.mark.skipif(not AMARILLO_FONT.exists(), reason="test font not present on this machine")


def _mask(size, filled_boxes):
    img = Image.new("L", size, 0)
    draw = ImageDraw.Draw(img)
    for x0, y0, x1, y1 in filled_boxes:
        draw.rectangle([x0, y0, x1 - 1, y1 - 1], fill=255)
    return img


def test_decompose_solid_square_merges_to_one_rectangle():
    mask = _mask((32, 32), [(4, 4, 28, 28)])
    rects = _decompose_mask_to_rectangles(mask, cell_size=1)
    assert len(rects) == 1
    x0, y0, w, h = rects[0]
    assert (x0, y0, x0 + w, y0 + h) == (4, 4, 28, 28)


def test_decompose_l_shape_needs_at_least_two_rectangles():
    mask = _mask((32, 32), [(4, 4, 12, 28), (4, 20, 28, 28)])
    rects = _decompose_mask_to_rectangles(mask, cell_size=1)
    assert len(rects) >= 2


def test_decompose_disjoint_regions_produce_separate_rectangles():
    mask = _mask((40, 20), [(2, 2, 10, 10), (30, 2, 38, 10)])
    rects = _decompose_mask_to_rectangles(mask, cell_size=1)
    # Two well-separated blobs must not merge into one rectangle spanning the gap.
    assert len(rects) == 2
    xs = sorted(r[0] for r in rects)
    assert xs[1] - xs[0] > 10


def test_decompose_empty_mask_returns_no_rectangles():
    mask = _mask((16, 16), [])
    assert _decompose_mask_to_rectangles(mask, cell_size=1) == []


def test_decompose_cell_size_coarsens_rectangle_count():
    mask = _mask((64, 64), [(4, 4, 60, 60)])
    fine = _decompose_mask_to_rectangles(mask, cell_size=1)
    coarse = _decompose_mask_to_rectangles(mask, cell_size=8)
    assert len(fine) >= 1 and len(coarse) >= 1


@requires_font
def test_render_glyph_mask_produces_some_ink():
    mask = _render_glyph_mask("A", AMARILLO_FONT)
    assert mask.mode == "L"
    assert mask.getextrema()[1] > 0  # some pixel is actually painted


@requires_font
def test_fit_glyph_legacy_returns_legacy_strategy_label():
    shapes, strategy = fit_glyph_legacy("A", AMARILLO_FONT)
    assert strategy == "legacy_primitive"
    assert len(shapes) > 0


@requires_font
def test_fit_glyph_legacy_shapes_have_valid_structure():
    shapes, _strategy = fit_glyph_legacy("A", AMARILLO_FONT)
    for shape in shapes:
        assert shape["type"] == SQUARE_TYPECODE
        assert shape["type_word"] == SQUARE_TYPE_WORD
        assert len(shape["data"]) == 7
        assert shape["data"][6] == 0  # no masks in this mode
        assert shape["mask"] is False
        assert shape["color"] == [255, 255, 255, 255]


@requires_font
def test_fit_glyph_legacy_is_centered_near_origin():
    shapes, _strategy = fit_glyph_legacy("A", AMARILLO_FONT, glyph_size=300.0)
    mean_x = sum(s["data"][0] for s in shapes) / len(shapes)
    mean_y = sum(s["data"][1] for s in shapes) / len(shapes)
    assert abs(mean_x) < 150
    assert abs(mean_y) < 150
