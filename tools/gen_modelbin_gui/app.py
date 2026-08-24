"""Composes GeneratorGUI from the shell + per-tab mixins, and the entry point.

Layout: a left-hand sidebar picks one of the nine tabs listed in
`state.TABS` (Generator / Advanced Generator / Direct Generator / ASCII Art /
Glyph Inspector / Output / Composer / Settings / Credits), each its own mixin
under tabs/ — a persistent Log panel (see shell.py) stays visible across all
of them since generation/export/build actions can be kicked off from more
than one tab. Configurator is no longer a sidebar tab: `ConfiguratorTabMixin`
is still composed in below, but it now builds a collapsed, lazily-scanned
per-glyph overrides workspace embedded inside Generator's own page
(`_build_configurator_workspace`) rather than a page of its own — so it has
no entry in `state.TABS` even though it's still one of the mixins here.
All the mixins operate on one shared GeneratorGUI instance (same self.*
state throughout), so which file a method lives in is purely an
organizational split, not a behavioral one.

Usage:
    python tools/gen_modelbin_gui.py
Or double-click Forza Writer.bat in the repo root.
"""
import tkinter as tk

from .shell import ShellMixin
from .tabs.forza_font_text import ForzaFontTextTabMixin
from .tabs.generator import GeneratorTabMixin
from .tabs.outputs import OutputsTabMixin
from .tabs.configurator import ConfiguratorTabMixin
from .tabs.advanced import AdvancedTabMixin
from .tabs.direct import DirectTabMixin
from .tabs.ascii_art import AsciiArtTabMixin
from .tabs.glyph_inspector import GlyphInspectorTabMixin
from .tabs.layer_effects import LayerEffectsTabMixin
from .tabs.composer import ComposerTabMixin
from .tabs.color_picker import ColorPickerMixin
from .tabs.settings import SettingsTabMixin
from .tabs.credits import CreditsTabMixin


class GeneratorGUI(
    ShellMixin,
    ForzaFontTextTabMixin,
    GeneratorTabMixin,
    OutputsTabMixin,
    ConfiguratorTabMixin,
    AdvancedTabMixin,
    DirectTabMixin,
    AsciiArtTabMixin,
    GlyphInspectorTabMixin,
    LayerEffectsTabMixin,
    ComposerTabMixin,
    ColorPickerMixin,
    SettingsTabMixin,
    CreditsTabMixin,
):
    pass


def main():
    root = tk.Tk()
    GeneratorGUI(root)
    root.mainloop()
