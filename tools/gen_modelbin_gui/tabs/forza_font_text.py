"""Forza Font Text tab: type arbitrary text and lay it out with one of the
11 native in-game vinyl fonts (`forza_writer.layout.layout_forza_text`).

This is not a fitted font. It is not traced from any file. Every glyph is
FH6's own native letter mesh, placed and scaled. The in-game Vinyl Editor
already owns this artwork. Nothing here approximates it. Output is real,
final, ready shapes.

Sibling to ascii_art.py, which does the same thing on a fixed monospace
grid. This does it as free-flowing proportional text. Neither uses a font
this tool generated or one installed on the machine. Only the letterforms
the in-game Vinyl Editor itself already has.
"""

import sys
from pathlib import Path

import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk

from PIL import ImageTk

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import file_preview  # noqa: E402
import gui_theme  # noqa: E402
from gen_forza_fonts_reference import FONT_IDENTIFICATION  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
from forza_writer.export import save as save_composed_json, to_json as composed_to_json  # noqa: E402
from forza_writer.fabric_project import save as save_project, to_fabric_project  # noqa: E402
from forza_writer.layout import layout_forza_text  # noqa: E402
from forza_writer.shapes import char_to_resource  # noqa: E402

from ..state import PREVIEW_SIZE  # noqa: E402


def _font_choice_label(font: int) -> str:
    ident = FONT_IDENTIFICATION.get(font, {"confirmed": False, "note": "Unidentified."})
    mark = "Confirmed" if ident["confirmed"] else "Lead"
    note = ident["note"]
    if note.strip().lower() == "unidentified.":
        return f"Forza Font {font}"
    return f"Forza Font {font} ({mark}: {note})"


def _placed_chars(text: str, font: int) -> list[str]:
    """Every character layout_forza_text() actually turns into a shape, in
    the same order. Space and unsupported characters produce no shape and
    are not in this list. layout_forza_text() itself returns plain shape
    dicts with no character attached, so this walks the same text with the
    same skip rule to rebuild a matching (shape index, character) pairing
    for named Editor Groups. It does not call layout_forza_text() itself
    and does not duplicate its position/scale math. Only the skip rule is
    shared."""
    lines = text.replace("\r\n", "\n").split("\n")
    chars = []
    for line in lines:
        for char in line:
            if char == " ":
                continue
            if char_to_resource(char, font):
                chars.append(char)
    return chars


class ForzaFontTextTabMixin:
    def _build_forza_font_text_page(self):
        page = ttk.Frame(self.page_container)
        self._pages['forza_font_text'] = page
        content = self._build_scroll_shell(page, 'forza_font_text')

        ttk.Label(
            content,
            text="Type text and lay it out with one of FH6's 11 built-in native fonts. Every "
                 "glyph is the game's own letter mesh, not a fitted or traced substitute. Output "
                 "drops straight into KFPS as finished, editable shapes.",
            style='Intro.TLabel', wraplength=gui_theme.WRAP_WIDE, justify='left',
        ).pack(fill='x', **gui_theme.PAGE_INTRO_PAD)

        text_frame = ttk.LabelFrame(content, text=gui_theme.hud_label('1. Text'))
        text_frame.pack(fill='x', **gui_theme.SECTION_PAD)
        self.forza_text_widget = tk.Text(text_frame, height=6, wrap='word')
        self.forza_text_widget.pack(fill='x', **gui_theme.ROW_PAD)
        self._register_independent_scroll(self.forza_text_widget)

        settings_frame = ttk.LabelFrame(content, text=gui_theme.hud_label('2. Font & Layout'))
        settings_frame.pack(fill='x', **gui_theme.SECTION_PAD)
        row1 = ttk.Frame(settings_frame)
        row1.pack(fill='x', **gui_theme.ROW_PAD)
        ttk.Label(row1, text='Forza Font:').pack(side='left')
        self.forza_font_var = tk.IntVar(value=1)
        font_choices = list(range(1, 12))
        self.forza_font_combo = ttk.Combobox(
            row1, state='readonly', width=44,
            values=[_font_choice_label(f) for f in font_choices])
        self.forza_font_combo.current(0)
        self.forza_font_combo.pack(side='left', padx=(4, 16))
        self.forza_font_combo.bind('<<ComboboxSelected>>', self._on_forza_font_combo_changed)

        ttk.Label(row1, text='Height:').pack(side='left')
        self.forza_height_var = tk.DoubleVar(value=360.0)
        ttk.Spinbox(row1, from_=10.0, to=5000.0, increment=10.0, width=7,
                    textvariable=self.forza_height_var).pack(side='left', padx=(4, 0))

        ttk.Label(
            settings_frame,
            text='All 11 fonts support the exact same characters. Switching fonts changes '
                 'letterform style only. It never adds character support.',
            style='Hint.TLabel', wraplength=gui_theme.WRAP_WIDE, justify='left',
        ).pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)

        color_row = ttk.Frame(settings_frame)
        color_row.pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)
        ttk.Label(color_row, text='Color:').pack(side='left')
        self.forza_text_color = (255, 255, 255, 255)
        self.forza_text_color_swatch = tk.Label(
            color_row, text='  ', bg='#ffffff', relief='sunken', width=3)
        self.forza_text_color_swatch.pack(side='left', padx=(4, 4))
        ttk.Button(color_row, text='Choose...', command=self._pick_forza_text_color).pack(side='left')

        action_row = ttk.Frame(content)
        action_row.pack(fill='x', **gui_theme.SECTION_PAD)
        ttk.Button(action_row, text='Preview', command=self._forza_text_run_preview).pack(side='left')
        self.forza_text_save_btn = ttk.Button(
            action_row, text='Save .json...', command=self._save_forza_text, state='disabled')
        self.forza_text_save_btn.pack(side='left', padx=(6, 0))
        self.forza_text_save_project_btn = ttk.Button(
            action_row, text='Save .fabric-project.json...', command=self._save_forza_text_project,
            state='disabled')
        self.forza_text_save_project_btn.pack(side='left', padx=(6, 0))
        self.forza_text_status_var = tk.StringVar(value='Type some text and click Preview.')
        self.forza_text_status_lbl = ttk.Label(
            action_row, textvariable=self.forza_text_status_var, style='Hint.TLabel',
            wraplength=gui_theme.WRAP_MED, justify='left')
        self.forza_text_status_lbl.pack(side='left', fill='x', expand=True, padx=(12, 0))

        preview_frame = ttk.LabelFrame(content, text=gui_theme.hud_label('Preview'))
        preview_frame.pack(fill='x', **gui_theme.SECTION_PAD)
        ttk.Label(
            preview_frame,
            text='Layout preview only. It shows line breaks and character coverage, not the '
                 "exact native vinyl letterforms (this tool has no local thumbnails for those). "
                 'Orange text marks a character with no native shape. It will not place.',
            style='Hint.TLabel', wraplength=gui_theme.WRAP_WIDE, justify='left',
        ).pack(fill='x', **gui_theme.ROW_PAD)
        self.forza_text_canvas = tk.Canvas(preview_frame, width=PREVIEW_SIZE[0],
                                            height=PREVIEW_SIZE[1], highlightthickness=1)
        self.forza_text_canvas.pack(fill='x', **gui_theme.ROW_PAD)

        self._forza_text_shapes: list[dict] = []
        self._forza_text_chars: list[str] = []
        self._forza_text_payload: dict | None = None
        self._forza_text_photo = None
        self._forza_text_preview_signature: tuple | None = None

    def _on_forza_font_combo_changed(self, _event=None):
        self.forza_font_var.set(self.forza_font_combo.current() + 1)

    def _forza_current_font(self) -> int:
        return max(1, min(11, self.forza_font_var.get()))

    def _pick_forza_text_color(self):
        _rgb, hex_color = colorchooser.askcolor(color='#%02x%02x%02x' % self.forza_text_color[:3])
        if hex_color is None:
            return
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        self.forza_text_color = (r, g, b, 255)
        self.forza_text_color_swatch.configure(bg=hex_color)

    def _forza_text_run_preview(self):
        text = self.forza_text_widget.get('1.0', 'end-1c')
        if not text.strip():
            self.forza_text_status_var.set('Type some text first.')
            self.forza_text_status_lbl.configure(style='Warn.TLabel')
            return
        try:
            target_height = float(self.forza_height_var.get())
        except (tk.TclError, ValueError):
            self.forza_text_status_var.set('Height must be a number.')
            self.forza_text_status_lbl.configure(style='Warn.TLabel')
            return

        font = self._forza_current_font()
        shapes = layout_forza_text(text, font=font, target_height=target_height)
        for shape in shapes:
            shape['color'] = list(self.forza_text_color)
        self._forza_text_shapes = shapes
        self._forza_text_payload = composed_to_json(shapes)
        self._forza_text_preview_signature = self._forza_text_current_signature()

        lines = text.replace('\r\n', '\n').split('\n')
        unsupported = {c for c in text if c not in ('\n', '\r', ' ') and not char_to_resource(c, font)}

        p = gui_theme.palette()
        image = file_preview.render_forza_text_preview(
            lines, unsupported, size=PREVIEW_SIZE, bg=p['canvas_bg'], fg=p['fg'])
        self._forza_text_photo = ImageTk.PhotoImage(image)
        self.forza_text_canvas.delete('all')
        self.forza_text_canvas.create_image(0, 0, anchor='nw', image=self._forza_text_photo)

        total_chars = sum(1 for c in text if c not in ('\n', '\r', ' '))
        status = (f'{len(shapes)} of {total_chars} character(s) placed. '
                  f'{len(unsupported)} distinct unsupported character(s).')
        self.forza_text_status_var.set(status)
        self.forza_text_status_lbl.configure(style='Warn.TLabel' if unsupported else 'Success.TLabel')
        self.forza_text_save_btn.configure(state='normal' if shapes else 'disabled')
        self.forza_text_save_project_btn.configure(state='normal' if shapes else 'disabled')
        self._forza_text_chars = _placed_chars(text, font)
        self._log(f'--- Forza Font Text preview: font {font}, {len(shapes)} shapes ---')

    def _forza_text_current_signature(self) -> tuple:
        return (
            self.forza_text_widget.get('1.0', 'end-1c'),
            self._forza_current_font(),
            str(self.forza_height_var.get()),
            self.forza_text_color,
        )

    def _save_forza_text(self):
        if not self._forza_text_payload or not self._forza_text_shapes:
            return
        if self._forza_text_preview_signature != self._forza_text_current_signature():
            self.forza_text_save_btn.configure(state='disabled')
            self.forza_text_status_var.set(
                'Settings changed since the last preview. Click Preview again before saving.')
            self.forza_text_status_lbl.configure(style='Warn.TLabel')
            return
        chosen = filedialog.asksaveasfilename(
            defaultextension='.json', filetypes=[('JSON', '*.json'), ('all files', '*.*')],
            initialdir=self.direct_out_var.get(), initialfile='forza_font_text.json')
        if not chosen:
            return
        try:
            Path(chosen).parent.mkdir(parents=True, exist_ok=True)
            save_composed_json(self._forza_text_payload, chosen)
            self.forza_text_status_var.set(f'Saved {len(self._forza_text_shapes)} shape(s) to {Path(chosen).name}.')
            self.forza_text_status_lbl.configure(style='Success.TLabel')
            self._log(f'--- Saved Forza Font Text JSON: {chosen} ---', tag='success')
        except Exception as exc:
            messagebox.showerror('Save failed', str(exc))

    def _save_forza_text_project(self):
        if not self._forza_text_shapes:
            return
        if self._forza_text_preview_signature != self._forza_text_current_signature():
            self.forza_text_save_project_btn.configure(state='disabled')
            self.forza_text_status_var.set(
                'Settings changed since the last preview. Click Preview again before saving.')
            self.forza_text_status_lbl.configure(style='Warn.TLabel')
            return
        chosen = filedialog.asksaveasfilename(
            defaultextension='.fabric-project.json',
            filetypes=[('KFPS Fabric Project', '*.fabric-project.json'), ('all files', '*.*')],
            initialdir=self.direct_out_var.get(), initialfile='forza_font_text.fabric-project.json')
        if not chosen:
            return
        try:
            # One Editor Group per placed character. Position, not name,
            # carries meaning here (see forza_writer.glyph_template for
            # that convention elsewhere), but each character still needs
            # its own group so KFPS lets a user select, move, or recolor
            # one letter without touching the rest. Index prefix keeps
            # group names unique when the same character repeats.
            groups = [(f'{i + 1}: {char}', [i]) for i, char in enumerate(self._forza_text_chars)]
            project = to_fabric_project(self._forza_text_shapes, name='Forza Font Text', groups=groups)
            Path(chosen).parent.mkdir(parents=True, exist_ok=True)
            save_project(project, chosen)
            self.forza_text_status_var.set(
                f'Saved {len(self._forza_text_shapes)} shape(s) to {Path(chosen).name}, '
                f'{len(groups)} group(s).')
            self.forza_text_status_lbl.configure(style='Success.TLabel')
            self._log(f'--- Saved Forza Font Text project: {chosen} ---', tag='success')
        except Exception as exc:
            messagebox.showerror('Save failed', str(exc))
