import json

from forza_writer.fabric_project import save, to_fabric_project
from forza_writer.shapes import resource_to_shape_word, resource_to_typecode


def _square_shape(x=0.0, y=0.0):
    return {
        "type": resource_to_typecode("Primitives", 1),
        "type_word": resource_to_shape_word("Primitives", 1),
        "data": [x, y, 1.0, 1.0, 0.0, 0.0, 0],
        "color": [255, 255, 255, 255],
    }


def test_top_level_schema():
    project = to_fabric_project([_square_shape()], name="TestProject")
    assert project["format"] == "kloudy_fabric_editor_project_v1"
    assert project["name"] == "TestProject"
    assert project["layer_count"] == 1
    assert len(project["shapes"]) == 1
    assert "editor_guides" in project
    assert project["editor_collapsed_groups"] == []
    assert "editor_source_overlay" not in project


def test_shape_gets_full_editor_metadata():
    project = to_fabric_project([_square_shape()], name="TestProject")
    shape = project["shapes"][0]
    for key in ("type", "type_word", "data", "color", "mask", "score", "source_format",
                "resource_family", "resource_index", "shape_name", "legacy_type",
                "legacy_divisor", "legacy_offset", "editor_id", "editor_hidden",
                "editor_locked", "editor_group_id", "editor_group_name"):
        assert key in shape, f"missing {key}"
    assert shape["resource_family"] == "Primitives"
    assert shape["resource_index"] == 1
    assert shape["shape_name"] == "Square"
    assert shape["mask"] is False
    assert shape["editor_id"] == "e1"
    assert shape["editor_group_id"] is None
    assert shape["editor_group_name"] is None


def test_grouping_assigns_matching_ids_and_ungrouped_stays_none():
    shapes = [_square_shape(), _square_shape(), _square_shape()]
    project = to_fabric_project(shapes, name="TestProject", groups=[("Group A", [0, 1])])
    s0, s1, s2 = project["shapes"]
    assert s0["editor_group_id"] == s1["editor_group_id"]
    assert s0["editor_group_name"] == s1["editor_group_name"] == "Group A"
    assert s2["editor_group_id"] is None
    assert s2["editor_group_name"] is None


def test_two_groups_get_distinct_ids():
    shapes = [_square_shape(), _square_shape()]
    project = to_fabric_project(shapes, name="TestProject", groups=[("A", [0]), ("B", [1])])
    assert project["shapes"][0]["editor_group_id"] != project["shapes"][1]["editor_group_id"]


def test_source_overlay_round_trips_when_supplied():
    overlay = {"version": 1, "kind": "layered_svg", "svg_text": "<svg></svg>"}
    project = to_fabric_project([_square_shape()], name="TestProject", source_overlay=overlay)
    assert project["editor_source_overlay"] == overlay


def test_save_creates_parent_dirs_and_writes_valid_json(tmp_path):
    project = to_fabric_project([_square_shape()], name="TestProject")
    out_path = tmp_path / "nested" / "dir" / "out.fabric-project.json"
    save(project, out_path)
    assert out_path.exists()
    loaded = json.loads(out_path.read_text(encoding="utf-8"))
    assert loaded["name"] == "TestProject"
