"""
lane/policy.py — routing policy models for TaskProposal → LaneDecision.

These models describe the shape of the lane routing config. They are
populated by LaneRoutingPolicy.from_dict() (or from_yaml()) and
consumed by LaneSelector.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class LaneRule(BaseModel):
    """A single conditional routing rule for lane selection.

    Rules are evaluated in ascending priority order (lower = higher priority).
    The first rule whose conditions all match the proposal wins.

    Matching semantics for each condition key:
        - scalar value  → proposal attribute must equal the value
        - list value    → proposal attribute must be in the list (any-of)
        - special key "max_risk_level": matches if proposal.risk_level is at or
          below the named level (low < medium < high)
    """

    name: str
    priority: int = 100
    select_lane: str = Field(description="LaneName value to assign when this rule matches")
    select_backend: str = Field(description="BackendName value to assign when this rule matches")
    when: dict[str, Any] = Field(
        default_factory=dict,
        description="Conditions on TaskProposal fields that must all be true for the rule to fire.",
    )
    description: str = ""
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score attached to LaneDecision when this rule fires.",
    )

    def matches(self, proposal_attrs: dict[str, Any]) -> bool:
        """Return True if all ``when`` conditions match the given proposal attribute dict."""
        for key, expected in self.when.items():
            if key == "max_risk_level":
                actual = proposal_attrs.get("risk_level", "low")
                if not _risk_at_or_below(actual, str(expected)):
                    return False
                continue

            actual = proposal_attrs.get(key)
            if isinstance(expected, list):
                if actual not in expected:
                    return False
            else:
                if actual != expected:
                    return False
        return True


class BackendRule(BaseModel):
    """Override backend selection within a lane when conditions are met."""

    name: str
    lane: str = Field(description="Only applies when this lane is selected")
    select_backend: str
    when: dict[str, Any] = Field(default_factory=dict)
    description: str = ""

    def matches(self, lane: str, proposal_attrs: dict[str, Any]) -> bool:
        if lane != self.lane:
            return False
        for key, expected in self.when.items():
            actual = proposal_attrs.get(key)
            if isinstance(expected, list):
                if actual not in expected:
                    return False
            else:
                if actual != expected:
                    return False
        return True


class FallbackPolicy(BaseModel):
    """Fallback lane/backend when no rule matches."""

    lane: str = "claude_cli"
    backend: str = "kodo"
    rationale: str = "Default fallback: no policy rule matched"


class DecisionThresholds(BaseModel):
    """Thresholds that modify routing outcomes."""

    min_confidence_to_select: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Rules with confidence below this produce a fallback instead.",
    )
    local_lane_max_risk: str = Field(
        default="low",
        description="aider_local is only eligible when risk_level is at or below this.",
    )


class AlternativeRoute(BaseModel):
    """A potential fallback or escalation route defined in policy.

    AlternativeRoute describes a candidate path SwitchBoard knows about but
    did not select as primary. Fallback/escalation engines evaluate these
    against proposal attributes and constraint labels to determine eligibility.

    Fields:
        name           — unique identifier for this alternative (for logging)
        lane           — target LaneName value
        backend        — target BackendName or extended backend value
        role           — "fallback" or "escalation"
        cost_class     — CostClass string value (low/medium/high)
        capability_class — CapabilityClass string value (basic/enhanced/premium/workflow)
        from_lanes     — primary lanes for which this alternative is relevant;
                         empty = applicable from any primary lane
        from_backends  — primary backends for which this alternative is relevant;
                         empty = applicable from any primary backend
        applies_when   — proposal attribute conditions that must hold for this alternative
                         to be offered (same matching semantics as LaneRule.when)
        blocked_by_labels — proposal labels that hard-block this alternative
        priority       — preference ordering among alternatives of the same role
        confidence     — policy confidence in this alternative (0.0–1.0)
        reason         — human-readable explanation for offering this alternative
        notes          — optional additional context
    """

    name: str
    lane: str
    backend: str
    role: str = Field(description="'fallback' or 'escalation'")
    cost_class: str = Field(default="medium", description="CostClass value")
    capability_class: str = Field(default="enhanced", description="CapabilityClass value")
    from_lanes: list[str] = Field(
        default_factory=list,
        description="Relevant when primary lane is in this list. Empty = any primary lane.",
    )
    from_backends: list[str] = Field(
        default_factory=list,
        description="Relevant when primary backend is in this list. Empty = any primary backend.",
    )
    applies_when: dict[str, Any] = Field(
        default_factory=dict,
        description="Proposal attribute conditions (same semantics as LaneRule.when).",
    )
    blocked_by_labels: list[str] = Field(
        default_factory=list,
        description="Proposal labels that hard-block this alternative.",
    )
    priority: int = Field(default=100, ge=0)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    reason: str = ""
    notes: str = ""

    def is_relevant_for_primary(self, primary_lane: str, primary_backend: str) -> bool:
        """Return True if this alternative applies to the given primary route."""
        if self.from_lanes and primary_lane not in self.from_lanes:
            return False
        if self.from_backends and primary_backend not in self.from_backends:
            return False
        return True

    def is_blocked_by(self, labels: list[str]) -> bool:
        """Return True if any proposal label hard-blocks this alternative."""
        label_set = set(labels)
        return any(bl in label_set for bl in self.blocked_by_labels)

    def matches_proposal_attrs(self, attrs: dict[str, Any]) -> bool:
        """Return True if proposal attributes satisfy applies_when conditions."""
        for key, expected in self.applies_when.items():
            actual = attrs.get(key)
            if isinstance(expected, list):
                if actual not in expected:
                    return False
            else:
                if actual != expected:
                    return False
        return True


class LaneRoutingPolicy(BaseModel):
    """Top-level lane routing policy loaded from config."""

    version: str = "1"
    rules: list[LaneRule] = Field(default_factory=list)
    backend_rules: list[BackendRule] = Field(default_factory=list)
    fallback: FallbackPolicy = Field(default_factory=FallbackPolicy)
    thresholds: DecisionThresholds = Field(default_factory=DecisionThresholds)
    excluded_backends: list[str] = Field(
        default_factory=list,
        description="Backends never selected regardless of policy.",
    )
    alternative_routes: list[AlternativeRoute] = Field(
        default_factory=list,
        description="Fallback and escalation route candidates defined by policy.",
    )

    def sorted_rules(self) -> list[LaneRule]:
        return sorted(self.rules, key=lambda r: r.priority)

    def sorted_backend_rules(self) -> list[BackendRule]:
        return sorted(self.backend_rules, key=lambda r: r.name)

    def fallback_alternatives(self) -> list[AlternativeRoute]:
        return sorted(
            [r for r in self.alternative_routes if r.role == "fallback"],
            key=lambda r: r.priority,
        )

    def escalation_alternatives(self) -> list[AlternativeRoute]:
        return sorted(
            [r for r in self.alternative_routes if r.role == "escalation"],
            key=lambda r: r.priority,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LaneRoutingPolicy":
        return cls.model_validate(data)


# ---------------------------------------------------------------------------
# Risk level ordering
# ---------------------------------------------------------------------------

_RISK_ORDER = {"low": 0, "medium": 1, "high": 2}


def _risk_at_or_below(actual: str, ceiling: str) -> bool:
    return _RISK_ORDER.get(actual, 1) <= _RISK_ORDER.get(ceiling, 1)
