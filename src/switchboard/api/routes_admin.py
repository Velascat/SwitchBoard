"""Admin / observability endpoints.

GET /admin/decisions/recent?n=20        — last N decisions (enriched)
GET /admin/decisions/{request_id}       — single decision lookup by correlation ID
GET /admin/summary?n=100                — aggregated stats over last N decisions
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from switchboard.observability.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["admin"], prefix="/admin")


class DecisionRecordResponse(BaseModel):
    timestamp: str
    request_id: str | None
    original_model_hint: str
    profile_name: str
    downstream_model: str
    rule_name: str
    reason: str
    task_type: str | None
    status: str
    error_category: str | None = None
    error: str | None = None
    latency_ms: float | None = None
    context_summary: dict[str, Any] | None = None
    rejected_profiles: list[dict[str, Any]] = []


class SummaryResponse(BaseModel):
    window: int
    total: int
    success_count: int
    error_count: int
    profile_counts: dict[str, int]
    rule_counts: dict[str, int]
    error_category_counts: dict[str, int]
    latency_p50_ms: float | None = None
    latency_p95_ms: float | None = None
    latency_mean_ms: float | None = None


def _to_response(r) -> DecisionRecordResponse:
    return DecisionRecordResponse(
        timestamp=r.timestamp,
        request_id=r.request_id,
        original_model_hint=r.original_model_hint,
        profile_name=r.profile_name or r.selected_profile,
        downstream_model=r.downstream_model,
        rule_name=r.rule_name,
        reason=r.reason,
        task_type=r.task_type,
        status=r.status,
        error_category=r.error_category,
        error=r.error,
        latency_ms=r.latency_ms,
        context_summary=r.context_summary,
        rejected_profiles=r.rejected_profiles,
    )


@router.get(
    "/decisions/recent",
    response_model=list[DecisionRecordResponse],
    summary="Return the last N routing decisions",
)
async def recent_decisions(
    request: Request,
    n: int = Query(default=20, ge=1, le=500, description="Number of recent decisions to return"),
) -> list[DecisionRecordResponse]:
    """Return the most recent routing decisions from the in-memory decision log."""
    decision_log = request.app.state.decision_log
    records = decision_log.last_n(n)
    return [_to_response(r) for r in records]


@router.get(
    "/decisions/{request_id}",
    response_model=DecisionRecordResponse,
    summary="Look up a single decision by request correlation ID",
)
async def get_decision(
    request_id: str,
    request: Request,
) -> DecisionRecordResponse:
    """Return the decision record for the given ``X-Request-ID`` correlation ID."""
    decision_log = request.app.state.decision_log
    record = decision_log.find_by_request_id(request_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No decision found for request_id={request_id!r}")
    return _to_response(record)


@router.get(
    "/summary",
    response_model=SummaryResponse,
    summary="Aggregated routing statistics over the last N decisions",
)
async def summary(
    request: Request,
    n: int = Query(default=100, ge=1, le=1000, description="Window size for aggregation"),
) -> SummaryResponse:
    """Return aggregated profile distribution, rule counts, error rates, and latency stats."""
    decision_log = request.app.state.decision_log
    stats = decision_log.summarize(n)
    return SummaryResponse(
        window=n,
        total=stats.total,
        success_count=stats.success_count,
        error_count=stats.error_count,
        profile_counts=stats.profile_counts,
        rule_counts=stats.rule_counts,
        error_category_counts=stats.error_category_counts,
        latency_p50_ms=stats.latency_p50_ms,
        latency_p95_ms=stats.latency_p95_ms,
        latency_mean_ms=stats.latency_mean_ms,
    )
