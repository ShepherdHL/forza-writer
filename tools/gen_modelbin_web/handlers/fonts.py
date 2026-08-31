"""Shared installed-font listing, used by any tab that lets the user pick a
font (Glyph Inspector, Glyph Template, and likely more later). One
registration, not one copy per tab -- see frontend/js/font-search.js for
the matching shared UI component.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from gen_modelbin_gui.state import enumerate_installed_fonts  # noqa: E402


def register(api, window) -> None:
    def list_installed(_payload: dict) -> dict:
        # enumerate_installed_fonts() reads both the machine-wide registry
        # key (C:\Windows\Fonts) and the per-user key (%LOCALAPPDATA%\
        # Microsoft\Windows\Fonts). A raw file dialog defaulted to just
        # the first of those misses every font installed for the current
        # user only, which is most custom fonts on a real machine.
        return {'fonts': [{'name': name, 'path': str(path)}
                           for name, path in enumerate_installed_fonts().items()]}

    api.register('fonts.list_installed', list_installed)
