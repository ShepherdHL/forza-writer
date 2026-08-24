"""Read-only preview rendering for the GUI's "Preview a file" panel — the
approximation/viewer the user asked for once the interactive per-glyph
editor was removed in favor of KFPS's own (better) editor.

Two file kinds, two renderers:

- `.json` (primitive-composition shape lists, `forza_writer.export`'s
  `fh6_typecode_json_export_v1` format): `render_json_preview` composites
  shapes bottom-to-top exactly the way FH6's layer stack would — painting
  each shape's own color where it covers, but *erasing back to background*
  wherever a `mask: true` shape covers, since that's what a mask layer
  actually does (see forza_writer/rect_decompose.py's stencil mode). This
  makes the preview an actual visual approximation, not just a coverage
  diagnostic like the debug PNGs used while building the fitter.
- `.modelbin` (custom vector meshes): `render_modelbin_preview` reads the
  flat 2D triangle mesh back via `gen_modelbin.read_mesh_triangles` and
  rasterizes it as filled triangles. There's no per-vertex color worth
  reading for this purpose, so it's a single flat fill — good enough to
  confirm "does this look like the letter", which is the whole point.

Both follow tools/font_preview.py's established discipline: pure PIL logic,
no Tkinter, and never raise — a bad file gets a placeholder tile with a
message instead of crashing the caller.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))

DEFAULT_SIZE = (400, 400)
DEFAULT_BG = "#101317"
DEFAULT_FG = "#e8e8e6"
MARGIN_FRACTION = 0.08  # keep a small border so shapes don't touch the edge


def _placeholder(size: tuple[int, int], message: str, bg: str, fg: str) -> Image.Image:
    img = Image.new("RGB", size, bg)
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    w, h = size
    # Simple manual word-wrap — load_default() has no reliable wrapping and
    # error messages can be long (a raised exception's str()).
    words = message.split()
    lines, current = [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if draw.textbbox((0, 0), trial, font=font)[2] > w - 20 and current:
            lines.append(current)
            current = word
        else:
            current = trial
    if current:
        lines.append(current)
    line_h = draw.textbbox((0, 0), "Ay", font=font)[3] + 4
    total_h = line_h * len(lines)
    y = (h - total_h) / 2
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        draw.text(((w - (bbox[2] - bbox[0])) / 2, y), line, font=font, fill=fg)
        y += line_h
    return img


def _paint_shapes(shapes: list[dict], resolution: int, glyph_size: float, bg: str):
    """Shared rasterization loop for render_json_preview/render_composed_preview:
    paint each shape bottom-to-top, erasing back to background wherever a
    `mask: true` shape covers — the same "actual look" semantics both
    renderers need, just parameterized on `glyph_size` (the real-unit span
    the ±COORD_RANGE canvas represents) since composed text spans far more
    than a single glyph's own box."""
    import numpy as np

    from forza_writer.primitive_fit import render_candidate, shape_to_render_params
    from forza_writer.primitive_shapes import PRIMITIVE_CATALOG

    canvas = np.zeros((resolution, resolution, 3), dtype=np.uint8)
    bg_rgb = tuple(int(bg[i:i + 2], 16) for i in (1, 3, 5))
    canvas[:, :] = bg_rgb

    for shape in shapes:
        shape_id, cx, cy, sx, sy, rot, skew_x = shape_to_render_params(
            shape, resolution, glyph_size)
        if shape_id is None:
            continue
        primitive = PRIMITIVE_CATALOG[shape_id]
        covered = render_candidate(primitive, cx, cy, sx, sy, rot, resolution, skew_x)
        if shape.get("mask"):
            # A mask punches transparency through everything below it —
            # revert those pixels to background, not to the mask's own
            # (irrelevant) color.
            canvas[covered] = bg_rgb
        else:
            color = shape.get("color", [255, 255, 255, 255])[:3]
            canvas[covered] = color

    return canvas


def render_json_preview(shapes: list[dict], size: tuple[int, int] = DEFAULT_SIZE,
                         bg: str = DEFAULT_BG, fg: str = DEFAULT_FG) -> Image.Image:
    """Render a primitive-composition shape list as it would actually look —
    including stencil-mode mask shapes erasing back to background, not just
    coverage. Never raises."""
    try:
        resolution = min(size)
        canvas = _paint_shapes(shapes, resolution, glyph_size=300.0, bg=bg)
        img = Image.fromarray(canvas, "RGB")
        if (resolution, resolution) != size:
            img = img.resize(size, Image.NEAREST)
        return img
    except Exception as exc:
        return _placeholder(size, f"couldn't render JSON preview: {exc}", bg, fg)


def render_composed_preview(shapes: list[dict], size: tuple[int, int] = DEFAULT_SIZE,
                             bg: str = DEFAULT_BG, fg: str = DEFAULT_FG) -> Image.Image:
    """Render a `forza_writer.text_compose.compose_text` shape list.

    `render_json_preview` assumes shapes live within one glyph's own
    ±150-real-unit box (`glyph_size=300`, centred at 0,0) — true for a
    single generated glyph file, but composed text can span many glyph
    widths and isn't centred at the origin. This re-centres the shape
    list's own real-unit bounding box and picks a `glyph_size` that fits
    that whole span (plus a small margin) into the canvas, then reuses the
    same paint loop. Never raises.

    Composed text is almost always far wider than it is tall (a single
    line's height is one glyph's worth; its width is dozens) — rendering
    that onto a *square* raster the way a single glyph does, then fitting
    the square into a wide target `size`, wastes most of the target's
    width on empty letterbox padding above/below a thin sliver of actual
    text (confirmed against a real composed sentence: the text rendered a
    few pixels tall in a mostly-empty 640x200 canvas). Fixed by rendering
    at higher internal resolution, then cropping to the content's own
    tight bounding box *before* fitting into `size` — the fit then uses
    the canvas's full available width for what's actually there, instead
    of the content's own (mostly empty) square bounding box.
    """
    try:
        import numpy as np

        if not shapes:
            return Image.new("RGB", size, bg)

        xs = [s["data"][0] for s in shapes]
        ys = [s["data"][1] for s in shapes]
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)
        cx = (x_min + x_max) / 2.0
        cy = (y_min + y_max) / 2.0
        span = max(x_max - x_min, y_max - y_min) or 1.0
        glyph_size = span / (1.0 - 2 * MARGIN_FRACTION)

        centered = [{**s, "data": [s["data"][0] - cx, s["data"][1] - cy, *s["data"][2:]]}
                    for s in shapes]

        # A *square* resolution (matching rasterize_contours' own
        # convention, one uniform real-unit-per-pixel scale for both axes)
        # so nothing distorts. Oversampled well past `size` so the crop
        # below still has real detail to work with rather than upscaling
        # already-blocky pixels.
        resolution = min(1600, max(size) * 3)
        canvas = _paint_shapes(centered, resolution, glyph_size=glyph_size, bg=bg)
        img = Image.fromarray(canvas, "RGB")

        bg_rgb = tuple(int(bg[i:i + 2], 16) for i in (1, 3, 5))
        painted = np.any(canvas != bg_rgb, axis=2)
        ys_idx, xs_idx = np.nonzero(painted)
        if len(xs_idx) == 0:
            return img.resize(size, Image.NEAREST)

        pad = max(2, round(resolution * MARGIN_FRACTION * 0.5))
        x0 = max(0, int(xs_idx.min()) - pad)
        x1 = min(resolution, int(xs_idx.max()) + pad + 1)
        y0 = max(0, int(ys_idx.min()) - pad)
        y1 = min(resolution, int(ys_idx.max()) + pad + 1)
        cropped = img.crop((x0, y0, x1, y1))

        fit_scale = min(size[0] / cropped.width, size[1] / cropped.height)
        fitted_size = (max(1, round(cropped.width * fit_scale)), max(1, round(cropped.height * fit_scale)))
        fitted = cropped.resize(fitted_size, Image.NEAREST)

        out = Image.new("RGB", size, bg)
        offset = ((size[0] - fitted_size[0]) // 2, (size[1] - fitted_size[1]) // 2)
        out.paste(fitted, offset)
        return out
    except Exception as exc:
        return _placeholder(size, f"couldn't render composed preview: {exc}", bg, fg)


_MONOSPACE_CANDIDATES = (
    Path(r"C:\Windows\Fonts\consola.ttf"),  # Consolas — matches the Log panel's font
    Path(r"C:\Windows\Fonts\cour.ttf"),     # Courier New fallback
)


def render_ascii_grid_preview(
    rows: list[str],
    supported: set[str],
    remap: dict[str, str | None] | None = None,
    size: tuple[int, int] = DEFAULT_SIZE,
    bg: str = DEFAULT_BG,
    fg: str = DEFAULT_FG,
    warn: str = "#e0745a",
) -> Image.Image:
    """Layout preview for `ascii_grid.layout_ascii_grid` — NOT a rendering of
    the actual native vinyl letterforms (those are meshes this tool doesn't
    have local thumbnails for; `render_json_preview`'s shape rasterizer only
    understands the Primitives family, not letter shapes — see
    `primitive_fit.shape_to_render_params`). This exists purely to confirm
    grid alignment and character coverage before export: `fg` for a cell that
    will place a real glyph, `warn` for one that's still unsupported and will
    come out blank, and nothing drawn for a deliberately blank cell (a space,
    or remapped to `None`/space). Never raises.
    """
    try:
        remap = remap or {}
        rows = rows or [""]
        cols = max((len(r) for r in rows), default=0) or 1
        w, h = size
        margin = min(w, h) * MARGIN_FRACTION
        cell_px = min((w - 2 * margin) / cols, (h - 2 * margin) / len(rows))
        cell_px = max(cell_px, 1.0)
        font_path = next((p for p in _MONOSPACE_CANDIDATES if p.exists()), None)
        font = ImageFont.truetype(str(font_path), max(6, int(cell_px * 0.82))) if font_path \
            else ImageFont.load_default()

        grid_w, grid_h = cols * cell_px, len(rows) * cell_px
        origin_x, origin_y = (w - grid_w) / 2, (h - grid_h) / 2

        img = Image.new("RGB", size, bg)
        draw = ImageDraw.Draw(img)
        for row_index, row in enumerate(rows):
            for col_index, char in enumerate(row):
                effective = remap.get(char, char)
                if effective in (None, " "):
                    continue
                color = fg if effective in supported else warn
                cx = origin_x + col_index * cell_px + cell_px / 2
                cy = origin_y + row_index * cell_px + cell_px / 2
                draw.text((cx, cy), effective, font=font, fill=color, anchor="mm")
        return img
    except Exception as exc:
        return _placeholder(size, f"couldn't render ASCII grid preview: {exc}", bg, fg)


def render_forza_text_preview(
    lines: list[str],
    unsupported: set[str],
    size: tuple[int, int] = DEFAULT_SIZE,
    bg: str = DEFAULT_BG,
    fg: str = DEFAULT_FG,
    warn: str = "#e0745a",
) -> Image.Image:
    """Layout preview for `layout.layout_forza_text`. Same limit as
    `render_ascii_grid_preview` and for the same reason. No local mesh data
    exists for the native vinyl letterforms, so this is not that. This
    draws the typed text with a plain system font, split on the same line
    breaks the real layout uses. It confirms line count and character
    coverage before export. It does not confirm letterform shape or exact
    per-glyph spacing. A character in `unsupported` draws in `warn`. Every
    other character draws in `fg`. Never raises.
    """
    try:
        lines = lines or [""]
        w, h = size
        font_path = next((p for p in _MONOSPACE_CANDIDATES if p.exists()), None)
        line_px = max(6, int((h - 2 * h * MARGIN_FRACTION) / max(1, len(lines))))
        font = ImageFont.truetype(str(font_path), min(line_px, 48)) if font_path \
            else ImageFont.load_default()

        img = Image.new("RGB", size, bg)
        draw = ImageDraw.Draw(img)
        top = h * MARGIN_FRACTION
        for row_index, line in enumerate(lines):
            cy = top + row_index * line_px + line_px / 2
            cx = w / 2 - draw.textlength(line, font=font) / 2
            for char in line:
                color = warn if char in unsupported else fg
                draw.text((cx, cy), char, font=font, fill=color, anchor="lm")
                cx += draw.textlength(char, font=font)
        return img
    except Exception as exc:
        return _placeholder(size, f"couldn't render text preview: {exc}", bg, fg)


def render_modelbin_preview(path: Path, size: tuple[int, int] = DEFAULT_SIZE,
                             bg: str = DEFAULT_BG, fg: str = DEFAULT_FG) -> Image.Image:
    """Render a .modelbin's flat 2D triangle mesh as a filled silhouette.
    No per-vertex color is read (the attribute buffer isn't relevant to
    "does this look like the letter"), so this is a single flat fill.
    Never raises."""
    try:
        from gen_modelbin import read_mesh_triangles

        vertices, triangles = read_mesh_triangles(Path(path))
        if not vertices or not triangles:
            return _placeholder(size, "mesh has no vertices/triangles", bg, fg)

        xs = [v[0] for v in vertices]
        ys = [v[1] for v in vertices]
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)
        span = max(x_max - x_min, y_max - y_min) or 1.0
        w, h = size
        margin = min(w, h) * MARGIN_FRACTION
        scale = (min(w, h) - 2 * margin) / span
        cx, cy = (x_min + x_max) / 2.0, (y_min + y_max) / 2.0

        def to_px(pt):
            x, y = pt
            return (w / 2 + (x - cx) * scale, h / 2 - (y - cy) * scale)

        img = Image.new("RGB", size, bg)
        draw = ImageDraw.Draw(img)
        for a, b, c in triangles:
            draw.polygon([to_px(vertices[a]), to_px(vertices[b]), to_px(vertices[c])], fill=fg)
        return img
    except Exception as exc:
        return _placeholder(size, f"couldn't render modelbin preview: {exc}", bg, fg)


def render_file_preview(path: Path, size: tuple[int, int] = DEFAULT_SIZE,
                         bg: str = DEFAULT_BG, fg: str = DEFAULT_FG) -> Image.Image:
    """Dispatch on file extension. Never raises — unknown extensions and
    unreadable files both fall through to a placeholder tile."""
    path = Path(path)
    try:
        if path.suffix.lower() == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
            return render_json_preview(data.get("shapes", []), size, bg, fg)
        if path.suffix.lower() == ".modelbin":
            return render_modelbin_preview(path, size, bg, fg)
        return _placeholder(size, f"unsupported file type: {path.suffix}", bg, fg)
    except Exception as exc:
        return _placeholder(size, f"couldn't read file: {exc}", bg, fg)
