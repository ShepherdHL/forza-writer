"""Settings tab: output/reference paths, palette/density, compute backend.
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
import game_locator  # noqa: E402
import gui_settings  # noqa: E402
import gui_theme  # noqa: E402
import glyph_overrides as glyph_overrides_store  # noqa: E402
import generated_data_cleanup  # noqa: E402

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
from forza_writer.generation_policy import policy_to_dict, preset_name_for  # noqa: E402
from forza_writer.image_debug import DEBUG_LABELS as IMAGE_DEBUG_LABELS  # noqa: E402
from forza_writer.text_compose import ALIGNMENTS, compose_text  # noqa: E402
from forza_writer.text_style import FILL_MODES, LineFill, TextStyle  # noqa: E402
from forza_writer.forza_colors import describe_color, forza_hsb_to_rgb, hex_to_rgb, rgb_to_forza_hsb  # noqa: E402
from forza_writer import manufacturer_colors  # noqa: E402
from forza_writer.variable_fonts import (  # noqa: E402
    VariableFontInfo, inspect_variable_font, instantiate_font, variation_slug)

from ..state import (  # noqa: E402
    FONT_EXTENSIONS, FONTS_DIR_SYSTEM, GRID_MAX_TILES, GRID_TILE_GAP, GRID_TILE_SIZE,
    ICON_PATH, LIVE_PREVIEW_SIZE, COMPOSE_PREVIEW_SIZE, OUTPUT_MODE_LABELS, PREVIEW_SIZE,
    SIDEBAR_WIDTH, TABS, TAB_LABELS, _MODE_LABELS, direct_output_filename,
    enumerate_installed_fonts, is_running_as_administrator, sidebar_tab_text)


class SettingsTabMixin:
    # Width (px) of the path-settings grid above which its four panels run
    # two-up instead of stacked — comfortably past the app's default startup
    # width (1000x780, minus the sidebar) so the common case still shows one
    # readable column, and only a genuinely wide/maximized window earns two.
    _SETTINGS_PATHS_WIDE_THRESHOLD = 880

    def _build_settings_page(self):
        page = ttk.Frame(self.page_container)
        self._pages['settings'] = page
        content = self._build_scroll_shell(page, 'settings')

        ttk.Label(content,
                  text='Paths used across every tab — every field below is shared with Generator, '
                       'Advanced Generator, Direct Generator, Outputs, and Composer. Click Save '
                       'settings to persist them to disk so they survive restarting the tool.',
                  style='Intro.TLabel', wraplength=gui_theme.WRAP_WIDE,
                  justify='left').pack(fill='x', **gui_theme.PAGE_INTRO_PAD)

        # Reference modelbin stands alone (it's an input reference, not an
        # output directory like the four below it) — full width, same as
        # before.
        self.settings_ref_status_var = tk.StringVar()
        ref_frame, self.ref_entry, self.settings_ref_status_lbl = self._build_path_setting(
            content, label='Reference Modelbin', variable=self.ref_var, browse_command=self._pick_ref,
            detect_command=self._detect_reference_modelbin,
            status_var=self.settings_ref_status_var,
            description='Needed only for the Custom Mesh (.modelbin) output mode. An extracted FH6 '
                         'game asset, see README.md, or click Detect to locate an installed copy of '
                         'Forza Horizon 6 (Xbox app, Microsoft Store, or Steam) and extract it '
                         'automatically.')
        ref_frame.pack(fill='x', **gui_theme.SECTION_PAD)

        self.settings_kfps_status_var = tk.StringVar()
        kfps_frame, _kfps_entry, self.settings_kfps_status_lbl = self._build_path_setting(
            content, label='KFPS Executable', variable=self.kfps_executable_var,
            browse_command=self._pick_kfps_executable, detect_command=self._detect_kfps,
            status_var=self.settings_kfps_status_var,
            description='Optional. Set this to enable the Plates tab\'s "Send to KFPS" button, which '
                         'launches KFPS.exe with the generated plate\'s geometry .json file, same as '
                         'dragging that file onto KFPS yourself. Leave blank to only ever write files, '
                         'never launch anything. Click Detect to search common install locations.')
        kfps_frame.pack(fill='x', **gui_theme.SECTION_PAD)

        # The four output-directory settings: full-width LabelFrames here
        # meant very long text fields and wasted space once the window was
        # maximized (see the gui-ux audit §1). A responsive 2-column grid
        # instead — collapsing back to one column at narrower widths — via
        # _bind_responsive_grid, the same helper Section 9's centralization
        # goal calls for.
        paths_grid = ttk.Frame(content)
        paths_grid.pack(fill='x', **gui_theme.SECTION_PAD)

        self.settings_out_status_var = tk.StringVar()
        out_frame, _out_entry, self.settings_out_status_lbl = self._build_path_setting(
            paths_grid, label='Fontpacks Output Directory', variable=self.out_var,
            browse_command=self._pick_out_dir, status_var=self.settings_out_status_var,
            description='Where Generator and Advanced Generation write primitive JSON fontpacks — one '
                         'folder per font, with each generation profile (output format, backend, curve '
                         'smoothness) nested inside it.')

        self.settings_modelbin_out_status_var = tk.StringVar()
        modelbin_out_frame, _modelbin_out_entry, self.settings_modelbin_out_status_lbl = self._build_path_setting(
            paths_grid, label='Modelbin Output Directory', variable=self.modelbin_out_var,
            browse_command=lambda: self._pick_output_dir(self.modelbin_out_var),
            status_var=self.settings_modelbin_out_status_var,
            description='Where Generator writes Custom Mesh (.modelbin) fontpacks. Kept separate from '
                         'primitive JSON fontpacks because these require injection into FH6.')

        self.settings_direct_out_status_var = tk.StringVar()
        direct_out_frame, _direct_out_entry, self.settings_direct_out_status_lbl = self._build_path_setting(
            paths_grid, label='Direct Output Directory', variable=self.direct_out_var,
            browse_command=self._pick_direct_out_dir, status_var=self.settings_direct_out_status_var,
            description="Where Direct Generation's \"Save .json...\" dialog starts — kept separate from "
                         'the fontpacks folder above since a Direct save is a single standalone JSON '
                         'file, not a fontpack.')

        self.settings_image_out_status_var = tk.StringVar()
        image_frame, _image_out_entry, self.settings_image_out_status_lbl = self._build_path_setting(
            paths_grid, label='Image-to-Text Output', variable=self.image_out_var,
            browse_command=self._pick_image_out_dir, status_var=self.settings_image_out_status_var)
        ttk.Checkbutton(
            image_frame, text='Save source image alongside output',
            variable=self.image_save_source_var).pack(anchor='w', padx=gui_theme.INDENT_PAD)
        ttk.Label(
            image_frame,
            text='Copies the exact image the trace was taken from, named to match its output. Your '
                 'original file is never moved or modified.',
            style='Hint.TLabel', wraplength=gui_theme.WRAP_MED,
            justify='left').pack(fill='x', padx=gui_theme.INDENT_PAD, pady=(0, 4))
        ttk.Checkbutton(
            image_frame, text='Save generation debug image and diagnostics',
            variable=self.image_save_debug_var,
            command=self._update_settings_status).pack(anchor='w', padx=gui_theme.INDENT_PAD)
        debug_row = ttk.Frame(image_frame)
        debug_row.pack(fill='x', padx=gui_theme.INDENT_PAD, pady=(2, 0))
        ttk.Label(debug_row, text='Debug view:').pack(side='left')
        self.image_debug_combo = ttk.Combobox(
            debug_row, textvariable=self.image_debug_mode_var, state='readonly', width=28,
            values=list(IMAGE_DEBUG_LABELS.values()))
        self.image_debug_combo.pack(side='left', padx=4)
        ttk.Label(
            image_frame,
            text='Off by default; nothing extra is written unless this is ticked. The debug image shows '
                 'why vinyls landed where they did — the traced rectangles, where coverage disagrees '
                 'with the source, or both — alongside a JSON file recording counts, accuracy and the '
                 'threshold actually used.',
            style='Hint.TLabel', wraplength=gui_theme.WRAP_MED,
            justify='left').pack(fill='x', padx=gui_theme.INDENT_PAD, pady=(2, 4))

        self._bind_responsive_grid(
            paths_grid, [out_frame, modelbin_out_frame, direct_out_frame, image_frame],
            threshold=self._SETTINGS_PATHS_WIDE_THRESHOLD)

        compute_frame = ttk.LabelFrame(content, text=gui_theme.hud_label('Generation Processor'))
        compute_frame.pack(fill='x', **gui_theme.SECTION_PAD)
        compute_row = ttk.Frame(compute_frame)
        compute_row.pack(fill='x', **gui_theme.ROW_PAD)
        for value, label in (('auto', 'Auto (prefer NVIDIA CUDA)'),
                             ('cuda', 'NVIDIA CUDA'), ('directml', 'AMD DirectML (Experimental)'),
                             ('cpu', 'CPU')):
            ttk.Radiobutton(compute_row, text=label, value=value,
                            variable=self.compute_backend_var,
                            command=self._update_compute_backend_status).pack(side='left', padx=(4, 12))
        ttk.Label(
            compute_frame,
            text='Applies to Shape Fitting (.json). Auto sends candidate scoring to an NVIDIA GPU '
                 'when CUDA is available and safely falls back to CPU otherwise. AMD DirectML is an '
                 'unverified, opt-in backend for AMD (and other DirectX 12) GPUs — see '
                 'docs/DIRECTML_ACCELERATION.md — and is never chosen by Auto; you will see a '
                 'warning before each run that uses it.',
            style='Hint.TLabel', wraplength=gui_theme.WRAP_MED,
            justify='left').pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)
        ttk.Label(compute_frame, textvariable=self.compute_backend_status_var,
                  style='Hint.TLabel', wraplength=gui_theme.WRAP_MED,
                  justify='left').pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)

        appearance_frame = ttk.LabelFrame(content, text=gui_theme.hud_label('Appearance'))
        appearance_frame.pack(fill='x', **gui_theme.SECTION_PAD)
        palette_row = ttk.Frame(appearance_frame)
        palette_row.pack(fill='x', **gui_theme.ROW_PAD)
        ttk.Label(palette_row, text='Color palette:').pack(side='left')
        # Driven by the registry (gui_theme.PALETTE_ORDER/DISPLAY_NAMES)
        # rather than a hardcoded list, so a new palette needs zero changes
        # here — see docs/GUI_THEME_SYSTEM.md.
        for value in gui_theme.PALETTE_ORDER:
            ttk.Radiobutton(palette_row, text=gui_theme.DISPLAY_NAMES[value], value=value,
                            variable=self.palette_var,
                            command=self._preview_appearance).pack(side='left', padx=(10, 0))
        self.palette_description_var = tk.StringVar(
            value=gui_theme.DESCRIPTIONS.get(self.palette_var.get(), ''))
        ttk.Label(appearance_frame, textvariable=self.palette_description_var,
                  style='Hint.TLabel', wraplength=gui_theme.WRAP_MED,
                  justify='left').pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)

        density_row = ttk.Frame(appearance_frame)
        density_row.pack(fill='x', **gui_theme.ROW_PAD)
        ttk.Label(density_row, text='Interface density:').pack(side='left')
        for value, label in (('compact', 'Compact'), ('balanced', 'Balanced'), ('spacious', 'Spacious')):
            ttk.Radiobutton(density_row, text=label, value=value,
                            variable=self.density_var,
                            command=self._preview_appearance).pack(side='left', padx=(10, 0))
        self.appearance_hint_var = tk.StringVar(
            value='Changes apply immediately and are saved automatically — no need to click Save settings.')
        ttk.Label(appearance_frame, textvariable=self.appearance_hint_var,
                  style='Hint.TLabel', wraplength=gui_theme.WRAP_MED,
                  justify='left').pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)

        # Same primary-action-row pattern as Generator's Generate row; this
        # was previously a one-off button with no surrounding frame.
        action_row = ttk.Frame(content)
        action_row.pack(fill='x', **gui_theme.SECTION_PAD)
        ttk.Button(action_row, text='Save settings', command=self._save_settings,
                   style='Accent.TButton').pack(side='left', padx=4)
        self.settings_saved_var = tk.StringVar()
        ttk.Label(action_row, textvariable=self.settings_saved_var, style='Hint.TLabel').pack(
            side='left', padx=8)

        cleanup_frame = ttk.LabelFrame(content, text=gui_theme.hud_label('Generated Data'))
        cleanup_frame.pack(fill='x', **gui_theme.SECTION_PAD)
        self.cleanup_selection_vars = {
            key: tk.BooleanVar(value=False) for key in generated_data_cleanup.TARGET_LABELS
        }
        self.cleanup_size_vars = {
            key: tk.StringVar(value='Calculating…') for key in generated_data_cleanup.TARGET_LABELS
        }
        selection_grid = ttk.Frame(cleanup_frame)
        selection_grid.pack(fill='x', padx=gui_theme.INDENT_PAD, pady=(5, 2))
        for index, (key, label) in enumerate(generated_data_cleanup.TARGET_LABELS.items()):
            row = ttk.Frame(selection_grid)
            row.grid(row=index, column=0, sticky='ew', pady=(2, 5))
            row.columnconfigure(1, weight=1)
            ttk.Checkbutton(row, variable=self.cleanup_selection_vars[key]).grid(
                row=0, column=0, rowspan=2, sticky='n', padx=(0, 5))
            ttk.Label(row, text=label).grid(row=0, column=1, sticky='w')
            ttk.Label(row, textvariable=self.cleanup_size_vars[key], style='Hint.TLabel').grid(
                row=0, column=2, sticky='e', padx=(12, 0))
            ttk.Label(row, text=generated_data_cleanup.TARGET_DESCRIPTIONS[key],
                      style='Hint.TLabel', wraplength=gui_theme.WRAP_MED,
                      justify='left').grid(row=1, column=1, columnspan=2, sticky='ew')
        selection_grid.columnconfigure(0, weight=1)
        select_row = ttk.Frame(cleanup_frame)
        select_row.pack(fill='x', padx=gui_theme.INDENT_PAD, pady=(2, 4))
        ttk.Button(select_row, text='Select All', command=lambda: self._select_cleanup_targets(True)).pack(
            side='left', padx=(0, 4))
        ttk.Button(select_row, text='Select None', command=lambda: self._select_cleanup_targets(False)).pack(
            side='left')
        ttk.Button(select_row, text='Refresh sizes', command=self._refresh_cleanup_sizes).pack(
            side='right')
        cleanup_row = ttk.Frame(cleanup_frame)
        cleanup_row.pack(fill='x', **gui_theme.ROW_PAD)
        ttk.Button(cleanup_row, text='Clean generated data…', style='Danger.TButton',
                   command=self._clean_generated_data).pack(side='left', padx=4)
        self.cleanup_status_var = tk.StringVar(value='')
        ttk.Label(cleanup_row, textvariable=self.cleanup_status_var, style='Hint.TLabel').pack(
            side='left', padx=8)
        ttk.Label(
            cleanup_frame,
            text='Only checked categories are cleared. Settings, per-glyph overrides, source fonts, '
                 'reference modelbins, files stored directly in data, and custom external output '
                 'folders are always preserved.',
            style='Hint.TLabel', wraplength=gui_theme.WRAP_MED,
            justify='left').pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)

        self.ref_var.trace_add('write', lambda *_: self._update_settings_status())
        self.out_var.trace_add('write', lambda *_: self._update_settings_status())
        self.modelbin_out_var.trace_add('write', lambda *_: self._update_settings_status())
        self.direct_out_var.trace_add('write', lambda *_: self._update_settings_status())
        self._refresh_cleanup_sizes()
    def _update_settings_status(self):
        ref_ok = Path(self.ref_var.get()).exists()
        self.settings_ref_status_var.set(
            ('✓ found' if ref_ok else '✗ not found') + f': {self.ref_var.get()}')
        self.settings_ref_status_lbl.configure(style='Success.TLabel' if ref_ok else 'Danger.TLabel')
        out_path = Path(self.out_var.get())
        out_exists = out_path.exists()
        self.settings_out_status_var.set(
            ('✓ exists' if out_exists else 'will be created on first use') + f': {out_path}')
        self.settings_out_status_lbl.configure(style='Success.TLabel' if out_exists else 'Hint.TLabel')
        modelbin_out_path = Path(self.modelbin_out_var.get())
        modelbin_out_exists = modelbin_out_path.exists()
        self.settings_modelbin_out_status_var.set(
            ('✓ exists' if modelbin_out_exists else 'will be created on first use') + f': {modelbin_out_path}')
        self.settings_modelbin_out_status_lbl.configure(
            style='Success.TLabel' if modelbin_out_exists else 'Hint.TLabel')
        direct_out_path = Path(self.direct_out_var.get())
        direct_out_exists = direct_out_path.exists()
        self.settings_direct_out_status_var.set(
            ('✓ exists' if direct_out_exists else 'will be created on first use') + f': {direct_out_path}')
        self.settings_direct_out_status_lbl.configure(
            style='Success.TLabel' if direct_out_exists else 'Hint.TLabel')
        image_out_path = Path(self.image_out_var.get())
        image_out_exists = image_out_path.exists()
        self.settings_image_out_status_var.set(
            ('✓ exists' if image_out_exists else 'will be created on first use') + f': {image_out_path}')
        self.settings_image_out_status_lbl.configure(
            style='Success.TLabel' if image_out_exists else 'Hint.TLabel')
        if hasattr(self, 'image_debug_combo'):
            # The view picker is meaningless while debug output is off.
            self.image_debug_combo.configure(
                state='readonly' if self.image_save_debug_var.get() else 'disabled')
        self._update_reference_warning()
        if hasattr(self, 'generator_settings_status_var'):
            self.generator_settings_status_var.set(
                f'Reference modelbin: {self.ref_var.get()}   |   Fontpacks output dir: {self.out_var.get()}')
    def _update_reference_warning(self):
        if not hasattr(self, 'reference_warning_var'):
            return
        if self.output_var.get() == 'modelbin' and not Path(self.ref_var.get()).exists():
            self.reference_warning_var.set(
                f'⚠ Reference modelbin not found: {self.ref_var.get()} — set it in Settings.')
        else:
            self.reference_warning_var.set('')
    def _save_settings(self):
        policy = self._current_generation_policy()
        blob = policy_to_dict(policy)
        # update_settings, not save_settings: this form only ever names the
        # fields it itself owns (paths, generation policy, image debug
        # options) -- save_settings fills anything absent from what you pass
        # it with the hardcoded default, so calling it directly here would
        # silently reset window geometry, the color picker's saved/recent
        # colors, and each tab's own last color back to defaults every time
        # someone clicks this button.
        gui_settings.update_settings({'reference_modelbin': self.ref_var.get(),
                                    'kfps_executable': self.kfps_executable_var.get(),
                                    'output_dir': self.out_var.get(),
                                    'modelbin_output_dir': self.modelbin_out_var.get(),
                                    'direct_output_dir': self.direct_out_var.get(),
                                    'image_output_dir': self.image_out_var.get(),
                                    'palette': self.palette_var.get(), 'density': self.density_var.get(),
                                    'compute_backend': self.compute_backend_var.get(),
                                    'generation_preset': preset_name_for(policy),
                                    'generation_allowed_shapes': blob['allowed_shapes'],
                                    'generation_preferred_shapes': blob['preferred_shapes'],
                                    'generation_fallback': blob['fallback'],
                                    'generation_allow_exact_cover': blob['allow_exact_cover'],
                                    'image_save_source': bool(self.image_save_source_var.get()),
                                    'image_save_debug': bool(self.image_save_debug_var.get()),
                                    'image_debug_mode': self._image_debug_mode()})
        self.settings_saved_var.set('Saved.')
        self._log('--- Settings saved ---', tag='success')
    def _pick_direct_out_dir(self):
        chosen = filedialog.askdirectory(initialdir=self.direct_out_var.get())
        if chosen:
            self.direct_out_var.set(chosen)
    def _pick_kfps_executable(self):
        chosen = filedialog.askopenfilename(
            filetypes=[('KFPS', 'KFPS.exe'), ('executable', '*.exe'), ('all files', '*.*')])
        if chosen:
            self.kfps_executable_var.set(chosen)
    def _detect_reference_modelbin(self):
        zip_path = game_locator.find_fh6_vinyls_zip()
        if zip_path is None:
            messagebox.showinfo(
                'Detect Reference Modelbin',
                'No Forza Horizon 6 install found (checked Xbox app, Microsoft Store, and Steam). '
                'Use Browse to set it manually, see README.md.')
            return
        dest = Path(__file__).resolve().parent.parent.parent.parent / 'user-assets' / game_locator.REFERENCE_MODELBIN_NAME
        try:
            game_locator.extract_reference_modelbin(dest, zip_path)
        except FileNotFoundError as exc:
            messagebox.showinfo('Detect Reference Modelbin', str(exc))
            return
        self.ref_var.set(str(dest))  # the existing trace on ref_var refreshes the status label
    def _detect_kfps(self):
        path = game_locator.find_kfps_executable()
        if path is None:
            messagebox.showinfo(
                'Detect KFPS',
                'No KFPS install found in common locations. Use Browse to set it manually.')
            return
        self.kfps_executable_var.set(str(path))
        self.settings_kfps_status_var.set(f'✓ found: {path}')
        self.settings_kfps_status_lbl.configure(style='Success.TLabel')
    def _pick_output_dir(self, variable):
        chosen = filedialog.askdirectory(initialdir=variable.get())
        if chosen:
            variable.set(chosen)
    def _clean_generated_data(self):
        if self.worker is not None and self.worker.is_alive():
            messagebox.showwarning(
                'Generation in progress', 'Wait for the current generation job to finish before cleaning data.')
            return
        selected = tuple(
            key for key, variable in self.cleanup_selection_vars.items() if variable.get())
        if not selected:
            messagebox.showwarning('Nothing selected', 'Select at least one output or cache category to clear.')
            return
        project_root = Path(__file__).resolve().parents[3]
        targets = generated_data_cleanup.cleanup_targets(project_root, selected=selected)
        summary = generated_data_cleanup.summarize(targets)
        target_text = '\n'.join(f'  • {path}' for path in targets)
        size_mb = summary.bytes / (1024 * 1024)
        if not messagebox.askyesno(
                'Clean generated data?',
                f'This will permanently remove {summary.files:,} generated file(s) '
                f'({size_mb:.1f} MB) from:\n\n{target_text}\n\nContinue?'):
            return
        if not messagebox.askyesno(
                'Final confirmation',
                'Are you absolutely sure? This cannot be undone from Forza Writer.\n\n'
                'Your settings, source files, reference modelbins, and custom external folders will remain.'):
            return
        try:
            removed = generated_data_cleanup.clear_generated_data(project_root, selected=selected)
            if 'variable-instances' in selected:
                self._configurator_scan_cache.clear()
                self._configurator_fit_cache.clear()
            if any(key in selected for key in ('modelbin', 'fontpacks', 'advgen', 'dgen', 'direct', 'image')):
                font_preview.clear_cache()
            self.cleanup_status_var.set(
                f'Clean slate ready, removed {removed.files:,} file(s), '
                f'{removed.bytes / (1024 * 1024):.1f} MB.')
            self._refresh_outputs_pack_list()
            self._refresh_cleanup_sizes()
            self._log('--- Generated data and caches cleared ---', tag='success')
        except Exception as exc:
            self.cleanup_status_var.set(f'Cleanup failed: {exc}')
            messagebox.showerror('Cleanup failed', str(exc))
    def _select_cleanup_targets(self, selected: bool):
        for variable in self.cleanup_selection_vars.values():
            variable.set(selected)
    def _refresh_cleanup_sizes(self):
        self._cleanup_size_generation += 1
        generation = self._cleanup_size_generation
        for variable in self.cleanup_size_vars.values():
            variable.set('Calculating…')
        project_root = Path(__file__).resolve().parents[3]

        def worker():
            sizes = {}
            for key in generated_data_cleanup.TARGET_LABELS:
                targets = generated_data_cleanup.cleanup_targets(project_root, selected=[key])
                summary = generated_data_cleanup.summarize(targets)
                sizes[key] = (summary.files, summary.bytes)
            self.msg_queue.put(('cleanup_sizes_ready', generation, sizes))

        threading.Thread(target=worker, daemon=True).start()
    def _pick_image_out_dir(self):
        chosen = filedialog.askdirectory(initialdir=self.image_out_var.get())
        if chosen:
            self.image_out_var.set(chosen)
    def _image_debug_mode(self) -> str:
        """The stored key for the debug view the combobox is showing.

        The widget displays human labels; settings keep the stable key so
        rewording a label never invalidates a saved preference.
        """
        label = self.image_debug_mode_var.get()
        for key, text in IMAGE_DEBUG_LABELS.items():
            if text == label:
                return key
        return 'combined'
    def _detect_compute_backend(self):
        def worker():
            self.msg_queue.put(('compute_backend_detected', gen_modelbin_gui.resolve_backend('auto')))
        threading.Thread(target=worker, daemon=True).start()
    def _update_compute_backend_status(self):
        requested = self.compute_backend_var.get()
        backend = gen_modelbin_gui.resolve_backend(requested)
        if requested == 'cpu':
            text = 'Selected: CPU (GPU acceleration disabled).'
        elif backend.resolved in ('cuda', 'directml'):
            device = getattr(backend, 'device', 'GPU')
            detail = getattr(backend, 'detail', 'GPU acceleration active')
            label = 'NVIDIA CUDA' if backend.resolved == 'cuda' else 'AMD DirectML (Experimental)'
            text = f'Selected: {label} - {device} - {detail}'
        elif requested == 'cuda':
            text = (f'NVIDIA CUDA selected but unavailable; generation will stop. '
                    f"{getattr(backend, 'detail', '')}")
        elif requested == 'directml':
            text = (f'AMD DirectML selected but unavailable; generation will stop. '
                    f"{getattr(backend, 'detail', '')}")
        else:
            text = f"Auto currently resolves to CPU. {getattr(backend, 'detail', '')}"
        self.compute_backend_status_var.set(text)
    def _preview_appearance(self):
        previous_spacing = gui_theme.spacing_snapshot()
        gui_theme.configure(self.palette_var.get(), self.density_var.get())
        gui_theme.reflow_spacing(self.root, previous_spacing)
        self.palette_description_var.set(gui_theme.DESCRIPTIONS.get(self.palette_var.get(), ''))
        self._apply_theme()
        self.root.update_idletasks()
        # Persisted immediately, the same way window geometry and the color
        # picker's saved/recent colors already are -- picking a palette or
        # density is itself the save action, not something that needs a
        # separate trip to the "Save settings" button below.
        gui_settings.update_settings({'palette': self.palette_var.get(), 'density': self.density_var.get()})
