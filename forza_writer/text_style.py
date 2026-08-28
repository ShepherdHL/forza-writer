"""Text styling for composed text: per-line solid/sequence/rainbow fill
color, faux bold/italic, and underline/strikethrough bars.

Deliberately kept separate from `text_compose.py`'s layout math: everything
here is pure shape/color transforms with no font I/O, so it's testable
without a real font file (unlike most of `text_compose.py`, which needs one).

Colors are plain `(r, g, b, a)` int tuples, 0-255 per channel, matching the
`"color"` field every emitted shape dict already carries (see `out.json` /
`forza_writer/primitive_fit.py`'s `placements_to_shapes`).

Bold and italic both reuse fields FH6's own renderer already understands
per-shape (`data[2]`/`data[3]` scale, `data[5]` shear slope: see
`primitive_fit.py`'s `MAX_ABS_SKEW`), rather than duplicating shapes: an
offset-duplicated outline/shadow would multiply the FH6 vinyl layer count
(e.g. an 8-direction outline turns 50 shapes into 450), which this project
tracks as a real constrained resource elsewhere (glyph/layer budgets in
README.md's Direct Generator section). Scaling/shearing shapes in place adds
zero shapes.
"""

from __future__ import annotations

import colorsys
from dataclasses import dataclass
from typing import Literal

RGBA = tuple[int, int, int, int]

FILL_MODES = ("solid", "sequence", "rainbow")

# Matches primitive_fit.MAX_ABS_SKEW: FH6's own bound on data[5]'s shear
# slope (a tan(angle), not degrees); going past this is unrenderable, not
# just visually extreme.
MAX_ABS_SKEW = 0.8

WHITE: RGBA = (255, 255, 255, 255)


@dataclass(frozen=True)
class LineFill:
    """The color treatment for one line of composed text. `sequence`
    generalizes both a 2-stop gradient and a fixed-band rainbow (e.g.
    ROYGBIV) into one editable color list: `blend=True` interpolates
    smoothly across every stop, supporting any number of stops; `blend=False`
    repeats each stop as a discrete band, cycling through any color list,
    not just a fixed rainbow."""
    mode: Literal["solid", "sequence", "rainbow"] = "solid"
    colors: tuple[RGBA, ...] = (WHITE,)
    blend: bool = False

    def __post_init__(self):
        if self.mode not in FILL_MODES:
            raise ValueError(f"mode must be one of {FILL_MODES}, got {self.mode!r}")
        if self.mode == "sequence" and not self.colors:
            raise ValueError("sequence fill needs at least one color")

    @property
    def is_noop(self) -> bool:
        return self.mode == "solid" and self.colors == (WHITE,)


@dataclass(frozen=True)
class TextStyle:
    """A no-arg `TextStyle()` is a complete no-op: no bold/italic/underline/
    strikethrough and no per-line fills: existing callers that don't pass
    a style must see byte-identical output to before this module existed.

    Bold/italic/underline/strikethrough/size/spacing stay document-wide
    (set once for the whole composed block); only fill color is per-line:
    `fills[i]` is the LineFill for composed line `i`."""
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strikethrough: bool = False
    fills: tuple[LineFill, ...] = ()

    @property
    def is_noop(self) -> bool:
        return (not self.bold and not self.italic and not self.underline
                and not self.strikethrough and all(f.is_noop for f in self.fills))

    def fill_for_line(self, index: int) -> LineFill:
        """The LineFill for composed line `index`. No fills configured (the
        default) means every line is unstyled; an index past the end of
        `fills` reuses the last entry: defensive only, since callers are
        expected to keep `fills` sized to the actual line count."""
        if not self.fills:
            return LineFill()
        return self.fills[index] if index < len(self.fills) else self.fills[-1]


@dataclass(frozen=True)
class CharPosition:
    """Where one composed character/token sits within its own line, for
    `color_for` to key off of. Both Sequence and Rainbow are per-line-scoped,
    since fill is a per-line concept and a document-spanning Rainbow sweep
    would be the odd one out."""
    index_in_line: int
    chars_in_line: int


def _lerp_color(start: RGBA, end: RGBA, t: float) -> RGBA:
    t = max(0.0, min(1.0, t))
    return tuple(round(a + (b - a) * t) for a, b in zip(start, end))  # type: ignore[return-value]


def _lerp_sequence(colors: tuple[RGBA, ...], t: float) -> RGBA:
    """Interpolates across an arbitrary number of color stops: t=0 is
    colors[0], t=1 is colors[-1], evenly spaced in between."""
    if len(colors) == 1:
        return colors[0]
    t = max(0.0, min(1.0, t))
    scaled = t * (len(colors) - 1)
    i = int(scaled)
    if i >= len(colors) - 1:
        return colors[-1]
    return _lerp_color(colors[i], colors[i + 1], scaled - i)


def _fraction(index: int, count: int) -> float:
    return 0.0 if count <= 1 else index / (count - 1)


def color_for(fill: LineFill, pos: CharPosition) -> RGBA:
    """The fill color for one character/token, per `fill.mode`."""
    if fill.mode == "solid":
        return fill.colors[0]
    if fill.mode == "rainbow":
        # Deliberately NOT _fraction (index/(count-1), endpoint-inclusive):
        # that would give the first and last character in a line the same
        # hue (both land on 0/1, i.e. red), making the sweep visibly snap
        # back at the line's end. index/count keeps every step distinct.
        hue = 0.0 if pos.chars_in_line <= 0 else (pos.index_in_line % pos.chars_in_line) / pos.chars_in_line
        r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
        return (round(r * 255), round(g * 255), round(b * 255), 255)
    if fill.mode == "sequence":
        if fill.blend:
            t = _fraction(pos.index_in_line, pos.chars_in_line)
            return _lerp_sequence(fill.colors, t)
        return fill.colors[pos.index_in_line % len(fill.colors)]
    raise ValueError(f"unknown fill mode {fill.mode!r}")  # pragma: no cover: guarded by __post_init__


def apply_bold(shape: dict, factor: float = 1.15) -> dict:
    """Thickens a non-mask shape by scaling its own width/height in place
    (around its own center: data[0]/data[1] are untouched, so this can't
    shift the shape's position). Mask (cutout/counter) shapes pass through
    unscaled: growing a letter's outline while its counter stays put is
    exactly what shrinks the counter the way a real bold weight does, and
    scaling a mask independently of the fill shape it cuts through would
    misalign the hole instead."""
    if shape.get("mask"):
        return shape
    data = shape["data"]
    return {**shape, "data": [
        data[0], data[1], data[2] * factor, data[3] * factor, *data[4:],
    ]}


def apply_italic(shape: dict, skew_delta: float = 0.25) -> dict:
    """Adds `skew_delta` to data[5] (FH6's own per-shape shear slope,
    already used for this by primitive_fit.py's candidate search), clamped
    to +/-MAX_ABS_SKEW. Applies to mask shapes too, so a letter's counter
    shears along with its outline instead of staying upright inside a
    leaning glyph."""
    data = shape["data"]
    skew = data[5] if len(data) > 5 else 0.0
    new_skew = max(-MAX_ABS_SKEW, min(MAX_ABS_SKEW, skew + skew_delta))
    new_data = list(data) + [0.0] * max(0, 6 - len(data))
    new_data[5] = new_skew
    return {**shape, "data": new_data}


def build_bar_shape(x_start: float, x_end: float, y_center: float,
                     thickness: float, color: RGBA) -> dict:
    """One "Square" primitive shape spanning [x_start, x_end] at y_center
    with the given height, used for underline/strikethrough bars. Same
    type/type_word/scale construction as primitive_fit.placements_to_shapes
    uses for Square primitives, but built directly in real-unit space
    (text_compose's shapes are already final real units, not the pixel/
    COORD_RANGE space placements_to_shapes converts from)."""
    from forza_writer.layout import PIXEL_ART_SQUARE_SIZE
    from forza_writer.primitive_shapes import PRIMITIVE_CATALOG
    from forza_writer.shapes import resource_to_shape_word, resource_to_typecode

    square = PRIMITIVE_CATALOG["square"]
    width = x_end - x_start
    x_center = (x_start + x_end) / 2.0
    return {
        "type": resource_to_typecode("Primitives", square.resource_index),
        "type_word": resource_to_shape_word("Primitives", square.resource_index),
        "data": [
            round(x_center, 6), round(y_center, 6),
            round(width / PIXEL_ART_SQUARE_SIZE, 6),
            round(thickness / PIXEL_ART_SQUARE_SIZE, 6),
            0.0, 0.0, 0,
        ],
        "color": list(color),
        "mask": False,
    }
