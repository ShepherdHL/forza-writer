"""Resolves one `PlateField`'s `CharSource` + text into a *typeset layout*:
one placeholder per character, correctly sized and positioned as if it held
that character in the source font's real proportions, in field-local space
-- centered near its own natural position, not yet placed into the plate
(that's `layout_engine.place_shapes_in_box`, called by `renderer.py`).

Layout (position/spacing) always comes from `CharSource.font_file`'s
metrics (`hhea`/`OS/2`/`hmtx`, via fontTools) -- that half never changed.
What each character actually *draws as* is a separate, optional choice:
`placeholder_font` (an int 1-11, threaded down from
`PlateInstance.placeholder_font` via `renderer.py`) swaps a character's
plain box for one of FH6's 11 native in-game vinyl fonts (see
`forza_writer.shapes.char_to_resource`) -- real, final letterform meshes
the in-game Vinyl Editor already has (the same shapes
`tools/gen_modelbin_gui/tabs/forza_font_text.py`'s tab uses), not
generated/traced/fitted for this feature, so it costs nothing extra to
resolve. A character with no shape in the chosen Forza font (coverage is
letters/digits/limited punctuation, not full Unicode -- see
`FORZA_FONTS_REFERENCE.md`) falls back to a plain box for that one
character. `placeholder_font=None` (the default) keeps every character a
plain box, matching this feature's original design -- see
`template.py::CharSource`'s docstring for why letterform geometry a plate
field generates *itself* (as opposed to referencing an already-existing
resource, real font-file metrics aside) was removed: pixel-traced plate
text looked poor and cost far too many shapes for an in-game decal. The
placeholder boxes (or Forza-font letterforms) are meant to be fine-tuned
or replaced in KFPS; `renderer.py` gives each one its own addressable
`PlateGroupNode` (`GroupKind.CHARACTER`) so that's a per-character
operation, not an all-or-nothing one.

A missing font file or a character outside the font's cmap is a warning,
never an exception -- a fallback advance width keeps the rest of the line
positioned sanely rather than collapsing onto the missing character.
`target_height`, if given, uniformly rescales the composed result via
`layout_engine.scale_shapes_to_height`, exactly as before.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from fontTools.ttLib import TTFont

from forza_writer.layout import PIXEL_ART_SQUARE_SIZE
from forza_writer.plates.layout_engine import scale_shapes_to_height
from forza_writer.plates.template import CharSource
from forza_writer.primitive_shapes import PRIMITIVE_CATALOG
from forza_writer.shapes import char_to_resource, resource_to_shape_word, resource_to_typecode

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FONTS_DIR = _REPO_ROOT / "assets" / "fonts"
PLATE_ASSETS_DIR = _REPO_ROOT / "data" / "plate_assets"

# Matches forza_writer.text_compose's own K/COORD_RANGE/GLYPH_SIZE convention
# (real_units_per_glyph_unit = GLYPH_SIZE / (2*COORD_RANGE)) so a character's
# placeholder box lands at the same width:height ratio a real traced glyph
# from the same font used to -- existing templates' char_scale/tracking
# values stay meaningful without re-tuning against a new unit scale.
_COORD_RANGE = 100.0
_GLYPH_SIZE = 300.0
_K = _GLYPH_SIZE / (2 * _COORD_RANGE)  # 1.5

ALIGNMENTS = ("left", "center", "right", "justify")


@lru_cache(maxsize=None)
def _font_metrics(font_path_str: str):
    """(units_per_em, cap_height, cmap, hmtx) for one font file, cached --
    read once per font regardless of how many characters/fields use it.
    `cap_height` prefers `OS/2.sCapHeight` (the actual design cap height);
    falls back to the hhea ascender for a font without that optional table."""
    font = TTFont(font_path_str, fontNumber=0)
    try:
        units_per_em = font["head"].unitsPerEm
        os2 = font.get("OS/2")
        cap_height = getattr(os2, "sCapHeight", 0) if os2 else 0
        if not cap_height:
            cap_height = font["hhea"].ascender
        cmap = font.getBestCmap()
        hmtx = {name: metrics[0] for name, metrics in font["hmtx"].metrics.items()}
    finally:
        font.close()
    return units_per_em, cap_height, cmap, hmtx


def _advance_width(char: str, units_per_em: int, cmap: dict, hmtx: dict,
                    warnings: list[str], font_label: str) -> float:
    glyph_name = cmap.get(ord(char))
    if glyph_name is not None and glyph_name in hmtx:
        return hmtx[glyph_name]
    msg = f"{char!r} is not in {font_label}'s font -- used an estimated width"
    if msg not in warnings:
        warnings.append(msg)
    return units_per_em / 2.0


def _placeholder_rect(cx: float, cy: float, width: float, height: float) -> dict:
    """One "Square" primitive centered at (cx, cy) -- matches
    `forza_writer.plates.renderer._solid_rect_shape`'s exact construction
    (same primitive lookup, same PIXEL_ART_SQUARE_SIZE convention), used
    here as a per-character placeholder rather than a decoration fill.
    Plain white; `renderer.py` applies the field's actual color on top,
    same as it always has."""
    square = PRIMITIVE_CATALOG["square"]
    return {
        "type": resource_to_typecode("Primitives", square.resource_index),
        "type_word": resource_to_shape_word("Primitives", square.resource_index),
        "data": [
            round(cx, 6), round(cy, 6),
            round(width / PIXEL_ART_SQUARE_SIZE, 6), round(height / PIXEL_ART_SQUARE_SIZE, 6),
            0.0, 0.0, 0,
        ],
        "color": [255, 255, 255, 255],
        "mask": False,
    }


def _forza_font_shape(cx: float, cy: float, height: float, char: str, font: int) -> dict | None:
    """One native Forza in-game font glyph mesh (see
    `forza_writer.shapes.char_to_resource`) at (cx, cy), uniformly scaled
    to `height` on both axes -- matching how
    `forza_writer.layout.layout_forza_text` itself scales these same
    meshes (`scale, scale`, never stretched non-uniformly the way a plain
    placeholder box is), so a letterform keeps its natural proportions
    regardless of how wide its metrics-derived advance happens to be.
    Returns `None` for a character the chosen font has no native shape for
    (Forza's 11 fonts all cover the same letters/digits/limited
    punctuation, not full Unicode -- see `FORZA_FONTS_REFERENCE.md`)."""
    resource = char_to_resource(char, font)
    if resource is None:
        return None
    family, index = resource
    scale = height / PIXEL_ART_SQUARE_SIZE
    return {
        "type": resource_to_typecode(family, index),
        "type_word": resource_to_shape_word(family, index),
        "data": [round(cx, 6), round(cy, 6), round(scale, 6), round(scale, 6), 0.0, 0.0, 0],
        "color": [255, 255, 255, 255],
        "mask": False,
    }


def _layout_text(text: str, font_path: Path, align: str, tracking: float, line_spacing: float,
                  placeholder_font: int | None) -> tuple[list[tuple[str, dict]], list[str]]:
    """Lays out `text` against `font_path`'s metrics. Returns
    `(char_shapes, warnings)` where `char_shapes` is one `(char, shape)`
    pair per non-space character, in reading order -- spaces advance the
    cursor but produce no shape/node, matching how a space has nothing to
    swap for real artwork in KFPS. `placeholder_font`, if given, draws a
    real Forza-font letterform per character instead of a plain box (see
    `_forza_font_shape`), falling back to a box for any one character that
    font doesn't cover."""
    if align not in ALIGNMENTS:
        raise ValueError(f"align must be one of {ALIGNMENTS}, got {align!r}")
    font_path_str = str(font_path)
    warnings: list[str] = []
    if not font_path.exists():
        return [], [f"font {font_path_str!r} not found -- no glyphs resolved"]

    units_per_em, cap_height, cmap, hmtx = _font_metrics(font_path_str)
    scale_font = 200.0 / units_per_em
    box_height = cap_height * scale_font * _K
    line_height = box_height * 1.4 * line_spacing

    lines_raw = text.split("\n")
    char_shapes: list[tuple[str, dict]] = []
    for line_index, line_text in enumerate(lines_raw):
        line_offset = line_index * line_height
        widths = [
            (char, _advance_width(char, units_per_em, cmap, hmtx, warnings, font_path.name) * scale_font * _K)
            for char in line_text
        ]
        line_width = sum(w for _, w in widths) + tracking * max(0, len(widths) - 1)
        if align == "right":
            shift = -line_width
        elif align in ("center", "justify"):
            shift = -line_width / 2.0
        else:
            shift = 0.0

        x = shift
        for char, advance in widths:
            if not char.isspace():
                shape = None
                if placeholder_font is not None:
                    shape = _forza_font_shape(x + advance / 2.0, line_offset, box_height, char, placeholder_font)
                    if shape is None:
                        msg = f"{char!r} has no shape in Forza Font {placeholder_font} -- used a placeholder box"
                        if msg not in warnings:
                            warnings.append(msg)
                if shape is None:
                    shape = _placeholder_rect(x + advance / 2.0, line_offset, advance, box_height)
                char_shapes.append((char, shape))
            x += advance + tracking

    return char_shapes, warnings


def resolve_field_shapes(
    text: str,
    char_source: CharSource,
    *,
    align: str = "left",
    tracking: float = 0.0,
    line_spacing: float = 1.0,
    target_height: float | None = None,
    placeholder_font: int | None = None,
) -> tuple[list[tuple[str, dict]], list[str]]:
    """Lays out `text` against `char_source.font_file`'s metrics. If any
    character is missing from it and `char_source.fallback` is set, the
    *whole* text is re-laid-out against the fallback font instead (a simple
    whole-swap, not per-character splicing -- correct and easy to reason
    about, at the cost of every character switching font together rather
    than mixing two within one field, which real plate fields don't need).
    `placeholder_font`, if given, is passed straight through to
    `_layout_text` -- see that function and `_forza_font_shape` for what it
    does; unrelated to `char_source`'s own metrics font, and not affected
    by the fallback-font swap above (a real letterform choice, not a
    metrics-coverage one).

    Returns `(char_shapes, warnings)` -- see `_layout_text` for
    `char_shapes`'s shape. `renderer.py` uses the per-character pairing to
    give each placeholder its own `PlateGroupNode`."""
    if not text:
        return [], []

    font_path = FONTS_DIR / char_source.font_file
    char_shapes, warnings = _layout_text(text, font_path, align, tracking, line_spacing, placeholder_font)
    if warnings and char_source.fallback is not None:
        fb_path = FONTS_DIR / char_source.fallback.font_file
        fb_shapes, fb_warnings = _layout_text(text, fb_path, align, tracking, line_spacing, placeholder_font)
        if len(fb_warnings) < len(warnings):
            char_shapes, warnings = fb_shapes, fb_warnings

    if target_height is not None and char_shapes:
        rescaled = scale_shapes_to_height([shape for _, shape in char_shapes], target_height)
        char_shapes = [(char, shape) for (char, _), shape in zip(char_shapes, rescaled)]

    return char_shapes, warnings


def load_symbol_asset(asset_id: str) -> tuple[list[dict], list[str]]:
    """A reusable plate component's fixed shape list (`data/plate_assets/
    <asset_id>.json`, `{"shapes": [...]}`). Used by `renderer.py`'s
    `Decoration` handling -- a decoration has no typed text/`CharSource` to
    resolve, just an asset id. Unrelated to character layout above; kept in
    this module only because it shares the "load a small shape-list JSON
    off disk" shape with the rest of this module."""
    asset_path = PLATE_ASSETS_DIR / f"{asset_id}.json"
    if not asset_path.exists():
        return [], [f"symbol asset {asset_id!r} not found at {asset_path} -- no glyphs resolved"]
    data = json.loads(asset_path.read_text(encoding="utf-8"))
    return list(data.get("shapes", [])), []
