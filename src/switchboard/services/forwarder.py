"""Forwarder — sends a rewritten request to 9router and logs the decision.

Section 9.4

The Forwarder is responsible for:
    1. Calling the ModelGateway port to send the request to 9router.
    2. Measuring round-trip latency.
    3. Building a DecisionRecord.
    4. Persisting the record via the DecisionSink port.
    5. Returning the raw provider response dict to the caller.

It does NOT parse or validate the upstream response — it passes it through
verbatim so that provider-specific fields are preserved.
"""

from __future__ import annotations

import time
from typing import Any

from switchboard.domain.selection_result import SelectionResult
from switchboard.observability.logging import get_logger
from switchboard.ports.model_gateway import ModelGateway
from switchboard.services.decision_logger import DecisionLogger, make_decision_record

logger = get_logger(__name__)


class Forwarder:
    """Forwards a rewritten request to 9router and records the routing decision."""

    def __init__(self, gateway: ModelGateway, decision_logger: DecisionLogger) -> None:
        self._gateway = gateway
        self._decision_log = decision_logger

    async def forward(
        self,
        *,
        request_body: dict[str, Any],
        selection_result: SelectionResult,
        original_model_hint: str,
    ) -> dict[str, Any]:
        """Send ``request_body`` to 9router and return the provider's response.

        Args:
            request_body:           The (possibly rewritten) request body to forward.
                                    The ``model`` field must already be set to the
                                    resolved downstream model.
            selection_result:       The :class:`SelectionResult` from the Selector.
            original_model_hint:    The ``model`` value as originally sent by the caller,
                                    used for logging purposes.

        Returns:
            The raw JSON response from the downstream provider (via 9router).

        Raises:
            httpx.HTTPStatusError:  If 9router returns a 4xx/5xx error.
            httpx.RequestError:     If the connection to 9router fails.
        """
        start = time.monotonic()
        error_str: str | None = None
        response_data: dict[str, Any] = {}

        profile_name = selection_result.profile_name or selection_result.profile

        try:
            logger.debug(
                "Forwarding request to 9router: model=%s profile=%s rule=%s",
                request_body.get("model"),
                profile_name,
                selection_result.rule_name,
            )
            response_data = await self._gateway.create_chat_completion(request_body)
        except Exception as exc:
            error_str = str(exc)
            raise
        finally:
            latency_ms = (time.monotonic() - start) * 1000
            record = make_decision_record(
                result=selection_result,
                original_model_hint=original_model_hint,
                latency_ms=round(latency_ms, 2),
                error=error_str,
            )
            self._decision_log.append(record)
            logger.info(
                "Decision: profile=%s model=%s rule=%s latency=%.1fms",
                profile_name,
                selection_result.downstream_model,
                selection_result.rule_name,
                latency_ms,
            )

        return response_data
