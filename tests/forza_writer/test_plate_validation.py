"""Tests for forza_writer/plates/validation.py and validation_rules.py:
checking a PlateInstance's typed field text against its template's
FieldValidation rules."""

from forza_writer.plates.instance import PlateInstance
from forza_writer.plates.template import (
    CharSource,
    FieldRole,
    FieldValidation,
    PlateField,
)
from forza_writer.plates.validation import (
    is_valid_for_generation,
    validate_field_text,
    validate_instance,
)


def _field(field_id="registration", validation=None, default_text=""):
    return PlateField(
        field_id=field_id, label_key="k", role=FieldRole.REGISTRATION,
        x_mm=0.0, y_mm=0.0, width_mm=100.0, height_mm=50.0, alignment="center",
        char_source=CharSource(font_file="X"),
        default_text=default_text, validation=validation,
    )


# ---------------------------------------------------------------------------
# validate_field_text: basic rule types
# ---------------------------------------------------------------------------

def test_field_with_no_validation_always_passes():
    field = _field(validation=None)
    assert validate_field_text(field, "anything at all") is None


def test_length_bounds():
    validation = FieldValidation(format_hint_key="hint", min_length=3, max_length=5)
    field = _field(validation=validation)
    assert validate_field_text(field, "AB") is not None
    assert validate_field_text(field, "ABCDEF") is not None
    assert validate_field_text(field, "ABC") is None
    assert validate_field_text(field, "ABCDE") is None


def test_allowed_pattern():
    validation = FieldValidation(format_hint_key="Format: AA99 AAA", allowed_pattern=r"[A-Z]{2}[0-9]{2}[A-Z]{3}")
    field = _field(validation=validation)
    assert validate_field_text(field, "AB12CDE") is None
    assert validate_field_text(field, "ab12cde") is not None  # lowercase not matched by the pattern
    assert validate_field_text(field, "AB12CD") is not None  # too short for the pattern


def test_excluded_chars():
    validation = FieldValidation(format_hint_key="hint", excluded_chars=("I", "Q"))
    field = _field(validation=validation)
    error = validate_field_text(field, "ABIQCD")
    assert error is not None
    assert "I" in error.reason and "Q" in error.reason
    assert validate_field_text(field, "ABCD") is None


def test_check_order_reports_length_before_pattern():
    validation = FieldValidation(format_hint_key="hint", min_length=10, allowed_pattern=r"[A-Z]+")
    field = _field(validation=validation)
    error = validate_field_text(field, "ab")  # fails both length and pattern
    assert "character(s) long" in error.reason


def test_error_carries_field_id_and_format_hint_key():
    validation = FieldValidation(format_hint_key="plates.validation.example", min_length=5)
    field = _field(field_id="my_field", validation=validation)
    error = validate_field_text(field, "x")
    assert error.field_id == "my_field"
    assert error.format_hint_key == "plates.validation.example"


# ---------------------------------------------------------------------------
# custom_rule_id
# ---------------------------------------------------------------------------

def test_custom_rule_us_ca_positional_letter_exclusion():
    validation = FieldValidation(format_hint_key="hint",
                                  custom_rule_id="us_ca_no_ambiguous_letters_in_outer_positions")
    field = _field(validation=validation)
    assert validate_field_text(field, "1ABC234") is None
    assert validate_field_text(field, "1IBC234") is not None  # 'I' in first letter position
    assert validate_field_text(field, "1ABQ234") is not None  # 'Q' in third letter position
    assert validate_field_text(field, "1ABCI34") is None      # 'I' in an unconstrained (2nd) letter position


def test_custom_rule_jp_leading_zero_as_dot():
    validation = FieldValidation(format_hint_key="hint", custom_rule_id="jp_serial_leading_zero_as_dot")
    field = _field(validation=validation)
    assert validate_field_text(field, "12-34") is None
    assert validate_field_text(field, "・1-23") is None
    assert validate_field_text(field, "01-23") is not None


def test_unknown_custom_rule_id_reports_a_clear_error_rather_than_crashing():
    validation = FieldValidation(format_hint_key="hint", custom_rule_id="nonexistent_rule")
    field = _field(validation=validation)
    error = validate_field_text(field, "anything")
    assert error is not None
    assert "nonexistent_rule" in error.reason


# ---------------------------------------------------------------------------
# validate_instance / is_valid_for_generation
# ---------------------------------------------------------------------------

def test_validate_instance_uses_default_text_when_field_value_missing():
    validation = FieldValidation(format_hint_key="hint", min_length=10)
    field = _field(validation=validation, default_text="short")
    template = _make_template(field)
    instance = PlateInstance(template_id="t", mode="authentic", field_values={})
    errors = validate_instance(template, instance)
    assert len(errors) == 1
    assert errors[0].field_id == field.field_id


def _make_template(*fields):
    from forza_writer.plates.template import (
        AccuracyStatus, Decoration, DecorationKind, PlateTemplate, Provenance,
    )
    return PlateTemplate(
        template_id="t", display_name_key="k", country="US", jurisdiction=None,
        era="current", plate_type="passenger", width_mm=300.0, height_mm=150.0,
        accuracy_status=AccuracyStatus.FICTIONAL, provenance=Provenance(source_notes="test"),
        background=Decoration(decoration_id="bg", kind=DecorationKind.SOLID_FILL, x_mm=0.0, y_mm=0.0,
                               color=(255, 255, 255, 255), editable=False),
        border=None, fields=fields,
    )


def test_is_valid_for_generation_blocks_authentic_mode_on_error():
    validation = FieldValidation(format_hint_key="hint", min_length=10)
    field = _field(validation=validation)
    template = _make_template(field)
    instance = PlateInstance(template_id="t", mode="authentic", field_values={"registration": "AB"})
    assert is_valid_for_generation(template, instance) is False


def test_is_valid_for_generation_never_blocks_vanity_mode():
    validation = FieldValidation(format_hint_key="hint", min_length=10)
    field = _field(validation=validation)
    template = _make_template(field)
    instance = PlateInstance(template_id="t", mode="vanity", field_values={"registration": "AB"})
    assert is_valid_for_generation(template, instance) is True


def test_is_valid_for_generation_true_when_authentic_and_all_fields_pass():
    validation = FieldValidation(format_hint_key="hint", min_length=1)
    field = _field(validation=validation)
    template = _make_template(field)
    instance = PlateInstance(template_id="t", mode="authentic", field_values={"registration": "AB"})
    assert is_valid_for_generation(template, instance) is True
