"""
Forza vinyl editor color conversions.

RGB/HSB/HSL/hex conversions match Bang's Forza Color Converter v1.3 (fcc.js):
https://dxbang.github.io/forza-colors/

Ported near-verbatim from `forza-painter-fh6-1.9.5/src/forza_colors.py`
(this project's own prior work — see THIRD_PARTY_NOTICES.md, same provenance
as the §2 entry there) with one addition: `forza_hsb_to_rgb`, the inverse of
`rgb_to_forza_hsb`, needed to turn the GTPlanet Colour Creation Database's
recorded H,S,B recipes (see forza_writer/manufacturer_colors.py) back into a
displayable RGB swatch.
"""

from __future__ import annotations

import colorsys
from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class RgbColor:
    r: int
    g: int
    b: int

    def clamped(self) -> "RgbColor":
        return RgbColor(
            max(0, min(255, int(self.r))),
            max(0, min(255, int(self.g))),
            max(0, min(255, int(self.b))),
        )


@dataclass(frozen=True)
class ColorFormats:
    hex: str
    rgb: RgbColor
    hsl_h: float
    hsl_s: float
    hsl_l: float
    hsb_h: float
    hsb_s: float
    hsb_b: float
    forza_h: float
    forza_s: float
    forza_b: float


def rgb_to_hex(r: int, g: int, b: int) -> str:
    rgb = RgbColor(r, g, b).clamped()
    return f"#{rgb.r:02x}{rgb.g:02x}{rgb.b:02x}"


def hex_to_rgb(hex_value: str) -> RgbColor | None:
    text = (hex_value or "").strip().lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if len(text) != 6:
        return None
    try:
        return RgbColor(int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
    except ValueError:
        return None


def rgb_to_hsl(r: int, g: int, b: int) -> Tuple[float, float, float]:
    r, g, b = (r / 255.0, g / 255.0, b / 255.0)
    light = max(r, g, b)
    sat = light - min(r, g, b)
    if sat:
        if light == r:
            hue = (g - b) / sat
        elif light == g:
            hue = 2 + (b - r) / sat
        else:
            hue = 4 + (r - g) / sat
    else:
        hue = 0.0
    h = 60 * hue
    if h < 0:
        h += 360
    if sat:
        s = 100 * (sat / (2 * light - sat) if light <= 0.5 else sat / (2 - (2 * light - sat)))
    else:
        s = 0.0
    l = (100 * (2 * light - sat)) / 2
    return h, s, l


def rgb_to_hsb(r: int, g: int, b: int) -> Tuple[float, float, float]:
    r, g, b = (r / 255.0, g / 255.0, b / 255.0)
    value = max(r, g, b)
    delta = value - min(r, g, b)
    if delta == 0:
        hue = 0.0
    elif value == r:
        hue = (g - b) / delta
    elif value == g:
        hue = 2 + (b - r) / delta
    else:
        hue = 4 + (r - g) / delta
    h = 60 * (hue + 6 if hue < 0 else hue)
    s = (delta / value) * 100 if value else 0.0
    return h, s, value * 100


def rgb_to_forza_hsb(r: int, g: int, b: int) -> Tuple[float, float, float]:
    """Forza editor H/S/B (hue 0-1, saturation and brightness 0-1)."""
    r, g, b = (r / 255.0, g / 255.0, b / 255.0)
    value = max(r, g, b)
    delta = value - min(r, g, b)
    if delta == 0:
        hue = 0.0
    elif value == r:
        hue = (g - b) / delta
    elif value == g:
        hue = 2 + (b - r) / delta
    else:
        hue = 4 + (r - g) / delta
    h = (60 * (hue + 6 if hue < 0 else hue)) / 360.0
    s = (delta / value) if value else 0.0
    return h, s, value


def forza_hsb_to_rgb(h: float, s: float, b: float) -> RgbColor:
    """Inverse of `rgb_to_forza_hsb`: Forza's H,S,B (each 0-1) back to RGB.
    Forza's H,S,B is already plain normalized HSV (see `rgb_to_forza_hsb`'s
    body — it's `rgb_to_hsb` with h/360, s/100, and value left as a 0-1
    fraction), so this is exactly `colorsys.hsv_to_rgb`."""
    r, g, bl = colorsys.hsv_to_rgb(h, s, b)
    return RgbColor(round(r * 255), round(g * 255), round(bl * 255)).clamped()


def describe_color(r: int, g: int, b: int) -> ColorFormats:
    rgb = RgbColor(r, g, b).clamped()
    hsl_h, hsl_s, hsl_l = rgb_to_hsl(rgb.r, rgb.g, rgb.b)
    hsb_h, hsb_s, hsb_b = rgb_to_hsb(rgb.r, rgb.g, rgb.b)
    forza_h, forza_s, forza_b = rgb_to_forza_hsb(rgb.r, rgb.g, rgb.b)
    return ColorFormats(
        hex=rgb_to_hex(rgb.r, rgb.g, rgb.b),
        rgb=rgb,
        hsl_h=hsl_h,
        hsl_s=hsl_s,
        hsl_l=hsl_l,
        hsb_h=hsb_h,
        hsb_s=hsb_s,
        hsb_b=hsb_b,
        forza_h=forza_h,
        forza_s=forza_s,
        forza_b=forza_b,
    )


def sb_square_array(hue: float, size: int):
    """RGB image array (uint8, shape `(size, size, 3)`), Saturation
    left->right (0..1) by Brightness top->bottom (1..0), at a fixed Hue --
    the pixel data behind a standard HSB picker's saturation/brightness
    square. Vectorized `colorsys.hsv_to_rgb` (hue is constant across the
    square, so only the sector selection happens once; S/V vary per pixel).
    Pulled out of `tools/gen_modelbin_gui/tabs/color_picker.py::
    ColorPickerMixin`, which now delegates here, so any other picker UI
    (e.g. the Layer Effects tab's per-layer color picker) can render the
    identical square without re-deriving this math or importing a Tk mixin
    for a pure numpy computation."""
    import numpy as np

    s = np.linspace(0.0, 1.0, size)
    v = np.linspace(1.0, 0.0, size)
    sat, val = np.meshgrid(s, v)
    i = int(hue * 6.0) % 6
    f = hue * 6.0 - int(hue * 6.0)
    p = val * (1.0 - sat)
    q = val * (1.0 - sat * f)
    t = val * (1.0 - sat * (1.0 - f))
    r, g, b = [(val, t, p), (q, val, p), (p, val, t),
               (p, q, val), (t, p, val), (val, p, q)][i]
    return (np.stack([r, g, b], axis=-1) * 255).astype(np.uint8)


def hue_strip_array(length: int, width: int):
    """RGB image array (uint8, shape `(length, width, 3)`), Hue top->bottom
    (0..1) at full Saturation/Brightness -- the pixel data behind a
    standard picker's hue strip. See `sb_square_array`'s docstring for why
    this lives here rather than in the Tk mixin that first defined it."""
    import numpy as np

    column = np.array([colorsys.hsv_to_rgb(h / (length - 1), 1.0, 1.0) for h in range(length)])
    column = (column * 255).astype(np.uint8)
    return np.tile(column[:, np.newaxis, :], (1, width, 1))
