from pathlib import Path

import pytest

from forza_writer.variable_fonts import inspect_variable_font, variation_slug


NOTO_VF = Path(r"C:\Windows\Fonts\NotoSansJP-VF.ttf")


def test_variation_slug_is_stable_and_filesystem_safe():
    assert variation_slug({"wght": 400}) == "WGHT400"
    assert variation_slug({"wdth": 75, "wght": 650.5}) == "WDTH75-WGHT650P5"
    assert variation_slug({"slnt": -12}) == "SLNTM12"


@pytest.mark.skipif(not NOTO_VF.exists(), reason="Noto variable test font is not installed")
def test_inspect_noto_variable_font_finds_axes_and_named_instances():
    info = inspect_variable_font(NOTO_VF)
    assert info.is_variable
    weight = next(axis for axis in info.axes if axis.tag == "wght")
    assert weight.minimum < weight.maximum
    assert any(instance.name.casefold() == "regular" for instance in info.instances)
    assert info.defaults["wght"] == weight.default
