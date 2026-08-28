from forza_writer.ascii_grid import (
    layout_ascii_grid,
    normalize_block,
    scan_unsupported,
    supported_chars,
)
from forza_writer.shapes import char_to_resource, resource_to_shape_word


def test_normalize_block_pads_ragged_lines_to_equal_width():
    rows = normalize_block("AB\nC\nDEFG")
    assert rows == ["AB  ", "C   ", "DEFG"]
    assert len({len(r) for r in rows}) == 1


def test_normalize_block_expands_tabs_and_drops_trailing_blank_lines():
    rows = normalize_block("A\tB\n\n")
    assert rows[0].startswith("A")
    assert rows[-1] != ""


def test_normalize_block_handles_crlf():
    assert normalize_block("AB\r\nCD") == ["AB", "CD"]


def test_supported_chars_matches_char_to_resource():
    supported = supported_chars(font=1)
    assert "A" in supported
    assert "a" in supported
    assert "%" in supported
    for char in supported:
        assert char_to_resource(char, font=1) is not None


def test_supported_chars_identical_across_fonts():
    # char_to_resource only changes which family a char comes from, never
    # which chars are supported: coverage must not vary by font number.
    assert supported_chars(font=1) == supported_chars(font=11)


def test_supported_chars_includes_digits_and_upper_symbols():
    # These must be supported per the KFPS glyph-mismatch report (see shapes.py).
    supported = supported_chars(font=1)
    for char in "0123456789!?&":
        assert char in supported


def test_supported_chars_excludes_common_ascii_art_punctuation():
    # Documents the current coverage gap rather than asserting a wishlist.
    # If these ever become supported, update this test alongside
    # ascii_grid.py's module docstring.
    supported = supported_chars(font=1)
    for char in ".,'`\"~-_<>*|(){}[]\\=":
        assert char not in supported


def test_scan_unsupported_ignores_spaces():
    rows = normalize_block("A B")
    assert scan_unsupported(rows, font=1) == {}


def test_scan_unsupported_reports_locations():
    rows = normalize_block("A.B\nC.D")
    result = scan_unsupported(rows, font=1)
    assert result == {".": [(0, 1), (1, 1)]}


def test_layout_ascii_grid_cell_advance_is_constant_regardless_of_glyph():
    # The whole point of a grid import (vs. layout_forza_text's variable
    # advance) is that every column lines up: verify blank, supported, and
    # unsupported cells all consume exactly one cell width.
    rows = normalize_block("A B.")
    shapes = layout_ascii_grid(rows, font=1, cell_width=10.0, cell_height=10.0)
    # Only 'A' and 'B' produce shapes (space is blank, '.' is unsupported).
    assert len(shapes) == 2
    xs = sorted(s["data"][0] for s in shapes)
    # Column 0 ('A') and column 2 ('B') are two cell-widths apart.
    assert xs[1] - xs[0] == 20.0


def test_layout_ascii_grid_remap_forces_blank():
    rows = normalize_block("AB")
    with_glyph = layout_ascii_grid(rows, font=1)
    assert len(with_glyph) == 2
    blanked = layout_ascii_grid(rows, font=1, remap={"B": None})
    assert len(blanked) == 1


def test_layout_ascii_grid_remap_substitutes_supported_char():
    rows = normalize_block(".")
    shapes = layout_ascii_grid(rows, font=1, remap={".": "o"})
    assert len(shapes) == 1
    family, index = char_to_resource("o", font=1)
    assert shapes[0]["type_word"] == resource_to_shape_word(family, index)


def test_layout_ascii_grid_multirow_row_advance():
    rows = normalize_block("A\nB")
    shapes = layout_ascii_grid(rows, font=1, cell_width=10.0, cell_height=15.0)
    assert len(shapes) == 2
    ys = sorted(s["data"][1] for s in shapes)
    assert ys[1] - ys[0] == 15.0


def test_layout_ascii_grid_color_applied():
    rows = normalize_block("A")
    shapes = layout_ascii_grid(rows, font=1, color=(10, 20, 30, 255))
    assert shapes[0]["color"] == [10, 20, 30, 255]
