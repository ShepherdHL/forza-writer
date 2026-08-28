"""Persistent GUI settings (file paths) — the "Settings" tab's backing
store. Nothing in the GUI previously survived a restart; every field reset
to hardcoded defaults on each launch. This adds a small JSON file under
Windows' per-user `%LOCALAPPDATA%`, matching this project's existing
Windows-only conventions (registry font discovery, the `.bat` launcher).

Deliberately minimal: only values the Settings tab actually exposes — the
two shared paths, visual palette, interface density, and compute backend.
Never raises — a missing or corrupt settings file falls back to defaults
rather than blocking the GUI from starting.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

SETTINGS_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "forza-writer"
SETTINGS_PATH = SETTINGS_DIR / "settings.json"

DEFAULT_SETTINGS = {
    "reference_modelbin": "user-assets/S_01.modelbin",
    "modelbin_output_dir": "data/modelbin",
    "output_dir": "data/fontpacks",
    "direct_output_dir": "data/direct",
    "image_output_dir": "data/image",
    # KFPS.exe's own path, for the Plates tab's "Send to KFPS" button
    # (subprocess.Popen([kfps_executable, geometry_json_path])). Empty by
    # default -- KFPS lives outside this repo, at whatever path this
    # specific machine happens to have it installed, so there's no sane
    # baked-in default the way the other paths above have one under
    # data/ or user-assets/.
    "kfps_executable": "",
    "palette": "charcoal",
    "density": "balanced",
    "compute_backend": "auto",
    # Generation policy (see forza_writer.generation_policy). Stored as plain
    # JSON types rather than a GenerationPolicy so this module stays free of
    # any forza_writer import — it is loaded before the rest of the app and
    # its own tests run with only tools/ on the path.
    #
    # An empty allowed list means "no restriction", not "nothing allowed";
    # that way a primitive added in a later build is available immediately
    # instead of arriving pre-disabled for anyone who ever saved settings.
    # Shape ids are validated against the real catalog at policy-construction
    # time (generation_policy.policy_from_dict), which is the only place that
    # knows what exists.
    "generation_preset": "balanced",
    "generation_allowed_shapes": [],
    "generation_preferred_shapes": [],
    "generation_fallback": "warn",
    "generation_allow_exact_cover": True,
    # Image to Text debugging output, all opt-in.
    "image_save_source": False,
    "image_save_debug": False,
    "image_debug_mode": "combined",
    # Window size/position/maximized state, restored on the next launch the
    # same way KFPS remembers its own window state -- resizing the window
    # is the opt-out, with nothing special to configure. window_geometry is
    # a plain Tk geometry string ("WxH+X+Y") for the *un-maximized* size,
    # so there's always something sensible to restore to if the window is
    # later un-maximized; empty means "no saved size yet, use the default."
    # window_maximized defaults to True (rather than empty/unset) so a
    # brand new install opens using the full screen, matching what was
    # actually asked for -- not a locked-in mode, just a first-run default
    # that this same save/restore path immediately starts overriding the
    # moment the user resizes or un-maximizes.
    "window_geometry": "",
    "window_maximized": True,
    # Shared color-picker state (tools/gen_modelbin_gui/color_picker_widget.py),
    # used identically by every tab's picker. saved_colors/recent_colors are
    # one shared library visible from every tab; color_ascii_art/
    # color_forza_font_text are each that *one* tab's own last-picked color,
    # kept separate because those two tabs each own a single current color
    # rather than editing color that already lives in project/layer data
    # (which is what Composer and Layer Effects edit, so they have no
    # last-color key of their own here).
    "saved_colors": {},
    "recent_colors": [],
    "color_ascii_art": [255, 255, 255, 255],
    "color_forza_font_text": [255, 255, 255, 255],
    "color_generator": [255, 255, 255, 255],
    "color_advanced": [255, 255, 255, 255],
    "color_direct": [255, 255, 255, 255],
}

# Deliberately duplicated from gui_theme.PALETTES' keys rather than
# imported — this module loads before the rest of the app and stays free
# of gui_theme's tkinter/PIL import weight. A test cross-checks the two
# sets stay in agreement, the same discipline KFPS uses for its own
# Python/QML supporter-flag duplication (see docs/GUI_THEME_SYSTEM.md).
VALID_PALETTES = {"charcoal", "slate", "eurocorp"}
VALID_DENSITIES = {"compact", "balanced", "spacious"}
VALID_COMPUTE_BACKENDS = {"auto", "cuda", "cpu"}
VALID_FALLBACKS = {"strict", "warn", "auto", "triangle"}
VALID_IMAGE_DEBUG_MODES = {"trace", "heatmap", "contours", "combined"}
# "custom" is a real, storable state: it is what the preset becomes the moment
# a user edits any individual dial.
VALID_PRESETS = {"balanced", "maximum_fidelity", "minimum_vinyl", "primitive_only", "custom"}

# Tk's own `wm geometry` string shape ("WxH+X+Y" / "WxH-X-Y" / mixed signs).
# A malformed value here (hand-edited file, a future format change) falls
# back to "no saved size" rather than being handed to root.geometry() and
# raising TclError at startup.
_GEOMETRY_RE = re.compile(r"^\d+x\d+[+-]\d+[+-]\d+$")

# Defaults used before the repository data-layout cleanup. Only these exact
# values are migrated, so user-selected custom paths remain untouched.
LEGACY_PATH_DEFAULTS = {
    "reference_modelbin": {"data/S_01.modelbin", r"data\S_01.modelbin"},
    "direct_output_dir": {"data/dgen", r"data\dgen"},
}

MAX_RECENT_COLORS = 10
MAX_SAVED_COLOR_NAME_LEN = 40


def _valid_rgba(value) -> list[int] | None:
    """A well-formed [r, g, b, a], each 0-255, or None."""
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        channels = [int(v) for v in value]
    except (TypeError, ValueError):
        return None
    if not all(0 <= v <= 255 for v in channels):
        return None
    return channels


def _validated(settings: dict) -> dict:
    """Return known settings with invalid enum-like values reset safely."""
    result = dict(DEFAULT_SETTINGS)
    result.update({k: v for k, v in settings.items() if k in DEFAULT_SETTINGS})
    for key, old_defaults in LEGACY_PATH_DEFAULTS.items():
        if result[key] in old_defaults:
            result[key] = DEFAULT_SETTINGS[key]
    if result["palette"] not in VALID_PALETTES:
        result["palette"] = DEFAULT_SETTINGS["palette"]
    if result["density"] not in VALID_DENSITIES:
        result["density"] = DEFAULT_SETTINGS["density"]
    if result["compute_backend"] not in VALID_COMPUTE_BACKENDS:
        result["compute_backend"] = DEFAULT_SETTINGS["compute_backend"]
    if result["generation_fallback"] not in VALID_FALLBACKS:
        result["generation_fallback"] = DEFAULT_SETTINGS["generation_fallback"]
    if result["generation_preset"] not in VALID_PRESETS:
        result["generation_preset"] = DEFAULT_SETTINGS["generation_preset"]
    if result["image_debug_mode"] not in VALID_IMAGE_DEBUG_MODES:
        result["image_debug_mode"] = DEFAULT_SETTINGS["image_debug_mode"]
    # Shape lists are only type-checked here; whether an id names a real
    # primitive is the catalog's business, not this module's.
    for key in ("generation_allowed_shapes", "generation_preferred_shapes"):
        value = result[key]
        if not isinstance(value, (list, tuple)):
            result[key] = list(DEFAULT_SETTINGS[key])
        else:
            result[key] = [str(item) for item in value]
    for key in ("generation_allow_exact_cover", "image_save_source", "image_save_debug"):
        result[key] = bool(result[key])
    result["window_maximized"] = bool(result["window_maximized"])
    if not isinstance(result["window_geometry"], str) or not _GEOMETRY_RE.match(result["window_geometry"]):
        result["window_geometry"] = DEFAULT_SETTINGS["window_geometry"]

    for key in ("color_ascii_art", "color_forza_font_text", "color_generator",
                "color_advanced", "color_direct"):
        result[key] = _valid_rgba(result[key]) or list(DEFAULT_SETTINGS[key])

    recent = result["recent_colors"]
    if isinstance(recent, list):
        cleaned = [c for c in (_valid_rgba(item) for item in recent) if c is not None]
    else:
        cleaned = []
    result["recent_colors"] = cleaned[:MAX_RECENT_COLORS]

    saved = result["saved_colors"]
    cleaned_saved = {}
    if isinstance(saved, dict):
        for name, value in saved.items():
            if not isinstance(name, str) or not name.strip():
                continue
            rgba = _valid_rgba(value)
            if rgba is not None:
                cleaned_saved[name.strip()[:MAX_SAVED_COLOR_NAME_LEN]] = rgba
    result["saved_colors"] = cleaned_saved
    return result


def update_settings(partial: dict) -> dict:
    """Merge `partial` onto the *current on-disk* settings and save the
    result, rather than onto DEFAULT_SETTINGS -- `save_settings` fills any
    key absent from what you pass it with the hardcoded default, so calling
    it directly with a small partial dict (e.g. just a color) would silently
    reset every other saved setting (window geometry, output paths, ...)
    back to defaults. This is the safe way to persist one or two fields at
    a time; see shell.py's _on_close for the hand-written version of this
    same pattern.
    """
    current = load_settings()
    current.update({k: v for k, v in partial.items() if k in DEFAULT_SETTINGS})
    save_settings(current)
    return current


def load_settings() -> dict:
    """Return saved settings merged over the defaults — any key missing
    from (or the file itself missing, or the file unreadable/corrupt)
    falls back to `DEFAULT_SETTINGS` rather than raising."""
    settings = dict(DEFAULT_SETTINGS)
    try:
        saved = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        if isinstance(saved, dict):
            settings = _validated(saved)
    except (OSError, ValueError):
        pass
    return _validated(settings)


def save_settings(settings: dict) -> None:
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    merged = _validated(settings)
    SETTINGS_PATH.write_text(json.dumps(merged, indent=2), encoding="utf-8")
