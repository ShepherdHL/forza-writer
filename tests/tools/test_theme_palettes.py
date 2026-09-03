"""theme_palettes: the shared, UI-independent palette/design-token registry.

Retargeted from the old tests/tools/test_gui_theme.py (the Tkinter app's own
theming module, since removed) onto theme_palettes directly -- this is pure
data plus the small active-selection accessor the web app reads via
theme_palettes.palette(), with no Tk dependency of its own.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "tools"))
import gui_settings  # noqa: E402
import theme_palettes  # noqa: E402
from theme_palettes import (  # noqa: E402
    DISPLAY_FONT_FAMILY,
    PALETTE,
    PALETTES,
    SOLID_SELECTED_ROW,
    palette,
    set_palette,
)

EXPECTED_KEYS = {
    "bg", "fg", "muted_fg", "entry_bg", "entry_fg", "select_bg", "select_fg",
    "button_bg", "button_active_bg", "border", "listbox_bg", "listbox_fg",
    "log_bg", "log_fg", "canvas_bg", "disabled_fg", "accent", "accent_active",
    "accent_glow", "secondary_accent", "success", "danger", "warn", "hint",
    "info", "panel_alt", "frame_light", "frame_dark", "sash",
}

# This pass's deliberately-chosen "Eurocorp II" values (Syndicate x Vercel
# identity redesign) -- pinned so a future tweak to one token doesn't
# silently drift the rest of the system out of the tonal relationships this
# pass was built around (near-black bg, workspace one tier lifted, accent
# reserved for active/selected state).
CHOSEN_VALUES = {
    "bg": "#1e1f22",
    "fg": "#f2f3f5",
    "panel_alt": "#2b2d31",
    "accent": "#e08a3f",
    "accent_active": "#a8611f",
    "accent_glow": "#f6b877",
    "border": "#41434a",
    "muted_fg": "#b5bac1",
    "hint": "#b5bac1",
    "warn": "#c99a52",
    "danger": "#c9645a",
    "success": "#72a08c",
    "secondary_accent": "#5c7a94",
}


def teardown_function(_fn):
    set_palette("charcoal")  # restore the default so later tests see charcoal


def test_palette_has_all_expected_keys():
    assert set(PALETTE.keys()) == EXPECTED_KEYS


def test_palette_values_are_valid_hex_colors():
    for key, value in PALETTE.items():
        assert value.startswith("#"), f"{key} = {value!r} isn't a hex color"
        assert len(value) == 7, f"{key} = {value!r} isn't #RRGGBB"


def test_palette_helper_returns_the_palette():
    assert palette() is PALETTE


def test_background_is_soft_charcoal_not_near_black():
    assert PALETTE["bg"] != "#000000"
    r, g, b = (int(PALETTE["bg"][i:i + 2], 16) for i in (1, 3, 5))
    assert min(r, g, b) >= 28


def test_all_palettes_have_the_same_valid_color_roles():
    for values in PALETTES.values():
        assert set(values) == EXPECTED_KEYS
        assert all(value.startswith("#") and len(value) == 7 for value in values.values())


def test_chosen_palette_values_match_this_passs_design_choices():
    for key, value in CHOSEN_VALUES.items():
        assert PALETTE[key] == value


def test_workspace_surface_is_lifted_above_the_base_background():
    # panel_alt (the default workspace surface) must read as a step above
    # bg (root/chrome) -- the depth cue the whole elevation model depends
    # on, since neither Tk nor this app's own CSS reset draws real shadows.
    bg = tuple(int(PALETTE["bg"][i:i + 2], 16) for i in (1, 3, 5))
    surface = tuple(int(PALETTE["panel_alt"][i:i + 2], 16) for i in (1, 3, 5))
    assert sum(surface) > sum(bg)


def test_accent_is_reserved_and_distinct_from_every_other_role():
    other_roles = {"warn", "danger", "success", "secondary_accent", "hint", "muted_fg"}
    assert PALETTE["accent"] not in {PALETTE[role] for role in other_roles}


def test_set_palette_switches_palette_and_rejects_unknown_values_safely():
    set_palette("slate")
    assert PALETTE == PALETTES["slate"]
    assert theme_palettes.CURRENT_PALETTE == "slate"
    set_palette("unknown")
    assert PALETTE == PALETTES["charcoal"]


# --- Eurocorp ---------------------------------------------------------


def test_eurocorp_is_registered_and_matches_the_shared_contract():
    assert "eurocorp" in PALETTES
    assert set(PALETTES["eurocorp"]) == EXPECTED_KEYS


def test_eurocorp_select_fg_is_dark_on_its_solid_accent_fill():
    # Charcoal/Slate's select_fg is cream because accent there is only ever
    # a thin highlight edge. Eurocorp's accent is a broad solid fill
    # (SOLID_SELECTED_ROW), so select_fg must stay dark -- reusing the
    # cream value here would silently regress into low-contrast text on a
    # solid orange row, exactly what this test guards against.
    eurocorp = PALETTES["eurocorp"]
    fg_sum = sum(int(eurocorp["select_fg"][i:i + 2], 16) for i in (1, 3, 5))
    assert fg_sum < 200  # near-black, not Charcoal/Slate's cream (~700)


def test_eurocorp_opts_into_solid_selected_row_and_the_others_dont():
    assert SOLID_SELECTED_ROW["eurocorp"] is True
    assert SOLID_SELECTED_ROW["charcoal"] is False
    assert SOLID_SELECTED_ROW["slate"] is False


def test_set_palette_eurocorp_round_trips_and_resets_cleanly():
    set_palette("eurocorp")
    assert PALETTE == PALETTES["eurocorp"]
    assert theme_palettes.CURRENT_PALETTE == "eurocorp"
    set_palette("charcoal")
    assert PALETTE == PALETTES["charcoal"]


def test_display_font_family_registry_is_eurocorp_only():
    # Charcoal/Slate deliberately have no preferred display font -- only
    # Eurocorp's DIN Pro homage opts in. Not part of EXPECTED_KEYS, so this
    # is its own explicit assertion rather than folded into the token-
    # contract test.
    assert DISPLAY_FONT_FAMILY["eurocorp"] == "DINPro-Medium"
    assert DISPLAY_FONT_FAMILY["charcoal"] is None
    assert DISPLAY_FONT_FAMILY["slate"] is None


def test_gui_settings_valid_palettes_matches_the_registry():
    # gui_settings.py deliberately doesn't import theme_palettes (see its
    # own VALID_PALETTES comment), so the two name lists can silently drift
    # -- this is the test that keeps them honest.
    assert gui_settings.VALID_PALETTES == set(PALETTES)
