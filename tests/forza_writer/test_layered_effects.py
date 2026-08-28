"""Tests for the Layered Glyph Effects engine (forza_writer/layered_effects.py,
layer_presets.py, layered_effects_text.py).

Font-style robustness is tested against a handful of structurally different
fonts already installed on this machine (bold sans, serif, slab serif,
script, condensed display, blackletter, geometric sans), skipped gracefully
when a given font isn't present: the same `requires_font`-style pattern
`test_primitive_fit.py`/`test_text_compose.py` already use for their own
external test font.
"""

from pathlib import Path

import pytest

from forza_writer.layer_presets import PRESET_REGISTRY
from forza_writer.layered_effects import (
    EffectLayer,
    LayerOperation,
    LayerStack,
    contours_to_polygon,
    estimate_vinyl_count,
    generate_layered_glyph,
    group_shapes_by_layer,
    polygon_to_contours,
    resolve_layer_stack,
)
from forza_writer.layered_effects_text import build_layered_shape_map, compose_layered_text

BUNDLED_FONT = Path(__file__).resolve().parent.parent.parent / "assets" / "fonts" / "LiberationSans-Regular.ttf"

_WINFONTS = Path(r"C:\Windows\Fonts")
STYLE_FONTS = {
    "bold_sans": _WINFONTS / "arialbd.ttf",
    "thin_sans": _WINFONTS / "verdana.ttf",
    "serif": _WINFONTS / "times.ttf",
    "slab_serif": _WINFONTS / "ROCK.TTF",
    "script": _WINFONTS / "MISTRAL.TTF",
    "condensed_display": _WINFONTS / "impact.ttf",
    "blackletter": _WINFONTS / "OLDENGL.TTF",
    "geometric_sans": _WINFONTS / "GOTHIC.TTF",
}
AVAILABLE_STYLE_FONTS = {name: path for name, path in STYLE_FONTS.items() if path.exists()}


def _norm_contours(char: str, font_path: Path, curve_segments: int = 8):
    import sys

    tools_dir = str(Path(__file__).resolve().parent.parent.parent / "tools")
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    from gen_modelbin import extract_contours, normalize_to_128

    contours, units_per_em = extract_contours(char, font_path, curve_segments)
    return normalize_to_128(contours, units_per_em)


# ---------------------------------------------------------------------------
# Contour <-> polygon round trip / hole preservation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("char", ["A", "B", "D", "O", "P", "Q", "R", "8", "@", "&"])
def test_hole_preserving_round_trip(char):
    norm = _norm_contours(char, BUNDLED_FONT)
    geom = contours_to_polygon(norm)
    assert not geom.is_empty
    assert geom.area > 0

    back = polygon_to_contours(geom)
    assert len(back) >= 1
    # Re-building from the round-tripped contours should reproduce the same
    # area (within floating point tolerance) -- nothing lost or duplicated.
    geom2 = contours_to_polygon(back)
    assert geom2.area == pytest.approx(geom.area, rel=1e-6)


def test_letters_with_counters_have_holes():
    for char in ("O", "A", "B", "8", "@"):
        norm = _norm_contours(char, BUNDLED_FONT)
        geom = contours_to_polygon(norm)
        polys = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
        hole_count = sum(len(p.interiors) for p in polys)
        assert hole_count >= 1, f"{char!r} should have at least one counter/hole"


def test_ampersand_has_multiple_islands_or_holes():
    # '&' is a good stress case for nesting depth > 1 in most fonts.
    norm = _norm_contours("&", BUNDLED_FONT)
    geom = contours_to_polygon(norm)
    assert geom.area > 0
    back = polygon_to_contours(geom)
    assert len(back) >= 2


# ---------------------------------------------------------------------------
# Inset is not scale
# ---------------------------------------------------------------------------

def test_inset_is_not_scale():
    norm = _norm_contours("A", BUNDLED_FONT)
    original = contours_to_polygon(norm)

    inset_layer = EffectLayer(id="a", name="inset", operation=LayerOperation.INSET, amount=6.0)
    inset_geom, warning = _apply(original, inset_layer)
    assert warning is None

    # A uniform scale that happens to match the inset's area ratio moves
    # every vertex proportionally toward the centroid -- it does NOT hold a
    # constant offset distance from each edge the way a true inset does. On
    # an asymmetric glyph like 'A', the inset and the area-matched scale
    # copy diverge measurably (different Hausdorff-style deviation from a
    # uniform per-edge offset), catching a "secretly implemented inset as
    # scale" regression.
    area_ratio = inset_geom.area / original.area
    import shapely.affinity as affinity
    scaled_geom = affinity.scale(original, xfact=area_ratio ** 0.5, yfact=area_ratio ** 0.5, origin="centroid")

    # symmetric_difference between the two is non-trivial when they're
    # genuinely different shapes; near-zero would mean inset degenerated
    # into a plain uniform scale.
    diff_area = inset_geom.symmetric_difference(scaled_geom).area
    assert diff_area > original.area * 0.02


def _apply(geom, layer, resolved=None):
    from forza_writer.layered_effects import apply_operation

    return apply_operation(geom, layer, resolved or {})


# ---------------------------------------------------------------------------
# Graceful collapse / font robustness
# ---------------------------------------------------------------------------

def test_deep_inset_collapses_gracefully_not_crash():
    norm = _norm_contours("i", BUNDLED_FONT)  # narrow stem + disjoint dot
    stack = LayerStack("deep", [
        EffectLayer(id="orig", name="Original", operation=LayerOperation.ORIGINAL),
        EffectLayer(id="huge", name="Huge inset", operation=LayerOperation.INSET, amount=500.0),
    ])
    results = resolve_layer_stack(norm, stack)
    huge = next(r for r in results if r.layer.id == "huge")
    assert huge.status == "collapsed"
    assert huge.warning
    assert huge.contours == []

    # Never reaches the primitive generator with empty/garbage geometry.
    groups = generate_layered_glyph(norm, stack)
    collapsed_group = next(g for g in groups if g.layer_id == "huge")
    assert collapsed_group.shapes == []


def test_layer_sourced_from_collapsed_layer_is_skipped_not_crashed():
    norm = _norm_contours(".", BUNDLED_FONT)  # tiny glyph, collapses fast
    stack = LayerStack("chain", [
        EffectLayer(id="a", name="A", operation=LayerOperation.INSET, amount=500.0),
        EffectLayer(id="b", name="B", operation=LayerOperation.INSET, amount=1.0, source="a"),
    ])
    results = resolve_layer_stack(norm, stack)
    a_result = next(r for r in results if r.layer.id == "a")
    b_result = next(r for r in results if r.layer.id == "b")
    assert a_result.status == "collapsed"
    assert b_result.status == "skipped"
    assert b_result.warning


@pytest.mark.parametrize("style_name", sorted(STYLE_FONTS))
def test_presets_resolve_without_crashing_across_font_styles(style_name):
    font_path = STYLE_FONTS[style_name]
    if not font_path.exists():
        pytest.skip(f"{font_path} not present on this machine")
    for char in ("A", "O", "S", "g"):
        norm = _norm_contours(char, font_path)
        if not norm:
            continue
        for preset_name, factory in PRESET_REGISTRY.items():
            stack = factory()
            # Must never raise, regardless of how aggressively a font's
            # geometry collapses under inset/outset.
            groups = generate_layered_glyph(norm, stack)
            assert isinstance(estimate_vinyl_count(groups), int)


# ---------------------------------------------------------------------------
# Boolean ops
# ---------------------------------------------------------------------------

def test_boolean_difference_builds_a_hollow_band():
    norm = _norm_contours("O", BUNDLED_FONT)
    stack = LayerStack("band", [
        EffectLayer(id="out20", name="Outset 20", operation=LayerOperation.OUTSET, amount=20.0),
        EffectLayer(id="out10", name="Outset 10", operation=LayerOperation.OUTSET, amount=10.0),
        EffectLayer(id="band", name="Band", operation=LayerOperation.BOOLEAN_DIFFERENCE,
                    source="out20", boolean_operand="out10"),
    ])
    results = resolve_layer_stack(norm, stack)
    band = next(r for r in results if r.layer.id == "band")
    out20 = next(r for r in results if r.layer.id == "out20")
    out10 = next(r for r in results if r.layer.id == "out10")
    assert band.status == "ok"
    # A ring/band's area is the difference of the two source areas.
    assert band.geometry.area == pytest.approx(out20.geometry.area - out10.geometry.area, rel=1e-3)


def test_boolean_union_covers_both_operands():
    norm = _norm_contours("A", BUNDLED_FONT)
    stack = LayerStack("union", [
        EffectLayer(id="orig", name="Original", operation=LayerOperation.ORIGINAL),
        EffectLayer(id="shifted", name="Shifted", operation=LayerOperation.TRANSLATE, offset_x=15.0),
        EffectLayer(id="merged", name="Merged", operation=LayerOperation.BOOLEAN_UNION,
                    source="orig", boolean_operand="shifted"),
    ])
    results = resolve_layer_stack(norm, stack)
    orig = next(r for r in results if r.layer.id == "orig")
    merged = next(r for r in results if r.layer.id == "merged")
    assert merged.status == "ok"
    assert merged.geometry.area >= orig.geometry.area


# ---------------------------------------------------------------------------
# Determinism / cosmetic-vs-structural caching contract
# ---------------------------------------------------------------------------

def test_resolution_is_deterministic():
    norm = _norm_contours("R", BUNDLED_FONT)
    stack = PRESET_REGISTRY["Concentric Inline"]()
    a = [r.contours for r in resolve_layer_stack(norm, stack)]
    b = [r.contours for r in resolve_layer_stack(norm, stack)]
    assert a == b


def test_cosmetic_change_does_not_alter_geometry_signature():
    stack = PRESET_REGISTRY["Multi-Outline"]()
    before = stack.geometry_signature()
    for layer in stack.layers:
        layer.color = (1, 2, 3, 4)
        layer.name = "renamed"
        layer.opacity = 0.5
    stack.layers[0].enabled = False
    after = stack.geometry_signature()
    assert before == after


def test_structural_change_alters_geometry_signature():
    stack = PRESET_REGISTRY["Concentric Inline"]()
    before = stack.geometry_signature()
    stack.layers[1].amount += 1.0
    assert stack.geometry_signature() != before


# ---------------------------------------------------------------------------
# Preset round trip (serialization)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("preset_name", sorted(PRESET_REGISTRY))
def test_preset_dict_round_trip(preset_name):
    stack = PRESET_REGISTRY[preset_name]()
    data = stack.to_dict()
    restored = LayerStack.from_dict(data)
    assert restored.geometry_signature() == stack.geometry_signature()
    assert [l.name for l in restored.layers] == [l.name for l in stack.layers]
    assert [l.color for l in restored.layers] == [l.color for l in stack.layers]


# ---------------------------------------------------------------------------
# Multi-glyph / multiline text integration
# ---------------------------------------------------------------------------

def test_layered_text_multiline_matches_plain_layout_advance():
    from forza_writer.text_compose import compose_shape_map

    stack = PRESET_REGISTRY["Concentric Inline"](step=4, count=2)
    shape_map, groups_by_char = build_layered_shape_map("Hi\nGo", BUNDLED_FONT, stack)
    layered_shapes, warnings = compose_shape_map("Hi\nGo", BUNDLED_FONT, shape_map)
    assert warnings == []
    assert layered_shapes  # produced something on both lines
    assert set(groups_by_char) == {"H", "i", "G", "o"}

    # Two visually distinct lines: shape y-extents should split into two
    # separated bands (line 2 offset down from line 1), not overlap into one.
    ys = sorted(s["data"][1] for s in layered_shapes)
    assert max(ys) - min(ys) > 50  # comfortably more than a single line's glyph height noise


def test_compose_layered_text_tags_every_shape_with_its_layer():
    stack = PRESET_REGISTRY["Multi-Outline"](step=4, count=3)
    shapes, warnings, groups_by_char = compose_layered_text("Ab", BUNDLED_FONT, stack)
    assert warnings == []
    assert shapes
    assert all("layer" in s and "name" in s["layer"] for s in shapes)
    layer_names = {s["layer"]["name"] for s in shapes}
    assert layer_names <= {l.name for l in stack.layers}


def test_group_shapes_by_layer_matches_fabric_project_groups():
    from forza_writer.fabric_project import to_fabric_project

    stack = PRESET_REGISTRY["Concentric Inline"](step=4, count=3)
    shapes, _warnings, _groups = compose_layered_text("AB", BUNDLED_FONT, stack)
    groups = group_shapes_by_layer(shapes)
    assert [name for name, _ in groups] == ["Original", "Inset 1", "Inset 2"]
    total_indices = sum(len(idx) for _, idx in groups)
    assert total_indices == len(shapes)

    project = to_fabric_project(shapes, name="layered-test", groups=groups)
    group_names = {s.get("editor_group_name") for s in project["shapes"]}
    assert group_names == {"Original", "Inset 1", "Inset 2"}


# ---------------------------------------------------------------------------
# Existing non-layered pipeline unaffected: a light smoke check here, since
# the authoritative check is running the pre-existing test_primitive_fit.py
# / test_text_compose.py / test_export.py / test_fabric_project.py suites
# unmodified alongside this file.
# ---------------------------------------------------------------------------

def test_plain_fit_glyph_unaffected_by_this_module_importing():
    from forza_writer.primitive_fit import fit_glyph

    shapes = fit_glyph("A", BUNDLED_FONT)
    assert shapes
    assert "layer" not in shapes[0]
