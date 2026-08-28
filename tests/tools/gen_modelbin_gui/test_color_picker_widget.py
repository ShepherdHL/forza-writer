"""tools/gen_modelbin_gui/color_picker_widget.py: the one color-picker
widget ASCII Art, Forza Font Text, Composer, and Layer Effects all embed.

Settings I/O is monkeypatched to a tmp_path settings.json for every test
here (unlike most of this test package) -- these tests actively read/write
saved_colors/recent_colors/color_* keys, and the real gui_settings.json on
the dev machine is not test-isolated (see conftest.py's `gui` fixture).
"""
import pytest

from conftest import tk  # noqa: E402

import gui_settings  # noqa: E402
from gen_modelbin_gui.color_picker_widget import ColorPickerWidget  # noqa: E402
from forza_writer import forza_colors  # noqa: E402 -- importable once the line above has run (see its own sys.path.insert)


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    path = tmp_path / 'settings.json'
    monkeypatch.setattr(gui_settings, 'SETTINGS_PATH', path)
    monkeypatch.setattr(gui_settings, 'SETTINGS_DIR', path.parent)
    yield path


@pytest.fixture
def widget(tk_root, isolated_settings):
    window = tk.Toplevel(tk_root)
    window.attributes('-alpha', 0.0)
    w = ColorPickerWidget(window)
    w.pack()
    tk_root.update()
    yield w
    window.destroy()


def test_self_drive_persists_across_construction(tk_root, isolated_settings):
    window1 = tk.Toplevel(tk_root)
    window1.attributes('-alpha', 0.0)
    w1 = ColorPickerWidget(window1, settings_key='color_ascii_art', initial=(1, 2, 3, 255))
    w1.pack()
    tk_root.update()
    w1.set_color((10, 20, 30, 255))
    window1.destroy()
    tk_root.update()

    window2 = tk.Toplevel(tk_root)
    window2.attributes('-alpha', 0.0)
    w2 = ColorPickerWidget(window2, settings_key='color_ascii_art', initial=(1, 2, 3, 255))
    tk_root.update()
    assert w2.color == (10, 20, 30, 255)
    window2.destroy()


def test_self_drive_falls_back_to_initial_when_nothing_saved(widget):
    assert widget.color == (255, 255, 255, 255)


def test_external_drive_reads_through_get_color(tk_root, isolated_settings):
    window = tk.Toplevel(tk_root)
    window.attributes('-alpha', 0.0)
    state = {'color': (9, 9, 9, 255)}
    w = ColorPickerWidget(window, get_color=lambda: state['color'])
    tk_root.update()
    assert w.color == (9, 9, 9, 255)
    state['color'] = (1, 1, 1, 255)
    w.sync()
    assert w.color == (1, 1, 1, 255)
    window.destroy()


def test_external_drive_none_disables_and_reenables(tk_root, isolated_settings):
    window = tk.Toplevel(tk_root)
    window.attributes('-alpha', 0.0)
    state = {'color': None}
    w = ColorPickerWidget(window, get_color=lambda: state['color'])
    tk_root.update()
    assert w.color is None
    assert str(w._pick_btn['state']) == 'disabled'
    state['color'] = (5, 5, 5, 255)
    w.sync()
    assert str(w._pick_btn['state']) == 'normal'
    window.destroy()


def test_on_change_called_with_new_color(widget):
    seen = []
    widget._on_change = seen.append
    widget.set_color((11, 22, 33, 255))
    assert seen == [(11, 22, 33, 255)]


def test_drag_gesture_records_only_final_color(widget):
    """Mirrors the SB-square/hue-strip drag handlers: each intermediate
    call passes record_recent=False, and only the gesture's final release
    (_commit_gesture_recent) should land one entry in Recent."""
    widget.set_color((10, 20, 30, 255), record_recent=False)
    widget.set_color((20, 30, 40, 255), record_recent=False)
    widget.set_color((30, 40, 50, 255), record_recent=False)
    assert widget._recent_colors == []
    widget._commit_gesture_recent()
    assert widget._recent_colors == [(30, 40, 50, 255)]


def test_save_named_color_persists_and_can_be_applied(widget):
    widget.set_color((44, 55, 66, 255))
    widget._save_name_var.set('Team Red')
    widget._save_current_as()

    assert widget._saved_colors['Team Red'] == (44, 55, 66, 255)
    loaded = gui_settings.load_settings()
    assert loaded['saved_colors']['Team Red'] == [44, 55, 66, 255]


def test_delete_saved_color_removes_it(widget):
    widget.set_color((44, 55, 66, 255))
    widget._save_name_var.set('Temp')
    widget._save_current_as()
    widget._delete_saved('Temp')

    assert 'Temp' not in widget._saved_colors
    loaded = gui_settings.load_settings()
    assert 'Temp' not in loaded['saved_colors']


def test_saving_color_broadcasts_to_sibling_instances(tk_root, isolated_settings):
    window_a = tk.Toplevel(tk_root)
    window_a.attributes('-alpha', 0.0)
    a = ColorPickerWidget(window_a)
    window_b = tk.Toplevel(tk_root)
    window_b.attributes('-alpha', 0.0)
    b = ColorPickerWidget(window_b)
    tk_root.update()

    a.set_color((7, 8, 9, 255))
    a._save_name_var.set('Shared')
    a._save_current_as()

    assert b._saved_colors.get('Shared') == (7, 8, 9, 255)

    window_a.destroy()
    window_b.destroy()


def test_destroyed_widget_is_dropped_from_live_instances(tk_root, isolated_settings):
    window = tk.Toplevel(tk_root)
    window.attributes('-alpha', 0.0)
    w = ColorPickerWidget(window)
    assert w in ColorPickerWidget._LIVE_INSTANCES
    window.destroy()
    tk_root.update()
    assert w not in ColorPickerWidget._LIVE_INSTANCES


def _find_buttons_by_text(root_widget, text):
    found = []
    stack = [root_widget]
    while stack:
        w = stack.pop()
        if isinstance(w, tk.Button) and w.cget('text') == text:
            found.append(w)
        stack.extend(w.winfo_children())
    return found


# -- full color readout (RGB/hex/HSL/HSB/Forza HSB), same everywhere -------

def test_readout_shows_all_representations_and_agrees_with_shared_conversion(widget):
    widget.set_color((30, 144, 255, 255))

    assert widget._hex_var.get() == '#1e90ff'
    assert widget._r_var.get() == '30'
    assert widget._g_var.get() == '144'
    assert widget._b_var.get() == '255'

    expected = forza_colors.describe_color(30, 144, 255)
    assert f'{expected.hsl_h:.1f}' in widget._hsl_var.get()
    assert f'{expected.hsb_h:.1f}' in widget._hsb_var.get()
    assert f'{expected.forza_h:.3f}' in widget._forza_var.get()


def test_readout_updates_on_every_commit_path(widget):
    """hex entry, RGB entry, and native/preset clicks all funnel through
    _redraw_all -- the readout must never go stale after any of them."""
    widget._hex_var.set('#00ff00')
    widget._commit_hex()
    assert '120.0' in widget._hsb_var.get()  # green's hue

    widget._r_var.set('255')
    widget._g_var.set('0')
    widget._b_var.set('0')
    widget._commit_rgb()
    assert '0.0' in widget._hsb_var.get()  # red's hue


def test_readout_clears_when_disabled(tk_root, isolated_settings):
    window = tk.Toplevel(tk_root)
    window.attributes('-alpha', 0.0)
    state = {'color': None}
    w = ColorPickerWidget(window, get_color=lambda: state['color'])
    tk_root.update()
    assert w._hsl_var.get() == ''
    assert w._forza_var.get() == ''
    window.destroy()


# -- named swatches everywhere a color list appears -------------------------

def test_basic_presets_are_named_buttons_not_bare_swatches(widget):
    matches = _find_buttons_by_text(widget, 'Red')
    assert len(matches) == 1
    btn = matches[0]
    assert btn.cget('background') == '#e2453c'


def test_named_swatch_is_keyboard_focusable_and_activatable(widget):
    """A real Button (not a Label with a click binding) is what makes this
    both Tab-reachable and Space-activatable via Tk's own default Button
    class binding -- neither is disabled here. invoke() is the reliable
    way to exercise a Tk button's action in a test; simulating a raw
    physical Space keypress through a headless, unfocused test window is
    exactly the kind of thing that's flaky for reasons unrelated to this
    code (confirmed directly: even a plain stock tk.Button's own built-in
    Space binding doesn't fire via event_generate here without true OS
    input focus, which an alpha=0 window can't reliably obtain headless)."""
    btn = _find_buttons_by_text(widget, 'Off White')[0]
    assert str(btn.cget('takefocus')) != '0'
    assert 'Button' in btn.bindtags()  # inherits Tk's own default Space-to-invoke binding
    btn.invoke()
    assert widget.color[:3] == (242, 243, 245)


def test_saved_color_shows_its_name_and_is_deletable_by_delete_key(widget):
    widget.set_color((44, 55, 66, 255))
    widget._save_name_var.set('Team Red')
    widget._save_current_as()

    matches = _find_buttons_by_text(widget, 'Team Red')
    assert len(matches) == 1
    btn = matches[0]

    btn.focus_force()  # a key event is focus-routed; a plain event_generate() isn't enough headless
    widget.winfo_toplevel().update()
    btn.event_generate('<Delete>')
    widget.winfo_toplevel().update()
    assert 'Team Red' not in widget._saved_colors
    assert not _find_buttons_by_text(widget, 'Team Red')


def test_recent_color_is_labeled_with_its_hex_code(widget):
    widget.set_color((10, 20, 30, 255))
    assert _find_buttons_by_text(widget, '#0a141e')
