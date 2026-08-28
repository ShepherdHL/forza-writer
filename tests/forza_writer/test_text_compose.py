import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from gen_modelbin import extract_contours  # noqa: E402
from gen_fontpack import build_fontpack, pack_dir_for  # noqa: E402
from forza_writer.compute_backend import resolve_backend  # noqa: E402
from forza_writer.text_compose import _glyph_layout_metrics, compose_text  # noqa: E402
from forza_writer.text_style import LineFill, TextStyle  # noqa: E402

AMARILLO_FONT = Path.home() / "Desktop" / "amarillo-usaf" / "amarurgt.ttf"
requires_font = pytest.mark.skipif(not AMARILLO_FONT.exists(), reason="test font not present on this machine")


@pytest.fixture(scope="module")
def small_pack(tmp_path_factory):
    out_dir = tmp_path_factory.mktemp("text_compose_pack_root")
    build_fontpack(AMARILLO_FONT, out_dir, "TCTEST", output="json",
                    chars={"A", "B", "M", ".", "T", "g"}, log=lambda *_: None)
    backend = resolve_backend("auto")
    return pack_dir_for(out_dir, "TCTEST", "json", 8, backend.resolved)


@requires_font
def test_size_correction_period_is_smaller_than_capital_m(small_pack):
    period_shapes, warnings = compose_text(".", small_pack)
    m_shapes, _ = compose_text("M", small_pack)
    assert warnings == []

    period_scale = sum(abs(s["data"][2]) + abs(s["data"][3]) for s in period_shapes) / len(period_shapes)
    m_scale = sum(abs(s["data"][2]) + abs(s["data"][3]) for s in m_shapes) / len(m_shapes)
    assert period_scale < m_scale


@requires_font
def test_glyph_bbox_center_differs_for_short_vs_tall_glyph(small_pack):
    # This is exactly the discrepancy compose_text's baseline correction
    # exists to cancel out: per-glyph bbox centering (what normalize_to_128
    # does at generation time) centres a short glyph like '.' at a very
    # different raw-font Y than a tall glyph like 'M'. Naively placing
    # both glyphs' already-normalized shapes on the same line (each
    # centred on its own bbox) would misalign their baselines. Both should
    # in fact sit on the same raw-font baseline (y=0).
    manifest = json.loads((small_pack / "manifest.json").read_text(encoding="utf-8"))
    font_path = manifest["font_file"]
    curve_segments = manifest["curve_segments"]
    period_metrics = _glyph_layout_metrics(".", font_path, curve_segments)
    m_metrics = _glyph_layout_metrics("M", font_path, curve_segments)
    assert period_metrics.cy != m_metrics.cy

    period_contours, _ = extract_contours(".", Path(font_path), curve_segments)
    m_contours, _ = extract_contours("M", Path(font_path), curve_segments)
    period_min_y = min(p[1] for c in period_contours for p in c)
    m_min_y = min(p[1] for c in m_contours for p in c)
    # Both glyphs sit flush on the font's baseline (raw y=0) despite their
    # very different heights/centres: this is why baseline correction
    # (not bbox-centre correction) is what compose_text needs to apply.
    assert period_min_y == 0
    assert m_min_y == 0


@requires_font
def test_advance_width_spacing_matches_real_hmtx_not_ink_bbox(small_pack):
    single, _ = compose_text("A", small_pack)
    double, _ = compose_text("AA", small_pack)
    n = len(single)
    assert len(double) == 2 * n

    manifest = json.loads((small_pack / "manifest.json").read_text(encoding="utf-8"))
    from fontTools.ttLib import TTFont
    font = TTFont(manifest["font_file"])
    try:
        cmap = font.getBestCmap()
        advance_font_units = font["hmtx"].metrics[cmap[ord("A")]][0]
        units_per_em = font["head"].unitsPerEm
    finally:
        font.close()
    from forza_writer.text_compose import K
    expected_advance = advance_font_units * (200.0 / units_per_em) * K

    first_x0 = double[0]["data"][0]
    second_x0 = double[n]["data"][0]
    assert abs(second_x0 - first_x0 - expected_advance) < 1e-6


@requires_font
def test_alignment_left_is_default_and_unshifted(small_pack):
    shapes_default, _ = compose_text("A", small_pack)
    shapes_left, _ = compose_text("A", small_pack, align="left")
    assert shapes_default == shapes_left


@requires_font
def test_alignment_right_shifts_shorter_line_by_deficit(small_pack):
    n_a = len(compose_text("A", small_pack)[0])

    shapes_left, _ = compose_text("A\nAA", small_pack, align="left")
    shapes_right, _ = compose_text("A\nAA", small_pack, align="right")

    line1_left = shapes_left[:n_a]
    line1_right = shapes_right[:n_a]
    line2_left = shapes_left[n_a:]
    line2_right = shapes_right[n_a:]

    deficits = {round(r["data"][0] - l["data"][0], 6) for l, r in zip(line1_left, line1_right)}
    assert len(deficits) == 1
    deficit = deficits.pop()
    assert deficit > 0

    # The longest line (line 2) needs no shift under right-align.
    for l, r in zip(line2_left, line2_right):
        assert abs(r["data"][0] - l["data"][0]) < 1e-9


@requires_font
def test_alignment_center_shifts_by_half_the_right_align_deficit(small_pack):
    n_a = len(compose_text("A", small_pack)[0])

    shapes_left, _ = compose_text("A\nAA", small_pack, align="left")
    shapes_right, _ = compose_text("A\nAA", small_pack, align="right")
    shapes_center, _ = compose_text("A\nAA", small_pack, align="center")

    right_deficit = shapes_right[0]["data"][0] - shapes_left[0]["data"][0]
    center_deficit = shapes_center[0]["data"][0] - shapes_left[0]["data"][0]
    assert abs(center_deficit - right_deficit / 2.0) < 1e-6


@requires_font
def test_alignment_justify_shifts_only_after_the_space_gap(small_pack):
    n_a = len(compose_text("A", small_pack)[0])

    shapes_left, _ = compose_text("A A\nAAAAA", small_pack, align="left")
    shapes_justify, _ = compose_text("A A\nAAAAA", small_pack, align="justify")

    line1_left = shapes_left[:2 * n_a]
    line1_justify = shapes_justify[:2 * n_a]

    first_a_left = line1_left[:n_a]
    first_a_justify = line1_justify[:n_a]
    second_a_left = line1_left[n_a:]
    second_a_justify = line1_justify[n_a:]

    for l, j in zip(first_a_left, first_a_justify):
        assert abs(j["data"][0] - l["data"][0]) < 1e-9  # token before the only gap: unshifted

    shifts = {round(j["data"][0] - l["data"][0], 6) for l, j in zip(second_a_left, second_a_justify)}
    assert len(shifts) == 1
    assert shifts.pop() > 0  # token after the gap: pushed right to fill the line


@requires_font
def test_alignment_justify_leaves_last_line_unjustified(small_pack):
    shapes_left, _ = compose_text("A A\nAAAAA", small_pack, align="left")
    shapes_justify, _ = compose_text("A A\nAAAAA", small_pack, align="justify")
    n_a = len(compose_text("A", small_pack)[0])
    line2_left = shapes_left[2 * n_a:]
    line2_justify = shapes_justify[2 * n_a:]
    for l, j in zip(line2_left, line2_justify):
        assert abs(j["data"][0] - l["data"][0]) < 1e-9


@requires_font
def test_missing_character_is_warned_not_raised(small_pack):
    shapes, warnings = compose_text("AZ", small_pack)  # 'Z' was never generated into small_pack
    assert any("Z" in w for w in warnings)
    assert len(shapes) == len(compose_text("A", small_pack)[0])  # Z contributed no shapes


@requires_font
def test_invalid_align_raises(small_pack):
    with pytest.raises(ValueError):
        compose_text("A", small_pack, align="diagonal")


def test_stencil_glyph_shapes_stay_contiguous_per_character(tmp_path):
    # Synthetic pack (no font dependency) with one normal glyph and one
    # stencil-strategy glyph (background square + mask cutout) placed
    # adjacent. Mask layers only punch through shapes *below* them in the
    # same layer stack, so cross-glyph mask bleed would require shapes from
    # different glyphs to interleave. compose_text must never do that.
    pack_dir = tmp_path / "SYN"
    (pack_dir / "Uppercase").mkdir(parents=True)

    normal_shape = {"type": 1, "type_word": 1, "data": [0, 0, 1, 1, 0, 0, 0], "color": [255, 255, 255, 255]}
    stencil_bg = {"type": 1, "type_word": 1, "data": [0, 0, 3, 3, 0, 0, 0], "color": [255, 255, 255, 255]}
    stencil_mask = {"type": 1, "type_word": 1, "data": [0, 0, 1, 1, 0, 0, 1], "color": [0, 0, 0, 255], "mask": True}

    (pack_dir / "Uppercase" / "SYN_A.json").write_text(
        json.dumps({"format": "fh6_typecode_json_export_v1", "shapes": [normal_shape]}), encoding="utf-8")
    (pack_dir / "Uppercase" / "SYN_B.json").write_text(
        json.dumps({"format": "fh6_typecode_json_export_v1", "shapes": [stencil_bg, stencil_mask]}),
        encoding="utf-8")

    manifest = {
        "format": "forza_writer_fontpack_v2",
        "font_file": str(AMARILLO_FONT) if AMARILLO_FONT.exists() else "unused.ttf",
        "curve_segments": 8,
        "categories": {
            "Uppercase": [
                {"char": "A", "artifacts": {"json": {"file": "Uppercase/SYN_A.json"}}},
                {"char": "B", "artifacts": {"json": {"file": "Uppercase/SYN_B.json"}}},
            ],
        },
    }
    (pack_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    if not AMARILLO_FONT.exists():
        pytest.skip("test font not present on this machine")

    shapes, warnings = compose_text("AB", pack_dir)
    assert warnings == []
    assert len(shapes) == 3


@requires_font
def test_default_style_reproduces_unstyled_output_exactly(small_pack):
    # style=None (the no-styling default) must be byte-identical to a no-op
    # TextStyle() and to omitting size_scale/line_spacing entirely. Every
    # caller that doesn't opt into styling, including Direct Generator's
    # compose_shaped_lines, depends on this exact equivalence.
    unstyled, warnings_unstyled = compose_text("A B\nAB", small_pack)
    explicit_noop, warnings_noop = compose_text("A B\nAB", small_pack, style=TextStyle())
    assert unstyled == explicit_noop
    assert warnings_unstyled == warnings_noop


@requires_font
def test_size_scale_scales_advance_width(small_pack):
    single, _ = compose_text("A", small_pack)
    doubled, _ = compose_text("A", small_pack, size_scale=2.0)
    assert doubled[0]["data"][2] == pytest.approx(single[0]["data"][2] * 2.0)
    assert doubled[0]["data"][3] == pytest.approx(single[0]["data"][3] * 2.0)

    single_two, _ = compose_text("AA", small_pack)
    doubled_two, _ = compose_text("AA", small_pack, size_scale=2.0)
    n = len(single_two) // 2
    single_advance = single_two[n]["data"][0] - single_two[0]["data"][0]
    doubled_advance = doubled_two[n]["data"][0] - doubled_two[0]["data"][0]
    assert doubled_advance == pytest.approx(single_advance * 2.0)


@requires_font
def test_line_spacing_scales_the_gap_between_lines(small_pack):
    normal, _ = compose_text("A\nA", small_pack)
    n = len(normal) // 2
    normal_gap = normal[n]["data"][1] - normal[0]["data"][1]

    doubled, _ = compose_text("A\nA", small_pack, line_spacing=2.0)
    doubled_gap = doubled[n]["data"][1] - doubled[0]["data"][1]
    assert doubled_gap == pytest.approx(normal_gap * 2.0)


def test_solid_fill_recolors_non_mask_shapes_but_not_mask_shapes(tmp_path):
    # Reuses the stencil-glyph synthetic-pack pattern from
    # test_stencil_glyph_shapes_stay_contiguous_per_character above: one
    # normal glyph and one stencil glyph (background + mask cutout), so the
    # mask shape's color can be checked against the fill color directly.
    if not AMARILLO_FONT.exists():
        pytest.skip("test font not present on this machine")

    pack_dir = tmp_path / "SYNSTYLE"
    (pack_dir / "Uppercase").mkdir(parents=True)

    normal_shape = {"type": 1, "type_word": 1, "data": [0, 0, 1, 1, 0, 0, 0], "color": [255, 255, 255, 255]}
    stencil_bg = {"type": 1, "type_word": 1, "data": [0, 0, 3, 3, 0, 0, 0], "color": [255, 255, 255, 255]}
    stencil_mask = {"type": 1, "type_word": 1, "data": [0, 0, 1, 1, 0, 0, 1], "color": [0, 0, 0, 255], "mask": True}

    (pack_dir / "Uppercase" / "SYN_A.json").write_text(
        json.dumps({"format": "fh6_typecode_json_export_v1", "shapes": [normal_shape]}), encoding="utf-8")
    (pack_dir / "Uppercase" / "SYN_B.json").write_text(
        json.dumps({"format": "fh6_typecode_json_export_v1", "shapes": [stencil_bg, stencil_mask]}),
        encoding="utf-8")

    manifest = {
        "format": "forza_writer_fontpack_v2",
        "font_file": str(AMARILLO_FONT),
        "curve_segments": 8,
        "categories": {
            "Uppercase": [
                {"char": "A", "artifacts": {"json": {"file": "Uppercase/SYN_A.json"}}},
                {"char": "B", "artifacts": {"json": {"file": "Uppercase/SYN_B.json"}}},
            ],
        },
    }
    (pack_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    style = TextStyle(fills=(LineFill(mode="solid", colors=((255, 0, 0, 255),)),))
    shapes, warnings = compose_text("AB", pack_dir, style=style)
    assert warnings == []
    assert len(shapes) == 3

    non_mask = [s for s in shapes if not s.get("mask")]
    mask = [s for s in shapes if s.get("mask")]
    assert len(non_mask) == 2
    assert len(mask) == 1
    assert all(s["color"] == [255, 0, 0, 255] for s in non_mask)
    assert mask[0]["color"] == [0, 0, 0, 255]  # untouched: still the original cutout color


def test_two_lines_get_two_independent_fills(tmp_path):
    # Same synthetic-pack pattern as above, two lines this time: confirms
    # fills are looked up per line (style.fill_for_line) rather than
    # applied uniformly across the whole document.
    if not AMARILLO_FONT.exists():
        pytest.skip("test font not present on this machine")

    pack_dir = tmp_path / "SYNSTYLE2"
    (pack_dir / "Uppercase").mkdir(parents=True)
    normal_shape = {"type": 1, "type_word": 1, "data": [0, 0, 1, 1, 0, 0, 0], "color": [255, 255, 255, 255]}
    (pack_dir / "Uppercase" / "SYN_A.json").write_text(
        json.dumps({"format": "fh6_typecode_json_export_v1", "shapes": [normal_shape]}), encoding="utf-8")
    manifest = {
        "format": "forza_writer_fontpack_v2",
        "font_file": str(AMARILLO_FONT),
        "curve_segments": 8,
        "categories": {"Uppercase": [{"char": "A", "artifacts": {"json": {"file": "Uppercase/SYN_A.json"}}}]},
    }
    (pack_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    style = TextStyle(fills=(
        LineFill(mode="solid", colors=((255, 0, 0, 255),)),
        LineFill(mode="solid", colors=((0, 0, 255, 255),)),
    ))
    shapes, warnings = compose_text("A\nA", pack_dir, style=style)
    assert warnings == []
    assert [s["color"] for s in shapes] == [[255, 0, 0, 255], [0, 0, 255, 255]]
