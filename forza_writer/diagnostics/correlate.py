"""Correlation engine: group cross-source events into injection transactions.

The pipeline touches three layers within a short window during a single
injection attempt (a catalog insert, a memory write at ``0x7A``, a read of an
RC0 override file). This module walks the unified event stream in timestamp
order, clusters events that occur close together in time into *transactions*,
and flags the ones that look like failures:

* any step whose ``outcome`` is ``rejected`` or ``reverted`` -> failure candidate
* any step touching a shape id outside the known 101-3840 validation range
  -> out-of-range (the boundary FH6 enforces at save time)

The result is designed so a human, or an AI assistant, can read the flagged
transactions alone and see the whole cross-source story of each failure.
"""

from __future__ import annotations

from typing import Any

KNOWN_RANGE = (101, 3840)
DEFAULT_WINDOW_MS = 1000.0

# Event types that represent real pipeline activity (as opposed to setup,
# snapshots, or errors). Only these anchor and populate transactions.
MEANINGFUL_TYPES = frozenset(
    {
        "write",
        "insert",
        "update",
        "delete",
        "query",
        "file_created",
        "file_modified",
        "file_deleted",
        "file_moved",
        "file_read",
        "change",
    }
)

_OUTCOME_SEVERITY = {"rejected": 3, "reverted": 2, "unknown": 1, "ok": 0}
_FAILURE_OUTCOMES = frozenset({"rejected", "reverted"})


def _shape_ids(event: dict[str, Any]) -> list[int]:
    detail = event.get("detail") or {}
    ids: list[int] = []
    for key in ("shape_id", "catalog_id"):
        value = detail.get(key)
        if isinstance(value, int):
            ids.append(value)
    for key in ("added_ids", "removed_ids", "out_of_range_ids"):
        value = detail.get(key)
        if isinstance(value, list):
            ids.extend(v for v in value if isinstance(v, int))
    return ids


def _out_of_range_ids(event: dict[str, Any], known_range: tuple[int, int]) -> list[int]:
    lo, hi = known_range
    return sorted({i for i in _shape_ids(event) if not (lo <= i <= hi)})


def _describe_step(event: dict[str, Any]) -> str:
    source = event["source"]
    event_type = event["event_type"]
    target = event.get("target") or ""
    if source == "sqlite":
        return f"catalog {event_type} {target}".strip()
    if source == "memory":
        region = (event.get("detail") or {}).get("region")
        region_suffix = f" ({region})" if region else ""
        return f"memory {event_type} @{target}{region_suffix}"
    if source == "filesystem":
        name = target.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
        return f"RC0 {event_type} {name}"
    return f"{source} {event_type}"


def _describe_reason(event: dict[str, Any], known_range: tuple[int, int]) -> str:
    source = event["source"]
    outcome = event["outcome"]
    detail = event.get("detail") or {}
    if source == "memory" and outcome == "reverted":
        return f"memory @{event.get('target')} reverted to baseline (FH6 overwrote/rejected the change)"
    if source == "sqlite" and outcome == "rejected":
        oor = _out_of_range_ids(event, known_range)
        suffix = f" - outside {known_range[0]}-{known_range[1]}" if oor else ""
        sid = detail.get("shape_id")
        return f"catalog id {sid} removed after insert{suffix}"
    if source == "memory" and outcome == "rejected":
        return f"memory write @{event.get('target')} did not take (value differs from intended)"
    return f"{source} {event['event_type']} -> {outcome}"


def correlate(
    events: list[dict[str, Any]],
    *,
    window_ms: float = DEFAULT_WINDOW_MS,
    known_range: tuple[int, int] = KNOWN_RANGE,
) -> list[dict[str, Any]]:
    """Cluster meaningful events into time-local transactions."""
    steps = sorted(
        (e for e in events if e.get("event_type") in MEANINGFUL_TYPES),
        key=lambda e: (e["t"], e["seq"]),
    )
    transactions: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    last_t: float | None = None

    def flush() -> None:
        if current:
            transactions.append(_finalize(current, len(transactions) + 1, known_range))

    for event in steps:
        if last_t is not None and event["t"] - last_t > window_ms:
            flush()
            current = []
        current.append(event)
        last_t = event["t"]
    flush()
    return transactions


def _finalize(steps: list[dict[str, Any]], index: int, known_range: tuple[int, int]) -> dict[str, Any]:
    sources = sorted({s["source"] for s in steps})
    worst = max(steps, key=lambda s: _OUTCOME_SEVERITY.get(s["outcome"], 1))
    outcome = worst["outcome"]
    failure = any(s["outcome"] in _FAILURE_OUTCOMES for s in steps)
    out_of_range_ids = sorted({i for s in steps for i in _out_of_range_ids(s, known_range)})
    attempted = "; ".join(dict.fromkeys(_describe_step(s) for s in steps))
    reason = None
    if failure:
        failing = next(s for s in steps if s["outcome"] in _FAILURE_OUTCOMES)
        reason = _describe_reason(failing, known_range)
    elif out_of_range_ids:
        reason = f"touches shape id(s) {out_of_range_ids} outside {known_range[0]}-{known_range[1]}"
    return {
        "id": f"txn_{index}",
        "t_start": steps[0]["t"],
        "t_end": steps[-1]["t"],
        "sources": sources,
        "cross_source": len(sources) > 1,
        "attempted": attempted or "(observation)",
        "outcome": outcome,
        "failure": failure,
        "out_of_range": bool(out_of_range_ids),
        "out_of_range_ids": out_of_range_ids,
        "reason": reason,
        "step_count": len(steps),
        "steps": steps,
    }


def flagged_transactions(transactions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [t for t in transactions if t["failure"] or t["out_of_range"]]


def last_failure_cutoff(transactions: list[dict[str, Any]]) -> float | None:
    fails = [t for t in transactions if t["failure"]]
    return fails[-1]["t_end"] if fails else None


def build_report(
    events: list[dict[str, Any]],
    *,
    window_ms: float = DEFAULT_WINDOW_MS,
    known_range: tuple[int, int] = KNOWN_RANGE,
    since_last_fail: bool = False,
) -> dict[str, Any]:
    """Correlate events into transactions and collect flagged failures.

    When ``since_last_fail`` is set, everything up to and including the last
    failed transaction is dropped and only the remainder is correlated. This is
    useful when iterating on a fix and re-running the same test repeatedly.
    """
    transactions = correlate(events, window_ms=window_ms, known_range=known_range)
    cutoff = None
    used_events = events
    if since_last_fail:
        cutoff = last_failure_cutoff(transactions)
        if cutoff is not None:
            used_events = [e for e in events if e["t"] > cutoff]
            transactions = correlate(used_events, window_ms=window_ms, known_range=known_range)
    return {
        "events": used_events,
        "transactions": transactions,
        "flagged": flagged_transactions(transactions),
        "since_last_fail_cutoff_ms": cutoff,
        "window_ms": window_ms,
        "known_range": list(known_range),
    }
