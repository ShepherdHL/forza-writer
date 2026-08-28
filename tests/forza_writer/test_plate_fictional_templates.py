"""Integration tests for the shipped fictional game-plate templates
(data/plate_templates/{GTA,NFS,SR,HALO,CP2077,MEDGE}/*.json, built by
tools/gen_plate_templates_fictional.py) -- using the actual shipped files,
mirroring test_plate_poc_templates.py's approach for the real-world set."""

import pytest

from forza_writer.plates.instance import PlateInstance
from forza_writer.plates.loader import list_templates, reload_templates
from forza_writer.plates.renderer import render_plate
from forza_writer.plates.template import AccuracyStatus
from forza_writer.plates.validation import is_valid_for_generation

EXPECTED_TEMPLATE_IDS = {
    "gta-sa-passenger-fictional",
    "nfs-fairhaven-passenger-fictional",
    "nfs-rockport-passenger-fictional",
    "nfs-palmont-passenger-fictional",
    "nfs-tricitybay-passenger-fictional",
    "nfs-seacrestcounty-police-fictional",
    "sr-stilwater-passenger-fictional",
    "sr-steelport-passenger-fictional",
    "halo-newmombasa-passenger-fictional",
    "halo-reach-barcode-fictional",
    "halo-reach-standard-fictional",
    "cp2077-nightcity-passenger-fictional",
    "medge-city-transport-fictional",
    "medge-city-passenger-fictional",
    "dl-harran-passenger-fictional",
    "phasmophobia-ghd-van-fictional",
}


@pytest.fixture(autouse=True)
def _reload():
    reload_templates()
    yield
    reload_templates()


def test_all_fictional_templates_are_present():
    ids = {t.template_id for t in list_templates()}
    assert EXPECTED_TEMPLATE_IDS.issubset(ids)


@pytest.mark.parametrize("template_id", sorted(EXPECTED_TEMPLATE_IDS))
def test_fictional_template_renders_default_text_without_warnings(template_id):
    template = next(t for t in list_templates() if t.template_id == template_id)
    instance = PlateInstance(template_id=template_id, mode="authentic", field_values={})
    shapes, root, warnings = render_plate(template, instance)
    assert warnings == [], f"{template_id} produced warnings: {warnings}"
    assert len(shapes) > 0
    assert root.kind.value == "plate"


@pytest.mark.parametrize("template_id", sorted(EXPECTED_TEMPLATE_IDS))
def test_fictional_template_default_text_passes_its_own_validation(template_id):
    template = next(t for t in list_templates() if t.template_id == template_id)
    instance = PlateInstance(template_id=template_id, mode="authentic", field_values={})
    assert is_valid_for_generation(template, instance) is True


def test_every_fictional_template_is_tagged_fictional_with_honest_provenance():
    """None of these is a real government standard -- every one must use
    AccuracyStatus.FICTIONAL, and every one's provenance must actually say
    what it's grounded in (never an empty/placeholder source_notes)."""
    for template in list_templates():
        if template.template_id not in EXPECTED_TEMPLATE_IDS:
            continue
        assert template.accuracy_status is AccuracyStatus.FICTIONAL
        assert template.provenance.source_notes.strip() != ""


def test_every_fictional_template_char_source_points_at_an_existing_font_file():
    """Same guarantee as the real-world POC set: no field may reference a
    font file that doesn't actually exist on disk."""
    from forza_writer.plates.glyph_resolve import FONTS_DIR

    for template in list_templates():
        if template.template_id not in EXPECTED_TEMPLATE_IDS:
            continue
        for field in template.fields:
            font_path = FONTS_DIR / field.char_source.font_file
            assert font_path.exists(), f"{template.template_id}.{field.field_id}: missing {font_path}"


def test_fictional_templates_are_nested_under_their_own_game_country_codes():
    by_id = {t.template_id: t for t in list_templates()}
    expected_country = {
        "gta-sa-passenger-fictional": "GTA",
        "nfs-fairhaven-passenger-fictional": "NFS",
        "sr-stilwater-passenger-fictional": "SR",
        "sr-steelport-passenger-fictional": "SR",
        "halo-newmombasa-passenger-fictional": "HALO",
        "halo-reach-barcode-fictional": "HALO",
        "halo-reach-standard-fictional": "HALO",
        "cp2077-nightcity-passenger-fictional": "CP2077",
        "medge-city-transport-fictional": "MEDGE",
        "medge-city-passenger-fictional": "MEDGE",
        "dl-harran-passenger-fictional": "DL",
        "phasmophobia-ghd-van-fictional": "PHAS",
    }
    for template_id, country in expected_country.items():
        assert by_id[template_id].country == country


def test_halo_reach_variants_are_two_distinct_templates_under_the_same_jurisdiction():
    by_id = {t.template_id: t for t in list_templates()}
    barcode = by_id["halo-reach-barcode-fictional"]
    standard = by_id["halo-reach-standard-fictional"]
    assert barcode.jurisdiction == standard.jurisdiction == "Reach"
    assert barcode.template_id != standard.template_id


def test_gta_registration_rejects_wrong_format():
    from forza_writer.plates.validation import validate_instance
    template = next(t for t in list_templates() if t.template_id == "gta-sa-passenger-fictional")
    instance = PlateInstance(template_id=template.template_id, mode="authentic",
                              field_values={"registration": "ABC1234"})
    errors = validate_instance(template, instance)
    assert any(e.field_id == "registration" for e in errors)
