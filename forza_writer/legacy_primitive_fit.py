"""Legacy raster-trace glyph-to-shapes strategy.

A faithful port of the original text-vinyl generator (written by this
project's author, using Cursor, and later contributed into bvzray's
`forza-painter-fh6` where it shipped in v1.9.5) — kept here as a known,
independently-produced reference to compare against `primitive_fit.py`'s
newer vector-outline fitter. Ported functions:

- `_render_glyph_mask` <- `forza-painter-fh6/src/text/geometry.py`'s
  `_render_horizontal_ltr_mask`
- `_decompose_mask_to_rectangles` <- the same file's
  `decompose_mask_to_rectangles`, ported verbatim (the actual algorithm
  worth preserving faithfully — everything else here is new glue).

Where the two pipelines fundamentally differ: this one rasterizes the
glyph with PIL (`ImageFont`/`ImageDraw`) and greedily merges filled grid
cells into maximal rectangles — no font-outline extraction, no curve
fitting, always Squares. That's a genuinely different algorithm from
`primitive_fit.py`'s vector silhouette search, which is the point: a
second, independently-tuned reference implementation, not a replacement.

Only the plain default "custom" preset behavior from the original tool is
ported (`cell_size=1`, `font_size=120`, no masks, no CJK/vertical-writing
support) — that's the actual shipped Latin-text default, not a stripped-down
approximation of it. See `THIRD_PARTY_NOTICES.md` for the full attribution.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from forza_writer.layout import PIXEL_ART_SQUARE_SIZE
from forza_writer.primitive_shapes import PRIMITIVE_CATALOG
from forza_writer.shapes import resource_to_typecode, resource_to_shape_word

DEFAULT_FONT_SIZE = 120
DEFAULT_CELL_SIZE = 1
DEFAULT_PADDING = 24
_FILL_THRESHOLD_FRACTION = 0.45  # matches the original's cell-fill test exactly

_SQUARE = PRIMITIVE_CATALOG["square"]
SQUARE_TYPE_WORD = resource_to_shape_word("Primitives", _SQUARE.resource_index)
SQUARE_TYPECODE = resource_to_typecode("Primitives", _SQUARE.resource_index)


def _render_glyph_mask(char: str, font_path: Path, font_size: int = DEFAULT_FONT_SIZE,
                        padding: int = DEFAULT_PADDING) -> Image.Image:
    """Rasterize a single character to an 'L'-mode ink mask, sized to its
    own drawn bounding box plus a small margin. Direct port of
    `_render_horizontal_ltr_mask`'s horizontal-LTR path (the only writing
    mode this port needs)."""
    font = ImageFont.truetype(str(font_path), font_size)
    probe = Image.new("L", (4, 4), 0)
    draw = ImageDraw.Draw(probe)
    bbox = draw.textbbox((0, 0), char, font=font)
    width = max(4, bbox[2] - bbox[0] + padding * 2)
    height = max(4, bbox[3] - bbox[1] + padding * 2)
    image = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(image)
    origin = (padding - bbox[0], padding - bbox[1])
    draw.text(origin, char, fill=255, font=font)
    return image


def _decompose_mask_to_rectangles(mask: Image.Image, cell_size: int = DEFAULT_CELL_SIZE
                                   ) -> list[tuple[int, int, int, int]]:
    """Merge grid cells into larger axis-aligned rectangles. Ported
    verbatim from `decompose_mask_to_rectangles` (same cell-fill threshold,
    same greedy row-scan-and-grow-height merge)."""
    cell_size = max(1, min(16, int(cell_size)))
    width, height = mask.size
    pixels = mask.load()
    threshold = 128
    cols = (width + cell_size - 1) // cell_size
    rows = (height + cell_size - 1) // cell_size
    grid = [[False] * cols for _ in range(rows)]

    for row in range(rows):
        y0 = row * cell_size
        y1 = min(height, y0 + cell_size)
        for col in range(cols):
            x0 = col * cell_size
            x1 = min(width, x0 + cell_size)
            filled = 0
            total = 0
            for y in range(y0, y1):
                for x in range(x0, x1):
                    total += 1
                    if pixels[x, y] >= threshold:
                        filled += 1
            grid[row][col] = filled > total * _FILL_THRESHOLD_FRACTION

    visited = [[False] * cols for _ in range(rows)]
    rectangles: list[tuple[int, int, int, int]] = []
    for row in range(rows):
        col = 0
        while col < cols:
            if not grid[row][col] or visited[row][col]:
                col += 1
                continue
            span = 1
            while col + span < cols and grid[row][col + span] and not visited[row][col + span]:
                span += 1
            height_span = 1
            can_grow = True
            while row + height_span < rows and can_grow:
                for dx in range(span):
                    if not grid[row + height_span][col + dx] or visited[row + height_span][col + dx]:
                        can_grow = False
                        break
                if can_grow:
                    height_span += 1
            for dy in range(height_span):
                for dx in range(span):
                    visited[row + dy][col + dx] = True
            x0 = col * cell_size
            y0 = row * cell_size
            rectangles.append((x0, y0, min(width - x0, span * cell_size),
                                min(height - y0, height_span * cell_size)))
            col += span
    return rectangles


def fit_glyph_legacy(char: str, font_path: Path, font_size: int = DEFAULT_FONT_SIZE,
                      cell_size: int = DEFAULT_CELL_SIZE, glyph_size: float = 300.0
                      ) -> tuple[list[dict], str]:
    """Rasterize `char` and decompose it into Square shapes, in the same
    real-unit convention `primitive_fit.placements_to_shapes` targets
    (glyph centred at the origin, longest ink-bbox dimension scaled to
    `glyph_size`) — so the result composes correctly through
    `forza_writer/text_compose.py` exactly like every other strategy's
    output, with no special-casing needed there.

    Returns `(shapes, "legacy_primitive")`, matching
    `primitive_fit.fit_glyph_with_strategy`'s `(shapes, strategy)` shape.
    """
    mask = _render_glyph_mask(char, Path(font_path), font_size)
    rects = _decompose_mask_to_rectangles(mask, cell_size)
    if not rects:
        return [], "legacy_primitive"

    x_min = min(x0 for x0, _y0, _w, _h in rects)
    x_max = max(x0 + w for x0, _y0, w, _h in rects)
    y_min = min(y0 for _x0, y0, _w, _h in rects)
    y_max = max(y0 + h for _x0, y0, _w, h in rects)
    bbox_cx = (x_min + x_max) / 2.0
    bbox_cy = (y_min + y_max) / 2.0
    span = max(x_max - x_min, y_max - y_min) or 1
    scale = glyph_size / span

    shapes = []
    for x0, y0, w, h in rects:
        rect_cx = x0 + w / 2.0
        rect_cy = y0 + h / 2.0
        shapes.append({
            "type": SQUARE_TYPECODE,
            "type_word": SQUARE_TYPE_WORD,
            "data": [
                round((rect_cx - bbox_cx) * scale, 6),
                round((rect_cy - bbox_cy) * scale, 6),
                round((w * scale) / PIXEL_ART_SQUARE_SIZE, 6),
                round((h * scale) / PIXEL_ART_SQUARE_SIZE, 6),
                0.0, 0.0, 0,
            ],
            "color": [255, 255, 255, 255],
            "mask": False,
        })
    return shapes, "legacy_primitive"
