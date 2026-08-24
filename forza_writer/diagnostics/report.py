"""Dual-output writer: a full machine-readable JSON and a human digest.

``session_<id>.json`` carries every field for scripted analysis or for pasting
straight to an AI assistant. ``session_<id>.summary.md`` is the skim-in-a-minute
digest: a one-paragraph overview, a one-line-per-transaction table, and a
"flagged" section that shows only the failure candidates in full so you never
scroll past the successes to find the problem.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


def _counts_by_source(events: list[dict[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter(e["source"] for e in events)
    return dict(sorted(counter.items()))


def build_session_document(
    *,
    session_id: str,
    started_utc: str,
    duration_ms: float,
    config: dict[str, Any],
    report: dict[str, Any],
) -> dict[str, Any]:
    events = report["events"]
    transactions = report["transactions"]
    flagged = report["flagged"]
    return {
        "session_id": session_id,
        "started_utc": started_utc,
        "duration_ms": round(duration_ms, 3),
        "config": config,
        "schema": {
            "fields": ["seq", "t", "source", "event_type", "target", "detail", "outcome"],
            "t_unit": "ms since session start",
            "outcomes": ["ok", "rejected", "reverted", "unknown"],
        },
        "counts_by_source": _counts_by_source(events),
        "event_count": len(events),
        "transaction_count": len(transactions),
        "failure_count": sum(1 for t in transactions if t["failure"]),
        "out_of_range_count": sum(1 for t in transactions if t["out_of_range"]),
        "correlation": {
            "window_ms": report["window_ms"],
            "known_range": report["known_range"],
            "since_last_fail_cutoff_ms": report["since_last_fail_cutoff_ms"],
        },
        "transactions": transactions,
        "flagged": flagged,
        "events": events,
    }


def write_json(document: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _fmt_secs(ms: float) -> str:
    return f"{ms / 1000.0:.2f}s"


def _md_escape(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def render_summary(document: dict[str, Any]) -> str:
    transactions = document["transactions"]
    flagged = document["flagged"]
    counts = document["counts_by_source"]
    lines: list[str] = []

    lines.append(f"# Diagnostic session `{document['session_id']}`")
    lines.append("")

    per_source = ", ".join(f"{src}: {n}" for src, n in counts.items()) or "no events"
    overview = (
        f"Session ran **{_fmt_secs(document['duration_ms'])}** starting {document['started_utc']}, "
        f"capturing **{document['event_count']} events** ({per_source}) grouped into "
        f"**{document['transaction_count']} transactions**, of which "
        f"**{document['failure_count']} failed** and "
        f"**{document['out_of_range_count']} touched shape ids outside "
        f"{document['correlation']['known_range'][0]}-{document['correlation']['known_range'][1]}**."
    )
    cutoff = document["correlation"]["since_last_fail_cutoff_ms"]
    if cutoff is not None:
        overview += f" (Reprocessed only events after the last failure at {_fmt_secs(cutoff)}.)"
    lines.append(overview)
    lines.append("")

    lines.append("## Transactions")
    lines.append("")
    if transactions:
        lines.append("| time | sources | attempted | outcome | reason |")
        lines.append("|------|---------|-----------|---------|--------|")
        for txn in transactions:
            flag = " [FLAG]" if (txn["failure"] or txn["out_of_range"]) else ""
            sources = "+".join(txn["sources"])
            reason = _md_escape(txn["reason"] or "")
            lines.append(
                f"| {_fmt_secs(txn['t_start'])} | {sources} | {_md_escape(txn['attempted'])} "
                f"| {txn['outcome']}{flag} | {reason} |"
            )
    else:
        lines.append("_No cross-source activity recorded._")
    lines.append("")

    lines.append("## Flagged (failure candidates)")
    lines.append("")
    if flagged:
        for txn in flagged:
            tags = []
            if txn["failure"]:
                tags.append("FAILURE")
            if txn["out_of_range"]:
                tags.append(f"OUT-OF-RANGE {txn['out_of_range_ids']}")
            lines.append(f"### {txn['id']} @ {_fmt_secs(txn['t_start'])} - {', '.join(tags)}")
            lines.append("")
            lines.append(f"- **Attempted:** {txn['attempted']}")
            lines.append(f"- **Outcome:** {txn['outcome']}")
            if txn["reason"]:
                lines.append(f"- **Reason:** {txn['reason']}")
            lines.append(f"- **Sources:** {', '.join(txn['sources'])}")
            lines.append("")
            lines.append("Steps:")
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(txn["steps"], indent=2, ensure_ascii=False))
            lines.append("```")
            lines.append("")
    else:
        lines.append("_None — no rejected/reverted steps and nothing outside the validation range._")
    lines.append("")

    return "\n".join(lines)


def write_summary(document: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_summary(document), encoding="utf-8")


def write_outputs(document: dict[str, Any], session_dir: Path, session_id: str) -> tuple[Path, Path]:
    json_path = session_dir / f"session_{session_id}.json"
    summary_path = session_dir / f"session_{session_id}.summary.md"
    write_json(document, json_path)
    write_summary(document, summary_path)
    return json_path, summary_path
