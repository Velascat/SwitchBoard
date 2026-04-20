"""Integration tests for POST /v1/chat/completions.

Uses pytest-asyncio and httpx's AsyncClient with a live FastAPI TestClient
(ASGI transport) to test the full request pipeline with a mocked 9router
gateway.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from switchboard.app import create_app
from switchboard.domain.models import SelectionContext, SelectionResult


# ---------------------------------------------------------------------------
# Helpers and fixtures
# ---------------------------------------------------------------------------

_SAMPLE_OPENAI_RESPONSE: dict[str, Any] = {
    "id": "chatcmpl-integration",
    "object": "chat.completion",
    "created": 1714000000,
    "model": "gpt-4o-mini",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "Hello!"},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13},
}


def _make_selection_result(
    profile: str = "fast",
    model: str = "gpt-4o-mini",
    rule: str = "default_short_request",
) -> SelectionResult:
    ctx = SelectionContext(
        messages=[{"role": "user", "content": "hi"}],
        model_hint="fast",
    )
    return SelectionResult(
        profile_name=profile,
        downstream_model=model,
        rule_name=rule,
        context=ctx,
    )


@pytest.fixture()
async def test_client():
    """Create a FastAPI test client with all service dependencies mocked."""
    app = create_app()

    # Mock classifier
    mock_classifier = MagicMock()
    mock_classifier.classify.return_value = SelectionContext(
        messages=[{"role": "user", "content": "Say hi."}],
        model_hint="fast",
        estimated_tokens=3,
    )

    # Mock selector
    mock_selector = MagicMock()
    mock_selector.select.return_value = _make_selection_result()

    # Mock forwarder
    mock_forwarder = MagicMock()
    mock_forwarder.forward = AsyncMock(return_value=_SAMPLE_OPENAI_RESPONSE)

    # Mock decision log
    mock_decision_log = MagicMock()
    mock_decision_log.last_n.return_value = []

    # Mock profile store
    mock_profile_store = MagicMock()
    mock_profile_store.get_profiles.return_value = {"fast": {}, "capable": {}}

    # Mock gateway
    mock_gateway = MagicMock()
    mock_gateway.close = AsyncMock()

    # Mock settings
    mock_settings = MagicMock()
    mock_settings.nine_router_url = "http://localhost:20128"
    mock_settings.port = 20401

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Inject mocks into app state (bypass lifespan)
        app.state.settings = mock_settings
        app.state.classifier = mock_classifier
        app.state.selector = mock_selector
        app.state.forwarder = mock_forwarder
        app.state.decision_log = mock_decision_log
        app.state.profile_store = mock_profile_store
        app.state.gateway = mock_gateway

        yield client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestChatCompletionsProxy:
    async def test_successful_request_returns_200(self, test_client: AsyncClient) -> None:
        resp = await test_client.post(
            "/v1/chat/completions",
            json={"model": "fast", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert resp.status_code == 200

    async def test_response_body_matches_upstream(self, test_client: AsyncClient) -> None:
        resp = await test_client.post(
            "/v1/chat/completions",
            json={"model": "fast", "messages": [{"role": "user", "content": "hi"}]},
        )
        data = resp.json()
        assert data["id"] == "chatcmpl-integration"
        assert data["choices"][0]["message"]["content"] == "Hello!"

    async def test_missing_messages_returns_422(self, test_client: AsyncClient) -> None:
        resp = await test_client.post(
            "/v1/chat/completions",
            json={"model": "fast"},
        )
        assert resp.status_code == 422

    async def test_invalid_json_returns_400(self, test_client: AsyncClient) -> None:
        resp = await test_client.post(
            "/v1/chat/completions",
            content=b"not-json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400

    async def test_classifier_called_with_body_and_headers(
        self, test_client: AsyncClient
    ) -> None:
        """Classifier must receive the request body and headers."""
        resp = await test_client.post(
            "/v1/chat/completions",
            json={"model": "fast", "messages": [{"role": "user", "content": "hello"}]},
            headers={"X-SwitchBoard-Priority": "high"},
        )
        assert resp.status_code == 200
        classifier = test_client._transport.app.state.classifier
        classifier.classify.assert_called_once()
        call_body = classifier.classify.call_args[0][0]
        assert call_body["model"] == "fast"

    async def test_forwarder_receives_rewritten_model(
        self, test_client: AsyncClient
    ) -> None:
        """The forwarder must receive a body where model = downstream_model, not the hint."""
        resp = await test_client.post(
            "/v1/chat/completions",
            json={"model": "fast", "messages": [{"role": "user", "content": "hello"}]},
        )
        assert resp.status_code == 200
        forwarder = test_client._transport.app.state.forwarder
        forwarder.forward.assert_called_once()
        call_kwargs = forwarder.forward.call_args.kwargs
        assert call_kwargs["request_body"]["model"] == "gpt-4o-mini"

    async def test_upstream_error_returns_502(self, test_client: AsyncClient) -> None:
        import httpx as _httpx

        forwarder = test_client._transport.app.state.forwarder
        forwarder.forward = AsyncMock(
            side_effect=_httpx.HTTPStatusError(
                "Bad Gateway",
                request=MagicMock(),
                response=MagicMock(status_code=502),
            )
        )
        resp = await test_client.post(
            "/v1/chat/completions",
            json={"model": "fast", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert resp.status_code == 502
