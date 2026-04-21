"""RetryingGateway — retry wrapper for the ModelGateway port.

Wraps any :class:`~switchboard.ports.model_gateway.ModelGateway` implementation
and automatically retries transient failures with bounded exponential backoff.

Retry policy
------------
* Maximum 2 retries (3 total attempts).
* Only non-streaming requests are retried — streams cannot be restarted mid-flight.
* Retryable conditions:
    - ``httpx.TimeoutException`` (read or connect timeout)
    - ``httpx.RequestError`` (connection refused, DNS failure, etc.)
    - ``httpx.HTTPStatusError`` with a retryable status code:
        429  Too Many Requests
        500  Internal Server Error
        502  Bad Gateway
        503  Service Unavailable
        504  Gateway Timeout
* Non-retryable conditions (raised immediately):
    - 4xx errors other than 429 (client error — retrying won't help)
    - Any exception not listed above

Observability
-------------
Every retry attempt is logged at WARNING level with the attempt number, reason,
and backoff delay so that operators can correlate retries with upstream instability.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from switchboard.observability.logging import get_logger
from switchboard.ports.model_gateway import ModelGateway

logger = get_logger(__name__)

_RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({429, 500, 502, 503, 504})

_MAX_RETRIES = 2
_DEFAULT_BACKOFF: tuple[float, ...] = (0.5, 1.0)  # seconds before attempt 2 and 3


class RetryingGateway:
    """ModelGateway decorator that retries transient failures.

    Usage::

        inner = HttpNineRouterGateway(base_url)
        gateway = RetryingGateway(inner)
    """

    def __init__(
        self,
        inner: ModelGateway,
        max_retries: int = _MAX_RETRIES,
        backoff: tuple[float, ...] = _DEFAULT_BACKOFF,
    ) -> None:
        self._inner = inner
        self._max_retries = max_retries
        self._backoff = backoff

    # ------------------------------------------------------------------
    # ModelGateway interface
    # ------------------------------------------------------------------

    async def create_chat_completion(self, request_body: dict[str, Any]) -> dict[str, Any]:
        """Forward a chat completion request with automatic retry on transient failures."""
        last_exc: BaseException | None = None

        for attempt in range(self._max_retries + 1):
            if attempt > 0:
                delay = self._backoff[min(attempt - 1, len(self._backoff) - 1)]
                logger.warning(
                    "Retry attempt %d/%d for chat completion (backoff=%.1fs reason=%s)",
                    attempt,
                    self._max_retries,
                    delay,
                    type(last_exc).__name__,
                )
                await asyncio.sleep(delay)

            try:
                return await self._inner.create_chat_completion(request_body)

            except httpx.TimeoutException as exc:
                last_exc = exc
                logger.warning("Upstream timeout on attempt %d: %s", attempt + 1, exc)
                if attempt >= self._max_retries:
                    raise

            except httpx.HTTPStatusError as exc:
                last_exc = exc
                status = exc.response.status_code
                if status not in _RETRYABLE_STATUS_CODES:
                    # Client errors (non-429 4xx) are not retryable
                    raise
                logger.warning(
                    "Retryable HTTP %d from upstream on attempt %d",
                    status,
                    attempt + 1,
                )
                if attempt >= self._max_retries:
                    raise

            except httpx.RequestError as exc:
                last_exc = exc
                logger.warning(
                    "Connection error on attempt %d: %s",
                    attempt + 1,
                    exc,
                )
                if attempt >= self._max_retries:
                    raise

        # Unreachable — the loop always re-raises on the final attempt
        raise RuntimeError("RetryingGateway: exhausted retries without raising")  # pragma: no cover

    async def stream_chat_completion(
        self, request_body: dict[str, Any]
    ) -> AsyncGenerator[bytes, None]:
        """Delegate streaming to the inner gateway without retry.

        Streaming responses cannot be retried — the client has already begun
        consuming bytes before a failure can be detected.
        """
        async for chunk in self._inner.stream_chat_completion(request_body):
            yield chunk

    async def close(self) -> None:
        """Close the underlying gateway and drain connections."""
        await self._inner.close()
