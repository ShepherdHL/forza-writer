"""Shared color-picker persistence: presets, and the saved/recent color
library every tab's picker instance shares (tools/gen_modelbin_gui/
color_picker_widget.py's ColorPickerWidget, `_LIVE_INSTANCES` cross-instance
sync). The picker's own rendering/interaction math (SB square, hue strip,
RGB<->HSL/HSB conversion) is reimplemented directly in
frontend/js/color-picker.js rather than round-tripped through this handler
on every drag pixel -- it's the same standard, well-defined HSV math
forza_colors.py itself documents as "just colorsys.hsv_to_rgb" under a
different unit convention, so duplicating the *formula* carries no drift
risk the way duplicating *state* would. What must stay server-side is
anything persisted: the saved/recent library and settings_key self-drive
colors, both via gui_settings, the single source of truth.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import gui_settings  # noqa: E402
from gen_modelbin_gui.color_picker_widget import _BASIC_PRESET_COLORS  # noqa: E402


def _rgba_to_hex(rgba) -> str:
    r, g, b = rgba[0], rgba[1], rgba[2]
    return f'#{r:02x}{g:02x}{b:02x}'


def _library_payload() -> dict:
    settings = gui_settings.load_settings()
    return {
        'saved': [{'name': name, 'rgba': rgba} for name, rgba in settings['saved_colors'].items()],
        'recent': settings['recent_colors'],
    }


def register(api, window) -> None:
    def get_presets(_payload: dict) -> dict:
        return {'presets': [{'rgba': list(color), 'name': name} for color, name in _BASIC_PRESET_COLORS]}

    def get_library(_payload: dict) -> dict:
        return _library_payload()

    def save_named(payload: dict) -> dict:
        settings = gui_settings.load_settings()
        saved = dict(settings['saved_colors'])
        name = payload['name'].strip()[:gui_settings.MAX_SAVED_COLOR_NAME_LEN]
        if not name:
            raise ValueError('Name required.')
        saved[name] = list(payload['rgba'])
        gui_settings.update_settings({'saved_colors': saved})
        return _library_payload()

    def delete_saved(payload: dict) -> dict:
        settings = gui_settings.load_settings()
        saved = dict(settings['saved_colors'])
        saved.pop(payload['name'], None)
        gui_settings.update_settings({'saved_colors': saved})
        return _library_payload()

    def push_recent(payload: dict) -> dict:
        settings = gui_settings.load_settings()
        rgba = list(payload['rgba'])
        recent = [c for c in settings['recent_colors'] if c != rgba]
        recent.insert(0, rgba)
        recent = recent[:gui_settings.MAX_RECENT_COLORS]
        gui_settings.update_settings({'recent_colors': recent})
        return _library_payload()

    def get_setting_color(payload: dict) -> dict:
        settings = gui_settings.load_settings()
        value = settings.get(payload['key'])
        return {'rgba': value}

    def set_setting_color(payload: dict) -> dict:
        gui_settings.update_settings({payload['key']: list(payload['rgba'])})
        return {'ok': True}

    api.register('color_picker.get_presets', get_presets)
    api.register('color_picker.get_library', get_library)
    api.register('color_picker.save_named', save_named)
    api.register('color_picker.delete_saved', delete_saved)
    api.register('color_picker.push_recent', push_recent)
    api.register('color_picker.get_setting_color', get_setting_color)
    api.register('color_picker.set_setting_color', set_setting_color)
