"""Composer tab: compose multi-line vinyl text from an already-generated
fontpack's glyphs, with real per-glyph spacing/baseline and per-line color
fills, or a Layered Glyph Effect applied per-character instead of the
fontpack's own flat glyphs. Mirrors tools/gen_modelbin_gui/tabs/composer.py's
compose_text/compose_layered_text pipelines against the real backend.

The Layered Glyph Effect path reuses layer_effects.py's own
apply_preset/get_presets handlers directly (registered under a different
name, but api.call() dispatch is global, not tab-scoped) rather than
duplicating preset lookup here -- Composer only ever needs a plain
LayerStack.to_dict() to hand to compose_layered_text, the same shape that
tab already produces and round-trips.
"""
from __future__ import annotations

import base64
import io
import json
import sys
from pathlib import Path

import webview

_TOOLS_DIR = Path(__file__).resolve().parent.parent.parent
_REPO_ROOT = _TOOLS_DIR.parent
sys.path.insert(0, str(_TOOLS_DIR))
sys.path.insert(0, str(_REPO_ROOT))

import file_preview  # noqa: E402
import gui_theme  # noqa: E402
from forza_writer.export import save as save_composed_json, to_json as composed_to_json  # noqa: E402
from forza_writer.forza_colors import hex_to_rgb  # noqa: E402
from forza_writer import manufacturer_colors  # noqa: E402
from forza_writer.layered_effects import LayerStack  # noqa: E402
from forza_writer.layered_effects_text import compose_layered_text  # noqa: E402
from forza_writer.text_compose import compose_text  # noqa: E402
from forza_writer.text_style import LineFill, TextStyle  # noqa: E402

COMPOSE_PREVIEW_SIZE = (640, 200)
_MFG_RESULT_CAP = 150


def _image_to_data_uri(image) -> str:
    buf = io.BytesIO()
    image.save(buf, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')


def register(api, window) -> None:
    composed_shapes: dict = {'shapes': None}

    def pick_pack_dir(payload: dict) -> dict:
        chosen = window.create_file_dialog(
            webview.FileDialog.FOLDER, directory=payload.get('initial', ''))
        if not chosen:
            return {'cancelled': True}
        return {'path': chosen[0]}

    def compose(payload: dict) -> dict:
        pack_dir = Path(payload['pack_dir'].strip())
        text = payload['text']
        if not (pack_dir / 'manifest.json').exists():
            raise ValueError(f'No manifest.json in: {pack_dir}')
        if not text:
            raise ValueError('Type some text to compose.')

        size_scale = max(0.25, min(4.0, float(payload['size']) / 100.0))
        line_spacing = max(0.5, min(3.0, float(payload['line_spacing']) / 100.0))
        letter_spacing = float(payload['letter_spacing'])

        fills = tuple(
            LineFill(mode=f['mode'], colors=tuple(tuple(c) for c in f['colors']), blend=f['blend'])
            for f in payload['fills']
        )
        style = TextStyle(
            bold=payload['bold'], italic=payload['italic'],
            underline=payload['underline'], strikethrough=payload['strikethrough'],
            fills=fills,
        )
        shapes, warnings = compose_text(
            text, pack_dir, align=payload['align'], letter_spacing=letter_spacing,
            size_scale=size_scale, line_spacing=line_spacing, style=style)

        composed_shapes['shapes'] = shapes
        p = gui_theme.palette()
        image = file_preview.render_composed_preview(shapes, COMPOSE_PREVIEW_SIZE, bg=p['canvas_bg'], fg=p['fg'])
        return {
            'shapes': shapes,
            'preview_image': _image_to_data_uri(image),
            'stats': f'{len(shapes)} shape(s).',
            'warnings': warnings,
        }

    def compose_layered(payload: dict) -> dict:
        pack_dir = Path(payload['pack_dir'].strip())
        text = payload['text']
        manifest_path = pack_dir / 'manifest.json'
        if not manifest_path.exists():
            raise ValueError(f'No manifest.json in: {pack_dir}')
        if not text:
            raise ValueError('Type some text to compose.')

        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        font_path_str = manifest.get('font_file')
        if not font_path_str or not Path(font_path_str).exists():
            raise ValueError(
                "This fontpack has no associated font file on this machine -- a Layered "
                "Glyph Effect needs the original font, not just the generated fontpack.")

        size_scale = max(0.25, min(4.0, float(payload['size']) / 100.0))
        line_spacing = max(0.5, min(3.0, float(payload['line_spacing']) / 100.0))
        letter_spacing = float(payload['letter_spacing'])
        stack = LayerStack.from_dict(payload['stack'])
        # fills=() deliberately skips the per-line color pass: each layer
        # already carries its own color, and letting a line-fill overwrite
        # every shape with one color would erase that distinction -- see
        # Tkinter's _compose_layer_effect_style docstring. One side effect:
        # underline/strikethrough need a single resolved line color to draw
        # their bar shape, so they render nothing while this is enabled,
        # same as there.
        style = TextStyle(
            bold=payload['bold'], italic=payload['italic'],
            underline=payload['underline'], strikethrough=payload['strikethrough'],
            fills=(),
        )
        shapes, warnings, _groups_by_char = compose_layered_text(
            text, font_path_str, stack, align=payload['align'], letter_spacing=letter_spacing,
            size_scale=size_scale, line_spacing=line_spacing, style=style)

        composed_shapes['shapes'] = shapes
        p = gui_theme.palette()
        image = file_preview.render_composed_preview(shapes, COMPOSE_PREVIEW_SIZE, bg=p['canvas_bg'], fg=p['fg'])
        return {
            'shapes': shapes,
            'preview_image': _image_to_data_uri(image),
            'stats': f'{len(shapes)} shape(s).',
            'warnings': warnings,
        }

    def save(payload: dict) -> dict:
        chosen = window.create_file_dialog(
            webview.FileDialog.SAVE, save_filename='composed_text.json',
            file_types=('JSON (*.json)',))
        if not chosen:
            return {'cancelled': True}
        path = chosen if isinstance(chosen, str) else chosen[0]
        save_composed_json(composed_to_json(payload['shapes']), path)
        return {'path': path}

    def mfg_makes(_payload: dict) -> dict:
        return {'makes': list(manufacturer_colors.all_makes()), 'total': len(manufacturer_colors.load_all())}

    def mfg_search(payload: dict) -> dict:
        term = payload.get('term', '')
        make = payload.get('make') or None
        results = manufacturer_colors.search(term, make=make)
        total = len(results)
        rows = results[:_MFG_RESULT_CAP]
        return {
            'total': total,
            'capped': total > _MFG_RESULT_CAP,
            'rows': [
                {'make': c.make, 'name': c.name, 'paint_type': c.paint_type, 'hex1': c.hex1,
                 'hue': c.hue, 'saturation': c.saturation, 'brightness': c.brightness}
                for c in rows
            ],
        }

    def mfg_color_rgba(payload: dict) -> dict:
        rgb = hex_to_rgb(payload['hex1'])
        if rgb is None:
            raise ValueError(f"Not a valid hex color: {payload['hex1']!r}")
        return {'rgba': [rgb.r, rgb.g, rgb.b, 255]}

    api.register('composer.pick_pack_dir', pick_pack_dir)
    api.register('composer.compose', compose)
    api.register('composer.compose_layered', compose_layered)
    api.register('composer.save', save)
    api.register('composer.mfg_makes', mfg_makes)
    api.register('composer.mfg_search', mfg_search)
    api.register('composer.mfg_color_rgba', mfg_color_rgba)
