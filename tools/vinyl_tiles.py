"""Render one vinyl-shape tile for the Generator tab's shape picker.

The whole tile — background, border, silhouette, caption, preferred badge —
is drawn as a single PIL image rather than assembled from Tk widgets. Tk's
canvas has no rounded rectangle and no way to tint a bitmap, so building the
tile here keeps the three states visually distinct and, more usefully, makes
the picker's appearance testable without constructing a GUI at all.

The silhouettes are `primitive_shapes.PRIMITIVE_CATALOG`'s own masks, not
separate artwork: what a tile shows is exactly the shape the fitter searches
with, so a wrong-looking tile means a wrong shape, not a wrong icon.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from forza_writer.primitive_shapes import PrimitiveShape  # noqa: E402

TILE_W = 104
TILE_H = 86
THUMB = 46
BADGE_R = 8          # preferred-star badge radius
BADGE_INSET = 13     # badge centre, in from the tile's top-right corner

# The three states a shape can be in. "preferred" implies allowed — the policy
# rejects preferring a disabled shape, so there is no fourth combination.
STATES = ("off", "on", "preferred")


def badge_hit(x: float, y: float) -> bool:
    """Whether a click at tile-local (x, y) landed on the preferred badge.

    Kept next to the drawing code on purpose: the badge is painted into the
    tile bitmap, so its hit area only stays correct if it is derived from the
    same constants that positioned it.
    """
    cx, cy = TILE_W - BADGE_INSET, BADGE_INSET
    return (x - cx) ** 2 + (y - cy) ** 2 <= (BADGE_R + 2) ** 2


def _font(size: int, bold: bool = False):
    for name in (("segoeuib.ttf" if bold else "segoeui.ttf"), "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _silhouette(shape: PrimitiveShape, fill: str, size: int = THUMB) -> Image.Image:
    mask = Image.fromarray((shape.mask * 255).astype(np.uint8), mode="L")
    mask = mask.resize((size, size), Image.LANCZOS)
    tinted = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    tinted.paste(Image.new("RGBA", (size, size), fill), (0, 0), mask)
    return tinted


def _fit_caption(draw, text: str, font, max_width: int) -> str:
    if draw.textlength(text, font=font) <= max_width:
        return text
    while len(text) > 4 and draw.textlength(text + "…", font=font) > max_width:
        text = text[:-1]
    return text + "…"


def render_tile(shape: PrimitiveShape, state: str, palette: dict) -> Image.Image:
    """One tile in the given state, using the live theme palette.

    Disabled tiles keep a visible (greyed) silhouette rather than being
    blanked: you have to be able to see what you switched off in order to
    switch it back on.
    """
    if state not in STATES:
        raise ValueError(f"state must be one of {STATES}, got {state!r}")

    accent = palette["accent"]
    image = Image.new("RGB", (TILE_W, TILE_H), palette["panel_alt"])
    draw = ImageDraw.Draw(image, "RGBA")
    box = [0, 0, TILE_W - 1, TILE_H - 1]

    if state == "off":
        draw.rounded_rectangle(box, 6, fill=palette["bg"], outline=palette["border"], width=1)
        silhouette_fill = caption_fill = palette["disabled_fg"]
    elif state == "preferred":
        draw.rounded_rectangle(box, 6, fill=palette["frame_light"], outline=accent, width=2)
        silhouette_fill, caption_fill = accent, palette["fg"]
    else:
        draw.rounded_rectangle(box, 6, fill=palette["frame_light"],
                               outline=palette["border"], width=1)
        silhouette_fill = caption_fill = palette["fg"]

    thumb = _silhouette(shape, silhouette_fill)
    image.paste(thumb, ((TILE_W - THUMB) // 2, 8), thumb)

    caption_font = _font(11)
    caption = _fit_caption(draw, shape.display_name, caption_font, TILE_W - 10)
    draw.text((TILE_W / 2, TILE_H - 15), caption, font=caption_font,
              fill=caption_fill, anchor="ma")

    if state == "preferred":
        cx, cy = TILE_W - BADGE_INSET, BADGE_INSET
        draw.ellipse([cx - BADGE_R, cy - BADGE_R, cx + BADGE_R, cy + BADGE_R], fill=accent)
        # Drawn rather than typed: the ★ character is missing from several
        # common Windows UI fonts and falls back to a tofu box.
        points = []
        for i in range(10):
            radius = 5.2 if i % 2 == 0 else 2.2
            angle = math.radians(-90 + i * 36)
            points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
        draw.polygon(points, fill=palette["bg"])

    return image
