"""Tests for lane/fallback.py — FallbackPolicyEngine."""

from __future__ import annotations

import pytest

from switchboard.lane.defaults import DEFAULT_POLICY
from switchboard.lane.fallback import FallbackPolicyEngine
from switchboard.lane.policy import AlternativeRoute, FallbackPolicy, LaneRoutingPolicy
from switchboard.lane.routing import EligibilityStatus


def _engine() -> FallbackPolicyEngine:
    return FallbackPolicyEngine()


def _policy_with_alts(*alts: AlternativeRoute) -> LaneRoutingPolicy:
    return LaneRoutingPolicy(
        alternative_routes=list(alts),
        fallback=FallbackPolicy(lane="claude_cli", backend="kodo"),
    )


def _fallback_alt(**kw) -> AlternativeRoute:
    defaults = dict(
        name="test_fallback",
        lane="claude_cli",
        backend="kodo",
        role="fallback",
        cost_class="medium",
        capability_class="enhanced",
        reason="test fallback route",
        priority=10,
        confidence=0.85,
    )
    defaults.update(kw)
    return AlternativeRoute(**defaults)


# ---------------------------------------------------------------------------
# Basic eligibility
# ---------------------------------------------------------------------------


def test_eligible_fallback_returned():
    policy = _policy_with_alts(_fallback_alt())
    plan, blocked = _engine().evaluate(
        {"risk_level": "low"}, "aider_local", "direct_local", policy
    )
    assert len(plan.candidates) == 1
    assert plan.candidates[0].eligibility_status == EligibilityStatus.ELIGIBLE


def test_eligible_fallback_has_correct_lane_backend():
    policy = _policy_with_alts(_fallback_alt(lane="claude_cli", backend="kodo"))
    plan, _ = _engine().evaluate({}, "aider_local", "direct_local", policy)
    assert plan.candidates[0].lane == "claude_cli"
    assert plan.candidates[0].backend == "kodo"


def test_eligible_fallback_confidence_preserved():
    policy = _policy_with_alts(_fallback_alt(confidence=0.75))
    plan, _ = _engine().evaluate({}, "aider_local", "direct_local", policy)
    assert plan.candidates[0].confidence == 0.75


def test_fallback_reason_from_alt():
    policy = _policy_with_alts(_fallback_alt(reason="explicit reason"))
    plan, _ = _engine().evaluate({}, "aider_local", "direct_local", policy)
    assert "explicit reason" in plan.candidates[0].reason


def test_empty_policy_gives_empty_plan():
    policy = _policy_with_alts()
    plan, blocked = _engine().evaluate({}, "aider_local", "direct_local", policy)
    assert plan.candidates == []
    assert blocked == []


# ---------------------------------------------------------------------------
# from_lanes filtering
# ---------------------------------------------------------------------------


def test_from_lanes_filters_irrelevant_primary():
    alt = _fallback_alt(from_lanes=["aider_local"])
    policy = _policy_with_alts(alt)
    # When primary is claude_cli, this fallback is not relevant
    plan, blocked = _engine().evaluate({}, "claude_cli", "kodo", policy)
    assert plan.candidates == []
    assert blocked == []


def test_from_lanes_matches_primary():
    alt = _fallback_alt(from_lanes=["aider_local"])
    policy = _policy_with_alts(alt)
    plan, _ = _engine().evaluate({}, "aider_local", "direct_local", policy)
    assert len(plan.candidates) == 1


def test_from_backends_filters_irrelevant_primary():
    alt = _fallback_alt(from_backends=["archon_then_kodo"])
    policy = _policy_with_alts(alt)
    # When primary backend is kodo, not relevant
    plan, blocked = _engine().evaluate({}, "claude_cli", "kodo", policy)
    assert plan.candidates == []
    assert blocked == []


def test_from_backends_matches_primary():
    alt = _fallback_alt(from_backends=["archon_then_kodo"])
    policy = _policy_with_alts(alt)
    plan, _ = _engine().evaluate({}, "claude_cli", "archon_then_kodo", policy)
    assert len(plan.candidates) == 1


# ---------------------------------------------------------------------------
# Constraint blocking (blocked_by_labels)
# ---------------------------------------------------------------------------


def test_local_only_label_blocks_remote_fallback():
    alt = _fallback_alt(blocked_by_labels=["local_only", "no_remote"])
    policy = _policy_with_alts(alt)
    plan, blocked = _engine().evaluate(
        {}, "aider_local", "direct_local", policy, labels=["local_only"]
    )
    assert plan.candidates == []
    assert len(blocked) == 1
    assert blocked[0].eligibility_status == EligibilityStatus.BLOCKED_BY_CONSTRAINT


def test_no_remote_label_blocks_fallback():
    alt = _fallback_alt(blocked_by_labels=["local_only", "no_remote"])
    policy = _policy_with_alts(alt)
    plan, blocked = _engine().evaluate(
        {}, "aider_local", "direct_local", policy, labels=["no_remote"]
    )
    assert len(blocked) == 1
    assert blocked[0].eligibility_status == EligibilityStatus.BLOCKED_BY_CONSTRAINT


def test_unrelated_label_does_not_block():
    alt = _fallback_alt(blocked_by_labels=["local_only"])
    policy = _policy_with_alts(alt)
    plan, blocked = _engine().evaluate(
        {}, "aider_local", "direct_local", policy, labels=["priority:high"]
    )
    assert len(plan.candidates) == 1
    assert blocked == []


def test_blocked_candidate_reason_mentions_label():
    alt = _fallback_alt(blocked_by_labels=["local_only"])
    policy = _policy_with_alts(alt)
    _, blocked = _engine().evaluate(
        {}, "aider_local", "direct_local", policy, labels=["local_only"]
    )
    assert "local_only" in blocked[0].reason


def test_blocked_candidate_has_zero_confidence():
    alt = _fallback_alt(blocked_by_labels=["local_only"])
    policy = _policy_with_alts(alt)
    _, blocked = _engine().evaluate(
        {}, "aider_local", "direct_local", policy, labels=["local_only"]
    )
    assert blocked[0].confidence == 0.0


# ---------------------------------------------------------------------------
# Policy exclusion blocking (excluded_backends)
# ---------------------------------------------------------------------------


def test_excluded_backend_blocks_fallback():
    alt = _fallback_alt(backend="kodo")
    policy = LaneRoutingPolicy(
        alternative_routes=[alt],
        excluded_backends=["kodo"],
    )
    plan, blocked = _engine().evaluate({}, "aider_local", "direct_local", policy)
    assert plan.candidates == []
    assert len(blocked) == 1
    assert blocked[0].eligibility_status == EligibilityStatus.BLOCKED_BY_POLICY


# ---------------------------------------------------------------------------
# applies_when conditions
# ---------------------------------------------------------------------------


def test_applies_when_filters_non_matching():
    alt = _fallback_alt(applies_when={"risk_level": "high"})
    policy = _policy_with_alts(alt)
    plan, blocked = _engine().evaluate(
        {"risk_level": "low"}, "aider_local", "direct_local", policy
    )
    # Not blocked — just silently not applicable
    assert plan.candidates == []
    assert blocked == []


def test_applies_when_matches():
    alt = _fallback_alt(applies_when={"risk_level": "high"})
    policy = _policy_with_alts(alt)
    plan, _ = _engine().evaluate(
        {"risk_level": "high"}, "aider_local", "direct_local", policy
    )
    assert len(plan.candidates) == 1


# ---------------------------------------------------------------------------
# Skipping same-as-primary
# ---------------------------------------------------------------------------


def test_same_lane_backend_as_primary_skipped():
    alt = _fallback_alt(lane="aider_local", backend="direct_local")
    policy = _policy_with_alts(alt)
    plan, blocked = _engine().evaluate({}, "aider_local", "direct_local", policy)
    assert plan.candidates == []
    assert blocked == []


# ---------------------------------------------------------------------------
# Reasoning text
# ---------------------------------------------------------------------------


def test_reasoning_mentions_count():
    policy = _policy_with_alts(_fallback_alt())
    plan, _ = _engine().evaluate({}, "aider_local", "direct_local", policy)
    assert "1" in plan.reasoning


def test_reasoning_no_fallbacks():
    plan, _ = _engine().evaluate({}, "aider_local", "direct_local", _policy_with_alts())
    assert "No fallback" in plan.reasoning


# ---------------------------------------------------------------------------
# Default policy integration
# ---------------------------------------------------------------------------


def test_default_policy_has_local_to_remote_fallback():
    plan, blocked = _engine().evaluate(
        {}, "aider_local", "direct_local", DEFAULT_POLICY, labels=[]
    )
    assert any(c.lane == "claude_cli" and c.backend == "kodo" for c in plan.candidates)


def test_default_policy_local_to_remote_blocked_by_local_only():
    plan, blocked = _engine().evaluate(
        {}, "aider_local", "direct_local", DEFAULT_POLICY, labels=["local_only"]
    )
    assert not any(c.lane == "claude_cli" for c in plan.candidates)
    assert any(c.eligibility_status == EligibilityStatus.BLOCKED_BY_CONSTRAINT for c in blocked)


def test_default_policy_workflow_fallback_from_archon():
    plan, _ = _engine().evaluate(
        {}, "claude_cli", "archon_then_kodo", DEFAULT_POLICY, labels=[]
    )
    assert any(c.lane == "claude_cli" and c.backend == "kodo" for c in plan.candidates)
