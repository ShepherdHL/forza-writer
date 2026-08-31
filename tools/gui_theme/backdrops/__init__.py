"""Optional per-theme backdrop registry.

A palette with no entry here simply has no backdrop — mirroring KFPS's
`backdropComponentFile` contract, where an empty path means the capability
is disabled rather than every theme needing to opt out explicitly. See
docs/GUI_THEME_SYSTEM.md.
"""

from . import eurocorp

_BACKDROPS = {
    "eurocorp": eurocorp.build_backdrop,
}

_BACKDROP_FRAME_BUILDERS = {
    "eurocorp": eurocorp.build_backdrop_frames,
}


def get_backdrop(theme_name: str):
    """Return the `(size, palette) -> PIL.Image` builder for `theme_name`,
    or None if that theme has no backdrop."""
    return _BACKDROPS.get(theme_name)


def get_backdrop_frames(theme_name: str):
    """Return the `(size, palette, n_frames=...) -> list[PIL.Image]` flip-
    book builder for `theme_name`, or None if that theme has no animated
    backdrop. A theme may have get_backdrop without this (a static-only
    backdrop), but never the reverse."""
    return _BACKDROP_FRAME_BUILDERS.get(theme_name)
