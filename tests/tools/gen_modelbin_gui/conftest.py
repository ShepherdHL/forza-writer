"""Shared fixtures/constants/helpers for the gen_modelbin_gui test package.

One Tk() per test *module* (see tk_root) — creating/destroying many separate
tk.Tk() interpreter instances back-to-back in one process is flaky on Windows
(intermittent Tcl init errors); a lightweight Toplevel per test (see gui) is
the stable pattern instead.
"""
import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "tools"))

AMARILLO_FONTPACK = Path(__file__).resolve().parent.parent.parent.parent / "data" / "fontpacks" / "AMARILLO-USAF"
requires_fontpack = pytest.mark.skipif(not (AMARILLO_FONTPACK / "manifest.json").exists(),
                                        reason="sample fontpack not present on this machine")
AMARILLO_FONT = Path.home() / "Desktop" / "amarillo-usaf" / "amarurgt.ttf"
requires_font = pytest.mark.skipif(not AMARILLO_FONT.exists(), reason="test font not present on this machine")
REFERENCE_MODELBIN = Path(__file__).resolve().parent.parent.parent.parent / "user-assets" / "S_01.modelbin"
requires_assets = pytest.mark.skipif(
    not (AMARILLO_FONT.exists() and REFERENCE_MODELBIN.exists()),
    reason="test font or reference modelbin not present on this machine")
tk = pytest.importorskip("tkinter")
from tkinter import ttk  # noqa: E402

@pytest.fixture(scope="package")
def tk_root():
    # Creating/destroying many separate tk.Tk() interpreter instances
    # back-to-back in one process is flaky on Windows (intermittent Tcl
    # init errors) — one Tk() for this whole test package (it used to be
    # one file, hence module scope; now it's split across 8 files, so
    # package scope keeps it at one Tk() total instead of one per file),
    # lightweight Toplevels per test below, is the stable pattern.
    root = tk.Tk()
    root.withdraw()
    yield root
    root.destroy()

@pytest.fixture
def gui(tk_root):
    from gen_modelbin_gui import GeneratorGUI
    window = tk.Toplevel(tk_root)
    # A Toplevel doesn't inherit its parent's withdrawn state, so without
    # this every one of the ~85 tests using this fixture flashed a real,
    # visible app window on screen. alpha=0 keeps it fully invisible while
    # staying "mapped" for Tk's purposes, so winfo_ismapped()/real pixel
    # layout (which several tests below rely on) still work correctly —
    # unlike .withdraw(), which would make the window unmapped and break
    # those geometry-dependent assertions.
    window.attributes('-alpha', 0.0)
    instance = GeneratorGUI(window)
    tk_root.update()
    yield instance
    window.destroy()

def _load_all_fonts_and_wait(gui, timeout=15):
    gui._load_all_fonts()
    deadline = time.time() + timeout
    while (not gui.fonts or str(gui.load_fonts_btn['state']) == 'disabled') and time.time() < deadline:
        gui._poll_queue()
        gui.root.update()
        time.sleep(0.05)
    gui._poll_queue()
    gui.root.update()

def _wait_for_font_scripts(gui, timeout=20):
    deadline = time.time() + timeout
    while len(gui._font_scripts) < len(gui.fonts) and time.time() < deadline:
        gui._poll_queue()
        gui.root.update()
        time.sleep(0.05)
    gui._poll_queue()
    gui.root.update()

def _configure_single_char_batch(gui, char, prefix, out_dir):
    gui.selected_font = AMARILLO_FONT
    gui.output_var.set('json')
    gui._on_output_mode_changed()
    gui.all_var.set(False)
    gui._on_all_toggled()
    for var in (gui.upper_var, gui.lower_var, gui.digits_var, gui.punct_var, gui.symbols_var):
        var.set(False)
    gui.custom_var.set(char)
    gui.prefix_var.set(prefix)
    gui.out_var.set(str(out_dir))

def _wait_for_worker(gui, timeout=20):
    deadline = time.time() + timeout
    while gui.worker is not None and gui.worker.is_alive() and time.time() < deadline:
        gui._poll_queue()
        gui.root.update()
        time.sleep(0.05)
    gui._poll_queue()
    gui.root.update()

def _write_loose_glyph_json(path, shapes):
    import json as jsonlib
    path.write_text(jsonlib.dumps({'shapes': shapes}), encoding='utf-8')

def _configure_configurator_font(gui, font=None):
    gui.configurator_font_var.set(str(font or AMARILLO_FONT))

def _wait_for_configurator_scan(gui, timeout=20):
    deadline = time.time() + timeout
    while 'inspected' not in gui.configurator_scan_status_var.get().lower() and time.time() < deadline:
        gui._poll_queue()
        gui.root.update()
        time.sleep(0.05)
    gui._poll_queue()
    gui.root.update()

def _profiled_gui_pack_dir(gui, out_dir, prefix, output='json'):
    from gen_fontpack import pack_dir_for
    from forza_writer.compute_backend import resolve_backend
    backend = resolve_backend(gui.compute_backend_var.get() if output == 'json' else 'cpu')
    return pack_dir_for(out_dir, prefix, output, max(1, int(gui.segments_var.get())), backend.resolved)

def _wait_for_configurator_detail(gui, timeout=20):
    deadline = time.time() + timeout
    while 'background' in gui.configurator_detail_status_var.get().lower() and time.time() < deadline:
        gui._poll_queue()
        gui.root.update()
        time.sleep(0.05)
    gui._poll_queue()
    gui.root.update()
