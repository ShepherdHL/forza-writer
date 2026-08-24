"""Wrap forza-writer shape lists into a KFPS Fabric Editor project file
(`.fabric-project.json`). General-purpose: takes any shape-dict list in the
format `forza_writer.layout` already produces
(`{"type", "type_word", "data", "color"}`), not coupled to any particular
generator — usable for primitive-fit output today, and for hijacked
custom-mesh shape references later.

Schema confirmed against two real KFPS project files, not reverse-engineered
from docs alone: a hand-made `AmarilloUSAF_FontPack.fabric-project.json`
(top-level structure, editor_source_overlay) and a KFPS-generated project
under `runtime/fabric-editor/projects/` (the grouping convention — flat
per-shape `editor_group_id`/`editor_group_name` fields, no separate group
registry). See KFPS's `docs/FABRIC_EDITOR_MANUAL.md` for behavior notes,
especially "Reference Image" and "Editor Groups" (both editor-only, never
exported as vinyl layers/game data).
"""

from __future__ import annotations

import json
import random
import string
from pathlib import Path
from typing import Any

from forza_writer.primitive_shapes import PRIMITIVE_CATALOG
from forza_writer.shapes import shape_word_to_resource

FORMAT = "kloudy_fabric_editor_project_v1"

# Matches the defaults observed in a real hand-made project file's
# editor_guides block — an empty-but-complete guides object, since we have
# no actual guide data to contribute.
_DEFAULT_EDITOR_GUIDES = {
    "version": 1,
    "gridEnabled": False,
    "gridSize": 50,
    "gridOpacity": 20,
    "guidesVisible": True,
    "snapGuides": True,
    "snapGrid": True,
    "snapCtrlOnly": True,
    "snapThreshold": 12,
    "guideConstraint": "free",
    "snapGuideAnchor": False,
    "snapGuideEnd": False,
    "guides": [],
}


def _group_id() -> str:
    alphabet = string.ascii_lowercase + string.digits
    token = "".join(random.choices(alphabet, k=8))
    token2 = "".join(random.choices(alphabet, k=8))
    return f"group-{token}-{token2}"


def _shape_name(family: str | None, index: int | None) -> str | None:
    if family is None:
        return None
    if family == "Primitives":
        for shape in PRIMITIVE_CATALOG.values():
            if shape.resource_index == index:
                return shape.display_name
    return f"{family} {index}"


def _enrich_shape(shape: dict, editor_id: str, group_id: str | None, group_name: str | None) -> dict:
    type_word = shape["type_word"]
    resource = shape_word_to_resource(type_word)
    family, index = resource if resource else (None, None)
    return {
        "type": shape["type"],
        "type_word": type_word,
        "data": list(shape["data"]),
        "color": list(shape["color"]),
        "mask": shape.get("mask", False),
        "score": 0,
        "source_format": "fh6_typecode",
        "resource_family": family,
        "resource_index": index,
        "shape_name": _shape_name(family, index),
        "legacy_type": None,
        "legacy_divisor": None,
        "legacy_offset": None,
        "editor_id": editor_id,
        "editor_hidden": False,
        "editor_locked": False,
        "editor_group_id": group_id,
        "editor_group_name": group_name,
    }


def to_fabric_project(shapes: list[dict], name: str,
                       groups: list[tuple[str, list[int]]] | None = None,
                       source_overlay: dict | None = None) -> dict[str, Any]:
    """Build a KFPS `.fabric-project.json` dict from a flat shape list.

    `groups`: list of `(group_name, shape_indices)`, where `shape_indices`
    index into `shapes`. Shapes not covered by any group get
    `editor_group_id`/`editor_group_name` = None. Group ids are synthesized
    locally — they don't need to match KFPS's own generator, just be unique
    and structurally consistent within this project.

    `source_overlay`, if given, is embedded verbatim as `editor_source_overlay`
    (build one with `forza_writer.reference_svg`). Omitted entirely if None —
    a fabric project doesn't require a reference image.
    """
    index_to_group: dict[int, tuple[str, str]] = {}
    if groups:
        for group_name, indices in groups:
            gid = _group_id()
            for i in indices:
                index_to_group[i] = (gid, group_name)

    enriched = []
    for i, shape in enumerate(shapes):
        gid, gname = index_to_group.get(i, (None, None))
        enriched.append(_enrich_shape(shape, f"e{i + 1}", gid, gname))

    project: dict[str, Any] = {
        "format": FORMAT,
        "name": name,
        "layer_count": len(enriched),
        "shapes": enriched,
        "editor_guides": dict(_DEFAULT_EDITOR_GUIDES),
        "editor_collapsed_groups": [],
    }
    if source_overlay is not None:
        project["editor_source_overlay"] = source_overlay
    return project


def save(data: dict[str, Any], path: str | Path) -> None:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
