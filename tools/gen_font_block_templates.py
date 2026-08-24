"""
Generate one glyph template per Unicode block a font actually supports —
the batch version of gen_glyph_template.py, meant for building a reusable
default template library from an openly-licensed font (e.g. Liberation
Sans, SIL OFL) rather than one-off templates for a specific licensed font
you don't want to ship in a public repo.

For each block in forza_writer.glyph_template.TEMPLATE_UNICODE_BLOCKS the
font covers with at least --min-chars glyphs, writes the same trio
gen_glyph_template.py does (template spec JSON, blank/traced
.fabric-project.json) under <out-dir>/<prefix-base>-<BLOCK-SLUG>/.

Usage:
    python tools/gen_font_block_templates.py --font-file "C:\\Windows\\Fonts\\LiberationSans-Regular.ttf" \\
        --prefix-base LIBERATION-SANS --out-dir data/fontpacks/default-templates
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fontTools.ttLib import TTFont  # noqa: E402

from forza_writer.fabric_project import save as save_project  # noqa: E402
from forza_writer.glyph_template import (  # noqa: E402
    DEFAULT_CHARS_PER_ROW, TEMPLATE_UNICODE_BLOCKS, blocks_covered_by_font, build_flat_template,
    build_font_traced_overlay_svg, save_template, wrap_template_as_project,
)

DEFAULT_OUT_DIR = Path("data/fontpacks/default-templates")
DEFAULT_MIN_CHARS = 4


def slugify(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-").upper()
    return s


def build_all_block_projects(font_path: Path, prefix_base: str, chars_per_row: int = DEFAULT_CHARS_PER_ROW,
                              min_chars: int = DEFAULT_MIN_CHARS, only_blocks: set[str] | None = None,
                              log=print):
    """Yields (block_name, template_id, template, project) for every block
    the font covers. `only_blocks`, if given, restricts to those exact
    TEMPLATE_UNICODE_BLOCKS names (case-sensitive) — e.g. to avoid embedding a large
    CJK font once per every block it happens to cover when only a couple
    are actually wanted."""
    font = TTFont(str(font_path), fontNumber=0)
    try:
        cmap = font.getBestCmap() or {}
    finally:
        font.close()

    covered = blocks_covered_by_font(cmap, min_chars=min_chars)
    blocks = covered
    if only_blocks is not None:
        unknown = only_blocks - {name for name, _ in covered}
        if unknown:
            log(f"  Note: requested block(s) not covered by this font (or below --min-chars), skipping: "
                f"{', '.join(sorted(unknown))}")
        blocks = [(name, chars) for name, chars in covered if name in only_blocks]
    log(f"Font covers {len(covered)} of {len(TEMPLATE_UNICODE_BLOCKS)} known block(s) with >= {min_chars} glyphs each; "
        f"building {len(blocks)}")
    for block_name, chars in blocks:
        template_id = f"{prefix_base}-{slugify(block_name)}"
        template = build_flat_template(chars, template_id, category_label=block_name,
                                        chars_per_row=chars_per_row)
        overlay_svg, missing = build_font_traced_overlay_svg(template, font_path)
        if missing:
            log(f"  [{block_name}] Note: {len(missing)} char(s) unexpectedly missing after cmap pre-filter")
        project = wrap_template_as_project(template, overlay_svg, template_id, overlay_opacity=0.5)
        log(f"  [{block_name}] {len(chars)} glyph(s), {template.row_count} row(s) -> {template_id}")
        yield block_name, template_id, template, project


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--font-file", required=True, help="Font file (otf/ttf/woff/woff2)")
    ap.add_argument("--prefix-base", required=True,
                     help="Prefix each block's template_id is built from, e.g. LIBERATION-SANS")
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR),
                     help=f"Root directory; each block writes to <out-dir>/<template_id>/ (default: {DEFAULT_OUT_DIR})")
    ap.add_argument("--chars-per-row", type=int, default=DEFAULT_CHARS_PER_ROW,
                     help=f"Glyphs per grid row (default: {DEFAULT_CHARS_PER_ROW})")
    ap.add_argument("--min-chars", type=int, default=DEFAULT_MIN_CHARS,
                     help=f"Skip a block if the font covers fewer than this many of its characters "
                          f"(default: {DEFAULT_MIN_CHARS})")
    ap.add_argument("--blocks", default=None,
                     help="Comma-separated block names to restrict to (must match TEMPLATE_UNICODE_BLOCKS exactly, "
                          "e.g. \"Hiragana,Katakana\"). Default: every block the font covers — expensive "
                          "for a large CJK font embedded per block, so scope this down when that matters.")
    args = ap.parse_args()

    font_path = Path(args.font_file)
    if not font_path.exists():
        print(f"Font file not found: {font_path}")
        sys.exit(1)

    only_blocks = {b.strip() for b in args.blocks.split(",")} if args.blocks else None

    out_dir = Path(args.out_dir)
    written = []
    for block_name, template_id, template, project in build_all_block_projects(
            font_path, args.prefix_base, args.chars_per_row, args.min_chars, only_blocks):
        block_dir = out_dir / template_id
        template_path = block_dir / f"{template_id}_template.json"
        project_path = block_dir / f"{template_id}_blank.fabric-project.json"
        svg_path = block_dir / f"{template_id}.svg"
        save_template(template, template_path)
        save_project(project, project_path)
        # Same SVG already embedded in the project's editor_source_overlay,
        # written out standalone too so it can be viewed/opened directly
        # without parsing the project JSON.
        svg_path.parent.mkdir(parents=True, exist_ok=True)
        svg_path.write_text(project["editor_source_overlay"]["svg_text"], encoding="utf-8")
        written.append((block_name, template_id, len(template.slots)))

    print(f"--- {len(written)} block template(s) written under {out_dir} ---")


if __name__ == "__main__":
    main()
