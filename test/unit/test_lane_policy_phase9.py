"""Tests for Phase 9 policy extensions — AlternativeRoute and LaneRoutingPolicy updates."""

from __future__ import annotations

import pytest

from switchboard.lane.defaults import DEFAULT_POLICY
from switchboard.lane.policy import AlternativeRoute, LaneRoutingPolicy


# ---------------------------------------------------------------------------
# AlternativeRoute construction
# ---------------------------------------------------------------------------


def test_alternative_route_requires_name():
    with pytest.raises(Exception):
        AlternativeRoute(lane="claude_cli", backend="kodo", role="fallback")


def test_alternative_route_defaults():
    alt = AlternativeRoute(
        name="test",
        lane="claude_cli",
        backend="kodo",
        role="fallback",
    )
    assert alt.from_lanes == []
    assert alt.from_backends == []
    assert alt.applies_when == {}
    assert alt.blocked_by_labels == []
    assert alt.priority == 100
    assert alt.confidence == 0.8
    assert alt.reason == ""
    assert alt.notes == ""


def test_alternative_route_role_fallback():
    alt = AlternativeRoute(name="t", lane="a", backend="b", role="fallback")
    assert alt.role == "fallback"


def test_alternative_route_role_escalation():
    alt = AlternativeRoute(name="t", lane="a", backend="b", role="escalation")
    assert alt.role == "escalation"


# ---------------------------------------------------------------------------
# AlternativeRoute.is_relevant_for_primary
# ---------------------------------------------------------------------------


def test_relevant_when_no_from_filters():
    alt = AlternativeRoute(name="t", lane="a", backend="b", role="fallback")
    assert alt.is_relevant_for_primary("any_lane", "any_backend") is True


def test_from_lanes_filters():
    alt = AlternativeRoute(
        name="t", lane="a", backend="b", role="fallback",
        from_lanes=["aider_local"],
    )
    assert alt.is_relevant_for_primary("aider_local", "direct_local") is True
    assert alt.is_relevant_for_primary("claude_cli", "kodo") is False


def test_from_backends_filters():
    alt = AlternativeRoute(
        name="t", lane="a", backend="b", role="fallback",
        from_backends=["archon_then_kodo"],
    )
    assert alt.is_relevant_for_primary("claude_cli", "archon_then_kodo") is True
    assert alt.is_relevant_for_primary("claude_cli", "kodo") is False


def test_both_from_filters_combined():
    alt = AlternativeRoute(
        name="t", lane="a", backend="b", role="fallback",
        from_lanes=["claude_cli"],
        from_backends=["kodo"],
    )
    assert alt.is_relevant_for_primary("claude_cli", "kodo") is True
    assert alt.is_relevant_for_primary("claude_cli", "archon_then_kodo") is False
    assert alt.is_relevant_for_primary("aider_local", "kodo") is False


# ---------------------------------------------------------------------------
# AlternativeRoute.is_blocked_by
# ---------------------------------------------------------------------------


def test_not_blocked_when_no_blocked_labels():
    alt = AlternativeRoute(name="t", lane="a", backend="b", role="fallback")
    assert alt.is_blocked_by(["local_only"]) is False


def test_blocked_when_matching_label():
    alt = AlternativeRoute(
        name="t", lane="a", backend="b", role="fallback",
        blocked_by_labels=["local_only"],
    )
    assert alt.is_blocked_by(["local_only"]) is True


def test_blocked_when_any_matching_label():
    alt = AlternativeRoute(
        name="t", lane="a", backend="b", role="fallback",
        blocked_by_labels=["local_only", "no_remote"],
    )
    assert alt.is_blocked_by(["no_remote"]) is True
    assert alt.is_blocked_by(["other_label"]) is False


def test_not_blocked_with_empty_proposal_labels():
    alt = AlternativeRoute(
        name="t", lane="a", backend="b", role="fallback",
        blocked_by_labels=["local_only"],
    )
    assert alt.is_blocked_by([]) is False


# ---------------------------------------------------------------------------
# AlternativeRoute.matches_proposal_attrs
# ---------------------------------------------------------------------------


def test_matches_with_no_conditions():
    alt = AlternativeRoute(name="t", lane="a", backend="b", role="fallback")
    assert alt.matches_proposal_attrs({"anything": "value"}) is True
    assert alt.matches_proposal_attrs({}) is True


def test_matches_scalar_condition():
    alt = AlternativeRoute(
        name="t", lane="a", backend="b", role="fallback",
        applies_when={"risk_level": "high"},
    )
    assert alt.matches_proposal_attrs({"risk_level": "high"}) is True
    assert alt.matches_proposal_attrs({"risk_level": "low"}) is False


def test_matches_list_condition():
    alt = AlternativeRoute(
        name="t", lane="a", backend="b", role="fallback",
        applies_when={"task_type": ["refactor", "feature"]},
    )
    assert alt.matches_proposal_attrs({"task_type": "refactor"}) is True
    assert alt.matches_proposal_attrs({"task_type": "feature"}) is True
    assert alt.matches_proposal_attrs({"task_type": "lint_fix"}) is False


def test_matches_multiple_conditions_all_required():
    alt = AlternativeRoute(
        name="t", lane="a", backend="b", role="fallback",
        applies_when={"risk_level": "high", "task_type": "refactor"},
    )
    assert alt.matches_proposal_attrs({"risk_level": "high", "task_type": "refactor"}) is True
    assert alt.matches_proposal_attrs({"risk_level": "high", "task_type": "lint_fix"}) is False
    assert alt.matches_proposal_attrs({"risk_level": "low", "task_type": "refactor"}) is False


# ---------------------------------------------------------------------------
# LaneRoutingPolicy.alternative_routes integration
# ---------------------------------------------------------------------------


def test_policy_alternative_routes_empty_by_default():
    policy = LaneRoutingPolicy()
    assert policy.alternative_routes == []


def test_policy_fallback_alternatives_filters_by_role():
    alts = [
        AlternativeRoute(name="f", lane="a", backend="b", role="fallback"),
        AlternativeRoute(name="e", lane="c", backend="d", role="escalation"),
    ]
    policy = LaneRoutingPolicy(alternative_routes=alts)
    assert len(policy.fallback_alternatives()) == 1
    assert policy.fallback_alternatives()[0].name == "f"


def test_policy_escalation_alternatives_filters_by_role():
    alts = [
        AlternativeRoute(name="f", lane="a", backend="b", role="fallback"),
        AlternativeRoute(name="e", lane="c", backend="d", role="escalation"),
    ]
    policy = LaneRoutingPolicy(alternative_routes=alts)
    assert len(policy.escalation_alternatives()) == 1
    assert policy.escalation_alternatives()[0].name == "e"


def test_policy_alternatives_sorted_by_priority():
    alts = [
        AlternativeRoute(name="b", lane="a", backend="b", role="fallback", priority=30),
        AlternativeRoute(name="a", lane="c", backend="d", role="fallback", priority=10),
        AlternativeRoute(name="c", lane="e", backend="f", role="fallback", priority=20),
    ]
    policy = LaneRoutingPolicy(alternative_routes=alts)
    names = [r.name for r in policy.fallback_alternatives()]
    assert names == ["a", "c", "b"]


# ---------------------------------------------------------------------------
# Default policy validates structure
# ---------------------------------------------------------------------------


def test_default_policy_has_alternative_routes():
    assert len(DEFAULT_POLICY.alternative_routes) > 0


def test_default_policy_has_fallback_alternatives():
    assert len(DEFAULT_POLICY.fallback_alternatives()) > 0


def test_default_policy_has_escalation_alternatives():
    assert len(DEFAULT_POLICY.escalation_alternatives()) > 0


def test_default_policy_all_alternatives_have_valid_roles():
    for alt in DEFAULT_POLICY.alternative_routes:
        assert alt.role in ("fallback", "escalation"), f"Invalid role: {alt.role!r}"


def test_default_policy_all_alternatives_have_names():
    names = [alt.name for alt in DEFAULT_POLICY.alternative_routes]
    assert len(names) == len(set(names)), "Duplicate alternative route names in DEFAULT_POLICY"


def test_default_policy_confidence_in_range():
    for alt in DEFAULT_POLICY.alternative_routes:
        assert 0.0 <= alt.confidence <= 1.0, f"Confidence out of range for {alt.name!r}"
