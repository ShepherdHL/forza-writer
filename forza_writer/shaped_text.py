"""OpenType shaping for reusable-glyph text generation.

HarfBuzz turns Unicode runs into positioned glyph IDs.  This is the missing
layer between input characters and font outlines for Arabic joining, Indic
reordering/conjuncts, ligatures, kerning, and mark attachment.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import uharfbuzz as hb
from fontTools.ttLib import TTFont


@dataclass(frozen=True)
class ShapedGlyph:
    glyph_id: int
    glyph_name: str
    cluster: int
    source_text: str
    x_advance: float
    y_advance: float
    x_offset: float
    y_offset: float


@dataclass(frozen=True)
class ShapedLine:
    glyphs: tuple[ShapedGlyph, ...]
    direction: str
    units_per_em: int


@lru_cache(maxsize=None)
def _font_data(font_path_str: str) -> tuple[bytes, int, tuple[str, ...]]:
    data = Path(font_path_str).read_bytes()
    face = hb.Face(data)
    font = TTFont(font_path_str, lazy=True, fontNumber=0)
    try:
        glyph_order = tuple(font.getGlyphOrder())
    finally:
        font.close()
    return data, face.upem, glyph_order


def _strong_direction(char: str) -> str | None:
    bidi = unicodedata.bidirectional(char)
    if bidi in {"R", "AL", "AN"}:
        return "rtl"
    if bidi in {"L", "EN"}:
        return "ltr"
    return None


def _directional_runs(text: str) -> tuple[str, list[tuple[int, str, str]]]:
    """Return a pragmatic visual-order run list for mixed LTR/RTL text.

    HarfBuzz shapes runs but intentionally does not implement the Unicode
    Bidirectional Algorithm.  This handles the common Arabic/Hebrew + Latin
    + digits case: neutrals inherit their nearest run, and RTL paragraphs
    reverse run order while HarfBuzz handles glyph order inside each run.
    """
    base = next((_strong_direction(c) for c in text if _strong_direction(c)), "ltr")
    logical: list[tuple[int, str, str]] = []
    start = 0
    current = base
    for index, char in enumerate(text):
        direction = _strong_direction(char)
        if direction is not None and direction != current:
            if index > start:
                logical.append((start, text[start:index], current))
            start, current = index, direction
    if start < len(text):
        logical.append((start, text[start:], current))
    if not logical:
        logical = [(0, text, base)]
    return base, list(reversed(logical)) if base == "rtl" else logical


def _cluster_source(run_text: str, cluster: int, clusters: list[int]) -> str:
    following = sorted(c for c in set(clusters) if c > cluster)
    end = following[0] if following else len(run_text)
    return run_text[cluster:end]


def _shape_run(run_text: str, font_path_str: str, start: int,
               direction: str) -> tuple[ShapedGlyph, ...]:
    data, upem, glyph_order = _font_data(font_path_str)
    face = hb.Face(data)
    font = hb.Font(face)
    font.scale = (upem, upem)
    hb.ot_font_set_funcs(font)
    buffer = hb.Buffer()
    buffer.add_str(run_text)
    buffer.direction = direction
    buffer.guess_segment_properties()
    hb.shape(font, buffer)
    clusters = [info.cluster for info in buffer.glyph_infos]
    result = []
    for info, position in zip(buffer.glyph_infos, buffer.glyph_positions):
        name = (glyph_order[info.codepoint]
                if 0 <= info.codepoint < len(glyph_order) else ".notdef")
        result.append(ShapedGlyph(
            glyph_id=info.codepoint,
            glyph_name=name,
            cluster=start + info.cluster,
            source_text=_cluster_source(run_text, info.cluster, clusters),
            x_advance=position.x_advance,
            y_advance=position.y_advance,
            x_offset=position.x_offset,
            y_offset=position.y_offset,
        ))
    return tuple(result)


def shape_text(text: str, font_path: str | Path) -> list[ShapedLine]:
    font_path_str = str(font_path)
    _data, upem, _order = _font_data(font_path_str)
    lines = []
    for line in text.split("\n"):
        base_direction, runs = _directional_runs(line)
        glyphs = tuple(
            glyph
            for start, run_text, direction in runs
            for glyph in _shape_run(run_text, font_path_str, start, direction)
        )
        lines.append(ShapedLine(glyphs, base_direction, upem))
    return lines
