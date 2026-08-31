"""Works around a Tcl/Tk init failure on machines with more than one Python
install on PATH.

Symptom: `import tkinter` (or `tkinter.Tk()`) raises
`_tkinter.TclError: Can't find a usable init.tcl in the following
directories: {...}` / `...couldn't read file "...": No error`, even though
that exact init.tcl file exists on disk and is perfectly readable.

Root cause, confirmed on this machine: this project's interpreter is a venv
based on C:\\Python312, which ships its own tcl86t.dll/tk86t.dll (and the
matching tcl/tcl8.6 library files) under that install. But C:\\Python313 is
also installed and appears earlier on PATH, and it ships its *own*
tcl86t.dll -- a different Tcl build. When `_tkinter`'s C extension loads,
Windows' DLL search picks up Python 3.13's tcl86t.dll instead of Python
3.12's matching one (PATH order wins over "the venv you meant"). That
mismatched DLL then can't find a usable init.tcl relative to itself, even
though the correct init.tcl is sitting right where Tcl reports it looked --
it's not actually the DLL that opened the directory listing in the error.

Fix: point TCL_LIBRARY/TK_LIBRARY at *this* interpreter's own tcl/tk
library folders explicitly, via sys.base_prefix (which resolves correctly
through a venv to the real base install). This sidesteps the DLL-search
ambiguity entirely -- Tcl uses whatever library path it's told, regardless
of which physical DLL got loaded.

Call `ensure_tcl_tk_library_env()` before the *first* `import tkinter`
anywhere in the process. It's a no-op if TCL_LIBRARY/TK_LIBRARY are already
set (an explicit override always wins) or if this interpreter's own base
install has no tcl/ folder to find paths under -- in either case tkinter's
own ordinary import error surfaces unchanged if something is still wrong.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def ensure_tcl_tk_library_env() -> None:
    try:
        base_tcl_dir = Path(sys.base_prefix) / 'tcl'
        if not base_tcl_dir.is_dir():
            return

        if 'TCL_LIBRARY' not in os.environ:
            tcl_dirs = sorted(base_tcl_dir.glob('tcl8.*'))
            for candidate in reversed(tcl_dirs):  # newest version first
                if (candidate / 'init.tcl').exists():
                    os.environ['TCL_LIBRARY'] = str(candidate)
                    break

        if 'TK_LIBRARY' not in os.environ:
            tk_dirs = sorted(base_tcl_dir.glob('tk8.*'))
            if tk_dirs:
                os.environ['TK_LIBRARY'] = str(tk_dirs[-1])
    except OSError:
        pass  # defensive only -- let the ordinary tkinter import error surface unchanged
