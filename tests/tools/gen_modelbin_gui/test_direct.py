"""Direct Generator tab: the direct-to-shapes generation path.
"""
import json
import sys
import time
from pathlib import Path

import pytest

from .conftest import (  # noqa: E402
    AMARILLO_FONT, AMARILLO_FONTPACK, REFERENCE_MODELBIN, requires_assets, requires_font,
    requires_fontpack, tk, ttk, _configure_configurator_font, _configure_single_char_batch,
    _load_all_fonts_and_wait, _profiled_gui_pack_dir, _wait_for_configurator_detail,
    _wait_for_configurator_scan, _wait_for_font_scripts, _wait_for_worker, _write_loose_glyph_json)

def test_direct_output_filename_identifies_font():
    from gen_modelbin_gui import direct_output_filename

    font = Path(r"C:\fonts\Butcherman-Regular.ttf")
    assert direct_output_filename(font, "modern", backend="cpu", segments=8) == (
        "butcherman-regular_direct_modern_cpu_s8.json")
    assert direct_output_filename(font, "legacy", cell_size=2) == (
        "butcherman-regular_direct_legacy_cpu_cell2.json")
    image = Path(r"C:\images\Driver Signature.png")
    assert direct_output_filename(image, "image", cell_size=1) == (
        "driver-signature_image_to_text_cpu_cell1.json")


def test_direct_generation_is_a_first_class_tab(gui):
    assert 'direct' in gui._pages
    assert gui._tab_labels['direct'].cget('text') == (
        'D\u2009I\u2009R\u2009E\u2009C\u2009T\nG\u2009E\u2009N\u2009E\u2009R\u2009A\u2009T\u2009O\u2009R')
    assert gui._tab_labels['direct'].winfo_reqwidth() <= gui.sidebar.winfo_width()


def test_direct_generator_previews_before_saving_with_processor_metadata(gui, tmp_path, monkeypatch):
    import gen_modelbin_gui as mod

    font_path = tmp_path / 'debug-font.ttf'
    font_path.write_bytes(b'placeholder')
    output_path = tmp_path / 'direct.json'
    shape = {
        'type': 1, 'data': [0, 0, 1, 1, 0, 0, 0],
        'color': [255, 255, 255, 255], 'mask': False,
    }
    monkeypatch.setattr(mod, 'generate_direct', lambda *args, **kwargs: (
        [shape], [], {'method': 'modern', 'unique_glyphs': 1, 'strategies': {'A': 'fake'}}))
    monkeypatch.setattr(mod.filedialog, 'asksaveasfilename', lambda **_kwargs: str(output_path))
    monkeypatch.setattr(mod, 'resolve_backend', lambda _request: type(
        'Backend', (), {'resolved': 'cuda'})())
    gui.direct_font_var.set(str(font_path))
    gui.direct_text_widget.insert('1.0', 'AAA')
    gui.direct_method_var.set('modern')
    gui.direct_segments_var.set(6)

    gui._start_direct_generation()
    gui.worker.join(timeout=5)
    gui._poll_queue()

    assert not output_path.exists()
    assert gui._direct_payload['direct_generation']['method'] == 'modern'
    assert gui._direct_payload['direct_generation']['compute_backend'] == 'cuda'
    assert gui._direct_payload['direct_generation']['curve_segments'] == 6
    assert gui._direct_payload['direct_generation']['text'] == 'AAA'
    assert len(gui._direct_payload['shapes']) == 1
    assert str(gui.direct_generate_btn.cget('state')) == 'normal'
    assert str(gui.direct_save_btn.cget('state')) == 'normal'

    gui._save_direct_generation()
    payload = json.loads(output_path.read_text(encoding='utf-8'))
    assert payload['direct_generation']['method'] == 'modern'
    assert payload['direct_generation']['compute_backend'] == 'cuda'
    assert payload['direct_generation']['curve_segments'] == 6
    assert payload['direct_generation']['text'] == 'AAA'
    assert len(payload['shapes']) == 1

    gui.direct_text_widget.insert('end', 'B')
    gui._save_direct_generation()
    assert str(gui.direct_save_btn.cget('state')) == 'disabled'
    assert 'Generate a new preview' in gui.direct_status_var.get()


def test_generator_shortcut_sends_selected_font_to_direct_generator(gui, tmp_path):
    font_path = tmp_path / 'selected-font.ttf'
    font_path.write_bytes(b'font')
    gui.selected_font = font_path
    gui.direct_text_widget.insert('1.0', 'Keep this text')
    gui.direct_method_var.set('legacy')

    gui._open_current_font_in_direct()

    assert gui._current_tab == 'direct'
    assert gui.direct_font_var.get() == str(font_path)
    assert gui.direct_text_widget.get('1.0', 'end-1c') == 'Keep this text'
    assert gui.direct_method_var.get() == 'legacy'
    assert 'Direct Generator' in gui.generator_to_direct_btn.cget('text')


def test_direct_text_clear_and_select_all_buttons(gui):
    gui.direct_text_widget.insert('1.0', 'Some text')

    gui.direct_select_all_btn.invoke()
    assert tuple(str(i) for i in gui.direct_text_widget.tag_ranges('sel')) == (
        gui.direct_text_widget.index('1.0'), gui.direct_text_widget.index('1.0 lineend'))

    gui.direct_clear_btn.invoke()
    assert gui.direct_text_widget.get('1.0', 'end-1c') == ''


def test_direct_has_its_own_embedded_color_picker(gui):
    from gen_modelbin_gui.color_picker_widget import ColorPickerWidget
    assert isinstance(gui.direct_color_picker, ColorPickerWidget)


def test_direct_generation_forwards_the_picker_color(gui, tmp_path, monkeypatch):
    import gen_modelbin_gui as mod

    font_path = tmp_path / 'debug-font.ttf'
    font_path.write_bytes(b'placeholder')
    calls = []

    def fake_generate_direct(*args, **kwargs):
        calls.append(kwargs)
        return [], [], {'method': 'modern', 'unique_glyphs': 0, 'strategies': {}}

    monkeypatch.setattr(mod, 'generate_direct', fake_generate_direct)
    gui.direct_font_var.set(str(font_path))
    gui.direct_text_widget.insert('1.0', 'A')
    gui.direct_method_var.set('modern')
    gui.direct_color = (77, 88, 99, 255)

    gui._start_direct_generation()
    gui.worker.join(timeout=5)
    gui._poll_queue()

    assert calls and calls[0]['solid_color'] == (77, 88, 99, 255)


