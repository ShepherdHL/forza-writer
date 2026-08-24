# forza-writer

<p align="center"><img src="assets/wordmark-ja.png" alt="Forza Writer — フォルツァ・ライター" width="720"></p>

Renders custom text as native Forza Horizon 6 vinyl layers by writing shape IDs
directly into FH6's process memory.

- Full reverse-engineering reference (memory layout, shape catalog, database
  findings, `.modelbin` format): [RESEARCH.md](RESEARCH.md)
- Full tab-by-tab GUI walkthrough and algorithm internals: [FEATURES.md](FEATURES.md)

## Quick start (GUI)

Double-click **`Forza Writer.bat`** in the repo root. It launches the fontpack
generator GUI using whatever Python is on your PATH — no command line needed.
It prefers the repo's `.venv` when present.

1. `pip install -r requirements.txt` once, beforehand.
2. NVIDIA users can additionally run `pip install -r requirements-cuda.txt` to
   enable the CUDA path.
3. Launch `Forza Writer.bat`.

No Administrator rights are required for the GUI or generation features. (The
separate command-line FH6 process-memory diagnostics tool is the one
exception — Windows may require elevation for it to inspect the game process.)

Everything below this point is the command-line path, for scripting/automation
or anything not (yet) exposed in the GUI.

## Features at a glance

The GUI is organized into seven tabs, picked from the left-hand sidebar. See
[FEATURES.md](FEATURES.md) for the full walkthrough of each.

- **Generator** — pick a font and characters, choose an output mode, and run
  a batch fontpack generation.
- **Advanced Generator** — generate from a specific instance of a variable
  font (weight, width, etc.).
- **Direct Generator** — write one complete text design directly, without
  generating a full fontpack; includes an image-to-text tracer.
- **Output** — browse and preview generated fontpacks and raw glyph files.
- **Configurator** — override how individual glyphs are generated, or assign
  hand-made glyph files.
- **Composer** — lay out and style arbitrary text from an existing fontpack
  (size, bold/italic, spacing, color).
- **Settings** — reference file paths, output directories, and GPU/CPU
  processor selection.

## Required asset: `user-assets/S_01.modelbin`

`tools/gen_modelbin.py` needs a reference FH6 vinyl `.modelbin` file to copy
material, mesh, and vertex-layout chunks from when building a new custom
shape. **This file is not included in this repository** — it's a game asset
extracted from Forza Horizon 6's `media\Livery\Vinyls.zip`, and redistributing
it would not be appropriate.

To use `gen_modelbin.py`, supply your own copy from a legally owned FH6
install:

1. Locate `Vinyls.zip` in your FH6 install, typically:
   `<FH6 install dir>\media\Livery\Vinyls.zip`
2. Extract `S_01.modelbin` from that archive.
3. Copy it into this repo at `user-assets/S_01.modelbin`.

Once in place, `gen_modelbin.py` picks it up automatically via
`--reference-modelbin` (default `user-assets/S_01.modelbin`), or point it at a
different file/shape with `--reference-modelbin <path>`.

You'll also need a font file of your own — pass it with `--font-file
<path to a .ttf/.otf>`.

## Generating a full fontpack

```
python tools/gen_fontpack.py --font-file "C:\path\to\AmarilloUSAF.ttf" --prefix AMARILLO-USAF
```

This generates every renderable character in the font's cmap in one batch,
sorted into category folders with a `manifest.json` cataloging every glyph.
By default it only generates `.modelbin` output. Pass `--output json` for a
primitive-composition path that needs no reference modelbin, catalog hijack,
or modified game files:

```
python tools/gen_fontpack.py --font-file "C:\path\to\AmarilloUSAF.ttf" --prefix AMARILLO-USAF --output json
```

See [FEATURES.md](FEATURES.md) for the full set of output modes
(`--output {modelbin,json,json_legacy}`), curve smoothness, compute backend
selection, and how glyph fitting is chosen per glyph.

## Packaging a fontpack for the KFPS Fabric Editor

```
python tools/gen_fabric_project.py --fontpack-dir data/fontpacks/AMARILLO-USAF
```

Wraps a fontpack's `--output json` glyphs into a `.fabric-project.json` file
that KFPS's Fabric Editor can open directly, with a reference grid image as a
tracing aid. Requires the fontpack to have been generated with `--output
json` or `--output json_legacy`. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
for the KFPS format/license context.

## Repository data layout

- `assets/` — redistributable resources shipped with Forza Writer.
- `data/modelbin/`, `data/fontpacks/`, `data/advgen/`, `data/dgen/`,
  `data/image/` — generated user output, ignored by Git.
- `research/` — checked-in reverse-engineering captures, reports,
  experiments, and SQL notes.
- `user-assets/` — game-derived files supplied by the user, ignored by Git.

## License

forza-writer is licensed under the MIT License — see [LICENSE](LICENSE).

Portions are ported from third-party MIT-licensed code; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for the required upstream
attributions before redistributing.

## Attribution & prior art

This project builds on research and code from the FH6 modding community.

- **Directly ported code:** [`forza_writer/shapes.py`](forza_writer/shapes.py)
  and [`forza_writer/layout.py`](forza_writer/layout.py) are Python ports of
  logic from **Kloudy's Forza Painter Suite (KFPS)** —
  [heyitshestia/kloudys-forza-painter-suite](https://github.com/heyitshestia/kloudys-forza-painter-suite)
  (MIT License). Phase 1's output was verified byte-identical to KFPS's own
  export for the same input text.
- **Background research, not incorporated code:** early investigation into
  the layer memory struct drew on findings documented in **bvzrays'
  forza-painter-fh6** —
  [bvzrays/forza-painter-fh6](https://github.com/bvzrays/forza-painter-fh6)
  (MIT License). No code from this project was copied in.
- **External tool, not a dependency:** the live shape catalog was explored
  during development using **FH6-DBDUMPER** —
  [matkhl/FH6-DBDUMPER](https://github.com/matkhl/FH6-DBDUMPER), a standalone
  tool run separately and never bundled or invoked by forza-writer.
- **Format research referenced, not used directly:** background on
  ForzaTech's `.modelbin` and `gamedbRC.slt` formats came from public
  write-ups and tools by **Nenkai** (ForzaTools), **Doliman100**
  ([ForzaTech-extraction-tools](https://github.com/Doliman100/ForzaTech-extraction-tools),
  [ForzaTech-encryption-tool](https://github.com/Doliman100/ForzaTech-encryption-tool)),
  and **D3FEKT** ([ForzaTechStudio](https://github.com/D3FEKT/ForzaTechStudio)).
  forza-writer's own `.modelbin` writer was built from first-principles
  reverse-engineering, not from any of these tools' code.

See [FEATURES.md](FEATURES.md) for full technical detail, and
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for the complete required
attributions.
