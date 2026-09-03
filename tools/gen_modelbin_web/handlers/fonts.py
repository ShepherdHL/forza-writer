"""Shared installed-font listing, used by any tab that lets the user pick a
font (Glyph Inspector, Glyph Template, and likely more later). One
registration, not one copy per tab -- see frontend/js/font-search.js for
the matching shared UI component.
"""
from __future__ import annotations

import base64
import io
import sys
import threading
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent.parent
_REPO_ROOT = _TOOLS_DIR.parent
sys.path.insert(0, str(_TOOLS_DIR))
sys.path.insert(0, str(_REPO_ROOT))

import font_preview  # noqa: E402
import gui_theme  # noqa: E402
from forza_writer.charset import charset_from_font  # noqa: E402
from forza_writer.script_detect import detect_font_scripts  # noqa: E402
from gen_modelbin_gui.state import GRID_TILE_SIZE, enumerate_installed_fonts  # noqa: E402

from ..events import push_event  # noqa: E402


def _image_to_data_uri(image) -> str:
    buf = io.BytesIO()
    image.save(buf, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')


def register(api, window) -> None:
    # Per-process cache of the (comparatively slow -- opens every installed
    # font file) script/glyph-count classification pass. Kicked off lazily
    # on first request rather than eagerly at startup, since not every
    # session touches the script filter or "sort by glyph count" -- see
    # classify() below.
    classify_cache: dict[str, dict] = {}
    classify_state = {'status': 'idle'}  # idle | running | done

    def list_installed(_payload: dict) -> dict:
        # enumerate_installed_fonts() reads both the machine-wide registry
        # key (C:\Windows\Fonts) and the per-user key (%LOCALAPPDATA%\
        # Microsoft\Windows\Fonts). A raw file dialog defaulted to just
        # the first of those misses every font installed for the current
        # user only, which is most custom fonts on a real machine.
        return {'fonts': [{'name': name, 'path': str(path)}
                           for name, path in enumerate_installed_fonts().items()]}

    def render_grid_tiles(payload: dict) -> dict:
        # Rasterizes each font's own name set in its own typeface, same as
        # Tkinter's Grid font-browser view (tabs/generator.py's
        # _populate_font_grid -> font_preview.render_font_name). Opens the
        # font file directly via PIL rather than relying on the browser's
        # OS-level font-family matching, so a registry display name that
        # doesn't resolve as a CSS font-family (not uncommon for style-
        # linked faces like "Arial Bold") still renders correctly.
        # font_preview.render_font_name caches by (path, name, size, bg,
        # fg), so repeat requests for the same font/theme are free.
        p = gui_theme.palette()
        tiles = [
            {'name': item['name'],
             'image': _image_to_data_uri(font_preview.render_font_name(
                 Path(item['path']), item['name'], GRID_TILE_SIZE,
                 bg=p['entry_bg'], fg=p['fg']))}
            for item in payload['fonts']
        ]
        return {'tiles': tiles}

    def classify(_payload: dict) -> dict:
        # One pass over every installed font, run once per process and
        # cached: which scripts it appears to support (script_detect.py's
        # cmap-coverage heuristic, same one Tkinter's script tabs use) plus
        # its total supported-character count (charset_from_font, the same
        # count the "N unique characters" warning already shows for a
        # single font -- reused here so a "sort by glyph count" number
        # matches what the user sees after actually picking that font).
        # ~3-5ms/font each; for ~500 installed fonts that's a couple of
        # seconds the first time either the script filter or the glyph-
        # count sort is used, never again after (both the frontend promise
        # and this cache persist for the rest of the session).
        if classify_state['status'] == 'done':
            return {'status': 'done', 'fonts': classify_cache}
        if classify_state['status'] == 'running':
            return {'status': 'running'}
        classify_state['status'] = 'running'

        def worker():
            for name, path in enumerate_installed_fonts().items():
                scripts = sorted(detect_font_scripts(path, name))
                try:
                    categorized, _skipped = charset_from_font(path)
                    glyph_count = sum(len(chars) for chars in categorized.values())
                except Exception:
                    glyph_count = 0
                classify_cache[name] = {'scripts': scripts, 'glyph_count': glyph_count}
            classify_state['status'] = 'done'
            push_event(window, 'fonts_classified', 0, {'fonts': classify_cache})

        threading.Thread(target=worker, daemon=True).start()
        return {'status': 'started'}

    api.register('fonts.list_installed', list_installed)
    api.register('fonts.render_grid_tiles', render_grid_tiles)
    api.register('fonts.classify', classify)
