"""Module-level constants and font-discovery helpers shared across the GUI package.

No app-mixin dependencies here on purpose. Every tab module imports from this
one, so there is a single place these live instead of duplicated or import-
order-dependent copies.
"""
import re
import winreg
import ctypes
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from gen_fontpack import sanitize_prefix  # noqa: E402
import gui_theme  # noqa: E402

from .i18n import t

_MODE_LABELS = {
    "auto": t("state.mask_mode.auto"),
    "force": t("state.mask_mode.force"),
    "never": t("state.mask_mode.never"),
    "manual": t("state.mask_mode.manual"),
}

FONT_EXTENSIONS = {'.ttf', '.otf'}

FONTS_DIR_SYSTEM = Path(r'C:\Windows\Fonts')

def _rgba_to_hex(rgba: tuple[int, int, int, int]) -> str:
    r, g, b = rgba[0], rgba[1], rgba[2]
    return f'#{r:02x}{g:02x}{b:02x}'

def is_running_as_administrator() -> bool:
    """Best-effort Windows elevation check used only for a startup notice."""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False

GRID_TILE_SIZE = (170, 36)

GRID_TILE_GAP = 3      # px between tiles, both axes. Column count is derived from this plus GRID_TILE_SIZE

GRID_MAX_TILES = 60

PREVIEW_SIZE = (280, 280)

# Glyph Inspector's categorized browser grid. Same "cap the tile count,
# offer to render more" shape as GRID_MAX_TILES above, just per-category
# instead of per-font-list, since one CJK category alone (e.g. CJK Unified
# Ideographs) can hold 10,000+ glyphs and must never all render at once.
GLYPH_TILE_SIZE = (40, 40)

GLYPH_TILE_GAP = 3

GLYPH_CATEGORY_TILE_CAP = 200

# "Show more" grows a category by this many tiles per click, up to
# GLYPH_CATEGORY_HARD_CAP. Confirmed by hitting it directly: letting
# "Show more" render an entire 12,000+-glyph CJK Unified Ideographs category
# in one shot exhausts Windows' per-process GDI bitmap handle budget and
# crashes the process ("Fail to allocate bitmap"), since each tile is a real
# Tk PhotoImage/Label, not a virtualized draw. The hard cap is a stopgap for
# Phase 1; true virtualized/windowed rendering (only building widgets for
# tiles actually scrolled into view) is the real fix and isn't in scope yet.
# Past the cap, search is the only way to reach a specific glyph.
GLYPH_CATEGORY_EXPAND_STEP = 200

GLYPH_CATEGORY_HARD_CAP = 1000

GLYPH_GRID_HEIGHT = 480

GLYPH_PREVIEW_SIZE = (380, 380)

LIVE_PREVIEW_SIZE = (160, 160)

COMPOSE_PREVIEW_SIZE = (640, 200)

LAYER_EFFECTS_PREVIEW_SIZE = (480, 300)

# Taller than COMPOSE_PREVIEW_SIZE. ASCII art is typically closer to square
# or portrait (many rows) rather than composed text's one-line-tall span.
ASCII_PREVIEW_SIZE = (640, 420)

SIDEBAR_WIDTH = 170

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

# Plates tab preview canvas, following the size-constant convention every
# other tab's preview already uses (PREVIEW_SIZE, LIVE_PREVIEW_SIZE, etc.
# above). Wider than tall like COMPOSE_PREVIEW_SIZE: a plate is a wide,
# short aspect ratio (~2:1 to ~5:1) far more often than square.
PLATES_PREVIEW_SIZE = (640, 260)

def direct_output_filename(font_path: Path, method: str, *, backend: str = 'cpu',
                           segments: int = 8, cell_size: int = 1) -> str:
    """Filesystem-safe Direct filename that always identifies its font."""
    font_name = sanitize_prefix(font_path.stem).lower()
    if method == 'modern':
        return f'{font_name}_direct_modern_{backend}_s{segments}.json'
    if method == 'image':
        return f'{font_name}_image_to_text_cpu_cell{cell_size}.json'
    return f'{font_name}_direct_legacy_cpu_cell{cell_size}.json'

def sidebar_tab_text(label: str) -> str:
    """Tracked HUD text that keeps multiword navigation labels readable.

    Applying letter spacing to a whole phrase makes it wider than the fixed
    sidebar. Stacking words preserves the visual treatment without clipping.
    """
    return '\n'.join(gui_theme.hud_label(word) for word in label.split())

OUTPUT_MODE_LABELS = {
    "modelbin": (t("state.output_mode.modelbin.title"), t("state.output_mode.modelbin.description")),
    "json": (t("state.output_mode.json.title"), t("state.output_mode.json.description")),
    "json_legacy": (t("state.output_mode.json_legacy.title"), t("state.output_mode.json_legacy.description")),
}

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

ICON_PATH = Path(__file__).resolve().parent.parent.parent / 'assets' / 'icon.ico'

