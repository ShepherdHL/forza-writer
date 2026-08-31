"""Configurator: per-glyph mask-mode overrides for a font, embedded as a
collapsible sub-section of the Generator tab (matching Tkinter's own
_build_configurator_workspace -- this is not a separate top-level tab).
Mirrors tools/gen_modelbin_gui/tabs/configurator.py.

Reviews the *whole* font's glyph set (every character it has a glyph for),
independent of Generator's own character-selection checkboxes -- an
override still applies at generation time even for a glyph Generator
wouldn't otherwise include, since overrides are read from disk by font
path alone at generation time (see batch_runner.resolve_overrides_for_
generation), not filtered by whatever happened to be checked when they
were set.

One deliberate, non-functionality-losing simplification: Tkinter inserts
tree rows in small batches via root.after to keep the Tk widget tree
responsive while populating a large CJK font's thousands of rows -- a
real Tk-widget-creation cost, not a computation cost. A browser renders a
few thousand DOM rows from one innerHTML assignment fast enough that this
isn't needed here. The *actual* per-glyph computation
(inspect_glyph_geometry) still runs as a real background thread with
progress events, same as Tkinter's own scan_worker -- that cost is real
computation, not a UI artifact, and stays async here too.
"""
from __future__ import annotations

import base64
import io
import json
import sys
import threading
from pathlib import Path

import webview

_TOOLS_DIR = Path(__file__).resolve().parent.parent.parent
_REPO_ROOT = _TOOLS_DIR.parent
sys.path.insert(0, str(_TOOLS_DIR))
sys.path.insert(0, str(_REPO_ROOT))

import file_preview  # noqa: E402
import glyph_overrides as glyph_overrides_store  # noqa: E402
import gui_theme  # noqa: E402
from forza_writer.charset import CATEGORY_ORDER, charset_from_font  # noqa: E402
from forza_writer.compute_backend import resolve_backend  # noqa: E402
from forza_writer.primitive_fit import (  # noqa: E402
    DEFAULT_RESOLUTION, fit_glyph_with_strategy, inspect_glyph_geometry, placements_to_shapes,
    preview_glyph_mask_options)

from ..events import push_event  # noqa: E402

_PREVIEW_SIZE = (160, 160)
_SCAN_PUSH_CHUNK = 100  # glyphs accumulated between scan progress push_events


def _image_to_data_uri(image) -> str:
    buf = io.BytesIO()
    image.save(buf, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')


def _char_list(font_path: Path) -> list[tuple[str, str]]:
    categorized, _skipped = charset_from_font(font_path)
    return [(char, category) for category in CATEGORY_ORDER for char in categorized.get(category, [])]


def register(api, window) -> None:
    scan_state = {'generation': 0}

    def list_glyphs(payload: dict) -> dict:
        font_path = Path(payload['font_path'])
        if not font_path.exists():
            raise ValueError(f'Font not found: {font_path}')
        entries = _char_list(font_path)
        overrides = glyph_overrides_store.load_overrides_for_font(font_path)
        return {'entries': [[char, category] for char, category in entries], 'overrides': overrides}

    def start_scan(payload: dict) -> dict:
        font_path = Path(payload['font_path'])
        if not font_path.exists():
            raise ValueError(f'Font not found: {font_path}')
        segments = max(1, int(payload.get('segments', 8)))
        entries = _char_list(font_path)
        overrides = glyph_overrides_store.load_overrides_for_font(font_path)

        scan_state['generation'] += 1
        generation = scan_state['generation']

        def worker():
            buffer: dict[str, dict] = {}
            for i, (char, _category) in enumerate(entries):
                if generation != scan_state['generation']:
                    return
                entry = overrides.get(char)
                if entry and entry.get('mode') == 'manual':
                    info = {'manual': True}
                else:
                    try:
                        info = inspect_glyph_geometry(char, font_path, segments)
                    except Exception as exc:
                        info = {'error': str(exc)}
                buffer[char] = info
                if len(buffer) >= _SCAN_PUSH_CHUNK or i == len(entries) - 1:
                    if generation != scan_state['generation']:
                        return
                    push_event(window, 'configurator_scan_progress', generation,
                               {'results': buffer, 'done': i + 1, 'total': len(entries)})
                    buffer = {}
            push_event(window, 'configurator_scan_done', generation, {'total': len(entries)})

        threading.Thread(target=worker, daemon=True).start()
        return {'generation': generation, 'total': len(entries)}

    def get_glyph_detail(payload: dict) -> dict:
        font_path = Path(payload['font_path'])
        char = payload['char']
        segments = max(1, int(payload.get('segments', 8)))
        compute_backend = payload.get('compute_backend', 'auto')
        compute_forced = bool(payload.get('compute_forced', False))
        p = gui_theme.palette()

        overrides = glyph_overrides_store.load_overrides_for_font(font_path)
        entry = overrides.get(char, {'mode': 'auto'})
        mode = entry['mode']

        if mode == 'manual':
            try:
                data = json.loads(Path(entry['file']).read_text(encoding='utf-8'))
                shapes = data.get('shapes', [])
            except Exception as exc:
                raise ValueError(f"Couldn't read {entry['file']!r}: {exc}") from exc
            image = file_preview.render_json_preview(shapes, _PREVIEW_SIZE, bg=p['canvas_bg'], fg=p['fg'])
            mask_count = sum(1 for s in shapes if s.get('mask'))
            return {
                'mode': 'manual', 'effective_mode': 'manual', 'shape_count': len(shapes),
                'mask_count': mask_count, 'file_name': Path(entry['file']).name,
                'preview_image': _image_to_data_uri(image), 'can_force_mask': False,
            }

        backend = resolve_backend(compute_backend)
        if compute_backend in ('cuda', 'directml') and not backend.available:
            raise ValueError(backend.detail)
        info = preview_glyph_mask_options(
            char, font_path, segments, curved_force_check=(compute_forced or mode == 'force'),
            compute_backend=backend.resolved, return_placements=True)
        effective_mode = mode
        if mode == 'force' and not info.get('can_force_mask'):
            effective_mode = 'auto'
        placements = None
        strategy = None
        if effective_mode == 'auto' or (effective_mode == 'never' and not info['rectilinear']):
            placements = info.get('_auto_placements')
            strategy = info['auto_strategy']
        elif effective_mode == 'force':
            placements = info.get('_forced_placements')
            strategy = 'stencil' if info['rectilinear'] else 'stencil_search'
        if placements is not None:
            shapes = placements_to_shapes(placements, DEFAULT_RESOLUTION)
        else:
            shapes, strategy = fit_glyph_with_strategy(
                char, font_path, segments, mask_mode=effective_mode, compute_backend=backend.resolved)
        info = {key: value for key, value in info.items() if not key.startswith('_')}
        image = file_preview.render_json_preview(shapes, _PREVIEW_SIZE, bg=p['canvas_bg'], fg=p['fg'])
        mask_count = sum(1 for shape in shapes if shape.get('mask'))
        return {
            'mode': mode, 'effective_mode': effective_mode, 'info': info,
            'shape_count': len(shapes), 'mask_count': mask_count, 'strategy': strategy,
            'backend': backend.resolved, 'can_force_mask': info.get('can_force_mask', False),
            'preview_image': _image_to_data_uri(image),
        }

    def set_override(payload: dict) -> dict:
        font_path = Path(payload['font_path'])
        char = payload['char']
        mode = payload['mode']
        overrides = glyph_overrides_store.load_overrides_for_font(font_path)
        if mode == 'auto':
            overrides.pop(char, None)
        else:
            overrides[char] = {'mode': mode}
        glyph_overrides_store.save_overrides_for_font(font_path, overrides)
        return {'ok': True}

    def assign_file(payload: dict) -> dict:
        font_path = Path(payload['font_path'])
        char = payload['char']
        chosen = window.create_file_dialog(
            webview.FileDialog.OPEN, file_types=('JSON (*.json)', 'All files (*.*)'))
        if not chosen:
            return {'cancelled': True}
        path = chosen[0]
        overrides = glyph_overrides_store.load_overrides_for_font(font_path)
        overrides[char] = {'mode': 'manual', 'file': path}
        glyph_overrides_store.save_overrides_for_font(font_path, overrides)
        return {'path': path}

    def reset_all(payload: dict) -> dict:
        font_path = Path(payload['font_path'])
        glyph_overrides_store.save_overrides_for_font(font_path, {})
        return {'ok': True}

    def force_all_rectilinear(payload: dict) -> dict:
        # Eligibility (rectilinear + can_force_mask) is computed client-side
        # from the already-completed scan results and passed in directly --
        # cheap, since the bulk scan already determined it for every glyph;
        # no need to re-derive or re-check it server-side. Manual glyphs are
        # still defensively skipped here so a stale client-side list can't
        # silently discard a file assignment.
        font_path = Path(payload['font_path'])
        chars = payload.get('chars') or []
        overrides = glyph_overrides_store.load_overrides_for_font(font_path)
        changed = 0
        for char in chars:
            if overrides.get(char, {}).get('mode') != 'manual':
                overrides[char] = {'mode': 'force'}
                changed += 1
        glyph_overrides_store.save_overrides_for_font(font_path, overrides)
        return {'changed': changed}

    api.register('configurator.list_glyphs', list_glyphs)
    api.register('configurator.start_scan', start_scan)
    api.register('configurator.get_glyph_detail', get_glyph_detail)
    api.register('configurator.set_override', set_override)
    api.register('configurator.assign_file', assign_file)
    api.register('configurator.reset_all', reset_all)
    api.register('configurator.force_all_rectilinear', force_all_rectilinear)
