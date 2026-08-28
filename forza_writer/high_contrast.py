"""Curated high-contrast palette and deterministic per-shape color
assignment for Main Generator's "High Contrast" color mode -- lets a user
tell FH6's individual primitive shapes apart at a glance in KFPS Fabric
Editor, where every shape composing a letter would otherwise be the same
flat solid color and effectively unselectable by eye.
"""

from __future__ import annotations

import random

RGBA = tuple[int, int, int, int]

# A curated categorical palette, not raw random RGB: each entry chosen for
# strong pairwise hue/lightness separation so two shapes assigned different
# entries never read as "yeah I guess that's kind of a different color".
# Loosely modeled on established qualitative palettes built for exactly this
# (Kelly's 22 colors of maximum contrast / Tableau's categorical sets),
# trimmed to entries that stay legible against both this app's own preview
# background and FH6's in-game/editor canvases.
HIGH_CONTRAST_PALETTE: tuple[RGBA, ...] = (
    (230, 25, 75, 255),    # red
    (60, 180, 75, 255),    # green
    (255, 225, 25, 255),   # yellow
    (0, 130, 200, 255),    # blue
    (245, 130, 48, 255),   # orange
    (145, 30, 180, 255),   # purple
    (70, 240, 240, 255),   # cyan
    (240, 50, 230, 255),   # magenta
    (210, 245, 60, 255),   # lime
    (250, 190, 212, 255),  # pink
    (0, 128, 128, 255),    # teal
    (220, 190, 255, 255),  # lavender
    (170, 110, 40, 255),   # brown
    (255, 250, 200, 255),  # cream
    (128, 0, 0, 255),      # maroon
    (170, 255, 195, 255),  # mint
    (128, 128, 0, 255),    # olive
    (255, 215, 180, 255),  # apricot
    (0, 0, 128, 255),      # navy
    (128, 128, 128, 255),  # gray
)

# Shape centers live in the fixed ±100 glyph-space primitive_fit.py already
# uses (COORD_RANGE), independent of resolution/glyph_size -- a typical
# letterform spans that whole ~200-unit range, so two shape centers within
# this distance of each other are close enough to read as touching/adjacent
# once actually rendered.
DEFAULT_ADJACENCY_RADIUS = 30.0


def assign_high_contrast_colors(
    centers: list[tuple[float, float]], seed: int,
    adjacency_radius: float = DEFAULT_ADJACENCY_RADIUS,
) -> list[RGBA]:
    """One color per entry in `centers`, deterministic for a given
    (centers, seed): the same shape layout and seed always produce the same
    colors, so regenerating the same glyph never shuffles them.

    Greedily avoids giving two shapes within `adjacency_radius` of each
    other the same palette entry -- a real spatial-proximity check against
    each shape's actual placement, not just "the previous shape in fitting
    order", since fitting order doesn't reliably track visual adjacency.
    Degenerates gracefully (reuses an entry) only when a shape has more
    same-radius neighbors than the palette has colors.
    """
    rng = random.Random(seed)
    palette = list(HIGH_CONTRAST_PALETTE)
    rng.shuffle(palette)
    radius_sq = adjacency_radius * adjacency_radius

    assigned: list[int] = []
    for i, (xi, yi) in enumerate(centers):
        used = set()
        for j in range(i):
            xj, yj = centers[j]
            dx, dy = xi - xj, yi - yj
            if dx * dx + dy * dy <= radius_sq:
                used.add(assigned[j])
        start = (seed + i) % len(palette)
        choice = start
        for k in range(len(palette)):
            candidate = (start + k) % len(palette)
            if candidate not in used:
                choice = candidate
                break
        assigned.append(choice)
    return [palette[idx] for idx in assigned]


def seed_for_char(base_seed: int, char: str) -> int:
    """Per-glyph seed derived from a batch's base seed: deterministic per
    character (regenerating the same char with the same base seed always
    reproduces the same shape colors) without carrying state between
    glyphs during a batch, and without every glyph in a batch collapsing
    onto the exact same shuffled palette order."""
    return (base_seed * 1_000_003 + ord(char)) & 0xFFFFFFFF
