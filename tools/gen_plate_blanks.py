"""
Builds the pre-rendered "blank plate" library (data/plate_blanks/) from
every template currently in data/plate_templates/: background + border +
decorations, rendered once and cached, instead of being rebuilt from
Decoration data on every single generation -- see
forza_writer/plates/blank_library.py's module docstring for why.

Run this after adding or editing a template. A template with no blank yet
still works (forza_writer/plates/renderer.py falls back to rendering it on
the fly), just without the caching benefit.

Usage:
    python tools/gen_plate_blanks.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forza_writer.plates import blank_library  # noqa: E402
from forza_writer.plates.loader import list_templates, reload_templates  # noqa: E402
from forza_writer.plates.renderer import render_plate_blank  # noqa: E402


def main():
    reload_templates()
    templates = list_templates()
    if not templates:
        print("No templates found under data/plate_templates/ -- nothing to do.")
        return
    for template in templates:
        shapes, nodes, warnings = render_plate_blank(template)
        path = blank_library.save_blank(template, shapes, nodes, warnings)
        note = f" (warnings: {warnings})" if warnings else ""
        print(f"Wrote {path} -- {len(shapes)} shapes{note}")


if __name__ == "__main__":
    main()
