"""FileCapabilityStore — loads capability data from a YAML file.

Implements the :class:`~switchboard.ports.capability_store.CapabilityStore` port.

The YAML file is read once and cached.  Call :meth:`reload` to force a fresh
read (useful after the file is edited without restarting the service).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from switchboard.observability.logging import get_logger

logger = get_logger(__name__)


class FileCapabilityStore:
    """Reads capability data from a YAML file on disk."""

    def __init__(self, capabilities_path: Path) -> None:
        self._path = capabilities_path
        self._cached: dict[str, Any] | None = None

    def get_capabilities(self) -> dict[str, Any]:
        """Load and return the capabilities dict from the YAML file.

        The result is cached after the first successful load.

        Returns:
            A dict keyed by model identifier, each value being a capability dict.

        The raw YAML is expected to contain a top-level ``models`` key:

        .. code-block:: yaml

            version: "1"
            models:
              gpt-4o-mini:
                supports_tools: true
                supports_streaming: true
                supports_long_context: false
                quality: medium
                cost_tier: low
        """
        if self._cached is None:
            self._cached = self._load()
        return self._cached

    def reload(self) -> dict[str, Any]:
        """Force a reload from disk and return the refreshed capabilities dict."""
        self._cached = None
        return self.get_capabilities()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load(self) -> dict[str, Any]:
        if not self._path.exists():
            logger.warning(
                "Capabilities file not found at %s; returning empty dict.", self._path
            )
            return {}

        with self._path.open("r", encoding="utf-8") as fh:
            raw: dict[str, Any] = yaml.safe_load(fh) or {}

        models: dict[str, Any] = raw.get("models", {})
        logger.info(
            "Capabilities loaded from %s: %d models",
            self._path,
            len(models),
        )
        return models
