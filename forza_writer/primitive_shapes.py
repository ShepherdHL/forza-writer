"""Catalog of FH6's built-in solid-fill "Primitives" shapes usable as
building blocks for the primitive-composition glyph fitter.

Each entry maps a shape id to its (family, index) in `forza_writer.shapes`'s
`VINYL_TYPE_BASES` table and to a canonical, unrotated, unit-square-bounded
filled silhouette mask (a boolean numpy array), generated once via Pillow and
cached. `forza_writer.primitive_fit` samples/transforms these masks during
its greedy search; it never talks to Pillow or index numbers directly.

Source of truth for names/indices: the in-game "Primitives" shape picker
itself, as captured in `FH6 - Vinyl Shape Codes.xlsx` (sheet "Visual
Reference", Page 1 screenshot + sheet "Google Sheets Reference" naming its
40 slots by row/column). The picker is a 4-row x 10-column grid filled
*column-major*, so `resource_index = (column - 1) * 4 + row`.

KFPS's `tools/fabric-editor/shape-names.json` ("Primitives", 40 slots) was
the previous reference here and agrees on 36 of 40 slots, but it is a
partly hand-authored list and is wrong where it guessed: it leaves slots 6
and 26 as "Primitive slot N" placeholders, and it duplicates two names onto
the slots either side of those gaps -- "Rounded Square" at both 7 and 22,
"Quarter Circle" at both 27 and 30. The screenshot shows 7 is a *Cut
Square* (chamfered corners) and 27 is an *Animal Tooth* (claw crescent);
the real Rounded Square and Quarter Circle are 22 and 30. Both were
corrected here; prefer the spreadsheet over shape-names.json on any future
disagreement, and see `tests/forza_writer/test_primitive_shapes.py` for the
pinned mapping. This module covers the subset that's
simple, solid-filled, and cheaply reproducible with `ImageDraw`/regular-
polygon math. That includes two ring/border shapes (Circle Border, Square
Border) deliberately kept in rather than excluded: a ring is its own
legitimate filled silhouette, not merely an outline of another shape, and
turns out to matter a lot for hole-bearing letterforms (O, the counter of
A/D/etc.) that solid disks/squares alone approximate poorly. Genuinely
irregular/hole-in-a-non-ring-shape primitives (Circle Cutout, Quarter Donut,
Crescent, Banana Crescent, Quarter Outside Circle, Triangle Swoosh) are still
excluded rather than guessed at with an approximate silhouette; adding them
later needs real reference geometry, not a blind approximation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw

MASK_RESOLUTION = 128  # working resolution for all cached silhouette masks


@dataclass(frozen=True)
class PrimitiveShape:
    shape_id: str
    resource_index: int
    display_name: str
    mask: np.ndarray  # bool, (MASK_RESOLUTION, MASK_RESOLUTION), True = filled
    rotationally_symmetric: bool = False  # skip rotation search if True (e.g. Circle)


def _new_canvas() -> Image.Image:
    return Image.new("L", (MASK_RESOLUTION, MASK_RESOLUTION), 0)


def _to_mask(img: Image.Image) -> np.ndarray:
    return np.array(img, dtype=bool)


def _regular_polygon(n: int, rotation_deg: float = -90.0, radius_ratio: float = 0.5) -> list[tuple[float, float]]:
    """Vertices of a regular n-gon centered in the canvas, point 0 at
    `rotation_deg` (default -90 = pointing up)."""
    c = MASK_RESOLUTION / 2.0
    r = MASK_RESOLUTION * radius_ratio
    pts = []
    for i in range(n):
        angle = math.radians(rotation_deg) + i * 2 * math.pi / n
        pts.append((c + r * math.cos(angle), c + r * math.sin(angle)))
    return pts


def _star(points: int, rotation_deg: float = -90.0,
          outer_ratio: float = 0.5, inner_ratio: float = 0.22) -> list[tuple[float, float]]:
    """Vertices of a `points`-pointed star, alternating outer/inner radius."""
    c = MASK_RESOLUTION / 2.0
    outer_r = MASK_RESOLUTION * outer_ratio
    inner_r = MASK_RESOLUTION * inner_ratio
    pts = []
    for i in range(points * 2):
        angle = math.radians(rotation_deg) + i * math.pi / points
        r = outer_r if i % 2 == 0 else inner_r
        pts.append((c + r * math.cos(angle), c + r * math.sin(angle)))
    return pts


def _square_mask() -> np.ndarray:
    """Full-bleed, deliberately with no inset margin. FH6's Square primitive
    fills its bounding box exactly, and the rectangle-decomposition path
    (forza_writer.rect_decompose) relies on that being true here: a rect of
    width w placed at scale w/resolution has to land on exactly those pixels,
    or an "exact" cover silently gains a gap on every edge."""
    img = _new_canvas()
    ImageDraw.Draw(img).rectangle([0, 0, MASK_RESOLUTION, MASK_RESOLUTION], fill=255)
    return _to_mask(img)


def _rounded_square_mask() -> np.ndarray:
    img = _new_canvas()
    m = MASK_RESOLUTION * 0.02
    radius = MASK_RESOLUTION * 0.22
    ImageDraw.Draw(img).rounded_rectangle([m, m, MASK_RESOLUTION - m, MASK_RESOLUTION - m],
                                           radius=radius, fill=255)
    return _to_mask(img)


def _tapered_rectangle_mask() -> np.ndarray:
    """A rectangle narrower at the top than the bottom (simple trapezoid)."""
    img = _new_canvas()
    top_m = MASK_RESOLUTION * 0.22
    bot_m = MASK_RESOLUTION * 0.06
    y0, y1 = MASK_RESOLUTION * 0.02, MASK_RESOLUTION * 0.92
    ImageDraw.Draw(img).polygon(
        [(top_m, y0), (MASK_RESOLUTION - top_m, y0),
         (MASK_RESOLUTION - bot_m, y1), (bot_m, y1)], fill=255)
    return _to_mask(img)


def _circle_mask() -> np.ndarray:
    img = _new_canvas()
    m = MASK_RESOLUTION * 0.06
    ImageDraw.Draw(img).ellipse([m, m, MASK_RESOLUTION - m, MASK_RESOLUTION - m], fill=255)
    return _to_mask(img)


def _half_circle_mask() -> np.ndarray:
    img = _new_canvas()
    m = MASK_RESOLUTION * 0.06
    ImageDraw.Draw(img).pieslice([m, m, MASK_RESOLUTION - m, (MASK_RESOLUTION - m) * 2 - MASK_RESOLUTION / 2],
                                  start=180, end=360, fill=255)
    return _to_mask(img)


def _quarter_circle_mask() -> np.ndarray:
    img = _new_canvas()
    r = MASK_RESOLUTION - MASK_RESOLUTION * 0.06
    ImageDraw.Draw(img).pieslice([-MASK_RESOLUTION * 0.06, -MASK_RESOLUTION * 0.06, r, r],
                                  start=0, end=90, fill=255)
    return _to_mask(img)


def _circle_border_mask(thickness_ratio: float = 0.28) -> np.ndarray:
    """A ring (annulus) — its own legitimate solid silhouette, not merely an
    outline of the filled Circle. Valuable for hole-bearing letterforms
    (O, the counter of A/D/etc.) that a solid disk can't approximate well."""
    img = _new_canvas()
    m = MASK_RESOLUTION * 0.06
    draw = ImageDraw.Draw(img)
    draw.ellipse([m, m, MASK_RESOLUTION - m, MASK_RESOLUTION - m], fill=255)
    inner = MASK_RESOLUTION * thickness_ratio
    draw.ellipse([inner, inner, MASK_RESOLUTION - inner, MASK_RESOLUTION - inner], fill=0)
    return _to_mask(img)


def _square_border_mask(thickness_ratio: float = 0.22) -> np.ndarray:
    img = _new_canvas()
    m = MASK_RESOLUTION * 0.04
    draw = ImageDraw.Draw(img)
    draw.rectangle([m, m, MASK_RESOLUTION - m, MASK_RESOLUTION - m], fill=255)
    inner = MASK_RESOLUTION * thickness_ratio
    draw.rectangle([inner, inner, MASK_RESOLUTION - inner, MASK_RESOLUTION - inner], fill=0)
    return _to_mask(img)


def _triangle_mask() -> np.ndarray:
    img = _new_canvas()
    ImageDraw.Draw(img).polygon(_regular_polygon(3, rotation_deg=-90, radius_ratio=0.48), fill=255)
    return _to_mask(img)


def _right_triangle_mask() -> np.ndarray:
    img = _new_canvas()
    m = MASK_RESOLUTION * 0.02
    ImageDraw.Draw(img).polygon(
        [(m, m), (m, MASK_RESOLUTION - m), (MASK_RESOLUTION - m, MASK_RESOLUTION - m)], fill=255)
    return _to_mask(img)


def _pentagon_mask() -> np.ndarray:
    img = _new_canvas()
    ImageDraw.Draw(img).polygon(_regular_polygon(5, radius_ratio=0.48), fill=255)
    return _to_mask(img)


def _hexagon_mask() -> np.ndarray:
    img = _new_canvas()
    ImageDraw.Draw(img).polygon(_regular_polygon(6, rotation_deg=-90, radius_ratio=0.48), fill=255)
    return _to_mask(img)


def _star_mask(points: int, inner_ratio: float = 0.22) -> np.ndarray:
    img = _new_canvas()
    ImageDraw.Draw(img).polygon(_star(points, outer_ratio=0.48, inner_ratio=inner_ratio), fill=255)
    return _to_mask(img)


def _up_arrow_mask() -> np.ndarray:
    """Hand-specified polygon: a triangular head over a rectangular shaft."""
    img = _new_canvas()
    c = MASK_RESOLUTION / 2.0
    head_w, head_top, head_base = MASK_RESOLUTION * 0.42, MASK_RESOLUTION * 0.06, MASK_RESOLUTION * 0.42
    shaft_w, shaft_bottom = MASK_RESOLUTION * 0.18, MASK_RESOLUTION * 0.92
    pts = [
        (c, head_top),
        (c + head_w / 2, head_base),
        (c + shaft_w / 2, head_base),
        (c + shaft_w / 2, shaft_bottom),
        (c - shaft_w / 2, shaft_bottom),
        (c - shaft_w / 2, head_base),
        (c - head_w / 2, head_base),
    ]
    ImageDraw.Draw(img).polygon(pts, fill=255)
    return _to_mask(img)


def _shield_mask() -> np.ndarray:
    """Hand-approximated: flat top, curved-ish sides tapering to a point at
    the bottom. Eyeballed against the shape's usual silhouette, not sourced
    from a real asset — flag as approximate if it ever needs to match the
    in-game shape precisely."""
    img = _new_canvas()
    m = MASK_RESOLUTION * 0.1
    c = MASK_RESOLUTION / 2.0
    top_y = MASK_RESOLUTION * 0.02
    mid_y = MASK_RESOLUTION * 0.55
    bottom_y = MASK_RESOLUTION * 0.94
    pts = [
        (m, top_y), (MASK_RESOLUTION - m, top_y),
        (MASK_RESOLUTION - m, mid_y), (c, bottom_y), (m, mid_y),
    ]
    ImageDraw.Draw(img).polygon(pts, fill=255)
    return _to_mask(img)


_BUILDERS: dict[str, tuple[int, str, callable, bool]] = {
    # shape_id: (resource_index, display_name, mask_builder, rotationally_symmetric)
    "square": (1, "Square", _square_mask, False),
    "circle": (2, "Circle", _circle_mask, True),
    "circle_border": (12, "Circle Border", _circle_border_mask, True),
    "square_border": (11, "Square Border", _square_border_mask, False),
    "triangle": (3, "Triangle", _triangle_mask, False),
    "right_triangle": (4, "Right Triangle", _right_triangle_mask, False),
    "hexagon": (5, "Hexagon", _hexagon_mask, False),
    "rounded_square": (22, "Rounded Square", _rounded_square_mask, False),
    "five_pointed_star": (8, "Five Pointed Star", lambda: _star_mask(5), False),
    "half_circle": (9, "Half Circle", _half_circle_mask, False),
    "shield": (10, "Shield", _shield_mask, False),
    "tapered_rectangle": (20, "Tapered Rectangle", _tapered_rectangle_mask, False),
    "fat_five_pointed_star": (21, "Fat Five Pointed Star", lambda: _star_mask(5, inner_ratio=0.34), False),
    "ten_pointed_star": (23, "Ten Pointed Star", lambda: _star_mask(10, inner_ratio=0.32), False),
    "up_arrow": (25, "Up Arrow", _up_arrow_mask, False),
    "quarter_circle": (30, "Quarter Circle", _quarter_circle_mask, False),
    "pentagon": (35, "Pentagon", _pentagon_mask, False),
}


def _build_catalog() -> dict[str, PrimitiveShape]:
    catalog = {}
    for shape_id, (index, name, builder, symmetric) in _BUILDERS.items():
        catalog[shape_id] = PrimitiveShape(
            shape_id=shape_id, resource_index=index, display_name=name,
            mask=builder(), rotationally_symmetric=symmetric)
    return catalog


PRIMITIVE_CATALOG: dict[str, PrimitiveShape] = _build_catalog()
