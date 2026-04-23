"""DecisionRecord — persisted audit entry written to the decision log.

Section 8.3
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


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

    context_summary: dict[str, Any] | None = None

    status: str = "success"
    error_category: str | None = None

    request_id: str | None = None
    latency_ms: float | None = None
    error: str | None = None
