"""Persistent user-defined Layered Glyph Effect presets -- one JSON file per
saved preset under the same per-user directory `tools/gui_settings.py`
already uses (`%LOCALAPPDATA%\\forza-writer\\layer_presets\\<name>.json`).
A sibling directory rather than an addition to that module's single settings
blob, because a preset store needs multiple independently named
saved/loaded/deleted entries, not one global config. Never raises -- a
missing or corrupt store degrades to "no saved presets" rather than
blocking the GUI from starting, matching `gui_settings.py`'s own
never-raises convention.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from gui_settings import SETTINGS_DIR

PRESETS_DIR = SETTINGS_DIR / "layer_presets"

_UNSAFE_NAME_CHARS = re.compile(r"[^A-Za-z0-9 _.-]+")


def _slug(name: str) -> str:
    """Filesystem-safe filename for a user-given preset name -- collapses
    anything outside a conservative safe set so a name like "Retro/Four" or
    "Racing: Shadow" can't escape `PRESETS_DIR` or collide with reserved
    characters."""
    safe = _UNSAFE_NAME_CHARS.sub("_", name).strip() or "preset"
    return safe[:80]


def list_presets() -> list[str]:
    """Every saved preset's display name (its `"name"` field, not the
    filename), sorted case-insensitively. Never raises -- unreadable files
    are silently skipped rather than surfacing a mid-list crash."""
    if not PRESETS_DIR.exists():
        return []
    names = []
    for path in sorted(PRESETS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        names.append(data.get("name", path.stem))
    return sorted(names, key=str.lower)


def save_preset(stack_dict: dict) -> Path:
    """Write `stack_dict` (a `forza_writer.layered_effects.LayerStack.to_dict()`
    result) to its own file, named after `stack_dict["name"]`. Overwrites an
    existing preset of the same name."""
    PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    path = PRESETS_DIR / f"{_slug(stack_dict['name'])}.json"
    path.write_text(json.dumps(stack_dict, indent=2), encoding="utf-8")
    return path


def load_preset(name: str) -> dict | None:
    """The saved `LayerStack.to_dict()` payload for `name`, or `None` if no
    matching preset exists (or its file is corrupt) -- callers can pass this
    straight to `LayerStack.from_dict` when not `None`."""
    path = PRESETS_DIR / f"{_slug(name)}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def delete_preset(name: str) -> bool:
    """True if a preset named `name` existed and was deleted."""
    path = PRESETS_DIR / f"{_slug(name)}.json"
    if not path.exists():
        return False
    path.unlink()
    return True
