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
from pathlib import Path
from statistics import mean, median

from switchboard.adapters.jsonl_decision_sink import JsonlDecisionSink
from switchboard.domain.decision_record import DecisionRecord
from switchboard.observability.logging import get_logger

logger = get_logger(__name__)

_BUFFER_SIZE = 1000  # maximum in-memory records


@dataclass
class SummaryStats:
    """Aggregated statistics over a window of decision records."""

    total: int = 0
    success_count: int = 0
    error_count: int = 0
    # lane → request count
    lane_counts: dict[str, int] = field(default_factory=dict)
    # backend → request count
    backend_counts: dict[str, int] = field(default_factory=dict)
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

            if r.selected_lane:
                stats.lane_counts[r.selected_lane] = stats.lane_counts.get(r.selected_lane, 0) + 1

            if r.selected_backend:
                stats.backend_counts[r.selected_backend] = (
                    stats.backend_counts.get(r.selected_backend, 0) + 1
                )

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
