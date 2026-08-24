"""Layer Effects tab: build a Layered Glyph Effect (inset/outset/translate/
scale/rotate/boolean layers derived from one source glyph, each independently
colored and ordered) and preview it against sample text, using the same
`forza_writer.layered_effects` engine and `forza_writer.primitive_fit`
pipeline every other tab's generation already goes through -- see
`forza_writer/layered_effects.py`'s module docstring for the full pipeline.

Kept intentionally simple for this first pass (a plain sample-text field
rather than Glyph Inspector's full categorized glyph browser, all layer
property fields always visible rather than dynamically shown/hidden per
operation) -- the spec's own guidance is to keep the interface approachable
before adding depth.
"""

import sys
import threading
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from PIL import Image, ImageTk

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import file_preview  # noqa: E402
import gui_theme  # noqa: E402
import layer_effect_presets_store  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
from forza_writer import forza_colors, layer_presets  # noqa: E402
from forza_writer import layered_effects  # noqa: E402
from forza_writer.layered_effects import EffectLayer, LayerOperation, LayerStack, new_layer_id  # noqa: E402
from forza_writer.layered_effects_text import compose_layered_text  # noqa: E402
from forza_writer.primitive_fit import fit_glyph  # noqa: E402
from forza_writer.text_compose import compose_shape_map  # noqa: E402

from ..state import LAYER_EFFECTS_PREVIEW_SIZE, _rgba_to_hex  # noqa: E402


class LayerEffectsTabMixin:
    _LE_SB_SIZE = 90
    _LE_HUE_WIDTH = 14
    _LE_WIDE_THRESHOLD = 820

    def _build_layer_effects_page(self):
        page = ttk.Frame(self.page_container)
        self._pages['layer_effects'] = page
        content = self._build_scroll_shell(page, 'layer_effects')

        ttk.Label(
            content,
            text='Derive multiple independently colored/transformed geometric layers from a source '
                 'glyph (inset rings, outset borders, offset shadows, boolean combinations) and run '
                 'each through the same primitive generator every other tab uses.',
            style='Intro.TLabel', wraplength=gui_theme.WRAP_WIDE, justify='left',
        ).pack(fill='x', **gui_theme.PAGE_INTRO_PAD)

        # -- state -------------------------------------------------------
        self._layer_effects_font: Path | None = None
        self._layer_effects_stack: LayerStack = layer_presets.preset_concentric_inline()
        self._layer_effects_selected_layer_id = (
            self._layer_effects_stack.layers[0].id if self._layer_effects_stack.layers else None)
        self._layer_effects_shapes: list[dict] = []
        self._layer_effects_compare_shapes: list[dict] = []
        self._layer_effects_groups_by_char: dict = {}
        self._layer_effects_layer_status: dict = {}
        self._layer_effects_generate_generation = 0
        self._layer_effects_picker_hue = 0.0
        self.layer_effects_row_vars: dict[str, tk.BooleanVar] = {}
        self.layer_effects_row_labels: dict[str, tk.Label] = {}
        self._layer_effects_source_choices: dict[str, str] = {}

        # -- 1. Font & sample text ---------------------------------------
        font_frame = ttk.LabelFrame(content, text=gui_theme.hud_label('1. Font & Sample Text'))
        font_frame.pack(fill='x', **gui_theme.SECTION_PAD)
        font_row = ttk.Frame(font_frame)
        font_row.pack(fill='x', **gui_theme.ROW_PAD)
        self.layer_effects_font_var = tk.StringVar()
        font_entry = ttk.Entry(font_row, textvariable=self.layer_effects_font_var)
        font_entry.pack(side='left', fill='x', expand=True, padx=(0, 4))
        font_entry.bind('<Return>', self._load_layer_effects_font_from_field)
        font_entry.bind('<FocusOut>', self._load_layer_effects_font_from_field)
        ttk.Button(font_row, text='Use selected font',
                   command=self._use_selected_font_in_layer_effects).pack(side='left', padx=2)
        ttk.Button(font_row, text='Browse...',
                   command=self._browse_layer_effects_font).pack(side='left', padx=2)

        sample_row = ttk.Frame(font_frame)
        sample_row.pack(fill='x', **gui_theme.ROW_PAD)
        ttk.Label(sample_row, text='Sample text:').pack(side='left')
        self.layer_effects_sample_var = tk.StringVar(value='Ag')
        sample_entry = ttk.Entry(sample_row, textvariable=self.layer_effects_sample_var)
        sample_entry.pack(side='left', fill='x', expand=True, padx=(4, 0))
        sample_entry.bind('<Return>', lambda _e: self._layer_effects_regenerate())
        sample_entry.bind('<FocusOut>', lambda _e: self._layer_effects_regenerate())

        self.layer_effects_font_status_var = tk.StringVar(
            value='Select a font to preview a Layered Glyph Effect.')
        ttk.Label(font_frame, textvariable=self.layer_effects_font_status_var, style='Hint.TLabel',
                  wraplength=gui_theme.WRAP_WIDE, justify='left').pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)

        # -- 2. Preset -----------------------------------------------------
        preset_frame = ttk.LabelFrame(content, text=gui_theme.hud_label('2. Preset'))
        preset_frame.pack(fill='x', **gui_theme.SECTION_PAD)
        preset_row = ttk.Frame(preset_frame)
        preset_row.pack(fill='x', **gui_theme.ROW_PAD)
        self.layer_effects_preset_var = tk.StringVar(value='Concentric Inline')
        ttk.Combobox(preset_row, textvariable=self.layer_effects_preset_var,
                     values=sorted(layer_presets.PRESET_REGISTRY), state='readonly').pack(
            side='left', fill='x', expand=True)
        ttk.Button(preset_row, text='Apply preset',
                   command=self._apply_layer_effects_preset).pack(side='left', padx=(4, 0))

        saved_row = ttk.Frame(preset_frame)
        saved_row.pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)
        ttk.Label(saved_row, text='Saved:').pack(side='left')
        self.layer_effects_saved_preset_var = tk.StringVar()
        self.layer_effects_saved_combo = ttk.Combobox(
            saved_row, textvariable=self.layer_effects_saved_preset_var,
            values=layer_effect_presets_store.list_presets(), state='readonly')
        self.layer_effects_saved_combo.pack(side='left', fill='x', expand=True, padx=(4, 4))
        ttk.Button(saved_row, text='Load', command=self._load_layer_effects_saved_preset).pack(
            side='left', padx=2)
        ttk.Button(saved_row, text='Save current as...', command=self._save_layer_effects_preset).pack(
            side='left', padx=2)
        ttk.Button(saved_row, text='Delete', command=self._delete_layer_effects_saved_preset).pack(
            side='left', padx=2)

        # -- body: layer list + properties (left) / preview (right) -------
        body = ttk.Frame(content)
        body.pack(fill='both', expand=True, padx=8, pady=(2, 8))
        left_col = ttk.Frame(body)
        right_col = ttk.LabelFrame(body, text=gui_theme.hud_label('Preview'))
        self._layer_effects_left_col = left_col
        self._layer_effects_right_col = right_col

        list_frame = ttk.LabelFrame(left_col, text=gui_theme.hud_label('3. Layers'))
        list_frame.pack(fill='x', pady=(0, 8))
        self.layer_effects_rows_container = ttk.Frame(list_frame)
        self.layer_effects_rows_container.pack(fill='x', padx=6, pady=(6, 4))
        btn_row = ttk.Frame(list_frame)
        btn_row.pack(fill='x', padx=6, pady=(0, 6))
        ttk.Button(btn_row, text='+ Add', command=self._add_layer_effects_layer).pack(side='left')
        ttk.Button(btn_row, text='Duplicate', command=self._duplicate_layer_effects_layer).pack(
            side='left', padx=2)
        ttk.Button(btn_row, text='Delete', command=self._delete_layer_effects_layer).pack(
            side='left', padx=2)
        ttk.Button(btn_row, text='▲', width=3,
                   command=lambda: self._move_layer_effects_layer(-1)).pack(side='left', padx=(8, 2))
        ttk.Button(btn_row, text='▼', width=3,
                   command=lambda: self._move_layer_effects_layer(1)).pack(side='left', padx=2)

        self._build_layer_effects_properties(left_col)
        self._build_layer_effects_color_picker(left_col)

        self.layer_effects_preview_canvas = tk.Canvas(
            right_col, width=LAYER_EFFECTS_PREVIEW_SIZE[0], height=LAYER_EFFECTS_PREVIEW_SIZE[1],
            highlightthickness=1)
        self.layer_effects_preview_canvas.pack(padx=6, pady=6)
        self.layer_effects_compare_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(right_col, text='Compare to source (plain, non-layered glyph)',
                        variable=self.layer_effects_compare_var,
                        command=self._refresh_layer_effects_preview).pack(anchor='w', padx=6)
        self.layer_effects_vinyl_count_var = tk.StringVar(value='Estimated vinyls: —')
        ttk.Label(right_col, textvariable=self.layer_effects_vinyl_count_var, style='Hint.TLabel').pack(
            anchor='w', padx=6, pady=(4, 2))
        self.layer_effects_status_var = tk.StringVar(value='Load a font to begin.')
        ttk.Label(right_col, textvariable=self.layer_effects_status_var, style='Hint.TLabel',
                  wraplength=LAYER_EFFECTS_PREVIEW_SIZE[0], justify='left').pack(
            fill='x', padx=6, pady=(0, 6))

        self._bind_responsive_columns(
            body, left_col, right_col, threshold=self._LE_WIDE_THRESHOLD,
            state_attr='_layer_effects_layout_wide')

        self._rebuild_layer_effects_rows()
        self._refresh_layer_effects_properties()

    # -- font loading -----------------------------------------------------

    def _use_selected_font_in_layer_effects(self):
        if getattr(self, 'selected_font', None) is None:
            messagebox.showinfo('No font selected', 'Select a font on Generator first, or click Browse.')
            return
        self.layer_effects_font_var.set(str(self.selected_font))
        self._load_layer_effects_font(self.selected_font)

    def _browse_layer_effects_font(self):
        chosen = filedialog.askopenfilename(
            filetypes=[('Fonts', '*.ttf;*.otf;*.ttc'), ('all files', '*.*')])
        if chosen:
            self.layer_effects_font_var.set(chosen)
            self._load_layer_effects_font(Path(chosen))

    def _load_layer_effects_font_from_field(self, _event=None):
        raw = self.layer_effects_font_var.get().strip()
        if not raw:
            return
        font_path = Path(raw)
        if self._layer_effects_font == font_path:
            return
        self._load_layer_effects_font(font_path)

    def _load_layer_effects_font(self, font_path: Path):
        if not font_path.exists():
            self.layer_effects_font_status_var.set(f'Font not found: {font_path}')
            return
        self._layer_effects_font = font_path
        self.layer_effects_font_status_var.set(f'{font_path.name} loaded.')
        self._layer_effects_regenerate()

    # -- generation (async — the only expensive step) ----------------------

    def _layer_effects_regenerate(self):
        if self._layer_effects_font is None:
            return
        sample = self.layer_effects_sample_var.get() or 'A'
        font_path = self._layer_effects_font
        stack = self._layer_effects_stack
        self._layer_effects_generate_generation += 1
        generation = self._layer_effects_generate_generation
        self.layer_effects_status_var.set('Generating…')

        def worker():
            try:
                shapes, warnings, groups_by_char = compose_layered_text(sample, font_path, stack)
                compare_map = {}
                for char in dict.fromkeys(c for c in sample if not c.isspace()):
                    try:
                        compare_map[char] = fit_glyph(char, font_path)
                    except Exception:
                        compare_map[char] = []
                compare_shapes, _warnings = compose_shape_map(sample, font_path, compare_map)
            except Exception as exc:
                self.msg_queue.put(('layer_effects_generate_error', generation, str(exc)))
                return
            self.msg_queue.put((
                'layer_effects_generate_ready', generation, shapes, warnings, groups_by_char,
                compare_shapes,
            ))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_layer_effects_generated(self, shapes, warnings, groups_by_char, compare_shapes):
        self._layer_effects_shapes = shapes
        self._layer_effects_groups_by_char = groups_by_char
        self._layer_effects_compare_shapes = compare_shapes
        self._layer_effects_layer_status = self._layer_effects_compute_layer_statuses(groups_by_char)
        status = f'{len(shapes)} shape(s) generated.'
        if warnings:
            status += ' ' + '; '.join(warnings)
        self.layer_effects_status_var.set(status)
        self._rebuild_layer_effects_rows()
        self._refresh_layer_effects_preview()

    @staticmethod
    def _layer_effects_compute_layer_statuses(groups_by_char) -> dict:
        statuses = {}
        for groups in groups_by_char.values():
            for group in groups:
                if group.status != 'ok':
                    statuses[group.layer_id] = (group.status, group.warning)
        return statuses

    # -- preview (cheap — never re-runs geometry/generation) ----------------

    def _refresh_layer_effects_preview(self):
        p = gui_theme.palette()
        if self.layer_effects_compare_var.get():
            shapes = self._layer_effects_compare_shapes
        else:
            enabled_ids = {l.id for l in self._layer_effects_stack.layers if l.enabled}
            shapes = [s for s in self._layer_effects_shapes if s.get('layer', {}).get('id') in enabled_ids]
        image = file_preview.render_composed_preview(
            shapes, LAYER_EFFECTS_PREVIEW_SIZE, bg=p['canvas_bg'], fg=p['fg'])
        self._layer_effects_photo = ImageTk.PhotoImage(image)
        self.layer_effects_preview_canvas.delete('all')
        self.layer_effects_preview_canvas.create_image(0, 0, anchor='nw', image=self._layer_effects_photo)
        self.layer_effects_vinyl_count_var.set(f'Estimated vinyls: {len(shapes)}')

    def _layer_effects_refresh_cosmetic_tags(self):
        """Re-apply every layer's *current* color/opacity/name onto the
        already-cached, already-positioned shape list, without re-running
        geometry or `primitive_fit` — the cheap path a color/opacity/rename
        edit takes (see `forza_writer.layered_effects.recolor_shape`)."""
        meta_by_id = {l.id: l for l in self._layer_effects_stack.layers}
        updated = []
        for shape in self._layer_effects_shapes:
            tag = shape.get('layer')
            if tag and tag['id'] in meta_by_id:
                layer = meta_by_id[tag['id']]
                shape = layered_effects.recolor_shape(shape, layer.color, layer.opacity)
                shape['layer'] = {'id': layer.id, 'name': layer.name}
            updated.append(shape)
        self._layer_effects_shapes = updated

    # -- layer list ---------------------------------------------------------

    def _rebuild_layer_effects_rows(self):
        for child in self.layer_effects_rows_container.winfo_children():
            child.destroy()
        self.layer_effects_row_vars = {}
        self.layer_effects_row_labels = {}
        layers = self._layer_effects_stack.layers
        n = len(layers)
        # Front-most layer (last in the list — drawn last, on top) shown at
        # the top of the row list, matching the spec's own mockup ordering
        # (highest number = front).
        for display_index, layer in enumerate(reversed(layers)):
            order_num = n - display_index
            row = ttk.Frame(self.layer_effects_rows_container)
            row.pack(fill='x', pady=1)
            enabled_var = tk.BooleanVar(value=layer.enabled)
            self.layer_effects_row_vars[layer.id] = enabled_var
            ttk.Checkbutton(
                row, variable=enabled_var,
                command=lambda lid=layer.id, v=enabled_var: self._toggle_layer_effects_enabled(lid, v),
            ).pack(side='left')
            warn = self._layer_effects_layer_status.get(layer.id)
            text = f'{order_num}  {layer.name}' + ('  ⚠' if warn else '')
            lbl = tk.Label(row, text=text, anchor='w', cursor='hand2', padx=4)
            lbl.pack(side='left', fill='x', expand=True)
            lbl.bind('<Button-1>', lambda _e, lid=layer.id: self._select_layer_effects_layer(lid))
            self.layer_effects_row_labels[layer.id] = lbl
        self._highlight_layer_effects_selected_row()

    def _highlight_layer_effects_selected_row(self):
        for lid, lbl in self.layer_effects_row_labels.items():
            selected = lid == self._layer_effects_selected_layer_id
            lbl.configure(font=('TkDefaultFont', 9, 'bold' if selected else 'normal'))

    def _select_layer_effects_layer(self, layer_id: str):
        self._layer_effects_selected_layer_id = layer_id
        self._highlight_layer_effects_selected_row()
        self._refresh_layer_effects_properties()

    def _selected_layer_effects_layer(self) -> EffectLayer | None:
        for layer in self._layer_effects_stack.layers:
            if layer.id == self._layer_effects_selected_layer_id:
                return layer
        return None

    def _toggle_layer_effects_enabled(self, layer_id: str, var: tk.BooleanVar):
        layer = next((l for l in self._layer_effects_stack.layers if l.id == layer_id), None)
        if layer is None:
            return
        layer.enabled = bool(var.get())
        if layer.id == self._layer_effects_selected_layer_id:
            self.layer_effects_enabled_var.set(layer.enabled)
        self._refresh_layer_effects_preview()

    # -- add / duplicate / delete / reorder ---------------------------------

    def _add_layer_effects_layer(self):
        layer = EffectLayer(
            id=new_layer_id(), name=f'Layer {len(self._layer_effects_stack.layers) + 1}',
            operation=LayerOperation.ORIGINAL, color=(255, 255, 255, 255))
        self._layer_effects_stack.layers.append(layer)
        self._layer_effects_selected_layer_id = layer.id
        self._rebuild_layer_effects_rows()
        self._refresh_layer_effects_properties()
        self._layer_effects_regenerate()

    def _duplicate_layer_effects_layer(self):
        source = self._selected_layer_effects_layer()
        if source is None:
            return
        copy = EffectLayer.from_dict(source.to_dict())
        copy.id = new_layer_id()
        copy.name = f'{source.name} copy'
        index = self._layer_effects_stack.layers.index(source)
        self._layer_effects_stack.layers.insert(index + 1, copy)
        self._layer_effects_selected_layer_id = copy.id
        self._rebuild_layer_effects_rows()
        self._refresh_layer_effects_properties()
        self._layer_effects_regenerate()

    def _delete_layer_effects_layer(self):
        layer = self._selected_layer_effects_layer()
        if layer is None or len(self._layer_effects_stack.layers) <= 1:
            return
        self._layer_effects_stack.layers.remove(layer)
        self._layer_effects_selected_layer_id = self._layer_effects_stack.layers[-1].id
        self._rebuild_layer_effects_rows()
        self._refresh_layer_effects_properties()
        self._layer_effects_regenerate()

    def _move_layer_effects_layer(self, delta: int):
        layers = self._layer_effects_stack.layers
        layer = self._selected_layer_effects_layer()
        if layer is None:
            return
        index = layers.index(layer)
        new_index = max(0, min(len(layers) - 1, index + delta))
        if new_index == index:
            return
        layers.pop(index)
        layers.insert(new_index, layer)
        self._rebuild_layer_effects_rows()
        self._refresh_layer_effects_properties()
        self._layer_effects_regenerate()

    # -- properties panel -----------------------------------------------------

    def _build_layer_effects_properties(self, parent):
        panel = ttk.LabelFrame(parent, text=gui_theme.hud_label('4. Layer Properties'))
        panel.pack(fill='x')
        grid = ttk.Frame(panel)
        grid.pack(fill='x', padx=6, pady=6)

        self.layer_effects_name_var = tk.StringVar()
        ttk.Label(grid, text='Name').grid(row=0, column=0, sticky='w', padx=(0, 6), pady=2)
        name_entry = ttk.Entry(grid, textvariable=self.layer_effects_name_var, width=22)
        name_entry.grid(row=0, column=1, sticky='we', pady=2)
        name_entry.bind('<Return>', self._commit_layer_effects_name)
        name_entry.bind('<FocusOut>', self._commit_layer_effects_name)

        self.layer_effects_enabled_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(grid, text='Enabled', variable=self.layer_effects_enabled_var,
                        command=self._commit_layer_effects_enabled).grid(
            row=1, column=0, columnspan=2, sticky='w', pady=2)

        ttk.Label(grid, text='Operation').grid(row=2, column=0, sticky='w', padx=(0, 6), pady=2)
        self.layer_effects_operation_var = tk.StringVar()
        op_combo = ttk.Combobox(grid, textvariable=self.layer_effects_operation_var,
                                values=[op.value for op in LayerOperation], state='readonly', width=20)
        op_combo.grid(row=2, column=1, sticky='w', pady=2)
        op_combo.bind('<<ComboboxSelected>>', self._commit_layer_effects_operation)

        ttk.Label(grid, text='Source').grid(row=3, column=0, sticky='w', padx=(0, 6), pady=2)
        self.layer_effects_source_var = tk.StringVar()
        self.layer_effects_source_combo = ttk.Combobox(
            grid, textvariable=self.layer_effects_source_var, state='readonly', width=20)
        self.layer_effects_source_combo.grid(row=3, column=1, sticky='w', pady=2)
        self.layer_effects_source_combo.bind('<<ComboboxSelected>>', self._commit_layer_effects_source)

        def float_field(row, label, default='0'):
            ttk.Label(grid, text=label).grid(row=row, column=0, sticky='w', padx=(0, 6), pady=2)
            var = tk.StringVar(value=default)
            entry = ttk.Entry(grid, textvariable=var, width=10)
            entry.grid(row=row, column=1, sticky='w', pady=2)
            return var, entry

        self.layer_effects_amount_var, e = float_field(4, 'Amount (inset/outset)')
        e.bind('<Return>', self._commit_layer_effects_amount)
        e.bind('<FocusOut>', self._commit_layer_effects_amount)
        self.layer_effects_offset_x_var, e = float_field(5, 'Offset X')
        e.bind('<Return>', self._commit_layer_effects_offset_x)
        e.bind('<FocusOut>', self._commit_layer_effects_offset_x)
        self.layer_effects_offset_y_var, e = float_field(6, 'Offset Y')
        e.bind('<Return>', self._commit_layer_effects_offset_y)
        e.bind('<FocusOut>', self._commit_layer_effects_offset_y)
        self.layer_effects_scale_x_var, e = float_field(7, 'Scale X', '1.0')
        e.bind('<Return>', self._commit_layer_effects_scale_x)
        e.bind('<FocusOut>', self._commit_layer_effects_scale_x)
        self.layer_effects_scale_y_var, e = float_field(8, 'Scale Y', '1.0')
        e.bind('<Return>', self._commit_layer_effects_scale_y)
        e.bind('<FocusOut>', self._commit_layer_effects_scale_y)
        self.layer_effects_rotation_var, e = float_field(9, 'Rotation (deg)')
        e.bind('<Return>', self._commit_layer_effects_rotation)
        e.bind('<FocusOut>', self._commit_layer_effects_rotation)

        ttk.Label(grid, text='Boolean operand').grid(row=10, column=0, sticky='w', padx=(0, 6), pady=2)
        self.layer_effects_boolean_operand_var = tk.StringVar()
        self.layer_effects_boolean_operand_combo = ttk.Combobox(
            grid, textvariable=self.layer_effects_boolean_operand_var, state='readonly', width=20)
        self.layer_effects_boolean_operand_combo.grid(row=10, column=1, sticky='w', pady=2)
        self.layer_effects_boolean_operand_combo.bind(
            '<<ComboboxSelected>>', self._commit_layer_effects_boolean_operand)

        ttk.Label(grid, text='Opacity').grid(row=11, column=0, sticky='w', padx=(0, 6), pady=2)
        self.layer_effects_opacity_var = tk.DoubleVar(value=1.0)
        ttk.Scale(grid, from_=0.0, to=1.0, variable=self.layer_effects_opacity_var, orient='horizontal',
                 length=140, command=self._commit_layer_effects_opacity).grid(
            row=11, column=1, sticky='w', pady=2)

    def _commit_layer_effects_float(self, field_name: str, var: tk.StringVar, default: float):
        layer = self._selected_layer_effects_layer()
        if layer is None:
            return
        try:
            value = float(var.get())
        except (TypeError, ValueError):
            value = default
        setattr(layer, field_name, value)
        var.set(str(value))
        self._layer_effects_regenerate()

    def _commit_layer_effects_amount(self, _e=None):
        self._commit_layer_effects_float('amount', self.layer_effects_amount_var, 0.0)

    def _commit_layer_effects_offset_x(self, _e=None):
        self._commit_layer_effects_float('offset_x', self.layer_effects_offset_x_var, 0.0)

    def _commit_layer_effects_offset_y(self, _e=None):
        self._commit_layer_effects_float('offset_y', self.layer_effects_offset_y_var, 0.0)

    def _commit_layer_effects_scale_x(self, _e=None):
        self._commit_layer_effects_float('scale_x', self.layer_effects_scale_x_var, 1.0)

    def _commit_layer_effects_scale_y(self, _e=None):
        self._commit_layer_effects_float('scale_y', self.layer_effects_scale_y_var, 1.0)

    def _commit_layer_effects_rotation(self, _e=None):
        self._commit_layer_effects_float('rotation_deg', self.layer_effects_rotation_var, 0.0)

    def _commit_layer_effects_name(self, _e=None):
        layer = self._selected_layer_effects_layer()
        if layer is None:
            return
        layer.name = self.layer_effects_name_var.get().strip() or layer.name
        self._rebuild_layer_effects_rows()
        self._layer_effects_refresh_cosmetic_tags()
        self._refresh_layer_effects_preview()

    def _commit_layer_effects_enabled(self):
        layer = self._selected_layer_effects_layer()
        if layer is None:
            return
        layer.enabled = self.layer_effects_enabled_var.get()
        row_var = self.layer_effects_row_vars.get(layer.id)
        if row_var is not None:
            row_var.set(layer.enabled)
        self._refresh_layer_effects_preview()

    def _commit_layer_effects_operation(self, _e=None):
        layer = self._selected_layer_effects_layer()
        if layer is None:
            return
        layer.operation = LayerOperation(self.layer_effects_operation_var.get())
        self._layer_effects_regenerate()

    def _commit_layer_effects_source(self, _e=None):
        layer = self._selected_layer_effects_layer()
        if layer is None:
            return
        label = self.layer_effects_source_var.get()
        layer.source = self._layer_effects_source_choices.get(label, 'original')
        self._layer_effects_regenerate()

    def _commit_layer_effects_boolean_operand(self, _e=None):
        layer = self._selected_layer_effects_layer()
        if layer is None:
            return
        label = self.layer_effects_boolean_operand_var.get()
        layer.boolean_operand = self._layer_effects_source_choices.get(label) if label else None
        self._layer_effects_regenerate()

    def _commit_layer_effects_opacity(self, value):
        layer = self._selected_layer_effects_layer()
        if layer is None:
            return
        try:
            layer.opacity = max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return
        self._layer_effects_refresh_cosmetic_tags()
        self._refresh_layer_effects_preview()

    def _refresh_layer_effects_properties(self):
        layer = self._selected_layer_effects_layer()
        if layer is None:
            return
        self.layer_effects_name_var.set(layer.name)
        self.layer_effects_enabled_var.set(layer.enabled)
        self.layer_effects_operation_var.set(layer.operation.value)
        self.layer_effects_amount_var.set(str(layer.amount))
        self.layer_effects_offset_x_var.set(str(layer.offset_x))
        self.layer_effects_offset_y_var.set(str(layer.offset_y))
        self.layer_effects_scale_x_var.set(str(layer.scale_x))
        self.layer_effects_scale_y_var.set(str(layer.scale_y))
        self.layer_effects_rotation_var.set(str(layer.rotation_deg))
        self.layer_effects_opacity_var.set(layer.opacity)

        index = next((i for i, l in enumerate(self._layer_effects_stack.layers)
                      if l.id == layer.id), None)
        choices = {'original': 'original'}
        labels = ['original']
        if index is not None:
            for earlier in self._layer_effects_stack.layers[:index]:
                choices[earlier.name] = earlier.id
                labels.append(earlier.name)
        self._layer_effects_source_choices = choices
        self.layer_effects_source_combo.configure(values=labels)
        self.layer_effects_source_var.set(
            next((lab for lab, lid in choices.items() if lid == layer.source), 'original'))
        self.layer_effects_boolean_operand_combo.configure(values=labels[1:])
        self.layer_effects_boolean_operand_var.set(
            next((lab for lab, lid in choices.items() if lid == layer.boolean_operand), ''))

        self.layer_effects_hex_var.set(_rgba_to_hex(layer.color))
        self.layer_effects_alpha_var.set(str(layer.color[3]))
        self.layer_effects_color_swatch.configure(background=_rgba_to_hex(layer.color))
        r, g, b, _a = layer.color
        _hue, saturation, brightness = forza_colors.rgb_to_forza_hsb(r, g, b)
        hue = self._layer_effects_picker_hue if saturation <= 0.01 else _hue
        self._redraw_layer_effects_color_picker(hue, saturation, brightness)

    # -- color picker (reuses forza_writer.forza_colors' shared array math,
    #    the same math tools/gen_modelbin_gui/tabs/color_picker.py's own
    #    square/strip were pulled out of) --------------------------------

    def _build_layer_effects_color_picker(self, parent):
        panel = ttk.LabelFrame(parent, text=gui_theme.hud_label('Layer Color'))
        panel.pack(fill='x', pady=(8, 0))

        row = ttk.Frame(panel)
        row.pack(fill='x', padx=6, pady=(6, 4))
        self.layer_effects_sb_canvas = tk.Canvas(
            row, width=self._LE_SB_SIZE, height=self._LE_SB_SIZE, highlightthickness=1, cursor='crosshair')
        self.layer_effects_sb_canvas.pack(side='left')
        self.layer_effects_sb_canvas.bind('<Button-1>', self._on_layer_effects_sb_pick)
        self.layer_effects_sb_canvas.bind('<B1-Motion>', self._on_layer_effects_sb_pick)

        self.layer_effects_hue_canvas = tk.Canvas(
            row, width=self._LE_HUE_WIDTH, height=self._LE_SB_SIZE, highlightthickness=1,
            cursor='sb_v_double_arrow')
        self.layer_effects_hue_canvas.pack(side='left', padx=(6, 0))
        self.layer_effects_hue_canvas.bind('<Button-1>', self._on_layer_effects_hue_pick)
        self.layer_effects_hue_canvas.bind('<B1-Motion>', self._on_layer_effects_hue_pick)
        strip = forza_colors.hue_strip_array(self._LE_SB_SIZE, self._LE_HUE_WIDTH)
        self._layer_effects_hue_photo = ImageTk.PhotoImage(Image.fromarray(strip, 'RGB'))
        self.layer_effects_hue_canvas.create_image(0, 0, anchor='nw', image=self._layer_effects_hue_photo)

        self.layer_effects_color_swatch = tk.Label(
            row, width=6, height=3, relief='solid', borderwidth=1, background='#ffffff')
        self.layer_effects_color_swatch.pack(side='left', padx=(10, 0))

        fields = ttk.Frame(panel)
        fields.pack(fill='x', padx=6, pady=(0, 6))
        self.layer_effects_hex_var = tk.StringVar()
        ttk.Label(fields, text='Hex').grid(row=0, column=0, sticky='w')
        hex_entry = ttk.Entry(fields, textvariable=self.layer_effects_hex_var, width=9)
        hex_entry.grid(row=0, column=1, sticky='w', padx=(4, 0))
        hex_entry.bind('<Return>', self._commit_layer_effects_hex)
        hex_entry.bind('<FocusOut>', self._commit_layer_effects_hex)
        self.layer_effects_alpha_var = tk.StringVar(value='255')
        ttk.Label(fields, text='Alpha').grid(row=0, column=2, sticky='w', padx=(8, 0))
        alpha_entry = ttk.Entry(fields, textvariable=self.layer_effects_alpha_var, width=4)
        alpha_entry.grid(row=0, column=3, sticky='w', padx=(4, 0))
        alpha_entry.bind('<Return>', self._commit_layer_effects_hex)
        alpha_entry.bind('<FocusOut>', self._commit_layer_effects_hex)

    def _redraw_layer_effects_color_picker(self, hue: float, saturation: float, brightness: float):
        self._layer_effects_picker_hue = hue
        square = forza_colors.sb_square_array(hue, self._LE_SB_SIZE)
        self._layer_effects_sb_photo = ImageTk.PhotoImage(Image.fromarray(square, 'RGB'))
        self.layer_effects_sb_canvas.delete('all')
        self.layer_effects_sb_canvas.create_image(0, 0, anchor='nw', image=self._layer_effects_sb_photo)
        cx = saturation * self._LE_SB_SIZE
        cy = (1.0 - brightness) * self._LE_SB_SIZE
        radius = 4
        self.layer_effects_sb_canvas.create_oval(
            cx - radius, cy - radius, cx + radius, cy + radius, outline='#ffffff', width=2)
        self.layer_effects_sb_canvas.create_oval(
            cx - radius, cy - radius, cx + radius, cy + radius, outline='#000000', width=1)
        self.layer_effects_hue_canvas.delete('marker')
        hy = hue * self._LE_SB_SIZE
        self.layer_effects_hue_canvas.create_line(
            0, hy, self._LE_HUE_WIDTH, hy, fill='#ffffff', width=3, tags='marker')
        self.layer_effects_hue_canvas.create_line(
            0, hy, self._LE_HUE_WIDTH, hy, fill='#000000', width=1, tags='marker')

    def _on_layer_effects_sb_pick(self, event):
        layer = self._selected_layer_effects_layer()
        if layer is None:
            return
        x = max(0, min(self._LE_SB_SIZE, event.x))
        y = max(0, min(self._LE_SB_SIZE, event.y))
        saturation = x / self._LE_SB_SIZE
        brightness = 1.0 - y / self._LE_SB_SIZE
        rgb = forza_colors.forza_hsb_to_rgb(self._layer_effects_picker_hue, saturation, brightness)
        self._set_layer_effects_color((rgb.r, rgb.g, rgb.b, layer.color[3]))

    def _on_layer_effects_hue_pick(self, event):
        layer = self._selected_layer_effects_layer()
        if layer is None:
            return
        y = max(0, min(self._LE_SB_SIZE, event.y))
        hue = y / self._LE_SB_SIZE
        self._layer_effects_picker_hue = hue
        _hue, saturation, brightness = forza_colors.rgb_to_forza_hsb(*layer.color[:3])
        rgb = forza_colors.forza_hsb_to_rgb(hue, saturation, brightness)
        self._set_layer_effects_color((rgb.r, rgb.g, rgb.b, layer.color[3]))

    def _commit_layer_effects_hex(self, _e=None):
        layer = self._selected_layer_effects_layer()
        if layer is None:
            return
        rgb = forza_colors.hex_to_rgb(self.layer_effects_hex_var.get())
        if rgb is None:
            return
        try:
            alpha = max(0, min(255, int(self.layer_effects_alpha_var.get())))
        except (TypeError, ValueError):
            alpha = 255
        self._set_layer_effects_color((rgb.r, rgb.g, rgb.b, alpha))

    def _set_layer_effects_color(self, rgba: tuple):
        layer = self._selected_layer_effects_layer()
        if layer is None:
            return
        layer.color = tuple(rgba)
        self._refresh_layer_effects_properties()
        self._layer_effects_refresh_cosmetic_tags()
        self._refresh_layer_effects_preview()

    # -- presets --------------------------------------------------------------

    def _apply_layer_effects_preset(self):
        factory = layer_presets.PRESET_REGISTRY.get(self.layer_effects_preset_var.get())
        if factory is None:
            return
        self._layer_effects_stack = factory()
        self._layer_effects_selected_layer_id = (
            self._layer_effects_stack.layers[0].id if self._layer_effects_stack.layers else None)
        self._rebuild_layer_effects_rows()
        self._refresh_layer_effects_properties()
        self._layer_effects_regenerate()

    def _save_layer_effects_preset(self):
        name = simpledialog.askstring('Save preset', 'Preset name:', parent=self.root)
        if not name:
            return
        self._layer_effects_stack.name = name
        layer_effect_presets_store.save_preset(self._layer_effects_stack.to_dict())
        self.layer_effects_saved_combo.configure(values=layer_effect_presets_store.list_presets())
        self.layer_effects_saved_preset_var.set(name)

    def _load_layer_effects_saved_preset(self):
        name = self.layer_effects_saved_preset_var.get()
        data = layer_effect_presets_store.load_preset(name)
        if not data:
            messagebox.showinfo('Not found', f'No saved preset named {name!r}.')
            return
        self._layer_effects_stack = LayerStack.from_dict(data)
        self._layer_effects_selected_layer_id = (
            self._layer_effects_stack.layers[0].id if self._layer_effects_stack.layers else None)
        self._rebuild_layer_effects_rows()
        self._refresh_layer_effects_properties()
        self._layer_effects_regenerate()

    def _delete_layer_effects_saved_preset(self):
        name = self.layer_effects_saved_preset_var.get()
        if name and layer_effect_presets_store.delete_preset(name):
            self.layer_effects_saved_combo.configure(values=layer_effect_presets_store.list_presets())
            self.layer_effects_saved_preset_var.set('')
