"""Core domain models for SwitchBoard.

Section 8.1 — SelectionContext
    Immutable snapshot of everything the policy engine may inspect.

Section 8.2 — SelectionResult
    The outcome of running the Selector: which profile and downstream model
    were chosen, and which rule triggered the decision.

Section 8.3 — DecisionRecord
    Persisted audit entry written to the decision log after every request.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 8.1  SelectionContext
# ---------------------------------------------------------------------------


class SelectionContext(BaseModel):
    """Immutable snapshot of a request's classification used by the policy engine.

    Attributes:
        messages:           The ``messages`` array from the chat completion body.
        model_hint:         The ``model`` field provided by the caller (may be empty).
        stream:             Whether the caller requested a streaming response.
        max_tokens:         Upper token bound from the request, if present.
        temperature:        Sampling temperature from the request, if present.
        tools_present:      True if the request body includes a ``tools`` array.
        estimated_tokens:   Rough token estimate derived from message content lengths.
        tenant_id:          Tenant identifier from ``X-SwitchBoard-Tenant-ID`` header.
        priority:           Priority tier from ``X-SwitchBoard-Priority`` header
                            (e.g. ``"high"``, ``"low"``).
        force_profile:      Profile name from ``X-SwitchBoard-Profile`` header that
                            bypasses policy evaluation when set.
        extra:              Any additional key/value pairs extracted by the classifier
                            for custom rule matching.
    """

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


# ---------------------------------------------------------------------------
# 8.2  SelectionResult
# ---------------------------------------------------------------------------


class SelectionResult(BaseModel):
    """The outcome produced by the Selector after policy evaluation.

    Attributes:
        profile_name:       The chosen profile name (e.g. ``"fast"``, ``"capable"``).
        downstream_model:   The concrete model identifier resolved from the
                            capability registry (e.g. ``"gpt-4o-mini"``).
        rule_name:          The name of the policy rule that triggered the selection,
                            or ``"fallback"`` if no rule matched.
        context:            The :class:`SelectionContext` that was evaluated.
    """

    profile_name: str
    downstream_model: str
    rule_name: str
    context: SelectionContext


# ---------------------------------------------------------------------------
# 8.3  DecisionRecord
# ---------------------------------------------------------------------------


class DecisionRecord(BaseModel):
    """Audit record written to the decision log for every routed request.

    Attributes:
        timestamp:          ISO-8601 UTC timestamp of when the decision was made.
        request_id:         Optional request identifier (from ``X-Request-ID`` header).
        original_model_hint:The ``model`` field as the caller specified it.
        profile_name:       The profile selected by the policy engine.
        downstream_model:   The downstream model the request was forwarded to.
        rule_name:          The policy rule that triggered, or ``"fallback"``.
        latency_ms:         Round-trip latency to 9router in milliseconds.
        tenant_id:          Tenant identifier if present in the request.
        error:              Non-null if the forwarding step produced an error.
    """

    timestamp: str
    request_id: str | None = None
    original_model_hint: str = ""
    profile_name: str = ""
    downstream_model: str = ""
    rule_name: str = ""
    latency_ms: float | None = None
    tenant_id: str | None = None
    error: str | None = None
