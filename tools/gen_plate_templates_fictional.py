"""
Builds a set of fictional license-plate templates modeled on plates seen in
nine video-game settings: Grand Theft Auto V (San Andreas), Need for Speed
(Fairhaven, Rockport, Palmont, Seacrest County, Tri City Bay), Saints Row
(Stilwater, Steelport), Halo (New Mombasa, Reach -- two variants),
Cyberpunk 2077 (Night City), Mirror's Edge (transport and passenger
variants), Dying Light (Harran), and Phasmophobia (the player team's van,
the game's one and only plate) -- into data/plate_templates/<country>/
*.json alongside the real-world proof-of-concept set
(tools/gen_plate_templates.py).

None of these are `REFERENCE_BASED` -- every template here uses
`AccuracyStatus.FICTIONAL`, since none is a real government standard. That
does not mean "invented freely," though: each template's own
`Provenance.source_notes` says exactly what it's grounded in (a developer
quote, an in-game screenshot supplied by a Forza Writer user, a wiki
gallery of player-made plates) and exactly what's a best-guess
approximation (a color read off a low-resolution screenshot, a font
standing in for one that doesn't exist as a redistributable file, an
Easter-egg micro-print transcribed from a blurry shot). Treat these as fan
approximations for a hobby tool, not as extracted or reproduced game
assets -- no image, texture, or font file from any of these games was
copied, downloaded, or scraped to build them. See each template's own
Provenance for its specific sources.

Typography: same placeholder-box policy as tools/gen_plate_templates.py --
every field only ever renders a plain box per character, sized/spaced from
the bundled, freely-licensed LiberationSans-Regular.ttf's real metrics,
never a font specific to any of these games and never letterform geometry.
None of these games has a confirmed freely redistributable digitization of
its actual plate font (several use serif, script, or stencil styles no
bundled font here reproduces) -- real artwork for any of these is the
user's to supply and fine-tune in KFPS. A repeated "|" run stands in for
Halo: Reach's barcode-style plate (the schema has no barcode-symbology
decoration kind); it lays out through the same metrics-based pipeline as
everything else rather than needing a new renderer path.

Usage:
    python tools/gen_plate_templates_fictional.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from forza_writer.plates.template import (  # noqa: E402
    AccuracyStatus,
    CharSource,
    Decoration,
    DecorationKind,
    FieldRole,
    FieldValidation,
    PlateField,
    PlateTemplate,
    Provenance,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "data" / "plate_templates"

_LATIN = CharSource(font_file="LiberationSans-Regular.ttf")

WHITE = (255, 255, 255, 255)
BLACK = (20, 20, 20, 255)
PLATE_W, PLATE_H = 304.8, 152.4  # US-style proportions -- every reference image is roughly this shape

# Mirror's Edge (2008) and Dying Light (2015) specifically, not the shared
# PLATE_W/PLATE_H above: Mirror's Edge's developer (DICE) is Stockholm-
# based, and both games' plates read as European/Nordic in proportion, not
# American, in the screenshots these templates were built from. 520x110mm
# is the real EU standard plate size (same figure de-current-eu-band/
# gb-current-standard already use), used here as the closer real-world
# size reference rather than the US-shaped default every other fictional
# template in this file uses.
EU_STYLE_W, EU_STYLE_H = 520.0, 110.0

SCREENSHOT_NOTE = (
    "Reference for this template's layout and text came from screenshots the Forza Writer user supplied "
    "directly (in-game/in-editor captures), not from any file, image, or asset extracted or downloaded from "
    "the game itself or an official tool."
)


def gta_san_andreas() -> PlateTemplate:
    return PlateTemplate(
        template_id="gta-sa-passenger-fictional",
        display_name_key="plates.template.gta_sa_passenger_fictional",
        country="GTA", jurisdiction="San Andreas", era="fictional", plate_type="passenger",
        width_mm=PLATE_W, height_mm=PLATE_H,
        accuracy_status=AccuracyStatus.FICTIONAL,
        provenance=Provenance(
            source_notes=(
                "Grand Theft Auto V ships five stock San Andreas plate variants (yellow-on-black, "
                "yellow-on-blue, a striped white variant, a plain white/blue variant, and a white "
                "government 'SA EXEMPT' plate) -- this template models the plain white-background/"
                "blue-text variant, the one described as most common. 'SAN ANDREAS' as the header text and "
                "the 2-digit/3-letter/3-digit registration format (e.g. 12ABC345) are corroborated across "
                "two independent wikis. No slogan/motto text was found on the plate itself in either "
                "source -- treat any claim of one as unconfirmed. The text color (a dark blue, "
                "approximately #0F2352) comes from a single wiki's datamined-looking hex values, not "
                "independently corroborated. The font is named 'Penitentiary Gothic Regular' by one wiki "
                "only; not bundled here either way -- this template's text uses the same placeholder Latin "
                "fontpack as every real-world template."
            ),
            reference_urls=(
                "https://www.grandtheftwiki.com/Vehicle_License_Plates",
                "https://gta.wiki/w/License_Plates",
                "https://gtaforums.com/topic/573705-san-andreas-license-plates/",
            ),
        ),
        background=Decoration(decoration_id="bg", kind=DecorationKind.SOLID_FILL, x_mm=0.0, y_mm=0.0,
                               color=WHITE, editable=False),
        border=None,
        fields=(
            PlateField(
                field_id="jurisdiction_header", label_key="plates.field.jurisdiction_header",
                role=FieldRole.JURISDICTION_TEXT,
                x_mm=20.0, y_mm=10.0, width_mm=264.8, height_mm=26.0, alignment="center",
                char_source=_LATIN, char_scale=0.55, tracking=2.0,
                default_text="SAN ANDREAS", color=(15, 35, 82, 255),
                editable_in_authentic_mode=False,
            ),
            PlateField(
                field_id="registration", label_key="plates.field.registration", role=FieldRole.REGISTRATION,
                x_mm=20.0, y_mm=48.0, width_mm=264.8, height_mm=70.0, alignment="center",
                char_source=_LATIN, char_scale=0.51, tracking=4.0,
                default_text="12ABC345", color=(15, 35, 82, 255),
                validation=FieldValidation(
                    format_hint_key="plates.validation.gta_sa.format_hint",
                    min_length=8, max_length=8,
                    allowed_pattern=r"[0-9]{2}[A-Z]{3}[0-9]{3}",
                ),
            ),
        ),
        tags=("vanity-available", "fictional-game"),
    )


def _nfs_city(template_id: str, jurisdiction: str, display_name_key: str, banner_text_key: str,
              banner_text: str, plate_text_key: str, default_text: str, banner_color, sticker_color,
              plate_type="passenger", extra_fields=(), extra_decorations=()) -> PlateTemplate:
    return PlateTemplate(
        template_id=template_id,
        display_name_key=display_name_key,
        country="NFS", jurisdiction=jurisdiction, era="fictional", plate_type=plate_type,
        width_mm=PLATE_W, height_mm=PLATE_H,
        accuracy_status=AccuracyStatus.FICTIONAL,
        provenance=Provenance(
            source_notes=(
                f"Modeled on a shared plate template used across the Need for Speed series: an italic city/"
                f"region banner across the top, large bold plate text, and a bottom colored sticker strip "
                f"with a month-year stamp. {SCREENSHOT_NOTE} The recurring registration text 'ND4SPD' (read "
                f"as 'need for speed') is a franchise in-joke that shows up across several games' example "
                f"plates, not something unique to this city. Banner/sticker colors are approximated by eye "
                f"from the supplied screenshots (compressed, low-resolution source images), not "
                f"color-picked from an authoritative source. The series also draws a small corner build "
                f"number and rotated vertical 'NFS' side text on most of these plates -- both omitted here, "
                f"since PlateField has no rotation support yet; this template only reproduces the "
                f"non-rotated elements. No italic/script font is bundled, so the banner's italic look is "
                f"not reproduced -- same placeholder Latin fontpack as every field on every template."
            ),
            reference_urls=("https://nfs.fandom.com/wiki/Licence_Plate",),
        ),
        background=Decoration(decoration_id="bg", kind=DecorationKind.SOLID_FILL, x_mm=0.0, y_mm=0.0,
                               color=(248, 246, 238, 255), editable=False),
        border=Decoration(decoration_id="border", kind=DecorationKind.BORDER, x_mm=0.0, y_mm=0.0,
                           color=(180, 175, 160, 255)),
        fields=(
            PlateField(
                field_id="city_banner", label_key="plates.field.city_banner", role=FieldRole.JURISDICTION_TEXT,
                x_mm=15.0, y_mm=8.0, width_mm=274.8, height_mm=26.0, alignment="center",
                char_source=_LATIN, char_scale=0.5, tracking=1.0,
                default_text=banner_text, color=banner_color,
                editable_in_authentic_mode=False,
            ),
            PlateField(
                field_id="registration", label_key="plates.field.registration", role=FieldRole.REGISTRATION,
                x_mm=15.0, y_mm=42.0, width_mm=274.8, height_mm=64.0, alignment="center",
                char_source=_LATIN, char_scale=0.54, tracking=3.0,
                default_text=default_text, color=(25, 25, 30, 255),
                editable_in_authentic_mode=True,
            ),
            *extra_fields,
        ),
        decorations=(
            Decoration(decoration_id="date_sticker", kind=DecorationKind.STICKER,
                       x_mm=104.0, y_mm=118.0, width_mm=96.8, height_mm=24.0, color=sticker_color),
            *extra_decorations,
        ),
        tags=("vanity-available", "fictional-game"),
    )


def nfs_fairhaven() -> PlateTemplate:
    return _nfs_city(
        "nfs-fairhaven-passenger-fictional", "Fairhaven", "plates.template.nfs_fairhaven_passenger_fictional",
        "plates.field.city_banner", "Fairhaven", "plates.field.registration", "NEED4SPD",
        banner_color=(20, 40, 95, 255), sticker_color=(70, 110, 190, 255),
    )


def nfs_rockport() -> PlateTemplate:
    return _nfs_city(
        "nfs-rockport-passenger-fictional", "Rockport", "plates.template.nfs_rockport_passenger_fictional",
        "plates.field.city_banner", "City Of Rockport", "plates.field.registration", "NFSMW",
        banner_color=(95, 40, 35, 255), sticker_color=(70, 110, 190, 255),
    )


def nfs_palmont() -> PlateTemplate:
    return _nfs_city(
        "nfs-palmont-passenger-fictional", "Palmont", "plates.template.nfs_palmont_passenger_fictional",
        "plates.field.city_banner", "City Of Palmont", "plates.field.registration", "CARBON",
        banner_color=(95, 40, 35, 255), sticker_color=(70, 110, 190, 255),
    )


def nfs_tri_city_bay() -> PlateTemplate:
    return _nfs_city(
        "nfs-tricitybay-passenger-fictional", "Tri City Bay", "plates.template.nfs_tricitybay_passenger_fictional",
        "plates.field.city_banner", "Tri City Bay", "plates.field.registration", "ND 4 SPD",
        banner_color=(120, 35, 40, 255), sticker_color=(70, 110, 190, 255),
    )


def nfs_seacrest_county() -> PlateTemplate:
    return _nfs_city(
        "nfs-seacrestcounty-police-fictional", "Seacrest County",
        "plates.template.nfs_seacrestcounty_police_fictional",
        "plates.field.city_banner", "Seacrest County", "plates.field.registration", "ND4SPD",
        banner_color=(15, 35, 90, 255), sticker_color=(70, 110, 190, 255), plate_type="police",
        extra_fields=(
            PlateField(
                field_id="police_caption", label_key="plates.field.police_caption", role=FieldRole.DECORATIVE_TEXT,
                x_mm=15.0, y_mm=107.0, width_mm=274.8, height_mm=10.0, alignment="center",
                char_source=_LATIN, char_scale=0.32, tracking=2.0,
                default_text="POLICE", color=(15, 35, 90, 255),
                editable_in_authentic_mode=False,
            ),
        ),
        extra_decorations=(
            Decoration(decoration_id="badge", kind=DecorationKind.SEAL,
                       x_mm=12.0, y_mm=45.0, width_mm=26.0, height_mm=26.0, color=(190, 160, 60, 255)),
        ),
    )


def sr_stilwater() -> PlateTemplate:
    return PlateTemplate(
        template_id="sr-stilwater-passenger-fictional",
        display_name_key="plates.template.sr_stilwater_passenger_fictional",
        country="SR", jurisdiction="Stilwater", era="fictional", plate_type="passenger",
        width_mm=PLATE_W, height_mm=PLATE_H,
        accuracy_status=AccuracyStatus.FICTIONAL,
        provenance=Provenance(
            source_notes=(
                "Modeled directly on a clean reference plate image the Forza Writer user supplied (Saints "
                "Row 2's Stilwater plate): 'STILWATER' as a green header banner, a blue divider beneath it, "
                "a yellow corner sticker, a bold blue two-group registration number (e.g. '180 174', no "
                "letter prefix on the plate itself -- an earlier web-research pass had guessed an 'SW' "
                "prefix from vehicle-naming conventions, which this reference image does not support), and "
                "'America's Hometown' as a gray tagline along the bottom. The real plate's divider is a "
                "wavy double line and it has a faint city-skyline watermark behind the registration number; "
                "both are simplified here -- the divider as a plain SEPARATOR bar and the skyline watermark "
                "omitted entirely, since the schema has no raster-image/watermark decoration kind. No "
                "script/serif font is bundled, so the header's serif look and the tagline's italic look "
                "aren't reproduced -- same placeholder Latin fontpack as every field on every template."
            ),
        ),
        background=Decoration(decoration_id="bg", kind=DecorationKind.SOLID_FILL, x_mm=0.0, y_mm=0.0,
                               color=WHITE, editable=False),
        border=None,
        fields=(
            PlateField(
                field_id="city_banner", label_key="plates.field.city_banner", role=FieldRole.JURISDICTION_TEXT,
                x_mm=15.0, y_mm=6.0, width_mm=250.0, height_mm=24.0, alignment="center",
                char_source=_LATIN, char_scale=0.5, tracking=2.0,
                default_text="STILWATER", color=(45, 105, 75, 255),
                editable_in_authentic_mode=False,
            ),
            PlateField(
                field_id="registration", label_key="plates.field.registration", role=FieldRole.REGISTRATION,
                x_mm=15.0, y_mm=44.0, width_mm=274.8, height_mm=62.0, alignment="center",
                char_source=_LATIN, char_scale=0.62, tracking=3.0,
                default_text="180 174", color=(35, 55, 150, 255),
                editable_in_authentic_mode=True,
            ),
            PlateField(
                field_id="tagline", label_key="plates.field.tagline", role=FieldRole.DECORATIVE_TEXT,
                x_mm=15.0, y_mm=124.0, width_mm=274.8, height_mm=16.0, alignment="center",
                char_source=_LATIN, char_scale=0.4, tracking=1.0,
                default_text="America's Hometown", color=(110, 108, 98, 255),
                editable_in_authentic_mode=False,
            ),
        ),
        decorations=(
            Decoration(decoration_id="divider", kind=DecorationKind.SEPARATOR,
                       x_mm=15.0, y_mm=32.0, width_mm=250.0, height_mm=3.0, color=(60, 100, 160, 255)),
            Decoration(decoration_id="sticker", kind=DecorationKind.STICKER,
                       x_mm=270.0, y_mm=6.0, width_mm=22.0, height_mm=18.0, color=(220, 190, 40, 255)),
        ),
        tags=("vanity-available", "fictional-game"),
    )


def sr_steelport() -> PlateTemplate:
    return PlateTemplate(
        template_id="sr-steelport-passenger-fictional",
        display_name_key="plates.template.sr_steelport_passenger_fictional",
        country="SR", jurisdiction="Steelport", era="fictional", plate_type="passenger",
        width_mm=PLATE_W, height_mm=PLATE_H,
        accuracy_status=AccuracyStatus.FICTIONAL,
        provenance=Provenance(
            source_notes=(
                f"{SCREENSHOT_NOTE} Two Saints Row: The Third vehicles' plates both read 'SR3' followed by "
                f"four digits (e.g. 'SR3 5221', 'SR3 9686') -- that prefix/format is a direct transcription "
                f"from the supplied screenshots. Each screenshot also shows a small script-style sticker or "
                f"stripe near the plate that a Saints Row wiki page describes as reading 'Steelport' -- "
                f"included here as a low-confidence best guess (field 'steelport_tag' below), since the "
                f"actual text is too small to read with confidence in either screenshot; treat its wording "
                f"and exact styling as unverified. No background color, border, or plate-face font is "
                f"documented anywhere for this design (a genuine research gap, not an oversight), so the "
                f"background/border here are a plain, undecorated approximation rather than anything sourced."
            ),
            reference_urls=("https://saintsrow.fandom.com/wiki/Vehicles_in_Saints_Row:_The_Third",),
        ),
        background=Decoration(decoration_id="bg", kind=DecorationKind.SOLID_FILL, x_mm=0.0, y_mm=0.0,
                               color=WHITE, editable=False),
        border=Decoration(decoration_id="border", kind=DecorationKind.BORDER, x_mm=0.0, y_mm=0.0,
                           color=(150, 150, 150, 255)),
        fields=(
            PlateField(
                field_id="registration", label_key="plates.field.registration", role=FieldRole.REGISTRATION,
                x_mm=15.0, y_mm=38.0, width_mm=274.8, height_mm=64.0, alignment="center",
                char_source=_LATIN, char_scale=0.62, tracking=3.0,
                default_text="SR3 5221", color=BLACK,
                editable_in_authentic_mode=True,
            ),
            PlateField(
                field_id="steelport_tag", label_key="plates.field.steelport_tag", role=FieldRole.DECORATIVE_TEXT,
                x_mm=15.0, y_mm=116.0, width_mm=274.8, height_mm=20.0, alignment="center",
                char_source=_LATIN, char_scale=0.4, tracking=1.0,
                default_text="STEELPORT", color=(45, 130, 90, 255),
                editable_in_authentic_mode=False,
            ),
        ),
        tags=("vanity-available", "fictional-game", "low-confidence-detail"),
    )


def halo_new_mombasa() -> PlateTemplate:
    return PlateTemplate(
        template_id="halo-newmombasa-passenger-fictional",
        display_name_key="plates.template.halo_newmombasa_passenger_fictional",
        country="HALO", jurisdiction="New Mombasa", era="fictional", plate_type="passenger",
        width_mm=PLATE_W, height_mm=PLATE_H,
        accuracy_status=AccuracyStatus.FICTIONAL,
        provenance=Provenance(
            source_notes=(
                "The K-prefixed registration format (a nod to Mombasa being a real city in Kenya) on New "
                "Mombasa's civilian 'Genet' coupes in Halo 3: ODST is developer-confirmed -- Bungie's Joseph "
                "Staten specifically called out the license-plate Easter egg, and roughly 30 plates each "
                "encode a character/lore reference (e.g. 'KBL 117J' for John-117). "
                f"{SCREENSHOT_NOTE} No source (developer or otherwise) documents the plate's background "
                "color, border, or font -- this template's plain pale background and dark text are a "
                "reasonable default, not a sourced design. The 'post_bios' micro-print field is an "
                "approximate transcription of small print visible near one plate in a supplied screenshot "
                "(a similar fake-BIOS-string Easter egg also appears on the Halo: Reach templates below) -- "
                "the exact characters are not fully legible at that resolution, so treat this field's text "
                "as a best-effort reading, not a confirmed transcription."
            ),
            reference_urls=("https://www.halopedia.org/License_plate_Easter_eggs",),
        ),
        background=Decoration(decoration_id="bg", kind=DecorationKind.SOLID_FILL, x_mm=0.0, y_mm=0.0,
                               color=(225, 224, 218, 255), editable=False),
        border=None,
        fields=(
            PlateField(
                field_id="registration", label_key="plates.field.registration", role=FieldRole.REGISTRATION,
                x_mm=15.0, y_mm=48.0, width_mm=274.8, height_mm=58.0, alignment="center",
                char_source=_LATIN, char_scale=0.6, tracking=3.0,
                default_text="KBL 117J", color=(35, 35, 40, 255),
                validation=FieldValidation(
                    format_hint_key="plates.validation.halo_nm.format_hint",
                    min_length=8, max_length=8,
                    allowed_pattern=r"K[A-Z]{2} [0-9]{3}[A-Z]",
                ),
            ),
            PlateField(
                field_id="post_bios", label_key="plates.field.post_bios", role=FieldRole.DECORATIVE_TEXT,
                x_mm=15.0, y_mm=112.0, width_mm=274.8, height_mm=14.0, alignment="center",
                char_source=_LATIN, char_scale=0.32, tracking=0.5,
                default_text="POST-BIOS A29.6294H.01", color=(120, 120, 115, 255),
                editable_in_authentic_mode=False,
            ),
        ),
        tags=("vanity-available", "fictional-game"),
    )


def _halo_reach(template_id: str, display_name_key: str, default_text: str, validation, extra_fields,
                bg_color) -> PlateTemplate:
    return PlateTemplate(
        template_id=template_id,
        display_name_key=display_name_key,
        country="HALO", jurisdiction="Reach", era="fictional", plate_type="passenger",
        width_mm=PLATE_W, height_mm=PLATE_H,
        accuracy_status=AccuracyStatus.FICTIONAL,
        provenance=Provenance(
            source_notes=(
                "Halopedia's civilian-vehicles article states that identification on the planet Reach is "
                f"'achieved through a barcode,' unlike Earth locations (which use letters and numbers). "
                f"{SCREENSHOT_NOTE} No source documents what that barcode actually looks like, so this "
                "template's specific colors, proportions, and the barcode itself (approximated as a run of "
                "'|' characters through the same fontpack pipeline as every other field -- the schema has "
                "no barcode-symbology decoration kind) come entirely from the supplied screenshots, not "
                "from any wiki or official description. The 'standard' variant's registration reads "
                "'M·100627' (a raised middle dot), matching the supplied screenshot directly."
            ),
            reference_urls=("https://www.halopedia.org/Civilian_vehicles",),
        ),
        background=Decoration(decoration_id="bg", kind=DecorationKind.SOLID_FILL, x_mm=0.0, y_mm=0.0,
                               color=bg_color, editable=False),
        border=None,
        fields=(
            PlateField(
                field_id="registration", label_key="plates.field.registration", role=FieldRole.REGISTRATION,
                x_mm=15.0, y_mm=48.0, width_mm=274.8, height_mm=58.0, alignment="center",
                char_source=_LATIN, char_scale=0.6, tracking=3.0,
                default_text=default_text, color=(35, 35, 32, 255),
                validation=validation,
            ),
            *extra_fields,
        ),
        tags=("vanity-available", "fictional-game"),
    )


def halo_reach_barcode() -> PlateTemplate:
    return _halo_reach(
        "halo-reach-barcode-fictional", "plates.template.halo_reach_barcode_fictional",
        "T2345GB1",
        FieldValidation(format_hint_key="plates.validation.halo_reach.format_hint",
                         min_length=8, max_length=8, allowed_pattern=r"[A-Z][0-9]{4}[A-Z]{2}[0-9]"),
        extra_fields=(
            PlateField(
                field_id="barcode", label_key="plates.field.barcode", role=FieldRole.DECORATIVE_TEXT,
                x_mm=30.0, y_mm=14.0, width_mm=244.8, height_mm=28.0, alignment="center",
                char_source=_LATIN, char_scale=0.85, tracking=1.5,
                default_text="|" * 22, color=(30, 30, 28, 255),
                editable_in_authentic_mode=False,
            ),
            PlateField(
                field_id="spartan_bios", label_key="plates.field.spartan_bios", role=FieldRole.DECORATIVE_TEXT,
                x_mm=15.0, y_mm=112.0, width_mm=274.8, height_mm=14.0, alignment="center",
                char_source=_LATIN, char_scale=0.28, tracking=0.5,
                default_text="SPARTAN III BIOS S56.7854.3354-DKW", color=(110, 108, 100, 255),
                editable_in_authentic_mode=False,
            ),
        ),
        bg_color=(158, 154, 142, 255),
    )


def halo_reach_standard() -> PlateTemplate:
    return _halo_reach(
        "halo-reach-standard-fictional", "plates.template.halo_reach_standard_fictional",
        "M·100627",
        FieldValidation(format_hint_key="plates.validation.halo_reach_standard.format_hint",
                         min_length=8, max_length=8, allowed_pattern=r"M·[0-9]{6}"),
        extra_fields=(
            PlateField(
                field_id="csg_mark", label_key="plates.field.csg_mark", role=FieldRole.DECORATIVE_TEXT,
                x_mm=254.0, y_mm=52.0, width_mm=36.0, height_mm=20.0, alignment="center",
                char_source=_LATIN, char_scale=0.4, tracking=1.0,
                default_text="CSG", color=(70, 70, 65, 255),
                editable_in_authentic_mode=False,
            ),
        ),
        bg_color=(210, 208, 200, 255),
    )


def cyberpunk_night_city() -> PlateTemplate:
    return PlateTemplate(
        template_id="cp2077-nightcity-passenger-fictional",
        display_name_key="plates.template.cp2077_nightcity_passenger_fictional",
        country="CP2077", jurisdiction="Night City", era="fictional", plate_type="passenger",
        width_mm=PLATE_W, height_mm=PLATE_H,
        accuracy_status=AccuracyStatus.FICTIONAL,
        provenance=Provenance(
            source_notes=(
                "Modeled on a fan-made novelty-plate graphic the Forza Writer user supplied, itself inspired "
                "by Night City vehicle plates in Cyberpunk 2077 -- not a screenshot of the game itself or an "
                "extracted/official CD Projekt Red asset. Layout: a dark diagonal block along the left edge, "
                "bold 'NC 77' text (read as Night City / the game's 2077 setting), a small flag-like emblem "
                "in the top-right corner, and a dark lower band containing a glitch/barcode-style pattern of "
                "vertical bars. The left block's jagged torn edge and the emblem's specific graphic (a star "
                "over banded colors, whose in-universe meaning isn't identifiable from the image alone) are "
                "both simplified to plain rectangles here -- the schema has no torn-edge or icon/star "
                "decoration primitive. The bar pattern reuses the same repeated-'|' approximation as the "
                "Halo: Reach barcode template above, through the ordinary fontpack pipeline rather than a "
                "dedicated barcode renderer."
            ),
        ),
        background=Decoration(decoration_id="bg", kind=DecorationKind.SOLID_FILL, x_mm=0.0, y_mm=0.0,
                               color=(224, 224, 220, 255), editable=False),
        border=None,
        fields=(
            PlateField(
                field_id="registration", label_key="plates.field.registration", role=FieldRole.REGISTRATION,
                x_mm=56.0, y_mm=18.0, width_mm=190.0, height_mm=42.0, alignment="left",
                char_source=_LATIN, char_scale=0.6, tracking=3.0,
                default_text="NC 77", color=(32, 32, 36, 255),
                validation=FieldValidation(
                    format_hint_key="plates.validation.cp2077.format_hint",
                    min_length=5, max_length=5, allowed_pattern=r"NC [0-9]{2}",
                ),
                editable_in_authentic_mode=True,
            ),
            PlateField(
                field_id="glitch_band", label_key="plates.field.glitch_band", role=FieldRole.DECORATIVE_TEXT,
                x_mm=15.0, y_mm=98.0, width_mm=274.8, height_mm=32.0, alignment="left",
                char_source=_LATIN, char_scale=0.5, tracking=1.5,
                default_text="|  ||   |||  | ||||   ||  |   ||| |  ||||", color=(220, 220, 216, 255),
                editable_in_authentic_mode=False,
            ),
        ),
        decorations=(
            Decoration(decoration_id="left_band", kind=DecorationKind.JURISDICTION_MARK,
                       x_mm=0.0, y_mm=0.0, width_mm=46.0, height_mm=152.4, color=(35, 38, 48, 255)),
            Decoration(decoration_id="lower_band", kind=DecorationKind.CUSTOM_SHAPE,
                       x_mm=0.0, y_mm=88.0, width_mm=304.8, height_mm=64.4, color=(35, 38, 48, 255)),
            Decoration(decoration_id="emblem", kind=DecorationKind.SEAL,
                       x_mm=245.0, y_mm=14.0, width_mm=44.0, height_mm=26.0, color=(75, 85, 100, 255)),
        ),
        tags=("vanity-available", "fictional-game"),
    )


def _mirrors_edge(template_id: str, display_name_key: str, plate_type: str, bg_color, band_color,
                   extra_fields: tuple, extra_notes: str) -> PlateTemplate:
    return PlateTemplate(
        template_id=template_id,
        display_name_key=display_name_key,
        country="MEDGE", jurisdiction=None, era="fictional", plate_type=plate_type,
        width_mm=EU_STYLE_W, height_mm=EU_STYLE_H,
        accuracy_status=AccuracyStatus.FICTIONAL,
        provenance=Provenance(
            source_notes=(
                f"{SCREENSHOT_NOTE} Mirror's Edge (2008) doesn't give its city a confirmed on-screen name in "
                f"the supplied reference, so `jurisdiction` is left unset here rather than guessing one. Sized "
                f"520x110mm (the real EU standard plate size, not this file's usual US-shaped PLATE_W/PLATE_H) "
                f"since the developer (DICE, Stockholm) and the plates' own European/Nordic proportions in the "
                f"reference screenshots both point to a European size reference being the closer fit, not an "
                f"American one -- flagged as an explicit judgment call, not a confirmed in-game measurement. "
                f"{extra_notes} A third, police-vehicle plate variant exists in the game but the user hasn't "
                f"been able to get a clear look at it yet (no screenshot supplied) -- not modeled here; add it "
                f"once real reference exists rather than inventing one. The barcode is approximated as a run "
                f"of '|' characters through the ordinary metrics-based layout pipeline (see "
                f"glyph_resolve.py's module docstring), same as every other barcode-style template in this set."
            ),
        ),
        background=Decoration(decoration_id="bg", kind=DecorationKind.SOLID_FILL, x_mm=0.0, y_mm=0.0,
                               color=bg_color, editable=False),
        border=None,
        fields=extra_fields,
        decorations=(
            Decoration(decoration_id="left_band", kind=DecorationKind.JURISDICTION_MARK,
                       x_mm=0.0, y_mm=0.0, width_mm=18.0, height_mm=EU_STYLE_H, color=band_color),
        ),
        tags=("vanity-available", "fictional-game"),
    )


def mirrors_edge_transport() -> PlateTemplate:
    return _mirrors_edge(
        "medge-city-transport-fictional", "plates.template.medge_city_transport_fictional", "commercial",
        bg_color=(224, 222, 214, 255), band_color=(35, 85, 165, 255),
        extra_fields=(
            PlateField(
                field_id="label", label_key="plates.field.label", role=FieldRole.DECORATIVE_TEXT,
                x_mm=26.0, y_mm=6.0, width_mm=488.0, height_mm=20.0, alignment="left",
                char_source=_LATIN, char_scale=0.4, tracking=1.0,
                default_text="CARGO 01", color=(35, 35, 32, 255),
                editable_in_authentic_mode=True,
            ),
            PlateField(
                field_id="barcode", label_key="plates.field.barcode", role=FieldRole.DECORATIVE_TEXT,
                x_mm=26.0, y_mm=32.0, width_mm=488.0, height_mm=72.0, alignment="left",
                char_source=_LATIN, char_scale=0.45, tracking=2.0,
                default_text="|" * 16, color=(30, 30, 28, 255),
                editable_in_authentic_mode=False,
            ),
        ),
        extra_notes=(
            "The truck/transport plate shows a blue band down the left edge and small text near the top "
            "(illegible at the supplied screenshot's resolution/blur -- 'CARGO 01' below is an unreadable "
            "placeholder, not a transcription of anything actually printed on it) above a barcode filling "
            "most of the remaining plate."
        ),
    )


def mirrors_edge_passenger() -> PlateTemplate:
    return _mirrors_edge(
        "medge-city-passenger-fictional", "plates.template.medge_city_passenger_fictional", "passenger",
        bg_color=WHITE, band_color=(45, 145, 70, 255),
        extra_fields=(
            PlateField(
                field_id="barcode", label_key="plates.field.barcode", role=FieldRole.DECORATIVE_TEXT,
                x_mm=26.0, y_mm=8.0, width_mm=488.0, height_mm=94.0, alignment="left",
                char_source=_LATIN, char_scale=0.45, tracking=2.0,
                default_text="|" * 16, color=BLACK,
                editable_in_authentic_mode=False,
            ),
        ),
        extra_notes=(
            "The passenger-car plate shows a green band down the left edge and a barcode filling nearly the "
            "whole remaining plate -- no separate readable text is visible at the supplied screenshot's "
            "resolution, so this template has no text field beyond the barcode itself."
        ),
    )


def dying_light_harran() -> PlateTemplate:
    return PlateTemplate(
        template_id="dl-harran-passenger-fictional",
        display_name_key="plates.template.dl_harran_passenger_fictional",
        country="DL", jurisdiction=None, era="fictional", plate_type="passenger",
        width_mm=EU_STYLE_W, height_mm=EU_STYLE_H,
        accuracy_status=AccuracyStatus.FICTIONAL,
        provenance=Provenance(
            source_notes=(
                f"{SCREENSHOT_NOTE} Only one Dying Light plate has been supplied so far (on the rear of an "
                f"armored van), so unlike templates backed by multiple examples, nothing here about format "
                f"consistency is corroborated -- this is a single data point, treated honestly as one. Sized "
                f"520x110mm (the real EU standard, matching Mirror's Edge's own reasoning above) since the "
                f"plate's proportions in the screenshot read as European/Nordic, not American -- an explicit "
                f"judgment call, not a confirmed in-game measurement. Two text elements are visible: 'HAR' "
                f"(read as short for Harran, the game's setting) in an amber/orange tone on the left, and "
                f"'HHM 155 M' in a lighter grey on the right, against a dark charcoal background -- unlike "
                f"Mirror's Edge, 'HAR' is rendered here as ordinary text (JURISDICTION_TEXT), not a solid "
                f"colored band, since it reads as actual characters in the screenshot rather than a color "
                f"block. The exact spacing/punctuation between '155' and 'M' is a best-effort reading of a "
                f"blurry, angled shot, not a confident transcription -- treat the plain space used here as "
                f"one reasonable guess among others. No format validation is applied for the same reason: one "
                f"example plate isn't enough to assert a real pattern. Vehicle type (an armored security "
                f"van) doesn't clearly imply a distinct in-universe plate category, so plate_type defaults to "
                f"passenger rather than guessing a commercial/security designation with no supporting "
                f"evidence. A dark charcoal background is a best-effort read of the screenshot's lighting, "
                f"not a confirmed base color."
            ),
        ),
        background=Decoration(decoration_id="bg", kind=DecorationKind.SOLID_FILL, x_mm=0.0, y_mm=0.0,
                               color=(32, 30, 28, 255), editable=False),
        border=None,
        fields=(
            PlateField(
                field_id="jurisdiction_header", label_key="plates.field.jurisdiction_header",
                role=FieldRole.JURISDICTION_TEXT,
                x_mm=20.0, y_mm=28.0, width_mm=90.0, height_mm=54.0, alignment="center",
                char_source=_LATIN, char_scale=0.53, tracking=2.0,
                default_text="HAR", color=(216, 148, 42, 255),
                editable_in_authentic_mode=False,
            ),
            PlateField(
                field_id="registration", label_key="plates.field.registration", role=FieldRole.REGISTRATION,
                x_mm=128.0, y_mm=24.0, width_mm=372.0, height_mm=62.0, alignment="left",
                char_source=_LATIN, char_scale=0.56, tracking=3.0,
                default_text="HHM 155 M", color=(222, 222, 216, 255),
                editable_in_authentic_mode=True,
            ),
        ),
        tags=("vanity-available", "fictional-game"),
    )


def phasmophobia_ghd_van() -> PlateTemplate:
    return PlateTemplate(
        template_id="phasmophobia-ghd-van-fictional",
        display_name_key="plates.template.phasmophobia_ghd_van_fictional",
        country="PHAS", jurisdiction=None, era="fictional", plate_type="commercial",
        width_mm=PLATE_W, height_mm=PLATE_H,
        accuracy_status=AccuracyStatus.FICTIONAL,
        provenance=Provenance(
            source_notes=(
                f"{SCREENSHOT_NOTE} Only one plate exists in Phasmophobia (the player team's Iveco Eurocargo "
                f"75E18 van/truck, a static, one-of-a-kind prop, not a per-vehicle-type plate family the way "
                f"most other templates in this set model a whole in-game standard), so a single template "
                f"fully covers it -- there's no second variant to build. Registration 'GHD666' -- read from "
                f"the supplied screenshot as '7GHD666' -- and 'GHD' standing for 'Ghost Huntin' Distribution' "
                f"(the in-game company name) are independently corroborated by the Phasmophobia Fandom wiki's "
                f"Truck page, not just the one screenshot. The smaller text along the plate's bottom is not "
                f"independently confirmed beyond the user's own best-effort reading of a dark, low-resolution "
                f"screenshot as 'GHOST HUNTIN' DIST.' -- a plausible abbreviated expansion of 'GHD' given the "
                f"wiki-confirmed company name, but not a verbatim transcription anyone has corroborated. "
                f"Plain black-on-white is a standard, unremarkable US plate color scheme and reads that way "
                f"in the screenshot; US size (this file's default PLATE_W/PLATE_H, the real 12x6in standard) "
                f"per the user's own identification of it as a US-style plate, the game being set in the US. "
                f"plate_type is 'commercial' rather than 'passenger' since the vehicle is explicitly a "
                f"company distribution van, unlike Dying Light's van above where no such distinction was "
                f"evidenced."
            ),
        ),
        background=Decoration(decoration_id="bg", kind=DecorationKind.SOLID_FILL, x_mm=0.0, y_mm=0.0,
                               color=WHITE, editable=False),
        border=None,
        fields=(
            PlateField(
                field_id="registration", label_key="plates.field.registration", role=FieldRole.REGISTRATION,
                x_mm=15.0, y_mm=38.0, width_mm=274.8, height_mm=76.0, alignment="center",
                char_source=_LATIN, char_scale=0.55, tracking=3.0,
                default_text="7GHD666", color=BLACK,
                editable_in_authentic_mode=True,
            ),
            PlateField(
                field_id="tagline", label_key="plates.field.tagline", role=FieldRole.DECORATIVE_TEXT,
                x_mm=15.0, y_mm=124.0, width_mm=274.8, height_mm=16.0, alignment="center",
                char_source=_LATIN, char_scale=0.4, tracking=1.0,
                default_text="GHOST HUNTIN' DIST.", color=(90, 88, 84, 255),
                editable_in_authentic_mode=False,
            ),
        ),
        tags=("vanity-available", "fictional-game"),
    )


TEMPLATES = (
    gta_san_andreas,
    nfs_fairhaven, nfs_rockport, nfs_palmont, nfs_tri_city_bay, nfs_seacrest_county,
    sr_stilwater, sr_steelport,
    halo_new_mombasa, halo_reach_barcode, halo_reach_standard,
    cyberpunk_night_city,
    mirrors_edge_transport, mirrors_edge_passenger,
    dying_light_harran,
    phasmophobia_ghd_van,
)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for builder in TEMPLATES:
        template = builder()
        country_dir = OUT_DIR / template.country
        country_dir.mkdir(parents=True, exist_ok=True)
        path = country_dir / f"{template.template_id}.json"
        path.write_text(json.dumps(template.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
