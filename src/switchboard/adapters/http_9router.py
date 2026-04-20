"""HttpNineRouterGateway — HTTP adapter for the 9router downstream.

Implements the :class:`~switchboard.ports.model_gateway.ModelGateway` port
using ``httpx.AsyncClient``.

The gateway:
    - Maintains a single persistent ``AsyncClient`` for connection pooling.
    - Forwards requests to ``{nine_router_url}/v1/chat/completions``.
    - Raises ``httpx.HTTPStatusError`` for non-2xx responses so the caller
      can translate them into appropriate HTTP errors.
    - Must be closed (``await gateway.close()``) on application shutdown to
      drain the connection pool cleanly.
"""

from __future__ import annotations

from typing import Any

import httpx

from switchboard.observability.logging import get_logger

logger = get_logger(__name__)

_DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=120.0, write=10.0, pool=5.0)


class HttpNineRouterGateway:
    """Sends chat completion requests to a 9router instance over HTTP."""

    def __init__(
        self,
        base_url: str,
        timeout: httpx.Timeout = _DEFAULT_TIMEOUT,
    ) -> None:
        """Initialise the gateway.

        Args:
            base_url: Root URL of the 9router instance, e.g. ``http://localhost:20128``.
            timeout:  httpx timeout configuration.
        """
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=timeout,
            headers={"Content-Type": "application/json"},
        )

    async def create_chat_completion(self, request_body: dict[str, Any]) -> dict[str, Any]:
        """Forward a chat completion request to 9router.

        Args:
            request_body: OpenAI-compatible chat completion request dict.

        Returns:
            Parsed JSON response from 9router.

        Raises:
            httpx.HTTPStatusError: If 9router responds with a non-2xx status.
            httpx.RequestError:    If the connection cannot be established.
        """
        url = "/v1/chat/completions"
        logger.debug(
            "POST %s%s model=%s",
            self._base_url,
            url,
            request_body.get("model", "<unset>"),
        )
        response = await self._client.post(url, json=request_body)
        response.raise_for_status()
        return response.json()

    async def close(self) -> None:
        """Close the underlying httpx.AsyncClient and drain connections."""
        await self._client.aclose()
        logger.debug("HttpNineRouterGateway client closed")
