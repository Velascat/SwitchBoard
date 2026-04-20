"""DecisionLog — persists routing decisions and provides a recent-N query.

Each decision is appended as a JSON line to a JSONL file on disk (if
``log_path`` is set) and always kept in an in-memory ring buffer so that
``/admin/decisions/recent`` can return results even before the first flush.

Thread / async safety: appending to a deque and writing to a file in an
asyncio context is safe as long as we do not ``await`` between the deque
append and the file write (both are synchronous).  For production use with
multiple workers, a proper database or structured log aggregator should
replace this implementation.
"""

from __future__ import annotations

import json
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import IO

from switchboard.domain.models import DecisionRecord
from switchboard.observability.logging import get_logger

logger = get_logger(__name__)

_BUFFER_SIZE = 1000  # maximum in-memory records


class DecisionLog:
    """Append-only log of routing decisions with an in-memory ring buffer."""

    def __init__(self, log_path: Path | None) -> None:
        """Initialise the log.

        Args:
            log_path: Path to the JSONL file to append to, or ``None`` to
                      disable disk persistence.
        """
        self._path = log_path
        self._buffer: deque[DecisionRecord] = deque(maxlen=_BUFFER_SIZE)
        self._file: IO[str] | None = None

        if log_path is not None:
            try:
                self._file = log_path.open("a", encoding="utf-8")
                logger.info("Decision log opened at %s", log_path)
            except OSError as exc:
                logger.warning("Could not open decision log at %s: %s", log_path, exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def append(self, record: DecisionRecord) -> None:
        """Append a decision record to the in-memory buffer and disk log."""
        self._buffer.append(record)
        if self._file is not None:
            try:
                self._file.write(record.model_dump_json() + "\n")
                self._file.flush()
            except OSError as exc:
                logger.warning("Failed to write decision record: %s", exc)

    def last_n(self, n: int) -> list[DecisionRecord]:
        """Return the most recent ``n`` decision records, newest last."""
        records = list(self._buffer)
        return records[-n:] if len(records) > n else records

    def record(self, decision: DecisionRecord) -> None:
        """Alias for :meth:`append` — satisfies the :class:`DecisionSink` port."""
        self.append(decision)

    def close(self) -> None:
        """Close the underlying file handle if open."""
        if self._file is not None:
            self._file.close()
            self._file = None


# ---------------------------------------------------------------------------
# Factory helper
# ---------------------------------------------------------------------------

def make_decision_record(
    *,
    result,  # SelectionResult
    original_model_hint: str,
    latency_ms: float | None = None,
    error: str | None = None,
) -> DecisionRecord:
    """Build a :class:`DecisionRecord` from a :class:`SelectionResult`."""
    return DecisionRecord(
        timestamp=datetime.now(timezone.utc).isoformat(),
        request_id=result.context.extra.get("request_id"),
        original_model_hint=original_model_hint,
        profile_name=result.profile_name,
        downstream_model=result.downstream_model,
        rule_name=result.rule_name,
        latency_ms=latency_ms,
        tenant_id=result.context.tenant_id,
        error=error,
    )
