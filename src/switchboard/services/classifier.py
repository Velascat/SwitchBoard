"""RequestClassifier — converts a raw chat completion request into a SelectionContext.

Classification happens in three passes:

1. **Header pass** — reads ``X-SwitchBoard-*`` headers for explicit overrides.
   These headers are trusted and short-circuit heuristic analysis.

2. **Body scalar pass** — extracts well-defined request fields (model, stream,
   max_tokens, temperature, tools).

3. **Heuristic pass** — derives higher-level context dimensions from message
   content and token estimates using deterministic keyword rules:
   - ``task_type``              — "code" | "analysis" | "planning" | "summarization" | "chat"
   - ``complexity``             — "low" | "medium" | "high"
   - ``requires_long_context``  — True if estimated_tokens > 6 000
   - ``requires_tools``         — True if a non-empty tools array is present
   - ``requires_structured_output`` — True if response_format is json_object or json_schema
   - ``latency_sensitivity``    — "high" when stream=True (unless overridden by header)

All heuristics are deterministic and fully inspectable here.
"""

from __future__ import annotations

import re
from typing import Any

from switchboard.domain.selection_context import SelectionContext


# ---------------------------------------------------------------------------
# Header names (lowercased for case-insensitive matching)
# ---------------------------------------------------------------------------

_HEADER_TENANT_ID = "x-switchboard-tenant-id"
_HEADER_PRIORITY = "x-switchboard-priority"
_HEADER_PROFILE = "x-switchboard-profile"
_HEADER_REQUEST_ID = "x-request-id"
_HEADER_COST_SENSITIVITY = "x-switchboard-cost-sensitivity"
_HEADER_LATENCY_SENSITIVITY = "x-switchboard-latency-sensitivity"

# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------

_CHARS_PER_TOKEN = 4
_LONG_CONTEXT_THRESHOLD = 6_000   # tokens; above this flag requires_long_context

# ---------------------------------------------------------------------------
# Task-type detection — keyword signals
# ---------------------------------------------------------------------------

# A code fence in any message is a strong signal for a code task.
_CODE_FENCE_RE = re.compile(r"```")

_CODE_PHRASES: tuple[str, ...] = (
    "write a function",
    "write a class",
    "write a script",
    "write a test",
    "implement ",
    "refactor ",
    "debug ",
    "fix the bug",
    "fix this bug",
    "unit test",
    "write code",
    "write the code",
    "add a method",
    "create a function",
)

_PLANNING_PHRASES: tuple[str, ...] = (
    "create a plan",
    "design a",
    "architecture",
    "how should i",
    "what approach",
    "roadmap",
    "outline the steps",
    "step by step",
    "plan for",
    "design pattern",
    "system design",
    "best approach",
    "how would you structure",
)

_SUMMARY_PHRASES: tuple[str, ...] = (
    "summarize",
    "summarise",
    "tldr",
    "tl;dr",
    "give me a summary",
    "brief summary",
    "key points",
    "main points",
    "sum up",
    "in short,",
)

_ANALYSIS_PHRASES: tuple[str, ...] = (
    "analyze",
    "analyse",
    "analysis of",
    "evaluate ",
    "compare and contrast",
    "pros and cons",
    "trade-offs",
    "tradeoffs",
    "investigate ",
    "what are the implications",
    "root cause",
    "diagnose ",
    "assess ",
    "assess the",
    "break down ",
    "examine ",
)

# response_format type values that indicate structured JSON output is required
_STRUCTURED_OUTPUT_TYPES: frozenset[str] = frozenset({"json_object", "json_schema"})


class RequestClassifier:
    """Converts a raw chat-completion request body + headers into a :class:`SelectionContext`."""

    def classify(self, request_body: dict[str, Any], headers: dict[str, str]) -> SelectionContext:
        normalised_headers = {k.lower(): v for k, v in headers.items()}

        # --- 1. Header overrides -------------------------------------------
        tenant_id = normalised_headers.get(_HEADER_TENANT_ID)
        priority = normalised_headers.get(_HEADER_PRIORITY)
        force_profile = normalised_headers.get(_HEADER_PROFILE)
        cost_sensitivity = normalised_headers.get(_HEADER_COST_SENSITIVITY)
        latency_sensitivity = normalised_headers.get(_HEADER_LATENCY_SENSITIVITY)

        # --- 2. Body scalars -------------------------------------------
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

        # --- 3. Heuristic pass --------------------------------------------
        task_type = _infer_task_type(messages)
        complexity = _infer_complexity(estimated_tokens, len(messages), tools_present)
        requires_long_context = estimated_tokens > _LONG_CONTEXT_THRESHOLD
        requires_tools = tools_present

        # Phase 8: detect structured output requirement
        response_format = request_body.get("response_format")
        requires_structured_output = _infer_structured_output(response_format)

        # Streaming requests are inherently latency-sensitive unless the
        # caller already specified a preference via header.
        if latency_sensitivity is None and stream:
            latency_sensitivity = "high"

        # Collect anything not captured by explicit fields
        extra: dict[str, Any] = {}
        if response_format is not None:
            extra["response_format"] = response_format
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
            # Phase 3 enriched fields
            task_type=task_type,
            complexity=complexity,
            requires_long_context=requires_long_context,
            requires_tools=requires_tools,
            cost_sensitivity=cost_sensitivity,
            latency_sensitivity=latency_sensitivity,
            # Phase 8
            requires_structured_output=requires_structured_output,
            extra=extra,
        )


# ---------------------------------------------------------------------------
# Heuristic helpers — all pure functions, deterministic, fully testable
# ---------------------------------------------------------------------------

def _extract_text(messages: list[dict[str, Any]]) -> str:
    """Concatenate all message text content into a single lowercase string."""
    parts: list[str] = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    parts.append(part["text"])
    return " ".join(parts).lower()


def _infer_task_type(messages: list[dict[str, Any]]) -> str:
    """Return the most likely task type from message content.

    Detection order: code → analysis → planning → summarization → chat (default).
    Code is checked first because other types can also reference code snippets.
    Analysis is checked before planning because many analysis phrases overlap
    with planning language.
    """
    text = _extract_text(messages)

    if _CODE_FENCE_RE.search(text) or any(p in text for p in _CODE_PHRASES):
        return "code"
    if any(p in text for p in _ANALYSIS_PHRASES):
        return "analysis"
    if any(p in text for p in _PLANNING_PHRASES):
        return "planning"
    if any(p in text for p in _SUMMARY_PHRASES):
        return "summarization"
    return "chat"


def _infer_structured_output(response_format: Any) -> bool:
    """Return True if the response_format field requires structured JSON output."""
    if not isinstance(response_format, dict):
        return False
    return response_format.get("type") in _STRUCTURED_OUTPUT_TYPES


def _infer_complexity(
    estimated_tokens: int,
    message_count: int,
    tools_present: bool,
) -> str:
    """Return complexity class based on token count, message depth, and tool use.

    Thresholds:
        high:   > 3 000 tokens  OR  > 8 messages  OR  tools present
        medium: > 500 tokens    OR  > 3 messages
        low:    everything else
    """
    if estimated_tokens > 3_000 or message_count > 8 or tools_present:
        return "high"
    if estimated_tokens > 500 or message_count > 3:
        return "medium"
    return "low"


def _estimate_tokens(messages: list[dict[str, Any]]) -> int:
    """Rough token estimate: sum character lengths of all content strings, divide by 4."""
    total_chars = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total_chars += len(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    total_chars += len(part["text"])
    return max(1, total_chars // _CHARS_PER_TOKEN)
