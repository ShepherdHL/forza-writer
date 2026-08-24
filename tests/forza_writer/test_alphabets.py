import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from forza_writer import alphabets  # noqa: E402

# Expected group character counts — a regression pin so a future edit to
# forza_writer/alphabets.py can't silently drop or duplicate a letter
# without a test failing. Counts were verified against the standard
# reference alphabet/syllabary/varnamala for each script (see the
# module's own docstring for what's included and what's deliberately
# left out, e.g. Devanagari matras, Thai positional vowel stacking).
EXPECTED_COUNTS = {
    "Cyrillic": {"Uppercase": 33, "Lowercase": 33},
    "Greek": {"Uppercase": 24, "Lowercase": 25},  # Lowercase includes word-final sigma
    "Japanese": {"Hiragana": 75, "Katakana": 76},  # Katakana also carries the long-vowel mark ー
    "Korean": {"Consonants": 19, "Vowels": 21},
    "Devanagari": {"Vowels": 11, "Consonants": 33},
    "Thai": {"Consonants": 44, "Vowels": 15, "Tone marks": 4},
    "Arabic": {"Letters": 36},
    "Hebrew": {"Letters": 27, "Niqqud (vowel points)": 15},  # Letters: 22 base + 5 final (sofit) forms
}

# Unicode block each script's characters must fall within — catches a
# stray copy-pasted character from the wrong script/table.
EXPECTED_BLOCKS = {
    "Cyrillic": [(0x0400, 0x04FF)],
    "Greek": [(0x0370, 0x03FF)],
    "Japanese": [(0x3040, 0x30FF)],
    "Korean": [(0x3130, 0x318F)],  # Hangul Compatibility Jamo
    "Devanagari": [(0x0900, 0x097F)],
    "Thai": [(0x0E00, 0x0E7F)],
    "Arabic": [(0x0600, 0x06FF)],
    "Hebrew": [(0x0590, 0x05FF)],
}


def test_expected_scripts_are_present():
    assert set(alphabets.ALPHABETS.keys()) == set(EXPECTED_COUNTS.keys())


def test_group_counts_match_the_pinned_reference():
    for script, groups in alphabets.ALPHABETS.items():
        actual = {label: len(letters) for label, letters in groups}
        assert actual == EXPECTED_COUNTS[script], f"{script} group counts drifted"


def test_no_duplicate_characters_within_a_script_group():
    for script, groups in alphabets.ALPHABETS.items():
        for label, letters in groups:
            assert len(letters) == len(set(letters)), f"{script}/{label} has a duplicate character"


def test_no_whitespace_or_ascii_leaked_into_a_script_group():
    for script, groups in alphabets.ALPHABETS.items():
        for label, letters in groups:
            for ch in letters:
                assert not ch.isspace(), f"{script}/{label} contains whitespace"
                assert ord(ch) > 127, f"{script}/{label} contains an ASCII character: {ch!r}"


def test_every_character_falls_within_the_expected_unicode_block():
    for script, groups in alphabets.ALPHABETS.items():
        blocks = EXPECTED_BLOCKS[script]
        for label, letters in groups:
            for ch in letters:
                cp = ord(ch)
                assert any(lo <= cp <= hi for lo, hi in blocks), (
                    f"{script}/{label} char {ch!r} (U+{cp:04X}) outside expected block(s) {blocks}")


def test_every_character_has_visible_geometry():
    # categorize_char (forza_writer.charset) would skip anything in this
    # set at generation time anyway — catches an accidental combining
    # mark or format character with no ink of its own.
    for script, groups in alphabets.ALPHABETS.items():
        for label, letters in groups:
            for ch in letters:
                cat = unicodedata.category(ch)
                assert cat[0] in ("L", "M"), f"{script}/{label} char {ch!r} has category {cat}"


def test_no_alphabet_scripts_are_the_chinese_variants_only():
    assert alphabets.NO_ALPHABET_SCRIPTS == {"Simplified Chinese", "Traditional Chinese"}


def test_no_alphabet_scripts_absent_from_alphabets_dict():
    assert alphabets.NO_ALPHABET_SCRIPTS.isdisjoint(alphabets.ALPHABETS.keys())


def test_chinese_scripts_have_bounded_explicit_generation_groups():
    for script in alphabets.NO_ALPHABET_SCRIPTS:
        groups = alphabets.groups_for_script(script)
        assert groups
        assert sum(len(set(chars)) for _label, chars in groups) < 500
        assert any("punctuation" in label.lower() for label, _chars in groups)


def test_shaping_caveats_only_cover_scripts_with_real_alphabets():
    assert set(alphabets.SHAPING_CAVEATS.keys()) <= set(alphabets.ALPHABETS.keys())


def test_cyrillic_and_greek_have_no_shaping_caveat():
    # These two are structurally identical to Latin's own uppercase/
    # lowercase model — nothing to caveat, unlike the other 5 scripts.
    assert "Cyrillic" not in alphabets.SHAPING_CAVEATS
    assert "Greek" not in alphabets.SHAPING_CAVEATS


def test_chars_for_script_unions_every_group():
    result = alphabets.chars_for_script("Korean")
    expected = set("ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ") | set("ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ")
    assert result == expected


def test_chars_for_script_empty_for_unknown_or_no_alphabet_script():
    assert alphabets.chars_for_script("Simplified Chinese") == set()
    assert alphabets.chars_for_script("Nonexistent Script") == set()
