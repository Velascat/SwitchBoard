"""DecisionSink port — abstraction over where routing decisions are persisted."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from switchboard.domain.models import DecisionRecord


@runtime_checkable
class DecisionSink(Protocol):
    """Contract for recording routing decisions.

    Any implementation (in-memory ring buffer, database, message queue, …)
    must satisfy this protocol.  The :class:`~switchboard.services.forwarder.Forwarder`
    depends only on this interface.
    """

    def record(self, decision: DecisionRecord) -> None:
        """Persist a single routing decision.

        Args:
            decision: The :class:`DecisionRecord` to store.
        """
        ...
