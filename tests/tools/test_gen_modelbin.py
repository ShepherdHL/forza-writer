import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "tools"))
from gen_modelbin import (  # noqa: E402
    extract_contours,
    generate_glyph,
    group_contours_by_nesting,
    normalize_to_128,
    read_mesh_triangles,
    triangulate,
    validate_modelbin,
)

AMARILLO_FONT = Path.home() / "Desktop" / "amarillo-usaf" / "amarurgt.ttf"
REFERENCE_MODELBIN = Path(__file__).resolve().parent.parent.parent / "user-assets" / "S_01.modelbin"
requires_assets = pytest.mark.skipif(
    not (AMARILLO_FONT.exists() and REFERENCE_MODELBIN.exists()),
    reason="test font or reference modelbin not present on this machine")

JOKERMAN_FONT = Path(r"C:\Windows\Fonts\JOKERMAN.TTF")
requires_jokerman = pytest.mark.skipif(not JOKERMAN_FONT.exists(),
                                        reason="Jokerman not installed on this machine")


@requires_assets
def test_read_mesh_triangles_matches_validate_modelbin_counts(tmp_path):
    out_path = tmp_path / "A.modelbin"
    generate_glyph("A", AMARILLO_FONT, REFERENCE_MODELBIN, out_path, curve_segments=8)
    ok, message = validate_modelbin(out_path)
    assert ok, message

    vertices, triangles = read_mesh_triangles(out_path)
    # validate_modelbin's success message embeds "<N> verts ... <M> indices".
    # Cross-check against it rather than re-deriving expected counts, since
    # that message is already proven correct by validate_modelbin's own
    # consistency checks.
    assert f"{len(vertices)} verts" in message
    assert f"{len(triangles) * 3} indices" in message


@requires_assets
def test_read_mesh_triangles_indices_in_bounds(tmp_path):
    out_path = tmp_path / "S.modelbin"
    generate_glyph("S", AMARILLO_FONT, REFERENCE_MODELBIN, out_path, curve_segments=8)
    vertices, triangles = read_mesh_triangles(out_path)
    for a, b, c in triangles:
        assert 0 <= a < len(vertices)
        assert 0 <= b < len(vertices)
        assert 0 <= c < len(vertices)


@requires_assets
def test_read_mesh_triangles_coordinates_in_expected_range(tmp_path):
    # build_modelbin works in a roughly +-128 space (SNORM16-backed).
    out_path = tmp_path / "O.modelbin"
    generate_glyph("O", AMARILLO_FONT, REFERENCE_MODELBIN, out_path, curve_segments=8)
    vertices, _triangles = read_mesh_triangles(out_path)
    for x, y in vertices:
        assert -130 <= x <= 130
        assert -130 <= y <= 130


def test_read_mesh_triangles_raises_on_malformed_file(tmp_path):
    bad = tmp_path / "bad.modelbin"
    bad.write_bytes(b"not a real modelbin file")
    with pytest.raises(ValueError):
        read_mesh_triangles(bad)


def test_read_mesh_triangles_raises_on_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_mesh_triangles(tmp_path / "does_not_exist.modelbin")


# --- group_contours_by_nesting / triangulate: fill/hole by containment, ----
# --- not contour order -------------------------------------------------

def _square(cx, cy, half):
    return [(cx - half, cy - half), (cx + half, cy - half), (cx + half, cy + half), (cx - half, cy + half)]


def test_group_contours_true_nested_hole_becomes_one_island_with_a_hole():
    outer, hole = _square(0, 0, 90), _square(0, 0, 30)
    groups = group_contours_by_nesting([outer, hole])
    assert groups == [(0, [1])]


def test_group_contours_order_independent_for_nested_hole():
    outer, hole = _square(0, 0, 90), _square(0, 0, 30)
    groups_outer_first = group_contours_by_nesting([outer, hole])
    groups_hole_first = group_contours_by_nesting([hole, outer])
    # Same geometric result either way: one island, outer=the big square,
    # holes=[the small square], just re-indexed for the swapped input order.
    outer_idx, holes = groups_hole_first[0]
    assert outer_idx == 1
    assert holes == [0]
    assert len(groups_outer_first) == len(groups_hole_first) == 1


def test_group_contours_disjoint_components_become_separate_islands():
    # Same shape of bug as Jokerman's 'K': two disjoint (non-nested)
    # contours must each get their own island, not one treated as a hole
    # cut from the other.
    left, right = _square(-60, 0, 20), _square(60, 0, 20)
    groups = group_contours_by_nesting([left, right])
    assert len(groups) == 2
    assert all(holes == [] for _outer, holes in groups)


def test_triangulate_true_hole_produces_no_triangles_inside_it():
    outer, hole = _square(0, 0, 90), _square(0, 0, 30)
    verts, tris = triangulate([outer, hole])
    for a, b, c in tris:
        cx = (verts[a][0] + verts[b][0] + verts[c][0]) / 3
        cy = (verts[a][1] + verts[b][1] + verts[c][1]) / 3
        assert not (-30 < cx < 30 and -30 < cy < 30)  # no triangle centroid lands inside the hole


def test_triangulate_disjoint_components_both_produce_triangles():
    # Guards against the disjoint-contour failure mode seen on Jokerman's
    # K/E: a "contour 0 = outer, rest = holes" rule would triangulate only
    # whichever contour happened to be listed first and treat the other as
    # a (nonsensical, disjoint) hole cut from it, silently losing it.
    # Grouping must be based on geometric nesting, not list order.
    left, right = _square(-60, 0, 20), _square(60, 0, 20)
    verts, tris = triangulate([left, right])
    assert len(tris) > 0
    xs_covered = [verts[i][0] for tri in tris for i in tri]
    assert any(x < -20 for x in xs_covered)  # left square's own triangles present
    assert any(x > 20 for x in xs_covered)   # right square's own triangles present


@requires_jokerman
def test_triangulate_real_jokerman_k_recovers_the_letterform():
    # Jokerman 'K' has 5 disjoint contours: the stroke plus 4 sparkle
    # accents, with a sparkle listed first. Nesting-based grouping must
    # triangulate the whole glyph rather than treating the real letterform
    # as a "hole" cut from the tiny first accent, so its triangle count
    # should be comparable to a similarly simple letter like 'J'.
    contours_k, upm = extract_contours("K", JOKERMAN_FONT, 8)
    verts_k, tris_k = triangulate(normalize_to_128(contours_k, upm))
    contours_j, _ = extract_contours("J", JOKERMAN_FONT, 8)
    verts_j, tris_j = triangulate(normalize_to_128(contours_j, upm))
    assert len(tris_k) > len(tris_j) * 0.5
