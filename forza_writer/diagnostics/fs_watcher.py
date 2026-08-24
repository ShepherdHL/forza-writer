"""Filesystem watcher for the ``MediaOverride\\RC0`` override path.

Read-only: it only ``stat``s and walks the tree. It prefers the ``watchdog``
library if it is installed (event-driven, catches reads/opens more promptly);
otherwise it falls back to polling, comparing size and mtime between scans.

Read-access ("did FH6 open this file?") cannot be observed reliably without a
filesystem filter driver / ETW. When NTFS last-access tracking happens to be
enabled, an advancing ``atime`` with no size/mtime change is logged as a
best-effort ``file_read`` hint, with a one-time caveat at startup.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

from forza_writer.diagnostics.session import OK, UNKNOWN, SessionLogger

try:  # optional dependency; polling is the fallback
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    _HAVE_WATCHDOG = True
except Exception:  # pragma: no cover - depends on environment
    _HAVE_WATCHDOG = False


class _Entry:
    __slots__ = ("size", "mtime", "atime")

    def __init__(self, size: int, mtime: float, atime: float):
        self.size = size
        self.mtime = mtime
        self.atime = atime


class FileSystemWatcher:
    def __init__(
        self,
        root: str | Path,
        logger: SessionLogger,
        *,
        recursive: bool = True,
        poll_interval: float = 1.0,
        detect_atime: bool = True,
        prefer_watchdog: bool = True,
    ) -> None:
        self.root = Path(root)
        self.logger = logger
        self.recursive = recursive
        self.poll_interval = poll_interval
        self.detect_atime = detect_atime
        self.use_watchdog = prefer_watchdog and _HAVE_WATCHDOG
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._observer: Any = None
        self._prev: dict[str, _Entry] | None = None

    # -- shared -----------------------------------------------------------
    def _emit_startup(self, file_count: int) -> None:
        self.logger.emit(
            "filesystem",
            "snapshot",
            target=str(self.root),
            detail={
                "exists": self.root.exists(),
                "file_count": file_count,
                "recursive": self.recursive,
                "backend": "watchdog" if self.use_watchdog else "polling",
            },
            outcome=OK,
        )
        if self.detect_atime:
            self.logger.emit(
                "filesystem",
                "atime_caveat",
                target=str(self.root),
                detail={"note": "read-access hints rely on NTFS last-access time, often disabled; treat file_read as best-effort only"},
                outcome=UNKNOWN,
            )

    # -- polling backend ---------------------------------------------------
    def _scan(self) -> dict[str, _Entry]:
        entries: dict[str, _Entry] = {}
        if not self.root.exists():
            return entries
        if self.recursive:
            walker = os.walk(self.root)
        else:
            walker = [(str(self.root), [], [e.name for e in os.scandir(self.root) if e.is_file()])]
        for dirpath, _dirs, filenames in walker:
            for filename in filenames:
                full = os.path.join(dirpath, filename)
                try:
                    st = os.stat(full)
                except OSError:
                    continue
                entries[full] = _Entry(st.st_size, st.st_mtime, st.st_atime)
        return entries

    def poll_once(self) -> None:
        current = self._scan()
        if self._prev is None:
            self._emit_startup(len(current))
            self._prev = current
            return
        prev = self._prev
        for path, entry in current.items():
            old = prev.get(path)
            if old is None:
                self.logger.emit("filesystem", "file_created", target=path, detail={"size": entry.size, "mtime": entry.mtime}, outcome=OK)
            elif entry.size != old.size or entry.mtime != old.mtime:
                self.logger.emit(
                    "filesystem",
                    "file_modified",
                    target=path,
                    detail={"size": entry.size, "old_size": old.size, "mtime": entry.mtime, "old_mtime": old.mtime},
                    outcome=OK,
                )
            elif self.detect_atime and entry.atime > old.atime:
                self.logger.emit(
                    "filesystem",
                    "file_read",
                    target=path,
                    detail={"atime": entry.atime, "old_atime": old.atime, "note": "best-effort read-access hint"},
                    outcome=OK,
                )
        for path in prev.keys() - current.keys():
            self.logger.emit("filesystem", "file_deleted", target=path, detail={}, outcome=OK)
        self._prev = current

    def _run_polling(self) -> None:
        while not self._stop.is_set():
            try:
                self.poll_once()
            except Exception as exc:  # pragma: no cover - defensive
                self.logger.emit("filesystem", "watcher_error", detail={"error": str(exc)}, outcome=UNKNOWN)
            self._stop.wait(self.poll_interval)

    # -- watchdog backend --------------------------------------------------
    def _make_watchdog_handler(self) -> Any:
        logger = self.logger
        _map = {"created": "file_created", "modified": "file_modified", "deleted": "file_deleted", "moved": "file_moved"}

        class _Handler(FileSystemEventHandler):  # type: ignore[misc]
            def on_any_event(self, event: Any) -> None:
                if getattr(event, "is_directory", False):
                    return
                event_type = _map.get(event.event_type, event.event_type)
                detail: dict[str, Any] = {}
                dest = getattr(event, "dest_path", None)
                if dest:
                    detail["dest_path"] = dest
                logger.emit("filesystem", event_type, target=getattr(event, "src_path", ""), detail=detail, outcome=OK)

        return _Handler()

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        if self._thread is not None or self._observer is not None:
            return
        if self.use_watchdog:
            file_count = len(self._scan())
            self._emit_startup(file_count)
            self._observer = Observer()
            self._observer.schedule(self._make_watchdog_handler(), str(self.root), recursive=self.recursive)
            self._observer.start()
            return
        self._thread = threading.Thread(target=self._run_polling, name="fs-watcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=self.poll_interval * 4 + 2)
            self._observer = None
        if self._thread is not None:
            self._thread.join(timeout=self.poll_interval * 4 + 2)
            self._thread = None
