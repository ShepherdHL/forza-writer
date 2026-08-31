"""Glyph Template tab: font loading, mode auto-selection, and generation."""
from pathlib import Path

from .conftest import _wait_for_glyph_template_font, _wait_for_glyph_template_worker  # noqa: E402

# Repo-bundled, openly-licensed (SIL OFL) fonts already used by
# tools/gen_font_block_templates.py's own default-template-library build,
# safe to embed in a test without a requires_font-style skip marker.
_ASSETS_FONTS = Path(__file__).resolve().parent.parent.parent.parent / "assets" / "fonts"
LIBERATION_SANS = _ASSETS_FONTS / "LiberationSans-Regular.ttf"


def _fake_font_info(family="Fake"):
    from forza_writer.font_info import FontInfo, FontMetrics, FontNames
    from forza_writer.variable_fonts import VariableFontInfo

    return FontInfo(
        path=Path("fake.ttf"),
        names=FontNames(family=family, subfamily="Regular", full_name=f"{family} Regular",
                         weight_class=400, is_italic=False),
        metrics=FontMetrics(units_per_em=1000, ascender=800, descender=-200,
                             cap_height=700, x_height=500),
        variable=VariableFontInfo((), ()),
        glyphs_by_category={}, category_order=(),
    )


def test_glyph_template_is_a_first_class_tab(gui):
    assert 'glyph_template' in gui._pages
    assert gui._tab_labels['glyph_template'].cget('text')


def test_glyph_template_mode_auto_selects_single_for_basic_latin_only_font(gui):
    info = _fake_font_info()
    covered = [
        ('Latin - Uppercase', list('ABC')),
        ('Latin - Lowercase', list('abc')),
        ('Digits', list('012')),
        ('Punctuation & Symbols', list('!?')),
    ]

    gui._apply_glyph_template_font_loaded(info, covered)

    assert gui.glyph_template_mode_var.get() == 'single'
    assert gui.glyph_template_prefix_var.get() == 'FAKE'


def test_glyph_template_mode_auto_selects_split_for_large_library_font(gui):
    info = _fake_font_info(family="Fake CJK")
    # 5 chars/block, comfortably above gen_font_block_templates.DEFAULT_MIN_CHARS
    # (4) so all three survive into the checklist.
    covered = [
        ('Latin - Uppercase', list('ABCDE')),
        ('Hiragana', list('あいうえお')),
        ('Katakana', list('アイウエオ')),
    ]

    gui._apply_glyph_template_font_loaded(info, covered)

    assert gui.glyph_template_mode_var.get() == 'split'
    assert set(gui.glyph_template_block_vars) == {'Latin - Uppercase', 'Hiragana', 'Katakana'}


def test_glyph_template_block_checklist_refilters_on_min_chars_change(gui):
    info = _fake_font_info()
    covered = [
        ('Latin - Uppercase', list('ABCDEFG')),  # 7 glyphs
        ('Digits', list('01234')),  # 5 glyphs -- clears the default threshold (4), not a raised one
    ]
    gui._apply_glyph_template_font_loaded(info, covered)
    assert set(gui.glyph_template_block_vars) == {'Latin - Uppercase', 'Digits'}

    gui.glyph_template_min_chars_var.set(6)

    assert set(gui.glyph_template_block_vars) == {'Latin - Uppercase'}


def test_glyph_template_font_load_populates_real_font(gui):
    gui._show_tab('glyph_template')
    gui.glyph_template_font_var.set(str(LIBERATION_SANS))
    gui._load_glyph_template_font(LIBERATION_SANS)
    _wait_for_glyph_template_font(gui)

    assert gui._glyph_template_font_info is not None
    assert gui.glyph_template_prefix_var.get() == 'LIBERATION-SANS'
    assert gui.glyph_template_block_vars  # checklist populated from the real cmap
    assert 'glyph(s)' in gui.glyph_template_font_status_var.get()


def test_glyph_template_single_mode_generate_writes_expected_files(gui, tmp_path):
    gui._show_tab('glyph_template')
    gui.glyph_template_font_var.set(str(LIBERATION_SANS))
    gui._load_glyph_template_font(LIBERATION_SANS)
    _wait_for_glyph_template_font(gui)

    gui.glyph_template_mode_var.set('single')
    gui._on_glyph_template_mode_changed()
    gui.glyph_template_charset_var.set('basic-latin')
    gui.glyph_template_out_var.set(str(tmp_path))
    gui.glyph_template_prefix_var.set('TEST-SINGLE')

    gui._start_glyph_template_generate()
    _wait_for_glyph_template_worker(gui)

    assert gui.glyph_template_status_var.get() == 'Done.'
    pack_dir = tmp_path / 'TEST-SINGLE'
    assert (pack_dir / 'TEST-SINGLE_template.json').exists()
    assert (pack_dir / 'TEST-SINGLE_blank.fabric-project.json').exists()
    assert (pack_dir / 'TEST-SINGLE.svg').exists()


def test_glyph_template_split_mode_generate_writes_only_checked_blocks(gui, tmp_path):
    gui._show_tab('glyph_template')
    gui.glyph_template_font_var.set(str(LIBERATION_SANS))
    gui._load_glyph_template_font(LIBERATION_SANS)
    _wait_for_glyph_template_font(gui)

    gui.glyph_template_mode_var.set('split')
    gui._on_glyph_template_mode_changed()
    gui.glyph_template_out_var.set(str(tmp_path))
    gui.glyph_template_prefix_var.set('TEST-SPLIT')

    assert 'Latin - Uppercase' in gui.glyph_template_block_vars
    for name, var in gui.glyph_template_block_vars.items():
        var.set(name == 'Latin - Uppercase')

    gui._start_glyph_template_generate()
    _wait_for_glyph_template_worker(gui)

    assert gui.glyph_template_status_var.get() == 'Done.'
    written = sorted(p.name for p in tmp_path.iterdir() if p.is_dir())
    assert written == ['TEST-SPLIT-LATIN-UPPERCASE']
    block_dir = tmp_path / 'TEST-SPLIT-LATIN-UPPERCASE'
    assert (block_dir / 'TEST-SPLIT-LATIN-UPPERCASE_template.json').exists()
    assert (block_dir / 'TEST-SPLIT-LATIN-UPPERCASE_blank.fabric-project.json').exists()
    assert (block_dir / 'TEST-SPLIT-LATIN-UPPERCASE.svg').exists()


def test_glyph_template_generate_without_font_shows_info_dialog(gui, monkeypatch, tmp_path):
    shown = []
    monkeypatch.setattr(
        'gen_modelbin_gui.tabs.glyph_template.messagebox.showinfo',
        lambda title, msg: shown.append((title, msg)))
    gui._glyph_template_font = None
    gui.glyph_template_out_var.set(str(tmp_path))

    gui._start_glyph_template_generate()

    assert shown and shown[0][0] == 'No font selected'
    assert gui._glyph_template_worker is None


def test_glyph_template_custom_tracing_color_appears_in_generated_svg(gui, tmp_path):
    gui._show_tab('glyph_template')
    gui.glyph_template_font_var.set(str(LIBERATION_SANS))
    gui._load_glyph_template_font(LIBERATION_SANS)
    _wait_for_glyph_template_font(gui)

    gui.glyph_template_mode_var.set('single')
    gui._on_glyph_template_mode_changed()
    gui.glyph_template_charset_var.set('basic-latin')
    gui.glyph_template_out_var.set(str(tmp_path))
    gui.glyph_template_prefix_var.set('TEST-COLOR')
    gui._set_glyph_template_text_color('#ff0044')

    gui._start_glyph_template_generate()
    _wait_for_glyph_template_worker(gui)

    assert gui.glyph_template_status_var.get() == 'Done.'
    svg_text = (tmp_path / 'TEST-COLOR' / 'TEST-COLOR.svg').read_text(encoding='utf-8')
    assert 'fill="#ff0044"' in svg_text
    assert 'fill="#e6e6e6"' not in svg_text  # the old hardcoded default shouldn't leak through


def test_glyph_template_invalid_tracing_color_blocks_generate(gui, monkeypatch, tmp_path):
    shown = []
    monkeypatch.setattr(
        'gen_modelbin_gui.tabs.glyph_template.messagebox.showinfo',
        lambda title, msg: shown.append((title, msg)))
    gui._glyph_template_font = LIBERATION_SANS
    gui.glyph_template_out_var.set(str(tmp_path))
    gui.glyph_template_text_color_var.set('not-a-color')

    gui._start_glyph_template_generate()

    assert shown and shown[0][0] == 'Invalid color'
    assert gui._glyph_template_worker is None


def test_glyph_template_pick_tracing_color_updates_var_and_swatch(gui, monkeypatch):
    monkeypatch.setattr(
        'gen_modelbin_gui.tabs.glyph_template.colorchooser.askcolor',
        lambda color, title: ((0, 255, 136), '#00ff88'))

    gui._pick_glyph_template_text_color()

    assert gui.glyph_template_text_color_var.get() == '#00ff88'
    assert gui.glyph_template_color_swatch.cget('background') == '#00ff88'


def test_glyph_template_typed_invalid_color_reverts_to_last_valid(gui, monkeypatch):
    monkeypatch.setattr('gen_modelbin_gui.tabs.glyph_template.messagebox.showinfo', lambda title, msg: None)
    gui._set_glyph_template_text_color('#123456')
    gui.glyph_template_text_color_var.set('garbage')

    gui._apply_glyph_template_text_color_from_field()

    assert gui.glyph_template_text_color_var.get() == '#123456'
