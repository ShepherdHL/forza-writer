"""Consolidated, cached font metadata for the Glyph Inspector.

Font metadata access is otherwise scattered: [[forza_writer/charset.py]]
opens the font for its own cmap-category split, [[forza_writer/text_compose.py]]
independently derives units-per-em/ascender/descender via `lru_cache`, and
[[forza_writer/variable_fonts.py]] separately inspects `fvar` axes. None of
them extract capHeight/xHeight or family/weight/style names, and each opens
the font itself rather than sharing one read. This module is the single
place the Glyph Inspector calls into for that combined metadata, cached per
font path so repeated glyph selection doesn't re-parse the font. It does not
replace or modify any of the three modules above -- they keep serving their
existing callers unchanged; this only adds the fourth, block-grouped view of
cmap coverage that the Inspector needs and that nothing else currently
computes (see [[forza_writer/unicode_blocks.py]]).
"""

from __future__ import annotations

import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from fontTools.ttLib import TTFont

from forza_writer.unicode_blocks import BLOCKS, block_for_codepoint

# tools/gen_modelbin.py -- same sys.path dance forza_writer/text_compose.py
# already does to reach it, for the same reason: glyph_geometry() below
# reuses its contour extraction rather than re-deriving glyph outlines a
# second way.
_TOOLS_DIR = str(Path(__file__).resolve().parent.parent / "tools")
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)
from forza_writer.variable_fonts import VariableFontInfo, inspect_variable_font

# Categories carved out of the Basic Latin block, matching the reference
# Pangram Pangram "Glyphs set overview" layout (Uppercase/Lowercase/Digits/
# Punctuation & Symbols shown before any named Unicode block). Every other
# category name is the literal Unicode block name from unicode_blocks.BLOCKS.
_BASIC_LATIN_CATEGORIES = ("Uppercase", "Lowercase", "Digits", "Punctuation & Symbols")

# Canonical category display order: the four Basic Latin buckets, then every
# other block in codepoint order, skipping "Basic Latin" itself (already
# split above) -- callers filter this down to categories the font actually
# has glyphs for.
CATEGORY_ORDER: tuple[str, ...] = _BASIC_LATIN_CATEGORIES + tuple(
    name for _start, _end, name in BLOCKS if name != "Basic Latin"
)


@dataclass(frozen=True)
class FontMetrics:
    units_per_em: int
    ascender: int
    descender: int
    cap_height: int | None  # OS/2.sCapHeight -- None if the font doesn't provide it
    x_height: int | None    # OS/2.sxHeight -- None if the font doesn't provide it


@dataclass(frozen=True)
class FontNames:
    family: str
    subfamily: str
    full_name: str
    weight_class: int | None  # OS/2.usWeightClass (100-900), None if no OS/2 table
    is_italic: bool


@dataclass(frozen=True)
class GlyphInfo:
    char: str
    codepoint: int
    glyph_name: str
    unicode_name: str | None  # unicodedata.name(), None if unassigned/has no name
    category: str             # see CATEGORY_ORDER


@dataclass(frozen=True)
class FontInfo:
    path: Path
    names: FontNames
    metrics: FontMetrics
    variable: VariableFontInfo
    glyphs_by_category: dict[str, list[GlyphInfo]]  # only categories with >=1 glyph, in CATEGORY_ORDER
    category_order: tuple[str, ...]                  # this font's populated categories, in display order


def _category_for(codepoint: int, char: str) -> str | None:
    """Unicode block name for *codepoint*, except Basic Latin is split into
    Uppercase/Lowercase/Digits/Punctuation & Symbols (see module docstring).
    Returns None for glyphs with no visible geometry (whitespace/control),
    matching charset.py's `categorize_char` skip behavior."""
    block = block_for_codepoint(codepoint)
    if block == "Basic Latin":
        cat = unicodedata.category(char)
        if cat == "Lu":
            return "Uppercase"
        if cat == "Ll":
            return "Lowercase"
        if cat == "Nd":
            return "Digits"
        if cat[0] in ("P", "S"):
            return "Punctuation & Symbols"
        return None  # space/control
    return block


def _read_name(table, *, primary_id: int, fallback_id: int, fallback: str) -> str:
    """Prefer the typographic name (16/17) over the legacy RIBBI-only name
    (1/2, capped at 4 style keywords) since Forza Writer's font packs
    routinely have more than 4 weights; fall back to the legacy id, then a
    caller-supplied default when the font has neither."""
    if table is None:
        return fallback
    value = (
        table.getName(primary_id, 3, 1, 0x409)
        or table.getName(primary_id, 1, 0, 0)
        or table.getName(fallback_id, 3, 1, 0x409)
        or table.getName(fallback_id, 1, 0, 0)
    )
    return str(value) if value is not None else fallback


def _load_names(font: TTFont) -> FontNames:
    table = font["name"] if "name" in font else None
    family = _read_name(table, primary_id=16, fallback_id=1, fallback="Unknown")
    subfamily = _read_name(table, primary_id=17, fallback_id=2, fallback="Regular")
    full_name = _read_name(table, primary_id=4, fallback_id=4, fallback=f"{family} {subfamily}")

    os2 = font.get("OS/2")
    weight_class = int(os2.usWeightClass) if os2 is not None else None
    is_italic = False
    if os2 is not None:
        is_italic = bool(os2.fsSelection & 0x01)
    elif "head" in font:
        is_italic = bool(font["head"].macStyle & 0x02)

    return FontNames(family=family, subfamily=subfamily, full_name=full_name,
                      weight_class=weight_class, is_italic=is_italic)


def _load_metrics(font: TTFont) -> FontMetrics:
    units_per_em = font["head"].unitsPerEm
    ascender = font["hhea"].ascender
    descender = font["hhea"].descender

    os2 = font.get("OS/2")
    # sCapHeight/sxHeight are OS/2 version 2+ fields; fontTools exposes 0 as
    # the default for older/absent versions, and 0 is never a real cap/x
    # height, so treat it the same as "field not provided".
    cap_height = getattr(os2, "sCapHeight", 0) if os2 is not None else 0
    x_height = getattr(os2, "sxHeight", 0) if os2 is not None else 0

    return FontMetrics(
        units_per_em=units_per_em,
        ascender=ascender,
        descender=descender,
        cap_height=cap_height or None,
        x_height=x_height or None,
    )


_font_info_cache: dict[str, FontInfo] = {}


def load_font_info(font_path: Path) -> FontInfo:
    """Load and cache combined metadata for *font_path*: names, metrics,
    variable-font axes, and cmap coverage grouped into Unicode-block
    categories. Cached per resolved path for the life of the process, same
    caching contract as charset.py's `_charset_cache` -- installed font
    files are static while the app runs, so a stale entry only matters if
    the file changes on disk mid-session, which nothing here does."""
    key = str(font_path)
    cached = _font_info_cache.get(key)
    if cached is not None:
        return cached

    font = TTFont(str(font_path), fontNumber=0)
    try:
        names = _load_names(font)
        metrics = _load_metrics(font)
        cmap = font.getBestCmap()
        glyph_order = font.getGlyphOrder()
        glyph_name_set = set(glyph_order)
    finally:
        font.close()

    variable = inspect_variable_font(font_path)

    glyphs_by_category: dict[str, list[GlyphInfo]] = {name: [] for name in CATEGORY_ORDER}
    for codepoint in sorted(cmap):
        char = chr(codepoint)
        category = _category_for(codepoint, char)
        if category is None:
            continue
        glyph_name = cmap[codepoint]
        if glyph_name not in glyph_name_set:
            continue  # cmap points at a glyph the font doesn't actually define
        unicode_name = unicodedata.name(char, None)
        glyphs_by_category[category].append(
            GlyphInfo(char=char, codepoint=codepoint, glyph_name=glyph_name,
                      unicode_name=unicode_name, category=category)
        )

    populated_order = tuple(name for name in CATEGORY_ORDER if glyphs_by_category[name])
    glyphs_by_category = {name: glyphs_by_category[name] for name in populated_order}

    result = FontInfo(
        path=Path(font_path),
        names=names,
        metrics=metrics,
        variable=variable,
        glyphs_by_category=glyphs_by_category,
        category_order=populated_order,
    )
    _font_info_cache[key] = result
    return result


def clear_cache() -> None:
    """Drop all cached FontInfo. Call when a font file is known to have
    changed on disk (not needed for a normal font-picker selection change --
    a new path just misses the cache and loads fresh)."""
    _font_info_cache.clear()


@dataclass(frozen=True)
class GlyphGeometry:
    advance_width: float
    left_side_bearing: float
    # None for a glyph with no drawable outline (e.g. a combining mark that
    # happens to have empty geometry in this font) -- there's no right edge
    # to measure a bearing or bbox from, so these stay unset rather than 0,
    # which would misreport as "touches both edges."
    right_side_bearing: float | None
    bbox: tuple[float, float, float, float] | None  # (xMin, yMin, xMax, yMax), font units
    width: float | None
    height: float | None


def glyph_geometry(font_path: Path, glyph: GlyphInfo, *, curve_segments: int = 8) -> GlyphGeometry:
    """Advance width, side bearings, and bounding box for one glyph.

    The bbox comes from `gen_modelbin.extract_glyph_contours` -- the same
    contour extraction the generation pipeline itself runs -- so the
    geometry shown in the Inspector's Reference view is the same reading of
    the glyph generation will use, not a second independent measurement
    that could quietly disagree with it.
    """
    from gen_modelbin import extract_glyph_contours  # local: see _TOOLS_DIR sys.path insert above

    contours, _units_per_em = extract_glyph_contours(glyph.glyph_name, font_path, curve_segments)

    font = TTFont(str(font_path), fontNumber=0)
    try:
        advance_width, lsb = font["hmtx"].metrics.get(glyph.glyph_name, (0, 0))
    finally:
        font.close()

    all_pts = [pt for contour in contours for pt in contour]
    if not all_pts:
        return GlyphGeometry(advance_width=advance_width, left_side_bearing=lsb,
                              right_side_bearing=None, bbox=None, width=None, height=None)

    xs = [p[0] for p in all_pts]
    ys = [p[1] for p in all_pts]
    x_min, x_max, y_min, y_max = min(xs), max(xs), min(ys), max(ys)
    width, height = x_max - x_min, y_max - y_min
    right_side_bearing = advance_width - lsb - width
    return GlyphGeometry(advance_width=advance_width, left_side_bearing=lsb,
                          right_side_bearing=right_side_bearing,
                          bbox=(x_min, y_min, x_max, y_max), width=width, height=height)
