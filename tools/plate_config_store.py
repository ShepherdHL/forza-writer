"""Persistent user-saved Plate Generator configurations -- one JSON file per
saved config under the same per-user directory `gui_settings.py`/
`layer_effect_presets_store.py` already use
(`%LOCALAPPDATA%\\forza-writer\\plate_configs\\<name>.json`).

Scope is deliberately narrow: this persists exactly what the Plates tab
needs to resume a session (which template, which mode, typed field values/
overrides) as a `forza_writer.plates.instance.PlateInstance` plus a name --
not undo/redo, not other tabs' state, not a general project file. See
docs/PLATE_GENERATOR_ARCHITECTURE.md for why that's a deliberate scope
decision, not a missing feature.

Never raises -- a missing or corrupt store degrades to "no saved configs"
rather than blocking the GUI from starting, matching
`gui_settings.py`/`layer_effect_presets_store.py`'s own convention.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from gui_settings import SETTINGS_DIR

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from forza_writer.plates.instance import PlateInstance  # noqa: E402

CONFIGS_DIR = SETTINGS_DIR / "plate_configs"

_UNSAFE_NAME_CHARS = re.compile(r"[^\w \-.]+", re.UNICODE)


def _slug(name: str) -> str:
    """Filesystem-safe filename for a user-given config name. Unicode word
    characters are kept (unlike layer_effect_presets_store.py's ASCII-only
    pattern) so a config named after a non-Latin template (e.g. a Japanese
    plate's own name) doesn't collapse to a near-empty/colliding filename."""
    safe = _UNSAFE_NAME_CHARS.sub("_", name).strip() or "config"
    return safe[:80]


def list_plate_configs() -> list[str]:
    """Every saved config's display name, sorted case-insensitively. Never
    raises -- unreadable files are silently skipped."""
    if not CONFIGS_DIR.exists():
        return []
    names = []
    for path in sorted(CONFIGS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        names.append(data.get("config_name", path.stem))
    return sorted(names, key=str.lower)


def save_plate_config(name: str, instance: PlateInstance) -> Path:
    """Writes `instance` under `name`, overwriting any existing config of
    the same name. The instance's own `to_dict()` is embedded verbatim
    alongside the display name, so `load_plate_config` can hand back a real
    `PlateInstance` via `PlateInstance.from_dict` directly."""
    CONFIGS_DIR.mkdir(parents=True, exist_ok=True)
    path = CONFIGS_DIR / f"{_slug(name)}.json"
    payload = {"config_name": name, "instance": instance.to_dict()}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_plate_config(name: str) -> PlateInstance | None:
    """The saved `PlateInstance` for `name`, or `None` if no matching config
    exists or its file is corrupt/unreadable."""
    path = CONFIGS_DIR / f"{_slug(name)}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return PlateInstance.from_dict(data["instance"])
    except (OSError, ValueError, KeyError):
        return None


def delete_plate_config(name: str) -> bool:
    """True if a config named `name` existed and was deleted."""
    path = CONFIGS_DIR / f"{_slug(name)}.json"
    if not path.exists():
        return False
    path.unlink()
    return True
