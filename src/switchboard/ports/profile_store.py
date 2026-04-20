"""ProfileStore port — abstraction over how model profiles are loaded."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ProfileStore(Protocol):
    """Contract that any profile storage backend must satisfy.

    Returns the profiles dictionary keyed by profile name.  Values are
    arbitrary dicts whose schema is defined in ``config/profiles.yaml``.
    """

    def get_profiles(self) -> dict[str, Any]:
        """Load and return all model profiles as a dictionary.

        Returns:
            Mapping of ``profile_name -> profile_dict``.

        Raises:
            IOError: If the profile source is unavailable.
        """
        ...
