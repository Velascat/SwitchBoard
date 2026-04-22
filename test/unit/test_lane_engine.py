"""Unit tests for LaneSelector (lane/engine.py)."""

from __future__ import annotations

import pytest

from control_plane.contracts import LaneDecision, TaskProposal
from control_plane.contracts.common import (
    BranchPolicy,
    ExecutionConstraints,
    TaskTarget,
    ValidationProfile,
)
from control_plane.contracts.enums import (
    BackendName,
    ExecutionMode,
    LaneName,
    Priority,
    RiskLevel,
    TaskType,
)

from switchboard.lane.defaults import DEFAULT_POLICY
from switchboard.lane.engine import LaneSelector, _proposal_attrs
from switchboard.lane.policy import (
    BackendRule,
    FallbackPolicy,
    LaneRule,
    LaneRoutingPolicy,
)


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


def _minimal_policy(*rules: LaneRule, fallback_lane: str = "claude_cli") -> LaneRoutingPolicy:
    return LaneRoutingPolicy(
        rules=list(rules),
        fallback=FallbackPolicy(lane=fallback_lane, backend="kodo"),
    )


def _local_rule(name: str = "local", when: dict | None = None) -> LaneRule:
    return LaneRule(
        name=name,
        priority=10,
        select_lane="aider_local",
        select_backend="direct_local",
        when=when or {"task_type": "lint_fix"},
    )


def _premium_rule(name: str = "premium", when: dict | None = None) -> LaneRule:
    return LaneRule(
        name=name,
        priority=20,
        select_lane="claude_cli",
        select_backend="kodo",
        when=when or {"task_type": "feature"},
    )


# ---------------------------------------------------------------------------
# Basic routing
# ---------------------------------------------------------------------------

class TestBasicRouting:
    def test_returns_lane_decision(self):
        selector = LaneSelector(policy=_minimal_policy(_local_rule()))
        result = selector.select(_proposal(task_type=TaskType.LINT_FIX))
        assert isinstance(result, LaneDecision)

    def test_lint_fix_routes_to_local(self):
        selector = LaneSelector(policy=DEFAULT_POLICY)
        result = selector.select(_proposal(task_type=TaskType.LINT_FIX, risk_level=RiskLevel.LOW))
        assert result.selected_lane == LaneName.AIDER_LOCAL
        assert result.selected_backend == BackendName.DIRECT_LOCAL

    def test_feature_high_risk_routes_to_claude(self):
        selector = LaneSelector(policy=DEFAULT_POLICY)
        result = selector.select(_proposal(task_type=TaskType.FEATURE, risk_level=RiskLevel.HIGH))
        assert result.selected_lane == LaneName.CLAUDE_CLI

    def test_documentation_low_risk_routes_local(self):
        selector = LaneSelector(policy=DEFAULT_POLICY)
        result = selector.select(_proposal(task_type=TaskType.DOCUMENTATION, risk_level=RiskLevel.LOW))
        assert result.selected_lane == LaneName.AIDER_LOCAL

    def test_bug_fix_medium_risk_routes_claude(self):
        selector = LaneSelector(policy=DEFAULT_POLICY)
        result = selector.select(_proposal(task_type=TaskType.BUG_FIX, risk_level=RiskLevel.MEDIUM))
        assert result.selected_lane == LaneName.CLAUDE_CLI


# ---------------------------------------------------------------------------
# Proposal ID propagation
# ---------------------------------------------------------------------------

class TestProposalIdPropagation:
    def test_decision_carries_proposal_id(self):
        selector = LaneSelector()
        p = _proposal()
        result = selector.select(p)
        assert result.proposal_id == p.proposal_id

    def test_each_decision_has_unique_id(self):
        selector = LaneSelector()
        d1 = selector.select(_proposal())
        d2 = selector.select(_proposal())
        assert d1.decision_id != d2.decision_id


# ---------------------------------------------------------------------------
# Policy rule matching
# ---------------------------------------------------------------------------

class TestPolicyRuleMatching:
    def test_first_matching_rule_wins(self):
        rules = [
            LaneRule(name="first", priority=10, select_lane="aider_local", select_backend="direct_local", when={"task_type": "lint_fix"}),
            LaneRule(name="second", priority=20, select_lane="claude_cli", select_backend="kodo", when={"task_type": "lint_fix"}),
        ]
        selector = LaneSelector(policy=_minimal_policy(*rules))
        result = selector.select(_proposal(task_type=TaskType.LINT_FIX))
        assert result.selected_lane == LaneName.AIDER_LOCAL
        assert result.policy_rule_matched == "first"

    def test_no_matching_rule_uses_fallback(self):
        rules = [LaneRule(name="only", priority=10, select_lane="aider_local", select_backend="direct_local", when={"task_type": "feature"})]
        selector = LaneSelector(policy=_minimal_policy(*rules, fallback_lane="claude_cli"))
        result = selector.select(_proposal(task_type=TaskType.LINT_FIX))
        assert result.selected_lane == LaneName.CLAUDE_CLI
        assert result.policy_rule_matched is None

    def test_fallback_rule_name_is_none(self):
        selector = LaneSelector(policy=_minimal_policy())
        result = selector.select(_proposal())
        assert result.policy_rule_matched is None

    def test_confidence_from_rule_attached_to_decision(self):
        rule = LaneRule(name="r", priority=10, select_lane="aider_local", select_backend="direct_local", when={}, confidence=0.77)
        selector = LaneSelector(policy=_minimal_policy(rule))
        result = selector.select(_proposal())
        assert result.confidence == 0.77


# ---------------------------------------------------------------------------
# Local-only constraint
# ---------------------------------------------------------------------------

class TestLocalOnlyConstraint:
    def test_local_only_label_routes_to_aider_local(self):
        selector = LaneSelector(policy=DEFAULT_POLICY)
        p = _proposal(task_type=TaskType.FEATURE, risk_level=RiskLevel.HIGH, labels=["local_only"])
        result = selector.select(p)
        assert result.selected_lane == LaneName.AIDER_LOCAL


# ---------------------------------------------------------------------------
# Backend exclusion
# ---------------------------------------------------------------------------

class TestBackendExclusion:
    def test_excluded_backend_skips_to_next_rule(self):
        rules = [
            LaneRule(name="local", priority=10, select_lane="aider_local", select_backend="direct_local", when={"task_type": "lint_fix"}),
            LaneRule(name="premium", priority=20, select_lane="claude_cli", select_backend="kodo", when={"task_type": "lint_fix"}),
        ]
        policy = LaneRoutingPolicy(
            rules=rules,
            excluded_backends=["direct_local"],
            fallback=FallbackPolicy(lane="claude_cli", backend="kodo"),
        )
        selector = LaneSelector(policy=policy)
        result = selector.select(_proposal(task_type=TaskType.LINT_FIX))
        assert result.selected_lane == LaneName.CLAUDE_CLI

    def test_all_matching_backends_excluded_falls_back(self):
        rules = [
            LaneRule(name="local", priority=10, select_lane="aider_local", select_backend="direct_local", when={"task_type": "lint_fix"}),
        ]
        policy = LaneRoutingPolicy(
            rules=rules,
            excluded_backends=["direct_local"],
            fallback=FallbackPolicy(lane="claude_cli", backend="kodo"),
        )
        selector = LaneSelector(policy=policy)
        result = selector.select(_proposal(task_type=TaskType.LINT_FIX))
        assert result.selected_lane == LaneName.CLAUDE_CLI


# ---------------------------------------------------------------------------
# Backend override rules
# ---------------------------------------------------------------------------

class TestBackendOverrideRules:
    def test_backend_override_applied_for_matching_lane(self):
        rule = LaneRule(name="codex_r", priority=10, select_lane="codex_cli", select_backend="archon_then_kodo", when={})
        brule = BackendRule(name="codex_low", lane="codex_cli", select_backend="kodo", when={"risk_level": "low"})
        policy = LaneRoutingPolicy(rules=[rule], backend_rules=[brule], fallback=FallbackPolicy(lane="claude_cli", backend="kodo"))
        selector = LaneSelector(policy=policy)
        result = selector.select(_proposal(risk_level=RiskLevel.LOW))
        assert result.selected_lane == LaneName.CODEX_CLI
        # backend is "kodo" after override; maps to BackendName.KODO
        from control_plane.contracts.enums import BackendName
        assert result.selected_backend == BackendName.KODO

    def test_archon_then_kodo_is_preserved_without_coercion(self):
        rule = LaneRule(
            name="structured",
            priority=10,
            select_lane="codex_cli",
            select_backend="archon_then_kodo",
            when={},
        )
        selector = LaneSelector(policy=_minimal_policy(rule))
        result = selector.select(_proposal(task_type=TaskType.REFACTOR, risk_level=RiskLevel.HIGH))
        assert result.selected_backend == BackendName.ARCHON_THEN_KODO


# ---------------------------------------------------------------------------
# Explain
# ---------------------------------------------------------------------------

class TestExplain:
    def test_explain_returns_explanation(self):
        selector = LaneSelector(policy=DEFAULT_POLICY)
        exp = selector.explain(_proposal(task_type=TaskType.LINT_FIX, risk_level=RiskLevel.LOW))
        assert exp.summary != ""

    def test_fallback_used_flag(self):
        selector = LaneSelector(policy=_minimal_policy())
        exp = selector.explain(_proposal(task_type=TaskType.FEATURE))
        assert exp.fallback_used is True
        assert exp.rule_matched is None

    def test_rule_matched_when_rule_fires(self):
        selector = LaneSelector(policy=_minimal_policy(_local_rule("my_rule")))
        exp = selector.explain(_proposal(task_type=TaskType.LINT_FIX))
        assert exp.rule_matched == "my_rule"
        assert exp.fallback_used is False

    def test_factors_contain_task_type(self):
        selector = LaneSelector(policy=DEFAULT_POLICY)
        exp = selector.explain(_proposal(task_type=TaskType.LINT_FIX))
        factor_names = [f.name for f in exp.factors]
        assert "task_type" in factor_names

    def test_alternatives_ruled_out_populated(self):
        rules = [
            LaneRule(name="local", priority=10, select_lane="aider_local", select_backend="direct_local", when={"task_type": "lint_fix"}),
            LaneRule(name="premium", priority=20, select_lane="claude_cli", select_backend="kodo", when={"task_type": "feature"}),
        ]
        selector = LaneSelector(policy=_minimal_policy(*rules))
        exp = selector.explain(_proposal(task_type=TaskType.LINT_FIX))
        assert any("claude_cli" in a for a in exp.alternatives_ruled_out)


# ---------------------------------------------------------------------------
# validate_policy
# ---------------------------------------------------------------------------

class TestValidatePolicy:
    def test_default_policy_is_valid(self):
        selector = LaneSelector(policy=DEFAULT_POLICY)
        issues = selector.validate_policy()
        assert issues == []

    def test_unknown_lane_detected(self):
        rule = LaneRule(name="bad", priority=10, select_lane="invalid_lane", select_backend="kodo", when={})
        policy = _minimal_policy(rule)
        selector = LaneSelector(policy=policy)
        issues = selector.validate_policy()
        assert any("invalid_lane" in i for i in issues)

    def test_unknown_backend_detected(self):
        rule = LaneRule(name="bad", priority=10, select_lane="aider_local", select_backend="nonexistent", when={})
        policy = _minimal_policy(rule)
        selector = LaneSelector(policy=policy)
        issues = selector.validate_policy()
        assert any("nonexistent" in i for i in issues)

    def test_duplicate_rule_name_detected(self):
        rules = [
            LaneRule(name="dup", priority=10, select_lane="aider_local", select_backend="direct_local", when={}),
            LaneRule(name="dup", priority=20, select_lane="claude_cli", select_backend="kodo", when={}),
        ]
        selector = LaneSelector(policy=_minimal_policy(*rules))
        issues = selector.validate_policy()
        assert any("dup" in i for i in issues)

    def test_bad_fallback_lane_detected(self):
        policy = LaneRoutingPolicy(fallback=FallbackPolicy(lane="not_a_lane", backend="kodo"))
        selector = LaneSelector(policy=policy)
        issues = selector.validate_policy()
        assert any("not_a_lane" in i for i in issues)


# ---------------------------------------------------------------------------
# _proposal_attrs helper
# ---------------------------------------------------------------------------

class TestProposalAttrs:
    def test_flattens_basic_fields(self):
        p = _proposal(task_type=TaskType.BUG_FIX, risk_level=RiskLevel.MEDIUM)
        attrs = _proposal_attrs(p)
        assert attrs["task_type"] == "bug_fix"
        assert attrs["risk_level"] == "medium"

    def test_local_only_false_by_default(self):
        p = _proposal()
        attrs = _proposal_attrs(p)
        assert attrs["local_only"] is False

    def test_local_only_true_from_label(self):
        p = _proposal(labels=["local_only"])
        attrs = _proposal_attrs(p)
        assert attrs["local_only"] is True


# ---------------------------------------------------------------------------
# Decision/proposal wiring
# ---------------------------------------------------------------------------

class TestDecisionWiring:
    def test_decision_has_switchboard_version(self):
        selector = LaneSelector()
        result = selector.select(_proposal())
        assert result.switchboard_version is not None

    def test_alternatives_considered_are_lane_names(self):
        selector = LaneSelector(policy=DEFAULT_POLICY)
        result = selector.select(_proposal(task_type=TaskType.LINT_FIX, risk_level=RiskLevel.LOW))
        for alt in result.alternatives_considered:
            assert isinstance(alt, LaneName)

    def test_rationale_is_non_empty(self):
        selector = LaneSelector(policy=DEFAULT_POLICY)
        result = selector.select(_proposal(task_type=TaskType.LINT_FIX))
        assert result.rationale


# ---------------------------------------------------------------------------
# Fixture-driven routing table
# ---------------------------------------------------------------------------

class TestRoutingTable:
    """Verify expected routing for a representative set of proposal shapes."""

    _CASES = [
        # (description, task_type, risk_level, expected_lane)
        ("lint low risk → local", TaskType.LINT_FIX, RiskLevel.LOW, LaneName.AIDER_LOCAL),
        ("docs low risk → local", TaskType.DOCUMENTATION, RiskLevel.LOW, LaneName.AIDER_LOCAL),
        ("simple_edit low risk → local", TaskType.SIMPLE_EDIT, RiskLevel.LOW, LaneName.AIDER_LOCAL),
        ("bug fix medium → claude", TaskType.BUG_FIX, RiskLevel.MEDIUM, LaneName.CLAUDE_CLI),
        ("test write low → claude", TaskType.TEST_WRITE, RiskLevel.LOW, LaneName.CLAUDE_CLI),
        ("feature high → claude", TaskType.FEATURE, RiskLevel.HIGH, LaneName.CLAUDE_CLI),
        ("refactor high → claude", TaskType.REFACTOR, RiskLevel.HIGH, LaneName.CLAUDE_CLI),
    ]

    @pytest.mark.parametrize("desc,task_type,risk,expected_lane", _CASES)
    def test_routing(self, desc: str, task_type: TaskType, risk: RiskLevel, expected_lane: LaneName):
        selector = LaneSelector(policy=DEFAULT_POLICY)
        result = selector.select(_proposal(task_type=task_type, risk_level=risk))
        assert result.selected_lane == expected_lane, f"FAILED: {desc}"
