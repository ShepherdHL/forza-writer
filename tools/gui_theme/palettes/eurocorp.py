"""Eurocorp — a bold, literal homage to Syndicate (2012)'s corporate-HUD
identity: true black surfaces, warm white text, and a saturated amber
accent used broadly (solid selected-row fills, primary buttons) rather
than restrained to live/selected state the way Charcoal and Slate use it.

An earlier, flatter "Eurocorp" palette existed before Charcoal/Slate and
was retired for reading as generic dashboard chrome once unrestrained
orange was toned back to a single accent role. This palette is a
deliberate reintroduction of that unrestrained treatment, not a
regression of it — `SOLID_SELECTED_ROW` and `select_fg`'s near-black tone
both exist specifically because accent is a broad fill here, not a thin
highlight edge. See docs/GUI_THEME_SYSTEM.md for the full rationale.

`success` and `secondary_accent`/`info` are sampled from the reference
HUD's own data-comparison colors (a green "this run" figure and a blue
"personal best" figure) rather than invented, so the palette's non-accent
hues still trace back to the source material.
"""

DISPLAY_NAME = "Eurocorp"
DESCRIPTION = "Syndicate (2012)'s black/orange HUD, worn openly."

SOLID_SELECTED_ROW = True

# Optional: not part of the palette token contract (EXPECTED_KEYS), since
# Charcoal/Slate don't define it. A condensed, technical display face for
# this palette's headings/titles, matching the reference HUD's typography;
# apply.py falls back to Segoe UI Semibold wherever this exact Tk font
# family isn't registered on the current machine (verified registered name
# via tkinter.font.families() -- Windows lists this file's family as
# "DINPro-Medium", not "DIN Pro Medium").
DISPLAY_FONT_FAMILY = "DINPro-Medium"

PALETTE = {
    "bg": "#0a0a0b",
    "fg": "#f5f3ee",
    "muted_fg": "#b8ada0",
    "entry_bg": "#08080a",
    "entry_fg": "#f5f3ee",
    "select_bg": "#f0a020",
    "select_fg": "#141008",       # near-black text: accent is a solid fill here, not a highlight edge
    "button_bg": "#1c1c1f",
    "button_active_bg": "#241d12",
    "border": "#3a342a",
    "listbox_bg": "#08080a",
    "listbox_fg": "#f5f3ee",
    "log_bg": "#08080a",
    "log_fg": "#f5f3ee",
    "canvas_bg": "#08080a",
    "disabled_fg": "#5c5750",
    "accent": "#f0a020",
    "accent_active": "#c47a10",
    "accent_glow": "#ffcf7a",
    "secondary_accent": "#2f9fce",  # sampled from the reference HUD's "personal best" blue
    "success": "#3ecf6e",           # sampled from the reference HUD's "this milestone" green
    "danger": "#e6453a",
    "warn": "#e0b23a",
    "hint": "#b8ada0",
    "info": "#2f9fce",
    "panel_alt": "#131315",
    "frame_light": "#1d1d1f",
    "frame_dark": "#050506",
    "sash": "#3a342a",
}
