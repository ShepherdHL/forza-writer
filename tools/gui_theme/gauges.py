"""Palette-aware PIL renderers for Glyph Inspector's Compare-mode focus
readout: a ring/donut gauge for percentage metrics (IoU, boundary F1) and
a two-row count "pill" for exact-count metrics (components, holes).

Colors always come from the active palette's own tokens (never a hardcoded
hex), so this reads correctly across Charcoal, Slate, and Eurocorp alike:
generated = `success`, target/expected = `secondary_accent`, and a
shortfall (generated short of expected) = `danger`. For the ring gauge
specifically there is deliberately no invented numeric "danger" threshold
for IoU/boundary F1 -- forza_writer.glyph_quality.compare_masks() doesn't
supply one, and manufacturing one here would be fabricating behavior the
underlying data doesn't support. The ring only ever shows generated-vs-
target visually; overall pass/review comes from compare_masks()'s own
`verdict` field, surfaced in Glyph Inspector's ledger instead.
"""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont


def _rgba(hex_color: str, alpha: int = 255) -> tuple[int, int, int, int]:
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    return (r, g, b, alpha)


def _centered_text(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str,
                    font: ImageFont.ImageFont, fill: tuple[int, int, int, int]) -> None:
    x0, y0, x1, y1 = box
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((x0 + (x1 - x0 - tw) / 2 - bbox[0], y0 + (y1 - y0 - th) / 2 - bbox[1]),
              text, font=font, fill=fill)


def render_ring_gauge(value: float, size: int, palette: dict[str, str]) -> Image.Image:
    """A `size`x`size` donut: a full-circle target track in
    `palette['secondary_accent']`, with a `value`-fraction arc (0.0-1.0)
    drawn over it in `palette['success']`, and the percentage centered.
    """
    value = max(0.0, min(1.0, value))
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    stroke = max(4, size // 14)
    pad = stroke // 2 + 2
    bbox = (pad, pad, size - pad, size - pad)
    draw.arc(bbox, start=0, end=360, fill=_rgba(palette["secondary_accent"]), width=stroke)
    if value > 0:
        draw.arc(bbox, start=-90, end=-90 + value * 360, fill=_rgba(palette["success"]), width=stroke)
    font = ImageFont.load_default()
    _centered_text(draw, (0, 0, size, size), f"{value * 100:.1f}%", font, _rgba(palette["fg"]))
    return image


def render_count_pill(generated: int, expected: int, size: tuple[int, int],
                       palette: dict[str, str]) -> Image.Image:
    """A two-row pill: the generated count (top, `success`) over the
    expected count (bottom, `secondary_accent`), each with a row of small
    pictogram dots. A small `danger`-colored flag appears in the corner
    when `generated < expected` -- an exact-integer comparison, not a
    fabricated threshold, so this is always well-defined."""
    width, height = size
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    half = height // 2
    radius = min(24, half // 2)
    success = _rgba(palette["success"])
    target = _rgba(palette["secondary_accent"])
    font = ImageFont.load_default()

    draw.rounded_rectangle((1, 1, width - 2, half - 2), radius=radius, outline=success, width=2)
    draw.rounded_rectangle((1, half + 1, width - 2, height - 2), radius=radius, outline=target, width=2)

    draw.text((14, half // 2 - 8), str(generated), font=font, fill=success)
    draw.text((14, half + half // 2 - 8), str(expected), font=font, fill=target)

    dot_r = 5
    gap = 6
    start_x = 54
    for i in range(max(generated, expected)):
        cx = start_x + i * (dot_r * 2 + gap)
        if cx + dot_r > width - 10:
            break  # more icons than fit -- the numeral above is still exact
        if i < generated:
            draw.ellipse((cx - dot_r, half // 2 - dot_r, cx + dot_r, half // 2 + dot_r), fill=success)
        if i < expected:
            draw.ellipse((cx - dot_r, half + half // 2 - dot_r, cx + dot_r, half + half // 2 + dot_r),
                         outline=target, width=2)

    if generated < expected:
        flag = _rgba(palette["danger"])
        draw.ellipse((width - 16, 2, width - 2, 16), fill=flag)

    return image
