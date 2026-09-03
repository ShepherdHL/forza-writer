"""Live-preview rendering for the Glyph Template tab: a scaled-to-fit
thumbnail of the grid a generation would produce, and a short rendered
sample of a Unicode block's actual characters.

PIL-only, Tkinter-free -- same convention as tools/font_preview.py and
tools/file_preview.py, which this reuses rather than duplicating. The one
shared home for this rendering logic, so a fix or feature here reaches
every GUI that calls it instead of needing to be re-applied per GUI (this
session already hit that exact trap once with the Glyph Template file-
naming bug, which lived as two separately-drifted copies before).
"""

from __future__ import annotations

from pathlib import Path

from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont

import font_preview
from forza_writer.glyph_template import GlyphTemplate

DEFAULT_GRID_SIZE = (640, 420)
DEFAULT_SAMPLE_SIZE = (220, 40)
DEFAULT_BG = "#101317"
DEFAULT_FG = "#e8e8e6"
_BORDER = "#3a3f46"
_LABEL = "#6b7178"
_PLACEHOLDER_FILL = "#4a4f56"
_MARGIN_FRACTION = 0.03
# Below this cell size the codepoint label / glyph placeholder text is
# skipped, not shrunk further -- past this point it's unreadable clutter
# rather than useful detail (a large Split-mode block can have hundreds of
# cells once scaled to fit a fixed preview box).
_MIN_LABEL_CELL_PX = 18
_MIN_PLACEHOLDER_CELL_PX = 10


def _placeholder(size: tuple[int, int], message: str, bg: str, fg: str) -> Image.Image:
    img = Image.new("RGB", size, bg)
    draw = ImageDraw.Draw(img)
    draw.text((8, 8), message, font=ImageFont.load_default(), fill=fg)
    return img


def _font_cmap(font_path: str | Path) -> set[str]:
    font = TTFont(str(font_path), fontNumber=0)
    try:
        return {chr(cp) for cp in (font.getBestCmap() or {})}
    finally:
        font.close()


def render_grid_preview(template: GlyphTemplate, font_path: str | Path | None,
                         text_color: str = "#e6e6e6", size: tuple[int, int] = DEFAULT_GRID_SIZE,
                         bg: str = DEFAULT_BG, fg: str = DEFAULT_FG) -> Image.Image:
    """A scaled-to-fit thumbnail of the grid `template` would produce: one
    cell per slot, a light border, its codepoint label, and either the
    traced glyph (in `text_color`, if `font_path` is given and its cmap
    covers that character) or a dim placeholder character -- matching
    `build_font_traced_overlay_svg`'s/`build_blank_overlay_svg`'s own
    fallback look in the real SVG. Cell pitch is auto-fit to `size` the
    same way `file_preview.render_ascii_grid_preview` fits its own grid,
    so the whole template is always visible regardless of how many slots
    it has. Never raises."""
    try:
        cols = max(1, template.chars_per_row)
        rows = max(1, template.row_count)
        w, h = size
        margin = min(w, h) * _MARGIN_FRACTION
        cell_px = max(1.0, min((w - 2 * margin) / cols, (h - 2 * margin) / rows))
        grid_w, grid_h = cols * cell_px, rows * cell_px
        origin_x, origin_y = (w - grid_w) / 2, (h - grid_h) / 2

        img = Image.new("RGB", size, bg)
        draw = ImageDraw.Draw(img)

        supported = _font_cmap(font_path) if font_path is not None else set()
        glyph_font = (ImageFont.truetype(str(font_path), max(6, int(cell_px * 0.6)))
                      if font_path is not None else None)
        label_font = (ImageFont.truetype(str(font_path), max(5, int(cell_px * 0.14)))
                      if font_path is not None and cell_px >= _MIN_LABEL_CELL_PX else None)

        for slot in template.slots:
            x0 = origin_x + slot.col * cell_px
            y0 = origin_y + slot.row * cell_px
            draw.rectangle([x0, y0, x0 + cell_px, y0 + cell_px], outline=_BORDER)
            if label_font is not None:
                draw.text((x0 + cell_px * 0.06, y0 + cell_px * 0.08), slot.codepoint,
                          font=label_font, fill=_LABEL)
            cx, cy = x0 + cell_px / 2, y0 + cell_px * 0.6
            if glyph_font is not None and slot.char in supported:
                draw.text((cx, cy), slot.char, font=glyph_font, fill=text_color, anchor="mm")
            elif cell_px >= _MIN_PLACEHOLDER_CELL_PX:
                fallback_font = glyph_font or ImageFont.load_default()
                draw.text((cx, cy), slot.char, font=fallback_font, fill=_PLACEHOLDER_FILL, anchor="mm")
        return img
    except Exception as exc:
        return _placeholder(size, f"couldn't render grid preview: {exc}", bg, fg)


def render_block_sample(font_path: str | Path, chars: list[str], sample_size: int = 8,
                         size: tuple[int, int] = DEFAULT_SAMPLE_SIZE,
                         bg: str = DEFAULT_BG, fg: str = DEFAULT_FG) -> Image.Image:
    """A short, space-joined sample of `chars` (the first `sample_size`),
    rendered in the font at `font_path` -- what a Unicode block actually
    looks like at a glance, for the Split-mode block checklist. Thin
    wrapper: font_preview.render_font_text already does "arbitrary string,
    auto-fit to box", which is exactly what this needs."""
    sample = " ".join(chars[:sample_size])
    return font_preview.render_font_text(font_path, sample, size, bg, fg)
