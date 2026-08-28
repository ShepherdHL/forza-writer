import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "tools"))
import gui_settings  # noqa: E402


def test_load_settings_returns_defaults_when_no_file_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(gui_settings, "SETTINGS_PATH", tmp_path / "does-not-exist" / "settings.json")
    assert gui_settings.load_settings() == gui_settings.DEFAULT_SETTINGS


def test_save_then_load_round_trips(tmp_path, monkeypatch):
    path = tmp_path / "nested" / "settings.json"
    monkeypatch.setattr(gui_settings, "SETTINGS_PATH", path)
    monkeypatch.setattr(gui_settings, "SETTINGS_DIR", path.parent)

    gui_settings.save_settings({"reference_modelbin": r"C:\custom\ref.modelbin", "output_dir": r"D:\packs",
                                "modelbin_output_dir": r"D:\modelbin",
                                "direct_output_dir": r"D:\direct",
                                "palette": "slate", "density": "spacious"})
    loaded = gui_settings.load_settings()
    assert loaded["reference_modelbin"] == r"C:\custom\ref.modelbin"
    assert loaded["output_dir"] == r"D:\packs"
    assert loaded["modelbin_output_dir"] == r"D:\modelbin"
    assert loaded["direct_output_dir"] == r"D:\direct"
    assert loaded["palette"] == "slate"
    assert loaded["density"] == "spacious"


def test_load_migrates_old_defaults_without_changing_custom_paths(tmp_path, monkeypatch):
    import json

    path = tmp_path / "settings.json"
    monkeypatch.setattr(gui_settings, "SETTINGS_PATH", path)
    monkeypatch.setattr(gui_settings, "SETTINGS_DIR", path.parent)
    path.write_text(json.dumps({
        "reference_modelbin": "data/S_01.modelbin",
        "direct_output_dir": r"data\dgen",
        "output_dir": r"D:\custom-packs",
    }), encoding="utf-8")

    loaded = gui_settings.load_settings()

    assert loaded["reference_modelbin"] == "user-assets/S_01.modelbin"
    assert loaded["direct_output_dir"] == "data/direct"
    assert loaded["output_dir"] == r"D:\custom-packs"


def test_save_creates_parent_directory(tmp_path, monkeypatch):
    path = tmp_path / "a" / "b" / "c" / "settings.json"
    monkeypatch.setattr(gui_settings, "SETTINGS_PATH", path)
    monkeypatch.setattr(gui_settings, "SETTINGS_DIR", path.parent)

    gui_settings.save_settings({"reference_modelbin": "x"})
    assert path.exists()


def test_load_settings_falls_back_on_corrupt_file(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    path.write_text("not valid json {{{", encoding="utf-8")
    monkeypatch.setattr(gui_settings, "SETTINGS_PATH", path)
    assert gui_settings.load_settings() == gui_settings.DEFAULT_SETTINGS


def test_load_settings_ignores_unknown_keys():
    # DEFAULT_SETTINGS itself defines the known-key set; save_settings must
    # not silently persist arbitrary extra keys a future caller might pass.
    assert set(gui_settings.DEFAULT_SETTINGS.keys()) == {
        "reference_modelbin", "kfps_executable", "output_dir", "modelbin_output_dir",
        "direct_output_dir", "image_output_dir",
        "palette", "density", "compute_backend",
        "generation_preset", "generation_allowed_shapes", "generation_preferred_shapes",
        "generation_fallback", "generation_allow_exact_cover",
        "image_save_source", "image_save_debug", "image_debug_mode",
        "window_geometry", "window_maximized",
        "saved_colors", "recent_colors", "color_ascii_art", "color_forza_font_text",
        "color_generator", "color_advanced", "color_direct",
    }


def test_invalid_enum_values_fall_back_to_defaults(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    path.write_text(
        '{"palette": "neon", "density": "enormous", "compute_backend": "quantum"}',
        encoding="utf-8")
    monkeypatch.setattr(gui_settings, "SETTINGS_PATH", path)
    loaded = gui_settings.load_settings()
    assert loaded["palette"] == "charcoal"
    assert loaded["density"] == "balanced"
    assert loaded["compute_backend"] == "auto"


def test_save_settings_drops_unknown_keys(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr(gui_settings, "SETTINGS_PATH", path)
    monkeypatch.setattr(gui_settings, "SETTINGS_DIR", path.parent)

    gui_settings.save_settings({"reference_modelbin": "x", "bogus_key": "y"})
    import json
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert "bogus_key" not in on_disk


def test_load_settings_ignores_unknown_keys_from_disk(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    path.write_text('{"reference_modelbin": "x", "bogus_key": "y"}', encoding="utf-8")
    monkeypatch.setattr(gui_settings, "SETTINGS_PATH", path)
    loaded = gui_settings.load_settings()
    assert "bogus_key" not in loaded
    assert loaded["reference_modelbin"] == "x"
    assert loaded["output_dir"] == gui_settings.DEFAULT_SETTINGS["output_dir"]


def test_saved_and_recent_colors_round_trip(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr(gui_settings, "SETTINGS_PATH", path)
    monkeypatch.setattr(gui_settings, "SETTINGS_DIR", path.parent)

    gui_settings.save_settings({
        "saved_colors": {"Team Red": [200, 20, 20, 255]},
        "recent_colors": [[1, 2, 3, 255], [4, 5, 6, 255]],
        "color_ascii_art": [10, 20, 30, 255],
    })
    loaded = gui_settings.load_settings()
    assert loaded["saved_colors"] == {"Team Red": [200, 20, 20, 255]}
    assert loaded["recent_colors"] == [[1, 2, 3, 255], [4, 5, 6, 255]]
    assert loaded["color_ascii_art"] == [10, 20, 30, 255]


def test_malformed_color_values_fall_back_to_defaults(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr(gui_settings, "SETTINGS_PATH", path)
    monkeypatch.setattr(gui_settings, "SETTINGS_DIR", path.parent)

    gui_settings.save_settings({
        "saved_colors": {"Bad": [999, 0, 0, 0], "": [1, 2, 3, 4], 5: [1, 2, 3, 4]},
        "recent_colors": [[1, 2, 3], "not-a-color", [300, 0, 0, 0], [1, 2, 3, 4]],
        "color_forza_font_text": "not-a-color",
    })
    loaded = gui_settings.load_settings()
    assert loaded["saved_colors"] == {}
    assert loaded["recent_colors"] == [[1, 2, 3, 4]]
    assert loaded["color_forza_font_text"] == gui_settings.DEFAULT_SETTINGS["color_forza_font_text"]


def test_recent_colors_capped_at_max(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr(gui_settings, "SETTINGS_PATH", path)
    monkeypatch.setattr(gui_settings, "SETTINGS_DIR", path.parent)

    many = [[i, i, i, 255] for i in range(gui_settings.MAX_RECENT_COLORS + 5)]
    gui_settings.save_settings({"recent_colors": many})
    loaded = gui_settings.load_settings()
    assert len(loaded["recent_colors"]) == gui_settings.MAX_RECENT_COLORS


def test_update_settings_preserves_other_fields(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr(gui_settings, "SETTINGS_PATH", path)
    monkeypatch.setattr(gui_settings, "SETTINGS_DIR", path.parent)

    gui_settings.save_settings({"output_dir": r"D:\packs", "window_maximized": False})
    result = gui_settings.update_settings({"color_ascii_art": [1, 2, 3, 4]})
    assert result["output_dir"] == r"D:\packs"
    assert result["window_maximized"] is False
    assert result["color_ascii_art"] == [1, 2, 3, 4]

    reloaded = gui_settings.load_settings()
    assert reloaded["output_dir"] == r"D:\packs"
    assert reloaded["window_maximized"] is False
    assert reloaded["color_ascii_art"] == [1, 2, 3, 4]
