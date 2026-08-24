import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "tools"))
import glyph_overrides  # noqa: E402


def test_load_overrides_for_font_returns_empty_when_no_file_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(glyph_overrides, "OVERRIDES_PATH", tmp_path / "does-not-exist" / "glyph_overrides.json")
    assert glyph_overrides.load_overrides_for_font(r"C:\fonts\Amarillo.ttf") == {}


def test_save_then_load_round_trips_mode_only_entries(tmp_path, monkeypatch):
    path = tmp_path / "nested" / "glyph_overrides.json"
    monkeypatch.setattr(glyph_overrides, "OVERRIDES_PATH", path)
    monkeypatch.setattr(glyph_overrides, "OVERRIDES_DIR", path.parent)

    font = r"C:\fonts\Amarillo.ttf"
    glyph_overrides.save_overrides_for_font(font, {"A": {"mode": "force"}, "B": {"mode": "never"}})
    loaded = glyph_overrides.load_overrides_for_font(font)
    assert loaded == {"A": {"mode": "force"}, "B": {"mode": "never"}}


def test_save_then_load_round_trips_manual_entries(tmp_path, monkeypatch):
    path = tmp_path / "glyph_overrides.json"
    monkeypatch.setattr(glyph_overrides, "OVERRIDES_PATH", path)
    monkeypatch.setattr(glyph_overrides, "OVERRIDES_DIR", path.parent)

    font = "font.ttf"
    glyph_overrides.save_overrides_for_font(font, {"C": {"mode": "manual", "file": r"D:\glyphs\C.json"}})
    loaded = glyph_overrides.load_overrides_for_font(font)
    assert loaded == {"C": {"mode": "manual", "file": r"D:\glyphs\C.json"}}


def test_save_creates_parent_directory(tmp_path, monkeypatch):
    path = tmp_path / "a" / "b" / "c" / "glyph_overrides.json"
    monkeypatch.setattr(glyph_overrides, "OVERRIDES_PATH", path)
    monkeypatch.setattr(glyph_overrides, "OVERRIDES_DIR", path.parent)

    glyph_overrides.save_overrides_for_font("font.ttf", {"A": {"mode": "force"}})
    assert path.exists()


def test_load_falls_back_on_corrupt_file(tmp_path, monkeypatch):
    path = tmp_path / "glyph_overrides.json"
    path.write_text("not valid json {{{", encoding="utf-8")
    monkeypatch.setattr(glyph_overrides, "OVERRIDES_PATH", path)
    assert glyph_overrides.load_overrides_for_font("font.ttf") == {}


def test_auto_mode_entries_are_not_persisted(tmp_path, monkeypatch):
    path = tmp_path / "glyph_overrides.json"
    monkeypatch.setattr(glyph_overrides, "OVERRIDES_PATH", path)
    monkeypatch.setattr(glyph_overrides, "OVERRIDES_DIR", path.parent)

    font = "font.ttf"
    glyph_overrides.save_overrides_for_font(font, {
        "A": {"mode": "force"}, "B": {"mode": "auto"}, "C": {"mode": "bogus"},
    })
    loaded = glyph_overrides.load_overrides_for_font(font)
    assert loaded == {"A": {"mode": "force"}}


def test_manual_entry_missing_file_is_not_persisted(tmp_path, monkeypatch):
    path = tmp_path / "glyph_overrides.json"
    monkeypatch.setattr(glyph_overrides, "OVERRIDES_PATH", path)
    monkeypatch.setattr(glyph_overrides, "OVERRIDES_DIR", path.parent)

    font = "font.ttf"
    glyph_overrides.save_overrides_for_font(font, {
        "A": {"mode": "manual"}, "B": {"mode": "manual", "file": ""}, "C": {"mode": "manual", "file": "x.json"},
    })
    loaded = glyph_overrides.load_overrides_for_font(font)
    assert loaded == {"C": {"mode": "manual", "file": "x.json"}}


def test_load_drops_a_malformed_entry_read_back_from_disk(tmp_path, monkeypatch):
    path = tmp_path / "glyph_overrides.json"
    path.write_text(
        '{"font.ttf": {"A": {"mode": "force"}, "B": {"mode": "manual"}, "C": "not-a-dict"}}',
        encoding="utf-8")
    monkeypatch.setattr(glyph_overrides, "OVERRIDES_PATH", path)
    assert glyph_overrides.load_overrides_for_font("font.ttf") == {"A": {"mode": "force"}}


def test_saving_empty_overrides_removes_the_fonts_entry(tmp_path, monkeypatch):
    path = tmp_path / "glyph_overrides.json"
    monkeypatch.setattr(glyph_overrides, "OVERRIDES_PATH", path)
    monkeypatch.setattr(glyph_overrides, "OVERRIDES_DIR", path.parent)

    font = "font.ttf"
    glyph_overrides.save_overrides_for_font(font, {"A": {"mode": "force"}})
    glyph_overrides.save_overrides_for_font(font, {"A": {"mode": "auto"}})
    assert glyph_overrides.load_overrides_for_font(font) == {}

    import json
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert font not in on_disk


def test_save_merges_across_fonts_without_clobbering_others(tmp_path, monkeypatch):
    path = tmp_path / "glyph_overrides.json"
    monkeypatch.setattr(glyph_overrides, "OVERRIDES_PATH", path)
    monkeypatch.setattr(glyph_overrides, "OVERRIDES_DIR", path.parent)

    glyph_overrides.save_overrides_for_font("font-a.ttf", {"A": {"mode": "force"}})
    glyph_overrides.save_overrides_for_font("font-b.ttf", {"B": {"mode": "never"}})

    assert glyph_overrides.load_overrides_for_font("font-a.ttf") == {"A": {"mode": "force"}}
    assert glyph_overrides.load_overrides_for_font("font-b.ttf") == {"B": {"mode": "never"}}


def test_load_ignores_a_non_dict_entry_for_the_font(tmp_path, monkeypatch):
    path = tmp_path / "glyph_overrides.json"
    path.write_text('{"font.ttf": "not-a-dict"}', encoding="utf-8")
    monkeypatch.setattr(glyph_overrides, "OVERRIDES_PATH", path)
    assert glyph_overrides.load_overrides_for_font("font.ttf") == {}
