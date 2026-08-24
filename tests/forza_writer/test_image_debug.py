"""Image-to-Text debug rendering and the diagnostics sidecar."""

import json
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from forza_writer.direct_generate import generate_image  # noqa: E402
from forza_writer.image_debug import (  # noqa: E402
    DEBUG_LABELS, DEBUG_MODES, ImageTraceDebug, accuracy, diagnostics, render_debug,
    write_debug_outputs)


@pytest.fixture
def lettering_image(tmp_path) -> Path:
    """A crop resembling what this feature is for: light lettering shapes on a
    dark background, the signature/logo case."""
    path = tmp_path / "sign.png"
    image = Image.new("RGB", (220, 90), (15, 15, 18))
    draw = ImageDraw.Draw(image)
    draw.rectangle([20, 25, 90, 60], fill=(250, 250, 250))
    draw.ellipse([120, 20, 190, 70], fill=(250, 250, 250))
    image.save(path)
    return path


@pytest.fixture
def trace(lettering_image) -> ImageTraceDebug:
    _shapes, _warnings, metadata = generate_image(lettering_image, cell_size=2)
    return metadata["trace_debug"]


# --- the snapshot the renderers work from --------------------------------

def test_generate_image_hands_back_a_trace_snapshot(trace):
    assert isinstance(trace, ImageTraceDebug)
    assert trace.rects
    assert trace.mask.shape == (trace.image.height, trace.image.width)


def test_snapshot_is_not_json_serializable_and_must_stay_out_of_saved_output(trace):
    # Guards the reason generate_image's caller filters this key out before
    # building the saved payload: it holds live PIL/numpy objects.
    with pytest.raises(TypeError):
        json.dumps({"trace_debug": trace})


def test_coverage_matches_the_rectangles_that_were_emitted(trace):
    covered = trace.coverage()
    assert covered.shape == trace.mask.shape
    manual = np.zeros_like(trace.mask)
    for x, y, width, height in trace.rects:
        manual[y:y + height, x:x + width] = True
    assert np.array_equal(covered, manual)


# --- accuracy ------------------------------------------------------------

def test_accuracy_splits_pixels_into_matched_missed_and_overshoot(trace):
    scores = accuracy(trace)
    assert scores["matched_pixels"] > 0
    assert scores["ink_pixels"] == scores["matched_pixels"] + scores["missed_pixels"]
    assert 0.0 <= scores["iou"] <= 1.0
    assert 0.0 <= scores["precision"] <= 1.0
    assert 0.0 <= scores["recall"] <= 1.0


def test_a_clean_high_contrast_trace_is_accurate(trace):
    # Solid shapes on a flat background should trace nearly exactly; a low
    # score here would mean thresholding or decomposition regressed.
    assert accuracy(trace)["iou"] > 0.9


def test_perfect_coverage_scores_one():
    mask = np.zeros((10, 10), dtype=bool)
    mask[2:8, 2:8] = True
    exact = ImageTraceDebug(
        image=Image.new("RGB", (10, 10)), mask=mask, rects=[(2, 2, 6, 6)],
        polarity="light", threshold=128, cell_size=1, source_size=(10, 10))
    scores = accuracy(exact)
    assert scores["iou"] == pytest.approx(1.0)
    assert scores["missed_pixels"] == 0
    assert scores["overshoot_pixels"] == 0


def test_empty_trace_does_not_divide_by_zero():
    blank = ImageTraceDebug(
        image=Image.new("RGB", (4, 4)), mask=np.zeros((4, 4), dtype=bool), rects=[],
        polarity="light", threshold=128, cell_size=1, source_size=(4, 4))
    assert accuracy(blank)["iou"] == 1.0


# --- rendering -----------------------------------------------------------

@pytest.mark.parametrize("mode", DEBUG_MODES)
def test_every_mode_renders_an_rgb_image(trace, mode):
    rendered = render_debug(trace, mode)
    assert rendered.mode == "RGB"
    assert rendered.width > 0 and rendered.height > 0


def test_single_panel_modes_match_the_traced_image_size(trace):
    for mode in ("trace", "heatmap", "contours"):
        assert render_debug(trace, mode).size == trace.image.size


def test_combined_view_tiles_four_panels(trace):
    combined = render_debug(trace, "combined")
    assert combined.width > trace.image.width
    assert combined.height > trace.image.height


def test_unknown_mode_falls_back_instead_of_raising(trace):
    # A diagnostic aid must never be what breaks a generation that worked.
    assert render_debug(trace, "no-such-mode").size == render_debug(trace, "combined").size


def test_every_mode_has_a_label_for_the_settings_picker():
    assert set(DEBUG_LABELS) == set(DEBUG_MODES)


def test_heatmap_distinguishes_matched_from_missed_ink():
    mask = np.zeros((8, 8), dtype=bool)
    mask[1:7, 1:7] = True
    partial = ImageTraceDebug(
        image=Image.new("RGB", (8, 8)), mask=mask, rects=[(1, 1, 6, 3)],
        polarity="light", threshold=128, cell_size=1, source_size=(8, 8))
    pixels = np.asarray(render_debug(partial, "heatmap"))
    # Covered ink and uncovered ink must not render the same colour, or the
    # view cannot answer the question it exists for.
    assert tuple(pixels[2, 3]) != tuple(pixels[5, 3])


# --- diagnostics sidecar -------------------------------------------------

def test_diagnostics_record_settings_counts_and_accuracy(trace):
    payload = diagnostics(trace)
    assert payload["method"] == "image"
    assert payload["vinyl_count"] == len(trace.rects)
    assert payload["vinyl_types"] == {"Square": len(trace.rects)}
    assert payload["polarity"] in {"light", "dark", "alpha"}
    assert "iou" in payload["accuracy"]


def test_diagnostics_note_source_and_generation_dimensions(trace):
    payload = diagnostics(trace)
    assert payload["source_dimensions"] == list(trace.source_size)
    assert payload["generation_dimensions"] == list(trace.image.size)


def test_diagnostics_are_json_serializable(trace):
    assert json.loads(json.dumps(diagnostics(trace)))


def test_a_downscaled_trace_says_so(lettering_image, tmp_path):
    big = tmp_path / "big.png"
    Image.open(lettering_image).resize((900, 400)).save(big)
    _s, _w, metadata = generate_image(big, max_dimension=128)
    assert diagnostics(metadata["trace_debug"])["downscaled"] is True


# --- writing the companion files ----------------------------------------

def test_nothing_is_written_unless_asked(trace, tmp_path):
    # Debug output is strictly opt-in: saving a design must not quietly
    # scatter extra files beside it.
    out = tmp_path / "OUT.json"
    out.write_text("{}", encoding="utf-8")
    assert write_debug_outputs(out, trace) == []
    assert list(tmp_path.glob("OUT.*")) == [out]


def test_source_copy_is_named_after_the_output_and_leaves_the_original_alone(
        trace, lettering_image, tmp_path):
    out = tmp_path / "SIGN.json"
    out.write_text("{}", encoding="utf-8")
    before = lettering_image.read_bytes()
    write_debug_outputs(out, trace, source_path=lettering_image, save_source=True)
    assert (tmp_path / "SIGN.source.png").exists()
    assert lettering_image.read_bytes() == before, "the user's original must never be modified"


def test_debug_output_writes_an_image_and_a_diagnostics_file(trace, tmp_path):
    out = tmp_path / "SIGN.json"
    out.write_text("{}", encoding="utf-8")
    written = write_debug_outputs(out, trace, save_debug=True, mode="heatmap")
    names = {Path(p).name for p in written}
    assert names == {"SIGN.debug.png", "SIGN.diagnostics.json"}
    payload = json.loads((tmp_path / "SIGN.diagnostics.json").read_text(encoding="utf-8"))
    assert payload["debug_view"] == "heatmap"


def test_companion_files_share_the_outputs_stem(trace, lettering_image, tmp_path):
    out = tmp_path / "MY-LOGO.json"
    out.write_text("{}", encoding="utf-8")
    written = write_debug_outputs(
        out, trace, source_path=lettering_image, save_source=True, save_debug=True)
    assert all(Path(p).name.startswith("MY-LOGO.") for p in written)


def test_diagnostics_record_which_source_file_was_traced(trace, lettering_image, tmp_path):
    out = tmp_path / "SIGN.json"
    out.write_text("{}", encoding="utf-8")
    write_debug_outputs(out, trace, source_path=lettering_image, save_debug=True)
    payload = json.loads((tmp_path / "SIGN.diagnostics.json").read_text(encoding="utf-8"))
    assert payload["source_file"] == str(lettering_image)
