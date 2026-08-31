"""Glyph Template tab: generate a KFPS-importable glyph template for a
font. A thin wrapper around the same two CLI tools the Tkinter tab already
wraps (tools/gen_glyph_template.py, tools/gen_font_block_templates.py) --
nothing here reimplements grid/SVG/font-embedding logic.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

import webview

_TOOLS_DIR = Path(__file__).resolve().parent.parent.parent
_REPO_ROOT = _TOOLS_DIR.parent
sys.path.insert(0, str(_TOOLS_DIR))
sys.path.insert(0, str(_REPO_ROOT))

import gen_font_block_templates  # noqa: E402
import gen_glyph_template  # noqa: E402
import gui_settings  # noqa: E402
from gen_fontpack import sanitize_prefix  # noqa: E402
from fontTools.ttLib import TTFont  # noqa: E402
from forza_writer.fabric_project import save as save_project  # noqa: E402
from forza_writer.font_info import load_font_info  # noqa: E402
from forza_writer.glyph_template import (  # noqa: E402
    DEFAULT_CHARS_PER_ROW, DEFAULT_TRACE_TEXT_COLOR, TEMPLATE_UNICODE_BLOCKS, blocks_covered_by_font,
    save_template, validate_hex_color)

from ..events import push_event  # noqa: E402

_FONT_FILE_TYPES = ('Fonts (*.ttf;*.otf;*.ttc)',)
# The first four TEMPLATE_UNICODE_BLOCKS entries are exactly "Basic Latin"
# split into uppercase/lowercase/digits/punctuation -- see
# tools/gen_modelbin_gui/tabs/glyph_template.py's own comment on this.
_BASIC_LATIN_BLOCK_NAMES = frozenset(name for name, _ranges in TEMPLATE_UNICODE_BLOCKS[:4])


def _load_and_scan(font_path: Path) -> dict:
    info = load_font_info(font_path)
    font = TTFont(str(font_path), fontNumber=0)
    try:
        cmap = font.getBestCmap() or {}
    finally:
        font.close()
    # min_chars=1: the full inventory of covered blocks. The UI's own
    # min-glyphs-per-block threshold filters this client-side as the user
    # changes it, without re-scanning the font each time.
    covered = blocks_covered_by_font(cmap, min_chars=1)
    glyph_count = sum(len(chars) for _name, chars in covered)
    weight = f', weight {info.names.weight_class}' if info.names.weight_class else ''
    italic = ', italic' if info.names.is_italic else ''
    beyond_basic_latin = any(name not in _BASIC_LATIN_BLOCK_NAMES for name, _chars in covered)
    return {
        'path': str(font_path),
        'name': info.names.full_name,
        'summary': (f'{info.names.full_name} ({info.names.family} {info.names.subfamily}'
                    f'{weight}{italic}). {glyph_count:,} glyph(s) across {len(covered)} '
                    f'Unicode block(s).'),
        'covered': [{'name': name, 'chars': chars} for name, chars in covered],
        'suggested_mode': 'split' if beyond_basic_latin else 'single',
        'suggested_prefix': sanitize_prefix(info.names.family),
        'total_known_blocks': len(TEMPLATE_UNICODE_BLOCKS),
    }


def register(api, window) -> None:
    generation = {'n': 0}

    def get_charsets(_payload: dict) -> dict:
        return {
            'charsets': list(gen_glyph_template.CHARSETS),
            'default_chars_per_row': DEFAULT_CHARS_PER_ROW,
            'default_trace_color': DEFAULT_TRACE_TEXT_COLOR,
            'default_min_chars': gen_font_block_templates.DEFAULT_MIN_CHARS,
            # A separate default from Settings' Fontpacks Output Directory --
            # these are blank tracing templates, not finished fontpacks.
            'default_output_dir': gui_settings.load_settings()['glyph_template_output_dir'],
        }

    def browse_font(_payload: dict) -> dict:
        chosen = window.create_file_dialog(webview.FileDialog.OPEN, file_types=_FONT_FILE_TYPES)
        if not chosen:
            return {'cancelled': True}
        return _load_and_scan(Path(chosen[0]))

    def load_font_by_path(payload: dict) -> dict:
        return _load_and_scan(Path(payload['path']))

    def pick_output_dir(payload: dict) -> dict:
        chosen = window.create_file_dialog(
            webview.FileDialog.FOLDER, directory=payload.get('initial', ''))
        if not chosen:
            return {'cancelled': True}
        return {'path': chosen[0]}

    def generate(payload: dict) -> dict:
        font_path = Path(payload['font_path'])
        text_color = payload['text_color']
        validate_hex_color(text_color)  # raises ValueError -> surfaced to the page as an error
        prefix = sanitize_prefix(payload['prefix'])
        out_dir = Path(payload['out_dir'])
        gui_settings.update_settings({'glyph_template_output_dir': str(out_dir)})
        mode = payload['mode']
        chars_per_row = max(1, int(payload['chars_per_row']))

        generation['n'] += 1
        gen = generation['n']

        def post_log(line: str) -> None:
            push_event(window, 'glyph_template_log', gen, {'line': line})

        def worker():
            try:
                if mode == 'split':
                    only_blocks = set(payload['only_blocks'])
                    if not only_blocks:
                        raise ValueError('Check at least one Unicode block to generate.')
                    min_chars = max(1, int(payload['min_chars']))
                    written = []
                    for _block_name, template_id, template, project in (
                            gen_font_block_templates.build_all_block_projects(
                                font_path, prefix, chars_per_row, min_chars, only_blocks,
                                log=post_log, text_color=text_color)):
                        # Nested under out_dir/prefix/ -- not out_dir/template_id/ directly --
                        # so a font's blocks group under one folder instead of scattering as
                        # loose siblings alongside every other font's own block folders.
                        block_dir = out_dir / prefix / template_id
                        save_template(template, block_dir / f'{template_id}_template.json')
                        save_project(project, block_dir / f'{template_id}_blank.fabric-project.json')
                        svg_path = block_dir / f'{template_id}.svg'
                        svg_path.parent.mkdir(parents=True, exist_ok=True)
                        svg_path.write_text(project['editor_source_overlay']['svg_text'], encoding='utf-8')
                        written.append(template_id)
                    message = f'{len(written)} block template(s) written under {out_dir / prefix}.'
                else:
                    charset = payload['charset']
                    template, project = gen_glyph_template.build_blank_project(
                        prefix, chars_per_row, charset, font_path, log=post_log, text_color=text_color)
                    pack_dir = out_dir / prefix
                    save_template(template, pack_dir / f'{prefix}_template.json')
                    save_project(project, pack_dir / f'{prefix}_blank.fabric-project.json')
                    svg_path = pack_dir / f'{prefix}.svg'
                    svg_path.parent.mkdir(parents=True, exist_ok=True)
                    svg_path.write_text(project['editor_source_overlay']['svg_text'], encoding='utf-8')
                    message = (f'{len(template.slots)} slot(s) across {template.row_count} row(s) '
                               f'-> {pack_dir}.')
                push_event(window, 'glyph_template_done', gen, {'ok': True, 'message': message})
            except Exception as exc:
                push_event(window, 'glyph_template_done', gen, {'ok': False, 'message': str(exc)})

        threading.Thread(target=worker, daemon=True).start()
        return {'generation': gen}

    api.register('glyph_template.get_charsets', get_charsets)
    api.register('glyph_template.browse_font', browse_font)
    api.register('glyph_template.load_font_by_path', load_font_by_path)
    api.register('glyph_template.pick_output_dir', pick_output_dir)
    api.register('glyph_template.generate', generate)
