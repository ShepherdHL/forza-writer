"""Regression coverage for a real bug: pywebview's Window.create_file_dialog
validates every file_types description/extension against a strict regex
before ever showing a dialog (webview.util.parse_file_type), and raises
instead of opening one if a filter string doesn't match. Three handlers
carried a filter string over from the Tkinter side's more permissive
filedialog verbatim and tripped this: a literal '/' in a description, a
hyphenated compound extension, and an extension missing its wildcard. Each
failed silently from the user's perspective, since the frontend's `if
(resp.ok && ...)` click handlers have no branch for resp.ok === false.

conftest.py's FakeWindow now runs the same validation, so these tests fail
loudly (a raised ValueError surfaces through JSApi.call as resp.ok=False)
if any handler's file_types regresses to an invalid filter string again.
"""
from gen_modelbin_web.handlers import advanced as advanced_handlers
from gen_modelbin_web.handlers import batch_runner
from gen_modelbin_web.handlers import forza_font_text as forza_font_text_handlers
from gen_modelbin_web.handlers import settings as settings_handlers


def test_advanced_browse_font_file_types_are_valid(api, window):
    advanced_handlers.register(api, window, batch_runner.new_run_state())
    resp = api.call('advanced.browse_font', {})
    assert resp['ok'] is True


def test_forza_font_text_save_fabric_project_file_types_are_valid(api, window):
    forza_font_text_handlers.register(api, window)
    resp = api.call('forza_font_text.save_project', {'initial_dir': ''})
    assert resp['ok'] is True


def test_settings_browse_kfps_file_types_are_valid(api, window):
    settings_handlers.register(api, window)
    resp = api.call('settings.browse', {'kind': 'kfps', 'initial': ''})
    assert resp['ok'] is True
