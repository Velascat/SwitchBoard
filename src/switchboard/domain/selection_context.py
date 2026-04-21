"""SelectionContext — immutable snapshot of a request's classification.

Section 8.1
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SelectionContext(BaseModel):
    """Immutable snapshot of a request's classification used by the policy engine.

    Attributes:
        client:             Identifier for the calling client or tenant.
        task_type:          High-level task category (e.g. ``"chat"``, ``"code"``,
                            ``"summarisation"``).
        complexity:         Complexity signal: ``"low"``, ``"medium"``, or ``"high"``.
        cost_sensitivity:   How cost-sensitive this request is: ``"low"``, ``"medium"``,
                            ``"high"``.
        latency_sensitivity: How latency-sensitive this request is: ``"low"``,
                            ``"medium"``, ``"high"``.
        requires_tools:     True if the request body includes a ``tools`` array.
        requires_long_context: True if the estimated token count exceeds the threshold
                            for a long-context model.
    """

    client: str | None = None
    task_type: str | None = None
    complexity: str | None = None
    cost_sensitivity: str | None = None
    latency_sensitivity: str | None = None
    requires_tools: bool = False
    requires_long_context: bool = False
    # Phase 8 — structured output capability requirement
    requires_structured_output: bool = False

    # ---------------------------------------------------------------------------
    # Extended fields kept for backward-compat with classifier and policy engine
    # ---------------------------------------------------------------------------
    messages: list[dict[str, Any]] = Field(default_factory=list)
    model_hint: str = ""
    stream: bool = False
    max_tokens: int | None = None
    temperature: float | None = None
    tools_present: bool = False
    estimated_tokens: int = 0
    tenant_id: str | None = None
    priority: str | None = None
    force_profile: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)
