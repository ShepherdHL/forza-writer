import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "tools"))
from gen_fontpack import (  # noqa: E402
    build_fontpack, generation_profile_id, glyph_filename, pack_dir_for,
    resolve_requested_chars)

# No font ships in this repo (same policy as the reference .modelbin, see
# README.md), so font-dependent tests reuse this repo's verification font
# and skip gracefully where it isn't present, rather than requiring one.
AMARILLO_FONT = Path.home() / "Desktop" / "amarillo-usaf" / "amarurgt.ttf"
requires_font = pytest.mark.skipif(not AMARILLO_FONT.exists(), reason="test font not present on this machine")

# Amarillo USAF never wins with stencil, so a font whose stencil savings are
# real is needed to prove allow_stencil genuinely changes the result, not
# just that the parameter is threaded.
SGA_FONT = Path.home() / "AppData" / "Local" / "Microsoft" / "Windows" / "Fonts" / "minecraft-standard-galactic-alphabet.otf"
requires_sga_font = pytest.mark.skipif(not SGA_FONT.exists(), reason="Standard Galactic Alphabet font not present on this machine")


def test_glyph_filename_ascii_alnum_uses_char_filename_convention():
    assert glyph_filename("PFX", "A") == "PFX_A.modelbin"
    assert glyph_filename("PFX", "a") == "PFX_a_lc.modelbin"


def test_glyph_filename_symbol_uses_codepoint():
    assert glyph_filename("PFX", "-") == "PFX_U+002D.modelbin"


def test_glyph_filename_respects_extension():
    assert glyph_filename("PFX", "A", "json") == "PFX_A.json"
    assert glyph_filename("PFX", "-", "json") == "PFX_U+002D.json"


def test_generation_profile_identifies_backend_and_curve_smoothness():
    assert generation_profile_id("json", 1, "cuda") == "JSON-CUDA-CS1"
    assert generation_profile_id("json", 8, "cpu") == "JSON-CPU-CS8"
    assert generation_profile_id("json_legacy", 32, "cpu") == "JSON-LEGACY-CPU"
    assert pack_dir_for(Path("out"), "NOTO-SANS-JP", "json", 1, "cuda") == (
        Path("out/NOTO-SANS-JP/JSON-CUDA-CS1"))


def _fake_cjk_charset(_font_path):
    # A stand-in for a CJK font's cmap: bounded Latin buckets plus a large
    # Han-heavy Letters bucket, kept distinct from Symbols so a Han-heavy
    # font's ideographs aren't miscategorized as symbols.
    han = [chr(0x4E00 + i) for i in range(2000)]
    return ({'Uppercase': list('AB'), 'Lowercase': list('ab'), 'Letters': han,
             'Numbers': list('01'), 'Punctuation': list('.,'), 'Symbols': list('$%')}, [])


def test_resolve_requested_chars_returns_none_when_no_scoping_flag_given():
    # None means "the font's entire cmap": build_fontpack's own existing
    # default, unchanged for anyone not using the scoping flags.
    assert resolve_requested_chars(Path('font.ttf'), None, None, None, False) is None


def test_resolve_requested_chars_chars_flag_strips_whitespace():
    result = resolve_requested_chars(Path('font.ttf'), 'A B\tc', None, None, False)
    assert result == {'A', 'B', 'c'}


def test_resolve_requested_chars_script_uses_bounded_curated_set(monkeypatch):
    import gen_fontpack
    monkeypatch.setattr(gen_fontpack, 'charset_from_font', _fake_cjk_charset)

    result = resolve_requested_chars(Path('font.ttf'), None, ['Cyrillic'], None, False)

    assert result == set('АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдеёжзийклмнопрстуфхцчшщъыьэюя')


def test_resolve_requested_chars_chinese_script_is_bounded_not_full_han(monkeypatch):
    import gen_fontpack
    monkeypatch.setattr(gen_fontpack, 'charset_from_font', _fake_cjk_charset)

    result = resolve_requested_chars(Path('font.ttf'), None, ['Traditional Chinese'], None, False)

    # Bounded test/scoping set, nowhere near the font's 2,000 fake Han glyphs.
    assert 0 < len(result) < 200


def test_resolve_requested_chars_category_pulls_from_the_actual_font(monkeypatch):
    import gen_fontpack
    monkeypatch.setattr(gen_fontpack, 'charset_from_font', _fake_cjk_charset)

    result = resolve_requested_chars(Path('font.ttf'), None, None, ['Uppercase', 'Numbers'], False)

    assert result == {'A', 'B', '0', '1'}


def test_resolve_requested_chars_all_han_is_unbounded_and_opt_in(monkeypatch):
    import gen_fontpack
    monkeypatch.setattr(gen_fontpack, 'charset_from_font', _fake_cjk_charset)

    without_han = resolve_requested_chars(Path('font.ttf'), None, None, ['Uppercase'], False)
    with_han = resolve_requested_chars(Path('font.ttf'), None, None, ['Uppercase'], True)

    assert without_han == {'A', 'B'}
    assert len(with_han) == 2002  # 'A', 'B' plus the full 2,000-char fake Han set


def test_resolve_requested_chars_is_additive_across_every_flag(monkeypatch):
    import gen_fontpack
    monkeypatch.setattr(gen_fontpack, 'charset_from_font', _fake_cjk_charset)

    result = resolve_requested_chars(Path('font.ttf'), 'Z', ['Cyrillic'], ['Numbers'], False)

    assert 'Z' in result and '0' in result and 'А' in result


@requires_font
def test_manifest_records_variable_font_source_and_coordinates(tmp_path, monkeypatch):
    import gen_fontpack
    monkeypatch.setattr(gen_fontpack, 'fit_glyph_with_strategy',
                        lambda *args, **kwargs: ([], 'primitive_search'))
    variation = {'named_instance': 'Regular', 'coordinates': {'wght': 400}}

    manifest = build_fontpack(
        AMARILLO_FONT, tmp_path, 'VARIABLE-META', output='json', chars={'A'},
        compute_backend='cpu', verify_quality=False, source_font_path=Path('source-variable.ttf'),
        variation=variation, log=lambda *_: None)

    assert manifest['font_file'] == str(AMARILLO_FONT)
    assert manifest['source_font_file'] == 'source-variable.ttf'
    assert manifest['variation'] == variation


def test_build_fontpack_rejects_bad_output_mode(tmp_path):
    with pytest.raises(ValueError):
        build_fontpack(AMARILLO_FONT, tmp_path, "X", output="bogus")


def test_build_fontpack_modelbin_requires_reference(tmp_path):
    with pytest.raises(ValueError):
        build_fontpack(AMARILLO_FONT, tmp_path, "X", output="modelbin", reference_modelbin=None)


@requires_font
def test_profiled_cpu_and_cuda_runs_do_not_overwrite_each_other(tmp_path, monkeypatch):
    import gen_fontpack
    from forza_writer.compute_backend import BackendInfo

    monkeypatch.setattr(
        gen_fontpack, "resolve_backend",
        lambda requested: BackendInfo(requested, requested, True, requested.upper(), "test"))
    monkeypatch.setattr(
        gen_fontpack, "fit_glyph_with_strategy",
        lambda *args, **kwargs: ([], "primitive_search"))

    cpu = build_fontpack(
        AMARILLO_FONT, tmp_path, "NOTO", output="json", chars={"A"},
        compute_backend="cpu", verify_quality=False, log=lambda *_: None)
    cuda = build_fontpack(
        AMARILLO_FONT, tmp_path, "NOTO", output="json", chars={"A"},
        compute_backend="cuda", verify_quality=False, log=lambda *_: None)

    assert cpu["pack_id"] == "NOTO__JSON-CPU-CS8"
    assert cuda["pack_id"] == "NOTO__JSON-CUDA-CS8"
    assert (pack_dir_for(tmp_path, "NOTO", "json", 8, "cpu") / "manifest.json").exists()
    assert (pack_dir_for(tmp_path, "NOTO", "json", 8, "cuda") / "manifest.json").exists()


@requires_font
def test_build_fontpack_json_only_needs_no_reference_modelbin(tmp_path):
    manifest = build_fontpack(AMARILLO_FONT, tmp_path, "TESTFONT", output="json", log=lambda *_: None)
    assert manifest["format"] == "forza_writer_fontpack_v2"
    assert manifest["reference_modelbin"] is None


@requires_font
def test_manifest_records_strategy_per_glyph(tmp_path):
    manifest = build_fontpack(AMARILLO_FONT, tmp_path, "TESTFONT", output="json",
                               chars={"A"}, log=lambda *_: None)
    entry = manifest["categories"]["Uppercase"][0]
    assert entry["char"] == "A"
    assert entry["artifacts"]["json"]["strategy"] in ("rect_decompose", "stencil", "primitive_search")
    # Amarillo's own glyphs never win with stencil, so no glyph in this pack
    # should trip the experimental flag.
    assert "experimental" not in manifest


@requires_font
def test_manifest_flags_experimental_when_stencil_is_used(tmp_path, monkeypatch):
    import gen_fontpack

    def fake_fit_glyph_with_strategy(char, font_path, curve_segments, mask_mode="auto", compute_backend="cpu", **kwargs):
        return [{"type": 1, "type_word": 1, "data": [0, 0, 1, 1, 0, 0, 0], "color": [255, 255, 255, 255]}], "stencil"

    monkeypatch.setattr(gen_fontpack, "fit_glyph_with_strategy", fake_fit_glyph_with_strategy)
    manifest = build_fontpack(AMARILLO_FONT, tmp_path, "TESTFONT", output="json",
                               chars={"A"}, log=lambda *_: None)
    assert "experimental" in manifest
    assert "stencil" in manifest["experimental"]
    assert manifest["summary"]["json"]["generated"] > 0
    assert manifest["summary"]["json"]["failed"] == 0
    assert "modelbin" not in manifest["summary"]

    upper_a = next(e for e in manifest["categories"]["Uppercase"] if e["char"] == "A")
    assert "json" in upper_a["artifacts"]
    assert "modelbin" not in upper_a["artifacts"]
    import gen_fontpack
    backend = gen_fontpack.resolve_backend("auto")
    json_path = pack_dir_for(tmp_path, "TESTFONT", "json", 8, backend.resolved) / upper_a["artifacts"]["json"]["file"]
    assert json_path.exists()


@requires_font
def test_build_fontpack_json_failure_does_not_abort_batch(tmp_path, monkeypatch):
    import gen_fontpack

    real_fit_glyph_with_strategy = gen_fontpack.fit_glyph_with_strategy
    calls = []

    def flaky_fit_glyph_with_strategy(char, font_path, curve_segments, mask_mode="auto", compute_backend="cpu", **kwargs):
        calls.append(char)
        if char == "B":
            raise RuntimeError("simulated failure")
        return real_fit_glyph_with_strategy(
            char, font_path, curve_segments, mask_mode=mask_mode, compute_backend=compute_backend)

    monkeypatch.setattr(gen_fontpack, "fit_glyph_with_strategy", flaky_fit_glyph_with_strategy)
    manifest = build_fontpack(AMARILLO_FONT, tmp_path, "TESTFONT", output="json", log=lambda *_: None)

    entries = {e["char"]: e for e in manifest["categories"]["Uppercase"]}
    assert entries["B"]["artifacts"]["json"]["file"] is None
    assert "simulated failure" in entries["B"]["artifacts"]["json"]["message"]
    # every other letter still generated despite B's failure
    assert entries["A"]["artifacts"]["json"]["file"] is not None
    assert entries["C"]["artifacts"]["json"]["file"] is not None
    assert manifest["summary"]["json"]["failed"] == 1


@requires_font
def test_should_stop_halts_after_requested_glyph_count(tmp_path):
    seen = []

    def should_stop():
        return len(seen) >= 3

    manifest = build_fontpack(AMARILLO_FONT, tmp_path, "HALTTEST", output="json",
                               chars={"A", "B", "C", "D", "E"},
                               should_stop=should_stop, on_glyph=lambda cat, entry: seen.append(entry["char"]),
                               log=lambda *_: None)

    assert manifest["halted"] is True
    assert seen == ["A", "B", "C"]
    assert [e["char"] for e in manifest["categories"]["Uppercase"]] == ["A", "B", "C"]
    assert manifest["summary"]["by_category"]["Lowercase"] == 0  # never reached, must not KeyError


@requires_font
def test_should_stop_false_never_halts(tmp_path):
    manifest = build_fontpack(AMARILLO_FONT, tmp_path, "NOHALT", output="json",
                               chars={"A"}, should_stop=lambda: False, log=lambda *_: None)
    assert "halted" not in manifest


@requires_font
def test_on_glyph_called_once_per_glyph_with_category_and_entry(tmp_path):
    calls = []
    build_fontpack(AMARILLO_FONT, tmp_path, "ONGLYPH", output="json", chars={"A", "B"},
                    on_glyph=lambda category, entry: calls.append((category, entry["char"])),
                    log=lambda *_: None)
    assert calls == [("Uppercase", "A"), ("Uppercase", "B")]


@requires_font
def test_files_written_tracks_every_artifact_this_run(tmp_path):
    manifest = build_fontpack(AMARILLO_FONT, tmp_path, "FILESTEST", output="json",
                               chars={"A", "B"}, log=lambda *_: None)
    assert {"Uppercase/FILESTEST_A.json", "Uppercase/FILESTEST_B.json"} <= set(
        manifest["files_written"])
    # Review overlays are artifacts of this run too and must be removable
    # by Abort alongside the glyph JSON files.
    assert all(path.endswith((".json", "_diff.png")) for path in manifest["files_written"])
    import gen_fontpack
    backend = gen_fontpack.resolve_backend("auto")
    pack_dir = pack_dir_for(tmp_path, "FILESTEST", "json", 8, backend.resolved)
    for rel in manifest["files_written"]:
        assert (pack_dir / rel).exists()


@requires_font
def test_json_legacy_output_uses_legacy_primitive_strategy(tmp_path):
    manifest = build_fontpack(AMARILLO_FONT, tmp_path, "LEGACYTEST", output="json_legacy",
                               chars={"A"}, log=lambda *_: None)
    assert manifest["output"] == "json_legacy"
    entry = manifest["categories"]["Uppercase"][0]
    assert entry["char"] == "A"
    assert entry["artifacts"]["json"]["strategy"] == "legacy_primitive"
    assert entry["artifacts"]["json"]["file"] is not None
    # Shares the same "json" summary key as the modern json path: this is
    # what keeps the GUI's summary-line formatting working unmodified for
    # both json strategies.
    assert manifest["summary"]["json"]["generated"] == 1
    assert manifest["summary"]["json"]["failed"] == 0
    json_path = pack_dir_for(tmp_path, "LEGACYTEST", "json_legacy", 8, "cpu") / entry["artifacts"]["json"]["file"]
    assert json_path.exists()


@requires_font
def test_allow_stencil_false_maps_to_never_mode_in_fit_glyph_with_strategy(tmp_path, monkeypatch):
    import gen_fontpack

    seen = []
    real = gen_fontpack.fit_glyph_with_strategy

    def spy(char, font_path, curve_segments, mask_mode="auto", compute_backend="cpu", **kwargs):
        seen.append(mask_mode)
        return real(char, font_path, curve_segments, mask_mode=mask_mode, compute_backend=compute_backend)

    monkeypatch.setattr(gen_fontpack, "fit_glyph_with_strategy", spy)
    build_fontpack(AMARILLO_FONT, tmp_path, "TESTFONT", output="json", chars={"A"},
                    allow_stencil=False, log=lambda *_: None)
    assert seen == ["never"]


@requires_font
def test_mask_overrides_takes_precedence_over_allow_stencil(tmp_path, monkeypatch):
    import gen_fontpack

    seen = {}
    real = gen_fontpack.fit_glyph_with_strategy

    def spy(char, font_path, curve_segments, mask_mode="auto", compute_backend="cpu", **kwargs):
        seen[char] = mask_mode
        return real(char, font_path, curve_segments, mask_mode=mask_mode, compute_backend=compute_backend)

    monkeypatch.setattr(gen_fontpack, "fit_glyph_with_strategy", spy)
    build_fontpack(AMARILLO_FONT, tmp_path, "TESTFONT", output="json", chars={"A", "B"},
                    allow_stencil=True, mask_overrides={"A": "never"}, log=lambda *_: None)
    assert seen["A"] == "never"  # overridden
    assert seen["B"] == "auto"   # falls back to allow_stencil's default


# --- manual_assignments (Configurator's per-glyph "assign a file") --------

def _write_manual_glyph_json(path, mask=False):
    import json
    path.write_text(json.dumps({"shapes": [
        {"type": 1, "type_word": 1, "data": [1, 2, 1, 1, 30, 0, 0], "color": [10, 20, 30, 255], "mask": False},
        *([{"type": 1, "type_word": 1, "data": [0, 0, 1, 1, 0, 0, 1], "color": [0, 0, 0, 255], "mask": True}]
          if mask else []),
    ]}), encoding="utf-8")
    return path


@requires_font
def test_manual_assignment_copies_source_shapes_verbatim_with_manual_strategy(tmp_path):
    source = _write_manual_glyph_json(tmp_path / "custom_A.json", mask=True)
    manifest = build_fontpack(AMARILLO_FONT, tmp_path / "out", "MANUALTEST", output="json",
                               chars={"A"}, manual_assignments={"A": source}, log=lambda *_: None)

    entry = next(e for e in manifest["categories"]["Uppercase"] if e["char"] == "A")
    artifact = entry["artifacts"]["json"]
    assert artifact["strategy"] == "manual"
    assert artifact["shape_count"] == 2

    import json
    import gen_fontpack
    backend = gen_fontpack.resolve_backend("auto")
    out_path = pack_dir_for(tmp_path / "out", "MANUALTEST", "json", 8, backend.resolved) / artifact["file"]
    written = json.loads(out_path.read_text(encoding="utf-8"))
    source_shapes = json.loads(source.read_text(encoding="utf-8"))["shapes"]
    assert written["shapes"] == source_shapes


@requires_font
def test_manual_assignment_takes_precedence_over_mask_overrides(tmp_path, monkeypatch):
    import gen_fontpack

    source = _write_manual_glyph_json(tmp_path / "custom_A.json")
    called = []
    real = gen_fontpack.fit_glyph_with_strategy

    def spy(char, font_path, curve_segments, mask_mode="auto", compute_backend="cpu", **kwargs):
        called.append(char)
        return real(char, font_path, curve_segments, mask_mode=mask_mode, compute_backend=compute_backend)

    monkeypatch.setattr(gen_fontpack, "fit_glyph_with_strategy", spy)
    manifest = build_fontpack(AMARILLO_FONT, tmp_path / "out", "MANUALPRECEDENCE", output="json",
                               chars={"A", "B"}, mask_overrides={"A": "force"},
                               manual_assignments={"A": source}, log=lambda *_: None)

    # fit_glyph_with_strategy (auto-fit) must never run for the manually
    # assigned char, only for the untouched one.
    assert called == ["B"]
    entries = {e["char"]: e for e in manifest["categories"]["Uppercase"]}
    assert entries["A"]["artifacts"]["json"]["strategy"] == "manual"
    assert entries["B"]["artifacts"]["json"]["strategy"] != "manual"


@requires_font
def test_manual_assignments_ignored_and_warned_for_non_json_output(tmp_path):
    logs = []
    source = _write_manual_glyph_json(tmp_path / "custom_A.json")
    build_fontpack(AMARILLO_FONT, tmp_path / "out", "MANUALLEGACY", output="json_legacy",
                    chars={"A"}, manual_assignments={"A": source}, log=logs.append)

    assert any("manual_assignments" in line and "json_legacy" in line for line in logs)


@requires_font
def test_manual_assignment_missing_source_file_is_recorded_as_a_failure(tmp_path):
    manifest = build_fontpack(AMARILLO_FONT, tmp_path / "out", "MANUALMISSING", output="json",
                               chars={"A"}, manual_assignments={"A": tmp_path / "does_not_exist.json"},
                               log=lambda *_: None)
    entry = next(e for e in manifest["categories"]["Uppercase"] if e["char"] == "A")
    assert entry["artifacts"]["json"]["file"] is None
    assert manifest["summary"]["json"]["failed"] == 1


@requires_sga_font
def test_allow_stencil_false_forces_direct_fill_on_a_real_font(tmp_path):
    # 'X' on this font genuinely needs fewer shapes as a stencil (10 vs 14
    # direct); allow_stencil=False must still force direct fill despite
    # that, not just pass the flag through without effect.
    manifest = build_fontpack(SGA_FONT, tmp_path, "SGATEST", output="json", chars={"X"},
                               allow_stencil=False, log=lambda *_: None)
    entry = next(e for e in manifest["categories"]["Uppercase"] if e["char"] == "X")
    assert entry["artifacts"]["json"]["strategy"] == "rect_decompose"
    assert "experimental" not in manifest


@requires_sga_font
def test_allow_stencil_true_lets_stencil_win_on_a_real_font(tmp_path):
    manifest = build_fontpack(SGA_FONT, tmp_path, "SGATEST2", output="json", chars={"X"},
                               allow_stencil=True, log=lambda *_: None)
    entry = next(e for e in manifest["categories"]["Uppercase"] if e["char"] == "X")
    assert entry["artifacts"]["json"]["strategy"] == "stencil"
    assert "experimental" in manifest


def test_output_modes_no_longer_includes_both():
    import gen_fontpack
    assert gen_fontpack.OUTPUT_MODES == ("modelbin", "json", "json_legacy")


@requires_font
def test_default_should_stop_and_on_glyph_are_safe_noops(tmp_path):
    # The CLI path never passes these; they must work with zero extra arguments.
    manifest = build_fontpack(AMARILLO_FONT, tmp_path, "DEFAULTS", output="json",
                               chars={"A"}, log=lambda *_: None)
    assert "halted" not in manifest
    assert manifest["files_written"][0] == "Uppercase/DEFAULTS_A.json"
    assert all(path.endswith((".json", "_diff.png")) for path in manifest["files_written"])


# -- color_mode / solid_color / high_contrast_seed --------------------------

def _glyph_shapes(tmp_path, manifest, category, char):
    import json as jsonlib
    entry = next(e for e in manifest["categories"][category] if e["char"] == char)
    pack_dir = pack_dir_for(tmp_path, manifest["prefix"], "json", manifest["curve_segments"],
                             manifest["generation_profile"]["compute_backend"])
    data = jsonlib.loads((pack_dir / entry["artifacts"]["json"]["file"]).read_text(encoding="utf-8"))
    return data["shapes"]


@requires_font
def test_default_color_mode_is_solid_white_and_recorded_in_manifest(tmp_path):
    manifest = build_fontpack(AMARILLO_FONT, tmp_path, "SOLIDDEF", output="json",
                               chars={"A"}, log=lambda *_: None)
    assert manifest["color_mode"] == "solid"
    assert manifest["color_seed"] is None
    shapes = _glyph_shapes(tmp_path, manifest, "Uppercase", "A")
    assert all(tuple(s["color"]) == (255, 255, 255, 255) for s in shapes if not s.get("mask"))


@requires_font
def test_custom_solid_color_applies_to_every_shape_and_export_matches(tmp_path):
    manifest = build_fontpack(AMARILLO_FONT, tmp_path, "SOLIDCUSTOM", output="json",
                               chars={"A"}, log=lambda *_: None,
                               color_mode="solid", solid_color=(10, 20, 30, 255))
    assert manifest["color_mode"] == "solid"
    shapes = _glyph_shapes(tmp_path, manifest, "Uppercase", "A")
    assert shapes  # sanity: this glyph actually produced shapes
    assert all(tuple(s["color"]) == (10, 20, 30, 255) for s in shapes if not s.get("mask"))


@requires_font
def test_high_contrast_mode_gives_adjacent_shapes_distinct_colors(tmp_path):
    manifest = build_fontpack(AMARILLO_FONT, tmp_path, "HICONTRAST", output="json",
                               chars={"A"}, log=lambda *_: None,
                               color_mode="high_contrast", high_contrast_seed=99)
    assert manifest["color_mode"] == "high_contrast"
    assert manifest["color_seed"] == 99
    shapes = [s for s in _glyph_shapes(tmp_path, manifest, "Uppercase", "A") if not s.get("mask")]
    assert len(shapes) >= 2  # otherwise "adjacent shapes differ" is vacuous
    colors = [tuple(s["color"]) for s in shapes]
    assert len(set(colors)) == len(colors), "every shape in this small glyph should be a distinct color"


@requires_font
def test_high_contrast_regeneration_with_same_seed_is_byte_identical(tmp_path):
    first = build_fontpack(AMARILLO_FONT, tmp_path / "run1", "HC", output="json",
                            chars={"A", "B"}, log=lambda *_: None,
                            color_mode="high_contrast", high_contrast_seed=1234)
    second = build_fontpack(AMARILLO_FONT, tmp_path / "run2", "HC", output="json",
                             chars={"A", "B"}, log=lambda *_: None,
                             color_mode="high_contrast", high_contrast_seed=1234)
    for char in ("A", "B"):
        colors1 = [tuple(s["color"]) for s in _glyph_shapes(tmp_path / "run1", first, "Uppercase", char)]
        colors2 = [tuple(s["color"]) for s in _glyph_shapes(tmp_path / "run2", second, "Uppercase", char)]
        assert colors1 == colors2


@requires_font
def test_high_contrast_preview_and_export_use_the_same_assignment(tmp_path):
    """The shapes written to disk (export) and the shapes fit_glyph_with_
    strategy returns in-process (what a live preview renders from) are the
    exact same call -- this pins that there's only one code path, not a
    preview-only and an export-only version that could drift apart."""
    import gen_fontpack
    from forza_writer.primitive_fit import fit_glyph_with_strategy
    from forza_writer.high_contrast import seed_for_char

    manifest = build_fontpack(AMARILLO_FONT, tmp_path, "AGREE", output="json",
                               chars={"A"}, log=lambda *_: None,
                               color_mode="high_contrast", high_contrast_seed=55)
    exported = [tuple(s["color"]) for s in _glyph_shapes(tmp_path, manifest, "Uppercase", "A")]

    preview_shapes, _strategy = fit_glyph_with_strategy(
        "A", AMARILLO_FONT, high_contrast_seed=seed_for_char(55, "A"))
    preview = [tuple(s["color"]) for s in preview_shapes]
    assert preview == exported


@requires_font
def test_mask_shapes_keep_mask_color_even_in_high_contrast_mode(tmp_path, monkeypatch):
    """A mask shape is a transparency cutout, never actually drawn -- high
    contrast coloring must never touch it, in export or preview."""
    from forza_writer.primitive_fit import PlacedShape, placements_to_shapes

    placements = [
        PlacedShape(shape_id="square", cx=10.0, cy=10.0, scale_x=1.0, scale_y=1.0,
                    rotation_deg=0.0, is_mask=True),
        PlacedShape(shape_id="square", cx=50.0, cy=50.0, scale_x=1.0, scale_y=1.0,
                    rotation_deg=0.0, is_mask=False),
    ]
    shapes = placements_to_shapes(placements, resolution=64, high_contrast_seed=7)
    assert shapes[0]["mask"] is True
    assert tuple(shapes[0]["color"]) == (0, 0, 0, 255)
    assert shapes[1]["mask"] is False
    assert tuple(shapes[1]["color"]) != (0, 0, 0, 255)
