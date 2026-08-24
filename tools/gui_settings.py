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
from pathlib import Path

SETTINGS_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "forza-writer"
SETTINGS_PATH = SETTINGS_DIR / "settings.json"

DEFAULT_SETTINGS = {
    "reference_modelbin": "user-assets/S_01.modelbin",
    "modelbin_output_dir": "data/modelbin",
    "output_dir": "data/fontpacks",
    "direct_output_dir": "data/direct",
    "image_output_dir": "data/image",
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
}

VALID_PALETTES = {"charcoal", "slate"}
VALID_DENSITIES = {"compact", "balanced", "spacious"}
VALID_COMPUTE_BACKENDS = {"auto", "cuda", "cpu"}
VALID_FALLBACKS = {"strict", "warn", "auto", "triangle"}
VALID_IMAGE_DEBUG_MODES = {"trace", "heatmap", "contours", "combined"}
# "custom" is a real, storable state: it is what the preset becomes the moment
# a user edits any individual dial.
VALID_PRESETS = {"balanced", "maximum_fidelity", "minimum_vinyl", "primitive_only", "custom"}

# Defaults used before the repository data-layout cleanup. Only these exact
# values are migrated, so user-selected custom paths remain untouched.
LEGACY_PATH_DEFAULTS = {
    "reference_modelbin": {"data/S_01.modelbin", r"data\S_01.modelbin"},
    "direct_output_dir": {"data/dgen", r"data\dgen"},
}


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
    return result


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
