"""Charcoal — the default palette. A softened neutral dark theme inspired
by modern desktop tools such as Discord, fused with Syndicate (2012)'s
futuristic-corporate HUD restraint (a single warm accent reserved for
live/selected state) and a Vercel-style flat tonal elevation model. See
`theme_palettes/__init__.py` for the token contract every palette here
must satisfy, and `docs/GUI_THEME_SYSTEM.md` for the full design system.
"""

DISPLAY_NAME = "Charcoal"
DESCRIPTION = "The default softer neutral theme."

# Whether the active nav row in the sidebar takes a full solid-accent fill
# (Eurocorp) or the restrained left-edge indicator strip every other
# palette here uses — see theme_palettes/eurocorp.py.
SOLID_SELECTED_ROW = False

PALETTE = {
    "bg": "#1e1f22",
    "fg": "#f2f3f5",
    "muted_fg": "#b5bac1",
    "entry_bg": "#1e1f22",
    "entry_fg": "#f2f3f5",
    "select_bg": "#e08a3f",      # accent — selection highlight reuses the accent, as before
    "select_fg": "#fdf6ef",
    "button_bg": "#383a40",
    "button_active_bg": "#43464d",
    "border": "#41434a",
    "listbox_bg": "#1e1f22",
    "listbox_fg": "#f2f3f5",
    "log_bg": "#1e1f22",
    "log_fg": "#f2f3f5",
    "canvas_bg": "#1e1f22",
    "disabled_fg": "#72767d",
    "accent": "#e08a3f",
    "accent_active": "#a8611f",  # darkens on press, reads as "engaged"
    "accent_glow": "#f6b877",    # light accent tint for a button/focus edge, never a fill
    "secondary_accent": "#5c7a94",  # Syndicate's cold companion tone — info/focus on non-primary controls
    "success": "#72a08c",        # deliberately muted, not vivid green
    "danger": "#c9645a",
    "warn": "#c99a52",           # amber-yellow, distinct from accent's cleaner orange
    "hint": "#b5bac1",
    "info": "#5c7a94",
    "panel_alt": "#2b2d31",
    "frame_light": "#313338",
    "frame_dark": "#232428",
    "sash": "#41434a",
}
