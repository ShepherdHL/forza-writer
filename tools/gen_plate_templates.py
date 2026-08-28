"""
Builds the five proof-of-concept plate templates (spec section 16) into
data/plate_templates/<country>/*.json: a simple US-style plate, a current
UK-style plate, a Japanese plate with multiple structured fields, a
German-style plate, and a blank custom vanity plate.

These exist to stress-test the architecture (per-field character-source
mixing, positional/custom validation rules, border/background layering,
decorations), not as a final, permanent template library -- see each
template's own Provenance.source_notes for exactly what is/isn't verified,
and docs/PLATE_TEMPLATE_SCHEMA.md for the sourcing process to extend this
set with a real jurisdiction.

**Typography note**: none of these bundle a real plate's actual font, and
none ever will -- a `PlateField` only ever renders a plain placeholder box
per character now, sized/spaced from a real font's metrics (never its
letterform geometry). Every field here reads metrics from a bundled,
freely-licensed font (assets/fonts/LiberationSans-Regular.ttf,
NotoSansCJKjp-Regular.otf) via `forza_writer.plates.template.CharSource`.
Real letterform artwork -- whether that ends up being UK's "Charles
Wright", Germany's "FE-Schrift", or anything else -- is the user's to
supply and fine-tune in KFPS; Forza Writer's job is correct size/spacing,
not generating the artwork itself. See
docs/PLATE_GENERATOR_ARCHITECTURE.md's changelog note.

Usage:
    python tools/gen_plate_templates.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from forza_writer.plates.template import (  # noqa: E402
    AccuracyStatus,
    CharSource,
    Decoration,
    DecorationKind,
    FieldRole,
    FieldValidation,
    PlateField,
    PlateTemplate,
    Provenance,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "data" / "plate_templates"

_LATIN = CharSource(font_file="LiberationSans-Regular.ttf")
_CJK = CharSource(font_file="NotoSansCJKjp-Regular.otf")

WHITE = (255, 255, 255, 255)
BLACK = (20, 20, 20, 255)


def us_california() -> PlateTemplate:
    return PlateTemplate(
        template_id="us-ca-passenger-current",
        display_name_key="plates.template.us_ca_passenger_current",
        country="US", jurisdiction="CA", era="current", plate_type="passenger",
        width_mm=304.8, height_mm=152.4,
        accuracy_status=AccuracyStatus.REFERENCE_BASED,
        provenance=Provenance(
            source_notes=(
                "12in x 6in and the legacy '1ABC234' format are verified via California Vehicle Code "
                "Section 5201. No official font name is confirmed for the plate face -- typography here "
                "is approximated with a bundled sans-serif, not an authentic reproduction. A reversed "
                "'123ABC1'-style format is reported effective ~March 2026 in news coverage only, not "
                "confirmed against a DMV.ca.gov primary source; this template models the long-standing "
                "legacy format and should be revisited once a primary source for the new format is found."
            ),
            reference_urls=("https://law.justia.com/codes/california/code-veh/division-3/chapter-1/article-9/section-5201/",),
        ),
        background=Decoration(decoration_id="bg", kind=DecorationKind.SOLID_FILL, x_mm=3.0, y_mm=3.0,
                               width_mm=298.8, height_mm=146.4, color=WHITE, editable=False),
        border=Decoration(decoration_id="border", kind=DecorationKind.BORDER, x_mm=0.0, y_mm=0.0,
                           color=(0, 40, 130, 255)),
        fields=(
            PlateField(
                field_id="jurisdiction_header", label_key="plates.field.jurisdiction_header",
                role=FieldRole.JURISDICTION_TEXT,
                x_mm=20.0, y_mm=10.0, width_mm=264.8, height_mm=28.0, alignment="center",
                char_source=_LATIN, char_scale=0.55, tracking=1.0,
                default_text="California", color=(190, 20, 20, 255),
                editable_in_authentic_mode=False,
            ),
            PlateField(
                field_id="registration", label_key="plates.field.registration", role=FieldRole.REGISTRATION,
                x_mm=20.0, y_mm=48.0, width_mm=264.8, height_mm=70.0, alignment="center",
                char_source=_LATIN, char_scale=0.57, tracking=4.0,
                default_text="1ABC234", color=(0, 40, 130, 255),
                validation=FieldValidation(
                    format_hint_key="plates.validation.us_ca.format_hint",
                    min_length=7, max_length=7,
                    allowed_pattern=r"[0-9][A-Z]{3}[0-9]{3}",
                    custom_rule_id="us_ca_no_ambiguous_letters_in_outer_positions",
                ),
            ),
        ),
        tags=("vanity-available",),
    )


def gb_current() -> PlateTemplate:
    return PlateTemplate(
        template_id="gb-current-standard",
        display_name_key="plates.template.gb_current_standard",
        country="GB", jurisdiction=None, era="current", plate_type="passenger",
        width_mm=520.0, height_mm=111.0,
        accuracy_status=AccuracyStatus.REFERENCE_BASED,
        provenance=Provenance(
            source_notes=(
                "Dimensions and character/spacing figures (79mm height, 50mm width, 14mm stroke, 11mm "
                "margins/inter-character space, 33mm inter-group space) are verified against The Road "
                "Vehicles (Display of Registration Marks) Regulations 2001 (SI 2001/561), BS AU 145e. "
                "Registration lettering is approximated with a bundled sans-serif, NOT the licensed "
                "'Charles Wright' font (K-Type foundry) -- that font's bold weight is free for personal "
                "use only and is not bundled or reproduced here. The real font also draws O/0 and I/1 "
                "identically by design and differentiates 8/B and D/0 via slab-serif details, none of "
                "which this placeholder font does; a purpose-built plate font, generated into a fontpack "
                "the same way any other font is (tools/gen_fontpack.py), is the recommended fix, not "
                "yet built."
            ),
            reference_urls=("https://www.legislation.gov.uk/uksi/2001/561",),
        ),
        background=Decoration(decoration_id="bg", kind=DecorationKind.SOLID_FILL, x_mm=0.0, y_mm=0.0,
                               color=WHITE, editable=False),
        border=None,
        fields=(
            PlateField(
                field_id="registration", label_key="plates.field.registration", role=FieldRole.REGISTRATION,
                x_mm=20.0, y_mm=16.0, width_mm=480.0, height_mm=79.0, alignment="center",
                char_source=_LATIN, char_scale=0.81, tracking=11.0,
                default_text="AB12 CDE", color=BLACK,
                validation=FieldValidation(
                    format_hint_key="plates.validation.gb.format_hint",
                    min_length=8, max_length=8,
                    allowed_pattern=r"[A-HJ-PR-Z]{2}[0-9]{2} [A-HJ-PR-Z]{3}",
                    excluded_chars=("I", "Q"),
                ),
            ),
        ),
        decorations=(
            Decoration(decoration_id="id_band", kind=DecorationKind.JURISDICTION_MARK,
                       x_mm=0.0, y_mm=0.0, width_mm=18.0, height_mm=111.0, color=(0, 40, 130, 255)),
        ),
        tags=("vanity-available",),
    )


def jp_private_passenger() -> PlateTemplate:
    return PlateTemplate(
        template_id="jp-private-passenger-current",
        display_name_key="plates.template.jp_private_passenger_current",
        country="JP", jurisdiction=None, era="current", plate_type="passenger",
        width_mm=330.0, height_mm=165.0,
        accuracy_status=AccuracyStatus.REFERENCE_BASED,
        provenance=Provenance(
            source_notes=(
                "330mm x 165mm dimensions and the white-background/green-text private-passenger color "
                "scheme are well-documented and consistently reported. The two-line, four-field layout "
                "(region name + classification number / hiragana + serial) and the centered-dot leading-"
                "zero serial convention are consistently reported across enthusiast sources but not "
                "traced to a primary MLIT legal text in this pass -- flagged approximate. No confirmed "
                "distinct font name for the plate face; typography approximated with bundled fonts "
                "(Noto Sans CJK JP for kanji/hiragana, a Latin sans for digits). The rear-only stamped "
                "aluminum seal (fuin) covering the top-left mounting bolt is not modeled as a distinct "
                "decoration in this version -- the schema has no front/rear-face distinction yet; a "
                "placeholder seal decoration is included but shown regardless of plate face."
            ),
        ),
        background=Decoration(decoration_id="bg", kind=DecorationKind.SOLID_FILL, x_mm=0.0, y_mm=0.0,
                               color=WHITE, editable=False),
        border=Decoration(decoration_id="border", kind=DecorationKind.BORDER, x_mm=0.0, y_mm=0.0,
                           color=(0, 110, 60, 255)),
        fields=(
            PlateField(
                field_id="region_kanji", label_key="plates.field.region_kanji", role=FieldRole.REGION_CODE,
                x_mm=15.0, y_mm=8.0, width_mm=170.0, height_mm=45.0, alignment="center",
                char_source=_CJK, char_scale=1.0, tracking=2.0,
                default_text="品川", color=(0, 110, 60, 255),
            ),
            PlateField(
                field_id="classification_number", label_key="plates.field.classification_number",
                role=FieldRole.CLASSIFICATION,
                x_mm=190.0, y_mm=8.0, width_mm=125.0, height_mm=45.0, alignment="center",
                char_source=_LATIN, char_scale=1.0, tracking=2.0,
                default_text="530", color=(0, 110, 60, 255),
                validation=FieldValidation(
                    format_hint_key="plates.validation.jp.classification_hint",
                    min_length=3, max_length=3, allowed_pattern=r"[0-9]{3}",
                ),
            ),
            PlateField(
                field_id="hiragana", label_key="plates.field.hiragana", role=FieldRole.FREE_TEXT,
                x_mm=15.0, y_mm=60.0, width_mm=60.0, height_mm=90.0, alignment="center",
                char_source=_CJK, char_scale=0.48, default_text="あ", color=(0, 110, 60, 255),
                validation=FieldValidation(
                    format_hint_key="plates.validation.jp.hiragana_hint",
                    min_length=1, max_length=1,
                    excluded_chars=("お", "し", "へ", "ん", "ゐ", "ゑ"),
                ),
            ),
            PlateField(
                field_id="serial", label_key="plates.field.serial", role=FieldRole.REGISTRATION,
                x_mm=90.0, y_mm=60.0, width_mm=225.0, height_mm=90.0, alignment="center",
                char_source=_LATIN, char_scale=0.62, tracking=3.0,
                default_text="12-34", color=(0, 110, 60, 255),
                validation=FieldValidation(
                    format_hint_key="plates.validation.jp.serial_hint",
                    min_length=5, max_length=5,
                    allowed_pattern=r"([0-9]|・)[0-9]-[0-9]{2}",
                    custom_rule_id="jp_serial_leading_zero_as_dot",
                ),
            ),
        ),
        decorations=(
            Decoration(decoration_id="seal", kind=DecorationKind.SEAL,
                       x_mm=8.0, y_mm=8.0, width_mm=14.0, height_mm=14.0, color=(180, 30, 30, 255)),
        ),
        tags=("vanity-available",),
    )


def de_current() -> PlateTemplate:
    return PlateTemplate(
        template_id="de-current-eu-band",
        display_name_key="plates.template.de_current_eu_band",
        country="DE", jurisdiction=None, era="current", plate_type="passenger",
        width_mm=520.0, height_mm=110.0,
        accuracy_status=AccuracyStatus.REFERENCE_BASED,
        provenance=Provenance(
            source_notes=(
                "520mm x 110mm single-line dimensions and the mandatory blue EU band (gold-star circle "
                "over a white 'D') are consistent with DIN 74069 as reported in secondary sources -- not "
                "independently cross-checked against the paywalled DIN text itself. Registration "
                "lettering is approximated with a bundled sans-serif, NOT FE-Schrift (Fälschungserschwerende "
                "Schrift) -- no confirmed open license exists for circulating digitizations of that font, "
                "so none is bundled; a purpose-built plate font, generated into a fontpack the same way "
                "any other font is, is the recommended long-term fix. The "
                "district-code/letter/digit format and the two inspection-sticker decorations are modeled "
                "structurally; the ~400-entry district-code lookup table itself is not yet built (tracked "
                "as a follow-up in docs/PLATE_TEMPLATE_SCHEMA.md), so the registration field's validation "
                "checks length/pattern only, not real district-code membership."
            ),
        ),
        background=Decoration(decoration_id="bg", kind=DecorationKind.SOLID_FILL, x_mm=45.0, y_mm=0.0,
                               width_mm=475.0, height_mm=110.0, color=WHITE, editable=False),
        border=Decoration(decoration_id="border", kind=DecorationKind.BORDER, x_mm=45.0, y_mm=0.0,
                           width_mm=475.0, height_mm=110.0, color=BLACK),
        fields=(
            PlateField(
                field_id="registration", label_key="plates.field.registration", role=FieldRole.REGISTRATION,
                x_mm=60.0, y_mm=16.0, width_mm=370.0, height_mm=75.0, alignment="center",
                char_source=_LATIN, char_scale=0.61, tracking=8.0,
                default_text="B MW 1234", color=BLACK,
                validation=FieldValidation(
                    format_hint_key="plates.validation.de.format_hint",
                    min_length=5, max_length=11,
                    allowed_pattern=r"[A-Z]{1,3} [A-Z]{1,2} [0-9]{1,4}",
                ),
            ),
        ),
        decorations=(
            Decoration(decoration_id="eu_band", kind=DecorationKind.JURISDICTION_MARK,
                       x_mm=0.0, y_mm=0.0, width_mm=45.0, height_mm=110.0, color=(0, 51, 153, 255)),
            Decoration(decoration_id="hu_sticker", kind=DecorationKind.STICKER,
                       x_mm=460.0, y_mm=5.0, width_mm=18.0, height_mm=18.0, color=(230, 160, 30, 255)),
            Decoration(decoration_id="zulassung_sticker", kind=DecorationKind.STICKER,
                       x_mm=460.0, y_mm=87.0, width_mm=18.0, height_mm=18.0, color=(200, 200, 200, 255)),
        ),
        tags=("vanity-available",),
    )


def custom_blank() -> PlateTemplate:
    return PlateTemplate(
        template_id="custom-blank",
        display_name_key="plates.template.custom_blank",
        country="XX", jurisdiction=None, era="current", plate_type="custom",
        width_mm=300.0, height_mm=150.0,
        accuracy_status=AccuracyStatus.FICTIONAL,
        provenance=Provenance(source_notes="Not based on any real jurisdiction. Dimensions are an "
                                            "arbitrary default, freely changeable."),
        background=Decoration(decoration_id="bg", kind=DecorationKind.SOLID_FILL, x_mm=6.0, y_mm=6.0,
                               width_mm=288.0, height_mm=138.0, color=(245, 245, 240, 255), editable=False),
        border=Decoration(decoration_id="border", kind=DecorationKind.BORDER, x_mm=0.0, y_mm=0.0,
                           color=BLACK),
        fields=(
            PlateField(
                field_id="registration", label_key="plates.field.registration", role=FieldRole.FREE_TEXT,
                x_mm=15.0, y_mm=55.0, width_mm=270.0, height_mm=40.0, alignment="center",
                char_source=_LATIN, char_scale=0.79, tracking=2.0,
                default_text="YOUR TEXT", color=BLACK,
                editable_in_authentic_mode=True,
            ),
        ),
    )


TEMPLATES = (us_california, gb_current, jp_private_passenger, de_current, custom_blank)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for builder in TEMPLATES:
        template = builder()
        # One subdirectory per country (data/plate_templates/<country>/<id>.json)
        # -- see forza_writer/plates/loader.py's module docstring for why.
        country_dir = OUT_DIR / template.country
        country_dir.mkdir(parents=True, exist_ok=True)
        path = country_dir / f"{template.template_id}.json"
        path.write_text(json.dumps(template.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
