"""Unit tests for RetryingGateway."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, call, patch

import httpx
import pytest

from switchboard.adapters.retrying_gateway import _RETRYABLE_STATUS_CODES, RetryingGateway


def _make_status_error(status_code: int) -> httpx.HTTPStatusError:
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    return httpx.HTTPStatusError("error", request=MagicMock(), response=response)


def _make_inner(side_effects) -> MagicMock:
    """Build a mock gateway whose create_chat_completion raises a sequence of exceptions."""
    inner = MagicMock()
    inner.create_chat_completion = AsyncMock(side_effect=side_effects)
    inner.close = AsyncMock()
    return inner


_GOOD_RESPONSE = {"id": "ok", "choices": []}


# ---------------------------------------------------------------------------
# Success path (no retries needed)
# ---------------------------------------------------------------------------


class TestRetryingGatewaySuccess:
    async def test_success_on_first_attempt(self) -> None:
        inner = _make_inner([_GOOD_RESPONSE])
        gw = RetryingGateway(inner, max_retries=2)
        result = await gw.create_chat_completion({"model": "fast", "messages": []})
        assert result == _GOOD_RESPONSE
        assert inner.create_chat_completion.call_count == 1

    async def test_close_delegates_to_inner(self) -> None:
        inner = _make_inner([_GOOD_RESPONSE])
        gw = RetryingGateway(inner)
        await gw.close()
        inner.close.assert_called_once()


# ---------------------------------------------------------------------------
# Retry on transient failures
# ---------------------------------------------------------------------------


class TestRetryingGatewayRetries:
    @pytest.mark.parametrize("status_code", sorted(_RETRYABLE_STATUS_CODES))
    async def test_retries_on_retryable_status(self, status_code: int) -> None:
        inner = _make_inner([
            _make_status_error(status_code),
            _GOOD_RESPONSE,
        ])
        with patch("asyncio.sleep", new_callable=AsyncMock):
            gw = RetryingGateway(inner, max_retries=2, backoff=(0.0, 0.0))
            result = await gw.create_chat_completion({})
        assert result == _GOOD_RESPONSE
        assert inner.create_chat_completion.call_count == 2

    async def test_retries_on_timeout(self) -> None:
        inner = _make_inner([
            httpx.ReadTimeout("timed out", request=MagicMock()),
            _GOOD_RESPONSE,
        ])
        with patch("asyncio.sleep", new_callable=AsyncMock):
            gw = RetryingGateway(inner, max_retries=2, backoff=(0.0,))
            result = await gw.create_chat_completion({})
        assert result == _GOOD_RESPONSE

    async def test_retries_on_connection_error(self) -> None:
        inner = _make_inner([
            httpx.ConnectError("connection refused"),
            _GOOD_RESPONSE,
        ])
        with patch("asyncio.sleep", new_callable=AsyncMock):
            gw = RetryingGateway(inner, max_retries=2, backoff=(0.0,))
            result = await gw.create_chat_completion({})
        assert result == _GOOD_RESPONSE

    async def test_succeeds_after_two_transient_failures(self) -> None:
        inner = _make_inner([
            _make_status_error(503),
            _make_status_error(503),
            _GOOD_RESPONSE,
        ])
        with patch("asyncio.sleep", new_callable=AsyncMock):
            gw = RetryingGateway(inner, max_retries=2, backoff=(0.0, 0.0))
            result = await gw.create_chat_completion({})
        assert result == _GOOD_RESPONSE
        assert inner.create_chat_completion.call_count == 3


# ---------------------------------------------------------------------------
# Raise after exhausting retries
# ---------------------------------------------------------------------------


class TestRetryingGatewayExhausted:
    async def test_raises_after_max_retries_timeout(self) -> None:
        exc = httpx.ReadTimeout("timed out", request=MagicMock())
        inner = _make_inner([exc, exc, exc])
        with patch("asyncio.sleep", new_callable=AsyncMock):
            gw = RetryingGateway(inner, max_retries=2, backoff=(0.0, 0.0))
            with pytest.raises(httpx.TimeoutException):
                await gw.create_chat_completion({})
        assert inner.create_chat_completion.call_count == 3

    async def test_raises_after_max_retries_connection_error(self) -> None:
        exc = httpx.ConnectError("refused")
        inner = _make_inner([exc, exc, exc])
        with patch("asyncio.sleep", new_callable=AsyncMock):
            gw = RetryingGateway(inner, max_retries=2, backoff=(0.0, 0.0))
            with pytest.raises(httpx.RequestError):
                await gw.create_chat_completion({})

    async def test_raises_after_max_retries_status(self) -> None:
        exc = _make_status_error(502)
        inner = _make_inner([exc, exc, exc])
        with patch("asyncio.sleep", new_callable=AsyncMock):
            gw = RetryingGateway(inner, max_retries=2, backoff=(0.0, 0.0))
            with pytest.raises(httpx.HTTPStatusError):
                await gw.create_chat_completion({})


# ---------------------------------------------------------------------------
# No retry for 4xx (except 429)
# ---------------------------------------------------------------------------


class TestRetryingGatewayNonRetryable:
    @pytest.mark.parametrize("status_code", [400, 401, 403, 404, 422])
    async def test_no_retry_for_4xx(self, status_code: int) -> None:
        exc = _make_status_error(status_code)
        inner = _make_inner([exc])
        gw = RetryingGateway(inner, max_retries=2)
        with pytest.raises(httpx.HTTPStatusError):
            await gw.create_chat_completion({})
        assert inner.create_chat_completion.call_count == 1

    async def test_429_is_retried(self) -> None:
        inner = _make_inner([_make_status_error(429), _GOOD_RESPONSE])
        with patch("asyncio.sleep", new_callable=AsyncMock):
            gw = RetryingGateway(inner, max_retries=2, backoff=(0.0,))
            result = await gw.create_chat_completion({})
        assert result == _GOOD_RESPONSE


# ---------------------------------------------------------------------------
# Backoff delays
# ---------------------------------------------------------------------------


class TestRetryingGatewayBackoff:
    async def test_backoff_delay_applied_between_attempts(self) -> None:
        inner = _make_inner([_make_status_error(503), _make_status_error(503), _GOOD_RESPONSE])
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            gw = RetryingGateway(inner, max_retries=2, backoff=(0.5, 1.0))
            await gw.create_chat_completion({})
        assert mock_sleep.call_count == 2
        assert mock_sleep.call_args_list[0] == call(0.5)
        assert mock_sleep.call_args_list[1] == call(1.0)

    async def test_no_sleep_on_first_attempt(self) -> None:
        inner = _make_inner([_GOOD_RESPONSE])
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            gw = RetryingGateway(inner, max_retries=2)
            await gw.create_chat_completion({})
        mock_sleep.assert_not_called()


# ---------------------------------------------------------------------------
# Streaming — no retry
# ---------------------------------------------------------------------------


class TestRetryingGatewayStreaming:
    async def test_stream_delegates_to_inner(self) -> None:
        async def _fake_stream(_):
            for chunk in [b"chunk1", b"chunk2"]:
                yield chunk

        inner = MagicMock()
        inner.stream_chat_completion = _fake_stream
        inner.close = AsyncMock()

        gw = RetryingGateway(inner, max_retries=2)
        chunks = []
        async for chunk in gw.stream_chat_completion({}):
            chunks.append(chunk)

        assert chunks == [b"chunk1", b"chunk2"]
