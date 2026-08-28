"""Tests for forza_writer/plates/layout_engine.py: mm-space -> plate-local
shape-unit box conversion, shape bounding boxes, and box-alignment placement.
Pure geometry -- no fonts, no fontpacks, just plain shape dicts."""

import pytest

from forza_writer.layout import PIXEL_ART_SQUARE_SIZE
from forza_writer.plates.layout_engine import (
    PlacedBox,
    place_shapes_in_box,
    plate_decoration_box,
    plate_field_box,
    scale_shapes_to_height,
    shape_bbox,
    shapes_bbox,
)
from forza_writer.plates.template import (
    AccuracyStatus,
    CharSource,
    Decoration,
    DecorationKind,
    FieldRole,
    PlateField,
    PlateTemplate,
    Provenance,
)


def _shape(cx, cy, sx=1.0, sy=1.0):
    return {"type": 0, "type_word": 0, "data": [cx, cy, sx, sy, 0.0, 0.0, 0], "color": [255, 255, 255, 255]}


def _template(width_mm=300.0, height_mm=150.0):
    return PlateTemplate(
        template_id="t", display_name_key="k", country="US", jurisdiction=None,
        era="current", plate_type="passenger", width_mm=width_mm, height_mm=height_mm,
        accuracy_status=AccuracyStatus.FICTIONAL, provenance=Provenance(source_notes="test"),
        background=Decoration(decoration_id="bg", kind=DecorationKind.SOLID_FILL, x_mm=0.0, y_mm=0.0,
                               color=(255, 255, 255, 255), editable=False),
        border=None, fields=(),
    )


def _field(x_mm, y_mm, width_mm, height_mm, alignment="center"):
    return PlateField(
        field_id="f", label_key="k", role=FieldRole.REGISTRATION,
        x_mm=x_mm, y_mm=y_mm, width_mm=width_mm, height_mm=height_mm, alignment=alignment,
        char_source=CharSource(font_file="X"),
    )


# ---------------------------------------------------------------------------
# plate_field_box / plate_decoration_box: mm -> plate-centered units
# ---------------------------------------------------------------------------

def test_field_box_top_left_corner_maps_to_plate_top_left():
    template = _template(width_mm=300.0, height_mm=150.0)
    field = _field(x_mm=0.0, y_mm=0.0, width_mm=100.0, height_mm=50.0)
    box = plate_field_box(template, field)
    assert box.left == pytest.approx(-150.0)
    assert box.top == pytest.approx(-75.0)
    assert box.width == pytest.approx(100.0)
    assert box.height == pytest.approx(50.0)


def test_field_box_centered_on_plate_when_field_spans_whole_plate():
    template = _template(width_mm=300.0, height_mm=150.0)
    field = _field(x_mm=0.0, y_mm=0.0, width_mm=300.0, height_mm=150.0)
    box = plate_field_box(template, field)
    assert box.cx == pytest.approx(0.0)
    assert box.cy == pytest.approx(0.0)


def test_field_box_bottom_right_field_is_positive_in_both_axes():
    template = _template(width_mm=200.0, height_mm=100.0)
    field = _field(x_mm=150.0, y_mm=80.0, width_mm=50.0, height_mm=20.0)
    box = plate_field_box(template, field)
    assert box.right == pytest.approx(100.0)
    assert box.bottom == pytest.approx(50.0)


def test_decoration_box_full_bleed_ignores_position_and_spans_whole_plate():
    template = _template(width_mm=520.0, height_mm=110.0)
    deco = Decoration(decoration_id="bg", kind=DecorationKind.SOLID_FILL, x_mm=999.0, y_mm=999.0)
    box = plate_decoration_box(template, deco)
    assert box.cx == pytest.approx(0.0)
    assert box.cy == pytest.approx(0.0)
    assert box.width == pytest.approx(520.0)
    assert box.height == pytest.approx(110.0)


def test_decoration_box_sized_decoration_positions_like_a_field():
    template = _template(width_mm=520.0, height_mm=110.0)
    deco = Decoration(decoration_id="eu-band", kind=DecorationKind.JURISDICTION_MARK,
                       x_mm=0.0, y_mm=0.0, width_mm=40.0, height_mm=110.0)
    box = plate_decoration_box(template, deco)
    assert box.left == pytest.approx(-260.0)
    assert box.top == pytest.approx(-55.0)
    assert box.width == pytest.approx(40.0)
    assert box.height == pytest.approx(110.0)


# ---------------------------------------------------------------------------
# shape_bbox / shapes_bbox
# ---------------------------------------------------------------------------

def test_shape_bbox_matches_pixel_art_square_size_convention():
    shape = _shape(cx=10.0, cy=-5.0, sx=2.0, sy=1.0)
    min_x, min_y, max_x, max_y = shape_bbox(shape)
    half_w = 2.0 * PIXEL_ART_SQUARE_SIZE / 2
    half_h = 1.0 * PIXEL_ART_SQUARE_SIZE / 2
    assert min_x == pytest.approx(10.0 - half_w)
    assert max_x == pytest.approx(10.0 + half_w)
    assert min_y == pytest.approx(-5.0 - half_h)
    assert max_y == pytest.approx(-5.0 + half_h)


def test_shapes_bbox_is_union_of_all_shapes():
    shapes = [_shape(cx=-50.0, cy=0.0, sx=0.1, sy=0.1), _shape(cx=50.0, cy=0.0, sx=0.1, sy=0.1)]
    min_x, _, max_x, _ = shapes_bbox(shapes)
    assert min_x < -50.0 + 1.0  # left edge of the leftmost shape
    assert max_x > 50.0 - 1.0   # right edge of the rightmost shape


def test_shapes_bbox_of_empty_list_is_none():
    assert shapes_bbox([]) is None


# ---------------------------------------------------------------------------
# place_shapes_in_box: alignment
# ---------------------------------------------------------------------------

def test_place_shapes_in_box_center_alignment_centers_content():
    shapes = [_shape(cx=0.0, cy=0.0, sx=0.1, sy=0.1)]
    box = PlacedBox(cx=100.0, cy=50.0, width=200.0, height=100.0)
    placed = place_shapes_in_box(shapes, box, alignment="center")
    min_x, min_y, max_x, max_y = shapes_bbox(placed)
    assert (min_x + max_x) / 2 == pytest.approx(box.cx)
    assert (min_y + max_y) / 2 == pytest.approx(box.cy)


def test_place_shapes_in_box_left_alignment_flushes_left_edge():
    shapes = [_shape(cx=0.0, cy=0.0, sx=0.1, sy=0.1)]
    box = PlacedBox(cx=100.0, cy=50.0, width=200.0, height=100.0)
    placed = place_shapes_in_box(shapes, box, alignment="left")
    min_x, _, _, _ = shapes_bbox(placed)
    assert min_x == pytest.approx(box.left)


def test_place_shapes_in_box_right_alignment_flushes_right_edge():
    shapes = [_shape(cx=0.0, cy=0.0, sx=0.1, sy=0.1)]
    box = PlacedBox(cx=100.0, cy=50.0, width=200.0, height=100.0)
    placed = place_shapes_in_box(shapes, box, alignment="right")
    _, _, max_x, _ = shapes_bbox(placed)
    assert max_x == pytest.approx(box.right)


def test_place_shapes_in_box_is_always_vertically_centered_regardless_of_alignment():
    shapes = [_shape(cx=0.0, cy=0.0, sx=0.1, sy=0.1)]
    box = PlacedBox(cx=100.0, cy=50.0, width=200.0, height=100.0)
    for alignment in ("left", "center", "right", "justify"):
        placed = place_shapes_in_box(shapes, box, alignment=alignment)
        _, min_y, _, max_y = shapes_bbox(placed)
        assert (min_y + max_y) / 2 == pytest.approx(box.cy)


def test_place_shapes_in_box_preserves_scale_rotation_color_mask():
    shape = {"type": 5, "type_word": 6, "data": [0.0, 0.0, 1.5, 0.5, 12.0, 0.2, 1],
             "color": [10, 20, 30, 255], "mask": True}
    box = PlacedBox(cx=0.0, cy=0.0, width=10.0, height=10.0)
    placed = place_shapes_in_box([shape], box, alignment="center")[0]
    assert placed["data"][2:] == [1.5, 0.5, 12.0, 0.2, 1]
    assert placed["color"] == [10, 20, 30, 255]
    assert placed["mask"] is True


def test_place_shapes_in_box_empty_input_returns_empty():
    box = PlacedBox(cx=0.0, cy=0.0, width=10.0, height=10.0)
    assert place_shapes_in_box([], box, alignment="center") == []


# ---------------------------------------------------------------------------
# scale_shapes_to_height
# ---------------------------------------------------------------------------

def test_scale_shapes_to_height_produces_exact_target_height():
    shapes = [_shape(cx=-20.0, cy=0.0, sx=0.2, sy=0.2), _shape(cx=20.0, cy=0.0, sx=0.2, sy=0.2)]
    scaled = scale_shapes_to_height(shapes, target_height=50.0)
    _, min_y, _, max_y = shapes_bbox(scaled)
    assert (max_y - min_y) == pytest.approx(50.0)


def test_scale_shapes_to_height_preserves_aspect_ratio():
    shapes = [_shape(cx=0.0, cy=0.0, sx=0.4, sy=0.2)]
    original = shapes_bbox(shapes)
    original_w, original_h = original[2] - original[0], original[3] - original[1]
    scaled = scale_shapes_to_height(shapes, target_height=original_h * 3)
    new = shapes_bbox(scaled)
    new_w, new_h = new[2] - new[0], new[3] - new[1]
    assert new_w / new_h == pytest.approx(original_w / original_h)


def test_scale_shapes_to_height_keeps_bbox_center_fixed():
    shapes = [_shape(cx=100.0, cy=-50.0, sx=0.2, sy=0.2)]
    scaled = scale_shapes_to_height(shapes, target_height=999.0)
    min_x, min_y, max_x, max_y = shapes_bbox(scaled)
    assert (min_x + max_x) / 2 == pytest.approx(100.0)
    assert (min_y + max_y) / 2 == pytest.approx(-50.0)


def test_scale_shapes_to_height_empty_or_degenerate_input_unchanged():
    assert scale_shapes_to_height([], target_height=10.0) == []
    degenerate = [_shape(cx=0.0, cy=0.0, sx=0.0, sy=0.0)]
    assert scale_shapes_to_height(degenerate, target_height=10.0) == degenerate


def test_place_shapes_in_box_multiple_shapes_keep_relative_spacing():
    shapes = [_shape(cx=0.0, cy=0.0, sx=0.1, sy=0.1), _shape(cx=100.0, cy=0.0, sx=0.1, sy=0.1)]
    box = PlacedBox(cx=0.0, cy=0.0, width=1000.0, height=1000.0)
    placed = place_shapes_in_box(shapes, box, alignment="left")
    assert placed[1]["data"][0] - placed[0]["data"][0] == pytest.approx(100.0)
