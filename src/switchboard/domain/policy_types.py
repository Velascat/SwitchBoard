"""Re-export shim for PolicyRule and PolicyConfig.

These types have moved to :mod:`switchboard.domain.policy_rule`.
This shim keeps existing import paths working.
"""

from switchboard.domain.policy_rule import PolicyConfig, PolicyRule

__all__ = ["PolicyConfig", "PolicyRule"]
