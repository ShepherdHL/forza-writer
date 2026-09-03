"""credits.py: static attribution content. Coverage here is about the
handler wiring itself -- correctly shaping CREDITS_SECTIONS' list-of-tuples
into the dispatched response, and dispatch itself.
"""
from gen_modelbin_web.handlers import credits as credits_handlers
from gen_modelbin_web.handlers.credits import CREDITS_SECTIONS


def test_get_sections_shapes_credits_sections_into_the_response(api, window):
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
