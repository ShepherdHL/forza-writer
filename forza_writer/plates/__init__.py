"""Data-driven License Plate / Vanity Plate generator.

A `PlateTemplate` (`template.py`) describes a plate standard; a
`PlateInstance` (`instance.py`) is one user's typed values against that
standard. See `docs/PLATE_GENERATOR_ARCHITECTURE.md` for the full pipeline
(template -> loader -> layout engine -> glyph resolve -> renderer -> group
tree -> export) and the reasoning behind keeping this a sibling to, not an
extension of, the existing Composer/Layer Effects tabs.
"""

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
from forza_writer.plates.instance import (
    DecorationOverride,
    FieldOverride,
    PlateInstance,
    PlateMode,
)

__all__ = [
    "AccuracyStatus",
    "CharSource",
    "Decoration",
    "DecorationKind",
    "DecorationOverride",
    "FieldOverride",
    "FieldRole",
    "FieldValidation",
    "PlateField",
    "PlateInstance",
    "PlateMode",
    "PlateTemplate",
    "Provenance",
]
