"""
lane/escalation.py — EscalationPolicyEngine.

Evaluates which escalation routes are warranted for a given primary routing
choice. Escalations are higher-capability alternatives used when the primary
route is likely insufficient for the task complexity, risk level, or
validation strictness required.

Escalation is policy-recommended, not automatic. SwitchBoard expresses the
intent; execution layers decide whether to act on it.

Key constraints:
- Escalation to archon_then_kodo requires explicit task shape justification
- Explicit constraints (local_only, no_remote) block all remote escalations
- Already-at-workflow primary has no further escalation path
"""

from __future__ import annotations

from typing import Any

from .policy import LaneRoutingPolicy
from .routing import (
    EligibilityStatus,
    EscalationPlan,
    RouteCandidate,
    route_capability_class,
    route_cost_class,
)


class EscalationPolicyEngine:
    """Evaluates escalation route eligibility for a primary routing choice.

    Returns an EscalationPlan (eligible candidates) and a list of blocked
    RouteCandidate entries. Blocked entries go into RoutingPlan.blocked_candidates.

    Escalation to archon_then_kodo or workflow backends is only offered when
    applies_when conditions specifically justify it — it is never offered
    merely because a higher tier exists.
    """

    def evaluate(
        self,
        proposal_attrs: dict[str, Any],
        primary_lane: str,
        primary_backend: str,
        policy: LaneRoutingPolicy,
        labels: list[str] | None = None,
    ) -> tuple[EscalationPlan, list[RouteCandidate]]:
        """Evaluate escalation candidates.

        Returns:
            (EscalationPlan with eligible candidates, list of blocked RouteCandidate)
        """
        proposal_labels = list(labels or [])
        excluded = set(policy.excluded_backends)
        eligible: list[RouteCandidate] = []
        blocked: list[RouteCandidate] = []

        for alt in policy.escalation_alternatives():
            # Only consider alternatives relevant to the current primary route
            if not alt.is_relevant_for_primary(primary_lane, primary_backend):
                continue

            # Skip if same as primary (escalation must be a genuinely higher path)
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
                            f"Escalation route blocked by constraint label(s): "
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

            # Policy block: backend is excluded
            if alt.backend in excluded:
                blocked.append(
                    RouteCandidate(
                        lane=alt.lane,
                        backend=alt.backend,
                        priority=alt.priority,
                        reason=f"Escalation route blocked by policy: backend '{alt.backend}' is excluded",
                        eligibility_status=EligibilityStatus.BLOCKED_BY_POLICY,
                        confidence=0.0,
                        estimated_cost_class=cost,
                        estimated_capability_class=capability,
                        notes=alt.notes or None,
                    )
                )
                continue

            # Applies-when conditions: escalation requires positive justification
            # If conditions don't match, the escalation is simply not warranted here
            if not alt.matches_proposal_attrs(proposal_attrs):
                continue

            eligible.append(
                RouteCandidate(
                    lane=alt.lane,
                    backend=alt.backend,
                    priority=alt.priority,
                    reason=alt.reason or f"Escalation via policy rule '{alt.name}'",
                    eligibility_status=EligibilityStatus.ELIGIBLE,
                    confidence=alt.confidence,
                    estimated_cost_class=cost,
                    estimated_capability_class=capability,
                    notes=alt.notes or None,
                )
            )

        reasoning = _escalation_reasoning(eligible, blocked, primary_lane, primary_backend)
        return EscalationPlan(candidates=eligible, reasoning=reasoning), blocked


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _escalation_reasoning(
    eligible: list[RouteCandidate],
    blocked: list[RouteCandidate],
    primary_lane: str,
    primary_backend: str,
) -> str:
    if not eligible and not blocked:
        return (
            f"No escalation warranted from {primary_lane}/{primary_backend} "
            "for this task type and risk level."
        )
    if not eligible and blocked:
        n = len(blocked)
        return (
            f"Escalation would be warranted but {n} route(s) are blocked "
            "by explicit constraints or policy."
        )
    primary_str = f"{eligible[0].lane}/{eligible[0].backend}"
    extra = f" (+{len(eligible) - 1} more)" if len(eligible) > 1 else ""
    return (
        f"{len(eligible)} escalation route(s) available. "
        f"First: {primary_str}{extra}."
        + (f" {len(blocked)} blocked." if blocked else "")
    )
