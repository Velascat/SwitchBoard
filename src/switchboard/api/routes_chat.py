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
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

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
    # ------------------------------------------------------------------
    # 1. Parse body
    # ------------------------------------------------------------------
    try:
        body: dict[str, Any] = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON body: {exc}") from exc

    if "messages" not in body:
        raise HTTPException(status_code=422, detail="Field 'messages' is required.")

    headers = dict(request.headers)

    # ------------------------------------------------------------------
    # 2. Classify
    # ------------------------------------------------------------------
    classifier = request.app.state.classifier
    context = classifier.classify(body, headers)

    # ------------------------------------------------------------------
    # 3. Select
    # ------------------------------------------------------------------
    selector = request.app.state.selector
    try:
        result = selector.select(context)
    except Exception as exc:
        logger.error("Selection failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Model selection failed.") from exc

    # ------------------------------------------------------------------
    # 4. Rewrite model field
    # ------------------------------------------------------------------
    rewritten_body = dict(body)
    rewritten_body["model"] = result.downstream_model

    # ------------------------------------------------------------------
    # 5 & 6. Forward and return
    # ------------------------------------------------------------------
    forwarder = request.app.state.forwarder
    try:
        response_data = await forwarder.forward(
            request_body=rewritten_body,
            selection_result=result,
            original_model_hint=body.get("model", ""),
        )
    except Exception as exc:
        logger.error("Forwarding failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail=f"Upstream error: {exc}") from exc

    return JSONResponse(content=response_data)
