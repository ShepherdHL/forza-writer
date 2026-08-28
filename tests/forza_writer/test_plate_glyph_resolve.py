"""Tests for forza_writer/plates/glyph_resolve.py: laying out a PlateField's
text as per-character placeholder boxes sized/spaced from a real font's
metrics (never its letterform geometry -- see the module's own docstring
for why), including the whole-swap fallback and load_symbol_asset (used by
decorations, not fields).

Uses the two fonts already bundled at assets/fonts/ (LiberationSans-Regular
for Latin, NotoSansCJKjp-Regular for CJK) -- metrics-only resolution needs
no special test font and no pre-generated fontpack, so every test here runs
unconditionally."""

import json

import pytest

from forza_writer.plates import glyph_resolve
from forza_writer.plates.layout_engine import shapes_bbox
from forza_writer.plates.template import CharSource

LATIN = CharSource(font_file="LiberationSans-Regular.ttf")
CJK = CharSource(font_file="NotoSansCJKjp-Regular.otf")


# ---------------------------------------------------------------------------
# Layout against a real font's metrics
# ---------------------------------------------------------------------------

def test_resolve_field_shapes_lays_out_one_shape_per_character():
    char_shapes, warnings = glyph_resolve.resolve_field_shapes("AB", LATIN)
    assert warnings == []
    assert [c for c, _ in char_shapes] == ["A", "B"]
    assert len(char_shapes) == 2


def test_resolve_field_shapes_skips_spaces_but_still_advances():
    with_space, _ = glyph_resolve.resolve_field_shapes("A B", LATIN)
    without_space, _ = glyph_resolve.resolve_field_shapes("AB", LATIN)
    assert [c for c, _ in with_space] == ["A", "B"]
    # The space still occupies room -- 'B' sits further right than it does
    # in "AB" with no space between.
    b_with_space = next(s for c, s in with_space if c == "B")["data"][0]
    b_without_space = next(s for c, s in without_space if c == "B")["data"][0]
    assert b_with_space > b_without_space


def test_resolve_field_shapes_missing_font_warns_without_crashing():
    source = CharSource(font_file="does-not-exist.ttf")
    char_shapes, warnings = glyph_resolve.resolve_field_shapes("AB", source)
    assert char_shapes == []
    assert "does-not-exist.ttf" in warnings[0]


def test_resolve_field_shapes_empty_text_returns_nothing():
    char_shapes, warnings = glyph_resolve.resolve_field_shapes("", LATIN)
    assert char_shapes == [] and warnings == []


def test_resolve_field_shapes_uncovered_character_warns_and_uses_fallback_width():
    # A CJK character isn't in LiberationSans's cmap.
    char_shapes, warnings = glyph_resolve.resolve_field_shapes("A品", LATIN)
    assert any("品" in w for w in warnings)
    assert [c for c, _ in char_shapes] == ["A", "品"]  # still placed, just with an estimated width


# ---------------------------------------------------------------------------
# Whole-swap fallback: primary font doesn't cover everything -> use fallback
# ---------------------------------------------------------------------------

def test_resolve_field_shapes_falls_back_when_primary_font_is_missing_characters():
    source = CharSource(font_file="LiberationSans-Regular.ttf", fallback=CJK)
    char_shapes, warnings = glyph_resolve.resolve_field_shapes("品川", source)  # not in Latin's cmap
    assert warnings == []  # the CJK fallback covers both characters
    assert [c for c, _ in char_shapes] == ["品", "川"]


def test_resolve_field_shapes_no_fallback_keeps_primarys_warnings():
    char_shapes, warnings = glyph_resolve.resolve_field_shapes("A品", LATIN)  # no fallback set
    assert any("品" in w for w in warnings)


# ---------------------------------------------------------------------------
# target_height rescaling
# ---------------------------------------------------------------------------

def test_resolve_field_shapes_respects_target_height():
    char_shapes, _ = glyph_resolve.resolve_field_shapes("A", LATIN, target_height=42.0)
    shapes = [s for _, s in char_shapes]
    bbox = shapes_bbox(shapes)
    assert (bbox[3] - bbox[1]) == pytest.approx(42.0)


def test_resolve_field_shapes_alignment_changes_position_not_count():
    left, _ = glyph_resolve.resolve_field_shapes("AB", LATIN, align="left")
    right, _ = glyph_resolve.resolve_field_shapes("AB", LATIN, align="right")
    assert len(left) == len(right) == 2
    a_left = next(s for c, s in left if c == "A")["data"][0]
    a_right = next(s for c, s in right if c == "A")["data"][0]
    assert a_left != a_right


# ---------------------------------------------------------------------------
# load_symbol_asset (used by renderer.py's Decoration handling, not fields)
# ---------------------------------------------------------------------------

def test_load_symbol_asset_returns_fixed_shapes(monkeypatch, tmp_path):
    monkeypatch.setattr(glyph_resolve, "PLATE_ASSETS_DIR", tmp_path)
    asset_shapes = [{"type": 1, "type_word": 1, "data": [0, 0, 1, 1, 0, 0, 0], "color": [1, 2, 3, 255]}]
    (tmp_path / "star.json").write_text(json.dumps({"shapes": asset_shapes}), encoding="utf-8")

    shapes, warnings = glyph_resolve.load_symbol_asset("star")
    assert warnings == []
    assert shapes == asset_shapes


def test_load_symbol_asset_missing_warns_without_crashing(monkeypatch, tmp_path):
    monkeypatch.setattr(glyph_resolve, "PLATE_ASSETS_DIR", tmp_path)
    shapes, warnings = glyph_resolve.load_symbol_asset("nonexistent")
    assert shapes == []
    assert "nonexistent" in warnings[0]


# ---------------------------------------------------------------------------
# placeholder_font: real Forza in-game letterforms instead of plain boxes
# ---------------------------------------------------------------------------

def test_placeholder_font_produces_different_shapes_than_plain_boxes():
    boxes, box_warnings = glyph_resolve.resolve_field_shapes("AB", LATIN)
    forza, forza_warnings = glyph_resolve.resolve_field_shapes("AB", LATIN, placeholder_font=7)
    assert box_warnings == forza_warnings == []
    assert [c for c, _ in boxes] == [c for c, _ in forza] == ["A", "B"]
    # Different resource -- a real letterform, not the "Square" primitive
    # every plain placeholder box uses.
    for (_, box_shape), (_, forza_shape) in zip(boxes, forza):
        assert box_shape["type"] != forza_shape["type"]


def test_placeholder_font_falls_back_to_a_box_for_an_uncovered_character():
    # Forza's 11 fonts cover letters/digits/limited punctuation, not a
    # barcode-style '|' run -- this must still produce a shape (a box),
    # with a warning naming the gap, not silently drop the character.
    char_shapes, warnings = glyph_resolve.resolve_field_shapes("A|B", LATIN, placeholder_font=7)
    assert [c for c, _ in char_shapes] == ["A", "|", "B"]
    assert any("'|'" in w and "Forza Font 7" in w for w in warnings)


def test_placeholder_font_none_is_the_default_and_keeps_plain_boxes():
    default, _ = glyph_resolve.resolve_field_shapes("A", LATIN)
    explicit_none, _ = glyph_resolve.resolve_field_shapes("A", LATIN, placeholder_font=None)
    assert default[0][1] == explicit_none[0][1]


def test_placeholder_font_respects_target_height():
    char_shapes, _ = glyph_resolve.resolve_field_shapes("A", LATIN, placeholder_font=7, target_height=42.0)
    shapes = [s for _, s in char_shapes]
    bbox = shapes_bbox(shapes)
    assert (bbox[3] - bbox[1]) == pytest.approx(42.0)
