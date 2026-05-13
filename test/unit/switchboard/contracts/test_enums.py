# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 ProtocolWarden
# ruff: noqa: S101
"""Unit tests for contracts/enums.py."""
from __future__ import annotations

from switchboard.contracts.enums import (
    BackendName,
    ExecutionMode,
    LaneName,
    Priority,
    RiskLevel,
    TaskType,
)


def test_task_type_values_are_strings() -> None:
    assert TaskType.BUG_FIX == "bug_fix"
    assert TaskType.FEATURE == "feature"
    assert TaskType.UNKNOWN == "unknown"


def test_lane_name_values() -> None:
    assert LaneName.CLAUDE_CLI == "claude_cli"
    assert LaneName.AIDER_LOCAL == "aider_local"


def test_backend_name_values() -> None:
    assert BackendName.ARCHON == "archon"
    assert BackendName.DEMO_STUB == "demo_stub"


def test_execution_mode_values() -> None:
    assert ExecutionMode.GOAL == "goal"
    assert ExecutionMode.FIX_PR == "fix_pr"


def test_risk_level_values() -> None:
    assert RiskLevel.LOW == "low"
    assert RiskLevel.HIGH == "high"


def test_priority_values() -> None:
    assert Priority.NORMAL == "normal"
    assert Priority.CRITICAL == "critical"


def test_enums_are_str_subclass() -> None:
    assert isinstance(TaskType.FEATURE, str)
    assert isinstance(LaneName.CLAUDE_CLI, str)
    assert isinstance(BackendName.ARCHON, str)
