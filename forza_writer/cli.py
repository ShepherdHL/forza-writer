"""CLI entry point for forza-writer."""

import argparse

from forza_writer.export import save, to_json
from forza_writer.layout import layout_forza_text


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render FH6 native font text as vinyl layer JSON."
    )
    parser.add_argument("text", help="Text to render")
    parser.add_argument("--font", type=int, default=1, help="Forza font number (1-11)")
    parser.add_argument("--out", required=True, help="Output JSON file path")
    args = parser.parse_args()

    shapes = layout_forza_text(args.text, font=args.font)
    save(to_json(shapes), args.out)
