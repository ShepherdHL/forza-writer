"""Tests for forza_writer/plates/loader.py: template loading, structural
validation, and the filterable registry the plate browser queries."""

import dataclasses
import json

import pytest

from forza_writer.plates.loader import (
    PlateTemplateError,
    get_template,
    list_templates,
    load_template,
    reload_templates,
    validate_template,
)
from forza_writer.plates.template import (
    AccuracyStatus,
    CharSource,
    Decoration,
    DecorationKind,
    FieldRole,
    PlateField,
    PlateTemplate,
    Provenance,
)


def _template(template_id, country="US", plate_type="passenger", tags=(), alignment="center", field_id="registration"):
    return PlateTemplate(
        template_id=template_id,
        display_name_key=f"plates.template.{template_id}",
        country=country,
        jurisdiction=None,
        era="current",
        plate_type=plate_type,
        width_mm=300.0,
        height_mm=150.0,
        accuracy_status=AccuracyStatus.FICTIONAL,
        provenance=Provenance(source_notes="test fixture"),
        background=Decoration(decoration_id="bg", kind=DecorationKind.SOLID_FILL, x_mm=0.0, y_mm=0.0,
                               color=(255, 255, 255, 255), editable=False),
        border=None,
        fields=(
            PlateField(
                field_id=field_id, label_key="plates.field.registration", role=FieldRole.REGISTRATION,
                x_mm=10.0, y_mm=10.0, width_mm=280.0, height_mm=100.0, alignment=alignment,
                char_source=CharSource(font_file="LiberationSans-Regular.ttf"),
            ),
        ),
        tags=tags,
    )


@pytest.fixture(autouse=True)
def _clear_cache():
    reload_templates()
    yield
    reload_templates()


def _write(directory, template):
    (directory / f"{template.template_id}.json").write_text(
        json.dumps(template.to_dict()), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# load_template / validate_template
# ---------------------------------------------------------------------------

def test_load_template_round_trips_a_valid_file(tmp_path):
    _write(tmp_path, _template("us-ca-passenger-current"))
    loaded = load_template(tmp_path / "us-ca-passenger-current.json")
    assert loaded.template_id == "us-ca-passenger-current"


def test_load_template_raises_on_unparseable_json(tmp_path):
    bad = tmp_path / "broken.json"
    bad.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(PlateTemplateError, match="could not read/parse"):
        load_template(bad)


def test_load_template_raises_on_missing_required_key(tmp_path):
    data = _template("us-ca-passenger-current").to_dict()
    del data["width_mm"]
    bad = tmp_path / "missing_field.json"
    bad.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(PlateTemplateError, match="invalid template"):
        load_template(bad)


def test_validate_template_rejects_duplicate_field_id():
    template = _template("dupe", field_id="registration")
    template = dataclasses.replace(template, fields=template.fields + (template.fields[0],))
    with pytest.raises(PlateTemplateError, match="duplicate field_id"):
        validate_template(template)


def test_validate_template_rejects_invalid_alignment():
    template = _template("bad-align", alignment="diagonal")
    with pytest.raises(PlateTemplateError, match="alignment must be one of"):
        validate_template(template)


# ---------------------------------------------------------------------------
# Registry: list_templates / get_template, malformed-file resilience
# ---------------------------------------------------------------------------

def test_list_templates_filters_by_country_and_plate_type(tmp_path):
    _write(tmp_path, _template("us-ca-passenger-current", country="US", plate_type="passenger"))
    _write(tmp_path, _template("gb-current-standard", country="GB", plate_type="passenger"))
    _write(tmp_path, _template("us-ca-motorcycle-current", country="US", plate_type="motorcycle"))

    us_plates = list_templates(directory=tmp_path, country="US")
    assert {t.template_id for t in us_plates} == {"us-ca-passenger-current", "us-ca-motorcycle-current"}

    us_passenger = list_templates(directory=tmp_path, country="US", plate_type="passenger")
    assert [t.template_id for t in us_passenger] == ["us-ca-passenger-current"]


def test_list_templates_filters_by_tags_and_search(tmp_path):
    _write(tmp_path, _template("gb-current-standard", country="GB", tags=("vanity-available",)))
    _write(tmp_path, _template("de-current-eu-band", country="DE", tags=()))

    tagged = list_templates(directory=tmp_path, tags=("vanity-available",))
    assert [t.template_id for t in tagged] == ["gb-current-standard"]

    searched = list_templates(directory=tmp_path, search="DE-CURRENT")
    assert [t.template_id for t in searched] == ["de-current-eu-band"]


def test_list_templates_is_sorted_deterministically(tmp_path):
    _write(tmp_path, _template("zz-template"))
    _write(tmp_path, _template("aa-template"))
    ids = [t.template_id for t in list_templates(directory=tmp_path)]
    assert ids == sorted(ids)


def test_registry_skips_malformed_templates_without_crashing(tmp_path):
    _write(tmp_path, _template("us-ca-passenger-current"))
    (tmp_path / "broken.json").write_text("{not valid json", encoding="utf-8")

    results = list_templates(directory=tmp_path)
    assert [t.template_id for t in results] == ["us-ca-passenger-current"]


def test_get_template_returns_none_for_unknown_id(tmp_path):
    _write(tmp_path, _template("us-ca-passenger-current"))
    assert get_template("nonexistent", directory=tmp_path) is None
    assert get_template("us-ca-passenger-current", directory=tmp_path) is not None


def test_registry_cache_does_not_pick_up_new_files_until_reload(tmp_path):
    _write(tmp_path, _template("us-ca-passenger-current"))
    assert len(list_templates(directory=tmp_path)) == 1

    _write(tmp_path, _template("gb-current-standard"))
    assert len(list_templates(directory=tmp_path)) == 1  # still cached

    reload_templates()
    assert len(list_templates(directory=tmp_path)) == 2
