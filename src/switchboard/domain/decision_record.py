"""DecisionRecord — persisted audit entry written to the decision log.

Section 8.3
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class DecisionRecord(BaseModel):
    """Audit record written to the decision log for every routed request.

    Attributes:
        timestamp:          ISO-8601 UTC timestamp of when the decision was made.
        client:             Identifier for the calling client or tenant.
        task_type:          High-level task category inferred from the request.
        selected_lane:      The lane selected by the router.
        selected_backend:   The backend selected within that lane.
        rule_name:          The policy rule that triggered, or ``"fallback"``.
        reason:             Human-readable explanation of the routing decision.
    """

    timestamp: str
    client: str | None = None
    task_type: str | None = None
    selected_lane: str = ""
    selected_backend: str = ""
    rule_name: str = ""
    reason: str = ""

    # Phase 3 — context summary: key derived fields captured at decision time
    context_summary: dict[str, Any] | None = None
    # Phase 3 — compatibility-only legacy selector trace
    rejected_profiles: list[dict[str, Any]] = Field(default_factory=list)

    # Phase 4 — lifecycle / failure visibility
    status: str = "success"           # "success" | "error"
    error_category: str | None = None  # "upstream_error" | "upstream_timeout" | "selection_error" | "internal_error"

    # Phase 7 — adaptive policy trace
    adjustment_applied: bool = False
    adjustment_reason: str | None = None

    # Phase 8 — advanced routing trace
    cost_estimate: float | None = None
    ab_experiment: str | None = None
    ab_bucket: str | None = None
    scored_profiles: list[dict] | None = None

    # ---------------------------------------------------------------------------
    # Legacy metadata fields kept only for compatibility with older logs.
    # ---------------------------------------------------------------------------
    request_id: str | None = None
    original_model_hint: str = ""
    latency_ms: float | None = None
    tenant_id: str | None = None
    error: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _lift_legacy_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        lifted = dict(data)
        if not lifted.get("selected_lane"):
            lifted["selected_lane"] = (
                lifted.get("selected_profile")
                or lifted.get("profile_name")
                or ""
            )
        if not lifted.get("selected_backend"):
            lifted["selected_backend"] = lifted.get("downstream_model") or ""
        return lifted

    @property
    def selected_profile(self) -> str:
        """Compatibility alias for legacy selector-oriented consumers."""
        return self.selected_lane

    @property
    def downstream_model(self) -> str:
        """Compatibility alias for legacy selector-oriented consumers."""
        return self.selected_backend

    @property
    def profile_name(self) -> str:
        """Compatibility alias for legacy selector-oriented consumers."""
        return self.selected_lane
