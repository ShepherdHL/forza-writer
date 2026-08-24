from forza_writer.charset import categorize_char, is_han_char


def test_uppercase():
    assert categorize_char("A") == "Uppercase"
    assert categorize_char("Z") == "Uppercase"


def test_lowercase():
    assert categorize_char("a") == "Lowercase"
    assert categorize_char("z") == "Lowercase"


def test_digits():
    assert categorize_char("0") == "Numbers"
    assert categorize_char("9") == "Numbers"


def test_punctuation():
    assert categorize_char("-") == "Punctuation"
    assert categorize_char(".") == "Punctuation"
    assert categorize_char("–") == "Punctuation"  # en dash
    assert categorize_char("—") == "Punctuation"  # em dash


def test_symbols():
    assert categorize_char("$") == "Symbols"
    assert categorize_char("") == "Symbols"  # private-use (e.g. a font logo glyph)


def test_uncased_letters_are_not_symbols():
    assert categorize_char("中") == "Letters"
    assert categorize_char("한") == "Letters"
    assert categorize_char("あ") == "Letters"


def test_han_detection_covers_bmp_and_supplementary_ideographs():
    assert is_han_char("中")
    assert is_han_char("𠀀")
    assert not is_han_char("あ")
    assert not is_han_char("한")


def test_whitespace_and_control_are_skipped():
    assert categorize_char(" ") is None
    assert categorize_char(" ") is None  # non-breaking space
    assert categorize_char("\t") is None
