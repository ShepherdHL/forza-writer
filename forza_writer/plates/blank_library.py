"""A library of pre-rendered "blank plate" files: the background, border,
and decoration shapes for one `PlateTemplate`, rendered once (by
`tools/gen_plate_blanks.py`) and reused on every subsequent generation
instead of being rebuilt from the template's `Decoration` data each time.

Only the *non-field* geometry is cached here -- registration text is always
composed fresh per instance (it's the one part that actually depends on
what the user typed), from an already-generated fontpack (see
`glyph_resolve.py`), never fitted live either way. `renderer.py::render_plate`
loads a blank via `load_blank`, falling back to rendering the decorations
on the fly (`renderer.render_plate_blank`) only when no cached blank exists
yet, or when a Vanity-mode instance actually overrides a decoration (the
cached blank reflects the template's own defaults, not any particular
instance's overrides).

**Staleness**: a saved blank embeds a signature of the template's
background/border/decorations at save time (`decoration_signature`).
`load_blank` recomputes that signature from the *current* template and
refuses to return a blank whose stored signature doesn't match -- someone
editing a template's decorations and forgetting to re-run
`tools/gen_plate_blanks.py` gets a correct (if uncached) render instead of
silently stale geometry. There is no way to detect this from the shapes
alone (they're just numbers), so the signature has to be computed from the
template's own data and carried alongside the cache.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from forza_writer.plates.group import PlateGroupNode
from forza_writer.plates.template import PlateTemplate

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_BLANKS_DIR = _REPO_ROOT / "data" / "plate_blanks"

FORMAT_VERSION = "forza_writer_plate_blank_v1"


def decoration_signature(template: PlateTemplate) -> str:
    """A short, stable hash of everything `render_plate_blank` actually
    reads from `template` (background, border, decorations) -- changes
    whenever any of those change, so a cached blank keyed to an old
    signature is detectably stale. Deliberately excludes fields/other
    template data that `render_plate_blank` never looks at, so editing a
    field's text or validation doesn't needlessly invalidate the cache."""
    payload = {
        "background": template.background.to_dict(),
        "border": template.border.to_dict() if template.border else None,
        "decorations": [d.to_dict() for d in template.decorations],
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8"))
    return digest.hexdigest()[:16]


def blank_path(template_id: str, country: str, directory: Path | None = None) -> Path:
    """Mirrors `data/plate_templates/<country>/<template_id>.json`'s own
    per-country nesting (`forza_writer/plates/loader.py`'s convention).

    `directory` defaults to the *current* value of this module's
    `DEFAULT_BLANKS_DIR`, resolved when this function actually runs -- not
    `None`, and not `DEFAULT_BLANKS_DIR` bound directly as the parameter's
    default. A bound default is captured once, at function-definition time
    (import time), so `monkeypatch.setattr(blank_library, "DEFAULT_BLANKS_DIR", ...)`
    in a test would silently have no effect on it -- confirmed directly:
    an earlier version of this function did exactly that and a test using
    the monkeypatch still wrote a real file into the repo's own
    data/plate_blanks/, not the test's tmp_path."""
    if directory is None:
        directory = DEFAULT_BLANKS_DIR
    return directory / country / f"{template_id}.json"


def save_blank(template: PlateTemplate, shapes: list[dict], nodes: list[PlateGroupNode],
               warnings: list[str], directory: Path | None = None) -> Path:
    path = blank_path(template.template_id, template.country, directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "format": FORMAT_VERSION,
        "template_id": template.template_id,
        "decoration_signature": decoration_signature(template),
        "shapes": shapes,
        "nodes": [node.to_dict() for node in nodes],
        "warnings": warnings,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def load_blank(template: PlateTemplate, directory: Path | None = None
                ) -> tuple[list[dict], list[PlateGroupNode], list[str]] | None:
    """`(shapes, top-level nodes, warnings)` for `template`, or `None` if no
    pre-rendered blank exists yet, it doesn't match `template`'s id, or its
    stored `decoration_signature` no longer matches `template`'s current
    background/border/decorations (stale -- see module docstring). Callers
    fall back to rendering on the fly in every `None` case; never raises on
    a missing or corrupt file."""
    path = blank_path(template.template_id, template.country, directory)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if data.get("format") != FORMAT_VERSION or data.get("template_id") != template.template_id:
        return None
    if data.get("decoration_signature") != decoration_signature(template):
        return None
    nodes = [PlateGroupNode.from_dict(node) for node in data.get("nodes", ())]
    return list(data.get("shapes", ())), nodes, list(data.get("warnings", ()))
