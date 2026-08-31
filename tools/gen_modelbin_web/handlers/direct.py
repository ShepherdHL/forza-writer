"""Direct Generator tab: generate one complete .json design straight from
text or an image, with no fontpack step. Mirrors tools/gen_modelbin_gui/
tabs/direct.py's generate_direct() pipeline against the real backend.

Unlike Advanced Generator, this tab has no real dependency on Generator's
own charset/prefix/segments state -- everything it needs (compute backend,
output directories, image-debug options) already lives in the shared
gui_settings, and font/image selection are entirely local to this tab.
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
import gui_theme  # noqa: E402
from gen_modelbin_gui.state import direct_output_filename  # noqa: E402
from forza_writer import image_debug  # noqa: E402
from forza_writer.compute_backend import resolve_backend  # noqa: E402
from forza_writer.direct_generate import generate_direct  # noqa: E402
from forza_writer.export import save as save_composed_json, to_json as composed_to_json  # noqa: E402

COMPOSE_PREVIEW_SIZE = (640, 200)
_FONT_FILE_TYPES = ('OpenType fonts (*.ttf;*.otf)',)
_IMAGE_FILE_TYPES = ('Images (*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.tif;*.tiff)',)


def _image_to_data_uri(image) -> str:
    buf = io.BytesIO()
    image.save(buf, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')


def register(api, window) -> None:
    state: dict = {'shapes': None, 'payload': None, 'trace_debug': None,
                   'source_image': None, 'suggested_name': None}

    def browse_font(_payload: dict) -> dict:
        chosen = window.create_file_dialog(webview.FileDialog.OPEN, file_types=_FONT_FILE_TYPES)
        if not chosen:
            return {'cancelled': True}
        return {'path': chosen[0]}

    def browse_image(_payload: dict) -> dict:
        chosen = window.create_file_dialog(webview.FileDialog.OPEN, file_types=_IMAGE_FILE_TYPES)
        if not chosen:
            return {'cancelled': True}
        return {'path': chosen[0]}

    def generate(payload: dict) -> dict:
        method = payload['method']
        text = payload.get('text', '')
        font_path = Path(payload.get('font_path', '').strip())
        image_path = Path(payload.get('image_path', '').strip())
        color = payload['color']

        if method == 'image' and not image_path.is_file():
            raise ValueError(f'Image not found: {image_path}')
        if method != 'image' and not font_path.is_file():
            raise ValueError(f'Font not found: {font_path}')
        if method != 'image' and not text.strip():
            raise ValueError('Type some text to generate.')

        settings = gui_settings.load_settings()
        if method == 'modern':
            resolved_backend = resolve_backend(settings['compute_backend']).resolved
            segments = max(1, int(payload['segments']))
            default_name = direct_output_filename(font_path, method, backend=resolved_backend, segments=segments)
            options = {'curve_segments': segments, 'align': payload['align'],
                       'compute_backend': resolved_backend, 'solid_color': color}
            gen_font_path = font_path
        elif method == 'legacy':
            resolved_backend = 'cpu'
            cell_size = max(1, min(16, int(payload['cell_size'])))
            default_name = direct_output_filename(font_path, method, cell_size=cell_size)
            options = {'cell_size': cell_size, 'solid_color': color}
            gen_font_path = font_path
        else:
            resolved_backend = 'cpu'
            cell_size = max(1, min(16, int(payload['cell_size'])))
            threshold_text = str(payload.get('threshold', 'auto')).strip().lower()
            threshold = None if threshold_text in ('', 'auto') else max(0, min(255, int(threshold_text)))
            default_name = direct_output_filename(image_path, method, cell_size=cell_size)
            options = {'image_path': str(image_path), 'cell_size': cell_size,
                       'polarity': payload['polarity'], 'threshold': threshold, 'solid_color': color}
            gen_font_path = None

        shapes, warnings, metadata = generate_direct(text, gen_font_path, method=method, **options)
        composed_payload = composed_to_json(shapes)
        serializable = {k: v for k, v in metadata.items() if k != 'trace_debug'}
        composed_payload['direct_generation'] = {
            **serializable,
            'font_file': str(font_path) if method != 'image' else None,
            'text': text if method != 'image' else None,
            'compute_backend': resolved_backend,
            **{k: v for k, v in options.items() if k != 'image_path'},
        }

        state['shapes'] = shapes
        state['payload'] = composed_payload
        state['trace_debug'] = metadata.get('trace_debug')
        state['source_image'] = str(image_path) if method == 'image' else None
        state['suggested_name'] = default_name

        p = gui_theme.palette()
        image = file_preview.render_composed_preview(shapes, COMPOSE_PREVIEW_SIZE, bg=p['canvas_bg'], fg=p['fg'])

        if method == 'modern':
            quality = metadata.get('quality_by_glyph', {})
            primitive_count = sum(1 for item in quality.values() if item.get('selected') == 'primitive')
            exact_count = sum(1 for item in quality.values() if item.get('selected') == 'exact')
            skewed_layers = sum(item.get('selected_skewed_layers', 0) for item in quality.values())
            detail = f"{metadata.get('unique_glyphs', 0)} unique glyph(s) fitted"
            if quality:
                detail += f'; {primitive_count} primitive, {exact_count} exact fallback'
                if skewed_layers:
                    detail += f'; {skewed_layers} skewed layer(s)'
        elif method == 'legacy':
            detail = f"cell size {metadata['cell_size']}"
        else:
            detail = f"{metadata['polarity']} foreground at threshold {metadata['threshold']}; cell size {metadata['cell_size']}"

        status = f'{method.capitalize()}: previewed {len(shapes)} shape(s) ({detail}).'
        if warnings:
            status += ' ' + ' '.join(warnings)

        return {
            'preview_image': _image_to_data_uri(image),
            'status': status,
            'warnings': warnings,
            'shape_count': len(shapes),
            'suggested_name': default_name,
        }

    def save(_payload: dict) -> dict:
        if not state['payload'] or not state['shapes']:
            raise ValueError('Nothing to save yet.')
        settings = gui_settings.load_settings()
        start_dir = settings['image_output_dir'] if state['trace_debug'] is not None else settings['direct_output_dir']
        chosen = window.create_file_dialog(
            webview.FileDialog.SAVE, directory=start_dir, save_filename=state['suggested_name'],
            file_types=('JSON (*.json)',))
        if not chosen:
            return {'cancelled': True}
        path = chosen if isinstance(chosen, str) else chosen[0]
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        save_composed_json(state['payload'], path)

        written = []
        accuracy_text = None
        if state['trace_debug'] is not None and (settings['image_save_source'] or settings['image_save_debug']):
            try:
                written = image_debug.write_debug_outputs(
                    path, state['trace_debug'], source_path=state['source_image'],
                    save_source=bool(settings['image_save_source']),
                    save_debug=bool(settings['image_save_debug']), mode=settings['image_debug_mode'])
                if settings['image_save_debug']:
                    scores = image_debug.accuracy(state['trace_debug'])
                    accuracy_text = (f"IoU {scores['iou']:.3f} ({scores['missed_pixels']:,} px missed, "
                                      f"{scores['overshoot_pixels']:,} px overshoot)")
            except Exception as exc:
                return {'path': path, 'shape_count': len(state['shapes']),
                        'debug_error': str(exc)}
        return {
            'path': path,
            'shape_count': len(state['shapes']),
            'written_debug': [str(p) for p in written],
            'accuracy_text': accuracy_text,
        }

    api.register('direct.browse_font', browse_font)
    api.register('direct.browse_image', browse_image)
    api.register('direct.generate', generate)
    api.register('direct.save', save)
