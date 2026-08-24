"""Memory diff logger built on the read-only probe primitives.

This watcher never writes to FH6. It snapshots target regions, polls them, and
emits common-schema events. Its key job is *revert detection*: when a region
changes away from its session-start baseline and later snaps back to that
baseline, FH6 has almost certainly overwritten or rejected the change (the
behavior seen when an out-of-range shape word is normalized at save). Such a
reversion is emitted as a ``write`` event with ``outcome="reverted"``.

If external tooling wants its writes logged, it can route them through
:meth:`MemoryDiffWatcher.record_write_attempt`, supplying its own write
callable. This watcher performs the before/after reads and logging only; it
holds no write capability and defaults to performing no write at all.
"""

from __future__ import annotations

import struct
import threading
from typing import Any, Callable

from forza_writer import probe
from forza_writer.diagnostics.session import OK, REJECTED, REVERTED, UNKNOWN, SessionLogger


def _byte_diffs(old: bytes, new: bytes, limit: int = 64) -> list[dict[str, Any]]:
    diffs: list[dict[str, Any]] = []
    for offset in range(min(len(old), len(new))):
        if old[offset] != new[offset]:
            diffs.append({"offset": offset, "old": f"0x{old[offset]:02x}", "new": f"0x{new[offset]:02x}"})
            if len(diffs) >= limit:
                diffs.append({"note": f"diff truncated at {limit} changed bytes"})
                break
    if len(old) != len(new):
        diffs.append({"note": f"length changed {len(old)} -> {len(new)}"})
    return diffs


class _Region:
    __slots__ = ("name", "address", "length", "baseline", "last", "diverged", "meta")

    def __init__(self, name: str, address: int, length: int, baseline: bytes, meta: dict[str, Any]):
        self.name = name
        self.address = address
        self.length = length
        self.baseline = baseline
        self.last = baseline
        self.diverged = False
        self.meta = meta


class MemoryDiffWatcher:
    def __init__(
        self,
        handle: int,
        logger: SessionLogger,
        *,
        poll_interval: float = 0.5,
        hex_dump_limit: int = 256,
    ) -> None:
        self.handle = handle
        self.logger = logger
        self.poll_interval = poll_interval
        self.hex_dump_limit = hex_dump_limit
        self._regions: dict[str, _Region] = {}
        self._regions_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # -- region setup ------------------------------------------------------
    def add_region(self, name: str, address: int, length: int, meta: dict[str, Any] | None = None) -> None:
        baseline, error = probe.try_read_process_memory(self.handle, address, length)
        meta = dict(meta or {})
        if error:
            self.logger.emit(
                "memory",
                "baseline_error",
                target=probe.hx(address),
                detail={"region": name, "length": length, "error": error, **meta},
                outcome=UNKNOWN,
            )
            return
        with self._regions_lock:
            self._regions[name] = _Region(name, address, length, baseline, meta)
        self.logger.emit(
            "memory",
            "baseline",
            target=probe.hx(address),
            detail={"region": name, "length": length, "baseline_hex": self._maybe_hex(baseline), **meta},
            outcome=OK,
        )

    def add_layer_regions(self, layer_count: int, max_seconds: float = 45.0) -> dict[str, Any]:
        """Locate the active vinyl group and watch each layer's shape-id (0x7A)
        and resource-pointer (0xA8) fields — the bytes the pipeline sets."""
        located = probe.locate_vinyl_group(self.handle, layer_count, max_seconds=max_seconds)
        group = probe.parse_address(located["group"])
        table = probe.parse_address(located["table"])
        self.logger.emit(
            "memory",
            "group_located",
            target=located["group"],
            detail={
                "table": located["table"],
                "layer_count": layer_count,
                "locator_source": located.get("source"),
                "locator_score": located.get("score"),
            },
            outcome=OK,
        )
        ptr_raw, error = probe.try_read_process_memory(self.handle, table, layer_count * 8)
        if error:
            self.logger.emit(
                "memory",
                "layer_table_error",
                target=located["table"],
                detail={"error": error},
                outcome=UNKNOWN,
            )
            return located
        layer_ptrs = list(struct.unpack(f"<{layer_count}Q", ptr_raw))
        for index, layer_ptr in enumerate(layer_ptrs):
            self.add_region(
                f"layer{index + 1}_shape_id",
                layer_ptr + probe.SHAPE_WORD_OFFSET,
                2,
                {"layer_index": index, "layer": index + 1, "field": "shape_word_0x7A"},
            )
            self.add_region(
                f"layer{index + 1}_resource_ptr",
                layer_ptr + probe.RESOURCE_PTR_OFFSET,
                8,
                {"layer_index": index, "layer": index + 1, "field": "resource_ptr_0xA8"},
            )
        return located

    # -- write observation (never writes on its own) ----------------------
    def record_write_attempt(
        self,
        name: str,
        address: int,
        intended_bytes: bytes,
        write_fn: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        length = len(intended_bytes)
        old, old_err = probe.try_read_process_memory(self.handle, address, length)
        performed = False
        write_error: str | None = None
        if write_fn is not None:
            try:
                write_fn()
                performed = True
            except Exception as exc:  # pragma: no cover - depends on external tool
                write_error = str(exc)
        after, after_err = probe.try_read_process_memory(self.handle, address, length)
        if performed and after_err is None and after == intended_bytes:
            outcome = OK
        elif performed:
            outcome = REJECTED
        else:
            outcome = UNKNOWN
        event = self.logger.emit(
            "memory",
            "write",
            target=probe.hx(address),
            detail={
                "region": name,
                "length": length,
                "old_hex": probe.bytes_to_hex(old) if old else None,
                "intended_hex": probe.bytes_to_hex(intended_bytes),
                "after_hex": probe.bytes_to_hex(after) if after else None,
                "performed": performed,
                "write_error": write_error,
                "read_errors": {"before": old_err, "after": after_err},
                "note": "write performed by external tooling; observed read-only here",
            },
            outcome=outcome,
        )
        if old_err is None:
            with self._regions_lock:
                region = _Region(name, address, length, old, {"origin": "write_attempt"})
                region.last = after if after_err is None else old
                region.diverged = after_err is None and after != old
                self._regions[name] = region
        return event

    # -- polling loop ------------------------------------------------------
    def poll_once(self) -> None:
        with self._regions_lock:
            regions = list(self._regions.values())
        for region in regions:
            cur, error = probe.try_read_process_memory(self.handle, region.address, region.length)
            if error:
                self.logger.emit(
                    "memory",
                    "read_error",
                    target=probe.hx(region.address),
                    detail={"region": region.name, "error": error, **region.meta},
                    outcome=UNKNOWN,
                )
                continue
            if cur == region.last:
                continue
            reverted = cur == region.baseline and region.diverged
            detail = {
                "region": region.name,
                "length": region.length,
                "old_hex": self._maybe_hex(region.last),
                "new_hex": self._maybe_hex(cur),
                "byte_diffs": _byte_diffs(region.last, cur),
                **region.meta,
            }
            if reverted:
                detail["baseline_hex"] = self._maybe_hex(region.baseline)
                detail["note"] = "value returned to session baseline — FH6 likely overwrote or rejected the change"
            self.logger.emit(
                "memory",
                "write",
                target=probe.hx(region.address),
                detail=detail,
                outcome=REVERTED if reverted else OK,
            )
            region.last = cur
            region.diverged = cur != region.baseline

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.poll_once()
            except Exception as exc:  # pragma: no cover - defensive
                self.logger.emit("memory", "watcher_error", detail={"error": str(exc)}, outcome=UNKNOWN)
            self._stop.wait(self.poll_interval)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="memory-diff", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.poll_interval * 4 + 2)
            self._thread = None

    # -- helpers -----------------------------------------------------------
    def _maybe_hex(self, data: bytes) -> str | None:
        if len(data) > self.hex_dump_limit:
            return None
        return probe.bytes_to_hex(data)
