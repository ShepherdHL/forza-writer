"""Shared fixtures for the gen_modelbin_web test package.

Every handler's register(api, window) only ever touches `window` via
window.evaluate_js (event push, see events.py) and window.create_file_dialog
(native Browse dialogs) -- neither needs a real WebView2 window, so tests
run against a real JSApi/AppState with a lightweight FakeWindow standing in
for the one webview actually creates. No GDI-style resource cost, no
pywebview startup, real handler code path exercised end to end.
"""
from __future__ import annotations

import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS_DIR))

import pytest  # noqa: E402
from webview.util import parse_file_type  # noqa: E402

import gui_settings  # noqa: E402
from gen_modelbin_web.api import JSApi  # noqa: E402
from gen_modelbin_web.state import AppState  # noqa: E402

AMARILLO_FONT = Path.home() / "Desktop" / "amarillo-usaf" / "amarurgt.ttf"
requires_font = pytest.mark.skipif(not AMARILLO_FONT.exists(), reason="test font not present on this machine")

_ASSETS_FONTS = Path(__file__).resolve().parent.parent.parent.parent / "assets" / "fonts"
LIBERATION_SANS = _ASSETS_FONTS / "LiberationSans-Regular.ttf"


class FakeWindow:
    """Stands in for pywebview's real Window. Records every evaluate_js
    call (push_event's payload) so tests can assert on pushed events
    without a live page to receive them, and returns a settable canned
    result from create_file_dialog instead of showing a real OS dialog."""

    def __init__(self):
        self.evaluated: list[str] = []
        self.file_dialog_result = None

    def evaluate_js(self, js: str) -> None:
        self.evaluated.append(js)

    def create_file_dialog(self, *_args, file_types=(), **_kwargs):
        # pywebview's real Window.create_file_dialog validates every
        # file_types entry against its filter-string regex before ever
        # showing a dialog (window.py) -- a description containing a
        # character outside [\w ], or an extension with anything but
        # `;`-joined `*.word` segments, raises instead of opening. A bare
        # canned-result stub here would never have caught the three
        # handlers that shipped with exactly that mistake (a literal '/'
        # in a description, a hyphenated compound extension, and a
        # wildcard-less extension), so mirror the real validation.
        for file_type in file_types:
            parse_file_type(file_type)
        return self.file_dialog_result


@pytest.fixture
def window() -> FakeWindow:
    return FakeWindow()


@pytest.fixture
def api(window) -> JSApi:
    return JSApi(AppState())


@pytest.fixture
def isolated_settings(tmp_path, monkeypatch):
    # Handlers that read/write gui_settings (color_picker.py's saved/recent
    # library, settings.py) must not touch the real settings.json on the
    # machine running the tests.
    path = tmp_path / 'settings.json'
    monkeypatch.setattr(gui_settings, 'SETTINGS_PATH', path)
    monkeypatch.setattr(gui_settings, 'SETTINGS_DIR', path.parent)
    return path
