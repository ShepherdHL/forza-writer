"""Validates a `PlateInstance`'s typed field text against its template's
`FieldValidation` rules -- the piece `template.py`'s own module docstring
promises and points to. Deliberately separate from both the schema
(`template.py`) and the renderer (`renderer.py`): a template can be loaded
and browsed without validating anything, and the renderer never blocks on
invalid input itself (spec explicitly wants Authentic-mode invalid input to
block *generation*, which is a decision for whatever calls the renderer --
today a test or future CLI, later the Plates tab's "Generate" button -- not
something baked into `render_plate` itself).

**Authentic vs. Vanity**: `validate_instance` always computes the same
structural facts regardless of mode (a length/pattern/exclusion violation is
still a fact even in Vanity mode) -- what differs is what a caller *does*
with the result. `is_valid_for_generation` is that mode-aware decision:
Authentic mode blocks on any error; Vanity mode's validation is advisory
only (spec section 3), so it always allows generation to proceed.
"""

from __future__ import annotations

from dataclasses import dataclass

from forza_writer.plates.instance import PlateInstance
from forza_writer.plates.template import FieldValidation, PlateField, PlateTemplate
from forza_writer.plates.validation_rules import RULE_REGISTRY


@dataclass(frozen=True)
class ValidationError:
    """One field's validation failure. `format_hint_key` is carried
    alongside `reason` (rather than requiring a second lookup) so a caller
    can show both "why this is wrong" and "what the expected format looks
    like" together, per spec's error-message requirement."""

    field_id: str
    reason: str
    format_hint_key: str


def _check_length(validation: FieldValidation, text: str) -> str | None:
    if validation.min_length is not None and len(text) < validation.min_length:
        return f"must be at least {validation.min_length} character(s) long, got {len(text)}"
    if validation.max_length is not None and len(text) > validation.max_length:
        return f"must be at most {validation.max_length} character(s) long, got {len(text)}"
    return None


def _check_pattern(validation: FieldValidation, text: str) -> str | None:
    if not validation.allowed_pattern:
        return None
    import re

    if not re.fullmatch(validation.allowed_pattern, text):
        return f"does not match the required format ({validation.allowed_pattern})"
    return None


def _check_excluded_chars(validation: FieldValidation, text: str) -> str | None:
    found = sorted({c for c in text if c in validation.excluded_chars})
    if found:
        return f"contains character(s) not allowed on this field: {', '.join(found)}"
    return None


def _check_custom_rule(validation: FieldValidation, text: str) -> str | None:
    if not validation.custom_rule_id:
        return None
    rule = RULE_REGISTRY.get(validation.custom_rule_id)
    if rule is None:
        return f"template references unknown validation rule {validation.custom_rule_id!r}"
    return rule(text)


def validate_field_text(field: PlateField, text: str) -> ValidationError | None:
    """`None` if `field` has no `validation` at all (purely decorative/free
    fields) or `text` passes every check; otherwise the *first* violation
    found, checked in a fixed, predictable order (length, then pattern,
    then excluded characters, then any custom rule) so the same input
    always reports the same reason rather than a set-iteration-order
    surprise."""
    validation = field.validation
    if validation is None:
        return None
    for check in (_check_length, _check_pattern, _check_excluded_chars, _check_custom_rule):
        reason = check(validation, text)
        if reason is not None:
            return ValidationError(field_id=field.field_id, reason=reason,
                                    format_hint_key=validation.format_hint_key)
    return None


def validate_instance(template: PlateTemplate, instance: PlateInstance) -> list[ValidationError]:
    """Every field's violation, in template field order. Uses each field's
    `default_text` when `instance.field_values` doesn't cover it -- matching
    what `renderer.py` would actually render, so validation and generation
    never silently disagree about what text is in play."""
    errors = []
    for field in template.fields:
        text = instance.field_values.get(field.field_id, field.default_text)
        error = validate_field_text(field, text)
        if error is not None:
            errors.append(error)
    return errors


def is_valid_for_generation(template: PlateTemplate, instance: PlateInstance) -> bool:
    """Whether generation should be allowed to proceed. Vanity mode's
    validation is advisory only (spec section 3) and never blocks; Authentic
    mode blocks on any `validate_instance` error."""
    if instance.mode != "authentic":
        return True
    return not validate_instance(template, instance)
