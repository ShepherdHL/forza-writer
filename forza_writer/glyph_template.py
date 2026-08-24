"""Blank glyph-slot templates for hand-made fontpacks.

A template is a fixed grid of labeled, empty cells (character + codepoint,
no rendered letterforms — nothing copied from any reference site or font)
that a user hand-draws into using Kloudy's Fabric Editor. Because each
cell's position is fixed and known in advance, Forza Writer can identify
which glyph a drawn shape group represents purely from where it sits in the
grid, with no OCR and no manual per-glyph tagging.

Shares its row/column layout convention (`chunk_rows`, category-then-row)
and grid math (`GLYPH_SIZE`/`CELL_PADDING`) with `reference_svg.py` and
`tools/gen_fabric_project.py` so a blank template and a generated fontpack's
tracing overlay line up the same way.
"""

from __future__ import annotations

import base64
import json
import math
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from fontTools.ttLib import TTFont

from forza_writer.charset import CATEGORY_ORDER, categorize_char
from forza_writer.reference_svg import chunk_rows

TEMPLATE_FORMAT = "forza_writer_glyph_template_v1"

# GLYPH_SIZE is the content box a placed/traced glyph is sized within;
# CELL_PADDING sets the cell pitch (GLYPH_SIZE * CELL_PADDING = 400, an
# exact, easy-to-verify number in KFPS's own grid/guide display) — chosen
# independently of tools/gen_fabric_project.py's own GLYPH_SIZE/CELL_PADDING,
# which is a separate pipeline (fitted packs) this module's blank/traced
# templates never share a grid with, so nothing requires the two to match.
GLYPH_SIZE = 300.0
CELL_PADDING = 400.0 / 300.0
DEFAULT_CHARS_PER_ROW = 10

# Hand-picked, not derived from any font file: A-Z, a-z, 0-9, common ASCII
# punctuation. Order matters — it fixes each character's row/column, so
# don't reorder an existing template's char list without minting a new
# template_id (old exports would silently decode to the wrong glyphs).
BASIC_LATIN_CHARS = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz"
    "0123456789"
    "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"
)


def categorized_from_chars(chars: str) -> dict[str, list[str]]:
    """Bucket an arbitrary character string with the same categorize_char()
    the rest of the app uses, so a template's category grouping matches
    generated fontpacks exactly regardless of script."""
    categorized: dict[str, list[str]] = {name: [] for name in CATEGORY_ORDER}
    for char in chars:
        cat = categorize_char(char)
        if cat is not None:
            categorized[cat].append(char)
    return categorized


def categorized_basic_latin() -> dict[str, list[str]]:
    return categorized_from_chars(BASIC_LATIN_CHARS)


def categorized_for_script_group(script: str, group_label: str) -> dict[str, list[str]]:
    """A single named group from forza_writer.alphabets.groups_for_script,
    e.g. categorized_for_script_group("Japanese", "Katakana") — the same
    curated, bounded character set the Generator tab's script checkboxes
    use, so a hand-made template's char list matches what a fitted fontpack
    for the same script would cover."""
    from forza_writer.alphabets import groups_for_script

    for label, chars in groups_for_script(script):
        if label == group_label:
            return categorized_from_chars(chars)
    available = [label for label, _ in groups_for_script(script)]
    raise ValueError(f"no {group_label!r} group for script {script!r}; available: {available}")


@dataclass(frozen=True)
class GlyphSlot:
    char: str
    codepoint: str
    unicode_name: str
    category: str
    row: int
    col: int


@dataclass(frozen=True)
class GlyphTemplate:
    template_id: str
    chars_per_row: int
    glyph_size: float
    cell_padding: float
    slots: list[GlyphSlot] = field(default_factory=list)

    @property
    def cell_size(self) -> float:
        return self.glyph_size * self.cell_padding

    @property
    def row_count(self) -> int:
        return (max((s.row for s in self.slots), default=-1)) + 1

    def cell_offset(self, row: int, col: int) -> tuple[float, float]:
        """Top-left corner of a cell in *template space*: row-down, Y=0 at
        row 0 — the convention the reference-image overlay is drawn in
        (`build_blank_overlay_svg`) and the one this dataclass's own
        `row`/`col` numbering follows. Not the convention KFPS's native
        shape coordinates use — see `cell_center_world`."""
        return (col * self.cell_size, row * self.cell_size)

    def cell_center_world(self, row: int, col: int) -> tuple[float, float]:
        """Cell center in KFPS's own shape-coordinate system, for a placed
        shape's `data[0]`/`data[1]`.

        Confirmed empirically (not assumed): placing a shape at
        `cell_offset`'s template-space Y put row 10 (the template's last
        row) at the *top* of the KFPS canvas and row 0 at the bottom —
        KFPS's native shape Y axis runs opposite to the row-down numbering
        everything else here uses. `forza_writer.layout.layout_forza_text`
        already negates Y for the same reason; this does the same, so a
        larger `row` here still lands lower on screen despite the sign
        flip.
        """
        x, y = self.cell_offset(row, col)
        return x + self.cell_size / 2, -(y + self.cell_size / 2)

    def cell_for_world_point(self, x: float, y: float) -> tuple[int, int]:
        """Inverse of `cell_center_world`: which (row, col) a KFPS
        world-space point (e.g. a drawn shape's data[0]/data[1]) falls
        into. Works for any point in the cell, not just its exact center."""
        col = math.floor(x / self.cell_size)
        row = math.floor(-y / self.cell_size)
        return row, col

    def slot_for_char(self, char: str) -> GlyphSlot | None:
        return next((s for s in self.slots if s.char == char), None)

    def slot_for_cell(self, row: int, col: int) -> GlyphSlot | None:
        return next((s for s in self.slots if s.row == row and s.col == col), None)

    def to_dict(self) -> dict:
        return {
            "format": TEMPLATE_FORMAT,
            "template_id": self.template_id,
            "chars_per_row": self.chars_per_row,
            "glyph_size": self.glyph_size,
            "cell_padding": self.cell_padding,
            "slots": [
                {
                    "char": s.char, "codepoint": s.codepoint, "unicode_name": s.unicode_name,
                    "category": s.category, "row": s.row, "col": s.col,
                }
                for s in self.slots
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GlyphTemplate":
        if data.get("format") != TEMPLATE_FORMAT:
            raise ValueError(f"unrecognized template format: {data.get('format')!r}")
        return cls(
            template_id=data["template_id"],
            chars_per_row=data["chars_per_row"],
            glyph_size=data["glyph_size"],
            cell_padding=data["cell_padding"],
            slots=[GlyphSlot(**s) for s in data["slots"]],
        )


def build_template(categorized: dict[str, list[str]], template_id: str,
                    chars_per_row: int = DEFAULT_CHARS_PER_ROW,
                    glyph_size: float = GLYPH_SIZE, cell_padding: float = CELL_PADDING) -> GlyphTemplate:
    """Lay `categorized` (category -> chars, e.g. from categorized_basic_latin())
    out into a fixed grid, category-then-row, matching chunk_rows()."""
    rows = chunk_rows(categorized, chars_per_row)
    slots = []
    for r, row_chars in enumerate(rows):
        for c, char in enumerate(row_chars):
            slots.append(GlyphSlot(
                char=char,
                codepoint=f"U+{ord(char):04X}",
                unicode_name=unicodedata.name(char, "?"),
                category=categorize_char(char) or "Symbols",
                row=r, col=c,
            ))
    return GlyphTemplate(template_id=template_id, chars_per_row=chars_per_row,
                          glyph_size=glyph_size, cell_padding=cell_padding, slots=slots)


def build_flat_template(chars: list[str], template_id: str, category_label: str = "Block",
                         chars_per_row: int = DEFAULT_CHARS_PER_ROW,
                         glyph_size: float = GLYPH_SIZE, cell_padding: float = CELL_PADDING) -> GlyphTemplate:
    """Lay an already-ordered, flat char list into a grid, chunked at
    chars_per_row — no CATEGORY_ORDER/chunk_rows bucketing, unlike
    build_template(). For a single-Unicode-block template (see
    TEMPLATE_UNICODE_BLOCKS below), where the whole block is already one
    semantic group and codepoint order is the only order that matters."""
    slots = []
    for i, char in enumerate(chars):
        row, col = divmod(i, chars_per_row)
        slots.append(GlyphSlot(
            char=char,
            codepoint=f"U+{ord(char):04X}",
            unicode_name=unicodedata.name(char, "?"),
            category=category_label,
            row=row, col=col,
        ))
    return GlyphTemplate(template_id=template_id, chars_per_row=chars_per_row,
                          glyph_size=glyph_size, cell_padding=cell_padding, slots=slots)


# name -> list of (first_codepoint, last_codepoint) inclusive ranges, for
# tools/gen_font_block_templates.py's one-template-per-block batch mode. A
# curated subset of real Unicode blocks (not the full ~397-block table —
# see forza_writer.unicode_blocks.BLOCKS for that, used elsewhere for
# general font introspection, a different job from this one), reshaped so
# "Basic Latin" is split into the four groups forza_writer.charset.
# categorize_char already buckets ASCII into, matching how gen_fontpack.py's
# generated packs categorize the same characters. A list (not a single
# range) for blocks whose desired grouping isn't a contiguous Unicode
# range, e.g. ASCII punctuation surrounds the uppercase/lowercase/digit
# runs rather than sitting in one span.
#
# Ranges/names are standard Unicode Character Database data (unicode.org's
# Blocks.txt) — factual codepoint boundaries, not anyone's copyrightable
# expression, so hardcoding them here carries none of the licensing
# concerns a font file or scraped artwork would.
TEMPLATE_UNICODE_BLOCKS: list[tuple[str, list[tuple[int, int]]]] = [
    ("Latin - Uppercase", [(0x0041, 0x005A)]),
    ("Latin - Lowercase", [(0x0061, 0x007A)]),
    ("Digits", [(0x0030, 0x0039)]),
    ("Punctuation & Symbols", [(0x0021, 0x002F), (0x003A, 0x0040), (0x005B, 0x0060), (0x007B, 0x007E)]),
    ("C1 Controls and Latin-1 Supplement", [(0x0080, 0x00FF)]),
    ("Latin Extended-A", [(0x0100, 0x017F)]),
    ("Latin Extended-B", [(0x0180, 0x024F)]),
    ("Spacing Modifier Letters", [(0x02B0, 0x02FF)]),
    ("Combining Diacritical Marks", [(0x0300, 0x036F)]),
    ("Greek and Coptic", [(0x0370, 0x03FF)]),
    ("Cyrillic", [(0x0400, 0x04FF)]),
    ("Latin Extended Additional", [(0x1E00, 0x1EFF)]),
    ("General Punctuation", [(0x2000, 0x206F)]),
    ("Currency Symbols", [(0x20A0, 0x20CF)]),
    ("Letterlike Symbols", [(0x2100, 0x214F)]),
    ("Arrows", [(0x2190, 0x21FF)]),
    ("Mathematical Operators", [(0x2200, 0x22FF)]),
    ("Enclosed Alphanumerics", [(0x2460, 0x24FF)]),
    ("Geometric Shapes", [(0x25A0, 0x25FF)]),
    ("CJK Symbols and Punctuation", [(0x3000, 0x303F)]),
    ("Hiragana", [(0x3040, 0x309F)]),
    ("Katakana", [(0x30A0, 0x30FF)]),
    ("CJK Compatibility", [(0x3300, 0x33FF)]),
    ("Alphabetic Presentation Forms", [(0xFB00, 0xFB4F)]),
    ("Halfwidth and Fullwidth Forms", [(0xFF00, 0xFFEF)]),
]


def chars_in_block(cmap: dict[int, str], ranges: list[tuple[int, int]]) -> list[str]:
    """Characters a font's cmap actually has a glyph for within `ranges` —
    codepoint order, not every codepoint in the range (most blocks have
    unassigned gaps, and a font rarely covers a whole block anyway)."""
    return [chr(cp) for start, end in ranges for cp in range(start, end + 1) if cp in cmap]


def blocks_covered_by_font(cmap: dict[int, str], min_chars: int = 4) -> list[tuple[str, list[str]]]:
    """Every TEMPLATE_UNICODE_BLOCKS entry the font covers with at least
    `min_chars` glyphs, in block order, as (name, chars). Skips blocks the
    font barely or doesn't touch — a font missing a script shouldn't
    produce a near-empty template for it."""
    result = []
    for name, ranges in TEMPLATE_UNICODE_BLOCKS:
        chars = chars_in_block(cmap, ranges)
        if len(chars) >= min_chars:
            result.append((name, chars))
    return result


def save_template(template: GlyphTemplate, path: str | Path) -> None:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(template.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_template(path: str | Path) -> GlyphTemplate:
    return GlyphTemplate.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def build_editor_guides(template: GlyphTemplate, grid_opacity: int = 30) -> dict:
    """KFPS `editor_guides` block, gridded and pre-lined to this template's
    exact cell pitch.

    `gridEnabled`/`gridSize` turns on KFPS's own live background grid at
    `cell_size` — its floor(bounds/step)*step rendering (editor.js
    `renderGuideObjects`) means grid lines land on multiples of `gridSize`
    starting from 0, which is exactly where our cell boundaries fall, so no
    offset math is needed to line the two up.

    Explicit horizontal/vertical `guides` (schema confirmed from editor.js:
    `{id, x1, y1, x2, y2, constraint}`) are added on top at every cell
    boundary — unlike the background grid these are individually visible,
    selectable, and Ctrl-snappable on their own regardless of whether the
    grid toggle is on, which is the stronger alignment signal while tracing.
    """
    cell = template.cell_size
    width = template.chars_per_row * cell
    height = template.row_count * cell
    guides = []
    for col in range(template.chars_per_row + 1):
        x = col * cell
        guides.append({
            "id": f"glyph-template-col-{col}", "x1": x, "y1": 0, "x2": x, "y2": height,
            "constraint": "vertical",
        })
    for row in range(template.row_count + 1):
        y = row * cell
        guides.append({
            "id": f"glyph-template-row-{row}", "x1": 0, "y1": y, "x2": width, "y2": y,
            "constraint": "horizontal",
        })
    return {
        "version": 1,
        "gridEnabled": True,
        "gridSize": cell,
        "gridOpacity": grid_opacity,
        "guidesVisible": True,
        "snapGuides": True,
        "snapGrid": True,
        "snapCtrlOnly": True,
        "snapThreshold": 12,
        "guideConstraint": "free",
        "snapGuideAnchor": False,
        "snapGuideEnd": False,
        "guides": guides,
    }


def _xml_escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def build_blank_overlay_svg(template: GlyphTemplate) -> str:
    """A labeled-but-empty grid: cell outline + character + codepoint per
    slot, no rendered letterforms. Meant as a `.fabric-project.json`
    `editor_source_overlay` — a tracing *layout* aid, not a tracing
    *artwork* aid; the user draws their own glyph inside each outline."""
    cell = template.cell_size
    width = template.chars_per_row * cell
    height = template.row_count * cell

    parts = []
    for slot in template.slots:
        x, y = template.cell_offset(slot.row, slot.col)
        parts.append(
            f'<rect x="{x:.2f}" y="{y:.2f}" width="{cell:.2f}" height="{cell:.2f}" '
            f'fill="none" stroke="#bbbbbb" stroke-width="2"/>'
        )
        parts.append(
            f'<text x="{x + cell * 0.5:.2f}" y="{y + cell * 0.58:.2f}" '
            f'font-size="{template.glyph_size * 0.45:.1f}" text-anchor="middle" '
            f'fill="#dddddd" font-family="sans-serif">{_xml_escape(slot.char)}</text>'
        )
        parts.append(
            f'<text x="{x + cell * 0.06:.2f}" y="{y + cell * 0.14:.2f}" '
            f'font-size="{template.glyph_size * 0.09:.1f}" '
            f'fill="#999999" font-family="monospace">{slot.codepoint}</text>'
        )

    return (
        f'<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
        f'<svg width="{width:.2f}" height="{height:.2f}" viewBox="0 0 {width:.2f} {height:.2f}" '
        f'version="1.1" xmlns="http://www.w3.org/2000/svg">\n'
        f'  <g>\n' + "\n".join(f"    {p}" for p in parts) + "\n  </g>\n</svg>\n"
    )


_FONT_MIME = {"otf": "font/otf", "ttf": "font/ttf", "woff": "font/woff", "woff2": "font/woff2"}
_FONT_FORMAT = {"otf": "opentype", "ttf": "truetype", "woff": "woff", "woff2": "woff2"}


def build_font_traced_overlay_svg(template: GlyphTemplate, font_path: str | Path,
                                   font_size_ratio: float = 0.62) -> tuple[str, list[str]]:
    """Grid overlay with each cell's actual letterform rendered from a real,
    locally-held font file — the font itself is embedded as a base64
    `@font-face` so it renders correctly in KFPS regardless of whether it's
    installed as a system font, not merely referenced by family name the
    way `reference_svg.build_reference_svg` does.

    This embeds the *user's own font file* directly (nothing fetched or
    scraped) — only appropriate for a font the user actually holds a license
    for; the caller is responsible for that, this function just draws it.

    Characters the font's cmap doesn't cover fall back to a label-only cell,
    same as `build_blank_overlay_svg`. Returns (svg_text, missing_chars).
    """
    font_path = Path(font_path)
    ext = font_path.suffix.lower().lstrip(".")
    if ext not in _FONT_MIME:
        raise ValueError(f"unsupported font file type: {font_path.suffix!r} (expected otf/ttf/woff/woff2)")
    font_b64 = base64.b64encode(font_path.read_bytes()).decode("ascii")
    family = "GlyphTemplateTraceFont"

    font = TTFont(str(font_path), fontNumber=0)
    try:
        supported = {chr(cp) for cp in (font.getBestCmap() or {})}
    finally:
        font.close()

    cell = template.cell_size
    width = template.chars_per_row * cell
    height = template.row_count * cell
    font_size = template.glyph_size * font_size_ratio

    parts = []
    missing = []
    for slot in template.slots:
        x, y = template.cell_offset(slot.row, slot.col)
        parts.append(
            f'<rect x="{x:.2f}" y="{y:.2f}" width="{cell:.2f}" height="{cell:.2f}" '
            f'fill="none" stroke="#bbbbbb" stroke-width="2"/>'
        )
        parts.append(
            f'<text x="{x + cell * 0.06:.2f}" y="{y + cell * 0.14:.2f}" '
            f'font-size="{template.glyph_size * 0.09:.1f}" '
            f'fill="#999999" font-family="monospace">{slot.codepoint}</text>'
        )
        if slot.char in supported:
            parts.append(
                f'<text x="{x + cell * 0.5:.2f}" y="{y + cell * 0.62:.2f}" '
                f'font-size="{font_size:.1f}" text-anchor="middle" '
                f'fill="#e6e6e6" font-family="{family}">{_xml_escape(slot.char)}</text>'
            )
        else:
            missing.append(slot.char)
            parts.append(
                f'<text x="{x + cell * 0.5:.2f}" y="{y + cell * 0.58:.2f}" '
                f'font-size="{template.glyph_size * 0.45:.1f}" text-anchor="middle" '
                f'fill="#555555" font-family="sans-serif">{_xml_escape(slot.char)}</text>'
            )

    svg = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
        f'<svg width="{width:.2f}" height="{height:.2f}" viewBox="0 0 {width:.2f} {height:.2f}" '
        f'version="1.1" xmlns="http://www.w3.org/2000/svg">\n'
        f'  <defs>\n'
        f'    <style>\n'
        f'      @font-face {{ font-family: "{family}"; '
        f'src: url(data:{_FONT_MIME[ext]};base64,{font_b64}) format("{_FONT_FORMAT[ext]}"); }}\n'
        f'    </style>\n'
        f'  </defs>\n'
        f'  <g>\n' + "\n".join(f"    {p}" for p in parts) + "\n  </g>\n</svg>\n"
    )
    return svg, missing


def wrap_template_as_project(template: GlyphTemplate, overlay_svg: str, template_id: str,
                              overlay_opacity: float = 0.6) -> dict:
    """Wrap a template + its overlay SVG into a KFPS `.fabric-project.json`
    dict: the reference-image overlay block, the empty-shapes-list
    workaround (one throwaway placeholder shape — see the comment below),
    and the grid/guides wired to the template's exact cell pitch. Shared by
    gen_glyph_template.py and gen_font_block_templates.py so both stay in
    sync rather than maintaining two copies of this."""
    from forza_writer.fabric_project import to_fabric_project

    overlay = {
        "version": 1,
        "kind": "layered_svg",
        "file_name": f"{template_id}_template.svg",
        "mime_type": "image/svg+xml",
        "data_url": None,
        "svg_text": overlay_svg,
        "intrinsic_width": round(template.chars_per_row * template.cell_size),
        "intrinsic_height": round(template.row_count * template.cell_size),
        "object_width": round(template.chars_per_row * template.cell_size),
        "object_height": round(template.row_count * template.cell_size),
        "rendered_width": round(template.chars_per_row * template.cell_size),
        "rendered_height": round(template.row_count * template.cell_size),
        "transform": {
            "left": 0, "top": 0, "scaleX": 1, "scaleY": 1,
            "angle": 0, "skewX": 0, "skewY": 0, "flipX": False, "flipY": False,
            "opacity": overlay_opacity, "visible": True,
        },
        "controls": {"scale_percent": 100, "opacity_percent": round(overlay_opacity * 100), "layer_mode": "below"},
    }
    # KFPS's loader (editor.js loadPayload) hard-rejects a project whose
    # shapes list is empty ("JSON shapes list is empty."), so a truly blank
    # canvas can't be opened at all. Seed one throwaway placeholder — a
    # tiny red square parked one full cell above-left of the grid (negative
    # coordinates, outside every labeled cell) — so the project loads; the
    # user deletes it before drawing their first real glyph. Uses the same
    # (type, type_word) pair as a real exported "Square" primitive
    # (VINYL_TYPE_BASES["Primitives"], shape_word 101) so it's a valid,
    # loadable shape rather than a synthetic one KFPS might reject too.
    placeholder = {
        "type": 1048677, "type_word": 101,
        "data": [-template.cell_size, -template.cell_size, 0.02, 0.02, 0, 0, 0],
        "color": [255, 0, 0, 255], "mask": False,
    }
    project = to_fabric_project([placeholder], name=template_id, groups=None, source_overlay=overlay)
    project["editor_guides"] = build_editor_guides(template)
    return project
