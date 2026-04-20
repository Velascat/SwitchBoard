"""FastAPI application factory and entry-point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from switchboard.config import load_settings
from switchboard.observability.logging import configure_logging, get_logger
from switchboard.services.capability_registry import CapabilityRegistry
from switchboard.services.decision_log import DecisionLog
from switchboard.services.policy_engine import PolicyEngine
from switchboard.adapters.file_policy_store import FilePolicyStore
from switchboard.adapters.file_profile_store import FileProfileStore
from switchboard.adapters.http_9router import HttpNineRouterGateway
from switchboard.services.classifier import RequestClassifier
from switchboard.services.selector import Selector
from switchboard.services.forwarder import Forwarder

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Application state — populated in lifespan, injected via request.app.state
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Load all configuration and wire up service dependencies on startup."""
    settings = load_settings()
    configure_logging(settings.log_level)

    logger.info("SwitchBoard starting up", extra={"port": settings.port})

    # --- Stores / adapters ---------------------------------------------------
    policy_store = FilePolicyStore(settings.resolve_path("policy_path"))
    profile_store = FileProfileStore(settings.resolve_path("profiles_path"))
    capability_registry = CapabilityRegistry(settings.resolve_path("capabilities_path"))
    gateway = HttpNineRouterGateway(settings.nine_router_url)
    decision_log = DecisionLog(
        settings.resolve_path("decision_log_path") if settings.decision_log_path else None
    )

    # --- Domain services -----------------------------------------------------
    policy_engine = PolicyEngine(policy_store)
    classifier = RequestClassifier()
    selector = Selector(policy_engine, capability_registry)
    forwarder = Forwarder(gateway, decision_log)

    # --- Attach to app state so routers can access them ----------------------
    app.state.settings = settings
    app.state.policy_engine = policy_engine
    app.state.capability_registry = capability_registry
    app.state.profile_store = profile_store
    app.state.classifier = classifier
    app.state.selector = selector
    app.state.forwarder = forwarder
    app.state.decision_log = decision_log
    app.state.gateway = gateway

    logger.info("SwitchBoard ready")
    yield

    # --- Shutdown ------------------------------------------------------------
    logger.info("SwitchBoard shutting down")
    await gateway.close()


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    from switchboard.api.routes_health import router as health_router
    from switchboard.api.routes_models import router as models_router
    from switchboard.api.routes_chat import router as chat_router
    from switchboard.api.routes_admin import router as admin_router

    app = FastAPI(
        title="SwitchBoard",
        description="Policy-driven model selection service: clients → SwitchBoard → 9router → providers.",
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
    app.include_router(models_router)
    app.include_router(chat_router)
    app.include_router(admin_router)

    return app


app = create_app()


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry-point for the ``switchboard`` console script."""
    settings = load_settings()
    configure_logging(settings.log_level)
    uvicorn.run(
        "switchboard.app:app",
        host="0.0.0.0",
        port=settings.port,
        log_level=settings.log_level,
        reload=False,
    )


if __name__ == "__main__":
    main()
