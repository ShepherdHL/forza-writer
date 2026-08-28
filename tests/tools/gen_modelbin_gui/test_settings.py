"""Settings tab: output/reference paths, palette/density, compute backend, appearance.
"""
import json
import sys
import time
from pathlib import Path

import pytest

from conftest import (  # noqa: E402
    AMARILLO_FONT, AMARILLO_FONTPACK, REFERENCE_MODELBIN, requires_assets, requires_font,
    requires_fontpack, tk, ttk, _configure_configurator_font, _configure_single_char_batch,
    _load_all_fonts_and_wait, _profiled_gui_pack_dir, _wait_for_configurator_detail,
    _wait_for_configurator_scan, _wait_for_font_scripts, _wait_for_worker, _write_loose_glyph_json)

def test_settings_save_persists_current_out_and_ref_vars(gui, tmp_path, monkeypatch):
    import gui_settings

    settings_path = tmp_path / 'settings.json'
    monkeypatch.setattr(gui_settings, 'SETTINGS_PATH', settings_path)
    monkeypatch.setattr(gui_settings, 'SETTINGS_DIR', settings_path.parent)

    gui.out_var.set(str(tmp_path / 'packs'))
    gui.modelbin_out_var.set(str(tmp_path / 'modelbin'))
    gui.direct_out_var.set(str(tmp_path / 'direct'))
    gui.ref_var.set(str(tmp_path / 'ref.modelbin'))
    gui.palette_var.set('slate')
    gui.density_var.set('spacious')
    gui.compute_backend_var.set('cpu')
    gui._save_settings()

    loaded = gui_settings.load_settings()
    assert loaded['output_dir'] == str(tmp_path / 'packs')
    assert loaded['modelbin_output_dir'] == str(tmp_path / 'modelbin')
    assert loaded['direct_output_dir'] == str(tmp_path / 'direct')
    assert loaded['reference_modelbin'] == str(tmp_path / 'ref.modelbin')
    assert loaded['palette'] == 'slate'
    assert loaded['density'] == 'spacious'
    assert loaded['compute_backend'] == 'cpu'
    assert gui.settings_saved_var.get() == 'Saved.'


def test_appearance_defaults_are_charcoal_and_balanced(gui):
    import gui_settings
    assert gui_settings.DEFAULT_SETTINGS['palette'] == 'charcoal'
    assert gui_settings.DEFAULT_SETTINGS['density'] == 'balanced'


def test_appearance_changes_preview_immediately_without_saving(gui, tmp_path, monkeypatch):
    import gui_settings
    import gui_theme

    settings_path = tmp_path / 'settings.json'
    monkeypatch.setattr(gui_settings, 'SETTINGS_PATH', settings_path)
    monkeypatch.setattr(gui_settings, 'SETTINGS_DIR', settings_path.parent)

    gui.palette_var.set('charcoal')
    gui.density_var.set('compact')
    gui._preview_appearance()
    original_font = gui._tab_labels['generator'].cget('font')
    try:
        gui.palette_var.set('slate')
        gui.density_var.set('spacious')
        gui._preview_appearance()
        assert gui.root.cget('bg') == gui_theme.PALETTES['slate']['bg']
        assert gui.style.lookup('TLabel', 'background') == gui_theme.PALETTES['slate']['panel_alt']
        assert gui_theme.CURRENT_DENSITY == 'spacious'
        assert gui._tab_labels['generator'].cget('font') != original_font
        assert 'immediately' in gui.appearance_hint_var.get()
    finally:
        gui.palette_var.set('charcoal')
        gui.density_var.set('balanced')
        gui._preview_appearance()


def test_appearance_changes_persist_without_clicking_save(gui, tmp_path, monkeypatch):
    """Picking a palette/density is itself the save action now -- no
    separate trip to the Save settings button, matching how window geometry
    and the color picker's saved/recent colors already persist immediately."""
    import gui_settings

    settings_path = tmp_path / 'settings.json'
    monkeypatch.setattr(gui_settings, 'SETTINGS_PATH', settings_path)
    monkeypatch.setattr(gui_settings, 'SETTINGS_DIR', settings_path.parent)

    gui.palette_var.set('eurocorp')
    gui.density_var.set('compact')
    gui._preview_appearance()

    loaded = gui_settings.load_settings()
    assert loaded['palette'] == 'eurocorp'
    assert loaded['density'] == 'compact'


def test_save_settings_does_not_reset_unrelated_saved_fields(gui, tmp_path, monkeypatch):
    """Regression test: _save_settings used to call gui_settings.save_settings
    with a partial dict, which silently resets every field it doesn't name
    back to DEFAULT_SETTINGS -- window geometry, the color picker's saved/
    recent colors, and each tab's own last color included."""
    import gui_settings

    settings_path = tmp_path / 'settings.json'
    monkeypatch.setattr(gui_settings, 'SETTINGS_PATH', settings_path)
    monkeypatch.setattr(gui_settings, 'SETTINGS_DIR', settings_path.parent)

    gui_settings.save_settings({
        'window_geometry': '1200x900+50+60',
        'window_maximized': False,
        'saved_colors': {'Team Red': [200, 20, 20, 255]},
        'recent_colors': [[1, 2, 3, 255]],
        'color_ascii_art': [10, 20, 30, 255],
    })

    gui._save_settings()

    loaded = gui_settings.load_settings()
    assert loaded['window_geometry'] == '1200x900+50+60'
    assert loaded['window_maximized'] is False
    assert loaded['saved_colors'] == {'Team Red': [200, 20, 20, 255]}
    assert loaded['recent_colors'] == [[1, 2, 3, 255]]
    assert loaded['color_ascii_art'] == [10, 20, 30, 255]


def test_settings_status_reflects_path_existence(gui, tmp_path):
    real_dir = tmp_path / 'exists'
    real_dir.mkdir()
    gui.out_var.set(str(real_dir))
    gui.direct_out_var.set(str(tmp_path / 'not-there-yet'))
    gui.ref_var.set(str(tmp_path / 'nope.modelbin'))
    gui._update_settings_status()
    assert '✓' in gui.settings_out_status_var.get()
    assert 'will be created' in gui.settings_direct_out_status_var.get()
    assert '✗' in gui.settings_ref_status_var.get()
    # The found/not-found state is a real success/danger distinction, not
    # just glyph-only — the label itself carries the matching style.
    assert str(gui.settings_out_status_lbl['style']) == 'Success.TLabel'
    assert str(gui.settings_direct_out_status_lbl['style']) == 'Hint.TLabel'
    assert str(gui.settings_ref_status_lbl['style']) == 'Danger.TLabel'


def test_settings_status_styles_both_found_as_success(gui, tmp_path):
    ref_file = tmp_path / 'ref.modelbin'
    ref_file.write_bytes(b'')
    gui.out_var.set(str(tmp_path))
    gui.ref_var.set(str(ref_file))
    gui._update_settings_status()
    assert str(gui.settings_out_status_lbl['style']) == 'Success.TLabel'
    assert str(gui.settings_ref_status_lbl['style']) == 'Success.TLabel'


def test_generator_status_line_reflects_settings(gui, tmp_path):
    gui.out_var.set(str(tmp_path))
    gui.ref_var.set('some_ref.modelbin')
    gui._update_settings_status()
    assert str(tmp_path) in gui.generator_settings_status_var.get()
    assert 'some_ref.modelbin' in gui.generator_settings_status_var.get()


def test_clean_generated_data_requires_both_confirmations(gui, tmp_path, monkeypatch):
    import generated_data_cleanup
    import gen_modelbin_gui as mod

    targets = (tmp_path / 'fontpacks',)
    targets[0].mkdir()
    gui.cleanup_selection_vars['fontpacks'].set(True)
    monkeypatch.setattr(generated_data_cleanup, 'cleanup_targets',
                        lambda _root, selected=None: targets)
    monkeypatch.setattr(
        generated_data_cleanup, 'summarize',
        lambda _targets: generated_data_cleanup.CleanupSummary(targets, 2, 1024))
    cleared = []
    monkeypatch.setattr(generated_data_cleanup, 'clear_generated_data',
                        lambda _root, selected=None: cleared.append(True))
    answers = iter((True, False))
    monkeypatch.setattr(mod.messagebox, 'askyesno', lambda *_args, **_kwargs: next(answers))

    gui._clean_generated_data()

    assert cleared == []


def test_clean_generated_data_clears_after_second_confirmation(gui, tmp_path, monkeypatch):
    import generated_data_cleanup
    import gen_modelbin_gui as mod

    targets = (tmp_path / 'fontpacks',)
    targets[0].mkdir()
    summary = generated_data_cleanup.CleanupSummary(targets, 3, 2048)
    gui.cleanup_selection_vars['fontpacks'].set(True)
    monkeypatch.setattr(generated_data_cleanup, 'cleanup_targets',
                        lambda _root, selected=None: targets)
    monkeypatch.setattr(generated_data_cleanup, 'summarize', lambda _targets: summary)
    monkeypatch.setattr(generated_data_cleanup, 'clear_generated_data',
                        lambda _root, selected=None: summary)
    monkeypatch.setattr(mod.messagebox, 'askyesno', lambda *_args, **_kwargs: True)
    monkeypatch.setattr(gui, '_refresh_outputs_pack_list', lambda: None)

    gui._clean_generated_data()

    assert 'removed 3 file(s)' in gui.cleanup_status_var.get().lower()


def test_clean_generated_data_requires_at_least_one_category(gui, monkeypatch):
    import gen_modelbin_gui as mod

    warnings = []
    monkeypatch.setattr(mod.messagebox, 'showwarning',
                        lambda title, message: warnings.append((title, message)))
    gui._select_cleanup_targets(False)

    gui._clean_generated_data()

    assert warnings
    assert 'nothing selected' in warnings[0][0].lower()


def test_cleanup_select_all_and_none_controls_every_category(gui):
    gui._select_cleanup_targets(True)
    assert all(variable.get() for variable in gui.cleanup_selection_vars.values())
    gui._select_cleanup_targets(False)
    assert not any(variable.get() for variable in gui.cleanup_selection_vars.values())


def test_cleanup_categories_have_descriptions_and_receive_size_labels(gui):
    import generated_data_cleanup

    assert set(gui.cleanup_size_vars) == set(generated_data_cleanup.TARGET_DESCRIPTIONS)
    deadline = time.time() + 5
    while any(var.get() == 'Calculating…' for var in gui.cleanup_size_vars.values()) and time.time() < deadline:
        gui._poll_queue()
        gui.root.update()
        time.sleep(0.01)
    assert all('file(s)' in var.get() for var in gui.cleanup_size_vars.values())


