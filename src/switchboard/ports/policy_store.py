"""PolicyStore port — abstraction over how policy configuration is loaded."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from switchboard.domain.policy_rule import PolicyConfig


@runtime_checkable
class PolicyStore(Protocol):
    """Contract that any policy storage backend must satisfy.

    Adapters (e.g. :class:`~switchboard.adapters.file_policy_store.FilePolicyStore`)
    implement this protocol.  The policy engine depends only on this interface.
    """

    def get_policy(self) -> PolicyConfig:
        """Load and return the current :class:`PolicyConfig`.

        Implementations may cache the result and/or watch the backing store for
        changes.  The method must be safe to call repeatedly.

        Returns:
            The active :class:`PolicyConfig`.

        Raises:
            IOError: If the policy source is unavailable.
            ValueError: If the policy source contains invalid configuration.
        """
        ...
