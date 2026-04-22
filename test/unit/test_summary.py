"""Unit tests for DecisionLogger — Phase 4 observability methods.

Tests: summarize(), find_by_request_id(), make_decision_record() status/error_category.
"""

from __future__ import annotations

import pytest

from switchboard.domain.decision_record import DecisionRecord
from switchboard.domain.selection_context import SelectionContext
from switchboard.domain.selection_result import SelectionResult
from switchboard.services.decision_logger import DecisionLogger, SummaryStats, make_decision_record


def _make_record(
    *,
    request_id: str | None = None,
    selected_lane: str = "fast",
    selected_backend: str = "kodo",
    rule_name: str = "default_short_request",
    status: str = "success",
    error_category: str | None = None,
    latency_ms: float | None = 10.0,
) -> DecisionRecord:
    return DecisionRecord(
        timestamp="2026-04-20T12:00:00+00:00",
        selected_lane=selected_lane,
        selected_backend=selected_backend,
        rule_name=rule_name,
        status=status,
        error_category=error_category,
        request_id=request_id,
        latency_ms=latency_ms,
    )


def _make_logger(*records: DecisionRecord) -> DecisionLogger:
    logger = DecisionLogger(log_path=None)
    for r in records:
        logger._buffer.append(r)
    return logger


# ---------------------------------------------------------------------------
# find_by_request_id
# ---------------------------------------------------------------------------


class TestFindByRequestId:
    def test_finds_existing_record(self) -> None:
        r = _make_record(request_id="abc123")
        logger = _make_logger(r)
        assert logger.find_by_request_id("abc123") is r

    def test_returns_none_for_unknown_id(self) -> None:
        r = _make_record(request_id="abc123")
        logger = _make_logger(r)
        assert logger.find_by_request_id("notfound") is None

    def test_returns_most_recent_on_duplicate(self) -> None:
        older = _make_record(request_id="dup", latency_ms=5.0)
        newer = _make_record(request_id="dup", latency_ms=99.0)
        logger = _make_logger(older, newer)
        result = logger.find_by_request_id("dup")
        assert result is newer

    def test_empty_buffer_returns_none(self) -> None:
        logger = _make_logger()
        assert logger.find_by_request_id("x") is None


# ---------------------------------------------------------------------------
# summarize
# ---------------------------------------------------------------------------


class TestSummarize:
    def test_empty_logger_returns_zero_stats(self) -> None:
        stats = _make_logger().summarize()
        assert stats.total == 0
        assert stats.success_count == 0
        assert stats.error_count == 0
        assert stats.latency_p50_ms is None

    def test_all_success_counts_correctly(self) -> None:
        records = [_make_record(status="success") for _ in range(5)]
        stats = _make_logger(*records).summarize()
        assert stats.total == 5
        assert stats.success_count == 5
        assert stats.error_count == 0

    def test_error_records_counted_separately(self) -> None:
        ok = [_make_record(status="success") for _ in range(3)]
        err = [_make_record(status="error", error_category="upstream_timeout") for _ in range(2)]
        stats = _make_logger(*ok, *err).summarize()
        assert stats.success_count == 3
        assert stats.error_count == 2

    def test_error_category_counts_aggregated(self) -> None:
        records = [
            _make_record(status="error", error_category="upstream_timeout"),
            _make_record(status="error", error_category="upstream_timeout"),
            _make_record(status="error", error_category="upstream_error"),
        ]
        stats = _make_logger(*records).summarize()
        assert stats.error_category_counts["upstream_timeout"] == 2
        assert stats.error_category_counts["upstream_error"] == 1

    def test_lane_counts_aggregated(self) -> None:
        records = [
            _make_record(selected_lane="fast"),
            _make_record(selected_lane="fast"),
            _make_record(selected_lane="capable"),
        ]
        stats = _make_logger(*records).summarize()
        assert stats.lane_counts["fast"] == 2
        assert stats.lane_counts["capable"] == 1

    def test_backend_counts_aggregated(self) -> None:
        records = [
            _make_record(selected_backend="kodo"),
            _make_record(selected_backend="kodo"),
            _make_record(selected_backend="direct_local"),
        ]
        stats = _make_logger(*records).summarize()
        assert stats.backend_counts["kodo"] == 2
        assert stats.backend_counts["direct_local"] == 1

    def test_rule_counts_aggregated(self) -> None:
        records = [
            _make_record(rule_name="coding_task"),
            _make_record(rule_name="coding_task"),
            _make_record(rule_name="default_short_request"),
        ]
        stats = _make_logger(*records).summarize()
        assert stats.rule_counts["coding_task"] == 2
        assert stats.rule_counts["default_short_request"] == 1

    def test_latency_stats_computed(self) -> None:
        records = [_make_record(latency_ms=float(v)) for v in [10, 20, 30, 40, 100]]
        stats = _make_logger(*records).summarize()
        assert stats.latency_p50_ms is not None
        assert stats.latency_mean_ms is not None
        assert stats.latency_p95_ms is not None

    def test_latency_excludes_error_records(self) -> None:
        records = [
            _make_record(status="success", latency_ms=10.0),
            _make_record(status="error", latency_ms=9999.0, error_category="upstream_error"),
        ]
        stats = _make_logger(*records).summarize()
        assert stats.latency_mean_ms == pytest.approx(10.0)

    def test_window_limits_records_used(self) -> None:
        records = [_make_record(selected_lane="fast") for _ in range(10)]
        records += [_make_record(selected_lane="capable") for _ in range(5)]
        stats = _make_logger(*records).summarize(n=5)
        assert stats.total == 5
        assert stats.lane_counts.get("capable", 0) == 5
        assert stats.lane_counts.get("fast", 0) == 0

    def test_no_latency_when_all_errors(self) -> None:
        records = [_make_record(status="error", error_category="internal_error", latency_ms=5.0)]
        stats = _make_logger(*records).summarize()
        assert stats.latency_p50_ms is None
        assert stats.latency_mean_ms is None

    def test_returns_summarystat_instance(self) -> None:
        stats = _make_logger(_make_record()).summarize()
        assert isinstance(stats, SummaryStats)


# ---------------------------------------------------------------------------
# make_decision_record — status / error_category
# ---------------------------------------------------------------------------


def _make_result(request_id: str | None = None) -> SelectionResult:
    ctx = SelectionContext(
        messages=[{"role": "user", "content": "hi"}],
        model_hint="fast",
        extra={"request_id": request_id} if request_id else {},
    )
    return SelectionResult(
        profile_name="fast",
        downstream_model="gpt-4o-mini",
        rule_name="default_short_request",
        reason="rule:default_short_request → profile:fast",
        context=ctx,
    )


class TestMakeDecisionRecord:
    def test_success_status_when_no_error(self) -> None:
        result = make_decision_record(result=_make_result(), original_model_hint="fast")
        assert result.status == "success"
        assert result.error_category is None

    def test_error_status_when_error_provided(self) -> None:
        result = make_decision_record(
            result=_make_result(),
            original_model_hint="fast",
            error="connection refused",
        )
        assert result.status == "error"

    def test_error_category_propagated(self) -> None:
        result = make_decision_record(
            result=_make_result(),
            original_model_hint="fast",
            error="timeout",
            error_category="upstream_timeout",
        )
        assert result.error_category == "upstream_timeout"

    def test_request_id_from_context_extra(self) -> None:
        result = make_decision_record(result=_make_result("req-abc"), original_model_hint="")
        assert result.request_id == "req-abc"

    def test_no_request_id_when_not_in_extra(self) -> None:
        result = make_decision_record(result=_make_result(), original_model_hint="")
        assert result.request_id is None

    def test_latency_ms_passed_through(self) -> None:
        result = make_decision_record(
            result=_make_result(), original_model_hint="", latency_ms=42.5
        )
        assert result.latency_ms == pytest.approx(42.5)
