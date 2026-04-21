"""DecisionRecord — persisted audit entry written to the decision log.

Section 8.3
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


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

    # Phase 3 — context summary: key derived fields captured at decision time
    context_summary: dict[str, Any] | None = None
    # Phase 3 — profiles considered but rejected before final selection
    rejected_profiles: list[dict[str, Any]] = Field(default_factory=list)

    # Phase 4 — lifecycle / failure visibility
    status: str = "success"           # "success" | "error"
    error_category: str | None = None  # "upstream_error" | "upstream_timeout" | "selection_error" | "internal_error"

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
