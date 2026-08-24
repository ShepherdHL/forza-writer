from forza_writer.export import to_json
from forza_writer.layout import layout_forza_text


def test_experimental_produces_twelve_shapes():
    shapes = layout_forza_text("EXPERIMENTAL", font=1)
    assert len(shapes) == 12


def test_experimental_first_shape_is_e():
    shapes = layout_forza_text("EXPERIMENTAL", font=1)
    assert shapes[0]["type"] == 1050481
    assert shapes[0]["type_word"] == 1905


def test_experimental_shape_data_structure():
    shapes = layout_forza_text("EXPERIMENTAL", font=1)
    for shape in shapes:
        assert "type" in shape
        assert "type_word" in shape
        assert len(shape["data"]) == 7
        assert shape["color"] == [255, 255, 255, 255]


def test_export_format():
    shapes = layout_forza_text("EXPERIMENTAL", font=1)
    data = to_json(shapes)
    assert data["format"] == "fh6_typecode_json_export_v1"
    assert data["source"] == "forza-writer"
    assert len(data["shapes"]) == 12
    assert all(s["mask"] is False for s in data["shapes"])


def test_multiline_layout():
    shapes = layout_forza_text("AB\nCD", font=1)
    assert len(shapes) == 4
