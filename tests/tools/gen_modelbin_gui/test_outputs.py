"""Output tab: browsing previously-generated fontpacks and their glyphs.
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

def test_outputs_pack_and_glyph_listboxes_have_their_own_scrollbars(gui):
    # A pack/glyph list longer than the visible area needs a visible
    # scrollbar; relying on the listbox's own native wheel scrolling gives
    # no visual cue that more content exists.
    for listbox in (gui.outputs_pack_listbox, gui.outputs_glyph_listbox):
        siblings = listbox.master.winfo_children()
        scrollbars = [w for w in siblings if isinstance(w, ttk.Scrollbar)]
        assert scrollbars, f'{listbox} has no sibling scrollbar'


def test_showing_outputs_tab_triggers_a_refresh(gui, monkeypatch):
    calls = []
    monkeypatch.setattr(gui, '_refresh_outputs_pack_list', lambda: calls.append(1))
    gui._show_tab('outputs')
    assert calls == [1]


@requires_fontpack
def test_outputs_refresh_lists_the_sample_fontpack(gui):
    gui.outputs_root_var.set(str(AMARILLO_FONTPACK.parent))
    gui._refresh_outputs_pack_list()
    names = [gui.outputs_pack_listbox.get(i) for i in range(gui.outputs_pack_listbox.size())]
    assert any('AMARILLO-USAF' in n for n in names)


def test_outputs_refresh_on_missing_root_does_not_raise(gui, tmp_path):
    gui.outputs_root_var.set(str(tmp_path / 'does-not-exist'))
    gui._refresh_outputs_pack_list()  # must not raise
    assert gui.outputs_pack_listbox.size() == 0


@requires_fontpack
def test_outputs_selecting_pack_lists_glyphs_by_category(gui):
    gui.outputs_root_var.set(str(AMARILLO_FONTPACK.parent))
    gui._refresh_outputs_pack_list()
    gui.outputs_pack_listbox.selection_set(0)
    gui._on_outputs_pack_selected()
    assert gui.outputs_glyph_listbox.size() > 0
    # One level deeper than the font folder itself: packs nest as
    # <font>/<profile>/manifest.json (see pack_dir_for).
    assert gui._outputs_current_pack_dir.parent == AMARILLO_FONTPACK


@requires_fontpack
def test_outputs_selecting_glyph_renders_preview(gui):
    gui.outputs_root_var.set(str(AMARILLO_FONTPACK.parent))
    gui._refresh_outputs_pack_list()
    gui.outputs_pack_listbox.selection_set(0)
    gui._on_outputs_pack_selected()
    gui.outputs_glyph_listbox.selection_set(0)
    gui._on_outputs_glyph_selected()
    assert gui._preview_photo is not None
    assert 'shape' in gui.preview_stats_var.get()


