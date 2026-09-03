"""English strings for tools/gen_plate_templates.py: each proof-of-concept
template's display_name_key, each of their fields' label_key, and each
field's FieldValidation.format_hint_key. One catalog entry per key the
template data itself references, so a template file's JSON can stay
locale-independent (a stable key, not literal English text) the same way
every other user-visible string in this app does.
"""

STRINGS: dict[str, str] = {
    'plates.template.us_ca_passenger_current': 'California Passenger, Current',
    'plates.template.gb_current_standard': 'Current Standard',
    'plates.template.jp_private_passenger_current': 'Private Passenger, Current',
    'plates.template.de_current_eu_band': 'Current (EU Band)',
    'plates.template.custom_blank': 'Custom / Vanity Plate',

    'plates.field.registration': 'Registration',
    'plates.field.jurisdiction_header': 'Header Text',
    'plates.field.region_kanji': 'Region (Kanji)',
    'plates.field.classification_number': 'Classification Number',
    'plates.field.hiragana': 'Hiragana',
    'plates.field.serial': 'Serial Number',

    'plates.validation.us_ca.format_hint': '1 digit, 3 letters, 3 digits (e.g. 1ABC234)',
    'plates.validation.gb.format_hint': '2 letters, 2 digits, space, 3 letters (e.g. AB12 CDE)',
    'plates.validation.jp.classification_hint': '3 digits (e.g. 530)',
    'plates.validation.jp.hiragana_hint': 'One hiragana character',
    'plates.validation.jp.serial_hint': '2 digits, hyphen, 2 digits (e.g. 12-34)',
    'plates.validation.de.format_hint': 'District letters, space, letters, space, digits (e.g. B MW 1234)',
}
