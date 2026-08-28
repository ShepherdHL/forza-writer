"""Merges every per-module English string catalog under this package.

Each sibling module (shell.py, generator.py, and so on) exports its own
STRINGS dict, named after the GUI source file it covers, so a string's
origin stays traceable back to the file that uses it. Adding a new GUI
module's strings means adding a new sibling module here, not editing this
file.
"""
import importlib
import pkgutil

STRINGS: dict[str, str] = {}

for _module_info in pkgutil.iter_modules(__path__):
    _module = importlib.import_module(f'{__name__}.{_module_info.name}')
    STRINGS.update(getattr(_module, 'STRINGS', {}))
