"""Selector health endpoint."""

from __future__ import annotations

import time

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(tags=["health"])

_start_time = time.monotonic()


class HealthResponse(BaseModel):
    status: str
    version: str
    uptime_s: float
    selector_ready: bool
    policy_valid: bool
    policy_issues: list[str] = []


@router.get("/health", response_model=HealthResponse, summary="Selector health check")
async def health(request: Request) -> HealthResponse:
    """Report local selector readiness only."""
    from switchboard import __version__

    issues = list(request.app.state.policy_issues)
    return HealthResponse(
        status="ok" if not issues else "degraded",
        version=__version__,
        uptime_s=round(time.monotonic() - _start_time, 2),
        selector_ready=True,
        policy_valid=not issues,
        policy_issues=issues,
    )
