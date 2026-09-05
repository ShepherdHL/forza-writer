"""The js_api bridge exposed to the page as window.pywebview.api.

One generic `call(name, payload)` entry point dispatching into a registry
built up as each tab is ported (Phase 2's recipe registers its handlers
here), rather than growing a new js_api method per action -- this mirrors
the existing (tag, generation, ...) message shape almost 1:1 and avoids
re-registering exposed methods every time a tab is added.

Kept free of any tkinter import: this is the web app's own bridge, not a
wrapper around the Tkinter GUI.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Callable

import webview

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import gui_settings  # noqa: E402

from .state import AppState, TAB_ORDER, TAB_TITLES  # noqa: E402

Handler = Callable[[dict], dict]


class JSApi:
    # pywebview's bridge-injection code (webview/util.py's inject_pywebview)
    # walks every *public* (non-underscore) attribute of this object via
    # dir() to build the JS-callable surface, recursing into anything
    # non-callable. A plain `self.window = window` here is exactly such an
    # attribute -- pywebview would recurse straight into the raw WinForms
    # Window.native object graph (genuinely cyclic: AccessibilityObject.
    # Bounds.Empty chains back into itself under pythonnet), blowing
    # Python's recursion limit and stalling the UI thread for many seconds
    # before it gives up. Both `state` and `window` must stay
    # underscore-prefixed so that walk skips them entirely.
    def __init__(self, state: AppState) -> None:
        self._state = state
        self._window = None  # set by app.py after window creation
        self._registry: dict[str, Handler] = {}

    def register(self, name: str, handler: Handler) -> None:
        self._registry[name] = handler

    def call(self, name: str, payload: dict | None = None) -> dict:
        handler = self._registry.get(name)
        if handler is None:
            return {"ok": False, "error": f"no handler registered for {name!r}"}
        try:
            result = handler(payload or {})
        except Exception as exc:  # surfaced to the page, not raised across the bridge
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "result": result}

    def get_tabs(self) -> list[dict]:
        return [{"id": tab_id, "label": TAB_TITLES[tab_id]} for tab_id in TAB_ORDER]

    def get_settings(self) -> dict:
        return gui_settings.load_settings()

    def save_settings(self, settings: dict) -> dict:
        gui_settings.save_settings(settings)
        return {"ok": True}

    def get_log(self) -> list[dict]:
        return self._state.log_lines

    def log(self, level: str, text: str) -> dict:
        entry = {"ts": time.strftime("%H:%M:%S"), "level": level, "text": text}
        self._state.log_lines.append(entry)
        return entry

    def export_log(self) -> dict:
        # A quick way to hand off the session's log after an unforeseen
        # error: writes every line in state.log_lines (not just whatever
        # happens to be scrolled into view), so it's the same content
        # get_log() would hand the page on a fresh load. Timestamped
        # default filename so exporting more than once in a session
        # doesn't silently overwrite the previous file.
        #
        # This is a direct JSApi method, not routed through call()'s
        # {ok, result}/try-except registry wrapper, so it has to do its own
        # -- an uncaught exception here (a bad save path, a permissions
        # error) would otherwise cross the bridge as an unhandled JS
        # promise rejection with no feedback shown anywhere.
        if self._window is None:
            return {"ok": False, "error": "Window not ready yet."}
        try:
            chosen = self._window.create_file_dialog(
                webview.FileDialog.SAVE,
                save_filename=time.strftime("forza-writer-log-%Y%m%d-%H%M%S.txt"),
                file_types=("Text files (*.txt)", "All files (*.*)"))
            if not chosen:
                return {"cancelled": True}
            path = chosen if isinstance(chosen, str) else chosen[0]
            lines = []
            for entry in self._state.log_lines:
                prefix = f"{entry['level'].upper()}: " if entry['level'] != 'plain' else ""
                lines.append(f"[{entry['ts']}] {prefix}{entry['text']}")
            Path(path).write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
            return {"ok": True, "path": path}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
