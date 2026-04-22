"""Unit tests for lane routing policy models."""

from __future__ import annotations

import pytest

from switchboard.lane.policy import (
    BackendRule,
    DecisionThresholds,
    FallbackPolicy,
    LaneRule,
    LaneRoutingPolicy,
    _risk_at_or_below,
)


# ---------------------------------------------------------------------------
# _risk_at_or_below
# ---------------------------------------------------------------------------

class TestRiskOrdering:
    def test_low_at_or_below_low(self):
        assert _risk_at_or_below("low", "low") is True

    def test_low_at_or_below_medium(self):
        assert _risk_at_or_below("low", "medium") is True

    def test_low_at_or_below_high(self):
        assert _risk_at_or_below("low", "high") is True

    def test_medium_not_below_low(self):
        assert _risk_at_or_below("medium", "low") is False

    def test_high_not_below_medium(self):
        assert _risk_at_or_below("high", "medium") is False

    def test_high_at_or_below_high(self):
        assert _risk_at_or_below("high", "high") is True


# ---------------------------------------------------------------------------
# LaneRule.matches
# ---------------------------------------------------------------------------

class TestLaneRuleMatches:
    def _rule(self, when: dict) -> LaneRule:
        return LaneRule(name="r", select_lane="aider_local", select_backend="direct_local", when=when)

    def test_empty_when_always_matches(self):
        rule = self._rule(when={})
        assert rule.matches({"task_type": "lint_fix"}) is True

    def test_scalar_match(self):
        rule = self._rule(when={"task_type": "lint_fix"})
        assert rule.matches({"task_type": "lint_fix"}) is True

    def test_scalar_no_match(self):
        rule = self._rule(when={"task_type": "lint_fix"})
        assert rule.matches({"task_type": "bug_fix"}) is False

    def test_list_match(self):
        rule = self._rule(when={"task_type": ["lint_fix", "documentation"]})
        assert rule.matches({"task_type": "documentation"}) is True

    def test_list_no_match(self):
        rule = self._rule(when={"task_type": ["lint_fix", "documentation"]})
        assert rule.matches({"task_type": "feature"}) is False

    def test_max_risk_level_low_ceiling(self):
        rule = self._rule(when={"max_risk_level": "low"})
        assert rule.matches({"risk_level": "low"}) is True
        assert rule.matches({"risk_level": "medium"}) is False

    def test_max_risk_level_medium_ceiling(self):
        rule = self._rule(when={"max_risk_level": "medium"})
        assert rule.matches({"risk_level": "low"}) is True
        assert rule.matches({"risk_level": "medium"}) is True
        assert rule.matches({"risk_level": "high"}) is False

    def test_multiple_conditions_all_must_match(self):
        rule = self._rule(when={"task_type": "lint_fix", "max_risk_level": "low"})
        assert rule.matches({"task_type": "lint_fix", "risk_level": "low"}) is True
        assert rule.matches({"task_type": "lint_fix", "risk_level": "high"}) is False
        assert rule.matches({"task_type": "bug_fix", "risk_level": "low"}) is False

    def test_missing_key_treated_as_none(self):
        rule = self._rule(when={"task_type": "lint_fix"})
        assert rule.matches({}) is False


# ---------------------------------------------------------------------------
# BackendRule.matches
# ---------------------------------------------------------------------------

class TestBackendRuleMatches:
    def test_wrong_lane_does_not_match(self):
        rule = BackendRule(
            name="r",
            lane="codex_cli",
            select_backend="kodo",
            when={"risk_level": "low"},
        )
        assert rule.matches("claude_cli", {"risk_level": "low"}) is False

    def test_correct_lane_and_condition(self):
        rule = BackendRule(
            name="r",
            lane="codex_cli",
            select_backend="kodo",
            when={"risk_level": ["low", "medium"]},
        )
        assert rule.matches("codex_cli", {"risk_level": "medium"}) is True

    def test_correct_lane_wrong_condition(self):
        rule = BackendRule(
            name="r",
            lane="codex_cli",
            select_backend="kodo",
            when={"risk_level": "low"},
        )
        assert rule.matches("codex_cli", {"risk_level": "high"}) is False


# ---------------------------------------------------------------------------
# LaneRoutingPolicy
# ---------------------------------------------------------------------------

class TestLaneRoutingPolicy:
    def test_sorted_rules_by_priority(self):
        rules = [
            LaneRule(name="b", priority=50, select_lane="claude_cli", select_backend="kodo", when={}),
            LaneRule(name="a", priority=10, select_lane="aider_local", select_backend="direct_local", when={}),
        ]
        policy = LaneRoutingPolicy(rules=rules)
        sorted_r = policy.sorted_rules()
        assert sorted_r[0].name == "a"
        assert sorted_r[1].name == "b"

    def test_from_dict(self):
        data = {
            "version": "1",
            "rules": [
                {
                    "name": "local_lint",
                    "priority": 10,
                    "select_lane": "aider_local",
                    "select_backend": "direct_local",
                    "when": {"task_type": "lint_fix"},
                }
            ],
            "fallback": {"lane": "claude_cli", "backend": "kodo"},
        }
        policy = LaneRoutingPolicy.from_dict(data)
        assert len(policy.rules) == 1
        assert policy.rules[0].name == "local_lint"
        assert policy.fallback.lane == "claude_cli"

    def test_default_fallback(self):
        policy = LaneRoutingPolicy()
        assert policy.fallback.lane == "claude_cli"
        assert policy.fallback.backend == "kodo"
