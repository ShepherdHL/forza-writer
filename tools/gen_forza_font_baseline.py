"""
Generate a baseline `.fabric-project.json` for one of FH6's built-in "Forza
Fonts" (1-11), pre-populated with the game's own native letter shapes laid
out in the same fixed glyph-slot grid gen_glyph_template.py uses.

Unlike gen_glyph_template.py's blank template (hand-draw every glyph from
nothing) or gen_fontpack.py's fitted packs (approximate an arbitrary font
file with primitive composition), this needs no drawing and no fitting at
all: FH6 already ships native shape resources for each letter of each Forza
Font (see forza_writer/shapes.py's char_to_resource, and
forza_writer/layout.py's layout_forza_text, which this reuses the same
PIXEL_ART_SQUARE_SIZE scale-fit math from). The output is a real,
already-correct starting point — open it in Kloudy's Fabric Editor and
fine-tune individual glyphs (recolor, resize, replace with custom shapes)
rather than drawing an entire alphabet from a blank cell.

Every character the chosen font doesn't natively support (most punctuation
beyond the ~15 symbols shapes.py's SYMBOL_MAP/UPPER_SYMBOL_MAP cover) is
left out of the project and recorded as skipped in the manifest, same
convention as gen_fontpack.py's "skipped" list.

Each glyph is placed in its own Editor Group, so the output already
satisfies import_glyph_template.py's grouping requirement — a baseline
project can go straight through that importer unmodified, before or after
any hand-editing.

Usage:
    python tools/gen_forza_font_baseline.py --font 1
    python tools/gen_forza_font_baseline.py --font 3 --prefix MY-FONT-3-BASELINE --out-dir data/fontpacks
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from forza_writer.fabric_project import save as save_project, to_fabric_project  # noqa: E402
from forza_writer.glyph_template import (  # noqa: E402
    DEFAULT_CHARS_PER_ROW, build_blank_overlay_svg, build_editor_guides, build_template,
    categorized_basic_latin, save_template,
)
from forza_writer.layout import PIXEL_ART_SQUARE_SIZE  # noqa: E402
from forza_writer.shapes import char_to_resource, resource_to_shape_word, resource_to_typecode  # noqa: E402

DEFAULT_OUT_DIR = Path("data/fontpacks")
GLYPH_FILL_RATIO = 0.8  # glyph height as a fraction of the cell, leaving a visible margin


def build_baseline_project(font: int, template_id: str, chars_per_row: int = DEFAULT_CHARS_PER_ROW,
                            log=print):
    """Returns (template, fabric_project_dict, skipped) where `skipped` is a
    list of (char, codepoint) for template slots this font has no native
    shape for."""
    categorized = categorized_basic_latin()
    template = build_template(categorized, template_id, chars_per_row=chars_per_row)

    target_height = template.glyph_size * GLYPH_FILL_RATIO
    scale = target_height / PIXEL_ART_SQUARE_SIZE

    shapes: list[dict] = []
    groups: list[tuple[str, list[int]]] = []
    skipped: list[tuple[str, str]] = []

    for slot in template.slots:
        resource = char_to_resource(slot.char, font)
        if resource is None:
            skipped.append((slot.char, slot.codepoint))
            log(f"  [{slot.category}] skip {slot.char!r} ({slot.codepoint}) — Forza Font {font} has no native "
                f"shape for this character")
            continue
        family, index = resource
        cx, cy = template.cell_center_world(slot.row, slot.col)
        index_in_shapes = len(shapes)
        shapes.append({
            "type": resource_to_typecode(family, index),
            "type_word": resource_to_shape_word(family, index),
            "data": [round(cx, 6), round(cy, 6), round(scale, 6), round(scale, 6), 0.0, 0.0, 0],
            "color": [255, 255, 255, 255],
        })
        groups.append((f"{slot.category} — {slot.char}", [index_in_shapes]))
        log(f"  [{slot.category}] ok   {slot.char!r} ({slot.codepoint}) <- {family}[{index}] -> "
            f"cell ({slot.row},{slot.col})")

    overlay_svg = build_blank_overlay_svg(template)
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
            "opacity": 0.35, "visible": True,
        },
        "controls": {"scale_percent": 100, "opacity_percent": 35, "layer_mode": "below"},
    }

    project = to_fabric_project(shapes, name=template_id, groups=groups, source_overlay=overlay)
    project["editor_guides"] = build_editor_guides(template)
    log(f"--- {len(shapes)} native glyph(s) placed, {len(skipped)} skipped (no native shape) ---")
    return template, project, skipped


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--font", type=int, required=True, choices=range(1, 12), metavar="1-11",
                     help="Which built-in Forza Font (1-11) to use as the baseline")
    ap.add_argument("--prefix", default=None,
                     help="Template/pack identifier (default: FORZA-FONT-<font>-BASELINE)")
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR),
                     help=f"Where to write <prefix>_template.json and <prefix>_baseline.fabric-project.json "
                          f"(default: {DEFAULT_OUT_DIR})")
    ap.add_argument("--chars-per-row", type=int, default=DEFAULT_CHARS_PER_ROW,
                     help=f"Glyphs per grid row (default: {DEFAULT_CHARS_PER_ROW})")
    args = ap.parse_args()

    prefix = args.prefix or f"FORZA-FONT-{args.font}-BASELINE"
    out_dir = Path(args.out_dir) / prefix
    template, project, skipped = build_baseline_project(args.font, prefix, args.chars_per_row)

    template_path = out_dir / f"{prefix}_template.json"
    project_path = out_dir / f"{prefix}_baseline.fabric-project.json"
    save_template(template, template_path)
    save_project(project, project_path)

    manifest_path = out_dir / f"{prefix}_baseline_summary.json"
    manifest_path.write_text(json.dumps({
        "font": args.font, "template_id": prefix,
        "placed": len(template.slots) - len(skipped), "skipped": [
            {"char": c, "codepoint": cp} for c, cp in skipped
        ],
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Wrote template spec: {template_path}")
    print(f"Wrote baseline project: {project_path}")
    print(f"Wrote summary: {manifest_path}")
    print("Open the project in Kloudy's Fabric Editor — every supported glyph is already placed;")
    print("fine-tune whatever you like, then export and run import_glyph_template.py to pull it back.")


if __name__ == "__main__":
    main()
