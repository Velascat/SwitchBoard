"""Tests for lane/planner.py — DecisionPlanner and RoutingPlan integration."""

from __future__ import annotations

import pytest

from control_plane.contracts import TaskProposal
from control_plane.contracts.common import BranchPolicy, ExecutionConstraints, TaskTarget, ValidationProfile
from control_plane.contracts.enums import ExecutionMode, LaneName, Priority, RiskLevel, TaskType

from switchboard.lane.defaults import DEFAULT_POLICY
from switchboard.lane.planner import DecisionPlanner
from switchboard.lane.policy import AlternativeRoute, FallbackPolicy, LaneRoutingPolicy
from switchboard.lane.routing import EligibilityStatus, RoutingPlan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
    execution_mode: ExecutionMode = ExecutionMode.GOAL,
    labels: list[str] | None = None,
) -> TaskProposal:
    return TaskProposal(
        task_id="TASK-1",
        project_id="proj-1",
        task_type=task_type,
        execution_mode=execution_mode,
        goal_text="do thing",
        target=_target(),
        risk_level=risk_level,
        priority=priority,
        labels=labels or [],
    )


def _planner(**kw) -> DecisionPlanner:
    return DecisionPlanner(**kw)


# ---------------------------------------------------------------------------
# RoutingPlan structure
# ---------------------------------------------------------------------------


def test_plan_returns_routing_plan():
    plan = _planner().plan(_proposal())
    assert isinstance(plan, RoutingPlan)


def test_plan_has_primary():
    plan = _planner().plan(_proposal())
    assert plan.primary is not None
    assert plan.primary.lane
    assert plan.primary.backend


def test_primary_is_eligible():
    plan = _planner().plan(_proposal())
    assert plan.primary.eligibility_status == EligibilityStatus.ELIGIBLE


def test_primary_confidence_positive():
    plan = _planner().plan(_proposal())
    assert plan.primary.confidence > 0.0


def test_plan_has_fallbacks_and_escalations():
    plan = _planner().plan(_proposal())
    assert plan.fallbacks is not None
    assert plan.escalations is not None


def test_policy_summary_populated():
    plan = _planner().plan(_proposal())
    assert plan.policy_summary
    assert "primary=" in plan.policy_summary


def test_primary_reason_populated():
    plan = _planner().plan(_proposal())
    assert plan.primary_reason


def test_fallback_reasoning_populated():
    plan = _planner().plan(_proposal())
    assert plan.fallback_reasoning


def test_escalation_reasoning_populated():
    plan = _planner().plan(_proposal())
    assert plan.escalation_reasoning


# ---------------------------------------------------------------------------
# Local-safe task routing
# ---------------------------------------------------------------------------


def test_local_low_risk_task_routes_to_local():
    plan = _planner().plan(
        _proposal(task_type=TaskType.LINT_FIX, risk_level=RiskLevel.LOW)
    )
    assert plan.primary.lane == "aider_local"
    assert plan.primary.backend == "direct_local"


def test_local_task_has_remote_fallback():
    """Low-risk local task without local_only → remote fallback is available."""
    plan = _planner().plan(
        _proposal(task_type=TaskType.LINT_FIX, risk_level=RiskLevel.LOW)
    )
    assert any(c.lane == "claude_cli" for c in plan.fallbacks.candidates)


def test_local_task_no_escalation_at_low_risk():
    plan = _planner().plan(
        _proposal(task_type=TaskType.LINT_FIX, risk_level=RiskLevel.LOW)
    )
    assert plan.escalations.candidates == []


# ---------------------------------------------------------------------------
# local_only constraint
# ---------------------------------------------------------------------------


def test_local_only_routes_to_local():
    plan = _planner().plan(_proposal(labels=["local_only"]))
    assert plan.primary.lane == "aider_local"


def test_local_only_blocks_remote_fallback():
    plan = _planner().plan(
        _proposal(task_type=TaskType.LINT_FIX, risk_level=RiskLevel.LOW, labels=["local_only"])
    )
    remote_fallbacks = [c for c in plan.fallbacks.candidates if c.lane != "aider_local"]
    assert remote_fallbacks == []


def test_local_only_escalation_blocked():
    plan = _planner().plan(
        _proposal(task_type=TaskType.REFACTOR, risk_level=RiskLevel.HIGH, labels=["local_only"])
    )
    remote_escalations = [c for c in plan.escalations.candidates if c.lane != "aider_local"]
    assert remote_escalations == []


def test_local_only_blocked_candidates_recorded():
    plan = _planner().plan(
        _proposal(task_type=TaskType.LINT_FIX, risk_level=RiskLevel.LOW, labels=["local_only"])
    )
    # Blocked fallback/escalation candidates should be visible
    assert any(
        c.eligibility_status == EligibilityStatus.BLOCKED_BY_CONSTRAINT
        for c in plan.blocked_candidates
    )


def test_local_only_blocked_reasoning_non_empty():
    plan = _planner().plan(
        _proposal(task_type=TaskType.LINT_FIX, risk_level=RiskLevel.LOW, labels=["local_only"])
    )
    assert plan.blocked_reasoning


# ---------------------------------------------------------------------------
# High-risk task escalation
# ---------------------------------------------------------------------------


def test_high_risk_routes_to_premium():
    plan = _planner().plan(
        _proposal(task_type=TaskType.BUG_FIX, risk_level=RiskLevel.HIGH)
    )
    assert plan.primary.lane == "claude_cli"


def test_high_risk_kodo_offers_workflow_escalation():
    """High-risk task on kodo primary → workflow escalation recommended."""
    plan = _planner().plan(
        _proposal(task_type=TaskType.BUG_FIX, risk_level=RiskLevel.HIGH)
    )
    assert any(c.backend == "archon_then_kodo" for c in plan.escalations.candidates)


def test_complex_refactor_routes_to_workflow_primary():
    """Refactor + medium risk already routes to archon_then_kodo as primary (premium_structured rule)."""
    plan = _planner().plan(
        _proposal(task_type=TaskType.REFACTOR, risk_level=RiskLevel.MEDIUM)
    )
    assert plan.primary.backend == "archon_then_kodo"


def test_feature_task_routes_to_workflow_primary():
    """Feature + medium risk already routes to archon_then_kodo as primary (premium_structured rule)."""
    plan = _planner().plan(
        _proposal(task_type=TaskType.FEATURE, risk_level=RiskLevel.MEDIUM)
    )
    assert plan.primary.backend == "archon_then_kodo"


# ---------------------------------------------------------------------------
# Blocked candidates are distinct from fallback/escalation candidates
# ---------------------------------------------------------------------------


def test_blocked_candidates_are_separate_from_fallbacks():
    plan = _planner().plan(
        _proposal(task_type=TaskType.LINT_FIX, risk_level=RiskLevel.LOW, labels=["local_only"])
    )
    # Blocked should appear in blocked_candidates, not in fallbacks.candidates
    blocked_routes = {(c.lane, c.backend) for c in plan.blocked_candidates}
    fallback_routes = {(c.lane, c.backend) for c in plan.fallbacks.candidates}
    assert not blocked_routes & fallback_routes


def test_blocked_candidates_have_ineligible_status():
    plan = _planner().plan(
        _proposal(task_type=TaskType.LINT_FIX, labels=["local_only"])
    )
    for c in plan.blocked_candidates:
        assert c.eligibility_status != EligibilityStatus.ELIGIBLE


# ---------------------------------------------------------------------------
# Policy summary fields
# ---------------------------------------------------------------------------


def test_policy_summary_mentions_fallbacks_when_present():
    plan = _planner().plan(_proposal(task_type=TaskType.LINT_FIX, risk_level=RiskLevel.LOW))
    if plan.fallbacks.candidates:
        assert "fallback" in plan.policy_summary.lower()


def test_policy_summary_mentions_blocked_when_present():
    plan = _planner().plan(
        _proposal(task_type=TaskType.LINT_FIX, labels=["local_only"])
    )
    if plan.blocked_candidates:
        assert "blocked" in plan.policy_summary.lower()


# ---------------------------------------------------------------------------
# LaneSelector.plan_routes() delegation
# ---------------------------------------------------------------------------


def test_lane_selector_plan_routes_returns_routing_plan():
    from switchboard.lane.engine import LaneSelector
    selector = LaneSelector()
    plan = selector.plan_routes(_proposal())
    assert isinstance(plan, RoutingPlan)


def test_lane_selector_plan_routes_primary_matches_select():
    from switchboard.lane.engine import LaneSelector
    from control_plane.contracts.enums import LaneName
    selector = LaneSelector()
    proposal = _proposal(task_type=TaskType.LINT_FIX, risk_level=RiskLevel.LOW)
    decision = selector.select(proposal)
    plan = selector.plan_routes(proposal)
    assert plan.primary.lane == decision.selected_lane.value


# ---------------------------------------------------------------------------
# Custom policy
# ---------------------------------------------------------------------------


def test_custom_policy_with_no_alternatives():
    policy = LaneRoutingPolicy(
        rules=[],
        fallback=FallbackPolicy(lane="claude_cli", backend="kodo"),
        alternative_routes=[],
    )
    planner = DecisionPlanner(policy=policy)
    plan = planner.plan(_proposal())
    assert plan.primary.lane == "claude_cli"
    assert plan.fallbacks.candidates == []
    assert plan.escalations.candidates == []
    assert plan.blocked_candidates == []


# ---------------------------------------------------------------------------
# Scenario: workflow-justified task
# ---------------------------------------------------------------------------


def test_workflow_shaped_task_routes_to_workflow_primary():
    """Refactor + high risk → already routes to archon_then_kodo as primary (premium_structured rule).
    No further escalation needed since the primary is already at workflow tier."""
    plan = _planner().plan(
        _proposal(task_type=TaskType.REFACTOR, risk_level=RiskLevel.HIGH)
    )
    assert plan.primary.backend == "archon_then_kodo"


def test_high_risk_non_structured_task_escalates_to_workflow():
    """bug_fix + high risk routes to kodo (high_risk_escalation rule), then escalation to workflow."""
    plan = _planner().plan(
        _proposal(task_type=TaskType.BUG_FIX, risk_level=RiskLevel.HIGH)
    )
    assert plan.primary.backend == "kodo"
    workflow_escalations = [
        c for c in plan.escalations.candidates
        if c.backend == "archon_then_kodo"
    ]
    assert len(workflow_escalations) >= 1


# ---------------------------------------------------------------------------
# Scenario: all remote alternatives blocked
# ---------------------------------------------------------------------------


def test_no_remote_blocks_all_alternatives():
    plan = _planner().plan(
        _proposal(
            task_type=TaskType.REFACTOR,
            risk_level=RiskLevel.HIGH,
            labels=["local_only"],
        )
    )
    eligible_remote = [
        c for c in plan.fallbacks.candidates + plan.escalations.candidates
        if c.lane != "aider_local"
    ]
    assert eligible_remote == []
