"""Generated plate output -- the user's typed values and (in Vanity mode)
per-field/decoration overrides, distinct from the `PlateTemplate` that
defines the standard. Keeping these separate is spec's explicit "standards
vs. instances" split: a template is a reusable rulebook; a `PlateInstance` is
one specific plate someone asked for. The renderer (`renderer.py`, Phase 5)
takes both and produces shapes -- neither dataclass here holds geometry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from forza_writer.plates.template import CharSource
from forza_writer.text_style import RGBA

FORMAT_VERSION = "forza_writer_plate_instance_v1"

PlateMode = Literal["authentic", "vanity"]


@dataclass(frozen=True)
class FieldOverride:
    """Vanity-mode-only per-field appearance override. Every value defaults
    to `None`, meaning "use the template's own setting" -- only fields a
    user actually changed carry a non-None value, so an instance's overrides
    dict stays small and a template update doesn't get silently masked by
    stale overrides the user never touched."""

    char_source: CharSource | None = None
    char_scale: float | None = None
    tracking: float | None = None
    color: RGBA | None = None
    alignment: str | None = None
    x_mm: float | None = None
    y_mm: float | None = None

    def to_dict(self) -> dict:
        return {
            "char_source": self.char_source.to_dict() if self.char_source else None,
            "char_scale": self.char_scale,
            "tracking": self.tracking,
            "color": list(self.color) if self.color else None,
            "alignment": self.alignment,
            "x_mm": self.x_mm,
            "y_mm": self.y_mm,
        }

    @staticmethod
    def from_dict(data: dict) -> "FieldOverride":
        char_source = data.get("char_source")
        color = data.get("color")
        return FieldOverride(
            char_source=CharSource.from_dict(char_source) if char_source else None,
            char_scale=data.get("char_scale"),
            tracking=data.get("tracking"),
            color=tuple(int(c) for c in color) if color else None,  # type: ignore[assignment]
            alignment=data.get("alignment"),
            x_mm=data.get("x_mm"),
            y_mm=data.get("y_mm"),
        )


@dataclass(frozen=True)
class DecorationOverride:
    """Vanity-mode-only per-decoration override: recolor, reposition, or
    hide (spec's "decorative components deletable" -- `visible=False` is how
    an instance expresses deletion without needing the renderer to special-
    case a missing dict entry vs. an intentionally-hidden one)."""

    color: RGBA | None = None
    visible: bool = True
    x_mm: float | None = None
    y_mm: float | None = None

    def to_dict(self) -> dict:
        return {
            "color": list(self.color) if self.color else None,
            "visible": self.visible,
            "x_mm": self.x_mm,
            "y_mm": self.y_mm,
        }

    @staticmethod
    def from_dict(data: dict) -> "DecorationOverride":
        color = data.get("color")
        return DecorationOverride(
            color=tuple(int(c) for c in color) if color else None,  # type: ignore[assignment]
            visible=bool(data.get("visible", True)),
            x_mm=data.get("x_mm"),
            y_mm=data.get("y_mm"),
        )


@dataclass(frozen=True)
class PlateInstance:
    """One generated (or about-to-be-generated) plate: which template, which
    mode, and the user's field text/overrides. `mode` is what drives the
    Authentic/Vanity UI badge and validation strictness (see
    `template.py::FieldValidation` and `forza_writer/plates/validation.py`,
    Phase 2) -- it travels with the instance so a saved/reloaded plate still
    knows which rules applied to it."""

    template_id: str
    mode: PlateMode
    field_values: dict[str, str] = field(default_factory=dict)
    field_overrides: dict[str, FieldOverride] = field(default_factory=dict)
    decoration_overrides: dict[str, DecorationOverride] = field(default_factory=dict)
    generated_at: str | None = None
    # 1-11 picks one of FH6's 11 native in-game vinyl fonts (see
    # forza_writer.shapes.char_to_resource) as a stand-in for every
    # character's placeholder box -- real, final game-native letterform
    # meshes, not a fitted/traced substitute (the same shapes
    # forza_font_text.py's tab already uses), so this costs nothing extra
    # to render and produces real geometry, not just a preview convenience.
    # None (the default) keeps every character a plain box, matching this
    # feature's original design -- see glyph_resolve.py's module docstring
    # for why a plate field never generates letterform geometry of its own.
    # A character with no shape in the chosen Forza font (font coverage is
    # letters/digits/limited punctuation only) falls back to a plain box
    # for that one character.
    placeholder_font: int | None = None

    def to_dict(self) -> dict:
        return {
            "format": FORMAT_VERSION,
            "template_id": self.template_id,
            "mode": self.mode,
            "field_values": dict(self.field_values),
            "field_overrides": {k: v.to_dict() for k, v in self.field_overrides.items()},
            "decoration_overrides": {k: v.to_dict() for k, v in self.decoration_overrides.items()},
            "generated_at": self.generated_at,
            "placeholder_font": self.placeholder_font,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PlateInstance":
        if data.get("format") != FORMAT_VERSION:
            raise ValueError(f"unrecognized plate instance format: {data.get('format')!r}")
        return cls(
            template_id=data["template_id"],
            mode=data["mode"],
            field_values=dict(data.get("field_values", {})),
            field_overrides={
                k: FieldOverride.from_dict(v) for k, v in data.get("field_overrides", {}).items()
            },
            decoration_overrides={
                k: DecorationOverride.from_dict(v) for k, v in data.get("decoration_overrides", {}).items()
            },
            generated_at=data.get("generated_at"),
            placeholder_font=data.get("placeholder_font"),
        )
