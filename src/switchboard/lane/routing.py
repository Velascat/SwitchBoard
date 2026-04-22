"""
lane/routing.py — routing plan models for fallback and escalation policy.

These models represent the structured output of Phase 9 routing: not just the
primary route selected, but the full set of alternatives (fallbacks and
escalations), blocked candidates, and explanatory context.

RoutingPlan is the primary output of DecisionPlanner.plan(). LaneDecision
remains the canonical contract — RoutingPlan is the richer routing-side view
for callers that need alternative path awareness.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Classification enums
# ---------------------------------------------------------------------------


class CostClass(str, Enum):
    """Relative cost bucket for a route.

    Not an exact number — exists to make routing explanations legible and
    allow coarse policy reasoning without fake numeric precision.
    """
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CapabilityClass(str, Enum):
    """Relative capability bucket for a route.

    Encodes the kind of execution capability the lane/backend combination
    provides, not performance.
    """
    BASIC = "basic"          # lightweight local execution; fast, zero marginal cost
    ENHANCED = "enhanced"    # remote model execution; good reasoning, low overhead
    PREMIUM = "premium"      # highest-tier model; best reasoning quality
    WORKFLOW = "workflow"    # structured multi-step workflow orchestration


class EligibilityStatus(str, Enum):
    """Why a route candidate is or is not eligible.

    Later orchestration layers must distinguish:
    - BLOCKED_BY_CONSTRAINT: hard no — do not use regardless of circumstances
    - BLOCKED_BY_POLICY:     policy-excluded — do not use unless policy changes
    - UNSUPPORTED:           backend cannot handle this request type
    - DEPRIORITIZED:         valid but lower-preference; use if primary is unavailable
    - ELIGIBLE:              ready to use
    """
    ELIGIBLE = "eligible"
    BLOCKED_BY_CONSTRAINT = "blocked_by_constraint"
    BLOCKED_BY_POLICY = "blocked_by_policy"
    UNSUPPORTED = "unsupported"
    DEPRIORITIZED = "deprioritized"


# ---------------------------------------------------------------------------
# Route candidate
# ---------------------------------------------------------------------------


class RouteCandidate(BaseModel):
    """A single lane/backend pair with routing context.

    Used for primary routes, fallback candidates, escalation candidates,
    and blocked candidates — the eligibility_status distinguishes them.
    """

    lane: str = Field(description="LaneName value for this route")
    backend: str = Field(description="BackendName or extended backend for this route")
    priority: int = Field(
        default=100,
        description="Ordering preference among candidates of the same role (lower = preferred)",
    )
    reason: str = Field(description="Why this candidate exists or was blocked")
    eligibility_status: EligibilityStatus
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    estimated_cost_class: CostClass
    estimated_capability_class: CapabilityClass
    notes: Optional[str] = None

    model_config = {"frozen": True}


# ---------------------------------------------------------------------------
# Fallback and escalation plans
# ---------------------------------------------------------------------------


class FallbackPlan(BaseModel):
    """Eligible fallback routes for the primary routing choice.

    Fallbacks are lower-capability or lower-cost alternatives used when the
    primary route is unavailable or fails at execution time.
    Execution layers decide whether and when to act on these.
    """

    candidates: list[RouteCandidate] = Field(default_factory=list)
    reasoning: str = Field(default="", description="Why these fallbacks exist or why there are none")

    model_config = {"frozen": True}


class EscalationPlan(BaseModel):
    """Eligible escalation routes for the primary routing choice.

    Escalations are higher-capability alternatives used when the primary
    route is likely insufficient (e.g. task is too complex, risk too high).
    Escalation is recommended, not automatic.
    """

    candidates: list[RouteCandidate] = Field(default_factory=list)
    reasoning: str = Field(default="", description="Why these escalations exist or why there are none")

    model_config = {"frozen": True}


# ---------------------------------------------------------------------------
# Routing plan — full decision output
# ---------------------------------------------------------------------------


class RoutingPlan(BaseModel):
    """Full routing decision including primary route and alternatives.

    primary        — the recommended primary route
    fallbacks      — eligible alternatives to use if primary is unavailable
    escalations    — eligible alternatives if primary is insufficient
    blocked_candidates — routes that exist in policy but are blocked (with reasons)
    policy_summary — one-line summary of the overall routing decision
    primary_reason — why this primary was chosen
    fallback_reasoning — why fallbacks exist or don't
    escalation_reasoning — why escalations exist or don't
    blocked_reasoning — summary of constraint/policy blocks if any
    """

    primary: RouteCandidate
    fallbacks: FallbackPlan
    escalations: EscalationPlan
    blocked_candidates: list[RouteCandidate] = Field(default_factory=list)
    policy_summary: str
    primary_reason: str
    fallback_reasoning: str
    escalation_reasoning: str
    blocked_reasoning: str = ""

    model_config = {"frozen": True}


# ---------------------------------------------------------------------------
# Cost and capability tables
# ---------------------------------------------------------------------------

# Canonical cost/capability mapping for known lane+backend combinations.
# Used by engines when building RouteCandidate instances.
_ROUTE_COST: dict[tuple[str, str], CostClass] = {
    ("aider_local", "direct_local"): CostClass.LOW,
    ("aider_local", "kodo"): CostClass.MEDIUM,
    ("claude_cli", "kodo"): CostClass.MEDIUM,
    ("codex_cli", "kodo"): CostClass.MEDIUM,
    ("claude_cli", "archon_then_kodo"): CostClass.HIGH,
    ("codex_cli", "archon_then_kodo"): CostClass.HIGH,
    ("claude_cli", "archon"): CostClass.HIGH,
    ("claude_cli", "openclaw"): CostClass.HIGH,
}

_ROUTE_CAPABILITY: dict[tuple[str, str], CapabilityClass] = {
    ("aider_local", "direct_local"): CapabilityClass.BASIC,
    ("aider_local", "kodo"): CapabilityClass.ENHANCED,
    ("claude_cli", "kodo"): CapabilityClass.ENHANCED,
    ("codex_cli", "kodo"): CapabilityClass.ENHANCED,
    ("claude_cli", "archon_then_kodo"): CapabilityClass.WORKFLOW,
    ("codex_cli", "archon_then_kodo"): CapabilityClass.WORKFLOW,
    ("claude_cli", "archon"): CapabilityClass.WORKFLOW,
    ("claude_cli", "openclaw"): CapabilityClass.PREMIUM,
}


def route_cost_class(lane: str, backend: str) -> CostClass:
    """Return CostClass for a lane/backend pair, defaulting to MEDIUM."""
    return _ROUTE_COST.get((lane, backend), CostClass.MEDIUM)


def route_capability_class(lane: str, backend: str) -> CapabilityClass:
    """Return CapabilityClass for a lane/backend pair, defaulting to ENHANCED."""
    return _ROUTE_CAPABILITY.get((lane, backend), CapabilityClass.ENHANCED)
