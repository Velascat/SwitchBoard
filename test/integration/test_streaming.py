"""Integration tests for SSE streaming passthrough.

Verifies that POST /v1/chat/completions with ``stream: true`` proxies
Server-Sent Events from 9router back to the caller verbatim, and that
the routing decision is still logged.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from switchboard.app import create_app
from switchboard.domain.selection_context import SelectionContext
from switchboard.domain.selection_result import SelectionResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_SSE = (
    b'data: {"id":"chatcmpl-stream","choices":[{"delta":{"role":"assistant","content":""},"finish_reason":null,"index":0}]}\n\n'
    b'data: {"id":"chatcmpl-stream","choices":[{"delta":{"content":"Hello"},"finish_reason":null,"index":0}]}\n\n'
    b'data: {"id":"chatcmpl-stream","choices":[{"delta":{},"finish_reason":"stop","index":0}]}\n\n'
    b"data: [DONE]\n\n"
)


def _make_selection_result(
    profile: str = "fast",
    model: str = "gpt-4o-mini",
    rule: str = "default_short_request",
) -> SelectionResult:
    ctx = SelectionContext(
        messages=[{"role": "user", "content": "hi"}],
        model_hint=profile,
    )
    return SelectionResult(
        profile_name=profile,
        downstream_model=model,
        rule_name=rule,
        context=ctx,
    )


async def _make_sse_chunks():
    """Async generator that yields the fake SSE response in chunks."""
    for chunk in [_FAKE_SSE[:80], _FAKE_SSE[80:]]:
        yield chunk


@pytest.fixture()
async def streaming_client():
    """Test client with a streaming-capable forwarder mock."""
    app = create_app()

    mock_classifier = MagicMock()
    mock_classifier.classify.return_value = SelectionContext(
        messages=[{"role": "user", "content": "hi"}],
        model_hint="fast",
        estimated_tokens=3,
    )

    mock_selector = MagicMock()
    mock_selector.select.return_value = _make_selection_result()

    mock_forwarder = MagicMock()
    mock_forwarder.forward = AsyncMock(return_value={"id": "test", "choices": []})

    async def _fake_stream(**kwargs):
        async for chunk in _make_sse_chunks():
            yield chunk

    mock_forwarder.stream = _fake_stream

    mock_decision_log = MagicMock()
    mock_decision_log.last_n.return_value = []

    mock_profile_store = MagicMock()
    mock_profile_store.get_profiles.return_value = {"fast": {}}

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
# Tests
# ---------------------------------------------------------------------------


class TestStreamingPassthrough:
    async def test_stream_request_returns_200(
        self, streaming_client: AsyncClient
    ) -> None:
        resp = await streaming_client.post(
            "/v1/chat/completions",
            json={
                "model": "fast",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": True,
            },
        )
        assert resp.status_code == 200

    async def test_stream_response_content_type_is_event_stream(
        self, streaming_client: AsyncClient
    ) -> None:
        resp = await streaming_client.post(
            "/v1/chat/completions",
            json={
                "model": "fast",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": True,
            },
        )
        assert "text/event-stream" in resp.headers.get("content-type", "")

    async def test_stream_response_body_contains_sse_data(
        self, streaming_client: AsyncClient
    ) -> None:
        resp = await streaming_client.post(
            "/v1/chat/completions",
            json={
                "model": "fast",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": True,
            },
        )
        body = resp.content
        assert b"data:" in body
        assert b"[DONE]" in body

    async def test_stream_calls_forwarder_stream_not_forward(
        self, streaming_client: AsyncClient
    ) -> None:
        """Streaming requests must use forwarder.stream(), not forwarder.forward()."""
        resp = await streaming_client.post(
            "/v1/chat/completions",
            json={
                "model": "fast",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": True,
            },
        )
        assert resp.status_code == 200
        forwarder = streaming_client._transport.app.state.forwarder
        forwarder.forward.assert_not_called()

    async def test_non_stream_request_uses_forward_not_stream(
        self, streaming_client: AsyncClient
    ) -> None:
        """Non-streaming requests must use forwarder.forward(), not forwarder.stream()."""
        resp = await streaming_client.post(
            "/v1/chat/completions",
            json={
                "model": "fast",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
        assert resp.status_code == 200
        forwarder = streaming_client._transport.app.state.forwarder
        forwarder.forward.assert_called_once()

    async def test_stream_missing_messages_returns_422(
        self, streaming_client: AsyncClient
    ) -> None:
        resp = await streaming_client.post(
            "/v1/chat/completions",
            json={"model": "fast", "stream": True},
        )
        assert resp.status_code == 422


class TestStreamingForwarder:
    """Unit-level tests for Forwarder.stream() method."""

    async def test_stream_method_exists_on_forwarder(self) -> None:
        from switchboard.services.forwarder import Forwarder

        assert hasattr(Forwarder, "stream"), "Forwarder must have a stream() method"

    async def test_stream_yields_gateway_chunks(self) -> None:
        from switchboard.domain.selection_context import SelectionContext
        from switchboard.domain.selection_result import SelectionResult
        from switchboard.services.decision_logger import DecisionLogger
        from switchboard.services.forwarder import Forwarder

        chunks_received = []

        class FakeGateway:
            async def stream_chat_completion(self, body):
                yield b"data: chunk1\n\n"
                yield b"data: chunk2\n\n"
                yield b"data: [DONE]\n\n"

            async def create_chat_completion(self, body):
                return {}

            async def close(self):
                pass

        forwarder = Forwarder(FakeGateway(), DecisionLogger(None))

        ctx = SelectionContext(messages=[{"role": "user", "content": "hi"}])
        result = SelectionResult(
            profile="fast",
            profile_name="fast",
            downstream_model="gpt-4o-mini",
            rule_name="test",
            context=ctx,
        )

        async for chunk in forwarder.stream(
            request_body={"model": "gpt-4o-mini", "messages": [], "stream": True},
            selection_result=result,
            original_model_hint="fast",
        ):
            chunks_received.append(chunk)

        assert len(chunks_received) == 3
        assert b"chunk1" in chunks_received[0]
        assert b"[DONE]" in chunks_received[2]

    async def test_stream_logs_decision_after_complete(self) -> None:
        import json
        import tempfile
        from pathlib import Path

        from switchboard.domain.selection_context import SelectionContext
        from switchboard.domain.selection_result import SelectionResult
        from switchboard.services.decision_logger import DecisionLogger
        from switchboard.services.forwarder import Forwarder

        class FakeGateway:
            async def stream_chat_completion(self, body):
                yield b"data: [DONE]\n\n"

            async def create_chat_completion(self, body):
                return {}

            async def close(self):
                pass

        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "decisions.jsonl"
            forwarder = Forwarder(FakeGateway(), DecisionLogger(log_path))

            ctx = SelectionContext(messages=[{"role": "user", "content": "hi"}])
            result = SelectionResult(
                profile="capable",
                profile_name="capable",
                downstream_model="gpt-4o",
                rule_name="tool_use",
                context=ctx,
            )

            async for _ in forwarder.stream(
                request_body={"model": "gpt-4o", "messages": [], "stream": True},
                selection_result=result,
                original_model_hint="capable",
            ):
                pass

            assert log_path.exists(), "Decision log must be written after streaming"
            record = json.loads(log_path.read_text().strip())
            assert record["selected_profile"] == "capable"
            assert record["downstream_model"] == "gpt-4o"
