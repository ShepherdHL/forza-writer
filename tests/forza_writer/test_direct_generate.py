from pathlib import Path

import pytest

from PIL import Image, ImageDraw

from forza_writer.direct_generate import (
    generate_direct, generate_image, generate_legacy, generate_modern)


WINDOWS_ARIAL = Path(r"C:\Windows\Fonts\arial.ttf")
requires_arial = pytest.mark.skipif(not WINDOWS_ARIAL.exists(), reason="Arial is unavailable")


@requires_arial
def test_legacy_traces_the_complete_repeated_text_run():
    single, _warnings, single_meta = generate_legacy("A", WINDOWS_ARIAL, cell_size=4)
    repeated, _warnings, repeated_meta = generate_legacy("AA", WINDOWS_ARIAL, cell_size=4)

    assert single_meta["method"] == "legacy"
    assert repeated_meta["rectangles"] > single_meta["rectangles"]
    assert len(repeated) == repeated_meta["rectangles"]
    assert all(shape["mask"] is False for shape in repeated)


@requires_arial
def test_modern_fits_each_distinct_character_once(monkeypatch):
    shapes, warnings, metadata = generate_modern("ABA", WINDOWS_ARIAL)

    assert len(shapes) > 0
    assert warnings == []
    assert metadata["unique_glyphs"] == 2
    assert set(metadata["strategies"]) == {"A", "B"}
    assert set(metadata["quality_by_glyph"]) == {"A", "B"}
    assert all(item["selected"] in {"primitive", "exact"}
               for item in metadata["quality_by_glyph"].values())


@requires_arial
def test_modern_quality_gate_can_select_a_skewed_primitive(monkeypatch):
    skewed = {
        "type": 1048677, "type_word": 101,
        "data": [0.0, 0.0, 1.0, 1.0, 0.0, 0.36, 0],
        "color": [255, 255, 255, 255], "mask": False,
    }
    monkeypatch.setattr(
        "forza_writer.direct_generate.fit_glyph_name_with_strategy",
        lambda *_args, **_kwargs: ([skewed], "primitive_search"))
    monkeypatch.setattr(
        "forza_writer.direct_generate.assess_glyph_name",
        lambda *_args, **_kwargs: ({
            "iou": 0.99, "precision": 0.99, "recall": 0.99,
            "boundary_f1": 0.98,
            "components_expected": 1, "components_generated": 1,
            "holes_expected": 1, "holes_generated": 1,
            "unknown_type_words": [], "verdict": "pass", "resolution": 128,
        }, None, None))

    shapes, warnings, metadata = generate_modern("A", WINDOWS_ARIAL)

    assert warnings == []
    assert metadata["quality_by_glyph"]["A"]["selected"] == "primitive"
    assert metadata["quality_by_glyph"]["A"]["selected_skewed_layers"] == 1
    assert shapes[0]["data"][5] == pytest.approx(0.36)


def test_direct_dispatch_rejects_unknown_method():
    with pytest.raises(ValueError, match="method must be one of"):
        generate_direct("A", WINDOWS_ARIAL, method="unknown")


def test_image_to_text_lifts_light_signature_without_a_font(tmp_path):
    source = tmp_path / "signature.png"
    image = Image.new("RGB", (80, 40), (230, 40, 20))
    draw = ImageDraw.Draw(image)
    draw.line((8, 30, 28, 8, 45, 31, 70, 10), fill="white", width=3)
    image.save(source)

    shapes, warnings, metadata = generate_image(
        source, polarity="light", threshold=220, cell_size=1)

    assert shapes
    assert warnings == []
    assert metadata["method"] == "image"
    assert metadata["polarity"] == "light"
    assert metadata["threshold"] == 220
    assert len(shapes) == metadata["rectangles"]
    assert all(shape["color"] == [255, 255, 255, 255] for shape in shapes)


def test_image_to_text_uses_transparency_automatically(tmp_path):
    source = tmp_path / "transparent.png"
    image = Image.new("RGBA", (24, 24), (255, 255, 255, 0))
    ImageDraw.Draw(image).ellipse((4, 4, 19, 19), fill=(10, 20, 30, 255))
    image.save(source)

    shapes, _warnings, metadata = generate_direct(
        method="image", image_path=source, polarity="auto", cell_size=2)

    assert shapes
    assert metadata["polarity"] == "alpha"
