"""Read-only watcher for the FH6 ``Livery_VinylsDecals`` shape catalog.

Scope and honesty about limits
------------------------------
FH6 validates its catalog from an in-process SQLite database. There is no safe,
supported way to intercept another process's *internal* SQL statements from the
outside, so this watcher does not claim to. It does two strictly read-only jobs:

1. **State polling** — opens the catalog read-only and snapshots the
   ``Livery_VinylsDecals`` table (row count, id extent, count within the known
   101-3840 range, and the exact rows for a set of *focus ids* such as 4001).
   Between snapshots it emits inserts/deletes/updates and focus-id transitions.
   A focus id that is out of range and later disappears is reported with
   ``outcome="rejected"`` — the fingerprint of FH6 dropping a test insert.

2. **Query tracing (opt-in, our connection only)** — ``install_trace`` logs
   statements executed on a connection *we* drive; it cannot see FH6's internal
   statements.

``copy_first=True`` copies the DB to a temp file and reads the copy, so there is
never any lock contention with a live game. The source is only ever read.
"""

from __future__ import annotations

import shutil
import sqlite3
import tempfile
import threading
from pathlib import Path
from typing import Any

from forza_writer.diagnostics.session import OK, REJECTED, UNKNOWN, SessionLogger

DEFAULT_TABLE = "Livery_VinylsDecals"
DEFAULT_ID_COLUMN = "Id"
KNOWN_RANGE = (101, 3840)
DEFAULT_FOCUS_IDS = (4001,)


class CatalogWatcher:
    def __init__(
        self,
        db_path: str | Path,
        logger: SessionLogger,
        *,
        table: str = DEFAULT_TABLE,
        id_column: str = DEFAULT_ID_COLUMN,
        known_range: tuple[int, int] = KNOWN_RANGE,
        focus_ids: tuple[int, ...] = DEFAULT_FOCUS_IDS,
        poll_interval: float = 1.0,
        copy_first: bool = True,
    ) -> None:
        self.db_path = Path(db_path)
        self.logger = logger
        self.table = table
        self.id_column = id_column
        self.known_range = known_range
        self.focus_ids = tuple(focus_ids)
        self.poll_interval = poll_interval
        self.copy_first = copy_first
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._prev_ids: set[int] | None = None
        self._prev_focus: dict[int, Any] = {}
        self._resolved_id_column: str | None = None

    def _in_range(self, value: int) -> bool:
        return self.known_range[0] <= value <= self.known_range[1]

    # -- connection helpers ------------------------------------------------
    def _open_readonly(self) -> tuple[sqlite3.Connection, Path | None]:
        if self.copy_first:
            tmp = Path(tempfile.gettempdir()) / f"fh6_catalog_snapshot_{id(self)}.sqlite"
            shutil.copy2(self.db_path, tmp)
            conn = sqlite3.connect(f"file:{tmp}?mode=ro&immutable=1", uri=True)
            return conn, tmp
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        return conn, None

    def _resolve_id_column(self, conn: sqlite3.Connection) -> str:
        if self._resolved_id_column:
            return self._resolved_id_column
        cols = [row[1] for row in conn.execute(f'PRAGMA table_info("{self.table}")').fetchall()]
        if not cols:
            raise RuntimeError(f"table {self.table!r} not found in {self.db_path}")
        for candidate in (self.id_column, "Id", "ID", "id", "TypeId", "TypeID"):
            if candidate in cols:
                self._resolved_id_column = candidate
                return candidate
        self._resolved_id_column = cols[0]
        self.logger.emit(
            "sqlite",
            "id_column_guess",
            target=self.table,
            detail={"chosen": cols[0], "available": cols, "note": "configured id column not found; using first column"},
            outcome=UNKNOWN,
        )
        return cols[0]

    # -- snapshotting ------------------------------------------------------
    def _snapshot(self, conn: sqlite3.Connection) -> dict[str, Any]:
        idc = self._resolve_id_column(conn)
        lo, hi = self.known_range
        total = conn.execute(f'SELECT COUNT(*) FROM "{self.table}"').fetchone()[0]
        extent = conn.execute(f'SELECT MIN("{idc}"), MAX("{idc}") FROM "{self.table}"').fetchone()
        in_range = conn.execute(
            f'SELECT COUNT(*) FROM "{self.table}" WHERE "{idc}" BETWEEN ? AND ?', (lo, hi)
        ).fetchone()[0]
        ids = {row[0] for row in conn.execute(f'SELECT "{idc}" FROM "{self.table}"').fetchall()}
        focus_rows: dict[int, Any] = {}
        for fid in self.focus_ids:
            row = conn.execute(f'SELECT * FROM "{self.table}" WHERE "{idc}" = ?', (fid,)).fetchone()
            focus_rows[fid] = list(row) if row is not None else None
        return {
            "id_column": idc,
            "total": total,
            "min_id": extent[0],
            "max_id": extent[1],
            "in_known_range": in_range,
            "out_of_known_range": total - in_range,
            "ids": ids,
            "focus_rows": focus_rows,
        }

    def _emit_changes(self, prev_ids: set[int], snap: dict[str, Any]) -> None:
        cur_ids = snap["ids"]
        added = sorted(cur_ids - prev_ids)
        removed = sorted(prev_ids - cur_ids)
        if added or removed:
            oor = [i for i in added + removed if not self._in_range(i)]
            self.logger.emit(
                "sqlite",
                "change",
                target=self.table,
                detail={
                    "added_ids": added[:200],
                    "removed_ids": removed[:200],
                    "added_count": len(added),
                    "removed_count": len(removed),
                    "out_of_range_ids": oor[:200],
                    "total": snap["total"],
                    "in_known_range": snap["in_known_range"],
                    "out_of_known_range": snap["out_of_known_range"],
                },
                outcome=OK,
            )
        for fid in self.focus_ids:
            before = self._prev_focus.get(fid)
            after = snap["focus_rows"].get(fid)
            if before == after:
                continue
            in_range = self._in_range(fid)
            if before is None and after is not None:
                event_type, outcome = "insert", OK
            elif before is not None and after is None:
                # An out-of-range id vanishing after appearing = FH6 rejected it.
                event_type, outcome = "delete", (REJECTED if not in_range else OK)
            else:
                event_type, outcome = "update", OK
            self.logger.emit(
                "sqlite",
                event_type,
                target=f"{self.table}#{fid}",
                detail={
                    "shape_id": fid,
                    "in_known_range": in_range,
                    "before": before,
                    "after": after,
                    "note": "captures whether FH6 accepts, drops, or normalizes this id",
                },
                outcome=outcome,
            )

    def poll_once(self) -> None:
        conn: sqlite3.Connection | None = None
        tmp: Path | None = None
        try:
            conn, tmp = self._open_readonly()
            snap = self._snapshot(conn)
        except Exception as exc:
            self.logger.emit("sqlite", "poll_error", target=str(self.db_path), detail={"error": str(exc)}, outcome=UNKNOWN)
            return
        finally:
            if conn is not None:
                conn.close()
            if tmp is not None:
                tmp.unlink(missing_ok=True)

        if self._prev_ids is None:
            self.logger.emit(
                "sqlite",
                "snapshot",
                target=self.table,
                detail={
                    "id_column": snap["id_column"],
                    "total": snap["total"],
                    "min_id": snap["min_id"],
                    "max_id": snap["max_id"],
                    "in_known_range": snap["in_known_range"],
                    "out_of_known_range": snap["out_of_known_range"],
                    "known_range": list(self.known_range),
                    "focus_ids": list(self.focus_ids),
                    "focus_rows": snap["focus_rows"],
                },
                outcome=OK,
            )
        else:
            self._emit_changes(self._prev_ids, snap)
        self._prev_ids = snap["ids"]
        self._prev_focus = snap["focus_rows"]

    # -- opt-in query tracing (our own connection only) --------------------
    def install_trace(self, conn: sqlite3.Connection, label: str = "owned_connection") -> None:
        def _trace(statement: str) -> None:
            self.logger.emit("sqlite", "query", target=self.table, detail={"label": label, "statement": statement}, outcome=OK)

        conn.set_trace_callback(_trace)

    # -- lifecycle ---------------------------------------------------------
    def _run(self) -> None:
        while not self._stop.is_set():
            self.poll_once()
            self._stop.wait(self.poll_interval)

    def start(self) -> None:
        if self._thread is not None:
            return
        if not self.db_path.exists():
            self.logger.emit("sqlite", "start_error", target=str(self.db_path), detail={"error": "database file not found"}, outcome=UNKNOWN)
            return
        self._thread = threading.Thread(target=self._run, name="sqlite-watcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.poll_interval * 4 + 2)
            self._thread = None
