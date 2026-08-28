"""Eurocorp's procedural geometric-line backdrop — a sparse network of thin
diagonal lines evoking the connective HUD graphics behind Syndicate
(2012)'s menu screens. Reuses the same technique gui_theme/apply.py's
checkbox/radio indicator glyphs already use (PIL-drawn, cached as a
PhotoImage) rather than introducing a new rendering approach — see
docs/GUI_THEME_SYSTEM.md.

Deterministic: a fixed seed means the same (width, height) always produces
the same image, so it's stable across runs and safe to snapshot-test.
"""

from __future__ import annotations

import random

from PIL import Image, ImageDraw

_SEED = 1337
_NODE_COUNT = 14
_EDGES_PER_NODE = 2
_ACCENT_LINE_COUNT = 3
_LINE_ALPHA = 60
_ACCENT_ALPHA = 130


def _rgba(hex_color: str, alpha: int) -> tuple[int, int, int, int]:
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    return (r, g, b, alpha)


def build_backdrop(size: tuple[int, int], palette: dict[str, str]) -> Image.Image:
    """Return a new RGBA image of `size` — a sparse diagonal line network
    in `palette['border']`, crossed by a few brighter `palette['accent']`
    lines. Degenerate (non-positive) sizes return a 1x1 transparent image
    rather than raising, since a caller may ask before real Tk layout has
    happened."""
    width, height = size
    if width <= 0 or height <= 0:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))

    rng = random.Random(_SEED)
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    nodes = [(rng.uniform(0, width), rng.uniform(0, height)) for _ in range(_NODE_COUNT)]
    line_color = _rgba(palette["border"], _LINE_ALPHA)
    accent_color = _rgba(palette["accent"], _ACCENT_ALPHA)

    # A sparse network, not a full mesh: each node connects only to its
    # nearest couple of later nodes, so the result reads as scattered
    # structural rails rather than a dense, noisy web.
    for index, node in enumerate(nodes):
        remaining = nodes[index + 1:]
        remaining.sort(key=lambda other: (other[0] - node[0]) ** 2 + (other[1] - node[1]) ** 2)
        for other in remaining[:_EDGES_PER_NODE]:
            draw.line([node, other], fill=line_color, width=1)

    # A few long, brighter accent lines crossing the full field top-to-
    # bottom, echoing the diagonal accent rules in the reference HUD.
    for _ in range(_ACCENT_LINE_COUNT):
        x1, x2 = rng.uniform(0, width), rng.uniform(0, width)
        draw.line([(x1, 0), (x2, height)], fill=accent_color, width=1)

    return image
