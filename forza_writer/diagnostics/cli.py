"""Unified diagnostic session CLI.

One command starts all three read-only listeners under a shared session id,
funnels every event into one common-schema timeline, and on stop (Ctrl+C or
``--duration`` timeout) auto-runs the correlation pass and writes both output
files into ``logs/<session_id>/``:

* ``session_<id>.json``: full machine-readable log (paste-to-AI ready)
* ``session_<id>.summary.md``: human digest (overview, table, flagged failures)

Examples
--------
Capture memory + catalog + override folder for two minutes::

    python -m forza_writer.diagnostics \\
        --layers 12 \\
        --sqlite "C:/path/to/fh6_catalog.sqlite" \\
        --fs-path "C:/.../MediaOverride/RC0" \\
        --duration 120

Re-correlate an existing session, focusing on what happened after your last
failure::

    python -m forza_writer.diagnostics --recorrelate logs/20260706-154200/session_20260706-154200.json --since-last-fail

Everything here is read-only; nothing writes to FH6's process, catalog, or files.
"""

from __future__ import annotations

import argparse
import json
import signal
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from forza_writer import probe
from forza_writer.diagnostics import correlate, report
from forza_writer.diagnostics.fs_watcher import FileSystemWatcher
from forza_writer.diagnostics.memory_diff import MemoryDiffWatcher
from forza_writer.diagnostics.session import SessionLogger
from forza_writer.diagnostics.sqlite_watcher import (
    DEFAULT_FOCUS_IDS,
    DEFAULT_ID_COLUMN,
    DEFAULT_TABLE,
    KNOWN_RANGE,
    CatalogWatcher,
)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _new_session_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _parse_memory_targets(values: list[str]) -> list[tuple[int, int]]:
    targets: list[tuple[int, int]] = []
    for value in values:
        if ":" not in value:
            raise argparse.ArgumentTypeError(f"--memory expects ADDR:LEN, got {value!r}")
        addr_str, len_str = value.split(":", 1)
        targets.append((int(addr_str, 0), int(len_str, 0)))
    return targets


def _parse_range(value: str) -> tuple[int, int]:
    sep = "-" if "-" in value else ":"
    lo, hi = value.split(sep, 1)
    return int(lo, 0), int(hi, 0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m forza_writer.diagnostics",
        description="Read-only, multi-source diagnostic logging for the FH6 injection pipeline.",
    )
    parser.add_argument("--logs-dir", type=Path, default=Path("logs"), help="Root folder for session output (default: logs/)")
    parser.add_argument("--session-id", default=None, help="Shared session id (default: UTC timestamp)")
    parser.add_argument("--duration", type=float, default=None, help="Stop automatically after N seconds (default: run until Ctrl+C)")
    parser.add_argument("--interval", type=float, default=1.0, help="Default poll interval for all watchers (seconds)")
    parser.add_argument("--window-ms", type=float, default=correlate.DEFAULT_WINDOW_MS, help="Max gap between events in one transaction (ms)")
    parser.add_argument("--since-last-fail", action="store_true", help="Report only events after the last flagged failure")
    parser.add_argument("--recorrelate", type=Path, default=None, help="Re-run correlation on an existing session JSON or .raw.jsonl (no capture)")

    mem = parser.add_argument_group("memory diff logger (read-only)")
    mem.add_argument("--pid", type=int, default=None, help="FH6 pid (auto-detected if omitted)")
    mem.add_argument("--layers", type=int, default=None, help="Watch each layer's shape-id (0x7A) and resource ptr (0xA8) for a group of this size")
    mem.add_argument("--memory", action="append", default=[], metavar="ADDR:LEN", help="Explicit region to watch (hex ok), repeatable")
    mem.add_argument("--mem-interval", type=float, default=None, help="Override poll interval for memory watcher")
    mem.add_argument("--mem-max-seconds", type=float, default=45.0, help="Time budget for locating the vinyl group")

    sql = parser.add_argument_group("sqlite catalog watcher (read-only)")
    sql.add_argument("--sqlite", type=Path, default=None, help="Path to the catalog SQLite database")
    sql.add_argument("--table", default=DEFAULT_TABLE, help=f"Catalog table (default: {DEFAULT_TABLE})")
    sql.add_argument("--id-column", default=DEFAULT_ID_COLUMN, help=f"Id column (default: {DEFAULT_ID_COLUMN}; auto-detected if missing)")
    sql.add_argument("--range", type=_parse_range, default=KNOWN_RANGE, metavar="LO-HI", help="Known valid id range (default: 101-3840)")
    sql.add_argument("--focus-id", action="append", type=lambda v: int(v, 0), default=[], help="Id to track transitions for (repeatable; default: 4001)")
    sql.add_argument("--sqlite-interval", type=float, default=None, help="Override poll interval for sqlite watcher")
    sql.add_argument("--sqlite-no-copy", action="store_true", help="Read the live DB directly instead of a temp copy (copy is default & safest)")

    fsg = parser.add_argument_group("filesystem watcher (read-only)")
    fsg.add_argument("--fs-path", type=Path, default=None, help="Path to watch, e.g. .../MediaOverride/RC0")
    fsg.add_argument("--fs-no-recursive", action="store_true", help="Do not descend into subdirectories")
    fsg.add_argument("--fs-interval", type=float, default=None, help="Override poll interval for filesystem watcher")
    fsg.add_argument("--fs-no-atime", action="store_true", help="Disable best-effort read-access (atime) hints")
    fsg.add_argument("--fs-no-watchdog", action="store_true", help="Force polling even if watchdog is installed")
    return parser


def _load_events(path: Path) -> list[dict[str, Any]]:
    if path.suffix == ".jsonl" or path.name.endswith(".raw.jsonl"):
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "events" in data:
        return list(data["events"])
    raise ValueError(f"could not find an events array in {path}")


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else _PROJECT_ROOT / path


def _recorrelate(args: argparse.Namespace) -> int:
    source_path = _resolve(args.recorrelate)
    events = _load_events(source_path)
    result = correlate.build_report(
        events,
        window_ms=args.window_ms,
        known_range=tuple(args.range),
        since_last_fail=args.since_last_fail,
    )
    session_id = args.session_id or _new_session_id()
    session_dir = _resolve(args.logs_dir) / session_id
    document = report.build_session_document(
        session_id=session_id,
        started_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        duration_ms=max((e["t"] for e in events), default=0.0),
        config={"recorrelate_source": str(source_path), "since_last_fail": args.since_last_fail},
        report=result,
    )
    json_path, summary_path = report.write_outputs(document, session_dir, session_id)
    print(f"Re-correlated {len(events)} events from {source_path}")
    print(f"  {json_path}")
    print(f"  {summary_path}")
    return 0


def run(args: argparse.Namespace) -> int:
    if args.recorrelate is not None:
        return _recorrelate(args)

    watch_memory = args.layers is not None or bool(args.memory)
    watch_sqlite = args.sqlite is not None
    watch_fs = args.fs_path is not None
    if not (watch_memory or watch_sqlite or watch_fs):
        build_parser().error("nothing to watch: provide at least one of --layers/--memory, --sqlite, or --fs-path")

    session_id = args.session_id or _new_session_id()
    session_dir = _resolve(args.logs_dir) / session_id
    logger = SessionLogger(session_id, session_dir).open()

    config: dict[str, Any] = {
        "session_id": session_id,
        "duration": args.duration,
        "interval": args.interval,
        "window_ms": args.window_ms,
        "watch_memory": watch_memory,
        "watch_sqlite": watch_sqlite,
        "watch_filesystem": watch_fs,
        "read_only": True,
    }
    logger.session_start(config)

    handle: int | None = None
    watchers: list[Any] = []
    stop_event = threading.Event()

    try:
        if watch_memory:
            try:
                pid = probe.find_fh6_pid(args.pid)
                handle = probe.attach(pid)
                logger.emit("memory", "attached", target=str(pid), detail={"pid": pid}, outcome="ok")
                mem_watcher = MemoryDiffWatcher(handle, logger, poll_interval=args.mem_interval or args.interval)
                for addr, length in _parse_memory_targets(args.memory):
                    mem_watcher.add_region(f"explicit_{probe.hx(addr)}", addr, length)
                if args.layers is not None:
                    mem_watcher.add_layer_regions(args.layers, max_seconds=args.mem_max_seconds)
                mem_watcher.start()
                watchers.append(mem_watcher)
            except Exception as exc:
                logger.emit("memory", "start_error", detail={"error": str(exc), "note": "continuing with other watchers"}, outcome="unknown")

        if watch_sqlite:
            catalog_watcher = CatalogWatcher(
                args.sqlite,
                logger,
                table=args.table,
                id_column=args.id_column,
                known_range=tuple(args.range),
                focus_ids=tuple(args.focus_id) or DEFAULT_FOCUS_IDS,
                poll_interval=args.sqlite_interval or args.interval,
                copy_first=not args.sqlite_no_copy,
            )
            catalog_watcher.start()
            watchers.append(catalog_watcher)

        if watch_fs:
            fs_watcher = FileSystemWatcher(
                args.fs_path,
                logger,
                recursive=not args.fs_no_recursive,
                poll_interval=args.fs_interval or args.interval,
                detect_atime=not args.fs_no_atime,
                prefer_watchdog=not args.fs_no_watchdog,
            )
            fs_watcher.start()
            watchers.append(fs_watcher)

        def _handle_signal(_signum: int, _frame: Any) -> None:
            stop_event.set()

        previous_handler = signal.signal(signal.SIGINT, _handle_signal)
        print(f"Diagnostic session {session_id} -> {session_dir}")
        print(f"Watchers: {', '.join(type(w).__name__ for w in watchers)}")
        print("Press Ctrl+C to stop." if args.duration is None else f"Auto-stops in {args.duration}s.")

        deadline = None if args.duration is None else time.monotonic() + args.duration
        try:
            while not stop_event.is_set():
                if deadline is not None and time.monotonic() >= deadline:
                    break
                stop_event.wait(0.25)
        finally:
            signal.signal(signal.SIGINT, previous_handler)

        reason = "interrupted" if stop_event.is_set() else "duration_elapsed"
        logger.session_stop(reason)
    finally:
        for watcher in watchers:
            try:
                watcher.stop()
            except Exception as exc:  # pragma: no cover - defensive
                logger.emit("session", "watcher_stop_error", detail={"watcher": type(watcher).__name__, "error": str(exc)}, outcome="unknown")
        if handle is not None:
            probe.close_handle(handle)
        duration_ms = logger.duration_ms()
        events = logger.events()
        logger.close()

    result = correlate.build_report(
        events,
        window_ms=args.window_ms,
        known_range=tuple(args.range),
        since_last_fail=args.since_last_fail,
    )
    document = report.build_session_document(
        session_id=session_id,
        started_utc=logger.started_utc,
        duration_ms=duration_ms,
        config=config,
        report=result,
    )
    json_path, summary_path = report.write_outputs(document, session_dir, session_id)

    print(
        f"Captured {document['event_count']} events, "
        f"{document['transaction_count']} transactions, "
        f"{document['failure_count']} failures, "
        f"{document['out_of_range_count']} out-of-range."
    )
    print(f"  {json_path}")
    print(f"  {summary_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
