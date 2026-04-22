"""
lane/fallback.py — FallbackPolicyEngine.

Evaluates which fallback routes are eligible for a given primary routing
choice. Fallbacks are lower-preference alternatives used when the primary
route is unavailable or fails at execution time.

SwitchBoard evaluates fallback eligibility here. Whether and when to
actually use a fallback is the execution layer's responsibility.
"""

from __future__ import annotations

from typing import Any

from .policy import AlternativeRoute, LaneRoutingPolicy
from .routing import (
    CostClass,
    CapabilityClass,
    EligibilityStatus,
    FallbackPlan,
    RouteCandidate,
    route_capability_class,
    route_cost_class,
)


class FallbackPolicyEngine:
    """Evaluates fallback route eligibility for a primary routing choice.

    Returns a FallbackPlan (eligible candidates) and a list of blocked
    RouteCandidate entries for transparency. Blocked entries are collected
    by the DecisionPlanner into RoutingPlan.blocked_candidates.

    Blocked-by-constraint is distinct from blocked-by-policy:
    - constraint: a proposal label explicitly prohibits this path (hard no)
    - policy: excluded_backends config excludes this backend
    """

    def evaluate(
        self,
        proposal_attrs: dict[str, Any],
        primary_lane: str,
        primary_backend: str,
        policy: LaneRoutingPolicy,
        labels: list[str] | None = None,
    ) -> tuple[FallbackPlan, list[RouteCandidate]]:
        """Evaluate fallback candidates.

        Returns:
            (FallbackPlan with eligible candidates, list of blocked RouteCandidate)
        """
        proposal_labels = list(labels or [])
        excluded = set(policy.excluded_backends)
        eligible: list[RouteCandidate] = []
        blocked: list[RouteCandidate] = []

        for alt in policy.fallback_alternatives():
            # Only consider alternatives relevant to the current primary route
            if not alt.is_relevant_for_primary(primary_lane, primary_backend):
                continue

            # Skip if same as primary (no point offering the same route)
            if alt.lane == primary_lane and alt.backend == primary_backend:
                continue

            cost = route_cost_class(alt.lane, alt.backend)
            capability = route_capability_class(alt.lane, alt.backend)

            # Hard block: explicit constraint label on the proposal
            if alt.is_blocked_by(proposal_labels):
                blocking_labels = [lb for lb in proposal_labels if lb in alt.blocked_by_labels]
                blocked.append(
                    RouteCandidate(
                        lane=alt.lane,
                        backend=alt.backend,
                        priority=alt.priority,
                        reason=(
                            f"Fallback route blocked by constraint label(s): "
                            f"{', '.join(blocking_labels)}"
                        ),
                        eligibility_status=EligibilityStatus.BLOCKED_BY_CONSTRAINT,
                        confidence=0.0,
                        estimated_cost_class=cost,
                        estimated_capability_class=capability,
                        notes=alt.notes or None,
                    )
                )
                continue

            # Policy block: backend is in the excluded list
            if alt.backend in excluded:
                blocked.append(
                    RouteCandidate(
                        lane=alt.lane,
                        backend=alt.backend,
                        priority=alt.priority,
                        reason=f"Fallback route blocked by policy: backend '{alt.backend}' is excluded",
                        eligibility_status=EligibilityStatus.BLOCKED_BY_POLICY,
                        confidence=0.0,
                        estimated_cost_class=cost,
                        estimated_capability_class=capability,
                        notes=alt.notes or None,
                    )
                )
                continue

            # Proposal attribute conditions: if they don't match, silently skip
            # (not blocked, just not applicable for this proposal shape)
            if not alt.matches_proposal_attrs(proposal_attrs):
                continue

            eligible.append(
                RouteCandidate(
                    lane=alt.lane,
                    backend=alt.backend,
                    priority=alt.priority,
                    reason=alt.reason or f"Fallback via policy rule '{alt.name}'",
                    eligibility_status=EligibilityStatus.ELIGIBLE,
                    confidence=alt.confidence,
                    estimated_cost_class=cost,
                    estimated_capability_class=capability,
                    notes=alt.notes or None,
                )
            )

        reasoning = _fallback_reasoning(eligible, blocked, primary_lane, primary_backend)
        return FallbackPlan(candidates=eligible, reasoning=reasoning), blocked


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _fallback_reasoning(
    eligible: list[RouteCandidate],
    blocked: list[RouteCandidate],
    primary_lane: str,
    primary_backend: str,
) -> str:
    if not eligible and not blocked:
        return (
            f"No fallback routes defined from {primary_lane}/{primary_backend}. "
            "Primary is the only available path."
        )
    if not eligible and blocked:
        n = len(blocked)
        return (
            f"All {n} fallback route(s) from {primary_lane}/{primary_backend} are blocked "
            "by explicit constraints or policy."
        )
    primary_str = f"{eligible[0].lane}/{eligible[0].backend}"
    extra = f" (+{len(eligible) - 1} more)" if len(eligible) > 1 else ""
    return (
        f"{len(eligible)} fallback route(s) available. "
        f"First: {primary_str}{extra}."
        + (f" {len(blocked)} blocked." if blocked else "")
    )
