"""The fixed, reviewed registry `FieldValidation.custom_rule_id` looks up.

This is the *only* place a template can invoke Python logic (see
`template.py::FieldValidation`'s docstring) -- for real-world formatting
quirks too irregular for a regex/exclusion list, such as a positional-only
letter exclusion or a serial number's non-decimal leading-zero convention.
Adding a rule here is a reviewed code change, deliberately not something a
template's own JSON can smuggle in arbitrary behavior for.

Each rule is `(text) -> str | None`: `None` means valid, a string is the
human-readable reason it's invalid (shown to the user alongside the field's
own `format_hint_key`).
"""

from __future__ import annotations

from typing import Callable

RuleFn = Callable[[str], "str | None"]


def _us_ca_no_ambiguous_letters_in_outer_positions(text: str) -> str | None:
    """California's legacy passenger format (`1ABC234`) excludes I, O, Q
    from the first and third letters of the 3-letter block (positions 2 and
    4 of the 7-character plate) to avoid confusion with 1/0 -- a positional
    rule a flat excluded-letters list can't express, since I/O/Q are
    otherwise allowed characters elsewhere on the plate."""
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 3:
        return None  # too short to have a first/third letter yet; length rules catch this separately
    for index in (0, 2):
        if letters[index].upper() in ("I", "O", "Q"):
            return (
                f"{letters[index].upper()!r} is not allowed as the "
                f"{'first' if index == 0 else 'third'} letter (visually ambiguous with 1/0)"
            )
    return None


def _jp_serial_leading_zero_as_dot(text: str) -> str | None:
    """Japanese plates show a leading zero in the 4-digit serial as a
    centered dot instead of the digit '0' (e.g. serial 0123 is shown/typed
    as '.123' or '-123' with a dot placeholder) -- this rule only checks
    that a literal '0' was not typed where the dot convention applies;
    the dot-for-display substitution itself happens in the renderer, not
    here, since validation and rendering are kept separate (module
    docstring)."""
    digits = text.replace("-", "").replace("・", "")  # strip the separator hyphen and centered dot (・)
    if digits.startswith("0"):
        return "a leading zero in the serial number is written as a centered dot (・), not the digit 0"
    return None


RULE_REGISTRY: dict[str, RuleFn] = {
    "us_ca_no_ambiguous_letters_in_outer_positions": _us_ca_no_ambiguous_letters_in_outer_positions,
    "jp_serial_leading_zero_as_dot": _jp_serial_leading_zero_as_dot,
}
