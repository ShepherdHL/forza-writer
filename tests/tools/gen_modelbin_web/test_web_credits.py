"""credits.py: reuses the Tkinter tab's own CREDITS_SECTIONS as the single
source of truth. Coverage here is about the handler wiring itself (correct
shape, correct dispatch) -- CREDITS_SECTIONS' own content is already
guarded by tests/tools/gen_modelbin_gui/test_credits.py.
"""
from gen_modelbin_web.handlers import credits as credits_handlers
from gen_modelbin_gui.tabs.credits import CREDITS_SECTIONS


def test_get_sections_mirrors_the_tkinter_tab_content(api, window):
    credits_handlers.register(api, window)

    resp = api.call('credits.get_sections')

    assert resp['ok'] is True
    sections = resp['result']['sections']
    assert len(sections) == len(CREDITS_SECTIONS)
    assert [s['title'] for s in sections] == [title for title, _entries in CREDITS_SECTIONS]
    assert sections[0]['entries'] == CREDITS_SECTIONS[0][1]


def test_open_link_calls_webbrowser_open(api, window, monkeypatch):
    opened = []
    monkeypatch.setattr(credits_handlers.webbrowser, 'open', lambda url: opened.append(url))
    credits_handlers.register(api, window)

    resp = api.call('credits.open_link', {'url': 'https://example.com'})

    assert resp == {'ok': True, 'result': {'ok': True}}
    assert opened == ['https://example.com']
