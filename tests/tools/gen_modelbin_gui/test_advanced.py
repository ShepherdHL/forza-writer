"""Advanced Generator tab: variable-font axis/instance selection and generation.
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


def test_prepared_advanced_instance_becomes_generators_authoritative_font(gui, tmp_path, monkeypatch):
    """The collapsed override workspace and main Generate action must target
    the same static variable-font instance prepared by Advanced Generator.
    """
    instance_path = tmp_path / 'selected-instance.ttf'
    instance_path.write_bytes(b'placeholder')
    gui._advanced_preview_generation = 7
    gui.prefix_var.set('SOURCE')
    monkeypatch.setattr(gui, '_advanced_coordinates', lambda: {'wght': 400})
    monkeypatch.setattr(gui, '_check_lowercase_warning', lambda: None)
    monkeypatch.setattr(gui, '_check_variable_font_status', lambda: None)
    monkeypatch.setattr(gui, '_on_character_selection_changed', lambda: None)
    opened = []
    monkeypatch.setattr(gui, '_set_configurator_workspace_open', opened.append)

    gui.msg_queue.put(('advanced_override_instance_ready', 7, instance_path))
    gui._poll_queue()

    assert gui.selected_font == instance_path
    assert gui.font_path_var.get() == str(instance_path)
    assert gui.prefix_var.get() == 'SOURCE-WGHT400'
    assert gui._current_tab == 'generator'
    assert opened == [True]

def test_advanced_generation_is_a_first_class_tab(gui):
    assert 'advanced' in gui._pages
    assert gui._tab_labels['advanced'].cget('text') == 'A\u2009D\u2009V\u2009A\u2009N\u2009C\u2009E\u2009D\nG\u2009E\u2009N\u2009E\u2009R\u2009A\u2009T\u2009O\u2009R'
    assert gui._tab_labels['advanced'].winfo_reqwidth() <= gui.sidebar.winfo_width()


def test_generator_shortcut_sends_selected_font_to_advanced_generator(gui, tmp_path, monkeypatch):
    font_path = tmp_path / 'selected-variable.ttf'
    font_path.write_bytes(b'font')
    gui.selected_font = font_path
    loaded = []
    monkeypatch.setattr(gui, '_load_advanced_font', lambda path: loaded.append(path))

    gui._open_current_font_in_advanced()

    assert gui._current_tab == 'advanced'
    assert loaded == [font_path]
    assert 'Send selected font' in gui.generator_to_advanced_btn.cget('text')


def test_advanced_variable_font_prefers_regular_named_instance(gui, tmp_path, monkeypatch):
    import gen_modelbin_gui as mod
    from forza_writer.variable_fonts import NamedInstance, VariableFontInfo, VariationAxis

    font_path = tmp_path / 'variable.ttf'
    font_path.write_bytes(b'placeholder')
    info = VariableFontInfo(
        (VariationAxis('wght', 'Weight', 100, 100, 900),),
        (NamedInstance('Thin', {'wght': 100}), NamedInstance('Regular', {'wght': 400}),
         NamedInstance('Bold', {'wght': 700})))
    monkeypatch.setattr(mod, 'inspect_variable_font', lambda _path: info)
    monkeypatch.setattr(gui, '_refresh_advanced_preview', lambda: None)

    gui._load_advanced_font(font_path)

    assert gui.advanced_instance_var.get() == 'Regular'
    assert gui._advanced_coordinates() == {'wght': 400.0}
    assert '3 named instance' in gui.advanced_font_status_var.get()


def test_advanced_generation_passes_one_explicit_instance_to_worker(gui, tmp_path, monkeypatch):
    import gen_modelbin_gui as mod
    from forza_writer.variable_fonts import NamedInstance, VariableFontInfo, VariationAxis

    font_path = tmp_path / 'variable.ttf'
    font_path.write_bytes(b'placeholder')
    info = VariableFontInfo(
        (VariationAxis('wght', 'Weight', 100, 100, 900),),
        (NamedInstance('Regular', {'wght': 400}),))
    monkeypatch.setattr(mod, 'inspect_variable_font', lambda _path: info)
    monkeypatch.setattr(gui, '_refresh_advanced_preview', lambda: None)
    monkeypatch.setattr(mod, 'charset_from_font', lambda _path: ({
        'Uppercase': ['A'], 'Lowercase': [], 'Letters': ['中'], 'Numbers': [],
        'Punctuation': [], 'Symbols': []}, []))
    gui._load_advanced_font(font_path)
    for var in (gui.upper_var, gui.lower_var, gui.digits_var, gui.punct_var,
                gui.symbols_var, gui.private_var):
        var.set(False)
    gui.custom_var.set('中')
    calls = []
    monkeypatch.setattr(gui, '_start_generation', lambda **kwargs: calls.append(kwargs) or True)

    gui._start_advanced_batch()

    assert len(calls) == 1
    assert calls[0]['font_path'] == font_path
    assert calls[0]['chars'] == {'中'}
    assert calls[0]['variation']['named_instance'] == 'Regular'
    assert calls[0]['variation']['coordinates'] == {'wght': 400.0}


