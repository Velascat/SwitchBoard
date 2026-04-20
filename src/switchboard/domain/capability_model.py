"""CapabilityModel — describes what a downstream model can do.

Section 8.4
"""

from __future__ import annotations

from pydantic import BaseModel


class CapabilityModel(BaseModel):
    """Capabilities and metadata for a single downstream model.

    Attributes:
        name:                   Model identifier string (e.g. ``"gpt-4o-mini"``).
        supports_tools:         Whether the model reliably supports function calling.
        supports_streaming:     Whether the model supports SSE streaming responses.
        supports_long_context:  Whether the model has a large context window (> 32 k).
        quality:                Relative quality tier: ``"low"``, ``"medium"``, ``"high"``.
        cost_tier:              Relative cost tier: ``"low"``, ``"medium"``, ``"high"``.
    """

    name: str = ""
    supports_tools: bool = False
    supports_streaming: bool = True
    supports_long_context: bool = False
    quality: str = "medium"
    cost_tier: str = "medium"
