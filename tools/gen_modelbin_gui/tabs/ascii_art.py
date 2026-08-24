"""ASCII Art tab: paste existing ASCII art and place it on a strict,
uniform grid using one of the 11 native in-game vinyl fonts
(`forza_writer.ascii_grid` / `forza_writer.shapes`) — never a font this tool
generated or one installed on the machine, since the in-game Vinyl Editor
can only ever place its own native letterforms.
"""

import sys
from pathlib import Path

import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk

from PIL import ImageTk

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import file_preview  # noqa: E402
import gui_theme  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
from forza_writer.ascii_grid import (  # noqa: E402
    layout_ascii_grid, normalize_block, scan_unsupported, supported_chars)
from forza_writer.export import save as save_composed_json, to_json as composed_to_json  # noqa: E402

from ..state import ASCII_PREVIEW_SIZE  # noqa: E402

_MAX_REMAP_ROWS = 40  # distinct unsupported characters shown for remapping


class AsciiArtTabMixin:
    def _build_ascii_art_page(self):
        page = ttk.Frame(self.page_container)
        self._pages['ascii_art'] = page
        content = self._build_scroll_shell(page, 'ascii_art')

        ttk.Label(
            content,
            text='Paste existing ASCII art and place it, character-for-character, using one of the '
                 "11 native in-game vinyl fonts. Every cell advances the same fixed width/height "
                 "regardless of its glyph, so columns stay aligned the way they were pasted. This "
                 "never uses a font this tool generated or one installed on your machine — only the "
                 "letterforms the in-game Vinyl Editor itself already has.",
            style='Intro.TLabel', wraplength=gui_theme.WRAP_WIDE, justify='left',
        ).pack(fill='x', **gui_theme.PAGE_INTRO_PAD)

        text_frame = ttk.LabelFrame(content, text=gui_theme.hud_label('1. Paste ASCII Art'))
        text_frame.pack(fill='x', **gui_theme.SECTION_PAD)
        self.ascii_text_widget = tk.Text(text_frame, height=12, wrap='none', font=('Consolas', 10))
        self.ascii_text_widget.pack(fill='x', **gui_theme.ROW_PAD)
        self._register_independent_scroll(self.ascii_text_widget)
        ttk.Label(
            text_frame,
            text='Ragged lines are padded to a rectangle automatically. Tabs expand to 4 spaces.',
            style='Hint.TLabel', wraplength=gui_theme.WRAP_WIDE, justify='left',
        ).pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)

        settings_frame = ttk.LabelFrame(content, text=gui_theme.hud_label('2. Grid Settings'))
        settings_frame.pack(fill='x', **gui_theme.SECTION_PAD)
        row1 = ttk.Frame(settings_frame)
        row1.pack(fill='x', **gui_theme.ROW_PAD)
        ttk.Label(row1, text='Native font (1-11):').pack(side='left')
        self.ascii_font_var = tk.IntVar(value=1)
        ttk.Spinbox(row1, from_=1, to=11, width=4, textvariable=self.ascii_font_var).pack(
            side='left', padx=(4, 16))
        ttk.Label(row1, text='Cell width:').pack(side='left')
        self.ascii_cell_width_var = tk.DoubleVar(value=18.0)
        ttk.Spinbox(row1, from_=1.0, to=200.0, increment=1.0, width=6,
                    textvariable=self.ascii_cell_width_var).pack(side='left', padx=(4, 16))
        ttk.Label(row1, text='Cell height:').pack(side='left')
        self.ascii_cell_height_var = tk.DoubleVar(value=25.0)
        ttk.Spinbox(row1, from_=1.0, to=200.0, increment=1.0, width=6,
                    textvariable=self.ascii_cell_height_var).pack(side='left', padx=(4, 0))
        ttk.Label(
            settings_frame,
            text='All 11 fonts support the exact same characters — only the letterform style '
                 "differs. Switching fonts never fixes an unsupported character; remapping it below "
                 'does.',
            style='Hint.TLabel', wraplength=gui_theme.WRAP_WIDE, justify='left',
        ).pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)

        color_row = ttk.Frame(settings_frame)
        color_row.pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)
        ttk.Label(color_row, text='Color:').pack(side='left')
        self.ascii_color = (255, 255, 255, 255)
        self.ascii_color_swatch = tk.Label(color_row, text='  ', bg='#ffffff', relief='sunken', width=3)
        self.ascii_color_swatch.pack(side='left', padx=(4, 4))
        ttk.Button(color_row, text='Choose...', command=self._pick_ascii_color).pack(side='left')

        remap_frame = ttk.LabelFrame(
            content, text=gui_theme.hud_label('3. Unsupported Characters'))
        remap_frame.pack(fill='x', **gui_theme.SECTION_PAD)
        ttk.Label(
            remap_frame,
            text="Characters the selected font can't place — most punctuation beyond "
                 '$ £ ¥ € æ ^ ß @ # + % ; : / ! ? & is still unavailable in the native vinyl fonts. '
                 'Leave blank to skip a cell, or type a single replacement character to use instead. '
                 'Nothing is substituted automatically.',
            style='Hint.TLabel', wraplength=gui_theme.WRAP_WIDE, justify='left',
        ).pack(fill='x', **gui_theme.ROW_PAD)
        self.ascii_remap_container = ttk.Frame(remap_frame)
        self.ascii_remap_container.pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)
        self.ascii_remap_vars: dict[str, tk.StringVar] = {}
        self.ascii_remap_status_var = tk.StringVar(value='Click "Preview" to scan for unsupported characters.')
        ttk.Label(remap_frame, textvariable=self.ascii_remap_status_var, style='Hint.TLabel',
                  wraplength=gui_theme.WRAP_WIDE, justify='left').pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)

        action_row = ttk.Frame(content)
        action_row.pack(fill='x', **gui_theme.SECTION_PAD)
        ttk.Button(action_row, text='Preview', command=self._ascii_run_preview).pack(side='left')
        self.ascii_save_btn = ttk.Button(
            action_row, text='Save .json...', command=self._save_ascii_art, state='disabled')
        self.ascii_save_btn.pack(side='left', padx=(6, 0))
        self.ascii_status_var = tk.StringVar(value='Paste some ASCII art and click Preview.')
        self.ascii_status_lbl = ttk.Label(
            action_row, textvariable=self.ascii_status_var, style='Hint.TLabel',
            wraplength=gui_theme.WRAP_MED, justify='left')
        self.ascii_status_lbl.pack(side='left', fill='x', expand=True, padx=(12, 0))

        preview_frame = ttk.LabelFrame(content, text=gui_theme.hud_label('Preview'))
        preview_frame.pack(fill='x', **gui_theme.SECTION_PAD)
        ttk.Label(
            preview_frame,
            text='Layout preview only — it shows grid alignment and character coverage, not the '
                 "exact native vinyl letterforms (this tool doesn't have local thumbnails for those). "
                 'Orange text marks a cell that will come out blank.',
            style='Hint.TLabel', wraplength=gui_theme.WRAP_WIDE, justify='left',
        ).pack(fill='x', **gui_theme.ROW_PAD)
        self.ascii_canvas = tk.Canvas(preview_frame, width=ASCII_PREVIEW_SIZE[0],
                                      height=ASCII_PREVIEW_SIZE[1], highlightthickness=1)
        self.ascii_canvas.pack(fill='x', **gui_theme.ROW_PAD)

        self._ascii_shapes: list[dict] = []
        self._ascii_payload: dict | None = None
        self._ascii_photo = None
        self._ascii_preview_signature: tuple | None = None

    def _pick_ascii_color(self):
        _rgb, hex_color = colorchooser.askcolor(color='#%02x%02x%02x' % self.ascii_color[:3])
        if hex_color is None:
            return
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        self.ascii_color = (r, g, b, 255)
        self.ascii_color_swatch.configure(bg=hex_color)

    def _ascii_current_font(self) -> int:
        try:
            return max(1, min(11, int(self.ascii_font_var.get())))
        except (tk.TclError, ValueError):
            return 1

    def _ascii_rebuild_remap_ui(self, unsupported: dict[str, list[tuple[int, int]]]) -> None:
        for child in self.ascii_remap_container.winfo_children():
            child.destroy()
        kept_vars: dict[str, tk.StringVar] = {}
        chars = sorted(unsupported, key=lambda c: unsupported[c][0])
        if not chars:
            self.ascii_remap_vars = {}
            self.ascii_remap_status_var.set('No unsupported characters found — every glyph will place.')
            return
        shown, truncated = chars[:_MAX_REMAP_ROWS], len(chars) > _MAX_REMAP_ROWS
        for char in shown:
            row = ttk.Frame(self.ascii_remap_container)
            row.pack(fill='x', pady=1)
            count = len(unsupported[char])
            label = char if char.strip() else repr(char)
            ttk.Label(row, text=f'{label!r} x{count}:', width=14).pack(side='left')
            var = self.ascii_remap_vars.get(char) or tk.StringVar(value='')
            kept_vars[char] = var
            ttk.Entry(row, textvariable=var, width=4).pack(side='left', padx=(4, 8))
            ttk.Label(row, text='(blank if empty)', style='Hint.TLabel').pack(side='left')
        self.ascii_remap_vars = kept_vars
        note = f' ({len(chars) - _MAX_REMAP_ROWS} more not shown)' if truncated else ''
        self.ascii_remap_status_var.set(
            f'{len(chars)} distinct unsupported character(s) found{note}. '
            f'Type a replacement above, then click Preview again.')

    def _ascii_remap_dict(self) -> dict[str, str | None]:
        remap: dict[str, str | None] = {}
        for char, var in self.ascii_remap_vars.items():
            value = var.get()
            remap[char] = value[0] if value else None
        return remap

    def _ascii_run_preview(self):
        text = self.ascii_text_widget.get('1.0', 'end-1c')
        rows = normalize_block(text)
        if not rows or not any(row.strip() for row in rows):
            self.ascii_status_var.set('Paste some ASCII art first.')
            self.ascii_status_lbl.configure(style='Warn.TLabel')
            return
        try:
            cell_width = float(self.ascii_cell_width_var.get())
            cell_height = float(self.ascii_cell_height_var.get())
        except (tk.TclError, ValueError):
            self.ascii_status_var.set('Cell width/height must be numbers.')
            self.ascii_status_lbl.configure(style='Warn.TLabel')
            return
        font = self._ascii_current_font()
        supported = supported_chars(font)
        unsupported = scan_unsupported(rows, font)
        self._ascii_rebuild_remap_ui(unsupported)
        remap = self._ascii_remap_dict()

        shapes = layout_ascii_grid(
            rows, font=font, cell_width=cell_width, cell_height=cell_height,
            remap=remap, color=self.ascii_color)
        self._ascii_shapes = shapes
        self._ascii_payload = composed_to_json(shapes)
        self._ascii_preview_signature = self._ascii_current_signature()

        p = gui_theme.palette()
        image = file_preview.render_ascii_grid_preview(
            rows, supported, remap, size=ASCII_PREVIEW_SIZE, bg=p['canvas_bg'], fg=p['fg'])
        self._ascii_photo = ImageTk.PhotoImage(image)
        self.ascii_canvas.delete('all')
        self.ascii_canvas.create_image(0, 0, anchor='nw', image=self._ascii_photo)

        cols = max((len(r) for r in rows), default=0)
        total_cells = sum(len(r) for r in rows)
        blank_cells = total_cells - len(shapes)
        status = (f'{len(rows)} row(s) x {cols} col(s): {len(shapes)} glyph(s) placed, '
                  f'{blank_cells} cell(s) blank ({len(unsupported)} distinct unsupported character(s)).')
        self.ascii_status_var.set(status)
        self.ascii_status_lbl.configure(style='Warn.TLabel' if unsupported else 'Success.TLabel')
        self.ascii_save_btn.configure(state='normal' if shapes else 'disabled')
        self._log(f'--- ASCII Art preview: {len(shapes)} shapes, {blank_cells} blank cell(s) ---')

    def _ascii_current_signature(self) -> tuple:
        return (
            self.ascii_text_widget.get('1.0', 'end-1c'),
            self._ascii_current_font(),
            str(self.ascii_cell_width_var.get()),
            str(self.ascii_cell_height_var.get()),
            self.ascii_color,
            tuple(sorted((c, v.get()) for c, v in self.ascii_remap_vars.items())),
        )

    def _save_ascii_art(self):
        if not self._ascii_payload or not self._ascii_shapes:
            return
        if self._ascii_preview_signature != self._ascii_current_signature():
            self.ascii_save_btn.configure(state='disabled')
            self.ascii_status_var.set('Settings changed since the last preview — click Preview again before saving.')
            self.ascii_status_lbl.configure(style='Warn.TLabel')
            return
        chosen = filedialog.asksaveasfilename(
            defaultextension='.json', filetypes=[('JSON', '*.json'), ('all files', '*.*')],
            initialdir=self.direct_out_var.get(), initialfile='ascii_art.json')
        if not chosen:
            return
        try:
            Path(chosen).parent.mkdir(parents=True, exist_ok=True)
            save_composed_json(self._ascii_payload, chosen)
            self.ascii_status_var.set(f'Saved {len(self._ascii_shapes)} shape(s) to {Path(chosen).name}.')
            self.ascii_status_lbl.configure(style='Success.TLabel')
            self._log(f'--- Saved ASCII Art JSON: {chosen} ---', tag='success')
        except Exception as exc:
            messagebox.showerror('Save failed', str(exc))
