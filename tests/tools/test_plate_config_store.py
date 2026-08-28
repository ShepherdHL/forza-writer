"""Tests for tools/plate_config_store.py: one-file-per-named-config
save/load/list/delete, matching layer_effect_presets_store.py's pattern."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "tools"))
import plate_config_store  # noqa: E402

from forza_writer.plates.instance import PlateInstance  # noqa: E402


def _instance(template_id="gb-current-standard", text="AB12 CDE"):
    return PlateInstance(template_id=template_id, mode="authentic",
                          field_values={"registration": text})


def test_list_plate_configs_empty_when_dir_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(plate_config_store, "CONFIGS_DIR", tmp_path / "does-not-exist")
    assert plate_config_store.list_plate_configs() == []


def test_save_then_load_round_trips(tmp_path, monkeypatch):
    monkeypatch.setattr(plate_config_store, "CONFIGS_DIR", tmp_path)
    instance = _instance()
    plate_config_store.save_plate_config("My UK Plate", instance)

    loaded = plate_config_store.load_plate_config("My UK Plate")
    assert loaded == instance


def test_load_nonexistent_config_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(plate_config_store, "CONFIGS_DIR", tmp_path)
    assert plate_config_store.load_plate_config("nonexistent") is None


def test_load_corrupt_file_returns_none_not_raise(tmp_path, monkeypatch):
    monkeypatch.setattr(plate_config_store, "CONFIGS_DIR", tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "broken.json").write_text("{not valid json", encoding="utf-8")
    assert plate_config_store.load_plate_config("broken") is None


def test_list_plate_configs_sorted_case_insensitively(tmp_path, monkeypatch):
    monkeypatch.setattr(plate_config_store, "CONFIGS_DIR", tmp_path)
    plate_config_store.save_plate_config("zebra", _instance())
    plate_config_store.save_plate_config("Apple", _instance())
    assert plate_config_store.list_plate_configs() == ["Apple", "zebra"]


def test_delete_plate_config(tmp_path, monkeypatch):
    monkeypatch.setattr(plate_config_store, "CONFIGS_DIR", tmp_path)
    plate_config_store.save_plate_config("temp", _instance())
    assert plate_config_store.delete_plate_config("temp") is True
    assert plate_config_store.load_plate_config("temp") is None
    assert plate_config_store.delete_plate_config("temp") is False


def test_unicode_config_name_does_not_collapse_to_empty_or_collide(tmp_path, monkeypatch):
    """A config named after a Japanese template's own name must not
    sanitize down to an empty/generic filename the way an ASCII-only
    sanitizer (layer_effect_presets_store.py's) would."""
    monkeypatch.setattr(plate_config_store, "CONFIGS_DIR", tmp_path)
    plate_config_store.save_plate_config("品川ナンバー", _instance(template_id="jp-private-passenger-current"))
    plate_config_store.save_plate_config("横浜ナンバー", _instance(template_id="jp-private-passenger-current"))

    names = plate_config_store.list_plate_configs()
    assert set(names) == {"品川ナンバー", "横浜ナンバー"}
    assert plate_config_store.load_plate_config("品川ナンバー").template_id == "jp-private-passenger-current"


def test_save_overwrites_existing_config_of_same_name(tmp_path, monkeypatch):
    monkeypatch.setattr(plate_config_store, "CONFIGS_DIR", tmp_path)
    plate_config_store.save_plate_config("my-config", _instance(text="AAA"))
    plate_config_store.save_plate_config("my-config", _instance(text="BBB"))
    loaded = plate_config_store.load_plate_config("my-config")
    assert loaded.field_values["registration"] == "BBB"
