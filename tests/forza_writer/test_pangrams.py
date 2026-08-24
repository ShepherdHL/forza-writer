"""Per-script sample text: the one-click "does this font render my script?" check."""

import sys
import unicodedata
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from forza_writer.alphabets import (  # noqa: E402
    ALPHABETS, CHINESE_STRUCTURAL_TEST, PANGRAM_SCRIPTS, PANGRAMS, chars_for_script,
    pangram_for, pangrams_for)
from forza_writer.script_detect import SCRIPTS  # noqa: E402

# Codepoint ranges that identify a script, used to confirm each sample is
# actually written in the script it is filed under. Deliberately checked by
# Unicode block rather than against ALPHABETS: real text legitimately contains
# characters (composed Hangul syllables, final sigma, Thai tone marks) that the
# curated generation alphabets don't list.
SCRIPT_RANGES: dict[str, tuple[tuple[int, int], ...]] = {
    "Latin": ((0x0041, 0x007A),),
    "Cyrillic": ((0x0400, 0x04FF),),
    "Greek": ((0x0370, 0x03FF), (0x1F00, 0x1FFF)),
    "Japanese": ((0x3040, 0x309F), (0x30A0, 0x30FF)),
    "Korean": ((0xAC00, 0xD7A3), (0x1100, 0x11FF), (0x3130, 0x318F)),
    "Arabic": ((0x0600, 0x06FF),),
    "Hebrew": ((0x0590, 0x05FF),),
    "Thai": ((0x0E00, 0x0E7F),),
    "Traditional Chinese": ((0x4E00, 0x9FFF),),
    "Simplified Chinese": ((0x4E00, 0x9FFF),),
}


def _in_script(char: str, script: str) -> bool:
    return any(lo <= ord(char) <= hi for lo, hi in SCRIPT_RANGES[script])


def _letters(text: str) -> list[str]:
    """Just the letter-ish characters — spaces, digits and punctuation are
    incidental to every sample and say nothing about its script."""
    return [c for c in text if unicodedata.category(c).startswith(("L", "M"))]


def _all_option_pairs():
    """Every (script, label, text) triple across every script's every
    sample option — the unit tests below run against, since PANGRAMS now
    holds a list of options per script rather than one string."""
    return [
        (script, label, text)
        for script, options in PANGRAMS.items()
        for label, text in options
    ]


# --- structure -----------------------------------------------------------

def test_every_pangram_key_is_a_real_script():
    assert set(PANGRAMS) <= set(SCRIPTS)


def test_pangram_scripts_are_listed_in_canonical_script_order():
    # The GUI iterates PANGRAM_SCRIPTS so its buttons match the script tabs;
    # dict order would drift from that the moment an entry is added.
    assert PANGRAM_SCRIPTS == [s for s in SCRIPTS if s in PANGRAMS]


def test_every_listed_script_actually_has_sample_text():
    for script in PANGRAM_SCRIPTS:
        options = PANGRAMS[script]
        assert options, script
        for label, text in options:
            assert label.strip(), script
            assert text.strip(), f"{script}/{label}"


def test_devanagari_is_deliberately_absent_rather_than_guessed_at():
    # An unverified sample is worse than no button; the UI omits the option.
    assert "Devanagari" in SCRIPTS
    assert "Devanagari" not in PANGRAMS
    assert pangram_for("Devanagari") is None
    assert pangrams_for("Devanagari") == []


def test_pangram_for_unknown_script_returns_none():
    assert pangram_for("Klingon") is None
    assert pangrams_for("Klingon") == []


def test_pangram_for_returns_the_first_option_of_pangrams_for():
    for script in PANGRAM_SCRIPTS:
        assert pangram_for(script) == pangrams_for(script)[0][1]


def test_no_duplicate_option_labels_within_a_script():
    for script, options in PANGRAMS.items():
        labels = [label for label, _text in options]
        assert len(labels) == len(set(labels)), f"{script} has a duplicate sample label"


# --- the samples really are in the script they claim ---------------------

@pytest.mark.parametrize("script,label,text", _all_option_pairs())
def test_sample_text_is_written_in_its_own_script(script, label, text):
    letters = _letters(text)
    assert letters, f"{script}/{label}"
    foreign = [c for c in letters if not _in_script(c, script)]
    assert not foreign, f"{script}/{label} contains non-{script} letters: {foreign!r}"


@pytest.mark.parametrize("script,label,text", _all_option_pairs())
def test_sample_text_is_long_enough_to_reveal_missing_glyphs(script, label, text):
    # Not every option needs to be an exhaustive pangram (see the Hebrew
    # coverage tests below for that distinction) — but even a "does this
    # look right" preview needs more than a handful of characters to be
    # useful for spotting a font that's missing glyphs.
    assert len(set(_letters(text))) >= 10, f"{script}/{label}"


def test_latin_sample_covers_the_whole_alphabet_and_all_ten_digits():
    sample = pangram_for("Latin").upper()
    assert set("ABCDEFGHIJKLMNOPQRSTUVWXYZ") <= set(sample)
    assert set("0123456789") <= set(sample)


def test_japanese_sample_is_the_iroha_covering_each_base_kana_once():
    hiragana = [c for c in pangram_for("Japanese") if 0x3040 <= ord(c) <= 0x309F]
    # The Iroha's defining property: no kana repeats.
    assert len(hiragana) == len(set(hiragana))
    assert len(set(hiragana)) >= 40


def test_both_chinese_variants_reuse_the_existing_structural_test_set():
    # Chinese has no pangram — no small closed repertoire to exhaust — so the
    # purpose-built structural set stands in rather than inventing one.
    assert pangram_for("Simplified Chinese") == CHINESE_STRUCTURAL_TEST
    assert pangram_for("Traditional Chinese") == CHINESE_STRUCTURAL_TEST


# --- known mismatch with the flat generation model -----------------------

def test_korean_sample_uses_composed_syllables_the_jamo_alphabet_cannot_build():
    # Documents a real limitation rather than hiding it: ALPHABETS["Korean"]
    # offers individual Jamo because composing them into syllable blocks needs
    # text shaping this tool doesn't do — but natural Korean text, including
    # this sample, is written in composed syllables. Generating from this
    # sample therefore needs a font whose cmap covers the syllables directly.
    syllables = {c for c in pangram_for("Korean") if 0xAC00 <= ord(c) <= 0xD7A3}
    assert syllables
    assert not syllables & chars_for_script("Korean")


def test_scripts_with_a_curated_alphabet_still_have_one():
    # The samples are a rendering check, not a replacement for the generation
    # alphabets — both must continue to exist independently.
    for script in ("Cyrillic", "Greek", "Japanese", "Korean", "Thai", "Arabic", "Hebrew"):
        assert script in ALPHABETS
        assert script in PANGRAMS


# --- Hebrew: multiple options, only one of which is a true pangram -------

def test_hebrew_has_three_labeled_options():
    labels = [label for label, _text in pangrams_for("Hebrew")]
    assert labels == [
        "Alphabet",
        "John 19:19-22 (Delitzsch Hebrew NT)",
        "Joke: Revelation 1:19½ (not real scripture)",
    ]


def test_hebrew_alphabet_option_matches_alphabets_hebrew_letters_exactly():
    # Reuses ALPHABETS["Hebrew"] directly rather than a second hand-typed
    # copy, so the two can't silently drift apart.
    alphabet_option = dict(pangrams_for("Hebrew"))["Alphabet"]
    assert alphabet_option == ALPHABETS["Hebrew"][0][1]


def test_hebrew_alphabet_option_is_a_true_pangram_covering_every_letter():
    # Unlike the popular "curious fish" Hebrew pangram sentences (verified
    # elsewhere to miss final letter forms), the plain alphabet row is by
    # construction a complete pangram: every base and final letter exactly
    # once.
    alphabet_option = dict(pangrams_for("Hebrew"))["Alphabet"]
    assert len(alphabet_option) == 27
    assert len(set(alphabet_option)) == 27


def test_hebrew_joke_option_is_clearly_labeled_as_not_real_scripture():
    joke_label = next(label for label, _text in pangrams_for("Hebrew") if label.startswith("Joke"))
    assert "not real scripture" in joke_label
