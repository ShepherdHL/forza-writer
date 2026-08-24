import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "tools"))
from gen_fabric_project import build_fabric_project  # noqa: E402

AMARILLO_FONTPACK = Path(__file__).resolve().parent.parent.parent / "data" / "fontpacks" / "AMARILLO-USAF"
requires_fontpack = pytest.mark.skipif(not (AMARILLO_FONTPACK / "manifest.json").exists(),
                                        reason="sample fontpack not present on this machine")


@requires_fontpack
def test_suggested_name_encodes_curve_segments_and_shape_count():
    project = build_fabric_project(AMARILLO_FONTPACK, log=lambda *_: None)
    import json
    manifest = json.loads((AMARILLO_FONTPACK / "manifest.json").read_text(encoding="utf-8"))

    expected = f"{manifest['prefix']}_S{manifest['curve_segments']}_{len(project['shapes'])}"
    assert project["suggested_name"] == expected


@requires_fontpack
def test_suggested_name_is_distinct_from_display_name():
    # "name" stays the plain prefix (used inside the project, e.g. for any
    # future KFPS-visible label); "suggested_name" is only for the export
    # filename. They should differ once real shape counts are involved.
    project = build_fabric_project(AMARILLO_FONTPACK, log=lambda *_: None)
    assert project["name"] != project["suggested_name"]
    assert project["name"] in project["suggested_name"]


@requires_fontpack
def test_suggested_name_has_no_path_separators(tmp_path):
    project = build_fabric_project(AMARILLO_FONTPACK, log=lambda *_: None)
    assert "/" not in project["suggested_name"]
    assert "\\" not in project["suggested_name"]
