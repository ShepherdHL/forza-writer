"""Loads and validates `PlateTemplate`s from `data/plate_templates/`, and
provides the searchable/filterable registry the plate browser (Phase 6)
queries.

Templates are laid out one subdirectory per country
(`data/plate_templates/<ISO-3166-1-alpha-2>/<template_id>.json`, e.g.
`US/us-ca-passenger-current.json`) rather than flat -- chosen once the
plate browser needed to scale toward "all 50 US states" rather than 5
proof-of-concept templates: `_scan` walks the whole tree (`rglob`), so the
nesting is purely organizational for humans browsing the folder and never
affects lookup (`get_template`/`list_templates` are keyed by
`template_id`, not by path).

Two validation layers, deliberately kept separate:
  - `template.py`'s dataclasses validate their own shape (required keys,
    enum membership, a `CharSource`'s kind-specific field present) --
    raised from `from_dict()` itself.
  - `validate_template(template)` here validates cross-field structural
    rules that need the whole template in view (unique field ids, an
    `alignment` string that's actually one of `text_compose.ALIGNMENTS`).

A template referencing a fontpack/hand-traced glyph set/asset that doesn't
exist on disk yet is *not* rejected at load time -- only at render time
(Phase 4/5) -- so the browser can list a template whose glyph assets haven't
been built yet instead of hiding it. This is a deliberate choice, not an
oversight: spec's proof-of-concept templates are meant to prove the
architecture before every asset exists.
"""

from __future__ import annotations

import json
from pathlib import Path

from forza_writer.plates.template import PlateTemplate
from forza_writer.text_compose import ALIGNMENTS

DEFAULT_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "plate_templates"


class PlateTemplateError(ValueError):
    """A template failed to load or validate. `str(error)` always names the
    offending template file and, where applicable, the specific field --
    spec's "errors must explain what's wrong and which field" requirement,
    applied to templates themselves rather than only user input."""


def validate_template(template: PlateTemplate) -> None:
    """Raises `PlateTemplateError` on the first structural problem found.
    Does not check glyph/asset existence -- see module docstring."""
    seen_ids: set[str] = set()
    for f in template.fields:
        if f.field_id in seen_ids:
            raise PlateTemplateError(
                f"template {template.template_id!r}: duplicate field_id {f.field_id!r}"
            )
        seen_ids.add(f.field_id)
        if f.alignment not in ALIGNMENTS:
            raise PlateTemplateError(
                f"template {template.template_id!r}, field {f.field_id!r}: "
                f"alignment must be one of {ALIGNMENTS}, got {f.alignment!r}"
            )
    for d in template.decorations:
        if d.decoration_id in seen_ids:
            raise PlateTemplateError(
                f"template {template.template_id!r}: decoration_id {d.decoration_id!r} "
                f"collides with a field_id -- ids must be unique across fields and decorations"
            )
        seen_ids.add(d.decoration_id)


def load_template(path: Path) -> PlateTemplate:
    """Loads and validates one template file. Raises `PlateTemplateError`
    (never a bare `json.JSONDecodeError`/`KeyError`) so callers can surface
    a message that names the file, per spec's "malformed templates" handling."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PlateTemplateError(f"{path}: could not read/parse template: {exc}") from exc
    try:
        template = PlateTemplate.from_dict(data)
    except (KeyError, ValueError, TypeError) as exc:
        raise PlateTemplateError(f"{path}: invalid template: {exc}") from exc
    validate_template(template)
    return template


_template_cache: dict[str, PlateTemplate] = {}
_scanned_dirs: set[str] = set()


def _scan(directory: Path) -> None:
    key = str(directory.resolve())
    if key in _scanned_dirs:
        return
    if directory.is_dir():
        for path in sorted(directory.rglob("*.json")):
            try:
                template = load_template(path)
            except PlateTemplateError:
                continue  # malformed templates are skipped, not fatal to the whole registry
            _template_cache[template.template_id] = template
    _scanned_dirs.add(key)


def reload_templates() -> None:
    """Clears the registry cache so the next `list_templates()`/`get_template()`
    re-scans disk. Not called automatically -- template files are expected to
    be static for the lifetime of a GUI session, same assumption
    `charset.py`'s font-enumeration cache already makes."""
    _template_cache.clear()
    _scanned_dirs.clear()


def get_template(template_id: str, directory: Path = DEFAULT_TEMPLATES_DIR) -> PlateTemplate | None:
    _scan(directory)
    return _template_cache.get(template_id)


def list_templates(
    directory: Path = DEFAULT_TEMPLATES_DIR,
    country: str | None = None,
    plate_type: str | None = None,
    tags: tuple[str, ...] | None = None,
    search: str | None = None,
) -> list[PlateTemplate]:
    """All loaded templates matching every given filter (AND, not OR).
    `search` matches case-insensitively against `template_id`/`country`/
    `jurisdiction`/`era`/`plate_type` -- display-name matching needs the i18n
    layer (`display_name_key` is a lookup key, not display text) and is the
    GUI layer's job, not this module's.

    A directory scan + in-memory filter, cached after the first call per
    `directory` -- comfortably handles the "hundreds/thousands of standards"
    scale spec asks for without needing an index/database; revisit only if
    that's ever a measured bottleneck."""
    _scan(directory)
    results = list(_template_cache.values())
    if country is not None:
        results = [t for t in results if t.country == country]
    if plate_type is not None:
        results = [t for t in results if t.plate_type == plate_type]
    if tags:
        results = [t for t in results if set(tags).issubset(t.tags)]
    if search:
        needle = search.lower()
        results = [
            t for t in results
            if needle in t.template_id.lower()
            or needle in t.country.lower()
            or needle in (t.jurisdiction or "").lower()
            or needle in t.era.lower()
            or needle in t.plate_type.lower()
        ]
    return sorted(results, key=lambda t: t.template_id)
