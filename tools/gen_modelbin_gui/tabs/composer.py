"""Composer tab: composing/previewing multi-line vinyl text and per-line fills.
The color picker itself lives in color_picker.py, not here.
"""

import colorsys
import json
import queue
import re
import string
import sys
import gen_modelbin_gui
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
from forza_writer import layer_presets  # noqa: E402
from forza_writer.layered_effects_text import compose_layered_text  # noqa: E402
from forza_writer.forza_colors import describe_color, forza_hsb_to_rgb, hex_to_rgb, rgb_to_forza_hsb  # noqa: E402
from forza_writer import manufacturer_colors  # noqa: E402
from forza_writer.variable_fonts import (  # noqa: E402
    VariableFontInfo, inspect_variable_font, instantiate_font, variation_slug)

from ..state import (  # noqa: E402
    FONT_EXTENSIONS, FONTS_DIR_SYSTEM, GRID_MAX_TILES, GRID_TILE_GAP, GRID_TILE_SIZE,
    ICON_PATH, LIVE_PREVIEW_SIZE, COMPOSE_PREVIEW_SIZE, OUTPUT_MODE_LABELS, PREVIEW_SIZE,
    SIDEBAR_WIDTH, TABS, TAB_LABELS, _MODE_LABELS, _rgba_to_hex, direct_output_filename,
    enumerate_installed_fonts, is_running_as_administrator, sidebar_tab_text)


class ComposerTabMixin:
    # Body width (px) below which the Color panel stacks under Compose
    # instead of sitting beside it. Not the point where the two regions
    # merely start to feel tight — the point below which pack's own layout
    # math cannot give both their natural size at all: the compose column's
    # floor (~779px, driven by the 640px preview canvas) plus the Color
    # panel's full width (334px) plus the gutter between them is ~1120px.
    # A lower threshold (980, the original value) let "wide" mode activate
    # up to 140px before that floor, and pack does not protect a
    # non-expanding widget's minimum when the cavity is that tight — it
    # silently compressed the Color panel down to as little as 205px,
    # clipping the Manufacturer Colors table (caught by the 1920x1080
    # resize audit, empirically swept in 25px steps to find the true
    # crossover). Below this threshold, stacking is always safe: both
    # regions simply get the full body width in turn.
    _COMPOSER_WIDE_THRESHOLD = 1130
    _COMPOSER_RESIZE_DEBOUNCE_MS = 120
    _SEQ_MODE_LABELS = (('solid', 'Solid'), ('sequence', 'Sequence'), ('rainbow', 'Rainbow ~'))
    _SEQ_PRESETS = {
        'roygbiv': [(226, 69, 60, 255), (236, 138, 46, 255), (240, 201, 58, 255), (95, 168, 90, 255),
                    (63, 127, 209, 255), (75, 79, 176, 255), (138, 79, 176, 255)],
        # Approximate representative shades, not an authoritative source —
        # easy to swap once exact values matter to you.
        'grayscale': [(0, 0, 0, 255), (54, 69, 79, 255), (128, 128, 128, 255),
                      (132, 136, 132, 255), (255, 255, 255, 255)],
    }
    _MAX_SEQ_STOPS = 12

    def _build_composer_page(self):
        page = ttk.Frame(self.page_container)
        self._pages['composer'] = page
        content = self._build_scroll_shell(page, 'composer')

        ttk.Label(content,
                  text='Type text using an already-generated fontpack\'s glyphs, with real per-glyph '
                       'spacing and a shared baseline — not just glyphs placed side by side, which '
                       'would render e.g. a period the same size as a capital M.',
                  style='Intro.TLabel', wraplength=gui_theme.WRAP_WIDE,
                  justify='left').pack(fill='x', **gui_theme.PAGE_INTRO_PAD)

        # Responsive body: compose text + per-line rows + style bar + preview
        # on the left, the Color panel (DxBang-style value editor + pack
        # tabs) on the right — the same right-hand slot every page with a
        # Color control uses, side by side only when there's real room for
        # both (the preview canvas alone is COMPOSE_PREVIEW_SIZE[0]=640px
        # wide), otherwise stacked with the Color panel below. Without this,
        # a merely-default-sized window clips the Color panel off the right
        # edge of this tab's one vertical scroll region with no horizontal
        # scrollbar to reach it — silently unreachable, not just narrow.
        body = ttk.Frame(content)
        body.pack(fill='both', expand=True, **gui_theme.SECTION_PAD)
        self.compose_body = body

        left_col = ttk.Frame(body)
        self.compose_left_col = left_col

        # Compose arbitrary text from an already-generated fontpack's
        # glyphs, with real per-glyph spacing/size and a shared baseline
        # (forza_writer.text_compose) — not just placing generated glyph
        # files side by side, which would render e.g. a period the same
        # size as a capital M (see text_compose.py's module docstring).
        compose_frame = ttk.LabelFrame(left_col, text=gui_theme.hud_label('Compose Text'))
        compose_frame.pack(fill='both', expand=True)

        compose_pack_row = ttk.Frame(compose_frame)
        compose_pack_row.pack(fill='x', **gui_theme.ROW_PAD)
        ttk.Label(compose_pack_row, text='Fontpack folder:').pack(side='left')
        self.compose_pack_var = tk.StringVar()
        ttk.Entry(compose_pack_row, textvariable=self.compose_pack_var).pack(
            side='left', fill='x', expand=True, padx=4)
        ttk.Button(compose_pack_row, text='Browse...',
                   command=self._pick_compose_pack_dir).pack(side='left', padx=2)
        ttk.Button(compose_pack_row, text='Use current',
                   command=self._use_current_pack_dir).pack(side='left', padx=2)

        self.compose_text_widget = tk.Text(compose_frame, height=4, wrap='word')
        self.compose_text_widget.pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)
        # No dedicated scrollbar (it's a short text-entry field, not an
        # output/display area) — still registered so a wheel-scroll over
        # it scrolls its own content instead of also dragging the page
        # canvas behind it if the typed text ever exceeds 4 lines.
        self._register_independent_scroll(self.compose_text_widget)
        self.compose_text_widget.bind('<KeyRelease>', self._on_compose_text_changed)
        compose_actions_row, self.compose_clear_btn, self.compose_select_all_btn = (
            self._build_text_box_actions_row(compose_frame, self.compose_text_widget))
        compose_actions_row.pack(fill='x', **gui_theme.ROW_PAD)
        compose_sample_row, self.compose_sample_script_var = self._build_sample_text_row(
            compose_frame, self.compose_text_widget)
        compose_sample_row.pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)

        lines_frame = ttk.LabelFrame(compose_frame, text=gui_theme.hud_label('Per-Line Color'))
        lines_frame.pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)
        ttk.Label(lines_frame,
                  text='Each line picks its own fill — Solid (one color), Sequence (an editable list '
                       'of color stops, Blended smoothly or Stepped as repeating bands), or Rainbow '
                       '(a continuous hue sweep across that line). Click a swatch, then use the Color '
                       'panel to change it.',
                  style='Hint.TLabel', wraplength=gui_theme.WRAP_WIDE,
                  justify='left').pack(fill='x', **gui_theme.ROW_PAD_TOP)
        self.compose_line_rows_container = ttk.Frame(lines_frame)
        self.compose_line_rows_container.pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)
        self._compose_line_fills: list[dict] = []
        self._compose_editing: tuple[int, int] | None = None
        self._compose_swatch_widgets: dict[tuple[int, int], tk.Label] = {}
        self._compose_last_line_count = -1

        layer_effect_frame = ttk.LabelFrame(compose_frame, text=gui_theme.hud_label('Layered Glyph Effect'))
        layer_effect_frame.pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)
        ttk.Label(
            layer_effect_frame,
            text="Replace the plain fontpack glyphs above with a multi-layer effect (inset rings, "
                 "outset borders, offset shadows, ...) built on the Layer Effects tab. While enabled, "
                 "Per-Line Color above is ignored — each layer carries its own color instead. Needs "
                 "the fontpack's original font file, not just the fontpack itself.",
            style='Hint.TLabel', wraplength=gui_theme.WRAP_WIDE, justify='left',
        ).pack(fill='x', **gui_theme.ROW_PAD_TOP)

        layer_effect_toggle_row = ttk.Frame(layer_effect_frame)
        layer_effect_toggle_row.pack(fill='x', **gui_theme.ROW_PAD)
        self.compose_layer_effect_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(layer_effect_toggle_row, text='Enable Layered Glyph Effect',
                        variable=self.compose_layer_effect_var,
                        command=self._on_compose_layer_effect_toggled).pack(side='left')

        layer_effect_preset_row = ttk.Frame(layer_effect_frame)
        layer_effect_preset_row.pack(fill='x', **gui_theme.ROW_PAD)
        self.compose_layer_effect_preset_var = tk.StringVar(value='Concentric Inline')
        ttk.Combobox(layer_effect_preset_row, textvariable=self.compose_layer_effect_preset_var,
                     values=sorted(layer_presets.PRESET_REGISTRY), state='readonly').pack(
            side='left', fill='x', expand=True)
        ttk.Button(layer_effect_preset_row, text='Apply preset',
                   command=self._apply_composer_layer_effect_preset).pack(side='left', padx=(4, 0))
        ttk.Button(layer_effect_preset_row, text='Edit Layers...',
                   command=lambda: self._show_tab('layer_effects')).pack(side='left', padx=(4, 0))

        self.compose_layer_effect_summary_var = tk.StringVar(value='')
        ttk.Label(layer_effect_frame, textvariable=self.compose_layer_effect_summary_var,
                  style='Hint.TLabel').pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)

        style_frame = ttk.Frame(compose_frame)
        style_frame.pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)
        ttk.Label(style_frame, text=gui_theme.hud_label('Style')).pack(anchor='w', **gui_theme.ROW_PAD_TOP)
        ttk.Label(style_frame, text='Applies to the whole block — color is set per line above.',
                  style='Hint.TLabel').pack(anchor='w')

        size_style_row = ttk.Frame(style_frame)
        size_style_row.pack(fill='x', **gui_theme.ROW_PAD)
        ttk.Label(size_style_row, text='Size:').pack(side='left')
        self.compose_size_var = tk.IntVar(value=100)
        ttk.Spinbox(size_style_row, from_=25, to=400, increment=5, width=5,
                    textvariable=self.compose_size_var).pack(side='left', padx=(4, 2))
        ttk.Label(size_style_row, text='%').pack(side='left', padx=(0, 14))
        self.compose_bold_var = tk.BooleanVar(value=False)
        self.compose_italic_var = tk.BooleanVar(value=False)
        self.compose_underline_var = tk.BooleanVar(value=False)
        self.compose_strikethrough_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(size_style_row, text='Bold', variable=self.compose_bold_var).pack(
            side='left', padx=(0, 8))
        ttk.Checkbutton(size_style_row, text='Italic', variable=self.compose_italic_var).pack(
            side='left', padx=(0, 8))
        ttk.Checkbutton(size_style_row, text='Underline', variable=self.compose_underline_var).pack(
            side='left', padx=(0, 8))
        ttk.Checkbutton(size_style_row, text='Strikethrough',
                         variable=self.compose_strikethrough_var).pack(side='left')

        spacing_row = ttk.Frame(style_frame)
        spacing_row.pack(fill='x', **gui_theme.ROW_PAD)
        ttk.Label(spacing_row, text='Letter spacing:').pack(side='left')
        self.compose_letter_spacing_var = tk.DoubleVar(value=0.0)
        ttk.Spinbox(spacing_row, from_=-50, to=200, increment=1, width=6,
                    textvariable=self.compose_letter_spacing_var).pack(side='left', padx=(4, 16))
        ttk.Label(spacing_row, text='Line spacing:').pack(side='left')
        self.compose_line_spacing_var = tk.IntVar(value=100)
        ttk.Spinbox(spacing_row, from_=50, to=300, increment=5, width=5,
                    textvariable=self.compose_line_spacing_var).pack(side='left', padx=(4, 2))
        ttk.Label(spacing_row, text='%').pack(side='left')

        ttk.Label(style_frame,
                  text='Bold/Italic reshape existing shapes in place — no extra vinyl layers. '
                       'Underline/Strikethrough each add one bar shape per line.',
                  style='Hint.TLabel', wraplength=gui_theme.WRAP_WIDE,
                  justify='left').pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)

        compose_opt_row = ttk.Frame(compose_frame)
        compose_opt_row.pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)
        ttk.Label(compose_opt_row, text='Align:').pack(side='left')
        self.compose_align_var = tk.StringVar(value='left')
        for value in ALIGNMENTS:
            ttk.Radiobutton(compose_opt_row, text=value.capitalize(), value=value,
                             variable=self.compose_align_var).pack(side='left', padx=(4, 0))
        ttk.Button(compose_opt_row, text='Compose', command=self._compose_text).pack(side='left', padx=(12, 2))
        self.compose_save_btn = ttk.Button(compose_opt_row, text='Save...',
                                            command=self._save_composed_text, state='disabled')
        self.compose_save_btn.pack(side='left', padx=2)

        ttk.Label(compose_frame,
                  text='Justify spreads extra space across word gaps to fill the widest line; the last '
                       'line of multi-line text stays left-aligned either way. Characters with no '
                       'generated glyph in the pack are skipped and listed below, not treated as errors.',
                  style='Hint.TLabel', wraplength=gui_theme.WRAP_WIDE,
                  justify='left').pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)

        compose_body = ttk.Frame(compose_frame)
        compose_body.pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)
        self.compose_canvas = tk.Canvas(compose_body, width=COMPOSE_PREVIEW_SIZE[0],
                                         height=COMPOSE_PREVIEW_SIZE[1], highlightthickness=1)
        self.compose_canvas.pack(fill='x')
        self.compose_stats_var = tk.StringVar(
            value='Pick a fontpack folder, type some text, and click Compose.')
        self.compose_stats_lbl = ttk.Label(
            compose_frame, textvariable=self.compose_stats_var, style='Hint.TLabel',
            wraplength=gui_theme.WRAP_WIDE, justify='left')
        self.compose_stats_lbl.pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)

        self._build_composer_color_panel(body)
        # Debounced (unlike Configurator/Glyph Inspector's same helper call):
        # while the user is actively dragging the window edge, Tk fires many
        # Configure events per second, and this page's width cascades down
        # through three nested levels (the scroll canvas -> its embedded
        # content frame -> this body frame — see _build_scroll_shell), so
        # mid-drag events can carry a transient width from a level that
        # hasn't caught up yet. Reacting to every one of those flickered the
        # Color panel in and out during a live resize; waiting for the drag
        # to actually pause avoids acting on those transient reads entirely.
        self._bind_responsive_columns(
            body, self.compose_left_col, self.compose_color_panel,
            threshold=self._COMPOSER_WIDE_THRESHOLD, left_padx=(0, 0), right_padx=(6, 0),
            debounce_ms=self._COMPOSER_RESIZE_DEBOUNCE_MS, state_attr='_compose_layout_wide')
        self._on_compose_text_changed()
        self._update_compose_layer_effect_summary()
    def _pick_compose_pack_dir(self):
        chosen = filedialog.askdirectory(initialdir=self.compose_pack_var.get() or self.out_var.get())
        if chosen:
            self.compose_pack_var.set(chosen)
    def _use_current_pack_dir(self):
        prefix = sanitize_prefix(self.prefix_var.get())
        output = self.output_var.get()
        backend = gen_modelbin_gui.resolve_backend(self.compute_backend_var.get() if output == 'json' else 'cpu')
        pack_dir = pack_dir_for(self.out_var.get(), prefix, output,
                                 max(1, int(self.segments_var.get())), backend.resolved)
        self.compose_pack_var.set(str(pack_dir))
    @staticmethod
    def _new_compose_line_fill() -> dict:
        return {'mode': 'solid', 'colors': [(255, 255, 255, 255)], 'blend': False}
    def _compose_line_texts(self) -> list[str]:
        return self.compose_text_widget.get('1.0', 'end-1c').split('\n')
    def _on_compose_text_changed(self, _event=None):
        lines = self._compose_line_texts()
        if len(lines) == self._compose_last_line_count:
            return
        self._compose_last_line_count = len(lines)
        while len(self._compose_line_fills) < len(lines):
            self._compose_line_fills.append(self._new_compose_line_fill())
        del self._compose_line_fills[len(lines):]
        if self._compose_editing is None or self._compose_editing[0] >= len(lines):
            self._compose_editing = (0, 0) if lines else None
        self._rebuild_compose_line_rows()
    def _rebuild_compose_line_rows(self):
        for child in self.compose_line_rows_container.winfo_children():
            child.destroy()
        self._compose_swatch_widgets.clear()
        for index, text in enumerate(self._compose_line_texts()):
            self._build_compose_line_row(self.compose_line_rows_container, index, text)
        self._refresh_compose_color_panel()
    def _build_compose_line_row(self, parent, index: int, text: str):
        fill = self._compose_line_fills[index]
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=2)
        ttk.Label(row, text=f'{index + 1}.', width=3).pack(side='left')
        preview = text.strip() or '(empty)'
        if len(preview) > 24:
            preview = preview[:23] + '…'
        ttk.Label(row, text=f'“{preview}”', style='Hint.TLabel', width=26,
                  anchor='w').pack(side='left', padx=(0, 8))

        controls = ttk.Frame(row)
        controls.pack(side='left', fill='x', expand=True)

        pills = ttk.Frame(controls)
        pills.pack(fill='x')
        p = gui_theme.palette()
        for mode_key, label in self._SEQ_MODE_LABELS:
            active = fill['mode'] == mode_key
            lbl = tk.Label(pills, text=label, padx=8, pady=2, cursor='hand2',
                            background=p['accent'] if active else p['button_bg'],
                            foreground=p['select_fg'] if active else p['fg'])
            lbl.pack(side='left', padx=(0, 3))
            lbl.bind('<Button-1>', lambda _e, li=index, m=mode_key: self._set_compose_line_mode(li, m))

        if fill['mode'] == 'solid':
            self._build_compose_swatch(controls, index, 0).pack(side='left', padx=(8, 0), pady=(3, 0))
        elif fill['mode'] == 'rainbow':
            ttk.Label(controls, text='(continuous hue sweep across this line)',
                      style='Hint.TLabel').pack(side='left', padx=(8, 0), pady=(3, 0))
        else:
            self._build_compose_sequence_editor(controls, index, fill)
    def _build_compose_swatch(self, parent, line_index: int, slot_index: int) -> tk.Label:
        fill = self._compose_line_fills[line_index]
        color = fill['colors'][slot_index]
        editing = self._compose_editing == (line_index, slot_index)
        sw = tk.Label(parent, width=3, cursor='hand2', background=_rgba_to_hex(color),
                       relief='solid' if editing else 'sunken', borderwidth=2 if editing else 1)
        sw.bind('<Button-1>', lambda _e: self._select_compose_editing(line_index, slot_index))
        self._compose_swatch_widgets[(line_index, slot_index)] = sw
        return sw
    def _build_compose_sequence_editor(self, parent, line_index: int, fill: dict):
        editor = ttk.Frame(parent)
        editor.pack(fill='x', pady=(3, 0))

        toggle = ttk.Frame(editor)
        toggle.pack(side='left')
        p = gui_theme.palette()
        for blend_value, label in ((True, 'Blend'), (False, 'Step')):
            active = fill['blend'] == blend_value
            lbl = tk.Label(toggle, text=label, padx=6, pady=1, cursor='hand2',
                            background=p['secondary_accent'] if active else p['button_bg'],
                            foreground=p['select_fg'] if active else p['fg'])
            lbl.pack(side='left')
            lbl.bind('<Button-1>', lambda _e, li=line_index, b=blend_value:
                     self._set_compose_sequence_blend(li, b))

        stops = ttk.Frame(editor)
        stops.pack(side='left', padx=(8, 0))
        for slot_index in range(len(fill['colors'])):
            cell = ttk.Frame(stops)
            cell.pack(side='left', padx=2)
            self._build_compose_swatch(cell, line_index, slot_index).pack()
            if len(fill['colors']) > 2:
                rm = ttk.Button(cell, text='×', width=2,
                                 command=lambda li=line_index, si=slot_index:
                                 self._remove_compose_sequence_stop(li, si))
                rm.pack()
        if len(fill['colors']) < self._MAX_SEQ_STOPS:
            ttk.Button(stops, text='+', width=2,
                       command=lambda li=line_index: self._add_compose_sequence_stop(li)).pack(
                side='left', padx=(2, 0))

        presets = ttk.Frame(editor)
        presets.pack(side='left', padx=(8, 0))
        for preset_key, label in (('roygbiv', 'ROYGBIV'), ('grayscale', 'Grayscale')):
            ttk.Button(presets, text=label, command=lambda li=line_index, k=preset_key:
                       self._apply_compose_sequence_preset(li, k)).pack(side='left', padx=1)
    def _set_compose_line_mode(self, line_index: int, mode: str):
        fill = self._compose_line_fills[line_index]
        fill['mode'] = mode
        if mode == 'solid':
            fill['colors'] = [fill['colors'][0]]
        elif mode == 'sequence' and len(fill['colors']) < 2:
            first = fill['colors'][0]
            fill['colors'] = [first, first]
        self._compose_editing = (line_index, 0)
        self._rebuild_compose_line_rows()
    def _add_compose_sequence_stop(self, line_index: int):
        fill = self._compose_line_fills[line_index]
        if len(fill['colors']) >= self._MAX_SEQ_STOPS:
            return
        fill['colors'].append(fill['colors'][-1])
        self._compose_editing = (line_index, len(fill['colors']) - 1)
        self._rebuild_compose_line_rows()
    def _remove_compose_sequence_stop(self, line_index: int, slot_index: int):
        fill = self._compose_line_fills[line_index]
        if len(fill['colors']) <= 2:
            return
        del fill['colors'][slot_index]
        if self._compose_editing and self._compose_editing[0] == line_index \
                and self._compose_editing[1] >= len(fill['colors']):
            self._compose_editing = (line_index, len(fill['colors']) - 1)
        self._rebuild_compose_line_rows()
    def _set_compose_sequence_blend(self, line_index: int, blend: bool):
        self._compose_line_fills[line_index]['blend'] = blend
        self._rebuild_compose_line_rows()
    def _apply_compose_sequence_preset(self, line_index: int, preset_key: str):
        fill = self._compose_line_fills[line_index]
        fill['colors'] = list(self._SEQ_PRESETS[preset_key])
        fill['blend'] = False
        self._compose_editing = (line_index, 0)
        self._rebuild_compose_line_rows()
    def _select_compose_editing(self, line_index: int, slot_index: int):
        self._compose_editing = (line_index, slot_index)
        self._rebuild_compose_line_rows()
    def _compose_style_from_widgets(self) -> TextStyle:
        self._on_compose_text_changed()  # ensure fills match the current text before freezing
        fills = tuple(
            LineFill(mode=d['mode'], colors=tuple(d['colors']), blend=d['blend'])
            for d in self._compose_line_fills
        )
        return TextStyle(
            bold=self.compose_bold_var.get(), italic=self.compose_italic_var.get(),
            underline=self.compose_underline_var.get(),
            strikethrough=self.compose_strikethrough_var.get(),
            fills=fills,
        )
    def _compose_layer_effect_style(self) -> TextStyle:
        """Bold/italic/underline/strikethrough still apply on top of a
        Layered Glyph Effect (they reshape already-generated shapes in
        place, same as the plain path — see `text_style.apply_bold`/
        `apply_italic`), but `fills=()` (a no-op LineFill) deliberately
        skips the per-line color pass: each layer already carries its own
        color, and letting `_place_lines` overwrite every shape with one
        line color would erase that distinction. One side effect: since
        underline/strikethrough need a single resolved line color to draw
        their bar shape and a no-op fill never produces one, they render
        nothing while a Layered Glyph Effect is enabled — call this out in
        the status line if it happens rather than silently doing nothing."""
        return TextStyle(
            bold=self.compose_bold_var.get(), italic=self.compose_italic_var.get(),
            underline=self.compose_underline_var.get(),
            strikethrough=self.compose_strikethrough_var.get(),
            fills=(),
        )
    def _on_compose_layer_effect_toggled(self):
        self._update_compose_layer_effect_summary()
    def _apply_composer_layer_effect_preset(self):
        """Applies a preset to the same `self._layer_effects_stack` object
        the Layer Effects tab edits — Composer and that tab always share one
        live stack, never a copy, so "Edit Layers..." always opens exactly
        what Compose will use."""
        factory = layer_presets.PRESET_REGISTRY.get(self.compose_layer_effect_preset_var.get())
        if factory is None:
            return
        self._layer_effects_stack = factory()
        self._layer_effects_selected_layer_id = (
            self._layer_effects_stack.layers[0].id if self._layer_effects_stack.layers else None)
        if hasattr(self, 'layer_effects_preset_var'):
            self.layer_effects_preset_var.set(self.compose_layer_effect_preset_var.get())
        if hasattr(self, '_rebuild_layer_effects_rows'):
            self._rebuild_layer_effects_rows()
            self._refresh_layer_effects_properties()
        self._update_compose_layer_effect_summary()
    def _update_compose_layer_effect_summary(self):
        if not hasattr(self, 'compose_layer_effect_summary_var'):
            return
        stack = self._layer_effects_stack
        state = 'Active' if self.compose_layer_effect_var.get() else 'Configured, not enabled'
        self.compose_layer_effect_summary_var.set(
            f'{state}: "{stack.name}" — {len(stack.layers)} layer(s). Edit on the Layer Effects tab.')
    def _compose_text(self):
        pack_dir = Path(self.compose_pack_var.get().strip())
        text = self.compose_text_widget.get('1.0', 'end-1c')
        if not (pack_dir / 'manifest.json').exists():
            self.compose_stats_var.set(f'No manifest.json in: {pack_dir}')
            self.compose_stats_lbl.configure(style='Danger.TLabel')
            return
        if not text:
            self.compose_stats_var.set('Type some text to compose.')
            self.compose_stats_lbl.configure(style='Hint.TLabel')
            return
        try:
            size_scale = max(0.25, min(4.0, self.compose_size_var.get() / 100.0))
            line_spacing = max(0.5, min(3.0, self.compose_line_spacing_var.get() / 100.0))
            letter_spacing = float(self.compose_letter_spacing_var.get())
        except (ValueError, tk.TclError):
            self.compose_stats_var.set('Size, letter spacing, and line spacing must be numbers.')
            self.compose_stats_lbl.configure(style='Warn.TLabel')
            return
        self._update_compose_layer_effect_summary()
        use_layer_effect = self.compose_layer_effect_var.get()
        try:
            if use_layer_effect:
                manifest = json.loads((pack_dir / 'manifest.json').read_text(encoding='utf-8'))
                font_path_str = manifest.get('font_file')
                if not font_path_str or not Path(font_path_str).exists():
                    self.compose_stats_var.set(
                        "This fontpack has no associated font file on this machine — a Layered "
                        "Glyph Effect needs the original font, not just the generated fontpack.")
                    self.compose_stats_lbl.configure(style='Danger.TLabel')
                    return
                shapes, warnings, _groups_by_char = compose_layered_text(
                    text, font_path_str, self._layer_effects_stack,
                    align=self.compose_align_var.get(), letter_spacing=letter_spacing,
                    size_scale=size_scale, line_spacing=line_spacing,
                    style=self._compose_layer_effect_style())
            else:
                shapes, warnings = compose_text(
                    text, pack_dir, align=self.compose_align_var.get(), letter_spacing=letter_spacing,
                    size_scale=size_scale, line_spacing=line_spacing,
                    style=self._compose_style_from_widgets())
        except Exception as exc:
            self.compose_stats_var.set(f"Couldn't compose text: {exc}")
            self.compose_stats_lbl.configure(style='Danger.TLabel')
            return

        self._composed_shapes = shapes
        p = gui_theme.palette()
        image = file_preview.render_composed_preview(shapes, COMPOSE_PREVIEW_SIZE,
                                                       bg=p['canvas_bg'], fg=p['fg'])
        self._compose_photo = ImageTk.PhotoImage(image)
        self.compose_canvas.delete('all')
        self.compose_canvas.create_image(0, 0, anchor='nw', image=self._compose_photo)

        self.compose_save_btn.configure(state='normal' if shapes else 'disabled')
        stats = f'{len(shapes)} shape(s).'
        if warnings:
            stats += ' ' + ' '.join(warnings)
        self.compose_stats_var.set(stats)
        self.compose_stats_lbl.configure(style='Warn.TLabel' if warnings else 'Hint.TLabel')
    def _save_composed_text(self):
        if not self._composed_shapes:
            return
        chosen = filedialog.asksaveasfilename(
            defaultextension='.json', filetypes=[('JSON', '*.json'), ('all files', '*.*')],
            initialfile='composed_text.json')
        if not chosen:
            return
        try:
            save_composed_json(composed_to_json(self._composed_shapes), chosen)
            self._log(f'--- Saved composed text: {chosen} ---', tag='success')
        except Exception as exc:
            messagebox.showerror('Save failed', str(exc))
    def _preview_stats_text(self, path: Path) -> tuple[str, str]:
        """Returns (stats text, ttk label style).

        For .modelbin files this also runs `validate_modelbin()` — the
        visual preview above only reads the position buffer (see
        `file_preview.render_modelbin_preview`'s docstring), so a glyph can
        render as a perfect silhouette here while the full-attribute buffer
        the GPU actually needs is malformed (the exact bug class that made
        early custom glyphs invisible in-game, see RESEARCH.md §6). The
        validator is the one check in this tool that looks at that buffer.
        """
        try:
            if path.suffix.lower() == '.json':
                data = json.loads(path.read_text(encoding='utf-8'))
                shapes = data.get('shapes', [])
                masks = sum(1 for s in shapes if s.get('mask'))
                return f'{path.name}\n{len(shapes)} shape(s), {masks} mask cutout(s).', 'Hint.TLabel'
            if path.suffix.lower() == '.modelbin':
                from gen_modelbin import read_mesh_triangles, validate_modelbin
                vertices, triangles = read_mesh_triangles(path)
                ok, message = validate_modelbin(path)
                status = 'Structurally valid' if ok else 'INVALID'
                style = 'Success.TLabel' if ok else 'Danger.TLabel'
                text = (f'{path.name}\n{len(vertices)} vertices, {len(triangles)} triangles.\n'
                        f'{status}: {message}\n'
                        f'Structural validity only — this doesn\'t confirm FH6 itself will '
                        f'render it (needs a live catalog-hijack test); see the Custom Mesh '
                        f'output mode\'s note.')
                return text, style
            return f'{path.name}\nUnsupported file type: {path.suffix}', 'Hint.TLabel'
        except Exception as exc:
            return f'{path.name}\nCouldn\'t read stats: {exc}', 'Danger.TLabel'
