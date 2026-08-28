# Plate template schema and how to add a jurisdiction

See `docs/PLATE_GENERATOR_ARCHITECTURE.md` for the overall pipeline this
schema feeds. This document is the schema reference and the practical
"how do I add one" guide.

## Schema reference

Every dataclass lives in `forza_writer/plates/template.py` (or `instance.py`
for generated output) and round-trips through `to_dict()`/`from_dict()`.
Field names below match the dataclass fields exactly.

### `PlateTemplate`

| Field | Type | Notes |
|---|---|---|
| `template_id` | `str` | Stable id, e.g. `"gb-current-standard"`. Never rename once shipped. |
| `display_name_key` | `str` | An i18n key, not literal text. |
| `country` | `str` | ISO 3166-1 alpha-2. |
| `jurisdiction` | `str \| None` | State/province/prefecture code, or `None`. |
| `era` | `str` | Free-text filterable tag (`"current"`, `"1970s-1980s"`). |
| `plate_type` | `str` | `"passenger"`, `"commercial"`, `"motorcycle"`, `"custom"`, ... -- real-world specialty categories (military, university, ...) drive a browser drill-down level too, see "Real-world specialty categories" below. |
| `width_mm`, `height_mm` | `float` | See "Unit convention" below. |
| `accuracy_status` | `AccuracyStatus` | `VERIFIED \| REFERENCE_BASED \| APPROXIMATE \| COMMUNITY_RECONSTRUCTION \| FICTIONAL`. |
| `provenance` | `Provenance` | Required `source_notes`; be specific about what's *not* verified. |
| `background` | `Decoration` | Usually `editable=False`. |
| `border` | `Decoration \| None` | See "Border/background layering" below. |
| `fields` | `tuple[PlateField, ...]` | Ordered, each independently addressable. |
| `decorations` | `tuple[Decoration, ...]` | Optional, defaults to `()`. |
| `tags` | `tuple[str, ...]` | Browser filter facets, e.g. `("vanity-available",)`. |

### `PlateField`

| Field | Type | Notes |
|---|---|---|
| `field_id` | `str` | Unique within the template. |
| `label_key` | `str` | i18n key. |
| `role` | `FieldRole` | `REGISTRATION \| REGION_CODE \| CLASSIFICATION \| JURISDICTION_TEXT \| DECORATIVE_TEXT \| FREE_TEXT` -- UI grouping, not enforced behavior. |
| `x_mm`, `y_mm`, `width_mm`, `height_mm` | `float` | Top-left origin, template-local mm space. |
| `alignment` | `str` | One of `forza_writer.text_compose.ALIGNMENTS` (`left/center/right/justify`). |
| `char_source` | `CharSource` | See architecture doc's "Glyph sourcing" section. |
| `char_scale` | `float` | Rendered text height = `height_mm * char_scale`. Tune against actual output -- see below. |
| `tracking` | `float` | Letter-spacing, mm. |
| `line_spacing` | `float` | Only matters for multi-line text (embedded `"\n"`). |
| `default_text` | `str` | Shown before the user types anything; must be a *valid* example under the field's own `validation`. |
| `color` | `RGBA \| None` | The standard's own fixed color (e.g. Japan's green text). `None` = pipeline default. |
| `validation` | `FieldValidation \| None` | `None` for purely decorative/free fields. |
| `editable_in_authentic_mode` | `bool` | Default `False`. |

### `CharSource`

| Field | Notes |
|---|---|
| `font_file` | Required, non-empty. A filename under `assets/fonts/`, e.g. `"LiberationSans-Regular.ttf"` -- read once for its metrics via fontTools, never for letterform geometry. |
| `fallback` | Optional `CharSource \| None` -- if the primary font is missing metrics for a character the field's text needs, the *whole* text is re-laid-out against this font instead (a whole-swap, not per-character mixing). |

**A `CharSource` never produces artwork.** Every character renders as a
plain placeholder box, sized/spaced from the named font's real metrics --
see the architecture doc's "Glyph sourcing" section for why, and for how
that box becomes a swappable KFPS group.

### `FieldValidation`

| Field | Notes |
|---|---|
| `format_hint_key` | Required i18n key, e.g. resolving to `"Format: AA99 AAA"`. |
| `min_length`, `max_length` | Optional. |
| `allowed_pattern` | Optional regex, checked with `re.fullmatch`. |
| `excluded_chars` | Tuple of individually-banned characters. |
| `custom_rule_id` | Optional name from `validation_rules.py::RULE_REGISTRY` -- see below. |

### `Decoration`

| Field | Notes |
|---|---|
| `decoration_id` | Unique (across both fields and decorations on one template). |
| `kind` | `SOLID_FILL \| BORDER \| SEAL \| LOGO \| SEPARATOR \| STICKER \| BOLT_HOLE \| JURISDICTION_MARK \| CUSTOM_SHAPE`. |
| `x_mm`, `y_mm` | Position. |
| `width_mm`, `height_mm` | `None` on either axis = full-bleed on that axis (ignores position on that axis). |
| `color` | Plain solid fill if no `asset_ref`. |
| `asset_ref` | Optional id into `data/plate_assets/`. |
| `editable` | `False` reserves it against Vanity-mode deletion. |

## Unit convention

1mm of template space = 1 shape unit (`forza_writer/plates/layout_engine.py::MM_TO_UNIT`).
This is deliberate: every generator's output is freely rescaled by the user
in Forza's own decal editor, so only *relative* proportions matter, not any
absolute real-world size. A 520mm-wide UK plate template literally spans
`x` in `[-260, 260]` -- trivially checkable.

## Border/background layering

`Decoration` has no "stroke width" concept. A visible border is produced by
drawing the border decoration's own box first (bottom of the paint order),
then the background's own box on top, sized smaller by however much frame
you want visible:

```python
background=Decoration(decoration_id="bg", kind=DecorationKind.SOLID_FILL,
                       x_mm=6.0, y_mm=6.0, width_mm=288.0, height_mm=138.0,
                       color=(245, 245, 240, 255), editable=False),
border=Decoration(decoration_id="border", kind=DecorationKind.BORDER,
                   x_mm=0.0, y_mm=0.0, color=(20, 20, 20, 255)),  # full-bleed
```

`renderer.py` always draws `border` before `background` -- see its own
module docstring for why reversing this order would hide the border
entirely.

## Tuning `char_scale` against real output (important)

**Do not guess `char_scale`.** The renderer only sizes text to its field's
*height*; it never checks width, and text is never auto-shrunk to fit
(spec explicitly forbids silently modifying content). An oversized
`char_scale` produces a real, functional plate -- a runtime warning, not a
crash -- but the text will visibly run past its field's box.

The practical workflow (used to tune all five proof-of-concept templates):

```python
from forza_writer.plates.loader import list_templates, reload_templates
from forza_writer.plates.instance import PlateInstance
from forza_writer.plates.renderer import render_plate

reload_templates()
template = next(t for t in list_templates() if t.template_id == "your-template-id")
instance = PlateInstance(template_id=template.template_id, mode="authentic", field_values={})
shapes, root, warnings = render_plate(template, instance)
print(warnings)  # any overflow warning names the field and the actual-vs-available width
```

Adjust `char_scale` down by roughly `available_width / actual_width` and
re-run until `warnings` is empty. Render to a PNG for a visual check:

```python
import file_preview
image = file_preview.render_composed_preview(shapes, size=(900, 450), bg="#555555", fg="#ffffff")
image.save("preview.png")
```

## How to add a new jurisdiction

1. **Source the facts.** Prefer a government/legal primary source for
   dimensions, registration format, colors, and any mandatory decorations.
2. **Choose an honest `accuracy_status`:**
   - Primary source confirmed -> `VERIFIED`.
   - Secondary/news sources only, or a detail you couldn't independently
     confirm -> `REFERENCE_BASED`, with the specific gap named in
     `Provenance.source_notes` (see the shipped templates for examples --
     e.g. `us-ca-passenger-current`'s note about the reported 2026 format
     change lacking a primary-source citation).
   - Visually similar but not researched -> `APPROXIMATE`.
   - Built from personal reference/memory, no web access -> `COMMUNITY_RECONSTRUCTION`,
     with `Provenance.reconstruction_author` set.
   - Not based on anything real -> `FICTIONAL`.
3. **Never bundle a font with an unconfirmed license.** Default to the
   existing bundled/freely-licensed placeholder font's metrics (state that
   plainly in `source_notes`), or reference a different bundled font whose
   proportions are a closer match if you're willing to add one (see
   "Improving size/spacing accuracy" below) -- either way, `CharSource`
   never renders the font's actual letterforms, only its metrics, so the
   licensing bar is about redistributing the file, not about reproducing
   its look.
4. **Build the template** as a Python function returning a `PlateTemplate`
   (see `tools/gen_plate_templates.py` for five worked examples spanning a
   single-field plate, a multi-field stress test, and border/background/
   decoration layering), then write it to
   `data/plate_templates/<country>/<id>.json` via `template.to_dict()` --
   see `data/plate_templates/US/README.md` for the per-state naming
   convention if you're adding a US state specifically.
5. **Tune `char_scale`** per the section above until every field renders
   with zero overflow warnings.
6. **Build the blank plate library entry**: `python tools/gen_plate_blanks.py`
   (rebuilds every template's cached background/border/decorations,
   including the new one).
7. **Add a test** confirming the template loads, validates its own
   `default_text`, and renders without warnings (see
   `tests/forza_writer/test_plate_poc_templates.py` for the pattern).

## Real-world specialty categories

Most US state DMV programs run specialty plates well beyond the standard
passenger issue -- military/veteran, law enforcement, university, civic
organization, Greek, high school, and so on (Louisiana's own published
categories, for one:
https://expresslane.dps.louisiana.gov/specialplatespublic/specialplatesviewer.aspx).
The Plates tab's browser is wired to group real-world templates by this
kind of category as a third drill-down level (country -> jurisdiction ->
category), on top of the existing two -- but as of this writing every
shipped real-world template is `plate_type="passenger"`, so that level
auto-skips and stays invisible, exactly like jurisdiction already does for
a single-jurisdiction country. This is deliberate: skeleton, not content --
see [[project_forza_writer_plate_generator]] memory / the commit that added
it for why building out the actual specialty templates was explicitly
scoped out.

`tools/gen_modelbin_gui/tabs/plates.py`'s `PLATE_CATEGORIES` dict is the
display-name registry the browser and search use to resolve a template's
`plate_type` into a readable label:

```python
PLATE_CATEGORIES = {
    "passenger": "Standard / Passenger",
    "military": "Military & Veteran",
    "law_enforcement": "Law Enforcement",
    "university": "University / College",
    "organization": "Organization / Service",
    "special_interest": "Special Interest",
    "high_school": "High School",
    "greek": "Sorority / Fraternity",
}
```

`plate_type` stays a free string (not a validated enum) -- a template
using a value outside this registry still works everywhere (browsing,
search, the Details panel), just falls back to a title-cased rendering of
the raw value instead of a hand-picked label. To add a real specialty
template: pick (or add) the `plate_type` value that best fits, build the
template the normal way (see "How to add a new jurisdiction" above), and
the category level starts showing up on its own the moment a jurisdiction
has more than one distinct `plate_type` -- no further code change needed.

## Fictional (game) templates

`tools/gen_plate_templates_fictional.py` builds templates modeled on
license plates from video games (GTA V, Need for Speed, Saints Row, Halo,
Cyberpunk 2077, Mirror's Edge, Dying Light, Phasmophobia) -- a second
worked-example set alongside the five real-world proof-of-concept
templates, showing what step 1 above ("source the facts") looks like
when there's no government statute to cite:

- A developer's own public statement about the design (e.g. Bungie's Joseph
  Staten confirming Halo 3: ODST's license-plate Easter egg) is as close to
  a primary source as fiction gets -- treat it that way.
- A screenshot someone actually took of the game (not an extracted/scraped
  game asset -- see this module's own docstring for why that distinction
  matters) is a legitimate direct source for layout, text, and color, the
  same way a photo of a real plate would be. Say so in `source_notes`, and
  say plainly when a color or a few characters of small print are a
  best-effort reading of a low-resolution image rather than a confident
  transcription.
- A wiki gallery of *player-made* vanity plates (e.g. the Need for Speed
  templates here) can still document a genuine, reused design template
  (banner placement, sticker, franchise in-joke text) even though no single
  example plate in it is "the" canonical one.
- It's fine -- and should be named plainly -- when nothing documents a
  design element at all (Halo: Reach's barcode plate's actual colors, Saints
  Row's Steelport background). `AccuracyStatus.FICTIONAL` doesn't mean
  "no sourcing effort was made"; it means "not a real government standard,"
  full stop -- the same honesty about gaps applies as everywhere else.

Every field in this set still reads metrics from the shared placeholder
Latin font (`LiberationSans-Regular.ttf`), same as the real-world set -- no
game's actual plate font, texture, or letterform is bundled, reproduced,
or rendered by any template here.

### Candidate franchises, not yet built

Games identified as worth adding a template for eventually, tracked here
so the franchise/`country` code and the reasoning for it are settled
before anyone actually builds one -- not a commitment to build them, and
not a template in their own right. (Dying Light was tracked here briefly
before being built -- see `dl-harran-passenger-fictional` above; nothing
listed as of this writing.)

## Adding a historical variant

The same process as a new jurisdiction -- just give it a distinct
`template_id` (e.g. `gb-pre-2001`) and set `era` accordingly. A historical
variant is not a special case in the schema; it's simply another template.

## Improving size/spacing accuracy with a different reference font

Since a `CharSource` only ever contributes metrics (never letterform
artwork -- see the architecture doc's "Glyph sourcing" section), the bar
for "which font should this template reference" is much lower than
sourcing a real, legally-bundleable plate font: you're picking a font
whose *character proportions* (a condensed vs. wide face, monospace vs.
proportional digits) are a closer match to the real plate's typesetting,
not one whose letterforms you intend to display. A real plate font is
still the ideal source if you have one, but a well-chosen substitute with
similar proportions is a legitimate, much lower-effort improvement over
the shared placeholder.

1. Add the font file under `assets/fonts/` (only a font you actually hold
   the rights to bundle/redistribute -- it's still a real file shipped in
   the repo, even though only its metrics are ever read).
2. Reference it from a `PlateField`:
   ```python
   char_source=CharSource(font_file="my-plate-metrics-font.ttf",
                          fallback=CharSource(font_file="LiberationSans-Regular.ttf"))
   ```
   The `fallback` covers any character the new font's cmap doesn't include.
3. Update the template's `Provenance` to say what the new font is standing
   in for and why it's a closer match, and drop any "approximated with the
   shared placeholder" caveat that no longer applies.
4. Rebuild the blank plate library (`python tools/gen_plate_blanks.py`) if
   this template's background/border/decorations changed too.

Producing actual letterform artwork for a plate's characters is out of
scope for this feature -- that happens per-generated-plate, in KFPS,
against the placeholder boxes this schema's `CharSource` positions.

## Community template packages

`forza_writer/plates/package_schema.py::PlatePackageManifest` defines the
distribution format (template + glyph sets + assets + attribution + a
required `license_note`), but **no import/validation pipeline exists yet**
-- this is a deliberate v1 scope decision, not a gap. Building the importer
is real follow-up work: validate every referenced template/glyph-set/asset
id resolves, `format_version` matches, and fail gracefully (not silently)
on anything malformed.

## Tutorial: a minimal two-field template

The simplest possible template, deliberately smaller than any
proof-of-concept template, walked through end to end:

```python
from forza_writer.plates.template import (
    AccuracyStatus, CharSource, Decoration, DecorationKind,
    FieldRole, PlateField, PlateTemplate, Provenance,
)

# Any font under assets/fonts/ works -- CharSource only ever reads its
# metrics, never its letterforms.
LATIN = CharSource(font_file="LiberationSans-Regular.ttf")

tutorial = PlateTemplate(
    template_id="tutorial-minimal",
    display_name_key="plates.template.tutorial_minimal",
    country="XX", jurisdiction=None, era="current", plate_type="custom",
    width_mm=200.0, height_mm=100.0,
    accuracy_status=AccuracyStatus.FICTIONAL,
    provenance=Provenance(source_notes="Tutorial example, not a real jurisdiction."),
    background=Decoration(decoration_id="bg", kind=DecorationKind.SOLID_FILL,
                           x_mm=0.0, y_mm=0.0, color=(255, 255, 255, 255), editable=False),
    border=None,
    fields=(
        PlateField(
            field_id="text", label_key="plates.field.registration", role=FieldRole.FREE_TEXT,
            x_mm=10.0, y_mm=30.0, width_mm=180.0, height_mm=40.0, alignment="center",
            char_source=LATIN, char_scale=0.8, default_text="HELLO",
        ),
    ),
)
```

One field, one background, no border, no decorations, no validation. Every
other template in this system is this same shape with more fields and
rules layered on top. Once written to `data/plate_templates/XX/tutorial-minimal.json`,
running `python tools/gen_plate_blanks.py` would cache its background so
`render_plate` doesn't rebuild it from `Decoration` data on every call --
see the architecture doc's "Blank plate library" section.
