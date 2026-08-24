"""The Forza Writer GUI design system: two dark palettes and three density
profiles built around clear, legible text and restrained orange accents.

Charcoal is the default: a softened neutral dark palette inspired by modern
desktop tools such as Discord. Slate retains the cooler blue-gray character
of the earlier "Eurocorp II" direction. Compact, Balanced (default), and
Spacious control the shared type and spacing scale.

The visual identity still fuses two references the user gave directly:
Syndicate (2012)'s futuristic-corporate HUD aesthetic (cold blue-black
surfaces, a single restrained warm accent used only for live/selected
state, thin precise dividers instead of heavy chrome) and the refined
spacing/surface language of a modern Vercel-style dark interface (flat
tonal elevation instead of drop shadows, hairline borders, disciplined
type scale, no visual noise). This supersedes the original "Eurocorp"
palette from an earlier pass, retuned as a real design system rather than a
flat color list.

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
  accent    used ONLY for live/selected/primary-action state: the
            sidebar's active-tab indicator, Accent.TButton, progress fill,
            list/text selection, a focused input's border, a checked
            checkbox/radio's fill. Nowhere else — that restraint is the
            point.

`frame_light` (sidebar hover tint) and `sash` (the sidebar/content
divider hairline) are the two "captured but unused" tokens from the
original palette that finally have a real job in this pass; `frame_dark`
remains reserved for a future deeper-recess need.

ttk theming only reaches ttk.* widgets; the handful of classic tk widgets
the GUIs use (Listbox, Text, Canvas) need their colors set directly. Both
are handled by apply_theme() so callers don't need to know which is which.

This module is also the GUI's full design system: the spacing scale and
label wraplength tiers from the prior polish pass, five semantic ttk
label styles (Intro/Hint/Warn/Danger/Success), a `hud_label()` helper for
the letter-spaced small-caps treatment used on section/nav chrome text,
and procedurally-drawn checkbox/radio indicator glyphs (see
`_build_indicator_images`) replacing ttk's stock OS-native indicators,
which read as generic developer-tool chrome against everything else here.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from PIL import Image, ImageDraw, ImageTk

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

PALETTES = {
    "charcoal": {
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
    },
    "slate": {
    "bg": "#1c1f24", "fg": "#f3f4f6", "muted_fg": "#aeb6c1",
    "entry_bg": "#202329", "entry_fg": "#f3f4f6", "select_bg": "#e08a3f",
    "select_fg": "#fdf6ef", "button_bg": "#343942", "button_active_bg": "#404650",
    "border": "#414750", "listbox_bg": "#202329", "listbox_fg": "#f3f4f6",
    "log_bg": "#1c1f24", "log_fg": "#f3f4f6", "canvas_bg": "#202329",
    "disabled_fg": "#707985", "accent": "#e08a3f", "accent_active": "#a8611f",
    "accent_glow": "#f6b877", "secondary_accent": "#6f8da8", "success": "#72a08c",
    "danger": "#d06b62", "warn": "#d2a35b", "hint": "#aeb6c1", "info": "#6f8da8",
    "panel_alt": "#24272d", "frame_light": "#2b2f36", "frame_dark": "#202329",
    "sash": "#414750",
    },
}

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

# Output-method identity colors. These deliberately sit outside the selected
# theme palettes: switching between Charcoal and Slate should not change the
# visual identity of an output format. The original pure fuchsia was softened
# slightly, and Legacy uses teal rather than cyan so it remains distinct from
# modern Primitive Shapes at a glance. Image (Image to Text) is violet — the
# one hue in this set not already used by a warn/danger/info/accent role
# elsewhere in either palette, so it reads as its own identity at a glance.
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

class AutoHideScrollbar(ttk.Scrollbar):
    """A ttk.Scrollbar that hides itself when the widget it controls
    already shows all of its content, and reappears once it doesn't —
    "scrollbars appear only when needed," not a permanently-visible,
    functionally inert full-trough thumb sitting on a short page that
    never needed to scroll in the first place.

    Geometry-manager-agnostic: remembers whatever `pack()`/`grid()` call
    last placed it and replays those exact arguments to reappear later.
    Every scrollbar in this GUI uses `pack()`, but nothing about the
    hide/show logic is pack-specific, so `grid()` is supported too.

    Usage is a drop-in replacement for `ttk.Scrollbar` — construct it,
    wire it to a widget's `yscrollcommand`/`xscrollcommand` exactly as
    you would a normal Scrollbar, and call `.pack(...)` once up front;
    it manages its own visibility from there.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._geo_manager: str | None = None
        self._geo_kwargs: dict | None = None

    def pack(self, **kwargs):
        self._geo_manager, self._geo_kwargs = "pack", kwargs
        super().pack(**kwargs)

    def grid(self, **kwargs):
        self._geo_manager, self._geo_kwargs = "grid", kwargs
        super().grid(**kwargs)

    def set(self, lo, hi):
        lo, hi = float(lo), float(hi)
        if lo <= 0.0 and hi >= 1.0:
            if self._geo_manager == "pack":
                self.pack_forget()
            elif self._geo_manager == "grid":
                self.grid_forget()
        elif self._geo_kwargs is not None and not self.winfo_ismapped():
            if self._geo_manager == "pack":
                super().pack(**self._geo_kwargs)
            elif self._geo_manager == "grid":
                super().grid(**self._geo_kwargs)
        super().set(lo, hi)


# Classic tk widgets (not ttk) that need direct color configuration. Each
# entry maps a widget's config option -> a palette key.
_TK_WIDGET_OPTION_MAP = {
    "bg": "listbox_bg",
    "fg": "listbox_fg",
    "selectbackground": "select_bg",
    "selectforeground": "select_fg",
    "highlightbackground": "border",
    "highlightcolor": "border",
    "insertbackground": "fg",
}

# U+2009 THIN SPACE between characters — Tk has no letter-spacing/tracking
# property, so this is the standard trick to approximate it. Reserved for
# short chrome labels only (section headers, sidebar nav) — never body
# copy, which needs to stay plain and readable.
_TRACKING_CHAR = " "


def hud_label(text: str) -> str:
    """Upper-case + letter-spaced treatment for section/nav chrome text —
    the small-caps HUD-console labeling this identity leans on. A thin
    space is inserted between adjacent non-space characters only, so
    tracking is added within each run of letters/digits without also
    widening real word gaps further — but a single plain space doesn't
    read as a word break once every letter around it already carries its
    own thin-space tracking (confirmed by rendering "Fontpack root
    folder": the real gaps between words were nearly invisible next to
    the letter tracking), so a real space is widened to two plain spaces
    instead, clearly out-sizing the tracking: "1. Font" -> "1.  F O N T"."""
    text = text.upper()
    out = []
    for i, ch in enumerate(text):
        if ch.isspace():
            # A plain ASCII space gets widened; anything else whitespace-y
            # (e.g. an already-inserted thin space, if this ever runs
            # twice on the same string) passes through unchanged rather
            # than compounding — this is what keeps the function
            # idempotent.
            out.append("  " if ch == " " else ch)
            continue
        out.append(ch)
        if i < len(text) - 1 and not text[i + 1].isspace():
            out.append(_TRACKING_CHAR)
    return "".join(out)


def palette() -> dict[str, str]:
    return PALETTE


# ---------------------------------------------------------------------------
# Custom checkbox/radio indicator glyphs
# ---------------------------------------------------------------------------
_GLYPH_SIZE = 15
_ICON_REFS: dict[tuple[int, str], list] = {}  # keeps each Tk interpreter's PhotoImages alive


def _build_indicator_images(p: dict[str, str], master: tk.Misc | None = None) -> dict[str, "ImageTk.PhotoImage"]:
    """Procedurally-drawn checkbox/radio glyphs — flat outline when
    unset, accent-filled when set — replacing ttk's stock OS-native
    indicator, which reads as generic utility-software chrome next to
    everything else in this pass. The radio "on" state is a thin accent
    ring with a small solid center dot (a reticle motif) rather than a
    fully filled circle, matching the HUD identity instead of a generic
    material-design radio."""
    s = _GLYPH_SIZE
    inset = 2
    c = s // 2

    def _canvas():
        return Image.new("RGBA", (s, s), (0, 0, 0, 0))

    images: dict[str, Image.Image] = {}

    box = [inset, inset, s - 1 - inset, s - 1 - inset]

    img = _canvas()
    ImageDraw.Draw(img).rectangle(box, outline=p["border"], width=1)
    images["check_off"] = img

    img = _canvas()
    ImageDraw.Draw(img).rectangle(box, outline=p["muted_fg"], width=1)
    images["check_off_hover"] = img

    img = _canvas()
    ImageDraw.Draw(img).rectangle(box, outline=p["disabled_fg"], width=1)
    images["check_off_disabled"] = img

    img = _canvas()
    d = ImageDraw.Draw(img)
    d.rectangle(box, fill=p["accent"], outline=p["accent"])
    d.line([(inset + 2, c), (c - 1, s - inset - 2), (s - inset - 2, inset + 1)],
           fill=p["select_fg"], width=2, joint="curve")
    images["check_on"] = img

    img = _canvas()
    d = ImageDraw.Draw(img)
    d.rectangle(box, fill=p["disabled_fg"], outline=p["disabled_fg"])
    d.line([(inset + 2, c), (c - 1, s - inset - 2), (s - inset - 2, inset + 1)],
           fill=p["bg"], width=2, joint="curve")
    images["check_on_disabled"] = img

    ellipse_box = [inset, inset, s - 1 - inset, s - 1 - inset]

    img = _canvas()
    ImageDraw.Draw(img).ellipse(ellipse_box, outline=p["border"], width=1)
    images["radio_off"] = img

    img = _canvas()
    ImageDraw.Draw(img).ellipse(ellipse_box, outline=p["muted_fg"], width=1)
    images["radio_off_hover"] = img

    img = _canvas()
    ImageDraw.Draw(img).ellipse(ellipse_box, outline=p["disabled_fg"], width=1)
    images["radio_off_disabled"] = img

    img = _canvas()
    d = ImageDraw.Draw(img)
    d.ellipse(ellipse_box, outline=p["accent"], width=1)
    r = 2
    d.ellipse([c - r, c - r, c + r, c + r], fill=p["accent"])
    images["radio_on"] = img

    img = _canvas()
    d = ImageDraw.Draw(img)
    d.ellipse(ellipse_box, outline=p["disabled_fg"], width=1)
    d.ellipse([c - r, c - r, c + r, c + r], fill=p["disabled_fg"])
    images["radio_on_disabled"] = img

    # Explicit master, not Tkinter's ambient "default root" (tkinter._default_root)
    # — that global tracks whichever Tk() was created/destroyed most recently
    # process-wide, which silently diverges from `style`'s own interpreter the
    # moment more than one Tk() root exists across a process's lifetime (e.g. a
    # test suite creating several independent tk.Tk() instances in sequence).
    # An image bound to the wrong interpreter fails at element_create time with
    # `image "pyimageN" doesn't exist` on THIS interpreter, since Tk images are
    # per-interpreter despite the auto-generated name being a process-wide counter.
    return {name: ImageTk.PhotoImage(image, master=master) for name, image in images.items()}


def _apply_custom_indicators(style: ttk.Style, p: dict[str, str], master: tk.Misc) -> None:
    """Register the procedural glyphs as ttk elements and re-layout
    TCheckbutton/TRadiobutton to use them. Best-effort: a failure here
    (an unusual Tk build without image-element support, e.g.) must not
    block the app — it just falls back to ttk's stock indicators."""
    try:
        palette_key = CURRENT_PALETTE
        check_element = f"Custom.{palette_key}.Checkbutton.indicator"
        radio_element = f"Custom.{palette_key}.Radiobutton.indicator"
        if check_element not in style.element_names():
            images = _build_indicator_images(p, master=master)
            _ICON_REFS[(id(style.tk), palette_key)] = list(images.values())

            style.element_create(
                check_element, "image", images["check_off"],
                ("disabled", "selected", images["check_on_disabled"]),
                ("disabled", images["check_off_disabled"]),
                ("selected", "active", images["check_on"]),
                ("selected", images["check_on"]),
                ("active", images["check_off_hover"]),
                width=_GLYPH_SIZE, height=_GLYPH_SIZE, sticky="w")
            style.element_create(
                radio_element, "image", images["radio_off"],
                ("disabled", "selected", images["radio_on_disabled"]),
                ("disabled", images["radio_off_disabled"]),
                ("selected", "active", images["radio_on"]),
                ("selected", images["radio_on"]),
                ("active", images["radio_off_hover"]),
                width=_GLYPH_SIZE, height=_GLYPH_SIZE, sticky="w")
        style.layout("TCheckbutton", [
            ("Checkbutton.padding", {"sticky": "nswe", "children": [
                (check_element, {"side": "left", "sticky": ""}),
                ("Checkbutton.focus", {"side": "left", "sticky": "", "children": [
                    ("Checkbutton.label", {"sticky": "nswe"}),
                ]}),
            ]}),
        ])

        style.layout("TRadiobutton", [
            ("Radiobutton.padding", {"sticky": "nswe", "children": [
                (radio_element, {"side": "left", "sticky": ""}),
                ("Radiobutton.focus", {"side": "left", "sticky": "", "children": [
                    ("Radiobutton.label", {"sticky": "nswe"}),
                ]}),
            ]}),
        ])
    except tk.TclError:
        pass


def _apply_output_option_styles(style: ttk.Style, p: dict[str, str], master: tk.Misc) -> None:
    """Give each output-related control its own stable identity color."""
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
            element = f"Output.{CURRENT_PALETTE}.{token}.{kind}.indicator"
            if element not in style.element_names():
                # PhotoImage is a native Tk resource. Rebuilding and replacing
                # it on every theme refresh can garbage-collect an image while
                # ttk still has it attached to an element. Only create it with
                # the element, and retain it for this specific Tcl interpreter.
                images = _build_indicator_images({**p, "accent": accent}, master=master)
                _ICON_REFS[(id(style.tk), f"{CURRENT_PALETTE}.{token}")] = list(images.values())
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


SCROLLBAR_HIT_WIDTH = 12   # invisible clickable/draggable width of the whole scrollbar
SCROLLBAR_THUMB_WIDTH = 4  # visible thin colored thumb, centered within the hit width


def _apply_flat_scrollbars(style: ttk.Style, p: dict[str, str]) -> None:
    """A thin trough+thumb scrollbar with no arrow buttons — ttk clam's
    stock scrollbar is a chunky, dated control that reads as OS chrome;
    this is the flat minimal rail a modern dark interface actually uses.

    The widget's own clickable/draggable width (`arrowsize` — in clam's
    scrollbar geometry this sizes the whole cross-axis, not just the now
    -removed arrow glyphs) is kept at a real, comfortably-clickable size
    (SCROLLBAR_HIT_WIDTH). A previous pass set `arrowsize=0` to get a
    hairline-thin look, which also shrank the *entire widget* — hit-testing
    included — down to a 1px-wide target: technically draggable but only
    if the pointer landed on that exact pixel, which reads as "dragging
    doesn't work." The thin look now comes from the thumb sub-element's
    own `width`, independent of the trough: the thumb's `sticky` only
    covers its scroll axis (`ns`/`ew`), not the cross axis, so it keeps
    its narrow natural width and sits centered in the wider invisible
    trough instead of stretching to fill it. troughcolor matches the
    surrounding surface so that full-width hit area stays visually
    invisible — only the thin thumb reads on screen.
    """
    for orient, layout_name, trough, thumb, thumb_sticky in (
        ("Vertical", "Vertical.TScrollbar", "Vertical.Scrollbar.trough", "Vertical.Scrollbar.thumb", "ns"),
        ("Horizontal", "Horizontal.TScrollbar", "Horizontal.Scrollbar.trough", "Horizontal.Scrollbar.thumb", "ew"),
    ):
        style.layout(layout_name, [
            (trough, {"sticky": "ns" if orient == "Vertical" else "ew", "children": [
                (thumb, {"expand": "1", "sticky": thumb_sticky}),
            ]}),
        ])
    # The thumb needs to actually be findable/grabbable — `border`'s
    # whole point is sitting at near-zero contrast against the surface,
    # which is right for a hairline divider and wrong for a scroll thumb.
    # gripcount=0 removes clam's legacy "grip" dots rendered mid-thumb —
    # a dated drag-handle affordance from another era of UI toolkits that
    # clashes with everything else in this identity; a flat colored thumb
    # already reads as draggable on its own.
    style.configure("TScrollbar", background=p["muted_fg"], troughcolor=p["panel_alt"],
                     bordercolor=p["panel_alt"], relief="flat",
                     arrowsize=SCROLLBAR_HIT_WIDTH, width=SCROLLBAR_THUMB_WIDTH, gripcount=0)
    style.map("TScrollbar", background=[("active", p["accent"]), ("pressed", p["accent"])])


def apply_theme(root: tk.Misc, style: ttk.Style, tk_widgets: list[tk.Widget] = ()) -> None:
    """Apply the palette + full design system to `style` (ttk) and any
    classic tk widgets passed in `tk_widgets` (e.g. a Listbox, Text, or
    Canvas — ttk styling doesn't reach these)."""
    p = PALETTE
    style.theme_use("clam")

    d = DENSITIES[CURRENT_DENSITY]
    heading_font = tkfont.Font(family="Segoe UI Semibold", size=d["body"])
    accent_button_font = tkfont.Font(family="Segoe UI Semibold", size=d["body"])
    button_font = tkfont.Font(family="Segoe UI", size=d["body"])
    body_font = tkfont.Font(family="Segoe UI", size=d["body"])
    # One size step down from body text — secondary/status text reads as
    # secondary by more than color alone, the same way the heading font
    # reads as a heading by more than just being un-colored.
    detail_font = tkfont.Font(family="Segoe UI", size=d["detail"])
    # A large standalone figure (e.g. a glyph/character count) reads as the
    # primary thing in its panel by size alone, well above heading_font —
    # this is the one role in the type scale that's larger than body text,
    # not smaller.
    title_font = tkfont.Font(family="Segoe UI Semibold", size=d["body"] + 9)

    style.configure(".", background=p["panel_alt"], foreground=p["fg"],
                     fieldbackground=p["entry_bg"])
    style.configure("TFrame", background=p["panel_alt"])
    # Embedded content frame for the font-grid Canvas. The Canvas remains
    # visible below this frame whenever only a few fonts match, so both layers
    # intentionally share canvas_bg to form one uninterrupted browser surface.
    style.configure("Grid.TFrame", background=p["canvas_bg"])
    style.configure("TLabelframe", background=p["panel_alt"], foreground=p["fg"],
                     bordercolor=p["border"], borderwidth=1, relief="solid")
    style.configure("TLabelframe.Label", background=p["panel_alt"], foreground=p["fg"],
                     font=heading_font)
    style.configure("TLabel", background=p["panel_alt"], foreground=p["fg"], font=body_font)
    # Chrome variant — for fixed UI regions (the Log panel) that read as
    # part of the app's frame rather than page content, sitting at the
    # darker `bg` tier instead of the workspace `panel_alt` tier.
    style.configure("Chrome.TLabelframe", background=p["bg"], foreground=p["fg"],
                     bordercolor=p["sash"], borderwidth=1, relief="solid")
    style.configure("Chrome.TLabelframe.Label", background=p["bg"], foreground=p["muted_fg"],
                     font=heading_font)
    # Semantic label styles — the design system's type scale below Heading:
    # Intro (a page's opening explainer — full-strength body text, not
    # muted, since it's the primary orientation copy for the tab, not an
    # aside) and four small/muted "detail" roles for secondary text and
    # state feedback (Hint = neutral secondary, Warn/Danger/Success = a
    # state actually being reported, not just dimmed for its own sake).
    style.configure("Intro.TLabel", background=p["panel_alt"], foreground=p["fg"])
    # Title — a large standalone figure (Generator's font-contents character
    # count is the first user), plain fg rather than accent: accent stays
    # reserved for live/selected/primary-action state, and this is neither.
    style.configure("Title.TLabel", background=p["panel_alt"], foreground=p["fg"], font=title_font)
    style.configure("Hint.TLabel", background=p["panel_alt"], foreground=p["hint"], font=detail_font)
    style.configure("Warn.TLabel", background=p["panel_alt"], foreground=p["warn"], font=detail_font)
    style.configure("Danger.TLabel", background=p["panel_alt"], foreground=p["danger"], font=detail_font)
    style.configure("Success.TLabel", background=p["panel_alt"], foreground=p["success"], font=detail_font)
    # Hyperlink text (e.g. Credits' reference links) — the palette's cool
    # "info/focus on non-primary controls" tone, never the warm accent,
    # which stays reserved for live/selected state per this module's own
    # discipline. Underlined like a web link; brightens to accent_glow on
    # hover via ttk's 'active' pointer state (set manually in the caller's
    # <Enter>/<Leave> bindings — plain ttk::label has no built-in hover
    # tracking the way Button/Checkbutton do).
    link_font = tkfont.Font(family="Segoe UI", size=d["detail"], underline=1)
    style.configure("Link.TLabel", background=p["panel_alt"], foreground=p["secondary_accent"],
                     font=link_font)
    style.map("Link.TLabel", foreground=[("active", p["accent_glow"])])
    # A credited entry's category line (e.g. "Directly Incorporated Code —
    # Font Mapping and Text Layout") — full-strength text at a small
    # semibold weight, one step stronger than the muted byline/description
    # around it without reaching for a new color the way Link/Badge do.
    category_font = tkfont.Font(family="Segoe UI Semibold", size=d["detail"])
    style.configure("Category.TLabel", background=p["panel_alt"], foreground=p["fg"], font=category_font)
    # Small inline chip — e.g. a license tag sitting next to a credited
    # project's name — one step lighter than the surface so it reads as a
    # label pinned to it, not another paragraph of body text.
    style.configure("Badge.TLabel", background=p["button_bg"], foreground=p["muted_fg"],
                     font=detail_font, padding=(6, 1))
    # Monospace technical references (a file path, a symbol, a format
    # name) — same muted tone as Hint so it doesn't outrank surrounding
    # prose, distinguished only by typeface, the same restraint real
    # documentation uses for inline `code`.
    code_font = tkfont.Font(family="Consolas", size=d["detail"])
    style.configure("Code.TLabel", background=p["panel_alt"], foreground=p["muted_fg"], font=code_font)

    style.configure("TButton", background=p["button_bg"], foreground=p["fg"],
                     bordercolor=p["border"], borderwidth=1, relief="solid",
                     font=button_font, padding=d["button_pad"])
    style.map("TButton",
              background=[("active", p["button_active_bg"]), ("disabled", p["panel_alt"])],
              bordercolor=[("active", p["muted_fg"]), ("disabled", p["border"])],
              foreground=[("disabled", p["disabled_fg"])])
    # Primary action buttons (Generate, Save) get the accent treatment — a
    # solid fill with a lighter accent_glow edge standing in for the soft
    # outer glow a real box-shadow would give a live/primary control.
    style.configure("Accent.TButton", background=p["accent"], foreground=p["select_fg"],
                     bordercolor=p["accent_glow"], borderwidth=1, relief="solid",
                     font=accent_button_font, padding=d["accent_pad"])
    style.map("Accent.TButton",
              background=[("active", p["accent_active"]), ("disabled", p["button_bg"])],
              bordercolor=[("active", p["accent_active"]), ("disabled", p["border"])],
              foreground=[("disabled", p["disabled_fg"])])
    style.configure("Danger.TButton", background=p["button_bg"], foreground=p["danger"],
                    bordercolor=p["danger"], borderwidth=1, relief="solid",
                    font=button_font, padding=d["button_pad"])
    style.map("Danger.TButton",
              background=[("active", p["button_active_bg"]), ("disabled", p["panel_alt"])],
              foreground=[("disabled", p["disabled_fg"])])
    style.configure("TCheckbutton", background=p["panel_alt"], foreground=p["fg"])
    style.map("TCheckbutton", foreground=[("disabled", p["disabled_fg"])],
              background=[("active", p["panel_alt"])])
    style.configure("TRadiobutton", background=p["panel_alt"], foreground=p["fg"])
    style.map("TRadiobutton", foreground=[("disabled", p["disabled_fg"])],
              background=[("active", p["panel_alt"])])
    _apply_custom_indicators(style, p, root)
    _apply_output_option_styles(style, p, root)

    style.configure("TEntry", fieldbackground=p["entry_bg"], foreground=p["entry_fg"],
                     insertcolor=p["fg"], bordercolor=p["border"], borderwidth=1)
    style.map("TEntry", foreground=[("disabled", p["disabled_fg"])],
              fieldbackground=[("disabled", p["panel_alt"])],
              bordercolor=[("focus", p["accent"])])
    style.configure("TCombobox", fieldbackground=p["entry_bg"], foreground=p["entry_fg"],
                     background=p["button_bg"], arrowcolor=p["fg"], bordercolor=p["border"])
    style.map("TCombobox", fieldbackground=[("readonly", p["entry_bg"]), ("disabled", p["panel_alt"])],
              foreground=[("disabled", p["disabled_fg"])],
              bordercolor=[("focus", p["accent"])])
    style.configure("TSpinbox", fieldbackground=p["entry_bg"], foreground=p["entry_fg"],
                     arrowcolor=p["fg"], bordercolor=p["border"])
    style.map("TSpinbox", bordercolor=[("focus", p["accent"])])
    style.configure("TProgressbar", background=p["accent"], troughcolor=p["entry_bg"],
                     bordercolor=p["border"], thickness=6)
    _apply_flat_scrollbars(style, p)
    style.configure("Treeview", background=p["entry_bg"], fieldbackground=p["entry_bg"],
                     foreground=p["fg"], bordercolor=p["border"])
    style.map("Treeview", background=[("selected", p["select_bg"])],
              foreground=[("selected", p["select_fg"])])
    style.configure("Treeview.Heading", background=p["button_bg"], foreground=p["fg"],
                     font=heading_font)

    try:
        root.configure(bg=p["bg"])
    except tk.TclError:
        pass

    for widget in tk_widgets:
        if widget is None:
            continue
        options = {}
        cls = widget.winfo_class()
        for opt, palette_key in _TK_WIDGET_OPTION_MAP.items():
            options[opt] = p[palette_key]
        if cls == "Text" or cls == "Listbox":
            options["bg"] = p["log_bg"] if cls == "Text" else p["listbox_bg"]
            options["fg"] = p["log_fg"] if cls == "Text" else p["listbox_fg"]
            options["font"] = (("Consolas", d["body"]) if cls == "Text"
                               else ("Segoe UI", d["body"]))
        elif cls == "Canvas":
            options["bg"] = p["canvas_bg"]
        try:
            widget.configure(**{k: v for k, v in options.items() if k in widget.keys()})
        except tk.TclError:
            pass

    apply_title_bar_theme(root)


def configure_text_tags(text_widget: tk.Text) -> None:
    """Standard semantic tags for a classic Text widget (e.g. the Log
    panel) — 'danger'/'warn'/'success'/'hint', the same four roles as the
    Hint/Warn/Danger/Success ttk label styles above, so a line of log
    output can carry the same meaning a status label would instead of
    every line reading identically regardless of outcome."""
    p = PALETTE
    text_widget.tag_configure("danger", foreground=p["danger"])
    text_widget.tag_configure("warn", foreground=p["warn"])
    text_widget.tag_configure("success", foreground=p["success"])
    text_widget.tag_configure("hint", foreground=p["hint"])


def build_legend(parent: tk.Misc, entries: list[tuple[str, str]], *, columns: int = 1) -> ttk.Frame:
    """A small color-swatch + label key, e.g. "white = match, blue = missing,
    red = extra ink" — for presenting a fixed set of color meanings as a real
    legend instead of dense inline prose glued onto a status label.

    `entries` is a list of (swatch color, label) pairs. Returns an unpacked
    `ttk.Frame`; the caller packs/grids it like any other widget, and can
    lay entries across `columns` if a single column runs too tall.
    """
    p = palette()
    legend = ttk.Frame(parent)
    for index, (swatch_color, label) in enumerate(entries):
        row = ttk.Frame(legend)
        row.grid(row=index // columns, column=index % columns, sticky='w', padx=(0, 14), pady=1)
        swatch = tk.Frame(row, width=11, height=11, background=swatch_color,
                           highlightthickness=1, highlightbackground=p['border'])
        swatch.pack(side='left', padx=(0, 6))
        ttk.Label(row, text=label, style='Hint.TLabel').pack(side='left')
    return legend


def _hex_to_colorref(hex_color: str) -> int:
    """DWM window-attribute colors are `COLORREF`s — 0x00BBGGRR, the
    reverse byte order from a normal #RRGGBB hex string."""
    hex_color = hex_color.lstrip("#")
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return (b << 16) | (g << 8) | r


def apply_title_bar_theme(root: tk.Misc) -> None:
    """Color the native Windows title bar to match the app instead of
    leaving it the OS's default light chrome, which clashes hard against
    the near-black window below it. Tkinter doesn't draw the title bar
    itself (it's OS-drawn window chrome) so this goes through DWM window
    attributes directly rather than replacing the native frame — keeps
    real window dragging/snapping/minimize/taskbar-thumbnail behavior
    intact, unlike a borderless-window-plus-custom-chrome approach would.

    `DWMWA_CAPTION_COLOR`/`DWMWA_TEXT_COLOR` (exact-color titlebar, Windows
    11 22000+) are tried first; `DWMWA_USE_IMMERSIVE_DARK_MODE` (dark-mode
    titlebar with the OS's own dark gray, Windows 10 20H1+) is the
    fallback so older Windows 10 still gets *a* dark titlebar even without
    an exact color match. Best-effort only — this is cosmetic, so any
    failure (non-Windows, an even older Windows build, DWM unavailable)
    is silently ignored rather than breaking the app over a title bar.
    """
    import sys
    if sys.platform != "win32":
        return
    try:
        import ctypes
        # The window needs to actually be realized (a real HWND with a
        # frame) before DWM will accept attribute changes for it — a
        # caller that applies this right after creating the root window,
        # before its own first update, would otherwise silently no-op.
        root.update_idletasks()
        # winfo_id() returns the drawing-surface child HWND on Windows, not
        # the actual framed top-level window DWM attributes apply to —
        # GetParent() walks up to the real frame HWND.
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        dwmapi = ctypes.windll.dwmapi

        dark_mode = ctypes.c_int(1)
        dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark_mode), ctypes.sizeof(dark_mode))

        caption_color = ctypes.c_int(_hex_to_colorref(PALETTE["bg"]))
        dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(caption_color), ctypes.sizeof(caption_color))
        text_color = ctypes.c_int(_hex_to_colorref(PALETTE["fg"]))
        dwmapi.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(text_color), ctypes.sizeof(text_color))
    except Exception:
        pass
