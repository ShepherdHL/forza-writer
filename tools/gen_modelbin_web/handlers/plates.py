"""License Plates tab: browse a plate standard, fill in its fields, watch a
live preview, and generate ordinary Forza Writer shapes from it. The
library taxonomy, drill-down browser resolution (`_resolve_browser_state`
below), and every backend call (forza_writer.plates.*, plate_config_store,
fabric_project, export) live here directly.

Template-driven UI strings (a template's display name, a field's label, a
format hint) are resolved dynamically through this app's own i18n package
(tools/gen_modelbin_web/i18n) via t(key), since the key to look up isn't
known until a template/field is loaded from data.

The saved-configs UI is a flat dropdown + Load/Save/Delete (three
operations, no nested menu). Plate Details opens as a modal-free readout
in the shared Log panel.
"""
from __future__ import annotations

import base64
import io
import subprocess
import sys
import time
from pathlib import Path

import webview

_TOOLS_DIR = Path(__file__).resolve().parent.parent.parent
_REPO_ROOT = _TOOLS_DIR.parent
sys.path.insert(0, str(_TOOLS_DIR))
sys.path.insert(0, str(_REPO_ROOT))

import file_preview  # noqa: E402
import gui_settings  # noqa: E402
import theme_palettes  # noqa: E402
import plate_config_store  # noqa: E402
from gen_forza_fonts_reference import FONT_IDENTIFICATION  # noqa: E402
from forza_writer.export import save as save_json, to_json as plate_to_json  # noqa: E402
from forza_writer.fabric_project import save as save_fabric_project, to_fabric_project  # noqa: E402
from forza_writer.layout import layout_forza_text  # noqa: E402
from forza_writer.plates.instance import PlateInstance  # noqa: E402
from forza_writer.plates.loader import list_templates, reload_templates  # noqa: E402
from forza_writer.plates.renderer import PLATE_SHAPE_WARN_THRESHOLD, render_plate  # noqa: E402
from forza_writer.plates.template import FieldRole, PlateTemplate  # noqa: E402
from forza_writer.plates.validation import is_valid_for_generation, validate_instance  # noqa: E402

from ..events import push_event  # noqa: E402
from ..i18n import t  # noqa: E402
from ..state import PLATES_PREVIEW_SIZE  # noqa: E402

_PLATES_OUTPUT_DIR = _REPO_ROOT / 'data' / 'plates'

LIBRARY_REAL, LIBRARY_FICTIONAL, LIBRARY_COMMUNITY, LIBRARY_CUSTOM = 'real', 'fictional', 'community', 'custom'
_LIBRARY_ORDER = (LIBRARY_REAL, LIBRARY_FICTIONAL, LIBRARY_COMMUNITY, LIBRARY_CUSTOM)
_LIBRARY_LABELS = {
    LIBRARY_REAL: 'Real-World', LIBRARY_FICTIONAL: 'Fictional',
    LIBRARY_COMMUNITY: 'Community', LIBRARY_CUSTOM: 'Custom',
}
_LIBRARY_ROOT_LABELS = _LIBRARY_LABELS  # breadcrumb root text is identical to the library label

_COUNTRY_NAMES = {
    'US': 'United States', 'GB': 'United Kingdom', 'JP': 'Japan', 'DE': 'Germany',
    'GTA': 'Grand Theft Auto V', 'NFS': 'Need for Speed', 'SR': 'Saints Row', 'HALO': 'Halo',
    'CP2077': 'Cyberpunk 2077', 'MEDGE': "Mirror's Edge", 'DL': 'Dying Light',
    'PHAS': 'Phasmophobia', 'XX': 'Blank Template',
}
PLATE_CATEGORIES = {
    'passenger': 'Standard / Passenger', 'military': 'Military & Veteran',
    'law_enforcement': 'Law Enforcement', 'university': 'University / College',
    'organization': 'Organization / Service', 'special_interest': 'Special Interest',
    'high_school': 'High School', 'greek': 'Sorority / Fraternity',
}
_FIELD_ROLE_GROUPS = {
    FieldRole.REGISTRATION: 'Registration', FieldRole.REGION_CODE: 'Registration',
    FieldRole.CLASSIFICATION: 'Registration', FieldRole.JURISDICTION_TEXT: 'Header / Jurisdiction Text',
    FieldRole.DECORATIVE_TEXT: 'Decorative / Identification', FieldRole.FREE_TEXT: 'Custom Text',
}
_MODE_BASELINE_LABELS = {LIBRARY_REAL: 'Authentic', LIBRARY_FICTIONAL: 'Source Accurate', LIBRARY_COMMUNITY: 'Original'}
_PLACEHOLDER_FONT_CHOICES = (0,) + tuple(range(1, 12))
_PLACEHOLDER_SAMPLE_TEXT = 'ABC123'
_PLACEHOLDER_SAMPLE_SIZE = (128, 40)


def _country_display_name(code: str) -> str:
    return _COUNTRY_NAMES.get(code, code)


def _category_display_name(plate_type: str) -> str:
    return PLATE_CATEGORIES.get(plate_type, plate_type.replace('_', ' ').title())


def _has_string(key: str) -> bool:
    try:
        t(key)
        return True
    except KeyError:
        return False


def _template_display_name(template: PlateTemplate) -> str:
    return t(template.display_name_key) if _has_string(template.display_name_key) else template.template_id


def _field_display_label(field) -> str:
    return t(field.label_key) if _has_string(field.label_key) else field.field_id


def _plate_library(template: PlateTemplate) -> str:
    if template.country == 'XX':
        return LIBRARY_CUSTOM
    if 'community' in template.tags:
        return LIBRARY_COMMUNITY
    if 'fictional-game' in template.tags:
        return LIBRARY_FICTIONAL
    return LIBRARY_REAL


def _level_country(template: PlateTemplate) -> tuple[str, str]:
    return template.country, _country_display_name(template.country)


def _level_jurisdiction(template: PlateTemplate) -> tuple[str, str]:
    value = template.jurisdiction or 'General'
    return value, value


def _level_category(template: PlateTemplate) -> tuple[str, str]:
    return template.plate_type, _category_display_name(template.plate_type)


_GROUP_LEVELS = {
    LIBRARY_REAL: (_level_country, _level_jurisdiction, _level_category),
    LIBRARY_FICTIONAL: (_level_country, _level_jurisdiction),
    LIBRARY_COMMUNITY: (),
    LIBRARY_CUSTOM: (),
}


def _plate_matches_search(template: PlateTemplate, search: str) -> bool:
    haystack = ' '.join((
        _template_display_name(template), template.country, _country_display_name(template.country),
        template.jurisdiction or '', template.era, template.plate_type,
        _category_display_name(template.plate_type), ' '.join(template.tags), template.accuracy_status.value,
    )).lower()
    return search in haystack


def _placeholder_font_label(font: int) -> str:
    if font == 0:
        return 'Boxes (no letterforms)'
    ident = FONT_IDENTIFICATION.get(font, {'confirmed': False, 'note': 'Unidentified.'})
    mark = 'Confirmed' if ident['confirmed'] else 'Lead'
    note = ident['note']
    if note.strip().lower() == 'unidentified.':
        return f'Forza Font {font}'
    return f'Forza Font {font} ({mark}: {note})'


def _image_to_data_uri(image) -> str:
    buf = io.BytesIO()
    image.save(buf, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')


def _pool_for_library(templates: list[PlateTemplate], library: str) -> list[PlateTemplate]:
    return [tpl for tpl in templates if _plate_library(tpl) == library]


def _resolve_browser_state(templates: list[PlateTemplate], library: str, search: str | None,
                            breadcrumb: list[tuple[int, str]]):
    """Drills the library's templates down through `_GROUP_LEVELS`'
    grouping functions (e.g. category, then sub-category), one level at a
    time, stopping at the first level with more than one distinct value
    left to choose from.

    A search string skips grouping entirely and filters the whole pool by
    match instead. Otherwise, for each level in order: if `breadcrumb`
    already picked a key there, filter to it and record an explicit trail
    entry, then continue to the next level. Otherwise compute the distinct
    keys the current pool actually has at that level -- a level with only
    one distinct value auto-skips itself (filter to it, record a
    non-explicit trail entry, continue) rather than making the user pick
    among one option; a level with more than one stops the walk and
    returns immediately so the caller can render a picker for it.

    Returns `(pool, trail, distinct)`: `pool` is the templates surviving
    every filter so far, `trail` is the breadcrumb of levels resolved
    (explicitly or auto-skipped) as `(level_index, key, label, explicit)`
    tuples, and `distinct` is `{key: (label, count)}` for the level still
    awaiting a pick, or `None` once every level is resolved (fully drilled
    down, or overridden by search).
    """
    pool = _pool_for_library(templates, library)
    if search:
        pool = [tpl for tpl in pool if _plate_matches_search(tpl, search)]

    levels = _GROUP_LEVELS.get(library, ())
    explicit = dict(breadcrumb)
    trail: list[tuple[int, str, str, bool]] = []

    for idx, level_fn in enumerate(levels):
        if search:
            break
        pairs = [level_fn(tpl) for tpl in pool]
        if idx in explicit:
            key = explicit[idx]
            label = next((lab for k, lab in pairs if k == key), key)
            pool = [tpl for tpl, (k, _lab) in zip(pool, pairs) if k == key]
            trail.append((idx, key, label, True))
            continue
        distinct: dict[str, list] = {}
        for k, lab in pairs:
            entry = distinct.setdefault(k, [lab, 0])
            entry[1] += 1
        if len(distinct) <= 1:
            if distinct:
                only_key, (only_label, _count) = next(iter(distinct.items()))
                pool = [tpl for tpl, (k, _lab) in zip(pool, pairs) if k == only_key]
                trail.append((idx, only_key, only_label, False))
            continue
        return pool, trail, {k: tuple(v) for k, v in distinct.items()}

    return pool, trail, None


def _field_role_group(role: FieldRole) -> str:
    return _FIELD_ROLE_GROUPS.get(role, 'Custom Text')


def _format_details(template: PlateTemplate) -> list[str]:
    library = _plate_library(template)
    lines = [_template_display_name(template), '']
    if library != LIBRARY_CUSTOM:
        country_label = 'Franchise' if library == LIBRARY_FICTIONAL else 'Country'
        jurisdiction_label = 'Location' if library == LIBRARY_FICTIONAL else 'Jurisdiction'
        lines.append(f'{country_label}: {_country_display_name(template.country)}')
        if template.jurisdiction:
            lines.append(f'{jurisdiction_label}: {template.jurisdiction}')
        lines.append(f'Era: {template.era}')
        lines.append(f'Plate Type: {_category_display_name(template.plate_type)}')
    lines.append(f'Dimensions: {template.width_mm:g}mm x {template.height_mm:g}mm')
    lines.append(f'Accuracy Status: {template.accuracy_status.value}')
    prov = template.provenance
    if prov.contributors:
        lines.append(f'Contributors: {", ".join(prov.contributors)}')
    if prov.reconstruction_author:
        lines.append(f'Reconstructed By: {prov.reconstruction_author}')
    if prov.year_documented:
        lines.append(f'Year Documented: {prov.year_documented}')
    if prov.reference_urls:
        lines.append('Sources:')
        lines.extend(f'  {url}' for url in prov.reference_urls)
    lines.append('')
    lines.append(f'Notes: {prov.source_notes}')
    return lines


def _group_tree_to_dict(node) -> dict:
    """Ported verbatim from plates.py's own module-level helper (kept local
    there rather than using PlateGroupNode.to_dict() -- mirrored exactly,
    not assumed equivalent)."""
    return {
        'node_id': node.node_id, 'kind': node.kind.value, 'name_key': node.name_key,
        'shape_indices': list(node.shape_indices), 'editable': node.editable, 'deletable': node.deletable,
        'children': [_group_tree_to_dict(child) for child in node.children],
    }


def _instance_from_payload(payload: dict) -> PlateInstance:
    return PlateInstance(
        template_id=payload['template_id'], mode=payload.get('mode', 'vanity'),
        field_values=dict(payload.get('field_values') or {}),
        placeholder_font=payload.get('placeholder_font') or None,
    )


def register(api, window) -> None:
    def _templates() -> list[PlateTemplate]:
        reload_templates()
        return list_templates()

    def get_libraries(_payload: dict) -> dict:
        return {'libraries': [{'key': lib, 'label': _LIBRARY_LABELS[lib]} for lib in _LIBRARY_ORDER]}

    def get_placeholder_fonts(_payload: dict) -> dict:
        # A small real "ABC123" showcase per font -- same real letterform-mesh
        # rasters (KFPS's Resources/Vinyls/{family}/{index}.png, via
        # file_preview.kfps_vinyls_dir) the live plate preview itself draws
        # when placeholder_font is set, not a re-traced/approximated font.
        # Without KFPS configured there's no local mesh data for these at
        # all (see forza_writer/plates/glyph_resolve.py's module docstring),
        # so the sample silently falls back to plain boxes -- still shows
        # real character count/spacing, just not the real letterforms.
        settings = gui_settings.load_settings()
        vinyls_dir = file_preview.kfps_vinyls_dir(settings.get('kfps_executable', ''))
        p = theme_palettes.palette()
        fonts = []
        for f in _PLACEHOLDER_FONT_CHOICES:
            entry = {'value': f, 'label': _placeholder_font_label(f)}
            if f != 0:
                shapes = layout_forza_text(_PLACEHOLDER_SAMPLE_TEXT, font=f,
                                            target_height=_PLACEHOLDER_SAMPLE_SIZE[1] * 0.8)
                image = file_preview.render_composed_preview(
                    shapes, _PLACEHOLDER_SAMPLE_SIZE, bg=p['canvas_bg'], fg=p['fg'], vinyls_dir=vinyls_dir)
                entry['sample_image'] = _image_to_data_uri(image)
            fonts.append(entry)
        return {'fonts': fonts, 'has_real_letterforms': vinyls_dir is not None}

    def browse(payload: dict) -> dict:
        templates = _templates()
        library = payload.get('library', LIBRARY_REAL)
        search = (payload.get('search') or '').strip().lower() or None
        breadcrumb = [(int(li), key) for li, key in (payload.get('breadcrumb') or [])]
        pool, trail, distinct = _resolve_browser_state(templates, library, search, breadcrumb)

        trail_out = [{'level_index': li, 'key': k, 'label': lab, 'is_explicit': explicit}
                      for li, k, lab, explicit in trail]
        if not pool:
            empty_reason = ('empty_community' if (library == LIBRARY_COMMUNITY
                             and not _pool_for_library(templates, LIBRARY_COMMUNITY)) else 'empty_search')
            return {'trail': trail_out, 'mode': 'empty', 'empty_reason': empty_reason, 'items': []}
        if distinct is not None:
            items = [{'key': k, 'label': lab, 'count': c} for k, (lab, c) in
                      sorted(distinct.items(), key=lambda kv: kv[1][0])]
            return {'trail': trail_out, 'mode': 'groups', 'items': items}
        items = [{'template_id': tpl.template_id, 'label': _template_display_name(tpl), 'era': tpl.era}
                  for tpl in sorted(pool, key=_template_display_name)]
        return {'trail': trail_out, 'mode': 'leaves', 'items': items,
                'single': len(items) == 1}

    def get_template(payload: dict) -> dict:
        templates = _templates()
        template = next((t for t in templates if t.template_id == payload['template_id']), None)
        if template is None:
            raise ValueError(f"No such template: {payload['template_id']!r}")
        library = _plate_library(template)
        levels = _GROUP_LEVELS.get(library, ())
        default_breadcrumb = [[idx, level_fn(template)[0]] for idx, level_fn in enumerate(levels)]
        groups: dict[str, list[dict]] = {}
        for field in template.fields:
            group_key = _field_role_group(field.role)
            groups.setdefault(group_key, []).append({
                'field_id': field.field_id, 'label': _field_display_label(field), 'default_text': field.default_text,
            })
        return {
            'template_id': template.template_id,
            'display_name': _template_display_name(template),
            'library': library,
            'default_breadcrumb': default_breadcrumb,
            'mode_baseline_label': _MODE_BASELINE_LABELS.get(library),
            'field_groups': [{'group': group, 'fields': fields} for group, fields in groups.items()],
            'show_group_headers': len(groups) > 1,
        }

    def show_details(payload: dict) -> dict:
        templates = _templates()
        template = next((t for t in templates if t.template_id == payload['template_id']), None)
        if template is None:
            raise ValueError(f"No such template: {payload['template_id']!r}")
        push_event(window, 'log_append', 0, {'ts': time.strftime('%H:%M:%S'), 'level': 'hint', 'text': '--- Plate Details ---'})
        for line in _format_details(template):
            push_event(window, 'log_append', 0, {'ts': time.strftime('%H:%M:%S'), 'level': 'plain', 'text': line})
        return {'ok': True}

    def validate(payload: dict) -> dict:
        templates = _templates()
        template = next((t for t in templates if t.template_id == payload['template_id']), None)
        if template is None:
            return {'errors': []}
        instance = _instance_from_payload(payload)
        if instance.mode != 'authentic':
            return {'errors': []}
        errors = validate_instance(template, instance)
        return {'errors': [
            {'field_id': e.field_id, 'reason': e.reason,
             'format_hint': t(e.format_hint_key) if _has_string(e.format_hint_key) else e.format_hint_key}
            for e in errors
        ]}

    def preview(payload: dict) -> dict:
        templates = _templates()
        template = next((t for t in templates if t.template_id == payload['template_id']), None)
        if template is None:
            raise ValueError(f"No such template: {payload['template_id']!r}")
        instance = _instance_from_payload(payload)
        width = int(payload.get('width') or PLATES_PREVIEW_SIZE[0])
        height = int(payload.get('height') or PLATES_PREVIEW_SIZE[1])
        size = (width, height) if width > 1 and height > 1 else PLATES_PREVIEW_SIZE

        settings = gui_settings.load_settings()
        vinyls_dir = file_preview.kfps_vinyls_dir(settings.get('kfps_executable', ''))

        shapes, _root, warnings = render_plate(template, instance)
        p = theme_palettes.palette()
        image = file_preview.render_composed_preview(shapes, size, bg=p['canvas_bg'], fg=p['fg'], vinyls_dir=vinyls_dir)
        font_not_shown = bool(instance.placeholder_font) and vinyls_dir is None
        return {
            'preview_image': _image_to_data_uri(image),
            'shape_count': len(shapes),
            'warnings': warnings,
            'font_not_shown': font_not_shown,
            'over_threshold': len(shapes) > PLATE_SHAPE_WARN_THRESHOLD,
            'threshold': PLATE_SHAPE_WARN_THRESHOLD,
        }

    def generate(payload: dict) -> dict:
        templates = _templates()
        template = next((t for t in templates if t.template_id == payload['template_id']), None)
        if template is None:
            raise ValueError(f"No such template: {payload['template_id']!r}")
        instance = _instance_from_payload(payload)
        if not is_valid_for_generation(template, instance):
            raise ValueError('Fix the highlighted field(s) before generating.')

        shapes, root, warnings = render_plate(template, instance)
        if len(shapes) > PLATE_SHAPE_WARN_THRESHOLD and not payload.get('confirmed'):
            return {'needs_confirm': True, 'shape_count': len(shapes), 'threshold': PLATE_SHAPE_WARN_THRESHOLD}

        out_dir = _PLATES_OUTPUT_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        json_path = out_dir / f'{template.template_id}.json'
        data = plate_to_json(shapes)
        data['plate_groups'] = _group_tree_to_dict(root)
        save_json(data, json_path)

        fabric_path = out_dir / f'{template.template_id}.fabric-project.json'
        project = to_fabric_project(shapes, template.template_id, groups=root.to_group_tuples())
        save_fabric_project(project, fabric_path)

        return {'path': str(json_path), 'shape_count': len(shapes), 'warnings': warnings}

    def send_to_kfps(payload: dict) -> dict:
        json_path = Path(payload['json_path'])
        if not json_path.exists():
            raise ValueError('Generate a plate first, then Send to KFPS.')
        kfps_path = gui_settings.load_settings().get('kfps_executable', '').strip()
        if not kfps_path:
            raise ValueError("Set KFPS's executable path in Settings first (Settings tab -> KFPS Executable).")
        try:
            subprocess.Popen([kfps_path, str(json_path)])
        except OSError as exc:
            raise ValueError(f"Couldn't launch KFPS: {exc}") from exc
        return {'ok': True, 'path': str(json_path)}

    def list_configs(_payload: dict) -> dict:
        return {'names': plate_config_store.list_plate_configs()}

    def save_config(payload: dict) -> dict:
        instance = _instance_from_payload(payload)
        plate_config_store.save_plate_config(payload['name'], instance)
        return {'names': plate_config_store.list_plate_configs()}

    def load_config(payload: dict) -> dict:
        instance = plate_config_store.load_plate_config(payload['name'])
        if instance is None:
            return {'found': False}
        return {
            'found': True, 'template_id': instance.template_id, 'mode': instance.mode,
            'field_values': instance.field_values, 'placeholder_font': instance.placeholder_font or 0,
        }

    def delete_config(payload: dict) -> dict:
        deleted = plate_config_store.delete_plate_config(payload['name'])
        return {'deleted': deleted, 'names': plate_config_store.list_plate_configs()}

    api.register('plates.get_libraries', get_libraries)
    api.register('plates.get_placeholder_fonts', get_placeholder_fonts)
    api.register('plates.browse', browse)
    api.register('plates.get_template', get_template)
    api.register('plates.show_details', show_details)
    api.register('plates.validate', validate)
    api.register('plates.preview', preview)
    api.register('plates.generate', generate)
    api.register('plates.send_to_kfps', send_to_kfps)
    api.register('plates.list_configs', list_configs)
    api.register('plates.save_config', save_config)
    api.register('plates.load_config', load_config)
    api.register('plates.delete_config', delete_config)
