"""The ttk style engine + classic-tk chrome that consumes palette/density
data — this is the "shared component" side of the design system, the
direct analogue of how KFPS's shared QML components consume `Theme.*`
tokens. Kept as one file rather than split further, matching how KFPS
doesn't fragment that consumer side per-theme either; only the *data*
(palettes/, backdrops/) is split per-theme.

Every function here takes the palette/density/palette-key it needs as an
explicit parameter rather than reaching for a module global — this module
(and .indicators, .output_accents, .backdrops) never import the parent
`gui_theme` package, so the dependency graph only ever points one way:
gui_theme/__init__.py -> apply.py -> {indicators, output_accents,
backdrops}. That one-way flow is what keeps CURRENT_PALETTE/PALETTE's
live-mutation semantics correct (see gui_theme/__init__.py's docstring)
and avoids any circular-import ordering footgun between sibling files.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from PIL import ImageTk

from . import backdrops
from .indicators import apply_custom_indicators
from .output_accents import apply_output_option_styles

# ---------------------------------------------------------------------------
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


def apply_theme(root: tk.Misc, style: ttk.Style, tk_widgets: list[tk.Widget], *,
                 palette: dict[str, str], palette_key: str, density: dict) -> None:
    """Apply the palette + full design system to `style` (ttk) and any
    classic tk widgets passed in `tk_widgets` (e.g. a Listbox, Text, or
    Canvas — ttk styling doesn't reach these)."""
    p = palette
    d = density
    style.theme_use("clam")

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
    apply_custom_indicators(style, p, root, palette_key)
    apply_output_option_styles(style, p, root, palette_key)

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
        for opt, palette_key_ in _TK_WIDGET_OPTION_MAP.items():
            options[opt] = p[palette_key_]
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

    apply_title_bar_theme(root, p)


def configure_text_tags(text_widget: tk.Text, palette: dict[str, str]) -> None:
    """Standard semantic tags for a classic Text widget (e.g. the Log
    panel) — 'danger'/'warn'/'success'/'hint', the same four roles as the
    Hint/Warn/Danger/Success ttk label styles above, so a line of log
    output can carry the same meaning a status label would instead of
    every line reading identically regardless of outcome."""
    p = palette
    text_widget.tag_configure("danger", foreground=p["danger"])
    text_widget.tag_configure("warn", foreground=p["warn"])
    text_widget.tag_configure("success", foreground=p["success"])
    text_widget.tag_configure("hint", foreground=p["hint"])


def build_legend(parent: tk.Misc, entries: list[tuple[str, str]], palette: dict[str, str], *,
                  columns: int = 1) -> ttk.Frame:
    """A small color-swatch + label key, e.g. "white = match, blue = missing,
    red = extra ink" — for presenting a fixed set of color meanings as a real
    legend instead of dense inline prose glued onto a status label.

    `entries` is a list of (swatch color, label) pairs. Returns an unpacked
    `ttk.Frame`; the caller packs/grids it like any other widget, and can
    lay entries across `columns` if a single column runs too tall.
    """
    p = palette
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


def apply_title_bar_theme(root: tk.Misc, palette: dict[str, str]) -> None:
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

        caption_color = ctypes.c_int(_hex_to_colorref(palette["bg"]))
        dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(caption_color), ctypes.sizeof(caption_color))
        text_color = ctypes.c_int(_hex_to_colorref(palette["fg"]))
        dwmapi.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(text_color), ctypes.sizeof(text_color))
    except Exception:
        pass


_BACKDROP_CACHE: dict[tuple[str, int, int], "ImageTk.PhotoImage"] = {}


def backdrop_photo_image(theme_key: str, width: int, height: int, palette: dict[str, str],
                          master: tk.Misc) -> "ImageTk.PhotoImage | None":
    """Return a cached PhotoImage of `theme_key`'s backdrop at this size,
    or None if that theme has no backdrop (see backdrops/__init__.py) or
    the size isn't real yet (before Tk has laid the canvas out)."""
    if width <= 0 or height <= 0:
        return None
    builder = backdrops.get_backdrop(theme_key)
    if builder is None:
        return None
    cache_key = (theme_key, width, height)
    cached = _BACKDROP_CACHE.get(cache_key)
    if cached is not None:
        return cached
    image = builder((width, height), palette)
    photo = ImageTk.PhotoImage(image, master=master)
    _BACKDROP_CACHE[cache_key] = photo
    return photo
