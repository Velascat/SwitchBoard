# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Velascat
"""DecisionSink port — abstraction over where routing decisions are persisted."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from switchboard.domain.decision_record import DecisionRecord


@runtime_checkable
class DecisionSink(Protocol):
    """Contract for recording routing decisions.

    Any implementation (in-memory ring buffer, database, message queue, …)
    must satisfy this protocol.
    """

    def record(self, decision: DecisionRecord) -> None:
        """Persist a single routing decision.

        Args:
            decision: The :class:`DecisionRecord` to store.
        """
        ...
