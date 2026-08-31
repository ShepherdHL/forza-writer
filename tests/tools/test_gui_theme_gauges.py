import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "tools"))
from gui_theme import gauges  # noqa: E402
from gui_theme.palettes.charcoal import PALETTE as CHARCOAL_PALETTE  # noqa: E402
from gui_theme.palettes.eurocorp import PALETTE as EUROCORP_PALETTE  # noqa: E402
from gui_theme.palettes.slate import PALETTE as SLATE_PALETTE  # noqa: E402

ALL_PALETTES = (CHARCOAL_PALETTE, EUROCORP_PALETTE, SLATE_PALETTE)


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


# --- render_ring_gauge ----------------------------------------------------

def test_render_ring_gauge_matches_the_requested_size():
    for p in ALL_PALETTES:
        assert gauges.render_ring_gauge(0.5, 96, p).size == (96, 96)


def test_render_ring_gauge_zero_value_draws_no_success_arc():
    p = EUROCORP_PALETTE
    pixels = list(gauges.render_ring_gauge(0.0, 96, p).convert("RGB").get_flattened_data())
    assert _hex_to_rgb(p["success"]) not in pixels


def test_render_ring_gauge_uses_the_given_palettes_success_color_when_full():
    for p in ALL_PALETTES:
        pixels = list(gauges.render_ring_gauge(1.0, 96, p).convert("RGB").get_flattened_data())
        assert _hex_to_rgb(p["success"]) in pixels


def test_render_ring_gauge_never_draws_a_danger_color():
    # No invented numeric threshold for percentage metrics -- true at
    # every value along the range, not just the extremes.
    p = EUROCORP_PALETTE
    danger_rgb = _hex_to_rgb(p["danger"])
    for value in (0.0, 0.2, 0.5, 0.8, 1.0):
        pixels = list(gauges.render_ring_gauge(value, 96, p).convert("RGB").get_flattened_data())
        assert danger_rgb not in pixels


def test_render_ring_gauge_clamps_out_of_range_values():
    p = EUROCORP_PALETTE
    below = gauges.render_ring_gauge(-0.5, 96, p).convert("RGB")
    above = gauges.render_ring_gauge(1.5, 96, p).convert("RGB")
    zero = gauges.render_ring_gauge(0.0, 96, p).convert("RGB")
    full = gauges.render_ring_gauge(1.0, 96, p).convert("RGB")
    assert list(below.get_flattened_data()) == list(zero.get_flattened_data())
    assert list(above.get_flattened_data()) == list(full.get_flattened_data())


# --- render_count_pill ------------------------------------------------------

def test_render_count_pill_matches_the_requested_size():
    for p in ALL_PALETTES:
        assert gauges.render_count_pill(2, 2, (140, 90), p).size == (140, 90)


def test_render_count_pill_uses_the_given_palettes_colors():
    for p in ALL_PALETTES:
        pixels = list(gauges.render_count_pill(2, 2, (140, 90), p).convert("RGB").get_flattened_data())
        assert _hex_to_rgb(p["success"]) in pixels
        assert _hex_to_rgb(p["secondary_accent"]) in pixels


def test_render_count_pill_no_danger_flag_when_generated_meets_expected():
    p = EUROCORP_PALETTE
    pixels = list(gauges.render_count_pill(2, 2, (140, 90), p).convert("RGB").get_flattened_data())
    assert _hex_to_rgb(p["danger"]) not in pixels


def test_render_count_pill_draws_a_danger_flag_on_shortfall():
    p = EUROCORP_PALETTE
    pixels = list(gauges.render_count_pill(1, 2, (140, 90), p).convert("RGB").get_flattened_data())
    assert _hex_to_rgb(p["danger"]) in pixels


def test_render_count_pill_no_danger_flag_when_generated_exceeds_expected():
    # Only a *shortfall* (generated < expected) is a regression -- more
    # generated than expected is never flagged.
    p = EUROCORP_PALETTE
    pixels = list(gauges.render_count_pill(3, 2, (140, 90), p).convert("RGB").get_flattened_data())
    assert _hex_to_rgb(p["danger"]) not in pixels
