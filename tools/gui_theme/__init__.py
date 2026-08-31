"""The Forza Writer GUI design system: three dark palettes and three density
profiles built around clear, legible text.

Charcoal is the default: a softened neutral dark palette inspired by modern
desktop tools such as Discord. Slate retains the cooler blue-gray character
of the earlier "Eurocorp II" direction. Eurocorp is a bold, literal
reintroduction of Syndicate (2012)'s black/orange HUD identity — see
palettes/eurocorp.py for why it deliberately opts out of the restraint the
other two follow. Compact, Balanced (default), and Spacious control the
shared type and spacing scale.

Charcoal/Slate's visual identity fuses two references the user gave
directly: Syndicate (2012)'s futuristic-corporate HUD aesthetic (cold
blue-black surfaces, a single restrained warm accent used only for
live/selected state, thin precise dividers instead of heavy chrome) and
the refined spacing/surface language of a modern Vercel-style dark
interface (flat tonal elevation instead of drop shadows, hairline
borders, disciplined type scale, no visual noise).

Surface/elevation model (depth without shadows — Tk can't draw real
box-shadows, so "elevation" here means tonal steps, the same technique
Vercel's own dark mode actually leans on):
  bg        the darkest tier — root window, sidebar, the Log
            panel's frame. Reads as "chrome"/fixed UI, not content.
  panel_alt one step lifted from bg — the default background for
            TFrame/TLabel/TLabelframe, i.e. every page's actual workspace.
            Sections are grouped by a hairline border + spacing + strong
            header typography here, not by heavier per-section fill
            tones — a page full of differently-tinted "cards" reads as
            generic dashboard chrome, which is explicitly not the brief.
  entry_bg  recessed below panel_alt, close to bg — inputs, lists, the
            Log panel's text, and preview canvases all sit in this tier,
            reading as "cut into" the surface rather than sitting on it.
  accent    Charcoal/Slate: used ONLY for live/selected/primary-action
            state (the sidebar's active-tab indicator, Accent.TButton,
            progress fill, list/text selection, a focused input's border,
            a checked checkbox/radio's fill) — nowhere else, that
            restraint is the point. Eurocorp deliberately breaks this
            rule; see palettes/eurocorp.py and SOLID_SELECTED_ROW below.

`frame_light` (sidebar hover tint) and `sash` (the sidebar/content
divider hairline) are two "captured but unused" tokens from the original
palette that finally have a real job in this pass; `frame_dark` remains
reserved for a future deeper-recess need.

ttk theming only reaches ttk.* widgets; the handful of classic tk widgets
the GUIs use (Listbox, Text, Canvas) need their colors set directly. Both
are handled by apply_theme() so callers don't need to know which is which.

This package is also the GUI's full design system: the spacing scale and
label wraplength tiers from the prior polish pass, five semantic ttk
label styles (Intro/Hint/Warn/Danger/Success), a `hud_label()` helper for
the letter-spaced small-caps treatment used on section/nav chrome text,
and procedurally-drawn checkbox/radio indicator glyphs (see indicators.py)
replacing ttk's stock OS-native indicators, which read as generic
developer-tool chrome against everything else here.

Package layout — deliberately organized the way Kloudy's FH6 Painter
(KFPS) compartmentalizes its own QML themes; see docs/GUI_THEME_SYSTEM.md
for the full contract and "adding a theme" recipe:
  palettes/   one file per palette's data (the Palette*.qml equivalent),
              registered explicitly in palettes/__init__.py (qmldir's
              equivalent) with a token contract enforced at import time.
  backdrops/  optional per-theme procedural backdrop art (the
              backdropComponentFile equivalent) — a theme with no entry
              here simply has no backdrop.
  indicators.py, output_accents.py, apply.py  the "consumer" side: the
              ttk style engine and chrome that reads palette/density data
              and applies it to real widgets. Kept together rather than
              split per-theme, since KFPS doesn't fragment its shared QML
              components per-theme either.

CURRENT_PALETTE/CURRENT_DENSITY/PALETTE/DENSITIES and configure()/
palette()/density() deliberately stay in this file rather than a separate
registry submodule: configure() rebinds CURRENT_PALETTE/CURRENT_DENSITY
(not just mutates them), and callers elsewhere in this codebase read
`gui_theme.CURRENT_PALETTE` via module-qualified access expecting to see
that rebind immediately. A submodule reassigning its own module-level
name would not be visible through an `__init__.py`-level `from .x import
CURRENT_PALETTE` — that import only captures the value at import time.
Keeping the rebindable state and the function that rebinds it in the same
module sidesteps that footgun entirely. (PALETTE is safe to share across
files regardless, since it's a dict mutated in place, never rebound.)
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from . import apply as _apply
from . import context_menu as _context_menu
from .output_accents import GENERATION_METHOD_STYLES, OUTPUT_ACCENTS
from .palettes import (
    DESCRIPTIONS,
    DISPLAY_FONT_FAMILY,
    DISPLAY_NAMES,
    PALETTE_ORDER,
    PALETTES,
    SOLID_SELECTED_ROW,
)

# Re-exported as-is — no palette/density dependency.
AutoHideScrollbar = _apply.AutoHideScrollbar
hud_label = _apply.hud_label
_hex_to_colorref = _apply._hex_to_colorref
SCROLLBAR_HIT_WIDTH = _apply.SCROLLBAR_HIT_WIDTH
SCROLLBAR_THUMB_WIDTH = _apply.SCROLLBAR_THUMB_WIDTH
attach_context_menu = _context_menu.attach_context_menu
bind_context_menus = _context_menu.bind_context_menus
select_all = _context_menu.select_all
clear_text = _context_menu.clear_text

# ---------------------------------------------------------------------------
# Design system: spacing scale + label wraplength tiers
# ---------------------------------------------------------------------------
# A shared vocabulary every _build_*_page() in gen_modelbin_gui.py builds
# from, rather than each page inventing its own padx/pady numbers.

SECTION_PAD = {"padx": 12, "pady": 8}
ROW_PAD = {"padx": 8, "pady": 4}
ROW_PAD_TOP = {"padx": 8, "pady": (6, 0)}
ROW_PAD_BOTTOM = {"padx": 8, "pady": (0, 6)}
PAGE_INTRO_PAD = {"padx": 12, "pady": (14, 8)}
INDENT_PAD = (24, 0)
SCROLLBAR_GUTTER = 3                              # gap between a scrollable widget and its scrollbar

# Label wraplength, px — three tiers picked by how much horizontal room the
# label actually has, instead of a new number every time one was added:
WRAP_WIDE = 760      # full-bleed text spanning the page (intro paragraphs, run-explainers)
WRAP_MED = 680        # text inside a LabelFrame, one padding level in
WRAP_NARROW = 480     # secondary text running alongside a fixed-size preview canvas

DENSITIES = {
    "compact": {"body": 9, "detail": 8, "button_pad": (9, 4), "accent_pad": (11, 5),
                "section": (10, 6), "row": (6, 3), "intro": (10, (10, 6)), "indent": 22},
    "balanced": {"body": 10, "detail": 9, "button_pad": (10, 6), "accent_pad": (13, 7),
                 "section": (12, 8), "row": (8, 4), "intro": (12, (14, 8)), "indent": 24},
    "spacious": {"body": 11, "detail": 10, "button_pad": (12, 7), "accent_pad": (15, 8),
                 "section": (16, 11), "row": (10, 6), "intro": (16, (18, 11)), "indent": 28},
}

CURRENT_PALETTE = "charcoal"
CURRENT_DENSITY = "balanced"
PALETTE = dict(PALETTES[CURRENT_PALETTE])


def configure(palette_name: str = "charcoal", density_name: str = "balanced") -> None:
    """Select the named palette/density and update shared tokens in place."""
    global CURRENT_PALETTE, CURRENT_DENSITY, INDENT_PAD
    if palette_name not in PALETTES:
        palette_name = "charcoal"
    if density_name not in DENSITIES:
        density_name = "balanced"
    CURRENT_PALETTE, CURRENT_DENSITY = palette_name, density_name
    PALETTE.clear()
    PALETTE.update(PALETTES[palette_name])
    d = DENSITIES[density_name]
    SECTION_PAD.update(padx=d["section"][0], pady=d["section"][1])
    ROW_PAD.update(padx=d["row"][0], pady=d["row"][1])
    ROW_PAD_TOP.update(padx=d["row"][0], pady=(d["row"][1] + 2, 0))
    ROW_PAD_BOTTOM.update(padx=d["row"][0], pady=(0, d["row"][1] + 2))
    PAGE_INTRO_PAD.update(padx=d["intro"][0], pady=d["intro"][1])
    INDENT_PAD = (d["indent"], 0)


def density() -> dict:
    """Return the active density tokens for classic Tk widget styling."""
    return DENSITIES[CURRENT_DENSITY]


def palette() -> dict[str, str]:
    return PALETTE


def spacing_snapshot() -> dict[str, object]:
    """Copy the active pack-layout tokens before changing density."""
    return {
        "section": dict(SECTION_PAD), "row": dict(ROW_PAD),
        "row_top": dict(ROW_PAD_TOP), "row_bottom": dict(ROW_PAD_BOTTOM),
        "intro": dict(PAGE_INTRO_PAD), "indent": INDENT_PAD,
    }


def reflow_spacing(root: tk.Misc, previous: dict[str, object]) -> None:
    """Update already-packed widgets that use the shared density tokens."""
    current = spacing_snapshot()

    def normalized(value):
        if isinstance(value, (tuple, list)):
            return tuple(str(v) for v in value)
        parts = root.tk.splitlist(str(value))
        return tuple(parts) if len(parts) > 1 else (parts[0] if parts else "0")

    padx_map, pady_map = {}, {}
    for name in ("section", "row", "row_top", "row_bottom", "intro"):
        for axis, mapping in (("padx", padx_map), ("pady", pady_map)):
            old, new = previous[name][axis], current[name][axis]
            if normalized(old) != normalized(new):
                mapping[normalized(old)] = new
    padx_map[normalized(previous["indent"])] = current["indent"]

    pending = [root]
    while pending:
        parent = pending.pop()
        pending.extend(parent.winfo_children())
        if parent.winfo_manager() != "pack":
            continue
        info = parent.pack_info()
        changes = {}
        old_padx, old_pady = normalized(info.get("padx", 0)), normalized(info.get("pady", 0))
        if old_padx in padx_map:
            changes["padx"] = padx_map[old_padx]
        if old_pady in pady_map:
            changes["pady"] = pady_map[old_pady]
        if changes:
            parent.pack_configure(**changes)


def apply_theme(root: tk.Misc, style: ttk.Style, tk_widgets: list[tk.Widget] = ()) -> None:
    return _apply.apply_theme(root, style, tk_widgets,
                               palette=PALETTE, palette_key=CURRENT_PALETTE,
                               density=DENSITIES[CURRENT_DENSITY])


def configure_text_tags(text_widget: tk.Text) -> None:
    return _apply.configure_text_tags(text_widget, PALETTE)


def build_legend(parent: tk.Misc, entries: list[tuple[str, str]], *, columns: int = 1) -> ttk.Frame:
    return _apply.build_legend(parent, entries, PALETTE, columns=columns)


def apply_title_bar_theme(root: tk.Misc) -> None:
    return _apply.apply_title_bar_theme(root, PALETTE)


def display_font_family(root: tk.Misc, fallback: str = "Segoe UI Semibold") -> str:
    """The active palette's preferred display-font Tk family name, or
    `fallback` if the palette has none or the font isn't actually
    registered on this machine. For hand-built font tuples outside
    apply_theme()'s own style construction (e.g. the sidebar nav labels
    and Credits' category headings) that want the same palette-aware
    display face apply_theme() already gives headings/titles."""
    return _apply._resolve_font_family(root, DISPLAY_FONT_FAMILY.get(CURRENT_PALETTE), fallback)


def backdrop_photo_image(width: int, height: int, master: tk.Misc):
    """Return a PhotoImage of the *active* theme's backdrop at this size,
    or None if it has none. See apply.py's backdrop_photo_image and
    backdrops/__init__.py."""
    return _apply.backdrop_photo_image(CURRENT_PALETTE, width, height, PALETTE, master)


def backdrop_frames(width: int, height: int) -> list | None:
    """The active theme's precomputed backdrop animation flip-book at this
    size, or None if it has none. See apply.py's backdrop_frames."""
    return _apply.backdrop_frames(CURRENT_PALETTE, width, height, PALETTE)
