"""Loads and searches the bundled GTPlanet Colour Creation Database
(`assets/data/manufacturer_colors.json`, built by `tools/build_manufacturer_colors.py`;
see THIRD_PARTY_NOTICES.md for the credit/usage note).

Pure data-layer module with no Tk dependency, so it stays independently
testable and reusable even though the Composer GUI's Manufacturer Colors
pack is the only current caller.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent.parent / "assets" / "data" / "manufacturer_colors.json"


@dataclass(frozen=True)
class ManufacturerColor:
    make: str
    name: str
    paint_type: str
    category: str  # "Vehicle" or "Wheel"
    hex1: str
    hex2: str  # "" when the entry has no second (two-tone) color
    hue: str    # e.g. "0.53 L": exact source slider-click notation
    saturation: str
    brightness: str


@lru_cache(maxsize=1)
def load_all() -> tuple[ManufacturerColor, ...]:
    raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    return tuple(ManufacturerColor(*row) for row in raw)


@lru_cache(maxsize=1)
def all_makes() -> tuple[str, ...]:
    return tuple(sorted({c.make for c in load_all()}))


def search(term: str = "", make: str | None = None) -> list[ManufacturerColor]:
    """Case-insensitive substring match over make+name; `make`, if given,
    filters to that exact make first (cheaper and more precise than folding
    it into the substring search)."""
    term = term.strip().lower()
    colors = load_all()
    if make:
        colors = tuple(c for c in colors if c.make == make)
    if not term:
        return list(colors)
    return [c for c in colors if term in c.make.lower() or term in c.name.lower()]
