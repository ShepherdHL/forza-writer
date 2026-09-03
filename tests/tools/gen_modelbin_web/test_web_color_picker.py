"""color_picker.py: shared saved/recent color library persistence, backing
every tab's picker instance. The picker's own render/interaction math lives
in frontend/js/color-picker.js (not testable without a browser); this
covers the server-side persistence logic that actually matters to get
right, since it's shared mutable state across every tab.
"""
import pytest

import gui_settings
from gen_modelbin_web.handlers import color_picker as color_picker_handlers
from gen_modelbin_web.handlers.color_picker import _BASIC_PRESET_COLORS


@pytest.fixture(autouse=True)
def _register(api, window):
    color_picker_handlers.register(api, window)
    return api


def test_get_presets_returns_the_basic_preset_colors(api, isolated_settings):
    resp = api.call('color_picker.get_presets')
    assert resp['result']['presets'] == [
        {'rgba': list(color), 'name': name} for color, name in _BASIC_PRESET_COLORS]


def test_get_library_starts_empty(api, isolated_settings):
    resp = api.call('color_picker.get_library')
    assert resp['result'] == {'saved': [], 'recent': []}


def test_save_named_adds_to_the_saved_library(api, isolated_settings):
    resp = api.call('color_picker.save_named', {'name': 'Sunset', 'rgba': [255, 128, 0, 255]})
    assert resp['result']['saved'] == [{'name': 'Sunset', 'rgba': [255, 128, 0, 255]}]

    # Persisted, not just returned -- a fresh read sees it too.
    resp2 = api.call('color_picker.get_library')
    assert resp2['result']['saved'] == [{'name': 'Sunset', 'rgba': [255, 128, 0, 255]}]


def test_save_named_rejects_a_blank_name(api, isolated_settings):
    resp = api.call('color_picker.save_named', {'name': '   ', 'rgba': [1, 2, 3, 255]})
    assert resp['ok'] is False
    assert 'Name required' in resp['error']


def test_save_named_truncates_an_overlong_name(api, isolated_settings):
    long_name = 'x' * 100
    resp = api.call('color_picker.save_named', {'name': long_name, 'rgba': [1, 2, 3, 255]})
    saved_name = resp['result']['saved'][0]['name']
    assert saved_name == 'x' * gui_settings.MAX_SAVED_COLOR_NAME_LEN


def test_delete_saved_removes_the_named_entry(api, isolated_settings):
    api.call('color_picker.save_named', {'name': 'Keep', 'rgba': [1, 1, 1, 255]})
    api.call('color_picker.save_named', {'name': 'Drop', 'rgba': [2, 2, 2, 255]})

    resp = api.call('color_picker.delete_saved', {'name': 'Drop'})

    names = [e['name'] for e in resp['result']['saved']]
    assert names == ['Keep']


def test_delete_saved_missing_name_is_a_no_op(api, isolated_settings):
    api.call('color_picker.save_named', {'name': 'Keep', 'rgba': [1, 1, 1, 255]})
    resp = api.call('color_picker.delete_saved', {'name': 'DoesNotExist'})
    assert [e['name'] for e in resp['result']['saved']] == ['Keep']


def test_push_recent_adds_newest_first(api, isolated_settings):
    api.call('color_picker.push_recent', {'rgba': [1, 0, 0, 255]})
    resp = api.call('color_picker.push_recent', {'rgba': [0, 1, 0, 255]})
    assert resp['result']['recent'] == [[0, 1, 0, 255], [1, 0, 0, 255]]


def test_push_recent_deduplicates_by_moving_to_front(api, isolated_settings):
    api.call('color_picker.push_recent', {'rgba': [1, 0, 0, 255]})
    api.call('color_picker.push_recent', {'rgba': [0, 1, 0, 255]})
    resp = api.call('color_picker.push_recent', {'rgba': [1, 0, 0, 255]})

    assert resp['result']['recent'] == [[1, 0, 0, 255], [0, 1, 0, 255]]


def test_push_recent_caps_at_the_max_length(api, isolated_settings):
    for i in range(gui_settings.MAX_RECENT_COLORS + 5):
        resp = api.call('color_picker.push_recent', {'rgba': [i, 0, 0, 255]})

    assert len(resp['result']['recent']) == gui_settings.MAX_RECENT_COLORS
    # Most recently pushed stays at the front; oldest ones fall off the end.
    assert resp['result']['recent'][0] == [gui_settings.MAX_RECENT_COLORS + 4, 0, 0, 255]


def test_get_and_set_setting_color_round_trip(api, isolated_settings):
    default = api.call('color_picker.get_setting_color', {'key': 'color_generator'})['result']['rgba']
    assert default == [255, 255, 255, 255]  # gui_settings.DEFAULT_SETTINGS's own default

    api.call('color_picker.set_setting_color', {'key': 'color_generator', 'rgba': [10, 20, 30, 255]})
    resp = api.call('color_picker.get_setting_color', {'key': 'color_generator'})

    assert resp['result']['rgba'] == [10, 20, 30, 255]
