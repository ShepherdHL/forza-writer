from pathlib import Path

import numpy as np
import pytest

import forza_writer.primitive_fit as primitive_fit_module
from forza_writer.primitive_fit import (
    DEFAULT_RESOLUTION,
    PlacedShape,
    _curved_stencil_placements,
    candidate_gain,
    fit_placements,
    fit_silhouette,
    placements_to_shapes,
    preview_glyph_mask_options,
    rasterize_contours,
    render_candidate,
    shape_to_render_params,
)
from forza_writer.primitive_shapes import PRIMITIVE_CATALOG
from forza_writer.shapes import resource_to_shape_word, resource_to_typecode

# No font ships in this repo (see README.md); font-dependent tests reuse this
# repo's verification font and skip gracefully where it isn't present.
AMARILLO_FONT = Path.home() / "Desktop" / "amarillo-usaf" / "amarurgt.ttf"
requires_font = pytest.mark.skipif(not AMARILLO_FONT.exists(), reason="test font not present on this machine")


def _square_target(res=DEFAULT_RESOLUTION):
    mask = np.zeros((res, res), dtype=bool)
    mask[16:48, 16:48] = True
    return mask


def test_candidate_gain_full_match_beats_overshoot():
    res = 32
    target = np.zeros((res, res), dtype=bool)
    target[8:24, 8:24] = True

    exact = target.copy()
    oversized = np.ones((res, res), dtype=bool)  # covers everything, including well outside target

    residual = target.copy()
    exact_gain = candidate_gain(exact, residual, target)
    oversized_gain = candidate_gain(oversized, residual, target)
    assert exact_gain > oversized_gain


def test_candidate_gain_no_new_coverage_scores_zero_or_less():
    res = 16
    target = np.ones((res, res), dtype=bool)
    residual = np.zeros((res, res), dtype=bool)  # already fully covered
    candidate = np.ones((res, res), dtype=bool)
    assert candidate_gain(candidate, residual, target) <= 0


def test_fit_silhouette_empty_target_returns_no_placements():
    empty = np.zeros((DEFAULT_RESOLUTION, DEFAULT_RESOLUTION), dtype=bool)
    assert fit_silhouette(empty) == []


def test_fit_silhouette_plain_square_converges_to_one_shape():
    placed = fit_silhouette(_square_target(), max_layers=8)
    assert len(placed) == 1


def test_fit_silhouette_covers_most_of_a_simple_target():
    target = _square_target()
    placed = fit_silhouette(target, max_layers=8)
    covered = np.zeros_like(target)
    for p in placed:
        shape = PRIMITIVE_CATALOG[p.shape_id]
        covered |= render_candidate(shape, p.cx, p.cy, p.scale_x, p.scale_y, p.rotation_deg, DEFAULT_RESOLUTION)
    intersection = np.count_nonzero(covered & target)
    union = np.count_nonzero(covered | target)
    iou = intersection / union
    assert iou > 0.85


# --- rasterize_contours: fill/hole by nesting, not contour order -----------

def _square(cx, cy, half):
    return [(cx - half, cy - half), (cx + half, cy - half), (cx + half, cy + half), (cx - half, cy + half)]


def _to_px(x, y, resolution=DEFAULT_RESOLUTION):
    from forza_writer.primitive_fit import COORD_RANGE
    px = (x + COORD_RANGE) / (2 * COORD_RANGE) * resolution
    py = (COORD_RANGE - y) / (2 * COORD_RANGE) * resolution
    return int(px), int(py)


def test_rasterize_contours_true_nested_hole_is_subtracted():
    # A ring: contour 0 = big outer square, contour 1 = small square hole
    # fully inside it.
    outer = _square(0, 0, 90)
    hole = _square(0, 0, 30)
    mask = rasterize_contours([outer, hole], DEFAULT_RESOLUTION)
    hx, hy = _to_px(0, 0)  # the hole's own centre: must stay unfilled
    assert not mask[hy, hx]
    ex, ey = _to_px(60, 0)  # inside the outer square, outside the hole
    assert mask[ey, ex]


def test_rasterize_contours_nested_hole_is_order_independent():
    # Same ring as above, but with the hole listed *first*: order must not
    # matter, only geometric nesting. A rule like "contour 0 is always the
    # outer boundary" would get this case wrong.
    outer = _square(0, 0, 90)
    hole = _square(0, 0, 30)
    mask_hole_first = rasterize_contours([hole, outer], DEFAULT_RESOLUTION)
    mask_outer_first = rasterize_contours([outer, hole], DEFAULT_RESOLUTION)
    assert np.array_equal(mask_hole_first, mask_outer_first)


def test_rasterize_contours_disjoint_components_both_fill():
    # Two separate, non-overlapping squares (e.g. a letter's main stroke
    # plus a disjoint decorative accent mark, as on real glyphs like
    # Jokerman's 'K'/'E', where the decorative accent is contour 0). Filling
    # by nesting rather than by "contour 0 = outer, rest = holes" matters
    # here: the latter rule would subtract the real letterform from the tiny
    # accent, leaving almost nothing. Neither square is nested in the other,
    # so both must end up filled, regardless of which is listed first.
    left = _square(-60, 0, 20)
    right = _square(60, 0, 20)
    mask = rasterize_contours([left, right], DEFAULT_RESOLUTION)
    assert mask.sum() > 0
    solo_left = rasterize_contours([left], DEFAULT_RESOLUTION)
    solo_right = rasterize_contours([right], DEFAULT_RESOLUTION)
    # Union, not one cancelling the other out.
    assert mask.sum() == pytest.approx(solo_left.sum() + solo_right.sum(), abs=4)


def test_placements_to_shapes_structure():
    placements = [PlacedShape(shape_id="square", cx=DEFAULT_RESOLUTION / 2, cy=DEFAULT_RESOLUTION / 2,
                               scale_x=0.5, scale_y=0.5, rotation_deg=0.0)]
    shapes = placements_to_shapes(placements, DEFAULT_RESOLUTION)
    assert len(shapes) == 1
    shape = shapes[0]
    assert len(shape["data"]) == 7
    assert shape["type_word"] == resource_to_shape_word("Primitives", PRIMITIVE_CATALOG["square"].resource_index)
    assert shape["type"] == resource_to_typecode("Primitives", PRIMITIVE_CATALOG["square"].resource_index)
    assert shape["color"] == [255, 255, 255, 255]


def test_placements_to_shapes_centered_placement_is_near_origin():
    # A candidate centered on the canvas should land near (0, 0) in glyph space.
    placements = [PlacedShape(shape_id="circle", cx=DEFAULT_RESOLUTION / 2, cy=DEFAULT_RESOLUTION / 2,
                               scale_x=0.5, scale_y=0.5, rotation_deg=0.0)]
    shapes = placements_to_shapes(placements, DEFAULT_RESOLUTION)
    x, y = shapes[0]["data"][0], shapes[0]["data"][1]
    assert abs(x) < 1e-6
    assert abs(y) < 1e-6


def test_placements_to_shapes_y_is_flipped_like_layout_py():
    # A placement in the top half of the canvas (small cy_px, "up" visually)
    # should produce a positive glyph-space y before negation, i.e. a
    # negative final y in the exported data, matching layout.py's `-y`.
    top = PlacedShape(shape_id="circle", cx=DEFAULT_RESOLUTION / 2, cy=1.0,
                       scale_x=0.3, scale_y=0.3, rotation_deg=0.0)
    bottom = PlacedShape(shape_id="circle", cx=DEFAULT_RESOLUTION / 2, cy=DEFAULT_RESOLUTION - 1.0,
                          scale_x=0.3, scale_y=0.3, rotation_deg=0.0)
    top_y = placements_to_shapes([top], DEFAULT_RESOLUTION)[0]["data"][1]
    bottom_y = placements_to_shapes([bottom], DEFAULT_RESOLUTION)[0]["data"][1]
    assert top_y < 0
    assert bottom_y > 0


def test_shape_to_render_params_round_trips_with_placements_to_shapes():
    original = PlacedShape(shape_id="triangle", cx=40.0, cy=15.0,
                            scale_x=0.6, scale_y=0.45, rotation_deg=37.5)
    shapes = placements_to_shapes([original], DEFAULT_RESOLUTION, glyph_size=300.0)
    shape_id, cx_px, cy_px, scale_x, scale_y, rotation_deg, skew_x = shape_to_render_params(
        shapes[0], DEFAULT_RESOLUTION, glyph_size=300.0)

    assert shape_id == "triangle"
    assert cx_px == pytest.approx(original.cx, abs=1e-3)
    assert cy_px == pytest.approx(original.cy, abs=1e-3)
    assert scale_x == pytest.approx(original.scale_x, abs=1e-3)
    assert scale_y == pytest.approx(original.scale_y, abs=1e-3)
    assert rotation_deg == pytest.approx(original.rotation_deg, abs=1e-3)
    assert skew_x == 0.0


def test_skew_round_trips_through_fh6_data_and_changes_render():
    placement = PlacedShape(
        shape_id="square", cx=DEFAULT_RESOLUTION / 2, cy=DEFAULT_RESOLUTION / 2,
        scale_x=0.25, scale_y=0.75, rotation_deg=0.0, skew_x=0.36)
    shape = placements_to_shapes([placement], DEFAULT_RESOLUTION)[0]

    assert shape["data"][5] == pytest.approx(0.36)
    shape_id, cx, cy, sx, sy, rotation, skew_x = shape_to_render_params(
        shape, DEFAULT_RESOLUTION)
    assert skew_x == pytest.approx(0.36)

    primitive = PRIMITIVE_CATALOG[shape_id]
    skewed = render_candidate(
        primitive, cx, cy, sx, sy, rotation, DEFAULT_RESOLUTION, skew_x)
    plain = render_candidate(
        primitive, cx, cy, sx, sy, rotation, DEFAULT_RESOLUTION, 0.0)
    assert not np.array_equal(skewed, plain)
    assert skewed.sum() == pytest.approx(plain.sum(), rel=0.08)


def test_shape_to_render_params_unknown_type_word_returns_none_shape_id():
    shape = {"type": 999999, "type_word": 0, "data": [0, 0, 1, 1, 0, 0, 0], "color": [255, 255, 255, 255]}
    shape_id, *_ = shape_to_render_params(shape, DEFAULT_RESOLUTION)
    assert shape_id is None


# --- strategy routing -------------------------------------------------------

def _blocky_e_contour():
    return [[(66.67, -100.0), (-66.67, -100.0), (-66.67, 100.0), (66.67, 100.0),
             (66.67, 66.67), (-33.33, 66.67), (-33.33, 16.67), (16.67, 16.67),
             (16.67, -16.67), (-33.33, -16.67), (-33.33, -66.67), (66.67, -66.67)]]


def _circle_contour(n=48, r=90.0):
    import math
    return [[(r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n))
             for i in range(n)]]


def test_rectilinear_glyph_routes_to_rect_decomposition():
    placements, strategy = fit_placements(_blocky_e_contour(), DEFAULT_RESOLUTION)
    assert strategy == "rect_decompose"
    # The blocky 'E' is exactly four rectangles. An unrouted primitive search
    # would need far more shapes to approximate the same silhouette, which is
    # why rect_decompose exists as a dedicated path for rectilinear glyphs.
    assert len(placements) == 4
    assert all(p.shape_id == "square" for p in placements)


def test_rect_decomposition_of_a_blocky_glyph_is_an_exact_cover():
    placements, _ = fit_placements(_blocky_e_contour(), DEFAULT_RESOLUTION)
    target = rasterize_contours(_blocky_e_contour(), DEFAULT_RESOLUTION)
    covered = np.zeros_like(target)
    for p in placements:
        covered |= render_candidate(PRIMITIVE_CATALOG[p.shape_id], p.cx, p.cy,
                                     p.scale_x, p.scale_y, p.rotation_deg, DEFAULT_RESOLUTION)
    assert np.array_equal(covered, target)


def test_curved_glyph_routes_to_primitive_search():
    _placements, strategy = fit_placements(_circle_contour(), DEFAULT_RESOLUTION)
    assert strategy == "primitive_search"


def test_curved_glyph_does_not_explode_into_many_rectangles():
    # Unrouted rectangle decomposition needs ~18 rects for a circle; the
    # search should keep it far below that.
    placements, _ = fit_placements(_circle_contour(), DEFAULT_RESOLUTION)
    assert len(placements) < 10


def _comb_contour():
    """A 3-prong comb: direct-fills in 4 rectangles (1 bar + 3 prongs), but
    only needs 1 background + 2 gap-cutouts as a stencil. This is the shape
    where stencil actually wins, unlike every real Amarillo USAF glyph
    (there, stencil never beats or only ties direct: see
    tests/test_rect_decompose.py's comb-mask test for the same result at
    the mask level). Using it as a real polygon contour here, rather than
    just a raster mask, proves the routing works end-to-end from actual
    glyph geometry."""
    return [[(-50, -60), (50, -60), (50, 60), (30, 60), (30, -20), (10, -20),
             (10, 60), (-10, 60), (-10, -20), (-30, -20), (-30, 60), (-50, 60)]]


def test_stencil_wins_end_to_end_on_a_comb_glyph():
    placements, strategy = fit_placements(_comb_contour(), DEFAULT_RESOLUTION)
    assert strategy == "stencil"
    assert len(placements) == 3
    assert sum(1 for p in placements if p.is_mask) == 2
    assert sum(1 for p in placements if not p.is_mask) == 1


def test_stencil_cover_of_comb_glyph_is_exact():
    placements, _ = fit_placements(_comb_contour(), DEFAULT_RESOLUTION)
    target = rasterize_contours(_comb_contour(), DEFAULT_RESOLUTION)
    covered = np.zeros_like(target)
    for p in placements:
        shape_mask = render_candidate(PRIMITIVE_CATALOG[p.shape_id], p.cx, p.cy,
                                       p.scale_x, p.scale_y, p.rotation_deg, DEFAULT_RESOLUTION)
        covered = (covered & ~shape_mask) if p.is_mask else (covered | shape_mask)
    assert np.array_equal(covered, target)


def test_mask_mode_never_forces_direct_even_when_stencil_would_win():
    # Same comb glyph as test_stencil_wins_end_to_end_on_a_comb_glyph,
    # where stencil genuinely needs fewer shapes (3 vs 4): mask_mode="never"
    # must still force the more-shapes direct fill.
    placements, strategy = fit_placements(_comb_contour(), DEFAULT_RESOLUTION, mask_mode="never")
    assert strategy == "rect_decompose"
    assert all(not p.is_mask for p in placements)
    assert len(placements) == 4


def test_mask_mode_auto_is_the_default():
    _placements, strategy = fit_placements(_comb_contour(), DEFAULT_RESOLUTION)
    assert strategy == "stencil"


def test_mask_mode_force_picks_stencil_even_on_a_tie():
    # 'I' ties at 1 shape either way (see test_direct_wins_ties_over_stencil,
    # where "auto" prefers direct on the tie); "force" must pick the
    # stencil cover regardless.
    i_contour = [[(-15, -100), (15, -100), (15, 100), (-15, 100)]]
    placements, strategy = fit_placements(i_contour, DEFAULT_RESOLUTION, mask_mode="force")
    assert strategy == "stencil"
    assert len(placements) == 1
    assert placements[0].is_mask is False  # background only, no negative space to cut


# --- curved-glyph stencil (mask forcing on non-rectilinear glyphs) ---------

def test_curved_stencil_placements_on_circle_has_one_background_and_some_cutouts():
    target = rasterize_contours(_circle_contour(), DEFAULT_RESOLUTION)
    placements = _curved_stencil_placements(target, DEFAULT_RESOLUTION)
    assert placements is not None
    assert placements[0].is_mask is False  # background is always first
    assert all(p.is_mask for p in placements[1:])  # everything else is a cutout
    assert len(placements) > 1  # a circle's corners are real negative space to cut


def test_curved_stencil_placements_returns_none_with_no_negative_space():
    # A target that already fills its own bounding box exactly (no corners
    # to cut) has nothing for a stencil to buy over direct fill.
    target = _square_target()
    assert _curved_stencil_placements(target, DEFAULT_RESOLUTION) is None


def test_fit_placements_force_mode_on_curved_glyph_uses_stencil_search():
    # A curved glyph forced into a mask cover via the negative-space search
    # rather than an exact rectangle cover.
    placements, strategy = fit_placements(_circle_contour(), DEFAULT_RESOLUTION, mask_mode="force")
    assert strategy == "stencil_search"
    assert any(not p.is_mask for p in placements)
    assert any(p.is_mask for p in placements)


def test_fit_placements_auto_mode_never_runs_curved_stencil_search(monkeypatch):
    # Performance guardrail: "auto" must stay cheap. It must never attempt
    # the extra negative-space search; only an explicit "force" may pay for it.
    def boom(*_args, **_kwargs):
        raise AssertionError("auto mode must not call _curved_stencil_placements")

    monkeypatch.setattr(primitive_fit_module, "_curved_stencil_placements", boom)
    _placements, strategy = fit_placements(_circle_contour(), DEFAULT_RESOLUTION, mask_mode="auto")
    assert strategy == "primitive_search"


def test_fit_placements_never_mode_on_curved_glyph_is_unaffected():
    placements, strategy = fit_placements(_circle_contour(), DEFAULT_RESOLUTION, mask_mode="never")
    assert strategy == "primitive_search"
    assert all(not p.is_mask for p in placements)


def test_direct_wins_ties_over_stencil():
    # 'I' is the real-world tie case: direct decomposes to exactly 1 rect
    # (fills its own bbox completely), and stencil is background(1) +
    # cutouts(0, no negative space at all) = 1 too. Direct must be
    # preferred: it needs no mask-layer semantics.
    i_contour = [[(-15, -100), (15, -100), (15, 100), (-15, 100)]]
    placements, strategy = fit_placements(i_contour, DEFAULT_RESOLUTION)
    assert strategy == "rect_decompose"
    assert len(placements) == 1
    assert placements[0].is_mask is False


def test_placements_to_shapes_mask_flag_sets_color_and_data6():
    mask_shape = PlacedShape(shape_id="square", cx=DEFAULT_RESOLUTION / 2, cy=DEFAULT_RESOLUTION / 2,
                              scale_x=0.5, scale_y=0.5, rotation_deg=0.0, is_mask=True)
    shape = placements_to_shapes([mask_shape], DEFAULT_RESOLUTION)[0]
    assert shape["mask"] is True
    assert shape["data"][6] == 1
    assert shape["color"] == [0, 0, 0, 255]


def test_placements_to_shapes_non_mask_flag_unaffected():
    normal_shape = PlacedShape(shape_id="square", cx=DEFAULT_RESOLUTION / 2, cy=DEFAULT_RESOLUTION / 2,
                                scale_x=0.5, scale_y=0.5, rotation_deg=0.0)
    shape = placements_to_shapes([normal_shape], DEFAULT_RESOLUTION)[0]
    assert shape["mask"] is False
    assert shape["data"][6] == 0
    assert shape["color"] == [255, 255, 255, 255]


# --- preview_glyph_mask_options (Advanced Mode's per-glyph summary) -------

@requires_font
def test_preview_glyph_mask_options_on_rectilinear_glyph_is_cheap_and_exact():
    # Amarillo USAF's 'E' is rectilinear and stencil never wins there (see
    # elsewhere in this suite), but forcing it must still report an exact
    # (IoU 1.0) cover, since the rectilinear path is exact either way.
    info = preview_glyph_mask_options("E", AMARILLO_FONT)
    assert info["rectilinear"] is True
    assert info["auto_strategy"] == "rect_decompose"
    if info["can_force_mask"]:
        assert info["forced_iou"] == 1.0


@requires_font
def test_preview_glyph_mask_options_auto_never_reports_a_masked_curved_glyph():
    # A curved glyph's "auto" strategy is always primitive_search (no mask)
    # by construction; the "force" fields describe a hypothetical, not what
    # "auto" would actually produce.
    info = preview_glyph_mask_options("O", AMARILLO_FONT)
    if not info["rectilinear"]:
        assert info["auto_strategy"] == "primitive_search"
