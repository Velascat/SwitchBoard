"""Health-check endpoint.

GET /health

Returns:
    200 — both SwitchBoard and the downstream 9router are reachable.
    200 — but with degraded=true if 9router is unreachable (SwitchBoard itself is still up).
"""

from __future__ import annotations

import time

import httpx
from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class DownstreamStatus(BaseModel):
    reachable: bool
    latency_ms: float | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    status: str  # "ok" | "degraded"
    version: str
    uptime_s: float
    nine_router: DownstreamStatus


_start_time = time.monotonic()


@router.get("/health", response_model=HealthResponse, summary="Service health check")
async def health(request: Request) -> HealthResponse:
    """Check SwitchBoard health and probe the downstream 9router."""
    from switchboard import __version__

    settings = request.app.state.settings
    nine_router_url = settings.nine_router_url

    # Probe 9router /health (or just GET /)
    nine_router_status = await _probe_nine_router(nine_router_url)

    overall = "ok" if nine_router_status.reachable else "degraded"

    return HealthResponse(
        status=overall,
        version=__version__,
        uptime_s=round(time.monotonic() - _start_time, 2),
        nine_router=nine_router_status,
    )


async def _probe_nine_router(base_url: str) -> DownstreamStatus:
    """Attempt a lightweight GET against 9router and return status."""
    probe_url = base_url.rstrip("/") + "/health"
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(probe_url)
            latency_ms = (time.monotonic() - start) * 1000
            reachable = resp.status_code < 500
            return DownstreamStatus(reachable=reachable, latency_ms=round(latency_ms, 1))
    except Exception as exc:
        latency_ms = (time.monotonic() - start) * 1000
        return DownstreamStatus(
            reachable=False,
            latency_ms=round(latency_ms, 1),
            error=str(exc),
        )
