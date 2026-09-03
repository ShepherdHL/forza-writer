"""Advanced Generator tab: variable-font axis/instance selection and
generation.

Shares its Characters and Vinyl Shapes UI logic with Generator via the
frontend's js/character-selector.js and js/vinyl-shapes.js components
(backed by the same generic generator.get_alphabets/charset_summary/
get_policy_defaults/render_shape_tile/validate_policy handlers Generator
itself uses), and shares the actual batch-generation worker/lock with
Generator via batch_runner.py -- see that module's docstring for why: in
Tkinter, Advanced Generator has no policy UI or character-selection UI of
its own at all and silently reads Generator's live Tk variables; the web
app has no such single shared object, so each generating tab gets its own
instance of the same two components instead of literally sharing state.

"Use current from Generator" (state.current_font, pushed by
generator.set_current_font whenever Generator's own selection changes) and
"Open per-glyph overrides for this instance" (open_instance_overrides,
below) close the two cross-tab gaps Tkinter's single object graph got for
free; see generator.py's set_current_font and configurator.py's module
docstring (its handlers already take font_path as a plain argument, so an
instantiated instance's temp file path scopes overrides correctly with no
Configurator-side change needed).
"""
from __future__ import annotations

import sys
from pathlib import Path

import webview

_TOOLS_DIR = Path(__file__).resolve().parent.parent.parent
_REPO_ROOT = _TOOLS_DIR.parent
sys.path.insert(0, str(_TOOLS_DIR))
sys.path.insert(0, str(_REPO_ROOT))

import font_preview  # noqa: E402
import theme_palettes  # noqa: E402
from gen_fontpack import sanitize_prefix  # noqa: E402
from forza_writer.charset import charset_from_font  # noqa: E402
from forza_writer.variable_fonts import inspect_variable_font, instantiate_font, variation_slug  # noqa: E402

from . import batch_runner  # noqa: E402

_FONT_FILE_TYPES = ('Variable or OpenType fonts (*.ttf;*.otf)', 'All files (*.*)')
_PREVIEW_SIZE = (640, 150)


def _instance_coordinates(info) -> dict[str, dict[str, float]]:
    """{label: coordinates} for 'Font default' plus every named instance,
    disambiguating a duplicate display name with its own coordinate slug --
    mirrors _load_advanced_font's dict-building loop exactly."""
    coords: dict[str, dict[str, float]] = {'Font default': dict(info.defaults)}
    for instance in info.instances:
        label = instance.name
        if label in coords:
            label = f'{label} ({variation_slug(instance.coordinates)})'
        coords[label] = dict(instance.coordinates)
    return coords


def register(api, window, run_state: dict, state=None) -> None:
    run = run_state

    def browse_font(_payload: dict) -> dict:
        chosen = window.create_file_dialog(webview.FileDialog.OPEN, file_types=_FONT_FILE_TYPES)
        if not chosen:
            return {'cancelled': True}
        return {'path': chosen[0]}

    def get_current_generator_font(_payload: dict) -> dict:
        return {'font_path': str(state.current_font) if state is not None and state.current_font else None}

    def open_instance_overrides(payload: dict) -> dict:
        # Instantiates the exact selected instance to a real static font
        # file and hands back its path, so the Generator-embedded
        # Configurator can scope per-glyph overrides to this instance
        # specifically -- a Thin and a Bold instance never share a repair,
        # since each coordinate combination instantiates to its own file.
        font_path = Path(payload['font_path'])
        coordinates = payload.get('coordinates') or {}
        instance_path = instantiate_font(font_path, coordinates)
        return {'instance_path': str(instance_path), 'slug': variation_slug(coordinates)}

    def inspect_font(payload: dict) -> dict:
        font_path = Path(payload['font_path'])
        if not font_path.exists():
            raise ValueError(f'Font not found: {font_path}')
        info = inspect_variable_font(font_path)
        if not info.is_variable:
            return {
                'is_variable': False,
                'status': ('This is a static font: it has no fvar variation axes. Use the Generator '
                           'tab unless you only need the advanced preview.'),
            }
        coords = _instance_coordinates(info)
        preferred = next((label for label in coords if label.casefold() == 'regular'), 'Font default')
        axis_text = ', '.join(
            f'{axis.name} {axis.minimum:g}-{axis.maximum:g} (file default {axis.default:g})'
            for axis in info.axes)
        return {
            'is_variable': True,
            'axes': [{'tag': a.tag, 'name': a.name, 'minimum': a.minimum, 'maximum': a.maximum,
                      'default': a.default} for a in info.axes],
            'instances': {label: coord for label, coord in coords.items()},
            'preferred_instance': preferred,
            'status': (f'Variable font: {len(info.axes)} axis/axes, {len(info.instances)} named '
                       f'instance(s). {axis_text}.'),
        }

    def preview(payload: dict) -> dict:
        font_path = Path(payload['font_path'])
        coordinates = payload.get('coordinates') or {}
        text = payload.get('text') or font_path.stem
        p = theme_palettes.palette()
        instance_path = instantiate_font(font_path, coordinates)
        image = font_preview.render_font_text(instance_path, text, _PREVIEW_SIZE, bg=p['canvas_bg'], fg=p['fg'])
        return {
            'preview_image': batch_runner.image_to_data_uri(image),
            'status': f'Previewing {variation_slug(coordinates)}.',
        }

    def workload_summary(payload: dict) -> dict:
        font_path = Path(payload['font_path']) if payload.get('font_path') else None
        if font_path is None:
            return {'text': 'Choose a variable font before generating.'}
        chars = batch_runner.selected_chars(payload, font_path)
        try:
            categorized, _ = charset_from_font(font_path)
            supported = {char for group in categorized.values() for char in group}
            glyph_count = len(supported if chars is None else supported & chars)
        except Exception:
            glyph_count = len(chars) if chars is not None else 0
        coordinates = payload.get('coordinates') or {}
        slug = variation_slug(coordinates)
        prefix = sanitize_prefix(payload.get('prefix', ''))
        instance_label = payload.get('instance_label', 'Custom')
        return {
            'text': (f'{glyph_count:,} glyphs x 1 instance = {glyph_count:,} outputs. '
                     f'{instance_label} ({slug}). Prefix {prefix}-{slug}'),
            'glyph_count': glyph_count,
        }

    def start(payload: dict) -> dict:
        font_path = Path(payload['font_path'])
        chars = batch_runner.selected_chars(payload, font_path)
        try:
            categorized, _ = charset_from_font(font_path)
            supported = {char for group in categorized.values() for char in group}
            glyph_count = len(supported if chars is None else supported & chars)
        except Exception:
            glyph_count = len(chars) if chars is not None else 0
        variation = {
            'named_instance': payload.get('instance_label', 'Custom'),
            'coordinates': payload.get('coordinates') or {},
            'source_font_file': str(font_path),
        }
        result = batch_runner.start(window, run, payload, source_label='Advanced Generator', variation=variation)
        result['glyph_count'] = glyph_count
        return result

    api.register('advanced.browse_font', browse_font)
    api.register('advanced.get_current_generator_font', get_current_generator_font)
    api.register('advanced.open_instance_overrides', open_instance_overrides)
    api.register('advanced.inspect_font', inspect_font)
    api.register('advanced.preview', preview)
    api.register('advanced.workload_summary', workload_summary)
    api.register('advanced.start', start)
