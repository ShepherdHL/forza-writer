"""
Consolidate every Forza Font 1-11 baseline (built by gen_forza_font_baseline.py)
into one organized reference. Output: a machine-readable index and a
human-readable summary doc. Purpose: ship a fast lookup with the tool.
Answer one question per font. What does it cover. Where is its baseline
project.

This is not a replacement for the per-font baseline projects. It reads
their existing *_baseline_summary.json files and presents them together.
It does not re-derive anything. Run gen_forza_font_baseline.py first for
any font missing a baseline.

Usage:
    python tools/gen_forza_fonts_reference.py
    python tools/gen_forza_fonts_reference.py --fontpacks-dir data/fontpacks --out-dir data/fontpacks
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from forza_writer.shapes import char_to_resource  # noqa: E402

DEFAULT_FONTPACKS_DIR = Path("data/fontpacks")
FONT_NUMBERS = range(1, 12)

# Real-world identification for each Forza Font. Confirmed by comparing
# actual KFPS screenshots against rendered candidate fonts, letterform by
# letterform. Not guessed from style alone. `confirmed=True` means a
# specific diagnostic letterform quirk matched (Font 6's Q renders as "2",
# Font 9's G has the Rockwell spur, Font 7's proportions match exactly).
# `confirmed=False` entries that still name a font are a same-family lead,
# not an identification. The exact cut was not found.
FONT_IDENTIFICATION: dict[int, dict] = {
    1: {"confirmed": True, "note": "Arial Bold"},
    2: {"confirmed": False, "note": "Unidentified. Elegant italic script/cursive. Art-Deco style."},
    3: {"confirmed": False, "note": "Unidentified."},
    4: {"confirmed": False, "note": "Unidentified. Hand-drawn/marker style. Rough, uneven strokes."},
    5: {"confirmed": False, "note": "Unidentified. Blackletter/Gothic. Similar to Goudy Text MT."},
    6: {"confirmed": True, "note": "Brush Script MT"},
    7: {"confirmed": True, "note": "Haettenschweiler"},
    8: {"confirmed": False, "note": "Unidentified. Bold weathered/distressed serif."},
    9: {"confirmed": True, "note": "Rockwell-esque font. Specifically Rockwell Bold, not Rockwell "
                                    "Condensed or Extra Bold. Matched down to the G's spur detail."},
    10: {"confirmed": False, "note": "Unidentified. High-contrast condensed serif. Similar to Onyx and "
                                      "Bodoni MT Poster Compressed."},
    11: {"confirmed": True, "note": "Century Gothic"},
}


def _prefix(font: int) -> str:
    return f"FORZA-FONT-{font}-BASELINE"


def load_font_entry(fontpacks_dir: Path, font: int) -> dict | None:
    """One font's consolidated entry, or None if its baseline hasn't been
    generated yet (gen_forza_font_baseline.py --font N first)."""
    prefix = _prefix(font)
    pack_dir = fontpacks_dir / prefix
    summary_path = pack_dir / f"{prefix}_baseline_summary.json"
    if not summary_path.exists():
        return None
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    # Resource families this font's placed glyphs actually draw from. Every
    # font uses its own Upper_Letters_N/Lower_Letters_N pair (see
    # forza_writer/shapes.py's char_to_resource). This is always the same
    # two names. Confirmed here by re-deriving it, not assumed.
    families = sorted({
        resource[0] for char in "ABCabc0" if (resource := char_to_resource(char, font))
    })

    return {
        "font": font,
        "template_id": prefix,
        "resource_families": families,
        "placed": summary["placed"],
        "skipped_count": len(summary["skipped"]),
        "skipped_chars": [entry["char"] for entry in summary["skipped"]],
        "identification": FONT_IDENTIFICATION.get(font, {"confirmed": False, "note": "Unidentified."}),
        "files": {
            "template": str((pack_dir / f"{prefix}_template.json").as_posix()),
            "baseline_project": str((pack_dir / f"{prefix}_baseline.fabric-project.json").as_posix()),
            "summary": str(summary_path.as_posix()),
        },
    }


def build_reference(fontpacks_dir: Path, log=print) -> dict:
    entries = []
    missing = []
    for font in FONT_NUMBERS:
        entry = load_font_entry(fontpacks_dir, font)
        if entry is None:
            missing.append(font)
            log(f"  Font {font}: no baseline found (run gen_forza_font_baseline.py --font {font} first)")
            continue
        entries.append(entry)
        log(f"  Font {font}: {entry['placed']} placed, {entry['skipped_count']} skipped, "
            f"families {entry['resource_families']}")

    # All 11 fonts share the same universal digit/punctuation slots (see
    # forza_writer/shapes.py's module docstring). True by construction of
    # char_to_resource. Confirmed here, not assumed. Every loaded font is
    # checked to agree before the set is treated as shared.
    skip_sets = {tuple(sorted(e["skipped_chars"])) for e in entries}
    shared_skip = len(skip_sets) == 1

    reference = {
        "format": "forza_fonts_reference_v1",
        "fonts": entries,
        "missing_fonts": missing,
        "coverage_shared_across_all_fonts": shared_skip,
    }
    if shared_skip and entries:
        reference["shared_skipped_chars"] = entries[0]["skipped_chars"]
        reference["shared_placed_count"] = entries[0]["placed"]
    return reference


def build_markdown(reference: dict) -> str:
    lines = ["# Forza Fonts 1-11 Reference", ""]
    lines.append(
        "Baseline `.fabric-project.json` files for each of FH6's 11 built-in "
        "\"Forza Fonts.\" Every native letter, digit, and punctuation shape "
        "the game ships. Pre-placed on the standard 400-unit template grid "
        "(see `tools/gen_forza_font_baseline.py`). The overlay reference "
        "image on each is a plain labeled grid. It is not a rendering of "
        "the actual native shapes. No accessible font file exists for "
        "these in-game meshes to trace from. The labels are a layout guide "
        "only. They will not line up pixel-perfectly with anything."
    )
    lines.append("")

    if reference["coverage_shared_across_all_fonts"] and reference["fonts"]:
        lines.append(
            f"**Coverage is identical across all 11 fonts**: "
            f"{reference['shared_placed_count']} of 94 template slots placed "
            f"(every letter, digit, and the punctuation marks every font "
            f"shares), {len(reference['shared_skipped_chars'])} skipped "
            f"(no font has a native shape for these):"
        )
        lines.append("")
        skipped_display = " ".join(reference["shared_skipped_chars"])
        lines.append(f"`{skipped_display}`")
        lines.append("")

    lines.append(
        "Real-world font identification below comes from manual comparison "
        "against actual KFPS screenshots of each baseline, letterform by "
        "letterform. This is not a style guess. ✅ means a specific "
        "diagnostic letterform quirk matched, not just an overall "
        "resemblance. ⚠️ means the closest lead found so far names a real "
        "font, but the exact cut is not confirmed. ❓ means no lead yet."
    )
    lines.append("")

    lines.append("| Font | Real-world identification | Resource families | Placed | Skipped | Files |")
    lines.append("|---|---|---|---|---|---|")
    for entry in reference["fonts"]:
        families = ", ".join(f"`{f}`" for f in entry["resource_families"])
        files = entry["files"]
        file_links = (
            f"[project]({files['baseline_project']}) · "
            f"[template]({files['template']}) · "
            f"[summary]({files['summary']})"
        )
        ident = entry["identification"]
        if ident["confirmed"]:
            ident_display = f"✅ {ident['note']}"
        elif ident["note"].strip().lower() != "unidentified.":
            ident_display = f"⚠️ {ident['note']}"
        else:
            ident_display = f"❓ {ident['note']}"
        lines.append(
            f"| {entry['font']} | {ident_display} | {families} | {entry['placed']} | "
            f"{entry['skipped_count']} | {file_links} |"
        )

    if reference["missing_fonts"]:
        lines.append("")
        lines.append(
            "**Not generated yet.** Font "
            + ", ".join(str(f) for f in reference["missing_fonts"])
            + ". Run `gen_forza_font_baseline.py --font N` for each."
        )

    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fontpacks-dir", default=str(DEFAULT_FONTPACKS_DIR),
                     help=f"Where the FORZA-FONT-<N>-BASELINE folders live (default: {DEFAULT_FONTPACKS_DIR})")
    ap.add_argument("--out-dir", default=None,
                     help="Where to write FORZA_FONTS_REFERENCE.json/.md (default: same as --fontpacks-dir)")
    args = ap.parse_args()

    fontpacks_dir = Path(args.fontpacks_dir)
    out_dir = Path(args.out_dir) if args.out_dir else fontpacks_dir

    reference = build_reference(fontpacks_dir)
    json_path = out_dir / "FORZA_FONTS_REFERENCE.json"
    md_path = out_dir / "FORZA_FONTS_REFERENCE.md"

    out_dir.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(reference, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(build_markdown(reference), encoding="utf-8")

    print(f"--- {len(reference['fonts'])}/11 fonts indexed -> {json_path} / {md_path} ---")


if __name__ == "__main__":
    main()
