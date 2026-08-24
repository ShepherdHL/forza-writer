"""Window chrome and generation orchestration shared across tabs: startup, theme,
sidebar/tab switching, scroll shell, log panel, and batch start/halt/abort.
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

def test_theme_applied_at_startup_matches_the_selected_palette(gui):
    import gui_theme
    assert gui.root.cget('bg') == gui_theme.PALETTE['bg']


def test_window_title_is_just_forza_writer(gui):
    assert gui.root.title() == 'Forza Writer'


def test_elevated_startup_logs_that_the_gui_does_not_need_admin(gui, monkeypatch):
    import gen_modelbin_gui as mod

    monkeypatch.setattr(mod, 'is_running_as_administrator', lambda: True)
    gui._log_startup_elevation_notice()

    text = gui.log.get('1.0', 'end-1c')
    assert 'Administrator mode detected' in text
    assert 'does not require Administrator mode for normal operation' in text
    assert 'process-memory diagnostics may require elevation' in text


def test_normal_startup_does_not_log_an_admin_notice(gui, monkeypatch):
    import gen_modelbin_gui as mod

    before = gui.log.get('1.0', 'end-1c')
    monkeypatch.setattr(mod, 'is_running_as_administrator', lambda: False)
    gui._log_startup_elevation_notice()

    assert gui.log.get('1.0', 'end-1c') == before


def test_variable_worker_uses_axis_safe_prefix_and_instance_overrides(gui, tmp_path, monkeypatch):
    import gen_modelbin_gui as mod
    instance_path = tmp_path / 'regular-instance.ttf'
    instance_path.write_bytes(b'instance')
    source_path = tmp_path / 'source-vf.ttf'
    source_path.write_bytes(b'source')
    monkeypatch.setattr(mod, 'instantiate_font',
                        lambda source, coordinates: instance_path)
    monkeypatch.setattr(gui, '_resolve_overrides_for_generation',
                        lambda path: ({'中': 'never'}, None) if path == instance_path else (None, None))
    captured = {}

    def fake_build(font_path, out_dir, prefix, output, reference, segments, **kwargs):
        captured.update(font_path=font_path, prefix=prefix, kwargs=kwargs)
        return {'summary': {'json': {'generated': 0, 'failed': 0}, 'skipped': 0},
                'files_written': []}

    monkeypatch.setattr(mod, 'build_fontpack', fake_build)
    variation = {'named_instance': 'Regular', 'coordinates': {'wght': 400}}

    gui._run_batch(source_path, tmp_path, 'NOTO-TC', 'json', None, 8, {'中'},
                   compute_backend='cpu', variation=variation)

    assert captured['font_path'] == instance_path
    assert captured['prefix'] == 'NOTO-TC-WGHT400'
    assert captured['kwargs']['source_font_path'] == source_path
    assert captured['kwargs']['variation'] == variation
    assert captured['kwargs']['mask_overrides'] == {'中': 'never'}


def test_log_applies_the_requested_tag_to_just_that_line(gui):
    gui._log('a neutral line')
    gui._log('a problem line', tag='warn')
    # The warn-tagged line (and only that line) carries the 'warn' tag.
    warn_line_start = gui.log.search('a problem line', '1.0', 'end')
    assert 'warn' in gui.log.tag_names(warn_line_start)
    neutral_line_start = gui.log.search('a neutral line', '1.0', 'end')
    assert gui.log.tag_names(neutral_line_start) == ()


def test_log_tag_colors_match_the_semantic_palette_roles(gui):
    import gui_theme
    p = gui_theme.palette()
    for tag, role in (('danger', 'danger'), ('warn', 'warn'), ('success', 'success')):
        assert gui.log.tag_cget(tag, 'foreground') == p[role]


def test_start_batch_without_a_font_logs_a_warn_tagged_line(gui):
    gui.selected_font = None
    gui._start_batch()
    line_start = gui.log.search('Select a font first.', '1.0', 'end')
    assert 'warn' in gui.log.tag_names(line_start)


@pytest.mark.skipif(sys.platform != 'win32', reason='window icon verification is Windows-only')
def test_window_icon_is_actually_applied(gui):
    # A missing/failed iconbitmap() call is swallowed silently by design
    # (cosmetic, must never block the app) — so "no exception" alone
    # doesn't prove the icon actually applied. WM_GETICON is the real
    # signal: it returns a null handle when no icon was set.
    import ctypes
    gui.root.deiconify()
    gui.root.update()
    hwnd = ctypes.windll.user32.GetParent(gui.root.winfo_id())
    WM_GETICON = 0x007F
    icon_handle = ctypes.windll.user32.SendMessageW(hwnd, WM_GETICON, 0, 0)
    assert icon_handle != 0
    gui.root.withdraw()


def test_large_generation_requires_confirmation_before_start(gui, monkeypatch):
    import gen_modelbin_gui as mod
    gui.selected_font = Path('large-cjk.ttf')
    gui.all_var.set(True)
    letters = [chr(0x4E00 + i) for i in range(500)]
    monkeypatch.setattr(mod, 'charset_from_font', lambda _p: ({
        'Uppercase': [], 'Lowercase': [], 'Letters': letters, 'Numbers': [],
        'Punctuation': [], 'Symbols': []}, []))
    confirmations = []
    monkeypatch.setattr(mod.messagebox, 'askyesno',
                        lambda title, message: confirmations.append((title, message)) or False)
    starts = []
    monkeypatch.setattr(gui, '_start_generation', lambda **kwargs: starts.append(kwargs))

    gui._start_batch()

    assert confirmations
    assert '500 glyphs' in confirmations[0][1]
    assert starts == []


def test_start_batch_confirms_before_generating_from_a_variable_font(gui, tmp_path, monkeypatch):
    # A variable font passed straight to the normal Generator gets whatever
    # raw, un-instantiated master fontTools happens to extract — never a
    # style the user actually chose (only Advanced Generator pins one via
    # instantiate_font). This must be caught and confirmed before the batch
    # starts, not discovered afterward in the output.
    import gen_modelbin_gui as mod
    from forza_writer.variable_fonts import NamedInstance, VariableFontInfo, VariationAxis

    font_path = tmp_path / 'variable.ttf'
    font_path.write_bytes(b'placeholder')
    info = VariableFontInfo(
        (VariationAxis('wght', 'Weight', 100, 100, 900),),
        (NamedInstance('Thin', {'wght': 100}), NamedInstance('Regular', {'wght': 400})))
    monkeypatch.setattr(mod, 'inspect_variable_font', lambda _path: info)
    gui.selected_font = font_path
    confirmations = []
    monkeypatch.setattr(mod.messagebox, 'askyesno',
                        lambda title, message: confirmations.append((title, message)) or False)
    starts = []
    monkeypatch.setattr(gui, '_start_generation', lambda **kwargs: starts.append(kwargs))

    gui._start_batch()

    assert confirmations
    assert 'variable font' in confirmations[0][1].lower()
    assert '2 named' in confirmations[0][1]
    assert 'Advanced Generator' in confirmations[0][1]
    assert starts == []


def test_start_batch_skips_variable_font_confirmation_for_a_static_font(gui, tmp_path, monkeypatch):
    import gen_modelbin_gui as mod
    from forza_writer.variable_fonts import VariableFontInfo

    font_path = tmp_path / 'static.ttf'
    font_path.write_bytes(b'placeholder')
    monkeypatch.setattr(mod, 'inspect_variable_font', lambda _path: VariableFontInfo((), ()))
    monkeypatch.setattr(mod, 'charset_from_font', lambda _p: ({
        'Uppercase': ['A'], 'Lowercase': [], 'Letters': [], 'Numbers': [],
        'Punctuation': [], 'Symbols': []}, []))
    gui.selected_font = font_path
    confirmations = []
    monkeypatch.setattr(mod.messagebox, 'askyesno',
                        lambda title, message: confirmations.append((title, message)) or True)
    starts = []
    monkeypatch.setattr(gui, '_start_generation', lambda **kwargs: starts.append(kwargs))

    gui._start_batch()

    assert confirmations == []
    assert len(starts) == 1


def test_fonts_load_automatically_at_startup(gui):
    # The font list used to require an explicit "Load All Fonts" click —
    # now __init__ kicks off the scan itself, so waiting on the queue
    # (without calling _load_all_fonts again) is enough to see it land.
    deadline = time.time() + 15
    while not gui.fonts and time.time() < deadline:
        gui._poll_queue()
        gui.root.update()
        time.sleep(0.05)
    gui._poll_queue()
    gui.root.update()
    assert len(gui.fonts) > 0
    assert str(gui.load_fonts_btn['state']) == 'normal'
    assert str(len(gui.fonts)) in gui.font_scan_status_var.get()


def test_font_script_detected_message_updates_state_incrementally(gui):
    gui._font_scan_generation = 1
    gui.fonts = {'Fake Font': Path('fake.ttf')}
    gui.msg_queue.put(('font_script_detected', 1, 'Fake Font', {'Latin'}))
    gui._poll_queue()
    assert gui._font_scripts['Fake Font'] == {'Latin'}


def test_font_script_detected_message_ignored_for_stale_generation(gui):
    gui._font_scan_generation = 5
    gui.msg_queue.put(('font_script_detected', 3, 'Stale Font', {'Latin'}))
    gui._poll_queue()
    assert 'Stale Font' not in gui._font_scripts


@requires_font
def test_start_batch_threads_allow_stencil_into_worker_args(gui, tmp_path, monkeypatch):
    _configure_single_char_batch(gui, 'A', 'STENCILARG', tmp_path)
    gui.allow_stencil_var.set(False)

    captured = {}
    real_run_batch = gui._run_batch

    def spy_run_batch(*args, **kwargs):
        captured['args'] = args
        return real_run_batch(*args, **kwargs)

    monkeypatch.setattr(gui, '_run_batch', spy_run_batch)
    gui._start_batch()
    _wait_for_worker(gui)

    assert captured['args'][-4] is False  # allow_stencil; overrides and compute backend trail it


@requires_font
def test_halt_abort_buttons_disabled_before_batch_starts(gui):
    assert str(gui.halt_btn['state']) == 'disabled'
    assert str(gui.abort_btn['state']) == 'disabled'


@requires_font
def test_halt_abort_buttons_enable_during_batch_and_disable_when_done(gui, tmp_path):
    _configure_single_char_batch(gui, 'A', 'HALTBTN', tmp_path)
    gui._start_batch()
    gui.root.update()
    assert str(gui.halt_btn['state']) == 'normal'
    assert str(gui.abort_btn['state']) == 'normal'
    _wait_for_worker(gui)
    assert str(gui.halt_btn['state']) == 'disabled'
    assert str(gui.abort_btn['state']) == 'disabled'


@requires_font
def test_halt_keeps_partial_pack(gui, tmp_path):
    gui.custom_var.set('ABCDE')
    _configure_single_char_batch(gui, 'ABCDE', 'HALTKEEP', tmp_path)
    gui._start_batch()
    gui.root.update()
    time.sleep(0.2)
    gui._halt_batch()
    _wait_for_worker(gui)

    manifest_path = _profiled_gui_pack_dir(gui, tmp_path, 'HALTKEEP') / 'manifest.json'
    assert manifest_path.exists()
    import json as jsonlib
    manifest = jsonlib.loads(manifest_path.read_text(encoding='utf-8'))
    assert manifest.get('halted') is True
    total_glyphs = sum(len(v) for v in manifest['categories'].values())
    assert 0 < total_glyphs < 5  # stopped partway through, not all 5 chars


@requires_font
def test_abort_removes_files_written_this_run(gui, tmp_path):
    gui.custom_var.set('ABCDE')
    _configure_single_char_batch(gui, 'ABCDE', 'ABORTKEEP', tmp_path)
    gui._start_batch()
    gui.root.update()
    time.sleep(0.2)
    gui._abort_batch()
    _wait_for_worker(gui)

    pack_dir = _profiled_gui_pack_dir(gui, tmp_path, 'ABORTKEEP')
    assert not (pack_dir / 'manifest.json').exists()
    remaining_files = [p for p in pack_dir.rglob('*') if p.is_file()] if pack_dir.exists() else []
    assert remaining_files == []


@requires_font
def test_live_preview_updates_during_generation(gui, tmp_path):
    _configure_single_char_batch(gui, 'A', 'LIVEPREVIEW', tmp_path)
    gui._start_batch()
    _wait_for_worker(gui)
    assert gui._live_glyph_count >= 1
    assert 'Generating' in gui.live_preview_stats_var.get() or gui._live_preview_photo is not None


def test_all_tabs_exist_after_ascii_art_addition():
    import gen_modelbin_gui as mod
    assert mod.TABS == [
        'forza_font_text', 'generator', 'advanced', 'direct', 'ascii_art', 'glyph_inspector',
        'layer_effects', 'outputs', 'composer', 'settings', 'credits']


def test_every_tab_has_its_own_primary_scroll_canvas(gui):
    # Every page must own exactly one primary vertical scroll region —
    # before this, only Generator had one at all, so Outputs/
    # Composer/Settings content that didn't fit was just silently clipped
    # with no way to reach it.
    import gen_modelbin_gui as mod
    for name in mod.TABS:
        assert name in gui._page_scroll_canvas, f'{name} has no primary scroll canvas'
        assert isinstance(gui._page_scroll_canvas[name], tk.Canvas)


def test_scroll_position_survives_switching_tabs_away_and_back(gui):
    gui.root.geometry('1000x400')  # force real overflow so yview has room to move
    gui.root.update()
    canvas = gui._page_scroll_canvas['generator']
    canvas.yview_moveto(0.3)
    gui.root.update()
    before = canvas.yview()

    gui._show_tab('outputs')
    gui.root.update()
    gui._show_tab('generator')
    gui.root.update()

    assert canvas.yview() == before


def test_expected_widgets_are_registered_as_independent_scroll_regions(gui):
    # The font list, font grid, Log, Outputs' two lists, and the Compose
    # text box all scroll themselves — each must opt out of the page-level
    # wheel routing via _register_independent_scroll (see _on_mousewheel).
    expected = {
        gui.font_list, gui.grid_canvas, gui.log,
        gui.outputs_pack_listbox, gui.outputs_glyph_listbox,
        gui.compose_text_widget,
    }
    assert expected <= gui._independent_scroll_widgets


def test_mousewheel_over_font_list_scrolls_the_list_not_the_page(gui, monkeypatch):
    # This is the exact bug a prior pass shipped: font_list was missing
    # from the exclusion set, so hovering it and scrolling moved *both*
    # the listbox and the outer Generator page canvas at once.
    gui._show_tab('generator')
    monkeypatch.setattr(gui.root, 'winfo_containing', lambda x, y: gui.font_list)
    page_canvas = gui._page_scroll_canvas['generator']
    calls = []
    monkeypatch.setattr(page_canvas, 'yview_scroll', lambda *a, **k: calls.append((a, k)))

    event = type('Event', (), {'x_root': 0, 'y_root': 0, 'delta': 120})()
    gui._on_mousewheel(event)

    assert calls == []


def test_mousewheel_over_plain_page_content_scrolls_the_page_canvas(gui, monkeypatch):
    gui._show_tab('generator')
    plain_widget = gui.load_fonts_btn  # not independently scrollable
    monkeypatch.setattr(gui.root, 'winfo_containing', lambda x, y: plain_widget)
    page_canvas = gui._page_scroll_canvas['generator']
    calls = []
    monkeypatch.setattr(page_canvas, 'yview_scroll', lambda *a, **k: calls.append((a, k)))

    event = type('Event', (), {'x_root': 0, 'y_root': 0, 'delta': 120})()
    gui._on_mousewheel(event)
    gui._flush_page_scroll()

    assert len(calls) == 1


def test_mousewheel_burst_is_coalesced_into_one_canvas_update(gui, monkeypatch):
    gui._show_tab('generator')
    monkeypatch.setattr(gui.root, 'winfo_containing', lambda _x, _y: gui.load_fonts_btn)
    page_canvas = gui._page_scroll_canvas['generator']
    calls = []
    scheduled = []
    monkeypatch.setattr(page_canvas, 'yview_scroll', lambda *args: calls.append(args))
    monkeypatch.setattr(gui.root, 'after', lambda delay, callback: scheduled.append((delay, callback)) or 'job')

    event = type('Event', (), {'x_root': 0, 'y_root': 0, 'delta': -120})()
    for _ in range(5):
        gui._on_mousewheel(event)

    assert len(scheduled) == 1
    assert scheduled[0][0] == gui._WHEEL_FRAME_MS
    assert calls == []
    scheduled[0][1]()
    assert len(calls) == 1
    assert calls[0][0] > 0


def test_precision_wheel_deltas_accumulate_instead_of_rounding_to_zero(gui, monkeypatch):
    gui._show_tab('generator')
    monkeypatch.setattr(gui.root, 'winfo_containing', lambda _x, _y: gui.load_fonts_btn)
    page_canvas = gui._page_scroll_canvas['generator']
    calls = []
    monkeypatch.setattr(page_canvas, 'yview_scroll', lambda *args: calls.append(args))
    monkeypatch.setattr(gui.root, 'after', lambda _delay, _callback: 'job')

    event = type('Event', (), {'x_root': 0, 'y_root': 0, 'delta': -20})()
    gui._on_mousewheel(event)
    gui._flush_page_scroll()

    assert calls == [(1, 'units')]


def test_primary_pages_use_a_small_fixed_pixel_scroll_increment(gui):
    for canvas in gui._page_scroll_canvas.values():
        assert int(float(canvas.cget('yscrollincrement'))) == gui._PAGE_SCROLL_INCREMENT


def test_page_up_down_scrolls_the_current_tabs_canvas_by_pages(gui, monkeypatch):
    gui._show_tab('generator')
    monkeypatch.setattr(gui.root, 'focus_get', lambda: gui.load_fonts_btn)
    page_canvas = gui._page_scroll_canvas['generator']
    calls = []
    monkeypatch.setattr(page_canvas, 'yview_scroll', lambda *a, **k: calls.append(a))

    gui._on_page_key(type('Event', (), {'keysym': 'Prior'})())
    gui._on_page_key(type('Event', (), {'keysym': 'Next'})())

    assert calls == [(-1, 'pages'), (1, 'pages')]


def test_page_up_down_does_not_hijack_focus_inside_an_independent_scroll_widget(gui, monkeypatch):
    # font_list has its own native Page Up/Down handling as a focusable
    # Listbox — the page canvas must not also move underneath it.
    gui._show_tab('generator')
    monkeypatch.setattr(gui.root, 'focus_get', lambda: gui.font_list)
    page_canvas = gui._page_scroll_canvas['generator']
    calls = []
    monkeypatch.setattr(page_canvas, 'yview_scroll', lambda *a, **k: calls.append(a))

    gui._on_page_key(type('Event', (), {'keysym': 'Prior'})())

    assert calls == []


def test_home_end_are_not_globally_rebound(gui):
    # Deliberately not implemented at the root level — Entry/Text widgets
    # already use Home/End to jump the text cursor, and rebinding them
    # globally would fire both the page-scroll and the text-cursor jump
    # on every press while typing.
    assert gui.root.bind_all('<Home>') in ('', None)
    assert gui.root.bind_all('<End>') in ('', None)


def test_mousewheel_over_outputs_listboxes_does_not_scroll_the_outputs_page(gui, monkeypatch):
    gui._show_tab('outputs')
    for widget in (gui.outputs_pack_listbox, gui.outputs_glyph_listbox):
        monkeypatch.setattr(gui.root, 'winfo_containing', lambda x, y, w=widget: w)
        page_canvas = gui._page_scroll_canvas['outputs']
        calls = []
        monkeypatch.setattr(page_canvas, 'yview_scroll', lambda *a, **k: calls.append((a, k)))
        event = type('Event', (), {'x_root': 0, 'y_root': 0, 'delta': 120})()
        gui._on_mousewheel(event)
        assert calls == [], f'{widget} did not exclude itself from page scrolling'


def test_log_has_both_vertical_and_horizontal_scrollbars(gui):
    # wrap='none' keeps each log line on one line, which means a long
    # line (a full file path in a "--- Done: ... -> C:\...\...json ---"
    # message) needs a horizontal scrollbar to actually be reachable.
    siblings = gui.log.master.winfo_children()
    scrollbars = [w for w in siblings if isinstance(w, ttk.Scrollbar)]
    orients = {str(sb.cget('orient')) for sb in scrollbars}
    assert orients == {'vertical', 'horizontal'}


def test_scrollable_widgets_have_a_gutter_before_their_scrollbar(gui):
    import gui_theme
    for widget in (gui.font_list, gui.grid_canvas):
        info = widget.pack_info()
        padx = info.get('padx', 0)
        # ttk normalizes a (0, N) padx tuple to a two-item tuple/list
        right_pad = padx[1] if isinstance(padx, (tuple, list)) else padx
        assert int(right_pad) >= gui_theme.SCROLLBAR_GUTTER


def test_show_tab_packs_only_the_selected_page(gui):
    for name in ('outputs', 'composer', 'settings', 'generator'):
        gui._show_tab(name)
        gui.root.update()
        assert gui._pages[name].winfo_manager() == 'pack'
        for other, page in gui._pages.items():
            if other != name:
                assert page.winfo_manager() == '', f'{other} still packed while {name} is active'


def test_show_tab_highlights_selected_sidebar_label(gui):
    # The active tab is signaled by a left-edge accent indicator strip +
    # a lifted row background, not a full solid-accent fill across the
    # row (that reads as a button, not nav chrome) — see _style_sidebar.
    import gui_theme
    p = gui_theme.palette()
    gui._show_tab('outputs')
    assert gui._tab_indicators['outputs'].cget('background') == p['accent']
    assert gui._tab_rows['outputs'].cget('background') == p['panel_alt']
    assert gui._tab_indicators['generator'].cget('background') == p['bg']
    assert gui._tab_rows['generator'].cget('background') == p['bg']


def test_sidebar_hover_tints_unselected_rows_only(gui):
    import gui_theme
    p = gui_theme.palette()
    gui._show_tab('generator')

    gui._on_tab_hover('outputs', True)
    assert gui._tab_rows['outputs'].cget('background') == p['frame_light']
    gui._on_tab_hover('outputs', False)
    assert gui._tab_rows['outputs'].cget('background') == p['bg']

    # Hovering the already-selected tab must not disturb its own look.
    gui._on_tab_hover('generator', True)
    assert gui._tab_rows['generator'].cget('background') == p['panel_alt']


@requires_font
def test_start_batch_threads_saved_overrides_into_worker_args(gui, tmp_path, monkeypatch):
    monkeypatch.setattr('glyph_overrides.OVERRIDES_PATH', tmp_path / 'glyph_overrides.json')
    monkeypatch.setattr('glyph_overrides.OVERRIDES_DIR', tmp_path)
    import glyph_overrides
    glyph_overrides.save_overrides_for_font(
        AMARILLO_FONT, {'A': {'mode': 'never'}, 'B': {'mode': 'manual', 'file': 'b.json'}})
    _configure_single_char_batch(gui, 'A', 'MASKOVERRIDEARG', tmp_path)

    captured = {}
    real_run_batch = gui._run_batch

    def spy_run_batch(*args, **kwargs):
        captured['args'] = args
        return real_run_batch(*args, **kwargs)

    monkeypatch.setattr(gui, '_run_batch', spy_run_batch)
    gui._start_batch()
    _wait_for_worker(gui)

    mask_overrides, manual_assignments = captured['args'][-3], captured['args'][-2]
    assert mask_overrides == {'A': 'never'}
    assert manual_assignments == {'B': Path('b.json')}


@requires_font
def test_start_batch_passes_none_overrides_when_nothing_saved(gui, tmp_path, monkeypatch):
    monkeypatch.setattr('glyph_overrides.OVERRIDES_PATH', tmp_path / 'glyph_overrides.json')
    monkeypatch.setattr('glyph_overrides.OVERRIDES_DIR', tmp_path)
    _configure_single_char_batch(gui, 'A', 'NOOVERRIDEARG', tmp_path)

    captured = {}
    real_run_batch = gui._run_batch

    def spy_run_batch(*args, **kwargs):
        captured['args'] = args
        return real_run_batch(*args, **kwargs)

    monkeypatch.setattr(gui, '_run_batch', spy_run_batch)
    gui._start_batch()
    _wait_for_worker(gui)

    assert captured['args'][-3] is None
    assert captured['args'][-2] is None


