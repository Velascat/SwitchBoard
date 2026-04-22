"""Structured error response helpers for the SwitchBoard API.

Routing endpoints return a small structured error body:

    {"error": {"type": "...", "message": "...", "code": "...", "request_id": "..."}}

Error types
-----------
``invalid_request_error``   — 400/422: malformed or missing request fields
``routing_error``           — 503: policy evaluation or lane selection failed
``internal_error``          — 500: unexpected exception inside SwitchBoard
"""

from __future__ import annotations

from fastapi.responses import JSONResponse


def error_response(
    status_code: int,
    error_type: str,
    message: str,
    code: str,
    request_id: str | None = None,
) -> JSONResponse:
    """Build a structured JSON error response.

    Args:
        status_code: HTTP status code to return.
        error_type:  High-level category (e.g. ``"upstream_error"``).
        message:     Human-readable description of the problem.
        code:        Machine-readable slug (e.g. ``"upstream_timeout"``).
        request_id:  Correlation ID injected into the response when available.

    Returns:
        A :class:`JSONResponse` with the structured error body.
    """
    body: dict = {"type": error_type, "message": message, "code": code}
    if request_id:
        body["request_id"] = request_id
    return JSONResponse(status_code=status_code, content={"error": body})


# ---------------------------------------------------------------------------
# Convenience constructors for each error category
# ---------------------------------------------------------------------------

def invalid_request(
    message: str,
    code: str = "invalid_request",
    request_id: str | None = None,
    status_code: int = 400,
) -> JSONResponse:
    return error_response(status_code, "invalid_request_error", message, code, request_id)


def routing_error(
    message: str,
    code: str = "routing_failed",
    request_id: str | None = None,
) -> JSONResponse:
    return error_response(503, "routing_error", message, code, request_id)


def upstream_error(
    message: str,
    code: str = "upstream_error",
    request_id: str | None = None,
    status_code: int = 502,
) -> JSONResponse:
    return error_response(status_code, "upstream_error", message, code, request_id)


def upstream_timeout(
    message: str = "The downstream execution boundary did not respond in time.",
    request_id: str | None = None,
) -> JSONResponse:
    return error_response(504, "upstream_timeout_error", message, "upstream_timeout", request_id)


def internal_error(
    message: str = "An unexpected internal error occurred.",
    request_id: str | None = None,
) -> JSONResponse:
    return error_response(500, "internal_error", message, "internal_server_error", request_id)
