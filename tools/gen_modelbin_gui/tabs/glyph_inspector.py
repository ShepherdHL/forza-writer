"""Glyph Inspector tab: browse every glyph a font supports, categorized by
Unicode block (see forza_writer/font_info.py, forza_writer/unicode_blocks.py),
and inspect one at large scale against the font's own metrics.

Font enumeration feeds a categorized/searchable tile grid and three
per-glyph views:

Reference: the glyph rendered straight from the font's outline, with
ascender/cap-height/x-height/baseline/descender guides.

Generated: runs the real generation pipeline
(forza_writer.primitive_fit.fit_glyph_with_strategy, the same call Direct
Generator uses), cached per (font, char, compute backend) like
Configurator's own fit cache.

Compare: diffs Generated against a target mask, either the font's own
outline (forza_writer.glyph_quality.assess_glyph's approach) or a
hand-loaded single-glyph shape file. The hand-made file must be the same
single-glyph, origin-centered `{"shapes": [...]}` format Configurator's
manual per-glyph overrides already use, not an arbitrary multi-glyph
design export: a whole KFPS project spans many glyphs in one shared
coordinate space with no reliable, universal way to tell which shapes
belong to which character, so the user exports/isolates one glyph's
shapes first to keep this reliable instead of guessing.
"""

import json
import sys
import threading
from pathlib import Path

import gen_modelbin_gui
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import file_preview  # noqa: E402
import font_preview  # noqa: E402
import glyph_reference_preview  # noqa: E402
import gui_theme  # noqa: E402
from gen_modelbin import extract_contours, normalize_to_128  # noqa: E402
from gui_theme import gauges  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
from forza_writer import glyph_quality  # noqa: E402
from forza_writer.font_info import FontInfo, GlyphInfo  # noqa: E402
from forza_writer.generation_policy import DEFAULT_POLICY  # noqa: E402
from forza_writer.primitive_fit import fit_glyph_with_strategy, rasterize_contours  # noqa: E402

from ..state import (  # noqa: E402
    GLYPH_CATEGORY_EXPAND_STEP, GLYPH_CATEGORY_HARD_CAP, GLYPH_CATEGORY_TILE_CAP, GLYPH_GRID_HEIGHT,
    GLYPH_PREVIEW_SIZE, GLYPH_TILE_GAP, GLYPH_TILE_SIZE)

# Compare mode's four metrics, in filmstrip/ledger display order. 'iou'/
# 'boundary_f1' are percentage metrics (rendered as a ring gauge);
# 'components'/'holes' are exact-count metrics (rendered as a count pill)
# read from compare_masks()'s own f'{key}_generated'/f'{key}_expected' keys.
_COMPARE_METRIC_ORDER = ('iou', 'boundary_f1', 'components', 'holes')
_COMPARE_METRIC_LABELS = {
    'iou': 'IoU', 'boundary_f1': 'Bnd F1', 'components': 'Comps', 'holes': 'Holes',
}


class GlyphInspectorTabMixin:
    # Body width (px) below which the detail/preview panel stacks under
    # the glyph grid. Below ~892px, pack's layout math cannot give the
    # panel its full natural width (396px, driven by the 380px preview
    # canvas) without help: the tile grid's own claim on the cavity leaves
    # too little, silently compressing the panel down to as little as
    # 343px, clipping the preview canvas itself. 900 sits safely above
    # that ~892px crossover, matching the threshold Composer's own Color
    # panel uses for the same reason.
    _GLYPH_INSPECTOR_WIDE_THRESHOLD = 900
    # A large font's tile grid can hold thousands of already-rendered
    # tiles (measured ~4,400 for a CJK font); re-gridding all of them
    # (~23ms) on every intermediate width during a live resize-drag stalls
    # the UI. Debounced like Composer's own resize handler, not applied
    # eagerly on every <Configure>: see `_on_glyph_inspector_grid_canvas_configure`.
    _GRID_RELAYOUT_DEBOUNCE_MS = 120

    def _build_glyph_inspector_page(self):
        page = ttk.Frame(self.page_container)
        self._pages['glyph_inspector'] = page
        content = self._build_scroll_shell(page, 'glyph_inspector')

        ttk.Label(
            content,
            text='Browse every glyph a font supports, grouped by Unicode block, and inspect one at '
                 'large scale against the font\'s own metrics — what the font itself says a character '
                 'should look like.',
            style='Intro.TLabel', wraplength=gui_theme.WRAP_WIDE, justify='left',
        ).pack(fill='x', **gui_theme.PAGE_INTRO_PAD)

        font_frame = ttk.LabelFrame(content, text=gui_theme.hud_label('1. Font'))
        font_frame.pack(fill='x', **gui_theme.SECTION_PAD)
        font_row = ttk.Frame(font_frame)
        font_row.pack(fill='x', **gui_theme.ROW_PAD)
        self.glyph_inspector_font_var = tk.StringVar()
        font_entry = ttk.Entry(font_row, textvariable=self.glyph_inspector_font_var)
        font_entry.pack(side='left', fill='x', expand=True, padx=(0, 4))
        font_entry.bind('<Return>', self._load_glyph_inspector_font_from_field)
        font_entry.bind('<FocusOut>', self._load_glyph_inspector_font_from_field)
        ttk.Button(font_row, text='Use selected font',
                   command=self._use_selected_font_in_glyph_inspector).pack(side='left', padx=2)
        ttk.Button(font_row, text='Browse...',
                   command=self._browse_glyph_inspector_font).pack(side='left', padx=2)

        self.glyph_inspector_font_status_var = tk.StringVar(value='Select a font to inspect its glyphs.')
        ttk.Label(font_frame, textvariable=self.glyph_inspector_font_status_var, style='Hint.TLabel',
                  wraplength=gui_theme.WRAP_WIDE, justify='left').pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)

        browser_frame = ttk.LabelFrame(content, text=gui_theme.hud_label('2. Glyphs'))
        browser_frame.pack(fill='x', **gui_theme.SECTION_PAD)

        body = ttk.Frame(browser_frame)
        body.pack(fill='both', expand=True, padx=8, pady=(2, 8))
        self.glyph_inspector_body = body

        # -- left: search + categorized tile grid ----------------------
        list_col = ttk.Frame(body)
        self.glyph_inspector_list_col = list_col

        search_row = ttk.Frame(list_col)
        search_row.pack(fill='x', pady=(0, 4))
        ttk.Label(search_row, text='Search:').pack(side='left')
        self.glyph_inspector_search_var = tk.StringVar()
        ttk.Entry(search_row, textvariable=self.glyph_inspector_search_var).pack(
            side='left', fill='x', expand=True, padx=(4, 0))
        self.glyph_inspector_search_var.trace_add(
            'write', lambda *_: self._populate_glyph_inspector_grid())
        ttk.Label(
            search_row,
            text='Character, U+codepoint, Unicode name, or glyph name',
            style='Hint.TLabel',
        ).pack(side='left', padx=(8, 0))

        self.glyph_inspector_status_var = tk.StringVar(value='Select a font to inspect its glyphs.')
        ttk.Label(list_col, textvariable=self.glyph_inspector_status_var, style='Hint.TLabel',
                  wraplength=gui_theme.WRAP_NARROW, justify='left').pack(fill='x', pady=(0, 4))

        grid_outer = ttk.Frame(list_col)
        grid_outer.pack(fill='both', expand=True)
        self.glyph_inspector_grid_canvas = tk.Canvas(
            grid_outer, height=GLYPH_GRID_HEIGHT, highlightthickness=0)
        grid_scroll = gui_theme.AutoHideScrollbar(
            grid_outer, orient='vertical', command=self.glyph_inspector_grid_canvas.yview)
        self.glyph_inspector_grid_canvas.configure(yscrollcommand=grid_scroll.set)
        self.glyph_inspector_grid_canvas.pack(
            side='left', fill='both', expand=True, padx=(0, gui_theme.SCROLLBAR_GUTTER))
        grid_scroll.pack(side='right', fill='y')
        self._register_independent_scroll(self.glyph_inspector_grid_canvas)

        self.glyph_inspector_grid_inner = ttk.Frame(self.glyph_inspector_grid_canvas, style='Grid.TFrame')
        self._glyph_inspector_grid_window = self.glyph_inspector_grid_canvas.create_window(
            (0, 0), window=self.glyph_inspector_grid_inner, anchor='nw')
        self.glyph_inspector_grid_inner.bind(
            '<Configure>',
            lambda _e: self.glyph_inspector_grid_canvas.configure(
                scrollregion=self.glyph_inspector_grid_canvas.bbox('all')))
        self.glyph_inspector_grid_canvas.bind('<Configure>', self._on_glyph_inspector_grid_canvas_configure)

        # -- right: inspector (mode control, large preview, metadata) --
        detail_col = ttk.LabelFrame(body, text=gui_theme.hud_label('Selected Glyph'))
        self.glyph_inspector_detail_col = detail_col

        mode_row = ttk.Frame(detail_col)
        mode_row.pack(fill='x', padx=6, pady=(6, 2))
        self.glyph_inspector_mode_row = mode_row
        self.glyph_inspector_mode_var = tk.StringVar(value='reference')
        ttk.Radiobutton(mode_row, text='Reference', value='reference',
                        variable=self.glyph_inspector_mode_var,
                        command=self._refresh_glyph_inspector_detail).pack(side='left')
        ttk.Radiobutton(mode_row, text='Generated', value='generated',
                        variable=self.glyph_inspector_mode_var,
                        command=self._refresh_glyph_inspector_detail).pack(side='left', padx=(8, 0))
        ttk.Radiobutton(mode_row, text='Compare', value='compare',
                        variable=self.glyph_inspector_mode_var,
                        command=self._refresh_glyph_inspector_detail).pack(side='left', padx=(8, 0))

        # Compare-only sub-row: which target to diff Generated against.
        # Shown/hidden by _update_glyph_inspector_compare_row rather than
        # rebuilt, so widget state (the loaded hand-made path per glyph)
        # survives switching modes back and forth.
        self.glyph_inspector_compare_row = ttk.Frame(detail_col)
        ttk.Radiobutton(self.glyph_inspector_compare_row, text='vs font outline', value='font',
                        variable=self._glyph_inspector_compare_target_var,
                        command=self._refresh_glyph_inspector_detail).pack(side='left')
        ttk.Radiobutton(self.glyph_inspector_compare_row, text='vs hand-made file', value='handmade',
                        variable=self._glyph_inspector_compare_target_var,
                        command=self._refresh_glyph_inspector_detail).pack(side='left', padx=(8, 0))
        ttk.Button(self.glyph_inspector_compare_row, text='Load hand-made file...',
                   command=self._load_glyph_inspector_handmade_file).pack(side='left', padx=(8, 0))

        self.glyph_inspector_preview_canvas = tk.Canvas(
            detail_col, width=GLYPH_PREVIEW_SIZE[0], height=GLYPH_PREVIEW_SIZE[1], highlightthickness=1)
        self.glyph_inspector_preview_canvas.pack(padx=6, pady=6)

        # Compare-only: a real legend for the diff overlay's colors, with
        # exact hex values matching forza_writer.glyph_quality.diff_overlay_image's
        # own fill colors, instead of a sentence glued onto the status label below.
        self.glyph_inspector_compare_legend = gui_theme.build_legend(
            detail_col,
            [('#F5F5F5', 'Match'),
             ('#2D7DFF', 'Missing from generated glyph'),
             ('#F54646', 'Extra generated ink')])

        # Compare-only: the focused metric's ring gauge / count pill, a
        # filmstrip of 4 cards to switch which metric is focused, and an
        # always-visible ledger of all 4 plus the overall verdict. Colors
        # are applied per palette in _render_glyph_inspector_compare_focus/
        # _ledger, not baked in here.
        self.glyph_inspector_compare_focus_label = ttk.Label(detail_col, anchor='center')
        self._glyph_inspector_compare_focus_photo = None

        self.glyph_inspector_compare_filmstrip = ttk.Frame(detail_col)
        self._glyph_inspector_compare_cards: dict[str, tk.Label] = {}
        for key in _COMPARE_METRIC_ORDER:
            card = tk.Label(self.glyph_inspector_compare_filmstrip, text=_COMPARE_METRIC_LABELS[key],
                             cursor='hand2', padx=4, pady=4, borderwidth=1, relief='solid')
            card.pack(side='left', fill='x', expand=True, padx=2)
            card.bind('<Button-1>', lambda _e, k=key: self._set_glyph_inspector_compare_focus(k))
            self._glyph_inspector_compare_cards[key] = card

        self.glyph_inspector_compare_ledger = ttk.Frame(detail_col)
        self._glyph_inspector_compare_ledger_labels: dict[str, tk.Label] = {}
        for key in _COMPARE_METRIC_ORDER:
            row = ttk.Frame(self.glyph_inspector_compare_ledger)
            row.pack(fill='x')
            ttk.Label(row, text=f'{_COMPARE_METRIC_LABELS[key]}:', style='Hint.TLabel',
                      width=8, anchor='w').pack(side='left')
            value_lbl = tk.Label(row, text='—', anchor='w', borderwidth=0)
            value_lbl.pack(side='left', fill='x', expand=True)
            self._glyph_inspector_compare_ledger_labels[key] = value_lbl
        self.glyph_inspector_compare_verdict = tk.Label(
            self.glyph_inspector_compare_ledger, text='', anchor='w', borderwidth=0)
        self.glyph_inspector_compare_verdict.pack(fill='x', pady=(4, 0))

        self._glyph_inspector_compare_focus_index = 0
        self._glyph_inspector_compare_metrics: dict | None = None

        meta = ttk.Frame(detail_col)
        self.glyph_inspector_meta_frame = meta
        meta.pack(fill='x', padx=6, pady=(0, 6))
        self.glyph_inspector_meta_vars: dict[str, tk.StringVar] = {}
        for key, label in (
            ('char', 'Character'), ('codepoint', 'Codepoint'), ('unicode_name', 'Unicode name'),
            ('glyph_name', 'Glyph name'), ('category', 'Category'),
            ('advance_width', 'Advance width'), ('bearings', 'Side bearings'),
            ('bbox', 'Bounding box'),
        ):
            row = ttk.Frame(meta)
            row.pack(fill='x')
            ttk.Label(row, text=f'{label}:', style='Hint.TLabel', width=14, anchor='w').pack(side='left')
            var = tk.StringVar(value='—')
            ttk.Label(row, textvariable=var, anchor='w', wraplength=220, justify='left').pack(
                side='left', fill='x', expand=True)
            self.glyph_inspector_meta_vars[key] = var

        self.glyph_inspector_detail_status_var = tk.StringVar(value='Select a glyph on the left.')
        ttk.Label(detail_col, textvariable=self.glyph_inspector_detail_status_var, style='Hint.TLabel',
                  wraplength=200, justify='left').pack(fill='x', padx=6, pady=(2, 6))

        self._bind_responsive_columns(
            body, self.glyph_inspector_list_col, self.glyph_inspector_detail_col,
            threshold=self._GLYPH_INSPECTOR_WIDE_THRESHOLD, state_attr='_glyph_inspector_layout_wide')

        # Appended to shell.py's _global_bind_funcids so _on_root_destroy
        # can free these too -- see that method's docstring.
        self._global_bind_funcids.append(self.root.bind_all('<Left>', self._on_glyph_inspector_key))
        self._global_bind_funcids.append(self.root.bind_all('<Right>', self._on_glyph_inspector_key))

    # -- font selection ---------------------------------------------------
    def _use_selected_font_in_glyph_inspector(self):
        if self.selected_font is None:
            messagebox.showinfo('No font selected', 'Select a font on Generator first, or click Browse.')
            return
        self.glyph_inspector_font_var.set(str(self.selected_font))
        self._load_glyph_inspector_font(self.selected_font)

    def _browse_glyph_inspector_font(self):
        chosen = filedialog.askopenfilename(
            filetypes=[('Fonts', '*.ttf;*.otf;*.ttc'), ('all files', '*.*')])
        if chosen:
            self.glyph_inspector_font_var.set(chosen)
            self._load_glyph_inspector_font(Path(chosen))

    def _load_glyph_inspector_font_from_field(self, _event=None):
        raw = self.glyph_inspector_font_var.get().strip()
        if not raw:
            return
        font_path = Path(raw)
        if self._glyph_inspector_font == font_path:
            return  # already loaded (or loading) this exact path; FocusOut fires on every tab-away
        self._load_glyph_inspector_font(font_path)

    def _load_glyph_inspector_font(self, font_path: Path):
        if not font_path.exists():
            self.glyph_inspector_font_status_var.set(f'Font not found: {font_path}')
            return

        self._glyph_inspector_load_generation += 1
        generation = self._glyph_inspector_load_generation
        self._glyph_inspector_font = font_path
        self._glyph_inspector_font_info = None
        self._set_glyph_inspector_selected_glyph(None)
        self.glyph_inspector_font_status_var.set(f'Loading {font_path.name}…')
        self.glyph_inspector_status_var.set('Loading glyphs…')
        for child in self.glyph_inspector_grid_inner.winfo_children():
            child.destroy()
        self._glyph_inspector_tile_photos.clear()
        self._glyph_inspector_tile_widgets.clear()

        def worker():
            try:
                info = gen_modelbin_gui.load_font_info(font_path)
            except Exception as exc:
                self.msg_queue.put(('glyph_inspector_font_error', generation, str(exc)))
                return
            self.msg_queue.put(('glyph_inspector_font_loaded', generation, info))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_glyph_inspector_font_loaded(self, info: FontInfo):
        self._glyph_inspector_font_info = info
        weight = f', weight {info.names.weight_class}' if info.names.weight_class else ''
        italic = ', italic' if info.names.is_italic else ''
        glyph_count = sum(len(glyphs) for glyphs in info.glyphs_by_category.values())
        self.glyph_inspector_font_status_var.set(
            f'{info.names.full_name} ({info.names.family} {info.names.subfamily}{weight}{italic}) — '
            f'{glyph_count:,} glyph(s) across {len(info.category_order)} categories.')
        self._populate_glyph_inspector_grid()

    # -- categorized tile grid --------------------------------------------
    def _glyph_inspector_columns_for_width(self, width: int) -> int:
        column_span = GLYPH_TILE_SIZE[0] + 2 * GLYPH_TILE_GAP
        return max(1, width // column_span)

    def _on_glyph_inspector_grid_canvas_configure(self, event) -> None:
        # The scrollregion-driving width update is cheap and stays
        # immediate; only the (potentially expensive) tile relayout is
        # debounced.
        self.glyph_inspector_grid_canvas.itemconfigure(self._glyph_inspector_grid_window, width=event.width)
        width = event.width
        self._debounce('glyph_inspector_grid', self._GRID_RELAYOUT_DEBOUNCE_MS,
                        lambda: self._apply_glyph_inspector_grid_columns(width))

    def _apply_glyph_inspector_grid_columns(self, width: int) -> None:
        columns = self._glyph_inspector_columns_for_width(width)
        changed = False
        for category, previous in list(self._glyph_inspector_category_columns.items()):
            if previous != columns:
                self._glyph_inspector_category_columns[category] = columns
                changed = True
        if changed:
            self._relayout_glyph_inspector_tiles()

    def _relayout_glyph_inspector_tiles(self) -> None:
        for category, inner in self._glyph_inspector_category_inner.items():
            columns = self._glyph_inspector_category_columns.get(category, 1)
            for i, tile in enumerate(inner.winfo_children()):
                tile.grid_configure(row=i // columns, column=i % columns)

    def _matches_glyph_search(self, glyph: GlyphInfo, needle: str) -> bool:
        if not needle:
            return True
        if needle in glyph.char.lower():
            return True
        if needle.startswith('u+') or needle.startswith('0x'):
            hex_part = needle[2:]
            if hex_part and hex_part in f'{glyph.codepoint:04x}':
                return True
        if glyph.unicode_name and needle in glyph.unicode_name.lower():
            return True
        if needle in glyph.glyph_name.lower():
            return True
        return False

    def _populate_glyph_inspector_grid(self):
        info = self._glyph_inspector_font_info
        self._glyph_inspector_grid_generation += 1
        generation = self._glyph_inspector_grid_generation
        for child in self.glyph_inspector_grid_inner.winfo_children():
            child.destroy()
        self._glyph_inspector_tile_photos.clear()
        self._glyph_inspector_tile_widgets.clear()
        self._glyph_inspector_category_inner.clear()
        self._glyph_inspector_category_columns.clear()
        self._glyph_inspector_category_shown.clear()
        self._glyph_inspector_ordered_glyphs = []

        if info is None:
            self.glyph_inspector_status_var.set('Select a font to inspect its glyphs.')
            return

        needle = self.glyph_inspector_search_var.get().strip().lower()
        columns = self._glyph_inspector_columns_for_width(self.glyph_inspector_grid_canvas.winfo_width())
        p = gui_theme.palette()

        render_jobs: list[tuple[str, GlyphInfo]] = []
        total_matched = 0
        for category in info.category_order:
            matched = [g for g in info.glyphs_by_category[category] if self._matches_glyph_search(g, needle)]
            if not matched:
                continue
            total_matched += len(matched)
            self._glyph_inspector_ordered_glyphs.extend(matched)

            header_row = ttk.Frame(self.glyph_inspector_grid_inner)
            header_row.pack(fill='x', pady=(8, 2))
            ttk.Label(header_row, text=gui_theme.hud_label(f'{category} ({len(matched)})'),
                      style='Hint.TLabel').pack(side='left')

            inner = ttk.Frame(self.glyph_inspector_grid_inner, style='Grid.TFrame')
            inner.pack(fill='x')
            self._glyph_inspector_category_inner[category] = inner
            self._glyph_inspector_category_columns[category] = columns

            shown = matched[:GLYPH_CATEGORY_TILE_CAP]
            self._glyph_inspector_category_shown[category] = len(shown)
            render_jobs.extend((category, g) for g in shown)

            overflow = len(matched) - len(shown)
            if overflow > 0:
                self._add_glyph_inspector_expand_row(category, overflow)

        self.glyph_inspector_status_var.set(
            f'{total_matched:,} glyph(s) match.' if needle else f'{total_matched:,} glyph(s).')

        def render_worker():
            for category, glyph in render_jobs:
                if generation != self._glyph_inspector_grid_generation:
                    return
                img = font_preview.render_glyph_tile(
                    info.path, glyph.char, GLYPH_TILE_SIZE, bg=p['entry_bg'], fg=p['fg'])
                self.msg_queue.put(('glyph_inspector_tile', generation, category, glyph, img))

        threading.Thread(target=render_worker, daemon=True).start()

    def _remove_glyph_inspector_expand_row(self, category: str) -> None:
        # The "Show N more" row sits immediately after this category's own
        # tile-grid Frame in stacking order, so it's identifiable without a
        # separate tracking dict.
        siblings = self.glyph_inspector_grid_inner.winfo_children()
        inner = self._glyph_inspector_category_inner.get(category)
        if inner is None or inner not in siblings:
            return
        idx = siblings.index(inner)
        if idx + 1 < len(siblings):
            siblings[idx + 1].destroy()

    def _add_glyph_inspector_expand_row(self, category: str, overflow: int) -> None:
        already_shown = self._glyph_inspector_category_shown.get(category, 0)
        more_row = ttk.Frame(self.glyph_inspector_grid_inner)
        more_row.pack(fill='x', pady=(2, 0))
        if already_shown >= GLYPH_CATEGORY_HARD_CAP:
            ttk.Label(
                more_row, style='Hint.TLabel',
                text=(f'{overflow:,} more in {category} — narrow with search to reach them '
                      f'(showing up to {GLYPH_CATEGORY_HARD_CAP:,} per category at once).'),
            ).pack(side='left')
            return
        step = min(GLYPH_CATEGORY_EXPAND_STEP, overflow, GLYPH_CATEGORY_HARD_CAP - already_shown)
        ttk.Button(
            more_row, text=f'Show {step:,} more in {category} ({overflow:,} remaining)',
            command=lambda c=category: self._expand_glyph_inspector_category(c),
        ).pack(side='left')

    def _expand_glyph_inspector_category(self, category: str):
        info = self._glyph_inspector_font_info
        if info is None or category not in info.glyphs_by_category:
            return  # font reloaded or category no longer exists since the button was built
        needle = self.glyph_inspector_search_var.get().strip().lower()
        matched = [g for g in info.glyphs_by_category[category] if self._matches_glyph_search(g, needle)]
        already_shown = self._glyph_inspector_category_shown.get(category, 0)
        # Grow by one bounded step rather than the full remainder: see
        # GLYPH_CATEGORY_HARD_CAP in state.py for why an unbounded expansion
        # of a huge CJK category is unsafe (Tk PhotoImage/GDI exhaustion).
        step_end = min(len(matched), already_shown + GLYPH_CATEGORY_EXPAND_STEP, GLYPH_CATEGORY_HARD_CAP)
        remaining = matched[already_shown:step_end]
        if not remaining:
            return
        self._glyph_inspector_category_shown[category] = step_end

        self._remove_glyph_inspector_expand_row(category)
        overflow = len(matched) - step_end
        if overflow > 0:
            self._add_glyph_inspector_expand_row(category, overflow)

        generation = self._glyph_inspector_grid_generation
        p = gui_theme.palette()

        def render_worker():
            for glyph in remaining:
                if generation != self._glyph_inspector_grid_generation:
                    return
                img = font_preview.render_glyph_tile(
                    info.path, glyph.char, GLYPH_TILE_SIZE, bg=p['entry_bg'], fg=p['fg'])
                self.msg_queue.put(('glyph_inspector_tile', generation, category, glyph, img))

        threading.Thread(target=render_worker, daemon=True).start()

    def _add_glyph_inspector_tile(self, category: str, glyph: GlyphInfo, pil_image) -> None:
        inner = self._glyph_inspector_category_inner.get(category)
        if inner is None:
            return
        photo = ImageTk.PhotoImage(pil_image)
        key = f'{category}\0{glyph.codepoint}'
        self._glyph_inspector_tile_photos[key] = photo
        idx = len(inner.winfo_children())
        columns = self._glyph_inspector_category_columns.get(category, 1)
        selected = (self._glyph_inspector_selected_glyph is not None
                    and self._glyph_inspector_selected_glyph.codepoint == glyph.codepoint
                    and self._glyph_inspector_selected_glyph.category == category)
        tile = ttk.Label(inner, image=photo, relief='solid' if selected else 'flat', cursor='hand2')
        tile.grid(row=idx // columns, column=idx % columns, padx=GLYPH_TILE_GAP, pady=GLYPH_TILE_GAP)
        tile.bind('<Button-1>', lambda _e, g=glyph: self._select_glyph_inspector_glyph(g))
        self._glyph_inspector_tile_widgets[key] = tile

    # -- selection + inspector detail -------------------------------------
    def _set_glyph_inspector_selected_glyph(self, glyph: GlyphInfo | None) -> None:
        previous = self._glyph_inspector_selected_glyph
        self._glyph_inspector_selected_glyph = glyph
        for target in (previous, glyph):
            if target is None:
                continue
            key = f'{target.category}\0{target.codepoint}'
            tile = self._glyph_inspector_tile_widgets.get(key)
            if tile is not None:
                tile.configure(relief='solid' if target is glyph else 'flat')

    def _select_glyph_inspector_glyph(self, glyph: GlyphInfo):
        self._set_glyph_inspector_selected_glyph(glyph)
        self._refresh_glyph_inspector_detail()

    def _on_glyph_inspector_key(self, event):
        if self._current_tab != 'glyph_inspector':
            return
        focused = self.root.focus_get()
        if isinstance(focused, (tk.Entry, ttk.Entry)):
            return  # typing in the search box or the font path field
        step = -1 if event.keysym == 'Left' else 1
        # Compare mode's filmstrip cards are plain Labels, not real Tk
        # focus targets (matching this file's own existing tile-grid
        # convention: click sets a selected-state variable, keyboard nav
        # is global and reads that state, rather than giving individual
        # tiles real focus) -- so this branches on the active mode instead
        # of on what widget currently holds focus.
        if self.glyph_inspector_mode_var.get() == 'compare':
            self._step_glyph_inspector_compare_focus(step)
            return
        glyphs = self._glyph_inspector_ordered_glyphs
        if not glyphs:
            return
        current = self._glyph_inspector_selected_glyph
        try:
            index = glyphs.index(current) if current is not None else -1
        except ValueError:
            index = -1
        new_index = max(0, min(len(glyphs) - 1, index + step)) if index >= 0 else 0
        self._select_glyph_inspector_glyph(glyphs[new_index])

    def _set_glyph_inspector_meta(self, **values: str) -> None:
        for key, var in self.glyph_inspector_meta_vars.items():
            var.set(values.get(key, '—'))

    def _update_glyph_inspector_compare_row(self, mode: str) -> None:
        if mode == 'compare':
            self.glyph_inspector_compare_row.pack(
                fill='x', padx=6, pady=(0, 2), after=self.glyph_inspector_mode_row)
            self.glyph_inspector_compare_legend.pack(
                fill='x', padx=6, pady=(0, 4), after=self.glyph_inspector_preview_canvas)
            self.glyph_inspector_compare_focus_label.pack(
                pady=(0, 4), after=self.glyph_inspector_compare_legend)
            self.glyph_inspector_compare_filmstrip.pack(
                fill='x', padx=6, pady=(0, 4), after=self.glyph_inspector_compare_focus_label)
            self.glyph_inspector_compare_ledger.pack(
                fill='x', padx=6, pady=(0, 4), before=self.glyph_inspector_meta_frame)
        else:
            self.glyph_inspector_compare_row.pack_forget()
            self.glyph_inspector_compare_legend.pack_forget()
            self.glyph_inspector_compare_focus_label.pack_forget()
            self.glyph_inspector_compare_filmstrip.pack_forget()
            self.glyph_inspector_compare_ledger.pack_forget()
            self._glyph_inspector_compare_metrics = None

    def _refresh_glyph_inspector_detail(self):
        glyph = self._glyph_inspector_selected_glyph
        info = self._glyph_inspector_font_info
        mode = self.glyph_inspector_mode_var.get()
        self._update_glyph_inspector_compare_row(mode)
        self.glyph_inspector_preview_canvas.delete('all')
        if glyph is None or info is None:
            self._set_glyph_inspector_meta()
            self.glyph_inspector_detail_status_var.set('Select a glyph on the left.')
            return

        self._set_glyph_inspector_meta(
            char=glyph.char, codepoint=f'U+{glyph.codepoint:04X}',
            unicode_name=glyph.unicode_name or '(unnamed)', glyph_name=glyph.glyph_name,
            category=glyph.category)

        try:
            geometry = gen_modelbin_gui.glyph_geometry(info.path, glyph)
        except Exception as exc:
            self.glyph_inspector_detail_status_var.set(f"Couldn't read glyph geometry: {exc}")
            geometry = None

        if geometry is not None:
            self.glyph_inspector_meta_vars['advance_width'].set(f'{geometry.advance_width:g} units')
            if geometry.bbox is not None:
                self.glyph_inspector_meta_vars['bearings'].set(
                    f'L {geometry.left_side_bearing:g} · R {geometry.right_side_bearing:g}')
                x_min, y_min, x_max, y_max = geometry.bbox
                self.glyph_inspector_meta_vars['bbox'].set(
                    f'{geometry.width:g} × {geometry.height:g} '
                    f'(x {x_min:g}..{x_max:g}, y {y_min:g}..{y_max:g})')
            else:
                self.glyph_inspector_meta_vars['bearings'].set(f'L {geometry.left_side_bearing:g} · R —')
                self.glyph_inspector_meta_vars['bbox'].set('(no drawable outline)')

        if mode == 'reference':
            self._render_glyph_inspector_reference(glyph, info)
        elif mode == 'generated':
            self._render_glyph_inspector_generated(glyph, info)
        elif mode == 'compare':
            self._render_glyph_inspector_compare(glyph, info)

    def _render_glyph_inspector_reference(self, glyph: GlyphInfo, info: FontInfo) -> None:
        p = gui_theme.palette()
        try:
            image = glyph_reference_preview.render_glyph_reference(
                info.path, glyph.char, GLYPH_PREVIEW_SIZE,
                units_per_em=info.metrics.units_per_em, ascender=info.metrics.ascender,
                descender=info.metrics.descender, cap_height=info.metrics.cap_height,
                x_height=info.metrics.x_height, bg=p['canvas_bg'], fg=p['fg'],
                guide_color=p['border'], label_color=p['hint'])
        except Exception as exc:
            self.glyph_inspector_detail_status_var.set(f"Couldn't render {glyph.char!r}: {exc}")
            return

        self._glyph_inspector_preview_photo = ImageTk.PhotoImage(image)
        self.glyph_inspector_preview_canvas.create_image(0, 0, anchor='nw',
                                                          image=self._glyph_inspector_preview_photo)
        self.glyph_inspector_detail_status_var.set(
            "Reference — rendered directly from the font's outline.")

    # -- Generated ------------------------------------------------------------
    def _glyph_inspector_generated_cache_key(self, char: str, font_path: Path) -> tuple:
        return (str(font_path), char, self.compute_backend_var.get())

    def _ensure_glyph_inspector_generated(self, glyph: GlyphInfo, info: FontInfo) -> dict | None:
        """Return the cached fit result for `glyph`, or `None` and kick off a
        background worker if it isn't ready yet. Cached per (font, char,
        compute backend), same idea as Configurator's `_configurator_fit_cache`,
        since re-running the fitter on every Left/Right keypress would be
        wasteful. The caller re-checks the cache once the worker's completion
        message re-triggers `_refresh_glyph_inspector_detail`."""
        cache_key = self._glyph_inspector_generated_cache_key(glyph.char, info.path)
        cached = self._glyph_inspector_generated_cache.get(cache_key)
        if cached is not None:
            return cached

        self._glyph_inspector_generate_generation += 1
        generation = self._glyph_inspector_generate_generation
        font_path = info.path
        char = glyph.char
        backend_choice = self.compute_backend_var.get()

        def worker():
            try:
                backend = gen_modelbin_gui.resolve_backend(backend_choice)
                if backend_choice in ('cuda', 'directml') and not backend.available:
                    raise RuntimeError(backend.detail)
                shapes, strategy = fit_glyph_with_strategy(
                    char, font_path, compute_backend=backend.resolved, policy=DEFAULT_POLICY)
            except Exception as exc:
                self.msg_queue.put(('glyph_inspector_generated_error', generation, cache_key, str(exc)))
                return
            self.msg_queue.put(('glyph_inspector_generated_ready', generation, cache_key,
                                {'shapes': shapes, 'strategy': strategy, 'backend': backend}))

        threading.Thread(target=worker, daemon=True).start()
        return None

    def _render_glyph_inspector_generated(self, glyph: GlyphInfo, info: FontInfo) -> None:
        result = self._ensure_glyph_inspector_generated(glyph, info)
        if result is None:
            self.glyph_inspector_detail_status_var.set(
                f'Generating ({self.compute_backend_var.get().upper()})…')
            return
        if 'error' in result:
            self.glyph_inspector_detail_status_var.set(f"Couldn't generate: {result['error']}")
            return

        p = gui_theme.palette()
        image = file_preview.render_json_preview(
            result['shapes'], GLYPH_PREVIEW_SIZE, bg=p['canvas_bg'], fg=p['fg'])
        self._glyph_inspector_preview_photo = ImageTk.PhotoImage(image)
        self.glyph_inspector_preview_canvas.create_image(0, 0, anchor='nw',
                                                          image=self._glyph_inspector_preview_photo)
        mask_count = sum(1 for s in result['shapes'] if s.get('mask'))
        self.glyph_inspector_detail_status_var.set(
            f"Generated — {len(result['shapes'])} shape(s), {mask_count} mask cutout(s), "
            f"strategy {result['strategy']} ({result['backend'].resolved.upper()}).")

    # -- Compare ----------------------------------------------------------------
    def _load_glyph_inspector_handmade_file(self) -> None:
        glyph = self._glyph_inspector_selected_glyph
        if glyph is None:
            messagebox.showinfo('No glyph selected', 'Select a glyph on the left first.')
            return
        chosen = filedialog.askopenfilename(
            title=f'Load a hand-made shape file for {glyph.char!r}',
            filetypes=[('Shape JSON', '*.json'), ('all files', '*.*')])
        if not chosen:
            return
        try:
            data = json.loads(Path(chosen).read_text(encoding='utf-8'))
            shapes = data.get('shapes') if isinstance(data, dict) else None
            if not shapes:
                raise ValueError(
                    'no non-empty "shapes" array found. This must be a single-glyph, origin-'
                    'centered {"shapes": [...]} file (the same format Configurator\'s manual '
                    'overrides use, and what gen_fontpack.py --output json produces per '
                    'character) — not a whole multi-glyph design export.')
        except Exception as exc:
            messagebox.showerror('Could not load file', f'{Path(chosen).name}: {exc}')
            return
        self._glyph_inspector_handmade_shapes[glyph.char] = shapes
        self._glyph_inspector_handmade_path[glyph.char] = chosen
        self._glyph_inspector_compare_target_var.set('handmade')
        self._refresh_glyph_inspector_detail()

    def _render_glyph_inspector_compare(self, glyph: GlyphInfo, info: FontInfo) -> None:
        result = self._ensure_glyph_inspector_generated(glyph, info)
        if result is None:
            self.glyph_inspector_detail_status_var.set(
                f'Generating ({self.compute_backend_var.get().upper()})…')
            return
        if 'error' in result:
            self.glyph_inspector_detail_status_var.set(f"Couldn't generate: {result['error']}")
            return

        resolution = glyph_quality.DEFAULT_VERIFY_RESOLUTION
        generated_mask, unknown = glyph_quality.render_shapes_mask(result['shapes'], resolution)

        target_source = self._glyph_inspector_compare_target_var.get()
        if target_source == 'handmade':
            handmade = self._glyph_inspector_handmade_shapes.get(glyph.char)
            if handmade is None:
                self.glyph_inspector_detail_status_var.set(
                    "No hand-made file loaded for this glyph — use 'Load hand-made file...' above.")
                return
            target_mask, _ = glyph_quality.render_shapes_mask(handmade, resolution)
            target_label = f"hand-made ({Path(self._glyph_inspector_handmade_path[glyph.char]).name})"
        else:
            try:
                contours, upm = extract_contours(glyph.char, info.path, 8)
                target_mask = rasterize_contours(normalize_to_128(contours, upm), resolution)
            except Exception as exc:
                self.glyph_inspector_detail_status_var.set(f"Couldn't rasterize font outline: {exc}")
                return
            target_label = 'font outline'

        metrics = glyph_quality.compare_masks(target_mask, generated_mask, unknown_type_words=unknown)
        overlay = glyph_quality.diff_overlay_image(target_mask, generated_mask)
        image = overlay.resize(GLYPH_PREVIEW_SIZE, Image.NEAREST)
        self._glyph_inspector_preview_photo = ImageTk.PhotoImage(image)
        self.glyph_inspector_preview_canvas.create_image(0, 0, anchor='nw',
                                                          image=self._glyph_inspector_preview_photo)

        self._glyph_inspector_compare_metrics = metrics
        self._render_glyph_inspector_compare_focus()
        self._render_glyph_inspector_compare_ledger()
        # The legend above the canvas explains the overlay's colors, so this
        # status line matches Reference/Generated's own "Mode: what you're
        # looking at" phrasing instead of repeating that explanation.
        self.glyph_inspector_detail_status_var.set(f'Compare — diff overlay against {target_label}.')

    def _glyph_inspector_compare_metric_shortfall(self, key: str) -> bool:
        """True only for the two exact-count metrics when generated falls
        short of expected -- an exact integer comparison, never a
        fabricated threshold. IoU/boundary F1 are never individually
        flagged; see gauges.render_ring_gauge's own docstring for why."""
        metrics = self._glyph_inspector_compare_metrics
        if metrics is None or key not in ('components', 'holes'):
            return False
        return metrics[f'{key}_generated'] < metrics[f'{key}_expected']

    def _render_glyph_inspector_compare_focus(self) -> None:
        metrics = self._glyph_inspector_compare_metrics
        if metrics is None:
            return
        p = gui_theme.palette()
        key = _COMPARE_METRIC_ORDER[self._glyph_inspector_compare_focus_index]
        if key in ('iou', 'boundary_f1'):
            image = gauges.render_ring_gauge(metrics[key], GLYPH_PREVIEW_SIZE[0], p)
        else:
            image = gauges.render_count_pill(
                metrics[f'{key}_generated'], metrics[f'{key}_expected'],
                (GLYPH_PREVIEW_SIZE[0], 90), p)
        self._glyph_inspector_compare_focus_photo = ImageTk.PhotoImage(image)
        self.glyph_inspector_compare_focus_label.configure(image=self._glyph_inspector_compare_focus_photo)

        for card_key, card in self._glyph_inspector_compare_cards.items():
            selected = card_key == key
            shortfall = self._glyph_inspector_compare_metric_shortfall(card_key)
            card.configure(
                bg=p['accent'] if selected else p['panel_alt'],
                fg=p['select_fg'] if selected else (p['danger'] if shortfall else p['fg']))

    def _render_glyph_inspector_compare_ledger(self) -> None:
        metrics = self._glyph_inspector_compare_metrics
        if metrics is None:
            return
        p = gui_theme.palette()
        for key, label_widget in self._glyph_inspector_compare_ledger_labels.items():
            if key in ('iou', 'boundary_f1'):
                text, color = f'{metrics[key]:.3f}', p['fg']
            else:
                generated, expected = metrics[f'{key}_generated'], metrics[f'{key}_expected']
                text = f'{generated} / {expected}'
                color = p['danger'] if generated < expected else p['fg']
            label_widget.configure(text=text, fg=color, bg=p['panel_alt'])

        verdict = metrics['verdict']
        if verdict == 'pass':
            self.glyph_inspector_compare_verdict.configure(text='VERDICT: PASS', fg=p['success'])
        elif verdict == 'review':
            self.glyph_inspector_compare_verdict.configure(text='VERDICT: REVIEW', fg=p['warn'])
        else:
            # compare_masks() only ever returns "pass"/"review" -- silently
            # falling back to one of them here would misreport a result the
            # data doesn't actually support.
            raise ValueError(f'unrecognized compare verdict: {verdict!r}')
        self.glyph_inspector_compare_verdict.configure(bg=p['panel_alt'])

    def _set_glyph_inspector_compare_focus(self, key: str) -> None:
        try:
            self._glyph_inspector_compare_focus_index = _COMPARE_METRIC_ORDER.index(key)
        except ValueError:
            return
        self._render_glyph_inspector_compare_focus()

    def _step_glyph_inspector_compare_focus(self, step: int) -> None:
        if self._glyph_inspector_compare_metrics is None:
            return
        count = len(_COMPARE_METRIC_ORDER)
        self._glyph_inspector_compare_focus_index = (self._glyph_inspector_compare_focus_index + step) % count
        self._render_glyph_inspector_compare_focus()
