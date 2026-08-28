"""
Render arbitrary text in a native Forza Font (1-11) and export it as a
KFPS-importable project, using forza_writer/layout.py's layout_forza_text
to do the actual glyph layout.

Output is real FH6 vinyl shapes, not a template or placeholder grid. Drop
the result straight into KFPS and it renders as text, in that font, ready
to move, recolor, or edit like any other layer.

Usage:
    python tools/gen_forza_font_text.py --font 6 --text "TEST DRIVE" --out my_text.fabric-project.json
    python tools/gen_forza_font_text.py --font 1 --text "LINE ONE\\nLINE TWO" --target-height 500
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from forza_writer.fabric_project import save as save_project  # noqa: E402
from forza_writer.fabric_project import to_fabric_project  # noqa: E402
from forza_writer.layout import layout_forza_text  # noqa: E402
from forza_writer.shapes import char_to_resource  # noqa: E402

DEFAULT_TARGET_HEIGHT = 360.0


def build_text_project(text: str, font: int, target_height: float, name: str) -> tuple[dict, list[str]]:
    """Returns (fabric_project_dict, unsupported_chars). unsupported_chars
    lists every non-space character this font has no native shape for. Text
    still renders. Those characters are just skipped, not blocked."""
    shapes = layout_forza_text(text, font=font, target_height=target_height)
    unsupported = sorted({
        c for c in text if c not in ("\n", "\r", " ") and not char_to_resource(c, font)
    })
    project = to_fabric_project(shapes, name=name)
    return project, unsupported


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--font", type=int, required=True, choices=range(1, 12), metavar="1-11",
                     help="Which built-in Forza Font to render with")
    ap.add_argument("--text", required=True, help="Text to render. Use \\n for a line break.")
    ap.add_argument("--target-height", type=float, default=DEFAULT_TARGET_HEIGHT,
                     help=f"Total text block height in editor units (default: {DEFAULT_TARGET_HEIGHT})")
    ap.add_argument("--out", default=None,
                     help="Output .fabric-project.json path (default: FORZA-FONT-<N>-TEXT.fabric-project.json)")
    args = ap.parse_args()

    text = args.text.replace("\\n", "\n")
    name = f"FORZA-FONT-{args.font}-TEXT"
    project, unsupported = build_text_project(text, args.font, args.target_height, name)

    if not project["shapes"]:
        print(f"No shapes generated. Font {args.font} has no native shape for any character in the text.")
        sys.exit(1)

    out_path = Path(args.out) if args.out else Path(f"{name}.fabric-project.json")
    save_project(project, out_path)

    print(f"{len(project['shapes'])} glyph(s) placed. Font {args.font}.")
    if unsupported:
        print(f"Skipped {len(unsupported)} unsupported character(s): {''.join(unsupported)}")
    print(f"Wrote: {out_path}")
    print("Open this file directly in Kloudy's Fabric Editor. Every letter is a real, editable shape.")


if __name__ == "__main__":
    main()
