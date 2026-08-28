"""English strings for tools/gen_modelbin_gui/shell.py."""

STRINGS: dict[str, str] = {
    'shell.window.title': 'Forza Writer',
    'shell.log.panel_title': 'Log',

    'shell.button.select_all': 'Select All',
    'shell.button.clear': 'Clear',
    'shell.button.browse': 'Browse...',
    'shell.button.insert': 'Insert',
    'shell.label.sample_text': 'Sample Text:',
    'shell.hint.sample_text': (
        'Sample text exercises most of the script. Some scripts offer multiple options, such '
        'as an alphabet row or a full passage. Pick one from the second dropdown.'
    ),
    'shell.log.no_sample_text': 'No sample text available for {script}.',
    'shell.log.inserted_sample_text': 'Inserted {script} sample text ({label}).',

    'shell.log.admin_mode_detected': (
        'Administrator mode detected. This tool does not require Administrator mode for '
        'normal operation. Only the separate FH6 process-memory diagnostics may require '
        'elevation.'
    ),

    'shell.log.batch_already_running': 'A batch is already running. Halt or abort it first.',
    'shell.log.select_font_first': 'Select a font first.',
    'shell.log.reference_modelbin_not_found': 'Reference modelbin not found: {path}',
    'shell.log.reference_modelbin_hint': (
        'This is an extracted FH6 game asset. See README.md, then set it in Settings.'
    ),
    'shell.log.no_characters_selected': 'No characters selected.',

    'shell.dialog.directml_warning_title': 'Experimental: AMD DirectML Generation',
    'shell.dialog.directml_warning_body': (
        'This generation method has not been professionally tested on AMD/Radeon hardware. '
        'It is included to support every hardware choice without requiring a specific GPU '
        'vendor.\n\n'
        'If the system becomes unstable during generation, abort the process immediately.'
    ),
    'shell.log.directml_cancelled': 'Generation cancelled at the DirectML warning.',

    'shell.log.fix_vinyl_shapes': (
        'Fix the vinyl shape selection under "5. Vinyl shapes" before generating.'
    ),

    'shell.dialog.variable_font_title': 'Variable Font Selected',
    'shell.dialog.variable_font_body': (
        '"{font_name}" is a variable font with {instance_count} named instance(s) '
        '(file default: {defaults}).\n\n'
        "Generating here uses the file's raw, un-instantiated outlines, not a deliberately "
        'chosen weight or style. Use Advanced Generator to pick a named instance, such as '
        'Regular or Bold, or custom axis coordinates instead.\n\n'
        'Continue anyway with the raw default outlines?'
    ),
    'shell.log.variable_font_cancelled': (
        'Generation cancelled. Use Advanced Generator for this variable font.'
    ),

    'shell.dialog.large_job_title': 'Large Generation Job',
    'shell.dialog.large_job_body': (
        'This will generate {glyph_count} glyphs and may take a long time.\n\n'
        'Continue with this large job?'
    ),
    'shell.log.large_job_cancelled': (
        'Large generation cancelled before starting ({glyph_count} glyphs).'
    ),

    'shell.log.aborted': '--- Aborted: {removed} file(s) removed ---',
    'shell.log.done': '--- Done: {bits}, {skipped} skipped -> {manifest_path} ---',
    'shell.log.done_halted': '--- Done (halted early): {bits}, {skipped} skipped -> {manifest_path} ---',
    'shell.log.failed': '--- FAILED: {error} ---',

    'shell.log.fallback_used': (
        '    Fallback used on {count} glyph(s). The selected shapes could not reach the '
        'quality target alone.'
    ),
    'shell.log.quality_shortfall': (
        '    {count} glyph(s) fell short of the quality target with the selected shapes. See '
        'the manifest for details.'
    ),

    'shell.status.live_preview_generating': 'Generating... {done} done: {category} {char}',
    'shell.status.live_preview_generating_quality': (
        'Generating... {done} done: {category} {char} ({verdict}, IoU {iou}, edge {boundary_f1})'
    ),

    'shell.log.direct_generator_failed': '--- Direct Generator failed: {error} ---',
    'shell.status.direct_generate_failed': 'Could not generate text: {error}',

    'shell.status.font_scan_count': '{count} font(s) found.',
    'shell.status.cleanup_size_summary': '{size} · {count} file(s)',

    'shell.status.configurator_scan_done': (
        '{count} glyph outline(s) inspected. Curved glyphs fit only when selected.'
    ),
    'shell.status.configurator_render_failed': 'Could not render {char}: {error}',

    'shell.status.advanced_preview_ready': (
        'Previewing {instance} from cached static instance {instance_file}.'
    ),
    'shell.status.advanced_preview_failed': 'Could not prepare instance: {error}',

    'shell.status.glyph_inspector_load_failed': 'Could not load font: {error}',
}
