"""Entry-point shim — the actual GUI now lives in tools/gen_modelbin_gui/
(see that package's app.py for the composed GeneratorGUI class).

Kept as a thin top-level script, rather than folding this into the package,
so existing invocations (Forza Writer.bat's `pythonw tools\\gen_modelbin_gui.py`)
keep working unchanged.

Usage:
    python tools/gen_modelbin_gui.py
Or double-click Forza Writer.bat in the repo root.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen_modelbin_gui.app import main  # noqa: E402

if __name__ == '__main__':
    main()
