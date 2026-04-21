"""AdjustmentEngine — derive bounded PolicyAdjustments from ProfileSignals."""

from __future__ import annotations

from dataclasses import dataclass

from switchboard.services.signal_aggregator import ProfileSignals

# Thresholds — deterministic, inspectable, documented
_DEMOTE_MIN_REQUESTS = 5       # need at least this many samples before demoting
_DEMOTE_ERROR_RATE = 0.40      # ≥40% error rate → demote
_DEMOTE_LATENCY_MS = 8_000.0   # ≥8 s mean latency → demote

_PROMOTE_MIN_REQUESTS = 20     # need at least this many samples before promoting
_PROMOTE_MAX_ERROR_RATE = 0.02  # ≤2% error rate sustained → promote


@dataclass
class PolicyAdjustment:
    """A bounded, inspectable recommendation for a single profile.

    Attributes:
        profile:  The profile this adjustment applies to.
        action:   ``"demote"`` | ``"neutral"`` | ``"promote"``
        reason:   Human-readable explanation of why this action was derived.
    """

    profile: str
    action: str  # "demote" | "neutral" | "promote"
    reason: str


class AdjustmentEngine:
    """Derive PolicyAdjustments from ProfileSignals using explicit heuristics.

    Rules are evaluated in priority order — the first matching rule wins:
      1. High error rate  → demote
      2. High latency     → demote
      3. Sustained health → promote
      4. Otherwise        → neutral
    """

    def derive(self, signals: dict[str, ProfileSignals]) -> list[PolicyAdjustment]:
        """Return one PolicyAdjustment per profile in ``signals``."""
        return [self._evaluate(sig) for sig in signals.values()]

    def _evaluate(self, sig: ProfileSignals) -> PolicyAdjustment:
        if sig.total_requests >= _DEMOTE_MIN_REQUESTS:
            if sig.error_rate >= _DEMOTE_ERROR_RATE:
                return PolicyAdjustment(
                    profile=sig.profile,
                    action="demote",
                    reason=(
                        f"error rate {sig.error_rate:.0%} over {sig.total_requests} requests "
                        f"exceeds threshold ({_DEMOTE_ERROR_RATE:.0%})"
                    ),
                )
            mean_lat = sig.mean_latency_ms
            if mean_lat is not None and mean_lat >= _DEMOTE_LATENCY_MS:
                return PolicyAdjustment(
                    profile=sig.profile,
                    action="demote",
                    reason=(
                        f"mean latency {mean_lat:.0f} ms over {sig.total_requests} requests "
                        f"exceeds threshold ({_DEMOTE_LATENCY_MS:.0f} ms)"
                    ),
                )

        if sig.total_requests >= _PROMOTE_MIN_REQUESTS and sig.error_rate <= _PROMOTE_MAX_ERROR_RATE:
            return PolicyAdjustment(
                profile=sig.profile,
                action="promote",
                reason=(
                    f"error rate {sig.error_rate:.1%} over {sig.total_requests} requests "
                    f"below threshold ({_PROMOTE_MAX_ERROR_RATE:.0%})"
                ),
            )

        return PolicyAdjustment(
            profile=sig.profile,
            action="neutral",
            reason="within normal operating parameters",
        )
