"""Unified session logger with a single common event schema.

Every listener (memory, SQLite, filesystem) emits through this logger, so all
events share one shape and line up on one timeline regardless of source::

    {
      "seq": <int, stable tie-breaker for equal timestamps>,
      "t": <float, milliseconds since session start>,
      "source": "memory" | "sqlite" | "filesystem" | "session",
      "event_type": <str, e.g. "write", "query", "file_modified">,
      "target": <str, address / table#id / file path>,
      "detail": { ...source-specific fields... },
      "outcome": "ok" | "rejected" | "reverted" | "unknown"
    }

The logger keeps every event in memory (for the post-session correlation pass)
and also streams each one to a ``.raw.jsonl`` file as it happens, so an
interrupted or crashed session still leaves a complete, replayable log on disk.
It is safe to share across watcher threads.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

# Canonical outcome vocabulary.
OK = "ok"
REJECTED = "rejected"
REVERTED = "reverted"
UNKNOWN = "unknown"

VALID_OUTCOMES = frozenset({OK, REJECTED, REVERTED, UNKNOWN})


def utc_now_iso() -> str:
    """ISO-8601 UTC timestamp with millisecond precision."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class SessionLogger:
    def __init__(self, session_id: str, session_dir: str | Path) -> None:
        self.session_id = session_id
        self.session_dir = Path(session_dir)
        self.started_utc = utc_now_iso()
        self._start_monotonic = time.monotonic()
        self._lock = threading.Lock()
        self._seq = 0
        self._events: list[dict[str, Any]] = []
        self._raw_file: TextIO | None = None

    # -- lifecycle ---------------------------------------------------------
    def open(self) -> "SessionLogger":
        self.session_dir.mkdir(parents=True, exist_ok=True)
        raw_path = self.session_dir / f"session_{self.session_id}.raw.jsonl"
        self._raw_file = raw_path.open("w", encoding="utf-8")
        return self

    def close(self) -> None:
        with self._lock:
            if self._raw_file is not None:
                self._raw_file.flush()
                self._raw_file.close()
                self._raw_file = None

    def __enter__(self) -> "SessionLogger":
        return self.open()

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # -- timing ------------------------------------------------------------
    def now_ms(self) -> float:
        return round((time.monotonic() - self._start_monotonic) * 1000.0, 3)

    # -- emission ----------------------------------------------------------
    def emit(
        self,
        source: str,
        event_type: str,
        target: str = "",
        detail: dict[str, Any] | None = None,
        outcome: str = UNKNOWN,
    ) -> dict[str, Any]:
        if outcome not in VALID_OUTCOMES:
            outcome = UNKNOWN
        with self._lock:
            self._seq += 1
            event = {
                "seq": self._seq,
                "t": self.now_ms(),
                "source": source,
                "event_type": event_type,
                "target": target,
                "detail": detail or {},
                "outcome": outcome,
            }
            self._events.append(event)
            if self._raw_file is not None:
                self._raw_file.write(json.dumps(event, ensure_ascii=False) + "\n")
                self._raw_file.flush()
            return event

    # -- access ------------------------------------------------------------
    def events(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._events)

    def duration_ms(self) -> float:
        return self.now_ms()

    # -- session markers ---------------------------------------------------
    def session_start(self, config: dict[str, Any]) -> None:
        self.emit("session", "session_start", target=self.session_id, detail={"config": config}, outcome=OK)

    def session_stop(self, reason: str) -> None:
        self.emit("session", "session_stop", target=self.session_id, detail={"reason": reason}, outcome=OK)
