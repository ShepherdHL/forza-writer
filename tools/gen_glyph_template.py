"""
Generate a blank glyph-slot template: an empty `.fabric-project.json` with a
labeled grid overlay (character + codepoint per cell, no rendered
letterforms) for hand-drawing a fontpack in Kloudy's Fabric Editor.

Open the exported project, draw each glyph inside its labeled cell using the
Fabric Editor's normal shape tools, and group every glyph's shapes together
(Editor Groups) before exporting again — grouping is what lets
import_glyph_template.py identify which glyph is which. Ungrouped or
stray shapes can't be attributed to a cell reliably and will be skipped on
import.

Usage:
    python tools/gen_glyph_template.py --prefix MY-HANDMADE-FONT
    python tools/gen_glyph_template.py --prefix MY-HANDMADE-FONT --out-dir data/fontpacks --chars-per-row 13
    python tools/gen_glyph_template.py --prefix MY-KATAKANA --charset katakana
    python tools/gen_glyph_template.py --prefix MODEL-PLASTIC-TRACE --font-file "PPModelPlastic-Medium.otf"

--font-file requires a font you actually hold a license for — it embeds
that exact font file into the reference overlay so KFPS renders its real
letterforms as a tracing guide (no artwork sourced from anywhere else).
Without it, cells are labeled but empty, same as before.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from forza_writer.fabric_project import save as save_project  # noqa: E402
from forza_writer.glyph_template import (  # noqa: E402
    DEFAULT_CHARS_PER_ROW, build_blank_overlay_svg, build_font_traced_overlay_svg,
    build_template, categorized_basic_latin, categorized_for_script_group, save_template,
    wrap_template_as_project,
)

DEFAULT_OUT_DIR = Path("data/fontpacks")

# name -> (script, group_label) for forza_writer.alphabets.groups_for_script,
# or None for the hand-picked Basic Latin set. Add more scripts/groups here
# as templates for them are needed — every entry gets the same grid/guide
# machinery for free, only the source character list differs.
CHARSETS = {
    "basic-latin": None,
    "hiragana": ("Japanese", "Hiragana"),
    "katakana": ("Japanese", "Katakana"),
}


def categorized_for_charset(charset: str) -> dict[str, list[str]]:
    spec = CHARSETS[charset]
    if spec is None:
        return categorized_basic_latin()
    script, group_label = spec
    return categorized_for_script_group(script, group_label)


def build_blank_project(template_id: str, chars_per_row: int = DEFAULT_CHARS_PER_ROW,
                         charset: str = "basic-latin", font_file: str | Path | None = None,
                         log=print):
    """Returns (template, fabric_project_dict). If `font_file` is given, the
    overlay shows that font's real letterforms (embedded, not scraped) as a
    tracing guide instead of a bare label; characters missing from its cmap
    fall back to a label-only cell, logged so it's not a silent gap."""
    categorized = categorized_for_charset(charset)
    template = build_template(categorized, template_id, chars_per_row=chars_per_row)
    if font_file is not None:
        overlay_svg, missing = build_font_traced_overlay_svg(template, font_file)
        if missing:
            log(f"  Note: font has no glyph for {len(missing)} slot(s), label-only there: "
                f"{''.join(missing)}")
        overlay_opacity = 0.5
    else:
        overlay_svg = build_blank_overlay_svg(template)
        overlay_opacity = 0.6

    project = wrap_template_as_project(template, overlay_svg, template_id, overlay_opacity)
    return template, project


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prefix", required=True, help="Template/pack identifier, e.g. MY-HANDMADE-FONT")
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR),
                     help=f"Where to write <prefix>_template.json and <prefix>_blank.fabric-project.json "
                          f"(default: {DEFAULT_OUT_DIR})")
    ap.add_argument("--chars-per-row", type=int, default=DEFAULT_CHARS_PER_ROW,
                     help=f"Glyphs per grid row (default: {DEFAULT_CHARS_PER_ROW})")
    ap.add_argument("--charset", choices=sorted(CHARSETS), default="basic-latin",
                     help=f"Which character set to lay out (default: basic-latin). "
                          f"One of: {', '.join(sorted(CHARSETS))}.")
    ap.add_argument("--font-file", default=None,
                     help="Optional font file (otf/ttf/woff/woff2) to embed as a real-letterform tracing "
                          "guide instead of bare labels. Only use a font you hold a license for — it's "
                          "embedded directly into the overlay, not fetched from anywhere.")
    args = ap.parse_args()

    if args.font_file and not Path(args.font_file).exists():
        print(f"Font file not found: {args.font_file}")
        sys.exit(1)

    out_dir = Path(args.out_dir) / args.prefix
    template, project = build_blank_project(args.prefix, args.chars_per_row, args.charset, args.font_file)

    template_path = out_dir / f"{args.prefix}_template.json"
    project_path = out_dir / f"{args.prefix}_blank.fabric-project.json"
    svg_path = out_dir / f"{args.prefix}.svg"
    save_template(template, template_path)
    save_project(project, project_path)
    # Same SVG already embedded in the project's editor_source_overlay,
    # written out standalone too so it can be viewed/opened directly.
    svg_path.parent.mkdir(parents=True, exist_ok=True)
    svg_path.write_text(project["editor_source_overlay"]["svg_text"], encoding="utf-8")

    print(f"{len(template.slots)} slots across {template.row_count} rows")
    print(f"Wrote template spec: {template_path}")
    print(f"Wrote blank project:  {project_path}")
    print(f"Wrote reference SVG:  {svg_path}")
    print("Open the project in Kloudy's Fabric Editor, draw each glyph inside its labeled cell,")
    print("group every glyph's shapes (Editor Groups), then export and run import_glyph_template.py.")


if __name__ == "__main__":
    main()
