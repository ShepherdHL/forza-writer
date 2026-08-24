"""Output tab: browsing previously-generated fontpacks and their glyphs.
"""

import colorsys
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
from forza_writer.forza_colors import describe_color, forza_hsb_to_rgb, hex_to_rgb, rgb_to_forza_hsb  # noqa: E402
from forza_writer import manufacturer_colors  # noqa: E402
from forza_writer.variable_fonts import (  # noqa: E402
    VariableFontInfo, inspect_variable_font, instantiate_font, variation_slug)

from ..state import (  # noqa: E402
    FONT_EXTENSIONS, FONTS_DIR_SYSTEM, GRID_MAX_TILES, GRID_TILE_GAP, GRID_TILE_SIZE,
    ICON_PATH, LIVE_PREVIEW_SIZE, COMPOSE_PREVIEW_SIZE, OUTPUT_MODE_LABELS, PREVIEW_SIZE,
    SIDEBAR_WIDTH, TABS, TAB_LABELS, _MODE_LABELS, direct_output_filename,
    enumerate_installed_fonts, is_running_as_administrator, sidebar_tab_text)


class OutputsTabMixin:
    def _build_outputs_page(self):
        page = ttk.Frame(self.page_container)
        self._pages['outputs'] = page
        content = self._build_scroll_shell(page, 'outputs')

        ttk.Label(content,
                  text='Browse fontpacks you\'ve already generated. Pick one on the left to list its '
                       'glyphs, then pick a glyph to preview it — or browse any .json/.modelbin file '
                       'directly below, whether or not it belongs to a recognized pack.',
                  style='Intro.TLabel', wraplength=gui_theme.WRAP_WIDE,
                  justify='left').pack(fill='x', **gui_theme.PAGE_INTRO_PAD)

        root_frame = ttk.LabelFrame(content, text=gui_theme.hud_label('Fontpack Root Folder'))
        root_frame.pack(fill='x', **gui_theme.SECTION_PAD)
        root_row = ttk.Frame(root_frame)
        root_row.pack(fill='x', **gui_theme.ROW_PAD)
        self.outputs_root_var = tk.StringVar(value=self.out_var.get())
        ttk.Entry(root_row, textvariable=self.outputs_root_var).pack(side='left', fill='x', expand=True, padx=4)
        ttk.Button(root_row, text='Browse...', command=self._pick_outputs_root).pack(side='left', padx=2)
        ttk.Button(root_row, text='Refresh', command=self._refresh_outputs_pack_list).pack(side='left', padx=2)

        # Fixed line-count height (not a pixel guess) — inside the page's
        # own scroll canvas these size to their natural/requested height
        # rather than stretching to fill the window, so an explicit
        # height keeps them at a genuinely useful size instead of
        # collapsing to Tk's Listbox default of 10.
        lists_frame = ttk.Frame(content)
        lists_frame.pack(fill='both', expand=True, **gui_theme.SECTION_PAD)

        pack_col = ttk.LabelFrame(lists_frame, text=gui_theme.hud_label('Fontpacks'))
        pack_col.pack(side='left', fill='both', expand=True, padx=(0, 4))
        pack_list_row = ttk.Frame(pack_col)
        pack_list_row.pack(fill='both', expand=True, padx=4, pady=4)
        self.outputs_pack_listbox = tk.Listbox(pack_list_row, height=12, exportselection=False)
        pack_scroll = gui_theme.AutoHideScrollbar(
            pack_list_row, orient='vertical', command=self.outputs_pack_listbox.yview)
        self.outputs_pack_listbox.configure(yscrollcommand=pack_scroll.set)
        self.outputs_pack_listbox.pack(side='left', fill='both', expand=True,
                                        padx=(0, gui_theme.SCROLLBAR_GUTTER))
        pack_scroll.pack(side='right', fill='y')
        self.outputs_pack_listbox.bind('<<ListboxSelect>>', self._on_outputs_pack_selected)
        self._register_independent_scroll(self.outputs_pack_listbox)

        glyph_col = ttk.LabelFrame(lists_frame, text=gui_theme.hud_label('Glyphs'))
        glyph_col.pack(side='left', fill='both', expand=True, padx=(4, 0))
        glyph_list_row = ttk.Frame(glyph_col)
        glyph_list_row.pack(fill='both', expand=True, padx=4, pady=4)
        self.outputs_glyph_listbox = tk.Listbox(glyph_list_row, height=12, exportselection=False)
        glyph_scroll = gui_theme.AutoHideScrollbar(
            glyph_list_row, orient='vertical', command=self.outputs_glyph_listbox.yview)
        self.outputs_glyph_listbox.configure(yscrollcommand=glyph_scroll.set)
        self.outputs_glyph_listbox.pack(side='left', fill='both', expand=True,
                                         padx=(0, gui_theme.SCROLLBAR_GUTTER))
        glyph_scroll.pack(side='right', fill='y')
        self.outputs_glyph_listbox.bind('<<ListboxSelect>>', self._on_outputs_glyph_selected)
        self._register_independent_scroll(self.outputs_glyph_listbox)

        # Preview — also doubles as "browse any file directly" for a file
        # outside any recognized pack. No in-app shape editor since KFPS's
        # own is better; this is just "let me see what's actually in this
        # file" for a .json (primitive-composition, mask cutouts rendered
        # as actual erase-to-background) or .modelbin (flat mesh fill).
        preview_frame = ttk.LabelFrame(content, text=gui_theme.hud_label('Preview'))
        preview_frame.pack(fill='x', **gui_theme.SECTION_PAD)
        preview_row = ttk.Frame(preview_frame)
        preview_row.pack(fill='x', **gui_theme.ROW_PAD)
        ttk.Label(preview_row, text='Or browse any file directly:').pack(side='left')
        self.preview_path_var = tk.StringVar()
        ttk.Entry(preview_row, textvariable=self.preview_path_var).pack(
            side='left', fill='x', expand=True, padx=4)
        ttk.Button(preview_row, text='Browse...', command=self._pick_preview_file).pack(side='left', padx=2)
        ttk.Button(preview_row, text='Preview', command=self._show_preview).pack(side='left', padx=2)

        preview_body = ttk.Frame(preview_frame)
        preview_body.pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)
        self.preview_canvas = tk.Canvas(preview_body, width=PREVIEW_SIZE[0],
                                         height=PREVIEW_SIZE[1], highlightthickness=1)
        self.preview_canvas.pack(side='left')
        self.preview_stats_var = tk.StringVar(value='Pick a fontpack on the left, or browse a file directly.')
        self.preview_stats_lbl = ttk.Label(
            preview_body, textvariable=self.preview_stats_var, style='Hint.TLabel',
            wraplength=gui_theme.WRAP_NARROW, justify='left')
        self.preview_stats_lbl.pack(side='left', anchor='n', padx=(10, 0))

        self._outputs_packs: list[tuple[Path, dict]] = []
        self._outputs_glyph_entries: list[tuple[str, dict]] = []
        self._outputs_current_pack_dir: Path | None = None
    def _pick_outputs_root(self):
        chosen = filedialog.askdirectory(initialdir=self.outputs_root_var.get())
        if chosen:
            self.outputs_root_var.set(chosen)
            self._refresh_outputs_pack_list()
    def _refresh_outputs_pack_list(self):
        self.outputs_pack_listbox.delete(0, 'end')
        self._outputs_packs = []
        root_dir = Path(self.outputs_root_var.get())
        if not root_dir.exists():
            return
        for manifest_path in sorted(root_dir.glob('*/*/manifest.json')):
            try:
                manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
            pack_dir = manifest_path.parent
            self._outputs_packs.append((pack_dir, manifest))
            total_glyphs = sum(len(v) for v in manifest.get('categories', {}).values())
            self.outputs_pack_listbox.insert(
                'end', f"{manifest.get('prefix', pack_dir.name)} "
                       f"[{manifest.get('generation_profile', {}).get('id', manifest.get('output', '?'))}] "
                       f"({total_glyphs} glyphs)")
    def _on_outputs_pack_selected(self, _event=None):
        sel = self.outputs_pack_listbox.curselection()
        if not sel:
            return
        pack_dir, manifest = self._outputs_packs[sel[0]]
        self._outputs_current_pack_dir = pack_dir
        self.outputs_glyph_listbox.delete(0, 'end')
        self._outputs_glyph_entries = []
        for category in CATEGORY_ORDER:
            for entry in manifest.get('categories', {}).get(category, []):
                artifact = entry.get('artifacts', {}).get('json') or entry.get('artifacts', {}).get('modelbin')
                label = f"{category}  {entry['char']!r}"
                if artifact and artifact.get('strategy'):
                    label += f"  ({artifact['strategy']})"
                quality = artifact.get('quality') if artifact else None
                if quality:
                    label += (f"  [{'PASS' if quality['verdict'] == 'pass' else 'REVIEW'} "
                              f"{quality['iou']:.2f}]")
                self.outputs_glyph_listbox.insert('end', label)
                self._outputs_glyph_entries.append((category, entry))
    def _on_outputs_glyph_selected(self, _event=None):
        sel = self.outputs_glyph_listbox.curselection()
        if not sel or self._outputs_current_pack_dir is None:
            return
        _category, entry = self._outputs_glyph_entries[sel[0]]
        artifact = entry.get('artifacts', {}).get('json') or entry.get('artifacts', {}).get('modelbin')
        if not artifact or not artifact.get('file'):
            return
        file_path = self._outputs_current_pack_dir / artifact['file']
        self.preview_path_var.set(str(file_path))
        p = gui_theme.palette()
        image = file_preview.render_file_preview(file_path, PREVIEW_SIZE, bg=p['canvas_bg'], fg=p['fg'])
        self._preview_photo = ImageTk.PhotoImage(image)
        self.preview_canvas.delete('all')
        self.preview_canvas.create_image(0, 0, anchor='nw', image=self._preview_photo)
        stats_text, stats_style = self._preview_stats_text(file_path)
        self.preview_stats_var.set(stats_text)
        self.preview_stats_lbl.configure(style=stats_style)
