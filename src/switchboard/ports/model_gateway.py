"""ModelGateway port — abstraction over the downstream LLM routing layer (9router)."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ModelGateway(Protocol):
    """Contract for sending chat completion requests to a downstream LLM provider.

    The only production implementation is
    :class:`~switchboard.adapters.http_9router.HttpNineRouterGateway` which
    forwards requests to 9router over HTTP.  Test doubles implement this
    protocol directly.
    """

    async def create_chat_completion(self, request_body: dict[str, Any]) -> dict[str, Any]:
        """Send a chat completion request and return the provider's response.

        Args:
            request_body: A dict matching the OpenAI chat completion request schema.
                          The ``model`` field must already be set to the resolved
                          downstream model identifier.

        Returns:
            The provider response as a parsed dict (OpenAI chat completion response
            schema or equivalent).

        Raises:
            httpx.HTTPStatusError: For 4xx / 5xx responses from 9router.
            httpx.RequestError:    For connection-level failures.
        """
        ...

    async def close(self) -> None:
        """Release any underlying connection resources (e.g. httpx.AsyncClient)."""
        ...
