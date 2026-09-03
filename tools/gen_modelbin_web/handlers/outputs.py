"""Output tab: browse previously-generated fontpacks and their glyphs, or
preview any .json/.modelbin file directly. Mirrors
tools/gen_modelbin_gui/tabs/outputs.py's manifest-scanning and preview
logic (shared with Generator's/Composer's own preview panels) against the
real backend.
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
import gui_settings  # noqa: E402
import gui_theme  # noqa: E402
from forza_writer.charset import CATEGORY_ORDER  # noqa: E402

PREVIEW_SIZE = (280, 280)


def _image_to_data_uri(image) -> str:
    buf = io.BytesIO()
    image.save(buf, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')


def _preview_stats_text(path: Path) -> dict:
    """Mirrors tabs/composer.py's _preview_stats_text: (text, style)."""
    try:
        if path.suffix.lower() == '.json':
            data = json.loads(path.read_text(encoding='utf-8'))
            shapes = data.get('shapes', [])
            masks = sum(1 for s in shapes if s.get('mask'))
            return {'text': f'{path.name}\n{len(shapes)} shape(s), {masks} mask cutout(s).', 'style': 'hint'}
        if path.suffix.lower() == '.modelbin':
            from gen_modelbin import read_mesh_triangles, validate_modelbin
            vertices, triangles = read_mesh_triangles(path)
            ok, message = validate_modelbin(path)
            status = 'Structurally valid' if ok else 'INVALID'
            text = (f'{path.name}\n{len(vertices)} vertices, {len(triangles)} triangles.\n'
                    f'{status}: {message}\n'
                    'Structural validity only. This does not confirm FH6 itself will render it '
                    '(needs a live catalog-hijack test).')
            return {'text': text, 'style': 'success' if ok else 'danger'}
        return {'text': f'{path.name}\nUnsupported file type: {path.suffix}', 'style': 'hint'}
    except Exception as exc:
        return {'text': f"{path.name}\nCouldn't read stats: {exc}", 'style': 'danger'}


def register(api, window) -> None:
    def browse_root(payload: dict) -> dict:
        chosen = window.create_file_dialog(
            webview.FileDialog.FOLDER, directory=payload.get('initial', ''))
        if not chosen:
            return {'cancelled': True}
        return {'path': chosen[0]}

    def list_packs(payload: dict) -> dict:
        root_dir = Path(payload['root'])
        if not root_dir.exists():
            return {'packs': []}
        packs = []
        for manifest_path in sorted(root_dir.glob('*/*/manifest.json')):
            try:
                manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
            pack_dir = manifest_path.parent
            total_glyphs = sum(len(v) for v in manifest.get('categories', {}).values())
            profile_id = manifest.get('generation_profile', {}).get('id', manifest.get('output', '?'))
            packs.append({
                'path': str(pack_dir),
                'label': f"{manifest.get('prefix', pack_dir.name)} [{profile_id}] ({total_glyphs} glyphs)",
            })
        return {'packs': packs}

    def get_pack_glyphs(payload: dict) -> dict:
        pack_dir = Path(payload['pack_dir'])
        manifest_path = pack_dir / 'manifest.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        entries = []
        for category in CATEGORY_ORDER:
            for entry in manifest.get('categories', {}).get(category, []):
                artifact = entry.get('artifacts', {}).get('json') or entry.get('artifacts', {}).get('modelbin')
                label = f"{category}  {entry['char']!r}"
                if artifact and artifact.get('strategy'):
                    label += f"  ({artifact['strategy']})"
                quality = artifact.get('quality') if artifact else None
                if quality:
                    verdict = 'PASS' if quality['verdict'] == 'pass' else 'REVIEW'
                    label += f"  [{verdict} {quality['iou']:.2f}]"
                file_rel = artifact.get('file') if artifact else None
                entries.append({
                    'label': label,
                    'path': str(pack_dir / file_rel) if file_rel else None,
                })
        return {'entries': entries}

    def browse_file(_payload: dict) -> dict:
        chosen = window.create_file_dialog(
            webview.FileDialog.OPEN, file_types=('Generated glyph (*.json;*.modelbin)',))
        if not chosen:
            return {'cancelled': True}
        return {'path': chosen[0]}

    def preview_file(payload: dict) -> dict:
        path = Path(payload['path'])
        if not path.exists():
            raise ValueError(f'File not found: {path}')
        p = gui_theme.palette()
        vinyls_dir = file_preview.kfps_vinyls_dir(gui_settings.load_settings().get('kfps_executable', ''))
        image = file_preview.render_file_preview(path, PREVIEW_SIZE, bg=p['canvas_bg'], fg=p['fg'],
                                                   vinyls_dir=vinyls_dir)
        stats = _preview_stats_text(path)
        return {'preview_image': _image_to_data_uri(image), **stats}

    api.register('outputs.browse_root', browse_root)
    api.register('outputs.list_packs', list_packs)
    api.register('outputs.get_pack_glyphs', get_pack_glyphs)
    api.register('outputs.browse_file', browse_file)
    api.register('outputs.preview_file', preview_file)
