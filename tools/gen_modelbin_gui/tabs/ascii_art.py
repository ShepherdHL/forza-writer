"""ASCII Art tab: paste existing ASCII art and place it on a strict,
uniform grid using one of the 11 native in-game vinyl fonts
(`forza_writer.ascii_grid` / `forza_writer.shapes`) — never a font this tool
generated or one installed on the machine, since the in-game Vinyl Editor
can only ever place its own native letterforms.
"""

import sys
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import ImageTk

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import file_preview  # noqa: E402
import gui_theme  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
from forza_writer.ascii_grid import (  # noqa: E402
    layout_ascii_grid, normalize_block, scan_unsupported, supported_chars)
from forza_writer.export import save as save_composed_json, to_json as composed_to_json  # noqa: E402

from ..color_picker_widget import ColorPickerWidget  # noqa: E402
from ..state import ASCII_PREVIEW_SIZE  # noqa: E402

_MAX_REMAP_ROWS = 40  # distinct unsupported characters shown for remapping

# gui_theme's named wrap tiers (WRAP_WIDE/MED/NARROW) are all calibrated for
# a full-width single-column page — too wide for this tab's own left
# controls column now that it sits beside a large preview panel. Matches
# Composer's Color panel, which hardcodes its own narrow-column wraplength
# (220) for the same reason rather than reusing a page-width tier.
_CONTROLS_WRAP = 340


class AsciiArtTabMixin:
    # Body width (px) below which the preview stacks under the controls
    # instead of sitting beside them. Empirically measured against the
    # controls column's own natural width (the Text widget is pinned to
    # width=48 characters specifically so this column has a predictable,
    # modest footprint) plus a preview panel that's actually worth having
    # beside it — see the same measurement approach used to fix Composer's
    # and Glyph Inspector's own thresholds in the 1920x1080 resize audit.
    _ASCII_ART_WIDE_THRESHOLD = 860
    _ASCII_PREVIEW_RESIZE_DEBOUNCE_MS = 120

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

        # Controls on the left at a fixed, modest width; a large preview
        # that actually grows into whatever room a maximized window gives
        # it on the right — the same shape as Composer's/Glyph Inspector's
        # own two-column pages, but with the expand side flipped (the
        # preview is the thing worth spending extra width on here, not the
        # controls), via _bind_responsive_columns's `expand='right'`.
        body = ttk.Frame(content)
        body.pack(fill='both', expand=True, **gui_theme.SECTION_PAD)
        self.ascii_body = body

        left_col = ttk.Frame(body)
        self.ascii_left_col = left_col

        text_frame = ttk.LabelFrame(left_col, text=gui_theme.hud_label('1. Paste ASCII Art'))
        text_frame.pack(fill='x')
        # width=48: without an explicit character width a Text widget's
        # natural size defaults wide enough to make this whole column
        # balloon back out to roughly what it was before this pass, at
        # the expense of the preview it was supposed to make room for.
        self.ascii_text_widget = tk.Text(text_frame, width=48, height=12, wrap='none',
                                          font=('Consolas', 10))
        self.ascii_text_widget.pack(fill='x', **gui_theme.ROW_PAD)
        self._register_independent_scroll(self.ascii_text_widget)
        ascii_actions_row, self.ascii_clear_btn, self.ascii_select_all_btn = (
            self._build_text_box_actions_row(text_frame, self.ascii_text_widget))
        ascii_actions_row.pack(fill='x', **gui_theme.ROW_PAD)
        ttk.Label(
            text_frame,
            text='Ragged lines are padded to a rectangle automatically. Tabs expand to 4 spaces.',
            style='Hint.TLabel', wraplength=_CONTROLS_WRAP, justify='left',
        ).pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)

        settings_frame = ttk.LabelFrame(left_col, text=gui_theme.hud_label('2. Grid Settings'))
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
            style='Hint.TLabel', wraplength=_CONTROLS_WRAP, justify='left',
        ).pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)

        remap_frame = ttk.LabelFrame(
            left_col, text=gui_theme.hud_label('3. Unsupported Characters'))
        remap_frame.pack(fill='x', **gui_theme.SECTION_PAD)
        ttk.Label(
            remap_frame,
            text="Characters the selected font can't place — most punctuation beyond "
                 '$ £ ¥ € æ ^ ß @ # + % ; : / ! ? & is still unavailable in the native vinyl fonts. '
                 'Leave blank to skip a cell, or type a single replacement character to use instead. '
                 'Nothing is substituted automatically.',
            style='Hint.TLabel', wraplength=_CONTROLS_WRAP, justify='left',
        ).pack(fill='x', **gui_theme.ROW_PAD)
        self.ascii_remap_container = ttk.Frame(remap_frame)
        self.ascii_remap_container.pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)
        self.ascii_remap_vars: dict[str, tk.StringVar] = {}
        self.ascii_remap_status_var = tk.StringVar(value='Click "Preview" to scan for unsupported characters.')
        ttk.Label(remap_frame, textvariable=self.ascii_remap_status_var, style='Hint.TLabel',
                  wraplength=_CONTROLS_WRAP, justify='left').pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)

        # Experimental, deliberately unpolished: a solid Square is a poor
        # stand-in for the missing letterform, not a real fix -- this is
        # just here to see whether it reads better than a blank cell.
        self.ascii_placeholder_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            remap_frame, text='Experiment: fill unsupported cells with a placeholder square',
            variable=self.ascii_placeholder_var).pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)

        action_row = ttk.Frame(left_col)
        action_row.pack(fill='x', **gui_theme.SECTION_PAD)
        ttk.Button(action_row, text='Preview', command=self._ascii_run_preview).pack(side='left')
        self.ascii_save_btn = ttk.Button(
            action_row, text='Save .json...', command=self._save_ascii_art, state='disabled')
        self.ascii_save_btn.pack(side='left', padx=(6, 0))
        self.ascii_status_var = tk.StringVar(value='Paste some ASCII art and click Preview.')
        self.ascii_status_lbl = ttk.Label(
            action_row, textvariable=self.ascii_status_var, style='Hint.TLabel',
            wraplength=200, justify='left')
        self.ascii_status_lbl.pack(side='left', fill='x', expand=True, padx=(12, 0))

        preview_frame = ttk.LabelFrame(body, text=gui_theme.hud_label('Preview'))
        self.ascii_preview_panel = preview_frame

        # Right-hand column, alongside Preview -- the same right-hand slot
        # every page with a Color control uses.
        color_frame = ttk.LabelFrame(preview_frame, text=gui_theme.hud_label('Color'))
        color_frame.pack(fill='x', **gui_theme.ROW_PAD)
        self.ascii_color_picker = ColorPickerWidget(
            color_frame, settings_key='color_ascii_art', on_change=self._on_ascii_color_change,
            title='')
        self.ascii_color_picker.pack(fill='x', padx=6, pady=6)
        self.ascii_color = self.ascii_color_picker.color

        ttk.Label(
            preview_frame,
            text='Layout preview only — it shows grid alignment and character coverage, not the '
                 "exact native vinyl letterforms (this tool doesn't have local thumbnails for those). "
                 'Orange text marks a cell whose character has no native shape. It will not place.',
            style='Hint.TLabel', wraplength=gui_theme.WRAP_WIDE, justify='left',
        ).pack(fill='x', **gui_theme.ROW_PAD)
        # No fixed size: this canvas fills whatever room the panel actually
        # has (fill='both', expand=True) and redraws itself to match --
        # ASCII_PREVIEW_SIZE is just the sensible initial size before the
        # first real layout pass. Re-rendering on every resize step would
        # repeat real drawing work on every intermediate width during a
        # live drag, so this is debounced the same way the large CJK-font
        # glyph-tile relayout already had to be.
        self.ascii_canvas = tk.Canvas(preview_frame, width=ASCII_PREVIEW_SIZE[0],
                                      height=ASCII_PREVIEW_SIZE[1], highlightthickness=1)
        self.ascii_canvas.pack(fill='both', expand=True, **gui_theme.ROW_PAD_BOTTOM)
        self.ascii_canvas.bind('<Configure>', self._on_ascii_canvas_configure)

        self._bind_responsive_columns(
            body, left_col, preview_frame, threshold=self._ASCII_ART_WIDE_THRESHOLD, expand='right')

        self._ascii_shapes: list[dict] = []
        self._ascii_payload: dict | None = None
        self._ascii_photo = None
        self._ascii_preview_signature: tuple | None = None
        # Cached inputs from the last successful preview render, so a
        # resize can redraw at the new size without re-running
        # layout_ascii_grid()/rescanning unsupported characters -- both
        # real work, and neither of which actually depends on canvas size.
        self._ascii_preview_rows: list[str] | None = None
        self._ascii_preview_supported: set[str] | None = None
        self._ascii_preview_remap: dict[str, str | None] | None = None

    def _on_ascii_color_change(self, rgba: tuple):
        self.ascii_color = rgba

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
        # An empty entry normally forces the cell blank (see the "blank if
        # empty" hint next to each row). The placeholder experiment wants
        # those same untouched entries to fall through to layout_ascii_grid's
        # own placeholder logic instead, so it skips them here rather than
        # baking in an explicit blank.
        placeholder = self.ascii_placeholder_var.get()
        remap: dict[str, str | None] = {}
        for char, var in self.ascii_remap_vars.items():
            value = var.get()
            if value:
                remap[char] = value[0]
            elif not placeholder:
                remap[char] = None
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
            remap=remap, color=self.ascii_color,
            placeholder_unsupported=self.ascii_placeholder_var.get())
        self._ascii_shapes = shapes
        self._ascii_payload = composed_to_json(shapes)
        self._ascii_preview_signature = self._ascii_current_signature()

        self._ascii_preview_rows = rows
        self._ascii_preview_supported = supported
        self._ascii_preview_remap = remap
        self._redraw_ascii_preview()

        cols = max((len(r) for r in rows), default=0)
        total_cells = sum(len(r) for r in rows)
        blank_cells = total_cells - len(shapes)
        status = (f'{len(rows)} row(s) x {cols} col(s): {len(shapes)} glyph(s) placed, '
                  f'{blank_cells} cell(s) blank ({len(unsupported)} distinct unsupported character(s)).')
        self.ascii_status_var.set(status)
        self.ascii_status_lbl.configure(style='Warn.TLabel' if unsupported else 'Success.TLabel')
        self.ascii_save_btn.configure(state='normal' if shapes else 'disabled')
        self._log(f'--- ASCII Art preview: {len(shapes)} shapes, {blank_cells} blank cell(s) ---')

    def _redraw_ascii_preview(self) -> None:
        """Render the cached layout at the canvas's *current* actual size.
        Safe to call with nothing cached yet (before the first Preview
        click) or with a not-yet-laid-out canvas -- both just no-op rather
        than drawing a degenerate image."""
        if self._ascii_preview_rows is None:
            return
        width = self.ascii_canvas.winfo_width()
        height = self.ascii_canvas.winfo_height()
        if width <= 1 or height <= 1:
            return
        p = gui_theme.palette()
        image = file_preview.render_ascii_grid_preview(
            self._ascii_preview_rows, self._ascii_preview_supported, self._ascii_preview_remap,
            size=(width, height), bg=p['canvas_bg'], fg=p['fg'])
        self._ascii_photo = ImageTk.PhotoImage(image)
        self.ascii_canvas.delete('all')
        self.ascii_canvas.create_image(0, 0, anchor='nw', image=self._ascii_photo)

    def _on_ascii_canvas_configure(self, _event) -> None:
        # Debounced: a live resize-drag fires many Configure events per
        # second, and re-rendering the grid preview on every one of them
        # (real PIL drawing work, not just repositioning) is exactly the
        # kind of repeated-expensive-work-on-every-intermediate-width that
        # stalled the Glyph Inspector tile grid before that was debounced
        # too -- same fix, applied here before it became a live problem
        # rather than after.
        self._debounce('ascii_preview_resize', self._ASCII_PREVIEW_RESIZE_DEBOUNCE_MS,
                        self._redraw_ascii_preview)

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
