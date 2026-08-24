import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "tools"))
from file_preview import (  # noqa: E402
    render_composed_preview,
    render_file_preview,
    render_json_preview,
    render_modelbin_preview,
)

AMARILLO_FONT = Path.home() / "Desktop" / "amarillo-usaf" / "amarurgt.ttf"
REFERENCE_MODELBIN = Path(__file__).resolve().parent.parent.parent / "user-assets" / "S_01.modelbin"
requires_assets = pytest.mark.skipif(
    not (AMARILLO_FONT.exists() and REFERENCE_MODELBIN.exists()),
    reason="test font or reference modelbin not present on this machine")


def _square_shape(mask=False):
    return {
        "type": 1048677, "type_word": 101,
        "data": [0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 1 if mask else 0],
        "color": [0, 0, 0, 255] if mask else [255, 255, 255, 255],
        "mask": mask,
    }


def test_render_json_preview_returns_correct_size():
    img = render_json_preview([_square_shape()], size=(200, 200))
    assert img.size == (200, 200)
    assert img.mode == "RGB"


def test_render_json_preview_empty_list_is_just_background():
    bg = "#111111"
    img = render_json_preview([], size=(64, 64), bg=bg)
    bg_rgb = tuple(int(bg[i:i + 2], 16) for i in (1, 3, 5))
    assert img.getpixel((32, 32)) == bg_rgb


def test_mask_shape_erases_back_to_background():
    # A big normal square, then a smaller mask square centered on top of it —
    # the masked region must read as background, not the mask's own color.
    bg = "#111111"
    normal = _square_shape(mask=False)
    # shape_to_render_params converts this fh6-unit scale via
    # scale_fraction = fh6_scale * PIXEL_ART_SQUARE_SIZE / glyph_size
    # (~128.5/300) -- 5.0 here comfortably covers the whole canvas incl. corners.
    normal["data"] = [0.0, 0.0, 5.0, 5.0, 0.0, 0.0, 0]
    cutout = _square_shape(mask=True)
    cutout["data"] = [0.0, 0.0, 0.3, 0.3, 0.0, 0.0, 1]  # small, centered

    img = render_json_preview([normal, cutout], size=(128, 128), bg=bg)
    bg_rgb = tuple(int(bg[i:i + 2], 16) for i in (1, 3, 5))
    center = img.getpixel((64, 64))
    corner = img.getpixel((5, 5))
    assert center == bg_rgb, "masked center should read as background, not fill color"
    assert corner == (255, 255, 255), "unmasked area should still be the normal shape's color"


def test_render_json_preview_never_raises_on_garbage_shape():
    img = render_json_preview([{"not": "a valid shape"}], size=(100, 100))
    assert img.size == (100, 100)


@requires_assets
def test_render_modelbin_preview_returns_correct_size(tmp_path):
    from gen_modelbin import generate_glyph

    out_path = tmp_path / "A.modelbin"
    generate_glyph("A", AMARILLO_FONT, REFERENCE_MODELBIN, out_path, curve_segments=8)
    img = render_modelbin_preview(out_path, size=(300, 300))
    assert img.size == (300, 300)
    assert img.mode == "RGB"


def test_render_modelbin_preview_never_raises_on_corrupt_file(tmp_path):
    bad = tmp_path / "bad.modelbin"
    bad.write_bytes(b"not a real modelbin")
    img = render_modelbin_preview(bad, size=(150, 150))
    assert img.size == (150, 150)


def test_render_modelbin_preview_never_raises_on_missing_file(tmp_path):
    img = render_modelbin_preview(tmp_path / "missing.modelbin", size=(80, 80))
    assert img.size == (80, 80)


def test_render_file_preview_dispatches_on_extension_json(tmp_path):
    import json as jsonlib

    path = tmp_path / "glyph.json"
    path.write_text(jsonlib.dumps({"shapes": [_square_shape()]}), encoding="utf-8")
    img = render_file_preview(path, size=(64, 64))
    assert img.size == (64, 64)


def test_render_file_preview_unsupported_extension_shows_placeholder(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("hello", encoding="utf-8")
    img = render_file_preview(path, size=(64, 64))
    assert img.size == (64, 64)


def test_render_file_preview_never_raises_on_missing_file(tmp_path):
    img = render_file_preview(tmp_path / "missing.json", size=(64, 64))
    assert img.size == (64, 64)


# --- render_composed_preview ------------------------------------------------

def _wide_row_of_squares(n=20, spacing=40.0, y_height=8.0):
    """A row of small squares spread far apart horizontally with a tiny
    vertical extent — the same "much wider than tall" shape a single line
    of composed text has (one glyph's worth of height, many glyphs' worth
    of width)."""
    return [
        {"type": 1048677, "type_word": 101, "data": [i * spacing, 0.0, 0.1, y_height / 300.0, 0.0, 0.0, 0],
         "color": [255, 255, 255, 255], "mask": False}
        for i in range(n)
    ]


def test_render_composed_preview_returns_correct_size():
    img = render_composed_preview(_wide_row_of_squares(), size=(300, 100))
    assert img.size == (300, 100)
    assert img.mode == "RGB"


def test_render_composed_preview_empty_list_is_just_background():
    bg = "#111111"
    img = render_composed_preview([], size=(64, 64), bg=bg)
    bg_rgb = tuple(int(bg[i:i + 2], 16) for i in (1, 3, 5))
    assert img.getpixel((32, 32)) == bg_rgb


def test_render_composed_preview_uses_most_of_the_canvas_width():
    # Regression test for the exact bug found composing a real sentence in
    # the GUI: wide, short content (a line of text) used to render at a
    # *square* internal resolution then get letterboxed into a wide target
    # canvas — the actual content occupied only a thin sliver near the
    # canvas centre (~30% of the available width), making composed text
    # tiny/illegible. Fixed by cropping to content before fitting, so the
    # painted content should now span most of the canvas's own width.
    import numpy as np

    size = (640, 200)
    bg = "#040405"
    img = render_composed_preview(_wide_row_of_squares(n=25, spacing=50.0), size=size, bg=bg)
    arr = np.array(img)
    bg_rgb = tuple(int(bg[i:i + 2], 16) for i in (1, 3, 5))
    painted = np.any(arr != bg_rgb, axis=2)
    xs = np.nonzero(painted)[1]
    assert len(xs) > 0
    painted_width = xs.max() - xs.min()
    assert painted_width > size[0] * 0.7


def test_render_composed_preview_mask_erases_to_background():
    bg = "#050607"
    bg_rgb = tuple(int(bg[i:i + 2], 16) for i in (1, 3, 5))
    shapes = [
        {"type": 1048677, "type_word": 101, "data": [0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 0],
         "color": [255, 255, 255, 255], "mask": False},
        {"type": 1048677, "type_word": 101, "data": [0.0, 0.0, 0.3, 0.3, 0.0, 0.0, 1],
         "color": [0, 0, 0, 255], "mask": True},
    ]
    img = render_composed_preview(shapes, size=(200, 200), bg=bg)
    # centre pixel should be punched back to background by the mask
    assert img.getpixel((100, 100)) == bg_rgb
