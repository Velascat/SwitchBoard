"""Contract tests for HttpNineRouterGateway.

Uses ``respx`` to mock the 9router HTTP API and verify that the gateway:
- sends requests to the correct URL with the correct body
- returns the parsed response dict on success
- raises httpx.HTTPStatusError on 4xx/5xx responses
- raises httpx.RequestError on connection failure
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from switchboard.adapters.http_9router import HttpNineRouterGateway


NINE_ROUTER_BASE = "http://fake-9router:20128"

_SAMPLE_REQUEST: dict[str, Any] = {
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "What is 2+2?"}],
}

_SAMPLE_RESPONSE: dict[str, Any] = {
    "id": "chatcmpl-test",
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
    "usage": {"prompt_tokens": 15, "completion_tokens": 1, "total_tokens": 16},
}


@pytest.fixture()
async def gateway() -> HttpNineRouterGateway:
    gw = HttpNineRouterGateway(NINE_ROUTER_BASE)
    yield gw
    await gw.close()


class TestSuccessfulForward:
    @respx.mock
    async def test_post_to_correct_url(self, gateway: HttpNineRouterGateway) -> None:
        route = respx.post(f"{NINE_ROUTER_BASE}/v1/chat/completions").mock(
            return_value=httpx.Response(200, json=_SAMPLE_RESPONSE)
        )
        await gateway.create_chat_completion(_SAMPLE_REQUEST)
        assert route.called

    @respx.mock
    async def test_request_body_forwarded(self, gateway: HttpNineRouterGateway) -> None:
        route = respx.post(f"{NINE_ROUTER_BASE}/v1/chat/completions").mock(
            return_value=httpx.Response(200, json=_SAMPLE_RESPONSE)
        )
        await gateway.create_chat_completion(_SAMPLE_REQUEST)
        sent_body = route.calls[0].request.content
        import json
        parsed = json.loads(sent_body)
        assert parsed["model"] == "gpt-4o-mini"
        assert len(parsed["messages"]) == 1

    @respx.mock
    async def test_returns_parsed_response(self, gateway: HttpNineRouterGateway) -> None:
        respx.post(f"{NINE_ROUTER_BASE}/v1/chat/completions").mock(
            return_value=httpx.Response(200, json=_SAMPLE_RESPONSE)
        )
        result = await gateway.create_chat_completion(_SAMPLE_REQUEST)
        assert result["id"] == "chatcmpl-test"
        assert result["choices"][0]["message"]["content"] == "4"


class TestErrorHandling:
    @respx.mock
    async def test_raises_on_400(self, gateway: HttpNineRouterGateway) -> None:
        respx.post(f"{NINE_ROUTER_BASE}/v1/chat/completions").mock(
            return_value=httpx.Response(400, json={"error": {"message": "Bad request"}})
        )
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await gateway.create_chat_completion(_SAMPLE_REQUEST)
        assert exc_info.value.response.status_code == 400

    @respx.mock
    async def test_raises_on_500(self, gateway: HttpNineRouterGateway) -> None:
        respx.post(f"{NINE_ROUTER_BASE}/v1/chat/completions").mock(
            return_value=httpx.Response(500, json={"error": "internal"})
        )
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await gateway.create_chat_completion(_SAMPLE_REQUEST)
        assert exc_info.value.response.status_code == 500

    @respx.mock
    async def test_raises_on_connection_error(self, gateway: HttpNineRouterGateway) -> None:
        respx.post(f"{NINE_ROUTER_BASE}/v1/chat/completions").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        with pytest.raises(httpx.RequestError):
            await gateway.create_chat_completion(_SAMPLE_REQUEST)


class TestGatewayClose:
    async def test_close_does_not_raise(self) -> None:
        gw = HttpNineRouterGateway(NINE_ROUTER_BASE)
        await gw.close()  # should not raise

    async def test_double_close_does_not_raise(self) -> None:
        gw = HttpNineRouterGateway(NINE_ROUTER_BASE)
        await gw.close()
        await gw.close()  # httpx handles this gracefully


class TestBaseUrlHandling:
    @respx.mock
    async def test_trailing_slash_stripped(self) -> None:
        gw = HttpNineRouterGateway(NINE_ROUTER_BASE + "/")
        route = respx.post(f"{NINE_ROUTER_BASE}/v1/chat/completions").mock(
            return_value=httpx.Response(200, json=_SAMPLE_RESPONSE)
        )
        await gw.create_chat_completion(_SAMPLE_REQUEST)
        assert route.called
        await gw.close()
