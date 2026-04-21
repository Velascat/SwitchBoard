"""DecisionLogger — persists routing decisions and provides a recent-N query.

Each decision is appended via the configured :class:`JsonlDecisionSink` (if
``log_path`` is set) and always kept in an in-memory ring buffer so that
``/admin/decisions/recent`` can return results even before the first flush.

Thread / async safety: appending to a deque and writing to a file in an
asyncio context is safe as long as we do not ``await`` between the deque
append and the file write (both are synchronous).  For production use with
multiple workers, a proper database or structured log aggregator should
replace this implementation.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any

from switchboard.adapters.jsonl_decision_sink import JsonlDecisionSink
from switchboard.domain.decision_record import DecisionRecord
from switchboard.domain.selection_result import SelectionResult
from switchboard.observability.logging import get_logger

logger = get_logger(__name__)

_BUFFER_SIZE = 1000  # maximum in-memory records


@dataclass
class SummaryStats:
    """Aggregated statistics over a window of decision records."""

    total: int = 0
    success_count: int = 0
    error_count: int = 0
    # profile → request count
    profile_counts: dict[str, int] = field(default_factory=dict)
    # rule → request count
    rule_counts: dict[str, int] = field(default_factory=dict)
    # error_category → count (errors only)
    error_category_counts: dict[str, int] = field(default_factory=dict)
    # latency stats across successful requests (ms)
    latency_p50_ms: float | None = None
    latency_p95_ms: float | None = None
    latency_mean_ms: float | None = None


class DecisionLogger:
    """Append-only log of routing decisions with an in-memory ring buffer."""

    def __init__(self, log_path: Path | None) -> None:
        """Initialise the logger.

        Args:
            log_path: Path to the JSONL file to append to, or ``None`` to
                      disable disk persistence.
        """
        self._buffer: deque[DecisionRecord] = deque(maxlen=_BUFFER_SIZE)
        self._sink = JsonlDecisionSink(log_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def append(self, record: DecisionRecord) -> None:
        """Append a decision record to the in-memory buffer and disk log."""
        self._buffer.append(record)
        self._sink.record(record)

    def last_n(self, n: int) -> list[DecisionRecord]:
        """Return the most recent ``n`` decision records, newest last."""
        records = list(self._buffer)
        return records[-n:] if len(records) > n else records

    def find_by_request_id(self, request_id: str) -> DecisionRecord | None:
        """Return the most recent record matching ``request_id``, or ``None``."""
        for record in reversed(self._buffer):
            if record.request_id == request_id:
                return record
        return None

    def summarize(self, n: int = 100) -> SummaryStats:
        """Aggregate the last ``n`` records into a :class:`SummaryStats` snapshot."""
        records = self.last_n(n)
        stats = SummaryStats(total=len(records))

        latencies: list[float] = []
        for r in records:
            if r.status == "error":
                stats.error_count += 1
                if r.error_category:
                    stats.error_category_counts[r.error_category] = (
                        stats.error_category_counts.get(r.error_category, 0) + 1
                    )
            else:
                stats.success_count += 1

            profile = r.selected_profile or r.profile_name
            if profile:
                stats.profile_counts[profile] = stats.profile_counts.get(profile, 0) + 1

            if r.rule_name:
                stats.rule_counts[r.rule_name] = stats.rule_counts.get(r.rule_name, 0) + 1

            if r.latency_ms is not None and r.status != "error":
                latencies.append(r.latency_ms)

        if latencies:
            sorted_lat = sorted(latencies)
            stats.latency_mean_ms = round(mean(sorted_lat), 2)
            stats.latency_p50_ms = round(median(sorted_lat), 2)
            p95_idx = max(0, int(len(sorted_lat) * 0.95) - 1)
            stats.latency_p95_ms = round(sorted_lat[p95_idx], 2)

        return stats

    def record(self, decision: DecisionRecord) -> None:
        """Alias for :meth:`append` — satisfies the :class:`DecisionSink` port."""
        self.append(decision)

    def close(self) -> None:
        """Close the underlying file handle if open."""
        self._sink.close()


# ---------------------------------------------------------------------------
# Factory helper
# ---------------------------------------------------------------------------


def make_decision_record(
    *,
    result: SelectionResult,
    original_model_hint: str,
    latency_ms: float | None = None,
    error: str | None = None,
    error_category: str | None = None,
) -> DecisionRecord:
    """Build a :class:`DecisionRecord` from a :class:`SelectionResult`."""
    context = result.context
    request_id = context.extra.get("request_id") if context and context.extra else None
    tenant_id = context.tenant_id if context else None
    profile_name = result.profile_name or result.profile

    context_summary: dict[str, Any] | None = None
    if context is not None:
        context_summary = {
            "task_type": context.task_type,
            "complexity": context.complexity,
            "estimated_tokens": context.estimated_tokens,
            "requires_tools": context.requires_tools,
            "requires_long_context": context.requires_long_context,
            "stream": context.stream,
            "cost_sensitivity": context.cost_sensitivity,
            "latency_sensitivity": context.latency_sensitivity,
        }

    return DecisionRecord(
        timestamp=datetime.now(timezone.utc).isoformat(),
        client=tenant_id,
        task_type=context.task_type if context else None,
        selected_profile=profile_name,
        downstream_model=result.downstream_model,
        rule_name=result.rule_name,
        reason=result.reason,
        context_summary=context_summary,
        rejected_profiles=result.rejected_profiles,
        status="error" if error else "success",
        error_category=error_category,
        request_id=request_id,
        original_model_hint=original_model_hint,
        profile_name=profile_name,
        latency_ms=latency_ms,
        tenant_id=tenant_id,
        error=error,
    )
