"""Advanced Generator tab: variable-font axis/instance selection and generation.
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
from forza_writer.forza_colors import describe_color, forza_hsb_to_rgb, hex_to_rgb, rgb_to_forza_hsb  # noqa: E402
from forza_writer import manufacturer_colors  # noqa: E402
from forza_writer.variable_fonts import (  # noqa: E402
    VariableFontInfo, inspect_variable_font, instantiate_font, variation_slug)

from ..color_picker_widget import ColorPickerWidget  # noqa: E402
from ..state import (  # noqa: E402
    FONT_EXTENSIONS, FONTS_DIR_SYSTEM, GRID_MAX_TILES, GRID_TILE_GAP, GRID_TILE_SIZE,
    ICON_PATH, LIVE_PREVIEW_SIZE, COMPOSE_PREVIEW_SIZE, OUTPUT_MODE_LABELS, PREVIEW_SIZE,
    SIDEBAR_WIDTH, TABS, TAB_LABELS, _MODE_LABELS, direct_output_filename,
    enumerate_installed_fonts, is_running_as_administrator, sidebar_tab_text)


class AdvancedTabMixin:
    def _on_advanced_color_change(self, rgba: tuple):
        self.advanced_color = rgba
    def _build_advanced_page(self):
        page = ttk.Frame(self.page_container)
        self._pages['advanced'] = page
        content = self._build_scroll_shell(page, 'advanced')

        ttk.Label(
            content,
            text='Generate a deliberate instance from a variable font. Choose a named style such as '
                 'Regular or Bold, or set the font axes yourself; Forza Writer pins those coordinates '
                 'to one static face so every renderer sees identical outlines.',
            style='Intro.TLabel', wraplength=gui_theme.WRAP_WIDE,
            justify='left').pack(fill='x', **gui_theme.PAGE_INTRO_PAD)

        source_frame = ttk.LabelFrame(content, text=gui_theme.hud_label('1. Variable font'))
        source_frame.pack(fill='x', **gui_theme.SECTION_PAD)
        source_row = ttk.Frame(source_frame)
        source_row.pack(fill='x', **gui_theme.ROW_PAD_TOP)
        ttk.Label(source_row, text='Font:').pack(side='left', padx=4)
        self.advanced_font_var = tk.StringVar()
        ttk.Entry(source_row, textvariable=self.advanced_font_var).pack(
            side='left', fill='x', expand=True, padx=4)
        ttk.Button(source_row, text='Browse…', command=self._pick_advanced_font).pack(side='left', padx=2)
        ttk.Button(source_row, text='Use current from Generator',
                   command=self._use_advanced_font_from_generator).pack(side='left', padx=2)
        self.advanced_font_status_var = tk.StringVar(
            value='Choose a variable .ttf/.otf font. Static fonts are identified clearly.')
        ttk.Label(source_frame, textvariable=self.advanced_font_status_var, style='Hint.TLabel',
                  wraplength=gui_theme.WRAP_WIDE, justify='left').pack(
                      fill='x', padx=4, pady=gui_theme.ROW_PAD_BOTTOM['pady'])

        axes_frame = ttk.LabelFrame(content, text=gui_theme.hud_label('2. Instance and Axes'))
        axes_frame.pack(fill='x', **gui_theme.SECTION_PAD)
        instance_row = ttk.Frame(axes_frame)
        instance_row.pack(fill='x', **gui_theme.ROW_PAD)
        ttk.Label(instance_row, text='Named instance:').pack(side='left', padx=4)
        self.advanced_instance_var = tk.StringVar(value='')
        self.advanced_instance_combo = ttk.Combobox(
            instance_row, textvariable=self.advanced_instance_var, state='readonly', width=34)
        self.advanced_instance_combo.pack(side='left', padx=4)
        self.advanced_instance_combo.bind('<<ComboboxSelected>>', self._on_advanced_instance_selected)
        ttk.Label(instance_row, text='Regular is preferred when the font provides it.',
                  style='Hint.TLabel').pack(side='left', padx=6)
        self.advanced_axes_body = ttk.Frame(axes_frame)
        self.advanced_axes_body.pack(fill='x', padx=4, pady=(2, 5))

        output_frame = ttk.LabelFrame(content, text=gui_theme.hud_label('3. Output Method'))
        output_frame.pack(fill='x', **gui_theme.SECTION_PAD)
        ttk.Label(
            output_frame,
            text='This is the same output selection shown on Generator. Changing it here also '
                 'changes it there.',
            style='Hint.TLabel', wraplength=gui_theme.WRAP_WIDE,
            justify='left').pack(fill='x', padx=4, pady=(4, 2))
        for mode in OUTPUT_MODES:
            title, description = OUTPUT_MODE_LABELS[mode]
            self._build_output_mode_option(
                output_frame, style=gui_theme.GENERATION_METHOD_STYLES[mode], title=title,
                description=description, variable=self.output_var, value=mode,
                command=self._on_output_mode_changed, warn_description=(mode == 'modelbin'))

        ttk.Label(
            output_frame,
            text="Shape Fitting uses the Generator tab's mask and curve-smoothness settings. "
                 'Pixel Tracing rasterizes each glyph independently for this reusable fontpack.',
            style='Hint.TLabel', wraplength=gui_theme.WRAP_WIDE,
            justify='left').pack(fill='x', padx=gui_theme.INDENT_PAD, pady=(2, 5))

        preview_frame = ttk.LabelFrame(content, text=gui_theme.hud_label('4. Preview'))
        preview_frame.pack(fill='x', **gui_theme.SECTION_PAD)
        preview_text_row = ttk.Frame(preview_frame)
        preview_text_row.pack(fill='x', **gui_theme.ROW_PAD)
        ttk.Label(preview_text_row, text='Preview Text:').pack(side='left', padx=4)
        self.advanced_preview_text_var = tk.StringVar(value='繁體中文 字體預覽 ABC 123')
        ttk.Entry(preview_text_row, textvariable=self.advanced_preview_text_var).pack(
            side='left', fill='x', expand=True, padx=4)
        ttk.Button(preview_text_row, text='Refresh instance preview',
                   command=self._refresh_advanced_preview).pack(side='left', padx=4)
        advanced_sample_row, self.advanced_sample_script_var = self._build_sample_text_row(
            preview_frame, self.advanced_preview_text_var)
        advanced_sample_row.pack(fill='x', **gui_theme.ROW_PAD)
        self.advanced_preview_canvas = tk.Canvas(
            preview_frame, width=640, height=150, highlightthickness=1)
        self.advanced_preview_canvas.pack(fill='x', padx=6, pady=6)
        self.advanced_preview_status_var = tk.StringVar(value='Select a variable font to preview it.')
        ttk.Label(preview_frame, textvariable=self.advanced_preview_status_var, style='Hint.TLabel',
                  wraplength=gui_theme.WRAP_WIDE, justify='left').pack(
                      fill='x', padx=6, pady=(0, 6))

        color_frame = ttk.LabelFrame(content, text=gui_theme.hud_label('5. Color'))
        color_frame.pack(fill='x', **gui_theme.SECTION_PAD)
        self.advanced_color_picker = ColorPickerWidget(
            color_frame, settings_key='color_advanced', on_change=self._on_advanced_color_change,
            title='')
        self.advanced_color_picker.pack(fill='x', padx=6, pady=6)
        self.advanced_color = self.advanced_color_picker.color

        run_frame = ttk.LabelFrame(content, text=gui_theme.hud_label('6. Generation'))
        run_frame.pack(fill='x', **gui_theme.SECTION_PAD)
        ttk.Label(
            run_frame,
            text="Uses the Generator tab's current character selection, curve smoothness, mask "
                 'setting, prefix, processor, and output directory. Only this one instance is '
                 'generated; named styles are never multiplied automatically.',
            style='Hint.TLabel', wraplength=gui_theme.WRAP_WIDE,
            justify='left').pack(fill='x', padx=4, pady=(4, 2))
        self.advanced_workload_var = tk.StringVar(value='No variable font selected.')
        ttk.Label(run_frame, textvariable=self.advanced_workload_var, style='Warn.TLabel',
                  wraplength=gui_theme.WRAP_WIDE, justify='left').pack(fill='x', padx=4, pady=4)
        action_row = ttk.Frame(run_frame)
        action_row.pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)
        self.advanced_generate_btn = ttk.Button(
            action_row, text='Generate selected instance', style='Accent.TButton',
            command=self._start_advanced_batch)
        self.advanced_generate_btn.pack(side='left', padx=4)
        ttk.Button(action_row, text='Open per-glyph overrides for this instance',
                   command=self._open_advanced_instance_overrides).pack(side='left', padx=4)
    def _pick_advanced_font(self):
        chosen = filedialog.askopenfilename(
            filetypes=[('Variable/OpenType fonts', '*.ttf;*.otf'), ('all files', '*.*')])
        if chosen:
            self._load_advanced_font(Path(chosen))
    def _use_advanced_font_from_generator(self):
        if self.selected_font is None:
            self._log('No font selected on the Generator tab yet.', tag='warn')
            return
        self._load_advanced_font(self.selected_font)
    def _load_advanced_font(self, font_path: Path):
        if not font_path.exists():
            self.advanced_font_status_var.set(f'Font not found: {font_path}')
            return
        try:
            info = gen_modelbin_gui.inspect_variable_font(font_path)
        except Exception as exc:
            self._advanced_font = None
            self.advanced_font_status_var.set(f'Could not inspect font: {exc}')
            return
        self._advanced_font = font_path
        self._advanced_info = info
        self.advanced_font_var.set(str(font_path))
        self._advanced_axis_vars.clear()
        self._advanced_instance_coordinates.clear()
        for child in self.advanced_axes_body.winfo_children():
            child.destroy()
        if not info.is_variable:
            self.advanced_instance_combo.configure(values=(), state='disabled')
            self.advanced_instance_var.set('Static font')
            self.advanced_font_status_var.set(
                'This is a static font: it has no fvar variation axes. Use the Generator tab — '
                'including its per-glyph overrides workspace — unless you only need the advanced preview.')
            self._update_advanced_summary()
            return

        default_label = 'Font default'
        self._advanced_instance_coordinates[default_label] = info.defaults
        for instance in info.instances:
            label = instance.name
            if label in self._advanced_instance_coordinates:
                label = f'{label} ({variation_slug(instance.coordinates)})'
            self._advanced_instance_coordinates[label] = dict(instance.coordinates)
        values = list(self._advanced_instance_coordinates) + ['Custom']
        self.advanced_instance_combo.configure(values=values, state='readonly')

        self._advanced_axis_display_vars: dict[str, tk.StringVar] = {}
        for row_index, axis in enumerate(info.axes):
            row = ttk.Frame(self.advanced_axes_body)
            row.pack(fill='x', pady=2)
            ttk.Label(row, text=f'{axis.name} ({axis.tag})', width=24).pack(side='left', padx=4)
            value_var = tk.DoubleVar(value=axis.default)
            self._advanced_axis_vars[axis.tag] = value_var
            scale = ttk.Scale(row, from_=axis.minimum, to=axis.maximum, variable=value_var,
                              command=lambda _value, tag=axis.tag: self._on_advanced_axis_changed(tag))
            scale.pack(side='left', fill='x', expand=True, padx=4)
            entry = ttk.Entry(row, textvariable=value_var, width=9)
            entry.pack(side='left', padx=4)
            entry.bind('<Return>', lambda _event, tag=axis.tag: self._commit_advanced_axis(tag))
            entry.bind('<FocusOut>', lambda _event, tag=axis.tag: self._commit_advanced_axis(tag))
            limits = tk.StringVar(value=f'{axis.minimum:g} – {axis.maximum:g}')
            self._advanced_axis_display_vars[axis.tag] = limits
            ttk.Label(row, textvariable=limits, style='Hint.TLabel', width=17).pack(side='left')

        preferred = next((label for label in self._advanced_instance_coordinates
                          if label.casefold() == 'regular'), default_label)
        self.advanced_instance_var.set(preferred)
        self._on_advanced_instance_selected()
        axis_text = ', '.join(
            f'{axis.name} {axis.minimum:g}–{axis.maximum:g} (file default {axis.default:g})'
            for axis in info.axes)
        self.advanced_font_status_var.set(
            f'Variable font: {len(info.axes)} axis/axes, {len(info.instances)} named instance(s). '
            f'{axis_text}.')
        self._refresh_advanced_preview()
    def _on_advanced_instance_selected(self, _event=None):
        label = self.advanced_instance_var.get()
        coordinates = self._advanced_instance_coordinates.get(label)
        if coordinates is None:
            return
        self._advanced_setting_instance = True
        try:
            for axis in self._advanced_info.axes:
                self._advanced_axis_vars[axis.tag].set(coordinates.get(axis.tag, axis.default))
        finally:
            self._advanced_setting_instance = False
        self._update_advanced_summary()
    def _on_advanced_axis_changed(self, _tag=None):
        if getattr(self, '_advanced_setting_instance', False):
            return
        self.advanced_instance_var.set('Custom')
        self._update_advanced_summary()
    def _commit_advanced_axis(self, tag: str):
        axis = next((axis for axis in self._advanced_info.axes if axis.tag == tag), None)
        if axis is None:
            return
        try:
            value = float(self._advanced_axis_vars[tag].get())
        except (ValueError, tk.TclError):
            value = axis.default
        self._advanced_axis_vars[tag].set(min(axis.maximum, max(axis.minimum, value)))
        self._on_advanced_axis_changed(tag)
    def _advanced_coordinates(self) -> dict[str, float]:
        return {tag: float(var.get()) for tag, var in self._advanced_axis_vars.items()}
    def _advanced_variation(self) -> dict:
        return {
            'named_instance': self.advanced_instance_var.get(),
            'coordinates': self._advanced_coordinates(),
            'source_font_file': str(self._advanced_font) if self._advanced_font else None,
        }
    def _update_advanced_summary(self):
        if not hasattr(self, 'advanced_workload_var'):
            return
        if self._advanced_font is None or not self._advanced_info.is_variable:
            self.advanced_workload_var.set('Choose a variable font before generating.')
            return
        chars = self._selected_chars(self._advanced_font)
        try:
            categorized, _ = gen_modelbin_gui.charset_from_font(self._advanced_font)
            supported = {char for group in categorized.values() for char in group}
            glyph_count = len(supported if chars is None else supported & chars)
        except Exception:
            glyph_count = len(chars) if chars is not None else 0
        coordinates = self._advanced_coordinates()
        slug = variation_slug(coordinates)
        prefix = sanitize_prefix(self.prefix_var.get())
        self.advanced_workload_var.set(
            f'{glyph_count:,} glyphs × 1 instance = {glyph_count:,} outputs · '
            f'{self.advanced_instance_var.get()} ({slug}) · prefix {prefix}-{slug}')
    def _refresh_advanced_preview(self):
        if self._advanced_font is None or not self._advanced_info.is_variable:
            self.advanced_preview_status_var.set('Choose a variable font first.')
            return
        self._advanced_preview_generation += 1
        generation = self._advanced_preview_generation
        source = self._advanced_font
        coordinates = self._advanced_coordinates()
        preview_text = self.advanced_preview_text_var.get() or source.stem
        p = gui_theme.palette()
        self.advanced_preview_status_var.set(
            f'Preparing {variation_slug(coordinates)} in the background…')

        def worker():
            try:
                instance_path = gen_modelbin_gui.instantiate_font(source, coordinates)
                image = font_preview.render_font_text(
                    instance_path, preview_text, (640, 150), bg=p['canvas_bg'], fg=p['fg'])
                self.msg_queue.put(('advanced_preview_ready', generation, instance_path, image))
            except Exception as exc:
                self.msg_queue.put(('advanced_preview_error', generation, str(exc)))

        threading.Thread(target=worker, daemon=True).start()
    def _start_advanced_batch(self):
        if self._advanced_font is None or not self._advanced_info.is_variable:
            self._log('Choose a variable font on Advanced Generator first.', tag='warn')
            return
        chars = self._selected_chars(self._advanced_font)
        try:
            categorized, _ = gen_modelbin_gui.charset_from_font(self._advanced_font)
            supported = {char for group in categorized.values() for char in group}
            glyph_count = len(supported if chars is None else supported & chars)
        except Exception:
            glyph_count = len(chars) if chars is not None else 0
        if glyph_count >= 500 and not messagebox.askyesno(
                'Large advanced generation job',
                f'This will generate {glyph_count:,} glyphs for one variable-font instance.\n\n'
                'Continue with this large job?'):
            return
        output = self.output_var.get()
        reference = Path(self.ref_var.get()) if output == 'modelbin' else None
        self._start_generation(
            font_path=self._advanced_font, out_dir=Path(self.out_var.get()),
            prefix=sanitize_prefix(self.prefix_var.get()), output=output, reference=reference,
            segments=max(1, int(self.segments_var.get())), chars=chars,
            allow_stencil=self.allow_stencil_var.get(), source_label='Advanced Generator',
            variation=self._advanced_variation(),
            color_mode='solid', solid_color=self.advanced_color)
    def _open_advanced_instance_overrides(self):
        if self._advanced_font is None or not self._advanced_info.is_variable:
            self._log('Choose a variable font first.', tag='warn')
            return
        self._advanced_preview_generation += 1
        generation = self._advanced_preview_generation
        source = self._advanced_font
        coordinates = self._advanced_coordinates()
        self.advanced_preview_status_var.set('Preparing the selected instance for per-glyph overrides…')

        def worker():
            try:
                path = gen_modelbin_gui.instantiate_font(source, coordinates)
                self.msg_queue.put(('advanced_override_instance_ready', generation, path))
            except Exception as exc:
                self.msg_queue.put(('advanced_preview_error', generation, str(exc)))

        threading.Thread(target=worker, daemon=True).start()
