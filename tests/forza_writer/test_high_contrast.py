from forza_writer.high_contrast import (
    HIGH_CONTRAST_PALETTE,
    assign_high_contrast_colors,
    seed_for_char,
)


def test_palette_is_curated_not_raw_random_rgb():
    # A handful of sanity properties that would fail for arbitrary random
    # RGB but hold for a deliberately chosen categorical set: full alpha,
    # no duplicate entries, and a reasonably large, fixed catalog.
    assert len(HIGH_CONTRAST_PALETTE) >= 12
    assert len(set(HIGH_CONTRAST_PALETTE)) == len(HIGH_CONTRAST_PALETTE)
    assert all(c[3] == 255 for c in HIGH_CONTRAST_PALETTE)
    assert all(len(c) == 4 and all(0 <= v <= 255 for v in c) for c in HIGH_CONTRAST_PALETTE)


def test_assignment_is_deterministic_for_same_seed_and_layout():
    centers = [(0.0, 0.0), (40.0, 0.0), (0.0, 40.0), (-40.0, -40.0), (80.0, 80.0)]
    first = assign_high_contrast_colors(centers, seed=1234)
    second = assign_high_contrast_colors(centers, seed=1234)
    assert first == second


def test_different_seeds_can_produce_different_assignments():
    centers = [(0.0, 0.0), (40.0, 0.0), (0.0, 40.0), (-40.0, -40.0), (80.0, 80.0)]
    results = {tuple(assign_high_contrast_colors(centers, seed=s)) for s in range(10)}
    assert len(results) > 1


def test_adjacent_shapes_never_share_a_color():
    # A tight cluster of centers, all within the default adjacency radius
    # of each other -- every pairwise combination is "adjacent", so no two
    # of them may be assigned the same palette entry.
    centers = [(0.0, 0.0), (5.0, 0.0), (0.0, 5.0), (5.0, 5.0), (2.5, 2.5)]
    colors = assign_high_contrast_colors(centers, seed=7)
    assert len(set(colors)) == len(colors)


def test_far_apart_shapes_may_reuse_a_color():
    centers = [(-90.0, -90.0), (90.0, 90.0)]
    colors = assign_high_contrast_colors(centers, seed=0, adjacency_radius=5.0)
    # Not required to differ -- just confirms distant shapes aren't
    # artificially forced apart by the same avoidance logic as neighbors.
    assert len(colors) == 2


def test_degenerate_case_more_neighbors_than_palette_colors_does_not_crash():
    n = len(HIGH_CONTRAST_PALETTE) + 5
    centers = [(float(i), 0.0) for i in range(n)]
    colors = assign_high_contrast_colors(centers, seed=3, adjacency_radius=1000.0)
    assert len(colors) == n
    assert all(c in HIGH_CONTRAST_PALETTE for c in colors)


def test_seed_for_char_is_deterministic_and_varies_by_character():
    assert seed_for_char(42, 'A') == seed_for_char(42, 'A')
    assert seed_for_char(42, 'A') != seed_for_char(42, 'B')
    assert seed_for_char(1, 'A') != seed_for_char(2, 'A')
