"""fonts.py: the shared installed-font listing used by any tab with a font
picker. enumerate_installed_fonts() itself (registry reads) is exercised by
the Tkinter suite; this only covers the handler's own response shaping.
"""
from pathlib import Path

from gen_modelbin_web.handlers import fonts as fonts_handlers


def test_list_installed_shapes_name_and_path(api, window, monkeypatch):
    monkeypatch.setattr(fonts_handlers, 'enumerate_installed_fonts', lambda: {
        'Amarillo USAF': Path('C:/Fonts/AmarilloUSAF.ttf'),
        'Liberation Sans': Path('C:/Fonts/LiberationSans-Regular.ttf'),
    })
    fonts_handlers.register(api, window)

    resp = api.call('fonts.list_installed')

    assert resp['ok'] is True
    assert resp['result']['fonts'] == [
        {'name': 'Amarillo USAF', 'path': 'C:\\Fonts\\AmarilloUSAF.ttf'},
        {'name': 'Liberation Sans', 'path': 'C:\\Fonts\\LiberationSans-Regular.ttf'},
    ]


def test_list_installed_empty_when_no_fonts_found(api, window, monkeypatch):
    monkeypatch.setattr(fonts_handlers, 'enumerate_installed_fonts', lambda: {})
    fonts_handlers.register(api, window)

    resp = api.call('fonts.list_installed')

    assert resp['result']['fonts'] == []
