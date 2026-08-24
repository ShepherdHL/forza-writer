"""Large reference-glyph renderer for the Glyph Inspector's Reference view:
the character drawn at large scale directly from the font's own outline,
with font metric guide lines (ascender/cap-height/x-height/baseline/
descender) behind it.

This is deliberately the *only* renderer for "what the font says this
glyph looks like". Glyph Inspector's Generated view (the real generation
pipeline's own output) and Compare view (a diff against it) draw separate
images via `tools.file_preview.render_json_preview` and
`forza_writer.glyph_quality`'s mask/overlay helpers instead of this
module's baseline-aligned convention -- they're each their own
self-contained canvas (glyph-centered, resolution-based), not pixel
-registered against this Reference view's metric-guide layout. Overlaying
Reference directly against Generated/Compare pixel-for-pixel would need a
shared coordinate system this module doesn't provide today.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

MARGIN = 28
LABEL_COLUMN_WIDTH = 116  # room for e.g. "Cap Height  700" at the right edge


def render_glyph_reference(font_path: Path, char: str, size: tuple[int, int], *,
                            units_per_em: int, ascender: int, descender: int,
                            cap_height: int | None, x_height: int | None,
                            bg: str, fg: str, guide_color: str, label_color: str) -> Image.Image:
    """Render `char` from `font_path` at the largest size that fits the
    ascender-to-descender span, with a horizontal guide line + numeric
    label for whichever metrics the font actually provides (missing
    metrics are simply skipped, never invented). Falls back to a muted
    placeholder if the glyph can't be rendered at all -- never raises."""
    w, h = size
    available_h = max(20, h - 2 * MARGIN)
    span = max(1, ascender - min(descender, 0))
    scale = available_h / span
    px = max(8, int(scale * units_per_em))
    # Recompute the real scale from the integer px actually used, so the
    # guide lines and the glyph (rendered at that rounded px size) agree
    # exactly rather than drifting by the rounding error.
    scale = px / units_per_em

    baseline_y = MARGIN + ascender * scale
    center_x = (w - LABEL_COLUMN_WIDTH) / 2

    img = Image.new("RGB", size, bg)
    draw = ImageDraw.Draw(img)

    def guide(value: int, label: str) -> None:
        y = baseline_y - value * scale
        if y < 1 or y > h - 1:
            return
        draw.line([(0, y), (w - LABEL_COLUMN_WIDTH, y)], fill=guide_color, width=1)
        draw.text((w - LABEL_COLUMN_WIDTH + 8, y), f"{label}  {value}",
                   fill=label_color, anchor="lm")

    guide(ascender, "Ascender")
    if cap_height:
        guide(cap_height, "Cap Height")
    if x_height:
        guide(x_height, "x-height")
    guide(0, "Baseline")
    guide(descender, "Descender")

    try:
        font = ImageFont.truetype(str(font_path), px)
        draw.text((center_x, baseline_y), char, font=font, fill=fg, anchor="ms")
    except Exception:
        draw.text((center_x, baseline_y), "?", fill=fg, anchor="ms")

    return img
