"""Layer Effects tab: build a Layered Glyph Effect (inset/outset/translate/
scale/rotate/boolean layers derived from one source glyph, each
independently colored and ordered) and preview it against sample text,
against the real forza_writer.layered_effects engine.

The entire LayerStack lives as a plain JS object in the frontend (add /
duplicate / delete / reorder / edit all happen client-side) since
EffectLayer/LayerStack round-trip to JSON losslessly via to_dict()/
from_dict(). The backend only ever sees a stack when it actually has to
resolve geometry or render a preview -- there is no server-side session
object holding it between requests.

Three update tiers:
  - regenerate(): full compose_layered_text() re-run. Needed whenever a
    layer's geometry-affecting fields change (operation/source/amount/
    offset/scale/rotation/boolean_operand), a layer is added/removed/
    reordered, the font or sample text changes, or a preset is applied.
  - recolor(): re-tints the last regenerate()'s cached shape list via
    layered_effects.recolor_shape() with no geometry re-run. Needed for
    color/opacity/name edits so dragging the opacity slider stays smooth
    instead of re-running primitive-fit on every tick.
  - render_preview(): re-renders the cached shapes with a different
    enabled-layer filter or "compare to source" mode -- no computation
    beyond that filter.
"""
from __future__ import annotations

import base64
import io
import sys
from pathlib import Path

import webview

_TOOLS_DIR = Path(__file__).resolve().parent.parent.parent
_REPO_ROOT = _TOOLS_DIR.parent
sys.path.insert(0, str(_TOOLS_DIR))
sys.path.insert(0, str(_REPO_ROOT))

import file_preview  # noqa: E402
import gui_settings  # noqa: E402
import theme_palettes  # noqa: E402
import layer_effect_presets_store  # noqa: E402
from forza_writer import layer_presets  # noqa: E402
from forza_writer import layered_effects  # noqa: E402
from forza_writer.layered_effects import LayerStack  # noqa: E402
from forza_writer.layered_effects_text import compose_layered_text  # noqa: E402

from ..state import LAYER_EFFECTS_PREVIEW_SIZE  # noqa: E402
from forza_writer.primitive_fit import fit_glyph  # noqa: E402
from forza_writer.text_compose import compose_shape_map  # noqa: E402


def _image_to_data_uri(image) -> str:
    buf = io.BytesIO()
    image.save(buf, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')


def _layer_statuses(groups_by_char) -> dict:
    statuses = {}
    for groups in groups_by_char.values():
        for group in groups:
            if group.status != 'ok':
                statuses[group.layer_id] = [group.status, group.warning]
    return statuses


def register(api, window) -> None:
    cache: dict = {'shapes': [], 'compare_shapes': []}

    def browse_font(_payload: dict) -> dict:
        chosen = window.create_file_dialog(
            webview.FileDialog.OPEN,
            file_types=('Fonts (*.ttf;*.otf;*.ttc)', 'All files (*.*)'))
        if not chosen:
            return {'cancelled': True}
        return {'path': chosen[0]}

    def get_presets(_payload: dict) -> dict:
        return {
            'built_in': sorted(layer_presets.PRESET_REGISTRY),
            'saved': layer_effect_presets_store.list_presets(),
        }

    def apply_preset(payload: dict) -> dict:
        factory = layer_presets.PRESET_REGISTRY.get(payload['name'])
        if factory is None:
            raise ValueError(f"No such preset: {payload['name']!r}")
        return {'stack': factory().to_dict()}

    def load_saved_preset(payload: dict) -> dict:
        data = layer_effect_presets_store.load_preset(payload['name'])
        if not data:
            return {'found': False}
        return {'found': True, 'stack': data}

    def save_preset(payload: dict) -> dict:
        layer_effect_presets_store.save_preset(payload['stack'])
        return {'saved': layer_effect_presets_store.list_presets()}

    def delete_preset(payload: dict) -> dict:
        deleted = layer_effect_presets_store.delete_preset(payload['name'])
        return {'deleted': deleted, 'saved': layer_effect_presets_store.list_presets()}

    def _render(shapes) -> str:
        p = theme_palettes.palette()
        vinyls_dir = file_preview.kfps_vinyls_dir(gui_settings.load_settings().get('kfps_executable', ''))
        image = file_preview.render_composed_preview(
            shapes, LAYER_EFFECTS_PREVIEW_SIZE, bg=p['canvas_bg'], fg=p['fg'], vinyls_dir=vinyls_dir)
        return _image_to_data_uri(image)

    def regenerate(payload: dict) -> dict:
        font_path = Path(payload['font_path'].strip())
        if not font_path.exists():
            raise ValueError(f'Font not found: {font_path}')
        sample = payload.get('sample') or 'A'
        stack = LayerStack.from_dict(payload['stack'])

        shapes, warnings, groups_by_char = compose_layered_text(sample, font_path, stack)
        compare_map = {}
        for char in dict.fromkeys(c for c in sample if not c.isspace()):
            try:
                compare_map[char] = fit_glyph(char, font_path)
            except Exception:
                compare_map[char] = []
        compare_shapes, _warnings = compose_shape_map(sample, font_path, compare_map)

        cache['shapes'] = shapes
        cache['compare_shapes'] = compare_shapes

        enabled_ids = {l.id for l in stack.layers if l.enabled}
        preview_shapes = [s for s in shapes if s.get('layer', {}).get('id') in enabled_ids]
        return {
            'shape_count': len(shapes),
            'warnings': warnings,
            'layer_statuses': _layer_statuses(groups_by_char),
            'preview_image': _render(preview_shapes),
            'vinyl_count': len(preview_shapes),
        }

    def recolor(payload: dict) -> dict:
        layers_by_id = {l['id']: l for l in payload['stack']['layers']}
        updated = []
        for shape in cache['shapes']:
            tag = shape.get('layer')
            if tag and tag['id'] in layers_by_id:
                meta = layers_by_id[tag['id']]
                shape = layered_effects.recolor_shape(shape, tuple(meta['color']), meta['opacity'])
                shape['layer'] = {'id': meta['id'], 'name': meta['name']}
            updated.append(shape)
        cache['shapes'] = updated

        enabled_ids = {l['id'] for l in payload['stack']['layers'] if l['enabled']}
        preview_shapes = [s for s in cache['shapes'] if s.get('layer', {}).get('id') in enabled_ids]
        return {'preview_image': _render(preview_shapes), 'vinyl_count': len(preview_shapes)}

    def render_preview(payload: dict) -> dict:
        if payload.get('compare'):
            shapes = cache['compare_shapes']
        else:
            enabled_ids = set(payload.get('enabled_ids') or [])
            shapes = [s for s in cache['shapes'] if s.get('layer', {}).get('id') in enabled_ids]
        return {'preview_image': _render(shapes), 'vinyl_count': len(shapes)}

    api.register('layer_effects.browse_font', browse_font)
    api.register('layer_effects.get_presets', get_presets)
    api.register('layer_effects.apply_preset', apply_preset)
    api.register('layer_effects.load_saved_preset', load_saved_preset)
    api.register('layer_effects.save_preset', save_preset)
    api.register('layer_effects.delete_preset', delete_preset)
    api.register('layer_effects.regenerate', regenerate)
    api.register('layer_effects.recolor', recolor)
    api.register('layer_effects.render_preview', render_preview)
