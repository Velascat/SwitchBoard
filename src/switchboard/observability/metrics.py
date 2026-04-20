"""Metrics stubs for SwitchBoard.

This module defines simple in-process counters that can be exposed via a
``/metrics`` endpoint in a future iteration.  The current implementation uses
plain Python integers wrapped in a thin ``Counter`` class so that the call
sites are already instrumented and a real Prometheus client can be dropped in
without changing any other code.

Usage::

    from switchboard.observability.metrics import requests_total, decisions_total

    requests_total.inc()
    decisions_total.inc(labels={"profile": "fast", "rule": "short_context"})
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any


class Counter:
    """A minimal monotonically increasing counter with optional label support."""

    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description
        self._total: int = 0
        self._labelled: dict[tuple, int] = defaultdict(int)

    def inc(self, amount: int = 1, labels: dict[str, Any] | None = None) -> None:
        """Increment the counter.

        Args:
            amount: How much to add (default 1).
            labels: Optional label dict for dimensioned tracking.
        """
        self._total += amount
        if labels:
            key = tuple(sorted(labels.items()))
            self._labelled[key] += amount

    @property
    def value(self) -> int:
        """Total count across all label combinations."""
        return self._total

    def labelled_value(self, labels: dict[str, Any]) -> int:
        """Return the count for a specific label combination."""
        key = tuple(sorted(labels.items()))
        return self._labelled.get(key, 0)

    def __repr__(self) -> str:
        return f"Counter(name={self.name!r}, value={self._total})"


# ---------------------------------------------------------------------------
# Module-level counter instances
# ---------------------------------------------------------------------------

requests_total = Counter(
    name="switchboard_requests_total",
    description="Total number of chat completion requests received by SwitchBoard.",
)

decisions_total = Counter(
    name="switchboard_decisions_total",
    description="Total number of routing decisions made, labelled by profile and rule.",
)

forwarding_errors_total = Counter(
    name="switchboard_forwarding_errors_total",
    description="Total number of errors encountered when forwarding to 9router.",
)
