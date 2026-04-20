"""SelectionResult — outcome of running the Selector.

Section 8.2
"""

from __future__ import annotations

from pydantic import BaseModel

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

    # ---------------------------------------------------------------------------
    # Legacy field — kept for backward-compat with existing selector + tests
    # ---------------------------------------------------------------------------
    profile_name: str = ""
    context: SelectionContext | None = None
