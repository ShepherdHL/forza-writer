"""Tests for forza_writer/plates/blank_library.py: save/load of pre-rendered
blank-plate files, one JSON per (country, template_id), keyed against a
signature of the template's own background/border/decorations so an edited
template can't silently serve a stale cached blank.

Every test passes `directory` explicitly rather than relying on
`DEFAULT_BLANKS_DIR` -- confirmed directly that monkeypatching the module
attribute does *not* affect a function whose parameter was bound to the
original value at def-time (an earlier version of this module had exactly
that bug, and a test relying on the monkeypatch silently wrote a real file
into the repo's own data/plate_blanks/ instead of a tmp_path). The dedicated
test below proves the fix; every other test avoids relying on the default
at all, matching how forza_writer/plates/renderer.py actually calls this
module (no directory argument, so it must resolve dynamically)."""

import dataclasses
import json

from forza_writer.plates import blank_library
from forza_writer.plates.group import GroupKind, PlateGroupNode
from forza_writer.plates.template import (
    AccuracyStatus,
    Decoration,
    DecorationKind,
    PlateTemplate,
    Provenance,
)


def _template(template_id="my-template", country="US", background=None, border=None, decorations=()):
    return PlateTemplate(
        template_id=template_id, display_name_key="k", country=country, jurisdiction=None,
        era="current", plate_type="passenger", width_mm=300.0, height_mm=150.0,
        accuracy_status=AccuracyStatus.FICTIONAL, provenance=Provenance(source_notes="test"),
        background=background or Decoration(decoration_id="bg", kind=DecorationKind.SOLID_FILL,
                                             x_mm=0.0, y_mm=0.0, color=(255, 255, 255, 255), editable=False),
        border=border, fields=(), decorations=decorations,
    )


def _sample_nodes():
    return [
        PlateGroupNode(node_id="bg", kind=GroupKind.BACKGROUND, shape_indices=(0,)),
        PlateGroupNode(node_id="border", kind=GroupKind.BORDER, shape_indices=(1,), children=[
            PlateGroupNode(node_id="border-detail", kind=GroupKind.CUSTOM, shape_indices=(2,)),
        ]),
    ]


def _sample_shapes():
    return [
        {"type": 1, "type_word": 1, "data": [0, 0, 1, 1, 0, 0, 0], "color": [255, 255, 255, 255], "mask": False},
        {"type": 1, "type_word": 1, "data": [1, 1, 1, 1, 0, 0, 0], "color": [0, 0, 0, 255], "mask": False},
        {"type": 1, "type_word": 1, "data": [2, 2, 1, 1, 0, 0, 0], "color": [10, 10, 10, 255], "mask": False},
    ]


def test_blank_path_mirrors_plate_templates_country_nesting(tmp_path):
    path = blank_library.blank_path("my-template", "US", directory=tmp_path)
    assert path == tmp_path / "US" / "my-template.json"


def test_save_then_load_round_trips_shapes_and_nodes(tmp_path):
    template = _template()
    shapes = _sample_shapes()
    nodes = _sample_nodes()
    blank_library.save_blank(template, shapes, nodes, warnings=["a warning"], directory=tmp_path)

    result = blank_library.load_blank(template, directory=tmp_path)
    assert result is not None
    loaded_shapes, loaded_nodes, loaded_warnings = result
    assert loaded_shapes == shapes
    assert loaded_warnings == ["a warning"]
    assert len(loaded_nodes) == 2
    assert loaded_nodes[1].children[0].node_id == "border-detail"


def test_load_blank_returns_none_when_no_file_exists(tmp_path):
    assert blank_library.load_blank(_template(), directory=tmp_path) is None


def test_load_blank_returns_none_on_corrupt_file(tmp_path):
    template = _template()
    path = blank_library.blank_path(template.template_id, template.country, directory=tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("{not valid json", encoding="utf-8")
    assert blank_library.load_blank(template, directory=tmp_path) is None


def test_load_blank_returns_none_when_template_id_does_not_match(tmp_path):
    """A file that happens to sit at the right path but was saved for a
    different template_id (e.g. a stale copy) must not be trusted."""
    template = _template(template_id="real-id")
    blank_library.save_blank(template, _sample_shapes(), [], [], directory=tmp_path)
    path = blank_library.blank_path("real-id", "US", directory=tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["template_id"] = "different-id"
    path.write_text(json.dumps(data), encoding="utf-8")

    assert blank_library.load_blank(template, directory=tmp_path) is None


def test_load_blank_returns_none_on_unrecognized_format(tmp_path):
    template = _template()
    path = blank_library.blank_path(template.template_id, template.country, directory=tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"format": "some_other_format", "template_id": template.template_id}),
                     encoding="utf-8")
    assert blank_library.load_blank(template, directory=tmp_path) is None


def test_save_blank_creates_country_subdirectory(tmp_path):
    template = _template(country="JP")
    blank_library.save_blank(template, _sample_shapes(), [], [], directory=tmp_path)
    assert (tmp_path / "JP" / "my-template.json").exists()


def test_default_directory_argument_resolves_dynamically_not_at_def_time(tmp_path, monkeypatch):
    """Regression test for the exact bug this module used to have: a bound
    default parameter (`directory: Path = DEFAULT_BLANKS_DIR`) captures the
    value at import time, so monkeypatching the module attribute afterward
    has no effect on calls that omit the argument. save_blank/load_blank
    must resolve DEFAULT_BLANKS_DIR fresh on every call instead."""
    monkeypatch.setattr(blank_library, "DEFAULT_BLANKS_DIR", tmp_path)
    template = _template()

    blank_library.save_blank(template, _sample_shapes(), [], [])  # no directory= given
    assert (tmp_path / "US" / "my-template.json").exists()

    result = blank_library.load_blank(template)  # no directory= given
    assert result is not None


# ---------------------------------------------------------------------------
# Staleness: decoration_signature
# ---------------------------------------------------------------------------

def test_decoration_signature_changes_when_background_color_changes():
    a = _template()
    b = dataclasses.replace(a, background=dataclasses.replace(a.background, color=(1, 2, 3, 255)))
    assert blank_library.decoration_signature(a) != blank_library.decoration_signature(b)


def test_decoration_signature_unaffected_by_unrelated_template_fields():
    """Editing a field's text/validation must not invalidate a background/
    border/decoration cache that never depended on fields at all."""
    a = _template()
    b = dataclasses.replace(a, era="1990s", tags=("vanity-available",))
    assert blank_library.decoration_signature(a) == blank_library.decoration_signature(b)


def test_load_blank_returns_none_when_template_decorations_have_changed_since_save(tmp_path):
    original = _template(border=Decoration(decoration_id="border", kind=DecorationKind.BORDER,
                                            x_mm=0.0, y_mm=0.0, color=(0, 0, 0, 255)))
    blank_library.save_blank(original, _sample_shapes(), _sample_nodes(), [], directory=tmp_path)
    assert blank_library.load_blank(original, directory=tmp_path) is not None  # sanity check: cache hits normally

    edited = dataclasses.replace(
        original, border=dataclasses.replace(original.border, color=(255, 0, 0, 255)))
    assert blank_library.load_blank(edited, directory=tmp_path) is None  # stale -- must not be trusted
