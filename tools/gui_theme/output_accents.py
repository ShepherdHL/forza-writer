"""Output-method identity colors. These deliberately sit outside the
selected theme palettes: switching between Charcoal, Slate, and Eurocorp
should not change the visual identity of an output format. The original
pure fuchsia was softened slightly, and Legacy uses teal rather than cyan
so it remains distinct from modern Primitive Shapes at a glance. Image
(Image to Text) is violet — the one hue in this set not already used by a
warn/danger/info/accent role in any palette, so it reads as its own
identity at a glance.
"""

import tkinter as tk
from tkinter import ttk

from .indicators import _build_indicator_images, _GLYPH_SIZE, _ICON_REFS

OUTPUT_ACCENTS = {
    "modelbin": "#E879F9",
    "json": "#7DF9FF",
    "json_legacy": "#2DD4BF",
    "image": "#A78BFA",
    "stencil": "#C0C0C0",
    "config_bg": "#3D3C3A",
    "config_active_bg": "#4A4946",
    "config_border": "#777673",
}

# Generation-method concept -> the ttk style carrying its identity color,
# registered by _apply_output_option_styles below. Keyed by the same output-
# mode strings Generator/Advanced Generator's `output_var` uses (Direct
# Generator's own `method` values differ — 'modern'/'legacy'/'image' — so it
# maps through its own small local dict onto these same style names rather
# than reusing this dict's keys directly). Centralized so a page never has to
# hand-write its own {mode: style_name} table the way Generator and Advanced
# Generator both used to.
GENERATION_METHOD_STYLES = {
    "modelbin": "Modelbin.TRadiobutton",     # Custom Mesh
    "json": "Primitive.TRadiobutton",        # Shape Fitting
    "json_legacy": "Legacy.TRadiobutton",    # Pixel Tracing
    "image": "Image.TRadiobutton",           # Image to Text
}


def apply_output_option_styles(style: ttk.Style, p: dict[str, str], master: tk.Misc,
                                palette_key: str) -> None:
    """Give each output-related control its own stable identity color.
    `palette_key` namespaces the registered ttk elements (see
    gui_theme/apply.py's _apply_custom_indicators for why this can't be
    read off a module global once palette data and its consumer live in
    different files)."""
    try:
        specs = (
            ("Modelbin.TRadiobutton", "radio", OUTPUT_ACCENTS["modelbin"]),
            ("Primitive.TRadiobutton", "radio", OUTPUT_ACCENTS["json"]),
            ("Legacy.TRadiobutton", "radio", OUTPUT_ACCENTS["json_legacy"]),
            ("Image.TRadiobutton", "radio", OUTPUT_ACCENTS["image"]),
            ("Stencil.TCheckbutton", "check", OUTPUT_ACCENTS["stencil"]),
        )
        for style_name, kind, accent in specs:
            token = style_name.split(".", 1)[0].lower()
            element = f"Output.{palette_key}.{token}.{kind}.indicator"
            if element not in style.element_names():
                # PhotoImage is a native Tk resource. Rebuilding and replacing
                # it on every theme refresh can garbage-collect an image while
                # ttk still has it attached to an element. Only create it with
                # the element, and retain it for this specific Tcl interpreter.
                images = _build_indicator_images({**p, "accent": accent}, master=master)
                _ICON_REFS[(id(style.tk), f"{palette_key}.{token}")] = list(images.values())
                off, on = images[f"{kind}_off"], images[f"{kind}_on"]
                style.element_create(
                    element, "image", off,
                    ("disabled", "selected", images[f"{kind}_on_disabled"]),
                    ("disabled", images[f"{kind}_off_disabled"]),
                    ("selected", "active", on),
                    ("selected", on),
                    ("active", images[f"{kind}_off_hover"]),
                    width=_GLYPH_SIZE, height=_GLYPH_SIZE, sticky="w")
            prefix = "Radiobutton" if kind == "radio" else "Checkbutton"
            style.layout(style_name, [
                (f"{prefix}.padding", {"sticky": "nswe", "children": [
                    (element, {"side": "left", "sticky": ""}),
                    (f"{prefix}.focus", {"side": "left", "sticky": "", "children": [
                        (f"{prefix}.label", {"sticky": "nswe"}),
                    ]}),
                ]}),
            ])
            style.configure(style_name, background=p["panel_alt"], foreground=accent)
            style.map(style_name,
                      foreground=[("disabled", p["disabled_fg"])],
                      background=[("active", p["panel_alt"])])

        style.configure(
            "Iridium.TButton",
            background=OUTPUT_ACCENTS["config_bg"], foreground=p["fg"],
            bordercolor=OUTPUT_ACCENTS["config_border"], borderwidth=1,
            relief="solid")
        style.map(
            "Iridium.TButton",
            background=[("active", OUTPUT_ACCENTS["config_active_bg"]),
                        ("disabled", p["panel_alt"])],
            bordercolor=[("active", OUTPUT_ACCENTS["stencil"]),
                         ("disabled", p["border"])],
            foreground=[("disabled", p["disabled_fg"])])
    except tk.TclError:
        pass
