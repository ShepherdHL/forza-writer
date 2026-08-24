"""Render a font's display name in its own typeface, for the GUI's font-grid
browser (dafont/Windows-font-picker style: "see what it looks like", not
just "read its name").

Rendering an arbitrary installed font can fail for all sorts of reasons
(corrupt file, unsupported table format, a name PIL's rasterizer chokes on)
— that must never crash the grid, just degrade to a plain-text placeholder
tile for that one font.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

DEFAULT_SIZE = (180, 40)
MIN_FONT_PX = 10
MAX_FONT_PX = 22

_cache: dict[tuple, Image.Image] = {}


def _fit_font(text: str, font_path: Path, box_w: int, box_h: int) -> ImageFont.FreeTypeFont:
    """Largest font size (within MIN/MAX_FONT_PX) whose rendered text fits
    the box width, falling back to MIN_FONT_PX if even that overflows."""
    dummy = Image.new("L", (1, 1))
    draw = ImageDraw.Draw(dummy)
    for px in range(MAX_FONT_PX, MIN_FONT_PX - 1, -1):
        font = ImageFont.truetype(str(font_path), px)
        bbox = draw.textbbox((0, 0), text, font=font)
        width, height = bbox[2] - bbox[0], bbox[3] - bbox[1]
        if width <= box_w - 12 and height <= box_h - 8:
            return font
    return ImageFont.truetype(str(font_path), MIN_FONT_PX)


def render_font_name(font_path: Path, display_name: str, size: tuple[int, int] = DEFAULT_SIZE,
                      bg: str = "#101317", fg: str = "#e8e8e6") -> Image.Image:
    """Render `display_name` set in the font at `font_path`. Falls back to a
    plain placeholder tile (default font, muted text) if the font can't be
    rendered at all — never raises."""
    key = (str(font_path), display_name, size, bg, fg)
    if key in _cache:
        return _cache[key]

    w, h = size
    try:
        font = _fit_font(display_name, font_path, w, h)
        img = Image.new("RGB", size, bg)
        draw = ImageDraw.Draw(img)
        bbox = draw.textbbox((0, 0), display_name, font=font)
        text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(((w - text_w) / 2 - bbox[0], (h - text_h) / 2 - bbox[1]),
                   display_name, font=font, fill=fg)
    except Exception:
        img = _fallback_tile(display_name, size, bg, fg)

    _cache[key] = img
    return img


def render_font_text(font_path: Path, text: str, size: tuple[int, int] = (640, 150),
                     bg: str = "#101317", fg: str = "#e8e8e6") -> Image.Image:
    """Render arbitrary preview text, scaling it to the available box."""
    key = ("text", str(font_path), text, size, bg, fg)
    if key in _cache:
        return _cache[key]
    w, h = size
    try:
        dummy = Image.new("L", (1, 1))
        draw = ImageDraw.Draw(dummy)
        font = None
        for px in range(min(72, h - 16), 11, -1):
            candidate = ImageFont.truetype(str(font_path), px)
            bbox = draw.textbbox((0, 0), text, font=candidate)
            if bbox[2] - bbox[0] <= w - 24 and bbox[3] - bbox[1] <= h - 16:
                font = candidate
                break
        font = font or ImageFont.truetype(str(font_path), 12)
        img = Image.new("RGB", size, bg)
        draw = ImageDraw.Draw(img)
        bbox = draw.textbbox((0, 0), text, font=font)
        draw.text(((w - (bbox[2] - bbox[0])) / 2 - bbox[0],
                   (h - (bbox[3] - bbox[1])) / 2 - bbox[1]), text, font=font, fill=fg)
    except Exception:
        img = _fallback_tile(text, size, bg, fg)
    _cache[key] = img
    return img


def render_glyph_tile(font_path: Path, char: str, size: tuple[int, int] = (44, 44),
                      bg: str = "#101317", fg: str = "#e8e8e6") -> Image.Image:
    """Render a single glyph centered in a small square tile, for the Glyph
    Inspector's categorized browser grid. Falls back to a muted placeholder
    (matching `render_font_name`'s degrade path) if the font can't render
    this character at all -- never raises."""
    key = ("glyph", str(font_path), char, size, bg, fg)
    if key in _cache:
        return _cache[key]

    w, h = size
    try:
        px = max(8, min(w, h) - 14)
        font = ImageFont.truetype(str(font_path), px)
        img = Image.new("RGB", size, bg)
        draw = ImageDraw.Draw(img)
        draw.text((w / 2, h / 2), char, font=font, fill=fg, anchor="mm")
    except Exception:
        img = _fallback_tile(char, size, bg, fg)

    _cache[key] = img
    return img


def _fallback_tile(display_name: str, size: tuple[int, int], bg: str, fg: str) -> Image.Image:
    img = Image.new("RGB", size, bg)
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    label = display_name if len(display_name) <= 24 else display_name[:21] + "..."
    bbox = draw.textbbox((0, 0), label, font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    w, h = size
    draw.text(((w - text_w) / 2, (h - text_h) / 2), label, font=font, fill=fg)
    return img


def clear_cache() -> None:
    _cache.clear()
