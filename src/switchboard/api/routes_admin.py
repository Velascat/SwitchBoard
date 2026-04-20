"""Admin / observability endpoints.

GET /admin/decisions/recent?n=20
    Returns the last N decision records from the decision log.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from switchboard.domain.models import SelectionResult
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
    latency_ms: float | None = None


@router.get(
    "/decisions/recent",
    response_model=list[DecisionRecordResponse],
    summary="Return the last N routing decisions",
)
async def recent_decisions(
    request: Request,
    n: int = Query(default=20, ge=1, le=500, description="Number of recent decisions to return"),
) -> list[DecisionRecordResponse]:
    """Return the most recent routing decisions from the in-memory or on-disk decision log.

    Useful for debugging policy behaviour without grepping JSONL files.
    """
    decision_log = request.app.state.decision_log
    records = decision_log.last_n(n)

    return [
        DecisionRecordResponse(
            timestamp=r.timestamp,
            request_id=r.request_id,
            original_model_hint=r.original_model_hint,
            profile_name=r.profile_name,
            downstream_model=r.downstream_model,
            rule_name=r.rule_name,
            latency_ms=r.latency_ms,
        )
        for r in records
    ]
