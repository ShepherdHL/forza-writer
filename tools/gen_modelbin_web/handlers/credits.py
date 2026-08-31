"""Credits tab: static attribution content, reusing the Tkinter tab's own
CREDITS_SECTIONS data (tools/gen_modelbin_gui/tabs/credits.py) as the single
source of truth rather than a hand-duplicated copy -- same principle
theme_export.py follows for palette colors.
"""
from __future__ import annotations

import sys
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from gen_modelbin_gui.tabs.credits import CREDITS_SECTIONS  # noqa: E402


def register(api, window) -> None:
    def get_sections(_payload: dict) -> dict:
        return {
            'sections': [
                {'title': title, 'entries': entries} for title, entries in CREDITS_SECTIONS
            ]
        }

    def open_link(payload: dict) -> dict:
        webbrowser.open(payload['url'])
        return {'ok': True}

    api.register('credits.get_sections', get_sections)
    api.register('credits.open_link', open_link)
