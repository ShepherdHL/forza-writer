"""Built-in Layered Glyph Effect presets.

Each preset is a small parametric factory that returns a `LayerStack` --
never hand-authored geometry -- so every visible effect in the Layer Effects
tab is just a particular arrangement of the same `EffectLayer` primitives
(see `forza_writer/layered_effects.py`). Adding a new preset later means
adding another factory function here and an entry in `PRESET_REGISTRY`, not
a new code path through the engine.
"""

from __future__ import annotations

from typing import Callable

from forza_writer.layered_effects import EffectLayer, LayerOperation, LayerStack, new_layer_id

RGBA = tuple[int, int, int, int]

WHITE: RGBA = (255, 255, 255, 255)
BLACK: RGBA = (0, 0, 0, 255)

# The reference multicolor nested-text image's gradient, used only as an
# example default: every preset's colors are overridable, and presets must
# never permanently hard-code a specific palette.
_DEFAULT_GRADIENT: tuple[RGBA, ...] = (
    (42, 221, 216, 255), (50, 168, 234, 255), (57, 131, 237, 255), (70, 79, 240, 255),
)


def _lerp(a: RGBA, b: RGBA, t: float) -> RGBA:
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))  # type: ignore[return-value]


def _gradient(count: int, colors: tuple[RGBA, ...] | None = None) -> list[RGBA]:
    """`count` colors evenly sampled across `colors` (default: the reference
    teal-to-indigo gradient above). `count <= 1` returns just the first
    stop."""
    stops = colors or _DEFAULT_GRADIENT
    if count <= 1:
        return [stops[0]]
    out = []
    for i in range(count):
        t = i / (count - 1)
        scaled = t * (len(stops) - 1)
        lo = int(scaled)
        hi = min(lo + 1, len(stops) - 1)
        out.append(_lerp(stops[lo], stops[hi], scaled - lo))
    return out


def preset_none(color: RGBA = WHITE) -> LayerStack:
    return LayerStack("None / Original", [
        EffectLayer(id=new_layer_id(), name="Original", operation=LayerOperation.ORIGINAL, color=color),
    ])


def preset_single_outline(amount: float = 12.0, outline_color: RGBA = BLACK, fill_color: RGBA = WHITE) -> LayerStack:
    return LayerStack("Single Outline", [
        EffectLayer(id=new_layer_id(), name="Outline", operation=LayerOperation.OUTSET,
                    amount=amount, color=outline_color),
        EffectLayer(id=new_layer_id(), name="Fill", operation=LayerOperation.ORIGINAL, color=fill_color),
    ])


def preset_concentric_inline(step: float = 8.0, count: int = 4, colors: tuple[RGBA, ...] | None = None) -> LayerStack:
    """Layer 1: Original, Layer 2: Inset `step`, Layer 3: Inset `2*step`,
    ... -- the construction behind the reference multicolor nested-text
    look."""
    palette = _gradient(count, colors)
    layers = [EffectLayer(id=new_layer_id(), name="Original", operation=LayerOperation.ORIGINAL, color=palette[0])]
    for i in range(1, count):
        layers.append(EffectLayer(
            id=new_layer_id(), name=f"Inset {i}", operation=LayerOperation.INSET,
            amount=step * i, color=palette[i],
        ))
    return LayerStack("Concentric Inline", layers)


def preset_multi_outline(step: float = 8.0, count: int = 4, colors: tuple[RGBA, ...] | None = None) -> LayerStack:
    """Reverse of Concentric Inline: outermost outset at the back, original
    on top -- Layer 1: Outset `(count-1)*step` ... Layer N: Original."""
    palette = _gradient(count, colors)
    layers = []
    for i in range(count - 1, 0, -1):
        layers.append(EffectLayer(
            id=new_layer_id(), name=f"Outset {i}", operation=LayerOperation.OUTSET,
            amount=step * i, color=palette[count - 1 - i],
        ))
    layers.append(EffectLayer(id=new_layer_id(), name="Original", operation=LayerOperation.ORIGINAL, color=palette[-1]))
    return LayerStack("Multi-Outline", layers)


def preset_offset_shadow(dx: float = 6.0, dy: float = 6.0, count: int = 4, colors: tuple[RGBA, ...] | None = None) -> LayerStack:
    """Repeated translated copies, furthest offset at the back, original on
    top -- Layer 1: Offset `(count-1)*(dx,dy)` ... Layer N: Original."""
    palette = _gradient(count, colors or ((40, 40, 40, 255), WHITE))
    layers = []
    for i in range(count - 1, 0, -1):
        layers.append(EffectLayer(
            id=new_layer_id(), name=f"Offset {i}", operation=LayerOperation.TRANSLATE,
            offset_x=dx * i, offset_y=dy * i, color=palette[count - 1 - i],
        ))
    layers.append(EffectLayer(id=new_layer_id(), name="Original", operation=LayerOperation.ORIGINAL, color=palette[-1]))
    return LayerStack("Offset Shadow", layers)


def preset_stepped_shadow(
    dx: float = 4.0, dy: float = -4.0, count: int = 5,
    color: RGBA = (30, 30, 30, 255), front_color: RGBA = WHITE,
) -> LayerStack:
    """Like Offset Shadow, but every step shares one shadow color (only the
    frontmost/original layer differs) -- a stepped "extrusion" look rather
    than a color gradient."""
    layers = []
    for i in range(count - 1, 0, -1):
        layers.append(EffectLayer(
            id=new_layer_id(), name=f"Step {i}", operation=LayerOperation.TRANSLATE,
            offset_x=dx * i, offset_y=dy * i, color=color,
        ))
    layers.append(EffectLayer(id=new_layer_id(), name="Original", operation=LayerOperation.ORIGINAL, color=front_color))
    return LayerStack("Stepped Shadow", layers)


PRESET_REGISTRY: dict[str, Callable[..., LayerStack]] = {
    "None / Original": preset_none,
    "Single Outline": preset_single_outline,
    "Concentric Inline": preset_concentric_inline,
    "Multi-Outline": preset_multi_outline,
    "Offset Shadow": preset_offset_shadow,
    "Stepped Shadow": preset_stepped_shadow,
}
