# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Velascat
"""FastAPI application factory for selector-only SwitchBoard."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from switchboard.config import load_settings
from switchboard.lane.engine import LaneSelector
from switchboard.lane.planner import DecisionPlanner
from switchboard.lane.policy import LaneRoutingPolicy
from switchboard.observability.logging import configure_logging
from switchboard.services.adjustment_store import AdjustmentStore
from switchboard.services.decision_logger import DecisionLogger


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Load runtime configuration and attach selector services."""
    settings = load_settings()
    configure_logging(settings.log_level)
    policy = _load_policy(settings)

    decision_logger = DecisionLogger(
        settings.resolve_path("decision_log_path") if settings.decision_log_path else None
    )
    adjustment_store = AdjustmentStore()

    def _adjustment_query(lane: str) -> str | None:
        """Return the AdjustmentEngine action for ``lane``, or ``None``.

        Refreshes the store from recent decisions on demand (TTL-gated) so
        the next request sees up-to-date health signals without bookkeeping
        in the request path.
        """
        if not adjustment_store.enabled:
            return None
        adjustment_store.maybe_refresh(decision_logger.last_n(adjustment_store.window_size))
        adj = adjustment_store.get_adjustment(lane)
        return adj.action if adj is not None else None

    selector = LaneSelector(policy=policy, adjustment_query=_adjustment_query)
    planner = DecisionPlanner(policy=policy, adjustment_query=_adjustment_query)

    app.state.settings = settings
    app.state.selector = selector
    app.state.planner = planner
    app.state.policy_issues = selector.validate_policy()
    app.state.decision_log = decision_logger
    app.state.decision_logger = decision_logger
    app.state.adjustment_store = adjustment_store

    yield

    decision_logger.close()


def _load_policy(settings) -> LaneRoutingPolicy | None:
    policy_path = settings.resolve_path("policy_path")
    if not policy_path.exists():
        return None
    return LaneRoutingPolicy.from_yaml(policy_path)


def create_app() -> FastAPI:
    """Create and configure the SwitchBoard API application."""
    from switchboard.api.routes_admin import router as admin_router
    from switchboard.api.routes_health import router as health_router
    from switchboard.api.routes_routing import router as routing_router

    app = FastAPI(
        title="SwitchBoard",
        description="Policy-driven execution-lane selector for canonical task proposals.",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(routing_router)
    app.include_router(admin_router)

    return app


app = create_app()


def main() -> None:
    """Entry-point for the ``switchboard`` console script."""
    settings = load_settings()
    configure_logging(settings.log_level)
    uvicorn.run(
        "switchboard.app:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )
