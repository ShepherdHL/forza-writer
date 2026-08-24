import pytest

from forza_writer.forza_colors import (
    describe_color, forza_hsb_to_rgb, hex_to_rgb, rgb_to_forza_hsb, rgb_to_hex, rgb_to_hsb, rgb_to_hsl,
)

# Cross-checked against this exact math via Node during the Composer color
# mockup this module was built from: pure R/G/B, the app's own accent
# (#e08a3f), a saturated blue-violet-ish arbitrary color, and the
# achromatic extremes.
SAMPLES = [
    (255, 0, 0), (0, 255, 0), (0, 0, 255),
    (224, 138, 63), (18, 52, 86), (255, 255, 255), (0, 0, 0), (128, 64, 200),
]


@pytest.mark.parametrize("r,g,b", SAMPLES)
def test_forza_hsb_round_trips_to_the_same_rgb(r, g, b):
    h, s, v = rgb_to_forza_hsb(r, g, b)
    back = forza_hsb_to_rgb(h, s, v)
    assert abs(back.r - r) <= 1
    assert abs(back.g - g) <= 1
    assert abs(back.b - b) <= 1


def test_forza_hsb_matches_known_pure_red():
    h, s, v = rgb_to_forza_hsb(255, 0, 0)
    assert h == pytest.approx(0.0)
    assert s == pytest.approx(1.0)
    assert v == pytest.approx(1.0)


def test_forza_hsb_matches_known_pure_blue():
    h, s, v = rgb_to_forza_hsb(0, 0, 255)
    assert h == pytest.approx(2 / 3)
    assert s == pytest.approx(1.0)
    assert v == pytest.approx(1.0)


def test_rgb_to_hex_and_hex_to_rgb_round_trip():
    rgb = hex_to_rgb("#e08a3f")
    assert (rgb.r, rgb.g, rgb.b) == (224, 138, 63)
    assert rgb_to_hex(rgb.r, rgb.g, rgb.b) == "#e08a3f"


def test_hex_to_rgb_accepts_shorthand_and_missing_hash():
    assert hex_to_rgb("f00") == hex_to_rgb("#ff0000")
    assert hex_to_rgb("ff0000") == hex_to_rgb("#ff0000")


def test_hex_to_rgb_rejects_malformed_input():
    assert hex_to_rgb("not a color") is None
    assert hex_to_rgb("#12345") is None


def test_describe_color_bundles_every_format_consistently():
    formats = describe_color(224, 138, 63)
    assert formats.hex == "#e08a3f"
    assert (formats.rgb.r, formats.rgb.g, formats.rgb.b) == (224, 138, 63)
    assert (formats.hsl_h, formats.hsl_s, formats.hsl_l) == rgb_to_hsl(224, 138, 63)
    assert (formats.hsb_h, formats.hsb_s, formats.hsb_b) == rgb_to_hsb(224, 138, 63)
    assert (formats.forza_h, formats.forza_s, formats.forza_b) == rgb_to_forza_hsb(224, 138, 63)


def test_rgb_to_hex_clamps_out_of_range_channels():
    assert rgb_to_hex(300, -10, 128) == "#ff0080"
