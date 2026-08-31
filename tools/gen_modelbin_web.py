"""Entry-point shim: the pywebview-based GUI lives in tools/gen_modelbin_web/
(see that package's app.py). Kept as a thin top-level script, mirroring
gen_modelbin_gui.py's own shim, so "Forza Writer (Web).bat"'s invocation
stays simple and stable.

Usage:
    python tools/gen_modelbin_web.py
Or double-click "Forza Writer (Web).bat" in the repo root.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen_modelbin_web.app import main  # noqa: E402

if __name__ == '__main__':
    main()
