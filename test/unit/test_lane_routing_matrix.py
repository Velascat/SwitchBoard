"""Fixture-based routing matrix tests — proposal scenarios vs expected RoutingPlan."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from control_plane.contracts import TaskProposal
from control_plane.contracts.common import TaskTarget
from control_plane.contracts.enums import ExecutionMode, Priority, RiskLevel, TaskType

from switchboard.lane.planner import DecisionPlanner
from switchboard.lane.routing import EligibilityStatus

_FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "switchboard" / "routing_matrix.json"


def _load_matrix():
    with open(_FIXTURE_PATH) as f:
        return json.load(f)


def _make_proposal(spec: dict) -> TaskProposal:
    target = TaskTarget(
        repo_key="svc",
        clone_url="https://git.example.com/svc.git",
        base_branch="main",
    )
    return TaskProposal(
        task_id="TASK-matrix",
        project_id="proj-matrix",
        task_type=TaskType(spec["task_type"]),
        execution_mode=ExecutionMode.GOAL,
        goal_text="matrix test",
        target=target,
        risk_level=RiskLevel(spec.get("risk_level", "low")),
        priority=Priority.NORMAL,
        labels=spec.get("labels", []),
    )


@pytest.mark.parametrize("scenario", _load_matrix(), ids=[s["_description"] for s in _load_matrix()])
def test_routing_matrix(scenario):
    proposal = _make_proposal(scenario["proposal"])
    plan = DecisionPlanner().plan(proposal)
    expected = scenario.get("expected", {})

    if "primary_lane" in expected:
        assert plan.primary.lane == expected["primary_lane"], (
            f"Expected primary lane {expected['primary_lane']!r}, got {plan.primary.lane!r}"
        )

    if "primary_backend" in expected:
        assert plan.primary.backend == expected["primary_backend"], (
            f"Expected primary backend {expected['primary_backend']!r}, got {plan.primary.backend!r}"
        )

    if "has_fallbacks" in expected:
        has = len(plan.fallbacks.candidates) > 0
        assert has == expected["has_fallbacks"], (
            f"Expected has_fallbacks={expected['has_fallbacks']}, "
            f"got {len(plan.fallbacks.candidates)} fallback(s)"
        )

    if "has_escalations" in expected:
        has = len(plan.escalations.candidates) > 0
        assert has == expected["has_escalations"], (
            f"Expected has_escalations={expected['has_escalations']}, "
            f"got {len(plan.escalations.candidates)} escalation(s)"
        )

    if "has_blocked" in expected:
        has = len(plan.blocked_candidates) > 0
        assert has == expected["has_blocked"], (
            f"Expected has_blocked={expected['has_blocked']}, "
            f"got {len(plan.blocked_candidates)} blocked"
        )

    if expected.get("all_blocked_by_constraint"):
        assert all(
            c.eligibility_status == EligibilityStatus.BLOCKED_BY_CONSTRAINT
            for c in plan.blocked_candidates
        ), "Expected all blocked candidates to be BLOCKED_BY_CONSTRAINT"

    if "escalation_backend_available" in expected:
        backend = expected["escalation_backend_available"]
        found = any(c.backend == backend for c in plan.escalations.candidates)
        assert found, (
            f"Expected escalation to backend {backend!r}, "
            f"got escalations: {[c.backend for c in plan.escalations.candidates]}"
        )
