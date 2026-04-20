"""DecisionRecord — persisted audit entry written to the decision log.

Section 8.3
"""

from __future__ import annotations

from pydantic import BaseModel


class DecisionRecord(BaseModel):
    """Audit record written to the decision log for every routed request.

    Attributes:
        timestamp:          ISO-8601 UTC timestamp of when the decision was made.
        client:             Identifier for the calling client or tenant.
        task_type:          High-level task category inferred from the request.
        selected_profile:   The profile selected by the policy engine.
        downstream_model:   The downstream model the request was forwarded to.
        rule_name:          The policy rule that triggered, or ``"fallback"``.
        reason:             Human-readable explanation of the routing decision.
    """

    timestamp: str
    client: str | None = None
    task_type: str | None = None
    selected_profile: str = ""
    downstream_model: str = ""
    rule_name: str = ""
    reason: str = ""

    # ---------------------------------------------------------------------------
    # Legacy fields — kept for backward-compat with existing decision_log +
    # admin route
    # ---------------------------------------------------------------------------
    request_id: str | None = None
    original_model_hint: str = ""
    profile_name: str = ""
    latency_ms: float | None = None
    tenant_id: str | None = None
    error: str | None = None
