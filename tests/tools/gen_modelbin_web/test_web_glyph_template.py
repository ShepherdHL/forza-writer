"""Glyph Template tab (web handler): font loading and generation."""
import time
from pathlib import Path

from gen_modelbin_web.handlers import glyph_template as glyph_template_handlers

_ASSETS_FONTS = Path(__file__).resolve().parent.parent.parent.parent / "assets" / "fonts"
LIBERATION_SANS = _ASSETS_FONTS / "LiberationSans-Regular.ttf"


def _wait_for_file(path: Path, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while not path.exists() and time.time() < deadline:
        time.sleep(0.05)
    assert path.exists(), f"{path} was never written within {timeout}s"


def test_get_charsets_returns_known_charsets(api, window):
    glyph_template_handlers.register(api, window)

    resp = api.call('glyph_template.get_charsets')

    assert resp['ok'] is True
    assert set(resp['result']['charsets']) == {'basic-latin', 'hiragana', 'katakana'}


def test_load_font_by_path_scans_real_font(api, window):
    glyph_template_handlers.register(api, window)

    resp = api.call('glyph_template.load_font_by_path', {'path': str(LIBERATION_SANS)})

    assert resp['ok'] is True
    result = resp['result']
    assert result['suggested_prefix'] == 'LIBERATION-SANS'
    assert result['covered']
    assert 'glyph(s)' in result['summary']


def test_single_mode_different_charsets_dont_collide(api, window, isolated_settings, tmp_path):
    """Regression test: generating Hiragana then Katakana under the same
    prefix used to both write <prefix>/<prefix>.svg through this handler's
    own (separate from the Tkinter tab's) file-writing code, so the second
    run silently overwrote the first."""
    glyph_template_handlers.register(api, window)

    def generate(charset):
        resp = api.call('glyph_template.generate', {
            'font_path': str(LIBERATION_SANS),
            'text_color': '#e6e6e6',
            'prefix': 'PP-MORI',
            'out_dir': str(tmp_path),
            'mode': 'single',
            'chars_per_row': 10,
            'charset': charset,
        })
        assert resp['ok'] is True
        return resp['result']['generation']

    hiragana_gen = generate('hiragana')
    hiragana_svg = tmp_path / 'PP-MORI-HIRAGANA' / 'PP-MORI-HIRAGANA.svg'
    _wait_for_file(hiragana_svg)

    katakana_gen = generate('katakana')
    katakana_svg = tmp_path / 'PP-MORI-KATAKANA' / 'PP-MORI-KATAKANA.svg'
    _wait_for_file(katakana_svg)

    assert hiragana_gen != katakana_gen
    assert hiragana_svg.exists()
    assert katakana_svg.exists()
    assert hiragana_svg.read_bytes() != katakana_svg.read_bytes()
    # The bare, unsuffixed prefix folder from the old (buggy) naming should
    # never get created for a non-default charset.
    assert not (tmp_path / 'PP-MORI').exists()


def test_single_mode_default_charset_still_uses_bare_prefix(api, window, isolated_settings, tmp_path):
    glyph_template_handlers.register(api, window)

    resp = api.call('glyph_template.generate', {
        'font_path': str(LIBERATION_SANS),
        'text_color': '#e6e6e6',
        'prefix': 'TEST-SINGLE',
        'out_dir': str(tmp_path),
        'mode': 'single',
        'chars_per_row': 10,
        'charset': 'basic-latin',
    })
    assert resp['ok'] is True

    svg_path = tmp_path / 'TEST-SINGLE' / 'TEST-SINGLE.svg'
    _wait_for_file(svg_path)
    assert (tmp_path / 'TEST-SINGLE' / 'TEST-SINGLE_template.json').exists()
    assert (tmp_path / 'TEST-SINGLE' / 'TEST-SINGLE_blank.fabric-project.json').exists()


def _assert_data_uri(value):
    assert isinstance(value, str)
    assert value.startswith('data:image/png;base64,')
    assert len(value) > len('data:image/png;base64,')


def test_render_preview_single_mode_returns_image(api, window):
    glyph_template_handlers.register(api, window)

    resp = api.call('glyph_template.render_preview', {
        'font_path': str(LIBERATION_SANS),
        'text_color': '#ff8800',
        'chars_per_row': 10,
        'mode': 'single',
        'charset': 'basic-latin',
    })

    assert resp['ok'] is True
    _assert_data_uri(resp['result']['image'])


def test_render_preview_split_mode_returns_image_for_named_block(api, window):
    glyph_template_handlers.register(api, window)

    resp = api.call('glyph_template.render_preview', {
        'font_path': str(LIBERATION_SANS),
        'text_color': '#00ffcc',
        'chars_per_row': 8,
        'mode': 'split',
        'block': {'name': 'Punctuation & Symbols', 'chars': list('.,!?()[]')},
    })

    assert resp['ok'] is True
    _assert_data_uri(resp['result']['image'])


def test_render_preview_split_mode_without_block_returns_no_image(api, window):
    """No block chosen to preview yet (nothing clicked in the checklist) --
    a valid, empty response, not an error."""
    glyph_template_handlers.register(api, window)

    resp = api.call('glyph_template.render_preview', {
        'font_path': str(LIBERATION_SANS),
        'text_color': '#e6e6e6',
        'chars_per_row': 10,
        'mode': 'split',
        'block': None,
    })

    assert resp['ok'] is True
    assert resp['result']['image'] is None


def test_render_preview_without_font_shows_placeholder_letterforms(api, window):
    """No font loaded yet is a valid state (payload's font_path empty) --
    the grid still renders, just with placeholder characters instead of
    traced letterforms, matching build_blank_overlay_svg's own fallback."""
    glyph_template_handlers.register(api, window)

    resp = api.call('glyph_template.render_preview', {
        'font_path': None,
        'text_color': '#e6e6e6',
        'chars_per_row': 10,
        'mode': 'single',
        'charset': 'basic-latin',
    })

    assert resp['ok'] is True
    _assert_data_uri(resp['result']['image'])


def test_render_block_samples_returns_one_image_per_block(api, window):
    glyph_template_handlers.register(api, window)

    resp = api.call('glyph_template.render_block_samples', {
        'font_path': str(LIBERATION_SANS),
        'blocks': [
            {'name': 'Punctuation & Symbols', 'chars': list('.,!?/\\[]')},
            {'name': 'Digits', 'chars': list('0123456789')},
        ],
    })

    assert resp['ok'] is True
    samples = resp['result']['samples']
    assert set(samples) == {'Punctuation & Symbols', 'Digits'}
    for uri in samples.values():
        _assert_data_uri(uri)
