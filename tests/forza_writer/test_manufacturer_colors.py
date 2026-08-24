import re

from forza_writer.manufacturer_colors import all_makes, load_all, search

HEX_RE = re.compile(r"^#[0-9a-f]{6}$")


def test_bundled_dataset_has_a_sane_row_count():
    # ~10,997 rows as of the GTPlanet Colour Creation Database snapshot this
    # was built from (see THIRD_PARTY_NOTICES.md §3) — a loose lower bound
    # so this doesn't break on minor future re-generation.
    assert len(load_all()) > 10000


def test_every_row_has_a_valid_hex1_and_category():
    for color in load_all():
        assert HEX_RE.match(color.hex1), color
        assert color.category in ("Vehicle", "Wheel")
        assert color.hex2 == "" or HEX_RE.match(color.hex2)


def test_all_makes_are_sorted_and_distinct():
    makes = all_makes()
    assert len(makes) > 100
    assert list(makes) == sorted(set(makes))


def test_search_by_make_name_returns_only_matching_rows():
    results = search("Ferrari")
    assert results
    assert all("ferrari" in c.make.lower() or "ferrari" in c.name.lower() for c in results)


def test_search_with_exact_make_filter():
    results = search("", make="Ford")
    assert results
    assert all(c.make == "Ford" for c in results)


def test_search_empty_term_and_no_make_returns_everything():
    assert len(search()) == len(load_all())


def test_search_is_case_insensitive():
    assert search("ferrari") == search("FERRARI") == search("FeRrArI")
