"""FileProfileStore — loads model profiles from a YAML file.

Implements the :class:`~switchboard.ports.profile_store.ProfileStore` port.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from switchboard.observability.logging import get_logger

logger = get_logger(__name__)


class FileProfileStore:
    """Reads model profiles from a YAML file on disk."""

    def __init__(self, profiles_path: Path) -> None:
        self._path = profiles_path
        self._cached: dict[str, Any] | None = None

    def get_profiles(self) -> dict[str, Any]:
        """Return all profiles as a dict keyed by profile name.

        Returns:
            Mapping of ``{profile_name: profile_dict}``.

        Raises:
            FileNotFoundError: If the profiles file does not exist.
        """
        if self._cached is None:
            self._cached = self._load()
        return self._cached

    def reload(self) -> dict[str, Any]:
        """Force a reload from disk and return the refreshed profiles dict."""
        self._cached = None
        return self.get_profiles()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load(self) -> dict[str, Any]:
        if not self._path.exists():
            logger.warning("Profiles file not found at %s; returning empty dict.", self._path)
            return {}

        with self._path.open("r", encoding="utf-8") as fh:
            raw: dict[str, Any] = yaml.safe_load(fh) or {}

        profiles: dict[str, Any] = raw.get("profiles", raw)
        logger.info(
            "Profiles loaded from %s: %d profiles",
            self._path,
            len(profiles),
        )
        return profiles
