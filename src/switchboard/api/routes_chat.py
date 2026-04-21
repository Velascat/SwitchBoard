"""Chat completions proxy endpoint.

POST /v1/chat/completions

Flow (section 9.5):
    1. Parse incoming request body.
    2. Classify request into a SelectionContext (headers + body heuristics).
    3. Run Selector → (profile_name, downstream_model, rule_name).
    4. Rewrite ``model`` field in request body to the resolved downstream model.
    5. Forward to 9router via Forwarder.
    6. Return the provider's response verbatim.
    7. Decision record written asynchronously by the Forwarder.

Error responses follow the OpenAI error format so that API-compatible clients
receive standard error parsing:

    {"error": {"type": "...", "message": "...", "code": "...", "request_id": "..."}}
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from switchboard.api.errors import (
    internal_error,
    invalid_request,
    routing_error,
    upstream_error,
    upstream_timeout,
)
from switchboard.observability.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["chat"])


@router.post(
    "/v1/chat/completions",
    summary="Chat completion with policy-driven model selection",
)
async def chat_completions(request: Request) -> JSONResponse:
    """Accept a chat completion request, select a model via policy, and proxy to 9router.

    The request body must be a valid OpenAI chat completion request object.
    The ``model`` field is treated as a *hint* — SwitchBoard may substitute a
    different downstream model based on the active policy.

    Any extra fields in the body are passed through unchanged so that provider-
    specific extensions (e.g. ``response_format``, ``tools``) are preserved.
    """
    # Correlation ID established before any processing so it appears in all errors.
    request_id = dict(request.headers).get("x-request-id") or uuid.uuid4().hex

    # ------------------------------------------------------------------
    # 1. Parse body
    # ------------------------------------------------------------------
    try:
        body: dict[str, Any] = await request.json()
    except Exception as exc:
        return invalid_request(
            f"Invalid JSON body: {exc}",
            code="invalid_json",
            request_id=request_id,
        )

    if "messages" not in body:
        return invalid_request(
            "Field 'messages' is required.",
            code="missing_required_field",
            status_code=422,
            request_id=request_id,
        )

    headers = dict(request.headers)

    # ------------------------------------------------------------------
    # 2. Classify
    # ------------------------------------------------------------------
    classifier = request.app.state.classifier
    context = classifier.classify(body, headers)
    context.extra["request_id"] = request_id

    # ------------------------------------------------------------------
    # 3. Select
    # ------------------------------------------------------------------
    selector = request.app.state.selector
    try:
        result = selector.select(context)
    except KeyError as exc:
        logger.error("No eligible profile for request %s: %s", request_id, exc)
        return routing_error(
            f"No eligible profile could be found for this request: {exc}",
            code="no_eligible_profile",
            request_id=request_id,
        )
    except Exception as exc:
        logger.error("Selection failed for request %s: %s", request_id, exc, exc_info=True)
        return routing_error(
            "Model selection failed due to an internal error.",
            code="selection_failed",
            request_id=request_id,
        )

    # ------------------------------------------------------------------
    # 4. Rewrite model field
    # ------------------------------------------------------------------
    rewritten_body = dict(body)
    rewritten_body["model"] = result.downstream_model

    # ------------------------------------------------------------------
    # 5 & 6. Forward and return
    # ------------------------------------------------------------------
    forwarder = request.app.state.forwarder
    original_model_hint = body.get("model", "")

    if rewritten_body.get("stream"):
        async def _event_stream():
            async for chunk in forwarder.stream(
                request_body=rewritten_body,
                selection_result=result,
                original_model_hint=original_model_hint,
            ):
                yield chunk

        return StreamingResponse(_event_stream(), media_type="text/event-stream")

    try:
        response_data = await forwarder.forward(
            request_body=rewritten_body,
            selection_result=result,
            original_model_hint=original_model_hint,
        )
    except httpx.TimeoutException as exc:
        logger.error("Upstream timeout for request %s: %s", request_id, exc)
        return upstream_timeout(request_id=request_id)
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        logger.error(
            "Upstream HTTP %d for request %s: %s", status, request_id, exc
        )
        return upstream_error(
            f"Upstream responded with HTTP {status}.",
            code="upstream_http_error",
            request_id=request_id,
            status_code=502,
        )
    except httpx.RequestError as exc:
        logger.error("Upstream connection error for request %s: %s", request_id, exc)
        return upstream_error(
            f"Could not connect to the upstream model provider: {exc}",
            code="upstream_connection_error",
            request_id=request_id,
            status_code=502,
        )
    except Exception as exc:
        logger.error(
            "Unexpected error forwarding request %s: %s", request_id, exc, exc_info=True
        )
        return internal_error(request_id=request_id)

    return JSONResponse(content=response_data)
