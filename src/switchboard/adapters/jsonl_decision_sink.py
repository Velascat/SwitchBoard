"""JsonlDecisionSink — appends DecisionRecord entries to a JSONL file.

Implements the :class:`~switchboard.ports.decision_sink.DecisionSink` port.

Each decision is appended as a single JSON line so that the log file can be
streamed, tail-followed, or processed line-by-line with standard tooling.

Thread / async safety: appending to a file is synchronous.  For production use
with multiple workers, a proper structured log aggregator should replace this
implementation.
"""

from __future__ import annotations

from pathlib import Path
from typing import IO

from switchboard.domain.decision_record import DecisionRecord
from switchboard.observability.logging import get_logger

logger = get_logger(__name__)


class JsonlDecisionSink:
    """Appends :class:`DecisionRecord` objects to a JSONL file."""

    def __init__(self, log_path: Path | None) -> None:
        """Initialise the sink.

        Args:
            log_path: Path to the JSONL file to append to, or ``None`` to
                      disable disk persistence.
        """
        self._path = log_path
        self._file: IO[str] | None = None

        if log_path is not None:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                self._file = log_path.open("a", encoding="utf-8")
                logger.info("JSONL decision sink opened at %s", log_path)
            except OSError as exc:
                logger.warning(
                    "Could not open JSONL decision sink at %s: %s", log_path, exc
                )

    # ------------------------------------------------------------------
    # DecisionSink protocol
    # ------------------------------------------------------------------

    def record(self, decision: DecisionRecord) -> None:
        """Append a decision record to the JSONL file.

        Args:
            decision: The :class:`DecisionRecord` to persist.
        """
        if self._file is not None:
            try:
                self._file.write(decision.model_dump_json() + "\n")
                self._file.flush()
            except OSError as exc:
                logger.warning("Failed to write decision record: %s", exc)

    def close(self) -> None:
        """Close the underlying file handle if open."""
        if self._file is not None:
            self._file.close()
            self._file = None
