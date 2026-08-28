"""Palette registry and token contract.

Every palette module in this package exports `PALETTE` (a dict matching
`EXPECTED_KEYS` exactly), `DISPLAY_NAME`, `DESCRIPTION`, and
`SOLID_SELECTED_ROW`. Registration below is explicit — a new palette module
existing in this directory does nothing until it's added to `_REGISTRY` —
the same "file exists but isn't wired in" discipline KFPS's `qmldir` +
`Theme.qml` `palettes` list use for `Palette*.qml` files. A palette that
doesn't match the contract fails at import time, not the first time a
missing key happens to be read.

See docs/GUI_THEME_SYSTEM.md for the full design system.
"""

from . import charcoal, eurocorp, slate

EXPECTED_KEYS = frozenset({
    "bg", "fg", "muted_fg", "entry_bg", "entry_fg", "select_bg", "select_fg",
    "button_bg", "button_active_bg", "border", "listbox_bg", "listbox_fg",
    "log_bg", "log_fg", "canvas_bg", "disabled_fg", "accent", "accent_active",
    "accent_glow", "secondary_accent", "success", "danger", "warn", "hint",
    "info", "panel_alt", "frame_light", "frame_dark", "sash",
})

# Explicit (slug, module) registration, in display order — the single
# place a new palette needs to be added for it to become selectable.
_REGISTRY = (
    ("charcoal", charcoal),
    ("slate", slate),
    ("eurocorp", eurocorp),
)

PALETTES: dict[str, dict[str, str]] = {}
PALETTE_ORDER: list[str] = []
DISPLAY_NAMES: dict[str, str] = {}
DESCRIPTIONS: dict[str, str] = {}
SOLID_SELECTED_ROW: dict[str, bool] = {}

for _slug, _module in _REGISTRY:
    _palette = _module.PALETTE
    _missing = EXPECTED_KEYS - set(_palette)
    _extra = set(_palette) - EXPECTED_KEYS
    if _missing or _extra:
        raise ValueError(
            f"palette {_slug!r} does not match the token contract: "
            f"missing={sorted(_missing)} extra={sorted(_extra)}")
    PALETTES[_slug] = _palette
    PALETTE_ORDER.append(_slug)
    DISPLAY_NAMES[_slug] = _module.DISPLAY_NAME
    DESCRIPTIONS[_slug] = _module.DESCRIPTION
    SOLID_SELECTED_ROW[_slug] = _module.SOLID_SELECTED_ROW

del _slug, _module, _palette, _missing, _extra
