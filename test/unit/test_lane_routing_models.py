"""Tests for lane/routing.py — RoutingPlan models and cost/capability tables."""

from __future__ import annotations

import pytest

from switchboard.lane.routing import (
    CapabilityClass,
    CostClass,
    EligibilityStatus,
    EscalationPlan,
    FallbackPlan,
    RouteCandidate,
    RoutingPlan,
    route_capability_class,
    route_cost_class,
)


# ---------------------------------------------------------------------------
# Enum values
# ---------------------------------------------------------------------------


def test_cost_class_values():
    assert CostClass.LOW == "low"
    assert CostClass.MEDIUM == "medium"
    assert CostClass.HIGH == "high"


def test_capability_class_values():
    assert CapabilityClass.BASIC == "basic"
    assert CapabilityClass.ENHANCED == "enhanced"
    assert CapabilityClass.PREMIUM == "premium"
    assert CapabilityClass.WORKFLOW == "workflow"


def test_eligibility_status_values():
    assert EligibilityStatus.ELIGIBLE == "eligible"
    assert EligibilityStatus.BLOCKED_BY_CONSTRAINT == "blocked_by_constraint"
    assert EligibilityStatus.BLOCKED_BY_POLICY == "blocked_by_policy"
    assert EligibilityStatus.UNSUPPORTED == "unsupported"
    assert EligibilityStatus.DEPRIORITIZED == "deprioritized"


# ---------------------------------------------------------------------------
# RouteCandidate
# ---------------------------------------------------------------------------


def _candidate(**kw) -> RouteCandidate:
    defaults = dict(
        lane="claude_cli",
        backend="kodo",
        priority=10,
        reason="test reason",
        eligibility_status=EligibilityStatus.ELIGIBLE,
        confidence=0.9,
        estimated_cost_class=CostClass.MEDIUM,
        estimated_capability_class=CapabilityClass.ENHANCED,
    )
    defaults.update(kw)
    return RouteCandidate(**defaults)


def test_route_candidate_construction():
    c = _candidate()
    assert c.lane == "claude_cli"
    assert c.backend == "kodo"
    assert c.eligibility_status == EligibilityStatus.ELIGIBLE


def test_route_candidate_is_frozen():
    c = _candidate()
    with pytest.raises(Exception):
        c.lane = "aider_local"


def test_route_candidate_notes_optional():
    c = _candidate()
    assert c.notes is None
    c2 = _candidate(notes="something")
    assert c2.notes == "something"


def test_route_candidate_confidence_range():
    with pytest.raises(Exception):
        _candidate(confidence=1.5)
    with pytest.raises(Exception):
        _candidate(confidence=-0.1)


# ---------------------------------------------------------------------------
# FallbackPlan
# ---------------------------------------------------------------------------


def test_fallback_plan_empty():
    plan = FallbackPlan()
    assert plan.candidates == []
    assert plan.reasoning == ""


def test_fallback_plan_with_candidates():
    plan = FallbackPlan(candidates=[_candidate()], reasoning="one fallback available")
    assert len(plan.candidates) == 1
    assert "fallback" in plan.reasoning


def test_fallback_plan_is_frozen():
    plan = FallbackPlan()
    with pytest.raises(Exception):
        plan.reasoning = "changed"


# ---------------------------------------------------------------------------
# EscalationPlan
# ---------------------------------------------------------------------------


def test_escalation_plan_empty():
    plan = EscalationPlan()
    assert plan.candidates == []
    assert plan.reasoning == ""


def test_escalation_plan_with_candidates():
    c = _candidate(
        backend="archon_then_kodo",
        estimated_cost_class=CostClass.HIGH,
        estimated_capability_class=CapabilityClass.WORKFLOW,
    )
    plan = EscalationPlan(candidates=[c], reasoning="workflow escalation available")
    assert len(plan.candidates) == 1
    assert plan.candidates[0].estimated_capability_class == CapabilityClass.WORKFLOW


# ---------------------------------------------------------------------------
# RoutingPlan
# ---------------------------------------------------------------------------


def _routing_plan(**kw) -> RoutingPlan:
    defaults = dict(
        primary=_candidate(),
        fallbacks=FallbackPlan(),
        escalations=EscalationPlan(),
        policy_summary="primary=claude_cli/kodo",
        primary_reason="matched rule medium_implementation",
        fallback_reasoning="no fallbacks defined",
        escalation_reasoning="no escalation warranted",
    )
    defaults.update(kw)
    return RoutingPlan(**defaults)


def test_routing_plan_construction():
    plan = _routing_plan()
    assert plan.primary.lane == "claude_cli"
    assert plan.fallbacks.candidates == []
    assert plan.escalations.candidates == []
    assert plan.blocked_candidates == []


def test_routing_plan_is_frozen():
    plan = _routing_plan()
    with pytest.raises(Exception):
        plan.policy_summary = "changed"


def test_routing_plan_blocked_candidates():
    blocked = _candidate(
        eligibility_status=EligibilityStatus.BLOCKED_BY_CONSTRAINT,
        reason="blocked by local_only",
        confidence=0.0,
    )
    plan = _routing_plan(blocked_candidates=[blocked])
    assert len(plan.blocked_candidates) == 1
    assert plan.blocked_candidates[0].eligibility_status == EligibilityStatus.BLOCKED_BY_CONSTRAINT


def test_routing_plan_blocked_reasoning_optional():
    plan = _routing_plan()
    assert plan.blocked_reasoning == ""


# ---------------------------------------------------------------------------
# Cost/capability table helpers
# ---------------------------------------------------------------------------


def test_local_route_cost_is_low():
    assert route_cost_class("aider_local", "direct_local") == CostClass.LOW


def test_kodo_route_cost_is_medium():
    assert route_cost_class("claude_cli", "kodo") == CostClass.MEDIUM


def test_archon_route_cost_is_high():
    assert route_cost_class("claude_cli", "archon_then_kodo") == CostClass.HIGH


def test_local_route_capability_is_basic():
    assert route_capability_class("aider_local", "direct_local") == CapabilityClass.BASIC


def test_kodo_route_capability_is_enhanced():
    assert route_capability_class("claude_cli", "kodo") == CapabilityClass.ENHANCED


def test_archon_route_capability_is_workflow():
    assert route_capability_class("claude_cli", "archon_then_kodo") == CapabilityClass.WORKFLOW


def test_unknown_route_defaults_to_medium_enhanced():
    assert route_cost_class("unknown_lane", "unknown_backend") == CostClass.MEDIUM
    assert route_capability_class("unknown_lane", "unknown_backend") == CapabilityClass.ENHANCED
