"""The one color-picker UI every tab that lets the user choose a color uses:
ASCII Art, Forza Font Text, Composer, and Layer Effects. Previously each of
those had grown its own bespoke picker (a plain swatch + OS dialog button in
the first two, a full HSB-square/hex/RGB/manufacturer-colors panel in
Composer, a near-identical but separately-implemented HSB-square/hex panel
in Layer Effects) that drifted out of sync with each other. This is a single
`ttk.Frame` subclass all four now build once and embed.

Two ways a tab can use it, matching the two kinds of "color" that exist in
this app:

- Self-drive (`settings_key` set): the widget owns one color and persists it
  under that key via `gui_settings`, restored on the next launch. This is
  what ASCII Art and Forza Font Text want -- each has exactly one "current"
  color that isn't part of any saved project.
- External-drive (`get_color`/`on_change` driving something else): the color
  actually lives elsewhere (a composed line's fill slot, a layer's `.color`)
  and the owning tab is the source of truth. The widget just renders
  whatever `get_color()` currently returns and calls `on_change(rgba)` when
  the user picks a new one; the owner writes it back into its own model and
  calls `.sync()` if anything besides this widget needs to know. Composer
  and Layer Effects use this mode. `get_color` returning None means "nothing
  is selected to edit" -- the widget shows a disabled placeholder instead of
  dead controls.

Saved (named) and Recent colors are the one part of this that is *not*
per-tab: they are a single shared library (`gui_settings`'s `saved_colors`/
`recent_colors`), and every open picker instance reflects changes made
through any other one in the same session via `_LIVE_INSTANCES` -- otherwise
saving a color in ASCII Art wouldn't show up in Forza Font Text's already-
built picker until an app restart.
"""

from __future__ import annotations

import sys
import weakref
from pathlib import Path
from typing import Callable

import tkinter as tk
from tkinter import colorchooser, ttk

from PIL import Image, ImageTk

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import gui_settings  # noqa: E402
import gui_theme  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from forza_writer import forza_colors  # noqa: E402

RGBA = tuple[int, int, int, int]

_SB_SIZE = 130
_HUE_STRIP_WIDTH = 18
_SWATCH_COLUMNS = 3  # named swatches are wider than the old bare color squares

# (color, name) -- a swatch alone never appears without its name alongside it,
# in this preset row or in Saved/Recent below (see _named_swatch).
_BASIC_PRESET_COLORS: list[tuple[RGBA, str]] = [
    ((242, 243, 245, 255), 'Off White'), ((114, 118, 125, 255), 'Steel Gray'),
    ((23, 24, 26, 255), 'Jet Black'), ((226, 69, 60, 255), 'Red'),
    ((236, 138, 46, 255), 'Orange'), ((240, 201, 58, 255), 'Yellow'),
    ((95, 168, 90, 255), 'Green'), ((63, 127, 209, 255), 'Blue'),
    ((75, 79, 176, 255), 'Indigo'), ((138, 79, 176, 255), 'Purple'),
    ((255, 95, 162, 255), 'Pink'), ((32, 196, 180, 255), 'Teal'),
]


def _rgba_to_hex(color: RGBA) -> str:
    r, g, b = color[0], color[1], color[2]
    return f'#{r:02x}{g:02x}{b:02x}'


def _readable_fg_for(hex_color: str) -> str:
    r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return '#17181a' if luminance > 140 else '#f2f3f5'


# The hue strip is a fixed, content-independent gradient (same _SB_SIZE x
# _HUE_STRIP_WIDTH image for every instance) -- one per top-level window,
# shared by every ColorPickerWidget inside it, rather than one fresh native
# Tk image per widget instance. A window that opens several of these (every
# real launch of this app builds at least four) was otherwise creating that
# many redundant images for pixel-identical content; combined with the SB
# square (see _redraw_sb_square's own docstring on the same underlying
# issue), that was enough distinct Tk image objects piling up over a long
# process to blow past Windows' GDI object quota and crash natively. Keyed
# by a weak reference so an entry disappears on its own once the window
# it belongs to is actually destroyed, instead of accumulating forever.
_HUE_PHOTO_CACHE: 'weakref.WeakKeyDictionary' = weakref.WeakKeyDictionary()


def _shared_hue_photo(widget: tk.Widget) -> ImageTk.PhotoImage:
    toplevel = widget.winfo_toplevel()
    photo = _HUE_PHOTO_CACHE.get(toplevel)
    if photo is None:
        strip = forza_colors.hue_strip_array(_SB_SIZE, _HUE_STRIP_WIDTH)
        photo = ImageTk.PhotoImage(Image.fromarray(strip, 'RGB'))
        _HUE_PHOTO_CACHE[toplevel] = photo
    return photo


class ColorPickerWidget(ttk.Frame):
    # Every live instance, so saving/deleting a shared (named or recent)
    # color in one tab's picker is reflected in every other tab's
    # already-built picker in the same session, not just after a restart.
    _LIVE_INSTANCES: list['ColorPickerWidget'] = []

    def __init__(
        self,
        parent,
        *,
        initial: RGBA = (255, 255, 255, 255),
        on_change: Callable[[RGBA], None] | None = None,
        settings_key: str | None = None,
        get_color: Callable[[], RGBA | None] | None = None,
        status_var: tk.StringVar | None = None,
        extra_content: Callable[[ttk.Widget], None] | None = None,
        title: str = 'Color',
    ):
        super().__init__(parent)
        self._on_change = on_change
        self._settings_key = settings_key
        self._get_color_external = get_color
        self._picker_hue = 0.0
        self._enabled = True
        self._sb_photo = None  # created once, updated via .paste() -- see _redraw_sb_square

        if settings_key is not None:
            saved = gui_settings.load_settings().get(settings_key)
            self._color: RGBA = tuple(saved) if saved else initial
        else:
            self._color = initial

        self._saved_colors: dict[str, RGBA] = {}
        self._recent_colors: list[RGBA] = []
        self._load_library()

        self._build(status_var, title, extra_content)
        ColorPickerWidget._LIVE_INSTANCES.append(self)
        self.bind('<Destroy>', self._on_destroy)
        self._redraw_all()

    # -- public API -----------------------------------------------------

    @property
    def color(self) -> RGBA | None:
        if self._get_color_external is not None:
            return self._get_color_external()
        return self._color

    def sync(self) -> None:
        """Re-pull the current color (external-drive mode) and redraw.
        Call this whenever something outside the widget's own controls
        might have changed what `get_color` returns -- a different line,
        slot, or layer got selected."""
        self._redraw_all()

    def set_color(self, rgba: RGBA, *, record_recent: bool = True) -> None:
        """Programmatic color change, as if the user picked it -- used by
        both the widget's own controls and by preset/saved/recent clicks."""
        if not self._enabled:
            return
        rgba = tuple(int(c) for c in rgba)
        if self._get_color_external is None:
            self._color = rgba
            if self._settings_key is not None:
                gui_settings.update_settings({self._settings_key: list(rgba)})
        if record_recent:
            self._push_recent(rgba)
        self._redraw_all()
        if self._on_change is not None:
            self._on_change(rgba)

    # -- construction -----------------------------------------------------

    def _build(self, status_var, title, extra_content) -> None:
        if status_var is not None:
            ttk.Label(self, textvariable=status_var, style='Hint.TLabel').pack(
                anchor='w', pady=(0, 4))
        elif title:
            ttk.Label(self, text=gui_theme.hud_label(title)).pack(anchor='w', pady=(0, 4))

        row = ttk.Frame(self)
        row.pack(fill='x')
        self._sb_canvas = tk.Canvas(row, width=_SB_SIZE, height=_SB_SIZE,
                                     highlightthickness=1, cursor='crosshair')
        self._sb_canvas.pack(side='left')
        self._sb_canvas.bind('<Button-1>', self._on_sb_pick)
        self._sb_canvas.bind('<B1-Motion>', self._on_sb_pick)
        self._sb_canvas.bind('<ButtonRelease-1>', self._commit_gesture_recent)

        self._hue_canvas = tk.Canvas(row, width=_HUE_STRIP_WIDTH, height=_SB_SIZE,
                                      highlightthickness=1, cursor='sb_v_double_arrow')
        self._hue_canvas.pack(side='left', padx=(6, 0))
        self._hue_canvas.bind('<Button-1>', self._on_hue_pick)
        self._hue_canvas.bind('<B1-Motion>', self._on_hue_pick)
        self._hue_canvas.bind('<ButtonRelease-1>', self._commit_gesture_recent)
        self._hue_photo = _shared_hue_photo(self)
        self._hue_canvas.create_image(0, 0, anchor='nw', image=self._hue_photo)

        swatch_col = ttk.Frame(row)
        swatch_col.pack(side='left', padx=(10, 0), fill='y')
        self._swatch = tk.Label(swatch_col, width=6, height=3, relief='solid',
                                 borderwidth=1, background='#ffffff')
        self._swatch.pack(anchor='n')
        self._pick_btn = ttk.Button(swatch_col, text='Pick… (OS)', command=self._pick_native)
        self._pick_btn.pack(anchor='n', pady=(6, 0))

        fields = ttk.Frame(self)
        fields.pack(fill='x', pady=(8, 4))
        self._hex_var = tk.StringVar()
        self._r_var = tk.StringVar()
        self._g_var = tk.StringVar()
        self._b_var = tk.StringVar()
        self._alpha_var = tk.StringVar(value='255')

        ttk.Label(fields, text='Hex').grid(row=0, column=0, sticky='w', pady=2)
        hex_entry = ttk.Entry(fields, textvariable=self._hex_var, width=9)
        hex_entry.grid(row=0, column=1, sticky='w', padx=(4, 0))
        hex_entry.bind('<Return>', self._commit_hex)
        hex_entry.bind('<FocusOut>', self._commit_hex)

        ttk.Label(fields, text='RGB').grid(row=1, column=0, sticky='w', pady=2)
        rgb_holder = ttk.Frame(fields)
        rgb_holder.grid(row=1, column=1, sticky='w', padx=(4, 0))
        for var in (self._r_var, self._g_var, self._b_var):
            entry = ttk.Entry(rgb_holder, textvariable=var, width=4)
            entry.pack(side='left', padx=(0, 3))
            entry.bind('<Return>', self._commit_rgb)
            entry.bind('<FocusOut>', self._commit_rgb)

        ttk.Label(fields, text='Alpha').grid(row=2, column=0, sticky='w', pady=2)
        alpha_entry = ttk.Entry(fields, textvariable=self._alpha_var, width=4)
        alpha_entry.grid(row=2, column=1, sticky='w', padx=(4, 0))
        alpha_entry.bind('<Return>', self._commit_rgb)
        alpha_entry.bind('<FocusOut>', self._commit_rgb)

        # Every representation of the current color, all four tabs, always
        # in agreement: this reads through forza_colors.describe_color --
        # the one conversion implementation everything in the app shares --
        # and is refreshed from the same place every commit path (drag,
        # hex/RGB entry, native dialog, preset/saved/recent click) already
        # funnels through: _redraw_all.
        readout = ttk.Frame(self)
        readout.pack(fill='x', pady=(0, 6))
        self._hsl_var = tk.StringVar()
        self._hsb_var = tk.StringVar()
        self._forza_var = tk.StringVar()

        def value_row(row_i, label, var):
            ttk.Label(readout, text=label).grid(row=row_i, column=0, sticky='w', padx=(0, 6), pady=2)
            ttk.Entry(readout, textvariable=var, width=22, state='readonly').grid(
                row=row_i, column=1, sticky='w')

        value_row(0, 'HSL', self._hsl_var)
        value_row(1, 'HSB', self._hsb_var)
        value_row(2, 'Forza H,S,B', self._forza_var)

        presets = ttk.Frame(self)
        presets.pack(fill='x', pady=(2, 6))
        for i, (color, name) in enumerate(_BASIC_PRESET_COLORS):
            cell = self._named_swatch(presets, color, name, on_click=lambda c=color: self.set_color(c))
            cell.grid(row=i // _SWATCH_COLUMNS, column=i % _SWATCH_COLUMNS, padx=2, pady=2)

        saved_frame = ttk.LabelFrame(self, text=gui_theme.hud_label('Saved Colors'))
        saved_frame.pack(fill='x', pady=(0, 6))
        save_row = ttk.Frame(saved_frame)
        save_row.pack(fill='x', padx=6, pady=(6, 2))
        self._save_name_var = tk.StringVar()
        ttk.Entry(save_row, textvariable=self._save_name_var, width=14).pack(side='left')
        self._save_btn = ttk.Button(save_row, text='Save current', command=self._save_current_as)
        self._save_btn.pack(side='left', padx=(4, 0))
        self._saved_grid = ttk.Frame(saved_frame)
        self._saved_grid.pack(fill='x', padx=6, pady=(2, 4))
        ttk.Label(saved_frame, text='Enter/click to apply. Delete key or right-click to remove.',
                  style='Hint.TLabel').pack(anchor='w', padx=6, pady=(0, 6))

        recent_frame = ttk.Frame(self)
        recent_frame.pack(fill='x', pady=(0, 6))
        ttk.Label(recent_frame, text=gui_theme.hud_label('Recently Used')).pack(anchor='w')
        self._recent_row = ttk.Frame(recent_frame)
        self._recent_row.pack(fill='x', pady=(2, 0))

        if extra_content is not None:
            extra_content(self)

    # -- library persistence ---------------------------------------------

    def _load_library(self) -> None:
        settings = gui_settings.load_settings()
        self._saved_colors = {name: tuple(rgba) for name, rgba in settings['saved_colors'].items()}
        self._recent_colors = [tuple(c) for c in settings['recent_colors']]

    def _persist_library(self) -> None:
        gui_settings.update_settings({
            'saved_colors': {name: list(rgba) for name, rgba in self._saved_colors.items()},
            'recent_colors': [list(c) for c in self._recent_colors],
        })

    def _push_recent(self, rgba: RGBA) -> None:
        self._recent_colors = [c for c in self._recent_colors if c != rgba]
        self._recent_colors.insert(0, rgba)
        self._recent_colors = self._recent_colors[:gui_settings.MAX_RECENT_COLORS]
        self._persist_library()
        self._broadcast_library_change()

    def _save_current_as(self) -> None:
        color = self.color
        if color is None:
            return
        name = self._save_name_var.get().strip()
        if not name:
            return
        self._saved_colors[name[:gui_settings.MAX_SAVED_COLOR_NAME_LEN]] = tuple(color)
        self._save_name_var.set('')
        self._persist_library()
        self._redraw_swatches()  # _broadcast_library_change only reaches *other* instances
        self._broadcast_library_change()

    def _delete_saved(self, name: str) -> None:
        self._saved_colors.pop(name, None)
        self._persist_library()
        self._redraw_swatches()  # _broadcast_library_change only reaches *other* instances
        self._broadcast_library_change()

    def _broadcast_library_change(self) -> None:
        for inst in list(ColorPickerWidget._LIVE_INSTANCES):
            if inst is self or not inst.winfo_exists():
                continue
            inst._saved_colors = dict(self._saved_colors)
            inst._recent_colors = list(self._recent_colors)
            inst._redraw_swatches()

    def _on_destroy(self, _event) -> None:
        if self in ColorPickerWidget._LIVE_INSTANCES:
            ColorPickerWidget._LIVE_INSTANCES.remove(self)

    # -- picker interactions -----------------------------------------------

    def _on_sb_pick(self, event):
        if self.color is None:
            return
        x = max(0, min(_SB_SIZE, event.x))
        y = max(0, min(_SB_SIZE, event.y))
        saturation = x / _SB_SIZE
        brightness = 1.0 - y / _SB_SIZE
        rgb = forza_colors.forza_hsb_to_rgb(self._picker_hue, saturation, brightness)
        self.set_color((rgb.r, rgb.g, rgb.b, self._read_alpha()), record_recent=False)

    def _on_hue_pick(self, event):
        current = self.color
        if current is None:
            return
        y = max(0, min(_SB_SIZE, event.y))
        hue = y / _SB_SIZE
        # Set before set_color, not after: at S=0 (gray/white/black) the
        # resulting RGB can't encode the new hue at all, so the next redraw's
        # "hold hue steady for grayscale" fallback would otherwise read back
        # the *previous* hue and snap the strip's marker back to where it
        # was -- dragging the hue strip on a white swatch would do nothing.
        self._picker_hue = hue
        _, saturation, brightness = forza_colors.rgb_to_forza_hsb(*current[:3])
        rgb = forza_colors.forza_hsb_to_rgb(hue, saturation, brightness)
        self.set_color((rgb.r, rgb.g, rgb.b, self._read_alpha()), record_recent=False)

    def _commit_gesture_recent(self, _event=None):
        """Record one color per drag gesture, not every drag pixel."""
        current = self.color
        if current is not None:
            self._push_recent(current)
            self._redraw_swatches()

    def _read_alpha(self) -> int:
        try:
            return max(0, min(255, int(self._alpha_var.get())))
        except ValueError:
            return 255

    def _commit_hex(self, _event=None):
        rgb = forza_colors.hex_to_rgb(self._hex_var.get())
        if rgb is None:
            return
        self.set_color((rgb.r, rgb.g, rgb.b, self._read_alpha()))

    def _commit_rgb(self, _event=None):
        try:
            r = max(0, min(255, int(self._r_var.get())))
            g = max(0, min(255, int(self._g_var.get())))
            b = max(0, min(255, int(self._b_var.get())))
        except ValueError:
            return
        self.set_color((r, g, b, self._read_alpha()))

    def _pick_native(self):
        current = self.color
        if current is None:
            return
        _, hex_color = colorchooser.askcolor(color=_rgba_to_hex(current), title='Choose a color')
        if not hex_color:
            return
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        self.set_color((r, g, b, 255))

    # -- redraw -----------------------------------------------------------

    def _redraw_all(self) -> None:
        color = self.color
        self._enabled = color is not None
        state = 'normal' if self._enabled else 'disabled'
        for widget in (self._pick_btn, self._save_btn):
            widget.configure(state=state)
        self._sb_canvas.configure(cursor='crosshair' if self._enabled else 'arrow')
        self._hue_canvas.configure(cursor='sb_v_double_arrow' if self._enabled else 'arrow')

        if color is None:
            self._sb_canvas.delete('all')
            self._sb_photo = None  # the image item was just deleted with everything else
            self._hue_canvas.delete('marker')
            self._swatch.configure(background='#808080')
            for var in (self._hex_var, self._r_var, self._g_var, self._b_var,
                        self._hsl_var, self._hsb_var, self._forza_var):
                var.set('')
            self._redraw_swatches()
            return

        r, g, b, a = color
        self._swatch.configure(background=_rgba_to_hex(color))
        self._hex_var.set(_rgba_to_hex(color))
        self._r_var.set(str(r))
        self._g_var.set(str(g))
        self._b_var.set(str(b))
        self._alpha_var.set(str(a))

        formats = forza_colors.describe_color(r, g, b)
        self._hsl_var.set(f'{formats.hsl_h:.1f}°  {formats.hsl_s:.1f}%  {formats.hsl_l:.1f}%')
        self._hsb_var.set(f'{formats.hsb_h:.1f}°  {formats.hsb_s:.1f}%  {formats.hsb_b:.1f}%')
        self._forza_var.set(f'{formats.forza_h:.3f}  {formats.forza_s:.3f}  {formats.forza_b:.3f}')

        _hue, saturation, brightness = forza_colors.rgb_to_forza_hsb(r, g, b)
        # Hold the picker's displayed hue steady for near-grayscale colors
        # rather than jumping it to whatever's arbitrary at S~0 -- matches
        # how a standard SB-square picker behaves.
        hue = _hue if saturation > 0.01 else self._picker_hue
        self._redraw_sb_square(hue, saturation, brightness)
        self._redraw_swatches()

    def _redraw_sb_square(self, hue: float, saturation: float, brightness: float) -> None:
        self._picker_hue = hue
        square = forza_colors.sb_square_array(hue, _SB_SIZE)
        image = Image.fromarray(square, 'RGB')
        if self._sb_photo is None:
            # Created once and updated in place via .paste() below on every
            # later redraw, rather than a fresh PhotoImage per redraw -- a
            # picker instance created and briefly touched hundreds of times
            # over a long-running process (the GUI test suite, but also just
            # a long real session with lots of color tweaking) was piling up
            # enough distinct Tk image objects to blow past Windows' GDI
            # object quota, which surfaces as a hard native crash, not a
            # normal Python exception.
            self._sb_photo = ImageTk.PhotoImage(image)
            self._sb_canvas.create_image(0, 0, anchor='nw', image=self._sb_photo, tags='sb_bg')
        else:
            self._sb_photo.paste(image)
        self._sb_canvas.delete('marker')
        cx = saturation * _SB_SIZE
        cy = (1.0 - brightness) * _SB_SIZE
        radius = 5
        self._sb_canvas.create_oval(cx - radius, cy - radius, cx + radius, cy + radius,
                                     outline='#ffffff', width=2, tags='marker')
        self._sb_canvas.create_oval(cx - radius, cy - radius, cx + radius, cy + radius,
                                     outline='#000000', width=1, tags='marker')
        self._hue_canvas.delete('marker')
        hy = hue * _SB_SIZE
        self._hue_canvas.create_line(0, hy, _HUE_STRIP_WIDTH, hy, fill='#ffffff', width=3, tags='marker')
        self._hue_canvas.create_line(0, hy, _HUE_STRIP_WIDTH, hy, fill='#000000', width=1, tags='marker')

    def _named_swatch(self, parent, color: RGBA, name: str, *,
                       on_click, on_delete=None) -> tk.Button:
        """One color sample AND its human-readable name as a single
        Tk Button -- never a bare colored square. A real Button (not a
        Label with a click binding) is what makes this Tab-reachable and
        Space-activatable for free (Tk's own default Button binding);
        `<Return>` is bound explicitly too, since classic tk.Button doesn't
        do that on its own the way ttk.Button does. `on_delete`, when
        given, is also bound to the Delete key, not just the mouse-only
        right-click, so removing a saved color doesn't require a mouse."""
        hexc = _rgba_to_hex(color)
        label = name if len(name) <= 11 else name[:10] + '…'
        btn = tk.Button(
            parent, text=label, background=hexc, foreground=_readable_fg_for(hexc),
            activebackground=hexc, activeforeground=_readable_fg_for(hexc),
            relief='raised', borderwidth=1, padx=3, pady=2, width=10,
            font=('Segoe UI', 8), command=on_click)
        btn.bind('<Return>', lambda _e: on_click())
        if on_delete is not None:
            btn.bind('<Button-3>', lambda _e: on_delete())
            btn.bind('<Delete>', lambda _e: on_delete())
        return btn

    def _redraw_swatches(self) -> None:
        for child in self._saved_grid.winfo_children():
            child.destroy()
        for i, (name, color) in enumerate(self._saved_colors.items()):
            btn = self._named_swatch(
                self._saved_grid, color, name,
                on_click=lambda c=color: self.set_color(c),
                on_delete=lambda n=name: self._delete_saved(n))
            btn.grid(row=i // _SWATCH_COLUMNS, column=i % _SWATCH_COLUMNS, padx=2, pady=2)

        for child in self._recent_row.winfo_children():
            child.destroy()
        for color in self._recent_colors:
            # Recent colors were never given a name -- the closest thing to
            # one is their own hex code, so that's what's shown.
            btn = self._named_swatch(
                self._recent_row, color, _rgba_to_hex(color),
                on_click=lambda c=color: self.set_color(c, record_recent=False))
            btn.pack(side='left', padx=2)
