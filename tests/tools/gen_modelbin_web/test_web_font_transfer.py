"""Cross-tab font-transfer parity with Tkinter's shared object graph:
Generator pushes its selection to AppState.current_font (generator.py's
set_current_font); Advanced Generator pulls it back (advanced.py's
get_current_generator_font) and can instantiate the current selection for
Configurator's per-glyph overrides (open_instance_overrides).
"""
from pathlib import Path

from gen_modelbin_web.handlers import advanced as advanced_handlers
from gen_modelbin_web.handlers import generator as generator_handlers


def test_set_current_font_stores_on_shared_state(api, window):
    generator_handlers.register(api, window, {}, api._state)

    resp = api.call('generator.set_current_font', {'font_path': 'C:/Fonts/Amarillo.ttf'})

    assert resp['ok'] is True
    assert api._state.current_font == 'C:/Fonts/Amarillo.ttf'


def test_set_current_font_with_no_path_clears_it(api, window):
    api._state.current_font = 'C:/Fonts/Amarillo.ttf'
    generator_handlers.register(api, window, {}, api._state)

    api.call('generator.set_current_font', {'font_path': ''})

    assert api._state.current_font is None


def test_get_current_generator_font_is_none_before_any_selection(api, window):
    advanced_handlers.register(api, window, {}, api._state)

    resp = api.call('advanced.get_current_generator_font')

    assert resp['ok'] is True
    assert resp['result']['font_path'] is None


def test_get_current_generator_font_reflects_generators_push(api, window):
    generator_handlers.register(api, window, {}, api._state)
    advanced_handlers.register(api, window, {}, api._state)

    api.call('generator.set_current_font', {'font_path': 'C:/Fonts/Amarillo.ttf'})
    resp = api.call('advanced.get_current_generator_font')

    assert resp['result']['font_path'] == 'C:/Fonts/Amarillo.ttf'


def test_open_instance_overrides_instantiates_with_given_coordinates(api, window, monkeypatch, tmp_path):
    instance_file = tmp_path / 'Font-Bold.ttf'
    instance_file.write_bytes(b'')
    calls = []

    def fake_instantiate(font_path, coordinates):
        calls.append((font_path, coordinates))
        return instance_file

    monkeypatch.setattr(advanced_handlers, 'instantiate_font', fake_instantiate)
    advanced_handlers.register(api, window, {}, api._state)

    resp = api.call('advanced.open_instance_overrides', {
        'font_path': str(tmp_path / 'Font.ttf'), 'coordinates': {'wght': 700},
    })

    assert resp['ok'] is True
    assert resp['result']['instance_path'] == str(instance_file)
    assert calls == [(Path(str(tmp_path / 'Font.ttf')), {'wght': 700})]


def test_open_instance_overrides_slug_reflects_coordinates(api, window, monkeypatch, tmp_path):
    instance_file = tmp_path / 'Font-Bold.ttf'
    instance_file.write_bytes(b'')
    monkeypatch.setattr(advanced_handlers, 'instantiate_font', lambda font_path, coordinates: instance_file)
    advanced_handlers.register(api, window, {}, api._state)

    resp = api.call('advanced.open_instance_overrides', {
        'font_path': str(tmp_path / 'Font.ttf'), 'coordinates': {'wght': 700},
    })

    from forza_writer.variable_fonts import variation_slug
    assert resp['result']['slug'] == variation_slug({'wght': 700})
