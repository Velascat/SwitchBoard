"""CapabilityStore port — abstraction over how capability data is loaded."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class CapabilityStore(Protocol):
    """Contract that any capability storage backend must satisfy.

    Returns the raw capabilities dictionary as loaded from the backing store
    (e.g. ``capabilities.yaml``).  Callers should not mutate the returned dict.
    """

    def get_capabilities(self) -> dict[str, Any]:
        """Load and return the full capabilities mapping.

        Returns:
            A dict whose top-level keys are model identifiers and whose values
            are capability dicts (``supports_tools``, ``supports_streaming``,
            ``supports_long_context``, ``quality``, ``cost_tier``, …).

        Raises:
            IOError: If the capability source is unavailable.
        """
        ...
