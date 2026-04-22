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
from switchboard.observability.logging import configure_logging
from switchboard.services.decision_logger import DecisionLogger


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Load runtime configuration and attach selector services."""
    settings = load_settings()
    configure_logging(settings.log_level)

    selector = LaneSelector()
    planner = DecisionPlanner()
    decision_logger = DecisionLogger(
        settings.resolve_path("decision_log_path") if settings.decision_log_path else None
    )

    app.state.settings = settings
    app.state.selector = selector
    app.state.planner = planner
    app.state.policy_issues = selector.validate_policy()
    app.state.decision_log = decision_logger
    app.state.decision_logger = decision_logger

    yield

    decision_logger.close()


def create_app() -> FastAPI:
    """Create and configure the SwitchBoard API application."""
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
