"""Build a dafont-style grid reference image (SVG, the font's own glyphs
rendered as text) for use as a KFPS Fabric Editor tracing aid.

Matches the technique already used in the hand-made
`AmarilloUSAF_FontPack.fabric-project.json` precedent: a plain
`<svg><g><text><tspan>...</tspan></text></g></svg>`, one `<tspan>` per grid
row, glyphs space-separated, styled with the font's own family name so a
KFPS user with that font installed sees real letterforms, not just a
grid of unstyled boxes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fontTools.ttLib import TTFont

DEFAULT_CHARS_PER_ROW = 10
DEFAULT_FONT_SIZE_PX = 192
# Ratios derived from the real hand-made reference SVG (192px font, 240px
# row pitch, ~106px left margin) — not exact font metrics, just enough to
# keep the grid legible and unclipped; KFPS lets the reference image be
# rescaled/repositioned after import regardless.
_ROW_PITCH_RATIO = 1.25
_FIRST_ROW_Y_RATIO = 1.16
_LEFT_MARGIN_RATIO = 0.55
_ROW_WIDTH_RATIO = 1.3  # generous per-glyph width budget to avoid clipping


@dataclass(frozen=True)
class ReferenceSvg:
    svg_text: str
    width: float
    height: float


def _read_family_name(font_path: Path) -> str:
    """Best-effort real family name from the font's own `name` table,
    preferring the typographic family (nameID 16) over the legacy one (1)."""
    font = TTFont(str(font_path), fontNumber=0)
    try:
        name_table = font["name"]
        for name_id in (16, 1):
            for platform_id in (3, 1, 0):  # Windows, Macintosh, Unicode
                record = name_table.getName(name_id, platform_id, -1, -1) if platform_id == 0 \
                    else next((r for r in name_table.names
                               if r.nameID == name_id and r.platformID == platform_id), None)
                if record is not None:
                    try:
                        value = record.toUnicode()
                    except Exception:
                        continue
                    if value:
                        return value
        return font_path.stem
    finally:
        font.close()


def chunk_rows(categorized: dict[str, list[str]], chars_per_row: int = DEFAULT_CHARS_PER_ROW) -> list[list[str]]:
    """Split a categorized charset into display rows, each category starting
    its own row (never spilling the tail of one category into the next),
    chunked at `chars_per_row`. Shared by the reference SVG and
    tools/gen_fabric_project.py's shape-grid layout so both line up."""
    from forza_writer.charset import CATEGORY_ORDER

    rows: list[list[str]] = []
    for category in CATEGORY_ORDER:
        chars = categorized.get(category, [])
        for i in range(0, len(chars), chars_per_row):
            rows.append(chars[i:i + chars_per_row])
    return rows


def build_reference_svg(font_path: Path, categorized: dict[str, list[str]],
                         chars_per_row: int = DEFAULT_CHARS_PER_ROW,
                         font_size_px: int = DEFAULT_FONT_SIZE_PX,
                         font_family_name: str | None = None) -> ReferenceSvg:
    """Build the reference grid SVG for a fontpack's categorized charset.

    `categorized` should be in the same shape `forza_writer.charset.
    charset_from_font` returns (category -> chars, in display order);
    categories are flattened in `forza_writer.charset.CATEGORY_ORDER` order,
    each starting on its own row so the grid reads the same way dafont's
    charmap groups characters.
    """
    family = font_family_name or _read_family_name(font_path)

    rows = [" ".join(row) for row in chunk_rows(categorized, chars_per_row)]
    if not rows:
        rows = [""]

    left_margin = font_size_px * _LEFT_MARGIN_RATIO
    row_pitch = font_size_px * _ROW_PITCH_RATIO
    first_y = font_size_px * _FIRST_ROW_Y_RATIO
    width = left_margin * 2 + chars_per_row * font_size_px * _ROW_WIDTH_RATIO
    height = first_y + (len(rows) - 1) * row_pitch + font_size_px * 0.4

    tspans = "\n".join(
        f'      <tspan x="{left_margin:.2f}" y="{first_y + i * row_pitch:.2f}" '
        f'style="fill:#ff0000">{_xml_escape(row)}</tspan>'
        for i, row in enumerate(rows)
    )

    svg_text = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
        f'<svg width="{width:.2f}" height="{height:.2f}" viewBox="0 0 {width:.2f} {height:.2f}" '
        f'version="1.1" xmlns="http://www.w3.org/2000/svg">\n'
        f'  <g>\n'
        f'    <text style="font-size:{font_size_px}px;font-family:{_xml_escape(family)};'
        f'writing-mode:lr-tb;direction:ltr;fill:#444240" x="{left_margin:.2f}" y="{first_y:.2f}">\n'
        f'{tspans}\n'
        f'    </text>\n'
        f'  </g>\n'
        f'</svg>\n'
    )
    return ReferenceSvg(svg_text=svg_text, width=width, height=height)


def _xml_escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))
