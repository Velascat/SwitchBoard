"""AdjustmentStore — operator-controllable cache of derived PolicyAdjustments."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from switchboard.domain.decision_record import DecisionRecord

from switchboard.services.adjustment_engine import AdjustmentEngine, PolicyAdjustment
from switchboard.services.signal_aggregator import SignalAggregator


@dataclass
class AdjustmentStoreState:
    """A snapshot of the current AdjustmentStore state for operator inspection."""

    enabled: bool
    adjustment_count: int
    demoted_profiles: list[str]
    promoted_profiles: list[str]
    last_refresh: str | None  # ISO-8601 UTC or None if never refreshed
    window_size: int


class AdjustmentStore:
    """In-memory cache of derived PolicyAdjustments with operator controls.

    Adjustments are derived from a window of observed DecisionRecords via the
    AdjustmentEngine.  The cache is refreshed on demand (operator call or TTL).
    Only non-neutral adjustments are stored; everything else is implicitly neutral.

    Operator controls:
        enable() / disable() — toggle adaptation globally (default: enabled)
        reset()              — clear all adjustments, return all profiles to neutral
        refresh(records)     — recompute from the provided records immediately
        maybe_refresh(records) — recompute only if TTL has elapsed
    """

    def __init__(
        self,
        engine: AdjustmentEngine | None = None,
        *,
        window_size: int = 200,
        ttl_seconds: float = 300.0,
        enabled: bool = True,
    ) -> None:
        self._engine = engine or AdjustmentEngine()
        self._aggregator = SignalAggregator()
        self._window_size = window_size
        self._ttl_seconds = ttl_seconds
        self._enabled = enabled
        self._adjustments: dict[str, PolicyAdjustment] = {}
        self._last_refresh: datetime | None = None

    # ------------------------------------------------------------------
    # Operator controls
    # ------------------------------------------------------------------

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def window_size(self) -> int:
        return self._window_size

    def enable(self) -> None:
        """Re-enable adaptive adjustment (no-op if already enabled)."""
        self._enabled = True

    def disable(self) -> None:
        """Disable adaptive adjustment without clearing cached data."""
        self._enabled = False

    def reset(self) -> None:
        """Clear all cached adjustments, returning every profile to neutral."""
        self._adjustments = {}
        self._last_refresh = None

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def refresh(self, records: list[DecisionRecord]) -> None:
        """Recompute adjustments from the given records and update the cache."""
        signals = self._aggregator.aggregate(records)
        new_adjustments: dict[str, PolicyAdjustment] = {}
        for adj in self._engine.derive(signals):
            if adj.action != "neutral":
                new_adjustments[adj.profile] = adj
        self._adjustments = new_adjustments
        self._last_refresh = datetime.now(timezone.utc)

    def maybe_refresh(self, records: list[DecisionRecord]) -> None:
        """Refresh only if the cache is stale (TTL exceeded or never populated)."""
        if self._last_refresh is None:
            self.refresh(records)
            return
        age = (datetime.now(timezone.utc) - self._last_refresh).total_seconds()
        if age >= self._ttl_seconds:
            self.refresh(records)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_adjustment(self, profile: str) -> PolicyAdjustment | None:
        """Return the cached adjustment for ``profile``, or ``None`` if neutral."""
        return self._adjustments.get(profile)

    def get_all_adjustments(self) -> list[PolicyAdjustment]:
        """Return all non-neutral adjustments."""
        return list(self._adjustments.values())

    def get_state(self) -> AdjustmentStoreState:
        """Return an inspectable snapshot of the current store state."""
        demoted = sorted(p for p, a in self._adjustments.items() if a.action == "demote")
        promoted = sorted(p for p, a in self._adjustments.items() if a.action == "promote")
        return AdjustmentStoreState(
            enabled=self._enabled,
            adjustment_count=len(self._adjustments),
            demoted_profiles=demoted,
            promoted_profiles=promoted,
            last_refresh=self._last_refresh.isoformat() if self._last_refresh else None,
            window_size=self._window_size,
        )
