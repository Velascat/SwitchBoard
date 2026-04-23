"""Unit tests for SignalAggregator and ProfileSignals."""

from __future__ import annotations

import pytest

from switchboard.domain.decision_record import DecisionRecord
from switchboard.services.signal_aggregator import ProfileSignals, SignalAggregator


def _record(
    lane: str,
    status: str = "success",
    latency_ms: float | None = 100.0,
) -> DecisionRecord:
    return DecisionRecord(
        timestamp="2024-01-01T00:00:00+00:00",
        selected_lane=lane,
        selected_backend="kodo",
        rule_name="test",
        reason="test",
        status=status,
        latency_ms=latency_ms if status != "error" else None,
    )


# ---------------------------------------------------------------------------
# ProfileSignals computed properties
# ---------------------------------------------------------------------------


class TestProfileSignals:
    def test_error_rate_zero_requests(self) -> None:
        sig = ProfileSignals(profile="capable")
        assert sig.error_rate == 0.0

    def test_error_rate_calculation(self) -> None:
        sig = ProfileSignals(profile="capable", total_requests=10, error_count=3)
        assert sig.error_rate == pytest.approx(0.3)

    def test_mean_latency_none_when_no_latencies(self) -> None:
        sig = ProfileSignals(profile="fast")
        assert sig.mean_latency_ms is None

    def test_mean_latency(self) -> None:
        sig = ProfileSignals(profile="fast", _latencies_ms=[100.0, 200.0, 300.0])
        assert sig.mean_latency_ms == pytest.approx(200.0)

    def test_p50_latency(self) -> None:
        sig = ProfileSignals(profile="fast", _latencies_ms=[100.0, 200.0, 300.0])
        assert sig.p50_latency_ms == pytest.approx(200.0)

    def test_p95_latency(self) -> None:
        latencies = list(range(1, 101))  # 1..100
        sig = ProfileSignals(profile="fast", _latencies_ms=[float(x) for x in latencies])
        # p95 index = max(0, int(100 * 0.95) - 1) = max(0, 94) = index 94 → value 95
        assert sig.p95_latency_ms == pytest.approx(95.0)

    def test_p50_none_when_no_latencies(self) -> None:
        sig = ProfileSignals(profile="fast")
        assert sig.p50_latency_ms is None


# ---------------------------------------------------------------------------
# SignalAggregator.aggregate
# ---------------------------------------------------------------------------


class TestSignalAggregator:
    def setup_method(self) -> None:
        self.agg = SignalAggregator()

    def test_empty_records_returns_empty_dict(self) -> None:
        result = self.agg.aggregate([])
        assert result == {}

    def test_counts_requests_per_lane(self) -> None:
        records = [_record("capable")] * 5 + [_record("fast")] * 3
        result = self.agg.aggregate(records)
        assert result["capable"].total_requests == 5
        assert result["fast"].total_requests == 3

    def test_counts_errors_correctly(self) -> None:
        records = [
            _record("capable", status="success"),
            _record("capable", status="error"),
            _record("capable", status="error"),
        ]
        result = self.agg.aggregate(records)
        assert result["capable"].error_count == 2
        assert result["capable"].error_rate == pytest.approx(2 / 3)

    def test_error_latency_not_included(self) -> None:
        records = [
            _record("capable", status="success", latency_ms=100.0),
            _record("capable", status="error", latency_ms=None),
        ]
        result = self.agg.aggregate(records)
        sig = result["capable"]
        assert len(sig._latencies_ms) == 1
        assert sig._latencies_ms[0] == pytest.approx(100.0)

    def test_skips_records_without_lane(self) -> None:
        record = DecisionRecord(
            timestamp="2024-01-01T00:00:00+00:00",
            selected_lane="",
            selected_backend="kodo",
            rule_name="test",
            reason="test",
        )
        result = self.agg.aggregate([record])
        assert result == {}

    def test_latencies_collected_for_success_only(self) -> None:
        records = [
            _record("fast", status="success", latency_ms=50.0),
            _record("fast", status="success", latency_ms=150.0),
            _record("fast", status="error", latency_ms=None),
        ]
        result = self.agg.aggregate(records)
        sig = result["fast"]
        assert sig.total_requests == 3
        assert sig.error_count == 1
        assert len(sig._latencies_ms) == 2
