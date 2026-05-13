# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 ProtocolWarden
# ruff: noqa: S101
"""Unit tests for contracts/proposal.py."""
from __future__ import annotations

import pytest

from switchboard.contracts.common import TaskTarget
from switchboard.contracts.enums import ExecutionMode, Priority, RiskLevel, TaskType
from switchboard.contracts.proposal import TaskProposal


def _target() -> TaskTarget:
    return TaskTarget(
        repo_key="my-repo",
        clone_url="https://github.com/org/repo.git",
        base_branch="main",
    )


def _minimal(**kwargs) -> TaskProposal:
    defaults = dict(
        task_id="t-1",
        project_id="proj-1",
        task_type=TaskType.BUG_FIX,
        execution_mode=ExecutionMode.GOAL,
        goal_text="Fix the failing test.",
        target=_target(),
    )
    defaults.update(kwargs)
    return TaskProposal(**defaults)


def test_auto_id_and_timestamp() -> None:
    p = _minimal()
    assert p.proposal_id
    assert p.proposed_at is not None


def test_unique_ids() -> None:
    assert _minimal().proposal_id != _minimal().proposal_id


def test_defaults() -> None:
    p = _minimal()
    assert p.priority == Priority.NORMAL
    assert p.risk_level == RiskLevel.LOW
    assert p.labels == []
    assert p.proposer is None


def test_custom_priority_and_risk() -> None:
    p = _minimal(priority=Priority.CRITICAL, risk_level=RiskLevel.HIGH)
    assert p.priority == Priority.CRITICAL
    assert p.risk_level == RiskLevel.HIGH


def test_frozen() -> None:
    p = _minimal()
    with pytest.raises(Exception):
        p.goal_text = "changed"  # type: ignore[misc]


def test_goal_text_preserved_verbatim() -> None:
    goal = "Refactor the auth module."
    assert _minimal(goal_text=goal).goal_text == goal


def test_with_proposer_and_labels() -> None:
    p = _minimal(proposer="oc-agent", labels=["urgent"])
    assert p.proposer == "oc-agent"
    assert "urgent" in p.labels
