"""Vinyl-shape tile rendering for the Generator tab's shape picker."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import gui_theme  # noqa: E402
import vinyl_tiles  # noqa: E402
from forza_writer.primitive_shapes import PRIMITIVE_CATALOG  # noqa: E402

PALETTE = gui_theme.PALETTES["charcoal"]
SQUARE = PRIMITIVE_CATALOG["square"]


def _colours(image) -> set[tuple[int, int, int]]:
    return {tuple(c) for c in np.asarray(image.convert("RGB")).reshape(-1, 3)}


def _hex(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


# --- basics --------------------------------------------------------------

@pytest.mark.parametrize("state", vinyl_tiles.STATES)
@pytest.mark.parametrize("shape_id", sorted(PRIMITIVE_CATALOG))
def test_every_shape_renders_in_every_state(shape_id, state):
    tile = vinyl_tiles.render_tile(PRIMITIVE_CATALOG[shape_id], state, PALETTE)
    assert tile.size == (vinyl_tiles.TILE_W, vinyl_tiles.TILE_H)
    assert tile.mode == "RGB"


def test_unknown_state_is_rejected_rather_than_rendered_wrong():
    with pytest.raises(ValueError):
        vinyl_tiles.render_tile(SQUARE, "sideways", PALETTE)


def test_states_cover_exactly_the_valid_policy_combinations():
    # "preferred" implies allowed; the policy rejects preferring a disabled
    # shape, so there is deliberately no fourth state.
    assert set(vinyl_tiles.STATES) == {"off", "on", "preferred"}


# --- the three states have to be visually distinct -----------------------

def test_each_state_renders_differently():
    rendered = [vinyl_tiles.render_tile(SQUARE, state, PALETTE).tobytes()
                for state in vinyl_tiles.STATES]
    assert len(set(rendered)) == 3, "a user must be able to tell the three states apart"


def test_preferred_tiles_use_the_accent_colour():
    accent = _hex(PALETTE["accent"])
    assert accent in _colours(vinyl_tiles.render_tile(SQUARE, "preferred", PALETTE))
    assert accent not in _colours(vinyl_tiles.render_tile(SQUARE, "on", PALETTE))


def test_disabled_tiles_still_show_their_shape():
    # Greyed, not blanked: you have to see what you switched off to switch it
    # back on.
    disabled = _colours(vinyl_tiles.render_tile(SQUARE, "off", PALETTE))
    assert _hex(PALETTE["disabled_fg"]) in disabled


def test_allowed_tiles_are_brighter_than_disabled_ones():
    def mean_luma(state):
        pixels = np.asarray(vinyl_tiles.render_tile(SQUARE, state, PALETTE).convert("L"))
        return pixels.mean()
    assert mean_luma("on") > mean_luma("off")


# --- the silhouettes are the real shapes, not separate artwork -----------

def test_tiles_render_the_catalogs_own_mask():
    # A tile showing the wrong picture would mean the *fitter* is using the
    # wrong shape, so this must come from the catalog rather than an icon set.
    circle = vinyl_tiles.render_tile(PRIMITIVE_CATALOG["circle"], "on", PALETTE)
    square = vinyl_tiles.render_tile(PRIMITIVE_CATALOG["square"], "on", PALETTE)
    assert circle.tobytes() != square.tobytes()


def test_a_solid_shape_covers_more_pixels_than_its_border_variant():
    def ink(shape_id):
        tile = np.asarray(
            vinyl_tiles.render_tile(PRIMITIVE_CATALOG[shape_id], "on", PALETTE).convert("L"))
        return int((tile > 200).sum())
    assert ink("circle") > ink("circle_border")
    assert ink("square") > ink("square_border")


# --- badge hit-testing ---------------------------------------------------

def test_badge_hit_matches_where_the_badge_is_drawn():
    assert vinyl_tiles.badge_hit(vinyl_tiles.TILE_W - vinyl_tiles.BADGE_INSET,
                                 vinyl_tiles.BADGE_INSET)


def test_tile_body_is_not_a_badge_hit():
    assert not vinyl_tiles.badge_hit(vinyl_tiles.TILE_W / 2, vinyl_tiles.TILE_H / 2)
    assert not vinyl_tiles.badge_hit(4, 4)
    assert not vinyl_tiles.badge_hit(vinyl_tiles.TILE_W - 4, vinyl_tiles.TILE_H - 4)


def test_badge_hit_area_stays_inside_the_tile():
    cx, cy = vinyl_tiles.TILE_W - vinyl_tiles.BADGE_INSET, vinyl_tiles.BADGE_INSET
    assert cx + vinyl_tiles.BADGE_R < vinyl_tiles.TILE_W
    assert cy - vinyl_tiles.BADGE_R >= 0


# --- theming -------------------------------------------------------------

@pytest.mark.parametrize("palette_name", sorted(gui_theme.PALETTES))
def test_tiles_render_under_every_palette(palette_name):
    tile = vinyl_tiles.render_tile(SQUARE, "on", gui_theme.PALETTES[palette_name])
    assert tile.size == (vinyl_tiles.TILE_W, vinyl_tiles.TILE_H)


def test_switching_palette_changes_the_rendered_tile():
    # Tiles bake palette colours into a bitmap, which is why the GUI has to
    # repaint them on a theme change rather than restyling a widget.
    charcoal = vinyl_tiles.render_tile(SQUARE, "on", gui_theme.PALETTES["charcoal"])
    slate = vinyl_tiles.render_tile(SQUARE, "on", gui_theme.PALETTES["slate"])
    assert charcoal.tobytes() != slate.tobytes()


# --- captions ------------------------------------------------------------

def test_long_names_are_truncated_to_fit_the_tile():
    from PIL import ImageDraw, Image
    draw = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    font = vinyl_tiles._font(11)
    fitted = vinyl_tiles._fit_caption(
        draw, "Fat Five Pointed Star", font, vinyl_tiles.TILE_W - 10)
    assert draw.textlength(fitted, font=font) <= vinyl_tiles.TILE_W - 10


def test_short_names_are_left_alone():
    from PIL import ImageDraw, Image
    draw = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    font = vinyl_tiles._font(11)
    assert vinyl_tiles._fit_caption(draw, "Circle", font, vinyl_tiles.TILE_W - 10) == "Circle"


# --- responsive column count --------------------------------------------

def _columns_for_width(width: int) -> int:
    """Mirror of the GUI's helper, exercised without constructing a window."""
    from gen_modelbin_gui.tabs.generator import GeneratorTabMixin
    return GeneratorTabMixin._shape_tile_columns_for_width(width)


def test_a_wider_window_packs_more_tiles_per_row():
    # The bug this replaced: weighted grid columns kept six tiles per row and
    # spread the spare width into gaps, so maximizing made the grid emptier
    # rather than denser.
    assert _columns_for_width(1740) > _columns_for_width(926) > _columns_for_width(500)


def test_column_count_never_drops_below_one():
    # A zero would divide by zero when placing tiles.
    for width in (0, 1, 40, vinyl_tiles.TILE_W - 1):
        assert _columns_for_width(width) >= 1


def test_column_count_never_exceeds_the_catalog():
    assert _columns_for_width(100_000) == len(PRIMITIVE_CATALOG)


def test_tiles_actually_fit_the_width_they_are_claimed_to_fit():
    span = vinyl_tiles.TILE_W + 6
    for width in (300, 500, 926, 1200, 1740):
        assert _columns_for_width(width) * span <= width
