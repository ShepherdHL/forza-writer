from pathlib import Path

import generated_data_cleanup as cleanup


def test_cleanup_removes_only_named_generated_and_cache_contents(tmp_path):
    project = tmp_path / "project"
    data = project / "data"
    app_data = tmp_path / "local"
    data.mkdir(parents=True)
    protected = project / "user-assets" / "S_01.modelbin"
    protected.parent.mkdir()
    protected.write_bytes(b"reference")
    unrelated = project / "research" / "modelbin"
    unrelated.mkdir(parents=True)
    (unrelated / "fixture.json").write_text("keep", encoding="utf-8")

    for target in cleanup.cleanup_targets(project, app_data):
        target.mkdir(parents=True)
        (target / "nested").mkdir()
        (target / "nested" / "generated.bin").write_bytes(b"1234")

    summary = cleanup.clear_generated_data(project, app_data)

    assert summary.files == len(cleanup.GENERATED_DATA_DIRS) + len(cleanup.LOCAL_CACHE_DIRS)
    assert summary.bytes == summary.files * 4
    assert protected.read_bytes() == b"reference"
    assert (unrelated / "fixture.json").read_text(encoding="utf-8") == "keep"
    for target in cleanup.cleanup_targets(project, app_data):
        assert target.is_dir()
        assert list(target.iterdir()) == []


def test_summary_ignores_missing_targets(tmp_path):
    summary = cleanup.summarize(cleanup.cleanup_targets(tmp_path / "project", tmp_path / "local"))
    assert summary.files == 0
    assert summary.bytes == 0


def test_format_size_uses_readable_binary_units():
    assert cleanup.format_size(0) == "0 B"
    assert cleanup.format_size(1536) == "1.5 KB"
    assert cleanup.format_size(5 * 1024 * 1024) == "5.0 MB"


def test_cleanup_can_remove_one_selected_category_without_touching_another(tmp_path):
    project = tmp_path / "project"
    selected = project / "data" / "fontpacks"
    preserved = project / "data" / "direct"
    selected.mkdir(parents=True)
    preserved.mkdir(parents=True)
    (selected / "remove.json").write_text("remove", encoding="utf-8")
    (preserved / "keep.json").write_text("keep", encoding="utf-8")

    cleanup.clear_generated_data(project, tmp_path / "local", selected=["fontpacks"])

    assert list(selected.iterdir()) == []
    assert (preserved / "keep.json").read_text(encoding="utf-8") == "keep"
