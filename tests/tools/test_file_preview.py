import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "tools"))
from file_preview import (  # noqa: E402
    kfps_vinyls_dir,
    render_composed_preview,
    render_file_preview,
    render_json_preview,
    render_modelbin_preview,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
from forza_writer.shapes import resource_to_shape_word, resource_to_typecode  # noqa: E402

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
    # A big normal square, then a smaller mask square centered on top of it:
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
    vertical extent: the same "much wider than tall" shape a single line
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
    # Wide, short content (a line of text) must fit to its own aspect ratio
    # rather than being rendered at a *square* internal resolution and then
    # letterboxed into a wide target canvas, which would leave the actual
    # content as a thin sliver near the canvas centre (~30% of the available
    # width) and make composed text tiny/illegible. Cropping to content
    # before fitting keeps the painted content spanning most of the
    # canvas's own width.
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


# -- Native Forza font letterforms (kfps_vinyls_dir + glyph compositing) ------

def _letter_shape(family="Upper_Letters_1", index=5, color=(255, 255, 255, 255)):
    return {
        "type": resource_to_typecode(family, index),
        "type_word": resource_to_shape_word(family, index),
        "data": [0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 0],
        "color": list(color),
        "mask": False,
    }


def _make_vinyls_dir(tmp_path, family="Upper_Letters_1", index=5, glyph_png=None):
    """A fake KFPS install layout: <root>/KFPS.exe next to
    tools/fabric-editor/Resources/Vinyls/<family>/<index>.png, matching
    kfps_vinyls_dir's expected sibling layout."""
    vinyls = tmp_path / "tools" / "fabric-editor" / "Resources" / "Vinyls" / family
    vinyls.mkdir(parents=True)
    if glyph_png is not None:
        glyph_png.save(vinyls / f"{index}.png")
    (tmp_path / "KFPS.exe").write_bytes(b"")
    return tmp_path / "KFPS.exe"


def _half_opaque_glyph(size=100):
    """Top half fully opaque white, bottom half fully transparent -- lets a
    test tell real alpha compositing apart from a naive solid-box fill."""
    img = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    for y in range(size // 2):
        for x in range(size):
            img.putpixel((x, y), (255, 255, 255, 255))
    return img


def test_kfps_vinyls_dir_resolves_relative_to_executable(tmp_path):
    exe = _make_vinyls_dir(tmp_path)
    resolved = kfps_vinyls_dir(str(exe))
    assert resolved == tmp_path / "tools" / "fabric-editor" / "Resources" / "Vinyls"


def test_kfps_vinyls_dir_none_when_unset():
    assert kfps_vinyls_dir("") is None


def test_kfps_vinyls_dir_none_when_folder_missing(tmp_path):
    missing_exe = tmp_path / "KFPS.exe"
    missing_exe.write_bytes(b"")
    assert kfps_vinyls_dir(str(missing_exe)) is None


def test_letterform_shape_falls_back_to_box_without_vinyls_dir():
    # No vinyls_dir passed at all -- must render exactly like it did before
    # letterform support existed (a plain filled box), never blank/crash.
    bg = "#101317"
    img = render_json_preview([_letter_shape()], size=(128, 128), bg=bg)
    bg_rgb = tuple(int(bg[i:i + 2], 16) for i in (1, 3, 5))
    assert img.getpixel((64, 64)) == (255, 255, 255)
    assert img.getpixel((2, 2)) == bg_rgb


def test_letterform_shape_falls_back_to_box_when_glyph_file_missing(tmp_path):
    exe = _make_vinyls_dir(tmp_path)  # no PNG written for this index
    vinyls = kfps_vinyls_dir(str(exe))
    bg = "#101317"
    img = render_json_preview([_letter_shape()], size=(128, 128), bg=bg, vinyls_dir=vinyls)
    bg_rgb = tuple(int(bg[i:i + 2], 16) for i in (1, 3, 5))
    assert img.getpixel((64, 64)) == (255, 255, 255)
    assert img.getpixel((2, 2)) == bg_rgb


def test_letterform_shape_composites_real_glyph_alpha(tmp_path):
    # A half-opaque synthetic glyph proves this is a real alpha composite,
    # not the fallback solid box: the bottom half of the shape's own
    # bounding box must stay background, which a plain box fill never would.
    exe = _make_vinyls_dir(tmp_path, glyph_png=_half_opaque_glyph())
    vinyls = kfps_vinyls_dir(str(exe))
    bg = "#101317"
    bg_rgb = tuple(int(bg[i:i + 2], 16) for i in (1, 3, 5))
    img = render_json_preview([_letter_shape()], size=(128, 128), bg=bg, vinyls_dir=vinyls)
    assert img.getpixel((64, 40)) == (255, 255, 255)   # top half: opaque -> painted
    assert img.getpixel((64, 90)) == bg_rgb            # bottom half: transparent -> untouched


def test_letterform_shape_tints_to_the_shapes_own_color(tmp_path):
    exe = _make_vinyls_dir(tmp_path, glyph_png=_half_opaque_glyph())
    vinyls = kfps_vinyls_dir(str(exe))
    img = render_json_preview([_letter_shape(color=(10, 200, 30, 255))], size=(128, 128),
                               bg="#101317", vinyls_dir=vinyls)
    assert img.getpixel((64, 40)) == (10, 200, 30)
