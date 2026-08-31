# forza-writer

<p align="center"><img src="assets/wordmark-ja.png" alt="Forza Writer: フォルツァ・ライター" width="720"></p>

Forza Writer is a tool designed to translate text to Forza Vinyls using fonts
on a user's machine. Text can be formatted and configured in this tool, then
exported to another vinyl editor for cleanup and import into the game.

The main driver of this project, as well as the original version used in the
[fork](https://github.com/ShepherdHL/forza-painter-fh6) of bvzrays'
forza-painter-fh6, is that Forza Horizon 6 does not support non-Latin text in
vinyl creation. Forza Writer is made with the intent to let users write in
alphabets outside of Latin. It includes generation for CJK (Chinese, Japanese
and Korean), Cyrillic, Greek, Arabic, Hebrew, Devanagari and Thai alphabets.

This tool was originally developed as a means of exploring the proprietary
`.modelbin` file format used in the ForzaTech engine. It was designed to
translate glyphs from font files directly into modelbin files that could be
injected into Forza Horizon 6, hence the name "Writer."

The purpose of publishing this tool is for research and development into
Forza Painter tools.

This tool alone does not write files to Forza Horizon 6 memory. Forza Writer is
considered a sister tool to Forza Painter and Kloudy's Forza Painter Suite
(KFPS). Assets generated from this tool can be exported as either `.json`
files or projects which can be opened and further edited in the KFPS Vinyl
Editor.

- Full reverse-engineering reference (memory layout, shape catalog, database
  findings and `.modelbin` format): [RESEARCH.md](RESEARCH.md)
- Full tab-by-tab GUI walkthrough and algorithm internals: [FEATURES.md](FEATURES.md)

## Quick start (GUI)

Forza Writer has two GUIs over the same Python backend and the same
`data/`/`user-assets/`/settings files, so switching between them mid-project
is safe:

- `Forza Writer.bat`: the original Tkinter GUI. Full feature set.
- `Forza Writer (Web).bat`: a newer pywebview-based GUI (WebView2), actively
  being migrated toward replacing the Tkinter one. All 13 tabs are ported.
  A handful of secondary cross-tab shortcuts and convenience buttons
  haven't caught up yet, since the web app doesn't share live state across
  tabs the way the Tkinter app's single object graph does. If something's
  missing there, the Tkinter app still has it.

Either one launches using whatever Python is on your PATH, no command line
needed, and prefers the repo's `.venv` when present.

1. `pip install -r requirements.txt` once, beforehand.
2. NVIDIA users can additionally run
   `pip install "cupy-cuda12x[ctk]>=14.1,<15"` to enable the CUDA path (the
   same line is in `requirements.txt`, commented out).
3. Launch `Forza Writer.bat` or `Forza Writer (Web).bat`.

No administrator rights are required for either GUI or generation features
(the separate command-line FH6 process-memory diagnostics tool is the one
exception, since Windows may require elevation for it to inspect the game
process).

Everything below this point is the command-line path, for scripting and
automation or anything not yet exposed in either GUI.

## Features

**MODELBIN translation**

Can translate any font on a user's machine to the proprietary MODELBIN
format used in Forza Horizon 6. Requires reference `.modelbin` files from a
Forza Horizon 6 installation (see "Required asset" below).

**Shape fitting (`.json`)**

Analyzes each glyph and approximates it using Forza's full primitive-shape
library, with optional masks.

**Pixel tracing (`.json`)**

Rasterizes text, then combines filled pixels into rectangular vinyl layers.

## Generation methods

**Standard: full font generation**

Generate all of the glyphs in a single font.

**Advanced: complex font generation**

Standard generation, but with significantly more control over how each
individual glyph is generated. Intended primarily for variable and OpenType
fonts.

**Direct: instant, lower effort generation**

Generate a small snippet of text. Ideal for users who don't wish to generate
an entire font.

**Lettering image (image to text)**

A feature designed to scan and recreate complex fonts or signatures from
images. Generates an exact monochrome trace of the subject in the image.

**ASCII art**

A charming but layer and resource intensive form of expression. Was
implemented primarily for testing. To minimize layer cost, it only uses the
original primitive shapes in Forza Horizon 6.

See [FEATURES.md](FEATURES.md) for the full walkthrough of every GUI tab and
each generation method's internals.

## Required asset: `user-assets/S_01.modelbin`

`tools/gen_modelbin.py` needs a reference FH6 vinyl `.modelbin` file to copy
material, mesh and vertex-layout chunks from when building a new custom
shape. This file is not included in this repository. It's a game asset
extracted from Forza Horizon 6's `media\Livery\Vinyls.zip`, and
redistributing it would not be appropriate.

To use `gen_modelbin.py`, supply your own copy from a legally owned FH6
install:

1. Locate `Vinyls.zip` in your FH6 install, typically:
   `<FH6 install dir>\media\Livery\Vinyls.zip`
2. Extract `S_01.modelbin` from that archive.
3. Copy it into this repo at `user-assets/S_01.modelbin`.

Both GUIs' Settings tab can do all three steps for you: click Detect next to
Reference Modelbin to search an Xbox app, Microsoft Store, or Steam install
for `Vinyls.zip` and extract `S_01.modelbin` automatically (see
`tools/game_locator.py`). The Settings tab also offers Detect for the KFPS
executable path, searching common install locations for `KFPS.exe`.

Once in place, `gen_modelbin.py` picks it up automatically via
`--reference-modelbin` (default `user-assets/S_01.modelbin`), or point it at
a different file or shape with `--reference-modelbin <path>`.

You'll also need a font file of your own, passed with `--font-file <path to
a .ttf/.otf>`.

## Packaging a fontpack for the KFPS Fabric Editor

```
python tools/gen_fabric_project.py --fontpack-dir data/fontpacks/ARIAL
```

Wraps a fontpack's `--output json` glyphs into a `.fabric-project.json` file
that KFPS's Fabric Editor can open directly, with a reference grid image as a
tracing aid. Requires the fontpack to have been generated with `--output
json` or `--output json_legacy`. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
for the KFPS format and license context.

## Repository data layout

- `assets/`: redistributable resources shipped with Forza Writer.
- `data/modelbin/`, `data/fontpacks/`, `data/advgen/`, `data/dgen/`,
  `data/image/`: generated user output, ignored by Git.
- `research/`: checked-in reverse-engineering captures, reports,
  experiments and SQL notes.
- `user-assets/`: game-derived files supplied by the user, ignored by Git.

## License

forza-writer is licensed under the MIT License. See [LICENSE](LICENSE).

Portions are ported from third-party MIT-licensed code. See
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for the required upstream
attributions before redistributing.

## Attribution and prior art

This project builds on research and code from the FH6 modding community.

- **Directly ported code:** [`forza_writer/shapes.py`](forza_writer/shapes.py)
  and [`forza_writer/layout.py`](forza_writer/layout.py) are Python ports of
  logic from Kloudy's Forza Painter Suite (KFPS),
  [heyitshestia/kloudys-forza-painter-suite](https://github.com/heyitshestia/kloudys-forza-painter-suite)
  (MIT License). Phase 1's output is byte-identical to KFPS's own export for
  the same input text.
- **Background research, not incorporated code:** early investigation into
  the layer memory struct drew on findings documented in bvzrays'
  forza-painter-fh6,
  [bvzrays/forza-painter-fh6](https://github.com/bvzrays/forza-painter-fh6)
  (MIT License). No code from this project was copied in.
- **External tool, not a dependency:** the live shape catalog was explored
  during development using FH6-DBDUMPER,
  [matkhl/FH6-DBDUMPER](https://github.com/matkhl/FH6-DBDUMPER), a standalone
  tool run separately and never bundled or invoked by forza-writer.
- **Format research referenced, not used directly:** background on
  ForzaTech's `.modelbin` and `gamedbRC.slt` formats came from public
  write-ups and tools by Nenkai (ForzaTools), Doliman100
  ([ForzaTech-extraction-tools](https://github.com/Doliman100/ForzaTech-extraction-tools)
  and [ForzaTech-encryption-tool](https://github.com/Doliman100/ForzaTech-encryption-tool))
  and D3FEKT ([ForzaTechStudio](https://github.com/D3FEKT/ForzaTechStudio)).
  forza-writer's own `.modelbin` writer was built from first-principles
  reverse-engineering, not from any of these tools' code.

See [FEATURES.md](FEATURES.md) for full technical detail and
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for the complete required
attributions.
