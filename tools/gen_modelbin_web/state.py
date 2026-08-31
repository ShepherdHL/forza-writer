"""Backend-owned app state for the web shell.

Tkinter's tab modules read live UI state directly off StringVar/BooleanVar
instances (see tabs/generator.py's charset-building, tabs/settings.py's
compute-backend selection) -- those aren't disposable bindings, they're
real inputs to backend logic. This module is where that state lives once
there's no Tk variable to hold it; each ported tab adds its own slice here
as it's built, per the migration plan's per-tab recipe.

Phase 0 only needs the shell-level state: which tab is showing and the
in-memory log line history (mirrored to gui_settings for the collapsed/
detached flags, same as shell.py's Log panel does today).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from gen_modelbin_gui.state import TABS, TAB_LABELS  # noqa: E402


class AppState:
    def __init__(self) -> None:
        self.current_tab = TABS[0]
        self.log_lines: list[dict] = []


TAB_ORDER = TABS
TAB_TITLES = TAB_LABELS
