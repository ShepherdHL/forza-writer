"""Glyph Inspector tab: font loading, and its Compare mode's pipeline
(background fit -> compare_masks/diff_overlay_image via forza_writer.
glyph_quality), talking to the real backend directly.
"""
from __future__ import annotations

import difflib
import json
import re
import sys
import threading
from pathlib import Path

import webview

_TOOLS_DIR = Path(__file__).resolve().parent.parent.parent
_REPO_ROOT = _TOOLS_DIR.parent
sys.path.insert(0, str(_TOOLS_DIR))
sys.path.insert(0, str(_REPO_ROOT))

import file_preview  # noqa: E402
import font_preview  # noqa: E402
import glyph_reference_preview  # noqa: E402
import gui_settings  # noqa: E402
import theme_palettes  # noqa: E402
from gen_modelbin import extract_contours, normalize_to_128  # noqa: E402
from forza_writer import glyph_quality  # noqa: E402
from forza_writer.compute_backend import resolve_backend  # noqa: E402
from forza_writer.font_info import glyph_geometry, load_font_info  # noqa: E402
from forza_writer.generation_policy import DEFAULT_POLICY  # noqa: E402
from forza_writer.primitive_fit import fit_glyph_with_strategy, rasterize_contours  # noqa: E402

from ..events import push_event  # noqa: E402
from ..imaging import image_to_data_uri as _image_to_data_uri  # noqa: E402
from ..state import (  # noqa: E402
    FONTS_DIR_SYSTEM, GLYPH_CATEGORY_TILE_CAP, GLYPH_PREVIEW_SIZE, GLYPH_TILE_SIZE, enumerate_installed_fonts)

_FONT_FILE_TYPES = ('Fonts (*.ttf;*.otf;*.ttc)',)
_SHAPE_FILE_TYPES = ('Shape JSON (*.json)',)

# Tokens a hand-made shape file's name commonly carries that are not part
# of the font's own name. Stripped before fuzzy-matching against installed
# font display names. Example: "AmarilloUSAF_FontPack_242.fabric-project.json"
# becomes "amarillousaf".
_FILENAME_NOISE_RE = re.compile(
    r'(_?fontpack_?\d*|_?v\d+|\.fabric-project|\.json$|[_\-\s]+\d+$)', re.IGNORECASE)


def _normalize_for_match(text: str) -> str:
    return re.sub(r'[^a-z0-9]', '', text.lower())


def _guess_font_from_filename(filename: str) -> dict | None:
    """Best-effort suggestion only. Never auto-applied. A hand-made shape
    file's name often embeds the font it was designed against. See the
    module docstring's example. This is worth surfacing, but a wrong guess
    must never silently swap the loaded font out from under the user. See
    load_handmade's caller in glyph-inspector.js. It only ever shows this
    as a dismissible suggestion."""
    stem = Path(filename).stem
    stem = _FILENAME_NOISE_RE.sub('', stem)
    needle = _normalize_for_match(stem)
    if len(needle) < 3:
        return None

    best_name, best_path, best_score = None, None, 0.0
    for display_name, path in enumerate_installed_fonts().items():
        haystack = _normalize_for_match(display_name)
        if not haystack:
            continue
        if needle == haystack:
            return {'name': display_name, 'path': str(path)}
        if needle in haystack or haystack in needle:
            score = min(len(needle), len(haystack)) / max(len(needle), len(haystack))
        else:
            score = difflib.SequenceMatcher(None, needle, haystack).ratio()
        if score > best_score:
            best_name, best_path, best_score = display_name, path, score
    if best_score >= 0.72:
        return {'name': best_name, 'path': str(best_path)}
    return None


def _font_status_text(info) -> str:
    weight = f', weight {info.names.weight_class}' if info.names.weight_class else ''
    italic = ', italic' if info.names.is_italic else ''
    glyph_count = sum(len(glyphs) for glyphs in info.glyphs_by_category.values())
    return (
        f'{info.names.full_name} ({info.names.family} {info.names.subfamily}{weight}{italic}), '
        f'{glyph_count:,} glyph(s) across {len(info.category_order)} categories.'
    )


def _categories_payload(info) -> list[dict]:
    """The categorized glyph grid's full metadata (no images -- those are
    fetched per-tile via render_tiles) -- cheap enough to send in one shot
    even for a large CJK font, since it's just text/numbers. Having every
    glyph's metadata client-side up front is what lets search filtering
    (see character-selector-style _matches_glyph_search on the JS side)
    happen instantly with no round trip per keystroke, matching Tkinter's
    own already-loaded-GlyphInfo-objects behavior.
    """
    return [
        {
            'name': category,
            'glyphs': [
                {'char': g.char, 'codepoint': g.codepoint, 'glyph_name': g.glyph_name,
                 'unicode_name': g.unicode_name}
                for g in glyphs
            ],
        }
        for category, glyphs in ((c, info.glyphs_by_category[c]) for c in info.category_order)
    ]


def register(api, window) -> None:
    # Per-process state for this tab only. Deliberately not folded into
    # state.AppState. Nothing outside this handler module needs it.
    loaded_font: dict = {'path': None, 'name': None, 'info': None}
    handmade_shapes: dict[str, list[dict]] = {}
    fit_cache: dict[tuple, tuple[list[dict], str]] = {}
    generation = {'n': 0}

    def _font_loaded_payload(font_path: Path) -> dict:
        info = load_font_info(font_path)  # raises on an unreadable/invalid font file
        loaded_font['path'] = font_path
        loaded_font['name'] = info.names.full_name
        loaded_font['info'] = info
        return {
            'path': str(font_path), 'name': info.names.full_name, 'status': _font_status_text(info),
            'categories': _categories_payload(info),
            'metrics': {
                'units_per_em': info.metrics.units_per_em, 'ascender': info.metrics.ascender,
                'descender': info.metrics.descender, 'cap_height': info.metrics.cap_height,
                'x_height': info.metrics.x_height,
            },
            'category_tile_cap': GLYPH_CATEGORY_TILE_CAP,
        }

    def load_font(payload: dict) -> dict:
        chosen = window.create_file_dialog(
            webview.FileDialog.OPEN, directory=payload.get('directory') or str(FONTS_DIR_SYSTEM),
            file_types=_FONT_FILE_TYPES)
        if not chosen:
            return {'cancelled': True}
        return _font_loaded_payload(Path(chosen[0]))

    def load_font_by_path(payload: dict) -> dict:
        """Loads a font the user already located. No dialog. Used to apply
        a filename-based suggestion (see _guess_font_from_filename) with one
        click instead of re-browsing to the same folder."""
        return _font_loaded_payload(Path(payload['path']))

    def _glyph_by_char(char: str):
        info = loaded_font['info']
        if info is None:
            raise ValueError('Load a font first.')
        for glyphs in info.glyphs_by_category.values():
            for g in glyphs:
                if g.char == char:
                    return g
        raise ValueError(f'{char!r} is not in the currently loaded font.')

    def render_tiles(payload: dict) -> dict:
        font_path = loaded_font['path']
        if font_path is None:
            raise ValueError('Load a font first.')
        p = theme_palettes.palette()
        tiles = [
            _image_to_data_uri(font_preview.render_glyph_tile(font_path, char, GLYPH_TILE_SIZE,
                                                                bg=p['entry_bg'], fg=p['fg']))
            for char in payload['chars']
        ]
        return {'tiles': tiles}

    def get_geometry(payload: dict) -> dict:
        glyph = _glyph_by_char(payload['char'])
        geometry = glyph_geometry(loaded_font['path'], glyph)
        if geometry.bbox is not None:
            x_min, y_min, x_max, y_max = geometry.bbox
            bearings = f'L {geometry.left_side_bearing:g} · R {geometry.right_side_bearing:g}'
            bbox = f'{geometry.width:g} × {geometry.height:g} (x {x_min:g}..{x_max:g}, y {y_min:g}..{y_max:g})'
        else:
            bearings = f'L {geometry.left_side_bearing:g} · R —'
            bbox = '(no drawable outline)'
        return {
            'char': glyph.char, 'codepoint': f'U+{glyph.codepoint:04X}',
            'unicode_name': glyph.unicode_name or '(unnamed)', 'glyph_name': glyph.glyph_name,
            'category': glyph.category, 'advance_width': f'{geometry.advance_width:g} units',
            'bearings': bearings, 'bbox': bbox,
        }

    def get_reference(payload: dict) -> dict:
        glyph = _glyph_by_char(payload['char'])
        info = loaded_font['info']
        p = theme_palettes.palette()
        image = glyph_reference_preview.render_glyph_reference(
            loaded_font['path'], glyph.char, GLYPH_PREVIEW_SIZE,
            units_per_em=info.metrics.units_per_em, ascender=info.metrics.ascender,
            descender=info.metrics.descender, cap_height=info.metrics.cap_height,
            x_height=info.metrics.x_height, bg=p['canvas_bg'], fg=p['fg'],
            guide_color=p['border'], label_color=p['hint'])
        return {'image': _image_to_data_uri(image),
                'status': "Reference: rendered directly from the font's outline."}

    def get_generated(payload: dict) -> dict:
        char = payload['char']
        font_path = loaded_font['path']
        if font_path is None:
            raise ValueError('Load a font first.')
        backend_choice = payload.get('compute_backend', 'auto')

        generation['n'] += 1
        gen = generation['n']

        def worker():
            try:
                cache_key = (str(font_path), char, backend_choice)
                cached = fit_cache.get(cache_key)
                if cached is None:
                    backend = resolve_backend(backend_choice)
                    if backend_choice in ('cuda', 'directml') and not backend.available:
                        raise RuntimeError(backend.detail)
                    shapes, strategy = fit_glyph_with_strategy(
                        char, font_path, compute_backend=backend.resolved, policy=DEFAULT_POLICY)
                    fit_cache[cache_key] = (shapes, strategy)
                else:
                    shapes, strategy = cached
                    backend = resolve_backend(backend_choice)

                p = theme_palettes.palette()
                vinyls_dir = file_preview.kfps_vinyls_dir(gui_settings.load_settings().get('kfps_executable', ''))
                image = file_preview.render_json_preview(shapes, GLYPH_PREVIEW_SIZE, bg=p['canvas_bg'], fg=p['fg'],
                                                          vinyls_dir=vinyls_dir)
                mask_count = sum(1 for s in shapes if s.get('mask'))
                push_event(window, 'glyph_inspector_generated_ready', gen, {
                    'image': _image_to_data_uri(image),
                    'status': f'Generated: {len(shapes)} shape(s), {mask_count} mask cutout(s), '
                              f'strategy {strategy} ({backend.resolved.upper()}).',
                })
            except Exception as exc:
                push_event(window, 'glyph_inspector_generated_error', gen, {'error': str(exc)})

        threading.Thread(target=worker, daemon=True).start()
        return {'generation': gen}

    def load_handmade(payload: dict) -> dict:
        char = payload.get('char')
        if not char:
            raise ValueError('No character set. Type a character to compare first.')
        chosen = window.create_file_dialog(webview.FileDialog.OPEN, file_types=_SHAPE_FILE_TYPES)
        if not chosen:
            return {'cancelled': True}
        chosen_path = Path(chosen[0])
        data = json.loads(chosen_path.read_text(encoding='utf-8'))
        shapes = data.get('shapes') if isinstance(data, dict) else None
        if not shapes:
            raise ValueError(
                'No non-empty "shapes" array found. This must be a single-glyph, origin-'
                'centered {"shapes": [...]} file (the same format Configurator\'s manual '
                'overrides use), not a whole multi-glyph design export.')
        handmade_shapes[char] = shapes
        suggestion = _guess_font_from_filename(chosen_path.name)
        return {'path': str(chosen_path), 'suggested_font': suggestion}

    def compare(payload: dict) -> dict:
        char = payload.get('char')
        if not char:
            raise ValueError('Type a character to compare.')
        if loaded_font['path'] is None:
            raise ValueError('Load a font first.')
        target_mode = payload.get('target', 'outline')
        backend_choice = payload.get('compute_backend', 'auto')

        generation['n'] += 1
        gen = generation['n']
        font_path = loaded_font['path']

        def worker():
            try:
                cache_key = (str(font_path), char, backend_choice)
                cached = fit_cache.get(cache_key)
                if cached is None:
                    backend = resolve_backend(backend_choice)
                    if backend_choice in ('cuda', 'directml') and not backend.available:
                        raise RuntimeError(backend.detail)
                    shapes, strategy = fit_glyph_with_strategy(
                        char, font_path, compute_backend=backend.resolved, policy=DEFAULT_POLICY)
                    fit_cache[cache_key] = (shapes, strategy)
                else:
                    shapes, strategy = cached

                resolution = glyph_quality.DEFAULT_VERIFY_RESOLUTION
                generated_mask, unknown = glyph_quality.render_shapes_mask(shapes, resolution)

                if target_mode == 'handmade':
                    handmade = handmade_shapes.get(char)
                    if handmade is None:
                        raise ValueError(
                            "No hand-made file loaded for this glyph. Use 'Load hand-made "
                            "file...' first.")
                    target_mask, _ = glyph_quality.render_shapes_mask(handmade, resolution)
                else:
                    contours, upm = extract_contours(char, font_path, 8)
                    target_mask = rasterize_contours(normalize_to_128(contours, upm), resolution)

                metrics = glyph_quality.compare_masks(target_mask, generated_mask, unknown_type_words=unknown)
                overlay = glyph_quality.diff_overlay_image(target_mask, generated_mask)
                push_event(window, 'glyph_inspector_compare_ready', gen, {
                    'metrics': metrics,
                    'overlay': _image_to_data_uri(overlay),
                    'strategy': strategy,
                })
            except Exception as exc:
                push_event(window, 'glyph_inspector_compare_error', gen, {'error': str(exc)})

        threading.Thread(target=worker, daemon=True).start()
        return {'generation': gen, 'status': 'started'}

    api.register('glyph_inspector.load_font', load_font)
    api.register('glyph_inspector.load_font_by_path', load_font_by_path)
    api.register('glyph_inspector.render_tiles', render_tiles)
    api.register('glyph_inspector.get_geometry', get_geometry)
    api.register('glyph_inspector.get_reference', get_reference)
    api.register('glyph_inspector.get_generated', get_generated)
    api.register('glyph_inspector.load_handmade', load_handmade)
    api.register('glyph_inspector.compare', compare)
