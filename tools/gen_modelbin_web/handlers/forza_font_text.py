"""Forza Font Text tab: lay out text with one of FH6's 11 native in-game
vinyl fonts (forza_writer.layout.layout_forza_text), including
"unsupported character" detection.
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
import theme_palettes  # noqa: E402
from gen_forza_fonts_reference import FONT_IDENTIFICATION  # noqa: E402
from forza_writer.export import save as save_composed_json, to_json as composed_to_json  # noqa: E402
from forza_writer.fabric_project import save as save_project, to_fabric_project  # noqa: E402
from forza_writer.layout import layout_forza_text  # noqa: E402
from forza_writer.shapes import char_to_resource  # noqa: E402

PREVIEW_SIZE = (280, 280)


def _font_choice_label(font: int) -> str:
    ident = FONT_IDENTIFICATION.get(font, {'confirmed': False, 'note': 'Unidentified.'})
    mark = 'Confirmed' if ident['confirmed'] else 'Lead'
    note = ident['note']
    if note.strip().lower() == 'unidentified.':
        return f'Forza Font {font}'
    return f'Forza Font {font} ({mark}: {note})'


def _placed_chars(text: str, font: int) -> list[str]:
    lines = text.replace('\r\n', '\n').split('\n')
    chars = []
    for line in lines:
        for char in line:
            if char == ' ':
                continue
            if char_to_resource(char, font):
                chars.append(char)
    return chars


def _image_to_data_uri(image) -> str:
    buf = io.BytesIO()
    image.save(buf, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')


def register(api, window) -> None:
    def get_fonts(_payload: dict) -> dict:
        return {'fonts': [{'value': f, 'label': _font_choice_label(f)} for f in range(1, 12)]}

    def preview(payload: dict) -> dict:
        text = payload['text']
        font = max(1, min(11, int(payload['font'])))
        height = float(payload['height'])
        color = payload['color']

        shapes = layout_forza_text(text, font=font, target_height=height)
        for shape in shapes:
            shape['color'] = list(color)
        composed_payload = composed_to_json(shapes)

        lines = text.replace('\r\n', '\n').split('\n')
        unsupported = sorted({c for c in text if c not in ('\n', '\r', ' ') and not char_to_resource(c, font)})
        total_chars = sum(1 for c in text if c not in ('\n', '\r', ' '))

        p = theme_palettes.palette()
        image = file_preview.render_forza_text_preview(
            lines, set(unsupported), size=PREVIEW_SIZE, bg=p['canvas_bg'], fg=p['fg'])

        return {
            'shapes': shapes,
            'payload': composed_payload,
            'chars': _placed_chars(text, font),
            'unsupported': unsupported,
            'total_chars': total_chars,
            'placed_count': len(shapes),
            'preview_image': _image_to_data_uri(image),
        }

    def save_json(payload: dict) -> dict:
        chosen = window.create_file_dialog(
            webview.FileDialog.SAVE, directory=payload.get('initial_dir', ''),
            save_filename='forza_font_text.json',
            file_types=('JSON (*.json)',))
        if not chosen:
            return {'cancelled': True}
        path = chosen if isinstance(chosen, str) else chosen[0]
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        save_composed_json(payload['payload'], path)
        return {'path': path}

    def save_fabric_project(payload: dict) -> dict:
        chosen = window.create_file_dialog(
            webview.FileDialog.SAVE, directory=payload.get('initial_dir', ''),
            save_filename='forza_font_text.fabric-project.json',
            file_types=('KFPS Fabric Project (*.json)', 'All files (*.*)'))
        if not chosen:
            return {'cancelled': True}
        path = chosen if isinstance(chosen, str) else chosen[0]
        shapes = payload['shapes']
        chars = payload['chars']
        groups = [(f'{i + 1}: {char}', [i]) for i, char in enumerate(chars)]
        project = to_fabric_project(shapes, name='Forza Font Text', groups=groups)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        save_project(project, path)
        return {'path': path, 'groups': len(groups)}

    api.register('forza_font_text.get_fonts', get_fonts)
    api.register('forza_font_text.preview', preview)
    api.register('forza_font_text.save_json', save_json)
    api.register('forza_font_text.save_project', save_fabric_project)
