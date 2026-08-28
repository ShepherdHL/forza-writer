import numpy as np

from forza_writer.primitive_fit import DEFAULT_RESOLUTION, render_candidate
from forza_writer.primitive_shapes import PRIMITIVE_CATALOG
from forza_writer.rect_decompose import (
    decompose_mask_to_rects,
    decompose_negative_space,
    is_rectilinear,
    rects_to_placements,
    stencil_placements,
)


def _rect_contour(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


COMB_SIZE = 46


def _comb_mask():
    """Bottom bar + 5 thin prongs separated by 4 gaps: a shape where the
    ink needs more rectangles to fill directly than the gaps need to cut.
    Bar spans exactly the prongs' extent (no overhang) so the negative
    space is exactly the 4 inter-prong gaps, nothing more. Square canvas
    (COMB_SIZE x COMB_SIZE) to match how render_candidate/stencil_placements
    are actually used elsewhere: both assume a single square resolution."""
    mask = np.zeros((COMB_SIZE, COMB_SIZE), dtype=bool)
    mask[20:24, 1:40] = True  # bar
    for i in range(5):
        x0 = 1 + i * 9
        mask[2:24, x0:x0 + 3] = True  # prong
    return mask


# --- rectilinear detection -------------------------------------------------

def test_axis_aligned_rectangle_is_rectilinear():
    assert is_rectilinear([_rect_contour(-50, -50, 50, 50)]) is True


def test_blocky_e_shape_is_rectilinear():
    # The real Amarillo 'E' outline: 12 points, all edges axis-aligned.
    e = [(66.67, -100.0), (-66.67, -100.0), (-66.67, 100.0), (66.67, 100.0),
         (66.67, 66.67), (-33.33, 66.67), (-33.33, 16.67), (16.67, 16.67),
         (16.67, -16.67), (-33.33, -16.67), (-33.33, -66.67), (66.67, -66.67)]
    assert is_rectilinear([e]) is True


def test_diagonal_edge_is_not_rectilinear():
    triangle = [(-50.0, -50.0), (50.0, -50.0), (0.0, 50.0)]
    assert is_rectilinear([triangle]) is False


def test_empty_contours_are_not_rectilinear():
    assert is_rectilinear([]) is False


def test_tolerance_absorbs_small_outline_noise():
    # Curve flattening leaves sub-unit residuals; those must not disqualify
    # an otherwise blocky glyph.
    almost = [(-50.0, -50.0), (50.0, -50.3), (50.2, 50.0), (-50.0, 50.0)]
    assert is_rectilinear([almost]) is True


# --- decomposition ---------------------------------------------------------

def test_solid_rectangle_decomposes_to_one_rect():
    mask = np.zeros((32, 32), dtype=bool)
    mask[8:24, 4:28] = True
    rects = decompose_mask_to_rects(mask)
    assert len(rects) == 1
    top, left, height, width = rects[0]
    assert (top, left, height, width) == (8, 4, 16, 24)


def test_empty_mask_decomposes_to_nothing():
    assert decompose_mask_to_rects(np.zeros((16, 16), dtype=bool)) == []


def test_l_shape_decomposes_to_two_rects():
    mask = np.zeros((32, 32), dtype=bool)
    mask[4:28, 4:12] = True     # vertical stem
    mask[20:28, 4:28] = True    # foot
    rects = decompose_mask_to_rects(mask)
    assert len(rects) == 2


def test_decomposition_never_covers_outside_the_mask():
    mask = np.zeros((32, 32), dtype=bool)
    mask[4:28, 4:12] = True
    mask[20:28, 4:28] = True
    for top, left, height, width in decompose_mask_to_rects(mask):
        assert mask[top:top + height, left:left + width].all()


def test_decomposition_respects_max_rects():
    rng = np.random.default_rng(0)
    noisy = rng.random((24, 24)) > 0.5
    assert len(decompose_mask_to_rects(noisy, max_rects=5)) <= 5


# --- placement conversion --------------------------------------------------

def test_rects_to_placements_are_all_squares_with_exact_scales():
    rects = [(8, 4, 16, 24)]
    placements = rects_to_placements(rects, 64)
    assert len(placements) == 1
    p = placements[0]
    assert p.shape_id == "square"
    assert p.rotation_deg == 0.0
    assert p.is_mask is False
    assert p.cx == 4 + 24 / 2
    assert p.cy == 8 + 16 / 2
    assert p.scale_x == 24 / 64
    assert p.scale_y == 16 / 64


def test_rects_to_placements_is_mask_flag():
    placements = rects_to_placements([(0, 0, 4, 4)], 32, is_mask=True)
    assert placements[0].is_mask is True


def test_decomposition_round_trips_to_an_exact_cover():
    # The whole point of this path: rendering the placements back must
    # reproduce the mask exactly, with zero overshoot.
    res = DEFAULT_RESOLUTION
    mask = np.zeros((res, res), dtype=bool)
    mask[8:56, 8:20] = True     # stem
    mask[8:20, 20:52] = True    # arm
    rects = decompose_mask_to_rects(mask)
    covered = np.zeros_like(mask)
    for p in rects_to_placements(rects, res):
        covered |= render_candidate(PRIMITIVE_CATALOG[p.shape_id], p.cx, p.cy,
                                     p.scale_x, p.scale_y, p.rotation_deg, res)
    assert np.array_equal(covered, mask)


# --- negative space / stencil -----------------------------------------------

def test_negative_space_of_a_solid_rectangle_is_empty():
    mask = np.zeros((32, 32), dtype=bool)
    mask[4:28, 4:28] = True
    assert decompose_negative_space(mask) == []


def test_negative_space_of_empty_mask_is_none():
    assert decompose_negative_space(np.zeros((16, 16), dtype=bool)) is None


def test_negative_space_finds_a_single_notch():
    mask = np.zeros((32, 32), dtype=bool)
    mask[4:28, 4:28] = True
    mask[4:16, 20:28] = False  # bite a notch out of the top-right corner
    negative = decompose_negative_space(mask)
    assert len(negative) == 1
    assert negative[0] == (4, 20, 12, 8)


def test_stencil_placements_is_background_plus_cutouts():
    mask = np.zeros((32, 32), dtype=bool)
    mask[4:28, 4:28] = True
    mask[4:16, 20:28] = False
    placements = stencil_placements(mask, 32)
    assert len(placements) == 2
    background, cutout = placements
    assert background.is_mask is False
    assert cutout.is_mask is True


def test_stencil_placements_none_for_empty_mask():
    assert stencil_placements(np.zeros((16, 16), dtype=bool), 16) is None


def test_stencil_placements_none_when_negative_space_exceeds_cap():
    rng = np.random.default_rng(1)
    noisy = rng.random((24, 24)) > 0.5
    assert stencil_placements(noisy, 24, max_rects=1) is None


def test_stencil_beats_direct_on_a_comb_shape():
    # A shape genuinely cheaper as a stencil: a bar with several thin
    # prongs needs one rectangle per prong to fill directly, but only one
    # cutout per gap between prongs to cut as a stencil, and there's one
    # fewer gap than prong (5 prongs -> 4 gaps).
    mask = _comb_mask()
    direct = decompose_mask_to_rects(mask)
    stencil = stencil_placements(mask, COMB_SIZE)
    assert len(direct) == 6
    assert len(stencil) == 5


def test_stencil_cover_is_visually_correct_via_masked_render():
    # Render the stencil the way a mask actually behaves: paint the
    # background, then erase wherever a cutout covers. Must reproduce the
    # exact original mask.
    mask = _comb_mask()
    covered = np.zeros((COMB_SIZE, COMB_SIZE), dtype=bool)
    for p in stencil_placements(mask, COMB_SIZE):
        shape_mask = render_candidate(PRIMITIVE_CATALOG[p.shape_id], p.cx, p.cy,
                                       p.scale_x, p.scale_y, p.rotation_deg, COMB_SIZE)
        if p.is_mask:
            covered &= ~shape_mask
        else:
            covered |= shape_mask
    assert np.array_equal(covered, mask)
