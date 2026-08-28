"""Direct Generator tab: the direct-to-shapes generation path (no fontpack step).
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
from forza_writer import image_debug  # noqa: E402
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


class DirectTabMixin:
    def _on_direct_color_change(self, rgba: tuple):
        self.direct_color = rgba
    def _build_direct_page(self):
        page = ttk.Frame(self.page_container)
        self._pages['direct'] = page
        content = self._build_scroll_shell(page, 'direct')

        ttk.Label(
            content,
            text='Type the exact text you need and generate one complete .json design. This is a '
                 'minimal troubleshooting path: it does not build or read a fontpack.',
            style='Intro.TLabel', wraplength=gui_theme.WRAP_WIDE, justify='left',
        ).pack(fill='x', **gui_theme.PAGE_INTRO_PAD)

        font_frame = ttk.LabelFrame(content, text=gui_theme.hud_label('1. Font'))
        font_frame.pack(fill='x', **gui_theme.SECTION_PAD)
        font_row = ttk.Frame(font_frame)
        font_row.pack(fill='x', **gui_theme.ROW_PAD)
        self.direct_font_var = tk.StringVar()
        ttk.Entry(font_row, textvariable=self.direct_font_var).pack(
            side='left', fill='x', expand=True, padx=(0, 4))
        ttk.Button(font_row, text='Use selected font',
                   command=self._use_selected_font_in_direct).pack(side='left', padx=2)
        ttk.Button(font_row, text='Browse...', command=self._browse_direct_font).pack(side='left', padx=2)

        image_row = ttk.Frame(font_frame)
        image_row.pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)
        ttk.Label(image_row, text='Lettering image:').pack(side='left')
        self.direct_image_var = tk.StringVar()
        ttk.Entry(image_row, textvariable=self.direct_image_var).pack(
            side='left', fill='x', expand=True, padx=(6, 4))
        ttk.Button(image_row, text='Browse...', command=self._browse_direct_image).pack(side='left')

        text_frame = ttk.LabelFrame(content, text=gui_theme.hud_label('2. Exact Text'))
        text_frame.pack(fill='x', **gui_theme.SECTION_PAD)
        self.direct_text_widget = tk.Text(text_frame, height=5, wrap='word')
        self.direct_text_widget.pack(fill='x', **gui_theme.ROW_PAD)
        self._register_independent_scroll(self.direct_text_widget)
        actions_row, self.direct_clear_btn, self.direct_select_all_btn = (
            self._build_text_box_actions_row(text_frame, self.direct_text_widget))
        actions_row.pack(fill='x', **gui_theme.ROW_PAD)
        sample_row, self.direct_sample_script_var = self._build_sample_text_row(
            text_frame, self.direct_text_widget)
        sample_row.pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)
        ttk.Label(
            text_frame,
            text='Repeated characters stay repeated. Shape Fitting analyzes each distinct glyph once '
                 'and reuses it. Pixel Tracing rasterizes the complete rendered text run.',
            style='Hint.TLabel', wraplength=gui_theme.WRAP_WIDE, justify='left',
        ).pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)

        method_frame = ttk.LabelFrame(content, text=gui_theme.hud_label('3. Generation Method'))
        method_frame.pack(fill='x', **gui_theme.SECTION_PAD)
        self.direct_method_var = tk.StringVar(value='modern')
        # Direct Generator's own method keys ('modern'/'legacy'/'image') differ
        # from Generator/Advanced Generator's output-mode keys, since
        # generate_direct()'s API predates and is independent of this UI
        # concern — this local map is what lets the three tabs still share
        # one identity color per concept (gui_theme.GENERATION_METHOD_STYLES)
        # without renaming either tab's underlying values.
        direct_method_styles = {
            'modern': gui_theme.GENERATION_METHOD_STYLES['json'],         # Shape Fitting
            'legacy': gui_theme.GENERATION_METHOD_STYLES['json_legacy'],  # Pixel Tracing
            'image': gui_theme.GENERATION_METHOD_STYLES['image'],         # Image to Text
        }
        self._build_output_mode_option(
            method_frame, style=direct_method_styles['modern'], title='Shape Fitting (.json)',
            variable=self.direct_method_var, value='modern',
            description='Analyzes each distinct glyph and approximates it using Forza\'s full '
                         'primitive-shape library, with quality checks and exact rectangular '
                         'fallback. Reuses repeated characters and the font\'s real metrics; this '
                         'Direct page does not use masks.')
        self._build_output_mode_option(
            method_frame, style=direct_method_styles['legacy'], title='Pixel Tracing (.json)',
            variable=self.direct_method_var, value='legacy',
            description='Rasterizes the complete text run first, preserving its kerning and shaping, '
                         'then combines filled pixels into rectangular vinyl layers. Usually much more '
                         'expensive in layer count; CPU only.')
        self._build_output_mode_option(
            method_frame, style=direct_method_styles['image'], title='Image to Text (.json)',
            variable=self.direct_method_var, value='image',
            description='Lifts lettering, logos, or a signature directly from a cropped image. No '
                         'font or typed text is required; the result is an exact monochrome rectangle '
                         'trace.')

        options = ttk.Frame(method_frame)
        options.pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)
        ttk.Label(options, text='Curve Smoothness:').pack(side='left')
        self.direct_segments_var = tk.IntVar(value=8)
        ttk.Spinbox(options, from_=1, to=32, width=5,
                    textvariable=self.direct_segments_var).pack(side='left', padx=(4, 12))
        ttk.Label(options, text='Align:').pack(side='left')
        self.direct_align_var = tk.StringVar(value='left')
        for value in ('left', 'center', 'right'):
            ttk.Radiobutton(options, text=value.capitalize(), value=value,
                            variable=self.direct_align_var).pack(side='left', padx=(4, 0))
        ttk.Label(options, text='Pixel trace cell size:').pack(side='left', padx=(16, 0))
        self.direct_cell_size_var = tk.IntVar(value=1)
        ttk.Spinbox(options, from_=1, to=16, width=4,
                    textvariable=self.direct_cell_size_var).pack(side='left', padx=(4, 0))

        image_options = ttk.Frame(method_frame)
        image_options.pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)
        ttk.Label(image_options, text='Image foreground:').pack(side='left')
        self.direct_image_polarity_var = tk.StringVar(value='auto')
        for value, label in (('auto', 'Auto'), ('light', 'Light/white'),
                             ('dark', 'Dark/black'), ('alpha', 'Transparency')):
            ttk.Radiobutton(image_options, text=label, value=value,
                            variable=self.direct_image_polarity_var).pack(side='left', padx=(4, 0))
        ttk.Label(image_options, text='Threshold:').pack(side='left', padx=(16, 0))
        self.direct_image_threshold_var = tk.StringVar(value='auto')
        ttk.Entry(image_options, width=6, textvariable=self.direct_image_threshold_var).pack(
            side='left', padx=(4, 0))

        color_frame = ttk.LabelFrame(content, text=gui_theme.hud_label('4. Color'))
        color_frame.pack(fill='x', **gui_theme.SECTION_PAD)
        self.direct_color_picker = ColorPickerWidget(
            color_frame, settings_key='color_direct', on_change=self._on_direct_color_change,
            title='')
        self.direct_color_picker.pack(fill='x', padx=6, pady=6)
        self.direct_color = self.direct_color_picker.color

        action_row = ttk.Frame(content)
        action_row.pack(fill='x', **gui_theme.SECTION_PAD)
        self.direct_generate_btn = ttk.Button(
            action_row, text='Generate Preview', command=self._start_direct_generation)
        self.direct_generate_btn.pack(side='left')
        self.direct_save_btn = ttk.Button(
            action_row, text='Save .json...', command=self._save_direct_generation,
            state='disabled')
        self.direct_save_btn.pack(side='left', padx=(6, 0))
        self.direct_status_var = tk.StringVar(
            value='Choose a font, enter text, and select a generation method.')
        self.direct_status_lbl = ttk.Label(
            action_row, textvariable=self.direct_status_var, style='Hint.TLabel',
            wraplength=gui_theme.WRAP_MED, justify='left')
        self.direct_status_lbl.pack(side='left', fill='x', expand=True, padx=(12, 0))

        preview_frame = ttk.LabelFrame(content, text=gui_theme.hud_label('Preview'))
        preview_frame.pack(fill='x', **gui_theme.SECTION_PAD)
        self.direct_canvas = tk.Canvas(preview_frame, width=COMPOSE_PREVIEW_SIZE[0],
                                       height=COMPOSE_PREVIEW_SIZE[1], highlightthickness=1)
        self.direct_canvas.pack(fill='x', **gui_theme.ROW_PAD)
    def _use_selected_font_in_direct(self):
        if self.selected_font is None:
            messagebox.showinfo('No font selected', 'Select a font on Generator first, or click Browse.')
            return
        self.direct_font_var.set(str(self.selected_font))
        self._show_tab('direct')
    def _browse_direct_font(self):
        chosen = filedialog.askopenfilename(
            filetypes=[('OpenType fonts', '*.ttf;*.otf'), ('all files', '*.*')])
        if chosen:
            self.direct_font_var.set(chosen)
    def _browse_direct_image(self):
        chosen = filedialog.askopenfilename(
            filetypes=[('Images', '*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.tif;*.tiff'),
                       ('all files', '*.*')])
        if chosen:
            self.direct_image_var.set(chosen)
    def _start_direct_generation(self):
        font_path = Path(self.direct_font_var.get().strip())
        text = self.direct_text_widget.get('1.0', 'end-1c')
        method = self.direct_method_var.get()
        image_path = Path(self.direct_image_var.get().strip())
        if method == 'image' and not image_path.is_file():
            self.direct_status_var.set(f'Image not found: {image_path}')
            self.direct_status_lbl.configure(style='Danger.TLabel')
            return
        if method != 'image' and not font_path.is_file():
            self.direct_status_var.set(f'Font not found: {font_path}')
            self.direct_status_lbl.configure(style='Danger.TLabel')
            return
        if method != 'image' and (not text or not text.strip()):
            self.direct_status_var.set('Type some text to generate.')
            self.direct_status_lbl.configure(style='Warn.TLabel')
            return
        if self.worker is not None and self.worker.is_alive():
            messagebox.showinfo('Generation in progress', 'Wait for the current generation job to finish.')
            return
        try:
            if method == 'modern':
                resolved_backend = gen_modelbin_gui.resolve_backend(self.compute_backend_var.get()).resolved
                segments = max(1, int(self.direct_segments_var.get()))
                default_name = direct_output_filename(
                    font_path, method, backend=resolved_backend, segments=segments)
            elif method == 'legacy':
                resolved_backend = 'cpu'
                cell_size = max(1, min(16, int(self.direct_cell_size_var.get())))
                default_name = direct_output_filename(
                    font_path, method, cell_size=cell_size)
            else:
                resolved_backend = 'cpu'
                cell_size = max(1, min(16, int(self.direct_cell_size_var.get())))
                threshold_text = self.direct_image_threshold_var.get().strip().lower()
                threshold = None if threshold_text in {'', 'auto'} else max(0, min(255, int(threshold_text)))
                default_name = direct_output_filename(image_path, method, cell_size=cell_size)
        except (ValueError, tk.TclError):
            self.direct_status_var.set(
                'Curve smoothness, cell size, and threshold must be whole numbers (or use auto).')
            self.direct_status_lbl.configure(style='Warn.TLabel')
            return
        self._direct_payload = None
        self._direct_shapes = []
        self._direct_preview_signature = self._direct_current_signature()
        self._direct_suggested_name = default_name
        self.direct_save_btn.configure(state='disabled')
        self.direct_canvas.delete('all')
        self._direct_photo = None
        self.direct_generate_btn.configure(state='disabled')
        self.direct_status_var.set(
            'Fitting and quality-checking distinct glyphs…' if method == 'modern'
            else ('Tracing the complete text run on CPU…' if method == 'legacy'
                  else 'Extracting and tracing lettering from the image…'))
        self.direct_status_lbl.configure(style='Hint.TLabel')
        self._log(f'--- Direct Generator preview: {method} ---')

        if method == 'modern':
            options = {
                'curve_segments': segments,
                'align': self.direct_align_var.get(),
                'compute_backend': resolved_backend,
            }
        elif method == 'legacy':
            options = {'cell_size': cell_size}
        else:
            options = {
                'image_path': str(image_path),
                'cell_size': cell_size,
                'polarity': self.direct_image_polarity_var.get(),
                'threshold': threshold,
            }
        options['solid_color'] = self.direct_color

        def worker():
            try:
                shapes, warnings, metadata = gen_modelbin_gui.generate_direct(
                    text, font_path, method=method, **options)
                payload = composed_to_json(shapes)
                # The trace snapshot is a live PIL/numpy object kept for debug
                # rendering, not something that belongs in a saved JSON — it
                # stays on the message for the GUI and out of the payload.
                serializable = {k: v for k, v in metadata.items() if k != 'trace_debug'}
                payload['direct_generation'] = {
                    **serializable,
                    'font_file': str(font_path) if method != 'image' else None,
                    'text': text if method != 'image' else None,
                    'compute_backend': resolved_backend,
                    **options,
                }
                self.msg_queue.put(
                    ('direct_done', shapes, warnings, metadata, payload, default_name))
            except Exception as exc:
                self.msg_queue.put(('direct_error', str(exc)))

        self.worker = threading.Thread(target=worker, daemon=True)
        self.worker.start()
    def _apply_direct_result(self, shapes, warnings, metadata, payload, suggested_name):
        self._direct_shapes = shapes
        self._direct_payload = payload
        self._direct_suggested_name = suggested_name
        # Only the image method produces one; kept so saving can write debug
        # output describing this exact trace rather than re-running it.
        self._direct_trace_debug = metadata.get('trace_debug')
        self._direct_source_image = (self.direct_image_var.get().strip()
                                     if metadata.get('method') == 'image' else None)
        p = gui_theme.palette()
        image = file_preview.render_composed_preview(
            shapes, COMPOSE_PREVIEW_SIZE, bg=p['canvas_bg'], fg=p['fg'])
        self._direct_photo = ImageTk.PhotoImage(image)
        self.direct_canvas.delete('all')
        self.direct_canvas.create_image(0, 0, anchor='nw', image=self._direct_photo)
        method = metadata['method'].capitalize()
        if metadata['method'] == 'modern':
            quality = metadata.get('quality_by_glyph', {})
            primitive_count = sum(
                item.get('selected') == 'primitive' for item in quality.values())
            exact_count = sum(item.get('selected') == 'exact' for item in quality.values())
            skewed_layers = sum(
                item.get('selected_skewed_layers', 0) for item in quality.values())
            detail = f"{metadata.get('unique_glyphs', 0)} unique glyph(s) fitted"
            if quality:
                detail += f'; {primitive_count} primitive, {exact_count} exact fallback'
                if skewed_layers:
                    detail += f'; {skewed_layers} skewed layer(s)'
        elif metadata['method'] == 'legacy':
            detail = f"cell size {metadata['cell_size']}"
        else:
            detail = (f"{metadata['polarity']} foreground at threshold {metadata['threshold']}; "
                      f"cell size {metadata['cell_size']}")
        status = f'{method}: previewed {len(shapes)} shape(s) ({detail}).'
        if warnings:
            status += ' ' + ' '.join(warnings)
        self.direct_status_var.set(status)
        self.direct_status_lbl.configure(style='Warn.TLabel' if warnings else 'Success.TLabel')
        self.direct_save_btn.configure(state='normal' if shapes else 'disabled')
        self._log(
            f'--- Direct Generator preview ready: {len(shapes)} shapes; not saved ---',
            tag='success')
    def _save_direct_generation(self):
        if not self._direct_payload or not self._direct_shapes:
            return
        if self._direct_preview_signature != self._direct_current_signature():
            self.direct_save_btn.configure(state='disabled')
            self.direct_status_var.set(
                'The font, text, or generation settings changed. Generate a new preview before saving.')
            self.direct_status_lbl.configure(style='Warn.TLabel')
            return
        trace_debug = getattr(self, '_direct_trace_debug', None)
        # An image trace saves into its own folder: it is a different kind of
        # artifact from a text Direct save, and its companion files would
        # otherwise scatter through the plain Direct output folder.
        start_dir = self.image_out_var.get() if trace_debug is not None else self.direct_out_var.get()
        chosen = filedialog.asksaveasfilename(
            defaultextension='.json', filetypes=[('JSON', '*.json'), ('all files', '*.*')],
            initialdir=start_dir, initialfile=self._direct_suggested_name)
        if not chosen:
            return
        try:
            Path(chosen).parent.mkdir(parents=True, exist_ok=True)
            save_composed_json(self._direct_payload, chosen)
            self.direct_status_var.set(
                f'Saved {len(self._direct_shapes)} shape(s) to {Path(chosen).name}.')
            self.direct_status_lbl.configure(style='Success.TLabel')
            self._log(f'--- Saved Direct Generator JSON: {chosen} ---', tag='success')
            self._write_image_debug_outputs(chosen, trace_debug)
        except Exception as exc:
            messagebox.showerror('Save failed', str(exc))
    def _write_image_debug_outputs(self, json_path, trace_debug) -> None:
        """Write the opt-in source copy / debug image / diagnostics sidecar.

        Failure here is logged, never raised: the generation the user asked
        for already succeeded and was saved, and a diagnostic extra must not
        turn that into an error dialog.
        """
        if trace_debug is None:
            return
        if not (self.image_save_source_var.get() or self.image_save_debug_var.get()):
            return
        try:
            written = image_debug.write_debug_outputs(
                json_path, trace_debug,
                source_path=getattr(self, '_direct_source_image', None),
                save_source=bool(self.image_save_source_var.get()),
                save_debug=bool(self.image_save_debug_var.get()),
                mode=self._image_debug_mode())
        except Exception as exc:
            self._log(f'Saved the design, but could not write debug output: {exc}', tag='warn')
            return
        for path in written:
            self._log(f'    wrote {Path(path).name}', tag='hint')
        if self.image_save_debug_var.get():
            scores = image_debug.accuracy(trace_debug)
            self._log(f'    trace accuracy: IoU {scores["iou"]:.3f} '
                      f'({scores["missed_pixels"]:,} px missed, '
                      f'{scores["overshoot_pixels"]:,} px overshoot)', tag='hint')
    def _direct_current_signature(self) -> tuple:
        """Identity of the inputs represented by the current in-memory preview."""
        return (
            self.direct_font_var.get(),
            self.direct_image_var.get(),
            self.direct_text_widget.get('1.0', 'end-1c'),
            self.direct_method_var.get(),
            str(self.direct_segments_var.get()),
            self.direct_align_var.get(),
            str(self.direct_cell_size_var.get()),
            self.direct_image_polarity_var.get(),
            self.direct_image_threshold_var.get(),
            self.compute_backend_var.get(),
        )
