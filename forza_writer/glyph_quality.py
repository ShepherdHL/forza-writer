"""Independent visual QA for primitive-composed glyph JSON.

The fitter optimizes a low-resolution working mask.  This module deliberately
starts again from the font outline and the *exported* shape dictionaries at a
higher resolution, so serialization/unit-conversion/mask bugs are measured too.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

DEFAULT_VERIFY_RESOLUTION = 256
DEFAULT_PASS_IOU = 0.90
DEFAULT_PASS_BOUNDARY_F1 = 0.80


def render_shapes_mask(shapes: list[dict], resolution: int) -> tuple[np.ndarray, list[int]]:
    """Render exported Forza primitive layers, including ordered mask cutouts."""
    from forza_writer.primitive_fit import render_candidate, shape_to_render_params
    from forza_writer.primitive_shapes import PRIMITIVE_CATALOG

    canvas = np.zeros((resolution, resolution), dtype=bool)
    unknown: list[int] = []
    for shape in shapes:
        shape_id, cx, cy, sx, sy, rotation, skew_x = shape_to_render_params(shape, resolution)
        if shape_id is None:
            unknown.append(int(shape.get("type_word", -1)))
            continue
        layer = render_candidate(
            PRIMITIVE_CATALOG[shape_id], cx, cy, sx, sy, rotation, resolution, skew_x)
        is_mask = bool(shape.get("mask") or (len(shape.get("data", [])) > 6 and shape["data"][6]))
        canvas = (canvas & ~layer) if is_mask else (canvas | layer)
    return canvas, unknown


def _component_count(mask: np.ndarray) -> int:
    """Count 8-connected components without adding a scipy dependency."""
    seen = np.zeros_like(mask, dtype=bool)
    height, width = mask.shape
    count = 0
    for y, x in np.argwhere(mask):
        if seen[y, x]:
            continue
        count += 1
        stack = [(int(y), int(x))]
        seen[y, x] = True
        while stack:
            cy, cx = stack.pop()
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if not (dx or dy):
                        continue
                    ny, nx = cy + dy, cx + dx
                    if 0 <= ny < height and 0 <= nx < width and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
    return count


def _hole_count(mask: np.ndarray) -> int:
    """Count enclosed background regions inside the ink's tight bounding box."""
    ys, xs = np.nonzero(mask)
    if not len(xs):
        return 0
    crop = mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    background = ~np.pad(crop, 1, constant_values=False)
    # The padded exterior is one component; all remaining components are holes.
    return max(0, _component_count(background) - 1)


def _boundary(mask: np.ndarray) -> np.ndarray:
    interior = mask.copy()
    for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        shifted = np.roll(mask, (dy, dx), axis=(0, 1))
        if dy == -1:
            shifted[-1, :] = False
        elif dy == 1:
            shifted[0, :] = False
        if dx == -1:
            shifted[:, -1] = False
        elif dx == 1:
            shifted[:, 0] = False
        interior &= shifted
    return mask & ~interior


def _dilate(mask: np.ndarray, radius: int) -> np.ndarray:
    out = np.zeros_like(mask)
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            shifted = np.roll(mask, (dy, dx), axis=(0, 1))
            if dy < 0:
                shifted[dy:, :] = False
            elif dy > 0:
                shifted[:dy, :] = False
            if dx < 0:
                shifted[:, dx:] = False
            elif dx > 0:
                shifted[:, :dx] = False
            out |= shifted
    return out


def compare_masks(target: np.ndarray, generated: np.ndarray, *, boundary_tolerance: int = 2,
                  unknown_type_words: list[int] | None = None) -> dict:
    intersection = int(np.count_nonzero(target & generated))
    target_area = int(np.count_nonzero(target))
    generated_area = int(np.count_nonzero(generated))
    union = target_area + generated_area - intersection
    precision = intersection / generated_area if generated_area else (1.0 if not target_area else 0.0)
    recall = intersection / target_area if target_area else (1.0 if not generated_area else 0.0)
    iou = intersection / union if union else 1.0

    target_boundary = _boundary(target)
    generated_boundary = _boundary(generated)
    target_boundary_n = int(target_boundary.sum())
    generated_boundary_n = int(generated_boundary.sum())
    boundary_precision = (int((generated_boundary & _dilate(target_boundary, boundary_tolerance)).sum()) /
                          generated_boundary_n) if generated_boundary_n else 0.0
    boundary_recall = (int((target_boundary & _dilate(generated_boundary, boundary_tolerance)).sum()) /
                       target_boundary_n) if target_boundary_n else 0.0
    boundary_f1 = (2 * boundary_precision * boundary_recall /
                   (boundary_precision + boundary_recall)) if boundary_precision + boundary_recall else 0.0

    target_components = _component_count(target)
    generated_components = _component_count(generated)
    target_holes = _hole_count(target)
    generated_holes = _hole_count(generated)
    unknown = sorted(set(unknown_type_words or []))
    passed = (iou >= DEFAULT_PASS_IOU and boundary_f1 >= DEFAULT_PASS_BOUNDARY_F1
              and target_components == generated_components and target_holes == generated_holes and not unknown)
    return {
        "resolution": int(target.shape[0]),
        "iou": round(iou, 6),
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "boundary_f1": round(boundary_f1, 6),
        "components_expected": target_components,
        "components_generated": generated_components,
        "holes_expected": target_holes,
        "holes_generated": generated_holes,
        "unknown_type_words": unknown,
        "verdict": "pass" if passed else "review",
    }


def assess_glyph(char: str, font_path: Path, shapes: list[dict], curve_segments: int = 8,
                 resolution: int = DEFAULT_VERIFY_RESOLUTION) -> tuple[dict, np.ndarray, np.ndarray]:
    """Return quality metrics plus the reference and generated masks."""
    from forza_writer.primitive_fit import rasterize_contours
    from gen_modelbin import extract_contours, normalize_to_128

    contours, upm = extract_contours(char, Path(font_path), curve_segments)
    target = rasterize_contours(normalize_to_128(contours, upm), resolution)
    generated, unknown = render_shapes_mask(shapes, resolution)
    return compare_masks(target, generated, unknown_type_words=unknown), target, generated


def assess_glyph_name(glyph_name: str, font_path: Path, shapes: list[dict],
                      curve_segments: int = 8,
                      resolution: int = DEFAULT_VERIFY_RESOLUTION
                      ) -> tuple[dict, np.ndarray, np.ndarray]:
    """Quality-check an explicit glyph selected by OpenType shaping."""
    from forza_writer.primitive_fit import rasterize_contours
    from gen_modelbin import extract_glyph_contours, normalize_to_128

    contours, upm = extract_glyph_contours(glyph_name, Path(font_path), curve_segments)
    target = rasterize_contours(normalize_to_128(contours, upm), resolution)
    generated, unknown = render_shapes_mask(shapes, resolution)
    return compare_masks(target, generated, unknown_type_words=unknown), target, generated


def diff_overlay_image(target: np.ndarray, generated: np.ndarray) -> Image.Image:
    """White=match, blue=missing (in target, not generated), red=overshoot
    (in generated, not target)."""
    rgb = np.zeros((*target.shape, 3), dtype=np.uint8)
    rgb[target & generated] = (245, 245, 245)
    rgb[target & ~generated] = (45, 125, 255)
    rgb[generated & ~target] = (245, 70, 70)
    return Image.fromarray(rgb, "RGB")


def save_diff_overlay(path: Path, target: np.ndarray, generated: np.ndarray) -> Path:
    """Write a white=match, blue=missing, red=overshoot diagnostic PNG."""
    path.parent.mkdir(parents=True, exist_ok=True)
    diff_overlay_image(target, generated).save(path)
    return path
