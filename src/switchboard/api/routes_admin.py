"""Admin / observability endpoints.

GET  /admin/decisions/recent?n=20        — last N decisions (enriched)
GET  /admin/decisions/{request_id}       — single decision lookup by correlation ID
GET  /admin/summary?n=100                — aggregated stats over last N decisions

GET  /admin/adaptive                     — adaptive policy state (Phase 7)
POST /admin/adaptive/enable              — enable adaptive adjustment
POST /admin/adaptive/disable             — disable adaptive adjustment
POST /admin/adaptive/reset               — clear all cached adjustments
POST /admin/adaptive/refresh             — recompute adjustments from decision log
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from switchboard.observability.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["admin"], prefix="/admin")


class AdjustmentResponse(BaseModel):
    profile: str
    action: str
    reason: str


class AdaptiveStateResponse(BaseModel):
    enabled: bool
    adjustment_count: int
    demoted_profiles: list[str]
    promoted_profiles: list[str]
    adjustments: list[AdjustmentResponse]
    last_refresh: str | None = None
    window_size: int


class DecisionRecordResponse(BaseModel):
    timestamp: str
    request_id: str | None
    original_model_hint: str
    selected_lane: str
    selected_backend: str
    rule_name: str
    reason: str
    task_type: str | None
    status: str
    error_category: str | None = None
    error: str | None = None
    latency_ms: float | None = None
    context_summary: dict[str, Any] | None = None
    rejected_profiles: list[dict[str, Any]] = []
    adjustment_applied: bool = False
    adjustment_reason: str | None = None
    cost_estimate: float | None = None
    ab_experiment: str | None = None
    ab_bucket: str | None = None
    scored_profiles: list[dict] | None = None


class SummaryResponse(BaseModel):
    window: int
    total: int
    success_count: int
    error_count: int
    lane_counts: dict[str, int]
    backend_counts: dict[str, int]
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
        selected_lane=r.selected_lane,
        selected_backend=r.selected_backend,
        rule_name=r.rule_name,
        reason=r.reason,
        task_type=r.task_type,
        status=r.status,
        error_category=r.error_category,
        error=r.error,
        latency_ms=r.latency_ms,
        context_summary=r.context_summary,
        rejected_profiles=r.rejected_profiles,
        adjustment_applied=getattr(r, "adjustment_applied", False),
        adjustment_reason=getattr(r, "adjustment_reason", None),
        cost_estimate=getattr(r, "cost_estimate", None),
        ab_experiment=getattr(r, "ab_experiment", None),
        ab_bucket=getattr(r, "ab_bucket", None),
        scored_profiles=getattr(r, "scored_profiles", None),
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
        lane_counts=stats.lane_counts,
        backend_counts=stats.backend_counts,
        rule_counts=stats.rule_counts,
        error_category_counts=stats.error_category_counts,
        latency_p50_ms=stats.latency_p50_ms,
        latency_p95_ms=stats.latency_p95_ms,
        latency_mean_ms=stats.latency_mean_ms,
    )


# ---------------------------------------------------------------------------
# Adaptive policy endpoints (Phase 7)
# ---------------------------------------------------------------------------


def _adaptive_state_response(store) -> AdaptiveStateResponse:
    state = store.get_state()
    adjustments = [
        AdjustmentResponse(profile=a.profile, action=a.action, reason=a.reason)
        for a in store.get_all_adjustments()
    ]
    return AdaptiveStateResponse(
        enabled=state.enabled,
        adjustment_count=state.adjustment_count,
        demoted_profiles=state.demoted_profiles,
        promoted_profiles=state.promoted_profiles,
        adjustments=adjustments,
        last_refresh=state.last_refresh,
        window_size=state.window_size,
    )


@router.get(
    "/adaptive",
    response_model=AdaptiveStateResponse,
    summary="Adaptive policy state and active adjustments",
)
async def get_adaptive_state(request: Request) -> AdaptiveStateResponse:
    """Return the current adaptive adjustment state: enabled flag, demoted/promoted profiles."""
    store = request.app.state.adjustment_store
    return _adaptive_state_response(store)


@router.post(
    "/adaptive/enable",
    response_model=AdaptiveStateResponse,
    summary="Enable adaptive policy adjustment",
)
async def adaptive_enable(request: Request) -> AdaptiveStateResponse:
    """Enable adaptive profile adjustment. Has no effect if already enabled."""
    store = request.app.state.adjustment_store
    store.enable()
    logger.info("Adaptive policy enabled by operator")
    return _adaptive_state_response(store)


@router.post(
    "/adaptive/disable",
    response_model=AdaptiveStateResponse,
    summary="Disable adaptive policy adjustment",
)
async def adaptive_disable(request: Request) -> AdaptiveStateResponse:
    """Disable adaptive profile adjustment without clearing cached data."""
    store = request.app.state.adjustment_store
    store.disable()
    logger.info("Adaptive policy disabled by operator")
    return _adaptive_state_response(store)


@router.post(
    "/adaptive/reset",
    response_model=AdaptiveStateResponse,
    summary="Clear all adaptive adjustments",
)
async def adaptive_reset(request: Request) -> AdaptiveStateResponse:
    """Clear all cached adjustments, returning all profiles to neutral."""
    store = request.app.state.adjustment_store
    store.reset()
    logger.info("Adaptive policy reset by operator")
    return _adaptive_state_response(store)


@router.post(
    "/adaptive/refresh",
    response_model=AdaptiveStateResponse,
    summary="Recompute adjustments from the decision log",
)
async def adaptive_refresh(
    request: Request,
    n: int = Query(default=200, ge=10, le=1000, description="Window size for signal aggregation"),
) -> AdaptiveStateResponse:
    """Force a refresh of adaptive adjustments from the last N decision records."""
    store = request.app.state.adjustment_store
    decision_log = request.app.state.decision_log
    records = decision_log.last_n(n)
    store.refresh(records)
    logger.info("Adaptive policy refreshed by operator (window=%d, records=%d)", n, len(records))
    return _adaptive_state_response(store)
