# Third-party notices

forza-writer is an original implementation, but part of it — the Phase 1
built-in-font mapping — is a direct port of logic from another MIT-licensed
project, and other parts were informed by (without copying code from) further
community tools. This file documents all of it, in decreasing order of how
directly the code was used. **Before distributing forza-writer, verify the
license text below against the live upstream repositories** (linked in each
section) — some of these projects license different parts of their own
codebase under different terms, and upstream text can change after the date
this file was written (2026-08-11).

## 1. Kloudy's Forza Painter Suite (KFPS) — directly ported code

- Repo: https://github.com/heyitshestia/kloudys-forza-painter-suite
- License: MIT (per the repo's `LICENSE` file)
- Used in: [`forza_writer/shapes.py`](forza_writer/shapes.py) (the
  `VINYL_TYPE_BASES` table and character-to-shape-word mapping) and
  [`forza_writer/layout.py`](forza_writer/layout.py) (text-layout math), both
  ported from KFPS's `tools/fabric-editor/editor.js`, plus glyph data from its
  `data/fh6_font_registry.json`.

**Important nuance:** KFPS's repository ships *four* separate license files
(`LICENSE`, `LICENSE.custom-importer`, `LICENSE.fabricjs`,
`LICENSE.geometrize-gpu`), because KFPS itself incorporates code from other
projects (including bvzrays' forza-painter-fh6 lineage, below) under their
own terms. The logic forza-writer ported — the fabric-editor and font
registry — falls under KFPS's primary `LICENSE`, which is MIT-style with
copyright held by the KFPS project. Reproduce that file's exact text
verbatim (do not paraphrase it) alongside this notice before distributing;
fetch it fresh from the link above rather than copying it from here, since
we do not want to risk a transcription error in a legal document.

## 2. bvzrays forza-painter-fh6 — directly ported code (this project's own prior work)

- Repo: https://github.com/bvzrays/forza-painter-fh6
- License: MIT (with upstream credit in its own `LICENSE` to AE/forza-painter,
  Sam Twidale/geometrize-lib, and Michael Fogleman/Primitive)
- Used in: [`forza_writer/legacy_primitive_fit.py`](forza_writer/legacy_primitive_fit.py),
  a faithful port of two functions from that repo's `src/text/geometry.py`
  (as shipped in v1.9.5): `_render_horizontal_ltr_mask` (glyph rasterization)
  and `decompose_mask_to_rectangles` (the greedy grid-to-rectangle merge
  algorithm) — ported near-verbatim, kept as an independent "legacy" json
  generation strategy alongside forza-writer's own vector-outline fitter.
  Both the original code in `forza-painter-fh6` and this port were written
  by this project's own author (originally with Cursor, later contributed
  upstream into bvzray's repo) — no third-party authorship is involved here,
  but it's documented anyway for provenance, matching this file's own
  discipline for every other piece of reused code.
- Also used in: [`forza_writer/forza_colors.py`](forza_writer/forza_colors.py),
  ported near-verbatim from that same repo's `src/forza_colors.py` (RGB/HSL/
  HSB/Forza-H,S,B color conversions, matching Bang's Forza Color Converter
  v1.3 — dxbang.github.io/forza-colors), plus one addition this project
  needed that the original lacked: `forza_hsb_to_rgb`, the inverse
  conversion. Same provenance as above — this project's own prior work.

## 3. GTPlanet Colour Creation Database — bundled data, not code

- Source: "Forza Colour Sheet (Est. 2019)," catalogued by forum users
  **Mitcho2001**, **JaCor653**, and **MadaraxUchiha** —
  [GTPlanet thread](https://www.gtplanet.net/forum/threads/forza-horizon-4-colour-creation-database-constant-work-in-progress-read-first-post.384407/#post-12589813).
  Per that thread, the database's own H,S,B recipes were originally identified
  using **Bang's Forza Color Converter v1.3** (see §1's sibling note in
  `forza_writer/forza_colors.py` — same tool, dxbang.github.io/forza-colors)
  plus official documentation from the car manufacturers themselves.
- Used in: [`assets/data/manufacturer_colors.json`](assets/data/manufacturer_colors.json)
  (built by [`tools/build_manufacturer_colors.py`](tools/build_manufacturer_colors.py)
  from the source spreadsheet's `Vehicle Colours` and `Wheel Colours` sheets),
  surfaced as the Composer tab's "Manufacturer Colors" pack
  (`forza_writer/manufacturer_colors.py`). This is data, not code — no logic
  was copied from the thread or its authors' own tooling.
- **Usage basis:** this is someone else's crowd-sourced data, not this
  project's own prior work like §2 below, and the GTPlanet thread does not
  state an explicit license for the spreadsheet itself. It is included here
  with attribution only, on the repo owner's own direct assessment of the
  GTPlanet community's norms around this database (not an independently
  verified license grant) — recorded here for that reason, same as this
  file's discipline for every other source. If you redistribute forza-writer,
  keep this credit intact; consider reaching out to the named authors if
  you're unsure the same basis applies to your use.

## 4. bvzrays forza-painter-fh6 — background research (separately, not code)

- Its `experiments/fh6_layer_dump_restore/DEVELOPMENT.md` notes on the vinyl
  layer struct (fields `0x7A`, `0xA8`, `0x58`) informed forza-writer's
  independent reverse-engineering of the same struct, unrelated to the
  ported code in §2 above — no code was copied for this part.

## 5. FH6-DBDUMPER — external tool, not a dependency

- Repo: https://github.com/matkhl/FH6-DBDUMPER
- Used as: a standalone tool run separately during development to inspect and
  test the live in-memory SQLite shape catalog. forza-writer does not bundle,
  link, invoke, or import it in any way.
  [`forza_writer/diagnostics/sqlite_watcher.py`](forza_writer/diagnostics/sqlite_watcher.py),
  which reads that same catalog for the diagnostics suite, is an independent
  implementation using Python's standard `sqlite3` module.
- Check the repo directly for its current license terms if you plan to use it
  yourself; forza-writer makes no claims about it since none of its code is
  redistributed here.

## 6. ForzaTech format research — referenced, not used directly

Background reading on the `.modelbin` and encrypted `gamedbRC.slt` formats,
used only to understand the file formats forza-writer independently
reimplements a writer for (`tools/gen_modelbin.py`), not as a source of
copied code:

- **Nenkai** — ForzaTools library
- **Doliman100** —
  [ForzaTech-extraction-tools](https://github.com/Doliman100/ForzaTech-extraction-tools),
  [ForzaTech-encryption-tool](https://github.com/Doliman100/ForzaTech-encryption-tool)
- **D3FEKT** — [ForzaTechStudio](https://github.com/D3FEKT/ForzaTechStudio)
  (which itself credits Nenkai and Doliman100 for the underlying format
  research)

Check each repo directly for current license terms before reuse.
