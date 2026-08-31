"""Settings tab: output/reference paths, palette/density, compute backend,
generated-data cleanup. Mirrors tools/gen_modelbin_gui/tabs/settings.py's
behavior (same gui_settings keys, same update_settings-not-save_settings
persistence semantics, same double-confirmation before deleting anything)
against the real backend, not a re-implementation.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

import webview

_TOOLS_DIR = Path(__file__).resolve().parent.parent.parent
_REPO_ROOT = _TOOLS_DIR.parent
sys.path.insert(0, str(_TOOLS_DIR))
sys.path.insert(0, str(_REPO_ROOT))

import game_locator  # noqa: E402
import generated_data_cleanup  # noqa: E402
import gui_settings  # noqa: E402
import gui_theme  # noqa: E402
from forza_writer.compute_backend import resolve_backend  # noqa: E402
from forza_writer.image_debug import DEBUG_LABELS as IMAGE_DEBUG_LABELS  # noqa: E402

from . import batch_runner  # noqa: E402
from ..events import push_event  # noqa: E402

_PATH_FIELDS = (
    ('reference_modelbin', 'Reference Modelbin'),
    ('kfps_executable', 'KFPS Executable'),
    ('output_dir', 'Fontpacks Output Directory'),
    ('modelbin_output_dir', 'Modelbin Output Directory'),
    ('direct_output_dir', 'Direct Output Directory'),
    ('image_output_dir', 'Image-to-Text Output'),
)


def _path_status(path_str: str) -> dict:
    path = Path(path_str)
    exists = path.exists()
    return {'path': path_str, 'exists': exists,
            'status': '✓ exists' if exists else 'will be created on first use'}


def register(api, window, run_state: dict | None = None) -> None:
    generation = {'n': 0}

    def get_appearance(_payload: dict) -> dict:
        settings = gui_settings.load_settings()
        return {
            'palettes': [
                {'id': slug, 'label': gui_theme.DISPLAY_NAMES[slug],
                 'description': gui_theme.DESCRIPTIONS.get(slug, '')}
                for slug in gui_theme.PALETTE_ORDER
            ],
            'densities': [
                {'id': 'compact', 'label': 'Compact'},
                {'id': 'balanced', 'label': 'Balanced'},
                {'id': 'spacious', 'label': 'Spacious'},
            ],
            'current': {'palette': settings['palette'], 'density': settings['density']},
        }

    def set_density(payload: dict) -> dict:
        # Palette is locked to Eurocorp in the web app for now (see
        # frontend/js/shell.js) and deliberately not settable from here --
        # this never touches the shared 'palette' key the Tkinter app also
        # reads, so a change made in the web app can't surprise the
        # Tkinter app's own next launch.
        gui_settings.update_settings({'density': payload['density']})
        return {'ok': True}

    def get_paths(_payload: dict) -> dict:
        settings = gui_settings.load_settings()
        return {
            'fields': [
                {'key': key, 'label': label, 'value': settings[key], **_path_status(settings[key])}
                for key, label in _PATH_FIELDS
            ],
            'image_save_source': settings['image_save_source'],
            'image_save_debug': settings['image_save_debug'],
            'image_debug_mode': settings['image_debug_mode'],
            'image_debug_labels': IMAGE_DEBUG_LABELS,
        }

    def browse(payload: dict) -> dict:
        kind = payload.get('kind', 'directory')
        initial = payload.get('initial', '')
        if kind == 'directory':
            chosen = window.create_file_dialog(webview.FileDialog.FOLDER, directory=initial)
        elif kind == 'kfps':
            chosen = window.create_file_dialog(
                webview.FileDialog.OPEN, directory=initial,
                file_types=('KFPS (*.exe)', 'Executable (*.exe)', 'All files (*.*)'))
        else:
            chosen = window.create_file_dialog(webview.FileDialog.OPEN, directory=initial)
        if not chosen:
            return {'cancelled': True}
        return {'path': chosen[0]}

    def detect_reference_modelbin(_payload: dict) -> dict:
        zip_path = game_locator.find_fh6_vinyls_zip()
        if zip_path is None:
            return {'found': False,
                    'message': 'No Forza Horizon 6 install found (checked Xbox app, Microsoft Store, and Steam).'}
        dest = _REPO_ROOT / 'user-assets' / game_locator.REFERENCE_MODELBIN_NAME
        try:
            game_locator.extract_reference_modelbin(dest, zip_path)
        except FileNotFoundError as exc:
            return {'found': False, 'message': str(exc)}
        return {'found': True, 'path': str(dest), 'message': f'Extracted from {zip_path}'}

    def detect_kfps_executable(_payload: dict) -> dict:
        path = game_locator.find_kfps_executable()
        if path is None:
            return {'found': False, 'message': 'No KFPS install found in common locations.'}
        return {'found': True, 'path': str(path)}

    def save_paths(payload: dict) -> dict:
        gui_settings.update_settings({
            'reference_modelbin': payload['reference_modelbin'],
            'kfps_executable': payload['kfps_executable'],
            'output_dir': payload['output_dir'],
            'modelbin_output_dir': payload['modelbin_output_dir'],
            'direct_output_dir': payload['direct_output_dir'],
            'image_output_dir': payload['image_output_dir'],
            'image_save_source': bool(payload['image_save_source']),
            'image_save_debug': bool(payload['image_save_debug']),
            'image_debug_mode': payload['image_debug_mode'],
        })
        return {'ok': True}

    def get_compute_backend(payload: dict) -> dict:
        requested = payload.get('requested', 'auto')
        backend = resolve_backend(requested)
        if requested == 'cpu':
            text = 'Selected: CPU (GPU acceleration disabled).'
        elif backend.resolved in ('cuda', 'directml'):
            label = 'NVIDIA CUDA' if backend.resolved == 'cuda' else 'AMD DirectML (Experimental)'
            text = f'Selected: {label} - {backend.device} - {backend.detail}'
        elif requested in ('cuda', 'directml'):
            label = 'NVIDIA CUDA' if requested == 'cuda' else 'AMD DirectML'
            text = f'{label} selected but unavailable; generation will stop. {backend.detail}'
        else:
            text = f'Auto currently resolves to CPU. {backend.detail}'
        return {'text': text}

    def save_compute_backend(payload: dict) -> dict:
        gui_settings.update_settings({'compute_backend': payload['requested']})
        return {'ok': True}

    def refresh_cleanup_sizes(_payload: dict) -> dict:
        generation['n'] += 1
        gen = generation['n']
        project_root = _REPO_ROOT

        def worker():
            sizes = {}
            for key in generated_data_cleanup.TARGET_LABELS:
                targets = generated_data_cleanup.cleanup_targets(project_root, selected=[key])
                summary = generated_data_cleanup.summarize(targets)
                sizes[key] = {'files': summary.files, 'bytes': summary.bytes}
            push_event(window, 'settings_cleanup_sizes_ready', gen, {'sizes': sizes})

        threading.Thread(target=worker, daemon=True).start()
        return {
            'targets': [
                {'key': key, 'label': label, 'description': generated_data_cleanup.TARGET_DESCRIPTIONS[key]}
                for key, label in generated_data_cleanup.TARGET_LABELS.items()
            ],
            'generation': gen,
        }

    def is_generation_running(_payload: dict) -> dict:
        return {'running': run_state is not None and batch_runner.is_running(run_state)}

    def clean_generated_data(payload: dict) -> dict:
        # Confirmation happens on the JS side (two sequential native
        # confirm() prompts, mirroring the Tkinter tab's own double
        # messagebox.askyesno) -- by the time this handler runs, the user
        # has already confirmed. This function performs the deletion, it
        # does not ask permission for it.
        if run_state is not None and batch_runner.is_running(run_state):
            raise ValueError('Wait for the current generation job to finish before cleaning data.')
        selected = tuple(payload.get('selected', ()))
        if not selected:
            raise ValueError('Nothing selected.')
        removed = generated_data_cleanup.clear_generated_data(_REPO_ROOT, selected=selected)
        return {'files': removed.files, 'bytes': removed.bytes}

    api.register('settings.get_appearance', get_appearance)
    api.register('settings.set_density', set_density)
    api.register('settings.get_paths', get_paths)
    api.register('settings.browse', browse)
    api.register('settings.detect_reference_modelbin', detect_reference_modelbin)
    api.register('settings.detect_kfps_executable', detect_kfps_executable)
    api.register('settings.save_paths', save_paths)
    api.register('settings.get_compute_backend', get_compute_backend)
    api.register('settings.save_compute_backend', save_compute_backend)
    api.register('settings.refresh_cleanup_sizes', refresh_cleanup_sizes)
    api.register('settings.is_generation_running', is_generation_running)
    api.register('settings.clean_generated_data', clean_generated_data)
