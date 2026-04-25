"""
lane/planner.py — DecisionPlanner: full routing plan with alternatives.

DecisionPlanner ties together the primary route selection (LaneSelector),
fallback evaluation (FallbackPolicyEngine), and escalation evaluation
(EscalationPolicyEngine) into a single RoutingPlan.

This is the Phase 9 entry point for callers that need the full picture of
what routing alternatives exist, why some are blocked, and what the policy
recommends for primary, fallback, and escalation paths.

Callers that only need the primary route should continue using LaneSelector.select().
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from operations_center.contracts import TaskProposal
from operations_center.contracts.enums import BackendName, LaneName

from .defaults import DEFAULT_POLICY
from .engine import LaneSelector, _proposal_attrs
from .escalation import EscalationPolicyEngine
from .fallback import FallbackPolicyEngine
from .policy import LaneRoutingPolicy
from .routing import (
    CostClass,
    CapabilityClass,
    EligibilityStatus,
    RouteCandidate,
    RoutingPlan,
    route_capability_class,
    route_cost_class,
)

logger = logging.getLogger(__name__)


class DecisionPlanner:
    """Produces a RoutingPlan: primary route + fallbacks + escalations.

    Usage::

        planner = DecisionPlanner()                     # default policy
        planner = DecisionPlanner(policy=my_policy)     # custom policy

        plan = planner.plan(proposal)
        print(plan.primary.lane, plan.primary.backend)
        print(plan.fallbacks.candidates)
        print(plan.escalations.candidates)
        print(plan.blocked_candidates)

    The primary route is derived from the same LaneSelector logic that
    LaneSelector.select() uses. Fallbacks and escalations are evaluated
    by their respective engines using the policy's alternative_routes.
    """

    def __init__(self, policy: Optional[LaneRoutingPolicy] = None) -> None:
        self._policy = policy or DEFAULT_POLICY
        self._selector = LaneSelector(policy=self._policy)
        self._fallback_engine = FallbackPolicyEngine()
        self._escalation_engine = EscalationPolicyEngine()

    def plan(self, proposal: TaskProposal) -> RoutingPlan:
        """Produce a full RoutingPlan for the given TaskProposal."""
        attrs = _proposal_attrs(proposal)
        labels = list(proposal.labels)

        # Step 1: Determine the primary route via LaneSelector
        lane, backend, rule_name, confidence, _ = self._selector._evaluate_rules(attrs)

        primary = RouteCandidate(
            lane=lane,
            backend=backend,
            priority=0,
            reason=self._selector._build_rationale(lane, backend, rule_name, attrs),
            eligibility_status=EligibilityStatus.ELIGIBLE,
            confidence=confidence,
            estimated_cost_class=route_cost_class(lane, backend),
            estimated_capability_class=route_capability_class(lane, backend),
        )

        # Step 2: Evaluate fallback alternatives
        fallback_plan, fallback_blocked = self._fallback_engine.evaluate(
            attrs, lane, backend, self._policy, labels
        )

        # Step 3: Evaluate escalation alternatives
        escalation_plan, escalation_blocked = self._escalation_engine.evaluate(
            attrs, lane, backend, self._policy, labels
        )

        # Combine all blocked candidates
        all_blocked = fallback_blocked + escalation_blocked

        # Build the summary
        policy_summary = _build_policy_summary(primary, fallback_plan, escalation_plan, all_blocked)
        blocked_reasoning = _build_blocked_reasoning(all_blocked)

        logger.debug(
            "DecisionPlanner: proposal=%s → primary=%s/%s fallbacks=%d escalations=%d blocked=%d",
            proposal.proposal_id,
            lane,
            backend,
            len(fallback_plan.candidates),
            len(escalation_plan.candidates),
            len(all_blocked),
        )

        return RoutingPlan(
            primary=primary,
            fallbacks=fallback_plan,
            escalations=escalation_plan,
            blocked_candidates=all_blocked,
            policy_summary=policy_summary,
            primary_reason=primary.reason,
            fallback_reasoning=fallback_plan.reasoning,
            escalation_reasoning=escalation_plan.reasoning,
            blocked_reasoning=blocked_reasoning,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_policy_summary(
    primary: RouteCandidate,
    fallbacks: Any,
    escalations: Any,
    blocked: list[RouteCandidate],
) -> str:
    parts = [f"primary={primary.lane}/{primary.backend}"]
    if fallbacks.candidates:
        parts.append(f"fallbacks={len(fallbacks.candidates)}")
    if escalations.candidates:
        parts.append(f"escalations={len(escalations.candidates)}")
    if blocked:
        parts.append(f"blocked={len(blocked)}")
    return "; ".join(parts)


def _build_blocked_reasoning(blocked: list[RouteCandidate]) -> str:
    if not blocked:
        return ""
    constraint_blocked = [c for c in blocked if c.eligibility_status == EligibilityStatus.BLOCKED_BY_CONSTRAINT]
    policy_blocked = [c for c in blocked if c.eligibility_status == EligibilityStatus.BLOCKED_BY_POLICY]
    parts: list[str] = []
    if constraint_blocked:
        routes = ", ".join(f"{c.lane}/{c.backend}" for c in constraint_blocked)
        parts.append(f"Constraint-blocked: {routes}")
    if policy_blocked:
        routes = ", ".join(f"{c.lane}/{c.backend}" for c in policy_blocked)
        parts.append(f"Policy-blocked: {routes}")
    return ". ".join(parts) + "."
