"""Generator tab: font discovery/selection (list + grid view, script
filtering, alphabet groups), character selection, and the main preview/export row.
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
import vinyl_tiles  # noqa: E402
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
from forza_writer.generation_policy import (  # noqa: E402
    DEFAULT_POLICY, FALLBACK_LABELS, FALLBACK_MODES, PRESET_LABELS, PRESETS,
    RECOMMENDED_PRESET, GenerationPolicy, policy_from_dict, policy_to_dict, preset_name_for)
from forza_writer.primitive_shapes import PRIMITIVE_CATALOG  # noqa: E402
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


class GeneratorTabMixin:
    def _build_generator_page(self):
        page = ttk.Frame(self.page_container)
        self._pages['generator'] = page
        content = self._build_scroll_shell(page, 'generator')

        ttk.Label(content,
                  text='Generate a new fontpack: pick a font, choose which characters to include, '
                       'pick an output type, then click Generate below.',
                  style='Intro.TLabel', wraplength=gui_theme.WRAP_WIDE,
                  justify='left').pack(fill='x', **gui_theme.PAGE_INTRO_PAD)

        # Font picker: search box + list/grid toggle + list
        font_frame = ttk.LabelFrame(content, text=gui_theme.hud_label('1. Font'))
        font_frame.pack(fill='both', expand=True, **gui_theme.SECTION_PAD)

        # The installed-font registry is scanned automatically in the
        # background as soon as the window opens (see __init__): this is a
        # fast registry-only scan (~512 fonts well under a second, measured
        # on this machine), unlike the per-file script-classification pass
        # that follows it. "Rescan Fonts" re-runs the same scan on demand
        # (e.g. after installing a new font without restarting); "Browse on
        # machine..." skips the installed-font list entirely and picks one
        # file directly, mirroring the split forza-painter-fh6 uses in its
        # own Text Vinyl tab, for consistency.
        load_row = ttk.Frame(font_frame)
        load_row.pack(fill='x', **gui_theme.ROW_PAD_TOP)
        self.load_fonts_btn = ttk.Button(load_row, text='Rescan Fonts', command=self._load_all_fonts)
        self.load_fonts_btn.pack(side='left')
        ttk.Button(load_row, text='Browse on machine...',
                   command=self._browse_font_on_machine).pack(side='left', padx=(6, 0))
        self.font_scan_status_var = tk.StringVar(value="Scanning installed fonts…")
        ttk.Label(font_frame, textvariable=self.font_scan_status_var, style='Hint.TLabel',
                  wraplength=gui_theme.WRAP_MED, justify='left').pack(fill='x', **gui_theme.ROW_PAD_TOP)

        search_row = ttk.Frame(font_frame)
        search_row.pack(fill='x', **gui_theme.ROW_PAD)
        ttk.Label(search_row, text='Search:').pack(side='left')
        self.search_var = tk.StringVar()
        self.search_var.trace_add('write', lambda *_: self._refresh_font_list())
        ttk.Entry(search_row, textvariable=self.search_var).pack(
            side='left', fill='x', expand=True, padx=4)

        # Script sub-tabs: filter the (already-loaded) font list down to
        # fonts whose cmap actually appears to support a given script.
        # This is prep work for non-Latin generation support, not full
        # support itself yet (see forza_writer/script_detect.py's module
        # docstring for how "appears to support" is decided). Classified
        # in the background right after the startup font scan finishes,
        # streamed in via the same queue/_poll_queue pattern as font-grid
        # tiles, so a script tab just shows fewer fonts until classification
        # for the rest streams in, rather than blocking on the whole pass.
        script_tab_frame = ttk.Frame(font_frame)
        script_tab_frame.pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)
        self._script_filter: str | None = None
        self._script_tab_labels: dict[str | None, tk.Label] = {}
        script_tab_names = [None] + list(script_detect.SCRIPTS)
        for i, script in enumerate(script_tab_names):
            lbl = tk.Label(script_tab_frame, text=(script or 'All'), padx=8, pady=3, cursor='hand2')
            lbl.grid(row=i // 6, column=i % 6, sticky='ew', padx=1, pady=1)
            lbl.bind('<Button-1>', lambda _e, s=script: self._select_script_filter(s))
            self._script_tab_labels[script] = lbl
        for col in range(6):
            script_tab_frame.columnconfigure(col, weight=1)
        ttk.Label(font_frame,
                  text='Optional: narrows the list below to fonts that appear to support the selected '
                       'script (detected in the background after fonts finish loading). Filtering/'
                       'browsing only for now — Characters below still uses the ASCII sets regardless '
                       'of script.',
                  style='Hint.TLabel', wraplength=gui_theme.WRAP_MED,
                  justify='left').pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)

        view_row = ttk.Frame(font_frame)
        view_row.pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)
        ttk.Label(view_row, text='View:').pack(side='left')
        ttk.Radiobutton(view_row, text='List', variable=self.font_view_var, value='list',
                         command=self._on_font_view_changed).pack(side='left', padx=(4, 0))
        ttk.Radiobutton(view_row, text='Grid', variable=self.font_view_var, value='grid',
                         command=self._on_font_view_changed).pack(side='left')

        # Grid overflow/status belongs on its own full-width line above the
        # browser. Packing it inside grid_outer instead would reserve a wide
        # strip beside the canvas for pack's side geometry, reducing the
        # number of font tiles that fit across the row.
        self.grid_status_var = tk.StringVar()
        self.grid_status_lbl = ttk.Label(
            font_frame, textvariable=self.grid_status_var, style='Hint.TLabel')

        list_row = ttk.Frame(font_frame)
        list_row.pack(fill='both', expand=True, **gui_theme.ROW_PAD)
        font_count_panel = ttk.LabelFrame(
            list_row, text=gui_theme.hud_label('Font Contents'), width=165)
        font_count_panel.pack(side='right', fill='y', padx=(8, 0))
        font_count_panel.pack_propagate(False)
        self.font_character_total_var = tk.StringVar(value='—')
        ttk.Label(
            font_count_panel, textvariable=self.font_character_total_var,
            style='Title.TLabel', anchor='center', justify='center').pack(
                fill='x', padx=8, pady=(14, 2))
        ttk.Label(
            font_count_panel, text='usable characters in font',
            style='Hint.TLabel', anchor='center', justify='center',
            wraplength=140).pack(fill='x', padx=8)
        self.fontpack_character_count_var = tk.StringVar(value='Select a font')
        ttk.Label(
            font_count_panel, textvariable=self.fontpack_character_count_var,
            style='Hint.TLabel', anchor='center', justify='center',
            wraplength=140).pack(fill='x', padx=8, pady=(14, 8))
        self.font_list = tk.Listbox(list_row, height=8, exportselection=False)
        scroll = gui_theme.AutoHideScrollbar(list_row, orient='vertical', command=self.font_list.yview)
        self.font_list.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y', padx=(gui_theme.SCROLLBAR_GUTTER, 0))
        self.font_list.pack(side='left', fill='both', expand=True, padx=(0, gui_theme.SCROLLBAR_GUTTER))
        self.font_list.bind('<<ListboxSelect>>', self._on_font_selected)
        self._register_independent_scroll(self.font_list)

        # Grid view: built but not packed; _on_font_view_changed swaps it
        # in for font_list's list_row when the user picks "Grid".
        self.grid_outer = ttk.Frame(font_frame)
        self.grid_canvas = tk.Canvas(self.grid_outer, height=200, highlightthickness=0)
        grid_scroll = gui_theme.AutoHideScrollbar(self.grid_outer, orient='vertical', command=self.grid_canvas.yview)
        self.grid_canvas.configure(yscrollcommand=grid_scroll.set)
        self.grid_canvas.pack(side='left', fill='both', expand=True, padx=(0, gui_theme.SCROLLBAR_GUTTER))
        grid_scroll.pack(side='right', fill='y')
        self._register_independent_scroll(self.grid_canvas)
        # Match the canvas behind it so short/filtered result sets read as
        # one continuous recessed browser surface rather than a raised strip
        # ending abruptly above a differently-colored empty area.
        self.grid_inner = ttk.Frame(self.grid_canvas, style='Grid.TFrame')
        self._grid_window = self.grid_canvas.create_window((0, 0), window=self.grid_inner, anchor='nw')
        self.grid_inner.bind('<Configure>',
                              lambda _e: self.grid_canvas.configure(scrollregion=self.grid_canvas.bbox('all')))
        self.grid_canvas.bind('<Configure>', self._on_grid_canvas_configure)
        self.font_path_var = tk.StringVar(value='(no font selected)')
        ttk.Label(font_frame, textvariable=self.font_path_var,
                  style='Hint.TLabel').pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)
        self.lowercase_warning_var = tk.StringVar(value='')
        ttk.Label(font_frame, textvariable=self.lowercase_warning_var, style='Warn.TLabel',
                  wraplength=gui_theme.WRAP_MED, justify='left').pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)
        self.large_font_warning_var = tk.StringVar(value='')
        ttk.Label(font_frame, textvariable=self.large_font_warning_var, style='Warn.TLabel',
                  wraplength=gui_theme.WRAP_MED, justify='left').pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)
        variation_row = ttk.Frame(font_frame)
        variation_row.pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)
        self.font_variation_status_var = tk.StringVar(value='')
        ttk.Label(variation_row, textvariable=self.font_variation_status_var, style='Hint.TLabel',
                  wraplength=gui_theme.WRAP_MED, justify='left').pack(
                      fill='x')
        # Keep transfer actions on their own row. Variable-font status text
        # can be long (especially for CJK fonts with many named instances);
        # sharing a packed row let that label consume the buttons' space.
        self.generator_transfer_row = ttk.Frame(font_frame)
        self.generator_transfer_row.pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)
        self.generator_transfer_row.columnconfigure(0, weight=1)
        self.generator_transfer_row.columnconfigure(1, weight=1)
        self.generator_to_advanced_btn = ttk.Button(
            self.generator_transfer_row, text='Send selected font to Advanced Generator',
            command=self._open_current_font_in_advanced)
        self.generator_to_advanced_btn.grid(row=0, column=1, sticky='ew', padx=(3, 0))
        self.generator_to_direct_btn = ttk.Button(
            self.generator_transfer_row, text='Send selected font to Direct Generator',
            command=self._open_current_font_in_direct)
        self.generator_to_direct_btn.grid(row=0, column=0, sticky='ew', padx=(0, 3))

        # Character selection
        chars_frame = ttk.LabelFrame(content, text=gui_theme.hud_label('2. Characters'))
        chars_frame.pack(fill='x', **gui_theme.SECTION_PAD)
        self.all_var = tk.BooleanVar(value=False)
        self.all_cb = ttk.Checkbutton(
            chars_frame, text='Entire font character map (advanced)', variable=self.all_var,
            command=self._on_all_toggled)
        self.all_cb.pack(anchor='w', **gui_theme.ROW_PAD_TOP)
        ttk.Label(chars_frame, text='Generates every character the selected font has a glyph for, '
                                     'ignoring the checkboxes below. This can mean thousands of glyphs.',
                  style='Hint.TLabel', wraplength=gui_theme.WRAP_MED,
                  justify='left').pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)

        self.upper_var = tk.BooleanVar(value=True)
        self.lower_var = tk.BooleanVar(value=True)
        self.digits_var = tk.BooleanVar(value=True)
        self.punct_var = tk.BooleanVar(value=True)
        self.symbols_var = tk.BooleanVar(value=False)
        self.private_var = tk.BooleanVar(value=False)
        row = ttk.Frame(chars_frame)
        row.pack(fill='x', **gui_theme.ROW_PAD)
        selection_changed = self._on_character_selection_changed
        self.upper_cb = ttk.Checkbutton(row, text='Latin uppercase A-Z (26)', variable=self.upper_var,
                                        command=selection_changed)
        self.lower_cb = ttk.Checkbutton(row, text='Latin lowercase a-z (26)', variable=self.lower_var,
                                        command=selection_changed)
        self.digits_cb = ttk.Checkbutton(row, text='ASCII digits 0-9 (10)', variable=self.digits_var,
                                         command=selection_changed)
        self.punct_cb = ttk.Checkbutton(row, text='ASCII punctuation (32)', variable=self.punct_var,
                                        command=selection_changed)
        self.symbols_cb = ttk.Checkbutton(row, text='Unicode symbols in font', variable=self.symbols_var,
                                          command=selection_changed)
        self.private_cb = ttk.Checkbutton(row, text='Private-use glyphs (advanced)',
                                          variable=self.private_var, command=selection_changed)
        for index, cb in enumerate((self.upper_cb, self.lower_cb, self.digits_cb, self.punct_cb,
                                    self.symbols_cb, self.private_cb)):
            cb.grid(row=index // 3, column=index % 3, sticky='w', padx=4, pady=2)
        for column in range(3):
            row.columnconfigure(column, weight=1)
        row2 = ttk.Frame(chars_frame)
        row2.pack(fill='x', **gui_theme.ROW_PAD)
        ttk.Label(row2, text='Extra characters:').pack(side='left', padx=4)
        self.custom_var = tk.StringVar()
        self.custom_var.trace_add('write', lambda *_: self._on_character_selection_changed())
        self.custom_entry = ttk.Entry(row2, textvariable=self.custom_var)
        self.custom_entry.pack(side='left', fill='x', expand=True, padx=4)
        ttk.Button(row2, text='Use only this text',
                   command=self._select_only_custom_text).pack(side='left', padx=4)
        ttk.Label(chars_frame,
                  text='Output is sorted into Uppercase/Lowercase/Letters/Numbers/Punctuation/Symbols '
                       'folders automatically, dafont-charmap style.',
                  style='Hint.TLabel', wraplength=gui_theme.WRAP_MED,
                  justify='left').pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)

        # Non-Latin alphabets: real generation support (not just the
        # Font section's script-tab filtering) for the 7 scripts that fit
        # this tool's flat one-glyph-per-character model (see
        # forza_writer/alphabets.py's module docstring for the shaping
        # caveats, e.g. Arabic renders isolated letterforms, Korean
        # renders individual Jamo not composed syllable blocks). Every
        # script's checkboxes are built once and stay alive regardless of
        # which script tab is currently selected: selecting a different
        # script only changes which group is *visible*; a box checked
        # earlier still counts when generating, same "additive, not
        # exclusive" behavior the ASCII row above already has.
        self._alphabet_vars: dict[str, dict[str, tk.BooleanVar]] = {}
        self._all_han_vars: dict[str, tk.BooleanVar] = {}
        self._alphabet_group_frames: dict[str, ttk.Frame] = {}
        self._alphabet_checkbuttons: list[ttk.Checkbutton] = []
        self.alphabet_section = ttk.Frame(chars_frame)
        self.alphabet_section.pack(fill='x', **gui_theme.ROW_PAD)
        selectable_scripts = list(alphabets.ALPHABETS) + sorted(alphabets.NO_ALPHABET_SCRIPTS)
        for script in selectable_scripts:
            groups = alphabets.groups_for_script(script)
            group_frame = ttk.Frame(self.alphabet_section)
            self._alphabet_group_frames[script] = group_frame
            self._alphabet_vars[script] = {}
            box_row = ttk.Frame(group_frame)
            box_row.pack(fill='x', anchor='w')
            for label, letters in groups:
                var = tk.BooleanVar(value=False)
                self._alphabet_vars[script][label] = var
                cb = ttk.Checkbutton(box_row, text=f'{label} ({len(set(letters))})', variable=var,
                                     command=self._on_character_selection_changed)
                cb.pack(side='left', padx=4)
                self._alphabet_checkbuttons.append(cb)
            if script in alphabets.NO_ALPHABET_SCRIPTS:
                all_han_var = tk.BooleanVar(value=False)
                self._all_han_vars[script] = all_han_var
                all_han_cb = ttk.Checkbutton(
                    group_frame,
                    text='All Han ideographs supported by this font (advanced)',
                    variable=all_han_var, command=self._on_character_selection_changed)
                all_han_cb.pack(anchor='w', padx=4, pady=(4, 1))
                self._alphabet_checkbuttons.append(all_han_cb)
            ttk.Button(group_frame, text=f'Select only {script}',
                       command=lambda s=script: self._select_only_script(s)).pack(
                           anchor='w', padx=4, pady=(4, 1))
            caveat = alphabets.SHAPING_CAVEATS.get(script)
            if caveat:
                ttk.Label(group_frame, text=caveat, style='Warn.TLabel',
                          wraplength=gui_theme.WRAP_MED,
                          justify='left').pack(fill='x', anchor='w', padx=4, pady=(2, 0))
            if script in alphabets.NO_ALPHABET_SCRIPTS:
                ttk.Label(
                    group_frame,
                    text='Chinese has no small complete alphabet. These are bounded test sets; '
                         'for a usable pack, paste the exact Chinese text you need above.',
                    style='Warn.TLabel', wraplength=gui_theme.WRAP_MED,
                    justify='left').pack(fill='x', anchor='w', padx=4, pady=(2, 0))
        self.no_alphabet_hint_lbl = ttk.Label(
            self.alphabet_section,
            text="Chinese has no alphabet-sized complete set. Paste the exact text you need, "
                 "choose a bounded test set, or deliberately use the entire font option.",
            style='Hint.TLabel', wraplength=gui_theme.WRAP_MED, justify='left')
        self._update_alphabet_section()

        self.character_count_var = tk.StringVar(value='')
        self.character_count_lbl = ttk.Label(
            chars_frame, textvariable=self.character_count_var, style='Hint.TLabel',
            wraplength=gui_theme.WRAP_MED, justify='left')
        self.character_count_lbl.pack(fill='x', padx=4, pady=(5, 3))
        self._on_character_selection_changed()

        # Output mode
        output_frame = ttk.LabelFrame(content, text=gui_theme.hud_label('3. Output'))
        output_frame.pack(fill='x', **gui_theme.SECTION_PAD)
        self.output_var = tk.StringVar(value='json')
        for mode in OUTPUT_MODES:
            title, description = OUTPUT_MODE_LABELS[mode]
            # The modelbin path's description leads with "Experimental.";
            # give it the Warn style so that caveat actually reads as one,
            # rather than blending into the same muted tone as every other
            # secondary label.
            self._build_output_mode_option(
                output_frame, style=gui_theme.GENERATION_METHOD_STYLES[mode], title=title,
                description=description, variable=self.output_var, value=mode,
                command=self._on_output_mode_changed, warn_description=(mode == 'modelbin'))

        # Primitive Shapes (.json) only: a rectilinear glyph sometimes needs
        # fewer shapes as a stencil (background Square + mask cutouts) than
        # filled directly: real savings, not a routing bug (e.g. the
        # Minecraft Standard Galactic Alphabet's 'X' needs 14 shapes direct
        # vs. 10 stencil), but it relies on FH6 mask-layer semantics that
        # haven't been confirmed against a live session yet (RESEARCH.md).
        # Default on (it's a genuine improvement when it wins); this lets
        # anyone who'd rather avoid masks entirely opt out, at the cost of
        # a few more shapes on the glyphs where stencil would have won.
        self.allow_stencil_var = tk.BooleanVar(value=True)
        stencil_row = ttk.Frame(output_frame)
        stencil_row.pack(fill='x', padx=4, pady=(4, 3))
        ttk.Checkbutton(stencil_row, text='Allow layer masks (stencil mode)',
                         style='Stencil.TCheckbutton',
                         variable=self.allow_stencil_var).pack(anchor='w')
        ttk.Label(stencil_row,
                  text="Shape Fitting only. Lets a rectilinear glyph use a background square + mask "
                       "cutouts when that needs fewer shapes than filling it directly. Uncheck to force "
                       "direct fill everywhere (more shapes on some glyphs, no mask layers at all).",
                  style='Hint.TLabel', wraplength=gui_theme.WRAP_MED,
                  justify='left').pack(anchor='w', padx=gui_theme.INDENT_PAD)

        # Per-glyph control is recessed lower in this page. Keeping its
        # expensive font scan closed until requested keeps the common
        # generation path lightweight by default.
        glyph_link_row = ttk.Frame(output_frame)
        glyph_link_row.pack(fill='x', padx=4, pady=(4, 3))
        ttk.Button(glyph_link_row, text='Open per-glyph overrides…',
                   style='Iridium.TButton',
                   command=self._goto_configurator_for_current_font).pack(anchor='w')
        ttk.Label(glyph_link_row,
                  text="Shape Fitting only. Force or forbid a mask on individual glyphs — including "
                       "forcing one onto a curved glyph, not just a blocky one — or assign an "
                       "already-made file per glyph. The workspace below loads only when opened.",
                  style='Hint.TLabel', wraplength=gui_theme.WRAP_MED,
                  justify='left').pack(anchor='w', padx=gui_theme.INDENT_PAD)

        # Options: curve segments + prefix (per-run). Reference-modelbin
        # and the output directory are persistent paths owned by the
        # Settings tab; this section just shows what they're currently
        # set to, with a shortcut to go change them.
        opt_frame = ttk.LabelFrame(content, text=gui_theme.hud_label('4. Options'))
        opt_frame.pack(fill='x', **gui_theme.SECTION_PAD)

        seg_row = ttk.Frame(opt_frame)
        seg_row.pack(fill='x', **gui_theme.ROW_PAD)
        ttk.Label(seg_row, text='Curve Smoothness:').pack(side='left', padx=4)
        self.segments_var = tk.IntVar(value=8)
        ttk.Spinbox(seg_row, from_=1, to=32, width=5,
                    textvariable=self.segments_var).pack(side='left')
        ttk.Label(
            opt_frame,
            text='Curve Smoothness is the number of straight line segments used to approximate each '
                 'Bezier curve in the source font before generation. 1 replaces every curve with one '
                 'straight chord, making rounded glyphs angular and potentially removing small details; '
                 'higher values follow the original outline more closely but create more source points '
                 'and take longer. 8 is the balanced default. This affects Custom Mesh and Shape '
                 'Fitting output; Pixel Tracing uses its own rasterization.',
            style='Hint.TLabel', wraplength=gui_theme.WRAP_MED,
            justify='left').pack(fill='x', padx=gui_theme.INDENT_PAD,
                                 pady=gui_theme.ROW_PAD_BOTTOM['pady'])
        ttk.Label(
            opt_frame,
            text='Generated variants are stored separately by output, resolved processor, and curve '
                 'smoothness — each font gets one folder, with a subfolder per profile, for example '
                 'NOTO-SANS-JP/JSON-CUDA-CS1 — so CPU and CUDA comparisons do not overwrite each other.',
            style='Hint.TLabel', wraplength=gui_theme.WRAP_MED,
            justify='left').pack(fill='x', padx=gui_theme.INDENT_PAD,
                                 pady=gui_theme.ROW_PAD_BOTTOM['pady'])

        prefix_row = ttk.Frame(opt_frame)
        prefix_row.pack(fill='x', **gui_theme.ROW_PAD)
        ttk.Label(prefix_row, text='Filename prefix:').pack(side='left', padx=4)
        self.prefix_var = tk.StringVar(value='CUSTOM')
        self.prefix_var.trace_add('write', self._on_prefix_changed)
        self.prefix_entry = ttk.Entry(prefix_row, textvariable=self.prefix_var, width=30)
        self.prefix_entry.pack(side='left', padx=4)
        self.preview_var = tk.StringVar()
        ttk.Label(prefix_row, textvariable=self.preview_var,
                  style='Hint.TLabel').pack(side='left', padx=8)

        settings_row = ttk.Frame(opt_frame)
        settings_row.pack(fill='x', padx=4, pady=(6, 3))
        self.generator_settings_status_var = tk.StringVar()
        ttk.Label(settings_row, textvariable=self.generator_settings_status_var, style='Hint.TLabel',
                  wraplength=gui_theme.WRAP_NARROW, justify='left').pack(side='left', fill='x', expand=True)
        ttk.Button(settings_row, text='Settings...',
                   command=lambda: self._show_tab('settings')).pack(side='right')

        processor_row = ttk.Frame(opt_frame)
        processor_row.pack(fill='x', padx=4, pady=(5, 3))
        ttk.Label(processor_row, text='Generation Processor:').pack(side='left', padx=(0, 6))
        for value, label in (('auto', 'Auto (prefer GPU)'), ('cuda', 'NVIDIA CUDA'),
                             ('directml', 'AMD DirectML (Experimental)'), ('cpu', 'CPU')):
            ttk.Radiobutton(processor_row, text=label, value=value,
                            variable=self.compute_backend_var,
                            command=self._update_compute_backend_status).pack(side='left', padx=(0, 10))
        ttk.Label(opt_frame, textvariable=self.compute_backend_status_var, style='Hint.TLabel',
                  wraplength=gui_theme.WRAP_MED, justify='left').pack(
            fill='x', padx=gui_theme.INDENT_PAD, pady=(0, 3))
        self.reference_warning_var = tk.StringVar(value='')
        ttk.Label(opt_frame, textvariable=self.reference_warning_var, style='Warn.TLabel',
                  wraplength=gui_theme.WRAP_MED, justify='left').pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)

        self._build_generator_color_section(content)
        self._build_generation_section(content)
        self._build_configurator_workspace(content)

        # Run + progress
        run_frame = ttk.Frame(content)
        run_frame.pack(fill='x', **gui_theme.SECTION_PAD)
        run_actions = ttk.Frame(run_frame)
        run_actions.pack(fill='x')
        self.generate_btn = ttk.Button(run_actions, text='Generate', command=self._start_batch,
                                        style='Accent.TButton')
        self.generate_btn.pack(side='left', padx=4)
        self._on_character_selection_changed()
        self.halt_btn = ttk.Button(run_actions, text='Halt', command=self._halt_batch, state='disabled')
        self.halt_btn.pack(side='left', padx=2)
        self.abort_btn = ttk.Button(run_actions, text='Abort', command=self._abort_batch, state='disabled')
        self.abort_btn.pack(side='left', padx=2)
        self.export_kfps_btn = ttk.Button(run_actions, text='Export to KFPS…', command=self._quick_export_kfps)
        self.export_kfps_btn.pack(side='right', padx=4)
        self.progress = ttk.Progressbar(run_frame, mode='indeterminate')
        self.progress.pack(fill='x', expand=True, padx=4, pady=(6, 0))

        ttk.Label(content,
                  text='Halt finishes the glyph in progress, then keeps whatever generated so far. '
                       'Abort does the same, then deletes every file this run wrote. Export to KFPS '
                       'packages an already-generated .json fontpack into a KFPS Fabric Editor project '
                       '(needs Shape Fitting output, generated first).',
                  style='Hint.TLabel', wraplength=gui_theme.WRAP_WIDE,
                  justify='left').pack(fill='x', padx=8, pady=(0, 4))

        # A small live preview: _run_batch renders each glyph into this
        # canvas as it completes. Separate from the Outputs tab's (larger)
        # browse-a-finished-pack canvas: this one is about the run in
        # progress, that one's about packs already done.
        live_frame = ttk.LabelFrame(content, text=gui_theme.hud_label('Live preview'))
        live_frame.pack(fill='x', **gui_theme.SECTION_PAD)
        live_body = ttk.Frame(live_frame)
        live_body.pack(fill='x', padx=4, pady=4)
        self.live_preview_canvas = tk.Canvas(live_body, width=LIVE_PREVIEW_SIZE[0],
                                              height=LIVE_PREVIEW_SIZE[1], highlightthickness=1)
        self.live_preview_canvas.pack(side='left')
        self.live_preview_stats_var = tk.StringVar(value='Click Generate to watch glyphs appear here.')
        ttk.Label(live_body, textvariable=self.live_preview_stats_var, style='Hint.TLabel',
                  wraplength=gui_theme.WRAP_NARROW, justify='left').pack(side='left', anchor='n', padx=(10, 0))
    def _load_all_fonts(self):
        if self.load_fonts_btn['state'] == 'disabled':
            return
        self._font_scan_generation += 1
        generation = self._font_scan_generation
        self.load_fonts_btn.configure(state='disabled')
        self.font_scan_status_var.set('Scanning installed fonts…')

        # Capture msg_queue itself, not self: this closure runs on a
        # background thread that this app never waits on or cancels, so it
        # keeps running (and keeps whatever it closes over alive) for as
        # long as the font scan takes, independent of the window's own
        # lifetime. Closing over self would pin the *entire* GUI instance --
        # every widget, every generated preview image -- alive for that
        # whole time instead of just the queue it actually needs.
        msg_queue = self.msg_queue

        def worker():
            fonts = enumerate_installed_fonts()
            msg_queue.put(('fonts_loaded', generation, fonts))

        threading.Thread(target=worker, daemon=True).start()
    def _on_fonts_loaded(self, generation: int, fonts: dict):
        if generation != self._font_scan_generation:
            return  # a newer scan superseded this one
        self.fonts = fonts
        # Keep script detections already known from an earlier scan (a
        # font file's script support can't change between scans) instead
        # of wiping the cache on every "Rescan Fonts" click: only fonts
        # this app hasn't classified before get (re-)detected below. Drop
        # entries for fonts no longer installed so this doesn't grow
        # across repeated install/uninstall cycles.
        self._font_scripts = {name: scripts for name, scripts in self._font_scripts.items()
                               if name in fonts}
        self.load_fonts_btn.configure(state='normal')
        self.font_scan_status_var.set(f'{len(fonts)} font(s) found. Detecting scripts…')
        self._refresh_font_list()
        if self.font_view_var.get() == 'grid':
            self._populate_font_grid()
        self._classify_font_scripts(generation)
    def _classify_font_scripts(self, generation: int):
        # Chained after the registry scan, not part of it: opening every
        # font file to read its cmap is real per-file work (unlike the
        # registry-only scan, which never opens a font at all), so this
        # runs as its own background pass and streams results back one
        # font at a time rather than blocking on the whole thing. Fonts
        # already classified by an earlier scan (see _on_fonts_loaded) are
        # skipped: re-detecting an already-known font's scripts on every
        # rescan would just reopen and reparse it for the identical answer
        # (measured ~3ms/font of real cmap-parsing work, real cost across
        # a few hundred installed fonts, and pure waste the second time).
        fonts = {name: path for name, path in self.fonts.items() if name not in self._font_scripts}
        if not fonts:
            self.msg_queue.put(('font_scripts_done', generation))
            return

        def worker():
            for name, path in fonts.items():
                if generation != self._font_scan_generation:
                    return  # superseded by a newer "Load All Fonts" click
                scripts = script_detect.detect_font_scripts(path, name)
                self.msg_queue.put(('font_script_detected', generation, name, scripts))
            self.msg_queue.put(('font_scripts_done', generation))

        threading.Thread(target=worker, daemon=True).start()
    def _select_script_filter(self, script: str | None):
        self._script_filter = script
        self._style_script_tabs()
        self._refresh_font_list()
        if self.font_view_var.get() == 'grid':
            self._populate_font_grid()
        self._update_alphabet_section()
    def _update_alphabet_section(self):
        # Only the group matching the currently-selected script tab is
        # shown: Latin needs no extra block (the ASCII checkboxes above
        # already cover it), and "All" shows nothing extra either, same
        # as picking no script filter at all.
        for frame in self._alphabet_group_frames.values():
            frame.pack_forget()
        self.no_alphabet_hint_lbl.pack_forget()
        script = self._script_filter
        if script in self._alphabet_group_frames:
            self._alphabet_group_frames[script].pack(fill='x', anchor='w')
        elif script in alphabets.NO_ALPHABET_SCRIPTS:
            self.no_alphabet_hint_lbl.pack(fill='x', anchor='w')
    def _style_script_tabs(self):
        p = gui_theme.palette()
        for script, lbl in self._script_tab_labels.items():
            selected = script == self._script_filter
            lbl.configure(background=p['accent'] if selected else p['button_bg'],
                          foreground=p['select_fg'] if selected else p['fg'])
    def _browse_font_on_machine(self):
        chosen = filedialog.askopenfilename(
            filetypes=[('Fonts', '*.ttf;*.otf;*.ttc'), ('all files', '*.*')])
        if not chosen:
            return
        path = Path(chosen)
        self.selected_font = path
        self.font_path_var.set(str(path))
        self.font_list.selection_clear(0, 'end')
        self._check_lowercase_warning()
        self._check_variable_font_status()
        self._on_character_selection_changed()
        if not self.prefix_edited:
            self.prefix_var.set(sanitize_prefix(path.stem))
            self.prefix_edited = False  # trace handler set it True; undo
    def _refresh_font_list(self):
        needle = self.search_var.get().lower()
        self.font_list.delete(0, 'end')
        self._visible_fonts = [
            name for name in self.fonts
            if needle in name.lower()
            and (self._script_filter is None or self._script_filter in self._font_scripts.get(name, set()))
        ]
        for name in self._visible_fonts:
            self.font_list.insert('end', name)
    def _check_lowercase_warning(self):
        # Not a blocking dialog: an all-caps stencil font legitimately has
        # no lowercase glyphs on purpose. Just make sure the user sees that
        # before generating and being surprised the Lowercase folder is empty.
        if self.selected_font is None:
            self.lowercase_warning_var.set('')
            return
        try:
            categorized, _skipped = gen_modelbin_gui.charset_from_font(self.selected_font)
            if not categorized.get('Lowercase'):
                self.lowercase_warning_var.set(
                    '⚠ This font has no lowercase glyphs — the Lowercase category will be empty.')
            else:
                self.lowercase_warning_var.set('')
        except Exception:
            # Don't let a font-parsing hiccup here block selecting a font;
            # generation itself will surface the real error if there is one.
            self.lowercase_warning_var.set('')
    def _check_variable_font_status(self):
        if self.selected_font is None:
            self.font_variation_status_var.set('')
            return
        try:
            info = gen_modelbin_gui.inspect_variable_font(self.selected_font)
        except Exception:
            self.font_variation_status_var.set('')
            return
        if not info.is_variable:
            self.font_variation_status_var.set('Static font (no variable axes).')
            return
        defaults = ', '.join(f'{axis.tag}={axis.default:g}' for axis in info.axes)
        self.font_variation_status_var.set(
            f'Variable font · file default {defaults} · {len(info.instances)} named instance(s). '
            'Use Advanced Generator to choose Regular or custom axes.')
    def _open_current_font_in_advanced(self):
        if self.selected_font is None:
            self._log('Select a font first.', tag='warn')
            return
        self._show_tab('advanced')
        self._load_advanced_font(self.selected_font)
    def _open_current_font_in_direct(self):
        """Transfer Generator's exact selected font without resetting Direct's text/options."""
        if self.selected_font is None:
            messagebox.showinfo(
                'No font selected',
                'Select a font on Generator before sending it to Direct Generator.')
            return
        self.direct_font_var.set(str(self.selected_font))
        self._show_tab('direct')
    def _on_font_selected(self, _event):
        sel = self.font_list.curselection()
        if not sel:
            return
        name = self._visible_fonts[sel[0]]
        self.selected_font = self.fonts[name]
        self.font_path_var.set(str(self.selected_font))
        self._check_lowercase_warning()
        self._check_variable_font_status()
        self._on_character_selection_changed()
        if not self.prefix_edited:
            # Auto-derive prefix from font name unless the user typed their own.
            self.prefix_var.set(sanitize_prefix(name))
            self.prefix_edited = False  # trace handler set it True; undo
    def _on_prefix_changed(self, *_):
        self.prefix_edited = True
        self._update_preview()
    def _on_output_mode_changed(self):
        self._update_preview()
        self._update_reference_warning()
    def _update_preview(self):
        prefix = sanitize_prefix(self.prefix_var.get()) if self.prefix_var.get() else 'CUSTOM'
        ext = 'modelbin' if self.output_var.get() == 'modelbin' else 'json'
        upper_example = glyph_filename(prefix, 'A', ext)
        lower_example = glyph_filename(prefix, 'a', ext)
        self.preview_var.set(f'e.g. {upper_example} / {lower_example}')
    def _pick_out_dir(self):
        chosen = filedialog.askdirectory(initialdir=self.out_var.get())
        if chosen:
            self.out_var.set(chosen)
    def _pick_ref(self):
        chosen = filedialog.askopenfilename(
            filetypes=[('modelbin', '*.modelbin'), ('all files', '*.*')])
        if chosen:
            self.ref_var.set(chosen)
    def _pick_preview_file(self):
        chosen = filedialog.askopenfilename(
            filetypes=[('generated glyph', '*.json;*.modelbin'), ('all files', '*.*')])
        if chosen:
            self.preview_path_var.set(chosen)
            self._show_preview()
    def _show_preview(self):
        raw = self.preview_path_var.get().strip()
        if not raw:
            self.preview_stats_var.set('Pick a .json or .modelbin file to preview.')
            self.preview_stats_lbl.configure(style='Hint.TLabel')
            return
        path = Path(raw)
        if not path.exists():
            self.preview_stats_var.set(f'File not found: {path}')
            self.preview_stats_lbl.configure(style='Danger.TLabel')
            return

        p = gui_theme.palette()
        image = file_preview.render_file_preview(path, PREVIEW_SIZE, bg=p['canvas_bg'], fg=p['fg'])
        self._preview_photo = ImageTk.PhotoImage(image)
        self.preview_canvas.delete('all')
        self.preview_canvas.create_image(0, 0, anchor='nw', image=self._preview_photo)
        stats_text, stats_style = self._preview_stats_text(path)
        self.preview_stats_var.set(stats_text)
        self.preview_stats_lbl.configure(style=stats_style)
    def _goto_configurator_for_current_font(self):
        self._show_tab('generator')
        self._set_configurator_workspace_open(True)
    def _quick_export_kfps(self):
        # Wraps gen_fabric_project.build_fabric_project(): the fontpack
        # dir is derived from the current Prefix/Fontpack-root-folder
        # fields, same as a Generate run would use, so this works whether
        # that pack was just generated this session or already existed.
        prefix = sanitize_prefix(self.prefix_var.get())
        backend = gen_modelbin_gui.resolve_backend(self.compute_backend_var.get())
        pack_dir = pack_dir_for(self.out_var.get(), prefix, 'json',
                                 max(1, int(self.segments_var.get())), backend.resolved)
        if not (pack_dir / 'manifest.json').exists():
            messagebox.showerror('No fontpack found',
                                  f'No manifest.json in:\n{pack_dir}\n\nGenerate a fontpack with '
                                  f'.json output first (Custom Mesh alone has no shapes to export).')
            return
        try:
            project = build_fabric_project(pack_dir, log=self._log)
            out_path = pack_dir / f"{project['suggested_name']}.fabric-project.json"
            save_project(project, out_path)
            self._log(f'--- Exported to KFPS: {out_path} ---', tag='success')
            messagebox.showinfo('Exported', f'Wrote:\n{out_path}\n\nOpen it from KFPS\'s Fabric Editor.')
        except Exception as exc:
            messagebox.showerror('Export failed', str(exc))
    def _on_font_view_changed(self):
        if self.font_view_var.get() == 'grid':
            self.font_list.master.pack_forget()
            self.grid_outer.pack(fill='both', expand=True, padx=4, pady=2)
            self.grid_status_lbl.pack(
                fill='x', anchor='w', padx=gui_theme.ROW_PAD['padx'], pady=(0, 2),
                before=self.grid_outer)
            # Force geometry to settle immediately so the canvas already
            # reports its real width below, rather than whatever stale
            # width (often 1px, never-laid-out) it had before this pack:
            # otherwise the first population would compute a bogus column
            # count from that stale width.
            self.grid_outer.update_idletasks()
            self._populate_font_grid()
        else:
            self.grid_outer.pack_forget()
            self.grid_status_lbl.pack_forget()
            self.font_list.master.pack(fill='both', expand=True, padx=4, pady=2)
    def _grid_columns_for_width(self, width: int) -> int:
        """How many GRID_TILE_SIZE tiles (with their gap) fit across
        `width`: the responsive replacement for a hard-coded column
        count, conceptually `repeat(auto-fill, minmax(tile, tile))`.
        Always at least 1, so a narrow window still shows a single column
        instead of a zero-column/div-by-zero grid."""
        column_span = GRID_TILE_SIZE[0] + 2 * GRID_TILE_GAP
        return max(1, width // column_span)
    def _relayout_grid_tiles(self) -> None:
        """Re-place every already-rendered tile at its row/column for the
        current self._grid_columns, without touching the rendered images.
        Cheap, so it's safe to call on every resize that changes the
        column count instead of only once at population time."""
        for i, tile in enumerate(self.grid_inner.winfo_children()):
            tile.grid_configure(row=i // self._grid_columns, column=i % self._grid_columns)
    def _on_grid_canvas_configure(self, event) -> None:
        self.grid_canvas.itemconfigure(self._grid_window, width=event.width)
        columns = self._grid_columns_for_width(event.width)
        if columns != self._grid_columns:
            self._grid_columns = columns
            self._relayout_grid_tiles()
    def _populate_font_grid(self):
        self._grid_generation += 1
        generation = self._grid_generation
        for child in self.grid_inner.winfo_children():
            child.destroy()
        self._grid_tile_refs.clear()
        self._grid_columns = self._grid_columns_for_width(self.grid_canvas.winfo_width())

        names = self._visible_fonts[:GRID_MAX_TILES]
        overflow = len(self._visible_fonts) - len(names)
        self.grid_status_var.set(f'{overflow} more — refine your search to see them' if overflow > 0 else '')

        p = gui_theme.palette()

        def render_worker():
            for name in names:
                if generation != self._grid_generation:
                    return
                path = self.fonts[name]
                img = font_preview.render_font_name(path, name, GRID_TILE_SIZE, bg=p['entry_bg'], fg=p['fg'])
                self.msg_queue.put(('grid_tile', generation, name, path, img))

        threading.Thread(target=render_worker, daemon=True).start()
    def _add_grid_tile(self, name: str, path: Path, pil_image) -> None:
        photo = ImageTk.PhotoImage(pil_image)
        self._grid_tile_refs.append(photo)
        idx = len(self._grid_tile_refs) - 1
        tile = ttk.Label(self.grid_inner, image=photo, relief='flat', cursor='hand2')
        tile.grid(row=idx // self._grid_columns, column=idx % self._grid_columns,
                  padx=GRID_TILE_GAP, pady=GRID_TILE_GAP)
        tile.bind('<Button-1>', lambda _e, n=name: self._select_font_by_name(n))
    def _select_font_by_name(self, name: str):
        self.selected_font = self.fonts[name]
        self.font_path_var.set(str(self.selected_font))
        self._check_lowercase_warning()
        self._check_variable_font_status()
        if not self.prefix_edited:
            self.prefix_var.set(sanitize_prefix(name))
            self.prefix_edited = False
        self._on_character_selection_changed()
        for i, tile in enumerate(self.grid_inner.winfo_children()):
            tile.configure(relief='solid' if self._visible_fonts[i] == name else 'flat')
    def _on_all_toggled(self):
        state = 'disabled' if self.all_var.get() else 'normal'
        for widget in (self.upper_cb, self.lower_cb, self.digits_cb, self.punct_cb,
                       self.symbols_cb, self.private_cb, self.custom_entry,
                       *self._alphabet_checkbuttons):
            widget.configure(state=state)
        self._on_character_selection_changed()
    def _select_only_script(self, script: str):
        """Clear every additive set, then enable only *script*'s groups."""
        self.all_var.set(False)
        for var in (self.upper_var, self.lower_var, self.digits_var, self.punct_var,
                    self.symbols_var, self.private_var):
            var.set(False)
        self.custom_var.set('')
        for group_vars in self._alphabet_vars.values():
            for var in group_vars.values():
                var.set(False)
        for var in self._all_han_vars.values():
            var.set(False)
        for var in self._alphabet_vars.get(script, {}).values():
            var.set(True)
        self._on_all_toggled()
    def _select_only_custom_text(self):
        """Clear every preset without clearing the text the user pasted."""
        text = self.custom_var.get()
        self.all_var.set(False)
        for var in (self.upper_var, self.lower_var, self.digits_var, self.punct_var,
                    self.symbols_var, self.private_var):
            var.set(False)
        for group_vars in self._alphabet_vars.values():
            for var in group_vars.values():
                var.set(False)
        for var in self._all_han_vars.values():
            var.set(False)
        self.custom_var.set(text)
        self._on_all_toggled()
    # -- Color (solid, or High Contrast per-shape) -------------------------
    def _build_generator_color_section(self, content):
        color_frame = ttk.LabelFrame(content, text=gui_theme.hud_label('5. Color'))
        color_frame.pack(fill='x', **gui_theme.SECTION_PAD)

        self.generator_color_mode_var = tk.StringVar(value='solid')
        mode_row = ttk.Frame(color_frame)
        mode_row.pack(fill='x', **gui_theme.ROW_PAD)
        ttk.Label(mode_row, text='Color mode:').pack(side='left', padx=(4, 6))
        ttk.Radiobutton(mode_row, text='Solid Color', value='solid',
                        variable=self.generator_color_mode_var,
                        command=self._on_generator_color_mode_changed).pack(side='left', padx=(0, 10))
        ttk.Radiobutton(mode_row, text='High Contrast (KFPS Fabric Editor)', value='high_contrast',
                        variable=self.generator_color_mode_var,
                        command=self._on_generator_color_mode_changed).pack(side='left')

        self.generator_color_picker_frame = ttk.Frame(color_frame)
        self.generator_color_picker = ColorPickerWidget(
            self.generator_color_picker_frame, settings_key='color_generator',
            on_change=self._on_generator_color_change, title='')
        self.generator_color_picker.pack(fill='x')
        self.generator_color = self.generator_color_picker.color

        self.generator_hc_frame = ttk.Frame(color_frame)
        seed_row = ttk.Frame(self.generator_hc_frame)
        seed_row.pack(fill='x', **gui_theme.ROW_PAD)
        ttk.Label(seed_row, text='Seed:').pack(side='left', padx=(4, 6))
        self.generator_hc_seed_var = tk.IntVar(value=0)
        ttk.Spinbox(seed_row, from_=0, to=2**31 - 1, width=12,
                    textvariable=self.generator_hc_seed_var).pack(side='left')
        ttk.Button(seed_row, text='Randomize', command=self._randomize_generator_seed).pack(
            side='left', padx=(6, 0))
        ttk.Label(
            self.generator_hc_frame,
            text="Each generated letter's individual primitive shapes get their own color from a "
                 'curated high-contrast palette, so you can tell them apart and select them '
                 'individually in KFPS Fabric Editor -- applied to the exported shapes themselves, '
                 'not just this preview. Deterministic for a given seed: regenerating with the same '
                 'seed reproduces the exact same colors. The seed used is recorded in the pack\'s '
                 'manifest either way.',
            style='Hint.TLabel', wraplength=gui_theme.WRAP_MED, justify='left',
        ).pack(fill='x', padx=gui_theme.INDENT_PAD, pady=gui_theme.ROW_PAD_BOTTOM['pady'])

        self._on_generator_color_mode_changed()

    def _on_generator_color_change(self, rgba: tuple):
        self.generator_color = rgba

    def _on_generator_color_mode_changed(self):
        if self.generator_color_mode_var.get() == 'high_contrast':
            self.generator_color_picker_frame.pack_forget()
            self.generator_hc_frame.pack(fill='x')
        else:
            self.generator_hc_frame.pack_forget()
            self.generator_color_picker_frame.pack(fill='x', **gui_theme.ROW_PAD)

    def _randomize_generator_seed(self):
        import random
        self.generator_hc_seed_var.set(random.randint(0, 2**31 - 1))
    # -- Generation policy (which vinyls the generator may use) -----------
    def _build_generation_section(self, content):
        """The vinyl-shape restrictions, preferences, preset and fallback.

        Every control here feeds one `GenerationPolicy`
        (`_current_generation_policy`) that the actual generation paths read,
        rather than being UI-only switches interpreted separately per tab.
        The shape list is built from `PRIMITIVE_CATALOG` itself, so a
        primitive added to the catalog appears here with no UI change and no
        second list to keep in sync.
        """
        frame = ttk.LabelFrame(content, text=gui_theme.hud_label('6. Vinyl Shapes'))
        frame.pack(fill='x', **gui_theme.SECTION_PAD)

        ttk.Label(
            frame,
            text='Restrict which FH6 primitives the generator may build glyphs from, and optionally '
                 'mark some as preferred so they win when two solutions are about equally accurate. '
                 'These apply to every generation path, not just this tab.',
            style='Intro.TLabel', wraplength=gui_theme.WRAP_WIDE,
            justify='left').pack(fill='x', padx=4, pady=(4, 2))

        preset_row = ttk.Frame(frame)
        preset_row.pack(fill='x', **gui_theme.ROW_PAD)
        ttk.Label(preset_row, text='Preset:').pack(side='left', padx=4)
        self.generation_preset_var = tk.StringVar(value=PRESET_LABELS[RECOMMENDED_PRESET])
        # "Custom" is shown, never chosen: it is what the preset *becomes*
        # when a dial moves, so offering it as a selection would be a no-op.
        self.generation_preset_combo = ttk.Combobox(
            preset_row, textvariable=self.generation_preset_var, state='readonly', width=24,
            values=[PRESET_LABELS[name] for name in PRESETS])
        self.generation_preset_combo.pack(side='left', padx=4)
        self.generation_preset_combo.bind('<<ComboboxSelected>>', self._on_generation_preset_selected)
        ttk.Button(preset_row, text='Restore Recommended Defaults',
                   command=self._restore_recommended_generation_defaults).pack(side='left', padx=8)

        self.generation_preset_hint_var = tk.StringVar()
        ttk.Label(frame, textvariable=self.generation_preset_hint_var, style='Hint.TLabel',
                  wraplength=gui_theme.WRAP_MED, justify='left').pack(
                      fill='x', padx=gui_theme.INDENT_PAD, pady=(0, 4))

        select_row = ttk.Frame(frame)
        select_row.pack(fill='x', **gui_theme.ROW_PAD)
        ttk.Label(select_row, text='Allowed shapes:').pack(side='left', padx=4)
        self.generation_shapes_toggle_btn = ttk.Button(
            select_row, text='Hide shapes', command=self._toggle_generation_shapes)
        self.generation_shapes_toggle_btn.pack(side='left', padx=2)
        ttk.Button(select_row, text='Select All',
                   command=lambda: self._set_all_shapes_allowed(True)).pack(side='left', padx=2)
        ttk.Button(select_row, text='Select None',
                   command=lambda: self._set_all_shapes_allowed(False)).pack(side='left', padx=2)
        self.generation_shapes_summary_var = tk.StringVar()
        ttk.Label(select_row, textvariable=self.generation_shapes_summary_var,
                  style='Hint.TLabel').pack(side='left', padx=8)

        # The tile grid is the tall part, so it collapses to the summary line
        # above once a selection is settled rather than occupying the tab
        # permanently.
        self.generation_shapes_body = ttk.Frame(frame)
        self.generation_shapes_body.pack(fill='x', padx=gui_theme.INDENT_PAD, pady=2)
        self._generation_shapes_visible = True

        self.shape_grid = ttk.Frame(self.generation_shapes_body)
        self.shape_grid.pack(fill='x')
        self._shape_allow_vars: dict[str, tk.BooleanVar] = {}
        self._shape_prefer_vars: dict[str, tk.BooleanVar] = {}
        self._shape_tiles: dict[str, tk.Canvas] = {}
        # Tk drops a PhotoImage the moment nothing references it, blanking the
        # widget; these keep every rendered tile alive for the window's life.
        self._shape_tile_photos: dict[str, ImageTk.PhotoImage] = {}
        self._shape_tile_columns = 0  # set by the first _relayout_shape_tiles
        for shape_id in PRIMITIVE_CATALOG:
            self._shape_allow_vars[shape_id] = tk.BooleanVar(value=True)
            self._shape_prefer_vars[shape_id] = tk.BooleanVar(value=False)
            canvas = tk.Canvas(self.shape_grid, width=vinyl_tiles.TILE_W,
                               height=vinyl_tiles.TILE_H,
                               highlightthickness=0, borderwidth=0, cursor='hand2')
            canvas.bind('<Button-1>', lambda event, sid=shape_id: self._on_shape_tile_click(event, sid))
            self._shape_tiles[shape_id] = canvas
        # Deliberately no columnconfigure(weight=...): weighted columns hand
        # each column an equal share of the spare width, which spreads
        # fixed-size tiles into wide empty gaps on a maximized window. The
        # column *count* responds to width instead (see
        # _shape_tile_columns_for_width), so a wider window packs more tiles
        # per row rather than the same few further apart.
        self.shape_grid.bind('<Configure>', self._on_shape_grid_configure)

        ttk.Label(
            self.generation_shapes_body,
            text='Click a tile to allow or disallow that vinyl. Click the ★ badge on an allowed tile '
                 'to mark it preferred — a tie-break, not an override: a preferred shape wins when it '
                 'fits about as well as the alternative, and still loses when it visibly fits worse. '
                 'Square is special: the exact rectangle and stencil strategies are built entirely '
                 'from it, so disabling Square also disables those and leaves the shape search to '
                 'answer every glyph.',
            style='Hint.TLabel', wraplength=gui_theme.WRAP_MED,
            justify='left').pack(fill='x', pady=(2, 4))

        fallback_row = ttk.Frame(frame)
        fallback_row.pack(fill='x', **gui_theme.ROW_PAD)
        ttk.Label(fallback_row, text='If the selection falls short:').pack(side='left', padx=4)
        self.generation_fallback_var = tk.StringVar(value=FALLBACK_LABELS[DEFAULT_POLICY.fallback])
        self.generation_fallback_combo = ttk.Combobox(
            fallback_row, textvariable=self.generation_fallback_var, state='readonly', width=54,
            values=[FALLBACK_LABELS[mode] for mode in FALLBACK_MODES])
        self.generation_fallback_combo.pack(side='left', padx=4)
        self.generation_fallback_combo.bind(
            '<<ComboboxSelected>>', lambda _e: self._on_generation_policy_changed())

        self.generation_exact_cover_var = tk.BooleanVar(value=DEFAULT_POLICY.allow_exact_cover)
        ttk.Checkbutton(
            frame, text='Allow exact rectangle/stencil cover for blocky glyphs',
            variable=self.generation_exact_cover_var,
            command=self._on_generation_policy_changed).pack(
                anchor='w', padx=gui_theme.INDENT_PAD, pady=(2, 0))
        ttk.Label(
            frame,
            text='On: a blocky glyph is solved exactly, usually in very few layers. Off: the shape '
                 'search answers it instead, favouring recognizable primitives over a grid of rectangles.',
            style='Hint.TLabel', wraplength=gui_theme.WRAP_MED,
            justify='left').pack(fill='x', padx=gui_theme.INDENT_PAD, pady=(0, 4))

        self.generation_validation_var = tk.StringVar()
        self.generation_validation_lbl = ttk.Label(
            frame, textvariable=self.generation_validation_var, style='Hint.TLabel',
            wraplength=gui_theme.WRAP_MED, justify='left')
        self.generation_validation_lbl.pack(fill='x', padx=4, pady=(0, 6))

        self._relayout_shape_tiles(vinyl_tiles.TILE_W * 6)
        self._apply_generation_policy(self._settings_generation_policy())

    def _settings_generation_policy(self) -> GenerationPolicy:
        """The saved policy, reporting rather than hiding anything unusable."""
        policy, dropped = policy_from_dict({
            "allowed_shapes": self.settings.get('generation_allowed_shapes', []),
            "preferred_shapes": self.settings.get('generation_preferred_shapes', []),
            "fallback": self.settings.get('generation_fallback', DEFAULT_POLICY.fallback),
            "allow_exact_cover": self.settings.get('generation_allow_exact_cover', True),
        })
        preset_name = self.settings.get('generation_preset', RECOMMENDED_PRESET)
        # A stored preset only wins when the stored dials still match it;
        # otherwise the individual settings are the truth and the preset is
        # stale, which is exactly the "custom" state.
        if preset_name in PRESETS and policy == PRESETS[preset_name]:
            policy = PRESETS[preset_name]
        if dropped:
            self._log(f'Ignored {len(dropped)} saved vinyl shape(s) not in this build: '
                      f'{", ".join(dropped)}', tag='warn')
        return policy

    def _current_generation_policy(self) -> GenerationPolicy:
        """Build a policy from the live controls.

        This is the single place the UI is turned into generation rules; every
        generation path reads the result rather than re-deriving it.
        """
        if not hasattr(self, '_shape_allow_vars'):
            return DEFAULT_POLICY
        allowed = frozenset(sid for sid, var in self._shape_allow_vars.items() if var.get())
        preferred = frozenset(sid for sid, var in self._shape_prefer_vars.items()
                              if var.get() and sid in allowed)
        label_to_mode = {label: mode for mode, label in FALLBACK_LABELS.items()}
        fallback = label_to_mode.get(self.generation_fallback_var.get(), DEFAULT_POLICY.fallback)

        # Start from the selected preset so its tuning dials (layer ceiling,
        # quality target, min gain) survive edits to the shape selection.
        base = PRESETS.get(self._selected_preset_name(), DEFAULT_POLICY)
        from dataclasses import replace
        return replace(
            base, allowed=allowed, preferred=preferred, fallback=fallback,
            allow_exact_cover=bool(self.generation_exact_cover_var.get()))

    def _selected_preset_name(self) -> str:
        label = self.generation_preset_var.get()
        for name, preset_label in PRESET_LABELS.items():
            if preset_label == label:
                return name
        return RECOMMENDED_PRESET

    def _apply_generation_policy(self, policy: GenerationPolicy) -> None:
        """Push a policy back onto the controls (loading settings, presets,
        Restore Defaults) without echoing a change event per widget."""
        for shape_id, var in self._shape_allow_vars.items():
            var.set(shape_id in policy.allowed)
        for shape_id, var in self._shape_prefer_vars.items():
            var.set(shape_id in policy.preferred)
        self.generation_fallback_var.set(FALLBACK_LABELS[policy.fallback])
        self.generation_exact_cover_var.set(policy.allow_exact_cover)
        name = preset_name_for(policy)
        if name in PRESET_LABELS:
            self.generation_preset_var.set(PRESET_LABELS[name])
        self._refresh_generation_state(policy)

    def _on_generation_preset_selected(self, _event=None) -> None:
        self._apply_generation_policy(PRESETS[self._selected_preset_name()])
        self._log(f'Generation preset: {self.generation_preset_var.get()}', tag='hint')

    def _restore_recommended_generation_defaults(self) -> None:
        self._apply_generation_policy(PRESETS[RECOMMENDED_PRESET])
        self._log('Restored recommended generation defaults.', tag='success')

    def _on_shape_tile_click(self, event, shape_id: str) -> None:
        """Tile click: the badge toggles preference, anywhere else toggles
        allowed.

        Hit-tested against the same constants that drew the badge (see
        `vinyl_tiles.badge_hit`) so the target can't drift from the artwork.
        The badge is only live on an allowed tile: preferring a disabled
        shape is an invalid policy, so clicking there allows it first.
        """
        allow_var = self._shape_allow_vars[shape_id]
        prefer_var = self._shape_prefer_vars[shape_id]
        if allow_var.get() and vinyl_tiles.badge_hit(event.x, event.y):
            prefer_var.set(not prefer_var.get())
        else:
            allow_var.set(not allow_var.get())
            if not allow_var.get():
                prefer_var.set(False)  # a disabled shape cannot stay preferred
        self._on_generation_policy_changed()

    @staticmethod
    def _shape_tile_columns_for_width(width: int) -> int:
        """How many tiles fit across `width`, at least 1 and never more than
        the catalog has: the same `repeat(auto-fill, ...)` idea the font grid
        uses, so a maximized window packs more per row instead of stretching
        the gaps between a fixed six."""
        span = vinyl_tiles.TILE_W + 6  # tile plus its padx on both sides
        return max(1, min(len(PRIMITIVE_CATALOG), width // span))

    def _relayout_shape_tiles(self, width: int | None = None) -> None:
        """Re-place the tiles for the current width. Cheap: it only moves
        existing widgets and never re-renders their images, so it is safe to
        call on any resize that actually changes the column count."""
        if not hasattr(self, '_shape_tiles'):
            return
        if width is None:
            width = self.shape_grid.winfo_width()
        columns = self._shape_tile_columns_for_width(width)
        if columns == self._shape_tile_columns:
            return
        self._shape_tile_columns = columns
        for index, shape_id in enumerate(PRIMITIVE_CATALOG):
            self._shape_tiles[shape_id].grid(
                row=index // columns, column=index % columns, padx=3, pady=3)

    def _on_shape_grid_configure(self, event) -> None:
        self._relayout_shape_tiles(event.width)

    def _shape_tile_state(self, shape_id: str) -> str:
        if not self._shape_allow_vars[shape_id].get():
            return 'off'
        return 'preferred' if self._shape_prefer_vars[shape_id].get() else 'on'

    def _redraw_shape_tiles(self) -> None:
        """Repaint every tile for the current selection and theme.

        Also called from `_apply_theme`, since the tiles bake palette colours
        into a bitmap and would otherwise keep the old theme's colours after a
        palette switch.
        """
        if not hasattr(self, '_shape_tiles'):
            return
        palette = gui_theme.palette()
        for shape_id, canvas in self._shape_tiles.items():
            state = self._shape_tile_state(shape_id)
            image = vinyl_tiles.render_tile(PRIMITIVE_CATALOG[shape_id], state, palette)
            # master= is explicit: an ImageTk.PhotoImage with no master binds
            # to Tkinter's ambient default root, which is the wrong
            # interpreter as soon as more than one exists.
            photo = ImageTk.PhotoImage(image, master=canvas)
            self._shape_tile_photos[shape_id] = photo
            canvas.delete('all')
            canvas.configure(background=palette['panel_alt'])
            canvas.create_image(0, 0, anchor='nw', image=photo)

    def _toggle_generation_shapes(self) -> None:
        self._generation_shapes_visible = not self._generation_shapes_visible
        if self._generation_shapes_visible:
            self.generation_shapes_body.pack(fill='x', padx=gui_theme.INDENT_PAD, pady=2)
            self.generation_shapes_toggle_btn.configure(text='Hide shapes')
        else:
            self.generation_shapes_body.pack_forget()
            self.generation_shapes_toggle_btn.configure(text='Show shapes')

    def _set_all_shapes_allowed(self, allowed: bool) -> None:
        for var in self._shape_allow_vars.values():
            var.set(allowed)
        if not allowed:
            # A preference on a disabled shape is an invalid state, not a
            # remembered one: clear rather than leave it to fail validation.
            for var in self._shape_prefer_vars.values():
                var.set(False)
        self._on_generation_policy_changed()

    def _on_generation_policy_changed(self) -> None:
        self._refresh_generation_state(self._current_generation_policy())

    def _refresh_generation_state(self, policy: GenerationPolicy) -> None:
        """Update the preset label, validation line, and Generate button.

        Generation is blocked with an explanation rather than silently
        reverting to defaults or crashing when the selection can't build
        anything.
        """
        if not hasattr(self, 'generation_validation_var'):
            return
        name = preset_name_for(policy)
        self.generation_preset_var.set(
            PRESET_LABELS.get(name, 'Custom') if name != 'custom' else 'Custom')
        self.generation_preset_hint_var.set(
            'Custom — these settings no longer match a preset.' if name == 'custom'
            else f'{PRESET_LABELS[name]} preset.')

        self._redraw_shape_tiles()
        self.generation_shapes_summary_var.set(
            f'{len(policy.allowed)} of {len(PRIMITIVE_CATALOG)} allowed'
            + (f', {len(policy.preferred)} preferred' if policy.preferred else ''))

        problems = policy.validate()
        if problems:
            self.generation_validation_var.set('Cannot generate: ' + ' '.join(problems))
            self.generation_validation_lbl.configure(style='Danger.TLabel')
        elif not policy.allows_exact_cover:
            self.generation_validation_var.set(
                'Exact rectangle/stencil cover is unavailable, so every glyph goes through the shape '
                'search. This is a valid choice, just a slower and less exact one for blocky fonts.')
            self.generation_validation_lbl.configure(style='Warn.TLabel')
        else:
            count = len(policy.allowed)
            preferred = len(policy.preferred)
            summary = f'{count} of {len(PRIMITIVE_CATALOG)} vinyl shapes allowed'
            if preferred:
                summary += f', {preferred} preferred'
            self.generation_validation_var.set(summary + '.')
            self.generation_validation_lbl.configure(style='Hint.TLabel')

        if hasattr(self, 'generate_btn') and self.worker is None:
            self.generate_btn.configure(state='disabled' if problems else 'normal')

    def _on_character_selection_changed(self):
        """Keep the exact workload visible before a costly batch starts."""
        if not hasattr(self, 'character_count_var'):
            return
        selected = self._selected_chars()
        supported: set[str] | None = None
        if self.selected_font is not None:
            try:
                categorized, _ = gen_modelbin_gui.charset_from_font(self.selected_font)
                supported = {char for chars in categorized.values() for char in chars}
            except Exception:
                supported = None

        if selected is None:
            if supported is None:
                text = 'Entire font selected — choose a font to see the glyph count.'
                count = None
            else:
                count = len(supported)
                text = f'Entire font selected: {count:,} glyphs will be generated.'
        else:
            count = len(selected)
            if supported is None:
                text = f'{count:,} unique glyphs selected — choose a font to check support.'
            else:
                available = len(selected & supported)
                missing = count - available
                text = f'{count:,} unique glyphs selected · {available:,} supported by this font'
                if missing:
                    text += f' · {missing:,} unavailable'
        if hasattr(self, 'font_character_total_var'):
            if supported is None:
                self.font_character_total_var.set('—')
                self.fontpack_character_count_var.set('Select a font')
                self.large_font_warning_var.set('')
            else:
                self.font_character_total_var.set(f'{len(supported):,}')
                generated = len(supported) if selected is None else len(selected & supported)
                noun = 'character' if generated == 1 else 'characters'
                self.fontpack_character_count_var.set(
                    f'{generated:,} {noun}\nselected for fontpack')
                if len(supported) > 1_000:
                    self.large_font_warning_var.set(
                        f'⚠ This font contains {len(supported):,} unique characters. '
                        'Consider using Advanced Generation to manage this large font more carefully.')
                else:
                    self.large_font_warning_var.set('')
        if count is not None and count >= 500:
            text += '  ⚠ Large generation job.'
        self.character_count_var.set(text)
        if hasattr(self, 'generate_btn'):
            self.generate_btn.configure(text=(f'Generate {count:,} glyphs' if count is not None
                                              else 'Generate'))
        if hasattr(self, 'advanced_workload_var'):
            self._update_advanced_summary()
    def _selected_chars(self, selection_font: Path | None = None) -> set[str] | None:
        if self.all_var.get():
            return None
        selection_font = selection_font or self.selected_font
        chars: set[str] = set()
        if self.upper_var.get():
            chars.update(string.ascii_uppercase)
        if self.lower_var.get():
            chars.update(string.ascii_lowercase)
        if self.digits_var.get():
            chars.update(string.digits)
        if self.punct_var.get():
            chars.update(string.punctuation)
        if self.symbols_var.get() and selection_font is not None:
            # "Symbols" isn't a fixed ASCII set like the others: pull
            # whatever the selected font's own cmap actually categorizes as
            # Symbols (forza_writer.charset's Unicode-category grouping).
            categorized, _ = gen_modelbin_gui.charset_from_font(selection_font)
            chars.update(c for c in categorized.get('Symbols', [])
                         if unicodedata.category(c).startswith('S'))
        if self.private_var.get() and selection_font is not None:
            categorized, _ = gen_modelbin_gui.charset_from_font(selection_font)
            chars.update(c for c in categorized.get('Symbols', [])
                         if unicodedata.category(c) == 'Co')
        # Every script's checkboxes count regardless of which one is
        # currently visible (see _update_alphabet_section): additive,
        # same as every other row in this section.
        for script, group_vars in self._alphabet_vars.items():
            groups = alphabets.groups_for_script(script)
            for label, letters in groups:
                var = group_vars.get(label)
                if var is not None and var.get():
                    chars.update(letters)
        if selection_font is not None and any(var.get() for var in self._all_han_vars.values()):
            categorized, _ = gen_modelbin_gui.charset_from_font(selection_font)
            chars.update(c for c in categorized.get('Letters', []) if is_han_char(c))
        for c in self.custom_var.get():
            if not c.isspace():
                chars.add(c)
        return chars
