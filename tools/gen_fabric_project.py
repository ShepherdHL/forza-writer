"""
Package a fontpack's generated glyphs into a single KFPS Fabric Editor
project (`.fabric-project.json`), one glyph per named group, arranged in
the same category-then-row grid as the reference SVG image so the two line
up as a tracing aid.

Only glyphs with a `json` artifact (the primitive-composition path) have a
shape list to pull from today. `.modelbin` glyphs have no importable shape
list until the catalog-hijack story in RESEARCH.md is resolved, so a
fontpack must have been generated with `--output json` or `--output both`.

Usage:
    python tools/gen_fabric_project.py --fontpack-dir data/fontpacks/AMARILLO-USAF
    python tools/gen_fabric_project.py --fontpack-dir data/fontpacks/AMARILLO-USAF --out my_project.fabric-project.json
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from forza_writer.fabric_project import save as save_project, to_fabric_project  # noqa: E402
from forza_writer.reference_svg import build_reference_svg, chunk_rows  # noqa: E402

CHARS_PER_ROW = 10
# Real FH6 editor units a single glyph's bounding box occupies once placed.
# Must match forza_writer.primitive_fit.fit_glyph's own glyph_size default,
# since that's the space each glyph's shapes were already generated in.
GLYPH_SIZE = 300.0
CELL_PADDING = 1.3  # grid cell = GLYPH_SIZE * CELL_PADDING, leaves a gap between glyphs


def _load_manifest(fontpack_dir: Path) -> dict:
    manifest_path = fontpack_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"no manifest.json in {fontpack_dir} — run gen_fontpack.py first")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _categorized_from_manifest(manifest: dict) -> dict[str, list[str]]:
    """Rebuild the category->chars mapping from what the manifest actually
    generated (not a fresh charset_from_font call), so the reference image
    and shape grid reflect exactly what's in this fontpack, even if it was
    hand-pruned after generation."""
    return {category: [entry["char"] for entry in entries]
            for category, entries in manifest["categories"].items()}


def build_fabric_project(fontpack_dir: Path, name: str | None = None,
                          chars_per_row: int = CHARS_PER_ROW, log=print) -> dict:
    manifest = _load_manifest(fontpack_dir)
    categorized = _categorized_from_manifest(manifest)
    rows = chunk_rows(categorized, chars_per_row)

    # char -> (row_index, col_index), so shape placement and the reference
    # SVG's row layout are driven by the exact same grid.
    cell_of: dict[str, tuple[int, int]] = {}
    for r, row in enumerate(rows):
        for c, char in enumerate(row):
            cell_of[char] = (r, c)

    all_shapes: list[dict] = []
    groups: list[tuple[str, list[int]]] = []
    missing = []

    for category, entries in manifest["categories"].items():
        for entry in entries:
            char = entry["char"]
            artifact = entry.get("artifacts", {}).get("json")
            if not artifact or not artifact.get("file"):
                missing.append(char)
                continue
            shape_path = fontpack_dir / artifact["file"]
            glyph_shapes = json.loads(shape_path.read_text(encoding="utf-8"))["shapes"]
            if not glyph_shapes:
                continue

            row, col = cell_of[char]
            cell_size = GLYPH_SIZE * CELL_PADDING
            offset_x = col * cell_size
            offset_y = row * cell_size

            start = len(all_shapes)
            for shape in glyph_shapes:
                placed = dict(shape)
                data = list(shape["data"])
                data[0] += offset_x
                data[1] += offset_y
                placed["data"] = data
                all_shapes.append(placed)
            groups.append((f"{category} — {char}", list(range(start, len(all_shapes)))))

    if missing:
        log(f"  {len(missing)} glyph(s) skipped (no json artifact): {''.join(missing)}")

    # Configurator-built packs may have no associated font at all:
    # font_file is optional there, so the reference-SVG overlay below just
    # gets skipped rather than raising.
    font_path = Path(manifest["font_file"]) if manifest.get("font_file") else None
    overlay = None
    if font_path is not None and font_path.exists():
        ref = build_reference_svg(font_path, categorized, chars_per_row=chars_per_row)
        # Scale the reference image so its own pixel span matches the shape
        # grid's editor-unit span, keeping the two visually aligned even
        # though they're built in different native units (SVG px vs FH6
        # editor units). This is an approximate alignment, not pixel-exact:
        # per-glyph SVG text advance is proportional while the shape grid
        # uses fixed-size cells, so treat it as a tracing aid, not a ruler.
        grid_width = chars_per_row * GLYPH_SIZE * CELL_PADDING
        grid_height = len(rows) * GLYPH_SIZE * CELL_PADDING
        scale = grid_width / ref.width if ref.width else 1.0
        overlay = {
            "version": 1,
            "kind": "layered_svg",
            "file_name": f"{manifest['prefix']}_reference.svg",
            "mime_type": "image/svg+xml",
            "data_url": None,
            "svg_text": ref.svg_text,
            "intrinsic_width": round(ref.width),
            "intrinsic_height": round(ref.height),
            "object_width": round(ref.width),
            "object_height": round(ref.height),
            "rendered_width": round(ref.width * scale),
            "rendered_height": round(ref.height * scale),
            "transform": {
                "left": 0, "top": 0, "scaleX": scale, "scaleY": scale,
                "angle": 0, "skewX": 0, "skewY": 0, "flipX": False, "flipY": False,
                "opacity": 0.45, "visible": True,
            },
            "controls": {"scale_percent": round(scale * 100), "opacity_percent": 45, "layer_mode": "below"},
        }
    else:
        log(f"  font file {font_path} not found — skipping reference image")

    name = name or manifest["prefix"]
    project = to_fabric_project(all_shapes, name=name, groups=groups, source_overlay=overlay)
    # A suggested export *filename*, distinct from the project's internal
    # display name: bakes in curve-segments smoothness and total shape count
    # (e.g. "AMARILLO-USAF_S8_368") so two exports of the same font at
    # different settings don't silently overwrite each other and the count
    # is visible without opening the file. Only known once every glyph's
    # shapes are actually in hand, i.e. at this point, not earlier.
    curve_segments = manifest.get("curve_segments", 8)
    project["suggested_name"] = f"{manifest['prefix']}_S{curve_segments}_{len(all_shapes)}"
    log(f"--- {len(all_shapes)} shapes across {len(groups)} glyph groups "
        f"({len(missing)} glyphs had no json artifact to include) ---")
    return project


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fontpack-dir", required=True, help="A fontpack directory produced by gen_fontpack.py")
    ap.add_argument("--out", default=None,
                     help="Output .fabric-project.json path (default: "
                          "<fontpack-dir>/<prefix>_S<curve-segments>_<shape-count>.fabric-project.json)")
    ap.add_argument("--chars-per-row", type=int, default=CHARS_PER_ROW,
                     help=f"Glyphs per grid row (default: {CHARS_PER_ROW})")
    args = ap.parse_args()

    fontpack_dir = Path(args.fontpack_dir)
    if not fontpack_dir.exists():
        print(f"Fontpack directory not found: {fontpack_dir}")
        sys.exit(1)

    project = build_fabric_project(fontpack_dir, chars_per_row=args.chars_per_row)
    out_path = Path(args.out) if args.out else fontpack_dir / f"{project['suggested_name']}.fabric-project.json"
    save_project(project, out_path)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
