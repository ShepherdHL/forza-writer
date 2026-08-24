"""Composer tab: composing/previewing multi-line vinyl text.
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

@requires_fontpack
def test_compose_text_renders_preview_and_enables_save(gui):
    gui.compose_pack_var.set(str(AMARILLO_FONTPACK))
    gui.compose_text_widget.delete('1.0', 'end')
    gui.compose_text_widget.insert('1.0', 'Hi')
    gui.compose_align_var.set('left')

    gui._compose_text()

    assert gui._composed_shapes
    assert str(gui.compose_save_btn['state']) == 'normal'
    assert gui._compose_photo is not None
    assert 'shape' in gui.compose_stats_var.get()
    assert str(gui.compose_stats_lbl['style']) == 'Hint.TLabel'


def test_compose_text_missing_pack_shows_message(gui, tmp_path):
    gui.compose_pack_var.set(str(tmp_path / 'no-such-pack'))
    gui.compose_text_widget.delete('1.0', 'end')
    gui.compose_text_widget.insert('1.0', 'Hi')

    gui._compose_text()

    assert 'No manifest.json' in gui.compose_stats_var.get()
    assert gui._composed_shapes == []
    assert str(gui.compose_stats_lbl['style']) == 'Danger.TLabel'


@requires_fontpack
def test_compose_text_empty_input_shows_message(gui):
    gui.compose_pack_var.set(str(AMARILLO_FONTPACK))
    gui.compose_text_widget.delete('1.0', 'end')

    gui._compose_text()

    assert 'Type some text' in gui.compose_stats_var.get()


@requires_fontpack
def test_save_composed_text_writes_file(gui, tmp_path, monkeypatch):
    import gen_modelbin_gui as mod

    gui.compose_pack_var.set(str(AMARILLO_FONTPACK))
    gui.compose_text_widget.delete('1.0', 'end')
    gui.compose_text_widget.insert('1.0', 'Hi')
    gui._compose_text()

    out_path = tmp_path / 'out.json'
    monkeypatch.setattr(mod.filedialog, 'asksaveasfilename', lambda **kw: str(out_path))

    gui._save_composed_text()

    assert out_path.exists()
    import json as jsonlib
    data = jsonlib.loads(out_path.read_text(encoding='utf-8'))
    assert data['format'] == 'fh6_typecode_json_export_v1'
    assert len(data['shapes']) == len(gui._composed_shapes)


def test_use_current_pack_dir_derives_from_prefix_and_out_dir(gui, tmp_path):
    gui.prefix_var.set('MYFONT')
    gui.out_var.set(str(tmp_path))
    gui._use_current_pack_dir()
    assert gui.compose_pack_var.get() == str(_profiled_gui_pack_dir(gui, tmp_path, 'MYFONT'))


def test_picker_updates_color_without_rebuilding_line_editor(gui):
    row_widgets = tuple(gui.compose_line_rows_container.winfo_children())
    swatch = gui._compose_swatch_widgets[(0, 0)]

    gui._set_compose_current_color((12, 34, 56, 255), record_recent=False)

    assert tuple(gui.compose_line_rows_container.winfo_children()) == row_widgets
    assert gui._compose_swatch_widgets[(0, 0)] is swatch
    assert swatch.cget('background') == '#0c2238'
    assert gui._compose_line_fills[0]['colors'][0] == (12, 34, 56, 255)


def test_picker_drag_records_only_final_color(gui):
    gui._compose_recent_colors.clear()

    gui._set_compose_current_color((10, 20, 30, 255), record_recent=False)
    gui._set_compose_current_color((20, 30, 40, 255), record_recent=False)
    gui._set_compose_current_color((30, 40, 50, 255), record_recent=False)

    assert gui._compose_recent_colors == []
    gui._commit_compose_picker_recent()
    assert gui._compose_recent_colors == [(30, 40, 50, 255)]


