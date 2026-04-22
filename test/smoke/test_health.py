"""Smoke tests for selector-only health semantics."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from switchboard.app import create_app


@pytest.fixture()
async def live_client():
    app = create_app()
    app.state.policy_issues = []

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
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

    async def test_health_response_has_selector_fields(self, live_client: AsyncClient) -> None:
        resp = await live_client.get("/health")
        data = resp.json()
        assert data["selector_ready"] is True
        assert "nine_router" not in data

    async def test_health_no_longer_reports_proxy_dependency(self, live_client: AsyncClient) -> None:
        resp = await live_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "nine_router" not in data
