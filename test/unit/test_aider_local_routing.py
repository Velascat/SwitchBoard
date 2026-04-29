# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Velascat
"""Routing tests for the aider_local lane."""

from __future__ import annotations

import pytest
from operations_center.contracts import TaskProposal
from operations_center.contracts.common import TaskTarget
from operations_center.contracts.enums import (
    BackendName,
    ExecutionMode,
    LaneName,
    Priority,
    RiskLevel,
    TaskType,
)

from switchboard.lane.defaults import DEFAULT_POLICY
from switchboard.lane.engine import LaneSelector


def _target() -> TaskTarget:
    return TaskTarget(
        repo_key="svc",
        clone_url="https://git.example.com/svc.git",
        base_branch="main",
    )


def _proposal(
    task_type: TaskType = TaskType.LINT_FIX,
    risk_level: RiskLevel = RiskLevel.LOW,
    priority: Priority = Priority.NORMAL,
    labels: list[str] | None = None,
) -> TaskProposal:
    return TaskProposal(
        task_id="TASK-1",
        project_id="proj-1",
        task_type=task_type,
        execution_mode=ExecutionMode.GOAL,
        goal_text="do thing",
        target=_target(),
        risk_level=risk_level,
        priority=priority,
        labels=labels or [],
    )


selector = LaneSelector(DEFAULT_POLICY)


class TestAiderLocalLaneSelection:
    def test_lint_fix_low_risk_selects_aider_local(self) -> None:
        decision = selector.select(_proposal(TaskType.LINT_FIX, RiskLevel.LOW))
        assert decision.selected_lane == LaneName.AIDER_LOCAL

    def test_simple_edit_low_risk_selects_aider_local(self) -> None:
        decision = selector.select(_proposal(TaskType.SIMPLE_EDIT, RiskLevel.LOW))
        assert decision.selected_lane == LaneName.AIDER_LOCAL

    def test_documentation_low_risk_selects_aider_local(self) -> None:
        decision = selector.select(_proposal(TaskType.DOCUMENTATION, RiskLevel.LOW))
        assert decision.selected_lane == LaneName.AIDER_LOCAL

    def test_aider_local_lane_uses_aider_local_backend(self) -> None:
        decision = selector.select(_proposal(TaskType.LINT_FIX, RiskLevel.LOW))
        assert decision.selected_lane == LaneName.AIDER_LOCAL
        assert decision.selected_backend == BackendName.AIDER_LOCAL

    def test_local_only_label_forces_aider_local(self) -> None:
        decision = selector.select(_proposal(labels=["local_only"]))
        assert decision.selected_lane == LaneName.AIDER_LOCAL
        assert decision.selected_backend == BackendName.AIDER_LOCAL

    def test_major_refactor_does_not_select_aider_local(self) -> None:
        decision = selector.select(_proposal(TaskType.REFACTOR, RiskLevel.HIGH))
        assert decision.selected_lane != LaneName.AIDER_LOCAL

    def test_high_risk_bug_fix_does_not_select_aider_local(self) -> None:
        decision = selector.select(_proposal(TaskType.BUG_FIX, RiskLevel.HIGH))
        assert decision.selected_lane != LaneName.AIDER_LOCAL

    def test_feature_does_not_select_aider_local(self) -> None:
        decision = selector.select(_proposal(TaskType.FEATURE, RiskLevel.MEDIUM))
        assert decision.selected_lane != LaneName.AIDER_LOCAL

    def test_selector_does_not_execute(self) -> None:
        """LaneSelector.select() must return a decision, never trigger execution."""
        decision = selector.select(_proposal(TaskType.LINT_FIX, RiskLevel.LOW))
        assert decision is not None
        assert hasattr(decision, "selected_lane")
        assert hasattr(decision, "selected_backend")


class TestAiderLocalBackendValue:
    def test_backend_name_is_not_direct_local(self) -> None:
        decision = selector.select(_proposal(TaskType.LINT_FIX, RiskLevel.LOW))
        assert decision.selected_backend != BackendName.DIRECT_LOCAL

    def test_backend_name_is_aider_local(self) -> None:
        decision = selector.select(_proposal(TaskType.LINT_FIX, RiskLevel.LOW))
        assert decision.selected_backend == BackendName.AIDER_LOCAL
