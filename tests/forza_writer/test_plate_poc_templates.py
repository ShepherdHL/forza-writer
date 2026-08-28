"""Integration tests for the five shipped proof-of-concept plate templates
(data/plate_templates/*.json, built by tools/gen_plate_templates.py) --
using the actual shipped files, not synthetic fixtures, per spec's
requirement that the proof-of-concept templates themselves are proven to
work, not just the generic machinery they exercise."""

import pytest

from forza_writer.plates.instance import PlateInstance
from forza_writer.plates.loader import list_templates, reload_templates
from forza_writer.plates.renderer import render_plate
from forza_writer.plates.validation import is_valid_for_generation

EXPECTED_TEMPLATE_IDS = {
    "us-ca-passenger-current",
    "gb-current-standard",
    "jp-private-passenger-current",
    "de-current-eu-band",
    "custom-blank",
}


@pytest.fixture(autouse=True)
def _reload():
    reload_templates()
    yield
    reload_templates()


def test_all_five_poc_templates_are_present():
    ids = {t.template_id for t in list_templates()}
    assert EXPECTED_TEMPLATE_IDS.issubset(ids)


@pytest.mark.parametrize("template_id", sorted(EXPECTED_TEMPLATE_IDS))
def test_poc_template_renders_default_text_without_warnings(template_id):
    template = next(t for t in list_templates() if t.template_id == template_id)
    instance = PlateInstance(template_id=template_id, mode="authentic", field_values={})
    shapes, root, warnings = render_plate(template, instance)
    assert warnings == [], f"{template_id} produced warnings: {warnings}"
    assert len(shapes) > 0
    assert root.kind.value == "plate"


@pytest.mark.parametrize("template_id", sorted(EXPECTED_TEMPLATE_IDS))
def test_poc_template_default_text_passes_its_own_validation(template_id):
    """Every default_text is meant to be a valid example of its own
    template's format -- if this fails, either the template's default text
    or its own validation rule disagrees with itself."""
    template = next(t for t in list_templates() if t.template_id == template_id)
    instance = PlateInstance(template_id=template_id, mode="authentic", field_values={})
    assert is_valid_for_generation(template, instance) is True


def test_every_poc_template_has_honest_accuracy_metadata():
    for template in list_templates():
        if template.template_id not in EXPECTED_TEMPLATE_IDS:
            continue
        assert template.provenance.source_notes.strip() != ""
        assert template.accuracy_status is not None


def test_us_ca_rejects_ambiguous_letter_in_first_position():
    from forza_writer.plates.validation import validate_instance
    template = next(t for t in list_templates() if t.template_id == "us-ca-passenger-current")
    instance = PlateInstance(template_id=template.template_id, mode="authentic",
                              field_values={"registration": "1IBC234"})
    errors = validate_instance(template, instance)
    assert any(e.field_id == "registration" for e in errors)


def test_jp_four_fields_are_independently_addressable():
    template = next(t for t in list_templates() if t.template_id == "jp-private-passenger-current")
    field_ids = {f.field_id for f in template.fields}
    assert field_ids == {"region_kanji", "classification_number", "hiragana", "serial"}
    # Each field references its own character source -- the architectural
    # stress test spec section 6 asks for: kanji/hiragana must point at a
    # CJK font's metrics while the numeric fields point at a Latin font's --
    # different metrics per field, via the same underlying mechanism.
    font_files = {f.field_id: f.char_source.font_file for f in template.fields}
    assert len(set(font_files.values())) >= 2


def test_gb_and_de_registration_fields_use_a_placeholder_font_not_a_bundled_real_plate_font():
    """Neither UK's 'Charles Wright' nor Germany's FE-Schrift is bundled
    (unconfirmed license) -- both templates must be using the shared
    placeholder Latin font's metrics, not a real plate font, and their own
    Provenance must say so."""
    for template_id in ("gb-current-standard", "de-current-eu-band"):
        template = next(t for t in list_templates() if t.template_id == template_id)
        registration = template.field_by_id("registration")
        assert registration.char_source.font_file == "LiberationSans-Regular.ttf"
        notes = template.provenance.source_notes
        assert "bundled" in notes or "not confirmed" in notes or "no confirmed" in notes


def test_every_poc_template_char_source_points_at_an_existing_font_file():
    """No field may reference a font file that doesn't actually exist on
    disk -- every character's metrics on a shipped template must come from
    something real, not something that would silently resolve to nothing
    at render time."""
    from forza_writer.plates.glyph_resolve import FONTS_DIR

    for template in list_templates():
        if template.template_id not in EXPECTED_TEMPLATE_IDS:
            continue
        for field in template.fields:
            font_path = FONTS_DIR / field.char_source.font_file
            assert font_path.exists(), f"{template.template_id}.{field.field_id}: missing {font_path}"
