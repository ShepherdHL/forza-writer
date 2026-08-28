from forza_writer.export import to_json


def test_shape_without_mask_key_defaults_to_false():
    shapes = [{"type": 1048677, "type_word": 101, "data": [0, 0, 1, 1, 0, 0, 0],
               "color": [255, 255, 255, 255]}]
    out = to_json(shapes)
    assert out["shapes"][0]["mask"] is False


def test_shape_with_mask_true_survives_export():
    # to_json() must not force-overwrite an upstream mask:True back to
    # False. Stencil mode's cutouts depend on this surviving.
    shapes = [{"type": 1048677, "type_word": 101, "data": [0, 0, 1, 1, 0, 0, 1],
               "color": [0, 0, 0, 255], "mask": True}]
    out = to_json(shapes)
    assert out["shapes"][0]["mask"] is True


def test_format_and_source_fields():
    out = to_json([])
    assert out["format"] == "fh6_typecode_json_export_v1"
    assert out["source"] == "forza-writer"
    assert out["shapes"] == []
