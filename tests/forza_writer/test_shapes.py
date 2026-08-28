from forza_writer.shapes import (
    char_to_resource,
    resource_to_shape_word,
    resource_to_typecode,
    shape_word_to_resource,
)


def test_font1_uppercase_a():
    family, index = char_to_resource("A", font=1)
    assert family == "Upper_Letters_1"
    assert index == 1
    assert resource_to_shape_word(family, index) == 1901
    assert resource_to_typecode(family, index) == 1050477


def test_font1_uppercase_z():
    family, index = char_to_resource("Z", font=1)
    assert family == "Upper_Letters_1"
    assert index == 26
    assert resource_to_typecode(family, index) == 1050502


def test_font1_lowercase_a():
    family, index = char_to_resource("a", font=1)
    assert family == "Lower_Letters_1"
    assert index == 1


def test_symbol_mapping():
    # '%' maps to index 37, matching the game meshes (see shapes.py's module
    # docstring for the KFPS glyph-mismatch report this is corrected against).
    family, index = char_to_resource("%", font=1)
    assert family == "Lower_Letters_1"
    assert index == 37


def test_lower_symbol_table_matches_corrected_report():
    expected = {
        "$": 27, "£": 28, "¥": 29, "€": 30, "æ": 31, "^": 32, "ß": 33,
        "@": 34, "#": 35, "+": 36, "%": 37, ";": 38, ":": 39, "/": 40,
    }
    for char, index in expected.items():
        family, actual_index = char_to_resource(char, font=1)
        assert family == "Lower_Letters_1"
        assert actual_index == index


def test_digits_supported_on_upper_page():
    expected = {"1": 27, "2": 28, "3": 29, "4": 30, "5": 31,
                "6": 32, "7": 33, "8": 34, "9": 35, "0": 36}
    for char, index in expected.items():
        family, actual_index = char_to_resource(char, font=1)
        assert family == "Upper_Letters_1"
        assert actual_index == index


def test_upper_symbols_supported():
    for char, index in {"!": 37, "?": 38, "&": 40}.items():
        family, actual_index = char_to_resource(char, font=1)
        assert family == "Upper_Letters_1"
        assert actual_index == index


def test_unsupported_char_returns_none():
    assert char_to_resource(" ", font=1) is None
    assert char_to_resource(".", font=1) is None


def test_font_clamped_to_range():
    family, index = char_to_resource("A", font=99)
    assert family == "Upper_Letters_11"


def test_shape_word_to_resource_round_trips_primitives():
    word = resource_to_shape_word("Primitives", 1)
    assert word == 101
    assert shape_word_to_resource(word) == ("Primitives", 1)


def test_shape_word_to_resource_round_trips_letter_families():
    for family, index in [("Upper_Letters_1", 1), ("Upper_Letters_1", 26), ("Lower_Letters_1", 27)]:
        word = resource_to_shape_word(family, index)
        assert shape_word_to_resource(word) == (family, index)


def test_shape_word_to_resource_unknown_word_returns_none():
    assert shape_word_to_resource(0) is None
