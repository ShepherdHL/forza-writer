"""GUI front-end for the font-to-fontpack pipeline.

See app.py for the composed GeneratorGUI class and entry point.

The generation/analysis entry points re-exported below (charset_from_font,
resolve_backend, generate_direct, inspect_variable_font, instantiate_font,
build_fontpack, is_running_as_administrator) are deliberately bound here,
on the top-level package, rather than only imported locally by whichever
tab module calls them. Tab modules call back through
`gen_modelbin_gui.<name>(...)` (see each tabs/*.py) instead of a bare
`from x import name`, so tests can substitute a fake via
`monkeypatch.setattr(gen_modelbin_gui, 'name', fake)`: a plain
`from x import name` snapshots the reference at import time, and a patch
here would never reach it. This must stay imported before `.app`, since
the tab modules resolve `gen_modelbin_gui.<name>` through this
already-partially-initialized package at their own import time.
"""
import sys
from pathlib import Path
from tkinter import filedialog, messagebox

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from gen_fontpack import build_fontpack  # noqa: E402

from forza_writer import script_detect  # noqa: E402
from forza_writer.charset import charset_from_font  # noqa: E402
from forza_writer.compute_backend import resolve_backend  # noqa: E402
from forza_writer.direct_generate import generate_direct  # noqa: E402
from forza_writer.font_info import glyph_geometry, load_font_info  # noqa: E402
from forza_writer.variable_fonts import inspect_variable_font, instantiate_font  # noqa: E402

from .state import (  # noqa: E402
    GRID_TILE_SIZE, OUTPUT_MODE_LABELS, TABS, direct_output_filename,
    is_running_as_administrator)

from .app import GeneratorGUI, main  # noqa: E402

__all__ = [
    "GeneratorGUI", "main",
    "charset_from_font", "resolve_backend", "generate_direct",
    "inspect_variable_font", "instantiate_font", "build_fontpack",
    "load_font_info", "glyph_geometry",
    "is_running_as_administrator", "direct_output_filename",
    "GRID_TILE_SIZE", "OUTPUT_MODE_LABELS", "TABS",
    "filedialog", "messagebox", "script_detect",
]
