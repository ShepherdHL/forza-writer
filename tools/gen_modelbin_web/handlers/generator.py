"""Generator tab: font selection, character selection, output mode, vinyl
shape policy, and the main batch-generation run. Mirrors
tools/gen_modelbin_gui/tabs/generator.py; the actual batch worker is shared
with Advanced Generator via batch_runner.py (see that module's docstring),
mirroring tools/gen_modelbin_gui/shell.py's shared _start_generation/
_run_batch that both Tkinter tabs delegate to.

Two deliberate scope simplifications for this first web pass (both
call-out-able, non-functionality-losing UI simplifications, not engine
changes):
  - Font browsing is search-only (reuses the shared fonts.list_installed
    catalog via the frontend's ForzaFontSearch widget) plus "Browse on
    machine...". The Tkinter tab's List/Grid toggle and script-tab filter
    are a *browsing* convenience only -- every installed font is still
    reachable, just via typing instead of a thumbnail grid.
  - Non-Latin alphabet groups are all shown at once rather than gated
    behind the (deferred) font-browser's script tabs. Every checkbox and
    the "Select only <script>" shortcut are present and behave exactly as
    in Tkinter -- additive, not exclusive.
  - Per-glyph Configurator overrides (mask_overrides/manual_assignments)
    are out of scope here, same as Tkinter's own Generator tab which only
    ever calls _start_generation with overrides resolved automatically.
"""
from __future__ import annotations

import sys
from pathlib import Path

import webview

_TOOLS_DIR = Path(__file__).resolve().parent.parent.parent
_REPO_ROOT = _TOOLS_DIR.parent
sys.path.insert(0, str(_TOOLS_DIR))
sys.path.insert(0, str(_REPO_ROOT))

import gui_settings  # noqa: E402
import gui_theme  # noqa: E402
import vinyl_tiles  # noqa: E402
from gen_fontpack import glyph_filename, pack_dir_for, sanitize_prefix  # noqa: E402
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


def register(api, window, run_state: dict) -> None:
    run = run_state

    def browse_font(_payload: dict) -> dict:
        chosen = window.create_file_dialog(webview.FileDialog.OPEN, file_types=_FONT_FILE_TYPES)
        if not chosen:
            return {'cancelled': True}
        return {'path': chosen[0]}

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
            # variation_status's prose, for _confirm_variable_font's dialog --
            # mirrors Tkinter's _confirm_variable_font_generation (shell.py),
            # which blocks generating a variable font's raw, un-instantiated
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
        image = vinyl_tiles.render_tile(shape, payload['state'], gui_theme.palette())
        return {'image': batch_runner.image_to_data_uri(image)}

    def get_policy_defaults(_payload: dict) -> dict:
        settings = gui_settings.load_settings()
        policy, dropped = policy_from_dict({
            'allowed_shapes': settings.get('generation_allowed_shapes', []),
            'preferred_shapes': settings.get('generation_preferred_shapes', []),
            'fallback': settings.get('generation_fallback', DEFAULT_POLICY.fallback),
            'allow_exact_cover': settings.get('generation_allow_exact_cover', True),
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
            'fallback_modes': list(FALLBACK_MODES),
            'fallback_labels': FALLBACK_LABELS,
            'primitive_count': len(PRIMITIVE_CATALOG),
        }

    def validate_policy(payload: dict) -> dict:
        policy, _dropped = policy_from_dict(payload['policy'])
        problems = policy.validate()
        return {'problems': problems, 'allows_exact_cover': policy.allow_exact_cover}

    def export_kfps(payload: dict) -> dict:
        prefix = sanitize_prefix(payload['prefix'])
        backend = resolve_backend(payload['compute_backend'])
        pack_dir = pack_dir_for(Path(payload['out_dir']), prefix, 'json', max(1, int(payload['segments'])), backend.resolved)
        if not (pack_dir / 'manifest.json').exists():
            raise ValueError(
                f'No manifest.json in: {pack_dir}\n\nGenerate a fontpack with .json output first '
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
    api.register('generator.pick_out_dir', pick_out_dir)
    api.register('generator.font_info', font_info)
    api.register('generator.get_alphabets', get_alphabets)
    api.register('generator.charset_summary', charset_summary)
    api.register('generator.filename_preview', filename_preview)
    api.register('generator.get_primitive_catalog', get_primitive_catalog)
    api.register('generator.render_shape_tile', render_shape_tile)
    api.register('generator.get_policy_defaults', get_policy_defaults)
    api.register('generator.validate_policy', validate_policy)
    api.register('generator.export_kfps', export_kfps)
    api.register('generator.start', start)
    api.register('generator.halt', halt)
    api.register('generator.abort', abort)
