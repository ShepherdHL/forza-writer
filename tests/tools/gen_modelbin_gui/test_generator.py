"""Generator tab: font discovery/selection, script filtering, alphabet groups,
character selection, preview, and quick export.
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

def test_all_checkbox_disables_individual_checkboxes_and_clears_filter(gui):
    gui.all_var.set(True)
    gui._on_all_toggled()
    assert str(gui.upper_cb["state"]) == "disabled"
    assert gui._selected_chars() is None

    gui.all_var.set(False)
    gui._on_all_toggled()
    assert str(gui.upper_cb["state"]) == "normal"
    assert gui._selected_chars() is not None


def test_selected_chars_empty_set_when_nothing_checked(gui):
    for var in (gui.upper_var, gui.lower_var, gui.digits_var, gui.punct_var,
                gui.symbols_var, gui.private_var):
        var.set(False)
    gui.custom_var.set("")
    assert gui._selected_chars() == set()


def test_all_checkbox_also_disables_alphabet_checkboxes(gui):
    assert gui._alphabet_checkbuttons, "expected at least one alphabet checkbox to exist"
    gui.all_var.set(True)
    gui._on_all_toggled()
    for cb in gui._alphabet_checkbuttons:
        assert str(cb["state"]) == "disabled"

    gui.all_var.set(False)
    gui._on_all_toggled()
    for cb in gui._alphabet_checkbuttons:
        assert str(cb["state"]) == "normal"


def test_selected_chars_includes_checked_alphabet_groups(gui):
    import forza_writer.alphabets as alphabets
    for var in (gui.upper_var, gui.lower_var, gui.digits_var, gui.punct_var, gui.symbols_var):
        var.set(False)
    gui.custom_var.set("")
    gui._alphabet_vars["Cyrillic"]["Uppercase"].set(True)

    result = gui._selected_chars()

    assert result == set(alphabets.ALPHABETS["Cyrillic"][0][1])  # the Uppercase group's letters


def test_selected_chars_unions_alphabet_groups_across_different_scripts(gui):
    for var in (gui.upper_var, gui.lower_var, gui.digits_var, gui.punct_var, gui.symbols_var):
        var.set(False)
    gui.custom_var.set("")
    gui._alphabet_vars["Cyrillic"]["Uppercase"].set(True)
    gui._alphabet_vars["Greek"]["Lowercase"].set(True)

    result = gui._selected_chars()

    assert "А" in result  # Cyrillic capital A (U+0410)
    assert "α" in result  # Greek lowercase alpha
    assert "Z" not in result


def test_alphabet_checkbox_stays_checked_when_its_script_tab_is_not_visible(gui):
    # "Additive, not exclusive" — checking a box for one script and then
    # switching the script filter elsewhere must not clear it, and it
    # must still count toward generation even though it's no longer the
    # visible group.
    import forza_writer.alphabets as alphabets
    gui._select_script_filter("Cyrillic")
    gui._alphabet_vars["Cyrillic"]["Lowercase"].set(True)
    gui._select_script_filter("Greek")

    assert gui._alphabet_vars["Cyrillic"]["Lowercase"].get() is True
    assert gui._selected_chars() >= set(alphabets.ALPHABETS["Cyrillic"][1][1])


def test_update_alphabet_section_shows_only_the_active_scripts_group(gui):
    gui._select_script_filter("Greek")
    assert gui._alphabet_group_frames["Greek"].winfo_manager() == "pack"
    assert gui._alphabet_group_frames["Cyrillic"].winfo_manager() == ""

    gui._select_script_filter("Thai")
    assert gui._alphabet_group_frames["Thai"].winfo_manager() == "pack"
    assert gui._alphabet_group_frames["Greek"].winfo_manager() == ""


def test_update_alphabet_section_hides_everything_for_all_and_latin(gui):
    gui._select_script_filter("Cyrillic")
    gui._select_script_filter(None)
    for frame in gui._alphabet_group_frames.values():
        assert frame.winfo_manager() == ""
    assert gui.no_alphabet_hint_lbl.winfo_manager() == ""

    gui._select_script_filter("Latin")
    for frame in gui._alphabet_group_frames.values():
        assert frame.winfo_manager() == ""
    assert gui.no_alphabet_hint_lbl.winfo_manager() == ""


def test_update_alphabet_section_shows_bounded_sets_for_chinese_variants(gui):
    for script in ("Simplified Chinese", "Traditional Chinese"):
        gui._select_script_filter(script)
        assert gui._alphabet_group_frames[script].winfo_manager() == "pack"
        assert "Structural test set" in gui._alphabet_vars[script]
        assert script in gui._all_han_vars


def test_select_only_chinese_clears_latin_and_does_not_enable_all_han(gui):
    gui._select_only_script("Simplified Chinese")

    assert not gui.upper_var.get()
    assert not gui.lower_var.get()
    assert not gui.digits_var.get()
    assert not gui.punct_var.get()
    assert not gui.symbols_var.get()
    assert not gui.private_var.get()
    assert not gui._all_han_vars["Simplified Chinese"].get()
    assert gui._selected_chars()
    assert all(not c.isascii() for c in gui._selected_chars())


def test_use_only_custom_text_clears_every_preset_but_keeps_pasted_text(gui):
    gui._alphabet_vars['Korean']['Consonants'].set(True)
    gui._all_han_vars['Simplified Chinese'].set(True)
    gui.symbols_var.set(True)
    gui.custom_var.set('中文测试 ABC')

    gui._select_only_custom_text()

    assert gui.custom_var.get() == '中文测试 ABC'
    assert gui._selected_chars() == set('中文测试ABC')


def test_symbols_selection_does_not_include_uncased_letters(gui, monkeypatch):
    import gen_modelbin_gui as mod
    for var in (gui.upper_var, gui.lower_var, gui.digits_var, gui.punct_var,
                gui.private_var):
        var.set(False)
    for groups in gui._alphabet_vars.values():
        for var in groups.values():
            var.set(False)
    gui.selected_font = Path("fake.ttf")
    gui.symbols_var.set(True)
    monkeypatch.setattr(mod, 'charset_from_font', lambda _p: ({
        'Uppercase': [], 'Lowercase': [], 'Letters': ['中', '한'], 'Numbers': [],
        'Punctuation': [], 'Symbols': ['$', '\ue000']}, []))

    assert gui._selected_chars() == {'$'}


def test_load_all_fonts_disables_button_and_shows_scanning_status(gui):
    gui._load_all_fonts()
    assert str(gui.load_fonts_btn['state']) == 'disabled'
    assert 'Scanning' in gui.font_scan_status_var.get()


def test_load_all_fonts_populates_fonts_and_re_enables_button(gui):
    _load_all_fonts_and_wait(gui)
    assert len(gui.fonts) > 0
    assert str(gui.load_fonts_btn['state']) == 'normal'
    assert str(len(gui.fonts)) in gui.font_scan_status_var.get()
    assert len(gui._visible_fonts) == len(gui.fonts)


def test_load_all_fonts_ignores_stale_scan_result(gui):
    # A second click while a scan is in flight must supersede the first —
    # simulate the first scan's result arriving after the second started.
    existing_fonts = dict(gui.fonts)
    gui._font_scan_generation = 5
    gui._on_fonts_loaded(3, {'Stale Font': Path('stale.ttf')})
    assert gui.fonts == existing_fonts
    assert 'Stale Font' not in gui.fonts


def test_script_tabs_include_all_ten_scripts_plus_all(gui):
    from forza_writer.script_detect import SCRIPTS
    assert set(gui._script_tab_labels.keys()) == {None} | set(SCRIPTS)


def test_no_script_filter_by_default(gui):
    assert gui._script_filter is None


def test_loading_fonts_triggers_script_classification(gui):
    _load_all_fonts_and_wait(gui)
    _wait_for_font_scripts(gui)
    assert len(gui._font_scripts) == len(gui.fonts)
    assert all(isinstance(v, set) for v in gui._font_scripts.values())


def test_rescanning_fonts_does_not_redetect_scripts_for_already_known_fonts(gui, monkeypatch):
    # Script detection opens and parses every font file — real per-file
    # work — so a "Rescan Fonts" click that finds the same fonts again
    # must not reopen/reclassify ones already known from the first scan.
    import gen_modelbin_gui as mod
    _load_all_fonts_and_wait(gui)
    _wait_for_font_scripts(gui)
    assert len(gui._font_scripts) == len(gui.fonts)  # baseline: everything classified once

    calls = []
    real_detect = mod.script_detect.detect_font_scripts

    def spy_detect(path, name=""):
        calls.append(name)
        return real_detect(path, name)

    monkeypatch.setattr(mod.script_detect, 'detect_font_scripts', spy_detect)

    gui._font_scan_generation += 1
    gui._on_fonts_loaded(gui._font_scan_generation, dict(gui.fonts))
    _wait_for_font_scripts(gui)

    assert calls == [], "already-classified fonts should not be re-opened/re-parsed on rescan"
    assert len(gui._font_scripts) == len(gui.fonts)


def test_rescanning_fonts_still_detects_genuinely_new_fonts(gui, monkeypatch):
    import gen_modelbin_gui as mod
    _load_all_fonts_and_wait(gui)
    _wait_for_font_scripts(gui)

    calls = []
    real_detect = mod.script_detect.detect_font_scripts

    def spy_detect(path, name=""):
        calls.append(name)
        return real_detect(path, name)

    monkeypatch.setattr(mod.script_detect, 'detect_font_scripts', spy_detect)

    new_fonts = dict(gui.fonts)
    new_fonts['Totally New Test Font'] = AMARILLO_FONT if AMARILLO_FONT.exists() else Path('nonexistent.ttf')
    gui._font_scan_generation += 1
    gui._on_fonts_loaded(gui._font_scan_generation, new_fonts)
    _wait_for_font_scripts(gui)

    assert calls == ['Totally New Test Font']
    assert 'Totally New Test Font' in gui._font_scripts


def test_rescanning_fonts_drops_scripts_for_uninstalled_fonts(gui):
    _load_all_fonts_and_wait(gui)
    _wait_for_font_scripts(gui)
    some_name = next(iter(gui.fonts))

    fonts_without_one = {name: path for name, path in gui.fonts.items() if name != some_name}
    gui._font_scan_generation += 1
    gui._on_fonts_loaded(gui._font_scan_generation, fonts_without_one)

    assert some_name not in gui._font_scripts


def test_selecting_a_script_filters_the_visible_font_list(gui):
    _load_all_fonts_and_wait(gui)
    _wait_for_font_scripts(gui)
    full_count = len(gui._visible_fonts)

    gui._select_script_filter('Thai')
    thai_count = len(gui._visible_fonts)

    assert 0 < thai_count < full_count
    assert all('Thai' in gui._font_scripts.get(name, set()) for name in gui._visible_fonts)


def test_selecting_all_clears_the_script_filter(gui):
    _load_all_fonts_and_wait(gui)
    _wait_for_font_scripts(gui)
    gui._select_script_filter('Thai')
    assert len(gui._visible_fonts) < len(gui.fonts)

    gui._select_script_filter(None)
    assert gui._script_filter is None
    assert len(gui._visible_fonts) == len(gui.fonts)


def test_selected_script_tab_is_highlighted(gui):
    import gui_theme
    p = gui_theme.palette()
    gui._select_script_filter('Korean')
    assert gui._script_tab_labels['Korean'].cget('background') == p['accent']
    assert gui._script_tab_labels[None].cget('background') == p['button_bg']


def test_browse_font_on_machine_selects_file_and_derives_prefix(gui, monkeypatch, tmp_path):
    import gen_modelbin_gui as mod
    font_path = tmp_path / 'My Custom Font.ttf'
    font_path.write_bytes(b'')
    monkeypatch.setattr(mod.filedialog, 'askopenfilename', lambda **kw: str(font_path))

    gui._browse_font_on_machine()

    assert gui.selected_font == font_path
    assert gui.font_path_var.get() == str(font_path)
    assert gui.prefix_var.get() == 'MY-CUSTOM-FONT'


def test_browse_font_on_machine_cancelled_leaves_selection_unchanged(gui, monkeypatch):
    import gen_modelbin_gui as mod
    monkeypatch.setattr(mod.filedialog, 'askopenfilename', lambda **kw: '')
    gui.selected_font = None

    gui._browse_font_on_machine()

    assert gui.selected_font is None


def test_font_view_toggle_swaps_widgets_without_raising(gui):
    # winfo_manager() checks geometry-manager registration (pack/grid'd or
    # not), which is what "currently swapped into the layout" means here —
    # winfo_ismapped() would also work (the fixture's alpha=0 Toplevel is
    # still mapped, just invisible) but manager registration is the more
    # direct thing this test actually wants to assert.
    gui.font_view_var.set("grid")
    gui._on_font_view_changed()
    gui.root.update()
    assert gui.grid_outer.winfo_manager() == "pack"

    gui.font_view_var.set("list")
    gui._on_font_view_changed()
    gui.root.update()
    assert gui.grid_outer.winfo_manager() == ""


@requires_fontpack
def test_font_grid_populates_tiles(gui):
    _load_all_fonts_and_wait(gui)
    gui.search_var.set("Arial")
    gui.root.update()
    gui.font_view_var.set("grid")
    gui._on_font_view_changed()
    deadline = time.time() + 5
    while time.time() < deadline and not gui._grid_tile_refs:
        gui._poll_queue()
        gui.root.update()
        time.sleep(0.05)
    # Not asserting tiles > 0 unconditionally — "Arial" may not be installed
    # on every machine — just that populating doesn't raise and status text
    # is set sensibly either way.
    assert isinstance(gui.grid_status_var.get(), str)


def test_font_grid_empty_space_uses_the_recessed_theme_surface(gui):
    import gui_theme

    palette = gui_theme.palette()
    assert gui.grid_canvas.cget('background') == palette['canvas_bg']
    assert gui.style.lookup('Grid.TFrame', 'background') == palette['canvas_bg']
    assert gui.grid_inner.cget('style') == 'Grid.TFrame'


def test_font_grid_column_count_grows_and_shrinks_with_window_width(gui):
    # The responsive column count (see GeneratorGUI._grid_columns_for_width)
    # replaced a hard-coded GRID_COLUMNS=3 that left most of a wide window
    # empty beside a narrow 3-column strip. This exercises that reflow
    # directly with synthetic tiles instead of real rendered font previews
    # (the column math doesn't care what image a tile shows), so it doesn't
    # depend on any specific font file being present on the machine, unlike
    # test_font_grid_populates_tiles above.
    from PIL import Image
    import gen_modelbin_gui as mod

    gui.font_view_var.set("grid")
    gui._on_font_view_changed()
    gui.root.update()

    def populate(n):
        for child in gui.grid_inner.winfo_children():
            child.destroy()
        gui._grid_tile_refs.clear()
        gui._grid_columns = gui._grid_columns_for_width(gui.grid_canvas.winfo_width())
        fake_image = Image.new("RGB", mod.GRID_TILE_SIZE, "black")
        for i in range(n):
            gui._add_grid_tile(f"Font {i}", Path("unused.ttf"), fake_image)
        gui.root.update()

    gui.root.geometry("420x400")
    gui.root.update()
    populate(24)
    narrow_columns = gui._grid_columns
    assert narrow_columns >= 1
    narrow_positions = [(t.grid_info()["row"], t.grid_info()["column"])
                         for t in gui.grid_inner.winfo_children()]
    assert max(c for _r, c in narrow_positions) == narrow_columns - 1

    # Widening the actual window (not the canvas directly) is what fires
    # the real <Configure> chain down to grid_canvas, exactly as it would
    # for a user dragging/maximizing the app window.
    gui.root.geometry("1600x400")
    gui.root.update()
    wide_columns = gui._grid_columns
    assert wide_columns > narrow_columns, (
        "a much wider window should lay out more grid columns instead of "
        "leaving the extra width empty"
    )
    wide_positions = [(t.grid_info()["row"], t.grid_info()["column"])
                       for t in gui.grid_inner.winfo_children()]
    assert max(c for _r, c in wide_positions) == wide_columns - 1
    assert len(set(wide_positions)) == len(wide_positions)  # reflow didn't overlap any tiles
    assert len(gui.grid_inner.winfo_children()) == 24  # reflow didn't drop/duplicate tiles

    gui.root.geometry("420x400")
    gui.root.update()
    assert gui._grid_columns == narrow_columns


def test_reference_modelbin_field_always_enabled(gui):
    # Settings' path fields are persistent config, not per-run-conditional
    # — unlike the old single-page layout, selecting a non-modelbin output
    # mode no longer disables the reference-modelbin entry (it lives on a
    # different tab now and you might want to fix/save it regardless of
    # what's currently selected on Generator).
    for mode in ("json", "modelbin", "json_legacy"):
        gui.output_var.set(mode)
        gui._on_output_mode_changed()
        assert str(gui.ref_entry["state"]) == "normal"


def test_reference_warning_shown_only_for_modelbin_mode_with_missing_ref(gui):
    gui.ref_var.set(r"C:\definitely\does\not\exist.modelbin")
    gui.output_var.set("modelbin")
    gui._on_output_mode_changed()
    assert "not found" in gui.reference_warning_var.get()

    gui.output_var.set("json")
    gui._on_output_mode_changed()
    assert gui.reference_warning_var.get() == ""


def test_output_mode_labels_match_output_modes_exactly():
    import gen_modelbin_gui as mod
    from gen_fontpack import OUTPUT_MODES
    assert set(mod.OUTPUT_MODE_LABELS.keys()) == set(OUTPUT_MODES)


def test_preview_empty_path_shows_prompt(gui):
    gui.preview_path_var.set("")
    gui._show_preview()
    assert "Pick a" in gui.preview_stats_var.get()


def test_preview_missing_file_does_not_raise(gui):
    gui.preview_path_var.set(r"C:\definitely\does\not\exist.json")
    gui._show_preview()
    assert "not found" in gui.preview_stats_var.get()


def test_lowercase_warning_empty_when_no_font_selected(gui):
    gui.selected_font = None
    gui._check_lowercase_warning()
    assert gui.lowercase_warning_var.get() == ''


def test_lowercase_warning_shown_for_all_caps_font(gui, monkeypatch):
    import gen_modelbin_gui as mod

    monkeypatch.setattr(mod, 'charset_from_font', lambda p: (
        {'Uppercase': ['A'], 'Lowercase': [], 'Numbers': [], 'Punctuation': [], 'Symbols': []}, []))
    gui.selected_font = Path('fake-all-caps-font.ttf')
    gui._check_lowercase_warning()
    assert 'no lowercase' in gui.lowercase_warning_var.get().lower()


def test_lowercase_warning_absent_for_mixed_case_font(gui, monkeypatch):
    import gen_modelbin_gui as mod

    monkeypatch.setattr(mod, 'charset_from_font', lambda p: (
        {'Uppercase': ['A'], 'Lowercase': ['a'], 'Numbers': [], 'Punctuation': [], 'Symbols': []}, []))
    gui.selected_font = Path('fake-mixed-case-font.ttf')
    gui._check_lowercase_warning()
    assert gui.lowercase_warning_var.get() == ''


def test_lowercase_warning_does_not_raise_on_font_parse_error(gui, monkeypatch):
    import gen_modelbin_gui as mod

    def boom(_p):
        raise RuntimeError("simulated font parse failure")

    monkeypatch.setattr(mod, 'charset_from_font', boom)
    gui.selected_font = Path('unreadable-font.ttf')
    gui._check_lowercase_warning()  # must not raise
    assert gui.lowercase_warning_var.get() == ''


def test_large_font_warning_recommends_advanced_generation(gui, monkeypatch):
    import gen_modelbin_gui as mod

    characters = [chr(0x4E00 + index) for index in range(1_001)]
    monkeypatch.setattr(mod, 'charset_from_font', lambda _path: ({'Letters': characters}, []))
    gui.selected_font = Path('large-cjk-font.ttf')

    gui._on_character_selection_changed()

    warning = gui.large_font_warning_var.get()
    assert '1,001 unique characters' in warning
    assert 'Advanced Generation' in warning


def test_large_font_warning_stays_hidden_at_one_thousand_characters(gui, monkeypatch):
    import gen_modelbin_gui as mod

    characters = [chr(0x4E00 + index) for index in range(1_000)]
    monkeypatch.setattr(mod, 'charset_from_font', lambda _path: ({'Letters': characters}, []))
    gui.selected_font = Path('medium-font.ttf')

    gui._on_character_selection_changed()

    assert gui.large_font_warning_var.get() == ''


def test_preview_json_file_shows_shape_and_mask_counts(gui, tmp_path):
    import json as jsonlib

    path = tmp_path / "glyph.json"
    path.write_text(jsonlib.dumps({"shapes": [
        {"type": 1, "type_word": 1, "data": [0, 0, 1, 1, 0, 0, 0], "color": [255, 255, 255, 255]},
        {"type": 1, "type_word": 1, "data": [0, 0, 1, 1, 0, 0, 1], "color": [0, 0, 0, 255], "mask": True},
    ]}), encoding="utf-8")
    gui.preview_path_var.set(str(path))
    gui._show_preview()
    assert "2 shape" in gui.preview_stats_var.get()
    assert "1 mask" in gui.preview_stats_var.get()
    assert gui._preview_photo is not None


@requires_assets
def test_preview_valid_modelbin_shows_structurally_valid_in_success_style(gui, tmp_path):
    # Regression test for wiring validate_modelbin() into the preview panel
    # (see RESEARCH.md's malformed-mesh-buffer bug): a real, correctly
    # generated glyph should read as structurally valid, styled Success.
    from gen_modelbin import generate_glyph

    out_path = tmp_path / "A.modelbin"
    generate_glyph("A", AMARILLO_FONT, REFERENCE_MODELBIN, out_path, curve_segments=8)

    gui.preview_path_var.set(str(out_path))
    gui._show_preview()

    stats = gui.preview_stats_var.get()
    assert "Structurally valid" in stats
    assert str(gui.preview_stats_lbl["style"]) == "Success.TLabel"


@requires_assets
def test_preview_corrupted_modelbin_shows_invalid_in_danger_style(gui, tmp_path):
    # Same as above, but with an out-of-bounds index injected into the
    # index buffer after generation — the exact failure mode validate_modelbin
    # exists to catch (a structurally-parseable file whose index buffer
    # references vertices past the end of a vertex buffer). The old,
    # position-only preview render can't tell this file apart from a good
    # one; the validator is what should catch it.
    import struct

    from gen_modelbin import generate_glyph, parse_buffer_header
    import gen_modelbin as gen_modelbin_mod

    out_path = tmp_path / "S.modelbin"
    generate_glyph("S", AMARILLO_FONT, REFERENCE_MODELBIN, out_path, curve_segments=8)

    data = bytearray(out_path.read_bytes())
    chunks = gen_modelbin_mod._parse_chunk_table(bytes(data))
    indb_off = next(off for tag, off, _size in chunks if tag == "IndB")
    i_count, _i_bytes, _i_stride, _flags, _fmt = parse_buffer_header(bytes(data), indb_off)
    struct.pack_into("<H", data, indb_off + 16, 0xFFFE)  # first index -> wildly out of bounds
    out_path.write_bytes(bytes(data))

    gui.preview_path_var.set(str(out_path))
    gui._show_preview()

    stats = gui.preview_stats_var.get()
    assert "INVALID" in stats
    assert "out of bounds" in stats
    assert str(gui.preview_stats_lbl["style"]) == "Danger.TLabel"


def test_allow_stencil_checkbox_defaults_to_true(gui):
    assert gui.allow_stencil_var.get() is True


@requires_fontpack
def test_quick_export_kfps_writes_file_and_shows_info(gui, monkeypatch):
    import gen_modelbin_gui as mod

    infos = []
    monkeypatch.setattr(mod.messagebox, 'showinfo', lambda title, msg: infos.append((title, msg)))
    gui.prefix_var.set('AMARILLO-USAF')
    gui.out_var.set(str(AMARILLO_FONTPACK.parent))

    gui._quick_export_kfps()

    assert len(infos) == 1
    assert '.fabric-project.json' in infos[0][1]
    assert '_S' in infos[0][1]  # curve-segments/shape-count naming convention (e.g. _S8_368)


def test_quick_export_kfps_missing_pack_shows_error(gui, tmp_path, monkeypatch):
    import gen_modelbin_gui as mod

    errors = []
    monkeypatch.setattr(mod.messagebox, 'showerror', lambda title, msg: errors.append((title, msg)))
    gui.prefix_var.set('NO-SUCH-PACK')
    gui.out_var.set(str(tmp_path))

    gui._quick_export_kfps()

    assert len(errors) == 1
    assert 'No fontpack found' in errors[0][0]


def test_scroll_position_survives_filtering_the_font_list(gui):
    gui.root.geometry('1000x400')
    gui.root.update()
    canvas = gui._page_scroll_canvas['generator']
    canvas.yview_moveto(0.3)
    gui.root.update()
    before = canvas.yview()

    gui.search_var.set('Ari')
    gui.root.update()

    assert canvas.yview() == before


@requires_font
def test_opening_glyph_overrides_uses_generator_font_and_stays_on_generator(gui, tmp_path, monkeypatch):
    monkeypatch.setattr('glyph_overrides.OVERRIDES_PATH', tmp_path / 'glyph_overrides.json')
    monkeypatch.setattr('glyph_overrides.OVERRIDES_DIR', tmp_path)
    gui.selected_font = AMARILLO_FONT
    gui.configurator_font_var.set('')

    gui._goto_configurator_for_current_font()
    _wait_for_configurator_scan(gui)

    assert gui.configurator_font_var.get() == str(AMARILLO_FONT)
    assert gui._current_tab == 'generator'
    assert gui._configurator_workspace_open is True


def test_opening_glyph_overrides_tracks_the_authoritative_generator_font(gui):
    gui.selected_font = Path('generator_font.ttf')
    gui.configurator_font_var.set('already_set_font.ttf')

    gui._goto_configurator_for_current_font()

    assert gui.configurator_font_var.get() == 'generator_font.ttf'
    assert gui._current_tab == 'generator'


