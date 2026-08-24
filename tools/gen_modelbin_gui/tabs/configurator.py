"""Configurator tab: per-glyph mask-mode overrides for a font (auto/force/never/manual),
backed by glyph_overrides.py on disk.
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

from ..state import (  # noqa: E402
    FONT_EXTENSIONS, FONTS_DIR_SYSTEM, GRID_MAX_TILES, GRID_TILE_GAP, GRID_TILE_SIZE,
    ICON_PATH, LIVE_PREVIEW_SIZE, COMPOSE_PREVIEW_SIZE, OUTPUT_MODE_LABELS, PREVIEW_SIZE,
    SIDEBAR_WIDTH, TABS, TAB_LABELS, _MODE_LABELS, direct_output_filename,
    enumerate_installed_fonts, is_running_as_administrator, sidebar_tab_text)


class ConfiguratorTabMixin:
    _CONFIGURATOR_WIDE_THRESHOLD = 900
    # Rows inserted per GUI-thread batch when populating the glyph tree. A
    # plain synchronous loop over a large CJK font's whole cmap (thousands of
    # characters) blocks the GUI thread for a visible stutter the moment the
    # workspace opens; batching through root.after yields back to the event
    # loop between chunks so the window stays responsive throughout, at the
    # cost of the full list taking a little longer to finish appearing.
    _CONFIGURATOR_INSERT_CHUNK = 150

    def _build_configurator_workspace(self, parent):
        """Build the former Configurator as a lazy Generator sub-workspace."""
        self.configurator_font_var = tk.StringVar()
        self._configurator_workspace_open = False

        workspace = ttk.LabelFrame(parent, text=gui_theme.hud_label('Per-Glyph Overrides'))
        workspace.pack(fill='x', **gui_theme.SECTION_PAD)
        header = ttk.Frame(workspace)
        header.pack(fill='x', padx=6, pady=5)
        self.configurator_toggle_btn = ttk.Button(
            header, text='▶  Open per-glyph overrides', command=self._toggle_configurator_workspace)
        self.configurator_toggle_btn.pack(side='left')
        self.configurator_summary_var = tk.StringVar(
            value='Closed — glyph scanning and previews are deferred.')
        ttk.Label(header, textvariable=self.configurator_summary_var, style='Hint.TLabel').pack(
            side='left', padx=8, fill='x', expand=True)

        content = ttk.Frame(workspace)
        self.configurator_workspace_body = content
        ttk.Label(content,
                  text='Overrides apply to the font currently selected above. Force or forbid masks '
                       'per glyph, or assign an already-made .json file. Changes save immediately and '
                       'the main Generate button uses them.',
                  style='Hint.TLabel', wraplength=gui_theme.WRAP_WIDE,
                  justify='left').pack(fill='x', padx=8, pady=(3, 6))

        scan_row = ttk.Frame(content)
        scan_row.pack(fill='x', padx=8, pady=(0, 3))
        ttk.Button(scan_row, text='Rescan glyphs', command=self._rescan_configurator_glyphs).pack(side='left')
        self.configurator_scan_status_var = tk.StringVar(value='Open this workspace to inspect the selected font.')
        ttk.Label(scan_row, textvariable=self.configurator_scan_status_var, style='Hint.TLabel',
                  wraplength=gui_theme.WRAP_MED, justify='left').pack(side='left', padx=8)

        bulk_row = ttk.Frame(content)
        bulk_row.pack(fill='x', padx=8, pady=(0, 3))
        ttk.Button(bulk_row, text='Reset all to Auto', command=self._configurator_reset_all).pack(
            side='left', padx=(0, 4))
        ttk.Button(bulk_row, text='Force mask on all eligible rectilinear glyphs',
                   command=self._configurator_force_all_rectilinear).pack(side='left')

        body = ttk.Frame(content)
        body.pack(fill='both', expand=True, padx=8, pady=(2, 8))
        self.configurator_columns = body

        list_col = ttk.Frame(body)
        self.configurator_list_col = list_col
        self.configurator_tree = ttk.Treeview(
            list_col, columns=('category', 'rectilinear', 'auto', 'mode'),
            show='tree headings', height=14)
        self.configurator_tree.heading('#0', text='Glyph')
        self.configurator_tree.column('#0', width=60, anchor='center', stretch=False)
        self.configurator_tree.heading('category', text='Category')
        self.configurator_tree.column('category', width=90, anchor='w', stretch=False)
        self.configurator_tree.heading('rectilinear', text='Rectilinear')
        self.configurator_tree.column('rectilinear', width=80, anchor='center', stretch=False)
        self.configurator_tree.heading('auto', text='Auto picks')
        self.configurator_tree.column('auto', width=150, anchor='w')
        self.configurator_tree.heading('mode', text='Mode')
        self.configurator_tree.column('mode', width=170, anchor='w', stretch=False)
        tree_scroll = gui_theme.AutoHideScrollbar(
            list_col, orient='vertical', command=self.configurator_tree.yview)
        self.configurator_tree.configure(yscrollcommand=tree_scroll.set)
        self.configurator_tree.pack(side='left', fill='both', expand=True, padx=(0, gui_theme.SCROLLBAR_GUTTER))
        tree_scroll.pack(side='right', fill='y')
        self.configurator_tree.bind('<<TreeviewSelect>>', self._on_configurator_glyph_selected)
        self._register_independent_scroll(self.configurator_tree)

        detail_col = ttk.LabelFrame(body, text=gui_theme.hud_label('Selected Glyph'))
        self.configurator_detail_col = detail_col
        self.configurator_preview_canvas = tk.Canvas(detail_col, width=LIVE_PREVIEW_SIZE[0],
                                                       height=LIVE_PREVIEW_SIZE[1], highlightthickness=1)
        self.configurator_preview_canvas.pack(padx=6, pady=6)

        self.configurator_mode_var = tk.StringVar(value='auto')
        self.configurator_force_rb = None
        for value, label in (('auto', 'Auto'), ('force', 'Force Mask'), ('never', 'Force No Mask')):
            rb = ttk.Radiobutton(detail_col, text=label, value=value, variable=self.configurator_mode_var,
                                  command=self._on_configurator_mode_changed)
            rb.pack(anchor='w', padx=6, pady=1)
            if value == 'force':
                self.configurator_force_rb = rb
        ttk.Button(detail_col, text='Assign file…', command=self._configurator_assign_file).pack(
            anchor='w', padx=6, pady=(4, 1))

        self.configurator_detail_status_var = tk.StringVar(value='Select a glyph on the left.')
        ttk.Label(detail_col, textvariable=self.configurator_detail_status_var, style='Hint.TLabel',
                  wraplength=180, justify='left').pack(fill='x', padx=6, pady=(4, 6))

        self._bind_responsive_columns(
            body, list_col, detail_col, threshold=self._CONFIGURATOR_WIDE_THRESHOLD,
            state_attr='_configurator_layout_wide')

    def _toggle_configurator_workspace(self):
        self._set_configurator_workspace_open(not self._configurator_workspace_open)

    def _set_configurator_workspace_open(self, opened: bool):
        if opened == self._configurator_workspace_open:
            return
        self._configurator_workspace_open = opened
        if not opened:
            self.configurator_workspace_body.pack_forget()
            self.configurator_toggle_btn.configure(text='▶  Open per-glyph overrides')
            self.configurator_summary_var.set('Closed — glyph scanning and previews are deferred.')
            return
        self.configurator_workspace_body.pack(fill='both', expand=True, padx=2, pady=(0, 5))
        self.configurator_toggle_btn.configure(text='▼  Close per-glyph overrides')
        selected = self.selected_font
        if selected is None:
            self.configurator_scan_status_var.set('Select a font above to inspect its glyphs.')
            self.configurator_summary_var.set('Open — waiting for a Generator font selection.')
            return
        selected_text = str(selected)
        needs_scan = self.configurator_font_var.get() != selected_text
        self.configurator_font_var.set(selected_text)
        self.configurator_summary_var.set(f'Open — editing {selected.name}.')
        if needs_scan or not self.configurator_tree.get_children():
            self._rescan_configurator_glyphs()

    def _configurator_char_list(self) -> list[tuple[str, str]]:
        """Every glyph the Configurator font actually has. Unlike
        Generator's character checkboxes, Configurator doesn't restrict
        what gets generated — it reviews/overrides the font's whole glyph
        set; restricting output stays Generator's job."""
        if self._configurator_font is None:
            return []
        categorized, _skipped = gen_modelbin_gui.charset_from_font(self._configurator_font)
        return [(char, category) for category in CATEGORY_ORDER for char in categorized.get(category, [])]
    def _configurator_mode_label(self, char: str) -> str:
        entry = self._configurator_overrides.get(char, {'mode': 'auto'})
        if entry['mode'] == 'manual':
            return f"Manual: {Path(entry['file']).name}"
        return _MODE_LABELS[entry['mode']]
    def _configurator_tree_row_values(self, char: str, rect_text: str, auto_text: str) -> tuple:
        category = self.configurator_tree.set(char, 'category')
        return (category, rect_text, auto_text, self._configurator_mode_label(char))
    def _update_configurator_row(self, char: str):
        if not self.configurator_tree.exists(char):
            return
        rect_text = self.configurator_tree.set(char, 'rectilinear')
        auto_text = self.configurator_tree.set(char, 'auto')
        self.configurator_tree.item(char, values=self._configurator_tree_row_values(char, rect_text, auto_text))
    def _rescan_configurator_glyphs(self):
        self.configurator_tree.delete(*self.configurator_tree.get_children())
        self._configurator_scan_cache.clear()
        self._configurator_fit_cache.clear()
        self._configurator_detail_generation += 1
        self._configurator_selected_char = None
        self.configurator_detail_status_var.set('Select a glyph on the left.')
        self.configurator_preview_canvas.delete('all')

        raw_path = self.configurator_font_var.get().strip()
        font_path = Path(raw_path) if raw_path else None
        if font_path is None:
            self.configurator_scan_status_var.set('Enter or browse to a font first.')
            self._configurator_font = None
            return
        if not font_path.exists():
            self.configurator_scan_status_var.set(f'Font not found: {font_path}')
            self._configurator_font = None
            return
        self._configurator_font = font_path

        self._configurator_overrides = {
            char: dict(entry) for char, entry in
            glyph_overrides_store.load_overrides_for_font(font_path).items()
        }
        entries = self._configurator_char_list()
        if not entries:
            self.configurator_scan_status_var.set('This font has no glyphs.')
            return

        self._configurator_scan_generation += 1
        generation = self._configurator_scan_generation
        segments = max(1, int(self.segments_var.get()))

        self.configurator_scan_status_var.set(f'Loading {len(entries)} glyph row(s)…')
        self._configurator_insert_rows_chunked(entries, generation, segments)

    def _configurator_insert_rows_chunked(self, entries: list[tuple[str, str]], generation: int,
                                           segments: int, start: int = 0) -> None:
        """Insert glyph rows in `_CONFIGURATOR_INSERT_CHUNK`-sized batches via
        `root.after` rather than one synchronous loop (see the class-level
        comment on that constant for why). Bails out via the same
        generation-check pattern `_apply_configurator_scan_result` already
        uses if a newer rescan supersedes this one mid-batch — a stale rescan
        must not keep inserting rows into a tree a fresher one already
        cleared.

        The background fitting pass only starts once every row exists (see
        the call to `_start_configurator_scan_worker` below): its results
        arrive keyed by character and get applied via
        `configurator_tree.exists(char)` — a fit result racing ahead of that
        character's own row being inserted would just be silently dropped.
        """
        if generation != self._configurator_scan_generation:
            return
        chunk = entries[start:start + self._CONFIGURATOR_INSERT_CHUNK]
        for char, category in chunk:
            self.configurator_tree.insert('', 'end', iid=char, text=char,
                                           values=(category, '…', 'select to fit',
                                                   self._configurator_mode_label(char)))
        next_start = start + len(chunk)
        if next_start < len(entries):
            self.root.after(1, self._configurator_insert_rows_chunked,
                            entries, generation, segments, next_start)
            return
        self.configurator_scan_status_var.set(f'Inspecting {len(entries)} glyph outline(s)…')
        self._start_configurator_scan_worker(entries, generation, segments)

    def _start_configurator_scan_worker(self, entries: list[tuple[str, str]], generation: int,
                                        segments: int) -> None:
        font_path = self._configurator_font

        def scan_worker():
            for char, _category in entries:
                if generation != self._configurator_scan_generation:
                    return
                entry = self._configurator_overrides.get(char)
                if entry and entry['mode'] == 'manual':
                    # Manually-assigned glyphs skip auto-fit entirely —
                    # there's no strategy/eligibility to probe for them.
                    info = {'manual': True}
                else:
                    try:
                        info = inspect_glyph_geometry(char, font_path, segments)
                    except Exception as exc:
                        info = {'error': str(exc)}
                self.msg_queue.put(('configurator_glyph_scanned', generation, char, info))
            self.msg_queue.put(('configurator_scan_done', generation, len(entries)))

        threading.Thread(target=scan_worker, daemon=True).start()
    def _apply_configurator_scan_result(self, char: str, info: dict):
        if not self.configurator_tree.exists(char):
            return
        self._configurator_scan_cache[char] = info
        if info.get('manual'):
            self.configurator_tree.item(char, values=self._configurator_tree_row_values(char, '—', '(manual file)'))
        elif 'error' in info:
            self.configurator_tree.item(
                char, values=self._configurator_tree_row_values(char, '?', f"error: {info['error']}"))
        else:
            rect_text = 'yes' if info['rectilinear'] else 'no'
            auto_text = (f"{info['auto_strategy']} ({info['auto_shape_count']})"
                         if info.get('auto_strategy') else 'select to fit')
            self.configurator_tree.item(char, values=self._configurator_tree_row_values(char, rect_text, auto_text))
    def _on_configurator_glyph_selected(self, _event=None):
        sel = self.configurator_tree.selection()
        if not sel:
            return
        char = sel[0]
        self._configurator_selected_char = char
        entry = self._configurator_overrides.get(char, {'mode': 'auto'})
        self.configurator_mode_var.set(entry['mode'])
        self._refresh_configurator_detail(char)
    def _on_configurator_mode_changed(self):
        # The three radios only ever set auto/force/never — "manual" is
        # reached exclusively through _configurator_assign_file below, but
        # picking a radio here while a manual glyph is selected correctly
        # drops that assignment in favor of auto-fit.
        char = self._configurator_selected_char
        if char is None:
            return
        mode = self.configurator_mode_var.get()
        if mode == 'auto':
            self._configurator_overrides.pop(char, None)
        else:
            self._configurator_overrides[char] = {'mode': mode}
        self._update_configurator_row(char)
        self._save_configurator_overrides()
        self._refresh_configurator_detail(char)
    def _configurator_assign_file(self):
        char = self._configurator_selected_char
        if char is None:
            self._log('Select a glyph first.', tag='warn')
            return
        chosen = filedialog.askopenfilename(filetypes=[('JSON', '*.json'), ('all files', '*.*')])
        if not chosen:
            return
        self._configurator_overrides[char] = {'mode': 'manual', 'file': chosen}
        self.configurator_mode_var.set('manual')  # no radio has this value — correctly shows none selected
        self._update_configurator_row(char)
        self._save_configurator_overrides()
        self._refresh_configurator_detail(char)
    def _refresh_configurator_detail(self, char: str, compute_forced: bool = False):
        if self._configurator_font is None:
            return
        # Invalidates any older in-flight detail worker, including when the
        # new selection is a manual file that needs no worker of its own.
        self._configurator_detail_generation += 1
        generation = self._configurator_detail_generation
        entry = self._configurator_overrides.get(char, {'mode': 'auto'})
        mode = entry['mode']
        p = gui_theme.palette()

        if mode == 'manual':
            if self.configurator_force_rb is not None:
                self.configurator_force_rb.configure(state='normal')
            try:
                data = json.loads(Path(entry['file']).read_text(encoding='utf-8'))
                shapes = data.get('shapes', [])
            except Exception as exc:
                self.configurator_detail_status_var.set(f"Couldn't read {entry['file']!r}: {exc}")
                return
            image = file_preview.render_json_preview(shapes, LIVE_PREVIEW_SIZE, bg=p['canvas_bg'], fg=p['fg'])
            self._configurator_preview_photo = ImageTk.PhotoImage(image)
            self.configurator_preview_canvas.delete('all')
            self.configurator_preview_canvas.create_image(0, 0, anchor='nw', image=self._configurator_preview_photo)
            mask_count = sum(1 for s in shapes if s.get('mask'))
            self.configurator_detail_status_var.set(
                f"{char!r}: {len(shapes)} shape(s), {mask_count} mask cutout(s) "
                f"— manual: {Path(entry['file']).name}")
            return

        segments = max(1, int(self.segments_var.get()))
        requested_backend = self.compute_backend_var.get()
        cache_key = (str(self._configurator_font), char, mode, segments, requested_backend,
                     bool(compute_forced))
        cached = self._configurator_fit_cache.get(cache_key)
        if cached is not None:
            self._apply_configurator_detail(char, cached)
            return

        font_path = self._configurator_font
        self.configurator_detail_status_var.set(
            f'Analyzing {char!r} in the background ({requested_backend.upper()})…')

        def detail_worker():
            self._configurator_fit_lock.acquire()
            try:
                if generation != self._configurator_detail_generation:
                    return
                backend = gen_modelbin_gui.resolve_backend(requested_backend)
                if requested_backend in ('cuda', 'directml') and not backend.available:
                    raise RuntimeError(backend.detail)
                info = preview_glyph_mask_options(
                    char, font_path, segments,
                    curved_force_check=(compute_forced or mode == 'force'),
                    compute_backend=backend.resolved, return_placements=True)
                effective_mode = mode
                if mode == 'force' and not info.get('can_force_mask'):
                    effective_mode = 'auto'
                placements = None
                strategy = None
                if effective_mode == 'auto' or (effective_mode == 'never' and not info['rectilinear']):
                    placements = info.get('_auto_placements')
                    strategy = info['auto_strategy']
                elif effective_mode == 'force':
                    placements = info.get('_forced_placements')
                    strategy = 'stencil' if info['rectilinear'] else 'stencil_search'
                if placements is not None:
                    shapes = placements_to_shapes(placements, DEFAULT_RESOLUTION)
                else:
                    shapes, strategy = fit_glyph_with_strategy(
                        char, font_path, segments, mask_mode=effective_mode,
                        compute_backend=backend.resolved)
                info = {key: value for key, value in info.items() if not key.startswith('_')}
                image = file_preview.render_json_preview(
                    shapes, LIVE_PREVIEW_SIZE, bg=p['canvas_bg'], fg=p['fg'])
                result = {
                    'info': info, 'shapes': shapes, 'strategy': strategy,
                    'image': image, 'backend': backend, 'effective_mode': effective_mode,
                }
                self._configurator_fit_cache[cache_key] = result
                self.msg_queue.put(('configurator_detail_ready', generation, char, result))
            except Exception as exc:
                self.msg_queue.put(('configurator_detail_error', generation, char, str(exc)))
            finally:
                self._configurator_fit_lock.release()

        threading.Thread(target=detail_worker, daemon=True).start()
    def _apply_configurator_detail(self, char: str, result: dict):
        info = result['info']
        shapes = result['shapes']
        strategy = result['strategy']
        self._configurator_scan_cache[char] = info
        if self.configurator_tree.exists(char):
            rect_text = 'yes' if info['rectilinear'] else 'no'
            auto_text = f"{info['auto_strategy']} ({info['auto_shape_count']})"
            self.configurator_tree.item(
                char, values=self._configurator_tree_row_values(char, rect_text, auto_text))

        can_force = info.get('can_force_mask', False)
        if self.configurator_force_rb is not None:
            self.configurator_force_rb.configure(state='normal' if can_force else 'disabled')
        if result['effective_mode'] != self.configurator_mode_var.get():
            self.configurator_mode_var.set(result['effective_mode'])

        self._configurator_preview_photo = ImageTk.PhotoImage(result['image'])
        self.configurator_preview_canvas.delete('all')
        self.configurator_preview_canvas.create_image(
            0, 0, anchor='nw', image=self._configurator_preview_photo)
        mask_count = sum(1 for shape in shapes if shape.get('mask'))
        backend = result['backend']
        status = (f'{char!r}: {len(shapes)} shape(s), {mask_count} mask cutout(s) '
                  f'({strategy}, {backend.resolved.upper()}).')
        if (not info.get('rectilinear', True) and info.get('can_force_mask')
                and info.get('forced_iou') is not None):
            status += (f" Forcing costs IoU {info['forced_iou']:.2f} at "
                       f"{info['forced_shape_count']} shape(s).")
        self.configurator_detail_status_var.set(status)
    def _save_configurator_overrides(self):
        if self._configurator_font is None:
            return
        try:
            glyph_overrides_store.save_overrides_for_font(self._configurator_font, self._configurator_overrides)
        except OSError as exc:
            self._log(f'Could not save glyph overrides: {exc}', tag='warn')
    def _configurator_reset_all(self):
        if not self._configurator_overrides and not self.configurator_tree.get_children():
            return
        self._configurator_overrides = {}
        for char in self.configurator_tree.get_children():
            self._update_configurator_row(char)
        self._save_configurator_overrides()
        if self._configurator_selected_char is not None:
            self.configurator_mode_var.set('auto')
            self._refresh_configurator_detail(self._configurator_selected_char)
    def _configurator_force_all_rectilinear(self):
        # Cheap — every rectilinear glyph's can_force_mask is already known
        # from the bulk scan (rectilinear eligibility never needs the
        # curved search), so this never triggers the expensive per-glyph
        # check the way forcing a curved glyph individually would. Manual
        # glyphs are left untouched — forcing a mask on them would silently
        # discard the file assignment, which isn't what "force mask on all
        # eligible" should do.
        changed = 0
        for char in self.configurator_tree.get_children():
            info = self._configurator_scan_cache.get(char)
            current = self._configurator_overrides.get(char, {'mode': 'auto'})
            if (info and current.get('mode') != 'manual' and info.get('rectilinear')
                    and info.get('can_force_mask')):
                self._configurator_overrides[char] = {'mode': 'force'}
                self._update_configurator_row(char)
                changed += 1
        self._save_configurator_overrides()
        self.configurator_scan_status_var.set(f'Forced mask on {changed} eligible rectilinear glyph(s).')
        if self._configurator_selected_char is not None:
            entry = self._configurator_overrides.get(self._configurator_selected_char, {'mode': 'auto'})
            self.configurator_mode_var.set(entry['mode'])
            self._refresh_configurator_detail(self._configurator_selected_char)
