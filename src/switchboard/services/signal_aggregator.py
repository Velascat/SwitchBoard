"""SignalAggregator — aggregate per-profile performance signals from decision history."""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean, median
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from switchboard.domain.decision_record import DecisionRecord


@dataclass
class ProfileSignals:
    """Aggregated performance signals for a single profile over a window of records."""

    profile: str
    total_requests: int = 0
    error_count: int = 0
    _latencies_ms: list[float] = field(default_factory=list, repr=False)

    @property
    def error_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.error_count / self.total_requests

    @property
    def mean_latency_ms(self) -> float | None:
        if not self._latencies_ms:
            return None
        return mean(self._latencies_ms)

    @property
    def p50_latency_ms(self) -> float | None:
        if not self._latencies_ms:
            return None
        return median(sorted(self._latencies_ms))

    @property
    def p95_latency_ms(self) -> float | None:
        if not self._latencies_ms:
            return None
        s = sorted(self._latencies_ms)
        idx = max(0, int(len(s) * 0.95) - 1)
        return s[idx]


class SignalAggregator:
    """Aggregate a list of DecisionRecords into per-profile ProfileSignals."""

    def aggregate(self, records: list[DecisionRecord]) -> dict[str, ProfileSignals]:
        """Return a mapping of profile name → ProfileSignals.

        Only profiles with at least one record are included.
        """
        signals: dict[str, ProfileSignals] = {}
        for record in records:
            profile = record.selected_profile or record.profile_name
            if not profile:
                continue
            if profile not in signals:
                signals[profile] = ProfileSignals(profile=profile)
            sig = signals[profile]
            sig.total_requests += 1
            if record.status == "error":
                sig.error_count += 1
            elif record.latency_ms is not None:
                sig._latencies_ms.append(record.latency_ms)
        return signals
