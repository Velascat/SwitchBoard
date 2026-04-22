"""Tests for lane/escalation.py — EscalationPolicyEngine."""

from __future__ import annotations

import pytest

from switchboard.lane.defaults import DEFAULT_POLICY
from switchboard.lane.escalation import EscalationPolicyEngine
from switchboard.lane.policy import AlternativeRoute, FallbackPolicy, LaneRoutingPolicy
from switchboard.lane.routing import CapabilityClass, EligibilityStatus


def _engine() -> EscalationPolicyEngine:
    return EscalationPolicyEngine()


def _policy_with_alts(*alts: AlternativeRoute) -> LaneRoutingPolicy:
    return LaneRoutingPolicy(
        alternative_routes=list(alts),
        fallback=FallbackPolicy(lane="claude_cli", backend="kodo"),
    )


def _escalation_alt(**kw) -> AlternativeRoute:
    defaults = dict(
        name="test_escalation",
        lane="claude_cli",
        backend="archon_then_kodo",
        role="escalation",
        cost_class="high",
        capability_class="workflow",
        reason="test escalation route",
        priority=10,
        confidence=0.88,
    )
    defaults.update(kw)
    return AlternativeRoute(**defaults)


# ---------------------------------------------------------------------------
# Basic eligibility
# ---------------------------------------------------------------------------


def test_eligible_escalation_returned():
    policy = _policy_with_alts(_escalation_alt())
    plan, blocked = _engine().evaluate(
        {}, "claude_cli", "kodo", policy
    )
    assert len(plan.candidates) == 1
    assert plan.candidates[0].eligibility_status == EligibilityStatus.ELIGIBLE


def test_eligible_escalation_has_correct_lane_backend():
    policy = _policy_with_alts(_escalation_alt(lane="claude_cli", backend="archon_then_kodo"))
    plan, _ = _engine().evaluate({}, "claude_cli", "kodo", policy)
    assert plan.candidates[0].lane == "claude_cli"
    assert plan.candidates[0].backend == "archon_then_kodo"


def test_escalation_capability_class_preserved():
    policy = _policy_with_alts(_escalation_alt(capability_class="workflow"))
    plan, _ = _engine().evaluate({}, "claude_cli", "kodo", policy)
    assert plan.candidates[0].estimated_capability_class == CapabilityClass.WORKFLOW


def test_empty_policy_gives_empty_plan():
    policy = _policy_with_alts()
    plan, blocked = _engine().evaluate({}, "claude_cli", "kodo", policy)
    assert plan.candidates == []
    assert blocked == []


# ---------------------------------------------------------------------------
# from_lanes / from_backends filtering
# ---------------------------------------------------------------------------


def test_from_lanes_filters_non_matching_primary():
    alt = _escalation_alt(from_lanes=["aider_local"])
    policy = _policy_with_alts(alt)
    # Primary is claude_cli, not aider_local
    plan, blocked = _engine().evaluate({}, "claude_cli", "kodo", policy)
    assert plan.candidates == []
    assert blocked == []


def test_from_lanes_matches_primary():
    alt = _escalation_alt(from_lanes=["aider_local"])
    policy = _policy_with_alts(alt)
    plan, _ = _engine().evaluate({}, "aider_local", "direct_local", policy)
    assert len(plan.candidates) == 1


def test_from_backends_filters_non_matching():
    alt = _escalation_alt(from_backends=["kodo"])
    policy = _policy_with_alts(alt)
    # Primary backend is archon_then_kodo, not kodo
    plan, _ = _engine().evaluate({}, "claude_cli", "archon_then_kodo", policy)
    assert plan.candidates == []


def test_from_backends_matches():
    alt = _escalation_alt(from_backends=["kodo"])
    policy = _policy_with_alts(alt)
    plan, _ = _engine().evaluate({}, "claude_cli", "kodo", policy)
    assert len(plan.candidates) == 1


# ---------------------------------------------------------------------------
# applies_when — escalation requires positive justification
# ---------------------------------------------------------------------------


def test_low_risk_does_not_trigger_escalation():
    alt = _escalation_alt(applies_when={"risk_level": ["medium", "high"]})
    policy = _policy_with_alts(alt)
    plan, blocked = _engine().evaluate({"risk_level": "low"}, "aider_local", "direct_local", policy)
    # Not blocked — just not warranted
    assert plan.candidates == []
    assert blocked == []


def test_medium_risk_triggers_escalation():
    alt = _escalation_alt(applies_when={"risk_level": ["medium", "high"]})
    policy = _policy_with_alts(alt)
    plan, _ = _engine().evaluate({"risk_level": "medium"}, "aider_local", "direct_local", policy)
    assert len(plan.candidates) == 1


def test_high_risk_triggers_escalation():
    alt = _escalation_alt(applies_when={"risk_level": "high"})
    policy = _policy_with_alts(alt)
    plan, _ = _engine().evaluate({"risk_level": "high"}, "claude_cli", "kodo", policy)
    assert len(plan.candidates) == 1


def test_simple_task_type_does_not_trigger_workflow_escalation():
    alt = _escalation_alt(applies_when={"task_type": ["refactor", "feature"]})
    policy = _policy_with_alts(alt)
    plan, blocked = _engine().evaluate({"task_type": "lint_fix"}, "claude_cli", "kodo", policy)
    assert plan.candidates == []
    assert blocked == []


def test_refactor_triggers_workflow_escalation():
    alt = _escalation_alt(applies_when={"task_type": ["refactor", "feature"]})
    policy = _policy_with_alts(alt)
    plan, _ = _engine().evaluate({"task_type": "refactor"}, "claude_cli", "kodo", policy)
    assert len(plan.candidates) == 1


def test_feature_triggers_workflow_escalation():
    alt = _escalation_alt(applies_when={"task_type": ["refactor", "feature"]})
    policy = _policy_with_alts(alt)
    plan, _ = _engine().evaluate({"task_type": "feature"}, "claude_cli", "kodo", policy)
    assert len(plan.candidates) == 1


# ---------------------------------------------------------------------------
# Constraint blocking
# ---------------------------------------------------------------------------


def test_local_only_blocks_escalation():
    alt = _escalation_alt(blocked_by_labels=["local_only", "no_remote"])
    policy = _policy_with_alts(alt)
    plan, blocked = _engine().evaluate(
        {"risk_level": "high"}, "aider_local", "direct_local", policy, labels=["local_only"]
    )
    assert plan.candidates == []
    assert len(blocked) == 1
    assert blocked[0].eligibility_status == EligibilityStatus.BLOCKED_BY_CONSTRAINT


def test_no_remote_blocks_escalation():
    alt = _escalation_alt(blocked_by_labels=["local_only", "no_remote"])
    policy = _policy_with_alts(alt)
    plan, blocked = _engine().evaluate(
        {"risk_level": "high"}, "aider_local", "direct_local", policy, labels=["no_remote"]
    )
    assert len(blocked) == 1
    assert blocked[0].eligibility_status == EligibilityStatus.BLOCKED_BY_CONSTRAINT


def test_constraint_block_distinct_from_not_warranted():
    alt = _escalation_alt(
        blocked_by_labels=["local_only"],
        applies_when={"risk_level": "high"},
    )
    policy = _policy_with_alts(alt)
    # local_only → blocked_by_constraint even when risk is high (warranted but blocked)
    plan, blocked = _engine().evaluate(
        {"risk_level": "high"}, "aider_local", "direct_local", policy, labels=["local_only"]
    )
    assert len(blocked) == 1
    assert blocked[0].eligibility_status == EligibilityStatus.BLOCKED_BY_CONSTRAINT


# ---------------------------------------------------------------------------
# Policy exclusion
# ---------------------------------------------------------------------------


def test_excluded_backend_blocks_escalation():
    alt = _escalation_alt(backend="archon_then_kodo")
    policy = LaneRoutingPolicy(
        alternative_routes=[alt],
        excluded_backends=["archon_then_kodo"],
    )
    plan, blocked = _engine().evaluate({}, "claude_cli", "kodo", policy)
    assert plan.candidates == []
    assert len(blocked) == 1
    assert blocked[0].eligibility_status == EligibilityStatus.BLOCKED_BY_POLICY


# ---------------------------------------------------------------------------
# Skip same-as-primary
# ---------------------------------------------------------------------------


def test_same_lane_backend_as_primary_skipped():
    alt = _escalation_alt(lane="claude_cli", backend="kodo")
    policy = _policy_with_alts(alt)
    plan, blocked = _engine().evaluate({}, "claude_cli", "kodo", policy)
    assert plan.candidates == []
    assert blocked == []


# ---------------------------------------------------------------------------
# Reasoning text
# ---------------------------------------------------------------------------


def test_reasoning_no_escalation_warranted():
    plan, _ = _engine().evaluate({}, "claude_cli", "kodo", _policy_with_alts())
    assert "No escalation" in plan.reasoning


def test_reasoning_blocked_by_constraint():
    alt = _escalation_alt(blocked_by_labels=["local_only"])
    policy = _policy_with_alts(alt)
    plan, blocked = _engine().evaluate(
        {}, "aider_local", "direct_local", policy, labels=["local_only"]
    )
    assert "blocked" in plan.reasoning.lower()


# ---------------------------------------------------------------------------
# Default policy integration
# ---------------------------------------------------------------------------


def test_default_policy_local_medium_risk_escalation():
    """Local task with medium risk → escalation to claude_cli/kodo."""
    plan, blocked = _engine().evaluate(
        {"risk_level": "medium", "task_type": "lint_fix"},
        "aider_local",
        "direct_local",
        DEFAULT_POLICY,
        labels=[],
    )
    assert any(c.lane == "claude_cli" for c in plan.candidates)


def test_default_policy_local_low_risk_no_escalation():
    """Local task with low risk → no escalation warranted."""
    plan, blocked = _engine().evaluate(
        {"risk_level": "low", "task_type": "lint_fix"},
        "aider_local",
        "direct_local",
        DEFAULT_POLICY,
        labels=[],
    )
    assert plan.candidates == []
    assert blocked == []


def test_default_policy_local_only_blocks_escalation():
    plan, blocked = _engine().evaluate(
        {"risk_level": "high"},
        "aider_local",
        "direct_local",
        DEFAULT_POLICY,
        labels=["local_only"],
    )
    assert not any(c.eligibility_status == EligibilityStatus.ELIGIBLE for c in plan.candidates)
    assert any(c.eligibility_status == EligibilityStatus.BLOCKED_BY_CONSTRAINT for c in blocked)


def test_default_policy_refactor_kodo_to_workflow():
    """Refactor task on kodo → workflow escalation available."""
    plan, _ = _engine().evaluate(
        {"task_type": "refactor", "risk_level": "medium"},
        "claude_cli",
        "kodo",
        DEFAULT_POLICY,
        labels=[],
    )
    assert any(c.backend == "archon_then_kodo" for c in plan.candidates)


def test_default_policy_feature_kodo_to_workflow():
    """Feature task on kodo → workflow escalation available."""
    plan, _ = _engine().evaluate(
        {"task_type": "feature", "risk_level": "medium"},
        "claude_cli",
        "kodo",
        DEFAULT_POLICY,
        labels=[],
    )
    assert any(c.backend == "archon_then_kodo" for c in plan.candidates)


def test_default_policy_lint_fix_no_workflow_escalation():
    """Lint fix task → no workflow escalation (not a complex task type)."""
    plan, _ = _engine().evaluate(
        {"task_type": "lint_fix", "risk_level": "low"},
        "claude_cli",
        "kodo",
        DEFAULT_POLICY,
        labels=[],
    )
    assert not any(c.backend == "archon_then_kodo" for c in plan.candidates)


def test_default_policy_high_risk_kodo_to_workflow():
    """High risk on kodo → workflow escalation available regardless of task type."""
    plan, _ = _engine().evaluate(
        {"task_type": "bug_fix", "risk_level": "high"},
        "claude_cli",
        "kodo",
        DEFAULT_POLICY,
        labels=[],
    )
    assert any(c.backend == "archon_then_kodo" for c in plan.candidates)
