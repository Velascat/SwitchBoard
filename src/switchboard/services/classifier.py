"""RequestClassifier — converts a raw chat completion request into a SelectionContext.

Classification happens in two passes:

1. **Header pass** — reads ``X-SwitchBoard-*`` headers for explicit overrides.
   These headers are trusted and short-circuit heuristic analysis.

2. **Body heuristics pass** — inspects the request body to infer context
   attributes that were not explicitly provided by the caller:
   - ``stream`` — from the ``stream`` boolean field.
   - ``max_tokens`` — from the ``max_tokens`` / ``max_completion_tokens`` field.
   - ``temperature`` — from the ``temperature`` field.
   - ``tools_present`` — from the presence of a non-empty ``tools`` list.
   - ``estimated_tokens`` — rough estimate based on total character count of all
     message content strings (1 token ≈ 4 characters).
   - ``model_hint`` — the ``model`` field of the request.
"""

from __future__ import annotations

from typing import Any

from switchboard.domain.selection_context import SelectionContext


# Header names (lowercased for case-insensitive matching)
_HEADER_TENANT_ID = "x-switchboard-tenant-id"
_HEADER_PRIORITY = "x-switchboard-priority"
_HEADER_PROFILE = "x-switchboard-profile"
_HEADER_REQUEST_ID = "x-request-id"

# Rough token estimate: average English word ≈ 5 chars, ≈ 1.3 tokens.
# Using a simple chars/4 heuristic is standard practice for quick estimation.
_CHARS_PER_TOKEN = 4


class RequestClassifier:
    """Converts a raw chat-completion request body + headers into a :class:`SelectionContext`."""

    def classify(self, request_body: dict[str, Any], headers: dict[str, str]) -> SelectionContext:
        """Produce a :class:`SelectionContext` from a request body and its headers.

        Args:
            request_body:   Parsed JSON body of the chat completion request.
            headers:        HTTP request headers (may be mixed case; handled internally).

        Returns:
            A fully populated :class:`SelectionContext`.
        """
        normalised_headers = {k.lower(): v for k, v in headers.items()}

        # --- 1. Header overrides -------------------------------------------
        tenant_id = normalised_headers.get(_HEADER_TENANT_ID)
        priority = normalised_headers.get(_HEADER_PRIORITY)
        force_profile = normalised_headers.get(_HEADER_PROFILE)

        # --- 2. Body heuristics -------------------------------------------
        messages: list[dict[str, Any]] = request_body.get("messages", [])
        model_hint: str = request_body.get("model", "")
        stream: bool = bool(request_body.get("stream", False))
        max_tokens: int | None = request_body.get("max_tokens") or request_body.get(
            "max_completion_tokens"
        )
        temperature: float | None = request_body.get("temperature")
        tools: list | None = request_body.get("tools")
        tools_present: bool = bool(tools)

        estimated_tokens = _estimate_tokens(messages)

        # Collect anything not captured by explicit fields for rule matching
        extra: dict[str, Any] = {}
        if "response_format" in request_body:
            extra["response_format"] = request_body["response_format"]
        if "user" in request_body:
            extra["user"] = request_body["user"]

        return SelectionContext(
            messages=messages,
            model_hint=model_hint,
            stream=stream,
            max_tokens=max_tokens,
            temperature=temperature,
            tools_present=tools_present,
            estimated_tokens=estimated_tokens,
            tenant_id=tenant_id,
            priority=priority,
            force_profile=force_profile,
            extra=extra,
        )


def _estimate_tokens(messages: list[dict[str, Any]]) -> int:
    """Rough token estimate: sum character lengths of all content strings, divide by 4."""
    total_chars = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total_chars += len(content)
        elif isinstance(content, list):
            # Multi-modal content parts
            for part in content:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    total_chars += len(part["text"])
    return max(1, total_chars // _CHARS_PER_TOKEN)
