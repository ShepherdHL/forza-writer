"""FH6 vinyl shape typecodes and character-to-resource mapping (from KFPS editor.js).

The symbol table below was corrected against
`../Forza Painter/KFPS Report/KFPS_Bug_Package_2026-07-11/reports/Glyph_Mismatch_Report.md`
("KFPS Vinyl Editor — Glyph Library / Text-Parser Mismatch: Full Cross-Reference",
2026-07-11). That report found KFPS's own `editor.js` symbol table rotated by
four slots against the actual game meshes, verified three independent ways
(static source diff, `Resources/Vinyls` mesh preview dumps, and live
in-game runtime — reproducing the "Ninja€s" bug exactly). It also
identified 14 previously-unused Upper-page slots per font (digits 1-0 and
`! ? @ &`) with preview assets already present in every font. Two open
items from that report, neither of which affects correctness of what's
implemented here:
- `;`/`:` at 38/39 (not the reverse) is the mesh-based reading, pending a
  single in-game keystroke to confirm the *input* mapping agrees with the
  mesh appearance — worst case these two swap.
- `@` exists on both pages (Upper 39, Lower 34); this module always
  resolves it to the Lower slot, matching this table's pre-correction
  behavior, rather than picking one per context.
"""

VINYL_TYPE_BASES = {
    "Primitives": 1048677,
    "Gradient_Shapes": 1048777,
    "Stripes": 1048877,
    "Tears": 1048977,
    "Racing_Icons": 1049077,
    "Flames": 1049177,
    "Paint_Splats": 1049277,
    "Tribal": 1049377,
    "Nature": 1049477,
    "Upper_Letters_2": 1049877,
    "Lower_Letters_2": 1049977,
    "Upper_Letters_3": 1050077,
    "Lower_Letters_3": 1050177,
    "Upper_Letters_4": 1050277,
    "Lower_Letters_4": 1050377,
    "Upper_Letters_1": 1050477,
    "Lower_Letters_1": 1050577,
    "Community_Vinyls_1": 1050677,
    "Community_Vinyls_2": 1050777,
    "Community_Vinyls_3": 1050877,
    "Community_Vinyls_4": 1050977,
    "Upper_Letters_5": 1051077,
    "Lower_Letters_5": 1051177,
    "Upper_Letters_6": 1051277,
    "Lower_Letters_6": 1051377,
    "Upper_Letters_7": 1051477,
    "Lower_Letters_7": 1051577,
    "Upper_Letters_8": 1051677,
    "Lower_Letters_8": 1051777,
    "Upper_Letters_9": 1051877,
    "Lower_Letters_9": 1051977,
    "Upper_Letters_10": 1052077,
    "Lower_Letters_10": 1052177,
    "Upper_Letters_11": 1052277,
    "Lower_Letters_11": 1052377,
}

UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
LOWER = "abcdefghijklmnopqrstuvwxyz"

# Lower_Letters_N indices 27-40 — corrected ordering (see module docstring).
SYMBOL_MAP = {
    "$": 27,
    "£": 28,
    "¥": 29,
    "€": 30,
    "æ": 31,
    "Æ": 31,
    "^": 32,
    "ß": 33,
    "@": 34,
    "#": 35,
    "+": 36,
    "%": 37,
    ";": 38,
    ":": 39,
    "/": 40,
}

# Upper_Letters_N indices 27-40 — digits and punctuation, universal across
# all 11 fonts (see module docstring). "0" sits at 36, after "1"-"9", not
# at 27 — that is how the game itself orders this page.
DIGIT_MAP = {
    "1": 27, "2": 28, "3": 29, "4": 30, "5": 31,
    "6": 32, "7": 33, "8": 34, "9": 35, "0": 36,
}

# "@" is deliberately absent here — it also exists on the Upper page (slot
# 39) but SYMBOL_MAP above already resolves "@" to the Lower page, and a
# character should only ever map to one resource.
UPPER_SYMBOL_MAP = {
    "!": 37,
    "?": 38,
    "&": 40,
}


def resource_to_shape_word(family: str, index: int) -> int:
    if family == "Primitives":
        return (100 + index) & 0xFFFF
    base = VINYL_TYPE_BASES[family]
    return (base - 0x100000 + index - 1) & 0xFFFF


_FAMILY_BAND_WIDTH = 100  # families are spaced 100 shape-words apart (verified against VINYL_TYPE_BASES); no family has anywhere near that many indices


def shape_word_to_resource(shape_word: int) -> tuple[str, int] | None:
    """Inverse of `resource_to_shape_word`: given a shape word, return the
    (family, index) that produced it, or None if it doesn't fall inside any
    known family's contiguous index band. Best-effort — relies on the
    observed 100-word spacing between families rather than an explicit
    per-family index count, since none is tracked here."""
    shape_word &= 0xFFFF
    if 101 <= shape_word < 101 + _FAMILY_BAND_WIDTH:
        return ("Primitives", shape_word - 100)
    for family, base in VINYL_TYPE_BASES.items():
        if family == "Primitives":
            continue
        offset = (base - 0x100000) & 0xFFFF
        if offset <= shape_word < offset + _FAMILY_BAND_WIDTH:
            return (family, shape_word - offset + 1)
    return None


def resource_to_typecode(family: str, index: int) -> int:
    return 0x100000 + resource_to_shape_word(family, index)


def char_to_resource(char: str, font: int = 1) -> tuple[str, int] | None:
    """Returns (family, index) or None for unsupported characters."""
    font = max(1, min(11, font))
    upper_idx = UPPER.find(char)
    if upper_idx >= 0:
        return (f"Upper_Letters_{font}", upper_idx + 1)
    lower_idx = LOWER.find(char)
    if lower_idx >= 0:
        return (f"Lower_Letters_{font}", lower_idx + 1)
    if char in DIGIT_MAP:
        return (f"Upper_Letters_{font}", DIGIT_MAP[char])
    if char in UPPER_SYMBOL_MAP:
        return (f"Upper_Letters_{font}", UPPER_SYMBOL_MAP[char])
    if char in SYMBOL_MAP:
        return (f"Lower_Letters_{font}", SYMBOL_MAP[char])
    return None
