"""Generator's per-glyph override workspace: mask-mode overrides.
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

@requires_font
def test_rescan_without_a_font_shows_a_hint_and_no_rows(gui, tmp_path, monkeypatch):
    monkeypatch.setattr('glyph_overrides.OVERRIDES_PATH', tmp_path / 'glyph_overrides.json')
    monkeypatch.setattr('glyph_overrides.OVERRIDES_DIR', tmp_path)
    gui.configurator_font_var.set('')

    gui._rescan_configurator_glyphs()

    assert gui.configurator_tree.get_children() == ()
    assert 'font' in gui.configurator_scan_status_var.get().lower()


@requires_font
def test_rescan_with_a_nonexistent_font_path_shows_not_found(gui, tmp_path, monkeypatch):
    monkeypatch.setattr('glyph_overrides.OVERRIDES_PATH', tmp_path / 'glyph_overrides.json')
    monkeypatch.setattr('glyph_overrides.OVERRIDES_DIR', tmp_path)
    gui.configurator_font_var.set(str(tmp_path / 'does_not_exist.ttf'))

    gui._rescan_configurator_glyphs()

    assert gui.configurator_tree.get_children() == ()
    assert 'not found' in gui.configurator_scan_status_var.get().lower()


@requires_font
def test_rescan_populates_the_fonts_whole_charset(gui, tmp_path, monkeypatch):
    # Unlike Generator's checkboxes, Configurator shows every glyph the
    # font has: it's for reviewing/overriding, not restricting what
    # generates (that stays Generator's job).
    monkeypatch.setattr('glyph_overrides.OVERRIDES_PATH', tmp_path / 'glyph_overrides.json')
    monkeypatch.setattr('glyph_overrides.OVERRIDES_DIR', tmp_path)
    _configure_configurator_font(gui)

    gui._rescan_configurator_glyphs()
    _wait_for_configurator_scan(gui)

    children = gui.configurator_tree.get_children()
    assert 'A' in children and 'a' in children and '0' in children
    assert gui.configurator_tree.set('A', 'auto') != 'scanning…'


@requires_font
def test_selecting_a_glyph_row_renders_a_preview_and_status(gui, tmp_path, monkeypatch):
    monkeypatch.setattr('glyph_overrides.OVERRIDES_PATH', tmp_path / 'glyph_overrides.json')
    monkeypatch.setattr('glyph_overrides.OVERRIDES_DIR', tmp_path)
    _configure_configurator_font(gui)
    gui._rescan_configurator_glyphs()
    _wait_for_configurator_scan(gui)

    gui.configurator_tree.selection_set('A')
    gui._on_configurator_glyph_selected()
    _wait_for_configurator_detail(gui)

    assert gui._configurator_selected_char == 'A'
    assert gui._configurator_preview_photo is not None, gui.configurator_detail_status_var.get()
    assert 'shape' in gui.configurator_detail_status_var.get()


@requires_font
def test_forcing_no_mask_updates_mode_column_and_persists(gui, tmp_path, monkeypatch):
    monkeypatch.setattr('glyph_overrides.OVERRIDES_PATH', tmp_path / 'glyph_overrides.json')
    monkeypatch.setattr('glyph_overrides.OVERRIDES_DIR', tmp_path)
    _configure_configurator_font(gui)
    gui._rescan_configurator_glyphs()
    _wait_for_configurator_scan(gui)

    gui.configurator_tree.selection_set('A')
    gui._on_configurator_glyph_selected()
    _wait_for_configurator_detail(gui)
    gui.configurator_mode_var.set('never')
    gui._on_configurator_mode_changed()

    assert gui._configurator_overrides['A'] == {'mode': 'never'}
    assert gui.configurator_tree.set('A', 'mode') == 'Force No Mask'

    import glyph_overrides
    on_disk = glyph_overrides.load_overrides_for_font(AMARILLO_FONT)
    assert on_disk['A'] == {'mode': 'never'}


@requires_font
def test_assign_file_sets_mode_to_manual_and_updates_column(gui, tmp_path, monkeypatch):
    import gen_modelbin_gui as mod
    monkeypatch.setattr('glyph_overrides.OVERRIDES_PATH', tmp_path / 'glyph_overrides.json')
    monkeypatch.setattr('glyph_overrides.OVERRIDES_DIR', tmp_path)
    _configure_configurator_font(gui)
    gui._rescan_configurator_glyphs()
    _wait_for_configurator_scan(gui)

    src = tmp_path / 'my_kfps_export.json'
    _write_loose_glyph_json(src, [{'type': 1048677, 'type_word': 101, 'data': [0, 0, 1, 1, 0, 0, 0],
                                    'color': [255, 255, 255, 255], 'mask': False}])
    monkeypatch.setattr(mod.filedialog, 'askopenfilename', lambda **kw: str(src))

    gui.configurator_tree.selection_set('A')
    gui._on_configurator_glyph_selected()
    _wait_for_configurator_detail(gui)
    gui._configurator_assign_file()

    assert gui._configurator_overrides['A'] == {'mode': 'manual', 'file': str(src)}
    assert 'my_kfps_export.json' in gui.configurator_tree.set('A', 'mode')

    import glyph_overrides
    on_disk = glyph_overrides.load_overrides_for_font(AMARILLO_FONT)
    assert on_disk['A'] == {'mode': 'manual', 'file': str(src)}


@requires_font
def test_assign_file_with_no_glyph_selected_logs_a_warning_and_does_nothing(gui, tmp_path, monkeypatch):
    import gen_modelbin_gui as mod
    monkeypatch.setattr('glyph_overrides.OVERRIDES_PATH', tmp_path / 'glyph_overrides.json')
    monkeypatch.setattr('glyph_overrides.OVERRIDES_DIR', tmp_path)
    called = []
    monkeypatch.setattr(mod.filedialog, 'askopenfilename', lambda **kw: called.append(True) or '')
    gui._configurator_selected_char = None

    gui._configurator_assign_file()

    assert called == []  # the file dialog must never even open
    warn_line_start = gui.log.search('Select a glyph first.', '1.0', 'end')
    assert warn_line_start != ''


@requires_font
def test_switching_mode_away_from_manual_drops_the_file_assignment(gui, tmp_path, monkeypatch):
    import gen_modelbin_gui as mod
    monkeypatch.setattr('glyph_overrides.OVERRIDES_PATH', tmp_path / 'glyph_overrides.json')
    monkeypatch.setattr('glyph_overrides.OVERRIDES_DIR', tmp_path)
    _configure_configurator_font(gui)
    gui._rescan_configurator_glyphs()
    _wait_for_configurator_scan(gui)

    src = tmp_path / 'assigned.json'
    _write_loose_glyph_json(src, [])
    monkeypatch.setattr(mod.filedialog, 'askopenfilename', lambda **kw: str(src))
    gui.configurator_tree.selection_set('A')
    gui._on_configurator_glyph_selected()
    _wait_for_configurator_detail(gui)
    gui._configurator_assign_file()
    assert gui._configurator_overrides['A']['mode'] == 'manual'

    gui.configurator_mode_var.set('auto')
    gui._on_configurator_mode_changed()

    assert 'A' not in gui._configurator_overrides
    assert gui.configurator_tree.set('A', 'mode') == 'Auto'


@requires_font
def test_reset_all_clears_overrides_and_saves(gui, tmp_path, monkeypatch):
    monkeypatch.setattr('glyph_overrides.OVERRIDES_PATH', tmp_path / 'glyph_overrides.json')
    monkeypatch.setattr('glyph_overrides.OVERRIDES_DIR', tmp_path)
    _configure_configurator_font(gui)
    gui._rescan_configurator_glyphs()
    _wait_for_configurator_scan(gui)
    gui._configurator_overrides['A'] = {'mode': 'never'}
    gui._update_configurator_row('A')

    gui._configurator_reset_all()

    assert gui._configurator_overrides == {}
    assert gui.configurator_tree.set('A', 'mode') == 'Auto'
    import glyph_overrides
    assert glyph_overrides.load_overrides_for_font(AMARILLO_FONT) == {}


@requires_font
def test_rescan_loads_previously_saved_overrides(gui, tmp_path, monkeypatch):
    monkeypatch.setattr('glyph_overrides.OVERRIDES_PATH', tmp_path / 'glyph_overrides.json')
    monkeypatch.setattr('glyph_overrides.OVERRIDES_DIR', tmp_path)
    import glyph_overrides
    glyph_overrides.save_overrides_for_font(AMARILLO_FONT, {'B': {'mode': 'never'}})
    _configure_configurator_font(gui)

    gui._rescan_configurator_glyphs()
    _wait_for_configurator_scan(gui)

    assert gui._configurator_overrides == {'B': {'mode': 'never'}}
    assert gui.configurator_tree.set('B', 'mode') == 'Force No Mask'
    assert gui.configurator_tree.set('A', 'mode') == 'Auto'


@requires_font
def test_force_all_rectilinear_skips_manual_glyphs(gui, tmp_path, monkeypatch):
    import gen_modelbin_gui as mod
    monkeypatch.setattr('glyph_overrides.OVERRIDES_PATH', tmp_path / 'glyph_overrides.json')
    monkeypatch.setattr('glyph_overrides.OVERRIDES_DIR', tmp_path)
    _configure_configurator_font(gui)
    gui._rescan_configurator_glyphs()
    _wait_for_configurator_scan(gui)

    src = tmp_path / 'assigned.json'
    _write_loose_glyph_json(src, [])
    monkeypatch.setattr(mod.filedialog, 'askopenfilename', lambda **kw: str(src))
    gui.configurator_tree.selection_set('I')
    gui._on_configurator_glyph_selected()
    _wait_for_configurator_detail(gui)
    gui._configurator_assign_file()
    assert gui._configurator_overrides['I']['mode'] == 'manual'

    gui._configurator_force_all_rectilinear()

    # "Force all eligible" must never silently discard a manual assignment.
    assert gui._configurator_overrides['I'] == {'mode': 'manual', 'file': str(src)}


def test_configurator_pack_survives_kfps_export_without_a_font(tmp_path, monkeypatch):
    # The load-bearing compatibility claim: a Configurator pack built with
    # no font assigned (font_file: None in the manifest) must still export
    # to KFPS cleanly, not crash on Path(None).
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
    from gen_fabric_project import build_fabric_project

    src = tmp_path / 'blah.json'
    _write_loose_glyph_json(src, [{'type': 1048677, 'type_word': 101, 'data': [0, 0, 1, 1, 0, 0, 0],
                                    'color': [255, 255, 255, 255], 'mask': False}])

    pack_dir = tmp_path / 'out' / 'NOFONTTEST'
    pack_dir.mkdir(parents=True)
    import json as jsonlib
    manifest = {
        'format': 'forza_writer_fontpack_v2', 'font_file': None, 'prefix': 'NOFONTTEST',
        'curve_segments': 8,
        'categories': {'Uppercase': [{'char': 'A', 'codepoint': 'U+0041', 'unicode_name': 'A',
                                       'artifacts': {'json': {'file': 'A.json', 'shape_count': 1,
                                                               'strategy': 'manual', 'message': 'ok'}}}]},
    }
    (pack_dir / 'A.json').write_text(src.read_text(encoding='utf-8'), encoding='utf-8')
    (pack_dir / 'manifest.json').write_text(jsonlib.dumps(manifest), encoding='utf-8')

    project = build_fabric_project(pack_dir, log=lambda *_: None)  # must not raise
    assert len(project['shapes']) == 1




# --- chunked row insertion (large fonts must not block the GUI thread) ---

@requires_font
def test_large_glyph_set_is_not_inserted_into_the_tree_in_one_synchronous_pass(gui, tmp_path, monkeypatch):
    # A font with thousands of glyphs (a CJK font, or here a synthetic
    # stand-in so the test doesn't depend on an actual large font being
    # installed) must not insert every row in one uninterrupted loop on the
    # GUI thread, which would freeze it. Immediately after kicking off the
    # rescan -- before pumping the event loop at all -- only the first chunk
    # should exist.
    monkeypatch.setattr('glyph_overrides.OVERRIDES_PATH', tmp_path / 'glyph_overrides.json')
    monkeypatch.setattr('glyph_overrides.OVERRIDES_DIR', tmp_path)
    _configure_configurator_font(gui)
    entries = [(chr(0x4E00 + i), 'Letters') for i in range(600)]
    monkeypatch.setattr(gui, '_configurator_char_list', lambda: entries)

    gui._rescan_configurator_glyphs()

    assert len(gui.configurator_tree.get_children()) == gui._CONFIGURATOR_INSERT_CHUNK


@requires_font
def test_large_glyph_set_eventually_finishes_populating(gui, tmp_path, monkeypatch):
    monkeypatch.setattr('glyph_overrides.OVERRIDES_PATH', tmp_path / 'glyph_overrides.json')
    monkeypatch.setattr('glyph_overrides.OVERRIDES_DIR', tmp_path)
    _configure_configurator_font(gui)
    entries = [(chr(0x4E00 + i), 'Letters') for i in range(600)]
    monkeypatch.setattr(gui, '_configurator_char_list', lambda: entries)

    gui._rescan_configurator_glyphs()
    deadline = time.time() + 10
    while len(gui.configurator_tree.get_children()) < len(entries) and time.time() < deadline:
        gui.root.update()
        time.sleep(0.01)

    assert len(gui.configurator_tree.get_children()) == len(entries)
    assert set(gui.configurator_tree.get_children()) == {char for char, _cat in entries}


@requires_font
def test_a_second_rescan_started_mid_chunk_supersedes_the_first(gui, tmp_path, monkeypatch):
    # A user who reopens the workspace on a different font before the first
    # large font finishes inserting must see only the second font's glyphs,
    # not a mix of both. Row insertion guards against this with the same
    # generation-check pattern the background fit-scan uses.
    monkeypatch.setattr('glyph_overrides.OVERRIDES_PATH', tmp_path / 'glyph_overrides.json')
    monkeypatch.setattr('glyph_overrides.OVERRIDES_DIR', tmp_path)
    _configure_configurator_font(gui)
    first_entries = [(chr(0x4E00 + i), 'Letters') for i in range(600)]
    monkeypatch.setattr(gui, '_configurator_char_list', lambda: first_entries)
    gui._rescan_configurator_glyphs()
    assert len(gui.configurator_tree.get_children()) == gui._CONFIGURATOR_INSERT_CHUNK

    second_entries = [('A', 'Uppercase'), ('B', 'Uppercase'), ('C', 'Uppercase')]
    monkeypatch.setattr(gui, '_configurator_char_list', lambda: second_entries)
    gui._rescan_configurator_glyphs()

    deadline = time.time() + 10
    while time.time() < deadline:
        gui.root.update()
        time.sleep(0.01)
        if set(gui.configurator_tree.get_children()) == {'A', 'B', 'C'}:
            break

    assert set(gui.configurator_tree.get_children()) == {'A', 'B', 'C'}


@requires_font
def test_background_fit_scan_only_starts_after_every_row_exists(gui, tmp_path, monkeypatch):
    # _apply_configurator_scan_result silently drops a result for a char
    # whose row hasn't been inserted yet (configurator_tree.exists guard) --
    # so the background worker must not start until row insertion is done,
    # or fit results for later glyphs would be lost rather than merely late.
    monkeypatch.setattr('glyph_overrides.OVERRIDES_PATH', tmp_path / 'glyph_overrides.json')
    monkeypatch.setattr('glyph_overrides.OVERRIDES_DIR', tmp_path)
    _configure_configurator_font(gui)
    entries = [(chr(0x4E00 + i), 'Letters') for i in range(600)]
    monkeypatch.setattr(gui, '_configurator_char_list', lambda: entries)

    started = []
    real_start = gui._start_configurator_scan_worker
    def spy_start(entries_arg, generation, segments):
        started.append(len(gui.configurator_tree.get_children()))
        real_start(entries_arg, generation, segments)
    monkeypatch.setattr(gui, '_start_configurator_scan_worker', spy_start)

    gui._rescan_configurator_glyphs()
    deadline = time.time() + 10
    while not started and time.time() < deadline:
        gui.root.update()
        time.sleep(0.01)

    assert started == [len(entries)]
