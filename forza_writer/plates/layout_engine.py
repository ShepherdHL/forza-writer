"""Pure geometry: converts a `PlateField`/`Decoration`'s mm-space box into a
plate-local shape-coordinate box, and places an already-composed shape list
(from `glyph_resolve.py`, Phase 4) inside that box per the field's alignment.
No font I/O, no glyph resolution -- everything here is testable with plain
shape dicts.

**Unit convention**: 1mm of template space equals 1 shape unit (`MM_TO_UNIT`
below). This is a deliberate simplification, not an oversight: spec section
20 explicitly wants scale-invariant templates ("avoid pixel-based
assumptions... users should be able to scale the complete finished plate
without destroying relative spacing"), and every generator in this codebase
already expects its output to be freely rescaled by the user once imported
into Forza's own decal editor. Since the *ratio* between elements is what
must stay correct, not any absolute real-world size, using mm directly keeps
the mapping transparent and trivially checkable (a 520mm-wide UK plate
template literally spans x in [-260, 260]).

**Origin convention**: templates are authored with a top-left origin (x_mm=0,
y_mm=0 is the plate's top-left corner, both growing right/down), matching how
a template author naturally thinks about a physical plate's layout. This
module re-centers that into the origin-at-plate-center, y-down convention
`forza_writer.text_compose`'s own composition already produces (confirmed
directly from `_place_lines`: increasing `line_index` adds a positive
`line_offset` straight into `data[1]`, i.e. later/lower lines get larger
`data[1]` -- text_compose's shape space is downward-positive). Re-centering
at plate-center rather than keeping a top-left shape origin matches how a
single glyph is conventionally centered around (0, 0) elsewhere in this
codebase (e.g. `tools/gen_modelbin.py::normalize_to_128`).

**Bounding-box measurement**: `shape_bbox` reads only `data[0..3]` (center
x/y, scale x/y) and `forza_writer.layout.PIXEL_ART_SQUARE_SIZE`, the
documented "scale=1.0 is this many editor units" constant every shape in
this codebase's format already uses (see `primitive_fit.py::placements_to_shapes`'s
own docstring). This works uniformly across every `CharSource` kind (fitted
primitives, outline meshes, hand-traced shapes) without needing kind-specific
geometry knowledge, at the cost of ignoring `rotation_deg` for the bbox
itself -- an acceptable approximation since composed text is never rotated
by this pipeline, and a rotated decoration being centered by its unrotated
bbox is a minor cosmetic nudge a user can correct via a position override,
not a correctness bug.
"""

from __future__ import annotations

from dataclasses import dataclass

from forza_writer.layout import PIXEL_ART_SQUARE_SIZE
from forza_writer.plates.template import Decoration, PlateField, PlateTemplate

MM_TO_UNIT = 1.0


def mm_to_units(mm: float) -> float:
    return mm * MM_TO_UNIT


@dataclass(frozen=True)
class PlacedBox:
    """A box in plate-local shape-coordinate space, center-based (matching
    every shape dict's own `data[0]`/`data[1]` center convention) rather than
    top-left-based."""

    cx: float
    cy: float
    width: float
    height: float

    @property
    def left(self) -> float:
        return self.cx - self.width / 2

    @property
    def right(self) -> float:
        return self.cx + self.width / 2

    @property
    def top(self) -> float:
        return self.cy - self.height / 2

    @property
    def bottom(self) -> float:
        return self.cy + self.height / 2


def plate_field_box(template: PlateTemplate, plate_field: PlateField) -> PlacedBox:
    """`plate_field`'s box, re-centered from the template's top-left-origin
    mm space into plate-centered shape units."""
    half_w = mm_to_units(template.width_mm) / 2
    half_h = mm_to_units(template.height_mm) / 2
    cx = mm_to_units(plate_field.x_mm + plate_field.width_mm / 2) - half_w
    cy = mm_to_units(plate_field.y_mm + plate_field.height_mm / 2) - half_h
    return PlacedBox(
        cx=cx, cy=cy,
        width=mm_to_units(plate_field.width_mm), height=mm_to_units(plate_field.height_mm),
    )


def plate_decoration_box(template: PlateTemplate, decoration: Decoration) -> PlacedBox:
    """`decoration`'s box. `width_mm`/`height_mm` of `None` means full-bleed
    on that axis (spans the whole plate, centered -- `x_mm`/`y_mm` on that
    axis are meaningless for a full bleed and are ignored, per
    `Decoration`'s own docstring)."""
    if decoration.width_mm is None:
        cx, width = 0.0, mm_to_units(template.width_mm)
    else:
        width = mm_to_units(decoration.width_mm)
        cx = mm_to_units(decoration.x_mm + decoration.width_mm / 2) - mm_to_units(template.width_mm) / 2
    if decoration.height_mm is None:
        cy, height = 0.0, mm_to_units(template.height_mm)
    else:
        height = mm_to_units(decoration.height_mm)
        cy = mm_to_units(decoration.y_mm + decoration.height_mm / 2) - mm_to_units(template.height_mm) / 2
    return PlacedBox(cx=cx, cy=cy, width=width, height=height)


def shape_bbox(shape: dict) -> tuple[float, float, float, float]:
    """(min_x, min_y, max_x, max_y) for one shape dict. See module docstring
    for why this ignores rotation."""
    data = shape["data"]
    cx, cy, scale_x, scale_y = data[0], data[1], data[2], data[3]
    half_w = abs(scale_x) * PIXEL_ART_SQUARE_SIZE / 2
    half_h = abs(scale_y) * PIXEL_ART_SQUARE_SIZE / 2
    return cx - half_w, cy - half_h, cx + half_w, cy + half_h


def shapes_bbox(shapes: list[dict]) -> tuple[float, float, float, float] | None:
    """Union bbox of every shape, or `None` for an empty list (e.g. a field
    whose text resolved to nothing, or a plate with zero decorations)."""
    if not shapes:
        return None
    boxes = [shape_bbox(s) for s in shapes]
    return (
        min(b[0] for b in boxes), min(b[1] for b in boxes),
        max(b[2] for b in boxes), max(b[3] for b in boxes),
    )


def scale_shapes_to_height(shapes: list[dict], target_height: float) -> list[dict]:
    """Uniformly rescales `shapes` (both position, around their own combined
    bbox center, and size) so their bbox height becomes `target_height`.
    Both axes scale by the same factor -- this is a zoom, not a stretch, so
    a glyph's proportions survive regardless of which `CharSource` kind
    produced it (fitted primitives, outline meshes, hand-traced shapes all
    carry size the same way: `data[2]`/`data[3]`, per
    `forza_writer.layout.PIXEL_ART_SQUARE_SIZE`'s convention).

    Returns `shapes` unchanged if their current bbox height is zero (a
    single-point/degenerate shape, or an empty list) -- scaling by an
    undefined factor would be worse than leaving it alone."""
    bbox = shapes_bbox(shapes)
    if bbox is None:
        return shapes
    min_x, min_y, max_x, max_y = bbox
    current_height = max_y - min_y
    if current_height <= 0:
        return shapes
    factor = target_height / current_height
    anchor_x, anchor_y = (min_x + max_x) / 2, (min_y + max_y) / 2
    return [
        {**shape, "data": [
            anchor_x + (shape["data"][0] - anchor_x) * factor,
            anchor_y + (shape["data"][1] - anchor_y) * factor,
            shape["data"][2] * factor, shape["data"][3] * factor,
            *shape["data"][4:],
        ]}
        for shape in shapes
    ]


def center_shapes_on_origin(shapes: list[dict]) -> list[dict]:
    """Recenters `shapes` so their combined bbox center sits at (0, 0),
    without changing size. Used by `glyph_resolve.py` to bring a
    single-character result from a whole-string composer (which places its
    output starting near x=0 extending rightward, not bbox-centered) into
    the same "centered at its own local origin" convention hand-traced
    glyphs already have, so both can be laid out left-to-right the same
    way."""
    bbox = shapes_bbox(shapes)
    if bbox is None:
        return shapes
    min_x, min_y, max_x, max_y = bbox
    cx, cy = (min_x + max_x) / 2, (min_y + max_y) / 2
    if cx == 0.0 and cy == 0.0:
        return shapes
    return [
        {**shape, "data": [shape["data"][0] - cx, shape["data"][1] - cy, *shape["data"][2:]]}
        for shape in shapes
    ]


def place_shapes_in_box(shapes: list[dict], box: PlacedBox, alignment: str = "center") -> list[dict]:
    """Translates `shapes` (already internally composed/aligned by
    `glyph_resolve.py`, e.g. `text_compose.compose_text`'s output) so their
    combined bounding box sits inside `box`: horizontally per `alignment`
    (`"left"`/`"right"` flush a content edge to the matching box edge;
    `"center"` and `"justify"` both center horizontally -- box-level
    "justify" has no distinct meaning once a block is already composed, so
    it's treated as center rather than silently misbehaving), always
    vertically centered (the schema has no per-field vertical-alignment
    concept; every plate field is short, single-block text or a symbol, not
    a paragraph that would need top/bottom anchoring).

    Only `data[0]`/`data[1]` are touched, preserving scale/rotation/skew/
    mask/color exactly -- same "translate in place" contract
    `text_compose._place_lines` already uses.
    """
    bbox = shapes_bbox(shapes)
    if bbox is None:
        return []
    min_x, min_y, max_x, max_y = bbox
    content_w = max_x - min_x
    content_h = max_y - min_y

    if alignment == "left":
        dx = box.left - min_x
    elif alignment == "right":
        dx = box.right - max_x
    else:
        dx = box.cx - (min_x + content_w / 2)
    dy = box.cy - (min_y + content_h / 2)

    return [
        {**shape, "data": [shape["data"][0] + dx, shape["data"][1] + dy, *shape["data"][2:]]}
        for shape in shapes
    ]
