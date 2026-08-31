"""Root-level fixtures/setup shared by the whole test suite.

Must run before any test module's own `import tkinter` -- see
tools/tcl_library_fix.py's module docstring for the exact Tcl/Tk init
failure this works around (two Python installs on PATH, each shipping its
own mismatched tcl86t.dll) and why setting TCL_LIBRARY/TK_LIBRARY here
fixes it. A root conftest.py is pytest's earliest, most reliable hook point
for whole-suite setup: it loads before every nested conftest.py and every
test module under tests/, including tests/tools/gen_modelbin_gui/conftest.py
itself, which imports `tkinter` directly at module scope.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from tcl_library_fix import ensure_tcl_tk_library_env  # noqa: E402

ensure_tcl_tk_library_env()
