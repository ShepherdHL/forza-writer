"""Entry point for the pywebview-based Forza Writer shell.

Phase 0: a fully-chromed, empty-tab-content shell (sidebar nav, animated
backdrop, collapsible/detachable Log panel) proving the pywebview
architecture end to end before any real tab logic is ported. See
tools/gen_modelbin_web/theme_export.py, api.py, events.py, state.py.

Runs as a separate, parallel entry point alongside the existing Tkinter
app (tools/gen_modelbin_gui.py, launched by Forza Writer.bat) -- nothing
that already works changes until a tab's web replacement reaches full
parity with its Tkinter original.
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
    # fontpack build at a time across the whole app), mirroring Tkinter's
    # single self.worker on shell.py. Settings also needs to see it, so
    # Clean generated data can refuse to run while a batch is writing --
    # created up front so every handler that needs it gets the one instance.
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
    generator_handlers.register(api, window, generation_run_state)
    advanced_handlers.register(api, window, generation_run_state)
    plates_handlers.register(api, window)
    configurator_handlers.register(api, window)

    def on_loaded():
        threading.Thread(target=_startup_log, args=(window,), daemon=True).start()

    window.events.loaded += on_loaded

    webview.start(gui="edgechromium")


if __name__ == "__main__":
    main()
