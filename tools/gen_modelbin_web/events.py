"""Push events from Python straight into the page.

Replaces the Tkinter shell's `_poll_queue` (a queue.Queue polled every
100ms via root.after) entirely -- pywebview's window.evaluate_js is
callable from any thread, so a worker thread can push an event the
moment it has one instead of a poller picking it up later. The frontend
registers per-tag listeners on window.__forzaEvents (see
frontend/js/events.js); each listener does its own `generation`
staleness check, the same role the queue's (tag, generation, ...) tuple
comparison plays today (e.g. tabs/glyph_inspector.py's stale-result guard).
"""
from __future__ import annotations

import json
import sys
import time

# pywebview's WinForms/WebView2 backend has a startup race: calling
# evaluate_js from a background thread before the CoreWebView2Controller
# has fully finished initializing throws a cascade of COM-interop errors
# ("CoreWebView2Controller members can only be accessed from the UI
# thread", occasionally alongside a pythonnet recursion error walking
# window.native.AccessibilityObject). It's transient, not a real deadlock
# -- confirmed empirically it recovers on its own -- but a single
# fire-and-forget evaluate_js call has no way to know that, so it retries
# with backoff instead of silently losing the event.
_MAX_ATTEMPTS = 6
_INITIAL_BACKOFF = 0.3


def push_event(window, tag: str, generation: int, payload: dict) -> None:
    js = (
        "window.__forzaEvents && window.__forzaEvents.dispatch("
        f"{json.dumps(tag)}, {generation}, {json.dumps(payload)})"
    )
    delay = _INITIAL_BACKOFF
    for attempt in range(_MAX_ATTEMPTS):
        try:
            window.evaluate_js(js)
            return
        except Exception as exc:  # the WebView2 startup race described above
            if attempt == _MAX_ATTEMPTS - 1:
                print(f"push_event: giving up on {tag!r} after {_MAX_ATTEMPTS} attempts: {exc}",
                      file=sys.stderr)
                return
            time.sleep(delay)
            delay *= 2
