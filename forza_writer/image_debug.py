"""Why the Image-to-Text trace produced the vinyls it did.

The image path (`direct_generate.generate_image`) makes three decisions that
are invisible in its output: which pixels counted as ink (polarity and
threshold), how those pixels were merged into rectangles (cell size), and
where the result disagrees with the source. A saved copy of the intermediate
mask would show the first and none of the rest, so these renderers exist to
show the actual reasoning: most importantly the *disagreement*, which is what
someone asking "why is that vinyl there?" is really looking at.

Everything here is opt-in and purely diagnostic: nothing in this module feeds
back into generation, and no file is written unless the caller asks for one.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw

# Rendering modes, in the order the UI offers them.
DEBUG_MODES: tuple[str, ...] = ("trace", "heatmap", "contours", "combined")

DEBUG_LABELS: dict[str, str] = {
    "trace": "Final Primitive Trace",
    "heatmap": "Coverage / Accuracy Heatmap",
    "contours": "Source Contours",
    "combined": "Combined Debug View",
}

# Palette chosen so the three heatmap states stay distinguishable in
# greyscale as well as colour, since these get shared as screenshots.
_INK_MATCHED = (86, 186, 116)     # covered ink: the trace got this right
_INK_MISSED = (226, 78, 66)       # ink the trace failed to cover
_INK_OVERSHOOT = (94, 132, 226)   # covered background: spill outside the ink
_BACKDROP = (26, 27, 30)
_TRACE_OUTLINE = (232, 138, 63)
_LABEL_FG = (238, 240, 244)


@dataclass(frozen=True)
class ImageTraceDebug:
    """Everything the renderers need, captured during one image trace.

    Deliberately a plain snapshot rather than a live handle on the generator:
    debug rendering happens after the fact, and must never be able to perturb
    the generation it is describing.
    """

    image: Image.Image                       # the (possibly downscaled) source actually traced
    mask: np.ndarray                         # bool ink silhouette, same size as `image`
    rects: list[tuple[int, int, int, int]]   # (x, y, w, h) in image pixels
    polarity: str
    threshold: int
    cell_size: int
    source_size: tuple[int, int]             # the original file's size, before any downscale

    def coverage(self) -> np.ndarray:
        """Boolean mask of what the emitted rectangles actually cover."""
        covered = np.zeros_like(self.mask)
        for x, y, width, height in self.rects:
            covered[y:y + height, x:x + width] = True
        return covered


def accuracy(debug: ImageTraceDebug) -> dict[str, float | int]:
    """How closely the rectangles reproduce the ink they were traced from."""
    covered = debug.coverage()
    ink = debug.mask
    matched = int(np.count_nonzero(covered & ink))
    missed = int(np.count_nonzero(ink & ~covered))
    overshoot = int(np.count_nonzero(covered & ~ink))
    union = matched + missed + overshoot
    return {
        "ink_pixels": int(np.count_nonzero(ink)),
        "covered_pixels": int(np.count_nonzero(covered)),
        "matched_pixels": matched,
        "missed_pixels": missed,
        "overshoot_pixels": overshoot,
        "iou": (matched / union) if union else 1.0,
        "precision": (matched / (matched + overshoot)) if (matched + overshoot) else 1.0,
        "recall": (matched / (matched + missed)) if (matched + missed) else 1.0,
    }


def diagnostics(debug: ImageTraceDebug) -> dict:
    """JSON-ready record of one trace: what was produced, and how faithfully.

    Written beside the debug image so a result can be compared against another
    run's settings later without re-deriving anything from the output JSON.
    """
    scores = accuracy(debug)
    return {
        "method": "image",
        "source_dimensions": list(debug.source_size),
        "generation_dimensions": list(debug.image.size),
        "downscaled": tuple(debug.source_size) != tuple(debug.image.size),
        "polarity": debug.polarity,
        "threshold": debug.threshold,
        "cell_size": debug.cell_size,
        "vinyl_count": len(debug.rects),
        "vinyl_types": {"Square": len(debug.rects)},
        "accuracy": {k: (round(v, 6) if isinstance(v, float) else v) for k, v in scores.items()},
    }


def _backdrop(size: tuple[int, int]) -> Image.Image:
    return Image.new("RGB", size, _BACKDROP)


def _dimmed_source(debug: ImageTraceDebug) -> Image.Image:
    """The source at low contrast, so overlays read clearly on top of it."""
    base = debug.image.convert("RGB")
    return Image.blend(_backdrop(base.size), base, 0.35)


def render_trace(debug: ImageTraceDebug) -> Image.Image:
    """Every emitted rectangle outlined over the dimmed source.

    Answers "which vinyl is which part of the picture" directly: one outline
    per vinyl the design will contain, in the same positions.
    """
    canvas = _dimmed_source(debug)
    draw = ImageDraw.Draw(canvas)
    for x, y, width, height in debug.rects:
        draw.rectangle([x, y, x + width - 1, y + height - 1], outline=_TRACE_OUTLINE)
    return canvas


def render_heatmap(debug: ImageTraceDebug) -> Image.Image:
    """Where the trace agrees and disagrees with the source ink.

    The most diagnostic of the four: missed ink means the threshold or cell
    size dropped detail, while overshoot means rectangles are spilling past
    the lettering: two very different fixes that look identical in the output
    alone.
    """
    covered = debug.coverage()
    ink = debug.mask
    out = np.zeros((*ink.shape, 3), dtype=np.uint8)
    out[...] = _BACKDROP
    out[covered & ink] = _INK_MATCHED
    out[ink & ~covered] = _INK_MISSED
    out[covered & ~ink] = _INK_OVERSHOOT
    return Image.fromarray(out, mode="RGB")


def render_contours(debug: ImageTraceDebug) -> Image.Image:
    """The silhouette boundary the threshold actually produced.

    Shows what was treated as ink *before* rectangles entered the picture, so
    a bad polarity/threshold choice is obvious on its own rather than being
    inferred from a strange-looking trace.
    """
    ink = debug.mask
    # A pixel is an edge when it is ink and any 4-neighbour is not. Padding by
    # one keeps the image border counting as "outside", so a silhouette that
    # runs to the edge still draws a boundary there.
    padded = np.pad(ink, 1, mode="constant", constant_values=False)
    interior = (padded[1:-1, 2:] & padded[1:-1, :-2]
                & padded[2:, 1:-1] & padded[:-2, 1:-1])
    edge = ink & ~interior
    out = np.zeros((*ink.shape, 3), dtype=np.uint8)
    out[...] = _BACKDROP
    out[ink] = (58, 62, 70)
    out[edge] = _LABEL_FG
    return Image.fromarray(out, mode="RGB")


def render_combined(debug: ImageTraceDebug) -> Image.Image:
    """All four views tiled in one image, each captioned.

    The default: comparing the panels against each other is what actually
    explains a result, and having them in one file survives being pasted into
    a message far better than four separate attachments.
    """
    panels = [
        ("Source", debug.image.convert("RGB")),
        ("Contours", render_contours(debug)),
        ("Trace", render_trace(debug)),
        ("Heatmap", render_heatmap(debug)),
    ]
    width, height = debug.image.size
    caption_h = 16
    gap = 6
    sheet = Image.new(
        "RGB",
        (width * 2 + gap * 3, (height + caption_h) * 2 + gap * 3),
        _BACKDROP)
    draw = ImageDraw.Draw(sheet)
    for index, (label, panel) in enumerate(panels):
        col, row = index % 2, index // 2
        x = gap + col * (width + gap)
        y = gap + row * (height + caption_h + gap)
        draw.text((x, y), label, fill=_LABEL_FG)
        sheet.paste(panel, (x, y + caption_h))
    return sheet


_RENDERERS = {
    "trace": render_trace,
    "heatmap": render_heatmap,
    "contours": render_contours,
    "combined": render_combined,
}


def render_debug(debug: ImageTraceDebug, mode: str = "combined") -> Image.Image:
    """Render one debug view. Unknown modes fall back to the combined sheet
    rather than raising: a diagnostic aid must never be the thing that breaks
    a generation the user actually wanted."""
    return _RENDERERS.get(mode, render_combined)(debug)


def write_debug_outputs(output_json_path, debug: ImageTraceDebug, *,
                         source_path=None, save_source: bool = False,
                         save_debug: bool = False, mode: str = "combined") -> list:
    """Write the opt-in companion files beside an Image-to-Text result.

    Named from the output's own stem so a source copy, a debug image and a
    diagnostics file are all obviously the same run: `SIGN.json` becomes
    `SIGN.source.png`, `SIGN.debug.png`, `SIGN.diagnostics.json`.

    Returns the paths actually written. Nothing is written unless asked for,
    and the source is *copied* through PIL rather than moved or re-encoded in
    place, so the user's original file is never touched.
    """
    from pathlib import Path

    output_json_path = Path(output_json_path)
    stem = output_json_path.with_suffix("")
    written = []

    if save_source:
        source_out = Path(f"{stem}.source.png")
        # Saved from the already-loaded image rather than shutil-copying the
        # original: this records the pixels the trace actually ran on
        # (post-downscale), which is what makes the debug views line up.
        debug.image.convert("RGB").save(source_out)
        written.append(source_out)

    if save_debug:
        debug_out = Path(f"{stem}.debug.png")
        render_debug(debug, mode).save(debug_out)
        written.append(debug_out)

        import json
        diag_out = Path(f"{stem}.diagnostics.json")
        payload = diagnostics(debug)
        payload["debug_view"] = mode
        if source_path is not None:
            payload["source_file"] = str(source_path)
        diag_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        written.append(diag_out)

    return written
