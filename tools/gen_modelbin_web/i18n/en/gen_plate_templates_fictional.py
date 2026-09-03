"""English strings for tools/gen_plate_templates_fictional.py: each fictional
game-plate template's display_name_key, each of their fields' label_key, and
each field's FieldValidation.format_hint_key. See
gen_plate_templates.py (in this same directory) for why templates
reference keys here rather than literal English text.
"""

STRINGS: dict[str, str] = {
    'plates.template.gta_sa_passenger_fictional': 'San Andreas Passenger (GTA V)',
    'plates.template.gta_sa_black_fictional': 'San Andreas, Black (GTA V)',
    'plates.template.gta_sa_blue_fictional': 'San Andreas, Blue (GTA V)',
    'plates.template.gta_sa_red_fictional': 'San Andreas, Striped (GTA V)',
    'plates.template.gta_sa_exempt_fictional': 'SA Exempt / Government (GTA V)',
    'plates.template.gta_libertycity_bw_fictional': 'Liberty City, Blue & White (GTA V)',
    'plates.template.gta_libertycity_by_fictional': 'Liberty City, Blue & Gold (GTA V)',
    'plates.template.gta_libertycity_skyline_fictional': 'Liberty City, Skyline (GTA V)',
    'plates.template.gta_vicecity_fictional': 'Vice City, Skyline (GTA V)',
    'plates.template.gta_lossantos_shrimps_fictional': 'Los Santos Shrimps (GTA V)',
    'plates.template.gta_sprunk_fictional': 'Sprunk (GTA V)',
    'plates.template.gta_patriot_fictional': 'Patriot Beer (GTA V)',
    'plates.template.nfs_fairhaven_passenger_fictional': 'Fairhaven Passenger (NFS: Most Wanted)',
    'plates.template.nfs_rockport_passenger_fictional': 'Rockport Passenger (NFS: Most Wanted)',
    'plates.template.nfs_palmont_passenger_fictional': 'Palmont Passenger (NFS: Carbon)',
    'plates.template.nfs_tricitybay_passenger_fictional': 'Tri City Bay Passenger (NFS)',
    'plates.template.nfs_seacrestcounty_police_fictional': 'Seacrest County Police (NFS: Undercover)',
    'plates.template.sr_stilwater_passenger_fictional': 'Stilwater Passenger (Saints Row 2)',
    'plates.template.sr_steelport_passenger_fictional': 'Steelport Passenger (Saints Row: The Third)',
    'plates.template.halo_newmombasa_passenger_fictional': 'New Mombasa Passenger (Halo 3: ODST)',
    'plates.template.halo_reach_barcode_fictional': 'Reach, Barcode Variant (Halo: Reach)',
    'plates.template.halo_reach_standard_fictional': 'Reach, Standard Variant (Halo: Reach)',
    'plates.template.cp2077_nightcity_passenger_fictional': 'Night City Passenger (Cyberpunk 2077)',
    'plates.template.medge_city_transport_fictional': "Transport Plate (Mirror's Edge)",
    'plates.template.medge_city_passenger_fictional': "Passenger Plate (Mirror's Edge)",
    'plates.template.dl_harran_passenger_fictional': 'Harran Passenger (Dying Light)',
    'plates.template.phasmophobia_ghd_van_fictional': 'Ghost Huntin\' Distribution Van (Phasmophobia)',

    'plates.field.city_banner': 'City / Region Banner',
    'plates.field.police_caption': 'Police Caption',
    'plates.field.tagline': 'Tagline',
    'plates.field.steelport_tag': 'Steelport Tag',
    'plates.field.post_bios': 'Micro-Print (Easter Egg)',
    'plates.field.barcode': 'Barcode',
    'plates.field.spartan_bios': 'Micro-Print (Easter Egg)',
    'plates.field.csg_mark': 'CSG Mark',
    'plates.field.glitch_band': 'Glitch Band',
    'plates.field.label': 'Label',
    'plates.field.month_sticker': 'Month Sticker',
    'plates.field.team_wordmark': 'Team Wordmark',

    'plates.validation.gta_sa.format_hint': '2 digits, 3 letters, 3 digits (e.g. 12ABC345)',
    'plates.validation.halo_nm.format_hint': "'K', 2 letters, space, 3 digits, 1 letter (e.g. KBL 117J)",
    'plates.validation.halo_reach.format_hint': '1 letter, 4 digits, 2 letters, 1 digit (e.g. T2345GB1)',
    'plates.validation.halo_reach_standard.format_hint': "'M', middle dot, 6 digits (e.g. M·100627)",
    'plates.validation.cp2077.format_hint': "'NC', space, 2 digits (e.g. NC 77)",
}
