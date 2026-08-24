import colorsys

import pytest

from forza_writer.layout import PIXEL_ART_SQUARE_SIZE
from forza_writer.primitive_shapes import PRIMITIVE_CATALOG
from forza_writer.shapes import resource_to_shape_word, resource_to_typecode
from forza_writer.text_style import (
    MAX_ABS_SKEW, CharPosition, LineFill, TextStyle, apply_bold, apply_italic, build_bar_shape,
    color_for,
)

RED = (255, 0, 0, 255)
GREEN = (0, 255, 0, 255)
BLUE = (0, 0, 255, 255)
WHITE = (255, 255, 255, 255)


def _pos(index_in_line=0, chars_in_line=1) -> CharPosition:
    return CharPosition(index_in_line=index_in_line, chars_in_line=chars_in_line)


def test_line_fill_default_is_noop():
    assert LineFill().is_noop


def test_line_fill_rejects_unknown_mode():
    with pytest.raises(ValueError):
        LineFill(mode="plaid")


def test_line_fill_sequence_requires_at_least_one_color():
    with pytest.raises(ValueError):
        LineFill(mode="sequence", colors=())


def test_text_style_default_is_noop():
    assert TextStyle().is_noop


def test_text_style_is_noop_false_when_any_line_has_a_real_fill():
    style = TextStyle(fills=(LineFill(), LineFill(mode="solid", colors=(RED,))))
    assert not style.is_noop


def test_text_style_fill_for_line_with_no_fills_is_noop_for_any_index():
    style = TextStyle()
    assert style.fill_for_line(0).is_noop
    assert style.fill_for_line(99).is_noop


def test_text_style_fill_for_line_reuses_last_entry_past_end():
    solid_red = LineFill(mode="solid", colors=(RED,))
    style = TextStyle(fills=(LineFill(), solid_red))
    assert style.fill_for_line(0) == LineFill()
    assert style.fill_for_line(1) == solid_red
    assert style.fill_for_line(5) == solid_red  # defensive reuse, past the end


def test_color_for_solid_ignores_position():
    fill = LineFill(mode="solid", colors=(RED,))
    assert color_for(fill, _pos()) == RED
    assert color_for(fill, _pos(index_in_line=5, chars_in_line=10)) == RED


def test_color_for_sequence_blend_two_stops_endpoints_and_midpoint():
    fill = LineFill(mode="sequence", colors=(RED, BLUE), blend=True)
    first = color_for(fill, _pos(index_in_line=0, chars_in_line=3))
    last = color_for(fill, _pos(index_in_line=2, chars_in_line=3))
    mid = color_for(fill, _pos(index_in_line=1, chars_in_line=3))
    assert first == RED
    assert last == BLUE
    assert mid == (128, 0, 128, 255)


def test_color_for_sequence_blend_multi_stop_interpolates_each_segment():
    fill = LineFill(mode="sequence", colors=(RED, GREEN, BLUE), blend=True)
    # 5 chars over 3 stops: t values 0, .25, .5, .75, 1 -> segments [RED,GREEN] then [GREEN,BLUE]
    colors = [color_for(fill, _pos(i, 5)) for i in range(5)]
    assert colors[0] == RED
    assert colors[2] == GREEN  # exact midpoint stop
    assert colors[4] == BLUE


def test_color_for_sequence_step_cycles_and_wraps():
    fill = LineFill(mode="sequence", colors=(RED, GREEN, BLUE), blend=False)
    colors = [color_for(fill, _pos(i, 4)) for i in range(4)]
    assert colors == [RED, GREEN, BLUE, RED]  # wraps back to the first stop


def test_color_for_sequence_single_color_is_effectively_solid():
    fill = LineFill(mode="sequence", colors=(RED,), blend=True)
    assert color_for(fill, _pos(0, 5)) == RED
    assert color_for(fill, _pos(4, 5)) == RED
    fill_step = LineFill(mode="sequence", colors=(RED,), blend=False)
    assert color_for(fill_step, _pos(3, 5)) == RED


def test_color_for_sequence_single_char_line_does_not_divide_by_zero():
    fill = LineFill(mode="sequence", colors=(RED, BLUE), blend=True)
    assert color_for(fill, _pos(0, 1)) == RED


def test_color_for_rainbow_sweeps_hue_per_line():
    fill = LineFill(mode="rainbow")
    count = 6
    colors = [color_for(fill, _pos(i, count)) for i in range(count)]
    assert len(set(colors)) == count  # every step distinct
    for i, color in enumerate(colors):
        expected = colorsys.hsv_to_rgb(i / count, 1.0, 1.0)
        expected_rgba = tuple(round(c * 255) for c in expected) + (255,)
        assert color == expected_rgba


def test_color_for_rainbow_single_char_line_does_not_divide_by_zero():
    fill = LineFill(mode="rainbow")
    assert color_for(fill, _pos(0, 1)) == RED  # hue 0 -> pure red


def test_apply_bold_scales_non_mask_shape_around_its_own_center():
    shape = {"type": 1, "type_word": 1, "data": [10.0, 20.0, 2.0, 3.0, 0.0, 0.0, 0],
             "color": [255, 255, 255, 255], "mask": False}
    boldened = apply_bold(shape, factor=1.2)
    assert boldened["data"][0] == 10.0 and boldened["data"][1] == 20.0  # position untouched
    assert boldened["data"][2] == pytest.approx(2.4)
    assert boldened["data"][3] == pytest.approx(3.6)
    assert boldened["data"][4:] == shape["data"][4:]  # rotation/skew/mask flag untouched


def test_apply_bold_leaves_mask_shapes_unscaled():
    shape = {"type": 1, "type_word": 1, "data": [0.0, 0.0, 2.0, 2.0, 0.0, 0.0, 1],
             "color": [0, 0, 0, 255], "mask": True}
    assert apply_bold(shape, factor=1.5) == shape


def test_apply_italic_adds_skew():
    shape = {"type": 1, "type_word": 1, "data": [0.0, 0.0, 1.0, 1.0, 0.0, 0.1, 0],
             "color": [255, 255, 255, 255], "mask": False}
    italic = apply_italic(shape, skew_delta=0.25)
    assert italic["data"][5] == pytest.approx(0.35)
    # everything else untouched
    assert italic["data"][:5] == shape["data"][:5]


def test_apply_italic_clamps_to_max_abs_skew():
    shape = {"type": 1, "type_word": 1, "data": [0.0, 0.0, 1.0, 1.0, 0.0, 0.7, 0],
             "color": [255, 255, 255, 255], "mask": False}
    italic = apply_italic(shape, skew_delta=0.5)
    assert italic["data"][5] == pytest.approx(MAX_ABS_SKEW)


def test_apply_italic_pads_missing_data_fields():
    shape = {"type": 1, "type_word": 1, "data": [0.0, 0.0], "color": [255, 255, 255, 255], "mask": False}
    italic = apply_italic(shape, skew_delta=0.3)
    assert italic["data"][5] == pytest.approx(0.3)


def test_build_bar_shape_matches_square_primitive():
    shape = build_bar_shape(x_start=0.0, x_end=100.0, y_center=5.0, thickness=10.0,
                             color=(1, 2, 3, 255))
    square = PRIMITIVE_CATALOG["square"]
    assert shape["type"] == resource_to_typecode("Primitives", square.resource_index)
    assert shape["type_word"] == resource_to_shape_word("Primitives", square.resource_index)
    assert shape["color"] == [1, 2, 3, 255]
    assert shape["mask"] is False
    assert shape["data"][0] == pytest.approx(50.0)  # x center
    assert shape["data"][1] == pytest.approx(5.0)   # y center
    assert shape["data"][2] == pytest.approx(100.0 / PIXEL_ART_SQUARE_SIZE, abs=1e-5)
    assert shape["data"][3] == pytest.approx(10.0 / PIXEL_ART_SQUARE_SIZE, abs=1e-5)
