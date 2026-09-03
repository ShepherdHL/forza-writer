# Forza Writer theme system

Themes are presentation data. `tools/theme_palettes/` is a small,
UI-independent package: three registered palettes plus the token contract
that validates them, with no dependency on the web app or any particular
rendering technology.

This document mirrors the shape of [Kloudy's FH6 Painter (KFPS)'s own
theme system doc](../../Forza%20Painter/KFPS/KloudysFH6Painter/KFPS.UI/docs/THEME_SYSTEM.md)
on purpose — `tools/theme_palettes/` is organized the same way KFPS
organizes its QML themes.

## Ownership

- `tools/theme_palettes/*.py` — one file per palette's data: every
  color/behavior token, plus `DISPLAY_NAME`, `DESCRIPTION`, and
  `SOLID_SELECTED_ROW`. The Python-language equivalent of KFPS's
  `Palette*.qml` files.
- `tools/theme_palettes/__init__.py` — explicit registration
  (`_REGISTRY`) and the token contract (`EXPECTED_KEYS`), validated at
  import time; the active selection (`CURRENT_PALETTE`, `PALETTE`,
  `palette()`, `set_palette()`). The equivalent of KFPS's `qmldir` +
  `Theme.qml` combined.
- `tools/gen_modelbin_web/theme_export.py` — the one consumer: generates
  `frontend/css/theme.css` from `theme_palettes.PALETTES`, one
  `html[data-theme="<slug>"] { --token: value; ... }` block per palette.
  Python stays the single source of truth for color; this module never
  hand-copies a hex value into CSS.
- `tools/gui_settings.py` — persistence and validation (`VALID_PALETTES`).
  Deliberately does **not** import `theme_palettes` (it must load before
  the rest of the app, without pulling in any UI-adjacent module), so it
  carries its own copy of the known palette names — the same
  "intentionally duplicated on both sides, with a test enforcing
  agreement" pattern KFPS's `theme_catalog.py`/QML supporter flags use.

## Palette contract

Every palette's `PALETTE` dict must have exactly the keys in
`theme_palettes/__init__.py`'s `EXPECTED_KEYS` — a mismatch (missing or
extra) raises at import time rather than surfacing as a `KeyError` the
first time some code happens to read the missing key.

Required metadata alongside `PALETTE` in each `theme_palettes/<name>.py`:

- `DISPLAY_NAME` — exact user-facing name shown in Settings.
- `DESCRIPTION` — one line, shown under the palette option when selected.
- `SOLID_SELECTED_ROW` — whether the sidebar's active nav row takes a
  full solid-accent fill (only Eurocorp today) or a restrained left-edge
  indicator strip. A generic capability flag, not a theme-name comparison
  — the same discipline KFPS's `angularControlsEnabled`/`classicMode`
  capability tokens follow.

## Current status: Eurocorp only

The web app's Settings tab reads `theme_palettes.DISPLAY_NAMES` /
`DESCRIPTIONS` / `PALETTE_ORDER` already, but its palette picker only
offers Eurocorp today (`document.documentElement.dataset.theme =
'eurocorp'` is hardcoded in `frontend/js/shell.js`) — nothing calls
`theme_palettes.set_palette()` yet. Charcoal and Slate stay registered
and fully valid (theme.css already has generated blocks for both) so
that wiring up a real selector later is CSS/JS work only, not a data
change.

## Adding a palette

1. Copy an existing `theme_palettes/*.py` file and change values without
   dropping any key `EXPECTED_KEYS` requires.
2. Give it a unique `DISPLAY_NAME` and a one-line `DESCRIPTION`.
3. Add it to `_REGISTRY` in `theme_palettes/__init__.py`.
4. Add its name to `VALID_PALETTES` in `tools/gui_settings.py`.
5. Run the validation below, then re-run `theme_export.write(...)` (or
   just relaunch the app, which does this automatically) to regenerate
   `theme.css` with the new palette's block.

## Validation

From the project root:

```bash
python -m pytest tests/tools/test_theme_palettes.py -v
```

## Token naming

Name tokens by purpose rather than appearance, matching KFPS's own rule:

- `previewSurface`/`preview_surface`, not `darkPreview`
- `rowHover`/`row_hover`, not `pinkHover`
- `primaryButtonTop`, not `goldButtonTop`

## Eurocorp

Eurocorp is a bold, literal homage to Syndicate (2012)'s corporate-HUD
identity: true black surfaces, warm white text, and a saturated amber
`accent` used broadly — solid-fill selected sidebar rows
(`SOLID_SELECTED_ROW = True`) — rather than restrained to live/selected
state.

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

The web app's animated backdrop (`frontend/js/backdrop.js`) renders this
same idea directly in the browser: a procedurally generated, continuously
drifting node network (nearest-neighbor mesh, accent diagonals, hexagon/
chevron motifs) evoking Syndicate's own menu screens.
