from __future__ import annotations

from switchboard.domain.decision_record import DecisionRecord
from switchboard.services.decision_logger import DecisionLogger


def _record(
    *,
    request_id: str | None = None,
    selected_lane: str = "aider_local",
    selected_backend: str = "direct_local",
    rule_name: str = "local_low_risk",
    status: str = "success",
    error_category: str | None = None,
    latency_ms: float | None = 10.0,
) -> DecisionRecord:
    return DecisionRecord(
        timestamp="2026-04-20T12:00:00+00:00",
        request_id=request_id,
        selected_lane=selected_lane,
        selected_backend=selected_backend,
        rule_name=rule_name,
        reason="test",
        status=status,
        error_category=error_category,
        latency_ms=latency_ms,
    )


def _logger(*records: DecisionRecord) -> DecisionLogger:
    logger = DecisionLogger(log_path=None)
    for record in records:
        logger.append(record)
    return logger


def test_find_by_request_id_returns_latest_match() -> None:
    logger = _logger(_record(request_id="dup", latency_ms=1.0), _record(request_id="dup", latency_ms=2.0))
    assert logger.find_by_request_id("dup").latency_ms == 2.0


def test_summarize_aggregates_lane_backend_rule_and_errors() -> None:
    logger = _logger(
        _record(selected_lane="aider_local", selected_backend="direct_local"),
        _record(selected_lane="claude_cli", selected_backend="kodo"),
        _record(
            selected_lane="claude_cli",
            selected_backend="kodo",
            status="error",
            error_category="internal_error",
            latency_ms=999.0,
        ),
    )

    stats = logger.summarize()
    assert stats.total == 3
    assert stats.success_count == 2
    assert stats.error_count == 1
    assert stats.lane_counts == {"aider_local": 1, "claude_cli": 2}
    assert stats.backend_counts == {"direct_local": 1, "kodo": 2}
    assert stats.rule_counts == {"local_low_risk": 3}
    assert stats.error_category_counts == {"internal_error": 1}
    assert stats.latency_mean_ms == 10.0

