"""Composer's color picker: the shared color-picker widget
(`tools/gen_modelbin_gui/color_picker_widget.py` -- the same one ASCII Art,
Forza Font Text, and Layer Effects embed) with two Composer-specific extras
bolted on below it: read-only HSL/HSB/Forza-notation readouts (for
reproducing an exact in-game slider value) and the Manufacturer Colors
browser. Split out of composer.py as its own concern.
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
from tkinter import filedialog, messagebox, ttk

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
from forza_writer.forza_colors import hex_to_rgb  # noqa: E402
from forza_writer import manufacturer_colors  # noqa: E402
from forza_writer.variable_fonts import (  # noqa: E402
    VariableFontInfo, inspect_variable_font, instantiate_font, variation_slug)

from ..color_picker_widget import ColorPickerWidget  # noqa: E402
from ..state import (  # noqa: E402
    FONT_EXTENSIONS, FONTS_DIR_SYSTEM, GRID_MAX_TILES, GRID_TILE_GAP, GRID_TILE_SIZE,
    ICON_PATH, LIVE_PREVIEW_SIZE, COMPOSE_PREVIEW_SIZE, OUTPUT_MODE_LABELS, PREVIEW_SIZE,
    SIDEBAR_WIDTH, TABS, TAB_LABELS, _MODE_LABELS, _rgba_to_hex, direct_output_filename,
    enumerate_installed_fonts, is_running_as_administrator, sidebar_tab_text)


class ColorPickerMixin:
    _MFG_RESULT_CAP = 150

    def _current_compose_color(self) -> tuple | None:
        if self._compose_editing is None:
            return None
        line_index, slot_index = self._compose_editing
        fill = self._compose_line_fills[line_index]
        slot_index = min(slot_index, len(fill['colors']) - 1)
        return fill['colors'][slot_index]

    def _build_composer_color_panel(self, parent):
        panel = ttk.LabelFrame(parent, text=gui_theme.hud_label('Color'))
        self.compose_color_panel = panel  # packed by _bind_responsive_columns, not here

        self.compose_editing_target_var = tk.StringVar(value='No line selected')
        ttk.Label(panel, textvariable=self.compose_editing_target_var, style='Hint.TLabel').pack(
            anchor='w', padx=6, pady=(6, 4))

        self.compose_color_picker = ColorPickerWidget(
            panel, get_color=self._current_compose_color, on_change=self._set_compose_current_color,
            title='', extra_content=self._build_compose_extra_content)
        self.compose_color_picker.pack(fill='both', expand=True, padx=6, pady=(0, 6))

    def _build_compose_extra_content(self, parent):
        """Composer-specific content appended below the shared picker's own
        Saved/Recent sections -- the manufacturer browser doesn't make sense
        on the other tabs that reuse this same widget. The RGB/hex/HSL/HSB/
        Forza-HSB readouts used to be built here too; they're now part of
        ColorPickerWidget itself so every tab gets them, not just this one."""
        link = ttk.Label(parent, text="Open Bang's Forza Color Converter ↗", style='Hint.TLabel',
                          cursor='hand2')
        link.pack(anchor='w', pady=(2, 8))
        link.bind('<Button-1>', lambda _e: webbrowser.open('https://dxbang.github.io/forza-colors/'))

        mfg_frame = ttk.LabelFrame(parent, text=gui_theme.hud_label('Manufacturer Colors'))
        mfg_frame.pack(fill='both', expand=True)
        self._build_compose_manufacturer_pane(mfg_frame)

    def _build_compose_manufacturer_pane(self, parent):
        body = ttk.Frame(parent)
        body.pack(fill='both', expand=True, padx=6, pady=6)

        self.compose_mfg_search_var = tk.StringVar()
        ttk.Entry(body, textvariable=self.compose_mfg_search_var).pack(fill='x')
        self.compose_mfg_search_var.trace_add('write', lambda *_: self._refresh_compose_mfg_results())

        makes = ('All makes',) + manufacturer_colors.all_makes()
        self.compose_mfg_make_var = tk.StringVar(value='All makes')
        self.compose_mfg_make_combo = ttk.Combobox(body, textvariable=self.compose_mfg_make_var,
                                                     values=makes, state='readonly')
        self.compose_mfg_make_combo.pack(fill='x', pady=(4, 0))
        self.compose_mfg_make_combo.bind('<<ComboboxSelected>>',
                                          lambda _e: self._refresh_compose_mfg_results())

        self.compose_mfg_count_var = tk.StringVar()
        ttk.Label(body, textvariable=self.compose_mfg_count_var, style='Hint.TLabel').pack(
            anchor='w', pady=(4, 2))

        tree_row = ttk.Frame(body)
        tree_row.pack(fill='both', expand=True)
        self.compose_mfg_tree = ttk.Treeview(tree_row, columns=('make', 'name', 'type'),
                                              show='headings', height=10)
        self.compose_mfg_tree.heading('make', text='Make')
        self.compose_mfg_tree.column('make', width=88, anchor='w', stretch=False)
        self.compose_mfg_tree.heading('name', text='Colour')
        self.compose_mfg_tree.column('name', width=140, anchor='w', stretch=False)
        self.compose_mfg_tree.heading('type', text='Type')
        self.compose_mfg_tree.column('type', width=76, anchor='w', stretch=False)
        # stretch=False on every column, not just 'type': a stretch=True
        # column silently grows past its configured width to fit its widest
        # cell's actual text (some manufacturer/colour names are long), which
        # used to be invisible -- the old toggle-tab container froze this
        # whole pane's size regardless of what it "wanted". Now that this
        # pane sizes itself naturally inside the responsive color-panel
        # column, an unpinned column reliably blew past the column's
        # available width at the narrow end (caught by the 1920x1080/
        # minimum-width resize audit).
        tree_scroll = gui_theme.AutoHideScrollbar(tree_row, orient='vertical',
                                                    command=self.compose_mfg_tree.yview)
        self.compose_mfg_tree.configure(yscrollcommand=tree_scroll.set)
        self.compose_mfg_tree.pack(side='left', fill='both', expand=True)
        tree_scroll.pack(side='right', fill='y')
        self.compose_mfg_tree.bind('<<TreeviewSelect>>', self._on_compose_mfg_select)
        self._register_independent_scroll(self.compose_mfg_tree)

        ttk.Label(body,
                  text=f'{len(manufacturer_colors.load_all()):,} real manufacturer paints. Each row\'s '
                       'exact hue/saturation/brightness slider notation is in the readouts above once '
                       'selected, for reproducing the precise in-game shade.',
                  style='Hint.TLabel', wraplength=220, justify='left').pack(anchor='w', pady=(4, 0))
        ttk.Label(body,
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
        self.compose_color_picker.set_color((rgb.r, rgb.g, rgb.b, 255))
        self.compose_editing_target_var.set(
            f'{self.compose_editing_target_var.get()}  —  H {color.hue}  S {color.saturation}  '
            f'B {color.brightness}')

    def _refresh_compose_color_panel(self):
        if self._compose_editing is None or self._compose_editing[0] >= len(self._compose_line_fills):
            self.compose_editing_target_var.set('No line selected')
        else:
            line_index, slot_index = self._compose_editing
            fill = self._compose_line_fills[line_index]
            slot_index = min(slot_index, len(fill['colors']) - 1)
            slot_label = f'Stop {slot_index + 1}' if fill['mode'] == 'sequence' else 'Color'
            self.compose_editing_target_var.set(f'Line {line_index + 1} · {slot_label}')
        self.compose_color_picker.sync()  # pulls the new color and redraws every readout itself

    def _set_compose_current_color(self, rgba: tuple):
        """The shared picker's on_change target: it has already redrawn its
        own controls (including every readout) by the time this runs, so
        this only needs to write the new color into Composer's own project
        data and keep the line list's own swatch in sync."""
        if self._compose_editing is None:
            return
        line_index, slot_index = self._compose_editing
        fill = self._compose_line_fills[line_index]
        slot_index = min(slot_index, len(fill['colors']) - 1)
        fill['colors'][slot_index] = rgba
        swatch = self._compose_swatch_widgets.get((line_index, slot_index))
        if swatch is not None and swatch.winfo_exists():
            swatch.configure(background=_rgba_to_hex(rgba))
