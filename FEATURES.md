# forza-writer — Features

Full tab-by-tab GUI walkthrough and generation-algorithm internals. See
[README.md](README.md) for setup and quick start, and
[RESEARCH.md](RESEARCH.md) for the reverse-engineering reference.

## Visual identity

The window defaults to a softened **Charcoal** dark palette with **Balanced**
spacing (`tools/gui_theme.py`). Settings also offers the cooler **Slate**
palette and Compact/Balanced/Spacious density profiles. The visual identity
retains the Syndicate (2012)-inspired corporate-HUD look with a modern
Vercel-style dark interface's refined spacing and flat tonal surfaces, a
matching dark Windows title bar, procedurally-drawn checkbox/radio glyphs in
place of the OS's stock indicators, and letter-spaced small-caps section/nav
labels. Its functional small/desktop icon (`assets/icon.ico`, built by
`tools/build_icon.py`) is the compact orange-and-white two-dot mark. The full
"FW" braille cells live in `assets/icon.png` for larger brand surfaces, while
`assets/wordmark-ja.png` is the Japanese/English title treatment. `gui_theme.py`
also doubles as the GUI's full design system — a spacing scale, wraplength
tiers, and semantic label styles (Intro/Hint/Warn/Danger/Success) every tab is
built from, so status text (a found-vs-missing path, a build that partially
failed, a batch that errored out) is colored by what actually happened rather
than reading the same muted gray regardless of outcome, and a restrained
orange accent reserved for live/selected state only — the sidebar's
active-tab indicator, the primary action button, a checked checkbox/radio —
rather than spread across the interface.

Every tab owns exactly one primary vertical scrollbar for its own content,
auto-hidden (`gui_theme.AutoHideScrollbar`) whenever that tab's content
already fits without it. A handful of panels scroll independently instead —
the font list, the font grid view, the Log, and Outputs' Fontpacks/Glyphs
lists — each with its own scrollbar that won't fight the page scroll
underneath it when you hover over it.

Forza Writer's GUI and generation features do **not** require Administrator
rights. If the GUI is launched elevated, its startup log says that it can be
started normally. The separate command-line FH6 process-memory diagnostics
are the exception: Windows may require elevation for that tool to inspect the
game process.

## The tabs

- **Generator** — pick a font and characters, choose an output mode (Custom
  Mesh / Primitive Shapes / Primitive Shapes - Legacy), and run the batch.
  Every installed font is scanned automatically in the background as soon as
  the window opens (doesn't block the UI); **Rescan Fonts** re-runs the same
  scan on demand (e.g. after installing a new font without restarting), and
  **Browse on machine…** picks one font file directly, bypassing the
  installed-font list entirely (same split as bvzray's forza-painter-fh6's own
  Text Vinyl tab). Once loaded, a row of script sub-tabs (Latin, Cyrillic,
  Greek, Japanese, Korean, Traditional/Simplified Chinese, Arabic,
  Devanagari, Thai) filters the list down to fonts that actually appear to
  support that script, detected from each font's own cmap in the background
  (see `forza_writer/script_detect.py`). Selecting a script tab also reveals
  real checkboxes for that script's alphabet in the Characters section below
  (`forza_writer/alphabets.py`) — Cyrillic, Greek, Japanese, Korean,
  Devanagari, Thai, and Arabic each get their own letter groups (checked ones
  stay selected even after switching to a different script tab), with a
  caveat shown for the handful where this tool's one-flat-shape-per-character
  model falls short of real typeset text (e.g. Arabic renders isolated
  letterforms rather than connected script). Simplified/Traditional Chinese
  offer bounded structural, punctuation, and script-variant test sets, a
  **Select only Chinese** action, and an explicit advanced **All Han
  ideographs supported by this font** option. The exact selected/supported
  glyph count is always shown; jobs of 500 or more require confirmation.
  **Entire font character map** is separately marked as advanced, so it
  cannot be confused with Chinese-only generation. Has **Halt** ("stop and
  keep" — finishes the glyph in progress, then returns a valid partial
  fontpack, `manifest.json`'s `"halted": true`) and **Abort** ("stop and
  discard" — same, then deletes every file that run wrote) buttons enabled
  while a batch is running, plus a small live-updating preview that renders
  each glyph as it finishes generating, and an **Export to KFPS…** button
  wrapping `gen_fabric_project.py` (see "Packaging a fontpack for the KFPS
  Fabric Editor" in README) without leaving the GUI.
- **Advanced Generator** — inspect an OpenType variable font's axes and named
  instances, choose a deliberate style (Regular is preferred when present) or
  enter custom axis coordinates, preview the resulting static instance, and
  generate it using the Generator tab's current characters/output settings.
  Generator includes **Send selected font to Advanced Generator…**, which
  transfers the exact current font while switching tabs. Only one instance is
  generated at a time. Output and glyph filenames include an axis identity
  such as `WGHT400`, manifests retain the original variable font and selected
  coordinates, and **Open this instance in Configurator** keeps glyph
  overrides specific to that exact instance rather than sharing a Thin repair
  with Bold.
- **Direct Generator** — type the exact text needed and write one complete
  `.json` design without first generating a fontpack. **Image to Text** can
  instead lift a one-color font sample, hand lettering, or signature directly
  from a cropped image; Auto handles ordinary light/dark lettering and images
  with transparency, while the foreground and threshold controls allow manual
  correction. **Generate Preview** performs the fit entirely in memory; **Save
  .json…** becomes available only after a successful preview, so rejected
  attempts do not leave unwanted files. **Quality-gated primitive library**
  tries the complete Forza primitive set for each distinct glyph, then
  independently checks silhouette overlap, overshoot, edges, components, and
  holes. A primitive fit is kept only when it passes strict thresholds and
  saves layers; otherwise that glyph falls back to a spill-free Square trace.
  Repeated glyphs still reuse the selected result with the font's real
  metrics. Primitive candidates may use bounded horizontal skew (`data[5]`,
  stored as a shear slope rather than degrees) when that improves the
  independently measured fit; the exact Square fallback remains unskewed.
  Modern Direct Generation shapes complete directional runs with HarfBuzz
  before fitting. Contextual Arabic forms, required ligatures, Indic
  substitutions/reordering, kerning, and combining-mark offsets therefore use
  positioned OpenType glyph identities rather than isolated cmap characters.
  Empty-outline control/layout glyphs retain their positioning without being
  sent through geometry normalization. **Original whole-text trace**
  rasterizes the complete run before applying the legacy Square-only
  rectangle merge; this preserves the legacy tool's kerning/shaping behavior
  and intentionally exposes its much higher layer cost. The side-by-side
  methods provide a minimal reproduction path for troubleshooting generator
  differences. Generator includes **Send selected font to Direct
  Generator…**, which transfers the exact current font without clearing text
  or generation settings already entered on Direct Generator.
- **Output** — browse every fontpack under the configured output directory
  (one that has a `manifest.json`), pick a pack to see its glyphs by
  category, and preview any glyph — or browse any `.json`/`.modelbin` file
  directly, regardless of whether it belongs to a recognized pack.
- **Configurator** — the per-glyph control tab: pick a font (independent of
  Generator's own selection) to see every glyph it has, then override
  individual glyphs — force or forbid a mask (even on curved glyphs), or
  assign an already-made `.json` file (e.g. exported one-by-one from KFPS) to
  skip auto-fit for that glyph entirely. "Build fontpack" runs through the
  same background worker Generate uses; loading a font only performs a cheap
  outline inspection, while curved glyph fitting is deferred until a glyph is
  selected and runs outside the UI thread (Halt/Abort live on the Generator
  tab). See "Configuring per-glyph overrides and existing glyph files" below.
- **Composer** — type arbitrary text using an already-generated fontpack's
  glyphs (see "Composing arbitrary text from a fontpack" below), then style
  it: Size, Bold/Italic/Underline/Strikethrough, letter/line spacing, and a
  Solid/Gradient/Rainbow fill color, all applied on top of the base layout
  without touching glyph generation. The Layer Effects tab builds on this
  with reusable, presettable layer effects for a composed design.
- **Settings** — the reference `.modelbin` path and separate output
  directories for each generation workflow, persisted to
  `%LOCALAPPDATA%\forza-writer\settings.json`, and generation processor.
  **Auto** prefers NVIDIA CUDA, falling back to CPU when CUDA/CuPy is
  unavailable; explicit CUDA and CPU choices are also available. AMD/Intel
  GPU acceleration is available as an experimental DirectML backend — see
  [docs/DIRECTML_ACCELERATION.md](docs/DIRECTML_ACCELERATION.md).
- **Credits** — attribution for third-party code, data, and research this
  project incorporates or drew on; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
  for the complete legal notices.

## Generating a full fontpack, in detail

`tools/gen_fontpack.py` generates every renderable character in a font's
cmap in one batch, sorted into Unicode-aware category folders (`Uppercase/`,
`Lowercase/`, `Letters/`, `Numbers/`, `Punctuation/`, `Symbols/`) with a
`manifest.json` cataloging every glyph — codepoint, category, output file,
vertex/triangle counts, and validation status — plus which characters were
skipped and why (whitespace and other glyphs with no visible geometry aren't
generated).

Primitive JSON output goes to `data/fontpacks/<prefix>/` by default, while
`.modelbin` output goes to `data/modelbin/<prefix>/` (`--out-dir` overrides
either default). Categorization is by Unicode general category
(`forza_writer/charset.py`), not by font-internal glyph order, so it works
for any font. Uncased writing systems (Han, Hangul, Kana, Arabic, and others)
go into `Letters/`, never `Symbols/`; the Generator's Symbols checkbox
selects only true Unicode symbol categories.

`tools/gen_modelbin.py`'s earcut triangulation and
`forza_writer/primitive_fit.py`'s silhouette rasterizer both used to assume a
glyph's first contour is always its outer boundary and every other contour
is a hole cut from it — wrong for decorative/display fonts with disjoint
components (separate accent marks, dots, swash flourishes), which can list a
small decorative contour before the main letterform and get it triangulated
backwards. Both now determine fill-vs-hole by actual geometric nesting
instead of contour order (`gen_modelbin.group_contours_by_nesting`, one
earcut() call per disjoint island; `primitive_fit.rasterize_contours`,
even-odd XOR fill).

### Choosing what gets generated: `--output {modelbin,json,json_legacy}`

By default `gen_fontpack.py` only generates `.modelbin` (the custom vector
mesh path — requires a catalog hijack + `Vinyls.zip` injection to actually
render in-game; see [RESEARCH.md](RESEARCH.md)). Pass `--output json` to
instead generate a **primitive-composition** JSON per glyph: a shape list
built entirely out of FH6's built-in "Primitives" shape catalog (Square,
Circle, Triangle, Star, rings, etc. — see `forza_writer/primitive_shapes.py`),
approximating the glyph's silhouette with a small greedy shape-fitting search
(`forza_writer/primitive_fit.py`). This mode needs **no reference modelbin,
no catalog hijack, and no modified game files** — every shape it places
already exists in FH6 today.

Primitive JSON fitting defaults to `--compute-backend auto`: batched
candidate scoring runs on NVIDIA CUDA when `requirements-cuda.txt` is
installed, while Pillow outline/template preparation and final local
refinement remain on the CPU. Use `--compute-backend cuda` to require CUDA
(and fail clearly if it is unavailable), or `--compute-backend cpu` for
deterministic CPU-only operation. Each fontpack manifest records the
requested backend, resolved backend, and GPU device name.

User-facing GUI and CLI runs keep generation variants in separate pack
directories. The directory name includes output mode, resolved processor,
and Curve Smoothness — for example `NOTO-SANS-JP__JSON-CUDA-CS1` versus
`NOTO-SANS-JP__JSON-CPU-CS1`. Repeating the same profile updates that
profile, but CPU/CUDA comparisons and different smoothness settings no
longer overwrite one another. The manifest retains the original logical
prefix and records the full generation profile.

**Curve Smoothness** (`--curve-segments`) controls how many straight
segments approximate each Bezier curve in the source font before geometry is
generated. At `1`, every curve becomes a single straight chord, so rounded
characters can become angular and small curved details can disappear.
Higher values follow the font outline more faithfully at the cost of more
source points and processing; `8` is the balanced default. It affects Custom
Mesh and modern Primitive Shapes generation, while the Legacy generator uses
its own raster-tracing process.

`--output json_legacy` generates the same kind of primitive-composition
JSON, but via a completely different, independently-tuned algorithm: a
faithful port of the original text-vinyl generator
(`forza_writer/legacy_primitive_fit.py`) that was later contributed into
bvzray's `forza-painter-fh6` and shipped in v1.9.5. It rasterizes the glyph
with PIL rather than tracing font outlines, then greedily merges filled grid
cells into rectangles — a fundamentally different (and typically much
finer-grained) decomposition than the vector-outline fitter above. Kept as a
known, independent reference; may produce better results than the modern
fitter on some fonts.

#### Two fitting strategies, routed per glyph

`primitive_fit.fit_placements()` picks a strategy from the glyph's own
geometry, because no single algorithm handles both blocky and curved
letterforms well:

- **Rectilinear glyphs** (every contour edge horizontal or vertical — blocky
  stencil fonts like Amarillo USAF) go to an exact rectangle decomposition
  (`forza_writer/rect_decompose.py`). The answer is computed, not searched
  for: the cover is exact (IoU 1.0), it's effectively instant, and each
  rectangle becomes one Square scaled independently on X and Y.
- **Everything else** goes to the greedy primitive search, which
  approximates curves with a handful of shapes where rectangles would need
  dozens.

This routing matters a lot. Measured on Amarillo USAF, `E` went from **9
shapes at IoU 0.855 → 4 shapes at IoU 1.000** (matching a hand-made vinyl
pack of the same font exactly), while `O` stays at a handful of shapes
rather than the 18 rectangles an unrouted decomposition would emit. Across a
22-glyph sample the pack got 16% smaller *and* more accurate; the full
68-glyph pack averages 5.4 shapes/glyph.

The search path also refines each candidate's position and per-axis scale
after the coarse pass, which recovers most of the benefit of continuous
(unquantized) aspect ratios — the discrete scale×aspect ladder alone can
only express three aspect ratios, and a blocky `E` needs ratios (0.19, 2.91,
1.33) that all fall outside it.

Perf: rectilinear glyphs are ~instant; searched glyphs run ~1-3s each at the
default resolution, so a full ~70-glyph pack takes a couple of minutes.
Tunable via `primitive_fit`'s `resolution`/`max_layers`/`quality_target`.
Optional Rust CPU acceleration for the candidate-scoring hot path is
described in [docs/RUST_CPU_ACCELERATION.md](docs/RUST_CPU_ACCELERATION.md).

### Stencil mode: a third rectilinear strategy, compared automatically

For rectilinear glyphs, `forza_writer/rect_decompose.py` also tries a
**stencil** decomposition alongside the direct fill: one large background
Square sized to the glyph's own bounding box, plus FH6 **mask** layers
(`data[6]=1`, `"mask": true` — punches transparency through whatever's below)
cut into its negative space, revealing the letterform. Both are exact
(zero-error) covers on a rectilinear glyph, so this is a pure shape-count
comparison — whichever needs fewer layers wins, direct wins ties. On real
Amarillo USAF glyphs stencil never actually wins (its strokes are already
the simpler side of the shape), but it does on shapes where the *background*
is simpler — e.g. a comb/prong shape needs one rectangle per prong to fill
directly, but only one cutout per *gap* between prongs as a stencil, and
there's always one fewer gap than prong. This isn't just a synthetic case —
it's a real win on real fonts too: the Standard Galactic Alphabet's `X` needs
14 shapes filled directly vs. 10 as a stencil, `Z` needs 12 vs. 7.

Mask-layer rendering follows forza-painter-fh6's own convention exactly
(`color=(0,0,0,255)`, `data[6]=1`, `"mask": true`) but **hasn't been
confirmed against a live FH6 session in this project yet** — a fontpack that
used stencil mode anywhere gets an `"experimental"` note in its
`manifest.json` so that's never silently assumed. Stencil mode is scoped to
individual glyphs for now: masks apply by z-order across a whole shared
layer stack, so combining multiple stencil'd glyphs into one multi-character
composition isn't attempted here.

Pass `--no-stencil` (CLI) or uncheck "Allow layer masks (stencil mode)"
(GUI, Generator tab) to opt out of stencil entirely and force direct fill
everywhere — trades away stencil's shape-count savings on glyphs where it
would have won, in exchange for using only the long-verified plain-fill path
with no mask layers at all.

That checkbox is a blanket default; the **Configurator** tab (see
"Configuring per-glyph overrides and existing glyph files" below) overrides
it per individual glyph — including forcing a mask onto a *curved* glyph,
which the automatic comparison above never attempts on its own (curved
glyphs get a mask-cutout stencil via a greedy search over the negative
space, `primitive_fit._curved_stencil_placements`, rather than an exact
rectangle decomposition — reported as `"stencil_search"` in the manifest,
distinct from rectilinear stencil's `"stencil"`).

## Preview a generated file

There's deliberately no in-app shape editor — KFPS's own Fabric Editor is far
more capable, and the fabric-project export already hands glyphs to it. What
the GUI does have is a **read-only preview** (`tools/file_preview.py`, wired
into the **Outputs** tab): browse a generated fontpack's glyphs, or point it
at any `.json`/`.modelbin` file directly, and see an actual rendering, not
just raw numbers.

- `.json` renders the shape stack the way FH6 actually draws it — including
  stencil-mode mask shapes genuinely erasing back to background, not just a
  coverage diagnostic.
- `.modelbin` reads the flat 2D triangle mesh back out
  (`gen_modelbin.read_mesh_triangles`) and rasterizes it as a filled
  silhouette.

Both fall back to a clear placeholder message instead of raising on a
malformed file, matching `font_preview.py`'s existing discipline.

## Configuring per-glyph overrides and existing glyph files

The GUI's **Configurator** tab is the per-glyph control surface for a font:
pick one (its own font field, decoupled from Generator's — a "Use current
from Generator" button copies Generator's selection over on demand) and it
lists every glyph the font has, via `forza_writer/charset.py::charset_from_font`
— reviewing/overriding the font's whole glyph set is the point, so unlike
Generator's category checkboxes, nothing here restricts what a later
Generate run actually produces. Selecting a row shows a live preview and
four per-glyph choices:

- **Auto** — the default: let `primitive_fit.fit_placements` decide (see
  "Stencil mode" above).
- **Force Mask** — force a mask-cutout stencil for this glyph even if auto
  would've picked direct fill, or even if the glyph is curved (never
  possible via the "Allow layer masks" checkbox alone — see
  `primitive_fit._curved_stencil_placements`). The detail panel reports the
  resulting shape count and, for a curved glyph, the IoU cost of forcing it
  (the cutout cover is a search, not an exact decomposition, so it can fall
  slightly short of the true outline).
- **Force No Mask** — always direct-fill this one glyph, regardless of the
  global checkbox.
- **Assign file…** — point at an existing `.json` file (e.g. exported
  one-by-one from KFPS, or made outside this tool entirely); auto-fit is
  skipped for that glyph and the file's shapes are copied verbatim
  (`strategy: "manual"` in the manifest). Switching a manually-assigned
  glyph back to Auto/Force Mask/Force No Mask drops the assignment.

"Reset all to Auto" and "Force mask on all eligible rectilinear glyphs"
apply in bulk (the latter never touches a manually-assigned glyph). Every
choice is saved immediately, per font, to
`%LOCALAPPDATA%\forza-writer\glyph_overrides.json` — both Configurator's own
"Build fontpack" and Generator's "Generate" reload it fresh for whichever
font they're about to build, so an override applies regardless of which tab
you actually click Build/Generate from. "Build fontpack" builds the font's
whole glyph set (Primitive Shapes/JSON output only) through the same
background worker Generate uses — Halt/Abort and live per-glyph progress are
the Generator tab's widgets, since both share one worker thread; switch tabs
mid-build to use them. The result is a fully native fontpack, usable by
Outputs, Composer, and KFPS export exactly like one Generator produced.

## Composing arbitrary text from a fontpack

The GUI's **Composer** tab (`forza_writer/text_compose.py`) types any string
using an already-generated fontpack's glyphs, with real spacing and a shared
baseline/scale — not just placing individually-generated glyph files side by
side, which would render a period the same size as a capital M (each glyph
normalizes to its own ±100 box independently at generation time; composing
re-derives a shared font-wide scale and the font's actual baseline instead).
Point it at a fontpack folder (containing `manifest.json`), type multi-line
text (`\n` splits lines; no auto-wrap), pick an alignment, and Compose:

- **Left** — no shift, the default.
- **Right** / **Center** — each line shifted by the full/half difference
  between its width and the widest line in the block.
- **Justify** — slack distributed across a line's inter-word gaps (falls back
  to inter-character gaps for a single-word line); the last line of a
  multi-line block stays left-aligned, standard typographic convention.

Characters with no generated glyph in the pack are skipped and reported as a
warning rather than raising. Save writes a normal `fh6_typecode_json_export_v1`
JSON file — the same format every other generated glyph file uses.

The **Style** section (`forza_writer/text_style.py`) applies on top of that
base layout, since every emitted shape already carries its own `"color"` and
`"mask"` — no glyph regeneration needed:

- **Size** — a percentage multiplier on the shared font-wide scale; scales
  spacing and line height along with the glyphs.
- **Bold** / **Italic** — reshape each shape's existing `data` fields in
  place (scale for Bold, FH6's own per-shape shear slope for Italic) rather
  than duplicating shapes, so neither adds vinyl layers. Bold leaves mask
  (counter/cutout) shapes unscaled, which is also what shrinks a letter's
  counter the way a real bold weight does.
- **Underline** / **Strikethrough** — one bar shape per line, positioned
  from the font's own `post`/`OS/2` underline/strikeout metrics.
- **Letter spacing** / **Line spacing** — additional real-unit gap between
  characters, and a percentage multiplier on line height.

These apply to the whole composed block. Color is different: it's set **per
line**, in a "Per-line color" list below the text box — each line
independently picks **Solid** (one color), **Sequence** (an editable list of
color stops, either smoothly **Blended** across the line or repeated as
discrete **Stepped** bands — a 2-stop Blend reproduces a gradient, a 7-stop
Step with the ROYGBIV preset reproduces a rainbow band), or **Rainbow** (a
continuous hue sweep across just that line). Mask shapes are never
recolored, so a letter's cutout stays whatever the fontpack generated it as.
Outline and drop-shadow effects are deliberately not included in Composer
itself: both would need offset-duplicated shape copies, multiplying the FH6
vinyl layer count (e.g. an 8-direction outline turns 50 shapes into 450) —
the **Layer Effects** tab (`forza_writer/layered_effects.py`) takes on that
cost deliberately, as an opt-in, separately presettable step.

Clicking any color swatch opens it in the **Color** panel alongside the
per-line list — editable Hex/RGB/Alpha fields, read-only HSL/HSB/Forza-H,S,B
readouts (`forza_writer/forza_colors.py`, matching Bang's Forza Color
Converter — a link to the live tool is right there too), a **Basic** preset
swatch grid, and a **Manufacturer Colors** pack: a searchable, filterable
10,997-color database of real manufacturer paints (catalogued by Mitcho2001,
JaCor653, and MadaraxUchiha on GTPlanet — see `THIRD_PARTY_NOTICES.md` §3,
and `forza_writer/manufacturer_colors.py`), each entry keeping the source's
exact H,S,B slider-click notation so the precise in-game shade is
reproducible, not just an approximation.
