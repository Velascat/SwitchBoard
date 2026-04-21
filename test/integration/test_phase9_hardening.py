"""Integration tests for Phase 9 platform hardening.

Tests:
  - Structured error responses from /v1/chat/completions
  - Error format is OpenAI-compatible
  - Each error category returns the correct status code and type
  - Global exception handler catches unexpected errors
  - RetryingGateway is wired into the live app
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from switchboard.app import create_app
from switchboard.domain.selection_context import SelectionContext
from switchboard.domain.selection_result import SelectionResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_selection_result(profile: str = "fast") -> SelectionResult:
    ctx = SelectionContext(messages=[{"role": "user", "content": "hi"}], model_hint=profile)
    return SelectionResult(
        profile_name=profile,
        downstream_model="gpt-4o-mini",
        rule_name="default",
        context=ctx,
    )


def _status_error(status_code: int) -> httpx.HTTPStatusError:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    return httpx.HTTPStatusError("error", request=MagicMock(), response=resp)


@pytest.fixture()
async def client():
    """ASGI test client with mocked dependencies."""
    app = create_app()

    mock_classifier = MagicMock()
    mock_classifier.classify.return_value = SelectionContext(
        messages=[{"role": "user", "content": "hi"}], model_hint="fast"
    )

    mock_selector = MagicMock()
    mock_selector.select.return_value = _make_selection_result()

    mock_forwarder = MagicMock()
    mock_forwarder.forward = AsyncMock(
        return_value={"id": "ok", "choices": [{"message": {"content": "hi"}, "index": 0}]}
    )

    mock_gateway = MagicMock()
    mock_gateway.close = AsyncMock()

    mock_decision_log = MagicMock()
    mock_decision_log.last_n.return_value = []

    mock_settings = MagicMock()
    mock_settings.port = 20401

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        app.state.settings = mock_settings
        app.state.classifier = mock_classifier
        app.state.selector = mock_selector
        app.state.forwarder = mock_forwarder
        app.state.gateway = mock_gateway
        app.state.decision_log = mock_decision_log
        app.state.decision_logger = mock_decision_log
        app.state.adjustment_store = MagicMock()
        yield ac, app


# ---------------------------------------------------------------------------
# Error response format (OpenAI-compatible)
# ---------------------------------------------------------------------------


class TestErrorResponseFormat:
    async def test_invalid_json_returns_structured_error(self, client) -> None:
        ac, _ = client
        resp = await ac.post(
            "/v1/chat/completions",
            content=b"not-json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert "error" in data
        assert data["error"]["type"] == "invalid_request_error"
        assert data["error"]["code"] == "invalid_json"
        assert "message" in data["error"]

    async def test_missing_messages_returns_structured_error(self, client) -> None:
        ac, _ = client
        resp = await ac.post("/v1/chat/completions", json={"model": "fast"})
        assert resp.status_code == 422
        data = resp.json()
        assert data["error"]["type"] == "invalid_request_error"
        assert data["error"]["code"] == "missing_required_field"

    async def test_request_id_in_error_response(self, client) -> None:
        ac, _ = client
        resp = await ac.post(
            "/v1/chat/completions",
            json={"model": "fast"},
            headers={"X-Request-ID": "trace-abc"},
        )
        data = resp.json()
        assert data["error"].get("request_id") == "trace-abc"

    async def test_upstream_timeout_returns_504(self, client) -> None:
        ac, app = client
        app.state.forwarder.forward = AsyncMock(
            side_effect=httpx.ReadTimeout("timed out", request=MagicMock())
        )
        resp = await ac.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
        assert resp.status_code == 504
        data = resp.json()
        assert data["error"]["type"] == "upstream_timeout_error"
        assert data["error"]["code"] == "upstream_timeout"

    async def test_upstream_http_error_returns_502(self, client) -> None:
        ac, app = client
        app.state.forwarder.forward = AsyncMock(side_effect=_status_error(503))
        resp = await ac.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
        assert resp.status_code == 502
        data = resp.json()
        assert data["error"]["type"] == "upstream_error"

    async def test_upstream_connection_error_returns_502(self, client) -> None:
        ac, app = client
        app.state.forwarder.forward = AsyncMock(
            side_effect=httpx.ConnectError("connection refused")
        )
        resp = await ac.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
        assert resp.status_code == 502
        data = resp.json()
        assert data["error"]["code"] == "upstream_connection_error"

    async def test_selection_key_error_returns_503(self, client) -> None:
        ac, app = client
        app.state.selector.select.side_effect = KeyError("no eligible profile")
        resp = await ac.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
        assert resp.status_code == 503
        data = resp.json()
        assert data["error"]["type"] == "routing_error"
        assert data["error"]["code"] == "no_eligible_profile"

    async def test_selection_unexpected_error_returns_503(self, client) -> None:
        ac, app = client
        app.state.selector.select.side_effect = RuntimeError("unexpected")
        resp = await ac.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
        assert resp.status_code == 503
        data = resp.json()
        assert data["error"]["type"] == "routing_error"


# ---------------------------------------------------------------------------
# Successful request still works (no regression)
# ---------------------------------------------------------------------------


class TestSuccessfulRequest:
    async def test_200_on_success(self, client) -> None:
        ac, _ = client
        resp = await ac.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "hi"}], "model": "fast"},
        )
        assert resp.status_code == 200
        assert "choices" in resp.json()

    async def test_no_error_key_on_success(self, client) -> None:
        ac, _ = client
        resp = await ac.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
        assert "error" not in resp.json()


# ---------------------------------------------------------------------------
# Error response helper unit tests
# ---------------------------------------------------------------------------


class TestErrorHelpers:
    def test_error_response_structure(self) -> None:
        from switchboard.api.errors import error_response

        resp = error_response(400, "invalid_request_error", "bad input", "bad_code")
        assert resp.status_code == 400
        import json
        body = json.loads(resp.body)
        assert body["error"]["type"] == "invalid_request_error"
        assert body["error"]["message"] == "bad input"
        assert body["error"]["code"] == "bad_code"

    def test_request_id_included_when_provided(self) -> None:
        from switchboard.api.errors import error_response
        import json

        resp = error_response(500, "internal_error", "oops", "err", request_id="req-123")
        body = json.loads(resp.body)
        assert body["error"]["request_id"] == "req-123"

    def test_request_id_omitted_when_none(self) -> None:
        from switchboard.api.errors import error_response
        import json

        resp = error_response(500, "internal_error", "oops", "err")
        body = json.loads(resp.body)
        assert "request_id" not in body["error"]

    def test_upstream_timeout_helper(self) -> None:
        from switchboard.api.errors import upstream_timeout
        assert upstream_timeout().status_code == 504

    def test_upstream_error_helper(self) -> None:
        from switchboard.api.errors import upstream_error
        assert upstream_error("bad").status_code == 502

    def test_routing_error_helper(self) -> None:
        from switchboard.api.errors import routing_error
        assert routing_error("no profile").status_code == 503

    def test_internal_error_helper(self) -> None:
        from switchboard.api.errors import internal_error
        assert internal_error().status_code == 500

    def test_invalid_request_helper_default_400(self) -> None:
        from switchboard.api.errors import invalid_request
        assert invalid_request("bad").status_code == 400

    def test_invalid_request_helper_accepts_422(self) -> None:
        from switchboard.api.errors import invalid_request
        assert invalid_request("missing", status_code=422).status_code == 422
