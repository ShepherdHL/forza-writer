"""Exact rectangle decomposition for rectilinear (blocky) glyphs.

Why this exists alongside `forza_writer.primitive_fit`'s greedy shape search:
the two solve genuinely different problems, and each is bad at the other's.

For a glyph whose outline is entirely axis-aligned (stencil/blocky fonts
like Amarillo USAF, where every edge is horizontal or vertical), the ideal
answer is a small set of exact rectangles, and it can be computed rather
than searched for. Measured on Amarillo USAF: 'E' decomposes to 4 rectangles
at IoU 1.000, where the greedy shape search needed 9 shapes and still only
reached IoU 0.855. The search literally cannot express the answer: the
rectangles an 'E' needs have aspect ratios 0.188/2.909/1.333, and the
search's discrete scale x aspect ladder only spans 0.51-1.96.

The converse is just as true, which is why this module doesn't replace the
search: on curved glyphs rectangle decomposition explodes (Amarillo 'O' needs
18 rectangles where the search finds 2 shapes, 'S' needs 29 where the search
finds 5). `primitive_fit.fit_glyph` routes between the two.

This mirrors how the same problem is solved elsewhere: both hand-made vinyl
fontpacks and forza-painter-fh6's text engine are decomposition-first, with
continuous (unquantized) per-rectangle scaling.
"""

from __future__ import annotations

import numpy as np

from forza_writer.primitive_shapes import PRIMITIVE_CATALOG

# A contour edge counts as axis-aligned if it deviates by less than this in
# normalized +-COORD_RANGE units. Font outlines are rarely bit-exact, and
# curve flattening introduces small residuals, so this can't be zero.
AXIS_TOLERANCE = 0.75

# Below this pixel area a leftover region isn't worth its own vinyl layer:
# it would be a sliver invisible at real scale.
MIN_RECT_AREA = 6


def is_rectilinear(contours: list[list[tuple[float, float]]],
                    tolerance: float = AXIS_TOLERANCE) -> bool:
    """True if every edge of every contour is horizontal or vertical.

    This is the routing signal for choosing decomposition over search. It's
    a property of the glyph, not the font: a font can mix blocky and curved
    glyphs and each is routed on its own merits.
    """
    if not contours:
        return False
    for contour in contours:
        if len(contour) < 3:
            return False
        for i, point in enumerate(contour):
            nxt = contour[(i + 1) % len(contour)]
            dx = abs(point[0] - nxt[0])
            dy = abs(point[1] - nxt[1])
            if dx > tolerance and dy > tolerance:
                return False
    return True


def _largest_all_ink_rect(mask: np.ndarray) -> tuple[int, int, int, int, int]:
    """Largest axis-aligned all-True rectangle in `mask`, via the standard
    per-row histogram / monotonic-stack method (O(rows*cols)).

    Returns (area, top, left, height, width); area 0 if the mask is empty.
    """
    rows, cols = mask.shape
    heights = np.zeros(cols, dtype=int)
    best = (0, 0, 0, 0, 0)
    for row in range(rows):
        heights = np.where(mask[row], heights + 1, 0)
        stack: list[tuple[int, int]] = []
        for col in range(cols + 1):
            current = int(heights[col]) if col < cols else 0
            start = col
            while stack and stack[-1][1] >= current:
                span_start, span_height = stack.pop()
                area = span_height * (col - span_start)
                if area > best[0]:
                    best = (area, row - span_height + 1, span_start, span_height, col - span_start)
                start = span_start
            stack.append((start, current))
    return best


def decompose_mask_to_rects(mask: np.ndarray, max_rects: int = 40,
                             min_area: int = MIN_RECT_AREA) -> list[tuple[int, int, int, int]]:
    """Cover `mask` with axis-aligned rectangles, largest-first.

    Every rectangle is fully inside the mask, so the cover never spills
    outside the glyph: for a truly rectilinear shape this reaches an exact
    (IoU 1.0) cover. Returns a list of (top, left, height, width) in pixels.
    """
    residual = mask.copy()
    rects: list[tuple[int, int, int, int]] = []
    for _ in range(max_rects):
        area, top, left, height, width = _largest_all_ink_rect(residual)
        if area < min_area:
            break
        rects.append((top, left, height, width))
        residual[top:top + height, left:left + width] = False
        if not residual.any():
            break
    return rects


def rects_to_placements(rects: list[tuple[int, int, int, int]], resolution: int,
                         is_mask: bool = False):
    """Convert pixel rectangles into `primitive_fit.PlacedShape` squares.

    Each rectangle becomes one Square primitive scaled independently on X and
    Y to exactly its own dimensions: no aspect quantization, which is the
    whole point of this path. `is_mask` tags every resulting placement as a
    stencil cutout (see `stencil_placements`) rather than an ordinary fill.
    """
    from forza_writer.primitive_fit import PlacedShape

    square_id = "square"
    assert square_id in PRIMITIVE_CATALOG, "the Square primitive is required for rect decomposition"

    placements = []
    for top, left, height, width in rects:
        placements.append(PlacedShape(
            shape_id=square_id,
            cx=left + width / 2.0,
            cy=top + height / 2.0,
            scale_x=width / resolution,
            scale_y=height / resolution,
            rotation_deg=0.0,
            is_mask=is_mask,
        ))
    return placements


def _bounding_box(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    """(top, left, height, width) of the tight bounding box of True pixels,
    or None if `mask` is empty."""
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    top, bottom = int(ys.min()), int(ys.max())
    left, right = int(xs.min()), int(xs.max())
    return top, left, bottom - top + 1, right - left + 1


def decompose_negative_space(mask: np.ndarray, max_rects: int = 40,
                              min_area: int = MIN_RECT_AREA) -> list[tuple[int, int, int, int]] | None:
    """Rectangle-decompose the gaps *inside* `mask`'s own bounding box:
    the "notches" a stencil would need to cut from a solid background to
    reveal `mask`'s shape. Returns None if `mask` is empty (nothing to cut
    a stencil from in the first place).

    A rectilinear region's complement within its own bounding rectangle is
    itself rectilinear, so this reuses `decompose_mask_to_rects` unchanged:
    no separate algorithm, just a second call against an inverted, bbox-
    clipped input.
    """
    bbox = _bounding_box(mask)
    if bbox is None:
        return None
    top, left, height, width = bbox
    negative = np.zeros_like(mask)
    negative[top:top + height, left:left + width] = True
    negative &= ~mask
    return decompose_mask_to_rects(negative, max_rects=max_rects, min_area=min_area)


def stencil_placements(mask: np.ndarray, resolution: int, max_rects: int = 40):
    """Build a stencil decomposition: one background Square sized to the
    glyph's bounding box, plus one mask cutout per negative-space rectangle.

    Returns None if the glyph is empty, or if the negative space needs more
    than `max_rects` cutouts (not worth it; falls back to the direct fill).
    """
    bbox = _bounding_box(mask)
    if bbox is None:
        return None
    negative_rects = decompose_negative_space(mask, max_rects=max_rects + 1)
    if negative_rects is None or len(negative_rects) > max_rects:
        return None

    background = rects_to_placements([bbox], resolution, is_mask=False)
    cutouts = rects_to_placements(negative_rects, resolution, is_mask=True)
    return background + cutouts
