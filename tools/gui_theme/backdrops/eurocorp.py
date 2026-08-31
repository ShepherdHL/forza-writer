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

import math
import random

from PIL import Image, ImageDraw

_SEED = 1337
_NODE_COUNT = 14
_EDGES_PER_NODE = 2
_ACCENT_LINE_COUNT = 3
_LINE_ALPHA = 60
_ACCENT_ALPHA = 130

# A second, independent seed for node drift velocities -- kept out of the
# main `_SEED` random stream entirely so build_backdrop_frames' frame 0 is
# pixel-identical to build_backdrop's own output (same node positions, same
# accent lines, drawn in the same order from the same draws).
_VELOCITY_SEED = 4111
_ANIMATION_FRAME_COUNT = 12
_DRIFT_SPEED = 0.6  # px/frame step -- slow ambient drift, not a flourish


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


def build_backdrop_frames(size: tuple[int, int], palette: dict[str, str],
                           n_frames: int = _ANIMATION_FRAME_COUNT) -> list[Image.Image]:
    """A flip-book of `n_frames` backdrop variants for a slow, continuous-
    looking drift animation -- frame 0 is pixel-identical to
    `build_backdrop`'s own output (same node positions, same accent lines),
    each subsequent frame nudges every node a small fixed step along its
    own seeded drift velocity, wrapping at the edges. The nearest-neighbor
    mesh is recomputed per frame from the moved positions (same rule
    `build_backdrop` uses), so connectivity drifts smoothly along with the
    nodes rather than jumping between arbitrarily different pairings.

    Accent lines and the degenerate-size fallback deliberately don't move
    or get overridden -- their glow/bloom-adjacent role in the wider design
    (see the HTML mockup this ports from) doesn't apply to this narrow
    sidebar strip, so this stays a direct animation of the existing static
    backdrop rather than introducing new visual elements.

    Callers own displaying this as an animation (a repeating Tk `after()`
    loop mutating one persistent PhotoImage via `.paste()` per tick) --
    this function only ever computes pixels, matching every other builder
    in this module.
    """
    width, height = size
    if width <= 0 or height <= 0:
        return [Image.new("RGBA", (1, 1), (0, 0, 0, 0))]

    rng = random.Random(_SEED)
    node_positions = [(rng.uniform(0, width), rng.uniform(0, height)) for _ in range(_NODE_COUNT)]
    line_color = _rgba(palette["border"], _LINE_ALPHA)
    accent_color = _rgba(palette["accent"], _ACCENT_ALPHA)
    accent_lines = [
        ((rng.uniform(0, width), 0), (rng.uniform(0, width), height))
        for _ in range(_ACCENT_LINE_COUNT)
    ]

    velocity_rng = random.Random(_VELOCITY_SEED)
    velocities = []
    for _ in range(_NODE_COUNT):
        angle = velocity_rng.uniform(0, 2 * math.pi)
        velocities.append((math.cos(angle) * _DRIFT_SPEED, math.sin(angle) * _DRIFT_SPEED))

    frames = []
    for frame_index in range(max(1, n_frames)):
        nodes = [
            ((x + vx * frame_index) % width, (y + vy * frame_index) % height)
            for (x, y), (vx, vy) in zip(node_positions, velocities)
        ]
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        for index, node in enumerate(nodes):
            remaining = nodes[index + 1:]
            remaining.sort(key=lambda other: (other[0] - node[0]) ** 2 + (other[1] - node[1]) ** 2)
            for other in remaining[:_EDGES_PER_NODE]:
                draw.line([node, other], fill=line_color, width=1)
        for start, end in accent_lines:
            draw.line([start, end], fill=accent_color, width=1)
        frames.append(image)

    return frames
