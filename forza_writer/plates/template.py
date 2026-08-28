"""License plate template data model.

A `PlateTemplate` is a data-driven description of one real-world or fictional
license plate standard (dimensions, background/border, an ordered list of
independently-addressable `PlateField`s, and reusable `Decoration`
components). It is never mutated into rendered geometry directly: the
renderer (`forza_writer/plates/renderer.py`) combines a `PlateTemplate` with
a `PlateInstance` (`instance.py`, the user's typed values and overrides) to
produce shapes. This split -- standard vs. instance -- is what lets a
template be added by writing JSON rather than code, and lets the same
template serve both Authentic and Vanity/Custom generation.

Every dataclass here is frozen and round-trips through `to_dict()`/
`from_dict()`, matching the convention `forza_writer/layered_effects.py`
(`EffectLayer`) and `forza_writer/glyph_template.py` (`GlyphTemplate`) already
use: lenient `from_dict` (defaults for missing keys where a sensible default
exists), explicit type coercion, and a `format_version` string on the
top-level container so a future format change can be detected rather than
silently misread.

Field text is not validated by this module -- `PlateField.validation`
(`FieldValidation`) only *describes* the rule; applying it against user input
is `forza_writer/plates/validation.py`'s job (Phase 2). Keeping the schema
and the validation logic separate means a template can be loaded, browsed,
and inspected even before its glyph assets exist, and lets the same
`FieldValidation` be read two ways: enforced in Authentic mode, advisory-only
in Vanity mode (see `PlateInstance.mode` in `instance.py`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from forza_writer.text_style import RGBA

FORMAT_VERSION = "forza_writer_plate_template_v1"


class AccuracyStatus(str, Enum):
    """How confidently a template's real-world claims are sourced. Never
    implies legal/historical accuracy beyond what's actually verified --
    surfaced in the generator UI's details panel, not the primary flow."""

    VERIFIED = "verified"
    REFERENCE_BASED = "reference_based"
    APPROXIMATE = "approximate"
    COMMUNITY_RECONSTRUCTION = "community_reconstruction"
    FICTIONAL = "fictional"


class FieldRole(str, Enum):
    """What kind of content a `PlateField` holds, for UI grouping/labeling
    and for renderer decisions that depend on role rather than on any
    jurisdiction-specific identity (e.g. which fields a details panel
    describes as "the registration" regardless of template)."""

    REGISTRATION = "registration"
    REGION_CODE = "region_code"
    CLASSIFICATION = "classification"
    JURISDICTION_TEXT = "jurisdiction_text"
    DECORATIVE_TEXT = "decorative_text"
    FREE_TEXT = "free_text"


class DecorationKind(str, Enum):
    """What a `Decoration` represents, for renderer placement logic and UI
    labeling. SOLID_FILL covers both a plate's full background and any plain
    colored rect; the rest name specific reusable plate components."""

    SOLID_FILL = "solid_fill"
    BORDER = "border"
    SEAL = "seal"
    LOGO = "logo"
    SEPARATOR = "separator"
    STICKER = "sticker"
    BOLT_HOLE = "bolt_hole"
    JURISDICTION_MARK = "jurisdiction_mark"
    CUSTOM_SHAPE = "custom_shape"


@dataclass(frozen=True)
class CharSource:
    """Which font's metrics (advance widths, cap height) size and space one
    `PlateField`'s characters. `font_file` is a path relative to
    `assets/fonts/` (e.g. `"LiberationSans-Regular.ttf"`), read once via
    fontTools purely for those metrics -- **no letterform geometry is ever
    produced from it.** A `PlateField`'s rendered output is a plain
    placeholder box per character, correctly sized and spaced as if it held
    that font's real glyph, for the user to replace with their own artwork
    (existing or hand-made) and fine-tune in KFPS. See
    `docs/PLATE_GENERATOR_ARCHITECTURE.md`'s changelog note.

    This is the second time this field's job has narrowed, not the first:
    the original design supported live font-fitting (TTF_DIRECT) and a
    plate-specific hand-traced-glyph reader (HAND_TRACED_TEMPLATE); those
    were replaced by a fontpack-only design (every field drawing real
    pixel-traced letterforms from a pre-generated fontpack); that in turn
    is replaced by this one, after direct feedback that pixel-traced plate
    text looked poor and cost far too many shapes for an in-game decal --
    Forza Writer's job on a plate's *characters* specifically is now
    typesetting only, not artwork.

    `fallback` lets a font missing a character's metrics (not in its cmap)
    fall back to a different font's metrics for that whole field, rather
    than every template needing one font with complete coverage -- e.g. a
    Latin registration field falling back to a CJK font's metrics is never
    needed in practice, but a template mixing scripts within one field
    would need it."""

    font_file: str
    fallback: "CharSource | None" = None

    def __post_init__(self):
        if not self.font_file:
            raise ValueError("CharSource requires a non-empty font_file")

    def to_dict(self) -> dict:
        return {
            "font_file": self.font_file,
            "fallback": self.fallback.to_dict() if self.fallback else None,
        }

    @staticmethod
    def from_dict(data: dict) -> "CharSource":
        fallback = data.get("fallback")
        return CharSource(
            font_file=data["font_file"],
            fallback=CharSource.from_dict(fallback) if fallback else None,
        )


@dataclass(frozen=True)
class FieldValidation:
    """The rule a `PlateField`'s typed text is checked against. Enforced
    (blocking, with this error shown) in Authentic mode; shown as a hint only
    in Vanity mode -- see `instance.py`'s `PlateInstance.mode`.

    `custom_rule_id` is the only place a template can invoke Python logic
    (a name looked up in `validation_rules.py::RULE_REGISTRY`, Phase 2), kept
    deliberately narrow so templates stay declarative while still able to
    express genuinely irregular real-world rules that no regex/exclusion
    list captures cleanly (e.g. Japan's centered-dot leading zero, a
    positional-only letter exclusion)."""

    format_hint_key: str
    min_length: int | None = None
    max_length: int | None = None
    allowed_pattern: str | None = None
    excluded_chars: tuple[str, ...] = ()
    custom_rule_id: str | None = None

    def to_dict(self) -> dict:
        return {
            "format_hint_key": self.format_hint_key,
            "min_length": self.min_length,
            "max_length": self.max_length,
            "allowed_pattern": self.allowed_pattern,
            "excluded_chars": list(self.excluded_chars),
            "custom_rule_id": self.custom_rule_id,
        }

    @staticmethod
    def from_dict(data: dict) -> "FieldValidation":
        return FieldValidation(
            format_hint_key=data["format_hint_key"],
            min_length=data.get("min_length"),
            max_length=data.get("max_length"),
            allowed_pattern=data.get("allowed_pattern"),
            excluded_chars=tuple(data.get("excluded_chars", ())),
            custom_rule_id=data.get("custom_rule_id"),
        )


@dataclass(frozen=True)
class PlateField:
    """One independently-addressable field on a plate (e.g. a Japanese
    plate's region name, classification number, hiragana character, and
    serial number are four separate `PlateField`s, each with its own
    `char_source` and `char_scale` -- this is what makes that four-field
    case fall out of the generic schema instead of needing renderer-side
    special-casing for Japan).

    Position/size are in the template's own physical mm space (top-left
    origin), independent of any pixel/preview resolution -- see
    `PlateTemplate.width_mm`/`height_mm`.

    `color`, if set, is the standard's own required text color (e.g. Japan's
    green private-passenger registration text) -- fixed for Authentic mode,
    and the base a Vanity-mode `FieldOverride.color` overrides. `None` means
    the underlying glyph pipeline's own default (typically white)."""

    field_id: str
    label_key: str
    role: FieldRole
    x_mm: float
    y_mm: float
    width_mm: float
    height_mm: float
    alignment: str  # one of forza_writer.text_compose.ALIGNMENTS
    char_source: CharSource
    char_scale: float = 1.0
    tracking: float = 0.0
    line_spacing: float = 1.0
    default_text: str = ""
    color: RGBA | None = None
    validation: FieldValidation | None = None
    editable_in_authentic_mode: bool = False

    def to_dict(self) -> dict:
        return {
            "field_id": self.field_id,
            "label_key": self.label_key,
            "role": self.role.value,
            "x_mm": self.x_mm,
            "y_mm": self.y_mm,
            "width_mm": self.width_mm,
            "height_mm": self.height_mm,
            "alignment": self.alignment,
            "char_source": self.char_source.to_dict(),
            "char_scale": self.char_scale,
            "tracking": self.tracking,
            "line_spacing": self.line_spacing,
            "default_text": self.default_text,
            "color": list(self.color) if self.color else None,
            "validation": self.validation.to_dict() if self.validation else None,
            "editable_in_authentic_mode": self.editable_in_authentic_mode,
        }

    @staticmethod
    def from_dict(data: dict) -> "PlateField":
        validation = data.get("validation")
        color = data.get("color")
        return PlateField(
            field_id=data["field_id"],
            label_key=data["label_key"],
            role=FieldRole(data["role"]),
            x_mm=float(data["x_mm"]),
            y_mm=float(data["y_mm"]),
            width_mm=float(data["width_mm"]),
            height_mm=float(data["height_mm"]),
            alignment=data["alignment"],
            char_source=CharSource.from_dict(data["char_source"]),
            char_scale=float(data.get("char_scale", 1.0)),
            tracking=float(data.get("tracking", 0.0)),
            line_spacing=float(data.get("line_spacing", 1.0)),
            default_text=data.get("default_text", ""),
            color=tuple(int(c) for c in color) if color else None,  # type: ignore[assignment]
            validation=FieldValidation.from_dict(validation) if validation else None,
            editable_in_authentic_mode=bool(data.get("editable_in_authentic_mode", False)),
        )


@dataclass(frozen=True)
class Decoration:
    """A reusable plate component reference (background fill, border, seal,
    logo, separator, sticker, bolt hole, jurisdiction mark, or an arbitrary
    custom shape) -- spec's "reusable components" requirement. `asset_ref`
    points into the shared component library (`assets.py`, Phase 5);
    `color`/`width_mm`/`height_mm` are enough to render a plain solid rect
    (e.g. the plate background) with no asset at all.

    `editable=False` is reserved for load-bearing elements a Vanity-mode
    user shouldn't be able to delete (a mandatory background), distinct from
    ordinary decorative elements which spec explicitly wants deletable."""

    decoration_id: str
    kind: DecorationKind
    x_mm: float
    y_mm: float
    width_mm: float | None = None
    height_mm: float | None = None
    color: RGBA | None = None
    asset_ref: str | None = None
    editable: bool = True

    def to_dict(self) -> dict:
        return {
            "decoration_id": self.decoration_id,
            "kind": self.kind.value,
            "x_mm": self.x_mm,
            "y_mm": self.y_mm,
            "width_mm": self.width_mm,
            "height_mm": self.height_mm,
            "color": list(self.color) if self.color else None,
            "asset_ref": self.asset_ref,
            "editable": self.editable,
        }

    @staticmethod
    def from_dict(data: dict) -> "Decoration":
        color = data.get("color")
        return Decoration(
            decoration_id=data["decoration_id"],
            kind=DecorationKind(data["kind"]),
            x_mm=float(data["x_mm"]),
            y_mm=float(data["y_mm"]),
            width_mm=float(data["width_mm"]) if data.get("width_mm") is not None else None,
            height_mm=float(data["height_mm"]) if data.get("height_mm") is not None else None,
            color=tuple(int(c) for c in color) if color else None,  # type: ignore[assignment]
            asset_ref=data.get("asset_ref"),
            editable=bool(data.get("editable", True)),
        )


@dataclass(frozen=True)
class Provenance:
    """Sourcing metadata for a template or hand-traced glyph set: who
    contributed it, what it's based on, and -- critically -- honest notes
    about sourcing gaps (e.g. "dimensions verified via statute, font name
    unconfirmed"). Kept out of the primary generator UI; shown in a details
    panel alongside `PlateTemplate.accuracy_status`."""

    source_notes: str
    contributors: tuple[str, ...] = ()
    reference_urls: tuple[str, ...] = ()
    reconstruction_author: str | None = None
    year_documented: int | None = None

    def to_dict(self) -> dict:
        return {
            "source_notes": self.source_notes,
            "contributors": list(self.contributors),
            "reference_urls": list(self.reference_urls),
            "reconstruction_author": self.reconstruction_author,
            "year_documented": self.year_documented,
        }

    @staticmethod
    def from_dict(data: dict) -> "Provenance":
        return Provenance(
            source_notes=data["source_notes"],
            contributors=tuple(data.get("contributors", ())),
            reference_urls=tuple(data.get("reference_urls", ())),
            reconstruction_author=data.get("reconstruction_author"),
            year_documented=data.get("year_documented"),
        )


@dataclass(frozen=True)
class PlateTemplate:
    """One plate standard -- country, jurisdiction, era, physical
    proportions, background/border, an ordered list of `PlateField`s, and
    reusable `Decoration`s. Never mutated into rendered output directly (see
    module docstring); the same template drives both Authentic and Vanity
    generation (`PlateInstance.mode` in `instance.py` decides which).

    `border` is explicitly `None`-able (not every template has one) rather
    than defaulting to a no-op `Decoration`, so a template's JSON makes the
    absence visible instead of implying an invisible border exists."""

    template_id: str
    display_name_key: str
    country: str
    jurisdiction: str | None
    era: str
    plate_type: str
    width_mm: float
    height_mm: float
    accuracy_status: AccuracyStatus
    provenance: Provenance
    background: Decoration
    border: Decoration | None
    fields: tuple[PlateField, ...]
    format_version: str = FORMAT_VERSION
    decorations: tuple[Decoration, ...] = ()
    tags: tuple[str, ...] = ()

    def field_by_id(self, field_id: str) -> PlateField | None:
        return next((f for f in self.fields if f.field_id == field_id), None)

    def to_dict(self) -> dict:
        return {
            "format": FORMAT_VERSION,
            "template_id": self.template_id,
            "display_name_key": self.display_name_key,
            "country": self.country,
            "jurisdiction": self.jurisdiction,
            "era": self.era,
            "plate_type": self.plate_type,
            "width_mm": self.width_mm,
            "height_mm": self.height_mm,
            "accuracy_status": self.accuracy_status.value,
            "provenance": self.provenance.to_dict(),
            "background": self.background.to_dict(),
            "border": self.border.to_dict() if self.border else None,
            "fields": [f.to_dict() for f in self.fields],
            "decorations": [d.to_dict() for d in self.decorations],
            "tags": list(self.tags),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PlateTemplate":
        if data.get("format") != FORMAT_VERSION:
            raise ValueError(f"unrecognized plate template format: {data.get('format')!r}")
        border = data.get("border")
        return cls(
            template_id=data["template_id"],
            display_name_key=data["display_name_key"],
            country=data["country"],
            jurisdiction=data.get("jurisdiction"),
            era=data["era"],
            plate_type=data["plate_type"],
            width_mm=float(data["width_mm"]),
            height_mm=float(data["height_mm"]),
            accuracy_status=AccuracyStatus(data["accuracy_status"]),
            provenance=Provenance.from_dict(data["provenance"]),
            background=Decoration.from_dict(data["background"]),
            border=Decoration.from_dict(border) if border else None,
            fields=tuple(PlateField.from_dict(f) for f in data["fields"]),
            format_version=FORMAT_VERSION,
            decorations=tuple(Decoration.from_dict(d) for d in data.get("decorations", ())),
            tags=tuple(data.get("tags", ())),
        )
