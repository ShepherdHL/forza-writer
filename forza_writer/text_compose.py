"""Compose arbitrary text into a single shape list from an already-generated
fontpack, with real per-glyph spacing (font `hmtx` advance widths) and a
shared baseline/scale across glyphs, plus left/center/right/justify
alignment.

Why this needs its own scale math, not just placing generated glyph files
side by side: `tools/gen_modelbin.py::normalize_to_128` (via
`glyph_bbox_and_scale`) normalizes each glyph *independently* to fill its
own ±100 box based on its own raw bounding box, which is exactly right for
a single centred glyph but wrong for composed text: a period (rawbbox
100x100 on Amarillo USAF) and a capital M (rawbbox 600x600) would render at
identical size. This module re-derives, per glyph, the per-glyph
centre/scale that was actually baked into its saved shapes at generation
time (`glyph_bbox_and_scale` on a fresh contour extraction; cheap, no
re-fitting), and replaces it with one shared font-wide scale
(`200 / units_per_em`) and the font's real baseline (font-space y=0),
rather than each glyph's own bbox centre.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_TOOLS_DIR = str(Path(__file__).resolve().parent.parent / "tools")
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

from fontTools.ttLib import TTFont  # noqa: E402

from gen_modelbin import extract_contours, glyph_bbox_and_scale  # noqa: E402

from forza_writer.text_style import (  # noqa: E402
    RGBA, CharPosition, TextStyle, apply_bold, apply_italic, build_bar_shape, color_for,
)

# Matches primitive_fit.COORD_RANGE / placements_to_shapes' default
# glyph_size=300.0: real_units_per_glyph_unit = glyph_size / (2*COORD_RANGE).
COORD_RANGE = 100.0
GLYPH_SIZE = 300.0
K = GLYPH_SIZE / (2 * COORD_RANGE)  # 1.5

ALIGNMENTS = ("left", "center", "right", "justify")


@dataclass(frozen=True)
class GlyphMetrics:
    cx: float           # raw font-unit bbox centre X baked into the saved shapes
    cy: float           # raw font-unit bbox centre Y baked into the saved shapes
    scale_g: float      # per-glyph normalize_to_128 scale actually used at generation time
    advance_width: float  # real hmtx advance, in font units
    units_per_em: int


@lru_cache(maxsize=None)
def _font_wide_metrics(font_path_str: str) -> tuple[int, int, int]:
    font = TTFont(font_path_str, fontNumber=0)
    try:
        units_per_em = font["head"].unitsPerEm
        ascender = font["hhea"].ascender
        descender = font["hhea"].descender
    finally:
        font.close()
    return units_per_em, ascender, descender


@lru_cache(maxsize=None)
def _underline_strike_metrics(font_path_str: str) -> tuple[float, float, float, float]:
    """(underline_pos, underline_thickness, strike_pos, strike_thickness), all
    in font units, font-space y positive upward (same convention as
    `_font_wide_metrics`'s ascender/descender) -- position is the offset from
    the baseline, thickness is the bar's height. `post.underline*` and
    `OS/2.yStrikeout*` are both optional OpenType tables; fonts missing them
    fall back to a documented approximation rather than raising."""
    font = TTFont(font_path_str, fontNumber=0)
    try:
        units_per_em = font["head"].unitsPerEm
        ascender = font["hhea"].ascender
        descender = font["hhea"].descender
        post = font.get("post")
        underline_pos = getattr(post, "underlinePosition", 0) if post else 0
        underline_thickness = getattr(post, "underlineThickness", 0) if post else 0
        os2 = font.get("OS/2")
        strike_pos = getattr(os2, "yStrikeoutPosition", 0) if os2 else 0
        strike_thickness = getattr(os2, "yStrikeoutSize", 0) if os2 else 0
    finally:
        font.close()

    if not underline_pos:
        underline_pos = descender / 2.0
    if not underline_thickness:
        underline_thickness = units_per_em * 0.05
    if not strike_pos:
        strike_pos = ascender * 0.3
    if not strike_thickness:
        strike_thickness = units_per_em * 0.05
    return underline_pos, underline_thickness, strike_pos, strike_thickness


@lru_cache(maxsize=None)
def _glyph_layout_metrics(char: str, font_path_str: str, curve_segments: int) -> GlyphMetrics:
    """Recover the exact per-glyph centre/scale `normalize_to_128` applied
    when this glyph's shapes were generated, plus its real advance width, by
    re-extracting the glyph's raw contours (cheap; no re-fitting)."""
    font_path = Path(font_path_str)
    contours, units_per_em = extract_contours(char, font_path, curve_segments)
    cx, cy, scale_g = glyph_bbox_and_scale(contours)

    font = TTFont(font_path_str, fontNumber=0)
    try:
        cmap = font.getBestCmap()
        glyph_name = cmap[ord(char)]
        advance_width = font["hmtx"].metrics[glyph_name][0]
    finally:
        font.close()

    return GlyphMetrics(cx=cx, cy=cy, scale_g=scale_g, advance_width=advance_width,
                         units_per_em=units_per_em)


@lru_cache(maxsize=None)
def _glyph_name_layout_metrics(glyph_name: str, font_path_str: str,
                               curve_segments: int) -> GlyphMetrics:
    """Normalization metrics for a glyph identity returned by HarfBuzz."""
    from gen_modelbin import extract_glyph_contours

    contours, units_per_em = extract_glyph_contours(
        glyph_name, Path(font_path_str), curve_segments)
    cx, cy, scale_g = glyph_bbox_and_scale(contours)
    font = TTFont(font_path_str, fontNumber=0)
    try:
        advance_width = font["hmtx"].metrics.get(glyph_name, (0, 0))[0]
    finally:
        font.close()
    return GlyphMetrics(cx, cy, scale_g, advance_width, units_per_em)


@lru_cache(maxsize=None)
def _cmap_and_hmtx(font_path_str: str):
    font = TTFont(font_path_str, fontNumber=0)
    try:
        cmap = font.getBestCmap()
        hmtx = {name: metrics[0] for name, metrics in font["hmtx"].metrics.items()}
    finally:
        font.close()
    return cmap, hmtx


def _fallback_advance_width(char: str, font_path_str: str, units_per_em: int) -> float:
    """Best-effort advance width for a character with no generated glyph
    (used so a missing/unavailable char still occupies roughly sane space
    rather than collapsing the rest of the line onto it)."""
    cmap, hmtx = _cmap_and_hmtx(font_path_str)
    glyph_name = cmap.get(ord(char))
    if glyph_name is not None and glyph_name in hmtx:
        return hmtx[glyph_name]
    return units_per_em / 2.0


@dataclass
class _Token:
    char: str
    shapes: list[dict]  # correction + baseline applied; NOT yet cursor-translated
    advance: float       # real FH6 units
    is_space: bool


def _load_glyph_shapes(char: str, fontpack_dir: Path, rel_path: str) -> list[dict]:
    file_path = fontpack_dir / rel_path
    data = json.loads(file_path.read_text(encoding="utf-8"))
    return data["shapes"]


def _correct_generated_shapes(char: str, raw_shapes: list[dict], font_path_str: str,
                              curve_segments: int, scale_font: float,
                              line_offset: float) -> tuple[list[dict], float]:
    """Undo per-glyph normalization and apply the shared font baseline."""
    metrics = _glyph_layout_metrics(char, font_path_str, curve_segments)
    correction = scale_font / metrics.scale_g
    x_offset = metrics.cx * scale_font * K
    y_offset = -metrics.cy * scale_font * K + line_offset
    shapes = []
    for shape in raw_shapes:
        data = shape["data"]
        shapes.append({**shape, "data": [
            data[0] * correction + x_offset,
            data[1] * correction + y_offset,
            data[2] * correction,
            data[3] * correction,
            data[4], data[5], data[6],
        ]})
    return shapes, metrics.advance_width * scale_font * K


def _correct_shaped_glyph(glyph_name: str, raw_shapes: list[dict], font_path_str: str,
                          curve_segments: int, scale_font: float,
                          x_offset_font: float, y_offset_font: float,
                          line_offset: float) -> list[dict]:
    metrics = _glyph_name_layout_metrics(glyph_name, font_path_str, curve_segments)
    correction = scale_font / metrics.scale_g
    x_offset = (metrics.cx + x_offset_font) * scale_font * K
    # Font/HarfBuzz y is positive upward; exported editor y is positive down.
    y_offset = -(metrics.cy + y_offset_font) * scale_font * K + line_offset
    return [
        {**shape, "data": [
            shape["data"][0] * correction + x_offset,
            shape["data"][1] * correction + y_offset,
            shape["data"][2] * correction,
            shape["data"][3] * correction,
            *shape["data"][4:],
        ]}
        for shape in raw_shapes
    ]


def _build_token(char: str, fontpack_dir: Path, rel_path: str | None,
                  font_path_str: str, curve_segments: int,
                  scale_font: float, line_offset: float,
                  warnings: list[str]) -> _Token:
    if char.isspace():
        units_per_em = _font_wide_metrics(font_path_str)[0]
        advance = _fallback_advance_width(char, font_path_str, units_per_em) * scale_font * K
        return _Token(char=char, shapes=[], advance=advance, is_space=True)

    if rel_path is None:
        units_per_em = _font_wide_metrics(font_path_str)[0]
        msg = f"{char!r} has no generated glyph in this fontpack — skipped"
        if msg not in warnings:
            warnings.append(msg)
        advance = _fallback_advance_width(char, font_path_str, units_per_em) * scale_font * K
        return _Token(char=char, shapes=[], advance=advance, is_space=False)

    raw_shapes = _load_glyph_shapes(char, fontpack_dir, rel_path)
    shapes, advance = _correct_generated_shapes(
        char, raw_shapes, font_path_str, curve_segments, scale_font, line_offset)
    return _Token(char=char, shapes=shapes, advance=advance, is_space=False)


def compose_shape_map(text: str, font_path: str | Path,
                      shape_map: dict[str, list[dict]], *, curve_segments: int = 8,
                      align: str = "left", letter_spacing: float = 0.0,
                      size_scale: float = 1.0, line_spacing: float = 1.0,
                      style: TextStyle | None = None
                      ) -> tuple[list[dict], list[str]]:
    """Compose in-memory generated glyphs without creating a fontpack."""
    if align not in ALIGNMENTS:
        raise ValueError(f"align must be one of {ALIGNMENTS}, got {align!r}")
    font_path_str = str(font_path)
    units_per_em, ascender, descender = _font_wide_metrics(font_path_str)
    scale_font = 200.0 / units_per_em * size_scale
    line_height = (ascender - descender) * scale_font * K * line_spacing
    warnings: list[str] = []
    lines: list[list[_Token]] = []
    for line_index, line_text in enumerate(text.split("\n")):
        line_offset = line_index * line_height
        tokens = []
        for char in line_text:
            if char.isspace():
                advance = _fallback_advance_width(char, font_path_str, units_per_em) * scale_font * K
                tokens.append(_Token(char, [], advance, True))
            elif char not in shape_map:
                message = f"{char!r} could not be generated — skipped"
                if message not in warnings:
                    warnings.append(message)
                advance = _fallback_advance_width(char, font_path_str, units_per_em) * scale_font * K
                tokens.append(_Token(char, [], advance, False))
            else:
                shapes, advance = _correct_generated_shapes(
                    char, shape_map[char], font_path_str, curve_segments, scale_font, line_offset)
                tokens.append(_Token(char, shapes, advance, False))
        lines.append(tokens)
    shapes = _place_lines(lines, align, letter_spacing, style, font_path_str, scale_font, line_height)
    return shapes, warnings


def compose_shaped_lines(shaped_lines, font_path: str | Path,
                         shape_map: dict[str, list[dict]], *,
                         curve_segments: int = 8, align: str = "left",
                         letter_spacing: float = 0.0,
                         size_scale: float = 1.0, line_spacing: float = 1.0,
                         style: TextStyle | None = None
                         ) -> tuple[list[dict], list[str]]:
    """Compose HarfBuzz-positioned glyphs while retaining reusable fits."""
    if align not in ALIGNMENTS:
        raise ValueError(f"align must be one of {ALIGNMENTS}, got {align!r}")
    font_path_str = str(font_path)
    units_per_em, ascender, descender = _font_wide_metrics(font_path_str)
    scale_font = 200.0 / units_per_em * size_scale
    line_height = (ascender - descender) * scale_font * K * line_spacing
    warnings: list[str] = []
    lines: list[list[_Token]] = []
    for line_index, shaped_line in enumerate(shaped_lines):
        line_offset = line_index * line_height
        tokens: list[_Token] = []
        for glyph in shaped_line.glyphs:
            advance = glyph.x_advance * scale_font * K
            raw_shapes = shape_map.get(glyph.glyph_name, [])
            if glyph.glyph_name == ".notdef":
                message = f"{glyph.source_text!r} shaped to the font's missing glyph — skipped"
                if message not in warnings:
                    warnings.append(message)
            corrected = (_correct_shaped_glyph(
                glyph.glyph_name, raw_shapes, font_path_str, curve_segments,
                scale_font, glyph.x_offset, glyph.y_offset, line_offset)
                if raw_shapes else [])
            tokens.append(_Token(
                glyph.source_text, corrected, advance,
                not raw_shapes and glyph.source_text.isspace()))
        lines.append(tokens)
    shapes = _place_lines(lines, align, letter_spacing, style, font_path_str, scale_font, line_height)
    return shapes, warnings


def _place_lines(lines: list[list[_Token]], align: str, letter_spacing: float,
                 style: TextStyle | None, font_path_str: str, scale_font: float,
                 line_height: float) -> list[dict]:
    """Place corrected tokens, then apply fill color / bold / italic /
    underline / strikethrough (forza_writer.text_style) on top if a
    non-default style was requested. `style=None` (or a no-op TextStyle())
    skips all of that and reproduces this function's pre-styling output
    exactly. Kept as the single shared placement routine for fontpack-based,
    HarfBuzz-based, and direct-fontpack composition."""
    style = style or TextStyle()

    def line_width(tokens: list[_Token]) -> float:
        if not tokens:
            return 0.0
        return sum(t.advance for t in tokens) + letter_spacing * max(0, len(tokens) - 1)

    line_widths = [line_width(tokens) for tokens in lines]
    max_line_width = max(line_widths, default=0.0)
    line_count = len(lines)

    underline_metrics = strike_metrics = None
    if style.underline or style.strikethrough:
        u_pos, u_thick, s_pos, s_thick = _underline_strike_metrics(font_path_str)
        underline_metrics = (u_pos * scale_font * K, abs(u_thick) * scale_font * K)
        strike_metrics = (s_pos * scale_font * K, abs(s_thick) * scale_font * K)

    all_shapes: list[dict] = []
    for line_index, tokens in enumerate(lines):
        width = line_widths[line_index]
        is_last_line = line_index == line_count - 1
        deficit = max_line_width - width
        shift = space_extra = char_extra = 0.0
        if align == "right":
            shift = deficit
        elif align == "center":
            shift = deficit / 2.0
        elif align == "justify" and not (is_last_line and line_count > 1):
            space_gaps = sum(1 for token in tokens if token.is_space)
            if space_gaps:
                space_extra = deficit / space_gaps
            elif len(tokens) > 1:
                char_extra = deficit / (len(tokens) - 1)

        chars_in_line = len(tokens)
        fill = style.fill_for_line(line_index)
        line_first_color: RGBA | None = None
        x = 0.0
        for index, token in enumerate(tokens):
            color = None
            if token.shapes and not fill.is_noop:
                pos = CharPosition(index_in_line=index, chars_in_line=chars_in_line)
                color = color_for(fill, pos)
                if line_first_color is None:
                    line_first_color = color
            for shape in token.shapes:
                data = shape["data"]
                placed = {**shape, "data": [data[0] + x + shift, data[1], *data[2:]]}
                if style.bold:
                    placed = apply_bold(placed)
                if style.italic:
                    placed = apply_italic(placed)
                if color is not None and not placed.get("mask"):
                    placed = {**placed, "color": list(color)}
                all_shapes.append(placed)
            advance = token.advance + (space_extra if token.is_space else 0.0)
            if char_extra and not token.is_space and index < len(tokens) - 1:
                advance += char_extra
            x += advance + letter_spacing

        if (style.underline or style.strikethrough) and line_first_color is not None:
            content_width = max(0.0, x - letter_spacing)
            line_offset = line_index * line_height
            for enabled, metrics in (
                (style.underline, underline_metrics), (style.strikethrough, strike_metrics),
            ):
                if not enabled:
                    continue
                position, thickness = metrics
                y_center = -position + line_offset
                all_shapes.append(build_bar_shape(
                    shift, shift + content_width, y_center, thickness, line_first_color))
    return all_shapes


def compose_text(text: str, fontpack_dir: str | Path, align: str = "left",
                  letter_spacing: float = 0.0, size_scale: float = 1.0,
                  line_spacing: float = 1.0, style: TextStyle | None = None
                  ) -> tuple[list[dict], list[str]]:
    """Compose `text` (may contain `\\n` line breaks, no auto-wrap) into one
    shape list using the glyphs already generated in `fontpack_dir` (a
    directory containing `manifest.json`, as produced by
    `tools/gen_fontpack.py::build_fontpack`).

    `style` (forza_writer.text_style.TextStyle) applies fill color/bold/
    italic/underline/strikethrough on top of the base layout; left as None
    (or an unstyled `TextStyle()`) for byte-identical output to before
    styling existed.

    Returns `(shapes, warnings)`. Characters with no generated `.json`
    artifact are skipped (not raised) and recorded in `warnings`, matching
    this project's established `skipped`-list convention.
    """
    if align not in ALIGNMENTS:
        raise ValueError(f"align must be one of {ALIGNMENTS}, got {align!r}")

    fontpack_dir = Path(fontpack_dir)
    manifest = json.loads((fontpack_dir / "manifest.json").read_text(encoding="utf-8"))
    font_path_str = manifest["font_file"]
    curve_segments = manifest.get("curve_segments", 8)

    rel_path_by_char: dict[str, str] = {}
    for entries in manifest["categories"].values():
        for entry in entries:
            json_artifact = entry.get("artifacts", {}).get("json")
            if json_artifact and json_artifact.get("file"):
                rel_path_by_char[entry["char"]] = json_artifact["file"]

    units_per_em, ascender, descender = _font_wide_metrics(font_path_str)
    scale_font = 200.0 / units_per_em * size_scale
    line_height = (ascender - descender) * scale_font * K * line_spacing

    warnings: list[str] = []
    lines_raw = text.split("\n")
    lines: list[list[_Token]] = []
    for line_index, line_text in enumerate(lines_raw):
        line_offset = line_index * line_height
        tokens = [
            _build_token(char, fontpack_dir, rel_path_by_char.get(char), font_path_str,
                         curve_segments, scale_font, line_offset, warnings)
            for char in line_text
        ]
        lines.append(tokens)

    shapes = _place_lines(lines, align, letter_spacing, style, font_path_str, scale_font, line_height)
    return shapes, warnings
