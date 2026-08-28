"""Detect which writing scripts a font actually supports, from its own
cmap: prep work for filtering the GUI's font list by script (Latin,
Cyrillic, Greek, Japanese, Korean, Traditional/Simplified Chinese, Arabic,
Devanagari, Thai) ahead of adding real non-Latin generation support.

Detection is cmap-coverage-based, same font-access pattern
`forza_writer/charset.py::charset_from_font` already uses (fontTools'
`getBestCmap()`), no new font-parsing approach introduced. A script
counts as "supported" once cmap coverage of a representative codepoint
sample clears a per-script threshold, not "any single codepoint present"
(which false-positives constantly: broad Windows UI fonts like Segoe
UI/Arial/Times New Roman carry a handful of stray glyphs, even a currency
symbol or two, well outside their primary script).

Thresholds were tuned empirically against real fonts installed on a real
Windows machine, not guessed in the abstract:

- The *full* Cyrillic/Greek Unicode blocks (not just the core ~50-letter
  alphabet) turned out to be the discriminating signal: the core alphabet
  alone is close to universal (every font tested, including CJK-focused
  ones, covered 100% of it, likely because it's part of the long-standard
  WGL4 repertoire most font tools ship by default), while CJK fonts
  landed around 26-34% of the *full* block (a handful of incidental glyphs)
  against 94-100% for genuinely Cyrillic/Greek-capable fonts.
- Arabic/Devanagari/Thai showed a much cleaner split even on the full
  block: fonts with no real support measured ~0-9%, a real Thai UI font
  (Leelawadee UI) measured 68%.
- Japanese (Hiragana+Katakana) and Korean (Hangul) both cleared 85-100%
  on fonts that genuinely support them.

This is a heuristic, not a certainty: a font landing just under a
threshold won't show up for that script even if it has partial support,
and see `SIMPLIFIED_CHINESE`/`TRADITIONAL_CHINESE` below for the
Simplified vs. Traditional Chinese caveat specifically. Good enough for
"help the user find candidate fonts," not treated as authoritative
elsewhere in the codebase.
"""

from __future__ import annotations

import string
from pathlib import Path

from fontTools.ttLib import TTFont

SCRIPTS = [
    "Latin",
    "Cyrillic",
    "Greek",
    "Japanese",
    "Korean",
    "Traditional Chinese",
    "Simplified Chinese",
    "Arabic",
    "Hebrew",
    "Devanagari",
    "Thai",
]

_LATIN_SAMPLE = [ord(c) for c in string.ascii_letters]
_CYRILLIC_SAMPLE = list(range(0x0400, 0x0500))
_GREEK_SAMPLE = list(range(0x0370, 0x0400))
_HIRAGANA_KATAKANA_SAMPLE = list(range(0x3040, 0x3100))
_HANGUL_SAMPLE = list(range(0xAC00, 0xAC00 + 4352)) + list(range(0x1100, 0x1200))
_HAN_SAMPLE = list(range(0x4E00, 0x4E00 + 4352))
_ARABIC_SAMPLE = list(range(0x0600, 0x0700))
_HEBREW_SAMPLE = list(range(0x0590, 0x0600))
_DEVANAGARI_SAMPLE = list(range(0x0900, 0x0980))
_THAI_SAMPLE = list(range(0x0E00, 0x0E80))

# (sample, coverage-fraction threshold): see module docstring for how
# these were derived. Hebrew's 0.5 was checked the same way: real
# Hebrew-capable fonts on a real Windows machine (Arial, Times New Roman,
# Segoe UI, Tahoma, Calibri) measured ~78% coverage of the full Hebrew
# block (not 100%; a handful of rare cantillation/presentation-form
# codepoints are commonly absent even from genuinely Hebrew-capable
# fonts), while CJK-only fonts (MS Gothic, SimSun) measured 0%, a wide
# enough gap that 0.5 cleanly separates them, matching Arabic/Devanagari/
# Thai's own threshold for a similarly-structured single-block script.
_SIMPLE_SCRIPTS: dict[str, tuple[list[int], float]] = {
    "Latin": (_LATIN_SAMPLE, 0.8),
    "Cyrillic": (_CYRILLIC_SAMPLE, 0.35),
    "Greek": (_GREEK_SAMPLE, 0.4),
    "Japanese": (_HIRAGANA_KATAKANA_SAMPLE, 0.6),
    "Korean": (_HANGUL_SAMPLE, 0.5),
    "Arabic": (_ARABIC_SAMPLE, 0.5),
    "Hebrew": (_HEBREW_SAMPLE, 0.5),
    "Devanagari": (_DEVANAGARI_SAMPLE, 0.5),
    "Thai": (_THAI_SAMPLE, 0.5),
}
_HAN_THRESHOLD = 0.4

# Font-name substrings hinting at Simplified vs. Traditional Chinese:
# cmap coverage alone can't tell the two apart (both draw from the same
# CJK Unified Ideographs block), so a Han-capable font is classified by
# its own name. A font that doesn't match either list shows up under
# *both* SIMPLIFIED_CHINESE and TRADITIONAL_CHINESE tabs rather than
# being silently dropped from either, ambiguous rather than absent.
_SIMPLIFIED_HINTS = ("simplified", " sc", "-sc", "yahei", "simsun", "simhei", "fangsong", "kaiti", "dengxian", "gb2312", "gb18030")
_TRADITIONAL_HINTS = ("traditional", " tc", "-tc", "jhenghei", "mingliu", "pmingliu", "dfkai", "big5", "kai")


def _coverage(cmap: set[int], sample: list[int]) -> float:
    if not sample:
        return 0.0
    return sum(1 for cp in sample if cp in cmap) / len(sample)


def _classify_chinese(name: str) -> set[str]:
    lowered = f" {name.lower()} "
    is_simplified = any(hint in lowered for hint in _SIMPLIFIED_HINTS)
    is_traditional = any(hint in lowered for hint in _TRADITIONAL_HINTS)
    if is_simplified and not is_traditional:
        return {"Simplified Chinese"}
    if is_traditional and not is_simplified:
        return {"Traditional Chinese"}
    return {"Simplified Chinese", "Traditional Chinese"}  # ambiguous: show in both


def detect_font_scripts(font_path: Path, display_name: str = "") -> set[str]:
    """Return the subset of `SCRIPTS` this font's cmap appears to support.

    `display_name` (the font's registry/file display name, not read from
    the font itself) drives the Simplified/Traditional Chinese split:
    pass whatever name the caller already has (e.g. `enumerate_installed_fonts`'s
    key) rather than this function re-deriving one. Never raises: a font
    that can't be opened/parsed just yields an empty set, matching this
    project's established "a bad font is a skip, not a crash" convention
    (see `forza_writer/charset.py::charset_from_font`).
    """
    try:
        font = TTFont(str(font_path), fontNumber=0)
        try:
            cmap = set(font.getBestCmap().keys())
        finally:
            font.close()
    except Exception:
        return set()

    detected = {
        script for script, (sample, threshold) in _SIMPLE_SCRIPTS.items()
        if _coverage(cmap, sample) >= threshold
    }
    if _coverage(cmap, _HAN_SAMPLE) >= _HAN_THRESHOLD:
        detected |= _classify_chinese(display_name or Path(font_path).stem)
    return detected
