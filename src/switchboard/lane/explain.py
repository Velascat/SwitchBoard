"""
lane/explain.py — decision explanation models.

DecisionExplanation is attached to a LaneDecision to make routing
inspectable without embedding internal scoring details in the result.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class DecisionFactor(BaseModel):
    """A single input that influenced the routing decision."""

    name: str = Field(description="e.g. 'task_type', 'risk_level', 'local_only_constraint'")
    value: str = Field(description="The value observed on the proposal")
    influence: str = Field(
        description="One of: selected_lane, selected_backend, ruled_out_alternative, confirmed_choice"
    )
    note: Optional[str] = None

    model_config = {"frozen": True}


class DecisionExplanation(BaseModel):
    """Concise explanation of why a LaneDecision was made.

    This is supplemental metadata — the canonical routing output is
    LaneDecision. Explanation is for logging, debugging, and audit.
    """

    rule_matched: Optional[str] = Field(
        default=None,
        description="Policy rule name that fired, or None if fallback was used.",
    )
    factors: list[DecisionFactor] = Field(
        default_factory=list,
        description="Inputs that drove the decision.",
    )
    alternatives_ruled_out: list[str] = Field(
        default_factory=list,
        description="Lanes/backends that were considered but excluded.",
    )
    fallback_used: bool = Field(
        default=False,
        description="True when no policy rule matched and the default fallback was applied.",
    )
    fallback_recommendation: Optional[str] = Field(
        default=None,
        description="Suggested alternative if the selected lane becomes unavailable.",
    )
    summary: str = Field(
        default="",
        description="One-line human-readable summary of the decision.",
    )

    model_config = {"frozen": True}
