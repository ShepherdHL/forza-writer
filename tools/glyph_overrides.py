"""Persistent per-glyph overrides — Configurator's backing store. Keyed by
font path (a font can be reselected across sessions and its per-glyph
choices should come back), sparse (only entries that depart from the
implicit "auto" default are stored). Same `%LOCALAPPDATA%/forza-writer/`
directory and defensive load pattern as `gui_settings.py`: a missing or
corrupt file falls back to `{}` rather than blocking the GUI from starting.

Each glyph's override is a single choice, not independent axes — a
manually-assigned file bypasses auto-fit entirely, so a mask mode doesn't
apply to it alongside a file the way "force"/"never" apply within auto-fit:

    {"<font path>": {"<char>": {"mode": "force"},
                      "<char2>": {"mode": "manual", "file": "C:/path/glyph.json"}}}

Supersedes the earlier `mask_overrides.py` (mask-mode-only, no manual-file
support) — this is a breaking format change from that module's
`mask_overrides.json`, acceptable since it's local machine state, not
shipped/exported data.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

# "auto" is the implicit default and is never stored — only an explicit
# per-glyph departure from it is worth persisting.
VALID_MODES = ("force", "never", "manual")

OVERRIDES_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "forza-writer"
OVERRIDES_PATH = OVERRIDES_DIR / "glyph_overrides.json"


def _load_all() -> dict[str, dict[str, dict]]:
    try:
        data = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, ValueError):
        pass
    return {}


def _is_valid_entry(entry) -> bool:
    if not isinstance(entry, dict) or entry.get("mode") not in VALID_MODES:
        return False
    if entry["mode"] == "manual":
        return isinstance(entry.get("file"), str) and bool(entry["file"])
    return True


def load_overrides_for_font(font_path: str | Path) -> dict[str, dict]:
    """Return `font_path`'s saved per-glyph overrides (char -> `{"mode":
    ...}` / `{"mode": "manual", "file": ...}`), or `{}` if none are saved,
    the store is missing/corrupt, or the font simply hasn't been seen
    before. Malformed individual entries (unknown mode, a "manual" entry
    missing its file) are dropped rather than raising."""
    per_font = _load_all().get(str(font_path), {})
    if not isinstance(per_font, dict):
        return {}
    return {char: entry for char, entry in per_font.items()
            if isinstance(char, str) and _is_valid_entry(entry)}


def save_overrides_for_font(font_path: str | Path, overrides: dict[str, dict]) -> None:
    """Persist `overrides` for `font_path`, merging into the existing store
    so other fonts' saved overrides are left untouched. Entries with an
    "auto" mode (or anything else invalid — see `_is_valid_entry`) are
    dropped rather than stored, since "auto" is the implicit default. If
    `overrides` has nothing left to store after that filtering, the font's
    entry is removed entirely rather than left as an empty dict."""
    all_overrides = _load_all()
    sparse = {char: entry for char, entry in overrides.items() if _is_valid_entry(entry)}
    key = str(font_path)
    if sparse:
        all_overrides[key] = sparse
    else:
        all_overrides.pop(key, None)
    OVERRIDES_DIR.mkdir(parents=True, exist_ok=True)
    OVERRIDES_PATH.write_text(json.dumps(all_overrides, indent=2, ensure_ascii=False), encoding="utf-8")
