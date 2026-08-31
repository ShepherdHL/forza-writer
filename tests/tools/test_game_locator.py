import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "tools"))
import game_locator  # noqa: E402


def _make_vinyls_zip(path: Path, *, modelbin_name: str = "S_01.modelbin", modelbin_data: bytes = b"fake-modelbin-bytes") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(modelbin_name, modelbin_data)
        archive.writestr("S_02.modelbin", b"other-shape-not-the-one-we-want")
    return path


def test_extract_reference_modelbin_writes_the_named_entry(tmp_path):
    zip_path = _make_vinyls_zip(tmp_path / "install" / "media" / "Livery" / "Vinyls.zip")
    dest = tmp_path / "user-assets" / "S_01.modelbin"

    result = game_locator.extract_reference_modelbin(dest, zip_path)

    assert result == dest
    assert dest.read_bytes() == b"fake-modelbin-bytes"


def test_extract_reference_modelbin_creates_missing_parent_dirs(tmp_path):
    zip_path = _make_vinyls_zip(tmp_path / "Vinyls.zip")
    dest = tmp_path / "does" / "not" / "exist" / "yet" / "S_01.modelbin"

    game_locator.extract_reference_modelbin(dest, zip_path)

    assert dest.exists()


def test_extract_reference_modelbin_raises_when_no_zip_located(tmp_path, monkeypatch):
    monkeypatch.setattr(game_locator, "find_fh6_vinyls_zip", lambda: None)
    dest = tmp_path / "S_01.modelbin"

    try:
        game_locator.extract_reference_modelbin(dest)
        assert False, "expected FileNotFoundError"
    except FileNotFoundError:
        pass


def test_extract_reference_modelbin_raises_when_entry_missing_from_zip(tmp_path):
    zip_path = tmp_path / "Vinyls.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("S_02.modelbin", b"not the reference shape")
    dest = tmp_path / "S_01.modelbin"

    try:
        game_locator.extract_reference_modelbin(dest, zip_path)
        assert False, "expected FileNotFoundError"
    except FileNotFoundError:
        pass


def test_dedupe_preserves_order_and_drops_repeats():
    a, b = Path("C:/a"), Path("C:/b")
    assert game_locator._dedupe([a, b, a]) == [a, b]
