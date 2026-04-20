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
from datetime import datetime, timezone
from pathlib import Path

from switchboard.adapters.jsonl_decision_sink import JsonlDecisionSink
from switchboard.domain.decision_record import DecisionRecord
from switchboard.domain.selection_result import SelectionResult
from switchboard.observability.logging import get_logger

logger = get_logger(__name__)

_BUFFER_SIZE = 1000  # maximum in-memory records


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
) -> DecisionRecord:
    """Build a :class:`DecisionRecord` from a :class:`SelectionResult`."""
    context = result.context
    request_id = context.extra.get("request_id") if context and context.extra else None
    tenant_id = context.tenant_id if context else None

    profile_name = result.profile_name or result.profile

    return DecisionRecord(
        timestamp=datetime.now(timezone.utc).isoformat(),
        client=tenant_id,
        task_type=context.task_type if context else None,
        selected_profile=profile_name,
        downstream_model=result.downstream_model,
        rule_name=result.rule_name,
        reason=result.reason,
        request_id=request_id,
        original_model_hint=original_model_hint,
        profile_name=profile_name,
        latency_ms=latency_ms,
        tenant_id=tenant_id,
        error=error,
    )
