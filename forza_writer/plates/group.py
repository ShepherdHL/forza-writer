"""`PlateGroupNode`: a general parent/child shape-grouping tree over the
renderer's flat output shape list.

Deliberately not built on `forza_writer/layered_effects.py`'s `EffectLayer`/
`LayerStack` (a flat, single-glyph geometric-effect stack -- a different
concept with the same word "layer") and not an extension of the Composer
tab's per-line model. Naming this a plate-specific, general-purpose concept
avoids overloading either existing term (see
`docs/PLATE_GENERATOR_ARCHITECTURE.md`'s naming-decisions section).

A node wraps *indices* into the same flat shape list `forza_writer.export`
already understands -- it is purely an organizational view over that list,
never a second geometry representation, so a generated plate's shapes are
never locked behind a plate-specific format: they are ordinary shapes with
an optional grouping tree alongside them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class GroupKind(str, Enum):
    """What a `PlateGroupNode` represents, for UI labeling -- the renderer
    builds this tree matching spec's suggested hierarchy: License Plate ->
    Background/Border/Fields/Decorations. Each FIELD node also has one
    CHARACTER child per typed character -- a placeholder box the user
    replaces with real letterform artwork and fine-tunes in KFPS (see
    `glyph_resolve.py`'s module docstring); `name_key` on a CHARACTER node
    is the literal character itself, not a translation key."""

    PLATE = "plate"
    BACKGROUND = "background"
    BORDER = "border"
    FIELD = "field"
    CHARACTER = "character"
    DECORATION = "decoration"
    CUSTOM = "custom"


@dataclass
class PlateGroupNode:
    node_id: str
    kind: GroupKind
    name_key: str | None = None
    children: list["PlateGroupNode"] = field(default_factory=list)
    shape_indices: tuple[int, ...] = ()
    editable: bool = True
    deletable: bool = True

    def flatten(self) -> list[int]:
        """Every shape index under this node, recursively, in tree order."""
        indices = list(self.shape_indices)
        for child in self.children:
            indices.extend(child.flatten())
        return indices

    def find(self, node_id: str) -> "PlateGroupNode | None":
        if self.node_id == node_id:
            return self
        for child in self.children:
            found = child.find(node_id)
            if found is not None:
                return found
        return None

    def to_group_tuples(self) -> list[tuple[str, list[int]]]:
        """This tree flattened into `forza_writer.fabric_project.to_fabric_project`'s
        `groups: list[(group_name, shape_indices)]` parameter -- one entry
        per node that actually owns shapes directly (a purely-organizational
        node with only child groups and no `shape_indices` of its own
        contributes no entry, since KFPS's own group model is flat and has
        nothing to attach an empty group to). Every node still contributes
        its descendants' shapes through them; only the *node itself* being
        empty of *direct* shapes is skipped."""
        tuples: list[tuple[str, list[int]]] = []
        if self.shape_indices:
            tuples.append((self.name_key or self.node_id, list(self.shape_indices)))
        for child in self.children:
            tuples.extend(child.to_group_tuples())
        return tuples

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "kind": self.kind.value,
            "name_key": self.name_key,
            "children": [child.to_dict() for child in self.children],
            "shape_indices": list(self.shape_indices),
            "editable": self.editable,
            "deletable": self.deletable,
        }

    @staticmethod
    def from_dict(data: dict) -> "PlateGroupNode":
        return PlateGroupNode(
            node_id=data["node_id"],
            kind=GroupKind(data["kind"]),
            name_key=data.get("name_key"),
            children=[PlateGroupNode.from_dict(child) for child in data.get("children", ())],
            shape_indices=tuple(data.get("shape_indices", ())),
            editable=bool(data.get("editable", True)),
            deletable=bool(data.get("deletable", True)),
        )
