"""One-time/rerunnable converter: the GTPlanet Colour Creation Database
spreadsheet -> assets/data/manufacturer_colors.json.

Source: "Forza Colour Sheet (Est. 2019)", catalogued by Mitcho2001, JaCor653,
and MadaraxUchiha —
https://www.gtplanet.net/forum/threads/forza-horizon-4-colour-creation-database-constant-work-in-progress-read-first-post.384407/#post-12589813
(see THIRD_PARTY_NOTICES.md for the full credit/usage note). Used with
permission from the repo owner, who has direct visibility into the GTPlanet
community's norms around this data — not an independently verified license.

The source files themselves are not checked into this repo (only the JSON
this script produces is); point this script at your own copies:

    python tools/build_manufacturer_colors.py \
        "Forza Colour Sheet (Est. 2019) - Vehicle Colours.csv" \
        "Forza Colour Sheet (Est. 2019).xlsx"

`openpyxl` is a dependency of *this script only* (to read the xlsx's Wheel
Colours sheet, which has no CSV export) — it is not added to
requirements.txt since the shipped app never reads .xlsx files. Install it
once with `pip install openpyxl` before running this.

Each row's HUE/SATURATION/BRIGHTNESS cells are recorded like "0.53 L" or
"0.99 R" — a normalized Forza H,S,B value (see forza_writer/forza_colors.py)
plus an "L"/"R" marker for which exact slider-click position (of two that
round to the same displayed value) reproduces the color precisely in-game.
That notation is preserved as-is in the output for players who want the
precise value, alongside a computed hex swatch (via
`forza_colors.forza_hsb_to_rgb`) for display purposes.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from forza_writer.forza_colors import forza_hsb_to_rgb  # noqa: E402

_VALUE_RE = re.compile(r"^([0-9.]+)\s*([LRlr])$")


def _parse_value(raw: str) -> tuple[float, str] | None:
    text = (raw or "").strip()
    if not text:
        return None
    match = _VALUE_RE.match(text)
    if not match:
        return None
    try:
        value = float(match.group(1))
    except ValueError:
        return None
    if not (0.0 <= value <= 1.0):
        return None
    return value, match.group(2).upper()


def _build_row(make: str, name: str, paint_type: str, category: str,
               h1_raw: str, s1_raw: str, b1_raw: str,
               h2_raw: str, s2_raw: str, b2_raw: str) -> list | None:
    make, name, paint_type = (make or "").strip(), (name or "").strip(), (paint_type or "").strip()
    if not make or not name:
        return None
    h1, s1, b1 = _parse_value(h1_raw), _parse_value(s1_raw), _parse_value(b1_raw)
    if not (h1 and s1 and b1):
        return None
    h2, s2, b2 = _parse_value(h2_raw), _parse_value(s2_raw), _parse_value(b2_raw)

    rgb1 = forza_hsb_to_rgb(h1[0], s1[0], b1[0])
    hex1 = f"#{rgb1.r:02x}{rgb1.g:02x}{rgb1.b:02x}"
    hex2 = ""
    if h2 and s2 and b2:
        rgb2 = forza_hsb_to_rgb(h2[0], s2[0], b2[0])
        hex2 = f"#{rgb2.r:02x}{rgb2.g:02x}{rgb2.b:02x}"

    return [
        make, name, paint_type, category, hex1, hex2,
        f"{h1[0]:.2f} {h1[1]}", f"{s1[0]:.2f} {s1[1]}", f"{b1[0]:.2f} {b1[1]}",
    ]


def parse_vehicle_csv(path: Path) -> tuple[list[list], int]:
    rows, skipped = [], 0
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        next(reader, None)  # "COLOR 1 (X)" / "COLOR 2 (Y)" group header
        next(reader, None)  # column names
        for raw in reader:
            if len(raw) < 9:
                continue
            row = _build_row(raw[0], raw[1], raw[2], "Vehicle",
                              raw[3], raw[4], raw[5], raw[6], raw[7], raw[8])
            if row:
                rows.append(row)
            elif (raw[0] or "").strip() and (raw[1] or "").strip():
                skipped += 1
    return rows, skipped


def parse_wheel_sheet(xlsx_path: Path) -> tuple[list[list], int]:
    import openpyxl

    wb = openpyxl.load_workbook(xlsx_path, data_only=True, read_only=True)
    ws = wb["Wheel Colours"]
    rows, skipped = [], 0
    for i, raw in enumerate(ws.iter_rows(values_only=True)):
        if i < 2 or len(raw) < 9:
            continue
        row = _build_row(raw[0], raw[1], raw[2], "Wheel",
                          raw[3], raw[4], raw[5], raw[6], raw[7], raw[8])
        if row:
            rows.append(row)
        elif (raw[0] or "") and (raw[1] or ""):
            skipped += 1
    return rows, skipped


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(2)
    vehicle_csv, xlsx = Path(sys.argv[1]), Path(sys.argv[2])

    vehicle_rows, vehicle_skipped = parse_vehicle_csv(vehicle_csv)
    wheel_rows, wheel_skipped = parse_wheel_sheet(xlsx)
    rows = vehicle_rows + wheel_rows

    out_path = Path(__file__).resolve().parent.parent / "assets" / "data" / "manufacturer_colors.json"
    out_path.write_text(json.dumps(rows, separators=(",", ":")), encoding="utf-8")

    makes = {row[0] for row in rows}
    print(f"wrote {out_path} — {len(rows)} rows ({len(vehicle_rows)} vehicle, "
          f"{len(wheel_rows)} wheel), {len(makes)} makes, "
          f"{vehicle_skipped + wheel_skipped} malformed source rows skipped")


if __name__ == "__main__":
    main()
