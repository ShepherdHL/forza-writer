"""Glyph Template tab: generate a KFPS-importable glyph template for a font.
A labeled grid, one cell per character, with the font's own letterforms
embedded as a tracing guide.

A thin GUI wrapper around the two CLI tools that already do this work
(nothing here reimplements grid/SVG/font-embedding logic):

`tools/gen_glyph_template.py` (single template, one curated charset) for a
font with a small, mostly-Latin glyph set, and `tools/gen_font_block_
templates.py` (one template per Unicode block the font covers, the batch
mode originally built for the Liberation Sans default template library) for
a font with a large or non-Latin library, so it doesn't produce one
unwieldy template.

Open the exported `_blank.fabric-project.json` in Kloudy's Fabric Editor,
draw each glyph inside its labeled cell, group every glyph's shapes
(Editor Groups), then run `tools/import_glyph_template.py` to turn it into
a fontpack.
"""

import sys
import threading
from pathlib import Path

import gen_modelbin_gui
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import gui_settings  # noqa: E402
import gui_theme  # noqa: E402
from gen_fontpack import sanitize_prefix  # noqa: E402
import gen_glyph_template  # noqa: E402
import gen_font_block_templates  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
from fontTools.ttLib import TTFont  # noqa: E402
from forza_writer.fabric_project import save as save_project  # noqa: E402
from forza_writer.font_info import FontInfo  # noqa: E402
from forza_writer.glyph_template import (  # noqa: E402
    DEFAULT_CHARS_PER_ROW, DEFAULT_TRACE_TEXT_COLOR, TEMPLATE_UNICODE_BLOCKS, blocks_covered_by_font,
    save_template, validate_hex_color)

# The first four TEMPLATE_UNICODE_BLOCKS entries are exactly the ranges that
# make up "Basic Latin" (see forza_writer.glyph_template's own comment on
# TEMPLATE_UNICODE_BLOCKS): uppercase, lowercase, digits, ASCII punctuation.
# A font covering anything past those four is the "large library" case the
# Split mode below exists for, so that's what picks the default mode once a
# font loads.
_BASIC_LATIN_BLOCK_NAMES = frozenset(name for name, _ranges in TEMPLATE_UNICODE_BLOCKS[:4])


class GlyphTemplateTabMixin:
    def _build_glyph_template_page(self):
        page = ttk.Frame(self.page_container)
        self._pages['glyph_template'] = page
        content = self._build_scroll_shell(page, 'glyph_template')

        ttk.Label(
            content,
            text="Generate an labeled uniform grid for your selected font, in the form of an SVG Template."
                 "This can be used in the KFPS Fabric Editor, or used as a tracing guide in the game.",
            style='Intro.TLabel', wraplength=gui_theme.WRAP_WIDE, justify='left',
        ).pack(fill='x', **gui_theme.PAGE_INTRO_PAD)

        # -- 1. Font ------------------------------------------------------
        font_frame = ttk.LabelFrame(content, text=gui_theme.hud_label('1. Font'))
        font_frame.pack(fill='x', **gui_theme.SECTION_PAD)
        font_row = ttk.Frame(font_frame)
        font_row.pack(fill='x', **gui_theme.ROW_PAD)
        self.glyph_template_font_var = tk.StringVar()
        font_entry = ttk.Entry(font_row, textvariable=self.glyph_template_font_var)
        font_entry.pack(side='left', fill='x', expand=True, padx=(0, 4))
        font_entry.bind('<Return>', self._load_glyph_template_font_from_field)
        font_entry.bind('<FocusOut>', self._load_glyph_template_font_from_field)
        ttk.Button(font_row, text='Use selected font',
                   command=self._use_selected_font_in_glyph_template).pack(side='left', padx=2)
        ttk.Button(font_row, text='Browse...',
                   command=self._browse_glyph_template_font).pack(side='left', padx=2)

        self.glyph_template_font_status_var = tk.StringVar(value='Select a font to build a template for.')
        ttk.Label(font_frame, textvariable=self.glyph_template_font_status_var, style='Hint.TLabel',
                  wraplength=gui_theme.WRAP_WIDE, justify='left').pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)
        ttk.Label(
            font_frame,
            text="The font file is embedded directly into the generated SVG/project as a tracing guide "
                 "(nothing fetched or scraped from anywhere). " \
                 "Only use a font you actually hold a license for.",
            style='Warn.TLabel', wraplength=gui_theme.WRAP_WIDE, justify='left',
        ).pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)

        color_row = ttk.Frame(font_frame)
        color_row.pack(fill='x', **gui_theme.ROW_PAD)
        ttk.Label(color_row, text='Tracing color:').pack(side='left', padx=4)
        self.glyph_template_text_color_var = tk.StringVar(value=DEFAULT_TRACE_TEXT_COLOR)
        self.glyph_template_color_swatch = tk.Label(
            color_row, width=4, relief='solid', borderwidth=1,
            background=DEFAULT_TRACE_TEXT_COLOR, cursor='hand2')
        self.glyph_template_color_swatch.pack(side='left', padx=(0, 6))
        self.glyph_template_color_swatch.bind('<Button-1>', self._pick_glyph_template_text_color)
        color_entry = ttk.Entry(color_row, textvariable=self.glyph_template_text_color_var, width=10)
        color_entry.pack(side='left')
        color_entry.bind('<Return>', self._apply_glyph_template_text_color_from_field)
        color_entry.bind('<FocusOut>', self._apply_glyph_template_text_color_from_field)
        ttk.Label(
            font_frame,
            text='Fill color of the traced letterform in the generated SVG. Click the swatch, or type '
                 'a #rgb/#rrggbb hex code. Pick something that stands out while tracing over it in KFPS.',
            style='Hint.TLabel', wraplength=gui_theme.WRAP_WIDE, justify='left',
        ).pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)

        # -- 2. Charset -----------------------------------------------------
        mode_frame = ttk.LabelFrame(content, text=gui_theme.hud_label('2. Charset'))
        mode_frame.pack(fill='x', **gui_theme.SECTION_PAD)
        self.glyph_template_mode_var = tk.StringVar(value='single')

        single_row = ttk.Frame(mode_frame)
        single_row.pack(fill='x', **gui_theme.ROW_PAD)
        ttk.Radiobutton(single_row, text='Single template', value='single',
                         variable=self.glyph_template_mode_var,
                         command=self._on_glyph_template_mode_changed).pack(side='left')
        self.glyph_template_charset_var = tk.StringVar(value='basic-latin')
        ttk.Combobox(single_row, textvariable=self.glyph_template_charset_var, state='readonly', width=14,
                     values=list(gen_glyph_template.CHARSETS)).pack(side='left', padx=(10, 4))
        ttk.Label(single_row, text='Chars/row:').pack(side='left', padx=(10, 2))
        self.glyph_template_chars_per_row_var = tk.IntVar(value=DEFAULT_CHARS_PER_ROW)
        ttk.Spinbox(single_row, from_=4, to=26, width=4,
                    textvariable=self.glyph_template_chars_per_row_var).pack(side='left')

        split_row = ttk.Frame(mode_frame)
        split_row.pack(fill='x', **gui_theme.ROW_PAD)
        ttk.Radiobutton(split_row, text='Split by Unicode block (recommended for large libraries)',
                         value='split', variable=self.glyph_template_mode_var,
                         command=self._on_glyph_template_mode_changed).pack(side='left')
        ttk.Label(split_row, text='Min glyphs/block:').pack(side='left', padx=(10, 2))
        self.glyph_template_min_chars_var = tk.IntVar(value=gen_font_block_templates.DEFAULT_MIN_CHARS)
        ttk.Spinbox(split_row, from_=1, to=999, width=5,
                    textvariable=self.glyph_template_min_chars_var).pack(side='left')
        # Added after construction (see bottom of this method) so the write
        # this trace reacts to is only ever a later user edit, never the
        # Variable's own initial value assignment above.
        self.glyph_template_min_chars_var.trace_add(
            'write', lambda *_: self._refresh_glyph_template_block_checklist())

        ttk.Label(
            mode_frame,
            text="Split writes one template per Unicode block the font actually covers (its own folder "
                 "+ SVG each), so a large or non-Latin font doesn't produce one unwieldy grid. This is "
                 "the same approach used to build the Liberation Sans default template library.",
            style='Hint.TLabel', wraplength=gui_theme.WRAP_WIDE, justify='left',
        ).pack(fill='x', padx=gui_theme.INDENT_PAD, pady=gui_theme.ROW_PAD_BOTTOM['pady'])

        self.glyph_template_blocks_frame = ttk.Frame(mode_frame)
        self.glyph_template_block_vars: dict[str, tk.BooleanVar] = {}
        self.glyph_template_blocks_status_var = tk.StringVar(
            value='Load a font to see which Unicode blocks it covers.')
        self.glyph_template_blocks_status_label = ttk.Label(
            mode_frame, textvariable=self.glyph_template_blocks_status_var, style='Hint.TLabel',
            wraplength=gui_theme.WRAP_WIDE, justify='left')
        self.glyph_template_blocks_status_label.pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)

        # -- 3. Output ------------------------------------------------------
        out_frame = ttk.LabelFrame(content, text=gui_theme.hud_label('3. Output'))
        out_frame.pack(fill='x', **gui_theme.SECTION_PAD)
        prefix_row = ttk.Frame(out_frame)
        prefix_row.pack(fill='x', **gui_theme.ROW_PAD)
        ttk.Label(prefix_row, text='Prefix:').pack(side='left', padx=4)
        self.glyph_template_prefix_var = tk.StringVar(value='CUSTOM')
        self.glyph_template_prefix_var.trace_add('write', self._on_glyph_template_prefix_changed)
        ttk.Entry(prefix_row, textvariable=self.glyph_template_prefix_var, width=30).pack(
            side='left', padx=4)

        out_row = ttk.Frame(out_frame)
        out_row.pack(fill='x', **gui_theme.ROW_PAD)
        ttk.Label(out_row, text='Output folder:').pack(side='left', padx=4)
        self.glyph_template_out_var = tk.StringVar(
            value=gui_settings.load_settings()['glyph_template_output_dir'])
        ttk.Entry(out_row, textvariable=self.glyph_template_out_var).pack(
            side='left', fill='x', expand=True, padx=4)
        ttk.Button(out_row, text='Browse...', command=self._pick_glyph_template_out_dir).pack(
            side='left', padx=2)
        ttk.Label(
            out_frame,
            text='A separate folder from Fontpacks Output Directory. These are blank tracing '
                 'templates, not finished fontpacks. Single mode writes <folder>/<prefix>/ for the '
                 'default basic-latin charset, or <folder>/<prefix>-<CHARSET>/ for any other charset '
                 '(so generating Hiragana then Katakana under the same prefix stays separate). Split '
                 'mode writes one <folder>/<prefix>-<BLOCK>/ per checked block.',
            style='Hint.TLabel', wraplength=gui_theme.WRAP_WIDE, justify='left',
        ).pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)

        # -- 4. Generate ------------------------------------------------------
        run_row = ttk.Frame(content)
        run_row.pack(fill='x', **gui_theme.SECTION_PAD)
        self.glyph_template_generate_btn = ttk.Button(
            run_row, text='Generate', style='Accent.TButton', command=self._start_glyph_template_generate)
        self.glyph_template_generate_btn.pack(side='left', padx=4)
        self.glyph_template_status_var = tk.StringVar(value='')
        ttk.Label(run_row, textvariable=self.glyph_template_status_var, style='Hint.TLabel',
                  wraplength=gui_theme.WRAP_MED, justify='left').pack(side='left', padx=8)

        self._on_glyph_template_mode_changed()

    # -- font selection -----------------------------------------------------
    def _use_selected_font_in_glyph_template(self):
        if self.selected_font is None:
            messagebox.showinfo('No font selected', 'Select a font on Generator first, or click Browse.')
            return
        self.glyph_template_font_var.set(str(self.selected_font))
        self._load_glyph_template_font(self.selected_font)

    def _browse_glyph_template_font(self):
        chosen = filedialog.askopenfilename(
            filetypes=[('Fonts', '*.ttf;*.otf;*.ttc'), ('all files', '*.*')])
        if chosen:
            self.glyph_template_font_var.set(chosen)
            self._load_glyph_template_font(Path(chosen))

    def _load_glyph_template_font_from_field(self, _event=None):
        raw = self.glyph_template_font_var.get().strip()
        if not raw:
            return
        font_path = Path(raw)
        if self._glyph_template_font == font_path:
            return  # already loaded (or loading) this exact path; FocusOut fires on every tab-away
        self._load_glyph_template_font(font_path)

    def _load_glyph_template_font(self, font_path: Path):
        if not font_path.exists():
            self.glyph_template_font_status_var.set(f'Font not found: {font_path}')
            return

        self._glyph_template_load_generation += 1
        generation = self._glyph_template_load_generation
        self._glyph_template_font = font_path
        self._glyph_template_font_info = None
        self._glyph_template_covered_blocks = []
        self.glyph_template_font_status_var.set(f'Loading {font_path.name}…')
        self.glyph_template_blocks_status_var.set('Scanning Unicode block coverage…')

        def worker():
            try:
                info = gen_modelbin_gui.load_font_info(font_path)
                font = TTFont(str(font_path), fontNumber=0)
                try:
                    cmap = font.getBestCmap() or {}
                finally:
                    font.close()
                # min_chars=1 here (not the min-glyphs-per-block spinbox
                # value): this is the full inventory of covered blocks,
                # re-filtered by _refresh_glyph_template_block_checklist as
                # that spinbox changes, without re-scanning the font.
                covered = blocks_covered_by_font(cmap, min_chars=1)
            except Exception as exc:
                self.msg_queue.put(('glyph_template_font_error', generation, str(exc)))
                return
            self.msg_queue.put(('glyph_template_font_loaded', generation, info, covered))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_glyph_template_font_loaded(self, info: FontInfo, covered: list[tuple[str, list[str]]]) -> None:
        self._glyph_template_font_info = info
        self._glyph_template_covered_blocks = covered
        glyph_count = sum(len(chars) for _name, chars in covered)
        weight = f', weight {info.names.weight_class}' if info.names.weight_class else ''
        italic = ', italic' if info.names.is_italic else ''
        self.glyph_template_font_status_var.set(
            f'{info.names.full_name} ({info.names.family} {info.names.subfamily}{weight}{italic}). '
            f'{glyph_count:,} glyph(s) across {len(covered)} Unicode block(s).')

        if not self._glyph_template_prefix_edited:
            self.glyph_template_prefix_var.set(sanitize_prefix(info.names.family))
            self._glyph_template_prefix_edited = False  # trace handler set it True; undo

        beyond_basic_latin = any(name not in _BASIC_LATIN_BLOCK_NAMES for name, _chars in covered)
        self.glyph_template_mode_var.set('split' if beyond_basic_latin else 'single')
        self._refresh_glyph_template_block_checklist()
        self._on_glyph_template_mode_changed()

    # -- mode / block checklist ----------------------------------------------
    def _on_glyph_template_mode_changed(self) -> None:
        if self.glyph_template_mode_var.get() == 'split':
            self.glyph_template_blocks_frame.pack(
                fill='x', padx=gui_theme.INDENT_PAD, pady=(0, 6),
                before=self.glyph_template_blocks_status_label)
        else:
            self.glyph_template_blocks_frame.pack_forget()

    def _refresh_glyph_template_block_checklist(self) -> None:
        for child in self.glyph_template_blocks_frame.winfo_children():
            child.destroy()
        self.glyph_template_block_vars.clear()

        covered = self._glyph_template_covered_blocks
        if not covered:
            self.glyph_template_blocks_status_var.set('Load a font to see which Unicode blocks it covers.')
            return

        min_chars = max(1, self.glyph_template_min_chars_var.get())
        eligible = [(name, chars) for name, chars in covered if len(chars) >= min_chars]
        if not eligible:
            self.glyph_template_blocks_status_var.set(
                f'No block reaches {min_chars} glyph(s) at this threshold. Lower "Min glyphs/block".')
            return

        for name, chars in eligible:
            var = tk.BooleanVar(value=True)
            self.glyph_template_block_vars[name] = var
            ttk.Checkbutton(self.glyph_template_blocks_frame, variable=var,
                            text=f'{name} ({len(chars)})').pack(anchor='w')
        self.glyph_template_blocks_status_var.set(
            f'{len(eligible)} of {len(TEMPLATE_UNICODE_BLOCKS)} known block(s) covered at this threshold. '
            'Uncheck any you don\'t want a template for.')

    # -- prefix / output dir --------------------------------------------------
    def _on_glyph_template_prefix_changed(self, *_args) -> None:
        self._glyph_template_prefix_edited = True

    def _pick_glyph_template_out_dir(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.glyph_template_out_var.get() or self.out_var.get())
        if chosen:
            self.glyph_template_out_var.set(chosen)
            gui_settings.update_settings({'glyph_template_output_dir': chosen})

    # -- tracing color ----------------------------------------------------------
    def _set_glyph_template_text_color(self, hex_color: str) -> None:
        self.glyph_template_text_color_var.set(hex_color)
        self.glyph_template_color_swatch.configure(background=hex_color)

    def _pick_glyph_template_text_color(self, _event=None) -> None:
        initial = self.glyph_template_text_color_var.get().strip()
        try:
            validate_hex_color(initial)
        except ValueError:
            initial = DEFAULT_TRACE_TEXT_COLOR
        _rgb, hex_color = colorchooser.askcolor(color=initial, title='Tracing color')
        if hex_color:
            self._set_glyph_template_text_color(hex_color)

    def _apply_glyph_template_text_color_from_field(self, _event=None) -> None:
        raw = self.glyph_template_text_color_var.get().strip()
        try:
            validate_hex_color(raw)
        except ValueError:
            messagebox.showinfo('Invalid color', f'{raw!r} is not a valid #rgb or #rrggbb hex color.')
            self.glyph_template_text_color_var.set(self.glyph_template_color_swatch.cget('background'))
            return
        self._set_glyph_template_text_color(raw)

    # -- generate -------------------------------------------------------------
    def _start_glyph_template_generate(self) -> None:
        if self._glyph_template_worker is not None and self._glyph_template_worker.is_alive():
            self._log('A glyph template is already generating.', tag='warn')
            return
        font_path = self._glyph_template_font
        if font_path is None:
            messagebox.showinfo('No font selected', 'Select a font first.')
            return
        text_color = self.glyph_template_text_color_var.get().strip()
        try:
            validate_hex_color(text_color)
        except ValueError:
            messagebox.showinfo('Invalid color', f'{text_color!r} is not a valid #rgb or #rrggbb hex color.')
            return

        prefix = sanitize_prefix(self.glyph_template_prefix_var.get())
        out_dir_raw = self.glyph_template_out_var.get() or gui_settings.DEFAULT_SETTINGS['glyph_template_output_dir']
        out_dir = Path(out_dir_raw)
        gui_settings.update_settings({'glyph_template_output_dir': out_dir_raw})
        mode = self.glyph_template_mode_var.get()
        chars_per_row = max(1, self.glyph_template_chars_per_row_var.get())

        def post_log(line: str) -> None:
            self.msg_queue.put(('log', line))

        if mode == 'split':
            only_blocks = {name for name, var in self.glyph_template_block_vars.items() if var.get()}
            if not only_blocks:
                messagebox.showinfo('No blocks selected', 'Check at least one Unicode block to generate.')
                return
            min_chars = max(1, self.glyph_template_min_chars_var.get())

            def worker():
                try:
                    written = []
                    for _block_name, template_id, template, project in (
                            gen_font_block_templates.build_all_block_projects(
                                font_path, prefix, chars_per_row, min_chars, only_blocks, log=post_log,
                                text_color=text_color)):
                        # out_dir/template_id/ directly, matching gen_font_block_templates.py's
                        # own CLI layout. template_id already starts with prefix (see
                        # build_all_block_projects), so a font's blocks already group together
                        # by that shared prefix without an extra nesting level.
                        block_dir = out_dir / template_id
                        save_template(template, block_dir / f'{template_id}_template.json')
                        save_project(project, block_dir / f'{template_id}_blank.fabric-project.json')
                        svg_path = block_dir / f'{template_id}.svg'
                        svg_path.parent.mkdir(parents=True, exist_ok=True)
                        svg_path.write_text(project['editor_source_overlay']['svg_text'], encoding='utf-8')
                        written.append(template_id)
                    self.msg_queue.put((
                        'glyph_template_done', 'success',
                        f'--- {len(written)} block template(s) written under {out_dir} ---'))
                except Exception as exc:
                    self.msg_queue.put(('glyph_template_done', 'danger', f"Couldn't generate: {exc}"))
        else:
            charset = self.glyph_template_charset_var.get()

            def worker():
                try:
                    template, project = gen_glyph_template.build_blank_project(
                        prefix, chars_per_row, charset, font_path, log=post_log, text_color=text_color)
                    # Use the template's own (possibly charset-suffixed) id, not
                    # prefix directly -- see build_blank_project's docstring.
                    # Without this, generating e.g. Hiragana then Katakana under
                    # the same prefix silently overwrote the first SVG/project,
                    # since both would otherwise land at <prefix>/<prefix>.svg.
                    effective_id = template.template_id
                    pack_dir = out_dir / effective_id
                    save_template(template, pack_dir / f'{effective_id}_template.json')
                    save_project(project, pack_dir / f'{effective_id}_blank.fabric-project.json')
                    svg_path = pack_dir / f'{effective_id}.svg'
                    svg_path.parent.mkdir(parents=True, exist_ok=True)
                    svg_path.write_text(project['editor_source_overlay']['svg_text'], encoding='utf-8')
                    self.msg_queue.put((
                        'glyph_template_done', 'success',
                        f'--- {len(template.slots)} slot(s) across {template.row_count} row(s) '
                        f'-> {pack_dir} ---'))
                except Exception as exc:
                    self.msg_queue.put(('glyph_template_done', 'danger', f"Couldn't generate: {exc}"))

        self.glyph_template_generate_btn.configure(state='disabled')
        self.glyph_template_status_var.set('Generating…')
        self._log(f'--- Building glyph template "{prefix}" from {font_path.name} ({mode} mode) ---')
        self._glyph_template_worker = threading.Thread(target=worker, daemon=True)
        self._glyph_template_worker.start()

    def _apply_glyph_template_done(self, tag: str, line: str) -> None:
        self._log(line, tag=tag)
        self.glyph_template_generate_btn.configure(state='normal')
        self.glyph_template_status_var.set('Done.' if tag == 'success' else 'Failed.')
