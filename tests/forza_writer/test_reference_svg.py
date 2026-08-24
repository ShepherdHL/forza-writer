import xml.etree.ElementTree as ET

from forza_writer.reference_svg import build_reference_svg

SVG_NS = "{http://www.w3.org/2000/svg}"


def test_build_reference_svg_parses_as_valid_xml():
    categorized = {"Uppercase": list("ABCDEFGHIJKL"), "Lowercase": [], "Numbers": [],
                   "Punctuation": [], "Symbols": []}
    # build_reference_svg needs a font path only to read the family name;
    # pass a name explicitly so no real font file is required for this test.
    result = build_reference_svg(font_path=None, categorized=categorized,
                                  chars_per_row=10, font_family_name="TestFamily")
    root = ET.fromstring(result.svg_text)
    assert root.tag == f"{SVG_NS}svg"


def test_row_count_matches_chars_per_row_chunking():
    # 12 uppercase chars at 10 per row -> 2 rows
    categorized = {"Uppercase": list("ABCDEFGHIJKL"), "Lowercase": [], "Numbers": [],
                   "Punctuation": [], "Symbols": []}
    result = build_reference_svg(font_path=None, categorized=categorized,
                                  chars_per_row=10, font_family_name="TestFamily")
    root = ET.fromstring(result.svg_text)
    tspans = root.findall(f".//{SVG_NS}tspan")
    assert len(tspans) == 2
    assert tspans[0].text == "A B C D E F G H I J"
    assert tspans[1].text == "K L"


def test_each_category_starts_a_new_row():
    categorized = {"Uppercase": ["A", "B"], "Lowercase": ["a", "b"], "Numbers": [],
                   "Punctuation": [], "Symbols": []}
    result = build_reference_svg(font_path=None, categorized=categorized,
                                  chars_per_row=10, font_family_name="TestFamily")
    root = ET.fromstring(result.svg_text)
    tspans = root.findall(f".//{SVG_NS}tspan")
    assert len(tspans) == 2
    assert tspans[0].text == "A B"
    assert tspans[1].text == "a b"


def test_font_family_name_appears_in_style():
    categorized = {"Uppercase": ["A"], "Lowercase": [], "Numbers": [], "Punctuation": [], "Symbols": []}
    result = build_reference_svg(font_path=None, categorized=categorized, font_family_name="MyCoolFont")
    assert "MyCoolFont" in result.svg_text


def test_empty_charset_still_produces_valid_svg():
    categorized = {"Uppercase": [], "Lowercase": [], "Numbers": [], "Punctuation": [], "Symbols": []}
    result = build_reference_svg(font_path=None, categorized=categorized, font_family_name="Empty")
    root = ET.fromstring(result.svg_text)
    assert root.tag == f"{SVG_NS}svg"
