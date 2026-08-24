"""Group a font's characters into dafont-style categories.

dafont's own charmap pages (e.g. dafont.com/<font>.charmap) group glyphs into
visual blocks — for Amarillo USAF specifically: uppercase, lowercase, digits,
a punctuation pair, then a trailing block of whitespace/dashes/private-use
glyphs. That trailing grouping mirrors the font's internal glyph order, which
is a font-specific artifact and doesn't generalize across fonts. What does
generalize is grouping by Unicode general category, which produces the same
content split into six named buckets: Uppercase, Lowercase, Letters, Numbers,
Punctuation, Symbols. ``Letters`` is deliberately separate: uncased scripts
such as Han, Hangul, and Kana are letters, not symbols. Whitespace and
control/format glyphs are excluded — they
have no ink to render as vinyl.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path

from fontTools.ttLib import TTFont

CATEGORY_ORDER = ["Uppercase", "Lowercase", "Letters", "Numbers", "Punctuation", "Symbols"]

HAN_RANGES = (
    (0x3400, 0x4DBF),   # CJK Unified Ideographs Extension A
    (0x4E00, 0x9FFF),   # CJK Unified Ideographs
    (0xF900, 0xFAFF),   # CJK Compatibility Ideographs
    (0x20000, 0x323AF), # Supplementary CJK extensions and compatibility
)


def is_han_char(char: str) -> bool:
    """Whether *char* is a Han ideograph (Chinese/Kanji/Hanja codepoint)."""
    cp = ord(char)
    return any(start <= cp <= end for start, end in HAN_RANGES)


def categorize_char(char: str) -> str | None:
    """Return the dafont-style category name for a character, or None if it
    has no visible geometry (whitespace, control/format/unassigned codepoints)
    and should be skipped rather than generated."""
    cat = unicodedata.category(char)
    if cat in ("Lu",):
        return "Uppercase"
    if cat in ("Ll",):
        return "Lowercase"
    if cat[0] == "L":  # Lt, Lm, Lo — titlecase/modifier/other letters
        return "Uppercase" if char.isupper() else "Lowercase" if char.islower() else "Letters"
    if cat[0] == "N":  # Nd, Nl, No
        return "Numbers"
    if cat[0] == "P":
        return "Punctuation"
    if cat[0] == "S":
        return "Symbols"
    if cat == "Co":  # private-use (e.g. a font's own logo/dingbat glyph)
        return "Symbols"
    return None  # Z* (whitespace/separators), other C* (control/format/surrogate)


# font_path (resolved, as str) -> (categorized, skipped). The GUI calls this
# 2-3x for a single font selection (the lowercase-glyph check, Advanced
# Mode's glyph list, and the Symbols character group each call it
# independently), and every call fully reopens the font and re-derives its
# cmap from scratch. Installed-font files are static for the life of the
# process — nothing in this app modifies them while running — so caching
# the categorized result per path is safe; a stale entry (the file being
# replaced on disk mid-session, which nothing here does) would only
# self-correct on the next app restart. Bounded by the number of distinct
# fonts actually browsed/selected in a session, not the full install count.
_charset_cache: dict[str, tuple[dict[str, list[str]], list[tuple[str, str]]]] = {}


def charset_from_font(font_path: Path) -> tuple[dict[str, list[str]], list[tuple[str, str]]]:
    """Read every cmap'd character from a font and bucket it by category.

    Returns (categorized, skipped): `categorized` maps category name -> chars
    sorted by codepoint; `skipped` lists (char, reason) for cmap'd characters
    that fell into no category (whitespace/control glyphs). Cached per
    resolved file path — see _charset_cache above.
    """
    key = str(font_path)
    cached = _charset_cache.get(key)
    if cached is not None:
        return cached

    font = TTFont(str(font_path), fontNumber=0)
    try:
        cmap = font.getBestCmap()
    finally:
        font.close()

    categorized: dict[str, list[str]] = {name: [] for name in CATEGORY_ORDER}
    skipped: list[tuple[str, str]] = []
    for codepoint in sorted(cmap):
        char = chr(codepoint)
        category = categorize_char(char)
        if category is None:
            skipped.append((char, f"no visible geometry ({unicodedata.category(char)})"))
            continue
        categorized[category].append(char)
    result = (categorized, skipped)
    _charset_cache[key] = result
    return result
