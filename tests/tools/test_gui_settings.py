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
        "reference_modelbin", "output_dir", "modelbin_output_dir",
        "direct_output_dir", "image_output_dir",
        "palette", "density", "compute_backend",
        "generation_preset", "generation_allowed_shapes", "generation_preferred_shapes",
        "generation_fallback", "generation_allow_exact_cover",
        "image_save_source", "image_save_debug", "image_debug_mode",
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
