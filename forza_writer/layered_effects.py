"""Layered Glyph Effects engine.

Derives multiple independently-transformed/colored geometric layers from a
single source glyph's outline, then routes each derived layer's contours
through the *existing* `forza_writer.primitive_fit` pipeline -- the same
generator plain (non-layered) glyphs already use -- so a layered glyph's
preview and its final generated output are always built from the exact same
geometry. See `forza_writer/primitive_fit.py::fit_placements` and
`tools/gen_modelbin.py::extract_glyph_contours`/`normalize_to_128` for the
upstream pipeline this plugs into.

Geometry (inset/outset, translate, scale, rotate, boolean union/difference/
intersection) is done with `shapely`, since nothing in this codebase already
does real vector offset/boolean geometry (only pixel-mask bitwise ops exist
elsewhere, e.g. `primitive_fit.rasterize_contours`, which are fill-rule
rasterization, not offset geometry). `shapely.Polygon(exterior, interiors)`
maps directly onto the outer/hole split `gen_modelbin.group_contours_by_nesting`
already computes for earcut triangulation, so glyph counters/holes (O, A, B,
8, @, &, ...) fall out correctly for free -- both inset and outset buffer
operations act correctly on holes too (an inset shrinks the fill *away* from
a hole boundary same as it does from the outer boundary; an outset grows the
fill into a hole, shrinking or closing it), with no special-casing needed.

Every geometry operation is written to never raise and never hand back
empty/invalid geometry to the primitive generator: a buffer or boolean op
that collapses a layer (self-intersection, zero-area, a hole that swallows
its own island) is caught and the layer is marked `"collapsed"` with a
human-readable reason instead. A layer whose `source` collapsed is skipped
the same way rather than propagating a crash.
"""

from __future__ import annotations

import sys
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable

from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
import shapely.affinity as affinity

from forza_writer import primitive_fit
from forza_writer.generation_policy import DEFAULT_POLICY, GenerationPolicy

# tools/gen_modelbin.py holds the codebase's one canonical outline-extraction
# and contour-nesting implementation; reuse group_contours_by_nesting rather
# than re-deriving hole/counter assignment a second way. Same sys.path dance
# forza_writer/font_info.py and forza_writer/text_compose.py already use to
# reach it.
_TOOLS_DIR = str(Path(__file__).resolve().parent.parent / "tools")
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)
from gen_modelbin import group_contours_by_nesting  # local: see _TOOLS_DIR sys.path insert above

Contours = list[list[tuple[float, float]]]
RGBA = tuple[int, int, int, int]

# Below this area (in the same ±100 glyph-unit space normalize_to_128 uses),
# a resolved polygon is treated as collapsed rather than a real sliver --
# keeps near-zero-area GEOS noise from reaching fit_placements.
_MIN_AREA = 1e-4


class LayerOperation(str, Enum):
    """The layer's primary behavior, for UI labeling/defaults and to select
    built-in preset shapes. Geometry resolution (see `apply_operation`)
    always applies the full composable property set (amount, scale,
    rotation, offset) regardless of `operation` -- e.g. the spec's own
    "Highlight" custom-mode example is an INSET layer that *also* carries an
    offset_x/offset_y, matching real vinyl-effect construction where a small
    nudge often accompanies an inset. `operation` mainly distinguishes
    INSET's sign convention (amount is always entered as a positive
    magnitude, per the spec's "Inset 8" / "Outset 24" language) and the
    BOOLEAN_* variants, which require a second layer as an operand."""

    ORIGINAL = "original"
    INSET = "inset"
    OUTSET = "outset"
    TRANSLATE = "translate"
    SCALE = "scale"
    ROTATE = "rotate"
    BOOLEAN_UNION = "boolean_union"
    BOOLEAN_DIFFERENCE = "boolean_difference"
    BOOLEAN_INTERSECTION = "boolean_intersection"


BOOLEAN_OPS = {
    LayerOperation.BOOLEAN_UNION,
    LayerOperation.BOOLEAN_DIFFERENCE,
    LayerOperation.BOOLEAN_INTERSECTION,
}


def new_layer_id() -> str:
    return uuid.uuid4().hex[:8]


@dataclass
class EffectLayer:
    """One entry in a `LayerStack`. `source` is either the literal string
    `"original"` or another layer's `id` that appears *earlier* in the same
    stack -- forward-only references, so a stack always resolves
    deterministically in list order with no possibility of a dependency
    cycle (the simpler of the two architectures the spec allows; see its
    "layer dependency model" section)."""

    id: str
    name: str
    operation: LayerOperation = LayerOperation.ORIGINAL
    enabled: bool = True
    source: str = "original"
    amount: float = 0.0  # inset/outset magnitude, glyph units, always >= 0
    offset_x: float = 0.0
    offset_y: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0
    rotation_deg: float = 0.0
    origin: str = "centroid"  # "centroid" | "glyph_origin" (shared (0,0))
    boolean_operand: str | None = None  # another layer's id; required for BOOLEAN_* ops
    color: RGBA = (255, 255, 255, 255)
    opacity: float = 1.0

    def structural_key(self) -> tuple:
        """Fields that affect resolved GEOMETRY only. Two layers with equal
        `structural_key()` always resolve to identical contours -- callers
        (the GUI's cache) use this to skip re-running `fit_placements` when
        only cosmetic fields (name/color/opacity) change, and to skip
        re-resolving a disabled layer's geometry at all. See
        `LayerStack.geometry_signature`."""
        return (
            self.operation.value, self.source, round(self.amount, 6),
            round(self.offset_x, 6), round(self.offset_y, 6),
            round(self.scale_x, 6), round(self.scale_y, 6),
            round(self.rotation_deg, 6), self.origin, self.boolean_operand,
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "operation": self.operation.value,
            "enabled": self.enabled, "source": self.source, "amount": self.amount,
            "offset_x": self.offset_x, "offset_y": self.offset_y,
            "scale_x": self.scale_x, "scale_y": self.scale_y,
            "rotation_deg": self.rotation_deg, "origin": self.origin,
            "boolean_operand": self.boolean_operand,
            "color": list(self.color), "opacity": self.opacity,
        }

    @staticmethod
    def from_dict(data: dict) -> "EffectLayer":
        color = data.get("color", [255, 255, 255, 255])
        return EffectLayer(
            id=data.get("id") or new_layer_id(),
            name=data.get("name", "Layer"),
            operation=LayerOperation(data.get("operation", "original")),
            enabled=bool(data.get("enabled", True)),
            source=data.get("source", "original"),
            amount=float(data.get("amount", 0.0)),
            offset_x=float(data.get("offset_x", 0.0)),
            offset_y=float(data.get("offset_y", 0.0)),
            scale_x=float(data.get("scale_x", 1.0)),
            scale_y=float(data.get("scale_y", 1.0)),
            rotation_deg=float(data.get("rotation_deg", 0.0)),
            origin=data.get("origin", "centroid"),
            boolean_operand=data.get("boolean_operand"),
            color=tuple(int(c) for c in color),  # type: ignore[assignment]
            opacity=float(data.get("opacity", 1.0)),
        )


@dataclass
class LayerStack:
    name: str
    layers: list[EffectLayer] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"name": self.name, "layers": [l.to_dict() for l in self.layers]}

    @staticmethod
    def from_dict(data: dict) -> "LayerStack":
        return LayerStack(
            name=data.get("name", "Custom"),
            layers=[EffectLayer.from_dict(d) for d in data.get("layers", [])],
        )

    def geometry_signature(self) -> tuple:
        """A hash-stable summary of every layer's `structural_key()`, in
        order. Unchanged between two stacks means `resolve_layer_stack` will
        produce identical geometry for both -- purely cosmetic edits (color,
        opacity, name, enabled) never change this."""
        return tuple(l.structural_key() for l in self.layers)


@dataclass
class LayerResult:
    layer: EffectLayer
    geometry: BaseGeometry | None
    contours: Contours
    status: str  # "ok" | "collapsed" | "skipped"
    warning: str | None = None


@dataclass
class LayerShapeGroup:
    layer_id: str
    layer_name: str
    color: RGBA
    shapes: list[dict]
    status: str
    warning: str | None = None


def _is_degenerate(geom: BaseGeometry | None) -> bool:
    return geom is None or geom.is_empty or geom.area <= _MIN_AREA


def contours_to_polygon(contours_norm: Contours) -> BaseGeometry:
    """Build a (Multi)Polygon from normalized glyph contours, respecting
    outer/hole structure via `group_contours_by_nesting`. A contour that
    fails to build a valid ring (self-intersecting/degenerate, which some
    decorative/display fonts produce) is repaired with `buffer(0)` and, if
    still invalid or empty, silently omitted -- the rest of the glyph's
    islands still resolve rather than the whole glyph failing."""
    valid = [c for c in contours_norm if len(c) >= 3]
    if not valid:
        return Polygon()

    islands = group_contours_by_nesting(valid)
    polys: list[Polygon] = []
    for outer_idx, hole_idxs in islands:
        exterior = valid[outer_idx]
        holes = [valid[h] for h in hole_idxs]
        try:
            poly = Polygon(exterior, holes)
        except Exception:
            continue
        if not poly.is_valid:
            poly = poly.buffer(0)
        if isinstance(poly, BaseGeometry) and not poly.is_empty and poly.area > _MIN_AREA:
            polys.append(poly)

    if not polys:
        return Polygon()
    if len(polys) == 1:
        return polys[0]
    return unary_union(polys)


def polygon_to_contours(geom: BaseGeometry | None) -> Contours:
    """Flatten a (Multi)Polygon back into `list[list[(x, y)]]` contours --
    exterior ring first, then each interior (hole) ring, per polygon.
    Degenerate rings (fewer than 3 points once the implicit closing point is
    dropped) are omitted."""
    if geom is None or geom.is_empty:
        return []
    polys = list(geom.geoms) if isinstance(geom, MultiPolygon) else [geom]
    out: Contours = []
    for poly in polys:
        if poly.is_empty or poly.area <= _MIN_AREA:
            continue
        ring = list(poly.exterior.coords)[:-1]
        if len(ring) >= 3:
            out.append(ring)
        for interior in poly.interiors:
            hole = list(interior.coords)[:-1]
            if len(hole) >= 3:
                out.append(hole)
    return out


def _origin_point(geom: BaseGeometry, origin: str):
    if origin == "glyph_origin":
        return (0.0, 0.0)
    return "centroid"


def apply_operation(
    geom: BaseGeometry, layer: EffectLayer, resolved: dict[str, LayerResult],
) -> tuple[BaseGeometry | None, str | None]:
    """Resolve one layer's geometry from its already-resolved source
    geometry. Returns `(geometry, None)` on success or `(None, reason)` if
    the operation collapsed the layer -- never raises."""
    result = geom

    signed_amount = 0.0
    if layer.operation == LayerOperation.INSET:
        signed_amount = -abs(layer.amount)
    elif layer.operation == LayerOperation.OUTSET:
        signed_amount = abs(layer.amount)
    if signed_amount:
        result = result.buffer(signed_amount, join_style="mitre")
        if _is_degenerate(result):
            return None, f"{layer.operation.value} {abs(signed_amount):g} collapsed the contour to nothing"

    if layer.scale_x != 1.0 or layer.scale_y != 1.0:
        result = affinity.scale(
            result, xfact=layer.scale_x, yfact=layer.scale_y,
            origin=_origin_point(result, layer.origin),
        )
        if _is_degenerate(result):
            return None, "scale collapsed the contour to nothing"

    if layer.rotation_deg:
        result = affinity.rotate(
            result, layer.rotation_deg, origin=_origin_point(result, layer.origin),
        )
        if _is_degenerate(result):
            return None, "rotate collapsed the contour to nothing"

    if layer.offset_x or layer.offset_y:
        result = affinity.translate(result, xoff=layer.offset_x, yoff=layer.offset_y)

    if layer.operation in BOOLEAN_OPS:
        operand = resolved.get(layer.boolean_operand) if layer.boolean_operand else None
        if operand is None or operand.status != "ok" or operand.geometry is None:
            return None, f"boolean operand {layer.boolean_operand!r} is unavailable"
        other = operand.geometry
        if layer.operation == LayerOperation.BOOLEAN_UNION:
            result = result.union(other)
        elif layer.operation == LayerOperation.BOOLEAN_DIFFERENCE:
            result = result.difference(other)
        else:
            result = result.intersection(other)
        if _is_degenerate(result):
            return None, f"{layer.operation.value} produced empty geometry"

    if not result.is_valid:
        result = result.buffer(0)
    if _is_degenerate(result):
        return None, "resulting geometry is empty or invalid"

    return result, None


def resolve_layer_stack(original_contours: Contours, stack: LayerStack) -> list[LayerResult]:
    """Evaluate every layer in `stack`, in list order, against the source
    glyph's contours. A layer referencing a collapsed/missing source is
    itself marked `"skipped"` rather than raising, so one bad layer never
    prevents the rest of the stack (or the rest of the text) from
    resolving."""
    original_geom = contours_to_polygon(original_contours)
    resolved: dict[str, LayerResult] = {}
    results: list[LayerResult] = []

    for layer in stack.layers:
        if layer.source == "original":
            base, base_ok = original_geom, not _is_degenerate(original_geom)
        else:
            src = resolved.get(layer.source)
            base = src.geometry if src else None
            base_ok = src is not None and src.status == "ok" and base is not None

        if not base_ok:
            result = LayerResult(layer, None, [], "skipped", f"source layer {layer.source!r} is unavailable")
            resolved[layer.id] = result
            results.append(result)
            continue

        geom, warning = apply_operation(base, layer, resolved)
        if geom is None:
            result = LayerResult(layer, None, [], "collapsed", warning)
        else:
            result = LayerResult(layer, geom, polygon_to_contours(geom), "ok", None)
        resolved[layer.id] = result
        results.append(result)

    return results


def recolor_shape(shape: dict, color: RGBA, opacity: float = 1.0) -> dict:
    """Apply `color`/`opacity` to one shape dict (mask/cutout shapes are
    never recolored -- same convention `forza_writer/text_style.py::
    color_for` already follows for per-character coloring). Used both by
    `_finalize_shape` at generation time and, standalone, by callers that
    want to re-tint an already-generated `LayerShapeGroup.shapes` list
    without re-running geometry/primitive-fitting -- e.g. the Layer Effects
    GUI tab's live color swatch, which must not trigger regeneration for a
    purely cosmetic edit."""
    if shape.get("mask"):
        return dict(shape)
    r, g, b, a = color
    if opacity != 1.0:
        a = max(0, min(255, round(a * opacity)))
    return {**shape, "color": [r, g, b, a]}


def _finalize_shape(shape: dict, layer: EffectLayer) -> dict:
    """Apply the layer's color and tag the shape with which layer produced
    it, for grouped export (`tools/gen_fabric_project.py`)."""
    out = recolor_shape(shape, layer.color, layer.opacity)
    out["layer"] = {"id": layer.id, "name": layer.name}
    return out


def generate_layered_glyph(
    contours_norm: Contours,
    stack: LayerStack,
    *,
    resolution: int = primitive_fit.DEFAULT_RESOLUTION,
    policy: GenerationPolicy | None = None,
    compute_backend: str = "cpu",
    glyph_size: float = 300.0,
) -> list[LayerShapeGroup]:
    """Resolve `stack` against `contours_norm` and run every enabled,
    non-collapsed layer's derived contours through the existing
    `primitive_fit.fit_placements` -> `placements_to_shapes` pipeline --
    the same pipeline a plain, non-layered glyph already uses. Returns one
    `LayerShapeGroup` per layer, in stack order (back-to-front, matching the
    spec's layer-ordering requirement), including disabled/collapsed layers
    (with an empty `shapes` list) so the GUI's layer list can render every
    row regardless of status."""
    policy = policy or DEFAULT_POLICY
    results = resolve_layer_stack(contours_norm, stack)
    groups: list[LayerShapeGroup] = []
    for r in results:
        if not r.layer.enabled or r.status != "ok" or not r.contours:
            groups.append(LayerShapeGroup(r.layer.id, r.layer.name, r.layer.color, [], r.status, r.warning))
            continue
        placements, _strategy = primitive_fit.fit_placements(
            r.contours, resolution=resolution, policy=policy, compute_backend=compute_backend,
        )
        shapes = primitive_fit.placements_to_shapes(placements, resolution, glyph_size)
        shapes = [_finalize_shape(s, r.layer) for s in shapes]
        groups.append(LayerShapeGroup(r.layer.id, r.layer.name, r.layer.color, shapes, "ok", None))
    return groups


def estimate_vinyl_count(groups: list[LayerShapeGroup]) -> int:
    """Total primitive-shape count across all `"ok"` layers -- purely
    informational (no enforced platform/game cap exists anywhere in this
    codebase today; see `forza_writer/generation_policy.py`), surfaced in
    the GUI so a user can see when a layered effect has gotten expensive."""
    return sum(len(g.shapes) for g in groups if g.status == "ok")


def flatten_layer_groups(groups: list[LayerShapeGroup]) -> list[dict]:
    """Concatenate every layer's shapes, back-to-front, into one shape list
    -- what a layered preview render and a layered text token both need."""
    flat: list[dict] = []
    for g in groups:
        flat.extend(g.shapes)
    return flat


def group_shapes_by_layer(shapes: list[dict]) -> list[tuple[str, list[int]]]:
    """Bucket a composed shape list's indices by the `"layer"` tag
    `_finalize_shape` attaches (`{"id", "name"}`), preserving first-seen
    layer order. Shapes without a `"layer"` key (plain, non-layered output)
    are omitted -- callers get an empty/no-op groups list for those, so this
    is safe to call unconditionally. Matches
    `forza_writer.fabric_project.to_fabric_project`'s existing generic
    `groups: list[tuple[name, [indices]]]` parameter directly -- an effect
    layer becomes one KFPS editor group spanning every character's shapes
    for that layer, per the spec's vinyl-layer-grouping example."""
    order: list[str] = []
    by_name: dict[str, list[int]] = {}
    for index, shape in enumerate(shapes):
        layer = shape.get("layer")
        if not layer:
            continue
        name = layer.get("name", layer.get("id", "Layer"))
        if name not in by_name:
            by_name[name] = []
            order.append(name)
        by_name[name].append(index)
    return [(name, by_name[name]) for name in order]
