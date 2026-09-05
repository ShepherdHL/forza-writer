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
import theme_palettes  # noqa: E402
from forza_writer.charset import charset_from_font  # noqa: E402
from forza_writer.script_detect import detect_font_scripts  # noqa: E402

from ..events import push_event  # noqa: E402
from ..state import GRID_TILE_SIZE, enumerate_installed_fonts  # noqa: E402


def _image_to_data_uri(image) -> str:
    buf = io.BytesIO()
    image.save(buf, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')


def register(api, window) -> None:
    # Per-process cache of the (comparatively slow -- opens every installed
    # font file) script/glyph-count classification pass, PLUS a warm-up of
    # font_preview's own render cache for every font's grid tile. Kicked
    # off immediately below (see the register()-body call to
    # start_classification() at the bottom of this function) rather than
    # waiting for the frontend's first fonts.classify/render_grid_tiles
    # call: measured at ~3.6s (classification) + ~1.1s (tile rendering) for
    # ~500 installed fonts, comfortably done in the background before a
    # user typically reaches the Generator tab and opens the Font grid, so
    # "every font is ready" ends up being the default experience rather
    # than something a click has to wait on. rescan() below is the one
    # remaining deliberately-heavier action, for the one case startup
    # loading can't cover: a font installed mid-session.
    classify_cache: dict[str, dict] = {}
    classify_state = {'status': 'idle'}  # idle | running | done

    def start_classification() -> None:
        if classify_state['status'] != 'idle':
            return
        classify_state['status'] = 'running'
        p = theme_palettes.palette()

        def worker():
            for name, path in enumerate_installed_fonts().items():
                scripts = sorted(detect_font_scripts(path, name))
                try:
                    categorized, _skipped = charset_from_font(path)
                    glyph_count = sum(len(chars) for chars in categorized.values())
                except Exception:
                    glyph_count = 0
                classify_cache[name] = {'scripts': scripts, 'glyph_count': glyph_count}
                try:
                    font_preview.render_font_name(path, name, GRID_TILE_SIZE, bg=p['entry_bg'], fg=p['fg'])
                except Exception:
                    pass  # render_grid_tiles falls back to rendering on demand either way
            classify_state['status'] = 'done'
            push_event(window, 'fonts_classified', 0, {'fonts': classify_cache})

        threading.Thread(target=worker, daemon=True).start()

    def list_installed(_payload: dict) -> dict:
        # enumerate_installed_fonts() reads both the machine-wide registry
        # key (C:\Windows\Fonts) and the per-user key (%LOCALAPPDATA%\
        # Microsoft\Windows\Fonts). A raw file dialog defaulted to just
        # the first of those misses every font installed for the current
        # user only, which is most custom fonts on a real machine.
        return {'fonts': [{'name': name, 'path': str(path)}
                           for name, path in enumerate_installed_fonts().items()]}

    def render_grid_tiles(payload: dict) -> dict:
        # Rasterizes each font's own name set in its own typeface
        # (font_preview.render_font_name). Opens the font file directly
        # via PIL rather than relying on the browser's
        # OS-level font-family matching, so a registry display name that
        # doesn't resolve as a CSS font-family (not uncommon for style-
        # linked faces like "Arial Bold") still renders correctly.
        # font_preview.render_font_name caches by (path, name, size, bg,
        # fg): the startup classification pass above already warms this
        # for every installed font, so in the common case this is just a
        # cache read, not a fresh render.
        p = theme_palettes.palette()
        tiles = [
            {'name': item['name'],
             'image': _image_to_data_uri(font_preview.render_font_name(
                 Path(item['path']), item['name'], GRID_TILE_SIZE,
                 bg=p['entry_bg'], fg=p['fg']))}
            for item in payload['fonts']
        ]
        return {'tiles': tiles}

    def classify(_payload: dict) -> dict:
        if classify_state['status'] == 'done':
            return {'status': 'done', 'fonts': classify_cache}
        start_classification()
        return {'status': classify_state['status']}

    def rescan(_payload: dict) -> dict:
        # Re-scans installed fonts from scratch: registry list, per-file
        # script/glyph classification, and grid-tile rendering. The one
        # deliberately heavier action left -- for when a font is installed
        # after this app already started and its automatic startup pass
        # already ran.
        classify_cache.clear()
        classify_state['status'] = 'idle'
        start_classification()
        return {'status': classify_state['status']}

    api.register('fonts.list_installed', list_installed)
    api.register('fonts.render_grid_tiles', render_grid_tiles)
    api.register('fonts.classify', classify)
    api.register('fonts.rescan', rescan)

    start_classification()
