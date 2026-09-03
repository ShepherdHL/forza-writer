"""Generator tab: font selection, character selection, output mode, vinyl
shape policy, and the main batch-generation run. The actual batch worker
is shared with Advanced Generator via batch_runner.py (see that module's
docstring).

Two deliberate UI choices:
  - Non-Latin alphabet groups are all shown at once rather than gated
    behind a script tab bar. Every checkbox and the "Select only <script>"
    shortcut are additive, not exclusive.
  - Per-glyph Configurator overrides (mask_overrides/manual_assignments)
    are resolved automatically from whatever's saved on disk for the
    selected font -- this handler's own `start()` never sets them
    directly; see batch_runner.resolve_overrides_for_generation.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import webview
from PIL import Image

_TOOLS_DIR = Path(__file__).resolve().parent.parent.parent
_REPO_ROOT = _TOOLS_DIR.parent
sys.path.insert(0, str(_TOOLS_DIR))
sys.path.insert(0, str(_REPO_ROOT))

import gui_settings  # noqa: E402
import theme_palettes  # noqa: E402
import vinyl_tiles  # noqa: E402
from gen_fontpack import find_pack_dir, glyph_filename, sanitize_prefix  # noqa: E402
from gen_fabric_project import build_fabric_project  # noqa: E402
from forza_writer import alphabets  # noqa: E402
from forza_writer.charset import charset_from_font  # noqa: E402
from forza_writer.compute_backend import resolve_backend  # noqa: E402
from forza_writer.fabric_project import save as save_project  # noqa: E402
from forza_writer.generation_policy import (  # noqa: E402
    DEFAULT_POLICY, FALLBACK_LABELS, FALLBACK_MODES, PRESET_LABELS, PRESETS,
    RECOMMENDED_PRESET, policy_from_dict, policy_to_dict)
from forza_writer.primitive_shapes import PRIMITIVE_CATALOG  # noqa: E402
from forza_writer.variable_fonts import inspect_variable_font  # noqa: E402

from . import batch_runner  # noqa: E402

_FONT_FILE_TYPES = ('Fonts (*.ttf;*.otf;*.ttc)', 'All files (*.*)')

# Read straight from assets/ rather than keeping a separate copy. Missing
# files are skipped, not an error, so the frontend's toggle just stays
# hidden until they're dropped in.
_EASTER_EGG_IMAGE_NAMES = ('lance_deepcirclelore.png', 'lance_optimalcircles.png')


def _easter_egg_images() -> list[str]:
    uris = []
    for name in _EASTER_EGG_IMAGE_NAMES:
        path = _REPO_ROOT / 'assets' / name
        if path.is_file():
            uris.append(batch_runner.image_to_data_uri(Image.open(path)))
    return uris

# Each non-Latin script's own endonym (the name speakers of it actually use),
# shown alongside the English label in the Characters grid -- e.g. "Ελληνικά
# (Greek)". Cyrillic/Devanagari/Thai/Arabic cover several languages each; the
# word shown is the script's own name (or its most emblematic language),
# since alphabets.py groups by script, not by one specific language.
_SCRIPT_NATIVE_NAMES = {
    'Cyrillic': 'Кириллица',
    'Greek': 'Ελληνικά',
    'Japanese': '日本語',
    'Korean': '한국어',
    'Devanagari': 'देवनागरी',
    'Thai': 'ภาษาไทย',
    'Arabic': 'العربية',
    'Hebrew': 'עברית',
    'Simplified Chinese': '简体中文',
    'Traditional Chinese': '繁體中文',
    'Vietnamese': 'Tiếng Việt',
    'Khmer': 'ខ្មែរ',
    'Tamil': 'தமிழ்',
}

# Groups the Characters grid into balanced regional sections (rather than
# one long flat list) so the card grid never ends a section on an
# orphaned trailing card. Vietnamese/Khmer are Latin/Brahmic-script
# respectively but geographically Southeast Asian, and Tamil spans South
# Asia and Southeast Asia (Singapore, Malaysia) -- all grouped with the
# other Asian entries rather than off in their own bucket.
_REGION_ORDER = ('European', 'Asian', 'Middle Eastern')
_SCRIPT_REGIONS = {
    'Cyrillic': 'European', 'Greek': 'European',
    'Japanese': 'Asian', 'Korean': 'Asian', 'Devanagari': 'Asian', 'Thai': 'Asian',
    'Simplified Chinese': 'Asian', 'Traditional Chinese': 'Asian', 'Vietnamese': 'Asian',
    'Khmer': 'Asian', 'Tamil': 'Asian',
    'Arabic': 'Middle Eastern', 'Hebrew': 'Middle Eastern',
}


def register(api, window, run_state: dict, state=None) -> None:
    run = run_state

    def browse_font(_payload: dict) -> dict:
        chosen = window.create_file_dialog(webview.FileDialog.OPEN, file_types=_FONT_FILE_TYPES)
        if not chosen:
            return {'cancelled': True}
        return {'path': chosen[0]}

    def set_current_font(payload: dict) -> dict:
        # Backs Advanced Generator's "Use current from Generator" pull --
        # the web app has no single shared object graph the way Tkinter's
        # tabs do, so Generator pushes its own selection here whenever it
        # changes and Advanced fetches it on demand instead.
        if state is not None:
            state.current_font = payload.get('font_path') or None
        return {'ok': True}

    def pick_out_dir(payload: dict) -> dict:
        chosen = window.create_file_dialog(webview.FileDialog.FOLDER, directory=payload.get('initial', ''))
        if not chosen:
            return {'cancelled': True}
        return {'path': chosen[0]}

    def font_info(payload: dict) -> dict:
        font_path = Path(payload['font_path'])
        result = {
            'lowercase_warning': '', 'variation_status': '', 'total_supported': 0,
            # is_variable/instance_count/defaults: structured form of
            # variation_status's prose, for a confirmation dialog that
            # blocks generating a variable font's raw, un-instantiated
            # outlines without the user explicitly choosing to.
            'is_variable': False, 'instance_count': 0, 'defaults': '',
        }
        try:
            categorized, _skipped = charset_from_font(font_path)
            supported = {char for chars in categorized.values() for char in chars}
            result['total_supported'] = len(supported)
            if not categorized.get('Lowercase'):
                result['lowercase_warning'] = 'This font has no lowercase glyphs -- the Lowercase category will be empty.'
        except Exception:
            pass
        try:
            info = inspect_variable_font(font_path)
            if not info.is_variable:
                result['variation_status'] = 'Static font (no variable axes).'
            else:
                defaults = ', '.join(f'{axis.tag}={axis.default:g}' for axis in info.axes)
                result['variation_status'] = (
                    f'Variable font: file default {defaults}, {len(info.instances)} named instance(s). '
                    'Use Advanced Generator to choose Regular or custom axes.')
                result['is_variable'] = True
                result['instance_count'] = len(info.instances)
                result['defaults'] = defaults
        except Exception:
            pass
        return result

    def get_alphabets(_payload: dict) -> dict:
        scripts = list(alphabets.ALPHABETS) + sorted(alphabets.NO_ALPHABET_SCRIPTS)
        return {
            'region_order': list(_REGION_ORDER),
            'scripts': [
                {
                    'name': script,
                    'native_name': _SCRIPT_NATIVE_NAMES.get(script),
                    'region': _SCRIPT_REGIONS.get(script, 'Asian'),
                    'no_alphabet': script in alphabets.NO_ALPHABET_SCRIPTS,
                    'caveat': alphabets.SHAPING_CAVEATS.get(script),
                    'groups': [{'label': label, 'count': len(set(letters))}
                               for label, letters in alphabets.groups_for_script(script)],
                }
                for script in scripts
            ],
        }

    def charset_summary(payload: dict) -> dict:
        font_path = Path(payload['font_path']) if payload.get('font_path') else None
        selected = batch_runner.selected_chars(payload, font_path)
        supported = None
        if font_path is not None:
            try:
                categorized, _ = charset_from_font(font_path)
                supported = {char for chars in categorized.values() for char in chars}
            except Exception:
                supported = None

        if selected is None:
            count = None if supported is None else len(supported)
            text = ('Entire font selected -- choose a font to see the glyph count.' if supported is None
                    else f'Entire font selected: {count:,} glyphs will be generated.')
        else:
            count = len(selected)
            if supported is None:
                text = f'{count:,} unique glyphs selected -- choose a font to check support.'
            else:
                available = len(selected & supported)
                missing = count - available
                text = f'{count:,} unique glyphs selected. {available:,} supported by this font'
                if missing:
                    text += f', {missing:,} unavailable'
        if count is not None and count >= 500:
            text += ' Large generation job.'

        font_total = len(supported) if supported is not None else None
        generated = None
        if supported is not None:
            generated = len(supported) if selected is None else len(selected & supported)
        return {
            'text': text,
            'count': count,
            'font_total': font_total,
            'generated': generated,
            'large_font': bool(font_total and font_total > 1000),
            'button_text': f'Generate {count:,} glyphs' if count is not None else 'Generate',
        }

    def filename_preview(payload: dict) -> dict:
        prefix = sanitize_prefix(payload['prefix']) if payload.get('prefix') else 'CUSTOM'
        ext = 'modelbin' if payload.get('output') == 'modelbin' else 'json'
        return {'upper': glyph_filename(prefix, 'A', ext), 'lower': glyph_filename(prefix, 'a', ext)}

    def get_primitive_catalog(_payload: dict) -> dict:
        return {'shapes': [{'id': sid, 'display_name': shape.display_name}
                            for sid, shape in PRIMITIVE_CATALOG.items()]}

    def render_shape_tile(payload: dict) -> dict:
        shape = PRIMITIVE_CATALOG[payload['shape_id']]
        image = vinyl_tiles.render_tile(shape, payload['state'], theme_palettes.palette())
        return {'image': batch_runner.image_to_data_uri(image)}

    def get_policy_defaults(_payload: dict) -> dict:
        settings = gui_settings.load_settings()
        policy, dropped = policy_from_dict({
            'allowed_shapes': settings.get('generation_allowed_shapes', []),
            'preferred_shapes': settings.get('generation_preferred_shapes', []),
            'fallback': settings.get('generation_fallback', DEFAULT_POLICY.fallback),
            'allow_exact_cover': settings.get('generation_allow_exact_cover', True),
            'allow_font_reuse': settings.get('generation_allow_font_reuse', False),
        })
        preset_name = settings.get('generation_preset', RECOMMENDED_PRESET)
        if preset_name in PRESETS and policy == PRESETS[preset_name]:
            policy = PRESETS[preset_name]
        return {
            'policy': policy_to_dict(policy),
            'dropped': dropped,
            'presets': {name: policy_to_dict(p) for name, p in PRESETS.items()},
            'preset_labels': PRESET_LABELS,
            'recommended_preset': RECOMMENDED_PRESET,
            'easter_egg_images': _easter_egg_images(),
            'fallback_modes': list(FALLBACK_MODES),
            'fallback_labels': FALLBACK_LABELS,
            'primitive_count': len(PRIMITIVE_CATALOG),
        }

    def validate_policy(payload: dict) -> dict:
        policy, _dropped = policy_from_dict(payload['policy'])
        problems = policy.validate()
        return {'problems': problems, 'allows_exact_cover': policy.allow_exact_cover}

    def open_output_folder(payload: dict) -> dict:
        """find_pack_dir (not pack_dir_for) accounts for build_fontpack's
        layer-count folder suffix, falling back to the root output dir when
        nothing's been generated under this exact profile (backend + curve
        smoothness) yet."""
        prefix = sanitize_prefix(payload['prefix'])
        backend = resolve_backend(payload['compute_backend'])
        out_dir = Path(payload['out_dir'])
        pack_dir = find_pack_dir(out_dir, prefix, payload['output'],
                                  max(1, int(payload['segments'])), backend.resolved)
        target = pack_dir if pack_dir is not None else out_dir
        if not target.is_dir():
            return {'opened': False, 'path': str(target)}
        os.startfile(target)  # noqa: S606 -- local desktop app, user's own files
        return {'opened': True, 'path': str(target)}

    def export_kfps(payload: dict) -> dict:
        # find_pack_dir (not pack_dir_for) accounts for build_fontpack's
        # layer-count folder suffix.
        prefix = sanitize_prefix(payload['prefix'])
        backend = resolve_backend(payload['compute_backend'])
        pack_dir = find_pack_dir(Path(payload['out_dir']), prefix, 'json',
                                  max(1, int(payload['segments'])), backend.resolved)
        if pack_dir is None:
            raise ValueError(
                f"No fontpack found for {prefix!r} under: {payload['out_dir']}\n\n"
                'Generate a fontpack with .json output first '
                '(Custom Mesh alone has no shapes to export).')
        lines: list[str] = []
        project = build_fabric_project(pack_dir, log=lines.append)
        out_path = pack_dir / f"{project['suggested_name']}.fabric-project.json"
        save_project(project, out_path)
        return {'path': str(out_path), 'log': lines}

    def halt(_payload: dict) -> dict:
        return batch_runner.halt(run)

    def abort(_payload: dict) -> dict:
        return batch_runner.abort(run)

    def start(payload: dict) -> dict:
        return batch_runner.start(window, run, payload, source_label='Generator')

    api.register('generator.browse_font', browse_font)
    api.register('generator.set_current_font', set_current_font)
    api.register('generator.pick_out_dir', pick_out_dir)
    api.register('generator.font_info', font_info)
    api.register('generator.get_alphabets', get_alphabets)
    api.register('generator.charset_summary', charset_summary)
    api.register('generator.filename_preview', filename_preview)
    api.register('generator.get_primitive_catalog', get_primitive_catalog)
    api.register('generator.render_shape_tile', render_shape_tile)
    api.register('generator.get_policy_defaults', get_policy_defaults)
    api.register('generator.validate_policy', validate_policy)
    api.register('generator.open_output_folder', open_output_folder)
    api.register('generator.export_kfps', export_kfps)
    api.register('generator.start', start)
    api.register('generator.halt', halt)
    api.register('generator.abort', abort)
