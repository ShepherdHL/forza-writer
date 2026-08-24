from pathlib import Path

import numpy as np

from forza_writer.glyph_quality import compare_masks, save_diff_overlay


def test_identical_masks_pass_with_perfect_metrics():
    target = np.zeros((32, 32), dtype=bool)
    target[5:25, 7:23] = True
    result = compare_masks(target, target.copy())
    assert result["verdict"] == "pass"
    assert result["iou"] == 1.0
    assert result["boundary_f1"] == 1.0
    assert result["components_expected"] == result["components_generated"] == 1


def test_missing_component_requires_review_even_when_main_shape_matches():
    target = np.zeros((64, 64), dtype=bool)
    target[5:45, 5:45] = True
    target[55:58, 55:58] = True
    generated = target.copy()
    generated[55:58, 55:58] = False
    result = compare_masks(target, generated)
    assert result["components_expected"] == 2
    assert result["components_generated"] == 1
    assert result["verdict"] == "review"


def test_lost_hole_requires_review():
    target = np.zeros((40, 40), dtype=bool)
    target[5:35, 5:35] = True
    target[14:26, 14:26] = False
    generated = np.zeros_like(target)
    generated[5:35, 5:35] = True
    result = compare_masks(target, generated)
    assert result["holes_expected"] == 1
    assert result["holes_generated"] == 0
    assert result["verdict"] == "review"


def test_diff_overlay_uses_documented_colors(tmp_path: Path):
    target = np.array([[True, True, False]], dtype=bool)
    generated = np.array([[True, False, True]], dtype=bool)
    path = save_diff_overlay(tmp_path / "diff.png", target, generated)
    from PIL import Image
    image = Image.open(path)
    assert [image.getpixel((x, 0)) for x in range(3)] == [
        (245, 245, 245), (45, 125, 255), (245, 70, 70)
    ]
