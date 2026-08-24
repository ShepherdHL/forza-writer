"""General Unicode block database: every block's codepoint range and name,
and a codepoint -> block-name lookup.

Backed by fontTools.unicodedata's own bundled UCD block table (fontTools is
already a hard dependency here) rather than a hand-maintained copy — 397
real blocks, not a curated subset. For a narrower, curated block list built
specifically for glyph-slot templates, see forza_writer.glyph_template's
TEMPLATE_UNICODE_BLOCKS instead; that's a different, smaller thing from
this module's job.
"""

from __future__ import annotations

from fontTools.unicodedata import Blocks as _Blocks
from fontTools.unicodedata import block as _block

# (first_codepoint, last_codepoint, name) for every block, in codepoint
# order. _Blocks.RANGES holds each block's start codepoint (ascending,
# parallel to _Blocks.VALUES for the name); a block's end is one before the
# next block's start, except the last block, which runs to the top of the
# codepoint space.
BLOCKS: list[tuple[int, int, str]] = [
    (start, (_Blocks.RANGES[i + 1] - 1 if i + 1 < len(_Blocks.RANGES) else 0x10FFFF), name)
    for i, (start, name) in enumerate(zip(_Blocks.RANGES, _Blocks.VALUES))
]


def block_for_codepoint(codepoint: int) -> str | None:
    """Unicode block name for *codepoint*, or None if it falls in an
    unassigned gap between blocks (fontTools.unicodedata.block() returns
    "No_Block" for that case; normalized to None here)."""
    name = _block(chr(codepoint))
    return None if name == "No_Block" else name
