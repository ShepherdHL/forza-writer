"""JSApi's own direct methods (export_log): unlike handlers dispatched
through JSApi.call(), these aren't wrapped by call()'s generic try/except,
so each has to handle its own failures -- export_log previously let a
write failure cross the bridge as an unhandled rejection with zero
user-visible feedback (see shell.js's click handler, fixed alongside this).
"""
from gen_modelbin_web.api import JSApi
from gen_modelbin_web.state import AppState


def test_export_log_returns_cancelled_when_no_window(window):
    api = JSApi(AppState())
    resp = api.export_log()
    assert resp == {'ok': False, 'error': 'Window not ready yet.'}


def test_export_log_returns_cancelled_when_dialog_is_dismissed(window):
    api = JSApi(AppState())
    api._window = window
    window.file_dialog_result = None

    assert api.export_log() == {'cancelled': True}


def test_export_log_writes_every_log_line(window, tmp_path):
    api = JSApi(AppState())
    api._window = window
    api._state.log_lines.append({'ts': '00:00:01', 'level': 'plain', 'text': 'Started.'})
    api._state.log_lines.append({'ts': '00:00:02', 'level': 'danger', 'text': 'Something broke.'})
    out_path = tmp_path / 'log.txt'
    window.file_dialog_result = [str(out_path)]

    resp = api.export_log()

    assert resp == {'ok': True, 'path': str(out_path)}
    assert out_path.read_text(encoding='utf-8') == (
        '[00:00:01] Started.\n[00:00:02] DANGER: Something broke.\n')


def test_export_log_reports_a_write_failure_instead_of_raising(window, tmp_path):
    api = JSApi(AppState())
    api._window = window
    # A directory that doesn't exist -- write_text raises FileNotFoundError,
    # same failure class as an unwritable/invalid path chosen in the dialog.
    window.file_dialog_result = [str(tmp_path / 'does-not-exist' / 'log.txt')]

    resp = api.export_log()

    assert resp['ok'] is False
    assert 'error' in resp
