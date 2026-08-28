"""Pins the Primitives catalog's resource indices.

`resource_index` decides which vinyl FH6 actually renders, and a wrong one
fails silently: the glyph still builds, the fitter still reports a good
cover, and the mistake only shows up as the wrong shape in-game. So the
whole id -> index mapping is asserted literally here rather than spot-checked.

Indices come from the in-game shape picker (Page 1 "Primitives"), a
4-row x 10-column grid filled column-major:
`resource_index = (column - 1) * 4 + row`. See `FH6 - Vinyl Shape Codes.xlsx`
and the provenance note in `forza_writer.primitive_shapes`' docstring --
in particular, KFPS's shape-names.json misnames slots 7 and 27, so
`rounded_square` and `quarter_circle` must not be pinned to those slots.
"""

import pytest

from forza_writer.primitive_shapes import MASK_RESOLUTION, PRIMITIVE_CATALOG
from forza_writer.shapes import resource_to_shape_word, shape_word_to_resource

# shape_id -> (resource_index, display_name, picker row, picker column)
EXPECTED_PRIMITIVES = {
    "square": (1, "Square", 1, 1),
    "circle": (2, "Circle", 2, 1),
    "triangle": (3, "Triangle", 3, 1),
    "right_triangle": (4, "Right Triangle", 4, 1),
    "hexagon": (5, "Hexagon", 1, 2),
    "five_pointed_star": (8, "Five Pointed Star", 4, 2),
    "half_circle": (9, "Half Circle", 1, 3),
    "shield": (10, "Shield", 2, 3),
    "square_border": (11, "Square Border", 3, 3),
    "circle_border": (12, "Circle Border", 4, 3),
    # picker calls this one "Narrowing Rectangle"
    "tapered_rectangle": (20, "Tapered Rectangle", 4, 5),
    "fat_five_pointed_star": (21, "Fat Five Pointed Star", 1, 6),
    # slot 7 is Cut Square, not this: rounded_square must not be pinned there
    "rounded_square": (22, "Rounded Square", 2, 6),
    "ten_pointed_star": (23, "Ten Pointed Star", 3, 6),
    "up_arrow": (25, "Up Arrow", 1, 7),
    # slot 27 is Animal Tooth, not this: quarter_circle must not be pinned there
    "quarter_circle": (30, "Quarter Circle", 2, 8),
    "pentagon": (35, "Pentagon", 3, 9),
}


def test_catalog_covers_exactly_the_expected_shapes():
    assert set(PRIMITIVE_CATALOG) == set(EXPECTED_PRIMITIVES)


@pytest.mark.parametrize("shape_id", sorted(EXPECTED_PRIMITIVES))
def test_resource_index_and_name_are_pinned(shape_id):
    index, name, _row, _col = EXPECTED_PRIMITIVES[shape_id]
    shape = PRIMITIVE_CATALOG[shape_id]
    assert shape.resource_index == index
    assert shape.display_name == name


@pytest.mark.parametrize("shape_id", sorted(EXPECTED_PRIMITIVES))
def test_index_matches_column_major_picker_position(shape_id):
    """The indices above aren't arbitrary: they're the picker grid read
    column-major. Recomputing them from (row, column) catches a slot being
    "fixed" to a value that no longer corresponds to any real grid cell."""
    index, _name, row, col = EXPECTED_PRIMITIVES[shape_id]
    assert (col - 1) * 4 + row == index
    assert 1 <= row <= 4 and 1 <= col <= 10


def test_indices_are_unique():
    indices = [s.resource_index for s in PRIMITIVE_CATALOG.values()]
    assert len(set(indices)) == len(indices)


@pytest.mark.parametrize("shape_id", sorted(EXPECTED_PRIMITIVES))
def test_index_round_trips_through_shape_word(shape_id):
    """Guards the encoding the emitted layers actually carry."""
    index = PRIMITIVE_CATALOG[shape_id].resource_index
    assert shape_word_to_resource(resource_to_shape_word("Primitives", index)) == ("Primitives", index)


@pytest.mark.parametrize("shape_id", sorted(EXPECTED_PRIMITIVES))
def test_masks_are_usable_silhouettes(shape_id):
    mask = PRIMITIVE_CATALOG[shape_id].mask
    assert mask.dtype == bool
    assert mask.shape == (MASK_RESOLUTION, MASK_RESOLUTION)
    assert mask.any(), "silhouette is empty"
