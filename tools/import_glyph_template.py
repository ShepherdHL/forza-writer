"""
Import a hand-drawn `.fabric-project.json` (built from gen_glyph_template.py's
blank grid) back into a "handmade" fontpack: identify which glyph each shape
group represents purely from its grid position, normalize its shapes to
glyph-local coordinates, and write per-glyph JSON files plus a manifest.json
in the same shape gen_fontpack.py's generated packs use.

Every glyph's shapes must be a single Editor Group in the Fabric Editor
(File > Group, or equivalent) before exporting — ungrouped/stray shapes have
no reliable way to be attributed to a cell and are recorded as skipped, not
guessed at.

Usage:
    python tools/import_glyph_template.py --project MyDrawing.fabric-project.json \\
        --template data/fontpacks/MY-HANDMADE-FONT/MY-HANDMADE-FONT_template.json \\
        --prefix MY-HANDMADE-FONT --out-dir data/fontpacks
"""
import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from forza_writer.export import save as save_json, to_json  # noqa: E402
from forza_writer.glyph_template import GlyphTemplate, load_template  # noqa: E402

MANIFEST_FORMAT = "forza_writer_fontpack_v2"


def _group_shapes(shapes: list[dict]) -> tuple[dict[str, list[dict]], list[dict]]:
    """Split the flat shape list by editor_group_id. Shapes with no group
    (editor_group_id is None) can't be attributed to any cell and are
    returned separately as `ungrouped`."""
    grouped: dict[str, list[dict]] = defaultdict(list)
    ungrouped: list[dict] = []
    for shape in shapes:
        gid = shape.get("editor_group_id")
        if gid is None:
            ungrouped.append(shape)
        else:
            grouped[gid].append(shape)
    return grouped, ungrouped


def _group_cell(shapes: list[dict], template: GlyphTemplate) -> tuple[int, int]:
    """Snap a group's shapes to the nearest grid cell using the centroid of
    each shape's anchor position (data[0], data[1]) — the inverse of
    `GlyphTemplate.cell_center_world`, which is what actually placed these
    shapes (gen_forza_font_baseline.py) or what a hand-drawn shape's
    position is naturally expressed in (KFPS's own Y-up world space)."""
    xs = [s["data"][0] for s in shapes if s.get("data")]
    ys = [s["data"][1] for s in shapes if s.get("data")]
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
    return template.cell_for_world_point(cx, cy)


def import_project(project: dict, template: GlyphTemplate, prefix: str, out_dir: Path,
                    log=print) -> dict:
    if project.get("format") != "kloudy_fabric_editor_project_v1":
        raise ValueError(f"unrecognized project format: {project.get('format')!r}")

    grouped, ungrouped = _group_shapes(project.get("shapes", []))
    if ungrouped:
        log(f"  WARNING: {len(ungrouped)} shape(s) have no Editor Group and cannot be attributed "
            f"to any glyph — group every glyph's shapes before exporting. Skipping them.")

    pack_dir = out_dir / prefix / "HANDMADE-v1"
    entries_by_category: dict[str, list[dict]] = {}
    slot_used_by: dict[tuple[int, int], str] = {}
    files_written: list[str] = []
    counts = {"generated": 0, "failed": 0}

    for group_id, shapes in grouped.items():
        group_name = shapes[0].get("editor_group_name") or group_id
        if not shapes or not any(s.get("data") for s in shapes):
            log(f"  FAIL group {group_name!r}: no shape data to locate in the grid")
            counts["failed"] += 1
            continue

        row, col = _group_cell(shapes, template)
        slot = template.slot_for_cell(row, col)
        if slot is None:
            log(f"  FAIL group {group_name!r}: centroid falls at cell (row={row}, col={col}), "
                f"outside the template's grid — drawn outside its labeled cell?")
            counts["failed"] += 1
            continue

        prior = slot_used_by.get((row, col))
        if prior is not None:
            log(f"  FAIL group {group_name!r}: cell (row={row}, col={col}) for {slot.char!r} "
                f"already claimed by group {prior!r} — two glyphs drawn in the same cell?")
            counts["failed"] += 1
            continue
        slot_used_by[(row, col)] = group_name

        # Normalize to glyph-local coordinates by subtracting the same
        # world-space cell center gen_forza_font_baseline.py placed a native
        # glyph at — the center, not cell_offset()'s template-space corner,
        # since that's the reference point placement actually uses.
        center_x, center_y = template.cell_center_world(row, col)
        normalized = []
        for shape in shapes:
            plain = {
                "type": shape["type"], "type_word": shape["type_word"],
                "data": list(shape["data"]), "color": list(shape["color"]),
                "mask": shape.get("mask", False),
            }
            plain["data"][0] -= center_x
            plain["data"][1] -= center_y
            normalized.append(plain)

        rel_path = Path(slot.category) / f"{prefix}_U+{ord(slot.char):04X}.json"
        out_path = pack_dir / rel_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        save_json(to_json(normalized), out_path)
        files_written.append(str(rel_path).replace("\\", "/"))
        counts["generated"] += 1

        entry = {
            "char": slot.char, "codepoint": slot.codepoint, "unicode_name": slot.unicode_name,
            "status": "complete",
            "artifacts": {"json": {
                "file": str(rel_path).replace("\\", "/"),
                "shape_count": len(normalized), "strategy": "handmade",
            }},
            "provenance": {"method": "drawn", "grid_cell": {"row": row, "col": col}},
        }
        entries_by_category.setdefault(slot.category, []).append(entry)
        log(f"  [{slot.category}] ok   {slot.char!r} ({slot.codepoint}) <- group {group_name!r} "
            f"cell ({row},{col}) -> {rel_path}")

    drawn_chars = {c for entries in entries_by_category.values() for e in entries for c in [e["char"]]}
    missing = [s for s in template.slots if s.char not in drawn_chars]

    manifest = {
        "format": MANIFEST_FORMAT,
        "kind": "handmade",
        "prefix": prefix,
        "pack_id": f"{prefix}__HANDMADE-v1",
        "template_id": template.template_id,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "categories": entries_by_category,
        "files_written": files_written,
        "summary": {
            "json": counts,
            "by_category": {c: len(entries_by_category.get(c, [])) for c in entries_by_category},
            "missing_slots": len(missing),
        },
        "missing_slots": [
            {"char": s.char, "codepoint": s.codepoint, "category": s.category}
            for s in missing
        ],
    }
    pack_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = pack_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"--- {counts['generated']} ok/{counts['failed']} failed, "
        f"{len(missing)} template slot(s) still empty -> {manifest_path} ---")
    return manifest


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True, help="Hand-drawn .fabric-project.json exported from KFPS")
    ap.add_argument("--template", required=True, help="Template spec JSON from gen_glyph_template.py")
    ap.add_argument("--prefix", required=True, help="Fontpack prefix/name")
    ap.add_argument("--out-dir", default="data/fontpacks", help="Fontpack root directory (default: data/fontpacks)")
    args = ap.parse_args()

    project_path = Path(args.project)
    template_path = Path(args.template)
    if not project_path.exists():
        print(f"Project file not found: {project_path}")
        sys.exit(1)
    if not template_path.exists():
        print(f"Template file not found: {template_path}")
        sys.exit(1)

    project = json.loads(project_path.read_text(encoding="utf-8"))
    template = load_template(template_path)
    import_project(project, template, args.prefix, Path(args.out_dir))


if __name__ == "__main__":
    main()
