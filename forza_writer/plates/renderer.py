"""Turns a `PlateTemplate` + `PlateInstance` into ordinary Forza Writer
shapes (the same flat `list[dict]` format `forza_writer.export.to_json`
already understands) plus a `PlateGroupNode` tree describing the plate's
structure, so a generated plate is never locked behind a plate-specific
format -- see `group.py`'s module docstring.

**Border/background layering**: `Decoration` has no "stroke width" concept,
so a visible border is produced the same way any vector tool without a
distinct outline primitive would: draw the border decoration's own box
first (bottom), then the background's own box on top, sized smaller by
however much frame the template author wants visible. This is deliberate,
not a missing feature -- it keeps the renderer generic (no jurisdiction- or
border-specific geometry logic) by pushing the actual framing dimensions
into template data, per this feature's core extensibility principle.

**Blank plate library**: background/border/decorations never depend on
user input (only fields do), so rebuilding them from `Decoration` data on
every single render is repeated work for a result that's identical every
time. `render_plate` loads a pre-rendered blank (background + border +
decorations, built once by `tools/gen_plate_blanks.py`) via
`blank_library.load_blank` when one exists and the instance doesn't
override any decoration; `render_plate_blank` (the on-the-fly path,
what the library-building script itself calls) is the fallback for a
template with no cached blank yet, or an instance that actually overrides
a decoration's color/position/visibility -- the cached blank only reflects
a template's own defaults, not any one instance's overrides.
"""

from __future__ import annotations

import dataclasses

from forza_writer.layout import PIXEL_ART_SQUARE_SIZE
from forza_writer.plates import blank_library
from forza_writer.plates.glyph_resolve import load_symbol_asset, resolve_field_shapes
from forza_writer.plates.group import GroupKind, PlateGroupNode
from forza_writer.plates.instance import PlateInstance
from forza_writer.plates.layout_engine import (
    PlacedBox,
    place_shapes_in_box,
    plate_decoration_box,
    plate_field_box,
    shapes_bbox,
)
from forza_writer.plates.template import Decoration, PlateField, PlateTemplate
from forza_writer.primitive_shapes import PRIMITIVE_CATALOG
from forza_writer.shapes import resource_to_shape_word, resource_to_typecode

# A rough per-plate shape budget for the "before you generate" estimate
# (spec's warn-before-generating requirement) -- not the fitted glyph
# pipeline's own per-glyph DEFAULT_MAX_LAYERS (forza_writer.generation_policy),
# which bounds a single glyph's *fit search*, not a whole plate's total.
# Measured, not guessed: with per-character placeholder boxes (one shape
# per character, not a traced letterform's many -- see glyph_resolve.py's
# module docstring) all 17 shipped templates range from 9 to 62 shapes each.
# A much lower ceiling than this feature's earlier pixel-traced-glyph design
# had (which ranged 394-2263) is exactly the point: an in-game decal plate
# should be cheap. Set with real headroom above the highest measured case
# rather than exactly at it, so an unusually long registration string still
# doesn't warn.
PLATE_SHAPE_WARN_THRESHOLD = 150


def _solid_rect_shape(box: PlacedBox, color: tuple[int, int, int, int]) -> dict:
    """One "Square" primitive filling `box`, matching
    `forza_writer.text_style.build_bar_shape`'s exact construction (same
    primitive lookup, same `scale = size / PIXEL_ART_SQUARE_SIZE`
    convention) -- used for a plain-color background/border/fill
    decoration with no `asset_ref`."""
    square = PRIMITIVE_CATALOG["square"]
    return {
        "type": resource_to_typecode("Primitives", square.resource_index),
        "type_word": resource_to_shape_word("Primitives", square.resource_index),
        "data": [
            round(box.cx, 6), round(box.cy, 6),
            round(box.width / PIXEL_ART_SQUARE_SIZE, 6), round(box.height / PIXEL_ART_SQUARE_SIZE, 6),
            0.0, 0.0, 0,
        ],
        "color": list(color),
        "mask": False,
    }


def _effective_decoration(decoration: Decoration, override) -> tuple[Decoration, bool]:
    """`decoration` with a Vanity-mode `DecorationOverride` applied, and
    whether it's visible (`override.visible=False` is spec's "decorative
    components deletable" expressed on an instance rather than mutating the
    template)."""
    if override is None:
        return decoration, True
    updates = {}
    if override.color is not None:
        updates["color"] = override.color
    if override.x_mm is not None:
        updates["x_mm"] = override.x_mm
    if override.y_mm is not None:
        updates["y_mm"] = override.y_mm
    effective = dataclasses.replace(decoration, **updates) if updates else decoration
    return effective, override.visible


def _render_decoration(decoration: Decoration, template: PlateTemplate,
                        override, warnings: list[str]) -> list[dict]:
    effective, visible = _effective_decoration(decoration, override)
    if not visible:
        return []
    box = plate_decoration_box(template, effective)
    if effective.asset_ref is not None:
        asset_shapes, asset_warnings = load_symbol_asset(effective.asset_ref)
        warnings.extend(asset_warnings)
        if not asset_shapes:
            return []
        placed = place_shapes_in_box(asset_shapes, box, alignment="center")
        if effective.color is not None:
            placed = [{**s, "color": list(effective.color)} if not s.get("mask") else s for s in placed]
        return placed
    if effective.color is None:
        warnings.append(
            f"decoration {decoration.decoration_id!r} has no asset_ref and no color -- nothing to render"
        )
        return []
    return [_solid_rect_shape(box, effective.color)]


def _effective_field_text_and_style(field: PlateField, instance: PlateInstance):
    text = instance.field_values.get(field.field_id, field.default_text)
    override = instance.field_overrides.get(field.field_id)
    char_source = field.char_source
    alignment = field.alignment
    tracking = field.tracking
    char_scale = field.char_scale
    x_mm, y_mm = field.x_mm, field.y_mm
    color = field.color
    if override is not None:
        char_source = override.char_source or char_source
        alignment = override.alignment or alignment
        tracking = override.tracking if override.tracking is not None else tracking
        char_scale = override.char_scale if override.char_scale is not None else char_scale
        x_mm = override.x_mm if override.x_mm is not None else x_mm
        y_mm = override.y_mm if override.y_mm is not None else y_mm
        color = override.color if override.color is not None else color
    return text, char_source, alignment, tracking, char_scale, x_mm, y_mm, color


def _render_field(field: PlateField, template: PlateTemplate, instance: PlateInstance,
                   warnings: list[str]) -> list[tuple[str, dict]]:
    """Returns one `(char, shape)` pair per non-space character in reading
    order -- each `shape` is a plain placeholder box, or (when
    `instance.placeholder_font` is set) a real Forza in-game font
    letterform -- see `glyph_resolve.py`'s module docstring. The caller
    (`render_plate`) gives each pair its own `PlateGroupNode` so a
    character is individually addressable/replaceable in KFPS."""
    text, char_source, alignment, tracking, char_scale, x_mm, y_mm, color = (
        _effective_field_text_and_style(field, instance))
    if not text:
        return []

    effective_field = dataclasses.replace(field, x_mm=x_mm, y_mm=y_mm)
    box = plate_field_box(template, effective_field)
    target_height = box.height * char_scale

    char_shapes, field_warnings = resolve_field_shapes(
        text, char_source, align=alignment, tracking=tracking,
        line_spacing=field.line_spacing, target_height=target_height,
        placeholder_font=instance.placeholder_font,
    )
    warnings.extend(field_warnings)
    if color is not None:
        char_shapes = [(c, {**s, "color": list(color)} if not s.get("mask") else s)
                        for c, s in char_shapes]

    shapes = [s for _, s in char_shapes]
    content_bbox = shapes_bbox(shapes)
    if content_bbox is not None:
        content_width = content_bbox[2] - content_bbox[0]
        if content_width > box.width * 1.001:  # small epsilon: float rounding, not a real overflow
            warnings.append(
                f"field {field.field_id!r} text {text!r} is {content_width:.1f} units wide but its "
                f"box is only {box.width:.1f} units -- it will overflow the field's box. Text is never "
                f"auto-shrunk to fit; use a smaller char_scale, shorter text, or a wider field."
            )

    placed = place_shapes_in_box(shapes, box, alignment)
    return [(c, s) for (c, _), s in zip(char_shapes, placed)]


def estimate_shape_count(template: PlateTemplate, instance: PlateInstance) -> int:
    """A cheap upper-bound estimate of the final shape count, for the "~N
    shapes" preview label (spec's warn-before-generating requirement) --
    actually renders every field (reusing already-cached glyph geometry, no
    new fitting), just doesn't build the group tree or apply color/decoration
    overrides beyond what counting needs. Safe to call on every keystroke
    the same way the lightweight preview path is."""
    shapes, _, _ = render_plate(template, instance)
    return len(shapes)


def render_plate_blank(template: PlateTemplate) -> tuple[list[dict], list[PlateGroupNode], list[str]]:
    """Background + border + every top-level decoration, using the
    template's own defaults (no instance, no overrides) -- the on-the-fly
    path `tools/gen_plate_blanks.py` calls to build the cached library, and
    `render_plate`'s own fallback when no cached blank exists yet or an
    instance overrides a decoration. Returns top-level nodes, not a PLATE
    root -- `render_plate` owns wrapping those into the final tree."""
    warnings: list[str] = []
    shapes: list[dict] = []
    nodes: list[PlateGroupNode] = []

    # Border drawn first (bottom of the paint order) so a smaller background
    # drawn on top of it leaves the border's edges visible as a frame -- see
    # module docstring. Reversing this order would let the background (often
    # full-bleed) completely cover the border instead.
    if template.border is not None:
        border_shapes = _render_decoration(template.border, template, None, warnings)
        if border_shapes:
            start = len(shapes)
            shapes.extend(border_shapes)
            nodes.append(PlateGroupNode(
                node_id=template.border.decoration_id, kind=GroupKind.BORDER,
                shape_indices=tuple(range(start, len(shapes))), editable=template.border.editable,
            ))

    bg_shapes = _render_decoration(template.background, template, None, warnings)
    if bg_shapes:
        start = len(shapes)
        shapes.extend(bg_shapes)
        nodes.append(PlateGroupNode(
            node_id=template.background.decoration_id, kind=GroupKind.BACKGROUND,
            shape_indices=tuple(range(start, len(shapes))), editable=template.background.editable,
        ))

    for decoration in template.decorations:
        deco_shapes = _render_decoration(decoration, template, None, warnings)
        if not deco_shapes:
            continue
        start = len(shapes)
        shapes.extend(deco_shapes)
        nodes.append(PlateGroupNode(
            node_id=decoration.decoration_id, kind=GroupKind.DECORATION,
            shape_indices=tuple(range(start, len(shapes))), editable=decoration.editable,
        ))

    return shapes, nodes, warnings


def render_plate(template: PlateTemplate, instance: PlateInstance
                  ) -> tuple[list[dict], PlateGroupNode, list[str]]:
    """The renderer's one entry point. Background/border/decorations come
    from the pre-rendered blank library when available (see module
    docstring); fields are always composed fresh (they're the one part
    that depends on what the user actually typed). Matches spec's suggested
    hierarchy: License Plate -> Background, Border, <fields>, Decorations.
    """
    warnings: list[str] = []

    blank = None if instance.decoration_overrides else blank_library.load_blank(template)
    if blank is not None:
        shapes, children, blank_warnings = list(blank[0]), list(blank[1]), list(blank[2])
        warnings.extend(blank_warnings)
    else:
        shapes, children, blank_warnings = render_plate_blank(template)
        warnings.extend(blank_warnings)
        # Vanity-mode decoration overrides need the live path even when a
        # cached blank exists for the template's own defaults -- re-render
        # just the overridden decorations on top of what's already there.
        if instance.decoration_overrides:
            for decoration in template.decorations:
                override = instance.decoration_overrides.get(decoration.decoration_id)
                if override is None:
                    continue
                deco_shapes = _render_decoration(decoration, template, override, warnings)
                # Replace that decoration's node/shapes rather than appending
                # a duplicate -- find_and_replace by node_id.
                existing = next((n for n in children if n.node_id == decoration.decoration_id), None)
                if existing is not None:
                    children.remove(existing)
                if deco_shapes:
                    start = len(shapes)
                    shapes.extend(deco_shapes)
                    children.append(PlateGroupNode(
                        node_id=decoration.decoration_id, kind=GroupKind.DECORATION,
                        shape_indices=tuple(range(start, len(shapes))), editable=decoration.editable,
                    ))

    for field in template.fields:
        char_shapes = _render_field(field, template, instance, warnings)
        if not char_shapes:
            continue
        char_nodes = []
        for char_index, (char, shape) in enumerate(char_shapes):
            idx = len(shapes)
            shapes.append(shape)
            char_nodes.append(PlateGroupNode(
                node_id=f"{field.field_id}_c{char_index}", kind=GroupKind.CHARACTER,
                name_key=char, shape_indices=(idx,),
            ))
        # The field node itself carries no shape_indices of its own -- its
        # shapes belong to its CHARACTER children (PlateGroupNode.flatten()
        # must return each shape index exactly once, not once per ancestor).
        children.append(PlateGroupNode(
            node_id=field.field_id, kind=GroupKind.FIELD, name_key=field.label_key,
            children=char_nodes,
        ))

    root = PlateGroupNode(
        node_id=template.template_id, kind=GroupKind.PLATE,
        name_key=template.display_name_key, children=children,
    )
    return shapes, root, warnings
