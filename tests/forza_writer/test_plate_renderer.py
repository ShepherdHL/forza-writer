"""Tests for forza_writer/plates/renderer.py: PlateTemplate + PlateInstance
-> (shapes, PlateGroupNode, warnings), including the blank-plate-library
fast path (background/border/decorations loaded from a cached pre-render
rather than rebuilt from Decoration data every time) and the per-character
placeholder-box group tree (see glyph_resolve.py's module docstring for
why fields no longer render real letterform geometry)."""

import dataclasses
from unittest.mock import patch

import pytest

from forza_writer.plates import blank_library, renderer
from forza_writer.plates.group import GroupKind
from forza_writer.plates.instance import DecorationOverride, FieldOverride, PlateInstance
from forza_writer.plates.renderer import estimate_shape_count, render_plate, render_plate_blank
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

LATIN = CharSource(font_file="LiberationSans-Regular.ttf")


def _template(field_char_source=LATIN, background=None, border=None, decorations=(), field_alignment="center"):
    return PlateTemplate(
        template_id="t", display_name_key="plates.template.t", country="US", jurisdiction=None,
        era="current", plate_type="passenger", width_mm=300.0, height_mm=150.0,
        accuracy_status=AccuracyStatus.FICTIONAL, provenance=Provenance(source_notes="test"),
        background=background or Decoration(decoration_id="bg", kind=DecorationKind.SOLID_FILL,
                                             x_mm=0.0, y_mm=0.0, color=(255, 255, 255, 255), editable=False),
        border=border,
        fields=(
            PlateField(
                field_id="registration", label_key="plates.field.registration", role=FieldRole.REGISTRATION,
                x_mm=20.0, y_mm=40.0, width_mm=260.0, height_mm=70.0, alignment=field_alignment,
                char_source=field_char_source, default_text="AB",
            ),
        ),
        decorations=decorations,
    )


@pytest.fixture(autouse=True)
def _isolate_blank_library(tmp_path, monkeypatch):
    """No test should see a real cached blank from data/plate_blanks/ (or
    leak one between tests) unless it explicitly builds one -- every test
    gets an empty, isolated blank-library directory by default."""
    monkeypatch.setattr(blank_library, "DEFAULT_BLANKS_DIR", tmp_path / "plate_blanks")


# ---------------------------------------------------------------------------
# Basic rendering: background + one field
# ---------------------------------------------------------------------------

def test_render_plate_produces_background_and_field_shapes():
    template = _template()
    instance = PlateInstance(template_id="t", mode="authentic", field_values={"registration": "AB"})

    shapes, root, warnings = render_plate(template, instance)
    assert warnings == []
    assert len(shapes) > 1  # background rect + at least one placeholder box

    assert root.kind == GroupKind.PLATE
    kinds = {child.kind for child in root.children}
    assert GroupKind.BACKGROUND in kinds
    assert GroupKind.FIELD in kinds


def test_render_plate_group_tree_flattens_to_every_shape_index_exactly_once():
    template = _template()
    instance = PlateInstance(template_id="t", mode="authentic", field_values={"registration": "AB"})

    shapes, root, _ = render_plate(template, instance)
    assert sorted(root.flatten()) == list(range(len(shapes)))


def test_render_plate_is_deterministic():
    template = _template()
    instance = PlateInstance(template_id="t", mode="authentic", field_values={"registration": "AB"})

    shapes1, _, _ = render_plate(template, instance)
    shapes2, _, _ = render_plate(template, instance)
    assert shapes1 == shapes2


# ---------------------------------------------------------------------------
# Border + background layering
# ---------------------------------------------------------------------------

def test_render_plate_with_border_creates_separate_border_node():
    border = Decoration(decoration_id="border", kind=DecorationKind.BORDER, x_mm=0.0, y_mm=0.0,
                         color=(0, 0, 0, 255))
    background = Decoration(decoration_id="bg", kind=DecorationKind.SOLID_FILL, x_mm=5.0, y_mm=5.0,
                             width_mm=290.0, height_mm=140.0, color=(255, 255, 255, 255), editable=False)
    template = _template(background=background, border=border)
    instance = PlateInstance(template_id="t", mode="authentic", field_values={"registration": "AB"})

    shapes, root, _ = render_plate(template, instance)
    # Border must be BELOW background in the shape list (drawn first, so a
    # smaller background on top leaves the border visible as a frame).
    bg_node = next(c for c in root.children if c.kind == GroupKind.BACKGROUND)
    border_node = next(c for c in root.children if c.kind == GroupKind.BORDER)
    assert min(border_node.shape_indices) < min(bg_node.shape_indices)


# ---------------------------------------------------------------------------
# Field text: default, override, vanity color
# ---------------------------------------------------------------------------

def test_render_plate_uses_default_text_when_no_field_value_given():
    template = _template()
    instance = PlateInstance(template_id="t", mode="authentic", field_values={})
    shapes, _, warnings = render_plate(template, instance)
    assert warnings == []
    assert len(shapes) > 1  # default_text="AB" still renders


def test_render_plate_authentic_field_color_is_applied():
    green_field = dataclasses.replace(_template().fields[0], color=(0, 128, 0, 255))
    template = dataclasses.replace(_template(), fields=(green_field,))
    instance = PlateInstance(template_id="t", mode="authentic", field_values={"registration": "AB"})

    shapes, root, _ = render_plate(template, instance)
    field_node = next(c for c in root.children if c.kind == GroupKind.FIELD)
    field_shapes = [shapes[i] for i in field_node.flatten()]
    assert all(s["color"] == [0, 128, 0, 255] for s in field_shapes if not s.get("mask"))


def test_render_plate_vanity_override_without_color_keeps_field_base_color():
    green_field = dataclasses.replace(_template().fields[0], color=(0, 128, 0, 255))
    template = dataclasses.replace(_template(), fields=(green_field,))
    # A vanity override that only changes tracking must not silently reset color.
    instance = PlateInstance(
        template_id="t", mode="vanity", field_values={"registration": "AB"},
        field_overrides={"registration": FieldOverride(tracking=5.0)},
    )
    shapes, root, _ = render_plate(template, instance)
    field_node = next(c for c in root.children if c.kind == GroupKind.FIELD)
    field_shapes = [shapes[i] for i in field_node.flatten()]
    assert all(s["color"] == [0, 128, 0, 255] for s in field_shapes if not s.get("mask"))


def test_render_plate_vanity_color_override_applies_to_field_shapes():
    template = _template()
    instance = PlateInstance(
        template_id="t", mode="vanity", field_values={"registration": "AB"},
        field_overrides={"registration": FieldOverride(color=(9, 8, 7, 255))},
    )
    shapes, root, _ = render_plate(template, instance)
    field_node = next(c for c in root.children if c.kind == GroupKind.FIELD)
    field_shapes = [shapes[i] for i in field_node.flatten()]
    assert all(s["color"] == [9, 8, 7, 255] for s in field_shapes if not s.get("mask"))


# ---------------------------------------------------------------------------
# Decoration overrides
# ---------------------------------------------------------------------------

def test_render_plate_decoration_override_hides_decoration():
    deco = Decoration(decoration_id="seal", kind=DecorationKind.SEAL, x_mm=10.0, y_mm=10.0,
                       width_mm=20.0, height_mm=20.0, color=(1, 2, 3, 255))
    template = _template(decorations=(deco,))
    instance_visible = PlateInstance(template_id="t", mode="vanity", field_values={"registration": "AB"})
    instance_hidden = PlateInstance(
        template_id="t", mode="vanity", field_values={"registration": "AB"},
        decoration_overrides={"seal": DecorationOverride(visible=False)},
    )

    _, root_visible, _ = render_plate(template, instance_visible)
    _, root_hidden, _ = render_plate(template, instance_hidden)
    assert any(c.kind == GroupKind.DECORATION for c in root_visible.children)
    assert not any(c.kind == GroupKind.DECORATION for c in root_hidden.children)


def test_render_plate_decoration_override_still_works_when_a_blank_is_cached():
    """A cached blank reflects the template's own defaults; an instance
    that overrides a decoration must still see that override applied, not
    silently fall back to the cached (unoverridden) version."""
    deco = Decoration(decoration_id="seal", kind=DecorationKind.SEAL, x_mm=10.0, y_mm=10.0,
                       width_mm=20.0, height_mm=20.0, color=(1, 2, 3, 255))
    template = _template(decorations=(deco,))

    blank_shapes, blank_nodes, blank_warnings = render_plate_blank(template)
    blank_library.save_blank(template, blank_shapes, blank_nodes, blank_warnings)

    instance = PlateInstance(
        template_id="t", mode="vanity", field_values={"registration": "AB"},
        decoration_overrides={"seal": DecorationOverride(color=(9, 9, 9, 255))},
    )
    shapes, root, _ = render_plate(template, instance)
    deco_node = next(c for c in root.children if c.kind == GroupKind.DECORATION)
    assert all(shapes[i]["color"] == [9, 9, 9, 255] for i in deco_node.shape_indices)


# ---------------------------------------------------------------------------
# Blank plate library
# ---------------------------------------------------------------------------

def test_render_plate_falls_back_to_on_the_fly_when_no_blank_is_cached():
    template = _template()
    instance = PlateInstance(template_id="t", mode="authentic", field_values={"registration": "AB"})

    with patch.object(renderer, "render_plate_blank", wraps=renderer.render_plate_blank) as spy:
        render_plate(template, instance)
    assert spy.call_count == 1  # no cached blank exists yet -- must render it on the fly


def test_render_plate_uses_cached_blank_without_recomputing_it():
    template = _template()
    blank_shapes, blank_nodes, blank_warnings = render_plate_blank(template)
    blank_library.save_blank(template, blank_shapes, blank_nodes, blank_warnings)

    instance = PlateInstance(template_id="t", mode="authentic", field_values={"registration": "AB"})
    with patch.object(renderer, "render_plate_blank", wraps=renderer.render_plate_blank) as spy:
        shapes, root, warnings = render_plate(template, instance)
    assert spy.call_count == 0  # the cached blank must be used instead
    assert warnings == []
    kinds = {child.kind for child in root.children}
    assert GroupKind.BACKGROUND in kinds and GroupKind.FIELD in kinds


def test_render_plate_blank_shapes_match_the_on_the_fly_render():
    """The cached-blank fast path and the on-the-fly fallback must agree on
    what the background/border actually look like -- not just both "work"."""
    border = Decoration(decoration_id="border", kind=DecorationKind.BORDER, x_mm=0.0, y_mm=0.0,
                         color=(0, 0, 0, 255))
    template = _template(border=border)
    instance = PlateInstance(template_id="t", mode="authentic", field_values={"registration": "AB"})

    on_the_fly_shapes, _, _ = render_plate(template, instance)

    blank_shapes, blank_nodes, blank_warnings = render_plate_blank(template)
    blank_library.save_blank(template, blank_shapes, blank_nodes, blank_warnings)
    cached_shapes, _, _ = render_plate(template, instance)

    assert on_the_fly_shapes == cached_shapes


def test_render_plate_blank_contains_no_field_geometry():
    template = _template(CharSource(font_file="unused.ttf"),
                         border=Decoration(decoration_id="border", kind=DecorationKind.BORDER,
                                            x_mm=0.0, y_mm=0.0, color=(0, 0, 0, 255)))
    shapes, nodes, _ = render_plate_blank(template)
    kinds = {node.kind for node in nodes}
    assert GroupKind.FIELD not in kinds
    assert GroupKind.BACKGROUND in kinds and GroupKind.BORDER in kinds


# ---------------------------------------------------------------------------
# Per-character placeholder boxes: one CHARACTER child per typed character,
# each independently addressable/replaceable in KFPS.
# ---------------------------------------------------------------------------

def test_render_plate_field_has_one_character_child_per_non_space_character():
    template = _template()
    instance = PlateInstance(template_id="t", mode="authentic", field_values={"registration": "A B"})
    _, root, _ = render_plate(template, instance)
    field_node = next(c for c in root.children if c.kind == GroupKind.FIELD)
    assert [c.kind for c in field_node.children] == [GroupKind.CHARACTER] * 2  # 'A' and 'B', space skipped
    assert field_node.shape_indices == ()  # the field's own shapes live on its CHARACTER children


def test_character_node_name_key_is_the_literal_character():
    template = _template()
    instance = PlateInstance(template_id="t", mode="authentic", field_values={"registration": "AB"})
    _, root, _ = render_plate(template, instance)
    field_node = next(c for c in root.children if c.kind == GroupKind.FIELD)
    assert [c.name_key for c in field_node.children] == ["A", "B"]


def test_character_nodes_are_positioned_left_to_right():
    template = _template(field_alignment="left")
    instance = PlateInstance(template_id="t", mode="authentic", field_values={"registration": "AB"})
    shapes, root, _ = render_plate(template, instance)
    field_node = next(c for c in root.children if c.kind == GroupKind.FIELD)
    a_shape = shapes[field_node.children[0].shape_indices[0]]
    b_shape = shapes[field_node.children[1].shape_indices[0]]
    assert a_shape["data"][0] < b_shape["data"][0]  # 'A' left of 'B'


# ---------------------------------------------------------------------------
# placeholder_font: threaded from PlateInstance down to glyph_resolve
# ---------------------------------------------------------------------------

def test_render_plate_threads_placeholder_font_to_field_shapes():
    template = _template()
    boxes_instance = PlateInstance(template_id="t", mode="authentic", field_values={"registration": "A"})
    forza_instance = PlateInstance(template_id="t", mode="authentic", field_values={"registration": "A"},
                                    placeholder_font=7)

    box_shapes, box_root, _ = render_plate(template, boxes_instance)
    forza_shapes, forza_root, _ = render_plate(template, forza_instance)

    box_field = next(c for c in box_root.children if c.kind == GroupKind.FIELD)
    forza_field = next(c for c in forza_root.children if c.kind == GroupKind.FIELD)
    box_char_shape = box_shapes[box_field.children[0].shape_indices[0]]
    forza_char_shape = forza_shapes[forza_field.children[0].shape_indices[0]]
    assert box_char_shape["type"] != forza_char_shape["type"]


# ---------------------------------------------------------------------------
# Overflow warning
# ---------------------------------------------------------------------------

def test_render_plate_warns_when_field_text_overflows_its_box():
    # A tiny box forces the composed text to be much wider than the box --
    # this must warn, not silently overflow or shrink.
    template = _template()
    field = template.fields[0]
    narrow_field = dataclasses.replace(field, width_mm=5.0, height_mm=60.0)
    template = dataclasses.replace(template, fields=(narrow_field,))
    instance = PlateInstance(template_id="t", mode="authentic", field_values={"registration": "AB"})

    _, _, warnings = render_plate(template, instance)
    assert any("overflow" in w for w in warnings)


def test_render_plate_does_not_warn_when_field_text_fits():
    template = _template()  # default field box is generously sized for "AB"
    instance = PlateInstance(template_id="t", mode="authentic", field_values={"registration": "AB"})
    _, _, warnings = render_plate(template, instance)
    assert not any("overflow" in w for w in warnings)


# ---------------------------------------------------------------------------
# estimate_shape_count
# ---------------------------------------------------------------------------

def test_estimate_shape_count_matches_actual_render():
    template = _template()
    instance = PlateInstance(template_id="t", mode="authentic", field_values={"registration": "AB"})
    shapes, _, _ = render_plate(template, instance)
    assert estimate_shape_count(template, instance) == len(shapes)
