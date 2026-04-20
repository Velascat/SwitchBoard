"""CapabilityRegistry — maps profile names to concrete downstream model identifiers.

Loads ``capabilities.yaml`` on first access and caches it.  A profile entry
in the registry specifies which downstream model identifier (the value passed
to 9router in the ``model`` field) should be used for that profile.

YAML schema (see ``config/capabilities.yaml`` for a full example):

    version: "1"
    profiles:
      fast:
        downstream_model: gpt-4o-mini
        provider_hint: openai
      capable:
        downstream_model: gpt-4o
        provider_hint: openai
      local:
        downstream_model: llama3
        provider_hint: ollama
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from switchboard.observability.logging import get_logger

logger = get_logger(__name__)


class CapabilityRegistry:
    """Resolves a profile name to the downstream model identifier used in 9router requests."""

    def __init__(self, capabilities_path: Path) -> None:
        self._path = capabilities_path
        self._data: dict[str, Any] | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve_profile(self, profile_name: str) -> str:
        """Return the downstream model identifier for ``profile_name``.

        Args:
            profile_name: The profile name (e.g. ``"fast"``).

        Returns:
            The downstream model string (e.g. ``"gpt-4o-mini"``).

        Raises:
            KeyError: If the profile is not found in the registry.
        """
        data = self._load()
        profiles: dict[str, Any] = data.get("profiles", {})
        if profile_name not in profiles:
            raise KeyError(
                f"Profile {profile_name!r} not found in capability registry. "
                f"Available: {sorted(profiles.keys())}"
            )
        entry = profiles[profile_name]
        if isinstance(entry, dict):
            model = entry.get("downstream_model", "")
        else:
            model = str(entry)

        if not model:
            raise ValueError(
                f"Profile {profile_name!r} in capability registry has no 'downstream_model'."
            )
        return model

    def get_provider_hint(self, profile_name: str) -> str | None:
        """Return the optional provider hint for a profile, or None."""
        data = self._load()
        entry = data.get("profiles", {}).get(profile_name, {})
        if isinstance(entry, dict):
            return entry.get("provider_hint")
        return None

    def all_profiles(self) -> dict[str, Any]:
        """Return the full profiles dict from the registry."""
        return self._load().get("profiles", {})

    def reload(self) -> None:
        """Force a reload of the capabilities file on next access."""
        self._data = None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load(self) -> dict[str, Any]:
        if self._data is None:
            if not self._path.exists():
                logger.warning("Capabilities file not found at %s; using empty registry.", self._path)
                self._data = {"version": "1", "profiles": {}}
            else:
                with self._path.open("r", encoding="utf-8") as fh:
                    self._data = yaml.safe_load(fh) or {}
                logger.info(
                    "Capability registry loaded from %s (%d profiles)",
                    self._path,
                    len(self._data.get("profiles", {})),
                )
        return self._data
