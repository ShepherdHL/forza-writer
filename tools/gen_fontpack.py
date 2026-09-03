"""
Generate a full, dafont-style categorized "fontpack" from a font: every
renderable character in the font's cmap, sorted into Uppercase/Lowercase/
Letters/Numbers/Punctuation/Symbols subfolders, plus a manifest.json cataloging every
glyph (and every skipped one, with why).

Each glyph can be generated as a custom vector mesh (.modelbin, requires a
catalog hijack + Vinyls.zip injection to actually use in-game, see README.md),
a primitive-composition JSON built via forza-writer's own vector-outline
fitter (works in-game today, no hijack needed), or a primitive-composition
JSON via the legacy raster-trace generator (a faithful port of the original
text-vinyl generator shipped in bvzray's forza-painter-fh6 v1.9.5, see
forza_writer/legacy_primitive_fit.py).

Usage:
    python tools/gen_fontpack.py --font-file "C:\\path\\to\\AmarilloUSAF.ttf" --prefix AMARILLO-USAF
    python tools/gen_fontpack.py --font-file font.ttf --prefix MYFONT --output json
    python tools/gen_fontpack.py --font-file font.ttf --prefix MYFONT --output json_legacy --out-dir data/fontpacks

--output modelbin (default) requires a reference modelbin (default:
user-assets/S_01.modelbin), see README.md. --output json/json_legacy need no
reference file at all.

With no scoping flags, every renderable character in the font's cmap is
generated: the long-standing default, and still fine for a small Latin
font. For a CJK font that can mean thousands of Han ideographs in one run;
--chars/--script/--category/--all-han restrict the batch the same way the
GUI's Generator tab does:
    python tools/gen_fontpack.py --font-file NotoSansTC.ttf --prefix NOTO-TC --output json --script "Traditional Chinese"
    python tools/gen_fontpack.py --font-file font.ttf --prefix MYFONT --output json --category Uppercase --category Numbers
    python tools/gen_fontpack.py --font-file font.ttf --prefix MYFONT --output json --chars "Hello, World!"
"""
import argparse
import json
import re
import shutil
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen_modelbin import (  # noqa: E402
    DEFAULT_REFERENCE_MODELBIN,
    char_filename,
    generate_glyph,
    validate_modelbin,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from forza_writer.alphabets import ALPHABETS, NO_ALPHABET_SCRIPTS, groups_for_script  # noqa: E402
from forza_writer.charset import CATEGORY_ORDER, charset_from_font, is_han_char  # noqa: E402
from forza_writer.export import save as save_json, to_json  # noqa: E402
from forza_writer.legacy_primitive_fit import fit_glyph_legacy  # noqa: E402
from forza_writer.primitive_fit import fit_glyph_with_strategy  # noqa: E402
from forza_writer.high_contrast import seed_for_char  # noqa: E402
from forza_writer.generation_policy import (  # noqa: E402
    DEFAULT_POLICY, GenerationPolicy, GenerationStats, policy_to_dict)
from forza_writer.glyph_quality import assess_glyph, save_diff_overlay  # noqa: E402
from forza_writer.compute_backend import resolve_backend  # noqa: E402

DEFAULT_FONTPACK_OUT_DIR = Path("data/fontpacks")
DEFAULT_MODELBIN_OUT_DIR = Path("data/modelbin")
# Kept as a compatibility alias for callers importing the old constant.
DEFAULT_OUT_DIR = DEFAULT_FONTPACK_OUT_DIR
OUTPUT_MODES = ("modelbin", "json", "json_legacy")
MANIFEST_FORMAT = "forza_writer_fontpack_v2"


def generation_profile_id(output: str, curve_segments: int, resolved_backend: str) -> str:
    """Stable, filesystem-safe identity for settings that change output.

    Quality-check resolution is intentionally absent: it changes validation
    artifacts, not generated geometry. The legacy fitter ignores curve
    flattening entirely, so its profile says so rather than implying that
    Curve Smoothness affected it.
    """
    if output == "json":
        return f"JSON-{resolved_backend.upper()}-CS{curve_segments}"
    if output == "json_legacy":
        return "JSON-LEGACY-CPU"
    return f"MODELBIN-CS{curve_segments}"


def pack_dir_for(out_dir: Path, prefix: str, output: str, curve_segments: int,
                  resolved_backend: str) -> Path:
    """Where this exact generation profile's pack *starts out*: one folder
    per font (`prefix`), with each profile (output format x backend x curve
    smoothness) nested inside it, so a CPU and a CUDA run of the same font
    sit together instead of scattered as flat siblings under `out_dir`.

    This is a write target, not a lookup: `build_fontpack` writes every
    glyph here, then -- for a json/json_legacy pack, once the true total
    shape count is known -- renames this exact directory to
    `<profile_id>_<total_shapes>` (see the total_shapes block near the end
    of `build_fontpack`). A caller that needs to *find* an
    already-generated pack after the fact (Export to KFPS, an "open output
    folder" action, abort cleanup) has to account for that possible suffix
    instead of assuming this exact path still exists; use
    `find_pack_dir` for that, not this function.
    """
    return Path(out_dir) / prefix / generation_profile_id(output, curve_segments, resolved_backend)


# Matches "<anything>_<digits>" at the end of a profile dir name -- the
# layer-count suffix build_fontpack appends, e.g. "JSON-CUDA-CS8_212".
_PACK_DIR_SUFFIX_RE = re.compile(r"^(?P<base>.+)_(?P<count>\d+)$")


def find_pack_dir(out_dir: Path, prefix: str, output: str, curve_segments: int,
                   resolved_backend: str) -> Path | None:
    """Locate an already-generated pack for this exact profile, whether or
    not `build_fontpack` renamed it to include a layer-count suffix.

    Checks the unsuffixed path first (always correct for modelbin, which
    never gets a suffix; also covers a json pack from before this feature
    existed), then falls back to the one `<profile_id>_<digits>` sibling
    directory, if exactly one exists. Returns None if neither is found, or
    if more than one suffixed sibling exists (an inconsistent state
    `build_fontpack` shouldn't produce on its own, since it replaces its
    own prior suffixed output rather than leaving old ones behind -- but
    this refuses to guess which is current rather than silently picking
    one).
    """
    bare = pack_dir_for(out_dir, prefix, output, curve_segments, resolved_backend)
    if bare.is_dir():
        return bare
    if not bare.parent.is_dir():
        return None
    matches = [p for p in bare.parent.glob(f"{bare.name}_*")
               if p.is_dir() and _PACK_DIR_SUFFIX_RE.match(p.name)
               and _PACK_DIR_SUFFIX_RE.match(p.name)["base"] == bare.name]
    return matches[0] if len(matches) == 1 else None


def glyph_filename(prefix: str, char: str, ext: str = "modelbin") -> str:
    """Filesystem-safe filename for a glyph.

    Plain ASCII letters/digits use gen_modelbin's existing char_filename
    convention (readable, with a _lc marker disambiguating case). Anything
    else (punctuation and symbols can include characters that are illegal
    in Windows filenames: /, \\, :, *, ?, ", <, >, |) is named by its
    Unicode codepoint instead, which is always filesystem-safe.
    """
    if char.isascii() and char.isalnum():
        stem = Path(char_filename(prefix, char)).stem
        return f"{stem}.{ext}"
    return f"{prefix}_U+{ord(char):04X}.{ext}"


def build_fontpack(font_path: Path, out_dir: Path, prefix: str,
                    output: str = "modelbin", reference_modelbin: Path | None = None,
                    curve_segments: int = 8, flip_winding: bool = True,
                    chars: set[str] | None = None,
                    should_stop=lambda: False, on_glyph=None,
                    log=print, allow_stencil: bool = True,
                    mask_overrides: dict[str, str] | None = None,
                    manual_assignments: dict[str, Path] | None = None,
                    verify_quality: bool = True, quality_resolution: int = 256,
                    compute_backend: str = "auto",
                    policy: GenerationPolicy | None = None,
                    source_font_path: Path | None = None,
                    variation: dict | None = None,
                    color_mode: str = "solid",
                    solid_color: tuple[int, int, int, int] = (255, 255, 255, 255),
                    high_contrast_seed: int | None = None) -> dict:
    """Generate a categorized fontpack. Returns the manifest dict (also
    written below `out_dir`; the pack directory is `<out_dir>/<prefix>/
    <output-backend-smoothness>`, see `pack_dir_for`, so CPU/CUDA and
    Curve Smoothness runs of the same font nest together instead of
    overwriting one another or scattering as flat siblings). Per-glyph,
    per-output-mode failures are caught and recorded rather than aborting
    the batch: a modelbin failure doesn't block that glyph's json output
    or vice versa.

    `allow_stencil` (the `--output json`/`json_legacy` paths only;
    `json_legacy` never uses stencil regardless, it has no mask concept at
    all) controls whether `fit_glyph_with_strategy` is allowed to pick the
    stencil strategy for a rectilinear glyph. Stencil wins automatically
    whenever it needs fewer shapes than direct fill. This is expected, not
    a routing bug: the Minecraft Standard Galactic Alphabet's 'X' needs 14
    shapes direct vs. 10 stencil, 'Z' needs 12 vs. 7. Since stencil relies
    on FH6 mask-layer semantics that haven't been confirmed against a live
    session yet (see RESEARCH.md), `allow_stencil=False` forces direct fill
    everywhere, trading some shape-count savings for avoiding masks
    entirely. This is what the GUI's "Allow layer masks" checkbox does.
    This is the *default* mask mode for every glyph; `mask_overrides`
    overrides it per glyph.

    `mask_overrides`, if given, maps individual characters to a
    `primitive_fit.MaskMode` string (`"auto"` / `"force"` / `"never"`):
    the GUI's Advanced Mode per-glyph choice. A character not present in
    the dict falls back to `allow_stencil`'s default (`"auto"` if True,
    `"never"` if False). `"force"` works even on curved glyphs (see
    `primitive_fit.fit_placements`'s `mask_mode="force"` docs), something
    `allow_stencil` alone could never do. `--output json` only, same as
    `allow_stencil`.

    `manual_assignments`, if given, maps individual characters to the path
    of an already-made `.json` glyph file (e.g. exported one-by-one from
    KFPS) whose shapes are copied verbatim instead of running auto-fit at
    all: the Configurator tab's per-glyph "assign a file" choice. Takes
    precedence over `mask_overrides`/`allow_stencil` for that character
    (auto-fit never runs for it), and is recorded with `strategy="manual"`.
    `--output json` only, same as `mask_overrides`. A warning is logged
    once (not per glyph) if assignments are given for any other output
    mode, since a manual file is a JSON shape list, not a mesh.

    `chars`, if given, restricts generation to that subset of the font's
    cmap (e.g. a GUI's "Uppercase only" checkbox). Characters not in the
    set are simply omitted from their category, not counted as skipped
    (`skipped` stays reserved for "the font has this glyph but it has no
    visible geometry", an unrelated concept from "the user didn't ask for
    this one").

    `should_stop`, if given, is checked before starting each glyph (never
    mid-glyph, so a stop never leaves a half-written file). Returning True
    halts the batch early. The manifest is still written, reflecting exactly
    what completed before stopping ("halt", as opposed to a caller discarding
    the partial pack itself, which this function has no opinion on; that's
    the caller's call to make, e.g. by deleting `manifest["files_written"]`
    after the fact for an "abort").

    `on_glyph`, if given, is called as `on_glyph(category, entry)` right
    after each glyph's entry is finalized (success or failure), so a caller
    can render a live preview without re-reading anything from disk.

    `color_mode`/`solid_color`/`high_contrast_seed` only affect `--output
    json`'s primitive-composed shapes (there's no per-shape concept on the
    `modelbin` mesh path). `color_mode="solid"` (the default) colors every
    shape `solid_color` (plain white if not given, matching this
    function's own longstanding hardcoded default). `color_mode=
    "high_contrast"` instead gives each glyph's individual shapes their own
    color from `forza_writer.high_contrast`'s curated palette, deterministic
    per `high_contrast_seed` -- see that module and `primitive_fit.
    placements_to_shapes` for how. Recorded into the manifest either way,
    so a pack always says which mode (and, for high_contrast, which seed)
    produced it.
    """
    if output not in OUTPUT_MODES:
        raise ValueError(f"output must be one of {OUTPUT_MODES}, got {output!r}")
    if output == "modelbin" and reference_modelbin is None:
        raise ValueError("reference_modelbin is required for output='modelbin'")
    if manual_assignments and output != "json":
        log(f"  Note: manual_assignments given but output={output!r} — manual file assignments only "
            f"apply to output='json'; ignoring {len(manual_assignments)} assignment(s).")

    policy = policy or DEFAULT_POLICY
    # Checked before any glyph is written rather than per glyph: an
    # unusable policy is a setup mistake, and failing on glyph 1 of 500
    # after creating a pack directory is a worse way to learn that.
    problems = policy.validate()
    if problems:
        raise ValueError("Generation settings cannot be used: " + " ".join(problems))

    backend = resolve_backend(compute_backend if output == "json" else "cpu")
    if output == "json" and compute_backend == "cuda" and not backend.available:
        raise RuntimeError(
            "NVIDIA CUDA was selected but is unavailable. " + backend.detail)
    if output == "json":
        log(f"  Compute backend: {backend.resolved.upper()}"
            f"{f' ({backend.device})' if backend.device else ''}")

    categorized, skipped = charset_from_font(font_path)
    if chars is not None:
        categorized = {cat: [c for c in lst if c in chars] for cat, lst in categorized.items()}
    profile_id = generation_profile_id(output, curve_segments, backend.resolved)
    pack_dir = pack_dir_for(out_dir, prefix, output, curve_segments, backend.resolved)

    manifest = {
        "format": MANIFEST_FORMAT,
        "font_file": str(font_path),
        "source_font_file": str(source_font_path or font_path),
        "variation": variation,
        "prefix": prefix,
        "pack_id": f"{prefix}__{profile_id}",
        "generation_policy": policy_to_dict(policy),
        "generation_profile": {
            "id": profile_id,
            "output": output,
            "curve_segments": curve_segments if output != "json_legacy" else None,
            "compute_backend": backend.resolved,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "output": output,
        "reference_modelbin": str(reference_modelbin) if reference_modelbin else None,
        "curve_segments": curve_segments,
        "flip_winding": flip_winding,
        "compute": {
            "requested": compute_backend,
            "resolved": backend.resolved,
            "device": backend.device,
            "detail": backend.detail,
        },
        "color_mode": color_mode,
        "color_seed": high_contrast_seed if color_mode == "high_contrast" else None,
        "categories": {},
        "skipped": [
            {"char": char, "codepoint": f"U+{ord(char):04X}", "reason": reason}
            for char, reason in skipped
        ],
    }

    counts = {"generated": 0, "failed": 0}
    quality_counts = {"pass": 0, "review": 0}
    stencil_used = False
    files_written: list[str] = []
    halted = False
    for category in CATEGORY_ORDER:
        chars = categorized.get(category, [])
        entries = []
        for char in chars:
            if should_stop():
                halted = True
                break
            entry = {
                "char": char,
                "codepoint": f"U+{ord(char):04X}",
                "unicode_name": unicodedata.name(char, "?"),
                "artifacts": {},
            }

            if output == "modelbin":
                rel_path = Path(category) / glyph_filename(prefix, char, "modelbin")
                out_path = pack_dir / rel_path
                try:
                    generate_glyph(char, font_path, reference_modelbin, out_path,
                                    curve_segments, flip_winding)
                    valid, message = validate_modelbin(out_path)
                    entry["artifacts"]["modelbin"] = {
                        "file": str(rel_path).replace("\\", "/"), "valid": valid, "message": message,
                    }
                    files_written.append(str(rel_path).replace("\\", "/"))
                    counts["generated"] += 1
                    log(f"  [{category}] {'ok  ' if valid else 'WARN'} modelbin {char!r} -> {rel_path}")
                except Exception as exc:
                    entry["artifacts"]["modelbin"] = {"file": None, "valid": False, "message": str(exc)}
                    counts["failed"] += 1
                    log(f"  [{category}] FAIL modelbin {char!r}: {exc}")

            elif output in ("json", "json_legacy"):
                rel_path = Path(category) / glyph_filename(prefix, char, "json")
                out_path = pack_dir / rel_path
                try:
                    # Only the searched json path produces diagnostics; a
                    # manually assigned file and the legacy tracer have no
                    # candidate search to report on.
                    glyph_stats = None
                    if output == "json" and char in (manual_assignments or {}):
                        source = Path(manual_assignments[char])
                        data = json.loads(source.read_text(encoding="utf-8"))
                        shapes, strategy = data.get("shapes", []), "manual"
                    elif output == "json":
                        default_mode = "auto" if allow_stencil else "never"
                        mode = (mask_overrides or {}).get(char, default_mode)
                        glyph_stats = GenerationStats()
                        glyph_seed = (seed_for_char(high_contrast_seed, char)
                                      if color_mode == "high_contrast" and high_contrast_seed is not None
                                      else None)
                        shapes, strategy = fit_glyph_with_strategy(
                            char, font_path, curve_segments, mask_mode=mode,
                            compute_backend=backend.resolved, policy=policy,
                            stats=glyph_stats, solid_color=solid_color,
                            high_contrast_seed=glyph_seed)
                    else:
                        shapes, strategy = fit_glyph_legacy(char, font_path)
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    save_json(to_json(shapes), out_path)
                    quality = None
                    if verify_quality:
                        quality, target_mask, generated_mask = assess_glyph(
                            char, font_path, shapes, curve_segments, quality_resolution)
                    entry["artifacts"]["json"] = {
                        "file": str(rel_path).replace("\\", "/"),
                        "shape_count": len(shapes), "strategy": strategy, "message": "ok",
                    }
                    if glyph_stats is not None:
                        entry["artifacts"]["json"]["diagnostics"] = glyph_stats.to_dict()
                    if quality is not None:
                        entry["artifacts"]["json"]["quality"] = quality
                        quality_counts[quality["verdict"]] += 1
                    files_written.append(str(rel_path).replace("\\", "/"))
                    if quality is not None and quality["verdict"] != "pass":
                        diff_rel = Path("quality") / category / f"{Path(rel_path).stem}_diff.png"
                        save_diff_overlay(pack_dir / diff_rel, target_mask, generated_mask)
                        quality["diff_file"] = str(diff_rel).replace("\\", "/")
                        files_written.append(quality["diff_file"])
                    if strategy in ("stencil", "stencil_search"):
                        stencil_used = True
                    counts["generated"] += 1
                    quality_label = (("PASS" if quality["verdict"] == "pass" else "REVIEW")
                                     if quality is not None else "unchecked")
                    quality_detail = (f"IoU {quality['iou']:.3f}, edge {quality['boundary_f1']:.3f}"
                                      if quality is not None else "quality check disabled")
                    log(f"  [{category}] ok   json     {char!r} -> {rel_path} "
                        f"({len(shapes)} shapes, {strategy}; {quality_label} "
                        f"{quality_detail})")
                except Exception as exc:
                    entry["artifacts"]["json"] = {"file": None, "shape_count": 0, "strategy": None,
                                                   "message": str(exc)}
                    counts["failed"] += 1
                    log(f"  [{category}] FAIL json {char!r}: {exc}")

            entries.append(entry)
            if on_glyph is not None:
                on_glyph(category, entry)
        manifest["categories"][category] = entries
        if halted:
            break

    manifest["files_written"] = files_written
    if halted:
        manifest["halted"] = True
        log("  --- halted early by request ---")

    # Both json strategies ("json" and "json_legacy") share the "json"
    # summary key: callers (the GUI's log-line formatting, in particular)
    # only care that *some* json artifact was generated, not which
    # strategy produced it.
    summary_mode = "json" if output in ("json", "json_legacy") else "modelbin"
    # Sum of every successfully generated glyph's shape_count. modelbin
    # glyphs have no such field (a mesh, not a shape list), so this is 0
    # for a modelbin pack -- correctly leaving its folder name untouched
    # below, since "layer count" isn't a concept that applies to it.
    total_shapes = sum(
        entry.get("artifacts", {}).get("json", {}).get("shape_count") or 0
        for entries in manifest["categories"].values()
        for entry in entries
    )
    manifest["summary"] = {
        "skipped": len(skipped),
        "by_category": {c: len(manifest["categories"].get(c, [])) for c in CATEGORY_ORDER},
        "total_shapes": total_shapes,
        summary_mode: counts,
    }
    if output in ("json", "json_legacy") and verify_quality:
        manifest["summary"]["quality"] = quality_counts
        manifest["quality_policy"] = {
            "resolution": quality_resolution,
            "pass_iou": 0.90,
            "pass_boundary_f1": 0.80,
            "topology_must_match": True,
            "diff_colors": {"match": "white", "missing": "blue", "overshoot": "red"},
        }
    if stencil_used:
        # Mask-layer behavior (stencil mode's cutouts) is implemented per
        # forza-painter-fh6's convention but hasn't been confirmed against a
        # live FH6 session in this project yet (see RESEARCH.md). Flag it so
        # nobody mistakes "generated" for "verified in-game".
        manifest["experimental"] = ("this pack includes stencil-mode glyphs (mask-layer cutouts); "
                                     "mask rendering hasn't been verified against a live FH6 session yet")

    if total_shapes > 0:
        # Renamed only now that the true total is known -- every write
        # above targeted the pre-rename pack_dir, and a directory rename is
        # atomic and doesn't touch any file inside or its already-recorded
        # path (every path in the manifest is relative to pack_dir, not
        # absolute). Only the profile subfolder gets the suffix
        # (JSON-CUDA-CS8 -> JSON-CUDA-CS8_212), not the font-level folder
        # above it: that level can hold several profiles of the same font
        # side by side (see pack_dir_for), each with its own total, so only
        # the subfolder has one well-defined count to name itself after.
        # Any older suffixed sibling of *this* profile is removed first --
        # not just one at today's exact total, but any "<base>_<digits>"
        # match -- otherwise a regenerate that changes the total (a
        # different preset, more characters, ...) would leave the old
        # count's folder behind as an orphan instead of the usual
        # regenerate-overwrites-in-place behavior every other path here
        # already has.
        base_name = pack_dir.name
        for sibling in pack_dir.parent.glob(f"{base_name}_*"):
            match = _PACK_DIR_SUFFIX_RE.match(sibling.name)
            if sibling.is_dir() and match and match["base"] == base_name:
                shutil.rmtree(sibling)
        pack_dir = pack_dir.rename(pack_dir.parent / f"{base_name}_{total_shapes}")

    # The directory build_fontpack actually wrote to, name only (not a full
    # path -- manifest.json intentionally stores no absolute paths
    # elsewhere either). A caller holding this same manifest right after
    # generation (abort cleanup, a "done" log line) can recover the true
    # pack_dir as `original_pack_dir.parent / manifest["pack_dir_name"]`
    # without re-deriving it or guessing at a suffix; a caller coming back
    # later with no manifest in hand yet should use `find_pack_dir` instead.
    manifest["pack_dir_name"] = pack_dir.name

    pack_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = pack_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"--- {summary_mode}: {counts['generated']} ok/{counts['failed']} failed, "
        f"{len(skipped)} skipped (no visible geometry) -> {manifest_path} ---")
    return manifest


def sanitize_prefix(name: str) -> str:
    s = name.strip().upper().replace(" ", "-")
    s = re.sub(r"[^A-Z0-9_\-]", "", s)
    s = re.sub(r"-{2,}", "-", s).strip("-_")
    return s or "CUSTOM"


SCRIPT_CHOICES = sorted(set(ALPHABETS) | NO_ALPHABET_SCRIPTS)


def resolve_requested_chars(font_path: Path, chars: str | None, scripts: list[str] | None,
                            categories: list[str] | None, all_han: bool) -> set[str] | None:
    """Build the `--chars`/`--script`/`--category`/`--all-han` character set.

    Mirrors the GUI's Characters section: additive across every flag given,
    bounded/curated per-script sets from
    `forza_writer/alphabets.py` rather than a script's full Unicode block, and
    full Han coverage only via the explicit, unbounded `--all-han` opt-in.
    Returns None (meaning "the font's entire cmap", this tool's long-standing
    default) when none of the scoping flags are given at all.
    """
    if not (chars or scripts or categories or all_han):
        return None
    result: set[str] = set()
    if chars:
        result.update(c for c in chars if not c.isspace())
    for script in scripts or ():
        for _label, letters in groups_for_script(script):
            result.update(letters)
    if categories or all_han:
        categorized, _skipped = charset_from_font(font_path)
        for category in categories or ():
            result.update(categorized.get(category, []))
        if all_han:
            result.update(c for c in categorized.get("Letters", []) if is_han_char(c))
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--font-file", required=True, help="Path to a TTF/OTF font file")
    ap.add_argument("--prefix", default=None,
                     help="Filename/folder prefix (default: derived from the font's file stem)")
    ap.add_argument("--output", choices=OUTPUT_MODES, default="modelbin",
                     help="modelbin: custom vector mesh (needs a catalog hijack to use in-game). "
                          "json: primitive-composition layer list via forza-writer's own vector-outline "
                          "fitter (works in-game today, no hijack). json_legacy: primitive-composition "
                          "layer list via the legacy raster-trace generator (ported from bvzray's "
                          "forza-painter-fh6 v1.9.5). (default: modelbin)")
    ap.add_argument("--reference-modelbin", default=str(DEFAULT_REFERENCE_MODELBIN),
                     help=f"Reference FH6 modelbin, only needed for --output modelbin "
                          f"(default: {DEFAULT_REFERENCE_MODELBIN}). Not included in this repo — see README.md.")
    ap.add_argument("--out-dir", default=None,
                     help="Fontpack root directory (default: data/modelbin for modelbin output, "
                          "data/fontpacks for JSON output); "
                          f"the pack is written to <out-dir>/<prefix>/<profile>/")
    ap.add_argument("--curve-segments", type=int, default=8,
                     help="Line segments per Bezier curve when flattening (default: 8)")
    ap.add_argument("--no-flip-winding", dest="flip_winding", action="store_false",
                     help="Don't reverse earcut's triangle winding, .modelbin output only (default: flip)")
    ap.add_argument("--no-stencil", dest="allow_stencil", action="store_false",
                     help="Never use the stencil strategy (mask-layer cutouts), --output json only — "
                          "forces direct fill even where stencil would need fewer shapes, trading shape "
                          "count for avoiding FH6 mask layers entirely (default: stencil allowed)")
    ap.add_argument("--no-quality-check", dest="verify_quality", action="store_false",
                    help="Skip high-resolution visual verification of JSON glyphs")
    ap.add_argument("--quality-resolution", type=int, default=256,
                    help="Square raster size for JSON glyph verification (default: 256)")
    ap.add_argument("--compute-backend", choices=("auto", "cuda", "cpu"), default="auto",
                    help="Primitive-fit processor: auto prefers NVIDIA CUDA and falls back to CPU "
                         "(default: auto; --output json only)")
    ap.add_argument("--chars", default=None,
                     help="Only generate these exact characters, e.g. --chars \"ABCabc123\" "
                          "(whitespace ignored). Combine freely with --script/--category/--all-han.")
    ap.add_argument("--script", action="append", default=None, choices=SCRIPT_CHOICES, metavar="NAME",
                     help=f"Restrict to a bounded, curated script set (forza_writer/alphabets.py); "
                          f"repeatable. One of: {', '.join(SCRIPT_CHOICES)}. Simplified/Traditional "
                          f"Chinese use small structural/punctuation/variant test sets, not full Han "
                          f"coverage — pass --all-han for that.")
    ap.add_argument("--category", action="append", default=None, choices=CATEGORY_ORDER, metavar="NAME",
                     help=f"Restrict to one of the font's own Unicode-category buckets; repeatable. "
                          f"One of: {', '.join(CATEGORY_ORDER)}. Letters/Symbols can still be large "
                          f"for a CJK or icon font — this filters by category, not by size.")
    ap.add_argument("--all-han", action="store_true",
                     help="Include every Han ideograph (Chinese/Kanji/Hanja) this font supports, on "
                          "top of any --chars/--script/--category given. Unbounded — can be thousands "
                          "of glyphs for a CJK font. Off by default, same explicit opt-in as the GUI's "
                          "'All Han ideographs (advanced)' checkbox.")
    args = ap.parse_args()

    font_path = Path(args.font_file)
    if not font_path.exists():
        print(f"Font file not found: {font_path}")
        sys.exit(1)

    reference_modelbin = None
    if args.output == "modelbin":
        reference_modelbin = Path(args.reference_modelbin)
        if not reference_modelbin.exists():
            print(f"Reference modelbin not found: {reference_modelbin}")
            print("This file is an extracted FH6 game asset and is not included in this repo.")
            print("See README.md for how to obtain your own copy.")
            sys.exit(1)

    if args.curve_segments < 1:
        print("--curve-segments must be at least 1")
        sys.exit(1)
    if args.quality_resolution < 32:
        print("--quality-resolution must be at least 32")
        sys.exit(1)

    chars = resolve_requested_chars(font_path, args.chars, args.script, args.category, args.all_han)
    if chars is not None and not chars:
        print("--chars/--script/--category/--all-han were given but matched no characters.")
        sys.exit(1)

    prefix = args.prefix or sanitize_prefix(font_path.stem)
    scope = f"{len(chars):,} selected characters" if chars is not None else "entire font cmap"
    print(f"Building fontpack '{prefix}' from {font_path.name} (output={args.output}, scope={scope})...")
    if chars is not None and len(chars) >= 500:
        print(f"  Note: {len(chars):,} glyphs selected — this may take a long time.")
    out_dir = Path(args.out_dir) if args.out_dir else (
        DEFAULT_MODELBIN_OUT_DIR if args.output == 'modelbin' else DEFAULT_FONTPACK_OUT_DIR)
    build_fontpack(font_path, out_dir, prefix, args.output, reference_modelbin,
                    args.curve_segments, args.flip_winding, chars=chars, allow_stencil=args.allow_stencil,
                    verify_quality=args.verify_quality, quality_resolution=args.quality_resolution,
                    compute_backend=args.compute_backend)


if __name__ == "__main__":
    main()
