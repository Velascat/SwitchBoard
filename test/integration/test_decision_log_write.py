"""Acceptance test: JSONL decision records are written to disk.

Verifies that a routed chat request produces a JSONL entry containing the
selected profile and downstream model — as required by Phase 1 acceptance
criterion D.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from switchboard.adapters.jsonl_decision_sink import JsonlDecisionSink
from switchboard.domain.decision_record import DecisionRecord
from switchboard.domain.selection_context import SelectionContext
from switchboard.domain.selection_result import SelectionResult
from switchboard.services.decision_logger import DecisionLogger, make_decision_record


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(
    profile: str = "fast",
    downstream_model: str = "gpt-4o-mini",
    rule_name: str = "default_short_request",
) -> SelectionResult:
    ctx = SelectionContext(
        messages=[{"role": "user", "content": "hello"}],
        model_hint=profile,
        estimated_tokens=5,
    )
    return SelectionResult(
        profile=profile,
        profile_name=profile,
        downstream_model=downstream_model,
        rule_name=rule_name,
        context=ctx,
    )


# ---------------------------------------------------------------------------
# JsonlDecisionSink — disk I/O
# ---------------------------------------------------------------------------


class TestJsonlDecisionSinkDiskIO:
    def test_record_written_to_file(self, tmp_path: Path) -> None:
        log_file = tmp_path / "decisions.jsonl"
        sink = JsonlDecisionSink(log_file)

        record = DecisionRecord(
            timestamp="2026-04-20T17:00:00Z",
            selected_profile="fast",
            downstream_model="gpt-4o-mini",
            rule_name="default_short_request",
            profile_name="fast",
        )
        sink.record(record)
        sink.close()

        assert log_file.exists(), "JSONL file was not created"
        lines = log_file.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1, f"Expected 1 line, got {len(lines)}"

    def test_record_is_valid_json(self, tmp_path: Path) -> None:
        log_file = tmp_path / "decisions.jsonl"
        sink = JsonlDecisionSink(log_file)

        record = DecisionRecord(
            timestamp="2026-04-20T17:00:00Z",
            selected_profile="capable",
            downstream_model="gpt-4o",
            rule_name="tool_use",
            profile_name="capable",
        )
        sink.record(record)
        sink.close()

        line = log_file.read_text(encoding="utf-8").strip()
        parsed = json.loads(line)
        assert isinstance(parsed, dict)

    def test_record_fields_match_input(self, tmp_path: Path) -> None:
        log_file = tmp_path / "decisions.jsonl"
        sink = JsonlDecisionSink(log_file)

        record = DecisionRecord(
            timestamp="2026-04-20T17:00:00Z",
            selected_profile="local",
            downstream_model="llama3",
            rule_name="low_priority_local",
            profile_name="local",
            latency_ms=123.4,
        )
        sink.record(record)
        sink.close()

        parsed = json.loads(log_file.read_text(encoding="utf-8").strip())
        assert parsed["selected_profile"] == "local"
        assert parsed["downstream_model"] == "llama3"
        assert parsed["rule_name"] == "low_priority_local"
        assert parsed["latency_ms"] == pytest.approx(123.4)

    def test_multiple_records_appended(self, tmp_path: Path) -> None:
        log_file = tmp_path / "decisions.jsonl"
        sink = JsonlDecisionSink(log_file)

        for i, profile in enumerate(["fast", "capable", "local"]):
            sink.record(
                DecisionRecord(
                    timestamp=f"2026-04-20T17:0{i}:00Z",
                    selected_profile=profile,
                    downstream_model=f"model-{i}",
                    rule_name="test",
                    profile_name=profile,
                )
            )
        sink.close()

        lines = log_file.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 3

        profiles = [json.loads(line)["selected_profile"] for line in lines]
        assert profiles == ["fast", "capable", "local"]

    def test_parent_directory_created_automatically(self, tmp_path: Path) -> None:
        nested = tmp_path / "runtime" / "logs" / "decisions.jsonl"
        sink = JsonlDecisionSink(nested)
        sink.record(
            DecisionRecord(
                timestamp="2026-04-20T17:00:00Z",
                selected_profile="fast",
                downstream_model="gpt-4o-mini",
                rule_name="test",
                profile_name="fast",
            )
        )
        sink.close()
        assert nested.exists()

    def test_none_path_does_not_create_file(self, tmp_path: Path) -> None:
        sink = JsonlDecisionSink(None)
        sink.record(
            DecisionRecord(
                timestamp="2026-04-20T17:00:00Z",
                selected_profile="fast",
                downstream_model="gpt-4o-mini",
                rule_name="test",
                profile_name="fast",
            )
        )
        sink.close()
        assert not any(tmp_path.iterdir())


# ---------------------------------------------------------------------------
# DecisionLogger — in-memory buffer + disk
# ---------------------------------------------------------------------------


class TestDecisionLoggerWithDisk:
    def test_append_writes_to_disk(self, tmp_path: Path) -> None:
        log_file = tmp_path / "decisions.jsonl"
        logger = DecisionLogger(log_file)

        result = _make_result()
        record = make_decision_record(
            result=result,
            original_model_hint="fast",
            latency_ms=200.0,
        )
        logger.append(record)
        logger.close()

        lines = log_file.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["selected_profile"] == "fast"
        assert parsed["downstream_model"] == "gpt-4o-mini"

    def test_last_n_returns_from_buffer(self, tmp_path: Path) -> None:
        logger = DecisionLogger(None)

        for i in range(5):
            result = _make_result(profile=f"profile_{i}", downstream_model=f"model_{i}")
            record = make_decision_record(result=result, original_model_hint="", latency_ms=float(i))
            logger.append(record)

        recent = logger.last_n(3)
        assert len(recent) == 3
        assert recent[-1].selected_profile == "profile_4"

    def test_decision_record_has_required_phase1_fields(self, tmp_path: Path) -> None:
        log_file = tmp_path / "decisions.jsonl"
        logger = DecisionLogger(log_file)

        result = _make_result(profile="capable", downstream_model="gpt-4o", rule_name="tool_use")
        record = make_decision_record(
            result=result,
            original_model_hint="gpt-4o",
            latency_ms=350.5,
        )
        logger.append(record)
        logger.close()

        parsed = json.loads(log_file.read_text(encoding="utf-8").strip())

        # Required Phase 1 fields per section 3.3
        assert "timestamp" in parsed
        assert "selected_profile" in parsed
        assert "downstream_model" in parsed
        assert "rule_name" in parsed
        assert "latency_ms" in parsed

        assert parsed["selected_profile"] == "capable"
        assert parsed["downstream_model"] == "gpt-4o"
        assert parsed["rule_name"] == "tool_use"
        assert parsed["latency_ms"] == pytest.approx(350.5)

    def test_error_field_set_on_failure(self, tmp_path: Path) -> None:
        log_file = tmp_path / "decisions.jsonl"
        logger = DecisionLogger(log_file)

        result = _make_result()
        record = make_decision_record(
            result=result,
            original_model_hint="fast",
            latency_ms=10.0,
            error="Connection refused",
        )
        logger.append(record)
        logger.close()

        parsed = json.loads(log_file.read_text(encoding="utf-8").strip())
        assert parsed["error"] == "Connection refused"
