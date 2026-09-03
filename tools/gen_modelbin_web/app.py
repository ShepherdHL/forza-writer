"""Entry point for Forza Writer's pywebview-based shell -- the app's only
GUI. Builds the window chrome (sidebar nav, animated backdrop,
collapsible/detachable Log panel), wires every tab's handlers, and starts
the WebView2-backed window. See theme_export.py, api.py, events.py,
state.py, and handlers/ for one module per tab.

Runs entirely as a local desktop app: pywebview loads index.html from disk
and talks to Python over its own in-process JS-API bridge -- no HTTP
server, no network socket.
"""
import sys
import threading
import time
from pathlib import Path

import webview

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gen_modelbin_web import theme_export  # noqa: E402
from gen_modelbin_web.api import JSApi  # noqa: E402
from gen_modelbin_web.events import push_event  # noqa: E402
from gen_modelbin_web.state import AppState  # noqa: E402
from gen_modelbin_web.handlers import fonts as fonts_handlers  # noqa: E402
from gen_modelbin_web.handlers import glyph_inspector as glyph_inspector_handlers  # noqa: E402
from gen_modelbin_web.handlers import credits as credits_handlers  # noqa: E402
from gen_modelbin_web.handlers import settings as settings_handlers  # noqa: E402
from gen_modelbin_web.handlers import color_picker as color_picker_handlers  # noqa: E402
from gen_modelbin_web.handlers import forza_font_text as forza_font_text_handlers  # noqa: E402
from gen_modelbin_web.handlers import ascii_art as ascii_art_handlers  # noqa: E402
from gen_modelbin_web.handlers import glyph_template as glyph_template_handlers  # noqa: E402
from gen_modelbin_web.handlers import outputs as outputs_handlers  # noqa: E402
from gen_modelbin_web.handlers import composer as composer_handlers  # noqa: E402
from gen_modelbin_web.handlers import direct as direct_handlers  # noqa: E402
from gen_modelbin_web.handlers import layer_effects as layer_effects_handlers  # noqa: E402
from gen_modelbin_web.handlers import batch_runner  # noqa: E402
from gen_modelbin_web.handlers import generator as generator_handlers  # noqa: E402
from gen_modelbin_web.handlers import advanced as advanced_handlers  # noqa: E402
from gen_modelbin_web.handlers import plates as plates_handlers  # noqa: E402
from gen_modelbin_web.handlers import configurator as configurator_handlers  # noqa: E402

FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"
# The app's icon -- a simple two-dot mark (white, then orange).
# Deliberately plain rather than a detailed braille-dot grid: at the
# 16-24px sizes Windows
# actually renders a title-bar/taskbar icon at, fine detail just reads as
# noise -- two bold dots hold up. Sets both the title-bar icon (top-left
# corner) and the taskbar icon -- pywebview draws both from this one file
# via webview.start's `icon` argument.
ICON_PATH = Path(__file__).resolve().parent.parent.parent / "assets" / "icon-web.ico"


def _startup_log(window) -> None:
    # Proves the worker-thread -> push_event -> live DOM update path works
    # end to end, the same pattern every later ported tab's background
    # worker will use in place of today's msg_queue.put(...). The delay
    # is just a courtesy first attempt -- push_event's own retry/backoff
    # (see events.py) is what actually protects against pywebview's
    # WebView2-controller startup race, not this sleep.
    time.sleep(1.0)
    push_event(window, "log_append", 0, {
        "ts": time.strftime("%H:%M:%S"),
        "level": "plain",
        "text": "Forza Writer (Web) shell ready.",
    })


def main() -> None:
    theme_export.write(FRONTEND_DIR / "css" / "theme.css")

    state = AppState()
    api = JSApi(state)

    window = webview.create_window(
        "Forza Writer",
        str(FRONTEND_DIR / "index.html"),
        js_api=api,
        width=1280,
        height=820,
        min_size=(960, 640),
    )
    api._window = window
    # Generator and Advanced Generator share one batch-runner lock (only one
    # fontpack build at a time across the whole app). Settings also needs
    # to see it, so Clean generated data can refuse to run while a batch
    # is writing -- created up front so every handler that needs it gets
    # the one instance.
    generation_run_state = batch_runner.new_run_state()
    fonts_handlers.register(api, window)
    glyph_inspector_handlers.register(api, window)
    credits_handlers.register(api, window)
    settings_handlers.register(api, window, generation_run_state)
    color_picker_handlers.register(api, window)
    forza_font_text_handlers.register(api, window)
    ascii_art_handlers.register(api, window)
    glyph_template_handlers.register(api, window)
    outputs_handlers.register(api, window)
    composer_handlers.register(api, window)
    direct_handlers.register(api, window)
    layer_effects_handlers.register(api, window)
    generator_handlers.register(api, window, generation_run_state, state)
    advanced_handlers.register(api, window, generation_run_state, state)
    plates_handlers.register(api, window)
    configurator_handlers.register(api, window)

    def on_loaded():
        threading.Thread(target=_startup_log, args=(window,), daemon=True).start()

    window.events.loaded += on_loaded

    webview.start(gui="edgechromium", icon=str(ICON_PATH))


if __name__ == "__main__":
    main()
