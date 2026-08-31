"""ASCII Art tab: place pasted ASCII art on a fixed grid using one of FH6's
11 native in-game vinyl fonts. Mirrors tools/gen_modelbin_gui/tabs/
ascii_art.py's pipeline (normalize_block -> scan_unsupported ->
layout_ascii_grid) against the real backend.
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
import gui_theme  # noqa: E402
from forza_writer.ascii_grid import (  # noqa: E402
    layout_ascii_grid, normalize_block, scan_unsupported, supported_chars)
from forza_writer.export import save as save_composed_json, to_json as composed_to_json  # noqa: E402

PREVIEW_SIZE = (640, 420)


def _image_to_data_uri(image) -> str:
    buf = io.BytesIO()
    image.save(buf, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')


def register(api, window) -> None:
    def preview(payload: dict) -> dict:
        text = payload['text']
        rows = normalize_block(text)
        if not rows or not any(row.strip() for row in rows):
            raise ValueError('Paste some ASCII art first.')

        font = max(1, min(11, int(payload['font'])))
        cell_width = float(payload['cell_width'])
        cell_height = float(payload['cell_height'])
        color = payload['color']
        placeholder = bool(payload.get('placeholder', False))
        remap = {k: (v if v else None) for k, v in payload.get('remap', {}).items()}

        supported = supported_chars(font)
        unsupported = scan_unsupported(rows, font)

        shapes = layout_ascii_grid(
            rows, font=font, cell_width=cell_width, cell_height=cell_height,
            remap=remap, color=color, placeholder_unsupported=placeholder)
        composed_payload = composed_to_json(shapes)

        cols = max((len(r) for r in rows), default=0)
        total_cells = sum(len(r) for r in rows)
        blank_cells = total_cells - len(shapes)

        p = gui_theme.palette()
        image = file_preview.render_ascii_grid_preview(
            rows, supported, remap, size=PREVIEW_SIZE, bg=p['canvas_bg'], fg=p['fg'])

        unsupported_sorted = sorted(unsupported, key=lambda c: unsupported[c][0])
        return {
            'shapes': shapes,
            'payload': composed_payload,
            'rows': len(rows),
            'cols': cols,
            'placed_count': len(shapes),
            'blank_cells': blank_cells,
            'unsupported': [{'char': c, 'count': len(unsupported[c])} for c in unsupported_sorted],
            'preview_image': _image_to_data_uri(image),
        }

    def save_json(payload: dict) -> dict:
        chosen = window.create_file_dialog(
            webview.FileDialog.SAVE, directory=payload.get('initial_dir', ''),
            save_filename='ascii_art.json', file_types=('JSON (*.json)',))
        if not chosen:
            return {'cancelled': True}
        path = chosen if isinstance(chosen, str) else chosen[0]
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        save_composed_json(payload['payload'], path)
        return {'path': path}

    api.register('ascii_art.preview', preview)
    api.register('ascii_art.save_json', save_json)
