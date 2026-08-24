import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "tools"))
from build_icon import (  # noqa: E402
    ICO_SIZES,
    SIMPLIFIED_MAX_SIZE,
    clean_wordmark,
    render_braille_cells,
    render_simplified,
    write_ico,
)

ACCENT = (204, 106, 46)
FG = (232, 235, 240)


def test_render_braille_cells_returns_rgba_with_transparent_background():
    img = render_braille_cells(256, ACCENT, FG)
    assert img.mode == "RGBA"
    assert img.getpixel((0, 0))[3] == 0  # corner is transparent, not a filled background


def test_render_braille_cells_contains_both_colors():
    img = render_braille_cells(256, ACCENT, FG)
    pixels = {img.getpixel((x, y))[:3] for x in range(0, img.width, 3) for y in range(0, img.height, 3)}
    assert ACCENT in pixels
    assert FG in pixels


def test_small_icon_is_the_clear_two_dot_mark():
    img = render_simplified(16, ACCENT, FG)
    assert img.size == (16, 16)
    # Both functional colors must survive at title-bar size.
    pixels = list(img.get_flattened_data())
    assert any(r > 150 and 50 < g < 150 and b < 100 and a > 180 for r, g, b, a in pixels)
    assert any(r > 190 and g > 190 and b > 190 and a > 180 for r, g, b, a in pixels)


def test_write_ico_produces_a_valid_multi_size_icondir(tmp_path):
    images = {size: render_simplified(size, ACCENT, FG) if size <= SIMPLIFIED_MAX_SIZE
              else render_braille_cells(size, ACCENT, FG) for size in ICO_SIZES}
    out_path = tmp_path / "test.ico"
    write_ico(images, out_path)

    data = out_path.read_bytes()
    reserved, type_, count = struct.unpack_from("<HHH", data, 0)
    assert reserved == 0
    assert type_ == 1  # ICO, not CUR
    assert count == len(ICO_SIZES)

    # every directory entry's declared byte range must actually fit in the file
    for i in range(count):
        entry = data[6 + i * 16: 6 + (i + 1) * 16]
        _w, _h, _cc, _r, _planes, _bpp, size_bytes, offset = struct.unpack("<BBBBHHII", entry)
        assert offset + size_bytes <= len(data)
        # PNG magic bytes at the declared offset
        assert data[offset:offset + 8] == b"\x89PNG\r\n\x1a\n"


def test_write_ico_dimension_byte_is_zero_for_256(tmp_path):
    # ICO format quirk: dimension byte 0 conventionally means 256, since a
    # single byte can't represent 256 directly.
    images = {256: render_braille_cells(256, ACCENT, FG)}
    out_path = tmp_path / "big.ico"
    write_ico(images, out_path)
    data = out_path.read_bytes()
    w, h = data[6], data[7]
    assert (w, h) == (0, 0)


def test_clean_wordmark_removes_matte_and_preserves_brand_colors():
    from PIL import Image
    source = Image.new("RGB", (2, 2), (4, 5, 5))
    source.putpixel((0, 0), ACCENT)
    source.putpixel((0, 1), (148, 112, 74))
    cleaned = clean_wordmark(source)
    assert cleaned.getpixel((1, 0))[3] == 0
    assert cleaned.getpixel((0, 0)) == (*ACCENT, 255)
    assert cleaned.getpixel((0, 1)) == (148, 112, 74, 255)


@pytest.mark.skipif(
    not (Path(__file__).resolve().parent.parent.parent / "assets" / "icon.ico").exists(),
    reason="assets/icon.ico not built yet — run tools/build_icon.py",
)
def test_built_icon_asset_is_loadable_and_has_expected_sizes():
    from PIL import Image
    img = Image.open(Path(__file__).resolve().parent.parent.parent / "assets" / "icon.ico")
    assert img.info.get("sizes") == {(s, s) for s in ICO_SIZES}
