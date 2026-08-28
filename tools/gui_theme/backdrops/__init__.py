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


def get_backdrop(theme_name: str):
    """Return the `(size, palette) -> PIL.Image` builder for `theme_name`,
    or None if that theme has no backdrop."""
    return _BACKDROPS.get(theme_name)
