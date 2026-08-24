"""Export shape lists to fh6_typecode_json_export_v1 JSON."""

import json
from pathlib import Path
from typing import Any


def to_json(shapes: list[dict]) -> dict[str, Any]:
    return {
        "format": "fh6_typecode_json_export_v1",
        "source": "forza-writer",
        "shapes": [
            {
                # Default first, shape's own value second — a shape that
                # already sets mask (e.g. a stencil-mode cutout) must win.
                # Doing this the other way around silently clobbers every
                # mask:True back to False on export.
                "mask": False,
                **shape,
            }
            for shape in shapes
        ],
    }


def save(data: dict[str, Any], path: str | Path) -> None:
    out_path = Path(path)
    out_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
