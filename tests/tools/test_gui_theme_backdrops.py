import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "tools"))
import gui_theme  # noqa: E402
from gui_theme.backdrops import get_backdrop, get_backdrop_frames  # noqa: E402
from gui_theme.backdrops.eurocorp import build_backdrop, build_backdrop_frames  # noqa: E402
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


def test_charcoal_and_slate_have_no_backdrop_frames():
    assert get_backdrop_frames("charcoal") is None
    assert get_backdrop_frames("slate") is None


def test_eurocorp_has_a_backdrop_frames_builder():
    assert get_backdrop_frames("eurocorp") is build_backdrop_frames


def test_build_backdrop_frames_returns_the_requested_count():
    frames = build_backdrop_frames((240, 400), EUROCORP_PALETTE, n_frames=12)
    assert len(frames) == 12
    assert all(frame.size == (240, 400) for frame in frames)


def test_build_backdrop_frames_is_deterministic_for_the_same_size():
    first = build_backdrop_frames((240, 400), EUROCORP_PALETTE)
    second = build_backdrop_frames((240, 400), EUROCORP_PALETTE)
    assert [f.tobytes() for f in first] == [f.tobytes() for f in second]


def test_build_backdrop_frames_first_frame_matches_the_static_backdrop():
    # The flip-book's frame 0 must be pixel-identical to build_backdrop's
    # own output -- same node positions, same accent lines -- so switching
    # a static consumer over to the animated builder is a strict upgrade,
    # not a visible jump at the moment the animation starts.
    static = build_backdrop((240, 400), EUROCORP_PALETTE)
    frames = build_backdrop_frames((240, 400), EUROCORP_PALETTE)
    assert frames[0].tobytes() == static.tobytes()


def test_build_backdrop_frames_nodes_drift_and_wrap():
    frames = build_backdrop_frames((240, 400), EUROCORP_PALETTE, n_frames=12)
    # Consecutive frames actually differ (nodes moved)...
    assert frames[0].tobytes() != frames[1].tobytes()
    # ...but wrapping means the drift is bounded, not runaway: no frame
    # should end up identical to a pure black/transparent field (which
    # would indicate every node wrapped out of view at once, a sign the
    # modulo wraparound is broken rather than working).
    empty = Image.new("RGBA", (240, 400), (0, 0, 0, 0)).tobytes()
    assert all(frame.tobytes() != empty for frame in frames)


def test_build_backdrop_frames_handles_a_degenerate_size_without_raising():
    frames = build_backdrop_frames((0, 0), EUROCORP_PALETTE)
    assert len(frames) >= 1
    assert frames[0].size == (1, 1)


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


def test_backdrop_frames_returns_none_for_a_theme_without_one():
    assert gui_theme.backdrop_frames(200, 200) is None  # default palette is charcoal


def test_backdrop_frames_returns_the_flip_book_for_eurocorp():
    try:
        gui_theme.configure("eurocorp", "balanced")
        frames = gui_theme.backdrop_frames(200, 200)
        assert frames is not None
        assert len(frames) > 1
        assert all(frame.size == (200, 200) for frame in frames)
    finally:
        gui_theme.configure()


def test_backdrop_frames_is_cached_for_the_same_size():
    try:
        gui_theme.configure("eurocorp", "balanced")
        first = gui_theme.backdrop_frames(150, 150)
        second = gui_theme.backdrop_frames(150, 150)
        assert first is second
    finally:
        gui_theme.configure()


def test_backdrop_photo_image_does_not_share_across_different_masters():
    # A bare (theme_key, width, height) cache key would let a second,
    # unrelated Canvas/interpreter at a coincidentally matching size reuse
    # a PhotoImage tied to some other (possibly already-destroyed) Tk
    # interpreter -- confirmed directly via a cross-test-file pytest run
    # that hit "image ... doesn't exist" from exactly this. Two distinct
    # masters at the same theme+size must never receive the same object.
    # Two Canvases under one root (rather than two real tk.Tk() instances,
    # which this codebase's own test suite deliberately avoids -- see
    # conftest.py's tk_root fixture on Tcl-init flakiness) still exercise
    # the actual property being fixed: the cache key is id(master), which
    # differs for any two distinct widgets regardless of interpreter.
    root = tk.Tk()
    try:
        root.withdraw()
        try:
            gui_theme.configure("eurocorp", "balanced")
            canvas_a = tk.Canvas(root)
            canvas_b = tk.Canvas(root)
            photo_a = gui_theme.backdrop_photo_image(150, 150, canvas_a)
            photo_b = gui_theme.backdrop_photo_image(150, 150, canvas_b)
            assert photo_a is not photo_b
        finally:
            gui_theme.configure()
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
