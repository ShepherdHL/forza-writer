# Forza Writer GUI theme system

Themes are presentation data. Page structure and workflow logic in
`tools/gen_modelbin_gui/` must not depend on a concrete palette name.

This document mirrors the shape of [Kloudy's FH6 Painter (KFPS)'s own
theme system doc](../../Forza%20Painter/KFPS/KloudysFH6Painter/KFPS.UI/docs/THEME_SYSTEM.md)
on purpose — `tools/gui_theme/` is organized the same way KFPS organizes
its QML themes, adapted to Python/Tk.

## Ownership

- `tools/gui_theme/palettes/*.py` — one file per palette's data: every
  color/behavior token, plus `DISPLAY_NAME`, `DESCRIPTION`, and
  `SOLID_SELECTED_ROW`. The Python-language equivalent of KFPS's
  `Palette*.qml` files.
- `tools/gui_theme/palettes/__init__.py` — explicit registration
  (`_REGISTRY`) and the token contract (`EXPECTED_KEYS`), validated at
  import time. The equivalent of KFPS's `qmldir` (explicit registration)
  and its `Theme.qml` contract test combined.
- `tools/gui_theme/backdrops/*.py` — optional per-theme procedural
  backdrop art. A theme with no entry in `backdrops/__init__.py`'s
  registry simply has no backdrop, the same as an empty
  `backdropComponentFile` in KFPS.
- `tools/gui_theme/indicators.py`, `output_accents.py`, `apply.py` — the
  ttk style engine and chrome that reads palette/density data and applies
  it to real widgets. This is the "consumer" side, analogous to how
  KFPS's shared QML components consume `Theme.*` tokens — it is not split
  per-theme, the same way KFPS doesn't fragment its shared components
  per-theme either.
- `tools/gui_theme/__init__.py` — palette/density selection state
  (`CURRENT_PALETTE`, `PALETTE`, `configure()`) and the full public API
  the rest of the app imports. The equivalent of KFPS's `Theme.qml`.
- `tools/gui_settings.py` — persistence and validation (`VALID_PALETTES`).
  Deliberately does **not** import `gui_theme` (it must load before the
  rest of the app, without pulling in tkinter/PIL), so it carries its own
  copy of the known palette names — the same "intentionally duplicated on
  both sides, with a test enforcing agreement" pattern KFPS's
  `theme_catalog.py`/QML supporter flags use.
- Reusable widgets and tab pages consume semantic tokens (`palette()['accent']`,
  `SOLID_SELECTED_ROW`, etc.). They must not compare `CURRENT_PALETTE`
  against a literal theme name.

## Palette contract

Every palette's `PALETTE` dict must have exactly the keys in
`palettes/__init__.py`'s `EXPECTED_KEYS` — a mismatch (missing or extra)
raises at import time rather than surfacing as a `KeyError` the first
time some widget happens to read the missing key.

Required metadata alongside `PALETTE` in each `palettes/<name>.py`:

- `DISPLAY_NAME` — exact user-facing name shown in Settings.
- `DESCRIPTION` — one line, shown under the palette radio buttons when
  that palette is selected.
- `SOLID_SELECTED_ROW` — whether the sidebar's active nav row takes a
  full solid-accent fill (only Eurocorp today) or the restrained
  left-edge indicator strip every other palette uses. A generic
  capability flag consumed by `shell.py`'s `_style_sidebar()`, not a
  theme-name comparison — the same discipline KFPS's `angularControlsEnabled`/
  `classicMode` capability tokens follow.

## Adding a palette

1. Copy an existing `palettes/*.py` file and change values without
   dropping any key `EXPECTED_KEYS` requires.
2. Give it a unique `DISPLAY_NAME` and a one-line `DESCRIPTION`.
3. Add it to `_REGISTRY` in `palettes/__init__.py`.
4. Add its name to `VALID_PALETTES` in `tools/gui_settings.py`.
5. Optionally add `backdrops/<name>.py` (a `build_backdrop(size, palette)
   -> PIL.Image` function) and register it in `backdrops/__init__.py`.
6. Run the validation below. `tools/gen_modelbin_gui/tabs/settings.py`'s
   palette radio buttons and description are driven by the registry, so
   no changes are needed there.

## Validation

From the project root:

```bash
python -m pytest tests/tools/test_gui_theme.py tests/tools/test_gui_theme_backdrops.py \
    tests/tools/gen_modelbin_gui/test_shell.py tests/tools/gen_modelbin_gui/test_settings.py -v
```

Every GUI test in this suite runs against a withdrawn or fully
transparent (`alpha=0`) Tk root — no visible window flashes during a
normal test run. Do the same in any new test rather than leaving a real
window on screen.

## Token naming

Name tokens by purpose rather than appearance, matching KFPS's own rule:

- `previewSurface`/`preview_surface`, not `darkPreview`
- `rowHover`/`row_hover`, not `pinkHover`
- `primaryButtonTop`, not `goldButtonTop`

## Eurocorp

Eurocorp is a bold, literal homage to Syndicate (2012)'s corporate-HUD
identity: true black surfaces, warm white text, and a saturated amber
`accent` used broadly — solid-fill selected sidebar rows
(`SOLID_SELECTED_ROW = True`), `Accent.TButton` — rather than restrained
to live/selected state.

An earlier, flatter "Eurocorp" palette existed before Charcoal/Slate and
was retired specifically because unrestrained orange read as generic
dashboard chrome once the design system settled on "`accent` only for
live/selected state." This palette is a deliberate reintroduction of that
unrestrained treatment, not a regression back into it — `select_fg` is
near-black rather than Charcoal/Slate's cream specifically because accent
is a broad solid fill here, not a thin highlight edge, and low-contrast
cream-on-orange text would be the result of copying that value over
unchanged.

`success` and `secondary_accent`/`info` are sampled from the reference
HUD's own on-screen data-comparison colors (a green "this run" figure and
a blue "personal best" figure) rather than invented from scratch, so the
palette's non-accent hues still trace back to the source material.

The geometric-line sidebar backdrop (`backdrops/eurocorp.py`) is a
sparse, deterministic network of thin diagonal lines — the same
procedural-PIL-drawing technique `indicators.py`'s checkbox/radio glyphs
already use, not a new rendering approach. It only renders in the
sidebar's own leftover space below the nav rows (`shell.py`'s
`_build_sidebar`/`_refresh_sidebar_backdrop`): ttk frames elsewhere in
the app are opaque, so a full-bleed backdrop can't sit under real page
content without competing with it.
