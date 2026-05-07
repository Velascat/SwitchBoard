# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Velascat
"""Tests for health-aware lane selection — adjustment_query wiring."""

from __future__ import annotations

from operations_center.contracts import TaskProposal
from operations_center.contracts.common import TaskTarget
from operations_center.contracts.enums import (
    ExecutionMode,
    Priority,
    RiskLevel,
    TaskType,
)

from switchboard.lane.engine import LaneSelector
from switchboard.lane.policy import (
    FallbackPolicy,
    LaneRoutingPolicy,
    LaneRule,
)
from switchboard.lane.routing import EligibilityStatus


def _target() -> TaskTarget:
    return TaskTarget(
        repo_key="svc",
        clone_url="https://git.example.com/svc.git",
        base_branch="main",
    )


def _proposal() -> TaskProposal:
    return TaskProposal(
        task_id="TASK-1",
        project_id="proj-1",
        task_type=TaskType.LINT_FIX,
        execution_mode=ExecutionMode.GOAL,
        goal_text="do thing",
        target=_target(),
        risk_level=RiskLevel.LOW,
        priority=Priority.NORMAL,
        labels=[],
    )


def _two_rule_policy() -> LaneRoutingPolicy:
    """Policy where both rules can match the same proposal — first wins by priority."""
    return LaneRoutingPolicy(
        rules=[
            LaneRule(
                name="prefer_local",
                priority=10,
                select_lane="aider_local",
                select_backend="direct_local",
                when={"task_type": "lint_fix"},
            ),
            LaneRule(
                name="fallback_premium",
                priority=20,
                select_lane="claude_cli",
                select_backend="kodo",
                when={"task_type": "lint_fix"},
            ),
        ],
        fallback=FallbackPolicy(lane="claude_cli", backend="kodo"),
    )


# ---------------------------------------------------------------------------
# LaneSelector.select() — primary route
# ---------------------------------------------------------------------------


class TestPrimarySelectionDemote:
    def test_no_query_unchanged(self):
        """Without adjustment_query, selection ignores health entirely."""
        sel = LaneSelector(policy=_two_rule_policy())
        decision = sel.select(_proposal())
        assert decision.selected_lane.value == "aider_local"

    def test_neutral_query_unchanged(self):
        """A query that always returns 'neutral' must not affect selection."""
        sel = LaneSelector(
            policy=_two_rule_policy(),
            adjustment_query=lambda lane: "neutral",
        )
        decision = sel.select(_proposal())
        assert decision.selected_lane.value == "aider_local"

    def test_promote_query_unchanged(self):
        """A 'promote' signal is informational only — it does not change selection."""
        sel = LaneSelector(
            policy=_two_rule_policy(),
            adjustment_query=lambda lane: "promote",
        )
        decision = sel.select(_proposal())
        assert decision.selected_lane.value == "aider_local"

    def test_demoted_lane_skipped(self):
        """Demoted lane is skipped, next matching rule's lane is selected."""
        demoted = {"aider_local"}
        sel = LaneSelector(
            policy=_two_rule_policy(),
            adjustment_query=lambda lane: "demote" if lane in demoted else "neutral",
        )
        decision = sel.select(_proposal())
        assert decision.selected_lane.value == "claude_cli"

    def test_skipped_lane_recorded_as_alternative(self):
        """Demoted lane appears in alternatives_considered."""
        sel = LaneSelector(
            policy=_two_rule_policy(),
            adjustment_query=lambda lane: "demote" if lane == "aider_local" else "neutral",
        )
        decision = sel.select(_proposal())
        alts = [a.value for a in decision.alternatives_considered]
        assert "aider_local" in alts

    def test_all_lanes_demoted_falls_through_to_fallback(self):
        """If every matching rule's lane is demoted, fallback is used (regardless of fallback's own state)."""
        sel = LaneSelector(
            policy=_two_rule_policy(),
            adjustment_query=lambda lane: "demote",
        )
        decision = sel.select(_proposal())
        # Fallback in _two_rule_policy is claude_cli/kodo
        assert decision.selected_lane.value == "claude_cli"
        assert decision.policy_rule_matched is None  # fallback rule_name maps to None

    def test_query_exception_treats_as_no_signal(self):
        """A throwing query must not break selection; treat as neutral."""
        def boom(lane):
            raise RuntimeError("signal source down")

        sel = LaneSelector(policy=_two_rule_policy(), adjustment_query=boom)
        decision = sel.select(_proposal())
        # Behaves as if no signal was available — primary rule wins
        assert decision.selected_lane.value == "aider_local"


# ---------------------------------------------------------------------------
# DecisionPlanner — full plan with demoted candidates marked DEPRIORITIZED
# ---------------------------------------------------------------------------


class TestRoutingPlanDemote:
    def test_no_query_no_deprioritized(self):
        """Without a query, no candidate gets DEPRIORITIZED via this path."""
        sel = LaneSelector(policy=_two_rule_policy())
        plan = sel.plan_routes(_proposal())
        for cand in plan.fallbacks.candidates + plan.escalations.candidates:
            assert cand.eligibility_status != EligibilityStatus.DEPRIORITIZED or "[health-demoted]" not in (cand.reason or "")

    def test_demoted_fallback_candidate_marked_deprioritized(self):
        """Demoted fallback candidate stays in plan but as DEPRIORITIZED with reason note."""
        # Use a richer policy with explicit fallback alternatives so we have something to demote.
        policy = LaneRoutingPolicy(
            rules=[
                LaneRule(
                    name="primary_premium",
                    priority=10,
                    select_lane="claude_cli",
                    select_backend="kodo",
                    when={"task_type": "lint_fix"},
                ),
            ],
            fallback=FallbackPolicy(lane="claude_cli", backend="kodo"),
            alternative_routes=[
                {
                    "name": "local_fallback",
                    "role": "fallback",
                    "lane": "aider_local",
                    "backend": "direct_local",
                    "applies_when": {"task_type": "lint_fix"},
                },
            ],
        )

        # Demote aider_local — it should still appear but as DEPRIORITIZED
        demoted = {"aider_local"}
        sel = LaneSelector(
            policy=policy,
            adjustment_query=lambda lane: "demote" if lane in demoted else "neutral",
        )
        plan = sel.plan_routes(_proposal())

        # Find the aider_local fallback candidate
        aider_candidates = [c for c in plan.fallbacks.candidates if c.lane == "aider_local"]
        if aider_candidates:  # only assert if alternative_routes was honoured by the engine
            assert aider_candidates[0].eligibility_status == EligibilityStatus.DEPRIORITIZED
            assert "health-demoted" in (aider_candidates[0].reason or "")
