"""Backend-owned app state for the web shell.

Also the single home for the small set of module-level constants and the
installed-font registry scan that several tabs' handlers need -- one place
these live instead of duplicated per-handler copies.
"""
from __future__ import annotations

import re
import sys
import winreg
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from gen_fontpack import sanitize_prefix  # noqa: E402

from .i18n import t

FONT_EXTENSIONS = {'.ttf', '.otf'}

FONTS_DIR_SYSTEM = Path(r'C:\Windows\Fonts')

GRID_TILE_SIZE = (170, 36)

GLYPH_TILE_SIZE = (40, 40)

# Glyph Inspector's categorized browser grid renders at most this many tiles
# per category up front (one CJK category alone can hold 10,000+ glyphs);
# past the cap, search is the way to reach a specific glyph.
GLYPH_CATEGORY_TILE_CAP = 200

GLYPH_PREVIEW_SIZE = (380, 380)

LAYER_EFFECTS_PREVIEW_SIZE = (480, 300)

PLATES_PREVIEW_SIZE = (640, 260)

TABS = ['forza_font_text', 'generator', 'advanced', 'direct', 'ascii_art', 'glyph_inspector',
        'glyph_template', 'layer_effects', 'outputs', 'composer', 'plates', 'settings', 'credits']

TAB_LABELS = {
    'forza_font_text': t('state.tab.forza_font_text'),
    'generator': t('state.tab.generator'),
    'advanced': t('state.tab.advanced'),
    'direct': t('state.tab.direct'),
    'ascii_art': t('state.tab.ascii_art'),
    'glyph_inspector': t('state.tab.glyph_inspector'),
    'glyph_template': t('state.tab.glyph_template'),
    'layer_effects': t('state.tab.layer_effects'),
    'outputs': t('state.tab.outputs'),
    'composer': t('state.tab.composer'),
    'plates': t('state.tab.plates'),
    'settings': t('state.tab.settings'),
    'credits': t('state.tab.credits'),
}


def direct_output_filename(font_path: Path, method: str, *, backend: str = 'cpu',
                           segments: int = 8, cell_size: int = 1) -> str:
    """Filesystem-safe Direct filename that always identifies its font."""
    font_name = sanitize_prefix(font_path.stem).lower()
    if method == 'modern':
        return f'{font_name}_direct_modern_{backend}_s{segments}.json'
    if method == 'image':
        return f'{font_name}_image_to_text_cpu_cell{cell_size}.json'
    return f'{font_name}_direct_legacy_cpu_cell{cell_size}.json'


def _read_fonts_key(root, key_path, base_dir):
    """Yield (display_name, resolved_path) pairs from one registry Fonts key."""
    try:
        key = winreg.OpenKey(root, key_path)
    except OSError:
        return
    try:
        i = 0
        while True:
            try:
                name, value, _type = winreg.EnumValue(key, i)
            except OSError:
                break
            i += 1
            if not isinstance(value, str):
                continue
            path = Path(value)
            if not path.is_absolute():
                path = base_dir / path
            if path.suffix.lower() in FONT_EXTENSIONS and path.exists():
                # Registry names look like "Arial (TrueType)". Strip the tag.
                display = re.sub(r'\s*\((?:TrueType|OpenType)\)\s*$', '', name)
                yield display, path
    finally:
        key.Close()


def enumerate_installed_fonts() -> dict[str, Path]:
    """Map font display name -> font file path for installed .ttf/.otf fonts.

    Reads both the machine-wide Fonts registry key (files usually relative to
    C:\\Windows\\Fonts) and the per-user key (files usually absolute, under
    %LOCALAPPDATA%\\Microsoft\\Windows\\Fonts).
    """
    fonts: dict[str, Path] = {}
    for display, path in _read_fonts_key(
            winreg.HKEY_LOCAL_MACHINE,
            r'SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts',
            FONTS_DIR_SYSTEM):
        fonts[display] = path
    for display, path in _read_fonts_key(
            winreg.HKEY_CURRENT_USER,
            r'SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts',
            FONTS_DIR_SYSTEM):
        fonts[display] = path
    return dict(sorted(fonts.items(), key=lambda kv: kv[0].lower()))


class AppState:
    def __init__(self) -> None:
        self.current_tab = TABS[0]
        self.log_lines: list[dict] = []
        # Generator's own font selection, pushed here by
        # handlers/generator.py's set_current_font whenever it changes and
        # read back by handlers/advanced.py's "Use current from Generator".
        self.current_font: str | None = None


TAB_ORDER = TABS
TAB_TITLES = TAB_LABELS
