"""Inspect and instantiate OpenType variable fonts for generation.

All Forza Writer renderers receive a static font file.  Pinning every axis
first keeps Pillow's Legacy path, fontTools outline extraction, quality
checks, previews, CPU, and CUDA on the exact same glyph geometry.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont


@dataclass(frozen=True)
class VariationAxis:
    tag: str
    name: str
    minimum: float
    default: float
    maximum: float


@dataclass(frozen=True)
class NamedInstance:
    name: str
    coordinates: dict[str, float]


@dataclass(frozen=True)
class VariableFontInfo:
    axes: tuple[VariationAxis, ...]
    instances: tuple[NamedInstance, ...]

    @property
    def is_variable(self) -> bool:
        return bool(self.axes)

    @property
    def defaults(self) -> dict[str, float]:
        return {axis.tag: axis.default for axis in self.axes}


def _name(font: TTFont, name_id: int, fallback: str) -> str:
    table = font["name"] if "name" in font else None
    if table is None:
        return fallback
    value = (table.getName(name_id, 3, 1, 0x409)
             or table.getName(name_id, 3, 10, 0x409)
             or table.getName(name_id, 1, 0, 0))
    return str(value) if value is not None else fallback


def inspect_variable_font(font_path: Path) -> VariableFontInfo:
    """Return axes and named instances; a static font returns empty tuples."""
    font = TTFont(str(font_path), lazy=True, fontNumber=0)
    try:
        if "fvar" not in font:
            return VariableFontInfo((), ())
        axes = tuple(
            VariationAxis(
                axis.axisTag,
                _name(font, axis.axisNameID, axis.axisTag),
                float(axis.minValue),
                float(axis.defaultValue),
                float(axis.maxValue),
            )
            for axis in font["fvar"].axes
        )
        instances = tuple(
            NamedInstance(
                _name(font, instance.subfamilyNameID, "Unnamed instance"),
                {tag: float(value) for tag, value in instance.coordinates.items()},
            )
            for instance in font["fvar"].instances
        )
        return VariableFontInfo(axes, instances)
    finally:
        font.close()


def variation_slug(coordinates: dict[str, float]) -> str:
    """Stable filesystem-safe identity such as ``WGHT400-WDTH75``."""
    parts = []
    for tag, value in sorted(coordinates.items()):
        number = f"{float(value):.3f}".rstrip("0").rstrip(".").replace("-", "M").replace(".", "P")
        safe_tag = "".join(c for c in tag.upper() if c.isalnum()) or "AXIS"
        parts.append(f"{safe_tag}{number}")
    return "-".join(parts) or "DEFAULT"


def default_instance_cache_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "forza-writer"
    return base / "variable-instances"


def instantiate_font(font_path: Path, coordinates: dict[str, float],
                     cache_dir: Path | None = None) -> Path:
    """Pin all variable axes and return a cached static font file.

    Coordinates are clamped to the font's declared user-space ranges. Missing
    axes use the file default. Static inputs are returned unchanged.
    """
    info = inspect_variable_font(font_path)
    if not info.is_variable:
        return Path(font_path)

    resolved: dict[str, float] = {}
    for axis in info.axes:
        value = float(coordinates.get(axis.tag, axis.default))
        resolved[axis.tag] = min(axis.maximum, max(axis.minimum, value))

    source = Path(font_path).resolve()
    stat = source.stat()
    identity = json.dumps({
        "path": str(source), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns,
        "coordinates": sorted(resolved.items()),
    }, sort_keys=True).encode("utf-8")
    digest = hashlib.sha256(identity).hexdigest()[:16]
    target_dir = cache_dir or default_instance_cache_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{source.stem}__{variation_slug(resolved)}__{digest}.ttf"
    if target.exists():
        return target

    font = TTFont(str(source), fontNumber=0)
    try:
        instance = instantiateVariableFont(
            font, resolved, inplace=False, optimize=True, updateFontNames=True, static=True)
        temporary = target.with_suffix(".tmp")
        instance.save(str(temporary))
        temporary.replace(target)
    finally:
        font.close()
    return target
