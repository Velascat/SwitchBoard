"""Smoke test: GET /v1/models returns 200 with expected shape.

Uses the FastAPI ASGI test transport so it can run without a real server.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from switchboard.app import create_app


@pytest.fixture()
async def live_client():
    """Minimal test client with only the state needed for GET /v1/models."""
    app = create_app()

    mock_settings = MagicMock()
    mock_settings.nine_router_url = "http://localhost:20128"
    mock_settings.port = 20401

    mock_profile_store = MagicMock()
    mock_profile_store.get_profiles.return_value = {
        "fast": {"downstream_model": "gpt-4o-mini", "tags": ["chat"]},
        "capable": {"downstream_model": "gpt-4o", "tags": ["reasoning"]},
        "local": {"downstream_model": "llama3", "tags": ["private"]},
    }

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        app.state.settings = mock_settings
        app.state.profile_store = mock_profile_store
        yield client


class TestModelsSmoke:
    async def test_models_returns_200(self, live_client: AsyncClient) -> None:
        """GET /v1/models must return HTTP 200."""
        resp = await live_client.get("/v1/models")
        assert resp.status_code == 200

    async def test_models_response_has_object_list(self, live_client: AsyncClient) -> None:
        """Response must include ``"object": "list"``."""
        resp = await live_client.get("/v1/models")
        data = resp.json()
        assert data.get("object") == "list"

    async def test_models_response_has_data_array(self, live_client: AsyncClient) -> None:
        """Response must include a ``data`` array."""
        resp = await live_client.get("/v1/models")
        data = resp.json()
        assert "data" in data
        assert isinstance(data["data"], list)

    async def test_models_data_contains_expected_profiles(
        self, live_client: AsyncClient
    ) -> None:
        """Each profile should appear as a model object with the correct ``id``."""
        resp = await live_client.get("/v1/models")
        data = resp.json()
        ids = {item["id"] for item in data["data"]}
        assert "fast" in ids
        assert "capable" in ids
        assert "local" in ids

    async def test_models_data_items_have_required_fields(
        self, live_client: AsyncClient
    ) -> None:
        """Each model object must have ``id``, ``object``, ``created``, and ``owned_by``."""
        resp = await live_client.get("/v1/models")
        data = resp.json()
        for item in data["data"]:
            assert "id" in item
            assert item["object"] == "model"
            assert "created" in item
            assert item["owned_by"] == "switchboard"
