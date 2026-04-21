"""Unit tests for AdjustmentEngine derivation rules."""

from __future__ import annotations

import pytest

from switchboard.services.adjustment_engine import (
    AdjustmentEngine,
    PolicyAdjustment,
    _DEMOTE_ERROR_RATE,
    _DEMOTE_LATENCY_MS,
    _DEMOTE_MIN_REQUESTS,
    _PROMOTE_MAX_ERROR_RATE,
    _PROMOTE_MIN_REQUESTS,
)
from switchboard.services.signal_aggregator import ProfileSignals


def _sig(
    profile: str = "capable",
    total: int = 10,
    errors: int = 0,
    latencies: list[float] | None = None,
) -> ProfileSignals:
    sig = ProfileSignals(
        profile=profile,
        total_requests=total,
        error_count=errors,
        _latencies_ms=latencies if latencies is not None else [],
    )
    return sig


class TestAdjustmentEngineNeutral:
    def setup_method(self) -> None:
        self.engine = AdjustmentEngine()

    def test_neutral_when_insufficient_requests(self) -> None:
        sig = _sig(total=_DEMOTE_MIN_REQUESTS - 1, errors=999)
        adj = self.engine._evaluate(sig)
        assert adj.action == "neutral"

    def test_neutral_within_thresholds(self) -> None:
        sig = _sig(total=10, errors=1)  # 10% error rate
        adj = self.engine._evaluate(sig)
        assert adj.action == "neutral"

    def test_neutral_low_latency(self) -> None:
        sig = _sig(total=10, latencies=[100.0] * 10)
        adj = self.engine._evaluate(sig)
        assert adj.action == "neutral"


class TestAdjustmentEngineDemote:
    def setup_method(self) -> None:
        self.engine = AdjustmentEngine()

    def test_demotes_on_high_error_rate(self) -> None:
        errors = int(_DEMOTE_MIN_REQUESTS * _DEMOTE_ERROR_RATE) + 1
        sig = _sig(total=_DEMOTE_MIN_REQUESTS, errors=errors)
        adj = self.engine._evaluate(sig)
        assert adj.action == "demote"
        assert "error rate" in adj.reason

    def test_demotes_at_exact_error_threshold(self) -> None:
        total = 10
        errors = int(total * _DEMOTE_ERROR_RATE)  # exactly at threshold
        sig = _sig(total=total, errors=errors)
        adj = self.engine._evaluate(sig)
        assert adj.action == "demote"

    def test_demotes_on_high_latency(self) -> None:
        sig = _sig(total=_DEMOTE_MIN_REQUESTS, latencies=[_DEMOTE_LATENCY_MS + 1000.0] * 10)
        adj = self.engine._evaluate(sig)
        assert adj.action == "demote"
        assert "latency" in adj.reason

    def test_error_rate_takes_priority_over_latency(self) -> None:
        errors = int(_DEMOTE_MIN_REQUESTS * _DEMOTE_ERROR_RATE) + 1
        sig = _sig(
            total=_DEMOTE_MIN_REQUESTS,
            errors=errors,
            latencies=[_DEMOTE_LATENCY_MS + 1000.0] * 10,
        )
        adj = self.engine._evaluate(sig)
        assert adj.action == "demote"
        assert "error rate" in adj.reason

    def test_no_demote_below_min_requests_even_with_bad_error_rate(self) -> None:
        sig = _sig(total=_DEMOTE_MIN_REQUESTS - 1, errors=_DEMOTE_MIN_REQUESTS - 1)
        adj = self.engine._evaluate(sig)
        assert adj.action == "neutral"


class TestAdjustmentEnginePromote:
    def setup_method(self) -> None:
        self.engine = AdjustmentEngine()

    def test_promotes_on_sustained_health(self) -> None:
        total = _PROMOTE_MIN_REQUESTS
        errors = int(total * _PROMOTE_MAX_ERROR_RATE)  # at threshold
        sig = _sig(total=total, errors=errors)
        adj = self.engine._evaluate(sig)
        assert adj.action == "promote"
        assert "error rate" in adj.reason

    def test_no_promote_below_min_requests(self) -> None:
        sig = _sig(total=_PROMOTE_MIN_REQUESTS - 1, errors=0)
        adj = self.engine._evaluate(sig)
        assert adj.action == "neutral"

    def test_no_promote_above_error_threshold(self) -> None:
        sig = _sig(total=_PROMOTE_MIN_REQUESTS, errors=3)  # 15% > 2%
        adj = self.engine._evaluate(sig)
        # Should be neutral (not enough errors to demote, too many to promote)
        assert adj.action in ("neutral", "demote")


class TestAdjustmentEngineDerive:
    def setup_method(self) -> None:
        self.engine = AdjustmentEngine()

    def test_derive_empty_signals(self) -> None:
        result = self.engine.derive({})
        assert result == []

    def test_derive_returns_one_per_profile(self) -> None:
        signals = {
            "capable": _sig("capable", total=10),
            "fast": _sig("fast", total=10),
        }
        result = self.engine.derive(signals)
        assert len(result) == 2
        profiles = {a.profile for a in result}
        assert profiles == {"capable", "fast"}

    def test_derive_mixed_actions(self) -> None:
        errors_for_demote = int(_DEMOTE_MIN_REQUESTS * _DEMOTE_ERROR_RATE) + 1
        signals = {
            "capable": _sig("capable", total=_DEMOTE_MIN_REQUESTS, errors=errors_for_demote),
            "fast": _sig("fast", total=10, errors=0),
        }
        result = self.engine.derive(signals)
        actions = {a.profile: a.action for a in result}
        assert actions["capable"] == "demote"
        assert actions["fast"] == "neutral"

    def test_adjustment_includes_profile_name(self) -> None:
        signals = {"myprofile": _sig("myprofile")}
        result = self.engine.derive(signals)
        assert result[0].profile == "myprofile"
