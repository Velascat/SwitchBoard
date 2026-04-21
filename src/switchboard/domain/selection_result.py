"""SelectionResult — outcome of running the Selector.

Section 8.2
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from switchboard.domain.selection_context import SelectionContext


class SelectionResult(BaseModel):
    """The outcome produced by the Selector after policy evaluation.

    Attributes:
        profile:            The chosen profile name (e.g. ``"fast"``, ``"capable"``).
        downstream_model:   The concrete model identifier resolved from the
                            capability registry (e.g. ``"gpt-4o-mini"``).
        rule_name:          The name of the policy rule that triggered the selection,
                            or ``"fallback"`` if no rule matched.
        reason:             Human-readable explanation of why this profile was chosen.
    """

    profile: str = ""
    downstream_model: str = ""
    rule_name: str = ""
    reason: str = ""

    # Phase 3 — rejection trace: profiles considered but ruled ineligible
    rejected_profiles: list[dict[str, Any]] = Field(default_factory=list)

    # Phase 7 — adaptive policy trace
    adjustment_applied: bool = False
    adjustment_reason: str | None = None

    # Phase 8 — advanced routing trace
    cost_estimate: float | None = None       # relative cost weight of selected profile
    ab_experiment: str | None = None         # experiment name if A/B routing applied
    ab_bucket: str | None = None             # "A" (control) or "B" (treatment)
    scored_profiles: list[dict] | None = None  # multi-factor scoring details

    # ---------------------------------------------------------------------------
    # Legacy field — kept for backward-compat with existing selector + tests
    # ---------------------------------------------------------------------------
    profile_name: str = ""
    context: SelectionContext | None = None
