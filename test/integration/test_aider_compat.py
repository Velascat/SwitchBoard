"""Integration tests for Aider/LiteLLM API compatibility.

Verifies that SwitchBoard's /v1/chat/completions endpoint handles the
request shape that Aider (via LiteLLM) sends, and that:
- model names sent as bare names (e.g. "fast", not "openai/fast") work
- Authorization header with a dummy Bearer token is accepted
- stream: true triggers the SSE passthrough path
- stream absent / false uses the JSON response path
- Profile override via X-SwitchBoard-Profile header works
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from switchboard.app import create_app
from switchboard.domain.selection_context import SelectionContext
from switchboard.domain.selection_result import SelectionResult


_OPENAI_RESPONSE: dict[str, Any] = {
    "id": "chatcmpl-aider-compat",
    "object": "chat.completion",
    "created": 1714000000,
    "model": "gpt-4o-mini",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "4"},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11},
}

_FAKE_SSE = b"data: {}\n\ndata: [DONE]\n\n"


def _make_result(profile="fast", model="gpt-4o-mini", rule="default_short_request"):
    ctx = SelectionContext(messages=[{"role": "user", "content": "hi"}])
    return SelectionResult(
        profile_name=profile, downstream_model=model, rule_name=rule, context=ctx
    )


@pytest.fixture()
async def compat_client():
    """Test client configured for Aider/LiteLLM compatibility tests."""
    app = create_app()

    mock_classifier = MagicMock()
    mock_classifier.classify.return_value = SelectionContext(
        messages=[{"role": "user", "content": "hello"}],
        model_hint="fast",
        estimated_tokens=5,
    )

    mock_selector = MagicMock()
    mock_selector.select.return_value = _make_result()

    mock_forwarder = MagicMock()
    mock_forwarder.forward = AsyncMock(return_value=_OPENAI_RESPONSE)

    async def _fake_stream(**kwargs):
        yield _FAKE_SSE

    mock_forwarder.stream = _fake_stream

    mock_decision_log = MagicMock()
    mock_decision_log.last_n.return_value = []
    mock_profile_store = MagicMock()
    mock_profile_store.get_profiles.return_value = {
        "fast": {}, "capable": {}, "local": {}
    }
    mock_gateway = MagicMock()
    mock_gateway.close = AsyncMock()
    mock_settings = MagicMock()
    mock_settings.nine_router_url = "http://localhost:20128"
    mock_settings.port = 20401

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        app.state.settings = mock_settings
        app.state.classifier = mock_classifier
        app.state.selector = mock_selector
        app.state.forwarder = mock_forwarder
        app.state.decision_log = mock_decision_log
        app.state.profile_store = mock_profile_store
        app.state.gateway = mock_gateway
        yield client


# ---------------------------------------------------------------------------
# Aider/LiteLLM sends bare model name (without "openai/" prefix)
# ---------------------------------------------------------------------------


class TestModelNameCompat:
    async def test_bare_model_name_fast_accepted(self, compat_client) -> None:
        resp = await compat_client.post(
            "/v1/chat/completions",
            json={"model": "fast", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert resp.status_code == 200

    async def test_bare_model_name_capable_accepted(self, compat_client) -> None:
        resp = await compat_client.post(
            "/v1/chat/completions",
            json={"model": "capable", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert resp.status_code == 200

    async def test_bare_model_name_local_accepted(self, compat_client) -> None:
        resp = await compat_client.post(
            "/v1/chat/completions",
            json={"model": "local", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert resp.status_code == 200

    async def test_model_hint_passed_to_classifier(self, compat_client) -> None:
        await compat_client.post(
            "/v1/chat/completions",
            json={"model": "capable", "messages": [{"role": "user", "content": "hi"}]},
        )
        classifier = compat_client._transport.app.state.classifier
        classifier.classify.assert_called_once()
        body_arg = classifier.classify.call_args[0][0]
        assert body_arg["model"] == "capable"


# ---------------------------------------------------------------------------
# Authorization header (Bearer token from LiteLLM) is forwarded but not required
# ---------------------------------------------------------------------------


class TestAuthHeader:
    async def test_bearer_token_header_accepted(self, compat_client) -> None:
        resp = await compat_client.post(
            "/v1/chat/completions",
            json={"model": "fast", "messages": [{"role": "user", "content": "hi"}]},
            headers={"Authorization": "Bearer sk-switchboard"},
        )
        assert resp.status_code == 200

    async def test_missing_auth_header_still_accepted(self, compat_client) -> None:
        resp = await compat_client.post(
            "/v1/chat/completions",
            json={"model": "fast", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Streaming path used when stream: true
# ---------------------------------------------------------------------------


class TestStreamingDispatch:
    async def test_stream_true_returns_event_stream(self, compat_client) -> None:
        resp = await compat_client.post(
            "/v1/chat/completions",
            json={
                "model": "fast",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": True,
            },
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")

    async def test_stream_false_returns_json(self, compat_client) -> None:
        resp = await compat_client.post(
            "/v1/chat/completions",
            json={
                "model": "fast",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": False,
            },
        )
        assert resp.status_code == 200
        assert resp.headers.get("content-type", "").startswith("application/json")

    async def test_stream_absent_returns_json(self, compat_client) -> None:
        resp = await compat_client.post(
            "/v1/chat/completions",
            json={"model": "fast", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert resp.status_code == 200
        assert resp.headers.get("content-type", "").startswith("application/json")


# ---------------------------------------------------------------------------
# Profile override via X-SwitchBoard-Profile header
# ---------------------------------------------------------------------------


class TestProfileOverrideHeader:
    async def test_profile_header_forwarded_to_classifier(
        self, compat_client
    ) -> None:
        await compat_client.post(
            "/v1/chat/completions",
            json={"model": "fast", "messages": [{"role": "user", "content": "hi"}]},
            headers={"X-SwitchBoard-Profile": "capable"},
        )
        classifier = compat_client._transport.app.state.classifier
        classifier.classify.assert_called_once()
        headers_arg = classifier.classify.call_args[0][1]
        normalised = {k.lower(): v for k, v in headers_arg.items()}
        assert normalised.get("x-switchboard-profile") == "capable"

    async def test_priority_header_forwarded(self, compat_client) -> None:
        await compat_client.post(
            "/v1/chat/completions",
            json={"model": "fast", "messages": [{"role": "user", "content": "hi"}]},
            headers={"X-SwitchBoard-Priority": "high"},
        )
        classifier = compat_client._transport.app.state.classifier
        headers_arg = classifier.classify.call_args[0][1]
        normalised = {k.lower(): v for k, v in headers_arg.items()}
        assert normalised.get("x-switchboard-priority") == "high"


# ---------------------------------------------------------------------------
# Aider sends temperature / max_tokens — these must pass through silently
# ---------------------------------------------------------------------------


class TestExtraFieldPassthrough:
    async def test_temperature_field_not_rejected(self, compat_client) -> None:
        resp = await compat_client.post(
            "/v1/chat/completions",
            json={
                "model": "fast",
                "messages": [{"role": "user", "content": "hi"}],
                "temperature": 0.0,
                "max_tokens": 2048,
            },
        )
        assert resp.status_code == 200

    async def test_tools_field_not_rejected(self, compat_client) -> None:
        resp = await compat_client.post(
            "/v1/chat/completions",
            json={
                "model": "fast",
                "messages": [{"role": "user", "content": "hi"}],
                "tools": [
                    {
                        "type": "function",
                        "function": {"name": "get_weather", "parameters": {}},
                    }
                ],
            },
        )
        assert resp.status_code == 200

    async def test_system_message_accepted(self, compat_client) -> None:
        resp = await compat_client.post(
            "/v1/chat/completions",
            json={
                "model": "fast",
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": "hi"},
                ],
            },
        )
        assert resp.status_code == 200
