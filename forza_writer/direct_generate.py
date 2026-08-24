"""Generate one complete FH6 text design directly from typed text.

This deliberately exposes two genuinely different pipelines:

* ``modern`` fits each distinct glyph with Forza Writer's primitive-shape
  library and composes the results with the font's real metrics.
* ``legacy`` rasterizes the complete text run and applies the original Text
  Vinyl Generator's greedy rectangle trace.  Rendering the run as a whole
  preserves Pillow/FreeType kerning and shaping and makes this a useful
  reference when debugging the newer reusable-glyph pipeline.
"""

from __future__ import annotations

from pathlib import Path

from fontTools.ttLib import TTFont
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from forza_writer.legacy_primitive_fit import (
    DEFAULT_CELL_SIZE,
    DEFAULT_FONT_SIZE,
    DEFAULT_PADDING,
    SQUARE_TYPECODE,
    SQUARE_TYPE_WORD,
    _decompose_mask_to_rectangles,
)
from forza_writer.layout import PIXEL_ART_SQUARE_SIZE
from forza_writer.primitive_fit import (
    fit_glyph_name_with_strategy,
    placements_to_shapes,
    rasterize_contours,
)
from forza_writer.glyph_quality import assess_glyph_name
from forza_writer.rect_decompose import decompose_mask_to_rects, rects_to_placements
from forza_writer.shaped_text import shape_text
from forza_writer.text_compose import compose_shaped_lines

# Direct Generation is the quality-first troubleshooting path.  Its output
# should trace the selected font, not merely suggest it with decorative FH6
# primitives.  At 64x64, an unlimited exact decomposition is still bounded
# by one Square per ink pixel, while the largest-rectangle pass normally
# produces far fewer layers.
DIRECT_TRACE_RESOLUTION = 48
DIRECT_VERIFY_RESOLUTION = 128
DIRECT_PRIMITIVE_MIN_IOU = 0.94
DIRECT_PRIMITIVE_MIN_PRECISION = 0.97
DIRECT_PRIMITIVE_MIN_BOUNDARY_F1 = 0.88

METHODS = ("modern", "legacy", "image")


def _otsu_threshold(values: np.ndarray) -> int:
    """Return a deterministic Otsu split for one uint8 channel."""
    histogram = np.bincount(values.reshape(-1), minlength=256).astype(np.float64)
    total = histogram.sum()
    weighted_total = np.dot(np.arange(256), histogram)
    background_weight = 0.0
    background_sum = 0.0
    best_variance = -1.0
    best_threshold = 127
    for threshold in range(255):
        background_weight += histogram[threshold]
        if background_weight == 0:
            continue
        foreground_weight = total - background_weight
        if foreground_weight == 0:
            break
        background_sum += threshold * histogram[threshold]
        background_mean = background_sum / background_weight
        foreground_mean = (weighted_total - background_sum) / foreground_weight
        variance = background_weight * foreground_weight * (background_mean - foreground_mean) ** 2
        if variance > best_variance:
            best_variance = variance
            best_threshold = threshold
    return best_threshold


def _image_ink_mask(image: Image.Image, polarity: str, threshold: int | None) -> tuple[np.ndarray, str, int]:
    """Extract a single ink silhouette without turning this into a general image tracer."""
    rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    rgb = rgba[..., :3]
    alpha = rgba[..., 3]
    if polarity not in {"auto", "light", "dark", "alpha"}:
        raise ValueError("polarity must be auto, light, dark, or alpha")
    if polarity == "alpha" or (polarity == "auto" and alpha.min() < 250):
        cut = 32 if threshold is None else max(0, min(255, int(threshold)))
        return alpha >= cut, "alpha", cut

    luminance = np.rint(
        rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722
    ).astype(np.uint8)
    cut = _otsu_threshold(luminance) if threshold is None else max(0, min(255, int(threshold)))
    resolved = polarity
    if resolved == "auto":
        # Lettering normally occupies less of a crop than its background.
        resolved = "light" if np.count_nonzero(luminance > cut) < np.count_nonzero(luminance <= cut) else "dark"
    # Requiring all channels to clear the cut makes light mode particularly
    # good at isolating white signatures from saturated livery artwork.
    mask = (rgb.min(axis=2) > cut) if resolved == "light" else (rgb.max(axis=2) <= cut)
    return mask, resolved, cut


def generate_image(
    image_path: str | Path,
    *,
    polarity: str = "auto",
    threshold: int | None = None,
    cell_size: int = DEFAULT_CELL_SIZE,
    max_dimension: int = 256,
    design_size: float = 300.0,
) -> tuple[list[dict], list[str], dict]:
    """Lift a monochrome lettering/signature silhouette from an image."""
    image_path = Path(image_path)
    with Image.open(image_path) as source:
        image = source.convert("RGBA")
    original_size = image.size  # before any downscale, for the diagnostics record
    limit = max(32, min(1024, int(max_dimension)))
    if max(image.size) > limit:
        scale = limit / max(image.size)
        image = image.resize(
            (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
            Image.Resampling.LANCZOS,
        )
    mask, resolved_polarity, resolved_threshold = _image_ink_mask(image, polarity, threshold)
    mask_image = Image.fromarray(np.where(mask, 255, 0).astype(np.uint8), mode="L")
    cell = max(1, min(16, int(cell_size)))
    rects = _decompose_mask_to_rectangles(mask_image, cell)
    if not rects:
        raise ValueError("No lettering pixels were found; try the opposite foreground or adjust the threshold")

    x_min = min(x for x, _y, _w, _h in rects)
    x_max = max(x + w for x, _y, w, _h in rects)
    y_min = min(y for _x, y, _w, _h in rects)
    y_max = max(y + h for _x, y, _w, h in rects)
    cx, cy = (x_min + x_max) / 2.0, (y_min + y_max) / 2.0
    scale = design_size / (max(x_max - x_min, y_max - y_min) or 1)
    shapes = [{
        "type": SQUARE_TYPECODE,
        "type_word": SQUARE_TYPE_WORD,
        "data": [
            round((x + width / 2.0 - cx) * scale, 6),
            round((y + height / 2.0 - cy) * scale, 6),
            round(width * scale / PIXEL_ART_SQUARE_SIZE, 6),
            round(height * scale / PIXEL_ART_SQUARE_SIZE, 6),
            0.0, 0.0, 0,
        ],
        "color": [255, 255, 255, 255],
        "mask": False,
    } for x, y, width, height in rects]
    # The trace snapshot rides along in the metadata so a caller that wants
    # debug output can render it later without re-running the trace (and so
    # getting a *different* answer than the one it is meant to explain).
    # Callers that don't want it simply ignore the key.
    from forza_writer.image_debug import ImageTraceDebug

    return shapes, [], {
        "method": "image",
        "source_size": list(image.size),
        "polarity": resolved_polarity,
        "threshold": resolved_threshold,
        "cell_size": cell,
        "rectangles": len(rects),
        "trace_debug": ImageTraceDebug(
            image=image, mask=mask, rects=list(rects),
            polarity=resolved_polarity, threshold=resolved_threshold,
            cell_size=cell, source_size=original_size),
    }


def supported_characters(text: str, font_path: str | Path) -> tuple[set[str], list[str]]:
    """Return drawable characters and ordered unsupported characters.

    Whitespace is layout rather than a glyph artifact and is therefore always
    accepted.  Unsupported characters are reported once, in input order.
    """
    font = TTFont(str(font_path), lazy=True, fontNumber=0)
    try:
        cmap = font.getBestCmap() or {}
    finally:
        font.close()
    drawable: set[str] = set()
    missing: list[str] = []
    for char in text:
        if char.isspace():
            continue
        if ord(char) in cmap:
            drawable.add(char)
        elif char not in missing:
            missing.append(char)
    return drawable, missing


def generate_modern(
    text: str,
    font_path: str | Path,
    *,
    curve_segments: int = 8,
    align: str = "left",
    letter_spacing: float = 0.0,
    mask_mode: str = "auto",
    compute_backend: str = "cpu",
) -> tuple[list[dict], list[str], dict]:
    """Fit each unique glyph with a quality-gated primitive/Square hybrid.

    The general fontpack fitter intentionally trades fidelity for a small
    layer count by approximating curves with FH6's stars, arrows, rings, and
    other primitives.  That trade is actively unhelpful in Direct Generation,
    whose purpose is to preview the exact requested text.  Rasterizing and
    Each full-library fit is independently rendered and compared with the
    source outline.  It is retained only when it preserves topology, clears
    strict silhouette/edge/overshoot thresholds, and actually saves layers;
    otherwise an exact spill-free Square trace is used.  This keeps a star or
    arrow when it truly matches a glyph without letting layer count excuse a
    visibly unrelated silhouette.
    """
    if not text or not text.strip():
        raise ValueError("Text is empty")
    font_path = Path(font_path)
    shaped_lines = shape_text(text, font_path)
    glyph_sources: dict[str, set[str]] = {}
    for line in shaped_lines:
        for glyph in line.glyphs:
            glyph_sources.setdefault(glyph.glyph_name, set()).add(glyph.source_text)
    shape_map: dict[str, list[dict]] = {}
    strategies: dict[str, str] = {}
    quality_by_glyph: dict[str, dict] = {}
    for glyph_name, sources in glyph_sources.items():
        # Import through the shared outline pipeline so variable fonts,
        # curve flattening, and normalization stay identical to fontpacks.
        from gen_modelbin import extract_glyph_contours, normalize_to_128

        contours, units_per_em = extract_glyph_contours(
            glyph_name, font_path, max(1, int(curve_segments)))
        if glyph_name == ".notdef" or not any(contours):
            shape_map[glyph_name] = []
            strategies[glyph_name] = (
                "missing_glyph" if glyph_name == ".notdef" else "empty_outline")
            quality_by_glyph[glyph_name] = {
                "selected": "layout_only",
                "primitive_layers": 0,
                "exact_layers": 0,
                "selected_skewed_layers": 0,
                "source_text": sorted(sources),
            }
            continue
        normalized = normalize_to_128(contours, units_per_em)
        target = rasterize_contours(normalized, DIRECT_TRACE_RESOLUTION)
        rects = decompose_mask_to_rects(
            target, max_rects=target.size, min_area=1)
        placements = rects_to_placements(rects, DIRECT_TRACE_RESOLUTION)
        exact_shapes = placements_to_shapes(
            placements, DIRECT_TRACE_RESOLUTION)
        primitive_shapes, primitive_strategy = fit_glyph_name_with_strategy(
            glyph_name,
            font_path,
            curve_segments=max(1, int(curve_segments)),
            mask_mode=mask_mode,
            compute_backend=compute_backend,
        )
        quality, _target, _generated = assess_glyph_name(
            glyph_name, font_path, primitive_shapes,
            curve_segments=max(1, int(curve_segments)),
            resolution=DIRECT_VERIFY_RESOLUTION,
        )
        topology_matches = (
            quality["components_expected"] == quality["components_generated"]
            and quality["holes_expected"] == quality["holes_generated"]
            and not quality["unknown_type_words"]
        )
        primitive_is_faithful = (
            quality["iou"] >= DIRECT_PRIMITIVE_MIN_IOU
            and quality["precision"] >= DIRECT_PRIMITIVE_MIN_PRECISION
            and quality["boundary_f1"] >= DIRECT_PRIMITIVE_MIN_BOUNDARY_F1
            and topology_matches
        )
        if primitive_is_faithful and len(primitive_shapes) < len(exact_shapes):
            shape_map[glyph_name] = primitive_shapes
            strategies[glyph_name] = primitive_strategy
            selected = "primitive"
        else:
            shape_map[glyph_name] = exact_shapes
            strategies[glyph_name] = "exact_rectangle_trace"
            selected = "exact"
        quality_by_glyph[glyph_name] = {
            **quality,
            "selected": selected,
            "primitive_layers": len(primitive_shapes),
            "exact_layers": len(exact_shapes),
            "selected_skewed_layers": sum(
                abs(float(shape["data"][5])) > 1e-6 for shape in shape_map[glyph_name]),
            "source_text": sorted(sources),
        }

    shapes, warnings = compose_shaped_lines(
        shaped_lines,
        font_path,
        shape_map,
        curve_segments=max(1, int(curve_segments)),
        align=align,
        letter_spacing=letter_spacing,
    )
    return shapes, warnings, {
        "method": "modern",
        "unique_glyphs": len(shape_map),
        "strategies": strategies,
        "quality_by_glyph": quality_by_glyph,
        "shaping": "harfbuzz",
        "line_directions": [line.direction for line in shaped_lines],
    }


def _render_text_mask(
    text: str,
    font_path: Path,
    font_size: int = DEFAULT_FONT_SIZE,
    padding: int = DEFAULT_PADDING,
) -> Image.Image:
    """Whole-run counterpart of the legacy single-glyph rasterizer."""
    font = ImageFont.truetype(str(font_path), font_size)
    probe = Image.new("L", (4, 4), 0)
    draw = ImageDraw.Draw(probe)
    spacing = max(1, round(font_size * 0.2))
    bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=spacing)
    width = max(4, bbox[2] - bbox[0] + padding * 2)
    height = max(4, bbox[3] - bbox[1] + padding * 2)
    image = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(image)
    origin = (padding - bbox[0], padding - bbox[1])
    draw.multiline_text(origin, text, fill=255, font=font, spacing=spacing)
    return image


def generate_legacy(
    text: str,
    font_path: str | Path,
    *,
    cell_size: int = DEFAULT_CELL_SIZE,
    font_size: int = DEFAULT_FONT_SIZE,
    design_size: float = 300.0,
) -> tuple[list[dict], list[str], dict]:
    """Trace the complete text mask with the original rectangle algorithm."""
    if not text or not text.strip():
        raise ValueError("Text is empty")
    font_path = Path(font_path)
    _drawable, missing = supported_characters(text, font_path)
    mask = _render_text_mask(text, font_path, max(1, int(font_size)))
    rects = _decompose_mask_to_rectangles(mask, max(1, min(16, int(cell_size))))
    if not rects:
        raise ValueError("No text pixels were rendered")

    x_min = min(x for x, _y, _w, _h in rects)
    x_max = max(x + w for x, _y, w, _h in rects)
    y_min = min(y for _x, y, _w, _h in rects)
    y_max = max(y + h for _x, y, _w, h in rects)
    cx = (x_min + x_max) / 2.0
    cy = (y_min + y_max) / 2.0
    scale = design_size / (max(x_max - x_min, y_max - y_min) or 1)

    shapes = []
    for x, y, width, height in rects:
        shapes.append({
            "type": SQUARE_TYPECODE,
            "type_word": SQUARE_TYPE_WORD,
            "data": [
                round((x + width / 2.0 - cx) * scale, 6),
                round((y + height / 2.0 - cy) * scale, 6),
                round(width * scale / PIXEL_ART_SQUARE_SIZE, 6),
                round(height * scale / PIXEL_ART_SQUARE_SIZE, 6),
                0.0,
                0.0,
                0,
            ],
            "color": [255, 255, 255, 255],
            "mask": False,
        })
    warnings = [f"{char!r} is not supported by {font_path.name}; fallback glyph may appear"
                for char in missing]
    return shapes, warnings, {
        "method": "legacy",
        "rectangles": len(rects),
        "cell_size": max(1, min(16, int(cell_size))),
    }


def generate_direct(
    text: str = "",
    font_path: str | Path | None = None,
    method: str = "modern",
    **options,
) -> tuple[list[dict], list[str], dict]:
    """Dispatch a Direct Generator request to the selected pipeline."""
    if method == "modern":
        if font_path is None:
            raise ValueError("font_path is required for modern generation")
        return generate_modern(text, font_path, **options)
    if method == "legacy":
        if font_path is None:
            raise ValueError("font_path is required for legacy generation")
        return generate_legacy(text, font_path, **options)
    if method == "image":
        image_path = options.pop("image_path", None)
        if image_path is None:
            raise ValueError("image_path is required for image generation")
        return generate_image(image_path, **options)
    raise ValueError(f"method must be one of {METHODS}, got {method!r}")
