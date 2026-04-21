"""FastAPI application factory and entry-point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from switchboard.adapters.file_policy_store import FilePolicyStore
from switchboard.adapters.file_profile_store import FileProfileStore
from switchboard.adapters.http_9router import HttpNineRouterGateway
from switchboard.adapters.retrying_gateway import RetryingGateway
from switchboard.config import load_settings
from switchboard.config.validator import ConfigValidationError, ConfigValidator
from switchboard.observability.logging import configure_logging, get_logger
from switchboard.services.adjustment_store import AdjustmentStore
from switchboard.services.capability_registry import CapabilityRegistry
from switchboard.services.classifier import RequestClassifier
from switchboard.services.decision_logger import DecisionLogger
from switchboard.services.experiment_router import ExperimentRouter
from switchboard.services.forwarder import Forwarder
from switchboard.services.policy_engine import PolicyEngine
from switchboard.services.profile_scorer import ProfileScorer
from switchboard.services.selector import Selector

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Application state — populated in lifespan, injected via request.app.state
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Load and validate all configuration, then wire up service dependencies."""
    settings = load_settings()
    configure_logging(settings.log_level)

    logger.info("SwitchBoard starting up", extra={"port": settings.port})

    # --- Stores / adapters ---------------------------------------------------
    policy_store = FilePolicyStore(settings.resolve_path("policy_path"))
    profile_store = FileProfileStore(settings.resolve_path("profiles_path"))
    capability_registry = CapabilityRegistry(settings.resolve_path("capabilities_path"))
    timeout = httpx.Timeout(
        connect=5.0,
        read=float(settings.nine_router_timeout_s),
        write=10.0,
        pool=5.0,
    )
    inner_gateway = HttpNineRouterGateway(settings.nine_router_url, timeout=timeout)
    gateway = RetryingGateway(inner_gateway)
    decision_logger = DecisionLogger(
        settings.resolve_path("decision_log_path") if settings.decision_log_path else None
    )

    # --- Configuration validation (fail fast on errors) ----------------------
    validator = ConfigValidator()
    try:
        validator.validate_all(settings, policy_store, profile_store, capability_registry)
    except ConfigValidationError as exc:
        logger.critical("Startup aborted due to configuration errors:\n%s", exc)
        raise

    # --- Domain services -----------------------------------------------------
    policy_engine = PolicyEngine(policy_store)
    classifier = RequestClassifier()
    adjustment_store = AdjustmentStore()
    policy_config = policy_store.get_policy()
    experiment_router = ExperimentRouter(policy_config.experiments)
    profile_scorer = ProfileScorer()
    selector = Selector(
        policy_engine,
        capability_registry,
        profile_store,
        adjustment_store,
        experiment_router,
        profile_scorer,
    )
    forwarder = Forwarder(gateway, decision_logger)

    # --- Attach to app state so routers can access them ----------------------
    app.state.settings = settings
    app.state.policy_engine = policy_engine
    app.state.capability_registry = capability_registry
    app.state.profile_store = profile_store
    app.state.classifier = classifier
    app.state.selector = selector
    app.state.adjustment_store = adjustment_store
    app.state.experiment_router = experiment_router
    app.state.profile_scorer = profile_scorer
    app.state.forwarder = forwarder
    # Expose under both names so existing routes using either name work.
    app.state.decision_log = decision_logger
    app.state.decision_logger = decision_logger
    app.state.gateway = gateway

    logger.info("SwitchBoard ready")
    yield

    # --- Shutdown ------------------------------------------------------------
    logger.info("SwitchBoard shutting down")
    await inner_gateway.close()
    decision_logger.close()


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

    # Global exception handler — catches anything that escapes route handlers
    @app.exception_handler(Exception)
    async def _global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "Unhandled exception on %s %s: %s",
            request.method,
            request.url.path,
            exc,
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "type": "internal_error",
                    "message": "An unexpected internal error occurred.",
                    "code": "internal_server_error",
                }
            },
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
