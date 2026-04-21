"""Smoke test: GET /health returns 200.

This test runs against a live (or test-client) SwitchBoard instance.
It uses the FastAPI ASGI test transport so it can run without a real server.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from switchboard.app import create_app


@pytest.fixture()
async def live_client():
    """Minimal test client with only the state needed for /health."""
    app = create_app()

    mock_settings = MagicMock()
    mock_settings.nine_router_url = "http://localhost:20128"
    mock_settings.port = 20401

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Inject minimal state
        app.state.settings = mock_settings
        yield client


class TestHealthSmoke:
    async def test_health_returns_200(self, live_client: AsyncClient) -> None:
        """GET /health must always return HTTP 200."""
        resp = await live_client.get("/health")
        assert resp.status_code == 200

    async def test_health_response_has_status_field(self, live_client: AsyncClient) -> None:
        resp = await live_client.get("/health")
        data = resp.json()
        assert "status" in data
        assert data["status"] in ("ok", "degraded")

    async def test_health_response_has_version(self, live_client: AsyncClient) -> None:
        resp = await live_client.get("/health")
        data = resp.json()
        assert "version" in data
        assert data["version"] == "0.1.0"

    async def test_health_response_has_nine_router_status(
        self, live_client: AsyncClient
    ) -> None:
        resp = await live_client.get("/health")
        data = resp.json()
        assert "nine_router" in data
        assert "reachable" in data["nine_router"]

    async def test_health_degraded_when_nine_router_unreachable(
        self, live_client: AsyncClient
    ) -> None:
        """When 9router is not running, status must be 'degraded' (not an error)."""
        resp = await live_client.get("/health")
        # The status code must still be 200 even when degraded
        assert resp.status_code == 200
        data = resp.json()
        # 9router is not running in test environment, so expect degraded
        if not data["nine_router"]["reachable"]:
            assert data["status"] == "degraded"
