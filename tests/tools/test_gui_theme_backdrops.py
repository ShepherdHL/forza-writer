import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "tools"))
import gui_theme  # noqa: E402
from gui_theme.backdrops import get_backdrop  # noqa: E402
from gui_theme.backdrops.eurocorp import build_backdrop  # noqa: E402
from gui_theme.palettes.eurocorp import PALETTE as EUROCORP_PALETTE  # noqa: E402

tk = pytest.importorskip("tkinter")
from tkinter import ttk  # noqa: E402


def test_charcoal_and_slate_have_no_backdrop():
    assert get_backdrop("charcoal") is None
    assert get_backdrop("slate") is None


def test_eurocorp_has_a_backdrop_builder():
    assert get_backdrop("eurocorp") is build_backdrop


def test_build_backdrop_is_deterministic_for_the_same_size():
    first = build_backdrop((240, 400), EUROCORP_PALETTE)
    second = build_backdrop((240, 400), EUROCORP_PALETTE)
    assert first.tobytes() == second.tobytes()


def test_build_backdrop_matches_the_requested_size():
    image = build_backdrop((180, 260), EUROCORP_PALETTE)
    assert image.size == (180, 260)


def test_build_backdrop_handles_a_degenerate_size_without_raising():
    image = build_backdrop((0, 0), EUROCORP_PALETTE)
    assert image.size == (1, 1)


def test_backdrop_photo_image_returns_none_for_a_theme_without_one():
    root = tk.Tk()
    try:
        root.withdraw()
        assert gui_theme.backdrop_photo_image(200, 200, root) is None  # default palette is charcoal
    finally:
        root.destroy()


def test_backdrop_photo_image_renders_for_eurocorp_without_raising():
    root = tk.Tk()
    try:
        root.withdraw()
        try:
            gui_theme.configure("eurocorp", "balanced")
            photo = gui_theme.backdrop_photo_image(200, 200, root)
            assert photo is not None
            assert photo.width() == 200
            assert photo.height() == 200
            # A real Canvas must actually accept the image without raising —
            # element_create/layout surgery elsewhere in this design system
            # is easy to get subtly wrong in ways that only show up here.
            canvas = tk.Canvas(root)
            canvas.create_image(0, 0, anchor='nw', image=photo)
            canvas.pack()
            root.update()
        finally:
            gui_theme.configure()  # restore the default for later tests
    finally:
        root.destroy()


def test_backdrop_photo_image_is_cached_for_the_same_size():
    root = tk.Tk()
    try:
        root.withdraw()
        try:
            gui_theme.configure("eurocorp", "balanced")
            first = gui_theme.backdrop_photo_image(150, 150, root)
            second = gui_theme.backdrop_photo_image(150, 150, root)
            assert first is second
        finally:
            gui_theme.configure()
    finally:
        root.destroy()
