# Plate Generator architecture

The License Plate / Vanity Plate Generator turns a data-driven plate
standard plus user-typed text into ordinary Forza Writer shapes. It is a
sibling area to Composer/Layer Effects, not an extension of either.

> **Scope note (2026-08-25):** an earlier version of this feature supported
> multiple glyph-sourcing mechanisms, including live font-fitting at
> render time and a plate-specific hand-traced-glyph reader. Both were
> removed after direct feedback that the feature had grown more complex
> than needed: every plate field now draws only from a fontpack that
> already exists under `data/fontpacks/`, the same pre-generated glyph
> shapes every other Forza Writer generator uses, and
> background/border/decorations are pre-rendered into a small library
> rather than rebuilt from template data on every generation. See "Glyph
> sourcing" and "Blank plate library" below.
>
> **Scope note (2026-08-26a):** added a second template set,
> `tools/gen_plate_templates_fictional.py` -- twelve `AccuracyStatus.FICTIONAL`
> templates modeled on license plates from five video-game franchises (GTA V,
> Need for Speed, Saints Row, Halo, Cyberpunk 2077), grouped under their own
> `country` codes (`GTA`, `NFS`, `SR`, `HALO`, `CP2077`) alongside the
> real-world set's `US`/`GB`/`JP`/`DE`. See `docs/PLATE_TEMPLATE_SCHEMA.md`'s
> "Fictional (game) templates" section for how sourcing works when there's
> no government statute to cite.
>
> **Scope note (2026-08-26b):** the fontpack-only design directly above was
> itself replaced the same day, after direct feedback that pixel-traced
> plate text looked poor and cost far too many shapes for an in-game decal
> (the five proof-of-concept templates alone ranged 394-868 shapes each;
> the seventeen shipped templates now range 9-62). `CharSource` no longer
> points at a fontpack -- it names a font file read once for its metrics
> (`hhea`/`OS/2`/`hmtx`, via fontTools), and every `PlateField` renders as
> one plain placeholder box per character, correctly sized/spaced as if it
> held that font's real glyph. **Forza Writer's job on a plate's characters
> is typesetting only now -- real letterform artwork is the user's to
> supply (existing or hand-made) and fine-tune in KFPS**, where each
> placeholder box is its own addressable group
> (`GroupKind.CHARACTER`, one per typed character) ready to be swapped.
> Background/border/decorations are unaffected -- still plain generated
> shapes from `Decoration` data, still cached via the blank plate library.
> See "Glyph sourcing" below (fully rewritten) and
> `glyph_resolve.py`'s module docstring.
>
> **Scope note (2026-08-26c):** the Plates tab UI was restructured around a
> library selector (Real-World / Fictional / Community / Custom, each its
> own browsing space -- real-world and fictional plates had briefly shared
> one country-grouped tree, which is what this replaces), a drill-down
> browser with breadcrumb navigation instead of a fully-expanded tree, a
> large persistent preview that now renders live (debounced) instead of on
> a manual button click, mode terminology that adapts per library
> ("Authentic" is never forced onto fictional/community content), fields
> grouped by role, an enriched Details panel, and saved configs moved into
> a compact header menu. This was a UI-layer restructuring only -- every
> generator/validation/export/persistence call in `tabs/plates.py` is the
> same call the previous layout made; see that file's own module docstring
> for the specifics of what changed and why.

> **Scope note (2026-08-26d):** three more changes the same day, all
> user-requested: (1) `PlateInstance.placeholder_font` (1-11) swaps every
> character's plain box for one of FH6's native in-game fonts -- real,
> final letterform meshes (`forza_writer.shapes.char_to_resource`, the
> same shapes `tools/gen_modelbin_gui/tabs/forza_font_text.py`'s tab
> already uses), not generated/traced, so it costs nothing extra;
> `None` (default) keeps plain boxes. The generated file always uses the
> real choice. (2) Plates now writes to a dedicated `data/plates/` (see
> `_PLATES_OUTPUT_DIR` in `tabs/plates.py`), not a subfolder of the shared
> fontpacks output directory (which defaulted to `data/fontpacks`, so
> plate output had been landing at `data/fontpacks/plates/...`). (3) A
> "Send to KFPS" button launches KFPS.exe (path set once in Settings)
> with the generated geometry `.json`, confirmed against KFPS's own
> `main.py` to be the exact argument it expects.
>
> **Scope note (2026-08-26e):** the on-screen preview couldn't show real
> letterforms when this was first written -- this repo genuinely has no
> local mesh/outline data for FH6's native fonts. That's still true, but
> it turned out not to be the end of the story: KFPS (a separate, sibling
> local application, not part of this repo) ships a per-glyph raster
> (`Resources/Vinyls/{family}/{index}.png`) alongside its own vertex mesh
> for the exact same purpose, and reading that at preview time works.
> `file_preview.kfps_vinyls_dir` resolves that folder from the
> Settings-configured KFPS executable path; `render_composed_preview`/
> `render_json_preview` composite the real raster (tinted to the shape's
> own color via its alpha channel) in place of the plain box whenever it's
> found, falling back to the box exactly as before when KFPS isn't
> configured or that folder is missing. `_render_plates_preview` no longer
> forces `placeholder_font=None`; the caveat text now only appears when
> the fallback actually happened. A first attempt at rasterizing the raw
> vertex meshes directly (instead of the PNGs) was abandoned: some
> letters rendered mirrored and others correct with no single coordinate
> fix, meaning the raw mesh data's winding/orientation is inconsistent
> per-glyph in a way not worth chasing further given the PNGs already
> render correctly.

## Fresh checkout: nothing to build

Unlike the fontpack-only design this replaced, there is no regeneration
step needed after a fresh checkout. `assets/fonts/LiberationSans-Regular.ttf`
and `NotoSansCJKjp-Regular.otf` are committed (unlike `data/fontpacks/`,
which was gitignored and had to be rebuilt), and `data/plate_templates/`/
`data/plate_blanks/` are both committed too. Running
`python tools/gen_plate_templates.py`/`gen_plate_templates_fictional.py`
is only needed when actually adding or editing a template.

## Pipeline

```
PlateTemplate (data/plate_templates/<country>/*.json)
    |
    +-- loader.py        load + structurally validate a template
    +-- validation.py     check typed field text against the template's rules
    |
PlateInstance (user's typed values + Vanity-mode overrides)
    |
    +-- renderer.py::render_plate(template, instance)
            |
            +-- blank_library.py   background/border/decorations, pre-rendered and cached
            +-- layout_engine.py   mm -> plate-local shape-unit box geometry
            +-- glyph_resolve.py   CharSource -> one placeholder box per character, sized/spaced from real font metrics
            +-- group.py           the PlateGroupNode hierarchy alongside the shapes (one CHARACTER node per character)
            |
            v
      (shapes: list[dict], root: PlateGroupNode, warnings: list[str])
```

`shapes` is the exact same flat shape-dict format
`forza_writer.export.to_json` already produces for every other generator --
a generated plate is never locked behind a plate-specific format. `root` is
a purely organizational tree over indices into that same list (see
`forza_writer/plates/group.py`'s module docstring).

## Naming decisions

The spec's own vocabulary ("Composer", "layer", "fontpack") collides with
narrower existing meanings in this codebase. Resolved explicitly rather
than left ambiguous:

| Term | Existing/narrower meaning | This feature's decision |
|---|---|---|
| Composer | `tabs/composer.py`: one text block, N lines, each a `LineFill` | Not reused. Plate output is *sent into* the existing export pipeline; the feature is a sibling area. |
| layer | `layered_effects.py`'s `EffectLayer`/`LayerStack`: a flat, single-glyph geometric-effect stack | Not reused. `PlateGroupNode` is a new, general-purpose parent/child tree. |
| fontpack | `tools/gen_fontpack.py`'s batch TTF -> categorized glyph JSON | Not used at all by plate fields (was, until 2026-08-26b -- see the scope note above). A `PlateField` now reads a font file's metrics directly via fontTools; no fontpack is built or consulted for character rendering. |

## Package layout

```
forza_writer/plates/
    template.py        PlateTemplate, PlateField, CharSource, Decoration,
                        Provenance, FieldValidation, AccuracyStatus
    instance.py         PlateInstance, FieldOverride, DecorationOverride
    group.py             PlateGroupNode, GroupKind
    loader.py            load/validate a template; the filterable registry
    validation.py        validate_instance / is_valid_for_generation
    validation_rules.py  RULE_REGISTRY -- the only place a template can invoke Python
    layout_engine.py     pure geometry: mm-space box conversion, bbox math, alignment
    glyph_resolve.py     CharSource -> one placeholder box per character, from real font metrics
    blank_library.py       pre-rendered background/border/decoration cache
    renderer.py             template + instance -> shapes + group tree + warnings
    package_schema.py       PlatePackageManifest (schema only -- see "Community packages" below)

tools/
    plate_config_store.py     one JSON file per saved PlateInstance
    gen_plate_templates.py     builds the proof-of-concept templates
    gen_plate_templates_fictional.py  builds the fictional game-plate templates (GTA/NFS/SR/HALO/CP2077)
    gen_plate_blanks.py         builds the blank-plate library from the current templates

tools/gen_modelbin_gui/tabs/plates.py   the GUI tab
```

## Glyph sourcing: size & spacing only, never artwork

Every `PlateField` declares a `CharSource`: a `font_file` (a filename under
`assets/fonts/`, e.g. `"LiberationSans-Regular.ttf"`) plus an optional
`fallback` (another `CharSource`, used whole-swap if the primary font is
missing metrics for any character the field's text actually needs -- see
`glyph_resolve.py`'s module docstring). `glyph_resolve.py` reads that
font's real metrics via fontTools (`hhea.ascender`, `OS/2.sCapHeight`,
`hmtx` per-glyph advance widths) and lays out one plain placeholder
rectangle per non-space character -- correctly proportioned and spaced as
if it held that font's real glyph, but never that glyph's actual outline.
**No letterform geometry is ever produced for a plate character, at
render time or otherwise.**

This is the second time this mechanism has narrowed, not the first. The
original design supported three glyph sources (live font-fitting,
fontpack-only, and a plate-specific hand-traced-glyph reader); a first
simplification (2026-08-25) cut that down to fontpack-only, reasoning that
a fontpack is already the pre-generated-glyph pipeline every other Forza
Writer generator uses. That reasoning held up fine architecturally, but
missed the actual point for *this* feature: a real plate's registration
text isn't meant to be Forza Writer-generated artwork at all -- it's a
typesetting problem (where does each character go, how big, how spaced)
layered on top of artwork the user already has or will make themselves.
Pixel-traced letterforms looked poor for this bundled font at plate scale
and multiplied a plate's shape count by roughly 20-30x for no benefit the
user actually wanted (see the scope note at the top of this doc for the
measured shape counts). Cutting the "generate the letterform" half out
entirely, rather than trying to make the traced letterforms look better,
is the fix.

**What a placeholder box gives you**: correct proportions (a "W" is wider
than an "I", a hyphen is short, matching the real font's own design), a
correct cap-height-based vertical size, and correct inter-character
spacing (`tracking` still applies exactly as before) -- everything
`char_scale`/`tracking`/alignment on an existing template already meant
stays meaningful unchanged. What it doesn't give you is a letterform to
look at; that's the trade being made deliberately.

**Getting from a placeholder box to a finished plate**: `renderer.py`
gives every placed character its own `PlateGroupNode`
(`GroupKind.CHARACTER`, `name_key` set to the literal character) nested
under its field's node, and every node with shapes becomes its own
selectable group in the exported `.fabric-project.json`
(`PlateGroupNode.to_group_tuples()`, unchanged from before). In KFPS, that
means each character is a named, individually selectable box -- swap it
for real letterform art (existing or hand-made) and fine-tune position/
size there, one character at a time, rather than the whole field at once.

### Why none of the shipped templates bundles a real plate's actual font

UK's "Charles Wright" and Germany's "FE-Schrift" have unconfirmed
redistribution licenses (see each template's own `Provenance.source_notes`
for the specifics); US/California and Japan have no confirmed distinct font
name at all. Every proof-of-concept template reads metrics from a bundled,
freely-licensed font (`assets/fonts/LiberationSans-Regular.ttf`,
`NotoSansCJKjp-Regular.otf`) as an explicit, documented approximation of
size/spacing only -- never a claim about what the real letterforms look
like. Real letterform artwork for any of these, purpose-built or not, is
out of scope for this feature entirely now; it belongs in KFPS.

## Blank plate library

Background, border, and decorations never depend on user input -- only
fields do -- so rebuilding them from `Decoration` data on every single
generation is repeated work for a result that's identical every time.
`tools/gen_plate_blanks.py` renders each template's background/border/
decorations once (`renderer.py::render_plate_blank`) and saves the result
to `data/plate_blanks/<country>/<template_id>.json`
(`forza_writer/plates/blank_library.py`). `render_plate` loads that cached
blank when one exists and the instance doesn't override any decoration,
falling back to the on-the-fly path only when no cached blank exists yet,
or a Vanity-mode instance actually overrides a decoration's color,
position, or visibility (the cached blank only reflects a template's own
defaults, not any one instance's overrides).

Run `tools/gen_plate_blanks.py` after adding or editing a template. A
template with no cached blank still works -- `render_plate` falls back
automatically -- just without the caching benefit.

## New infrastructure (didn't exist before this feature)

- **`PlateGroupNode`** (`group.py`) -- a general parent/child shape-grouping
  tree. `forza_writer/fabric_project.py::to_fabric_project` already accepts
  `groups: list[(name, shape_indices)]`; `PlateGroupNode.to_group_tuples()`
  flattens a tree into that shape directly, so exporting to KFPS needs zero
  changes to `fabric_project.py`. For the app's own JSON export format
  (`export.to_json`), the Plates tab adds an **additive** `"plate_groups"`
  key -- additive because every existing consumer only reads `"shapes"`, so
  this can't regress any other generator's export.
- **Plate config persistence** (`tools/plate_config_store.py`) -- explicitly
  scoped to *just* what the Plates tab needs to resume a session (template,
  mode, field values/overrides), one JSON file per named config, mirroring
  `tools/layer_effect_presets_store.py`'s exact pattern. This is **not**
  undo/redo and **not** a general project-save format -- neither exists
  anywhere in Forza Writer, and building either was explicitly out of scope
  for this feature.
- **The blank plate library** (`blank_library.py`, above) -- a small,
  plate-specific pre-render cache, not a general asset-caching system.

## Authentic vs. Vanity mode

One `PlateTemplate` serves both modes -- there is no separate schema:

- **Authentic**: `forza_writer/plates/validation.py::is_valid_for_generation`
  checks every field's typed (or default) text against its
  `FieldValidation`. Any violation blocks generation; the GUI shows the
  specific field, the reason, and the expected format
  (`FieldValidation.format_hint_key`). Input is never silently corrected.
- **Vanity/Custom**: the same validation runs but is advisory only -- it
  never blocks. Every field/decoration also gains free override
  (`FieldOverride`/`DecorationOverride` on a `PlateInstance`) of text,
  color, position, alignment, tracking, or character source within the
  still-fixed physical template. The GUI shows a persistent
  "Customized / Fictional" badge in this mode so a modified plate is never
  mistaken for the real standard.

## Community template packages (schema only)

`forza_writer/plates/package_schema.py` defines `PlatePackageManifest`: a
declarative (JSON + referenced files, no executable code) description of a
distributable bundle of templates + fontpacks + assets + attribution + a
required `license_note`. **No import/validation pipeline exists yet** --
this was an explicit scope decision (architect the format, build the
importer later) confirmed with the feature's stakeholder. Building that
importer is real follow-up work, not a gap discovered late.

## Known limitations / follow-up work

- **No real letterform artwork exists for any shipped template's
  characters** -- by design now (see "Glyph sourcing" above), not a gap to
  fill in code. Producing that artwork (per character, per template, in
  KFPS) is a human/content task, not something `tools/gen_plate_templates*.py`
  should try to automate again.
- **`PLATE_SHAPE_WARN_THRESHOLD`** (`renderer.py`) is set from real
  measurement (all seventeen shipped templates range 9-62 shapes with the
  current placeholder-box pipeline), not a guess, but still worth
  revisiting once more/larger templates exist.
- **No front/rear plate-face distinction** in `Decoration` -- Japan's
  rear-only mounting-bolt seal is modeled as an always-visible placeholder
  decoration rather than a real front/rear-aware element.
- **Germany's district-code dataset** (400+ real codes) isn't built --
  the registration field's validation checks length/pattern only, not real
  district-code membership.
- **Favorites/recent plate standards** are not built (spec marks this
  optional if it complicates the architecture; with 5 proof-of-concept
  templates there's no real need yet).
- **`PlateField.editable_in_authentic_mode` is schema-only, not enforced.**
  Every field stays editable in the GUI and `validate_instance` doesn't
  consult it. Left unimplemented deliberately: it's genuinely unclear
  whether the flag should be a simple per-template-wide bool at all (e.g.
  Japan's region-kanji field is arguably something a real user *would* want
  to change even in Authentic mode) versus something more granular. Resolve
  the design question before wiring up enforcement, not the other way
  around.
- **The blank plate library must be rebuilt manually** (`tools/gen_plate_blanks.py`)
  after editing a template's background/border/decorations -- there's no
  automatic staleness check, so an edited template with a stale cached
  blank will keep rendering the *old* background/border/decorations until
  the library is rebuilt. `render_plate` has no way to detect this today.
