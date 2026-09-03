"""English strings for tools/gen_modelbin_web/state.py."""

STRINGS: dict[str, str] = {
    'state.tab.forza_font_text': 'Forza Font Text',
    'state.tab.generator': 'Generator',
    'state.tab.advanced': 'Advanced Generator',
    'state.tab.direct': 'Direct Generator',
    'state.tab.ascii_art': 'ASCII Art',
    'state.tab.glyph_inspector': 'Glyph Inspector',
    'state.tab.glyph_template': 'Glyph Template',
    'state.tab.layer_effects': 'Layer Effects',
    'state.tab.outputs': 'Output',
    'state.tab.composer': 'Composer',
    'state.tab.settings': 'Settings',
    'state.tab.credits': 'Credits',

    'state.mask_mode.auto': 'Auto',
    'state.mask_mode.force': 'Force Mask',
    'state.mask_mode.never': 'Force No Mask',
    'state.mask_mode.manual': 'Manual',

    'state.output_mode.modelbin.title': 'Custom Mesh (.modelbin)',
    'state.output_mode.modelbin.description': (
        'Experimental. These are the native files Forza games use for vinyls. Adding one to '
        'the game requires a catalog hijack or SQLite injection. KFPS cannot open this format; '
        'it only reads its own JSON vinyl format, not .modelbin. The preview in Output can '
        'confirm the file is structurally valid, but only the live hijack test confirms FH6 '
        'renders it correctly.'
    ),
    'state.output_mode.json.title': 'Shape Fitting (.json)',
    'state.output_mode.json.description': (
        "Analyzes each glyph and approximates it using Forza's full primitive-shape library, "
        'with optional masks.'
    ),
    'state.output_mode.json_legacy.title': 'Pixel Tracing (.json)',
    'state.output_mode.json_legacy.description': (
        'Rasterizes each glyph, then combines the filled pixels into rectangular vinyl layers.'
    ),
}
