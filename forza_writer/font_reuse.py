"""Reuse an existing in-game Forza Font letterform instead of composing one
from primitives, when a target glyph happens to already look like it.

Five of FH6's eleven built-in fonts have been positively identified against
real, named fonts by comparing in-game screenshots letterform by letterform
(see tools/gen_forza_fonts_reference.py's FONT_IDENTIFICATION table). Real
outline data for those five is therefore just a font file already sitting in
C:\\Windows\\Fonts, not a guess. The other six Forza Fonts are still
unidentified, so there is no real geometry to compare a target glyph against
for those yet; they are deliberately left out of CONFIRMED_FONT_FILES rather
than guessed at.

This is a per-glyph opportunistic check, not a whole-font one. Amarillo USAF
is nothing like Arial Bold overall, but its capital V happens to match Arial
Bold's V closely enough to reuse outright, at a fraction of the shape count a
primitive composition needs for the same letter. Every character is checked
against every confirmed font independently; most glyphs will match none of
them and fall through to the normal fit unchanged.

Two different fonts drawn at the "same" cap height routinely still differ in
stroke weight, which a rigid same-scale comparison penalizes far more
harshly than a person looking at the result would: measured on Amarillo
USAF's own capital V against Arial Bold's, native scale scores IoU 0.51, but
the same pair scored at the non-uniform stretch the font's actual author
picked by hand (confirmed against the real hand-built project file) reaches
IoU 0.86 at 100% precision -- no ink spills outside the target at all, only
a difference in how much of the target's own ink gets covered. So this
searches a small stretch grid per candidate the same way primitive_fit's own
ASPECTS ladder does for primitives, rather than comparing once at native
proportions.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
from PIL import Image

# Forza Font number -> real font filename. Both the identification and the
# specific weight are confirmed by letterform comparison against actual
# in-game screenshots, not assumed from style alone (font 9 specifically
# matched Rockwell *Bold*, not Regular).
CONFIRMED_FONT_FILES: dict[int, str] = {
    1: "arialbd.ttf",   # Arial Bold
    6: "BRUSHSCI.TTF",  # Brush Script MT
    7: "HATTEN.TTF",    # Haettenschweiler
    9: "ROCKB.TTF",     # Rockwell Bold
    11: "GOTHICB.TTF",  # Century Gothic Bold
}

_WINDOWS_FONTS_DIR = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"

# Same glyph_size default primitive_fit.placements_to_shapes uses, so a
# reused whole-glyph shape sits at the same real-world size a primitive
# composition of the same glyph would.
_DEFAULT_GLYPH_SIZE = 300.0

# Independent x/y stretch factors tried per candidate, centered, same idea
# as primitive_fit's own coarse-then-accept search. Weighted toward
# horizontal compression: stroke-weight mismatches between two unrelated
# fonts show up mostly as "the borrowed letter is wider/bolder," per the
# module docstring's own measured example, so this samples x more densely
# than y.
_STRETCH_X = (0.60, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 1.0, 1.05, 1.1, 1.2)
_STRETCH_Y = (0.9, 1.0, 1.1)

# Deliberately not the fontpack quality gate's pass bar (glyph_quality.
# compare_masks, IoU >= 0.90 and boundary_f1 >= 0.80): boundary_f1 checks
# edge alignment within a tight pixel tolerance, which two different
# fonts' strokes essentially never clear even at their best-fitting
# stretch, per the module docstring's measured example (boundary_f1 0.52 at
# the stretch that already reaches 100% precision). Precision matters more
# here than boundary agreement: it is the "does this spill ink outside the
# target's silhouette" check, which is what would actually look wrong on a
# vinyl. Topology (hole count) is still required, so a substitute
# reasonable on raw overlap can't still be structurally the wrong letter.
MIN_IOU = 0.85
MIN_PRECISION = 0.95


def resolve_font_path(filename: str) -> Path | None:
    """Not underscore-prefixed: forza_writer.glyph_quality also calls this,
    to re-render an already-placed font_reuse shape from the same real font
    file that produced it, for preview/quality-gate purposes."""
    path = _WINDOWS_FONTS_DIR / filename
    return path if path.is_file() else None


def _stretched(mask: np.ndarray, sx: float, sy: float) -> np.ndarray:
    if sx == 1.0 and sy == 1.0:
        return mask
    img = Image.fromarray((mask * 255).astype(np.uint8))
    w, h = img.size
    new_w, new_h = max(1, round(w * sx)), max(1, round(h * sy))
    resized = img.resize((new_w, new_h), Image.NEAREST)
    canvas = Image.new("L", (w, h), 0)
    canvas.paste(resized, ((w - new_w) // 2, (h - new_h) // 2))
    return np.array(canvas, dtype=bool)


def best_reuse_candidate(char: str, target_contours_norm, resolution: int,
                          glyph_size: float = _DEFAULT_GLYPH_SIZE,
                          ) -> tuple[int, dict, float] | None:
    """The best confirmed-font substitute for `char`, or None if nothing
    clears `MIN_IOU`/`MIN_PRECISION` at its best-fitting stretch.

    Returns `(font_number, forza_writer shape dict, iou)` for the single
    best match among those that pass, never a partial/best-effort pick: a
    substitute that merely resembles the target is worse than the normal
    fit, since it is presented as *exactly* this glyph, not an
    approximation of it. The winning stretch is baked into the returned
    shape's own scale_x/scale_y, same as the hand-built reference project
    this module's calibration measurement came from.
    """
    from forza_writer.layout import PIXEL_ART_SQUARE_SIZE
    from forza_writer.primitive_fit import rasterize_contours
    from forza_writer.glyph_quality import _component_count, _hole_count, compare_masks
    from forza_writer.shapes import char_to_resource, resource_to_shape_word, resource_to_typecode
    from gen_modelbin import extract_contours, normalize_to_128

    target_mask = rasterize_contours(target_contours_norm, resolution)
    if not target_mask.any():
        return None
    target_holes = _hole_count(target_mask)
    target_components = _component_count(target_mask)

    best: tuple[float, int, float, float, float] | None = None  # iou, font, sx, sy, precision
    for font_number, filename in CONFIRMED_FONT_FILES.items():
        resource = char_to_resource(char, font_number)
        if resource is None:
            continue
        font_path = resolve_font_path(filename)
        if font_path is None:
            continue
        try:
            contours, upm = extract_contours(char, font_path, 8)
        except Exception:
            continue
        candidate_native = rasterize_contours(normalize_to_128(contours, upm), resolution)
        if not candidate_native.any():
            continue
        for sx in _STRETCH_X:
            for sy in _STRETCH_Y:
                stretched = _stretched(candidate_native, sx, sy)
                quality = compare_masks(target_mask, stretched)
                if quality["iou"] < MIN_IOU or quality["precision"] < MIN_PRECISION:
                    continue
                if (quality["holes_generated"] != target_holes
                        or quality["components_generated"] != target_components):
                    continue
                if best is None or quality["iou"] > best[0]:
                    best = (quality["iou"], font_number, sx, sy, quality["precision"])
    if best is None:
        return None

    iou, font_number, sx, sy, _precision = best
    family, index = char_to_resource(char, font_number)
    base_scale = glyph_size / PIXEL_ART_SQUARE_SIZE
    shape = {
        "type": resource_to_typecode(family, index),
        "type_word": resource_to_shape_word(family, index),
        "data": [0.0, 0.0, round(base_scale * sx, 6), round(base_scale * sy, 6), 0.0, 0.0, 0],
        "color": [255, 255, 255, 255],
        "mask": False,
    }
    return font_number, shape, iou
