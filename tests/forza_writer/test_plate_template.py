"""Tests for the plate template/instance data model
(forza_writer/plates/template.py, instance.py).

Phase 1 scope only: dataclass round-trips through to_dict()/from_dict(),
including Unicode field text, and rejection of malformed input. Loading from
actual files, cross-field schema validation, and rendering are later phases
(loader.py, renderer.py).
"""

import dataclasses

import pytest

from forza_writer.plates.instance import (
    DecorationOverride,
    FieldOverride,
    PlateInstance,
)
from forza_writer.plates.template import (
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


def _fontpack_source(font_file="LiberationSans-Regular.ttf"):
    return CharSource(font_file=font_file)


def _registration_field(field_id="registration", text="AB12 CDE"):
    return PlateField(
        field_id=field_id,
        label_key="plates.field.registration",
        role=FieldRole.REGISTRATION,
        x_mm=20.0, y_mm=10.0, width_mm=480.0, height_mm=79.0,
        alignment="center",
        char_source=_fontpack_source(),
        default_text=text,
        validation=FieldValidation(
            format_hint_key="plates.validation.gb.format_hint",
            min_length=7, max_length=8,
            allowed_pattern=r"^[A-Z]{2}[0-9]{2}[A-Z]{3}$",
            excluded_chars=("I", "Q"),
        ),
    )


def _minimal_template():
    return PlateTemplate(
        template_id="gb-current-standard",
        display_name_key="plates.template.gb_current",
        country="GB",
        jurisdiction=None,
        era="current",
        plate_type="passenger",
        width_mm=520.0,
        height_mm=111.0,
        accuracy_status=AccuracyStatus.REFERENCE_BASED,
        provenance=Provenance(
            source_notes="Sizing verified against SI 2001/561.",
            reference_urls=("https://www.legislation.gov.uk/uksi/2001/561",),
        ),
        background=Decoration(
            decoration_id="bg", kind=DecorationKind.SOLID_FILL,
            x_mm=0.0, y_mm=0.0, color=(255, 255, 255, 255), editable=False,
        ),
        border=None,
        fields=(_registration_field(),),
    )


# ---------------------------------------------------------------------------
# CharSource
# ---------------------------------------------------------------------------

def test_char_source_round_trip_with_fallback():
    source = CharSource(
        font_file="LiberationSans-Regular.ttf",
        fallback=_fontpack_source("NotoSansCJKjp-Regular.otf"),
    )
    restored = CharSource.from_dict(source.to_dict())
    assert restored == source
    assert restored.fallback.font_file == "NotoSansCJKjp-Regular.otf"


def test_char_source_requires_a_non_empty_font_file():
    with pytest.raises(ValueError, match="font_file"):
        CharSource(font_file="")


# ---------------------------------------------------------------------------
# PlateField / FieldValidation
# ---------------------------------------------------------------------------

def test_plate_field_round_trip():
    field = _registration_field()
    restored = PlateField.from_dict(field.to_dict())
    assert restored == field


def test_plate_field_color_round_trips():
    field = dataclasses.replace(_registration_field(), color=(0, 128, 0, 255))
    restored = PlateField.from_dict(field.to_dict())
    assert restored.color == (0, 128, 0, 255)


def test_plate_field_no_color_round_trips_as_none():
    field = _registration_field()
    assert field.color is None
    restored = PlateField.from_dict(field.to_dict())
    assert restored.color is None


def test_plate_field_unicode_default_text_survives_round_trip():
    field = PlateField(
        field_id="hiragana",
        label_key="plates.field.hiragana",
        role=FieldRole.DECORATIVE_TEXT,
        x_mm=0.0, y_mm=0.0, width_mm=30.0, height_mm=30.0,
        alignment="center",
        char_source=CharSource(font_file="NotoSansCJKjp-Regular.otf"),
        default_text="あ",  # hiragana "a"
    )
    restored = PlateField.from_dict(field.to_dict())
    assert restored.default_text == "あ"


# ---------------------------------------------------------------------------
# Decoration / Provenance
# ---------------------------------------------------------------------------

def test_decoration_round_trip_full_and_minimal():
    full = Decoration(
        decoration_id="eu-band", kind=DecorationKind.JURISDICTION_MARK,
        x_mm=0.0, y_mm=0.0, width_mm=40.0, height_mm=111.0,
        color=(0, 51, 153, 255), asset_ref="eu-band-de",
    )
    assert Decoration.from_dict(full.to_dict()) == full

    minimal = Decoration(decoration_id="bg", kind=DecorationKind.SOLID_FILL, x_mm=0.0, y_mm=0.0)
    restored = Decoration.from_dict(minimal.to_dict())
    assert restored.width_mm is None and restored.color is None


def test_provenance_round_trip():
    prov = Provenance(
        source_notes="Font approximated, not bundled.",
        contributors=("CRUSE2382",),
        reconstruction_author="CRUSE2382",
        year_documented=2020,
    )
    assert Provenance.from_dict(prov.to_dict()) == prov


# ---------------------------------------------------------------------------
# PlateTemplate
# ---------------------------------------------------------------------------

def test_plate_template_round_trip():
    template = _minimal_template()
    restored = PlateTemplate.from_dict(template.to_dict())
    assert restored == template
    assert restored.field_by_id("registration") is not None
    assert restored.field_by_id("nonexistent") is None


def test_plate_template_with_border_and_decorations_round_trip():
    template = PlateTemplate(
        template_id="de-current-eu-band",
        display_name_key="plates.template.de_current",
        country="DE",
        jurisdiction=None,
        era="current",
        plate_type="passenger",
        width_mm=520.0,
        height_mm=110.0,
        accuracy_status=AccuracyStatus.REFERENCE_BASED,
        provenance=Provenance(source_notes="DIN 74069, not independently cross-checked."),
        background=Decoration(decoration_id="bg", kind=DecorationKind.SOLID_FILL, x_mm=0.0, y_mm=0.0,
                               color=(255, 255, 255, 255), editable=False),
        border=Decoration(decoration_id="border", kind=DecorationKind.BORDER, x_mm=0.0, y_mm=0.0,
                           color=(0, 0, 0, 255)),
        fields=(_registration_field(field_id="registration", text="B MW 1234"),),
        decorations=(
            Decoration(decoration_id="eu-band", kind=DecorationKind.JURISDICTION_MARK,
                       x_mm=0.0, y_mm=0.0, width_mm=40.0, height_mm=110.0, asset_ref="eu-band-de"),
            Decoration(decoration_id="hu-sticker", kind=DecorationKind.STICKER,
                       x_mm=200.0, y_mm=5.0, width_mm=20.0, height_mm=20.0, asset_ref="hu-sticker"),
        ),
        tags=("vanity-available",),
    )
    restored = PlateTemplate.from_dict(template.to_dict())
    assert restored == template
    assert len(restored.decorations) == 2


def test_plate_template_rejects_unrecognized_format():
    data = _minimal_template().to_dict()
    data["format"] = "some_other_format_v9"
    with pytest.raises(ValueError, match="unrecognized plate template format"):
        PlateTemplate.from_dict(data)


def test_plate_template_from_dict_raises_on_missing_required_field():
    data = _minimal_template().to_dict()
    del data["width_mm"]
    with pytest.raises(KeyError):
        PlateTemplate.from_dict(data)


# ---------------------------------------------------------------------------
# PlateInstance / FieldOverride / DecorationOverride
# ---------------------------------------------------------------------------

def test_plate_instance_round_trip_authentic_mode():
    instance = PlateInstance(
        template_id="gb-current-standard",
        mode="authentic",
        field_values={"registration": "AB12 CDE"},
        generated_at="2026-08-25T00:00:00Z",
    )
    restored = PlateInstance.from_dict(instance.to_dict())
    assert restored == instance


def test_plate_instance_placeholder_font_round_trips():
    instance = PlateInstance(template_id="us-ca-passenger-current", mode="authentic", placeholder_font=7)
    restored = PlateInstance.from_dict(instance.to_dict())
    assert restored.placeholder_font == 7


def test_plate_instance_placeholder_font_defaults_to_none():
    instance = PlateInstance(template_id="us-ca-passenger-current", mode="authentic")
    assert instance.placeholder_font is None
    restored = PlateInstance.from_dict(instance.to_dict())
    assert restored.placeholder_font is None


def test_plate_instance_round_trip_vanity_mode_with_overrides():
    instance = PlateInstance(
        template_id="jp-private-passenger-current",
        mode="vanity",
        field_values={
            "region_kanji": "品川",  # Shinagawa
            "classification_number": "530",
            "hiragana": "あ",
            "serial": "12-34",
        },
        field_overrides={
            "registration": FieldOverride(color=(255, 0, 0, 255), char_scale=1.1),
        },
        decoration_overrides={
            "seal": DecorationOverride(visible=False),
        },
    )
    restored = PlateInstance.from_dict(instance.to_dict())
    assert restored == instance
    assert restored.field_values["region_kanji"] == "品川"
    assert restored.decoration_overrides["seal"].visible is False


def test_plate_instance_rejects_unrecognized_format():
    data = PlateInstance(template_id="x", mode="vanity").to_dict()
    data["format"] = "wrong"
    with pytest.raises(ValueError, match="unrecognized plate instance format"):
        PlateInstance.from_dict(data)


def test_field_override_all_none_round_trips_as_no_op():
    override = FieldOverride()
    restored = FieldOverride.from_dict(override.to_dict())
    assert restored == override
    assert restored.char_source is None and restored.color is None
