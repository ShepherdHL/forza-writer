"""English strings for tools/gen_modelbin_web/handlers/plates.py.

'state.tab.plates' lives here rather than in i18n/en/state.py: every
per-module catalog merges into one global STRINGS dict regardless of which
file defines a given key (see i18n/en/__init__.py's pkgutil-based merge),
so this key can be added without touching state.py's own catalog file at
all -- state.py's TAB_LABELS just calls t('state.tab.plates') the same way
it calls every other tab's key.
"""

STRINGS: dict[str, str] = {
    'state.tab.plates': 'License Plates',

    # -- Library selector (Real-World / Fictional / Community / Custom) -----
    'plates.library.real': 'Real-World',
    'plates.library.fictional': 'Fictional',
    'plates.library.community': 'Community',
    'plates.library.custom': 'Custom',

    'plates.search.placeholder.real': 'Search countries, jurisdictions, eras, or plate types...',
    'plates.search.placeholder.fictional': 'Search franchises, locations, factions, or plate types...',
    'plates.search.placeholder.community': 'Search creators, kits, games, or plate types...',
    'plates.search.placeholder.custom': 'Search custom templates...',

    'plates.browser.none_selected': 'Select a plate from the browser to begin.',
    'plates.browser.empty_community': (
        'No community plate kits yet. Credited, imported community work will appear here once added.'
    ),
    'plates.browser.empty_search': 'No plates match your search in this library.',
    'plates.browser.breadcrumb_root.real': 'Real-World',
    'plates.browser.breadcrumb_root.fictional': 'Fictional',
    'plates.browser.breadcrumb_root.community': 'Community',
    'plates.browser.breadcrumb_root.custom': 'Custom',
    'plates.browser.details_button': 'Details...',
    'plates.browser.back_button': '‹ Back',

    # -- Plate rules (formerly "Mode") -- terminology varies by library so
    # "Authentic" is never forced onto fictional/community content.
    'plates.mode.title': 'Plate Rules',
    'plates.mode.baseline.real': 'Authentic',
    'plates.mode.baseline.fictional': 'Source Accurate',
    'plates.mode.baseline.community': 'Original',
    'plates.mode.customized': 'Customized',
    'plates.mode.vanity_badge': 'Customized -- not regulation-compliant',

    'plates.placeholder_font.title': 'Placeholder Font',

    'plates.fields.title': 'Plate Settings',
    'plates.fields.group.registration': 'Registration',
    'plates.fields.group.header': 'Header / Jurisdiction Text',
    'plates.fields.group.decorative': 'Decorative / Identification',
    'plates.fields.group.custom': 'Custom Text',

    'plates.preview.title': 'Preview',
    'plates.preview.not_yet_rendered': 'Pick a plate to preview it here.',
    'plates.preview.rendering': 'Rendering...',
    'plates.preview.shape_count': '~{count} shapes',
    'plates.preview.font_not_shown': (
        '(showing boxes -- set KFPS\'s executable path in Settings to preview this font\'s '
        'real letterforms here)'
    ),
    'plates.preview.shape_count_warning': (
        '~{count} shapes -- this exceeds the usual budget ({threshold}) and may be slow or '
        'unstable in-game.'
    ),

    'plates.validation.blocked': (
        '{field_label}: {reason}\nExpected format: {format_hint}'
    ),

    'plates.generate.button': 'Generate Plate',
    'plates.generate.blocked': 'Fix the highlighted field(s) before generating.',
    'plates.generate.confirm_large': (
        'This plate is estimated at ~{count} shapes, above the usual budget of {threshold}. '
        'Generate anyway?'
    ),
    'plates.generate.done': 'Generated {count} shapes -> {path}',
    'plates.generate.failed': "Couldn't generate this plate: {error}",
    'plates.generate.send_to_kfps': 'Send to KFPS',
    'plates.generate.kfps_nothing_generated': 'Generate a plate first, then Send to KFPS.',
    'plates.generate.kfps_not_configured': (
        'Set KFPS\'s executable path in Settings first (Settings tab -> KFPS Executable).'
    ),
    'plates.generate.kfps_sent': 'Sent {path} to KFPS.',
    'plates.generate.kfps_failed': "Couldn't launch KFPS: {error}",

    'plates.config.menu_button': 'Saved',
    'plates.config.save_button': 'Save Current...',
    'plates.config.delete_button': 'Delete "{name}"',
    'plates.config.name_prompt': 'Name for this saved configuration:',
    'plates.config.none_saved': 'No saved configurations yet.',
    'plates.config.empty_menu': 'No saved configurations',

    'plates.details.title': 'Plate Details',
    'plates.details.field.country.real': 'Country',
    'plates.details.field.country.fictional': 'Franchise',
    'plates.details.field.jurisdiction.real': 'Jurisdiction',
    'plates.details.field.jurisdiction.fictional': 'Location',
    'plates.details.field.era': 'Era',
    'plates.details.field.plate_type': 'Plate Type',
    'plates.details.field.dimensions': 'Dimensions',
    'plates.details.field.accuracy': 'Accuracy Status',
    'plates.details.field.contributors': 'Contributors',
    'plates.details.field.reconstruction_author': 'Reconstructed By',
    'plates.details.field.year_documented': 'Year Documented',
    'plates.details.field.sources': 'Sources',
    'plates.details.field.notes': 'Notes',
}
