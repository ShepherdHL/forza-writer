"""Per-glyph text integration for the Layered Glyph Effects engine.

`forza_writer/text_compose.py::compose_shape_map` already accepts a plain
`shape_map: dict[char, list[dict]]` and derives each glyph's position
correction from that glyph's *own* original contours
(`_correct_generated_shapes` -> `_glyph_layout_metrics`) -- it never
inspects the shapes it's given beyond their `data`/`color`/`mask` fields.
Since `layered_effects.generate_layered_glyph` builds every derived layer's
shapes in the same normalized ±100 glyph space the original glyph's own
contours live in (insets/outsets/etc. are applied directly in that space,
before `primitive_fit.fit_placements`), a flattened multi-layer shape list
is just as valid an input to `compose_shape_map` as a single-fit shape list
-- so multi-character and multiline text (spacing, alignment, line height)
all come from the existing, unmodified composition pipeline for free. This
is deliberately the "Per Glyph" mode the spec asks be implemented first
(each glyph gets its own independently-resolved layer stack before layout);
a future "Whole Text Object" mode would instead union/lay out contours
*before* handing them to `layered_effects`, and can be added as a sibling
function here without touching this one.
"""

from __future__ import annotations

import sys
from pathlib import Path

_TOOLS_DIR = str(Path(__file__).resolve().parent.parent / "tools")
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)
from gen_modelbin import extract_contours, normalize_to_128  # noqa: E402  local: see _TOOLS_DIR sys.path insert above

from forza_writer.generation_policy import GenerationPolicy
from forza_writer.layered_effects import LayerShapeGroup, LayerStack, flatten_layer_groups, generate_layered_glyph
from forza_writer.text_compose import ALIGNMENTS, compose_shape_map
from forza_writer.text_style import TextStyle


def build_layered_shape_map(
    text: str,
    font_path: str | Path,
    stack: LayerStack,
    *,
    curve_segments: int = 8,
    policy: GenerationPolicy | None = None,
    compute_backend: str = "cpu",
) -> tuple[dict[str, list[dict]], dict[str, list[LayerShapeGroup]]]:
    """Resolve `stack` independently against every distinct non-space
    character in `text`, once each (repeated characters reuse the same
    result). Returns `(shape_map, groups_by_char)`: `shape_map` is ready to
    pass straight to `text_compose.compose_shape_map`; `groups_by_char`
    keeps each character's un-flattened per-layer groups (with `status`/
    `warning`) for GUI inspection/preview use."""
    font_path = Path(font_path)
    shape_map: dict[str, list[dict]] = {}
    groups_by_char: dict[str, list[LayerShapeGroup]] = {}
    for char in dict.fromkeys(c for c in text if not c.isspace()):
        contours, units_per_em = extract_contours(char, font_path, curve_segments)
        norm = normalize_to_128(contours, units_per_em)
        groups = generate_layered_glyph(norm, stack, policy=policy, compute_backend=compute_backend)
        groups_by_char[char] = groups
        shape_map[char] = flatten_layer_groups(groups)
    return shape_map, groups_by_char


def compose_layered_text(
    text: str,
    font_path: str | Path,
    stack: LayerStack,
    *,
    align: str = "left",
    letter_spacing: float = 0.0,
    size_scale: float = 1.0,
    line_spacing: float = 1.0,
    style: TextStyle | None = None,
    curve_segments: int = 8,
    policy: GenerationPolicy | None = None,
    compute_backend: str = "cpu",
) -> tuple[list[dict], list[str], dict[str, list[LayerShapeGroup]]]:
    """Compose `text` (may contain `\\n` line breaks) with a Layered Glyph
    Effect applied per-character, reusing `text_compose.compose_shape_map`
    verbatim for layout/alignment/spacing/multiline handling. Returns
    `(shapes, warnings, groups_by_char)` -- `style` layers `TextStyle`'s
    existing per-character fill/bold/italic on top exactly as it does for
    non-layered text; leave it `None` to keep each layer's own configured
    color untouched (the common case, since color is normally set per-layer
    already)."""
    if align not in ALIGNMENTS:
        raise ValueError(f"align must be one of {ALIGNMENTS}, got {align!r}")
    shape_map, groups_by_char = build_layered_shape_map(
        text, font_path, stack, curve_segments=curve_segments,
        policy=policy, compute_backend=compute_backend,
    )
    shapes, warnings = compose_shape_map(
        text, font_path, shape_map, curve_segments=curve_segments, align=align,
        letter_spacing=letter_spacing, size_scale=size_scale, line_spacing=line_spacing,
        style=style,
    )
    return shapes, warnings, groups_by_char
