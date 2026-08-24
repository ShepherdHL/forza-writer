"""Composer's color picker: the HSB square + hue strip, manufacturer-color pane,
swatches, and recent-colors — split out of composer.py as its own concern.
"""

import json
import queue
import re
import string
import sys
import threading
import unicodedata
import webbrowser
import winreg
import ctypes
from pathlib import Path

import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk

import numpy as np
from PIL import Image, ImageTk

# gen_fontpack.py lives in tools/, alongside this package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from gen_fontpack import (  # noqa: E402
    OUTPUT_MODES,
    build_fontpack,
    glyph_filename,
    pack_dir_for,
    sanitize_prefix,
)
from gen_fabric_project import build_fabric_project, save_project  # noqa: E402
import file_preview  # noqa: E402
import font_preview  # noqa: E402
import gui_settings  # noqa: E402
import gui_theme  # noqa: E402
import glyph_overrides as glyph_overrides_store  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
from forza_writer import alphabets  # noqa: E402
from forza_writer.charset import CATEGORY_ORDER, charset_from_font, is_han_char  # noqa: E402
from forza_writer.export import save as save_composed_json, to_json as composed_to_json  # noqa: E402
from forza_writer.compute_backend import resolve_backend  # noqa: E402
from forza_writer.direct_generate import generate_direct  # noqa: E402
from forza_writer.primitive_fit import (  # noqa: E402
    DEFAULT_RESOLUTION, fit_glyph_with_strategy, inspect_glyph_geometry, placements_to_shapes,
    preview_glyph_mask_options)
from forza_writer import script_detect  # noqa: E402
from forza_writer.text_compose import ALIGNMENTS, compose_text  # noqa: E402
from forza_writer.text_style import FILL_MODES, LineFill, TextStyle  # noqa: E402
from forza_writer import forza_colors  # noqa: E402
from forza_writer.forza_colors import describe_color, forza_hsb_to_rgb, hex_to_rgb, rgb_to_forza_hsb  # noqa: E402
from forza_writer import manufacturer_colors  # noqa: E402
from forza_writer.variable_fonts import (  # noqa: E402
    VariableFontInfo, inspect_variable_font, instantiate_font, variation_slug)

from ..state import (  # noqa: E402
    FONT_EXTENSIONS, FONTS_DIR_SYSTEM, GRID_MAX_TILES, GRID_TILE_GAP, GRID_TILE_SIZE,
    ICON_PATH, LIVE_PREVIEW_SIZE, COMPOSE_PREVIEW_SIZE, OUTPUT_MODE_LABELS, PREVIEW_SIZE,
    SIDEBAR_WIDTH, TABS, TAB_LABELS, _MODE_LABELS, _rgba_to_hex, direct_output_filename,
    enumerate_installed_fonts, is_running_as_administrator, sidebar_tab_text)


class ColorPickerMixin:
    _BASIC_PRESET_COLORS = [
        (242, 243, 245, 255), (114, 118, 125, 255), (23, 24, 26, 255),
        (226, 69, 60, 255), (236, 138, 46, 255), (240, 201, 58, 255), (95, 168, 90, 255),
        (63, 127, 209, 255), (75, 79, 176, 255), (138, 79, 176, 255),
        (255, 95, 162, 255), (32, 196, 180, 255),
    ]
    _MFG_RESULT_CAP = 150
    _SB_SIZE = 150
    _HUE_STRIP_WIDTH = 20

    @staticmethod
    def _sb_square_array(hue: float, size: int) -> np.ndarray:
        """RGB image array, Saturation left->right (0..1) by Brightness
        top->bottom (1..0), at a fixed Hue. Delegates to
        `forza_writer.forza_colors.sb_square_array`, which this method used
        to define directly — pulled out so other picker UIs (e.g. the Layer
        Effects tab) can render the same square without a Tk dependency."""
        return forza_colors.sb_square_array(hue, size)
    @staticmethod
    def _hue_strip_array(length: int, width: int) -> np.ndarray:
        """RGB image array, Hue top->bottom (0..1) at full Saturation/Brightness.
        Delegates to `forza_writer.forza_colors.hue_strip_array`; see
        `_sb_square_array`'s docstring."""
        return forza_colors.hue_strip_array(length, width)
    def _build_compose_hsb_picker(self, parent):
        row = ttk.Frame(parent)
        row.pack(fill='x', padx=6, pady=(0, 4))

        self.compose_sb_canvas = tk.Canvas(row, width=self._SB_SIZE, height=self._SB_SIZE,
                                            highlightthickness=1, cursor='crosshair')
        self.compose_sb_canvas.pack(side='left')
        self.compose_sb_canvas.bind('<Button-1>', self._on_compose_sb_pick)
        self.compose_sb_canvas.bind('<B1-Motion>', self._on_compose_sb_pick)
        self.compose_sb_canvas.bind('<ButtonRelease-1>', self._commit_compose_picker_recent)

        self.compose_hue_canvas = tk.Canvas(row, width=self._HUE_STRIP_WIDTH, height=self._SB_SIZE,
                                             highlightthickness=1, cursor='sb_v_double_arrow')
        self.compose_hue_canvas.pack(side='left', padx=(6, 0))
        self.compose_hue_canvas.bind('<Button-1>', self._on_compose_hue_pick)
        self.compose_hue_canvas.bind('<B1-Motion>', self._on_compose_hue_pick)
        self.compose_hue_canvas.bind('<ButtonRelease-1>', self._commit_compose_picker_recent)

        strip = self._hue_strip_array(self._SB_SIZE, self._HUE_STRIP_WIDTH)
        self._compose_hue_photo = ImageTk.PhotoImage(Image.fromarray(strip, 'RGB'))
        self.compose_hue_canvas.create_image(0, 0, anchor='nw', image=self._compose_hue_photo)

        self._compose_picker_hue = 0.0

        ttk.Label(parent,
                  text='Drag inside the square for Saturation/Brightness, drag the strip for Hue.',
                  style='Hint.TLabel', wraplength=220, justify='left').pack(
            anchor='w', padx=6, pady=(0, 0))
    def _current_compose_color(self) -> tuple | None:
        if self._compose_editing is None:
            return None
        line_index, slot_index = self._compose_editing
        fill = self._compose_line_fills[line_index]
        slot_index = min(slot_index, len(fill['colors']) - 1)
        return fill['colors'][slot_index]
    def _redraw_compose_picker(self, hue: float, saturation: float, brightness: float):
        self._compose_picker_hue = hue
        square = self._sb_square_array(hue, self._SB_SIZE)
        self._compose_sb_photo = ImageTk.PhotoImage(Image.fromarray(square, 'RGB'))
        self.compose_sb_canvas.delete('all')
        self.compose_sb_canvas.create_image(0, 0, anchor='nw', image=self._compose_sb_photo)
        cx = saturation * self._SB_SIZE
        cy = (1.0 - brightness) * self._SB_SIZE
        radius = 5
        self.compose_sb_canvas.create_oval(cx - radius, cy - radius, cx + radius, cy + radius,
                                            outline='#ffffff', width=2)
        self.compose_sb_canvas.create_oval(cx - radius, cy - radius, cx + radius, cy + radius,
                                            outline='#000000', width=1)

        self.compose_hue_canvas.delete('marker')
        hy = hue * self._SB_SIZE
        self.compose_hue_canvas.create_line(0, hy, self._HUE_STRIP_WIDTH, hy, fill='#ffffff',
                                             width=3, tags='marker')
        self.compose_hue_canvas.create_line(0, hy, self._HUE_STRIP_WIDTH, hy, fill='#000000',
                                             width=1, tags='marker')
    def _on_compose_sb_pick(self, event):
        if self._current_compose_color() is None:
            return
        x = max(0, min(self._SB_SIZE, event.x))
        y = max(0, min(self._SB_SIZE, event.y))
        saturation = x / self._SB_SIZE
        brightness = 1.0 - y / self._SB_SIZE
        rgb = forza_hsb_to_rgb(self._compose_picker_hue, saturation, brightness)
        self._set_compose_current_color(
            (rgb.r, rgb.g, rgb.b, self._read_compose_alpha()), record_recent=False)
    def _on_compose_hue_pick(self, event):
        current = self._current_compose_color()
        if current is None:
            return
        y = max(0, min(self._SB_SIZE, event.y))
        hue = y / self._SB_SIZE
        # Set this before _set_compose_current_color, not after: at S=0
        # (white/black/gray) the resulting RGB can't encode the new hue at
        # all, so _refresh_compose_color_panel's "hold the hue steady for
        # grayscale" fallback would otherwise read back the *previous*
        # hue and silently snap the strip's marker back to where it was —
        # dragging the hue strip on a fresh white swatch would do nothing.
        self._compose_picker_hue = hue
        _, saturation, brightness = rgb_to_forza_hsb(*current[:3])
        rgb = forza_hsb_to_rgb(hue, saturation, brightness)
        self._set_compose_current_color(
            (rgb.r, rgb.g, rgb.b, self._read_compose_alpha()), record_recent=False)

    def _commit_compose_picker_recent(self, _event=None):
        """Record one final color per picker gesture, not every drag pixel."""
        current = self._current_compose_color()
        if current is None:
            return
        self._push_compose_recent(current)
        self._refresh_compose_recent()
    def _build_composer_color_panel(self, parent):
        panel = ttk.LabelFrame(parent, text=gui_theme.hud_label('Color'))
        self.compose_color_panel = panel  # packed by _bind_responsive_columns, not here

        self.compose_editing_target_var = tk.StringVar(value='No line selected')
        ttk.Label(panel, textvariable=self.compose_editing_target_var, style='Hint.TLabel').pack(
            anchor='w', padx=6, pady=(6, 4))

        self._build_compose_hsb_picker(panel)

        swatch_row = ttk.Frame(panel)
        swatch_row.pack(fill='x', padx=6, pady=(8, 0))
        self.compose_color_swatch_big = tk.Label(swatch_row, width=6, height=3, relief='solid',
                                                   borderwidth=1, background='#ffffff')
        self.compose_color_swatch_big.pack(side='left')
        ttk.Button(swatch_row, text='Pick… (OS dialog)', command=self._pick_compose_color_native).pack(
            side='left', padx=6)

        grid = ttk.Frame(panel)
        grid.pack(fill='x', padx=6, pady=(10, 4))
        self.compose_hex_var = tk.StringVar()
        self.compose_r_var = tk.StringVar()
        self.compose_g_var = tk.StringVar()
        self.compose_b_var = tk.StringVar()
        self.compose_alpha_var = tk.StringVar(value='255')
        self.compose_hsl_var = tk.StringVar()
        self.compose_hsb_var = tk.StringVar()
        self.compose_forza_var = tk.StringVar()

        def value_row(row_i, label, entries, readonly=False, commit=None):
            ttk.Label(grid, text=label).grid(row=row_i, column=0, sticky='w', padx=(0, 6), pady=2)
            holder = ttk.Frame(grid)
            holder.grid(row=row_i, column=1, sticky='w')
            for var, width in entries:
                entry = ttk.Entry(holder, textvariable=var, width=width,
                                   state='readonly' if readonly else 'normal')
                entry.pack(side='left', padx=(0, 3))
                if commit and not readonly:
                    entry.bind('<Return>', commit)
                    entry.bind('<FocusOut>', commit)

        value_row(0, 'Hex', [(self.compose_hex_var, 9)], commit=self._commit_compose_hex)
        value_row(1, 'RGB', [(self.compose_r_var, 4), (self.compose_g_var, 4), (self.compose_b_var, 4)],
                   commit=self._commit_compose_rgb)
        value_row(2, 'Alpha', [(self.compose_alpha_var, 4)], commit=self._commit_compose_rgb)
        value_row(3, 'HSL', [(self.compose_hsl_var, 22)], readonly=True)
        value_row(4, 'HSB', [(self.compose_hsb_var, 22)], readonly=True)
        value_row(5, 'Forza H,S,B', [(self.compose_forza_var, 22)], readonly=True)

        link = ttk.Label(panel, text="Open Bang's Forza Color Converter ↗", style='Hint.TLabel',
                          cursor='hand2')
        link.pack(anchor='w', padx=6, pady=(4, 8))
        link.bind('<Button-1>', lambda _e: webbrowser.open('https://dxbang.github.io/forza-colors/'))

        tabs_row = ttk.Frame(panel)
        tabs_row.pack(fill='x', padx=6)
        self.compose_pack_tab_labels = {}
        self._compose_pack_tab = 'basic'
        for key, label in (('basic', 'Basic'), ('manufacturer', 'Manufacturer Colors')):
            lbl = tk.Label(tabs_row, text=label, padx=8, pady=3, cursor='hand2')
            lbl.pack(side='left', padx=(0, 2))
            lbl.bind('<Button-1>', lambda _e, k=key: self._show_compose_pack(k))
            self.compose_pack_tab_labels[key] = lbl

        # Fixed-height container, not each pane packed straight into `panel`:
        # Basic is a short swatch grid, Manufacturer Colors is a search box +
        # combobox + 10-row Treeview + caption — several times taller.
        # Packing either pane directly into `panel` made switching between
        # them visibly resize the whole Color panel (and, since this panel
        # sits inside Composer's page-level scroll canvas, the page's own
        # scrollable height) — see the gui-ux audit's Composer example.
        # Locking this container to the taller pane's own natural height
        # means the *contents* change on toggle, not the panel's footprint;
        # the shorter Basic pane just leaves empty space below it, which the
        # audit explicitly allows ("interior content may change or scroll").
        self.compose_pack_body = tk.Frame(panel)
        self.compose_pack_body.pack(fill='both', expand=True, padx=6, pady=(4, 6))

        self.compose_pack_panes = {}
        basic_pane = ttk.Frame(self.compose_pack_body)
        self._build_compose_basic_presets(basic_pane)
        self.compose_pack_panes['basic'] = basic_pane

        mfg_pane = ttk.Frame(self.compose_pack_body)
        self._build_compose_manufacturer_pane(mfg_pane)
        self.compose_pack_panes['manufacturer'] = mfg_pane

        self._refresh_compose_pack_body_size()
        self._style_compose_pack_tabs()
        basic_pane.pack(fill='both', expand=True)

        ttk.Label(panel, text=gui_theme.hud_label('Recently Used')).pack(anchor='w', padx=6, pady=(4, 2))
        self.compose_recent_row = ttk.Frame(panel)
        self.compose_recent_row.pack(fill='x', padx=6, pady=(0, 8))
        self._compose_recent_colors: list[tuple] = []
        self._refresh_compose_recent()
    def _build_compose_basic_presets(self, parent):
        grid = ttk.Frame(parent)
        grid.pack(fill='x')
        for i, color in enumerate(self._BASIC_PRESET_COLORS):
            sw = tk.Label(grid, width=2, relief='sunken', background=_rgba_to_hex(color), cursor='hand2')
            sw.grid(row=i // 6, column=i % 6, padx=2, pady=2)
            sw.bind('<Button-1>', lambda _e, c=color: self._set_compose_current_color(c))
    def _build_compose_manufacturer_pane(self, parent):
        self.compose_mfg_search_var = tk.StringVar()
        ttk.Entry(parent, textvariable=self.compose_mfg_search_var).pack(fill='x')
        self.compose_mfg_search_var.trace_add('write', lambda *_: self._refresh_compose_mfg_results())

        makes = ('All makes',) + manufacturer_colors.all_makes()
        self.compose_mfg_make_var = tk.StringVar(value='All makes')
        self.compose_mfg_make_combo = ttk.Combobox(parent, textvariable=self.compose_mfg_make_var,
                                                     values=makes, state='readonly')
        self.compose_mfg_make_combo.pack(fill='x', pady=(4, 0))
        self.compose_mfg_make_combo.bind('<<ComboboxSelected>>',
                                          lambda _e: self._refresh_compose_mfg_results())

        self.compose_mfg_count_var = tk.StringVar()
        ttk.Label(parent, textvariable=self.compose_mfg_count_var, style='Hint.TLabel').pack(
            anchor='w', pady=(4, 2))

        tree_row = ttk.Frame(parent)
        tree_row.pack(fill='both', expand=True)
        self.compose_mfg_tree = ttk.Treeview(tree_row, columns=('make', 'name', 'type'),
                                              show='headings', height=10)
        self.compose_mfg_tree.heading('make', text='Make')
        self.compose_mfg_tree.column('make', width=88, anchor='w')
        self.compose_mfg_tree.heading('name', text='Colour')
        self.compose_mfg_tree.column('name', width=140, anchor='w')
        self.compose_mfg_tree.heading('type', text='Type')
        self.compose_mfg_tree.column('type', width=76, anchor='w', stretch=False)
        tree_scroll = gui_theme.AutoHideScrollbar(tree_row, orient='vertical',
                                                    command=self.compose_mfg_tree.yview)
        self.compose_mfg_tree.configure(yscrollcommand=tree_scroll.set)
        self.compose_mfg_tree.pack(side='left', fill='both', expand=True)
        tree_scroll.pack(side='right', fill='y')
        self.compose_mfg_tree.bind('<<TreeviewSelect>>', self._on_compose_mfg_select)
        self._register_independent_scroll(self.compose_mfg_tree)

        ttk.Label(parent,
                  text=f'{len(manufacturer_colors.load_all()):,} real manufacturer paints. Each row\'s '
                       'exact hue/saturation/brightness slider notation is in the status line below '
                       'once selected, for reproducing the precise in-game shade.',
                  style='Hint.TLabel', wraplength=220, justify='left').pack(anchor='w', pady=(4, 0))
        ttk.Label(parent,
                  text='Source: GTPlanet — catalogued by Mitcho2001, JaCor653, and MadaraxUchiha.',
                  style='Hint.TLabel', wraplength=220, justify='left').pack(anchor='w', pady=(6, 0))

        self._compose_mfg_rows: list = []
        self._refresh_compose_mfg_results()
    @staticmethod
    def _readable_fg_for(hex_color: str) -> str:
        r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
        luminance = 0.299 * r + 0.587 * g + 0.114 * b
        return '#17181a' if luminance > 140 else '#f2f3f5'
    def _refresh_compose_mfg_results(self):
        term = self.compose_mfg_search_var.get()
        make = self.compose_mfg_make_var.get()
        make = None if make in ('', 'All makes') else make
        results = manufacturer_colors.search(term, make=make)
        total = len(results)
        self.compose_mfg_count_var.set(
            f'{total:,} match(es).' if total <= self._MFG_RESULT_CAP
            else f'Showing {self._MFG_RESULT_CAP} of {total:,} — refine your search.')

        tree = self.compose_mfg_tree
        tree.delete(*tree.get_children())
        self._compose_mfg_rows = results[:self._MFG_RESULT_CAP]
        for i, color in enumerate(self._compose_mfg_rows):
            tag = f'mfg{i}'
            tree.tag_configure(tag, background=color.hex1, foreground=self._readable_fg_for(color.hex1))
            tree.insert('', 'end', iid=str(i), values=(color.make, color.name, color.paint_type),
                        tags=(tag,))
    def _on_compose_mfg_select(self, _event=None):
        selection = self.compose_mfg_tree.selection()
        if not selection:
            return
        index = int(selection[0])
        if index >= len(self._compose_mfg_rows):
            return
        color = self._compose_mfg_rows[index]
        rgb = hex_to_rgb(color.hex1)
        if rgb is None:
            return
        self._set_compose_current_color((rgb.r, rgb.g, rgb.b, 255))
        self.compose_editing_target_var.set(
            f'{self.compose_editing_target_var.get()}  —  H {color.hue}  S {color.saturation}  '
            f'B {color.brightness}')
    def _push_compose_recent(self, rgba: tuple):
        self._compose_recent_colors = [c for c in self._compose_recent_colors if c != rgba]
        self._compose_recent_colors.insert(0, rgba)
        self._compose_recent_colors = self._compose_recent_colors[:10]
    def _refresh_compose_recent(self):
        for child in self.compose_recent_row.winfo_children():
            child.destroy()
        for color in self._compose_recent_colors:
            sw = tk.Label(self.compose_recent_row, width=2, relief='sunken',
                           background=_rgba_to_hex(color), cursor='hand2')
            sw.pack(side='left', padx=2)
            sw.bind('<Button-1>', lambda _e, c=color: self._set_compose_current_color(c, record_recent=False))
    def _refresh_compose_color_panel(self):
        if self._compose_editing is None or self._compose_editing[0] >= len(self._compose_line_fills):
            self.compose_editing_target_var.set('No line selected')
            return
        line_index, slot_index = self._compose_editing
        fill = self._compose_line_fills[line_index]
        slot_index = min(slot_index, len(fill['colors']) - 1)
        color = fill['colors'][slot_index]
        slot_label = f'Stop {slot_index + 1}' if fill['mode'] == 'sequence' else 'Color'
        self.compose_editing_target_var.set(f'Line {line_index + 1} · {slot_label}')

        r, g, b, a = color
        self.compose_color_swatch_big.configure(background=_rgba_to_hex(color))
        self.compose_hex_var.set(_rgba_to_hex(color))
        self.compose_r_var.set(str(r))
        self.compose_g_var.set(str(g))
        self.compose_b_var.set(str(b))
        self.compose_alpha_var.set(str(a))
        formats = describe_color(r, g, b)
        self.compose_hsl_var.set(f'{formats.hsl_h:.1f}°  {formats.hsl_s:.1f}%  {formats.hsl_l:.1f}%')
        self.compose_hsb_var.set(f'{formats.hsb_h:.1f}°  {formats.hsb_s:.1f}%  {formats.hsb_b:.1f}%')
        self.compose_forza_var.set(f'{formats.forza_h:.3f}  {formats.forza_s:.3f}  {formats.forza_b:.3f}')

        # Hold the picker's displayed hue steady for near-grayscale colors
        # (saturation ~0) rather than jumping it to whatever colorsys
        # arbitrarily returns for gray/white/black — matches how every
        # standard SB-square picker behaves.
        picker_hue = formats.forza_h if formats.forza_s > 0.01 else self._compose_picker_hue
        self._redraw_compose_picker(picker_hue, formats.forza_s, formats.forza_b)
    def _read_compose_alpha(self) -> int:
        try:
            return max(0, min(255, int(self.compose_alpha_var.get())))
        except ValueError:
            return 255
    def _commit_compose_hex(self, _event=None):
        rgb = hex_to_rgb(self.compose_hex_var.get())
        if rgb is None:
            return
        self._set_compose_current_color((rgb.r, rgb.g, rgb.b, self._read_compose_alpha()))
    def _commit_compose_rgb(self, _event=None):
        try:
            r = max(0, min(255, int(self.compose_r_var.get())))
            g = max(0, min(255, int(self.compose_g_var.get())))
            b = max(0, min(255, int(self.compose_b_var.get())))
        except ValueError:
            return
        self._set_compose_current_color((r, g, b, self._read_compose_alpha()))
    def _pick_compose_color_native(self):
        current = self._current_compose_color()
        if current is None:
            return
        _, hex_color = colorchooser.askcolor(color=_rgba_to_hex(current), title='Choose a color')
        if not hex_color:
            return
        r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
        self._set_compose_current_color((r, g, b, 255))
    def _set_compose_current_color(self, rgba: tuple, record_recent: bool = True):
        if self._compose_editing is None:
            return
        line_index, slot_index = self._compose_editing
        fill = self._compose_line_fills[line_index]
        slot_index = min(slot_index, len(fill['colors']) - 1)
        fill['colors'][slot_index] = rgba
        swatch = self._compose_swatch_widgets.get((line_index, slot_index))
        if swatch is not None and swatch.winfo_exists():
            swatch.configure(background=_rgba_to_hex(rgba))
        self._refresh_compose_color_panel()
        if record_recent:
            self._push_compose_recent(rgba)
            self._refresh_compose_recent()
