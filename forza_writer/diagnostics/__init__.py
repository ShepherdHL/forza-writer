"""Read-only, multi-source diagnostic instrumentation for the FH6 pipeline.

All three listeners (process memory, the ``Livery_VinylsDecals`` catalog, and
the ``MediaOverride\\RC0`` override path) emit through one common event schema
into a single :class:`SessionLogger`. After capture, the correlation engine
groups cross-source events into injection *transactions* and flags failures, and
the report writer emits a full JSON log plus a human-readable ``summary.md``.

Everything here is observation-only. Nothing writes to FH6's process memory, its
SQLite catalog, or the MediaOverride file tree.
"""

from forza_writer.diagnostics.session import (
    OK,
    REJECTED,
    REVERTED,
    UNKNOWN,
    SessionLogger,
    utc_now_iso,
)

__all__ = ["SessionLogger", "utc_now_iso", "OK", "REJECTED", "REVERTED", "UNKNOWN"]
