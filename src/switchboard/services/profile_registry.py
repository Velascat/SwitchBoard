"""ProfileRegistry — resolves profile names to downstream model identifiers.

Loads profiles from a :class:`~switchboard.ports.profile_store.ProfileStore` and
capabilities from a :class:`~switchboard.ports.capability_store.CapabilityStore`.
Together these two sources provide a complete picture: what profiles exist and
which downstream model each profile maps to.

The ProfileRegistry is the authoritative answer to "given profile name X, what
concrete model string should go in the 9router request?"
"""

from __future__ import annotations

from typing import Any

from switchboard.observability.logging import get_logger

logger = get_logger(__name__)


class ProfileRegistry:
    """Resolves profile names to downstream model identifiers.

    Args:
        profile_store:   Any object with a ``get_profiles() -> dict`` method.
        capability_store: Any object with a ``get_capabilities() -> dict`` method.
                          May be ``None`` if capability data is embedded in profiles.
    """

    def __init__(self, profile_store, capability_store=None) -> None:
        self._profile_store = profile_store
        self._capability_store = capability_store

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_profiles(self) -> dict[str, Any]:
        """Return all profiles as a dict keyed by profile name."""
        return self._profile_store.get_profiles()

    def resolve_profile(self, profile_name: str) -> str:
        """Return the downstream model identifier for ``profile_name``.

        Args:
            profile_name: The profile name (e.g. ``"fast"``).

        Returns:
            The downstream model string (e.g. ``"gpt-4o-mini"``).

        Raises:
            KeyError:   If the profile is not found.
            ValueError: If the profile has no ``downstream_model`` field.
        """
        profiles = self._profile_store.get_profiles()
        if profile_name not in profiles:
            raise KeyError(
                f"Profile {profile_name!r} not found in profile registry. "
                f"Available: {sorted(profiles.keys())}"
            )
        entry = profiles[profile_name]
        model = entry.get("downstream_model", "") if isinstance(entry, dict) else str(entry)

        if not model:
            raise ValueError(
                f"Profile {profile_name!r} has no 'downstream_model' field."
            )
        return model

    def profile_exists(self, profile_name: str) -> bool:
        """Return True if ``profile_name`` is present in the registry."""
        return profile_name in self._profile_store.get_profiles()

    def all_profile_names(self) -> list[str]:
        """Return a sorted list of all known profile names."""
        return sorted(self._profile_store.get_profiles().keys())
