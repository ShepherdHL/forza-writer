"""Safely enumerate and clear Forza Writer-owned generated data.

Only exact, named application output/cache directories are eligible.  Files
stored directly in ``data`` (reference modelbins, captures, color data, and
test fixtures) are deliberately outside the cleanup boundary.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path


GENERATED_DATA_DIRS = ("modelbin", "fontpacks", "advgen", "dgen", "direct", "image")
LOCAL_CACHE_DIRS = ("cupy-cache", "variable-instances")
TARGET_LABELS = {
    "modelbin": "Modelbin generation output",
    "fontpacks": "Standard fontpacks",
    "advgen": "Advanced Generation output (legacy folder)",
    "dgen": "Direct Generation output (legacy folder)",
    "direct": "Direct Generation output",
    "image": "Image-to-Text output and diagnostics",
    "cupy-cache": "CUDA compiled-kernel cache",
    "variable-instances": "Cached variable-font instances",
}
TARGET_DESCRIPTIONS = {
    "modelbin": "Custom-mesh glyph files generated from fonts and alphabets.",
    "fontpacks": "Complete standard fontpacks, including manifests and per-glyph output profiles.",
    "advgen": "Output retained in the older, separate Advanced Generation folder layout.",
    "dgen": "Output retained in the older Direct Generation folder layout.",
    "direct": "Standalone JSON files produced by Direct Generation.",
    "image": "Image-to-Text JSON, copied source images, debug views, and diagnostics.",
    "cupy-cache": "Compiled CUDA kernels. Safe to clear; they are rebuilt when GPU generation runs.",
    "variable-instances": "Temporary static fonts created from variable-font axis selections.",
}


def format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


@dataclass(frozen=True)
class CleanupSummary:
    targets: tuple[Path, ...]
    files: int
    bytes: int


def cleanup_targets(project_root: Path, local_app_data: Path | None = None,
                    selected: tuple[str, ...] | list[str] | None = None) -> tuple[Path, ...]:
    project_root = Path(project_root).resolve()
    app_data = Path(local_app_data or os.environ.get("LOCALAPPDATA", Path.home())).resolve()
    data_root = project_root / "data"
    cache_root = app_data / "forza-writer"
    names = tuple(TARGET_LABELS) if selected is None else tuple(selected)
    unknown = set(names) - set(TARGET_LABELS)
    if unknown:
        raise ValueError(f"Unknown cleanup target(s): {', '.join(sorted(unknown))}")
    return tuple(
        (cache_root if name in LOCAL_CACHE_DIRS else data_root) / name
        for name in names)


def summarize(targets: tuple[Path, ...]) -> CleanupSummary:
    files = 0
    size = 0
    for target in targets:
        try:
            exists = target.exists()
        except OSError:
            # The cleaner itself will report an inaccessible target if the
            # user proceeds; the confirmation preview must still be usable.
            continue
        if not exists:
            continue
        try:
            for item in target.rglob("*"):
                if item.is_file() and not item.is_symlink():
                    files += 1
                    size += item.stat().st_size
        except OSError:
            continue
    return CleanupSummary(targets, files, size)


def clear_generated_data(project_root: Path, local_app_data: Path | None = None,
                         selected: tuple[str, ...] | list[str] | None = None) -> CleanupSummary:
    """Delete the contents of exact application-owned directories.

    Root directories are preserved so configured default paths remain valid.
    Resolving and comparing against ``cleanup_targets`` prevents a caller from
    broadening deletion through a symlink or an accidentally supplied path.
    """
    targets = cleanup_targets(project_root, local_app_data, selected)
    before = summarize(targets)
    for target in targets:
        try:
            exists = target.exists()
        except OSError as exc:
            raise PermissionError(f"Cannot access generated-data directory: {target}") from exc
        if not exists:
            continue
        if target.is_symlink():
            raise ValueError(f"Refusing to clear symlinked output directory: {target}")
        for child in target.iterdir():
            if child.is_symlink() or child.is_file():
                child.unlink()
            elif child.is_dir():
                shutil.rmtree(child)
    return before
